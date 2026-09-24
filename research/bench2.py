import time, subprocess, statistics
import pypdfium2 as pdfium
pdf=pdfium.PdfDocument("paper.pdf")
for dpi in (150,200):
    ts=[]
    for i in range(3):
        f=f"o{dpi}_{i}.png"; pdf[i].render(scale=dpi/72, grayscale=True).to_pil().save(f)
        t=time.perf_counter(); r=subprocess.run(["tesseract",f,"-","--psm","0","--dpi",str(dpi)],capture_output=True,text=True); ts.append(time.perf_counter()-t)
    print(f"OSD {dpi}dpi median {statistics.median(ts)*1000:.0f} ms ->", " ".join(l for l in r.stdout.splitlines() if l.startswith(('Rotate','Script:','Orientation conf'))))
from ocrmac import ocrmac
pdf[0].render(scale=150/72).to_pil().save("v0.png")
for lvl in ("fast","accurate"):
    ts=[]
    for _ in range(3):
        t=time.perf_counter(); res=ocrmac.OCR("v0.png", recognition_level=lvl).recognize(); ts.append(time.perf_counter()-t)
    confs=[c for _,c,_ in res]
    print(f"Apple Vision OCR {lvl} 150dpi: median {statistics.median(ts)*1000:.0f} ms, {len(res)} lines, mean conf {sum(confs)/len(confs):.2f}")
