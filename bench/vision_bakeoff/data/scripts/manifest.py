"""
The full page manifest for the vision-bakeoff triage bench: one dict per
page, giving its id, the raw source file to process, and every labels.jsonl
field. build_all.py consumes this to produce pages/*.jpg + labels.jsonl.

content dict keys: table, math, form, code, chart, photo (True/False/None)
"""

RAW = "/Users/kavy/Code/Projects/jesteruct/bench/vision_bakeoff/data/raw"

NO_CONTENT = dict(table=False, math=False, form=False, code=False, chart=False, photo=False)


def c(**kw):
    d = dict(NO_CONTENT)
    d.update(kw)
    return d


PDB_BASE = "https://huggingface.co/datasets/zhihengli-casia/puredocbench"
PDB_LICENSE = "CC BY 4.0"
PDB_SOURCE_PREFIX = "PureDocBench (zhihengli-casia/puredocbench)"

PAGES = []

# ---------------------------------------------------------------------------
# 1. PureDocBench -- 8 triplets x 3 tracks = 24 pages
# ---------------------------------------------------------------------------
PDB_TRIPLETS = [
    dict(
        key="mathdense",
        page_id_src="01_academic/01_journal_paper/academic_paper_017_数学超密集双栏",
        clean="clean/01_academic/01_journal_paper/academic_paper_017_数学超密集双栏.png",
        digital="digital_degraded/01_academic/01_journal_paper/academic_paper_017_数学超密集双栏.png",
        real="real_degraded/01_academic/01_journal_paper/academic_paper_017_数学超密集双栏__real_screen_photography.png",
        real_chain="screen_photography",
        content=c(table=True, math=True),
        script="cjk",
        lang_note="simplified_chinese, double_column",
    ),
    dict(
        key="gnnpaper",
        page_id_src="01_academic/01_journal_paper/academic_paper_005_计算机学报_图神经网络",
        clean="clean/01_academic/01_journal_paper/academic_paper_005_计算机学报_图神经网络.png",
        digital="digital_degraded/01_academic/01_journal_paper/academic_paper_005_计算机学报_图神经网络.png",
        real="real_degraded/01_academic/01_journal_paper/academic_paper_005_计算机学报_图神经网络__real_phone_flat_normal_top.png",
        real_chain="phone_flat_indoor_normal_top",
        content=c(table=True, math=True, chart=True),
        script="cjk",
        lang_note="simplified_chinese, single_column",
    ),
    dict(
        key="jacs",
        page_id_src="01_academic/01_journal_paper/academic_paper_001_JACS_催化反应动力学",
        clean="clean/01_academic/01_journal_paper/academic_paper_001_JACS_催化反应动力学.png",
        digital="digital_degraded/01_academic/01_journal_paper/academic_paper_001_JACS_催化反应动力学.png",
        real="real_degraded/01_academic/01_journal_paper/academic_paper_001_JACS_催化反应动力学__real_screen_na_screen_screen.png",
        real_chain="screen_photography",
        content=c(table=True, math=True),
        script="latin",
        lang_note="english, double_column",
    ),
    dict(
        key="quantumthesis",
        page_id_src="01_academic/02_thesis/thesis_003_博士论文_量子信息",
        clean="clean/01_academic/02_thesis/thesis_003_博士论文_量子信息.png",
        digital="digital_degraded/01_academic/02_thesis/thesis_003_博士论文_量子信息.png",
        real="real_degraded/01_academic/02_thesis/thesis_003_博士论文_量子信息__real_phone_flat_normal_top.png",
        real_chain="phone_flat_indoor_normal_top",
        content=c(table=True, math=True),
        script="cjk",
        lang_note="simplified_chinese, single_column",
    ),
    dict(
        key="bankrisk",
        page_id_src="01_academic/03_technical_report/technical_report_011_银行风控报告",
        clean="clean/01_academic/03_technical_report/technical_report_011_银行风控报告.png",
        digital="digital_degraded/01_academic/03_technical_report/technical_report_011_银行风控报告.png",
        real="real_degraded/01_academic/03_technical_report/technical_report_011_银行风控报告__real_phone_flat_normal_top.png",
        real_chain="phone_flat_indoor_normal_top",
        content=c(table=True),
        script="cjk",
        lang_note="simplified_chinese, single_column",
    ),
    dict(
        key="labreport_zh",
        page_id_src="02_education/06_lab_report/lab_report_001_杨氏模量测定实验",
        clean="clean/02_education/06_lab_report/lab_report_001_杨氏模量测定实验.png",
        digital="digital_degraded/02_education/06_lab_report/lab_report_001_杨氏模量测定实验.png",
        real="real_degraded/02_education/06_lab_report/lab_report_001_杨氏模量测定实验__real_screenshot_na_na_na.png",
        real_chain="screenshot_compressed",
        content=c(table=True, math=True),
        script="cjk",
        lang_note="simplified_chinese, single_column",
    ),
    dict(
        key="labreport_en",
        page_id_src="02_education/06_lab_report/lab_report_003_Spectrophotometric_Iron_EN",
        clean="clean/02_education/06_lab_report/lab_report_003_Spectrophotometric_Iron_EN.png",
        digital="digital_degraded/02_education/06_lab_report/lab_report_003_Spectrophotometric_Iron_EN.png",
        real="real_degraded/02_education/06_lab_report/lab_report_003_Spectrophotometric_Iron_EN__real_phone_flat_normal_top.png",
        real_chain="phone_flat_indoor_normal_top",
        content=c(table=True, math=True),
        script="latin",
        lang_note="english, single_column",
    ),
]

