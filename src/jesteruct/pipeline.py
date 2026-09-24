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
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from pebble import ProcessPool
from redis.asyncio import Redis

from . import __version__, calibrate, intake, policy, probes
from .calibrate import Calibration
from .config import Settings
from .events import NO_EVENTS, Events
from .evidence import EVIDENCE_VERSION, build_state
from .limiter import LocalLimiter, ValkeyLimiter
from .models import Doc, Lane, Manifest, PageEvidence, PageRef, PageRoute, Versions, VisionFacts
from .probes.ocr import resolve_backend
from .providers import OpenRouter, ProviderRejected
from .segment import segment
from .store import Store, manifest_key, thumb_key

log = logging.getLogger(__name__)

CALIBRATION_FILE = Path(__file__).with_name("calibration.json")  # written by `jst calibrate`, shipped with the package


def _digest(parts: dict) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]


def answer_basis(settings: Settings) -> str:
    """What Jev's answers depend on. A calibration fitted on answers of another basis does not describe these.

    The OCR backend is left out on purpose: it was measured not to change routing (docs/ARCHITECTURE.md), and a
    calibration fitted natively on macOS must serve the Linux containers too.
    """
    return _digest(
        {
            "evidence": EVIDENCE_VERSION,
            "policy": policy.POLICY_VERSION,
            "questions": policy.questions_hash(),
            "jev": settings.jev_model,
            "vision": settings.vision_model,
            "jev_batch": settings.jev_batch_size,
        }
    )


def load_calibration(settings: Settings) -> Calibration | None:
    """The shipped calibration, if enabled and fitted on this answer basis; otherwise review uses the raw threshold."""
    calibration = calibrate.load(CALIBRATION_FILE) if settings.use_calibration else None
    if calibration and calibration.basis != answer_basis(settings):
        log.warning("calibration %s was fitted on other evidence or models; not applied", calibration.version)
        return None
    return calibration


def route_key(settings: Settings) -> str:
    """Everything that can change a route. Equal keys mean a stored manifest can be reused."""
    calibration = load_calibration(settings)
    return _digest(
        {
            "answers": answer_basis(settings),
            "calibration": calibration.version if calibration else None,
            "router": __version__,
            "ocr": resolve_backend(settings.ocr_backend),
            "review": settings.review_threshold,
        }
    )


