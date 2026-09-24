# /// script
# requires-python = ">=3.12"
# dependencies = ["torch", "torchvision", "transformers>=5", "pillow", "numpy", "onnxruntime", "timm"]
# ///
import time, sys, glob, statistics as st, torch, numpy as np
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForObjectDetection
imgs = [Image.open(p).convert("RGB") for p in sorted(glob.glob("/tmp/pdfbench/imgs/*_clean.png") + glob.glob("/tmp/pdfbench/imgs/*_scan.jpg") + glob.glob("/tmp/pdfbench/imgs/*_photo.jpg"))]
which = sys.argv[1:] or ["egret", "heron", "ppv3"]
REPOS = {"egret": "docling-project/docling-layout-egret-medium", "heron": "docling-project/docling-layout-heron", "ppv3": "PaddlePaddle/PP-DocLayoutV3_safetensors"}
def sync(dev):
    if dev == "mps": torch.mps.synchronize()
for name in which:
    proc = AutoImageProcessor.from_pretrained(REPOS[name])
    for dev in ("mps", "cpu"):
        model = AutoModelForObjectDetection.from_pretrained(REPOS[name]).to(dev).eval()
        nparams = sum(p.numel() for p in model.parameters()) / 1e6
        for bs in (1, 8):
            times = []
            with torch.inference_mode():
                for rep in range(2 if dev == "mps" else 1):
                    for i in range(0, len(imgs), bs):
                        batch = imgs[i:i+bs]
                        t = time.perf_counter()
                        inp = proc(images=batch, return_tensors="pt").to(dev)
                        out = model(**inp); sync(dev)
                        res = proc.post_process_object_detection(out, target_sizes=[im.size[::-1] for im in batch], threshold=0.4)
                        if rep == 1 or dev == "cpu": times.append((time.perf_counter() - t) / len(batch))
            print(f"{name} ({nparams:.0f}M params) {dev} bs={bs}: {st.median(times)*1000:.0f} ms/page (median, incl. preprocessing+postprocess)", flush=True)
            if dev == "cpu": break  # bs=8 on CPU is not informative for per-page latency
        if name and dev == "mps":
            labs = model.config.id2label
            for k, im_res in [(0, res[0])]:
                pass
        del model
    # region histogram example on first clean image
    model = AutoModelForObjectDetection.from_pretrained(REPOS[name]).eval()
    with torch.inference_mode():
        r = proc.post_process_object_detection(model(**proc(images=imgs[:1], return_tensors="pt")), target_sizes=[imgs[0].size[::-1]], threshold=0.4)[0]
    from collections import Counter
    print("   labels on", "first page:", dict(Counter(model.config.id2label[int(l)] for l in r["labels"])), flush=True)
