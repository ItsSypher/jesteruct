"""Quick OCR for pages without a trustworthy text layer: Apple Vision on macOS, RapidOCR (ONNX) elsewhere.

The result only feeds evidence (a text sample and a confidence), so one fast English-model pass is enough.
Engines are created lazily, once per process.
"""

import io
import sys
from functools import cache

import numpy as np
from PIL import Image

from ..models import OcrResult


def resolve_backend(requested: str) -> str:
    if requested != "auto":
        return requested
    if sys.platform == "darwin":
        try:
            import ocrmac  # noqa: F401
        except ImportError:
            return "rapid"
        return "apple"
    return "rapid"


@cache
def _rapid():
    from rapidocr import RapidOCR

    return RapidOCR(params={"Global.log_level": "warning"})


def _apple(jpeg: bytes) -> OcrResult:
    from ocrmac import ocrmac

    img = Image.open(io.BytesIO(jpeg))
    lines = ocrmac.OCR(img, recognition_level="accurate", language_preference=["en-US"]).recognize()
    confidence = sum(c for _, c, _ in lines) / len(lines) if lines else 0.0
    return OcrResult(text="\n".join(t for t, _, _ in lines), confidence=confidence, lines=len(lines), backend="apple")


def _rapid_ocr(jpeg: bytes) -> OcrResult:
    img = np.array(Image.open(io.BytesIO(jpeg)).convert("RGB"))[:, :, ::-1]
    result = _rapid()(img)
    texts = list(result.txts or ())
    scores = list(result.scores or ())
    confidence = sum(scores) / len(scores) if scores else 0.0
    return OcrResult(text="\n".join(texts), confidence=confidence, lines=len(texts), backend="rapid")


def read(jpeg: bytes, backend: str) -> OcrResult:
    return _apple(jpeg) if backend == "apple" else _rapid_ocr(jpeg)
