# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx"]
# ///
import os, sys, time, json, asyncio, base64, httpx
exec(open('/tmp/pdfbench/vlmbench.py').read().split('def call')[0])
async def one(c, model, img):
    p = payload(model, img, {"stream": False}); p.pop("stream_options")
    r = await c.post(f"{BASE}/chat/completions", json=p, headers={"Authorization": f"Bearer {KEY}"}); return r.json()
async def main():
    model = sys.argv[1]; n = int(sys.argv[2]); conc = int(sys.argv[3])
    imgs = list(IMGS.values()) * (n // 3)
    sem = asyncio.Semaphore(conc)
    async with httpx.AsyncClient(timeout=600) as c:
        async def g(i):
            async with sem: return await one(c, model, i)
        t = time.perf_counter(); res = await asyncio.gather(*[g(i) for i in imgs]); el = time.perf_counter() - t
    ok = sum(1 for r in res if "choices" in r)
    print(f"{model} conc={conc}: {len(imgs)} pages in {el:.1f}s -> {len(imgs)/el:.2f} pages/s ({ok} ok)")
asyncio.run(main())
