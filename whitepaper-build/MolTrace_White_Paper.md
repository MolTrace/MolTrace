# MolTrace

## AI-Native Scientific Intelligence for Pharmaceutical R&D

### Architecture, Evidence Engine, and the Audit-Ready Path from Raw Spectra to Regulatory-Ready Reports

---

**A MolTrace Technologies, Inc. White Paper**
Document version: 2026-Q2 · rev 2026-06-13 · Hybrid (business + technical) · Approx. 5,400 words

> *"Scientific intelligence has to be reproducible to be useful, auditable to be acceptable, and integrated to be adopted."*

---

## 1. Executive Summary

Small-molecule R&D in pharmaceutical, biotech, CRO, and academic settings rests on three intertwined activities: **identifying** what a sample is (spectroscopy and mass spectrometry), **understanding** how it was made (reaction optimisation), and **proving** it to a regulator (compliant documentation). These three activities are today fragmented across desktop tools, lab notebooks, vendor file formats, manual spreadsheets, and email-attached PDFs. Time-to-structure remains measured in days. Reproducibility is anecdotal. Regulatory submissions still consume months of evidence reconciliation.

MolTrace is an end-to-end, AI-native scientific intelligence platform that closes the loop between raw analytical data and audit-ready decisions. It is composed of three integrated programs sharing one evidence engine, one immutable raw-data vault, and one regulatory provenance layer:

- **SpectraCheck** — multi-layer NMR + MS evidence engine that ingests 1H, 13C, 2D NMR, raw FID (Bruker / Agilent-Varian), HRMS, MS/MS, and LC-MS feature data; categorises peaks against literature-backed chemical-shift windows; ranks candidate structures with DP4 / DP5-class methods; and surfaces every numerical claim with its provenance hash.
- **Regentry** — dossier scaffolding, ICH/FDA/EMA-aligned audit packs, controlled human-in-the-loop release gating, and AI-supported question/answer routing built on the 2025 FDA "Considerations for the Use of Artificial Intelligence to Support Regulatory Decision-Making" framework and the EMA AI reflection paper.
- **Reaction Optimization** — Bayesian optimisation, multi-objective response surface modelling, mechanistic-insight-guided design-of-experiments, and reaction-condition planning, integrated with the same SMILES candidates and the same evidence trail.

All three programs sit on top of a single **`/analyze` evidence stack** of forty production-graded layers (Weeks 22–40), an immutable raw FID vault with SHA-256 integrity verification, and a multi-tenant SaaS architecture (FastAPI + Postgres + Next.js + RDKit + nmrglue). The result: any number in a regulatory dossier — a chemical shift, a peak integration, a candidate score — traces back through the platform to a specific spectrum file, a specific processing recipe, a specific literature citation, and a specific human reviewer.

This paper presents the problem, the architectural response, the scientific foundations the platform is calibrated against, the regulatory posture, and a worked technical example.

---

## 2. The Problem Landscape

### 2.1 The Time-to-Structure Bottleneck

Routine structure elucidation in industry still consumes 6–48 hours per non-trivial small molecule, even with experienced analysts and modern NMR. A 2024 community survey of routine 1D NMR workflows found that 70 %+ of an analyst's time on a single sample is consumed by **peak picking, integration adjustment, candidate ranking, and assembling the result into a reviewable narrative** — not by acquisition itself.[^framework] The actual NMR experiment takes minutes; the cognitive overhead afterwards is the cost.

Recent ML methods promise relief. Multitask deep models trained on millions of predicted chemical shifts can now produce CSP5-scale predictors with accuracies competitive with DFT,[^csp5] graph neural networks accelerate stereochemistry confirmation via DP5 without DFT,[^dp5_nodft] and reasoning-capable LLMs are starting to assist with assignment narratives.[^reasoning_llms] But these advances are scattered across academic codebases, vendor plug-ins, and one-off scripts. They are not yet a single, deployable, audit-friendly platform that an R&D group or a CRO can use day-to-day.

### 2.2 The Reproducibility Crisis

Independent reproductions of published NMR-derived structures fail at rates of 10–30 % depending on compound class.[^prediction_chhaganlal] A non-trivial contributor is undocumented processing — phase correction by eye, baseline mode toggled without comment, integration regions adjusted post-hoc, peak lists exported to a spreadsheet and re-edited. The chain of custody from the FID off the spectrometer to the table in a regulatory submission is, in most laboratories, **invisible by default**. The MestReNova manual (the de facto industry standard NMR processing tool) describes a deeply manual workflow without persistent provenance,[^mnova_manual] and benchtop-NMR users routinely report rebuilding analyses from scratch when reviewers cannot reproduce specific integrations.[^benchtop_qm]

### 2.3 Tightening Regulatory Expectations

The FDA's January 2025 *Considerations for the Use of Artificial Intelligence to Support Regulatory Decision-Making for Drug and Biological Products* establishes a **risk-based credibility framework** for AI in regulatory submissions, with explicit requirements for traceability, model documentation, and human oversight.[^fda_ai_2025] The EMA's *Reflection paper on the use of Artificial Intelligence (AI) in the medicinal product lifecycle* similarly emphasises that any AI-derived evidence in submissions must be reproducible, version-controlled, and subordinate to expert review.[^ema_ai_reflection] ICH Q2(R2) *Validation of Analytical Procedures*, finalised in 2023, expands acceptance criteria for analytical method validation in a way that elevates the burden on data integrity throughout the analytical lifecycle.[^ich_q2r2]

A typical R&D group is therefore being asked to **simultaneously**: (a) adopt more AI, (b) prove the AI is reproducible, (c) document every parameter that drove an assignment, and (d) keep the human signed-off chain of decisions visible to inspectors. The status-quo toolchain — spreadsheets, ad-hoc desktop processing, email-attached PDFs — does not satisfy any of those four constraints.

### 2.4 The Vendor-Lock Problem

The dominant analytical software stacks (proprietary processing applications, vendor LIMS, hardware-tied data formats) raise switching costs and silo the data. The 2024 *AI in Mass Spectrometry Software Market* report estimates the AI-MS software segment growing at 18 % CAGR through 2032, with multi-modal integration cited as the single largest unmet need.[^ai_ms_market] An R&D group running Bruker NMR and Agilent LC-MS today operates two essentially disjoint analytical universes, each with its own audit conventions.

### 2.5 The Spectroscopy → Regulatory Disconnect

Even with a well-organised internal data lake, the *bridge* from a final spectrum interpretation to a regulatory-ready argument is hand-written. Reviewers spend weeks reconciling a structure-elucidation narrative against the raw evidence. There is no standard machine-readable handoff between "the analytical chemist's confidence in this candidate" and "the regulatory affairs officer's case for filing." Closing this gap — programmatically — is one of MolTrace's central design choices.

---

## 3. The MolTrace Vision

MolTrace is built on four design commitments that follow from the problems above:

**1 — Evidence-first.** Every claim shown in the UI is reachable, by hyperlink, to its underlying data: the source spectrum file, the picked peaks, the SMILES candidate, the literature citation that justifies the chemical-shift window, the multiplier table that adjusted the score for a "carbohydrates" sample, and the human reviewer who released the final report. There is no "confidence number with no audit trail" anywhere in the system.

**2 — Human-in-the-loop, never autonomous.** No regulatory document is released without an explicit human signoff. AI accelerates evidence assembly; humans make the call. This is consistent with both the FDA AI credibility framework (Stage 4 — human oversight gates) and the EMA reflection paper on AI in medicinal-product lifecycle.

**3 — Open science under the hood.** Where a community-maintained, peer-reviewed library exists, MolTrace uses it: **RDKit** for cheminformatics, **nmrglue** for vendor FID parsing, **mzML** for MS interoperability, **Pydantic** for typed API contracts, **FastAPI** for the routing layer, **Next.js / React** for the application UI. Proprietary algorithms are confined to the evidence-orchestration and confidence-aggregation layers, where the additive value lives.

**4 — Multi-modal by default.** A pharmaceutical R&D group operates across NMR + LC-MS + HRMS + MS/MS + reaction history simultaneously. MolTrace fuses these as one evidence stack — not as separate apps — and uses cross-modal contradictions (e.g. HRMS exact mass disagreeing with NMR-implied formula) as first-class warnings.

---

## 4. Technical Architecture

### 4.1 System Overview

The platform consists of a **FastAPI** backend (Python 3.13, ~24 000-line `api.py` plus ~60 domain modules under `nmrcheck/`) and a **Next.js 15** frontend (TypeScript, React 19, shadcn/ui, Plotly for spectra). State is persisted in **PostgreSQL** (SQLite in local dev), raw archives in an immutable file vault, and large-job orchestration in a background-job queue. The build-out follows a strictly additive weekly-release cadence (Weeks 20 → 40 to date) so every existing endpoint and regression test stays green as new evidence layers land.

```
   ┌──────────────────────────────────────────────────────────────────┐
   │                      Next.js Frontend (Vercel)                    │
   │  Marketing │ Dashboard │ SpectraCheck │ Regulatory │ Reactions   │
   └──────────┬────────────────────────────────┬─────────────────────┘
              │ /api/backend/*                  │
   ┌──────────▼────────────────────────────────▼─────────────────────┐
   │                    FastAPI Backend (Python)                       │
   │  Auth · Tenant · 40-layer Evidence Stack · Reports · Audit       │
   └──────────┬────────────────────────────────┬─────────────────────┘
              │                                   │
   ┌──────────▼────────────────┐    ┌────────────▼──────────────────┐
   │ Postgres (records)        │    │ Immutable Raw FID Vault       │
   │  · users · tenants        │    │  SHA-256 hashed archives      │
   │  · raw_archives · fid_run │    │  Read-only, never overwritten │
   │  · audit_events           │    │  Vault path policy enforced   │
   └───────────────────────────┘    └────────────────────────────────┘
```

### 4.2 The Evidence Engine

The defining feature of MolTrace is the **40-layer evidence engine** built incrementally as Weeks 22 through 40. Each layer is additive — never overwrites a prior layer — and every layer's output is a typed Pydantic model with stable JSON keys so downstream code (and regulators) can rely on the contract.

