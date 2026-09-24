"""
Build contact_sheets/sheet_XX.jpg: 3x2 grids of 6 pages each (~480px wide
tiles), with the page id drawn on each tile, so a reviewer can eyeball labels
quickly. Reads pages/*.jpg in the order they appear in labels.jsonl.
"""
import json
import math
import os

from PIL import Image, ImageDraw, ImageFont

DATA_DIR = "/Users/kavy/Code/Projects/jesteruct/bench/vision_bakeoff/data"
PAGES_DIR = os.path.join(DATA_DIR, "pages")
OUT_DIR = os.path.join(DATA_DIR, "contact_sheets")
LABELS_PATH = os.path.join(DATA_DIR, "labels.jsonl")

TILE_W = 480
COLS, ROWS = 3, 2
PER_SHEET = COLS * ROWS
PAD = 8
LABEL_H = 26


def load_font():
    for path in [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Menlo.ttc",
    ]:
        try:
            return ImageFont.truetype(path, 18)
        except Exception:
            continue
    return ImageFont.load_default()


def make_tile(page_id, font):
    path = os.path.join(PAGES_DIR, f"{page_id}.jpg")
    im = Image.open(path).convert("RGB")
    w, h = im.size
    scale = TILE_W / w
    tile_h = round(h * scale)
    im = im.resize((TILE_W, tile_h), Image.LANCZOS)

    canvas = Image.new("RGB", (TILE_W, tile_h + LABEL_H), (255, 255, 255))
    canvas.paste(im, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, tile_h, TILE_W, tile_h + LABEL_H], fill=(20, 20, 20))
    draw.text((6, tile_h + 4), page_id, fill=(255, 255, 255), font=font)
    return canvas


def main():
    ids = []
    with open(LABELS_PATH) as f:
        for line in f:
            ids.append(json.loads(line)["id"])

    os.makedirs(OUT_DIR, exist_ok=True)
    font = load_font()
    n_sheets = math.ceil(len(ids) / PER_SHEET)

    for sheet_idx in range(n_sheets):
        chunk = ids[sheet_idx * PER_SHEET:(sheet_idx + 1) * PER_SHEET]
        tiles = [make_tile(pid, font) for pid in chunk]
        max_tile_h = max(t.height for t in tiles)

        sheet_w = COLS * TILE_W + (COLS + 1) * PAD
        sheet_h = ROWS * max_tile_h + (ROWS + 1) * PAD
        sheet = Image.new("RGB", (sheet_w, sheet_h), (230, 230, 230))

        for i, tile in enumerate(tiles):
            row, col = divmod(i, COLS)
            x = PAD + col * (TILE_W + PAD)
            y = PAD + row * (max_tile_h + PAD)
            sheet.paste(tile, (x, y))

        out_path = os.path.join(OUT_DIR, f"sheet_{sheet_idx + 1:02d}.jpg")
        sheet.save(out_path, "JPEG", quality=88)
        print(f"{out_path}: {len(chunk)} tiles")


if __name__ == "__main__":
    main()
