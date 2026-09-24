"""Queue, worker and API against a real Valkey in Docker; skipped when Docker is unavailable."""

import asyncio
import hashlib
import json
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import redis
from fastapi.testclient import TestClient

from jesteruct.api import create_app
from jesteruct.config import Settings
from jesteruct.events import NO_EVENTS, STREAM, Events, Hub, valkey_sink
from jesteruct.models import Doc, JobIndex, Manifest, PageRoute, Segment, Versions
from jesteruct.queue import DEAD, JobQueue, connect
from jesteruct.store import Store, input_key, job_key, manifest_key
from jesteruct.worker import consume, process

DOC_SHA = "d" * 64


@pytest.fixture(scope="module")
def valkey_url():
    if not shutil.which("docker") or subprocess.run(["docker", "info"], capture_output=True).returncode:
        pytest.skip("docker is not available")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    name = f"jst-test-{uuid.uuid4().hex[:8]}"
    cmd = ["docker", "run", "-d", "--rm", "--name", name, "-p", f"127.0.0.1:{port}:6379", "valkey/valkey:8"]
    subprocess.run(cmd, check=True, capture_output=True)
    url = f"redis://127.0.0.1:{port}/0"
    try:
        client = redis.Redis.from_url(url)
        for _ in range(100):
            try:
                client.ping()
                break
            except redis.ConnectionError:
                time.sleep(0.1)
        yield url
    finally:
        subprocess.run(["docker", "stop", name], capture_output=True)


@pytest.fixture
def settings(valkey_url, tmp_path):
    redis.Redis.from_url(valkey_url).flushdb()
    return Settings(_env_file=None, valkey_url=valkey_url, store_url=f"file://{tmp_path / 'store'}")


@pytest.fixture
async def valkey(settings):
    client = connect(settings)
    yield client
    await client.aclose()


async def new_queue(valkey, settings, consumer="a", **overrides) -> JobQueue:
    queue = JobQueue(valkey, settings.model_copy(update=overrides), consumer)
    await queue.ensure_group()
    return queue


def make_manifest(lanes: list[str]) -> Manifest:
    doc = Doc(
        sha256=DOC_SHA,
        name="scan.pdf",
        path="scan.pdf",
        kind="pdf",
        mime="application/pdf",
        size=4,
        page_count=len(lanes),
    )
    versions = Versions(
        router="0", evidence="e", policy="p", questions="q", jev_model="j", vision_model="v", ocr_backend="apple"
    )
    pages = [PageRoute(index=i, lane=lane, candidate_lane=lane, path_p=0.9) for i, lane in enumerate(lanes)]
    return Manifest(
        doc=doc,
        route_key="rk",
        versions=versions,
        pages=pages,
        segments=[Segment(start=0, end=len(lanes) - 1, lane=lanes[0])],
    )


class FakeRouter:
    route_key = "rk"

    def __init__(self, manifests=(), error: Exception | None = None, gate: asyncio.Event | None = None):
        self.manifests, self.error, self.gate = list(manifests), error, gate
        self.calls: list[tuple[str, bytes, str | None]] = []

    async def route_file(self, path: Path, name: str | None = None, events: Events = NO_EVENTS) -> list[Manifest]:
        self.calls.append((path.name, path.read_bytes(), name))
        await events("doc", doc_sha=DOC_SHA, name=name)
        if self.gate:
            await self.gate.wait()
        if self.error:
            raise self.error
        return self.manifests


@pytest.mark.anyio
async def test_enqueue_is_idempotent_and_failed_jobs_requeue(settings, valkey):
    queue = await new_queue(valkey, settings)
    await queue.ensure_group()  # a second call ignores BUSYGROUP
    assert await queue.enqueue("j1", "inputs/a", "a.pdf")
    assert not await queue.enqueue("j1", "inputs/a", "a.pdf")
    assert await valkey.xlen(settings.stream) == 1

    await queue.set_status("j1", "failed", error="boom")
    assert await queue.enqueue("j1", "inputs/a", "a.pdf")
    job = await queue.status("j1")
    assert (job["status"], job["deliveries"], "error" in job) == ("queued", "0", False)
    assert await queue.backlog() == 2


