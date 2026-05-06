# Week 38 — LC-MS Isotope/Adduct Consensus + Feature-Family Confidence

## Purpose

Week 38 converts Week 37 LC-MS feature-family hints into an interpretable feature-family confidence layer.

The layer answers a narrower question than structure identification:

> Which LC-MS feature groups look like a coherent, sample-enriched feature family that is safe to pass into downstream candidate scoring after human review?

It does **not** identify unknown compounds, perform database search, perform generative structure proposal, or claim molecular identity.

## Why this layer follows Week 37

Week 37 produces grouped LC-MS features with blank subtraction, RT alignment, and simple isotope/adduct/in-source-loss relationships. Week 38 scores those relationships as a feature-family-level evidence object.

This makes the downstream confidence engine less vulnerable to treating a single m/z peak as decisive evidence. A good LC-MS family should usually show at least some combination of:

- low blank/background contribution
- acceptable peak purity
- plausible isotope satellite behavior
- plausible adduct-pair behavior when present
- plausible in-source-loss behavior when present
- MS/MS precursor linkage near the same RT

## New module

```text
src/nmrcheck/lcms_consensus.py
```

Main function:

```python
score_lcms_feature_family_consensus(request)
```

## New API endpoints

```text
POST /ms/lcms/features/consensus
POST /ms/lcms/features/consensus/evidence
POST /ms/lcms/features/consensus/upload
```

## Inputs

The structured endpoint accepts any of the following:

- a full `LCMSFeatureGroupingResult`
- a list of `LCMSFeatureGroup` records
- a Week 37 grouped feature table text export

Optional input:

- molecular formula for approximate isotope-envelope scoring
- expected anchor adduct, default `[M+H]+`
- anchor group ID
- m/z tolerance
- ppm tolerance
- family RT tolerance
- blank-ratio thresholds
- minimum promotion score

## Scored evidence layers

Each feature family reports layer scores for:

```text
blank_subtraction
peak_purity
isotope_envelope
adduct_consensus
in_source_loss
msms_linkage
```

Each layer includes:

- used / not used state
- normalized score
- status
- contradiction flag
- evidence summary
- warnings
- metadata

## Feature-family labels

Family-level labels:

```text
high_confidence_feature_family
moderate_confidence_feature_family
low_confidence_feature_family
conflicting_or_background_family
insufficient_family_evidence
```

Result-level labels:

```text
ready_for_candidate_scoring
review_conflicting_families
insufficient_consensus
invalid_input
```

## Promotion gate

A family can be promoted only when:

- the weighted consensus score meets the configured score gate
- no key contradiction gate is triggered
- the anchor is not blank-like/background-like
- isotope/adduct evidence, when used, does not strongly contradict the assumptions

The default promotion score gate is:

```text
0.62
```

Promotion means:

```text
suitable for downstream candidate scoring after human review
```

Promotion does **not** mean:

```text
molecular identity proven
```

## Approximate isotope scoring

When a formula is supplied, Week 38 uses the existing transparent formula-isotope approximation from the HRMS layer. This is intentionally a triage method, not a full isotope-convolution engine.

It compares detected M+1 and M+2 feature ratios against approximate formula expectations and reports missing or contradictory isotope satellites.

## Adduct and in-source-loss scoring

Adduct evidence uses same-RT mass differences such as:

```text
[M+Na]+ / [M+H]+: 21.981943 Da
[M+K]+ / [M+H]+: 37.955882 Da
[M+NH4]+ / [M+H]+: 17.026549 Da
```

In-source-loss evidence uses same-RT lower-mass relationships such as:

```text
H2O loss: 18.010565 Da
NH3 loss: 17.026549 Da
CO2 loss: 43.989829 Da
CO loss: 27.994915 Da
```

These are scored as supportive chromatographic evidence. They are not structural proof.

## UI placement

The new section appears in the Analysis tab:

```text
LC-MS Feature Detection + EIC/XIC + Peak Purity
↓
LC-MS Feature Grouping + Blank Subtraction + RT Alignment
↓
LC-MS Isotope/Adduct Consensus + Feature-Family Confidence
↓
Processed spectrum upload
```

## Files added or changed

Added:

```text
src/nmrcheck/lcms_consensus.py
tests/test_week38_lcms_feature_family_consensus.py
tests/test_week38_lcms_consensus_ui.py
tests/test_week38_lcms_consensus_api.py
docs/week38_lcms_feature_family_consensus.md
docs/codex_week38_lcms_feature_family_consensus_prompt.md
```

Updated:

```text
src/nmrcheck/models.py
src/nmrcheck/api.py
src/nmrcheck/web.py
src/nmrcheck/__init__.py
README.md
.env.render.example
pyproject.toml
```

## Local test commands

```bash
PYTHONPATH=src uv run pytest -q \
  tests/test_week38_lcms_feature_family_consensus.py \
  tests/test_week38_lcms_consensus_ui.py \
  tests/test_week38_lcms_consensus_api.py
```

Compile:

```bash
PYTHONPATH=src uv run python -m compileall src/nmrcheck
```

## Known limitations

Week 38 does not include:

- full isotope convolution
- nonlinear RT warping
- retention-index calibration
- library/database search
- generative unknown-compound proposal
- DIA deconvolution
- ion mobility / CCS consensus
- direct vendor raw-file parsing
- automatic unified-confidence weighting changes

Those should remain separate layers.