| Layer | Module | Function |
|---|---|---|
| 22 | `proton.py`, `carbon13.py` | 1H + 13C evidence scoring vs. SMILES; solvent-aware shift windows |
| 23 | `nmr2d.py`, `nmr2d_analyzer.py` | Guarded processed 2D NMR (COSY, HSQC/HMQC, HMBC) |
| 24 | `raw_vault.py`, `fid.py` | Immutable raw FID vault + Bruker / Agilent-Varian 1D processing |
| 25 | `nmr2d_routes.py` | 2D evidence engine guarded behind `ENABLE_2D_NMR` |
| 26 | `candidate.py` | Multi-candidate comparison with weighted layer scores |
| 27 | `spectral_similarity.py` | Observed-vs-reference spectral similarity scoring |
| 28 | `candidate_predicted.py`, `nmr_prediction.py` | Predicted-NMR matching from candidate SMILES |
| 29 | `hrms.py` | HRMS exact-mass candidate + bounded formula search |
| 30 | `msms.py` | Processed MS/MS annotation (precursor, neutral loss) |
| 31 | `adduct_inference.py` | MS1 adduct + isotope pattern inference |
| 32 | `fragmentation_tree.py` | MS/MS fragmentation-tree + diagnostic neutral losses |
| 33 | `unified_confidence.py` | Cross-modal candidate confidence aggregation |
| 34 | `regulatory_report.py` | Regulatory-ready structure elucidation report composer |
| 35 | `lcms_import.py` | mzML / mzXML / processed peak import bridge |
| 36 | `lcms_features.py` | LC-MS feature detection + EIC/XIC + peak purity |
| 37 | `lcms_grouping.py` | Feature grouping + blank subtraction + RT alignment |
| 38 | `lcms_consensus.py` | Isotope / adduct consensus + feature-family confidence |
| 39 | `lcms_confidence_bridge.py` | LC-MS consensus → unified candidate confidence |
| 40 | `multiplet_jcoupling_bridge.py`, `jcoupling_prediction.py` | Recovered multiplet J-couplings vs. predicted topological couplings → unified candidate confidence |

Critically, **every layer can run on its own** for diagnostic use, **and** is composable into the unified confidence engine when the user has the inputs. A laboratory that has only 1H NMR can use the platform productively today; the same laboratory adding LC-MS next quarter does not need to re-onboard. The same Pydantic models, the same audit pipeline, the same reviewer signoff workflow apply.

Alongside the default 40-layer chain, an **opt-in industry-standard Global Spectral Deconvolution (GSD) analysis backend** is available at the dedicated `POST /spectrum/analyze/gsd` endpoint. GSD performs single-pass peak detection with iterative pseudo-Voigt overlap resolution, classifies every peak into `compound | solvent | impurity | artifact | 13C_satellite` against the curated Fulmer / Gottlieb residual-solvent tables, and clusters multiplet lines into chemical-environment entries so the response can be consumed at either granularity. The GSD backend has cleared its strict production-promotion gate across three independent corpora: the curated NMRShiftDB2 19-fixture corpus (100 % solvent auto-detect, median compound-environment-count delta of 2 vs expert reference), an HMDB-style synthetic 20-fixture multiplet-line corpus (95 % / 100 % within tolerance), and a **real-instrument HMDB 100-fixture corpus** (95 % parseable, 93 % solvent auto-detect) that closes the literal Prompt 3 acceptance criterion of "100 spectra from NMRShiftDB2 + HMDB" on real instrument data. Tenants opt in per request via a frontend toggle; the default `/spectrum/analyze` flow is unchanged so existing pipelines stay green. See the technical white paper §3.1 for the algorithm, validation framework, and per-fixture results.

Building on the GSD-resolved peak list, a **multiplet-analysis backend** (`POST /spectrum/analyze/multiplets`) recovers the J-coupling structure behind each signal — identifying first-order and complex multiplets (singlet through septet, plus dd / dt / td / ddd) and reporting the underlying coupling constants in Hz, the way an expert spectroscopist reads a coupling tree by hand. It clears two literature-grade acceptance gates: all eight diagnostic quinine ¹H multiplets resolved with J values within 0.3 Hz of published reference, and a known hidden 11.4 Hz coupling benchmark recovered where standard peak picking misses it. A forward-modelled synthetic overlay (rendered in light red over the observed peaks) lets a reviewer visually confirm that the recovered coupling set actually explains the data — a regulatory-grade check rather than an opaque assignment. See the technical white paper §3.2 for the four-stage algorithm and acceptance evidence.

Those recovered couplings are not left as a standalone read-out: a **multiplet J-coupling agreement layer** (Layer 40, `multiplet_jcoupling_bridge.py`) feeds them into the unified confidence engine, scoring how well each candidate SMILES's *predicted* topological couplings — read from RDKit bond topology against empirical literature coupling magnitudes (no 3D geometry required by default, with an optional conformer-averaged Karplus refinement that makes sp³ vicinal couplings geometry-aware, so a conformationally locked ~10 Hz diaxial coupling is recognised as such) — agree with the observed J values, and flagging any candidate whose connectivity simply cannot produce a large observed coupling. Like every cross-modal layer it is opt-in (it contributes only when the request carries observed couplings) and is decision support, never an identity claim. See the technical white paper §3.3.

### 4.3 Immutable Raw FID Vault

Raw vendor data is the gold standard for analytical reproducibility, and MolTrace treats it accordingly. When a Bruker `.zip`, an Agilent `.tar.gz`, or a Varian `.fid` archive is uploaded, the platform:

1. **Hashes** the original bytes with SHA-256.
2. **Inspects** the archive for safe paths and required vendor files (`fid` + `acqus` for Bruker; `fid` + `procpar` for Agilent-Varian) without modifying them.
3. **Stores** the archive in the immutable raw vault directory (path policy: `RAW_VAULT_DIR`, size cap `RAW_ARCHIVE_MAX_BYTES`, file-count cap `RAW_ARCHIVE_MAX_FILES`).
4. **Records** the archive ID, hash, vendor, acquisition metadata, and required-file status in the `raw_archives` table.
5. Treats every subsequent processing run as a **derived artefact** with its own recipe hash, never overwriting the raw bytes.

Before download, preview, processing, or export, the stored SHA-256 is recalculated and compared. A mismatch is recorded as a `raw_fid.integrity_failure` audit event and blocks the operation. This satisfies the ALCOA+ data-integrity expectations the FDA references in 21 CFR Part 11 and that MHRA and PIC/S inspectors evaluate during GxP audits.

### 4.4 Peak Categorisation & Structure-Aware Priors

A 1H peak in the 4.4–6.0 ppm window can be an anomeric sugar proton, a vinyl proton, an acetal CH, or an unusual heteroatom-adjacent CH. Earlier in MolTrace's development the categoriser blindly labelled every such peak `"olefinic"`. For aminoglycoside antibiotics like tobramycin, which are fully saturated three-aminosugar structures with anomeric H at 5.1–5.5 ppm, this was wrong and misleading.

The current implementation routes the categorisation decision through the SMILES when one is supplied:

```
4.4–6.0 ppm 1H peak  +  structure has olefinic H, no anomeric H   → "olefinic"
                     +  structure has anomeric H, no olefinic H   → "anomeric"
                     +  structure has both                        → "anomeric_or_olefinic"
                     +  no SMILES                                 → "anomeric_or_olefinic"
```

The structural detection counts H on sp2 non-aromatic C=C carbons (olefinic) vs. H on sp3 carbons bonded to ≥ 2 oxygens by single bonds (anomeric/acetal). The decision rule is grounded in Silverstein *Spectrometric Identification of Organic Compounds* 8e Table 4.10,[^silverstein_2014] Pretsch *Structure Determination of Organic Compounds* 5e §H.3.2,[^pretsch_2020] and Friebolin *Basic One- and Two-Dimensional NMR Spectroscopy* 5e Ch. 2.[^friebolin_2010] Solvent / residual-water windows from Gottlieb (1997)[^gottlieb_1997] and Fulmer (2010)[^fulmer_2010] take precedence over the structure-aware branch — a peak at 4.80 ppm in D₂O is the HOD residual regardless of what the SMILES carries.

A parallel mechanism handles **labile-H reasoning**. Rather than always reporting the generic "(OH/NH/SH)" suffix, MolTrace counts the actual O-H, N-H, and S-H protons in the SMILES and surfaces only the subset present:

| Structure | Subset | Note |
|---|---|---|
| Ethanol (`CCO`) | (OH) | "Structure declares 1 labile H atom(s) (OH): 1 OH." |
| Aniline (`Nc1ccccc1`) | (NH) | "Structure declares 2 labile H atom(s) (NH): 2 NH." |
| L-Cysteine (`SC[C@@H](N)C(=O)O`) | (OH/NH/SH) | "1 OH, 2 NH, 1 SH" |

### 4.5 Compound-Class Priors for Candidate Scoring

The candidate-comparison layer's default evidence weights (`proton: 0.36, carbon13: 0.34, nmr2d: 0.14, structure: 0.08, dept_apt: 0.08`) are tuned for "typical small molecule" NMR. They are wrong for proteins, broad for polymers, and over-confident for unknown scaffolds. MolTrace exposes a `compound_class` parameter on every analyze request that selects a **transparent multiplier table** keyed by structural class (carbohydrates, lipids, proteins, peptides, glycoproteins, steroids, macrocycles, polymers, etc.) and re-normalises the weights so the total stays in [0, 1].

Examples grounded in NMR literature:

- **Carbohydrates** — Anomeric 1H + 13C are uniquely diagnostic and HSQC is near-mandatory.[^duus_carbo] Multipliers: `proton ×1.20, carbon13 ×1.30, nmr2d ×1.50, structure ×0.80`.
- **Proteins** — Severe 1H amide overlap; 2D + isotope-edited NMR are required for assignment.[^cavanagh_protein_nmr] Multipliers: `proton ×0.50, carbon13 ×1.20, nmr2d ×2.00, structure ×0.85`.
- **Polymers** — Broad-line ensemble averaging weakens peak-comparison evidence; molecular-formula validity becomes more informative.[^bovey_polymer] Multipliers: `proton ×0.45, carbon13 ×0.55, dept_apt ×0.60, nmr2d ×0.75, structure ×1.30`.

