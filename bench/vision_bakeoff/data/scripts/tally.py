"""Print counts per category for the final report / README."""
import collections
import json

LABELS = "/Users/kavy/Code/Projects/jesteruct/bench/vision_bakeoff/data/labels.jsonl"

rows = [json.loads(line) for line in open(LABELS)]
print("total pages:", len(rows))

cap = collections.Counter()
for r in rows:
    for v in r["capture_ok"]:
        cap[v] += 1
print("capture_ok:", dict(cap))

for field in ["legibility", "handwriting", "script"]:
    c = collections.Counter(r[field] for r in rows)
    print(f"{field}:", dict(c))

content = collections.Counter()
for r in rows:
    for k, v in r["content"].items():
        if v:
            content[k] += 1
print("content (true counts):", dict(content))

# source family breakdown
fam = collections.Counter()
for r in rows:
    src = r["source"]
    if src.startswith("PureDocBench"):
        fam["PureDocBench"] += 1
    elif src.startswith("olmOCR"):
        fam["olmOCR-Bench"] += 1
    elif src.startswith("FUNSD"):
        fam["FUNSD"] += 1
    elif src.startswith("GNHK"):
        fam["GNHK"] += 1
    elif "Arabic" in src:
        fam["Arabic"] += 1
    elif src.startswith("Synthetic"):
        fam["Synthetic"] += 1
    else:
        fam["other"] += 1
print("by source family:", dict(fam))
