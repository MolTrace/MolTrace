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
