# MolTrace Release Guardrails

This file is the top-level reviewer map for diagnostic artifacts, Prompt 1/2
raw-FID sidecars, and the next SpectraCheck prompt layers.

## Non-Negotiable Boundaries

- Prompt 1/2 Bruker/Varian FID reader, phase, and baseline work remains
  reporting-only unless a separate manual runtime-promotion phase is opened.
- Processed 1H/13C spectra, processed analysis tables, and current
  Mnova-like raw-FID spectrum behavior must not change as a side effect of
  diagnostic work.
- SpectraCheck, Regulatory Hub, and ReactionIQ regressions must stay green.
- Prompt output may not drive plotted spectra, peak markers, legends,
  integration, qNMR, phase correction, baseline correction, or analysis tables
  until an explicit promotion stage is reviewed and protected by tests.
- Unknown or failed diagnostic paths must fall back to the existing legacy
  behavior, not block user uploads.

## Reviewer Commands

Run these before merging changes that touch raw-FID Prompt diagnostics,
release-health payloads, Deployment Settings health rendering, CI artifact
names, release docs, or prompt promotion policy:

```bash
./scripts/run_prompt_sidecar_guardrails.sh
./scripts/run_release_health_contract_guardrails.sh
```

The full release checklist lives at:

```text
moltrace_backend/docs/week21_release_candidate.md
```

The manual promotion policy lives at:

```text
moltrace_backend/docs/raw_fid_prompt_manual_promotion_design.md
```

## CI Artifacts Map

| Artifact | Open this when | Release decision |
| --- | --- | --- |
| `raw-fid-prompt-release-readiness` | You need the fastest one-page Prompt 1/2 readiness summary. | Reviewer-facing summary only; runtime activation stays blocked. |
| `raw-fid-prompt-shadow-comparison` | You need sidecar-vs-legacy fixture deltas. | Read-only comparison evidence; do not use it to drive plotted spectra. |
| `raw-fid-prompt-provenance-checksums` | You need fixture/report hashes for audit trails. | Audit evidence only; investigate hash drift before release. |
| `raw-fid-prompt-manual-promotion-gate` | You need detailed manual-promotion gate diagnostics. | May show `review_required` without failing CI; `activation_allowed=false` must remain in effect. |

## Fast Prompt Integration Cadence

Use the same five-step cadence for Prompt 3 through Prompt 12. Do not promote a
new layer directly into user-visible runtime behavior.

1. **Spec and contract first**
   - Write the minimal module contract, dataclasses, expected inputs/outputs,
     and fixture expectations.
   - Add contract tests before wiring into SpectraCheck.

2. **Pure engine next**
   - Implement the smallest standalone engine with deterministic outputs.
   - Keep it independent of FastAPI routes and React state until unit tests are
     stable.

3. **Shadow or sidecar integration**
   - Expose the new layer as metadata, diagnostics, or admin-only comparison.
   - Do not replace visible spectra, peak picking, processed analysis, or
     existing evidence tables.

4. **Frontend visibility only when useful**
   - Add parser and display tests if the layer appears in Deployment Settings,
     SpectraCheck QA panels, or release-health output.
   - Keep default user-facing behavior unchanged.

5. **Promotion is separate**
   - Only after fixtures, shadow comparisons, and guardrails pass should a
     dedicated promotion phase consider runtime activation.
   - Promotion must include rollback, screenshots, fixture summaries, and
     focused regression tests.

## Prompt 3 Through Prompt 12 Plan

- **Prompt 3: GSD layer** can start next. Build it as a standalone,
  deterministic sidecar first, with no visible spectrum mutation.
- **Prompts 4-6** should extend evidence quality and candidate reasoning only
  through contracts and sidecars until their fixture behavior is stable.
- **Prompts 7-9** should add UI/admin display only after backend contracts are
  pinned.
- **Prompts 10-12** should be treated as promotion or orchestration layers:
  they can combine earlier outputs, but must not loosen existing spectrum,
  session, dashboard, Regulatory Hub, or ReactionIQ regressions.

## Per-Prompt Definition Of Done

Each prompt phase is done only when:

- New behavior has narrow unit or contract tests.
- Existing SpectraCheck processed-spectrum tests remain unchanged.
- Raw-FID visible behavior remains legacy unless the phase explicitly opens a
  promotion branch.
- Release-health or artifact docs are updated if new diagnostics are exposed.
- `./scripts/run_prompt_sidecar_guardrails.sh` passes when SpectraCheck raw-FID
  diagnostics are touched.
- `./scripts/run_release_health_contract_guardrails.sh` passes when admin
  release-health payloads or frontend health rendering are touched.
- Any new dependency is justified in docs and added with clear install steps.

## Dependency Rule

Do not add dependencies opportunistically. If a prompt truly requires a new
package, document:

- why the current stack cannot do the job;
- the exact package and version range;
- backend or frontend install commands;
- tests proving the dependency is optional or has a safe failure mode.
