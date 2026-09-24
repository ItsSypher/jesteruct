# Jev lane classification test

98 cases: img 60, pdf 25, ocr 8, garb 5.

| system | run | n | lane acc | under-route | over-route | uncertain | text-layer acc | img | pdf | ocr | garb | p50 s | p95 s | $ per 1k |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jev_c2 | 1 | 98 | 0.796 | 0.163 | 0.041 | 0.000 | 0.959 | 48/60 | 22/25 | 4/8 | 4/5 | 0.3 | 0.38 | 0.0572 |
| jev_c2 | 2 | 98 | 0.827 | 0.143 | 0.031 | 0.000 | 0.959 | 49/60 | 22/25 | 5/8 | 5/5 | 0.3 | 0.35 | 0.0572 |
| jev_v1_probes | 1 | 98 | 0.643 | 0.255 | 0.102 | 0.000 | 0.929 | 42/60 | 13/25 | 4/8 | 4/5 | 0.3 | 0.36 | 0.0354 |
| jev_v1_probes | 2 | 98 | 0.643 | 0.245 | 0.112 | 0.000 | 0.939 | 43/60 | 11/25 | 4/8 | 5/5 | 0.3 | 0.38 | 0.0354 |
| jev_v2_probes_text | 1 | 98 | 0.724 | 0.235 | 0.041 | 0.000 | 0.969 | 43/60 | 20/25 | 4/8 | 4/5 | 0.3 | 0.37 | 0.0545 |
| jev_v2_probes_text | 2 | 98 | 0.724 | 0.235 | 0.041 | 0.000 | 0.980 | 43/60 | 20/25 | 4/8 | 4/5 | 0.3 | 0.36 | 0.0545 |
| jev_v3_full | 1 | 98 | 0.796 | 0.173 | 0.031 | 0.000 | 0.959 | 51/60 | 19/25 | 4/8 | 4/5 | 0.3 | 0.38 | 0.0561 |
| jev_v3_full | 2 | 98 | 0.806 | 0.163 | 0.031 | 0.000 | 0.969 | 51/60 | 20/25 | 4/8 | 4/5 | 0.31 | 0.37 | 0.0561 |
| jev_vector | 1 | 98 | 0.918 | 0.051 | 0.031 | 0.000 | 0.990 | 58/60 | 22/25 | 5/8 | 5/5 | 0.29 | 0.37 | 0.0414 |
| jev_vector | 2 | 98 | 0.918 | 0.051 | 0.031 | 0.000 | 0.990 | 58/60 | 22/25 | 5/8 | 5/5 | 0.29 | 0.36 | 0.0414 |
| jev_vector_novision | 1 | 98 | 0.786 | 0.143 | 0.071 | 0.000 | 0.990 | 45/60 | 23/25 | 4/8 | 5/5 | 0.3 | 0.37 | 0.0397 |
| jev_vector_novision | 2 | 98 | 0.776 | 0.143 | 0.082 | 0.000 | 0.990 | 44/60 | 23/25 | 4/8 | 5/5 | 0.3 | 0.37 | 0.0397 |
| jevvec_claude-haiku-latest | 1 | 98 | 0.888 | 0.061 | 0.051 | 0.000 | 0.990 | 55/60 | 21/25 | 6/8 | 5/5 | 0.31 | 0.39 | 0.0414 |
| jevvec_claude-haiku-latest_skiptrusted | 1 | 98 | 0.878 | 0.071 | 0.051 | 0.000 | 0.990 | 55/60 | 21/25 | 5/8 | 5/5 | 0.3 | 0.37 | 0.0411 |
| jevvec_gemini-3.5-flash-lite | 1 | 98 | 0.908 | 0.051 | 0.041 | 0.000 | 0.990 | 56/60 | 23/25 | 5/8 | 5/5 | 0.3 | 0.39 | 0.0414 |
| jevvec_gemini-3.5-flash-lite_skiptrusted | 1 | 98 | 0.939 | 0.031 | 0.031 | 0.000 | 0.990 | 58/60 | 23/25 | 6/8 | 5/5 | 0.3 | 0.41 | 0.0411 |
| jevvec_gemini-3.8-flash | 1 | 98 | 0.929 | 0.041 | 0.031 | 0.000 | 0.990 | 58/60 | 22/25 | 6/8 | 5/5 | 0.31 | 0.4 | 0.0414 |
| jevvec_gemini-3.8-flash_skiptrusted | 1 | 98 | 0.918 | 0.051 | 0.031 | 0.000 | 0.990 | 58/60 | 21/25 | 6/8 | 5/5 | 0.31 | 0.43 | 0.0411 |
| jevvec_gpt-6-luna | 1 | 98 | 0.888 | 0.082 | 0.031 | 0.000 | 0.990 | 54/60 | 22/25 | 6/8 | 5/5 | 0.3 | 0.4 | 0.0414 |
| jevvec_gpt-6-luna_skiptrusted | 1 | 98 | 0.878 | 0.082 | 0.041 | 0.000 | 0.990 | 53/60 | 22/25 | 6/8 | 5/5 | 0.3 | 0.39 | 0.0411 |
| llm_gemini-3.8-flash | 1 | 94 | 0.904 | 0.032 | 0.064 | 0.000 | 0.979 | 53/57 | 21/24 | 7/8 | 4/5 | 4.12 | 12.99 | 2.4351 |
| llm_gemini-3.8-flash_c2 | 1 | 96 | 0.865 | 0.031 | 0.104 | 0.000 | 0.979 | 51/59 | 22/25 | 6/7 | 4/5 | 4.1 | 13.5 | 2.5647 |
| llm_gpt-6-luna | 1 | 98 | 0.888 | 0.061 | 0.051 | 0.000 | 0.980 | 54/60 | 21/25 | 7/8 | 5/5 | 3.38 | 8.01 | 0.1811 |
| llm_gpt-6-luna_c2 | 1 | 98 | 0.929 | 0.031 | 0.041 | 0.000 | 0.990 | 56/60 | 23/25 | 7/8 | 5/5 | 3.23 | 5.4 | 0.1832 |
| rules | 1 | 98 | 0.643 | 0.235 | 0.122 | 0.000 | 0.980 | 39/60 | 16/25 | 3/8 | 5/5 | 0 | 0 | 0.0 |
| vision_only | 1 | 98 | 0.888 | 0.082 | 0.031 | 0.000 | 0.980 | 56/60 | 18/25 | 8/8 | 5/5 | 0 | 0 | 0.0 |