REAL_CHAIN_TO_CAPTURE = {
    "phone_flat_indoor_normal_top": (["camera_photo"], "degraded",
        "real_chain_label=phone_flat_indoor_normal_top (manifest): phone photo of the printed page."),
    "screen_photography": (["camera_photo"], "degraded",
        "real_chain_label=screen_photography (manifest): phone photo of the page displayed on a screen "
        "(moire/glare expected); still fundamentally a camera capture, visually verified."),
    "screenshot_compressed": (["screenshot"], "degraded",
        "real_chain_label=screenshot_compressed (manifest): a plain digital screenshot + recompression, "
        "no physical capture device -- capture_ok corrected from the naive camera_photo/flatbed_scan "
        "assumption to screenshot after checking the manifest field."),
}

for t in PDB_TRIPLETS:
    base_source = f"{PDB_SOURCE_PREFIX}, page_id={t['page_id_src']}"
    # clean
    PAGES.append(dict(
        id=f"pdb_{t['key']}_clean",
        raw=f"{RAW}/puredocbench_images/{t['clean']}",
        source=f"{base_source} (clean track)",
        license=PDB_LICENSE,
        capture_ok=["digital_render"],
        legibility="clean",
        handwriting="none",
        content=t["content"],
        script=t["script"],
        label_basis=(
            f"construction: PureDocBench clean track is the direct HTML/CSS render, no degradation applied. "
            f"content.table/math derived from GT layout_dets category_type counts and confirmed visually "
            f"({t['lang_note']}). script set from GT page_attribute.language, confirmed visually."
            + (f" {t.get('note','')}" if t.get("note") else "")
        ),
    ))
    # digital degraded (capture_ok/legibility refined per-page in DIGITAL_CAPTURE_OVERRIDES below)
    PAGES.append(dict(
        id=f"pdb_{t['key']}_digital",
        raw=f"{RAW}/puredocbench_images/{t['digital']}",
        source=f"{base_source} (digital-degraded track)",
        license=PDB_LICENSE,
        capture_ok=["flatbed_scan", "fax"],  # refined per-page below after visual check
        legibility="degraded",
        handwriting="none",
        content=t["content"],
        script=t["script"],
        label_basis=(
            "construction: PureDocBench digital-degraded track applies one of 10 code-defined scene "
            "degradation profiles (aged_archive, book_binding, multi_gen_copy, fax_thermal, "
            "low_quality_print, ink_bleed, heavy_compression, uneven_lighting, geometric_distort, "
            "noise_blur_combo -- see scripts/degradation_v2/apply_degradation_v2.py in the PureDocBench "
            "GitHub repo) to the clean render; the release manifest does not record which profile was used "
            "per page, so capture_ok/legibility here were set from visual inspection of the actual image."
        ),
    ))
    # real degraded
    real_cap, real_leg, real_basis = REAL_CHAIN_TO_CAPTURE[t["real_chain"]]
    PAGES.append(dict(
        id=f"pdb_{t['key']}_real",
        raw=f"{RAW}/puredocbench_images/{t['real']}",
        source=f"{base_source} (real-degraded track)",
        license=PDB_LICENSE,
        capture_ok=real_cap,
        legibility=real_leg,
        handwriting="none",
        content=t["content"],
        script=t["script"],
        label_basis=(
            f"construction + release_manifest_candidate_1475.csv: {real_basis} Per the PureDocBench "
            "DATASET_CARD, the 'real-degraded' track is itself produced by applying controlled physical/"
            "capture conditions in software (screen capture, phone capture, creasing, flash, low light, "
            "etc.) to the rendered page, not by physically printing and photographing it with a camera; "
            "capture_ok reflects the visual capture type being simulated, not literal physical provenance."
        ),
    ))

