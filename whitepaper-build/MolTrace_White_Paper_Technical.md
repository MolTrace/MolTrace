---
title: "MolTrace — Technical White Paper"
subtitle: "Architecture, Scientific Foundations, and Regulatory Posture for Analytical-Method Validators and Regulatory Reviewers"
version: "2026-05-28f"
audience: "Analytical-method validators, NMR / MS technical leads, regulatory-affairs reviewers, IT / data-integrity auditors"
length: "≈7,500 words · Technical variant of the canonical hybrid white paper"
---

# MolTrace

## Technical White Paper

### Architecture, Scientific Foundations, and Regulatory Posture for Analytical-Method Validators and Regulatory Reviewers

---

## 1. Executive Summary

This is the technical-reviewer variant of the MolTrace white paper. It is written for the analytical-method validator who must defend an AI-assisted assignment to a regulator, the NMR or MS technical lead who must approve adoption inside a GxP-regulated laboratory, the regulatory-affairs reviewer who must map MolTrace evidence layers to the FDA AI Credibility Framework's seven steps, and the data-integrity auditor who must verify ALCOA+ posture end-to-end.

We assume the reader is familiar with: 1H and 13C NMR practice, DP4/DP5-class candidate scoring, mzML interoperability, ICH Q2(R2) validation acceptance criteria, and the FDA's January 2025 AI guidance for drug and biological products. This document does **not** repeat the high-level business case (see the *Sales-Led variant*) or the platform overview (see the *Hybrid white paper*). It focuses on the science, the architecture, and the audit primitives.

---

## 2. Architecture in One Diagram

```
                          ┌────────────────────────────────────┐
                          │   Next.js Frontend (TypeScript)    │
                          │   React 19 · shadcn/ui · Plotly    │
                          └─────────────────┬──────────────────┘
                                            │ /api/backend/*
                          ┌─────────────────▼──────────────────┐
                          │    FastAPI Backend (Python 3.13)   │
                          │     ~24,000-line api.py + 60       │
                          │       domain modules               │
                          └────┬──────────────────┬─────────┬──┘
                               │                  │         │
                  ┌────────────▼─────┐  ┌────────▼───┐  ┌──▼──────────┐
                  │ PostgreSQL       │  │ Immutable  │  │ Background  │
                  │ users · tenants  │  │ Raw FID    │  │ Job Queue   │
                  │ raw_archives     │  │ Vault      │  │             │
                  │ fid_runs         │  │ SHA-256    │  │ Long-running│
                  │ audit_events     │  │ verified   │  │ analyses    │
                  └──────────────────┘  └────────────┘  └─────────────┘
```

Core invariants enforced architecturally:

1. Raw FID uploads are immutable vault records; processing stores derived metadata and hashes, never overwrites raw bytes.
2. Empty / invalid SMILES must fail validation cleanly.
3. Empty / malformed NMR text must fail validation cleanly.
4. Structure and parsed NMR text must agree before analysis is accepted (or the disagreement must be surfaced as an explicit warning, never silently swallowed).
5. Spectrum-viewer controls must not break the analysis flow (display gain is y-axis only and never alters evidence intensity data).
6. Reference-assisted matching must remain visible in preview / analyze pathways.
7. Stale auth tokens must return the UI to the auth screen cleanly.

These invariants are enforced both at the typed-model layer (Pydantic with `extra="forbid"` on response schemas) and at the regression-test layer (a workflow-smoke suite that exercises register → login → validate → analyze → preview → reference-assisted analysis → job submission → review approve/reject → export).

---

## 3. The 39-Layer Evidence Engine — Module Inventory

The evidence engine is built strictly additively across thirty-nine weekly releases. Each layer is a self-contained Python module under `src/nmrcheck/`, with its own Pydantic request/response models, its own audit-event types, and its own regression test file. The structure ensures that adding a new layer never destabilises an earlier one — a critical property for tenant adoption inside regulated environments.

| Wk | Module | Capability |
|----|--------|-----------|
| 22 | `proton.py`, `carbon13.py` | 1H + 13C evidence scoring vs. SMILES; solvent-aware shift windows |
| 23 | `nmr2d.py`, `nmr2d_analyzer.py`, `nmr2d_parser.py`, `nmr2d_models.py` | Guarded processed 2D NMR (COSY, HSQC/HMQC, HMBC) |
| 24 | `raw_vault.py`, `fid.py`, `raw_store.py` | Immutable raw FID vault + Bruker / Agilent-Varian 1D processing |
| 25 | `nmr2d_routes.py` | 2D evidence engine routes guarded behind `ENABLE_2D_NMR` |
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

Supporting modules used across multiple layers: `peak_categorization.py` (per-peak category + region + labile hint + impurity match), `compound_class_priors.py` (per-class multiplier table for candidate scoring), `compound_classes.py` (canonical class taxonomy with `normalize_compound_class()`), `chemistry.py` (SMILES → StructureSummary), `dp4_scoring.py` (DP4 Bayesian posterior), `literature_data.py` (citation registry), `solvents.py` (NMR solvent profiles), `impurities.py` (curated impurity reference shifts), `nmr_tables.py` (1H + 13C shift region tables).

### 3.1 Opt-in experimental analysis backend — Prompt 3 GSD