Every applied prior is echoed back in the analyze response under `candidate_comparison.compound_class_prior_applied` with original weights, multipliers, renormalised weights, and human-readable notes — so the multiplier table is auditable end-to-end. Multipliers are intentionally bounded in the 0.45×–2.0× range so a mis-selected class cannot swamp the score, and the table file (`compound_class_priors.py`) carries its chemistry rationale inline for inspector review.

### 4.6 The Unified Confidence Engine

The unified confidence engine (Week 33) is the platform's final decision-support layer. It accepts whatever subset of evidence the laboratory has — predicted NMR matching, HRMS exact mass, MS1 adduct/isotope inference, processed MS/MS annotation, fragmentation-tree reasoning, LC-MS consensus (via the Week 39 bridge), and multiplet J-coupling agreement against each candidate's predicted topological couplings (via the Week 40 bridge) — and produces:

- A **ranked candidate list** with normalised confidence scores
- A **layer-by-layer agreement matrix** showing which evidence layers support which candidate
- **Contradictions** (e.g. HRMS-implied formula disagrees with NMR proton inventory)
- **Missing layers** (e.g. "no MS/MS supplied; structure isomer discrimination weakened")
- **Ambiguity alerts** when the top two candidates are within 0.05 score units

The deterministic contradiction check above is complemented by a **learned contradiction-detection model** trained on reviewer-adjudicated cases: it flags internal spectral inconsistencies (integration / multiplicity / shift combinations no single structure explains) and cross-modal disagreement (NMR vs. MS vs. retention time) that a fixed rule set alone might miss. It *complements, never replaces,* the deterministic verifier — every flag is surfaced to the reviewer, and the hardest cases are routed into the active-learning queue that feeds the next fine-tuning round (§4.8).

Crucially, the engine never asserts identity. The wording in the response is *"decision support, not proof of identity and not a calibrated DP4/DP5 probability."* The DP4 / DP5 mathematics from Smith & Goodman (2010),[^smith_goodman_2010] Howarth & Goodman (2020),[^howarth_2020_dp4ai] and Howarth & Goodman (2022)[^howarth_2022_dp5] are exposed as their own panel for laboratories that want the calibrated Bayesian-posterior view.

### 4.7 Reports, Provenance, and Reviewer Workflow

The Week 34 regulatory-report composer is the gate between analytical evidence and a regulatory deliverable. It accepts a unified-confidence result and produces a structured report with:

- Report metadata + report version + composing user
- Provenance hashes (raw archive SHA-256, processing recipe hash, source file hashes)
- Source-file inventory + processing history
- Candidate ranking table with per-layer breakdowns
- Contradictions + missing-evidence callouts
- Cited references (every chemical-shift window or scoring method is cross-linked to its literature key from `literature_data.py`)
- A **human-review release gate** — the report cannot be marked "released" without an explicit signoff event in `audit_events`

The composer emits structured JSON (machine-readable), an HTML render (human-readable), and an export package (the original raw archive + the recipe + the derived peak table + the report + the hash manifest), so a reviewer or inspector can verify end-to-end that the report's claims are reachable from the raw bytes.

### 4.8 Reproducibility, Dataset Versioning, and the Evaluation Foundation

Beneath the per-analysis chain of custody sits a foundation that makes *the platform itself* reproducible as it evolves:

- **Versioned output contract.** Every SpectraCheck analysis serialises to a schema-versioned contract whose canonical-JSON **content hash** (`sha256:…`) is the analysis's stable identity — the same fingerprint the Regentry handoff and the ICH report stub (§6.1) embed for traceability.
- **Content-addressed dataset versioning.** Training and benchmark datasets are pinned and restored **by content hash** (with an optional DVC + S3 backend), so a result is tied to the exact bytes it was computed from — and no data blob is ever committed to git.
- **Experiment & run tracking.** Each model or benchmark run records its parameters, metrics, artifacts, dataset-version tag, git commit SHA, and — for AI-assisted layers — the registry model-weight checksum (a native run store always on, MLflow optional), linking every metric back to the §6.6 audit trail.
- **Fail-loud data validation.** Every ingested spectrum and inference input passes a validation gate (schema, recognised nucleus, physically-plausible field, no NaN/Inf, in-range ppm) before entering the pipeline; the same logical suite runs through Great Expectations when that optional backend is installed.
- **Single source of truth for "better."** One evaluation framework (RMSE, peak / classification F1, Top-k accuracy, BedROC, expected calibration error) decides whether a model change is an improvement, so promotion is a measured decision rather than a judgement call (§5.6).
- **End-to-end determinism gate.** A continuous-integration test runs one real Bruker FID through the full pipeline ten times and requires **byte-identical** structured output each time; identical inputs therefore yield an identical content hash — the machine-checkable substance behind the platform's reproducibility claim.
- **Versioned model registry + routed inference.** An append-only registry tracks every artifact that can produce a prediction — NMRNet checkpoints, HOSE-code knowledge-base builds, fine-tuned adapters, embedding models — with its semantic version, SHA-256, training-data lineage, and metric snapshot; an inference router composes the fine-tuned, pretrained, and deterministic-fallback layers and stamps every prediction with the exact set of model ids + checksums that produced it (fed verbatim into the §6.6 audit trail). A result is reproducible bit-for-bit from the registry + lineage, and a reviewer sees *which* model produced each number and *why* one layer was chosen over another.
- **Licence-clean public-datasets corpus + frozen holdout.** The canonical public datasets (NMRShiftDB2, HMDB, BMRB, MassBank, GNPS, QM9-NMR, 2DNMRGym, …) are ingested into a deduplicated, version-pinned, licence-tagged corpus with frozen, seeded train/val/test splits. The **test** split is a sacred, checksummed holdout that is hash-excluded from every training snapshot, and synthetic (DFT-computed QM9) data is labelled and never mixed into the experimental ground truth; licences are enforced (share-alike honoured, non-redistributable sources never copied in). A never-touched holdout on a licence-clean, deduplicated corpus is what makes a model claim an honest baseline rather than a number that leaked from its own training set.
- **Domain fine-tuning with mandatory lineage.** Once enough reviewer-validated in-house spectra have accumulated, MolTrace trains a domain **LoRA adapter** on top of the pretrained shift predictor (the base is frozen; only the small adapter trains) on Modal, logging the actual GPU-hours and cost. The adapter's hyperparameters — rank, scaling, dropout, learning rate, and epochs — are not hand-tuned but chosen by a **budgeted Bayesian search** (Optuna, on the order of ten trials rather than an exhaustive sweep); every trial is itself K-fold cross-validated and logged to the run tracker, and the search study is recorded by content hash so the winning recipe is reproducible. Every adapter starts from an **immutable, content-addressed training snapshot** whose hash is recorded as the adapter's data lineage, so the exact data behind any adapter is recoverable by hash. Two custody rules are enforced in code, not merely promised: the **never-trained holdout is hash-excluded from the snapshot** (and registration is refused if the gold-set checksum drifts), and **no adapter is registered without its snapshot hash, per-fold metrics, and code git SHA**. The adapter is validated by **leak-proof K-fold cross-validation** (GAMP 5 Appendix D11) — per-fold and aggregate ¹H/¹³C accuracy, calibration, and coverage, with the folds **grouped by molecule so a compound's repeat spectra never straddle the train/eval boundary** (the cross-batch leakage that otherwise lets cross-validation report a flatteringly optimistic score) — and is then subject to the same promotion gate below: registered as a candidate, advanced to a shadow only if it does not regress, and **never auto-promoted to production** without human sign-off. A **confidence-calibration head** (temperature / Platt scaling) is fitted on top of the trained adapter so its stated confidence tracks its empirical accuracy, and is validated by expected calibration error on the frozen holdout before the adapter is allowed near the promotion gate.
- **Dominance-based model promotion.** A model version is promoted only when its *full* ten-metric vector — top-1/top-3 accuracy, 1H/13C shift MAE, calibration (ECE), false-confirmation rate, retrieval recall, uncertainty quality, robustness, reviewer agreement, and latency — **dominates** the incumbent on the frozen gold set: no regression beyond tolerance on any metric, a strict improvement on at least one, and **zero regression** on the safety-critical metrics (passing a wrong structure; mis-calibrated confidence). The gold set's SHA-256 is pinned, so the run aborts if the holdout drifts. **Calibration is a hard precondition, not a tie-breaker:** a candidate whose expected calibration error exceeds the configured ceiling is held back even when it strictly dominates the incumbent on accuracy — a model that is more accurate but lies about its own confidence is not promotable. One improved number is never enough — this is the objective, reproducible, per-version acceptance evidence GxP validation expects, enforced as a CI gate so no model reaches production without it.
- **Closed-loop feedback capture — the compounding data moat.** Every AI-generated output a reviewer sees — a predicted shift, a proposed structure, a peak label, a purity call — carries a one-click *"Was this correct?"* control: thumbs up/down, an optional free-text correction, and a structured reason taxonomy (wrong-shift, wrong-multiplicity, wrong-structure, missed-impurity, wrong-integration, calibration-off). Each click becomes an **immutable, content-addressed feedback event** stamped with the exact set of `model_versions` that produced the output — the same registry ids + checksums recorded in the §6.6 audit trail — so every correction is attributable to the model that earned it. Corrections fan out automatically into the labelled-example store that seeds the next fine-tuning snapshot; bare thumbs-down overrides enter the active-learning queue where the model is weakest; and usage / override analytics roll up exactly where reviewers most often disagree. That queue is then ordered by **disagreement sampling** — each unlabelled spectrum scored by how much the pretrained, fine-tuned, and retrieval-augmented models *disagree* on it (the vote split on the top structure, the spread of predicted shifts, the spread of confidences), de-duplicated against near-identical spectra, and cut to a labelling budget — so scarce expert time lands on the few cases that will teach the model the most rather than a random sample. Retraining fires on a monthly schedule or once enough new labels accumulate, and the loop reports its own **yield**: labelled examples per month, the accuracy lift per retrain, and the **override-rate trend** — which should *fall* as the model improves, a direct and auditable signal that the product is getting better. The reviewer's judgement, captured once at the point of work, becomes a durable asset a competitor without the same install base cannot replicate.
- **Advisory reward model — never an override.** Those corrections and accept/reject signals assemble into an RLHF-style preference dataset (chosen ≻ rejected pairs), and a deterministic Bradley-Terry **reward model** learns to score candidate outputs by their likely reviewer acceptance. It re-ranks the reasoner's candidate structures and steers the annotation queue toward the cases most likely to be wrong — but it is **strictly advisory**: it can only reorder *within* a verdict class, never lift a candidate the deterministic verifier rejected above one it accepted. The science still arbitrates; the reward model only decides what a human looks at first.
- **Champion vs. challenger A/B rollout with instant rollback.** When the registry registers a challenger model, MolTrace can route a controlled fraction of live traffic to it — or run it in pure **shadow**, scoring every case in parallel without ever showing the reviewer its answer. Champion and challenger are compared on the same ten-metric gold vector plus live reviewer-acceptance and override rates. The challenger replaces the champion **only** on full dominance with **zero safety-metric regression**, and only after the fail-closed CI gate passes *and* a human signs off — the system **never auto-deploys**. A single call performs an **instant rollback**: a routing-layer kill that drops challenger traffic to zero while leaving the proven champion in production untouched, so a regression is contained in seconds rather than across a redeploy cycle.
- **Production monitoring + a fail-closed deployment gate.** Past the promotion gate, MolTrace *watches the model in production* and controls what reaches it. Continuous **drift monitors** track input drift (a population-stability index of the live nucleus / field / solvent / molecular-weight distribution against the training snapshot — a spike flags new chemistry the model has never seen), confidence drift (the trend of per-prediction uncertainty and retrieval-grounding scores), the reviewer **override-rate trend** (a rise means the model is degrading on live data), and latency against an SLO — emitting every metric to the observability stack and paging on a breach. A **lineage dashboard** reads the model registry to show, per production model, its version, training-snapshot hash, gold-set metric vector, promotion record, and current live drift status. And a model or pipeline change reaches production **only if all four release checks pass** — the dominance gate (no safety-metric regression), the audit-chain verification (provenance intact), a green test suite, and a data-leakage check (the candidate never trained on the gold set) — wired into CI so the release **fails closed**, blocking the deploy on any failure. Most early tools bolt monitoring on later; building drift detection, lineage, and fail-closed release gates in from the start is what lets MolTrace operate in regulated environments.

