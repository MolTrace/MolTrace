# AI/ML layer — upgrade program

**Date:** 2026-08-08 · **Scope:** the whole AI/ML layer across both science packages
(`moltrace.spectroscopy.ai|feedback|eval|data|ops`, `moltrace.regulatory.ai|intelligence|eval|ops`)
and the product surface that is supposed to expose it (`nmrcheck/ai_inference_store.py`,
`ml_model_factory_store.py`, and 76 HTTP routes).

Written under `module_build_runbook.md` Part C. P0 (evidence pass) was run before any judgement:
every claim below was `git grep`-ed or counted on this checkout, and the central finding was
*measured*, not argued. Inputs: the business-folder **AI Operations Roadmap v1.0** (11 phases,
5-layer architecture, 16 canonical datasets), the **Testing AI/ML Playbook**, and
`structure_elucidation_program.md` (2026-08-07), whose B0–B7 sequencing this document extends
rather than replaces.

**Headline.** MolTrace has two AI/ML layers and they do not touch each other. One is a
15,721-line science library that is genuinely good — versioned registry, provenance-complete
inference router, dominance-gated eval harness, leak-proof dataset pipeline, RLHF reward model
constrained to reorder only within a verifier verdict class. The other is 76 REST routes of
AI-governance CRUD — model cards, training runs, calibration assessments, drift alerts, canary
deployments — in which **every number is supplied by the caller**, because neither store imports
`moltrace` at all. The result is a platform that can record that a model was calibrated but
cannot calibrate one, and a science layer that can calibrate one but has no way to be called.

So the first upgrade is not a model. **It is the seam.** Layer 0 below is the whole difference
between "we have an AI/ML layer" and "the AI/ML layer is in the product."

---

## Part A — measured state

### A1. What is built, and what it is worth

| Package | LOC | Verdict |
|---|---|---|
| `spectroscopy/ai/registry.py` | 720 | **Strong.** Append-only, semver + SHA-256, training-data lineage, status transitions, pluggable store (in-memory / SQLAlchemy). |
| `spectroscopy/ai/router.py` | 344 | **Strong.** 3-layer routing (LoRA → NMRNet → HOSE) with a complete, deterministic `model_versions` provenance dict, and an explicit `unregistered:*` marker rather than a silent drop. |
| `spectroscopy/ai/finetune.py` | 2,197 | LoRA config, k-fold with leak-proof grouping, Optuna-style HPO, Platt + temperature calibration heads, contradiction detector. |
| `spectroscopy/ai/rag.py` | 1,032 | Retrieval over the similarity index → Claude with structured outputs, **cite-or-drop** hallucination guard, verifier arbitration, full audit capture. |
| `spectroscopy/ai/ms_models.py` | 511 | CSI:FingerID / METLIN-RT / DP4 fusion; licence-respecting wrappers that return `available=False` rather than a fabricated candidate. |
| `spectroscopy/ai/active_learning.py` | 1,007 | Override capture, query-by-committee disagreement scoring, budgeted dedup queue, retraining trigger, loop-yield metrics. |
| `spectroscopy/eval/harness.py` | 577 | **The best asset in the layer.** Checksum-locked gold set, 10-metric vector, direction-aware **dominance** promotion rule, `SAFETY_CRITICAL = {false_confirmation_rate, ece}` with zero-regression tolerance, `gate_for_ci`. |
| `spectroscopy/eval/shift_accuracy.py` | 359 | Molecule-level (SHA-256) held-out split; produced MolTrace's first real error bar on 2026-08-07. |
| `spectroscopy/data/datasets_pipeline.py` | 938 | Licence-aware source registry, leak-proof splits, QM9 kept out of val/test. |
| `spectroscopy/feedback/*` | 1,227 | Feedback capture with a reason taxonomy, reward model, A/B champion-challenger gated on `dominates`. |
| `spectroscopy/ops/*` | 970 | Drift/lineage monitoring + `deployment_gate.self_check` (wired into CI). |
| `regulatory/ai/*` + `intelligence/*` | 2,377 | Registry, router, LoRA, active learning, grounded RAG search — **all of it dark** (see A2). |

This is not a prototype layer. Measured against the roadmap's five layers, Layers 1–4 are
substantially *implemented*; the roadmap's advice to defer Layer 5 (custom models) has been
correctly followed.

### A2. The disconnection — counted, not asserted

`nmrcheck` (the HTTP layer) imports from `moltrace` in **18 places total**. Of the entire AI/ML
layer, exactly four:

```
api.py:9498   from moltrace.spectroscopy.ai.rag import ...          # POST /spectrum/reason
api.py:27639  from moltrace.spectroscopy.ops import monitoring       # GET /admin/ops/model-lineage
api.py:27640  from moltrace.spectroscopy.ops.deployment_gate import self_check
api.py:27707  from moltrace.spectroscopy.ops.monitoring import lineage_dashboard
```

Not imported by the product at all: `InferenceRouter`, `ModelRegistry`, `finetune`, `ms_models`,
`active_learning`, all of `feedback/`, all of `eval/`, all of `data/`, and **every module under
`moltrace.regulatory.ai` and `moltrace.regulatory.intelligence`** (0 imports, 0 routes).

Meanwhile the product surface carries **76 AI/ML routes**:

| Prefix | Routes | What it actually does |
|---|---|---|
| `/ml/*` | 35 | CRUD via `ml_model_factory_store` — tasks, feature pipelines, training runs, evaluation runs, model artifacts, model cards, calibration assessments, error analysis, OOD assessments, deployment candidates, model health. |
| `/ai/*` | 31 | CRUD via `ai_inference_store` — services, predictions, routing decisions, explanations, active-learning candidates, shadow evaluations, canary deployments, monitoring events, prediction audit. |
| `/model-versions`, `/model-health` | 8 | Version + drift-alert records. |
| `/admin/ops/*` | 2 | The only two that call the science layer. |

`grep -c moltrace ai_inference_store.py ml_model_factory_store.py` → **0 and 0.**

