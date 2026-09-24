import asyncio
import json
from pathlib import Path

import httpx
import pytest

from jesteruct.config import Settings
from jesteruct.limiter import LocalLimiter
from jesteruct.providers import OpenRouter, ProviderRejected, ProviderUnavailable
from jesteruct.store import Store

QUESTIONS = {"text_layer_trustworthy": {"type": "noul", "instructions": "..."}}


def provider(tmp_path: Path, handler, **settings_kw) -> tuple[OpenRouter, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    settings = Settings(openrouter_api_key="k", jev_timeout_s=0.5, **settings_kw)
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


def test_unusable_output_is_retried_and_never_cached(tmp_path):
    good = {"answers": {"text_layer_trustworthy": {"noul": 0.9}}}
    replies = iter([{"answers": {}}, {"choices": None}, good])
    p, seen = provider(tmp_path, lambda r: httpx.Response(200, json=next(replies)))
    assert asyncio.run(p.decide({"page_evidence": "x"}, QUESTIONS)).answers == {"text_layer_trustworthy": 0.9}
    assert len(seen) == 3
    assert asyncio.run(p.decide({"page_evidence": "x"}, QUESTIONS)).cost == 0.0  # the good answer was cached


def test_transient_errors_give_up_after_the_deadline(tmp_path):
    p, seen = provider(tmp_path, lambda r: httpx.Response(503))
    with pytest.raises(ProviderUnavailable):
        asyncio.run(p.decide({"page_evidence": "x"}, QUESTIONS))
    assert len(seen) >= 1


def test_batched_decisions_share_one_request_and_cache_per_page(tmp_path):
    def answer(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert set(body["state"]) == {"p0_page_evidence", "p1_page_evidence"}
        assert body["questions"]["p1_text_layer_trustworthy"]["instructions"].startswith("About page p1 only")
        answers = {k: {"noul": 0.1 if k.startswith("p0") else 0.9} for k in body["questions"]}
        return httpx.Response(200, json={"answers": answers})

    p, seen = provider(tmp_path, answer, jev_batch_size=2)

    async def both():
        return await asyncio.gather(
            p.decide({"page_evidence": "a"}, QUESTIONS), p.decide({"page_evidence": "b"}, QUESTIONS)
        )

    first, second = asyncio.run(both())
    assert first.answers == {"text_layer_trustworthy": 0.1}
    assert second.answers == {"text_layer_trustworthy": 0.9}
    assert len(seen) == 1
    again = asyncio.run(both())  # each page's answers were cached on their own
    assert [d.answers for d in again] == [first.answers, second.answers]
    assert len(seen) == 1


def test_a_lone_batched_page_is_asked_unprefixed(tmp_path):
    def answer(request: httpx.Request) -> httpx.Response:
        assert set(json.loads(request.content)["state"]) == {"page_evidence"}
        return httpx.Response(200, json={"answers": {"text_layer_trustworthy": {"noul": 0.8}}})

    p, seen = provider(tmp_path, answer, jev_batch_size=4, jev_batch_wait_ms=1)
    first = asyncio.run(p.decide({"page_evidence": "a"}, QUESTIONS))
    again = asyncio.run(p.decide({"page_evidence": "a"}, QUESTIONS))
    assert first.answers == again.answers == {"text_layer_trustworthy": 0.8}
    assert len(seen) == 1 and again.cost == 0.0
