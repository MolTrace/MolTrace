# MolTrace validation playbook

Step-by-step prompts for validating every NMR analysis path and product module
against real data. Each phase is self-contained: preconditions, the exact
fixture, the command, what to measure, and what "pass" means.

**Every route, blocker and line reference below was verified against the running
code on 2026-08-04, not inferred.** Where a phase is blocked, the blocker is
stated up front so nobody spends a day discovering it.

---

## Ground rules

1. **One phase at a time.** Finish and report before starting the next.
2. **Fix forward.** When a phase finds a defect, fix it, add the regression
   test, re-run the phase, then move on.
3. **Never validate against synthetic data when real data exists.** The three
   defects found on day one were all invisible to the synthetic suite.
4. **A passing HTTP status is not a pass.** Every phase asserts a scientific
   or security property, never `200 OK`.
5. **Re-baseline visibly.** If a test encodes a defect, change it in place with
   a comment saying what moved and why. Never silently update an expectation.

---

## Environment

```bash
cd ~/MolTrace/moltrace_backend
PYTHONPATH=src .venv/bin/python -m uvicorn --factory nmrcheck.api:create_app \
  --host 127.0.0.1 --port 8000
```

Health check must return `{"status":"ok"}`:

```bash
curl -s http://127.0.0.1:8000/health
```

### Authentication

```bash
EMAIL="validation.$(date +%s)@moltrace.co"; PASS='V4lidation!Pass2026'
curl -s -X POST http://127.0.0.1:8000/auth/register -H 'content-type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}"
curl -s -X POST http://127.0.0.1:8000/auth/login -H 'content-type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}"
```

Use `access_token` as `authorization: Bearer <token>`.

> **Reserved TLDs are rejected.** `.local`, `.test`, `.example` all 422. Use a
> real domain.

> **CRITICAL for any security phase.** With `API_KEY` unset — the default —
> `Settings.local_auth_disabled` is `True` and the server does **not** enforce
> per-user auth. Any cross-tenant test run against a default server proves
> nothing. Set `API_KEY` before Phase B2.

### Fixtures

`validation_fixtures/` (gitignored), staged from the user's own Bruker data:

| Fixture | Solvent | Recycle | Scans | Raw FID | Processed 1r |
|---|---|---|---|---|---|
| `naw-1-244-54pt/10` | CDCl₃ | 30.0 s | 16 | yes | yes |
| `naw-1-244-54pt/11` | CDCl₃ | 5.0 s | 16 | yes | yes |
| `MH0143-…-5/6/7/8` | D₂O | 5.0 s | 128 | yes | no |
| `33` | MeOD | 5.0 s | 64 | yes | yes |

`10` and `11` are the same sample at two recycle delays — the only true matched
pair, and the anchor for every quantitation claim.

Regenerate with `validation_fixtures/inventory.json`. Parse Bruker delays from
the `##$D= (0..63)` **array**, not a `##$D1=` scalar — that scalar does not
exist and reading it yields `D1 = 0` for every dataset.

---

# Track A — analysis paths

## A1. Processed NMR upload — PARTLY DONE, see "A1 RESULT" at the end

> **Status 2026-08-04.** The Bruker blocker below is real and unchanged, but it
> does **not** block the phase: the path was exercised end to end by converting
> a real `1r` to CSV offline. The A/B against the raw-FID path found that the
> two ingest routes agree on peak POSITIONS (median Δ 0.009 ppm) and disagree
> wildly on INTEGRALS (per-peak ratio spanning 0.12–20.0), with both differing
> from the trace itself by ≥30% at every integration window. Full method,
> numbers and limits in **A1 RESULT** at the end of this document.
>
> Still untested from the list below: `/nmr/processed/analyze` persistence,
> the `preview_points_json` override, and the peak-table CSV branch. The run
> used `POST /spectrum/preview`, not the full analyze routes.

> **BLOCKED for Bruker.** `parse_processed_spectrum` (`spectrum.py:2516`)
> dispatches on file extension and accepts only
> `csv/tsv/txt/xy/asc/dat/jcamp/jdx/dx`. **There is no reader for Bruker
> processed data (`pdata/1/1r`).** Do not attempt to upload `1r` — scope the
> reader instead, or validate this phase with CSV/JCAMP only.

> **JCAMP is also unreliable.** `_parse_jcamp_text` (`spectrum.py:569-588`)
> skips all `##` headers and treats every data line as consecutive `(x,y)`
> pairs. It does **not** decode AFFN/PAC/SQZ/DIF/DUP, apply `XFACTOR`/`YFACTOR`,
> convert `XUNITS` Hz→ppm, or reconstruct from `FIRSTX/LASTX/DELTAX`. Real
> `(X++(Y..Y))` files mis-parse. The route's own warning concedes this.

**Prompt:**

> Validate the processed-spectrum upload path. First establish which formats
> are genuinely supported by reading `parse_processed_spectrum`
> (`spectrum.py:2516`) and its dispatch block (2537-2554) — do not assume.
>
> Export a fixture to a supported format and drive it through
> `POST /nmr/processed/analyze` (`api.py:10538`, the primary FE route) and
> `POST /spectrum/analyze` (`api.py:7507`, the legacy route that persists).
>
> Measure and report:
> 1. Peak count detected vs peaks visible by manual inspection of the trace.
>    Report the over-pick factor as a number.
> 2. Whether `/nmr/processed/analyze` persisted an analysis record. **It does
>    not** — there is no `save_analysis` call in its body. Confirm and report
>    the consequence for any loop that expects to retrieve the analysis later.
> 3. Whether passing `preview_points_json` causes the uploaded file bytes to be
>    ignored (`api.py:9963`). If so, state plainly that the analysis then runs
>    on the frontend's downsampled display trace, not the uploaded data.
> 4. The peak-table CSV branch bypasses peak detection entirely and uses
>    uploaded rows verbatim. Confirm, and state which validation claims that
>    branch can and cannot support.
>
> **Pass:** every supported format round-trips with a documented over-pick
> factor, and every unsupported format fails with an error naming the cause.
> **Fail:** any format silently produces a degraded result.

## A2. Raw FID upload — DONE, 3 defects fixed

Path is `fully_implemented` and works end to end. `POST /fid/preview`,
`POST /fid/process`, `GET /fid/runs/{id}/report`.

Verified on `naw-1-244-54pt/10`: Bruker zip detected, 131072 points, group-delay
correction, zero-fill ×2, 0.3 Hz exponential apodization, auto-phase −11.625°,
Bernstein-polynomial baseline, nmrglue. Acquisition gating correctly returned
**quantitative** (recycle 30.0 s, 30° pulse) and read `d1 = 22.00461` from acqus.

**Three defects found and fixed:**

1. **Solvent never read from acqus.** Every Bruker file carries
   `##$SOLVENT=`; nothing read it, so solvent arrived only from the upload form.
   An upload without one was analysed as solvent-unknown, silently disabling
   residual-peak referencing, the impurity library and the exchange model.
   Fixed: `_resolve_raw_fid_solvent`.
2. **Raw FID was never referenced.** `_reference_axis` took a target only from
   an explicit `reference_ppm` or a reference spectrum. Neither exists on an
   ordinary upload, so the ordinary upload was never referenced.
   Fixed: `_solvent_reference_target` residual-peak fallback.
3. **The reference-peak selector could not correct anything.** It ranked by
   distance to target, with intensity as a tiebreak — but `points` is the dense
   trace, so a sample at the target always existed and always won, making the
   shift ~0. It also ranked by `-abs(intensity)`, scoring a deep negative
   baseline swing as highly as a real peak, and returned one (−4.6e8).
   Fixed: take the tallest **positive** line in the window.

Measured effect on `naw-1-244-54pt/10`: axis error corrected from **+0.024 ppm
to 0.0000 ppm**; solvent resolves to CDCl₃; residual and water regions now
masked; impurity candidates 1 → 6.

**Remaining, not yet addressed:**

- Bruker writes `Acetone` for acetone-d₆ but the profile set keys on
  `acetone-d6`, so acetone datasets resolve to `acqus_unrecognised` and lose
  solvent handling. One alias fixes it; `canonical_solvent` is broadly used, so
  check blast radius.
- Two inconsistent upload size caps (vault 2 GiB vs route limit);
  `max_request_body_bytes` defaults to 0 (off) and multipart is exempt from the
  body guard.
