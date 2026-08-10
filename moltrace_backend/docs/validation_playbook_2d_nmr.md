# Validation playbook — the 2D NMR layer (phase C)

Companion to `validation_playbook.md`, which covers 1D NMR (phase A) and the
product loops (phase B). Same rules, same gates, same standard of evidence.

**Read `validation_playbook.md` "Ground rules" first.** The ones that keep biting:
measure before you build, a defect with no mechanism usually is not one, an error
statistic must ship its coverage, bounds come from the data distribution and not
from round numbers, and a test asserting current behaviour may be encoding the bug.

---

## What is already here (surveyed 2026-08-09, verify before trusting)

**Routes (7):**

```
POST /nmr2d/analyze          POST /nmr2d/preview        POST /nmr2d/raw/preview
GET  /nmr2d/status           GET  /nmr2d/runs/{id}      GET  /nmr2d/runs/{id}/report
POST /nmr2d/runs/{id}/review
```

**Modules:** `nmr2d.py`, `nmr2d_analyzer.py` (624), `nmr2d_parser.py` (532),
`nmr2d_models.py` (246), `nmr2d_routes.py` (276).

**Experiment types (`NMR2DExperimentType`):** `COSY`, `HSQC`, `HMQC`, `HMBC`,
`UNKNOWN`. **No NOESY, ROESY or TOCSY** — see C7.

**Existing tests:** `test_week23_nmr2d.py`, `test_week25_nmr2d_api.py`,
`test_week25_nmr2d_parser.py`, `test_week25_nmr2d_evidence.py`,
`test_week25_nmr2d_report.py`, `test_week25_2d_nmr_evidence_engine.py`,
`test_week25_1_dept_2d_ui_placement.py`.

**Build spec (`MolTrace-Spectroscopy-Build-Spec-v2.2.docx`) claims that are NOT
obviously in the code — treat each as a claim to test, not a feature to assume:**

* *Method 7: HSQC 2D verification with rectangular prediction boxes.*
  `nmr2d_analyzer.py` exposes no `verify`/`predict`/`expect`/`assign` function —
  only `_match_score`. **C1 must settle whether 2D verification exists at all.**
* *Method 2: TransPeakNet, solvent-aware 2D HSQC prediction (GNN, transfer +
  unsupervised learning).*
* *2DNMRGym (~22k annotated HSQC spectra)* as a training/eval corpus.
* *Similarity concatenated across 1H, 13C, HSQC, HMBC, COSY.*

---

## C0. Stage real 2D fixtures and establish ground truth

Phase A only worked because exp 10 of a matched pair was independently
quantitative and could therefore *be* the truth. 2D needs its own equivalent, and
2D truth is different: it is **connectivity**, not intensity.

> **Prompt.** Stage real 2D datasets from `~/My Business /NMR Test Samples` into
> `validation_fixtures/nmr2d/` (gitignored — the repo is public and these are
> real customer spectra). For each, record in an inventory: experiment type from
> the pulse program (not the folder name), both nuclei, both sweep widths, TD in
> each dimension, number of increments, whether the data is magnitude or phase
> sensitive, and whether processed `2rr` exists alongside the raw `ser`.
>
> Ground truth is **the assigned structure and its expected correlations**, not a
> peak list. For at least one compound, write the expected HSQC one-bond H–C
> pairs and the expected 2–3 bond HMBC correlations out by hand from the
> structure, and record who derived them and from what. A correlation list
> derived from the software under test is not ground truth — that is the circular
> trap the A1 retraction came from.
>
> Deliverable: `validation_fixtures/nmr2d/inventory.json` plus a short note in
> this file naming which compound has hand-derived correlations, and what the
> hand derivation assumed (for example whether 2-bond H–C HMBC correlations were
> counted, which vary in intensity and are often absent).

**Gate:** do not start C2 until at least one fixture has a hand-derived expected
correlation list. Everything downstream is scored against it.

---

## C1. Establish what the 2D layer actually does

Modelled on A5 (DP4), which found the method implemented correctly but fed the
wrong inputs. Assume nothing from the route names.

