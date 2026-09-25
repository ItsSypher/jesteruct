"""The e2 evidence: the layout sentence and the agreement of a PDF text layer with fresh OCR."""

from pathlib import Path

import pytest

from jesteruct.config import Settings
from jesteruct.evidence import build_state, describe_agreement, describe_layout
from jesteruct.models import ImageQuality, LayoutFacts, OcrResult, PageEvidence, PageRef, PdfFacts
from jesteruct.probes import language, layout, probe_page
from jesteruct.probes.text import agreement

FILES = Path(__file__).parents[1] / "evalset" / "files"
IMAGE = ImageQuality(**dict.fromkeys(ImageQuality.model_fields, 100.0))  # these tests do not look at image quality


def page(pdf_columns: int | None, regions: LayoutFacts | None, ocr_agreement: float | None = None) -> PageEvidence:
    return PageEvidence(
        ref=PageRef(doc_path="x.pdf", index=0, kind="pdf"),
        image=IMAGE,
        pdf=PdfFacts(image_coverage=0.0, invisible_text=False, columns=pdf_columns),
        layout=regions,
        ocr=OcrResult(text="", confidence=0.95, lines=3, backend="apple") if ocr_agreement is not None else None,
        ocr_agreement=ocr_agreement,
    )


def test_layout_is_described_in_coarse_words():
    paper = LayoutFacts(model="m", counts={"table": 1, "formula": 7, "figure": 2, "text": 9}, columns=2)
    assert describe_layout(paper) == (
        "Layout: 1 table, many formula blocks, 2 figures, text is laid out in two or more columns."
    )
    photo = LayoutFacts(model="m", counts={"figure": 1}, area={"figure": 0.97})
    assert describe_layout(photo) == "Layout: no tables, no formula blocks, 1 figure covering most of the page."
    assert describe_layout(None) is None


def test_columns_are_stated_once():
    both = build_state(page(2, LayoutFacts(model="m", counts={"text": 4}, columns=2)), None)["page_evidence"]
    assert both.count("two or more columns") == 1
    assert "Layout: no tables, no formula blocks, no figures, text is laid out in two or more columns." in both
    fallback = build_state(page(2, None), None)["page_evidence"]  # layout model failed: the structure sentence says it
    assert "Input: a one-page PDF, little or no image content, text is laid out in two or more columns." in fallback
    no_text = build_state(page(2, LayoutFacts(model="m", counts={"figure": 1})), None)["page_evidence"]
    assert no_text.count("two or more columns") == 1  # the model found no text regions: the text layer's estimate


@pytest.mark.parametrize(
    ("value", "phrase"),
    [(0.9, "mostly agree."), (0.5, "mostly agree."), (0.3, "partly agree."), (0.2, "partly agree."), (0.1, "disagree")],
)
def test_agreement_bins(value: float, phrase: str):
    sentence = describe_agreement(page(1, None, value))
    assert sentence.startswith("The embedded text layer and a fresh OCR pass ") and phrase in sentence
    assert sentence in build_state(page(1, None, value), None)["page_evidence"]


def test_agreement_compares_words_of_three_or_more_letters_in_any_script():
    assert agreement("The quick brown fox", "the QUICK brown fox, 42") == 1.0
    assert agreement("Tne qvick brwn fex", "The quick brown fox") == 0.0
    assert agreement("ab 12 !!", "The quick brown fox") is None  # no layer words to compare
    assert agreement("Быстрая бурая лиса", "быстрая бурая лиса") == 1.0
    assert agreement("人人生而自由", "人人生而自由") == 1.0  # character pairs where words have no spaces
    assert agreement("人人生而自由", "The quick brown fox") == 0.0
    assert describe_agreement(page(1, None)) is None


ENGLISH = (
    "All human beings are born free and equal in dignity and rights. They are endowed with reason and conscience\n"
    "and should act towards one another in a spirit of brotherhood. Everyone is entitled to all the rights and\n"
    "freedoms set forth in this Declaration, without distinction of any kind, such as race, colour or sex."
)
FRENCH = (
    "Tous les êtres humains naissent libres et égaux en dignité et en droits. Ils sont doués de raison et de\n"
    "conscience et doivent agir les uns envers les autres dans un esprit de fraternité. Chacun peut se prévaloir\n"
    "de tous les droits et de toutes les libertés proclamés dans la présente Déclaration, sans distinction aucune."
)


@pytest.mark.skipif(not Path(Settings().lid_model).expanduser().is_file(), reason="scripts/openlid.py builds it")
def test_text_reads_as_language_in_any_language_and_garbage_does_not():
    model = language.check(Settings().lid_model)
    assert language.identify(ENGLISH, model)[0::2] == ("eng", "")
    assert language.identify(FRENCH, model)[0::2] == ("fra", "")
    shifted = "".join(chr(ord(c) + 1) if c.isalpha() else c for c in ENGLISH)  # a font without its Unicode map
    assert language.identify(shifted, model)[2] == "does not read as text in any language"
    assert language.identify(ENGLISH.replace(" ", "\x03 "), model)[2] == "control or undefined characters"
    assert language.identify(" ".join(ENGLISH), model)[2] == "many one-letter fragments"


@pytest.mark.skipif(not FILES.exists(), reason="evalset files not present")
def test_layout_columns_on_the_issue_pages():
    """Slide bullets do not read as two columns; a paper does, and so does a newsletter whose columns are short."""
    newsletter = FILES.parent / "fresh/files/pdf_olm_cols_08c9eac4_page_1_pg1.pdf"  # present after build.py fetch
    pages = [(FILES / "pdf_olmx_02.pdf", 1), (FILES / "pdf_olmocr_multicol_01.pdf", 2)]
    for path, columns in pages + ([(newsletter, 2)] if newsletter.exists() else []):
        ev, jpeg = probe_page(PageRef(doc_path=str(path), index=0, kind="pdf"))
        assert ev.layout == layout.detect(jpeg)
        assert (ev.layout.columns, ev.pdf.columns) == (columns, columns), path.name
