"""Which vision model should feed Jev's evidence, and can we skip it on clean born-digital PDFs?

Reuses run_jev's decomposed (vector) Jev setup and swaps the source of the `vision_check` evidence:
  - page images reuse each model's bake-off answers (no new calls);
  - PDF renders get one new call per model, cached in vlm_cache/<model>/.
Also runs a "skip vision on trusted PDFs" policy: no vision call when the cheap rules already trust the text layer.

Usage: uv run --no-project --with httpx python run_evidence_sweep.py
"""

import asyncio
import base64
import json
from pathlib import Path

import httpx

import run_jev as R
from run import SCHEMA, SYSTEM, load_key

ROOT = Path(__file__).parent
VB = ROOT.parent / "vision_bakeoff"
MODELS = ["google/gemini-3.8-flash", "google/gemini-3.5-flash-lite", "openai/gpt-6-luna", "~anthropic/claude-haiku-latest"]


def slug(m):
    return m.replace("/", "__").replace("~", "")


def source_image(c):
    """The image the vision model sees for a case, and the bake-off page id if it is one of the 60 pages."""
    cid = c["id"]
    if cid.startswith("img_"):
        return None, cid[4:]
    if cid.startswith("ocr_"):
        return None, cid[4:]
    if cid.startswith("garb_"):
        src = "pdf_" + cid[5:].rsplit("_", 1)[0]
        return ROOT / "pages" / f"{src}.jpg", None
    return ROOT / "pages" / f"{cid}.jpg", None


async def vlm_answer(client, key, model, c, sem):
    img, pid = source_image(c)
    if pid:
        f = VB / "results" / slug(model) / f"{pid}.json"
        try:
            return json.loads(json.loads(f.read_text())["content"]), 0.0
        except Exception:
            return None, 0.0
    cache = ROOT / "vlm_cache" / slug(model) / f"{img.stem}.json"
    if model == "google/gemini-3.8-flash" and (ROOT / "vlm_cache" / f"{img.stem}.json").exists():
        return json.loads((ROOT / "vlm_cache" / f"{img.stem}.json").read_text()), 0.0
    if cache.exists():
        d = json.loads(cache.read_text())
        return d.get("answer"), 0.0
    b64 = base64.b64encode(img.read_bytes()).decode()
    body = {"model": model, "messages": [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": [{"type": "text", "text": "Triage this page."}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}],
            "response_format": {"type": "json_schema", "json_schema": SCHEMA}, "provider": {"require_parameters": True}, "usage": {"include": True}}
    async with sem:
        for attempt in range(5):
            r = await client.post("https://openrouter.ai/api/v1/chat/completions", json=body, headers={"Authorization": f"Bearer {key}"}, timeout=300)
            if r.status_code == 200:
                break
            await asyncio.sleep(2 ** attempt * 3)
    j = r.json()
    try:
        ans = json.loads(j["choices"][0]["message"]["content"])
    except Exception:
        ans = None
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"answer": ans, "cost": (j.get("usage") or {}).get("cost")}))
    return ans, (j.get("usage") or {}).get("cost") or 0.0


def rules_trust(c):
    return R.rules(c)["flags"]["text_layer_trustworthy"] == 1.0


async def main():
    key = load_key()
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient() as client:
        # 1) collect vision answers per model
        answers = {}
        for m in MODELS:
            res = await asyncio.gather(*(vlm_answer(client, key, m, c, sem) for c in R.CASES))
            answers[m] = {c["id"]: a for c, (a, _) in zip(R.CASES, res)}

        # 2) run decomposed Jev with each evidence source, and with vision skipped on rule-trusted PDFs
        async def job(system, c, vlm_ans):
            out = ROOT / "results" / system / "run1" / f"{c['id']}.json"
            if out.exists():
                return
            cc = {**c, "vlm": vlm_ans}
            variant = "v3_full" if vlm_ans is not None else "v2_probes_text"
            async with sem:
                rec = await R.jev(client, key, cc, variant, "vector")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps({"case": c["id"], "system": system, "run": 1, "vision_used": vlm_ans is not None, **rec}))

        jobs = []
        for m in MODELS:
            tag = slug(m).split("__")[1]
            for c in R.CASES:
                jobs.append(job(f"jevvec_{tag}", c, answers[m][c["id"]]))
                jobs.append(job(f"jevvec_{tag}_skiptrusted", c, None if rules_trust(c) else answers[m][c["id"]]))
        await asyncio.gather(*jobs)
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