- Caller processing settings are silently overridden for ¹H
  (`_apply_raw_fid_advised_constraints`, `fid.py:802` forces
  `zero_fill_factor=3`).
- Peak detection is auto-tuned to best-match the structure's proton target
  (`_structure_guided_peak_estimates`, `fid.py:3057`) — **this makes peak count
  partly a function of the expected answer.** Assess whether that is defensible.
- A 32-entry in-process LRU cache can return a stale result across a code
  change. Restart the server between validation runs.

## A3. Legacy vs P3 structure-constrained assignment

> **P3 never runs in production.** The only switch is the process env var
> `MOLTRACE_STRUCTURE_ASSIGNMENT` (`structure_assignment.py:43`), default off.
> There is **no request-level opt-in**, and the var is set in no deployment
> config — absent from Dockerfile, cloudbuild.yaml, settings.py. Cloud Run
> therefore never executes P3.

**Prompt:**

> Run both arms over `naw-1-244-54pt/10` and `MH0143-…-5`, toggling
> `MOLTRACE_STRUCTURE_ASSIGNMENT`.
>
> Before comparing, fix the **A/B input asymmetry**: legacy `observed.total`
> excludes peaks categorised `solvent` *and* `impurity`; confirm what P3
> excludes. Two arms fed different signals cannot be compared — resolve this
> first or the whole comparison is void.
>
> Then address: **P3 fails silently.** `_build_structure_assignment`
> (`peak_categorization.py:1140-1147`) swallows every exception and returns
> `None`, which is indistinguishable in the payload from "ran and found
> nothing". Make failure distinguishable before trusting any P3 result.
>
> There is no frozen golden for the P3 payload —
> `tests/test_nmr_inventory_golden.py` runs with the flag unset, so all six
> fixtures pin the legacy answer. Freeze a P3 golden as part of this phase.
>
> Also fix the env-var leak at `tests/test_nmr_real_spectra_accuracy.py:100`,
> which sets the flag process-wide and never restores it.
>
> **Pass:** both arms fed identical signals, P3 failure is visible, a P3 golden
> exists, and a recommendation on making P3 default is supported by measured
> agreement/disagreement counts.

## A4. GSD deconvolution

> **The critical question is answered, and the answer is bad. The production
> path discards the fit.** `spectrum.py:1275` emits `area=total_area`, where
> `total_area` is the **pre-deconvolution** sum (`spectrum.py:1236`). The
> production deconvolver never computes a per-component area at all —
> `gsd.py:162` returns `(center_ppm, height, width)` tuples only.
>
> So GSD currently cannot deliver quantitation for overlapped multiplets in the
> path SpectraCheck actually runs — which is the entire purpose of
> deconvolution.

**Prompt:**

