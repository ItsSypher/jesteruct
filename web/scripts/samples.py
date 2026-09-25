"""Build the Studio's demo samples in web/public/samples/ from evalset/files and a few files of our own.

Run from the repository root: `uv run python web/scripts/samples.py`. The output is committed; rerun it only to
change the set. Each sample lists the lane it is labelled with in the evaluation (or the lane intake rules imply
for our own files) and what it demonstrates.
"""

import json
import shutil
import zipfile
from email.message import EmailMessage
from pathlib import Path

import pikepdf

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / "evalset" / "files"
OUT = ROOT / "web" / "public" / "samples"

OLMOCR = "olmOCR-Bench (allenai/olmOCR-bench), ODC-By 1.0"
PUREDOC = "PureDocBench (zhihengli-casia/puredocbench), CC BY 4.0"
OWN = "Own construction"

# file, source, label, title, what it shows
COPIED = [
    (
        "pdf_olmx_12.pdf",
        "born-digital-report.pdf",
        OLMOCR,
        "L1",
        "Born-digital report",
        "A text layer made with the document: the cheap rule trusts it, so OCR and vision are skipped.",
    ),
    (
        "pdf_olmocr_arxivmath_04.pdf",
        "math-paper.pdf",
        OLMOCR,
        "L2",
        "Paper with equations",
        "Born-digital, but full of mathematical notation, which needs a math-aware lane.",
    ),
    (
        "pdf_code_01.pdf",
        "source-listing.pdf",
        f"{OWN}; CPython source under the PSF License",
        "L2",
        "Source listing",
        "A monospaced code page: complex layout although the text layer is clean.",
    ),
    (
        "img_pdb_bankrisk_clean.jpg",
        "bank-report-clean.jpg",
        PUREDOC,
        "L3",
        "Clean scan",
        "An image with no text layer, sharp and flat: OCR will read it as it is.",
    ),
    (
        "img_pdb_bankrisk_digital.jpg",
        "bank-report-banded.jpg",
        PUREDOC,
        "L4",
        "Mildly degraded copy",
        "The same page with light digital degradation. Borderline between L3 and L4, so review may catch it.",
    ),
    (
        "img_pdb_bankrisk_real.jpg",
        "bank-report-photo.jpg",
        PUREDOC,
        "L4",
        "Photographed printout",
        "The same page again, photographed on a desk: a degraded capture.",
    ),
    (
        "img_synth_camera_01.jpg",
        "notice-board-photo.jpg",
        OWN,
        "L4",
        "Camera photo",
        "A synthetic phone photo: perspective, vignette and blur.",
    ),
    ("img_synth_fax_01.jpg", "memo-fax.jpg", OWN, "L4", "Fax", "A synthetic fax: dithered, skewed and speckled."),
    (
        "img_gnhk_01.jpg",
        "handwritten-notes.jpg",
        "GNHK (GoodNotes), CC BY 4.0",
        "L5",
        "Handwriting",
        "A photo of handwritten notes: the vision check sees handwriting, Jev routes it to L5.",
    ),
    (
        "img_arabic_01.jpg",
        "arabic-lesson.jpg",
        "HumynLabs Arabic Documents, CC BY 4.0",
        "L3",
        "Arabic page",
        "A clean page in Arabic script: the script and right-to-left modifiers ride along with the lane.",
    ),
]


def mixed_report(path: Path) -> None:
    """Three pages that need three different lanes, so the manifest has three segments."""
    out = pikepdf.new()
    for name in ("pdf_olmx_02.pdf", "pdf_olmocr_tables_03.pdf", "ocr_synth_fax_02.pdf"):
        with pikepdf.open(FILES / name) as src:
            out.pages.extend(src.pages)
    out.save(path, deterministic_id=True)


def locked_pdf(path: Path) -> None:
    with pikepdf.open(FILES / "pdf_code_02.pdf") as src:
        src.save(path, encryption=pikepdf.Encryption(owner="jesteruct", user="demo"))


def docx(path: Path) -> None:
    """The smallest valid word-processing package: intake knows it by its parts, never by the extension."""
    body = "".join(
        f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>"
        for line in (
            "Routing review, 24 September",
            "Attendees: platform, data, and the lanes team.",
            "Decision: keep one page per Jev request; batching costs about two points of accuracy.",
            "Next: move the labelled pages out of the repository.",
        )
    )
    parts = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/'
        'package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
        'relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/'
        'document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"'
        "/></Types>",
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/'
        'package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/document.xml": '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats'
        f'.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>',
    }
    _zip(path, {name: text.encode() for name, text in parts.items()})


def bundle(path: Path) -> None:
    _zip(
        path,
        {
            "bundle/receipts/shift-schedule-photo.jpg": (FILES / "img_synth_camera_02.jpg").read_bytes(),
            "bundle/readme-screenshot.jpg": (FILES / "img_synth_screenshot_01.jpg").read_bytes(),
            "bundle/notes.txt": b"Scanned on the third floor copier. Receipts are in the receipts folder.\n",
        },
    )


def email(path: Path) -> None:
    msg = EmailMessage()
    msg["From"] = "lanes@example.com"
    msg["To"] = "router@example.com"
    msg["Subject"] = "Newsletter for routing"
    msg["Date"] = "Thu, 24 Sep 2026 09:00:00 +0000"
    msg.set_content("Hello,\n\nThe two-column newsletter is attached.\n\nThanks\n")
    pdf = (FILES / "pdf_olmocr_multicol_03.pdf").read_bytes()
    msg.add_attachment(pdf, maintype="application", subtype="pdf", filename="newsletter.pdf")
    path.write_bytes(bytes(msg))


def _zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(zipfile.ZipInfo(name, date_time=(2026, 9, 24, 9, 0, 0)), data, zipfile.ZIP_DEFLATED)


BUILT = [
    (
        mixed_report,
        "mixed-report.pdf",
        f"{OLMOCR}; {OWN}",
        "L1 L2 L4",
        "Three-page PDF",
        "A born-digital page, a table page and a faxed page with an old OCR layer: three segments in one manifest.",
    ),
    (
        docx,
        "meeting-notes.docx",
        OWN,
        "L0",
        "Word document",
        "A native office file: no rendering needed, so it goes straight to L0.",
    ),
    (
        bundle,
        "scans-bundle.zip",
        OWN,
        "L4 L3 L0",
        "Zip archive",
        "A container: intake expands it, and each file inside is routed as its own document.",
    ),
    (
        email,
        "newsletter-email.eml",
        f"{OWN}; attachment from {OLMOCR}",
        "L0 L2",
        "Email with attachment",
        "The body text is native (L0); the attached two-column PDF is routed on its own.",
    ),
    (
        locked_pdf,
        "locked.pdf",
        OWN,
        "LQ",
        "Encrypted PDF",
        "Password protected, so intake quarantines it with a reason instead of guessing.",
    ),
]


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    samples = []
    for source, name, licence, lanes, title, shows in COPIED:
        shutil.copyfile(FILES / source, OUT / name)
        samples.append({"file": name, "title": title, "lanes": lanes.split(), "shows": shows, "source": licence})
    for build, name, licence, lanes, title, shows in BUILT:
        build(OUT / name)
        samples.append({"file": name, "title": title, "lanes": lanes.split(), "shows": shows, "source": licence})
    (OUT / "samples.json").write_text(json.dumps(samples, indent=2, ensure_ascii=False) + "\n")
    total = sum(f.stat().st_size for f in OUT.iterdir())
    print(f"{len(samples)} samples, {total / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
