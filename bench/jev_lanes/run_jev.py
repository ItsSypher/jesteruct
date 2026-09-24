"""Jev as the lane classifier: run every case under three evidence variants, plus baselines.

Variants (what goes into Jev's state):
  v1_probes         structure + image-quality + text statistics, verbalised; no raw text
  v2_probes_text    v1 + a text sample (embedded layer and/or fresh OCR)
  v3_full           v2 + the vision model's answers (Gemini 3.8 Flash), verbalised
Baselines: rules-only, vision-only mapping, and general LLMs given the v3 state as text.

Every request is cached under results/<system>/<run>/<case>.json, so reruns are free.
Usage: uv run --no-project --with httpx python run_jev.py [--runs 2]
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT.parent / "vision_bakeoff"))
from run import load_key

CASES = [json.loads(l) for l in (ROOT / "cases.jsonl").read_text().split("\n") if l.strip()]
# Column estimate from a projection profile of PDF text positions (stand-in for the layout model), see columns.json.
COLUMNS = json.loads((ROOT / "columns.json").read_text()) if (ROOT / "columns.json").exists() else {}
LANES = ["L1", "L2", "L3", "L4", "L5"]
JEV_MODEL = "typesafe/jev-1.13"
CRITERIA_VERSION = "c1"


# ---------------------------------------------------------------- verbalisation (fixed, versioned)

def words_image(q):
    s = []
    s.append("very soft or blurry" if q["sharpness"] < 300 else "somewhat soft" if q["sharpness"] < 1500 else "sharp")
    s.append("low contrast" if q["contrast"] < 25 else "normal contrast")
    if q["border_mean"] < 200:
        s.append("dark or coloured surroundings at the page edges, as when a page is photographed on a surface")
    elif q["border_std"] > 20:
        s.append("uneven or speckled page edges")
    else:
        s.append("clean white page edges")
    s.append("grey or tinted paper background" if q["background_mean"] < 235 else "white paper background")
    s.append("colourful" if q["colour"] > 15 else "some colour" if q["colour"] > 3 else "greyscale")
    if q["noise"] >= 2:
        s.append("visible pixel noise")
    if q["bilevel_share"] > 0.95 and q["contrast"] < 30:
        s.append("almost only pure black and pure white pixels")
    return "Page image: " + ", ".join(s) + "."


def words_text(st, what):
    if st["chars"] == 0:
        return f"{what}: none."
    amount = "only a few words" if st["chars"] < 100 else "a short amount of text" if st["chars"] < 500 else "a full page of text"
    cw = st["common_word_share"]
    read = "reads as normal English prose" if cw >= 0.3 else "partly readable: names, numbers, fragments, or a non-English language" if cw >= 0.1 else "few recognisable English words"
    s = [amount, read]
    if st["cid_share"] > 0.05:
        s.append("contains encoding codes like (cid:NN)")
    if st["odd_char_share"] > 0.05:
        s.append("many unusual or private-use symbols")
    if st["short_token_share"] > 0.35:
        s.append("many one-letter fragments")
    sc = st.get("script") or {}
    if sc:
        top = max(sc, key=sc.get)
        names = {"latin": "Latin letters", "cjk": "Chinese, Japanese or Korean characters", "arabic": "Arabic letters", "cyrillic": "Cyrillic letters", "other": "letters of another script"}
        s.append(f"mostly {names[top]}")
    return f"{what}: " + ", ".join(s) + "."


def words_structure(c):
    if c["input"] == "image":
        return "Input: an image file (JPEG) with no embedded text; any text below comes from a quick English-model OCR pass."
    s = ["Input: a one-page PDF"]
    cov = c["image_coverage"]
    s.append("the page is one full-page image" if cov > 0.9 else "images cover a large part of the page" if cov > 0.3 else "little or no image content")
    if c["invisible_text"] and cov > 0.9:
        s.append("its text layer is invisible text laid over the image, typical of an earlier OCR pass")
    prod = c.get("producer", "")
    if "Tesseract" in prod or "ABBYY" in prod or "img2pdf" in prod:
        s.append(f"made by scanning or OCR software ({prod.split()[0]})")
    if c.get("math_font"):
        s.append("uses mathematical fonts")
    if c.get("mono_font"):
        s.append("uses monospaced fonts")
    col = COLUMNS.get(c["id"], {})
    if col.get("left") is not None:
        gap, lo = col["gutter"], min(col["left"], col["right"])
        s.append("text is laid out in two or more columns" if (gap < 0.3 * lo and lo > 0.3) else "text is in a single column")
    return ", ".join(s) + "."


def words_ocr(c):
    if "ocr_conf" not in c:
        return None
    conf = c["ocr_conf"]
    lvl = "high" if conf >= 0.9 else "medium" if conf >= 0.7 else "low"
    return f"Quick OCR (English model) found {c['ocr_lines']} text lines with {lvl} average confidence."


def words_vlm(v):
    if not v:
        return "Vision check: unavailable."
    flags = [k for k in ("table", "math", "form", "code", "chart", "photo") if (v.get("content") or {}).get(k)]
    return (f"Vision check of the page image: capture looks like {v.get('capture')}; legibility {v.get('legibility')}; "
            f"handwriting {v.get('handwriting')}; contains {', '.join(flags) or 'plain text only'}; main script {v.get('script')}.")


def build_state(c, variant):
    ev = [words_structure(c), words_image(c["iqa"])]
    if c["input"] == "pdf":
        ev.append(words_text(c["stats"], "Embedded text layer"))
    if "ocr_text" in c or c["input"] == "image":
        o = words_ocr(c)
        if o:
            ev.append(o)
        if c["input"] == "image":
            ev.append(words_text(c["stats"], "OCR text"))
    state = {"page_evidence": " ".join(ev)}
    if variant in ("v2_probes_text", "v3_full"):
        if c["input"] == "pdf":
            state["embedded_text_sample"] = (c.get("text") or "")[:1200]
        if c.get("ocr_text") or c["input"] == "image":
            state["ocr_text_sample"] = (c.get("ocr_text") if c["input"] == "pdf" else c.get("text") or "")[:1200]
    if variant == "v3_full":
        state["vision_check"] = words_vlm(c.get("vlm"))
    return state


CRITERIA = {
    "L1": "A real embedded text layer made by the software that created the document (not OCR laid over an image), the text reads normally, and the page is a single column of prose, headings, lists or references with no tables, equations or source code.",
    "L2": "A real embedded text layer as in L1, but the page has tables, equations, source code, or two or more text columns.",
    "L3": "No trustworthy embedded text (an image file, a scan, a PDF whose only text is an OCR layer over an image, or garbled text), and the page image is clean: printed text, flat, sharp, good contrast.",
    "L4": "No trustworthy embedded text, and the page image is degraded: a camera photo, a fax, blur, noise, stains, fading, skew or low contrast.",
    "L5": "Most of the page content is handwritten.",
    "uncertain": "The evidence is not enough to decide.",
}

CRITERIA_C2 = {
    "L5": "Most of the page content is handwritten, whatever the capture type or text layer.",
    "L1": "Not mostly handwritten. A real embedded text layer made by the software that created the document (not OCR laid over an image), the text reads normally, and the page is a single column of prose, headings, lists or references with no tables, equations or source code.",
    "L2": "Not mostly handwritten. A real embedded text layer as in L1, but the page has tables, equations, source code, or two or more text columns.",
    "L3": "Not mostly handwritten. No trustworthy embedded text (an image file, a scan, a PDF whose only text is an OCR layer over an image, or garbled text), and the page image is clean: printed text, flat, sharp, good contrast.",
    "L4": "Not mostly handwritten. No trustworthy embedded text, and the page image is degraded: a camera photo, a fax, blur, noise, stains, fading, skew or low contrast.",
    "uncertain": "The evidence is not enough to decide.",
}

VECTOR_Q = {
    "text_layer_trustworthy": {"type": "noul", "instructions": "The page has a real embedded text layer created with the document (not an OCR layer over an image, not garbled), whose text can be used directly without OCR."},
    "mostly_handwritten": {"type": "noul", "instructions": "Most of the page content is handwritten."},
    "camera_or_fax": {"type": "noul", "instructions": "The page image is a camera photo of a physical page or a fax."},
    "heavily_degraded": {"type": "noul", "instructions": "The page image is clearly degraded for text recognition: blur, strong noise, fading, stains, low contrast or warping."},
    "complex_layout": {"type": "noul", "instructions": "The page has tables, equations, source code, or two or more text columns."},
}


def vector_policy(f):
    """Fixed rule table from Jev's answers to a lane; the lane probability is the product along the decision path."""
    hw, tl, cf, dg, cx = (f.get(k) or 0.0 for k in ("mostly_handwritten", "text_layer_trustworthy", "camera_or_fax", "heavily_degraded", "complex_layout"))
    if hw >= 0.5:
        return "L5", hw
    if tl >= 0.5:
        return ("L2", (1 - hw) * tl * cx) if cx >= 0.5 else ("L1", (1 - hw) * tl * (1 - cx))
    bad = max(cf, dg)
    return ("L4", (1 - hw) * (1 - tl) * bad) if bad >= 0.5 else ("L3", (1 - hw) * (1 - tl) * (1 - bad))


