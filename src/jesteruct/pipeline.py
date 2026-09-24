"""Routing one file end to end: intake → probes → (OCR + vision) → Jev → policy → segments → manifest.

CPU work (intake, PDF parsing, rendering, OCR) runs in a pebble process pool with per-task timeouts. Network work
(Jev, vision) is async. Pages run concurrently up to `page_concurrency`; each page waits only for the previous page's
text, which the continuation question needs.
"""

import asyncio
import hashlib
import json
import logging
import multiprocessing
import tempfile
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from pebble import ProcessPool
from redis.asyncio import Redis

from . import __version__, intake, policy, probes
from .config import Settings
from .evidence import EVIDENCE_VERSION, build_state
from .limiter import LocalLimiter, ValkeyLimiter
from .models import Doc, Manifest, PageEvidence, PageRef, PageRoute, Versions, VisionFacts
from .probes.ocr import resolve_backend
from .providers import OpenRouter, ProviderRejected
from .segment import segment
from .store import Store, manifest_key, thumb_key

log = logging.getLogger(__name__)


def route_key(settings: Settings) -> str:
    """Everything that can change a route. Equal keys mean a stored manifest can be reused."""
    parts = {
        "router": __version__,
        "evidence": EVIDENCE_VERSION,
        "policy": policy.POLICY_VERSION,
        "questions": policy.questions_hash(),
        "jev": settings.jev_model,
        "vision": settings.vision_model,
        "ocr": resolve_backend(settings.ocr_backend),
        "review": settings.review_threshold,
    }
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]


class Router:
    def __init__(self, settings: Settings, store: Store, provider: OpenRouter, pool: ProcessPool):
        self.settings = settings
        self.store = store
        self._provider = provider
        self._pool = pool
        self._pages = asyncio.Semaphore(settings.page_concurrency)
        self.ocr_backend = resolve_backend(settings.ocr_backend)
        self.route_key = route_key(settings)
        self.versions = Versions(
            router=__version__,
            evidence=EVIDENCE_VERSION,
            policy=policy.POLICY_VERSION,
            questions=policy.questions_hash(),
            jev_model=settings.jev_model,
            vision_model=settings.vision_model,
            ocr_backend=self.ocr_backend,
        )

    async def route_file(
        self, path: Path, name: str | None = None, text_overrides: dict[int, str] | None = None, reuse: bool = True
    ) -> list[Manifest]:
        """One manifest per routable document in the file (containers expand into their children).

        `text_overrides` replaces a page's embedded text (used by the eval to test garbled layers). Such a route does
        not describe the stored bytes, so it neither reuses nor stores manifests.
        """
        persist = not text_overrides
        with tempfile.TemporaryDirectory(prefix="jst-") as work:
            docs = await self._run(intake.expand, path, self.settings, Path(work), name)
            manifests = []
            for doc in docs:
                # the manifest records where the document came from, not the temp copy it was routed from
                label = (name or str(path)) if doc.parent_sha is None else doc.name
                labelled = doc.model_copy(update={"path": label})
                manifests.append(
                    await self._route_doc(labelled, doc.path, text_overrides or {}, reuse and persist, persist)
                )
            return manifests

    async def _route_doc(self, doc: Doc, local: str, overrides: dict[int, str], reuse: bool, persist: bool) -> Manifest:
        key = manifest_key(doc.sha256, self.route_key)
        if reuse and (existing := await self.store.get_model(key, Manifest)):
            return existing
        cost = [0.0]
        served: list[str] = []
        if doc.quarantine:
            pages = [policy.fixed_route(0, "LQ", f"quarantined: {doc.quarantine}")]
        elif doc.kind in ("office", "text"):
            pages = [policy.fixed_route(0, "L0", f"native {doc.kind} format")]
        else:
            kind = "pdf" if doc.kind == "pdf" else "image"
            loop = asyncio.get_running_loop()
            tails: list[asyncio.Future[str]] = [loop.create_future() for _ in range(doc.page_count)]
            try:
                async with asyncio.TaskGroup() as group:  # one failing page cancels its siblings
                    tasks = [
                        group.create_task(
                            self._route_page(
                                doc, PageRef(doc_path=local, index=i, kind=kind), overrides.get(i), tails, cost, served
                            )
                        )
                        for i in range(doc.page_count)
                    ]
            except BaseExceptionGroup as group_error:
                raise group_error.exceptions[0] from None
            pages = [t.result() for t in tasks]
        manifest = Manifest(
            doc=doc,
            route_key=self.route_key,
            versions=self.versions.model_copy(update={"jev_served": served[0] if served else None}),
            pages=list(pages),
            segments=segment(list(pages)),
            cost_usd=round(cost[0], 6),
        )
        if persist:
            await self.store.put_json(key, manifest)
        return manifest

    async def _route_page(
        self,
        doc: Doc,
        ref: PageRef,
        override: str | None,
        tails: list[asyncio.Future[str]],
        cost: list[float],
        served: list[str],
    ) -> PageRoute:
        i = ref.index
        async with self._pages:
            timings: dict[str, int] = {}
            start = t = time.perf_counter()
            try:
                ev, jpeg = await self._probe(ref, override)
            except Exception as e:  # probe crashed or timed out twice: the page cannot be measured
                tails[i].set_result("")
                log.warning("probe failed %s page %d: %r", doc.name, i, e)
                return policy.fixed_route(i, "LQ", f"probe_failed: {type(e).__name__}")
            timings["probe"] = _ms(t)

            vision: VisionFacts | None = None
            reasons: list[str] = []
            try:
                if not policy.text_layer_trusted(ev):
                    ev, vision = await self._read_and_look(ev, jpeg, timings, cost, reasons)
            finally:
                if not tails[i].done():
                    tails[i].set_result(ev.text)

            await self.store.put(thumb_key(doc.sha256, i), probes.image.thumbnail(jpeg))
            previous = await tails[i - 1] if i > 0 else None

            t = time.perf_counter()
            try:
                decision = await self._provider.decide(
                    build_state(ev, vision, previous), policy.questions(bool(previous))
                )
            except ProviderRejected as e:
                return policy.fixed_route(i, "LH", f"jev_rejected: {e}")
            timings["jev"] = _ms(t)
            cost[0] += decision.cost
            if decision.model:
                served.append(decision.model)

            route = policy.route_page(i, decision.answers, ev, vision, self.settings.review_threshold)
            route.reasons.extend(reasons)
            route.thumb_key = thumb_key(doc.sha256, i)
            route.timings_ms = {**timings, "total": _ms(start)}  # OCR and vision overlap, so stages don't sum to total
            return route

    async def _read_and_look(
        self, ev: PageEvidence, jpeg: bytes, timings: dict[str, int], cost: list[float], reasons: list[str]
    ) -> tuple[PageEvidence, VisionFacts | None]:
        """No trusted text layer: OCR the page and ask the vision model, in parallel."""
        t = time.perf_counter()
        ocr_task = self._run(probes.read_text, ev, jpeg, self.ocr_backend)
        vision_task = asyncio.ensure_future(self._provider.vision(jpeg))
        try:
            ev = await ocr_task
            timings["ocr"] = _ms(t)
        except Exception as e:
            reasons.append(f"ocr_failed: {type(e).__name__}")
        try:
            result = await vision_task
            timings["vision"] = _ms(t)
            cost[0] += result.cost
            return ev, result.facts
        except ProviderRejected as e:
            reasons.append(f"vision_unavailable: {e}")
            return ev, None

    async def _probe(self, ref: PageRef, override: str | None) -> tuple[PageEvidence, bytes]:
        try:
            return await self._run(probes.probe_page, ref, override)
        except Exception:  # one retry in a fresh process covers transient crashes
            return await self._run(probes.probe_page, ref, override)

    async def _run(self, fn, *args):
        future = self._pool.schedule(fn, args=args, timeout=self.settings.probe_timeout_s)
        return await asyncio.wrap_future(future)


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