> Do not begin by writing tests. Begin by deciding whether to make the
> production path use fitted areas.
>
> There are two independent GSD implementations: `nmrcheck.gsd` (production)
> and `moltrace.spectroscopy.peaks.gsd` (sidecar, explicitly "deliberately
> independent"). At level 4-5 the sidecar's areas are **not fitted either** —
> they are re-derived by a pure-Lorentzian approximation
> (`peaks/gsd.py:907`). Establish which, if either, produces a real fitted area.
>
> Note the code's own stated reason at `spectrum.py:1522-1524`: GSD runs once,
> on the winning candidate only, because full deconvolution is too expensive.
> Any fix must respect that cost constraint or explicitly renegotiate it.
>
> **No area/quantitation validation exists anywhere today.** The A/B gate
> asserts only `peak_count` and `environment_count`
> (`tests/test_gsd_prompt3_fe_ab_envelope.py:200-219`). Adding one is part of
> this phase.
>
> Validate against `naw-1-244-54pt/10` (30 s recycle — the cleanest
> quantitative data available). For a resolved multiplet, fitted areas must
> reproduce integration ratios within a stated tolerance.
>
> **Pass:** production GSD returns fitted areas, a quantitation test guards
> them, and the A/B fixture mechanism still works.
> **Acceptable alternative:** GSD is documented as non-quantitative and every
> user-facing surface stops implying otherwise.

## A5. DP4

> **DP4 exists and is genuinely implemented** — `dp4_scoring.py`, 360 lines,
> Smith & Goodman 2010 in log space with an in-house regularised-incomplete-beta
> Student-t CDF. `tests/test_dp4_scoring.py` passes (15 tests). It has **zero
> HTTP routes**; it is reachable only internally (`api.py:10879`).
>
> Do not confuse it with Repho's Bayesian reaction optimization — unrelated.

**Prompt:**

> Validate DP4 as implemented, then close the gap between it and what is
> claimed publicly.
>
> Confirm each of these by reading the code, then decide what to do:
> 1. **DP4+ (Grimblat & Sarotti 2015) is absent** — no sp2/sp3 separate
>    parameterisation, zero hits repo-wide.
> 2. **DP5 (Howarth & Goodman 2022) is absent** but is **cited in disclaimer
>    copy** (`unified_confidence.py:326`, `web.py:1490`). This is a
>    public-claim/implementation mismatch of exactly the kind that produced the
>    fabricated-qNEHVI incident. Treat as urgent.
> 3. **Predicted shifts are not DFT/GIAO** — they come from the in-house RDKit
>    empirical predictor (`nmr_prediction.py:419`). Published DP4 assumes DFT
>    shifts with published error parameters. Using empirical shifts with
>    DP4's Student-t parameters is not the published method; either source DFT
>    shifts or re-derive parameters from the empirical predictor's own error
>    distribution.
> 4. **Pairing is greedy, not an assignment** — `_pair_observed_predicted`
>    (`dp4_scoring.py:157-190`) walks observed peaks in list order. Two
>    candidates can be scored on different pairings, making them
>    non-commensurable.
> 5. **A non-published penalty term** — `log_lik += unmatched * math.log(0.5)`
>    (`dp4_scoring.py:278-283`) is not in Smith & Goodman. Either justify it in
>    the code and the docs or remove it.
> 6. **Silent failure** — `api.py:10879` swallows per-candidate prediction
>    failures with `except Exception: continue`, dropping the candidate.
>
> **Pass:** every public claim matches the implementation, the probability is
> commensurable across candidates, and failures are visible.

## A6. RAG

> **Exactly one RAG is real end to end: spectral similarity retrieval.** It has
> a route (`POST /spectrum/retrieve`), a 42,449-molecule NMRShiftDB2 FAISS index
> physically on disk, and it was verified to load and return neighbours.
>
> Everything else is dark:
> - **Regulatory RAG** — library-only, no route, no corpus. Neither
>   `moltrace.regulatory.intelligence` nor `.data` is imported under `nmrcheck`.
> - **`VectorRetriever`** (`rag_search.py:210`) raises unless an embedder is
>   injected; there is no default backend and none configured.
> - **`/spectrum/reason`** — `anthropic` is not installed and
>   `ANTHROPIC_API_KEY` is unset.
> - **`/regulatory/sources/search`**, **`/regulatory/dossiers/{id}/query`** —
>   real routes, `regulatory_source_documents = 0`, `regulatory_citations = 0`.
> - **`/knowledge/search`** — all source tables 0 rows.
> - **`retrieve_precedents`** — `reaction_literature_priors = 0` and the agent
>   layer is off by default.

**Prompt:**

> Validate spectral similarity properly, and make the dark subsystems honest.
>
> For similarity: drive `POST /spectrum/retrieve` with peak lists from the
> fixtures. Verify neighbours are chemically sensible, not just returned.
> Confirm the encoder-version contract — a persisted index cannot detect an
> encoding change from its dimension alone, so any encoder change requires
> bumping `ENCODER_VERSION` **and** rebuilding.
>
> For every dark subsystem: it must not appear in any user-facing surface as
> though it works. Either wire it (route + corpus) or gate it behind an
> explicit "not configured" state that the UI renders honestly. A route that
> returns an empty result because its corpus has zero rows is worse than a
> route that says it is not configured — the first reads as "nothing matched".
>
> Note the 2.1 GB NMRexp corpus was deleted for disk space; re-fetch from
> Zenodo `doi:10.5281/zenodo.17296666` if a phase needs it.
>
> **Pass:** similarity validated on real fixtures; every other RAG either wired
> or explicitly marked unconfigured everywhere it surfaces.

---

# Track B — module loops

## B1. SpectraCheck

> **Good news: the loop closes with no background worker.** Every analyze route
> is synchronous; `POST /jobs` executes inline (`orchestration_store.py:781`)
> and `POST /jobs/submit` falls back to FastAPI `BackgroundTasks` when
> `REDIS_URL` is unset. The undeployed Memorystore/RQ worker does not block this.

**Prompt:**

> Drive the full loop on `naw-1-244-54pt/10`: upload → analyze → review →
> report. Fix what breaks.
>
> Known obstacles, confirm each:
> 1. Analyze steps persist rows but **do not return their ids**, so a client
>    cannot chain to the report step without a separate list call. Fix by
>    returning the id.
> 2. **There is no server-side route that generates a report from a session.**
>    `POST /spectracheck/sessions/{id}/reports` stores a
>    client-supplied payload. Decide whether the product needs server-side
>    generation; a client-authored "report" is not defensible evidence.
> 3. **No PDF export exists in the HTTP surface.** `export_pdfa` is
>    library-only and needs optional `reportlab`.
> 4. **Managed files and artifacts have no owner scoping** —
>    `list_file_records`, `get_file_record`, `get_file_download`,
>    `get_artifact_record` (`orchestration_store.py:371-391`). Treat as a
>    security defect, not a loop defect.
> 5. `/reports/{report_id}` resolves against two different tables under one URL
>    space. Disambiguate.
> 6. 6 of 10 declared orchestration job types have no execution adapter
>    (`orchestration_store.py:41-52`). Either implement or stop declaring them.
>
> **Pass:** a chemist can upload a real FID and obtain a persisted report
> artifact they would accept as evidence, with owner scoping enforced
> throughout.

## B2. Regentry — security phase DONE, loop phase remaining

> **Set `API_KEY` before any probe.** With it unset, `local_auth_disabled` is
> `True` and cross-tenant tests prove nothing.

**Each of the five reported defects was re-probed individually. Two did not
hold.** Reporting them unverified would have burned a day fixing a
non-existent exploit.

| # | Defect | Verdict | Status |
|---|---|---|---|
| 1 | Cross-tenant write, `POST /regulatory/action-items` | CONFIRMED (201) | **Fixed** `b049003` |
| 2 | Cross-tenant signing, `POST /esignatures/records` | **CONFIRMED** once step-up is satisfied | **Fixed** — subject gate |
| 3 | E-signature register globally readable | CONFIRMED | **Fixed** `0d4174b` |
| 4a | Controlled records globally readable | CONFIRMED (200) | **By design** — see below |
| 4b | Controlled records globally *mutable* | **CONFIRMED** (see correction) | **Fixed** `0039` |
| 5 | `PATCH /compound-registry/compounds/{id}` | CONFIRMED (renamed, 200) | **Fixed** `0039` |

> **Correction, and a lesson worth keeping.** 4b was first recorded here as
> *refuted* because `PATCH /controlled-records/{id}` returns 405. That was a bad
> refutation: `PATCH` is not a route on this resource at all. The real mutations
> are `POST .../lock`, `.../new-version` and `.../archive`, and **all three were
> wide open** — an unrelated user locked another user's approved validation
> protocol (200), created a new version of it (201), and archived a second one
> (200).
>
> Probing one verb and generalising to "not mutable" nearly buried a GxP
> integrity failure. When refuting a mutation claim, enumerate the resource's
> actual write routes from the OpenAPI document first.
>
> A second defect surfaced with it: `locked_by` was taken from the request body,
> so a probe locked a record and it came back reading `locked_by: "attacker"`.
> The `archive` route on the same resource already attributed to the
> authenticated principal ("never client-supplied"); `lock` did not. Now
> server-derived, with the client's claim retained in metadata as
> `locked_by_client_claimed` rather than dropped.

**Controlled-record reads stay open deliberately.** The Validation Center
workspace is an oversight surface — a reviewer is meant to see records raised by
colleagues, and scoping reads to the creator would empty the screen for exactly
the people the feature exists for. Cross-customer separation is a real and
separate problem that **cannot be solved on this axis**, because there is no
server-derived tenant; calling per-user scoping "tenant isolation" would be
worse than naming the gap.

**What the fixes established, reusable for the rest:**

- Dossiers are correctly protected by `require_dossier_access`
  (`api.py:2819`) → `dossier_access_facts` → PDP, non-leaking 404. That gate can
  only reach a dossier named in the **path**. Routes naming it in the **body**
  must call `authorize_dossier_access()` explicitly.
- `regulatory_action_items` has no ownership column, so #1 authorizes through
  the parent `dossier_id`.
- `compound_entities`, `compound_batches` and `controlled_records` had **no
  ownership column at all**. Migration `0039` adds `created_by_user_id` to all
  three — required for ALCOA+ attributability regardless of access control,
  since "Attributable" is the *A*.
- **Not tenant-scoped, deliberately.** There is no server-derived tenant on a
  request: `AccessContext` carries none, `organizations` has no link to
  `tenants`, `tenants` is empty, and `team_members` is empty and keyed by
  `user_email`. Per-user is the only axis that can actually be enforced.
  Widening to an organisation later is a read-model change on top of this
  column; recovering who created an unattributed row is impossible.
- **Reads vs writes were split on purpose.** A compound registry is a shared
  reference — colleagues look up each other's structures — so closing reads
  would break the feature rather than secure it. Writes were the actual defect.
  This is the opposite call from dossiers, where ownership is itself
  confidential, which is also why the registry returns **403** rather than a
  non-leaking 404.
- A NULL `created_by_user_id` (pre-migration row) is refused to non-admins
  rather than treated as unowned-and-editable. "Nobody is recorded as
  responsible" must not read as "anyone may change it".

> **Second correction, same lesson.** #2 was first recorded as *not reproduced*
> because the route returns 401 `step_up_required`. That was also premature:
> step-up is trivially satisfied by any legitimate user with their **own**
> password. Once stepped up, a user produced an `approved` Part 11 signature on
> a regulatory dossier that had returned 404 to them a moment earlier.
>
> The route already enforced §11.200 step-up, §11.100 server principal and
> §11.70 content binding — but nothing checked that the signer could reach the
> subject. A correctly stepped-up principal signing under their own name is
> still forging evidence if they cannot reach the record.
>
> **The first fix attempt was wrong and the tests caught it.** Making unknown
> `target_type` values fail closed broke `test_unbound_target_is_honest`, which
> pins deliberate behaviour: an unresolvable type signs but stays honestly
> *unbound* (no content hash, `binding_status: "unbound"`). Binding and
> authorization are separate axes. The attack requires naming the **real**
> resource type — a subject is the `(target_type, target_id)` pair, so
> `analysis#7` does not attach to dossier 7 — so gating the ownable types and
> letting unknown ones through is both correct and non-breaking.

**Remaining prompt:**

> Extend `authorize_signature_target` as ownable subject types are added. It
> currently gates `regulatory_dossier` and `controlled_record`. `reaction_project`
> and `spectracheck_session` are real ownable subjects with existing gates
> (`require_reaction_access`) and should be added when someone confirms the
> signing flows that use them.
>
> Then sweep the rest of Regentry the same way: enumerate write routes from
> OpenAPI, probe each with a **valid** body (a 422 is schema validation, not a
> denial), and test the legitimate path too — the controlled-record fix
> initially failed closed for the owner because the create route was left
> unwired.
> checks that the caller may access the subject. If it does not, someone can
> sign a record they cannot read, which is a Part 11 integrity failure. Do not
> report it as an exploit until reproduced past the step-up gate.
>
> Then sweep every remaining Regentry route for the same omission; assume more
> exist, and check body-addressed parameters specifically — that is what hid #1.
>
> Then the loop: create → populate → review/sign → export, using the existing
> 4 dossiers and 15 method registry entries. Exercise Part 11 §11.70 verify and
> §11.50 manifestation, and ALCOA+ archive/restore.
>
> Note **export produces a manifest, not a file** —
> `create_submission_package` writes a JSON manifest of file/artifact ids. If
> the product promises a submission package, that is a gap.
>
> Keep all compliance language as "designed to support". SOC 2 is not held.

**Prompt:**

> Phase 1 — security. For each of the five routes, apply the existing
> `require_dossier_access` / `authz.authorize` pattern. Add a regression test
> per route asserting a non-owner receives a non-leaking 404. Then sweep every
> remaining route in the module for the same omission; assume more exist.
>
> Phase 2 — loop. Only once Phase 1 is green: create → populate → review/sign →
> export, using the existing 4 dossiers and 15 method registry entries.
> Exercise Part 11 §11.70 verify and §11.50 manifestation, and ALCOA+
> archive/restore.
>
> Note **export produces a manifest, not a file** —
> `create_submission_package` writes a JSON manifest of file/artifact ids. If
> the product promises a submission package, that is a gap.
>
> Keep all compliance language as "designed to support". SOC 2 is not held.
>
> **Pass:** every route owner-scoped with a test; a dossier round-trips through
> sign and export; no compliance claim is stated as held fact.

## B3. Repho

> **Existing rows are unreadable.** All 8 projects have `owner_id = None`, and
> `_owns_resource` (`authz.py:240-251`) returns `False` for a null owner, which
> `require_reaction_access` maps to a 404. So every seeded project 404s for
> everyone.
>
> Decide deliberately: backfill `owner_id` on the seed rows, or create fresh
> owned rows. Do **not** relax `_owns_resource` — returning `False` for an
> unowned resource is the correct default-deny.

**Prompt:**

> Establish readable data first (backfill owners or create fresh projects),
> then drive project → experiment → cycle → recommendation → feedback.
>
> Known empty tables that bound what is testable without writes:
> `reaction_execution_batches`, `reaction_execution_items`,
> `reaction_analytical_results`, `reaction_optimization_runs` — all 0. The
> make/test half of the loop cannot be exercised on existing rows at all.
> Cost, safety and green profiles are also 0 rows, so those GETs 404 on every
> project.
>
> Project 4 has a **rejected safety screening**, so
> `assert_execution_allowed` (`reaction_safety.py:422`) raises → 409 on any
> batch commit. That is correct behaviour — use it as a positive test that the
> safety gate holds, not as a bug.
>
> Verify the three invariants that matter:
> 1. Propose-next is human-gated and **executes nothing**.
> 2. The safety review gate blocks execution when screening is rejected.
> 3. Unsafe rejections stay **excluded** from preference learning.
>
> Then audit public copy against implementation. A fabricated algorithm name
> (qNEHVI) shipped in marketing once. Verify every named method against backend
> source, never against other marketing copy.
>
> **Pass:** loop completes on owned rows, all three invariants hold under test,
> and every publicly named algorithm exists in code.

---

## Cross-cutting findings

Not owned by a single phase; each needs a decision.

- **Auth is off by default.** `API_KEY` unset → `local_auth_disabled = True`.
  Any security conclusion drawn from a default local server is invalid.
- **Two route families reach the same core.** Legacy (`/spectrum/*`,
  `/analyze`, `/carbon13/*`) persists analyses; the newer FE family
  (`/nmr/processed/*`) wraps the same parsers and does not persist. The newer
  family self-identifies as `"legacy_route_wrapped": "/spectrum/analyze"`.
  Converging them is a product decision worth taking explicitly.
- **The 503 envelope hides the cause** — body is a generic "Service temporarily
  unavailable" with a correlation id. Fine for users, but validation runs need
  the real traceback; read the server log.
- **No Makefile, docker-compose, seed script or fixture loader exists.** Every
  phase currently re-derives its own setup. Worth building once.
- **The heaviest real-data test is excluded by default** —
  `tests/test_nmr_real_spectra_accuracy.py` is marked `slow` and `addopts`
  carries `-m 'not slow'`. Opt in explicitly.
- **`tests/test_regulatory_e2e.py` drives no HTTP route** — it is library-level
  with stubbed calculators. It will not catch any of the five Regentry
  security defects. Do not treat it as end-to-end coverage.

---

## A1 RESULT — processed NMR upload (run 2026-08-04, real data)

**Scope correction.** A1 was written as blocked because there is no Bruker `1r`
reader. That was true but not the whole picture: the reader is missing, yet the
processed-upload path itself is fully exercisable. `parse_processed_spectrum`
(`spectrum.py:2516`) accepts CSV, TSV, TXT, XY, ASC, DAT, JCAMP, JDX and DX. A
chemist with Bruker data simply cannot use it without converting first — that
is a real product gap, but a different one from "untestable".

Note also that `/analyze/upload` is a *different* thing again: it takes
JSON/CSV batches of `{smiles, nmr_text, solvent}` — reported NMR **text**, not
spectral data.

**Method.** Vault archive 28 (`33.zip`, the user's own 500 MHz spectrum: zg30,
NS=64, d1=1 s, AQ 4.0 s, MeOD) carries both a raw `fid` and a processed
`pdata/1/1r`. The `1r` was converted to CSV offline with nmrglue and uploaded
to `POST /spectrum/preview`; the same archive was previewed via
`POST /raw-fid/28/preview`. Same physical spectrum, two ingest paths.

**Peak DETECTION agrees. Peak INTEGRATION does not.**

- Positions: 17 mutual-nearest pairs within 0.15 ppm, median Δ **0.009 ppm**.
  Both paths are looking at the same resonances.
- Integrals: the per-peak H ratio between the two paths spans **0.12 to 20.0**.
  If the paths differed only in scale anchor — both report
  `integration_scale_basis: provisional`, so neither is anchored — that ratio
  would be one constant. A 167x spread means they genuinely disagree about
  which peaks are the big ones.

**Both disagree with the spectrum itself.** The `1r` trace was integrated
directly (baseline = median of the −2.0 to −0.5 ppm signal-free region) and each
path's proton shares compared against it, excluding the MeOD residual (3.31) and
water (4.87) so solvent suppression could not be mistaken for error:

| half-window | processed-CSV | raw-FID |
|---|---|---|
| ±0.02 | 83.9% | 83.8% |
| ±0.03 | 69.2% | 66.5% |
| ±0.05 | 58.6% | 50.4% |
| ±0.06 | 52.9% | 53.6% |
| ±0.08 | 30.0% | 72.3% |
| ±0.10 | 31.3% | 70.4% |
| ±0.15 | 40.9% | 63.6% |

Total absolute error in relative proton share, summed over 22 non-solvent
peaks. **Neither path falls below 30% at any window.** Worst individual cases at
±0.06: 4.706 ppm true 6.2% vs processed 25.1%; 7.837 ppm true 8.6% vs raw-FID
15.6% while processed says 1.4%.

**Honest limits of this measurement.** The reference integration uses a fixed
window and a crude baseline, so it under-integrates broad multiplets and cannot
serve as a precise ground truth. That is exactly why the window was swept
rather than chosen: the *ranking* of the two paths flips with it (processed
wins at ±0.08–0.10, raw-FID at ±0.05), so **no claim is made that either path
is better**. The robust claim is only that both are far from the trace at every
window, which no windowing artefact explains.

**Next prompt:**

> Do not fix this from the API surface. Both paths converge on the same peak
> LIST and diverge only on integrals, so the defect is downstream of detection
> and upstream of reporting — the integration/scale chain in `spectrum.py` that
> `project_nmr_quantitation_accuracy` already lists as partly outstanding
> (`_normalize_integrations_to_target` still forces sum == structural total;
> 0.5 H quantiser floor; solvent not masked from the denominator by default).
>
> Build the reference integrator properly first — per-peak windows from fitted
> linewidth, not a fixed ±0.06 — so there is a trustworthy arbiter. Without it
> you cannot tell a fix from a regression. Then re-run this A/B; it is cheap and
> now scripted.

---

## A1 RESULT, part 2 — a real ground truth (run 2026-08-04)

The run above had a genuine weakness and said so: with no trustworthy arbiter it
could show the two ingest paths *disagreeing*, but not which one was *wrong*.
That gap is now closed, and it did not need the reference integrator.

**The arbiter is the sample, not the software.** The fixture is a matched pair —
one sample, one probe, one pulse program (`zg30`), one solvent (CDCl3), differing
only in recycle delay:

| exp | d1 | AQ | recycle | verdict |
|---|---|---|---|---|
| 10 | 22.005 s | 7.995 s | **30.00 s** | fully relaxed → quantitative |
| 11 | 1.000 s | 3.998 s | 5.00 s | routine → semi-quantitative |

At 30 s recycle with a 30° pulse, exp 10 is quantitative. **Its own trace areas
therefore ARE the true proton ratios** — no structure knowledge required, no
arbiter that could itself be wrong.

### Finding 1 — the acquisition model change is validated

Measured differential saturation between the two halves (28 signal windows taken
from the relaxed spectrum, each compared as a share of its own spectrum's total,
which cancels the receiver-gain/`NC_proc` difference instead of assuming it away):

```
measured spread (exp11/exp10)  1.1334
current model  (T1_SLOW_S 8 s) 1.1543   +0.021  conservative
pre-fix model  (T1_SLOW_S 5 s) 1.0784   -0.055  OPTIMISTIC
```

The `b4014fc` change cut the error ~2.6× **and** moved it to the safe side: the
model now slightly over-warns rather than telling a chemist the integrals are
better than they are. Both classifications are also correct — exp 10
`quantitative`, exp 11 `semi_quantitative`. Baseline re-pinned in
`test_acquisition_quality.py` (1.141 → 1.1334, better method).

### Finding 2 — the processed path does NOT recover true proton ratios

Feeding exp 10 through `parse_processed_spectrum` gives 19 peaks summing to
353 H. Comparing each peak's reported share of total H against its share of true
trace area, over **well-isolated peaks only** (nearest neighbour > 0.15 ppm and
< 40 H, so the measurement's own partition error is excluded):

```
  ppm      H      H share   area share    error
 5.227    5.00      1.42%        1.51%     -6.4%
 2.100    2.00      0.57%        0.78%    -27.0%
 1.933    9.50      2.69%        2.34%    +15.2%
 1.472   25.50      7.22%        6.69%     +7.9%
 1.186    5.00      1.42%        2.59%    -45.4%
 0.812    1.00      0.28%        1.00%    -71.5%

median |error| 21.1%     worst 71.5%     within 10%: 2/6
```

**The error is systematic, not noise.** Large multiplets come back close to
right (+8%, +15%); the smallest signals are badly under-reported (−27%, −45%,
−71%). So the chemist most misled is the one reading a minor impurity or a single
diagnostic proton — the opposite of how an integration should degrade. Every
reported value also lands on the 0.5 H quantiser grid, across a 124:1 dynamic
range.

Pinned in `tests/test_processed_upload_accuracy.py`, which **skips** when the
fixture is absent (real spectra are gitignored, and a synthetic stand-in would
quietly turn this into a test that cannot fail).

**Next prompt:**

> The arbiter problem is solved — stop blocking on the reference integrator.
> `tests/test_processed_upload_accuracy.py` measures the error against a real
> quantitative spectrum, so a fix can now be told from a regression directly.
>
> Chase the small-peak bias specifically; that is where the whole error lives.
> Candidates, in order: the 0.5 H quantiser floor (50% granularity on a 1 H
> signal); `_normalize_integrations_to_target` still forcing sum == structural
> total; and per-peak integration windows still being width-insensitive, which
> costs a broad small peak proportionally more of its area than a sharp large
> one. Re-baseline `MEASURED_MEDIAN_ERROR_PCT` downward in the same change and
> say so.
>
> Then re-run the exp10-vs-exp11 comparison as a second check: a fix that
> improves the relaxed spectrum but not the routine one has probably tuned to
> this fixture rather than fixed the chain.

---

## A4 PREMISE — re-verified 2026-08-04 (it holds)

Re-checked while waiting on a suite run, and worth recording because the first
check reached the **opposite, wrong** conclusion.

`moltrace/spectroscopy/peaks/gsd.py` derives peak areas from fitted amplitudes
(`amplitude` at :654 and :823, analytic `height * fwhm * pi/2` at :912, with a
trapezoid fallback at :965). Reading only that file makes the A4 blocker look
stale — "GSD fits areas properly, the note is wrong".

It is not wrong. That file is the **sidecar**. The A4 claim is about the
**production** path, and there it holds exactly as written:

- `nmrcheck/gsd.py:155` `deconvolve_region` returns `(center_ppm, height,
  hwhm_ppm)` per line. **No area is computed at all.**
- `nmrcheck/spectrum.py:1236` `total_area = sum(component.area for component in
  cluster)` — the PRE-deconvolution cluster sum.
- `nmrcheck/spectrum.py:1275` emits `area=total_area`.

So production GSD uses its fit for **multiplicity only**; the area a chemist
reads never passes through the deconvolution. Two implementations with the same
name is the trap — check which one the path under test imports before
concluding anything about "GSD".

**Consequence for A1.** These are related but not the same defect. A1's
small-peak bias is measured on well-isolated peaks, where clustering is not in
play, so fixing GSD areas will not by itself close A1's 21% median error. Treat
them as independent and re-measure A1 after any GSD change rather than assuming
credit.

---

## A3 RESULT — legacy vs P3 (run 2026-08-04, real spectra)

**Headline: the comparison that looked decisive was circular, and the number
worth having was one nobody is reading.**

### The three prerequisite defects, all fixed

1. **Input asymmetry.** Legacy `observed_total` excludes `{"solvent",
   "impurity"}`; P3 excluded only `"solvent"`. The arms were solving different
   problems. Worse in P3's direction: conservation is a hard constraint there,
   so a leaked impurity is not merely over-counted, it is forced onto real
   structural positions and displaces the analyte's assignment.
2. **Silent failure.** `_build_structure_assignment` collapsed *never ran*,
   *raised and was swallowed*, and *ran and was infeasible* into a bare `None`.
   An arm that crashes on every fixture scored identically to one that
   legitimately declines, so the comparison could not fail. Now returns a named
   `status` (`ok` / `infeasible` / `error` / `no_assignable_signals`) with the
   exception type on error.
3. **Env-var leak.** `tests/test_nmr_real_spectra_accuracy.py` set
   `MOLTRACE_STRUCTURE_ASSIGNMENT=1` process-wide with no restore. pytest shares
   a process per xdist worker, so the flag leaked into every later test in that
   worker — meaning **which arm the slow suite measured depended on execution
   order**. Past green runs of that suite are not evidence about P3.

### The scored A/B, and why it means nothing

Seven structure-paired nmrshiftdb2 1H spectra, scored as summed absolute error
per class (aromatic / anomeric-olefinic / aliphatic / labile) against the
structure-derived `expected` block:

```
total class error   legacy = 33.0 H     p3 = 0.0 H
per-spectrum wins   legacy = 0   p3 = 6   tie = 1
```

P3 scores a perfect zero on all seven. **That is an identity, not a result.**
The solver pins it (`structure_assignment.py`, equality constraints):

```python
for j in range(n_cols):
    ...
    b_eq.append(demand[j])     # demand[j] = that environment's proton
                               # count, taken from the STRUCTURE
```

Every environment receives exactly its structural proton count as a hard
equality, so summing by class reproduces the structure's own composition.
Scoring `class_rollup` against a structure-derived expectation compares the
structure with itself.

**Falsified directly.** Feeding indole's structure three unrelated spectra:

```
real-ish indole spectrum     {'aromatic': 6.0, 'labile': 1.0}   status=ok
PURELY ALIPHATIC spectrum    {'aromatic': 6.0, 'labile': 1.0}   status=ok
ONE peak at 4.0 ppm          {'aromatic': 6.0, 'labile': 1.0}   status=ok
```

A spectrum with no aromatic signal whatsoever still reports 6 aromatic H.

This is the same circularity as the reported TOTAL, which
`_normalize_integrations_to_target` pins to the structural count in **both**
arms — which is why all seven spectra report a total exactly equal to truth in
both arms.

### The signal that is real, and unused

`total_cost` — the transport cost of moving observed signal onto the structure's
environments — is strongly spectrum-dependent:

```
matching spectrum        total_cost =    1.39
wrong compound entirely  total_cost = 1721.22      (~1234x)
```

But `feasible` stays `True`, `status` stays `ok`, and `notes` stays empty in
both. **The product computes a working structure-vs-spectrum mismatch signal and
does not surface it as any kind of verdict**, while surfacing a class rollup that
carries no spectral information at all.

Pinned in `tests/test_structure_assignment_is_not_a_measurement.py`.

### Recommendation

**Do not enable P3 by default on the strength of the class comparison**, and do
not present `class_rollup` anywhere as an *observed* inventory — least of all
beside the expected inventory, where it reads as independent corroboration and is
the structure agreeing with itself. In a regulated report that is a fabricated
cross-check.

**Next prompt:**

> Make `total_cost` a verdict. It already separates a matching spectrum from a
> mismatched one by ~1200x; calibrate a threshold from the seven fixtures plus
> deliberate mismatches, and have P3 report structure-spectrum disagreement
> instead of `feasible: true` on a spectrum from another compound. That converts
> P3 from a tautology into the consistency check it was meant to be.
>
> Then decide what, if anything, `class_rollup` is for. If it stays, rename it so
> no caller can read it as observed — it is the structure's composition, and the
> legacy arm is the only one attempting a measurement.
>
> Legacy's 33.0 H of class error is real and worth fixing on its own: an N-H
> resonating in the aromatic window is counted aromatic (indole: legacy 7
> aromatic / 0 labile, truth 6/1), and one fixture reports `aromatic: 1.0` for a
> C6H10O2 with no aromatic ring available at all.

---

## A4 RESULT — GSD deconvolution (run 2026-08-04)

**The blocker is confirmed, with evidence, and the decision is NOT to wire the
fitted areas in yet. Reason below — it is a mixed-basis hazard, not reluctance.**

### The defect, pinned

`deconvolve_region` (`nmrcheck/gsd.py:155`) fits a sum of pseudo-Voigt lines,
each `[amp, centre, hwhm, eta]`. The area of such a line is analytic:

```
area = amp * (eta * pi * hwhm + (1 - eta) * hwhm * sqrt(pi / ln 2))
```

Every fitted area exists at the moment of the fit. The function returns
`(centre, height, hwhm)` — dropping `eta` — and its sole consumer
(`spectrum.py:1263`) reads `[line[0] for line in resolved_lines]`, the centres
and nothing else. The number a chemist reads is
`total_area = sum(component.area ...)` (`spectrum.py:1236`), summed over raw
local maxima **before** any deconvolution.

So the deconvolution informs multiplicity and never touches quantitation.

### The fit is good — that is what makes the discard costly

Verified on closed-form synthetics (`tests/test_gsd_fitted_areas.py`):

- two equal-width lines with heights 1:3 → fitted areas recovered in ratio 3.0
- a broad/short line and a sharp/tall one carrying **equal** area (50×π×0.06 vs
  150×π×0.02) → recovered in ratio 1.0 despite a 3× height difference

That second case is precisely what a raw local-maximum sum cannot do, and it is
the case overlapped multiplets present.

### Measured stake on real data — with a caveat that matters

`naw-1-244-54pt/10`, comparing raw trapezoid integration against the sum of
fitted line areas:

```
  region ppm    lines   fitted/raw
  7.80- 7.60      6       1.310
  4.35- 4.20      9       1.272
  4.80- 4.40     10       1.171
  2.15- 1.85      2       1.018
  1.55- 1.15      2       0.932
  aggregate                1.151
```

The denser the overlap, the more the fit recovers — the expected signature of
raw integration losing tail area to neighbours.

**Caveat, and it is load-bearing:** those fitted sums assume a pure Lorentzian
(`h·π·w`) because **the return type drops `eta`**. A pseudo-Voigt with `eta < 1`
carries up to ~32% less area for the same height and width, so every ratio above
is an UPPER BOUND. The true gap cannot be measured from outside the function at
all. That is not a footnote — it is the strongest single argument for exposing
the area from inside the fit rather than reconstructing it downstream.

### Why not wire it in now

A cluster is emitted as ONE `_PeakEstimate`. Deconvolution runs only when
`len(cluster) >= 2` and the region has enough points, so swapping in fitted areas
would put **some** clusters on a fitted basis and leave others on the raw basis,
within the same spectrum. Mixed-basis integrals are worse than consistently-raw
ones: the ratios between peaks — the only thing a proton count depends on —
would then depend on whether each peak happened to qualify for deconvolution.

This also interacts with two results already in hand: A1's 21% median
integration error on isolated peaks, and the apportionment change in `4099eb8`.
Changing the area basis without re-measuring against the exp-10 ground truth
would make all three uninterpretable together.

**Next prompt:**

> 1. Widen `deconvolve_region` to return the fitted area per line, computed
>    inside the fit where `eta` is known. `tests/test_gsd_fitted_areas.py`
>    asserts the current 3-tuple deliberately — re-baseline it in the same
>    change and say so.
> 2. Decide the basis rule BEFORE using the areas, and make it all-or-nothing
>    per spectrum: either every cluster's area comes from a fit (deconvolve
>    unconditionally, including singletons) or none does. Record the basis in
>    the payload next to `integration_scale` so a reader can tell which was used.
> 3. Re-measure against exp 10 with `tests/test_processed_upload_accuracy.py`.
>    That fixture is quantitative, so its trace areas are the true ratios: if
>    fitted areas are the improvement they look like, the 21.1% median error must
>    drop. If it does not drop, the deconvolution is not the constraint and the
>    remaining error is in the scale chain.
> 4. Only then consider splitting a cluster into multiple environments. That is a
>    separate and much larger feature — it needs a rule for telling "one
>    environment, several J-coupled lines" from "two environments that overlap",
>    which the line positions alone cannot settle.

---

## A5 RESULT — DP4 (run 2026-08-04)

**DP4 exists and is implemented correctly. It is fed the wrong kind of
prediction, and it scores only the peaks the predictor already got right.**

### First, a correction to an earlier note

The standing note said "DP4 exists but DP5 is claimed-not-built". That
overstates it. DP5 appears in three places and **none is an implementation
claim**: two disclaimers that explicitly say results are "not ... calibrated
DP4/DP5 probabilities", and one bibliographic entry (title, authors, venue, DOI)
appended to the reference block when a DP4 ranking exists. Citing subsequent
literature beside a related result is normal practice. On DP5, the code is
honest.

`smith_goodman_2010_dp4` — the method actually implemented — is cited in the
base reference list, correctly.

### The real defect: DFT constants on an empirical predictor

`dp4_probabilities` is a faithful Smith & Goodman 2010 implementation: Student-t
likelihood, regularised incomplete beta, published σ/ν, linear calc→exp scaling.
15 unit tests cover that arithmetic and it is sound.

Those constants —

```
DP4_SIGMA_1H = 0.185     DP4_NU_1H = 14.18
```

— are the residual distribution of **DFT/GIAO-computed** shifts after scaling.
The paper is *"Assigning the Stereochemistry of Pairs of Diastereoisomers from
GIAO NMR Shift Calculations"*.

Production computes no DFT. `api.py:10995` calls
`predict_nmr_from_smiles_fast`, documented as **"RDKit atom-environment
prediction"** — an empirical predictor with a different, wider error
distribution.

The failure mode is asymmetric and therefore dangerous: a DP4 posterior is steep
in σ, so an understated σ **saturates the posterior toward 1.0** for whichever
candidate sits nearest. It yields a confident number, not an obviously wrong
one — the worst shape for a figure quoted into a structure-assignment argument.

### Measured on the seven structure-paired real spectra

```
paired within DP4's own 0.3 ppm window   n=24   RMSE 0.416 ppm   2.25x sigma
paired without any window                n=51   RMSE 1.429 ppm   7.72x sigma
```

**Both are biased, in opposite directions** — the narrow window silently drops
every badly-predicted peak; the wide one greedily pairs distant ones. The truth
is bracketed between them, not pinned. A first pass reported only the censored
2.25x and looked like six clean cases plus one outlier; uncensoring showed every
case above σ (0.53 to 2.04 ppm RMSE) and the "clean six" to be an artefact of the
window. Do not quote either number without its pairing rule.

What is unambiguous: **even the favourably-selected matched subset sits at 2.25x
the assumed σ**, and **fewer than half the peaks pair at all** (n 24 of 51).

### The likelihood is built on a favourable subset

Because pairing happens at 0.3 ppm, the Student-t likelihood is evaluated over
the peaks the predictor already placed well. Everything it could not place is
absorbed by a **flat** penalty:

```python
log_lik += unmatched * math.log(0.5)      # dp4_scoring.py:279
```

That does not scale with the residual. Verified: a candidate missing by 0.4 ppm
and one missing by 4.4 ppm on the same peak produce **identical** log
likelihoods. (When *nothing* matches, DP4 short-circuits to `-inf` / probability
0, which is separate and reasonable.)

So a candidate that is slightly wrong everywhere and one that is absurdly wrong
everywhere are charged the same for the peaks neither could place, while the
posterior's confidence comes from the minority that happened to land.

Pinned in `tests/test_dp4_input_calibration.py`.

**Next prompt:**

> Do not "fix" this by widening σ to the measured value. That trades a wrong
> constant for a hand-fitted one and still calls the output a DP4 probability.
>
> Decide first what the number is FOR. Two defensible routes:
>
> 1. **Keep DP4 honest by feeding it DFT.** Requires a GIAO pipeline the product
>    does not have. Large, and the right answer only if calibrated posteriors
>    are actually a selling point.
> 2. **Stop calling it DP4.** Keep the Bayesian ranking as a relative
>    discriminator, calibrate σ/ν empirically against a proper corpus (the seven
>    fixtures are far too few), and rename the output so no reader takes it for
>    the published DP4 posterior. The existing "not a calibrated DP4/DP5
>    probability" disclaimer already points this way — the ranking payload should
>    say the same thing.
>
> Either way, make the unmatched penalty scale with the residual, and surface the
> matched fraction next to the probability. A posterior computed from 24 of 51
> peaks should say so.

---

## A6 RESULT — RAG subsystems (run 2026-08-04)

**Two RAGs exist. One is wired and works on a real corpus; the other is
library-only. The wired one has a licence gate that fails OPEN.**

### Which is actually reachable

| module | wired? |
|---|---|
| `moltrace/spectroscopy/ai/rag.py` | **yes** — `POST /spectrum/reason` (`api.py:9290`) |
| `moltrace/regulatory/intelligence/rag_search.py` | **no** — 0 references in `api.py` |
| `moltrace/regulatory/ai/rag_reasoner.py` | **no** — 0 references in `api.py` |

So the regulatory RAG is library-only, as the standing note said. The
spectroscopy RAG is live.

### Correction: the corpus is real, not synthetic

A standing note read "`raw_data_vault` is 95% synthetic residue" and it was easy
to carry that over to the RAG. **It does not apply.** The similarity index is a
separate artefact: `spectrum_similarity_index/` — 51 MB, FAISS, separate 1H and
13C indices, **42,449 records, every one carrying a SMILES**, all sourced from
`nmrshiftdb2.nmredata.sd`. That is a real public NMR database. Retrieved
precedent is genuine.

`raw_data_vault` (uploaded files) and `spectrum_similarity_index` (the retrieval
corpus) are different things; do not carry a judgement about one onto the other.

### The finding: the licence gate defaults to off

Every index record carries:

```json
"license": "CC-BY-SA (NMRShiftDB2) - local use only, do not distribute"
```

The plumbing around this is genuinely well built:

- `SpectrumReasonAnalogue.license` carries the terms into the API response
  (`api.py:8605`), so attribution travels with the data;
- `build_reasoning_context(..., allowed_licenses=...)` implements a filter;
- the index itself is gitignored, so it is not shipped in the repo.

But the filter is caller-supplied and **defaults to nothing**:

```python
allowed_licenses: list[str] | None = Field(default=None, max_length=64)   # models.py:16422
license_filter = {str(x) for x in allowed_licenses} if allowed_licenses is not None else None
```

So by default `POST /spectrum/reason` returns SMILES from records whose own
metadata says *"local use only, do not distribute"*, to any authenticated
caller. The safe behaviour requires the caller to opt in, which is the wrong way
round for a commercial product — a licence gate should fail closed.

**This is a legal question, not a scientific one, and it is not mine to settle.**
CC-BY-SA does permit redistribution with attribution and share-alike, and the
"do not distribute" wording appears to have been added by whoever built the
index rather than by the upstream licence. The point is narrower: the product
currently redistributes by default, on data it has itself labelled
non-distributable, and nobody has to make a decision for that to happen.

**Next prompt:**

> Make the licence gate fail closed. Give `allowed_licenses` a deployment-level
> default rather than `None`, so serving a record is a configured decision
> instead of the fallback. Keep the per-request override.
>
> Then get a ruling on the corpus terms and put it in writing next to the index
> builder — if NMRShiftDB2 CC-BY-SA redistribution is fine with attribution,
> change the metadata string, because the current one contradicts what the
> product does with it every time the endpoint is called.
>
> Separately: decide whether the regulatory RAG is a product or dead code. It
> has been library-only across two audits. If it is meant to ship it needs an
> endpoint and an indexed corpus; if not, say so in the module docstring so the
> next audit does not re-derive this.

---

## B1 RESULT — SpectraCheck: uploaded files are readable by any authenticated user

**This is the most serious defect found in the whole validation programme, and
it is NOT fixed. Read this before anything else in Track B.**

### Probed live, with auth enforced

Two unrelated accounts. Owner uploads `owner_private.csv` via `POST /files/upload`
(201, file id 1). The **other** user then:

```
GET /files/1                -> 200      (record)
GET /files/1/download       -> 200      ppm,intensity 1.0,10 2.0,20
GET /files                  -> 200      1 file listed: "1_owner_private.csv"
```

The second user **downloaded the bytes**. For a product whose users upload
proprietary FIDs, that is one customer reading another customer's raw spectral
data — the single most confidential thing the system holds.

### Why it is not a route patch

```
managed_file_records columns:
  id, filename, original_filename, content_type, file_size_bytes, sha256,
  storage_backend, storage_key, file_kind, created_at, metadata_json
                                    *** no owner column ***
```

Same shape as the compound registry before migration 0039: nothing to scope
against. None of `list_file_records`, `get_file_record`, `get_file_download`,
`get_artifact_record` takes an owner parameter, because there is nothing to
pass.

### The fix, ready to execute

1. **Migration 0041** — `created_by_user_id` on `managed_file_records` and the
   artifact table, nullable + indexed, plus the `_ensure_sqlite_schema` arm.
   Follow `0039_registry_attributability.py` exactly; the reasoning about
   nullable-for-legacy and no-backfill applies unchanged.
2. **Stamp on create** — `upload_file_record` takes `created_by_user_id`.
3. **Scope on read** — `owner_scope_id` on all four readers; `None` keeps the
   unscoped view for the system key/admin, matching `list_signatures` and the
   action-item list.
4. **Non-leaking 404 on the by-id routes**, not 403. Unlike the compound
   registry — where a shared reference makes existence non-secret — an uploaded
   file's existence *is* confidential, so this follows the dossier pattern.
5. **Legacy NULL rows**: refuse to non-admins, as with 0039. A file uploaded
   before attribution existed has no provable owner, and "nobody is recorded"
   must not read as "anyone may download it".

### Why it was not fixed in this pass

The four routes live in `api.py`, which had uncommitted changes from a parallel
session at the time. `git commit -- api.py` commits the WORKTREE version, so
committing the fix would have swept that session's in-flight work into it.
Fixing only the store layer would have left the routes unwired — the
half-applied guard this codebase keeps producing, and the exact shape of the
`action-items` hole (`b049003`).

**Do this first, in a session with `api.py` uncontested.**

### The other five B1 obstacles — status

| # | claim | verdict |
|---|---|---|
| 1 | analyze steps do not return persisted ids | not re-probed this pass |
| 2 | no server-side report generation; `POST .../reports` stores a client payload | **stands** — and `spectracheck_store` prefers a client-supplied `report_sha256` over the server computation, so the integrity hash is client-authored too |
| 3 | no PDF export in the HTTP surface | not re-probed |
| 4 | managed files unscoped | **CONFIRMED, above** |
| 5 | `/reports/{id}` resolves two tables | not re-probed |
| 6 | 6 of 10 job types have no adapter | not re-probed |

Only #4 was probed live this pass; the rest are carried forward as claims, not
findings. Do not cite them as verified.

---

## A1 CORRECTION (2026-08-06) — the 21.1% figure was my measurement, not the pipeline

**"A1 RESULT, part 2" above is wrong where it says the processed path does not
recover true proton ratios. Read this instead.**

That section reported a median 21.1% error with small peaks under-reported to
-71.5%, over "well-isolated peaks". The comparison was against a **midpoint
partition of the trace computed by the test itself** — every point assigned to
its nearest reported peak. The pipeline does not integrate that way, so the
number measured the disagreement between two window methods and then attributed
it to the pipeline.

Re-measured on the identical run (same fixture, same 19 peaks, same 353 H),
comparing each peak's share of the reported proton total against its share of
the pipeline's **own fitted areas**:

```
median |error| = 1.7%     worst = 8.8%     within 10%: 14/14
```

**The area-to-proton scaling is faithful.** The apportionment work in `4099eb8`
and the reference fix in `b4014fc` did what they were supposed to.

### What the correction does NOT clear

Faithful scaling inherits whatever the areas are. Those come from raw
local-maximum cluster sums (`spectrum.py:1236`), and the pseudo-Voigt fit that
could correct them is computed and thrown away — that is A4, unchanged and still
real. A spectrum can pass the corrected test and still report wrong proton
counts if the integration windows are wrong.

So the open question moves: **it is about the windows and the discarded fit, not
about the scaling.** A4 measured fitted-vs-raw areas differing by up to 31% in
dense regions, which is the same disagreement my partition was picking up — I
just mislabelled its cause.

### The methodological lesson, stated plainly

The partition was a crude proxy for "true area" and it was **not a better
arbiter than the thing it was auditing**. When a measurement disagrees with the
system under test, the first question is which of the two is the better
instrument. I skipped that question because the result matched what I already
suspected.

This is the same failure as the three harness errors in A3, and it got further
because the output was plausible, size-ordered, and chemically narratable. It
was committed, written into a test as a pinned baseline, and reported as a
headline finding before anything caught it.

**What caught it:** running the diagnostic through `_estimates_to_peaks` while
looking for the *cause* of the error, and finding the stage-to-stage error was
0.0%. A defect with no mechanism is usually not a defect.

Corrected in `tests/test_processed_upload_accuracy.py`, which now measures the
scaling step against the pipeline's own areas and names the window question as
A4's rather than pretending to answer it.

---

## B1 LOOP RESULT — SpectraCheck end to end on a real FID (2026-08-06)

Driven on `naw-1-244-54pt/10` (the fully relaxed half of the matched pair),
auth enforced, as an ordinary non-admin user.

### The loop closes, and produces real artefacts

| step | route | result |
|---|---|---|
| upload | `POST /raw-fid/upload` | 200, Bruker detected, archive persisted |
| process | `POST /raw-fid/{id}/process` | 200 in 8.9 s, 20 peaks |
| run | `GET /fid/runs/{id}` | 200 |
| report | `GET /fid/runs/{id}/report` | 200 — structured: `inferred_peak_list`, `processing_assumptions`, `qa_diagnostics`, `raw_fid_provenance`, `review_decisions`, `run` |
| report (HTML) | `GET /fid/runs/{id}/report.html` | 200, **27 KB** |
| **review** | `POST /fid/runs/{id}/review` | **403** |
| package | `GET /fid/runs/{id}/package` | 200, **1.8 MB** evidence bundle |

**Report production works.** The acquisition gating also read the real file
correctly — `level=quantitative, recycle=30.0 s` — so the P2b work holds on
instrument data, not just fixtures.

### Finding 1 — scientific review is gated on the PLATFORM ADMIN role

```
POST /fid/runs/{id}/review           dependencies=[Depends(require_admin)]
POST /fid/runs/{id}/approve          require_admin
POST /fid/runs/{id}/reject           require_admin
POST /fid/runs/{id}/request-changes  require_admin
```

versus, on the sibling surface:

```
POST /spectracheck/sessions/{id}/review    require_access_context
```

This is not segregation of duties — that would be "a second qualified person",
not "an administrator". It conflates *can administer the system* with *is
qualified to approve an analysis*. In a lab the reviewer is a senior chemist,
not IT.

The consequence is a dead end: a chemist runs an analysis, gets a report, and
**cannot have it reviewed** unless a platform admin does it. Either every
reviewer is over-privileged or the review step does not happen.

Worse, the product already has the right model and does not use it here —
`session_reviewers` (reviewer_email, assigned_by, status), `review_tasks`
(assigned_to), `approval_records` (approver_email, decision, rationale). The FID
run path bypasses all of it.

The refusal is also uninformative: *"You do not have access to perform this
action."* A chemist reading that concludes the feature is broken, which — from
where they stand — it is.

### Finding 2 — a raw FID cannot be processed without a declared structure

`POST /raw-fid/{id}/process` has `smiles` in its **required** list; omitting it
is a 422. So "process my spectrum and show me what is in it" is not reachable —
every raw-FID analysis must begin with an asserted structure.

That is defensible for the verifier (it needs an expectation to compare against)
but it forecloses the QC workflow a chemist most often wants: *is this sample
clean, and does the integral pattern look right*, asked before committing to a
structure. Worth a deliberate decision rather than an implicit one.

### Corrected: the run id IS returned

Playbook obstacle #1 said analyze steps persist rows without returning their
ids. Partly wrong — `fid_run_id` comes back, nested under `preview` rather than
at the top level of the response. A client can chain without a list call; it
just has to know where to look.

**Next prompt:**

> Move FID-run review off `require_admin` and onto the reviewer model that
> already exists. A reviewer should be a second qualified user — assigned via
> `session_reviewers` / `review_tasks`, recorded in `approval_records` — not a
> platform administrator. Keep admin as an override, not the gate.
>
> While there, make the refusal say what is missing. "You do not have access to
> perform this action" on a review route should name the reviewer requirement.
>
> Then decide whether `smiles` must stay required on
> `POST /raw-fid/{id}/process`. If the verifier genuinely needs it, say so in
> the 422; if a structure-free QC pass is wanted, that is a product decision to
> take deliberately.

---

## B2 LOOP RESULT — Regentry end to end (2026-08-06)

Security phase was completed earlier (five holes closed or correctly
dispositioned). This is the loop: create → populate → assess → export.

### The loop closes

| step | result |
|---|---|
| create dossier | 201 |
| action item on it | 201 |
| **read it back** | 200, visible to the owner |
| readiness-report | 200 |
| impurity-risk-register | 200 |
| batch-assessment | 200 |
| nitrosamine-cumulative-risk | 200 |
| submission-package | 201 |
| ctd-module3-bundle | 201 |

The "action items created 201 then permanently invisible to their creator"
defect from the 2026-07-26 audit is **fixed** — the item came back on
`GET /regulatory/action-items?dossier_id=…` immediately.

### The export is a manifest of references, and that part is done well

`POST /regulatory/dossiers/{id}/submission-package` does not bundle bytes. It
writes a JSON manifest listing each included file with its **own** sha256, size
and original filename, plus a package-level `package_sha256`. Verified with a
real uploaded file: the manifest carried
`{"file_id": 2, "file_size_bytes": 27, "original_filename": "coa_evidence.csv",
"sha256": "7b374da5…"}`.

That is defensible provenance — a reviewer can verify each referenced artefact
independently. It carries an honest `language_notice`: *"Export package is for
review and does not assert legal approval or guaranteed compliance."* Consistent
with the "designed to support" framing.

**The caller chooses the contents.** `create_submission_package` iterates
`payload.file_ids_json` / `artifact_ids_json`; the endpoint does not discover the
dossier's own evidence. Reasonable for a curated submission — but see below.

### Finding — an EMPTY package is produced, hashed, and marked ready

```
POST .../submission-package  {}          -> 201
  file_ids_json:     []
  artifact_ids_json: []
  status:            "ready_for_review"
  warnings:          []
  package_sha256:    "882564c4e0594a58cb931549200b2cb1dae087964e90b1ce2f68250daad5c0ce"
```

A submission package containing **nothing** comes back marked ready for review,
with a valid-looking SHA-256 over an empty manifest and no warning.

The asymmetry is the tell. Reference a file that does not exist and the manifest
**does** warn:

```
POST .../submission-package  {"file_ids_json":[999999]}   -> 201
  warnings: ['File 999999 was not found for the export package manifest.']
```

So the emptiness check is half applied: absent-referent is caught, absent-
reference is not. And the empty case is the more dangerous of the two, because
it looks complete — a status of `ready_for_review`, a real digest, an empty
warnings array. A reviewer glancing at it has nothing to alert them.

A caller that simply forgets `file_ids_json` — an FE bug, a mis-shaped request —
gets a regulatory submission package with no evidence and no complaint.

**Next prompt:**

> Warn on an empty submission package, and do not let it reach
> `ready_for_review`. The machinery is already there: the manifest's `warnings`
> array is populated for a missing referent, so the same path should say when
> nothing was referenced at all. `status` should reflect it — `draft` or
> `empty`, not `ready_for_review`.
>
> Then decide whether the endpoint should DISCOVER the dossier's evidence rather
> than requiring the caller to enumerate it. Curated selection is defensible, but
> today nothing connects a dossier's own action items, assessments and linked
> reports to its export, so "everything relevant" is the caller's problem to get
> right and the server never checks.
>
> Not probed this pass: whether the CTD module-3 bundle has the same empty-case
> behaviour (it returned 201 on a near-empty dossier and its fields were all
> null), and whether `package_sha256` is stable across re-creation.
