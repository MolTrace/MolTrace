"use client"

// Golden Path runner — executes the five real endpoints in order, measuring each.
//
// The arc is chained on real data, not on narration: step 1's `generated_inputs.
// nmr_text` (the peak list the FID processor actually produced) is what step 2
// compares candidates against. If step 1 degrades, step 2 degrades with it —
// which is exactly the property the handoff's §6.3 check relies on.
//
// A failed step STOPS the arc. Continuing past a failure would render four green
// panels under one red one and read as "mostly worked"; an arc that broke in the
// middle did not complete, and the UI says so.

import { useCallback, useMemo, useState } from "react"
import { ApiError } from "@/lib/api/client"
import {
  GOLDEN_PATH_STEPS,
  assessImpurities,
  compareCandidateEvidence,
  createActionItem,
  createDossierWithProvenance,
  createEvidenceBundle,
  evaluateContracts,
  initialOutcomes,
  listExpectedOutputContracts,
  measuredArcElapsedMs,
  processRawFid,
  recordArc,
  runCompliantDesign,
  type ContractCheck,
  type CrossModuleActionItem,
  type ExpectedOutputContract,
  type FIDProcessResult,
  type GoldenPathInputs,
  type GoldenPathStepKey,
  type GoldenPathStepOutcome,
  type PilotEvidenceBundle,
  type PilotRunDetail,
  type StepStatus,
} from "@/lib/pilot/golden-path"
import { readRunRegulatorySummary } from "@/lib/reaction/regulatory-proposal"

/** User-facing failure text. Never leaks a status code or an endpoint path. */
function failureText(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error && err.message) return err.message
  return "This step could not be completed."
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return v != null && typeof v === "object" && !Array.isArray(v)
}

/** Pull the peak list step 1 actually produced, so step 2 runs on real data. */
export function nmrTextFromFid(result: unknown): string | null {
  if (!isRecord(result)) return null
  const generated = result.generated_inputs
  if (!isRecord(generated)) return null
  const text = generated.nmr_text
  return typeof text === "string" && text.trim() !== "" ? text : null
}

export type GoldenPathRunState = {
  outcomes: GoldenPathStepOutcome[]
  running: boolean
  /** The step currently in flight, for the progress affordance. */
  activeStep: GoldenPathStepKey | null
  pilotRun: PilotRunDetail | null
  contracts: ExpectedOutputContract[]
  checks: ContractCheck[]
  actionItems: CrossModuleActionItem[]
  bundle: PilotEvidenceBundle | null
  /** Set when the arc stopped early. The arc did not complete. */
  haltedAt: GoldenPathStepKey | null
  /** Measured wall-clock across the steps that ran. */
  totalElapsedMs: number | null
  recordingError: string | null
}

