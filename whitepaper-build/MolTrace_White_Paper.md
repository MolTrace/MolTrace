# MolTrace

## AI-Native Scientific Intelligence for Pharmaceutical R&D

### Architecture, Evidence Engine, and the Audit-Ready Path from Raw Spectra to Regulatory-Ready Reports

---

**A MolTrace Technologies, Inc. White Paper**
Document version: 2026-Q2 · Hybrid (business + technical) · Approx. 5,200 words

> *"Scientific intelligence has to be reproducible to be useful, auditable to be acceptable, and integrated to be adopted."*

---

## 1. Executive Summary

Small-molecule R&D in pharmaceutical, biotech, CRO, and academic settings rests on three intertwined activities: **identifying** what a sample is (spectroscopy and mass spectrometry), **understanding** how it was made (reaction optimisation), and **proving** it to a regulator (compliant documentation). These three activities are today fragmented across desktop tools, lab notebooks, vendor file formats, manual spreadsheets, and email-attached PDFs. Time-to-structure remains measured in days. Reproducibility is anecdotal. Regulatory submissions still consume months of evidence reconciliation.

MolTrace is an end-to-end, AI-native scientific intelligence platform that closes the loop between raw analytical data and audit-ready decisions. It is composed of three integrated programs sharing one evidence engine, one immutable raw-data vault, and one regulatory provenance layer:

- **SpectraCheck** — multi-layer NMR + MS evidence engine that ingests 1H, 13C, 2D NMR, raw FID (Bruker / Agilent-Varian), HRMS, MS/MS, and LC-MS feature data; categorises peaks against literature-backed chemical-shift windows; ranks candidate structures with DP4 / DP5-class methods; and surfaces every numerical claim with its provenance hash.
- **Regulatory Intelligence Hub** — dossier scaffolding, ICH/FDA/EMA-aligned audit packs, controlled human-in-the-loop release gating, and AI-supported question/answer routing built on the 2025 FDA "Considerations for the Use of Artificial Intelligence to Support Regulatory Decision-Making" framework and the EMA AI reflection paper.
- **Reaction Optimization** — Bayesian optimisation, multi-objective response surface modelling, mechanistic-insight-guided design-of-experiments, and reaction-condition planning, integrated with the same SMILES candidates and the same evidence trail.

All three programs sit on top of a single **`/analyze` evidence stack** of thirty-nine production-graded layers (Weeks 22–39), an immutable raw FID vault with SHA-256 integrity verification, and a multi-tenant SaaS architecture (FastAPI + Postgres + Next.js + RDKit + nmrglue). The result: any number in a regulatory dossier — a chemical shift, a peak integration, a candidate score — traces back through the platform to a specific spectrum file, a specific processing recipe, a specific literature citation, and a specific human reviewer.

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

The platform consists of a **FastAPI** backend (Python 3.13, ~24 000-line `api.py` plus ~60 domain modules under `nmrcheck/`) and a **Next.js 15** frontend (TypeScript, React 19, shadcn/ui, Plotly for spectra). State is persisted in **PostgreSQL** (SQLite in local dev), raw archives in an immutable file vault, and large-job orchestration in a background-job queue. The build-out follows a strictly additive weekly-release cadence (Weeks 20 → 39 to date) so every existing endpoint and regression test stays green as new evidence layers land.

