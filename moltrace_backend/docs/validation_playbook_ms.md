# Validation playbook — the MS evidence layer (phase D)

Runs **after** phase C (2D NMR). Companion to `validation_playbook.md` (1D NMR,
product loops) and `validation_playbook_2d_nmr.md`. Same rules, same gates.

MS differs from NMR in one way that shapes every phase below: **a mass is not a
structure.** An exact mass constrains a formula, a formula constrains a candidate
set, and fragments constrain it further — but nothing in this layer identifies a
compound on its own. Every phase has to keep that distinction visible, because
the failure mode here is a confident identification the evidence cannot support.

---

## What is already here (surveyed 2026-08-09, verify before trusting)

**23 routes**, each analysis route paired with an `/evidence` variant and often an
`/upload` variant:

```
/ms/hrms/formulas/search              /ms/hrms/candidates/match
/ms/adducts/infer
/ms/lcms/features/detect              /ms/lcms/features/group
/ms/lcms/features/consensus           /ms/lcms/dereplication
/ms/lcms/import/bridge
/ms/msms/annotate                     /ms/msms/fragmentation-tree
```

**Modules:** `moltrace/spectroscopy/ai/ms_models.py` (511), plus `lcms_grouping.py`
and the HRMS paths in `api.py`.

**Existing tests:** `test_ai_ms_models.py`, `test_ms_evidence_studio_contract.py`,
`test_week29_hrms_api.py`, `test_week29_hrms_exact_mass.py`, `test_week29_hrms_ui.py`.

### The finding that has to lead this phase

**CSI:FingerID / SIRIUS is not implemented.** Both backends in
`ms_models.py` raise:

```python
def _sirius_rest_backend(url: str) -> CSIBackend:
    raise CSIFingerIDUnavailable(
        "SIRIUS REST integration is configured but not implemented in this build; ...")

def _sirius_cli_backend(binary: str) -> CSIBackend:
    raise CSIFingerIDUnavailable(
        "SIRIUS CLI integration is configured but not implemented in this build; ...")
```

So `predict_msms_candidates` **cannot turn an MS/MS spectrum into structures**
unless a caller injects its own `backend=` callable. It fails honestly rather
than fabricating — which is the right design — but the build spec names
"MS/MS → structure via CSI:FingerID" as a **differentiator**, and
`fuse_candidates` is documented as combining NMR + MS/MS + RT. Checked
2026-08-09: the whitepapers do **not** currently claim it works. Keep it that
way until D7 changes the answer.

---

## D0. Stage real MS fixtures and establish ground truth

> **Prompt.** Stage real MS data into `validation_fixtures/ms/` (gitignored).
> Prefer open formats (mzML/mzXML) over vendor blobs. For each, record:
> ionisation mode and polarity, mass analyser and its nominal resolving power,
> whether it is MS1 or MS/MS, collision energy and type (CID/HCD) for MS/MS,
> calibration state, and the LC method if present.
>
> Ground truth here is **the known compound and its formula**, from the same
> samples whose structures are already established for the NMR fixtures — that
> reuse is the point, because it is what lets D10 test fusion honestly.
>
> Record the instrument's **measured** mass accuracy on a known ion, in ppm. Do
> not take it from the datasheet. Every tolerance downstream must derive from
> this measurement, and a datasheet figure is a manufacturer's best case.

**Gate:** no phase past D2 starts until measured mass accuracy exists, because
every tolerance below is derived from it.

---

## D1. Establish what is real across all 23 routes

> **Prompt.** As C1, and as A5 before it. For each route, POST a real fixture and
> record: does it compute, does it echo, or does it stub? Specifically settle:
>
> 1. **Which routes have a real algorithm** behind them versus an adapter shell.
>    `ms_models.py` carries two explicit "not implemented in this build" raises —
>    find whether there are others, in any MS module, and list them.
> 2. **What `/evidence` variants add.** 10 analysis routes each have one. If the
>    evidence variant returns the same numbers with a wrapper, say so; if it adds
>    provenance and citations, verify those are computed rather than echoed
>    (the "AI numbers must be computed" rule — 76 routes once recorded
>    caller-supplied confidences).
> 3. **Owner scoping.** Probe every route that stores or reads a record
>    cross-user, with `API_KEY` set and a valid body. A 422 is a bad shape, not a
>    denial; a 405 is the wrong verb, not a refusal. Enumerate write routes from
>    the OpenAPI document rather than guessing.
> 4. **Whether any MS result can change a verdict**, or whether the layer is
>    parallel decoration. Grep the consumers into the unified confidence engine.
>
> Deliverable: a "D1 RESULT" table — route, real/shell, scoped y/n, reaches
> verdict y/n — in this file.

