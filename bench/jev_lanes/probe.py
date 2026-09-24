"""Build the Jev lane-classification test cases: evidence (what the router's probes would see) plus ground-truth lanes.

Cases:
  img_*   the 60 labelled page images from ../vision_bakeoff/data, as image inputs (no text layer)
  pdf_*   born-digital (or book-scan) single-page PDFs with whatever text layer they carry
  ocr_*   page images wrapped by Tesseract into PDFs with an invisible OCR text layer
  garb_*  born-digital PDFs whose extracted text is replaced by a garbled layer (evidence-level synthetic)

Ground truth lanes come from gt_lanes() below, a fixed written mapping from labels to lanes.
Writes cases.jsonl. Usage: uv run --no-project --with pypdfium2 --with pikepdf --with ocrmac --with opencv-python-headless --with numpy --with pillow --with httpx python probe.py
"""

import base64
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import cv2
import httpx
import numpy as np
import pikepdf
import pypdfium2 as pdfium
from ocrmac import ocrmac

ROOT = Path(__file__).parent
VB = ROOT.parent / "vision_bakeoff"
sys.path.insert(0, str(VB))
from run import SCHEMA, SYSTEM, load_key  # same visual-evidence prompt as the bake-off

LANES = ["L1", "L2", "L3", "L4", "L5"]
LABELS = {json.loads(l)["id"]: json.loads(l) for l in (VB / "data/labels.jsonl").read_text().splitlines() if l.strip()}

# Hand labels for the 12 extra olmOCR PDFs (visual check of the contact sheet, 2026-09-24).
EXTRA = {
    "olmx_01": dict(desc="colourful weekly TV schedule grid", table=True, multicol=True, math=False, code=False, hw="none", scan=False, degraded=False),
    "olmx_02": dict(desc="presentation slide with bullets", table=False, multicol=False, math=False, code=False, hw="none", scan=False, degraded=False),
    "olmx_03": dict(desc="journal reference list page", table=False, multicol=False, math=False, code=False, hw="none", scan=False, degraded=False),
    "olmx_04": dict(desc="two-column old encyclopedia page scan", table=False, multicol=True, math=False, code=False, hw="none", scan=True, degraded=False),
    "olmx_05": dict(desc="two-column old encyclopedia page scan", table=False, multicol=True, math=False, code=False, hw="none", scan=True, degraded=False),
    "olmx_06": dict(desc="three-column old dictionary page scan", table=False, multicol=True, math=False, code=False, hw="none", scan=True, degraded=False),
    "olmx_07": dict(desc="yellowed two-page book spread photo", table=False, multicol=True, math=False, code=False, hw="none", scan=True, degraded=True),
    "olmx_08": dict(desc="single-column journal prose", table=False, multicol=False, math=False, code=False, hw="none", scan=False, degraded=False),
    "olmx_09": dict(desc="thesis reference list", table=False, multicol=False, math=False, code=False, hw="none", scan=False, degraded=False),
    "olmx_10": dict(desc="report cover page with logos", table=False, multicol=False, math=False, code=False, hw="none", scan=False, degraded=False),
    "olmx_11": dict(desc="two-column prose article", table=False, multicol=True, math=False, code=False, hw="none", scan=False, degraded=False),
    "olmx_12": dict(desc="single-column journal page", table=False, multicol=False, math=False, code=False, hw="none", scan=False, degraded=False),
}


# ---------------------------------------------------------------- ground truth

def gt_lanes(text_layer, lab):
    """Acceptable lanes for a case.

    text_layer: 'trusted' (real born-digital text), or anything else (none / ocr layer / garbled), meaning OCR is needed.
    lab: dict with hw ('none'|'some'|'mostly'|None), complex (bool|None), degraded (True|False|None).
    """
    if lab.get("hw") == "mostly":
        return ["L5"]
    if text_layer == "trusted":
        if lab.get("complex") is None:
            return ["L1", "L2"]
        return ["L2"] if lab["complex"] else ["L1"]
    if lab.get("degraded") is None:
        return ["L3", "L4"]
    return ["L4"] if lab["degraded"] else ["L3"]