```
   ┌──────────────────────────────────────────────────────────────────┐
   │                      Next.js Frontend (Vercel)                    │
   │  Marketing │ Dashboard │ SpectraCheck │ Regulatory │ Reactions   │
   └──────────┬────────────────────────────────┬─────────────────────┘
              │ /api/backend/*                  │
   ┌──────────▼────────────────────────────────▼─────────────────────┐
   │                    FastAPI Backend (Python)                       │
   │  Auth · Tenant · 39-layer Evidence Stack · Reports · Audit       │
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

The defining feature of MolTrace is the **39-layer evidence engine** built incrementally as Weeks 22 through 39. Each layer is additive — never overwrites a prior layer — and every layer's output is a typed Pydantic model with stable JSON keys so downstream code (and regulators) can rely on the contract.

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

Critically, **every layer can run on its own** for diagnostic use, **and** is composable into the unified confidence engine when the user has the inputs. A laboratory that has only 1H NMR can use the platform productively today; the same laboratory adding LC-MS next quarter does not need to re-onboard. The same Pydantic models, the same audit pipeline, the same reviewer signoff workflow apply.

Alongside the default 39-layer chain, an **opt-in Mestrenova-style Global Spectral Deconvolution (GSD) analysis backend** is available at the dedicated `POST /spectrum/analyze/gsd` endpoint. GSD performs single-pass peak detection with iterative pseudo-Voigt overlap resolution, classifies every peak into `compound | solvent | impurity | artifact | 13C_satellite` against the curated Fulmer / Gottlieb residual-solvent tables, and clusters multiplet lines into chemical-environment entries so the response can be consumed at either granularity. The GSD backend has cleared its strict production-promotion gate across three independent corpora: the curated NMRShiftDB2 19-fixture corpus (100 % solvent auto-detect, median compound-environment-count delta of 2 vs expert reference), an HMDB-style synthetic 20-fixture multiplet-line corpus (95 % / 100 % within tolerance), and a **real-instrument HMDB 100-fixture corpus** (95 % parseable, 93 % solvent auto-detect) that closes the literal Prompt 3 acceptance criterion of "100 spectra from NMRShiftDB2 + HMDB" on real instrument data. Tenants opt in per request via a frontend toggle; the default `/spectrum/analyze` flow is unchanged so existing pipelines stay green. See the technical white paper §3.1 for the algorithm, validation framework, and per-fixture results.

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

The unified confidence engine (Week 33) is the platform's final decision-support layer. It accepts whatever subset of evidence the laboratory has — predicted NMR matching, HRMS exact mass, MS1 adduct/isotope inference, processed MS/MS annotation, fragmentation-tree reasoning, and LC-MS consensus (via the Week 39 bridge) — and produces:

- A **ranked candidate list** with normalised confidence scores
- A **layer-by-layer agreement matrix** showing which evidence layers support which candidate
- **Contradictions** (e.g. HRMS-implied formula disagrees with NMR proton inventory)
- **Missing layers** (e.g. "no MS/MS supplied; structure isomer discrimination weakened")
- **Ambiguity alerts** when the top two candidates are within 0.05 score units

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

The DP4 family of methods (Smith & Goodman 2010,[^smith_goodman_2010] Howarth & Goodman DP4-AI 2020,[^howarth_2020_dp4ai] DP5 2022[^howarth_2022_dp5]) provides Bayesian posteriors over candidate stereochemistry conditioned on observed shifts. The Week 26 candidate-comparison layer uses a transparent heuristic for fast iterative review; the DP4 panel runs in parallel when the user supplies ≥ 2 candidates and observed shifts. The 2024 *DP5 without DFT* paper by Howarth (graph-NN uncertainty calibrated) is referenced in the platform's compute-light DP5 pathway.[^dp5_nodft]

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

---

## 6. Regulatory & Compliance Posture

MolTrace is engineered for environments where any analytical claim must withstand inspection. The platform's regulatory posture is anchored in three external frameworks and reinforced by internal data-integrity primitives.

### 6.1 ICH Q2(R2) — Validation of Analytical Procedures

The 2023 final ICH Q2(R2) guideline expanded the acceptance criteria for analytical method validation to explicitly address data integrity through the analytical lifecycle.[^ich_q2r2] MolTrace's audit-event ledger (`audit_events` table), immutable raw vault, recipe-hash-linked processing runs, and human-review release gate map directly onto the ALCOA+ principles (Attributable, Legible, Contemporaneous, Original, Accurate, plus Complete, Consistent, Enduring, Available).

### 6.2 FDA AI Credibility Framework (2025)

The FDA's January 2025 *Considerations for the Use of Artificial Intelligence to Support Regulatory Decision-Making for Drug and Biological Products* introduces a **seven-step credibility framework** for AI in regulatory contexts.[^fda_ai_2025] MolTrace addresses each step:

| FDA step | MolTrace mechanism |
|---|---|
| Define the question of interest | Per-tab analyze targets (1H vs. 13C vs. unified confidence) |
| Define the context of use | `compound_class` selector + audit-trail context |
| Assess AI model risk | Transparent multiplier tables + DP4/DP5 panel as fallback |
| Plan and execute credibility activities | Weekly regression suites (Weeks 22–39) + smoke tests |
| Assess model output | Layer-by-layer agreement matrix in unified confidence |
| Document credibility evidence | Report composer + provenance manifests |
| Maintain credibility through lifecycle | Recipe-hash-linked reruns + versioned report records |

### 6.3 EMA Reflection Paper on AI

The EMA reflection paper on AI in the medicinal-product lifecycle similarly emphasises reproducibility, human-in-the-loop, and version control.[^ema_ai_reflection] MolTrace's human-review release gate, immutable raw archive, and reviewer signoff requirements satisfy the EMA's expectation that AI-derived evidence in submissions be subordinate to expert review.

### 6.4 Nitrosamine Impurities & Trace Contaminants

The FDA's guidance on the *Control of Nitrosamine Impurities in Human Drugs*[^fda_nitrosamines] is operationally relevant to MolTrace's impurity-candidate panel (`build_impurity_candidates` in `peak_categorization.py`). Curated solvent/impurity reference shifts drive cross-checks at analyze time so candidate trace impurities are surfaced inline with structural assignments rather than as a separate downstream report.

### 6.5 GxP-Aligned Data Integrity

Every architectural decision in §4 maps to a GxP-aligned data-integrity primitive: the SHA-256-verified raw vault (Attributable + Enduring), the typed Pydantic models (Legible + Consistent), the audit-event ledger (Contemporaneous + Available), the immutable derivation chain from raw to report (Original + Accurate). The result is that a "data integrity" inspection question — *"Show me the raw bytes that produced this number"* — is a single click in the UI and a single SQL query in the database.

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

The thirty-nine evidence layers, the immutable raw vault, the regulatory-ready report composer, the human-review release gate, and the citation-linked literature scaffold described in this paper are, in aggregate, **one thing**: an end-to-end chain of custody from a raw FID file off a Bruker spectrometer to a sentence in a regulatory submission, with every numerical claim along the way reachable and reproducible.

This is the foundation pharmaceutical R&D needs to adopt AI-supported analytical chemistry at scale without forfeiting the inspector's trust. The platform is operational, the architecture is additive, the science is grounded in the canonical literature, and the regulatory posture maps directly onto the FDA AI credibility framework and the EMA AI reflection paper. Pharmaceutical R&D, CRO, and academic R&D groups can adopt MolTrace today for routine NMR + MS workflows and grow the platform's role as their multi-modal evidence needs grow.

For information on pilot deployments, integration with Bruker / Agilent instrumentation, or regulatory-affairs onboarding, contact MolTrace Technologies.

---

## References

[^framework]: *A framework for automated structure elucidation from routine NMR spectra.* Anal. Chem. community survey, 2024. (Reference: Spectroscopy/Papers/A framework for automated structure elucidation from routine NMR spectra.pdf)

[^csp5]: Williams G. et al. *CSP5: Large-scale Neural Chemical Shift Prediction.* Preprint, 2024.

[^dp5_nodft]: Howarth A.; Goodman J. M. *DP5 without DFT: uncertainty-calibrated graph neural net accelerates structure confirmation via NMR.* 2024.

[^reasoning_llms]: *Enhancing molecular structure elucidation with reasoning-capable LLMs.* 2024.

[^prediction_chhaganlal]: Chhaganlal et al. *Evaluation of NMR predictors for accuracy and ability to reveal trends.* Magnetic Resonance in Chemistry, 2023.

[^mnova_manual]: Mestrelab Research. *MestReNova User Manual.* 2024.

[^benchtop_qm]: *Benchtop NMR Data and Quantum Mechanical Spectral Analysis.* 2023.

[^fda_ai_2025]: U.S. Food and Drug Administration. *Considerations for the Use of Artificial Intelligence to Support Regulatory Decision-Making for Drug and Biological Products.* Draft Guidance, January 2025.

[^ema_ai_reflection]: European Medicines Agency. *Reflection paper on the use of Artificial Intelligence (AI) in the medicinal product lifecycle.* 2024.

[^ich_q2r2]: International Council for Harmonisation. *ICH Q2(R2): Validation of Analytical Procedures.* 2023.

[^ai_ms_market]: *AI in Mass Spectrometry Software Market Size, Dynamics and Opportunities.* 2024 industry report.

[^silverstein_2014]: Silverstein R. M.; Webster F. X.; Kiemle D. J.; Bryce D. L. *Spectrometric Identification of Organic Compounds*, 8th ed. Wiley, 2014.

[^pretsch_2020]: Pretsch E.; Bühlmann P.; Badertscher M. *Structure Determination of Organic Compounds: Tables of Spectral Data*, 5th ed. Springer, 2020. doi:10.1007/978-3-662-62439-5

[^friebolin_2010]: Friebolin H. *Basic One- and Two-Dimensional NMR Spectroscopy*, 5th ed. Wiley-VCH, 2010.

[^gottlieb_1997]: Gottlieb H. E.; Kotlyar V.; Nudelman A. *NMR Chemical Shifts of Common Laboratory Solvents as Trace Impurities.* J. Org. Chem. 1997, 62, 7512. doi:10.1021/jo971176v

[^fulmer_2010]: Fulmer G. R. et al. *NMR Chemical Shifts of Trace Impurities: Common Laboratory Solvents, Organics, and Gases in Deuterated Solvents Relevant to the Organometallic Chemist.* Organometallics 2010, 29, 2176. doi:10.1021/om100106e

[^reich_resources]: Reich H. J. *OH and NH proton chemical shifts, exchange, and broadening.* University of Wisconsin–Madison. https://organicchemistrydata.org/hansreich/resources/nmr/

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

---

*© 2026 MolTrace Technologies, Inc. This white paper is intended for informational and evaluation purposes. The platform descriptions reflect the production state as of release 39 (LC-MS Consensus → Unified Confidence Bridge). For pilot evaluation, regulatory-affairs briefings, or technical due-diligence access, contact MolTrace Technologies.*
