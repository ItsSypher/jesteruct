"""Evidence in words: Jev reasons well over descriptions and poorly over raw numbers.

The bins and phrases are frozen at EVIDENCE_VERSION (measured in bench/jev_lanes). Change them only together with a
version bump and an eval run; the version is part of every route key.
"""

from .models import ImageQuality, PageEvidence, TextStats, VisionFacts

EVIDENCE_VERSION = "e1"
TEXT_SAMPLE_CHARS = 1200
PREVIOUS_SAMPLE_CHARS = 600

_SCRIPT_NAMES = {
    "latin": "Latin letters",
    "cjk": "Chinese, Japanese or Korean characters",
    "arabic": "Arabic letters",
    "cyrillic": "Cyrillic letters",
    "other": "letters of another script",
}
_SCANNER_PRODUCERS = ("Tesseract", "ABBYY", "img2pdf")


def describe_image(q: ImageQuality) -> str:
    s = ["very soft or blurry" if q.sharpness < 300 else "somewhat soft" if q.sharpness < 1500 else "sharp"]
    s.append("low contrast" if q.contrast < 25 else "normal contrast")
    if q.border_mean < 200:
        s.append("dark or coloured surroundings at the page edges, as when a page is photographed on a surface")
    elif q.border_std > 20:
        s.append("uneven or speckled page edges")
    else:
        s.append("clean white page edges")
    s.append("grey or tinted paper background" if q.background_mean < 235 else "white paper background")
    s.append("colourful" if q.colour > 15 else "some colour" if q.colour > 3 else "greyscale")
    if q.noise >= 2:
        s.append("visible pixel noise")
    if q.bilevel_share > 0.95 and q.contrast < 30:
        s.append("almost only pure black and pure white pixels")
    return "Page image: " + ", ".join(s) + "."


def describe_text(st: TextStats, what: str) -> str:
    if st.chars == 0:
        return f"{what}: none."
    amount = (
        "only a few words" if st.chars < 100 else "a short amount of text" if st.chars < 500 else "a full page of text"
    )
    cw = st.common_word_share
    if cw >= 0.3:
        read = "reads as normal English prose"
    elif cw >= 0.1:
        read = "partly readable: names, numbers, fragments, or a non-English language"
    else:
        read = "few recognisable English words"
    s = [amount, read]
    if st.cid_share > 0.05:
        s.append("contains encoding codes like (cid:NN)")
    if st.odd_char_share > 0.05:
        s.append("many unusual or private-use symbols")
    if st.short_token_share > 0.35:
        s.append("many one-letter fragments")
    if st.script:
        s.append(f"mostly {_SCRIPT_NAMES[max(st.script, key=st.script.get)]}")
    return f"{what}: " + ", ".join(s) + "."


def describe_structure(ev: PageEvidence) -> str:
    if ev.pdf is None:
        return (
            "Input: an image file (JPEG) with no embedded text; "
            "any text below comes from a quick English-model OCR pass."
        )
    f = ev.pdf
    s = ["Input: a one-page PDF"]
    cov = f.image_coverage
    s.append(
        "the page is one full-page image"
        if cov > 0.9
        else "images cover a large part of the page"
        if cov > 0.3
        else "little or no image content"
    )
    if f.invisible_text and cov > 0.9:
        s.append("its text layer is invisible text laid over the image, typical of an earlier OCR pass")
    if any(p in f.producer for p in _SCANNER_PRODUCERS):
        s.append(f"made by scanning or OCR software ({f.producer.split()[0]})")
    if f.math_font:
        s.append("uses mathematical fonts")
    if f.mono_font:
        s.append("uses monospaced fonts")
    if f.columns == 2:
        s.append("text is laid out in two or more columns")
    elif f.columns == 1:
        s.append("text is in a single column")
    return ", ".join(s) + "."


def describe_ocr(ev: PageEvidence) -> str | None:
    if ev.ocr is None:
        return None
    c = ev.ocr.confidence
    level = "high" if c >= 0.9 else "medium" if c >= 0.7 else "low"
    return f"Quick OCR (English model) found {ev.ocr.lines} text lines with {level} average confidence."


def describe_vision(v: VisionFacts | None) -> str:
    if v is None:
        return "Vision check: unavailable."
    flags = [k for k in ("table", "math", "form", "code", "chart", "photo") if v.content.get(k)]
    return (
        f"Vision check of the page image: capture looks like {v.capture}; legibility {v.legibility}; "
        f"handwriting {v.handwriting}; contains {', '.join(flags) or 'plain text only'}; main script {v.script}."
    )


def build_state(ev: PageEvidence, vision: VisionFacts | None, previous_text: str | None = None) -> dict[str, str]:
    """The `state` Jev decides over. The vision check is included only when it was run."""
    parts = [describe_structure(ev), describe_image(ev.image)]
    is_image = ev.pdf is None
    if not is_image:
        parts.append(describe_text(ev.text_stats, "Embedded text layer"))
    if ocr := describe_ocr(ev):
        parts.append(ocr)
    if is_image:
        parts.append(describe_text(ev.text_stats, "OCR text"))
    state = {"page_evidence": " ".join(parts)}
    if not is_image:
        state["embedded_text_sample"] = ev.text[:TEXT_SAMPLE_CHARS]
    if is_image:
        state["ocr_text_sample"] = ev.text[:TEXT_SAMPLE_CHARS]
    elif ev.ocr is not None:
        state["ocr_text_sample"] = ev.ocr.text[:TEXT_SAMPLE_CHARS]
    if vision is not None:
        state["vision_check"] = describe_vision(vision)
    if previous_text:
        state["previous_page_text_sample"] = previous_text[-PREVIOUS_SAMPLE_CHARS:]
    return state
