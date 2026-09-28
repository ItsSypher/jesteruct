"""The two hosted models behind one gateway (OpenRouter): Jev decisions and the Gemini vision check.

Every response is cached in the object store under a hash of its request, so re-running a document is free and
deterministic. Transient failures retry with jitter until a deadline, then raise ProviderUnavailable (the job is
retried later); a request the provider rejects raises ProviderRejected (that page goes to human review).
"""

import asyncio
import base64
import contextlib
import hashlib
import json
import random
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

import httpx

from .config import Settings
from .limiter import Limiter
from .models import VisionFacts
from .store import Store, cache_key

VISION_PROMPT = """You triage document pages for a processing pipeline. Look at the page image and report only what you can see.

capture - how the image was produced:
- digital_render: rendered directly from a digital file; perfectly flat, uniform background, no scanner or camera artefacts.
- flatbed_scan: a physical page on a scanner; flat, but with scan noise, grey or uneven paper tone, slight skew, speckles or copier artefacts.
- fax: bilevel (pure black and white) low-resolution image, jagged text, often a fax header line and streaks.
- camera_photo: a photo of a physical page; perspective distortion, curved or warped paper, uneven lighting or shadows, background visible around the page.
- screenshot: a capture of a screen or app UI; window chrome, UI elements, pixel-exact rendering.

legibility - how easy the text is to read for OCR: clean, mild_issues, hard_to_read, illegible.

defects - true for each defect that makes some characters harder to read: photocopy (blotchy, bleeding, broken or dithered strokes from copying), bleed_through (text or pictures from the reverse side show through), curved_page (curved, warped or folded paper, or a book spread bending into its gutter), heavy_speckle (dense dots, dirt or noise over the text), faded_text (faint, thin or broken characters). Light speckle, a paper tint, light banding or stripes, and a faint watermark behind crisp text are not defects.

handwriting:
- none: no handwriting at all.
- annotations_only: printed page with handwritten notes, marks or signatures.
- fields_filled_by_hand: printed form whose fields are filled in by hand.
- mostly_handwritten: the main content is handwritten.

content - true if the page contains at least one: table (rows and columns of cells), math (equations or mathematical notation), form (labelled fields, boxes or checkboxes to fill), code (source code or configuration listing), chart (plot, graph or diagram of data), photo (photographic picture).

script - the main writing system of the text.

Use "unsure" only when the image genuinely does not let you decide."""  # noqa: E501

_FLAGS = ["table", "math", "form", "code", "chart", "photo"]
_DEFECTS = ["photocopy", "bleed_through", "curved_page", "heavy_speckle", "faded_text"]
VISION_SCHEMA = {
    "name": "page_triage",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["capture", "legibility", "defects", "handwriting", "content", "script"],
        "properties": {
            "capture": {
                "type": "string",
                "enum": ["digital_render", "flatbed_scan", "fax", "camera_photo", "screenshot", "unsure"],
            },
            "legibility": {"type": "string", "enum": ["clean", "mild_issues", "hard_to_read", "illegible", "unsure"]},
            "defects": {
                "type": "object",
                "additionalProperties": False,
                "required": _DEFECTS,
                "properties": {k: {"type": "boolean"} for k in _DEFECTS},
            },
            "handwriting": {
                "type": "string",
                "enum": ["none", "annotations_only", "fields_filled_by_hand", "mostly_handwritten", "unsure"],
            },
            "content": {
                "type": "object",
                "additionalProperties": False,
                "required": _FLAGS,
                "properties": {k: {"type": "boolean"} for k in _FLAGS},
            },
            "script": {
                "type": "string",
                "enum": ["latin", "cyrillic", "greek", "arabic", "hebrew", "cjk", "other", "mixed", "unsure"],
            },
        },
    },
}


T = TypeVar("T")
JEV_PATH = "/alpha/decisions"
MAX_UNUSABLE = 3  # attempts with malformed output before a request counts as rejected
_UNUSABLE = (KeyError, IndexError, TypeError, ValueError)
_FIELD = re.compile(r"`([a-z_]+)`")


def _digest(path: str, body: dict) -> str:
    return hashlib.sha256(json.dumps({"path": path, "body": body}, sort_keys=True).encode()).hexdigest()


def _raw(data: dict, key: str) -> dict:
    return data["answers"][key]


