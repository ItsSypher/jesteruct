import time, statistics, subprocess, tempfile, os
import pypdfium2 as pdfium, pikepdf, numpy as np, cv2
path="paper.pdf"
t=time.perf_counter(); pdf=pdfium.PdfDocument(path); n=len(pdf); t_open=time.perf_counter()-t
# S1-ish: text extraction + char count per page
tt=[];chars=[]
for i in range(n):
    t=time.perf_counter(); pg=pdf[i]; tp=pg.get_textpage(); s=tp.get_text_range(); chars.append(len(s)); tt.append(time.perf_counter()-t)
# pikepdf object walk: images + filters per page
t=time.perf_counter(); pk=pikepdf.open(path); imgs=0
for p in pk.pages:
    for k,v in p.images.items(): imgs+=1; _=v.get('/Filter')
t_pk=time.perf_counter()-t
# render 120dpi grayscale + IQA
rt=[];qt=[]
for i in range(n):
    t=time.perf_counter(); img=pdf[i].render(scale=120/72, grayscale=True).to_numpy(); rt.append(time.perf_counter()-t)
    t=time.perf_counter(); g=img if img.ndim==2 else cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    lap=cv2.Laplacian(g,cv2.CV_64F).var(); con=g.std(); noise=np.median(np.abs(g.astype(np.int16)-cv2.medianBlur(g,3)))
    qt.append(time.perf_counter()-t)
    if i==0: cv2.imwrite("p0.png",g)
# tesseract OSD on 3 pages (render at 300dpi for OSD)
ot=[]
for i in range(min(3,n)):
    img=pdf[i].render(scale=300/72, grayscale=True).to_pil(); f=f"osd{i}.png"; img.save(f)
    t=time.perf_counter(); r=subprocess.run(["tesseract",f,"-","--psm","0"],capture_output=True,text=True); ot.append(time.perf_counter()-t)
ms=lambda xs:f"median {statistics.median(xs)*1000:.1f} ms, p95 {sorted(xs)[int(len(xs)*.95)-1]*1000:.1f} ms"
print(f"pages={n} open={t_open*1000:.1f}ms imgs={imgs}")
print("text extract:",ms(tt)); print(f"pikepdf image/filter walk: {t_pk*1000/n:.2f} ms/page")
print("render 120dpi gray:",ms(rt)); print("IQA metrics:",ms(qt)); print("tesseract OSD 300dpi:",ms(ot)); print(r.stdout[:200], r.stderr[-200:])