# fix digital track capture_ok per visual check (filled in after downloading)
DIGITAL_CAPTURE_OVERRIDES = {
    # key: (capture_ok list, legibility, extra basis note)
    "jacs": (["flatbed_scan"], "degraded",
             "Visually: warm/gray cast, faint dust-speck noise, softened glyph edges -- consistent with "
             "the aged_archive/low_quality_print profiles, not fax (still full grayscale, not bilevel)."),
    "gnnpaper": (["flatbed_scan"], "degraded",
                 "Visually: fine repeating horizontal banding across the whole page with color preserved "
                 "-- matches the low_quality_print profile description (banding, toner shortage, streaks), "
                 "not fax_thermal (which the code defines as near-binary)."),
    "mathdense": (["digital_render", "flatbed_scan"], "clean",
                  "Visually indistinguishable from the clean track (no detectable noise/blur/banding/"
                  "yellowing) -- this page's digital-degradation draw was evidently very mild; labelled "
                  "clean rather than assuming degradation from the track name alone."),
    "quantumthesis": (["digital_render", "flatbed_scan"], "clean",
                       "Visually indistinguishable from the clean track, same as academic_paper_017 -- "
                       "labelled clean rather than assuming degradation from the track name alone."),
    "bankrisk": (["flatbed_scan"], "degraded",
                 "Visually: yellowed/warm cast, washed-out reds, scattered dust/foxing specks, slight "
                 "softening -- matches the aged_archive profile (yellowing, faded ink, foxing spots)."),
    "labreport_zh": (["digital_render", "flatbed_scan"], "clean",
                      "Visually indistinguishable from the clean track -- labelled clean rather than "
                      "assuming degradation from the track name alone."),
    "labreport_en": (["flatbed_scan"], "degraded",
                      "Visually: fine repeating horizontal banding/scan-line dropout across the whole "
                      "page plus small vertical scratch marks -- matches the low_quality_print profile."),
}

for entry in PAGES:
    for key, (cap, leg, note) in DIGITAL_CAPTURE_OVERRIDES.items():
        if entry["id"] == f"pdb_{key}_digital":
            entry["capture_ok"] = cap
            entry["legibility"] = leg
            entry["label_basis"] += " " + note

