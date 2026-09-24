# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.28", "numpy>=2.2", "pillow>=11", "pypdfium2>=5.13", "pikepdf>=10"]
# ///
"""Build evalset/fresh: a labelled page set, disjoint from evalset/, for calibrating the review threshold (issue #3).

    uv run evalset/fresh/build.py           # fetch what is missing, then write files/ and cases.jsonl
    uv run evalset/fresh/build.py sheets    # contact sheets of the pages still waiting for a visual label

Labels come from construction or dataset metadata where those settle the lane, and from a visual check of contact
sheets (VISUAL, at the end of this file) where they do not. Lanes follow the fixed mapping of bench/jev_lanes/probe.py.
Downloads are cached in evalset/fresh/.cache (gitignored): about 1.2 GB, most of it PureDocBench captures read by
byte range out of its 35 GiB tar. The OCR-layer variants need the tesseract CLI.
"""

import concurrent.futures
import csv
import fnmatch
import hashlib
import io
import itertools
import json
import random
import re
import subprocess
import sys
import threading
import time
import unicodedata
from base64 import b64decode
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pikepdf
import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
RAW = CACHE / "raw"
EVALSET = HERE.parent
REPO = EVALSET.parent

sys.path.insert(0, str(REPO / "bench/vision_bakeoff/data/scripts"))
from synth_degrade import make_camera_photo, make_fax, rotate_page  # noqa: E402  (the bench's synthetic captures)


def evalset_sources() -> dict[str, set]:
    """Source pages already used by evalset/, per dataset, so the fresh set never reuses one."""
    lines = (EVALSET / "cases.jsonl").read_text(encoding="utf-8").split("\n")  # garbled overrides hold \x85 etc.
    sources = [json.loads(line)["source"] for line in lines if line.strip()]

    def grab(pattern: str, within: str) -> set[str]:
        return {m.group(1) for s in sources if within in s and (m := re.search(pattern, s))}

    return {
        # the bench also dropped a staff directory from olmOCR tables; it stays out here too
        "olmocr": grab(r"bench_data/pdfs/(\S+\.pdf)", "olmOCR")
        | {"tables/022b5843eb82c5e76fb3da69a0c432187f6c_pg1_pg1.pdf"},
        "gnhk": {int(r) for r in grab(r"row_idx=(\d+)", "GNHK")},
        "pdb": grab(r"page_id=(\S+)", "PureDocBench"),
    }  # evalset's FUNSD rows are from the test split; the fresh set draws from train


# ---------------------------------------------------------------- downloads


def _download(url: str, path: Path) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        r = httpx.get(url, follow_redirects=True, timeout=300)
        r.raise_for_status()
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(r.content)
        tmp.replace(path)


def _download_all(jobs: list[tuple[str, Path]]) -> None:
    with concurrent.futures.ThreadPoolExecutor(12) as pool:
        list(pool.map(lambda job: _download(*job), jobs))


def _hf_tree(repo: str, rev: str, path: str) -> list[dict]:
    url, out = f"https://huggingface.co/api/datasets/{repo}/tree/{rev}/{path}", []
    while url:
        r = httpx.get(url, timeout=60)
        r.raise_for_status()
        out += r.json()
        url = r.links.get("next", {}).get("url")
    return [x for x in out if x["type"] == "file"]


def _hf_rows(dataset: str, split: str, offset: int = 0, limit: int | None = None) -> list[dict]:
    """Rows from the HF datasets-server rows API (image cells come back as short-lived URLs)."""
    rows: list[dict] = []
    while limit is None or len(rows) < limit:
        length = 100 if limit is None else min(100, limit - len(rows))
        params = {
            "dataset": dataset,
            "config": "default",
            "split": split,
            "offset": offset + len(rows),
            "length": length,
        }
        for attempt in range(6):  # the API answers the odd 5xx on large rows
            r = httpx.get("https://datasets-server.huggingface.co/rows", params=params, timeout=300)
            if r.status_code < 500:
                break
            time.sleep(2 + 4 * attempt)
        r.raise_for_status()
        page = r.json()
        rows += page["rows"]
        if not page["rows"] or offset + len(rows) >= page["num_rows_total"]:
            break
    return rows


def _rows_with_images(dataset: str, split: str, folder: str, keep=lambda row: True) -> list[dict]:
    """A small image dataset's rows, each kept row's image downloaded to RAW/folder/<split>_<row_idx>.jpg."""
    path = CACHE / f"{folder}_{split}.json"
    if not path.exists():
        rows = [r for r in _hf_rows(dataset, split) if keep(r)]
        _download_all([(r["row"]["image"]["src"], RAW / folder / f"{split}_{r['row_idx']}.jpg") for r in rows])
        out = [{"row_idx": r["row_idx"], **{k: v for k, v in r["row"].items() if k != "image"}} for r in rows]
        path.write_text(json.dumps(out, ensure_ascii=False))
    return json.loads(path.read_text())


def _sample(split_size: int, n: int, seed: str) -> set[int]:
    return set(random.Random(seed).sample(range(split_size), n))


# ---------------------------------------------------------------- PureDocBench: one split tar, read by byte range

PDB_BASE = (
    "https://huggingface.co/datasets/zhihengli-casia/puredocbench/resolve/d56779469315a6489ab656dbd17595f094480f5c/"
)
PDB_PARTS = [(f"pdb_full.tar.part-{i:03d}", 4_089_446_400 if i < 9 else 802_099_200) for i in range(10)]
PDB_IMAGES_START = 65_171_968  # first header of images/ in the concatenated archive (found by the bench's walk)
PDB_PREFIX = "puredocbench-v1.0/images/"
PDB_TRACKS = {
    "clean": ("clean", "clean_rel"),
    "digital": ("digital_degraded", "digital_rel"),
    "real": ("real_degraded", "real_rel"),
}
# Document types without records about people. Medical, certificates, statements, resumes, letters, court papers,
# logistics and directories stay out even though PureDocBench content is synthetic.
PDB_SUBCATEGORIES = {
    "01_academic": "01_journal_paper 02_thesis 03_technical_report 04_patent 05_research_proposal 06_conference_poster",
    "02_education": "01_textbook 02_exam_paper 03_slides 04_school_notice 05_syllabus 06_lab_report",
    "03_legal_gov": "01_gov_document 05_legislation",
    "04_business": "02_quotation 04_meeting_memo 06_business_plan 07_employee_handbook",
    "05_finance": "02_financial_report 08_audit_report 09_fund_prospectus",
    "07_publishing": "01_newspaper 02_magazine 03_book 04_brochure_menu",
    "08_technical": "01_product_manual 02_datasheet 03_api_reference 04_architecture_diagram 05_release_notes",
    "10_certificate": "05_quality_certification",
}
PDB_TRIPLETS = 32


class SplitTar:
    """The release is one ~35 GiB tar split into ten parts with no per-file access; read ranges of the concatenation."""

    def __init__(self) -> None:
        starts = itertools.accumulate([0] + [size for _, size in PDB_PARTS])
        self.parts = [(lo, lo + size, name) for lo, (name, size) in zip(starts, PDB_PARTS, strict=False)]
        self.size = self.parts[-1][1]
        self._local = threading.local()
        self._cdn: dict[str, str] = {}

    def _client(self) -> httpx.Client:
        if not hasattr(self._local, "client"):
            self._local.client = httpx.Client(timeout=120)
        return self._local.client

    def _get(self, name: str, a: int, b: int) -> bytes:
        for _ in range(4):
            if name not in self._cdn:  # resolve the signed CDN URL once; it saves a redirect on every read
                self._cdn[name] = (
                    self._client().get(PDB_BASE + name, headers={"Range": "bytes=0-0"}).headers["location"]
                )
            try:
                r = self._client().get(self._cdn[name], headers={"Range": f"bytes={a}-{b - 1}"})
            except httpx.TransportError:
                continue
            if r.status_code == 206:
                return r.content
            self._cdn.pop(name, None)  # the signature expired
        raise RuntimeError(f"range read failed: {name} {a}-{b}")

    def read(self, start: int, length: int) -> bytes:
        out = bytearray()
        for lo, hi, name in self.parts:
            a, b = max(start, lo), min(start + length, hi)
            if a < b:
                out += self._get(name, a - lo, b - lo)
        return bytes(out)


def _tar_header(block: bytes) -> tuple[bytes, int, bytes] | None:
    """(name, size, typeflag) of a valid ustar header block, else None."""
    if len(block) < 512 or block[257:262] != b"ustar":
        return None
    try:
        checksum = int(block[148:156].split(b"\0")[0].strip() or b"0", 8)
        size = int(block[124:136].split(b"\0")[0].strip() or b"0", 8)
    except ValueError:
        return None
    if checksum != sum(block[:148]) + 8 * 32 + sum(block[156:512]):
        return None
    name, prefix = block[:100].split(b"\0")[0], block[345:500].split(b"\0")[0]
    return (prefix + b"/" + name if prefix else name), size, block[156:157]