@asynccontextmanager
async def open_router(settings: Settings, store: Store, valkey: Redis | None = None) -> AsyncIterator[Router]:
    limiter = ValkeyLimiter(valkey) if valkey is not None else LocalLimiter()
    pool = ProcessPool(max_workers=settings.cpu_count, max_tasks=200, context=multiprocessing.get_context("spawn"))
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=64)) as client:
        try:
            yield Router(settings, store, OpenRouter(settings, store, limiter, client), pool)
        finally:
            pool.close()
            await asyncio.to_thread(pool.join)


def _files(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for p in paths:
        if p.is_dir():
            found += sorted(
                f for f in p.rglob("*") if f.is_file() and not any(part.startswith(".") for part in f.parts)
            )
        else:
            found.append(p)
    return found


async def route_paths(paths: list[Path], settings: Settings, out: Path) -> list[Manifest]:
    """`jst route`: route files natively and write each manifest to `out`."""
    out.mkdir(parents=True, exist_ok=True)
    files = _files(paths)
    limit = asyncio.Semaphore(4)
    async with open_router(settings, Store.from_settings(settings)) as router:

        async def one(f: Path) -> list[Manifest]:
            async with limit:
                manifests = await router.route_file(f)
            for m in manifests:
                (out / f"{Path(m.doc.name).stem}-{m.doc.sha256[:8]}.json").write_text(m.model_dump_json(indent=2))
            return manifests

        results = await asyncio.gather(*(one(f) for f in files))
    return [m for ms in results for m in ms]


async def probe_state(path: Path, page: int, settings: Settings) -> dict:
    """`jst probe`: the evidence and Jev state for one page, computed in-process, without calling any provider."""
    with tempfile.TemporaryDirectory(prefix="jst-") as work:
        doc = intake.expand(path, settings, Path(work))[0]
        if doc.quarantine:
            return {"doc": doc.model_dump(), "quarantine": doc.quarantine}
        ref = PageRef(doc_path=doc.path, index=page, kind="pdf" if doc.kind == "pdf" else "image")
        ev, jpeg = probes.probe_page(ref)
        trusted = policy.text_layer_trusted(ev)
        if not trusted:
            ev = probes.read_text(ev, jpeg, resolve_backend(settings.ocr_backend))
        return {
            "doc": doc.model_dump(),
            "text_layer_trusted": trusted,
            "evidence": ev.model_dump(exclude={"text"}),
            "state": build_state(ev, None),
        }