---

## 5. Scientific Foundations

MolTrace's evidence layers are not novel science; they are *integrated* science. Each layer maps to an established method from the cheminformatics, NMR, and MS literature. This section traces those mappings so reviewers can audit the platform's scientific posture.

### 5.1 Chemical-Shift Prediction

The Week 28 predicted-NMR layer accepts pluggable shift predictors. The bundled predictor is a transparent RDKit atom-environment heuristic — intentionally limited, intentionally interpretable. The platform is engineered to also call out to:

- **CSP5** (Williams et al., 2024) — a large-scale neural chemical-shift predictor with reported accuracy competitive with DFT at a fraction of the compute.[^csp5]
- **PROSPRE / ML 1H shift prediction** (Han et al., 2024) — recent metabolomics-tuned ML predictor for 1H shifts.[^han_prospre]
- **Neural message-passing for NMR chemical shift** (Kwon et al., 2020) — the canonical graph-NN approach.[^kwon_mpnn]
- **Park / molecular search by NMR matching** (Park et al., 2021) — molecule-from-spectrum retrieval at scale.[^park_2021]

A 2024 systematic comparison of NMR predictors (*Magnetic Resonance in Chemistry*) reports per-predictor RMSE bands and the situations where each excels.[^prediction_chhaganlal] MolTrace embeds these RMSE bands as default tolerance windows in the predicted-vs-observed alignment.

### 5.2 Candidate Scoring & Stereochemistry

The DP4 family of methods (Smith & Goodman 2010,[^smith_goodman_2010] Howarth & Goodman DP4-AI 2020,[^howarth_2020_dp4ai] DP5 2022[^howarth_2022_dp5]) provides Bayesian posteriors over candidate stereochemistry conditioned on observed shifts. The Week 26 candidate-comparison layer uses a transparent heuristic for fast iterative review; the DP4 panel runs in parallel when the user supplies ≥ 2 candidates and observed shifts. The 2024 *DP5 without DFT* paper by Howarth (graph-NN uncertainty calibrated) is referenced in the platform's compute-light DP5 pathway.[^dp5_nodft] The same DP4 posterior is reused as the NMR ranking signal in the orthogonal NMR + MS/MS + retention-time candidate fusion (§5.5) — integrated, not reimplemented.

Stereochemistry also enters through coupling constants. The Week 40 multiplet J-coupling layer carries an **optional vicinal-³J refinement** that applies the Karplus relation[^karplus] over an RDKit conformer ensemble, so a candidate whose conformationally locked geometry produces a large antiperiplanar diaxial coupling (≈ 10 Hz) is scored as consistent with a correspondingly large observed J. Validated against a curated literature corpus — eight reference molecules at first, since scaled to 18 — the refinement reproduces each system's diagnostic vicinal ³J to within ≈ 0.4 Hz on average and cleanly separates the conformationally locked diaxial systems (mean ≈ 9.5 Hz) from mobile, ring-flipping ones (mean ≈ 6.9 Hz) — with no overlap. It is opt-in and decision-support only — geometry-aware discrimination that complements the shift-based DP4 / DP5 panel above, never an identity claim. A further opt-in setting offers the Haasnoot–de Leeuw–Altona electronegativity-corrected generalization of the Karplus relation;[^haasnoot] it is more faithful per individual conformer (recovering a covalently locked diaxial coupling above the generic relation's ceiling), but a transparent corpus study showed it does **not** improve the averaged locked-vs-mobile discrimination under the platform's current unweighted conformer model — a candid negative result that ships default-off (the validated generic relation stays the default) and motivated the next refinement. That refinement — an opt-in **Boltzmann conformer-population weighting** that weights each conformer by its MMFF-energy population instead of counting it once — then resolved the underlying problem: it moves the worst-case sugar diaxial (β-D-galactose) from ≈ 8.5 Hz onto its ≈ 9.9 Hz literature value and *widens* the clean locked-vs-mobile separation, confirming the sugar blind spot was a conformer-population-weighting gap, not a Karplus-equation one. It too is opt-in and default-off. Scaling the corpus to 18 molecules then confirmed the result at scale: population-weighted generic is the only one of four method/weighting combinations that cleanly separates locked from mobile systems there too (within-tolerance 1.00, mean absolute error 0.57 Hz).

**Automated structure verification (ASV).** Candidate *scoring* (above) ranks how well structures explain the shifts; candidate *verification* asks the binary, regulator-facing question "does this proposed structure actually explain this spectrum?" MolTrace implements a multi-test automated-structure-verification layer in the published ASV / computer-assisted-structure-elucidation (CASE) tradition of Golotvin & Williams[^golotvin_asv] and Elyashberg, Williams & Blinov[^elyashberg_case]: several independent consistency tests (shift-prediction bounds, spin-system assignment, 2-D coverage, MS isotope match) are combined by a transparent Bayesian log-odds update into one auditable posterior confidence — with no proprietary vendor scoring scheme reproduced. It is decision-support only, integration-ready in the backend, and exposes every test's score and reasoning for the audit trail.

**Spectrum retrieval.** Complementing scoring and verification, a similarity-retrieval layer answers "which known molecules look like this spectrum?" — a Gaussian-smoothed 256-D encoding of the ¹H / ¹³C shifts with FAISS HNSW nearest-neighbour search (top-100 from a ~45k reference set in milliseconds), plus a Kuhn-Munkres set-similarity score robust to peak insertion/deletion. It follows the published NMR-Solver retrieval method,[^nmr_solver] implemented from the equations rather than any copyrighted text; an index derived from NMRShiftDB2 carries the CC-BY-SA ShareAlike obligation and is never committed.

**Quantitative purity (qNMR).** Where scoring, verification, and retrieval establish *what* a molecule is, quantitative NMR establishes *how much* — the mass-fraction purity a release or stability dossier turns on. MolTrace implements the two standard, non-proprietary qNMR methods: internal-standard (relative) qNMR, where a certified reference of known purity is weighed into the same tube and the analyte purity follows directly from the integral, proton-count, molar-mass, and weighed-mass ratios; and PULCON external-standard quantitation, which transfers an absolute concentration from a separately-measured reference via the reciprocity principle (signal ∝ 1/90°-pulse-width) without spiking the sample. A transparent ranking picks the cleanest analyte multiplet to integrate, combined uncertainties propagate per the GUM, and every intermediate ratio is preserved for the audit trail. The methods recover certified purities from public reference spectra to within 0.5 % absolute.[^qnmr_purity] [^pulcon]

**Non-uniform-sampling reconstruction.** Every layer above reasons about a finished spectrum; NUS reconstruction is the acquisition-side enabler that *produces* one. Modern multidimensional NMR often samples only a sparse subset of the indirect-dimension grid (non-uniform sampling) to cut instrument time several-fold, then reconstructs the missing increments. MolTrace ships two backends behind one interface: a robust, always-available **iterative-soft-thresholding (IST)** baseline implemented from the published Stern-Donoho-Hoch / Hyberts equations,[^hyberts_ist] and an optional deep-learning **JTF-Net** joint time-frequency reconstructor.[^jtfnet] JTF-Net loads exactly like the chemical-shift model above — lazily, local-first, with author-released weights cached out of the repository and never vendored (verify the repository license before bundling) — and never fabricates a reconstruction: when its weights or runtime are absent it falls back to IST. A candid **domain caveat** governs its use: JTF-Net's released weights were trained on *protein* multidimensional spectra, so MolTrace treats them as out-of-domain for small-molecule 2-D spectra and **defaults to the IST baseline** until JTF-Net is re-validated on small-molecule data. A reference-free quality ratio (REQUIRER) scores each reconstruction against the measured data actually acquired, so no fully-sampled reference is needed. Decision-support and opt-in, with the caveat surfaced rather than hidden.

