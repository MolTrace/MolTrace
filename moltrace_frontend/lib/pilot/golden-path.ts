// Golden Path — one seeded arc, FID → dossier.
//
// This module drives the FIVE REAL endpoints of the arc and measures each one.
// It is deliberately the only place that knows the difference between a number
// the platform measured and a number it assumed.
//
// THREE RULES THIS FILE EXISTS TO HOLD
//
//  1. `POST /pilot/scenarios/{id}/run` IS A RECORDER, NOT AN EXECUTOR.
//     It never calls SpectraCheck, Regentry or Repho. Every step it writes is a
//     canned literal — `output_summary_json.expected_output` is the string
//     "safe summary", and `resource_links` is always `[]`. So we call it to MINT
//     the run record (evidence bundles and sign-off need a run to hang off), we
//     stash our own measurements in its `metadata_json`, and we NEVER render its
//     step summaries. `pilotStepSummaryIsCanned` below exists so a caller can
//     assert that at runtime. Record the arc; do not let it narrate the arc.
//
//  2. THE SERVER-SIDE CONTRACT CHECK SCORES THE CANNED STEPS, NOT THE ARC.
//     `golden_pilot_store.validate_pilot_run` reads
//     `matching_step.output_summary_json` — i.e. the literals from rule 1 — and
//     there is no route to write a real step output back. A `pass` from it
//     therefore means "the hardcoded shape carried the contracted fields", NOT
//     "the arc produced contracted output". Rendering that next to the real
//     panels would be the same defect one layer up, so `evaluateContracts()`
//     applies the SAME contract semantics to the REAL responses, client-side.
//     Routing real step outputs is a backend change — see the handoff, §7.
//
//  3. ROI HOURS ARE ASSUMED; ROI COUNTS AND THE ARC'S OWN CLOCK ARE MEASURED.
//     `total_minutes_saved` is Σ(events × a hardcoded per-task constant) — the
//     ORM column is honestly named `estimated_minutes_saved` and the API model
//     drops the qualifier. `splitRoi()` keeps the two apart so the UI cannot
//     accidentally present an assumption table as a measurement.

import { apiFetch } from "@/lib/api/client"
import type { components } from "@/src/lib/api/schema"

// ── wire types ────────────────────────────────────────────────────────────────
export type GoldenPilotScenario = components["schemas"]["GoldenPilotScenario"]
export type PilotRunDetail = components["schemas"]["PilotRunDetail"]
export type PilotRunStep = components["schemas"]["PilotRunStep"]
export type PilotRunCreate = components["schemas"]["PilotRunCreate"]
export type ExpectedOutputContract = components["schemas"]["ExpectedOutputContract"]
export type PilotEvidenceBundle = components["schemas"]["PilotEvidenceBundle"]
export type PilotModule = PilotRunStep["module"]
export type RoiSnapshot = components["schemas"]["RoiSnapshot"]
export type CrossModuleActionItem = components["schemas"]["CrossModuleActionItem"]
export type CrossModuleActionItemCreate = components["schemas"]["CrossModuleActionItemCreate"]
export type FIDProcessResult = components["schemas"]["FIDProcessResult"]
export type CandidateComparisonResult = components["schemas"]["CandidateComparisonResult"]
export type ImpurityAssessRequest = components["schemas"]["ImpurityAssessRequest"]
export type ImpurityAssessResult = components["schemas"]["ImpurityAssessResult"]
export type ReactionBoRunRequest = components["schemas"]["ReactionBayesianOptimizationRunRequest"]
export type ReactionBoRun = components["schemas"]["ReactionBayesianOptimizationRun"]
export type RegulatoryDossier = components["schemas"]["RegulatoryDossier"]
export type RegulatoryDossierCreate = components["schemas"]["RegulatoryDossierCreate"]
export type RegulatoryEvidenceLink = components["schemas"]["RegulatoryEvidenceLink"]
export type RegulatoryEvidenceLinkCreate = components["schemas"]["RegulatoryEvidenceLinkCreate"]

// ── the arc ───────────────────────────────────────────────────────────────────

/** The five steps, in order. `stepKey`/`module` match the backend's
 *  `MODULE_STEP_KEYS` vocabulary so an ExpectedOutputContract written against a
 *  scenario resolves onto the real step it contracts. */
