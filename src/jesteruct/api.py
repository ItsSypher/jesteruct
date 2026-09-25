"""HTTP API: submit a document as a job, then read the job and its manifests. Workers do the routing.

`/v1/events` streams what the workers are doing, as Server-Sent Events, and with `JST_WEB_DIR` set the API also
serves the Studio at `/`. There is no auth in v1: put it at the ingress.
"""

import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Query, UploadFile
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis
from redis.exceptions import RedisError

from . import __version__, policy, probes
from .config import Settings, get_settings
from .events import Events, Hub, sse, valkey_sink
from .evidence import EVIDENCE_VERSION
from .models import LANES, JobIndex
from .queue import JobQueue, connect
from .store import Store, input_key, job_key, manifest_key, thumb_key, view_key

RETRY_AFTER_S = 30
POLL_S = 0.5
CHUNK = 1 << 20
FINISHED = ("done", "failed")


SHA = "^[0-9a-f]{64}$"
EVENT_ID = r"^\d+-\d+$"


class _Assets(StaticFiles):
    """The built Studio. Vite fingerprints everything under assets/, so those files can be cached for good."""

    def file_response(self, full_path, stat_result, scope, status_code=200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        if scope["path"].startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


@dataclass
class _Service:
    valkey: Redis
    queue: JobQueue
    store: Store
    route_key: str
    hub: Hub
    info: dict

    async def job(self, job_id: str) -> JobIndex | None:
        """The finished index from the store, else the live state from Valkey."""
        state = await self.queue.status(job_id)
        if state is None or state["status"] == "done":
            index = await self.store.get_model(job_key(job_id), JobIndex)
            if index or state is None:
                return index
        return JobIndex(
            job_id=job_id,
            status=state["status"],
            input_key=state["input_key"],
            error=state.get("error"),
            deliveries=int(state.get("deliveries", 0)),
        )


async def _read_capped(file: UploadFile, limit: int) -> tuple[bytes, str]:
    data, digest = bytearray(), hashlib.sha256()
    while chunk := await file.read(CHUNK):
        data += chunk
        digest.update(chunk)
        if len(data) > limit:
            raise HTTPException(413, f"file is larger than {limit >> 20} MB")
    return bytes(data), digest.hexdigest()


def _info(settings: Settings, route_key: str) -> dict:
    """What the router is running: versions, the calibration, the questions Jev answers and the lanes."""
    from .pipeline import answer_basis, load_calibration

    calibration = load_calibration(settings)
    groups = {
        "routing": policy.ROUTING_QUESTIONS,
        "modifier": policy.MODIFIER_QUESTIONS,
        "continuation": policy.CONTINUATION_QUESTION,
    }
    return {
        "version": __version__,
        "route_key": route_key,
        "basis": answer_basis(settings),
        "evidence": EVIDENCE_VERSION,
        "policy": policy.POLICY_VERSION,
        "jev_model": settings.jev_model,
        "vision_model": settings.vision_model,
        "calibration": {"version": calibration.version, "threshold": calibration.threshold} if calibration else None,
        "questions": {
            name: {"group": group, "instructions": spec["instructions"], "criteria": spec.get("criteria")}
            for group, questions in groups.items()
            for name, spec in questions.items()
        },
        "lanes": LANES,
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        from .pipeline import route_key

        valkey = connect(settings)
        queue = JobQueue(valkey, settings)
        await queue.ensure_group()
        key = route_key(settings)
        hub = Hub(valkey)
        await hub.start()
        app.state.svc = _Service(valkey, queue, Store.from_settings(settings), key, hub, _info(settings, key))
        try:
            yield
        finally:
            await hub.stop()
            await valkey.aclose()

    app = FastAPI(title="jesteruct", version=__version__, lifespan=lifespan)

    def svc() -> _Service:
        return app.state.svc

    @app.post("/v1/jobs", status_code=202)
    async def submit(file: UploadFile, wait: Annotated[float, Query(ge=0, le=60)] = 0) -> Response:
        """Queue a document for routing. With `wait`, answer with the finished job if it is ready in time."""
        s = svc()
        if await s.queue.backlog() > settings.max_backlog:
            raise HTTPException(503, "too many queued jobs", headers={"Retry-After": str(RETRY_AFTER_S)})
        data, sha = await _read_capped(file, settings.max_file_mb << 20)
        key = input_key(sha)
        if not await s.store.exists(key):
            await s.store.put(key, data)
        job_id = f"{sha[:16]}-{s.route_key[:8]}"
        name = file.filename or sha
        if await s.queue.enqueue(job_id, key, name):
            await Events(valkey_sink(s.valkey), job_id)("job.queued", name=name, size=len(data))

        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait
        job = await s.job(job_id)
        while job and job.status not in FINISHED and loop.time() < deadline:
            await asyncio.sleep(POLL_S)
            job = await s.job(job_id)
        if wait and job and job.status in FINISHED:
            return JSONResponse(job.model_dump(mode="json"))
        location = f"/v1/jobs/{job_id}"
        return JSONResponse(
            {"job_id": job_id, "status": job.status if job else "queued", "links": {"self": location}},
            status_code=202,
            headers={"Location": location},
        )

    @app.get("/v1/jobs/{job_id}")
    async def get_job(job_id: str) -> JobIndex:
        if job := await svc().job(job_id):
            return job
        raise HTTPException(404, "unknown job")

    @app.get("/v1/manifests/{doc_sha}")
    async def get_manifest(doc_sha: Annotated[str, PathParam(pattern=SHA)]) -> Response:
        """The manifest routed with the current route key."""
        s = svc()
        if (data := await s.store.get(manifest_key(doc_sha, s.route_key))) is None:
            raise HTTPException(404, "no manifest for this document and route key")
        return Response(data, media_type="application/json")

    @app.get("/v1/thumbs/{doc_sha}/{page}")
    async def get_thumb(doc_sha: Annotated[str, PathParam(pattern=SHA)], page: Annotated[int, PathParam(ge=0)]):
        """A page's thumbnail. It depends only on the document's bytes, so it never changes."""
        if (data := await svc().store.get(thumb_key(doc_sha, page))) is None:
            raise HTTPException(404, "no thumbnail for this page")
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @app.get("/v1/pages/{doc_sha}/{page}")
    async def get_page_view(doc_sha: Annotated[str, PathParam(pattern=SHA)], page: Annotated[int, PathParam(ge=0)]):
        """A page at full resolution, for people. It is rendered from the stored document the first time it is asked
        for and kept, so routing never pays for it."""
        store = svc().store
        if (data := await store.get(view_key(doc_sha, page))) is None:
            if (document := await store.get(input_key(doc_sha))) is None:
                raise HTTPException(404, "this document's bytes are not stored")
            try:
                data = await asyncio.to_thread(probes.image.page_view, document, page)
            except (IndexError, EOFError, OSError) as e:
                raise HTTPException(404, f"no view of this page: {type(e).__name__}") from None
            await store.put(view_key(doc_sha, page), data)
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @app.get("/v1/info")
    async def info() -> dict:
        return svc().info

    @app.get("/v1/events")
    async def events(
        job: str | None = None,
        last: Annotated[int, Query(ge=0, le=1000)] = 0,
        last_event_id: Annotated[str | None, Header(pattern=EVENT_ID)] = None,
    ) -> StreamingResponse:
        """Progress of every job, or of one, as Server-Sent Events: recent history first, then live."""

        async def stream() -> AsyncIterator[str]:
            yield ": connected\n\n"  # proxies pass the response on at once rather than at the first event
            async with svc().hub.subscribe(after=last_event_id, last=last) as messages:
                async for message in messages:
                    if message is None or job is None or message[1]["j"] == job:
                        yield sse(message)

        headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}  # proxies must not buffer the stream
        return StreamingResponse(stream(), media_type="text/event-stream", headers=headers)

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> dict:
        try:
            await svc().valkey.ping()
        except RedisError as e:
            raise HTTPException(503, f"valkey: {e}") from e
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    if settings.web_dir:  # last, so the API routes above take precedence
        app.mount("/", _Assets(directory=settings.web_dir, html=True), name="studio")
    return app
