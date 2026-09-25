"""From a catalogue entry to the file the router is given.

Every page in pages.jsonl names where its raw file comes from (`fetch`) and where it is cached (`raw`, under
.cache/raw/). `fetch_raw` downloads what is missing; `stage` turns a raw file into the page's case file under
.cache/stage/: a single-page PDF, or a 1024 px JPEG, optionally cropped or put through a synthetic capture.
"""

import concurrent.futures
import functools
import hashlib
import io
import os
import re
import struct
import subprocess
import sys
import tarfile
import threading
import time
import unicodedata
import warnings
import zlib
from base64 import b64decode
from itertools import accumulate
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pikepdf
import pypdfium2 as pdfium
from PIL import Image, ImageOps

HERE = Path(__file__).parent
CACHE = HERE / ".cache"
RAW = CACHE / "raw"
STAGE = CACHE / "stage"
REPO = HERE.parent.parent

sys.path.insert(0, str(REPO / "bench/vision_bakeoff/data/scripts"))
from synth_degrade import make_camera_photo, make_fax, rotate_page  # noqa: E402  (the bench's synthetic captures)

# SEC EDGAR asks every client for a descriptive User-Agent with a contact; it checks the shape, not the address.
_HEADERS = {
    "www.sec.gov": {
        "User-Agent": "jesteruct evalset builder admin@jesteruct.invalid",
        "Accept-Encoding": "gzip, deflate",
        "Accept": "*/*",
    }
}


# ---------------------------------------------------------------- downloads


@functools.cache
def _hf_token() -> str:
    """HF_TOKEN from the environment or the repository's .env; anonymous requests get far lower rate limits."""
    if token := os.environ.get("HF_TOKEN"):
        return token
    env = REPO / ".env"
    for line in env.read_text().splitlines() if env.exists() else []:
        name, _, value = line.partition("=")
        if name.strip() == "HF_TOKEN":
            return value.strip().strip("\"'")
    return ""


def _headers(url: str) -> dict[str, str]:
    host = urlparse(url).netloc
    if host.endswith("huggingface.co") and _hf_token():  # httpx drops it on a redirect to another host
        return {"Authorization": f"Bearer {_hf_token()}"}
    return _HEADERS.get(host, {})


def _get(url: str, client: httpx.Client | None = None) -> bytes:
    headers = _headers(url)
    for attempt in range(6):
        try:
            r = (client or httpx).get(url, headers=headers, follow_redirects=True, timeout=300)
        except httpx.TransportError:
            r = None
        if r is not None and r.status_code == 200:
            return r.content
        if r is not None and r.status_code not in (429, 500, 502, 503, 504):
            r.raise_for_status()
        time.sleep(2 + 4 * attempt)
    raise RuntimeError(f"download failed: {url}")


def hf_rows(dataset: str, split: str, offset: int, length: int, config: str = "default") -> list[dict]:
    """Rows from the HF datasets-server rows API (image cells come back as short-lived URLs)."""
    params = {"dataset": dataset, "config": config, "split": split, "offset": offset, "length": length}
    for attempt in range(10):  # the API answers the odd 5xx on large rows, and 429 when asked too often
        try:
            url = "https://datasets-server.huggingface.co/rows"
            r = httpx.get(url, params=params, headers=_headers(url), timeout=300)
        except httpx.TransportError:
            time.sleep(5)
            continue
        if r.status_code < 500 and r.status_code != 429:
            break
        wait = r.headers.get("retry-after", "")
        time.sleep(float(wait) if wait.isdigit() else 5 + 10 * attempt)
    r.raise_for_status()
    return r.json()["rows"]


def _hf_cell(spec: dict) -> bytes:
    """One cell of one dataset row: an image (downloaded from its URL) or a base64 string (a PDF)."""
    (row,) = hf_rows(spec["hf"], spec["split"], spec["row"], 1, spec.get("config", "default"))
    cell = row["row"][spec["column"]]
    return _get(cell["src"]) if isinstance(cell, dict) else b64decode(cell)


