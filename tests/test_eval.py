"""Lean tests for jesteruct.eval: metric arithmetic and output files, against a fake router (no network)."""

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType

import pytest

from jesteruct.config import Settings
from jesteruct.eval import run_eval
from jesteruct.models import Doc, Manifest, PageRoute, Versions, VisionFacts

_VERSIONS = Versions(
    router="t", evidence="t", policy="t", questions="t", jev_model="t", vision_model="t", ocr_backend="t"
)

# Case "a": routed and predicted correctly.
_ROUTE_A = PageRoute(
    index=0, lane="L3", candidate_lane="L3", path_p=0.9, answers={}, reasons=[], timings_ms={"probe": 10, "jev": 20}
)
# Case "b": below the review threshold, sent to LH; its candidate lane was still acceptable.
_ROUTE_B = PageRoute(
    index=0,
    lane="LH",
    candidate_lane="L1",
    path_p=0.3,
    answers={},
    reasons=["low confidence"],
    timings_ms={"probe": 5, "jev": 15},
)
# Case "c": routed to a weaker lane than any acceptable one (under-route), with a vision check.
_ROUTE_C = PageRoute(
    index=0,
    lane="L3",
    candidate_lane="L3",
    path_p=0.8,
    answers={},
    reasons=["clean image"],
    timings_ms={"probe": 8, "jev": 12, "vision": 50},
    vision=VisionFacts(capture="digital_render", legibility="clean", handwriting="none", content={}, script="latin"),
)
_CASES = {
    "a": (_ROUTE_A, ["L3"], "img", 0.001),
    "b": (_ROUTE_B, ["L1", "L2"], "pdf", 0.002),
    "c": (_ROUTE_C, ["L4"], "pdf", 0.01),
}


class FakeRouter:
    """Stands in for jesteruct.pipeline.Router: one page per file, keyed by the file's stem."""

    async def route_file(self, path: Path, name=None, text_overrides=None, reuse=True) -> list[Manifest]:
        route, _, _, cost = _CASES[path.stem]
        doc = Doc(
            sha256="0" * 64, name=path.name, path=str(path), kind="pdf", mime="application/pdf", size=1, page_count=1
        )
        return [Manifest(doc=doc, route_key="k", versions=_VERSIONS, pages=[route], segments=[], cost_usd=cost)]


@pytest.fixture
def fake_router(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def fake_open_router(settings, store, valkey=None):
        yield FakeRouter()

    try:
        import jesteruct.pipeline as pipeline_mod
    except ModuleNotFoundError:
        pipeline_mod = ModuleType("jesteruct.pipeline")
        sys.modules["jesteruct.pipeline"] = pipeline_mod
    monkeypatch.setattr(pipeline_mod, "open_router", fake_open_router, raising=False)


def _write_cases(path: Path) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for cid, (_, gt, group, _) in _CASES.items():
            fh.write(json.dumps({"id": cid, "file": f"{cid}.pdf", "page": 0, "gt": gt, "group": group}) + "\n")
            (path.parent / f"{cid}.pdf").write_bytes(b"")


def test_run_eval_metrics_and_outputs(tmp_path: Path, fake_router: None) -> None:
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(cases_path)
    out = tmp_path / "out"
    settings = Settings(store_url=f"file://{tmp_path / 'store'}")

    summary = asyncio.run(run_eval(cases_path, settings, out))

    overall = summary["overall"]
    assert overall["n"] == 3
    assert summary["n_errors"] == 0
    # a is right, b is sent to review, c is under-routed: accuracy = 1/3.
    assert overall["accuracy"] == pytest.approx(1 / 3, abs=1e-4)
    # b's candidate (L1) was acceptable, only c's candidate was wrong: candidate accuracy = 2/3.
    assert overall["candidate_accuracy"] == pytest.approx(2 / 3, abs=1e-4)
    # only c's candidate lane ranks below every acceptable lane.
    assert overall["under_route"] == pytest.approx(1 / 3, abs=1e-4)
    assert overall["over_route"] == 0.0
    # only b ends in LH.
    assert overall["review_rate"] == pytest.approx(1 / 3, abs=1e-4)
    assert overall["cost_usd"] == pytest.approx(0.013)

    results_path = out / "results.jsonl"
    report_path = out / "report.md"
    assert results_path.exists()
    assert report_path.exists()
    rows = [json.loads(line) for line in results_path.read_text().splitlines()]
    assert {r["id"] for r in rows} == {"a", "b", "c"}
    assert report_path.read_text().startswith("# Eval report")


def test_run_eval_limit(tmp_path: Path, fake_router: None) -> None:
    cases_path = tmp_path / "cases.jsonl"
    _write_cases(cases_path)
    settings = Settings(store_url=f"file://{tmp_path / 'store'}")

    summary = asyncio.run(run_eval(cases_path, settings, tmp_path / "out", limit=1))

    assert summary["overall"]["n"] == 1
