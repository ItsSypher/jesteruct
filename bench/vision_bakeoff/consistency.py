"""Run-to-run consistency for models run twice (results/ vs results_run2/).
Reports per-axis agreement, accuracy of each run, and accuracy when both runs agree vs when they disagree,
which tests whether two-sample agreement is usable as a confidence signal."""
import json
from pathlib import Path
from score import LABELS, parse, page_scores, AXES, COMPOSITE_AXES

ROOT = Path(__file__).parent
def load(d):
    return {json.loads(f.read_text())["page"]: parse(json.loads(f.read_text())) for f in d.glob("*.json")}

def key(pred, axis):
    if pred is None: return None
    return json.dumps(pred.get(axis), sort_keys=True)

lines = ["# Run-to-run consistency (two independent runs, same inputs)\n",
         "| model | pages | agree_all_axes | agree_capture | agree_handwriting | agree_content | agree_script | composite_run1 | composite_run2 | acc_when_agree | acc_when_disagree | pages_disagree |",
         "|" + "---|" * 12]
for d2 in sorted((ROOT / "results_run2").iterdir()):
    d1 = ROOT / "results" / d2.name
    a, b = load(d1), load(d2)
    pids = [p for p in a if p in b and p in LABELS and a[p] is not None and b[p] is not None]
    agree = {ax: sum(key(a[p], ax) == key(b[p], ax) for p in pids) / len(pids) for ax in ["capture", "handwriting", "content", "script"]}
    allag = [p for p in pids if all(key(a[p], ax) == key(b[p], ax) for ax in COMPOSITE_AXES)]
    dis = [p for p in pids if p not in allag]
    def comp(ps, src):
        vals = []
        for ax in COMPOSITE_AXES:
            v = [page_scores(src[p], LABELS[p])[ax] for p in ps]
            v = [x for x in v if x is not None]
            if v: vals.append(sum(v) / len(v))
        return round(sum(vals) / len(vals), 3) if vals else ""
    lines.append(f"| {json.loads(next(d2.glob('*.json')).read_text())['model']} | {len(pids)} | {len(allag)/len(pids):.2f} | " +
                 " | ".join(f"{agree[x]:.2f}" for x in ["capture", "handwriting", "content", "script"]) +
                 f" | {comp(pids, a)} | {comp(pids, b)} | {comp(allag, a)} | {comp(dis, a)} | {len(dis)} |")
out = "\n".join(lines) + "\n"
(ROOT / "consistency.md").write_text(out)
print(out)
