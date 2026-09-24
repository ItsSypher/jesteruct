"""Regenerate data/labels.jsonl from labels.orig.jsonl plus label_overrides.json (glob keys, dotted fields)."""
import fnmatch, json
from pathlib import Path
D = Path(__file__).parent / "data"
ov = {k: v for k, v in json.loads((D / "label_overrides.json").read_text()).items() if not k.startswith("_")}
out = []
for line in (D / "labels.orig.jsonl").read_text().splitlines():
    if not line.strip():
        continue
    r = json.loads(line)
    for pat, fields in ov.items():
        if fnmatch.fnmatch(r["id"], pat):
            for f, v in fields.items():
                if f.startswith("_"):
                    continue
                if "." in f:
                    a, b = f.split(".", 1)
                    r.setdefault(a, {})[b] = v
                else:
                    r[f] = v
            r.setdefault("overrides", []).append(pat)
    out.append(json.dumps(r, ensure_ascii=False))
(D / "labels.jsonl").write_text("\n".join(out) + "\n")
print(f"{len(out)} labels written; {sum('overrides' in json.loads(l) for l in out)} overridden")