# PureDocBench ships one ~35 GiB tar split into ten parts; its pages are read by byte range of the concatenation.
PDB_BASE = (
    "https://huggingface.co/datasets/zhihengli-casia/puredocbench/resolve/d56779469315a6489ab656dbd17595f094480f5c/"
)
PDB_PARTS = [(f"pdb_full.tar.part-{i:03d}", 4_089_446_400 if i < 9 else 802_099_200) for i in range(10)]


class SplitTar:
    def __init__(self) -> None:
        starts = accumulate([0] + [size for _, size in PDB_PARTS])
        self.parts = [(lo, lo + size, name) for lo, (name, size) in zip(starts, PDB_PARTS, strict=False)]
        self._local = threading.local()
        self._cdn: dict[str, str] = {}

    def _client(self) -> httpx.Client:
        if not hasattr(self._local, "client"):
            self._local.client = httpx.Client(timeout=120)
        return self._local.client

    def _get(self, name: str, a: int, b: int) -> bytes:
        for _ in range(4):
            if name not in self._cdn:  # resolve the signed CDN URL once; it saves a redirect on every read
                head = self._client().get(PDB_BASE + name, headers={"Range": "bytes=0-0", **_headers(PDB_BASE)})
                self._cdn[name] = head.headers["location"]
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


class _Stream(io.RawIOBase):
    """A forward-only file over an HTTP response, for tarfile's streaming mode."""

    def __init__(self, response: httpx.Response) -> None:
        self._chunks, self._buf = response.iter_bytes(1 << 20), b""

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:
        while not self._buf:
            try:
                self._buf = next(self._chunks)
            except StopIteration:
                return 0
        n = min(len(b), len(self._buf))
        b[:n], self._buf = self._buf[:n], self._buf[n:]
        return n


def _tar_members(url: str, names: set[str]) -> dict[str, bytes]:
    """Members of a remote (compressed) tar, read in one streaming pass that stops once all are found."""
    out: dict[str, bytes] = {}
    with httpx.stream("GET", url, headers=_headers(url), follow_redirects=True, timeout=600) as r:
        r.raise_for_status()
        with tarfile.open(fileobj=io.BufferedReader(_Stream(r), 1 << 20), mode="r|*") as tar:
            for member in tar:
                if member.name in names:
                    out[member.name] = tar.extractfile(member).read()
                    if len(out) == len(names):
                        break
    if missing := names - out.keys():
        raise RuntimeError(f"{url}: no {sorted(missing)[:3]}")
    return out


def _range(url: str, a: int, b: int) -> bytes:
    for attempt in range(6):
        r = httpx.get(url, headers={"Range": f"bytes={a}-{b - 1}", **_headers(url)}, follow_redirects=True, timeout=300)
        if r.status_code == 206:
            return r.content
        time.sleep(2 + 4 * attempt)
    raise RuntimeError(f"range read failed: {url} {a}-{b}")


def zip_directory(url: str) -> dict[str, tuple[int, int, int, int]]:
    """A remote zip's central directory, by range reads: name -> (header offset, compressed size, method, size)."""
    size = int(httpx.head(url, headers=_headers(url), follow_redirects=True, timeout=60).headers["content-length"])
    tail = _range(url, max(0, size - 65_536), size)
    end = tail.rfind(b"PK\x05\x06")
    _, length, start = struct.unpack("<HII", tail[end + 10 : end + 20])
    if start == 0xFFFFFFFF:  # zip64: the end-of-directory locator points at the zip64 record
        locator = tail.rfind(b"PK\x06\x07")
        (record,) = struct.unpack("<Q", tail[locator + 8 : locator + 16])
        head = _range(url, record, record + 56)
        _, length, start = struct.unpack("<QQQ", head[32:56])
    directory, out, i = _range(url, start, start + length), {}, 0
    while i < len(directory):
        method, _, _, _, csize, usize, nlen, xlen, clen = struct.unpack("<HHHIIIHHH", directory[i + 10 : i + 34])
        (offset,) = struct.unpack("<I", directory[i + 42 : i + 46])
        name = directory[i + 46 : i + 46 + nlen].decode("utf-8", "replace")
        extra = directory[i + 46 + nlen : i + 46 + nlen + xlen]
        j = 0
        while j + 4 <= len(extra):  # zip64 sizes and offset replace the 0xFFFFFFFF placeholders
            tag, n = struct.unpack("<HH", extra[j : j + 4])
            if tag == 1:
                vals = iter(struct.unpack(f"<{n // 8}Q", extra[j + 4 : j + 4 + n]))
                usize = next(vals) if usize == 0xFFFFFFFF else usize
                csize = next(vals) if csize == 0xFFFFFFFF else csize
                offset = next(vals) if offset == 0xFFFFFFFF else offset
            j += 4 + n
        out[name] = (offset, csize, method, usize)
        i += 46 + nlen + xlen + clen
    return out


