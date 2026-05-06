# Codex Prompt: Week 31 Adduct + Isotope Pattern Inference Layer

Goal: verify, harden, and polish the Adduct + Isotope Pattern Inference Layer.

Do not add raw LC-MS/MS vendor-file parsing, mzML parsing, full fragmentation trees, generative unknown-compound proposals, or global UI redesign. Do not alter stable NMR, HRMS, MS/MS, auth, admin, review, reporting, or real-spectrum viewer layers unless a bug is directly related to this MS1 layer.

Scientific rule: adduct and isotope inference is a triage layer. It proposes plausible precursor ion assignments, isotope clusters, charge states, halogen signatures, formula candidates, and paired adduct evidence. It does not prove molecular identity. Results must be interpreted with HRMS exact mass, MS/MS fragments, NMR evidence, and human review.

Endpoints:

```text
POST /ms/adducts/infer
POST /ms/adducts/infer/evidence
```

Focused verification:

```bash
PYTHONPATH=src uv run pytest -q \
  tests/test_week31_adduct_isotope.py \
  tests/test_week31_adduct_ui.py \
  tests/test_week31_adduct_api.py \
  tests/test_week30_msms_annotation.py \
  tests/test_week30_msms_ui.py \
  tests/test_week30_msms_api.py \
  tests/test_week29_hrms_exact_mass.py \
  tests/test_week29_hrms_ui.py \
  tests/test_week29_hrms_api.py \
  tests/test_week28_candidate_predicted_nmr.py \
  tests/test_week28_mobile_ui.py \
  tests/test_week27_spectral_similarity.py \
  tests/test_week26_candidate_comparison.py
```

Full verification:

```bash
PYTHONPATH=src uv run pytest -q
PYTHONPATH=src uv run python -m compileall src/nmrcheck
grep -R "adducts/infer\|Adduct + Isotope\|MS1Adduct\|isotope_clusters\|halogen_signature" src/nmrcheck tests docs README.md || true
```