def image_lab(l):
    caps = set(l["capture_ok"])
    hard = {"fax", "camera_photo"}
    if l.get("legibility") == "degraded" or caps <= hard:
        degraded = True
    elif l.get("legibility") == "clean" and not (caps & hard):
        degraded = False
    else:
        degraded = None
    c = l.get("content") or {}
    return {"hw": l.get("handwriting"), "degraded": degraded,
            "complex": None if any(c.get(k) is None for k in ("table", "math", "code")) else bool(c.get("table") or c.get("math") or c.get("code"))}


# ---------------------------------------------------------------- probes

def iqa(img_bgr):
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim == 3 else img_bgr
    h, w = g.shape
    b = max(4, int(0.03 * min(h, w)))
    border = np.concatenate([g[:b].ravel(), g[-b:].ravel(), g[:, :b].ravel(), g[:, -b:].ravel()])
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV) if img_bgr.ndim == 3 else None
    return {
        "sharpness": float(cv2.Laplacian(g, cv2.CV_64F).var()),
        "contrast": float(g.std()),
        "noise": float(np.median(np.abs(g.astype(np.int16) - cv2.medianBlur(g, 3)))),
        "bilevel_share": float(((g <= 30) | (g >= 225)).mean()),
        "background_mean": float(np.percentile(g, 90)),
        "border_mean": float(border.mean()),
        "border_std": float(border.std()),
        "colour": float(hsv[..., 1].mean()) if hsv is not None else 0.0,
    }


def ocr(path):
    r = ocrmac.OCR(str(path), recognition_level="accurate", language_preference=["en-US"]).recognize()
    text = "\n".join(x[0] for x in r)
    return text, (sum(x[1] for x in r) / len(r) if r else 0.0), len(r)


WORD = re.compile(r"[A-Za-z]{2,}")
COMMON = set("the of and to in a is that for it as was with be by on not he this are or his from at which but have an they you were her she there been one all we their has would when who will more if no out so said what up its about into than them can only other new some could time these two may then do first any my now such like our over man me even most made after also did many before must through back years where much your way well down should because each just those people how too little state good very make world still own see men work long get here between both life being under never day same another know while last might us great old year off come since against go came right used take three".split())


def text_stats(t):
    toks = t.split()
    words = WORD.findall(t)
    n = max(1, len(t))
    scripts = {"latin": 0, "cjk": 0, "arabic": 0, "cyrillic": 0, "other": 0}
    for ch in t:
        if not ch.isalpha():
            continue
        name = unicodedata.name(ch, "")
        k = "latin" if "LATIN" in name else "cjk" if ("CJK" in name or "HIRAGANA" in name or "KATAKANA" in name or "HANGUL" in name) else "arabic" if "ARABIC" in name else "cyrillic" if "CYRILLIC" in name else "other"
        scripts[k] += 1
    alpha = sum(scripts.values()) or 1
    return {
        "chars": len(t.strip()),
        "cid_share": len(re.findall(r"\(cid:\d+\)", t)) * 7 / n,
        "odd_char_share": sum(1 for ch in t if unicodedata.category(ch) in ("Co", "Cn", "So") or ch == "�") / n,
        "short_token_share": sum(len(x) < 2 for x in toks) / max(1, len(toks)),
        "common_word_share": sum(w.lower() in COMMON for w in words) / max(1, len(words)),
        "script": {k: round(v / alpha, 2) for k, v in scripts.items() if v},
    }


def pdf_probe(path):
    doc = pdfium.PdfDocument(str(path))
    page = doc[0]
    w, h = page.get_size()
    text = page.get_textpage().get_text_range()
    img_area = 0.0
    for obj in page.get_objects(max_depth=2):
        if obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE:
            l, b, r, t = obj.get_bounds()
            img_area += max(0, r - l) * max(0, t - b)
    pk = pikepdf.open(str(path))
    p0 = pk.pages[0]
    contents = p0.obj.get("/Contents")
    streams = contents if isinstance(contents, pikepdf.Array) else [contents] if contents is not None else []
    cs = b"".join(s.read_bytes() for s in streams)
    fonts = []
    try:
        for _, f in (p0.obj.Resources.get("/Font") or {}).items():
            fonts.append(str(f.get("/BaseFont", "")))
    except Exception:
        pass
    return {
        "text": text,
        "image_coverage": min(1.0, img_area / (w * h)),
        "invisible_text": bool(re.search(rb"(^|\s)3\s+Tr\b", cs)),
        "producer": str(pk.docinfo.get("/Producer", "")) if pk.docinfo else "",
        "fonts": fonts[:12],
        "math_font": any(re.search(r"CMMI|CMSY|CMEX|Math|STIX|MSBM", f) for f in fonts),
        "mono_font": any(re.search(r"Courier|Mono|Consol|Menlo|CMTT", f, re.I) for f in fonts),
        "size_pt": [round(w), round(h)],
    }


