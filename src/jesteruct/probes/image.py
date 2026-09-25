"""Page images: one 1024 px JPEG per page (what the vision model sees), image-quality measures, a thumbnail, and a
full-resolution view for people."""

import io
import threading

import cv2
import numpy as np
import pillow_heif
import pypdfium2 as pdfium
from PIL import Image, ImageOps

from ..models import ImageQuality

pillow_heif.register_heif_opener()  # pool processes open phone photos (HEIC) without importing intake
cv2.setNumThreads(1)  # parallelism comes from the process pool

LONG_SIDE = 1024
THUMB_SIDE = 320
VIEW_SIDE = 2400  # a PDF page shown to a person: A4 at about 290 dpi
VIEW_IMAGE_SIDE = 4096  # an image file is shown at its own resolution, up to this
_VIEW_LOCK = threading.Lock()  # the API renders views in threads, and pdfium is not thread-safe


def _jpeg(img: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def render_pdf_page(page: pdfium.PdfPage) -> bytes:
    w, h = page.get_size()
    return _jpeg(page.render(scale=LONG_SIDE / max(w, h)).to_pil())


def image_page(path: str, index: int) -> bytes:
    with Image.open(path) as img:
        img.seek(index)
        if img.format == "JPEG" and max(img.size) <= LONG_SIDE:
            with open(path, "rb") as f:  # already page-sized: keep the original bytes
                return f.read()
        frame = ImageOps.exif_transpose(img.convert("RGB"))
        frame.thumbnail((LONG_SIDE, LONG_SIDE), Image.Resampling.LANCZOS)
        return _jpeg(frame)


def page_view(document: bytes, index: int) -> bytes:
    """One page at the best resolution worth showing a person, from the document's own bytes. Raises IndexError,
    EOFError or OSError when there is no such page or the bytes are not a PDF or an image."""
    with _VIEW_LOCK:
        if document.startswith(b"%PDF-"):
            pdf = pdfium.PdfDocument(document)
            if not 0 <= index < len(pdf):
                raise IndexError(f"no page {index}")
            page = pdf[index]
            w, h = page.get_size()
            return _jpeg(page.render(scale=VIEW_SIDE / max(w, h)).to_pil(), quality=88)
        with Image.open(io.BytesIO(document)) as img:
            img.seek(index)
            frame = ImageOps.exif_transpose(img.convert("RGB"))
            frame.thumbnail((VIEW_IMAGE_SIDE, VIEW_IMAGE_SIDE), Image.Resampling.LANCZOS)
            return _jpeg(frame, quality=88)


def thumbnail(jpeg: bytes) -> bytes:
    with Image.open(io.BytesIO(jpeg)) as img:
        img.thumbnail((THUMB_SIDE, THUMB_SIDE), Image.Resampling.LANCZOS)
        return _jpeg(img, quality=80)


def decode(jpeg: bytes) -> np.ndarray:
    return cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)


def quality(bgr: np.ndarray) -> ImageQuality:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    b = max(4, int(0.03 * min(h, w)))
    border = np.concatenate([gray[:b].ravel(), gray[-b:].ravel(), gray[:, :b].ravel(), gray[:, -b:].ravel()])
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return ImageQuality(
        sharpness=float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        contrast=float(gray.std()),
        noise=float(np.median(np.abs(gray.astype(np.int16) - cv2.medianBlur(gray, 3)))),
        bilevel_share=float(((gray <= 30) | (gray >= 225)).mean()),
        background_mean=float(np.percentile(gray, 90)),
        border_mean=float(border.mean()),
        border_std=float(border.std()),
        colour=float(hsv[..., 1].mean()),
    )
