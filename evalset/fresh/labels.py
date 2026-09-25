"""Blind labels: the two rubrics, the label store, the merge rule and the packets labellers work from.

Every opinion is one line of labels.jsonl: {"key", "labeller", "code", "why"}. Labellers A (Claude) and B (a model of
another family, label_model.py) label every page; C adjudicates the pages where they disagree. Nobody sees a page's
source, its metadata or another labeller's code.
"""

import json
import secrets
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path

CODES = {
    "capture": {"clean": ["L3"], "degraded": ["L4"], "borderline": ["L3", "L4"], "handwritten": ["L5"], "unusable": []},
    "layout": {"simple": ["L1"], "complex": ["L2"], "borderline": ["L1", "L2"], "unusable": []},
}
LABELLERS = ("a", "b", "c")
BATCH = 50

_PRIVATE = (
    "personal data about a private individual: a personal letter, contact details, an ID, a medical or school record,"
    " a receipt that prints a cashier's full name. Authors of published work and officials in official documents are"
    " not private individuals."
)
# (title, introduction, {code: definition}) per rubric; the packet READMEs and labeller B's prompt are made from it.
_RUBRICS = {
    "capture": (
        "how the page was captured",
        "Each image is one document page: a scan, a photo, a fax or a screenshot.",
        {
            "clean": (
                "The page is flat and the printed text is crisp and fully legible, so a standard OCR engine would read"
                " it at near full accuracy. Mild, uniform artefacts still count as clean: light speckle or dust, a"
                " slight tint or yellowing, light banding, mild JPEG softness, a slight skew, a small page on a larger"
                " scan bed, a faint watermark behind crisp text. A crisp screenshot, or a crisp page turned on its"
                " side, is clean."
            ),
            "degraded": (
                "Degradation would plausibly hurt a standard OCR engine: blur or low resolution that makes glyphs soft"
                " or merged, heavy noise, bleed-through, broken, blotchy or bleeding strokes (for example after many"
                " photocopy generations), warped, curved or perspective-distorted paper, uneven lighting or shadows,"
                " a camera photo rather than a scan, fax artefacts."
            ),
            "borderline": "You genuinely hesitate between clean and degraded.",
            "handwritten": (
                "Most of the content is handwritten. A printed form filled in by hand is not handwritten: judge its"
                " capture as clean or degraded."
            ),
            "unusable": f"Blank, not a document, or it shows {_PRIVATE}",
        },
    ),
    "layout": (
        "how complex the page layout is",
        "Each image is one page of a born-digital PDF: made on a computer, with a real text layer. The code says how"
        " hard its layout is for plain text extraction.",
        {
            "simple": (
                "Running text in one column: headings, paragraphs, lists, figures or images with captions, headers"
                " and footers."
            ),
            "complex": (
                "Any of these: a table, including a borderless one (values aligned in rows and columns that plain"
                " text extraction would scramble); equations or dense inline mathematical notation; source code or"
                " configuration listings; two or more text columns over a substantial part of the page."
            ),
            "borderline": "You genuinely hesitate between simple and complex.",
            "unusable": f"Blank or nearly blank, not a document, or it shows {_PRIVATE}",
        },
    ),
}


def _lines(text: str, indent: str = "") -> str:
    """One sentence per line."""
    return f"\n{indent}".join(s if s.endswith(".") else s + "." for s in text.rstrip(".").split(". "))


def rubric(name: str) -> str:
    title, intro, codes = _RUBRICS[name]
    items = "\n".join(f"- `{code}`:\n  {_lines(text, '  ')}" for code, text in codes.items())
    return f"# Labelling: {title}\n\n{_lines(intro)}\nGive each image exactly one code.\n\n{items}\n"


def readme(name: str) -> str:
    return (
        rubric(name) + "\n## Output\n\nWrite `labels.jsonl` in this folder: one JSON object per line, one line per"
        ' image, for example\n\n    {"image": "q7f3k2.jpg", "code": "CODE", "why": "a reason"}\n\n'
        "`why` is in English and under 15 words.\nJudge each image only by what it shows.\n"
    )


# ---------------------------------------------------------------- the store


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append(path: Path, records: Iterable[dict]) -> int:
    """Add opinions to the store. A labeller gives one opinion per page: repeats are skipped, changes refused."""
    have = {(r["key"], r["labeller"]): r["code"] for r in load(path)}
    new = []
    for r in records:
        known = have.get((r["key"], r["labeller"]))
        if known is not None and known != r["code"]:
            raise ValueError(f"{r['key']}: labeller {r['labeller']} already said {known!r}, now {r['code']!r}")
        if known is None:
            have[(r["key"], r["labeller"])] = r["code"]
            new.append({k: r[k] for k in ("key", "labeller", "code", "why")})
    with path.open("a", encoding="utf-8") as fh:
        fh.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in new)
    return len(new)


# ---------------------------------------------------------------- the merge rule


def _pair(lanes: set[str]) -> set[str] | None:
    """The boundary pair (L1/L2 or L3/L4) that holds all these lanes, if one does."""
    return next((p for p in ({"L1", "L2"}, {"L3", "L4"}) if lanes and lanes <= p), None)