def _tar_sync(tar: SplitTar, pos: int) -> int:
    """Offset of the first tar header at or after pos."""
    pos = -(-pos // 512) * 512
    while chunk := tar.read(pos, 1 << 20):
        for i in range(0, len(chunk) - 511, 512):
            if _tar_header(chunk[i : i + 512]):
                return pos + i
        pos += len(chunk)
    return tar.size


def _tar_walk(tar: SplitTar, start: int, stop: int) -> dict[int, tuple[str, int]]:
    """Regular files whose header sits in [start, stop): data offset -> (name, size). Reads headers only."""
    entries: dict[int, tuple[str, int]] = {}
    buf, buf_at = b"", 0

    def get(at: int, n: int) -> bytes:  # a long-name entry and the header after it usually share one read
        nonlocal buf, buf_at
        if not (buf_at <= at and at + n <= buf_at + len(buf)):
            buf, buf_at = tar.read(at, max(n, 4096)), at
        return buf[at - buf_at : at - buf_at + n]

    pos, long_name = start, None
    while pos < stop or long_name is not None:
        header = _tar_header(get(pos, 512))
        if header is None:  # end of the archive
            break
        name, size, flag = header
        data_at = pos + 512
        if flag == b"L":  # GNU long name: this entry's data is the next entry's name
            long_name = get(data_at, size).split(b"\0")[0]
        else:
            if flag in (b"0", b"\0"):
                entries[data_at] = ((long_name or name).decode("utf-8", "replace"), size)
            long_name = None
        pos = data_at + -(-size // 512) * 512
    return entries


def pdb_index() -> dict[str, tuple[int, int]]:
    """name -> (data offset, size) for every image, walked in parallel segments of about 100 headers each.

    The clean track (the first ~2.5 GB) holds the small files, so its segments are shorter.
    """
    path = CACHE / "pdb_index.json"
    if not path.exists():
        tar = SplitTar()
        guesses = [*range(PDB_IMAGES_START + 150_000_000, 2_500_000_000, 150_000_000)]
        guesses += [*range(2_500_000_000, tar.size, 1_200_000_000)]
        with concurrent.futures.ThreadPoolExecutor(16) as pool:
            bounds = sorted({PDB_IMAGES_START, *pool.map(lambda p: _tar_sync(tar, p), guesses), tar.size})
            parts = list(pool.map(lambda k: _tar_walk(tar, bounds[k], bounds[k + 1]), range(len(bounds) - 1)))
        merged: dict[int, tuple[str, int]] = {}
        for part in reversed(parts):  # an earlier segment saw the long name of an entry straddling a boundary
            merged.update(part)
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({name: (at, size) for at, (name, size) in merged.items()}, ensure_ascii=False))
    return {k: tuple(v) for k, v in json.loads(path.read_text()).items()}


def _png_size(head: bytes) -> tuple[int, int] | None:
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def pdb_fetch(excluded: set[str]) -> list[dict]:
    """One triplet (clean, digital-degraded and real-degraded renders of a page) per allowed document type, topped up
    to PDB_TRIPLETS, with the images fetched by byte range."""
    path = CACHE / "pdb_chosen.json"
    index, tar = pdb_index(), SplitTar()
    if not path.exists():
        text = httpx.get(PDB_BASE + "release_manifest_candidate_1475.csv", follow_redirects=True, timeout=60).text
        allowed = [
            m
            for m in csv.DictReader(io.StringIO(text))
            if m["subcategory"] in PDB_SUBCATEGORIES.get(m["category"], "").split() and m["page_id"] not in excluded
        ]
        for m in allowed:
            m["names"] = {track: f"{PDB_PREFIX}{folder}/{m[col]}" for track, (folder, col) in PDB_TRACKS.items()}

        def usable(m: dict) -> bool:  # all three tracks present, and not a tall strip of several pages
            if not all(n in index for n in m["names"].values()):
                return False
            size = _png_size(tar.read(index[m["names"]["clean"]][0], 24))
            return size is not None and max(size) / min(size) <= 1.9

        with concurrent.futures.ThreadPoolExecutor(16) as pool:
            allowed = [m for m, ok in zip(allowed, pool.map(usable, allowed), strict=True) if ok]
        rng, by_type = random.Random("fresh-pdb"), {}
        for m in allowed:
            by_type.setdefault(m["subcategory"], []).append(m)
        chosen = [rng.choice(group) for _, group in sorted(by_type.items())]
        chosen += rng.sample([m for m in allowed if m not in chosen], PDB_TRIPLETS - len(chosen))
        out = []
        for m in sorted(chosen, key=lambda m: m["page_id"]):
            name = Path(m["page_id"]).name
            prefix = re.match(r"[a-z_]+_\d{3}", name)  # e.g. academic_paper_017
            key = prefix.group(0) if prefix else _short(name)
            out.append({"page_id": m["page_id"], "real_chain": m["real_chain_label"], "key": key, "names": m["names"]})
        path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    chosen = json.loads(path.read_text())

    def fetch(t: dict, track: str) -> None:
        dest = pdb_file(t, track)
        if not dest.exists():
            offset, size = index[t["names"][track]]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(tar.read(offset, size))

    with concurrent.futures.ThreadPoolExecutor(12) as pool:
        list(pool.map(lambda job: fetch(*job), [(t, track) for t in chosen for track in PDB_TRACKS]))
    return chosen


def pdb_file(triplet: dict, track: str) -> Path:
    return RAW / "pdb" / track / (triplet["key"] + Path(triplet["names"][track]).suffix)


# ---------------------------------------------------------------- the other sources

OLM_REPO, OLM_REV = "allenai/olmOCR-bench", "54a96a6fb6a2bd3b297e59869491db4d3625b711"
OLM_DRAW = {"arxiv_math": 70, "multi_column": 110}  # PDFs drawn per category; the other categories are taken whole
OLM_CATEGORIES = [
    "arxiv_math",
    "headers_footers",
    "long_tiny_text",
    "multi_column",
    "old_scans",
    "old_scans_math",
    "tables",
]


def olm_fetch(excluded: set[str]) -> list[Path]:
    """olmOCR-Bench single-page PDFs; `excluded` holds the `category/file.pdf` names evalset/ already uses."""
    jobs = []
    for cat in OLM_CATEGORIES:
        names = sorted(Path(f["path"]).name for f in _hf_tree(OLM_REPO, OLM_REV, f"bench_data/pdfs/{cat}"))
        names = [n for n in names if n.endswith(".pdf") and f"{cat}/{n}" not in excluded]
        if cat in OLM_DRAW:
            names = sorted(random.Random(f"fresh-{cat}").sample(names, OLM_DRAW[cat]))
        base = f"https://huggingface.co/datasets/{OLM_REPO}/resolve/{OLM_REV}/bench_data/pdfs/{cat}/"
        jobs += [(base + n, RAW / "olmocr" / cat / n) for n in names]
    _download_all(jobs)
    return [path for _, path in jobs]


DLN_DATASET, DLN_TEST_ROWS = "docling-project/DocLayNet-v1.2", 4999
DLN_TABLE, DLN_FORMULA = 9, 3  # COCO category ids of the layout boxes


def doclaynet_fetch() -> list[dict]:
    """Five seeded windows of 100 DocLayNet test rows: each page's own PDF, layout boxes and document category."""
    path = CACHE / "doclaynet_test.json"
    if not path.exists():
        rng, out = random.Random("fresh-doclaynet"), []
        for offset in sorted(rng.sample(range(0, DLN_TEST_ROWS - 100, 100), 5)):
            for r in _hf_rows(DLN_DATASET, "test", offset, 100):
                row = r["row"]
                pdf = RAW / "doclaynet" / f"test_{r['row_idx']}.pdf"
                pdf.parent.mkdir(parents=True, exist_ok=True)
                pdf.write_bytes(b64decode(row["pdf"]))
                out.append({"row_idx": r["row_idx"], "categories": row["category_id"], **row["metadata"]})
        path.write_text(json.dumps(out, ensure_ascii=False))
    return json.loads(path.read_text())


OMNI_REPO, OMNI_REV = "opendatalab/OmniDocBench", "aa1ee96d106dbe53d0ae59474d75c6e6d9b53fec"
OMNI_HARD = {"fuzzy_scan", "fuzzy_content", "geometric_deformation"}
# pages drawn per data source, on top of every page flagged fuzzy or deformed and every historical document
OMNI_DRAW = {
    "note": 30,
    "exam_paper": 14,
    "book": 8,
    "newspaper": 6,
    "magazine": 6,
    "colorful_textbook": 6,
    "research_report": 5,
    "academic_literature": 5,
    "PPT2PDF": 5,
}


def omni_fetch() -> list[dict]:
    path = CACHE / "omnidocbench_chosen.json"
    if not path.exists():
        base = f"https://huggingface.co/datasets/{OMNI_REPO}/resolve/{OMNI_REV}/"
        pages = [
            p["page_info"] for p in httpx.get(base + "OmniDocBench.json", follow_redirects=True, timeout=300).json()
        ]
        chosen = [p for p in pages if OMNI_HARD & set(p["page_attribute"]["special_issue"])]
        chosen += [p for p in pages if p["page_attribute"]["data_source"] == "historical_document" and p not in chosen]
        rng = random.Random("fresh-omni")
        for source, n in OMNI_DRAW.items():
            pool = [p for p in pages if p["page_attribute"]["data_source"] == source and p not in chosen]
            chosen += rng.sample(pool, min(n, len(pool)))
        _download_all([(base + "images/" + p["image_path"], RAW / "omni" / p["image_path"]) for p in chosen])
        path.write_text(json.dumps(chosen, ensure_ascii=False))
    return json.loads(path.read_text())


RVL_CLASSES = [
    "letter",
    "form",
    "email",
    "handwritten",
    "advertisement",
    "scientific report",
    "scientific publication",
    "specification",
    "file folder",
    "news article",
    "budget",
    "invoice",
    "presentation",
    "questionnaire",
    "resume",
    "memo",
]

# GNHK: a transcription screen first (letters, cards, tutoring and child-observation notes, contact details), then
# rows dropped on reading their transcription (GNHK_DROP): personal notes, messages and diaries, notes naming
# colleagues or pupils, and a few with too little text to tell. What is left is still looked at.
_GNHK_PERSONAL = re.compile(
    r"\b(dear|name|address|street|road|avenue|tel|phone|mobile|e-?mail|mr|mrs|ms|miss|dr|love|xoxo|birthday|"
    r"sincerely|regards|born|age|patient|dob|passport|account|password|postcode|zip|apartment|mum|dad|mom|son|"
    r"daughter|wife|husband|boyfriend|girlfriend|baby|tutored|tutoring|session|child|child's|liam|aiden|aidan|"
    r"wedding|married|marriage|congrats|congratulations|thank|thanks|thanx|sorry|miss you|lord|jesus|prayer)\b|@",
    re.IGNORECASE,
)
_PHONE = re.compile(r"\d{3}[\s-]?\d{3,4}[\s-]?\d{3,4}")
GNHK_DROP = {
    4,
    19,
    23,
    37,
    42,
    57,
    59,
    65,
    66,
    68,
    84,
    87,
    92,
    101,
    102,
    110,
    117,
    146,
    150,
    154,
    159,
    163,
    165,
    178,
    185,
    187,
    189,
    194,
    209,
    211,
    214,
    216,
    234,
    242,
    243,
    245,
    249,
    250,
    252,
    260,
    264,
    279,
    283,
    285,
    291,
    293,
    312,
    321,
    335,
    342,
    346,
    347,
    352,
    357,
    362,
    370,
    378,
    390,
    392,
    401,
    402,
    407,
    409,
    410,
    418,
    423,
    436,
    441,
    465,
    472,
    474,
    478,
    483,
    484,
    492,
    503,
    511,
}


def gnhk_fetch(excluded: set[int]) -> list[dict]:
    """A seeded draw of 48 GNHK rows that pass the personal-data screen, with their photos."""
    path = CACHE / "gnhk_chosen.json"
    if not path.exists():
        rows = []
        for r in _hf_rows("Berzerker/gnhk_ocr_dataset", "train"):
            lines = json.loads(r["row"]["output_json_dumpsed"]).splitlines()  # "x y w h word" per line
            text = " ".join(line.split(" ", 4)[4] for line in lines if line.count(" ") >= 4)
            if len(text.split()) >= 25 and not _GNHK_PERSONAL.search(text) and not _PHONE.search(text):
                rows.append({"row_idx": r["row_idx"], "text": text, "src": r["row"]["image"]["src"]})
        pool = [r for r in rows if r["row_idx"] not in GNHK_DROP | excluded]
        chosen = sorted(random.Random("fresh-gnhk").sample(pool, 48), key=lambda r: r["row_idx"])
        _download_all([(r["src"], RAW / "gnhk" / f"train_{r['row_idx']}.jpg") for r in chosen])
        path.write_text(json.dumps([{k: v for k, v in r.items() if k != "src"} for r in chosen], ensure_ascii=False))
    return json.loads(path.read_text())


# ---------------------------------------------------------------- candidate pages


def gt_lanes(text_layer: str, lab: dict) -> list[str]:
    """Acceptable lanes, by the fixed mapping of bench/jev_lanes/probe.py (gt_lanes)."""
    if lab.get("hw") == "mostly":
        return ["L5"]
    if text_layer == "trusted":
        if lab.get("complex") is None:
            return ["L1", "L2"]
        return ["L2"] if lab["complex"] else ["L1"]
    if lab.get("degraded") is None:
        return ["L3", "L4"]
    return ["L4"] if lab["degraded"] else ["L3"]


@dataclass
class Page:
    key: str  # source key, e.g. "olm/old_scans/12"; the visual labels are keyed by it
    src: Path  # the raw PDF or image
    source: str  # attribution, written to cases.jsonl
    text_layer: str  # "trusted", or why the page needs OCR: "none", "ocr" (an OCR layer) or "garbled"
    lab: dict = field(default_factory=dict)  # hw, complex, degraded; None until known
    look: bool = False  # the label needs the visual check before the page can be used
    as_pdf: bool = False  # ship the single-page PDF rather than a 1024 px JPEG
    stratum: str = ""  # the draw for the visual check and the selection quotas work per stratum

    @property
    def gt(self) -> list[str]:
        return gt_lanes(self.text_layer, self.lab)


def _short(stem: str) -> str:
    """A source file stem as a key part: long hashes cut to 8 characters, ASCII only."""
    stem = re.sub(r"[0-9a-f]{16,}", lambda m: m.group(0)[:8], stem.replace("_processed", ""))
    return re.sub(r"[^A-Za-z0-9.]+", "_", stem).strip("_")


def pdf_facts(path: Path) -> dict:
    """Text layer, image coverage and invisible (OCR-layer) text of page 1."""
    page = pdfium.PdfDocument(str(path))[0]
    w, h = page.get_size()
    area = 0.0
    for obj in page.get_objects(max_depth=3):
        if obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE:
            left, bottom, right, top = obj.get_bounds()
            area += max(0.0, min(right, w) - max(left, 0.0)) * max(0.0, min(top, h) - max(bottom, 0.0))
    with pikepdf.open(path) as pdf:
        streams = pdf.pages[0].obj.get("/Contents")
        streams = streams if isinstance(streams, pikepdf.Array) else [streams] if streams is not None else []
        content = b"".join(s.read_bytes() for s in streams)
    return {
        "text": page.get_textpage().get_text_bounded(),
        "image_coverage": min(1.0, area / (w * h)),
        "invisible_text": bool(re.search(rb"(^|\s)3\s+Tr\b", content)),
    }


def _odd_share(text: str) -> float:
    body = "".join(text.split())
    return sum(unicodedata.category(c) in ("Co", "Cn", "Cc") or c == "�" for c in body) / max(1, len(body))


def text_layer_ok(text: str) -> bool:
    """A real, readable text layer: enough text, no cid glyph codes, few unmapped or control characters."""
    return (
        len("".join(text.split())) >= 200
        and "(cid:" not in text
        and _odd_share(text) < 0.01
        and len(re.findall(r"[^\W\d_]{2,}", text)) >= 30
    )


def _pdf_page(key: str, path: Path, source: str, complex_: bool | None) -> Page | None:
    """A PDF page by its structure: a full-page image is a scan whatever text sits over it; a readable text layer is
    born-digital; a broken one is a real garbled layer; anything else is left out. The stratum says which."""
    facts = pdf_facts(path)
    chars = len("".join(facts["text"].split()))
    if facts["image_coverage"] >= 0.9:
        layer = "ocr" if chars > 50 else "none"
        small = path.stat().st_size <= 350_000  # image-only scans ship as PDFs only when small
        return Page(key, path, source, layer, look=True, as_pdf=layer == "ocr" or small, stratum="scan")
    if text_layer_ok(facts["text"]):
        lab = {"hw": "none", "complex": complex_}
        return Page(key, path, source, "trusted", lab, look=complex_ is None, as_pdf=True, stratum="digital")
    if chars >= 200 and ("(cid:" in facts["text"] or _odd_share(facts["text"]) >= 0.2):
        source += " (garbled text layer)"
        return Page(key, path, source, "garbled", {"hw": "none"}, look=True, as_pdf=True, stratum="garbled")
    return None


def olm_pages(excluded: set[str]) -> list[Page]:
    """olmOCR-Bench: born-digital arxiv_math, tables and multi_column pages are L2 by category; the other born-digital
    pages and every scan are looked at."""
    pages = []
    for path in olm_fetch(excluded):
        cat = path.parent.name
        by_category = cat in ("arxiv_math", "tables", "multi_column")
        source = f"olmOCR-Bench ({OLM_REPO}), bench_data/pdfs/{cat}/{path.name}"
        page = _pdf_page(f"olm/{cat}/{_short(path.stem)}", path, source, True if by_category else None)
        if page is not None:
            digital = f"olm-{cat}" if by_category else "olm-digital"
            page.stratum = {"scan": f"olm-scan-{cat}", "digital": digital, "garbled": "olm-garbled"}[page.stratum]
            pages.append(page)
    return pages


def dln_pages() -> list[Page]:
    """DocLayNet: born-digital pages with a table or formula box are L2 by their layout labels; the other born-digital
    pages are looked at for columns and code, and scans for their condition."""
    pages = []
    for m in doclaynet_fetch():
        by_layout = bool({DLN_TABLE, DLN_FORMULA} & set(m["categories"]))
        source = (
            f"DocLayNet v1.2 ({DLN_DATASET}), test row {m['row_idx']}: {m['original_filename']} "
            f"page {m['page_no']} ({m['doc_category']})"
        )
        path = RAW / "doclaynet" / f"test_{m['row_idx']}.pdf"
        page = _pdf_page(f"dln/{m['row_idx']}", path, source, True if by_layout else None)
        if page is not None and page.stratum != "garbled":
            digital = f"dln-complex-{m['doc_category']}" if by_layout else "dln-simple"
            page.stratum = {"scan": "dln-scan", "digital": digital}[page.stratum]
            pages.append(page)
    return pages


def pdb_pages(excluded: set[str]) -> list[Page]:
    """PureDocBench triplets as image files: the clean render is L3; the degraded tracks are looked at."""
    pages = []
    for t in pdb_fetch(excluded):
        source = f"PureDocBench (zhihengli-casia/puredocbench), page_id={t['page_id']}"
        camera = t["real_chain"] != "screenshot_compressed"  # every other real-degraded chain is a phone capture
        tracks = {
            "clean": ("clean track", False, False),
            "digital": ("digital-degraded track", None, True),
            "real": (f"real-degraded track, {t['real_chain']}", True if camera else None, True),
        }
        clean = pdb_file(t, "clean").read_bytes()
        for track, (note, degraded, look) in tracks.items():
            if track != "clean" and pdb_file(t, track).read_bytes() == clean:
                continue  # the release ships a few degraded-track files that are copies of the clean render
            pages.append(
                Page(
                    f"pdb/{t['key']}/{track}",
                    pdb_file(t, track),
                    f"{source} ({note})",
                    "none",
                    {"hw": "none", "degraded": degraded},
                    look=look,
                    stratum=f"pdb-{track}",
                )
            )
    return pages


def image_pages() -> list[Page]:
    """The page-image datasets. Every page is looked at: condition, handwriting and personal data."""
    pages = []
    for r in _rows_with_images("nielsr/funsd", "train", "funsd"):
        pages.append(
            Page(
                f"funsd/{r['row_idx']}",
                RAW / "funsd" / f"train_{r['row_idx']}.jpg",
                f"FUNSD train split via nielsr/funsd, row_idx={r['row_idx']}",
                "none",
                look=True,
                stratum="funsd",
            )
        )
    for r in gnhk_fetch(evalset_sources()["gnhk"]):
        pages.append(
            Page(
                f"gnhk/{r['row_idx']}",
                RAW / "gnhk" / f"train_{r['row_idx']}.jpg",
                f"GNHK via HF mirror Berzerker/gnhk_ocr_dataset, row_idx={r['row_idx']}",
                "none",
                {"hw": "mostly"},
                look=True,
                stratum="gnhk",
            )
        )
    cord = _sample(100, 40, "fresh-cord")
    for r in _rows_with_images("naver-clova-ix/cord-v2", "test", "cord", lambda r: r["row_idx"] in cord):
        pages.append(
            Page(
                f"cord/{r['row_idx']}",
                RAW / "cord" / f"test_{r['row_idx']}.jpg",
                f"CORD v2 (naver-clova-ix/cord-v2) test split, row_idx={r['row_idx']}, phone photo",
                "none",
                {"hw": "none", "degraded": True},
                look=True,
                stratum="cord",
            )
        )
    sroie = _sample(361, 36, "fresh-sroie")
    for r in _rows_with_images("jsdnrs/ICDAR2019-SROIE", "test", "sroie", lambda r: r["row_idx"] in sroie):
        pages.append(
            Page(
                f"sroie/{r['row_idx']}",
                RAW / "sroie" / f"test_{r['row_idx']}.jpg",
                f"ICDAR 2019 SROIE (jsdnrs/ICDAR2019-SROIE) test split, row_idx={r['row_idx']}",
                "none",
                look=True,
                stratum="sroie",
            )
        )
    rvl = "jordyvl/rvl_cdip_100_examples_per_class"
    for r in _rows_with_images(rvl, "test", "rvl", lambda r: RVL_CLASSES[r["row"]["label"]] != "resume"):
        label = RVL_CLASSES[r["label"]]
        pages.append(
            Page(
                f"rvl/{r['row_idx']}",
                RAW / "rvl" / f"test_{r['row_idx']}.jpg",
                f"RVL-CDIP ({rvl}) test split, row_idx={r['row_idx']}, class {label}",
                "none",
                look=True,
                stratum=f"rvl-{label.replace(' ', '_')}",
            )
        )
    for p in omni_fetch():
        attr = p["page_attribute"]
        hard = bool(OMNI_HARD & set(attr["special_issue"]))
        issues = f", {', '.join(attr['special_issue'])}" if attr["special_issue"] else ""
        pages.append(
            Page(
                f"omni/{_short(Path(p['image_path']).stem)}",
                RAW / "omni" / p["image_path"],
                f"OmniDocBench ({OMNI_REPO}), images/{p['image_path']} ({attr['data_source']}, "
                f"{attr['language']}{issues})",
                "none",
                {"degraded": True} if hard else {},
                look=True,
                stratum="omni-hard" if hard else f"omni-{attr['data_source']}",
            )
        )
    return pages


def candidates() -> list[Page]:
    excluded = evalset_sources()
    pages = olm_pages(excluded["olmocr"]) + dln_pages() + pdb_pages(excluded["pdb"]) + image_pages()
    assert len({p.key for p in pages}) == len(pages), "source keys must be unique"
    return pages


# ---------------------------------------------------------------- the visual check

# Looked-at pages drawn for the check, per stratum (all of a stratum that is not listed).
VIEW = {
    "olm-digital": 92,
    "olm-scan-old_scans": 40,
    "olm-scan-headers_footers": 20,
    "olm-scan-multi_column": 12,
    "olm-scan-tables": 12,
    "olm-scan-old_scans_math": 8,
    "olm-scan-long_tiny_text": 8,
    "dln-simple": 80,
    "dln-scan": 30,
    "funsd": 32,
    "cord": 30,
    "sroie": 24,
    "omni-exam_paper": 10,
    "omni-book": 6,
    **{f"rvl-{c.replace(' ', '_')}": 4 for c in RVL_CLASSES},
    "rvl-handwritten": 25,
    "rvl-letter": 0,  # correspondence between named people
    "rvl-memo": 0,
    "rvl-email": 0,
}
VISUAL_CODES = {
    "simple": {"complex": False},
    "complex": {"complex": True},
    "complex?": {"complex": None},
    "clean": {"hw": "none", "degraded": False},
    "degraded": {"hw": "none", "degraded": True},
    "degraded?": {"hw": "none", "degraded": None},
    "hw": {"hw": "mostly"},
}
LAYOUT_CODES = {"simple", "complex", "complex?"}  # for pages with a trusted text layer; the rest take image codes


def _codes() -> dict[str, str]:
    """VISUAL as source key -> code."""
    return {
        line.split()[0]: line.split()[1] for line in (ln.split("#")[0] for ln in VISUAL.splitlines()) if line.strip()
    }


def viewed(pages: list[Page]) -> list[Page]:
    out = []
    for stratum, group in itertools.groupby(
        sorted((p for p in pages if p.look), key=lambda p: p.stratum), lambda p: p.stratum
    ):
        group = list(group)
        n = VIEW.get(stratum, len(group))
        out += group if n >= len(group) else random.Random(f"view-{stratum}").sample(group, n)
    return out


def labelled(pages: list[Page]) -> list[Page]:
    """Built pages, plus looked-at pages merged with their visual label. Drops and unchecked pages go."""
    codes, out = _codes(), []
    if unknown := codes.keys() - {p.key for p in pages}:
        raise ValueError(f"visual labels for pages that are not candidates: {sorted(unknown)[:5]}")
    for p in pages:
        code = codes.get(p.key)
        if code == "drop" or (p.look and code is None):
            continue
        if code is not None:
            if (code in LAYOUT_CODES) != (p.text_layer == "trusted"):
                raise ValueError(f"{p.key}: {code!r} does not fit a page whose text layer is {p.text_layer}")
            p.lab = {**p.lab, **VISUAL_CODES[code]}
        out.append(p)
    return out


def page_image(page: Page) -> Image.Image:
    """The page as a viewer sees it: PDFs rendered to 1024 px on the long side, photos turned upright."""
    if page.src.suffix == ".pdf":
        pdf_page = pdfium.PdfDocument(str(page.src))[0]
        return pdf_page.render(scale=1024 / max(pdf_page.get_size())).to_pil()
    with Image.open(page.src) as im:
        return ImageOps.exif_transpose(im).copy()


def sheets(pages: list[Page]) -> None:
    """Contact sheets of the drawn pages still waiting for a visual label: 12 to a sheet, per source."""
    out = CACHE / "sheets"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.jpg"):
        old.unlink()
    codes = _codes()
    todo = sorted((p for p in viewed(pages) if p.key not in codes), key=lambda p: p.key)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 15)
    except OSError:
        font = ImageFont.load_default()
    for source, group in itertools.groupby(todo, key=lambda p: p.key.split("/")[0]):
        group = list(group)
        for n in range(0, len(group), 12):
            sheet = Image.new("RGB", (4 * 404, 3 * 550), (120, 120, 120))
            for i, p in enumerate(group[n : n + 12]):
                im = page_image(p).convert("RGB")
                im.thumbnail((400, 520))
                tile = Image.new("RGB", (400, 546), "white")
                tile.paste(im, ((400 - im.width) // 2, 0))
                ImageDraw.Draw(tile).text((4, 526), f"{p.key} [{p.stratum}]"[:46], fill="black", font=font)
                sheet.paste(tile, ((i % 4) * 404, (i // 4) * 550))
            sheet.save(out / f"{source}_{n // 12:02d}.jpg", quality=80)
    print(len(todo), "pages to label in", out)


# ---------------------------------------------------------------- selection and synthetic variants

# At most this many pages per "stratum lanes" group, drawn by a stable hash of the key; the first matching pattern
# applies to each group. Groups not listed are kept whole. The quotas balance the lanes and keep the set small.
KEEP = {
    "olm-digital L1": 24,
    "olm-digital L2": 8,
    "olm-arxiv_math L2": 6,
    "olm-tables L2": 6,
    "olm-multi_column L2": 6,
    "dln-simple L2": 6,
    "dln-complex-financial_reports L2": 6,
    "dln-complex-* L2": 4,
    "olm-scan-old_scans L5": 8,
    "olm-scan-* L3": 3,
    "olm-scan-* L3/L4": 2,
    "dln-scan L3": 6,
    "pdb-clean L3": 16,
    "pdb-digital L3/L4": 14,
    "pdb-digital L4": 12,
    "pdb-real L4": 18,
    "omni-hard L3/L4": 12,
    "omni-hard L4": 14,
    "omni-note L5": 10,
    "omni-* L3": 1,
    "rvl-* L3": 1,
    "rvl-* L3/L4": 1,
    "funsd L3": 6,
    "sroie L3": 4,
    "sroie L3/L4": 4,
    "sroie L4": 6,
    "cord L4": 20,
    "gnhk L5": 30,
}
# A second, blind labelling of the L4 image pages that route to L3, with as many L4 pages that route to L4 mixed in
# (the second labeller kept every one of those at L4). Where it saw a clean or borderline scan, the two labels
# disagree, so either lane is accepted; an OCR-layer copy of the page follows its image.
SECOND_LOOK = {
    "omni_jiaocaineedrop_jiaocai_needrop_en_108",  # L3/L4: crisp text but faint show-through of reverse
    "omni_jiaocaineedrop_jiaocai_needrop_en_1349",  # L3: watermark behind crisp text
    "omni_jiaocaineedrop_jiaocai_needrop_en_1509",  # L3: crisp, flat
    "omni_jiaocaineedrop_jiaocai_needrop_en_1523",  # L3: crisp, flat, mild JPEG softness
    "omni_jiaocaineedrop_jiaocai_needrop_en_2211",  # L3: watermark behind crisp text
    "omni_jiaocaineedrop_jiaocai_needrop_en_2360",  # L3: crisp, flat
    "omni_jiaocaineedrop_jiaocai_needrop_en_2825",  # L3/L4: crisp text but faint show-through of reverse
    "omni_jiaocaineedrop_jiaocai_needrop_en_2839",  # L3: watermark behind crisp text
    "pdb_book_004_digital",  # L3: banding stripes, glyphs still crisp
    "pdb_brochure_menu_004_digital",  # L3: banding stripes, glyphs crisp
    "pdb_magazine_004_digital",  # L3: banding stripes, glyphs crisp
    "pdb_product_manual_004_digital",  # L3: light banding, text crisp
    "pdb_technical_report_005_digital",  # L3: banding stripes, glyphs crisp
    "sroie_18",  # L3/L4: faded thin receipt print, some blotchy words
    "sroie_295",  # L3: light speckle, small crisp text
    "sroie_334",  # L3: light speckle, text crisp
    "sroie_340",  # L3: light speckle, text crisp
}
MAX_PDF_BYTES = 600_000  # the few larger PDFs (big embedded photos) are left out to keep the set small
SYNTH_CAPTURES = {"fax": 4, "camera": 4, "rotated": 2}  # made from born-digital pages that are not in the set
GARBLED_OVERRIDES = 12  # garbled text layers over born-digital PDFs in the set (evidence-level, no new file)
OCR_WRAPPED = 8  # tesseract OCR-layer PDFs made from image pages in the set
OLM_SHORT = {
    "arxiv_math": "math",
    "headers_footers": "hf",
    "long_tiny_text": "tiny",
    "multi_column": "cols",
    "old_scans": "old",
    "old_scans_math": "oldmath",
    "tables": "tables",
}


def _rank(key: str) -> str:
    return hashlib.sha256(f"fresh:{key}".encode()).hexdigest()


def select(pages: list[Page]) -> list[Page]:
    groups: dict[str, list[Page]] = {}
    for p in pages:
        if not (p.as_pdf and p.src.stat().st_size > MAX_PDF_BYTES):
            groups.setdefault(f"{p.stratum} {'/'.join(p.gt)}", []).append(p)
    out = []
    for name, group in sorted(groups.items()):
        n = next((v for pattern, v in KEEP.items() if fnmatch.fnmatchcase(name, pattern)), len(group))
        out += sorted(group, key=lambda p: _rank(p.key))[:n]
    return out


def _slug(key: str) -> str:
    parts = key.split("/")
    if parts[0] == "olm":
        parts[1] = OLM_SHORT[parts[1]]
    return "_".join(parts)[:72]


def garble(text: str, kind: str) -> str:
    """The broken text layers of bench/jev_lanes/probe.py: cid codes, a constant glyph offset, mojibake."""
    if kind == "cid":
        return "".join(f"(cid:{ord(c) % 97 + 3})" if c.isalpha() else c for c in text)
    if kind == "shift":  # glyph ids without a ToUnicode map often come out as a constant offset
        return "".join(chr(ord(c) + 29) if c.isalpha() else c for c in text)
    return text.encode("utf-8").decode("latin-1", errors="replace").replace("e", "Ã©").replace("a", "")


def _jpeg(im: Image.Image, dest: Path) -> None:
    """1024 px on the long side, JPEG quality 90; grayscale sources stay grayscale."""
    im = im.convert("L" if im.mode in ("1", "L", "LA", "I", "I;16") else "RGB")
    scale = 1024 / max(im.size)
    im.resize((round(im.width * scale), round(im.height * scale)), Image.Resampling.LANCZOS).save(
        dest, "JPEG", quality=90, optimize=True
    )


def assemble(pages: list[Page]) -> list[dict]:
    """Write files/ and return the cases; every file is checked against evalset/files by sha256."""
    files = HERE / "files"
    files.mkdir(exist_ok=True)
    for old in files.iterdir():
        old.unlink()
    pool = labelled(pages)
    chosen = select(pool)
    cases = []

    def add(case_id: str, file: str, gt: list[str], group: str, source: str, **extra: str) -> None:
        cases.append(
            {"id": case_id, "file": f"files/{file}", "page": 0, "gt": gt, "group": group, "source": source, **extra}
        )

    for p in chosen:
        slug = _slug(p.key)
        if p.as_pdf:
            group = "garb" if p.text_layer == "garbled" else "pdf"
            (files / f"{group}_{slug}.pdf").write_bytes(p.src.read_bytes())
            add(f"{group}_{slug}", f"{group}_{slug}.pdf", p.gt, group, p.source)
        else:
            _jpeg(page_image(p), files / f"img_{slug}.jpg")
            add(f"img_{slug}", f"img_{slug}.jpg", p.gt, "img", p.source)

    # Synthetic captures of born-digital pages left out of the set: a fax or a phone photo is L4, a page on its side L3.
    spare = sorted((p for p in pool if p.text_layer == "trusted" and p not in chosen), key=lambda p: _rank(p.key))
    makers = {"fax": make_fax, "camera": make_camera_photo, "rotated": rotate_page}
    for i, (kind, p) in enumerate(zip([k for k, n in SYNTH_CAPTURES.items() for _ in range(n)], spare, strict=False)):
        im = page_image(p).convert("RGB")
        im = makers[kind](im) if kind == "rotated" else makers[kind](im, seed=i)
        slug = f"synth_{kind}_{_slug(p.key)}"
        _jpeg(im, files / f"img_{slug}.jpg")
        gt = ["L3"] if kind == "rotated" else ["L4"]
        add(f"img_{slug}", f"img_{slug}.jpg", gt, "img", f"{p.source} ({kind} simulation, own construction)")

    # Garbled text layers over born-digital PDFs in the set: the page still needs OCR, and its image is clean (L3).
    digital = sorted((p for p in chosen if p.text_layer == "trusted"), key=lambda p: _rank("garble:" + p.key))
    for i, p in enumerate(digital[:GARBLED_OVERRIDES]):
        kind = ("cid", "shift", "mojibake")[i % 3]
        add(
            f"garb_{_slug(p.key)}_{kind}",
            f"pdf_{_slug(p.key)}.pdf",
            ["L3"],
            "garb",
            f"{p.source} (garbled text layer, evidence-level synthetic)",
            text_override=garble(pdf_facts(p.src)["text"], kind),
        )

    # OCR-layer PDFs of Latin-script image pages in the set: the layer is untrusted, so the lanes stay the image's.
    latin = ("funsd/", "rvl/", "sroie/", "cord/", "gnhk/", "olm/old_scans/")
    images = sorted(
        (p for p in chosen if not p.as_pdf and p.key.startswith(latin)), key=lambda p: _rank("ocr:" + p.key)
    )
    for p in images[:OCR_WRAPPED]:
        slug = _slug(p.key)
        base = CACHE / "ocr" / f"ocr_{slug}"
        base.parent.mkdir(exist_ok=True)
        subprocess.run(
            ["tesseract", str(files / f"img_{slug}.jpg"), str(base), "-l", "eng", "--dpi", "150", "pdf"],
            check=True,
            capture_output=True,
        )
        with pikepdf.open(base.with_suffix(".pdf")) as pdf:  # drop the timestamps so a rebuild gives the same bytes
            for stamp in ("/CreationDate", "/ModDate"):
                if stamp in pdf.docinfo:
                    del pdf.docinfo[stamp]
            pdf.save(files / f"ocr_{slug}.pdf", deterministic_id=True)
        add(f"ocr_{slug}", f"ocr_{slug}.pdf", p.gt, "ocr", f"{p.source} (OCR layer added with Tesseract)")

    for c in cases:
        if c["group"] in ("img", "ocr") and c["id"].split("_", 1)[1] in SECOND_LOOK:
            c["gt"] = ["L3", "L4"]
    images = {c["id"].split("_", 1)[1] for c in cases if c["group"] == "img"}
    assert SECOND_LOOK.issubset(images), "a second look names a page the set no longer holds"
    assert len({c["id"] for c in cases}) == len(cases), "case ids must be unique"
    digests = {hashlib.sha256(f.read_bytes()).hexdigest(): f.name for f in files.iterdir()}
    assert len(digests) == len(list(files.iterdir())), "two fresh files are identical"
    taken = {hashlib.sha256(f.read_bytes()).hexdigest() for f in (EVALSET / "files").iterdir()}
    assert not taken & digests.keys(), f"files already in evalset/: {[digests[d] for d in taken & digests.keys()]}"
    return sorted(cases, key=lambda c: (c["group"], c["id"]))


def main() -> None:
    pages = candidates()
    if sys.argv[1:] == ["sheets"]:
        sheets(pages)
        return
    cases = assemble(pages)
    with open(HERE / "cases.jsonl", "w", encoding="utf-8") as fh:
        fh.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in cases)
    lanes = sorted({"/".join(c["gt"]) for c in cases})
    table: dict[str, dict[str, int]] = {}
    for c in cases:
        synthetic = any(s in c["source"] for s in ("own construction", "evidence-level synthetic", "Tesseract"))
        family = c["source"].split(" (")[0].split(",")[0].split(" via ")[0] + (" [synthetic]" if synthetic else "")
        table.setdefault(family, dict.fromkeys(lanes, 0))["/".join(c["gt"])] += 1
    size = sum(f.stat().st_size for f in (HERE / "files").iterdir())
    print(f"{len(cases)} cases, {size / 1e6:.1f} MB")
    print("source".ljust(32), *(lane.rjust(6) for lane in lanes))
    for family, counts in sorted(table.items()):
        print(family.ljust(32), *(str(counts[lane]).rjust(6) for lane in lanes))


# One line per looked-at page: source key, code (a VISUAL_CODES key, or "drop"), and a note where it helps.
VISUAL = """
cord/2 degraded
cord/3 degraded
cord/8 degraded
cord/12 degraded
cord/15 degraded
cord/21 degraded
cord/24 degraded
cord/29 degraded
cord/32 degraded
cord/35 degraded
cord/36 degraded
cord/38 degraded
cord/40 degraded  # a phone-scanner capture, heavily washed out
cord/44 degraded
cord/48 degraded
cord/49 degraded
cord/54 degraded
cord/63 degraded?  # white background, looks like a scanner-app capture
cord/65 degraded
cord/69 degraded
cord/70 degraded
cord/78 degraded
cord/79 degraded
cord/90 degraded
cord/92 degraded
cord/93 degraded
cord/94 degraded
cord/96 degraded
cord/97 degraded
cord/98 degraded
dln/302 complex  # three columns
dln/315 complex  # two columns
dln/317 drop  # a customer profile built around a named person's photograph
dln/318 clean  # clean scan with no text layer
dln/321 complex  # three columns
dln/338 complex  # three columns
dln/341 simple
dln/345 simple  # a list of company directors
dln/346 drop  # a photograph of people with little text
dln/352 complex  # two columns
dln/357 drop  # a photograph, almost no text
dln/359 complex  # two columns
dln/360 drop  # mostly a photograph of people
dln/376 drop  # a photograph of named employees
dln/379 complex  # two columns
dln/383 simple
dln/388 complex  # two columns
dln/389 simple
dln/393 drop  # a customer profile built around a named person's photograph
dln/394 complex  # two columns
dln/397 complex  # two columns
dln/1107 simple
dln/1109 complex  # two text columns
dln/1113 complex  # three text columns
dln/1127 complex  # two text columns under a diagram
dln/1136 simple  # one text column and a map
dln/1145 simple  # one text column and a flow chart
dln/1149 complex  # three-column address directory
dln/1150 complex  # two columns
dln/1159 drop  # mostly a photograph of people
dln/1163 simple  # one text column beside a map
dln/1167 complex?  # organisation chart, no text columns
dln/1188 complex  # three text columns
dln/1193 complex  # two text columns
dln/1195 simple
dln/1196 complex  # two text columns
dln/1197 complex  # three-column directory
dln/2301 complex  # two columns with equations
dln/2306 complex  # two columns
dln/2310 complex  # two columns
dln/2315 complex
dln/2322 complex
dln/2327 complex  # two columns
dln/2328 complex
dln/2330 complex
dln/2331 complex
dln/2341 complex
dln/2344 complex  # two columns
dln/2349 complex  # two columns
dln/2351 complex
dln/2365 complex  # two columns
dln/2368 complex  # two-column references
dln/2377 complex
dln/2379 complex
dln/2383 complex  # two columns
dln/3004 simple  # one column with bullets
dln/3009 clean  # clean scan with an OCR layer
dln/3011 clean  # clean scan with an OCR layer
dln/3015 simple
dln/3020 clean  # clean scan with an OCR layer
dln/3022 simple
dln/3025 clean  # clean scan with an OCR layer
dln/3032 clean  # clean scan with an OCR layer
dln/3035 clean  # clean scan with an OCR layer
dln/3041 clean  # clean scan with an OCR layer
dln/3047 clean  # clean scan with an OCR layer
dln/3048 clean  # clean scan with an OCR layer
dln/3049 clean  # clean scan with an OCR layer
dln/3057 simple  # bullets and chart excerpts
dln/3060 complex  # two-column glossary
dln/3065 clean  # clean scan with an OCR layer
dln/3067 clean  # clean scan with an OCR layer
dln/3068 simple  # a list beside a diagram
dln/3073 clean  # clean scan with an OCR layer
dln/3074 clean  # clean scan with an OCR layer
dln/3080 clean  # clean scan with an OCR layer
dln/3085 clean  # clean scan with an OCR layer
dln/3088 clean  # clean scan with an OCR layer
dln/3092 complex?  # one column under a small boxed table
dln/3095 clean  # clean scan with an OCR layer
dln/3901 complex  # screen listing in monospace
dln/3906 complex  # three-column index
dln/3907 complex  # screen listings in monospace
dln/3910 simple
dln/3912 complex  # monospace screen listings
dln/3915 simple
dln/3917 simple
dln/3918 simple
dln/3923 complex  # monospace screen listing
dln/3926 complex  # monospace screen listing
dln/3932 simple
dln/3933 simple
dln/3936 simple
dln/3940 complex  # monospace screen listings
dln/3942 complex  # two columns of boxed text
dln/3945 simple
dln/3952 complex  # monospace screen listings
dln/3955 simple
dln/3957 complex  # two-column glossary
dln/3976 simple
dln/3978 simple
dln/3979 clean  # clean scan with no text layer
dln/3983 clean  # clean scan with no text layer
dln/3984 clean  # clean scan with no text layer
dln/3987 clean  # clean scan with no text layer
dln/3988 clean  # clean scan with no text layer
dln/3991 clean  # clean scan with no text layer
dln/3992 clean  # clean scan with no text layer
dln/3994 clean  # clean scan with no text layer
dln/3998 clean  # clean scan with no text layer
funsd/1 clean
funsd/4 clean
funsd/22 clean
funsd/31 clean
funsd/34 drop  # names a private plaintiff in an injury suit
funsd/36 degraded  # broken, speckled print
funsd/37 clean
funsd/58 clean
funsd/59 clean
funsd/64 clean
funsd/65 clean
funsd/69 clean
funsd/78 degraded?  # a fax cover sheet, legible
funsd/80 clean
funsd/83 clean
funsd/85 clean
funsd/87 clean
funsd/89 clean
funsd/92 degraded?  # a fax, legible
funsd/95 clean
funsd/100 clean
funsd/107 clean  # handwritten notes over a clean form
funsd/111 clean
funsd/112 degraded?  # noisy halftone header
funsd/114 clean
funsd/117 clean
funsd/121 clean
funsd/128 clean
funsd/133 degraded?  # a fax, legible
funsd/140 drop  # a litigation claimant's name and date of birth
funsd/141 clean
funsd/142 clean
gnhk/34 hw
gnhk/38 hw
gnhk/40 hw  # sideways
gnhk/55 hw
gnhk/82 hw
gnhk/83 hw  # sideways
gnhk/90 hw
gnhk/97 hw
gnhk/98 hw
gnhk/105 hw
gnhk/119 hw
gnhk/124 drop  # a printed diagram with handwritten labels: not clearly mostly handwritten
gnhk/133 hw
gnhk/173 hw
gnhk/218 hw
gnhk/223 hw
gnhk/226 hw
gnhk/235 hw
gnhk/248 hw
gnhk/262 hw
gnhk/276 drop  # a sales list naming customers
gnhk/298 hw
gnhk/301 hw  # photographed sideways
gnhk/318 hw
gnhk/320 hw
gnhk/324 hw
gnhk/329 hw
gnhk/332 hw
gnhk/337 hw
gnhk/339 hw
gnhk/354 hw
gnhk/356 hw
gnhk/371 hw  # sideways
gnhk/376 hw
gnhk/403 drop  # printed exam questions with handwritten answers: not clearly mostly handwritten
gnhk/406 hw  # upside down
gnhk/430 hw
gnhk/444 hw
gnhk/456 hw
gnhk/470 hw
gnhk/471 hw
gnhk/473 hw
gnhk/481 hw
gnhk/482 hw  # sideways
gnhk/487 hw
gnhk/493 hw
gnhk/508 hw
gnhk/510 hw
olm/headers_footers/0a5fbc4e_page_7 simple
olm/headers_footers/0a8610e7_page_1 simple
olm/headers_footers/0ae20716_page_6 complex  # two columns
olm/headers_footers/00c67a6c_page_12 complex  # two columns
olm/headers_footers/0c2450d3_page_1 complex  # two columns
olm/headers_footers/0ef848c6_page_6 simple
olm/headers_footers/1fbe22f0_page_6 complex  # two columns
olm/headers_footers/2cb8b9fb_page_2 complex  # two columns
olm/headers_footers/2f6acb03_page_8 simple
olm/headers_footers/3f4659b0_page_1 degraded?  # grainy newspaper scan
olm/headers_footers/3f932638_page_1 complex  # price table
olm/headers_footers/4b91e05f_page_1 clean
olm/headers_footers/04cea54b_page_1 simple  # a blank form
olm/headers_footers/4f4c20ab_page_1 simple
olm/headers_footers/6a3e0393_page_9 complex  # two columns
olm/headers_footers/06a69732_page_6 complex  # property table
olm/headers_footers/6b9ddb2b_page_4 simple
olm/headers_footers/006c33b9_page_10 complex  # two-column references
olm/headers_footers/6e6caf4c_page_1 simple
olm/headers_footers/6ed2822b_page_5 simple
olm/headers_footers/7ddc63ce_page_72 simple
olm/headers_footers/7e384245_page_2 simple
olm/headers_footers/7fdd8933_page_9 complex  # two columns
olm/headers_footers/8dcbce41_page_13 clean
olm/headers_footers/8e953483_page_21 complex  # tax form table
olm/headers_footers/8f76c6ef_page_12 simple
olm/headers_footers/8fda461e_page_11 complex  # table
olm/headers_footers/09bfc0f3_page_3 simple
olm/headers_footers/9e4735e2_page_3 complex  # two columns
olm/headers_footers/9f896cbb_page_12 simple
olm/headers_footers/12abc83c_page_144 complex  # two-column index
olm/headers_footers/12cf936d_page_9 clean  # garbled layer over a clean Persian page
olm/headers_footers/13e2b289_page_32 simple
olm/headers_footers/17ce5025_page_1 complex  # course table
olm/headers_footers/025a6b47_page_1 simple  # a map with a legend
olm/headers_footers/029b20b3_page_6 simple
olm/headers_footers/030ae7ca_page_32 complex  # two-column list
olm/headers_footers/30bf26b6_page_38 clean
olm/headers_footers/34dc485d_page_170 simple
olm/headers_footers/39c4b332_page_5 simple
olm/headers_footers/47fdbae4_page_32 clean  # a slide as one image
olm/headers_footers/060c2cf8_page_9 clean
olm/headers_footers/70b11ae2_page_5 clean  # garbled layer over clean Persian tables
olm/headers_footers/87edbc40_page_1 simple
olm/headers_footers/88c0a6de_page_1 complex  # a blank form laid out in boxed fields
olm/headers_footers/148c79ae_page_9 clean  # charts embedded as one image
olm/headers_footers/0184e1ce_page_6 complex  # two columns
olm/headers_footers/385c01ed_page_9 clean
olm/headers_footers/0805b42e_page_2 simple
olm/headers_footers/911b6932_page_64 simple
olm/headers_footers/957b8963_page_8 clean
olm/headers_footers/958d5687_page_6 complex  # equations
olm/headers_footers/1218c2e6_page_3 clean  # patent drawing sheet
olm/headers_footers/1245af60_page_6 complex  # table and charts
olm/headers_footers/3734d658_page_1 complex  # course table
olm/headers_footers/6585e7a6_page_2 simple
olm/headers_footers/7825b0e2_page_5 simple
olm/headers_footers/8063d40c_page_1 clean  # Bengali notice
olm/headers_footers/008086ee_page_2 clean
olm/headers_footers/8648fed4_page_1 simple
olm/headers_footers/9009e616_page_1 complex  # two columns
olm/headers_footers/13352c55_page_15 clean
olm/headers_footers/29019be3_page_1 simple  # a checklist
olm/headers_footers/34530cb5_page_25 simple  # reference list
olm/headers_footers/38981f20_page_11 simple
olm/headers_footers/52282f90_page_6 complex  # two columns
olm/headers_footers/55256caf_page_4 complex  # tables
olm/headers_footers/73071ef7_page_1 complex  # boxed field table
olm/headers_footers/138610e5_page_2 complex  # two columns
olm/headers_footers/0188595f_page_1 simple  # chapter title and contents list
olm/headers_footers/0383177b_page_1 drop  # a certificate naming a student
olm/headers_footers/451431d1_page_1 clean  # press clipping
olm/headers_footers/0678963a_page_2 simple
olm/headers_footers/848067e3_page_2 simple
olm/headers_footers/3004640a_page_4 complex  # two columns
olm/headers_footers/3754542b_page_4 simple
olm/headers_footers/78643402_page_1 complex  # bid tabulation table
olm/headers_footers/a4bf0c8a_page_1 complex  # two columns
olm/headers_footers/a9d90977_page_4 simple
olm/headers_footers/a09e0320_page_6 clean  # garbled layer over a clean Arabic page
olm/headers_footers/a85bbe20_page_11 simple
olm/headers_footers/a2704890_page_4 complex  # two columns
olm/headers_footers/af928f58_page_1 simple
olm/headers_footers/af288944_page_4 complex  # two columns and a table
olm/headers_footers/b1bcaf90_page_13 simple  # monospaced legal text, one column
olm/headers_footers/b2ca8e00_page_2 simple
olm/headers_footers/b51e32be_page_1 complex  # two columns
olm/headers_footers/b79ccdcb_page_19 simple  # slide handout
olm/headers_footers/b329b808_page_3 drop  # mostly photographs of people
olm/headers_footers/b409e077_page_8 simple
olm/headers_footers/bab14288_page_6 complex  # two columns
olm/headers_footers/bec1f712_page_9 simple
olm/headers_footers/c2f9c3c5_page_2 simple
olm/headers_footers/cea8801d_page_3 simple  # figure page
olm/headers_footers/d76a8019_page_8 complex  # statistics table
olm/headers_footers/d93aa3ed_page_4 complex  # two columns
olm/headers_footers/d660c61f_page_12 clean
olm/headers_footers/dc851826_page_37 complex?  # inline chemical formulas
olm/headers_footers/e7f89d27_page_1 clean
olm/headers_footers/e21f9a88_page_1 simple
olm/headers_footers/e83afed6_page_1 complex  # two columns
olm/headers_footers/e99fc594_page_1 simple  # a thesis title page
olm/headers_footers/e1877d4f_page_7 simple
olm/headers_footers/ed107236_page_2 simple
olm/headers_footers/ef5e1f59_page_26 simple
olm/headers_footers/f9f5429b_page_5 clean
olm/headers_footers/f7559ece_page_1 simple
olm/headers_footers/f7469518_page_1 clean  # illustrated poster as one image
olm/headers_footers/fc5b2acd_page_17 simple
olm/headers_footers/fd9f7d29_page_37 simple
olm/headers_footers/fe8c6edb_page_3 degraded?  # yellowed book page
olm/headers_footers/fe8d3e95_page_16 complex  # equations
olm/long_tiny_text/10a_pg1 clean  # dense two-column dictionary scan
olm/long_tiny_text/12_pg71_pg1 complex  # two-column references
olm/long_tiny_text/12_pg174_pg1 complex  # two-column references
olm/long_tiny_text/13_pg67_pg1 clean
olm/long_tiny_text/13_pg556_pg1 clean
olm/long_tiny_text/13_pg811_pg1 clean
olm/long_tiny_text/15c_pg1 degraded?  # yellowed, tiny print
olm/long_tiny_text/17_pg17_pg1 degraded  # yellowed two-page spread photo
olm/long_tiny_text/17_pg33_pg1 degraded  # yellowed spread photo, tinted
olm/long_tiny_text/17_pg34_pg1 degraded  # yellowed spread photo, tinted
olm/long_tiny_text/20_pg39_pg1 complex  # multi-column listings
olm/multi_column/0b2e551b_page_9_pg1 clean
olm/multi_column/0cf93d93_page_5_pg1 clean
olm/multi_column/0d7f2cbc_page_6_pg1 clean
olm/multi_column/00d8a44d_page_1_pg1 clean
olm/multi_column/02a3e23d_page_12_pg1 clean
olm/multi_column/02a3e23d_page_16_pg1 clean
olm/multi_column/02a3e23d_page_17_pg1 clean
olm/multi_column/02e31046_page_5_pg1 clean
olm/multi_column/05a0e5bc_page_3_pg1 clean  # garbled layer over a clean born-digital page
olm/multi_column/065d792c_page_9_pg1 clean
olm/multi_column/075cc4e9_page_11_pg1 clean
olm/multi_column/075cc4e9_page_13_pg1 clean
olm/multi_column/0353b31c_page_5_pg1 clean
olm/old_scans/8 hw
olm/old_scans/9 clean  # typed letter
olm/old_scans/12 hw  # handwritten letter, 1914
olm/old_scans/15 clean  # typed letter
olm/old_scans/18 hw
olm/old_scans/19 hw
olm/old_scans/20 hw
olm/old_scans/21 hw
olm/old_scans/23 clean  # typed letter
olm/old_scans/24 clean  # typed letter
olm/old_scans/25 clean  # typed letter
olm/old_scans/27 hw
olm/old_scans/29 hw
olm/old_scans/31 clean  # typed letter
olm/old_scans/35 hw
olm/old_scans/36 degraded?  # printed 1862 statement on aged paper
olm/old_scans/39 hw
olm/old_scans/41 hw
olm/old_scans/47 hw
olm/old_scans/48 hw
olm/old_scans/50 hw
olm/old_scans/52 hw
olm/old_scans/54 hw
olm/old_scans/57 hw
olm/old_scans/59 clean  # typed spread
olm/old_scans/62 clean  # typed letters
olm/old_scans/63 clean  # printed bulletin cover
olm/old_scans/67 degraded?  # dense tiny tables across a spread
olm/old_scans/71 degraded?  # newspaper spread, tiny print
olm/old_scans/72 clean  # newspaper page
olm/old_scans/75 degraded  # clippings with heavy ink marks
olm/old_scans/76 hw
olm/old_scans/83 hw
olm/old_scans/84 hw
olm/old_scans/85 hw
olm/old_scans/87 hw
olm/old_scans/91 hw
olm/old_scans/94 drop  # a handwritten letter beside a printed newsletter: mixed
olm/old_scans/98 hw
olm/old_scans/99 hw
olm/old_scans_math/1_pg10 clean
olm/old_scans_math/1_pg19 clean
olm/old_scans_math/1_pg61 clean
olm/old_scans_math/1_pg113 clean
olm/old_scans_math/2_pg349 degraded?  # yellowed book page
olm/old_scans_math/4_pg98 degraded?  # yellowed book page
olm/old_scans_math/4_pg355 degraded?  # yellowed book page
olm/old_scans_math/5_pg281 clean
olm/tables/2d0e0586_pg373 clean
olm/tables/5fd60eb1_pg15_pg1 clean  # a slide as one image
olm/tables/6d48ac02_pg9 clean
olm/tables/0486cc2e_pg1 clean  # garbled layer over a clean born-digital page
olm/tables/26076dc3_pg3_pg1 clean
olm/tables/77895f72_pg1 clean
olm/tables/533600ba_pg20_pg1 clean
olm/tables/6130975d_pg11 clean
olm/tables/8097792c_pg1 degraded?  # faint dot-matrix print
olm/tables/b773892d_pg1_pg1 clean
olm/tables/d896f9ae_pg4_pg1 clean
olm/tables/df96e707_pg6_pg1 clean
olm/tables/f2ad0cd0_pg1_pg1 clean
omni/PPT_11.2013EvaluatingTraineeteacherproficiency_page_029 clean
omni/PPT_B14_Claeys_Consistent_Presentation_of_Images_v2_page_006 clean
omni/PPT_PresentationSpecification_page_007 clean
omni/PPT_english_studies_s6_on_the_road_resource_3_page_003 clean
omni/book_en_A.Course.in.Abstract.Harmonic.Analysis._.Gerald.B.Folland.0849384907_page_119 clean
omni/color_textbook_zhonggaokao_KET_KET_KET_25_10_01_page_004 clean
omni/color_textbook_zhonggaokao_KET_KET_KET_25_10_04_KET_KET_page_003 clean
omni/color_textbook_zhonggaokao_KET_KET_KET_25_10_10_Part9_Part9_page_010 clean
omni/docstructbench_dianzishu_zhongwenzaixian_o.O_61522126.pdf_206 clean
omni/docstructbench_dianzishu_zhongwenzaixian_o.O_63688043.pdf_110 clean
omni/docstructbench_llm_raw_scihub_o.O_chin.201025015.pdf_1 clean
omni/eastmoney_a2542ccf.pdf_2 clean
omni/eastmoney_c1c12db9.pdf_1 clean
omni/exam_paper_2004_2019_page_010 degraded  # faded, fuzzy scan
omni/exam_paper_2004_2019_page_050 degraded  # faded, fuzzy scan
omni/exam_paper_2018_page_003 clean
omni/exam_paper_en_file_putnam_archive_1998_Solutions_1998s_page_002 clean
omni/exam_paper_en_file_putnam_archive_2000_Solutions_2000s_page_003 clean
omni/jiaocaineedrop_5f9c4ab0.pdf_2 clean
omni/jiaocaineedrop_2005_QP.pdf_5 degraded?  # flagged fuzzy, looks clean
omni/jiaocaineedrop_bde81e42.pdf_14 drop  # a list of named private people with photographs
omni/jiaocaineedrop_bio_113065.pdf_213 clean
omni/jiaocaineedrop_chem_203343.pdf_121 clean
omni/jiaocaineedrop_jiaocai_needrop_en_16 clean
omni/jiaocaineedrop_jiaocai_needrop_en_85 drop  # nearly blank page
omni/jiaocaineedrop_jiaocai_needrop_en_108 degraded  # grey, soft scan
omni/jiaocaineedrop_jiaocai_needrop_en_155 clean
omni/jiaocaineedrop_jiaocai_needrop_en_250 degraded?  # flagged fuzzy, looks clean
omni/jiaocaineedrop_jiaocai_needrop_en_453 degraded?  # repeated watermark over the text
omni/jiaocaineedrop_jiaocai_needrop_en_467 degraded?  # flagged fuzzy, looks clean
omni/jiaocaineedrop_jiaocai_needrop_en_601 degraded?  # flagged fuzzy, looks clean
omni/jiaocaineedrop_jiaocai_needrop_en_678 clean
omni/jiaocaineedrop_jiaocai_needrop_en_854 degraded?  # flagged fuzzy, looks clean
omni/jiaocaineedrop_jiaocai_needrop_en_887 degraded?  # flagged fuzzy, looks clean
omni/jiaocaineedrop_jiaocai_needrop_en_913 degraded?  # flagged fuzzy, looks clean
omni/jiaocaineedrop_jiaocai_needrop_en_1118 clean
omni/jiaocaineedrop_jiaocai_needrop_en_1141 degraded  # curved, tinted capture
omni/jiaocaineedrop_jiaocai_needrop_en_1349 degraded  # faded two-page spread, tiny print
omni/jiaocaineedrop_jiaocai_needrop_en_1509 degraded  # faded
omni/jiaocaineedrop_jiaocai_needrop_en_1523 degraded  # washed out
omni/jiaocaineedrop_jiaocai_needrop_en_1719 degraded?  # flagged fuzzy, looks clean
omni/jiaocaineedrop_jiaocai_needrop_en_1776 drop  # nearly blank page
omni/jiaocaineedrop_jiaocai_needrop_en_1898 degraded?  # flagged fuzzy, looks clean
omni/jiaocaineedrop_jiaocai_needrop_en_2124 clean
omni/jiaocaineedrop_jiaocai_needrop_en_2211 degraded  # faded two-page spread, tiny print
omni/jiaocaineedrop_jiaocai_needrop_en_2360 degraded  # faded two-page spread, tiny print
omni/jiaocaineedrop_jiaocai_needrop_en_2509 degraded?  # flagged fuzzy, looks clean
omni/jiaocaineedrop_jiaocai_needrop_en_2755 clean
omni/jiaocaineedrop_jiaocai_needrop_en_2825 degraded  # grainy, tinted
omni/jiaocaineedrop_jiaocai_needrop_en_2839 degraded  # grey two-page spread, tiny print
omni/jiaocaineedrop_jiaocai_needrop_en_2982 degraded?  # repeated watermark over the text
omni/jiaocaineedrop_jiaocai_needrop_en_3009 degraded?  # flagged fuzzy, looks clean
omni/jiaocaineedrop_jiaocai_needrop_en_3313 degraded?  # beige tint
omni/jiaocaineedrop_jiaocai_needrop_en_3361 degraded?  # flagged fuzzy, looks clean
omni/jiaocaineedrop_jiaocai_needrop_en_3751 degraded?  # flagged fuzzy, looks clean
omni/magazine_TheEconomist.2023.11.18_page_071 clean
omni/magazine_TheEconomist.2023.12.16_page_026 clean
omni/magazine_TheEconomist.2024.03.09_page_016 clean
omni/magazine_TheEconomist.2024.03.09_page_079 clean
omni/newspaper_9bb9e05d_1 clean
omni/newspaper_02912feb_1 clean
omni/newspaper_TheGuardianUS_2025_1_8_magazinesclubnew_page_029 clean
omni/newspaper_The_Guardian_UK_0801_magazinesclubnew_page_061 clean
omni/newspaper_USAToday_2025_01_08_magazinesclubnew_page_024 clean
omni/newspaper_a105e3b0_1 clean
omni/notes_1ba14cb3_16 hw
omni/notes_1ba14cb3_32 hw
omni/notes_1ba14cb3_33 hw
omni/notes_1ba14cb3_35 hw
omni/notes_1ba14cb3_53 hw
omni/notes_1ba14cb3_55 hw
omni/notes_1ba14cb3_56 hw
omni/notes_1ba14cb3_76 hw
omni/notes_1ba14cb3_78 hw
omni/notes_1ba14cb3_96 hw
omni/notes_1ba14cb3_100 hw
omni/notes_1ba14cb3_101 hw
omni/notes_1ba14cb3_121 hw
omni/notes_9e951846_13 hw
omni/notes_f7f010b7_2 hw
omni/notes_f7f010b7_5 drop  # a blank ruled page
omni/notes_f7f010b7_25 hw
omni/notes_f7f010b7_27 hw
omni/notes_f7f010b7_29 hw
omni/notes_f7f010b7_30 hw
omni/notes_f7f010b7_45 hw
omni/notes_f7f010b7_46 hw
omni/notes_f7f010b7_49 hw
omni/notes_f7f010b7_50 hw
omni/notes_f7f010b7_51 hw
omni/notes_f7f010b7_52 hw
omni/notes_f7f010b7_53 hw
omni/notes_f7f010b7_90 hw
omni/notes_f7f010b7_91 hw
omni/notes_f7f010b7_116 hw
omni/page_0c1be55c_0b1b_4d62_b17d_ed752f9af9f2 degraded?  # grey cast, slight skew
omni/page_2ff22832_e343_46a7_b94f_47ed864ce486 clean
omni/page_3c690b07_30d7_4e77_bf20_012f0080fb1d clean
omni/page_3ecc67a1_9b19_4fb9_b74d_acbb73db5c53 clean
omni/page_4b8f8a9d_e061_4207_a42e_ebf9b7090099 degraded?  # watermark over the text
omni/page_07b33434_d7fe_4ada_b764_ba2df172d1fb degraded?  # grey cast
omni/page_8e2f7ce3_83c4_4977_b6dc_278394c4bd64 degraded?  # bold blotchy print
omni/page_014dee5d_dfce_406b_925e_4ec8ffe4ac16 degraded  # skewed, blurred capture
omni/page_28c45f5f_7e0d_464a_89ec_8de3a4abb927 degraded?  # flagged fuzzy, looks clean
omni/page_942ac90d_4704_43f3_9286_719c7be9e655 clean
omni/page_4540d82a_19d8_44ef_8f18_6d42fdb2a2de degraded  # washed-out photo of a spread
omni/page_07088b2f_f9d6_4c38_9c97_d7f98bc3d556 degraded  # high-contrast photocopy with black borders
omni/page_47977c29_59ca_4534_9a00_becad3bfdaa4 clean
omni/page_50209df6_f404_4e67_a646_bc9697f2e214 degraded  # photo of a spread, curved pages
omni/page_52875b3d_f4dc_44c2_a9bb_514b0763833d clean
omni/page_776044e4_c33c_420d_84a8_acbffad569bd degraded  # photographed magazine page
omni/page_af9aded3_1faf_4d12_ad5f_28a66d0a9114 degraded?  # grey scan, faint watermark
omni/page_b13fef06_6ae9_4b2d_a948_0340e03f97ce degraded?  # grey noisy scan
omni/page_b21c7247_a843_4316_a44d_c3365077f077 clean
omni/page_b145da5c_182f_4d4e_813a_28b8d6971b0f clean
omni/page_c018d221_68b3_4a14_84cd_c9abde2db3a4 degraded  # dark photo of a book spread
omni/page_dad79c54_8125_4927_9988_ee1d2a139d7b degraded?  # flagged fuzzy, vertical text
omni/page_dc728bd5_50a9_41e8_9e5a_d4b01e6664a2 clean
omni/page_e2fbf592_51f5_431a_8ae6_0c62e3349e89 degraded?  # flagged fuzzy, looks clean
omni/page_e721a819_6dbf_453a_a7ad_857c24f9aa3e clean
omni/scihub_j.physe.2007.10.027.pdf_0 clean
omni/yanbaopptmerge_baa6d029.pdf_11 clean
omni/yanbaopptmerge_yanbaoPPT_685 clean
omni/yanbaopptmerge_yanbaoPPT_1735 degraded?  # flagged fuzzy, slide art behind text
omni/yanbaopptmerge_yanbaoPPT_5885 degraded?  # flagged fuzzy, slide art behind text
omni/yanbaor2_yanbaoPPT_569 clean
pdb/academic_paper_010/digital degraded?  # light blue tint, readable
pdb/academic_paper_010/real degraded  # page small and sideways on a desk
pdb/academic_paper_019/digital degraded  # strong geometric warp
pdb/academic_paper_019/real degraded
pdb/api_reference_010/digital degraded?  # colour speckle noise
pdb/api_reference_010/real degraded  # photo of a screen
pdb/architecture_diagram_010/digital degraded  # washed out, low contrast
pdb/architecture_diagram_010/real degraded
pdb/audit_report_012/digital degraded?  # slight fading
pdb/audit_report_012/real clean  # compressed screenshot, no visible loss
pdb/book_004/digital degraded  # scan-line banding across the page
pdb/book_004/real degraded
pdb/bp_verdapack_en_v1/digital degraded  # heavily faded
pdb/bp_verdapack_en_v1/real degraded
pdb/brochure_menu_004/digital degraded  # scan-line banding
pdb/brochure_menu_004/real degraded
pdb/conference_poster_016/digital degraded?  # no visible degradation
pdb/conference_poster_016/real degraded
pdb/datasheet_017/digital degraded?  # uneven lighting at the edges
pdb/datasheet_017/real clean  # compressed screenshot, no visible loss
pdb/employee_handbook_010/digital degraded  # rotated and warped
pdb/employee_handbook_010/real degraded
pdb/exam_paper_030/digital degraded?  # aged paper tint
pdb/exam_paper_030/real degraded
pdb/financial_report_005/digital degraded?  # no visible degradation
pdb/financial_report_005/real degraded
pdb/fund_prospectus_008/digital degraded  # warped
pdb/fund_prospectus_008/real degraded
pdb/gov_document_001/digital degraded  # curved, skewed lines
pdb/gov_document_001/real degraded
pdb/lab_report_017/digital degraded?  # aged paper tint
pdb/legislation_022/digital degraded  # blurred, low contrast
pdb/legislation_022/real clean  # compressed screenshot, no visible loss
pdb/magazine_004/digital degraded  # scan-line banding
pdb/magazine_004/real degraded
pdb/meeting_memo_003/digital degraded?  # grey, faded
pdb/meeting_memo_003/real degraded  # handheld, oblique
pdb/newspaper_007/digital degraded?  # grey tone
pdb/newspaper_007/real degraded
pdb/patent_026/digital degraded?  # no visible degradation
pdb/patent_026/real degraded
pdb/product_manual_004/digital degraded  # scan-line banding
pdb/product_manual_004/real clean  # compressed screenshot, no visible loss
pdb/quality_certification_002/digital degraded?  # speckle noise and tint
pdb/quality_certification_002/real degraded  # sideways, small in frame
pdb/quotation_023/digital degraded?  # no visible degradation
pdb/quotation_023/real clean  # compressed screenshot, no visible loss
pdb/release_notes_011/digital degraded?  # no visible degradation
pdb/release_notes_011/real degraded  # photo of a screen
pdb/research_proposal_027/digital degraded?  # no visible degradation
pdb/research_proposal_027/real degraded
pdb/school_notice_006/clean drop  # a named student's timetable with a student number
pdb/school_notice_006/digital drop
pdb/school_notice_006/real drop
pdb/slides_015/digital degraded?  # no visible degradation
pdb/slides_015/real degraded  # photo of a screen
pdb/syllabus_023/digital degraded?  # no visible degradation
pdb/technical_report_005/digital degraded  # scan-line banding
pdb/technical_report_005/real degraded
pdb/textbook_013/digital degraded  # faded, speckled
pdb/textbook_013/real degraded?  # tagged a phone capture but shows no camera signature
pdb/thesis_001/digital degraded  # faded, speckled
pdb/thesis_001/real degraded
rvl/30 clean
rvl/38 degraded?  # fax, small print
rvl/45 clean
rvl/47 clean
rvl/75 drop  # a consumer's letter
rvl/76 hw
rvl/77 drop  # nearly blank page
rvl/78 hw
rvl/79 drop  # a consumer's letter with name, address and birth date
rvl/80 drop  # an addressed envelope
rvl/81 hw
rvl/82 hw
rvl/83 drop  # a consumer's letter about their health
rvl/84 drop  # a consumer's letter with name, address and phone
rvl/85 hw  # handwritten lab note on a printed form, speckled
rvl/86 hw
rvl/87 drop  # a consumer's letter with name, address and birth date
rvl/88 drop  # a consumer's letter with name and address
rvl/89 drop  # a consumer's letter about their health
rvl/90 drop  # a pupil's letter with name and school
rvl/91 drop  # a consumer's letter with name and address
rvl/92 drop  # a reply card with name and address
rvl/93 drop  # a consumer's letter with name and address
rvl/94 drop  # a consumer's note with name and address
rvl/95 drop  # a consumer's letter with name
rvl/96 drop  # a consumer's letter naming family
rvl/97 hw  # short handwritten lab list
rvl/98 drop  # a consumer's letter with name, address and phone
rvl/99 hw  # handwritten lab notes on graph paper
rvl/104 degraded?  # halftone advertisement
rvl/105 degraded?  # halftone advertisement
rvl/109 degraded  # dark halftone photograph
rvl/116 clean
rvl/128 clean
rvl/140 clean
rvl/141 clean
rvl/146 degraded?  # low-resolution dense typescript
rvl/157 degraded  # low-resolution, tiny print
rvl/158 degraded  # low-resolution, tiny print
rvl/164 degraded?  # low-resolution, small print
rvl/165 degraded?  # low-resolution, small print
rvl/181 clean
rvl/182 clean
rvl/191 degraded  # dark, noisy handwritten form
rvl/198 clean
rvl/203 drop  # a file folder with almost no text
rvl/212 drop  # a black file folder
rvl/220 drop  # a nearly blank folder
rvl/223 drop  # a dark file folder
rvl/226 degraded?  # low-resolution newsprint
rvl/231 degraded?  # low-resolution, small print
rvl/232 degraded  # low-resolution newsprint, skewed columns
rvl/243 clean
rvl/250 degraded?  # sideways budget table with a strike-through line
rvl/251 clean
rvl/257 degraded?  # sideways, speckled edges
rvl/263 clean
rvl/277 degraded?  # stamps and handwriting over an invoice
rvl/280 degraded  # dark photocopy with black borders
rvl/287 clean
rvl/299 clean
rvl/301 clean  # sideways slide
rvl/304 clean  # sideways cover
rvl/306 clean
rvl/320 drop  # a black cover with almost no text
rvl/327 clean  # a blank questionnaire
rvl/328 drop  # a named taste-panel respondent
rvl/329 clean  # interview transcript, no names
rvl/346 clean
sroie/17 clean
sroie/18 degraded  # small receipt, faint print
sroie/39 clean
sroie/46 clean
sroie/54 drop  # prints a customer's full name
sroie/75 clean
sroie/79 drop  # prints a cashier's name
sroie/97 drop  # prints an operator's full name
sroie/104 degraded  # faded thermal print, parts missing
sroie/116 clean
sroie/159 clean
sroie/167 clean
sroie/205 degraded?  # grey thermal paper
sroie/215 degraded?  # grey thermal paper
sroie/222 degraded?  # grey thermal paper
sroie/224 degraded?  # grey thermal paper
sroie/225 degraded?  # grey thermal paper
sroie/268 degraded  # crumpled, cropped receipt
sroie/295 degraded  # a small receipt on a full flatbed page: tiny print at page scale
sroie/321 degraded  # a small receipt on a full flatbed page
sroie/324 degraded  # a small receipt on a full flatbed page
sroie/331 drop  # prints a cashier's full name
sroie/334 degraded  # a small receipt on a full flatbed page
sroie/340 degraded  # a small receipt on a full flatbed page
"""

if __name__ == "__main__":
    main()
