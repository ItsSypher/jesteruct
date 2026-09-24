# Vision bakeoff: document-page triage bench

A small, hand-checked set of page images for evaluating vision LLMs as
document-page triage classifiers (capture type, legibility, handwriting,
content type, script). Built 2026-09-24.

Every page was opened and visually inspected before its labels were
finalized; corrections made from that visual check are noted per-page in
`label_basis` in `labels.jsonl`. No paid APIs were used anywhere in this
pipeline -- all downloads are from public HF/GitHub sources, and all
rendering/degradation/classification steps are local (pypdfium2, Pillow,
numpy, reportlab, headless Chrome, tesseract available but unused since no
OCR judging was needed).

## Layout

```
data/
  pages/<id>.jpg          -- final bench images (RGB JPEG, long side 1024px, q90)
  labels.jsonl            -- one JSON object per page (see schema below)
  contact_sheets/sheet_XX.jpg -- 3x2 review grids, in labels.jsonl order
  raw/                    -- untouched source downloads/renders (gitignored)
  scripts/                -- all pipeline code
  build.py                -- top-level pipeline entry point / documentation
```

## labels.jsonl schema

- `id` -- page id
- `source` -- dataset name + original identifier/URL
- `license` -- as declared by the source (or "own construction" for synthetic pages)
- `capture_ok` -- list of acceptable values from
  `{digital_render, flatbed_scan, fax, camera_photo, screenshot}` (a list
  because e.g. a digitally-degraded page can legitimately look like either a
  scan or a fax)
- `legibility` -- `clean` | `degraded` | `null`
- `handwriting` -- `none` | `some` | `mostly` | `null`
- `content` -- `{table, math, form, code, chart, photo}`, each `true`/`false`/`null`
  (`null` only where genuinely unsure; every page here was visually checked,
  so `null` was rarely needed)
- `script` -- `latin` | `cyrillic` | `greek` | `arabic` | `hebrew` | `cjk` |
  `other` | `mixed` | `null`
- `label_basis` -- how each label was derived (construction / dataset
  metadata / visual check), including any correction made after looking at
  the actual image

## Sources and licences

1. **PureDocBench** (`zhihengli-casia/puredocbench`, CC BY 4.0) -- 7
   triplets x 3 tracks (clean / digital-degraded / real-degraded) = 21 pages
   (adapted down from the requested 8; see substitutions below). See
   "PureDocBench access notes" below for how these were obtained without
   downloading the ~35GB archive.
2. **olmOCR-Bench** (`allenai/olmOCR-bench`, ODC-By 1.0) -- 17 pages rendered
   from single-page PDFs with pypdfium2: 6 `old_scans`, 4 `tables`, 4
   `arxiv_math`, 3 `multi_column`.
3. **FUNSD** test split, via `nielsr/funsd` (HF datasets-server rows API) --
   5 pages. Non-commercial research licence, evaluation-only use here.
   Original scans are 1990s US tobacco-industry business records from the
   public Truth Tobacco Industry Documents / RVL-CDIP archive.
4. **GNHK** handwriting photos, via the HF mirror `Berzerker/gnhk_ocr_dataset`
   (CC BY 4.0, original dataset by GoodNotes) -- 5 pages. The canonical
   GitHub `GoodNotes/GNHK-dataset` release requires a Google-Forms-gated
   download, so the row-level HF mirror was used instead (see substitutions
   below for two rows that were swapped out for privacy reasons).
5. **Arabic**: substituted -- see substitutions below. 3 pages from
   `HumynLabs/Arabic_Documents_Dataset_PDF` (HF, CC BY 4.0 per repo tags):
   "Lessons in Arabic Language, Book 1" by Dr. V. Abdur-Raheem, a freely
   distributed teaching text (courtesy Fatwa-Online.com).
6. **Synthetic, by construction** -- 9 pages: 2 code pages (real CPython
   stdlib source, PSF License, rendered with reportlab), 2 fax simulations,
   2 headless-Chrome screenshots, 2 camera-photo simulations, 1 rotated page
   -- all built from 5 fresh, plain text/table pages written for this bench
   (own construction, no external licence).

## Substitutions from the original brief

- **KITAB-Bench**: the HF org `kitab-bench` only hosts a `misc` repo of paper
  figures, not the benchmark's page images, and no other KITAB-Bench mirror
  with individually-addressable files was found. Substituted with 3 pages
  from `HumynLabs/Arabic_Documents_Dataset_PDF` (CC BY 4.0), a scanned Arabic
  primer with vocabulary tables and dialogue drills.
- **GNHK**: used the HF row-mirror `Berzerker/gnhk_ocr_dataset` instead of
  the GitHub release (which needs a gated Google-Forms download). Of an
  initial 5-row sample, 2 rows were dropped for containing personal data
  about private individuals (a child's first name in a tutoring session
  note; a hand-addressed envelope with two people's full names and home
  addresses) and replaced with 2 other rows from the same mirror.
- **olmOCR-Bench tables**: one initially-sampled PDF
  (`tables/022b5843eb82c5e76fb3da69a0c432187f6c_pg1_pg1.pdf`) turned out to
  be a university staff phone/room directory listing named individuals with
  extensions and usernames; dropped for the personal-data rule and replaced
  with a numerical-methods textbook page (table + worked equations).
