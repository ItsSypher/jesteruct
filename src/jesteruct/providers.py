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
import time
from collections.abc import Callable
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

handwriting:
- none: no handwriting at all.
- annotations_only: printed page with handwritten notes, marks or signatures.
- fields_filled_by_hand: printed form whose fields are filled in by hand.
- mostly_handwritten: the main content is handwritten.

content - true if the page contains at least one: table (rows and columns of cells), math (equations or mathematical notation), form (labelled fields, boxes or checkboxes to fill), code (source code or configuration listing), chart (plot, graph or diagram of data), photo (photographic picture).

script - the main writing system of the text.

Use "unsure" only when the image genuinely does not let you decide."""  # noqa: E501

_FLAGS = ["table", "math", "form", "code", "chart", "photo"]
VISION_SCHEMA = {
    "name": "page_triage",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["capture", "legibility", "handwriting", "content", "script"],
        "properties": {
            "capture": {
                "type": "string",
                "enum": ["digital_render", "flatbed_scan", "fax", "camera_photo", "screenshot", "unsure"],
            },
            "legibility": {"type": "string", "enum": ["clean", "mild_issues", "hard_to_read", "illegible", "unsure"]},
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
MAX_UNUSABLE = 3  # attempts with malformed output before a request counts as rejected
_UNUSABLE = (KeyError, IndexError, TypeError, ValueError)


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
        self._headers = {"Authorization": f"Bearer {settings.openrouter_api_key.get_secret_value()}"}

    async def decide(self, state: dict[str, str], questions: dict) -> Decision:
        def parse(data: dict) -> dict[str, float]:
            answers = {}
            for key, spec in questions.items():
                a = data["answers"][key]
                answers[key] = float(a["noul"] if spec["type"] == "noul" else a["score"])
            return answers

        body = {"model": self._s.jev_model, "state": state, "questions": questions}
        answers, data, cost = await self._call(
            "jev", "/alpha/decisions", body, self._s.jev_timeout_s, self._s.jev_rpm, parse
        )
        return Decision(answers=answers, model=data.get("model"), cost=cost)

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
        self, kind: str, path: str, body: dict, timeout: float, rpm: int, parse: Callable[[dict], T]
    ) -> tuple[T, dict, float]:
        """POST with cache, shared rate limit, retries and a deadline.

        Only responses that `parse` accepts are cached; unusable output (truncated JSON, missing answers) is retried
        a few times before the request counts as rejected. Returns (parsed value, raw response, cost spent).
        """
        digest = hashlib.sha256(json.dumps({"path": path, "body": body}, sort_keys=True).encode()).hexdigest()
        key = cache_key(kind, digest)
        if (cached := await self._store.get_json(key)) is not None:
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
