import asyncio
from pathlib import Path

import httpx
import pytest

from jesteruct.config import Settings
from jesteruct.limiter import LocalLimiter
from jesteruct.providers import OpenRouter, ProviderRejected, ProviderUnavailable
from jesteruct.store import Store

QUESTIONS = {"text_layer_trustworthy": {"type": "noul", "instructions": "..."}}


def provider(tmp_path: Path, handler) -> tuple[OpenRouter, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    settings = Settings(openrouter_api_key="k", jev_timeout_s=0.5)
    client = httpx.AsyncClient(transport=httpx.MockTransport(record))
    return OpenRouter(settings, Store(f"file://{tmp_path}"), LocalLimiter(), client), seen


def test_answers_are_parsed_and_cached(tmp_path):
    body = {
        "model": "typesafe/jev-1.13-x",
        "answers": {"text_layer_trustworthy": {"noul": 0.93}},
        "usage": {"cost": 2e-5},
    }
    p, seen = provider(tmp_path, lambda r: httpx.Response(200, json=body))
    first = asyncio.run(p.decide({"page_evidence": "x"}, QUESTIONS))
    again = asyncio.run(p.decide({"page_evidence": "x"}, QUESTIONS))
    assert first.answers == {"text_layer_trustworthy": 0.93} and first.cost == 2e-5
    assert again.answers == first.answers and again.cost == 0.0
    assert len(seen) == 1


@pytest.mark.parametrize(
    ("status", "error"), [(401, ProviderUnavailable), (402, ProviderUnavailable), (400, ProviderRejected)]
)
def test_status_classification(tmp_path, status, error):
    p, _ = provider(tmp_path, lambda r: httpx.Response(status, json={"error": {"message": "no"}}))
    with pytest.raises(error):
        asyncio.run(p.decide({"page_evidence": "x"}, QUESTIONS))


def test_transient_errors_give_up_after_the_deadline(tmp_path):
    p, seen = provider(tmp_path, lambda r: httpx.Response(503))
    with pytest.raises(ProviderUnavailable):
        asyncio.run(p.decide({"page_evidence": "x"}, QUESTIONS))
    assert len(seen) >= 1
