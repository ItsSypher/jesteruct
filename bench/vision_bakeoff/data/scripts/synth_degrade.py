"""
Synthetic degradation generators for the vision-bakeoff bench:
  - fax: 1-bit dither, low effective dpi, slight skew, salt noise, fax header
  - camera_photo: perspective warp onto a textured background, lighting
    gradient, blur, JPEG compression
  - rotate: simple 90-degree rotation (for the "rotated page" case)

Pure PIL/numpy, no external services.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


def make_fax(img: Image.Image, seed: int = 0) -> Image.Image:
    rng = np.random.default_rng(seed)
    img = img.convert("L")

    # Simulate a low effective capture resolution (~100-150 "dpi" equivalent)
    # relative to the source, then upscale back so the page stays big.
    w, h = img.size
    low_w, low_h = max(1, w // 3), max(1, h // 3)
    img = img.resize((low_w, low_h), Image.LANCZOS).resize((w, h), Image.LANCZOS)

    # Slight skew (1-2 degrees), expand to keep full page, white background.
    angle = float(rng.uniform(1.0, 2.0) * rng.choice([-1, 1]))
    img = img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=255)

    # 1-bit dithered (classic fax bilevel look).
    img_1bit = img.convert("1", dither=Image.FLOYDSTEINBERG)
    arr = np.array(img_1bit.convert("L"), dtype=np.float32)

    # Salt noise (isolated black/white speckle typical of thermal fax lines).
    speckle = rng.random(arr.shape)
    arr[speckle < 0.004] = 0.0
    arr[speckle > 0.997] = 255.0

    out = Image.fromarray(arr.astype(np.uint8), mode="L").convert("RGB")

    # Fax header line.
    draw = ImageDraw.Draw(out)
    header = "*** FAX *** 09/24 00:41  FROM: 555-0134  PAGE 001  ***"
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 22)
    except Exception:
        font = ImageFont.load_default()
    draw.rectangle([0, 0, out.width, 40], fill=(255, 255, 255))
    draw.text((10, 8), header, fill=(0, 0, 0), font=font)

    return out


def make_camera_photo(img: Image.Image, seed: int = 0) -> Image.Image:
    rng = np.random.default_rng(seed)
    img = img.convert("RGB")
    w, h = img.size

    # Desk-like textured background, larger than the page.
    pad = int(0.18 * max(w, h))
    bg_w, bg_h = w + 2 * pad, h + 2 * pad
    base_color = rng.integers(60, 110, size=3)
    bg = np.zeros((bg_h, bg_w, 3), dtype=np.uint8)
    bg[:, :] = base_color
    noise = rng.normal(0, 10, size=(bg_h, bg_w, 3))
    bg = np.clip(bg.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    bg_img = Image.fromarray(bg).filter(ImageFilter.GaussianBlur(3))

    # Perspective-warp the page slightly (four corner jitter).
    def jitter(pt, frac=0.03):
        dx = rng.uniform(-frac, frac) * w
        dy = rng.uniform(-frac, frac) * h
        return pt[0] + dx, pt[1] + dy

    src = [(0, 0), (w, 0), (w, h), (0, h)]
    dst = [jitter(p) for p in src]

    def find_coeffs(pa, pb):
        matrix = []
        for p1, p2 in zip(pa, pb):
            matrix.append([p2[0], p2[1], 1, 0, 0, 0, -p1[0] * p2[0], -p1[0] * p2[1]])
            matrix.append([0, 0, 0, p2[0], p2[1], 1, -p1[1] * p2[0], -p1[1] * p2[1]])
        A = np.array(matrix, dtype=np.float64)
        B = np.array(pa).reshape(8)
        res = np.linalg.solve(A, B)
        return res

    coeffs = find_coeffs(dst, src)
    warped = img.transform((w, h), Image.PERSPECTIVE, coeffs, resample=Image.BICUBIC, fillcolor=(255, 255, 255))

    canvas_img = bg_img.copy()
    canvas_img.paste(warped, (pad, pad))

    # Uneven lighting gradient (vignette + warm/cool wash).
    yy, xx = np.mgrid[0:bg_h, 0:bg_w]
    cx, cy = rng.uniform(0.3, 0.7) * bg_w, rng.uniform(0.3, 0.7) * bg_h
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    dist /= dist.max()
    light = 1.15 - 0.5 * dist
    arr = np.array(canvas_img, dtype=np.float32)
    for c in range(3):
        arr[:, :, c] *= light
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    canvas_img = Image.fromarray(arr)

    # Slight blur + downscale/upscale to emulate phone-camera softness.
    canvas_img = canvas_img.filter(ImageFilter.GaussianBlur(radius=float(rng.uniform(0.8, 1.6))))

    # Crop back down a bit so the page still dominates the frame.
    crop_pad = int(pad * 0.4)
    canvas_img = canvas_img.crop((crop_pad, crop_pad, bg_w - crop_pad, bg_h - crop_pad))

    return canvas_img


def rotate_page(img: Image.Image, degrees: int = 90) -> Image.Image:
    return img.rotate(-degrees, expand=True, fillcolor=(255, 255, 255))