## Run-to-run agreement (Jev)

- jev_c2: same lane on 0.969 of cases; mean change in chosen-lane probability 0.020.
- jev_v1_probes: same lane on 0.949 of cases; mean change in chosen-lane probability 0.014.
- jev_v2_probes_text: same lane on 1.000 of cases; mean change in chosen-lane probability 0.012.
- jev_v3_full: same lane on 0.990 of cases; mean change in chosen-lane probability 0.015.
- jev_vector: same lane on 1.000 of cases; mean change in chosen-lane probability 0.012.
- jev_vector_novision: same lane on 0.990 of cases; mean change in chosen-lane probability 0.024.

## Calibration of Jev's lane probability (run 1)

- jev_c2: mean p when right 0.920, when wrong 0.726, ECE 0.097; p>=0.5: acc 0.811 on 95/98; p>=0.7: acc 0.867 on 83/98; p>=0.9: acc 0.939 on 66/98; p>=0.99: acc 0.966 on 29/98
- jev_v1_probes: mean p when right 0.899, when wrong 0.823, ECE 0.238; p>=0.5: acc 0.670 on 91/98; p>=0.7: acc 0.679 on 81/98; p>=0.9: acc 0.698 on 63/98; p>=0.99: acc 0.800 on 45/98
- jev_v2_probes_text: mean p when right 0.906, when wrong 0.871, ECE 0.188; p>=0.5: acc 0.724 on 98/98; p>=0.7: acc 0.738 on 84/98; p>=0.9: acc 0.776 on 67/98; p>=0.99: acc 0.758 on 33/98
- jev_v3_full: mean p when right 0.905, when wrong 0.774, ECE 0.108; p>=0.5: acc 0.794 on 97/98; p>=0.7: acc 0.812 on 85/98; p>=0.9: acc 0.922 on 64/98; p>=0.99: acc 0.944 on 18/98
- jev_vector: mean p when right 0.785, when wrong 0.600, ECE 0.163; p>=0.5: acc 0.947 on 94/98; p>=0.7: acc 0.960 on 75/98; p>=0.9: acc 1.000 on 1/98; p>=0.99: none kept
- jev_vector_novision: mean p when right 0.727, when wrong 0.624, ECE 0.103; p>=0.5: acc 0.800 on 90/98; p>=0.7: acc 0.877 on 57/98; p>=0.9: acc 1.000 on 3/98; p>=0.99: none kept
- jevvec_claude-haiku-latest: mean p when right 0.789, when wrong 0.616, ECE 0.145; p>=0.5: acc 0.916 on 95/98; p>=0.7: acc 0.947 on 75/98; p>=0.9: none kept; p>=0.99: none kept
- jevvec_claude-haiku-latest_skiptrusted: mean p when right 0.792, when wrong 0.593, ECE 0.157; p>=0.5: acc 0.925 on 93/98; p>=0.7: acc 0.947 on 75/98; p>=0.9: acc 1.000 on 3/98; p>=0.99: none kept
- jevvec_gemini-3.5-flash-lite: mean p when right 0.777, when wrong 0.581, ECE 0.176; p>=0.5: acc 0.946 on 93/98; p>=0.7: acc 0.973 on 73/98; p>=0.9: acc 1.000 on 1/98; p>=0.99: none kept
- jevvec_gemini-3.5-flash-lite_skiptrusted: mean p when right 0.762, when wrong 0.620, ECE 0.192; p>=0.5: acc 0.967 on 92/98; p>=0.7: acc 0.971 on 69/98; p>=0.9: acc 1.000 on 3/98; p>=0.99: none kept
- jevvec_gemini-3.8-flash: mean p when right 0.780, when wrong 0.626, ECE 0.159; p>=0.5: acc 0.947 on 94/98; p>=0.7: acc 0.961 on 76/98; p>=0.9: acc 1.000 on 1/98; p>=0.99: none kept
- jevvec_gemini-3.8-flash_skiptrusted: mean p when right 0.780, when wrong 0.584, ECE 0.178; p>=0.5: acc 0.957 on 93/98; p>=0.7: acc 0.961 on 76/98; p>=0.9: acc 1.000 on 1/98; p>=0.99: none kept
- jevvec_gpt-6-luna: mean p when right 0.771, when wrong 0.599, ECE 0.136; p>=0.5: acc 0.922 on 90/98; p>=0.7: acc 0.971 on 70/98; p>=0.9: acc 1.000 on 1/98; p>=0.99: none kept
- jevvec_gpt-6-luna_skiptrusted: mean p when right 0.775, when wrong 0.578, ECE 0.174; p>=0.5: acc 0.934 on 91/98; p>=0.7: acc 0.957 on 69/98; p>=0.9: acc 1.000 on 4/98; p>=0.99: none kept

