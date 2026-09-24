"""Vision-arbiter bake-off runner.

Every model gets the same page image, prompt and strict JSON schema, with no
output-token cap and no reasoning overrides, so each runs at its own defaults.
Cost comes from OpenRouter's usage accounting on each response. A ledger shared
across runs enforces the budget, and results are cached per (model, page) so
runs resume where they stopped.

Usage:
  uv run --no-project --with httpx python run.py --models models.txt --pages all --budget 3.5
"""

import argparse
import asyncio
import base64
import json
import os
import random
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).parent
DATA = Path(os.environ.get("BAKEOFF_DATA", ROOT / "data"))
RESULTS = Path(os.environ.get("BAKEOFF_RESULTS", ROOT / "results"))
LEDGER = ROOT / "ledger.json"
API = "https://openrouter.ai/api/v1/chat/completions"
PROMPT_VERSION = "p1"

SYSTEM = """You triage document pages for a processing pipeline. Look at the page image and report only what you can see.

capture - how the image was produced:
- digital_render: rendered directly from a digital file; perfectly flat, uniform background, no scanner or camera artefacts.
- flatbed_scan: a physical page on a scanner; flat, but with scan noise, grey or uneven paper tone, slight skew, speckles or copier artefacts.
- fax: bilevel (pure black and white) low-resolution image, jagged text, often a fax header line and streaks.
- camera_photo: a photo of a physical page; perspective distortion, curved or warped paper, uneven lighting or shadows, background visible around the page.
- screenshot: a capture of a screen or app UI; window chrome, UI elements, pixel-exact rendering.

legibility - how easy the text is to read for OCR: clean, mild_issues, hard_to_read, illegible.

handwriting:
- none: no handwriting at all.
- annotations_only: printed page with handwritten notes, marks or signatures.
- fields_filled_by_hand: printed form whose fields are filled in by hand.
- mostly_handwritten: the main content is handwritten.

content - true if the page contains at least one: table (rows and columns of cells), math (equations or mathematical notation), form (labelled fields, boxes or checkboxes to fill), code (source code or configuration listing), chart (plot, graph or diagram of data), photo (photographic picture).

script - the main writing system of the text.

Use "unsure" only when the image genuinely does not let you decide."""

SCHEMA = {
    "name": "page_triage",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["capture", "legibility", "handwriting", "content", "script"],
        "properties": {
            "capture": {"type": "string", "enum": ["digital_render", "flatbed_scan", "fax", "camera_photo", "screenshot", "unsure"]},
            "legibility": {"type": "string", "enum": ["clean", "mild_issues", "hard_to_read", "illegible", "unsure"]},
            "handwriting": {"type": "string", "enum": ["none", "annotations_only", "fields_filled_by_hand", "mostly_handwritten", "unsure"]},
            "content": {
                "type": "object",
                "additionalProperties": False,
                "required": ["table", "math", "form", "code", "chart", "photo"],
                "properties": {k: {"type": "boolean"} for k in ["table", "math", "form", "code", "chart", "photo"]},
            },
            "script": {"type": "string", "enum": ["latin", "cyrillic", "greek", "arabic", "hebrew", "cjk", "other", "mixed", "unsure"]},
        },
    },
}


def load_key() -> str:
    for line in (ROOT.parents[1] / ".env").read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("OPENROUTER_API_KEY not found in .env")


class Ledger:
    """Spend shared across runs; every call's cost is added before the next starts."""

    def __init__(self, budget: float):
        self.budget = budget
        self.spent = json.loads(LEDGER.read_text())["spent"] if LEDGER.exists() else 0.0
        self.lock = asyncio.Lock()

    def remaining(self) -> float:
        return self.budget - self.spent

    async def add(self, cost: float):
        async with self.lock:
            self.spent += cost
            LEDGER.write_text(json.dumps({"spent": round(self.spent, 6)}))


def slug(model: str) -> str:
    return model.replace("/", "__").replace("~", "")


