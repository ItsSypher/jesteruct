import pytest

from jesteruct import policy
from jesteruct.models import ImageQuality, PageEvidence, PageRef, PdfFacts, TextStats

IMAGE = ImageQuality(
    sharpness=3000,
    contrast=40,
    noise=0,
    bilevel_share=0.9,
    background_mean=255,
    border_mean=255,
    border_std=0,
    colour=0,
)


def answers(**kw: float) -> dict[str, float]:
    base = dict.fromkeys(policy.ROUTING_QUESTIONS, 0.02)
    return {**base, **kw}


def evidence(pdf: bool = True) -> PageEvidence:
    facts = PdfFacts(image_coverage=0.0, invisible_text=False, columns=1) if pdf else None
    kind = "pdf" if pdf else "image"
    return PageEvidence(ref=PageRef(doc_path="x", index=0, kind=kind), image=IMAGE, pdf=facts)


@pytest.mark.parametrize(
    ("given", "lane"),
    [
        ({"text_layer_trustworthy": 0.97}, "L1"),
        ({"text_layer_trustworthy": 0.97, "complex_layout": 0.9}, "L2"),
        ({"text_layer_trustworthy": 0.97, "has_math": 0.9}, "L2"),
        ({}, "L3"),
        ({"camera_or_fax": 0.9}, "L4"),
        ({"heavily_degraded": 0.8}, "L4"),
        ({"capture_defects": 0.7}, "L4"),
        ({"mostly_handwritten": 0.9, "text_layer_trustworthy": 0.97, "camera_or_fax": 0.9}, "L5"),
    ],
)
def test_rule_table(given, lane):
    route = policy.route_page(0, answers(**given), evidence(), None, review_threshold=0.5)
    assert route.candidate_lane == lane
    assert route.lane == lane


def test_low_path_probability_goes_to_review_and_keeps_candidate():
    route = policy.route_page(0, answers(text_layer_trustworthy=0.55, complex_layout=0.52), evidence(), None, 0.5)
    assert route.lane == "LH"
    assert route.candidate_lane == "L2"
    assert route.path_p == pytest.approx(0.98 * 0.55 * 0.52, abs=1e-3)


def test_modifiers():
    a = answers(text_layer_trustworthy=0.9, has_table=0.8, has_handwriting=0.7)
    ev = evidence()
    ev.pdf.columns = 2
    ev.text_stats = TextStats(chars=900, script={"arabic": 0.9, "latin": 0.1})
    assert policy.route_page(0, a, ev, None, 0.5).modifiers == [
        "handwriting",
        "multi_column",
        "rtl",
        "script_arabic",
        "table",
    ]


def test_trust_rule_rejects_ocr_layers_and_garbage():
    ev = evidence()
    ev.text_stats = TextStats(chars=3000, common_word_share=0.4)
    assert policy.text_layer_trusted(ev)
    ev.pdf.invisible_text, ev.pdf.image_coverage = True, 1.0
    assert not policy.text_layer_trusted(ev)
    ev = evidence()
    ev.text_stats = TextStats(chars=3000, common_word_share=0.0, cid_share=0.4)
    assert not policy.text_layer_trusted(ev)
    assert not policy.text_layer_trusted(evidence(pdf=False))