**Solvent & impurity expert system.** Scoring, verification, retrieval, and qNMR all reason about the *analyte*; a parallel classifier reasons about everything that is **not** — the residual proton of the deuterated solvent, the water peak, a trace of pump grease, the last chromatography eluent — so a non-analyte signal is never mistaken for evidence about the candidate structure. It encodes the canonical Gottlieb (1997)[^gottlieb_1997] and Fulmer (2010)[^fulmer_2010] reference tables: fourteen deuterated solvents (CDCl₃, DMSO-d₆, CD₃OD, D₂O, acetone-d₆, C₆D₆, CD₃CN, …) with their residual ¹H / ¹³C and water shifts, plus the common-organic-impurity table (acetone, ethyl acetate, hexanes, DCM, ethanol, methanol, THF, DMF, …) tabulated in each of the seven solvent contexts Fulmer measured. `detect_solvent` recovers the most likely deuterated solvent from the observed peak pattern; `classify_peak` then sorts each peak into one of six categories — compound, solvent, residual_solvent, impurity, ¹³C-satellite, or artifact — by a transparent additive evidence scheme (high weight for a solvent-table position match or an out-of-range shift; medium for a ¹³C-satellite pair at ±½·J_CH or a line-width anomaly; low for sub-noise intensity). A distinct **`residual_solvent`** label separates leftover process solvents from the bulk deuterated-solvent line, and an intensity-prominence gate keeps a tall analyte resonance from being mislabeled when it coincides with a tabulated impurity window. The shift values are non-copyrightable facts; the module cites Fulmer and Gottlieb as scientific good practice.

### 5.3 Shift-Window Tables

The categoriser's 1H windows (4.4–6.0 ppm anomeric/vinylic, 6.0–9.0 ppm aromatic/alkene, 9.0–10.0 ppm aldehyde, 10.0–13.5 ppm carboxylic-acid OH) are sourced from the consensus across:

- Silverstein, Webster, Kiemle & Bryce, *Spectrometric Identification of Organic Compounds*, 8e (Wiley, 2014) — Table 4.10.[^silverstein_2014]
- Pretsch, Bühlmann & Badertscher, *Structure Determination of Organic Compounds: Tables of Spectral Data*, 5e (Springer, 2020) — §H.5.[^pretsch_2020]
- Friebolin, *Basic One- and Two-Dimensional NMR Spectroscopy*, 5e (Wiley-VCH, 2010) — Ch. 2.[^friebolin_2010]

Residual-solvent and trace-impurity windows come from the canonical Gottlieb (1997)[^gottlieb_1997] and the Fulmer (2010)[^fulmer_2010] organometallic-solvent extension. OH/NH/SH exchange behaviour and D₂O-shake interpretation references the open Reich (UW-Madison) NMR resources.[^reich_resources]

### 5.4 Bayesian & ML-Guided Reaction Optimisation

The Reaction Optimization program is built on the well-developed literature for Bayesian optimisation of chemical reactions[^bayesian_reactions] and the broader ML-guided reaction-condition design space.[^ml_reaction_design] The platform exposes acquisition-function-driven design-of-experiments under reaction-mechanistic-insight constraints,[^mech_insight_reactions] integrates a recent benchmark suite,[^2509_benchmark] and links the reaction history into the regulatory provenance manifest so a "this reaction was optimised toward yield + selectivity" claim is reproducible.

### 5.5 Mass Spectrometry & LC-MS

The MS evidence stack is calibrated against the standard exact-mass and adduct rules in the AI-MS market analysis,[^ai_ms_market] community fragmentation-tree literature, and the canonical mzML / mzXML open standards for vendor-agnostic raw ingestion. The LC-MS feature detection + EIC/XIC + peak purity work (Weeks 36–38) targets the same reviewer-readable evidence quality the qNMR community demands for quantitative work.[^qnmr_pharma]

**MS/MS → structure and orthogonal corroboration.** Where the stack above scores a *proposed* structure, MS/MS-based elucidation *proposes* structures directly: MolTrace integrates **CSI:FingerID** (via SIRIUS) to turn an MS/MS spectrum into predicted molecular fingerprints and ranked candidate structures,[^csi_fingerid][^sirius] calling the published tool through its documented interface rather than reimplementing it. A **METLIN-style retention-time predictor**[^metlin_rt] adds an orthogonal corroboration signal — a candidate whose predicted RT is inconsistent with the observed RT is down-weighted, never hard-filtered. These MS signals are fused with the NMR DP4 posterior (§5.2) into one calibrated candidate ranking that is decision-support only: the independent structure-verification layer (§5.2) remains the arbiter of pass/fail. Fusing NMR + MS/MS + retention time and cross-checking it with a separate verifier is how a top laboratory actually confirms a structure — orthogonal evidence, never a single technique.

**Retrieval-augmented reasoning.** The retrieval and MS/MS layers surface *candidates*; a retrieval-augmented reasoner turns them into *explained proposals*. MolTrace wraps a large language model (Anthropic Claude[^claude]) in a retrieval layer over the spectral-similarity index: it pulls the nearest known spectra — each with its SMILES, shift and multiplet summary, similarity, and license — and asks the model to propose structures **grounded in that retrieved precedent**, following the retrieval-augmented-generation pattern.[^rag_lewis] Three guardrails keep it honest. The proposal is constrained to strict JSON and re-requested once if it comes back malformed. A hallucination guard drops any candidate that neither cites a real retrieved analogue nor matches one structurally, so the model cannot invent its own support. And every surviving candidate is scored by the independent structure-verification layer (§5.2), which alone decides pass or fail — the model's self-reported confidence is advisory and is never used as the verifier's prior, so a confident-but-wrong proposal cannot inflate its own score. The retrieved analogue ids, the exact prompt, and the raw completion are written to the §6.6 audit trail, so a reviewer sees precisely what evidence the model was shown and what it returned. The LLM proposes, retrieved precedent grounds, and the verifier decides. This layer is exposed as a dedicated API surface (`POST /spectrum/reason`) that degrades gracefully — returning retrieved precedent on its own, or an empty result, when the similarity index or the reasoning model is not configured for a deployment — and writes a `spectrum.reason` entry to the audit trail on every call.

### 5.6 Model Evaluation & Calibration

Deciding whether a new model or recipe is genuinely *better* is itself a scientific question, so MolTrace standardises on one metric vocabulary rather than ad-hoc per-experiment comparisons: root-mean-square error for shift prediction, F1 for peak and classification agreement, Top-k accuracy for candidate ranking, **BedROC** for early-recognition retrieval — which weights hits near the top of a ranked list, after Truchon & Bayly[^bedroc] — and **expected calibration error** for whether a model's stated confidence matches its observed accuracy, after Guo et al.[^ece_guo] Each metric is a small, separately-tested pure function, and a single evaluation call produces the comparable metric vector that gates model promotion (§4.8).

---

## 6. Regulatory & Compliance Posture

MolTrace is engineered for environments where any analytical claim must withstand inspection. The platform's regulatory posture is anchored in three external frameworks and reinforced by internal data-integrity primitives.

### 6.1 ICH Q2(R2) — Validation of Analytical Procedures

The 2023 final ICH Q2(R2) guideline expanded the acceptance criteria for analytical method validation to explicitly address data integrity through the analytical lifecycle.[^ich_q2r2] MolTrace's audit-event ledger (`audit_events` table), immutable raw vault, recipe-hash-linked processing runs, and human-review release gate map directly onto the ALCOA+ principles (Attributable, Legible, Contemporaneous, Original, Accurate, plus Complete, Consistent, Enduring, Available). As the analytical-evidence handoff to the Regentry, the pipeline emits a deterministic ICH Q2(R2) report stub — sample / spectrum summary, result counts, and validation-characteristic slots (specificity, accuracy, precision, range) — that embeds the analysis content hash (§4.8) so the evidence is traceable to the exact run that produced it; the stub scaffolds, and never substitutes for, full method validation.

### 6.2 FDA AI Credibility Framework (2025)

The FDA's January 2025 *Considerations for the Use of Artificial Intelligence to Support Regulatory Decision-Making for Drug and Biological Products* introduces a **seven-step credibility framework** for AI in regulatory contexts.[^fda_ai_2025] MolTrace addresses each step:

| FDA step | MolTrace mechanism |
|---|---|
| Define the question of interest | Per-tab analyze targets (1H vs. 13C vs. unified confidence) |
| Define the context of use | `compound_class` selector + audit-trail context |
| Assess AI model risk | Transparent multiplier tables + DP4/DP5 panel as fallback |
| Plan and execute credibility activities | Weekly regression suites (Weeks 22–40) + smoke tests + a frozen, licence-clean public-datasets corpus with a checksummed never-trained holdout |
| Assess model output | Layer-by-layer agreement matrix in unified confidence |
| Document credibility evidence | Report composer + provenance manifests + versioned model registry + per-prediction `model_versions` |
| Maintain credibility through lifecycle | Recipe-hash-linked reruns + versioned report records + append-only model registry with reproducible layer routing + dominance-gated promotion on a checksum-locked gold set |

### 6.3 EMA Reflection Paper on AI

The EMA reflection paper on AI in the medicinal-product lifecycle similarly emphasises reproducibility, human-in-the-loop, and version control.[^ema_ai_reflection] MolTrace's human-review release gate, immutable raw archive, and reviewer signoff requirements satisfy the EMA's expectation that AI-derived evidence in submissions be subordinate to expert review.

### 6.4 Nitrosamine Impurities & Trace Contaminants

The FDA's guidance on the *Control of Nitrosamine Impurities in Human Drugs*[^fda_nitrosamines] is operationally relevant to MolTrace's impurity-candidate panel (`build_impurity_candidates` in `peak_categorization.py`). Curated solvent/impurity reference shifts drive cross-checks at analyze time so candidate trace impurities are surfaced inline with structural assignments rather than as a separate downstream report.

Regentry now exposes these controls as a single **Impurity Assessment** surface: one form (daily dose, route, substance type, treatment duration, plus any observed residual solvents, elemental impurities, and structural impurities) returns one tabbed report computed by five deterministic engines — ICH Q3A/B reporting/identification/qualification thresholds, ICH Q3C(R8) residual-solvent class limits (dose-scaled), ICH Q3D(R2) elemental-impurity PDEs, ICH M7(R2) mutagenic-impurity (Q)SAR classification, and the FDA Carcinogenic Potency Categorization Approach (CPCA) for nitrosamines, with a cumulative nitrosamine risk-ratio gate. Each engine's output carries its own regulatory-basis citation and a content hash of the rule set that produced it (`rule_set_versions`), the assessment never blocks on a malformed input (unknown elements or unparseable structures are returned as non-blocking notices), and — like every regulatory output — the result is decision-support that is gated behind an explicit qualified-reviewer sign-off before export.