export const GOLDEN_PATH_STEPS = [
  {
    key: "raw_fid_process",
    stepKey: "spectracheck_evidence_item",
    module: "spectracheck" as PilotModule,
    title: "Raw FID → spectrum",
    /** Narration must match what the endpoint returns, not what we wish it returned. */
    narration: "Vendor FID processed into a referenced spectrum with picked peaks.",
    endpoint: "raw-FID processing",
  },
  {
    key: "candidate_evidence",
    stepKey: "spectracheck_evidence_item",
    module: "spectracheck" as PilotModule,
    title: "Spectrum → structure evidence",
    // The deterministic verifier (`verify_structure`) has NO API route and is not
    // referenced anywhere in `src/nmrcheck/`. This step returns ranked candidate
    // evidence. Never narrate it as "the verifier confirmed the structure".
    narration: "Candidates ranked against the observed spectrum. This is ranked evidence, not a verifier verdict.",
    endpoint: "candidate comparison",
  },
  {
    key: "impurity_assess",
    stepKey: "regulatory_action_item",
    module: "regulatory_hub" as PilotModule,
    title: "Impurity assessment",
    narration: "Deterministic ICH/FDA engines. Every number carries its rule-set version.",
    endpoint: "impurity assessment",
  },
  {
    key: "bo_run",
    stepKey: "reaction_constraint",
    module: "reaction_optimization" as PilotModule,
    title: "Compliant design",
    narration: "Optimizer proposes under the active regulatory limits, and declines when every candidate breaches one.",
    endpoint: "reaction optimization",
  },
  {
    key: "dossier_evidence",
    stepKey: "cross_module_review_task",
    module: "cross_module" as PilotModule,
    title: "Dossier + provenance",
    narration: "The evidence links are what make this an arc rather than a fifth screen.",
    endpoint: "dossier evidence linking",
  },
] as const

export type GoldenPathStepKey = (typeof GOLDEN_PATH_STEPS)[number]["key"]

export type StepStatus = "pending" | "running" | "succeeded" | "failed" | "requires_review"

/** One executed step. `payload` is the endpoint's REAL response body — never a
 *  pilot step summary. `elapsedMs` is measured wall-clock, not an assumption. */
export type GoldenPathStepOutcome = {
  key: GoldenPathStepKey
  stepKey: string
  module: PilotModule
  status: StepStatus
  /** Epoch ms. Null until the step starts. */
  startedAt: number | null
  finishedAt: number | null
  /** Measured wall-clock for this step. Null while pending/running. */
  elapsedMs: number | null
  payload: unknown
  /** User-facing failure text. Never an HTTP status or endpoint path. */
  error: string | null
}

export function initialOutcomes(): GoldenPathStepOutcome[] {
  return GOLDEN_PATH_STEPS.map((s) => ({
    key: s.key,
    stepKey: s.stepKey,
    module: s.module,
    status: "pending" as StepStatus,
    startedAt: null,
    finishedAt: null,
    elapsedMs: null,
    payload: null,
    error: null,
  }))
}

/** Sum of the steps that actually ran. This is the demo's one genuinely measured
 *  duration — unlike `total_hours_saved`, nothing here is a constant. */
export function measuredArcElapsedMs(outcomes: GoldenPathStepOutcome[]): number | null {
  const ran = outcomes.filter((o) => o.elapsedMs != null)
  if (ran.length === 0) return null
  return ran.reduce((sum, o) => sum + (o.elapsedMs ?? 0), 0)
}

// ── the five real calls ───────────────────────────────────────────────────────

/** Frozen inputs for one arc. Sourced from the scenario's `required_inputs_json`
 *  where present so the same seeded arc replays identically. */
export type GoldenPathInputs = {
  archiveId: string
  smiles: string
  solvent: string | null
  candidatesText: string
  protonNmrText: string | null
  dailyDoseG: number
  route: ImpurityAssessRequest["route"]
  substanceType: ImpurityAssessRequest["substance_type"]
  durationMonths: number
  reactionProjectId: number | null
  dossierTitle: string
  productName: string | null
}

export const EMPTY_INPUTS: GoldenPathInputs = {
  archiveId: "",
  smiles: "",
  solvent: null,
  candidatesText: "",
  protonNmrText: null,
  dailyDoseG: 1,
  route: "oral",
  substanceType: "drug_substance",
  durationMonths: 120,
  reactionProjectId: null,
  dossierTitle: "Golden path dossier",
  productName: null,
}