QUESTIONS = {
    "lane": {"type": "choice", "instructions": "Using `page_evidence` and any samples or checks provided, which processing lane fits this page?", "criteria": CRITERIA},
    "text_layer_trustworthy": {"type": "noul", "instructions": "The page has a real embedded text layer created with the document, whose text can be used directly without OCR."},
    "has_table": {"type": "noul", "instructions": "The page contains at least one table."},
    "has_math": {"type": "noul", "instructions": "The page contains mathematical equations or notation."},
    "has_code": {"type": "noul", "instructions": "The page contains source code or a configuration listing."},
    "has_handwriting": {"type": "noul", "instructions": "The page contains any handwriting: notes, signatures, filled-in fields or handwritten text."},
    "is_form": {"type": "noul", "instructions": "The page is a form with labelled fields or boxes to fill in."},
    "degradation": {"type": "score", "instructions": "How degraded is the page image for text recognition?",
                    "criteria": ["Clean: flat, sharp, good contrast", "Mild: slight noise, tint or softness", "Heavy: photo distortion, fax artefacts, strong noise or fading", "Severe: large parts hard to read"]},
}


# ---------------------------------------------------------------- systems

async def jev(client, key, c, variant, mode="choice"):
    if mode == "choice":
        qs = QUESTIONS
    elif mode == "c2":
        qs = {**QUESTIONS, "lane": {**QUESTIONS["lane"], "criteria": CRITERIA_C2}}
    else:
        qs = VECTOR_Q
    body = {"model": JEV_MODEL, "state": build_state(c, variant), "questions": qs}
    t0 = time.perf_counter()
    for attempt in range(5):
        r = await client.post("https://openrouter.ai/api/alpha/decisions", json=body, headers={"Authorization": f"Bearer {key}"}, timeout=120)
        if r.status_code == 200:
            break
        await asyncio.sleep(2 ** attempt * 2)
    j = r.json()
    a = j.get("answers") or {}
    if mode == "vector":
        flags = {k: (a.get(k) or {}).get("noul") for k in VECTOR_Q}
        lane, p = vector_policy(flags)
        return {"lane": lane, "lane_probs": {lane: p}, "flags": flags, "degradation": None,
                "latency_s": round(time.perf_counter() - t0, 3), "cost": (j.get("usage") or {}).get("cost"),
                "model": j.get("model"), "status": r.status_code, "error": None if r.status_code == 200 else r.text[:300]}
    lane = (a.get("lane") or {}).get("choice")
    return {"lane": lane, "lane_probs": (a.get("lane") or {}).get("probabilities"),
            "flags": {k: (a.get(k) or {}).get("noul") for k in QUESTIONS if QUESTIONS[k]["type"] == "noul"},
            "degradation": (a.get("degradation") or {}).get("score"),
            "latency_s": round(time.perf_counter() - t0, 3), "cost": (j.get("usage") or {}).get("cost"),
            "model": j.get("model"), "status": r.status_code, "error": None if r.status_code == 200 else r.text[:300]}