## Errors (run 1)

**jev_c2** (20 wrong)
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_pdb_labreport_en_digital: said L3, truth ['L4']
- img_olmocr_oldscans_02: said L4, truth ['L3']
- img_olmocr_oldscans_04: said L3, truth ['L5']
- img_olmocr_oldscans_05: said L3, truth ['L5']
- img_funsd_01: said L3, truth ['L4']
- img_funsd_04: said L3, truth ['L4']
- img_gnhk_01: said L4, truth ['L5']
- img_gnhk_02: said L4, truth ['L5']
- img_gnhk_03: said L4, truth ['L5']
- img_gnhk_04: said L4, truth ['L5']
- img_gnhk_05: said L4, truth ['L5']
- pdf_olmx_02: said L2, truth ['L1']
- pdf_olmx_07: said L3, truth ['L4']
- pdf_olmx_10: said L3, truth ['L1']
- ocr_olmocr_oldscans_02: said L4, truth ['L3']
- ocr_olmocr_oldscans_04: said L3, truth ['L5']
- ocr_funsd_04: said L3, truth ['L4']
- ocr_gnhk_02: said L4, truth ['L5']
- garb_olmocr_arxivmath_01_cid: said L2, truth ['L3']

**jev_v1_probes** (35 wrong)
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_pdb_labreport_en_digital: said L3, truth ['L4']
- img_olmocr_oldscans_01: said L4, truth ['L5']
- img_olmocr_oldscans_02: said L4, truth ['L3']
- img_olmocr_oldscans_03: said L3, truth ['L5']
- img_olmocr_oldscans_04: said L3, truth ['L5']
- img_olmocr_oldscans_05: said L3, truth ['L5']
- img_funsd_01: said L3, truth ['L4']
- img_funsd_02: said L3, truth ['L4']
- img_funsd_04: said L3, truth ['L4']
- img_gnhk_01: said L4, truth ['L5']
- img_gnhk_02: said L4, truth ['L5']
- img_gnhk_03: said L4, truth ['L5']
- img_gnhk_04: said L4, truth ['L5']
- img_gnhk_05: said L4, truth ['L5']
- img_synth_fax_01: said L3, truth ['L4']
- img_synth_screenshot_02: said L4, truth ['L3']
- img_synth_rotated_01: said L4, truth ['L3']
- pdf_olmocr_tables_03: said L3, truth ['L2']
- pdf_olmocr_tables_04: said L1, truth ['L2']
- pdf_olmocr_multicol_01: said L1, truth ['L2']
- pdf_olmocr_multicol_02: said L3, truth ['L2']
- pdf_olmocr_multicol_03: said L1, truth ['L2']
- pdf_code_01: said L1, truth ['L2']
- pdf_code_02: said L1, truth ['L2']
- pdf_olmx_01: said L3, truth ['L2']
- pdf_olmx_03: said L3, truth ['L1']
- pdf_olmx_09: said L3, truth ['L1']
- pdf_olmx_10: said L3, truth ['L1']
- pdf_olmx_11: said L1, truth ['L2']
- ocr_olmocr_oldscans_02: said L4, truth ['L3']
- ocr_olmocr_oldscans_04: said L3, truth ['L5']
- ocr_funsd_04: said L3, truth ['L4']
- ocr_gnhk_02: said L4, truth ['L5']
- garb_olmocr_arxivmath_01_cid: said L2, truth ['L3']

