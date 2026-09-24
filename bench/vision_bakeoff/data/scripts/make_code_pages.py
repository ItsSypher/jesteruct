"""
Synthetic "code page" generator: render a page of real, permissively licensed
(PSF License, same license family as MIT/BSD -- CPython stdlib) source code as
a born-digital PDF using a monospace font, then convert to PNG.

Source: CPython standard library (csv.py, textwrap.py), PSF License.
"""
import subprocess
import sys

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

FONT = "Courier"
FONT_SIZE = 9
LINE_HEIGHT = 11.5
MARGIN = 40


def render_code_pdf(src_path, out_pdf, start_line, n_lines, title):
    with open(src_path) as f:
        lines = f.readlines()
    chunk = lines[start_line:start_line + n_lines]

    c = canvas.Canvas(out_pdf, pagesize=LETTER)
    w, h = LETTER
    y = h - MARGIN

    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN, y, title)
    y -= LINE_HEIGHT * 1.8

    c.setFont(FONT, FONT_SIZE)
    for line in chunk:
        line = line.rstrip("\n").expandtabs(4)
        c.drawString(MARGIN, y, line)
        y -= LINE_HEIGHT
        if y < MARGIN:
            break
    c.showPage()
    c.save()


def pdf_to_png(pdf_path, png_path, target_long_side=1600):
    sys.path.insert(0, "/Users/kavy/Code/Projects/jesteruct/bench/vision_bakeoff/data/scripts")
    from render_pdf_pages import render
    render(pdf_path, png_path, target_long_side=target_long_side)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("src")
    p.add_argument("out_pdf")
    p.add_argument("out_png")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--n", type=int, default=48)
    p.add_argument("--title", default="")
    args = p.parse_args()
    render_code_pdf(args.src, args.out_pdf, args.start, args.n, args.title)
    pdf_to_png(args.out_pdf, args.out_png)