export function useGoldenPathRun(scenarioId: number | null) {
  const [outcomes, setOutcomes] = useState<GoldenPathStepOutcome[]>(initialOutcomes)
  const [running, setRunning] = useState(false)
  const [activeStep, setActiveStep] = useState<GoldenPathStepKey | null>(null)
  const [pilotRun, setPilotRun] = useState<PilotRunDetail | null>(null)
  const [contracts, setContracts] = useState<ExpectedOutputContract[]>([])
  const [checks, setChecks] = useState<ContractCheck[]>([])
  const [actionItems, setActionItems] = useState<CrossModuleActionItem[]>([])
  const [bundle, setBundle] = useState<PilotEvidenceBundle | null>(null)
  const [haltedAt, setHaltedAt] = useState<GoldenPathStepKey | null>(null)
  const [recordingError, setRecordingError] = useState<string | null>(null)

  const totalElapsedMs = useMemo(() => measuredArcElapsedMs(outcomes), [outcomes])

  const run = useCallback(
    async (inputs: GoldenPathInputs) => {
      setRunning(true)
      setHaltedAt(null)
      setRecordingError(null)
      setPilotRun(null)
      setBundle(null)
      setChecks([])
      setActionItems([])

      let working = initialOutcomes()
      setOutcomes(working)

      const commit = (next: GoldenPathStepOutcome[]) => {
        working = next
        setOutcomes(next)
      }
      const patch = (key: GoldenPathStepKey, changes: Partial<GoldenPathStepOutcome>) =>
        commit(working.map((o) => (o.key === key ? { ...o, ...changes } : o)))

      /** Run one step, measuring it. Returns null when it failed. */
      async function step<T>(
        key: GoldenPathStepKey,
        call: () => Promise<T>,
        statusOf: (value: T) => StepStatus = () => "succeeded",
      ): Promise<T | null> {
        setActiveStep(key)
        const startedAt = Date.now()
        patch(key, { status: "running", startedAt, finishedAt: null, elapsedMs: null, error: null })
        try {
          const value = await call()
          const finishedAt = Date.now()
          patch(key, {
            status: statusOf(value),
            finishedAt,
            elapsedMs: finishedAt - startedAt,
            payload: value,
            error: null,
          })
          return value
        } catch (err) {
          const finishedAt = Date.now()
          patch(key, {
            status: "failed",
            finishedAt,
            elapsedMs: finishedAt - startedAt,
            payload: null,
            error: failureText(err),
          })
          setHaltedAt(key)
          return null
        }
      }

      try {
        // 1 — Raw FID → spectrum.
        const fid = await step<FIDProcessResult>("raw_fid_process", () => processRawFid(inputs))
        if (fid == null) return

        // 2 — Spectrum → structure evidence. Fed by step 1's real peak list.
        const evidence = await step("candidate_evidence", () =>
          compareCandidateEvidence(inputs, nmrTextFromFid(fid)),
        )
        if (evidence == null) return

        // 3 — Impurity assessment. Deterministic, version-pinned.
        const impurities = await step("impurity_assess", () => assessImpurities(inputs))
        if (impurities == null) return

        // 4 — Compliant design. `requires_review` is the demo-worthy outcome:
        // the optimizer declining rather than proposing something unfilable.
        if (inputs.reactionProjectId != null) {
          const projectId = inputs.reactionProjectId
          const bo = await step(
            "bo_run",
            () => runCompliantDesign(projectId),
            (value) => {
              const summary = readRunRegulatorySummary(value)
              if (value.status === "requires_review") return "requires_review"
              if (summary.feasibilityKnown && (summary.feasibleCount ?? 0) === 0) return "requires_review"
              return value.status === "failed" ? "failed" : "succeeded"
            },
          )
          if (bo == null) return
        } else {
          patch("bo_run", {
            status: "failed",
            error: "No reaction project is linked to this scenario, so the design step was not run.",
          })
          setHaltedAt("bo_run")
          return
        }

        // 5 — Dossier + provenance.
        const dossier = await step("dossier_evidence", () => createDossierWithProvenance(inputs, working))
        if (dossier == null) return

        // The two seams, recorded once the arc has produced records that actually
        // exist. Anchoring them earlier would mean writing a placeholder resource
        // id, and an action item that names resource 0 names nothing — the whole
        // point of the chain is that each end deep-links to a real record.
        const evidenceLinkId =
          dossier.links.find((l) => l.evidence_type === "unified_evidence")?.id ?? dossier.links[0]?.id ?? null
        const items: CrossModuleActionItem[] = []
        for (const spec of [
          evidenceLinkId != null
            ? ({
                source_program: "spectracheck",
                target_program: "regulatory_hub",
                source_resource_type: "evidence_link",
                source_resource_id: evidenceLinkId,
                target_resource_type: "dossier",
                target_resource_id: dossier.dossier.id,
                action_type: "link_evidence",
                title: "Structure evidence linked into the regulatory dossier",
                description:
                  "The ranked candidate evidence from the processed spectrum is carried on this dossier as a reviewable evidence link.",
                severity: "info",
                status: "open",
              } as const)
            : null,
          {
            source_program: "regulatory_hub",
            target_program: "reaction_optimization",
            source_resource_type: "dossier",
            source_resource_id: dossier.dossier.id,
            target_resource_type: "reaction_project",
            target_resource_id: inputs.reactionProjectId,
            action_type: "create_reaction_constraint",
            title: "Impurity limits applied to the design proposal",
            description:
              "The assessed limits were applied to this project's optimization run, so a candidate breaching a hard limit is reported rather than recommended.",
            severity: "warning",
            status: "open",
          } as const,
        ]) {
          if (spec == null) continue
          try {
            items.push(await createActionItem(spec))
          } catch {
            // The handoff record is continuity, not correctness — a failure here
            // must not fail the arc, and an item we could not write is simply
            // absent rather than drawn as if it exists.
          }
        }
        setActionItems(items)
      } finally {
        setActiveStep(null)

        // Record the arc — separately from executing it, so a recording failure
        // can never be mistaken for an arc failure (or vice versa). `running`
        // stays true across this: releasing the button first would let a second
        // click start a fresh arc while this one is still being written down.
        if (scenarioId != null) {
          try {
            const recorded = await recordArc(scenarioId, working)
            setPilotRun(recorded)
            try {
              setBundle(await createEvidenceBundle(recorded.id, "Golden path evidence bundle"))
            } catch {
              setBundle(null)
            }
            try {
              const defined = await listExpectedOutputContracts(scenarioId)
              setContracts(defined)
              setChecks(evaluateContracts(defined, working))
            } catch {
              setContracts([])
              setChecks([])
            }
          } catch (err) {
            setRecordingError(failureText(err))
          }
        }
        setRunning(false)
      }
    },
    [scenarioId],
  )

  const reset = useCallback(() => {
    setOutcomes(initialOutcomes())
    setHaltedAt(null)
    setPilotRun(null)
    setBundle(null)
    setChecks([])
    setActionItems([])
    setRecordingError(null)
  }, [])

  const state: GoldenPathRunState = {
    outcomes,
    running,
    activeStep,
    pilotRun,
    contracts,
    checks,
    actionItems,
    bundle,
    haltedAt,
    totalElapsedMs,
    recordingError,
  }

  return { ...state, run, reset, steps: GOLDEN_PATH_STEPS }
}
