"""PDF structure: the embedded text layer, image coverage, hidden OCR text, producer, fonts and a column estimate.

The column estimate here is the fallback for when the layout model (`layout.py`) finds no text regions.

pdfium is not thread-safe; these functions run inside the probe process pool, one call at a time per process.
"""

import ctypes
import math
import re
from functools import lru_cache

import numpy as np
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from ..models import PdfFacts

_GRID = 64  # image coverage is measured on a 64 x 64 grid of the page, so overlapping image layers count once
_HIDDEN_MODES = (3, 7)  # invisible and clip-only text: how OCR tools lay a text layer over a scan
_MATH_FONT = re.compile(r"CMMI|CMSY|CMEX|Math|STIX|MSBM")
_MONO_FONT = re.compile(r"Courier|Mono|Consol|Menlo|CMTT", re.I)


@lru_cache(maxsize=8)
def _pdfium(path: str) -> pdfium.PdfDocument:
    return pdfium.PdfDocument(path)


def page(path: str, index: int) -> pdfium.PdfPage:
    return _pdfium(path)[index]


def _page_bounds(obj: pdfium.PdfObject) -> tuple[float, float, float, float]:
    """An object's bounds in page space: pdfium gives them in the space of the Form XObject that holds the object."""
    left, bottom, right, top = obj.get_bounds()
    corners = [(left, bottom), (left, top), (right, bottom), (right, top)]
    form = obj.container
    while form is not None:
        matrix = form.get_matrix()
        corners = [matrix.on_point(x, y) for x, y in corners]
        form = form.container
    xs, ys = zip(*corners, strict=True)
    return min(xs), min(ys), max(xs), max(ys)


def _cells(low: float, high: float, size: float) -> slice:
    return slice(max(0, math.floor(low / size * _GRID)), min(_GRID, math.ceil(high / size * _GRID)))


def _font_name(font: pdfium_c.FPDF_FONT) -> str:
    n = pdfium_c.FPDFFont_GetBaseFontName(font, None, 0)
    buffer = ctypes.create_string_buffer(n)
    pdfium_c.FPDFFont_GetBaseFontName(font, buffer, n)
    return buffer.value.decode("utf-8", "replace")


def _objects(pg: pdfium.PdfPage) -> tuple[float, bool, set[str]]:
    """One pass over the page's objects, through Form XObjects at any depth.

    Returns the share of the page under images, whether its text is hidden, and the fonts of its text. Text is hidden
    when it is drawn invisibly (render mode 3 or 7) or before images that then cover the page: the two ways OCR tools
    put a text layer under a scan.
    """
    w, h = pg.get_size()
    under_images = np.zeros((_GRID, _GRID), bool)
    over_text = np.zeros((_GRID, _GRID), bool)  # under images drawn after the first text
    invisible = text_seen = False
    fonts: dict[int, str] = {}  # by font handle: a page's text objects share a few fonts
    for obj in pg.get_objects():
        if obj.type == pdfium_c.FPDF_PAGEOBJ_TEXT:
            text_seen = True
            invisible |= pdfium_c.FPDFTextObj_GetTextRenderMode(obj.raw) in _HIDDEN_MODES
            font = pdfium_c.FPDFTextObj_GetFont(obj.raw)
            if font and (handle := ctypes.cast(font, ctypes.c_void_p).value) not in fonts:
                fonts[handle] = _font_name(font)
        elif obj.type == pdfium_c.FPDF_PAGEOBJ_IMAGE:
            left, bottom, right, top = _page_bounds(obj)
            cells = (_cells(bottom, top, h), _cells(left, right, w))
            under_images[cells] = True
            if text_seen:
                over_text[cells] = True
    return float(under_images.mean()), invisible or float(over_text.mean()) >= 0.9, set(fonts.values())


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


def structure(path: str, index: int) -> tuple[PdfFacts, str]:
    """Facts about one PDF page and its embedded text."""
    pg = page(path, index)
    textpage = pg.get_textpage()
    text = textpage.get_text_range()
    coverage, hidden, fonts = _objects(pg)
    facts = PdfFacts(
        image_coverage=coverage,
        invisible_text=hidden,
        producer=_pdfium(path).get_metadata_dict().get("Producer", ""),
        math_font=any(_MATH_FONT.search(f) for f in fonts),
        mono_font=any(_MONO_FONT.search(f) for f in fonts),
        columns=_columns(textpage, pg.get_size()[0]),
    )
    return facts, text
