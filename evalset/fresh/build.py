# /// script
# requires-python = ">=3.12,<3.14"
# dependencies = ["httpx>=0.28", "numpy>=2.2", "pillow>=11", "pypdfium2>=5.13", "pikepdf>=10", "jesteruct"]
#
# [tool.uv.sources]
# jesteruct = { path = "../..", editable = true }
# ///
"""Build evalset/fresh: blind-labelled pages, disjoint from evalset/, split once into a tuning and a held-out part.

    uv run evalset/fresh/build.py                             # write files/ and cases.jsonl from the labels so far
    uv run evalset/fresh/build.py packets DIR                 # blind labelling packets of every page
    uv run evalset/fresh/build.py adjudication-packets DIR    # blind packets of the pages A and B disagree on
    uv run evalset/fresh/build.py ingest --labeller a|c DIR   # add the labels.jsonl files under DIR to labels.jsonl
    uv run evalset/fresh/build.py pack                        # files/ as a release tarball, with its sha256
    uv run evalset/fresh/build.py fetch                       # download that release into files/ and verify it

pages.jsonl is the catalogue: every page, where its raw file comes from and how it becomes the file the router is
given (sources.py), plus the variants built from pages (garbled text layers, OCR-layer PDFs). Part v1 is the first
build's 396 cases, with their old single labels kept for comparison only. Part v2 was drawn once, before labelling:
quotas per source stratum, one page per source document in a stable hash order, pinned in pages.jsonl (a web
document with its sha256, so an upstream change fails loudly). labels.jsonl holds every labeller's opinion,
and the ground truth comes from the merge rule in labels.py: only pages with a final label become cases, and the build
counts the rest. split.json records each new document's split the first time its pages have a final label, and never
changes it. Downloads are cached in .cache/ (gitignored); the OCR-layer variants need the tesseract CLI.
"""

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
from collections import Counter
from pathlib import Path

import labels
import numpy as np
import sources
from PIL import Image

HERE = Path(__file__).parent
CACHE = sources.CACHE
FILES = HERE / "files"
EVALSET = HERE.parent
RELEASE = "evalset-fresh-v2"
PACKET_IDS = CACHE / "packet_ids.json"
NEAR_DUPLICATE = 2  # bits of 256; distinct near-blank pages come out 5 or more apart
GARBLED_GT = ["L3"]  # a garbled layer over a born-digital page: the page needs OCR, and its image is clean


def _jsonl(path: Path) -> list[dict]:
    # split on "\n" only: garbled text overrides hold characters such as \x85 that splitlines() breaks on
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def catalogue() -> tuple[list[dict], list[dict]]:
    entries = _jsonl(HERE / "pages.jsonl")
    pages = [e for e in entries if "key" in e]
    variants = [e for e in entries if "of" in e]
    if len(pages) + len(variants) != len(entries):
        raise ValueError("every line of pages.jsonl is a page (with a key) or a variant (with of)")
    for name, values in (("key", [p["key"] for p in pages]), ("id", [e["id"] for e in entries])):
        if dupes := [v for v, n in Counter(values).items() if n > 1]:
            raise ValueError(f"repeated {name}s in pages.jsonl: {dupes[:3]}")
    _check_disjoint(pages)
    return pages, variants


_SOURCE_PAGE = [  # how a source page is named in the attribution of both sets
    r"olmOCR-Bench.*(bench_data/pdfs/\S+\.pdf)",
    r"(Berzerker/gnhk_ocr_dataset).*row_idx=(\d+)",
    r"PureDocBench.*(page_id=\S+)",
]


def _source_pages(source: str) -> set[tuple[str, ...]]:
    return {m.groups() for pattern in _SOURCE_PAGE if (m := re.search(pattern, source))}


def _check_disjoint(pages: list[dict]) -> None:
    """No page may reuse a source page of evalset/ (its olmOCR-Bench PDFs, GNHK rows and PureDocBench pages; its
    FUNSD pages come from another split). Files are checked by sha256 when they are written."""
    taken = set().union(*(_source_pages(c["source"]) for c in _jsonl(EVALSET / "cases.jsonl")))
    for p in pages:
        if shared := _source_pages(p["source"]) & taken:
            raise ValueError(f"{p['key']} reuses a source page of evalset/: {shared}")


