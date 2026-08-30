# MolTrace Frontend — Changelog

Notable changes to the MolTrace frontend (`moltrace_frontend/`). The backend
keeps its own log in `moltrace_backend/CHANGELOG.md`; that one is explicitly
backend-only, which is why frontend work went unrecorded until this file existed.

**This log starts on 2026-08-08 and is not backfilled.** Reconstructing earlier
entries from commit history would mean characterising changes without having
verified them, which is worse than an honest starting point. For anything older,
`git log -- moltrace_frontend/` is the record.

Entries are dated rather than versioned. `package.json` carries `0.1.0` and has
not tracked releases; inventing a version history to match the backend's
`v0.6x` line would be a fiction of exactly the kind several entries below are
about.

---

## 2026-08-30 — a labelled mockup can still be the only thing on the page

The 2026-08-08 sweep drew its line at **labelled mockup versus unlabelled
substitution** and, on that line, cleared `reaction-studio`: every block there does
render its own disclaimer at display time. That judgement still holds. This entry
adds the case it did not cover — a mockup can be honestly labelled and still be
misleading, if it is the only thing the page offers.

### Reaction Studio opens a real campaign before it shows an illustrative one

The surface named "Reaction Studio" led with fixed sample data. The numbers were
disclosed: the outcomes card reads "values are fictional and shown for layout
only", and the prediction card is `status="unavailable"` with "predicted yield
placeholder 76%" and "Predictions are turned off until model evidence is
connected". A chemist met them anyway, because there was nothing else to meet.

The optimizer, surrogate diagnostics, Pareto front, safety screening and regulatory
constraints all run against real experiments at `/reactions/[reactionId]`, and this
page never mentioned it. An "Open a reaction project" picker now leads, above the
scheme editor and the sample tables; selecting a project routes to its workspace.
Accounts with no projects get an honest empty state pointing at where to create one,
rather than a blank control.

Routed rather than embedded, deliberately: `ReactionProjectDetail` takes no props
and reads `useParams()` for its id, so embedding it would mean refactoring an
11,000-line component and mounting it a second time would duplicate every fetch it
performs.

The sample content stays. It is honestly labelled and it is what gives the page its
layout; the defect was that it had no alternative above it, not that it existed. One
piece of copy did mislead and changed: the run-data section read "Factor settings
per run paired with measured yield / selectivity / impurity outcomes", which
describes the reader's own data. It now says the rows are fixed sample values and
points at the picker.

The picker is uncontrolled — `value={null}`, navigate on change — so there is no
state to re-set and no inline literal feeding a `setState`. That is the shape that
caused an infinite render loop in this codebase before, and it is avoided
structurally rather than by care.

---

## 2026-08-08 — the screens stop showing numbers nobody measured

A sweep for data the product displayed as though it were the customer's own.
The recurring shape: a fabricated fallback that is indistinguishable from a
measurement at the moment a new deployment has no live data — first login, which
is also when a regulated buyer decides whether the numbers can be trusted.

### Fabricated dashboard metrics removed

The main dashboard rendered 23 active analyses, 7 awaiting review, 12 reports,
156 hours saved and 94.2 % model confidence whenever the backend was
unreachable, beside five activity rows attributed to "Dr. Chen", "Dr. Patel" and
"Dr. Kim" against sample "API-Q4-BATCH-12".

Cards now stay and the number becomes an explicit dash. Hiding a tile would be
its own dishonesty: a reader cannot tell a metric that is genuinely zero from one
that failed to load.

* **A fabricated green light is worse than a fabricated count.** Operations
  reported `systemHealthStatus: "healthy"` and method health a validation run
  that had `"succeeded"` — precisely when those endpoints could not be reached.
  Those are the signals a reviewer acts on.
* **"Model Confidence" at 94.2 % had no live branch at all** — not a fallback, a
  permanent fiction, and no model-confidence metric exists anywhere in the
  product to wire it to. Replaced by **Mean Session Confidence**: the mean of the
  confidence the sessions in view actually report, carrying its denominator.
  Sessions with no score are excluded rather than counted as zero, which would
  have made the figure respond to *coverage* while looking like it responded to
  quality.
* `reviewRequiredCount` is `null` rather than `0` when unknown. "No sessions need
  review" and "we could not find out" are different answers and only one of them
  should colour the card.

**The demo constants were load-bearing.** Replacing
`setQcRecentFailed(DEMO_QC_ALERTS.recentFailed)` with a fresh `[]` made the
component render forever: `setState` bails out only on reference equality, the
demo constants were module-level, and the QC effect depends on
`overview.sessions`, which the overview context returns as a new array every
render. The fabrication was holding an existing dependency bug shut by accident.
Fixed with module-level `NO_QC_ROWS` / `NO_ACTIVITY_ROWS` / `NO_JOB_ROWS`.

### Four prototype routes retired

`/dashboard/regulatory`, `/dashboard/spectroscopy`, `/dashboard/reactions` and
`/dashboard/projects` were v0 mockups — fully static screens with **zero** data
fetching, rendering invented records as though they were the customer's own.
Nothing in the product linked to them; the only references were visual-baseline
scripts whose match signals pinned the fabricated identifiers themselves.

A mockup route cannot be made honest while remaining a mockup: there is no live
source behind it to fall back from. Each now redirects to the real surface, so
the URL keeps working and lands on data that exists.

The fourth was missed on the first pass — the sweep had grepped for the invented
reviewer names and that page carries none. Found by re-running the sweep instead
of trusting it.

### Saved Reports tiles

Rendered 12 ready / 3 generating / 47 this month on a failed stats fetch, with
"Example value" in small print underneath. Better than the dashboard managed and
still wrong: the number is what the eye lands on and the disclaimer is read
second if at all. Now a dash.

### Deliberately left as they are

The line this sweep draws is **labelled mockup versus unlabelled substitution**,
not "contains demo data":

* the **"Example layout"** table in Saved Reports — under a heading saying so,
  stating the rows are not approved or signed off;
* **reaction-studio** — every block renders its own disclaimer at display time
  ("Figures below are placeholders for a future surrogate model. No prediction
  has been run yet"), not merely a code comment;
* **automation-roi** — labelled "Demo scenario — illustrative metrics only" and
  "(synthetic)".

### Also landed this day

Recorded from each commit's own description rather than re-interpreted:

* `957c161` — the owner-scoped compound registry refusal renders neutrally,
  following the backend change that scoped reads to the registrant.
* `f72a80a` — the SpectraCheck evidence panels stop overstating their own
  numbers.
* `610610a` — the live marketing pages stop quoting numbers the product cannot
  produce; `fa50ba2` stops implying regional presence the team does not have.
* `faf4b3b`, `bf36192` — the published contact addresses were on a domain the
  project does not own; the public contact surfaces now route to a mailbox that
  exists.
* `01e6c3e`, `1f32219` — knowledge surfaces show what a fact was justified by and
  whether anyone still stands behind it, plus the corpus conveyor.
* `0613117` — two test doubles given the signatures they are actually called
  with.