**jev_v2_probes_text** (27 wrong)
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_pdb_quantumthesis_real: said L3, truth ['L4']
- img_pdb_labreport_en_digital: said L3, truth ['L4']
- img_olmocr_oldscans_01: said L4, truth ['L5']
- img_olmocr_oldscans_02: said L4, truth ['L3']
- img_olmocr_oldscans_03: said L3, truth ['L5']
- img_olmocr_oldscans_04: said L3, truth ['L5']
- img_olmocr_oldscans_05: said L3, truth ['L5']
- img_funsd_01: said L3, truth ['L4']
- img_funsd_02: said L3, truth ['L4']
- img_funsd_04: said L3, truth ['L4']
- img_gnhk_01: said L4, truth ['L5']
- img_gnhk_02: said L4, truth ['L5']
- img_gnhk_03: said L4, truth ['L5']
- img_gnhk_04: said L4, truth ['L5']
- img_gnhk_05: said L4, truth ['L5']
- img_synth_rotated_01: said L4, truth ['L3']
- pdf_olmocr_multicol_01: said L1, truth ['L2']
- pdf_olmocr_multicol_02: said L1, truth ['L2']
- pdf_olmocr_multicol_03: said L1, truth ['L2']
- pdf_olmx_10: said L3, truth ['L1']
- pdf_olmx_11: said L1, truth ['L2']
- ocr_olmocr_oldscans_02: said L4, truth ['L3']
- ocr_olmocr_oldscans_04: said L3, truth ['L5']
- ocr_funsd_04: said L3, truth ['L4']
- ocr_gnhk_02: said L4, truth ['L5']
- garb_olmocr_arxivmath_01_cid: said L2, truth ['L3']