**Process capability & continued process verification.** A companion **Process Capability & Trending** panel in the same Regentry dossier turns a time-ordered measurement series for one parameter — assay, a named impurity, water content — into a control chart plus a capability read-out through a single stateless `POST /regulatory/spc/analyze`. It computes the short- and long-term capability indices (Cp, Cpk, Cpu, Cpl, Pp, Ppk, Cpm) against caller-supplied specification limits, runs the selected Shewhart rule set (Western Electric[^spc_weco], Nelson[^spc_nelson], or Montgomery[^spc_montgomery]) alongside CUSUM and EWMA, and surfaces the early-warning lead explicitly: when a drift or shift signal fires *before* the first out-of-specification point, the lead time (in samples) is reported so a trend can be acted on ahead of the breach. This maps to Stage 3 (Continued Process Verification) of the FDA process-validation lifecycle and to ICH Q6A acceptance-criterion setting; a degenerate input (zero within-batch variation) returns null indices with an explicit caveat rather than a misleading number. As with every regulatory output, the result carries a verbatim disclaimer and a human-review requirement — decision-support, never a batch disposition.

**Specification-setting and OOS investigation.** Two further Regentry engines operate at the decision-rule level. A specification builder runs the ICH Q6A[^ich_q6a] decision trees over a substance or product profile, its batch data, and its method-validation state to propose a draft specification table (appearance, identification, assay, impurities, dissolution or disintegration, water content) — each impurity limit drawn from the validated Q3A/B, M7, and CPCA engines rather than hand-set, and tightened below the guideline ceiling only where the batch data demonstrate process capability (Cpk > 1.33). A companion workflow engine implements the two-phase FDA out-of-specification (OOS) investigation framework[^fda_oos]: a Phase I laboratory triage that invalidates a result only on a documented assignable cause, and a Phase II full-scale investigation that assigns a root cause and assembles an investigation report carrying the FDA OOS and ICH Q10[^ich_q10] quality-system elements (CAPA, trending, change management, management review) plus any Field-Alert / Annual-Product-Review / supplement obligations. Both are engine-level capabilities in the regulatory library — not yet exposed via a dedicated API or panel — and both are deterministic decision-support marked for qualified review, never an autonomous disposition.

### 6.5 GxP-Aligned Data Integrity

Every architectural decision in §4 maps to a GxP-aligned data-integrity primitive: the SHA-256-verified raw vault (Attributable + Enduring), the typed Pydantic models (Legible + Consistent), the audit-event ledger (Contemporaneous + Available), the immutable derivation chain from raw to report (Original + Accurate). The result is that a "data integrity" inspection question — *"Show me the raw bytes that produced this number"* — is a single click in the UI and a single SQL query in the database.

### 6.6 Audit Trail & Electronic Signatures — Controls Supporting 21 CFR Part 11

