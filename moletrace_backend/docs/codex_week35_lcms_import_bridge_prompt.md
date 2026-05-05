# Codex prompt: Week 35 Raw LC-MS/MS mzML + Processed Peak Import Bridge

Paste this into Codex after applying `nmrcheck_week35_raw_lcms_msms_import_bridge.zip`.

```text
You are working on the SpectraCheck / CheminSight repo.

I just applied:
nmrcheck_week35_raw_lcms_msms_import_bridge.zip

Goal:
Verify, harden, and polish the Raw LC-MS/MS mzML + Processed Peak Import Bridge.

Do not add full proprietary vendor raw parsing.
Do not add database/library search.
Do not add generative unknown-compound proposals.
Do not alter NMR/FID/raw baseline/phase/spectrum viewer behavior.
Do not redesign the UI globally.
Do not change HRMS, MS1 adduct/isotope, MS/MS annotation, fragmentation-tree, unified confidence, or report-composer contracts unless a bug is directly related to LC-MS import bridging.

Scientific/product rule:
This layer is an import bridge, not a final identification engine. It must preserve raw/source provenance, generate downstream peak-list views, and clearly expose limitations. Imported MS evidence must remain complementary to NMR and human review.

Deep research requirement:
Use the attached/source literature and summarize implementation-relevant takeaways in your final response. Prioritize:
- MestreNova Manual: LC/GC/MS formats, TIC/MS browser, scan selection, peak detection, elemental composition, molecular match, MS tables, and provenance/raw-file handling.
- Silverstein: MS instrumentation, high-resolution exact mass, isotope evidence, molecular formula, DBE/IHD, tandem MS parent/daughter ion interpretation, and electrospray/adduct behavior.
- AI-powered MS/multiomics perspective: proprietary raw-data access difficulties, metadata complexity, open-format needs, and vendor-library constraints.
- Data Scientist's Handbook: README documentation, defensive programming, modular programs, data validation, unit checks, and reproducible reports.

Files to inspect:
- src/nmrcheck/lcms_import.py
- src/nmrcheck/models.py
- src/nmrcheck/api.py
- src/nmrcheck/web.py
- tests/test_week35_lcms_import_bridge.py
- tests/test_week35_lcms_ui.py
- tests/test_week35_lcms_api.py
- docs/week35_raw_lcms_msms_import_bridge.md

Endpoints to verify:
- POST /ms/lcms/import/bridge
- POST /ms/lcms/import/bridge/evidence
- POST /ms/lcms/import/bridge/upload

Required behavior:
1. Processed LC-MS/MS peak tables parse scan_id, ms_level, rt_min, mz, intensity, and precursor_mz.
2. mzML metadata is parsed and common uncompressed/zlib 32-bit or 64-bit binary m/z/intensity arrays decode correctly.
3. mzXML metadata is parsed and common interleaved peak arrays decode correctly.
4. Unsupported vendor formats return a warning and provenance response rather than crashing.
5. The bridge computes SHA-256 hashes from the original source bytes/text.
6. The bridge never mutates raw/source data.
7. Outputs include MS1 peak-list text for adduct/isotope inference.
8. Outputs include selected MS/MS peak-list text for processed MS/MS annotation and fragmentation-tree reasoning.
9. Outputs include precursor inventory and chromatogram/scan summaries.
10. UI appears after the report composer and before Processed spectrum upload.
11. Copy buttons populate HRMS, adduct/isotope, MS/MS, fragmentation-tree, unified-confidence, and report provenance fields.
12. Existing Week 29-34 tests remain stable.

Add or strengthen tests:
1. Processed peak table extracts MS1 and MS/MS peak lists.
2. mzML uncompressed binary arrays decode correctly.
3. mzXML interleaved peak pairs decode correctly.
4. Unsupported vendor source returns warning and immutable provenance.
5. API endpoint returns processed_peak_table result.
6. UI placement is correct.
7. Copy-to-MS-workflows and copy-hash-to-report functions exist.
8. Existing HRMS/MS1/MSMS/fragmentation/unified/report tests still pass.

Run focused tests:
PYTHONPATH=src uv run pytest -q \
  tests/test_week35_lcms_import_bridge.py \
  tests/test_week35_lcms_ui.py \
  tests/test_week35_lcms_api.py \
  tests/test_week34_regulatory_report.py \
  tests/test_week34_report_ui.py \
  tests/test_week34_report_api.py \
  tests/test_week33_unified_confidence.py \
  tests/test_week33_unified_ui.py \
  tests/test_week33_unified_api.py \
  tests/test_week32_fragmentation_tree.py \
  tests/test_week32_fragmentation_tree_ui.py \
  tests/test_week32_fragmentation_tree_api.py \
  tests/test_week31_adduct_isotope.py \
  tests/test_week31_adduct_ui.py \
  tests/test_week31_adduct_api.py \
  tests/test_week30_msms_annotation.py \
  tests/test_week30_msms_ui.py \
  tests/test_week30_msms_api.py \
  tests/test_week29_hrms_exact_mass.py \
  tests/test_week29_hrms_ui.py \
  tests/test_week29_hrms_api.py

Run full tests:
PYTHONPATH=src uv run pytest -q

Compile:
PYTHONPATH=src uv run python -m compileall src/nmrcheck

Search:
grep -R "lcms/import/bridge\|Raw LC-MS/MS\|LCMSImportBridge\|mzML\|mzXML" src/nmrcheck tests docs README.md || true

Acceptance criteria:
- Import bridge works for processed peak tables.
- Simple mzML and mzXML files are parsed.
- Raw/source SHA-256 is produced.
- Unsupported proprietary formats return clear warnings.
- UI placement is correct.
- Stable NMR/MS/report layers are unchanged.
- Focused tests pass.
- Full tests pass or unrelated failures are documented.

Return:
1. Files changed
2. Endpoints verified
3. UI changes verified
4. Tests added/updated
5. Literature takeaways used
6. Test results
7. Known limitations
8. Exact local commands I should run
```