Read `create_prediction` and the mechanism is explicit: it resolves a *service row*, picks an
*artifact row*, then calls `_extract_confidence(payload, …)` — the confidence comes **from the
request body**. `POST /ai/predictions` records that a prediction happened. It does not make one.
Same for `/ml/calibration-assessments` (a submitted ECE), `/ml/training-runs` (a submitted run),
`/ai/routing/decide` (a row-level route, not `InferenceRouter`).

**This is not a bug and the governance layer is not wasted.** It is a correct, audit-grade
system-of-record — attributable, reviewable, `human_review_required=True` throughout — that was
built before the engine it was meant to record. What is missing is the wire between them.

### A3. Corrections to the AI Operations Roadmap, from this checkout

The roadmap is sound strategy and its ordering critique is right. Five premises have since moved:

1. **"Do not train any custom models in the first 90 days"** — followed, and it worked. The
   largest accuracy gain to date (**18.6× on ¹³C uncertainty**, 35.0 → 1.88 ppm median σ) came
   from building the HOSE knowledge base from NMRShiftDB2 assignments. No model, no GPU, no new
   dependency. Layer 5 remains correctly deferred.
2. **"Layers 1 and 2 give 70–80% of capability on day one"** — not on this checkout. Layer 1's
   NMRNet forward pass is still two `NotImplementedError`s in `nmrnet_service/app.py:59,76`.
   Production runs on the HOSE fallback. That is now *good* (¹³C MAE 3.44 ppm held-out) but it
   is not Layer 1.
3. **The 10 evaluation metrics** in the roadmap are the wrong set for this architecture. The
   harness's actual vector — with `false_confirmation_rate` and `ece` as zero-regression
   safety-critical metrics and a **dominance** rule rather than a single headline — is stricter
   and should be treated as canonical. The roadmap's targets (Top-1 ≥85%, ECE ≤3%) are
   reasonable *destinations* but must not be quoted until measured on the gold set.
4. **SOC 2 Type II** appears in Phases 10 and the 90-day plan. SOC 2 is **not held**, and all
   compliance language in this repo is "designed to support." Any AI/ML upgrade artifact must
   inherit that framing.
5. **Tooling.** The roadmap's stack (DVC, MLflow, Pinecone, Triton, Argo, Label Studio, Evidently)
   is largely *already implemented in-repo* rather than adopted: the registry is the model
   registry, `datasets_pipeline` is the DVC role, `ops/monitoring` is the Evidently role,
   `feedback/capture` + the annotation queue is the Label Studio role. Adding those SaaS
   dependencies now would fragment the audit trail across systems the HMAC-chained
   `spectroscopy/audit/` cannot cover. **Recommendation: keep the in-repo implementations, and
   spend the tooling budget on GPU for Layer 1 instead.**

### A4. Model IDs are stale

| Site | Pinned | Status |
|---|---|---|
| `spectroscopy/ai/rag.py:89` | `claude-opus-4-8` | superseded |
| `regulatory/ai/rag_reasoner.py:63` | `claude-sonnet-4-6` | superseded |

Both should move to the Claude 5 family (`claude-opus-5` for adversarial/structure reasoning,
`claude-sonnet-5` for high-volume grounded retrieval), pinned in **one** place with the model id
recorded in the audit entry so a past answer stays attributable to the model that produced it.

---

## Part B — the upgraded architecture

The roadmap's five layers stay. This adds **Layer 0** (the seam) below them and splits the
roadmap's Layer 4 into evaluation, feedback and governance, because in a regulated product those
are three different owners.

| # | Layer | Roadmap map | Where it lives | State |
|---|---|---|---|---|
| **L0** | **The seam** — science library ↔ product surface | (absent from roadmap) | `nmrcheck/ai_inference_store.py`, `ml_model_factory_store.py` | **Missing entirely.** |
| **L1** | Prediction core — shift prediction, MS→structure, RT | Layer 1 | `predict/`, `ai/ms_models.py`, `nmrnet_service/` | Fallback live; NMRNet stub. |
| **L2** | Representation & retrieval — embeddings, index, RAG plumbing | Layer 2 (half) | `similarity/`, `ai/rag.py`, `regulatory/intelligence/` | Spectral RAG live at 1 route; regulatory RAG dark. |
| **L3** | Reasoning — LLM proposal under the verifier | Layer 2 (half) | `ai/rag.py`, `regulatory/ai/rag_reasoner.py` | Live but on superseded models. |
| **L4** | Post-training — LoRA/DoRA, preference optimisation, RLVR | Layer 3 | `ai/finetune.py`, `feedback/reward_model.py` | Built, never run on real data. |
| **L5** | Evaluation & calibration — gold sets, conformal, decoys | Layer 3 gate | `eval/harness.py`, `eval/shift_accuracy.py` | Strongest asset; needs conformal + decoys. |
| **L6** | Feedback & active learning | Layer 4 | `feedback/`, `ai/active_learning.py` | Built, not wired to any user action. |
| **L7** | Governance & MLOps | Layer 4 gate | `ops/`, `regulatory/ops/`, the 76 routes | Product half live, science half dark. |
| — | Custom architectures | Layer 5 | — | **Correctly deferred.** Do not open. |

### Two invariants that constrain every layer

1. **The deterministic verifier is the sole arbiter.** No layer below may declare correctness.
   L3 proposes, L1 predicts, L5 measures — `verification.verify_structure` decides. The reward
   model may reorder only *within* a verdict class. This is already enforced and must survive
   every change here.
2. **Nothing produces a number without provenance.** `RoutedPrediction.model_versions` is the
   template: artifact id → SHA-256 for everything that touched the result, with
   `unregistered:*` markers rather than silent gaps.

### Sequencing

This program interleaves with `structure_elucidation_program.md` Part D rather than competing
with it. Combined order:

| Order | Package | Source | Why here |
|---|---|---|---|
| 1 | **L0** — the seam | this doc | Every other layer is invisible to the product until this exists. Lowest cost, highest leverage. |
| 2 | **B0** — NMRNet forward pass + client | SEP | L1's remaining half. Already specified. |
| 3 | **B1/B3** — over-picking, assignment | SEP | Gate every measured number. |
| 4 | **L5** — conformal calibration + decoys | this doc | Closes the measured `ece` defect (¹³C σ optimistic ~3× in the tight bin) and the missing `false_confirmation_rate`. |
| 5 | **L2** — retrieval upgrade + regulatory RAG wiring | this doc | 2,377 dark LOC; largest ratio of shipped-to-exposed. |
| 6 | **L3** — model refresh + tool-grounded reasoning | this doc | Cheap, but pointless before L5 can score it. |
| 7 | **L6** — close the feedback loop | this doc | Needs L0 (capture point) and L5 (promotion gate). |
| 8 | **L4** — first real post-training run | this doc | Needs ≥1,000 L6-produced labels. Not before. |
| 9 | **L7** — AIBOM, EU AI Act / GAMP 5 D11 artifacts | this doc | Records what the layers above actually did. |

---

## Part C — Layer 0: the seam — **built 2026-08-08**

> **Status.** C1 (the adapter), C3 (prediction + promotion-gate wiring) and C5 (the guard test)
> ship. `nmrcheck/ai_engine_adapter.py` is the single import boundary; `grep -c moltrace` on both
> stores is still 0, asserted by a test. `nmr_shift_prediction` routes through `InferenceRouter`
> and `nmr_candidate_ranking` through the in-house DP4; both refuse a caller-supplied
> `confidence_score` / `uncertainty_json` / `ood_status` / `model_versions`. The `0.82` default is
> gone. Deployment-candidate approval applies `eval.harness.dominates` with three outcomes
> (passed / refused / not applicable), and both sides of the metric-asymmetry hole are closed.
> Confidence derives from the verifier's own σ→significance mapping
> (`spectroscopy/ai/confidence.py`), so the 35 ppm median ¹³C σ that reached production scores
> 0.143 and reports `out_of_domain` instead of leaving an abstention indistinguishable from a
> prediction.
>
> **C2 shipped 2026-08-08, with one deliberate deviation from the specification below.** The spec
> said "point `SqlAlchemyRegistryStore` at the existing `model_artifacts` table … rather than a
> parallel table." That was wrong, and the reason is worth recording: the registry's entries are
> **immutable** with lifecycle changes *appended* to a separate status log, while
> `model_artifacts.status` is a mutable column. Merging them would either destroy the append-only
> guarantee — the property that makes a promotion reconstructable and a retirement un-editable —
> or force a rewrite of a table 35 routes read. So C2 shipped as a **link, not a merge**:
> migration `0044` adds `model_artifacts.registry_model_id` (nullable, unique, not backfilled),
> and each side keeps its own semantics.
>
> What that closed is the hole the spec was groping at: `InferenceRouter` resolves what to serve
> from the registry, and **nothing in the product ever wrote it** — so approving a deployment
> candidate flipped a row and changed nothing about which artifact answered a prediction.
> Approval is now the single writer of `ModelStatus.PRODUCTION`, `GET /ml/model-artifacts` reports
> the registry's *live* status (so a superseded artifact reads `retired`, not `approved`), and
> promotion is refused — approval standing, router unchanged — when the artifact carries no
> content hash or when a semantic version is reused against different bytes.
>
> Ordering is deliberate: the approval commits *before* the promotion is attempted. A failed
> promotion then leaves the router serving the incumbent, which is the safe direction; the reverse
> order could leave the registry serving a model whose approval never recorded.
>
> **C4 stays deferred, precondition named.** There is no regulatory guidance index on disk. The
> spectral RAG has a real one (`spectrum_similarity_index/spectra.faiss`); `regulatory/data/` holds
> only `corpus_pipeline.py`, and nothing in `api.py` references `regulatory_search`. Shipping the
> two routes now would give a search over nothing, which reads as a capability rather than a gap.
> **Unblocks when:** the licence-partitioned corpus is built and indexed — FDA text redistributable,
> ICH/EMA/WHO internal-only with cited excerpts — which is its own change.

**Goal.** Every one of the 76 governance routes becomes a *record of something the science layer
did*, rather than a record of something a caller claimed. No new endpoints. No contract breakage.

### C1. The adapter

New module: `src/nmrcheck/ai_engine_adapter.py` — the single, and only, import boundary between
`nmrcheck` and `moltrace.spectroscopy.ai|eval|feedback`. Stores keep zero `moltrace` imports;
they take results, not engines.

```
ai_engine_adapter.py
  ├── resolve_router(session)      -> InferenceRouter over SqlAlchemyRegistryStore
  ├── run_shift_prediction(...)    -> RoutedPrediction
  ├── run_ms_candidates(...)       -> RankedCandidate[]
  ├── score_gold_set(bundle)       -> GoldMetricVector
  └── to_prediction_record(rp)     -> PredictionRequest  (the wire shape, unchanged)
```

Rules, in order of importance:

* **Fail loud, degrade recorded.** If the engine is unavailable the adapter raises; the route
  returns the existing `AIInferenceError` path. It never substitutes a caller-supplied number for
  a computed one — that is the exact failure mode this layer exists to end.
* **Lazy import.** `moltrace.spectroscopy.ai` pulls RDKit and (optionally) torch. Import inside
  the function, as `api.py:9498` already does, so the ~800-route app still builds in
  `routed_app` without the ML extras.
* **Provenance is mandatory.** `RoutedPrediction.model_versions` maps 1:1 onto the prediction
  record's provenance field. A prediction with an empty `model_versions` is rejected by the
  adapter, not stored with a gap.

### C2. Registry unification — one registry, two views

Today there are two: `moltrace.spectroscopy.ai.registry.ModelRegistry` (semver, SHA-256, lineage,
status transitions, append-only) and the ORM `model_artifacts` / `model_versions` tables behind
`/ml/*`. They describe the same objects and can disagree.

**Decision: `ModelRegistry` is authoritative; the ORM tables become its projection.** It already
has the properties the regulated path needs (append-only, artifact hash, lineage) and it is the
one the router actually reads at inference time. Concretely:

1. `SqlAlchemyRegistryStore` gets pointed at the existing `model_artifacts` table (adding
   `artifact_sha256`, `lineage_json`, `parent_base_id`, `confidence_band_ppm` where absent) rather
   than a parallel table. One migration, Postgres delta **plus** its `_ensure_sqlite_schema`
   counterpart.