class Router:
    def __init__(self, settings: Settings, store: Store, provider: OpenRouter, pool: ProcessPool):
        self.settings = settings
        self.store = store
        self._provider = provider
        self._pool = pool
        self._pages = asyncio.Semaphore(settings.page_concurrency)
        self.ocr_backend = resolve_backend(settings.ocr_backend)
        self.calibration = load_calibration(settings)
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
        self,
        path: Path,
        name: str | None = None,
        text_overrides: dict[int, str] | None = None,
        reuse: bool = True,
        events: Events = NO_EVENTS,
    ) -> list[Manifest]:
        """One manifest per routable document in the file (containers expand into their children).

        `text_overrides` replaces a page's embedded text (used by the eval to test garbled layers). Such a route does
        not describe the stored bytes, so it neither reuses nor stores manifests. `events` reports progress to live
        views.
        """
        persist = not text_overrides
        with tempfile.TemporaryDirectory(prefix="jst-") as work:
            docs = await self._run(intake.expand, path, self.settings, Path(work), name)
            manifests = []
            for doc in docs:
                # the manifest records where the document came from, not the temp copy it was routed from
                label = (name or str(path)) if doc.parent_sha is None else doc.name
                run = _DocRun(doc.model_copy(update={"path": label}), doc.path, text_overrides or {}, events)
                await events("doc", **doc.model_dump(include=_DOC_EVENT, mode="json"), doc_sha=doc.sha256)
                manifests.append(await self._route_doc(run, reuse and persist, persist))
            return manifests

    async def _route_doc(self, run: "_DocRun", reuse: bool, persist: bool) -> Manifest:
        doc = run.doc
        key = manifest_key(doc.sha256, self.route_key)
        if reuse and (existing := await self.store.get_model(key, Manifest)):
            await run.done(existing, cached=True)
            return existing
        if doc.quarantine:
            pages = [await run.fixed(0, "LQ", f"quarantined: {doc.quarantine}")]
        elif doc.kind in ("office", "text"):
            pages = [await run.fixed(0, "L0", f"native {doc.kind} format")]
        else:
            kind = "pdf" if doc.kind == "pdf" else "image"
            loop = asyncio.get_running_loop()
            run.tails = [loop.create_future() for _ in range(doc.page_count)]
            try:
                async with asyncio.TaskGroup() as group:  # one failing page cancels its siblings
                    tasks = [
                        group.create_task(self._route_page(run, PageRef(doc_path=run.local, index=i, kind=kind)))
                        for i in range(doc.page_count)
                    ]
            except BaseExceptionGroup as group_error:
                raise group_error.exceptions[0] from None
            pages = [t.result() for t in tasks]
        manifest = Manifest(
            doc=doc,
            route_key=self.route_key,
            versions=self.versions.model_copy(update={"jev_served": run.served}),
            pages=list(pages),
            segments=segment(list(pages)),
            cost_usd=round(run.cost, 6),
        )
        if persist:
            await self.store.put_json(key, manifest)
        await run.done(manifest, cached=False)
        return manifest

    async def _route_page(self, run: "_DocRun", ref: PageRef) -> PageRoute:
        i, doc = ref.index, run.doc
        async with self._pages:
            timings: dict[str, int] = {}
            start = t = time.perf_counter()
            await run.stage(i, "probe", "start")
            try:
                ev, jpeg = await self._probe(ref, run.overrides.get(i))
            except Exception as e:  # probe crashed or timed out twice: the page cannot be measured
                run.tails[i].set_result("")
                log.warning("probe failed %s page %d: %r", doc.name, i, e)
                await run.stage(i, "probe", "fail")
                return await run.fixed(i, "LQ", f"probe_failed: {type(e).__name__}")
            timings["probe"] = _ms(t)
            trusted = policy.text_layer_trusted(ev)
            await run.stage(i, "probe", "done", timings["probe"], _probe_facts(ev, trusted))

            vision: VisionFacts | None = None
            reasons: list[str] = []
            try:
                if trusted:
                    await run.stage(i, "ocr", "skip")
                    await run.stage(i, "vision", "skip")
                else:
                    ev, vision = await self._read_and_look(run, i, ev, jpeg, timings, reasons)
            finally:
                if not run.tails[i].done():
                    run.tails[i].set_result(ev.text)

            thumb = thumb_key(doc.sha256, i)
            await self.store.put(thumb, probes.image.thumbnail(jpeg))
            previous = await run.tails[i - 1] if i > 0 else None

            state = build_state(ev, vision, previous)
            await run.stage(i, "jev", "start")
            t = time.perf_counter()
            try:
                decision = await self._provider.decide(state, policy.questions(bool(previous)))
            except ProviderRejected as e:
                await run.stage(i, "jev", "fail")
                return await run.fixed(i, "LH", f"jev_rejected: {e}", thumb)
            timings["jev"] = _ms(t)
            run.cost += decision.cost
            run.served = run.served or decision.model
            jev_facts = {"answers": decision.answers, "model": decision.model, "evidence": state["page_evidence"]}
            await run.stage(i, "jev", "done", timings["jev"], jev_facts)

            route = policy.route_page(i, decision.answers, ev, vision, self.settings.review_threshold, self.calibration)
            route.reasons.extend(reasons)
            route.thumb_key = thumb
            route.timings_ms = {**timings, "total": _ms(start)}  # OCR and vision overlap, so stages don't sum to total
            await run.routed(route)
            return route

    async def _read_and_look(
        self, run: "_DocRun", i: int, ev: PageEvidence, jpeg: bytes, timings: dict[str, int], reasons: list[str]
    ) -> tuple[PageEvidence, VisionFacts | None]:
        """No trusted text layer: OCR the page and ask the vision model, in parallel; each reports when it is done."""
        t = time.perf_counter()

        async def read() -> tuple[PageEvidence, str | None]:
            await run.stage(i, "ocr", "start")
            try:
                read = await self._run(probes.read_text, ev, jpeg, self.ocr_backend)
            except Exception as e:
                await run.stage(i, "ocr", "fail")
                return ev, f"ocr_failed: {type(e).__name__}"
            timings["ocr"] = _ms(t)
            facts = read.ocr.model_dump(exclude={"text"}) if read.ocr else None
            await run.stage(i, "ocr", "done", timings["ocr"], facts)
            return read, None

        async def look() -> tuple[VisionFacts | None, str | None]:
            await run.stage(i, "vision", "start")
            try:
                result = await self._provider.vision(jpeg)
            except ProviderRejected as e:
                await run.stage(i, "vision", "fail")
                return None, f"vision_unavailable: {e}"
            timings["vision"] = _ms(t)
            run.cost += result.cost
            await run.stage(i, "vision", "done", timings["vision"], result.facts.model_dump(mode="json"))
            return result.facts, None

        (ev, ocr_failed), (facts, vision_failed) = await asyncio.gather(read(), look())
        reasons.extend(r for r in (ocr_failed, vision_failed) if r)  # in a fixed order, so manifests are stable
        return ev, facts

    async def _probe(self, ref: PageRef, override: str | None) -> tuple[PageEvidence, bytes]:
        try:
            return await self._run(probes.probe_page, ref, override)
        except Exception:  # one retry in a fresh process covers transient crashes
            return await self._run(probes.probe_page, ref, override)

    async def _run(self, fn, *args):
        future = self._pool.schedule(fn, args=args, timeout=self.settings.probe_timeout_s)
        return await asyncio.wrap_future(future)


