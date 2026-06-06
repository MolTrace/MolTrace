# Required standard for every future SpectraCheck package

Starting with Week 26 and every subsequent module/package, each package must include a Codex handoff document.

## Required file

Each package must include:

```text
docs/codex_<package_or_week_name>_prompt.md
```

Example:

```text
docs/codex_week27_spectral_similarity_prompt.md
```

## Required README section

Each package README update must include a short section titled:

```text
Codex handoff
```

It should point to the relevant Codex prompt file and summarize what Codex should verify.

## Required Codex prompt structure

Every Codex prompt must include:

1. package name
2. goal
3. explicit “do not alter stable behavior” list
4. files to inspect
5. endpoints to verify
6. UI placement/UX requirements, if applicable
7. tests to add or strengthen
8. focused test commands
9. full test command
10. compile command
11. grep/search commands
12. acceptance criteria
13. expected final response format

## Regression rule

Every future module must include a current-state guard. New features must be additive unless the user explicitly asks for a refactor.

Stable behavior to protect:
- real-spectrum viewer
- raw FID immutable/storage direction
- auto-phase and Bernstein baseline correction
- 1H evidence
- 13C evidence
- DEPT/APT
- 2D NMR
- candidate comparison
- authentication/admin behavior
- review/audit/report flows

## Scientific reporting rule

Every future module must clearly distinguish:
- evidence
- display
- heuristic inference
- human review
- final claim

SpectraCheck should not overclaim “confirmed” unless human review has approved the result.


## Deep research requirement

Every future SpectraCheck package must include a short research scan before implementation. The Codex prompt must ask Codex to:
- inspect the relevant attached/source literature;
- summarize implementation-relevant takeaways;
- explicitly distinguish what is implemented now from what remains a future ML/DFT/external-predictor integration;
- preserve citations or literature notes in package documentation when appropriate.

For NMR/MS modules, prioritize evidence from:
- NMR-Solver and spectral matching papers;
- NMR chemical-shift prediction literature;
- NMR-Challenge/Silverstein for practical interpretation;
- established NMR desktop software for workflow/UI expectations;
- Data Scientist's Handbook for regression, defensive programming, and modularity.


## MS layer sequencing rule

MS development should proceed in stable, auditable stages:
1. HRMS exact mass and formula constraints.
2. Processed MS/MS peak-table annotation.
3. Adduct and isotope pattern inference.
4. Fragmentation-tree and neutral-loss reasoning.
5. LC-MS/MS chromatographic and raw file support.
6. Generative unknown-compound hypotheses.

Each stage must preserve the NMR evidence stack and must include Codex handoff instructions, focused tests, full tests, and a clear statement that MS evidence is complementary rather than a replacement for NMR.


## Week 30 processed MS/MS validation note

The processed MS/MS beta is the second MS layer. Future MS packages must preserve this sequence:
- keep exact-mass HRMS constraints stable;
- keep processed peak-table MS/MS annotation stable;
- add adduct/isotope inference only after processed MS/MS is validated;
- add raw LC-MS/MS and chromatographic workflows only after the processed-table layer has strong tests.

Do not let raw-file support destabilize current NMR or HRMS evidence outputs.

## Week 31+ MS stability rule

When adding new MS modules, keep the sequence staged and auditable:

1. HRMS exact mass and formula constraints.
2. Processed MS/MS peak-table annotation.
3. MS1 adduct and isotope pattern inference.
4. Processed MS/MS fragmentation-tree and neutral-loss reasoning.
5. mzML and raw LC-MS/MS vendor-file ingestion.
6. Database search and library matching.
7. Generative unknown-compound hypotheses.

Every MS module must include Codex instructions, focused tests, UI placement tests, explicit scientific limitations, and regression guards showing that NMR/FID/HRMS/MSMS layers remain stable.


## Week 32 fragmentation-tree stability rule

New MS/MS reasoning layers must remain additive and must not change:
- NMR processing or visualization;
- raw FID immutability;
- HRMS exact-mass matching;
- MS1 adduct/isotope inference;
- processed MS/MS annotation beta.

Fragmentation-tree features must expose explicit nodes, edges, diagnostic hits, contradiction flags, and human-review notes. They must not claim final structure proof.


## Unified confidence layer rule

After individual evidence modules exist, new modules should report how their scores are used by the unified confidence engine. Unified confidence must preserve all child module API contracts, expose missing evidence and contradiction flags, and remain human-in-the-loop. Do not market unified scores as absolute proof or calibrated probabilities unless a validated calibration study exists.


