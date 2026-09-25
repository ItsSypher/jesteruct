"""Routing policy: the questions Jev answers and the rule table that turns answers into a lane.

Jev answers narrow yes/no questions better than one multi-option lane choice (0.92-0.94 vs 0.80 lane accuracy in
bench/jev_lanes/REPORT.md), so the lane is decided here, in code, from those answers. Modifier and continuation
questions ride along in the same request. Question wording is part of POLICY_VERSION: p4 (issue #9) sends a page to L2
on any code, table, form or math answer, and words the degradation questions after the labelling rubric.
"""

import hashlib
import json

from .calibrate import Calibration
from .models import Lane, PageEvidence, PageRoute, VisionFacts

POLICY_VERSION = "p4"

ROUTING_QUESTIONS = {
    "text_layer_trustworthy": {
        "type": "noul",
        "instructions": "The page has a real embedded text layer created with the document (not an OCR layer over an "
        "image, not garbled), whose text can be used directly without OCR.",
    },
    "mostly_handwritten": {
        "type": "noul",
        "instructions": "Most of the page content is handwritten. A printed form filled in by hand, or a printed page "
        "with handwritten notes, marks or signatures, is not.",
    },
    "camera_or_fax": {
        "type": "noul",
        "instructions": "The page image is a camera photo of a physical page or a fax. A flatbed scan, a screenshot "
        "or a digital render is neither.",
    },
    "heavily_degraded": {
        "type": "noul",
        "instructions": "The page image is degraded enough to plausibly hurt a standard OCR engine: blur or low "
        "resolution that makes characters soft or merged, heavy noise, fading, stains, low contrast, uneven lighting "
        "or shadows, or warping.",
    },
    "capture_defects": {
        "type": "noul",
        "instructions": "The page image has defects that make some characters harder to read: photocopy artefacts "
        "(blotchy, broken or dithered strokes), bleed-through from the reverse side, curved or warped paper, heavy "
        "speckle, or faded or broken characters. Light speckle, a paper tint, light banding, a faint watermark, faint "
        "show-through or light copy grain behind crisp text do not count.",
    },
    "complex_layout": {
        "type": "noul",
        "instructions": "The page has tables, equations, source code, or two or more text columns.",
    },
}
MODIFIER_QUESTIONS = {
    "has_table": {"type": "noul", "instructions": "The page contains at least one table."},
    "has_math": {"type": "noul", "instructions": "The page contains mathematical equations or notation."},
    "has_code": {"type": "noul", "instructions": "The page contains source code or a configuration listing."},
    "is_form": {"type": "noul", "instructions": "The page is a form with labelled fields or boxes to fill in."},
    "has_handwriting": {
        "type": "noul",
        "instructions": "The page contains any handwriting: notes, signatures, filled-in fields or handwritten text.",
    },
    "degradation": {
        "type": "score",
        "instructions": "How degraded is the page image for text recognition?",
        "criteria": [
            "Clean: flat, sharp, good contrast",
            "Mild: slight noise, tint or softness",
            "Heavy: photo distortion, fax or photocopy artefacts, bleed-through, strong noise or fading",
            "Severe: large parts hard to read",
        ],
    },
}
CONTINUATION_QUESTION = {
    "continues_previous": {
        "type": "noul",
        "instructions": "This page's text (`embedded_text_sample`) continues the same table, list "
        "or sentence that ends `previous_page_text_sample`.",
    }
}


def questions(with_previous: bool) -> dict:
    return {**ROUTING_QUESTIONS, **MODIFIER_QUESTIONS, **(CONTINUATION_QUESTION if with_previous else {})}