LLM_SCHEMA = {"name": "lane", "strict": True, "schema": {"type": "object", "additionalProperties": False,
              "required": ["lane", "text_layer_trustworthy", "has_table", "has_math", "has_code", "has_handwriting", "is_form", "degradation"],
              "properties": {"lane": {"type": "string", "enum": LANES + ["uncertain"]},
                             **{k: {"type": "boolean"} for k in ["text_layer_trustworthy", "has_table", "has_math", "has_code", "has_handwriting", "is_form"]},
                             "degradation": {"type": "integer", "minimum": 0, "maximum": 3}}}}


async def llm(client, key, c, model, criteria=None):
    criteria = criteria or CRITERIA
    state = build_state(c, "v3_full")
    prompt = ("Classify this document page into a processing lane from the evidence below.\n\nLanes:\n" +
              "\n".join(f"- {k}: {v}" for k, v in criteria.items()) +
              "\n\nAlso answer: text_layer_trustworthy, has_table, has_math, has_code, has_handwriting, is_form (booleans) and degradation 0-3 (0 clean, 3 severe).\n\nEvidence:\n" +
              json.dumps(state, ensure_ascii=False, indent=1))
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_schema", "json_schema": LLM_SCHEMA},
            "provider": {"require_parameters": True}, "usage": {"include": True}}
    t0 = time.perf_counter()
    for attempt in range(5):
        r = await client.post("https://openrouter.ai/api/v1/chat/completions", json=body, headers={"Authorization": f"Bearer {key}"}, timeout=300)
        if r.status_code == 200:
            break
        await asyncio.sleep(2 ** attempt * 2)
    j = r.json()
    try:
        a = json.loads(j["choices"][0]["message"]["content"])
    except Exception:
        a = {}
    return {"lane": a.get("lane"), "lane_probs": None, "flags": {k: (None if a.get(k) is None else float(a[k])) for k in ["text_layer_trustworthy", "has_table", "has_math", "has_code", "has_handwriting", "is_form"]},
            "degradation": a.get("degradation"), "latency_s": round(time.perf_counter() - t0, 3), "cost": (j.get("usage") or {}).get("cost"),
            "model": j.get("model"), "status": r.status_code, "error": None if a else str(j)[:300]}