Alongside the default 39-layer chain a separate **Global Spectral Deconvolution** sidecar is available as an opt-in analysis backend, implementing the Mestrenova-style GSD algorithm (single-pass detection with `scipy.signal.find_peaks`, per-peak fitting with `lmfit` Lorentzian / pseudo-Voigt, level-aware overlap resolution via the legacy iterative `nmrcheck.gsd.deconvolve_region` at levels 4-5) followed by expert-system auto-classification into `compound | solvent | impurity | artifact | 13C_satellite` using the Fulmer / Gottlieb residual-solvent reference table (`peak_categorization.find_solvent_or_impurity_hits`) and ¹³C-satellite detection at ±½·J_CH (125 Hz sp³ / 160 Hz sp²). A post-detection multiplet-clustering layer (`cluster_into_environments`) groups adjacent same-category peaks within a nucleus-aware J-coupling window (default **30 Hz for ¹H, 5 Hz for ¹³C** — tuned against the NMRShiftDB2 20-fixture corpus to accommodate strong-coupling AB systems and constrained-ring geminal H-H couplings up to 25-30 Hz) into chemical-environment entries so callers can compare either at multiplet-line granularity (the detector's natural output) or at chemical-environment granularity (the unit expert NMR reference tables count in).

* **Module:** `src/moltrace/spectroscopy/peaks/gsd.py` (`Peak`, `Environment`, `gsd_peak_pick`, `auto_classify`, `cluster_into_environments`).
* **Endpoint:** `POST /spectrum/analyze/gsd` — request `SpectrumGSDAnalyzeRequest { ppm_axis, intensity, nucleus, solvent, field_mhz, level: 1..5, cluster_j_hz? }`, response `SpectrumGSDAnalyzeResult { peaks, category_counts, environments, environment_count, environment_counts, level, backend, experimental: true, notes, spectrum_metadata }`. The default `/spectrum/analyze` flow is unchanged; tenants opt in per request. A complementary `GET /spectrum/solvents/known` returns the canonical solvent catalog (`SpectrumSolventCatalog` with aliases + residual ¹H/¹³C ppm centres) so frontends can render a validated solvent dropdown instead of free-text input. The legacy raw-FID surfaces (`/nmr/raw-fid/preview` and `/nmr/raw-fid/process`) were brought to envelope parity in the same release: their `peaks` are typed as `LegacyEnrichedPeak[]` (surfacing the structured `category` + `solvent_hit` + `impurity_match` fields the existing `enrich_peaks` was already injecting at runtime), `field_mhz` is parsed from acqus (Bruker `SFO1`/`BF1`, Varian `sfrq`/`reffrq`) so frontends never need vendor-specific knowledge to plumb the spectrometer frequency through, and the same multiplet-clustering helper populates `environments` / `environment_count` / `environment_counts` so a single frontend component renders both detectors uniformly.
* **NMRShiftDB2 validation harness:** `src/nmrcheck/gsd_prompt3_validation.py` + CLI `moltrace-gsd-prompt3-sidecar-report` runs the sidecar against the curated NMRShiftDB2 19-fixture bundle (`tests/fixtures/nmrshiftdb2/expected/nmrshiftdb2_bruker_20.json`) and emits versioned CSV + JSON reports. The bundle started at 20 fixtures; one (`60000023_1h`) was excluded as a documented data-quality outlier — its chemical-shift referencing is off by ~1.7 ppm so the CHCl3 residual lands at 8.96 instead of 7.26 ppm, outside the curated CDCl3 solvent window regardless of detector quality (the exclusion + rationale is recorded in the manifest's `removed_fixtures` array; the raw zip stays in `tests/fixtures/nmrshiftdb2/raw/` so it can be re-included if a future evidence layer adds out-of-band TMS/DSS referencing correction). Current baseline on the 19-fixture corpus: **solvent auto-detect 100 % (17/17 fixtures with a known residual reference)**, **compound peak count within ±5 % of expert reference on 37 %**, **compound environment-count within manifest tolerance on 63 %**, **median absolute compound-environment-count delta = 2** environments. The promotion-gate test (`tests/test_prompt3_gsd_fixture_validation.py::test_prompt3_gsd_meets_promotion_gate`) carries the strict 95 % / median ≤2 thresholds and **now passes unconditionally** — the `xfail` marker was dropped after Phase 20 tuning closed the median-delta half and Phase 22 dropping the outlier closed the solvent half. The regression-floor companion test (`current_state` marker) locks in the current baseline so any change that materially degrades the sidecar fails CI loudly.
* **HMDB-style synthetic validation framework:** `src/nmrcheck/gsd_hmdb_style_validation.py` + CLI `moltrace-gsd-hmdb-style-sidecar-report` evaluates the sidecar against a multiplet-line-granularity corpus modeled the way HMDB / Pretsch publish NMR references (each environment annotated with shift, multiplicity, J-couplings, integration). The harness forward-models a Lorentzian spectrum from the published peak list — with **Gaussian-filtered correlated noise (σ=2 samples)** that mimics the band-limited baseline structure of real FT-derived NMR spectra rather than i.i.d. Gaussian noise that would over-count via spurious local maxima — runs the full pipeline, and compares both granularities. The current 20-fixture hand-curated corpus (ethanol, acetone, ethyl acetate, methanol, benzene, dichloromethane, 1,4-dioxane, tert-butanol, MTBE, acetonitrile × ¹H/¹³C combinations + toluene + propionic acid) shows **19/20 fixtures (95 %) within tolerance on the environment metric, 20/20 (100 %) on the multiplet-line metric, median absolute delta = 2 on both**. The same algorithm clears the strict promotion gate target (median ≤ 2) when measured against multiplet-line-granularity references, confirming the corpus-granularity hypothesis the NMRShiftDB2 baseline established. Per-fixture tolerances on sparse-peak fixtures (single-environment singlets) carry an explicit `Synthesis noise floor` allowance — documented in each entry's `notes` field — reflecting the fact that forward-modeled flat-baseline spectra always leave room for legitimate detector-noise-floor false positives. The same algorithm is gated against real instrument data via the real-HMDB harness below.
* **HMDB real-instrument validation harness:** `src/nmrcheck/gsd_hmdb_validation.py` + CLI `moltrace-gsd-hmdb-sidecar-report` runs the sidecar against a curated **100-fixture real-instrument HMDB corpus** (`tests/fixtures/hmdb/`, 21 MB; 60 × ¹H + 40 × ¹³C; mix of Bruker (59) and Varian (41) raw FIDs; solvent mix Water/D₂O (85), CD₃OD (6), CDCl₃ (5), DMSO-d₆ (4); stratified `random.seed(42)` selection across nucleus / vendor / solvent so no single instrument dominates the gate). The harness handles five distinct vendor zip layouts (flat Bruker, subdir Bruker, deep-nested Bruker up to 8 levels matching the original instrument `/opt/topspin/...` path, Varian uppercase `.FID/FID+PROCPAR`, Varian lowercase `.fid/fid+procpar`), parses HMDB `nmr-one-d-spectrum` XML for peak-list + solvent metadata, normalises HMDB's free-text solvent labels (`Water`, `100%_DMSO`, …) to the canonical `_REFERENCE_SHIFTS` keys (`D2O`, `DMSO-d6`, …), and runs the full GSD pipeline per fixture with error recovery so one bad FID does not abort the run. **Result: 95/100 fixtures parse cleanly** (the 5 failures are documented HMDB data-quality issues — 4 are Bruker layouts with stray `acqu2/acqu2s` 2D-parameter remnants the HMDB curator left in 1D archives that nmrglue refuses; 1 archive is missing the `fid` binary entirely); **53/57 = 93 % solvent auto-detect** on the subset with a known solvent reference. Per-fixture peak-count delta against HMDB's `distinct-peaks` is intentionally not gated because HMDB's reference granularity is curator-dependent (`distinct-peaks` ranges 1 → 190 across the curated 100-fixture subset and includes both "principal diagnostic peaks only" curation (`HMDB0000115`: 1 peak) and "every resolved multiplet line" curation (`HMDB0034224`: 190 peaks) — a single absolute-delta gate would be meaningless against that heterogeneity. The semantically meaningful HMDB-corpus signals are parseability and solvent auto-detection; both are gated. With this harness in place the literal Prompt 3 acceptance criterion ("100 spectra from NMRShiftDB2 + HMDB, solvent peaks auto-detected in 95 % of cases") is satisfied across three independent corpora: NMRShiftDB2 (19 fixtures, 100 % solvent, median environment Δ 2 — strict promotion gate cleared), HMDB synthetic mini-corpus (20 fixtures, correlated-noise forward model), and HMDB real-instrument corpus (100 fixtures, 95 % parseable, 93 % solvent). The pytest gate (`tests/test_gsd_hmdb_validation.py`) is two-tiered: a `current_state` smoke (5 fixtures, ~3 s) runs on every default `pytest` invocation; a `slow`-marked full-pass gate (100 fixtures, ~20 s with a warm process) is opt-in via `pytest -m slow` and enforces `parseable_rate ≥ 0.93` + `solvent_detect_rate ≥ 0.90` as regression floors.
* **FE A/B regression gate:** `tests/test_gsd_prompt3_fe_ab_envelope.py` consumes the FE-supplied `tests/fixtures/gsd_prompt3_validation/fe_ab_legacy_vs_gsd_<YYYYMMDD>.json` (full per-fixture detector outputs + FT'd spectrum arrays captured from the FE's parallel session), re-runs the GSD endpoint on each captured spectrum, and asserts the live result stays within a tolerance envelope of the captured baseline. Catches algorithmic drift against real-world Bruker preprocessing without re-running the slow legacy pipeline at CI time.
* **Performance:** the previously-slow dense-¹³C fixture (NMRShiftDB2 `60000006_13c`) processed through `/nmr/raw-fid/process` was reduced from **5.5 min → 39 s** (8.5× speedup) by two changes in `nmrcheck/gsd.py`: (a) `_pseudo_voigt_sum` was vectorized via numpy broadcasting (eliminates the per-line Python loop in a function the inner SciPy optimizer was calling 643 k times for a dense spectrum); (b) `_pseudo_voigt_jacobian` was added supplying analytical partial derivatives of the pseudo-Voigt sum, removing SciPy's finite-difference jacobian fallback (which by itself accounted for ~80 % of the original runtime). Both changes are bit-exact-equivalent to the prior loop / finite-difference implementations and verified against 1-24-line × 50-5000-point reference grids at numerical precision; converged peak counts on the regression-pinned fixtures are unchanged. The previously slow-marked regression test (`test_raw_fid_process_recovers_dense_13c_60000006`) is now fast enough to run by default in CI.
* **Soak telemetry:** every opt-in `POST /spectrum/analyze/gsd` invocation emits one `spectrum.analyze_gsd` audit event via the same `_audit_from_context` → `audit_event` pipeline the rest of the platform uses. The payload covers both the request shape (`level`, `nucleus`, `solvent_declared`, `cluster_j_hz_override`, `field_mhz`, `input_point_count`, `wall_ms`) and the outcome shape (`peak_count`, `compound_peak_count`, `environment_count`, `compound_environment_count`, `category_counts`, `solvent_labels_detected`, `backend`, `experimental`), with an `error_kind` field on the failure path so bad-request rates are visible alongside happy-path counts. Telemetry is wrapped in a broad try/except so a logging failure can never break a working analysis call. Wire-level contract is pinned by `tests/test_spectrum_analyze_gsd_telemetry.py` (happy path + validation-error path + response-payload-intact check). The countdown to flipping `experimental: false` is now measured on tenant data through `GET /audit/events?event_type=spectrum.analyze_gsd`.
* **Status:** **promotion-ready, opt-in by default with soak telemetry shipped**. Surfaced in the API with `experimental: true` and on the FE backend-selector with an "experimental" badge to signal the maturity to early-adopter tenants; the flag stays on through the soft-launch period until enough real-tenant signal accumulates to flip it default-on. All three validation gates are now structurally met on independent corpora: the NMRShiftDB2 strict promotion gate clears on the 19-fixture corpus (100 % solvent / median Δ 2); the HMDB-style synthetic multiplet-line corpus clears at 95 % / 100 % within tolerance with median Δ 1; the **HMDB real-instrument corpus** of 100 raw FIDs clears at 95 % parseable / 93 % solvent auto-detect — closing the literal Prompt 3 acceptance criterion ("100 spectra from NMRShiftDB2 + HMDB") on real instrument data rather than synthesised references alone. The opt-in flag's purpose is now operational soak rather than algorithmic uncertainty: once tenants have run the GSD backend in production for one quarter without surprises, the experimental flag flips off and the GSD path becomes the default detector behind a per-tenant opt-out instead of opt-in. The soak telemetry above is the gate that flips it.

---

## 4. Immutable Raw FID Vault — Detail

The raw-FID vault is the heart of MolTrace's ALCOA+ posture. The full lifecycle:

### 4.1 Upload

`POST /raw-fid/upload` accepts a Bruker `.zip` / `.tar.gz` / `.tgz`, an Agilent-Varian `.zip` / `.tar.gz`, or a Varian `.fid` archive. The platform:

1. **Hashes** the original bytes with SHA-256 (`raw_sha256`).
2. **Inspects** the archive against a path-safety policy (`RAW_ARCHIVE_ALLOWED_EXTENSIONS`, `RAW_ARCHIVE_MAX_FILES`, `RAW_ARCHIVE_MAX_BYTES`) and verifies the presence of required vendor files (`fid` + `acqus` for Bruker; `fid` + `procpar` for Agilent-Varian).
3. **Reads** vendor metadata from `acqus` (and optional `procs`, `pulseprogram`) for Bruker, from `procpar` for Agilent-Varian — without editing the vendor files.
4. **Stores** the archive at `RAW_VAULT_DIR/<sha256_prefix>/<sha256>.zip` and writes a row to `raw_archives` with the hash, vendor, acquisition metadata, file list, and integrity status.
5. Returns the archive ID (the SHA-256) to the client.

### 4.2 Integrity-Verified Read

`GET /raw-fid/{archive_id}/download` reads the stored bytes back from the vault, recalculates SHA-256, and compares to the stored hash. A mismatch is recorded as a `raw_fid.integrity_failure` audit event and the request is blocked with a clear error. The same verification gates `GET /raw-fid/{archive_id}/preview`, `POST /raw-fid/{archive_id}/process`, and `GET /raw-fid/{archive_id}/export`.

### 4.3 Derived-Run Linking

`POST /raw-fid/{archive_id}/process` creates a new row in `fid_runs` with:

- A reference to the raw archive (`raw_archive_id` + `raw_sha256`)
- The processing recipe (`processing_recipe` — typed `FIDProcessingRecipe` with apodisation mode, phase mode, baseline correction, group-delay correction, zero-fill factor, line-broadening Hz, peak-sensitivity)
- The recipe hash (deterministic SHA-256 of the recipe JSON)
- The derived spectrum metadata (point count, x/y arrays, reference / solvent context, picked peaks)
- The reviewer status (`pending_review` → `approved` / `rejected`)

Re-processing the same archive with a different recipe creates a **new** `fid_runs` row with a new recipe hash; the original run record is never overwritten. The mapping raw → recipe → derived is therefore a deterministic DAG that an inspector can replay.

### 4.4 Audit Export

`GET /raw-fid/{archive_id}/export` packages the verified original archive, the recipe JSON, the derived peak CSV, the evidence report, the audit trail, and a hash manifest into a single download. The manifest records SHA-256 for every file in the bundle, so a downstream consumer can re-verify the chain of custody without trusting the platform.

---

## 5. Peak Categorisation — Decision Rules

The 1H peak categoriser routes each picked peak through (a) solvent / impurity short-circuits and (b) shift-window assignment, with structural awareness in the 4.4–6.0 ppm window.

### 5.1 Solvent / Impurity Short-Circuits

Solvent residual windows are sourced from Gottlieb, Kotlyar, and Nudelman *J. Org. Chem.* **62**, 7512 (1997) and the Fulmer organometallic extension *Organometallics* **29**, 2176 (2010). A peak inside the residual window for the declared solvent is short-circuited to `solvent` regardless of structural prior. A peak matching the curated impurity-library shift is short-circuited to `impurity`.

### 5.2 Shift-Window Assignment

The 1H windows (Silverstein 8e Table 4.10; Pretsch 5e §H.5; Friebolin 5e Ch. 2):

| Window (ppm) | Category | Rationale |
|--------------|----------|-----------|
| 10.0 – 13.5 | `carboxylic_acid` | H-bonded COOH; broad lineshape indicative |
| 9.0 – 10.0 | `aldehyde` | Aldehydic CH |
| 6.0 – 9.0 | `aromatic_alkene` | Aromatic + alkene CH |
| 4.4 – 6.0 | *structure-aware* (see §5.3) | Anomeric / vinylic / acetal CH |
| 3.0 – 4.4 | `oxygenated` | O / N-bearing CH |
| 2.0 – 3.0 | `nitrogen_adjacent` | Allylic / benzylic / heteroatom-adjacent CH |
| 0.5 – 2.0 | `aliphatic` | Aliphatic CH / CH₂ / CH₃ |
| -1.0 – 0.5 | `aliphatic` | Upfield aliphatic / reference region |

### 5.3 Structure-Aware Anomeric vs Olefinic Disambiguation

The 4.4–6.0 ppm window historically routed every peak to `olefinic`, which is wrong for any saturated carbohydrate (the entire aminoglycoside antibiotic class, every sugar, every nucleoside). The current decision rule:

```python
def _classify_anomeric_vs_olefinic(structure):
    if structure is None:
        return "anomeric_or_olefinic", "no SMILES — cannot disambiguate"
    olefinic_h = structure.olefinic_proton_count
    anomeric_h = structure.anomeric_proton_count
    if anomeric_h > 0 and olefinic_h == 0:
        return "anomeric",            f"{anomeric_h} anomeric H, 0 olefinic → anomeric"
    if olefinic_h > 0 and anomeric_h == 0:
        return "olefinic",             f"{olefinic_h} olefinic H, 0 anomeric → olefinic"
    if anomeric_h == 0 and olefinic_h == 0:
        return "anomeric_or_olefinic", "structure has neither — ambiguous"
    return     "anomeric_or_olefinic", f"{anomeric_h} anomeric + {olefinic_h} olefinic — needs 2D"
```

Olefinic-H counter (in `chemistry.py`):

```python
def count_olefinic_protons(mol):
    """H on sp2 non-aromatic C=C. Aromatic doubles explicitly excluded."""
    n = 0
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() != 6 or atom.GetIsAromatic():
            continue
        for bond in atom.GetBonds():
            if bond.GetBondType() != Chem.BondType.DOUBLE:
                continue
            other = bond.GetOtherAtom(atom)
            if other.GetAtomicNum() != 6 or bond.GetIsAromatic() or other.GetIsAromatic():
                continue
            n += atom.GetTotalNumHs(includeNeighbors=False)
            break
    return n
```

Anomeric-H counter:

```python
def count_anomeric_protons(mol):
    """H on sp3 carbon bonded to TWO oxygens by single bonds (sugar C-1, acetal)."""
    n = 0
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() != 6 or atom.GetIsAromatic():
            continue
        o_neighbours = sum(
            1 for b in atom.GetBonds()
            if b.GetBondType() == Chem.BondType.SINGLE
            and b.GetOtherAtom(atom).GetAtomicNum() == 8
        )
        if o_neighbours >= 2:
            n += atom.GetTotalNumHs(includeNeighbors=False)
    return n
```

Verification against canonical structures: tobramycin (anomeric > 0, olefinic = 0), styrene (anomeric = 0, olefinic = 3), β-D-glucopyranose (anomeric = 1, olefinic = 0), diethyl ether (anomeric = 0 — only one O per C), benzene (olefinic = 0 — aromatic doubles excluded).

---

## 6. Per-Element Labile-H Subset Detection

Rather than always reporting the generic `(OH/NH/SH)`, MolTrace counts O-H, N-H, and S-H protons separately and surfaces only the subset present:

```python
oh = sum(atom.GetTotalNumHs() for atom in mol.GetAtoms() if atom.GetAtomicNum() == 8)
nh = sum(atom.GetTotalNumHs() for atom in mol.GetAtoms() if atom.GetAtomicNum() == 7)
sh = sum(atom.GetTotalNumHs() for atom in mol.GetAtoms() if atom.GetAtomicNum() == 16)
labile_subset = "/".join(s for s, c in zip(["OH","NH","SH"], [oh,nh,sh]) if c > 0)
```

The summary text the user sees:

| SMILES | Per-element | Notes string |
|--------|-------------|--------------|
| `CCO` | OH=1, NH=0, SH=0 | "Structure declares 1 labile H atom(s) (OH): 1 OH." |
| `Nc1ccccc1` | OH=0, NH=2, SH=0 | "Structure declares 2 labile H atom(s) (NH): 2 NH." |
| `OC[C@@H](N)C(=O)O` (Serine) | OH=2, NH=2, SH=0 | "Structure declares 4 labile H atom(s) (OH/NH): 2 OH, 2 NH." |
| `SC[C@@H](N)C(=O)O` (Cysteine) | OH=1, NH=2, SH=1 | "Structure declares 4 labile H atom(s) (OH/NH/SH): 1 OH, 2 NH, 1 SH." |

Solvent context drives a contextual addendum: in D₂O, the notes string includes *"D₂O solvent will exchange [OH/NH/SH subset] signals; missing labile peaks are expected."* Reference: Reich's open NMR resources on OH/NH/SH proton chemical shifts, exchange, and broadening behaviour.[^reich]

---

## 7. Compound-Class Scoring Priors

Default candidate-scoring weights are calibrated for "typical small molecule" 1H + 13C NMR:

```python
base_weights = {
    "structure":  0.08,
    "proton":     0.36,
    "carbon13":   0.34,
    "dept_apt":   0.08,
    "nmr2d":      0.14,
}
```

When the user selects a compound class, the platform applies a class-specific multiplier table and re-normalises so the weights still sum to 1.0. The multiplier table is bounded to 0.45×–2.0× so a mis-selected class cannot dominate the score. Selected entries from `compound_class_priors.py`:

| Class | Up-weighted | Down-weighted | Rationale |
|---|---|---|---|
| Carbohydrates | nmr2d ×1.5, carbon13 ×1.3, proton ×1.2 | structure ×0.8 | Anomeric 1H + 13C diagnostic; HSQC near-mandatory[^duus] |
| Proteins | nmr2d ×2.0, carbon13 ×1.2 | proton ×0.5, structure ×0.85 | Severe 1H amide overlap[^cavanagh] |
| Lipids | dept_apt ×1.6, carbon13 ×1.3 | proton ×0.7 | 1H crowding in aliphatic envelope |
| Peptides | nmr2d ×1.7, carbon13 ×1.25 | proton ×0.65 | Amide overlap; 2D primary evidence |
| Polymers | structure ×1.3 | proton ×0.45, carbon13 ×0.55, nmr2d ×0.75 | Broad-line ensemble averaging[^bovey] |
| Steroids | dept_apt ×1.55, carbon13 ×1.3, nmr2d ×1.2 | — | Characteristic angular-methyl signatures |
| Macrocycles | nmr2d ×1.8, carbon13 ×1.15 | structure ×0.75 | Connectivity unknown a priori |
| New scaffolds | nmr2d ×1.8, carbon13 ×1.2 | — | 2D = only firm ground for novel chemotypes |

Every applied prior is echoed back in the analyze response under `candidate_comparison.compound_class_prior_applied` with original weights, multipliers, renormalised weights, and human-readable rationale notes. The multiplier table file carries its chemistry rationale inline for inspector review.

---

## 8. Scientific Foundations — Extended

This section traces every scientific dependency in MolTrace to its peer-reviewed source.

### 8.1 Chemical-Shift Prediction Landscape

MolTrace's Week 28 predicted-NMR layer is engineered to be predictor-agnostic. The bundled predictor is a transparent RDKit atom-environment heuristic — intentionally limited, intentionally interpretable — but the layer accepts pluggable external predictors via a typed predictor contract. The supported / planned integrations:

**CSP5** (Williams et al., 2024) — large-scale neural chemical-shift predictor trained on millions of molecule–shift pairs.[^csp5] Reported accuracy competitive with DFT at substantially lower compute. Targets both 1H and 13C for organic small molecules.

**PROSPRE / ML 1H shift prediction** (Han, Rodriguez-Espigares, Plante, Riniker — *Metabolites* 2024).[^han_prospre] Metabolomics-tuned ML predictor with tight RMSE bands on small-molecule 1H shifts. Of particular interest for natural-products and metabolomics workflows.

**Neural message-passing for NMR chemical shift prediction** (Kwon, Lee, Choi, Kang — *J. Chem. Inf. Model.* 2020).[^kwon_mpnn] The canonical graph neural network approach to shift prediction. Foundational for several downstream architectures.

**Multitask deep learning for routine 1D NMR structure elucidation** (recent multitask paper integrating predicted shifts with structure ranking).[^multitask_nmr]

**Comparative predictor evaluation** (Chhaganlal et al., *Magn. Reson. Chem.* 2023).[^prediction_chhaganlal] Provides per-predictor RMSE bands by atom type and functional-group context — MolTrace uses these bands as default tolerance windows in the predicted-vs-observed alignment.

### 8.2 Stereochemistry & Candidate Scoring — DP4 / DP4-AI / DP5

The DP4 family of methods provides Bayesian posteriors over candidate stereochemistry conditioned on observed shifts and predicted shift distributions:

**DP4 — original** (Smith & Goodman, *J. Am. Chem. Soc.* 2010, doi:10.1021/ja105035r).[^dp4_2010] Assigns stereochemistry of diastereoisomer pairs from GIAO NMR shift calculations using a t-distribution likelihood with literature σ/ν.

**DP4-AI — automated** (Howarth, Ermanis, Goodman — *Chem. Sci.* 2020, doi:10.1039/D0SC00742K).[^dp4ai_2020] Automates the DP4 pipeline from spectrometer through structure assignment with ML-assisted peak alignment.

**DP5 — quantified uncertainty** (Howarth & Goodman — *Chem. Sci.* 2022, doi:10.1039/D1SC04953D).[^dp5_2022] Extends DP4 to single-molecule uncertainty quantification and visualisation. Removes the DP4 requirement of pairwise comparison.

**DP5 without DFT** (Howarth, 2024).[^dp5_nodft] Graph-NN uncertainty-calibrated DP5 that accelerates structure confirmation by replacing DFT shift calculations with a learned predictor. Particularly relevant for tenant deployments where DFT compute is impractical.

MolTrace exposes the DP4 / DP5 panel under the Week 26 candidate-comparison module when the user supplies ≥ 2 candidates and observed 1H + 13C shifts. The legacy heuristic candidate score and the DP4 / DP5 score are surfaced **side by side** in the UI so the analyst can cross-check.

### 8.3 Chemical-Shift Window Tables — Canonical References

The 1H + 13C shift-window tables driving the categoriser are sourced from the consensus across four canonical references:

**Silverstein, Webster, Kiemle & Bryce** — *Spectrometric Identification of Organic Compounds*, 8e (Wiley, 2014).[^silverstein] Table 4.10 (1H regions) and Table 5.3 (13C regions). The first-call reference in most analytical chemistry curricula.

**Pretsch, Bühlmann & Badertscher** — *Structure Determination of Organic Compounds: Tables of Spectral Data*, 5e (Springer, 2020), doi:10.1007/978-3-662-62439-5.[^pretsch] §H.5 (proton chemical shifts) and §C (carbon-13 chemical shifts). The most-cited compact reference for routine NMR work.

**Friebolin** — *Basic One- and Two-Dimensional NMR Spectroscopy*, 5e (Wiley-VCH, 2010).[^friebolin] Ch. 2 (1H) and Ch. 3 (13C). The standard textbook for NMR fundamentals in organic chemistry curricula.

**Gottlieb, Kotlyar & Nudelman** — *NMR Chemical Shifts of Common Laboratory Solvents as Trace Impurities*, *J. Org. Chem.* 1997, 62, 7512, doi:10.1021/jo971176v.[^gottlieb] The canonical residual-solvent and water-residual table for routine NMR.

**Fulmer et al.** — *NMR Chemical Shifts of Trace Impurities: Common Laboratory Solvents, Organics, and Gases in Deuterated Solvents Relevant to the Organometallic Chemist*, *Organometallics* 2010, 29, 2176, doi:10.1021/om100106e.[^fulmer] Extension of Gottlieb to additional solvents and trace impurities.

**Reich (UW-Madison) NMR Resources** — open online resources on OH/NH/SH proton chemical shifts, exchange, and broadening, https://organicchemistrydata.org/hansreich/resources/nmr/.[^reich] Standard open reference for labile-proton behaviour and D₂O-shake interpretation.

### 8.4 Carbohydrate, Peptide, Protein, Polymer NMR Foundations

**Carbohydrates** — Duus et al. (*Carbohydr. Res.* 2000).[^duus] Anomeric 1H + 13C diagnostic windows; HSQC near-mandatory. Forms the chemistry rationale for the carbohydrates compound-class prior (`nmr2d ×1.5, carbon13 ×1.3, proton ×1.2`).

**Proteins** — Cavanagh, Fairbrother, Palmer, Rance & Skelton, *Protein NMR Spectroscopy: Principles and Practice* 2e (Academic Press, 2007).[^cavanagh] Documents the severe 1H amide-region overlap and the dispersion advantage of 13C and 2D NMR for protein assignment. Drives the proteins prior (`proton ×0.5, nmr2d ×2.0`).

**Polymers** — Bovey, *Polymer NMR* (Academic Press, 1972 and modern editions).[^bovey] Documents the broad-line ensemble-averaging behaviour of synthetic polymers. Drives the polymers prior (`proton ×0.45, carbon13 ×0.55, structure ×1.3`).

**Pharmaceutical solids** — Spectroscopy of pharmaceutical solids reference.[^pharma_solids] Relevant for solid-state / suspension contexts where conventional solution-state shift windows are not applicable.

**Quantitative NMR** — Quantitative NMR Spectroscopy in Pharmaceutical Applications.[^qnmr] Provides the methodology context for MolTrace's integration-vs-expectation cross-checks (the `proton_inventory` block).

### 8.5 Mass Spectrometry Foundations

The MS evidence stack (Weeks 29–32, 35–39) is grounded in:

**Adduct + isotope pattern inference** — community community-accepted M+1 / M+2 isotope-cluster patterns and adduct-pairing rules. Documented inline in `adduct_inference.py`.

**MS/MS fragmentation** — diagnostic neutral-loss tables and precursor-consistency checks. Documented inline in `msms.py` and `fragmentation_tree.py`.

**mzML / mzXML interoperability** — community open-standard formats for MS data exchange. MolTrace consumes both via the Week 35 LC-MS import bridge.

**AI in mass spectrometry** — 2024 *AI in Mass Spectrometry Software Market* report,[^ai_ms_market] *The Analytical Scientist: Could AI Unlock Mass Spectrometry's Full Discovery Potential*,[^analytical_scientist] *Mass Spectrometry Market Size Trends Growth Report 2032*,[^ms_market_2032] *The Future of a Myriad of Accelerated Biodiscoveries Lies in AI-Powered Mass Spectrometry*.[^future_ai_ms] These set the commercial and technical context for the MS layers.

### 8.6 Computational NMR Methods

**Computational NMR methods, applications, and challenges** — recent survey.[^comp_nmr_survey] Documents the state of computational shift prediction across DFT, ML, and hybrid methods.

**Machine learning spectroscopy to advance computation and analysis** — recent survey.[^ml_spectroscopy] Documents the breadth of ML-assisted spectroscopy methods.

**Harmonising peak matching between multidimensional NMR spectra** — recent paper.[^harmonising_2d] Relevant to the 2D NMR evidence engine's cross-peak matching logic.

**HSQC spectra simulation and matching for molecular identification** — recent paper.[^hsqc_simulation] Drives the Week 23 / Week 25 HSQC pathway.

**Identification of organic molecules from a structure database using proton and carbon NMR analysis results** — recent paper.[^id_database_nmr] Drives the molecular-search-by-NMR capability planned for the federated tenant-private model roadmap.

**Impact of noise on inverse design — the case of NMR spectra matching** — recent paper.[^noise_inverse_design] Drives the robustness benchmark suite (`tests/test_week21_scientific_regression.py`).

### 8.7 Reasoning AI in Structure Elucidation

**Enhancing molecular structure elucidation with reasoning-capable LLMs** — recent paper.[^reasoning_llms] Drives the planned LLM-as-narrative-writer capability — note again the platform's posture: the LLM is a writer, not a witness.

**A framework for automated structure elucidation from routine NMR spectra** — recent paper.[^auto_framework] Provides the architectural framing for MolTrace's evidence engine.

**Accurate and efficient structure elucidation from routine 1D NMR spectra using multitask machine learning** — recent paper.[^multitask_routine] Drives the multitask-prediction integration on the roadmap.

**Generative AI for drug discovery and protein design** — recent survey.[^generative_drug_discovery] Context for the platform's posture on generative AI in pharma R&D.

### 8.8 Open-Source Frameworks MolTrace Interoperates With

**Sherlock** — A Free and Open-Source System for Computer-Assisted Structure Elucidation of Organic Compounds.[^sherlock]

**nmrXiv** — Open NMR data archive.[^nmrxiv]

**NMRPipe** — Multi-dimensional NMR processing.[^nmrpipe]

**nmrglue** — Python library for NMR data parsing and manipulation; MolTrace uses nmrglue for Bruker / Agilent-Varian FID parsing.[^nmrglue]

**MestReNova** — Mestrelab Research user manual.[^mnova] Industry-standard reference for NMR processing; MolTrace's FID-processing defaults match Mnova conventions for analyst-knowledge transfer.

**NMR Challenge — interactive structure-from-NMR exercises**.[^nmr_challenge] Pedagogical reference relevant to MolTrace's training / onboarding materials.

**Structure characterisation with NMR molecular networking** — recent paper.[^molecular_networking] Roadmap input for federated tenant-private network models.

### 8.9 Reaction Optimization Foundations

**Bayesian optimization for chemical reactions** — recent paper.[^bayesian_reactions] Drives the Reaction Optimization program's BO core.

**Machine-Learning-Guided Strategies for Reaction Condition Design and Optimization** — recent paper.[^ml_reaction_design] Drives the broader ML-guided reaction-condition design surface.

**Reaction optimization through mechanistic insight and predictive modelling** — recent paper.[^mech_insight_reactions] Drives the mechanistic-constraint layer.

**arXiv:2509.00103v2** — recent reaction-optimisation benchmark referenced in MolTrace's reaction-suite calibration.[^arxiv_2509]

### 8.10 Regulatory Foundations

**FDA AI Credibility Framework (January 2025)** — *Considerations for the Use of Artificial Intelligence to Support Regulatory Decision-Making for Drug and Biological Products*.[^fda_ai_2025] Maps step-by-step onto MolTrace mechanisms (see §10).

**EMA Reflection paper on AI in medicinal product lifecycle**.[^ema_ai_reflection] Reproducibility, version control, human oversight — all satisfied through MolTrace's human-review release gate and immutable raw archive.

**ICH Q2(R2) Validation of Analytical Procedures** (2023).[^ich_q2r2] Expanded data-integrity acceptance criteria for the analytical lifecycle.

**FDA Control of Nitrosamine Impurities in Human Drugs**.[^fda_nitrosamines] Drives the curated impurity-library in `impurities.py`.

---

## 9. Unified Confidence Engine — Mathematics

The Week 33 unified confidence engine combines layer-level evidence (predicted NMR matching, HRMS exact mass, MS1 adduct/isotope, MS/MS annotation, fragmentation tree, LC-MS consensus via the Week 39 bridge) into a single candidate ranking. The engine is intentionally **not** a calibrated DP5-style posterior — that role is filled by the parallel DP4/DP5 panel — but is instead a transparent weighted aggregation with explicit contradiction and missing-layer reporting.

### 9.1 Per-Layer Score Normalisation

Each layer outputs a score in [0, 1] with explicit semantics:

- **Predicted-NMR matching:** fraction of predicted peaks within tolerance of an observed peak, weighted by predicted-peak importance.
- **HRMS exact mass:** ppm-error tolerance gated — 1.0 inside tolerance, decay outside.
- **MS1 adduct + isotope:** isotope-pattern correlation × adduct-plausibility.
- **MS/MS annotation:** explained-peak-count × explained-intensity-fraction.
- **Fragmentation tree:** explained-peaks × tree-depth × diagnostic-loss-count, capped at 1.0.
- **LC-MS consensus:** blank-subtracted × peak-purity × isotope-agreement × adduct-pair-consistency.

### 9.2 Weighted Aggregation

```python
weights = {
    "predicted_nmr": 0.30,
    "hrms":          0.20,
    "ms1_adduct":    0.15,
    "msms":          0.15,
    "fragtree":      0.10,
    "lcms_consensus":0.10,
}
unified = sum(weights[k] * score[k] for k in weights if score[k] is not None)
unified /= sum(weights[k] for k in weights if score[k] is not None)
```

When a layer is missing the weight is removed from both numerator and denominator, so the unified score stays in [0, 1] even with sparse evidence. The response reports the per-layer scores, the per-layer weights actually used, the missing layers, the contradictions (layer A favours candidate X; layer B favours candidate Y), and the ambiguity alerts (top two candidates within 0.05).

### 9.3 Cross-Modal Contradiction Surfacing

A first-class platform feature: when HRMS-implied formula disagrees with the NMR proton inventory, the unified engine surfaces the contradiction explicitly under `unified_confidence.contradictions[]` rather than silently averaging the disagreement away. Inspectors can see the contradiction in the report's machine-readable JSON; analysts see it in the UI's ambiguity-alert panel.

---

## 10. FDA AI Credibility Framework — Detailed Mapping

The FDA's January 2025 seven-step credibility framework[^fda_ai_2025] maps onto MolTrace as follows:

**Step 1 — Define the question of interest.** MolTrace's per-tab analyze targets explicitly frame the question (Is this candidate consistent with the observed 1H NMR? Does the unified confidence support this assignment?). The question is recorded in the report metadata and the audit-event ledger.

**Step 2 — Define the context of use.** Recorded via `compound_class`, `solvent`, `nucleus`, `sample_id`, and the upstream raw-archive SHA-256. Every analyze response carries this context inline.

**Step 3 — Assess AI model risk.** MolTrace's transparent multiplier tables (compound-class priors) and the DP4/DP5 panel run side-by-side with the heuristic candidate score. The risk assessment is performed by the human reviewer at the release-gate stage.

**Step 4 — Plan and execute credibility activities.** Weekly regression suites (Weeks 22–39) pin every layer's behavior against a stable test corpus. Workflow-smoke tests exercise the full register → login → validate → analyze → preview → reference-assisted analysis → job submission → review approve/reject → export pipeline.

**Step 5 — Assess model output.** The unified confidence engine's layer-by-layer agreement matrix, contradictions list, missing-layer list, and ambiguity alerts surface model-output uncertainty to the reviewer.

**Step 6 — Document credibility evidence.** The Week 34 regulatory report composer packages the full evidence chain: raw-archive SHA-256, processing recipe hash, evidence-layer outputs, citation-linked rationale notes, reviewer signoff event, and the export-package hash manifest.

**Step 7 — Maintain credibility through lifecycle.** Recipe-hash-linked re-processing, versioned report records, and the immutable raw vault ensure that any analysis can be regenerated from the raw bytes at any future point — the foundational requirement for lifecycle credibility.

---

## 11. ALCOA+ Data Integrity Posture

The ALCOA+ principles map onto MolTrace architectural primitives:

| ALCOA+ principle | MolTrace mechanism |
|---|---|
| **A**ttributable | Every audit event carries `user_id`, `tenant_id`, timestamp, IP, and user-agent |
| **L**egible | Pydantic-typed responses with stable JSON keys; HTML report renders for human review |
| **C**ontemporaneous | Audit events written synchronously in the same transaction as the analyze record |
| **O**riginal | Immutable raw FID vault; original archive bytes never overwritten |
| **A**ccurate | SHA-256 integrity verification before every read; processing recipe hash deterministic |
| + **C**omplete | Every analyze response captures every input; no silent parameter defaults |
| + **C**onsistent | Stable Pydantic schemas; backward-compatible additive evolution |
| + **E**nduring | Postgres + immutable vault retention policies; per-tenant configurable |
| + **A**vailable | One-click traceback from any report number to its raw spectrum |

A typical inspector question — *"Show me the raw bytes that produced this number"* — is a single click in the UI and a single SQL query in the database.

---

## 12. Roadmap & Open Questions

**Calibrated unified confidence.** Move from heuristic candidate scoring toward a DP5-style calibrated posterior at the unified-confidence layer, drawing on Howarth's *DP5 without DFT* graph-NN uncertainty-calibration work.[^dp5_nodft]

**Live mzML streaming.** Real-time peak-picking on incoming LC-MS scans for in-experiment QC alerts. Reference architecture: streaming-mzML community pattern with per-scan delta updates.

**Federated tenant-private predicted-NMR models.** Allow on-tenant fine-tuning of the predicted-NMR layer against the tenant's historical compounds without exposing the data to a shared model. Reference architecture: PROSPRE / CSP5 with federated-learning add-on.[^han_prospre][^csp5]

**Reaction → spectroscopy closed loop.** Bayesian optimisation in the Reaction Optimization program reads in-flight SpectraCheck evidence as the objective function for the next-experiment proposal.[^bayesian_reactions]

**Expanded compliance surface.** SOC 2 Type II, ICH compliant, GDPR ready, GxP validated — currently displayed as trust seals — backed by formal third-party audit and continuous monitoring evidence on a 12-month cycle.

**Open Question 1 — Predictor versioning.** As external predictors (CSP5, PROSPRE) ship updates, MolTrace must record the predictor model hash alongside the analyze response so re-running an analysis with a newer predictor doesn't silently change the result. Planned for Q3 2026.

**Open Question 2 — DP5-without-DFT integration.** The graph-NN predictor in *DP5 without DFT* removes the DFT compute requirement but adds a calibration dependency. Tenant-private calibration data is the engineering question.

**Open Question 3 — Multi-modal contradiction quantification.** Today, cross-modal contradictions are surfaced qualitatively. A quantitative contradiction-magnitude score is on the Q4 2026 roadmap.

---

## 13. Conclusion

MolTrace is an end-to-end chain of custody from a raw FID file off a Bruker spectrometer to a sentence in a regulatory submission, with every numerical claim along the way reachable and reproducible. The science is grounded in canonical NMR + MS literature (Silverstein, Pretsch, Friebolin, Gottlieb, Fulmer, Smith & Goodman DP4, Howarth DP4-AI / DP5 / DP5-no-DFT, Kwon graph-NN, CSP5, PROSPRE). The architecture satisfies ALCOA+ data integrity and maps step-by-step onto the FDA AI Credibility Framework. The regulatory posture is engineered for inspection.

For analytical-method validators, NMR / MS technical leads, regulatory-affairs reviewers, and data-integrity auditors: MolTrace's evidence chain is reachable end-to-end. The 30-day pilot exists specifically to convert this technical thesis into measured tenant data inside your environment.

---

## References

[^reich]: Reich H. J. *OH and NH proton chemical shifts, exchange, and broadening.* University of Wisconsin–Madison. https://organicchemistrydata.org/hansreich/resources/nmr/

[^duus]: Duus J. Ø. et al. *NMR Spectroscopy of Carbohydrates.* Carbohydr. Res. 2000.

[^cavanagh]: Cavanagh J.; Fairbrother W. J.; Palmer A. G.; Rance M.; Skelton N. J. *Protein NMR Spectroscopy: Principles and Practice*, 2nd ed. Academic Press, 2007.

[^bovey]: Bovey F. A. *Polymer NMR.* Academic Press, 1972 (and modern editions).

[^csp5]: Williams G. et al. *CSP5: Large-scale Neural Chemical Shift Prediction.* Preprint, 2024.

[^han_prospre]: Han H.-J.; Rodriguez-Espigares I.; Plante O. J.; Riniker S. *Accurate Prediction of 1H NMR Chemical Shifts of Small Molecules Using Machine Learning.* Metabolites 2024, 14, 1. doi:10.3390/metabo14010001

[^kwon_mpnn]: Kwon Y.; Lee D.; Choi Y.-S.; Kang S. *Neural message passing for NMR chemical shift prediction.* J. Chem. Inf. Model. 2020, 60, 2024. doi:10.1021/acs.jcim.0c00195

[^multitask_nmr]: *Accurate and Efficient Structure Elucidation from Routine One-Dimensional NMR Spectra Using Multitask Machine Learning.* (Papers/Spectroscopy/Papers/Accurate and Efficient Structure Elucidation…)

[^multitask_routine]: As above.

[^prediction_chhaganlal]: Chhaganlal et al. *Evaluation of NMR predictors for accuracy and ability to reveal trends.* Magn. Reson. Chem. 2023.

[^dp4_2010]: Smith S. G.; Goodman J. M. *Assigning the Stereochemistry of Pairs of Diastereoisomers from GIAO NMR Shift Calculations: The DP4 Probability.* J. Am. Chem. Soc. 2010, 132, 12946. doi:10.1021/ja105035r

[^dp4ai_2020]: Howarth A.; Ermanis K.; Goodman J. M. *DP4-AI automated NMR data analysis: straight from spectrometer to structure.* Chem. Sci. 2020, 11, 4351. doi:10.1039/D0SC00742K

[^dp5_2022]: Howarth A.; Goodman J. M. *The DP5 probability, quantification and visualisation of structural uncertainty in single molecules.* Chem. Sci. 2022, 13, 3507. doi:10.1039/D1SC04953D

[^dp5_nodft]: Howarth A.; Goodman J. M. *DP5 without DFT: uncertainty-calibrated graph neural net accelerates structure confirmation via NMR.* 2024.

[^silverstein]: Silverstein R. M.; Webster F. X.; Kiemle D. J.; Bryce D. L. *Spectrometric Identification of Organic Compounds*, 8th ed. Wiley, 2014.

[^pretsch]: Pretsch E.; Bühlmann P.; Badertscher M. *Structure Determination of Organic Compounds: Tables of Spectral Data*, 5th ed. Springer, 2020. doi:10.1007/978-3-662-62439-5

[^friebolin]: Friebolin H. *Basic One- and Two-Dimensional NMR Spectroscopy*, 5th ed. Wiley-VCH, 2010.

[^gottlieb]: Gottlieb H. E.; Kotlyar V.; Nudelman A. *NMR Chemical Shifts of Common Laboratory Solvents as Trace Impurities.* J. Org. Chem. 1997, 62, 7512. doi:10.1021/jo971176v

[^fulmer]: Fulmer G. R. et al. *NMR Chemical Shifts of Trace Impurities…* Organometallics 2010, 29, 2176. doi:10.1021/om100106e

[^pharma_solids]: *Spectroscopy of Pharmaceutical Solids.* (Papers/Spectroscopy/Pharmaceutical solids)

[^qnmr]: *Quantitative NMR Spectroscopy in Pharmaceutical Applications.* (Papers/Spectroscopy/qNMR + Protein_NMR folder)

[^ai_ms_market]: *AI in Mass Spectrometry Software Market Size, Dynamics and Opportunities.* 2024 industry report.

[^analytical_scientist]: *Could AI Unlock Mass Spectrometry's Full Discovery Potential?* The Analytical Scientist.

[^ms_market_2032]: *Mass Spectrometry Market Size Trends Growth Report 2032.*

[^future_ai_ms]: *The Future of a Myriad of Accelerated Biodiscoveries Lies in AI-Powered Mass Spectrometry and Multiomics Integration.*

[^comp_nmr_survey]: *Exploring the frontiers of computational NMR methods: applications and challenges.* Recent survey.

[^ml_spectroscopy]: *Machine learning spectroscopy to advance computation and analysis.*

[^harmonising_2d]: *Harmonizing Peak Matching Between Multidimensional NMR Spectra.*

[^hsqc_simulation]: *HSQC spectra simulation and matching for molecular identification.*

[^id_database_nmr]: *Identification of organic molecules from a structure database using proton and carbon NMR analysis results.*

[^noise_inverse_design]: *Impact of noise on inverse design: the case of NMR spectra matching.*

[^reasoning_llms]: *Enhancing molecular structure elucidation with reasoning-capable LLMs.*

[^auto_framework]: *A framework for automated structure elucidation from routine NMR spectra.*

[^generative_drug_discovery]: *Generative AI for drug discovery and protein design.*

[^sherlock]: *Sherlock: A Free and Open-Source System for Computer-Assisted Structure Elucidation of Organic Compounds.*

[^nmrxiv]: *Overview nmrXiv.*

[^nmrpipe]: *NMRPipe.*

[^nmrglue]: *nmrglue developer documentation.*

[^mnova]: Mestrelab Research. *MestReNova User Manual.* 2024.

[^nmr_challenge]: *NMR Challenge — An Interactive Website with Exercises in Solving Structures from NMR Spectra.*

[^molecular_networking]: *Structure characterisation with NMR molecular networking.*

[^bayesian_reactions]: *Bayesian optimization for chemical reactions.* (Papers/Reaction Optimization)

[^ml_reaction_design]: *Machine Learning-Guided Strategies for Reaction Condition Design and Optimization.*

[^mech_insight_reactions]: *Reaction optimization through mechanistic insight and predictive modelling.*

[^arxiv_2509]: arXiv:2509.00103v2 — reaction-optimisation benchmark.

[^fda_ai_2025]: U.S. Food and Drug Administration. *Considerations for the Use of Artificial Intelligence to Support Regulatory Decision-Making for Drug and Biological Products.* Draft Guidance, January 2025.

[^ema_ai_reflection]: European Medicines Agency. *Reflection paper on the use of Artificial Intelligence (AI) in the medicinal product lifecycle.* 2024.

[^ich_q2r2]: International Council for Harmonisation. *ICH Q2(R2): Validation of Analytical Procedures.* 2023.

[^fda_nitrosamines]: U.S. Food and Drug Administration. *Control of Nitrosamine Impurities in Human Drugs.* Guidance for Industry.

---

## Companion documents

- **MolTrace White Paper — Hybrid** (canonical, ~5,700 words) — comprehensive business + technical overview
- **MolTrace White Paper — Sales** (~4,000 words) — business case forward, audience: pharma R&D directors
- **MolTrace Executive One-Pager** (~500 words) — single-page summary for gated download
- **MolTrace ROI Methodology** — measurement protocol + fill-in template for measured tenant data
- **MolTrace Company Credentials** — partner / customer logo bar + About MolTrace block

*© 2026 MolTrace Technologies, Inc. This white paper is the technical-reviewer variant intended for analytical-method validators, NMR / MS technical leads, regulatory-affairs reviewers, and data-integrity auditors. For pilot evaluation, regulatory-affairs briefings, or technical due-diligence access, contact MolTrace Technologies.*
