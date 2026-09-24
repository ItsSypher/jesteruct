import time, sys, torch, pypdfium2 as pdfium
from transformers import AutoImageProcessor, AutoModelForObjectDetection
repo=sys.argv[1]; dev=sys.argv[2]; bs=int(sys.argv[3]); dtype=torch.float16 if (len(sys.argv)>4 and sys.argv[4]=="fp16") else torch.float32
imgs=[]
for f in ["/tmp/jbench/pdfref.pdf","/tmp/jbench/heron.pdf","/tmp/jbench/docling.pdf"]:
    d=pdfium.PdfDocument(f)
    for i in range(min(len(d),16)): imgs.append(d[i].render(scale=120/72).to_pil().convert("RGB"))
imgs=imgs[:32]
proc=AutoImageProcessor.from_pretrained(repo, use_fast=True); model=AutoModelForObjectDetection.from_pretrained(repo, dtype=dtype).to(dev).eval()
def sync():
    if dev=="mps": torch.mps.synchronize()
tp=tf=tpp=0; n=0
for it in range(2):
  for i in range(0,len(imgs),bs):
    b=imgs[i:i+bs]
    t0=time.perf_counter(); inp=proc(images=b, return_tensors="pt"); inp={k:v.to(dev, dtype) if v.is_floating_point() else v.to(dev) for k,v in inp.items()}; sync(); t1=time.perf_counter()
    with torch.no_grad(): out=model(**inp)
    sync(); t2=time.perf_counter()
    res=proc.post_process_object_detection(out, target_sizes=[im.size[::-1] for im in b], threshold=0.3); t3=time.perf_counter()
    if it==1: tp+=t1-t0; tf+=t2-t1; tpp+=t3-t2; n+=len(b)
print(f"{repo.split('/')[-1]} {dev} bs={bs} {dtype}: preprocess {tp/n*1000:.1f} + forward {tf/n*1000:.1f} + post {tpp/n*1000:.1f} = {(tp+tf+tpp)/n*1000:.1f} ms/page (input {tuple(inp['pixel_values'].shape)})")
