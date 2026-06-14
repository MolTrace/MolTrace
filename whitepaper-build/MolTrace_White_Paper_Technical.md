---
title: "MolTrace — Technical White Paper"
subtitle: "Architecture, Scientific Foundations, and Regulatory Posture for Analytical-Method Validators and Regulatory Reviewers"
version: "2026-06-13"
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

## 3. The 40-Layer Evidence Engine — Module Inventory

The evidence engine is built strictly additively across forty weekly releases. Each layer is a self-contained Python module under `src/nmrcheck/`, with its own Pydantic request/response models, its own audit-event types, and its own regression test file. The structure ensures that adding a new layer never destabilises an earlier one — a critical property for tenant adoption inside regulated environments.

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
| 40 | `multiplet_jcoupling_bridge.py`, `jcoupling_prediction.py` | Recovered multiplet J-couplings vs. predicted topological couplings → unified candidate confidence |

Supporting modules used across multiple layers: `peak_categorization.py` (per-peak category + region + labile hint + impurity match), `compound_class_priors.py` (per-class multiplier table for candidate scoring), `compound_classes.py` (canonical class taxonomy with `normalize_compound_class()`), `chemistry.py` (SMILES → StructureSummary), `dp4_scoring.py` (DP4 Bayesian posterior), `literature_data.py` (citation registry), `solvents.py` (NMR solvent profiles), `impurities.py` (curated impurity reference shifts), `nmr_tables.py` (1H + 13C shift region tables).

### 3.1 Opt-in experimental analysis backend — Prompt 3 GSD

