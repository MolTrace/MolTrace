# Codex Week 30 Prompt: Processed MS/MS Annotation Beta

Goal: verify, harden, and polish the Processed MS/MS Annotation Beta.

Do not add raw LC-MS/MS vendor-file parsing, mzML import, database search against MassBank/GNPS/HMDB/MoNA/PubChem/vendor libraries, generative unknown-compound proposals, or global UI redesign. Do not modify stable NMR, HRMS, candidate comparison, spectral similarity, FID processing, raw spectrum viewer, auth, admin, reports, or review workflows unless directly related to MS/MS annotation.

Scientific rule: processed MS/MS is an orthogonal evidence layer. It can support or weaken candidate structures by precursor consistency, neutral losses, fragment-ion matches, and explained intensity, but it does not prove full connectivity or stereochemistry. It must be interpreted with NMR, HRMS exact mass, isotope evidence, predicted NMR matching, and human review.

Required endpoints:

```text
POST /ms/msms/annotate
POST /ms/msms/annotate/evidence
```

Focused verification:

```bash
PYTHONPATH=src uv run pytest -q \
  tests/test_week30_msms_annotation.py \
  tests/test_week30_msms_ui.py \
  tests/test_week30_msms_api.py \
  tests/test_week29_hrms_exact_mass.py \
  tests/test_week29_hrms_ui.py \
  tests/test_week29_hrms_api.py \
  tests/test_week28_candidate_predicted_nmr.py \
  tests/test_week28_mobile_ui.py \
  tests/test_week27_spectral_similarity.py \
  tests/test_week26_candidate_comparison.py \
  tests/test_week25_dept_apt.py \
  tests/test_week23_nmr2d.py \
  tests/test_week22_carbon13.py
```

Full verification:

```bash
PYTHONPATH=src uv run pytest -q
PYTHONPATH=src uv run python -m compileall src/nmrcheck
grep -R "ms/msms\|MS/MS\|neutral_loss\|fragment_match\|Processed MS/MS" src/nmrcheck tests docs README.md || true
```
