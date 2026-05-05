# Week 39 — LC-MS Consensus → Unified Candidate Confidence + Report Composer Bridge

## Purpose

Week 39 connects the Week 38 LC-MS feature-family consensus output to the unified candidate confidence engine and the regulatory-ready report composer.

The layer answers one narrow question:

> Does a candidate structure's theoretical adduct m/z agree with a promoted LC-MS feature-family anchor that has already passed the Week 38 consensus gate?

It does **not** perform structure identification, database search, retention-index prediction, or generative unknown-compound proposal.

## New module

- `src/nmrcheck/lcms_confidence_bridge.py`

## New models

- `LCMSCandidateFeatureFamilyMatch`
- `LCMSConsensusCandidateBridgeRequest`
- `LCMSConsensusCandidateBridgeResult`

## Updated models

`UnifiedCandidateConfidenceRequest` now accepts optional LC-MS consensus bridge fields:

- `lcms_consensus_result`
- `lcms_consensus_request`
- `lcms_family_table_text`
- `lcms_anchor_adduct`
- `lcms_mz_tolerance_da`
- `lcms_ppm_tolerance`
- `lcms_min_family_consensus_score`
- `lcms_require_promoted_family`
- `lcms_selected_family_id`
- `lcms_layer_weight`

`UnifiedEvidenceLayerName` now includes:

- `lcms_feature_family`

## New endpoints

- `POST /confidence/candidates/lcms-consensus-bridge`
- `POST /confidence/candidates/unified/lcms-bridge`

The existing unified confidence endpoints also accept LC-MS bridge evidence when the optional fields are supplied.

## Updated UI

The unified candidate confidence panel now includes an **LC-MS consensus bridge** block. When the latest Week 38 consensus result exists, the UI can include its exported `family_table_text` in unified candidate confidence and report-composer form submissions.

## Scoring behavior

The bridge:

1. Resolves a Week 38 consensus result from one of:
   - full `LCMSFeatureFamilyConsensusResult`
   - a full `LCMSFeatureFamilyConsensusRequest`
   - exported `family_table_text`
2. Filters feature families by:
   - `promoted_for_candidate_scoring` when required
   - non-conflicting family label
   - minimum consensus score
   - optional selected family ID
3. Computes each candidate's theoretical adduct m/z.
4. Compares the candidate m/z to eligible family anchor m/z values.
5. Adds one transparent unified-confidence layer per candidate.

## Candidate labels

- `matches_promoted_feature_family`
- `matches_review_feature_family`
- `no_mass_match_to_consensus_family`
- `no_eligible_consensus_family`
- `candidate_invalid`

## Report composer behavior

When the unified result includes LC-MS feature-family evidence, the report composer adds LC-MS bridge details to the evidence coverage section, including:

- bridge adduct assumption
- family counts
- eligible family counts
- promoted family counts
- LC-MS bridge result SHA-256
- top-candidate LC-MS layer score and evidence summary

## Guardrails

The bridge is intentionally conservative:

- a promoted LC-MS family is treated as an evidence object, not identity proof;
- m/z/adduct disagreement creates candidate-level contradictions;
- table-only consensus imports are marked as reduced provenance;
- original raw data and feature tables are never mutated;
- LC-MS support cannot bypass human review in the report composer.

## Focused tests

- `tests/test_week39_lcms_confidence_bridge.py`
- `tests/test_week39_lcms_bridge_ui.py`
- `tests/test_week39_lcms_bridge_api.py`

## Next layer

The next best layer after Week 39 is:

**Week 40: Multi-sample LC-MS Cohort Evidence + Replicate Reproducibility Dashboard**

That layer should score how reproducible promoted LC-MS feature families are across technical/biological replicates, batches, blanks, and QC pools before they influence discovery claims.