- **PureDocBench patent triplet dropped**: the candidate chosen from the
  release manifest for "patent, table, Chinese" (`patent_004`) turned out to
  be a 2481x9019px image (aspect ratio 3.64 -- effectively several pages
  concatenated), which would be reduced to ~281px wide at our 1024px
  long-side spec and become illegible. A same-subcategory replacement
  (`patent_014`, normal ~1.4 aspect ratio, two clean data tables) was found
  and its clean render recovered at no extra download cost, but fetching its
  digital/real-degraded tracks would have needed a second full linear walk
  of the archive (the single-pass, no-random-access constraint described
  below), so the patent triplet was dropped rather than paying that cost,
  taking PureDocBench from 8 to 7 triplets (24 to 21 pages) and the overall
  bench to exactly 60 pages.

## PureDocBench access notes

The HF repo `zhihengli-casia/puredocbench` ships its image release only as
`pdb_full.tar.part-000..009`, a ~35GiB tar split into 10 parts with no
per-file access and the dataset viewer disabled -- there is no way to
download individual images through the normal HF API. To stay under the
download budget, `scripts/pdb_tar_reader.py` + `scripts/fetch_puredocbench.py`
instead treat the 10 parts as one continuous byte stream and walk the tar
structure directly over HTTP:

- For entries we don't need, only the 512-byte USTAR header is fetched (to
  read the file size and jump the cursor forward); the entry's data is never
  downloaded.
- For entries we do need (all 1,475 `gt/*.json` files, recovered for free
  from one 160MB head-of-part-000 fetch used during exploration; plus the
  clean/digital-degraded/real-degraded images for our 7 chosen pages), one
  HTTP Range GET fetches exactly that file's bytes.

This is why the 7 PureDocBench triplets were deliberately chosen to sit
early in the archive's directory order (categories `01_academic` and
`02_education`, which sort first): the tar has to be walked linearly from
the start, so an early position keeps the (many, small) header-only request
count -- and therefore the wall-clock time -- down. All 7 pages come from
just 2 of PureDocBench's 10 top-level domains for this reason; within those,
subcategories were chosen for variety (journal paper x3, PhD thesis,
technical report, lab report x2) and to mix Chinese/English and
table/math/plain content, per the ground-truth annotation counts in each
page's `gt/*.json` (see `label_basis` for each page).

Total PureDocBench download: ~227MB actual image bytes (well under budget),
across 7,391 total HTTP requests (mostly 512-byte header-only reads; the
large majority of the ~35GB archive was never downloaded).

## Counts

Total pages: **60**

By source family:
- PureDocBench: 21 (7 triplets x clean/digital-degraded/real-degraded)
- olmOCR-Bench: 17 (6 old_scans, 4 tables, 4 arxiv_math, 3 multi_column)
- FUNSD: 5
- GNHK: 5
- Arabic: 3
- Synthetic: 9 (2 code, 2 fax, 2 screenshot, 2 camera-photo, 1 rotated)

`capture_ok` (pages, multi-label so counts sum to >60):
digital_render 25, flatbed_scan 19, camera_photo 13, fax 5, screenshot 3

`legibility`: clean 46, degraded 14
`handwriting`: none 45, some 6, mostly 9
`script`: latin 42, cjk 15, arabic 3
`content` (true counts): table 32, math 23, chart 5, form 5, code 3, photo 0

## Caveats

- Three of the 7 PureDocBench "digital-degraded" pages (the dense-math
  journal page, the quantum-thesis page, and the Chinese lab report) turned
  out to be visually indistinguishable from their clean counterparts, and
  one "real-degraded" page (the English lab report) showed no camera
  signature at all (no perspective/lighting/blur, despite being tagged
  `phone_flat_indoor_normal_top` in the release manifest) -- the per-page
  degradation-profile draw was evidently very mild in these cases. They are
  labelled `legibility: clean` rather than assumed-degraded, with a note in
  `label_basis`; this is real, useful signal about the underlying dataset's
  degradation-strength variance, not a pipeline bug (verified by comparing
  file hashes/sizes between tracks -- they are genuinely different files).
- PureDocBench's "real-degraded" track is itself produced by a software
  pipeline simulating physical/capture conditions (screen capture, phone
  capture, creasing, flash, low light), not by literally printing and
  photographing pages with a camera. `capture_ok` reflects the visual
  capture type being simulated (what the image looks like), not literal
  physical provenance; this is called out per-page in `label_basis`.
- `synth_camera_02`'s table has a cosmetic header-row mismatch (a copy-paste
  leftover from the shared page generator: "Item/Quantity/Unit Price/Total"
  instead of day/employee/time/location) -- doesn't affect `content.table`.
- The FUNSD pages come from a 1990s US tobacco-industry litigation archive
  (public via the Truth Tobacco Industry Documents collection / RVL-CDIP);
  they contain business data, not private-individual personal data.
- Rotation is intentionally not scored by this bench; `synth_rotated_01` is
  kept purely as a noted edge case (see its `label_basis`).