**jev_v3_full** (20 wrong)
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_pdb_labreport_en_digital: said L3, truth ['L4']
- img_olmocr_oldscans_02: said L4, truth ['L3']
- img_funsd_01: said L3, truth ['L4']
- img_gnhk_01: said L4, truth ['L5']
- img_gnhk_02: said L4, truth ['L5']
- img_gnhk_03: said L4, truth ['L5']
- img_gnhk_04: said L4, truth ['L5']
- img_gnhk_05: said L4, truth ['L5']
- pdf_olmocr_multicol_01: said L1, truth ['L2']
- pdf_olmocr_multicol_02: said L1, truth ['L2']
- pdf_olmocr_multicol_03: said L1, truth ['L2']
- pdf_olmx_07: said L3, truth ['L4']
- pdf_olmx_10: said L3, truth ['L1']
- pdf_olmx_11: said L1, truth ['L2']
- ocr_olmocr_oldscans_02: said L4, truth ['L3']
- ocr_olmocr_oldscans_04: said L3, truth ['L5']
- ocr_funsd_04: said L3, truth ['L4']
- ocr_gnhk_02: said L4, truth ['L5']
- garb_olmocr_arxivmath_01_cid: said L2, truth ['L3']

**jev_vector** (8 wrong)
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_pdb_labreport_en_digital: said L3, truth ['L4']
- pdf_olmx_02: said L2, truth ['L1']
- pdf_olmx_07: said L3, truth ['L4']
- pdf_olmx_10: said L3, truth ['L1']
- ocr_olmocr_oldscans_02: said L4, truth ['L3']
- ocr_olmocr_oldscans_04: said L3, truth ['L5']
- ocr_gnhk_02: said L4, truth ['L5']

**jev_vector_novision** (21 wrong)
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_pdb_labreport_en_clean: said L4, truth ['L3']
- img_olmocr_oldscans_02: said L4, truth ['L3']
- img_olmocr_oldscans_03: said L4, truth ['L5']
- img_olmocr_oldscans_04: said L4, truth ['L5']
- img_olmocr_oldscans_05: said L4, truth ['L5']
- img_olmocr_oldscans_06: said L4, truth ['L3']
- img_funsd_02: said L3, truth ['L4']
- img_funsd_04: said L3, truth ['L4']
- img_gnhk_01: said L4, truth ['L5']
- img_gnhk_02: said L4, truth ['L5']
- img_gnhk_03: said L4, truth ['L5']
- img_gnhk_04: said L4, truth ['L5']
- img_gnhk_05: said L4, truth ['L5']
- img_synth_screenshot_02: said L4, truth ['L3']
- pdf_olmx_02: said L2, truth ['L1']
- pdf_olmx_10: said L3, truth ['L1']
- ocr_olmocr_oldscans_02: said L4, truth ['L3']
- ocr_olmocr_oldscans_04: said L3, truth ['L5']
- ocr_funsd_04: said L3, truth ['L4']
- ocr_gnhk_02: said L4, truth ['L5']

**jevvec_claude-haiku-latest** (11 wrong)
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_pdb_bankrisk_digital: said L3, truth ['L4']
- img_pdb_labreport_en_digital: said L3, truth ['L4']
- img_olmocr_oldscans_02: said L4, truth ['L3']
- img_funsd_02: said L3, truth ['L4']
- pdf_olmocr_tables_01: said L4, truth ['L3']
- pdf_olmx_02: said L2, truth ['L1']
- pdf_olmx_07: said L3, truth ['L4']
- pdf_olmx_10: said L3, truth ['L1']
- ocr_olmocr_oldscans_02: said L4, truth ['L3']
- ocr_gnhk_02: said L4, truth ['L5']

**jevvec_claude-haiku-latest_skiptrusted** (12 wrong)
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_pdb_bankrisk_digital: said L3, truth ['L4']
- img_pdb_labreport_en_digital: said L3, truth ['L4']
- img_olmocr_oldscans_02: said L4, truth ['L3']
- img_funsd_02: said L3, truth ['L4']
- pdf_olmocr_tables_01: said L4, truth ['L3']
- pdf_olmx_02: said L2, truth ['L1']
- pdf_olmx_07: said L3, truth ['L4']
- pdf_olmx_10: said L3, truth ['L1']
- ocr_olmocr_oldscans_02: said L4, truth ['L3']
- ocr_olmocr_oldscans_04: said L3, truth ['L5']
- ocr_gnhk_02: said L4, truth ['L5']

**jevvec_gemini-3.5-flash-lite** (9 wrong)
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_pdb_labreport_zh_digital: said L5, truth ['L3', 'L4']
- img_pdb_labreport_en_digital: said L3, truth ['L4']
- img_synth_camera_02: said L3, truth ['L4']
- pdf_olmx_02: said L2, truth ['L1']
- pdf_olmx_10: said L3, truth ['L1']
- ocr_olmocr_oldscans_02: said L4, truth ['L3']
- ocr_olmocr_oldscans_04: said L3, truth ['L5']
- ocr_gnhk_02: said L4, truth ['L5']