> **Prompt.** For each of the 7 routes, POST a real fixture and record the
> response shape. Then answer, in writing, with file:line evidence:
>
> 1. Does anything **verify a 2D spectrum against a candidate structure**, or
>    does the layer only parse, peak-pick and score internal consistency?
>    `_match_score(matches, possible, fallback)` suggests the latter. If there is
>    no structure-aware path, say so plainly — the build spec's "Method 7: HSQC
>    verification with rectangular prediction boxes" would then be **specified,
>    not shipped**, and every downstream phase depends on knowing which.
> 2. Where do `possible` and `matches` come from? If `possible` is derived from
>    the observed peaks rather than from the structure, the score is
>    self-referential and cannot fail — the same shape as the DP4 coverage
>    defect, where an error statistic computed over survivors stopped responding
>    to error.
> 3. Does the 2D result reach the unified confidence engine, and can it change a
>    verdict? Grep the consumers. If it cannot, the layer is decoration however
>    good its parsing is.
> 4. Does `/nmr2d/runs/{id}` apply owner scoping and a non-leaking 404? Probe
>    cross-user with `API_KEY` set — with it unset auth is not enforced and the
>    probe proves nothing.
>
> Deliverable: a "C1 RESULT" section here stating, for each of the four, what is
> real, with the evidence. Correct the build spec's claims in the same pass if
> they overstate.

---

## C2. Parser fidelity — the 2D dimensions are where silent errors live

> **Prompt.** 2D parsing has failure modes 1D does not. For each staged fixture,
> verify against the acquisition parameters rather than against the parser's own
> output:
>
> * **Axis assignment.** F2 is normally the directly-detected dimension (usually
>   1H) and F1 the indirect one. A transposed spectrum still parses and still
>   looks plausible — every correlation is simply mirrored. Assert the parsed F1
>   nucleus matches `##$NUC1`/`NUC2` from `acqu`/`acqu2s`, not a guess from the
>   ppm range.
> * **Referencing per dimension.** Each axis has its own SF/SR. An off-referenced
>   F1 shifts every carbon correlation by a constant; that is invisible without a
>   reference. Check against a known peak.
> * **Magnitude vs phase-sensitive.** The spec notes `'magnitude': for 2D HMBC`.
>   Confirm the parser knows which it has; taking the magnitude of a
>   phase-sensitive spectrum destroys sign information that DEPT-edited HSQC
>   depends on.
> * **Folding / aliasing.** A peak outside the F1 sweep width folds back and
>   appears at a real-looking but wrong shift. Check whether the parser can
>   detect this, and if it cannot, say so — it is a correctness limit worth
>   stating, not hiding.
>
> Write the invariant tests first; each must fail against a deliberately
> transposed, mis-referenced or folded fixture before the fix lands.

---

## C3. Peak picking in two dimensions — artifacts are not signal

> **Prompt.** A 2D peak picker that reports artifacts as correlations will
> produce confident nonsense downstream, and the connectivity layer has no way to
> tell. Measure, on real fixtures, how the picker handles:
>
> * **t1 noise** — vertical streaks through strong F2 signals, the dominant 2D
>   artifact. These are not peaks and must not become correlations.
> * **Ridges / streaks** from incomplete relaxation or truncation.
> * **Solvent and residual-water columns.**
> * **Symmetry.** COSY is symmetric about the diagonal; HSQC is not. Symmetrising
>   suppresses noise but *manufactures* peaks where two artifacts coincide.
>   Determine whether the code symmetrises and, if so, whether it says it did.
>
> Report the count of picked peaks against hand-counted true correlations, with
> the **denominator** — the A-phase lesson: the peak detector over-picked 3–7x on
> 1D and that was only visible because the true count was known.
>
> **Bound rule:** any intensity threshold must come from the measured noise
> distribution of that spectrum, not a constant. Record how it was derived.

---

## C4. HSQC verification against a structure (the spec's Method 7)

Only start once C1 has established whether this exists.

