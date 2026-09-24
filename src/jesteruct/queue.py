"""Job queue on a Valkey stream with one consumer group.

Each job has a hash (`jst:job:{id}`) holding its status and delivery count; the stream only carries job ids. Workers
read as many messages as they have free slots, so the group's lag (what KEDA scales on) is the real backlog. Live work
is kept by heartbeats; a message left idle for `claim_idle_s` belongs to a crashed or failed attempt and is reclaimed.
After `max_deliveries` attempts the job moves to `jst:dead` and is marked failed.

Acked messages are deleted, so the stream holds only unfinished work. Scripts and transactions span several keys, so
the Valkey deployment must not be in cluster mode.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from .config import Settings
from .models import JobStatus

log = logging.getLogger(__name__)

DEAD = "jst:dead"
FINISHED_TTL_S = 7 * 24 * 3600  # finished jobs keep their durable index in the store; Valkey forgets them

# Queue a job unless it is already known; a failed job starts over with a fresh delivery count.
_ENQUEUE = """
local status = redis.call('HGET', KEYS[1], 'status')
if status and status ~= 'failed' then return 0 end
redis.call('DEL', KEYS[1])
redis.call('HSET', KEYS[1], 'status', 'queued', 'input_key', ARGV[2], 'name', ARGV[3], 'created_at', ARGV[4],
           'deliveries', 0)
redis.call('XADD', KEYS[2], '*', 'job_id', ARGV[1])
return 1
"""


def connect(settings: Settings) -> Redis:
    if not settings.valkey_url:
        raise ValueError("JST_VALKEY_URL is required for the API and workers")
    return Redis.from_url(settings.valkey_url, decode_responses=True)


def job_hash(job_id: str) -> str:
    return f"jst:job:{job_id}"


@dataclass(frozen=True)
class Delivery:
    id: str  # stream message id
    job_id: str
    job: dict[str, str]  # the job hash, with this delivery counted


class JobQueue:
    def __init__(self, valkey: Redis, settings: Settings, consumer: str = "api"):
        self.valkey = valkey
        self.stream = settings.stream
        self.group = settings.group
        self.consumer = consumer
        self.claim_idle_s = settings.claim_idle_s
        self.max_deliveries = settings.max_deliveries
        self._enqueue = valkey.register_script(_ENQUEUE)

    async def ensure_group(self) -> None:
        try:
            await self.valkey.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def enqueue(self, job_id: str, input_key: str, name: str) -> bool:
        """Queue a job once. True when it was newly queued; False when it is already queued, running or done."""
        created = datetime.now(UTC).isoformat()
        keys = [job_hash(job_id), self.stream]
        return bool(await self._enqueue(keys=keys, args=[job_id, input_key, name, created]))

    async def read(self, count: int, block_ms: int = 1000) -> list[Delivery]:
        """New messages for this consumer; `count` should be the number of free slots."""
        reply = await self.valkey.xreadgroup(self.group, self.consumer, {self.stream: ">"}, count=count, block=block_ms)
        return await self._deliver(reply[0][1] if reply else [])

    async def reclaim(self, count: int) -> list[Delivery]:
        """Take over messages nobody has heartbeated for `claim_idle_s`."""
        _, messages, _ = await self.valkey.xautoclaim(
            self.stream, self.group, self.consumer, self.claim_idle_s * 1000, "0-0", count=count
        )
        return await self._deliver(messages)

    async def heartbeat(self, ids: list[str]) -> None:
        """Reset the idle time of in-flight messages so they are not reclaimed."""
        if ids:
            await self.valkey.xclaim(self.stream, self.group, self.consumer, 0, ids, justid=True)

    async def ack(self, message_id: str) -> None:
        async with self.valkey.pipeline(transaction=True) as p:
            p.xack(self.stream, self.group, message_id)
            p.xdel(self.stream, message_id)
            await p.execute()

    async def status(self, job_id: str) -> dict[str, str] | None:
        return await self.valkey.hgetall(job_hash(job_id)) or None

    async def set_status(self, job_id: str, status: JobStatus, error: str | None = None) -> None:
        async with self.valkey.pipeline(transaction=True) as p:
            p.hset(job_hash(job_id), "status", status)
            if error is None:
                p.hdel(job_hash(job_id), "error")
            else:
                p.hset(job_hash(job_id), "error", error)
            if status in ("done", "failed"):
                p.expire(job_hash(job_id), FINISHED_TTL_S)
            await p.execute()

    async def backlog(self) -> int:
        """Messages not yet delivered to any worker."""
        for group in await self.valkey.xinfo_groups(self.stream):
            if group["name"] == self.group:
                if group["lag"] is not None:
                    return int(group["lag"])
                # Lag is unknown after some deletions; acked messages are deleted, so the rest are pending or unread.
                return await self.valkey.xlen(self.stream) - int(group["pending"])
        return await self.valkey.xlen(self.stream)

    async def _deliver(self, messages: list[tuple[str, dict[str, str]]]) -> list[Delivery]:
        """Count one delivery per message and dead-letter the jobs that have used up their attempts."""
        if not messages:
            return []
        async with self.valkey.pipeline(transaction=False) as p:
            for _, fields in messages:
                p.hincrby(job_hash(fields["job_id"]), "deliveries", 1)
                p.hgetall(job_hash(fields["job_id"]))
            replies = await p.execute()
        live = []
        for (message_id, fields), job in zip(messages, replies[1::2], strict=True):
            delivery = Delivery(message_id, fields["job_id"], job)
            if int(job["deliveries"]) > self.max_deliveries:
                await self._dead_letter(delivery)
            else:
                live.append(delivery)
        return live

    async def _dead_letter(self, d: Delivery) -> None:
        error = f"gave up after {self.max_deliveries} deliveries: {d.job.get('error') or 'worker lost'}"
        log.warning("dead-letter job=%s message=%s error=%r", d.job_id, d.id, error)
        async with self.valkey.pipeline(transaction=True) as p:
            p.xadd(DEAD, {"job_id": d.job_id, "message_id": d.id, "error": error})
            p.hset(job_hash(d.job_id), mapping={"status": "failed", "error": error})
            p.expire(job_hash(d.job_id), FINISHED_TTL_S)
            p.xack(self.stream, self.group, d.id)
            p.xdel(self.stream, d.id)
            await p.execute()