def render(path, out):
    pg = pdfium.PdfDocument(str(path))[0]
    w, h = pg.get_size()
    pg.render(scale=1024 / max(w, h)).to_pil().convert("RGB").save(out, quality=90)


def vlm(path, cache):
    """Visual evidence from the bake-off's default arbiter (Gemini 3.8 Flash), cached per image."""
    if cache.exists():
        return json.loads(cache.read_text())
    img = base64.b64encode(Path(path).read_bytes()).decode()
    body = {"model": "google/gemini-3.8-flash", "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": [{"type": "text", "text": "Triage this page."},
                                     {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}}]}],
        "response_format": {"type": "json_schema", "json_schema": SCHEMA}, "provider": {"require_parameters": True}, "usage": {"include": True}}
    r = httpx.post("https://openrouter.ai/api/v1/chat/completions", json=body, headers={"Authorization": f"Bearer {load_key()}"}, timeout=300).json()
    ans = json.loads(r["choices"][0]["message"]["content"])
    ans["_cost"] = r.get("usage", {}).get("cost")
    cache.parent.mkdir(exist_ok=True)
    cache.write_text(json.dumps(ans))
    return ans


def bakeoff_vlm(pid):
    f = VB / "results/google__gemini-3.8-flash" / f"{pid}.json"
    try:
        return json.loads(json.loads(f.read_text())["content"])
    except Exception:
        return None


# ---------------------------------------------------------------- garbling (evidence-level synthetic)

def garble(t, kind):
    if kind == "cid":
        return "".join(f"(cid:{ord(c) % 97 + 3})" if c.isalpha() else c for c in t)
    if kind == "shift":  # glyph ids without a ToUnicode map often come out as a constant offset
        return "".join(chr(ord(c) + 29) if c.isalpha() else c for c in t)
    if kind == "mojibake":
        return t.encode("utf-8").decode("latin-1", errors="replace").replace("e", "Ã©").replace("a", "")
    raise ValueError(kind)


# ---------------------------------------------------------------- build

