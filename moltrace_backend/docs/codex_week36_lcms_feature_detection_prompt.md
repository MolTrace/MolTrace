# Codex prompt: Week 36 LC-MS Feature Detection + EIC/XIC + Peak Purity

Paste this into Codex after applying `nmrcheck_week36_lcms_feature_detection_xic_peak_purity.zip`.

```text
You are working on the SpectraCheck / CheminSight repo.

I just applied:
nmrcheck_week36_lcms_feature_detection_xic_peak_purity.zip

Goal:
Verify, harden, and polish the LC-MS Feature Detection + EIC/XIC + Peak Purity layer.

Do not add proprietary vendor raw parsing yet.
Do not add MS-Numpress decoding yet unless it is a small, well-tested optional extension.
Do not add database/library search.
Do not add generative unknown-compound proposals.
Do not redesign the global UI.
Do not alter raw FID processing, spectrum visualization, NMR evidence, HRMS exact mass, MS1 adduct/isotope inference, processed MS/MS annotation, fragmentation-tree reasoning, unified confidence, or report composer contracts unless a bug is directly caused by this Week 36 feature layer.

Scientific/product rule:
LC-MS feature detection and peak purity are chromatographic evidence layers. They can support whether a target m/z is associated with a coherent chromatographic feature and whether the feature is locally clean, but they do not prove molecular formula, connectivity, stereochemistry, or identity. Human review is mandatory before using feature purity as candidate-confirmation evidence.

Literature/source takeaways to use:
- Established MS desktop software includes mass chromatograms, trace baseline correction, retention-time alignment, peak purity, chromatography export, MS tables, and live MS spectrum previews. Use these concepts as workflow inspiration, not as copied UI.
- MS/AI literature emphasizes raw-data access difficulty, metadata complexity, isolated pipelines, scalability, and the need for iterative extraction from raw MS data.
- Combined NMR/MS/MS workflows note that LC retention time can add selectivity but is condition-dependent; accurate mass, MS/MS, and NMR remain orthogonal evidence streams.
- Defensive programming sources emphasize modular programs, validation, unit checks, and reproducible reports.

Files to inspect:
- src/nmrcheck/lcms_features.py
- src/nmrcheck/lcms_import.py
- src/nmrcheck/models.py
- src/nmrcheck/api.py
- src/nmrcheck/web.py
- tests/test_week36_lcms_feature_detection.py
- tests/test_week36_lcms_feature_ui.py
- tests/test_week36_lcms_feature_api.py
- docs/week36_lcms_feature_detection_xic_peak_purity.md

Endpoints to verify:
- POST /ms/lcms/features/detect
- POST /ms/lcms/features/detect/evidence
- POST /ms/lcms/features/detect/upload

Required behavior:
1. Accept processed LC-MS peak tables with scan_id, ms_level, rt_min, mz, intensity, and precursor_mz columns.
2. Accept the same conservative mzML/mzXML sources used by the Week 35 bridge.
3. Extract EIC/XIC traces for user-specified target m/z values.
4. Auto-select target m/z values from intense MS1 clusters when no target values are supplied.
5. Detect chromatographic features using configurable height, smoothing, scan-count, m/z, and ppm tolerances.
6. Calculate apex RT, apex intensity, integrated area, width, and signal-to-noise estimate.
7. Estimate local peak purity using coeluting ion area in a retention-time window.
8. Report top coeluting ions with area, relative area, max intensity, and correlation to the target XIC when possible.
9. Link nearby MS/MS scans by precursor m/z and RT window.
10. Return clear warnings for coelution, weak features, unsupported vendor files, and missing MS1 scans.
11. UI section must be after Raw LC-MS/MS mzML + Processed Peak Import Bridge and before Processed spectrum upload.
12. Stable NMR/FID/HRMS/MS/MS layers must not be changed.

UI requirements:
- Section title: LC-MS Feature Detection + EIC/XIC + Peak Purity
- Fields:
  - optional LC-MS/MS file
  - filename / source label
  - source format
  - source text / peak table
  - target m/z values
  - m/z tolerance, Da
  - ppm tolerance
  - minimum relative feature height
  - minimum scans per feature
  - smoothing window
  - purity RT window
  - top coeluting ions
  - max features
- Buttons:
  - Detect features + XICs
  - Use import bridge input
  - Copy best feature
  - Copy purity to report
  - Clear features
- Display:
  - feature counts
  - clean/coeluting/weak summary
  - best feature
  - feature table
  - peak-purity details
  - warnings
  - recommended next actions

Add or strengthen tests:
1. Processed LC-MS table produces a clean feature with high peak purity.
2. Coeluting ion series flags possible_coelution or poor_peak_purity.
3. Auto-target selection recovers the dominant target from MS1 scans.
4. Unsupported vendor raw input returns a clear conversion requirement.
5. UI placement is correct.
6. Copy-to-MS-workflows and copy-to-report functions exist.
7. /ms/lcms/features/detect endpoint works after login.
8. Existing Week 35 import bridge tests still pass.
9. Existing Week 34/33/32/31/30/29 focused tests still pass.

Run focused tests:
PYTHONPATH=src uv run pytest -q \
  tests/test_week36_lcms_feature_detection.py \
  tests/test_week36_lcms_feature_ui.py \
  tests/test_week36_lcms_feature_api.py \
  tests/test_week35_lcms_import_bridge.py \
  tests/test_week35_lcms_ui.py \
  tests/test_week35_lcms_api.py \
  tests/test_week34_regulatory_report.py \
  tests/test_week34_report_ui.py \
  tests/test_week33_unified_confidence.py \
  tests/test_week33_unified_ui.py \
  tests/test_week32_fragmentation_tree.py \
  tests/test_week32_fragmentation_tree_ui.py \
  tests/test_week31_adduct_isotope.py \
  tests/test_week31_adduct_ui.py \
  tests/test_week30_msms_annotation.py \
  tests/test_week30_msms_ui.py \
  tests/test_week29_hrms_exact_mass.py \
  tests/test_week29_hrms_ui.py

Run full tests:
PYTHONPATH=src uv run pytest -q

Compile:
PYTHONPATH=src uv run python -m compileall src/nmrcheck

Search:
grep -R "lcms/features\|LC-MS Feature Detection\|EIC\|XIC\|peak purity\|coeluting" src/nmrcheck tests docs README.md || true

Acceptance criteria:
- Feature detection returns chromatographic features and XIC points.
- Peak-purity reports identify clean and coeluting features.
- MS/MS scans can be linked to features by precursor m/z and retention time.
- UI placement is correct and controls are visible.
- Stable NMR and MS evidence contracts are unchanged.
- Focused tests pass.
- Full tests pass or unrelated failures are documented.
- Final response includes literature takeaways and exact local commands.

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
