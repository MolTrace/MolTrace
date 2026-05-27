# NMRCheck

This is the canonical active baseline for NMRCheck.

Core surface area:

- authenticated registration, login, verification, and password reset
- rule-based `¹H NMR` validation and analysis against SMILES
- solvent-aware `¹H` evidence scoring and beta `¹³C NMR` validation
- review queue, audit logging, admin controls, and metrics
- processed spectrum preview and analysis for CSV / TSV / JDX / DX uploads
- raw Bruker and Varian/Agilent 1D FID beta preview, analysis, reports, and reviewer signoff
- guarded processed 2D NMR evidence support for COSY, HSQC/HMQC, and HMBC behind `ENABLE_2D_NMR`

## Administrator login

Admin users are controlled by **`ADMIN_EMAILS`** (comma-separated, case-insensitive). If the variable is **unset**, the backend falls back to the default list in `get_settings()` in `src/nmrcheck/settings.py` (which includes the project owner email). On **register**, **sign-up**, and **login**, any matching user receives `is_admin: true`; existing users are **promoted on the next successful login** if their email is in the list but `is_admin` was false.

For **production** (e.g. Render), set `ADMIN_EMAILS` explicitly so it is not overwritten by a template that lists only a placeholder address. See `.env.render.example`.

Canonical source of truth:

- `src/nmrcheck/settings.py`
- `src/nmrcheck/api.py`
- `src/nmrcheck/web.py`
- `src/nmrcheck/spectrum.py`
- `src/nmrcheck/fid.py`
- `src/nmrcheck/orm.py`
- `src/nmrcheck/models.py`

## Supported processed spectrum formats

- CSV / TSV peak tables
- CSV / TSV processed traces
- simple JCAMP-DX (JDX / DX) XY-style exports

## Supported raw FID beta formats

- Bruker 1D dataset `.zip`, `.tar.gz`, or `.tgz` archive with a folder containing `fid` and `acqus`
- Varian/Agilent 1D dataset `.zip`, `.tar.gz`, or `.tgz` archive with a folder, often ending in `.fid`, containing `fid` and `procpar`

Raw FID-derived evidence requires human reviewer signoff before final report use.

## Guarded 2D NMR Evidence Engine

Week 25 adds an additive, feature-flagged processed 2D evidence layer. Set
`ENABLE_2D_NMR=true` to expose `POST /nmr2d/preview`,
`POST /nmr2d/analyze`, `GET /nmr2d/runs/{run_id}`,
`GET /nmr2d/runs/{run_id}/report`, and the guarded UI section. The module
accepts processed COSY, HSQC/HMQC, and HMBC peak tables
(`.csv`, `.tsv`, `.json`), optionally carries lightweight contour preview
points from intensity-bearing tables, links correlations to current ¹H and
¹³C text context, and stores a separate `nmr2d_runs` record for review.
Local development defaults to `ENABLE_2D_NMR=true` and
`ENABLE_2D_CONTOUR_PREVIEW=true`; `ENABLE_RAW_2D_FID_BETA=false` keeps raw 2D
FID/SER processing disabled unless explicitly enabled for beta work. When
`ENABLE_2D_NMR=false`, protected 2D endpoints return a clear feature-flag error
and the UI hides the 2D navigation and section.

The 2D layer is intentionally separate from the stable ¹H, ¹³C, spectrum
viewer, raw FID vault, reports, and reviewer workflows. Regression tests pin
those existing outputs while the feature flag is enabled. Raw 2D FID/SER
production processing is not implemented in this guarded release.

## Immutable Raw FID Vault

