# /// script
# requires-python = ">=3.12"
# dependencies = ["onnxruntime", "pillow", "numpy", "huggingface_hub"]
# ///
import onnxruntime as ort, numpy as np, time, glob, statistics as st
from PIL import Image
from huggingface_hub import hf_hub_download
path = hf_hub_download("docling-project/docling-layout-heron-onnx", "model.onnx")
print("ort", ort.__version__, ort.get_available_providers())
imgs = [Image.open(p).convert("RGB").resize((640, 640)) for p in sorted(glob.glob("/tmp/pdfbench/imgs/*.png"))+sorted(glob.glob("/tmp/pdfbench/imgs/*_scan.jpg"))]
for prov in (["CPUExecutionProvider"], [("CoreMLExecutionProvider", {"MLComputeUnits": "ALL", "ModelFormat": "MLProgram"}), "CPUExecutionProvider"]):
    so = ort.SessionOptions(); so.log_severity_level = 3
    t = time.perf_counter(); s = ort.InferenceSession(path, so, providers=prov); tl = time.perf_counter() - t
    ins = s.get_inputs()
    if prov[0] == "CPUExecutionProvider": print("inputs:", [(i.name, i.shape, i.type) for i in ins])
    times = []
    for rep in range(2):
        for im in imgs:
            x = (np.asarray(im, dtype=np.float32) / 255.0).transpose(2, 0, 1)[None]
            feed = {ins[0].name: x}
            if len(ins) > 1: feed[ins[1].name] = np.array([[640, 640]], dtype=np.int64)
            t = time.perf_counter(); s.run(None, feed); 
            if rep: times.append(time.perf_counter() - t)
    p = prov[0] if isinstance(prov[0], str) else prov[0][0]
    print(f"heron-onnx {p}: session load {tl:.1f}s, {st.median(times)*1000:.0f} ms/page median (model only, 640x640)")