> **Prompt.** Build or validate one-bond H–C verification:
>
> 1. From a candidate structure, predict the expected H–C pairs (each protonated
>    carbon gives one correlation; a diastereotopic CH2 can give two).
> 2. Score observed against expected with a **rectangular tolerance** — separate
>    windows in F2 (1H, tight, ~0.05–0.1 ppm) and F1 (13C, loose, several ppm).
>    A single circular tolerance is wrong because the two axes have completely
>    different precision, and using one number for both is the "same ruler for
>    every atom" mistake already corrected in the 1D verifier.
> 3. **Derive both tolerances from the measured residual distribution** of the
>    shift predictor on held-out data, per axis. Do not pick round numbers. If
>    the predictor's per-axis error is not measured, measure it first.
> 4. Report **coverage**: how many expected correlations were found, out of how
>    many expected. An HSQC "match score" without that denominator is the DP4
>    defect again.
> 5. A missing correlation is evidence, not absence of evidence — quaternary
>    carbons have none by construction and must be excluded from the denominator,
>    not counted as misses.
>
> Invariant test first: a correct structure scores high, a regioisomer with the
> same formula scores measurably lower, and a structure whose CH count differs is
> caught by coverage rather than by score.

---

## C5. HMBC — the ambiguity is the feature, and it must be reported

> **Prompt.** HMBC shows 2–3 bond H–C correlations, sometimes 4 through
> conjugation, and 2-bond correlations are frequently weak or absent. That makes
> it powerful for connectivity and dangerous for automated scoring.
>
> * Never treat an absent HMBC correlation as refutation. Its absence is
>   uninformative; only presence is evidence. Assert this in a test — it is the
>   single most likely way an automated HMBC scorer produces a confident false
>   rejection, which is the direction that matters (the same asymmetry found in
>   the DP4 heavy-tail analysis).
> * A single HMBC correlation is usually consistent with several structures.
>   Report how many candidate structures each correlation set is consistent with,
>   not just the best one.
* Record the `n`-bond assumption per correlation. A correlation counted as 3-bond
  under one interpretation and 2-bond under another supports different skeletons.
>
> Deliverable: a measured statement of how much HMBC narrows the candidate set on
> the staged fixtures — the same "what did this actually buy" question the
> HMBC/regioisomer work already answered for 13C shifts.

---

## C6. COSY and the diagonal

> **Prompt.** COSY correlates coupled protons. Two specific hazards:
>
> * **Diagonal peaks are not correlations.** Every signal appears on the
>   diagonal by construction. If diagonal peaks reach the connectivity graph, the
>   layer will "confirm" that every proton couples to itself.
> * **Symmetry.** Cross peaks appear in mirrored pairs; counting both doubles the
>   evidence for one coupling. Confirm each coupling is counted once and assert
>   it.
>
> Measure how many true H–H couplings COSY recovers on the staged fixtures
> against the hand-derived list, with the denominator.

---

## C7. The missing experiments — decide deliberately, in writing

`NMR2DExperimentType` has COSY, HSQC, HMQC, HMBC. It has **no NOESY, ROESY or
TOCSY**.

> **Prompt.** This is a scope decision, not an oversight to quietly fix. Write
> the decision down with its reasoning:
>
> * **NOESY/ROESY are through-space.** They are how relative stereochemistry and
>   conformation are actually established. Without them the platform can verify a
>   constitution but cannot address stereochemistry from 2D at all — which
>   matters because DP4's original purpose (Smith & Goodman 2010) was
>   *diastereomer* assignment. State plainly whether stereochemistry is in scope.
* **TOCSY** propagates through a whole spin system and is how sugar rings and
  amino-acid side chains get assigned — directly relevant to the carbohydrate
  work already in the codebase.
>
> If they are added, `UNKNOWN` must not silently absorb them: a NOESY parsed as
> `UNKNOWN` and scored with through-bond logic would produce confident nonsense,
> because a through-space correlation between two protons implies nothing about
> bonding. Add a test that an unrecognised pulse program is refused with a message
> naming it, rather than defaulted.

---

## C8. Does 2D change a verdict? (the "so what" phase)

