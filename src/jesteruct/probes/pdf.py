"""PDF structure: the embedded text layer, image coverage, invisible OCR text, producer, fonts and a column estimate.

The column estimate here is the fallback for when the layout model (`layout.py`) fails.

pdfium is not thread-safe; these functions run inside the probe process pool, one call at a time per process.
"""

import re
from functools import lru_cache

import numpy as np
import pikepdf
import pypdfium2 as pdfium

from ..models import PdfFacts

_INVISIBLE_TEXT = re.compile(rb"(^|\s)3\s+Tr\b")  # text render mode 3: typical of an OCR layer under a scan
_MATH_FONT = re.compile(r"CMMI|CMSY|CMEX|Math|STIX|MSBM")
_MONO_FONT = re.compile(r"Courier|Mono|Consol|Menlo|CMTT", re.I)


@lru_cache(maxsize=8)
def _pdfium(path: str) -> pdfium.PdfDocument:
    return pdfium.PdfDocument(path)


@lru_cache(maxsize=8)
def _pikepdf(path: str) -> pikepdf.Pdf:
    return pikepdf.open(path)


def page(path: str, index: int) -> pdfium.PdfPage:
    return _pdfium(path)[index]


def _image_coverage(pg: pdfium.PdfPage) -> float:
    w, h = pg.get_size()
    area = 0.0
    for obj in pg.get_objects(max_depth=2):
        if obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE:
            left, bottom, right, top = obj.get_bounds()
            area += max(0.0, right - left) * max(0.0, top - bottom)
    return min(1.0, area / (w * h))


def _columns(textpage: pdfium.PdfTextPage, width: float) -> int | None:
    """Projection profile of text boxes: two columns when a clear gutter sits between two dense sides."""
    rects = [textpage.get_rect(i) for i in range(textpage.count_rects())]
    if len(rects) < 10:
        return None
    occupancy = np.zeros(100)
    for left, bottom, right, top in rects:
        a, z = int(max(0.0, left / width) * 100), int(min(1.0, right / width) * 100)
        occupancy[a : max(a + 1, z)] += top - bottom
    if occupancy.max() == 0:
        return None
    occupancy /= occupancy.max()
    gutter = int(np.argmin(occupancy[30:71])) + 30
    lower = min(float(occupancy[10:gutter].mean()), float(occupancy[gutter + 1 : 90].mean()))
    return 2 if occupancy[gutter] < 0.3 * lower and lower > 0.3 else 1


def _content_and_fonts(path: str, index: int) -> tuple[bytes, list[str], str]:
    pdf = _pikepdf(path)
    pg = pdf.pages[index].obj
    contents = pg.get("/Contents")
    streams = contents if isinstance(contents, pikepdf.Array) else [contents] if contents is not None else []
    content = b"".join(s.read_bytes() for s in streams)
    fonts: list[str] = []
    resources = pg.get("/Resources")
    if resources is not None and "/Font" in resources:
        fonts = [str(f.get("/BaseFont", "")) for _, f in resources.Font.items()]
    producer = str(pdf.docinfo.get("/Producer", "")) if pdf.docinfo else ""
    return content, fonts, producer


def structure(path: str, index: int) -> tuple[PdfFacts, str]:
    """Facts about one PDF page and its embedded text."""
    pg = page(path, index)
    textpage = pg.get_textpage()
    text = textpage.get_text_range()
    content, fonts, producer = _content_and_fonts(path, index)
    facts = PdfFacts(
        image_coverage=_image_coverage(pg),
        invisible_text=bool(_INVISIBLE_TEXT.search(content)),
        producer=producer,
        math_font=any(_MATH_FONT.search(f) for f in fonts),
        mono_font=any(_MONO_FONT.search(f) for f in fonts),
        columns=_columns(textpage, pg.get_size()[0]),
    )
    return facts, text
