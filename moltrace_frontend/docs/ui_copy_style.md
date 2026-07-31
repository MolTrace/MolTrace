# UI copy style

Rules for user-visible text in the MolTrace app. Derived from an audit of 1,584
in-app strings (median 10 words; 174 over 18 words; 34 cards whose description
merely restated their title).

The audience is pharmaceutical R&D scientists and regulatory reviewers. They are
expert readers with little time. Short is respectful, not dumbed-down — but
short must never cost precision, and it must never cost a hedge.

## 1. One idea per string

A description says **what the thing does**, in ≤14 words. Mechanism — the
algorithm, the library, the fallback chain, how it is configured — is a *second*
sentence, or it belongs in a tooltip, or it is not needed at all.

> ✗ Encodes a candidate SMILES into the same vector space as the reference
> library and returns the nearest spectra by L2 distance. The similarity index
> is server-configured; matches are decision support.
>
> ✓ Finds reference spectra closest to a candidate structure.
> Nearest-neighbour search over encoded shifts. Decision support.

Lead with the verb and the object. Cut the run-up: "This panel lets you…",
"Use this to…", "The following…".

## 2. Never restate the title

If a card's description repeats the nouns already in its title, it is costing a
line and earning nothing. Either say something new or delete it.

> ✗ **Workflow runs** — "Workflow runs across every analysis session in this project."
> ✓ **Workflow runs** — "Across every session in this project."
> ✓ **Workflow runs** — *(no description)*

## 3. Hedges are load-bearing — keep them, don't rewrite them

Compliance framing ("designed to support", never "compliant") and honest scoping
("decision support only", "advisory", "never a synthesis instruction",
"qualified human review required", "illustrative") are the product's claims about
itself. They are legally and scientifically meaningful.

**Shorten the description around a hedge; never shorten the hedge.** Where the
same hedge already appears verbatim in several places, keep that exact wording so
it reads as a recognized standing caveat rather than fresh prose each time.

Only 37 of the 174 long strings carry a hedge. The other 137 are the target.

## 4. Labels are nouns, not sentences

Field labels, column headers, tabs and buttons: ≤4 words, no terminal period, no
explanation. Explanation goes in help text or a tooltip.

> ✗ "experiments needing outcome confirmation" ✓ "Awaiting outcomes"
> ✗ "Open a reaction project to load mobile approval summary"
> ✓ "Open a reaction project to see its approval summary"

Never name the surface in its own copy ("mobile", "this panel", "the dashboard").
The reader can see where they are.

## 5. Empty states: what is missing, then the one action

≤12 words. Do not apologise, do not explain the data model.

> ✗ "No compact preview data available for this session."
> ✓ "No spectrum preview yet."

## 6. Errors: what failed, then what to do

One sentence. No mechanism, no status code, no field path.

> ✗ "Download failed (403)"  ✓ "This file could not be downloaded. Please try again."

## 7. Keep the science

Terseness stops at domain vocabulary. `HSQC`, `qNMR`, `ICH M7(R2)`, `Cp/Cpk`,
`Pareto front`, `SHA-256` and their kin are the shortest correct form already —
replacing them with plain English makes the copy *longer* and less precise. Same
for units and nucleus labels.

See also `docs/app_simplification_plan.md`.
