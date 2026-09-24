#!/usr/bin/env python3
"""
Top-level build script for the vision-bakeoff triage bench.

Reproduces the whole dataset from scratch. Each stage is idempotent-ish and
can be re-run individually; see scripts/ for the implementation of each step.
Run with: uv run --no-project --with <deps> python3 build.py <stage>

Stages (run in this order for a full rebuild):

  1. pdb        -- fetch PureDocBench clean/digital/real images for the 8
                    chosen triplets directly from the remote split tar
                    archive (scripts/fetch_puredocbench.py), without
                    downloading the full ~35GB archive. Also requires the
                    gt/ jsons, which were extracted once from a 160MB head
                    fetch of part-000 (see scripts/pdb_tar_reader.py and the
                    inline notes in fetch_puredocbench.py). This step is slow
                    (many small sequential HTTP range requests, ~30-45 min)
                    because the archive has no per-file random access.

  2. olmocr     -- download the specific olmOCR-Bench PDFs we need (old_scans
                    x6, tables x4, arxiv_math x4, multi_column x3) and render
                    them to PNG with pypdfium2 (scripts/render_pdf_pages.py).

  3. funsd      -- pull 5 FUNSD test-split rows (image + words/ner) via the
                    HF datasets-server rows API.

  4. gnhk       -- pull GNHK rows (image + transcription) via the HF mirror
                    Berzerker/gnhk_ocr_dataset datasets-server rows API.

  5. arabic     -- download 3 pages from HumynLabs/Arabic_Documents_Dataset_PDF
                    and render with pypdfium2.

  6. synthetic  -- generate all "by construction" pages: 2 code pages
                    (scripts/make_code_pages.py over CPython stdlib source),
                    5 fresh clean source pages (scripts/make_source_pages.py),
                    2 fax + 2 camera-photo degradations of those sources
                    (scripts/synth_degrade.py), 2 headless-Chrome screenshots
                    of hand-authored HTML pages, and 1 rotated page.

  7. assemble   -- scripts/build_all.py: resize every raw source to
                    pages/<id>.jpg (RGB, long side 1024px, quality 90) per
                    scripts/manifest.py, and write labels.jsonl.

  8. contact    -- scripts/make_contact_sheets.py: build contact_sheets/*.jpg.

Because stage 1 is network-heavy and was run interactively with several
manual visual-QA checkpoints (see labels.jsonl label_basis fields and
README.md), this file documents the pipeline rather than blindly re-running
stage 1 unattended; steps 2-8 are safe to re-run end to end.
"""
import subprocess
import sys

SCRIPTS = "scripts"


def run(cmd):
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"

    if stage in ("pdb", "all"):
        print("Stage 1 (pdb): see scripts/fetch_puredocbench.py -- long-running, run manually:")
        print("  uv run --no-project --with requests python3 scripts/fetch_puredocbench.py")

    if stage in ("assemble", "all"):
        run(["uv", "run", "--no-project", "--with", "pillow", "python3", f"{SCRIPTS}/build_all.py"])

    if stage in ("contact", "all"):
        run(["uv", "run", "--no-project", "--with", "pillow", "python3", f"{SCRIPTS}/make_contact_sheets.py"])


if __name__ == "__main__":
    main()
