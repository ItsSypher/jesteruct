# /// script
# requires-python = ">=3.12"
# dependencies = ["pypdfium2", "numpy", "opencv-python-headless", "pillow"]
# ///
import pypdfium2 as pdfium, numpy as np, cv2, os
from PIL import Image
os.makedirs("imgs", exist_ok=True)
srcs = {"guide": "/Users/kavy/Downloads/Q50 LUMI User Guide (1).pdf", "paper": "/Users/kavy/Downloads/QPizza Paper Theory.pdf"}
rng = np.random.default_rng(0)
for tag, f in srcs.items():
    d = pdfium.PdfDocument(f)
    for i in range(3):
        a = d[i].render(scale=120/72, grayscale=True).to_numpy()
        cv2.imwrite(f"imgs/{tag}{i}_clean.png", a)
        h, w = a.shape
        # synthetic flatbed scan: 1.5 deg skew, blur, noise, jpeg q35
        M = cv2.getRotationMatrix2D((w/2, h/2), 1.5, 1.0)
        s = cv2.warpAffine(a, M, (w, h), borderValue=235)
        s = cv2.GaussianBlur(s, (0, 0), 1.6)
        s = np.clip(s.astype(np.float32) + rng.normal(0, 12, s.shape), 0, 255).astype(np.uint8)
        cv2.imwrite(f"imgs/{tag}{i}_scan.jpg", s, [cv2.IMWRITE_JPEG_QUALITY, 35])
        # synthetic camera photo: page warped onto textured background with lighting gradient
        bg = (rng.normal(90, 25, (int(h*1.3), int(w*1.3)))).clip(0,255).astype(np.uint8)
        bg = cv2.GaussianBlur(bg, (0,0), 3)
        H, W = bg.shape
        src = np.float32([[0,0],[w,0],[w,h],[0,h]])
        dst = np.float32([[W*0.12,H*0.08],[W*0.85,H*0.12],[W*0.9,H*0.93],[W*0.08,H*0.88]])
        P = cv2.getPerspectiveTransform(src, dst)
        warped = cv2.warpPerspective(a, P, (W, H), borderValue=0)
        mask = cv2.warpPerspective(np.full_like(a,255), P, (W, H))
        out = np.where(mask>0, warped, bg).astype(np.float32)
        grad = np.linspace(0.65, 1.05, W)[None, :]
        out = np.clip(out*grad, 0, 255).astype(np.uint8)
        cv2.imwrite(f"imgs/{tag}{i}_photo.jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 85])
print(sorted(os.listdir("imgs")))
