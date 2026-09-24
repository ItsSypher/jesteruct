import hashlib
import io
import zipfile
from email.message import EmailMessage
from pathlib import Path

import pikepdf
from PIL import Image

from jesteruct.config import Settings
from jesteruct.intake import expand


def _settings() -> Settings:
    return Settings(openrouter_api_key="")


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_pdf_page_count(tmp_path):
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    pdf.add_blank_page(page_size=(200, 200))
    buf = io.BytesIO()
    pdf.save(buf)
    path = _write(tmp_path, "doc.pdf", buf.getvalue())

    docs = expand(path, _settings(), tmp_path / "work")

    assert len(docs) == 1
    assert docs[0].kind == "pdf"
    assert docs[0].page_count == 2
    assert docs[0].quarantine is None


def test_encrypted_pdf_is_quarantined(tmp_path):
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    buf = io.BytesIO()
    pdf.save(buf, encryption=pikepdf.Encryption(owner="owner-pw", user="user-pw"))
    path = _write(tmp_path, "secret.pdf", buf.getvalue())

    docs = expand(path, _settings(), tmp_path / "work")

    assert len(docs) == 1
    assert docs[0].kind == "pdf"
    assert docs[0].quarantine == "encrypted"


def test_multipage_tiff_frame_count(tmp_path):
    frames = [Image.new("RGB", (10, 10), (i * 20, 0, 0)) for i in range(3)]
    buf = io.BytesIO()
    frames[0].save(buf, format="TIFF", save_all=True, append_images=frames[1:])
    path = _write(tmp_path, "scan.tiff", buf.getvalue())

    docs = expand(path, _settings(), tmp_path / "work")

    assert len(docs) == 1
    assert docs[0].kind == "image"
    assert docs[0].page_count == 3
    assert docs[0].quarantine is None


def test_zip_expands_into_children_with_parent_sha(tmp_path):
    zip_bytes_buf = io.BytesIO()
    with zipfile.ZipFile(zip_bytes_buf, "w") as zf:
        zf.writestr("a.txt", "first file")
        zf.writestr("b.txt", "second file")
    zip_bytes = zip_bytes_buf.getvalue()
    path = _write(tmp_path, "bundle.zip", zip_bytes)
    parent_sha = hashlib.sha256(zip_bytes).hexdigest()

    docs = expand(path, _settings(), tmp_path / "work")

    assert len(docs) == 2
    assert {d.kind for d in docs} == {"text"}
    assert all(d.parent_sha == parent_sha for d in docs)
    assert {d.name for d in docs} == {"a.txt", "b.txt"}


def test_zip_bomb_is_quarantined(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("bomb.bin", b"0" * 15_000_000)
    path = _write(tmp_path, "bomb.zip", buf.getvalue())

    docs = expand(path, _settings(), tmp_path / "work")

    assert len(docs) == 1
    assert docs[0].kind == "archive"
    assert docs[0].quarantine == "archive_bomb"


def test_email_body_and_attachment(tmp_path):
    msg = EmailMessage()
    msg["From"] = "sender@example.com"
    msg["To"] = "receiver@example.com"
    msg["Subject"] = "hello"
    msg.set_content("this is the body")
    msg.add_attachment(b"attachment payload", maintype="text", subtype="plain", filename="note.txt")
    raw = msg.as_bytes()
    path = _write(tmp_path, "message.eml", raw)
    parent_sha = hashlib.sha256(raw).hexdigest()

    docs = expand(path, _settings(), tmp_path / "work")

    assert len(docs) == 2
    assert all(d.parent_sha == parent_sha for d in docs)
    names = {d.name for d in docs}
    assert any(n.endswith("#body.txt") for n in names)
    assert "note.txt" in names
    assert all(d.kind == "text" for d in docs)


def test_unsupported_bytes_are_quarantined(tmp_path):
    path = _write(tmp_path, "blob.bin", bytes(range(256)) * 4)

    docs = expand(path, _settings(), tmp_path / "work")

    assert len(docs) == 1
    assert docs[0].kind == "unknown"
    assert docs[0].quarantine == "unsupported_type"