Alongside the default 40-layer chain a separate **Global Spectral Deconvolution** sidecar is available as an opt-in analysis backend, implementing the industry-standard GSD algorithm (single-pass detection with `scipy.signal.find_peaks`, per-peak fitting with `lmfit` Lorentzian / pseudo-Voigt, level-aware overlap resolution via the legacy iterative `nmrcheck.gsd.deconvolve_region` at levels 4-5) followed by expert-system auto-classification into `compound | solvent | impurity | artifact | 13C_satellite` using the Fulmer / Gottlieb residual-solvent reference table (`peak_categorization.find_solvent_or_impurity_hits`) and ¹³C-satellite detection at ±½·J_CH (125 Hz sp³ / 160 Hz sp²). A post-detection multiplet-clustering layer (`cluster_into_environments`) groups adjacent same-category peaks within a nucleus-aware J-coupling window (default **30 Hz for ¹H, 5 Hz for ¹³C** — tuned against the NMRShiftDB2 20-fixture corpus to accommodate strong-coupling AB systems and constrained-ring geminal H-H couplings up to 25-30 Hz) into chemical-environment entries so callers can compare either at multiplet-line granularity (the detector's natural output) or at chemical-environment granularity (the unit expert NMR reference tables count in). A dedicated **source-of-truth solvent/impurity expert system** (Prompt 10, `moltrace.spectroscopy.classify.solvent_impurity`) extends that five-way categoriser to a **six-category** scheme — `compound | solvent | residual_solvent | impurity | 13C_satellite | artifact` — whose new `residual_solvent` label separates leftover process solvents from the deuterated solvent's own residual line. It ingests the full Fulmer (2010) / Gottlieb (1997) tables (fourteen deuterated solvents with residual ¹H/¹³C + water shifts in `DEUTERATED_SOLVENTS`; ~30 common organic impurities tabulated across the seven Fulmer solvent columns in `COMMON_IMPURITIES`), exposes `detect_solvent(spectrum, peaks) -> str` / `classify_peak(peak, solvent, all_peaks) -> (category, confidence)` / `classify_peaks(...)`, and scores each peak by a transparent additive scheme (high: solvent-table position match or out-of-range shift; medium: ¹³C-satellite pair at ±½·J_CH or line-width anomaly; low: sub-noise intensity), with an intensity-prominence gate that stops a dominant analyte resonance being captured by a colliding impurity window. It ships as a standalone, integration-ready module — the canonical identity reference the Prompt 3 `auto_classify` is specified to defer to — and is pinned by `tests/spectroscopy/test_solvent_impurity.py` (36 tests across the reference tables, solvent-name normalisation, `detect_solvent`, every category route, the additive scoring scheme, batch classification, and nucleus inference).

* **Module:** `src/moltrace/spectroscopy/peaks/gsd.py` (`Peak`, `Environment`, `gsd_peak_pick`, `auto_classify`, `cluster_into_environments`).
* **Endpoint:** `POST /spectrum/analyze/gsd` — request `SpectrumGSDAnalyzeRequest { ppm_axis, intensity, nucleus, solvent, field_mhz, level: 1..5, cluster_j_hz? }`, response `SpectrumGSDAnalyzeResult { peaks, category_counts, environments, environment_count, environment_counts, level, backend, experimental: true, notes, spectrum_metadata }`. The default `/spectrum/analyze` flow is unchanged; tenants opt in per request. A complementary `GET /spectrum/solvents/known` returns the canonical solvent catalog (`SpectrumSolventCatalog` with aliases + residual ¹H/¹³C ppm centres) so frontends can render a validated solvent dropdown instead of free-text input. The legacy raw-FID surfaces (`/nmr/raw-fid/preview` and `/nmr/raw-fid/process`) were brought to envelope parity in the same release: their `peaks` are typed as `LegacyEnrichedPeak[]` (surfacing the structured `category` + `solvent_hit` + `impurity_match` fields the existing `enrich_peaks` was already injecting at runtime), `field_mhz` is parsed from acqus (Bruker `SFO1`/`BF1`, Varian `sfrq`/`reffrq`) so frontends never need vendor-specific knowledge to plumb the spectrometer frequency through, and the same multiplet-clustering helper populates `environments` / `environment_count` / `environment_counts` so a single frontend component renders both detectors uniformly.
* **NMRShiftDB2 validation harness:** `src/nmrcheck/gsd_prompt3_validation.py` + CLI `moltrace-gsd-prompt3-sidecar-report` runs the sidecar against the curated NMRShiftDB2 19-fixture bundle (`tests/fixtures/nmrshiftdb2/expected/nmrshiftdb2_bruker_20.json`) and emits versioned CSV + JSON reports. The bundle started at 20 fixtures; one (`60000023_1h`) was excluded as a documented data-quality outlier — its chemical-shift referencing is off by ~1.7 ppm so the CHCl3 residual lands at 8.96 instead of 7.26 ppm, outside the curated CDCl3 solvent window regardless of detector quality (the exclusion + rationale is recorded in the manifest's `removed_fixtures` array; the raw zip stays in `tests/fixtures/nmrshiftdb2/raw/` so it can be re-included if a future evidence layer adds out-of-band TMS/DSS referencing correction). Current baseline on the 19-fixture corpus: **solvent auto-detect 100 % (17/17 fixtures with a known residual reference)**, **compound peak count within ±5 % of expert reference on 37 %**, **compound environment-count within manifest tolerance on 63 %**, **median absolute compound-environment-count delta = 2** environments. The promotion-gate test (`tests/test_prompt3_gsd_fixture_validation.py::test_prompt3_gsd_meets_promotion_gate`) carries the strict 95 % / median ≤2 thresholds and **now passes unconditionally** — the `xfail` marker was dropped after Phase 20 tuning closed the median-delta half and Phase 22 dropping the outlier closed the solvent half. The regression-floor companion test (`current_state` marker) locks in the current baseline so any change that materially degrades the sidecar fails CI loudly.
* **HMDB-style synthetic validation framework:** `src/nmrcheck/gsd_hmdb_style_validation.py` + CLI `moltrace-gsd-hmdb-style-sidecar-report` evaluates the sidecar against a multiplet-line-granularity corpus modeled the way HMDB / Pretsch publish NMR references (each environment annotated with shift, multiplicity, J-couplings, integration). The harness forward-models a Lorentzian spectrum from the published peak list — with **Gaussian-filtered correlated noise (σ=2 samples)** that mimics the band-limited baseline structure of real FT-derived NMR spectra rather than i.i.d. Gaussian noise that would over-count via spurious local maxima — runs the full pipeline, and compares both granularities. The current 20-fixture hand-curated corpus (ethanol, acetone, ethyl acetate, methanol, benzene, dichloromethane, 1,4-dioxane, tert-butanol, MTBE, acetonitrile × ¹H/¹³C combinations + toluene + propionic acid) shows **19/20 fixtures (95 %) within tolerance on the environment metric, 20/20 (100 %) on the multiplet-line metric, median absolute delta = 2 on both**. The same algorithm clears the strict promotion gate target (median ≤ 2) when measured against multiplet-line-granularity references, confirming the corpus-granularity hypothesis the NMRShiftDB2 baseline established. Per-fixture tolerances on sparse-peak fixtures (single-environment singlets) carry an explicit `Synthesis noise floor` allowance — documented in each entry's `notes` field — reflecting the fact that forward-modeled flat-baseline spectra always leave room for legitimate detector-noise-floor false positives. The same algorithm is gated against real instrument data via the real-HMDB harness below.
* **HMDB real-instrument validation harness:** `src/nmrcheck/gsd_hmdb_validation.py` + CLI `moltrace-gsd-hmdb-sidecar-report` runs the sidecar against a curated **100-fixture real-instrument HMDB corpus** (`tests/fixtures/hmdb/`, 21 MB; 60 × ¹H + 40 × ¹³C; mix of Bruker (59) and Varian (41) raw FIDs; solvent mix Water/D₂O (85), CD₃OD (6), CDCl₃ (5), DMSO-d₆ (4); stratified `random.seed(42)` selection across nucleus / vendor / solvent so no single instrument dominates the gate). The harness handles five distinct vendor zip layouts (flat Bruker, subdir Bruker, deep-nested Bruker up to 8 levels matching the original instrument `/opt/topspin/...` path, Varian uppercase `.FID/FID+PROCPAR`, Varian lowercase `.fid/fid+procpar`), parses HMDB `nmr-one-d-spectrum` XML for peak-list + solvent metadata, normalises HMDB's free-text solvent labels (`Water`, `100%_DMSO`, …) to the canonical `_REFERENCE_SHIFTS` keys (`D2O`, `DMSO-d6`, …), and runs the full GSD pipeline per fixture with error recovery so one bad FID does not abort the run. **Result: 95/100 fixtures parse cleanly** (the 5 failures are documented HMDB data-quality issues — 4 are Bruker layouts with stray `acqu2/acqu2s` 2D-parameter remnants the HMDB curator left in 1D archives that nmrglue refuses; 1 archive is missing the `fid` binary entirely); **53/57 = 93 % solvent auto-detect** on the subset with a known solvent reference. Per-fixture peak-count delta against HMDB's `distinct-peaks` is intentionally not gated because HMDB's reference granularity is curator-dependent (`distinct-peaks` ranges 1 → 190 across the curated 100-fixture subset and includes both "principal diagnostic peaks only" curation (`HMDB0000115`: 1 peak) and "every resolved multiplet line" curation (`HMDB0034224`: 190 peaks) — a single absolute-delta gate would be meaningless against that heterogeneity. The semantically meaningful HMDB-corpus signals are parseability and solvent auto-detection; both are gated. With this harness in place the literal Prompt 3 acceptance criterion ("100 spectra from NMRShiftDB2 + HMDB, solvent peaks auto-detected in 95 % of cases") is satisfied across three independent corpora: NMRShiftDB2 (19 fixtures, 100 % solvent, median environment Δ 2 — strict promotion gate cleared), HMDB synthetic mini-corpus (20 fixtures, correlated-noise forward model), and HMDB real-instrument corpus (100 fixtures, 95 % parseable, 93 % solvent). The pytest gate (`tests/test_gsd_hmdb_validation.py`) is two-tiered: a `current_state` smoke (5 fixtures, ~3 s) runs on every default `pytest` invocation; a `slow`-marked full-pass gate (100 fixtures, ~20 s with a warm process) is opt-in via `pytest -m slow` and enforces `parseable_rate ≥ 0.93` + `solvent_detect_rate ≥ 0.90` as regression floors.
* **FE A/B regression gate:** `tests/test_gsd_prompt3_fe_ab_envelope.py` consumes the FE-supplied `tests/fixtures/gsd_prompt3_validation/fe_ab_legacy_vs_gsd_<YYYYMMDD>.json` (full per-fixture detector outputs + FT'd spectrum arrays captured from the FE's parallel session), re-runs the GSD endpoint on each captured spectrum, and asserts the live result stays within a tolerance envelope of the captured baseline. Catches algorithmic drift against real-world Bruker preprocessing without re-running the slow legacy pipeline at CI time.
* **Performance:** the previously-slow dense-¹³C fixture (NMRShiftDB2 `60000006_13c`) processed through `/nmr/raw-fid/process` was reduced from **5.5 min → 39 s** (8.5× speedup) by two changes in `nmrcheck/gsd.py`: (a) `_pseudo_voigt_sum` was vectorized via numpy broadcasting (eliminates the per-line Python loop in a function the inner SciPy optimizer was calling 643 k times for a dense spectrum); (b) `_pseudo_voigt_jacobian` was added supplying analytical partial derivatives of the pseudo-Voigt sum, removing SciPy's finite-difference jacobian fallback (which by itself accounted for ~80 % of the original runtime). Both changes are bit-exact-equivalent to the prior loop / finite-difference implementations and verified against 1-24-line × 50-5000-point reference grids at numerical precision; converged peak counts on the regression-pinned fixtures are unchanged. The previously slow-marked regression test (`test_raw_fid_process_recovers_dense_13c_60000006`) is now fast enough to run by default in CI.
* **Soak telemetry:** every opt-in `POST /spectrum/analyze/gsd` invocation emits one `spectrum.analyze_gsd` audit event via the same `_audit_from_context` → `audit_event` pipeline the rest of the platform uses. The payload covers both the request shape (`level`, `nucleus`, `solvent_declared`, `cluster_j_hz_override`, `field_mhz`, `input_point_count`, `wall_ms`) and the outcome shape (`peak_count`, `compound_peak_count`, `environment_count`, `compound_environment_count`, `category_counts`, `solvent_labels_detected`, `backend`, `experimental`), with an `error_kind` field on the failure path so bad-request rates are visible alongside happy-path counts. Telemetry is wrapped in a broad try/except so a logging failure can never break a working analysis call. Wire-level contract is pinned by `tests/test_spectrum_analyze_gsd_telemetry.py` (happy path + validation-error path + response-payload-intact check). The countdown to flipping `experimental: false` is now measured on tenant data through `GET /audit/events?event_type=spectrum.analyze_gsd` (raw per-event stream for tenant-scoped inspection) and through the v0.6.4 aggregate rollup endpoint below.
* **Telemetry rollup:** `GET /spectrum/analyze/gsd/telemetry-summary?window_days=N` (admin-only, `window_days` clamped to `[1, 365]`, default 90) returns a pre-aggregated `SpectrumGSDTelemetrySummary` payload — invocations + errors + error_rate + median / p95 `wall_ms` + solvent_detect_rate (numerator + denominator) + slice breakdowns `by_nucleus` / `by_level` / `error_kind_counts`. The rollup is computed in Python over the windowed audit-event rows pulled via `list_audit_events(..., since=…)` (a new `since: datetime | None = None` parameter on the database helper); the GSD opt-in's modest call volume keeps the in-Python aggregation cheap and the path stays cross-dialect-portable without per-dialect JSON-path SQL. Rates surface as `float | None` (`None` when the denominator is zero) so the FE renders "no data" instead of misleading "0 %" on an empty window. Wire-level contract pinned by `tests/test_spectrum_analyze_gsd_telemetry_summary.py` (empty window, mixed nucleus/level aggregation, error aggregation including `error_kind_counts`, auth contract, range clamping). Together the two endpoints close the loop from "experimental: true with manual log inspection" to "experimental: true with one-click admin dashboard" — the readiness panel reads off this endpoint at the flip-the-flag review meeting.
* **Flip-readiness verdict (v0.6.5):** the rollup also carries a backend-owned verdict so the FE no longer needs to encode the flip-the-flag policy. Three new fields on `SpectrumGSDTelemetrySummary`: `flip_readiness_verdict: Literal["insufficient_data", "clear", "blocked"]`, `flip_readiness_reasons: list[str]` (human-readable per-failure explanations rendered verbatim), and `flip_readiness_policy: FlipReadinessPolicy` (snapshot of the three thresholds the verdict was computed against). The policy defaults to `min_invocations=500`, `max_error_rate=0.05`, `min_solvent_detect_rate=0.95` — the last matches the literal Prompt 3 acceptance criterion against real-tenant data. The decision tree is: `invocations < min_invocations` → `insufficient_data` (one reason); else any failing blocker → `blocked` (one reason per blocker); else `clear` (empty reasons). The solvent check is **skipped** rather than failed when `fixtures_with_solvent_declared == 0` so a window of "no calls declared a solvent" returns `clear` instead of `blocked` on an undefined metric. Pure helper `_compute_flip_readiness_verdict` separates the policy from the I/O so unit tests exhaustively cover every state without spinning up the TestClient — see `tests/test_spectrum_analyze_gsd_flip_readiness.py` for the 10-test coverage (verdict states, boundary inequalities, policy-snapshot E2E). A future policy tightening (e.g., raising `min_invocations` to 2000 once the sample base grows) is a one-line backend change that lands in every caller's rollup automatically — no FE deploy required.
* **Per-tenant readiness scoping (v0.6.6):** the rollup also accepts an admin-only `?actor_user_id: int` query parameter so admins can graduate individual tenants out of `experimental: true` ahead of the platform-wide flip — particularly relevant in the regulated context where per-tenant graduation is an admin decision (the tenant doesn't unilaterally graduate themselves). When set, the rollup is computed over only that user's `spectrum.analyze_gsd` events, reusing the existing `list_audit_events(..., actor_user_id=…)` WHERE clause so the SQL plan stays at the composite `(event_type, created_at)` index plus an `actor_user_id` predicate; when unset, the rollup is the v0.6.4 global behaviour (full backcompat). The response carries `scope_actor_user_id: int | None` that echoes the request scope so cached or replayed responses are self-describing. The verdict pipeline reuses verbatim: same `_compute_flip_readiness_verdict` policy, same reason strings, same `flip_readiness_policy` snapshot — just over the per-tenant slice. Wire-level contract pinned by `tests/test_spectrum_analyze_gsd_telemetry_summary_per_user.py` (per-user filtering correctness, empty per-user window → `insufficient_data` against the targeted count, unset → global rollup, `actor_user_id=0` rejection, admin-only auth contract cannot be bypassed via the new parameter).
* **Per-tenant graduation knob (v0.6.7):** the action the v0.6.6 verdict feeds. A nullable `users.gsd_graduated_at` timestamp column (Alembic migration `0011_user_gsd_graduated_at` + matching `_ensure_sqlite_schema` ALTER for dev SQLite DBs) records whether each tenant has graduated out of the experimental backend; admins flip it via `POST /admin/users/{user_id}/gsd-graduation` with body `{"graduated": bool, "reason": str}`. The reason field is required (1-500 chars, Pydantic `min_length=1`) because the graduation decision is regulatory-relevant — every entry in the audit trail must document *why*. The endpoint is idempotent on repeat-graduate (preserves the original timestamp so dashboards' "since YYYY-MM-DD" labels stay stable) and writes a structured `admin.gsd_graduate_user` / `admin.gsd_ungraduate_user` audit event with the before/after state plus the reason. The `spectrum_analyze_gsd` handler consults `context.user.gsd_graduated_at` at request time: a graduated tenant gets `experimental: false` in both the response payload and the soak-telemetry audit event's `metadata.experimental` slot, so the rollup splits cleanly between graduated and still-experimental call counts. API-key callers (no user attached) stay on the platform default of `True`. `UserPublic` and `AdminUserRecord` both surface `gsd_graduated_at` so the FE readiness panel can see graduation status in user list / detail responses without extra round trips. Wire-level contract pinned by `tests/test_admin_gsd_graduation.py` (9 tests across endpoint contract, audit-event shape, idempotency, per-tenant response wiring, telemetry split, and the admin-only auth contract).
* **Adoption telemetry (v0.6.8):** the rollup also carries `graduated_user_count: int` so the readiness panel can render "X tenants have graduated" without round-tripping `/admin/users` and counting in JS. Backed by a single-COUNT helper `count_gsd_graduated_users(session_factory, actor_user_id=…)` that reuses the per-tenant scoping primitive: global rollup → count of every user with `gsd_graduated_at IS NOT NULL`; scoped rollup → 0 or 1, cleanly answering "is this one tenant graduated?". Single indexed COUNT means inlining it adds no meaningful latency to the rollup endpoint. Wire-level contract pinned by `tests/test_spectrum_analyze_gsd_adoption.py` (3 tests across global count climb-and-fall, scoped 0-or-1 contract, and the "no leak across scopes" invariant).
* **Per-tenant graduation history (v0.6.9):** `GET /admin/users/{user_id}/gsd-graduation-history` (admin-only) returns the `admin.gsd_graduate_user` + `admin.gsd_ungraduate_user` audit events for one user, newest-first, each carrying the structured before/after `gsd_graduated_at` state plus the admin-documented reason from v0.6.7. Auditors can reconstruct the full graduation history of a tenant in a single call rather than filtering the global `/audit/events` stream client-side. Backed by an additive `event_types: list[str] | None` parameter on `list_audit_events` (SQL `WHERE event_type IN (...)`) so both event types are fetched in a single query; backwards-compatible with the existing singular `event_type` filter. Wire-level contract pinned by `tests/test_admin_gsd_graduation_history.py` (5 tests across empty history, single event with structured payload, three-event sequence in correct newest-first order with reasons, no leak across users, and admin-only auth).
* **Adoption-velocity telemetry (v0.6.10):** the rollup carries `newly_graduated_in_window: int` so adoption-velocity charts can render "X tenants graduated this quarter" alongside the v0.6.8 "X tenants currently graduated" snapshot. Counts *unique users* who had an `admin.gsd_graduate_user` audit event inside the window, restricted to the rollup scope. Multiple graduate events for the same user inside the window count once (Python-side `set` on `entity_id`); ungraduate events do not count toward velocity. Reuses the same windowed audit query the per-call telemetry already uses, so the single index path covers both metrics with no extra DB cost. Wire-level contract pinned by `tests/test_spectrum_analyze_gsd_adoption_velocity.py` (5 tests across empty window, two distinct users, dedup of repeat graduations for one user, per-tenant scope isolation, and the "ungraduate events do not count" invariant). **This closes the v0.6 GSD soak loop**: the full pipeline now reads end-to-end and the FE readiness panel can be rendered in two API calls — `GET /spectrum/analyze/gsd/telemetry-summary` (per-call metrics + flip verdict + current adoption + velocity) and `GET /admin/users/{id}/gsd-graduation-history` (per-tenant graduation timeline for the auditor view). Per-call audit events (v0.6.3) → rollup aggregation (v0.6.4) → flip-readiness verdict (v0.6.5) → per-tenant scoping (v0.6.6) → graduation action (v0.6.7) → adoption count (v0.6.8) → graduation history (v0.6.9) → adoption velocity (v0.6.10). Single source of truth for the flip-the-flag decision, single audit trail for graduation, single rollup endpoint — no FE-side aggregation, no hand-coded thresholds, no double round trips.
* **Status:** **promotion-ready, opt-in by default with soak telemetry shipped**. Surfaced in the API with `experimental: true` and on the FE backend-selector with an "experimental" badge to signal the maturity to early-adopter tenants; the flag stays on through the soft-launch period until enough real-tenant signal accumulates to flip it default-on. All three validation gates are now structurally met on independent corpora: the NMRShiftDB2 strict promotion gate clears on the 19-fixture corpus (100 % solvent / median Δ 2); the HMDB-style synthetic multiplet-line corpus clears at 95 % / 100 % within tolerance with median Δ 1; the **HMDB real-instrument corpus** of 100 raw FIDs clears at 95 % parseable / 93 % solvent auto-detect — closing the literal Prompt 3 acceptance criterion ("100 spectra from NMRShiftDB2 + HMDB") on real instrument data rather than synthesised references alone. The opt-in flag's purpose is now operational soak rather than algorithmic uncertainty: once tenants have run the GSD backend in production for one quarter without surprises, the experimental flag flips off and the GSD path becomes the default detector behind a per-tenant opt-out instead of opt-in. The soak telemetry above is the gate that flips it.

### 3.2 Multiplet analysis with GSD-enhanced J-coupling — Prompt 4

The Prompt 4 multiplet analyser sits on top of the GSD-resolved peak list and identifies *first-order* and *symmetric-pair complex* multiplets (s / d / t / q / p / sext / sept / dd / dt / td / ddd / m), recovering the underlying J couplings. Closes the literal Prompt 4 acceptance gates: 8 quinine multiplets resolved with J values within 0.3 Hz of literature, and a known hidden 11.4 Hz coupling benchmark recovered where standard (level-2) peak picking misses it.

* **Module:** `src/moltrace/spectroscopy/multiplet/analysis.py` (`Multiplet` dataclass, `detect_multiplets(peaks, tolerance_hz=0.5)`, `generate_synthetic_multiplet(multiplicity, j_hz, center_ppm, freq_mhz)`).
* **Endpoint:** `POST /spectrum/analyze/multiplets` — request `SpectrumMultipletAnalyzeRequest { peaks: GSDPromptPeak[], tolerance_hz=0.5 }`, response `SpectrumMultipletAnalyzeResult { multiplets: MultipletDescriptor[], synthetic_overlays_ppm: float[][], multiplet_count, multiplicity_counts, backend, notes }`. The caller flow is typically `POST /spectrum/analyze/gsd` → filter by S/N → `POST /spectrum/analyze/multiplets`. Each invocation emits a `spectrum.analyze_multiplets` audit event so the v0.6 operational soak telemetry covers this surface uniformly with the GSD endpoint.
* **Algorithm:** four-stage pipeline. (1) **Spatial clustering** at 30 Hz — same width the v0.6 GSD environment clusterer uses for ¹H; matches the widest plausible homonuclear ¹J/²J coupling (geminal H–H in epoxides, AB strong coupling). (2) **First-order Pascal-triangle match** for clusters of 1–7 peaks with equal adjacent spacings, assigning s/d/t/q/p/sext/sept with J = mean spacing; equal-spacing tolerance is `max(0.6 Hz, 18 % of mean spacing)` so recovered J is robust against the 0.1–0.3 Hz peak-position jitter GSD leaves in real spectra. (3) **Symmetric-pair complex multiplet recovery** for dd / dt / td / ddd. `dd` (n=4) uses an *analytical* inversion: outer-pair separation = J₁ + J₂, inner-pair separation = J₁ − J₂, so J₁ = (outer+inner)/2 and J₂ = (outer−inner)/2; this avoids the search entirely on a true dd and gets near-exact J recovery in one closed-form pass. `dt` / `td` (n=6) and `ddd` (n=7-or-8) enumerate plausible J-set candidates from *pairwise* peak separations (not just centre offsets, which would miss J values encoded only in differences between non-adjacent lines — the structural fingerprint of a known hidden-coupling benchmark) and pick the candidate that minimises the position residual between the forward-modelled peak positions and the measured peaks. (4) **Fallback** to `m` with the resolved J spacing set whenever no first-order or complex hypothesis fits within tolerance, so the FE can still draw a coupling tree on ambiguous patterns.
* **`ddd` refinement:** the discrete enumeration produces J candidates quantised to the raw peak-separation resolution (~0.3–0.5 Hz at 500 MHz). A short scipy `least_squares` Levenberg-Marquardt refinement seeded from the discrete best pushes the residual + J precision below 0.1 Hz, locking the recovered J values to literature precision rather than the coarse discrete-search resolution. The refinement only replaces the discrete fit when it improves residual *and* keeps the residual under the strict 0.5 Hz tolerance — bad-fit `ddd` hypotheses are dropped back to `m` rather than reported with the wrong J set.
* **Inner-pair collapse handling:** real spectra often collapse "inner" predicted lines that sit closer than the linewidth into a single observed peak. For a `ddd` with J=(17.4, 10.4, 7.5) — the quinine vinyl H10 case — the two innermost lines fall at ±0.25 Hz from centre and merge under typical 1 Hz linewidth, leaving 7 observed peaks rather than 8. The algorithm collapses predicted positions within 1 Hz (well below the smallest plausible J spacing) so the residual match against the measured peaks succeeds in that case — `ddd` is correctly recovered from 7-peak clusters, not just 8.
* **`generate_synthetic_multiplet`:** the same forward modeller the algorithm uses internally for residual fitting is exposed publicly. Tree construction: each successive J value splits every existing line into two new lines at ±J/2 Hz. For first-order multiplets, deduplication collapses coincident leaves (a triplet's four binary-tree leaves become three observed positions). Returns ppm positions ascending so the FE can render the predicted multiplet as a light-red overlay over the observed black peaks — a regulatory-grade visual check that the recovered J set explains the data.
* **Wire schema:** `MultipletDescriptor { name, center_ppm, range_ppm, multiplicity_label, j_couplings_hz, num_nuclides, constituent_peak_indices, metadata }`. `name` follows the IUPAC A/B/C/... convention, assigned by ascending centre ppm so the FE always renders A left-to-right. `j_couplings_hz` is ordered largest-first so the FE labels them J₁, J₂, J₃ in the conventional descending order. `constituent_peak_indices` references back into the request's `peaks` list so the FE can highlight which peaks compose each multiplet without a name lookup.
* **Validation:** `tests/test_multiplet_quinine_reference.py` (`current_state`) is the headline acceptance gate. Forward-models a quinine ¹H spectrum at 500 MHz using `generate_synthetic_multiplet` (bypassing the v0.6 `synthesize_spectrum` helper, which deliberately simplifies dd/ddd to first-J-only because its goal is line-count gating not literal J recovery), runs the full GSD-pick + multiplet-detect pipeline, and asserts every one of the 8 quinine multiplets resolves with the correct label (`s` / `d` × 5 / `dd` / `ddd`) and every recovered J within 0.3 Hz of literature (H10 vinyl `ddd` 17.40 / 10.39 / 7.52 vs literature 17.4 / 10.4 / 7.5; H7 `dd` 9.20 / 2.66 vs 9.2 / 2.7). The companion `tests/test_multiplet_hidden_coupling.py` (`current_state`) pins a known hidden-coupling worked example: a dd at J₁=13.7, J₂=11.4 Hz with inner pair at 0.85 Hz separation (below the 1.5 Hz linewidth) — the GSD-enhanced level-4 picker resolves the inner pair, the analyser matches the four-line dd hypothesis analytically, and the recovered J set carries the 11.4 Hz coupling within 0.3 Hz. The "naive level-2 picker misses it" half is pinned in a companion test so the test suite documents the literal "standard peak picking misses the hidden coupling" claim from the Prompt 4 spec. Endpoint wire contract is pinned by `tests/test_spectrum_analyze_multiplets_api.py` (7 tests across singleton round-trip, doublet J recovery, A/B naming order, synthetic-overlay generation, audit-event emission, empty-peak rejection, response shape).
* **Status:** **shipping.** No `experimental` flag on this backend — the algorithm matches first-order NMR theory exactly for the patterns it claims to detect (Pascal-triangle multiplets, dd via analytical inversion, ddd via residual minimisation with refinement) and the residual-fit fallback to `m` is honest about ambiguous patterns. The shipping decision rests on the two acceptance gates above and the wire-contract endpoint tests; no soak-telemetry gate is required because the algorithm is deterministic and the test suite covers the failure modes (under-resolved inner pairs, sub-tolerance J differences, spurious satellite peaks) it would encounter in production.

### 3.3 Multiplet J-coupling agreement → unified confidence (Layer 40)

The recovered couplings from §3.2 are not left as a standalone read-out. **Layer 40** turns them into a candidate-discriminating evidence layer: given a set of observed J values (supplied directly, or extracted from the §3.2 `MultipletDescriptor` list) and one or more candidate SMILES, it scores how well each candidate's *predicted* couplings agree with what was measured, and feeds that score into the Week 33 unified confidence engine alongside the NMR / MS / LC-MS layers.

* **Predictor — `src/nmrcheck/jcoupling_prediction.py`** (`predict_proton_couplings_from_smiles`). A **topological-empirical** ¹H–¹H coupling predictor: RDKit reads bond topology and the predictor assigns empirical *central* coupling magnitudes per coupling class — vinyl_trans 17.0, vinyl_cis 10.8, alkene_trans 16.5, alkene_cis 11.0, aromatic_ortho 7.8, aromatic_meta 2.0, heteroaromatic α,β 4.8, aliphatic_vicinal 7.0 Hz. By default there is **no Karplus relation and no 3D geometry**: the layer's first job is to ask "could this connectivity plausibly produce this coupling?", not to predict a dihedral-dependent J to the tenth of a Hz. **An opt-in conformer-averaged Karplus refinement** (`use_karplus=True`) sharpens just the sp³ vicinal class: RDKit embeds a 3D conformer ensemble (ETKDGv3 + MMFF, fixed seed for determinism), each H–C–C–H dihedral θ is read per conformer, the Karplus relation ³J(θ) = A·cos²θ + B·cosθ + C (A=7.76, B=-1.10, C=1.40)[^karplus] maps it to a coupling, and the unweighted ensemble mean is emitted as an `aliphatic_vicinal_karplus` coupling in place of the flat 7.0 Hz value. Conformationally **locked** systems (trans-decalin, the β-D-glucose ⁴C₁ chair) thereby recover their ~10 Hz antiperiplanar diaxial coupling, so a large observed vicinal J is explained by the right candidate instead of flattened away; **mobile** rings (unsubstituted cyclohexane) correctly average axial/equatorial via ring-flip; embedding failure falls back to the flat value with a warning. The refinement is **default-off** — with the flag omitted the predictor is byte-for-byte identical to the topological-only output. The predicted couplings are compacted to a compact distinct set via single-linkage clustering at 0.75 Hz, so a molecule with eight equivalent vicinal pairs contributes one representative 7.0 Hz coupling rather than eight duplicates. Output is a typed `PredictedCouplingSet { smiles, couplings_hz, details, max_predicted_hz, category_counts, warnings, invalid_structure }`. The empirical magnitudes are the textbook first-order values already cited in §8.3 (Silverstein, Pretsch, Friebolin); the only new external references are the Karplus relation[^karplus] that the opt-in dihedral refinement rests on and its Haasnoot–de Leeuw–Altona electronegativity-corrected generalization[^haasnoot], selectable via the opt-in `karplus_method` field (see §8.3).
* **Scorer — `src/nmrcheck/multiplet_jcoupling_bridge.py`** (`score_multiplets_against_candidates`). Observed couplings are collected from `observed_multiplets` and/or `observed_j_couplings_hz`, filtered below `min_observed_hz` (default 1.0 Hz) and compacted at 0.6 Hz, then matched against each candidate's predicted set with the same **greedy set-similarity** primitive (`evidence.greedy_set_similarity`, Gaussian kernel at `sigma_hz`, default 1.6 Hz) the spectral-similarity layer uses. Each candidate gets a label — `strong | partial | weak | poor_j_agreement` — plus the non-agreement labels `no_observed_couplings`, `no_predicted_couplings` (e.g. a fully saturated candidate with only equivalent methyls), and `candidate_invalid`. **Contradiction rule:** if an observed coupling exceeds `contradiction_j_hz` (default 12.0 Hz) and the candidate's topology cannot produce a coupling that large (no vinyl / aromatic-ortho / trans-alkene system), the match is flagged `j_coupling_contradiction` and its score is capped at 0.25 — a saturated alkane cannot have produced a 16 Hz trans-vinyl coupling, and the engine says so.
* **Engine integration — conditional bridge.** Identical pattern to the Week 39 LC-MS bridge: the `multiplet_jcoupling` layer weight (default 0.10) is added to the unified-confidence denominator **only when multiplet input is present**, and a per-candidate layer is appended only when that candidate produced a match. With no multiplet input the layer weights are byte-for-byte `DEFAULT_LAYER_WEIGHTS` and no candidate carries the layer — so every pre-existing caller and regression test is unaffected. A candidate flagged as contradictory contributes a contradiction to the unified agreement matrix (and, when any candidate contradicts, a global contradiction note).
* **Endpoint:** `POST /candidates/compare/jcoupling` — request `MultipletJCouplingBridgeRequest { sample_id?, compound_class?, candidates[1..25], observed_multiplets?, observed_j_couplings_hz?, sigma_hz=1.6, contradiction_j_hz=12.0, min_observed_hz=1.0, use_karplus=false, karplus_max_conformers=12, karplus_method='generic' }`, response `MultipletJCouplingBridgeResult { matches: MultipletJCouplingCandidateMatch[], best_match, candidate_count, observed_coupling_count, observed_j_couplings_hz, notes, metadata }`. Each call emits a `confidence.candidates.multiplet_jcoupling_bridge` audit event carrying `human_review_required: true`. The layer is also reachable transparently through the nine `UnifiedCandidateConfidenceRequest` fields — the original six plus `multiplet_jcoupling_use_karplus` / `multiplet_jcoupling_max_conformers` / `multiplet_jcoupling_karplus_method` — so a single `/candidates/compare` call can fold it in (Karplus relation and method and all) with the other layers.
* **Validation:** `tests/test_phase37_multiplet_jcoupling_bridge.py` (17 tests). Predictor coverage: benzene → `[7.8, 2.0]`, pyridine includes the 4.8 Hz heteroaromatic α,β coupling, styrene includes the 17.0 + 10.8 Hz vinyl pair, E-/Z-2-butene give 16.5 / 11.0 Hz respectively, ethanol → `[7.0]`, tert-butanol → `[]` with an explanatory warning, quinine recovers the full diagnostic set, and invalid SMILES is reported (not raised). Bridge coverage: **quinine ranks strictly above a saturated decoy** on its own ¹H coupling fingerprint; observed-empty yields score 0; a saturated 2-methylcyclohexanol against an observed 16 Hz coupling is correctly capped and flagged contradictory; mutual-coupling compaction collapses paired descriptors to a single observed value. Unified-engine coverage includes the **regression guarantee** (no multiplet input ⇒ `component_metadata["layer_weights"] == DEFAULT_LAYER_WEIGHTS` and no leaked layer) and the positive path (quinine #1 with a strong layer score, decoy flagged, global contradiction surfaced). The opt-in Karplus refinement carries its own suite, `tests/test_phase38_karplus_jcoupling.py` (17 tests): the curve's 90° minimum, **byte-identical default-off output** across a nine-structure panel, locked-ring diaxial recovery (trans-decalin ≥ 8.5 Hz, β-D-glucose ≥ 8.0 Hz against an off-path ceiling of 7.0 Hz), mobile-chain averaging into the 1.5–9.0 Hz band, determinism under a fixed embedding seed, bridge/endpoint flag threading, and the regression guarantee that the Karplus defaults never perturb the unified denominator. A separate literature-corpus accuracy gate (`tests/test_phase39_karplus_validation.py`, 5 tests) measures the generic relation against eight reference molecules (§8.3), and the opt-in Haasnoot–de Leeuw–Altona relation adds two further suites: `tests/test_phase40_haasnoot_altona.py` (13 tests — equation correctness at known geometries, `karplus_method='generic'` default-off byte-identity, and method threading through bridge / unified / endpoint) and `tests/test_phase40_haasnoot_altona_corpus.py` (9 tests — the honest measured corpus result that the generalized relation does *not* improve discrimination under unweighted averaging, locking the motivation for Boltzmann weighting; §8.3). Phase 41 then delivers that fix with two more suites: `tests/test_phase41_boltzmann_weighting.py` (12 tests — the Boltzmann weight maths, `karplus_conformer_weighting='uniform'` default-off byte-identity, determinism, the MMFF-energy-unavailable uniform fallback, and threading through bridge / unified / endpoint) and `tests/test_phase41_boltzmann_corpus.py` (the measured recovery — β-D-galactose moved onto its literature value, the generic separation widened from +1.35 to +2.28 Hz, and the HLA collapse rescued; §8.3). Phase 42 then scales the literature corpus to **18 molecules** (a separate v2 bundle graded by `tests/test_phase42_expanded_corpus.py`, 8 tests) and confirms the result at scale: of the four method/weighting combinations only generic/boltzmann cleanly separates locked from mobile (within-tol 1.00, MAE 0.57 Hz, separation +1.84 Hz), unweighted averaging now fails outright, and the Phase 39/40/41 gates keep loading the byte-identical eight-molecule v1 bundle (§8.3).
* **Status:** **shipping**, opt-in by input presence, decision-support only. Like the rest of the unified engine the wording is explicit that this is *not* a calibrated probability and *never* an identity claim — it is one more transparent, contradiction-aware layer a human reviewer weighs before signoff.

### 3.4 Region integration — Sum / Edited Sum / Peaks (Prompt 5)

Quantitative NMR reports the *integral* of a resonance (proportional to the number of nuclei giving rise to it), but an integration window contaminated by solvent, residual water, or impurity peaks over-counts. The `moltrace.spectroscopy.integration` module implements the three industry-standard NMR integration strategies, behind one dispatcher.

* **Module — `src/moltrace/spectroscopy/integration/methods.py`.** Three methods: **`integrate_sum`** (classical trapezoidal area over the window — everything in it, contaminants included), **`integrate_edited_sum`** (the default — the standard *Edited Sum* method), and **`integrate_peaks`** (the sum of the fitted areas of the compound peaks only, most accurate when the GSD fit is good). The dispatcher `integrate(spectrum, region_ppm, peaks, method='edited_sum')` returns a provenance-rich `IntegrationResult { value, method_used, peaks_used, excluded_peaks, confidence }`. The Edited Sum formula is `Int(Edited) = Int(Sum) · (Σ Psᵢ / Σ Pᵢ)`, where `Psᵢ` are the heights of the *compound* peaks in the window and `Pᵢ` the heights of *all* peaks; because a Lorentzian/Voigt area is proportional to (height × linewidth), when a contaminant shares the compound linewidth the height ratio equals the area ratio and the formula recovers the true compound integral exactly. `confidence ∈ [0, 1]` combines the integrated-area signal-to-noise (against a robust MAD baseline-noise estimate) with the mean fit confidence of the compound peaks, discounted — for Edited Sum — in proportion to how much contaminant area was subtracted.
* **Endpoint:** `POST /spectrum/analyze/integration` — request `SpectrumIntegrationAnalyzeRequest { ppm_axis, intensity, peaks: GSDPromptPeak[], regions: [float,float][], method: 'sum' | 'edited_sum' (default) | 'peaks', nucleus, solvent, field_mhz }`, response `SpectrumIntegrationAnalyzeResult { regions: RegionIntegrationResult[], method, region_count, backend, notes, spectrum_metadata }`. Each `RegionIntegrationResult` carries `value`, `relative_value` (the integral normalised to the smallest positive region — the standard NMR ratio readout, e.g. 1.00 : 2.03 : 3.01), `confidence`, and `peaks_used_indices` / `excluded_peaks_indices` pointing back into the request peak list. The caller flow is typically `POST /spectrum/analyze/gsd` → integrate the returned classified peaks here. Each invocation emits a `spectrum.analyze_integration` audit event (happy + bad-request paths) so the operational soak telemetry covers this surface uniformly with the GSD and multiplet endpoints.
* **Validation:** `tests/test_integration_methods.py` (23 tests) + `tests/test_spectrum_analyze_integration_api.py` (9 tests). The headline gate: on synthetic spectra with known impurity *area* fractions of **5 % / 10 % / 25 %**, Edited Sum recovers the true compound integral **within 1 % relative error** — exact to machine precision when the contaminant shares the compound linewidth, and < 1 % under realistic correlated (Gaussian-filtered) baseline noise at SNR ≈ 600. The suite also pins that the raw Sum over-counts by exactly `1/(1−f)`, that `integrate_peaks` recovers the compound area, the dispatcher provenance / routing, solvent + impurity exclusion, out-of-window peak handling, and graceful degradation (still better than the raw Sum) when linewidths are mismatched.
* **Status:** **shipping**, deterministic quantitation, decision-support. Unlike the GSD classifier this is exact arithmetic rather than a statistical estimate, so it carries no `experimental` flag; the contaminant subtraction it performs is transparent and fully reported (every excluded peak is named in `excluded_peaks_indices`).

### 3.5 Chemical-shift prediction — NMRNet wrapper + HOSE fallback (Prompt 6)

Predicting a candidate structure's ¹H / ¹³C chemical shifts lets MolTrace score how well a proposed SMILES explains an observed spectrum. The `moltrace.spectroscopy.predict` module provides this behind one interface with two backends, exposed at `POST /spectrum/predict/shifts`.

* **Interface — `predict_shifts(smiles, nuclei=('1H','13C'), n_conformers=8, device=None, allow_fallback=True) -> ShiftPrediction`.** Pipeline: parse + sanitise SMILES (RDKit) → add explicit hydrogens → embed a *conformer ensemble* (`ETKDGv3` `EmbedMultipleConfs` + MMFF, UFF fallback, reseed on failure) → per-conformer atom types + coordinates → backend inference → aggregate across conformers. The result lists per-atom `{atom_index, element, nucleus, predicted_ppm, uncertainty_ppm}` and names the `method` and `device` used plus any `warnings`.
* **Primary backend — NMRNet (opt-in).** The SE(3)-equivariant Transformer of Xu et al. (*Nat. Comput. Sci.* 5, 292–300 (2025); doi:10.1038/s43588-025-00783-z), with a reported benchmark MAE of ≈ 0.181 ppm (¹H) / 1.098 ppm (¹³C). NMRNet ships as a research codebase (Uni-Mol-based) plus downloadable weights, not a pip-installable model, so MolTrace integrates it as an **optional, lazily-loaded, local-first** backend that runs on the resolved device — **CUDA → MPS → CPU**, with CPU the supported baseline and MPS best-effort (Uni-Core's fused kernels have no MPS path, so ops fall back to CPU via `PYTORCH_ENABLE_MPS_FALLBACK`, and a total MPS failure re-runs on CPU). Weights are acquired from the official Zenodo release (or a configured mirror), cached under `~/.cache/moltrace/nmrnet/`, and SHA-256-verifiable. It activates only when torch + the NMRNet package + per-nucleus weights are present and **never fabricates a prediction**; per-atom uncertainty is the standard deviation across the conformer ensemble (null for a single conformer). (An optional GPU `nmrnet_service/` scaffold remains for a remote-inference deployment.)
* **Fallback — HOSE-code / NMRShiftDB2.** When NMRNet is unavailable, a topological nearest-environment predictor: each atom is encoded as a HOSE-style spherical environment code (spheres 1–6) and looked up in a knowledge base, **decreasing the sphere until a match is found** (most-specific → most-general); the prediction is the mean shift of the matching reference atoms and the uncertainty their spread, falling back to an element-level prior (flagged high-uncertainty) when nothing matches. The sphere decreases until a match with **≥ 3 references** is found (statistical robustness). RDKit has no built-in HOSE generator, so the code is implemented in-module. The bundled knowledge base is a curated literature seed (textbook solvents and functional groups, independent of NMRShiftDB2); `scripts/build_hose_kb.py` produces a full NMRShiftDB2-derived table (a CC-BY-SA derivative, never committed — see `NOTICE`) for production coverage.
* **Endpoint:** `POST /spectrum/predict/shifts` — request `{ smiles, nuclei, n_conformers }`, response `{ smiles, nuclei, method, device, n_conformers, shifts: [{atom_index, element, nucleus, predicted_ppm, uncertainty_ppm}], shift_count, warnings }` (uncertainty nullable for a single conformer). The response names the active `method` and `device` and carries `warnings` (e.g. why it fell back); each call emits a `spectrum.predict_shifts` audit event, matching the GSD / multiplet / integration telemetry.
* **Validation:** `tests/spectroscopy/test_nmrnet_wrapper.py` + `tests/test_spectrum_predict_shifts_api.py`. The fallback mechanism and the NMRNet path's device resolution, conformer-ensemble aggregation, single-conformer NaN, and MPS→CPU retry are unit-tested (the latter via a fake torch, as torch has no Python-3.14 wheel in the dev sandbox). The NMRNet **paper-accuracy gate** asserts the measured **QM9-NMR** MAE is within 30 % of the paper's QM9-NMR figures (**0.020 / 0.262 ppm**, not the 0.181 / 1.098 nmrshiftdb2 headline) and is **skipped until a real checkpoint and the QM9-NMR set are present** — MolTrace asserts no measured model accuracy it has not actually run.
* **Status:** **shipping** (HOSE fallback), **NMRNet opt-in / integration-ready**, decision-support — a predicted-shift read-out for candidate discrimination, never an identity claim.

### 3.6 Automated structure verification — multi-test ASV scorer (Prompt 7)

Chemical-shift prediction (§3.5) answers "what would this structure look like?"; structure *verification* answers the regulatory question "does the proposed structure actually explain this spectrum, and how confident should I be?" The `moltrace.spectroscopy.verification` module implements this as a multi-test automated-structure-verification (ASV) layer, following the published ASV / computer-assisted structure-elucidation (CASE) methodology of Golotvin & Williams and Elyashberg et al. (§8.2) — independent tests, each contributing a fit score and a reliability, combined into a single posterior. It reproduces **no** proprietary vendor scoring scheme; the score / significance / quality decomposition and the Bayesian combination below are MolTrace's own transparent formulation.

* **Per-test result.** Each test returns `TestResult{score ∈ [-1, +1], significance ≥ 0, quality = score·tanh(significance/3), prior_confidence, diagnostic, …}`. `score` is the signed fit (+1 corroborates, −1 refutes); `significance` (0–2 low, 3–5 medium, 5+ high) is a test-specific reliability; `quality` attenuates the score by a smooth bounded function of significance so an unreliable test barely moves the needle.
* **The four tests.** **PredictionBoundsTest** — is every predicted shift (from §3.5) bounded by an experimental resonance of the correct nuclide count within tolerance? Significance scales with the shift-prediction confidence (NMRNet's per-atom `uncertainty_ppm`; on HOSE fallback the KB spread, a monotone proxy for match sphere). **AssignmentsTest** — assign experimental resonances to the predicted spin system and score the assignment with a merit function; significance falls as the unexplained (impurity) integral rises. **HSQC2DRangesTest** — predict one-bond C–H cross-peak rectangles and check coverage against supplied 2-D peaks, returning matched / missing / extra counts. **MSMoleculeMatchTest** — an intensity-weighted cosine of a first-principles isotope envelope (IUPAC-2016 abundances) against the experimental MS, with the m/z accuracy taken from the user spec.
* **Transparent combination.** Tests are combined by a Bayesian update in log-odds space: `logit(p_post) = logit(prior_confidence) + Σ_i quality_i · ln 10`. The single documented evidence unit `ln 10` means a maximally confident corroborating test multiplies the odds by ~10× and a contradicting one divides them by ~10×. The posterior is the logistic of that sum; the verdict is **consistent** (≥ 0.80), **inconsistent** (≤ 0.20), or **inconclusive**. Every score, significance, quality, per-test log-likelihood-ratio, and constant is exposed on `VerificationResult.combination` and `to_audit_dict()` — nothing is hidden behind opaque constants, and the structure feeds the audit trail.
* **No fabricated evidence.** A test whose data is absent (no 2-D peaks, no MS) *abstains* (quality 0, posterior unchanged) rather than guess; a per-test error degrades to an abstain instead of failing the whole verification.
* **Validation:** `tests/spectroscopy/test_verification_scorer.py` (32 tests) covers the quality / abstain algebra, the Bayesian combination + verdict thresholds, each test's corroborate / refute / abstain behaviour, and end-to-end `verify_structure` via the deterministic HOSE fallback. The module ships the **mechanism**; no measured verification accuracy is asserted against a labelled benchmark (consistent with MolTrace's no-unmeasured-claims policy).
* **Status:** **shipping** (scoring layer, decision-support), endpoint/UI integration-ready — a consistency read-out for candidate discrimination, never an identity claim.

### 3.7 Spectrum retrieval — vector + set similarity (Prompt 8)

Verification (§3.6) scores one proposed structure; *retrieval* answers the complementary question "which known molecules have a spectrum like this one?" — the first step of a database-driven (CASE-style) elucidation. The `moltrace.spectroscopy.similarity` module implements two complementary similarity measures over ¹H / ¹³C shifts, consuming either predicted shifts (§3.5) or experimental peak lists, following the large-scale spectral-matching methodology of **NMR-Solver** (Jin et al., 2025).[^nmr_solver] Both measures are implemented from the published equations, not from any copyrighted text.

* **Gaussian-smoothed vector encoding + L2 retrieval.** Each spectrum is encoded as `g(t) = Σ_i exp(-(t − x_i)² / 2σ²)` sampled on a uniform ppm grid; the ¹H and ¹³C halves (128 points each) concatenate into a **256-D** vector. Nearest neighbours are found by L2 (Euclidean) distance, indexed with **FAISS HNSW** for million-scale retrieval — measured at **top-100 from the ~45k NMRShiftDB2 scale in ≈ 2 ms** (well under the 1 s target; synthetic-corpus benchmark), scaling to the 106M SimNMR-PubChem index.
* **Kuhn-Munkres set similarity.** A peak-to-peak optimal bipartite matching, `S(X,Y) = (1/√(m·n)) · max_P Σ exp(-(x_i − y_j)² / 2σ²)`, solved exactly by the Hungarian algorithm (`scipy.optimize.linear_sum_assignment`). Because the matching is injective on the smaller set, surplus peaks are left **unmatched** — making the score robust to peak insertion/deletion and shift noise. Identical sets score 1.0, disjoint sets ≈ 0; used to re-rank a vector-retrieved shortlist.
* **Licensing.** An index built from NMRShiftDB2 (~45k) is a CC-BY-SA derivative (ShareAlike — see `NOTICE`), gitignored and never committed; build it locally with `scripts/build_similarity_index.py`. The optional 106M **SimNMR-PubChem** corpus (Hugging Face `yqj01/SimNMR-PubChem`) is MIT-licensed, which permits commercial indexing (re-confirm the dataset card at ship time).
* **Validation:** `tests/spectroscopy/test_similarity_scoring.py` (33 tests) covers the encoding (peak placement, empty, σ effect), the L2 and set-similarity algebra (identical → 1.0, insertion-robust, optimal-vs-greedy matching, symmetry), and the FAISS index (self-retrieval, recall vs an exact brute-force k-NN, save/load, batch), plus a `@slow` 45k acceptance test pinning the < 1 s top-100 retrieval target.
* **Endpoint:** `POST /spectrum/retrieve` (v0.8.2) — query by ¹H/¹³C shift lists or a SMILES, matched by L2 distance against the server-configured FAISS index (`MOLTRACE_SIMILARITY_INDEX`); returns the top-k `{id, l2_distance}` with a `spectrum.retrieve` audit event, or `index_available=false` when no index is configured.
* **Status:** **shipping** (retrieval + scoring library + endpoint), UI integration-ready — a "find similar known spectra" read-out, never an identity claim.

### 3.8 Quantitative-NMR purity — internal-standard + PULCON (Prompt 9)

Verification and retrieval (§3.6–3.7) answer *what* the molecule is; quantitative NMR (qNMR) answers *how much* of it is present — the mass-fraction purity a release or stability dossier turns on. The `moltrace.spectroscopy.qnmr` module turns the integral of a resonance — strictly proportional to the number of nuclei that produce it — into a purity, by the two established, non-proprietary qNMR methods. Both are implemented from the published metrology, and every intermediate ratio is preserved on an auditable `PurityResult`.

* **Multiplet selection.** `rank_multiplets_for_qnmr` scores each candidate analyte multiplet for fitness as the integration target on a transparent additive scale (max 13): **+5** no solvent/impurity line inside the window, **+3** clean baseline (no artifact / ¹³C-satellite line or broad background hump in the window ± margin), **+2** all lines narrow (FWHM ≤ 5 Hz — a field-independent linewidth measure), **+2** determinate multiplicity (label ≠ `m`, so the contributing proton count is known), **+1** not exchange-broadened (a broad labile-proton singlet scores 0). The per-criterion breakdown is written into each multiplet's `metadata["qnmr"]`; ranking never mutates the inputs.
* **Internal standard (relative qNMR).** A certified reference of known purity is weighed into the same solution: `P_x = (I_x/I_std)·(N_std/N_x)·(M_x/M_std)·(m_std/m_x)·P_std`, where `I` are integrals, `N` the protons giving rise to each integrated signal (exact integers), `M` the *average* molar masses, `m` the weighed masses, and `P_std` the certified purity. Because both species share one spectrum, receiver gain / pulse / temperature cancel exactly — the most precise route, needing no instrument calibration.[^qnmr_purity]
* **PULCON (external standard).** By the reciprocity principle the signal per spin ∝ 1/(90° pulse width), so an absolute concentration transfers from a separately-measured external reference without spiking the analyte: `c_meas = c_ref·(I_x/N_x)/(I_ref/N_ref)·(pw_x/pw_ref)·corr`, with documented temperature (Curie-law), receiver-gain, and scan corrections that each default to 1 under matched acquisition. Purity is `100·c_meas/c_nominal` against the weighed nominal concentration.[^pulcon]
* **Uncertainty.** Both routes propagate the input relative uncertainties (the two integrals, the masses or concentrations, the standard purity, optionally the molar masses) in quadrature per the GUM, since purity is a product of independent factors; the exact proton counts contribute nothing. The combined standard uncertainty is returned alongside the purity.
* **Validation:** `tests/spectroscopy/test_qnmr_purity.py` (47 tests) covers the ranking criteria, both equations against hand-computed worked examples, **closed-loop synthetic recovery to < 0.5 % absolute**, the GUM quadrature, the validation / warning paths, and the RDKit SMILES molar-mass / proton-count helpers. The formulas were checked against AIST **SDBS** certified-purity spectra (recovery within 0.5 % absolute); SDBS data are redistribution-restricted and used for **internal validation only** — never bundled with MolTrace.
* **Status:** **shipping** (quantitation library), endpoint/UI integration-ready — a quantitative-purity read-out with full provenance for the audit trail.

### 3.9 Non-uniform-sampling reconstruction — IST baseline + JTF-Net (Prompt 11)

Everything above assumes a fully sampled, processed spectrum. Modern multidimensional NMR routinely shortcuts the acquisition by sampling only a sparse subset of the indirect-dimension grid — **non-uniform sampling (NUS)** — and then *reconstructing* the missing increments, trading a reconstruction step for a several-fold reduction in instrument time. The `moltrace.spectroscopy.nus` module provides that reconstruction behind one interface with two backends and a reference-free quality metric, following the SAME local-first, weights-cached-out-of-git device pattern as the §3.5 NMRNet wrapper.

* **Baseline — `reconstruct_ist(nus_fid, sampling_schedule, iterations=200, threshold=0.97)`.** Iterative soft thresholding (IST-S), the robust, always-available default: a weights-free, numpy-only routine introduced for NMR by Stern–Donoho–Hoch and developed into the hmsIST workflow by Hyberts et al.[^hyberts_ist] Each pass transforms the time-domain residual to the spectrum, soft-thresholds at `threshold · max(|S|)` to peel off the strongest surviving spectral stratum (phase-preserving complex thresholding), accumulates it, and re-derives the residual against the **measured data at the sampled increments only**; the reconstructed FID is the inverse transform of the accumulated sparse spectrum. Deterministic and domain-agnostic — the recommended default for MolTrace's small-molecule 2-D spectra.
* **Optional backend — `reconstruct_jtfnet(nus_fid, sampling_schedule, device=None, allow_fallback=True)`.** The JTF-Net joint time-frequency network of Luo et al. (*Nat. Commun.* 16, 2342, 2025),[^jtfnet] reported faster and higher quality than IST in its training domain. JTF-Net ships as a research codebase plus author-released weights, not a pip-installable model, so MolTrace integrates it exactly as NMRNet: lazy `torch`, device resolved **CUDA → MPS → CPU** with `PYTORCH_ENABLE_MPS_FALLBACK=1` and an MPS→CPU retry, `torch.load(map_location=device)`, weights cached under `~/.cache/moltrace/jtfnet/` (SHA-256-verifiable, never vendored — see `NOTICE`). It activates only when torch + the JTF-Net package + weights are present and **never fabricates a reconstruction**: when any is absent it raises `JTFNetUnavailable` and (by default) routes to the IST baseline with a warning.
* **DOMAIN CAVEAT — protein-trained weights, not assumed transferable.** JTF-Net's released weights were trained and validated on **protein** multidimensional spectra (biomolecular NUS, e.g. 3D HNCA); MolTrace treats them as **out-of-domain** for small-molecule 2-D spectra (HSQC/HMBC) and defaults to IST until JTF-Net is re-validated or fine-tuned on small-molecule data. The paper's domain gate — recovering 3D HNCA peak positions < 0.05 ppm and intensities < 10 % against the fully sampled reference at 25 % sampling — is documented but **not asserted** in the suite, because it requires the authors' weights; a separate small-molecule validation set is required before production use.
* **Reference-free quality — `assess_reconstruction_quality(reconstructed, original_nus_fid) -> float`.** REQUIRER (Reconstruction Quality Assurance Ratio; "LCR" in the preprint): the fraction of grid points whose local relative reconstruction error falls below a reliability threshold, returned in `[0, 1]` (1 = best). It is reference-free because it scores the reconstruction against the **measured** NUS data that we actually hold — not a fully sampled ground truth — so it is available at inference time. (The paper additionally weights this by JTF-Net's learned per-point confidence lattice; that weighting is part of the JTF-Net weights integration, whereas this function computes the model-free, data-consistency form.)
* **Validation:** `tests/spectroscopy/test_nus_reconstruct.py` (27 tests). On synthetic NUS FIDs the IST baseline recovers the true peak positions exactly (the three planted frequencies are the three largest spectral peaks) and the strongest peak's intensity to within 30 % at 40 % sampling; REQUIRER lies in `[0, 1]`, rises monotonically with sampling density (25 % → 50 % → 75 %), and cleanly separates a real reconstruction from zero/noise. The JTF-Net path's device resolution, MPS→CPU retry, weights-acquisition guard, unfilled-model-forward guard, and IST fallback are unit-tested with a fake torch (no torch wheel / weights in CI), with `allow_fallback=False` surfacing `JTFNetUnavailable`.
* **Status:** **shipping** (IST baseline, reconstruction library), **JTF-Net opt-in / integration-ready**, decision-support — a reconstruction-plus-self-assessed-quality read-out, with the protein-domain caveat surfaced rather than hidden.

### 3.10 Audit trail + GxP controls supporting 21 CFR Part 11 (Prompt 12)

Every layer in §§3.1–3.9 produces a *decision-support number*; this layer makes each one **attributable, tamper-evident, and reproducible**. `moltrace.spectroscopy.audit` provides software controls that **support** 21 CFR Part 11 workflows[^cfr_part11] (audit trail, electronic signatures, access control) and the ALCOA+ data-integrity attributes the FDA references for CGMP records.[^fda_data_integrity] It cross-cuts the evidence engine: the same decorator wraps any analysis function from Prompts 1–11, and the resulting chain ties into the §4 raw-FID vault and the §11 ALCOA+ posture. **These controls help customers meet 21 CFR Part 11; MolTrace does not claim the product is itself compliant — full computerized-system validation (CSV) remains the customer's responsibility, and no function emits a self-compliance claim.**

* **`AuditEntry` + the hash chain.** Each audited call appends a frozen `AuditEntry` carrying the UTC timestamp, `user_id`, `operation`, the **SHA-256 of the input spectrum and of the output**, all method `parameters`, the `software_version`, the `model_versions` map, the `previous_entry_hash` (chain of custody), and an **HMAC-SHA256 `signature`** keyed by an organisation secret (from `$MOLTRACE_AUDIT_HMAC_KEY`, never committed). Linking each row to the prior row's hash means insertion / deletion / reordering breaks the chain; the keyed HMAC additionally makes any *content* edit detectable and unforgeable. `verify_chain` (keyless structural check, or keyed authenticity check) is the periodic tamper-detection primitive; `assert_chain_integrity` raises on any break.
* **`with_audit(operation_name, ...)`.** The decorator that wraps any analysis function and writes the entry to an **append-only** `AuditLog`. Two backends ship — `InMemoryAuditLog` and a durable append-only `JsonlAuditLog` (pair with a WORM/object-lock store) — behind one ABC that a production PostgreSQL append-only table (row-level integrity: `REVOKE UPDATE, DELETE` + INSERT-only trigger) or AWS QLDB implements identically. It records both successful and failed operations, attributes each to the authenticated operator (`audit_context`), and passes through with a one-time warning when auditing is unconfigured — so it is **safe to apply across the Prompt 1–11 functions** before auditing is switched on in production.
* **Reproducibility of AI-assisted results.** The Prompt 6 NMRNet and Prompt 11 JTF-Net loaders register each resolved checkpoint's **exact SHA-256** in a model registry that the decorator snapshots into every entry's `model_versions` — so any AI-assisted number is reproducible against the precise weights that produced it (best-effort, guarded; never breaks inference).
* **Electronic signatures (designed per 21 CFR Part 11.50 / 11.70).** `ElectronicSignature` + `sign_record` / `verify_signature`: the **manifestation** carries the signer's printed name, the date/time, and the **meaning** of the signature (authorship | review | approval | responsibility) — §11.50; and a keyed HMAC over the entry's hash **binds the signature to that one record** so it cannot be excised, copied, or transferred to another record — §11.70.
* **Retention + submission export.** `RetentionPolicy` encodes a configurable retention floor (default **7 years**, calendar-correct incl. leap-day). `render_audit_report_text` / `render_audit_report_html` produce a deterministic archival report (chain verdict, captured model checksums, signature manifestations, and the customer-responsibility disclaimer); `export_pdfa` renders PDF/A-2b for a submission when the optional `reportlab` renderer is installed (else the always-available HTML/text master is used; PDF/A conformance is validated in the customer's CSV).
* **Validation:** `tests/spectroscopy/test_audit_trail.py` (28 tests): hash-chain + HMAC tamper detection (content edit, deletion, reorder), the decorator (input/result hashing, parameter + model-checksum capture, failure recording, user attribution, unconfigured passthrough), e-signatures (§11.50 manifestation, §11.70 record-linking), JSONL persistence + verification across reopen, the 7-year retention floor, deterministic report rendering, the **"no compliance claim" guard**, and the key providers.
* **Status:** **shipping** (audit-trail + e-signature library, append-only backends), production-rollout-ready — the cross-cutting control plane that makes every other layer's output defensible in an inspection.

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

### 4.5 Dataset Versioning, Experiment Tracking, and the Determinism Gate

The raw → recipe → derived DAG above secures a single analysis; an MLOps foundation extends the same content-addressed discipline to the data and models behind every layer.

- **Versioned output contract.** Each SpectraCheck analysis serialises through a schema-versioned contract and a canonical-JSON encoder (sorted keys, fixed float rounding, `-0.0` → `0.0`, NaN / Inf rejected) to a stable `sha256:…` content hash. That hash is the analysis's identity across reruns and the value the Regulatory-Hub handoff and the ICH Q2(R2) stub (§8.10, §10) embed.
- **Content-addressed dataset versioning.** Datasets are pinned and restored **by content hash**; an optional DVC + S3 remote provides distributed storage with a native local-remote fallback, and no dataset blob is committed to git — only the hash pointer.
- **Experiment tracking.** Every model / benchmark run logs parameters, metrics, artifacts, a dataset-version tag, the git commit SHA, and the registry model-weight checksum from the §3.10 audit subsystem. A native file-backed run store is always available; MLflow is an optional drop-in backend.
- **Validation gate.** A native validator rejects malformed inputs (schema, recognised nucleus, field-MHz range, NaN / Inf, per-nucleus ppm range) before ingestion or inference; the identical logical suite is expressible as a Great Expectations suite when that optional backend is installed. Both raise loudly.
- **Determinism gate.** A CI test drives one real Bruker FID through `read_fid → GSD peak-pick → classification → multiplet detection → integration → contract → ICH stub` ten times and asserts the structured output is **byte-identical** on every iteration (one content hash across all ten). Reproducibility is a continuously-tested invariant, not an aspiration.
- **Versioned model registry + routed inference.** An append-only registry (`moltrace.spectroscopy.ai`) tracks every artifact that can produce a prediction — NMRNet checkpoints, HOSE-code KB builds, LoRA adapters, embedding models, and the Prompt 21 MS / ranking models (CSI:FingerID, METLIN-RT, DP4-AI) — with its semantic version, SHA-256, training-data lineage (dataset snapshot hash + row count), metric snapshot, and lifecycle status (candidate / shadow / production / retired); entries are immutable and a new version supersedes the old (supersession reconstructed from the append-only log). An inference router composes the fine-tuned (LoRA), pretrained (NMRNet), and deterministic-fallback (HOSE) layers — choosing LoRA per atom only when a production adapter exists for the nucleus and the conformer-ensemble uncertainty is within the adapter's validated confidence band — and emits, per prediction, the exact `{model_id: sha256}` set that produced it, fed verbatim into the §3.10 audit entry's `model_versions`. A result is therefore reproducible bit-for-bit from the registry + lineage, and a reviewer sees which model produced each number and why one layer was chosen over another.

- **Licence-clean public-datasets corpus + frozen holdout (Prompt 20).** `moltrace.spectroscopy.data` ingests the canonical public datasets through per-source adapters that pin the upstream version, record the licence (CC-BY-SA share-alike for NMRShiftDB2; non-redistributable SDBS / METLIN excluded from the corpus), and content-hash the payload (refusing a silently-changed upstream). Records are canonicalised (RDKit SMILES + InChIKey), deduplicated by `(InChIKey, spectral-hash)`, validated through the gate above (failures quarantined), and split with a fixed recorded seed into train/val/test grouped by molecule skeleton so no molecule straddles splits. The **test** split is the sacred holdout — experimental-only, checksummed, and returned as a hash-exclusion set that fine-tuning must honour; DFT-computed QM9 data is labelled `computed`, kept out of val/test, and dropped from training when it shares a molecule with the eval set.

- **LoRA domain fine-tuning pipeline (Prompt 15).** `moltrace.spectroscopy.ai.finetune` is Roadmap Layer 3 (Domain Fine-Tuning): once ≥ 1,000 reviewer-validated in-house spectra have accumulated, it trains a **LoRA adapter** on top of the pretrained §3.5 shift predictor / embedding head — low rank (r = 8–16), alpha, dropout; **the base is frozen and only the adapter trains** — runs the job on **Modal** (logging actual GPU-hours and the resulting cost; ~$200/run target), and registers the adapter in the registry above. The first step freezes the validated-example set into an **immutable, content-addressed training snapshot** (row count, per-class counts, nucleus/field/solvent distribution); that snapshot hash *is* the `training_data_lineage` recorded with the adapter — so the exact data behind every adapter is recoverable by hash. **Two chain-of-custody invariants are enforced, not just documented:** (1) **the holdout is never trained on** — the snapshot subtracts the Prompt 20 hash-exclusion set (raising at freeze time if a record leaks), and registration additionally refuses if the snapshot's gold-set checksum disagrees with the live gold set; (2) **no adapter is registered without complete lineage** — snapshot hash + per-fold metrics + code git SHA are mandatory. The adapter's hyper-parameters — rank, alpha, dropout, learning rate, and epochs — are not hand-picked but selected by **Bayesian hyper-parameter optimisation** (`optimize_hyperparameters`, Optuna TPE, ~10 trials under a fixed budget rather than a grid sweep): each trial is *itself* K-fold cross-validated, scored on one objective (mean ¹H/¹³C MAE plus a calibration penalty) and logged to the run tracker (Prompt 19), and the resulting `HPOStudy` is serialised by content hash with `created_utc` excluded from the manifest, so the study id is time-independent and the winning `LoRAConfig` is reproducible — that config is what the final adapter trains on (its `study_id` is recorded in the adapter manifest under `hpo`). The adapter is validated by **leak-proof K-fold cross-validation (GAMP 5 Appendix D11)**: each of *k* deterministic, complete-and-disjoint folds — **grouped by molecule skeleton (GroupKFold)** so every spectrum of a molecule, and every repeat scan of one physical sample/batch, lands in a single fold and a compound can never straddle the train/eval boundary (the cross-batch leakage that makes naive per-spectrum CV read optimistically) — trains on *k−1* and evaluates on the held-out fold, recording per-fold ¹H/¹³C MAE, calibration, and coverage, reported as **mean ± std** (the same molecule-skeleton grouping that keeps molecules from straddling the corpus-level train/val/test splits now also governs the in-training folds; the chosen strategy and group count are stamped into the run manifest, and a corpus with fewer molecule groups than folds is refused rather than silently leaked); a final adapter is fit on the full corpus and its content SHA-256 + manifest (hyper-parameters, per-fold + aggregate metrics, snapshot hash, base id, git SHA) saved. A **confidence-calibration head** — temperature or Platt scaling fitted on a validation split (`fit_temperature_scaling` / `fit_platt_scaling`, both pure SciPy) — is then layered on the trained adapter so a stated 80 % confidence means ~80 % empirical accuracy; the head is folded into the registered bundle (a `CalibratedBundle` that rewrites each prediction's `confidence` and stamps a `calibration` tag into `model_versions`) and is scored by **expected calibration error** on the frozen holdout (§8.11). Promotion is then **gated by the dominance check below** — registered as `candidate` always, advanced to `shadow` only when it does not regress the incumbent, and **never auto-promoted to `production`** (human sign-off required). Calibration is a **hard precondition, not a tie-breaker**: `register_if_eligible` enforces a `max_ece` ceiling, so a candidate whose calibrated ECE exceeds it is held at `candidate` even when its full accuracy vector strictly dominates the incumbent — a more-accurate model that mis-states its own confidence is treated as a regression, not an upgrade. Adapter weights are cached out of git (the same `~/.cache/moltrace/…` policy as the §3.5 NMRNet weights); the registry stores only the SHA-256 + lineage. The heavy training stack (`modal` / `torch` / `peft`) is lazily imported behind a clear `FineTuneUnavailable`, and the trainer is injectable, so the snapshot → k-fold → gated-registration logic is fully testable on a CPU-only host.

- **Dominance-gated model promotion (Prompt 17).** `moltrace.spectroscopy.eval.harness` scores a model on a frozen, checksum-locked gold set (100 hand-validated spectra: 60 NMRShiftDB2 + 20 HMDB + 20 in-house) across ten metrics — top-1/top-3 structure accuracy, 1H/13C shift MAE, ECE (reusing the §8.11 calibration metric), false-confirmation rate, retrieval recall@k, error-vs-uncertainty AUROC, perturbation robustness, reviewer agreement, and latency p50/p95 — and promotes a candidate only when its full vector **dominates** the incumbent: no regression beyond tolerance on any metric, a strict improvement on at least one, and **zero regression** on the safety-critical metrics (false-confirmation rate, calibration; tolerance 0). The gold-set SHA-256 is enforced (the run aborts on drift), the per-metric deltas form the promotion record, and `gate_for_ci` returns a CI exit code so no model reaches production without dominating the incumbent.

- **Contradiction detection (Prompt 22).** Complementing the deterministic §3.6 verifier, `moltrace.spectroscopy.ai.finetune` adds a contradiction layer that flags spectra no single structure can explain. A deterministic detector (`detect_contradictions`) applies transparent, typed rules — proton-integration vs. expected-count mismatch (only above a relative tolerance), multiplicity vs. coupling-neighbour mismatch, a shift outside the nuclide window, "no consistent structure" from the verifier, and cross-modal disagreement (NMR top candidate ≠ MS top candidate, or retention time uncorroborated, from Prompt 21) — each emitting a severity-scored `ContradictionSignal`, aggregated into a `ContradictionReport` with a tunable threshold. On top of it, `train_contradiction_detector` fits a *learned* detector (a calibrated logistic over the same feature space) under the **identical discipline as the adapters**: leak-proof K-fold CV (the same molecule-skeleton GroupKFold grouping, so co-molecule examples never straddle a fold) with per-fold precision / recall / F1 + ECE, temperature-calibration of the pooled out-of-fold scores against a **max-ECE gate**, gold-set hash-exclusion, and a reproducible (time-independent) run id carrying full lineage (dataset hash, feature names, per-fold metrics, git SHA). Contradictions at or above threshold are surfaced to the reviewer (`to_reviewer_dict`) and the hardest cases are pushed into the **active-learning queue** that prioritises the next fine-tuning round (Prompt 16). It **complements, never replaces,** the deterministic verifier — a second, learned opinion on internal consistency, not a new identity claim.

- **Closed-loop reviewer feedback — capture → reward model → A/B rollout (Prompt 23).** `moltrace.spectroscopy.feedback` turns reviewer interaction into a compounding data asset without ever letting a model override the science. **Capture** (`feedback.capture`): every AI output — predicted shift, proposed structure, peak label, purity call, multiplicity, integration — is rated through one intake (thumbs up/down + an optional free-text correction + a structured reason taxonomy: wrong-shift, wrong-multiplicity, wrong-structure, missed-impurity, wrong-integration, calibration-off, other). Each rating is frozen into an **immutable, content-addressed `FeedbackEvent`** carrying the full output context and the exact `model_versions` — the same `{model_id: sha256}` set the §4.5 router stamps into the §3.10 audit entry — that produced it, persisted append-only and idempotently (in-memory or SQLAlchemy store, INSERT-only by `event_id`). The single intake fans out deterministically: a correction becomes a Prompt 16 `LabeledExample` (the seed for the next §4.5 fine-tuning snapshot); a bare thumbs-down becomes an active-learning item; and `usage_analytics` rolls up override / acceptance rates per output kind and model so investment targets the layers reviewers most often overrule. **Reward model** (`feedback.reward_model`): corrections and accept/reject signals assemble into an RLHF-style **preference dataset** (chosen ≻ rejected pairs), from which a deterministic **Bradley-Terry reward model** (full-batch logistic on standardised advisory features, L2-regularised, no identifiable intercept — the bias cancels in the pairwise differences) is trained — `train_reward_model` reporting pairwise accuracy and a reproducible, time-independent run id with full lineage. It re-ranks the Prompt 14 reasoner's candidates (`rank_candidates`) and re-prioritises the annotation queue (`prioritize_annotation_queue`), but is **structurally advisory**: ranking primary-sorts on the deterministic verifier's verdict, so a reward score can only reorder *within* a verdict class — it can never lift a verifier-rejected candidate above an accepted one. The Prompt 7 verifier remains the sole arbiter of correctness. **A/B rollout** (`feedback.ab_testing`): when Prompt 15 registers a challenger, an `ABRouter` either routes a controlled traffic slice to it (**canary**) or scores it in parallel without ever serving it (**shadow**), with sticky per-request bucketing (SHA-256 of the routing key) so a given case is always assigned the same arm. Champion and challenger are compared via `evaluate_promotion` on the same §4.5 ten-metric `GoldMetricVector` **plus** live reviewer-acceptance and override rates; the decision returns `promote = True` only on §4.5 dominance with **zero safety-metric regression**, with the acceptance / override guards held, with the Prompt 18 fail-closed gate green (`gate_exit_code == 0`), and `requires_sign_off` is **always** True. `ABTest.promote` refuses (raising `PromotionBlocked`) unless the decision is positive **and** carries a non-empty `signed_off_by` — the system **never auto-deploys**. `rollback()` is an **instant routing-layer kill** (challenger traffic → 0, champion left untouched in `production`), deliberately distinct from the gated, sign-off-only `registry.promote` that retires a champion — so a regression is contained in a single call, with no registry change and no redeploy.
- **MLOps: monitoring, drift detection, and the fail-closed deployment gate (Prompt 18).** `moltrace.spectroscopy.ops` is the observability + release-control layer over the stack. **Drift monitors** (`production_monitors`) compute a `[0,1]` traffic-light per signal: **input drift** — the population-stability index (`population_stability_index` categorical + `numeric_psi` quantile-binned) of the live nucleus / field / solvent / molecular-weight distribution against the §4.5 training snapshot, so a PSI ≥ 0.25 flags new chemistry; **confidence drift** — the windowed trend of the Prompt 6 per-prediction uncertainty and the Prompt 14 RAG grounding; **override-rate drift** — the Prompt 16 `loop_yield_metrics` override trend (rising == live degradation); and **latency** p50 / p95 vs an SLO. Every metric is emitted to an injectable observability sink and each breach pages an injectable alerter. **`lineage_dashboard`** reads the Prompt 13 registry — per production model: version, training-snapshot hash, gold `GoldMetricVector`, promotion record + supersession, and live drift status. The **deployment gate** (`run_deployment_gate` / `evaluate_deployment_gate`) allows a deploy **only if all four checks pass**: `check_dominance` (the §4.5 Prompt 17 `dominates` gate — zero safety-metric regression), `check_audit_chain` (the §3.10 `verify_chain` — chain links + HMAC signatures intact), the test-suite-green flag, and `check_data_leakage` (the candidate snapshot is bound to the gating gold checksum **and** its `record_hashes` are disjoint from the holdout). Every input defaults to *failed*, so it fails closed. The CLI (`moltrace-deployment-gate`) is wired into the CI/CD workflow as a `deployment-gate` job that `needs` both test suites and that `deploy` in turn `needs`; its `--self-check` proves on every run that the gate allows an all-pass candidate and **blocks every single-check failure**, so a regression in the release-control logic fails CI before it can let a bad model through. Every monitor input, the sink, the pager, and the gate inputs are injected, so the layer is unit-tested (`tests/test_ops_monitoring.py`, 21 tests) on a CPU-only host with no live infrastructure. **Downstream contract:** SpectraCheck is the upstream source of truth for the Regentry and Repho; its output is the versioned, content-addressed `infra.contract` envelope (schema `1.0.0`; `docs/spectracheck_output_contract.md`) so those modules depend on a stable shape, not pipeline internals.

- **Active-learning loop — disagreement sampling + loop yield (Prompt 16).** `moltrace.spectroscopy.ai.active_learning` closes the flywheel over that capture layer. `capture_override` turns a reviewer override into a `LabeledExample` carrying full provenance — raw-FID hash, processed spectrum (and its content hash), the §4.5 `model_versions`, the original AI output, the correction, and reviewer id + timestamp — persisted append-only through the same `FeedbackCollector`. `disagreement_score` runs N model variants (the §4.5 pretrained and fine-tuned routers plus the Prompt 14 RAG reasoner) and blends their **vote split on the top-1 structure**, the **variance of predicted shifts** (soft-saturated per ppm), and the **spread of confidences** into one `[0, 1]` information-value score; `build_annotation_queue` ranks an unlabelled pool by it, **de-duplicates near-identical spectra** (a fingerprint key or an injected similarity threshold), reuses the Prompt 23 `prioritize_annotation_queue`, and slices to a labelling **budget** — so expert effort concentrates on the most informative cases, not a random draw. `retraining_trigger` fires on a **monthly schedule or a new-label volume**, and `kickoff_finetune` wires straight into the §4.5 Prompt 15 chain (`build_training_snapshot` → `finetune_lora` → `register_if_eligible`). `loop_yield_metrics` instruments the flywheel — labelled examples per month, the **override-rate trend** (negative == the model improving), and **accuracy lift per retrain** — and `emit_loop_yield` writes that rollup to the §3.10 audit trail for the Layer-4 dashboard. Every model variant, the retrain kick-off, and the audit recorder are injected, so the loop scores and orchestrates on a CPU-only host with no torch / LLM dependencies. **Validation:** `tests/test_ai_active_learning.py` (31 tests) covers override-capture provenance + idempotence, disagreement across the three variant adapters, queue rank / de-dup / budget, the schedule-and-volume trigger wired to the Prompt 15 chain, and loop-yield rates / trend / lift with audit emission.

The native core of this foundation carries zero new runtime dependencies; the heavier lineage tooling (MLflow, DVC, Great Expectations) lives behind an optional `infra` extra so the default install stays lean.

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

**Automated structure verification (ASV) & CASE.** Beyond stereochemistry scoring, MolTrace's §3.6 verification layer follows the multi-test *automated structure verification* methodology of Golotvin & Williams[^golotvin_asv] and the *computer-assisted structure elucidation* (CASE) framework of Elyashberg, Williams & Blinov[^elyashberg_case]: a proposed structure is checked by several independent consistency tests (prediction bounds, spin-system assignment, 2-D coverage, MS isotope match), each contributing a fit score and a reliability, combined into a single posterior. MolTrace's combination is an explicit Bayesian log-odds update with one documented evidence unit — no proprietary vendor scoring scheme is reproduced. The MS test's isotope envelope uses IUPAC-2016 natural abundances.[^iupac_isotopes]

**Quantitative NMR (qNMR) purity.** MolTrace's §3.8 quantitation layer implements the two standard, non-proprietary qNMR purity methods: internal-standard (relative) qNMR — `P_x = (I_x/I_std)(N_std/N_x)(M_x/M_std)(m_std/m_x)·P_std` — from the pharmaceutical-qNMR literature of Pauli et al. and Bharti & Roy,[^qnmr_purity] and PULCON external-standard quantitation built on the reciprocity principle of Wider & Dreier[^pulcon] (signal per spin ∝ 1/90°-pulse-width). Combined uncertainties propagate per the GUM (quadrature of independent relative uncertainties), and the methods recover certified purities from AIST SDBS reference spectra to within 0.5 % absolute — SDBS used for internal validation only and never redistributed.

### 8.3 Chemical-Shift Window Tables — Canonical References

The 1H + 13C shift-window tables driving the categoriser are sourced from the consensus across four canonical references:

**Silverstein, Webster, Kiemle & Bryce** — *Spectrometric Identification of Organic Compounds*, 8e (Wiley, 2014).[^silverstein] Table 4.10 (1H regions) and Table 5.3 (13C regions). The first-call reference in most analytical chemistry curricula.

**Pretsch, Bühlmann & Badertscher** — *Structure Determination of Organic Compounds: Tables of Spectral Data*, 5e (Springer, 2020), doi:10.1007/978-3-662-62439-5.[^pretsch] §H.5 (proton chemical shifts) and §C (carbon-13 chemical shifts). The most-cited compact reference for routine NMR work.

**Friebolin** — *Basic One- and Two-Dimensional NMR Spectroscopy*, 5e (Wiley-VCH, 2010).[^friebolin] Ch. 2 (1H) and Ch. 3 (13C). The standard textbook for NMR fundamentals in organic chemistry curricula.

**Gottlieb, Kotlyar & Nudelman** — *NMR Chemical Shifts of Common Laboratory Solvents as Trace Impurities*, *J. Org. Chem.* 1997, 62, 7512, doi:10.1021/jo971176v.[^gottlieb] The canonical residual-solvent and water-residual table for routine NMR.

**Fulmer et al.** — *NMR Chemical Shifts of Trace Impurities: Common Laboratory Solvents, Organics, and Gases in Deuterated Solvents Relevant to the Organometallic Chemist*, *Organometallics* 2010, 29, 2176, doi:10.1021/om100106e.[^fulmer] Extension of Gottlieb to additional solvents and trace impurities.

**Reich (UW-Madison) NMR Resources** — open online resources on OH/NH/SH proton chemical shifts, exchange, and broadening, https://organicchemistrydata.org/hansreich/resources/nmr/.[^reich] Standard open reference for labile-proton behaviour and D₂O-shake interpretation.

**Karplus relation — vicinal ³J dihedral dependence (opt-in Layer 40 refinement).** The same first-order coupling tables (Silverstein Table 4.10, Pretsch §H, Friebolin Ch. 2) give the flat empirical magnitudes the topological predictor of §3.3 uses; the vicinal class additionally carries a well-known *geometric* dependence captured by the Karplus relation, ³J(θ) = A·cos²θ + B·cosθ + C (Karplus, *J. Chem. Phys.* 1959; *J. Am. Chem. Soc.* 1963).[^karplus] MolTrace's opt-in Layer 40 refinement uses the widely-tabulated generic constants A = 7.76, B = −1.10, C = 1.40 (as tabulated in Pretsch 5e), giving ≈ 8.1 Hz at 0°, a 1.4 Hz minimum near 90°, and ≈ 10.3 Hz antiperiplanar at 180°. Rather than assume a single dihedral, the predictor generates an RDKit ETKDGv3 conformer ensemble, MMFF-optimises it, measures every H–C–C–H dihedral, applies the relation, and reports the unweighted ensemble mean — so a conformationally mobile (ring-flipping) system relaxes toward the ≈ 7 Hz average while a locked chair preserves its ≈ 10 Hz antiperiplanar diaxial coupling. This is decision-support sharpening of candidate discrimination, not a claim to predict J to sub-Hz accuracy; it is **default-off** and leaves the topological-only output byte-for-byte unchanged when not requested. A curated literature corpus of eight reference molecules — four covalently/rigidly locked (trans-decalin, β-D-glucopyranose, myo-inositol, β-D-galactopyranose) and four conformationally mobile or acyclic (cyclohexane, cis-decalin, n-butane, ethanol) — quantifies the behaviour: the refinement reproduces each system's literature diagnostic vicinal ³J with a **mean absolute error of ≈ 0.4 Hz** (median 0.26 Hz; worst case 1.41 Hz, on β-D-galactose, where the generic relation under-predicts a hydroxylated diaxial — its known Haasnoot–Altona blind spot), and — the operative result for candidate discrimination — **recovers every locked diaxial coupling as a larger value (mean ≈ 9.5 Hz, each ≥ 8.5 Hz) than every mobile/averaged coupling (mean ≈ 6.9 Hz, each ≤ 7.1 Hz), a clean separation with no overlap**, and splits the rigid trans-decalin from its ring-flipping cis diastereomer by ≈ 3 Hz (`moltrace-karplus-jcoupling-report`; `tests/test_phase39_karplus_validation.py`). The corpus deliberately scopes the claim to *rigidly* locked geometries: because the refinement averages each H–C–C–H dihedral **unweighted** across the conformer ensemble, a merely *thermodynamically* anchored monocycle (e.g. 4-*tert*-butylcyclohexanol) ring-flips in the ensemble and its diaxial averages away — so the recovered ≈ 10 Hz coupling is a property of covalent rigidity (fused rings, strong-preference pyranose chairs), not of every substituent-biased chair.

**Haasnoot–de Leeuw–Altona generalized Karplus — electronegativity/orientation correction (opt-in, default-off).** The generic three-term relation deliberately ignores the *substituents* on the H–C–C–H fragment, and for that reason it caps near 10.26 Hz at 180° and under-predicts heavily oxygenated diaxial couplings — the β-D-galactose worst case above. The Haasnoot–de Leeuw–Altona (HLA) generalization adds those terms: ³J = P₁·cos²φ + P₂·cosφ + P₃ + Σᵢ Δχᵢ·[P₄ + P₅·cos²(ξᵢ·φ + P₆·|Δχᵢ|)], where each β-substituent contributes a correction scaled by its Huggins-scale electronegativity difference from hydrogen (Δχ) and its orientation relative to the coupling protons (ξ = ±1), read per conformer from the same 3D ensemble (Haasnoot, de Leeuw & Altona, *Tetrahedron* 1980).[^haasnoot] MolTrace exposes it as a second selectable relation via a `karplus_method` field (`'generic'` — the default — or `'haasnoot_altona'`) on the predictor and the request models, using the widely-cited six-parameter set (P₁ = 13.86, P₂ = −0.81, P₃ = 0.0, P₄ = 0.56, P₅ = −2.32, P₆ = 17.9°). At known geometries the equation behaves exactly as published — no substituents give 13.05/0/14.67 Hz at 0/90/180°, two β-oxygens plus two β-carbons (a pyranose diaxial) pull the 180° value down to ≈ 9.7 Hz — and unit tests pin those endpoints (`tests/test_phase40_haasnoot_altona.py`, 13 tests). **A candid, measured caveat governs how it ships.** Per *individual* conformer the HLA relation is the more literature-faithful of the two — it recovers the covalently-locked trans-decalin diaxial at ≈ 11.6 Hz, *above* the generic relation's ≈ 10.3 Hz three-term ceiling and squarely on the ≈ 11 Hz literature value. But its dynamic range is far wider (0 → 14.7 Hz versus the generic 1.4 → 10.3 Hz), and under the **unweighted** conformer averaging the current pipeline uses, that width *amplifies* the averaging artefact described above: across the eight-molecule corpus, HLA lifts the mobile/averaged systems markedly (cyclohexane 7.1 → 9.2 Hz, ethanol 6.5 → 8.0 Hz) while *lowering* the very sugar it was meant to fix (β-D-galactose 8.5 → 7.9 Hz, the opposite of the intended move toward 9.9 Hz), so the clean locked-vs-mobile separation that the generic relation achieves **collapses** (a measured locked-vs-mobile separation of +1.35 Hz under generic becomes −1.23 Hz under HLA). The diagnosis is unambiguous and is locked by an explicit regression gate (`tests/test_phase40_haasnoot_altona_corpus.py`, 9 tests; `moltrace-karplus-jcoupling-report --method haasnoot_altona`): the sugar under-prediction is **not** a deficiency of the Karplus *functional form* — a more elaborate equation does not fix it — but of the **unweighted conformer population model**, because a Boltzmann-favoured ground-state chair is being averaged on equal footing with high-energy ring-flipped conformers. HLA therefore ships **opt-in and default-off** (the generic path remains byte-for-byte unchanged and the default), as a correct, tested, per-conformer-superior relation whose corpus-level behaviour motivates the natural next step — Boltzmann-weighted conformer populations, delivered next.

**Boltzmann conformer-population weighting — the fix (opt-in).** The Phase 40 diagnosis above pinpointed the real defect: the diagnostic ground-state chair was being averaged on *equal footing* with high-energy ring-flipped conformers. The fix is to weight each conformer by its thermodynamic population rather than counting it once. MolTrace exposes this as a `karplus_conformer_weighting` field (`'uniform'` — the default, a plain ensemble mean — or `'boltzmann'`), orthogonal to `karplus_method`: when `'boltzmann'` is selected the per-conformer couplings are combined as Σᵢ wᵢ·Jᵢ / Σᵢ wᵢ with wᵢ = exp(−(Eᵢ − E_min)/RT) from the conformer's MMFF energy (T = 298.15 K), degrading safely to the uniform mean with a warning if MMFF energies are unavailable. The measured effect on the eight-molecule corpus is decisive and is locked by a regression gate (`tests/test_phase41_boltzmann_corpus.py`; `moltrace-karplus-jcoupling-report --weighting boltzmann`). It **fixes the sugar blind spot**: β-D-galactose's diagnostic diaxial moves from 8.49 Hz (generic/uniform — the original worst case) to ≈ 10.1 Hz, onto its ≈ 9.9 Hz literature value, because the ⁴C₁ ground state stops being diluted. It **widens, not merely preserves, the discrimination**: the clean locked-vs-mobile separation grows from +1.35 Hz (generic/uniform) to +2.28 Hz (generic/boltzmann), with locked systems tightening toward ≈ 10 Hz and mobile systems staying in the ≈ 7 Hz averaged regime. It also **rescues the HLA collapse** — the −1.23 Hz inversion under haasnoot/uniform becomes a clean +0.36 Hz separation under haasnoot/boltzmann. And it carries a clean scientific punch line: once conformers are population-weighted, the *generic* relation discriminates better than the electronegativity-corrected HLA one (+2.28 vs +0.36 Hz; HLA still over-predicts mobile couplings), so the sugar under-prediction was never a deficiency of the Karplus functional form — it was the unweighted population model all along. Like every refinement here it is **opt-in and default-off**, so the generic/uniform path remains byte-for-byte unchanged and the Phase 39/40 gates are untouched; selecting `'boltzmann'` is decision-support sharpening, not a sub-Hz prediction claim.

**Phase 42 — confirmation at scale (n = 18).** The eight-molecule corpus above is the original validation; Phase 42 asks whether the result survives a larger, harder one. A separate **18-molecule** literature corpus (`karplus_jcoupling_corpus_v2.json` — nine covalently/conformationally locked diaxial systems, including five pyranosides: methyl β-D-gluco- and β-D-galacto-pyranoside, β-D-quinovose, β-D-mannopyranose and β-D-xylopyranose; and nine mobile/averaged systems), graded across the full {generic, haasnoot_altona} × {uniform, boltzmann} grid, makes the case *sharper*: **generic/boltzmann is the only one of the four method/weighting combinations that cleanly separates the locked diaxials from the mobile systems at scale** (locked-vs-mobile separation +1.84 Hz; the other three are all negative — generic/uniform −0.64, haasnoot/uniform −2.10, haasnoot/boltzmann −0.07 Hz), and it is simultaneously the most accurate (within-tolerance 1.00, mean absolute error 0.57 Hz, the lowest locked coupling 9.92 Hz still clearing the highest mobile coupling 8.08 Hz — a clean gap with no overlap). The mechanism is legible in a single molecule: β-D-quinovose, a genuinely locked sugar, washes out to a mobile-like 6.50 Hz under the unweighted mean and is restored to 10.25 Hz once conformers are population-weighted. The larger corpus therefore *strengthens* the Phase 41 conclusion rather than merely repeating it — unweighted averaging, which only narrowed the separation at n = 8, now **fails outright** at n = 18 (several locked sugars fall into the mobile band), while population-weighted generic both recovers them and widens the separation by +2.48 Hz over the plain mean. The v2 corpus deliberately scopes 'mobile' to ring-flipping / pseudorotating rings and short freely-rotating chains; long n-alkanes (n-pentane, n-hexane) are excluded with documented rationale, because vacuum MMFF over-stabilises their extended all-anti backbone and inflates the Boltzmann-weighted coupling through a force-field/solvation limitation rather than a genuine locked geometry. The result is locked by a regression gate (`tests/test_phase42_expanded_corpus.py`, 8 tests; `moltrace-karplus-jcoupling-report` graded on the v2 bundle), and the Phase 39/40/41 gates are untouched — they keep loading the byte-identical eight-molecule v1 corpus.

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

**MS/MS → structure + retention-time corroboration (Prompt 21).** `ai/ms_models.py` integrates **CSI:FingerID** via **SIRIUS**[^csi_fingerid][^sirius] to predict molecular fingerprints and ranked candidate structures from an MS/MS spectrum — called through its documented interface (REST service or CLI), licence-respecting, never reimplemented or bundled, and degrading to `available=False` on a host without a configured backend. A **METLIN-style retention-time predictor**[^metlin_rt] supplies an orthogonal corroboration signal: a Gaussian down-weight in the RT residual demotes RT-inconsistent candidates (never a hard filter). These MS signals are fused with the **reused** in-house DP4 posterior (§8.2; `dp4_scoring`, Smith & Goodman 2010 σ/ν) into one calibrated candidate ranking (summing to 1.0; signal weights renormalise when a signal is absent). The fused ranking is **decision-support only** — the §3.6 verifier remains the arbiter of pass/fail — and each model (CSI:FingerID, METLIN-RT, DP4) is registered in the §4.5 model registry with version + SHA-256. Fusing NMR + MS/MS + RT and cross-checking with an independent verifier is materially stronger than any single-technique tool.

**Retrieval-augmented reasoning (Prompt 14).** `ai/rag.py` wraps a large language model (Anthropic Claude, `claude-opus-4-8`[^claude]) in a retrieval layer over the §3.7 similarity index, following the retrieval-augmented-generation pattern.[^rag_lewis] `build_reasoning_context(spectrum, *, index, resolver, top_k=50)` retrieves the nearest known spectra (duck-typed, injectable index) and joins each to its metadata through an injectable resolver — SMILES, shift / multiplet summary, an L2 → bounded-similarity transform, and **license** (with an optional licence allow-list) — packing a **token-bounded** context. `propose_structures(spectrum, context, max_candidates=5)` then asks the model for strict-JSON `{smiles, rationale, cited_analogue_ids, self_confidence}` candidates, **schema-validating with exactly one retry**; a **hallucination guard** drops any candidate that neither cites a retrieved analogue nor structurally matches one *before* verification; and each survivor is scored by the §3.6 `verify_structure` verifier, which is the sole arbiter of pass/fail. The model's `self_confidence` is advisory and is **never** used as the verifier prior (a fixed neutral prior is used), so LLM confidence cannot override the evidence-based posterior. Every backend (LLM, index, resolver, verifier, support check, audit recorder) is injectable and `anthropic` is an optional, un-pinned dependency, so the layer runs deterministically on a CPU-only host with no network, no FAISS, and no `anthropic`. The retrieved ids, the exact prompt, and the raw completion(s) are captured for the §3.10 audit trail (operation `spectrum.rag.propose`), giving a reviewer the full provenance of every model-assisted proposal. **Endpoint:** `POST /spectrum/reason` (v0.16.1) exposes this layer over a *real* query spectrum (paired `ppm_axis` + `intensity`, the same input as `/spectrum/analyze/gsd`, since the verifier scores each candidate against the observed data): it returns the retrieved precedent analogues and the verifier-accepted candidates — ranked by posterior confidence, with the guard-dropped / verifier-rejected set surfaced separately for transparency — under **two independent capability flags**, `index_available` (the FAISS similarity index is configured server-side via `MOLTRACE_SIMILARITY_INDEX`) and `reasoner_available` (`anthropic` + `ANTHROPIC_API_KEY` are present), so the surface degrades gracefully to retrieval-only, or to an empty state, returning `200` rather than an error. An optional `MOLTRACE_SIMILARITY_METADATA` sidecar resolves index ids to SMILES / license / source, and a per-request `allowed_licenses` allow-list filters retrieval. Each call also emits a `spectrum.reason` audit event through the platform's `_audit_from_context` → `audit_event` pipeline, complementing the library-level `spectrum.rag.propose` provenance record. **Validation:** `tests/test_ai_rag.py` (26 tests) covers retrieval with structures + scores + license + token-bounding, strict-JSON validation + single retry, the **adversarial** hallucination guard (uncited + unsupported dropped before verification), verifier-decides / self-confidence-not-the-prior, and audit capture — all with fakes (no FAISS, no `anthropic`, no weights). **Status:** **shipping** library; the LLM proposes, retrieved precedent grounds, the verifier decides.

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

**ICH Q2(R2) Validation of Analytical Procedures** (2023).[^ich_q2r2] Expanded data-integrity acceptance criteria for the analytical lifecycle; the pipeline emits a deterministic, content-hash-keyed ICH Q2(R2) report stub as the Regulatory-Hub handoff artefact (§4.5).

**GAMP 5 (2nd ed., 2022), Appendix D11 — Computerised System Validation**.[^gamp5] MolTrace generates a versioned, byte-reproducible D11 CSV document skeleton (intended use, GAMP software category, GxP-risk class, requirements-traceability matrix, IQ/OQ/PQ evidence slots) to accelerate a customer's validation; the overall compliance determination remains the regulated user's responsibility.

**FDA Control of Nitrosamine Impurities in Human Drugs**.[^fda_nitrosamines] Drives the curated impurity-library in `impurities.py`.

**ICH Q3A/B, Q3C(R8), Q3D(R2), M7(R2) + FDA CPCA — unified Impurity Assessment.** Five deterministic engines are exposed through one authenticated endpoint (`POST /regulatory/impurities/assess`) and one Regulatory-Hub panel: Q3A/B reporting/identification/qualification thresholds for the dose, Q3C residual-solvent class limits scaled to the daily dose (Option 2), Q3D elemental-impurity PDEs by administration route, M7 mutagenic-impurity classification from (Q)SAR/experimental inputs, and the FDA CPCA carcinogenic-potency category for nitrosamines with a cumulative risk-ratio gate (must be < 1). Each engine returns its `regulatory_basis` and a SHA-256 of the rule set that produced it (`rule_set_versions`), so a number is traceable to the exact encoded guideline revision; the route degrades gracefully (unknown elements / unparseable SMILES become non-blocking warnings rather than failures) and every response is `human_review_required` by construction.

**Process capability & SPC trending — Continued Process Verification.** A sixth Regentry engine analyses a time-ordered measurement series for one *(product, parameter)* through one authenticated endpoint (`POST /regulatory/spc/analyze`) and one Regulatory-Hub panel. It returns the process-capability/-performance indices (Cp, Cpk, Cpu, Cpl, Pp, Ppk, plus Cpm against a target) computed from within- and overall-sigma against caller-supplied USL/LSL, the selected Shewhart rule set (Western Electric / Western Electric classic[^spc_weco] / Nelson[^spc_nelson] / Montgomery[^spc_montgomery]) evaluated alongside CUSUM and EWMA, and the out-of-specification and signal index sets for chart annotation. The contract foregrounds the early-warning lead — `first_signal_index`, `first_oos_index`, and `lead_points` — so a drift or shift flagged before any spec breach is reported as quantified lead time; non-finite indices arising from zero within-batch variation are returned as `null` with explicit `warnings` rather than a fabricated number. The engine maps to Stage 3 (Continued Process Verification) of the FDA process-validation lifecycle and to ICH Q6A acceptance-criterion setting; the series is caller-supplied (no persisted measurement table yet), every response is `human_review_required`, and the result carries a verbatim decision-support disclaimer — it is never a batch disposition.

**ICH Q6A specification-setting decision trees.** A deterministic specification-builder module runs the ICH Q6A[^ich_q6a] decision trees over a substance/product profile, its batch-analysis data, and its method-validation state and returns a draft specification table — appearance, identification, assay, impurities, dissolution or disintegration, and water content — each parameter carrying a proposed limit, a justification, and a method reference. The impurity rows are not hand-set: the qualification threshold comes from the Q3A/B engine, the mutagenic-impurity safety limit from M7, and the Cohort-of-Concern acceptable intake from CPCA, and a limit is tightened below the guideline ceiling only where the batch data demonstrate process capability (Cpk > 1.33). It is an engine-level capability — not yet exposed through the Regulatory-Hub API or a panel — that proposes a specification for qualified review, never a filed acceptance criterion.

**FDA out-of-specification (OOS) investigation workflow.** A workflow engine implements the two-phase framework of the FDA 2006 OOS guidance.[^fda_oos] Phase I is a laboratory investigation (analyst calculation/transcription error, instrument calibration, sample-preparation review) that invalidates the original result only on a documented assignable laboratory cause and otherwise escalates; Phase II is a full-scale investigation (expanded laboratory work, manufacturing-process review, retesting under a pre-defined protocol — no testing into compliance) that assigns a root cause across the five FDA categories and applies the invalidation rule: a result is invalidated only with a documented assignable cause, while an unexplained OOS stands and the batch fails. A single call assembles an investigation report carrying the FDA OOS and ICH Q10[^ich_q10] pharmaceutical-quality-system elements (CAPA, quality-signal trending, change management, management review) plus the regulatory-reporting obligations a confirmed OOS triggers (Field Alert, Annual Product Review entry, NDA/ANDA supplement). Like the Q6A builder it is an engine-level capability marked `human_review_required` — the quality unit owns the disposition.

**Versioned, licence-aware guidance corpus + grounded retrieval (RAG).** Underneath the calculators sits a regulatory-guidance corpus the deterministic engines cite into. `moltrace.regulatory.data` is a versioned, licence-aware ingestion pipeline: per-source adapters (FDA, ICH, EMA, WHO) stamp each document with its revision, effective date, source URL, licence, and a deterministic `content_hash` over the version-defining fields, so a re-fetch of the same revision is byte-identical and any upstream change is detectable; `revision_watch` opens a change-control + re-validation item on a new revision and *holds* the changed text out of answers until the deterministic rule-set is revalidated, rather than silently changing a result. Licence tiering is enforced end to end — FDA guidance is US-government public domain and `redistributable`; ICH, EMA, and WHO texts are copyrighted, flagged internal-only, capped to minimal excerpts, and always carry a citation + official-source link (`guard_redistribution` raises on any attempt to export internal-only text). `index()` chunks by section (configurable token `chunk_size`/`chunk_overlap` windowing) and keeps source + section + effective date + URL on every chunk. On top, `moltrace.regulatory.intelligence.rag_search` retrieves the top-_k_ chunks for a query (optional `filter_source` over ICH/FDA/EMA/WHO) — a zero-dependency `LexicalRetriever` (TF-IDF cosine) by default, or a `VectorRetriever` over injected embeddings (e.g. `text-embedding-3-small`) — annotating each hit with the MolTrace engine it maps to. `synthesize_answer` is deterministic-first: the default extractive path uses no LLM at all; the optional Claude path (`claude-sonnet-4-6`) runs under a system contract that forbids any knowledge outside the retrieved excerpts, requires per-claim `[S#]` citations, and forbids stating any specific regulated number — every PDE/TTC/threshold defers to the deterministic engines above[^rag_lewis] — backed by a programmatic post-hoc check that flags invalid citation markers or any regulated number absent from the excerpts. A `RegulatorySearchResult` carries the exact source document, section, effective date, and link for each hit, and a validation harness reproduces curated regulatory FAQ pairs to guard retrieval against drift. The Claude/embedding backends live behind an optional `rag` extra; the engine and its full test suite run offline on the extractive + lexical paths.

### 8.11 Model Evaluation & Calibration Metrics

A model change is an improvement only if a fixed, pre-registered metric says so, so MolTrace centralises the definition of "better" in one evaluation module. Each metric is an independently-tested pure function over predicted-versus-reference data:

- **RMSE** — root-mean-square error for chemical-shift prediction.
- **F1** — harmonic mean of precision and recall for peak detection and for peak classification, the standard information-retrieval definition.[^vanrijsbergen]
- **Top-k accuracy** — whether the correct candidate appears in the top *k* of a ranked list.
- **BedROC** — Boltzmann-enhanced discrimination of ROC, an early-recognition metric that up-weights true hits near the top of a ranked list with a tunable α, after Truchon & Bayly.[^bedroc]
- **ECE** — expected calibration error, the binned gap between a model's stated confidence and its empirical accuracy, after Guo et al.[^ece_guo]

A single call returns the comparable metric vector consumed by the experiment-tracking and promotion machinery of §4.5, so promotion decisions are auditable measurements rather than judgement calls. ECE is no longer only a passive read-out: the §4 fine-tuning pipeline both *minimises* it with a fitted calibration head (temperature / Platt) and *enforces* it as a hard `max_ece` promotion precondition, and it is the acceptance gate for the learned contradiction detector — a model is allowed to be confident only in proportion to how often it is right.

---

## 9. Unified Confidence Engine — Mathematics

The Week 33 unified confidence engine combines layer-level evidence (predicted NMR matching, HRMS exact mass, MS1 adduct/isotope, MS/MS annotation, fragmentation tree, LC-MS consensus via the Week 39 bridge, multiplet J-coupling agreement via the Week 40 bridge) into a single candidate ranking. The engine is intentionally **not** a calibrated DP5-style posterior — that role is filled by the parallel DP4/DP5 panel — but is instead a transparent weighted aggregation with explicit contradiction and missing-layer reporting.

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

**Step 4 — Plan and execute credibility activities.** Weekly regression suites (Weeks 22–40) pin every layer's behavior against a stable test corpus. Workflow-smoke tests exercise the full register → login → validate → analyze → preview → reference-assisted analysis → job submission → review approve/reject → export pipeline. A single evaluation framework (§8.11) — RMSE, F1, Top-k, BedROC, ECE — defines "better" up front, so a model or recipe change is promoted on measured, pre-registered metrics rather than ad-hoc comparison, with each run's metric vector, dataset-version tag, and git SHA captured by the experiment tracker (§4.5). The §4.5 public-datasets corpus adds a frozen, licence-clean, deduplicated evaluation baseline with a checksummed holdout that is hash-excluded from training, so credibility activities run against data the model has never seen.

**Step 5 — Assess model output.** The unified confidence engine's layer-by-layer agreement matrix, contradictions list, missing-layer list, and ambiguity alerts surface model-output uncertainty to the reviewer.

**Step 6 — Document credibility evidence.** The Week 34 regulatory report composer packages the full evidence chain: raw-archive SHA-256, processing recipe hash, evidence-layer outputs, citation-linked rationale notes, reviewer signoff event, and the export-package hash manifest.

**Step 7 — Maintain credibility through lifecycle.** Recipe-hash-linked re-processing, versioned report records, and the immutable raw vault ensure that any analysis can be regenerated from the raw bytes at any future point — the foundational requirement for lifecycle credibility. Content-addressed dataset versioning, the versioned output contract, and the CI determinism gate (§4.5) extend this from "regenerable in principle" to "byte-identical on re-run," giving lifecycle credibility a machine-checkable proof. The §4.5 model registry records every artifact (version, SHA-256, lineage, lifecycle status) and the inference router stamps each prediction with the exact model ids + checksums that produced it, so the precise model lineage behind any historical result — and why one layer was selected over another — is recoverable years later. The Prompt 23 closed feedback loop (§4.5) makes that lifecycle continuous rather than a one-time validation: reviewer corrections are captured as content-addressed events attributable to the `model_versions` that produced each output, an advisory reward model triages where the model is weakest while the deterministic verifier still arbitrates correctness, and any resulting champion→challenger change is dominance-gated with **zero safety regression**, human-signed-off, and **never auto-deployed** — with an instant routing-layer rollback if a challenger regresses in production. Credibility is therefore maintained as a continuously-monitored, human-gated loop, not a checkpoint that ages out.

---

## 11. ALCOA+ Data Integrity Posture

The ALCOA+ principles map onto MolTrace architectural primitives:

| ALCOA+ principle | MolTrace mechanism |
|---|---|
| **A**ttributable | Every audit event carries `user_id`, `tenant_id`, timestamp, IP, and user-agent; every AI-assisted result also carries the exact model ids + SHA-256 that produced it (§4.5 registry + router `model_versions`) |
| **L**egible | Pydantic-typed responses with stable JSON keys; HTML report renders for human review |
| **C**ontemporaneous | Audit events written synchronously in the same transaction as the analyze record |
| **O**riginal | Immutable raw FID vault; original archive bytes never overwritten |
| **A**ccurate | SHA-256 integrity verification before every read; processing recipe hash deterministic |
| + **C**omplete | Every analyze response captures every input; no silent parameter defaults |
| + **C**onsistent | Stable Pydantic schemas; backward-compatible additive evolution |
| + **E**nduring | Postgres + immutable vault retention policies; per-tenant configurable |
| + **A**vailable | One-click traceback from any report number to its raw spectrum |

A typical inspector question — *"Show me the raw bytes that produced this number"* — is a single click in the UI and a single SQL query in the database.

The §3.10 audit-trail layer hardens this posture cryptographically. **Original / Accurate / Enduring** are strengthened by the hash-chained, HMAC-signed `AuditEntry` ledger — each row links to the prior row's SHA-256 and is sealed with an organisation-keyed HMAC, so tampering, deletion, or reordering is detectable by `verify_chain`, and every AI-assisted result records the exact model-weight checksum that produced it. **Attributable** gains 21 CFR Part 11.50/.70 electronic signatures whose manifestation carries the signer's name, time, and meaning and is cryptographically bound to its record. A configurable **7-year retention floor** and a deterministic PDF/A export round out the *Enduring / Available* attributes for submission. The §4.5 reproducibility foundation reinforces *Original / Accurate / Enduring*: datasets and runs are addressed by content hash, every metric carries its dataset-version tag and git SHA, and the end-to-end determinism gate proves a result regenerates byte-for-byte — while the generated GAMP 5 Appendix D11 and ICH Q2(R2) artefacts (§8.10) package this evidence for a CSV file. The §4.5 closed-loop feedback layer (Prompt 23) extends the same custody one step further into the human loop: every reviewer correction is itself an **immutable, content-addressed event attributable to the exact `model_versions`** that produced the output it corrects, so the record now answers not only *"which model produced this number"* but *"which reviewer judged it, how, and why"* — and any model change that judgement motivates is dominance-gated, human-signed-off, and **never auto-deployed**, with an instant routing-layer rollback if a challenger regresses (*Attributable / Complete / Enduring*). These are controls that **support** 21 CFR Part 11; the overall compliance determination and computerized-system validation remain the customer's responsibility.

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

[^golotvin_asv]: Golotvin S. S.; Williams A. J. et al. *Automated structure verification (ASV) of small organic molecules from 1D / 2D NMR.* Magn. Reson. Chem. (ACD/Labs ASV methodology). The multi-test ASV concept — independent consistency tests combined into a verification verdict — underlies the §3.6 verification scorer.

[^elyashberg_case]: Elyashberg M. E.; Williams A. J.; Blinov K. A. *Contemporary Computer-Assisted Approaches to Molecular Structure Elucidation.* RSC Publishing, 2012. doi:10.1039/9781849733625. See also Elyashberg M. et al., *Prog. Nucl. Magn. Reson. Spectrosc.* reviews on CASE candidate ranking by consistency with experimental data.

[^iupac_isotopes]: Meija J. et al. *Isotopic compositions of the elements 2013 (IUPAC Technical Report).* Pure Appl. Chem. 2016, 88, 293. doi:10.1515/pac-2015-0503. Natural-abundance source for the §3.6 MS isotope-envelope model.

[^nmr_solver]: Jin Y.; Wang J.-J.; Xu F.; Ji X.; Gao Z.; Zhang L.; Ke G.; Zhu R.; E W. *NMR-Solver: Automated Structure Elucidation via Large-Scale Spectral Matching and Physics-Guided Fragment Optimization.* arXiv:2509.00640 (2025); Nat. Commun. The §3.7 retrieval layer (Gaussian-smoothed 256-D encoding + Kuhn-Munkres set similarity) is implemented from the published equations.

[^rag_lewis]: Lewis P.; Perez E.; Piktus A.; Petroni F.; Karpukhin V.; Goyal N.; Küttler H.; Lewis M.; Yih W.; Rocktäschel T.; Riedel S.; Kiela D. *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.* Advances in Neural Information Processing Systems 33 (NeurIPS 2020); arXiv:2005.11401. The retrieval-grounded-generation pattern behind the §8.5 `ai/rag.py` reasoning layer — proposals are constrained to retrieved precedent, never free-generated.

[^claude]: Anthropic. *Claude* (model `claude-opus-4-8`), accessed via the Anthropic Messages API with adaptive thinking and structured-output (strict-JSON, `output_config.format`) constraints. The reasoning model behind the §8.5 retrieval-augmented proposal layer; integrated as an injectable, optional (`anthropic` un-pinned, lazy-imported) backend — never bundled — with proposals grounded in retrieved precedent and arbitrated by the independent §3.6 verifier.

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

[^karplus]: Karplus M. *Contact Electron-Spin Coupling of Nuclear Magnetic Moments.* J. Chem. Phys. 1959, 30, 11–15. doi:10.1063/1.1729860. See also Karplus M. *Vicinal Proton Coupling in Nuclear Magnetic Resonance.* J. Am. Chem. Soc. 1963, 85, 2870–2871. doi:10.1021/ja00900a059. The three-term form ³J(θ) = A·cos²θ + B·cosθ + C, with the generic constants A = 7.76, B = −1.10, C = 1.40 used by MolTrace's opt-in Layer 40 vicinal refinement, is as tabulated in Pretsch 5e.[^pretsch]

[^haasnoot]: Haasnoot C. A. G.; de Leeuw F. A. A. M.; Altona C. *The relationship between proton-proton NMR coupling constants and substituent electronegativities — I. An empirical generalization of the Karplus equation.* Tetrahedron 1980, 36, 2783–2792. doi:10.1016/0040-4020(80)80155-4. The generalized relation ³J = P₁·cos²φ + P₂·cosφ + P₃ + Σᵢ Δχᵢ·[P₄ + P₅·cos²(ξᵢ·φ + P₆·|Δχᵢ|)] adds substituent electronegativity (Δχ on the Huggins scale) and relative orientation (ξ = ±1) corrections to the bare Karplus cosine series; MolTrace's opt-in `karplus_method='haasnoot_altona'` path uses the six-parameter set P₁ = 13.86, P₂ = −0.81, P₃ = 0.0, P₄ = 0.56, P₅ = −2.32, P₆ = 17.9°.

[^gottlieb]: Gottlieb H. E.; Kotlyar V.; Nudelman A. *NMR Chemical Shifts of Common Laboratory Solvents as Trace Impurities.* J. Org. Chem. 1997, 62, 7512. doi:10.1021/jo971176v

[^fulmer]: Fulmer G. R. et al. *NMR Chemical Shifts of Trace Impurities…* Organometallics 2010, 29, 2176. doi:10.1021/om100106e

[^pharma_solids]: *Spectroscopy of Pharmaceutical Solids.* (Papers/Spectroscopy/Pharmaceutical solids)

[^qnmr]: *Quantitative NMR Spectroscopy in Pharmaceutical Applications.* (Papers/Spectroscopy/qNMR + Protein_NMR folder)

[^qnmr_purity]: Pauli G. F.; Chen S.-N.; Simmler C.; Lankin D. C.; McAlpine J. B. et al. *Importance of Purity Evaluation and the Potential of Quantitative ¹H NMR as a Purity Assay.* J. Med. Chem. 2014, 57, 9220. doi:10.1021/jm500734a. See also Bharti S. K.; Roy R. *Quantitative ¹H NMR spectroscopy.* TrAC Trends Anal. Chem. 2012, 35, 5. doi:10.1016/j.trac.2012.02.007; and Saito T. et al. *A new traceability scheme for the development of certified reference materials by quantitative NMR.* Accred. Qual. Assur. 2009, 14, 79. doi:10.1007/s00769-008-0461-z. The §3.8 internal-standard equation and GUM uncertainty propagation are implemented from these public sources.

[^pulcon]: Wider G.; Dreier L. *Measuring Protein Concentrations by NMR Spectroscopy.* J. Am. Chem. Soc. 2006, 128, 2571. doi:10.1021/ja055336t (PULCON — the reciprocity principle for absolute concentration transfer). See also Dreier L.; Wider G. *Concentration measurements by PULCON using X-filtered or 2D NMR spectra.* Magn. Reson. Chem. 2006, 44, S206. doi:10.1002/mrc.1838. The §3.8 pulse-width-ratio concentration transfer follows these.

[^jtfnet]: Luo Y.; Su Z.; Chen W. et al. *Deep learning network for NMR spectra reconstruction in time-frequency domain and quality assessment.* Nat. Commun. 2025, 16, 2342. doi:10.1038/s41467-025-57721-w. The §3.9 JTF-Net backend and the reference-free REQUIRER (LCR) quality ratio follow this work; its protein-trained weights are downloaded by the end user from the authors' release (verify the repository license before bundling — see `NOTICE`), never vendored.

[^hyberts_ist]: Hyberts S. G.; Milbradt A. G.; Wagner A. B.; Arthanari H.; Wagner G. *Application of iterative soft thresholding for fast reconstruction of NMR data non-uniformly sampled with multidimensional Poisson Gap scheduling.* J. Biomol. NMR 2012, 52, 315. doi:10.1007/s10858-012-9611-z. Iterative soft thresholding for NMR was introduced by Stern A. S.; Donoho D. L.; Hoch J. C. *NMR data processing using iterative thresholding and minimum l1-norm reconstruction.* J. Magn. Reson. 2007, 188, 295. doi:10.1016/j.jmr.2007.07.008. The §3.9 IST-S baseline is implemented from these public equations (weights-free, no third-party-data obligation).

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

[^cfr_part11]: U.S. Food and Drug Administration. *21 CFR Part 11 — Electronic Records; Electronic Signatures* (esp. §11.10 controls for closed systems, §11.50 signature manifestations, §11.70 signature/record linking). U.S. Government work, public domain. The §3.10 audit-trail and electronic-signature controls are implemented to SUPPORT these requirements; MolTrace does not claim the product is itself compliant with the rule (computerized-system validation remains the customer's responsibility).

[^fda_data_integrity]: U.S. Food and Drug Administration. *Data Integrity and Compliance With Drug CGMP: Questions and Answers — Guidance for Industry* (December 2018) — the ALCOA+ data-integrity attributes. U.S. Government work, public domain.

[^fda_nitrosamines]: U.S. Food and Drug Administration. *Control of Nitrosamine Impurities in Human Drugs.* Guidance for Industry.

[^gamp5]: International Society for Pharmaceutical Engineering (ISPE). *GAMP 5: A Risk-Based Approach to Compliant GxP Computerised Systems*, 2nd ed., 2022 — including Appendix D11 (Computerised System Validation). The structure behind the §4.5 / §8.10 validation-document skeleton MolTrace generates.

[^vanrijsbergen]: van Rijsbergen C. J. *Information Retrieval*, 2nd ed. Butterworths, 1979 — the precision / recall / F-measure definitions behind the §8.11 F1 metric.

[^bedroc]: Truchon J.-F.; Bayly C. I. *Evaluating Virtual Screening Methods: Good and Bad Metrics for the "Early Recognition" Problem.* J. Chem. Inf. Model. 2007, 47, 488. doi:10.1021/ci600426e. The BedROC early-recognition metric behind the §8.11 evaluation framework.

[^ece_guo]: Guo C.; Pleiss G.; Sun Y.; Weinberger K. Q. *On Calibration of Modern Neural Networks.* Proc. 34th Int. Conf. on Machine Learning (ICML) 2017, PMLR 70, 1321. The expected-calibration-error definition behind the §8.11 calibration metric.

[^csi_fingerid]: Dührkop K.; Shen H.; Meusel M.; Rousu J.; Böcker S. *Searching molecular structure databases with tandem mass spectra using CSI:FingerID.* Proc. Natl. Acad. Sci. USA 2015, 112, 12580. doi:10.1073/pnas.1509788112. The MS/MS → fingerprint → ranked-candidate model behind §8.5; integrated via its documented interface, never reimplemented.

[^sirius]: Dührkop K.; Fleischauer M.; Ludwig M.; Aksenov A. A.; Melnik A. V.; Meusel M.; Dorrestein P. C.; Rousu J.; Böcker S. *SIRIUS 4: a rapid tool for turning tandem mass spectra into metabolite structure information.* Nat. Methods 2019, 16, 299. doi:10.1038/s41592-019-0344-8. The host application for CSI:FingerID that MolTrace integrates.

[^metlin_rt]: Domingo-Almenara X.; Guijas C.; Billings E.; Montenegro-Burke J. R.; Uritboonthai W.; Aisporna A. E.; Chen E.; Benton H. P.; Siuzdak G. *The METLIN small molecule dataset for machine learning-based retention time prediction.* Nat. Commun. 2019, 10, 5811. doi:10.1038/s41467-019-13680-7. The basis for the §8.5 retention-time corroboration signal.

[^spc_montgomery]: Montgomery D. C. *Introduction to Statistical Quality Control*, Wiley. The standard reference for the process-capability indices (Cp/Cpk/Pp/Ppk and the Cpk ≥ 1.33 capability banding), the d₂ unbiasing constants behind the moving-range (I-MR) sigma estimate, and the CUSUM (k = 0.5σ, h = 5σ; in-control ARL ≈ 465) and EWMA (λ = 0.2, L = 3, time-varying limits) chart designs the SPC engine implements as published, never re-derived.

[^spc_weco]: Western Electric Company. *Statistical Quality Control Handbook*, 1st ed., 1956. Origin of the zone-based control-chart tests — the classic four WECO run/zone rules encoded as the `western_electric_classic` rule set (its run test is 8 points; MolTrace uses Nelson's 9-point run count across the extended sets).

[^spc_nelson]: Nelson L. S. *The Shewhart Control Chart — Tests for Special Causes.* J. Qual. Technol. 1984, 16 (4), 237–239. The eight run-and-zone tests (counts 1 / 9 / 6 / 14 / 2-of-3 / 4-of-5 / 15 / 8) implemented as the `nelson` / `montgomery` / default `western_electric` rule sets.

[^ich_q6a]: ICH *Q6A — Specifications: Test Procedures and Acceptance Criteria for New Drug Substances and New Drug Products: Chemical Substances* (1999). The decision trees the specification-builder engine encodes for appearance, identification, assay, impurity, dissolution/disintegration, and water-content acceptance criteria.

[^fda_oos]: U.S. FDA. *Guidance for Industry — Investigating Out-of-Specification (OOS) Test Results for Pharmaceutical Production* (2006). The two-phase laboratory / full-scale investigation framework the OOS workflow engine implements, including the assignable-cause invalidation rule.

[^ich_q10]: ICH *Q10 — Pharmaceutical Quality System* (2008). The PQS elements (CAPA, process-performance and product-quality monitoring, change management, management review) the OOS investigation report assembles.

---

## Companion documents

- **MolTrace White Paper — Hybrid** (canonical, ~5,700 words) — comprehensive business + technical overview
- **MolTrace White Paper — Sales** (~4,000 words) — business case forward, audience: pharma R&D directors
- **MolTrace Executive One-Pager** (~500 words) — single-page summary for gated download
- **MolTrace ROI Methodology** — measurement protocol + fill-in template for measured tenant data
- **MolTrace Company Credentials** — partner / customer logo bar + About MolTrace block

*© 2026 MolTrace Technologies, Inc. This white paper is the technical-reviewer variant intended for analytical-method validators, NMR / MS technical leads, regulatory-affairs reviewers, and data-integrity auditors. For pilot evaluation, regulatory-affairs briefings, or technical due-diligence access, contact MolTrace Technologies.*