Raw FID uploads are handled non-destructively. The original archive is hashed
with SHA-256, inspected for safe paths/files, stored in the local immutable raw
data vault by default (`RAW_VAULT_DIR`, default `raw_data_vault/`), and
recorded in the `raw_archives` table with vendor/acquisition metadata and
required-file status. Bruker metadata is read from `acqus`, optional `procs`,
and `pulseprogram`; Varian/Agilent metadata is read from `procpar`, without
editing vendor files. Processing outputs are stored as derivative metadata. The app does not overwrite
raw binary FID files or extracted FID/SER files. Vault limits and policy are
controlled with `RAW_ARCHIVE_MAX_BYTES`, `RAW_ARCHIVE_MAX_FILES`,
`RAW_ARCHIVE_ALLOWED_EXTENSIONS`, `RAW_ARCHIVE_IMMUTABLE`, and
`RAW_ARCHIVE_REQUIRE_HASH_VERIFICATION`. The stored archive SHA-256 is
recalculated before download, preview/process, and export; mismatches are
blocked and audited as `raw_fid.integrity_failure`. FID evidence packages are available at
`GET /fid/runs/{run_id}/package` and include `analysis.json`,
`processing_metadata.json`, `raw_upload_provenance.json`,
`raw_archive_export_manifest.json`, and the original archive when it is still
available in immutable storage.

Raw FID beta processing defaults to automatic phase correction followed by
Bernstein polynomial baseline correction, order 3. Phase and baseline correction
settings, p0/p1, phase score, Bernstein coefficients, baseline QA, warnings, and
whether each correction was applied are recorded in metadata for review.
Processed spectrum uploads are not baseline corrected by default; processed-file
baseline correction is optional and explicit.

FID processing runs link back to the immutable raw archive by database ID and
SHA-256. Run records store the processing recipe and derived spectrum metadata
separately from the raw archive, including phase, baseline, zero-fill,
apodization, digital-filter correction status, reference/solvent context,
peak-picking settings, warnings, and reviewer status.
The structured `FIDProcessingRecipe` defaults to auto phasing, Bernstein
baseline correction order 3, real display mode, vertical gain `1.0`, and
`debug_preview=false`. Reprocessing builds a new recipe against the verified
vault archive instead of editing or replacing the original FID package.

The explicit immutable-vault workflow is:

- `POST /raw-fid/upload` stores the original archive and returns its SHA-256 archive ID.
- `GET /raw-fid/{archive_id}` returns metadata and integrity status only.
- `GET /raw-fid/{archive_id}/download` verifies SHA-256 before serving original bytes.
- `POST /raw-fid/{archive_id}/preview` processes a temporary preview without creating a run unless requested.
- `POST /raw-fid/{archive_id}/process` creates a linked FID processing run and analysis.
- `GET /raw-fid/{archive_id}/runs` lists derived processing runs.
- `GET /raw-fid/{archive_id}/export` packages the verified original archive, recipe, derived peak CSV, evidence report, audit trail, and hash manifest.

The export manifest records hashes for the original archive and derived evidence
files so a reviewer can verify that the raw data were preserved and that
processing runs are separate derived artifacts.

Legacy `/fid/preview` and `/fid/process` remain available. `/fid/preview` is now
temporary preview-only and recommends the explicit raw-vault workflow;
`/fid/process` stores the upload in the vault before processing and records a
legacy warning in provenance.

## Core invariants

- empty SMILES must fail
- invalid SMILES must fail
- empty `¹H NMR` text must fail
- malformed `¹H NMR` text must fail
- structure and parsed `¹H NMR` text must agree before analysis is accepted
- unsupported processed spectrum formats must fail clearly
- reference-assisted matching must remain visible in preview/analyze
- spectrum viewer controls must not break the analysis flow
- display gain is y-axis only and must not alter evidence intensity data
- raw FID uploads are immutable vault records; processing stores derived metadata and hashes, never raw overwrites
- stale auth tokens must return the UI to the auth screen cleanly

## Workflow smoke coverage

The test suite now covers a direct route-level workflow that exercises:

1. register
2. login
3. validate
4. analyze
5. spectrum preview
6. reference-assisted spectrum analysis
7. job submission
8. approve / reject review actions
9. export endpoints
10. FID run review/report actions
11. E2E API smoke coverage for auth, validation, analysis, workspaces, health, and deployment diagnostics
12. raw FID Prompt sidecar reporting-only smoke status, with the visible legacy SpectraCheck pipeline unchanged
13. raw FID Prompt manual-promotion gates reported as CI artifacts without activating the Prompt 1/2 sidecar
14. raw FID Prompt provenance checksum artifacts for fixture identity, JSON/CSV report hashes, and archived FID hashes
15. raw FID Prompt manual-promotion design documented in `docs/raw_fid_prompt_manual_promotion_design.md`

