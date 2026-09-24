import time, statistics as st, sys
import pypdfium2 as pdfium, pikepdf, fitz, numpy as np
files = ["/tmp/jbench/pdfref.pdf", "/tmp/jbench/heron.pdf", "/tmp/jbench/docling.pdf", "/tmp/jbench/irs.pdf"]
scale = 120/72
def t_pdfium(path, n=200):
    doc = pdfium.PdfDocument(path); N = min(len(doc), n); ts=[]; tt=[]
    for i in range(N):
        t=time.perf_counter(); pg=doc[i]
        bm = pg.render(scale=scale, grayscale=True); a = bm.to_numpy(); ts.append(time.perf_counter()-t)
        t=time.perf_counter(); tp=pg.get_textpage(); s=tp.get_text_range(); nc=tp.count_chars(); tt.append(time.perf_counter()-t)
    return N, ts, tt
def t_fitz(path, n=200):
    doc = fitz.open(path); N=min(len(doc), n); ts=[]; tt=[]
    for i in range(N):
        t=time.perf_counter(); pg=doc[i]
        pix = pg.get_pixmap(dpi=120, colorspace=fitz.csGRAY); a=np.frombuffer(pix.samples, dtype=np.uint8); ts.append(time.perf_counter()-t)
        t=time.perf_counter(); s=pg.get_text(); tt.append(time.perf_counter()-t)
    return N, ts, tt
def t_pike(path, n=200):
    t=time.perf_counter(); pdf=pikepdf.open(path); topen=time.perf_counter()-t
    N=min(len(pdf.pages), n); ts=[]
    for i in range(N):
        t=time.perf_counter(); pg=pdf.pages[i]
        imgs = list(pg.images.items())
        for k,im in imgs: _=(im.get('/Filter'), im.get('/BitsPerComponent'), im.get('/Width'))
        fonts = pg.Resources.get('/Font', {}); _=[ (fonts[f].get('/BaseFont'), '/ToUnicode' in fonts[f]) for f in fonts.keys()] if fonts else None
        annots = pg.get('/Annots'); _ = len(annots) if annots else 0
        ts.append(time.perf_counter()-t)
    return N, ts, topen
def fmt(x): return f"median {st.median(x)*1000:.1f} ms, p95 {sorted(x)[int(len(x)*0.95)-1]*1000:.1f} ms, mean {st.mean(x)*1000:.1f} ms"
for f in files:
    N, r, tx = t_pdfium(f); print(f, N, "pages"); print("  pypdfium2 render120 gray:", fmt(r)); print("  pypdfium2 textpage+text:", fmt(tx))
    N, r, tx = t_fitz(f); print("  pymupdf render120 gray:  ", fmt(r)); print("  pymupdf get_text:        ", fmt(tx))
    N, r, to = t_pike(f); print(f"  pikepdf open {to*1000:.1f} ms; per-page images/fonts/annots:", fmt(r))