> **Prompt.** The B-phase equivalent of "is this decoration". Take the staged
> fixtures and run the unified confidence engine **with and without** the 2D
> layer contributing.
>
> * Does any candidate ranking change? By how much?
> * Does 2D ever *overturn* a 1D-only conclusion, or only agree with it?
> * On the regioisomer pairs 13C shifts get wrong, does HSQC/HMBC separate them?
>   (The HMBC-vs-13C work reports 99 % separation — verify that figure holds on
>   these fixtures and at what operating point, and compare at *matched*
>   operating points, not one method's best against the other's worst.)
>
> If 2D changes nothing, that is the finding, and it is more valuable than a
> feature. Report it.

---

## C9. Product loop and report

> **Prompt.** Mirror B1. Upload a real 2D dataset through the UI as a user would,
> run the analysis, produce the report, and note every obstacle in order. Verify:
> the review route enforces separation of duties as the FID one now does; the
> report carries provenance and the `human_review_required` flag; no backend
> jargon reaches user-visible copy; and any figure quoted carries its uncertainty
> and coverage. Then write the FE handoff as a numbered checklist — directory,
> regeneration command, contract delta by name, shapes, verification — and say
> explicitly which items are permanent FE work rather than stopgaps.

---

## Cross-cutting rules for this phase

* **Licence check before any corpus lands.** 2DNMRGym, and any HSQC training set,
  must have their terms read and recorded before use, exactly as NMRShiftDB2's
  CC-BY-SA forced the redistribution gate. Grounding is not redistribution;
  shipping the records is. Fail closed.
* **No claim in public copy without a `git grep` to backend source.** TransPeakNet
  and CSI:FingerID appear in the build spec; verify what is *wired* before either
  appears on a marketing page.
* **Any new route** gets an owner-scope check and a non-leaking 404, probed with a
  valid body under `API_KEY`.
* **Compliance language stays "designed to support".**
* **Every accuracy figure ships with n and its denominator.**

---

## C1 RESULT — 2D scores its own peak list, not the structure (2026-08-09)

**The spec's "Method 7: HSQC verification with rectangular prediction boxes" is
specified, not shipped.** There is a structure-aware path, but it does not do
what verification means.

### 1. Is there structure verification? No.

`analyze_nmr2d_preview` accepts `smiles`, so a structure-aware path exists. What
it does with it (`nmr2d_analyzer.py:63`):

```python
def _proton_references(proton_nmr_text, *, smiles, solvent):
    if not proton_nmr_text or not proton_nmr_text.strip():
        return [], None, []          # <- SMILES never consulted
    if smiles:
        report = analyze_proton_evidence(smiles=..., nmr_text=..., solvent=...)
        return [_ReferencePeak(shift_ppm=..., region=...) ...]
```

Two consequences:

* **Without 1D text the structure is ignored entirely** — the early return fires
  before `smiles` is read. A 2D spectrum plus a SMILES yields no references at all.
* When it is used, it produces a **1D shift list**, not predicted H–C correlation
  pairs. So the layer asks "does this cross peak sit near a known 1D shift",
  never "does this molecule predict this correlation".

### 2. Where do `matches` and `possible` come from? The observed peaks.

`dimension_possible` is incremented **per observed peak** (`:256`, `:290`):

```python
if experiment == "COSY":
    dimension_possible += 2 if proton_refs else 1
elif experiment in {"HSQC", "HMQC"}:
    dimension_possible += (1 if proton_refs else 0) + (1 if carbon_refs else 0)
```

The denominator is what was *found*, never what was *expected*. This is the
self-referential shape predicted in the C1 prompt, and the same defect class as
the DP4 coverage bug: an error statistic computed over survivors stops responding
to error.

### 3. Measured: showing LESS of the molecule scores BETTER

Ibuprofen has 7 protonated carbons, so ~7 one-bond HSQC correlations. Same
structure, same 1D text, varying only how many correlations are observed:

```
observed                     evidence_score   matched   missing_reference_count
all 7 correlations                  0.8047          7                         0
only 2 of 7 (5 MISSING)             0.8218          2                         0
only 1 of 7 (6 MISSING)             0.6552          1                         0
```

**Withholding five of seven correlations produced a higher score than showing all
seven** (0.8218 vs 0.8047). The score is not merely insensitive to missing
correlations — it is non-monotonic in completeness.

