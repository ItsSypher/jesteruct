"""Evidence in words: Jev reasons well over descriptions and poorly over raw numbers.

The bins and phrases are frozen at EVIDENCE_VERSION. Those of e1 were measured in bench/jev_lanes; e2 adds the layout
sentence and the agreement of a PDF text layer with fresh OCR (issue #4); e3 adds mathematical symbols in the text
layer and the vision check's capture defects, and counts formula blocks rather than formulas, which the layout model
finds only when they are displayed (evalset/fresh). e4 (issue #9) drops OCR text and confidence, which outvoted the
vision check on handwriting; words legibility plainly and leaves out soft defects behind text the vision check reads as
clean; finds OCR layers at any form depth and under a covering image; and says when a page has no mathematical fonts
or symbols. Change them only together with a version bump and an eval run; the version is part of every route key.
"""

from .models import ImageQuality, LayoutFacts, PageEvidence, TextStats, VisionFacts
from .probes.language import NAMES

EVIDENCE_VERSION = "e4"
MATH_SHARE = 0.008  # math symbols per character: born-digital L1 pages stay below 0.0052, inline-math pages reach 0.009
TEXT_SAMPLE_CHARS = 1200
PREVIOUS_SAMPLE_CHARS = 600

_SCRIPT_NAMES = {
    "latin": "Latin letters",
    "cjk": "Chinese, Japanese or Korean characters",
    "arabic": "Arabic letters",
    "cyrillic": "Cyrillic letters",
    "other": "letters of another script",
}
_LEGIBILITY = {
    "clean": "every character is easy to read",
    "mild_issues": "some characters are harder to read",
    "hard_to_read": "much of the text is hard to read",
    "illegible": "the text is illegible",
    "unsure": "unclear",
}
_CAPTURE = {
    "digital_render": "a digital render, not a photo, scan or fax",
    "flatbed_scan": "a flatbed scan, not a camera photo or fax",
    "fax": "a fax",
    "camera_photo": "a camera photo of a physical page",
    "screenshot": "a screenshot, not a photo, scan or fax",
    "unsure": "unclear",
}
_HANDWRITING = {
    "none": "no handwriting",
    "annotations_only": "a printed page with only handwritten notes, marks or signatures",
    "fields_filled_by_hand": "a printed form whose fields are filled in by hand",
    "mostly_handwritten": "mostly handwritten",
    "unsure": "unclear",
}
_SOFT_DEFECTS = ("photocopy", "bleed_through", "heavy_speckle", "faded_text")
_SCANNER_PRODUCERS = ("Tesseract", "ABBYY", "img2pdf")
_LAYOUT_NOUNS = {"table": "table", "formula": "formula block", "figure": "figure"}
_DEFECTS = {
    "photocopy": "photocopy artefacts",
    "bleed_through": "bleed-through from the reverse side",
    "curved_page": "curved or warped paper",
    "heavy_speckle": "heavy speckle",
    "faded_text": "faded or broken characters",
}


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


def _reads(st: TextStats) -> str:
    """Whether the text reads as language, in any language (probes.language)."""
    if st.unreadable:
        reason = st.unreadable.removeprefix("does not read as text in any language")
        return "does not read as text in any language" + (f": {reason}" if reason else "")
    if st.readability is None:
        return "mostly numbers and symbols"
    if st.readability >= 0.5:
        return f"reads as {NAMES[st.language]} text" if st.language else "reads as text in several languages"
    name = NAMES[st.language] if st.language else "text"
    return f"partly reads as {name}: names, numbers, table cells or fragments"


def describe_text(st: TextStats, what: str) -> str:
    if st.chars == 0:
        return f"{what}: none."
    amount = (
        "only a few words" if st.chars < 100 else "a short amount of text" if st.chars < 500 else "a full page of text"
    )
    s = [amount, _reads(st)]
    if st.cid_share > 0.05:
        s.append("contains encoding codes like (cid:NN)")
    if st.odd_char_share > 0.05:
        s.append("many unusual or private-use symbols")
    if st.short_token_share > 0.35 and "one-letter" not in st.unreadable:
        s.append("many one-letter fragments")
    if st.math_share >= MATH_SHARE:
        s.append("frequent mathematical symbols or operators")
    if st.script:
        s.append(f"mostly {_SCRIPT_NAMES[max(st.script, key=st.script.get)]}")
    return f"{what}: " + ", ".join(s) + "."


