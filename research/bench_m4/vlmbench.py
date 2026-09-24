# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx"]
# ///
"""Latency + answer bench for one-page JSON classification against OpenAI-compatible endpoints."""
import base64, json, os, sys, time, httpx, statistics as st
BASE = os.environ.get("BASE", "https://openrouter.ai/api/v1")
KEY = os.environ.get("KEY", os.environ.get("OPENROUTER_API_KEY", "x"))
RUNS = int(os.environ.get("RUNS", "3"))
PFX = os.environ.get("PFX", "vlm_")
IMGS = {"scan": f"imgs/{PFX}paper1_scan.jpg", "photo": f"imgs/{PFX}guide0_photo.jpg", "clean": f"imgs/{PFX}paper1_clean.jpg"}
SCHEMA = {"type": "object", "additionalProperties": False,
  "required": ["handwriting", "capture", "legibility", "main_content", "script"],
  "properties": {
    "handwriting": {"type": "string", "enum": ["none","annotations_only","fields_filled_by_hand","mostly_handwritten","unsure"]},
    "capture": {"type": "string", "enum": ["digital_render","flatbed_scan","fax","camera_photo","screenshot","unsure"]},
    "legibility": {"type": "string", "enum": ["clean","mild_issues","hard_to_read","illegible","unsure"]},
    "main_content": {"type": "array", "maxItems": 4, "items": {"type": "string", "enum": ["prose","table","form","chart","photo","math","code","letterhead","signature_page"]}},
    "script": {"type": "string", "enum": ["latin","cyrillic","arabic","hebrew","cjk","other","mixed","unsure"]}}}
PROMPT = ("Classify this single document page image. Answer only from what is visible. "
  "capture: digital_render = rendered straight from a digital file (perfectly straight, clean white, no noise); "
  "flatbed_scan = scanned paper (noise, slight skew, blur or JPEG artefacts, page fills the frame); "
  "camera_photo = photographed (background visible around the page, perspective, uneven light). "
  "Return JSON matching the schema.")
def payload(model, img, extra):
    b64 = base64.b64encode(open(img, "rb").read()).decode()
    p = {"model": model, "stream": True, "temperature": 0, "max_tokens": 300,
         "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}],
         "response_format": {"type": "json_schema", "json_schema": {"name": "page", "strict": True, "schema": SCHEMA}},
         "stream_options": {"include_usage": True}}
    p.update(extra); return p
def call(client, model, img, extra):
    t0 = time.perf_counter(); ttft = None; txt = ""; usage = {}; prov = None
    with client.stream("POST", f"{BASE}/chat/completions", json=payload(model, img, extra),
                       headers={"Authorization": f"Bearer {KEY}"}) as r:
        if r.status_code != 200:
            return {"err": f"{r.status_code} {r.read()[:300]!r}"}
        for line in r.iter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]": continue
            ev = json.loads(line[6:]); prov = ev.get("provider", prov)
            if ev.get("usage"): usage = ev["usage"]
            for ch in ev.get("choices", []):
                d = ch.get("delta", {})
                piece = d.get("content") or ""
                if (piece or d.get("reasoning")) and ttft is None: ttft = time.perf_counter() - t0
                txt += piece
    tot = time.perf_counter() - t0
    try: ans = json.loads(txt); ok = True
    except Exception: ans = txt[:120]; ok = False
    return {"ttft": ttft, "total": tot, "ok": ok, "ans": ans, "usage": usage, "prov": prov}
def main():
    models = sys.argv[1:]
    with httpx.Client(timeout=120) as c:
        for spec in models:
            model, _, ex = spec.partition("|"); extra = json.loads(ex) if ex else {}
            res = []
            for i in range(RUNS):
                for tag, img in IMGS.items():
                    r = call(c, model, img, extra); r["img"] = tag; res.append(r)
            good = [r for r in res if "err" not in r]
            if not good: print(f"{spec}: ERROR {res[0]['err']}"); continue
            tt = [r["ttft"] for r in good if r["ttft"]]; tot = [r["total"] for r in good]
            u = good[-1]["usage"]; valid = sum(r["ok"] for r in good)
            caps = {t: [r["ans"].get("capture") if isinstance(r["ans"], dict) else "BAD" for r in good if r["img"] == t] for t in IMGS}
            leg = [r["ans"].get("legibility") if isinstance(r["ans"], dict) else "BAD" for r in good if r["img"]=="scan"]
            print(f"{spec.split('|')[0]} [{good[-1]['prov']}]: ttft p50 {st.median(tt):.2f}s | total p50 {st.median(tot):.2f}s max {max(tot):.2f}s | "
                  f"valid {valid}/{len(good)} | in {u.get('prompt_tokens')} out {u.get('completion_tokens')} cost {u.get('cost')} | "
                  f"capture scan={caps['scan']} photo={caps['photo']} clean={caps['clean']} | scan-legib={leg}", flush=True)
            if len(good) < len(res): print("   errors:", [r["err"][:120] for r in res if "err" in r][:2])
main()
