"""Queue worker: routes jobs from the stream and publishes their manifests and job index to the store.

A failed attempt is not acked. Its message goes idle and is reclaimed after `claim_idle_s`, which doubles as the retry
backoff, until the queue dead-letters it.
"""

import asyncio
import collections
import logging
import os
import signal
import socket
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

from prometheus_client import Counter, Gauge, Histogram, start_http_server
from redis.exceptions import RedisError

from .config import Settings
from .events import Events, Sink, valkey_sink
from .models import DocEntry, JobIndex, Manifest
from .queue import Delivery, JobQueue, connect
from .store import Store, job_key, manifest_key

if TYPE_CHECKING:
    from .pipeline import Router

log = logging.getLogger("jesteruct.worker")

JOBS = Counter("jst_jobs", "Job attempts by outcome.", ["status"])
PAGES = Counter("jst_pages", "Routed pages by lane.", ["lane"])
JOB_SECONDS = Histogram("jst_job_seconds", "Wall time of one job attempt.", buckets=(1, 5, 15, 30, 60, 120, 300, 900))
INFLIGHT = Gauge("jst_inflight_jobs", "Jobs being routed by this worker.")


async def run(settings: Settings, metrics_port: int) -> None:
    """`jst worker`: consume jobs until SIGTERM or SIGINT, then finish the in-flight ones and exit."""
    from .pipeline import open_router

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    start_http_server(metrics_port)
    valkey = connect(settings)
    store = Store.from_settings(settings)
    queue = JobQueue(valkey, settings, consumer=f"{socket.gethostname()}-{os.getpid()}")
    await queue.ensure_group()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    signals = (signal.SIGTERM, signal.SIGINT)

    def on_signal() -> None:
        log.info("stopping; finishing in-flight jobs (signal again to force)")
        stop.set()
        for sig in signals:
            loop.remove_signal_handler(sig)

    for sig in signals:
        loop.add_signal_handler(sig, on_signal)
    try:
        async with open_router(settings, store, valkey) as router:
            log.info("started consumer=%s slots=%d", queue.consumer, settings.worker_max_docs)
            await consume(queue, router, store, settings.worker_max_docs, stop, valkey_sink(valkey))
    finally:
        await valkey.aclose()


async def consume(
    queue: JobQueue, router: "Router", store: Store, slots: int, stop: asyncio.Event, sink: Sink | None = None
) -> None:
    """Keep up to `slots` jobs running until `stop` is set, then wait for the in-flight ones."""
    inflight: dict[str, asyncio.Task] = {}
    every = max(1.0, queue.claim_idle_s / 4)
    beat = asyncio.create_task(_heartbeat(queue, inflight, every))
    next_reclaim = 0.0
    try:
        while not stop.is_set():
            free = slots - len(inflight)
            if not free:
                await asyncio.wait(inflight.values(), timeout=1, return_when=asyncio.FIRST_COMPLETED)
                continue
            try:
                deliveries = []
                if time.monotonic() >= next_reclaim:
                    deliveries = await queue.reclaim(free)
                    next_reclaim = time.monotonic() + every
                deliveries = deliveries or await queue.read(free)
            except RedisError:
                log.exception("queue unavailable")
                await asyncio.sleep(1)
                continue
            for d in deliveries:
                if d.id in inflight:  # reclaimed from ourselves after missed heartbeats; it is already running
                    continue
                inflight[d.id] = asyncio.create_task(process(d, router, store, queue, sink))
                inflight[d.id].add_done_callback(lambda _, message_id=d.id: inflight.pop(message_id))
        if inflight:
            log.info("draining inflight=%d", len(inflight))
            await asyncio.wait(inflight.values())
    finally:
        beat.cancel()


async def _heartbeat(queue: JobQueue, inflight: dict[str, asyncio.Task], every: float) -> None:
    while True:
        await asyncio.sleep(every)
        try:
            await queue.heartbeat(list(inflight))
        except RedisError:
            log.exception("heartbeat failed")


async def process(d: Delivery, router: "Router", store: Store, queue: JobQueue, sink: Sink | None = None) -> None:
    """Route one job's input, write its manifests and index, then ack. On failure the message stays unacked."""
    started = time.monotonic()
    events = Events(sink, d.job_id)
    INFLIGHT.inc()
    try:
        await queue.set_status(d.job_id, "running")
        await events("job.started", deliveries=int(d.job["deliveries"]))
        with tempfile.TemporaryDirectory(prefix="jst-job-") as work:
            data = await store.get(d.job["input_key"])
            if data is None:
                raise FileNotFoundError(f"input {d.job['input_key']} is missing from the store")
            name = Path(d.job["name"]).name
            path = Path(work) / (name if name not in ("", "..") else "input")
            await asyncio.to_thread(path.write_bytes, data)
            manifests = await router.route_file(path, d.job["name"], events=events)
        documents = [await _publish(m, router.route_key, store) for m in manifests]
        index = JobIndex(
            job_id=d.job_id,
            status="done",
            input_key=d.job["input_key"],
            documents=documents,
            deliveries=int(d.job["deliveries"]),
        )
        await store.put_json(job_key(d.job_id), index)
        await queue.set_status(d.job_id, "done")
        await queue.ack(d.id)
        await events("job.done", status="done", error=None)
    except Exception as e:
        JOBS.labels("error").inc()
        log.exception("job failed job=%s delivery=%s", d.job_id, d.job.get("deliveries"))
        error = f"{type(e).__name__}: {e}"
        await events("job.retry", error=error, deliveries=int(d.job["deliveries"]))  # redelivered, or dead-lettered
        try:
            await queue.set_status(d.job_id, "queued", error=error)
        except RedisError:
            log.exception("could not record the error job=%s", d.job_id)
    else:
        JOBS.labels("done").inc()
        log.info("job done job=%s docs=%d seconds=%.1f", d.job_id, len(documents), time.monotonic() - started)
    finally:
        INFLIGHT.dec()
        JOB_SECONDS.observe(time.monotonic() - started)


async def _publish(m: Manifest, route_key: str, store: Store) -> DocEntry:
    """Store a manifest unless it is already there, and summarise it for the job index."""
    key = manifest_key(m.doc.sha256, route_key)
    if not await store.exists(key):
        await store.put_json(key, m)
    lanes = collections.Counter(p.lane for p in m.pages)
    for lane, n in lanes.items():
        PAGES.labels(lane).inc(n)
    return DocEntry(
        doc_sha=m.doc.sha256, name=m.doc.name, parent_sha=m.doc.parent_sha, manifest_key=key, lanes=dict(lanes)
    )
