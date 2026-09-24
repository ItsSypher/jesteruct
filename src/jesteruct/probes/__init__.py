"""Cheap page measurements. These are the pool entry points; each call must be picklable and self-contained."""

from ..models import PageEvidence, PageRef
from . import image, ocr, pdf
from .text import text_stats

TEXT_SAMPLE = 4000


def probe_page(ref: PageRef, text_override: str | None = None) -> tuple[PageEvidence, bytes]:
    """Measure one page; returns the evidence and the 1024 px JPEG used for OCR and vision."""
    facts, text = None, ""
    if ref.kind == "pdf":
        facts, text = pdf.structure(ref.doc_path, ref.index)
        jpeg = image.render_pdf_page(pdf.page(ref.doc_path, ref.index))
    else:
        jpeg = image.image_page(ref.doc_path, ref.index)
    if text_override is not None:
        text = text_override
    evidence = PageEvidence(
        ref=ref,
        image=image.quality(image.decode(jpeg)),
        pdf=facts,
        text=text[:TEXT_SAMPLE],
        text_stats=text_stats(text),
    )
    return evidence, jpeg


def read_text(evidence: PageEvidence, jpeg: bytes, backend: str) -> PageEvidence:
    """Add a fresh OCR pass. On image pages the OCR text becomes the page text, as it is the only text there is."""
    result = ocr.read(jpeg, backend)
    if evidence.ref.kind == "image":
        return evidence.model_copy(
            update={"ocr": result, "text": result.text[:TEXT_SAMPLE], "text_stats": text_stats(result.text)}
        )
    return evidence.model_copy(update={"ocr": result, "ocr_stats": text_stats(result.text)})


__all__ = ["image", "probe_page", "read_text", "text_stats"]