And `missing_reference_count` — a field named for exactly this — **reports 0 in
every case**, including when six of seven are absent. The concept is present in
the output shape; nothing computes it against a structure.

For an HSQC this is the load-bearing failure: a quaternary carbon legitimately
has no correlation, but a *protonated* carbon with none is evidence against the
structure, and that evidence is currently unreachable.

### 4. Reach and scoping

* **Reaches the analysis path** — `api.py:28627` calls `analyze_nmr2d_preview`
  after `parse_nmr2d_upload`. Whether the score can change a *verdict* rather
  than ride alongside one is still open; C8 settles it.
* **Owner scoping is correct.** `nmr2d_routes.py:219` derives `user_id` from the
  context (None for the system key), passes it to `get_nmr2d_run_by_id`, and
  returns a non-leaking `404 "2D NMR run not found."`. No action needed.

### What C4 must therefore build, not validate

C4 was written as "build or validate". It is **build**:

1. Predict expected H–C pairs from the structure — one per protonated carbon,
   two for diastereotopic CH2.
2. Make `possible` the count of *expected* correlations, so the denominator stops
   depending on what was found.
3. Populate `missing_reference_count` from that comparison, excluding quaternary
   carbons from the denominator rather than counting them as misses.
4. Only then add the rectangular per-axis tolerance, derived from the measured
   per-axis residual distribution.

Until (2) lands, no 2D score should be presented as evidence for a structure, and
any figure quoted from it needs the caveat that its denominator is the observed
peak count. Worth checking whether public copy already quotes one.

### C1 addendum — the score is weighted most where it is least validated

Traced after the finding above, because a score that cannot fail only matters if
something consumes it. It does.

`candidate.py:101` takes **the exact field probed above**:

```python
global_2d_score = nmr2d_result.evidence_score if nmr2d_result else None
```

and feeds it into candidate comparison with base weight **0.14**
(`candidate.py:115`), which is then multiplied by the per-class prior
(`apply_compound_class_weights`, `candidate.py:117`).

The `nmr2d` multipliers in `compound_class_priors.py`:

| class | nmr2d multiplier | the comment in the table |
|---|---|---|
| carbohydrates | **1.50** | "Anomeric 1H + 13C are uniquely diagnostic; HSQC near-mandatory" |
| flavonoids | 1.40 | "2D for ring linkages and sugar attach" |
| glycoproteins | 1.40 | "2D primary evidence" |
| alkaloids | 1.30 | "2D resolves N-adjacent stereochemistry" |

**The chemistry is right and that is the problem.** HSQC genuinely is
near-mandatory for carbohydrates (Duus et al. 2000, cited in the technical
whitepaper) — the weighting reflects real practice. But the quantity being
up-weighted is a score whose denominator is the observed peak count, which the
measurement above shows can rise when correlations go missing. So the component
carrying the most weight on carbohydrates, flavonoids, glycoproteins and
alkaloids is the one that cannot currently detect the failure it exists to catch.

Carbohydrates are also the class this codebase has invested the most 1D work in
(anomeric caps, benzylidene acetals, the aminoglycoside paths), which makes it
the most likely place for a confident 2D-driven wrong answer to be believed.

**This raises C4 from "next phase" to the blocking one.** Until `possible` counts
expected correlations, the honest options are (a) fix the denominator, or (b)
drop the `nmr2d` weight to 0 for the up-weighted classes and say why. Do not
leave a 1.5x multiplier on a score that rewards incompleteness.

Not yet checked: whether `unified_confidence.py` applies the same priors — the
multipliers do not appear in that module, so its 2D handling is a separate
question and should not be assumed to share this defect.

---

## C4 RESULT — the denominator is structural now (2026-08-09)

### The tolerance question answered itself, and changed the design

C4 called for a rectangular per-axis tolerance derived from the predictor's
measured residual distribution. That measurement was done first, using the fitted
error model from `fit_error_model` (1H scale 0.162 / ν 1.23; 13C scale 1.665 /
ν 1.24 — heavy-tailed):

