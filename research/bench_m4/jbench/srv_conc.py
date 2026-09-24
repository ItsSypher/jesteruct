import httpx, base64, json, time, asyncio, sys
SCHEMA=json.load(open("/tmp/jbench/schema.json")); M=sys.argv[1]
imgs=[base64.b64encode(open(f"/tmp/jbench/s768_{n}","rb").read()).decode() for n in ["page_digital.jpg","page_scan.jpg","p_photo.jpg"]]
async def one(c,i):
  r=await c.post("http://localhost:8931/v1/chat/completions",json={"model":M,"max_tokens":120,"temperature":0,
    "messages":[{"role":"user","content":[{"type":"text","text":f"Classify this document page image (#{i}). Return JSON matching the schema."},{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+imgs[i%3]}}]}],
    "response_format":{"type":"json_schema","json_schema":{"name":"page","strict":True,"schema":SCHEMA}}})
  return r.status_code
async def main():
  async with httpx.AsyncClient(timeout=600) as c:
    await one(c,0)
    for conc in [1,4,8]:
      n=8 if conc<8 else 16; t=time.perf_counter(); sem=asyncio.Semaphore(conc)
      async def w(i):
        async with sem: return await one(c,i)
      res=await asyncio.gather(*[w(i) for i in range(n)])
      el=time.perf_counter()-t; print(f"{M} concurrency {conc}: {n/el:.2f} pages/s ({el/n:.2f}s per page amortised) codes={set(res)}")
asyncio.run(main())