def _zip_members(url: str, names: set[str]) -> dict[str, bytes]:
    directory, out = zip_directory(url), {}
    for name in names:
        offset, csize, method, _ = directory[name]
        head = _range(url, offset, offset + 30)
        nlen, xlen = struct.unpack("<HH", head[26:30])
        data = _range(url, offset + 30 + nlen + xlen, offset + 30 + nlen + xlen + csize)
        out[name] = data if method == 0 else zlib.decompressobj(-15).decompress(data)
    return out


def fetch_raw(entries: list[dict]) -> None:
    """Download every raw file that is not cached yet."""
    todo = [e for e in entries if "fetch" in e and not (RAW / e["raw"]).exists()]
    archives: dict[str, list[dict]] = {}
    for e in todo:
        if "member" in e["fetch"]:
            archives.setdefault(e["fetch"]["url"], []).append(e)
    pdb = SplitTar()

    def one(e: dict) -> None:
        spec = e["fetch"]
        if "pdb" in spec:
            data = pdb.read(*spec["pdb"])
        elif "hf" in spec:
            data = _hf_cell(spec)
        else:
            data = _get(spec["url"])
        _write(RAW / e["raw"], data)

    def archive(url: str) -> None:
        wanted = {e["fetch"]["member"]: e for e in archives[url]}
        read = _zip_members if url.endswith(".zip") else _tar_members
        for name, data in read(url, set(wanted)).items():
            _write(RAW / wanted[name]["raw"], data)

    rows = [e for e in todo if "hf" in e["fetch"]]  # the rows API allows only a few requests at a time
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        list(pool.map(one, rows))
    with concurrent.futures.ThreadPoolExecutor(12) as pool:
        list(pool.map(one, [e for e in todo if "member" not in e["fetch"] and "hf" not in e["fetch"]]))
        list(pool.map(archive, archives))


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


# ---------------------------------------------------------------- PDF facts


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


TEXT_LAYER_RULE = "structural-2"  # part of every cached verdict, so a rule change never reuses old ones


def text_layer(path: Path) -> str:
    """ "trusted" for a born-digital page; otherwise why the page needs OCR: "none", "ocr" (an OCR layer over a
    full-page image) or "garbled".

    Structural on purpose: short text (a cover, a slide, a numeric table) or a few odd glyphs (TeX delimiters and
    bullets extract as private-use characters) do not make a born-digital page a scan. The first rule required 200
    characters, 30 words and under 1% odd characters, and sent such pages to the capture rubric, where labellers could
    only call them clean scans.
    """
    if path.suffix != ".pdf":
        return "none"
    facts = pdf_facts(path)
    chars = len("".join(facts["text"].split()))
    if facts["image_coverage"] >= 0.9:
        return "ocr" if chars > 50 else "none"
    if chars >= 200 and ("(cid:" in facts["text"] or _odd_share(facts["text"]) >= 0.2):
        return "garbled"
    return "trusted" if chars >= 20 else "none"


# ---------------------------------------------------------------- staging