```
        90 % of predictions within      95 %
  1H          ± 0.752 ppm            ± 1.339 ppm
  13C         ± 7.650 ppm            ± 13.560 ppm
```

**A window holding 90 % of this predictor's 1H predictions is ±0.75 ppm** — most
of the aliphatic region. Matching observed peaks against *predicted* shifts
cannot work at this accuracy: the window needed to avoid false misses is wide
enough to match almost anything.

So the structure is used only for the **count** of distinct H–C environments,
which comes from graph symmetry and is exact chemistry rather than a prediction.
Matching stays where it already was — observed 2D peaks against *observed* 1D
shifts, which are measured. The denominator becomes real without inheriting the
predictor's inaccuracy. Tolerance-based per-correlation matching is deferred
until a predictor exists that can support it (the spec's TransPeakNet is the
candidate).

### Measured, on the same probe C1 used

```
observed          evidence_score          missing_reference_count
                 before    after          before   after
all 7             0.8047   0.8047            0        0
2 of 7 (5 gone)   0.8218   0.2348            0        5
1 of 7 (6 gone)   0.6552   0.0936            0        6
```

The complete spectrum is **unchanged** — no regression on the correct case. The
incomplete ones now fall, and `missing_reference_count` reports the truth for the
first time.

Structural coverage multiplies rather than adds. An HSQC explaining two of seven
predicted environments is not "slightly less good" than a complete one: most of
the molecule is unaccounted for, and every other term in the score is computed
over the peaks that *are* present, so none of them can see the absence.

### What was found while building it

Symmetry collapse was first written against **predicted shifts**, and the tests
caught it. The heuristic predictor returns 14.00 ppm for all three ibuprofen
methyls and 129.0 for all four aromatic CH, so shift-based collapse merged
chemically distinct environments and produced 5 expectations where a real HSQC
shows 7 — a denominator too *small*, letting coverage exceed 100 %. Equivalence
is a property of the molecule, so it now collapses on RDKit canonical ranks with
`breakTies=False`. Verified: ethanol 2, benzene 1 (six equivalent atoms),
ibuprofen 7 with equivalents `[2,1,1,1,1,2,2]`, CCl4 0.

`missing_reference_count` was also **mis-named for what it computed**: observed
correlations matching no reference — an *unexpected* peak, not a missing one.
That is why it read 0 while six of seven were absent. With a structure it now
means what its name says; without one it keeps the old meaning, because renaming
a field on a live contract is a separate change.

### Still open

* **HMBC has no structural denominator** and deliberately so — 2- and 3-bond
  correlations, sometimes 4 through conjugation, and 2-bond ones frequently
  absent. A structural denominator there would punish correct structures. C5.
* **The `nmr2d` class multipliers** (carbohydrates 1.50, flavonoids 1.40,
  glycoproteins 1.40, alkaloids 1.30) are now multiplying a score that can fail
  for the right reason. Whether those values are still the right ones against the
  changed score is C8's question, not an assumption to carry.
* **Per-correlation matching** — knowing *which* environment is missing rather
  than how many — needs a predictor accurate enough for a usable window.

---

## C5 RESULT — partial: the guard is in, the measurement waits on C0

### Done: HMBC gets no structural denominator, and that is now pinned

Checked first rather than assumed. The HMBC branch (`nmr2d_analyzer.py:340`)
scores observed peaks against observed 1D reference shifts and has **no
expectation set at all**, so absence was never penalised. C4 did not change that
— the structural denominator is gated to HSQC/HMQC.

Measured with a structure supplied, HMBC-only previews:

```
observed        evidence_score   missing_reference_count   expected_environment_count
6 of 6              0.6918                 0                        None
3 of 6              0.7951                 0                        None
1 of 6              0.5729                 0                        None
```

`missing_reference_count` stays 0 and no structural expectation is formed,
whatever is observed. Correct.

**The reason this needed a guard rather than a note.** C4 gave HSQC a structural
denominator. The natural next move for anyone tidying up is to give HMBC one for
symmetry — and that would reject correct structures. An HSQC one-bond correlation
is *expected*: every protonated carbon must show one. An HMBC correlation is not.
2-bond couplings are frequently weak or absent even when the structure is right,
depending on dihedral angle and on how the experiment's delay was tuned. Absence
is uninformative; only presence is evidence. Three tests now pin this with the
reason attached.