function readString(v: unknown): string | null {
  return typeof v === "string" && v.trim() !== "" ? v.trim() : null
}
function readNumber(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v
  if (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v))) return Number(v)
  return null
}
function readEnum<T extends string>(v: unknown, allowed: readonly T[]): T | null {
  return typeof v === "string" && (allowed as readonly string[]).includes(v) ? (v as T) : null
}

const ROUTES = ["oral", "parenteral", "inhalation", "cutaneous"] as const
const SUBSTANCE_TYPES = ["drug_substance", "drug_product"] as const

/**
 * Seed the arc's inputs from the scenario's own `required_inputs_json`.
 *
 * The point of a golden path is that it replays identically, so the frozen
 * inputs come from the scenario record rather than from whatever the operator
 * last typed. Anything the scenario does not pin is left at its default for the
 * operator to supply — never guessed.
 */
export function inputsFromScenario(scenario: GoldenPilotScenario | null): GoldenPathInputs {
  if (scenario == null) return { ...EMPTY_INPUTS }
  const required = scenario.required_inputs_json ?? {}
  return {
    ...EMPTY_INPUTS,
    archiveId: readString(required.archive_id) ?? EMPTY_INPUTS.archiveId,
    smiles: readString(required.smiles) ?? EMPTY_INPUTS.smiles,
    solvent: readString(required.solvent),
    candidatesText: readString(required.candidates_text) ?? readString(required.smiles) ?? "",
    protonNmrText: readString(required.proton_nmr_text),
    dailyDoseG: readNumber(required.daily_dose_g) ?? EMPTY_INPUTS.dailyDoseG,
    route: readEnum(required.route, ROUTES) ?? EMPTY_INPUTS.route,
    substanceType: readEnum(required.substance_type, SUBSTANCE_TYPES) ?? EMPTY_INPUTS.substanceType,
    durationMonths: readNumber(required.duration_months) ?? EMPTY_INPUTS.durationMonths,
    reactionProjectId: readNumber(required.reaction_project_id),
    dossierTitle: readString(required.dossier_title) ?? `${scenario.title} — dossier`,
    productName: readString(required.product_name),
  }
}

/** Which frozen inputs the scenario did not pin. The arc cannot run without
 *  these, and the UI names them rather than failing mid-arc. */
export function missingInputs(inputs: GoldenPathInputs): string[] {
  const missing: string[] = []
  if (!inputs.archiveId) missing.push("Raw FID archive")
  if (!inputs.smiles) missing.push("Structure (SMILES)")
  if (!inputs.candidatesText) missing.push("Candidate structures")
  if (inputs.reactionProjectId == null) missing.push("Reaction project")
  return missing
}

/** `POST /raw-fid/{archive_id}/process` — form-encoded, operates on a registered
 *  archive rather than an ad-hoc upload, which is what makes the arc replayable. */
export async function processRawFid(inputs: GoldenPathInputs): Promise<FIDProcessResult> {
  const body = new URLSearchParams()
  body.set("smiles", inputs.smiles)
  if (inputs.solvent) body.set("solvent", inputs.solvent)
  return apiFetch<FIDProcessResult>(`/raw-fid/${encodeURIComponent(inputs.archiveId)}/process`, {
    method: "POST",
    body,
  })
}

/** `POST /candidates/compare/evidence` — multipart. Returns ranked candidate
 *  evidence. NOT the deterministic verifier: that has no route (handoff §2). */
export async function compareCandidateEvidence(
  inputs: GoldenPathInputs,
  protonNmrText: string | null,
): Promise<CandidateComparisonResult> {
  const fd = new FormData()
  fd.set("candidates_text", inputs.candidatesText)
  const proton = protonNmrText ?? inputs.protonNmrText
  if (proton) fd.set("proton_nmr_text", proton)
  if (inputs.solvent) fd.set("solvent", inputs.solvent)
  return apiFetch<CandidateComparisonResult>("/candidates/compare/evidence", { method: "POST", body: fd })
}