## Week 20 Additions

Varian/Agilent 1D beta detection and nmrglue processing dispatch are now wired into the existing Raw FID flow. Deployment hardening now includes `GET /admin/deployment`, startup setting validation, Render install of optional FID dependencies, and the checklist in `docs/deployment_hardening.md`.

## Week 21 Release Candidate

Scientific validation fixtures, regression coverage, `GET /admin/release-health`, local SQLite reset via `python -m nmrcheck.cli reset-dev-db`, GitHub Actions CI, and evidence-confidence reporting are now included. The Raw FID run history is presented as one reviewer table with Open, Select, Report, Approve, and Reject actions. CI also runs `moltrace-raw-fid-sidecar-report --limit 1 --no-include-varian --quiet --smoke` to ensure the Prompt 1/2 raw-FID fixture report stays diagnostic-only and does not activate the sidecar path. A separate non-blocking manual-promotion gate job writes JSON/CSV artifacts for the Prompt 1/2 promotion gates while keeping the visible SpectraCheck raw-FID and processed-spectrum pipelines unchanged. CI also uploads a provenance checksum artifact with fixture archive hashes and report export hashes for audit trails.

## Week 22 Evidence Engine

The app now includes ¹H peak-level evidence scoring plus a ¹³C NMR beta layer. New endpoints include `POST /proton/evidence`, `POST /carbon13/validate`, `POST /carbon13/analyze`, `POST /carbon13/evidence`, `POST /carbon13/upload`, `POST /carbon13/spectrum/preview`, `POST /carbon13/spectrum/analyze`, `POST /carbon13/fid/preview`, and `POST /carbon13/fid/analyze`. The ¹³C path compares observed non-solvent carbon signals with the SMILES-derived carbon count, classifies carbon-shift regions, accepts optional DEPT/APT-like carbon types, and checks embedded ¹³C solvent/impurity-reference shifts.

Run the full regression suite with:

```bash
PYTHONPATH=src uv run pytest
```

## Week 26 Candidate Comparison Engine

Week 26 adds a candidate comparison layer for ranking multiple proposed
structures against the same evidence stack. It is additive and does not alter
the existing 1H, 13C, DEPT/APT, 2D NMR, raw FID, baseline, phase, or real
spectrum viewer behavior.

New module:

- `src/nmrcheck/candidate.py`

New endpoints:

- `POST /candidates/compare`
- `POST /candidates/compare/evidence`

New UI section:

- `Candidate Comparison Engine`

The section appears in the Analysis tab after the DEPT/APT + 2D NMR Evidence
Studio and before processed spectrum upload. It uses current 1H and 13C text as
read-only evidence and includes selected DEPT/APT and 2D files when present.

New tests:

- `tests/test_week26_candidate_comparison.py`
- `tests/test_week26_candidate_ui.py`

Candidate comparison is evidence ranking, not final structure confirmation. It
returns ranked candidates, best candidate, score breakdowns, evidence layers
used, contradictions, ambiguity alerts, and human-review notes.

## Week 27 Spectral Similarity Scoring

Week 27 adds spectral similarity scoring for comparing observed NMR spectra
against reference, prediction, literature, previous-run, or candidate-specific
spectra. It is additive and does not alter 1H/13C evidence, DEPT/APT, 2D NMR,
candidate comparison, raw FID processing, auto-phase, Bernstein baseline, or the
real spectrum viewer.

New module:

- `src/nmrcheck/spectral_similarity.py`

New endpoints:

- `POST /similarity/score`
- `POST /similarity/score/evidence`

New UI section:

- `Spectral Similarity Scoring`

The section appears in the Analysis tab after Candidate Comparison and before
processed spectrum upload. It uses current 1H and 13C text as read-only observed
spectra, provides separate reference text fields, and can include observed and
reference processed 2D peak tables.

New tests:

- `tests/test_week27_spectral_similarity.py`
- `tests/test_week27_spectral_similarity_api.py`
- `tests/test_week27_spectral_similarity_ui.py`

