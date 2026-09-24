# /// script
# requires-python = ">=3.12"
# dependencies = ["pypdfium2", "pikepdf", "pymupdf", "numpy", "opencv-python-headless"]
# ///
import time, sys, statistics as st
import pypdfium2 as pdfium, pikepdf, fitz, numpy as np, cv2
files = sys.argv[1:]
def t(): return time.perf_counter()
for f in files:
    d = pdfium.PdfDocument(f); n = len(d)
    # pypdfium2 render 120dpi grayscale
    ts=[]
    for i in range(n):
        s=t(); p=d[i]; bm=p.render(scale=120/72, grayscale=True); a=bm.to_numpy(); ts.append(t()-s)
    # text extraction
    tt=[]
    for i in range(n):
        s=t(); tp=d[i].get_textpage(); txt=tp.get_text_bounded(); c=tp.count_chars(); tt.append(t()-s)
    # quality metrics on last render
    s=t(); lv=cv2.Laplacian(a, cv2.CV_64F).var(); rms=a.std(); q=t()-s
    # pymupdf
    md=fitz.open(f); tm=[]
    for pg in md:
        s=t(); pm=pg.get_pixmap(dpi=120, colorspace=fitz.csGRAY); tm.append(t()-s)
    tmt=[]
    for pg in md:
        s=t(); pg.get_text(); tmt.append(t()-s)
    s=t(); pk=pikepdf.open(f); imgs=0
    for pg in pk.pages:
        r=pg.obj.get('/Resources'); 
        if r is not None and '/XObject' in r: imgs+=len(r.XObject.keys())
    pke=t()-s
    ms=lambda x: f"med {st.median(x)*1000:.1f} ms, mean {st.mean(x)*1000:.1f} ms"
    print(f"{f.split('/')[-1]}: {n} pages, render shape {a.shape}")
    print(f"  pdfium render120 gray: {ms(ts)}  | pymupdf render120 gray: {ms(tm)}")
    print(f"  pdfium text+chars:     {ms(tt)}  | pymupdf get_text:       {ms(tmt)}")
    print(f"  pikepdf open+walk XObjects all pages: {pke*1000:.1f} ms total ({pke*1000/n:.2f} ms/page); laplacian+rms {q*1000:.2f} ms")