/** `POST /regulatory/impurities/assess` — version-pinned rule engine, never an LLM. */
export async function assessImpurities(inputs: GoldenPathInputs): Promise<ImpurityAssessResult> {
  const payload: ImpurityAssessRequest = {
    daily_dose_g: inputs.dailyDoseG,
    route: inputs.route,
    substance_type: inputs.substanceType,
    duration_months: inputs.durationMonths,
    // Pinned, not defaulted: the golden path is a fixed reproducible scenario, and the
    // authority chooses the Category-1 nitrosamine limit (FDA 26.5 vs EMA 18 ng/day),
    // so leaving it implicit would let a server-side default change the pilot's numbers.
    authority: "FDA",
  }
  return apiFetch<ImpurityAssessResult>("/regulatory/impurities/assess", { method: "POST", body: payload })
}

/** `POST /reaction-projects/{id}/optimization/bo/run`. A run whose every candidate
 *  breaches a hard limit reports `requires_review`, not `succeeded`. */
export async function runCompliantDesign(reactionProjectId: number): Promise<ReactionBoRun> {
  const payload: ReactionBoRunRequest = {
    algorithm: "gaussian_process_ei",
    batch_size: 5,
    cost_aware: false,
    safety_aware: true,
    include_negative_outcomes: false,
    candidate_count: 64,
  }
  return apiFetch<ReactionBoRun>(
    `/reaction-projects/${encodeURIComponent(String(reactionProjectId))}/optimization/bo/run`,
    { method: "POST", body: payload },
  )
}

export type DossierStepResult = {
  dossier: RegulatoryDossier
  links: RegulatoryEvidenceLink[]
}

/** `POST /regulatory/dossiers` then one `evidence-links` call per upstream step.
 *  The links are the provenance — a dossier with no links is a fifth screen. */
export async function createDossierWithProvenance(
  inputs: GoldenPathInputs,
  upstream: GoldenPathStepOutcome[],
): Promise<DossierStepResult> {
  const create: RegulatoryDossierCreate = {
    title: inputs.dossierTitle,
    product_name: inputs.productName,
    max_daily_dose_g: inputs.dailyDoseG,
    substance_type: inputs.substanceType,
    route: inputs.route,
    status: "draft",
    ...(inputs.reactionProjectId != null ? { reaction_project_id: inputs.reactionProjectId } : {}),
  }
  const dossier = await apiFetch<RegulatoryDossier>("/regulatory/dossiers", { method: "POST", body: create })

  const links: RegulatoryEvidenceLink[] = []
  for (const step of upstream) {
    if (step.status !== "succeeded" && step.status !== "requires_review") continue
    const spec = GOLDEN_PATH_STEPS.find((s) => s.key === step.key)
    if (!spec) continue
    const link: RegulatoryEvidenceLinkCreate = {
      evidence_type: evidenceTypeForStep(step.key),
      title: spec.title,
      summary: spec.narration,
      status: "needs_review",
      metadata_json: {
        golden_path_step: step.key,
        // The step's own measured clock, carried onto the evidence record.
        elapsed_ms: step.elapsedMs,
        step_status: step.status,
      },
    }
    links.push(
      await apiFetch<RegulatoryEvidenceLink>(
        `/regulatory/dossiers/${encodeURIComponent(String(dossier.id))}/evidence-links`,
        { method: "POST", body: link },
      ),
    )
  }
  return { dossier, links }
}

function evidenceTypeForStep(key: GoldenPathStepKey): RegulatoryEvidenceLinkCreate["evidence_type"] {
  switch (key) {
    case "raw_fid_process":
      return "analytical_artifact"
    case "candidate_evidence":
      return "unified_evidence"
    case "impurity_assess":
      return "qc_assessment"
    case "bo_run":
      return "reaction_report"
    default:
      return "other"
  }
}

// ── cross-module continuity ───────────────────────────────────────────────────

/** The handoff chain: 2→3 (spectracheck → regentry) and 3→4 (regentry → repho).
 *  Each item names a real resource so the command-center card can deep-link it. */
export async function createActionItem(payload: CrossModuleActionItemCreate): Promise<CrossModuleActionItem> {
  return apiFetch<CrossModuleActionItem>("/cross-module/action-items", { method: "POST", body: payload })
}

export async function listActionItems(limit = 50): Promise<CrossModuleActionItem[]> {
  return apiFetch<CrossModuleActionItem[]>(`/cross-module/action-items?limit=${encodeURIComponent(String(limit))}`)
}

