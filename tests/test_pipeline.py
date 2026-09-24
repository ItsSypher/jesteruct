"""End to end through the real intake, probes and process pool, with a fake provider standing in for the models."""

import asyncio
import json
import multiprocessing
import sys
from pathlib import Path

import pikepdf
import pytest
from pebble import ProcessPool
from PIL import Image

from jesteruct.config import Settings
from jesteruct.evidence import build_state
from jesteruct.models import Manifest, PageRef, VisionFacts
from jesteruct.pipeline import Router
from jesteruct.probes import probe_page
from jesteruct.providers import Decision, Vision
from jesteruct.store import Store, manifest_key

ROOT = Path(__file__).parents[1]
FILES = ROOT / "evalset" / "files"
BORN_DIGITAL = FILES / "pdf_olmx_08.pdf"
HANDWRITING = FILES / "img_gnhk_01.jpg"
pytestmark = pytest.mark.skipif(not BORN_DIGITAL.exists(), reason="evalset files not present")


class FakeProvider:
    """Jev trusts text layers that read as English; the vision check reports handwriting."""

    def __init__(self) -> None:
        self.vision_calls = 0

    async def decide(self, state: dict[str, str], questions: dict) -> Decision:
        answers = dict.fromkeys(questions, 0.02)
        if "embedded_text_sample" in state and "reads as normal English prose" in state["page_evidence"]:
            answers["text_layer_trustworthy"] = 0.97
        if "mostly_handwritten" in state.get("vision_check", ""):
            answers["mostly_handwritten"] = 0.95
        return Decision(answers=answers, model="fake-jev", cost=0.0001)

    async def vision(self, jpeg: bytes) -> Vision:
        self.vision_calls += 1
        facts = VisionFacts(
            capture="camera_photo",
            legibility="clean",
            handwriting="mostly_handwritten",
            content=dict.fromkeys(["table", "math", "form", "code", "chart", "photo"], False),
            script="latin",
        )
        return Vision(facts=facts, cost=0.001)


def mixed_pdf(tmp: Path) -> Path:
    """Two born-digital pages followed by one image-only page."""
    image_pdf = tmp / "image.pdf"
    Image.open(HANDWRITING).convert("RGB").save(image_pdf)
    out = pikepdf.new()
    with pikepdf.open(BORN_DIGITAL) as digital, pikepdf.open(image_pdf) as scanned:
        out.pages.extend([digital.pages[0], digital.pages[0], scanned.pages[0]])
        out.save(tmp / "mixed.pdf")
    return tmp / "mixed.pdf"


def test_route_mixed_document(tmp_path: Path):
    settings = Settings(store_url=f"file://{tmp_path / 'store'}", page_concurrency=4)
    store = Store.from_settings(settings)
    provider = FakeProvider()

    async def run() -> tuple[Manifest, Manifest]:
        pool = ProcessPool(max_workers=2, context=multiprocessing.get_context("spawn"))
        try:
            router = Router(settings, store, provider, pool)
            path = mixed_pdf(tmp_path)
            (first,) = await router.route_file(path)
            (again,) = await router.route_file(path)  # same bytes and route key: the stored manifest is reused
            return first, again
        finally:
            pool.close()
            pool.join()

    first, again = asyncio.run(run())
    assert [p.lane for p in first.pages] == ["L1", "L1", "L5"]
    assert [(s.start, s.end, s.lane) for s in first.segments] == [(0, 1, "L1"), (2, 2, "L5")]
    assert provider.vision_calls == 1  # only the page without a trusted text layer
    assert again.created_at == first.created_at
    assert asyncio.run(store.exists(manifest_key(first.doc.sha256, first.route_key)))
    assert all(asyncio.run(store.exists(p.thumb_key)) for p in first.pages)


def _sentences(evidence: str) -> list[str]:
    """The image-quality sentence depends on how the platform renders non-embedded fonts; the rest does not."""
    parts = [s.strip() for s in evidence.split(". ") if s.strip()]
    return parts if sys.platform == "darwin" else [s for s in parts if not s.startswith("Page image:")]


def _e1_part(evidence: str) -> list[str]:
    """Evidence e2 moved the column estimate into its new layout sentence; everything else is still e1."""
    for clause in (", text is laid out in two or more columns", ", text is in a single column"):
        evidence = evidence.replace(clause, "")
    return [s for s in _sentences(evidence) if not s.startswith("Layout:")]


def test_evidence_matches_the_benchmark():
    """Ported probes describe born-digital pages as the benchmark (recorded on macOS, evidence e1) did."""
    rows = [json.loads(line) for line in (ROOT / "bench/jev_lanes/states_v3.jsonl").read_text().split("\n") if line]
    golden = {row["id"]: row["state"]["page_evidence"] for row in rows}
    checked = 0
    for pdf in sorted(FILES.glob("pdf_*.pdf")):
        ev, _ = probe_page(PageRef(doc_path=str(pdf), index=0, kind="pdf"))
        if pdf.stem in golden and ev.pdf.image_coverage <= 0.9:  # born-digital pages: no OCR in their evidence
            assert _e1_part(build_state(ev, None)["page_evidence"]) == _e1_part(golden[pdf.stem]), pdf.stem
            checked += 1
    assert checked >= 15
