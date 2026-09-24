"""
Final assembly: reads manifest.PAGES, converts each raw source image to
pages/<id>.jpg (RGB, long side 1024px, quality 90), and writes labels.jsonl.

Run after all raw/ sources have been fetched (see build.py for the full
pipeline including downloads).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from manifest import PAGES  # noqa: E402
from imgutil import to_page_jpeg  # noqa: E402

DATA_DIR = "/Users/kavy/Code/Projects/jesteruct/bench/vision_bakeoff/data"
PAGES_DIR = os.path.join(DATA_DIR, "pages")
LABELS_PATH = os.path.join(DATA_DIR, "labels.jsonl")

REQUIRED_FIELDS = ["id", "source", "license", "capture_ok", "legibility", "handwriting",
                   "content", "script", "label_basis"]
CAPTURE_VALUES = {"digital_render", "flatbed_scan", "fax", "camera_photo", "screenshot"}
LEGIBILITY_VALUES = {"clean", "degraded", None}
HANDWRITING_VALUES = {"none", "some", "mostly", None}
SCRIPT_VALUES = {"latin", "cyrillic", "greek", "arabic", "hebrew", "cjk", "other", "mixed", None}
CONTENT_KEYS = {"table", "math", "form", "code", "chart", "photo"}


def validate(entry):
    for f in REQUIRED_FIELDS:
        assert f in entry, f"{entry.get('id')}: missing field {f}"
    assert isinstance(entry["capture_ok"], list) and entry["capture_ok"], entry["id"]
    for v in entry["capture_ok"]:
        assert v in CAPTURE_VALUES, f"{entry['id']}: bad capture_ok value {v}"
    assert entry["legibility"] in LEGIBILITY_VALUES, entry["id"]
    assert entry["handwriting"] in HANDWRITING_VALUES, entry["id"]
    assert entry["script"] in SCRIPT_VALUES, entry["id"]
    assert set(entry["content"].keys()) == CONTENT_KEYS, entry["id"]
    for v in entry["content"].values():
        assert v in (True, False, None), entry["id"]


def main():
    os.makedirs(PAGES_DIR, exist_ok=True)
    seen_ids = set()
    label_rows = []
    missing = []
    for entry in PAGES:
        validate(entry)
        pid = entry["id"]
        assert pid not in seen_ids, f"duplicate id {pid}"
        seen_ids.add(pid)

        if not os.path.exists(entry["raw"]):
            missing.append((pid, entry["raw"]))
            continue

        out_path = os.path.join(PAGES_DIR, f"{pid}.jpg")
        size = to_page_jpeg(entry["raw"], out_path)

        label_rows.append({
            "id": pid,
            "source": entry["source"],
            "license": entry["license"],
            "capture_ok": entry["capture_ok"],
            "legibility": entry["legibility"],
            "handwriting": entry["handwriting"],
            "content": entry["content"],
            "script": entry["script"],
            "label_basis": entry["label_basis"],
        })
        print(f"{pid}: {entry['raw']} -> {out_path} {size}")

    with open(LABELS_PATH, "w") as f:
        for row in label_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(label_rows)} pages to {PAGES_DIR}")
    print(f"Wrote {LABELS_PATH}")
    if missing:
        print(f"\nMISSING {len(missing)} raw sources (not processed):")
        for pid, raw in missing:
            print(f"  {pid}: {raw}")


if __name__ == "__main__":
    main()