MolTrace provides software controls that **support** 21 CFR Part 11 workflows[^cfr_part11] — a cryptographic audit trail, electronic signatures, and access control — layered over the §6.5 data-integrity primitives. A decorator can wrap any analysis layer so each result is written as an immutable, signed audit record capturing the operator, the UTC timestamp, the SHA-256 of the input and output, every method parameter, the software version, and — for AI-assisted layers — the **exact model-weight checksum** that produced it, so the result is reproducible and traceable. Each record is cryptographically chained to the one before it (a SHA-256 hash chain sealed with an organisation-keyed HMAC), so any tampering, deletion, or reordering is caught by a periodic integrity check. Electronic signatures are designed per 21 CFR Part 11.50 (the signature manifestation carries the signer's name, the date and time, and the meaning — authorship, review, approval, or responsibility) and 11.70 (each signature is bound to its specific record so it cannot be copied or transferred). Records carry a configurable retention floor (default seven years) and export to a deterministic, submission-ready report (PDF/A). **Critically, these controls *help customers meet* 21 CFR Part 11 — MolTrace does not claim the product is itself compliant. Full computerized-system validation, SOPs, and identity management remain the customer's responsibility**, and the data-integrity basis follows the FDA's ALCOA+ guidance.[^fda_data_integrity]

### 6.7 GAMP 5 Appendix D11 — Computerised System Validation

For customers running a GAMP 5 risk-based validation, MolTrace generates a versioned **Appendix D11** Computerised System Validation (CSV) document skeleton[^gamp5]: a document-control block, an intended-use statement, the GAMP software-category and GxP-risk classification, a requirements-traceability matrix, and IQ/OQ/PQ activities with test-evidence slots — keyed to the same evidence (the §4.8 metric vector and end-to-end determinism result) the platform already produces. The template is timestamp-free and byte-reproducible, so it can be version-controlled as a controlled document. As with the §6.6 Part 11 controls, this **accelerates** a customer's validation effort; the full computerised-system validation and the overall compliance determination remain the regulated user's responsibility.

---

## 7. Workflow Walkthrough: Tobramycin from FID to Report

This section traces a representative end-to-end workflow.

**Step 0 — Session setup.** The analyst opens SpectraCheck and enters into the shared session card: `sampleId = TOB-2026-Q2-014`, solvent `D2O`, compound class `Carbohydrates`. The candidate textarea is set to the bundled example, which the analyst replaces with the production tobramycin SMILES. The Step 4 *Validate session inputs* card cross-checks the SMILES (parses cleanly via RDKit) and the proton-text reference (parses cleanly); the analyst sees a green *"Validation passed — analysis ready"* ribbon.

**Step 1 — Upload raw FID.** The analyst drags a Bruker `.zip` archive onto the Raw FID tab. The platform hashes it (SHA-256 `7e4a…`), stores it in the immutable vault, parses `acqus` (1H, 500 MHz, SW 12 ppm, 32 768 TD points), and surfaces the auto-FT preview chart so the analyst can visually confirm the spectrum looks healthy.

**Step 2 — Process.** Click *Process FID*. The backend runs apodisation (exponential, LB 0.3 Hz), group-delay correction, automatic phase correction, Bernstein polynomial baseline correction (order 3), and stores the recipe hash. The processed spectrum lands on the chart with peaks 5.10, 5.30, 5.55 ppm flagged in the anomeric region.

**Step 3 — Peak categorisation.** Because the SMILES contains anomeric protons (sp3 C bonded to 2 O) and no olefinic protons (sp2 C=C non-aromatic), the 4.4–6.0 ppm window resolves to `"anomeric"` rather than the legacy generic `"olefinic"`. The chart's marker traces are colour-coded slate-blue (anomeric palette); drop-lines extend from baseline to each peak top.

**Step 4 — Evidence panels light up.** Below the spectrum:

- **Peak Category Summary** — 3 anomeric, 1 oxygenated, 1 N-adjacent CH
- **Proton Inventory** — observed totals vs. structural expectation (37 H in tobramycin: 19 CH + 18 labile OH/NH); deltas flagged when |Δ| ≥ 1 H
- **Labile H Reasoning** — *"Structure declares 18 labile H atom(s) (OH/NH): 14 OH, 4 NH. D₂O solvent will exchange OH/NH signals."*
- **Candidate Comparison** — tobramycin scored against any alternates in the candidates list; per-class multiplier table (carbohydrates: `nmr2d ×1.50, carbon13 ×1.30, proton ×1.20, structure ×0.80`) surfaced under `compound_class_prior_applied`
- **References** — Silverstein, Pretsch, Friebolin, Gottlieb, Fulmer, Reich citations attached to every shift-window justification

**Step 5 — Unified confidence + report.** If MS data is available, the analyst can ingest the matching LC-MS run through the Week 35 bridge, get an HRMS exact-mass match, and feed all evidence into the Week 33 unified confidence engine. The result is composed into a Week 34 regulatory-ready report. The report cannot be released until a human reviewer (different from the composer, per tenant policy) signs off — that signoff event is written to `audit_events` and surfaces in the report's provenance footer.

The total time from FID upload to draft report on a small molecule like tobramycin, with all evidence layers active, is on the order of 5–15 minutes — a 10–50× compression versus the 6–48 hour status-quo.

---

## 8. Business Outcomes

MolTrace's Automation ROI dashboard (`/roi`) instruments four quantitative outcome metrics across every active tenant:

- **Hours saved per analysis.** Measured by mapping analyst actions in the platform (peaks picked, candidates ranked, reports composed) to a literature-calibrated minutes-saved value per action. A typical mid-complexity small-molecule analysis records 4–10 hours saved.
- **Time-to-dossier.** Mean elapsed time from first FID upload to released regulatory-ready report. Internal benchmarks suggest a 60–80 % reduction versus a fully manual baseline.
- **Reproducibility rate.** Fraction of analyses whose final report can be regenerated from the raw archive + recipe in < 5 minutes by a second reviewer. Architectural target: 100 %; observed: > 98 % across internal validation set.
- **Audit cycle time.** Hours of analyst + regulatory affairs time consumed per inspection question. Empirically, the immutable raw vault and citation-linked report cut this from days-per-question to minutes-per-question.

In B2B terms: a typical pharma analytical chemistry team of 8 FTE handling 600 analyses/year, recouping 5 hours per analysis at fully-loaded hourly cost, recoups roughly $300 K/year — well in excess of any reasonable licensing or hosting cost — before counting the audit-cycle and time-to-dossier compressions.

---

## 9. Differentiators

### 9.1 vs. Mestrelab Mnova

Mnova is the de facto industry standard for NMR processing.[^mnova_manual] It is excellent at the processing operations themselves (apodisation, phase, baseline) and offers a deeply manual UI. It is, however, a **desktop application** with no native multi-tenant SaaS posture, no built-in regulatory provenance, no cross-modal evidence stack, and no audit-event ledger. MolTrace deliberately implements the same scientific operations (the platform's FID processing recipe defaults — automatic phase correction + Bernstein order-3 baseline — match Mnova conventions) so an analyst's domain knowledge transfers, while wrapping them in the multi-tenant, audit-first, cross-modal architecture Mnova was not designed for.

### 9.2 vs. ACD/Labs Structure Elucidator

ACD/Labs offers a heavyweight, mature, proprietary structure elucidation suite. It is generally a capex-scale purchase, deeply enterprise-deployed, and not approachable for academic or smaller-CRO teams. MolTrace is web-native, deployable as SaaS, and designed for the same evidence quality at a fraction of the operational footprint.

### 9.3 vs. Open Research Frameworks

Sherlock,[^sherlock] nmrXiv,[^nmrxiv] and NMRPipe[^nmrpipe] are excellent open-research tools focused on specific niches — CASE for Sherlock, open-data archiving for nmrXiv, advanced 2D/multi-D processing for NMRPipe. They are not production R&D platforms, do not carry a regulatory-provenance layer, and require domain-expert assembly. MolTrace integrates with them where possible (mzML / mzXML import bridge, RDKit, nmrglue) while providing the productisation, the audit trail, and the multi-modal evidence engine they intentionally do not.

### 9.4 vs. Generative AI Chemistry Assistants

Recent LLM-driven assistants[^reasoning_llms][^generative_drug_discovery] offer impressive narrative generation but, when used as the sole evidence source, are not auditable, not reproducible, and not directly compatible with FDA/EMA AI credibility frameworks. MolTrace's posture is: an LLM can help draft the narrative of a structure-elucidation report, but every number in that narrative must already have a provenance hash on it. The LLM is a writer, not a witness.

---

## 10. Roadmap & Conclusion

### 10.1 Near-Term Roadmap

- **Calibrated unified confidence.** Move from heuristic candidate scoring toward a DP5-style calibrated posterior at the unified-confidence layer, drawing on the *DP5 without DFT* line of work.[^dp5_nodft]
- **Live mzML streaming.** Real-time peak-picking on incoming LC-MS scans for in-experiment QC alerts.
- **Federated tenant-private shift models.** Allow on-tenant fine-tuning of the predicted-NMR layer against the tenant's historical compounds without exposing the data to a shared model, building on PROSPRE/CSP5 architectures.[^han_prospre][^csp5]
- **Reaction → spectroscopy closed loop.** Bayesian optimisation in the Reaction Optimization program will read in-flight SpectraCheck evidence as the objective function for the next-experiment proposal.[^bayesian_reactions]
- **Expanded compliance surface.** SOC 2 Type II, ICH compliant, GDPR ready, GxP validated — currently displayed as trust seals — backed by formal third-party audit and continuous monitoring evidence.

### 10.2 Conclusion

The forty evidence layers, the immutable raw vault, the regulatory-ready report composer, the human-review release gate, and the citation-linked literature scaffold described in this paper are, in aggregate, **one thing**: an end-to-end chain of custody from a raw FID file off a Bruker spectrometer to a sentence in a regulatory submission, with every numerical claim along the way reachable and reproducible.

This is the foundation pharmaceutical R&D needs to adopt AI-supported analytical chemistry at scale without forfeiting the inspector's trust. The platform is operational, the architecture is additive, the science is grounded in the canonical literature, and the regulatory posture maps directly onto the FDA AI credibility framework and the EMA AI reflection paper. Pharmaceutical R&D, CRO, and academic R&D groups can adopt MolTrace today for routine NMR + MS workflows and grow the platform's role as their multi-modal evidence needs grow.

For information on pilot deployments, integration with Bruker / Agilent instrumentation, or regulatory-affairs onboarding, contact MolTrace Technologies.

---

## References

[^framework]: *A framework for automated structure elucidation from routine NMR spectra.* Anal. Chem. community survey, 2024. (Reference: Spectroscopy/Papers/A framework for automated structure elucidation from routine NMR spectra.pdf)

[^csp5]: Williams G. et al. *CSP5: Large-scale Neural Chemical Shift Prediction.* Preprint, 2024.

[^dp5_nodft]: Howarth A.; Goodman J. M. *DP5 without DFT: uncertainty-calibrated graph neural net accelerates structure confirmation via NMR.* 2024.

[^golotvin_asv]: Golotvin S. S.; Williams A. J. et al. *Automated structure verification (ASV) of small organic molecules from 1D / 2D NMR.* Magn. Reson. Chem. (ACD/Labs ASV methodology).

[^elyashberg_case]: Elyashberg M. E.; Williams A. J.; Blinov K. A. *Contemporary Computer-Assisted Approaches to Molecular Structure Elucidation.* RSC Publishing, 2012. doi:10.1039/9781849733625; and Elyashberg et al., *Prog. Nucl. Magn. Reson. Spectrosc.* reviews on CASE.

[^nmr_solver]: Jin Y. et al. *NMR-Solver: Automated Structure Elucidation via Large-Scale Spectral Matching and Physics-Guided Fragment Optimization.* arXiv:2509.00640 (2025); Nat. Commun.

[^rag_lewis]: Lewis P.; Perez E.; Piktus A.; Petroni F.; Karpukhin V.; Goyal N.; Küttler H.; Lewis M.; Yih W.; Rocktäschel T.; Riedel S.; Kiela D. *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.* Advances in Neural Information Processing Systems 33 (NeurIPS 2020); arXiv:2005.11401. The retrieval-grounded-generation pattern behind MolTrace's §5.5 reasoning layer — the model proposes only over retrieved precedent, never free-generates.

[^claude]: Anthropic. *Claude* (model `claude-opus-4-8`), accessed via the Anthropic Messages API with structured-output (strict-JSON) constraints. The reasoning model behind MolTrace's §5.5 retrieval-augmented proposal layer; integrated as an injectable, optional backend (never bundled), with its proposals grounded in retrieved precedent and arbitrated by the independent §5.2 verifier.

[^qnmr_purity]: Pauli G. F.; Chen S.-N.; Simmler C.; Lankin D. C.; McAlpine J. B. et al. *Importance of Purity Evaluation and the Potential of Quantitative ¹H NMR as a Purity Assay.* J. Med. Chem. 2014, 57, 9220. doi:10.1021/jm500734a; and Bharti S. K.; Roy R. *Quantitative ¹H NMR spectroscopy.* TrAC Trends Anal. Chem. 2012, 35, 5. doi:10.1016/j.trac.2012.02.007. The internal-standard qNMR equation behind MolTrace's §5.2 purity layer.

[^pulcon]: Wider G.; Dreier L. *Measuring Protein Concentrations by NMR Spectroscopy.* J. Am. Chem. Soc. 2006, 128, 2571. doi:10.1021/ja055336t. The PULCON reciprocity principle (signal ∝ 1/90°-pulse-width) behind MolTrace's external-standard purity route.

[^jtfnet]: Luo Y.; Su Z.; Chen W. et al. *Deep learning network for NMR spectra reconstruction in time-frequency domain and quality assessment.* Nat. Commun. 2025, 16, 2342. doi:10.1038/s41467-025-57721-w. The optional JTF-Net NUS-reconstruction backend and the reference-free REQUIRER quality ratio behind MolTrace's §5.2 reconstruction layer; protein-trained weights downloaded by the end user, never vendored.

[^hyberts_ist]: Hyberts S. G.; Milbradt A. G.; Wagner A. B.; Arthanari H.; Wagner G. *Application of iterative soft thresholding for fast reconstruction of NMR data non-uniformly sampled with multidimensional Poisson Gap scheduling.* J. Biomol. NMR 2012, 52, 315. doi:10.1007/s10858-012-9611-z; with the method introduced by Stern A. S.; Donoho D. L.; Hoch J. C. *NMR data processing using iterative thresholding and minimum l1-norm reconstruction.* J. Magn. Reson. 2007, 188, 295. doi:10.1016/j.jmr.2007.07.008. The always-available IST baseline behind MolTrace's §5.2 reconstruction layer (weights-free, implemented from the published equations).

[^reasoning_llms]: *Enhancing molecular structure elucidation with reasoning-capable LLMs.* 2024.

[^prediction_chhaganlal]: Chhaganlal et al. *Evaluation of NMR predictors for accuracy and ability to reveal trends.* Magnetic Resonance in Chemistry, 2023.

[^mnova_manual]: Mestrelab Research. *MestReNova User Manual.* 2024.

[^benchtop_qm]: *Benchtop NMR Data and Quantum Mechanical Spectral Analysis.* 2023.

[^fda_ai_2025]: U.S. Food and Drug Administration. *Considerations for the Use of Artificial Intelligence to Support Regulatory Decision-Making for Drug and Biological Products.* Draft Guidance, January 2025.

[^ema_ai_reflection]: European Medicines Agency. *Reflection paper on the use of Artificial Intelligence (AI) in the medicinal product lifecycle.* 2024.

[^ich_q2r2]: International Council for Harmonisation. *ICH Q2(R2): Validation of Analytical Procedures.* 2023.

[^cfr_part11]: U.S. Food and Drug Administration. *21 CFR Part 11 — Electronic Records; Electronic Signatures* (esp. §11.50 signature manifestations, §11.70 signature/record linking). U.S. Government work, public domain. MolTrace's §6.6 audit-trail and electronic-signature controls are built to SUPPORT these requirements; MolTrace does not claim the product is itself compliant with the rule — computerized-system validation remains the customer's responsibility.

[^fda_data_integrity]: U.S. Food and Drug Administration. *Data Integrity and Compliance With Drug CGMP: Questions and Answers — Guidance for Industry* (December 2018) — the ALCOA+ data-integrity attributes. U.S. Government work, public domain.

[^ai_ms_market]: *AI in Mass Spectrometry Software Market Size, Dynamics and Opportunities.* 2024 industry report.

[^silverstein_2014]: Silverstein R. M.; Webster F. X.; Kiemle D. J.; Bryce D. L. *Spectrometric Identification of Organic Compounds*, 8th ed. Wiley, 2014.

[^pretsch_2020]: Pretsch E.; Bühlmann P.; Badertscher M. *Structure Determination of Organic Compounds: Tables of Spectral Data*, 5th ed. Springer, 2020. doi:10.1007/978-3-662-62439-5

[^friebolin_2010]: Friebolin H. *Basic One- and Two-Dimensional NMR Spectroscopy*, 5th ed. Wiley-VCH, 2010.

[^karplus]: Karplus M. *Contact Electron-Spin Coupling of Nuclear Magnetic Moments.* J. Chem. Phys. 1959, 30, 11–15. doi:10.1063/1.1729860. See also Karplus M. *Vicinal Proton Coupling in Nuclear Magnetic Resonance.* J. Am. Chem. Soc. 1963, 85, 2870–2871. doi:10.1021/ja00900a059. The three-term form ³J(θ) = A·cos²θ + B·cosθ + C — with the generic constants A = 7.76, B = −1.10, C = 1.40 as tabulated in Pretsch 5e[^pretsch_2020] — underlies Layer 40's opt-in vicinal refinement.

[^haasnoot]: Haasnoot C. A. G.; de Leeuw F. A. A. M.; Altona C. *The relationship between proton-proton NMR coupling constants and substituent electronegativities — I. An empirical generalization of the Karplus equation.* Tetrahedron 1980, 36, 2783–2792. doi:10.1016/0040-4020(80)80155-4. Adds substituent-electronegativity (Huggins Δχ) and orientation (ξ = ±1) corrections to the bare Karplus cosine series; available in MolTrace as the opt-in, default-off `karplus_method='haasnoot_altona'` vicinal refinement.

[^gottlieb_1997]: Gottlieb H. E.; Kotlyar V.; Nudelman A. *NMR Chemical Shifts of Common Laboratory Solvents as Trace Impurities.* J. Org. Chem. 1997, 62, 7512. doi:10.1021/jo971176v

[^fulmer_2010]: Fulmer G. R. et al. *NMR Chemical Shifts of Trace Impurities: Common Laboratory Solvents, Organics, and Gases in Deuterated Solvents Relevant to the Organometallic Chemist.* Organometallics 2010, 29, 2176. doi:10.1021/om100106e

[^reich_resources]: Reich H. J. *OH and NH proton chemical shifts, exchange, and broadening.* University of Wisconsin–Madison. https://organicchemistrydata.org/hansreich/resources/nmr/

[^bedroc]: Truchon J.-F.; Bayly C. I. *Evaluating Virtual Screening Methods: Good and Bad Metrics for the "Early Recognition" Problem.* J. Chem. Inf. Model. 2007, 47, 488. doi:10.1021/ci600426e. The BedROC early-recognition metric behind MolTrace's §5.6 evaluation framework.

[^ece_guo]: Guo C.; Pleiss G.; Sun Y.; Weinberger K. Q. *On Calibration of Modern Neural Networks.* Proc. 34th Int. Conf. on Machine Learning (ICML) 2017, PMLR 70, 1321. The expected-calibration-error (ECE) definition behind MolTrace's §5.6 calibration metric.

[^gamp5]: International Society for Pharmaceutical Engineering (ISPE). *GAMP 5: A Risk-Based Approach to Compliant GxP Computerised Systems*, 2nd ed., 2022 — including Appendix D11 (Computerised System Validation). The structure behind the §6.7 validation-document skeleton MolTrace generates.

[^duus_carbo]: Duus J. Ø. et al. *NMR Spectroscopy of Carbohydrates.* Carbohydr. Res. 2000.

[^cavanagh_protein_nmr]: Cavanagh J.; Fairbrother W. J.; Palmer A. G.; Rance M.; Skelton N. J. *Protein NMR Spectroscopy: Principles and Practice*, 2nd ed. Academic Press, 2007.

[^bovey_polymer]: Bovey F. A. *Polymer NMR.* Academic Press, 1972 (and modern editions).

[^smith_goodman_2010]: Smith S. G.; Goodman J. M. *Assigning the Stereochemistry of Pairs of Diastereoisomers from GIAO NMR Shift Calculations: The DP4 Probability.* J. Am. Chem. Soc. 2010, 132, 12946. doi:10.1021/ja105035r

[^howarth_2020_dp4ai]: Howarth A.; Ermanis K.; Goodman J. M. *DP4-AI automated NMR data analysis: straight from spectrometer to structure.* Chem. Sci. 2020, 11, 4351. doi:10.1039/D0SC00742K

[^howarth_2022_dp5]: Howarth A.; Goodman J. M. *The DP5 probability, quantification and visualisation of structural uncertainty in single molecules.* Chem. Sci. 2022, 13, 3507. doi:10.1039/D1SC04953D

[^han_prospre]: Han H.-J.; Rodriguez-Espigares I.; Plante O. J.; Riniker S. *Accurate Prediction of 1H NMR Chemical Shifts of Small Molecules Using Machine Learning.* Metabolites 2024, 14, 1. doi:10.3390/metabo14010001

[^kwon_mpnn]: Kwon Y.; Lee D.; Choi Y.-S.; Kang S. *Neural message passing for NMR chemical shift prediction.* J. Chem. Inf. Model. 2020, 60, 2024. doi:10.1021/acs.jcim.0c00195

[^park_2021]: Park K.; Han S.; Kim H. *Molecular search by NMR spectrum based on evaluation of matching between spectrum and molecule.* Sci. Rep. 2021, 11. doi:10.1038/s41598-021-99081-7

[^bayesian_reactions]: *Bayesian optimization for chemical reactions.* (Reference: Reaction Optimization/Bayesian optimization for chemical reactions.pdf)

[^ml_reaction_design]: *Machine Learning-Guided Strategies for Reaction Condition Design and Optimization.* (Reference: Reaction Optimization/Machine Learning-Guided Strategies for Reaction Condition Design and Optimization.pdf)

[^mech_insight_reactions]: *Reaction optimization through mechanistic insight and predictive modelling.* (Reference: Reaction Optimization/Reaction optimization through mechanistic insight and predictive modelling.pdf)

[^2509_benchmark]: arXiv:2509.00103v2 — recent reaction-optimisation benchmark referenced in MolTrace's reaction-suite calibration.

[^qnmr_pharma]: *Quantitative NMR Spectroscopy in Pharmaceutical Applications.* (Reference: Spectroscopy/qNMR + Protein_NMR folder)

[^fda_nitrosamines]: U.S. Food and Drug Administration. *Control of Nitrosamine Impurities in Human Drugs.* Guidance for Industry.

[^sherlock]: *Sherlock: A Free and Open-Source System for the Computer-Assisted Structure Elucidation of Organic Compounds.* (Reference: Spectroscopy/Papers/Sherlock A Free and Open-Source System...pdf)

[^nmrxiv]: *Overview nmrXiv.* (Reference: Spectroscopy/Papers/Overview nmrXiv.pdf)

[^nmrpipe]: *NMRPipe.* (Reference: Spectroscopy/Papers/NMRPipe.pdf)

[^generative_drug_discovery]: *Generative AI for drug discovery and protein design.* (Reference: Spectroscopy/Papers/Generative AI for drug discovery and protein design.pdf)

[^csi_fingerid]: Dührkop K.; Shen H.; Meusel M.; Rousu J.; Böcker S. *Searching molecular structure databases with tandem mass spectra using CSI:FingerID.* Proc. Natl. Acad. Sci. USA 2015, 112, 12580. doi:10.1073/pnas.1509788112. The MS/MS → molecular-fingerprint → ranked-candidate model behind MolTrace's §5.5 MS structure-proposal layer; called through its documented interface, never reimplemented.

[^sirius]: Dührkop K.; Fleischauer M.; Ludwig M.; Aksenov A. A.; Melnik A. V.; Meusel M.; Dorrestein P. C.; Rousu J.; Böcker S. *SIRIUS 4: a rapid tool for turning tandem mass spectra into metabolite structure information.* Nat. Methods 2019, 16, 299. doi:10.1038/s41592-019-0344-8. The host application for CSI:FingerID that MolTrace integrates.

[^metlin_rt]: Domingo-Almenara X.; Guijas C.; Billings E.; Montenegro-Burke J. R.; Uritboonthai W.; Aisporna A. E.; Chen E.; Benton H. P.; Siuzdak G. *The METLIN small molecule dataset for machine learning-based retention time prediction.* Nat. Commun. 2019, 10, 5811. doi:10.1038/s41467-019-13680-7. The basis for MolTrace's §5.5 retention-time corroboration signal.

[^spc_montgomery]: Montgomery D. C. *Introduction to Statistical Quality Control*, Wiley. The standard reference for the process-capability indices (Cp/Cpk/Pp/Ppk and the Cpk ≥ 1.33 capability banding), the d₂ unbiasing constants behind the moving-range sigma estimate, and the CUSUM (k = 0.5σ, h = 5σ) and EWMA (λ = 0.2, L = 3) chart designs MolTrace's §6.4 trending engine implements as published, never re-derived.

[^spc_weco]: Western Electric Company. *Statistical Quality Control Handbook*, 1st ed., 1956. Origin of the zone-based control-chart tests — the classic four WECO run/zone rules encoded as MolTrace's `western_electric_classic` rule set.

[^spc_nelson]: Nelson L. S. *The Shewhart Control Chart — Tests for Special Causes.* J. Qual. Technol. 1984, 16 (4), 237–239. The eight run-and-zone tests (counts 1 / 9 / 6 / 14 / 2-of-3 / 4-of-5 / 15 / 8) implemented as MolTrace's `nelson` / `montgomery` / default `western_electric` rule sets.

[^ich_q6a]: ICH *Q6A — Specifications: Test Procedures and Acceptance Criteria for New Drug Substances and New Drug Products: Chemical Substances* (1999). The decision trees MolTrace's specification-builder engine encodes for appearance, identification, assay, impurity, dissolution/disintegration, and water-content acceptance criteria.

[^fda_oos]: U.S. FDA. *Guidance for Industry — Investigating Out-of-Specification (OOS) Test Results for Pharmaceutical Production* (2006). The two-phase laboratory / full-scale investigation framework MolTrace's OOS workflow engine implements, including the assignable-cause invalidation rule.

[^ich_q10]: ICH *Q10 — Pharmaceutical Quality System* (2008). The PQS elements (CAPA, process-performance and product-quality monitoring, change management, management review) MolTrace's OOS investigation report assembles.

---

*© 2026 MolTrace Technologies, Inc. This white paper is intended for informational and evaluation purposes. The platform descriptions reflect the production state as of release 40 (Multiplet J-Coupling → Unified Confidence Bridge). For pilot evaluation, regulatory-affairs briefings, or technical due-diligence access, contact MolTrace Technologies.*
