import time, os, numpy as np, onnxruntime as ort
from huggingface_hub import hf_hub_download
from PIL import Image
import pypdfium2 as pdfium
os.chdir("/tmp/jstbench")
import sys
p=sys.argv[1] if len(sys.argv)>1 else hf_hub_download("docling-project/docling-layout-heron-onnx","model.onnx")
print("ort", ort.__version__, ort.get_available_providers())
s0=ort.InferenceSession(p, providers=["CPUExecutionProvider"])
for i in s0.get_inputs(): print("input", i.name, i.shape, i.type)
for o in s0.get_outputs(): print("output", o.name, o.shape)
imgs=[]
for f in ["born.pdf","heron.pdf","scan.pdf"]:
    d=pdfium.PdfDocument(f)
    for i in range(len(d)): imgs.append(d[i].render(scale=120/72).to_pil().convert("RGB"))
def prep(im):
    a=np.asarray(im.resize((640,640), Image.BILINEAR), dtype=np.uint8)
    a=a.transpose(2,0,1)[None]
    return a if 'uint8' in s0.get_inputs()[0].type else (a.astype(np.float32)/255.)
X=[prep(im) for im in imgs[:16]]
inputs=s0.get_inputs()
def feed(x):
    fd={inputs[0].name:x}
    for extra in inputs[1:]:
        fd[extra.name]=np.array([[640,640]],dtype=np.int64)
    return fd
configs=[("CPU EP",["CPUExecutionProvider"]),
         ("CoreML EP MLProgram ALL",[("CoreMLExecutionProvider",{"ModelFormat":"MLProgram","MLComputeUnits":"ALL"}),"CPUExecutionProvider"]),
         ("CoreML EP MLProgram CPUAndNeuralEngine",[("CoreMLExecutionProvider",{"ModelFormat":"MLProgram","MLComputeUnits":"CPUAndNeuralEngine"}),"CPUExecutionProvider"]),
         ("CoreML EP MLProgram CPUAndGPU",[("CoreMLExecutionProvider",{"ModelFormat":"MLProgram","MLComputeUnits":"CPUAndGPU"}),"CPUExecutionProvider"])]
ref=None
for name,prov in configs:
    try:
        t=time.perf_counter(); s=ort.InferenceSession(p, providers=prov); load=time.perf_counter()-t
        out=s.run(None, feed(X[0])); s.run(None, feed(X[1]))
        t=time.perf_counter()
        for x in X: out=s.run(None, feed(x))
        e=(time.perf_counter()-t)/len(X)
        if ref is None: ref=out
        diff=max(float(np.abs(a-b).max()) for a,b in zip(out,ref)) if ref is not None else 0
        print(f"{name}: {1000*e:.0f} ms/page, session load {load:.1f}s, max abs diff vs CPU {diff:.3g}", flush=True)
    except Exception as ex:
        print(name,"FAIL",repr(ex)[:400], flush=True)