def page_ids(spec: str) -> list[str]:
    rows = [json.loads(l) for l in (DATA / "labels.jsonl").read_text().splitlines() if l.strip()]
    ids = [r["id"] for r in rows]
    if spec == "all":
        return ids
    if spec.startswith("sample:"):
        # Stratified by acceptable capture class, fixed seed, so every model sees the same subset.
        n = int(spec.split(":")[1])
        by = {}
        for r in rows:
            by.setdefault(r["capture_ok"][0], []).append(r["id"])
        rng = random.Random(7)
        for v in by.values():
            rng.shuffle(v)
        out, i = [], 0
        while len(out) < min(n, len(ids)):
            for v in by.values():
                if i < len(v) and len(out) < n:
                    out.append(v[i])
            i += 1
        return out
    return [s for s in spec.split(",") if s]


async def call(client, key, model, pid, ledger, sem, reserve):
    out = RESULTS / slug(model) / f"{pid}.json"
    if out.exists() and (lambda r: not r.get("error") and r.get("content") is not None)(json.loads(out.read_text())):
        return  # cached success; transport failures are retried on the next run
    async with sem:
        if ledger.remaining() < reserve:
            print(f"budget stop before {model} {pid} (spent ${ledger.spent:.4f})")
            return
        img = base64.b64encode((DATA / "pages" / f"{pid}.jpg").read_bytes()).decode()
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": [
                    {"type": "text", "text": "Triage this page."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}},
                ]},
            ],
            "response_format": {"type": "json_schema", "json_schema": SCHEMA},
            "provider": {"require_parameters": True},
            "usage": {"include": True},
        }
        rec = {"model": model, "page": pid, "prompt_version": PROMPT_VERSION}
        for attempt in range(6):
            t0 = time.perf_counter()
            try:
                r = await client.post(API, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=300)
                rec["latency_s"] = round(time.perf_counter() - t0, 3)
                rec["status"] = r.status_code
                if r.status_code == 429 or r.status_code >= 500:
                    await asyncio.sleep(2 ** attempt * 5)
                    continue
                j = r.json()
                break
            except (httpx.HTTPError, json.JSONDecodeError) as e:
                rec["error"] = repr(e)
                await asyncio.sleep(2 ** attempt * 3)
        else:
            rec["error"] = rec.get("error") or f"gave up after status {rec.get('status')}"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(rec, indent=1))
            return
        usage = j.get("usage") or {}
        cost = float(usage.get("cost") or 0.0)
        await ledger.add(cost)
        choice = (j.get("choices") or [{}])[0]
        rec.update({
            "provider": j.get("provider"),
            "model_served": j.get("model"),
            "finish_reason": choice.get("finish_reason"),
            "content": (choice.get("message") or {}).get("content"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "cost": cost,
            "api_error": j.get("error"),
        })
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rec, indent=1))
        print(f"{model:45s} {pid:28s} {rec['latency_s']:6.2f}s ${cost:.5f} total ${ledger.spent:.4f}")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True, help="file with one model id per line, or comma list")
    ap.add_argument("--pages", default="all", help="all | sample:N | comma list of ids")
    ap.add_argument("--budget", type=float, default=3.5, help="total USD across all runs (ledger)")
    ap.add_argument("--reserve", type=float, default=0.25, help="stop starting calls below this remaining budget (covers calls in flight)")
    ap.add_argument("--concurrency", type=int, default=8)
    a = ap.parse_args()
    models = Path(a.models).read_text().split() if os.path.exists(a.models) else a.models.split(",")
    models = [m for m in models if m and not m.startswith("#")]
    pids = page_ids(a.pages)
    ledger = Ledger(a.budget)
    print(f"{len(models)} models x {len(pids)} pages; ledger spent ${ledger.spent:.4f} of ${a.budget}")
    key = load_key()
    sem = asyncio.Semaphore(a.concurrency)
    async with httpx.AsyncClient() as client:
        # Interleave models so a budget stop leaves every model with a comparable page count.
        jobs = [call(client, key, m, p, ledger, sem, a.reserve) for p in pids for m in models]
        await asyncio.gather(*jobs)
    print(f"done; ledger spent ${ledger.spent:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