2. `GET /ml/model-artifacts` reads through the registry, so what the UI shows is what the router
   would resolve.
3. `POST /ml/deployment-candidates/{id}/approve` becomes the **only** writer of a
   `ModelStatus.PRODUCTION` transition. Registry status changes stop being a library call and
   become a reviewed, signed product action — which is what GAMP 5 D11 human sign-off means.

**Invariant test first:** a model the registry resolves as `production` for a nucleus is the same
artifact id `/ml/model-artifacts` reports as deployed, for every nucleus, with no third state.

### C3. Route-by-route wiring

| Route | Today | After L0 |
|---|---|---|
| `POST /ai/predictions` | records caller-supplied confidence | calls `run_shift_prediction`; `confidence` and `uncertainty` computed; `model_versions` attached |
| `POST /ai/routing/decide` | picks an artifact row | delegates to `InferenceRouter` resolution; records the per-atom `Layer` distribution and the routing `reason` string verbatim |
| `POST /ml/evaluation-runs` | records submitted metrics | runs `eval.harness.evaluate` against the checksum-locked gold set; stores the full `GoldMetricVector` |
| `POST /ml/calibration-assessments` | records submitted ECE | computes ECE + reliability bins from the eval run; refuses if the gold-set checksum does not match the recorded one |
| `POST /ml/deployment-candidates/{id}/approve` | flips a row | runs `eval.harness.dominates` first; **refuses** on any `SAFETY_CRITICAL` regression, naming the metric and the delta |
| `POST /ai/canary-deployments` | records a canary | reads `feedback/ab_testing` champion-challenger state |
| `POST /ai/active-learning/candidates` | records a candidate | populated from `active_learning.build_annotation_queue` |
| `GET /ai/model-monitoring` | reads events | reads `ops/monitoring` drift + lineage |
| `POST /ai/predictions/{id}/feedback` | records feedback | emits `feedback.capture.FeedbackEvent` into the active-learning queue (this is the L6 entry point) |

The wire shapes do not change, so `schema.d.ts` regeneration is additive and the FE keeps working
throughout. **Contracts first:** routes/models land and `pnpm generate:openapi` runs before any
frontend work.

### C4. Regulatory AI — from dark to two routes

`moltrace.regulatory.ai` + `intelligence` is 2,377 lines behind zero routes. It does **not** get
2,377 lines' worth of surface. It gets the two that the existing FE can consume:

* `POST /regulatory/intelligence/search` — grounded corpus retrieval via
  `intelligence.rag_search`, returning citations with `rule_set_version`, and an explicit
  `matched=false` for unknown inputs.
* `POST /regulatory/intelligence/explain` — `ai.rag_reasoner` over retrieved guidance, with
  `human_review_required=True` and cite-or-drop.

Both inherit the baseline access gate and each must apply its own owner/team scope check with a
**non-leaking 404**. Neither may emit a regulated number — those come from the version-pinned
rule engine, and the reasoner is restricted to *explaining* a number the engine already produced.

### C5. What L0 does not do

No new models. No new datasets. No accuracy claim. It is plumbing, and its success criterion is
falsifiable: after L0, `grep -c moltrace ai_inference_store.py` is still 0 (stores stay clean),
`ai_engine_adapter.py` is the only new import boundary, and **no AI/ML route accepts a
model-derived number from the request body.** That last one is the test to write first.

---

## Part D — Layer 1: the prediction core

L1 = `structure_elucidation_program.md` **B0**, plus three additions that document does not cover.
B0 items 1–4 stand as written and are not restated. The additions:

### D1. Conformal prediction over the shift predictor — **fitted and measured 2026-08-08**