Note the score still moves with peak count through the other terms (0.6918 /
0.7951 / 0.5729 above) because quality and artifact terms average over the peaks
present. That is **not** asserted as monotonic in either direction — for HMBC,
observing more correlations genuinely does not mean the structure is more likely
right, since a wrong structure can also produce many. No claim is made here that
the evidence does not support.

### Not done, and why

The rest of C5 needs real spectra with hand-derived correlations, i.e. **C0**,
which has not been run — the fixtures are not staged. Specifically outstanding:

* **How much HMBC narrows the candidate set.** The deliverable C5 asks for is a
  measured statement, and there is nothing honest to measure without ground
  truth. Fabricating it from synthetic peaks would produce a number about the
  fixture generator, not about HMBC.
* **Reporting how many structures a correlation set is consistent with.** Needs a
  candidate enumerator that does not exist yet; scope it before building.
* **Recording the n-bond assumption per correlation.** A correlation counted as
  3-bond under one reading and 2-bond under another supports different skeletons,
  and nothing currently records which was assumed.

**C0 is now the blocking phase for the rest of C.** C2 (parser fidelity), C3
(artifact rejection), C6 (COSY diagonal) and C8 (does 2D change a verdict) all
need real 2D data with known answers. The synthetic probes used for C1/C4/C5 were
enough to expose a denominator defect and pin a design decision, but they cannot
establish accuracy against reality.

---

## C0 SOURCES — real 2D data, searched and licence-checked (2026-08-09)

The gap blocking C2/C3/C6/C8 is real 2D spectra with known answers. Four
candidates, checked for licence first because that is what killed the last one.

### The licence position, stated once

**"We are only testing, not distributing" resolves share-alike. It does not
resolve NonCommercial.** Those are different clauses:

* **CC-BY-SA** (NMRShiftDB2) restricts *redistribution* — the obligation is to
  license derivatives alike. Internal use is unaffected, which is exactly why the
  existing gate withholds structures from API responses rather than banning the
  corpus.
* **CC BY-NC** restricts *use*: "You may not use the material for commercial
  purposes", where commercial means primarily directed toward commercial
  advantage. Developing and validating a product sold under a commercial licence
  is plausibly commercial use **even with nothing redistributed**.

That is a reading, not a legal opinion, and it is worth one email rather than an
argument — see 2DNMRGym below, whose authors explicitly invite exactly that.

### 1. 2DNMRGym — the best scientific fit, blocked on licence

~22,000 HSQC spectra with molecular graphs and SMILES. Critically it carries a
**dual-layer annotation**: algorithm-generated "silver" labels for the bulk, plus
**479 spectra / 7,310 peaks manually annotated and cross-validated by three
domain experts** — a gold-standard subset.

That 479-spectrum subset is precisely what C0 asks for and better than
hand-deriving one compound here, because it is expert-labelled and
cross-validated rather than derived by whoever is running the phase.

**Licence: code MIT, data CC BY-NC 4.0.** The README states: *"If you wish to use
the dataset for commercial purposes, please contact the authors."* So the route
is explicit and cheap. **Do not ingest it until that permission exists in
writing**, and record the reply next to the corpus manifest.

Distributed via Hugging Face; peak lists and annotations rather than raw FIDs, so
it serves C4-style correlation work but not C2 (parser fidelity), which needs raw
`ser` files.

### 2. MetaboLights (EMBL-EBI) — the usable one, and it has raw data

**Licence: CC0 for submissions from April 2025**, i.e. public domain dedication,
commercial reuse permitted, no attribution required. Submissions *before* April
2025 fall under EBI terms of use and must be checked per study.

It holds **raw Bruker data including `ser` files** — study `MTBLS1` is the
canonical public example — and since June 2025 raw NMR folders are deposited as
ZIPs. That makes it the only candidate here that can serve **C2**, since parser
fidelity needs the real acquisition files, not a peak list.