def verdict(rubric: str, codes: dict[str, str]) -> tuple[str, list[str]]:
    """("final", lanes), ("drop", []), ("needs_c", []) or ("pending", []) from one page's codes per labeller.

    A and B agreeing settles the page, and `borderline` gives the set label. When they differ, C decides by majority,
    except that opinions that differ only across one boundary (L3 against L4, L1 against L2, or `borderline` against
    either) give the set label. Two `unusable` opinions drop the page, and so do three different opinions that no
    boundary pair holds.
    """
    lanes = CODES[rubric]
    if "a" not in codes or "b" not in codes:
        return "pending", []
    said = [codes[k] for k in LABELLERS if k in codes]
    if codes["a"] == codes["b"]:
        return ("final", lanes[codes["a"]]) if lanes[codes["a"]] else ("drop", [])
    if "c" not in codes:
        return "needs_c", []
    if said.count("unusable") >= 2:
        return "drop", []
    usable = [c for c in said if c != "unusable"]
    pair = _pair({lane for c in usable for lane in lanes[c]})
    if pair is not None and len(set(usable)) > 1:
        return "final", sorted(pair)
    top, n = Counter(said).most_common(1)[0]
    if n >= 2:
        return ("final", lanes[top]) if lanes[top] else ("drop", [])
    return "drop", []


def verdicts(store: list[dict], rubrics: dict[str, str]) -> dict[str, tuple[str, list[str]]]:
    """Every page's verdict; `rubrics` maps each page key to its rubric."""
    codes: dict[str, dict[str, str]] = {}
    for r in store:
        if r["key"] not in rubrics:
            raise ValueError(f"a label for a page that is not in the corpus: {r['key']}")
        if r["code"] not in CODES[rubrics[r["key"]]]:
            raise ValueError(f"{r['key']}: {r['code']!r} is not a {rubrics[r['key']]} code")
        codes.setdefault(r["key"], {})[r["labeller"]] = r["code"]
    return {key: verdict(rubric, codes.get(key, {})) for key, rubric in rubrics.items()}


# ---------------------------------------------------------------- packets


def _clean_jpeg(jpeg: bytes) -> bytes:
    """Check that a JPEG carries no metadata segment (Exif, XMP, comments) that could name its source."""
    i = 2
    while i + 4 <= len(jpeg) and jpeg[i] == 0xFF and jpeg[i + 1] not in (0xDA, 0xD9):
        marker, size = jpeg[i + 1], int.from_bytes(jpeg[i + 2 : i + 4], "big")
        if marker == 0xFE or (0xE1 <= marker <= 0xEF):
            raise ValueError(f"packet image carries a metadata segment 0xFF{marker:02X}")
        i += 2 + size
    return jpeg


def _new_id(taken: set[str]) -> str:
    while (pid := "".join(secrets.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(6))) in taken:
        pass
    taken.add(pid)
    return pid


def write_packets(
    pages: list[tuple[str, str]], render: Callable[[str], bytes], out: Path, ids_file: Path
) -> dict[str, int]:
    """Blind packets of (key, rubric) pages under out/<rubric>/batch-NN/: shuffled images under random ids, and a
    README per batch. The id-to-key map goes to ids_file, outside the packets. Returns the image count per rubric."""
    ids = json.loads(ids_file.read_text()) if ids_file.exists() else {}
    taken, counts = set(ids), {}
    order = sorted(pages)
    secrets.SystemRandom().shuffle(order)
    for rubric in CODES:
        mine = [key for key, r in order if r == rubric]
        counts[rubric] = len(mine)
        for n in range(0, len(mine), BATCH):
            batch = out / rubric / f"batch-{n // BATCH + 1:02d}"
            batch.mkdir(parents=True)
            (batch / "README.md").write_text(readme(rubric))
            for key in mine[n : n + BATCH]:
                pid = _new_id(taken)
                ids[pid] = {"key": key, "rubric": rubric}
                (batch / f"{pid}.jpg").write_bytes(_clean_jpeg(render(key)))
    ids_file.parent.mkdir(parents=True, exist_ok=True)
    ids_file.write_text(json.dumps(ids, indent=0, sort_keys=True))
    return counts


def read_packet_labels(packet_dir: Path, ids_file: Path, labeller: str, name: str = "labels.jsonl") -> list[dict]:
    """A labeller's answers in every batch under packet_dir, mapped back to page keys and checked against the rubric."""
    if labeller not in LABELLERS:
        raise ValueError(f"labeller must be one of {LABELLERS}")
    ids = json.loads(ids_file.read_text())
    out = []
    for batch in sorted({p.parent for p in packet_dir.rglob("README.md")}):
        images = {p.name for p in batch.glob("*.jpg")}
        answers = load(batch / name)
        seen = Counter(a["image"] for a in answers)
        if missing := images - seen.keys():
            raise ValueError(f"{batch}: no label for {sorted(missing)[:5]}")
        if odd := (seen.keys() - images) | {s for s, n in seen.items() if n > 1}:
            raise ValueError(f"{batch}: unknown or repeated images {sorted(odd)[:5]}")
        for a in answers:
            page = ids[a["image"].removesuffix(".jpg")]
            if a["code"] not in CODES[page["rubric"]]:
                raise ValueError(f"{batch}/{a['image']}: {a['code']!r} is not a {page['rubric']} code")
            out.append({"key": page["key"], "labeller": labeller, "code": a["code"], "why": a.get("why", "")})
    if not out:
        raise ValueError(f"no labelled batches under {packet_dir}")
    return out
