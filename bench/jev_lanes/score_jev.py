"""Score run_jev.py results. Writes scores_table.md. Usage: uv run --no-project python score_jev.py"""

import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
CASES = {c["id"]: c for c in (json.loads(l) for l in (ROOT / "cases.jsonl").read_text().split("\n") if l.strip())}
RANK = {"L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5}


def load(system, run):
    d = ROOT / "results" / system / f"run{run}"
    return {json.loads(f.read_text())["case"]: json.loads(f.read_text()) for f in d.glob("*.json")} if d.exists() else {}


def group(cid):
    return cid.split("_")[0]


def tl_truth(c):
    return c.get("text_layer_truth", "none") == "trusted"


def lane_metrics(res):
    n = ok = abst = under = over = err = 0
    by = defaultdict(lambda: [0, 0])
    wrong = []
    for cid, c in CASES.items():
        r = res.get(cid)
        if not r or r.get("error") or r.get("lane") is None:
            err += 1
            continue
        n += 1
        lane, gt = r["lane"], c["gt"]
        g = group(cid)
        by[g][1] += 1
        if lane == "uncertain":
            abst += 1
            continue
        if lane in gt:
            ok += 1
            by[g][0] += 1
        else:
            wrong.append((cid, lane, gt))
            if RANK[lane] < min(RANK[x] for x in gt):
                under += 1
            elif RANK[lane] > max(RANK[x] for x in gt):
                over += 1
    return {"n": n, "errors": err, "acc": ok / n if n else 0, "abstain": abst / n if n else 0, "under": under / n if n else 0,
            "over": over / n if n else 0, "by_group": {g: f"{a}/{t}" for g, (a, t) in sorted(by.items())}, "wrong": wrong}


def tl_acc(res):
    v = [(r["flags"].get("text_layer_trustworthy") or 0) >= 0.5 for cid, r in res.items() if r.get("flags") and r["flags"].get("text_layer_trustworthy") is not None]
    t = [tl_truth(CASES[cid]) for cid, r in res.items() if r.get("flags") and r["flags"].get("text_layer_trustworthy") is not None]
    return sum(a == b for a, b in zip(v, t)) / len(v) if v else None


def calibration(res):
    """For Jev: probability of the chosen lane vs being right; selective accuracy when p < tau goes to review."""
    pts = []
    for cid, r in res.items():
        p = (r.get("lane_probs") or {}).get(r.get("lane"))
        if p is None or r.get("lane") == "uncertain":
            continue
        pts.append((p, r["lane"] in CASES[cid]["gt"]))
    if not pts:
        return None
    out = {"mean_p_right": statistics.mean([p for p, ok in pts if ok] or [0]), "mean_p_wrong": statistics.mean([p for p, ok in pts if not ok] or [0])}
    for tau in (0.5, 0.7, 0.9, 0.99):
        kept = [ok for p, ok in pts if p >= tau]
        out[f"tau{tau}"] = f"acc {sum(kept)/len(kept):.3f} on {len(kept)}/{len(pts)}" if kept else "none kept"
    bins = defaultdict(list)
    for p, ok in pts:
        bins[min(9, int(p * 10))].append((p, ok))
    out["ece"] = sum(len(v) / len(pts) * abs(statistics.mean(p for p, _ in v) - statistics.mean(ok for _, ok in v)) for v in bins.values())
    return out


def agreement(a, b):
    ids = [i for i in a if i in b and a[i].get("lane") and b[i].get("lane")]
    same = sum(a[i]["lane"] == b[i]["lane"] for i in ids)
    dp = [abs((a[i].get("lane_probs") or {}).get(a[i]["lane"], 0) - (b[i].get("lane_probs") or {}).get(a[i]["lane"], 0)) for i in ids]
    return same / len(ids) if ids else None, (statistics.mean(dp) if dp else None)


def timing(res):
    lat = sorted(r.get("latency_s") or 0 for r in res.values() if r.get("latency_s"))
    cost = [r.get("cost") or 0 for r in res.values()]
    return (round(statistics.median(lat), 2) if lat else 0, round(lat[int(0.95 * len(lat)) - 1], 2) if lat else 0, round(1000 * sum(cost) / max(1, len(cost)), 4))


def main():
    systems = sorted(p.name for p in (ROOT / "results").iterdir())
    lines = ["# Jev lane classification test\n", f"{len(CASES)} cases: " + ", ".join(f"{g} {sum(group(c) == g for c in CASES)}" for g in ("img", "pdf", "ocr", "garb")) + ".\n",
             "| system | run | n | lane acc | under-route | over-route | uncertain | text-layer acc | img | pdf | ocr | garb | p50 s | p95 s | $ per 1k |",
             "|" + "---|" * 15]
    details = []
    for s in systems:
        for run in (1, 2):
            res = load(s, run)
            if not res:
                continue
            m = lane_metrics(res)
            p50, p95, c1k = timing(res)
            tl = tl_acc(res)
            lines.append(f"| {s} | {run} | {m['n']} | {m['acc']:.3f} | {m['under']:.3f} | {m['over']:.3f} | {m['abstain']:.3f} | {'' if tl is None else f'{tl:.3f}'} | " +
                         " | ".join(m["by_group"].get(g, "") for g in ("img", "pdf", "ocr", "garb")) + f" | {p50} | {p95} | {c1k} |")
            if run == 1:
                details.append((s, m, calibration(res)))
    lines.append("\n## Run-to-run agreement (Jev)\n")
    for s in systems:
        a, b = load(s, 1), load(s, 2)
        if a and b:
            same, dp = agreement(a, b)
            lines.append(f"- {s}: same lane on {same:.3f} of cases; mean change in chosen-lane probability {dp:.3f}.")
    lines.append("\n## Calibration of Jev's lane probability (run 1)\n")
    for s, m, cal in details:
        if cal:
            lines.append(f"- {s}: mean p when right {cal['mean_p_right']:.3f}, when wrong {cal['mean_p_wrong']:.3f}, ECE {cal['ece']:.3f}; "
                         + "; ".join(f"p>={k[3:]}: {v}" for k, v in cal.items() if k.startswith("tau")))
    lines.append("\n## Errors (run 1)\n")
    for s, m, _ in details:
        lines.append(f"**{s}** ({len(m['wrong'])} wrong)")
        for cid, lane, gt in m["wrong"]:
            lines.append(f"- {cid}: said {lane}, truth {gt}")
        lines.append("")
    (ROOT / "scores_table.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
