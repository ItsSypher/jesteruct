"""Progress events for live views such as the Studio: what happens to each page, as it happens.

Workers append events to one capped Valkey stream, and the API relays it to browsers as Server-Sent Events (one
reader per API process, fanned out to every connection). Events are advisory: emitting costs one XADD and never
fails a job, a viewer that connects late replays recent history from the stream, and page text is never included.
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress

from redis.asyncio import Redis
from redis.exceptions import RedisError

log = logging.getLogger(__name__)

STREAM = "jst:events"
MAXLEN = 20_000  # a few minutes at full throughput, about 30 MB: a live feed; the manifests are the record
QUEUE = 2_000  # events buffered per browser; a viewer that falls this far behind is dropped and reconnects
KEEPALIVE_S = 15.0

Event = dict[str, object]
Sink = Callable[[Event], Awaitable[None]]
Message = tuple[str, dict[str, str]]  # stream id, fields


class Events:
    """The emitter of one job. With no sink (native runs, the evaluation) every event is discarded."""

    def __init__(self, sink: Sink | None = None, job_id: str = ""):
        self._sink = sink
        self.job_id = job_id

    async def __call__(self, type: str, **data: object) -> None:
        if self._sink is None:
            return
        try:
            await self._sink({"type": type, "job_id": self.job_id, "at": round(time.time() * 1000), **data})
        except Exception:  # a live view must never cost a job
            log.warning("event dropped type=%s job=%s", type, self.job_id, exc_info=True)


NO_EVENTS = Events()


def valkey_sink(valkey: Redis) -> Sink:
    async def sink(event: Event) -> None:
        fields = {"t": str(event["type"]), "j": str(event["job_id"]), "e": json.dumps(event, default=str)}
        await valkey.xadd(STREAM, fields, maxlen=MAXLEN, approximate=True)

    return sink


def _after(a: str, b: str) -> bool:
    """Stream ids compare as (milliseconds, sequence)."""
    return tuple(map(int, a.split("-"))) > tuple(map(int, b.split("-")))


class Hub:
    """Reads the event stream once per process and fans it out to subscribers."""

    def __init__(self, valkey: Redis):
        self._valkey = valkey
        self._subscribers: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        # Start from the newest event now, not "$" at the first read, so nothing appended in between is missed.
        newest = await self._valkey.xrevrange(STREAM, max="+", min="-", count=1)
        self._task = asyncio.create_task(self._pump(newest[0][0] if newest else "0-0"))

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

    async def _pump(self, last: str) -> None:
        while True:
            try:
                reply = await self._valkey.xread({STREAM: last}, count=500, block=10_000)
            except RedisError:
                log.warning("event stream unavailable", exc_info=True)
                await asyncio.sleep(1)
                continue
            for _, messages in reply or []:
                for message_id, fields in messages:
                    last = message_id
                    for queue in list(self._subscribers):
                        try:
                            queue.put_nowait((message_id, fields))
                        except asyncio.QueueFull:  # too slow: end its stream; the browser resumes by Last-Event-ID
                            self._subscribers.discard(queue)
                            queue.get_nowait()
                            queue.put_nowait(None)

    @asynccontextmanager
    async def subscribe(self, after: str | None = None, last: int = 0) -> AsyncIterator[AsyncIterator[Message | None]]:
        """Recent history (after an event id, or the last `last` events), then live events, without gaps or repeats.

        The iterator yields None as a keepalive when nothing has happened for KEEPALIVE_S, and ends when the
        subscriber fell too far behind.
        """
        queue: asyncio.Queue = asyncio.Queue(QUEUE)
        self._subscribers.add(queue)  # before reading history, so nothing falls between the two
        try:
            if after:
                history = await self._valkey.xrange(STREAM, min=f"({after}", max="+", count=QUEUE)
            elif last:
                history = list(reversed(await self._valkey.xrevrange(STREAM, max="+", min="-", count=last)))
            else:
                history = []

            async def messages() -> AsyncIterator[Message | None]:
                seen = after or "0-0"
                for message in history:
                    seen = message[0]
                    yield message
                while True:
                    try:
                        message = await asyncio.wait_for(queue.get(), KEEPALIVE_S)
                    except TimeoutError:
                        yield None
                        continue
                    if message is None:
                        return
                    if _after(message[0], seen):
                        seen = message[0]
                        yield message

            yield messages()
        finally:
            self._subscribers.discard(queue)


def sse(message: Message | None) -> str:
    """One Server-Sent Events frame; None is a keepalive comment."""
    if message is None:
        return ": keepalive\n\n"
    message_id, fields = message
    return f"id: {message_id}\nevent: {fields['t']}\ndata: {fields['e']}\n\n"
