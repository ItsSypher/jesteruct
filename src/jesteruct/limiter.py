"""Request-rate limits per provider. With Valkey the limit is shared by every replica (GCRA in one Lua script);
without it each process enforces the limit on its own."""

import asyncio
import time
from typing import Protocol

from redis.asyncio import Redis


class Limiter(Protocol):
    async def acquire(self, key: str, per_minute: int) -> None: ...


class LocalLimiter:
    def __init__(self) -> None:
        self._tat: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, key: str, per_minute: int) -> None:
        interval = 60.0 / per_minute
        async with self._lock:
            now = time.monotonic()
            start = max(now, self._tat.get(key, now))
            self._tat[key] = start + interval
        if (wait := start - now) > 0:
            await asyncio.sleep(wait)


# Generic cell rate algorithm: each call reserves the next free slot and returns how long to wait for it.
_GCRA = """
local now = tonumber(redis.call('TIME')[1]) * 1000 + math.floor(tonumber(redis.call('TIME')[2]) / 1000)
local interval = tonumber(ARGV[1])
local tat = tonumber(redis.call('GET', KEYS[1]) or now)
local start = math.max(now, tat)
redis.call('SET', KEYS[1], start + interval, 'PX', math.ceil(start + interval - now) + 1000)
return start - now
"""


class ValkeyLimiter:
    def __init__(self, valkey: Redis) -> None:
        self._script = valkey.register_script(_GCRA)

    async def acquire(self, key: str, per_minute: int) -> None:
        wait_ms = await self._script(keys=[f"jst:rate:{key}"], args=[60_000 / per_minute])
        if wait_ms > 0:
            await asyncio.sleep(wait_ms / 1000)
