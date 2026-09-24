# /// script
# requires-python = ">=3.12"
# dependencies = ["pypdfium2", "opencv-python-headless", "numpy"]
# ///
import subprocess, time, cv2, pypdfium2 as pdfium, os, re
env = {**os.environ, "OMP_THREAD_LIMIT": "1"}
docs = {"guide": "/Users/kavy/Downloads/Q50 LUMI User Guide (1).pdf", "paper": "/Users/kavy/Downloads/QPizza Paper Theory.pdf", "pofo": "/Users/kavy/Downloads/Portfolio Optimization Quantum Computer.pdf"}
for dpi in (120, 200, 300):
    right = total = 0; ts = []
    for tag, f in docs.items():
        d = pdfium.PdfDocument(f)
        for i in range(min(4, len(d))):
            a = d[i].render(scale=dpi/72, grayscale=True).to_numpy()
            for rot, cvr in ((0, None), (90, cv2.ROTATE_90_CLOCKWISE), (180, cv2.ROTATE_180)):
                im = a if cvr is None else cv2.rotate(a, cvr)
                p = f"/tmp/pdfbench/osd_tmp.png"; cv2.imwrite(p, im)
                t = time.perf_counter()
                o = subprocess.run(["tesseract", p, "-", "--psm", "0", "--dpi", str(dpi)], capture_output=True, text=True, env=env).stdout
                ts.append(time.perf_counter() - t)
                m = re.search(r"Orientation in degrees: (\d+)", o)
                total += 1; right += bool(m and int(m.group(1)) == rot)
    print(f"dpi {dpi}: correct orientation {right}/{total}, median {sorted(ts)[len(ts)//2]*1000:.0f} ms/page")
