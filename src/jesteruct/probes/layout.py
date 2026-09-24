"""Page layout from a small detector: regions per label, and a column estimate from the text regions.

The detector is 360LayoutAnalysis's YOLOv8n "general6" model (text, title, figure, table, caption, equation), run on
ONNX Runtime through rapid-layout. Of the models tried it came closest to PP-DocLayoutV3 on columns and tables, on scans
as well as born-digital pages, at about 20 ms a page; V3 itself takes 600 ms.
The engine is created lazily, once per process.
"""

import fcntl
import logging
import tempfile
from collections.abc import Iterable
from functools import cache
from pathlib import Path
from typing import Literal

import numpy as np

from ..models import LayoutFacts
from .image import decode

MODEL = "yolov8n_layout_general6"
_NAMES = {"equation": "formula"}  # the other labels keep the model's names, lower-cased
_TEXT = "text"  # body text; titles are left out, because slide bullets can come out as titles
_COLUMN_WIDTH = 0.15  # share of the page width below which a text region is too narrow to be a column
# Share of the text's height over which text regions must sit side by side for two columns. Born-digital L1 pages in
# evalset/ and evalset/fresh have none at all; a letterhead's address beside its date stays far below this.
_SIDE_BY_SIDE = 0.2

Box = tuple[float, float, float, float]  # left, top, right, bottom as shares of the page size


@cache
def _engine():
    from rapid_layout import RapidLayout

    # The first use downloads the weights (images bake them in). Pool processes start together, so one downloads
    # while the others wait. rapid-layout also announces its set-up at INFO level, on handlers of its own.
    with open(Path(tempfile.gettempdir()) / "jesteruct-layout.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        logging.disable(logging.INFO)
        try:
            # One thread per engine: the probe pool already runs one process per core.
            return RapidLayout(model_type=MODEL, engine_cfg={"intra_op_num_threads": 1, "inter_op_num_threads": 1})
        finally:
            logging.disable(logging.NOTSET)


def detect(page: bytes | np.ndarray) -> LayoutFacts:
    """Regions on one page image: a JPEG, or one already decoded to BGR."""
    bgr = decode(page) if isinstance(page, bytes) else page
    h, w = bgr.shape[:2]
    result = _engine()(bgr)
    boxes = [] if result.boxes is None else np.asarray(result.boxes, dtype=float).tolist()
    labels = [] if result.class_names is None else [str(c).lower() for c in result.class_names]
    counts: dict[str, int] = {}
    area: dict[str, float] = {}
    text: list[Box] = []
    for (left, top, right, bottom), label in zip(boxes, labels, strict=True):
        name = _NAMES.get(label, label)
        counts[name] = counts.get(name, 0) + 1
        area[name] = area.get(name, 0.0) + (right - left) * (bottom - top) / (w * h)
        if name == _TEXT and right - left >= _COLUMN_WIDTH * w:
            text.append((left / w, top / h, right / w, bottom / h))
    return LayoutFacts(
        model=MODEL, counts=counts, area={k: round(min(1.0, v), 3) for k, v in area.items()}, columns=_columns(text)
    )


def _columns(text: list[Box]) -> Literal[1, 2] | None:
    """Two columns when text regions sit side by side, apart horizontally, over a large share of the text's height.

    Measured against the text rather than the page, so banners, photos and white space do not hide a newsletter's
    columns.
    """
    if not text:
        return None
    side_by_side = _height(
        (max(a[1], b[1]), min(a[3], b[3]))
        for i, a in enumerate(text)
        for b in text[i + 1 :]
        if (a[2] <= b[0] or b[2] <= a[0]) and min(a[3], b[3]) > max(a[1], b[1])
    )
    return 2 if side_by_side >= _SIDE_BY_SIDE * _height((t[1], t[3]) for t in text) else 1


def _height(spans: Iterable[tuple[float, float]]) -> float:
    """The total height covered by vertical spans, overlaps counted once."""
    covered = reach = 0.0
    for top, bottom in sorted(spans):
        covered += max(0.0, bottom - max(top, reach))
        reach = max(reach, bottom)
    return covered