def describe_structure(ev: PageEvidence) -> str:
    if ev.pdf is None:
        return "Input: an image file (JPEG) with no embedded text."
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
        s.append("its text layer is hidden behind or under the page image, typical of an earlier OCR pass")
    if any(p in f.producer for p in _SCANNER_PRODUCERS):
        s.append(f"made by scanning or OCR software ({f.producer.split()[0]})")
    if f.math_font:
        s.append("uses mathematical fonts")
    elif ev.text_stats.chars and ev.text_stats.math_share < MATH_SHARE:
        s.append("no mathematical fonts or symbols")
    if f.mono_font:
        s.append("uses monospaced fonts")
    if ev.layout is None or ev.layout.columns is None:  # otherwise the layout sentence states the columns
        s.extend(_columns(f.columns))
    return ", ".join(s) + "."


def _columns(columns: int | None) -> list[str]:
    if columns == 2:
        return ["text is laid out in two or more columns"]
    if columns == 1:
        return ["text is in a single column"]
    return []


def _count(n: int, noun: str) -> str:
    """A region count in coarse words: no, 1 to 4, or many."""
    if n == 0:
        return f"no {noun}s"
    if n == 1:
        return f"1 {noun}"
    return f"{n if n < 5 else 'many'} {noun}s"


def describe_layout(layout: LayoutFacts | None) -> str | None:
    if layout is None:
        return None
    s = [_count(layout.counts.get(k, 0), noun) for k, noun in _LAYOUT_NOUNS.items()]
    if layout.area.get("figure", 0.0) >= 0.6:  # the layout model sees most scans and photos as one big figure
        s[-1] += " covering most of the page"
    return "Layout: " + ", ".join(s + _columns(layout.columns)) + "."


def describe_agreement(ev: PageEvidence) -> str | None:
    """How well the embedded text layer matches a fresh OCR pass: a layer over handwriting rarely does."""
    a = ev.ocr_agreement
    if a is None:
        return None
    if a >= 0.5:
        return "The embedded text layer and a fresh OCR pass mostly agree."
    if a >= 0.2:
        return "The embedded text layer and a fresh OCR pass partly agree."
    return (
        "The embedded text layer and a fresh OCR pass mostly disagree, "
        "so the layer is probably not a faithful copy of the page."
    )


def describe_vision(v: VisionFacts | None) -> str:
    if v is None:
        return "Vision check: unavailable."
    flags = [k for k in ("table", "math", "form", "code", "chart", "photo") if v.content.get(k)]
    # When the vision check reads the text as clean, a soft defect it also flags is faint show-through or copy grain
    # behind crisp text, which the labelling rubric counts as clean; a curved page still distorts the lines.
    soft = v.legibility == "clean"
    defects = [_DEFECTS[k] for k in _DEFECTS if v.defects.get(k) and not (soft and k in _SOFT_DEFECTS)]
    return (
        f"Vision check of the page image: capture looks like {_CAPTURE.get(v.capture, v.capture)}; "
        f"legibility: {_LEGIBILITY.get(v.legibility, v.legibility)}; "
        f"defects that make characters harder to read: {', '.join(defects) or 'none'}; "
        f"handwriting: {_HANDWRITING.get(v.handwriting, v.handwriting)}; "
        f"contains {', '.join(flags) or 'plain text only'}; main script {v.script}."
    )


def build_state(ev: PageEvidence, vision: VisionFacts | None, previous_text: str | None = None) -> dict[str, str]:
    """The `state` Jev decides over. The vision check is included only when it was run.

    OCR text is never shown: on image pages a fluent read of handwriting outvoted the vision check, and OCR's only job
    left is the agreement check of an untrusted PDF layer.
    """
    parts = [describe_structure(ev), describe_image(ev.image)]
    if layout := describe_layout(ev.layout):
        parts.append(layout)
    if ev.pdf is not None:
        parts.append(describe_text(ev.text_stats, "Embedded text layer"))
    if agreement := describe_agreement(ev):
        parts.append(agreement)
    state = {"page_evidence": " ".join(parts)}
    if ev.pdf is not None:
        state["embedded_text_sample"] = ev.text[:TEXT_SAMPLE_CHARS]
    if vision is not None:
        state["vision_check"] = describe_vision(vision)
    if previous_text:
        state["previous_page_text_sample"] = previous_text[-PREVIOUS_SAMPLE_CHARS:]
    return state
