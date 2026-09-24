"""Render single-page PDFs to PNG using pypdfium2, targeting >=1024px long side."""
import sys
import pypdfium2 as pdfium

def render(pdf_path, out_path, target_long_side=1600):
    pdf = pdfium.PdfDocument(pdf_path)
    page = pdf[0]
    w, h = page.get_size()
    long_side = max(w, h)
    scale = target_long_side / long_side
    bitmap = page.render(scale=scale, draw_annots=True)
    pil_image = bitmap.to_pil()
    pil_image = pil_image.convert("RGB")
    pil_image.save(out_path)
    print(out_path, pil_image.size)

if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2])