> **The guarantee holds on real data, and the defect is larger than B5 could see.**
> `spectroscopy/eval/conformal.py` fits Mondrian split-conformal bands (nucleus × reported-σ
> decile). Reproduce with `scripts/measure_conformal_calibration.py`. Three molecule-level
> splits cut from one hash in a single pass — 39,628 train / 5,040 calibration / 4,950
> evaluation from 49,618 NMRShiftDB2 molecules, 393,760 reference atoms in the table.
>
> | target | nucleus | n | empirical coverage | mean half-width | median |
> |---|---|---|---|---|---|
> | 90 % | ¹³C | 36,844 | **90.03 %** | 6.95 ppm | 4.72 ppm |
> | 90 % | ¹H | 12,508 | **90.61 %** | 0.714 ppm | 0.397 ppm |
> | 95 % | ¹³C | 36,844 | 94.72 % | 9.18 ppm | 6.23 ppm |
> | 95 % | ¹H | 12,508 | 94.93 % | 0.951 ppm | 0.520 ppm |
>
> At 90 % the worst deficit is **0.0000** — both nuclei meet target. At 95 % there is a
> **0.28 pp shortfall on ¹³C** (94.72 % against 95 %), reported rather than rounded away; it is
> within sampling noise at n = 36,844 but it is a shortfall, and the report names it. Every atom
> found a calibrated band (pooled fallback 0.0 %).
>
> **The finding — σ is not merely mis-scaled, it is *differentially* mis-scaled.** The ratio of
> conformal half-width to mean reported σ, across the ten ¹³C bands:
>
> | mean σ (ppm) | 0.17 | 0.46 | 0.82 | 1.31 | 2.01 | 2.83 | 3.67 | 4.64 | 6.38 | 12.66 |
> |---|---|---|---|---|---|---|---|---|---|---|
> | half-width / σ | **8.66×** | 4.09× | 3.08× | 2.62× | 2.36× | 2.09× | 1.92× | 1.79× | 1.83× | **1.77×** |
>
> **Under a correctly-scaled σ that ratio is a constant** — it is the error distribution's 90th
> percentile expressed in units of σ, whatever that distribution happens to be. It is not
> constant: it varies **4.90×** on ¹³C and **3.81×** on ¹H, monotonically, and the extreme is at
> the tight end. This is a stronger statement than B5's "optimistic ~3×", and materially worse
> news: a constant mis-scaling could be repaired by multiplying σ by one number. This cannot.
>
> **It is worst exactly where the arbiter leans hardest.** `_significance_from_sigma` scores a
> tight σ highest, so the atoms the verifier weights most are the atoms whose confidence is most
> overstated — the failure is aligned with the decision, not orthogonal to it.
>
> **Extends, rather than contradicts, B5's ¹H finding.** B5 reported ¹H well calibrated
> throughout, and at its bin resolution (σ ≈ 0.18 / 0.70 / 1.40) that still holds — those bands
> sit at ratios 2.10× / 1.85× / 1.90×. The problem lives below them: ¹H's two tightest bands
> (mean σ 0.021 and 0.056 ppm) need **7.22×** and **4.33×** their claimed σ. B5's coarse bins
> averaged over the region where the defect is.
>
> **The verifier now scores on the interval — landed, with the re-baseline recorded.**
> `_significance_from_half_width` replaces `_significance_from_sigma` at the single call site in
> `PredictionBoundsTest`, anchored on `calibration.reference_half_width(nucleus, σ_ref)` so
> refitting the bands moves the anchor with them. Same shape, same anchor: a width equal to the
> reference still scores 4 ("medium"). Invariant tests were written first (range, monotonicity,
> anchor, abstention on an unusable width or a missing anchor); the numbers that legitimately
> moved are pinned in `test_significance_rebaseline_*`:
>
> | ¹³C mean σ | significance from σ | from the interval |
> |---|---|---|
> | 0.169 | 7.377 | **6.111** |
> | 2.005 | 3.995 | 4.000 |
> | 12.656 | 1.092 | **1.395** |
>
> The mapping **compresses**: most-to-least significant falls from **6.757× to 4.382×**. Tight
> atoms lose weight they had not earned; wide atoms get some back. That is the correction, not a
> side effect — σ's spread was the artefact.
>
> `VerificationOptions.shift_calibration` supplies it. Absent, every match falls back to the σ
> basis and the test's `details.significance_basis` counts how many atoms used each, alongside the
> calibration fingerprint and target coverage — so a run scored on the weaker basis is visible in
> the audit record instead of indistinguishable from a calibrated one. A calibration that cannot
> anchor a nucleus falls back rather than scoring everything as certain.
>
> ### ~~Adjacent defect: the match tolerance~~ — **WITHDRAWN 2026-08-08, and the withdrawal
> itself was wrong the first time**
>
> This section previously claimed `PredictionBoundsTest`'s `tol = max(base, 3σ)` is "too
> permissive everywhere and worst for confident atoms — 2.74× at σ = 0.169". **That claim is
> withdrawn.** It compared a rule operating at ~96 % retention against a *90 %* conformal window,
> which is not a comparison. `scripts/measure_match_tolerance.py` measures the two quantities that
> actually move in opposite directions, on 4,947 held-out molecules / 49,352 matched atoms:
>
> * **retention** — share of atoms whose *true* line falls inside the window;
> * **exposure** — mean count of *other* atoms' lines also inside it.
>
> | rule | ¹³C retention | ¹³C exposure | ¹H retention | ¹H exposure |
> |---|---|---|---|---|
> | current `max(base, 3σ)` | 96.301 % | 2.515 | 96.067 % | 3.363 |
> | conformal 90 % | 90.026 % | 1.755 | 90.614 % | 2.542 |
> | conformal 95 % | 94.721 % | 2.221 | 94.931 % | 3.196 |
> | conformal 99 % | 99.012 % | 3.531 | 99.137 % | 4.912 |
>
> **Correction to the first withdrawal, recorded because the mechanism is the reusable part.** The
> first version of this retraction interpolated conformal exposure to the current rule's 96.301 %
> retention by drawing a chord between the **non-adjacent** 95 % and 99 % rows, got ~2.70, and
> concluded conformal was worse. That is invalid: exposure-vs-retention is strongly **convex**
> (¹³C slope 0.0992 from 90→95, 0.3052 from 95→99), and a convex function lies **below** its
> chord, so the estimate was biased upward by **8.8 %**. Refitting the calibration directly at
> targets 0.963/0.965 gives ¹³C exposure **2.484** at matched retention — **1.24 % better** than
> the current rule, not worse. On ¹H the current rule wins by 1.85 %. **It is a wash that reverses
> by nucleus.** A retraction of a conclusion drawn from an invalid comparison must not itself rest
> on one.
>
> **The conclusion survives on better evidence.** Two independent tests, neither relying on
> interpolation:
>
> 1. **Weighted by the code's own objective.** `PredictionBoundsTest` weights each match by
>    `tanh(significance/3)`, and significance is monotone-decreasing in the half-width, so a false
>    match on a *tight* atom is worth ~4.4× more evidence than one on a wide atom. Measured on that
>    objective the current rule is still ahead (¹³C weighted exposure 2.2872 vs 2.2971): it
>    concentrates its exposure on low-weight, wide-σ atoms.
> 2. **Family frontier.** Across **108** `(base, k)` settings for ¹³C and **99** for ¹H, **zero**
>    weakly dominate `(4.0, 3.0)` / `(0.30, 3.0)`.
>
> **The original claim was also inverted, not merely overstated.** Per-band realized retention
> shows the flat floor **under**-covers confident atoms: ¹³C floor-bound bands realize
> 96.80 / 95.96 / 94.41 / 93.74 % against a 96.30 % aggregate, while the widest bands reach
> 97.74–98.43 % (¹H the same shape: 94.1 % tight, 98.5 % wide). "Worst for confident atoms" points
> the wrong way — the confident atoms are the ones getting *less* than nominal coverage.
>
> ### The defect that does survive — `AssignmentsTest`, which nothing above had looked at
>
> `_SHIFT_TOL_PPM` has a **second consumer**. `AssignmentsTest` (`scorer.py:641`) builds its
> candidate set with `d <= 3.0 * base_tol` — a flat **12.0 ppm** (¹³C) / **0.90 ppm** (¹H) radius
> with **no σ adaptation at all**. Measured on the same split, that window is **strictly dominated
> on both axes**:
>
> | window | ¹³C retention | ¹³C exposure | ¹H retention | ¹H exposure |
> |---|---|---|---|---|
> | `AssignmentsTest` flat 3×base | 95.06 % | 3.133 | 91.05 % | 3.672 |
> | `PredictionBoundsTest` `max(base, 3σ)` | **96.30 %** | **2.515** | **96.07 %** | **3.363** |
>
> Strictly dominated means there is no trade-off to argue about: the σ-adaptive rule already in the
> file achieves *higher* retention at *lower* exposure, on both nuclei. This is the mechanism-backed
> version of "too permissive", and it is in a different test from the one the original claim named.
>
> **Fixed 2026-08-08 — and the second σ-blind use was the worse one.** `AssignmentsTest` used the
> flat constant *twice*: as the candidate radius, and as the width of the merit Gaussian
> `exp(-0.5·(d/base_tol)²)`. The merit scale is the more consequential. On a fixed 4.0 ppm ruler an
> atom predicted to ±1.5 ppm scores **0.88** for a 2 ppm miss that is well *outside* its interval,
> while an atom predicted to ±22 ppm scores **0.32** for a 6 ppm hit well *inside* its own — the
> same inversion the significance mapping had, one test over.
>
> Both now scale by the resonance's own conformal interval, with the flat constant as the fallback
> when no calibration is supplied. Re-baselined on the same held-out split
> (`scripts/measure_assignments_window.py`, 32,708 ¹³C / 10,662 ¹H resonances):
>
> | candidate radius | ¹³C retention | ¹³C candidates | ¹H retention | ¹H candidates |
> |---|---|---|---|---|
> | flat `3×base` (before) | 95.06 % | 3.274 | 90.96 % | 3.501 |
> | **`3×` conformal (now)** | **99.07 %** | 4.089 | **99.25 %** | 4.898 |
> | `max(flat, conformal)` | 99.59 % | 4.481 | 99.48 % | 5.111 |
>
> The flat radius was losing the true pairing for **5.0 % of ¹³C and 9.0 % of ¹H resonances**, and
> each loss is penalised *twice* — merit 0.0, **and** the resonance's integral counted as
> unexplained impurity, which lowers this test's own significance. A correct structure was being
> marked down for the predictor's uncertainty.
>
> `max(flat, conformal)` was rejected despite scoring marginally higher: its extra 0.5 pp costs 10 %
> more candidates and reintroduces the flat floor that is the thing being removed. Note the adaptive
> rule is **not** a superset — for confident atoms it is *narrower* than 12.0 ppm — and retention
> still rises, because the loss was concentrated in high-σ resonances the flat radius truncated.
>
> A pairing one scale away now scores `exp(-0.5)` for every atom on every nucleus, which is what
> makes merits comparable across a molecule at all. Without a calibration the behaviour is
> byte-identical to before, asserted by a test, and `details.window_basis` records which ruler
> priced each resonance plus the calibration fingerprint.
>
> ### And the finding that neither window can fix
>
> Ambiguity is **intrinsic at this predictor's accuracy, not a tuning failure.** Replicating
> `_group_resonances` (ε = 0.50 ppm ¹³C / 0.03 ppm ¹H) on both sides and deduplicating observed
> shifts to lines — i.e. matching as `PredictionBoundsTest` actually does — **26.5 % of in-window
> ¹³C resonances and 32.5 % of ¹H resonances have a rival line strictly closer to the prediction
> than their own**. Narrowing the window from the current rule to conformal-90 cuts exposure 33 %
> (1.917 → 1.278) but misassignment only 2.3 pp (26.5 % → 24.2 %).
>
> Two honest limits on that number. It is measured on **clean assignment data with no spurious
> peaks** — with the picker over-picking 3–7×, real spectra are worse. And it is a **per-resonance
> ambiguity rate**, not end-to-end assignment accuracy: the real matcher's sequential `used[]`
> bookkeeping is order-dependent and this does not model it. (The raw per-atom figure before
> grouping was 36.0 % / 42.2 %; quoting *that* would have reported the measuring method's artefact
> as the pipeline's defect.)
>
> The actionable conclusion is that the scoring model, not the window, is where this belongs:
> `PredictionBoundsTest` scored a match as corroboration without discounting for how many other
> lines could have matched equally well.
>
> **Fixed 2026-08-08.** `_ambiguity_weight` is a normalised likelihood under the same Gaussian the
> merit function uses — the posterior that the line the matcher chose is the right one, given the
> alternatives. One candidate gives **exactly 1.0** (so an unambiguous match is untouched, which is
> what makes it safe to land); `k` equidistant candidates give **exactly 1/k**; a distant rival
> barely dilutes anything. It depends only on the distances, so it is **order-independent**, and
> rivals are counted over *all* in-window units including ones an earlier resonance already took —
> ambiguity is a property of the spectrum and the prediction, not of the greedy matcher's order.
>
> It attenuates **significance**, never score. Five candidate lines do not mean the structure is
> wrong; they mean the observation says little either way, and significance is the channel the
> module defines as "how much the verdict should count". The discount can only attenuate, never flip
> a sign. Scale is the resonance's conformal interval where one exists, the claimed σ otherwise, and
> an unusable scale degrades to the uniform `1/k` rather than a NaN that would reach the posterior.
> `details.mean_ambiguity_weight` plus per-resonance `ambiguity_weight` / `candidate_lines` are
> recorded, so a verdict reached on diluted evidence is visible as such.
>
> **Aggregate effect, measured** (`scripts/measure_ambiguity_discount.py`, same held-out split):
>
> | | ¹³C (32,234) | ¹H (10,521) |
> |---|---|---|
> | mean ambiguity weight | 0.610 | 0.537 |
> | median | 0.542 | 0.480 |
> | undiscounted (> 0.99) | 32.4 % | 25.7 % |
> | halved or worse (< 0.5) | **41.1 %** | **50.5 %** |
> | mean significance | 3.851 → 2.566 | 2.812 → 1.694 |
> | odds multiplier, fully corroborating | **×7.20 → ×4.94** | **×5.42 → ×3.25** |
>
> The shift test was over-claiming its evidence by **31 % on ¹³C and 40 % on ¹H** in odds terms.
> A third of matches are genuinely unambiguous and untouched; the median match was carrying about
> twice the weight it had earned.
>
> **It shifts verdicts.** From a 0.50 prior a single fully corroborating test now reaches 0.832 on
> ¹³C (still above the 0.80 `consistent` threshold) and **0.765 on ¹H (below it)** — so a ¹H-only
> verification that read `consistent` on a perfect match now reads `inconclusive`. That is the
> intended direction, since one nucleus matching among ~2 candidate lines per resonance is not a
> confirmed structure on its own, but it is a real change in what the platform tells a user.
>
> **Softened to 40 % by direction (2026-08-08).** `_AMBIGUITY_FLOOR = 0.40`, applied affinely as
> `f + (1-f)·w`. A **policy choice, not a measured constant** — selected as the point where a fully
> corroborating ¹H test returns to `consistent`, i.e. by the verdict it produces. Recorded as such in
> the constant's docstring and pinned by a test. A hard `max(f, w)` was tried first and cannot do
> this: swept to 0.50 it touched 41 %/51 % of matches and moved the posterior only +0.012/+0.022,
> leaving ¹H below threshold at every value, because the tail carries almost none of the aggregate.
>
> | | ¹³C | ¹H |
> |---|---|---|
> | mean weight | 0.610 → 0.766 | 0.537 → 0.722 |
> | halved or worse | 41.1 % → 4.1 % | 50.5 % → 8.3 % |
> | odds multiplier | ×4.94 → ×5.92 | ×3.25 → ×4.10 |
> | posterior | 0.8317 → 0.8556 | 0.7645 → **0.8040** |
> | verdict | consistent | inconclusive → **consistent** |
>
> Against the undiscounted baseline the discount now removes 17.8 % of the evidence on ¹³C and
> 24.4 % on ¹H, down from 31.4 % and 40.1 % — roughly three-fifths of its measured strength retained.
> `w = 1` still maps to 1.0, so an unambiguous match stays undiscounted.
>
> **Caveat that bounds all of the above.** Measured on clean assignment data with no spurious peaks.
> Real spectra carry 3–7× more lines (B1), so the true ambiguity — and therefore the true
> over-claim — is larger than these figures, not smaller.
>
> **Still pending:** the two conformal metrics in `GoldMetricVector` (see the safety-critical
> rollout hazard below).
>
> **Rollout hazard to resolve before promoting coverage to `SAFETY_CRITICAL`.** The adapter's
> promotion gate refuses when one evaluation reports a safety-critical metric and the other does
> not — the anti-asymmetry rule. Adding a third safety metric would therefore refuse every
> promotion during rollout, because no incumbent reports it yet. Add it as a normal metric with
> tolerance 0 first (same strictness, no trap), and promote it once evaluations report it across
> the board.

### D1 — original specification

B5 measured the defect precisely: reported ¹³C σ is **optimistic ~3× in the 0–0.5 ppm bin** —
worst exactly where the verifier's `_significance_from_sigma` weights it highest. Platt and
temperature scaling (`ai/finetune.py`) fix *classifier* calibration; they do not give a
regression predictor a coverage guarantee.

**Split conformal prediction** does, and it is the right tool for a regulated claim because its
guarantee is distribution-free and finite-sample: calibrate on a held-out split, and a 90%
interval covers the truth ≥90% of the time regardless of whether the model is any good.

* Method: **Mondrian (class-conditional) split conformal**, binned by nucleus × predicted-σ decile
  — the binning is what repairs the tight-σ bin specifically, instead of inflating every interval
  uniformly.
* Calibration set: the B5 held-out molecule split (SHA-256 molecule-level, already disjoint).
* Output: `ShiftPrediction` gains `interval_lo`, `interval_hi`, `coverage_target`,
  `conformal_version` alongside the existing σ. **σ stays** — it is the model's claim; the
  interval is the guarantee. Reporting both is the honest form.
* Consumer change: `verification/scorer.py::_significance_from_sigma` switches to the conformal
  interval width. This changes a regulated scoring path, so it needs an invariant test **first**
  and a visible re-baseline — the same standard applied to the ν finding.
* Metric: add **empirical coverage** and **mean interval width** to `GoldMetricVector`. Coverage
  below target is a `SAFETY_CRITICAL` regression; a narrower interval at equal coverage is the
  only honest definition of "sharper."

### D2. Δ-learning, not a second model *(new)*

The tempting next step is a bigger predictor. The measured evidence says otherwise: a matched
HOSE environment already beats the element prior **13.7×** on ¹³C, and the residual error is
right-skewed (p95 = 12 ppm, max = 146) — i.e. concentrated in specific environments, not spread.

**Δ-learning** targets exactly that: train a small model on the *residual* (measured − HOSE
prediction) rather than on the shift itself, using features the KB cannot see (solvent,
concentration/pH proxies, ring strain, stereochemistry, long-range through-space terms). This is
the established pattern in the shift-prediction literature and it has three properties this
codebase needs:

1. It **cannot be worse than the baseline** — a residual model that learns nothing predicts 0 and
   the system falls back to the HOSE number exactly.
2. It is small enough to train on CPU, so it does not depend on the GPU sidecar landing.
3. Its provenance is a second entry in `model_versions`, not a replacement — the router's existing
   layer mechanism already expresses it (`Layer.DELTA_RESIDUAL` alongside the three current ones).

**Gate:** deploy only if it dominates on the B5 gold set with no `SAFETY_CRITICAL` regression, per
`eval.harness.dominates`. If the gain is under the harness tolerance, do not deploy — the same
rule the roadmap states for fine-tuning (<5pp ⇒ pretrained is good enough).

### D3. Training sets — the decision, extended

`structure_elucidation_program.md` B0a settled the split by role and by licence. Restated with
the two additions this program needs:

| Source | Licence | Role | Constraint |
|---|---|---|---|
| **NMRShiftDB2 / NMReDATA** | CC BY-SA | HOSE KB (49,618 mol / 495,215 assignments) | ShareAlike is viral on a **redistributed** derived table → deployed state only, never a shipped artifact. Already in `NOTICE`. |
| **NMRexp** (3.37 M records) | **CC BY 4.0** | The **published** benchmark + proton-inventory validation at scale | The only corpus both real-experimental and commercially redistributable. 2.1 GB already on disk, gitignored. Baseline: 98.8% readable, 0 inventory violations — re-run after any parser change. |
| **QM9-NMR** | open | Regression test only | Error against DFT targets, ≤9 heavy atoms, CHNOF. Never in val/test. |
| **Δ-learning residuals** *(new)* | derived | L1/D2 training | Inherits the licence of whatever produced the measurement. Split **by molecule SHA-256**, same as B5, or the residual model memorises the KB. |
| **BMRB** *(new)* | open | Independent held-out validation | Not in the KB and not in NMRexp → the only genuinely third-party check on both. `scripts/fetch_bmrb_metabolomics.py` already exists. |

**Datasets the roadmap lists that this program declines, with reasons:** SDBS (AIST — no
redistribution), METLIN full (licence), Reaxys (commercial, $$$). `datasets_pipeline.py` already
excludes SDBS and METLIN from the corpus for exactly this reason; that decision stands.

### D4. What L1 must not become

* **Not CASCADE/PAiNN.** Same model class as NMRNet. A swap is a proposal only after a measured
  A/B on the B5 gold set.
* **Not GIAO-DFT in the interactive path.** Hours to days per molecule. It is an offline tier
  with a queue, a cost ceiling and a named requester — and it is blocked on the Redis/RQ consumer
  that is deliberately not deployed (see `project_pending_redis_worker`).
* **Not a published MAE before B1/B3.** With the picker over-picking 3–7×, the assignment step
  matches predicted shifts to spurious lines and reports a flattering error.

---

## Part E — Layers 2–7, in outline

Each is expanded into a full specification in its own pass, one per session, in the Part B order.

**L2 — Representation & retrieval.** Wire the dark regulatory RAG (C4). Upgrade spectral
retrieval from single-vector similarity to **hybrid retrieval + cross-encoder rerank**, and adopt
**contextual retrieval** (prepend the chunk's document context before embedding) for the guidance
corpus, where the failure mode today is a chunk that is correct but unattributable. Bump
`ENCODER_VERSION` and rebuild on any encoding change — a persisted index's dimension cannot detect
one. For MS, evaluate a self-supervised MS/MS embedding (DreaMS-class) against the current
MS2DeepScore path on a held-out split before adopting.

**L3 — Reasoning.** Move both RAG call sites to the Claude 5 family, pinned in one place, model
id recorded per audit entry. Convert the reasoner from free-form proposal to **tool-grounded**:
prose from the LLM, every number from a tool call into the deterministic engines — the pattern
already proven in the Repho reaction agent (`project_repho_reaction_agent_fe`). Add
retrieval-grounding metrics (answer-in-context rate, citation precision) to the harness.

**L4 — Post-training.** First real run, only once L6 has produced ≥1,000 labelled corrections.
LoRA → **DoRA** for the same parameter budget. For preference learning, **DPO/ORPO** rather than
PPO — no separate reward model to drift. Then the architecturally-native idea: **RLVR
(reinforcement learning from verifiable rewards)** using `verify_structure` as the reward oracle.
MolTrace already owns the thing most teams lack — a deterministic verifier that can score a
proposal without a human. That is a genuine, defensible moat and it is a natural fit for the
existing constraint that AI may only reorder within a verdict class.

**L5 — Evaluation & calibration.** Conformal coverage + interval width into `GoldMetricVector`
(D1). Build the **decoy generator and false-confirmation measurement** (B5.2) — accuracy on
correct structures says nothing about how often a wrong one is confirmed, and
`false_confirmation_rate` is already a zero-regression metric with nothing feeding it. Adopt
**scaffold-split** and **MCES-distance** evaluation for MS→structure so the benchmark is
comparable to published work.

**L6 — Feedback & active learning.** The roadmap calls this the moat and it is the one layer with
*zero* production data flowing through it. Entry point is `POST /ai/predictions/{id}/feedback`
(C3). Then: reason-taxonomy capture → disagreement scoring across the router's layers →
budgeted annotation queue → retraining trigger. Every override is an L4 training example and an
L5 gold-set candidate. Nothing auto-deploys — human sign-off per GAMP 5 D11, enforced at C2's
approve route.

**L7 — Governance & MLOps.** Emit an **AI Bill of Materials** (CycloneDX ML-BOM) per model
release, joining the existing SBOM + SLSA provenance gates in `ci-cd.yml` — model card, dataset
lineage, licence obligations (the CC BY-SA constraint is a *distribution* fact and belongs in a
machine-readable manifest). Map the artifacts each layer already produces onto GAMP 5 Appendix
D11, FDA's January 2025 AI credibility framework, and EU AI Act Article 17 — **as controls
designed to support those frameworks**, never as a compliance claim. SOC 2 is not held.

---

## Part F — claim-integrity register

Nothing in this program licenses a public claim. Specifically:

| Claim | Allowed when |
|---|---|
| "MolTrace predicts ¹³C shifts to X ppm" | X is produced by `eval/shift_accuracy.py` on a held-out molecule split, quoted as **MAE and median and p95**, stratified by class. Never a benchmark MAE from a paper. |
| "Calibrated confidence" | Empirical conformal coverage ≥ target on the held-out split, reported with interval width. |
| "Active learning improves the model" | An `eval.harness.dominates` pass of a post-L6 checkpoint over its predecessor, with the labelled-example count stated. |
| "AI-assisted structure verification" | Always — the verifier is deterministic and the AI proposes. This one is already true. |
| Anything with "SOC 2", "compliant", "validated" | Never in this form. "Designed to support." |

---

**Procedure:** runbook Part C, P0 (evidence pass) complete — every count and import above taken
from this checkout. P1 (rule check) applied: A3.4 (SOC 2), A3.5 (tooling fragmentation vs the
HMAC-chained audit trail), C4 (no regulated number from a reasoner) and D1 (regulated scoring
path ⇒ invariant test before re-baseline) are the four rule collisions found and resolved.
P2–P10 apply per layer at build time.