def stage_all(pages: list[dict]) -> dict[str, Path]:
    sources.fetch_raw(pages)
    for p in pages:
        if "sha256_raw" in p and sources.sha256(sources.RAW / p["raw"]) != p["sha256_raw"]:
            raise ValueError(f"{p['key']}: the public document changed upstream ({p['fetch']['url']})")
    return {p["key"]: sources.stage(p) for p in pages}


def rubrics(pages: list[dict], staged: dict[str, Path]) -> dict[str, str]:
    """Born-digital pages with a readable text layer are judged on layout; every other page on capture."""
    path = CACHE / "text_layers.json"
    known = json.loads(path.read_text()) if path.exists() else {}
    for p in pages:
        f = staged[p["key"]]
        tag = f"{f.name}:{sources.sha256(f)}"
        if tag not in known:
            known[tag] = sources.text_layer(f)
        p["text_layer"] = known[tag]
    path.write_text(json.dumps(known, indent=0, sort_keys=True))
    return {p["key"]: "layout" if p["text_layer"] == "trusted" else "capture" for p in pages}


def _check_near_duplicates(pages: list[dict], staged: dict[str, Path]) -> None:
    """Pages of different documents must not show the same image, here or in evalset/. A file hash misses the same
    scan served by two datasets (FUNSD's forms come from RVL-CDIP) and the same photo in two splits of one dataset
    (CORD), so each page gets a 256-bit difference hash, and two within NEAR_DUPLICATE bits fail the build."""
    path = CACHE / "image_hashes.json"
    known = json.loads(path.read_text()) if path.exists() else {}
    items = [(p["doc"], p["key"], staged[p["key"]]) for p in pages]
    items += [("evalset", f"evalset/{f.name}", f) for f in sorted((EVALSET / "files").iterdir())]  # its own twins pass
    for _, _, f in items:
        digest = sources.sha256(f)
        if digest not in known:
            gray = np.asarray(sources.page_image(f).convert("L").resize((17, 16), Image.Resampling.LANCZOS), np.int16)
            known[digest] = "".join("1" if b else "0" for b in (gray[:, 1:] > gray[:, :-1]).ravel())
    path.write_text(json.dumps(known, indent=0, sort_keys=True))
    bits = np.array([[c == "1" for c in known[sources.sha256(f)]] for _, _, f in items])
    close = np.argwhere(np.triu((bits[:, None, :] != bits[None, :, :]).sum(-1) <= NEAR_DUPLICATE, 1))
    if pairs := [(items[i][1], items[j][1]) for i, j in close if items[i][0] != items[j][0]]:
        raise ValueError(f"near-identical pages of different documents: {pairs[:5]}")


# ---------------------------------------------------------------- the split


def _rank(text: str) -> str:
    return hashlib.sha256(f"split:{text}".encode()).hexdigest()


def assign_splits(pages: list[dict], gt: dict[str, list[str]]) -> dict[str, str]:
    """Each document's split. v1 documents shaped evidence e3, so they are all `tune`. A new document gets its split
    the first time one of its pages has a final label: half `tune`, half `holdout` within each (source family, lane)
    stratum, taken in a stable hash order of the document id, and recorded in split.json for good."""
    path = HERE / "split.json"
    fixed: dict[str, str] = json.loads(path.read_text()) if path.exists() else {}
    docs: dict[str, list[dict]] = {}
    for p in pages:
        if p["part"] == "v2":
            docs.setdefault(p["doc"], []).append(p)
    count: Counter = Counter()

    def stratum(doc: str) -> str:
        first = min((p for p in docs[doc] if p["key"] in gt), key=lambda p: p["key"])
        return f"{first['family']} {'/'.join(gt[first['key']])}"

    for doc, split in fixed.items():
        if doc in docs:
            count[stratum(doc), split] += sum(p["key"] in gt for p in docs[doc])
    new = sorted((d for d in docs if d not in fixed and any(p["key"] in gt for p in docs[d])), key=_rank)
    for doc in new:
        s = stratum(doc)
        tune, holdout = count[s, "tune"], count[s, "holdout"]
        split = (
            "tune" if tune < holdout else "holdout" if holdout < tune else ("tune", "holdout")[int(_rank(doc), 16) % 2]
        )
        fixed[doc] = split
        count[s, split] += sum(p["key"] in gt for p in docs[doc])
    if new:
        path.write_text(json.dumps(fixed, indent=0, sort_keys=True) + "\n")
    return {p["doc"]: fixed.get(p["doc"], "tune") if p["part"] == "v2" else "tune" for p in pages}