# fix real-degraded track legibility per visual check (filled in after downloading;
# the manifest's real_chain_label predicts capture TYPE reliably, but not severity --
# several of these turned out to be very mild draws, crisp and clearly legible)
REAL_CAPTURE_OVERRIDES = {
    "jacs": (["camera_photo"], "degraded",
             "Visually: photo of the page open on a laptop screen (visible dark bezel, on-screen glare, "
             "trackpad/keyboard visible below) -- confirms screen_photography; some softness/glare."),
    "gnnpaper": (["camera_photo"], "clean",
                 "Visually: sharp, well-lit top-down phone photo on a laptop keyboard -- no meaningful "
                 "camera degradation despite the real-degraded track name."),
    "mathdense": (["camera_photo"], "degraded",
                  "Visually: photo of the page open on a laptop/monitor screen (dark bezel visible) -- "
                  "confirms screen_photography; visible glare/softness."),
    "quantumthesis": (["camera_photo"], "clean",
                       "Visually: sharp top-down phone photo of the printed page (curled page edges "
                       "visible, plain background) -- no meaningful camera degradation."),
    "bankrisk": (["camera_photo"], "clean",
                 "Visually: sharp top-down phone photo on a laptop keyboard, page curling at the bottom "
                 "edge -- no meaningful camera degradation."),
    "labreport_zh": (["screenshot"], "clean",
                      "Visually: plain screenshot with a small gray browser/viewer margin, otherwise "
                      "pixel-for-pixel like the clean/digital renders -- no compression artifacts visible."),
    "labreport_en": (["camera_photo", "digital_render"], "clean",
                      "Visually indistinguishable from a clean digital render (no perspective, lighting "
                      "gradient, blur, or background of any kind) despite the manifest's "
                      "phone_flat_indoor_normal_top label -- this page's real-degradation draw left no "
                      "visible camera signature, so digital_render is included alongside camera_photo."),
}

for entry in PAGES:
    for key, (cap, leg, note) in REAL_CAPTURE_OVERRIDES.items():
        if entry["id"] == f"pdb_{key}_real":
            entry["capture_ok"] = cap
            entry["legibility"] = leg
            entry["label_basis"] += " " + note

# ---------------------------------------------------------------------------
# 2. olmOCR-Bench -- 17 pages (allenai/olmOCR-bench, ODC-By)
# ---------------------------------------------------------------------------
OLMOCR_SOURCE = "olmOCR-Bench (allenai/olmOCR-bench)"
OLMOCR_LICENSE = "ODC-By 1.0"

OLD_SCANS = [
    ("1", "mostly", "Handwritten Civil War-era letter to Theodore Roosevelt, dated 1914; clean legible "
                     "flatbed scan of aged paper (LOC crowd.loc.gov transcription campaign)."),
    ("2", "some", "Typewritten Western Union inter-office letter; only the closing signature "
                  "('Robert Lyles Beal') is handwritten."),
    ("3", "mostly", "Handwritten letter on Beckner Printing Co. letterhead (page 2 of a multi-page letter)."),
    ("4", "mostly", "Handwritten letter on Beckner Printing Co. letterhead (page 3, continuation)."),
    ("5", "mostly", "Handwritten letter on Beckner Printing Co. letterhead (page continuation, different content)."),
    ("6", "some", "Typewritten confidential letter; small handwritten page-number/ack annotation plus "
                  "handwritten closing signature."),
]
for i, (num, hw, basis) in enumerate(OLD_SCANS, start=1):
    PAGES.append(dict(
        id=f"olmocr_oldscans_{i:02d}",
        raw=f"{RAW}/olmocr_rendered/old_scans/{num}.png",
        source=f"{OLMOCR_SOURCE}, bench_data/pdfs/old_scans/{num}.pdf (page 1) -- original scan via "
               f"crowd.loc.gov (Library of Congress, public domain)",
        license=OLMOCR_LICENSE,
        capture_ok=["flatbed_scan"],
        legibility="clean",
        handwriting=hw,
        content=NO_CONTENT,
        script="latin",
        label_basis=f"dataset metadata (olmOCR-bench 'old_scans' category = real old scanned documents) "
                    f"+ visual check: {basis}",
    ))

