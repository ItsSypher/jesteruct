"""HTTP API: submit a document as a job, then read the job and its manifests. Workers do the routing.

There is no auth in v1: put it at the ingress.
"""

import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, UploadFile
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis
from redis.exceptions import RedisError

from . import __version__
from .config import Settings, get_settings
from .models import JobIndex
from .queue import JobQueue, connect
from .store import Store, input_key, job_key, manifest_key

RETRY_AFTER_S = 30
POLL_S = 0.5
CHUNK = 1 << 20
FINISHED = ("done", "failed")


@dataclass
class _Service:
    valkey: Redis
    queue: JobQueue
    store: Store
    route_key: str

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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        from .pipeline import route_key

        valkey = connect(settings)
        queue = JobQueue(valkey, settings)
        await queue.ensure_group()
        app.state.svc = _Service(valkey, queue, Store.from_settings(settings), route_key(settings))
        try:
            yield
        finally:
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
        await s.queue.enqueue(job_id, key, file.filename or sha)

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
    async def get_manifest(doc_sha: Annotated[str, PathParam(pattern="^[0-9a-f]{64}$")]) -> Response:
        """The manifest routed with the current route key."""
        s = svc()
        if (data := await s.store.get(manifest_key(doc_sha, s.route_key))) is None:
            raise HTTPException(404, "no manifest for this document and route key")
        return Response(data, media_type="application/json")

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

    return app
