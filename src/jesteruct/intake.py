"""Turn one input file into the routable documents it contains.

Format is decided from magic bytes, never from the file extension, so a renamed or
mislabelled file still lands in the right handler. Containers (zip, email) are not
routed themselves; only the documents they expand into are, except when the
container itself has to be quarantined."""

import email
import email.message
import email.policy
import hashlib
import io
import json
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile, ZipInfo

import pikepdf
import pillow_heif
import pypdfium2 as pdfium
from PIL import Image

from .config import Settings
from .models import Doc, DocKind

pillow_heif.register_heif_opener()

_HEIF_BRANDS = {b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"hevm", b"hevs", b"mif1", b"msf1"}
_EMAIL_HINT_HEADERS = {b"from", b"to", b"subject", b"date", b"message-id", b"mime-version", b"received"}

# Archive-bomb budget: a member has to be both sizeable and suspiciously compressible
# before it is flagged, so an ordinary well-compressed file never trips the check.
_BOMB_TOTAL_BYTES = 1_000_000_000
_BOMB_MIN_MEMBER_BYTES = 10_000_000
_BOMB_RATIO = 100


@dataclass(frozen=True)
class _Unit:
    """One file being classified: the input, an archive member, or an email part."""

    data: bytes
    name: str
    sha: str
    size: int
    settings: Settings
    workdir: Path
    parent_sha: str | None
    depth: int
    top_path: Path | None = None  # set only for the original input file

    def leaf(self, kind: DocKind, mime: str, page_count: int = 0, quarantine: str | None = None) -> Doc:
        path = self.top_path if self.top_path is not None else _materialize(self.workdir, self.sha, self.data)
        return Doc(
            sha256=self.sha,
            name=self.name,
            path=str(path),
            kind=kind,
            mime=mime,
            size=self.size,
            page_count=page_count,
            parent_sha=self.parent_sha,
            quarantine=quarantine,
        )

    def child(self, data: bytes, name: str) -> list[Doc]:
        return _expand(data, name, self.settings, self.workdir, parent_sha=self.sha, depth=self.depth + 1)


def expand(path: Path, settings: Settings, workdir: Path, name: str | None = None) -> list[Doc]:
    """Expand one input file into its routable documents, in order.

    Children (archive members, email parts) are written into workdir; the top-level
    file is referenced in place since it already holds exactly its own bytes."""
    workdir.mkdir(parents=True, exist_ok=True)
    data = path.read_bytes()
    return _expand(data, name or path.name, settings, workdir, parent_sha=None, depth=0, top_path=path)


def _expand(
    data: bytes,
    name: str,
    settings: Settings,
    workdir: Path,
    *,
    parent_sha: str | None,
    depth: int,
    top_path: Path | None = None,
) -> list[Doc]:
    sha = hashlib.sha256(data).hexdigest()
    unit = _Unit(data, name, sha, len(data), settings, workdir, parent_sha, depth, top_path)
    if unit.size == 0:
        return [unit.leaf("unknown", "application/octet-stream", quarantine="empty")]
    if unit.size > settings.max_file_mb * 1024 * 1024:
        return [unit.leaf("unknown", "application/octet-stream", quarantine="too_large")]
    kind, mime = _sniff(data, name)
    return _HANDLERS[kind](unit, mime)


def _materialize(workdir: Path, sha: str, data: bytes) -> Path:
    dest = workdir / sha
    if not dest.exists():
        dest.write_bytes(data)
    return dest


# --- sniffing -----------------------------------------------------------------


