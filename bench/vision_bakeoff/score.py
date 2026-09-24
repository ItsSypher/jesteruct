"""Score bake-off results against labels.jsonl and write report.md + scores.csv.

Axes are scored only where the label is known (not null). Composite is the mean
of per-axis accuracies, so no axis dominates by page count. Invalid JSON and
"unsure" answers count as wrong, and are also reported separately. Intervals are
a page-level bootstrap. Models are compared on the pages they all share, so a
model with a smaller page set does not skew the comparison.

Usage: uv run --no-project python score.py
"""

import csv
import json
import random
import statistics
from pathlib import Path

import os
ROOT = Path(__file__).parent
DATA = Path(os.environ.get("BAKEOFF_DATA", ROOT / "data"))
RESULTS = Path(os.environ.get("BAKEOFF_RESULTS", ROOT / "results"))
LABELS = {r["id"]: r for r in (json.loads(l) for l in (DATA / os.environ.get("BAKEOFF_LABELS", "labels.jsonl")).read_text().splitlines() if l.strip())}
HW = {"none": "none", "annotations_only": "some", "fields_filled_by_hand": "some", "mostly_handwritten": "mostly"}
FLAGS = ["table", "math", "form", "code", "chart", "photo"]


def parse(rec, lenient=False):
    """Strict: the content must be exactly the schema's JSON object.
    Lenient: also unwrap code fences and a one-element list, to separate task skill from format compliance."""
    text = rec.get("content") or ""
    if lenient:
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        v = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if lenient and isinstance(v, list) and len(v) == 1:
        v = v[0]
    return v if isinstance(v, dict) else None


def transport_error(rec):
    return bool(rec.get("error")) or rec.get("status") not in (200, "200", None) or rec.get("content") is None


def page_scores(pred, lab):
    """Per-axis 1/0 for one page; None where the label is unknown."""
    s = {}
    s["capture"] = None if not lab.get("capture_ok") else float(bool(pred) and pred.get("capture") in lab["capture_ok"])
    if lab.get("legibility"):
        got = None if not pred else ("clean" if pred.get("legibility") == "clean" else "degraded" if pred.get("legibility") in ("mild_issues", "hard_to_read", "illegible") else None)
        s["legibility"] = float(got == lab["legibility"])
    else:
        s["legibility"] = None
    s["handwriting"] = None if not lab.get("handwriting") else float(bool(pred) and HW.get(pred.get("handwriting")) == lab["handwriting"])
    s["script"] = None if not lab.get("script") else float(bool(pred) and pred.get("script") == lab["script"])
    c = lab.get("content") or {}
    known = [f for f in FLAGS if c.get(f) is not None]
    if known:
        pc = (pred or {}).get("content") or {}
        s["content"] = sum(float(pc.get(f) is c[f]) for f in known) / len(known)
    else:
        s["content"] = None
    return s


AXES = ["capture", "legibility", "handwriting", "content", "script"]
# Legibility is reported but kept out of the composite: its labels mean image degradation, while the prompt asks
# about OCR difficulty, so handwriting pages disagree by definition. Fix the definition before scoring it.
COMPOSITE_AXES = ["capture", "handwriting", "content", "script"]


def composite(rows):
    per = {a: [r[a] for r in rows if r[a] is not None] for a in AXES}
    accs = [sum(per[a]) / len(per[a]) for a in COMPOSITE_AXES if per[a]]
    return sum(accs) / len(accs) if accs else float("nan"), {a: (sum(v) / len(v) if v else None) for a, v in per.items()}


def boot(rows, n=1000, seed=3):
    rng = random.Random(seed)
    vals = sorted(composite([rows[rng.randrange(len(rows))] for _ in rows])[0] for _ in range(n))
    return vals[int(0.025 * n)], vals[int(0.975 * n)]