/**
 * Deep link for one end of a cross-module handoff.
 *
 * Returns null when the resource type has no viewer that can focus that record —
 * a link that lands on an unfiltered list is not an audit trail, and a link to a
 * route that does not exist is worse than a plain label. Every href below was
 * checked against the App Router tree.
 */
export function actionItemResourceHref(
  resourceType: string | null | undefined,
  resourceId: number | null | undefined,
): string | null {
  if (!resourceType || resourceId == null) return null
  switch (resourceType) {
    case "dossier":
      return `/regulatory/dossiers/${resourceId}`
    case "reaction_project":
      return `/reactions/${resourceId}`
    case "action_item":
      return `/regulatory/action-queue?item=${resourceId}`
    default:
      // Notably `evidence_link`: it is a real record, but it is rendered inside
      // its dossier and has no addressable view of its own, so the dossier end
      // of the handoff carries the link instead.
      return null
  }
}

// ── pilot recording (rule 1) ──────────────────────────────────────────────────

export async function listScenarios(limit = 25): Promise<GoldenPilotScenario[]> {
  return apiFetch<GoldenPilotScenario[]>(`/pilot/scenarios?limit=${encodeURIComponent(String(limit))}`)
}

export async function listExpectedOutputContracts(scenarioId: number): Promise<ExpectedOutputContract[]> {
  return apiFetch<ExpectedOutputContract[]>(
    `/pilot/scenarios/${encodeURIComponent(String(scenarioId))}/expected-output-contracts`,
  )
}

export async function listPilotRuns(limit = 10): Promise<PilotRunDetail[]> {
  return apiFetch<PilotRunDetail[]>(`/pilot/runs?limit=${encodeURIComponent(String(limit))}`)
}

export async function getPilotRun(pilotRunId: number): Promise<PilotRunDetail> {
  return apiFetch<PilotRunDetail>(`/pilot/runs/${encodeURIComponent(String(pilotRunId))}`)
}

/**
 * Mint the run record for an arc we already executed ourselves.
 *
 * There is no `POST /pilot/runs`: `POST /pilot/scenarios/{id}/run` is the only
 * creation route, and it writes canned steps as a side effect. We accept those
 * steps as an inert anchor and carry the REAL measurements in `metadata_json`,
 * which is a free-form dict the recorder passes through untouched.
 */
export async function recordArc(
  scenarioId: number,
  outcomes: GoldenPathStepOutcome[],
  extra: Omit<PilotRunCreate, "metadata_json" | "run_label"> & { run_label?: string } = {},
): Promise<PilotRunDetail> {
  const payload: PilotRunCreate = {
    run_label: extra.run_label ?? "Golden path arc",
    ...(extra.tenant_id != null ? { tenant_id: extra.tenant_id } : {}),
    ...(extra.project_id != null ? { project_id: extra.project_id } : {}),
    ...(extra.sample_id != null ? { sample_id: extra.sample_id } : {}),
    metadata_json: {
      // Named so a reader of the raw record cannot mistake these for the
      // recorder's own canned steps.
      golden_path_executed_client_side: true,
      measured_total_elapsed_ms: measuredArcElapsedMs(outcomes),
      steps: outcomes.map((o) => ({
        step: o.key,
        status: o.status,
        elapsed_ms: o.elapsedMs,
        started_at: o.startedAt != null ? new Date(o.startedAt).toISOString() : null,
        finished_at: o.finishedAt != null ? new Date(o.finishedAt).toISOString() : null,
      })),
    },
  }
  return apiFetch<PilotRunDetail>(`/pilot/scenarios/${encodeURIComponent(String(scenarioId))}/run`, {
    method: "POST",
    body: payload,
  })
}

export async function createEvidenceBundle(pilotRunId: number, title: string): Promise<PilotEvidenceBundle> {
  return apiFetch<PilotEvidenceBundle>(`/pilot/runs/${encodeURIComponent(String(pilotRunId))}/evidence-bundle`, {
    method: "POST",
    body: { title, status: "ready_for_review" },
  })
}

export async function listEvidenceBundles(pilotRunId: number): Promise<PilotEvidenceBundle[]> {
  return apiFetch<PilotEvidenceBundle[]>(`/pilot/runs/${encodeURIComponent(String(pilotRunId))}/evidence-bundle`)
}

/**
 * True when a recorded pilot step carries the recorder's canned literal rather
 * than engine output. Exported so a caller can prove it never renders one.
 *
 * The recorder writes `expected_output: "safe summary"` and an always-empty
 * `resource_links` on every step it emits.
 */