**jevvec_gemini-3.5-flash-lite_skiptrusted** (6 wrong)
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_pdb_labreport_en_digital: said L3, truth ['L4']
- pdf_olmx_02: said L2, truth ['L1']
- pdf_olmx_10: said L3, truth ['L1']
- ocr_olmocr_oldscans_02: said L4, truth ['L3']
- ocr_gnhk_02: said L4, truth ['L5']

**jevvec_gemini-3.8-flash** (7 wrong)
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_pdb_labreport_en_digital: said L3, truth ['L4']
- pdf_olmx_02: said L2, truth ['L1']
- pdf_olmx_07: said L3, truth ['L4']
- pdf_olmx_10: said L3, truth ['L1']
- ocr_olmocr_oldscans_02: said L4, truth ['L3']
- ocr_gnhk_02: said L4, truth ['L5']

**jevvec_gemini-3.8-flash_skiptrusted** (8 wrong)
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_pdb_labreport_en_digital: said L3, truth ['L4']
- pdf_code_02: said L1, truth ['L2']
- pdf_olmx_02: said L2, truth ['L1']
- pdf_olmx_07: said L3, truth ['L4']
- pdf_olmx_10: said L3, truth ['L1']
- ocr_olmocr_oldscans_02: said L4, truth ['L3']
- ocr_gnhk_02: said L4, truth ['L5']

**jevvec_gpt-6-luna** (11 wrong)
- img_pdb_mathdense_real: said L3, truth ['L4']
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_pdb_gnnpaper_real: said L3, truth ['L4']
- img_pdb_jacs_real: said L3, truth ['L4']
- img_pdb_quantumthesis_real: said L3, truth ['L4']
- img_pdb_labreport_en_digital: said L3, truth ['L4']
- pdf_olmx_02: said L2, truth ['L1']
- pdf_olmx_07: said L3, truth ['L4']
- pdf_olmx_10: said L3, truth ['L1']
- ocr_olmocr_oldscans_02: said L4, truth ['L3']
- ocr_gnhk_02: said L4, truth ['L5']

**jevvec_gpt-6-luna_skiptrusted** (12 wrong)
- img_pdb_mathdense_real: said L3, truth ['L4']
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_pdb_gnnpaper_real: said L3, truth ['L4']
- img_pdb_jacs_real: said L3, truth ['L4']
- img_pdb_quantumthesis_real: said L3, truth ['L4']
- img_pdb_labreport_en_digital: said L3, truth ['L4']
- img_olmocr_oldscans_02: said L4, truth ['L3']
- pdf_olmx_02: said L2, truth ['L1']
- pdf_olmx_07: said L3, truth ['L4']
- pdf_olmx_10: said L3, truth ['L1']
- ocr_olmocr_oldscans_02: said L4, truth ['L3']
- ocr_gnhk_02: said L4, truth ['L5']

**llm_gemini-3.8-flash** (9 wrong)
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_funsd_01: said L3, truth ['L4']
- img_synth_code_01: said L4, truth ['L3']
- img_synth_rotated_01: said L4, truth ['L3']
- pdf_olmx_01: said L4, truth ['L2']
- pdf_olmx_10: said L3, truth ['L1']
- pdf_olmx_11: said L1, truth ['L2']
- ocr_olmocr_oldscans_02: said L4, truth ['L3']
- garb_olmx_03_mojibake: said L4, truth ['L3']

**llm_gemini-3.8-flash_c2** (13 wrong)
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_pdb_labreport_en_digital: said L3, truth ['L4']
- img_olmocr_oldscans_02: said L4, truth ['L3']
- img_funsd_01: said L3, truth ['L4']
- img_synth_code_01: said L4, truth ['L3']
- img_synth_code_02: said L4, truth ['L3']
- img_synth_screenshot_02: said L4, truth ['L3']
- img_synth_rotated_01: said L4, truth ['L3']
- pdf_olmx_01: said L4, truth ['L2']
- pdf_olmx_02: said L2, truth ['L1']
- pdf_olmx_10: said L3, truth ['L1']
- ocr_olmocr_oldscans_02: said L4, truth ['L3']
- garb_olmx_03_mojibake: said L4, truth ['L3']