def page_image(path: Path, index: int = 0) -> Image.Image:
    """The page as a viewer sees it: PDFs rendered to 1024 px on the long side, photos turned upright."""
    if path.suffix == ".pdf":
        pdf_page = pdfium.PdfDocument(str(path))[index]
        return pdf_page.render(scale=1024 / max(pdf_page.get_size())).to_pil()
    with Image.open(path) as im:
        im.seek(index)
        return ImageOps.exif_transpose(im).copy()


def jpeg(im: Image.Image, dest: Path) -> None:
    """1024 px on the long side, JPEG quality 90; grayscale sources stay grayscale."""
    im = im.convert("L" if im.mode in ("1", "L", "LA", "I", "I;16") else "RGB")
    scale = 1024 / max(im.size)
    im.resize((round(im.width * scale), round(im.height * scale)), Image.Resampling.LANCZOS).save(
        dest,
        "JPEG",
        quality=90,
        optimize=True,
        comment=b"",  # no comment copied from the source (it can name it)
    )


def _single_page(src: Path, index: int, dest: Path) -> None:
    with pikepdf.open(src) as pdf:
        if len(pdf.pages) == 1 and index == 0:
            dest.write_bytes(src.read_bytes())
            return
        out = pikepdf.new()
        with warnings.catch_warnings():  # form pages lose their AcroForm; the router renders page content only
            warnings.simplefilter("ignore", pikepdf.PageCopyWarning)
            out.pages.append(pdf.pages[index])
        out.remove_unreferenced_resources()
        out.save(dest, deterministic_id=True, compress_streams=True)


_SYNTH = {"fax": make_fax, "camera": make_camera_photo}


def stage(entry: dict) -> Path:
    """The page's case file: the PDF page itself, or its 1024 px JPEG (cropped or simulated when the entry says)."""
    STAGE.mkdir(parents=True, exist_ok=True)
    src, index = RAW / entry["raw"], entry.get("page", 0)
    if entry["render"] == "pdf":
        dest = STAGE / f"{entry['id']}.pdf"
        if not dest.exists():
            _single_page(src, index, dest)
        return dest
    dest = STAGE / f"{entry['id']}.jpg"
    if not dest.exists():
        im = page_image(src, index)
        if crop := entry.get("crop"):  # fractions of the page: left, top, right, bottom
            w, h = im.size
            im = im.crop((round(crop[0] * w), round(crop[1] * h), round(crop[2] * w), round(crop[3] * h)))
        if derive := entry.get("derive"):
            kind, _, seed = derive.partition(":")
            im = im.convert("RGB")
            im = rotate_page(im) if kind == "rotated" else _SYNTH[kind](im, seed=int(seed))
        jpeg(im, dest)
    return dest


def ocr_pdf(image: Path, dest: Path) -> None:
    """A Tesseract OCR-layer PDF of an image page, without timestamps so a rebuild gives the same bytes."""
    base = CACHE / "ocr" / dest.stem
    base.parent.mkdir(exist_ok=True)
    subprocess.run(
        ["tesseract", str(image), str(base), "-l", "eng", "--dpi", "150", "pdf"], check=True, capture_output=True
    )
    with pikepdf.open(base.with_suffix(".pdf")) as pdf:
        for stamp in ("/CreationDate", "/ModDate"):
            if stamp in pdf.docinfo:
                del pdf.docinfo[stamp]
        pdf.save(dest, deterministic_id=True)


def garble(text: str, kind: str) -> str:
    """The broken text layers of bench/jev_lanes/probe.py: cid codes, a constant glyph offset, mojibake."""
    if kind == "cid":
        return "".join(f"(cid:{ord(c) % 97 + 3})" if c.isalpha() else c for c in text)
    if kind == "shift":  # glyph ids without a ToUnicode map often come out as a constant offset
        return "".join(chr(ord(c) + 29) if c.isalpha() else c for c in text)
    return text.encode("utf-8").decode("latin-1", errors="replace").replace("e", "Ã©").replace("a", "")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