export function pilotStepSummaryIsCanned(step: Pick<PilotRunStep, "output_summary_json">): boolean {
  const summary = step.output_summary_json
  if (summary == null || typeof summary !== "object") return false
  return (summary as Record<string, unknown>).expected_output === "safe summary"
}

/** One step as it actually ran, read back off a stored run. */
export type RecordedArcStep = {
  step: string
  status: StepStatus
  elapsedMs: number | null
}

export type RecordedArc = {
  steps: RecordedArcStep[]
  totalElapsedMs: number | null
}

const STEP_STATUSES: readonly StepStatus[] = ["pending", "running", "succeeded", "failed", "requires_review"]

/**
 * Read the arc a run actually executed, from `metadata_json`.
 *
 * Deliberately NOT `run.steps`: every step the recorder emits is written with
 * `status: "succeeded"` regardless of what happened, so counting those would
 * report five green steps for an arc that never ran. Returns null when the run
 * carries no client-executed record — unknown, never "it all passed".
 */
export function readRecordedArc(run: Pick<PilotRunDetail, "metadata_json"> | null | undefined): RecordedArc | null {
  const metadata = run?.metadata_json
  if (metadata == null || typeof metadata !== "object") return null
  const record = metadata as Record<string, unknown>
  if (record.golden_path_executed_client_side !== true) return null
  const rawSteps = Array.isArray(record.steps) ? record.steps : []
  const steps: RecordedArcStep[] = []
  for (const raw of rawSteps) {
    if (raw == null || typeof raw !== "object" || Array.isArray(raw)) continue
    const row = raw as Record<string, unknown>
    const step = typeof row.step === "string" ? row.step : null
    if (step == null) continue
    const status = STEP_STATUSES.find((s) => s === row.status) ?? "pending"
    const elapsed = typeof row.elapsed_ms === "number" && Number.isFinite(row.elapsed_ms) ? row.elapsed_ms : null
    steps.push({ step, status, elapsedMs: elapsed })
  }
  const total = record.measured_total_elapsed_ms
  return {
    steps,
    totalElapsedMs: typeof total === "number" && Number.isFinite(total) ? total : null,
  }
}

// ── contract evaluation against the REAL responses (rule 2) ───────────────────

export type ContractCheckStatus = "pass" | "fail" | "warning" | "not_assessed"

export type ContractCheck = {
  contractId: number
  stepKey: string
  targetModule: PilotModule
  status: ContractCheckStatus
  /** The step this contract resolved onto, or null when nothing matched. */
  matchedStep: GoldenPathStepKey | null
  missingRequiredFields: string[]
  forbiddenFieldsPresent: string[]
  statusMismatch: boolean
}

/** Mirrors the backend's `_has_path`: dotted path, every part must be a key of a
 *  plain object. Kept identical so a client-side check means the same thing a
 *  server-side one would, once real step outputs are routable. */
export function hasPath(value: unknown, path: string): boolean {
  let current: unknown = value
  for (const part of path.split(".")) {
    if (current == null || typeof current !== "object" || Array.isArray(current)) return false
    if (!Object.prototype.hasOwnProperty.call(current, part)) return false
    current = (current as Record<string, unknown>)[part]
  }
  return true
}

/**
 * Apply the scenario's expected-output contracts to the arc's REAL responses.
 *
 * Deliberately NOT `POST /pilot/runs/{id}/validate`: that endpoint scores the
 * recorder's canned step summaries (see rule 2 at the top of this file), so its
 * verdict is about a hardcoded literal, not about the run the user just watched.
 */