Spectral similarity is a confidence aid and ranking signal, not final structure
confirmation. Results expose vector scores, set-matching scores, matched peaks,
unmatched observed/reference peaks, warnings, and human-review notes.

## Week 28 Candidate-Specific Predicted NMR Matching + Mobile UI

Week 28 adds candidate-specific predicted NMR matching for comparing observed
1H, 13C, and optional HSQC/HMQC-style 2D evidence against approximate predicted
signals generated from each candidate SMILES. It also adds mobile-friendly
analysis workspace CSS.

New modules:

- `src/nmrcheck/nmr_prediction.py`
- `src/nmrcheck/candidate_predicted.py`

New endpoints:

- `POST /prediction/nmr/preview`
- `POST /prediction/nmr/match`
- `POST /prediction/nmr/match/evidence`

New UI section:

- `Candidate-specific Predicted NMR Matching`

The section appears in the Analysis tab after Spectral Similarity Scoring and
before processed spectrum upload. It uses current 1H and 13C text and selected
2D upload as read-only observed evidence.

New tests:

- `tests/test_week28_candidate_predicted_nmr.py`
- `tests/test_week28_prediction_api.py`
- `tests/test_week28_mobile_ui.py`

The bundled predictor is a transparent RDKit atom-environment heuristic for beta
review. Candidate-specific predicted matching is ranking evidence, not final
structure confirmation, and exposes predicted peaks, unmatched evidence,
ambiguity alerts, warnings, and human-review notes.

## Week 29 HRMS / Exact-Mass Constraint Layer

Week 29 adds the first mass-spectrometry constraint layer: HRMS exact-mass
candidate matching and bounded formula search. It is additive and does not alter
the existing NMR, FID, viewer, authentication, review, audit, or reporting
workflows.

New module:

- `src/nmrcheck/hrms.py`

New endpoints:

- `POST /ms/hrms/candidates/match`
- `POST /ms/hrms/candidates/match/evidence`
- `POST /ms/hrms/formulas/search`

New UI section:

- `HRMS / Exact-Mass Constraint Layer`

The section appears in the Analysis tab after Candidate-specific Predicted NMR
Matching and before processed spectrum upload. It supports observed m/z, adduct,
ion mode, ppm tolerance, optional M+1/M+2 isotope hints, candidate exact-mass
matching, and bounded CHNOPSClBr formula search.

New tests:

- `tests/test_week29_hrms_exact_mass.py`
- `tests/test_week29_hrms_api.py`
- `tests/test_week29_hrms_ui.py`

HRMS exact mass constrains formula and candidate plausibility but does not prove
connectivity or stereochemistry. It should be interpreted with NMR evidence and
human review.

## Week 30 Processed MS/MS Annotation Beta

Week 30 adds a processed tandem-MS evidence layer after HRMS. It accepts
processed centroid MS/MS peak lists and annotates precursor consistency, common
neutral losses, simple candidate fragment hypotheses, explained peak count, and
explained intensity fraction.

New module:

- `src/nmrcheck/msms.py`

New endpoints:

- `POST /ms/msms/annotate`
- `POST /ms/msms/annotate/evidence`

New UI section:

- `Processed MS/MS Annotation Beta`

The section appears in the Analysis tab after HRMS / Exact-Mass Constraint Layer
and before processed spectrum upload. It is intentionally limited to processed
peak tables and does not parse raw LC-MS/MS vendor files or search external
MS/MS libraries.

New tests:

- `tests/test_week30_msms_annotation.py`
- `tests/test_week30_msms_api.py`
- `tests/test_week30_msms_ui.py`

MS/MS fragments and neutral losses support or weaken candidate structures, but
do not prove complete connectivity or stereochemistry. Human review remains
required.

## Week 31 Adduct + Isotope Pattern Inference

Week 31 adds a processed MS1 / HRMS triage layer between HRMS exact-mass
matching and processed MS/MS annotation. It infers isotope clusters, charge
state, M+1/M+2 percentages, rough carbon count, halogen-style M+2 signatures,
paired adduct peaks, likely precursor adducts, and bounded formula candidates.