---

## D2. Exact mass and formula assignment

> **Prompt.** This is the foundation and it is arithmetic, so it can be checked
> exactly.
>
> * **Monoisotopic, not average.** Confirm the code uses monoisotopic masses
>   throughout. Average mass is right for a bulk property and wrong for a peak;
>   mixing them is a classic and quiet error.
> * **The electron mass.** For `[M+H]+` the ion mass is M + 1.007276 (proton),
>   not M + 1.008 (hydrogen atom). At 5 ppm on m/z 300 the window is ±0.0015 —
>   the electron mass (0.000549) is a third of it. Assert this against a
>   hand-computed value.
> * **Tolerance from measurement.** The ppm window comes from D0's measured
>   accuracy, not from a round 5 ppm. State how it was derived.
> * **Report the candidate count, always.** A formula search returning one hit at
>   ±1 ppm and forty at ±10 ppm is the same measurement; only the window differs.
>   Emitting the top hit without the count of alternatives is the coverage defect
>   found in DP4, in a new place.
> * **Chemical plausibility filters** (RDBE / rings-plus-double-bonds, valence,
>   the Seven Golden Rules heuristics) reduce the set. If applied, they must be
>   named in the output and their effect on the count reported — a filter that
>   silently removes the true answer is worse than a long list.

---

## D3. Isotope patterns — the constraint most likely to be under-used

> **Prompt.** Isotope distribution is strong, cheap evidence and is frequently
> reduced to a checkbox.
>
> * Verify the predicted pattern against the measured one with a real similarity
>   metric, and report it. Cl and Br are near-diagnostic (M+2 at ~32 % and ~97 %);
>   S is visible; a single C13 peak ratio constrains carbon count directly.
> * The **carbon count from the M+1 ratio** is a genuinely independent constraint
>   on the formula. Confirm whether it is used; if not, that is a real gap worth
>   naming with its measured value on the fixtures.
> * Isotope intensity is unreliable when the peak is saturated or near the noise
>   floor. Gate on that, and say when the gate fires — do not silently score a
>   saturated pattern.

---

## D4. Adducts — where a confident wrong answer comes from

> **Prompt.** `/ms/adducts/infer` exists. Adduct misassignment produces a
> perfectly self-consistent, completely wrong formula.
>
> * Cover at minimum `[M+H]+`, `[M+Na]+`, `[M+K]+`, `[M+NH4]+`, `[M-H]-`,
>   `[M+Cl]-`, dimers `[2M+H]+`, and multiply-charged `[M+2H]2+`.
> * **Charge state must be inferred from isotope spacing** (1/z Da), not assumed
>   to be 1. Assert this; a 2+ ion read as 1+ doubles the apparent mass.
> * Report adduct assignment as a **ranked set with its evidence**, never as a
>   single decided fact — the same rule the DP4 ranking now follows.
> * Test the ambiguous case deliberately: `[M+Na]+` and `[M+H]+` of two different
>   compounds can land within tolerance of each other. The output must show both.

---

## D5. LC-MS feature detection and grouping

> **Prompt.** Five routes cover detect / group / consensus / dereplication /
> import-bridge. Validate against the D0 fixtures:
>
> * **Detection is not quantitation.** Never let an intensity-scaling rule decide
>   whether a feature *exists* — that error has already been made once in this
>   codebase and is recorded in the 1D playbook.
> * **Report the denominator** on every recovery figure: features found out of
>   features present, not just the count found.
> * **Grouping** must not merge co-eluting isomers into one feature. Measure how
>   often it does on the fixtures.
* **RT alignment across runs** — if implemented, measure the residual after
  alignment; if not, say so.
> * **Dereplication** matches features against a library: see D8 for the licence
>   gate before any library lands.

---

## D6. MS/MS fragmentation

> **Prompt.** Fragment interpretation is where over-claiming is easiest.
>
> * A fragment formula must be a **subformula of the precursor**. Assert it —
>   this single constraint removes most nonsense assignments.
> * Account for **hydrogen rearrangement** explicitly. Fragment masses routinely
>   differ from naive bond cleavage by ±1–2 H, and a scorer that ignores this
>   will reject correct assignments (a confident false rejection, the direction
>   that matters most).
> * A **fragmentation tree** is a hypothesis, not an observation. Report how many
>   trees are consistent with the data, not only the best-scoring one.
> * Collision energy changes the spectrum substantially. A library match at a
>   different CE than the query is weaker evidence; record the CE of both.

---

## D7. CSI:FingerID / SIRIUS — decide, then either wire or withdraw

