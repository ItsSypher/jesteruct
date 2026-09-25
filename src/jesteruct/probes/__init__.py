"""Cheap page measurements. These are the pool entry points; each call must be picklable and self-contained."""

import logging

import numpy as np

from ..models import LayoutFacts, PageEvidence, PageRef
from . import image, language, layout, ocr, pdf
from .text import agreement, text_stats

# The OCR agreement and the previous-page tail need the whole text of a page; the cap only bounds hostile files.
TEXT_SAMPLE = 50_000

log = logging.getLogger(__name__)


def probe_page(
    ref: PageRef, text_override: str | None = None, lid_model: str | None = None
) -> tuple[PageEvidence, bytes]:
    """Measure one page; returns the evidence and the 1024 px JPEG used for OCR and vision. With `lid_model`, the text
    layer's language and readability are measured too (the router always passes it)."""
    facts, text = None, ""
    if ref.kind == "pdf":
        facts, text = pdf.structure(ref.doc_path, ref.index)
        jpeg = image.render_pdf_page(pdf.page(ref.doc_path, ref.index))
    else:
        jpeg = image.image_page(ref.doc_path, ref.index)
    if text_override is not None:
        text = text_override
    bgr = image.decode(jpeg)
    regions = _layout(bgr)
    if facts is not None and regions is not None and regions.columns is not None:  # else the text-layer estimate stays
        facts = facts.model_copy(update={"columns": regions.columns})
    evidence = PageEvidence(
        ref=ref,
        image=image.quality(bgr),
        pdf=facts,
        layout=regions,
        text=text[:TEXT_SAMPLE],
        text_stats=text_stats(text, lid_model),
    )
    return evidence, jpeg


def _layout(bgr: np.ndarray) -> LayoutFacts | None:
    """The layout model's regions, or None when it fails; a PDF page then keeps the projection-profile columns."""
    try:
        return layout.detect(bgr)
    except Exception:
        log.warning("layout model failed", exc_info=True)
        return None


def read_text(evidence: PageEvidence, jpeg: bytes, backend: str) -> PageEvidence:
    """OCR a PDF page and compare the text with its embedded layer (policy.needs_ocr says when)."""
    result = ocr.read(jpeg, backend)
    return evidence.model_copy(update={"ocr": result, "ocr_agreement": agreement(evidence.text, result.text)})


__all__ = ["image", "language", "probe_page", "read_text", "text_stats"]