Caveat to check per study before use: metabolomics 2D is usually a *mixture*
(biofluid, extract), not a single pure compound. Mixtures are excellent for C3
(artifact rejection under real crowding) and poor for C4 (a structural
denominator assumes one known structure). Filter for studies on characterised
single compounds or spike-in standards.

### 3. BMRB — public domain, but check the fit

Public-domain licensing, and the scope explicitly includes natural products,
metabolomics and small molecules alongside its protein core. Good for reference
chemical shifts. Weaker for this phase specifically because the raw 2D holdings
skew biomolecular — and the technical whitepaper already records that
protein-trained assumptions are not transferable, which applies to the data as
much as to model weights.

### 4. NMRShiftDB2 — already in the tree, already gated

CC-BY-SA, and the redistribution gate for it already exists
(`_REDISTRIBUTABLE_LICENCES`, empty and failing closed). Predominantly 1D
assignments, so it does not solve the 2D gap, but it is the precedent for how a
share-alike corpus is handled here.

### Recommended C0 sequence

1. **Start with MetaboLights**, filtered to post-April-2025 CC0 studies with raw
   2D and a single characterised compound. Unblocks C2 immediately and needs no
   permission.
2. **Email the 2DNMRGym authors** in parallel. The 479-spectrum expert subset is
   worth waiting for and the ask is one message.
3. Keep the maintainer's own `~/My Business /NMR Test Samples` as the in-house
   set — it is already licence-clean, and it is the only source where the
   structure is known with certainty rather than inferred.

**Record the licence per source in the corpus manifest before ingest, and fail
closed on anything unread.** That is the standing rule and it is what turned this
search from "here are four datasets" into "one is usable today".

### C0 SEARCH RESULT — no 2D raw data is available yet (2026-08-09)

Searched rather than assumed, and the answer is a clean negative that saves the
next session the same hour.

**In-house (`~/My Business /NMR Test Samples`): 1D only.** Four `acqus` files,
all 1D — e.g. `zgpg30` (power-gated-decoupled 13C). **Zero** `ser`, `acqu2s` or
`2rr` anywhere in the tree. The compounds are exactly the right ones (pyrrolidine
sulfamates, napamine, tobramycin — structures known with certainty), but no 2D
was acquired.

**MetaboLights recent CC0: NMR is sparse, and what there is is 1D.** Scanned the
60 most recent public studies via the API:

* **Every one is `CC0 1.0 Universal`.** The April-2025 cutoff is real and
  holding, and `datasetLicense` is exposed as a field — so the licence gate this
  playbook demands can be *automated*, not eyeballed.
* Only **2 of ~60** are NMR at all (`MTBLS15218`, `MTBLS15091`). Metabolomics
  deposition is MS-dominated.
* `MTBLS15218`'s raw Bruker folders are **1D**: one `fid`, one `acqus`, no `ser`.
  Pulse program `noesypr1d`.

**A trap worth recording: `noesypr1d` is a 1D experiment.** It uses a NOESY pulse
element for solvent suppression and has "NOESY" in its name. Any search filtering
on "NOESY" to find 2D data will collect 1D metabolomics spectra by the thousand.

### What this means for C0

Raw 2D has to be *sourced*, and the options split by which phase they serve:

| need | source | status |
|---|---|---|
| **C2** parser fidelity (needs real `ser`, `acqu2s`, per-axis referencing) | targeted MetaboLights search, or acquire in-house | not yet found |
| **C4/C5** correlation work (needs peak lists + assignments) | 2DNMRGym, 479 expert-annotated | blocked on CC BY-NC permission |

**The strongest option is probably to acquire one.** The in-house compounds
already have certain structures — an HSQC and an HMBC on the pyrrolidine
sulfamate or napamine would give ground truth no public corpus can match, because
the structure is known rather than inferred, and it is licence-clean by
construction. One overnight run on a known sample unblocks C2, C3, C4 and C6
together.

Failing that, a targeted MetaboLights scan filtering assay files for HSQC/HMBC
experiment types (rather than scanning by recency) is the next cheapest search —
the metabolomics 2D literature exists, so the deposits likely do too, just not in
the most recent 60.