TABLES_PAGES = [
    ("008d1dbe3c5a5fd2bac6e4f29acc45e711aa_pg8_pg1", c(table=True, chart=True),
     "Environmental-health journal reprint page with a HYSPLIT trajectory line chart/map figure and two "
     "GenBank-match data tables; has a PDF text layer (born-digital)."),
    ("0091c5b23fe54b3a7cbe5b0b8c26057b7d70_pg3_pg1", c(table=True),
     "Two-column BMJ journal page (immunisation study) with two data tables; text layer present."),
    ("00e980a0c4645fc83f27c467d10bbdeb8661_pg64", c(table=True),
     "Engineering-report page (Atlanta CSO remedial measures) with a milestones table; text layer present."),
    ("0ee4f7788272e811ae7717b7133770892fe6_pg8", c(table=True, math=True),
     "Numerical-methods textbook page (quadratic splines) with a data table and multiple worked equations; "
     "text layer present. Substituted for a different table_tests candidate "
     "(tables/022b5843eb82c5e76fb3da69a0c432187f6c_pg1_pg1.pdf) that turned out to be a university staff "
     "phone/room directory listing named individuals -- excluded per the personal-data rule."),
]
for i, (name, content, basis) in enumerate(TABLES_PAGES, start=1):
    PAGES.append(dict(
        id=f"olmocr_tables_{i:02d}",
        raw=f"{RAW}/olmocr_rendered/tables/{name}.png",
        source=f"{OLMOCR_SOURCE}, bench_data/pdfs/tables/{name}.pdf (page 1)",
        license=OLMOCR_LICENSE,
        capture_ok=["digital_render"],
        legibility="clean",
        handwriting="none",
        content=content,
        script="latin",
        label_basis=f"PDF has an extractable text layer (checked with pypdfium2) -> born-digital. {basis}",
    ))

ARXIV_MATH_PAGES = [
    ("2502.15977_pg21", c(math=True),
     "Math paper (toric superschemes) with a colored geometric fan diagram (not a data chart) and dense "
     "equations."),
    ("2503.02004_pg9", c(math=True, chart=True),
     "Signal-processing paper with an 'Algorithm' pseudocode box (math/algorithmic notation, not literal "
     "source code -- content.code left false) plus 8 heatmap/scatter data-visualization panels (charts)."),
    ("2503.03754_pg10", c(math=True),
     "Information-theory paper, dense multi-line equations, references list, no table/figure."),
    ("2503.03759_pg9", c(math=True),
     "Information-theory paper (complex-valued Shannon entropy), dense equations, no table/figure."),
]
for i, (name, content, basis) in enumerate(ARXIV_MATH_PAGES, start=1):
    PAGES.append(dict(
        id=f"olmocr_arxivmath_{i:02d}",
        raw=f"{RAW}/olmocr_rendered/arxiv_math/{name}.png",
        source=f"{OLMOCR_SOURCE}, bench_data/pdfs/arxiv_math/{name}.pdf (page 1) -- arXiv preprint",
        license=OLMOCR_LICENSE,
        capture_ok=["digital_render"],
        legibility="clean",
        handwriting="none",
        content=content,
        script="latin",
        label_basis=f"olmOCR-bench 'arxiv_math' category (math-heavy arXiv pages); text layer confirmed. {basis}",
    ))

MULTI_COLUMN_PAGES = [
    ("0005784d0d255f6652180433936fa2998188_page_1_pg1", NO_CONTENT,
     "Two-column NLP paper (title page, abstract, intro); named authors are standard public academic "
     "authorship, not private personal data."),
    ("00187fe0533b1e8ddc748adab4924b6f7099_page_10_pg1", NO_CONTENT,
     "Two-column ACS Nano paper, author-information/acknowledgments/references page; named authors are "
     "public academic authorship."),
    ("0083fb2109e58be50aec2eca07fcbfe1230b_page_1_pg1", NO_CONTENT,
     "Three-column 1995 IRS 'Instructions for Form 1116' page -- instructional text about a tax form, not "
     "a fillable form itself, so content.form left false."),
]
for i, (name, content, basis) in enumerate(MULTI_COLUMN_PAGES, start=1):
    PAGES.append(dict(
        id=f"olmocr_multicol_{i:02d}",
        raw=f"{RAW}/olmocr_rendered/multi_column/{name}.png",
        source=f"{OLMOCR_SOURCE}, bench_data/pdfs/multi_column/{name}.pdf (page 1)",
        license=OLMOCR_LICENSE,
        capture_ok=["digital_render"],
        legibility="clean",
        handwriting="none",
        content=content,
        script="latin",
        label_basis=f"olmOCR-bench 'multi_column' category; text layer confirmed. {basis}",
    ))