def _sniff(data: bytes, name: str) -> tuple[DocKind, str]:
    if data.startswith(b"%PDF-"):
        return "pdf", "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image", "image/jpeg"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image", "image/tiff"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image", "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image", "image/webp"
    if data.startswith(b"BM") and data[6:10] == b"\x00\x00\x00\x00":  # reserved header bytes, unlike text
        return "image", "image/bmp"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS:
        return "image", "image/heic"
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "office", "application/x-ole-storage"
    if data.startswith(b"{\\rtf"):
        return "office", "application/rtf"
    if data[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"):
        return _sniff_zip(data)
    if _looks_like_email(data, name):
        return "email", "message/rfc822"
    if _looks_like_text(data):
        return "text", _text_mime(data, name)
    return "unknown", "application/octet-stream"


def _sniff_zip(data: bytes) -> tuple[DocKind, str]:
    try:
        with ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            if "[Content_Types].xml" in names:
                return "office", _ooxml_mime(names)
            if "mimetype" in names:
                mimetype = zf.read("mimetype").decode("ascii", "replace").strip()
                if mimetype.startswith("application/vnd.oasis.opendocument"):
                    return "office", mimetype
            return "archive", "application/zip"
    except BadZipFile:
        return "archive", "application/zip"


def _ooxml_mime(names: list[str]) -> str:
    if any(n.startswith("word/") for n in names):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if any(n.startswith("xl/") for n in names):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if any(n.startswith("ppt/") for n in names):
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    return "application/octet-stream"


def _looks_like_email(data: bytes, name: str) -> bool:
    if name.lower().endswith(".eml"):
        return True
    seen: set[bytes] = set()
    for raw_line in data[:4096].split(b"\n")[:20]:
        line = raw_line.rstrip(b"\r")
        if not line:
            break
        if line[:1] in b" \t":
            continue  # header continuation
        head, sep, _ = line.partition(b":")
        if not sep or not head.isascii() or b" " in head:
            return False
        seen.add(head.strip().lower())
    return bool(seen & _EMAIL_HINT_HEADERS)


def _looks_like_text(data: bytes) -> bool:
    sample = data[:65536]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _text_mime(data: bytes, name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in (".md", ".markdown"):
        return "text/markdown"
    if suffix == ".csv":
        return "text/csv"
    if suffix in (".htm", ".html"):
        return "text/html"
    if suffix == ".json":
        return "application/json"
    if data.lstrip()[:1] in (b"{", b"["):
        try:
            json.loads(data.decode("utf-8"))
            return "application/json"
        except Exception:
            pass
    if b"<html" in data[:512].lower() or b"<!doctype html" in data[:512].lower():
        return "text/html"
    return "text/plain"


# --- handlers -------------------------------------------------------------------


def _handle_pdf(unit: _Unit, mime: str) -> list[Doc]:
    try:
        with pikepdf.open(io.BytesIO(unit.data)):
            pass
    except pikepdf.PasswordError:
        return [unit.leaf("pdf", mime, quarantine="encrypted")]
    except Exception:
        pass  # pikepdf is stricter than pdfium about structure; let pdfium have the final say

    try:
        pdf = pdfium.PdfDocument(unit.data)
    except Exception as exc:
        reason = "encrypted" if "password" in str(exc).lower() else "corrupt"
        return [unit.leaf("pdf", mime, quarantine=reason)]

    try:
        page_count = len(pdf)
    except Exception:
        return [unit.leaf("pdf", mime, quarantine="corrupt")]
    finally:
        pdf.close()

    if page_count > unit.settings.max_pages:
        return [unit.leaf("pdf", mime, page_count, quarantine="too_many_pages")]
    return [unit.leaf("pdf", mime, page_count)]


def _handle_image(unit: _Unit, mime: str) -> list[Doc]:
    try:
        with Image.open(io.BytesIO(unit.data)) as im:
            page_count = getattr(im, "n_frames", 1)
            pixels = im.width * im.height
    except Exception:
        return [unit.leaf("image", mime, quarantine="corrupt")]

    if pixels > unit.settings.max_image_pixels:
        return [unit.leaf("image", mime, page_count, quarantine="image_too_large")]
    return [unit.leaf("image", mime, page_count)]


def _passthrough(kind: DocKind):
    def handler(unit: _Unit, mime: str) -> list[Doc]:
        return [unit.leaf(kind, mime)]

    return handler


def _handle_unsupported(unit: _Unit, mime: str) -> list[Doc]:
    return [unit.leaf("unknown", mime, quarantine="unsupported_type")]


def _handle_archive(unit: _Unit, mime: str) -> list[Doc]:
    if unit.depth >= unit.settings.max_depth:
        return [unit.leaf("archive", mime, quarantine="too_deep")]
    try:
        zf = ZipFile(io.BytesIO(unit.data))
    except BadZipFile:
        return [unit.leaf("archive", mime, quarantine="corrupt")]

    with zf:
        members = [zi for zi in zf.infolist() if _safe_member(zi)]
        if not members:
            return [unit.leaf("archive", mime, quarantine="empty")]
        if len(members) > unit.settings.max_children:
            return [unit.leaf("archive", mime, quarantine="too_many_children")]
        if _looks_like_bomb(members):
            return [unit.leaf("archive", mime, quarantine="archive_bomb")]
        docs: list[Doc] = []
        for zi in members:
            child_name = PurePosixPath(zi.filename).name or zi.filename
            docs += unit.child(zf.read(zi), child_name)
    return docs


def _safe_member(zi: ZipInfo) -> bool:
    if zi.is_dir():
        return False
    posix = PurePosixPath(zi.filename)
    if posix.is_absolute() or ".." in posix.parts:
        return False
    return not stat.S_ISLNK(zi.external_attr >> 16)


def _looks_like_bomb(members: list[ZipInfo]) -> bool:
    if sum(zi.file_size for zi in members) > _BOMB_TOTAL_BYTES:
        return True
    return any(
        zi.file_size > _BOMB_MIN_MEMBER_BYTES and zi.file_size > _BOMB_RATIO * max(zi.compress_size, 1)
        for zi in members
    )


def _handle_email(unit: _Unit, mime: str) -> list[Doc]:
    if unit.depth >= unit.settings.max_depth:
        return [unit.leaf("email", mime, quarantine="too_deep")]
    try:
        msg = email.message_from_bytes(unit.data, policy=email.policy.default)
        body = _email_body(msg)
        attachments = list(msg.iter_attachments())
    except Exception:
        return [unit.leaf("email", mime, quarantine="corrupt")]

    child_count = (1 if body is not None else 0) + len(attachments)
    if child_count > unit.settings.max_children:
        return [unit.leaf("email", mime, quarantine="too_many_children")]

    docs: list[Doc] = []
    if body is not None:
        docs += unit.child(body.encode(), f"{unit.name}#body.txt")
    for part in attachments:
        payload = part.get_payload(decode=True) or b""
        docs += unit.child(payload, part.get_filename() or "attachment")

    if not docs:
        return [unit.leaf("email", mime, quarantine="empty")]
    return docs


def _email_body(msg: email.message.Message) -> str | None:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return None
    try:
        return part.get_content()
    except Exception:
        payload = part.get_payload(decode=True) or b""
        return payload.decode(part.get_content_charset() or "utf-8", "replace")


_HANDLERS = {
    "pdf": _handle_pdf,
    "image": _handle_image,
    "office": _passthrough("office"),
    "text": _passthrough("text"),
    "archive": _handle_archive,
    "email": _handle_email,
    "unknown": _handle_unsupported,
}