@pytest.mark.anyio
async def test_read_then_ack(settings, valkey):
    queue = await new_queue(valkey, settings)
    await queue.enqueue("j1", "inputs/a", "a.pdf")
    [d] = await queue.read(2, block_ms=10)
    assert (d.job_id, d.job["name"], d.job["deliveries"]) == ("j1", "a.pdf", "1")
    assert await queue.backlog() == 0
    assert await queue.read(2, block_ms=10) == []

    await queue.ack(d.id)
    assert (await valkey.xpending(settings.stream, settings.group))["pending"] == 0
    assert await valkey.xlen(settings.stream) == 0
    await queue.enqueue("j2", "inputs/b", "b.pdf")
    assert await queue.backlog() == 1  # lag stays known after acked messages are deleted


@pytest.mark.anyio
async def test_idle_message_is_reclaimed_unless_heartbeated(settings, valkey):
    a = await new_queue(valkey, settings, "a", claim_idle_s=1)
    b = await new_queue(valkey, settings, "b", claim_idle_s=1)
    await a.enqueue("j1", "inputs/a", "a.pdf")
    [d] = await a.read(1, block_ms=10)

    await asyncio.sleep(1.1)
    await a.heartbeat([d.id])
    assert await b.reclaim(1) == []

    await asyncio.sleep(1.1)
    [again] = await b.reclaim(1)
    assert (again.id, again.job["deliveries"]) == (d.id, "2")


@pytest.mark.anyio
async def test_dead_letter_after_max_deliveries(settings, valkey):
    queue = await new_queue(valkey, settings, claim_idle_s=0, max_deliveries=2)
    await queue.enqueue("j1", "inputs/a", "a.pdf")
    assert len(await queue.read(1, block_ms=10)) == 1
    await queue.set_status("j1", "queued", error="RuntimeError: boom")
    assert len(await queue.reclaim(1)) == 1
    assert await queue.reclaim(1) == []  # third delivery

    job = await queue.status("j1")
    assert job["status"] == "failed"
    assert "boom" in job["error"]
    [(_, dead)] = await valkey.xrange(DEAD)
    assert dead["job_id"] == "j1"
    assert await valkey.xlen(settings.stream) == 0
    [(_, event)] = await valkey.xrange(STREAM)
    assert (event["t"], json.loads(event["e"])["status"]) == ("job.done", "failed")


@pytest.mark.anyio
async def test_process_publishes_manifests_and_index(settings, valkey):
    store, queue = Store.from_settings(settings), await new_queue(valkey, settings)
    await store.put(input_key("abc"), b"%PDF")
    await queue.enqueue("j1", input_key("abc"), "scan.pdf")
    [d] = await queue.read(1, block_ms=10)
    router = FakeRouter([make_manifest(["L1", "L3", "L1"])])

    await process(d, router, store, queue, valkey_sink(valkey))

    assert [fields["t"] for _, fields in await valkey.xrange(STREAM)] == ["job.started", "doc", "job.done"]
    assert router.calls == [("scan.pdf", b"%PDF", "scan.pdf")]
    assert await store.get_model(manifest_key(DOC_SHA, "rk"), Manifest) == router.manifests[0]
    index = await store.get_model(job_key("j1"), JobIndex)
    assert (index.status, index.deliveries, len(index.documents)) == ("done", 1, 1)
    assert index.documents[0].lanes == {"L1": 2, "L3": 1}
    assert index.documents[0].manifest_key == manifest_key(DOC_SHA, "rk")
    assert (await queue.status("j1"))["status"] == "done"
    assert await valkey.xlen(settings.stream) == 0


@pytest.mark.anyio
async def test_failed_attempt_stays_pending(settings, valkey):
    store, queue = Store.from_settings(settings), await new_queue(valkey, settings)
    await store.put(input_key("abc"), b"%PDF")
    await queue.enqueue("j1", input_key("abc"), "scan.pdf")
    [d] = await queue.read(1, block_ms=10)

    await process(d, FakeRouter(error=RuntimeError("provider down")), store, queue, valkey_sink(valkey))

    assert [fields["t"] for _, fields in await valkey.xrange(STREAM)] == ["job.started", "doc", "job.retry"]
    job = await queue.status("j1")
    assert (job["status"], job["error"]) == ("queued", "RuntimeError: provider down")
    assert (await valkey.xpending(settings.stream, settings.group))["pending"] == 1
    assert not await store.exists(job_key("j1"))