def main():
    out = []
    pages = ROOT / "pages"
    pages.mkdir(exist_ok=True)
    vcache = ROOT / "vlm_cache"

    # 1) image inputs
    for pid, l in LABELS.items():
        path = VB / "data/pages" / f"{pid}.jpg"
        text, conf, lines = ocr(path)
        out.append({"id": f"img_{pid}", "input": "image", "text_layer": "none", "image": str(path),
                    "iqa": iqa(cv2.imread(str(path))), "text": text, "ocr_conf": conf, "ocr_lines": lines,
                    "stats": text_stats(text), "vlm": bakeoff_vlm(pid), "gt": gt_lanes("none", image_lab(l)), "lab": image_lab(l)})

    # 2) PDFs: born-digital from the bake-off set, code pages and the extras
    pdfs = []
    for pid, l in LABELS.items():
        src = l.get("source", "")
        m = re.search(r"bench_data/pdfs/(tables|multi_column|arxiv_math)/([^\s)]+\.pdf)", src)
        if m:
            f = next((VB / "data/raw/olmocr_pdfs" / m.group(1)).glob(Path(m.group(2)).name), None)
            if f:
                c = l.get("content") or {}
                lab = {"hw": "none", "complex": bool(c.get("table") or c.get("math") or c.get("code") or m.group(1) == "multi_column"), "degraded": False,
                       "scan": "flatbed_scan" in l["capture_ok"]}  # e.g. olmocr_tables_01/02 are scans carrying an OCR layer
                pdfs.append((f"pdf_{pid}", f, lab))
    for i, f in enumerate(sorted((VB / "data/raw/synthetic/code").glob("*.pdf"))):
        pdfs.append((f"pdf_code_{i+1:02d}", f, {"hw": "none", "complex": True, "degraded": False}))
    for i, f in enumerate(sorted((ROOT / "raw/olmocr_extra").glob("*.pdf"))):
        e = EXTRA[f"olmx_{i+1:02d}"]
        pdfs.append((f"pdf_olmx_{i+1:02d}", f, {"hw": e["hw"], "complex": e["table"] or e["math"] or e["code"] or e["multicol"], "degraded": e["degraded"], "scan": e["scan"]}))

    for cid, f, lab in pdfs:
        pr = pdf_probe(f)
        img = pages / f"{cid}.jpg"
        render(f, img)
        st = text_stats(pr["text"])
        # A page is a scan whatever its text layer if it is mostly one image; its text layer is then an OCR layer.
        is_scan = lab.get("scan", False)
        tl = "trusted" if (st["chars"] > 50 and not is_scan) else ("untrusted_ocr_layer" if st["chars"] > 50 else "none")
        rec = {"id": cid, "input": "pdf", "pdf": str(f), "image": str(img), **{k: pr[k] for k in ("image_coverage", "invisible_text", "producer", "math_font", "mono_font")},
               "iqa": iqa(cv2.imread(str(img))), "text": pr["text"], "stats": st, "vlm": vlm(img, vcache / f"{cid}.json"),
               "text_layer_truth": tl, "gt": gt_lanes(tl, lab), "lab": lab}
        if tl != "trusted":  # the router OCRs pages whose text layer it cannot trust
            text, conf, lines = ocr(img)
            rec.update({"ocr_text": text, "ocr_conf": conf, "ocr_lines": lines})
        out.append(rec)

    # 3) Tesseract OCR-layer PDFs made from page images
    for pid in ["olmocr_oldscans_02", "olmocr_oldscans_04", "funsd_03", "funsd_04", "pdb_jacs_digital", "pdb_bankrisk_clean", "synth_fax_02", "gnhk_02"]:
        img = VB / "data/pages" / f"{pid}.jpg"
        base = pages / f"ocr_{pid}"
        subprocess.run(["tesseract", str(img), str(base), "-l", "eng", "--dpi", "150", "pdf"], check=True, capture_output=True)
        pr = pdf_probe(f"{base}.pdf")
        text, conf, lines = ocr(img)
        l = LABELS[pid]
        out.append({"id": f"ocr_{pid}", "input": "pdf", "pdf": f"{base}.pdf", "image": str(img),
                    **{k: pr[k] for k in ("image_coverage", "invisible_text", "producer", "math_font", "mono_font")},
                    "iqa": iqa(cv2.imread(str(img))), "text": pr["text"], "stats": text_stats(pr["text"]),
                    "ocr_text": text, "ocr_conf": conf, "ocr_lines": lines, "vlm": bakeoff_vlm(pid),
                    "text_layer_truth": "untrusted_ocr_layer", "gt": gt_lanes("ocr", image_lab(l)), "lab": image_lab(l)})

    # 4) garbled text layers over clean born-digital pages
    for (src_id, kind) in [("pdf_olmx_08", "cid"), ("pdf_olmx_12", "shift"), ("pdf_olmx_03", "mojibake"),
                           ("pdf_olmocr_multicol_01", "shift"), ("pdf_olmocr_arxivmath_01", "cid")]:
        src = next((r for r in out if r["id"] == src_id), None)
        if not src:
            continue
        g = garble(src["text"], kind)
        text, conf, lines = ocr(src["image"])
        out.append({**src, "id": f"garb_{src_id[4:]}_{kind}", "text": g, "stats": text_stats(g),
                    "ocr_text": text, "ocr_conf": conf, "ocr_lines": lines, "text_layer_truth": "garbled",
                    "gt": gt_lanes("garbled", {**src["lab"], "degraded": False}), "synthetic_evidence": True})

    with open(ROOT / "cases.jsonl", "w") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print(len(out), "cases;", Counter(r["id"].split("_")[0] for r in out), Counter(tuple(r["gt"]) for r in out))


if __name__ == "__main__":
    main()
