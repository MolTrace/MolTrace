"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react"
import { ArrowLeft, ChevronDown, ExternalLink, FlaskConical, Info } from "lucide-react"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { MlModelProvenanceSummary } from "@/components/ml/ml-model-provenance-summary"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { apiFetch } from "@/lib/api/client"
import { formatStableUtcDateTime } from "@/lib/utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"

const reactionProjectTabClass =
  "font-mono text-xs sm:text-sm data-[state=active]:[background-color:var(--mt-violet)] data-[state=active]:[color:#EBF4F8] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Separator } from "@/components/ui/separator"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Switch } from "@/components/ui/switch"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ModelDiagnosticsCard } from "@/components/reaction-optimization/model-diagnostics-card"
import { ReactionResponseOverview } from "@/components/reaction-optimization/reaction-response-overview"
import { ReactionRegulatoryConstraintsPanel } from "@/components/reaction-optimization/reaction-regulatory-constraints-panel"
import {
  ReactionStudioCompoundLinkingPanel,
  ReactionStudioCompoundLinkSummary,
} from "@/components/reaction-optimization/reaction-studio-compound-linking-panel"
import { ReactionStudioKnowledgeLinksCard } from "@/components/knowledge/knowledge-links-integration"
import { ReactionResponsePreview } from "@/components/reaction-optimization/reaction-response-preview"
import {
  countClosedLoopOutcomeFieldKeys,
  trackReactionAdvisorReviewSaved,
  trackReactionAdvisorRunCompleted,
  trackReactionAdvisorRunStarted,
  trackReactionBenchmarkRunCompleted,
  trackReactionBenchmarkRunStarted,
  trackReactionBoAdvisorComparisonRun,
  trackReactionBoRunCompleted,
  trackReactionBoRunStarted,
  trackReactionCostProfileSaved,
  trackReactionExperimentAdded,
  trackReactionMechanisticHypothesisCreated,
  trackReactionObjectiveProfileSaved,
  trackReactionOptimizationRunCompleted,
  trackReactionOptimizationRunStarted,
  trackReactionPriorAdded,
  trackReactionRecommendationCritiqued,
  trackReactionOutcomeRecorded,
  trackReactionRecommendationApproved,
  trackReactionAnalyticalResultLinked,
  trackReactionCycleDecisionSaved,
  trackReactionExecutionBatchCreated,
  trackReactionExecutionItemCompleted,
  trackReactionExecutionItemFailed,
  trackReactionExecutionItemStarted,
  trackReactionRecommendationBatchCreated,
  trackReactionRecommendationConvertedToExperiment,
  trackReactionRecommendationRejected,
  trackReactionOutcomeConfirmed,
  trackReactionOutcomeExtractionRun,
  trackReactionOptimizationCycleCreated,
  trackReactionSafetyProfileSaved,
  trackSpectracheckLinkedToReaction,
} from "@/src/lib/analytics/analytics-client"

const VARIABLES_TOOLTIP =
  "Reaction variables define the condition space for experiment planning and recommendation."

const OBJECTIVE_PROFILE_TOOLTIP =
  "Defines what the optimizer should improve, such as yield, selectivity, impurity, conversion, or a weighted multi-objective score."

const DESIGN_SPACE_TOOLTIP =
  "Defines the reaction conditions the optimizer is allowed to explore."

const COST_AWARE_TOOLTIP =
  "Cost-aware optimization penalizes expensive or unavailable conditions so recommendations remain practical."

const SAFETY_CONSTRAINTS_TOOLTIP =
  "Safety constraints block or warn against reaction conditions that violate user-defined limits."

const OBJECTIVE_TYPE_OPTIONS = [
  "maximize_yield",
  "maximize_selectivity",
  "minimize_impurity",
  "maximize_conversion",
  "multi_objective",
  "custom",
] as const

const BO_ALGORITHM_OPTIONS = [
  "gaussian_process_ei",
  "gaussian_process_ucb",
  "random_forest_ei",
  "tpe_like",
  "rule_based_fallback",
] as const

const ADVISOR_MODE_OPTIONS = [
  "rule_based_mechanistic",
  "llm_guided_placeholder",
  "hybrid_bo_llm",
] as const

const MECHANISTIC_CONFIDENCE_LABELS = ["low", "medium", "high", "speculative"] as const

const MECHANISTIC_HYPOTHESIS_STATUS = ["proposed", "accepted", "rejected", "revised"] as const

const MECHANISTIC_HYPOTHESES_TOOLTIP =
  "Mechanistic hypotheses document the chemical reasoning behind optimization decisions and can be revised as new experiments are added."

const LITERATURE_PRIOR_SOURCE_TYPES = [
  "user_note",
  "literature_reference",
  "internal_history",
  "model_prior",
  "rule_based_prior",
] as const

const LITERATURE_PRIORS_TOOLTIP =
  "Reaction priors capture literature, internal history, or user-provided mechanistic context that can inform optimization decisions."

const BO_ADVISOR_COMPARISON_TOOLTIP =
  "Comparison highlights where mathematical optimization and chemical reasoning agree or disagree. Final experiment scheduling still requires human review."

const ADVISOR_REVIEW_DECISIONS = [
  "accept_for_review",
  "request_modification",
  "reject_advisor_output",
  "defer",
] as const

const BENCHMARK_TOOLTIP =
  "Benchmarking evaluates how an optimizer would perform on completed or enumerated reaction data. It is used for validation, not proof of universal superiority."

const ADVISOR_TAB_TOOLTIP =
  "The Advisor critiques optimization recommendations using mechanistic, cost, safety, and practical reasoning. It does not autonomously schedule experiments."

const EXECUTION_TAB_TOOLTIP =
  "Execution connects approved recommendations to planned experiments, analytical results, confirmed outcomes, and the next optimization cycle. Human confirmation is required."

const APPROVED_RECOMMENDATIONS_CONVERT_TOOLTIP =
  "Approved recommendations can be converted into planned experiments. This does not mean the experiment has been performed."

const EXECUTION_BOARD_TOOLTIP =
  "Execution status is manually updated by the user. MolTrace does not assume an experiment was performed until it is marked completed."

const ANALYTICAL_RESULTS_INTAKE_TOOLTIP =
  "Analytical results connect reaction execution to SpectraCheck, LC-MS, NMR, or chromatography evidence. They support outcome extraction but require human confirmation."

const ANALYTICAL_RESULT_TYPE_OPTIONS = ["nmr", "lcms", "hrms", "msms", "hplc", "uplc", "qnmr", "other"] as const

const OUTCOME_EXTRACTION_METHOD_OPTIONS = [
  "rule_based",
  "lcms_area",
  "nmr_purity",
  "unified_spectracheck",
  "manual",
] as const

const OPTIMIZATION_CYCLE_TIMELINE_TOOLTIP =
  "Optimization cycles track how each batch of experiments updates the model and informs the next round of recommendations."

const REACTION_OPTIMIZATION_CYCLE_STATUS_OPTIONS = [
  "draft",
  "running",
  "completed",
  "requires_review",
  "failed",
] as const

const REACTION_OPTIMIZATION_CYCLE_DECISION_OPTIONS = [
  "continue_optimization",
  "pause",
  "stop_success",
  "stop_insufficient_progress",
  "revise_design_space",
  "revise_objective",
  "requires_review",
] as const

/** Dedupe mirrored list fields commonly returned alongside `*_json` copies (e.g. warnings vs warnings_json). */
function mergeDuplicateApiListPair(record: Record<string, unknown>, a: string, b: string): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const key of [a, b] as const) {
    const raw = record[key]
    if (!Array.isArray(raw)) continue
    for (const item of raw) {
      const s = typeof item === "string" ? item.trim() : String(item).trim()
      if (!s || seen.has(s)) continue
      seen.add(s)
      out.push(s)
    }
  }
  return out
}

function optimizationCycleDecisionRecordFromCycle(cycle: Record<string, unknown>): Record<string, unknown> | null {
  const md = cycle.metadata_json
  if (!isRecord(md)) return null
  const ld = md.latest_decision
  return isRecord(ld) ? ld : null
}

function mergeOutcomeExtractionNotes(run: Record<string, unknown>): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const key of ["notes", "notes_json"] as const) {
    const raw = run[key]
    if (!Array.isArray(raw)) continue
    for (const item of raw) {
      const s = typeof item === "string" ? item.trim() : String(item).trim()
      if (!s || seen.has(s)) continue
      seen.add(s)
      out.push(s)
    }
  }
  return out
}

function mergeOutcomeExtractionWarnings(run: Record<string, unknown>): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const key of ["warnings", "warnings_json"] as const) {
    const raw = run[key]
    if (!Array.isArray(raw)) continue
    for (const item of raw) {
      const s = typeof item === "string" ? item.trim() : String(item).trim()
      if (!s || seen.has(s)) continue
      seen.add(s)
      out.push(s)
    }
  }
  return out
}

/** Map proposed_outcome_json value to a concise text input string. */
function proposedOutcomeScalarToInput(raw: unknown): string {
  if (typeof raw === "number" && Number.isFinite(raw)) return String(raw)
  if (typeof raw === "string" && raw.trim()) return raw.trim()
  return ""
}

type ExplorationState = "free" | "fixed" | "excluded"

type ReactionExecutionPlanningRow = {
  recommendation_id: number
  experiment_id: number
  experiment_status: string
  execution_item_id: number | null
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return v != null && typeof v === "object" && !Array.isArray(v)
}

function readNum(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v
  return null
}

function fmtIso(iso: unknown): string {
  if (typeof iso !== "string" || !iso.trim()) return "—"
  return formatStableUtcDateTime(iso)
}

/** Convert `<input type="datetime-local">` value to ISO-8601 for POST/PATCH batch planned_start / planned_end. */
function plannedDatetimeLocalInputToIsoOrUndefined(value: string): string | undefined {
  const t = value.trim()
  if (!t) return undefined
  const augmented = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(t) ? `${t}:00` : t
  const ms = Date.parse(augmented)
  if (Number.isNaN(ms)) return undefined
  return new Date(ms).toISOString()
}

/** Checklist progress label for execution items (array of objects with done-like flags). */
function executionItemChecklistProgressLabel(item: Record<string, unknown>): string {
  const raw = item.checklist_json
  if (!Array.isArray(raw) || raw.length === 0) return "—"
  let done = 0
  for (const x of raw) {
    if (!isRecord(x)) continue
    if (x.done === true || x.completed === true || x.checked === true) done += 1
  }
  return `${done}/${raw.length}`
}

function parseExperimentYield(exp: Record<string, unknown>): number | null {
  return readOutcomeNumber(exp, "yield_percent")
}

function readOutcomeNumber(exp: Record<string, unknown>, field: string): number | null {
  const outcome = exp.outcome
  if (isRecord(outcome)) {
    const v = readNum(outcome[field])
    if (v != null) return v
  }
  const oj = exp.outcome_json
  if (isRecord(oj)) {
    const v = readNum(oj[field])
    if (v != null) return v
  }
  return null
}

function formatAllowedValuesDisplay(raw: unknown): string {
  if (raw == null) return "—"
  if (Array.isArray(raw)) return raw.map((x) => String(x)).join(", ")
  if (typeof raw === "object") return JSON.stringify(raw)
  return String(raw)
}

function formatDefaultDisplay(raw: unknown): string {
  if (raw == null) return "—"
  if (typeof raw === "boolean") return raw ? "true" : "false"
  if (typeof raw === "number" && Number.isFinite(raw)) return String(raw)
  return String(raw)
}

function jsonPreview(raw: unknown, maxChars = 800): string {
  try {
    const s = JSON.stringify(raw, null, 2)
    if (s.length <= maxChars) return s
    return `${s.slice(0, maxChars)}…`
  } catch {
    return String(raw)
  }
}

/** Display strings aligned with ReactionRecommendationLabel — no claims of global optimality. */
const RECOMMENDATION_LABEL_DISPLAY: Record<string, string> = {
  recommended_next_experiment: "recommended next experiment",
  promising_condition: "promising condition",
  requires_human_review: "requires human review",
  exploratory_condition: "exploratory condition",
  control_condition: "control condition",
  insufficient_data: "insufficient data",
}

function formatRecommendationLabel(raw: unknown): string {
  if (typeof raw !== "string" || !raw.trim()) return "—"
  return RECOMMENDATION_LABEL_DISPLAY[raw] ?? raw
}

/** Combine parallel list fields returned by the API (e.g. warnings vs warnings_json). */
/** True if outcome_json includes at least one numeric outcome field (excludes free-text notes). */
function outcomeJsonHasNumericMetrics(oj: Record<string, unknown>): boolean {
  const keys = [
    "yield_percent",
    "conversion_percent",
    "selectivity_percent",
    "impurity_percent",
    "isolated_yield_percent",
    "lcms_area_percent",
    "nmr_purity_percent",
  ]
  return keys.some((k) => {
    const v = oj[k]
    return typeof v === "number" && Number.isFinite(v)
  })
}

function mergeRunStringLists(...sources: unknown[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const src of sources) {
    if (!Array.isArray(src)) continue
    for (const x of src) {
      if (typeof x !== "string") continue
      const t = x.trim()
      if (!t || seen.has(t)) continue
      seen.add(t)
      out.push(t)
    }
  }
  return out
}

/** Read first present metadata field (GET /reaction-experiments/{id}/evidence `metadata`). */
function pickMetadataField(md: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = md[k]
    if (typeof v === "string" && v.trim()) return v.trim()
    if (typeof v === "number" && Number.isFinite(v)) return String(v)
    if (typeof v === "boolean") return v ? "true" : "false"
  }
  return "—"
}

/** Summary lines for reaction experiment evidence — no full SpectraCheck payload. */
function reactionEvidenceSummary(ev: Record<string, unknown>): {
  linkedSessionId: number | null
  evidenceRecordCount: number
  sampleId: string
  unifiedEvidenceStatus: string
  reportStatus: string
  qcStatus: string
} {
  const md = isRecord(ev.metadata) ? ev.metadata : {}
  const records = Array.isArray(ev.evidence_records) ? ev.evidence_records : []
  const fromMeta = readNum(md.evidence_count)
  return {
    linkedSessionId: readNum(ev.linked_spectracheck_session_id),
    evidenceRecordCount: fromMeta ?? records.length,
    sampleId: pickMetadataField(md, ["sample_id"]),
    unifiedEvidenceStatus: pickMetadataField(md, [
      "unified_evidence_status",
      "readiness_status",
      "unified_status",
    ]),
    reportStatus: pickMetadataField(md, ["report_status"]),
    qcStatus: pickMetadataField(md, ["qc_status"]),
  }
}

function summarizeConditions(cj: unknown): string {
  if (!isRecord(cj)) return "—"
  const keys = Object.keys(cj).slice(0, 6)
  if (keys.length === 0) return "—"
  return keys.map((k) => `${k}: ${String((cj as Record<string, unknown>)[k])}`).join("; ")
}

function bestOutcomeLabel(objective: string | undefined, experiments: Record<string, unknown>[]): string {
  const completed = experiments.filter((e) => e.status === "completed")
  if (completed.length === 0) return "No completed experiments yet."
  const yields = completed.map(parseExperimentYield).filter((x): x is number => x != null)
  if (objective === "maximize_yield" || objective === "multi_objective" || !objective) {
    if (yields.length === 0) return "No numeric yield_percent recorded on completed runs."
    const best = Math.max(...yields)
    return `Highest recorded yield_percent among completed experiments: ${best}% (lab-dependent; not proof of global optimum).`
  }
  return `Review outcomes on completed experiments for objective ${objective}.`
}

function parseExplorationState(v: unknown): ExplorationState | null {
  if (v === "free" || v === "fixed" || v === "excluded") return v
  if (typeof v !== "string") return null
  const s = v.trim().toLowerCase()
  if (s === "free" || s === "fixed" || s === "excluded") return s
  return null
}

/** Normalize GET /design-space payloads (array root or wrapped entries). */
function parseDesignSpaceEntries(raw: unknown): Record<number, ExplorationState> {
  const out: Record<number, ExplorationState> = {}
  let rows: unknown[] = []
  if (Array.isArray(raw)) rows = raw
  else if (isRecord(raw)) {
    if (Array.isArray(raw.entries)) rows = raw.entries
    else if (Array.isArray(raw.variable_states)) rows = raw.variable_states
    else if (Array.isArray(raw.design_space_entries)) rows = raw.design_space_entries
  }
  for (const row of rows) {
    if (!isRecord(row)) continue
    const id = readNum(row.reaction_variable_id ?? row.variable_id ?? row.id)
    if (id == null) continue
    let st =
      parseExplorationState(row.exploration_state) ??
      parseExplorationState(row.state)
    if (st == null) {
      if (row.is_fixed === true) st = "fixed"
      else if (row.is_excluded === true) st = "excluded"
      else st = "free"
    }
    out[id] = st
  }
  return out
}

function buildExplorationMap(
  variableRecords: Record<string, unknown>[],
  dsRaw: unknown,
): Record<number, ExplorationState> {
  const fromApi = parseDesignSpaceEntries(dsRaw)
  const map: Record<number, ExplorationState> = { ...fromApi }
  for (const v of variableRecords) {
    const id = readNum(v.id)
    if (id == null) continue
    if (map[id] === undefined) map[id] = "free"
  }
  return map
}

function constraintsTextFromField(raw: unknown): string {
  if (raw == null) return ""
  if (typeof raw === "string") return raw
  try {
    return JSON.stringify(raw, null, 2)
  } catch {
    return String(raw)
  }
}

/** Serialize textarea for JSON/object API fields — empty → null. */
function jsonFieldFromText(text: string): unknown {
  const t = text.trim()
  if (!t) return null
  try {
    return JSON.parse(t) as unknown
  } catch {
    return t
  }
}

function readBoRunId(r: Record<string, unknown>): string {
  const v = r.bo_run_id ?? r.id ?? r.run_id
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  if (typeof v === "string" && v.trim()) return v.trim()
  return "—"
}

function readMetadataBool(rec: unknown, key: string): boolean {
  if (!isRecord(rec)) return false
  const mj = rec.metadata_json
  const md = rec.metadata
  if (isRecord(mj) && mj[key] === true) return true
  if (isRecord(md) && md[key] === true) return true
  return false
}

function literaturePriorCitationLine(citation: unknown): string {
  if (typeof citation === "string" && citation.trim()) return citation.trim()
  return "No citation provided."
}

function advisorRunReviewFromRecord(raw: unknown): Record<string, unknown> | null {
  if (!isRecord(raw)) return null
  const mdj = raw.metadata_json
  if (isRecord(mdj) && isRecord(mdj.review)) return mdj.review
  const md = raw.metadata
  if (isRecord(md) && isRecord(md.review)) return md.review
  return null
}

function LiteraturePriorRelevanceTags({ tags }: { tags: unknown }) {
  if (Array.isArray(tags) && tags.length > 0 && tags.every((t) => typeof t === "string")) {
    return (
      <div className="flex flex-wrap gap-1">
        {(tags as string[]).map((t, ti) => (
          <Badge key={`${ti}-${t}`} variant="outline" className="text-[10px] font-normal">
            {t}
          </Badge>
        ))}
      </div>
    )
  }
  return (
    <pre className="max-h-24 max-w-[280px] overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-2 text-[10px] leading-snug">
      {jsonPreview(tags ?? [], 2000)}
    </pre>
  )
}

function pickLatestBatchId(batches: unknown[]): number | null {
  if (batches.length === 0) return null
  const rows = batches.filter(isRecord) as Record<string, unknown>[]
  let bestId: number | null = null
  let bestTime = -Infinity
  for (const b of rows) {
    const id = readNum(b.id)
    if (id == null) continue
    const ts =
      typeof b.updated_at === "string"
        ? Date.parse(b.updated_at)
        : typeof b.created_at === "string"
          ? Date.parse(b.created_at)
          : Number.NaN
    const t = Number.isFinite(ts) ? ts : 0
    if (t > bestTime) {
      bestTime = t
      bestId = id
    } else if (t === bestTime && bestId != null && id > bestId) {
      bestId = id
    }
  }
  if (bestId != null) return bestId
  const ids = rows.map((r) => readNum(r.id)).filter((x): x is number => x != null)
  return ids.length ? Math.max(...ids) : null
}

/** Rows from GET /reaction-recommendation-batches/{batch_id} (array root or nested). */
function parseRecommendationBatchItems(raw: unknown): Record<string, unknown>[] {
  if (Array.isArray(raw)) return raw.filter(isRecord) as Record<string, unknown>[]
  if (!isRecord(raw)) return []
  for (const k of ["recommendations", "items", "entries", "recommendation_rows"]) {
    const v = raw[k]
    if (Array.isArray(v)) return v.filter(isRecord) as Record<string, unknown>[]
  }
  return []
}

function formatPredictedScoreDisplay(r: Record<string, unknown>): string {
  const v = readNum(r.predicted_score)
  if (v != null) return String(v)
  const po = r.predicted_outcome_json
  if (isRecord(po)) {
    const s = readNum(po.score) ?? readNum(po.predicted_score) ?? readNum(po.value)
    if (s != null) return String(s)
  }
  return "—"
}

function formatExpectedImprovementDisplay(r: Record<string, unknown>): string {
  const v = readNum(r.expected_improvement) ?? readNum(r.estimated_improvement)
  if (v != null) return String(v)
  return "—"
}

function formatEstimatedCostDisplay(r: Record<string, unknown>): string {
  const v = readNum(r.estimated_cost)
  if (v != null) return String(v)
  return "—"
}

function formatAcquisitionScoreDisplay(r: Record<string, unknown>): string {
  const v = readNum(r.acquisition_score)
  if (v != null) return String(v)
  return "—"
}