# ---------------------------------------------------------------------------
# 3. FUNSD (nielsr/funsd test split, non-commercial licence, evaluation only)
# ---------------------------------------------------------------------------
FUNSD_LICENSE = "FUNSD non-commercial research licence (evaluation use only)"
FUNSD_PAGES = [
    (0, ["flatbed_scan", "fax"], "degraded", "none", c(form=True),
     "Ohio Attorney General confidential facsimile transmission cover sheet; a printed fax-machine header "
     "banner is baked into the page image, but filled-in fields (name, numbers, date) look typewritten, not "
     "handwritten -- handwriting set to none rather than assumed."),
    (1, ["fax"], "degraded", "some", c(form=True, table=True),
     "Lorillard tobacco co. internal fax memo (Truth Tobacco Industry Documents / RVL-CDIP source, public "
     "litigation archive); fax header banner visible; one handwritten 'X' checkbox mark; data table of "
     "store volumes."),
    (2, ["flatbed_scan"], "clean", "some", c(form=True),
     "Lorillard 'Competitive Product Introduction' progress-report form; handwritten 'X' checkbox and a "
     "handwritten '(Wisconsin)' annotation; otherwise typewritten."),
    (3, ["fax"], "degraded", "some", c(form=True),
     "Lorillard Tampa->Greensboro fax, 'Retail Excel Progress Report'; fax header banner visible; "
     "handwritten '#17' note and 'X' checkbox mark."),
    (4, ["flatbed_scan"], "clean", "some", c(form=True, table=True),
     "Lorillard 'Old Gold' progress-report form with a store-accounts table; handwritten division names "
     "('Milw. South' / 'Milw. North') and an 'X' checkbox mark."),
]
for idx, cap, leg, hw, content, basis in FUNSD_PAGES:
    PAGES.append(dict(
        id=f"funsd_{idx+1:02d}",
        raw=f"{RAW}/funsd/funsd_{idx}.jpg",
        source=f"FUNSD test split via nielsr/funsd (datasets-server rows API), row_idx={idx} -- original "
               f"scans are 1990s US tobacco-industry business records (Truth Tobacco Industry Documents "
               f"archive, public via litigation)",
        license=FUNSD_LICENSE,
        capture_ok=cap,
        legibility=leg,
        handwriting=hw,
        content=content,
        script="latin",
        label_basis=f"visual check of the actual scan: {basis}",
    ))

# ---------------------------------------------------------------------------
# 4. GNHK -- 5 pages, full-page phone photos of handwriting
#    (mirror: HF dataset Berzerker/gnhk_ocr_dataset, original GNHK is CC BY 4.0
#    by GoodNotes; GitHub GoodNotes/GNHK-dataset requires a Google-Forms
#    download, so the HF row-level mirror was used instead)
# ---------------------------------------------------------------------------
GNHK_LICENSE = "CC BY 4.0 (GNHK dataset, GoodNotes)"
GNHK_PAGES = [
    (2, c(), "Student's ruled-notebook English sentence-copying exercise (proverbs about greatness), "
             "photographed sideways (rotated ~90 degrees) on a table."),
    (3, c(), "Business/study notes on Amazon FBA strategy in a spiral notebook, photographed on a desk."),
    (6, c(), "List of handwritten inspirational quotes in a notebook; visible page crease/shadow across "
             "the frame."),
    (8, c(table=True), "Handwritten laundry-service price list with a clear column-header row "
                        "(Services / Price / Kilos / Amount) -- a simple hand-drawn table."),
    (13, c(), "Handwritten English essay/notes about GDP and a trip to Guilin, photographed sideways "
              "(rotated ~90 degrees) in a ruled notebook."),
]
for i, (row, content, basis) in enumerate(GNHK_PAGES, start=1):
    PAGES.append(dict(
        id=f"gnhk_{i:02d}",
        raw=f"{RAW}/gnhk/gnhk_{row}.jpg",
        source=f"GNHK dataset via HF mirror Berzerker/gnhk_ocr_dataset (datasets-server rows API), "
               f"row_idx={row}",
        license=GNHK_LICENSE,
        capture_ok=["camera_photo"],
        legibility="clean" if row != 6 else "degraded",
        handwriting="mostly",
        content=content,
        script="latin",
        label_basis=f"visual check: {basis} Two other sampled rows (row 0: a child's named tutoring "
                    f"session note; row 5: a hand-addressed envelope with full names and home addresses) "
                    f"were excluded and replaced with these under the personal-data exclusion rule.",
    ))