@pytest.mark.anyio
async def test_consume_finishes_inflight_work_on_stop(settings, valkey):
    store, queue = Store.from_settings(settings), await new_queue(valkey, settings)
    for job in ("j1", "j2"):
        await store.put(input_key(job), b"%PDF")
    gate, stop = asyncio.Event(), asyncio.Event()
    worker = asyncio.create_task(consume(queue, FakeRouter([make_manifest(["L1"])], gate=gate), store, 1, stop))

    await queue.enqueue("j1", input_key("j1"), "one.pdf")
    for _ in range(100):
        if (await queue.status("j1"))["status"] == "running":
            break
        await asyncio.sleep(0.05)
    stop.set()
    await queue.enqueue("j2", input_key("j2"), "two.pdf")
    gate.set()
    await asyncio.wait_for(worker, 5)

    assert (await queue.status("j1"))["status"] == "done"
    assert (await queue.status("j2"))["status"] == "queued"


@pytest.mark.anyio
async def test_hub_replays_recent_history_then_streams_live_events(valkey):
    sink = valkey_sink(valkey)
    await Events(sink, "j1")("job.queued", name="a.pdf", size=4)
    await Events(sink, "j2")("job.queued", name="b.pdf", size=5)
    hub = Hub(valkey)
    await hub.start()

    async def next_event(messages):
        while (message := await anext(messages)) is None:  # skip keepalives
            pass
        return message

    try:
        async with hub.subscribe(last=1) as messages:
            replayed = await next_event(messages)
            await Events(sink, "j3")("job.started", deliveries=1)
            live = await next_event(messages)
        async with hub.subscribe(after=replayed[0]) as messages:  # a browser resuming by Last-Event-ID
            resumed = await next_event(messages)
    finally:
        await hub.stop()

    assert (replayed[1]["j"], live[1]["t"], json.loads(live[1]["e"])["deliveries"]) == ("j2", "job.started", 1)
    assert resumed == live


def test_api_submit_is_idempotent(settings, tmp_path):
    from jesteruct.pipeline import route_key

    job_id = f"{hashlib.sha256(b'hello').hexdigest()[:16]}-{route_key(settings)[:8]}"
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text("<!doctype html><title>Studio</title>")

    with TestClient(create_app(settings.model_copy(update={"web_dir": str(tmp_path / "web")}))) as client:
        files = {"file": ("hello.txt", b"hello", "text/plain")}
        first, second = client.post("/v1/jobs", files=files), client.post("/v1/jobs", files=files)
        assert (first.status_code, second.status_code) == (202, 202)
        assert (
            first.json()
            == second.json()
            == {"job_id": job_id, "status": "queued", "links": {"self": f"/v1/jobs/{job_id}"}}
        )
        assert first.headers["location"] == f"/v1/jobs/{job_id}"
        valkey = redis.Redis.from_url(settings.valkey_url, decode_responses=True)
        assert valkey.xlen(settings.stream) == 1
        assert [fields["t"] for _, fields in valkey.xrange(STREAM)] == ["job.queued"]  # once, for the new job

        assert client.get(f"/v1/jobs/{job_id}").json()["status"] == "queued"
        assert client.get("/v1/jobs/unknown").status_code == 404
        assert client.get(f"/v1/manifests/{DOC_SHA}").status_code == 404
        assert client.get(f"/v1/thumbs/{DOC_SHA}/0").status_code == 404
        info = client.get("/v1/info").json()
        assert info["route_key"] == route_key(settings) and info["questions"]["capture_defects"]["group"] == "routing"
        assert client.get("/readyz").status_code == 200
        assert "<title>Studio</title>" in client.get("/").text  # the Studio, behind the API routes