## Report governance rule

Every future evidence-producing module should expose enough structured metadata for the report composer:
- evidence layer name
- score and confidence band
- agreement and contradiction counts
- missing evidence
- warnings and limitations
- source-file hashes when available
- processing history
- human-review status

No generated report should imply autonomous regulatory approval. The report layer must remain human-in-the-loop, auditable, and explicit about uncertainty.


## Week 35 LC-MS/MS import bridge rule

Raw LC-MS/MS support must be staged, conservative, and provenance-first:
- prefer open formats such as mzML/mzXML and processed peak tables before proprietary vendor parsing;
- compute SHA-256 hashes for source files/text;
- never overwrite raw files;
- expose scan summaries, TIC/base-peak summaries, precursor inventory, and downstream peak-list text;
- warn when binary compression, vendor formats, or metadata limitations prevent confident parsing;
- preserve HRMS, MS1 adduct/isotope, MS/MS, fragmentation-tree, unified confidence, report composer, NMR, and FID contracts.

Future raw-MS packages should add capabilities in this order: MS-Numpress decoding, robust chromatographic deconvolution, mzML/mzXML validation fixtures, open-format file storage, then carefully gated vendor-converter integrations.

## Week 36 LC-MS feature detection rule

LC-MS feature detection must remain conservative and provenance-first:
- feature detection operates on MS1 scans from open/processed sources;
- EIC/XIC extraction must expose the target m/z, tolerance, RT series, apex RT, area, width, and signal-to-noise estimate;
- peak purity must be reported as local chromatographic evidence, not identity proof;
- coeluting ions, weak features, missing MS1 data, and unsupported vendor files must create explicit warnings;
- MS/MS scan links must use precursor m/z and retention time checks;
- results must be copied into downstream evidence modules only through explicit user action;
- preserve raw-file hashes and never mutate raw source data.

Future chromatographic layers should add baseline-aware deconvolution, isotope/adduct grouping across RT, blank subtraction, RT alignment, and retention-index calibration in separate packages with regression tests.

## Week 37 LC-MS feature grouping rule

LC-MS feature grouping must remain a conservative multi-run QC layer:
- group features by m/z and aligned retention time only after Week 36 feature detection remains stable;
- treat retention-time alignment as a shift correction unless a validated warping model is added later;
- keep blank subtraction transparent with sample area, blank area, blank ratio, and blank-subtracted area;
- flag blank-like/background-like features rather than deleting them silently;
- annotate isotope/adduct/in-source-loss feature families as review hints, not identity proof;
- preserve run-level SHA-256 hashes and processing settings for the report composer;
- keep all downstream copying explicit and human-triggered.

Future LC-MS layers should add advanced deconvolution, isotope/adduct consensus scoring, multi-sample statistics, retention-index calibration, and library/database search as separate packages with regression tests.

## Week 38 LC-MS feature-family consensus rule

LC-MS feature-family consensus must remain a scoring and gating layer, not an identification layer:
- consume Week 37 grouped features, explicit groups, or grouped feature table text;
- score blank subtraction, peak purity, isotope envelope, adduct-pair, in-source-loss, and MS/MS linkage evidence separately;
- keep isotope expectations transparent and approximate unless a validated full isotope convolution engine is added later;
- treat adducts and in-source losses as supportive review evidence, not structural proof;
- fail or hold blank-like/background-like anchors for reviewer inspection;
- export promoted family tables for downstream candidate scoring, but do not silently inject them into final structure confidence;
- preserve all tolerances, formula assumptions, and evidence warnings for the report composer.

Future LC-MS packages should add advanced chromatographic deconvolution, multi-sample cohort statistics, retention-index calibration, ion mobility/CCS consensus, and library/database search as separate modules with focused tests.

## Week 39 LC-MS consensus bridge rule

LC-MS consensus-to-confidence bridging must remain a transparent evidence bridge:
- consume a full Week 38 consensus result, a Week 38 consensus request, or the exported family table text;
- compare candidate theoretical adduct m/z values to eligible feature-family anchors;
- require promoted, non-conflicting feature families by default;
- record candidate-level contradictions when a candidate does not match promoted LC-MS feature-family evidence;
- preserve consensus table/result hashes and bridge settings for the report composer;
- never treat LC-MS family consensus as molecular identity proof;
- never bypass human review or local quality-system validation.

Future LC-MS layers should add replicate/cohort reproducibility, QC-pool drift monitoring, retention-index calibration, ion mobility/CCS support, and library/database search as separate modules with focused tests.