# ---------------------------------------------------------------------------
# 5. Arabic -- 3 pages (substituted for KITAB-Bench, which has no accessible
#    HF dataset repo beyond a paper-figures-only 'kitab-bench/misc'; used
#    HumynLabs/Arabic_Documents_Dataset_PDF instead, CC BY 4.0 per repo tags)
# ---------------------------------------------------------------------------
ARABIC_LICENSE = "CC BY 4.0 (per HF repo tags)"
ARABIC_PAGES = [
    ("5", c(), "Lesson 1 of an Arabic-language primer: line drawings (door, mosque, house, key, pen, "
               "book, chair, bed, desk) with Arabic vocabulary captions."),
    ("50", c(table=True), "Vocabulary box (ruled grid of Arabic words) followed by a Q&A dialogue drill."),
    ("100", c(), "Lesson 18 Q&A dialogue drill (family members, bicycles, holidays, shops)."),
]
for i, (num, content, basis) in enumerate(ARABIC_PAGES, start=1):
    PAGES.append(dict(
        id=f"arabic_{i:02d}",
        raw=f"{RAW}/arabic_rendered/page_{num}.png",
        source=f"HumynLabs/Arabic_Documents_Dataset_PDF (HF), 549_01_Lessons_in_Arabic_Language-{num}.pdf "
               f"(page 1) -- 'Lessons in Arabic Language, Book 1' by Dr. V. Abdur-Raheem, Islaamic "
               f"University of Madeenah (freely distributed teaching text, courtesy Fatwa-Online.com)",
        license=ARABIC_LICENSE,
        capture_ok=["flatbed_scan"],
        legibility="clean",
        handwriting="none",
        content=content,
        script="arabic",
        label_basis=f"visual check: {basis} No PDF text layer for the Arabic body text (only a small "
                    f"English attribution footer), consistent with a scanned page image. Substituted for "
                    f"KITAB-Bench, whose HF org (kitab-bench) only hosts paper figures, not the benchmark "
                    f"images themselves.",
    ))

# ---------------------------------------------------------------------------
# 6. Synthetic, by construction -- 9 pages
# ---------------------------------------------------------------------------
SYNTH_LICENSE_CODE = "code content: PSF License (CPython stdlib); page layout: own construction"
SYNTH_LICENSE_OWN = "own construction for this benchmark"

PAGES.append(dict(
    id="synth_code_01",
    raw=f"{RAW}/synthetic/code/csv_page.png",
    source="Synthetic: reportlab-rendered PDF of CPython Lib/csv.py (lines 61-106), monospace font",
    license=SYNTH_LICENSE_CODE,
    capture_ok=["digital_render"],
    legibility="clean",
    handwriting="none",
    content=c(code=True),
    script="latin",
    label_basis="construction: real permissively-licensed (PSF) Python source code rendered to a "
                "born-digital PDF with reportlab, Courier font.",
))
PAGES.append(dict(
    id="synth_code_02",
    raw=f"{RAW}/synthetic/code/textwrap_page.png",
    source="Synthetic: reportlab-rendered PDF of CPython Lib/textwrap.py (lines 21-66), monospace font",
    license=SYNTH_LICENSE_CODE,
    capture_ok=["digital_render"],
    legibility="clean",
    handwriting="none",
    content=c(code=True),
    script="latin",
    label_basis="construction: real permissively-licensed (PSF) Python source code rendered to a "
                "born-digital PDF with reportlab, Courier font.",
))