def _answers(data: dict, questions: dict) -> dict[str, float]:
    out = {}
    for key, spec in questions.items():
        a = _raw(data, key)
        out[key] = float(a["noul"] if spec["type"] == "noul" else a["score"])
    return out


def _scoped(i: int, spec: dict) -> dict:
    """A question about page i of a batched request: field references and the question itself point at page i."""
    instructions = _FIELD.sub(lambda m: f"`p{i}_{m.group(1)}`", spec["instructions"])
    return {**spec, "instructions": f"About page p{i} only (the state fields that start with `p{i}_`): {instructions}"}


@dataclass
class _Pending:
    state: dict[str, str]
    questions: dict
    key: str  # this page's own cache key
    future: asyncio.Future


class _Batcher:
    """Coalesces concurrent decisions into requests of up to `size` pages, waiting at most `wait_s` to fill one."""

    def __init__(self, send: Callable[[list[_Pending]], Awaitable[None]], size: int, wait_s: float):
        self._send, self._size, self._wait = send, size, wait_s
        self._pending: list[_Pending] = []
        self._timer: asyncio.TimerHandle | None = None
        self._inflight: set[asyncio.Task] = set()

    def add(self, pending: _Pending) -> None:
        self._pending.append(pending)
        if len(self._pending) >= self._size:
            self._flush()
        elif self._timer is None:
            self._timer = asyncio.get_running_loop().call_later(self._wait, self._flush)

    def _flush(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        while self._pending:
            batch, self._pending = self._pending[: self._size], self._pending[self._size :]
            task = asyncio.create_task(self._send(batch))
            self._inflight.add(task)
            task.add_done_callback(self._inflight.discard)


class ProviderRejected(Exception):
    """The provider refused this request (4xx, invalid output). Retrying will not help."""


class ProviderUnavailable(Exception):
    """The provider kept failing until the deadline. Retry the job later."""


@dataclass
class Decision:
    answers: dict[str, float]
    model: str | None
    cost: float


@dataclass
class Vision:
    facts: VisionFacts
    cost: float


class OpenRouter:
    def __init__(self, settings: Settings, store: Store, limiter: Limiter, client: httpx.AsyncClient):
        self._s = settings
        self._store = store
        self._limiter = limiter
        self._client = client
        # Checked here, because httpx rejects an empty bearer header as a transport error, which is retried for minutes.
        if not (key := settings.openrouter_api_key.get_secret_value().strip()):
            raise ValueError("no OpenRouter API key: set OPENROUTER_API_KEY in .env (copy .env.example)")
        self._headers = {"Authorization": f"Bearer {key}"}
        self._batcher = _Batcher(self._decide_batch, settings.jev_batch_size, settings.jev_batch_wait_ms / 1000)

    async def decide(self, state: dict[str, str], questions: dict) -> Decision:
        if self._s.jev_batch_size > 1:
            body = {"model": self._s.jev_model, "state": state, "questions": questions}
            key = cache_key("jev", _digest(JEV_PATH, {**body, "batch": self._s.jev_batch_size}))
            pending = _Pending(state, questions, key, asyncio.get_running_loop().create_future())
            self._batcher.add(pending)
            return await pending.future
        return await self._decide_one(state, questions)

    async def _decide_one(self, state: dict[str, str], questions: dict) -> Decision:
        body = {"model": self._s.jev_model, "state": state, "questions": questions}
        answers, data, cost = await self._call(
            "jev", JEV_PATH, body, self._s.jev_timeout_s, self._s.jev_rpm, lambda d: _answers(d, questions)
        )
        return Decision(answers=answers, model=data.get("model"), cost=cost)

    async def _decide_batch(self, pages: list["_Pending"]) -> None:
        """One Jev request for several pages. Each page's answers are cached under its own key, so a replay does
        not depend on which pages happened to share a request. A page left alone is asked unprefixed, exactly as it
        would be without batching."""
        todo = []
        for p in pages:
            cached = await self._store.get_json(p.key)
            try:
                p.future.set_result(Decision(answers=_answers(cached, p.questions), model=cached.get("model"), cost=0))
            except (*_UNUSABLE, AttributeError):
                todo.append(p)
        if not todo:
            return
        solo = len(todo) == 1

        def name(i: int, field: str) -> str:
            return field if solo else f"p{i}_{field}"

        state = {name(i, k): v for i, p in enumerate(todo) for k, v in p.state.items()}
        questions = {
            name(i, q): spec if solo else _scoped(i, spec)
            for i, p in enumerate(todo)
            for q, spec in p.questions.items()
        }
        body = {"model": self._s.jev_model, "state": state, "questions": questions}
        try:
            answers, data, cost = await self._call(
                "jev",
                JEV_PATH,
                body,
                self._s.jev_timeout_s,
                self._s.jev_rpm,
                lambda d: _answers(d, questions),
                cache=False,
            )
        except Exception as e:
            for p in todo:
                p.future.set_exception(e)
            return
        for i, p in enumerate(todo):
            mine = {q: answers[name(i, q)] for q in p.questions}
            record = {"model": data.get("model"), "answers": {q: _raw(data, name(i, q)) for q in p.questions}}
            await self._store.put_json(p.key, record)
            p.future.set_result(Decision(answers=mine, model=data.get("model"), cost=cost / len(todo)))

    async def vision(self, jpeg: bytes) -> Vision:
        image = base64.b64encode(jpeg).decode()
        body = {
            "model": self._s.vision_model,
            "messages": [
                {"role": "system", "content": VISION_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Triage this page."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}},
                    ],
                },
            ],
            "response_format": {"type": "json_schema", "json_schema": VISION_SCHEMA},
            "provider": {"require_parameters": True},
            "usage": {"include": True},
        }

        def parse(data: dict) -> VisionFacts:
            return VisionFacts.model_validate_json(data["choices"][0]["message"]["content"])

        facts, _, cost = await self._call(
            "vision", "/v1/chat/completions", body, self._s.vision_timeout_s, self._s.vision_rpm, parse
        )
        return Vision(facts=facts, cost=cost)

    async def _call(
        self,
        kind: str,
        path: str,
        body: dict,
        timeout: float,
        rpm: int,
        parse: Callable[[dict], T],
        cache: bool = True,
    ) -> tuple[T, dict, float]:
        """POST with cache, shared rate limit, retries and a deadline.

        Only responses that `parse` accepts are cached; unusable output (truncated JSON, missing answers) is retried
        a few times before the request counts as rejected. Returns (parsed value, raw response, cost spent).
        """
        key = cache_key(kind, _digest(path, body)) if cache else None
        if key and (cached := await self._store.get_json(key)) is not None:
            with contextlib.suppress(*_UNUSABLE):  # an unusable cached answer is fetched again
                return parse(cached), cached, 0.0
        deadline = time.monotonic() + 4 * timeout
        attempt = unusable = 0
        spent = 0.0
        while True:
            await self._limiter.acquire(kind, rpm)
            try:
                r = await self._client.post(
                    self._s.openrouter_base_url + path, json=body, headers=self._headers, timeout=timeout
                )
            except httpx.TransportError as e:
                retry_after, error = None, repr(e)
            else:
                if r.status_code == 200:
                    try:
                        data = r.json()
                    except ValueError:
                        data = {}
                    if data.get("error"):
                        raise ProviderRejected(str(data["error"])[:300])
                    spent += float((data.get("usage") or {}).get("cost") or 0.0)
                    try:
                        value = parse(data)
                    except _UNUSABLE as e:
                        unusable += 1
                        if unusable >= MAX_UNUSABLE:
                            raise ProviderRejected(f"{kind} returned unusable output {unusable} times: {e}") from e
                        continue
                    if key:
                        await self._store.put_json(key, data)
                    return value, data, spent
                if r.status_code in (401, 402, 403):  # credentials or billing: a system fault, not a page verdict
                    raise ProviderUnavailable(f"{kind} {r.status_code}: {r.text[:300]}")
                if r.status_code != 429 and r.status_code < 500:
                    raise ProviderRejected(f"{kind} {r.status_code}: {r.text[:300]}")
                retry_after, error = r.headers.get("retry-after"), f"{kind} {r.status_code}"
            attempt += 1
            wait = float(retry_after) if retry_after and retry_after.isdigit() else min(30.0, 2**attempt)
            wait *= 0.5 + random.random()
            if time.monotonic() + wait > deadline:
                raise ProviderUnavailable(error)
            await asyncio.sleep(wait)
