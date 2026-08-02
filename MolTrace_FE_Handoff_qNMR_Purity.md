# Frontend handoff — qNMR purity

**From:** backend session. **Commit:** `cccf845`.
**Status:** merged to `main`, full suite green (3393 passed).

**Why this one matters more than its size suggests.** qNMR purity is SpectraCheck's headline
analytical claim — the ±0.5% figure on the module's own datasheet. The engine was fully
implemented and completely unreachable: no route referenced it, and the only qNMR surface in the
product was gated behind a regulatory dossier, which a SpectraCheck-only customer does not have.
Until this is on screen, the flagship claim is true in the codebase and not in the product.

Two stateless routes, no persistence, no subject, no gating beyond authentication. This is the
smallest handoff I've written and the highest-value one.

---

## Task 1 — Regenerate

```bash
cd /Users/michaelhotor/MolTrace/moltrace_backend && .venv/bin/uvicorn nmrcheck.main:app --port 8000
```
```bash
cd /Users/michaelhotor/MolTrace/moltrace_frontend && npm run generate:openapi
```

| Kind | Name |
|---|---|
| New path | `POST /spectrum/qnmr/purity` — against a weighed internal standard |
| New path | `POST /spectrum/qnmr/purity/pulcon` — against an external reference |
| New schemas | `QnmrInternalStandardRequest`, `QnmrPulconRequest`, `QnmrPurityResult` |

**Done when:** `grep -c "QnmrPurityResult" src/lib/api/schema.d.ts` is non-zero.

---

## Task 2 — Build the panel

`components/spectracheck/shift-prediction-panel.tsx` is the pattern to copy: a stateless
`/spectrum/…` compute panel using `apiFetch`, mounted from
`spectracheck-processed-spectrum-section.tsx`. A purity panel belongs in the same place, near the
integration panel — purity is what an analyst computes *from* the integrals they have just
reviewed.

### Internal standard — the routine determination

Eight required numbers, one optional with a sane default:

```jsonc
{ "analyte_integral": 2.0, "standard_integral": 1.0,
  "analyte_protons": 2,   "standard_protons": 1,
  "analyte_molar_mass": 100.0, "standard_molar_mass": 100.0,   // g/mol
  "analyte_mass_mg": 10.0,     "standard_mass_mg": 10.0,
  "standard_purity_percent": 100.0 }                            // optional, defaults to 100
```

### PULCON — external reference

Six required, plus acquisition terms that all default sensibly
(`analyte_pulse_width_us`, `reference_pulse_width_us`, `*_temperature_k`, `*_receiver_gain`,
`*_scans`). **Default the acquisition terms and keep them behind a disclosure** — a user who
leaves them alone gets a correct ratio-based answer, and surfacing nine extra fields up front
would make the routine case look harder than it is.

### The response

```jsonc
{ "purity_percent": 99.1, "uncertainty_percent": 0.42, "relative_uncertainty": 0.0042,
  "method": "internal_standard",
  "inputs": { … }, "intermediates": { … }, "warnings": [ … ], "notes": [ … ] }
```

---

## Task 3 — Show the uncertainty and the derivation *(this is the product, not decoration)*

Three things distinguish this from a calculator, and all three are easy to drop:

1. **Never show `purity_percent` without `uncertainty_percent`.** It is a combined standard
   uncertainty at k = 1. Render it as `99.10 ± 0.42 %` — a purity figure without its uncertainty is
   exactly the unfalsifiable number this module exists to replace.
2. **Surface `intermediates`.** Every ratio that built the answer comes back so a reviewer can
   re-derive it from the record alone. Collapsed by default is fine; absent is not. That is what
   makes the number defensible rather than something to take on trust.
3. **Render `warnings` prominently.** The engine flags things like a purity above 100%, which
   means the inputs are wrong — a real result the analyst needs to see, not a footnote.

`notes` carries the decision-support framing and should be shown verbatim. Do not label output as
a certificate of analysis, and do not present the figure as a released result — it is only as good
as the integration and weighing behind it, which the notes say.

---

## Task 4 — Let a lab own its uncertainty

`integral_rel_u`, `mass_rel_u`, `standard_purity_rel_u`, `molar_mass_rel_u` (and the PULCON
equivalents) are **optional** — omit them and the engine's conservative defaults apply.

Supplying them is what turns the reported figure from the engine's estimate into *this
laboratory's* estimate, which is what a validated method needs. Put them behind an "uncertainty
inputs" disclosure, and send `undefined` rather than `0` when untouched — sending `0` claims
perfect measurement and will report an uncertainty far tighter than the lab can justify.

---

## Not in scope

- **No persistence.** These routes compute and return; nothing is stored. Attaching a purity result
  to a session as evidence is a separate piece of backend work that does not exist yet — so do not
  build a "save to session" affordance that has nowhere to go.
- The dossier-gated `qnmr-compliance` surface is unrelated and unchanged. It answers "is this
  method ICH Q2/Q14-ready for a filing"; this answers "what is the purity". A SpectraCheck-only
  customer can reach the second and not the first, which is the point of the change.

---

## Verification

**Done when:** with `MOLTRACE_ENABLED_MODULES=spectracheck` and no dossier anywhere, an analyst can
enter the eight internal-standard numbers, get a purity with its uncertainty, expand the
derivation, and see any warning — with an empty console.

A quick arithmetic sanity check you can type in: the example body above returns exactly **100%**,
because every ratio is 1 except the integral ratio, which cancels the proton ratio. Halve
`analyte_integral` to 1.0 and it returns exactly **50%**.