def main():
    models = {}
    for d in sorted(RESULTS.iterdir()):
        recs = [json.loads(p.read_text()) for p in d.glob("*.json")]
        if recs:
            models[recs[0]["model"]] = {r["page"]: r for r in recs if r["page"] in LABELS}
    # The shared set is the pages answered by every model with at least 80% coverage of the largest page set,
    # so one rate-limited provider cannot shrink the comparison for everyone. Low-coverage models are flagged.
    ok = {m: {pid for pid, r in v.items() if not transport_error(r)} for m, v in models.items()}
    biggest = max((len(x) for x in ok.values()), default=0)
    core = [x for x in ok.values() if biggest and len(x) >= 0.8 * biggest]
    shared = set.intersection(*core) if core else set()
    low_coverage = sorted(m for m, x in ok.items() if x and len(x) < 0.8 * biggest)
    out = []
    for m, recs in models.items():
        errors = sum(transport_error(r) for r in recs.values())
        recs = {pid: r for pid, r in recs.items() if not transport_error(r)}
        if not recs:
            out.append({"model": m, "pages": 0, "errors": errors})
            continue
        lenient_rows = [page_scores(parse(r, lenient=True), LABELS[pid]) for pid, r in recs.items()]
        rows, valid, unsure, lat, cost, rtok, ctok = [], 0, 0, [], [], [], []
        for pid, rec in recs.items():
            pred = parse(rec)
            valid += pred is not None
            unsure += bool(pred) and "unsure" in json.dumps(pred)
            if rec.get("latency_s") is not None and pred is not None:
                lat.append(rec["latency_s"])
            cost.append(rec.get("cost") or 0.0)
            rtok.append(rec.get("reasoning_tokens") or 0)
            ctok.append(rec.get("completion_tokens") or 0)
            rows.append((pid, page_scores(pred, LABELS[pid])))
        allrows = [s for _, s in rows]
        sh = [s for pid, s in rows if pid in shared]
        comp, axes = composite(allrows)
        comp_sh = composite(sh)[0] if sh else float("nan")
        lo, hi = boot(sh) if len(sh) >= 10 else (float("nan"), float("nan"))
        n = len(recs)
        out.append({
            "model": m,
            "pages": n,
            "valid_json": f"{valid}/{n}",
            "errors": errors,
            "composite_all": round(comp, 3),
            "composite_lenient": round(composite(lenient_rows)[0], 3),
            "composite_shared": round(comp_sh, 3),
            "ci95_shared": f"{lo:.3f}-{hi:.3f}",
            **{f"acc_{a}": (round(v, 3) if v is not None else "") for a, v in axes.items()},
            "unsure_rate": round(unsure / n, 3),
            "p50_s": round(statistics.median(lat), 2) if lat else "",
            "p95_s": round(sorted(lat)[max(0, int(0.95 * len(lat)) - 1)], 2) if lat else "",
            "usd_per_1k_pages": round(1000 * sum(cost) / n, 3),
            "mean_reasoning_tokens": round(sum(rtok) / n),
            "mean_completion_tokens": round(sum(ctok) / n),
            "provider": sorted({(r.get("provider") or "?") for r in recs.values()}),
        })
    failed = [r for r in out if not r.get("pages")]
    out = [r for r in out if r.get("pages")]
    out.sort(key=lambda r: -r["composite_shared"])
    # Pareto frontiers on the shared pages: no other model is both at least as good and cheaper (or faster).
    for key in ("usd_per_1k_pages", "p50_s"):
        for r in out:
            r[f"pareto_{key}"] = r[key] != "" and not any(
                o is not r and o[key] != "" and o["composite_shared"] >= r["composite_shared"] and o[key] <= r[key]
                and (o["composite_shared"] > r["composite_shared"] or o[key] < r[key]) for o in out)
    with open(ROOT / os.environ.get("BAKEOFF_CSV", "scores.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    cols = ["model", "pages", "errors", "valid_json", "composite_lenient", "composite_shared", "ci95_shared", "acc_capture", "acc_legibility", "acc_handwriting", "acc_content", "acc_script", "p50_s", "p95_s", "usd_per_1k_pages", "mean_reasoning_tokens", "pareto_usd_per_1k_pages", "pareto_p50_s"]
    lines = [f"# Vision arbiter bake-off\n", f"Shared pages across all models: {len(shared)}.\n", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in out:
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    if low_coverage:
        lines.append(f"\nLow coverage (under 80% of pages answered; composite_shared not comparable): {', '.join(low_coverage)}.")
    for r in failed:
        lines.append(f"\nNo successful calls: {r['model']} ({r['errors']} transport errors).")
    (ROOT / os.environ.get("BAKEOFF_REPORT", "scores_table.md")).write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