New module:

- `src/nmrcheck/adduct_inference.py`

New endpoints:

- `POST /ms/adducts/infer`
- `POST /ms/adducts/infer/evidence`

New UI section:

- `Adduct + Isotope Pattern Inference`

The section appears in the Analysis tab after HRMS / Exact-Mass Constraint Layer
and before Processed MS/MS Annotation Beta. It accepts processed centroid MS1
peak tables only. Use the Week 35 LC-MS/MS import bridge to extract peak-list
views from mzML/mzXML or source files.

New tests:

- `tests/test_week31_adduct_isotope.py`
- `tests/test_week31_adduct_api.py`
- `tests/test_week31_adduct_ui.py`

Adduct and isotope inference proposes precursor-ion hypotheses and isotope
signatures. It does not prove molecular identity and should be interpreted with
HRMS exact mass, MS/MS fragments, NMR evidence, and human review.

## Week 32 MS/MS Fragmentation-Tree Reasoning

Week 32 adds an interpretable processed MS/MS fragmentation-tree layer after the
Processed MS/MS Annotation Beta. It links precursor, fragment, and subfragment
peaks using diagnostic neutral-loss differences and candidate-specific
plausibility checks.

New module:

- `src/nmrcheck/fragmentation_tree.py`

New endpoints:

- `POST /ms/msms/fragmentation-tree`
- `POST /ms/msms/fragmentation-tree/evidence`

New UI section:

- `MS/MS Fragmentation-Tree + Diagnostic Neutral-Loss Reasoning`

The section appears in the Analysis tab after Processed MS/MS Annotation Beta
and before processed spectrum upload. It accepts processed centroid MS/MS peak
tables only. Use the Week 35 LC-MS/MS import bridge to extract peak-list views
from mzML/mzXML or source files; library search and generative
unknown-structure proposals remain out of scope.

New tests:

- `tests/test_week32_fragmentation_tree.py`
- `tests/test_week32_fragmentation_tree_api.py`
- `tests/test_week32_fragmentation_tree_ui.py`

Fragmentation-tree reasoning supports or weakens candidate structures by
explained peaks, explained intensity, diagnostic losses, tree depth, and
contradiction flags. It does not prove final connectivity or stereochemistry.

## Week 33 Unified Candidate Confidence Engine

Week 33 adds a unified decision-support layer after the fragmentation-tree
module. It combines candidate-specific predicted NMR, HRMS exact mass, MS1
adduct/isotope inference, processed MS/MS annotation, and MS/MS
fragmentation-tree reasoning into one transparent candidate confidence ranking.

New module:

- `src/nmrcheck/unified_confidence.py`

New endpoints:

- `POST /confidence/candidates/unified`
- `POST /confidence/candidates/unified/evidence`

New UI section:

- `Unified Candidate Confidence Engine`

The section appears in the Analysis tab after MS/MS Fragmentation-Tree +
Diagnostic Neutral-Loss Reasoning and before processed spectrum upload. It uses
current 1H/13C/NMR/MS evidence as read-only context and reports layer-level
agreement, missing layers, contradictions, and ambiguity alerts.

New tests:

- `tests/test_week33_unified_confidence.py`
- `tests/test_week33_unified_api.py`
- `tests/test_week33_unified_ui.py`

Unified confidence is decision support, not proof of identity and not a
calibrated DP4/DP5 probability. Human review remains required.

## Week 34 Regulatory-ready Structure Elucidation Report Composer

Week 34 adds a governance/report layer after unified confidence. It turns a
supplied unified confidence result, or a unified confidence request that the app
runs through the existing Week 33 engine, into an audit-ready structure
elucidation report.

New module:

- `src/nmrcheck/regulatory_report.py`

New endpoints:

- `POST /reports/structure-elucidation/compose`
- `POST /reports/structure-elucidation/compose/evidence`
- `POST /reports/structure-elucidation/compose/html`

New UI section:

- `Regulatory-ready Structure Elucidation Report Composer`

The section appears in the Analysis tab after Unified Candidate Confidence
Engine and before processed spectrum upload. It records report metadata,
provenance hashes, source files, processing history, candidate tables,
contradictions, missing evidence, and a human-review release gate.