def questions_hash() -> str:
    blob = json.dumps(questions(True), sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def text_layer_trusted(ev: PageEvidence) -> bool:
    """Cheap rule: a PDF text layer that reads as language, in any language, and is not an OCR layer over a
    full-page image (issue #7).

    Pages that pass need no OCR and no vision check; the rest get the vision check.
    """
    if ev.pdf is None:
        return False
    st = ev.text_stats
    ocr_layer = ev.pdf.invisible_text and ev.pdf.image_coverage > 0.9
    return st.chars > 50 and not ocr_layer and not st.unreadable and st.cid_share < 0.05 and st.odd_char_share < 0.05


def needs_ocr(ev: PageEvidence) -> bool:
    """For a page without a trusted text layer: fresh OCR only checks a PDF's untrusted layer against the page, since an
    OCR layer over handwriting or a garbled encoding reads differently. Image files and PDF pages without text are
    judged from the vision check, which reads handwriting and defects better than an OCR engine's confidence does."""
    return ev.pdf is not None and ev.text_stats.chars > 0


def _lane(a: dict[str, float]) -> tuple[Lane, float, list[str]]:
    """The rule table. Handwriting wins, then text-layer trust, then image condition.

    A page is complex when Jev finds any structure that plain text extraction scrambles: `complex_layout`, or the
    narrower code, table, form and math answers. Jev often reads `complex_layout` as columns and displayed equations
    only, so a code listing, a borderless table, a form or inline notation needs its own answer to reach L2.
    """
    hw, tl = a.get("mostly_handwritten", 0.0), a.get("text_layer_trustworthy", 0.0)
    cx = max(a.get(k, 0.0) for k in ("complex_layout", "has_code", "has_table", "is_form", "has_math"))
    bad = max(a.get(k, 0.0) for k in ("camera_or_fax", "heavily_degraded", "capture_defects"))
    if hw >= 0.5:
        return "L5", hw, [f"mostly handwritten ({hw:.2f})"]
    if tl >= 0.5:
        if cx >= 0.5:
            return "L2", (1 - hw) * tl * cx, [f"trusted text layer ({tl:.2f})", f"complex layout ({cx:.2f})"]
        return "L1", (1 - hw) * tl * (1 - cx), [f"trusted text layer ({tl:.2f})", f"simple layout ({1 - cx:.2f})"]
    if bad >= 0.5:
        return (
            "L4",
            (1 - hw) * (1 - tl) * bad,
            [f"no trusted text ({1 - tl:.2f})", f"degraded or photo/fax ({bad:.2f})"],
        )
    return "L3", (1 - hw) * (1 - tl) * (1 - bad), [f"no trusted text ({1 - tl:.2f})", f"clean image ({1 - bad:.2f})"]


def _modifiers(lane: Lane, a: dict[str, float], ev: PageEvidence, vision: VisionFacts | None) -> list[str]:
    mods = [
        name
        for key, name in (("has_table", "table"), ("has_math", "math"), ("has_code", "code"), ("is_form", "form"))
        if a.get(key, 0.0) >= 0.5
    ]
    if lane != "L5" and a.get("has_handwriting", 0.0) >= 0.5:
        mods.append("handwriting")
    if ev.pdf is not None and ev.pdf.columns == 2:
        mods.append("multi_column")
    script = (
        vision.script
        if vision
        else (max(ev.text_stats.script, key=ev.text_stats.script.get) if ev.text_stats.script else "")
    )
    if script in ("cjk", "arabic", "hebrew", "cyrillic", "greek"):
        mods.append(f"script_{script}")
    if script in ("arabic", "hebrew"):
        mods.append("rtl")
    return sorted(set(mods))


def route_page(
    index: int,
    answers: dict[str, float],
    ev: PageEvidence,
    vision: VisionFacts | None,
    review_threshold: float,
    calibration: Calibration | None = None,
) -> PageRoute:
    """Lane from the rule table. With a calibration, review is decided on the calibrated probability that the lane
    is right (`calibrate.py`); without one, on the raw path probability."""
    lane, path_p, reasons = _lane(answers)
    final: Lane = lane
    confidence: float | None = None
    if calibration:
        confidence = calibration(lane, path_p)
        if confidence < calibration.threshold:
            final = "LH"
            reasons.append(f"low confidence (calibrated {confidence:.2f} < {calibration.threshold:.2f})")
    elif path_p < review_threshold:
        final = "LH"
        reasons.append(f"low confidence (path {path_p:.2f} < {review_threshold:.2f})")
    return PageRoute(
        index=index,
        lane=final,
        candidate_lane=lane,
        path_p=round(path_p, 4),
        confidence=None if confidence is None else round(confidence, 4),
        answers=answers,
        modifiers=_modifiers(lane, answers, ev, vision),
        degradation=answers.get("degradation"),
        continuation=answers.get("continues_previous"),
        vision=vision,
        reasons=reasons,
    )


def fixed_route(index: int, lane: Lane, reason: str) -> PageRoute:
    """Pages decided without Jev: native formats (L0), quarantine (LQ) and provider rejections (LH)."""
    return PageRoute(index=index, lane=lane, candidate_lane=lane, path_p=1.0, reasons=[reason])
