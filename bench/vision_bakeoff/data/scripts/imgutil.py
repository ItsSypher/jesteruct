"""Shared image utility: convert any raw source image to the bench's page
format -- RGB JPEG, long side exactly 1024px, quality 90, LANCZOS resize."""
from PIL import Image


def to_page_jpeg(src_path, out_path, long_side=1024, quality=90):
    im = Image.open(src_path)
    im = im.convert("RGB")
    w, h = im.size
    scale = long_side / max(w, h)
    new_w, new_h = round(w * scale), round(h * scale)
    # Ensure the long side is EXACTLY long_side (rounding can leave it at
    # long_side-1 for the already-long dimension); fix up explicitly.
    if w >= h:
        new_w = long_side
    else:
        new_h = long_side
    im = im.resize((new_w, new_h), Image.LANCZOS)
    im.save(out_path, "JPEG", quality=quality)
    return im.size