New tests:

- `tests/test_week34_regulatory_report.py`
- `tests/test_week34_report_api.py`
- `tests/test_week34_report_ui.py`

The composer is an audit-ready decision record, not autonomous regulatory
approval. Final release requires human review and local quality-system
validation.

## Week 35 Raw LC-MS/MS mzML + Processed Peak Import Bridge

Week 35 adds a provenance-first import bridge for mzML, mzXML, and processed
LC-MS/MS peak tables. It does not parse proprietary vendor raw formats directly
or perform library/database search; it preserves source hashes and generates
downstream MS1/MS/MS peak-list views for the existing MS evidence layers.

New module:

- `src/nmrcheck/lcms_import.py`

New endpoints:

- `POST /ms/lcms/import/bridge`
- `POST /ms/lcms/import/bridge/evidence`
- `POST /ms/lcms/import/bridge/upload`

New UI section:

- `Raw LC-MS/MS mzML + Processed Peak Import Bridge`

The section appears in the Analysis tab after the Regulatory-ready Structure
Elucidation Report Composer and before processed spectrum upload. It can copy
extracted MS1 peaks to HRMS/adduct/unified workflows, copy selected MS/MS peaks
to annotation/fragmentation/unified workflows, and copy the raw/source SHA-256
into report provenance.

New tests:

- `tests/test_week35_lcms_import_bridge.py`
- `tests/test_week35_lcms_api.py`
- `tests/test_week35_lcms_ui.py`

The bridge is an import and provenance layer, not an identification engine.
Imported MS evidence remains complementary to NMR and requires human review.

## Week 36 LC-MS Feature Detection + EIC/XIC + Peak Purity

Week 36 adds a chromatographic evidence layer after the Week 35 import bridge.
It extracts EIC/XIC traces from MS1 scan series, detects target m/z features,
estimates local peak purity and coelution, and links nearby MS/MS scans by
precursor m/z and retention time.

New module:

- `src/nmrcheck/lcms_features.py`

New endpoints:

- `POST /ms/lcms/features/detect`
- `POST /ms/lcms/features/detect/evidence`
- `POST /ms/lcms/features/detect/upload`

New UI section:

- `LC-MS Feature Detection + EIC/XIC + Peak Purity`

The section appears in the Analysis tab after the Raw LC-MS/MS mzML + Processed
Peak Import Bridge and before processed spectrum upload. It can reuse the
import bridge source input, copy the best feature into HRMS/MS workflows, and
copy purity/provenance notes into the report composer.

New tests:

- `tests/test_week36_lcms_feature_detection.py`
- `tests/test_week36_lcms_feature_api.py`
- `tests/test_week36_lcms_feature_ui.py`

Peak purity is chromatographic evidence only. It can identify clean or
coeluting features, but molecular identity still requires orthogonal HRMS,
MS/MS, NMR evidence, provenance review, and human interpretation.

## Week 37 LC-MS Feature Grouping + Blank Subtraction + RT Alignment

Week 37 adds a feature-table QC layer after LC-MS feature detection. It groups
sample, blank, QC, and reference features by m/z plus aligned retention time,
applies conservative blank subtraction, flags blank/background-like groups, and
adds isotope/adduct/in-source-loss family hints for reviewer triage.

New module:

- `src/nmrcheck/lcms_grouping.py`

New endpoints:

- `POST /ms/lcms/features/group`
- `POST /ms/lcms/features/group/evidence`
- `POST /ms/lcms/features/group/upload`

New UI section:

- `LC-MS Feature Grouping + Blank Subtraction + RT Alignment`

The section appears in the Analysis tab after `LC-MS Feature Detection +
EIC/XIC + Peak Purity` and before processed spectrum upload. It can reuse the
latest LC-MS feature source, report run SHA-256 hashes, display RT shifts and
blank ratios, copy the best sample-enriched group into downstream MS workflows,
and copy feature-table QC provenance into the report composer.

New tests:

- `tests/test_week37_lcms_feature_grouping.py`
- `tests/test_week37_lcms_grouping_api.py`
- `tests/test_week37_lcms_grouping_ui.py`

