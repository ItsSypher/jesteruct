import onnxruntime as ort, numpy as np, time, sys, statistics as st, pypdfium2 as pdfium, cv2
from huggingface_hub import hf_hub_download
ort.set_default_logger_severity(3)
pages=[]
for f in ["/tmp/jbench/pdfref.pdf","/tmp/jbench/heron.pdf","/tmp/jbench/docling.pdf"]:
    d=pdfium.PdfDocument(f)
    for i in range(min(len(d),10)): pages.append(np.array(d[i].render(scale=120/72).to_pil().convert("RGB")))
MEAN=np.array([0.485,0.456,0.406],np.float32); STD=np.array([0.229,0.224,0.225],np.float32)
def prep(img,S,norm=True):
    h,w,_=img.shape; x=cv2.resize(img,(S,S)).astype(np.float32)/255.
    if norm: x=(x-MEAN)/STD
    return x.transpose(2,0,1)[None].copy(), np.array([[S/h,S/w]],np.float32), np.array([[S,S]],np.float32)
specs={"pp-doclayout-s":("stefanj0/PP-DocLayout-S-ONNX","pp_doclayout_s.onnx",480,True),
       "pp-doclayout_plus-l":("PaddlePaddle/PP-DocLayout_plus-L_onnx","inference.onnx",800,True),
       "doclayout-yolo":("anyformat/doclayout-yolo-docstructbench","model.onnx",1024,False)}
name=sys.argv[1]; ep=sys.argv[2]
repo,fn,S,norm=specs[name]; p=hf_hub_download(repo,fn)
prov={"cpu":["CPUExecutionProvider"],
      "coreml":[("CoreMLExecutionProvider",{"ModelFormat":"MLProgram","MLComputeUnits":"ALL"}),"CPUExecutionProvider"],
      "coreml-gpu":[("CoreMLExecutionProvider",{"ModelFormat":"MLProgram","MLComputeUnits":"CPUAndGPU"}),"CPUExecutionProvider"]}[ep]
so=ort.SessionOptions()
t=time.perf_counter()
try: s=ort.InferenceSession(p, so, providers=prov)
except Exception as e: print(name,ep,"SESSION FAIL",str(e)[:200]); sys.exit()
tl=time.perf_counter()-t
ins=[i.name for i in s.get_inputs()]
def feed(img):
    x,sf,ims=prep(img,S,norm); f={"image":x,"images":x,"scale_factor":sf,"im_shape":ims}; return {k:f[k] for k in ins}
try:
    for _ in range(3): s.run(None, feed(pages[0]))
except Exception as e: print(name,ep,"RUN FAIL",str(e)[:200]); sys.exit()
tp=[];tr=[]
for img in pages:
    t0=time.perf_counter(); fd=feed(img); t1=time.perf_counter(); out=s.run(None, fd); t2=time.perf_counter(); tp.append(t1-t0); tr.append(t2-t1)
print(f"{name} ORT[{ep}] {S}px: load {tl:.1f}s, preprocess {st.median(tp)*1000:.1f} ms + run median {st.median(tr)*1000:.1f} ms (p90 {sorted(tr)[int(len(tr)*.9)]*1000:.1f}) over {len(pages)} pages")