PAGES.append(dict(
    id="synth_fax_01",
    raw=f"{RAW}/synthetic/fax/memo_fax1.png",
    source="Synthetic: original 'Internal Memorandum' text page -> 1-bit Floyd-Steinberg dither, 3x "
           "downsample/upsample, ~1.5deg skew, salt speckle noise, added fax header line",
    license=SYNTH_LICENSE_OWN,
    capture_ok=["fax"],
    legibility="degraded",
    handwriting="none",
    content=c(),
    script="latin",
    label_basis="construction: degradation pipeline in scripts/synth_degrade.py::make_fax applied to a "
                "distinct clean source page (not used as a bench page in its clean form).",
))
PAGES.append(dict(
    id="synth_fax_02",
    raw=f"{RAW}/synthetic/fax/invoice_fax2.png",
    source="Synthetic: original 'Purchase Order Summary' table page -> same fax pipeline as synth_fax_01",
    license=SYNTH_LICENSE_OWN,
    capture_ok=["fax"],
    legibility="degraded",
    handwriting="none",
    content=c(table=True),
    script="latin",
    label_basis="construction: degradation pipeline in scripts/synth_degrade.py::make_fax applied to a "
                "distinct clean source page containing a small table (still visible through the fax noise).",
))

PAGES.append(dict(
    id="synth_screenshot_01",
    raw=f"{RAW}/synthetic/html/readme_page.png",
    source="Synthetic: headless-Chrome screenshot of a hand-authored GitHub-README-style HTML page",
    license=SYNTH_LICENSE_OWN,
    capture_ok=["screenshot"],
    legibility="clean",
    handwriting="none",
    content=c(code=True),
    script="latin",
    label_basis="construction: rendered with `Google Chrome --headless --screenshot`; page includes two "
                "fenced code blocks (pip install / python snippet).",
))
PAGES.append(dict(
    id="synth_screenshot_02",
    raw=f"{RAW}/synthetic/html/spreadsheet_page.png",
    source="Synthetic: headless-Chrome screenshot of a hand-authored spreadsheet-UI-style HTML page",
    license=SYNTH_LICENSE_OWN,
    capture_ok=["screenshot"],
    legibility="clean",
    handwriting="none",
    content=c(table=True),
    script="latin",
    label_basis="construction: rendered with `Google Chrome --headless --screenshot`; mimics a "
                "spreadsheet grid UI (row/column headers, formula bar).",
))

PAGES.append(dict(
    id="synth_camera_01",
    raw=f"{RAW}/synthetic/camera/notice_cam1.jpg",
    source="Synthetic: original 'Community Notice Board' text page -> perspective warp onto a textured "
           "desk-colored background, lighting-gradient vignette, Gaussian blur, JPEG compression",
    license=SYNTH_LICENSE_OWN,
    capture_ok=["camera_photo"],
    legibility="degraded",
    handwriting="none",
    content=c(),
    script="latin",
    label_basis="construction: degradation pipeline in scripts/synth_degrade.py::make_camera_photo "
                "applied to a distinct clean source page.",
))
PAGES.append(dict(
    id="synth_camera_02",
    raw=f"{RAW}/synthetic/camera/schedule_cam2.jpg",
    source="Synthetic: original 'Weekly Shift Schedule' table page -> same camera-photo pipeline as "
           "synth_camera_01",
    license=SYNTH_LICENSE_OWN,
    capture_ok=["camera_photo"],
    legibility="degraded",
    handwriting="none",
    content=c(table=True),
    script="latin",
    label_basis="construction: degradation pipeline in scripts/synth_degrade.py::make_camera_photo "
                "applied to a distinct clean source page containing a small table. Note: the table's "
                "header row text ('Item/Quantity/Unit Price/Total') is a leftover from the shared page "
                "generator and doesn't match the day/employee/time/location columns below it -- a cosmetic "
                "mismatch, not a labelling issue (content.table is still true).",
))

PAGES.append(dict(
    id="synth_rotated_01",
    raw=f"{RAW}/synthetic/rotated/notice_rotate.png",
    source="Synthetic: original 'Building Access Notice' text page, rotated 90 degrees",
    license=SYNTH_LICENSE_OWN,
    capture_ok=["digital_render"],
    legibility="clean",
    handwriting="none",
    content=c(),
    script="latin",
    label_basis="construction: clean born-digital page rotated 90 degrees clockwise; rotation is not "
                "itself scored by this bench, kept only as a noted edge case.",
))