> **Prompt.** Currently unimplemented (see above). Three honest options — pick one
> in writing:
>
> 1. **Wire it properly.** SIRIUS is external, GPL-licensed, JVM-based and heavy.
>    Determine deployment shape (the API scales to zero; SIRIUS does not fit that
>    model), licence compatibility with BUSL 1.1 for *distribution* versus
>    *calling a service*, and cost. Calling a separately-installed binary is a
>    different licence question from bundling it — get that answered before
>    building.
> 2. **Wire a lighter alternative** and name it accurately rather than calling it
>    CSI:FingerID.
> 3. **Withdraw the claim** from the build spec and keep the honest
>    `CSIFingerIDUnavailable` failure.
>
> Whichever is chosen: **verify no public copy claims it works** before shipping
> anything. Checked 2026-08-09 — the whitepapers are clean; the build spec is not.
> Public copy is verified against backend source, never against other copy.

---

## D8. Spectral libraries — licence gate before any corpus lands

> **Prompt.** The build spec names **MassBank EU** and **GNPS**. Read and record
> each licence *before* ingesting anything, exactly as NMRShiftDB2's CC-BY-SA
> forced the `_REDISTRIBUTABLE_LICENCES` gate.
>
> * MassBank records carry per-record licences that are **not uniform** — some are
>   CC-BY, some CC-BY-NC, some more restrictive. A blanket ingest is a blanket
>   assumption. The gate must be per record, and it must fail closed.
> * Distinguish **grounding** from **redistribution**, as the RAG work already
>   does: using a library to score a match is internal processing; returning the
>   library record to a caller is distribution.
> * Non-commercial clauses matter here specifically, because production use of
>   MolTrace requires a commercial licence.
>
> Deliverable: a per-source licence table in this file, and a redistribution gate
> with a test that a non-redistributable record's structure is withheld while its
> similarity, rank and citation id still reach the caller.

---

## D9. Retention time as orthogonal corroboration

> **Prompt.** RT is genuinely independent of mass, which makes it valuable — and
> it is method-dependent, which makes it fragile.
>
> * An RT predictor trained on one LC method does not transfer to another.
>   Establish whether the code knows which method a prediction is valid for, and
>   refuse rather than guess when it does not match.
> * RT must **down-weight, never hard-filter** a candidate. This is already the
>   stated design in the build spec — verify it in code and pin it with a test.
> * Report the predictor's measured error on the fixtures, with n.

---

## D10. Fusion — the phase that justifies the whole layer

> **Prompt.** `fuse_candidates` combines NMR (DP4) + MS/MS + RT. This is the
> stated differentiator, so it gets the most scrutiny.
>
> * **The deterministic verifier remains the sole arbiter.** Fusion may reorder
>   within a verdict class; it may not overturn one. Assert it.
> * **Weights come from measured per-modality accuracy**, not from
>   judgement. If a weight is a round number, it is a guess — say so or derive it.
> * **A fused score is not a probability.** Same rule the DP4 ranking now follows:
>   `probability_is_calibrated: False` and a basis string, unless and until it is
>   calibrated against held-out truth.
* **Missing modalities must not be imputed.** A candidate with no MS/MS evidence
  scores on what exists, with coverage reported; silently substituting a prior
  makes absence look like agreement.
> * **Measure the actual lift.** Run the fixtures with NMR alone, MS alone, and
>   fused. If fusion does not beat the better single modality at a matched
>   operating point, that is the finding — report it rather than shipping the
>   architecture. Compare at matched operating points, not one method's best
>   against another's worst.

---

## D11. Product loop, report, and handoff

> **Prompt.** Mirror B1 and C9. Upload real MS data through the UI, run the
> analysis, produce the report, note every obstacle in order. Verify owner
> scoping end to end, `human_review_required` on any regulated output, no backend
> jargon in user-visible copy, and every figure carrying its uncertainty and
> coverage. Then write the FE handoff as a numbered checklist, marking which
> items are permanent FE work.

---

## Cross-cutting rules for this phase

* **A mass is not a structure.** No route may present an identification the
  evidence cannot support. Rank, with coverage, and name what would discriminate.
* **Every tolerance derives from D0's measured accuracy**, and says so.
* **Every count ships its denominator** — candidates considered, features present,
  library records searched.
* **Licences are read before ingest, per record, failing closed.**
* **Public copy is verified against backend source.** CSI:FingerID is the live
  example: specified, documented in a module docstring, and not implemented.
* **Compliance language stays "designed to support"; SOC 2 is not held.**
* **New routes get owner scoping and a non-leaking 404**, probed with a valid body.