# ---------------------------------------------------------------- the build


def build() -> None:
    pages, variants = catalogue()
    staged = stage_all(pages)
    _check_near_duplicates(pages, staged)
    rubric = rubrics(pages, staged)
    verdicts = labels.verdicts(labels.load(HERE / "labels.jsonl"), rubric)
    if pending := sum(state == "pending" for state, _ in verdicts.values()):
        raise SystemExit(f"{pending} pages still lack labeller A or B; files/ and cases.jsonl are left as they are")
    gt = {key: lanes for key, (state, lanes) in verdicts.items() if state == "final"}
    splits = assign_splits(pages, gt)
    by_key = {p["key"]: p for p in pages}

    FILES.mkdir(exist_ok=True)
    for old in FILES.iterdir():
        old.unlink()
    cases = []

    def add(case_id: str, file: Path, page: dict, lanes: list[str], group: str, source: str, **extra) -> None:
        dest = FILES / file.name
        if not dest.exists():
            dest.write_bytes(file.read_bytes())
        cases.append(
            {
                "id": case_id,
                "file": f"files/{dest.name}",
                "page": 0,
                "gt": lanes,
                "group": group,
                "source": source,
                "key": page["key"],
                "split": splits[page["doc"]],
                "sha256": sources.sha256(dest),
                **extra,
            }
        )

    for p in pages:
        if p["key"] in gt:
            group = "img" if p["render"] == "jpeg" else "garb" if p["text_layer"] == "garbled" else "pdf"
            add(p["id"], staged[p["key"]], p, gt[p["key"]], group, p["source"])
    for v in variants:
        base = by_key[v["of"]]
        if base["key"] not in gt:
            continue
        kind, _, how = v["variant"].partition(":")
        if kind == "garble":
            text = sources.garble(sources.pdf_facts(staged[base["key"]])["text"], how)
            source = f"{base['source']} (garbled text layer, evidence-level synthetic)"
            add(v["id"], staged[base["key"]], base, GARBLED_GT, "garb", source, text_override=text)
        else:
            dest = sources.STAGE / f"{v['id']}.pdf"
            if not dest.exists():
                sources.ocr_pdf(staged[base["key"]], dest)
            add(v["id"], dest, base, gt[base["key"]], "ocr", f"{base['source']} (OCR layer added with Tesseract)")

    digests = Counter(c["sha256"] for c in cases if "text_override" not in c)
    assert max(digests.values(), default=1) == 1, "two fresh cases have identical files"
    taken = {sources.sha256(f) for f in (EVALSET / "files").iterdir()}
    assert not taken & digests.keys(), "a fresh file is also in evalset/"
    cases.sort(key=lambda c: (c["group"], c["id"]))
    with open(HERE / "cases.jsonl", "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in cases)
    report(pages, cases, verdicts, rubric)


def report(pages: list[dict], cases: list[dict], verdicts: dict, rubric: dict[str, str]) -> None:
    states = Counter(state for state, _ in verdicts.values())
    size = sum(f.stat().st_size for f in FILES.iterdir())
    print(f"{len(cases)} cases, {size / 1e6:.1f} MB; pages: {dict(sorted(states.items()))}")
    lanes = sorted({"/".join(c["gt"]) for c in cases})
    table: dict[str, Counter] = {}
    for c in cases:
        family = next(p["family"] for p in pages if p["key"] == c["key"])
        table.setdefault(f"{family} [{c['split']}]", Counter())["/".join(c["gt"])] += 1
    print("source".ljust(44), *(lane.rjust(6) for lane in lanes))
    for row, counts in sorted(table.items()):
        print(row[:44].ljust(44), *(str(counts[lane]).rjust(6) for lane in lanes))
    contradictions = []
    for p in pages:
        state, lanes_ = verdicts[p["key"]]
        if state != "final":
            continue
        for what, prior in (("metadata", p["prior"]), ("old label", p.get("old"))):
            if prior and not set(lanes_) & set(prior):
                contradictions.append(f"  {p['key']}: {'/'.join(lanes_)}, {what} says {'/'.join(prior)}")
    if contradictions:
        print(f"{len(contradictions)} final labels contradict their prior:", *contradictions, sep="\n")


# ---------------------------------------------------------------- packets and labels


def _router_jpeg(path: Path) -> bytes:
    """The exact 1024 px JPEG the router sees for a page file."""
    from jesteruct.probes import image, pdf

    if path.suffix == ".pdf":
        return image.render_pdf_page(pdf.page(str(path), 0))
    return image.image_page(str(path), 0)


def write_packets(out: Path, adjudication: bool) -> None:
    pages, _ = catalogue()
    staged = stage_all(pages)
    rubric = rubrics(pages, staged)
    if adjudication:
        verdicts = labels.verdicts(labels.load(HERE / "labels.jsonl"), rubric)
        todo = [(k, rubric[k]) for k, (state, _) in verdicts.items() if state == "needs_c"]
    else:
        todo = list(rubric.items())
    counts = labels.write_packets(todo, lambda key: _router_jpeg(staged[key]), out, PACKET_IDS)
    print(f"{counts} images in {out}; the id map is {PACKET_IDS}")


def ingest(labeller: str, packets: Path) -> None:
    records = labels.read_packet_labels(packets, PACKET_IDS, labeller)
    print(f"{labels.append(HERE / 'labels.jsonl', records)} opinions added as labeller {labeller}")


# ---------------------------------------------------------------- release asset


def pack() -> None:
    """A plain, reproducible tar of files/ and its sha256, for the release asset."""
    out = CACHE / "release" / f"{RELEASE}.tar"
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w", format=tarfile.PAX_FORMAT) as tar:
        for f in sorted(FILES.iterdir()):
            info = tar.gettarinfo(f, arcname=f"files/{f.name}")
            info.mtime, info.uid, info.gid, info.uname, info.gname, info.mode = 0, 0, 0, "", "", 0o644
            with f.open("rb") as fh:
                tar.addfile(info, fh)
    digest = sources.sha256(out)
    out.with_suffix(".tar.sha256").write_text(f"{digest}  {out.name}\n")
    print(f"{out} ({out.stat().st_size / 1e6:.1f} MB), sha256 {digest}")
    print(f"gh release create {RELEASE} {out} {out.with_suffix('.tar.sha256')} --title {RELEASE}")


def fetch() -> None:
    """Download the release asset, check it, unpack it into files/ and verify every case file against cases.jsonl."""
    dest = CACHE / "release"
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["gh", "release", "download", RELEASE, "--pattern", f"{RELEASE}.tar*", "--dir", str(dest), "--clobber"],
        check=True,
    )
    tar_path = dest / f"{RELEASE}.tar"
    want = (dest / f"{RELEASE}.tar.sha256").read_text().split()[0]
    if sources.sha256(tar_path) != want:
        raise SystemExit(f"{tar_path.name} does not match its sha256")
    FILES.mkdir(exist_ok=True)
    with tarfile.open(tar_path) as tar:
        tar.extractall(HERE, filter="data")
    bad = [
        c["file"]
        for c in _jsonl(HERE / "cases.jsonl")
        if not (HERE / c["file"]).exists() or sources.sha256(HERE / c["file"]) != c["sha256"]
    ]
    if bad:
        raise SystemExit(f"{len(bad)} case files are missing or differ from cases.jsonl, for example {bad[:3]}")
    print(f"files/ verified against cases.jsonl ({RELEASE})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command")
    for name in ("packets", "adjudication-packets"):
        commands.add_parser(name).add_argument("out", type=Path)
    ing = commands.add_parser("ingest")
    ing.add_argument("--labeller", required=True, choices=["a", "c"])
    ing.add_argument("packets", type=Path)
    commands.add_parser("pack")
    commands.add_parser("fetch")
    args = parser.parse_args()
    if args.command in ("packets", "adjudication-packets"):
        write_packets(args.out, args.command == "adjudication-packets")
    elif args.command == "ingest":
        ingest(args.labeller, args.packets)
    elif args.command == "pack":
        pack()
    elif args.command == "fetch":
        fetch()
    else:
        build()


if __name__ == "__main__":
    main()