_DOC_EVENT = {"name", "kind", "mime", "page_count", "parent_sha", "quarantine"}


@dataclass
class _DocRun:
    """One document being routed: what its pages share, and how its progress is reported."""

    doc: Doc
    local: str  # the temporary copy the pages are read from
    overrides: dict[int, str]
    events: Events
    tails: list[asyncio.Future[str]] = field(default_factory=list)  # each page's text, for the next continuation
    cost: float = 0.0
    served: str | None = None  # the Jev model that answered first

    async def stage(self, page: int, stage: str, state: str, ms: int | None = None, data: object = None) -> None:
        await self.events("page.stage", doc_sha=self.doc.sha256, page=page, stage=stage, state=state, ms=ms, data=data)

    async def routed(self, route: PageRoute) -> None:
        thumb = f"/v1/thumbs/{self.doc.sha256}/{route.index}" if route.thumb_key else None
        await self.stage(route.index, "policy", "done", data={**route.model_dump(mode="json"), "thumb": thumb})

    async def fixed(self, page: int, lane: Lane, reason: str, thumb: str | None = None) -> PageRoute:
        """A page decided without Jev: native formats, quarantine and provider rejections."""
        route = policy.fixed_route(page, lane, reason)
        route.thumb_key = thumb
        await self.routed(route)
        return route

    async def done(self, manifest: Manifest, cached: bool) -> None:
        await self.events(
            "doc.done",
            doc_sha=self.doc.sha256,
            route_key=manifest.route_key,
            lanes=dict(Counter(p.lane for p in manifest.pages)),
            segments=[s.model_dump(mode="json") for s in manifest.segments],
            cost_usd=manifest.cost_usd,
            cached=cached,
        )


def _probe_facts(ev: PageEvidence, trusted: bool) -> dict:
    """What the probes measured, for live views; never the page text."""
    return {
        "text_layer_trusted": trusted,
        "evidence": build_state(ev, None)["page_evidence"],
        "image": ev.image.model_dump(mode="json"),
        "layout": ev.layout.model_dump(mode="json") if ev.layout else None,
        "pdf": ev.pdf.model_dump(mode="json") if ev.pdf else None,
    }


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