**llm_gpt-6-luna** (11 wrong)
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_pdb_labreport_en_digital: said L3, truth ['L4']
- img_olmocr_oldscans_02: said L4, truth ['L3']
- img_funsd_01: said L3, truth ['L4']
- img_funsd_04: said L3, truth ['L4']
- img_synth_rotated_01: said L4, truth ['L3']
- pdf_olmocr_multicol_02: said L1, truth ['L2']
- pdf_olmx_01: said L4, truth ['L2']
- pdf_olmx_10: said L3, truth ['L1']
- pdf_olmx_11: said L1, truth ['L2']
- ocr_olmocr_oldscans_02: said L4, truth ['L3']

**llm_gpt-6-luna_c2** (7 wrong)
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_pdb_labreport_en_digital: said L3, truth ['L4']
- img_olmocr_oldscans_02: said L4, truth ['L3']
- img_funsd_01: said L3, truth ['L4']
- pdf_olmx_01: said L3, truth ['L2']
- pdf_olmx_02: said L2, truth ['L1']
- ocr_olmocr_oldscans_02: said L4, truth ['L3']

**rules** (35 wrong)
- img_pdb_mathdense_clean: said L5, truth ['L3']
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_pdb_bankrisk_clean: said L5, truth ['L3']
- img_pdb_bankrisk_digital: said L5, truth ['L4']
- img_pdb_bankrisk_real: said L5, truth ['L4']
- img_olmocr_oldscans_01: said L4, truth ['L5']
- img_olmocr_oldscans_02: said L4, truth ['L3']
- img_olmocr_oldscans_03: said L3, truth ['L5']
- img_olmocr_oldscans_04: said L3, truth ['L5']
- img_olmocr_oldscans_05: said L3, truth ['L5']
- img_funsd_01: said L3, truth ['L4']
- img_funsd_02: said L3, truth ['L4']
- img_funsd_04: said L3, truth ['L4']
- img_gnhk_01: said L4, truth ['L5']
- img_gnhk_02: said L4, truth ['L5']
- img_gnhk_03: said L4, truth ['L5']
- img_gnhk_04: said L4, truth ['L5']
- img_gnhk_05: said L4, truth ['L5']
- img_synth_fax_01: said L3, truth ['L4']
- img_synth_fax_02: said L3, truth ['L4']
- img_synth_screenshot_02: said L4, truth ['L3']
- pdf_olmocr_tables_03: said L1, truth ['L2']
- pdf_olmocr_multicol_02: said L1, truth ['L2']
- pdf_olmocr_multicol_03: said L1, truth ['L2']
- pdf_olmx_01: said L4, truth ['L2']
- pdf_olmx_04: said L4, truth ['L3']
- pdf_olmx_05: said L4, truth ['L3']
- pdf_olmx_06: said L4, truth ['L3']
- pdf_olmx_09: said L3, truth ['L1']
- pdf_olmx_11: said L1, truth ['L2']
- ocr_olmocr_oldscans_02: said L4, truth ['L3']
- ocr_olmocr_oldscans_04: said L3, truth ['L5']
- ocr_funsd_04: said L3, truth ['L4']
- ocr_synth_fax_02: said L3, truth ['L4']
- ocr_gnhk_02: said L4, truth ['L5']

**vision_only** (11 wrong)
- img_pdb_gnnpaper_digital: said L3, truth ['L4']
- img_pdb_bankrisk_digital: said L3, truth ['L4']
- img_pdb_labreport_en_digital: said L3, truth ['L4']
- img_funsd_01: said L3, truth ['L4']
- pdf_olmocr_tables_01: said L4, truth ['L3']
- pdf_olmocr_multicol_01: said L1, truth ['L2']
- pdf_olmocr_multicol_02: said L1, truth ['L2']
- pdf_olmocr_multicol_03: said L1, truth ['L2']
- pdf_olmx_01: said L3, truth ['L2']
- pdf_olmx_09: said L3, truth ['L1']
- pdf_olmx_11: said L1, truth ['L2']