Retention-time alignment is a transparent per-run shift correction, not full
chromatographic warping. Blank subtraction and feature-family annotations are
review aids and do not prove molecular identity.

## Week 38 LC-MS Isotope/Adduct Consensus + Feature-Family Confidence

Week 38 turns Week 37 feature-family hints into a transparent LC-MS consensus
evidence layer. It scores grouped LC-MS features using blank-subtraction gates,
peak-purity support, isotope-envelope agreement, adduct-pair consistency,
in-source-loss relationships, and MS/MS precursor linkage.

New module:

- `src/nmrcheck/lcms_consensus.py`

New endpoints:

- `POST /ms/lcms/features/consensus`
- `POST /ms/lcms/features/consensus/evidence`
- `POST /ms/lcms/features/consensus/upload`

New UI section:

- `LC-MS Isotope/Adduct Consensus + Feature-Family Confidence`

The section appears in the Analysis tab after `LC-MS Feature Grouping + Blank
Subtraction + RT Alignment` and before processed spectrum upload. A promoted
family is a stronger LC-MS evidence object for downstream candidate scoring,
not proof of molecular identity.

New tests:

- `tests/test_week38_lcms_feature_family_consensus.py`
- `tests/test_week38_lcms_consensus_api.py`
- `tests/test_week38_lcms_consensus_ui.py`

Codex handoff:

- `docs/codex_week38_lcms_feature_family_consensus_prompt.md`

This layer does not perform library search, retention-index prediction, or
generative unknown-compound proposal.

## Week 39 LC-MS Consensus to Unified Confidence Bridge

Week 39 connects promoted Week 38 LC-MS feature-family consensus to unified
candidate confidence and regulatory-ready reports.

New module:

- `src/nmrcheck/lcms_confidence_bridge.py`

New endpoints:

- `POST /confidence/candidates/lcms-consensus-bridge`
- `POST /confidence/candidates/unified/lcms-bridge`

Updated endpoints:

- `POST /confidence/candidates/unified`
- `POST /confidence/candidates/unified/evidence`
- `POST /reports/structure-elucidation/compose/evidence`

Updated UI:

- The Unified Candidate Confidence Engine now has an `LC-MS consensus bridge`
  block that can include the latest Week 38 family table.

New tests:

- `tests/test_week39_lcms_confidence_bridge.py`
- `tests/test_week39_lcms_bridge_api.py`
- `tests/test_week39_lcms_bridge_ui.py`

Codex handoff:

- `docs/codex_week39_lcms_consensus_unified_bridge_prompt.md`

This layer checks candidate theoretical adduct m/z against promoted LC-MS
feature-family anchors. It is an evidence bridge, not an identity engine.
Candidate rankings still require NMR, HRMS, MS/MS, contradiction review, and
human approval.

## Codex handoff

This package includes dedicated Codex verification prompts:

```text
docs/codex_week26_candidate_comparison_prompt.md
docs/codex_week27_spectral_similarity_prompt.md
docs/codex_week28_candidate_predicted_nmr_mobile_prompt.md
docs/codex_week29_hrms_exact_mass_prompt.md
docs/codex_week30_processed_msms_annotation_prompt.md
docs/codex_week31_adduct_isotope_prompt.md
docs/codex_week32_msms_fragmentation_tree_prompt.md
docs/codex_week33_unified_candidate_confidence_prompt.md
docs/codex_week34_regulatory_report_prompt.md
docs/codex_week35_lcms_import_bridge_prompt.md
docs/codex_week36_lcms_feature_detection_prompt.md
docs/codex_week37_lcms_feature_grouping_prompt.md
docs/codex_week38_lcms_feature_family_consensus_prompt.md
docs/codex_week39_lcms_consensus_unified_bridge_prompt.md
```

It also records the future-package handoff standard:

```text
docs/codex_future_package_standard.md
```

From this package onward, future modules should include a
`docs/codex_<package_or_week_name>_prompt.md` file, a README Codex handoff
section, a current-state guard, and clear separation of evidence, display,
heuristic inference, human review, and final claims.