/** Displays POST/GET /reaction-recommendations/{id}/advisor/critique response — advisory copy only. */
function RecommendationAdvisorCritiqueCard({ payload }: { payload: Record<string, unknown> }) {
  const riskFlags = Array.isArray(payload.risk_flags) ? payload.risk_flags : []
  const suggestedControls = Array.isArray(payload.suggested_controls) ? payload.suggested_controls : []
  const suggestedAlternatives = Array.isArray(payload.suggested_alternatives)
    ? payload.suggested_alternatives
    : []
  const recVal = payload.recommendation
  const recLabel = typeof recVal === "string" && recVal.trim() ? recVal.trim() : "—"

  return (
    <Card className="border-muted">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Condition critique (Advisor)</CardTitle>
        <CardDescription className="text-xs">
          POST /reaction-recommendations/{"{recommendation_id}"}/advisor/critique — GET same path. Interpretations are
          plausible and provisional; potential concerns require review before experimental decisions.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <Alert>
          <AlertTitle className="text-sm">Advisory interpretation</AlertTitle>
          <AlertDescription className="text-xs">
            Mechanistic and practical notes below are plausible summaries — not proof of best outcome. Suggested controls
            are advisory; where information is sparse, treat as insufficient information until reviewed.
          </AlertDescription>
        </Alert>

        <div className="flex flex-wrap gap-2">
          <Badge variant="outline" className="font-mono text-xs">
            recommendation: {recLabel}
          </Badge>
          <Badge
            variant={payload.human_review_required === true ? "secondary" : "outline"}
            className="text-xs"
          >
            human_review_required: {String(payload.human_review_required)}
          </Badge>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium uppercase text-muted-foreground">condition_summary_json</p>
          <pre className="max-h-40 overflow-auto rounded-md bg-muted/40 p-3 text-xs leading-relaxed">
            {jsonPreview(isRecord(payload.condition_summary_json) ? payload.condition_summary_json : {}, 6000)}
          </pre>
        </div>

        <div className="space-y-1">
          <p className="text-xs font-medium uppercase text-muted-foreground">mechanistic_rationale</p>
          <p className="text-muted-foreground">{String(payload.mechanistic_rationale ?? "")}</p>
        </div>

        <div className="space-y-1">
          <p className="text-xs font-medium uppercase text-muted-foreground">practicality_assessment</p>
          <p className="text-muted-foreground">{String(payload.practicality_assessment ?? "")}</p>
        </div>

        <div className="space-y-1">
          <p className="text-xs font-medium uppercase text-muted-foreground">cost_assessment</p>
          <p className="text-muted-foreground">{String(payload.cost_assessment ?? "")}</p>
        </div>

        <div className="space-y-1">
          <p className="text-xs font-medium uppercase text-muted-foreground">safety_assessment</p>
          <p className="text-muted-foreground">{String(payload.safety_assessment ?? "")}</p>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium uppercase text-muted-foreground">risk_flags</p>
          {riskFlags.length > 0 ? (
            <ul className="space-y-2">
              {riskFlags.map((f, i) => (
                <li key={i} className="rounded-md border border-border p-2 text-xs">
                  {isRecord(f) ? (
                    <div className="flex flex-wrap gap-2">
                      {typeof f.type === "string" ? (
                        <Badge variant="outline" className="font-mono text-[10px]">
                          {f.type}
                        </Badge>
                      ) : null}
                      {typeof f.severity === "string" ? (
                        <Badge variant="secondary" className="text-[10px]">
                          {f.severity}
                        </Badge>
                      ) : null}
                      <pre className="max-h-24 w-full overflow-auto whitespace-pre-wrap break-words text-[10px] leading-snug text-muted-foreground">
                        {jsonPreview(f, 2000)}
                      </pre>
                    </div>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted-foreground">risk_flags: none</p>
          )}
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium uppercase text-muted-foreground">suggested_controls</p>
          {suggestedControls.length > 0 ? (
            <pre className="max-h-40 overflow-auto rounded-md bg-muted/40 p-3 text-[10px] leading-snug">
              {jsonPreview(suggestedControls, 6000)}
            </pre>
          ) : (
            <p className="text-xs text-muted-foreground">suggested_controls: none</p>
          )}
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium uppercase text-muted-foreground">suggested_alternatives</p>
          {suggestedAlternatives.length > 0 ? (
            <pre className="max-h-40 overflow-auto rounded-md bg-muted/40 p-3 text-[10px] leading-snug">
              {jsonPreview(suggestedAlternatives, 6000)}
            </pre>
          ) : (
            <p className="text-xs text-muted-foreground">suggested_alternatives: none</p>
          )}
        </div>

        <Collapsible className="rounded-md border border-border">
          <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm font-medium hover:bg-muted/50">
            Developer JSON
            <ChevronDown className="h-4 w-4 shrink-0 opacity-70" />
          </CollapsibleTrigger>
          <CollapsibleContent className="border-t border-border px-3 py-3">
            <DeveloperJsonPanel data={payload} />
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  )
}

/** Prefer batches tagged as BO when present; otherwise use full list. */
function filterBoRecommendationBatches(batches: unknown[]): Record<string, unknown>[] {
  if (!Array.isArray(batches)) return []
  const rows = batches.filter(isRecord) as Record<string, unknown>[]
  const tagged = rows.filter((b) => {
    const src = b.source ?? b.batch_type ?? b.run_kind ?? b.optimization_kind
    if (typeof src !== "string") return false
    const t = src.toLowerCase()
    return t.includes("bo") || t.includes("bayes") || t.includes("bayesian")
  })
  return tagged.length > 0 ? tagged : rows
}

function parseBenchmarkTrajectory(raw: unknown): Record<string, unknown>[] {
  if (Array.isArray(raw)) return raw.filter(isRecord) as Record<string, unknown>[]
  if (!isRecord(raw)) return []
  const t =
    raw.trajectory ??
    raw.trajectory_json ??
    raw.steps ??
    raw.benchmark_trajectory ??
    raw.iterations
  if (Array.isArray(t)) return t.filter(isRecord) as Record<string, unknown>[]
  return []
}

function readBenchmarkBestObserved(r: Record<string, unknown>): string {
  const m = isRecord(r.metrics_json) ? r.metrics_json : null
  const v =
    readNum(r.best_observed_objective) ??
    readNum(r.best_observed) ??
    readNum(r.best_objective_value) ??
    (m ? readNum(m.best_observed_objective) ?? readNum(m.best_observed) : null)
  return v != null ? String(v) : "—"
}

function readBenchmarkRegret(r: Record<string, unknown>): string {
  const v = readNum(r.simple_regret) ?? readNum(r.regret)
  return v != null ? String(v) : "—"
}

function readBenchmarkExperimentsUsed(r: Record<string, unknown>): string {
  const v =
    readNum(r.experiments_used) ??
    readNum(r.num_experiments_used) ??
    readNum(r.experiment_count) ??
    readNum(r.n_experiments)
  return v != null ? String(v) : "—"
}

export function ReactionProjectDetail() {
  const params = useParams()
  const raw = params?.reactionId
  const reactionProjectId =
    typeof raw === "string"
      ? Number.parseInt(raw, 10)
      : Array.isArray(raw) && raw[0]
        ? Number.parseInt(raw[0], 10)
        : NaN

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [project, setProject] = useState<Record<string, unknown> | null>(null)
  const [variables, setVariables] = useState<unknown[]>([])
  const [experiments, setExperiments] = useState<unknown[]>([])
  const [recommendations, setRecommendations] = useState<unknown[]>([])
  const [runs, setRuns] = useState<unknown[]>([])
  const [evidenceCounts, setEvidenceCounts] = useState<Record<number, number>>({})
  const [experimentEvidenceById, setExperimentEvidenceById] = useState<Record<number, Record<string, unknown>>>({})
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<{ tone: "ok" | "err"; text: string } | null>(null)

  /** Variable create form */
  const [vName, setVName] = useState("")
  const [vType, setVType] = useState("numeric")
  const [vUnit, setVUnit] = useState("")
  const [vMin, setVMin] = useState("")
  const [vMax, setVMax] = useState("")
  const [vAllowedCsv, setVAllowedCsv] = useState("")
  const [vDefault, setVDefault] = useState("")

  /** Experiment create form */
  const [expCode, setExpCode] = useState("")
  const [expStatus, setExpStatus] = useState("planned")
  const [expConditionValues, setExpConditionValues] = useState<Record<string, string>>({})
  const [expYield, setExpYield] = useState("")
  const [expConversion, setExpConversion] = useState("")
  const [expSelectivity, setExpSelectivity] = useState("")
  const [expImpurity, setExpImpurity] = useState("")
  const [expIsolatedYield, setExpIsolatedYield] = useState("")
  const [expLcmsArea, setExpLcmsArea] = useState("")
  const [expNmrPurity, setExpNmrPurity] = useState("")
  const [expNotes, setExpNotes] = useState("")
  const [expSessionId, setExpSessionId] = useState("")

  /** Recommendation review — human approval required */
  const [revReviewerName, setRevReviewerName] = useState("")
  const [revComment, setRevComment] = useState<Record<number, string>>({})
  /** Cached GET/POST /reaction-recommendations/{id}/advisor/critique payloads keyed by recommendation id. */
  const [critiqueByRecommendationId, setCritiqueByRecommendationId] = useState<Record<number, unknown>>({})

  const [mechanisticHypotheses, setMechanisticHypotheses] = useState<unknown[]>([])
  const [mhTitle, setMhTitle] = useState("")
  const [mhHypothesis, setMhHypothesis] = useState("")
  const [mhConfidence, setMhConfidence] = useState<string>("speculative")
  const [mhSupportingJson, setMhSupportingJson] = useState("")
  const [mhContradictingJson, setMhContradictingJson] = useState("")

  const [literaturePriors, setLiteraturePriors] = useState<unknown[]>([])
  const [lpSourceType, setLpSourceType] = useState<string>("user_note")
  const [lpTitle, setLpTitle] = useState("")
  const [lpSummary, setLpSummary] = useState("")
  const [lpCitation, setLpCitation] = useState("")
  const [lpTagsJson, setLpTagsJson] = useState("")

  /** Latest POST /optimization/run response for this session */
  const [lastOptimizationRun, setLastOptimizationRun] = useState<unknown>(null)
  /** Latest POST /optimization/bo/run response */
  const [lastBoRun, setLastBoRun] = useState<unknown>(null)
  const [boAlgorithm, setBoAlgorithm] = useState<string>(BO_ALGORITHM_OPTIONS[0])
  const [boBatchSize, setBoBatchSize] = useState("1")
  const [boExplorationWeight, setBoExplorationWeight] = useState("0.1")
  const [boCostAware, setBoCostAware] = useState(true)
  const [boSafetyAware, setBoSafetyAware] = useState(true)
  const [boIncludeFailedAsNegative, setBoIncludeFailedAsNegative] = useState(false)
  const [boNotes, setBoNotes] = useState("")

  /** Link SpectraCheck session dialog */
  const [linkDialogExperimentId, setLinkDialogExperimentId] = useState<number | null>(null)
  const [linkSessionInput, setLinkSessionInput] = useState("")
  const [linkNoteInput, setLinkNoteInput] = useState("")

  const [objectiveProfileRaw, setObjectiveProfileRaw] = useState<unknown>(null)
  const [designSpaceRaw, setDesignSpaceRaw] = useState<unknown>(null)
  const [objectiveType, setObjectiveType] = useState<string>("maximize_yield")
  const [weightYield, setWeightYield] = useState("")
  const [weightSelectivity, setWeightSelectivity] = useState("")
  const [weightImpurityPenalty, setWeightImpurityPenalty] = useState("")
  const [weightConversion, setWeightConversion] = useState("")
  const [weightCostPenalty, setWeightCostPenalty] = useState("")
  const [minimumYield, setMinimumYield] = useState("")
  const [minimumSelectivity, setMinimumSelectivity] = useState("")
  const [maximumImpurity, setMaximumImpurity] = useState("")
  const [hardConstraintsText, setHardConstraintsText] = useState("")
  const [softConstraintsText, setSoftConstraintsText] = useState("")
  const [explorationByVariableId, setExplorationByVariableId] = useState<Record<number, ExplorationState>>({})

  const [costProfileRaw, setCostProfileRaw] = useState<unknown>(null)
  const [safetyProfileRaw, setSafetyProfileRaw] = useState<unknown>(null)
  const [reagentCostsText, setReagentCostsText] = useState("")
  const [solventCostsText, setSolventCostsText] = useState("")
  const [catalystCostsText, setCatalystCostsText] = useState("")
  const [ligandCostsText, setLigandCostsText] = useState("")
  const [availabilityNotes, setAvailabilityNotes] = useState("")
  const [maxCostPerExperiment, setMaxCostPerExperiment] = useState("")
  const [costProfilePenaltyWeight, setCostProfilePenaltyWeight] = useState("")
  const [blockedReagentsText, setBlockedReagentsText] = useState("")
  const [blockedSolventsText, setBlockedSolventsText] = useState("")
  const [maxTemperatureC, setMaxTemperatureC] = useState("")
  const [maxPressureBar, setMaxPressureBar] = useState("")
  const [incompatiblePairsText, setIncompatiblePairsText] = useState("")
  const [requiredControlsText, setRequiredControlsText] = useState("")
  const [safetyNotes, setSafetyNotes] = useState("")

  const [recommendationBatchesList, setRecommendationBatchesList] = useState<unknown[]>([])
  const [latestRecommendationBatch, setLatestRecommendationBatch] = useState<unknown>(null)

  const [benchmarkRuns, setBenchmarkRuns] = useState<unknown[]>([])
  const [lastBenchmarkRun, setLastBenchmarkRun] = useState<unknown>(null)
  const [benchmarkName, setBenchmarkName] = useState("")
  const [benchmarkAlgorithm, setBenchmarkAlgorithm] = useState<string>(BO_ALGORITHM_OPTIONS[0])
  const [benchmarkObjective, setBenchmarkObjective] = useState("")
  const [benchmarkBudget, setBenchmarkBudget] = useState("20")
  const [benchmarkSeed, setBenchmarkSeed] = useState("")
  const [useCompletedProjectData, setUseCompletedProjectData] = useState(true)

  /** Latest POST /advisor/run response for this session (detail shape matches GET /reaction-advisor-runs/{id}). */
  const [lastAdvisorRun, setLastAdvisorRun] = useState<unknown>(null)
  const [boRuns, setBoRuns] = useState<unknown[]>([])
  const [advisorRunsList, setAdvisorRunsList] = useState<unknown[]>([])
  const [advBoRunId, setAdvBoRunId] = useState("")
  const [advBatchId, setAdvBatchId] = useState("")
  const [advisorMode, setAdvisorMode] = useState<string>(ADVISOR_MODE_OPTIONS[0])
  const [advIncludeCostSafety, setAdvIncludeCostSafety] = useState(true)
  const [advIncludeCompletedExperiments, setAdvIncludeCompletedExperiments] = useState(true)
  const [advIncludeLiteraturePriors, setAdvIncludeLiteraturePriors] = useState(true)
  const [advNotes, setAdvNotes] = useState("")
  const [comparisons, setComparisons] = useState<unknown[]>([])
  const [lastComparison, setLastComparison] = useState<unknown>(null)
  const [cmpBoRunId, setCmpBoRunId] = useState("")
  const [cmpAdvisorRunId, setCmpAdvisorRunId] = useState("")
  const [advisorReviewRunId, setAdvisorReviewRunId] = useState("")
  const [advisorReviewerName, setAdvisorReviewerName] = useState("")
  const [advisorReviewDecision, setAdvisorReviewDecision] = useState<string>(ADVISOR_REVIEW_DECISIONS[0])
  const [advisorReviewRationale, setAdvisorReviewRationale] = useState("")

  /** GET /reaction-projects/{id}/execution-batches (lab execution grouping; optional for POST convert body). */
  const [executionBatchesList, setExecutionBatchesList] = useState<unknown[]>([])
  const [convertRecExecutionBatchId, setConvertRecExecutionBatchId] = useState("")
  const [convertRecRationale, setConvertRecRationale] = useState("")
  const [executionPlanningRows, setExecutionPlanningRows] = useState<ReactionExecutionPlanningRow[]>([])
  const [executionBatchItemCounts, setExecutionBatchItemCounts] = useState<Record<number, number>>({})
  /** All GET /reaction-execution-batches/{batch_id}/items rows flattened for the execution board. */
  const [executionBoardItems, setExecutionBoardItems] = useState<unknown[]>([])
  const [boardDialog, setBoardDialog] = useState<
    null | { kind: "run" | "done" | "fail" | "checklist" | "note"; itemId: number }
  >(null)
  const [boardDialogOperator, setBoardDialogOperator] = useState("")
  const [boardDialogMessage, setBoardDialogMessage] = useState("")
  const [boardDialogFailureReason, setBoardDialogFailureReason] = useState("")
  const [boardDialogNote, setBoardDialogNote] = useState("")
  const [boardDialogChecklistJson, setBoardDialogChecklistJson] = useState("")
  const [arExecutionItemId, setArExecutionItemId] = useState("")
  const [arResultType, setArResultType] = useState<string>(ANALYTICAL_RESULT_TYPE_OPTIONS[0])
  const [arSpectraCheckSessionId, setArSpectraCheckSessionId] = useState("")
  const [arFileId, setArFileId] = useState("")
  const [arArtifactId, setArArtifactId] = useState("")
  const [arSourceHash, setArSourceHash] = useState("")
  const [arSummaryText, setArSummaryText] = useState("")
  const [analyticalResultsByExecutionItemId, setAnalyticalResultsByExecutionItemId] = useState<Record<number, unknown[]>>({})
  const [analyticalResultsLoadingItemId, setAnalyticalResultsLoadingItemId] = useState<number | null>(null)
  const [oeExecutionItemId, setOeExecutionItemId] = useState("")
  const [oeExtractionMethod, setOeExtractionMethod] = useState<string>(OUTCOME_EXTRACTION_METHOD_OPTIONS[0])
  const [oeAnalyticalResultIdChoice, setOeAnalyticalResultIdChoice] = useState("__all__")
  const [oeExtractionRun, setOeExtractionRun] = useState<Record<string, unknown> | null>(null)
  const [oeConfirmedYieldPercent, setOeConfirmedYieldPercent] = useState("")
  const [oeConfirmedConversionPercent, setOeConfirmedConversionPercent] = useState("")
  const [oeConfirmedSelectivityPercent, setOeConfirmedSelectivityPercent] = useState("")
  const [oeConfirmedImpurityPercent, setOeConfirmedImpurityPercent] = useState("")
  const [oeConfirmedIsolatedYieldPercent, setOeConfirmedIsolatedYieldPercent] = useState("")
  const [oeConfirmedLcmsAreaPercent, setOeConfirmedLcmsAreaPercent] = useState("")
  const [oeConfirmedNmrPurityPercent, setOeConfirmedNmrPurityPercent] = useState("")
  const [oeConfirmedNotes, setOeConfirmedNotes] = useState("")
  const [oeReviewerName, setOeReviewerName] = useState("")
  const [oeConfirmRationale, setOeConfirmRationale] = useState("")
  const [optimizationCyclesList, setOptimizationCyclesList] = useState<unknown[]>([])
  const [optCcExecutionBatchId, setOptCcExecutionBatchId] = useState("")
  const [optCcStatus, setOptCcStatus] = useState<string>(REACTION_OPTIMIZATION_CYCLE_STATUS_OPTIONS[0])
  const [optCcCycleNumber, setOptCcCycleNumber] = useState("")
  const [optCcBoRunId, setOptCcBoRunId] = useState("")
  const [optCcAdvisorRunId, setOptCcAdvisorRunId] = useState("")
  const [optCcRecBatchId, setOptCcRecBatchId] = useState("")
  const [optimizationCycleDetailById, setOptimizationCycleDetailById] = useState<
    Record<number, Record<string, unknown>>
  >({})
  const [optimizationCycleDetailLoadingId, setOptimizationCycleDetailLoadingId] = useState<number | null>(null)
  const [occExpandedId, setOccExpandedId] = useState<number | null>(null)
  const [occDecision, setOccDecision] = useState<string>(REACTION_OPTIMIZATION_CYCLE_DECISION_OPTIONS[0])
  const [occRationale, setOccRationale] = useState("")
  const [occReviewer, setOccReviewer] = useState("")
  const [plEbBatchCode, setPlEbBatchCode] = useState("")
  const [plEbTitle, setPlEbTitle] = useState("")
  const [plEbPlannedStart, setPlEbPlannedStart] = useState("")
  const [plEbPlannedEnd, setPlEbPlannedEnd] = useState("")
  const [plEbNotes, setPlEbNotes] = useState("")
  const [plannerSelectedBatchId, setPlannerSelectedBatchId] = useState<number | null>(null)
  const [plannerBatchDetail, setPlannerBatchDetail] = useState<unknown>(null)
  const [plannerBatchItems, setPlannerBatchItems] = useState<unknown[]>([])
  const [plannerPanelLoading, setPlannerPanelLoading] = useState(false)
  const [execPlannerExperimentId, setExecPlannerExperimentId] = useState("")
  const [execPlannerItemCode, setExecPlannerItemCode] = useState("")
  const [execPlannerOperatorName, setExecPlannerOperatorName] = useState("")
  const [execPlannerChecklistJsonText, setExecPlannerChecklistJsonText] = useState("")
  const [plannerItemInspectPayload, setPlannerItemInspectPayload] = useState<unknown>(null)
  const [regulatoryPayloadForOptimization, setRegulatoryPayloadForOptimization] = useState<{
    regulatory_constraints: Record<string, unknown>[]
    compliance_objective: Record<string, unknown> | null
  } | null>(null)
  const [useRegulatoryAnchorInOptimization, setUseRegulatoryAnchorInOptimization] = useState(true)

  const reload = useCallback(async () => {
    if (!Number.isFinite(reactionProjectId) || reactionProjectId < 1) return
    setLoading(true)
    setError("")
    try {
      const base = `/reaction-projects/${reactionProjectId}`
      const [
        p,
        vr,
        ex,
        rec,
        rn,
        opRaw,
        dsRaw,
        costRaw,
        safetyRaw,
        boRunsRaw,
        advisorRunsRaw,
        mechHypsRaw,
        litPriorsRaw,
        comparisonsRaw,
        execBatchesRaw,
      ] = await Promise.all([
        apiFetch<unknown>(`${base}`, { method: "GET" }),
        apiFetch<unknown>(`${base}/variables`, { method: "GET" }),
        apiFetch<unknown>(`${base}/experiments`, { method: "GET" }),
        apiFetch<unknown>(`${base}/recommendations`, { method: "GET" }),
        apiFetch<unknown>(`${base}/optimization/runs`, { method: "GET" }).catch(() => []),
        apiFetch<unknown>(`${base}/objective-profile`, { method: "GET" }).catch(() => null),
        apiFetch<unknown>(`${base}/design-space`, { method: "GET" }).catch(() => null),
        apiFetch<unknown>(`${base}/cost-profile`, { method: "GET" }).catch(() => null),
        apiFetch<unknown>(`${base}/safety-profile`, { method: "GET" }).catch(() => null),
        apiFetch<unknown>(`${base}/optimization/bo/runs`, { method: "GET" }).catch(() => []),
        apiFetch<unknown>(`${base}/advisor/runs`, { method: "GET" }).catch(() => []),
        apiFetch<unknown>(`${base}/mechanistic-hypotheses`, { method: "GET" }).catch(() => []),
        apiFetch<unknown>(`${base}/literature-priors`, { method: "GET" }).catch(() => []),
        apiFetch<unknown>(`${base}/advisor/comparisons`, { method: "GET" }).catch(() => []),
        apiFetch<unknown>(`${base}/execution-batches`, { method: "GET" }).catch(() => []),
      ])
      setProject(isRecord(p) ? p : null)
      const vrList = Array.isArray(vr) ? vr : []
      setVariables(vrList)
      setExperiments(Array.isArray(ex) ? ex : [])
      setRecommendations(Array.isArray(rec) ? rec : [])
      setRuns(Array.isArray(rn) ? rn : [])
      setBoRuns(Array.isArray(boRunsRaw) ? boRunsRaw : [])
      setAdvisorRunsList(Array.isArray(advisorRunsRaw) ? advisorRunsRaw : [])
      setMechanisticHypotheses(Array.isArray(mechHypsRaw) ? mechHypsRaw : [])
      setLiteraturePriors(Array.isArray(litPriorsRaw) ? litPriorsRaw : [])
      const cmpRows = Array.isArray(comparisonsRaw) ? comparisonsRaw : []
      setComparisons(cmpRows)
      setLastComparison(cmpRows.length > 0 && isRecord(cmpRows[0]) ? cmpRows[0] : null)
      const execRows = Array.isArray(execBatchesRaw) ? execBatchesRaw : []
      setExecutionBatchesList(execRows)
      const execBatchIds = execRows
        .filter(isRecord)
        .map((raw) => readNum(raw.id))
        .filter((x): x is number => x != null)
      const countMap: Record<number, number> = {}
      const boardAcc: Record<string, unknown>[] = []
      await Promise.all(
        execBatchIds.map(async (bid) => {
          try {
            const items = await apiFetch<unknown>(`/reaction-execution-batches/${bid}/items`, {
              method: "GET",
            })
            const arr = Array.isArray(items) ? items.filter(isRecord) : []
            countMap[bid] = arr.length
            for (const row of arr) boardAcc.push(row as Record<string, unknown>)
          } catch {
            countMap[bid] = 0
          }
        }),
      )
      boardAcc.sort((a, b) => {
        const ia = readNum(a.id)
        const ib = readNum(b.id)
        return (ib ?? 0) - (ia ?? 0)
      })
      setExecutionBoardItems(boardAcc)
      setExecutionBatchItemCounts(countMap)

      setObjectiveProfileRaw(opRaw)
      setDesignSpaceRaw(dsRaw)
      if (isRecord(opRaw)) {
        const ot = opRaw.objective_type
        if (typeof ot === "string" && ot.trim()) setObjectiveType(ot.trim())
        const wSrc = isRecord(opRaw.weights_json)
          ? opRaw.weights_json
          : isRecord(opRaw.weights)
            ? opRaw.weights
            : {}
        const wNum = (k: string) => {
          const n = readNum((wSrc as Record<string, unknown>)[k])
          return n != null ? String(n) : ""
        }
        setWeightYield(wNum("yield"))
        setWeightSelectivity(wNum("selectivity"))
        setWeightImpurityPenalty(wNum("impurity_penalty"))
        setWeightConversion(wNum("conversion"))
        setWeightCostPenalty(wNum("cost_penalty"))
        const tt = isRecord(opRaw.target_thresholds) ? opRaw.target_thresholds : null
        const rMinY = readNum(opRaw.minimum_yield) ?? readNum(tt?.minimum_yield)
        const rMinS = readNum(opRaw.minimum_selectivity) ?? readNum(tt?.minimum_selectivity)
        const rMaxI = readNum(opRaw.maximum_impurity) ?? readNum(tt?.maximum_impurity)
        setMinimumYield(rMinY != null ? String(rMinY) : "")
        setMinimumSelectivity(rMinS != null ? String(rMinS) : "")
        setMaximumImpurity(rMaxI != null ? String(rMaxI) : "")
        setHardConstraintsText(constraintsTextFromField(opRaw.hard_constraints_json ?? opRaw.hard_constraints))
        setSoftConstraintsText(constraintsTextFromField(opRaw.soft_constraints_json ?? opRaw.soft_constraints))
      } else {
        setObjectiveType("maximize_yield")
        setWeightYield("")
        setWeightSelectivity("")
        setWeightImpurityPenalty("")
        setWeightConversion("")
        setWeightCostPenalty("")
        setMinimumYield("")
        setMinimumSelectivity("")
        setMaximumImpurity("")
        setHardConstraintsText("")
        setSoftConstraintsText("")
      }

      const variableRecordsForMap = vrList.filter(isRecord) as Record<string, unknown>[]
      setExplorationByVariableId(buildExplorationMap(variableRecordsForMap, dsRaw))

      setCostProfileRaw(costRaw)
      if (isRecord(costRaw)) {
        setReagentCostsText(constraintsTextFromField(costRaw.reagent_costs_json))
        setSolventCostsText(constraintsTextFromField(costRaw.solvent_costs_json))
        setCatalystCostsText(constraintsTextFromField(costRaw.catalyst_costs_json))
        setLigandCostsText(constraintsTextFromField(costRaw.ligand_costs_json))
        const av = costRaw.availability_notes
        setAvailabilityNotes(typeof av === "string" ? av : "")
        const mce = readNum(costRaw.max_cost_per_experiment)
        setMaxCostPerExperiment(mce != null ? String(mce) : "")
        const cpw = readNum(costRaw.cost_penalty_weight)
        setCostProfilePenaltyWeight(cpw != null ? String(cpw) : "")
      } else {
        setReagentCostsText("")
        setSolventCostsText("")
        setCatalystCostsText("")
        setLigandCostsText("")
        setAvailabilityNotes("")
        setMaxCostPerExperiment("")
        setCostProfilePenaltyWeight("")
      }

      setSafetyProfileRaw(safetyRaw)
      if (isRecord(safetyRaw)) {
        setBlockedReagentsText(constraintsTextFromField(safetyRaw.blocked_reagents))
        setBlockedSolventsText(constraintsTextFromField(safetyRaw.blocked_solvents))
        const tc = readNum(safetyRaw.max_temperature_c)
        setMaxTemperatureC(tc != null ? String(tc) : "")
        const pb = readNum(safetyRaw.max_pressure_bar)
        setMaxPressureBar(pb != null ? String(pb) : "")
        setIncompatiblePairsText(constraintsTextFromField(safetyRaw.incompatible_pairs))
        setRequiredControlsText(constraintsTextFromField(safetyRaw.required_controls))
        const sn = safetyRaw.safety_notes
        setSafetyNotes(typeof sn === "string" ? sn : "")
      } else {
        setBlockedReagentsText("")
        setBlockedSolventsText("")
        setMaxTemperatureC("")
        setMaxPressureBar("")
        setIncompatiblePairsText("")
        setRequiredControlsText("")
        setSafetyNotes("")
      }

      const exArr = Array.isArray(ex) ? ex : []
      const counts: Record<number, number> = {}
      const evById: Record<number, Record<string, unknown>> = {}
      await Promise.all(
        exArr.map(async (row) => {
          if (!isRecord(row)) return
          const eid = readNum(row.id)
          const linked = readNum(row.linked_spectracheck_session_id)
          if (eid == null || linked == null) return
          try {
            const ev = await apiFetch<unknown>(`/reaction-experiments/${eid}/evidence`, { method: "GET" })
            if (isRecord(ev)) {
              evById[eid] = ev
              const recs = Array.isArray(ev.evidence_records) ? ev.evidence_records : []
              const md = isRecord(ev.metadata) ? ev.metadata : {}
              const nMeta = readNum(md.evidence_count)
              counts[eid] = nMeta ?? recs.length
            }
          } catch {
            /* ignore per-experiment evidence failures */
          }
        }),
      )
      setEvidenceCounts(counts)
      setExperimentEvidenceById(evById)

      let batchesList: unknown[] = []
      let batchDetail: unknown = null
      try {
        const br = await apiFetch<unknown>(`${base}/recommendation-batches`, { method: "GET" })
        batchesList = Array.isArray(br) ? br : []
        const candidates = filterBoRecommendationBatches(batchesList)
        const bid = pickLatestBatchId(candidates.length > 0 ? candidates : batchesList)
        if (bid != null) {
          batchDetail = await apiFetch<unknown>(`/reaction-recommendation-batches/${bid}`, {
            method: "GET",
          })
        }
      } catch {
        batchesList = []
        batchDetail = null
      }
      setRecommendationBatchesList(batchesList)
      setLatestRecommendationBatch(batchDetail)

      let optimizationCyclesRaw: unknown[] = []
      try {
        const ocRaw = await apiFetch<unknown>(`${base}/optimization-cycles`, { method: "GET" })
        optimizationCyclesRaw = Array.isArray(ocRaw) ? ocRaw : []
      } catch {
        optimizationCyclesRaw = []
      }
      setOptimizationCyclesList(optimizationCyclesRaw)

      const benchRunsRaw = await apiFetch<unknown>(`${base}/optimization/benchmark-runs`, { method: "GET" }).catch(
        () => [],
      )
      setBenchmarkRuns(Array.isArray(benchRunsRaw) ? benchRunsRaw : [])
    } catch (e) {
      setProject(null)
      setVariables([])
      setExperiments([])
      setRecommendations([])
      setRuns([])
      setBoRuns([])
      setAdvisorRunsList([])
      setMechanisticHypotheses([])
      setLiteraturePriors([])
      setComparisons([])
      setLastComparison(null)
      setObjectiveProfileRaw(null)
      setDesignSpaceRaw(null)
      setCostProfileRaw(null)
      setSafetyProfileRaw(null)
      setRecommendationBatchesList([])
      setLatestRecommendationBatch(null)
      setBenchmarkRuns([])
      setOptimizationCyclesList([])
      setExplorationByVariableId({})
      setEvidenceCounts({})
      setExperimentEvidenceById({})
      setError(formatApiError(e, "Could not load reaction project."))
    } finally {
      setLoading(false)
    }
  }, [reactionProjectId])

  useEffect(() => {
    void reload()
  }, [reload])

  const objective = typeof project?.objective === "string" ? project.objective : undefined
  const status = typeof project?.status === "string" ? project.status : undefined
  const projectName = typeof project?.name === "string" ? project.name : "Reaction project"

  useEffect(() => {
    if (typeof objective === "string" && objective.trim()) {
      setBenchmarkObjective((prev) => (prev.trim() === "" ? objective : prev))
    }
  }, [objective])

  useEffect(() => {
    if (advisorReviewRunId.trim() !== "") return
    const rid = isRecord(lastAdvisorRun) ? readNum(lastAdvisorRun.advisor_run_id ?? lastAdvisorRun.id) : null
    if (rid != null) {
      setAdvisorReviewRunId(String(rid))
      return
    }
    const first = advisorRunsList.find(isRecord)
    const firstId = first ? readNum(first.advisor_run_id ?? first.id) : null
    if (firstId != null) setAdvisorReviewRunId(String(firstId))
  }, [advisorRunsList, lastAdvisorRun, advisorReviewRunId])

  const experimentsRec = useMemo(
    () => experiments.filter(isRecord) as Record<string, unknown>[],
    [experiments],
  )
  const experimentCount = experimentsRec.length
  const completedExperimentCount = useMemo(
    () => experimentsRec.filter((e) => e.status === "completed").length,
    [experimentsRec],
  )
  const linkedSessionCount = experimentsRec.filter((e) => readNum(e.linked_spectracheck_session_id) != null).length

  const confirmedReactionOutcomesCount = useMemo(() => {
    return experimentsRec.filter((e) => {
      const md = e.metadata_json
      return isRecord(md) && isRecord(md.outcome_confirmation)
    }).length
  }, [experimentsRec])

  const failedSkippedReactionExperimentsCount = useMemo(() => {
    return experimentsRec.filter((e) => {
      const st = String(e.status ?? "").toLowerCase()
      return st === "failed" || st === "skipped" || st === "canceled"
    }).length
  }, [experimentsRec])

  const execTabLatestBoRunRecord = useMemo((): Record<string, unknown> | null => {
    if (lastBoRun != null && isRecord(lastBoRun)) return lastBoRun
    const rows = boRuns.filter(isRecord) as Record<string, unknown>[]
    const sorted = [...rows].sort((a, b) => {
      const ia = readNum(a.bo_run_id ?? a.id) ?? 0
      const ib = readNum(b.bo_run_id ?? b.id) ?? 0
      return ib - ia
    })
    return sorted[0] ?? null
  }, [lastBoRun, boRuns])

  const execTabLatestAdvisorRunRecord = useMemo((): Record<string, unknown> | null => {
    if (lastAdvisorRun != null && isRecord(lastAdvisorRun)) return lastAdvisorRun
    const rows = advisorRunsList.filter(isRecord) as Record<string, unknown>[]
    const sorted = [...rows].sort((a, b) => {
      const ia = readNum(a.advisor_run_id ?? a.id) ?? 0
      const ib = readNum(b.advisor_run_id ?? b.id) ?? 0
      return ib - ia
    })
    return sorted[0] ?? null
  }, [lastAdvisorRun, advisorRunsList])

  const execTabLastOptimizationCycleDecisionLabel = useMemo(() => {
    const rows = optimizationCyclesList.filter(isRecord) as Record<string, unknown>[]
    if (rows.length === 0) return "—"
    const sorted = [...rows].sort((a, b) => {
      const cnA = readNum(a.cycle_number) ?? 0
      const cnB = readNum(b.cycle_number) ?? 0
      if (cnB !== cnA) return cnB - cnA
      return (readNum(b.id) ?? 0) - (readNum(a.id) ?? 0)
    })
    const top = sorted[0]
    const cn = top.cycle_number
    const decRecord = optimizationCycleDecisionRecordFromCycle(top)
    if (decRecord == null) return `cycle ${cn != null ? String(cn) : "—"} · no recorded decision`
    const dRaw = decRecord.decision
    const d = typeof dRaw === "string" ? dRaw.replace(/_/g, " ") : "—"
    return `cycle ${cn != null ? String(cn) : "—"} · ${d}`
  }, [optimizationCyclesList])

  const sortedRecs = useMemo(() => {
    const rs = recommendations.filter(isRecord) as Record<string, unknown>[]
    return [...rs].sort((a, b) => {
      const ua = typeof a.updated_at === "string" ? Date.parse(a.updated_at) : 0
      const ub = typeof b.updated_at === "string" ? Date.parse(b.updated_at) : 0
      return ub - ua
    })
  }, [recommendations])

  const latestBatchRows = useMemo(
    () => parseRecommendationBatchItems(latestRecommendationBatch),
    [latestRecommendationBatch],
  )

  /** Rows with status approved from GET /reaction-projects/{id}/recommendations (sortedRecs ordering). */
  const approvedRecommendationsQueue = useMemo(
    () => sortedRecs.filter((r) => String(r.status ?? "").toLowerCase() === "approved"),
    [sortedRecs],
  )

  const reactionExecutionBatchRecords = useMemo(
    () => executionBatchesList.filter(isRecord) as Record<string, unknown>[],
    [executionBatchesList],
  )

  useEffect(() => {
    setExecutionPlanningRows((prev) => {
      const prevByRec = new Map(prev.map((row) => [row.recommendation_id, row]))
      for (const r of sortedRecs) {
        const rid = readNum(r.id)
        if (rid == null) continue
        const md = isRecord(r.metadata_json) ? r.metadata_json : {}
        const eid = readNum(md.converted_experiment_id)
        if (eid == null) continue
        const cur = prevByRec.get(rid)
        prevByRec.set(rid, {
          recommendation_id: rid,
          experiment_id: eid,
          experiment_status:
            typeof cur?.experiment_status === "string" && cur.experiment_status.trim()
              ? cur.experiment_status
              : "planned",
          execution_item_id: cur?.execution_item_id ?? null,
        })
      }
      return [...prevByRec.values()].sort((a, b) => b.recommendation_id - a.recommendation_id)
    })
  }, [sortedRecs])

  const executionPlanningByRecId = useMemo(
    () => new Map(executionPlanningRows.map((row) => [row.recommendation_id, row])),
    [executionPlanningRows],
  )

  const plannedExperimentsForPlanner = useMemo(
    () => experimentsRec.filter((e) => String(e.status ?? "").toLowerCase() === "planned"),
    [experimentsRec],
  )

  const experimentCodeById = useMemo(() => {
    const m = new Map<number, string>()
    for (const e of experimentsRec) {
      const id = readNum(e.id)
      if (id == null) continue
      const code = typeof e.experiment_code === "string" ? e.experiment_code.trim() : ""
      m.set(id, code || `experiment_id ${id}`)
    }
    return m
  }, [experimentsRec])

  useEffect(() => {
    if (plannerSelectedBatchId == null || !Number.isFinite(plannerSelectedBatchId)) {
      setPlannerBatchDetail(null)
      setPlannerBatchItems([])
      setPlannerPanelLoading(false)
      return
    }
    let cancelled = false
    setPlannerPanelLoading(true)
    ;(async () => {
      try {
        const [b, rawItems] = await Promise.all([
          apiFetch<unknown>(`/reaction-execution-batches/${plannerSelectedBatchId}`, { method: "GET" }),
          apiFetch<unknown>(`/reaction-execution-batches/${plannerSelectedBatchId}/items`, {
            method: "GET",
          }),
        ])
        if (cancelled) return
        setPlannerBatchDetail(b)
        setPlannerBatchItems(Array.isArray(rawItems) ? rawItems : [])
      } catch {
        if (!cancelled) {
          setPlannerBatchDetail(null)
          setPlannerBatchItems([])
        }
      } finally {
        if (!cancelled) setPlannerPanelLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [plannerSelectedBatchId])

  const plannerBatchItemRecords = useMemo(
    () => plannerBatchItems.filter(isRecord) as Record<string, unknown>[],
    [plannerBatchItems],
  )

  const executionBoardItemRecords = useMemo(
    () => executionBoardItems.filter(isRecord) as Record<string, unknown>[],
    [executionBoardItems],
  )

  const executionBoardColumns = useMemo(() => {
    const planned: Record<string, unknown>[] = []
    const running: Record<string, unknown>[] = []
    const completed: Record<string, unknown>[] = []
    const failedSkipped: Record<string, unknown>[] = []
    for (const row of executionBoardItemRecords) {
      const st = String(row.status ?? "").toLowerCase()
      if (st === "running") running.push(row)
      else if (st === "completed") completed.push(row)
      else if (st === "failed" || st === "skipped" || st === "canceled") failedSkipped.push(row)
      else planned.push(row)
    }
    return { planned, running, completed, failedSkipped }
  }, [executionBoardItemRecords])

  function executionBatchIdForBoardItem(boardItemId: number): number | undefined {
    const row = executionBoardItemRecords.find((r) => readNum(r.id) === boardItemId)
    const bid = row ? readNum(row.execution_batch_id) : null
    return bid ?? undefined
  }

  const executionItemSelectorRows = useMemo(() => {
    return executionBoardItemRecords.map((row) => {
      const itemId = readNum(row.id)
      const experimentId = readNum(row.experiment_id)
      const itemCode = typeof row.item_code === "string" ? row.item_code : ""
      const experimentCode =
        experimentId != null ? experimentCodeById.get(experimentId) ?? `experiment_id ${experimentId}` : "—"
      return { itemId, itemCode, experimentCode }
    })
  }, [executionBoardItemRecords, experimentCodeById])

  const selectedAnalyticalExecutionItemId = useMemo(() => {
    const n = Number.parseInt(arExecutionItemId.trim(), 10)
    return Number.isFinite(n) ? n : null
  }, [arExecutionItemId])

  const selectedOutcomeExecutionItemId = useMemo(() => {
    const n = Number.parseInt(oeExecutionItemId.trim(), 10)
    return Number.isFinite(n) && n >= 1 ? n : null
  }, [oeExecutionItemId])

  useEffect(() => {
    if (selectedAnalyticalExecutionItemId == null || selectedAnalyticalExecutionItemId < 1) return
    void loadExecutionItemAnalyticalResults(selectedAnalyticalExecutionItemId)
  }, [selectedAnalyticalExecutionItemId])

  useEffect(() => {
    if (selectedOutcomeExecutionItemId == null || selectedOutcomeExecutionItemId < 1) return
    void loadExecutionItemAnalyticalResults(selectedOutcomeExecutionItemId)
  }, [selectedOutcomeExecutionItemId])

  useEffect(() => {
    setOeExtractionRun(null)
    setOeExtractionMethod(OUTCOME_EXTRACTION_METHOD_OPTIONS[0])
    setOeAnalyticalResultIdChoice("__all__")
    setOeConfirmedYieldPercent("")
    setOeConfirmedConversionPercent("")
    setOeConfirmedSelectivityPercent("")
    setOeConfirmedImpurityPercent("")
    setOeConfirmedIsolatedYieldPercent("")
    setOeConfirmedLcmsAreaPercent("")
    setOeConfirmedNmrPurityPercent("")
    setOeConfirmedNotes("")
    setOeReviewerName("")
    setOeConfirmRationale("")
  }, [selectedOutcomeExecutionItemId])

  useEffect(() => {
    if (occExpandedId == null) return
    setOccRationale("")
    setOccDecision(REACTION_OPTIMIZATION_CYCLE_DECISION_OPTIONS[0])
    setOccReviewer("")
  }, [occExpandedId])

  const executionRecommendationBatchesRecords = useMemo(
    () => recommendationBatchesList.filter(isRecord) as Record<string, unknown>[],
    [recommendationBatchesList],
  )

  const executionCycleTimeline = useMemo(() => {
    const items: { sk: number; detail: string; whenLabel: string }[] = []
    const addRecord = (
      kind: string,
      r: Record<string, unknown>,
      idKeys: readonly string[],
      detailKeys: readonly string[],
    ) => {
      let idNum: number | null = null
      for (const k of idKeys) {
        idNum = readNum(r[k])
        if (idNum != null) break
      }
      const tRaw = r.updated_at ?? r.created_at
      const sk = typeof tRaw === "string" ? Date.parse(tRaw) || 0 : 0
      let det = ""
      for (const k of detailKeys) {
        const v = r[k]
        if (typeof v === "string" && v.trim()) {
          det = v.trim()
          break
        }
      }
      if (!det && typeof r.status === "string" && r.status.trim()) det = r.status.trim()
      if (!det) det = kind
      items.push({
        sk,
        detail: `${kind} · id=${idNum ?? "—"} · ${det}`,
        whenLabel: fmtIso(tRaw),
      })
    }
    for (const x of boRuns) {
      if (isRecord(x)) addRecord("GET /optimization/bo/runs row", x, ["id", "bo_run_id"], ["algorithm"])
    }
    for (const x of runs) {
      if (isRecord(x)) addRecord("GET /optimization/runs row", x, ["id"], ["model_type"])
    }
    for (const x of advisorRunsList) {
      if (isRecord(x)) addRecord("GET /advisor/runs row", x, ["advisor_run_id", "id"], ["advisor_mode"])
    }
    return items.sort((a, b) => b.sk - a.sk)
  }, [boRuns, runs, advisorRunsList])

  const executionDevPayload = useMemo(
    () => ({
      approved_recommendations_queue: approvedRecommendationsQueue,
      execution_batches: executionBatchesList,
      execution_batch_item_counts: executionBatchItemCounts,
      execution_board_items: executionBoardItems,
      recommendation_batches_list: recommendationBatchesList,
      execution_planning_rows: executionPlanningRows,
      experiments,
      experiments_with_linked_spectracheck_sessions: experimentsRec.filter(
        (e) => readNum(e.linked_spectracheck_session_id) != null,
      ),
      optimization_runs: runs,
      bo_runs: boRuns,
      advisor_runs: advisorRunsList,
      comparisons,
    }),
    [
      approvedRecommendationsQueue,
      executionBatchesList,
      executionBatchItemCounts,
      executionBoardItems,
      executionPlanningRows,
      recommendationBatchesList,
      experiments,
      experimentsRec,
      runs,
      boRuns,
      advisorRunsList,
      comparisons,
    ],
  )

  const modelDiagnosticsDerived = useMemo(() => {
    const bo = isRecord(lastBoRun) ? lastBoRun : null
    const rule = isRecord(lastOptimizationRun) ? lastOptimizationRun : null
    const training =
      readNum(bo?.training_experiment_count) ??
      readNum(bo?.input_experiment_count) ??
      readNum(rule?.input_experiment_count) ??
      null
    const mtBo = bo ? String(bo.model_type ?? bo.algorithm ?? "").trim() : ""
    const mtRule = rule ? String(rule.model_type ?? "").trim() : ""
    const modelType = mtBo || mtRule ? mtBo || mtRule || null : null
    const diag =
      bo && isRecord(bo.diagnostics_json)
        ? bo.diagnostics_json
        : bo && isRecord(bo.diagnostics)
          ? (bo.diagnostics as Record<string, unknown>)
          : null
    const uncertaintySummary =
      diag && typeof diag.uncertainty_summary === "string" ? diag.uncertainty_summary : null
    const featureEncodingSummary =
      diag && typeof diag.feature_encoding_summary === "string" ? diag.feature_encoding_summary : null
    const valFromDiag =
      diag && isRecord(diag.validation_metrics) ? diag.validation_metrics : null
    const mBo = bo && isRecord(bo.metrics_json) ? bo.metrics_json : null
    const mRule = rule && isRecord(rule.metrics_json) ? rule.metrics_json : null
    let validationMetricsJson: unknown = null
    if (valFromDiag && Object.keys(valFromDiag).length > 0) validationMetricsJson = valFromDiag
    else if (mBo && Object.keys(mBo).length > 0) validationMetricsJson = mBo
    else if (mRule && Object.keys(mRule).length > 0) validationMetricsJson = mRule
    const warnings = mergeRunStringLists(
      bo?.warnings,
      bo?.warnings_json,
      rule?.warnings,
      rule?.warnings_json,
    )
    return {
      trainingExperimentCount: training,
      modelType,
      objectiveSummary: objective ?? null,
      validationMetricsJson,
      warnings,
      uncertaintySummary,
      featureEncodingSummary,
    }
  }, [lastBoRun, lastOptimizationRun, objective])

  const benchmarkTrajectoryRows = useMemo(() => {
    if (!isRecord(lastBenchmarkRun)) return []
    return parseBenchmarkTrajectory(lastBenchmarkRun)
  }, [lastBenchmarkRun])

  const latestRec = sortedRecs[0]

  const variableRecords = useMemo(
    () => variables.filter(isRecord) as Record<string, unknown>[],
    [variables],
  )

  const variableNamesOrdered = useMemo(() => {
    const names: string[] = []
    for (const v of variableRecords) {
      const n = typeof v.name === "string" ? v.name.trim() : ""
      if (n) names.push(n)
    }
    return names
  }, [variableRecords])

  const conditionKeysFromExperiments = useMemo(() => {
    const keys = new Set<string>()
    for (const e of experimentsRec) {
      const cj = e.conditions_json
      if (isRecord(cj)) {
        for (const k of Object.keys(cj)) keys.add(k)
      }
    }
    return [...keys].sort()
  }, [experimentsRec])

  /** Condition columns: variable order first, then any keys present in experiment data only. */
  const conditionColumnKeys = useMemo(() => {
    const out = [...variableNamesOrdered]
    for (const k of conditionKeysFromExperiments) {
      if (!out.includes(k)) out.push(k)
    }
    return out
  }, [variableNamesOrdered, conditionKeysFromExperiments])

  const devPayload = useMemo(
    () => ({
      project,
      variables,
      experiments,
      recommendations,
      optimization_runs: runs,
      objective_profile: objectiveProfileRaw,
      design_space: designSpaceRaw,
      cost_profile: costProfileRaw,
      safety_profile: safetyProfileRaw,
      recommendation_batches: recommendationBatchesList,
      latest_recommendation_batch: latestRecommendationBatch,
      benchmark_runs: benchmarkRuns,
      last_benchmark_run: lastBenchmarkRun,
    }),
    [
      project,
      variables,
      experiments,
      recommendations,
      runs,
      objectiveProfileRaw,
      designSpaceRaw,
      costProfileRaw,
      safetyProfileRaw,
      recommendationBatchesList,
      latestRecommendationBatch,
      benchmarkRuns,
      lastBenchmarkRun,
    ],
  )

  function buildObjectiveProfileRequestBody(): Record<string, unknown> {
    const weights_json: Record<string, number> = {}
    const putW = (key: string, s: string) => {
      const t = s.trim()
      if (!t) return
      const n = Number.parseFloat(t)
      if (Number.isFinite(n)) weights_json[key] = n
    }
    putW("yield", weightYield)
    putW("selectivity", weightSelectivity)
    putW("impurity_penalty", weightImpurityPenalty)
    putW("conversion", weightConversion)
    putW("cost_penalty", weightCostPenalty)

    const putThreshold = (s: string) => {
      const t = s.trim()
      if (!t) return null
      const n = Number.parseFloat(t)
      return Number.isFinite(n) ? n : null
    }
    const minimum_yield = putThreshold(minimumYield)
    const minimum_selectivity = putThreshold(minimumSelectivity)
    const maximum_impurity = putThreshold(maximumImpurity)

    let hard_constraints_json: unknown = null
    const hc = hardConstraintsText.trim()
    if (hc) {
      try {
        hard_constraints_json = JSON.parse(hc) as unknown
      } catch {
        hard_constraints_json = hc
      }
    }
    let soft_constraints_json: unknown = null
    const sc = softConstraintsText.trim()
    if (sc) {
      try {
        soft_constraints_json = JSON.parse(sc) as unknown
      } catch {
        soft_constraints_json = sc
      }
    }

    return {
      objective_type: objectiveType,
      weights_json,
      minimum_yield,
      minimum_selectivity,
      maximum_impurity,
      hard_constraints_json,
      soft_constraints_json,
    }
  }

  async function saveObjectiveProfile(e: React.FormEvent) {
    e.preventDefault()
    setMsg(null)
    setBusy("objective-profile")
    try {
      const body = buildObjectiveProfileRequestBody()
      const base = `/reaction-projects/${reactionProjectId}/objective-profile`
      if (objectiveProfileRaw != null) {
        await apiFetch(base, { method: "PATCH", body })
      } else {
        await apiFetch(base, { method: "POST", body })
      }
      setMsg({ tone: "ok", text: "Objective profile saved." })
      trackReactionObjectiveProfileSaved({
        reaction_project_id: reactionProjectId,
        objective_type: objectiveType,
        completed_experiment_count: completedExperimentCount,
        status,
      })
      await reload()
    } catch (err) {
      setMsg({ tone: "err", text: formatApiError(err, "Save objective profile failed.") })
    } finally {
      setBusy(null)
    }
  }

  async function saveDesignSpace(e: React.FormEvent) {
    e.preventDefault()
    setMsg(null)
    setBusy("design-space")
    try {
      const entries: Record<string, unknown>[] = []
      for (const v of variableRecords) {
        const id = readNum(v.id)
        if (id == null) continue
        const exploration_state = explorationByVariableId[id] ?? "free"
        entries.push({
          reaction_variable_id: id,
          exploration_state,
        })
      }
      await apiFetch(`/reaction-projects/${reactionProjectId}/design-space`, {
        method: designSpaceRaw != null ? "PATCH" : "POST",
        body: { entries },
      })
      setMsg({ tone: "ok", text: "Design space saved." })
      await reload()
    } catch (err) {
      setMsg({ tone: "err", text: formatApiError(err, "Save design space failed.") })
    } finally {
      setBusy(null)
    }
  }

  function buildCostProfileRequestBody(): Record<string, unknown> {
    const maxRaw = maxCostPerExperiment.trim()
    const max_cost_per_experiment =
      maxRaw && Number.isFinite(Number.parseFloat(maxRaw)) ? Number.parseFloat(maxRaw) : null
    const cpwRaw = costProfilePenaltyWeight.trim()
    const cost_penalty_weight =
      cpwRaw && Number.isFinite(Number.parseFloat(cpwRaw)) ? Number.parseFloat(cpwRaw) : null
    return {
      reagent_costs_json: jsonFieldFromText(reagentCostsText),
      solvent_costs_json: jsonFieldFromText(solventCostsText),
      catalyst_costs_json: jsonFieldFromText(catalystCostsText),
      ligand_costs_json: jsonFieldFromText(ligandCostsText),
      availability_notes: availabilityNotes.trim() || null,
      max_cost_per_experiment,
      cost_penalty_weight,
    }
  }

  async function saveCostProfile(e: React.FormEvent) {
    e.preventDefault()
    setMsg(null)
    setBusy("cost-profile")
    try {
      const body = buildCostProfileRequestBody()
      const path = `/reaction-projects/${reactionProjectId}/cost-profile`
      if (costProfileRaw != null) {
        await apiFetch(path, { method: "PATCH", body })
      } else {
        await apiFetch(path, { method: "POST", body })
      }
      setMsg({ tone: "ok", text: "Cost profile saved." })
      trackReactionCostProfileSaved({
        reaction_project_id: reactionProjectId,
        objective_type: objectiveType,
        completed_experiment_count: completedExperimentCount,
        status,
      })
      await reload()
    } catch (err) {
      setMsg({ tone: "err", text: formatApiError(err, "Save cost profile failed.") })
    } finally {
      setBusy(null)
    }
  }

  function buildSafetyProfileRequestBody(): Record<string, unknown> {
    const tRaw = maxTemperatureC.trim()
    const max_temperature_c =
      tRaw && Number.isFinite(Number.parseFloat(tRaw)) ? Number.parseFloat(tRaw) : null
    const pRaw = maxPressureBar.trim()
    const max_pressure_bar =
      pRaw && Number.isFinite(Number.parseFloat(pRaw)) ? Number.parseFloat(pRaw) : null
    return {
      blocked_reagents: jsonFieldFromText(blockedReagentsText),
      blocked_solvents: jsonFieldFromText(blockedSolventsText),
      max_temperature_c,
      max_pressure_bar,
      incompatible_pairs: jsonFieldFromText(incompatiblePairsText),
      required_controls: jsonFieldFromText(requiredControlsText),
      safety_notes: safetyNotes.trim() || null,
    }
  }

  async function saveSafetyProfile(e: React.FormEvent) {
    e.preventDefault()
    setMsg(null)
    setBusy("safety-profile")
    try {
      const body = buildSafetyProfileRequestBody()
      const path = `/reaction-projects/${reactionProjectId}/safety-profile`
      if (safetyProfileRaw != null) {
        await apiFetch(path, { method: "PATCH", body })
      } else {
        await apiFetch(path, { method: "POST", body })
      }
      setMsg({ tone: "ok", text: "Safety profile saved." })
      trackReactionSafetyProfileSaved({
        reaction_project_id: reactionProjectId,
        objective_type: objectiveType,
        completed_experiment_count: completedExperimentCount,
        status,
      })
      await reload()
    } catch (err) {
      setMsg({ tone: "err", text: formatApiError(err, "Save safety profile failed.") })
    } finally {
      setBusy(null)
    }
  }

  async function submitVariable(e: React.FormEvent) {
    e.preventDefault()
    setMsg(null)
    const name = vName.trim()
    if (!name) {
      setMsg({ tone: "err", text: "Variable name is required." })
      return
    }
    setBusy("variable")
    try {
      let categoricalAllowed: string[] | null = null
      if (vType === "categorical") {
        const parts = vAllowedCsv
          .split(",")
          .map((s) => s.trim())
          .filter((s) => s.length > 0)
        categoricalAllowed = parts.length > 0 ? parts : null
      }
      const minV =
        vType === "numeric" && vMin.trim() ? Number.parseFloat(vMin) : Number.NaN
      const maxV =
        vType === "numeric" && vMax.trim() ? Number.parseFloat(vMax) : Number.NaN
      const defRaw = vDefault.trim()
      let default_value: unknown = null
      if (defRaw) {
        try {
          default_value = JSON.parse(defRaw) as unknown
        } catch {
          const n = Number(defRaw)
          default_value = Number.isFinite(n) ? n : defRaw
        }
      }
      await apiFetch(`/reaction-projects/${reactionProjectId}/variables`, {
        method: "POST",
        body: {
          name,
          variable_type: vType,
          unit: vUnit.trim() || null,
          allowed_values_json: vType === "categorical" ? categoricalAllowed : null,
          min_value: vType === "numeric" && Number.isFinite(minV) ? minV : null,
          max_value: vType === "numeric" && Number.isFinite(maxV) ? maxV : null,
          default_value,
          metadata_json: {},
        },
      })
      setMsg({ tone: "ok", text: "Variable created." })
      setVName("")
      setVAllowedCsv("")
      setVMin("")
      setVMax("")
      setVDefault("")
      await reload()
    } catch (err) {
      setMsg({ tone: "err", text: formatApiError(err, "Create variable failed.") })
    } finally {
      setBusy(null)
    }
  }

  function buildConditionsJsonFromForm(): Record<string, unknown> {
    const conditions_json: Record<string, unknown> = {}
    const byName = new Map<string, Record<string, unknown>>()
    for (const v of variableRecords) {
      const name = typeof v.name === "string" ? v.name.trim() : ""
      if (name) byName.set(name, v)
    }
    for (const name of variableNamesOrdered) {
      const raw = (expConditionValues[name] ?? "").trim()
      if (!raw) continue
      const row = byName.get(name)
      const vt = row && typeof row.variable_type === "string" ? row.variable_type : "text"
      if (vt === "numeric") {
        const n = Number.parseFloat(raw)
        if (Number.isFinite(n)) conditions_json[name] = n
      } else if (vt === "boolean") {
        conditions_json[name] = raw === "true"
      } else {
        conditions_json[name] = raw
      }
    }
    return conditions_json
  }

  function buildOutcomeJsonFromForm(): Record<string, unknown> {
    const outcome_json: Record<string, unknown> = {}
    const putPct = (key: string, s: string) => {
      const t = s.trim()
      if (!t) return
      const n = Number.parseFloat(t)
      if (Number.isFinite(n)) outcome_json[key] = n
    }
    putPct("yield_percent", expYield)
    putPct("conversion_percent", expConversion)
    putPct("selectivity_percent", expSelectivity)
    putPct("impurity_percent", expImpurity)
    putPct("isolated_yield_percent", expIsolatedYield)
    putPct("lcms_area_percent", expLcmsArea)
    putPct("nmr_purity_percent", expNmrPurity)
    if (expNotes.trim()) outcome_json.notes = expNotes.trim()
    return outcome_json
  }

  async function submitExperiment(e: React.FormEvent) {
    e.preventDefault()
    setMsg(null)
    const code = expCode.trim()
    if (!code) {
      setMsg({ tone: "err", text: "experiment_code is required." })
      return
    }
    const conditions_json = buildConditionsJsonFromForm()
    const outcome_json = buildOutcomeJsonFromForm()
    const sidRaw = expSessionId.trim()
    const linked_spectracheck_session_id =
      sidRaw && /^\d+$/.test(sidRaw) ? Number.parseInt(sidRaw, 10) : null

    setBusy("experiment")
    try {
      await apiFetch(`/reaction-projects/${reactionProjectId}/experiments`, {
        method: "POST",
        body: {
          experiment_code: code,
          status: expStatus,
          conditions_json,
          outcome_json,
          linked_spectracheck_session_id,
          metadata_json: {},
        },
      })
      const nextCount = experimentCount + 1
      trackReactionExperimentAdded({
        reaction_project_id: reactionProjectId,
        experiment_count: nextCount,
        objective,
        status: expStatus,
      })
      if (outcomeJsonHasNumericMetrics(outcome_json)) {
        trackReactionOutcomeRecorded({
          reaction_project_id: reactionProjectId,
          experiment_count: nextCount,
          objective,
          status: expStatus,
        })
      }
      if (linked_spectracheck_session_id != null) {
        trackSpectracheckLinkedToReaction({
          reaction_project_id: reactionProjectId,
          experiment_count: nextCount,
          objective,
          status: expStatus,
          has_spectracheck_link: true,
        })
      }
      setMsg({ tone: "ok", text: "Experiment created." })
      setExpCode("")
      setExpConditionValues({})
      setExpYield("")
      setExpConversion("")
      setExpSelectivity("")
      setExpImpurity("")
      setExpIsolatedYield("")
      setExpLcmsArea("")
      setExpNmrPurity("")
      setExpNotes("")
      setExpSessionId("")
      await reload()
    } catch (err) {
      setMsg({ tone: "err", text: formatApiError(err, "Create experiment failed.") })
    } finally {
      setBusy(null)
    }
  }

  async function runOptimization() {
    setMsg(null)
    setBusy("optimization")
    trackReactionOptimizationRunStarted({
      reaction_project_id: reactionProjectId,
      experiment_count: experimentCount,
      objective,
      status,
    })
    const t0 = typeof performance !== "undefined" ? performance.now() : Date.now()
    try {
      const optimizationBody: Record<string, unknown> = {
        model_type: "rule_based",
        objective: objective ?? null,
        max_recommendations: 5,
        metadata_json: {},
      }
      if (useRegulatoryAnchorInOptimization && regulatoryPayloadForOptimization) {
        optimizationBody.regulatory_constraints_json = regulatoryPayloadForOptimization.regulatory_constraints
        optimizationBody.compliance_objective_json = regulatoryPayloadForOptimization.compliance_objective
        optimizationBody.metadata_json = {
          regulatory_anchor_enabled: true,
        }
      }
      const runRecord = await apiFetch<unknown>(`/reaction-projects/${reactionProjectId}/optimization/run`, {
        method: "POST",
        body: optimizationBody,
      })
      const t1 = typeof performance !== "undefined" ? performance.now() : Date.now()
      trackReactionOptimizationRunCompleted({
        reaction_project_id: reactionProjectId,
        experiment_count: experimentCount,
        objective,
        status,
        duration_seconds: (t1 - t0) / 1000,
      })
      setLastOptimizationRun(runRecord)
      setMsg({
        tone: "ok",
        text: "Optimization run finished — advisory results only; recommended next experiment choices still require human review.",
      })
      await reload()
    } catch (err) {
      setMsg({ tone: "err", text: formatApiError(err, "Optimization run failed.") })
    } finally {
      setBusy(null)
    }
  }

  async function runBayesianOptimization() {
    setMsg(null)
    setBusy("bo-optimization")
    const bs = boBatchSize.trim()
    const batch_size =
      bs && Number.isFinite(Number.parseInt(bs, 10)) ? Math.max(1, Number.parseInt(bs, 10)) : 1
    trackReactionBoRunStarted({
      reaction_project_id: reactionProjectId,
      algorithm: boAlgorithm,
      batch_size,
      objective_type: objectiveType,
      objective,
      experiment_count: experimentCount,
      completed_experiment_count: completedExperimentCount,
      status,
    })
    const t0 = typeof performance !== "undefined" ? performance.now() : Date.now()
    try {
      const ew = boExplorationWeight.trim()
      const exploration_weight =
        ew && Number.isFinite(Number.parseFloat(ew)) ? Number.parseFloat(ew) : null
      const body: Record<string, unknown> = {
        algorithm: boAlgorithm,
        batch_size,
        exploration_weight,
        cost_aware: boCostAware,
        safety_aware: boSafetyAware,
        include_failed_experiments_as_negative: boIncludeFailedAsNegative,
        notes: boNotes.trim() || null,
      }
      if (useRegulatoryAnchorInOptimization && regulatoryPayloadForOptimization) {
        body.regulatory_constraints_json = regulatoryPayloadForOptimization.regulatory_constraints
        body.compliance_objective_json = regulatoryPayloadForOptimization.compliance_objective
      }
      const runRecord = await apiFetch<unknown>(
        `/reaction-projects/${reactionProjectId}/optimization/bo/run`,
        {
          method: "POST",
          body,
        },
      )
      const t1 = typeof performance !== "undefined" ? performance.now() : Date.now()
      const duration_seconds = (t1 - t0) / 1000
      let runStatus = "ok"
      if (isRecord(runRecord) && typeof runRecord.status === "string" && runRecord.status.trim()) {
        runStatus = runRecord.status.trim()
      }
      let recommendation_count = 0
      if (isRecord(runRecord)) {
        const rj = runRecord.recommendations_json
        if (Array.isArray(rj)) recommendation_count = rj.length
        else {
          const recs = runRecord.recommendations
          if (Array.isArray(recs)) recommendation_count = recs.length
        }
      }
      trackReactionBoRunCompleted({
        reaction_project_id: reactionProjectId,
        algorithm: boAlgorithm,
        batch_size,
        objective_type: objectiveType,
        objective,
        experiment_count: experimentCount,
        completed_experiment_count: completedExperimentCount,
        status: runStatus,
        duration_seconds,
      })
      trackReactionRecommendationBatchCreated({
        reaction_project_id: reactionProjectId,
        algorithm: boAlgorithm,
        batch_size,
        objective_type: objectiveType,
        recommendation_count,
        completed_experiment_count: completedExperimentCount,
        status,
      })
      setLastBoRun(runRecord)
      setMsg({
        tone: "ok",
        text: "Bayesian optimization run finished — advisory results only; recommended next experiment choices still require human review.",
      })
      await reload()
    } catch (err) {
      const t1 = typeof performance !== "undefined" ? performance.now() : Date.now()
      trackReactionBoRunCompleted({
        reaction_project_id: reactionProjectId,
        algorithm: boAlgorithm,
        batch_size,
        objective_type: objectiveType,
        objective,
        experiment_count: experimentCount,
        completed_experiment_count: completedExperimentCount,
        status: "failed",
        duration_seconds: (t1 - t0) / 1000,
      })
      setMsg({ tone: "err", text: formatApiError(err, "Bayesian optimization run failed.") })
    } finally {
      setBusy(null)
    }
  }

  async function runBenchmark() {
    setMsg(null)
    setBusy("benchmark")
    const budgetRaw = benchmarkBudget.trim()
    const experiment_budget =
      budgetRaw && Number.isFinite(Number.parseInt(budgetRaw, 10))
        ? Math.max(1, Number.parseInt(budgetRaw, 10))
        : 20
    const algoTrim = benchmarkAlgorithm.trim()
    const objectiveForMeta = (benchmarkObjective.trim() || objective || "").trim()
    trackReactionBenchmarkRunStarted({
      reaction_project_id: reactionProjectId,
      algorithm: algoTrim || undefined,
      objective_type: objectiveForMeta || undefined,
      batch_size: experiment_budget,
      experiment_count: experimentCount,
      completed_experiment_count: completedExperimentCount,
      status,
    })
    const t0 = typeof performance !== "undefined" ? performance.now() : Date.now()
    try {
      const seedRaw = benchmarkSeed.trim()
      const random_seed =
        seedRaw === ""
          ? null
          : Number.isFinite(Number.parseInt(seedRaw, 10))
            ? Number.parseInt(seedRaw, 10)
            : null
      const runRecord = await apiFetch<unknown>(`/reaction-projects/${reactionProjectId}/optimization/benchmark`, {
        method: "POST",
        body: {
          benchmark_name: benchmarkName.trim() || null,
          algorithm: benchmarkAlgorithm.trim() || null,
          objective: benchmarkObjective.trim() || objective || null,
          experiment_budget,
          random_seed,
          use_completed_project_data: useCompletedProjectData,
        },
      })
      const t1 = typeof performance !== "undefined" ? performance.now() : Date.now()
      let benchStatus = "ok"
      if (isRecord(runRecord) && typeof runRecord.status === "string" && runRecord.status.trim()) {
        benchStatus = runRecord.status.trim()
      }
      trackReactionBenchmarkRunCompleted({
        reaction_project_id: reactionProjectId,
        algorithm: algoTrim || undefined,
        objective_type: objectiveForMeta || undefined,
        batch_size: experiment_budget,
        experiment_count: experimentCount,
        completed_experiment_count: completedExperimentCount,
        status: benchStatus,
        duration_seconds: (t1 - t0) / 1000,
      })
      setLastBenchmarkRun(runRecord)
      setMsg({
        tone: "ok",
        text: "Benchmark run finished — results describe behavior on this dataset only and do not prove universal superiority of any optimizer.",
      })
      await reload()
    } catch (err) {
      const t1 = typeof performance !== "undefined" ? performance.now() : Date.now()
      trackReactionBenchmarkRunCompleted({
        reaction_project_id: reactionProjectId,
        algorithm: algoTrim || undefined,
        objective_type: objectiveForMeta || undefined,
        batch_size: experiment_budget,
        experiment_count: experimentCount,
        completed_experiment_count: completedExperimentCount,
        status: "failed",
        duration_seconds: (t1 - t0) / 1000,
      })
      setMsg({ tone: "err", text: formatApiError(err, "Benchmark run failed.") })
    } finally {
      setBusy(null)
    }
  }

  async function runAdvisor() {
    setMsg(null)
    setBusy("advisor-run")
    const boParsed = advBoRunId.trim() ? Number.parseInt(advBoRunId.trim(), 10) : Number.NaN
    const bo_run_id = Number.isFinite(boParsed) ? boParsed : undefined
    trackReactionAdvisorRunStarted({
      reaction_project_id: reactionProjectId,
      advisor_mode: advisorMode,
      bo_run_id,
      status,
    })
    const t0 = typeof performance !== "undefined" ? performance.now() : Date.now()
    try {
      const metadata_json: Record<string, unknown> = {
        include_cost_safety_context: advIncludeCostSafety,
        include_completed_experiments: advIncludeCompletedExperiments,
        include_literature_priors: advIncludeLiteraturePriors,
      }
      const notesTrim = advNotes.trim()
      if (notesTrim) metadata_json.notes = notesTrim

      const body: Record<string, unknown> = {
        advisor_mode: advisorMode,
        metadata_json,
      }
      if (useRegulatoryAnchorInOptimization && regulatoryPayloadForOptimization) {
        body.regulatory_constraints_json = regulatoryPayloadForOptimization.regulatory_constraints
        body.compliance_objective_json = regulatoryPayloadForOptimization.compliance_objective
        metadata_json.regulatory_anchor_enabled = true
      }
      if (Number.isFinite(boParsed)) body.bo_run_id = boParsed
      const batchParsed = advBatchId.trim() ? Number.parseInt(advBatchId.trim(), 10) : Number.NaN
      if (Number.isFinite(batchParsed)) body.recommendation_batch_id = batchParsed

      const runRecord = await apiFetch<unknown>(`/reaction-projects/${reactionProjectId}/advisor/run`, {
        method: "POST",
        body,
      })
      let detail: unknown = runRecord
      const rid = isRecord(runRecord) ? readNum(runRecord.advisor_run_id ?? runRecord.id) : null
      if (rid != null) {
        try {
          detail = await apiFetch<unknown>(`/reaction-advisor-runs/${rid}`, { method: "GET" })
        } catch {
          detail = runRecord
        }
      }
      const t1 = typeof performance !== "undefined" ? performance.now() : Date.now()
      const detailRec = isRecord(detail) ? detail : null
      const warning_count = mergeRunStringLists(detailRec?.warnings, detailRec?.warnings_json).length
      const recommendation_count = readNum(detailRec?.recommendation_count) ?? undefined
      const runStatus =
        detailRec && typeof detailRec.status === "string" && detailRec.status.trim()
          ? detailRec.status.trim()
          : "ok"
      trackReactionAdvisorRunCompleted({
        reaction_project_id: reactionProjectId,
        advisor_mode: advisorMode,
        bo_run_id,
        recommendation_count,
        warning_count,
        status: runStatus,
        duration_seconds: (t1 - t0) / 1000,
      })
      setLastAdvisorRun(detail)
      setMsg({
        tone: "ok",
        text: "Advisor run finished — advisory results only; recommended next experiments still require human review.",
      })
      await reload()
    } catch (err) {
      const t1 = typeof performance !== "undefined" ? performance.now() : Date.now()
      trackReactionAdvisorRunCompleted({
        reaction_project_id: reactionProjectId,
        advisor_mode: advisorMode,
        bo_run_id,
        status: "failed",
        duration_seconds: (t1 - t0) / 1000,
      })
      setMsg({ tone: "err", text: formatApiError(err, "Advisor run failed.") })
    } finally {
      setBusy(null)
    }
  }

  async function postRecommendationAdvisorCritique(recId: number) {
    setMsg(null)
    setBusy(`critique-${recId}`)
    try {
      const data = await apiFetch<unknown>(`/reaction-recommendations/${recId}/advisor/critique`, {
        method: "POST",
        body: { metadata_json: {} },
      })
      setCritiqueByRecommendationId((prev) => ({ ...prev, [recId]: data }))
      const rec = isRecord(data) ? data : null
      const warning_count = Array.isArray(rec?.risk_flags) ? rec.risk_flags.length : 0
      trackReactionRecommendationCritiqued({
        reaction_project_id: reactionProjectId,
        recommendation_count: 1,
        warning_count,
        status:
          rec && typeof rec.recommendation === "string" && rec.recommendation.trim()
            ? rec.recommendation.trim()
            : "ok",
      })
      setMsg({
        tone: "ok",
        text: "Advisor critique recorded — advisory interpretation only; requires human review before execution.",
      })
    } catch (err) {
      setMsg({ tone: "err", text: formatApiError(err, "Advisor critique failed.") })
    } finally {
      setBusy(null)
    }
  }

  async function getRecommendationAdvisorCritique(recId: number) {
    setMsg(null)
    setBusy(`critique-${recId}`)
    try {
      const data = await apiFetch<unknown>(`/reaction-recommendations/${recId}/advisor/critique`, {
        method: "GET",
      })
      setCritiqueByRecommendationId((prev) => ({ ...prev, [recId]: data }))
      setMsg({ tone: "ok", text: "Advisor critique loaded." })
    } catch (err) {
      setMsg({ tone: "err", text: formatApiError(err, "Could not load advisor critique.") })
    } finally {
      setBusy(null)
    }
  }

  async function createMechanisticHypothesis(e: React.FormEvent) {
    e.preventDefault()
    setMsg(null)
    const title = mhTitle.trim()
    const hypothesis = mhHypothesis.trim()
    if (!title || !hypothesis) {
      setMsg({ tone: "err", text: "title and hypothesis are required." })
      return
    }
    let supporting_observations_json: unknown
    let contradicting_observations_json: unknown
    try {
      const rawS = mhSupportingJson.trim()
      const rawC = mhContradictingJson.trim()
      supporting_observations_json = rawS ? (JSON.parse(rawS) as unknown) : []
      contradicting_observations_json = rawC ? (JSON.parse(rawC) as unknown) : []
    } catch {
      setMsg({
        tone: "err",
        text: "supporting_observations_json and contradicting_observations_json must be valid JSON when provided.",
      })
      return
    }
    setBusy("mh-create")
    try {
      await apiFetch(`/reaction-projects/${reactionProjectId}/mechanistic-hypotheses`, {
        method: "POST",
        body: {
          title,
          hypothesis,
          supporting_observations_json,
          contradicting_observations_json,
          confidence_label: mhConfidence,
          status: "proposed",
          metadata_json: {},
        },
      })
      trackReactionMechanisticHypothesisCreated({
        reaction_project_id: reactionProjectId,
        status: "created",
      })
      setMhTitle("")
      setMhHypothesis("")
      setMhConfidence("speculative")
      setMhSupportingJson("")
      setMhContradictingJson("")
      setMsg({ tone: "ok", text: "Mechanistic hypothesis created." })
      await reload()
    } catch (err) {
      setMsg({ tone: "err", text: formatApiError(err, "Create mechanistic hypothesis failed.") })
    } finally {
      setBusy(null)
    }
  }

  async function patchMechanisticHypothesis(hypothesisId: number, body: Record<string, unknown>) {
    setMsg(null)
    setBusy(`mh-patch-${hypothesisId}`)
    try {
      await apiFetch(`/reaction-mechanistic-hypotheses/${hypothesisId}`, {
        method: "PATCH",
        body,
      })
      setMsg({ tone: "ok", text: "Mechanistic hypothesis updated." })
      await reload()
    } catch (err) {
      setMsg({ tone: "err", text: formatApiError(err, "Update mechanistic hypothesis failed.") })
    } finally {
      setBusy(null)
    }
  }

  async function createLiteraturePrior(e: React.FormEvent) {
    e.preventDefault()
    setMsg(null)
    const title = lpTitle.trim()
    const summary = lpSummary.trim()
    if (!title || !summary) {
      setMsg({ tone: "err", text: "title and summary are required." })
      return
    }
    let relevance_tags_json: unknown
    try {
      const raw = lpTagsJson.trim()
      relevance_tags_json = raw ? (JSON.parse(raw) as unknown) : []
    } catch {
      setMsg({ tone: "err", text: "relevance_tags_json must be valid JSON when provided." })
      return
    }
    const citeTrim = lpCitation.trim()
    setBusy("lp-create")
    try {
      await apiFetch(`/reaction-projects/${reactionProjectId}/literature-priors`, {
        method: "POST",
        body: {
          source_type: lpSourceType,
          title,
          summary,
          citation: citeTrim.length > 0 ? citeTrim : null,
          relevance_tags_json,
          metadata_json: {},
        },
      })
      trackReactionPriorAdded({
        reaction_project_id: reactionProjectId,
        status: "created",
      })
      setLpTitle("")
      setLpSummary("")
      setLpCitation("")
      setLpTagsJson("")
      setLpSourceType("user_note")
      setMsg({ tone: "ok", text: "Literature prior created." })
      await reload()
    } catch (err) {
      setMsg({ tone: "err", text: formatApiError(err, "Create literature prior failed.") })
    } finally {
      setBusy(null)
    }
  }

  async function compareBoAdvisorRecommendations() {
    setMsg(null)
    setBusy("bo-advisor-compare")
    try {
      const body: Record<string, unknown> = { metadata_json: {} }
      const boParsed = cmpBoRunId.trim() ? Number.parseInt(cmpBoRunId.trim(), 10) : Number.NaN
      if (Number.isFinite(boParsed)) body.bo_run_id = boParsed
      const advisorParsed = cmpAdvisorRunId.trim() ? Number.parseInt(cmpAdvisorRunId.trim(), 10) : Number.NaN
      if (Number.isFinite(advisorParsed)) body.advisor_run_id = advisorParsed
      const data = await apiFetch<unknown>(`/reaction-projects/${reactionProjectId}/advisor/compare-bo-llm`, {
        method: "POST",
        body,
      })
      const rec = isRecord(data) ? data : null
      trackReactionBoAdvisorComparisonRun({
        reaction_project_id: reactionProjectId,
        bo_run_id: readNum(rec?.bo_run_id) ?? undefined,
        warning_count: Array.isArray(rec?.disagreements) ? rec.disagreements.length : 0,
        status:
          rec && typeof rec.final_review_recommendation === "string" && rec.final_review_recommendation.trim()
            ? rec.final_review_recommendation.trim()
            : "ok",
      })
      setLastComparison(data)
      setMsg({
        tone: "ok",
        text: "BO vs Advisor comparison created — this output is decision-support only and requires review.",
      })
      await reload()
    } catch (err) {
      setMsg({ tone: "err", text: formatApiError(err, "BO vs Advisor comparison failed.") })
    } finally {
      setBusy(null)
    }
  }

  async function saveAdvisorReview() {
    setMsg(null)
    const ridRaw = advisorReviewRunId.trim()
    const rid = ridRaw ? Number.parseInt(ridRaw, 10) : Number.NaN
    const rationale = advisorReviewRationale.trim()
    if (!Number.isFinite(rid)) {
      setMsg({ tone: "err", text: "advisor_run_id is required." })
      return
    }
    if (!rationale) {
      setMsg({ tone: "err", text: "rationale is required." })
      return
    }
    setBusy("advisor-review-save")
    try {
      const data = await apiFetch<unknown>(`/reaction-advisor-runs/${rid}/review`, {
        method: "POST",
        body: {
          reviewer_name: advisorReviewerName.trim() || null,
          decision: advisorReviewDecision,
          rationale,
          metadata_json: {},
        },
      })
      trackReactionAdvisorReviewSaved({
        reaction_project_id: reactionProjectId,
        bo_run_id: readNum(isRecord(data) ? data.bo_run_id : null) ?? undefined,
        status: advisorReviewDecision,
      })
      if (isRecord(data)) setLastAdvisorRun(data)
      setMsg({
        tone: "ok",
        text: "Advisor review saved — accepted output remains advisory and does not schedule experiments automatically.",
      })
      await reload()
    } catch (err) {
      setMsg({ tone: "err", text: formatApiError(err, "Save advisor review failed.") })
    } finally {
      setBusy(null)
    }
  }

  async function approveRecommendation(id: number) {
    setBusy(`approve-${id}`)
    setMsg(null)
    const name = revReviewerName.trim()
    const comment = revComment[id]?.trim() ?? ""
    if (!name || !comment) {
      setMsg({
        tone: "err",
        text: "Reviewer name and review comment are required before approval.",
      })
      setBusy(null)
      return
    }
    try {
      await apiFetch(`/reaction-recommendations/${id}/approve`, {
        method: "POST",
        body: {
          reviewer_name: name,
          reviewer_comment: comment,
          rationale: comment,
          metadata_json: {},
        },
      })
      trackReactionRecommendationApproved({
        reaction_project_id: reactionProjectId,
        experiment_count: experimentCount,
        objective,
        objective_type: objectiveType,
        completed_experiment_count: completedExperimentCount,
        recommendation_count: sortedRecs.length,
        status: "approved",
      })
      setMsg({ tone: "ok", text: "Recommendation recorded as approved." })
      await reload()
    } catch (err) {
      setMsg({ tone: "err", text: formatApiError(err, "Approve failed.") })
    } finally {
      setBusy(null)
    }
  }

  async function rejectRecommendation(id: number) {
    setBusy(`reject-${id}`)
    setMsg(null)
    const name = revReviewerName.trim()
    const comment = revComment[id]?.trim() ?? ""
    if (!name || !comment) {
      setMsg({
        tone: "err",
        text: "Reviewer name and review comment are required before rejection.",
      })
      setBusy(null)
      return
    }
    try {
      await apiFetch(`/reaction-recommendations/${id}/reject`, {
        method: "POST",
        body: {
          reviewer_name: name,
          reviewer_comment: comment,
          rationale: comment,
          metadata_json: {},
        },
      })
      trackReactionRecommendationRejected({
        reaction_project_id: reactionProjectId,
        experiment_count: experimentCount,
        objective,
        objective_type: objectiveType,
        completed_experiment_count: completedExperimentCount,
        recommendation_count: sortedRecs.length,
        status: "rejected",
      })
      setMsg({ tone: "ok", text: "Recommendation recorded as rejected." })
      await reload()
    } catch (err) {
      setMsg({ tone: "err", text: formatApiError(err, "Reject failed.") })
    } finally {
      setBusy(null)
    }
  }

  async function convertRecommendationToPlannedExperiment(recommendation_id: number) {
    setBusy(`convert-rec-${recommendation_id}`)
    setMsg(null)
    const rationale = convertRecRationale.trim()
    if (!rationale) {
      setMsg({ tone: "err", text: "rationale is required before conversion (POST body field)." })
      setBusy(null)
      return
    }
    const rid = convertRecExecutionBatchId.trim()
    let execution_batch_id: number | undefined
    if (rid && rid !== "__none__") {
      const n = Number.parseInt(rid, 10)
      if (!Number.isFinite(n) || n < 1) {
        setMsg({ tone: "err", text: "execution_batch_id must be a positive integer when provided." })
        setBusy(null)
        return
      }
      execution_batch_id = n
    }
    try {
      const body: Record<string, unknown> = {
        rationale,
        metadata_json: {},
      }
      if (execution_batch_id != null) body.execution_batch_id = execution_batch_id
      const reviewer = revReviewerName.trim()
      if (reviewer) body.reviewer_name = reviewer

      const data = await apiFetch<unknown>(`/reaction-recommendations/${recommendation_id}/convert-to-experiment`, {
        method: "POST",
        body,
      })
      const rec = isRecord(data) ? data : null
      const exp = rec && isRecord(rec.experiment) ? rec.experiment : null
      const item = rec && isRecord(rec.execution_item) ? rec.execution_item : null
      const experiment_id = exp ? readNum(exp.id) : null
      const experiment_status = exp && typeof exp.status === "string" ? exp.status : "planned"
      const execution_item_id = item ? readNum(item.id) : null
      if (experiment_id != null) {
        setExecutionPlanningRows((prev) => {
          const map = new Map(prev.map((row) => [row.recommendation_id, row]))
          map.set(recommendation_id, {
            recommendation_id,
            experiment_id,
            experiment_status,
            execution_item_id,
          })
          return [...map.values()].sort((a, b) => b.recommendation_id - a.recommendation_id)
        })
      }
      setMsg({
        tone: "ok",
        text:
          experiment_id != null
            ? `Planned experiment recorded (experiment id ${experiment_id}; status ${experiment_status}). Saving a conversion does not mean the experiment was performed in the lab.`
            : "Conversion response received — check experiment list if the backend returned an experiment.",
      })
      trackReactionRecommendationConvertedToExperiment({
        reaction_project_id: reactionProjectId,
        ...(execution_batch_id != null ? { batch_id: execution_batch_id } : {}),
        ...(execution_item_id != null ? { item_id: execution_item_id } : {}),
        status: experiment_status,
      })
      await reload()
    } catch (err) {
      setMsg({
        tone: "err",
        text: formatApiError(err, "POST /reaction-recommendations/{recommendation_id}/convert-to-experiment failed."),
      })
    } finally {
      setBusy(null)
    }
  }

  async function createExecutionBatchPlanner(e: React.FormEvent) {
    e.preventDefault()
    setMsg(null)
    const batch_code = plEbBatchCode.trim()
    if (!batch_code) {
      setMsg({ tone: "err", text: "batch_code is required (POST body field)." })
      return
    }
    setBusy("exec-batch-create")
    try {
      const metadata_json: Record<string, unknown> = {}
      const n = plEbNotes.trim()
      if (n) metadata_json.notes = n
      const body: Record<string, unknown> = {
        batch_code,
        title: plEbTitle.trim() || null,
        status: "draft",
        metadata_json,
      }
      const ps = plannedDatetimeLocalInputToIsoOrUndefined(plEbPlannedStart)
      const pe = plannedDatetimeLocalInputToIsoOrUndefined(plEbPlannedEnd)
      if (ps) body.planned_start = ps
      if (pe) body.planned_end = pe
      const created = await apiFetch<unknown>(`/reaction-projects/${reactionProjectId}/execution-batches`, {
        method: "POST",
        body,
      })
      const newId = isRecord(created) ? readNum(created.id) : null
      const createdStatus =
        isRecord(created) && typeof created.status === "string" && created.status.trim()
          ? created.status.trim()
          : "draft"
      trackReactionExecutionBatchCreated({
        reaction_project_id: reactionProjectId,
        ...(newId != null ? { batch_id: newId } : {}),
        status: createdStatus,
      })
      setMsg({ tone: "ok", text: "Execution batch created (planning record)." })
      setPlEbBatchCode("")
      setPlEbTitle("")
      setPlEbPlannedStart("")
      setPlEbPlannedEnd("")
      setPlEbNotes("")
      if (newId != null) setPlannerSelectedBatchId(newId)
      await reload()
    } catch (err) {
      setMsg({
        tone: "err",
        text: formatApiError(err, "POST /reaction-projects/{reaction_project_id}/execution-batches failed."),
      })
    } finally {
      setBusy(null)
    }
  }

  async function addExecutionPlannerItem(e: React.FormEvent) {
    e.preventDefault()
    setMsg(null)
    if (plannerSelectedBatchId == null || !Number.isFinite(plannerSelectedBatchId)) {
      setMsg({ tone: "err", text: "Open an execution batch first (batch_id from GET list)." })
      return
    }
    const item_code = execPlannerItemCode.trim()
    if (!item_code) {
      setMsg({ tone: "err", text: "item_code is required (POST body field)." })
      return
    }
    const exRaw = execPlannerExperimentId.trim()
    if (!exRaw || exRaw === "__none__") {
      setMsg({
        tone: "err",
        text: "Select a planned experiment — experiment_id links the item to stored conditions.",
      })
      return
    }
    const experiment_id = Number.parseInt(exRaw, 10)
    if (!Number.isFinite(experiment_id) || experiment_id < 1) {
      setMsg({ tone: "err", text: "experiment_id must be a positive integer." })
      return
    }
    const chosen = plannedExperimentsForPlanner.some((row) => readNum(row.id) === experiment_id)
    if (!chosen) {
      setMsg({ tone: "err", text: "Selected experiment must have status planned in the current GET experiments list." })
      return
    }
    let checklist_json: unknown = []
    const ck = execPlannerChecklistJsonText.trim()
    if (ck) {
      try {
        checklist_json = JSON.parse(ck) as unknown
      } catch {
        setMsg({ tone: "err", text: "checklist_json must parse as JSON (array or object)." })
        return
      }
    }
    setBusy("exec-item-add")
    try {
      const body: Record<string, unknown> = {
        item_code,
        experiment_id,
        status: "planned",
        checklist_json,
        metadata_json: {},
      }
      const op = execPlannerOperatorName.trim()
      if (op) body.operator_name = op
      await apiFetch(`/reaction-execution-batches/${plannerSelectedBatchId}/items`, {
        method: "POST",
        body,
      })
      setMsg({ tone: "ok", text: "Execution item added to batch (planning record)." })
      setExecPlannerItemCode("")
      setExecPlannerOperatorName("")
      setExecPlannerChecklistJsonText("")
      await reload()
    } catch (err) {
      setMsg({
        tone: "err",
        text: formatApiError(err, "POST /reaction-execution-batches/{batch_id}/items failed."),
      })
    } finally {
      setBusy(null)
    }
  }

  function openExecutionBoardDialog(
    kind: "run" | "done" | "fail" | "checklist" | "note",
    item: Record<string, unknown>,
  ) {
    const id = readNum(item.id)
    if (id == null) return
    setBoardDialog({ kind, itemId: id })
    setBoardDialogOperator(typeof item.operator_name === "string" ? item.operator_name : "")
    setBoardDialogMessage("")
    setBoardDialogFailureReason("")
    setBoardDialogNote("")
    if (kind === "checklist") {
      try {
        setBoardDialogChecklistJson(JSON.stringify(item.checklist_json ?? [], null, 2))
      } catch {
        setBoardDialogChecklistJson("[]")
      }
    } else {
      setBoardDialogChecklistJson("")
    }
  }

  function closeExecutionBoardDialog() {
    setBoardDialog(null)
    setBoardDialogOperator("")
    setBoardDialogMessage("")
    setBoardDialogFailureReason("")
    setBoardDialogNote("")
    setBoardDialogChecklistJson("")
  }

  async function submitExecutionBoardDialog(e: React.FormEvent) {
    e.preventDefault()
    if (boardDialog == null) return
    const { kind, itemId } = boardDialog
    setBusy(`board-${kind}-${itemId}`)
    setMsg(null)
    try {
      if (kind === "run") {
        const body: Record<string, unknown> = { metadata_json: {} }
        const op = boardDialogOperator.trim()
        const msg = boardDialogMessage.trim()
        if (op) body.operator_name = op
        if (msg) body.message = msg
        await apiFetch(`/reaction-execution-items/${itemId}/mark-running`, { method: "POST", body })
        trackReactionExecutionItemStarted({
          reaction_project_id: reactionProjectId,
          batch_id: executionBatchIdForBoardItem(itemId),
          item_id: itemId,
          status: "running",
        })
        setMsg({ tone: "ok", text: "Execution item marked running." })
      } else if (kind === "done") {
        const body: Record<string, unknown> = { metadata_json: {} }
        const op = boardDialogOperator.trim()
        const msg = boardDialogMessage.trim()
        if (op) body.operator_name = op
        if (msg) body.message = msg
        await apiFetch(`/reaction-execution-items/${itemId}/mark-completed`, { method: "POST", body })
        trackReactionExecutionItemCompleted({
          reaction_project_id: reactionProjectId,
          batch_id: executionBatchIdForBoardItem(itemId),
          item_id: itemId,
          status: "completed",
        })
        setMsg({
          tone: "ok",
          text: "Execution item marked completed — human-recorded status; other records may still require review.",
        })
      } else if (kind === "fail") {
        const failure_reason = boardDialogFailureReason.trim()
        if (!failure_reason) {
          setMsg({ tone: "err", text: "failure_reason is required for POST …/mark-failed." })
          setBusy(null)
          return
        }
        const body: Record<string, unknown> = { failure_reason, metadata_json: {} }
        const op = boardDialogOperator.trim()
        if (op) body.operator_name = op
        await apiFetch(`/reaction-execution-items/${itemId}/mark-failed`, { method: "POST", body })
        trackReactionExecutionItemFailed({
          reaction_project_id: reactionProjectId,
          batch_id: executionBatchIdForBoardItem(itemId),
          item_id: itemId,
          status: "failed",
        })
        setMsg({ tone: "ok", text: "Execution item marked failed." })
      } else if (kind === "checklist") {
        let checklist_json: unknown
        try {
          checklist_json = JSON.parse(boardDialogChecklistJson) as unknown
        } catch {
          setMsg({ tone: "err", text: "checklist_json must be valid JSON." })
          setBusy(null)
          return
        }
        await apiFetch(`/reaction-execution-items/${itemId}`, {
          method: "PATCH",
          body: { checklist_json },
        })
        setMsg({ tone: "ok", text: "checklist_json PATCH saved." })
      } else if (kind === "note") {
        const text = boardDialogNote.trim()
        if (!text) {
          setMsg({ tone: "err", text: "Note text is required." })
          setBusy(null)
          return
        }
        const item = executionBoardItemRecords.find((r) => readNum(r.id) === itemId)
        const prevMd = item && isRecord(item.metadata_json) ? { ...item.metadata_json } : {}
        const notes = Array.isArray(prevMd.execution_board_notes)
          ? [...(prevMd.execution_board_notes as unknown[])]
          : []
        notes.push({ message: text, recorded_at: new Date().toISOString() })
        await apiFetch(`/reaction-execution-items/${itemId}`, {
          method: "PATCH",
          body: { metadata_json: { ...prevMd, execution_board_notes: notes } },
        })
        setMsg({ tone: "ok", text: "Note appended via PATCH metadata_json." })
      }
      closeExecutionBoardDialog()
      await reload()
    } catch (err) {
      setMsg({ tone: "err", text: formatApiError(err, "Execution board action failed.") })
    } finally {
      setBusy(null)
    }
  }

  async function loadExecutionItemAnalyticalResults(executionItemId: number) {
    setAnalyticalResultsLoadingItemId(executionItemId)
    try {
      const rows = await apiFetch<unknown>(`/reaction-execution-items/${executionItemId}/analytical-results`, {
        method: "GET",
      })
      setAnalyticalResultsByExecutionItemId((prev) => ({
        ...prev,
        [executionItemId]: Array.isArray(rows) ? rows : [],
      }))
    } catch {
      setAnalyticalResultsByExecutionItemId((prev) => ({ ...prev, [executionItemId]: [] }))
    } finally {
      setAnalyticalResultsLoadingItemId(null)
    }
  }

  async function addAnalyticalResultToExecutionItem(e: React.FormEvent) {
    e.preventDefault()
    setMsg(null)
    const executionItemId = selectedAnalyticalExecutionItemId
    if (executionItemId == null || executionItemId < 1) {
      setMsg({ tone: "err", text: "execution_item_id is required." })
      return
    }
    const parseOptionalPositiveInt = (raw: string): number | null | "invalid" => {
      const t = raw.trim()
      if (!t) return null
      const n = Number.parseInt(t, 10)
      if (!Number.isFinite(n) || n < 1) return "invalid"
      return n
    }
    const spectracheck_session_id = parseOptionalPositiveInt(arSpectraCheckSessionId)
    const file_id = parseOptionalPositiveInt(arFileId)
    const artifact_id = parseOptionalPositiveInt(arArtifactId)
    if (spectracheck_session_id === "invalid" || file_id === "invalid" || artifact_id === "invalid") {
      setMsg({ tone: "err", text: "session_id, file_id, and artifact_id must be positive integers when provided." })
      return
    }
    let summary_json: unknown = {}
    const summaryRaw = arSummaryText.trim()
    if (summaryRaw) {
      try {
        summary_json = JSON.parse(summaryRaw) as unknown
      } catch {
        summary_json = { summary_text: summaryRaw }
      }
    }
    setBusy("exec-analytical-add")
    try {
      const body: Record<string, unknown> = {
        result_type: arResultType,
        summary_json: isRecord(summary_json) ? summary_json : { value: summary_json },
        metadata_json: {},
      }
      if (spectracheck_session_id != null) body.spectracheck_session_id = spectracheck_session_id
      if (file_id != null) body.file_id = file_id
      if (artifact_id != null) body.artifact_id = artifact_id
      const source_hash = arSourceHash.trim()
      if (source_hash) body.source_hash = source_hash

      await apiFetch(`/reaction-execution-items/${executionItemId}/analytical-results`, {
        method: "POST",
        body,
      })
      trackReactionAnalyticalResultLinked({
        reaction_project_id: reactionProjectId,
        batch_id: executionBatchIdForBoardItem(executionItemId),
        item_id: executionItemId,
        result_type: arResultType,
        has_spectracheck_link: typeof spectracheck_session_id === "number",
        has_artifact_id: typeof artifact_id === "number",
      })
      setArResultType(ANALYTICAL_RESULT_TYPE_OPTIONS[0])
      setArSpectraCheckSessionId("")
      setArFileId("")
      setArArtifactId("")
      setArSourceHash("")
      setArSummaryText("")
      setMsg({ tone: "ok", text: "Analytical result linked to execution item." })
      await loadExecutionItemAnalyticalResults(executionItemId)
    } catch (err) {
      setMsg({
        tone: "err",
        text: formatApiError(err, "POST /reaction-execution-items/{item_id}/analytical-results failed."),
      })
    } finally {
      setBusy(null)
    }
  }

  function applyProposedOutcomeToConfirmedFields(po: Record<string, unknown>) {
    setOeConfirmedYieldPercent(proposedOutcomeScalarToInput(po.yield_percent))
    setOeConfirmedConversionPercent(proposedOutcomeScalarToInput(po.conversion_percent))
    setOeConfirmedSelectivityPercent(proposedOutcomeScalarToInput(po.selectivity_percent))
    setOeConfirmedImpurityPercent(proposedOutcomeScalarToInput(po.impurity_percent))
    setOeConfirmedIsolatedYieldPercent(proposedOutcomeScalarToInput(po.isolated_yield_percent))
    setOeConfirmedLcmsAreaPercent(proposedOutcomeScalarToInput(po.lcms_area_percent))
    setOeConfirmedNmrPurityPercent(proposedOutcomeScalarToInput(po.nmr_purity_percent))
    const n = po.notes
    setOeConfirmedNotes(
      typeof n === "string" ? n : typeof n === "number" && Number.isFinite(n) ? String(n) : "",
    )
  }

  function buildConfirmedOutcomeJsonFromOutcomeForm():
    | { ok: true; json: Record<string, unknown> }
    | { ok: false; error: string } {
    const pctPairs: readonly [field: string, raw: string][] = [
      ["yield_percent", oeConfirmedYieldPercent],
      ["conversion_percent", oeConfirmedConversionPercent],
      ["selectivity_percent", oeConfirmedSelectivityPercent],
      ["impurity_percent", oeConfirmedImpurityPercent],
      ["isolated_yield_percent", oeConfirmedIsolatedYieldPercent],
      ["lcms_area_percent", oeConfirmedLcmsAreaPercent],
      ["nmr_purity_percent", oeConfirmedNmrPurityPercent],
    ]
    const out: Record<string, unknown> = {}
    for (const [field, raw] of pctPairs) {
      const t = raw.trim()
      if (!t) continue
      const n = Number.parseFloat(t)
      if (!Number.isFinite(n)) return { ok: false, error: `${field} must be a finite number.` }
      if (n < 0 || n > 100) return { ok: false, error: `${field} must be between 0 and 100.` }
      out[field] = Math.round(n * 1e6) / 1e6
    }
    const note = oeConfirmedNotes.trim()
    if (note) out.notes = note
    return { ok: true, json: out }
  }

  async function extractProposedOutcome() {
    setMsg(null)
    const executionItemId = selectedOutcomeExecutionItemId
    if (executionItemId == null || executionItemId < 1) {
      setMsg({ tone: "err", text: "execution_item_id is required." })
      return
    }

    let analytical_result_id: number | undefined
    const arChoice = oeAnalyticalResultIdChoice.trim()
    if (arChoice !== "" && arChoice !== "__all__") {
      const nar = Number.parseInt(arChoice, 10)
      if (!Number.isFinite(nar) || nar < 1) {
        setMsg({ tone: "err", text: "analytical_result_id must be a positive integer when provided." })
        return
      }
      analytical_result_id = nar
    }

    const body: Record<string, unknown> = {
      extraction_method: oeExtractionMethod,
      metadata_json: {},
    }
    if (analytical_result_id != null) body.analytical_result_id = analytical_result_id

    setBusy("exec-outcome-extract")
    try {
      const raw = await apiFetch<unknown>(`/reaction-execution-items/${executionItemId}/extract-outcome`, {
        method: "POST",
        body,
      })
      if (!isRecord(raw)) throw new Error("Unexpected response envelope.")
      let merged = raw
      const rid = readNum(raw.id)
      if (rid != null) {
        const refreshed = await apiFetch<unknown>(`/reaction-outcome-extraction-runs/${rid}`, { method: "GET" })
        if (isRecord(refreshed)) merged = refreshed
      }
      setOeExtractionRun(merged)
      const po = merged.proposed_outcome_json
      applyProposedOutcomeToConfirmedFields(isRecord(po) ? po : {})
      const extStat =
        typeof merged.status === "string" && merged.status.trim() ? merged.status.trim() : undefined
      trackReactionOutcomeExtractionRun({
        reaction_project_id: reactionProjectId,
        batch_id: executionBatchIdForBoardItem(executionItemId),
        item_id: executionItemId,
        outcome_fields_count: countClosedLoopOutcomeFieldKeys(isRecord(po) ? po : {}),
        ...(extStat ? { status: extStat } : {}),
      })
      setMsg({
        tone: "ok",
        text: "Proposed outcome extracted; requires confirmation before it becomes official.",
      })
    } catch (err) {
      setMsg({
        tone: "err",
        text: formatApiError(err, "POST /reaction-execution-items/{item_id}/extract-outcome failed."),
      })
    } finally {
      setBusy(null)
    }
  }

  async function confirmRecordedOutcome(e: React.FormEvent) {
    e.preventDefault()
    setMsg(null)

    const executionItemId = selectedOutcomeExecutionItemId
    if (executionItemId == null || executionItemId < 1) {
      setMsg({ tone: "err", text: "execution_item_id is required." })
      return
    }

    const rationale = oeConfirmRationale.trim()
    if (!rationale) {
      setMsg({
        tone: "err",
        text: "Provide a confirmation rationale (reviewer comment). Reviewer_name is recommended when available.",
      })
      return
    }

    const reviewer_name = oeReviewerName.trim()

    const extraction_run_id = readNum(oeExtractionRun?.id)
    const built = buildConfirmedOutcomeJsonFromOutcomeForm()
    if (!built.ok) {
      setMsg({ tone: "err", text: built.error })
      return
    }

    if (Object.keys(built.json).length === 0 && extraction_run_id == null) {
      setMsg({
        tone: "err",
        text: "Run extract-outcome first, or fill at least one confirmed outcome field before confirming.",
      })
      return
    }

    const body: Record<string, unknown> = {
      rationale,
      metadata_json: {},
    }
    if (reviewer_name) body.reviewer_name = reviewer_name
    if (extraction_run_id != null) body.extraction_run_id = extraction_run_id
    if (Object.keys(built.json).length > 0) body.confirmed_outcome_json = built.json

    const outcomeCountEnvelope: Record<string, unknown> =
      Object.keys(built.json).length > 0
        ? built.json
        : oeExtractionRun != null && isRecord(oeExtractionRun.proposed_outcome_json)
          ? oeExtractionRun.proposed_outcome_json
          : {}

    setBusy("exec-outcome-confirm")
    try {
      await apiFetch(`/reaction-execution-items/${executionItemId}/confirm-outcome`, {
        method: "POST",
        body,
      })
      trackReactionOutcomeConfirmed({
        reaction_project_id: reactionProjectId,
        batch_id: executionBatchIdForBoardItem(executionItemId),
        item_id: executionItemId,
        outcome_fields_count: countClosedLoopOutcomeFieldKeys(outcomeCountEnvelope),
        status: extraction_run_id != null ? "with_extraction_run" : "without_extraction_run",
      })
      setMsg({ tone: "ok", text: "Confirmed outcome applied to official experiment outcome_json." })
      setOeExtractionRun(null)
      setOeConfirmedYieldPercent("")
      setOeConfirmedConversionPercent("")
      setOeConfirmedSelectivityPercent("")
      setOeConfirmedImpurityPercent("")
      setOeConfirmedIsolatedYieldPercent("")
      setOeConfirmedLcmsAreaPercent("")
      setOeConfirmedNmrPurityPercent("")
      setOeConfirmedNotes("")
      setOeConfirmRationale("")
      await reload()
    } catch (err) {
      setMsg({
        tone: "err",
        text: formatApiError(err, "POST /reaction-execution-items/{item_id}/confirm-outcome failed."),
      })
    } finally {
      setBusy(null)
    }
  }

  async function loadOptimizationCycleDetail(cycleId: number) {
    setOptimizationCycleDetailLoadingId(cycleId)
    try {
      const raw = await apiFetch<unknown>(`/reaction-optimization-cycles/${cycleId}`, { method: "GET" })
      if (isRecord(raw)) {
        setOptimizationCycleDetailById((prev) => ({ ...prev, [cycleId]: raw }))
      }
    } catch {
      /* detail optional on failure — list envelope still renders */
    } finally {
      setOptimizationCycleDetailLoadingId(null)
    }
  }

  async function createOptimizationCycleRecord(e: React.FormEvent) {
    e.preventDefault()
    setMsg(null)
    if (!Number.isFinite(reactionProjectId) || reactionProjectId < 1) return

    const body: Record<string, unknown> = {
      status: optCcStatus,
      metadata_json: {},
    }

    const cn = optCcCycleNumber.trim()
    if (cn) {
      const n = Number.parseInt(cn, 10)
      if (!Number.isFinite(n) || n < 1) {
        setMsg({ tone: "err", text: "cycle_number must be a positive integer when provided." })
        return
      }
      body.cycle_number = n
    }

    const eb = optCcExecutionBatchId.trim()
    if (eb !== "" && eb !== "__none__") {
      const bid = Number.parseInt(eb, 10)
      if (!Number.isFinite(bid) || bid < 1) {
        setMsg({ tone: "err", text: "execution_batch_id must be a positive integer when selected." })
        return
      }
      body.execution_batch_id = bid
    }

    const addOptionalPositiveIntField = (raw: string, field: string): boolean => {
      const t = raw.trim()
      if (!t) return true
      const n = Number.parseInt(t, 10)
      if (!Number.isFinite(n) || n < 1) {
        setMsg({ tone: "err", text: `${field} must be a positive integer when provided.` })
        return false
      }
      body[field] = n
      return true
    }
    if (!addOptionalPositiveIntField(optCcBoRunId, "bo_run_id")) return
    if (!addOptionalPositiveIntField(optCcAdvisorRunId, "advisor_run_id")) return
    if (!addOptionalPositiveIntField(optCcRecBatchId, "recommendation_batch_id")) return

    setBusy("opt-cc-create")
    try {
      const createdCc = await apiFetch<unknown>(`/reaction-projects/${reactionProjectId}/optimization-cycles`, {
        method: "POST",
        body,
      })
      const crRow = isRecord(createdCc) ? createdCc : null
      const ccNum = crRow ? readNum(crRow.cycle_number) : null
      const ccBatch =
        typeof body.execution_batch_id === "number"
          ? body.execution_batch_id
          : crRow != null
            ? readNum(crRow.execution_batch_id)
            : null
      trackReactionOptimizationCycleCreated({
        reaction_project_id: reactionProjectId,
        ...(ccBatch != null ? { batch_id: ccBatch } : {}),
        ...(ccNum != null ? { cycle_number: ccNum } : {}),
        status: optCcStatus,
      })
      setMsg({ tone: "ok", text: "Optimization cycle created." })
      setOptCcCycleNumber("")
      setOptCcBoRunId("")
      setOptCcAdvisorRunId("")
      setOptCcRecBatchId("")
      await reload()
    } catch (err) {
      setMsg({
        tone: "err",
        text: formatApiError(err, "POST /reaction-projects/{reaction_project_id}/optimization-cycles failed."),
      })
    } finally {
      setBusy(null)
    }
  }

  async function submitOptimizationCycleDecision(cycleId: number, e: React.FormEvent) {
    e.preventDefault()
    setMsg(null)
    const rationale = occRationale.trim()
    if (!rationale) {
      setMsg({ tone: "err", text: "Decision rationale is required." })
      return
    }

    const body: Record<string, unknown> = {
      decision: occDecision,
      rationale,
      metadata_json: {},
    }
    const rev = occReviewer.trim()
    if (rev) body.reviewer_name = rev

    setBusy(`opt-cc-dec-${cycleId}`)
    try {
      await apiFetch(`/reaction-optimization-cycles/${cycleId}/decision`, {
        method: "POST",
        body,
      })
      const decCycleRow =
        optimizationCyclesList
          .filter(isRecord)
          .find((x) => readNum(x.id) === cycleId) ?? null
      const decCn = decCycleRow != null ? readNum(decCycleRow.cycle_number) : null
      const decEb = decCycleRow != null ? readNum(decCycleRow.execution_batch_id) : null
      trackReactionCycleDecisionSaved({
        reaction_project_id: reactionProjectId,
        ...(decEb != null ? { batch_id: decEb } : {}),
        ...(decCn != null ? { cycle_number: decCn } : {}),
        status: occDecision,
      })
      setMsg({ tone: "ok", text: "Optimization cycle decision recorded." })
      setOccRationale("")
      setOptimizationCycleDetailById((prev) => {
        const next = { ...prev }
        delete next[cycleId]
        return next
      })
      await reload()
    } catch (err) {
      setMsg({
        tone: "err",
        text: formatApiError(err, "POST /reaction-optimization-cycles/{cycle_id}/decision failed."),
      })
    } finally {
      setBusy(null)
    }
  }

  function openLinkExperimentDialog(eid: number) {
    const row = experimentsRec.find((x) => readNum(x.id) === eid)
    const linked = row ? readNum(row.linked_spectracheck_session_id) : null
    setLinkSessionInput(linked != null ? String(linked) : "")
    setLinkNoteInput("")
    setLinkDialogExperimentId(eid)
  }

  async function submitLinkSpectraCheckSession(e: React.FormEvent) {
    e.preventDefault()
    if (linkDialogExperimentId == null) return
    setMsg(null)
    const raw = linkSessionInput.trim()
    const sid = Number.parseInt(raw, 10)
    if (!Number.isFinite(sid) || sid < 1) {
      setMsg({ tone: "err", text: "session_id must be a positive integer." })
      return
    }
    const eid = linkDialogExperimentId
    setBusy(`link-${eid}`)
    try {
      const metadata_json: Record<string, unknown> = {}
      const note = linkNoteInput.trim()
      if (note) metadata_json.note = note
      await apiFetch(`/reaction-experiments/${eid}/link-spectracheck-session`, {
        method: "POST",
        body: { session_id: sid, metadata_json },
      })
      trackSpectracheckLinkedToReaction({
        reaction_project_id: reactionProjectId,
        experiment_count: experimentCount,
        objective,
        status,
        has_spectracheck_link: true,
      })
      setMsg({ tone: "ok", text: "SpectraCheck session linked to reaction experiment." })
      setLinkDialogExperimentId(null)
      await reload()
    } catch (err) {
      setMsg({ tone: "err", text: formatApiError(err, "Link SpectraCheck session failed.") })
    } finally {
      setBusy(null)
    }
  }

  if (!Number.isFinite(reactionProjectId) || reactionProjectId < 1) {
    return (
      <Alert variant="destructive">
        <AlertTitle className="text-sm">Invalid route</AlertTitle>
        <AlertDescription className="text-xs">Missing or invalid reaction_project_id.</AlertDescription>
      </Alert>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" asChild>
              <Link href="/reactions">
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back
              </Link>
            </Button>
            <Badge variant="outline" className="font-mono text-xs">
              reaction_project_id={reactionProjectId}
            </Badge>
          </div>
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-violet)" }}
          >
            MolTrace · Reaction Studio (project-level)
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Reaction Studio (project-level)</h1>
          <p className="text-sm text-muted-foreground">{loading ? "Loading…" : projectName}</p>
        </div>
        <div className="flex items-center gap-2">
          <FlaskConical className="h-5 w-5" style={{ color: "var(--mt-violet)" }} aria-hidden />
        </div>
      </div>

      {error ? (
        <AlertCard variant="error" title="Backend unavailable" description={error} />
      ) : null}

      {msg ? (
        <AlertCard
          variant={msg.tone === "ok" ? "success" : "error"}
          title={msg.tone === "ok" ? "Update" : "Error"}
          description={msg.text}
        />
      ) : null}

      <ReactionStudioKnowledgeLinksCard reactionProjectId={reactionProjectId} />

      <Tabs defaultValue="overview" className="w-full min-w-0">
        <div className="min-w-0 overflow-x-auto pb-2 [-webkit-overflow-scrolling:touch]">
          <TabsList className="inline-flex h-auto min-h-9 w-max max-w-full flex-nowrap justify-start gap-1">
            <TabsTrigger value="overview" className={reactionProjectTabClass}>
              Overview
            </TabsTrigger>
            <TabsTrigger value="variables" className={reactionProjectTabClass}>
              Variables
            </TabsTrigger>
            <TabsTrigger value="experiments" className={reactionProjectTabClass}>
              Experiments
            </TabsTrigger>
            <TabsTrigger value="objective" className={reactionProjectTabClass}>
              Objective
            </TabsTrigger>
            <TabsTrigger value="cost-safety" className={reactionProjectTabClass}>
              {"Cost & Safety"}
            </TabsTrigger>
            <TabsTrigger value="optimization" className={reactionProjectTabClass}>
              Optimization
            </TabsTrigger>
            <TabsTrigger value="advisor" className={reactionProjectTabClass}>
              <span className="inline-flex items-center gap-1">
                Advisor
                <span
                  className="inline-flex shrink-0"
                  onClick={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                  }}
                  onPointerDown={(e) => e.stopPropagation()}
                >
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span
                        className="inline-flex size-5 shrink-0 cursor-default items-center justify-center rounded-full text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        aria-label="About Advisor"
                        tabIndex={0}
                      >
                        <Info className="size-3.5" aria-hidden strokeWidth={2} />
                      </span>
                    </TooltipTrigger>
                    <TooltipContent sideOffset={4} className="max-w-xs text-xs">
                      {ADVISOR_TAB_TOOLTIP}
                    </TooltipContent>
                  </Tooltip>
                </span>
              </span>
            </TabsTrigger>
            <TabsTrigger value="recommendations" className={reactionProjectTabClass}>
              Recommendations
            </TabsTrigger>
            <TabsTrigger value="execution" className={reactionProjectTabClass}>
              <span className="inline-flex items-center gap-1">
                Execution
                <span
                  className="inline-flex shrink-0"
                  onClick={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                  }}
                  onPointerDown={(e) => e.stopPropagation()}
                >
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span
                        className="inline-flex size-5 shrink-0 cursor-default items-center justify-center rounded-full text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        aria-label="About Execution"
                        tabIndex={0}
                      >
                        <Info className="size-3.5" aria-hidden strokeWidth={2} />
                      </span>
                    </TooltipTrigger>
                    <TooltipContent sideOffset={4} className="max-w-xs text-xs">
                      {EXECUTION_TAB_TOOLTIP}
                    </TooltipContent>
                  </Tooltip>
                </span>
              </span>
            </TabsTrigger>
            <TabsTrigger value="evidence" className={reactionProjectTabClass}>
              Evidence Links
            </TabsTrigger>
            <TabsTrigger value="developer" className={reactionProjectTabClass}>
              Developer JSON
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="overview" className="mt-4 space-y-6">
          <div className="space-y-1">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-violet)" }}
            >
              Project · Overview
            </p>
            <h2 className="font-mono text-xl font-bold tracking-tight">Reaction project at a glance</h2>
            <p className="text-sm text-muted-foreground">
              Project metadata, campaign aggregates, and recent activity — the source of truth for the rest of the workspace.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Card
              className="overflow-hidden rounded-xl py-0"
              style={{ borderTop: "3px solid var(--mt-violet)" }}
            >
              <CardHeader className="pt-4 pb-2">
                <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                  Objective
                </CardTitle>
              </CardHeader>
              <CardContent className="pb-4">
                <p
                  className="font-mono text-base font-bold"
                  style={{ color: "var(--mt-violet)" }}
                >
                  {objective ?? "—"}
                </p>
              </CardContent>
            </Card>
            <Card
              className="overflow-hidden rounded-xl py-0"
              style={{ borderTop: "3px solid var(--mt-violet)" }}
            >
              <CardHeader className="pt-4 pb-2">
                <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                  Status
                </CardTitle>
              </CardHeader>
              <CardContent className="pb-4">
                <Badge variant="outline">{status ?? "—"}</Badge>
              </CardContent>
            </Card>
            <Card
              className="overflow-hidden rounded-xl py-0"
              style={{ borderTop: "3px solid var(--mt-violet)" }}
            >
              <CardHeader className="pt-4 pb-2">
                <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                  Experiment count
                </CardTitle>
              </CardHeader>
              <CardContent className="pb-4">
                <p
                  className="font-mono text-3xl font-bold tabular-nums leading-none"
                  style={{ color: "var(--mt-violet)" }}
                >
                  {loading ? "…" : experimentCount}
                </p>
                <p className="mt-2 text-xs text-muted-foreground">From GET …/experiments</p>
              </CardContent>
            </Card>
          </div>
          <ReactionResponseOverview
            loading={loading}
            experiments={experimentsRec}
            variableRecords={variableRecords}
            variableNamesOrdered={variableNamesOrdered}
          />
          <ModuleCard
            accent="violet"
            eyebrow="Overview · Best Outcome"
            title="best observed outcome"
            description="Aggregate view only — not a guarantee of future performance."
          >
            <p className="text-sm text-muted-foreground">
              {loading ? "…" : bestOutcomeLabel(objective, experimentsRec)}
            </p>
          </ModuleCard>
          <ModuleCard
            accent="violet"
            eyebrow="Overview · Latest Recommendation"
            title="latest recommendation"
          >
            <div className="space-y-2 text-sm">
              {loading ? (
                <p className="text-muted-foreground">…</p>
              ) : latestRec ? (
                <>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="secondary" className="font-mono text-xs">
                      rank {String(latestRec.rank ?? "—")}
                    </Badge>
                    <Badge variant="outline">{String(latestRec.label ?? "")}</Badge>
                    <Badge variant="outline">{String(latestRec.status ?? "")}</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">{fmtIso(latestRec.updated_at)}</p>
                  <p className="line-clamp-4 text-muted-foreground">{String(latestRec.rationale ?? "")}</p>
                </>
              ) : (
                <p className="text-muted-foreground">No recommendations returned.</p>
              )}
            </div>
          </ModuleCard>
          <ModuleCard
            accent="violet"
            eyebrow="Overview · Linked Evidence"
            title="linked SpectraCheck evidence"
            description="Experiments with linked_spectracheck_session_id and evidence record counts."
          >
            <div className="text-sm">
              <p>
                <span className="text-muted-foreground">Linked sessions (experiments): </span>
                <span className="font-semibold tabular-nums">{loading ? "…" : linkedSessionCount}</span>
              </p>
              <p className="mt-2 text-xs text-muted-foreground">
                Evidence records from linked SpectraCheck sessions are counted per experiment and shown in the Evidence Links tab.
              </p>
            </div>
          </ModuleCard>
          <ReactionStudioCompoundLinkSummary loading={loading} project={project} experiments={experimentsRec} />
        </TabsContent>

        <TabsContent value="variables" className="mt-4 space-y-6">
          <div className="space-y-1">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-violet)" }}
            >
              Project · Variables
            </p>
            <h2 className="font-mono text-xl font-bold tracking-tight">Optimization variable definitions</h2>
            <p className="text-sm text-muted-foreground">
              Continuous and categorical variables, their bounds, units, and encoding. Drives the design space and recommendation generation.
            </p>
          </div>
          <ModuleCard
            accent="violet"
            eyebrow="Reaction · Variables"
            title={
              <span className="inline-flex items-center gap-2">
                Variables
                <InfoTooltip content={VARIABLES_TOOLTIP} label="About reaction variables" />
              </span>
            }
            description="Reaction variables defining the experimental parameter space — temperature, solvent, catalyst loading, and other independently controlled inputs."
          >
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>name</TableHead>
                    <TableHead>type</TableHead>
                    <TableHead>unit</TableHead>
                    <TableHead className="min-w-[140px]">allowed values</TableHead>
                    <TableHead className="text-right">min</TableHead>
                    <TableHead className="text-right">max</TableHead>
                    <TableHead className="min-w-[100px]">default</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loading ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-muted-foreground">
                        Loading…
                      </TableCell>
                    </TableRow>
                  ) : variables.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-muted-foreground">
                        No variables.
                      </TableCell>
                    </TableRow>
                  ) : (
                    variables.filter(isRecord).map((v) => (
                      <TableRow key={String(v.id)}>
                        <TableCell className="font-medium">{String(v.name ?? "")}</TableCell>
                        <TableCell className="font-mono text-xs">{String(v.variable_type ?? "")}</TableCell>
                        <TableCell>{String(v.unit ?? "—")}</TableCell>
                        <TableCell className="max-w-[200px] truncate text-xs text-muted-foreground">
                          {formatAllowedValuesDisplay(v.allowed_values_json)}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs tabular-nums">
                          {v.min_value != null ? String(v.min_value) : "—"}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs tabular-nums">
                          {v.max_value != null ? String(v.max_value) : "—"}
                        </TableCell>
                        <TableCell className="font-mono text-xs">{formatDefaultDisplay(v.default_value)}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Reaction · Add Variable"
            title="add variable"
            description="Define a new reaction variable with its type, unit, and allowed-value constraints for use across all experiments in this project."
          >
              <form className="grid gap-4 md:grid-cols-2" onSubmit={(e) => void submitVariable(e)}>
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="rv-name">variable name</Label>
                  <Input id="rv-name" value={vName} onChange={(e) => setVName(e.target.value)} maxLength={160} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="rv-type">variable type</Label>
                  <Select value={vType} onValueChange={setVType}>
                    <SelectTrigger id="rv-type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="categorical">categorical</SelectItem>
                      <SelectItem value="numeric">numeric</SelectItem>
                      <SelectItem value="boolean">boolean</SelectItem>
                      <SelectItem value="text">text</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="rv-unit">
                    unit <span className="font-normal text-muted-foreground">(optional)</span>
                  </Label>
                  <Input id="rv-unit" value={vUnit} onChange={(e) => setVUnit(e.target.value)} maxLength={80} />
                </div>
                {vType === "categorical" ? (
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="rv-allowed">allowed values</Label>
                    <p className="text-xs text-muted-foreground">Comma-separated (categorical).</p>
                    <Input
                      id="rv-allowed"
                      value={vAllowedCsv}
                      onChange={(e) => setVAllowedCsv(e.target.value)}
                      placeholder="e.g. THF, DMF, Dioxane"
                      autoComplete="off"
                    />
                  </div>
                ) : null}
                {vType === "numeric" ? (
                  <>
                    <div className="space-y-2">
                      <Label htmlFor="rv-min">min value</Label>
                      <Input id="rv-min" value={vMin} onChange={(e) => setVMin(e.target.value)} inputMode="decimal" />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="rv-max">max value</Label>
                      <Input id="rv-max" value={vMax} onChange={(e) => setVMax(e.target.value)} inputMode="decimal" />
                    </div>
                  </>
                ) : null}
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="rv-def">
                    default value <span className="font-normal text-muted-foreground">(optional)</span>
                  </Label>
                  <Input id="rv-def" value={vDefault} onChange={(e) => setVDefault(e.target.value)} />
                </div>
                <div className="md:col-span-2">
                  <Button type="submit" disabled={busy === "variable"}>
                    {busy === "variable" ? "Saving…" : "Add variable"}
                  </Button>
                </div>
              </form>
          </ModuleCard>
        </TabsContent>

        <TabsContent value="experiments" className="mt-4 space-y-6">
          <div className="space-y-1">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-violet)" }}
            >
              Project · Experiments
            </p>
            <h2 className="font-mono text-xl font-bold tracking-tight">Experiment matrix &amp; outcomes</h2>
            <p className="text-sm text-muted-foreground">
              All experiments in this project — variable values, outcomes, and SpectraCheck-linked analytical results.
            </p>
          </div>
          <ModuleCard
            accent="violet"
            eyebrow="Reaction · Experiment Matrix"
            title="experiment matrix"
            description="Reaction experiment matrix — each row records a unique condition set, outcome metrics, and the SpectraCheck session linked for analytical evidence."
          >
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>experiment_code</TableHead>
                    <TableHead>status</TableHead>
                    {conditionColumnKeys.map((k) => (
                      <TableHead key={k} className="max-w-[100px] whitespace-nowrap text-xs">
                        {k}
                      </TableHead>
                    ))}
                    <TableHead className="text-right text-xs">yield</TableHead>
                    <TableHead className="text-right text-xs">conversion</TableHead>
                    <TableHead className="text-right text-xs">selectivity</TableHead>
                    <TableHead className="text-right text-xs">impurity</TableHead>
                    <TableHead className="font-mono text-xs">linked_spectracheck_session_id</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">updated_at</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">SpectraCheck</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {experimentsRec.map((e) => {
                    const eid = readNum(e.id)
                    const cj = isRecord(e.conditions_json) ? e.conditions_json : {}
                    const yld = readOutcomeNumber(e, "yield_percent")
                    const conv = readOutcomeNumber(e, "conversion_percent")
                    const sel = readOutcomeNumber(e, "selectivity_percent")
                    const imp = readOutcomeNumber(e, "impurity_percent")
                    const linked = readNum(e.linked_spectracheck_session_id)
                    return (
                      <TableRow key={String(e.id)}>
                        <TableCell className="font-mono text-xs">{String(e.experiment_code ?? "")}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className="font-normal">
                            {String(e.status ?? "")}
                          </Badge>
                        </TableCell>
                        {conditionColumnKeys.map((k) => (
                          <TableCell key={k} className="max-w-[100px] truncate text-xs">
                            {String((cj as Record<string, unknown>)[k] ?? "—")}
                          </TableCell>
                        ))}
                        <TableCell className="text-right font-mono text-xs tabular-nums">
                          {yld != null ? `${yld}` : "—"}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs tabular-nums">
                          {conv != null ? `${conv}` : "—"}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs tabular-nums">
                          {sel != null ? `${sel}` : "—"}
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs tabular-nums">
                          {imp != null ? `${imp}` : "—"}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {linked != null ? linked : "—"}
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                          {fmtIso(e.updated_at)}
                        </TableCell>
                        <TableCell className="min-w-[140px]">
                          {eid != null ? (
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="text-xs"
                              disabled={busy != null}
                              onClick={() => openLinkExperimentDialog(eid)}
                            >
                              Link SpectraCheck Session
                            </Button>
                          ) : null}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                  {!loading && experimentsRec.length === 0 ? (
                    <TableRow>
                      <TableCell
                        colSpan={9 + conditionColumnKeys.length}
                        className="text-muted-foreground"
                      >
                        No experiments.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Reaction · Evidence Summary"
            title="SpectraCheck evidence summary"
            description="Analytical evidence summary for experiments with linked SpectraCheck sessions — confidence status, QC outcome, and evidence record count. Open SpectraCheck for full spectral evidence."
          >
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>experiment_code</TableHead>
                    <TableHead className="font-mono text-xs">linked_spectracheck_session_id</TableHead>
                    <TableHead className="text-xs">sample_id</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">unified status</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">report status</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">QC status</TableHead>
                    <TableHead className="text-right text-xs">evidence_records</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">open</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {experimentsRec
                    .filter((row) => readNum(row.linked_spectracheck_session_id) != null)
                    .map((row) => {
                      const eid = readNum(row.id)
                      const linked = readNum(row.linked_spectracheck_session_id)
                      const ev = eid != null ? experimentEvidenceById[eid] : undefined
                      const summ = ev ? reactionEvidenceSummary(ev) : null
                      return (
                        <TableRow key={String(row.id)}>
                          <TableCell className="font-mono text-xs">{String(row.experiment_code ?? "")}</TableCell>
                          <TableCell className="font-mono text-xs">{linked != null ? linked : "—"}</TableCell>
                          <TableCell className="max-w-[100px] truncate text-xs">
                            {summ?.sampleId ?? (loading ? "…" : "—")}
                          </TableCell>
                          <TableCell className="max-w-[120px] truncate text-xs">
                            {summ?.unifiedEvidenceStatus ?? "—"}
                          </TableCell>
                          <TableCell className="max-w-[120px] truncate text-xs">
                            {summ?.reportStatus ?? "—"}
                          </TableCell>
                          <TableCell className="max-w-[120px] truncate text-xs">{summ?.qcStatus ?? "—"}</TableCell>
                          <TableCell className="text-right font-mono text-xs tabular-nums">
                            {summ != null ? summ.evidenceRecordCount : loading ? "…" : "—"}
                          </TableCell>
                          <TableCell className="whitespace-nowrap">
                            {linked != null ? (
                              <Button variant="outline" size="sm" className="h-8 gap-1 px-2 text-xs" asChild>
                                <Link
                                  href={`/spectracheck?sessionId=${encodeURIComponent(String(linked))}`}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                >
                                  Open
                                  <ExternalLink className="h-3 w-3" aria-hidden />
                                </Link>
                              </Button>
                            ) : (
                              "—"
                            )}
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  {!loading &&
                  experimentsRec.filter((row) => readNum(row.linked_spectracheck_session_id) != null).length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={8} className="text-muted-foreground">
                        No linked SpectraCheck sessions — use Link SpectraCheck Session on an experiment row.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Reaction · Add Experiment"
            title="add experiment"
            description="Register a new reaction experiment with its condition set, status, and optional outcome fields."
          >
              <form className="space-y-6" onSubmit={(e) => void submitExperiment(e)}>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="ex-code">experiment_code</Label>
                    <Input id="ex-code" value={expCode} onChange={(e) => setExpCode(e.target.value)} maxLength={120} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="ex-st">status</Label>
                    <Select value={expStatus} onValueChange={setExpStatus}>
                      <SelectTrigger id="ex-st">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="planned">planned</SelectItem>
                        <SelectItem value="running">running</SelectItem>
                        <SelectItem value="completed">completed</SelectItem>
                        <SelectItem value="failed">failed</SelectItem>
                        <SelectItem value="excluded">excluded</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="space-y-3">
                  <p className="text-sm font-medium">conditions_json</p>
                  <p className="text-xs text-muted-foreground">
                    Fields follow GET …/variables. Leave blank to omit a key.
                  </p>
                  {variableRecords.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No reaction variables yet — add variables first, or POST with empty conditions_json.
                    </p>
                  ) : (
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                      {variableRecords.map((v) => {
                        const key = typeof v.name === "string" ? v.name : ""
                        if (!key) return null
                        const vt = typeof v.variable_type === "string" ? v.variable_type : "text"
                        const unit = typeof v.unit === "string" && v.unit.trim() ? v.unit : ""
                        const label = unit ? `${key} (${unit})` : key
                        const val = expConditionValues[key] ?? ""
                        const setVal = (s: string) =>
                          setExpConditionValues((prev) => ({ ...prev, [key]: s }))
                        const allowed = v.allowed_values_json
                        return (
                          <div key={key} className="space-y-2">
                            <Label htmlFor={`ex-cond-${key}`} className="font-mono text-xs">
                              {label}
                            </Label>
                            {vt === "categorical" && Array.isArray(allowed) ? (
                              <Select
                                value={val || "__none__"}
                                onValueChange={(x) => setVal(x === "__none__" ? "" : x)}
                              >
                                <SelectTrigger id={`ex-cond-${key}`}>
                                  <SelectValue placeholder="—" />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="__none__">—</SelectItem>
                                  {allowed.map((opt) => (
                                    <SelectItem key={String(opt)} value={String(opt)}>
                                      {String(opt)}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            ) : vt === "boolean" ? (
                              <Select
                                value={val || "__none__"}
                                onValueChange={(x) => setVal(x === "__none__" ? "" : x)}
                              >
                                <SelectTrigger id={`ex-cond-${key}`}>
                                  <SelectValue placeholder="—" />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="__none__">—</SelectItem>
                                  <SelectItem value="true">true</SelectItem>
                                  <SelectItem value="false">false</SelectItem>
                                </SelectContent>
                              </Select>
                            ) : vt === "numeric" ? (
                              <Input
                                id={`ex-cond-${key}`}
                                inputMode="decimal"
                                value={val}
                                onChange={(e) => setVal(e.target.value)}
                              />
                            ) : (
                              <Input
                                id={`ex-cond-${key}`}
                                value={val}
                                onChange={(e) => setVal(e.target.value)}
                              />
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>

                <div className="space-y-3">
                  <p className="text-sm font-medium">outcome_json</p>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    <div className="space-y-2">
                      <Label htmlFor="ex-yield">yield_percent</Label>
                      <Input
                        id="ex-yield"
                        inputMode="decimal"
                        value={expYield}
                        onChange={(e) => setExpYield(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="ex-conv">conversion_percent</Label>
                      <Input
                        id="ex-conv"
                        inputMode="decimal"
                        value={expConversion}
                        onChange={(e) => setExpConversion(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="ex-sel">selectivity_percent</Label>
                      <Input
                        id="ex-sel"
                        inputMode="decimal"
                        value={expSelectivity}
                        onChange={(e) => setExpSelectivity(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="ex-imp">impurity_percent</Label>
                      <Input
                        id="ex-imp"
                        inputMode="decimal"
                        value={expImpurity}
                        onChange={(e) => setExpImpurity(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="ex-iso">isolated_yield_percent</Label>
                      <Input
                        id="ex-iso"
                        inputMode="decimal"
                        value={expIsolatedYield}
                        onChange={(e) => setExpIsolatedYield(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="ex-lcms">lcms_area_percent</Label>
                      <Input
                        id="ex-lcms"
                        inputMode="decimal"
                        value={expLcmsArea}
                        onChange={(e) => setExpLcmsArea(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="ex-nmr">nmr_purity_percent</Label>
                      <Input
                        id="ex-nmr"
                        inputMode="decimal"
                        value={expNmrPurity}
                        onChange={(e) => setExpNmrPurity(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2 sm:col-span-2 lg:col-span-3">
                      <Label htmlFor="ex-notes">notes</Label>
                      <Textarea
                        id="ex-notes"
                        rows={3}
                        value={expNotes}
                        onChange={(e) => setExpNotes(e.target.value)}
                      />
                    </div>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="ex-sc">linked_spectracheck_session_id</Label>
                  <p className="text-xs text-muted-foreground">optional</p>
                  <Input
                    id="ex-sc"
                    value={expSessionId}
                    onChange={(e) => setExpSessionId(e.target.value)}
                    inputMode="numeric"
                  />
                </div>

                <Button type="submit" disabled={busy === "experiment"}>
                  {busy === "experiment" ? "Saving…" : "Add experiment"}
                </Button>
              </form>
          </ModuleCard>
        </TabsContent>

        <TabsContent value="objective" className="mt-4 space-y-6">
          <div className="space-y-1">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-violet)" }}
            >
              Project · Objective
            </p>
            <h2 className="font-mono text-xl font-bold tracking-tight">Optimization objective &amp; weights</h2>
            <p className="text-sm text-muted-foreground">
              Single- or multi-objective definition with per-target weights and direction (maximize / minimize).
            </p>
          </div>
          <ModuleCard
            accent="violet"
            eyebrow="Reaction · Objective"
            title={
              <span className="inline-flex items-center gap-2">
                Objective profile
                <InfoTooltip content={OBJECTIVE_PROFILE_TOOLTIP} label="About objective profile" />
              </span>
            }
            description="Define the optimization objective — yield, selectivity, purity, or a composite target — including weighting and thresholds used by the optimization engine."
          >
              <form className="space-y-6" onSubmit={(e) => void saveObjectiveProfile(e)}>
                <div className="space-y-2">
                  <Label htmlFor="obj-type">objective type</Label>
                  <Select value={objectiveType} onValueChange={setObjectiveType}>
                    <SelectTrigger id="obj-type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {OBJECTIVE_TYPE_OPTIONS.map((opt) => (
                        <SelectItem key={opt} value={opt}>
                          {opt}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-3">
                  <p className="text-sm font-medium">weights_json</p>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    <div className="space-y-2">
                      <Label htmlFor="w-yield">yield</Label>
                      <Input
                        id="w-yield"
                        inputMode="decimal"
                        value={weightYield}
                        onChange={(e) => setWeightYield(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="w-sel">selectivity</Label>
                      <Input
                        id="w-sel"
                        inputMode="decimal"
                        value={weightSelectivity}
                        onChange={(e) => setWeightSelectivity(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="w-imp">impurity penalty</Label>
                      <Input
                        id="w-imp"
                        inputMode="decimal"
                        value={weightImpurityPenalty}
                        onChange={(e) => setWeightImpurityPenalty(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="w-conv">conversion</Label>
                      <Input
                        id="w-conv"
                        inputMode="decimal"
                        value={weightConversion}
                        onChange={(e) => setWeightConversion(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="w-cost">cost penalty</Label>
                      <Input
                        id="w-cost"
                        inputMode="decimal"
                        value={weightCostPenalty}
                        onChange={(e) => setWeightCostPenalty(e.target.value)}
                      />
                    </div>
                  </div>
                </div>

                <div className="space-y-3">
                  <p className="text-sm font-medium">target thresholds</p>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    <div className="space-y-2">
                      <Label htmlFor="min-yield">minimum yield</Label>
                      <Input
                        id="min-yield"
                        inputMode="decimal"
                        value={minimumYield}
                        onChange={(e) => setMinimumYield(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="min-sel">minimum selectivity</Label>
                      <Input
                        id="min-sel"
                        inputMode="decimal"
                        value={minimumSelectivity}
                        onChange={(e) => setMinimumSelectivity(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="max-imp">maximum impurity</Label>
                      <Input
                        id="max-imp"
                        inputMode="decimal"
                        value={maximumImpurity}
                        onChange={(e) => setMaximumImpurity(e.target.value)}
                      />
                    </div>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="hard-constraints">hard constraints</Label>
                  <p className="text-xs text-muted-foreground">JSON or text (advanced).</p>
                  <Textarea
                    id="hard-constraints"
                    rows={5}
                    value={hardConstraintsText}
                    onChange={(e) => setHardConstraintsText(e.target.value)}
                    className="font-mono text-xs"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="soft-constraints">soft constraints</Label>
                  <p className="text-xs text-muted-foreground">JSON or text (advanced).</p>
                  <Textarea
                    id="soft-constraints"
                    rows={5}
                    value={softConstraintsText}
                    onChange={(e) => setSoftConstraintsText(e.target.value)}
                    className="font-mono text-xs"
                  />
                </div>

                <Button type="submit" disabled={busy === "objective-profile" || loading}>
                  {busy === "objective-profile" ? "Saving…" : "Save objective profile"}
                </Button>
              </form>
          </ModuleCard>
          <ReactionRegulatoryConstraintsPanel
            reactionProjectId={reactionProjectId}
            onPayloadChange={setRegulatoryPayloadForOptimization}
            onUseInOptimizationChange={setUseRegulatoryAnchorInOptimization}
          />
        </TabsContent>

        <TabsContent value="cost-safety" className="mt-4 space-y-6">
          <div className="space-y-1">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-violet)" }}
            >
              Project · Cost &amp; Safety
            </p>
            <h2 className="font-mono text-xl font-bold tracking-tight">Cost profile &amp; safety constraints</h2>
            <p className="text-sm text-muted-foreground">
              Per-reagent costs and safety guard-rails — fed into the recommendation generator and Reaction Advisor.
            </p>
          </div>
          <ModuleCard
            accent="violet"
            eyebrow="Reaction · Cost"
            title={
              <span className="inline-flex items-center gap-2">
                Cost profile
                <InfoTooltip content={COST_AWARE_TOOLTIP} label="Cost-aware optimization" />
              </span>
            }
            description="Reagent, solvent, and process cost parameters applied during optimization to penalize expensive condition combinations."
          >
              <form className="space-y-6" onSubmit={(e) => void saveCostProfile(e)}>
                <div className="space-y-2">
                  <Label htmlFor="cp-reagent-costs">reagent_costs_json</Label>
                  <p className="text-xs text-muted-foreground">JSON or table (advanced).</p>
                  <Textarea
                    id="cp-reagent-costs"
                    rows={4}
                    value={reagentCostsText}
                    onChange={(e) => setReagentCostsText(e.target.value)}
                    className="font-mono text-xs"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cp-solvent-costs">solvent_costs_json</Label>
                  <p className="text-xs text-muted-foreground">JSON or table (advanced).</p>
                  <Textarea
                    id="cp-solvent-costs"
                    rows={4}
                    value={solventCostsText}
                    onChange={(e) => setSolventCostsText(e.target.value)}
                    className="font-mono text-xs"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cp-catalyst-costs">catalyst_costs_json</Label>
                  <p className="text-xs text-muted-foreground">JSON or table (advanced).</p>
                  <Textarea
                    id="cp-catalyst-costs"
                    rows={4}
                    value={catalystCostsText}
                    onChange={(e) => setCatalystCostsText(e.target.value)}
                    className="font-mono text-xs"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cp-ligand-costs">ligand_costs_json</Label>
                  <p className="text-xs text-muted-foreground">JSON or table (advanced).</p>
                  <Textarea
                    id="cp-ligand-costs"
                    rows={4}
                    value={ligandCostsText}
                    onChange={(e) => setLigandCostsText(e.target.value)}
                    className="font-mono text-xs"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cp-availability">availability_notes</Label>
                  <Textarea
                    id="cp-availability"
                    rows={3}
                    value={availabilityNotes}
                    onChange={(e) => setAvailabilityNotes(e.target.value)}
                  />
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="cp-max-cost">max_cost_per_experiment</Label>
                    <Input
                      id="cp-max-cost"
                      inputMode="decimal"
                      value={maxCostPerExperiment}
                      onChange={(e) => setMaxCostPerExperiment(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="cp-penalty-weight">cost_penalty_weight</Label>
                    <Input
                      id="cp-penalty-weight"
                      inputMode="decimal"
                      value={costProfilePenaltyWeight}
                      onChange={(e) => setCostProfilePenaltyWeight(e.target.value)}
                    />
                  </div>
                </div>
                <Button type="submit" disabled={busy === "cost-profile" || loading}>
                  {busy === "cost-profile" ? "Saving…" : "Save cost profile"}
                </Button>
              </form>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Reaction · Safety"
            title={
              <span className="inline-flex items-center gap-2">
                Safety profile
                <InfoTooltip content={SAFETY_CONSTRAINTS_TOOLTIP} label="Safety constraints" />
              </span>
            }
            description="Blocked reagents, hazard flags, and safety-constraint parameters applied to filter candidate conditions before scoring."
          >
              <form className="space-y-6" onSubmit={(e) => void saveSafetyProfile(e)}>
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Label htmlFor="sp-blocked-reagents">blocked_reagents</Label>
                    {blockedReagentsText.trim() ? (
                      <Badge variant="destructive" className="text-[10px] font-normal">
                        blocked list active
                      </Badge>
                    ) : null}
                  </div>
                  <p className="text-xs text-muted-foreground">JSON or list (advanced).</p>
                  <Textarea
                    id="sp-blocked-reagents"
                    rows={4}
                    value={blockedReagentsText}
                    onChange={(e) => setBlockedReagentsText(e.target.value)}
                    className="border-destructive/25 font-mono text-xs"
                  />
                </div>
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Label htmlFor="sp-blocked-solvents">blocked_solvents</Label>
                    {blockedSolventsText.trim() ? (
                      <Badge variant="destructive" className="text-[10px] font-normal">
                        blocked list active
                      </Badge>
                    ) : null}
                  </div>
                  <p className="text-xs text-muted-foreground">JSON or list (advanced).</p>
                  <Textarea
                    id="sp-blocked-solvents"
                    rows={4}
                    value={blockedSolventsText}
                    onChange={(e) => setBlockedSolventsText(e.target.value)}
                    className="border-destructive/25 font-mono text-xs"
                  />
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="sp-max-temp">max_temperature_c</Label>
                    <p className="text-xs text-muted-foreground">Maximum temperature (°C).</p>
                    <Input
                      id="sp-max-temp"
                      inputMode="decimal"
                      value={maxTemperatureC}
                      onChange={(e) => setMaxTemperatureC(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="sp-max-pressure">max_pressure_bar</Label>
                    <p className="text-xs text-muted-foreground">Maximum pressure (bar).</p>
                    <Input
                      id="sp-max-pressure"
                      inputMode="decimal"
                      value={maxPressureBar}
                      onChange={(e) => setMaxPressureBar(e.target.value)}
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="sp-incompatible">incompatible_pairs</Label>
                  <p className="text-xs text-muted-foreground">JSON (advanced).</p>
                  <Textarea
                    id="sp-incompatible"
                    rows={4}
                    value={incompatiblePairsText}
                    onChange={(e) => setIncompatiblePairsText(e.target.value)}
                    className="font-mono text-xs"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="sp-controls">required_controls</Label>
                  <p className="text-xs text-muted-foreground">JSON (advanced).</p>
                  <Textarea
                    id="sp-controls"
                    rows={4}
                    value={requiredControlsText}
                    onChange={(e) => setRequiredControlsText(e.target.value)}
                    className="font-mono text-xs"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="sp-notes">safety_notes</Label>
                  <Textarea
                    id="sp-notes"
                    rows={4}
                    value={safetyNotes}
                    onChange={(e) => setSafetyNotes(e.target.value)}
                  />
                </div>
                <Button type="submit" disabled={busy === "safety-profile" || loading}>
                  {busy === "safety-profile" ? "Saving…" : "Save safety profile"}
                </Button>
              </form>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Reaction · Design Space"
            title={
              <span className="inline-flex items-center gap-2">
                Design space
                <InfoTooltip content={DESIGN_SPACE_TOOLTIP} label="About design space" />
              </span>
            }
            description="Experimental design space — variable bounds, fixed values, and categorical levels that constrain the optimization search region."
          >
            <div className="space-y-6">
              <div className="table-scroll">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>variable name</TableHead>
                      <TableHead>type</TableHead>
                      <TableHead className="min-w-[140px]">allowed values</TableHead>
                      <TableHead className="text-right">min</TableHead>
                      <TableHead className="text-right">max</TableHead>
                      <TableHead className="whitespace-nowrap">fixed / excluded</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {loading ? (
                      <TableRow>
                        <TableCell colSpan={6} className="text-muted-foreground">
                          Loading…
                        </TableCell>
                      </TableRow>
                    ) : variableRecords.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="text-muted-foreground">
                          No reaction variables yet — add variables on the Variables tab.
                        </TableCell>
                      </TableRow>
                    ) : (
                      variableRecords.map((v) => {
                        const vid = readNum(v.id)
                        const name = typeof v.name === "string" ? v.name : ""
                        const vt = typeof v.variable_type === "string" ? v.variable_type : ""
                        const state = vid != null ? explorationByVariableId[vid] ?? "free" : "free"
                        const rowHighlight =
                          state === "excluded"
                            ? "border-l-4 border-l-destructive bg-destructive/5"
                            : state === "fixed"
                              ? "border-l-4 border-l-amber-500/70 bg-amber-500/5"
                              : ""
                        return (
                          <TableRow key={String(v.id ?? name)} className={rowHighlight}>
                            <TableCell className="font-medium">{name}</TableCell>
                            <TableCell className="font-mono text-xs">{vt}</TableCell>
                            <TableCell className="max-w-[200px] truncate text-xs text-muted-foreground">
                              {formatAllowedValuesDisplay(v.allowed_values_json)}
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs tabular-nums">
                              {v.min_value != null ? String(v.min_value) : "—"}
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs tabular-nums">
                              {v.max_value != null ? String(v.max_value) : "—"}
                            </TableCell>
                            <TableCell className="min-w-[140px]">
                              {vid != null ? (
                                <div className="flex flex-wrap items-center gap-2">
                                  <Select
                                    value={state}
                                    onValueChange={(val) => {
                                      const next = val as ExplorationState
                                      setExplorationByVariableId((prev) => ({ ...prev, [vid]: next }))
                                    }}
                                  >
                                    <SelectTrigger
                                      className={
                                        state === "excluded"
                                          ? "h-9 border-destructive/60"
                                          : state === "fixed"
                                            ? "h-9 border-amber-500/60"
                                            : "h-9"
                                      }
                                    >
                                      <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                      <SelectItem value="free">free</SelectItem>
                                      <SelectItem value="fixed">fixed</SelectItem>
                                      <SelectItem value="excluded">excluded</SelectItem>
                                    </SelectContent>
                                  </Select>
                                  {state === "excluded" ? (
                                    <Badge variant="destructive" className="text-[10px] font-normal">
                                      excluded
                                    </Badge>
                                  ) : state === "fixed" ? (
                                    <Badge variant="outline" className="border-amber-500/60 text-[10px] font-normal">
                                      fixed
                                    </Badge>
                                  ) : null}
                                </div>
                              ) : (
                                "—"
                              )}
                            </TableCell>
                          </TableRow>
                        )
                      })
                    )}
                  </TableBody>
                </Table>
              </div>
              <form onSubmit={(e) => void saveDesignSpace(e)}>
                <Button type="submit" disabled={busy === "design-space" || loading || variableRecords.length === 0}>
                  {busy === "design-space" ? "Saving…" : "Save design space"}
                </Button>
              </form>
            </div>
          </ModuleCard>
        </TabsContent>

        <TabsContent value="optimization" className="mt-4 space-y-6">
          <div className="space-y-1">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-violet)" }}
            >
              Project · Optimization
            </p>
            <h2 className="font-mono text-xl font-bold tracking-tight">Bayesian optimization &amp; benchmark runs</h2>
            <p className="text-sm text-muted-foreground">
              Launch optimization cycles with regulatory constraints, compare BO vs LLM advisors, and inspect benchmark history.
            </p>
          </div>
          <ReactionRegulatoryConstraintsPanel
            reactionProjectId={reactionProjectId}
            onPayloadChange={setRegulatoryPayloadForOptimization}
            onUseInOptimizationChange={setUseRegulatoryAnchorInOptimization}
          />
          <ModelDiagnosticsCard
            loading={loading}
            trainingExperimentCount={modelDiagnosticsDerived.trainingExperimentCount}
            trainingCountFallbackTotal={experimentCount}
            modelType={modelDiagnosticsDerived.modelType}
            objectiveSummary={modelDiagnosticsDerived.objectiveSummary}
            validationMetricsJson={modelDiagnosticsDerived.validationMetricsJson}
            warnings={modelDiagnosticsDerived.warnings}
            uncertaintySummary={modelDiagnosticsDerived.uncertaintySummary}
            featureEncodingSummary={modelDiagnosticsDerived.featureEncodingSummary}
          />
          <ReactionResponsePreview
            loading={loading}
            experiments={experimentsRec}
            variableRecords={variableRecords}
            variableNamesOrdered={variableNamesOrdered}
          />
          <ModuleCard
            accent="violet"
            eyebrow="Optimization · Run"
            title="run optimization"
            description="Generate rule-based next-experiment suggestions from heuristic optimization. Each recommended condition set requires human review before scheduling."
          >
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2 text-sm">
                <Badge variant="outline" className="font-mono text-xs">
                  model_type: rule_based
                </Badge>
                {status ? (
                  <Badge variant="outline" className="text-xs">
                    project status: {status}
                  </Badge>
                ) : null}
                <Badge variant="outline" className="tabular-nums text-xs">
                  experiment count: {experimentCount}
                </Badge>
                {objective ? (
                  <Badge variant="outline" className="font-mono text-xs">
                    objective: {objective}
                  </Badge>
                ) : null}
              </div>
              <p className="text-xs text-muted-foreground">
                The run request uses the project&apos;s objective and the experiments above as input; output remains
                advisory.
              </p>
              <Button
                type="button"
                onClick={() => void runOptimization()}
                disabled={
                  busy === "optimization" ||
                  busy === "bo-optimization" ||
                  busy === "benchmark" ||
                  busy === "advisor-run" ||
                  loading
                }
              >
                {busy === "optimization" ? "Running…" : "Run optimization"}
              </Button>
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Optimization · Bayesian Run"
            title="Bayesian Optimization Run"
            description="Generate model-based next-experiment suggestions via Bayesian optimization. Predicted scores are probabilistic — each recommendation requires human review before scheduling."
          >
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="bo-alg">algorithm</Label>
                <Select value={boAlgorithm} onValueChange={setBoAlgorithm}>
                  <SelectTrigger id="bo-alg">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {BO_ALGORITHM_OPTIONS.map((opt) => (
                      <SelectItem key={opt} value={opt}>
                        {opt}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="bo-batch">batch_size</Label>
                  <Input
                    id="bo-batch"
                    inputMode="numeric"
                    min={1}
                    value={boBatchSize}
                    onChange={(e) => setBoBatchSize(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="bo-explore">exploration_weight</Label>
                  <Input
                    id="bo-explore"
                    inputMode="decimal"
                    value={boExplorationWeight}
                    onChange={(e) => setBoExplorationWeight(e.target.value)}
                  />
                </div>
              </div>
              <div className="space-y-3 rounded-lg border border-border p-3">
                <div className="flex items-center justify-between gap-4">
                  <Label htmlFor="bo-cost-aware" className="font-mono text-xs">
                    cost_aware
                  </Label>
                  <Switch
                    id="bo-cost-aware"
                    checked={boCostAware}
                    onCheckedChange={(c) => setBoCostAware(Boolean(c))}
                  />
                </div>
                <div className="flex items-center justify-between gap-4">
                  <Label htmlFor="bo-safety-aware" className="font-mono text-xs">
                    safety_aware
                  </Label>
                  <Switch
                    id="bo-safety-aware"
                    checked={boSafetyAware}
                    onCheckedChange={(c) => setBoSafetyAware(Boolean(c))}
                  />
                </div>
                <div className="flex items-center justify-between gap-4">
                  <Label htmlFor="bo-failed-neg" className="text-xs leading-snug">
                    include_failed_experiments_as_negative
                  </Label>
                  <Switch
                    id="bo-failed-neg"
                    checked={boIncludeFailedAsNegative}
                    onCheckedChange={(c) => setBoIncludeFailedAsNegative(Boolean(c))}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="bo-notes">notes</Label>
                <p className="text-xs text-muted-foreground">optional</p>
                <Textarea id="bo-notes" rows={3} value={boNotes} onChange={(e) => setBoNotes(e.target.value)} />
              </div>
              <Button
                type="button"
                onClick={() => void runBayesianOptimization()}
                disabled={
                  busy === "bo-optimization" ||
                  busy === "optimization" ||
                  busy === "benchmark" ||
                  busy === "advisor-run" ||
                  loading
                }
              >
                {busy === "bo-optimization" ? "Running…" : "Run optimization"}
              </Button>
            </div>
          </ModuleCard>

          {lastBoRun != null ? (
            <ModuleCard
              accent="violet"
              eyebrow="Optimization · Latest BO Run"
              title="latest Bayesian optimization run"
              description="Bayesian optimization run summary — algorithm, model, input experiment count, status, diagnostics, and warnings from the most recent run."
            >
              <div className="space-y-4">
                {isRecord(lastBoRun) ? (
                  <>
                    {String(lastBoRun.status ?? "").toLowerCase() === "insufficient_data" ? (
                      <Alert>
                        <AlertTitle className="text-sm">insufficient_data</AlertTitle>
                        <AlertDescription className="text-xs">
                          More completed experiments are needed for reliable model-based optimization. Exploratory
                          recommendations are shown.
                        </AlertDescription>
                      </Alert>
                    ) : null}
                    <div className="flex flex-wrap gap-2 text-sm">
                      <Badge variant="outline" className="font-mono text-xs">
                        BO run ID: {readBoRunId(lastBoRun)}
                      </Badge>
                      <Badge variant="outline" className="font-mono text-xs">
                        algorithm: {String(lastBoRun.algorithm ?? "—")}
                      </Badge>
                      <Badge variant="outline" className="font-mono text-xs">
                        model_type: {String(lastBoRun.model_type ?? "—")}
                      </Badge>
                      <Badge variant="outline" className="tabular-nums text-xs">
                        input_experiment_count: {String(lastBoRun.input_experiment_count ?? "—")}
                      </Badge>
                      <Badge variant="outline">status: {String(lastBoRun.status ?? "—")}</Badge>
                    </div>
                    <MlModelProvenanceSummary sources={[lastBoRun]} className="rounded-md border border-dashed px-3 py-2" />
                    {(() => {
                      const ws = mergeRunStringLists(lastBoRun.warnings, lastBoRun.warnings_json)
                      return (
                        <div className="space-y-2">
                          <p className="text-sm font-medium">warnings</p>
                          {ws.length > 0 ? (
                            <ul className="list-inside list-disc text-sm text-muted-foreground">
                              {ws.map((w) => (
                                <li key={w}>{w}</li>
                              ))}
                            </ul>
                          ) : (
                            <p className="text-sm text-muted-foreground">warnings: none</p>
                          )}
                        </div>
                      )
                    })()}
                    {(() => {
                      const ns = mergeRunStringLists(lastBoRun.notes, lastBoRun.notes_json)
                      return (
                        <div className="space-y-2">
                          <p className="text-sm font-medium">notes</p>
                          {ns.length > 0 ? (
                            <ul className="list-inside list-disc text-sm text-muted-foreground">
                              {ns.map((n) => (
                                <li key={n}>{n}</li>
                              ))}
                            </ul>
                          ) : (
                            <p className="text-sm text-muted-foreground">notes: none</p>
                          )}
                        </div>
                      )
                    })()}
                    {(() => {
                      const d = lastBoRun.diagnostics_json ?? lastBoRun.diagnostics
                      const populated =
                        d != null &&
                        (typeof d === "string"
                          ? d.trim().length > 0
                          : isRecord(d)
                            ? Object.keys(d).length > 0
                            : Array.isArray(d)
                              ? d.length > 0
                              : true)
                      return populated ? (
                        <div className="space-y-2">
                          <p className="text-sm font-medium">diagnostics</p>
                          <pre className="max-h-48 overflow-auto rounded-md bg-muted/40 p-3 text-xs leading-relaxed">
                            {typeof d === "string" ? d : jsonPreview(d, 4000)}
                          </pre>
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">diagnostics: none</p>
                      )
                    })()}
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">Run response could not be parsed as an object.</p>
                )}
                <Collapsible className="rounded-md border border-border">
                  <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm font-medium hover:bg-muted/50">
                    Developer JSON
                    <ChevronDown className="h-4 w-4 shrink-0 opacity-70" />
                  </CollapsibleTrigger>
                  <CollapsibleContent className="border-t border-border px-3 py-3">
                    <DeveloperJsonPanel data={lastBoRun} />
                  </CollapsibleContent>
                </Collapsible>
              </div>
            </ModuleCard>
          ) : (
            <p className="text-sm text-muted-foreground">
              After you run Bayesian optimization, this panel shows BO run ID, algorithm, model_type, status, warnings,
              notes, and diagnostics from the POST response.
            </p>
          )}

          {lastOptimizationRun != null ? (
            <ModuleCard
              accent="violet"
              eyebrow="Optimization · Latest Run"
              title="latest optimization run"
              description="Fields from the POST response: status, model, experiment count, metrics_json, recommendations_json, warnings, and notes."
            >
              <div className="space-y-4">
                {isRecord(lastOptimizationRun) ? (
                  <>
                    <div className="flex flex-wrap gap-2 text-sm">
                      <Badge variant="outline">status: {String(lastOptimizationRun.status ?? "—")}</Badge>
                      <Badge variant="outline" className="font-mono">
                        model_type: {String(lastOptimizationRun.model_type ?? "—")}
                      </Badge>
                      <Badge variant="outline" className="tabular-nums">
                        input_experiment_count: {String(lastOptimizationRun.input_experiment_count ?? "—")}
                      </Badge>
                    </div>
                    <MlModelProvenanceSummary
                      sources={[lastOptimizationRun]}
                      className="rounded-md border border-dashed px-3 py-2"
                    />
                    {(() => {
                      const m = lastOptimizationRun.metrics_json
                      const populated = isRecord(m) && Object.keys(m).length > 0
                      return populated ? (
                        <div className="space-y-2">
                          <p className="text-sm font-medium">metrics_json</p>
                          <pre className="max-h-48 overflow-auto rounded-md bg-muted/40 p-3 text-xs leading-relaxed">
                            {jsonPreview(m, 4000)}
                          </pre>
                        </div>
                      ) : null
                    })()}
                    {(() => {
                      const recs = lastOptimizationRun.recommendations_json
                      const n = Array.isArray(recs) ? recs.length : 0
                      return (
                        <p className="text-sm text-muted-foreground">
                          recommendations_json returned {n} row{n === 1 ? "" : "s"} — see the Recommendations tab to review
                          each promising condition.
                        </p>
                      )
                    })()}
                    {(() => {
                      const ws = mergeRunStringLists(
                        lastOptimizationRun.warnings,
                        lastOptimizationRun.warnings_json,
                      )
                      return ws.length > 0 ? (
                        <div className="space-y-2">
                          <p className="text-sm font-medium">warnings</p>
                          <ul className="list-inside list-disc text-sm text-muted-foreground">
                            {ws.map((w) => (
                              <li key={w}>{w}</li>
                            ))}
                          </ul>
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">warnings: none</p>
                      )
                    })()}
                    {(() => {
                      const ns = mergeRunStringLists(lastOptimizationRun.notes, lastOptimizationRun.notes_json)
                      return ns.length > 0 ? (
                        <div className="space-y-2">
                          <p className="text-sm font-medium">notes</p>
                          <ul className="list-inside list-disc text-sm text-muted-foreground">
                            {ns.map((n) => (
                              <li key={n}>{n}</li>
                            ))}
                          </ul>
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">notes: none</p>
                      )
                    })()}
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">Run response could not be parsed as an object.</p>
                )}
                <DeveloperJsonPanel data={lastOptimizationRun} />
              </div>
            </ModuleCard>
          ) : (
            <p className="text-sm text-muted-foreground">
              After you run optimization, this panel shows run status, metrics_json, and recommendations_json counts from
              the POST response.
            </p>
          )}

          <ModuleCard
            accent="violet"
            eyebrow="Optimization · Benchmark"
            title={
              <span className="inline-flex items-center gap-2">
                Optimization Benchmark / Replay
                <InfoTooltip content={BENCHMARK_TOOLTIP} label="About benchmarking" />
              </span>
            }
            description="Benchmark optimization algorithms against this project's historical experiment data. Results compare relative algorithm behavior on this dataset only — not universal superiority."
          >
            <div className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="bench-name">benchmark_name</Label>
                  <Input
                    id="bench-name"
                    value={benchmarkName}
                    onChange={(e) => setBenchmarkName(e.target.value)}
                    placeholder="Optional label for this benchmark run"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="bench-alg">algorithm</Label>
                  <Select value={benchmarkAlgorithm} onValueChange={setBenchmarkAlgorithm}>
                    <SelectTrigger id="bench-alg">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {BO_ALGORITHM_OPTIONS.map((opt) => (
                        <SelectItem key={opt} value={opt}>
                          {opt}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="bench-obj">objective</Label>
                  <Select value={benchmarkObjective || objective || OBJECTIVE_TYPE_OPTIONS[0]} onValueChange={setBenchmarkObjective}>
                    <SelectTrigger id="bench-obj">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {OBJECTIVE_TYPE_OPTIONS.map((opt) => (
                        <SelectItem key={opt} value={opt}>
                          {opt}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="bench-budget">experiment_budget</Label>
                  <Input
                    id="bench-budget"
                    inputMode="numeric"
                    min={1}
                    value={benchmarkBudget}
                    onChange={(e) => setBenchmarkBudget(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="bench-seed">
                    random_seed <span className="font-normal text-muted-foreground">(optional)</span>
                  </Label>
                  <Input
                    id="bench-seed"
                    inputMode="numeric"
                    value={benchmarkSeed}
                    onChange={(e) => setBenchmarkSeed(e.target.value)}
                    placeholder="Leave blank for none"
                  />
                </div>
                <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-3 md:col-span-2">
                  <Label htmlFor="bench-use-completed" className="font-mono text-xs">
                    use_completed_project_data
                  </Label>
                  <Switch
                    id="bench-use-completed"
                    checked={useCompletedProjectData}
                    onCheckedChange={(c) => setUseCompletedProjectData(Boolean(c))}
                  />
                </div>
              </div>
              <Button
                type="button"
                onClick={() => void runBenchmark()}
                disabled={
                  busy === "benchmark" ||
                  busy === "optimization" ||
                  busy === "bo-optimization" ||
                  busy === "advisor-run" ||
                  loading
                }
              >
                {busy === "benchmark" ? "Running…" : "Start benchmark"}
              </Button>

              <Separator />

              {lastBenchmarkRun != null && isRecord(lastBenchmarkRun) ? (
                <div className="space-y-4">
                  <p className="text-xs font-medium text-muted-foreground">Latest benchmark response</p>
                  <div className="flex flex-wrap gap-2 text-sm">
                    <Badge variant="outline" className="tabular-nums text-xs">
                      best observed objective: {readBenchmarkBestObserved(lastBenchmarkRun)}
                    </Badge>
                    {readNum(lastBenchmarkRun.simple_regret) != null ||
                    readNum(lastBenchmarkRun.regret) != null ? (
                      <Badge variant="outline" className="tabular-nums text-xs">
                        simple regret: {readBenchmarkRegret(lastBenchmarkRun)}
                      </Badge>
                    ) : null}
                    <Badge variant="outline" className="tabular-nums text-xs">
                      experiments used: {readBenchmarkExperimentsUsed(lastBenchmarkRun)}
                    </Badge>
                  </div>
                  <div className="space-y-2">
                    <p className="text-sm font-medium">trajectory</p>
                    {benchmarkTrajectoryRows.length > 0 ? (
                      <div className="table-scroll">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead className="w-16 text-xs">step</TableHead>
                              <TableHead className="text-xs">row</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {benchmarkTrajectoryRows.map((row, idx) => (
                              <TableRow key={idx}>
                                <TableCell className="font-mono text-xs tabular-nums">
                                  {(() => {
                                    const s =
                                      readNum(row.step) ??
                                      readNum(row.iteration) ??
                                      readNum(row.t) ??
                                      readNum(row.index)
                                    return s != null ? String(s) : String(idx + 1)
                                  })()}
                                </TableCell>
                                <TableCell className="align-top">
                                  <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-2 text-[10px] leading-snug">
                                    {jsonPreview(row, 4000)}
                                  </pre>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">trajectory: none</p>
                    )}
                  </div>
                  {(() => {
                    const ws = mergeRunStringLists(
                      lastBenchmarkRun.warnings,
                      lastBenchmarkRun.warnings_json,
                    )
                    return (
                      <div className="space-y-2">
                        <p className="text-sm font-medium">warnings</p>
                        {ws.length > 0 ? (
                          <ul className="list-inside list-disc text-sm text-muted-foreground">
                            {ws.map((w) => (
                              <li key={w}>{w}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-sm text-muted-foreground">warnings: none</p>
                        )}
                      </div>
                    )
                  })()}
                  {(() => {
                    const ns = mergeRunStringLists(lastBenchmarkRun.notes, lastBenchmarkRun.notes_json)
                    return (
                      <div className="space-y-2">
                        <p className="text-sm font-medium">notes</p>
                        {ns.length > 0 ? (
                          <ul className="list-inside list-disc text-sm text-muted-foreground">
                            {ns.map((n) => (
                              <li key={n}>{n}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-sm text-muted-foreground">notes: none</p>
                        )}
                      </div>
                    )
                  })()}
                  <DeveloperJsonPanel data={lastBenchmarkRun} />
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  After a benchmark POST succeeds, this section shows best observed objective, regret if returned,
                  experiment count, trajectory, warnings, and notes.
                </p>
              )}
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Optimization · Benchmark Runs"
            title="benchmark runs"
            description="Historical algorithm benchmark runs for this project, including algorithm, status, and benchmark name."
          >
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>id</TableHead>
                    <TableHead>status</TableHead>
                    <TableHead className="font-mono text-xs">benchmark_name</TableHead>
                    <TableHead className="font-mono text-xs">algorithm</TableHead>
                    <TableHead>created_at</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {benchmarkRuns.filter(isRecord).map((r, ri) => (
                    <TableRow key={String(r.id ?? `bench-${ri}`)}>
                      <TableCell className="font-mono text-xs">{String(r.id ?? "—")}</TableCell>
                      <TableCell>{String(r.status ?? "")}</TableCell>
                      <TableCell className="max-w-[140px] truncate text-xs">{String(r.benchmark_name ?? "—")}</TableCell>
                      <TableCell className="font-mono text-xs">{String(r.algorithm ?? "—")}</TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{fmtIso(r.created_at)}</TableCell>
                    </TableRow>
                  ))}
                  {!loading && benchmarkRuns.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-muted-foreground">
                        No benchmark runs.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Optimization · Run History"
            title="optimization runs"
            description="Heuristic optimization run history — model type, input experiment count, and status for each run."
          >
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>id</TableHead>
                    <TableHead>status</TableHead>
                    <TableHead>model_type</TableHead>
                    <TableHead className="text-right">input_experiment_count</TableHead>
                    <TableHead>created_at</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {runs.filter(isRecord).map((r) => (
                    <TableRow key={String(r.id)}>
                      <TableCell className="font-mono text-xs">{String(r.id)}</TableCell>
                      <TableCell>{String(r.status ?? "")}</TableCell>
                      <TableCell className="font-mono text-xs">{String(r.model_type ?? "")}</TableCell>
                      <TableCell className="text-right tabular-nums">{String(r.input_experiment_count ?? "—")}</TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {fmtIso(r.created_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                  {!loading && runs.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-muted-foreground">
                        No optimization runs.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </div>
          </ModuleCard>
        </TabsContent>

        <TabsContent value="advisor" className="mt-4 space-y-6">
          <div className="space-y-1">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-violet)" }}
            >
              Project · Optimization Advisor
            </p>
            <h2 className="font-mono text-xl font-bold tracking-tight">LLM-assisted optimization advisor</h2>
            <p className="text-sm text-muted-foreground">
              Run the LLM advisor against literature priors and mechanistic hypotheses; inspect rationale and side-by-side BO comparisons.
            </p>
          </div>
          <ModuleCard
            accent="violet"
            eyebrow="Advisor · Run"
            title="Optimization Advisor"
            description="LLM-assisted advisor integrating BO suggestions, mechanistic hypotheses, and literature priors to flag next-experiment priorities. All recommendations require human review."
          >
            <div className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2">
                {boRuns.filter(isRecord).length > 0 ? (
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="adv-bo-run">bo_run_id</Label>
                    <Select
                      value={advBoRunId.trim() === "" ? "__none__" : advBoRunId.trim()}
                      onValueChange={(v) => setAdvBoRunId(v === "__none__" ? "" : v)}
                    >
                      <SelectTrigger id="adv-bo-run">
                        <SelectValue placeholder="—" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">—</SelectItem>
                        {boRuns.filter(isRecord).map((row) => {
                          const bid = readBoRunId(row)
                          return (
                            <SelectItem key={bid} value={bid}>
                              {bid}{" "}
                              {typeof row.algorithm === "string" ? `· ${row.algorithm}` : ""} · {fmtIso(row.created_at)}
                            </SelectItem>
                          )
                        })}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      Optional — select a completed Bayesian optimization run to provide model-based context to the advisor. Omit to use the latest available run.
                    </p>
                  </div>
                ) : null}

                {recommendationBatchesList.filter(isRecord).length > 0 ? (
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="adv-batch">recommendation_batch_id</Label>
                    <Select
                      value={advBatchId.trim() === "" ? "__none__" : advBatchId.trim()}
                      onValueChange={(v) => setAdvBatchId(v === "__none__" ? "" : v)}
                    >
                      <SelectTrigger id="adv-batch">
                        <SelectValue placeholder="—" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">—</SelectItem>
                        {recommendationBatchesList.filter(isRecord).map((row) => {
                          const bid = readNum(row.id)
                          if (bid == null) return null
                          return (
                            <SelectItem key={bid} value={String(bid)}>
                              {String(bid)} · {fmtIso(row.updated_at ?? row.created_at)}
                            </SelectItem>
                          )
                        })}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      Optional — link a recommendation batch to provide model-ranking context to the advisor.
                    </p>
                  </div>
                ) : null}

                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="adv-mode">advisor_mode</Label>
                  <Select value={advisorMode} onValueChange={setAdvisorMode}>
                    <SelectTrigger id="adv-mode">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ADVISOR_MODE_OPTIONS.map((m) => (
                        <SelectItem key={m} value={m}>
                          {m}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-3 md:col-span-2">
                  <Label htmlFor="adv-cost-safety" className="font-mono text-xs">
                    include_cost_safety_context
                  </Label>
                  <Switch
                    id="adv-cost-safety"
                    checked={advIncludeCostSafety}
                    onCheckedChange={(c) => setAdvIncludeCostSafety(Boolean(c))}
                  />
                </div>
                <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-3 md:col-span-2">
                  <Label htmlFor="adv-completed" className="font-mono text-xs">
                    include_completed_experiments
                  </Label>
                  <Switch
                    id="adv-completed"
                    checked={advIncludeCompletedExperiments}
                    onCheckedChange={(c) => setAdvIncludeCompletedExperiments(Boolean(c))}
                  />
                </div>
                <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-3 md:col-span-2">
                  <Label htmlFor="adv-lit" className="font-mono text-xs">
                    include_literature_priors
                  </Label>
                  <Switch
                    id="adv-lit"
                    checked={advIncludeLiteraturePriors}
                    onCheckedChange={(c) => setAdvIncludeLiteraturePriors(Boolean(c))}
                  />
                </div>

                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="adv-notes">notes</Label>
                  <Textarea
                    id="adv-notes"
                    rows={3}
                    value={advNotes}
                    onChange={(e) => setAdvNotes(e.target.value)}
                    className="text-sm"
                  />
                  <p className="text-xs text-muted-foreground">Optional — stored in metadata_json when provided.</p>
                </div>
              </div>

              <Button
                type="button"
                onClick={() => void runAdvisor()}
                disabled={
                  busy === "advisor-run" ||
                  busy === "optimization" ||
                  busy === "bo-optimization" ||
                  busy === "benchmark" ||
                  loading
                }
              >
                {busy === "advisor-run" ? "Running…" : "Run Advisor"}
              </Button>

              {!loading && advisorRunsList.filter(isRecord).length > 0 ? (
                <div className="table-scroll space-y-2">
                  <p className="text-xs font-medium text-muted-foreground">
                    Advisor run history for this project
                  </p>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">advisor_run_id</TableHead>
                        <TableHead className="text-xs">status</TableHead>
                        <TableHead className="text-xs">advisor_mode</TableHead>
                        <TableHead className="text-xs">created_at</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {advisorRunsList.filter(isRecord).map((row, ri) => (
                        <TableRow key={String(row.id ?? row.advisor_run_id ?? ri)}>
                          <TableCell className="font-mono text-xs">
                            {String(readNum(row.advisor_run_id ?? row.id) ?? "—")}
                          </TableCell>
                          <TableCell className="text-xs">{String(row.status ?? "")}</TableCell>
                          <TableCell className="font-mono text-xs">{String(row.advisor_mode ?? "")}</TableCell>
                          <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                            {fmtIso(row.created_at)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ) : null}

              {lastAdvisorRun != null && isRecord(lastAdvisorRun) ? (
                <div className="space-y-4 border-t border-border pt-4">
                  {String(lastAdvisorRun.advisor_mode ?? "") === "rule_based_mechanistic" ? (
                    <Alert>
                      <AlertTitle className="text-sm">Mechanistic advisor mode</AlertTitle>
                      <AlertDescription className="text-xs">
                        Rule-based mechanistic advisor was used. External LLM guidance is not configured.
                      </AlertDescription>
                    </Alert>
                  ) : null}
                  {readMetadataBool(lastAdvisorRun, "llm_guided_configured") ? (
                    <Alert>
                      <AlertTitle className="text-sm">LLM guidance</AlertTitle>
                      <AlertDescription className="text-xs">LLM-guided advisory mode enabled.</AlertDescription>
                    </Alert>
                  ) : null}

                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className="font-mono text-xs">
                      advisor_mode: {String(lastAdvisorRun.advisor_mode ?? "—")}
                    </Badge>
                    <Badge variant="outline" className="text-xs">
                      status: {String(lastAdvisorRun.status ?? "—")}
                    </Badge>
                    <Badge variant="outline" className="tabular-nums text-xs">
                      recommendation_count:{" "}
                      {String(readNum(lastAdvisorRun.recommendation_count) ?? "—")}
                    </Badge>
                    <Badge variant="outline" className="tabular-nums text-xs">
                      critiques:{" "}
                      {Array.isArray(lastAdvisorRun.critiques) ? lastAdvisorRun.critiques.length : "—"}
                    </Badge>
                    <Badge variant="outline" className="tabular-nums text-xs">
                      hypotheses:{" "}
                      {Array.isArray(lastAdvisorRun.hypotheses) ? lastAdvisorRun.hypotheses.length : "—"}
                    </Badge>
                    <Badge variant="outline" className="tabular-nums text-xs">
                      agreements:{" "}
                      {Array.isArray(lastAdvisorRun.agreements)
                        ? lastAdvisorRun.agreements.length
                        : "—"}
                    </Badge>
                    <Badge variant="outline" className="tabular-nums text-xs">
                      disagreements:{" "}
                      {Array.isArray(lastAdvisorRun.disagreements)
                        ? lastAdvisorRun.disagreements.length
                        : "—"}
                    </Badge>
                    <Badge
                      variant={lastAdvisorRun.human_review_required === true ? "secondary" : "outline"}
                      className="text-xs"
                    >
                      human_review_required: {String(lastAdvisorRun.human_review_required)}
                    </Badge>
                  </div>

                  <MlModelProvenanceSummary
                    sources={[lastAdvisorRun]}
                    className="rounded-md border border-dashed px-3 py-2"
                  />

                  {(() => {
                    const ws = mergeRunStringLists(lastAdvisorRun.warnings, lastAdvisorRun.warnings_json)
                    return (
                      <div className="space-y-2">
                        <p className="text-sm font-medium">warnings</p>
                        {ws.length > 0 ? (
                          <ul className="list-inside list-disc text-sm text-muted-foreground">
                            {ws.map((w, i) => (
                              <li key={`adv-w-${i}-${w.slice(0, 24)}`}>{w}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-sm text-muted-foreground">warnings: none</p>
                        )}
                      </div>
                    )
                  })()}

                  {(() => {
                    const ns = mergeRunStringLists(lastAdvisorRun.notes, lastAdvisorRun.notes_json)
                    return (
                      <div className="space-y-2">
                        <p className="text-sm font-medium">notes</p>
                        {ns.length > 0 ? (
                          <ul className="list-inside list-disc text-sm text-muted-foreground">
                            {ns.map((n, i) => (
                              <li key={`${i}-${n}`}>{n}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-sm text-muted-foreground">notes: none</p>
                        )}
                      </div>
                    )
                  })()}

                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <p className="text-sm font-medium">agreements</p>
                      {Array.isArray(lastAdvisorRun.agreements) && lastAdvisorRun.agreements.length > 0 ? (
                        <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-3 text-[10px] leading-snug">
                          {jsonPreview(lastAdvisorRun.agreements, 6000)}
                        </pre>
                      ) : (
                        <p className="text-sm text-muted-foreground">agreements: none</p>
                      )}
                    </div>
                    <div className="space-y-2">
                      <p className="text-sm font-medium">disagreements</p>
                      {Array.isArray(lastAdvisorRun.disagreements) && lastAdvisorRun.disagreements.length > 0 ? (
                        <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-3 text-[10px] leading-snug">
                          {jsonPreview(lastAdvisorRun.disagreements, 6000)}
                        </pre>
                      ) : (
                        <p className="text-sm text-muted-foreground">disagreements: none</p>
                      )}
                    </div>
                  </div>

                  <Collapsible className="rounded-md border border-border">
                    <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm font-medium hover:bg-muted/50">
                      Developer JSON
                      <ChevronDown className="h-4 w-4 shrink-0 opacity-70" />
                    </CollapsibleTrigger>
                    <CollapsibleContent className="border-t border-border px-3 py-3">
                      <DeveloperJsonPanel data={lastAdvisorRun} />
                    </CollapsibleContent>
                  </Collapsible>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  After running the advisor, this panel shows the run summary: mode, status, agreed and disagreed conditions, warnings, and whether human review is required.
                </p>
              )}
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Advisor · Mechanistic Hypotheses"
            title={
              <span className="inline-flex items-center gap-2">
                Mechanistic hypotheses
                <InfoTooltip content={MECHANISTIC_HYPOTHESES_TOOLTIP} label="About mechanistic hypotheses" />
              </span>
            }
            description="Mechanistic hypotheses linking observed experimental trends to proposed reaction mechanisms. Indicative only — not proof of mechanism."
          >
            <div className="space-y-6">
              <form className="space-y-4" onSubmit={(e) => void createMechanisticHypothesis(e)}>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="mh-title">title</Label>
                    <Input
                      id="mh-title"
                      value={mhTitle}
                      onChange={(e) => setMhTitle(e.target.value)}
                      maxLength={240}
                      autoComplete="off"
                    />
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="mh-hypothesis">hypothesis</Label>
                    <Textarea
                      id="mh-hypothesis"
                      rows={4}
                      value={mhHypothesis}
                      onChange={(e) => setMhHypothesis(e.target.value)}
                      className="text-sm"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="mh-confidence">confidence_label</Label>
                    <Select value={mhConfidence} onValueChange={setMhConfidence}>
                      <SelectTrigger id="mh-confidence">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {MECHANISTIC_CONFIDENCE_LABELS.map((c) => (
                          <SelectItem key={c} value={c}>
                            {c}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="mh-supporting">supporting_observations_json</Label>
                    <p className="text-xs text-muted-foreground">JSON array or object; leave empty for none.</p>
                    <Textarea
                      id="mh-supporting"
                      rows={3}
                      value={mhSupportingJson}
                      onChange={(e) => setMhSupportingJson(e.target.value)}
                      className="font-mono text-xs"
                      placeholder="[]"
                    />
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="mh-contradicting">contradicting_observations_json</Label>
                    <p className="text-xs text-muted-foreground">JSON array or object; leave empty for none.</p>
                    <Textarea
                      id="mh-contradicting"
                      rows={3}
                      value={mhContradictingJson}
                      onChange={(e) => setMhContradictingJson(e.target.value)}
                      className="font-mono text-xs"
                      placeholder="[]"
                    />
                  </div>
                </div>
                <Button type="submit" disabled={busy != null || loading}>
                  {busy === "mh-create" ? "Saving…" : "Add hypothesis"}
                </Button>
              </form>

              <Separator />

              <div className="space-y-4">
                {mechanisticHypotheses.filter(isRecord).map((row) => {
                  const hid = readNum(row.id)
                  if (hid == null) return null
                  const st = typeof row.status === "string" ? row.status : ""
                  const conf = typeof row.confidence_label === "string" ? row.confidence_label : ""
                  const sup = row.supporting_observations_json
                  const con = row.contradicting_observations_json
                  return (
                    <Card key={hid} className="border-muted">
                      <CardHeader className="pb-2">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <CardTitle className="text-sm font-medium leading-snug">{String(row.title ?? "")}</CardTitle>
                          <div className="flex flex-wrap gap-2">
                            <Badge variant="outline" className="font-mono text-xs">
                              confidence_label: {conf || "—"}
                            </Badge>
                            <Badge variant="secondary" className="font-mono text-xs">
                              status: {st || "—"}
                            </Badge>
                            {row.human_review_required === true ? (
                              <Badge variant="outline" className="text-xs">
                                human_review_required
                              </Badge>
                            ) : null}
                          </div>
                        </div>
                        <CardDescription className="text-xs">
                          id {hid} · updated {fmtIso(row.updated_at)}
                        </CardDescription>
                      </CardHeader>
                      <CardContent className="space-y-4 text-sm">
                        <div className="space-y-1">
                          <p className="text-xs font-medium uppercase text-muted-foreground">hypothesis</p>
                          <p className="text-muted-foreground">{String(row.hypothesis ?? "")}</p>
                        </div>
                        <div className="grid gap-4 sm:grid-cols-2">
                          <div className="space-y-2">
                            <Label className="text-xs" htmlFor={`mh-st-${hid}`}>
                              status
                            </Label>
                            <Select
                              value={st || "proposed"}
                              onValueChange={(v) => void patchMechanisticHypothesis(hid, { status: v })}
                              disabled={busy != null || loading}
                            >
                              <SelectTrigger id={`mh-st-${hid}`}>
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {MECHANISTIC_HYPOTHESIS_STATUS.map((s) => (
                                  <SelectItem key={s} value={s}>
                                    {s}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                          <div className="space-y-2">
                            <Label className="text-xs" htmlFor={`mh-conf-${hid}`}>
                              confidence_label
                            </Label>
                            <Select
                              value={conf || "speculative"}
                              onValueChange={(v) => void patchMechanisticHypothesis(hid, { confidence_label: v })}
                              disabled={busy != null || loading}
                            >
                              <SelectTrigger id={`mh-conf-${hid}`}>
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {MECHANISTIC_CONFIDENCE_LABELS.map((c) => (
                                  <SelectItem key={c} value={c}>
                                    {c}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        </div>
                        <div className="space-y-2">
                          <p className="text-xs font-medium uppercase text-muted-foreground">
                            supporting_observations_json
                          </p>
                          <pre className="max-h-40 overflow-auto rounded-md bg-muted/40 p-3 text-[10px] leading-snug">
                            {jsonPreview(sup ?? [], 8000)}
                          </pre>
                        </div>
                        <div className="space-y-2">
                          <p className="text-xs font-medium uppercase text-muted-foreground">
                            contradicting_observations_json
                          </p>
                          <pre className="max-h-40 overflow-auto rounded-md bg-muted/40 p-3 text-[10px] leading-snug">
                            {jsonPreview(con ?? [], 8000)}
                          </pre>
                        </div>
                      </CardContent>
                    </Card>
                  )
                })}
                {!loading && mechanisticHypotheses.filter(isRecord).length === 0 ? (
                  <p className="text-sm text-muted-foreground">No mechanistic hypotheses yet.</p>
                ) : null}
              </div>
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Advisor · Literature Priors"
            title={
              <span className="inline-flex items-center gap-2">
                Reaction priors and literature notes
                <InfoTooltip content={LITERATURE_PRIORS_TOOLTIP} label="About reaction priors" />
              </span>
            }
            description="Literature references, prior knowledge summaries, and user-entered citations used as advisor context. Citations are not generated by the platform."
          >
            <div className="space-y-6">
              <form className="space-y-4" onSubmit={(e) => void createLiteraturePrior(e)}>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="lp-source">source_type</Label>
                    <Select value={lpSourceType} onValueChange={setLpSourceType}>
                      <SelectTrigger id="lp-source">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {LITERATURE_PRIOR_SOURCE_TYPES.map((s) => (
                          <SelectItem key={s} value={s}>
                            {s}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="lp-title">title</Label>
                    <Input
                      id="lp-title"
                      value={lpTitle}
                      onChange={(e) => setLpTitle(e.target.value)}
                      maxLength={240}
                      autoComplete="off"
                    />
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="lp-summary">summary</Label>
                    <Textarea
                      id="lp-summary"
                      rows={4}
                      value={lpSummary}
                      onChange={(e) => setLpSummary(e.target.value)}
                      className="text-sm"
                    />
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="lp-citation">citation</Label>
                    <p className="text-xs text-muted-foreground">Optional — paste or type a real reference only.</p>
                    <Textarea
                      id="lp-citation"
                      rows={2}
                      value={lpCitation}
                      onChange={(e) => setLpCitation(e.target.value)}
                      className="text-sm"
                      maxLength={2000}
                    />
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="lp-tags">relevance_tags_json</Label>
                    <p className="text-xs text-muted-foreground">
                      JSON array (e.g. [&quot;solvent&quot;, &quot;amidation&quot;]) or object; leave empty for none.
                    </p>
                    <Textarea
                      id="lp-tags"
                      rows={2}
                      value={lpTagsJson}
                      onChange={(e) => setLpTagsJson(e.target.value)}
                      className="font-mono text-xs"
                      placeholder="[]"
                    />
                  </div>
                </div>
                <Button type="submit" disabled={busy != null || loading}>
                  {busy === "lp-create" ? "Saving…" : "Add prior"}
                </Button>
              </form>

              <Separator />

              <div className="table-scroll space-y-4">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">source_type</TableHead>
                      <TableHead className="text-xs">title</TableHead>
                      <TableHead className="min-w-[200px] text-xs">summary</TableHead>
                      <TableHead className="min-w-[140px] text-xs">citation</TableHead>
                      <TableHead className="text-xs">relevance_tags_json</TableHead>
                      <TableHead className="text-xs">created_at</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {literaturePriors.filter(isRecord).map((row) => {
                      const pid = readNum(row.id)
                      if (pid == null) return null
                      const st = typeof row.source_type === "string" ? row.source_type : ""
                      return (
                        <TableRow key={pid}>
                          <TableCell className="align-top">
                            <div className="flex flex-col gap-1">
                              <Badge variant="outline" className="font-mono text-[10px] w-fit">
                                {st || "—"}
                              </Badge>
                              {row.human_review_required === true ? (
                                <Badge variant="secondary" className="text-[10px] w-fit">
                                  human_review_required
                                </Badge>
                              ) : null}
                            </div>
                          </TableCell>
                          <TableCell className="max-w-[160px] align-top text-sm font-medium">
                            {String(row.title ?? "")}
                          </TableCell>
                          <TableCell className="max-w-[280px] align-top text-xs text-muted-foreground">
                            <span className="line-clamp-6">{String(row.summary ?? "")}</span>
                          </TableCell>
                          <TableCell className="max-w-[200px] align-top text-xs text-muted-foreground">
                            {literaturePriorCitationLine(row.citation)}
                          </TableCell>
                          <TableCell className="align-top">
                            <LiteraturePriorRelevanceTags tags={row.relevance_tags_json} />
                          </TableCell>
                          <TableCell className="whitespace-nowrap align-top text-xs text-muted-foreground">
                            {fmtIso(row.created_at)}
                          </TableCell>
                        </TableRow>
                      )
                    })}
                    {!loading && literaturePriors.filter(isRecord).length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="text-muted-foreground">
                          No literature priors yet.
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </div>
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Advisor · BO Comparison"
            title={
              <span className="inline-flex items-center gap-2">
                BO vs Advisor comparison
                <InfoTooltip content={BO_ADVISOR_COMPARISON_TOOLTIP} label="About BO vs Advisor comparison" />
              </span>
            }
            description="Compare Bayesian optimization rankings with advisor concern signals to surface agreement and disagreement across candidates. Output is advisory — final experiment scheduling requires human review."
          >
            <div className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="cmp-bo-run">bo_run_id</Label>
                  <Select
                    value={cmpBoRunId.trim() === "" ? "__none__" : cmpBoRunId.trim()}
                    onValueChange={(v) => setCmpBoRunId(v === "__none__" ? "" : v)}
                  >
                    <SelectTrigger id="cmp-bo-run">
                      <SelectValue placeholder="—" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">—</SelectItem>
                      {boRuns.filter(isRecord).map((row) => {
                        const bid = readBoRunId(row)
                        return (
                          <SelectItem key={`cmp-bo-${bid}`} value={bid}>
                            {bid} {typeof row.algorithm === "string" ? `· ${row.algorithm}` : ""} ·{" "}
                            {fmtIso(row.created_at)}
                          </SelectItem>
                        )
                      })}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cmp-advisor-run">advisor_run_id</Label>
                  <Select
                    value={cmpAdvisorRunId.trim() === "" ? "__none__" : cmpAdvisorRunId.trim()}
                    onValueChange={(v) => setCmpAdvisorRunId(v === "__none__" ? "" : v)}
                  >
                    <SelectTrigger id="cmp-advisor-run">
                      <SelectValue placeholder="—" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">—</SelectItem>
                      {advisorRunsList.filter(isRecord).map((row, ri) => {
                        const rid = readNum(row.advisor_run_id ?? row.id)
                        if (rid == null) return null
                        return (
                          <SelectItem key={`cmp-adv-${rid}-${ri}`} value={String(rid)}>
                            {String(rid)} · {String(row.advisor_mode ?? "")} · {fmtIso(row.created_at)}
                          </SelectItem>
                        )
                      })}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <Button
                type="button"
                onClick={() => void compareBoAdvisorRecommendations()}
                disabled={busy != null || loading}
              >
                {busy === "bo-advisor-compare" ? "Comparing…" : "Compare recommendations"}
              </Button>

              {lastComparison != null && isRecord(lastComparison) ? (
                <div className="space-y-4 border-t border-border pt-4">
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="outline" className="font-mono text-xs">
                      bo_run_id: {String(lastComparison.bo_run_id ?? "—")}
                    </Badge>
                    <Badge variant="outline" className="font-mono text-xs">
                      advisor_run_id: {String(lastComparison.advisor_run_id ?? "—")}
                    </Badge>
                    <Badge variant="secondary" className="text-xs">
                      requires review
                    </Badge>
                    {lastComparison.human_review_required === true ? (
                      <Badge variant="outline" className="text-xs">
                        human_review_required
                      </Badge>
                    ) : null}
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <p className="text-sm font-medium">agreements (agrees / BO-supported)</p>
                      {Array.isArray(lastComparison.agreements) && lastComparison.agreements.length > 0 ? (
                        <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-3 text-[10px] leading-snug">
                          {jsonPreview(lastComparison.agreements, 8000)}
                        </pre>
                      ) : (
                        <p className="text-sm text-muted-foreground">agreements: none</p>
                      )}
                    </div>
                    <div className="space-y-2">
                      <p className="text-sm font-medium">disagreements (disagrees / advisor concern)</p>
                      {Array.isArray(lastComparison.disagreements) && lastComparison.disagreements.length > 0 ? (
                        <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-3 text-[10px] leading-snug">
                          {jsonPreview(lastComparison.disagreements, 8000)}
                        </pre>
                      ) : (
                        <p className="text-sm text-muted-foreground">disagreements: none</p>
                      )}
                    </div>
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <p className="text-sm font-medium">BO summary</p>
                      <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-3 text-[10px] leading-snug">
                        {jsonPreview(lastComparison.bo_summary_json ?? {}, 8000)}
                      </pre>
                    </div>
                    <div className="space-y-2">
                      <p className="text-sm font-medium">advisor summary</p>
                      <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-3 text-[10px] leading-snug">
                        {jsonPreview(lastComparison.advisor_summary_json ?? {}, 8000)}
                      </pre>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <p className="text-sm font-medium">risk flags</p>
                    <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-3 text-[10px] leading-snug">
                      {jsonPreview(lastComparison.metadata_json ?? {}, 4000)}
                    </pre>
                  </div>

                  <div className="space-y-1">
                    <p className="text-sm font-medium">final review recommendation</p>
                    <p className="text-sm text-muted-foreground">
                      {String(lastComparison.final_review_recommendation ?? "—")}
                    </p>
                  </div>

                  <Collapsible className="rounded-md border border-border">
                    <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm font-medium hover:bg-muted/50">
                      Developer JSON
                      <ChevronDown className="h-4 w-4 shrink-0 opacity-70" />
                    </CollapsibleTrigger>
                    <CollapsibleContent className="border-t border-border px-3 py-3">
                      <DeveloperJsonPanel data={lastComparison} />
                    </CollapsibleContent>
                  </Collapsible>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No comparison yet — select runs and compare recommendations. Agreement/disagreement output is advisory
                  and requires review.
                </p>
              )}

              {!loading && comparisons.filter(isRecord).length > 0 ? (
                <div className="table-scroll space-y-2">
                  <p className="text-xs font-medium text-muted-foreground">
                    BO vs. advisor comparison history for this project
                  </p>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">id</TableHead>
                        <TableHead className="text-xs">bo_run_id</TableHead>
                        <TableHead className="text-xs">advisor_run_id</TableHead>
                        <TableHead className="text-xs">final_review_recommendation</TableHead>
                        <TableHead className="text-xs">created_at</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {comparisons.filter(isRecord).map((row, ri) => (
                        <TableRow key={String(row.id ?? `cmp-${ri}`)}>
                          <TableCell className="font-mono text-xs">{String(row.id ?? "—")}</TableCell>
                          <TableCell className="font-mono text-xs">{String(row.bo_run_id ?? "—")}</TableCell>
                          <TableCell className="font-mono text-xs">{String(row.advisor_run_id ?? "—")}</TableCell>
                          <TableCell className="max-w-[220px] text-xs text-muted-foreground">
                            {String(row.final_review_recommendation ?? "—")}
                          </TableCell>
                          <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                            {fmtIso(row.created_at)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ) : null}
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Advisor · Condition Critique"
            title="Condition Critique"
            description="Condition-level critique from the advisor when available — lab-dependent interpretation still required."
          >
            {lastAdvisorRun != null &&
            isRecord(lastAdvisorRun) &&
            Array.isArray(lastAdvisorRun.critiques) &&
            lastAdvisorRun.critiques.length > 0 ? (
              <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-3 text-[10px] leading-snug">
                {jsonPreview(lastAdvisorRun.critiques, 8000)}
              </pre>
            ) : (
              <p className="text-sm text-muted-foreground">No condition critique returned yet.</p>
            )}
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Advisor · Human Review"
            title="Human Review"
            description="Record a human review decision on an advisor run — approve, flag for revision, or reject. Advisor output is decision-support only and does not autonomously schedule experiments."
          >
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="advisor-review-run">advisor_run_id</Label>
                  <Select
                    value={advisorReviewRunId.trim() === "" ? "__none__" : advisorReviewRunId.trim()}
                    onValueChange={(v) => setAdvisorReviewRunId(v === "__none__" ? "" : v)}
                  >
                    <SelectTrigger id="advisor-review-run">
                      <SelectValue placeholder="—" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">—</SelectItem>
                      {advisorRunsList.filter(isRecord).map((row, ri) => {
                        const rid = readNum(row.advisor_run_id ?? row.id)
                        if (rid == null) return null
                        return (
                          <SelectItem key={`review-adv-${rid}-${ri}`} value={String(rid)}>
                            {String(rid)} · {String(row.advisor_mode ?? "")} · {fmtIso(row.created_at)}
                          </SelectItem>
                        )
                      })}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="advisor-reviewer-name">reviewer_name</Label>
                  <Input
                    id="advisor-reviewer-name"
                    autoComplete="name"
                    value={advisorReviewerName}
                    onChange={(e) => setAdvisorReviewerName(e.target.value)}
                    placeholder="Your name"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="advisor-review-decision">decision</Label>
                  <Select value={advisorReviewDecision} onValueChange={setAdvisorReviewDecision}>
                    <SelectTrigger id="advisor-review-decision">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ADVISOR_REVIEW_DECISIONS.map((d) => (
                        <SelectItem key={d} value={d}>
                          {d}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="advisor-review-rationale">
                    rationale <span className="text-destructive">(required)</span>
                  </Label>
                  <Textarea
                    id="advisor-review-rationale"
                    rows={4}
                    value={advisorReviewRationale}
                    onChange={(e) => setAdvisorReviewRationale(e.target.value)}
                    placeholder="Required review comment."
                  />
                </div>
              </div>

              <Button
                type="button"
                onClick={() => void saveAdvisorReview()}
                disabled={busy != null || loading}
              >
                {busy === "advisor-review-save" ? "Saving…" : "Save advisor review"}
              </Button>

              <Alert>
                <AlertTitle className="text-sm">Scheduling guardrail</AlertTitle>
                <AlertDescription className="text-xs">
                  Accepted advisor output does not automatically schedule experiments. Scheduling still requires
                  recommendation approval on the Recommendations tab when implemented.
                </AlertDescription>
              </Alert>

              {(() => {
                const review = advisorRunReviewFromRecord(lastAdvisorRun)
                if (!review) return <p className="text-sm text-muted-foreground">No advisor review saved yet.</p>
                return (
                  <div className="space-y-2 rounded-md border border-border p-3">
                    <p className="text-sm font-medium">Latest review</p>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="outline" className="font-mono text-xs">
                        decision: {String(review.decision ?? "—")}
                      </Badge>
                      <Badge variant="outline" className="text-xs">
                        reviewer: {String(review.reviewer_name ?? "—")}
                      </Badge>
                      <Badge variant="outline" className="text-xs">
                        reviewed_at: {fmtIso(review.reviewed_at)}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">{String(review.rationale ?? "")}</p>
                  </div>
                )
              })()}
            </div>
          </ModuleCard>
        </TabsContent>

        <TabsContent value="recommendations" className="mt-4 space-y-6">
          <div className="space-y-1">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-violet)" }}
            >
              Project · Recommendations
            </p>
            <h2 className="font-mono text-xl font-bold tracking-tight">Reviewer queue &amp; approvals</h2>
            <p className="text-sm text-muted-foreground">
              Approve, reject, or convert recommendations to experiments. Chemist sign-off is required before execution.
            </p>
          </div>
          <ModuleCard
            accent="violet"
            eyebrow="Recommendations · Reviewer"
            title="Reviewer"
            description={
              <>
                POST …/reaction-recommendations/{"{recommendation_id}"}/approve and …/reject require reviewer_name and
                reviewer_comment (human approval). Outputs are decision-support; each recommended next experiment
                requires human review.
              </>
            }
          >
            <div className="space-y-2">
              <Label htmlFor="rec-reviewer-name">reviewer_name</Label>
              <Input
                id="rec-reviewer-name"
                autoComplete="name"
                value={revReviewerName}
                onChange={(e) => setRevReviewerName(e.target.value)}
                placeholder="Your name"
              />
              <p className="text-xs text-muted-foreground">
                Shared across approve/reject on this tab. Each row needs a reviewer_comment before approval or rejection.
              </p>
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Recommendations · Latest BO Batch"
            title="Latest BO recommendation batch"
            description="Most recent Bayesian optimization recommendation batch — ranked candidates with predicted scores, model uncertainty, and estimated improvement. All values are probabilistic and require human review."
          >
            <div className="space-y-4">
              {!loading && latestBatchRows.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No recommendation batches loaded — run Bayesian optimization or wait for batch data from the backend.
                </p>
              ) : (
                <div className="table-scroll">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="whitespace-nowrap text-xs">rank</TableHead>
                        <TableHead className="text-xs">label</TableHead>
                        <TableHead className="min-w-[140px] text-xs">proposed conditions</TableHead>
                        <TableHead className="text-xs">predicted score</TableHead>
                        <TableHead className="text-xs">estimated improvement</TableHead>
                        <TableHead className="min-w-[100px] text-xs">model uncertainty</TableHead>
                        <TableHead className="text-xs">estimated cost</TableHead>
                        <TableHead className="text-xs">safety status</TableHead>
                        <TableHead className="text-xs">acquisition score</TableHead>
                        <TableHead className="min-w-[120px] text-xs">rationale</TableHead>
                        <TableHead className="text-xs">status</TableHead>
                        <TableHead className="min-w-[160px] text-xs">reviewer_comment</TableHead>
                        <TableHead className="text-xs"> </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {loading ? (
                        <TableRow>
                          <TableCell colSpan={13} className="text-muted-foreground">
                            Loading…
                          </TableCell>
                        </TableRow>
                      ) : (
                        latestBatchRows.flatMap((r) => {
                          const id = readNum(r.id)
                          if (id == null) return []
                          const st = String(r.status ?? "")
                          const canReview = st === "proposed"
                          const conditionsJson = r.conditions_json ?? r.proposed_conditions
                          const critBusy = busy === `critique-${id}`
                          const critPayload = critiqueByRecommendationId[id]
                          const showCritiqueRow =
                            critBusy || (critPayload != null && isRecord(critPayload))
                          const rowsOut: ReactNode[] = [
                            <TableRow key={id}>
                              <TableCell className="font-mono text-xs tabular-nums">{String(r.rank ?? "—")}</TableCell>
                              <TableCell className="max-w-[120px] text-xs">
                                <Badge variant="outline" className="font-normal">
                                  {formatRecommendationLabel(r.label)}
                                </Badge>
                              </TableCell>
                              <TableCell className="max-w-[180px] align-top">
                                <pre className="max-h-24 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-2 text-[10px] leading-snug">
                                  {jsonPreview(conditionsJson ?? {}, 800)}
                                </pre>
                              </TableCell>
                              <TableCell className="font-mono text-xs tabular-nums">
                                {formatPredictedScoreDisplay(r)}
                              </TableCell>
                              <TableCell className="font-mono text-xs tabular-nums">
                                {formatExpectedImprovementDisplay(r)}
                              </TableCell>
                              <TableCell className="max-w-[140px] align-top">
                                <pre className="max-h-24 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-2 text-[10px] leading-snug">
                                  {jsonPreview(r.uncertainty_json ?? {}, 600)}
                                </pre>
                              </TableCell>
                              <TableCell className="font-mono text-xs tabular-nums">
                                {formatEstimatedCostDisplay(r)}
                              </TableCell>
                              <TableCell className="max-w-[100px] text-xs">{String(r.safety_status ?? "—")}</TableCell>
                              <TableCell className="font-mono text-xs tabular-nums">
                                {formatAcquisitionScoreDisplay(r)}
                              </TableCell>
                              <TableCell className="max-w-[160px] align-top text-xs text-muted-foreground">
                                <span className="line-clamp-4">{String(r.rationale ?? "")}</span>
                              </TableCell>
                              <TableCell className="text-xs">
                                <Badge variant="outline">{st}</Badge>
                              </TableCell>
                              <TableCell className="min-w-[160px] align-top">
                                <Textarea
                                  rows={2}
                                  className="min-h-[52px] text-xs"
                                  value={revComment[id] ?? ""}
                                  onChange={(e) => setRevComment((prev) => ({ ...prev, [id]: e.target.value }))}
                                  placeholder="Required for approve/reject."
                                />
                              </TableCell>
                              <TableCell className="align-top">
                                <div className="flex flex-col gap-1">
                                  <Button
                                    type="button"
                                    size="sm"
                                    variant="secondary"
                                    className="h-8 text-xs"
                                    disabled={busy != null}
                                    onClick={() => void postRecommendationAdvisorCritique(id)}
                                  >
                                    {critBusy ? "…" : "Critique with Advisor"}
                                  </Button>
                                  <Button
                                    type="button"
                                    size="sm"
                                    variant="outline"
                                    className="h-8 text-xs"
                                    disabled={busy != null}
                                    onClick={() => void getRecommendationAdvisorCritique(id)}
                                  >
                                    {critBusy ? "…" : "Fetch critique"}
                                  </Button>
                                  <Button
                                    type="button"
                                    size="sm"
                                    className="h-8 text-xs"
                                    disabled={!canReview || busy != null}
                                    onClick={() => void approveRecommendation(id)}
                                  >
                                    {busy === `approve-${id}` ? "…" : "Approve"}
                                  </Button>
                                  <Button
                                    type="button"
                                    size="sm"
                                    variant="outline"
                                    className="h-8 text-xs"
                                    disabled={!canReview || busy != null}
                                    onClick={() => void rejectRecommendation(id)}
                                  >
                                    {busy === `reject-${id}` ? "…" : "Reject"}
                                  </Button>
                                </div>
                              </TableCell>
                            </TableRow>,
                          ]
                          if (showCritiqueRow) {
                            rowsOut.push(
                              <TableRow key={`${id}-advisor-critique`}>
                                <TableCell colSpan={13} className="align-top bg-muted/10 p-4">
                                  {critBusy && critPayload == null ? (
                                    <p className="text-sm text-muted-foreground">Loading critique…</p>
                                  ) : isRecord(critPayload) ? (
                                    <RecommendationAdvisorCritiqueCard payload={critPayload} />
                                  ) : null}
                                </TableCell>
                              </TableRow>,
                            )
                          }
                          return rowsOut
                        })
                      )}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Recommendations · List"
            title="recommendations"
            description="Proposed next-experiment recommendations from the optimization engine — ranked by predicted improvement. Approve or reject each with a reviewer name and comment."
          >
            <div className="space-y-6">
              {sortedRecs.map((r) => {
                const id = readNum(r.id)
                if (id == null) return null
                const st = String(r.status ?? "")
                const canReview = st === "proposed"
                return (
                  <Card key={id} className="border-muted">
                    <CardHeader className="pb-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <CardTitle className="text-sm font-medium">recommendation_id {id}</CardTitle>
                        <Badge variant="secondary" className="font-mono text-xs">
                          rank {String(r.rank ?? "")}
                        </Badge>
                        <Badge variant="outline">{formatRecommendationLabel(r.label)}</Badge>
                        <Badge variant="outline">{st}</Badge>
                        {r.human_review_required === true ? (
                          <Badge variant="secondary" className="text-xs">
                            requires human review
                          </Badge>
                        ) : null}
                      </div>
                      <CardDescription className="text-xs">{fmtIso(r.updated_at)}</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4 text-sm">
                      <div className="space-y-2">
                        <p className="text-xs font-medium uppercase text-muted-foreground">conditions_json</p>
                        <pre className="max-h-36 overflow-auto rounded-md bg-muted/40 p-3 text-xs leading-relaxed">
                          {jsonPreview(r.conditions_json ?? {}, 4000)}
                        </pre>
                      </div>
                      <div className="space-y-2">
                        <p className="text-xs font-medium uppercase text-muted-foreground">predicted_outcome_json</p>
                        <pre className="max-h-36 overflow-auto rounded-md bg-muted/40 p-3 text-xs leading-relaxed">
                          {jsonPreview(r.predicted_outcome_json ?? {}, 4000)}
                        </pre>
                      </div>
                      <div className="space-y-2">
                        <p className="text-xs font-medium uppercase text-muted-foreground">uncertainty_json</p>
                        <pre className="max-h-36 overflow-auto rounded-md bg-muted/40 p-3 text-xs leading-relaxed">
                          {jsonPreview(r.uncertainty_json ?? {}, 4000)}
                        </pre>
                      </div>
                      <div className="space-y-1">
                        <p className="text-xs font-medium uppercase text-muted-foreground">rationale</p>
                        <p className="text-muted-foreground">{String(r.rationale ?? "")}</p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          disabled={busy != null}
                          onClick={() => void postRecommendationAdvisorCritique(id)}
                        >
                          {busy === `critique-${id}` ? "…" : "Critique with Advisor"}
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={busy != null}
                          onClick={() => void getRecommendationAdvisorCritique(id)}
                        >
                          {busy === `critique-${id}` ? "…" : "Fetch critique"}
                        </Button>
                      </div>
                      {busy === `critique-${id}` && critiqueByRecommendationId[id] == null ? (
                        <p className="text-sm text-muted-foreground">Loading critique…</p>
                      ) : isRecord(critiqueByRecommendationId[id]) ? (
                        <RecommendationAdvisorCritiqueCard payload={critiqueByRecommendationId[id]} />
                      ) : null}
                      <Separator />
                      <div className="space-y-2">
                        <Label htmlFor={`rev-${id}`}>reviewer_comment <span className="text-destructive">(required)</span></Label>
                        <Textarea
                          id={`rev-${id}`}
                          rows={3}
                          value={revComment[id] ?? ""}
                          onChange={(e) => setRevComment((prev) => ({ ...prev, [id]: e.target.value }))}
                          placeholder="Review rationale for approving or rejecting this promising condition."
                        />
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          type="button"
                          size="sm"
                          disabled={!canReview || busy != null}
                          onClick={() => void approveRecommendation(id)}
                        >
                          {busy === `approve-${id}` ? "…" : "Approve"}
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={!canReview || busy != null}
                          onClick={() => void rejectRecommendation(id)}
                        >
                          {busy === `reject-${id}` ? "…" : "Reject"}
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                )
              })}
              {!loading && sortedRecs.length === 0 ? (
                <p className="text-sm text-muted-foreground">No recommendations.</p>
              ) : null}
            </div>
          </ModuleCard>
        </TabsContent>

        <TabsContent value="execution" className="mt-4 min-w-0 max-w-full space-y-6">
          <div className="space-y-1">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-violet)" }}
            >
              Project · Execution
            </p>
            <h2 className="font-mono text-xl font-bold tracking-tight">Lab execution batches &amp; outcomes</h2>
            <p className="text-sm text-muted-foreground">
              Track approved recommendations through execution batches, mark items running / completed / failed, and confirm outcomes against SpectraCheck-linked analytics. Not autonomous — requires human confirmation.
            </p>
          </div>
          <AlertCard
            variant="info"
            title="Human confirmation"
            description="This tab summarizes execution-related project data. It does not autonomously run reactions, schedule lab work, or approve recommendations."
          />

          {confirmedReactionOutcomesCount > 0 ? (
            <ModuleCard
              accent="violet"
              eyebrow="Execution · Cycle Ready"
              title="Ready for next optimization cycle"
              description="Confirmed outcomes are ready to seed the next optimization cycle. Bayesian optimization and advisor runs use the saved objective, cost, and safety profiles — neither triggers automatically after outcome confirmation."
            >
              <div className="space-y-4">
                <div className="rounded-md border border-border bg-muted/20 px-3 py-2 text-sm text-muted-foreground">
                  <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
                    <div className="flex flex-wrap justify-between gap-2 border-b border-border/60 pb-2 sm:flex-col sm:justify-start sm:border-0 sm:pb-0">
                      <dt className="text-xs uppercase tracking-wide">newly completed experiments count</dt>
                      <dd className="font-mono tabular-nums text-foreground">{completedExperimentCount}</dd>
                    </div>
                    <div className="flex flex-wrap justify-between gap-2 border-b border-border/60 pb-2 sm:flex-col sm:justify-start sm:border-0 sm:pb-0">
                      <dt className="text-xs uppercase tracking-wide">confirmed outcomes count</dt>
                      <dd className="font-mono tabular-nums text-foreground">{confirmedReactionOutcomesCount}</dd>
                    </div>
                    <div className="flex flex-wrap justify-between gap-2 border-b border-border/60 pb-2 sm:flex-col sm:justify-start sm:border-0 sm:pb-0">
                      <dt className="text-xs uppercase tracking-wide">failed/skipped experiments count</dt>
                      <dd className="font-mono tabular-nums text-foreground">{failedSkippedReactionExperimentsCount}</dd>
                    </div>
                    <div className="flex flex-wrap justify-between gap-2 border-b border-border/60 pb-2 sm:flex-col sm:justify-start sm:border-0 sm:pb-0">
                      <dt className="text-xs uppercase tracking-wide">last BO run</dt>
                      <dd className="font-mono text-xs text-foreground">
                        {execTabLatestBoRunRecord != null
                          ? `${readBoRunId(execTabLatestBoRunRecord)} · ${String(execTabLatestBoRunRecord.algorithm ?? "—")} · ${String(execTabLatestBoRunRecord.status ?? "—")}`
                          : "—"}
                      </dd>
                    </div>
                    <div className="flex flex-wrap justify-between gap-2 border-b border-border/60 pb-2 sm:flex-col sm:justify-start sm:border-0 sm:pb-0">
                      <dt className="text-xs uppercase tracking-wide">last advisor run</dt>
                      <dd className="font-mono text-xs text-foreground">
                        {execTabLatestAdvisorRunRecord != null
                          ? `${
                              readNum(
                                execTabLatestAdvisorRunRecord.advisor_run_id ?? execTabLatestAdvisorRunRecord.id,
                              ) ?? "—"
                            } · ${String(execTabLatestAdvisorRunRecord.advisor_mode ?? execTabLatestAdvisorRunRecord.mode ?? "—")} · ${String(execTabLatestAdvisorRunRecord.status ?? "—")}`
                          : "—"}
                      </dd>
                    </div>
                    <div className="flex flex-wrap justify-between gap-2 sm:flex-col sm:justify-start">
                      <dt className="text-xs uppercase tracking-wide">last cycle decision</dt>
                      <dd className="min-w-0 shrink text-xs text-foreground">{execTabLastOptimizationCycleDecisionLabel}</dd>
                    </div>
                  </dl>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={busy != null}
                    onClick={() => void runBayesianOptimization()}
                  >
                    {busy === "bo-optimization" ? "Running…" : "Run next BO cycle"}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={busy != null}
                    onClick={() => void runAdvisor()}
                  >
                    {busy === "advisor-run" ? "Running…" : "Run Advisor critique"}
                  </Button>
                </div>
              </div>
            </ModuleCard>
          ) : null}

          <ModuleCard
            accent="violet"
            eyebrow="Execution · Approved Queue"
            title={
              <span className="inline-flex items-center gap-2">
                Approved recommendations queue
                <InfoTooltip
                  content={APPROVED_RECOMMENDATIONS_CONVERT_TOOLTIP}
                  label="Approved recommendation conversion note"
                />
              </span>
            }
            description="Approved recommendations pending conversion to planned experiments. Conversion requires a rationale and optionally an execution batch assignment. Recording a planned experiment is not confirmation that laboratory work occurred."
          >
            <div className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="conv-rec-rationale">rationale</Label>
                  <Textarea
                    id="conv-rec-rationale"
                    rows={3}
                    className="text-sm"
                    value={convertRecRationale}
                    onChange={(e) => setConvertRecRationale(e.target.value)}
                    placeholder="Required POST body rationale for conversion."
                  />
                  <p className="text-xs text-muted-foreground">
                    Optional reviewer_name uses the Recommendations tab reviewer_name field when set.
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="conv-exec-batch">execution_batch_id</Label>
                  <Select value={convertRecExecutionBatchId || "__none__"} onValueChange={setConvertRecExecutionBatchId}>
                    <SelectTrigger id="conv-exec-batch">
                      <SelectValue placeholder="Optional" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">—</SelectItem>
                      {reactionExecutionBatchRecords.flatMap((b) => {
                        const bid = readNum(b.id)
                        if (bid == null) return []
                        return [
                          <SelectItem key={`neb-${bid}`} value={String(bid)}>
                            {String(bid)}
                          </SelectItem>,
                        ]
                      })}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    Omit (—) to leave execution_batch_id out of the POST body when the backend allows conversion without an
                    execution batch link.
                  </p>
                </div>
              </div>

              <div className="table-scroll">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="font-mono text-xs tabular-nums">recommendation_id</TableHead>
                      <TableHead className="text-xs">rank</TableHead>
                      <TableHead className="text-xs">label</TableHead>
                      <TableHead className="min-w-[140px] text-xs">proposed conditions</TableHead>
                      <TableHead className="text-xs">predicted score</TableHead>
                      <TableHead className="min-w-[100px] text-xs">uncertainty</TableHead>
                      <TableHead className="text-xs">estimated cost</TableHead>
                      <TableHead className="text-xs">safety status</TableHead>
                      <TableHead className="min-w-[120px] text-xs">rationale</TableHead>
                      <TableHead className="text-xs">approval status</TableHead>
                      <TableHead className="font-mono text-xs">planned experiment</TableHead>
                      <TableHead className="text-xs"> </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {approvedRecommendationsQueue.map((r) => {
                      const id = readNum(r.id)
                      if (id == null) return null
                      const planned = executionPlanningByRecId.get(id)
                      const convBusy = busy === `convert-rec-${id}`
                      const conditionsJson = r.conditions_json ?? r.proposed_conditions
                      return (
                        <TableRow key={`exec-approved-${id}`}>
                          <TableCell className="font-mono text-xs tabular-nums">{id}</TableCell>
                          <TableCell className="font-mono text-xs tabular-nums">{String(r.rank ?? "—")}</TableCell>
                          <TableCell className="text-xs">
                            <Badge variant="outline" className="font-normal">
                              {formatRecommendationLabel(r.label)}
                            </Badge>
                          </TableCell>
                          <TableCell className="max-w-[180px] align-top">
                            <pre className="max-h-24 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-2 text-[10px] leading-snug">
                              {jsonPreview(conditionsJson ?? {}, 800)}
                            </pre>
                          </TableCell>
                          <TableCell className="font-mono text-xs tabular-nums">
                            {formatPredictedScoreDisplay(r)}
                          </TableCell>
                          <TableCell className="max-w-[140px] align-top">
                            <pre className="max-h-24 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-2 text-[10px] leading-snug">
                              {jsonPreview(r.uncertainty_json ?? {}, 600)}
                            </pre>
                          </TableCell>
                          <TableCell className="font-mono text-xs tabular-nums">
                            {formatEstimatedCostDisplay(r)}
                          </TableCell>
                          <TableCell className="max-w-[100px] text-xs">{String(r.safety_status ?? "—")}</TableCell>
                          <TableCell className="max-w-[160px] align-top text-xs text-muted-foreground">
                            <span className="line-clamp-4">{String(r.rationale ?? "")}</span>
                          </TableCell>
                          <TableCell className="text-xs">
                            <Badge variant="outline">{String(r.status ?? "")}</Badge>
                          </TableCell>
                          <TableCell className="font-mono text-xs align-top">
                            {planned != null ? (
                              <div className="flex flex-col gap-1">
                                <span className="tabular-nums">{planned.experiment_id}</span>
                                <Badge variant="secondary" className="w-fit text-[10px] font-normal">
                                  {planned.experiment_status}
                                </Badge>
                                {planned.execution_item_id != null ? (
                                  <span className="text-[10px] text-muted-foreground">
                                    execution_item id {planned.execution_item_id}
                                  </span>
                                ) : null}
                              </div>
                            ) : (
                              "—"
                            )}
                          </TableCell>
                          <TableCell className="align-top">
                            <Button
                              type="button"
                              size="sm"
                              className="h-8 whitespace-normal text-xs"
                              disabled={
                                loading || busy != null || !convertRecRationale.trim()
                              }
                              onClick={() => void convertRecommendationToPlannedExperiment(id)}
                            >
                              {convBusy ? "…" : "Convert to planned experiment"}
                            </Button>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                    {!loading && approvedRecommendationsQueue.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={12} className="text-muted-foreground">
                          No approved recommendations yet — review and approve candidates on the Recommendations tab first.
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </div>

              <div className="space-y-2">
                <p className="text-sm font-medium">Execution planning list</p>
                <p className="text-xs text-muted-foreground">
                  Planned experiments created or linked via conversion appear here (experiment status is a database field,
                  not proof of laboratory completion).
                </p>
                <div className="table-scroll">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="font-mono text-xs">recommendation_id</TableHead>
                        <TableHead className="font-mono text-xs">experiment id</TableHead>
                        <TableHead className="font-mono text-xs">execution_item id</TableHead>
                        <TableHead className="text-xs">experiment status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {executionPlanningRows.map((row) => (
                        <TableRow key={`plan-${row.recommendation_id}-${row.experiment_id}`}>
                          <TableCell className="font-mono text-xs tabular-nums">{row.recommendation_id}</TableCell>
                          <TableCell className="font-mono text-xs tabular-nums">{row.experiment_id}</TableCell>
                          <TableCell className="font-mono text-xs tabular-nums">
                            {row.execution_item_id != null ? row.execution_item_id : "—"}
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className="font-normal">
                              {row.experiment_status}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      ))}
                      {!loading && executionPlanningRows.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={4} className="text-muted-foreground">
                            No planned experiments recorded via conversion yet.
                          </TableCell>
                        </TableRow>
                      ) : null}
                    </TableBody>
                  </Table>
                </div>
              </div>
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Execution · Batch Planner"
            title="Execution Batch Planner"
            description="Plan and track lab execution batches — create batches, assign planned experiments as items, and update item status as lab work progresses. Statuses reflect recorded progress only and do not trigger any lab automation."
          >
            <div className="space-y-8">
              <form className="space-y-4" onSubmit={(e) => void createExecutionBatchPlanner(e)}>
                <p className="text-sm font-medium">Create execution batch</p>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="eb-pl-batch-code">batch_code</Label>
                    <Input
                      id="eb-pl-batch-code"
                      value={plEbBatchCode}
                      onChange={(e) => setPlEbBatchCode(e.target.value)}
                      maxLength={120}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="eb-pl-title">title</Label>
                    <Input
                      id="eb-pl-title"
                      value={plEbTitle}
                      onChange={(e) => setPlEbTitle(e.target.value)}
                      maxLength={240}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="eb-pl-planned-start">planned_start</Label>
                    <Input
                      id="eb-pl-planned-start"
                      type="datetime-local"
                      step={60}
                      value={plEbPlannedStart}
                      onChange={(e) => setPlEbPlannedStart(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="eb-pl-planned-end">planned_end</Label>
                    <Input
                      id="eb-pl-planned-end"
                      type="datetime-local"
                      step={60}
                      value={plEbPlannedEnd}
                      onChange={(e) => setPlEbPlannedEnd(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="eb-pl-notes">notes</Label>
                    <Textarea
                      id="eb-pl-notes"
                      rows={2}
                      className="text-sm"
                      value={plEbNotes}
                      onChange={(e) => setPlEbNotes(e.target.value)}
                      placeholder="Optional — stored under metadata_json when present."
                    />
                  </div>
                </div>
                <Button type="submit" disabled={busy != null}>
                  {busy === "exec-batch-create" ? "Creating…" : "Create execution batch"}
                </Button>
              </form>

              <Separator />

              <div className="space-y-2">
                <p className="text-sm font-medium">Execution batches</p>
                <div className="table-scroll">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="font-mono text-xs">batch_id</TableHead>
                        <TableHead className="text-xs">batch code</TableHead>
                        <TableHead className="text-xs">title</TableHead>
                        <TableHead className="text-xs">status</TableHead>
                        <TableHead className="text-right text-xs tabular-nums">item count</TableHead>
                        <TableHead className="whitespace-nowrap text-xs">planned_start</TableHead>
                        <TableHead className="whitespace-nowrap text-xs">planned_end</TableHead>
                        <TableHead className="text-xs"> </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {reactionExecutionBatchRecords.flatMap((row) => {
                        const bid = readNum(row.id)
                        if (bid == null) return []
                        const selected = plannerSelectedBatchId === bid
                        return [
                          <TableRow key={`eb-plan-${bid}`} className={selected ? "bg-muted/40" : undefined}>
                            <TableCell className="font-mono text-xs tabular-nums">{bid}</TableCell>
                            <TableCell className="font-mono text-xs">{String(row.batch_code ?? "")}</TableCell>
                            <TableCell className="max-w-[160px] truncate text-xs">{String(row.title ?? "—")}</TableCell>
                            <TableCell>
                              <Badge variant="outline" className="font-normal">
                                {String(row.status ?? "")}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs tabular-nums">
                              {loading
                                ? "…"
                                : executionBatchItemCounts[bid] !== undefined
                                  ? executionBatchItemCounts[bid]
                                  : "…"}
                            </TableCell>
                            <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                              {fmtIso(row.planned_start)}
                            </TableCell>
                            <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                              {fmtIso(row.planned_end)}
                            </TableCell>
                            <TableCell className="whitespace-nowrap">
                              <Button
                                type="button"
                                variant={selected ? "secondary" : "outline"}
                                size="sm"
                                className="h-8 text-xs"
                                disabled={busy != null}
                                onClick={() => setPlannerSelectedBatchId(bid)}
                              >
                                Open
                              </Button>
                            </TableCell>
                          </TableRow>,
                        ]
                      })}
                      {!loading && reactionExecutionBatchRecords.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={8} className="text-muted-foreground">
                            No execution batches — create one above.
                          </TableCell>
                        </TableRow>
                      ) : null}
                    </TableBody>
                  </Table>
                </div>
                {plannerSelectedBatchId != null ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="secondary" className="font-mono text-xs">
                      selected_batch_id={plannerSelectedBatchId}
                    </Badge>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-8 text-xs"
                      disabled={busy != null}
                      onClick={() => setPlannerSelectedBatchId(null)}
                    >
                      Clear selection
                    </Button>
                  </div>
                ) : null}
              </div>

              {plannerSelectedBatchId != null ? (
                <div className="space-y-4">
                  <Separator />
                  <div className="space-y-2">
                    <p className="text-sm font-medium">Batch detail</p>
                    {plannerPanelLoading ? (
                      <p className="text-xs text-muted-foreground">Loading batch detail…</p>
                    ) : isRecord(plannerBatchDetail) ? (
                      <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                        <span className="font-mono">{String(plannerBatchDetail.batch_code ?? "")}</span>
                        <span>·</span>
                        <span>{String(plannerBatchDetail.title ?? "—")}</span>
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">Batch detail unavailable.</p>
                    )}
                  </div>

                  <Separator />

                  <form className="space-y-4" onSubmit={(e) => void addExecutionPlannerItem(e)}>
                    <p className="text-sm font-medium">Add execution item</p>
                    <div className="grid gap-4 md:grid-cols-2">
                      <div className="space-y-2 md:col-span-2">
                        <Label htmlFor="eb-pl-exp">experiment id (planned experiment)</Label>
                        <Select
                          value={execPlannerExperimentId || "__none__"}
                          onValueChange={setExecPlannerExperimentId}
                        >
                          <SelectTrigger id="eb-pl-exp">
                            <SelectValue placeholder="Choose experiment id" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__none__">—</SelectItem>
                            {plannedExperimentsForPlanner.flatMap((row) => {
                              const id = readNum(row.id)
                              if (id == null) return []
                              const code = typeof row.experiment_code === "string" ? row.experiment_code : ""
                              const label = code ? `${id} (${code})` : String(id)
                              return [
                                <SelectItem key={`eb-exp-${id}`} value={String(id)}>
                                  {label}
                                </SelectItem>,
                              ]
                            })}
                          </SelectContent>
                        </Select>
                        <p className="text-xs text-muted-foreground">
                          Experiments with status planned can be added to this execution batch.
                        </p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="eb-pl-item-code">item_code</Label>
                        <Input
                          id="eb-pl-item-code"
                          value={execPlannerItemCode}
                          onChange={(e) => setExecPlannerItemCode(e.target.value)}
                          maxLength={120}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="eb-pl-operator">operator_name</Label>
                        <Input
                          id="eb-pl-operator"
                          value={execPlannerOperatorName}
                          onChange={(e) => setExecPlannerOperatorName(e.target.value)}
                          maxLength={200}
                          placeholder="Optional POST body."
                        />
                      </div>
                      <div className="space-y-2 md:col-span-2">
                        <Label htmlFor="eb-pl-checklist">checklist_json</Label>
                        <Textarea
                          id="eb-pl-checklist"
                          rows={3}
                          className="font-mono text-xs"
                          value={execPlannerChecklistJsonText}
                          onChange={(e) => setExecPlannerChecklistJsonText(e.target.value)}
                          placeholder='Optional JSON array or object ([{"done":false,"task":"rinse"}]).'
                        />
                      </div>
                    </div>
                    <Button type="submit" disabled={busy != null}>
                      {busy === "exec-item-add" ? "Adding…" : "Add to batch"}
                    </Button>
                  </form>

                  <Separator />

                  <div className="space-y-2">
                    <p className="text-sm font-medium">Batch items</p>
                    <div className="table-scroll">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="text-xs">item code</TableHead>
                            <TableHead className="text-xs">experiment code</TableHead>
                            <TableHead className="text-xs">status</TableHead>
                            <TableHead className="text-xs">operator</TableHead>
                            <TableHead className="whitespace-nowrap text-xs">started_at</TableHead>
                            <TableHead className="whitespace-nowrap text-xs">completed_at</TableHead>
                            <TableHead className="text-xs">conditions summary</TableHead>
                            <TableHead className="text-xs">actions</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {plannerBatchItemRecords.map((item) => {
                            const itemId = readNum(item.id)
                            const eidItem = readNum(item.experiment_id)
                            const code =
                              eidItem != null ? experimentCodeById.get(eidItem) ?? `id ${eidItem}` : "—"
                            return (
                              <TableRow key={itemId ?? String(item.item_code)}>
                                <TableCell className="font-mono text-xs">{String(item.item_code ?? "")}</TableCell>
                                <TableCell className="font-mono text-xs">{code}</TableCell>
                                <TableCell>
                                  <Badge variant="outline" className="font-normal">
                                    {String(item.status ?? "")}
                                  </Badge>
                                </TableCell>
                                <TableCell className="max-w-[120px] truncate text-xs">{String(item.operator_name ?? "—")}</TableCell>
                                <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                                  {fmtIso(item.started_at)}
                                </TableCell>
                                <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                                  {fmtIso(item.completed_at)}
                                </TableCell>
                                <TableCell className="max-w-[200px] truncate text-xs text-muted-foreground">
                                  {summarizeConditions(item.conditions_json)}
                                </TableCell>
                                <TableCell>
                                  <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    className="h-8 text-xs"
                                    disabled={busy != null}
                                    onClick={() => setPlannerItemInspectPayload(item)}
                                  >
                                    Inspect
                                  </Button>
                                </TableCell>
                              </TableRow>
                            )
                          })}
                          {plannerPanelLoading && plannerBatchItemRecords.length === 0 ? (
                            <TableRow>
                              <TableCell colSpan={8} className="text-muted-foreground">
                                Loading items…
                              </TableCell>
                            </TableRow>
                          ) : null}
                          {!plannerPanelLoading && plannerBatchItemRecords.length === 0 ? (
                            <TableRow>
                              <TableCell colSpan={8} className="text-muted-foreground">
                                No items — POST items using the form above when an experiment row is planned.
                              </TableCell>
                            </TableRow>
                          ) : null}
                        </TableBody>
                      </Table>
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Execution · Batches"
            title="Execution batches"
            description="Recommendation batches grouping model-suggested experiments — batch records are informational; lab execution is always human-initiated."
          >
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="font-mono text-xs">batch_id</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">updated_at</TableHead>
                    <TableHead className="text-xs">summary</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {executionRecommendationBatchesRecords.map((b, idx) => {
                    const bid = readNum(b.id)
                    const key =
                      bid != null ? `batch-${bid}` : `batch-idx-${idx}-${String(b.updated_at ?? "x")}`
                    return (
                      <TableRow key={key}>
                        <TableCell className="font-mono text-xs tabular-nums">
                          {bid != null ? bid : "—"}
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                          {fmtIso(b.updated_at)}
                        </TableCell>
                        <TableCell className="max-w-[min(520px,100%)] align-top">
                          <pre className="max-h-28 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-2 text-[10px] leading-snug">
                            {jsonPreview(b, 1200)}
                          </pre>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                  {!loading && executionRecommendationBatchesRecords.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={3} className="text-muted-foreground">
                        No recommendation batch rows loaded — run optimization or reload when batches exist.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Execution · Board"
            title={
              <span className="inline-flex items-center gap-2">
                Experiment Execution Board
                <InfoTooltip content={EXECUTION_BOARD_TOOLTIP} label="Manual execution status" />
              </span>
            }
            description="Lab execution board — manually advance execution item status as reactions are run. Status transitions are user-initiated; no autonomous lab scheduling occurs here."
            className="min-w-0"
          >
            <div className="space-y-4">
              {!loading && executionBoardItemRecords.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No execution items loaded — create batches and items in Execution Batch Planner (or via approved
                  conversion) first.
                </p>
              ) : null}
              <div className="grid min-w-0 grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                {(
                  [
                    ["planned", "planned", executionBoardColumns.planned],
                    ["running", "running", executionBoardColumns.running],
                    ["completed", "completed", executionBoardColumns.completed],
                    ["failed", "failed/skipped", executionBoardColumns.failedSkipped],
                  ] as const
                ).map(([colKey, colTitle, rows]) => (
                  <Card key={colKey} className="min-w-0 border-muted shadow-none">
                    <CardHeader className="pb-2 pt-4">
                      <CardTitle className="text-sm font-medium">{colTitle}</CardTitle>
                      <CardDescription className="text-xs tabular-nums">{rows.length} items</CardDescription>
                    </CardHeader>
                    <CardContent className="max-h-[min(70vh,840px)] space-y-3 overflow-y-auto pt-0">
                      {rows.map((item) => {
                        const itemId = readNum(item.id)
                        const eid = readNum(item.experiment_id)
                        const expCode =
                          eid != null ? experimentCodeById.get(eid) ?? `id ${eid}` : "—"
                        const st = String(item.status ?? "").toLowerCase()
                        const canMarkRun = st === "planned"
                        const canMarkDone = st === "planned" || st === "running"
                        const canMarkFail = st === "planned" || st === "running"
                        const actBusy = busy != null
                        return (
                          <Card key={itemId ?? String(item.item_code)} className="border-border shadow-none">
                            <CardHeader className="space-y-1 p-3 pb-1">
                              <CardTitle className="break-words font-mono text-xs leading-snug">
                                {String(item.item_code ?? "")}
                              </CardTitle>
                              <CardDescription className="font-mono text-[10px]">
                                item_id {itemId != null ? itemId : "—"}
                              </CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-2 p-3 pt-0 text-xs">
                              <div>
                                <span className="text-muted-foreground">experiment code </span>
                                <span className="font-mono">{expCode}</span>
                              </div>
                              <div className="space-y-0.5">
                                <p className="text-muted-foreground">conditions summary</p>
                                <p className="line-clamp-4 break-words text-muted-foreground">
                                  {summarizeConditions(item.conditions_json)}
                                </p>
                              </div>
                              <div>
                                <span className="text-muted-foreground">operator </span>
                                {String(item.operator_name ?? "—")}
                              </div>
                              <div className="flex flex-wrap gap-1">
                                <Badge variant="outline" className="text-[10px] font-normal">
                                  {String(item.status ?? "")}
                                </Badge>
                              </div>
                              <div>
                                <span className="text-muted-foreground">checklist progress </span>
                                <span className="font-mono tabular-nums">
                                  {executionItemChecklistProgressLabel(item)}
                                </span>
                              </div>
                              <Separator />
                              <div className="space-y-1">
                                <p className="text-[10px] font-medium uppercase text-muted-foreground">actions</p>
                                <div className="flex flex-col gap-1">
                                  <Button
                                    type="button"
                                    variant="secondary"
                                    size="sm"
                                    className="h-8 w-full justify-start text-xs"
                                    disabled={actBusy || !canMarkRun}
                                    onClick={() => openExecutionBoardDialog("run", item)}
                                  >
                                    Mark running
                                  </Button>
                                  <Button
                                    type="button"
                                    variant="secondary"
                                    size="sm"
                                    className="h-8 w-full justify-start text-xs"
                                    disabled={actBusy || !canMarkDone}
                                    onClick={() => openExecutionBoardDialog("done", item)}
                                  >
                                    Mark completed
                                  </Button>
                                  <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    className="h-8 w-full justify-start text-xs"
                                    disabled={actBusy || !canMarkFail}
                                    onClick={() => openExecutionBoardDialog("fail", item)}
                                  >
                                    Mark failed
                                  </Button>
                                  <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    className="h-8 w-full justify-start text-xs"
                                    disabled={actBusy}
                                    onClick={() => openExecutionBoardDialog("checklist", item)}
                                  >
                                    Edit checklist
                                  </Button>
                                  <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    className="h-8 w-full justify-start text-xs"
                                    disabled={actBusy}
                                    onClick={() => openExecutionBoardDialog("note", item)}
                                  >
                                    Add note
                                  </Button>
                                </div>
                              </div>
                            </CardContent>
                          </Card>
                        )
                      })}
                      {!loading && rows.length === 0 ? (
                        <p className="text-xs text-muted-foreground">No items in this column.</p>
                      ) : null}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Execution · Status Table"
            title="Experiment execution board"
            description="Experiment status reflects manually recorded lab progress — yield, analytical link, and linked SpectraCheck session for each planned run."
          >
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>experiment_code</TableHead>
                    <TableHead>status</TableHead>
                    <TableHead className="text-right text-xs">yield %</TableHead>
                    <TableHead className="font-mono text-xs">linked_spectracheck_session_id</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">spectracheck</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {experimentsRec.map((e) => {
                    const linked = readNum(e.linked_spectracheck_session_id)
                    const yld = readOutcomeNumber(e, "yield_percent")
                    return (
                      <TableRow key={String(e.id)}>
                        <TableCell className="font-mono text-xs">{String(e.experiment_code ?? "")}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className="font-normal">
                            {String(e.status ?? "")}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right font-mono text-xs tabular-nums">
                          {yld != null ? `${yld}` : "—"}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {linked != null ? linked : "—"}
                        </TableCell>
                        <TableCell className="whitespace-nowrap">
                          {linked != null ? (
                            <Button variant="outline" size="sm" className="h-8 gap-1 px-2 text-xs" asChild>
                              <Link
                                href={`/spectracheck?sessionId=${encodeURIComponent(String(linked))}`}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                Open
                                <ExternalLink className="h-3 w-3" aria-hidden />
                              </Link>
                            </Button>
                          ) : (
                            "—"
                          )}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                  {!loading && experimentsRec.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-muted-foreground">
                        No experiments — use the Experiments tab to POST
                        /reaction-projects/{"{reaction_project_id}"}/experiments.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Execution · Analytical Intake"
            title={
              <span className="inline-flex items-center gap-2">
                Analytical results intake
                <InfoTooltip content={ANALYTICAL_RESULTS_INTAKE_TOOLTIP} label="Analytical results context" />
              </span>
            }
            description="Link concise analytical metadata and summary values to execution items. Full spectral evidence and QC records remain in SpectraCheck."
          >
            <div className="space-y-6">
              <form className="space-y-4" onSubmit={(e) => void addAnalyticalResultToExecutionItem(e)}>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="ar-item">execution_item_id</Label>
                    <Select value={arExecutionItemId || "__none__"} onValueChange={setArExecutionItemId}>
                      <SelectTrigger id="ar-item">
                        <SelectValue placeholder="Select execution item" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">—</SelectItem>
                        {executionItemSelectorRows.flatMap((row) => {
                          if (row.itemId == null) return []
                          const label = `${row.itemId} (${row.itemCode || "item"}) · ${row.experimentCode}`
                          return [
                            <SelectItem key={`ar-item-${row.itemId}`} value={String(row.itemId)}>
                              {label}
                            </SelectItem>,
                          ]
                        })}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="ar-type">result_type</Label>
                    <Select value={arResultType} onValueChange={setArResultType}>
                      <SelectTrigger id="ar-type">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {ANALYTICAL_RESULT_TYPE_OPTIONS.map((opt) => (
                          <SelectItem key={opt} value={opt}>
                            {opt}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="ar-sc">spectracheck_session_id</Label>
                    <Input
                      id="ar-sc"
                      inputMode="numeric"
                      value={arSpectraCheckSessionId}
                      onChange={(e) => setArSpectraCheckSessionId(e.target.value)}
                      placeholder="Optional"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="ar-file">file_id</Label>
                    <Input
                      id="ar-file"
                      inputMode="numeric"
                      value={arFileId}
                      onChange={(e) => setArFileId(e.target.value)}
                      placeholder="Optional"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="ar-artifact">artifact_id</Label>
                    <Input
                      id="ar-artifact"
                      inputMode="numeric"
                      value={arArtifactId}
                      onChange={(e) => setArArtifactId(e.target.value)}
                      placeholder="Optional"
                    />
                  </div>

                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="ar-hash">source_hash</Label>
                    <Input
                      id="ar-hash"
                      value={arSourceHash}
                      onChange={(e) => setArSourceHash(e.target.value)}
                      maxLength={128}
                      placeholder="Optional"
                    />
                  </div>

                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="ar-summary">summary_json</Label>
                    <Textarea
                      id="ar-summary"
                      rows={5}
                      className="font-mono text-xs"
                      value={arSummaryText}
                      onChange={(e) => setArSummaryText(e.target.value)}
                      placeholder='Advanced field. JSON preferred; plain text is stored as {"summary_text": "..."}'
                    />
                  </div>
                </div>
                <Button type="submit" disabled={busy != null}>
                  {busy === "exec-analytical-add" ? "Adding…" : "Add analytical result"}
                </Button>
              </form>

              <Separator />

              <div className="table-scroll">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>result type</TableHead>
                      <TableHead className="font-mono text-xs">linked SpectraCheck session</TableHead>
                      <TableHead className="font-mono text-xs">artifact/file ID</TableHead>
                      <TableHead className="whitespace-nowrap text-xs">QC status</TableHead>
                      <TableHead className="font-mono text-xs">source hash</TableHead>
                      <TableHead className="whitespace-nowrap text-xs">created</TableHead>
                      <TableHead className="text-xs">summary preview</TableHead>
                      <TableHead className="whitespace-nowrap text-xs">open</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(selectedAnalyticalExecutionItemId != null
                      ? (analyticalResultsByExecutionItemId[selectedAnalyticalExecutionItemId] ?? [])
                      : []
                    )
                      .filter(isRecord)
                      .map((row, idx) => {
                        const sid = readNum(row.spectracheck_session_id)
                        const fid = readNum(row.file_id)
                        const aid = readNum(row.artifact_id)
                        const af = [aid != null ? `artifact:${aid}` : null, fid != null ? `file:${fid}` : null]
                          .filter((x): x is string => x != null)
                          .join(" · ")
                        const key = readNum(row.id) ?? idx
                        return (
                          <TableRow key={`ar-row-${key}`}>
                            <TableCell className="text-xs">{String(row.result_type ?? "")}</TableCell>
                            <TableCell className="font-mono text-xs">{sid != null ? sid : "—"}</TableCell>
                            <TableCell className="font-mono text-xs">{af || "—"}</TableCell>
                            <TableCell className="max-w-[120px] truncate text-xs">
                              {String(row.qc_status ?? "—")}
                            </TableCell>
                            <TableCell className="max-w-[180px] truncate font-mono text-xs">
                              {String(row.source_hash ?? "—")}
                            </TableCell>
                            <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                              {fmtIso(row.created_at)}
                            </TableCell>
                            <TableCell className="max-w-[min(380px,100%)] align-top">
                              <pre className="max-h-24 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-2 text-[10px] leading-snug">
                                {jsonPreview(isRecord(row.summary_json) ? row.summary_json : {}, 900)}
                              </pre>
                            </TableCell>
                            <TableCell className="whitespace-nowrap">
                              {sid != null ? (
                                <Button variant="outline" size="sm" className="h-8 gap-1 px-2 text-xs" asChild>
                                  <Link
                                    href={`/spectracheck?sessionId=${encodeURIComponent(String(sid))}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                  >
                                    Open
                                    <ExternalLink className="h-3 w-3" aria-hidden />
                                  </Link>
                                </Button>
                              ) : (
                                "—"
                              )}
                            </TableCell>
                          </TableRow>
                        )
                      })}

                    {selectedAnalyticalExecutionItemId == null ? (
                      <TableRow>
                        <TableCell colSpan={8} className="text-muted-foreground">
                          Select an execution item to view linked analytical results.
                        </TableCell>
                      </TableRow>
                    ) : analyticalResultsLoadingItemId === selectedAnalyticalExecutionItemId ? (
                      <TableRow>
                        <TableCell colSpan={8} className="text-muted-foreground">
                          Loading analytical results…
                        </TableCell>
                      </TableRow>
                    ) : (
                      (analyticalResultsByExecutionItemId[selectedAnalyticalExecutionItemId] ?? []).length === 0 && (
                        <TableRow>
                          <TableCell colSpan={8} className="text-muted-foreground">
                            No analytical results linked for this execution item.
                          </TableCell>
                        </TableRow>
                      )
                    )}
                  </TableBody>
                </Table>
              </div>
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Execution · Outcome Extraction"
            title="Outcome extraction"
            description="Yield, conversion, and related fields are recorded on POST/PATCH experiments as outcome_json (see Experiments tab). The UI does not autonomously import numerical outcomes from spectral files."
          >
            <div className="space-y-4">
              <p className="text-xs text-muted-foreground">
                Extract yield, conversion, and related outcome values from linked analytical data. Proposed outcomes require explicit confirmation before updating the experiment record.
              </p>

              <div className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="oe-exec-item">execution_item_id</Label>
                    <Select value={oeExecutionItemId || "__none__"} onValueChange={setOeExecutionItemId}>
                      <SelectTrigger id="oe-exec-item">
                        <SelectValue placeholder="Select execution item" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">—</SelectItem>
                        {executionItemSelectorRows.flatMap((row) => {
                          if (row.itemId == null) return []
                          const label = `${row.itemId} (${row.itemCode || "item"}) · ${row.experimentCode}`
                          return [
                            <SelectItem key={`oe-item-${row.itemId}`} value={String(row.itemId)}>
                              {label}
                            </SelectItem>,
                          ]
                        })}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="oe-method">extraction_method</Label>
                    <Select value={oeExtractionMethod} onValueChange={setOeExtractionMethod}>
                      <SelectTrigger id="oe-method">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {OUTCOME_EXTRACTION_METHOD_OPTIONS.map((opt) => (
                          <SelectItem key={opt} value={opt}>
                            {opt}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="oe-ar-id">analytical_result_id</Label>
                    <Select
                      value={oeAnalyticalResultIdChoice}
                      onValueChange={setOeAnalyticalResultIdChoice}
                      disabled={selectedOutcomeExecutionItemId == null}
                    >
                      <SelectTrigger id="oe-ar-id">
                        <SelectValue placeholder={selectedOutcomeExecutionItemId == null ? "Select execution item first" : "Optional scope"} />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__all__">Use all analytical results linked to item</SelectItem>
                        {(selectedOutcomeExecutionItemId != null
                          ? (analyticalResultsByExecutionItemId[selectedOutcomeExecutionItemId] ?? [])
                          : []
                        )
                          .filter(isRecord)
                          .flatMap((ar) => {
                            const rid = readNum(ar.id)
                            if (rid == null) return []
                            const rt = String(ar.result_type ?? "")
                            return [
                              <SelectItem key={`oe-ar-${rid}`} value={String(rid)}>
                                #{rid}{rt ? ` (${rt})` : ""}
                              </SelectItem>,
                            ]
                          })}
                      </SelectContent>
                    </Select>
                    {selectedOutcomeExecutionItemId != null &&
                      analyticalResultsLoadingItemId === selectedOutcomeExecutionItemId ? (
                      <p className="text-xs text-muted-foreground">Loading analytical results…</p>
                    ) : null}
                  </div>
                </div>

                <Button
                  type="button"
                  variant="outline"
                  disabled={busy != null || selectedOutcomeExecutionItemId == null}
                  onClick={() => void extractProposedOutcome()}
                >
                  {busy === "exec-outcome-extract" ? "Extracting…" : "Extract proposed outcome"}
                </Button>

                {oeExtractionRun != null ? (
                  <div className="space-y-4 rounded-md border border-border bg-muted/10 px-3 py-3 md:px-4 md:py-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium">Proposed outcome</span>
                      {typeof oeExtractionRun.status === "string" ? (
                        <Badge variant="outline" className="font-normal capitalize">
                          {oeExtractionRun.status === "requires_review"
                            ? "requires confirmation"
                            : oeExtractionRun.status.replace(/_/g, " ")}
                        </Badge>
                      ) : null}
                      {typeof oeExtractionRun.extraction_method === "string" && oeExtractionRun.extraction_method ? (
                        <Badge variant="secondary" className="font-normal font-mono text-xs">
                          {oeExtractionRun.extraction_method}
                        </Badge>
                      ) : null}
                    </div>

                    <div className="space-y-1">
                      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        extracted raw (proposed_outcome_json)
                      </p>
                      <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-2 text-[10px] leading-snug">
                        {jsonPreview(
                          isRecord(oeExtractionRun.proposed_outcome_json)
                            ? oeExtractionRun.proposed_outcome_json
                            : {},
                          2400,
                        )}
                      </pre>
                    </div>

                    <div className="space-y-2 text-xs">
                      <p>
                        <span className="font-medium text-foreground">confidence_label</span>{" "}
                        <span className="font-mono text-muted-foreground">
                          {typeof oeExtractionRun.confidence_label === "string"
                            ? oeExtractionRun.confidence_label
                            : "—"}
                        </span>
                      </p>
                      {mergeOutcomeExtractionWarnings(oeExtractionRun).length > 0 ? (
                        <div className="space-y-1">
                          <p className="font-medium text-foreground">warnings</p>
                          <ul className="list-inside list-disc text-muted-foreground">
                            {mergeOutcomeExtractionWarnings(oeExtractionRun).map((w) => (
                              <li key={w}>{w}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                      {mergeOutcomeExtractionNotes(oeExtractionRun).length > 0 ? (
                        <div className="space-y-1">
                          <p className="font-medium text-foreground">notes</p>
                          <ul className="list-inside list-disc text-muted-foreground">
                            {mergeOutcomeExtractionNotes(oeExtractionRun).map((n) => (
                              <li key={n}>{n}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                    </div>

                    <Separator />

                    <Alert>
                      <AlertTitle className="text-sm">Official experiment outcome</AlertTitle>
                      <AlertDescription className="text-xs">
                        Confirming updates the official reaction experiment outcome. The proposed outcome is not official
                        until you confirm with the form below.
                      </AlertDescription>
                    </Alert>

                    <form className="space-y-4" onSubmit={(e) => void confirmRecordedOutcome(e)}>
                      <p className="text-base font-medium">Confirmed outcome</p>
                      <p className="text-sm text-muted-foreground">
                        Edit the confirmed outcome fields you want to persist. Percent fields you leave blank are omitted
                        from confirmed_outcome_json; the server merges only the keys you send with the existing
                        outcome_json row. Omitting confirmed_outcome_json entirely still applies the proposed outcome when an
                        extraction_run_id is supplied.
                      </p>

                      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                        <div className="space-y-2">
                          <Label htmlFor="oe-yield">yield_percent</Label>
                          <Input
                            id="oe-yield"
                            inputMode="decimal"
                            className="font-mono text-xs"
                            value={oeConfirmedYieldPercent}
                            onChange={(e) => setOeConfirmedYieldPercent(e.target.value)}
                            placeholder="0–100"
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="oe-conv">conversion_percent</Label>
                          <Input
                            id="oe-conv"
                            inputMode="decimal"
                            className="font-mono text-xs"
                            value={oeConfirmedConversionPercent}
                            onChange={(e) => setOeConfirmedConversionPercent(e.target.value)}
                            placeholder="0–100"
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="oe-sel">selectivity_percent</Label>
                          <Input
                            id="oe-sel"
                            inputMode="decimal"
                            className="font-mono text-xs"
                            value={oeConfirmedSelectivityPercent}
                            onChange={(e) => setOeConfirmedSelectivityPercent(e.target.value)}
                            placeholder="0–100"
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="oe-imp">impurity_percent</Label>
                          <Input
                            id="oe-imp"
                            inputMode="decimal"
                            className="font-mono text-xs"
                            value={oeConfirmedImpurityPercent}
                            onChange={(e) => setOeConfirmedImpurityPercent(e.target.value)}
                            placeholder="0–100"
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="oe-iso">isolated_yield_percent</Label>
                          <Input
                            id="oe-iso"
                            inputMode="decimal"
                            className="font-mono text-xs"
                            value={oeConfirmedIsolatedYieldPercent}
                            onChange={(e) => setOeConfirmedIsolatedYieldPercent(e.target.value)}
                            placeholder="0–100"
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="oe-lcms">lcms_area_percent</Label>
                          <Input
                            id="oe-lcms"
                            inputMode="decimal"
                            className="font-mono text-xs"
                            value={oeConfirmedLcmsAreaPercent}
                            onChange={(e) => setOeConfirmedLcmsAreaPercent(e.target.value)}
                            placeholder="0–100"
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="oe-nmr">nmr_purity_percent</Label>
                          <Input
                            id="oe-nmr"
                            inputMode="decimal"
                            className="font-mono text-xs"
                            value={oeConfirmedNmrPurityPercent}
                            onChange={(e) => setOeConfirmedNmrPurityPercent(e.target.value)}
                            placeholder="0–100"
                          />
                        </div>
                        <div className="space-y-2 sm:col-span-2 lg:col-span-3">
                          <Label htmlFor="oe-notes">notes</Label>
                          <Textarea
                            id="oe-notes"
                            rows={3}
                            className="text-sm"
                            value={oeConfirmedNotes}
                            onChange={(e) => setOeConfirmedNotes(e.target.value)}
                            placeholder="Optional free text stored on confirmed_outcome_json.notes"
                          />
                        </div>
                      </div>

                      <div className="grid gap-4 md:grid-cols-2">
                        <div className="space-y-2">
                          <Label htmlFor="oe-reviewer">reviewer_name</Label>
                          <Input
                            id="oe-reviewer"
                            value={oeReviewerName}
                            onChange={(e) => setOeReviewerName(e.target.value)}
                            placeholder="Operator or reviewer (optional if rationale identifies the actor)"
                          />
                        </div>
                        <div className="space-y-2 md:col-span-2">
                          <Label htmlFor="oe-rationale">rationale</Label>
                          <Textarea
                            id="oe-rationale"
                            rows={3}
                            className="text-sm"
                            required
                            value={oeConfirmRationale}
                            onChange={(e) => setOeConfirmRationale(e.target.value)}
                            placeholder="Required confirmation comment (reviewer rationale)."
                          />
                        </div>
                      </div>

                      <Button type="submit" disabled={busy != null}>
                        {busy === "exec-outcome-confirm" ? "Confirming…" : "Confirm outcome"}
                      </Button>
                    </form>
                  </div>
                ) : null}
              </div>

              <Separator />

              <div className="rounded-md border border-border bg-muted/20 px-3 py-2 text-sm text-muted-foreground">
                Completed experiments with numeric outcome metrics:{" "}
                <span className="font-mono tabular-nums text-foreground">
                  {experimentsRec.filter((e) => outcomeJsonHasNumericMetrics(
                    isRecord(e.outcome_json) ? e.outcome_json : {},
                  )).length}
                </span>
                {" · "}
                Linked SpectraCheck sessions:{" "}
                <span className="font-mono tabular-nums text-foreground">{linkedSessionCount}</span>
              </div>
              <div className="table-scroll">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>experiment_code</TableHead>
                      <TableHead>status</TableHead>
                      <TableHead className="text-right text-xs">yield %</TableHead>
                      <TableHead className="text-right text-xs">conversion %</TableHead>
                      <TableHead className="text-xs">outcome_json preview</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {experimentsRec.map((e) => {
                      const oj = isRecord(e.outcome_json) ? e.outcome_json : {}
                      const yld = readOutcomeNumber(e, "yield_percent")
                      const conv = readOutcomeNumber(e, "conversion_percent")
                      return (
                        <TableRow key={`exec-out-${String(e.id)}`}>
                          <TableCell className="font-mono text-xs">{String(e.experiment_code ?? "")}</TableCell>
                          <TableCell>
                            <Badge variant="outline" className="font-normal">
                              {String(e.status ?? "")}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right font-mono text-xs tabular-nums">
                            {yld != null ? `${yld}` : "—"}
                          </TableCell>
                          <TableCell className="text-right font-mono text-xs tabular-nums">
                            {conv != null ? `${conv}` : "—"}
                          </TableCell>
                          <TableCell className="max-w-[min(380px,100%)] align-top">
                            <pre className="max-h-24 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-2 text-[10px] leading-snug">
                              {jsonPreview(oj, 800)}
                            </pre>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                    {!loading && experimentsRec.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5} className="text-muted-foreground">
                          No experiments to summarize.
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </div>
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Execution · Cycle Timeline"
            title={
              <span className="inline-flex items-center gap-2">
                Optimization cycle timeline
                <InfoTooltip content={OPTIMIZATION_CYCLE_TIMELINE_TOOLTIP} label="About optimization cycles" />
              </span>
            }
            description="Timeline of recent Bayesian optimization, heuristic, and advisor runs across all cycles — ordering is informational, not an autonomous loop."
          >
            <div className="space-y-4">
              <p className="text-xs text-muted-foreground">
                Create and track optimization cycles that link execution batches with their corresponding optimization runs and advisor decisions. Run ordering below is informational.
              </p>

              <form className="space-y-4" onSubmit={(e) => void createOptimizationCycleRecord(e)}>
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  <div className="space-y-2 lg:col-span-2">
                    <Label htmlFor="opt-cc-eb">execution_batch_id</Label>
                    <Select value={optCcExecutionBatchId || "__none__"} onValueChange={setOptCcExecutionBatchId}>
                      <SelectTrigger id="opt-cc-eb">
                        <SelectValue placeholder="Optional linkage" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">No explicit execution_batch_id</SelectItem>
                        {reactionExecutionBatchRecords.flatMap((brow) => {
                          const bid = readNum(brow.id)
                          if (bid == null) return []
                          const code =
                            typeof brow.batch_code === "string" && brow.batch_code.trim()
                              ? brow.batch_code.trim()
                              : `batch_${bid}`
                          return [
                            <SelectItem key={`opt-cc-eb-${bid}`} value={String(bid)}>
                              {`${bid} · ${code}`}
                            </SelectItem>,
                          ]
                        })}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="opt-cc-st">status</Label>
                    <Select value={optCcStatus} onValueChange={setOptCcStatus}>
                      <SelectTrigger id="opt-cc-st">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {REACTION_OPTIMIZATION_CYCLE_STATUS_OPTIONS.map((st) => (
                          <SelectItem key={st} value={st}>
                            {st}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="opt-cc-num">cycle_number</Label>
                    <Input
                      id="opt-cc-num"
                      inputMode="numeric"
                      className="font-mono text-xs"
                      value={optCcCycleNumber}
                      onChange={(e) => setOptCcCycleNumber(e.target.value)}
                      placeholder="Optional server default"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="opt-cc-bo">bo_run_id</Label>
                    <Input
                      id="opt-cc-bo"
                      inputMode="numeric"
                      className="font-mono text-xs"
                      value={optCcBoRunId}
                      onChange={(e) => setOptCcBoRunId(e.target.value)}
                      placeholder="Optional linkage"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="opt-cc-ad">advisor_run_id</Label>
                    <Input
                      id="opt-cc-ad"
                      inputMode="numeric"
                      className="font-mono text-xs"
                      value={optCcAdvisorRunId}
                      onChange={(e) => setOptCcAdvisorRunId(e.target.value)}
                      placeholder="Optional linkage"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="opt-cc-rb">recommendation_batch_id</Label>
                    <Input
                      id="opt-cc-rb"
                      inputMode="numeric"
                      className="font-mono text-xs"
                      value={optCcRecBatchId}
                      onChange={(e) => setOptCcRecBatchId(e.target.value)}
                      placeholder="Optional linkage"
                    />
                  </div>
                </div>
                <Button type="submit" variant="outline" disabled={busy != null}>
                  {busy === "opt-cc-create" ? "Creating…" : "Create optimization cycle"}
                </Button>
              </form>

              <Separator />

              <div className="table-scroll">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-px" aria-hidden />
                      <TableHead className="text-right text-xs">cycle_number</TableHead>
                      <TableHead>status</TableHead>
                      <TableHead className="text-right text-xs tabular-nums">input experiments</TableHead>
                      <TableHead className="text-right text-xs tabular-nums">new experiments</TableHead>
                      <TableHead className="font-mono text-xs">bo_run_id</TableHead>
                      <TableHead className="font-mono text-xs">advisor_run_id</TableHead>
                      <TableHead className="font-mono text-xs">recommendation_batch_id</TableHead>
                      <TableHead className="font-mono text-xs">execution_batch_id</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {optimizationCyclesList
                      .filter(isRecord)
                      .flatMap((craw) => {
                        const cid = readNum(craw.id)
                        if (cid == null) return []

                        const open = occExpandedId === cid
                        const merged = optimizationCycleDetailById[cid] ?? craw
                        const inN = readNum(merged.input_experiment_count)
                        const nwN = readNum(merged.new_experiment_count)
                        const warningsList = mergeDuplicateApiListPair(merged, "warnings_json", "warnings")
                        const notesList = mergeDuplicateApiListPair(merged, "notes_json", "notes")
                        const dec = optimizationCycleDecisionRecordFromCycle(merged)

                        const summaryBlob = jsonPreview(isRecord(merged.summary_json) ? merged.summary_json : {}, 4200)

                        const rowCols = (
                          <>
                            <TableCell className="w-px p-2">
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                className="h-8 w-8 p-0"
                                aria-expanded={open}
                                aria-label={open ? "Collapse cycle detail" : "Expand cycle detail"}
                                onClick={() => {
                                  setOccExpandedId((prev) => {
                                    if (prev === cid) return null
                                    void loadOptimizationCycleDetail(cid)
                                    return cid
                                  })
                                }}
                              >
                                <ChevronDown
                                  className={`h-4 w-4 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
                                  aria-hidden
                                />
                              </Button>
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs tabular-nums">
                              {merged.cycle_number != null ? String(merged.cycle_number) : "—"}
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline" className="font-normal capitalize">
                                {String(merged.status ?? "").replace(/_/g, " ") || "—"}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs tabular-nums">
                              {inN != null ? inN : "—"}
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs tabular-nums">
                              {nwN != null ? nwN : "—"}
                            </TableCell>
                            <TableCell className="font-mono text-xs">{readNum(merged.bo_run_id) ?? "—"}</TableCell>
                            <TableCell className="font-mono text-xs">
                              {readNum(merged.advisor_run_id) ?? "—"}
                            </TableCell>
                            <TableCell className="font-mono text-xs">
                              {readNum(merged.recommendation_batch_id) ?? "—"}
                            </TableCell>
                            <TableCell className="font-mono text-xs">
                              {readNum(merged.execution_batch_id) ?? "—"}
                            </TableCell>
                          </>
                        )

                        const pieces = [<TableRow key={`occ-row-${cid}`}>{rowCols}</TableRow>]

                        if (open) {
                          pieces.push(
                            <TableRow key={`occ-detail-${cid}`} className="bg-muted/5 align-top [&>td]:border-t-0">
                              <TableCell colSpan={9} className="p-4">
                                <div className="space-y-4 text-sm">
                                  {optimizationCycleDetailLoadingId === cid ? (
                                    <p className="text-xs text-muted-foreground">
                                      Loading cycle detail…
                                    </p>
                                  ) : null}
                                  <div className="space-y-2">
                                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                                      summary_json
                                    </p>
                                    <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-3 text-[10px] leading-snug">
                                      {summaryBlob}
                                    </pre>
                                  </div>
                                  {warningsList.length > 0 ? (
                                    <div className="space-y-1">
                                      <p className="text-xs font-medium text-muted-foreground">warnings</p>
                                      <ul className="list-inside list-disc text-xs text-muted-foreground">
                                        {warningsList.map((w) => (
                                          <li key={`${cid}-w-${w}`}>{w}</li>
                                        ))}
                                      </ul>
                                    </div>
                                  ) : (
                                    <p className="text-xs text-muted-foreground">warnings — none listed.</p>
                                  )}
                                  {notesList.length > 0 ? (
                                    <div className="space-y-1">
                                      <p className="text-xs font-medium text-muted-foreground">notes</p>
                                      <ul className="list-inside list-disc text-xs text-muted-foreground">
                                        {notesList.map((n) => (
                                          <li key={`${cid}-n-${n}`}>{n}</li>
                                        ))}
                                      </ul>
                                    </div>
                                  ) : (
                                    <p className="text-xs text-muted-foreground">notes — none listed.</p>
                                  )}
                                  <div className="space-y-2">
                                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                                      decision record
                                    </p>
                                    {dec != null ? (
                                      <div className="space-y-1 rounded-md border border-border px-3 py-2 text-xs">
                                        <p>
                                          <span className="text-muted-foreground">decision</span>{" "}
                                          <span className="font-mono capitalize">
                                            {String(dec.decision ?? "").replace(/_/g, " ")}
                                          </span>
                                        </p>
                                        <p className="whitespace-pre-wrap text-muted-foreground">
                                          rationale:{" "}
                                          <span className="text-foreground">{String(dec.rationale ?? "")}</span>
                                        </p>
                                        {dec.reviewer_name != null ? (
                                          <p className="text-muted-foreground">
                                            reviewer_name:{" "}
                                            <span className="font-mono text-foreground">{String(dec.reviewer_name)}</span>
                                          </p>
                                        ) : null}
                                        {typeof dec.created_at === "string" ? (
                                          <p className="text-muted-foreground">created_at {fmtIso(dec.created_at)}</p>
                                        ) : null}
                                      </div>
                                    ) : (
                                      <p className="text-xs text-muted-foreground">
                                        decision record — not present on metadata_json.latest_decision yet.
                                      </p>
                                    )}
                                  </div>
                                  <Separator />
                                  <form className="space-y-4" onSubmit={(e) => void submitOptimizationCycleDecision(cid, e)}>
                                    <p className="text-xs font-medium text-muted-foreground">Record decision</p>
                                    <div className="grid gap-4 md:grid-cols-2">
                                      <div className="space-y-2 md:col-span-2">
                                        <Label htmlFor={`opt-dec-${cid}`}>decision</Label>
                                        <Select value={occDecision} onValueChange={setOccDecision}>
                                          <SelectTrigger id={`opt-dec-${cid}`}>
                                            <SelectValue />
                                          </SelectTrigger>
                                          <SelectContent>
                                            {REACTION_OPTIMIZATION_CYCLE_DECISION_OPTIONS.map((d) => (
                                              <SelectItem key={`${cid}-${d}`} value={d}>
                                                {d}
                                              </SelectItem>
                                            ))}
                                          </SelectContent>
                                        </Select>
                                      </div>
                                      <div className="space-y-2 md:col-span-2">
                                        <Label htmlFor={`opt-rat-${cid}`}>rationale</Label>
                                        <Textarea
                                          id={`opt-rat-${cid}`}
                                          className="text-sm"
                                          required
                                          value={occRationale}
                                          onChange={(e) => setOccRationale(e.target.value)}
                                          placeholder="Human rationale (required)."
                                        />
                                      </div>
                                      <div className="space-y-2 md:col-span-2">
                                        <Label htmlFor={`opt-rev-${cid}`}>reviewer_name</Label>
                                        <Input
                                          id={`opt-rev-${cid}`}
                                          value={occReviewer}
                                          onChange={(e) => setOccReviewer(e.target.value)}
                                          placeholder="Optional when rationale identifies reviewer context"
                                        />
                                      </div>
                                    </div>
                                    <Button type="submit" variant="outline" size="sm" disabled={busy != null}>
                                      {busy === `opt-cc-dec-${cid}` ? "Recording…" : "Submit decision"}
                                    </Button>
                                  </form>
                                </div>
                              </TableCell>
                            </TableRow>,
                          )
                        }

                        return pieces
                      })}
                    {!loading && optimizationCyclesList.filter(isRecord).length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={9} className="text-muted-foreground">
                          No optimization cycles recorded yet — create one using the form above.
                        </TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </div>

              <Separator />

              <div className="space-y-2">
                {!loading && executionCycleTimeline.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No optimization or advisor run rows loaded yet.</p>
                ) : (
                  <ul className="space-y-2 text-sm">
                    {executionCycleTimeline.map((row, i) => (
                      <li
                        key={`cycle-${i}-${row.detail.slice(0, 32)}`}
                        className="flex flex-wrap items-baseline justify-between gap-2 rounded-md border border-border bg-muted/10 px-3 py-2"
                      >
                        <span className="text-muted-foreground">{row.detail}</span>
                        <span className="whitespace-nowrap text-xs text-muted-foreground">{row.whenLabel}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Execution · Developer JSON"
            title="Developer JSON"
            description="Aggregated execution-oriented snapshot for debugging (same API fields as elsewhere)."
          >
            <Collapsible className="rounded-md border border-border">
              <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm font-medium hover:bg-muted/50">
                Developer JSON
                <ChevronDown className="h-4 w-4 shrink-0 opacity-70" />
              </CollapsibleTrigger>
              <CollapsibleContent className="border-t border-border px-3 py-3">
                <DeveloperJsonPanel data={executionDevPayload} />
              </CollapsibleContent>
            </Collapsible>
          </ModuleCard>
        </TabsContent>

        <TabsContent value="evidence" className="mt-4 space-y-6">
          <div className="space-y-1">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-violet)" }}
            >
              Project · Evidence Links
            </p>
            <h2 className="font-mono text-xl font-bold tracking-tight">SpectraCheck-linked analytical evidence</h2>
            <p className="text-sm text-muted-foreground">
              Compound &amp; batch linking to SpectraCheck sessions for outcome-extraction provenance — the SpectraCheck ↔ Reaction integration seam.
            </p>
          </div>
          <ReactionStudioCompoundLinkingPanel
            loading={loading}
            project={project}
            experiments={experimentsRec}
            onRefresh={reload}
          />
          <ModuleCard
            accent="violet"
            eyebrow="Reaction · Evidence Links"
            title="Evidence Links"
            description="Analytical evidence summary for all experiments linked to a SpectraCheck session — metadata, record counts, and QC status. Use Open for full spectral evidence."
          >
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>experiment_id</TableHead>
                    <TableHead>experiment_code</TableHead>
                    <TableHead className="font-mono text-xs">linked_spectracheck_session_id</TableHead>
                    <TableHead className="text-xs">sample_id</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">unified status</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">report status</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">QC status</TableHead>
                    <TableHead className="text-right">evidence_records</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">open</TableHead>
                    <TableHead className="hidden lg:table-cell">conditions preview</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {experimentsRec
                    .filter((e) => readNum(e.linked_spectracheck_session_id) != null)
                    .map((e) => {
                      const eid = readNum(e.id)
                      const linked = readNum(e.linked_spectracheck_session_id)
                      if (eid == null) return null
                      const ev = experimentEvidenceById[eid]
                      const summ = ev ? reactionEvidenceSummary(ev) : null
                      return (
                        <TableRow key={eid}>
                          <TableCell className="font-mono text-xs">{eid}</TableCell>
                          <TableCell className="font-mono text-xs">{String(e.experiment_code ?? "")}</TableCell>
                          <TableCell className="font-mono text-xs">{linked != null ? linked : "—"}</TableCell>
                          <TableCell className="max-w-[100px] truncate text-xs">
                            {summ?.sampleId ?? (loading ? "…" : "—")}
                          </TableCell>
                          <TableCell className="max-w-[120px] truncate text-xs">
                            {summ?.unifiedEvidenceStatus ?? "—"}
                          </TableCell>
                          <TableCell className="max-w-[120px] truncate text-xs">
                            {summ?.reportStatus ?? "—"}
                          </TableCell>
                          <TableCell className="max-w-[120px] truncate text-xs">{summ?.qcStatus ?? "—"}</TableCell>
                          <TableCell className="text-right tabular-nums">
                            {summ != null ? summ.evidenceRecordCount : evidenceCounts[eid] ?? "…"}
                          </TableCell>
                          <TableCell className="whitespace-nowrap">
                            {linked != null ? (
                              <Button variant="outline" size="sm" className="h-8 gap-1 px-2 text-xs" asChild>
                                <Link
                                  href={`/spectracheck?sessionId=${encodeURIComponent(String(linked))}`}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                >
                                  Open
                                  <ExternalLink className="h-3 w-3" aria-hidden />
                                </Link>
                              </Button>
                            ) : (
                              "—"
                            )}
                          </TableCell>
                          <TableCell className="hidden max-w-[220px] truncate text-xs text-muted-foreground lg:table-cell">
                            {summarizeConditions(e.conditions_json)}
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  {!loading &&
                  experimentsRec.filter((e) => readNum(e.linked_spectracheck_session_id) != null).length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={10} className="text-muted-foreground">
                        No experiments with linked_spectracheck_session_id.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </div>
          </ModuleCard>
        </TabsContent>

        <TabsContent value="developer" className="mt-4 space-y-6">
          <div className="space-y-1">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-violet)" }}
            >
              Project · Developer JSON
            </p>
            <h2 className="font-mono text-xl font-bold tracking-tight">Raw payloads for debugging</h2>
            <p className="text-sm text-muted-foreground">
              Aggregated reaction-project payloads in this browser session — use to inspect backend response shape, audit fields, and warnings.
            </p>
          </div>
          <ModuleCard
            accent="violet"
            eyebrow="Reaction · Developer JSON"
            title="Developer JSON"
            description="Aggregated payloads from this reaction project workspace (debugging only)."
          >
            <DeveloperJsonPanel data={devPayload} />
          </ModuleCard>
        </TabsContent>
      </Tabs>

      <Dialog
        open={linkDialogExperimentId != null}
        onOpenChange={(open) => {
          if (!open) setLinkDialogExperimentId(null)
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Link SpectraCheck Session</DialogTitle>
            <DialogDescription>
              Link a SpectraCheck analysis session to this experiment to enable evidence tracking and cross-module analytical review.
              {linkDialogExperimentId != null ? (
                <span className="mt-1 block font-mono text-xs">
                  experiment_id={linkDialogExperimentId}
                </span>
              ) : null}
            </DialogDescription>
          </DialogHeader>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              void submitLinkSpectraCheckSession(e)
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="link-sc-session-id">session_id</Label>
              <Input
                id="link-sc-session-id"
                inputMode="numeric"
                value={linkSessionInput}
                onChange={(e) => setLinkSessionInput(e.target.value)}
                placeholder="SpectraCheck session id"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="link-sc-note">
                note <span className="font-normal text-muted-foreground">(optional)</span>
              </Label>
              <Textarea
                id="link-sc-note"
                rows={3}
                value={linkNoteInput}
                onChange={(e) => setLinkNoteInput(e.target.value)}
                placeholder="Stored in metadata_json when provided."
              />
            </div>
            <DialogFooter className="gap-2 sm:gap-0">
              <Button type="button" variant="outline" onClick={() => setLinkDialogExperimentId(null)}>
                Cancel
              </Button>
              <Button type="submit" disabled={busy != null && busy.startsWith("link-")}>
                {busy?.startsWith("link-") ? "Linking…" : "Link session"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={plannerItemInspectPayload != null}
        onOpenChange={(open) => {
          if (!open) setPlannerItemInspectPayload(null)
        }}
      >
        <DialogContent className="max-h-[85vh] max-w-xl overflow-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Execution item (inspect)</DialogTitle>
            <DialogDescription className="text-xs">
              Execution item detail — for review only.
            </DialogDescription>
          </DialogHeader>
          <DeveloperJsonPanel data={plannerItemInspectPayload} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setPlannerItemInspectPayload(null)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={boardDialog != null}
        onOpenChange={(open) => {
          if (!open) closeExecutionBoardDialog()
        }}
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          {boardDialog != null ? (
            <>
              <DialogHeader>
                <DialogTitle className="text-base">
                  {boardDialog.kind === "run"
                    ? "Mark running"
                    : boardDialog.kind === "done"
                      ? "Mark completed"
                      : boardDialog.kind === "fail"
                        ? "Mark failed"
                        : boardDialog.kind === "checklist"
                          ? "Edit checklist_json"
                          : "Add note"}
                </DialogTitle>
                <DialogDescription className="text-xs">
                  {boardDialog.kind === "run"
                    ? "Mark this execution item as running — record operator name and start timestamp."
                    : boardDialog.kind === "done"
                      ? "Mark this execution item as completed — record completion notes and confirm outcome."
                      : boardDialog.kind === "fail"
                        ? "Mark this execution item as failed — record failure reason for deviation tracking."
                        : boardDialog.kind === "checklist"
                          ? "Update the execution checklist for this item."
                          : "Add a note to this execution item."}
                </DialogDescription>
              </DialogHeader>
              <form className="space-y-4" onSubmit={(e) => void submitExecutionBoardDialog(e)}>
                {(boardDialog.kind === "run" || boardDialog.kind === "done") && (
                  <>
                    <div className="space-y-2">
                      <Label htmlFor="ebd-operator">operator_name</Label>
                      <Input
                        id="ebd-operator"
                        autoComplete="name"
                        value={boardDialogOperator}
                        onChange={(e) => setBoardDialogOperator(e.target.value)}
                        placeholder="Optional"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="ebd-message">message</Label>
                      <Textarea
                        id="ebd-message"
                        rows={3}
                        className="text-sm"
                        value={boardDialogMessage}
                        onChange={(e) => setBoardDialogMessage(e.target.value)}
                        placeholder={
                          boardDialog.kind === "done"
                            ? "Optional completion note (POST message field)."
                            : "Optional (POST message field)."
                        }
                      />
                    </div>
                  </>
                )}
                {boardDialog.kind === "fail" && (
                  <>
                    <div className="space-y-2">
                      <Label htmlFor="ebd-failure">failure_reason</Label>
                      <Textarea
                        id="ebd-failure"
                        required
                        rows={4}
                        className="text-sm"
                        value={boardDialogFailureReason}
                        onChange={(e) => setBoardDialogFailureReason(e.target.value)}
                        placeholder="Required for mark-failed."
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="ebd-fail-operator">operator_name</Label>
                      <Input
                        id="ebd-fail-operator"
                        autoComplete="name"
                        value={boardDialogOperator}
                        onChange={(e) => setBoardDialogOperator(e.target.value)}
                        placeholder="Optional"
                      />
                    </div>
                  </>
                )}
                {boardDialog.kind === "checklist" && (
                  <div className="space-y-2">
                    <Label htmlFor="ebd-checklist">checklist_json</Label>
                    <Textarea
                      id="ebd-checklist"
                      rows={10}
                      className="font-mono text-xs"
                      value={boardDialogChecklistJson}
                      onChange={(e) => setBoardDialogChecklistJson(e.target.value)}
                    />
                  </div>
                )}
                {boardDialog.kind === "note" && (
                  <div className="space-y-2">
                    <Label htmlFor="ebd-note">note</Label>
                    <Textarea
                      id="ebd-note"
                      rows={4}
                      className="text-sm"
                      value={boardDialogNote}
                      onChange={(e) => setBoardDialogNote(e.target.value)}
                      placeholder="Appended via PATCH metadata_json (execution_board_notes array)."
                    />
                  </div>
                )}
                <DialogFooter className="gap-2 sm:gap-0">
                  <Button type="button" variant="outline" onClick={() => closeExecutionBoardDialog()}>
                    Cancel
                  </Button>
                  <Button type="submit" disabled={busy != null}>
                    {busy != null
                      ? "…"
                      : boardDialog.kind === "checklist" || boardDialog.kind === "note"
                        ? "Save"
                        : "Submit"}
                  </Button>
                </DialogFooter>
              </form>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  )
}