export function evaluateContracts(
  contracts: ExpectedOutputContract[],
  outcomes: GoldenPathStepOutcome[],
): ContractCheck[] {
  return contracts.map((contract) => {
    const matched =
      outcomes.find((o) => o.stepKey === contract.step_key) ??
      outcomes.find((o) => o.module === contract.target_module) ??
      null

    const actual = matched?.payload ?? null
    const required = contract.required_fields_json ?? []
    const forbidden = contract.forbidden_fields_json ?? []
    const expectedStatuses = contract.expected_statuses_json ?? []

    const missingRequiredFields = matched == null ? [...required] : required.filter((f) => !hasPath(actual, f))
    const forbiddenFieldsPresent = matched == null ? [] : forbidden.filter((f) => hasPath(actual, f))
    const statusMismatch =
      expectedStatuses.length > 0 && (matched == null || !expectedStatuses.includes(matched.status))

    let status: ContractCheckStatus = "pass"
    if (matched == null || matched.status === "pending") {
      status = "not_assessed"
    } else if (missingRequiredFields.length > 0 || forbiddenFieldsPresent.length > 0 || statusMismatch) {
      status = "fail"
    } else if (matched.status === "requires_review") {
      // A contracted step that the engine itself flagged for review is not a
      // clean pass — `human_review_required` is never styled away.
      status = "warning"
    }

    return {
      contractId: contract.id,
      stepKey: contract.step_key,
      targetModule: contract.target_module,
      status,
      matchedStep: matched?.key ?? null,
      missingRequiredFields,
      forbiddenFieldsPresent,
      statusMismatch,
    }
  })
}

// ── ROI: measured vs estimated (rule 3) ───────────────────────────────────────

export type RoiCount = { key: string; label: string; value: number }

export type RoiSplit = {
  /** Real event counts. Safe to present as measured. */
  measuredCounts: RoiCount[]
  /**
   * Σ(events × a hardcoded, admin-editable per-task constant). NOT a measured
   * duration. Null when no snapshot exists — a missing snapshot must render as
   * "no data", never as `0`.
   */
  estimatedHoursSaved: number | null
  /** The arc's own wall-clock. Genuinely measured, unlike the hours above. */
  measuredArcElapsedMs: number | null
  /** Warnings the snapshot carried, rendered above the figures they qualify. */
  warnings: string[]
  dataMode: RoiSnapshot["data_mode"] | null
}

/** Copy for the hours figure. Kept here so every surface says the same thing. */
export const ESTIMATED_HOURS_QUALIFIER = "Estimated"
export const ESTIMATED_HOURS_BASIS =
  "Not a measured duration: each completed task contributes a fixed time-saved constant set in your automation-task settings, and those constants are summed. The counts beside it are real event counts."
/** Where a reader can go and check the constants for themselves. `/roi` renders
 *  every automation-task definition with its `default_minutes_saved` — i.e. the
 *  actual assumption table the hours figure is summed from. There is no
 *  `/settings` route, and a dead link here would defeat the disclosure. */
export const AUTOMATION_TASK_SETTINGS_HREF = "/roi"

export function splitRoi(snapshot: RoiSnapshot | null, arcElapsedMs: number | null): RoiSplit {
  if (snapshot == null) {
    return {
      measuredCounts: [],
      estimatedHoursSaved: null,
      measuredArcElapsedMs: arcElapsedMs,
      warnings: [],
      dataMode: null,
    }
  }
  return {
    measuredCounts: [
      { key: "tasks_automated", label: "Tasks automated", value: snapshot.tasks_automated },
      { key: "analyses_completed", label: "Analyses completed", value: snapshot.analyses_completed },
      { key: "reports_generated", label: "Reports generated", value: snapshot.reports_generated },
      { key: "workflows_completed", label: "Workflows completed", value: snapshot.workflows_completed },
      { key: "review_tasks_completed", label: "Reviews completed", value: snapshot.review_tasks_completed },
      { key: "qc_warnings", label: "QC warnings", value: snapshot.qc_warnings },
      { key: "failed_jobs", label: "Failed jobs", value: snapshot.failed_jobs },
    ],
    estimatedHoursSaved: snapshot.total_hours_saved,
    measuredArcElapsedMs: arcElapsedMs,
    warnings: snapshot.warnings ?? [],
    dataMode: snapshot.data_mode,
  }
}

export async function fetchRoiSnapshot(): Promise<RoiSnapshot | null> {
  try {
    return await apiFetch<RoiSnapshot>("/analytics/roi?scope=global")
  } catch {
    // A missing snapshot is "no data", not zero. Callers render the dash.
    return null
  }
}

/** Format a measured duration. Sub-second stays in ms so a fast arc reads as fast. */
export function formatElapsed(ms: number | null): string {
  if (ms == null || !Number.isFinite(ms)) return "—"
  if (ms < 1000) return `${Math.round(ms)} ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`
  const minutes = Math.floor(ms / 60_000)
  const seconds = Math.round((ms % 60_000) / 1000)
  return `${minutes} min ${seconds} s`
}
