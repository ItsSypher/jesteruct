"""Quick OCR for pages without a trustworthy text layer: Apple Vision on macOS, RapidOCR (ONNX) elsewhere.

The result only feeds evidence (a text sample and a confidence), so one fast English-model pass is enough.
Engines are created lazily, once per process.
"""

import io
import logging
import subprocess
import sys
from functools import cache

import numpy as np
from PIL import Image, ImageDraw

from ..models import OcrResult

log = logging.getLogger(__name__)

# A warm first call takes about a second; a cold one compiles Vision's Neural Engine models first (26-59 s measured).
APPLE_CHECK_S = 180


def resolve_backend(requested: str) -> str:
    """`auto` is Apple Vision on macOS when it answers, and RapidOCR otherwise."""
    if requested != "auto":
        return requested
    if sys.platform != "darwin":
        return "rapid"
    try:
        import ocrmac  # noqa: F401
    except ImportError:
        return "rapid"
    if not _apple_answers():
        log.warning("Apple Vision OCR did not answer within %d s; using RapidOCR", APPLE_CHECK_S)
        return "rapid"
    return "apple"


@cache
def _apple_answers() -> bool:
    """Apple Vision can hang outright, and a hung call cannot be cancelled inside the process, so it is tried once, in a
    child process with a deadline.

    The deadline outlasts a cold compile on purpose. After a macOS update Vision recompiles its models, and it keeps the
    result only if the caller is still alive when the compile ends; a caller killed sooner leaves the cache cold for the
    next one. The child runs `sys.executable`, as the probe pool's workers do, because the cache is kept per executable.
    """
    check = [sys.executable, "-c", "from jesteruct.probes.ocr import _read_a_word; _read_a_word()"]
    try:
        return subprocess.run(check, capture_output=True, timeout=APPLE_CHECK_S).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def _read_a_word() -> None:
    img = Image.new("RGB", (320, 64), "white")
    ImageDraw.Draw(img).text((12, 20), "jesteruct", fill="black")
    buffer = io.BytesIO()
    img.save(buffer, "JPEG")
    _apple(buffer.getvalue())


@cache
def _rapid():
    from rapidocr import RapidOCR

    # One thread per engine: the probe pool already runs one process per core, and ONNX Runtime's default of one thread
    # per core in every process oversubscribes the CPU many times over.
    return RapidOCR(
        params={
            "Global.log_level": "warning",
            "EngineConfig.onnxruntime.intra_op_num_threads": 1,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        }
    )


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
