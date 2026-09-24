import onnxruntime as ort, numpy as np, pypdfium2 as pdfium, cv2, collections, time
from huggingface_hub import hf_hub_download
ort.set_default_logger_severity(3)
L="paragraph_title image text number abstract content figure_title formula table table_title reference doc_title footnote header algorithm footer seal chart_title chart formula_number header_image footer_image aside_text".split()
p=hf_hub_download("stefanj0/PP-DocLayout-S-ONNX","pp_doclayout_s.onnx")
MEAN=np.array([0.485,0.456,0.406],np.float32); STD=np.array([0.229,0.224,0.225],np.float32)
for threads in [0,1,2]:
  so=ort.SessionOptions()
  if threads: so.intra_op_num_threads=threads
  s=ort.InferenceSession(p,so,providers=["CPUExecutionProvider"])
  d=pdfium.PdfDocument("/tmp/jbench/heron.pdf"); ts=[]
  for i in range(len(d)):
    img=np.array(d[i].render(scale=120/72).to_pil().convert("RGB")); h,w,_=img.shape
    x=((cv2.resize(img,(480,480)).astype(np.float32)/255.-MEAN)/STD).transpose(2,0,1)[None].copy()
    t=time.perf_counter(); out=s.run(None,{"image":x,"scale_factor":np.array([[480/h,480/w]],np.float32)}); ts.append(time.perf_counter()-t)
    det=out[0][:int(np.array(out[1]).ravel()[0])]
    if threads==0 and i in (0,2,5): print("page",i,dict(collections.Counter(L[int(c)] for c in det[det[:,1]>0.5][:,0])))
  print("threads",threads or "default", "median ms", round(float(np.median(ts))*1000,1))
