# Codex Prompt: Week 33 Unified Candidate Confidence Engine

Goal: verify, harden, and polish the Week 33 Unified Candidate Confidence Engine.

Do not add new raw vendor parsing, mzML parsing, generative unknown structure proposals, or a replacement for existing NMR/MS modules. Do not globally redesign the UI or mutate raw FID, processed spectrum traces, or existing evidence inputs.

Scientific/product rule: unified confidence is a human-in-the-loop decision-support layer. It is not a final identity claim and not a calibrated DP4/DP5 probability. It must expose evidence agreement, disagreement, missing layers, contradictions, and reviewer priorities.

Endpoints to verify:

- `POST /confidence/candidates/unified`
- `POST /confidence/candidates/unified/evidence`

Required behavior:

1. Accept candidate structures plus optional 1H, 13C, 2D, HRMS, MS1, and MS/MS evidence.
2. Call existing evidence modules rather than reimplementing them.
3. Rank candidates by transparent weighted confidence.
4. Report layer-level scores for predicted NMR, HRMS exact mass, adduct/isotope inference, MS/MS annotation, and fragmentation tree.
5. Report missing layers, contradictions, and ambiguity when top candidates are close.
6. Do not crash on invalid SMILES.
7. Clearly state that the confidence score is decision support, not proof.
8. Existing NMR/MS layers still pass their tests.

UI requirements:

- Add `Unified Candidate Confidence Engine`.
- Place it after `MS/MS Fragmentation-Tree + Diagnostic Neutral-Loss Reasoning`.
- Place it before `Processed spectrum upload`.
- Include candidate list, observed 1H text, observed 13C text, HRMS observed m/z, HRMS/adduct, HRMS ppm tolerance, use inferred adduct, processed MS1 peak list, MS/MS precursor m/z, MS/MS ppm tolerance, and processed MS/MS peak list.
- Include `Build unified confidence`, `Copy current inputs`, and `Clear unified result`.
- Display best candidate, selected adduct, layers used, candidate count, ranked candidates, confidence score, confidence band, agreement count, contradiction count, missing layer count, and layer-level evidence details.

Focused tests:

```bash
PYTHONPATH=src uv run pytest -q \
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
  tests/test_week29_hrms_api.py \
  tests/test_week28_candidate_predicted_nmr.py \
  tests/test_week28_mobile_ui.py
```