def rules(c):
    st, q = c["stats"], c["iqa"]
    real_text = (c["input"] == "pdf" and st["chars"] > 50 and not (c["invisible_text"] and c["image_coverage"] > 0.9)
                 and st["common_word_share"] >= 0.1 and st["cid_share"] < 0.05 and st["odd_char_share"] < 0.05)
    if real_text:
        digits = sum(ch.isdigit() for ch in (c.get("text") or "")) / max(1, len(c.get("text") or ""))
        lane = "L2" if (c.get("math_font") or c.get("mono_font") or digits > 0.12) else "L1"
    else:
        conf = c.get("ocr_conf", 1.0)
        common = (c["stats"] if c["input"] == "image" else {"common_word_share": 1}).get("common_word_share", 1)
        if conf < 0.7 and common < 0.1:
            lane = "L5"
        elif q["border_mean"] < 200 or q["sharpness"] < 300 or q["background_mean"] < 235 or q["noise"] >= 2:
            lane = "L4"
        else:
            lane = "L3"
    return {"lane": lane, "flags": {"text_layer_trustworthy": float(real_text)}, "latency_s": 0.0, "cost": 0.0}


def vision_only(c):
    v = c.get("vlm") or {}
    base = rules(c)
    if base["flags"]["text_layer_trustworthy"]:
        cont = v.get("content") or {}
        return {**base, "lane": "L2" if (cont.get("table") or cont.get("math") or cont.get("code")) else "L1"}
    if v.get("handwriting") == "mostly_handwritten":
        lane = "L5"
    elif v.get("capture") in ("camera_photo", "fax") or v.get("legibility") in ("hard_to_read", "illegible", "mild_issues"):
        lane = "L4"
    else:
        lane = "L3"
    return {**base, "lane": lane}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--llms", default="openai/gpt-6-luna,google/gemini-3.8-flash")
    a = ap.parse_args()
    key = load_key()
    sem = asyncio.Semaphore(12)
    async with httpx.AsyncClient() as client:
        async def job(system, run, c, fn):
            out = ROOT / "results" / system / f"run{run}" / f"{c['id']}.json"
            if out.exists():
                return
            async with sem:
                rec = await fn()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps({"case": c["id"], "system": system, "run": run, **rec}))
        jobs = []
        for run in range(1, a.runs + 1):
            for c in CASES:
                for v in ("v1_probes", "v2_probes_text", "v3_full"):
                    jobs.append(job(f"jev_{v}", run, c, lambda c=c, v=v: jev(client, key, c, v)))
        for m in a.llms.split(","):
            for c in CASES:
                jobs.append(job("llm_" + m.split("/")[1], 1, c, lambda c=c, m=m: llm(client, key, c, m)))
                jobs.append(job("llm_" + m.split("/")[1] + "_c2", 1, c, lambda c=c, m=m: llm(client, key, c, m, CRITERIA_C2)))
        for run in range(1, a.runs + 1):
            for c in CASES:
                jobs.append(job("jev_c2", run, c, lambda c=c: jev(client, key, c, "v3_full", "c2")))
                jobs.append(job("jev_vector", run, c, lambda c=c: jev(client, key, c, "v3_full", "vector")))
                jobs.append(job("jev_vector_novision", run, c, lambda c=c: jev(client, key, c, "v2_probes_text", "vector")))
        await asyncio.gather(*jobs)
    for c in CASES:
        for system, fn in (("rules", rules), ("vision_only", vision_only)):
            out = ROOT / "results" / system / "run1" / f"{c['id']}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps({"case": c["id"], "system": system, "run": 1, **fn(c)}))
    # Keep a copy of the exact states sent, for inspection.
    with open(ROOT / "states_v3.jsonl", "w") as f:
        for c in CASES:
            f.write(json.dumps({"id": c["id"], "gt": c["gt"], "state": build_state(c, "v3_full")}, ensure_ascii=False) + "\n")
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
