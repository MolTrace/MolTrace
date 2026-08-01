"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import { ArrowLeft, ChevronDown, ExternalLink, FlaskConical, Lightbulb } from "lucide-react"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { DeveloperOnly, useDeveloperMode } from "@/components/developer-mode-provider"
import { MlModelProvenanceSummary } from "@/components/ml/ml-model-provenance-summary"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { apiFetch, ApiError } from "@/lib/api/client"
import { formatStableUtcDateTime } from "@/lib/utils"
import { statusLabel } from "@/lib/ui/status"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { StatusBadge } from "@/components/ui/status-badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty"

/** Shared style for inline, baseline-aligned link-buttons rendered inside prose
 *  (e.g. the safety-gate deep-link). `inline min-h-0 align-baseline` neutralizes
 *  the global button min-height; the focus-visible ring matches house style. */
const INLINE_LINK_BUTTON_CLASS =
  "inline min-h-0 align-baseline font-medium text-foreground underline underline-offset-2 hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:rounded-sm"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { KeyNumberTableField } from "@/components/ui/key-number-table-field"
import { StringListField } from "@/components/ui/string-list-field"
import { PairListField } from "@/components/ui/pair-list-field"
import { KeyChoiceTableField } from "@/components/ui/key-choice-table-field"
import { JsonObjectField } from "@/components/ui/json-object-field"
import { ObjectArrayField } from "@/components/ui/object-array-field"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsContent } from "@/components/ui/tabs"
import { StructureEditorPanel } from "@/src/components/chemistry/StructureEditorPanel"
import {
  WorkspaceStageNav,
  type WorkspaceStageGroup,
} from "@/components/app/workspace-stage-nav"
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
import { GreenMetricsPanel } from "@/components/reaction-optimization/green-metrics-panel"
import { ParetoFrontPanel } from "@/components/reaction-optimization/pareto-front-panel"
import { PlateDesignPanel } from "@/components/reaction-optimization/plate-design-panel"
import { SafetyScreeningPanel } from "@/components/reaction-optimization/safety-screening-panel"
import { MlCapabilitiesPanel } from "@/components/reaction-optimization/ml-capabilities-panel"
import { YieldPredictionPanel } from "@/components/reaction-optimization/yield-prediction-panel"
import { RouteScoresPanel } from "@/components/reaction-optimization/route-scores-panel"
import { ForwardCheckPanel } from "@/components/reaction-optimization/forward-check-panel"
import {
  hypervolumeTrend,
  nonDominatedExperimentIds,
  objectivesKey,
  paretoFrontFromRun,
} from "@/lib/reaction/pareto"
import { ReactionResponseOverview } from "@/components/reaction-optimization/reaction-response-overview"
import { ReactionRegulatoryConstraintsPanel } from "@/components/reaction-optimization/reaction-regulatory-constraints-panel"
import { ReactionRegulatoryCompliancePanel } from "@/components/reaction-optimization/reaction-regulatory-compliance-panel"
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
import { RAW_DATA_DISCLOSURE } from "@/lib/ui/copy"

const VARIABLES_TOOLTIP =
  "Reaction variables define the condition space for experiment planning and recommendation."

const OBJECTIVE_PROFILE_TOOLTIP =
  "What the optimizer should improve — one metric (yield, selectivity, purity) or a weighted composite, together with the per-target weights and thresholds the optimization engine applies."

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
  "minimize_e_factor",
  "maximize_atom_economy",
  "maximize_green_score",
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
  "The chemical reasoning behind optimization decisions; revise as new experiments are added."

const LITERATURE_PRIOR_SOURCE_TYPES = [
  "user_note",
  "literature_reference",
  "internal_history",
  "model_prior",
  "rule_based_prior",
] as const

const LITERATURE_PRIORS_TOOLTIP =
  "Literature, internal history, or your own mechanistic context that can inform optimization."

const BO_ADVISOR_COMPARISON_TOOLTIP =
  "Where mathematical optimization and chemical reasoning agree or disagree: each candidate is lined up against the advisor's concern signals so agreement and disagreement are visible per candidate."

const ADVISOR_REVIEW_DECISIONS = [
  "accept_for_review",
  "request_modification",
  "reject_advisor_output",
  "defer",
] as const

const BENCHMARK_TOOLTIP =
  "How an optimizer would perform on completed or enumerated reaction data. It is used for validation, not proof of universal superiority."

const ADVISOR_TAB_TOOLTIP =
  "The Advisor critiques optimization recommendations using mechanistic, cost, safety, and practical reasoning. It does not autonomously schedule experiments."

const EXECUTION_TAB_TOOLTIP =
  "Connects approved recommendations to planned experiments, analytical results, outcomes, and the next cycle. Human confirmation is required."

// ── Two-tier Reaction Studio section navigation ──────────────────────────
// Fourteen sections, grouped into the way a campaign is actually run: orient,
// define the problem, lay out experiments, optimise, execute and record. The
// stage is the primary tab and its sections are the secondary tabs — see
// components/app/workspace-stage-nav.tsx for why the tiers are split.
//
// The per-section blurb below replaces the hover tooltips that used to hang off
// the Advisor and Execution tabs alone: a caption states the same thing for
// every section, without an info target to hit on the way past.
const REACTION_STUDIO_NAV: WorkspaceStageGroup[] = [
  {
    id: "overview",
    label: "Overview",
    sections: [
      {
        value: "overview",
        label: "Overview",
        desc: "Project details, campaign aggregates, and recent activity — the source of truth for the rest of the workspace.",
      },
    ],
  },
  {
    id: "design",
    label: "Design",
    sections: [
      {
        value: "variables",
        label: "Variables",
        desc: "The factors this campaign can change, and the range each one is allowed to take.",
      },
      {
        value: "objective",
        label: "Objective",
        desc: "What the campaign is optimising for, and the constraints a candidate has to satisfy.",
      },
      {
        value: "cost-safety",
        label: "Cost & Safety",
        desc: "Cost per experiment and the structural safety screen — decision support that gates on your review, not on its own.",
      },
      {
        value: "green",
        label: "Green",
        desc: "Green-chemistry metrics for the campaign, and how candidate conditions compare on them.",
      },
    ],
  },
  {
    id: "experiments",
    label: "Experiments",
    sections: [
      {
        value: "experiments",
        label: "Experiments",
        desc: "The experiment matrix for this project — conditions run, outcomes recorded, and what each one contributed.",
      },
      {
        value: "plates",
        label: "Plates",
        desc: "High-throughput plate layouts generated from the campaign variables, ready to export.",
      },
      {
        value: "routes",
        label: "Routes",
        desc: "Candidate synthetic routes scored against this project's objective and constraints.",
      },
    ],
  },
  {
    id: "optimization",
    label: "Optimization",
    sections: [
      {
        value: "optimization",
        label: "Optimization",
        desc: "Optimisation runs, their diagnostics, and the trade-off front they produced.",
      },
      {
        value: "advisor",
        label: "Advisor",
        desc: ADVISOR_TAB_TOOLTIP,
      },
      {
        value: "recommendations",
        label: "Recommendations",
        desc: "Proposed next conditions, each with the reasoning and the evidence behind it. Nothing is scheduled without your approval.",
      },
    ],
  },
  {
    id: "execution",
    label: "Execution",
    sections: [
      {
        value: "execution",
        label: "Execution",
        desc: EXECUTION_TAB_TOOLTIP,
      },
      {
        value: "evidence",
        label: "Evidence Links",
        desc: "Analytical evidence attached to this project, and what each item supports.",
      },
    ],
  },
  {
    id: "developer",
    label: "Developer JSON",
    sections: [
      {
        value: "developer",
        label: "Developer JSON",
        desc: "Raw results for troubleshooting, validation, and data-shape inspection.",
      },
    ],
  },
]

// Mechanism only — the matching caveat ("Recording a planned experiment is not
// confirmation that laboratory work occurred") is visible in the card description.
const APPROVED_RECOMMENDATIONS_CONVERT_TOOLTIP =
  "Converting an approved recommendation writes a planned experiment. The conversion asks for a rationale and lets you assign the new experiment to an execution batch."

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
  "How each batch of experiments updates the model and informs the next round."

/*
 * Mechanism tooltips.
 *
 * These carry the *how* — surrogate details, acquisition functions, decision
 * thresholds, data scoping — out of the card descriptions so a scanning reader
 * is not taxed by them. Caveats deliberately did NOT move here: "advisory",
 * "decision-support only", "deploys nothing", "requires human review" and the
 * like stay in the visible description, because a hedge behind a hover is a
 * weaker hedge.
 */

const WARM_START_TOOLTIP =
  "Fits a prior from the accumulated outcomes of the campaigns you select and uses it to seed the model for a new campaign. The default source is this campaign alone; adding related campaigns you own makes it transfer learning."

const AB_PROMOTION_TOOLTIP =
  "Held-out metrics and safety-flag recall are compared side by side. The verdict reads promotable only when the challenger shows no safety regression and dominates the champion on the metrics you enter."

const EXECUTION_BATCH_PLANNER_TOOLTIP =
  "Create a batch, assign planned experiments to it as items, and move each item through its status as lab work progresses. Item status is recorded progress you enter by hand."

const CYCLE_READY_TOOLTIP =
  "Bayesian optimization and advisor runs read the objective, cost, and safety profiles saved on this project, so confirmed outcomes are picked up the next time you start a run."

const ADVISOR_HUMAN_REVIEW_TOOLTIP =
  "Approve, flag for revision, or reject a specific advisor run. The decision, the reviewer, and the comment are recorded against that run."

const OUTCOME_EXTRACTION_TOOLTIP =
  "Yield, conversion, and related outcome fields live on the experiment record — the Experiments tab is where they are read back."

const LATEST_BO_BATCH_TOOLTIP =
  "Each candidate carries the model's predicted score, its uncertainty, and the expected improvement the acquisition function used to rank it."

const EVIDENCE_SUMMARY_TOOLTIP =
  "One row per experiment with a linked SpectraCheck session: confidence status, QC outcome, and how many evidence records the session holds. Open SpectraCheck for the full spectral evidence."

const EVIDENCE_LINKS_TOOLTIP =
  "One row per experiment linked to a SpectraCheck session, with the session metadata, record counts, and QC status. Use Open for the full spectral evidence."

const EXPERIMENT_MATRIX_TOOLTIP =
  "One row per unique condition set, with its outcome metrics and the SpectraCheck session linked to it for analytical evidence."

const ADD_VARIABLE_TOOLTIP =
  "A variable's type, unit, and allowed-value constraints apply to every experiment in this project, so the design space and every recommendation stay inside them."

const RECOMMENDATIONS_LIST_TOOLTIP =
  "Candidates are ranked by the improvement the model predicts. Approving or rejecting one records your reviewer name and comment against it."

const LATEST_BO_RUN_TOOLTIP =
  "Reports the acquisition function and surrogate model used, how many experiments went in, and any diagnostics or warnings the run emitted."

const ADVISOR_RUN_TOOLTIP =
  "The advisor reads the current Bayesian optimization suggestions alongside your mechanistic hypotheses and literature priors, then flags which next experiments it would prioritise."

const EXECUTION_STATUS_TABLE_TOOLTIP =
  "One row per planned run, showing its recorded yield, its analytical link, and the SpectraCheck session attached to it."

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

/** Readable text for the stored option vocabularies above. The stored value is never
 *  rewritten — this map only supplies what a scientist reads in a picker, badge, or
 *  table cell. Domain terms (Bayesian/GP/EI/UCB, LC-MS, qNMR, E-factor) stay intact;
 *  anything unlisted falls back to sentence-cased words. */
const REACTION_OPTION_LABELS: Record<string, string> = {
  // Objectives
  maximize_yield: "Maximize yield",
  maximize_selectivity: "Maximize selectivity",
  minimize_impurity: "Minimize impurity",
  maximize_conversion: "Maximize conversion",
  minimize_e_factor: "Minimize E-factor",
  maximize_atom_economy: "Maximize atom economy",
  maximize_green_score: "Maximize green score",
  multi_objective: "Multi-objective",
  custom: "Custom",
  // Bayesian-optimization algorithms
  gaussian_process_ei: "Gaussian process · expected improvement (EI)",
  gaussian_process_ucb: "Gaussian process · upper confidence bound (UCB)",
  random_forest_ei: "Random forest · expected improvement (EI)",
  tpe_like: "Tree-structured Parzen estimator (TPE-like)",
  rule_based_fallback: "Rule-based fallback (no model)",
  // Advisor modes
  rule_based_mechanistic: "Rule-based mechanistic",
  llm_guided_placeholder: "Language-model guided (placeholder)",
  hybrid_bo_llm: "Hybrid — Bayesian optimization + language model",
  // Literature-prior sources
  user_note: "Chemist note",
  literature_reference: "Literature reference",
  internal_history: "Internal history",
  model_prior: "Model prior",
  rule_based_prior: "Rule-based prior",
  // Advisor review decisions
  accept_for_review: "Accept for review",
  request_modification: "Request modification",
  reject_advisor_output: "Reject advisor output",
  defer: "Defer",
  // Analytical result types
  nmr: "NMR",
  lcms: "LC-MS",
  hrms: "HRMS",
  msms: "MS/MS",
  hplc: "HPLC",
  uplc: "UPLC",
  qnmr: "qNMR",
  other: "Other",
  // Outcome extraction methods
  rule_based: "Rule-based",
  lcms_area: "LC-MS area %",
  nmr_purity: "NMR purity",
  unified_spectracheck: "Unified SpectraCheck confidence",
  manual: "Manual entry",
  // Optimization-cycle statuses
  draft: "Draft",
  running: "Running",
  completed: "Completed",
  requires_review: "Requires review",
  failed: "Failed",
  // Optimization-cycle decisions
  continue_optimization: "Continue optimization",
  pause: "Pause",
  stop_success: "Stop — target met",
  stop_insufficient_progress: "Stop — insufficient progress",
  revise_design_space: "Revise design space",
  revise_objective: "Revise objective",
}

/** Display text for a stored option/status token. Never pass the result back to the server. */
function optionLabel(value: string | null | undefined): string {
  const raw = (value ?? "").trim()
  if (!raw) return "—"
  return REACTION_OPTION_LABELS[raw] ?? statusLabel(raw)
}

/** Yes / No / — for a flag, so a reader never sees a raw true/false/undefined. */
function flagLabel(value: unknown): string {
  if (value === true) return "Yes"
  if (value === false) return "No"
  return "—"
}

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

export function optimizationCycleDecisionRecordFromCycle(cycle: Record<string, unknown>): Record<string, unknown> | null {
  const md = cycle.metadata_json
  if (!isRecord(md)) return null
  const ld = md.latest_decision
  return isRecord(ld) ? ld : null
}

/** R5 — true only when the cycle's latest decision unlocks proposing the next batch. */
export function cycleCanProposeNext(cycle: Record<string, unknown>): boolean {
  const dec = optimizationCycleDecisionRecordFromCycle(cycle)
  return dec != null && dec.decision === "continue_optimization"
}

/** R5 — loop metrics on a cycle (metadata_json.cycle_metrics.metrics): the "how fast / how far". */
export function cycleLoopMetricsFromCycle(cycle: Record<string, unknown>): Record<string, unknown> | null {
  const md = cycle.metadata_json
  if (!isRecord(md)) return null
  const cm = md.cycle_metrics
  if (!isRecord(cm)) return null
  return isRecord(cm.metrics) ? cm.metrics : null
}

/** R5 — half-closed-loop info present on a PROPOSED draft cycle (metadata_json.propose_next + note). */
export function cycleProposeNextInfoFromCycle(
  cycle: Record<string, unknown>,
): { flags: Record<string, unknown>; note: string | null; proposedFrom: number | null } | null {
  const md = cycle.metadata_json
  if (!isRecord(md)) return null
  const pn = md.propose_next
  if (!isRecord(pn)) return null
  return {
    flags: pn,
    note: typeof md.note === "string" ? md.note : null,
    proposedFrom: readNum(md.proposed_from_cycle_id),
  }
}

/** R5 — DMTA loop sequence + per-phase latencies + provenance from a cycle's
 *  cycle_metrics (drives the optional DMTA stepper). */
export function cycleDmtaInfoFromCycle(cycle: Record<string, unknown>): {
  sequence: string[]
  phaseLatencies: Record<string, unknown>
  provenance: Record<string, unknown> | null
  engine: string | null
} | null {
  const md = cycle.metadata_json
  if (!isRecord(md)) return null
  const cm = md.cycle_metrics
  if (!isRecord(cm)) return null
  const sequence = Array.isArray(cm.dmta_sequence)
    ? cm.dmta_sequence.filter((s): s is string => typeof s === "string")
    : []
  const metrics = isRecord(cm.metrics) ? cm.metrics : {}
  return {
    sequence,
    phaseLatencies: isRecord(metrics.phase_latencies_seconds) ? metrics.phase_latencies_seconds : {},
    provenance: isRecord(cm.provenance) ? cm.provenance : null,
    engine: typeof cm.engine === "string" ? cm.engine : null,
  }
}

/** R5 — user-facing message for a failed propose-next. The 409 "why you can't
 *  propose" reason rides in `detail`, but formatApiError only unpacks 401/403/404
 *  — so the 409 detail is surfaced directly; everything else (incl. the
 *  non-owner 404 and any 5xx) falls through formatApiError. */
export function proposeNextErrorMessage(err: unknown, fallback: string): string {
  if (
    err instanceof ApiError &&
    err.status === 409 &&
    isRecord(err.data) &&
    typeof err.data.detail === "string"
  ) {
    return err.data.detail
  }
  return formatApiError(err, fallback)
}

/** R5 — build the optional BO-param body for propose-next. Every field is
 *  defaulted server-side, so an untouched/invalid value is simply omitted and
 *  `{}` stays valid (handoff §4 item 1: "POST {} (or pass BO params …)"). */
export function proposeNextRequestBody(opts: {
  algorithm?: string | null
  batchSize?: string | number | null
  safetyAware?: boolean | null
}): Record<string, unknown> {
  const body: Record<string, unknown> = {}
  if (typeof opts.algorithm === "string" && opts.algorithm.trim()) {
    body.algorithm = opts.algorithm.trim()
  }
  // batch_size is an integer experiment-count server-side; floor both the
  // numeric and string paths so e.g. 2.9 → 2 (matches runBayesianOptimization).
  const raw =
    typeof opts.batchSize === "number"
      ? opts.batchSize
      : Number.parseInt(String(opts.batchSize ?? "").trim(), 10)
  const n = Math.floor(raw)
  if (Number.isFinite(n) && n >= 1) body.batch_size = n
  if (typeof opts.safetyAware === "boolean") body.safety_aware = opts.safetyAware
  return body
}

/** R8 — the math-frozen Claude advisor-agent block that rides in an advisor run's
 *  untyped `metadata_json.agent`. Absent unless the MOLTRACE_REACTION_AGENT flag +
 *  an LLM advisor_mode are in play, so read defensively. The model plans/narrates/
 *  re-ranks but NEVER computes a number — every quantitative value lives in
 *  `tool_calls[].output` (the grounded source of truth); narrative/plan are prose. */
export function advisorAgentFromRun(run: unknown): {
  engine: string | null
  mode: string | null
  llmUsed: boolean
  modelVersion: string | null
  narrative: string | null
  plan: string[]
  toolCalls: Record<string, unknown>[]
  safetyStatus: string | null
  safetyPrecheck: Record<string, unknown> | null
  executionBlocked: boolean
  warnings: string[]
  stopReason: string | null
  disclaimer: string | null
  humanReviewRequired: boolean
  isFallback: boolean
} | null {
  if (!isRecord(run)) return null
  const md = run.metadata_json
  if (!isRecord(md)) return null
  const a = md.agent
  if (!isRecord(a)) return null
  const mode = typeof a.mode === "string" ? a.mode : null
  const modelVersion = typeof a.model_version === "string" ? a.model_version : null
  const precheck = isRecord(a.safety_precheck) ? a.safety_precheck : null
  return {
    engine: typeof a.engine === "string" ? a.engine : null,
    mode,
    llmUsed: a.llm_used === true,
    modelVersion,
    narrative: typeof a.narrative === "string" ? a.narrative : null,
    plan: Array.isArray(a.plan) ? a.plan.filter((s): s is string => typeof s === "string") : [],
    toolCalls: Array.isArray(a.tool_calls) ? a.tool_calls.filter(isRecord) : [],
    safetyStatus: precheck && typeof precheck.status === "string" ? precheck.status : null,
    safetyPrecheck: precheck,
    executionBlocked: a.execution_blocked === true,
    warnings: Array.isArray(a.warnings) ? a.warnings.filter((s): s is string => typeof s === "string") : [],
    stopReason: typeof a.stop_reason === "string" ? a.stop_reason : null,
    disclaimer: typeof a.disclaimer === "string" ? a.disclaimer : null,
    // Always-review: defaults true even if the field is absent (the agent schedules nothing).
    humanReviewRequired: a.human_review_required !== false,
    // Degraded path: deterministic / no-LLM when explicitly fallback or no model version.
    isFallback: mode === "rule_based_fallback" || modelVersion == null,
  }
}

// ── R9: chemist feedback → preference re-ranker → A/B promotion gate ──────────

/** R9 — feedback decisions. */
export const REACTION_FEEDBACK_DECISIONS = ["accept", "edit", "reject"] as const
/** R9 — reject reason taxonomy (a reason is required on a reject; backend 422s otherwise). */
export const REACTION_FEEDBACK_REASONS = [
  "unsafe",
  "infeasible_on_our_kit",
  "reagent_unavailable",
  "cost",
  "lower_confidence_than_stated",
  "wrong_precedent",
  "other",
] as const

/** R9 — a reject needs a reason; accept/edit do not. */
export function reactionFeedbackReasonRequired(decision: string): boolean {
  return decision === "reject"
}

/** R9 — best-effort model_version that produced a proposal (optional on the feedback request):
 *  the recommendation's own field, else a run-level hint, else null (omitted). */
export function reactionProposalModelVersion(rec: unknown, hint: string | null): string | null {
  if (isRecord(rec)) {
    if (typeof rec.model_version === "string" && rec.model_version) return rec.model_version
    const md = rec.metadata_json
    if (isRecord(md) && typeof md.model_version === "string" && md.model_version) return md.model_version
  }
  return hint && hint.trim() ? hint.trim() : null
}

/** R9 — typed view over a ReactionFeedbackRecord (POST/GET …/feedback response). The three
 *  routing flags are the point: an unsafe rejection is a high-signal safety event that hardens R6
 *  and is excluded from preference learning. */
export function reactionFeedbackRecordView(rec: unknown): {
  id: number | null
  proposalRef: string | null
  decision: string | null
  reason: string | null
  isSafetySignal: boolean
  routesToSafetyHardening: boolean
  isPreferenceLearnable: boolean
  modelVersion: string | null
  createdAt: string | null
  disclaimer: string | null
} | null {
  if (!isRecord(rec)) return null
  return {
    id: readNum(rec.id),
    proposalRef: typeof rec.proposal_ref === "string" ? rec.proposal_ref : null,
    decision: typeof rec.decision === "string" ? rec.decision : null,
    reason: typeof rec.reason === "string" ? rec.reason : null,
    isSafetySignal: rec.is_safety_signal === true,
    routesToSafetyHardening: rec.routes_to_safety_hardening === true,
    isPreferenceLearnable: rec.is_preference_learnable === true,
    modelVersion: typeof rec.model_version === "string" ? rec.model_version : null,
    createdAt: typeof rec.created_at === "string" ? rec.created_at : null,
    disclaimer: typeof rec.disclaimer === "string" ? rec.disclaimer : null,
  }
}

/** R9 — typed view over a ReactionPreferenceRanking (advisory re-rank; never the optimiser's call). */
export function reactionPreferenceRankingView(resp: unknown): {
  advisory: boolean
  boRunId: number | null
  disclaimer: string | null
  ranked: {
    proposalRef: string
    acceptanceScore: number | null
    originalRank: number | null
    conditionsJson: Record<string, unknown>
  }[]
} | null {
  if (!isRecord(resp)) return null
  const rawRanked = Array.isArray(resp.ranked) ? resp.ranked : []
  return {
    advisory: resp.advisory !== false,
    boRunId: readNum(resp.bo_run_id),
    disclaimer: typeof resp.disclaimer === "string" ? resp.disclaimer : null,
    ranked: rawRanked.filter(isRecord).map((it) => ({
      proposalRef: typeof it.proposal_ref === "string" ? it.proposal_ref : String(it.proposal_ref ?? ""),
      acceptanceScore: readNum(it.acceptance_score),
      originalRank: readNum(it.original_rank),
      conditionsJson: isRecord(it.conditions_json) ? it.conditions_json : {},
    })),
  }
}

/** R9 — index a preference ranking by proposal_ref so the "likely-accept" re-rank can merge onto
 *  the recommendation cards (keeps the optimiser's original_rank visible). `rerank` is 1-based. */
export function reactionPreferenceRankByRef(
  ranking: ReturnType<typeof reactionPreferenceRankingView>,
): Map<string, { acceptanceScore: number | null; originalRank: number | null; rerank: number }> {
  const m = new Map<string, { acceptanceScore: number | null; originalRank: number | null; rerank: number }>()
  if (!ranking) return m
  ranking.ranked.forEach((it, i) => {
    m.set(it.proposalRef, { acceptanceScore: it.acceptanceScore, originalRank: it.originalRank, rerank: i + 1 })
  })
  return m
}

/** R9 — a stable content key for a proposal's conditions. The preference-ranking `proposal_ref` is an
 *  acquisition-candidate id, a DIFFERENT id space from the recommendation-row id the cards render, so
 *  keying the re-rank merge by id is unreliable across projects. Both carry the same conditions_json,
 *  so we join on content instead (keys sorted; numbers normalized so 20 === 20.0). */
export function canonicalConditionsKey(conditions: unknown): string {
  if (!isRecord(conditions)) return ""
  const entries = Object.keys(conditions)
    .sort()
    .map((k) => {
      const v = conditions[k]
      const norm =
        typeof v === "number" || typeof v === "string" || typeof v === "boolean" ? v : JSON.stringify(v)
      return [k, norm]
    })
  return JSON.stringify(entries)
}

/** R9 — index the preference ranking by canonical conditions key (robust to the proposal_ref vs
 *  recommendation-id id-space mismatch). First entry wins on a conditions collision. */
export function reactionPreferenceRankByConditions(
  ranking: ReturnType<typeof reactionPreferenceRankingView>,
): Map<string, { acceptanceScore: number | null; originalRank: number | null; rerank: number }> {
  const m = new Map<string, { acceptanceScore: number | null; originalRank: number | null; rerank: number }>()
  if (!ranking) return m
  ranking.ranked.forEach((it, i) => {
    const key = canonicalConditionsKey(it.conditionsJson)
    if (key && !m.has(key)) {
      m.set(key, { acceptanceScore: it.acceptanceScore, originalRank: it.originalRank, rerank: i + 1 })
    }
  })
  return m
}

/** R9 — validate a safety_flag_recall input: a finite number in [0, 1], else null (blocked, never
 *  silently coerced to 0 — recall is the hard, blocking safety dimension of the A/B gate). */
export function parseReactionRecall(v: string | number): number | null {
  if (typeof v !== "number") {
    const s = String(v ?? "").trim()
    if (s === "") return null // blank must NOT coerce to 0 (Number("") === 0)
    const n = Number(s)
    return Number.isFinite(n) && n >= 0 && n <= 1 ? n : null
  }
  return Number.isFinite(v) && v >= 0 && v <= 1 ? v : null
}

// ── R10: warm-start transfer-learning priors ─────────────────────────────────

/** R10 — typed view over a ReactionWarmStartPriorRecord (POST/GET …/warm-start/prior). The lineage
 *  fields let a reviewer see exactly what the prior was fit from: owned + verified data only, never
 *  the frozen evaluation gold set. */
export function reactionWarmStartPriorView(rec: unknown): {
  id: number | null
  snapshotHash: string | null
  objectiveTarget: number | null
  globalMean: number | null
  trainedN: number | null
  excludedGoldCount: number | null
  excludedUnverifiedCount: number | null
  sourceProjectIds: number[]
  augmentationCount: number | null
  lineage: Record<string, unknown> | null
  /** false ⇒ a PREVIEW fit (require_verified was off — unverified data admitted). The verbatim
   *  disclaimer's "verified-only" sentence is NOT true for such a record; render it as a preview. */
  verifiedOnly: boolean
  createdAt: string | null
  disclaimer: string | null
} | null {
  if (!isRecord(rec)) return null
  const lineage = isRecord(rec.lineage) ? rec.lineage : null
  return {
    id: readNum(rec.id),
    snapshotHash: typeof rec.snapshot_hash === "string" ? rec.snapshot_hash : null,
    objectiveTarget: readNum(rec.objective_target),
    globalMean: readNum(rec.global_mean),
    trainedN: readNum(rec.trained_n),
    excludedGoldCount: readNum(rec.excluded_gold_count),
    excludedUnverifiedCount: readNum(rec.excluded_unverified_count),
    sourceProjectIds: Array.isArray(rec.source_project_ids)
      ? rec.source_project_ids.filter((n): n is number => typeof n === "number")
      : [],
    augmentationCount: readNum(rec.augmentation_count),
    lineage,
    // Only an explicit false marks a preview; absent/true reads as verified-only.
    verifiedOnly: lineage?.verified_only !== false,
    createdAt: typeof rec.created_at === "string" ? rec.created_at : null,
    disclaimer: typeof rec.disclaimer === "string" ? rec.disclaimer : null,
  }
}

/** R10 — typed view over a ReactionWarmStartRanking (advisory; never the optimiser's decision). */
export function reactionWarmStartRankingView(resp: unknown): {
  advisory: boolean
  priorId: number | null
  boRunId: number | null
  globalMean: number | null
  disclaimer: string | null
  ranked: {
    proposalRef: string
    priorMean: number | null
    originalRank: number | null
    conditionsJson: Record<string, unknown>
  }[]
} | null {
  if (!isRecord(resp)) return null
  const rawRanked = Array.isArray(resp.ranked) ? resp.ranked : []
  return {
    advisory: resp.advisory !== false,
    priorId: readNum(resp.prior_id),
    boRunId: readNum(resp.bo_run_id),
    globalMean: readNum(resp.global_mean),
    disclaimer: typeof resp.disclaimer === "string" ? resp.disclaimer : null,
    ranked: rawRanked.filter(isRecord).map((it) => ({
      proposalRef: typeof it.proposal_ref === "string" ? it.proposal_ref : String(it.proposal_ref ?? ""),
      priorMean: readNum(it.prior_mean),
      originalRank: readNum(it.original_rank),
      conditionsJson: isRecord(it.conditions_json) ? it.conditions_json : {},
    })),
  }
}

/** R10 — index the warm-start ranking by canonical conditions key (same id-space-agnostic join as
 *  R9: proposal_ref is an acquisition-candidate id, not the recommendation-row id the cards use). */
export function reactionWarmStartRankByConditions(
  ranking: ReturnType<typeof reactionWarmStartRankingView>,
): Map<string, { priorMean: number | null; originalRank: number | null; rerank: number }> {
  const m = new Map<string, { priorMean: number | null; originalRank: number | null; rerank: number }>()
  if (!ranking) return m
  ranking.ranked.forEach((it, i) => {
    const key = canonicalConditionsKey(it.conditionsJson)
    if (key && !m.has(key)) {
      m.set(key, { priorMean: it.priorMean, originalRank: it.originalRank, rerank: i + 1 })
    }
  })
  return m
}

/** R10 — build the warm-start prior request body. An empty source list is omitted so the backend
 *  defaults to intra-campaign (this project only); a blank target is omitted (→ null server-side). */
export function reactionWarmStartBuildBody(opts: {
  sourceProjectIds: number[]
  objectiveTarget?: string | number | null
  requireVerified: boolean
  goldSetObservationIds?: string[]
}): {
  source_project_ids?: number[]
  objective_target?: number
  require_verified: boolean
  gold_set_observation_ids?: string[]
} {
  const body: {
    source_project_ids?: number[]
    objective_target?: number
    require_verified: boolean
    gold_set_observation_ids?: string[]
  } = { require_verified: opts.requireVerified }
  const ids = opts.sourceProjectIds.filter((n) => Number.isFinite(n))
  if (ids.length > 0) body.source_project_ids = Array.from(new Set(ids))
  const raw = String(opts.objectiveTarget ?? "").trim()
  if (raw !== "") {
    const t = typeof opts.objectiveTarget === "number" ? opts.objectiveTarget : Number(raw)
    if (Number.isFinite(t)) body.objective_target = t
  }
  const gold = (opts.goldSetObservationIds ?? []).filter((s) => typeof s === "string" && s.trim() !== "")
  if (gold.length > 0) body.gold_set_observation_ids = gold
  return body
}

/** R10 — user-facing message for a failed warm-start build. 400 carries the admissible-data reason
 *  (no verified experiments / duplicate observation ids / non-native value) in `detail`; a 404 is the
 *  non-leaking owner/source guard (don't echo which id). */
export function reactionWarmStartErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 400 && isRecord(err.data) && typeof err.data.detail === "string") return err.data.detail
    if (err.status === 404) {
      return "No warm-start prior could be built — check that you own every source campaign you selected."
    }
  }
  return formatApiError(err, "Could not build the warm-start prior.")
}

/** R9 — typed view over a ReactionABPromotionVerdict. Pure decision-support: deploys nothing.
 *  `promotable` is true only when there is no safety regression AND the challenger dominates;
 *  human sign-off + rollback are always required. */
export function reactionAbVerdictView(resp: unknown): {
  championVersion: string | null
  challengerVersion: string | null
  promotable: boolean
  safetyRegression: boolean
  dominates: boolean
  requiresHumanSignoff: boolean
  rollbackAvailable: boolean
  reasons: string[]
  excludedMetrics: string[]
  disclaimer: string | null
} | null {
  if (!isRecord(resp)) return null
  const strList = (v: unknown) =>
    Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []
  return {
    championVersion: typeof resp.champion_version === "string" ? resp.champion_version : null,
    challengerVersion: typeof resp.challenger_version === "string" ? resp.challenger_version : null,
    promotable: resp.promotable === true,
    safetyRegression: resp.safety_regression === true,
    dominates: resp.dominates === true,
    requiresHumanSignoff: resp.requires_human_signoff !== false,
    rollbackAvailable: resp.rollback_available !== false,
    reasons: strList(resp.reasons),
    excludedMetrics: strList(resp.excluded_metrics),
    disclaimer: typeof resp.disclaimer === "string" ? resp.disclaimer : null,
  }
}

/** R9 — parse a "name=value, name2=value2" (or newline / JSON) string into a numeric metric map.
 *  Non-numeric entries are dropped, so a malformed field never poisons the request. */
export function parseReactionMetricsText(text: string): Record<string, number> {
  const out: Record<string, number> = {}
  const t = (text ?? "").trim()
  if (!t) return out
  if (t.startsWith("{")) {
    try {
      const obj: unknown = JSON.parse(t)
      if (isRecord(obj)) {
        for (const [k, v] of Object.entries(obj)) {
          const n = typeof v === "number" ? v : Number(v)
          if (k.trim() && Number.isFinite(n)) out[k.trim()] = n
        }
        return out
      }
    } catch {
      // fall through to key=value parsing
    }
  }
  for (const pair of t.split(/[,\n]/)) {
    const idx = pair.search(/[=:]/)
    if (idx < 0) continue
    const k = pair.slice(0, idx).trim()
    const n = Number(pair.slice(idx + 1).trim())
    if (k && Number.isFinite(n)) out[k] = n
  }
  return out
}

/** R9 — parse a "name=higher, name2=lower" string into a per-metric direction map. The backend's
 *  A/B engine only honours the tokens "higher" / "lower" (anything else excludes the metric), so we
 *  normalize the friendly synonyms (maximize/max, minimize/min) to those. */
export function parseReactionDirectionsText(text: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const pair of (text ?? "").split(/[,\n]/)) {
    const idx = pair.search(/[=:]/)
    if (idx < 0) continue
    const k = pair.slice(0, idx).trim()
    const raw = pair.slice(idx + 1).trim().toLowerCase()
    const v =
      raw === "higher" || raw === "maximize" || raw === "max" || raw === "up"
        ? "higher"
        : raw === "lower" || raw === "minimize" || raw === "min" || raw === "down"
          ? "lower"
          : null
    if (k && v) out[k] = v
  }
  return out
}

/** R9 — build the ReactionABEvaluateRequest body from the compare-panel form inputs. */
export function reactionAbEvaluateBody(form: {
  championVersion: string
  championMetrics: string
  championRecall: string | number
  challengerVersion: string
  challengerMetrics: string
  challengerRecall: string | number
  directions?: string
  tolerance?: string | number
}): {
  champion: { model_version: string; metrics: Record<string, number>; safety_flag_recall: number }
  challenger: { model_version: string; metrics: Record<string, number>; safety_flag_recall: number }
  directions?: Record<string, string>
  tolerance: number
} {
  const num = (v: string | number | undefined): number => {
    const n = typeof v === "number" ? v : Number(String(v ?? "").trim())
    return Number.isFinite(n) ? n : 0
  }
  const body: {
    champion: { model_version: string; metrics: Record<string, number>; safety_flag_recall: number }
    challenger: { model_version: string; metrics: Record<string, number>; safety_flag_recall: number }
    directions?: Record<string, string>
    tolerance: number
  } = {
    champion: {
      model_version: form.championVersion.trim() || "champion",
      metrics: parseReactionMetricsText(form.championMetrics),
      safety_flag_recall: num(form.championRecall),
    },
    challenger: {
      model_version: form.challengerVersion.trim() || "challenger",
      metrics: parseReactionMetricsText(form.challengerMetrics),
      safety_flag_recall: num(form.challengerRecall),
    },
    tolerance: num(form.tolerance),
  }
  const dirs = parseReactionDirectionsText(form.directions ?? "")
  if (Object.keys(dirs).length > 0) body.directions = dirs
  return body
}

/** R9 — user-facing message for a failed feedback POST. A 422 (e.g. reject without a valid reason)
 *  carries its reason in `detail`; formatApiError only unpacks 401/403/404, so surface 422 here. */
export function reactionFeedbackErrorMessage(err: unknown): string {
  if (err instanceof ApiError && err.status === 422) {
    if (isRecord(err.data) && typeof err.data.detail === "string") return err.data.detail
    return "A valid reason is required to reject a proposal."
  }
  return formatApiError(err, "Could not save your feedback.")
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
  // Display only — the stored value is still a true/false flag.
  if (typeof raw === "boolean") return raw ? "Yes" : "No"
  if (typeof raw === "number" && Number.isFinite(raw)) return String(raw)
  return String(raw)
}

/** Reader-facing name for a variable's type. The stored values ("boolean", …) are
 *  unchanged — statusLabel() alone would still print developer vocabulary. */
const VARIABLE_TYPE_LABELS: Record<string, string> = {
  categorical: "Categorical",
  numeric: "Numeric",
  boolean: "Yes / no",
  text: "Free text",
}

function variableTypeLabel(raw: unknown): string {
  const value = typeof raw === "string" ? raw.trim() : ""
  if (!value) return "—"
  return VARIABLE_TYPE_LABELS[value.toLowerCase()] ?? statusLabel(value)
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

/** Read a free-text "notes" field stored as the backend's list|dict json shape. */
function notesFromField(raw: unknown): string {
  if (typeof raw === "string") return raw
  if (Array.isArray(raw)) return raw.filter((v) => v != null).map((v) => String(v)).join("\n")
  if (raw && typeof raw === "object") {
    const notes = (raw as Record<string, unknown>).notes
    if (typeof notes === "string") return notes
    if (Array.isArray(notes)) return notes.map((v) => String(v)).join("\n")
  }
  return ""
}

/** Candidate pool the BO sampler draws from. Mirrors the server default
 *  (ReactionBayesianOptimizationRunRequest.candidate_count, ge=1 le=1000). */
const BO_CANDIDATE_COUNT = 64

/** Free text → the backend's `{notes: ...}` json object (empty text → {}). */
function notesToField(text: string): Record<string, unknown> {
  const t = text.trim()
  return t ? { notes: t } : {}
}

/**
 * Serialize a notes-style field non-destructively. These wire fields
 * (availability_json, safety_notes_json) can hold arbitrary structured data
 * that this free-text UI can't fully render; if the user hasn't changed the
 * visible text away from what we loaded, resend the original value verbatim
 * rather than clobbering it with a `{notes}`/`{}` reduction.
 */
function notesFieldForSave(text: string, loadedRaw: unknown): unknown {
  if (text.trim() === notesFromField(loadedRaw).trim()) {
    return loadedRaw ?? {}
  }
  return notesToField(text)
}

/** Coerce a checklist row's done-like flags from the "true"/"false" TEXT the structured
 *  editor emits into real booleans — the progress reader counts `x.done === true` strictly. */
export function checklistForWire(rows: Record<string, unknown>[]): Record<string, unknown>[] {
  const toBool = (v: unknown): unknown => {
    if (typeof v !== "string") return v
    const s = v.trim().toLowerCase()
    if (s === "true" || s === "yes" || s === "done" || s === "1") return true
    if (s === "false" || s === "no" || s === "0" || s === "") return false
    return v
  }
  return rows.map((row) => {
    const out = { ...row }
    for (const k of ["done", "completed", "checked"]) {
      if (k in out) out[k] = toBool(out[k])
    }
    return out
  })
}

/** Read a wire object field into a plain object (non-objects → {}), for JsonObjectField. */
function objectFromField(raw: unknown): Record<string, unknown> {
  return raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {}
}

/** Read a wire array-of-objects field for ObjectArrayField (a bare object → [object]). */
function objectArrayFromField(raw: unknown): Record<string, unknown>[] {
  if (Array.isArray(raw)) return raw.filter((v): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v))
  if (raw && typeof raw === "object") return [raw as Record<string, unknown>]
  return []
}

/** Read a wire cost/weight field into a flat name→number map for KeyNumberTableField. */
function numberMapFromField(raw: unknown): Record<string, number> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {}
  const out: Record<string, number> = {}
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    const n = typeof v === "number" ? v : Number(v)
    if (Number.isFinite(n)) out[k] = n
  }
  return out
}

/** Read a blocked-values wire field (array, or the legacy {name: true|[...]}) into a string list. */
function stringListFromField(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.filter((v) => v != null).map((v) => String(v))
  if (raw && typeof raw === "object") {
    const out: string[] = []
    for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
      if (v === true) out.push(k)
      else if (Array.isArray(v)) out.push(...v.map((e) => String(e)))
    }
    return out
  }
  return []
}

/** Read an incompatible-pairs wire field (array-of-pairs, or {pairs:[...]}) into [a,b] rows. */
function pairListFromField(raw: unknown): [string, string][] {
  const list = Array.isArray(raw)
    ? raw
    : raw && typeof raw === "object" && Array.isArray((raw as Record<string, unknown>).pairs)
      ? ((raw as Record<string, unknown>).pairs as unknown[])
      : []
  const out: [string, string][] = []
  for (const item of list) {
    if (Array.isArray(item) && item.length >= 2) {
      out.push([String(item[0] ?? ""), String(item[1] ?? "")])
    } else if (item && typeof item === "object") {
      const rec = item as Record<string, unknown>
      const left = rec.left ?? rec.a
      const right = rec.right ?? rec.b
      if (left != null && right != null) out.push([String(left), String(right)])
    }
  }
  return out
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
          Interpretations are
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
            Human review required: {flagLabel(payload.human_review_required)}
          </Badge>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium uppercase text-muted-foreground">Condition summary</p>
          <pre className="max-h-40 overflow-auto rounded-md bg-muted/40 p-3 text-xs leading-relaxed">
            {jsonPreview(isRecord(payload.condition_summary_json) ? payload.condition_summary_json : {}, 6000)}
          </pre>
        </div>

        <div className="space-y-1">
          <p className="text-xs font-medium uppercase text-muted-foreground">Mechanistic rationale</p>
          <p className="text-muted-foreground">{String(payload.mechanistic_rationale ?? "")}</p>
        </div>

        <div className="space-y-1">
          <p className="text-xs font-medium uppercase text-muted-foreground">Practicality assessment</p>
          <p className="text-muted-foreground">{String(payload.practicality_assessment ?? "")}</p>
        </div>

        <div className="space-y-1">
          <p className="text-xs font-medium uppercase text-muted-foreground">Cost assessment</p>
          <p className="text-muted-foreground">{String(payload.cost_assessment ?? "")}</p>
        </div>

        <div className="space-y-1">
          <p className="text-xs font-medium uppercase text-muted-foreground">Safety assessment</p>
          <p className="text-muted-foreground">{String(payload.safety_assessment ?? "")}</p>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium uppercase text-muted-foreground">Risk flags</p>
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
            <p className="text-xs text-muted-foreground">Risk flags: none</p>
          )}
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium uppercase text-muted-foreground">Suggested controls</p>
          {suggestedControls.length > 0 ? (
            <pre className="max-h-40 overflow-auto rounded-md bg-muted/40 p-3 text-[10px] leading-snug">
              {jsonPreview(suggestedControls, 6000)}
            </pre>
          ) : (
            <p className="text-xs text-muted-foreground">Suggested controls: none</p>
          )}
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium uppercase text-muted-foreground">Suggested alternatives</p>
          {suggestedAlternatives.length > 0 ? (
            <pre className="max-h-40 overflow-auto rounded-md bg-muted/40 p-3 text-[10px] leading-snug">
              {jsonPreview(suggestedAlternatives, 6000)}
            </pre>
          ) : (
            <p className="text-xs text-muted-foreground">Suggested alternatives: none</p>
          )}
        </div>

        <DeveloperOnly>
          <Collapsible className="rounded-md border border-border">
            <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm font-medium hover:bg-muted/50">
              Developer JSON
              <ChevronDown className="h-4 w-4 shrink-0 opacity-70" />
            </CollapsibleTrigger>
            <CollapsibleContent className="border-t border-border px-3 py-3">
              <DeveloperJsonPanel data={payload} />
            </CollapsibleContent>
          </Collapsible>
        </DeveloperOnly>
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
  /** Latest project id, for dropping stale async responses after a client-side project switch. */
  const reactionProjectIdRef = useRef(reactionProjectId)
  reactionProjectIdRef.current = reactionProjectId

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  // Controlled tab value so the half-closed-loop banner can deep-link to the
  // Cost & Safety tab (where the R6 structural-safety screening / gate lives).
  const [activeTab, setActiveTab] = useState("overview")
  // Developer-mode gate: the raw-payload section is debugging surface, so it is
  // dropped from the nav (and from keyboard roaming) unless developer mode is on.
  // It used to be wrapped in <DeveloperOnly> around a single TabsTrigger.
  const reactionStudioDeveloperMode = useDeveloperMode().enabled
  const visibleReactionStudioNav = useMemo(
    () =>
      reactionStudioDeveloperMode
        ? REACTION_STUDIO_NAV
        : REACTION_STUDIO_NAV.filter((g) => g.id !== "developer"),
    [reactionStudioDeveloperMode],
  )
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
  const [mhSupporting, setMhSupporting] = useState<Record<string, unknown>[]>([])
  const [mhContradicting, setMhContradicting] = useState<Record<string, unknown>[]>([])
  const [mhFormKey, setMhFormKey] = useState(0)

  const [literaturePriors, setLiteraturePriors] = useState<unknown[]>([])
  const [lpSourceType, setLpSourceType] = useState<string>("user_note")
  const [lpTitle, setLpTitle] = useState("")
  const [lpSummary, setLpSummary] = useState("")
  const [lpCitation, setLpCitation] = useState("")
  const [lpTags, setLpTags] = useState<string[]>([])
  const [lpFormKey, setLpFormKey] = useState(0)

  /** Latest POST /optimization/run response for this session */
  const [lastOptimizationRun, setLastOptimizationRun] = useState<unknown>(null)
  /** Latest POST /optimization/bo/run response */
  const [lastBoRun, setLastBoRun] = useState<unknown>(null)
  // R9 — chemist feedback (per recommendation), advisory preference re-rank, A/B promotion gate.
  const [feedbackDraft, setFeedbackDraft] = useState<
    Record<number, { decision: string; reason: string; freeText: string }>
  >({})
  const [feedbackResult, setFeedbackResult] = useState<Record<number, Record<string, unknown>>>({})
  const [showLikelyAccept, setShowLikelyAccept] = useState(false)
  const [preferenceRanking, setPreferenceRanking] = useState<Record<string, unknown> | null>(null)
  const [abForm, setAbForm] = useState({
    championVersion: "",
    championMetrics: "",
    championRecall: "",
    challengerVersion: "",
    challengerMetrics: "",
    challengerRecall: "",
    directions: "",
    tolerance: "0",
  })
  // Structured A/B inputs (the metrics maps + direction map replace the parsed text fields).
  const [abChampionMetrics, setAbChampionMetrics] = useState<Record<string, number>>({})
  const [abChallengerMetrics, setAbChallengerMetrics] = useState<Record<string, number>>({})
  const [abDirections, setAbDirections] = useState<Record<string, string>>({})
  const [abVerdict, setAbVerdict] = useState<Record<string, unknown> | null>(null)
  // R10 — warm-start transfer-learning priors.
  const [warmStartPrior, setWarmStartPrior] = useState<Record<string, unknown> | null>(null)
  /** true ⇒ the prior GET failed for a NON-404 reason — render "couldn't load", never "none yet". */
  const [wsPriorLoadFailed, setWsPriorLoadFailed] = useState(false)
  const [warmStartRanking, setWarmStartRanking] = useState<Record<string, unknown> | null>(null)
  const [showWarmStartRank, setShowWarmStartRank] = useState(false)
  /** "loading" | "loaded" | "error" for the owned-campaign picker (distinct empty vs failed). */
  const [wsProjectsStatus, setWsProjectsStatus] = useState<"loading" | "loaded" | "error">("loading")
  const [ownedReactionProjects, setOwnedReactionProjects] = useState<Record<string, unknown>[]>([])
  const [wsSourceIds, setWsSourceIds] = useState<number[]>([])
  const [wsObjectiveTarget, setWsObjectiveTarget] = useState("")
  const [wsRequireVerified, setWsRequireVerified] = useState(true)
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
  const [weightEFactor, setWeightEFactor] = useState("")
  const [weightAtomEconomy, setWeightAtomEconomy] = useState("")
  const [weightGreenScore, setWeightGreenScore] = useState("")
  const [minimumYield, setMinimumYield] = useState("")
  const [minimumSelectivity, setMinimumSelectivity] = useState("")
  const [maximumImpurity, setMaximumImpurity] = useState("")
  const [hardConstraints, setHardConstraints] = useState<Record<string, unknown>>({})
  const [softConstraints, setSoftConstraints] = useState<Record<string, unknown>>({})
  const [objectiveFormKey, setObjectiveFormKey] = useState(0)
  const [explorationByVariableId, setExplorationByVariableId] = useState<Record<number, ExplorationState>>({})

  const [costProfileRaw, setCostProfileRaw] = useState<unknown>(null)
  const [safetyProfileRaw, setSafetyProfileRaw] = useState<unknown>(null)
  // Cost/safety profiles: structured object state (was raw-JSON text). A `key`
  // bump (costFormKey) remounts the field editors after a reload/save so they
  // reseed from the freshly-loaded values.
  const [reagentCosts, setReagentCosts] = useState<Record<string, number>>({})
  const [solventCosts, setSolventCosts] = useState<Record<string, number>>({})
  const [catalystCosts, setCatalystCosts] = useState<Record<string, number>>({})
  const [ligandCosts, setLigandCosts] = useState<Record<string, number>>({})
  const [availabilityNotes, setAvailabilityNotes] = useState("")
  // The loaded availability_json verbatim. It is a functional map the optimizer reads
  // (unavailable reagents are penalized), not just prose — preserve it byte-for-byte
  // unless the user edits the visible notes text, so a PATCH never wipes structured data.
  const [availabilityRaw, setAvailabilityRaw] = useState<unknown>(null)
  const [maxCostPerExperiment, setMaxCostPerExperiment] = useState("")
  const [costProfilePenaltyWeight, setCostProfilePenaltyWeight] = useState("")
  const [costFormKey, setCostFormKey] = useState(0)
  const [blockedReagents, setBlockedReagents] = useState<string[]>([])
  const [blockedSolvents, setBlockedSolvents] = useState<string[]>([])
  const [maxTemperatureC, setMaxTemperatureC] = useState("")
  const [maxPressureBar, setMaxPressureBar] = useState("")
  const [incompatiblePairs, setIncompatiblePairs] = useState<[string, string][]>([])
  const [requiredControls, setRequiredControls] = useState<string[]>([])
  const [safetyNotes, setSafetyNotes] = useState("")
  // As with availabilityRaw: preserve the loaded safety_notes_json unless the visible
  // text is edited, so we never overwrite a structured value we couldn't fully display.
  const [safetyNotesRaw, setSafetyNotesRaw] = useState<unknown>(null)
  const [safetyFormKey, setSafetyFormKey] = useState(0)

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
  const [boardDialogChecklist, setBoardDialogChecklist] = useState<Record<string, unknown>[]>([])
  const [arExecutionItemId, setArExecutionItemId] = useState("")
  const [arResultType, setArResultType] = useState<string>(ANALYTICAL_RESULT_TYPE_OPTIONS[0])
  const [arSpectraCheckSessionId, setArSpectraCheckSessionId] = useState("")
  const [arFileId, setArFileId] = useState("")
  const [arArtifactId, setArArtifactId] = useState("")
  const [arSourceHash, setArSourceHash] = useState("")
  const [arSummary, setArSummary] = useState<Record<string, unknown>>({})
  const [arFormKey, setArFormKey] = useState(0)
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
  const [execPlannerChecklist, setExecPlannerChecklist] = useState<Record<string, unknown>[]>([])
  const [execPlannerFormKey, setExecPlannerFormKey] = useState(0)
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
        setWeightEFactor(wNum("e_factor_weight"))
        setWeightAtomEconomy(wNum("atom_economy_weight"))
        setWeightGreenScore(wNum("green_score_weight"))
        // Thresholds come back ONLY under target_thresholds_json (the write-side nests them
        // there); keep the legacy top-level / target_thresholds reads as fallbacks for old rows.
        const tt = isRecord(opRaw.target_thresholds_json)
          ? opRaw.target_thresholds_json
          : isRecord(opRaw.target_thresholds)
            ? opRaw.target_thresholds
            : null
        const rMinY = readNum(tt?.minimum_yield) ?? readNum(opRaw.minimum_yield)
        const rMinS = readNum(tt?.minimum_selectivity) ?? readNum(opRaw.minimum_selectivity)
        const rMaxI = readNum(tt?.maximum_impurity) ?? readNum(opRaw.maximum_impurity)
        setMinimumYield(rMinY != null ? String(rMinY) : "")
        setMinimumSelectivity(rMinS != null ? String(rMinS) : "")
        setMaximumImpurity(rMaxI != null ? String(rMaxI) : "")
        setHardConstraints(objectFromField(opRaw.hard_constraints_json ?? opRaw.hard_constraints))
        setSoftConstraints(objectFromField(opRaw.soft_constraints_json ?? opRaw.soft_constraints))
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
        setHardConstraints({})
        setSoftConstraints({})
      }
      setObjectiveFormKey((k) => k + 1)

      const variableRecordsForMap = vrList.filter(isRecord) as Record<string, unknown>[]
      setExplorationByVariableId(buildExplorationMap(variableRecordsForMap, dsRaw))

      setCostProfileRaw(costRaw)
      if (isRecord(costRaw)) {
        setReagentCosts(numberMapFromField(costRaw.reagent_costs_json))
        setSolventCosts(numberMapFromField(costRaw.solvent_costs_json))
        setCatalystCosts(numberMapFromField(costRaw.catalyst_costs_json))
        setLigandCosts(numberMapFromField(costRaw.ligand_costs_json))
        setAvailabilityRaw(costRaw.availability_json ?? null)
        setAvailabilityNotes(notesFromField(costRaw.availability_json))
        const mce = readNum(costRaw.max_cost_per_experiment)
        setMaxCostPerExperiment(mce != null ? String(mce) : "")
        const cpw = readNum(costRaw.cost_penalty_weight)
        setCostProfilePenaltyWeight(cpw != null ? String(cpw) : "")
      } else {
        setReagentCosts({})
        setSolventCosts({})
        setCatalystCosts({})
        setLigandCosts({})
        setAvailabilityRaw(null)
        setAvailabilityNotes("")
        setMaxCostPerExperiment("")
        setCostProfilePenaltyWeight("")
      }
      setCostFormKey((k) => k + 1)

      setSafetyProfileRaw(safetyRaw)
      if (isRecord(safetyRaw)) {
        setBlockedReagents(stringListFromField(safetyRaw.blocked_reagents_json))
        setBlockedSolvents(stringListFromField(safetyRaw.blocked_solvents_json))
        const tc = readNum(safetyRaw.max_temperature_c)
        setMaxTemperatureC(tc != null ? String(tc) : "")
        const pb = readNum(safetyRaw.max_pressure_bar)
        setMaxPressureBar(pb != null ? String(pb) : "")
        setIncompatiblePairs(pairListFromField(safetyRaw.incompatible_pairs_json))
        setRequiredControls(stringListFromField(safetyRaw.required_controls_json))
        setSafetyNotesRaw(safetyRaw.safety_notes_json ?? null)
        setSafetyNotes(notesFromField(safetyRaw.safety_notes_json))
      } else {
        setBlockedReagents([])
        setBlockedSolvents([])
        setMaxTemperatureC("")
        setMaxPressureBar("")
        setIncompatiblePairs([])
        setRequiredControls([])
        setSafetyNotesRaw(null)
        setSafetyNotes("")
      }
      setSafetyFormKey((k) => k + 1)

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

  // R10 — load any existing warm-start prior + the owned-campaign picker options on mount / project
  // switch, and seed the source picker with this campaign (intra-campaign warm-start is the default).
  // A project change RESETS every R9/R10 rank surface first, so project B's cards can never render
  // re-ranked/badged by project A's prior or preference model.
  useEffect(() => {
    setWarmStartPrior(null)
    setWsPriorLoadFailed(false)
    setWarmStartRanking(null)
    setShowWarmStartRank(false)
    setPreferenceRanking(null)
    setShowLikelyAccept(false)
    setWsSourceIds([reactionProjectId])
    void loadWarmStartPrior()
    void loadOwnedReactionProjects()
  }, [reactionProjectId])

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

  // Repho R2 — multi-objective Pareto front rides inside the latest BO run's
  // diagnostics_json (null for single-objective campaigns / insufficient data).
  const paretoFront = useMemo(
    () => paretoFrontFromRun(execTabLatestBoRunRecord),
    [execTabLatestBoRunRecord],
  )
  const paretoTrend = useMemo(
    () => (paretoFront ? hypervolumeTrend(boRuns, objectivesKey(paretoFront.objectives)) : []),
    [paretoFront, boRuns],
  )
  const paretoNonDominatedIds = useMemo(() => nonDominatedExperimentIds(paretoFront), [paretoFront])
  const paretoKneeId = paretoFront?.kneeExperimentId ?? null

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

  // R9 — best-effort model version that produced the current proposals (feedback provenance).
  const reactionRunModelHint = useMemo<string | null>(() => {
    const tryKeys = (o: unknown, keys: string[]): string | null => {
      if (!isRecord(o)) return null
      for (const k of keys) {
        const v = o[k]
        if (typeof v === "string" && v) return v
      }
      return null
    }
    return (
      tryKeys(lastBoRun, ["surrogate_model_version", "model_version", "algorithm"]) ??
      tryKeys(lastOptimizationRun, ["model_version", "model_type"]) ??
      null
    )
  }, [lastBoRun, lastOptimizationRun])

  // R9 — advisory preference ranking joined to cards by conditions content (id-space-agnostic).
  const preferenceRankByConditions = useMemo(
    () => reactionPreferenceRankByConditions(reactionPreferenceRankingView(preferenceRanking)),
    [preferenceRanking],
  )

  // R10 — warm-start ranking joined to cards by conditions content (same id-space-agnostic join).
  const warmStartRankByConditions = useMemo(
    () => reactionWarmStartRankByConditions(reactionWarmStartRankingView(warmStartRanking)),
    [warmStartRanking],
  )

  // R9/R10 — how many of the displayed proposals the ACTIVE re-rank actually covers (transparency:
  // the re-rank is a no-op for anything it can't match, so we surface "ranked M of N").
  const rerankMatchCount = useMemo(() => {
    const active = showLikelyAccept
      ? preferenceRankByConditions
      : showWarmStartRank
        ? warmStartRankByConditions
        : null
    if (!active || active.size === 0) return 0
    return sortedRecs.filter((r) => active.has(canonicalConditionsKey(r.conditions_json))).length
  }, [showLikelyAccept, showWarmStartRank, preferenceRankByConditions, warmStartRankByConditions, sortedRecs])

  // R9/R10 — recommendation cards, optionally re-ordered by the ACTIVE advisory re-rank (likely
  // acceptance OR warm-start prior_mean; mutually exclusive) while keeping the optimiser's own order
  // recoverable via each card's original_rank badge.
  const displayRecs = useMemo(() => {
    const scoreOf = showLikelyAccept
      ? (r: Record<string, unknown>) =>
          preferenceRankByConditions.get(canonicalConditionsKey(r.conditions_json))?.acceptanceScore ?? -Infinity
      : showWarmStartRank
        ? (r: Record<string, unknown>) =>
            warmStartRankByConditions.get(canonicalConditionsKey(r.conditions_json))?.priorMean ?? -Infinity
        : null
    if (!scoreOf) return sortedRecs
    const score = scoreOf
    return [...sortedRecs].sort((a, b) => score(b) - score(a))
  }, [showLikelyAccept, showWarmStartRank, preferenceRankByConditions, warmStartRankByConditions, sortedRecs])

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
        detail: `${kind} · #${idNum ?? "—"} · ${optionLabel(det)}`,
        whenLabel: fmtIso(tRaw),
      })
    }
    for (const x of boRuns) {
      if (isRecord(x)) addRecord("Bayesian optimization run", x, ["id", "bo_run_id"], ["algorithm"])
    }
    for (const x of runs) {
      if (isRecord(x)) addRecord("Heuristic optimization run", x, ["id"], ["model_type"])
    }
    for (const x of advisorRunsList) {
      if (isRecord(x)) addRecord("Advisor run", x, ["advisor_run_id", "id"], ["advisor_mode"])
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

  // Autocomplete pool for the cost/safety name fields: the design space's own
  // categorical choices (catalyst/solvent/ligand/base names) so a chemist picks
  // a value that already exists in the campaign instead of retyping it.
  const categoricalSuggestions = useMemo(() => {
    const seen = new Set<string>()
    for (const v of variableRecords) {
      const allowed = v.allowed_values_json
      if (Array.isArray(allowed)) {
        for (const a of allowed) {
          const s = a == null ? "" : String(a).trim()
          if (s) seen.add(s)
        }
      }
    }
    return [...seen].sort((a, b) => a.localeCompare(b))
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
    putW("e_factor_weight", weightEFactor)
    putW("atom_economy_weight", weightAtomEconomy)
    putW("green_score_weight", weightGreenScore)

    const putThreshold = (s: string) => {
      const t = s.trim()
      if (!t) return null
      const n = Number.parseFloat(t)
      return Number.isFinite(n) ? n : null
    }
    const minimum_yield = putThreshold(minimumYield)
    const minimum_selectivity = putThreshold(minimumSelectivity)
    const maximum_impurity = putThreshold(maximumImpurity)

    // The Create model (ReactionObjectiveProfileCreate, extra=forbid) has no
    // minimum_yield/selectivity/impurity fields — thresholds live in
    // target_thresholds_json (which is how the read-side already hydrates them),
    // and hard/soft constraints are `dict` (no None). The previous payload sent
    // those thresholds as top-level keys + null/string constraints and 422'd.
    const target_thresholds_json: Record<string, number> = {}
    if (minimum_yield != null) target_thresholds_json.minimum_yield = minimum_yield
    if (minimum_selectivity != null) target_thresholds_json.minimum_selectivity = minimum_selectivity
    if (maximum_impurity != null) target_thresholds_json.maximum_impurity = maximum_impurity

    return {
      objective_type: objectiveType,
      weights_json,
      target_thresholds_json,
      hard_constraints_json: hardConstraints,
      soft_constraints_json: softConstraints,
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
    // The Create model (ReactionCostProfileCreate, extra=forbid) types the cost
    // maps as `dict` with no `None`, and has no `availability_notes` field — it's
    // `availability_json: dict`. Send the objects directly (empty → {}) under the
    // schema keys; the previous payload (unsuffixed key + null empties) 422'd.
    return {
      reagent_costs_json: reagentCosts,
      solvent_costs_json: solventCosts,
      catalyst_costs_json: catalystCosts,
      ligand_costs_json: ligandCosts,
      availability_json: notesFieldForSave(availabilityNotes, availabilityRaw),
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
    // The Create model (ReactionSafetyConstraintProfileCreate, extra=forbid) uses
    // `_json`-suffixed keys typed `list|dict` (no `None`), and `safety_notes_json`
    // is a list|dict — not a string. The previous payload (unsuffixed keys, a
    // bare notes string, null empties) 422'd on every save. Send schema-correct
    // arrays (empty → []) and wrap the note text.
    return {
      blocked_reagents_json: blockedReagents,
      blocked_solvents_json: blockedSolvents,
      max_temperature_c,
      max_pressure_bar,
      incompatible_pairs_json: incompatiblePairs,
      required_controls_json: requiredControls,
      safety_notes_json: notesFieldForSave(safetyNotes, safetyNotesRaw),
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
      setMsg({ tone: "err", text: "Experiment code is required." })
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
        // ReactionBayesianOptimizationRunRequest is extra="forbid": the field is
        // `include_negative_outcomes`, there is no `notes` key (free text belongs in
        // metadata_json), and candidate_count is sent explicitly because
        // openapi-typescript renders server-defaulted fields as required.
        include_negative_outcomes: boIncludeFailedAsNegative,
        candidate_count: BO_CANDIDATE_COUNT,
        metadata_json: notesToField(boNotes),
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
          // ReactionOptimizationBenchmarkRequest (extra="forbid") accepts only
          // benchmark_name (non-null str), algorithm (enum), and metadata_json.
          // The objective/budget/seed/use-completed controls have no model slot, so
          // carry them in metadata_json (non-lossy, auditable) rather than as rejected
          // top-level keys; a BE change is needed for them to affect the benchmark.
          benchmark_name: benchmarkName.trim() || "phase50_replay",
          algorithm: benchmarkAlgorithm.trim() || "rule_based_fallback",
          metadata_json: {
            objective: benchmarkObjective.trim() || objective || null,
            experiment_budget,
            random_seed,
            use_completed_project_data: useCompletedProjectData,
          },
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
    setBusy("mh-create")
    try {
      await apiFetch(`/reaction-projects/${reactionProjectId}/mechanistic-hypotheses`, {
        method: "POST",
        body: {
          title,
          hypothesis,
          supporting_observations_json: mhSupporting,
          contradicting_observations_json: mhContradicting,
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
      setMhSupporting([])
      setMhContradicting([])
      setMhFormKey((k) => k + 1)
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
    const relevance_tags_json = lpTags
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
      setLpTags([])
      setLpFormKey((k) => k + 1)
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
      setMsg({ tone: "err", text: "Advisor run ID is required." })
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
      setMsg({ tone: "err", text: "A rationale is required before conversion." })
      setBusy(null)
      return
    }
    const rid = convertRecExecutionBatchId.trim()
    let execution_batch_id: number | undefined
    if (rid && rid !== "__none__") {
      const n = Number.parseInt(rid, 10)
      if (!Number.isFinite(n) || n < 1) {
        setMsg({ tone: "err", text: "Execution batch ID must be a positive integer when provided." })
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
            ? `Planned experiment recorded (experiment id ${experiment_id}; status ${statusLabel(experiment_status)}). Saving a conversion does not mean the experiment was performed in the lab.`
            : "Conversion completed — check the experiment list to confirm an experiment was created.",
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
        text: formatApiError(err, "Could not convert the recommendation to a planned experiment."),
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
      setMsg({ tone: "err", text: "Batch code is required." })
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
        text: formatApiError(err, "Could not create the execution batch."),
      })
    } finally {
      setBusy(null)
    }
  }

  async function addExecutionPlannerItem(e: React.FormEvent) {
    e.preventDefault()
    setMsg(null)
    if (plannerSelectedBatchId == null || !Number.isFinite(plannerSelectedBatchId)) {
      setMsg({ tone: "err", text: "Open an execution batch first." })
      return
    }
    const item_code = execPlannerItemCode.trim()
    if (!item_code) {
      setMsg({ tone: "err", text: "Item code is required." })
      return
    }
    const exRaw = execPlannerExperimentId.trim()
    if (!exRaw || exRaw === "__none__") {
      setMsg({
        tone: "err",
        text: "Select a planned experiment to link the item to its stored conditions.",
      })
      return
    }
    const experiment_id = Number.parseInt(exRaw, 10)
    if (!Number.isFinite(experiment_id) || experiment_id < 1) {
      setMsg({ tone: "err", text: "Experiment ID must be a positive integer." })
      return
    }
    const chosen = plannedExperimentsForPlanner.some((row) => readNum(row.id) === experiment_id)
    if (!chosen) {
      setMsg({ tone: "err", text: "Selected experiment must have status planned." })
      return
    }
    setBusy("exec-item-add")
    try {
      const body: Record<string, unknown> = {
        item_code,
        experiment_id,
        status: "planned",
        checklist_json: checklistForWire(execPlannerChecklist),
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
      setExecPlannerChecklist([])
      setExecPlannerFormKey((k) => k + 1)
      await reload()
    } catch (err) {
      setMsg({
        tone: "err",
        text: formatApiError(err, "Could not add the execution item."),
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
      setBoardDialogChecklist(objectArrayFromField(item.checklist_json))
    } else {
      setBoardDialogChecklist([])
    }
  }

  function closeExecutionBoardDialog() {
    setBoardDialog(null)
    setBoardDialogOperator("")
    setBoardDialogMessage("")
    setBoardDialogFailureReason("")
    setBoardDialogNote("")
    setBoardDialogChecklist([])
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
          setMsg({ tone: "err", text: "A failure reason is required to mark the item failed." })
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
        await apiFetch(`/reaction-execution-items/${itemId}`, {
          method: "PATCH",
          body: { checklist_json: checklistForWire(boardDialogChecklist) },
        })
        setMsg({ tone: "ok", text: "Checklist saved." })
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
        setMsg({ tone: "ok", text: "Note saved." })
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
      setMsg({ tone: "err", text: "Session ID, file ID, and artifact ID must be positive integers when provided." })
      return
    }
    setBusy("exec-analytical-add")
    try {
      const body: Record<string, unknown> = {
        result_type: arResultType,
        summary_json: arSummary,
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
      setArSummary({})
      setArFormKey((k) => k + 1)
      setMsg({ tone: "ok", text: "Analytical result linked to execution item." })
      await loadExecutionItemAnalyticalResults(executionItemId)
    } catch (err) {
      setMsg({
        tone: "err",
        text: formatApiError(err, "Couldn't link the analytical result."),
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
      setMsg({ tone: "err", text: "An execution item is required." })
      return
    }

    let analytical_result_id: number | undefined
    const arChoice = oeAnalyticalResultIdChoice.trim()
    if (arChoice !== "" && arChoice !== "__all__") {
      const nar = Number.parseInt(arChoice, 10)
      if (!Number.isFinite(nar) || nar < 1) {
        setMsg({ tone: "err", text: "The analytical result ID must be a positive integer when provided." })
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
        text: formatApiError(err, "Couldn't extract the proposed outcome."),
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
      setMsg({ tone: "err", text: "An execution item is required." })
      return
    }

    const rationale = oeConfirmRationale.trim()
    if (!rationale) {
      setMsg({
        tone: "err",
        text: "Provide a confirmation rationale (reviewer comment). A reviewer name is recommended when available.",
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
        text: "Extract the proposed outcome first, or fill at least one confirmed outcome field before confirming.",
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
      setMsg({ tone: "ok", text: "Confirmed outcome applied to the official experiment outcome." })
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
        text: formatApiError(err, "Couldn't confirm the outcome."),
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
        setMsg({ tone: "err", text: "Cycle number must be a positive integer when provided." })
        return
      }
      body.cycle_number = n
    }

    const eb = optCcExecutionBatchId.trim()
    if (eb !== "" && eb !== "__none__") {
      const bid = Number.parseInt(eb, 10)
      if (!Number.isFinite(bid) || bid < 1) {
        setMsg({ tone: "err", text: "The execution batch ID must be a positive integer when selected." })
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
        text: formatApiError(err, "Couldn't create the optimization cycle."),
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
        text: formatApiError(err, "Couldn't record the cycle decision."),
      })
    } finally {
      setBusy(null)
    }
  }

  // R5 — half-closed DMTA loop: propose the next batch as a NEW DRAFT cycle.
  // Decision-support only — it executes nothing; committing an execution batch
  // still needs a human (and passes the R6 safety gate). The backend 409s with a
  // human-readable reason when the latest decision isn't `continue_optimization`.
  /** Deep-link from the half-closed-loop banner to the structural-safety gate,
   *  which lives in the Cost & Safety tab (a different tab from the cycle UI). */
  function goToSafetyGate() {
    setActiveTab("cost-safety")
    if (typeof window === "undefined") return
    window.requestAnimationFrame(() => {
      const el = document.getElementById("reaction-safety-gate")
      el?.scrollIntoView({ block: "start", behavior: "smooth" })
      el?.focus({ preventScroll: true })
    })
  }

  /** R9 — POST structured chemist feedback on a proposal. A reject needs a reason (guarded here +
   *  backed by the 422). The response's routing flags tell us whether it was an unsafe rejection
   *  (routed to the safety gate, excluded from preference learning). */
  async function submitReactionFeedback(rec: Record<string, unknown>) {
    const id = readNum(rec.id)
    if (id == null) return
    const draft = feedbackDraft[id] ?? { decision: "accept", reason: "", freeText: "" }
    if (reactionFeedbackReasonRequired(draft.decision) && !draft.reason) {
      setMsg({ tone: "err", text: "A reason is required to reject a proposal." })
      return
    }
    setMsg(null)
    setBusy(`feedback-${id}`)
    try {
      const body: Record<string, unknown> = {
        proposal_ref: String(id),
        decision: draft.decision,
        free_text: draft.freeText.trim(),
      }
      if (draft.reason) body.reason = draft.reason
      if (isRecord(rec.conditions_json)) body.features = rec.conditions_json
      const mv = reactionProposalModelVersion(rec, reactionRunModelHint)
      if (mv) body.model_version = mv
      const created = await apiFetch<unknown>(`/reaction-projects/${reactionProjectId}/feedback`, {
        method: "POST",
        body,
      })
      if (isRecord(created)) setFeedbackResult((prev) => ({ ...prev, [id]: created }))
      const view = reactionFeedbackRecordView(created)
      setMsg({
        tone: "ok",
        text: view?.isSafetySignal
          ? "Feedback recorded. Unsafe rejection routed to the safety gate — excluded from preference learning."
          : "Feedback recorded — advisory; it never overrides the optimiser.",
      })
    } catch (err) {
      setMsg({ tone: "err", text: reactionFeedbackErrorMessage(err) })
    } finally {
      setBusy(null)
    }
  }

  /** R9 — GET the advisory preference ranking and turn on the likely-accept re-rank. */
  async function loadPreferenceRanking() {
    setMsg(null)
    setBusy("pref-rank")
    try {
      const data = await apiFetch<unknown>(
        `/reaction-projects/${reactionProjectId}/preference-ranking`,
        { method: "GET" },
      )
      setPreferenceRanking(isRecord(data) ? data : null)
      setShowLikelyAccept(true)
    } catch (err) {
      setMsg({
        tone: "err",
        text: formatApiError(err, "Couldn't load the preference ranking."),
      })
    } finally {
      setBusy(null)
    }
  }

  /** R9 — POST an A/B promotion evaluation (pure decision-support; deploys nothing). */
  async function evaluateAbPromotion(e: React.FormEvent) {
    e.preventDefault()
    // Recall is the hard, blocking safety dimension — never fabricate a 0 for a blank/garbage field.
    if (parseReactionRecall(abForm.championRecall) == null || parseReactionRecall(abForm.challengerRecall) == null) {
      setMsg({
        tone: "err",
        text: "Safety-flag recall must be a number between 0 and 1 for both the champion and the challenger.",
      })
      return
    }
    setMsg(null)
    setBusy("ab-eval")
    try {
      // Build the request from the structured metric/direction maps (the string helper
      // reactionAbEvaluateBody stays for its unit tests; the UI now supplies objects directly).
      const numOr0 = (v: string): number => {
        const n = Number(v.trim())
        return Number.isFinite(n) ? n : 0
      }
      const body: Record<string, unknown> = {
        champion: {
          model_version: abForm.championVersion.trim() || "champion",
          metrics: abChampionMetrics,
          safety_flag_recall: parseReactionRecall(abForm.championRecall) ?? 0,
        },
        challenger: {
          model_version: abForm.challengerVersion.trim() || "challenger",
          metrics: abChallengerMetrics,
          safety_flag_recall: parseReactionRecall(abForm.challengerRecall) ?? 0,
        },
        tolerance: numOr0(abForm.tolerance),
      }
      if (Object.keys(abDirections).length > 0) body.directions = abDirections
      const data = await apiFetch<unknown>(
        `/reaction-projects/${reactionProjectId}/ab-promotion/evaluate`,
        { method: "POST", body },
      )
      setAbVerdict(isRecord(data) ? data : null)
    } catch (err) {
      setMsg({
        tone: "err",
        text: formatApiError(err, "Couldn't evaluate the A/B promotion."),
      })
    } finally {
      setBusy(null)
    }
  }

  /** R10 — fetch the chemist's owned reaction campaigns for the warm-start source picker. */
  async function loadOwnedReactionProjects() {
    setWsProjectsStatus("loading")
    try {
      const data = await apiFetch<unknown>("/reaction-projects", { method: "GET" })
      setOwnedReactionProjects(Array.isArray(data) ? (data.filter(isRecord) as Record<string, unknown>[]) : [])
      setWsProjectsStatus("loaded")
    } catch {
      setOwnedReactionProjects([])
      setWsProjectsStatus("error")
    }
  }

  /** R10 — GET the existing warm-start prior. ONLY a 404 means "none yet"; any other failure is a
   *  load error and must not masquerade as confirmed non-existence. Responses for a project the user
   *  has since navigated away from are dropped (stale-response guard). */
  async function loadWarmStartPrior() {
    const pid = reactionProjectId
    try {
      const data = await apiFetch<unknown>(`/reaction-projects/${pid}/warm-start/prior`, {
        method: "GET",
      })
      if (pid !== reactionProjectIdRef.current) return
      setWarmStartPrior(isRecord(data) ? data : null)
      setWsPriorLoadFailed(false)
    } catch (err) {
      if (pid !== reactionProjectIdRef.current) return
      setWarmStartPrior(null)
      setWsPriorLoadFailed(!(err instanceof ApiError && err.status === 404))
    }
  }

  /** R10 — build (freeze + fit) a warm-start prior from the selected owned campaigns. */
  async function buildWarmStartPrior(e: React.FormEvent) {
    e.preventDefault()
    // A non-numeric target must be refused, not silently dropped from the request.
    const rawTarget = wsObjectiveTarget.trim()
    if (rawTarget !== "" && !Number.isFinite(Number(rawTarget))) {
      setMsg({ tone: "err", text: "Objective target must be a number (or leave it blank)." })
      return
    }
    setMsg(null)
    setBusy("ws-build")
    try {
      const body = reactionWarmStartBuildBody({
        sourceProjectIds: wsSourceIds,
        objectiveTarget: wsObjectiveTarget,
        requireVerified: wsRequireVerified,
      })
      const created = await apiFetch<unknown>(
        `/reaction-projects/${reactionProjectId}/warm-start/prior`,
        { method: "POST", body },
      )
      setWarmStartPrior(isRecord(created) ? created : null)
      setWsPriorLoadFailed(false)
      // The new prior supersedes whatever an active ranking was computed from — force a refetch.
      setWarmStartRanking(null)
      setShowWarmStartRank(false)
      const view = reactionWarmStartPriorView(created)
      const n = view?.trainedN
      setMsg({
        tone: "ok",
        text:
          n != null
            ? wsRequireVerified
              ? `Warm-start prior fit from ${n} verified observation${n === 1 ? "" : "s"} — advisory; it never overrides the optimiser.`
              : `Warm-start prior fit from ${n} observation${n === 1 ? "" : "s"} (PREVIEW — includes unconfirmed data; rebuild with verified-only before real use).`
            : "Warm-start prior built (advisory).",
      })
    } catch (err) {
      setMsg({ tone: "err", text: reactionWarmStartErrorMessage(err) })
    } finally {
      setBusy(null)
    }
  }

  /** R10 — GET the warm-start ranking and turn on the (mutually exclusive with R9) warm-start re-rank. */
  async function loadWarmStartRanking() {
    setMsg(null)
    setBusy("ws-rank")
    try {
      const data = await apiFetch<unknown>(
        `/reaction-projects/${reactionProjectId}/warm-start/ranking`,
        { method: "GET" },
      )
      setWarmStartRanking(isRecord(data) ? data : null)
      setShowWarmStartRank(true)
      setShowLikelyAccept(false) // only one advisory re-rank active at a time
    } catch (err) {
      setMsg({
        tone: "err",
        text: formatApiError(err, "Couldn't load the warm-start ranking."),
      })
    } finally {
      setBusy(null)
    }
  }

  async function proposeNextBatch(cycleId: number) {
    setMsg(null)
    setBusy(`opt-cc-propose-${cycleId}`)
    try {
      const created = await apiFetch<unknown>(
        `/reaction-optimization-cycles/${cycleId}/propose-next`,
        {
          method: "POST",
          // Carry the BO params from the Bayesian-Optimization run form on the
          // Optimization tab (one shared config); every field is server-defaulted
          // so this stays valid when untouched.
          body: proposeNextRequestBody({
            algorithm: boAlgorithm,
            batchSize: boBatchSize,
            safetyAware: boSafetyAware,
          }),
        },
      )
      const row = isRecord(created) ? created : null
      const newId = row ? readNum(row.id) : null
      const newCn = row ? readNum(row.cycle_number) : null
      setMsg({
        tone: "ok",
        text:
          `Proposed the next batch as a new draft cycle${newCn != null ? ` (cycle ${newCn})` : ""}. ` +
          "Decision-support only — nothing has run; committing the batch still needs human signoff.",
      })
      await reload()
      if (newId != null) {
        setOccExpandedId(newId)
        void loadOptimizationCycleDetail(newId)
      }
    } catch (err) {
      setMsg({
        tone: "err",
        text: proposeNextErrorMessage(
          err,
          "Couldn't propose the next batch.",
        ),
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
      setMsg({ tone: "err", text: "Session ID must be a positive integer." })
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
        <AlertDescription className="text-xs">Missing or invalid reaction project ID.</AlertDescription>
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
              Project ID {reactionProjectId}
            </Badge>
          </div>
          <p
            className="font-mono text-[11px] font-bold uppercase tracking-[0.2em]"
            style={{ color: "var(--mt-violet-ink)" }}
          >
            MolTrace · Reaction Studio (project-level)
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight sm:text-3xl">Reaction Studio (project-level)</h1>
          <p className="text-sm text-muted-foreground">{loading ? "Loading…" : projectName}</p>
        </div>
        <div className="flex items-center gap-2">
          <FlaskConical className="h-5 w-5" style={{ color: "var(--mt-violet)" }} aria-hidden />
        </div>
      </div>

      {error ? (
        <AlertCard variant="error" title="Project data unavailable" description={error} />
      ) : null}

      {msg ? (
        <AlertCard
          variant={msg.tone === "ok" ? "success" : "error"}
          title={msg.tone === "ok" ? "Update" : "Error"}
          description={msg.text}
        />
      ) : null}

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full min-w-0">
        <WorkspaceStageNav
          groups={visibleReactionStudioNav}
          activeValue={activeTab}
          onSelect={setActiveTab}
          label="Reaction Studio"
          accent="violet"
        />

        {/* Reference material for the project, below the nav rather than above
            it: the sections are what a reader navigates by. */}
        <div className="mt-4">
          <ReactionStudioKnowledgeLinksCard reactionProjectId={reactionProjectId} />
        </div>

        <TabsContent value="overview" className="mt-4 space-y-6">
          <div className="space-y-1">
            <p
              className="font-mono text-[11px] font-bold uppercase tracking-[0.2em]"
              style={{ color: "var(--mt-violet-ink)" }}
            >
              Project · Overview
            </p>
            <h2 className="font-mono text-2xl font-bold tracking-tight">Reaction project at a glance</h2>
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
                  style={{ color: "var(--mt-violet-ink)" }}
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
                  style={{ color: "var(--mt-violet-ink)" }}
                >
                  {loading ? "…" : experimentCount}
                </p>
                <p className="mt-2 text-xs text-muted-foreground">From recorded experiments</p>
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
                    <Badge variant="outline">{latestRec.status ? statusLabel(latestRec.status) : ""}</Badge>
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
            description="Experiments with a linked SpectraCheck session, and their evidence record counts."
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
              className="font-mono text-[11px] font-bold uppercase tracking-[0.2em]"
              style={{ color: "var(--mt-violet-ink)" }}
            >
              Project · Variables
            </p>
            <h2 className="font-mono text-2xl font-bold tracking-tight">Optimization variable definitions</h2>
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
                        <TableCell className="text-xs">{variableTypeLabel(v.variable_type)}</TableCell>
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
            title={
              <span className="inline-flex items-center gap-2">
                add variable
                <InfoTooltip content={ADD_VARIABLE_TOOLTIP} label="Where a variable applies" />
              </span>
            }
            description="Define a new reaction variable for this project."
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
                      {/* Labels are display-only; value= stays byte-identical (sent to the server). */}
                      <SelectItem value="categorical">Categorical</SelectItem>
                      <SelectItem value="numeric">Numeric</SelectItem>
                      <SelectItem value="boolean">Yes / no</SelectItem>
                      <SelectItem value="text">Free text</SelectItem>
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
              className="font-mono text-[11px] font-bold uppercase tracking-[0.2em]"
              style={{ color: "var(--mt-violet-ink)" }}
            >
              Project · Experiments
            </p>
            <h2 className="font-mono text-2xl font-bold tracking-tight">Experiment matrix &amp; outcomes</h2>
            <p className="text-sm text-muted-foreground">
              All experiments in this project — variable values, outcomes, and SpectraCheck-linked analytical results.
            </p>
          </div>
          <ModuleCard
            accent="violet"
            eyebrow="Reaction · Experiment Matrix"
            title={
              <span className="inline-flex items-center gap-2">
                experiment matrix
                <InfoTooltip content={EXPERIMENT_MATRIX_TOOLTIP} label="What each row records" />
              </span>
            }
            description="Every experiment run in this project, one row each."
          >
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Experiment code</TableHead>
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
                    <TableHead className="text-right text-xs">Green score</TableHead>
                    <TableHead className="text-xs">pareto</TableHead>
                    <TableHead className="font-mono text-xs">Linked SpectraCheck session</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">Updated</TableHead>
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
                    const greenScore = readOutcomeNumber(e, "green_score")
                    const linked = readNum(e.linked_spectracheck_session_id)
                    return (
                      <TableRow key={String(e.id)}>
                        <TableCell className="font-mono text-xs">{String(e.experiment_code ?? "")}</TableCell>
                        <TableCell>
                          <StatusBadge status={e.status} />
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
                        <TableCell className="text-right font-mono text-xs tabular-nums">
                          {greenScore != null ? greenScore.toLocaleString(undefined, { maximumFractionDigits: 1 }) : "—"}
                        </TableCell>
                        <TableCell>
                          {eid != null && eid === paretoKneeId ? (
                            <Badge
                              variant="secondary"
                              className="whitespace-nowrap text-xs"
                              style={{ backgroundColor: "var(--mt-amber-soft)", color: "var(--mt-amber)" }}
                            >
                              knee
                            </Badge>
                          ) : eid != null && paretoNonDominatedIds.has(eid) ? (
                            <Badge
                              variant="secondary"
                              className="text-xs"
                              style={{ backgroundColor: "var(--mt-violet-soft)", color: "var(--mt-violet-ink)" }}
                            >
                              Pareto
                            </Badge>
                          ) : (
                            <span className="text-xs text-muted-foreground">—</span>
                          )}
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
                        colSpan={11 + conditionColumnKeys.length}
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
            title={
              <span className="inline-flex items-center gap-2">
                SpectraCheck evidence summary
                <InfoTooltip content={EVIDENCE_SUMMARY_TOOLTIP} label="What this summary shows" />
              </span>
            }
            description="Analytical evidence for experiments with a linked SpectraCheck session."
          >
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Experiment code</TableHead>
                    <TableHead className="text-xs">Linked SpectraCheck session</TableHead>
                    <TableHead className="text-xs">Sample ID</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">unified status</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">report status</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">QC status</TableHead>
                    <TableHead className="text-right text-xs">Evidence records</TableHead>
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
                    <Label htmlFor="ex-code">Experiment code</Label>
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
                  <p className="text-sm font-medium">Conditions</p>
                  <p className="text-xs text-muted-foreground">
                    Fields come from the project variables. Leave blank to omit a key.
                  </p>
                  {variableRecords.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No reaction variables yet — add variables first, or save with no conditions set.
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
                  <p className="text-sm font-medium">Outcome</p>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    <div className="space-y-2">
                      <Label htmlFor="ex-yield">Yield (%)</Label>
                      <Input
                        id="ex-yield"
                        inputMode="decimal"
                        value={expYield}
                        onChange={(e) => setExpYield(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="ex-conv">Conversion (%)</Label>
                      <Input
                        id="ex-conv"
                        inputMode="decimal"
                        value={expConversion}
                        onChange={(e) => setExpConversion(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="ex-sel">Selectivity (%)</Label>
                      <Input
                        id="ex-sel"
                        inputMode="decimal"
                        value={expSelectivity}
                        onChange={(e) => setExpSelectivity(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="ex-imp">Impurity (%)</Label>
                      <Input
                        id="ex-imp"
                        inputMode="decimal"
                        value={expImpurity}
                        onChange={(e) => setExpImpurity(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="ex-iso">Isolated yield (%)</Label>
                      <Input
                        id="ex-iso"
                        inputMode="decimal"
                        value={expIsolatedYield}
                        onChange={(e) => setExpIsolatedYield(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="ex-lcms">LC-MS area (%)</Label>
                      <Input
                        id="ex-lcms"
                        inputMode="decimal"
                        value={expLcmsArea}
                        onChange={(e) => setExpLcmsArea(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="ex-nmr">NMR purity (%)</Label>
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
                  <Label htmlFor="ex-sc">Linked SpectraCheck session</Label>
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
              className="font-mono text-[11px] font-bold uppercase tracking-[0.2em]"
              style={{ color: "var(--mt-violet-ink)" }}
            >
              Project · Objective
            </p>
            <h2 className="font-mono text-2xl font-bold tracking-tight">Optimization objective &amp; weights</h2>
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
            description="Set the target this project optimizes toward."
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
                          {optionLabel(opt)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-3">
                  <p className="text-sm font-medium">Weights</p>
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
                    <div className="space-y-2">
                      <Label htmlFor="w-efactor">E-factor</Label>
                      <Input
                        id="w-efactor"
                        inputMode="decimal"
                        value={weightEFactor}
                        onChange={(e) => setWeightEFactor(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="w-ae">atom economy</Label>
                      <Input
                        id="w-ae"
                        inputMode="decimal"
                        value={weightAtomEconomy}
                        onChange={(e) => setWeightAtomEconomy(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="w-green">green score</Label>
                      <Input
                        id="w-green"
                        inputMode="decimal"
                        value={weightGreenScore}
                        onChange={(e) => setWeightGreenScore(e.target.value)}
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

                <JsonObjectField
                  key={`hard-constraints-${objectiveFormKey}`}
                  label="Hard constraints"
                  initialValue={hardConstraints}
                  onChange={setHardConstraints}
                  description="Conditions a candidate must satisfy (name/value pairs). Advanced — leave empty for none."
                  idPrefix="hard-constraints"
                />
                <JsonObjectField
                  key={`soft-constraints-${objectiveFormKey}`}
                  label="Soft constraints"
                  initialValue={softConstraints}
                  onChange={setSoftConstraints}
                  description="Preferences that penalize but don't exclude a candidate. Advanced — leave empty for none."
                  idPrefix="soft-constraints"
                />

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
          <ReactionRegulatoryCompliancePanel reactionProjectId={reactionProjectId} />
        </TabsContent>

        <TabsContent value="cost-safety" className="mt-4 space-y-6">
          <div className="space-y-1">
            <p
              className="font-mono text-[11px] font-bold uppercase tracking-[0.2em]"
              style={{ color: "var(--mt-violet-ink)" }}
            >
              Project · Cost &amp; Safety
            </p>
            <h2 className="font-mono text-2xl font-bold tracking-tight">Cost profile &amp; safety constraints</h2>
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
                <KeyNumberTableField
                  key={`reagent-costs-${costFormKey}`}
                  label="Reagent costs"
                  keyLabel="Reagent"
                  valueLabel="Cost"
                  unit="cost/unit"
                  addLabel="Add reagent"
                  initialValue={reagentCosts}
                  onChange={setReagentCosts}
                  suggestions={categoricalSuggestions}
                  suggestionsHint="Suggestions come from this project's design-space choices."
                  idPrefix="cp-reagent-costs"
                />
                <KeyNumberTableField
                  key={`solvent-costs-${costFormKey}`}
                  label="Solvent costs"
                  keyLabel="Solvent"
                  valueLabel="Cost"
                  unit="cost/unit"
                  addLabel="Add solvent"
                  initialValue={solventCosts}
                  onChange={setSolventCosts}
                  suggestions={categoricalSuggestions}
                  suggestionsHint="Suggestions come from this project's design-space choices."
                  idPrefix="cp-solvent-costs"
                />
                <KeyNumberTableField
                  key={`catalyst-costs-${costFormKey}`}
                  label="Catalyst costs"
                  keyLabel="Catalyst"
                  valueLabel="Cost"
                  unit="cost/unit"
                  addLabel="Add catalyst"
                  initialValue={catalystCosts}
                  onChange={setCatalystCosts}
                  suggestions={categoricalSuggestions}
                  suggestionsHint="Suggestions come from this project's design-space choices."
                  idPrefix="cp-catalyst-costs"
                />
                <KeyNumberTableField
                  key={`ligand-costs-${costFormKey}`}
                  label="Ligand costs"
                  keyLabel="Ligand"
                  valueLabel="Cost"
                  unit="cost/unit"
                  addLabel="Add ligand"
                  initialValue={ligandCosts}
                  onChange={setLigandCosts}
                  suggestions={categoricalSuggestions}
                  suggestionsHint="Suggestions come from this project's design-space choices."
                  idPrefix="cp-ligand-costs"
                />
                <div className="space-y-2">
                  <Label htmlFor="cp-availability">Availability notes</Label>
                  <Textarea
                    id="cp-availability"
                    rows={3}
                    value={availabilityNotes}
                    onChange={(e) => setAvailabilityNotes(e.target.value)}
                  />
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="cp-max-cost">Max cost per experiment</Label>
                    <Input
                      id="cp-max-cost"
                      inputMode="decimal"
                      value={maxCostPerExperiment}
                      onChange={(e) => setMaxCostPerExperiment(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="cp-penalty-weight">Cost penalty weight</Label>
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
                <StringListField
                  key={`blocked-reagents-${safetyFormKey}`}
                  label="Blocked reagents"
                  itemLabel="Reagent"
                  addLabel="Add blocked reagent"
                  initialValue={blockedReagents}
                  onChange={setBlockedReagents}
                  suggestions={categoricalSuggestions}
                  suggestionsHint="Suggestions come from this project's design-space choices."
                  description="Candidate conditions using any blocked reagent are filtered out before scoring."
                  idPrefix="sp-blocked-reagents"
                />
                <StringListField
                  key={`blocked-solvents-${safetyFormKey}`}
                  label="Blocked solvents"
                  itemLabel="Solvent"
                  addLabel="Add blocked solvent"
                  initialValue={blockedSolvents}
                  onChange={setBlockedSolvents}
                  suggestions={categoricalSuggestions}
                  suggestionsHint="Suggestions come from this project's design-space choices."
                  description="Candidate conditions using any blocked solvent are filtered out before scoring."
                  idPrefix="sp-blocked-solvents"
                />
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="sp-max-temp">Max temperature (°C)</Label>
                    <p className="text-xs text-muted-foreground">Maximum temperature (°C).</p>
                    <Input
                      id="sp-max-temp"
                      inputMode="decimal"
                      value={maxTemperatureC}
                      onChange={(e) => setMaxTemperatureC(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="sp-max-pressure">Max pressure (bar)</Label>
                    <p className="text-xs text-muted-foreground">Maximum pressure (bar).</p>
                    <Input
                      id="sp-max-pressure"
                      inputMode="decimal"
                      value={maxPressureBar}
                      onChange={(e) => setMaxPressureBar(e.target.value)}
                    />
                  </div>
                </div>
                <PairListField
                  key={`incompatible-pairs-${safetyFormKey}`}
                  label="Incompatible pairs"
                  leftLabel="Component A"
                  rightLabel="Component B"
                  addLabel="Add incompatible pair"
                  initialValue={incompatiblePairs}
                  onChange={setIncompatiblePairs}
                  suggestions={categoricalSuggestions}
                  suggestionsHint="Suggestions come from this project's design-space choices."
                  description="Conditions containing both components of a pair are filtered out before scoring."
                  idPrefix="sp-incompatible"
                />
                <StringListField
                  key={`required-controls-${safetyFormKey}`}
                  label="Required controls"
                  itemLabel="Control"
                  itemPlaceholder="e.g. blast shield, slow addition"
                  addLabel="Add required control"
                  initialValue={requiredControls}
                  onChange={setRequiredControls}
                  description="Operational controls a chemist must confirm before running flagged chemistry."
                  idPrefix="sp-controls"
                />
                <div className="space-y-2">
                  <Label htmlFor="sp-notes">Safety notes</Label>
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

          <div id="reaction-safety-gate" tabIndex={-1} className="scroll-mt-4 outline-none">
            <SafetyScreeningPanel
              projectId={reactionProjectId}
              productSmilesHint={typeof project?.target_product_smiles === "string" ? project.target_product_smiles : null}
            />
          </div>

          <ForwardCheckPanel key={reactionProjectId} projectId={reactionProjectId} />
        </TabsContent>

        <TabsContent value="green" className="mt-4 space-y-6">
          <GreenMetricsPanel projectId={reactionProjectId} experiments={experimentsRec} />
        </TabsContent>

        <TabsContent value="plates" className="mt-4 space-y-6">
          <PlateDesignPanel projectId={reactionProjectId} variables={variableRecords} />
        </TabsContent>

        <TabsContent value="routes" className="mt-4 space-y-6">
          <div className="space-y-1">
            <p
              className="font-mono text-[11px] font-bold uppercase tracking-[0.2em]"
              style={{ color: "var(--mt-violet-ink)" }}
            >
              Project · Routes
            </p>
            <h2 className="font-mono text-2xl font-bold tracking-tight">Synthesis route scoring</h2>
            <p className="text-sm text-muted-foreground">
              Score pasted or hand-built route trees with the frozen safety and green-chemistry
              engines. Route generation is not available on this deployment; routes are entered manually by
              design.
            </p>
          </div>
          <RouteScoresPanel key={reactionProjectId} projectId={reactionProjectId} />

          {/* The drawing canvas belongs on a page that knows which project it is
              looking at. Its first home was the program-level demo workspace,
              where a captured scheme had no entity to belong to — so it sits
              here too, carrying the project it was drawn for. */}
          <section aria-labelledby="route-scheme-heading" className="space-y-3 border-t pt-6">
            <div className="space-y-1">
              <p
                className="font-mono text-[11px] font-bold uppercase tracking-[0.2em]"
                style={{ color: "var(--mt-violet-ink)" }}
              >
                Project · Scheme
              </p>
              <h2 id="route-scheme-heading" className="font-mono text-2xl font-bold tracking-tight">
                Draw or import a scheme
              </h2>
              <p className="text-sm text-muted-foreground">
                Sketch a route step, or bring in a structure or reaction you already have, and
                capture it as a molfile or reaction block.
              </p>
            </div>
            <StructureEditorPanel contextLabel={`Project ${reactionProjectId}`} />
          </section>
        </TabsContent>

        <TabsContent value="optimization" className="mt-4 space-y-6">
          <div className="space-y-1">
            <p
              className="font-mono text-[11px] font-bold uppercase tracking-[0.2em]"
              style={{ color: "var(--mt-violet-ink)" }}
            >
              Project · Optimization
            </p>
            <h2 className="font-mono text-2xl font-bold tracking-tight">Bayesian optimization &amp; benchmark runs</h2>
            <p className="text-sm text-muted-foreground">
              Launch optimization cycles with regulatory constraints, compare BO vs LLM advisors, and inspect benchmark history.
            </p>
          </div>

          <ModuleCard
            accent="violet"
            eyebrow="Optimization · Warm-start"
            title={
              <span className="inline-flex items-center gap-2">
                Warm-start from related campaigns
                <InfoTooltip content={WARM_START_TOOLTIP} label="How the warm-start prior is fitted" />
              </span>
            }
            description="Reach the target in fewer experiments by reusing past campaigns. Advisory — it never overrides the optimiser. Fits only from owned, SpectraCheck-verified data — never the frozen evaluation gold set."
          >
            <form className="space-y-4" onSubmit={(e) => void buildWarmStartPrior(e)}>
              <div className="space-y-2">
                <span id="ws-sources-label" className="text-xs font-medium">
                  source campaigns (owned)
                </span>
                <div className="flex flex-wrap gap-2" role="group" aria-labelledby="ws-sources-label">
                  {wsProjectsStatus === "loading" ? (
                    <span className="text-xs text-muted-foreground">Loading your campaigns…</span>
                  ) : wsProjectsStatus === "error" ? (
                    <span className="flex items-center gap-2 text-xs text-muted-foreground">
                      Couldn&apos;t load your campaigns.
                      <button
                        type="button"
                        className={INLINE_LINK_BUTTON_CLASS}
                        onClick={() => void loadOwnedReactionProjects()}
                      >
                        Retry
                      </button>
                    </span>
                  ) : ownedReactionProjects.length === 0 ? (
                    <span className="text-xs text-muted-foreground">
                      No campaigns found — this campaign is still used as the default source.
                    </span>
                  ) : (
                    ownedReactionProjects.map((p) => {
                      const pid = readNum(p.id)
                      if (pid == null) return null
                      const isSelf = pid === reactionProjectId
                      const selected = wsSourceIds.includes(pid)
                      return (
                        <Button
                          key={pid}
                          type="button"
                          size="sm"
                          aria-pressed={selected}
                          variant={selected ? "default" : "outline"}
                          className="h-8 text-xs"
                          onClick={() =>
                            setWsSourceIds((prev) =>
                              prev.includes(pid) ? prev.filter((x) => x !== pid) : [...prev, pid],
                            )
                          }
                        >
                          {String(p.name ?? `project ${pid}`)}
                          {isSelf ? " (this campaign)" : ""}
                        </Button>
                      )
                    })
                  )}
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Defaults to this campaign (intra-campaign warm-start). Add related campaigns you own
                  for transfer learning; a campaign you don&apos;t own is rejected.
                </p>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label htmlFor="ws-target" className="text-xs">Objective target (optional)</Label>
                  <Input
                    id="ws-target"
                    className="h-8 text-xs"
                    inputMode="decimal"
                    value={wsObjectiveTarget}
                    onChange={(e) => setWsObjectiveTarget(e.target.value)}
                    placeholder="e.g. 95"
                  />
                  {wsObjectiveTarget.trim() !== "" && !Number.isFinite(Number(wsObjectiveTarget)) ? (
                    <p className="text-[11px] text-destructive">Enter a number (or leave it blank).</p>
                  ) : null}
                </div>
                <div className="flex items-center gap-2 pt-5">
                  <Switch id="ws-verified" checked={wsRequireVerified} onCheckedChange={setWsRequireVerified} />
                  <Label htmlFor="ws-verified" className="text-xs">require verified data only</Label>
                </div>
              </div>
              {!wsRequireVerified ? (
                <div
                  role="status"
                  className="rounded-md border bg-muted/30 px-3 py-2 text-xs"
                  style={{ borderLeft: "3px solid var(--mt-amber)" }}
                >
                  <p className="font-medium text-foreground">Preview mode — fitting on unconfirmed data.</p>
                  <p className="text-muted-foreground">
                    A prior for real use should admit only SpectraCheck-verified / reviewer-confirmed
                    outcomes.
                  </p>
                </div>
              ) : null}
              <Button type="submit" size="sm" disabled={busy != null || wsSourceIds.length === 0}>
                {busy === "ws-build" ? "Building…" : "Build warm-start prior"}
              </Button>
            </form>
            {(() => {
              const p = reactionWarmStartPriorView(warmStartPrior)
              if (p == null) {
                return wsPriorLoadFailed ? (
                  <p className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
                    Couldn&apos;t load the warm-start prior — this is a load failure, not proof none
                    exists.
                    <button
                      type="button"
                      className={INLINE_LINK_BUTTON_CLASS}
                      onClick={() => void loadWarmStartPrior()}
                    >
                      Retry
                    </button>
                  </p>
                ) : (
                  <p className="mt-4 text-sm text-muted-foreground">
                    No warm-start prior yet — build one from your verified campaigns above.
                  </p>
                )
              }
              return (
                <div className="mt-4 space-y-3 rounded-md border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium text-foreground">Fitted prior · lineage</p>
                    <Badge variant="secondary" className="text-xs">advisory</Badge>
                    {!p.verifiedOnly ? (
                      <Badge variant="destructive" className="text-xs">
                        preview — unverified data admitted
                      </Badge>
                    ) : null}
                    {p.snapshotHash ? (
                      <Badge variant="outline" className="font-mono text-[11px]">
                        snapshot {p.snapshotHash.slice(0, 12)}…
                      </Badge>
                    ) : null}
                  </div>
                  {!p.verifiedOnly ? (
                    <p
                      className="rounded-md border bg-muted/30 px-3 py-2 text-xs font-medium text-foreground"
                      style={{ borderLeft: "3px solid var(--mt-amber)" }}
                    >
                      This prior was fit in preview mode with unconfirmed data admitted — rebuild with
                      “require verified data only” before using it to guide real experiments.
                    </p>
                  ) : null}
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
                    {[
                      { label: "Training observations", value: p.trainedN },
                      { label: "excluded · gold", value: p.excludedGoldCount },
                      { label: "excluded · unverified", value: p.excludedUnverifiedCount },
                      { label: "augmentation", value: p.augmentationCount },
                      { label: "Objective target", value: p.objectiveTarget },
                    ].map((m) => (
                      <div key={m.label} className="rounded-md border px-2 py-1.5">
                        <p className="font-mono text-sm tabular-nums">{m.value != null ? m.value : "—"}</p>
                        <p className="text-[10px] text-muted-foreground">{m.label}</p>
                      </div>
                    ))}
                  </div>
                  {p.sourceProjectIds.length > 0 ? (
                    <p className="text-[11px] text-muted-foreground">
                      source campaigns:{" "}
                      <span className="font-mono text-foreground">{p.sourceProjectIds.join(", ")}</span>
                    </p>
                  ) : null}
                  {/* The verbatim disclaimer asserts a verified-only fit — true only for a
                      non-preview prior; for a preview fit the amber note above states the truth. */}
                  {p.disclaimer && p.verifiedOnly ? (
                    <p className="text-[11px] italic text-muted-foreground">{p.disclaimer}</p>
                  ) : null}
                </div>
              )
            })()}
          </ModuleCard>

          <YieldPredictionPanel key={reactionProjectId} projectId={reactionProjectId} variables={variableRecords} />

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
                  Model type: rule-based
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
                        {optionLabel(opt)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="bo-batch">Batch size</Label>
                  <Input
                    id="bo-batch"
                    inputMode="numeric"
                    min={1}
                    value={boBatchSize}
                    onChange={(e) => setBoBatchSize(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="bo-explore">Exploration weight</Label>
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
                    Cost-aware
                  </Label>
                  <Switch
                    id="bo-cost-aware"
                    checked={boCostAware}
                    onCheckedChange={(c) => setBoCostAware(Boolean(c))}
                  />
                </div>
                <div className="flex items-center justify-between gap-4">
                  <Label htmlFor="bo-safety-aware" className="font-mono text-xs">
                    Safety-aware
                  </Label>
                  <Switch
                    id="bo-safety-aware"
                    checked={boSafetyAware}
                    onCheckedChange={(c) => setBoSafetyAware(Boolean(c))}
                  />
                </div>
                <div className="flex items-center justify-between gap-4">
                  <Label htmlFor="bo-failed-neg" className="text-xs leading-snug">
                    Include failed experiments as negatives
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
              title={
                <span className="inline-flex items-center gap-2">
                  latest Bayesian optimization run
                  <InfoTooltip content={LATEST_BO_RUN_TOOLTIP} label="What the run summary reports" />
                </span>
              }
              description="Summary of the most recent Bayesian optimization run."
            >
              <div className="space-y-4">
                {isRecord(lastBoRun) ? (
                  <>
                    {String(lastBoRun.status ?? "").toLowerCase() === "insufficient_data" ? (
                      <Alert>
                        <AlertTitle className="text-sm">Insufficient data</AlertTitle>
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
                        Algorithm: {optionLabel(typeof lastBoRun.algorithm === "string" ? lastBoRun.algorithm : null)}
                      </Badge>
                      <Badge variant="outline" className="font-mono text-xs">
                        Model type: {String(lastBoRun.model_type ?? "—")}
                      </Badge>
                      <Badge variant="outline" className="tabular-nums text-xs">
                        Input experiment count: {String(lastBoRun.input_experiment_count ?? "—")}
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
                <DeveloperOnly>
                  <Collapsible className="rounded-md border border-border">
                    <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm font-medium hover:bg-muted/50">
                      Developer JSON
                      <ChevronDown className="h-4 w-4 shrink-0 opacity-70" />
                    </CollapsibleTrigger>
                    <CollapsibleContent className="border-t border-border px-3 py-3">
                      <DeveloperJsonPanel data={lastBoRun} />
                    </CollapsibleContent>
                  </Collapsible>
                </DeveloperOnly>
              </div>
            </ModuleCard>
          ) : (
            <p className="text-sm text-muted-foreground">
              After you run Bayesian optimization, this panel shows the run ID, algorithm, model, status, warnings,
              notes, and diagnostics from the latest run.
            </p>
          )}

          {paretoFront != null ? <ParetoFrontPanel front={paretoFront} trend={paretoTrend} /> : null}

          {lastOptimizationRun != null ? (
            <ModuleCard
              accent="violet"
              eyebrow="Optimization · Latest Run"
              title="latest optimization run"
              description="Status, model, experiment count, metrics, recommendations, warnings, and notes from the latest run."
            >
              <div className="space-y-4">
                {isRecord(lastOptimizationRun) ? (
                  <>
                    <div className="flex flex-wrap gap-2 text-sm">
                      <Badge variant="outline">status: {String(lastOptimizationRun.status ?? "—")}</Badge>
                      <Badge variant="outline" className="font-mono">
                        Model type: {String(lastOptimizationRun.model_type ?? "—")}
                      </Badge>
                      <Badge variant="outline" className="tabular-nums">
                        Input experiment count: {String(lastOptimizationRun.input_experiment_count ?? "—")}
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
                          <p className="text-sm font-medium">Metrics</p>
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
                          Recommendations returned {n} row{n === 1 ? "" : "s"} — see the Recommendations tab to review
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
              After you run optimization, this panel shows run status, metrics, and recommendation counts from
              the latest run.
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
            description="Replay optimization algorithms over this project's past experiments. Results compare relative algorithm behavior on this dataset only — not universal superiority."
          >
            <div className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="bench-name">Benchmark name</Label>
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
                          {optionLabel(opt)}
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
                          {optionLabel(opt)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="bench-budget">Experiment budget</Label>
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
                    Random seed <span className="font-normal text-muted-foreground">(optional)</span>
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
                    Use completed project data
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
                              <TableHead className="text-xs">Recorded values</TableHead>
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
                  After a benchmark run finishes, this section shows best observed objective, regret if returned,
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
                    <TableHead className="font-mono text-xs">Benchmark name</TableHead>
                    <TableHead className="font-mono text-xs">algorithm</TableHead>
                    <TableHead>Created</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {benchmarkRuns.filter(isRecord).map((r, ri) => (
                    <TableRow key={String(r.id ?? `bench-${ri}`)}>
                      <TableCell className="font-mono text-xs">{String(r.id ?? "—")}</TableCell>
                      <TableCell>{String(r.status ?? "")}</TableCell>
                      <TableCell className="max-w-[140px] truncate text-xs">{String(r.benchmark_name ?? "—")}</TableCell>
                      <TableCell className="text-xs">{optionLabel(typeof r.algorithm === "string" ? r.algorithm : null)}</TableCell>
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
                    <TableHead>Model type</TableHead>
                    <TableHead className="text-right">Input experiment count</TableHead>
                    <TableHead>Created</TableHead>
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
              className="font-mono text-[11px] font-bold uppercase tracking-[0.2em]"
              style={{ color: "var(--mt-violet-ink)" }}
            >
              Project · Optimization Advisor
            </p>
            <h2 className="font-mono text-2xl font-bold tracking-tight">LLM-assisted optimization advisor</h2>
            <p className="text-sm text-muted-foreground">
              Run the LLM advisor against literature priors and mechanistic hypotheses; inspect rationale and side-by-side BO comparisons.
            </p>
          </div>
          <ModuleCard
            accent="violet"
            eyebrow="Advisor · Run"
            title={
              <span className="inline-flex items-center gap-2">
                Optimization Advisor
                <InfoTooltip content={ADVISOR_RUN_TOOLTIP} label="What the advisor reads" />
              </span>
            }
            description="Flags which next experiments to prioritise. All recommendations require human review."
          >
            <div className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2">
                {boRuns.filter(isRecord).length > 0 ? (
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="adv-bo-run">BO run</Label>
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
                              {typeof row.algorithm === "string" ? `· ${optionLabel(row.algorithm)}` : ""} · {fmtIso(row.created_at)}
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
                    <Label htmlFor="adv-batch">Recommendation batch</Label>
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
                  <Label htmlFor="adv-mode">Advisor mode</Label>
                  <Select value={advisorMode} onValueChange={setAdvisorMode}>
                    <SelectTrigger id="adv-mode">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ADVISOR_MODE_OPTIONS.map((m) => (
                        <SelectItem key={m} value={m}>
                          {optionLabel(m)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-3 md:col-span-2">
                  <Label htmlFor="adv-cost-safety" className="font-mono text-xs">
                    Include cost &amp; safety context
                  </Label>
                  <Switch
                    id="adv-cost-safety"
                    checked={advIncludeCostSafety}
                    onCheckedChange={(c) => setAdvIncludeCostSafety(Boolean(c))}
                  />
                </div>
                <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-3 md:col-span-2">
                  <Label htmlFor="adv-completed" className="font-mono text-xs">
                    Include completed experiments
                  </Label>
                  <Switch
                    id="adv-completed"
                    checked={advIncludeCompletedExperiments}
                    onCheckedChange={(c) => setAdvIncludeCompletedExperiments(Boolean(c))}
                  />
                </div>
                <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-3 md:col-span-2">
                  <Label htmlFor="adv-lit" className="font-mono text-xs">
                    Include literature priors
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
                  <p className="text-xs text-muted-foreground">Optional — saved with the run when provided.</p>
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
                        <TableHead className="text-xs">Advisor run ID</TableHead>
                        <TableHead className="text-xs">status</TableHead>
                        <TableHead className="text-xs">Advisor mode</TableHead>
                        <TableHead className="text-xs">Created</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {advisorRunsList.filter(isRecord).map((row, ri) => (
                        <TableRow key={String(row.id ?? row.advisor_run_id ?? ri)}>
                          <TableCell className="font-mono text-xs">
                            {String(readNum(row.advisor_run_id ?? row.id) ?? "—")}
                          </TableCell>
                          <TableCell className="text-xs">{String(row.status ?? "")}</TableCell>
                          <TableCell className="text-xs">{optionLabel(typeof row.advisor_mode === "string" ? row.advisor_mode : null)}</TableCell>
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
                      Advisor mode: {optionLabel(typeof lastAdvisorRun.advisor_mode === "string" ? lastAdvisorRun.advisor_mode : null)}
                    </Badge>
                    <Badge variant="outline" className="text-xs">
                      status: {String(lastAdvisorRun.status ?? "—")}
                    </Badge>
                    <Badge variant="outline" className="tabular-nums text-xs">
                      Recommendation count:{" "}
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
                      Human review required: {flagLabel(lastAdvisorRun.human_review_required)}
                    </Badge>
                  </div>

                  <MlModelProvenanceSummary
                    sources={[lastAdvisorRun]}
                    className="rounded-md border border-dashed px-3 py-2"
                  />

                  {(() => {
                    const agent = advisorAgentFromRun(lastAdvisorRun)
                    if (agent == null) return null
                    return (
                      <section
                        className="space-y-3 rounded-md border bg-muted/20 p-3"
                        style={{ borderLeft: "3px solid var(--mt-violet)" }}
                        aria-label="Reaction agent"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-medium text-foreground">Reaction agent</p>
                          {agent.engine ? (
                            <Badge variant="outline" className="font-mono text-[11px]">
                              {agent.engine}
                            </Badge>
                          ) : null}
                          {agent.isFallback ? (
                            <Badge variant="secondary" className="text-[11px]">
                              deterministic · no LLM
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="font-mono text-[11px]">
                              model: {agent.modelVersion}
                            </Badge>
                          )}
                          {agent.stopReason ? (
                            <Badge variant="outline" className="text-[11px]">
                              stop: {agent.stopReason.replace(/_/g, " ")}
                            </Badge>
                          ) : null}
                        </div>

                        {agent.isFallback ? (
                          <Alert>
                            <AlertTitle className="text-sm">Deterministic plan (no LLM)</AlertTitle>
                            <AlertDescription className="text-xs">
                              No Anthropic key / agent flag in play — this plan is the rule-based fallback,
                              not a model-guided one. Treat it as the baseline deterministic critique.
                            </AlertDescription>
                          </Alert>
                        ) : null}

                        {/* §4.3 safety pre-check banner */}
                        {agent.safetyStatus || agent.executionBlocked ? (
                          <div
                            className="space-y-1 rounded-md border px-3 py-2 text-xs"
                            style={{
                              borderLeft: `3px solid ${
                                agent.executionBlocked || agent.safetyStatus === "blocked"
                                  ? "var(--mt-amber)"
                                  : "var(--mt-teal)"
                              }`,
                            }}
                          >
                            <p className="font-medium text-foreground">
                              Safety pre-check:{" "}
                              <span className="font-mono">
                                {(agent.safetyStatus ?? "unknown").replace(/_/g, " ")}
                              </span>
                            </p>
                            {agent.safetyPrecheck != null &&
                            typeof agent.safetyPrecheck.summary === "string" ? (
                              <p className="text-muted-foreground">{agent.safetyPrecheck.summary}</p>
                            ) : null}
                            {agent.executionBlocked ? (
                              <p className="font-medium text-foreground">
                                The agent refused the action tools — resolve the blocking structural-safety
                                screening before any proposed batch can proceed.{" "}
                                <button
                                  type="button"
                                  className={INLINE_LINK_BUTTON_CLASS}
                                  onClick={goToSafetyGate}
                                >
                                  Open the safety gate (Cost &amp; Safety) →
                                </button>
                              </p>
                            ) : null}
                          </div>
                        ) : null}

                        {/* §4.1 plan panel — model prose, explicitly NOT the source of numbers */}
                        {agent.narrative || agent.plan.length > 0 ? (
                          <div className="space-y-2">
                            <div className="flex items-center gap-2">
                              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                                agent plan
                              </p>
                              <Badge variant="outline" className="text-[10px]">
                                model prose — not a source of numbers
                              </Badge>
                            </div>
                            {agent.narrative ? (
                              <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                                {agent.narrative}
                              </p>
                            ) : null}
                            {agent.plan.length > 0 ? (
                              <ol className="list-inside list-decimal space-y-1 text-sm text-muted-foreground">
                                {agent.plan.map((step, i) => (
                                  <li key={`agent-plan-${i}`}>{step}</li>
                                ))}
                              </ol>
                            ) : null}
                            <p className="text-[11px] text-muted-foreground">
                              Decision support only — the agent re-ranks and explains; the chemist decides.
                              It schedules nothing.{" "}
                              {agent.toolCalls.length > 0
                                ? "Any figure in the prose is a citation to a tool call below, not a computed value."
                                : "No grounded tool outputs were recorded for this run — treat any figure in the prose as uncited."}
                            </p>
                          </div>
                        ) : null}

                        {/* §4.2 tool-call provenance — the ONLY source of quantitative truth */}
                        {agent.toolCalls.length > 0 ? (
                          <div className="space-y-2">
                            <div className="flex items-center gap-2">
                              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                                tool-call provenance
                              </p>
                              <Badge variant="secondary" className="text-[10px]">
                                grounded — every number comes from here
                              </Badge>
                            </div>
                            <div className="space-y-2">
                              {agent.toolCalls.map((tc, i) => {
                                const name = typeof tc.name === "string" ? tc.name : "tool"
                                const isErr = tc.is_error === true
                                return (
                                  <div
                                    key={`agent-tc-${i}-${name}`}
                                    className="space-y-1 rounded-md border px-3 py-2"
                                  >
                                    <div className="flex flex-wrap items-center gap-2">
                                      <Badge
                                        variant={isErr ? "destructive" : "outline"}
                                        className="font-mono text-[11px]"
                                      >
                                        {name}
                                      </Badge>
                                      <span className="text-[10px] text-muted-foreground">
                                        {isErr ? "tool error" : "source: tool"}
                                      </span>
                                    </div>
                                    {isRecord(tc.arguments) && Object.keys(tc.arguments).length > 0 ? (
                                      <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-words rounded bg-muted/40 p-2 text-[10px] leading-snug">
                                        args: {jsonPreview(tc.arguments, 2000)}
                                      </pre>
                                    ) : null}
                                    {tc.output != null ? (
                                      <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-muted/40 p-2 text-[10px] leading-snug">
                                        {jsonPreview(tc.output, 6000)}
                                      </pre>
                                    ) : null}
                                  </div>
                                )
                              })}
                            </div>
                          </div>
                        ) : null}

                        {agent.warnings.length > 0 ? (
                          <div className="space-y-1">
                            <p className="text-xs font-medium text-muted-foreground">agent warnings</p>
                            <ul className="list-inside list-disc text-xs text-muted-foreground">
                              {agent.warnings.map((w, i) => (
                                <li key={`agent-w-${i}-${w.slice(0, 24)}`}>{w}</li>
                              ))}
                            </ul>
                          </div>
                        ) : null}

                        {agent.disclaimer ? (
                          <p className="rounded-md bg-muted/40 px-3 py-2 text-[11px] italic text-muted-foreground">
                            {agent.disclaimer}
                          </p>
                        ) : null}

                        {/* §4.5 always-review */}
                        <p className="text-[11px] font-medium text-foreground">
                          Human review required — the agent schedules nothing; a chemist signs off on any
                          next step.
                        </p>
                      </section>
                    )
                  })()}

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

                  <DeveloperOnly>
                    <Collapsible className="rounded-md border border-border">
                      <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm font-medium hover:bg-muted/50">
                        Developer JSON
                        <ChevronDown className="h-4 w-4 shrink-0 opacity-70" />
                      </CollapsibleTrigger>
                      <CollapsibleContent className="border-t border-border px-3 py-3">
                        <DeveloperJsonPanel data={lastAdvisorRun} />
                      </CollapsibleContent>
                    </Collapsible>
                  </DeveloperOnly>
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
                    <Label htmlFor="mh-confidence">Confidence label</Label>
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
                  <div className="md:col-span-2">
                    <ObjectArrayField
                      key={`mh-supporting-${mhFormKey}`}
                      label="Supporting observations"
                      itemLabel="Observation"
                      addLabel="Add observation"
                      fields={[
                        { key: "observation", label: "Observation", type: "textarea" },
                        { key: "experiment_code", label: "Experiment code" },
                      ]}
                      initialValue={mhSupporting}
                      onChange={setMhSupporting}
                      description="Evidence that supports this hypothesis. Leave empty for none."
                      idPrefix="mh-supporting"
                    />
                  </div>
                  <div className="md:col-span-2">
                    <ObjectArrayField
                      key={`mh-contradicting-${mhFormKey}`}
                      label="Contradicting observations"
                      itemLabel="Observation"
                      addLabel="Add observation"
                      fields={[
                        { key: "observation", label: "Observation", type: "textarea" },
                        { key: "experiment_code", label: "Experiment code" },
                      ]}
                      initialValue={mhContradicting}
                      onChange={setMhContradicting}
                      description="Evidence that contradicts this hypothesis. Leave empty for none."
                      idPrefix="mh-contradicting"
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
                              Confidence: {conf || "—"}
                            </Badge>
                            <Badge variant="secondary" className="font-mono text-xs">
                              status: {st || "—"}
                            </Badge>
                            {row.human_review_required === true ? (
                              <Badge variant="outline" className="text-xs">
                                Human review required
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
                              Confidence label
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
                            Supporting observations
                          </p>
                          <pre className="max-h-40 overflow-auto rounded-md bg-muted/40 p-3 text-[10px] leading-snug">
                            {jsonPreview(sup ?? [], 8000)}
                          </pre>
                        </div>
                        <div className="space-y-2">
                          <p className="text-xs font-medium uppercase text-muted-foreground">
                            Contradicting observations
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
                  <Empty>
                    <EmptyHeader>
                      <EmptyMedia variant="icon">
                        <Lightbulb />
                      </EmptyMedia>
                      <EmptyTitle>No mechanistic hypotheses yet</EmptyTitle>
                      <EmptyDescription>Record a hypothesis to track proposed mechanisms.</EmptyDescription>
                    </EmptyHeader>
                  </Empty>
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
            description="Literature and prior knowledge used as advisor context. Citations are not generated by the platform."
          >
            <div className="space-y-6">
              <form className="space-y-4" onSubmit={(e) => void createLiteraturePrior(e)}>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="lp-source">Source type</Label>
                    <Select value={lpSourceType} onValueChange={setLpSourceType}>
                      <SelectTrigger id="lp-source">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {LITERATURE_PRIOR_SOURCE_TYPES.map((s) => (
                          <SelectItem key={s} value={s}>
                            {optionLabel(s)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="lp-title">Title</Label>
                    <Input
                      id="lp-title"
                      value={lpTitle}
                      onChange={(e) => setLpTitle(e.target.value)}
                      maxLength={240}
                      autoComplete="off"
                    />
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="lp-summary">Summary</Label>
                    <Textarea
                      id="lp-summary"
                      rows={4}
                      value={lpSummary}
                      onChange={(e) => setLpSummary(e.target.value)}
                      className="text-sm"
                    />
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="lp-citation">Citation</Label>
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
                  <div className="md:col-span-2">
                    <StringListField
                      key={`lp-tags-${lpFormKey}`}
                      label="Relevance tags"
                      itemLabel="Tag"
                      itemPlaceholder="e.g. solvent, amidation"
                      addLabel="Add tag"
                      initialValue={lpTags}
                      onChange={setLpTags}
                      suggestions={categoricalSuggestions}
                      description="Short tags for retrieval/relevance. Leave empty for none."
                      idPrefix="lp-tags"
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
                      <TableHead className="text-xs">Source type</TableHead>
                      <TableHead className="text-xs">Title</TableHead>
                      <TableHead className="min-w-[200px] text-xs">Summary</TableHead>
                      <TableHead className="min-w-[140px] text-xs">Citation</TableHead>
                      <TableHead className="text-xs">Relevance tags</TableHead>
                      <TableHead className="text-xs">Created</TableHead>
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
                                  Needs human review
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
            description="Compare Bayesian optimization rankings with the advisor's concerns. Output is advisory — final experiment scheduling requires human review."
          >
            <div className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="cmp-bo-run">BO run</Label>
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
                            {bid} {typeof row.algorithm === "string" ? `· ${optionLabel(row.algorithm)}` : ""} ·{" "}
                            {fmtIso(row.created_at)}
                          </SelectItem>
                        )
                      })}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cmp-advisor-run">Advisor run</Label>
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
                            {String(rid)} · {optionLabel(typeof row.advisor_mode === "string" ? row.advisor_mode : null)} · {fmtIso(row.created_at)}
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
                      BO run: {String(lastComparison.bo_run_id ?? "—")}
                    </Badge>
                    <Badge variant="outline" className="font-mono text-xs">
                      Advisor run: {String(lastComparison.advisor_run_id ?? "—")}
                    </Badge>
                    <Badge variant="secondary" className="text-xs">
                      requires review
                    </Badge>
                    {lastComparison.human_review_required === true ? (
                      <Badge variant="outline" className="text-xs">
                        Needs human review
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

                  <DeveloperOnly>
                    <Collapsible className="rounded-md border border-border">
                      <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm font-medium hover:bg-muted/50">
                        Developer JSON
                        <ChevronDown className="h-4 w-4 shrink-0 opacity-70" />
                      </CollapsibleTrigger>
                      <CollapsibleContent className="border-t border-border px-3 py-3">
                        <DeveloperJsonPanel data={lastComparison} />
                      </CollapsibleContent>
                    </Collapsible>
                  </DeveloperOnly>
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
                        <TableHead className="text-xs">ID</TableHead>
                        <TableHead className="text-xs">BO run</TableHead>
                        <TableHead className="text-xs">Advisor run</TableHead>
                        <TableHead className="text-xs">Final review recommendation</TableHead>
                        <TableHead className="text-xs">Created</TableHead>
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
            title={
              <span className="inline-flex items-center gap-2">
                Human Review
                <InfoTooltip content={ADVISOR_HUMAN_REVIEW_TOOLTIP} label="What a review decision records" />
              </span>
            }
            description="Record a review decision on an advisor run. Advisor output is decision-support only and does not autonomously schedule experiments."
          >
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="advisor-review-run">Advisor run</Label>
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
                            {String(rid)} · {optionLabel(typeof row.advisor_mode === "string" ? row.advisor_mode : null)} · {fmtIso(row.created_at)}
                          </SelectItem>
                        )
                      })}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="advisor-reviewer-name">Reviewer name</Label>
                  <Input
                    id="advisor-reviewer-name"
                    autoComplete="name"
                    value={advisorReviewerName}
                    onChange={(e) => setAdvisorReviewerName(e.target.value)}
                    placeholder="Your name"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="advisor-review-decision">Decision</Label>
                  <Select value={advisorReviewDecision} onValueChange={setAdvisorReviewDecision}>
                    <SelectTrigger id="advisor-review-decision">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ADVISOR_REVIEW_DECISIONS.map((d) => (
                        <SelectItem key={d} value={d}>
                          {optionLabel(d)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="advisor-review-rationale">
                    Rationale <span className="text-destructive">(required)</span>
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
                        Decision: {optionLabel(typeof review.decision === "string" ? review.decision : null)}
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
              className="font-mono text-[11px] font-bold uppercase tracking-[0.2em]"
              style={{ color: "var(--mt-violet-ink)" }}
            >
              Project · Recommendations
            </p>
            <h2 className="font-mono text-2xl font-bold tracking-tight">Reviewer queue &amp; approvals</h2>
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
                Approving or rejecting a recommendation requires a reviewer name and comment (human approval). Outputs are decision-support; each recommended next experiment
                requires human review.
              </>
            }
          >
            <div className="space-y-2">
              <Label htmlFor="rec-reviewer-name">Reviewer name</Label>
              <Input
                id="rec-reviewer-name"
                autoComplete="name"
                value={revReviewerName}
                onChange={(e) => setRevReviewerName(e.target.value)}
                placeholder="Your name"
              />
              <p className="text-xs text-muted-foreground">
                Shared across approve/reject on this tab. Each row needs a review comment before approval or rejection.
              </p>
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Recommendations · Latest BO Batch"
            title={
              <span className="inline-flex items-center gap-2">
                Latest BO recommendation batch
                <InfoTooltip content={LATEST_BO_BATCH_TOOLTIP} label="What each candidate carries" />
              </span>
            }
            description="Ranked candidates from the most recent Bayesian optimization run. All values are probabilistic and require human review."
          >
            <div className="space-y-4">
              {!loading && latestBatchRows.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No recommendation batches yet — run Bayesian optimization, or wait for the current batch to finish.
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
                        <TableHead className="min-w-[160px] text-xs">Review comment</TableHead>
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
            title={
              <span className="inline-flex items-center gap-2">
                Recommendations
                <InfoTooltip content={RECOMMENDATIONS_LIST_TOOLTIP} label="How candidates are ranked" />
              </span>
            }
            description="Proposed next experiments awaiting your approve-or-reject decision."
          >
            <div className="space-y-6">
              {/* R9/R10 — advisory re-ranks (mutually exclusive); the optimiser's own rank stays visible. */}
              <div className="flex flex-wrap items-center gap-3 rounded-md border bg-muted/20 px-3 py-2">
                <Button
                  type="button"
                  size="sm"
                  variant={showLikelyAccept ? "default" : "outline"}
                  disabled={busy != null}
                  onClick={() => {
                    if (showLikelyAccept) setShowLikelyAccept(false)
                    else {
                      setShowWarmStartRank(false)
                      void loadPreferenceRanking()
                    }
                  }}
                >
                  {busy === "pref-rank"
                    ? "Ranking…"
                    : showLikelyAccept
                      ? "Likely-acceptance re-rank: on"
                      : "Re-rank by likely acceptance"}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={showWarmStartRank ? "default" : "outline"}
                  disabled={busy != null}
                  onClick={() => {
                    if (showWarmStartRank) setShowWarmStartRank(false)
                    else {
                      setShowLikelyAccept(false)
                      void loadWarmStartRanking()
                    }
                  }}
                >
                  {busy === "ws-rank"
                    ? "Ranking…"
                    : showWarmStartRank
                      ? "Warm-start re-rank: on"
                      : "Re-rank by warm-start prior"}
                </Button>
                <span className="text-xs text-muted-foreground">
                  Advisory —{" "}
                  {showWarmStartRank
                    ? reactionWarmStartPriorView(warmStartPrior)?.verifiedOnly === false
                      ? "warm-start biases toward conditions from related campaigns (PREVIEW prior — fit including unconfirmed data)"
                      : "warm-start biases toward conditions that worked on related, verified campaigns"
                    : "likely-acceptance re-orders by predicted chemist acceptance from past feedback"}
                  . The
                  optimiser&apos;s own rank stays visible (badge) and is never overridden.
                </span>
                {showLikelyAccept || showWarmStartRank ? (
                  <span className="w-full text-[11px] text-muted-foreground">
                    {rerankMatchCount > 0
                      ? `Ranked ${rerankMatchCount} of ${sortedRecs.length} proposal${sortedRecs.length === 1 ? "" : "s"} against the ${showWarmStartRank ? "warm-start prior" : "preference model"}; unmatched proposals keep the optimiser's order.`
                      : `No current proposals matched the ${showWarmStartRank ? "warm-start ranking" : "preference ranking"} — showing the optimiser's original order${showWarmStartRank ? " (run a BO batch, or build a prior first)" : ""}.`}
                  </span>
                ) : null}
              </div>
              {displayRecs.map((r) => {
                const id = readNum(r.id)
                if (id == null) return null
                const st = String(r.status ?? "")
                const canReview = st === "proposed"
                const condKey = canonicalConditionsKey(r.conditions_json)
                const likely = preferenceRankByConditions.get(condKey)
                const warm = warmStartRankByConditions.get(condKey)
                return (
                  <Card key={id} className="border-muted">
                    <CardHeader className="pb-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <CardTitle className="text-sm font-medium">Recommendation {id}</CardTitle>
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
                        {showLikelyAccept && likely && likely.acceptanceScore != null ? (
                          <Badge
                            variant="outline"
                            className="font-mono text-xs"
                            style={{ borderColor: "var(--mt-teal)", color: "var(--mt-teal-ink)" }}
                          >
                            BO #{likely.originalRank ?? "—"} · likely-accept {likely.acceptanceScore.toFixed(2)}
                          </Badge>
                        ) : showWarmStartRank && warm && warm.priorMean != null ? (
                          <Badge
                            variant="outline"
                            className="font-mono text-xs"
                            style={{ borderColor: "var(--mt-violet)", color: "var(--mt-violet-ink)" }}
                          >
                            BO #{warm.originalRank ?? "—"} · prior {warm.priorMean.toFixed(2)}
                          </Badge>
                        ) : showLikelyAccept || showWarmStartRank ? (
                          <Badge variant="outline" className="text-[10px] text-muted-foreground">
                            unranked
                          </Badge>
                        ) : null}
                      </div>
                      <CardDescription className="text-xs">{fmtIso(r.updated_at)}</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4 text-sm">
                      <div className="space-y-2">
                        <p className="text-xs font-medium uppercase text-muted-foreground">Conditions</p>
                        <pre className="max-h-36 overflow-auto rounded-md bg-muted/40 p-3 text-xs leading-relaxed">
                          {jsonPreview(r.conditions_json ?? {}, 4000)}
                        </pre>
                      </div>
                      <div className="space-y-2">
                        <p className="text-xs font-medium uppercase text-muted-foreground">Predicted outcome</p>
                        <pre className="max-h-36 overflow-auto rounded-md bg-muted/40 p-3 text-xs leading-relaxed">
                          {jsonPreview(r.predicted_outcome_json ?? {}, 4000)}
                        </pre>
                      </div>
                      <div className="space-y-2">
                        <p className="text-xs font-medium uppercase text-muted-foreground">Uncertainty</p>
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
                        <Label htmlFor={`rev-${id}`}>Review comment <span className="text-destructive">(required)</span></Label>
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
                      <Separator />
                      {/* R9 — structured chemist feedback that trains the advisory preference re-ranker. */}
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <p className="text-xs font-medium uppercase text-muted-foreground">proposal feedback</p>
                          <Badge variant="outline" className="text-[10px]">advisory · trains the re-ranker</Badge>
                        </div>
                        {(() => {
                          const draft = feedbackDraft[id] ?? { decision: "accept", reason: "", freeText: "" }
                          const needReason = reactionFeedbackReasonRequired(draft.decision)
                          const setDraft = (
                            patch: Partial<{ decision: string; reason: string; freeText: string }>,
                          ) => setFeedbackDraft((prev) => ({ ...prev, [id]: { ...draft, ...patch } }))
                          const fbView = reactionFeedbackRecordView(feedbackResult[id])
                          return (
                            <div className="space-y-2">
                              <div className="flex flex-wrap items-end gap-2">
                                <div className="space-y-1">
                                  <Label htmlFor={`fb-dec-${id}`} className="text-xs">Decision</Label>
                                  <Select
                                    value={draft.decision}
                                    onValueChange={(v) => setDraft(v === "reject" ? { decision: v } : { decision: v, reason: "" })}
                                  >
                                    <SelectTrigger id={`fb-dec-${id}`} className="h-8 w-[130px] text-xs">
                                      <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                      {REACTION_FEEDBACK_DECISIONS.map((d) => (
                                        <SelectItem key={d} value={d}>{d}</SelectItem>
                                      ))}
                                    </SelectContent>
                                  </Select>
                                </div>
                                {needReason ? (
                                  <div className="space-y-1">
                                    <Label htmlFor={`fb-reason-${id}`} className="text-xs">
                                      Reason <span className="text-destructive">(required)</span>
                                    </Label>
                                    <Select value={draft.reason} onValueChange={(v) => setDraft({ reason: v })}>
                                      <SelectTrigger id={`fb-reason-${id}`} className="h-8 w-[210px] text-xs">
                                        <SelectValue placeholder="select a reason" />
                                      </SelectTrigger>
                                      <SelectContent>
                                        {REACTION_FEEDBACK_REASONS.map((rs) => (
                                          <SelectItem key={rs} value={rs}>{rs.replace(/_/g, " ")}</SelectItem>
                                        ))}
                                      </SelectContent>
                                    </Select>
                                  </div>
                                ) : null}
                                <Button
                                  type="button"
                                  size="sm"
                                  className="h-8 text-xs"
                                  disabled={busy != null || (needReason && !draft.reason)}
                                  onClick={() => void submitReactionFeedback(r)}
                                >
                                  {busy === `feedback-${id}` ? "…" : "Submit feedback"}
                                </Button>
                              </div>
                              <Textarea
                                rows={2}
                                className="text-xs"
                                value={draft.freeText}
                                onChange={(e) => setDraft({ freeText: e.target.value })}
                                placeholder="Optional free-text (e.g. why this is infeasible on our kit)."
                              />
                              {needReason && draft.reason === "unsafe" ? (
                                <p className="text-[11px] font-medium text-foreground">
                                  An “unsafe” rejection is high-signal: it routes to strengthen the R6 safety
                                  screen and is excluded from preference learning.
                                </p>
                              ) : null}
                              {fbView ? (
                                <div
                                  className="rounded-md border px-3 py-2 text-[11px]"
                                  style={{ borderLeft: `3px solid ${fbView.isSafetySignal ? "var(--mt-amber)" : "var(--mt-teal)"}` }}
                                >
                                  <p className="text-muted-foreground">
                                    Recorded: <span className="font-mono text-foreground">{fbView.decision}</span>
                                    {fbView.reason ? (
                                      <> · <span className="font-mono text-foreground">{fbView.reason.replace(/_/g, " ")}</span></>
                                    ) : null}
                                  </p>
                                  {fbView.isSafetySignal ? (
                                    <p className="font-medium text-foreground">
                                      Routed to the safety gate (R6){fbView.routesToSafetyHardening ? " for hardening" : ""} —
                                      excluded from preference learning.{" "}
                                      <button type="button" className={INLINE_LINK_BUTTON_CLASS} onClick={goToSafetyGate}>
                                        Open the safety gate →
                                      </button>
                                    </p>
                                  ) : (
                                    <p className="text-muted-foreground">
                                      {fbView.isPreferenceLearnable
                                        ? "Feeds the advisory preference re-ranker."
                                        : "Not used for preference learning."}
                                    </p>
                                  )}
                                </div>
                              ) : null}
                            </div>
                          )
                        })()}
                      </div>
                    </CardContent>
                  </Card>
                )
              })}
              {!loading && displayRecs.length === 0 ? (
                <p className="text-sm text-muted-foreground">No recommendations.</p>
              ) : null}
            </div>
          </ModuleCard>

          <ModuleCard
            accent="violet"
            eyebrow="Models · A/B promotion gate"
            title={
              <span className="inline-flex items-center gap-2">
                A/B model promotion (advisory)
                <InfoTooltip content={AB_PROMOTION_TOOLTIP} label="How the promotion verdict is decided" />
              </span>
            }
            description="Compare a challenger model against the current champion. Decision-support only — it deploys nothing; a human still signs off and rollback stays available."
          >
            <form className="space-y-4" onSubmit={(e) => void evaluateAbPromotion(e)}>
              <div className="grid gap-4 md:grid-cols-2">
                {(
                  [
                    { key: "champion", verLabel: "championVersion", metLabel: "championMetrics", recLabel: "championRecall", ph: "champion-v1" },
                    { key: "challenger", verLabel: "challengerVersion", metLabel: "challengerMetrics", recLabel: "challengerRecall", ph: "challenger-v2" },
                  ] as const
                ).map((side) => (
                  <div key={side.key} className="space-y-2 rounded-md border p-3">
                    <p className="text-xs font-medium uppercase text-muted-foreground">{side.key}</p>
                    <div className="space-y-1">
                      <Label htmlFor={`ab-${side.key}-ver`} className="text-xs">Model version</Label>
                      <Input
                        id={`ab-${side.key}-ver`}
                        className="h-8 text-xs"
                        value={abForm[side.verLabel]}
                        onChange={(e) => setAbForm((p) => ({ ...p, [side.verLabel]: e.target.value }))}
                        placeholder={side.ph}
                      />
                    </div>
                    <KeyNumberTableField
                      label="Metrics"
                      keyLabel="Metric"
                      valueLabel="Value"
                      addLabel="Add metric"
                      initialValue={side.key === "champion" ? abChampionMetrics : abChallengerMetrics}
                      onChange={side.key === "champion" ? setAbChampionMetrics : setAbChallengerMetrics}
                      idPrefix={`ab-${side.key}-met`}
                    />
                    <div className="space-y-1">
                      <Label htmlFor={`ab-${side.key}-rec`} className="text-xs">Safety-flag recall</Label>
                      <Input
                        id={`ab-${side.key}-rec`}
                        className="h-8 text-xs"
                        value={abForm[side.recLabel]}
                        onChange={(e) => setAbForm((p) => ({ ...p, [side.recLabel]: e.target.value }))}
                        placeholder="0.95"
                      />
                    </div>
                  </div>
                ))}
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <KeyChoiceTableField
                  label="Directions"
                  keyLabel="Metric"
                  valueLabel="Better when"
                  addLabel="Add direction"
                  options={[
                    { value: "higher", label: "Higher is better" },
                    { value: "lower", label: "Lower is better" },
                  ]}
                  initialValue={abDirections}
                  onChange={setAbDirections}
                  description="Which way is better for each metric (defaults apply when unset)."
                  idPrefix="ab-dirs"
                />
                <div className="space-y-1">
                  <Label htmlFor="ab-tol" className="text-xs">Tolerance</Label>
                  <Input
                    id="ab-tol"
                    className="h-8 text-xs"
                    value={abForm.tolerance}
                    onChange={(e) => setAbForm((p) => ({ ...p, tolerance: e.target.value }))}
                    placeholder="0"
                  />
                </div>
              </div>
              <Button type="submit" size="sm" disabled={busy != null}>
                {busy === "ab-eval" ? "Evaluating…" : "Evaluate promotion"}
              </Button>
            </form>
            {(() => {
              const v = reactionAbVerdictView(abVerdict)
              if (v == null) return null
              return (
                <div
                  className="mt-4 space-y-3 rounded-md border p-3"
                  style={{ borderLeft: `3px solid ${v.promotable ? "var(--mt-teal)" : "var(--mt-amber)"}` }}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={v.promotable ? "default" : "secondary"} className="text-xs">
                      {v.promotable ? "promotable (pending sign-off)" : "not promotable"}
                    </Badge>
                    <Badge variant="outline" className="text-xs">Safety regression: {String(v.safetyRegression)}</Badge>
                    <Badge variant="outline" className="text-xs">dominates: {String(v.dominates)}</Badge>
                    <Badge variant="outline" className="font-mono text-[11px]">
                      {v.challengerVersion ?? "challenger"} vs {v.championVersion ?? "champion"}
                    </Badge>
                  </div>
                  <p className="rounded-md bg-muted/40 px-3 py-2 text-xs font-medium text-foreground">
                    Requires human sign-off — this evaluation does not deploy or roll back any model;
                    rollback remains available.
                  </p>
                  {v.reasons.length > 0 ? (
                    <div className="space-y-1">
                      <p className="text-xs font-medium text-muted-foreground">Reasons</p>
                      <ul className="list-inside list-disc text-xs text-muted-foreground">
                        {v.reasons.map((rr, i) => (
                          <li key={`ab-reason-${i}`}>{rr}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {v.excludedMetrics.length > 0 ? (
                    <p className="text-[11px] text-muted-foreground">
                      excluded metrics (unknown direction / not comparable):{" "}
                      <span className="font-mono">{v.excludedMetrics.join(", ")}</span>
                    </p>
                  ) : null}
                  {v.disclaimer ? (
                    <p className="text-[11px] italic text-muted-foreground">{v.disclaimer}</p>
                  ) : null}
                </div>
              )
            })()}
          </ModuleCard>
        </TabsContent>

        <TabsContent value="execution" className="mt-4 min-w-0 max-w-full space-y-6">
          <div className="space-y-1">
            <p
              className="font-mono text-[11px] font-bold uppercase tracking-[0.2em]"
              style={{ color: "var(--mt-violet-ink)" }}
            >
              Project · Execution
            </p>
            <h2 className="font-mono text-2xl font-bold tracking-tight">Lab execution batches &amp; outcomes</h2>
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
              title={
                <span className="inline-flex items-center gap-2">
                  Ready for next optimization cycle
                  <InfoTooltip content={CYCLE_READY_TOOLTIP} label="What the next cycle reads" />
                </span>
              }
              description="Confirmed outcomes are ready to seed the next optimization cycle. Neither Bayesian optimization nor the advisor triggers automatically after outcome confirmation."
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
                          ? `${readBoRunId(execTabLatestBoRunRecord)} · ${optionLabel(typeof execTabLatestBoRunRecord.algorithm === "string" ? execTabLatestBoRunRecord.algorithm : null)} · ${optionLabel(typeof execTabLatestBoRunRecord.status === "string" ? execTabLatestBoRunRecord.status : null)}`
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
                            } · ${optionLabel(
                              typeof execTabLatestAdvisorRunRecord.advisor_mode === "string"
                                ? execTabLatestAdvisorRunRecord.advisor_mode
                                : typeof execTabLatestAdvisorRunRecord.mode === "string"
                                  ? execTabLatestAdvisorRunRecord.mode
                                  : null,
                            )} · ${optionLabel(typeof execTabLatestAdvisorRunRecord.status === "string" ? execTabLatestAdvisorRunRecord.status : null)}`
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
            description="Approved recommendations pending conversion to planned experiments. Recording a planned experiment is not confirmation that laboratory work occurred."
          >
            <div className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="conv-rec-rationale">Rationale</Label>
                  <Textarea
                    id="conv-rec-rationale"
                    rows={3}
                    className="text-sm"
                    value={convertRecRationale}
                    onChange={(e) => setConvertRecRationale(e.target.value)}
                    placeholder="Reason for conversion (required)."
                  />
                  <p className="text-xs text-muted-foreground">
                    Optional reviewer name uses the Recommendations tab reviewer name field when set.
                  </p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="conv-exec-batch">Execution batch</Label>
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
                    Omit (—) to record the conversion without an execution batch link when that is allowed.
                  </p>
                </div>
              </div>

              <div className="table-scroll">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="font-mono text-xs tabular-nums">Recommendation</TableHead>
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
                                    Execution item {planned.execution_item_id}
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
                        <TableHead className="font-mono text-xs">Recommendation</TableHead>
                        <TableHead className="font-mono text-xs">Experiment ID</TableHead>
                        <TableHead className="font-mono text-xs">Execution item</TableHead>
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
            title={
              <span className="inline-flex items-center gap-2">
                Execution Batch Planner
                <InfoTooltip content={EXECUTION_BATCH_PLANNER_TOOLTIP} label="How execution batches work" />
              </span>
            }
            description="Plan and track lab execution batches. Statuses reflect recorded progress only and do not trigger any lab automation."
          >
            <div className="space-y-8">
              <form className="space-y-4" onSubmit={(e) => void createExecutionBatchPlanner(e)}>
                <p className="text-sm font-medium">Create execution batch</p>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="eb-pl-batch-code">Batch code</Label>
                    <Input
                      id="eb-pl-batch-code"
                      value={plEbBatchCode}
                      onChange={(e) => setPlEbBatchCode(e.target.value)}
                      maxLength={120}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="eb-pl-title">Title</Label>
                    <Input
                      id="eb-pl-title"
                      value={plEbTitle}
                      onChange={(e) => setPlEbTitle(e.target.value)}
                      maxLength={240}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="eb-pl-planned-start">Planned start</Label>
                    <Input
                      id="eb-pl-planned-start"
                      type="datetime-local"
                      step={60}
                      value={plEbPlannedStart}
                      onChange={(e) => setPlEbPlannedStart(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="eb-pl-planned-end">Planned end</Label>
                    <Input
                      id="eb-pl-planned-end"
                      type="datetime-local"
                      step={60}
                      value={plEbPlannedEnd}
                      onChange={(e) => setPlEbPlannedEnd(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="eb-pl-notes">Notes</Label>
                    <Textarea
                      id="eb-pl-notes"
                      rows={2}
                      className="text-sm"
                      value={plEbNotes}
                      onChange={(e) => setPlEbNotes(e.target.value)}
                      placeholder="Optional — kept with the batch details when present."
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
                        <TableHead className="font-mono text-xs">Batch ID</TableHead>
                        <TableHead className="text-xs">Batch code</TableHead>
                        <TableHead className="text-xs">Title</TableHead>
                        <TableHead className="text-xs">Status</TableHead>
                        <TableHead className="text-right text-xs tabular-nums">Item count</TableHead>
                        <TableHead className="whitespace-nowrap text-xs">Planned start</TableHead>
                        <TableHead className="whitespace-nowrap text-xs">Planned end</TableHead>
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
                      Selected batch {plannerSelectedBatchId}
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
                        <Label htmlFor="eb-pl-exp">Experiment (planned experiment)</Label>
                        <Select
                          value={execPlannerExperimentId || "__none__"}
                          onValueChange={setExecPlannerExperimentId}
                        >
                          <SelectTrigger id="eb-pl-exp">
                            <SelectValue placeholder="Choose an experiment" />
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
                        <Label htmlFor="eb-pl-item-code">Item code</Label>
                        <Input
                          id="eb-pl-item-code"
                          value={execPlannerItemCode}
                          onChange={(e) => setExecPlannerItemCode(e.target.value)}
                          maxLength={120}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="eb-pl-operator">Operator name</Label>
                        <Input
                          id="eb-pl-operator"
                          value={execPlannerOperatorName}
                          onChange={(e) => setExecPlannerOperatorName(e.target.value)}
                          maxLength={200}
                          placeholder="Optional."
                        />
                      </div>
                      <div className="md:col-span-2">
                        <ObjectArrayField
                          key={`eb-pl-checklist-${execPlannerFormKey}`}
                          label="Checklist"
                          itemLabel="Step"
                          addLabel="Add step"
                          fields={[
                            { key: "task", label: "Task" },
                            { key: "done", label: "Done? (true/false)", type: "text" },
                          ]}
                          initialValue={execPlannerChecklist}
                          onChange={setExecPlannerChecklist}
                          description="Optional prep/run steps for this execution item."
                          idPrefix="eb-pl-checklist"
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
                            <TableHead className="whitespace-nowrap text-xs">Started</TableHead>
                            <TableHead className="whitespace-nowrap text-xs">Completed</TableHead>
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
                                No items — add items using the form above when an experiment row is planned.
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
                    <TableHead className="font-mono text-xs">Batch ID</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">Updated</TableHead>
                    <TableHead className="text-xs">Summary</TableHead>
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
            description="Advance each execution item as reactions are run. Status transitions are user-initiated; no autonomous lab scheduling occurs here."
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
                                Item {itemId != null ? itemId : "—"}
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
            title={
              <span className="inline-flex items-center gap-2">
                Experiment execution board
                <InfoTooltip content={EXECUTION_STATUS_TABLE_TOOLTIP} label="What each row shows" />
              </span>
            }
            description="Experiment status reflects manually recorded lab progress."
          >
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Experiment code</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right text-xs">Yield %</TableHead>
                    <TableHead className="font-mono text-xs">Linked SpectraCheck session</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">SpectraCheck</TableHead>
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
                          <StatusBadge status={e.status} />
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
                        No experiments — use the Experiments tab to record one.
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
            description="Link analytical summary values to execution items. Full spectral evidence and QC records remain in SpectraCheck."
          >
            <div className="space-y-6">
              <form className="space-y-4" onSubmit={(e) => void addAnalyticalResultToExecutionItem(e)}>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="ar-item">Execution item</Label>
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
                    <Label htmlFor="ar-type">Result type</Label>
                    <Select value={arResultType} onValueChange={setArResultType}>
                      <SelectTrigger id="ar-type">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {ANALYTICAL_RESULT_TYPE_OPTIONS.map((opt) => (
                          <SelectItem key={opt} value={opt}>
                            {optionLabel(opt)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="ar-sc">SpectraCheck session</Label>
                    <Input
                      id="ar-sc"
                      inputMode="numeric"
                      value={arSpectraCheckSessionId}
                      onChange={(e) => setArSpectraCheckSessionId(e.target.value)}
                      placeholder="Optional"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="ar-file">File</Label>
                    <Input
                      id="ar-file"
                      inputMode="numeric"
                      value={arFileId}
                      onChange={(e) => setArFileId(e.target.value)}
                      placeholder="Optional"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="ar-artifact">Artifact</Label>
                    <Input
                      id="ar-artifact"
                      inputMode="numeric"
                      value={arArtifactId}
                      onChange={(e) => setArArtifactId(e.target.value)}
                      placeholder="Optional"
                    />
                  </div>

                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="ar-hash">Source hash</Label>
                    <Input
                      id="ar-hash"
                      value={arSourceHash}
                      onChange={(e) => setArSourceHash(e.target.value)}
                      maxLength={128}
                      placeholder="Optional"
                    />
                  </div>

                  <div className="md:col-span-2">
                    <JsonObjectField
                      key={`ar-summary-${arFormKey}`}
                      label="Summary"
                      initialValue={arSummary}
                      onChange={setArSummary}
                      fields={[{ key: "summary_text", label: "Summary text", type: "textarea" }]}
                      allowCustomKeys
                      description="A free-text summary, and/or your own labeled fields. Leave empty for none."
                      idPrefix="ar-summary"
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
            title={
              <span className="inline-flex items-center gap-2">
                Outcome extraction
                <InfoTooltip content={OUTCOME_EXTRACTION_TOOLTIP} label="Where outcomes are stored" />
              </span>
            }
            description="Records confirmed yield and conversion onto the experiment. The UI does not autonomously import numerical outcomes from spectral files."
          >
            <div className="space-y-4">
              <p className="text-xs text-muted-foreground">
                Extract yield, conversion, and related outcome values from linked analytical data. Proposed outcomes require explicit confirmation before updating the experiment record.
              </p>

              <div className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="oe-exec-item">Execution item</Label>
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
                    <Label htmlFor="oe-method">Extraction method</Label>
                    <Select value={oeExtractionMethod} onValueChange={setOeExtractionMethod}>
                      <SelectTrigger id="oe-method">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {OUTCOME_EXTRACTION_METHOD_OPTIONS.map((opt) => (
                          <SelectItem key={opt} value={opt}>
                            {optionLabel(opt)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="oe-ar-id">Analytical result</Label>
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
                        <Badge variant="secondary" className="font-normal text-xs">
                          {optionLabel(oeExtractionRun.extraction_method)}
                        </Badge>
                      ) : null}
                    </div>

                    <div className="space-y-1">
                      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        Extracted raw (proposed outcome)
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
                        <span className="font-medium text-foreground">Confidence</span>{" "}
                        <span className="font-mono text-muted-foreground">
                          {typeof oeExtractionRun.confidence_label === "string"
                            ? oeExtractionRun.confidence_label
                            : "—"}
                        </span>
                      </p>
                      {mergeOutcomeExtractionWarnings(oeExtractionRun).length > 0 ? (
                        <div className="space-y-1">
                          <p className="font-medium text-foreground">Warnings</p>
                          <ul className="list-inside list-disc text-muted-foreground">
                            {mergeOutcomeExtractionWarnings(oeExtractionRun).map((w) => (
                              <li key={w}>{w}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                      {mergeOutcomeExtractionNotes(oeExtractionRun).length > 0 ? (
                        <div className="space-y-1">
                          <p className="font-medium text-foreground">Notes</p>
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
                        Edit the confirmed outcome fields you want to keep. Percent fields you leave blank are left
                        unchanged; only the values you enter are saved over the existing outcome. Leaving every field
                        blank still applies the proposed outcome.
                      </p>

                      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                        <div className="space-y-2">
                          <Label htmlFor="oe-yield">Yield (%)</Label>
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
                          <Label htmlFor="oe-conv">Conversion (%)</Label>
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
                          <Label htmlFor="oe-sel">Selectivity (%)</Label>
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
                          <Label htmlFor="oe-imp">Impurity (%)</Label>
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
                          <Label htmlFor="oe-iso">Isolated yield (%)</Label>
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
                          <Label htmlFor="oe-lcms">LC-MS area (%)</Label>
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
                          <Label htmlFor="oe-nmr">NMR purity (%)</Label>
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
                          <Label htmlFor="oe-notes">Notes</Label>
                          <Textarea
                            id="oe-notes"
                            rows={3}
                            className="text-sm"
                            value={oeConfirmedNotes}
                            onChange={(e) => setOeConfirmedNotes(e.target.value)}
                            placeholder="Optional free text saved with the confirmed outcome."
                          />
                        </div>
                      </div>

                      <div className="grid gap-4 md:grid-cols-2">
                        <div className="space-y-2">
                          <Label htmlFor="oe-reviewer">Reviewer name</Label>
                          <Input
                            id="oe-reviewer"
                            value={oeReviewerName}
                            onChange={(e) => setOeReviewerName(e.target.value)}
                            placeholder="Operator or reviewer (optional if rationale identifies the actor)"
                          />
                        </div>
                        <div className="space-y-2 md:col-span-2">
                          <Label htmlFor="oe-rationale">Rationale</Label>
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
                      <TableHead>Experiment code</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right text-xs">Yield %</TableHead>
                      <TableHead className="text-right text-xs">Conversion %</TableHead>
                      <TableHead className="text-xs">Outcome preview</TableHead>
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
            description="Recent Bayesian optimization, heuristic, and advisor runs across all cycles. Ordering is informational, not an autonomous loop."
          >
            <div className="space-y-4">
              <p className="text-xs text-muted-foreground">
                Create and track optimization cycles that link execution batches with their corresponding optimization runs and advisor decisions. Run ordering below is informational.
              </p>

              <form className="space-y-4" onSubmit={(e) => void createOptimizationCycleRecord(e)}>
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  <div className="space-y-2 lg:col-span-2">
                    <Label htmlFor="opt-cc-eb">Execution batch</Label>
                    <Select value={optCcExecutionBatchId || "__none__"} onValueChange={setOptCcExecutionBatchId}>
                      <SelectTrigger id="opt-cc-eb">
                        <SelectValue placeholder="Optional linkage" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">No execution batch link</SelectItem>
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
                    <Label htmlFor="opt-cc-st">Status</Label>
                    <Select value={optCcStatus} onValueChange={setOptCcStatus}>
                      <SelectTrigger id="opt-cc-st">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {REACTION_OPTIMIZATION_CYCLE_STATUS_OPTIONS.map((st) => (
                          <SelectItem key={st} value={st}>
                            {optionLabel(st)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="opt-cc-num">Cycle number</Label>
                    <Input
                      id="opt-cc-num"
                      inputMode="numeric"
                      className="font-mono text-xs"
                      value={optCcCycleNumber}
                      onChange={(e) => setOptCcCycleNumber(e.target.value)}
                      placeholder="Optional — numbered automatically if blank"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="opt-cc-bo">BO run</Label>
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
                    <Label htmlFor="opt-cc-ad">Advisor run</Label>
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
                    <Label htmlFor="opt-cc-rb">Recommendation batch</Label>
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
                      <TableHead className="text-right text-xs">Cycle number</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right text-xs tabular-nums">Input experiments</TableHead>
                      <TableHead className="text-right text-xs tabular-nums">New experiments</TableHead>
                      <TableHead className="font-mono text-xs">BO run</TableHead>
                      <TableHead className="font-mono text-xs">Advisor run</TableHead>
                      <TableHead className="font-mono text-xs">Recommendation batch</TableHead>
                      <TableHead className="font-mono text-xs">Execution batch</TableHead>
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
                        // R5 — half-closed DMTA loop bits
                        const loopMetrics = cycleLoopMetricsFromCycle(merged)
                        const proposeInfo = cycleProposeNextInfoFromCycle(merged)
                        const dmtaInfo = cycleDmtaInfoFromCycle(merged)
                        const latestDecision =
                          dec != null && typeof dec.decision === "string" ? dec.decision : null
                        const canProposeNext = cycleCanProposeNext(merged)
                        const proposeBusy = busy === `opt-cc-propose-${cid}`

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
                                  {proposeInfo != null ? (
                                    <div
                                      className="space-y-1 rounded-md border bg-muted/30 px-3 py-2 text-xs"
                                      style={{ borderLeft: "3px solid var(--mt-amber)" }}
                                    >
                                      <p className="font-medium text-foreground">
                                        Half-closed loop · proposed draft
                                      </p>
                                      <p className="text-muted-foreground">
                                        {proposeInfo.note ??
                                          "Proposed next batch (decision-support). Nothing has run — committing an execution batch still requires human signoff."}
                                      </p>
                                      <div className="flex flex-wrap gap-x-4 gap-y-1 pt-0.5 text-muted-foreground">
                                        {proposeInfo.proposedFrom != null ? (
                                          <span>
                                            proposed from cycle{" "}
                                            <span className="font-mono text-foreground">
                                              {proposeInfo.proposedFrom}
                                            </span>
                                          </span>
                                        ) : null}
                                        {proposeInfo.flags.requires_human_signoff_before_execution === true ? (
                                          <span className="font-medium text-foreground">
                                            Execution requires human signoff
                                          </span>
                                        ) : null}
                                        {typeof proposeInfo.flags.safety_gate_status === "string" ? (
                                          <span>
                                            safety gate:{" "}
                                            <span className="font-mono text-foreground">
                                              {String(proposeInfo.flags.safety_gate_status).replace(/_/g, " ")}
                                            </span>
                                          </span>
                                        ) : null}
                                      </div>
                                      {proposeInfo.flags.execution_blocked_by_safety === true ? (
                                        <p className="font-medium text-foreground">
                                          Execution is blocked by the safety gate — resolve the rejected
                                          structural-safety screening before this batch can be planned or run.{" "}
                                          <button
                                            type="button"
                                            className={INLINE_LINK_BUTTON_CLASS}
                                            onClick={goToSafetyGate}
                                          >
                                            Open the safety gate (Cost &amp; Safety) →
                                          </button>
                                        </p>
                                      ) : null}
                                    </div>
                                  ) : null}
                                  <div className="space-y-2">
                                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                                      Summary
                                    </p>
                                    <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-3 text-[10px] leading-snug">
                                      {summaryBlob}
                                    </pre>
                                  </div>
                                  {warningsList.length > 0 ? (
                                    <div className="space-y-1">
                                      <p className="text-xs font-medium text-muted-foreground">Warnings</p>
                                      <ul className="list-inside list-disc text-xs text-muted-foreground">
                                        {warningsList.map((w) => (
                                          <li key={`${cid}-w-${w}`}>{w}</li>
                                        ))}
                                      </ul>
                                    </div>
                                  ) : (
                                    <p className="text-xs text-muted-foreground">Warnings — none listed.</p>
                                  )}
                                  {notesList.length > 0 ? (
                                    <div className="space-y-1">
                                      <p className="text-xs font-medium text-muted-foreground">Notes</p>
                                      <ul className="list-inside list-disc text-xs text-muted-foreground">
                                        {notesList.map((n) => (
                                          <li key={`${cid}-n-${n}`}>{n}</li>
                                        ))}
                                      </ul>
                                    </div>
                                  ) : (
                                    <p className="text-xs text-muted-foreground">Notes — none listed.</p>
                                  )}
                                  <div className="space-y-2">
                                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                                      decision record
                                    </p>
                                    {dec != null ? (
                                      <div className="space-y-1 rounded-md border border-border px-3 py-2 text-xs">
                                        <p>
                                          <span className="text-muted-foreground">Decision</span>{" "}
                                          <span className="font-mono capitalize">
                                            {String(dec.decision ?? "").replace(/_/g, " ")}
                                          </span>
                                        </p>
                                        <p className="whitespace-pre-wrap text-muted-foreground">
                                          Rationale:{" "}
                                          <span className="text-foreground">{String(dec.rationale ?? "")}</span>
                                        </p>
                                        {dec.reviewer_name != null ? (
                                          <p className="text-muted-foreground">
                                            Reviewer name:{" "}
                                            <span className="font-mono text-foreground">{String(dec.reviewer_name)}</span>
                                          </p>
                                        ) : null}
                                        {typeof dec.created_at === "string" ? (
                                          <p className="text-muted-foreground">Created {fmtIso(dec.created_at)}</p>
                                        ) : null}
                                      </div>
                                    ) : (
                                      <p className="text-xs text-muted-foreground">
                                        No decision recorded yet.
                                      </p>
                                    )}
                                  </div>
                                  {loopMetrics != null ? (
                                    <div className="space-y-2">
                                      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                                        loop metrics
                                      </p>
                                      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
                                        {[
                                          { label: "total experiments", value: readNum(loopMetrics.total_experiments) },
                                          { label: "new this cycle", value: readNum(loopMetrics.new_experiments) },
                                          { label: "to target", value: readNum(loopMetrics.experiments_to_target) },
                                          { label: "best objective", value: readNum(loopMetrics.best_objective) },
                                          { label: "objective target", value: readNum(loopMetrics.objective_target) },
                                          { label: "gap to target", value: readNum(loopMetrics.objective_gap) },
                                          { label: "latency (s)", value: readNum(loopMetrics.latency_seconds) },
                                        ].map((m) => (
                                          <div key={m.label} className="rounded-md border px-2 py-1.5">
                                            <p className="font-mono text-sm tabular-nums">
                                              {m.value != null ? m.value : "—"}
                                            </p>
                                            <p className="text-[10px] text-muted-foreground">{m.label}</p>
                                          </div>
                                        ))}
                                        <div className="rounded-md border px-2 py-1.5">
                                          <p className="font-mono text-sm">
                                            {loopMetrics.target_met === true
                                              ? "yes"
                                              : loopMetrics.target_met === false
                                                ? "no"
                                                : "—"}
                                          </p>
                                          <p className="text-[10px] text-muted-foreground">target met</p>
                                        </div>
                                      </div>
                                    </div>
                                  ) : null}
                                  {dmtaInfo != null && dmtaInfo.sequence.length > 0 ? (
                                    <div className="space-y-2">
                                      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                                        DMTA loop{dmtaInfo.engine ? ` · ${dmtaInfo.engine}` : ""}
                                      </p>
                                      <div className="flex flex-wrap items-center gap-1.5">
                                        {dmtaInfo.sequence.map((phase, i) => {
                                          const lat = readNum(dmtaInfo.phaseLatencies[phase])
                                          return (
                                            <div key={`${phase}-${i}`} className="flex items-center gap-1.5">
                                              {i > 0 ? (
                                                <span aria-hidden className="text-muted-foreground/50">
                                                  →
                                                </span>
                                              ) : null}
                                              <div className="rounded-md border px-2 py-1 text-center">
                                                <p className="text-xs font-medium capitalize">
                                                  {phase.replace(/_/g, " ")}
                                                </p>
                                                <p className="font-mono text-[10px] tabular-nums text-muted-foreground">
                                                  {lat != null ? `${lat}s` : "—"}
                                                </p>
                                              </div>
                                            </div>
                                          )
                                        })}
                                      </div>
                                      <p className="text-[11px] text-muted-foreground">
                                        Only propose &amp; safety-gate are automated; make / test / learn / decision are
                                        human steps (no latency until performed).
                                      </p>
                                      {dmtaInfo.provenance != null ? (
                                        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
                                          {typeof dmtaInfo.provenance.surrogate_model_version === "string" ? (
                                            <span>
                                              surrogate{" "}
                                              <span className="font-mono text-foreground">
                                                {dmtaInfo.provenance.surrogate_model_version}
                                              </span>
                                            </span>
                                          ) : null}
                                          {Array.isArray(dmtaInfo.provenance.spectracheck_session_ids) &&
                                          dmtaInfo.provenance.spectracheck_session_ids.length > 0 ? (
                                            <span>
                                              SpectraCheck sessions{" "}
                                              <span className="font-mono text-foreground">
                                                {dmtaInfo.provenance.spectracheck_session_ids.join(", ")}
                                              </span>
                                            </span>
                                          ) : null}
                                        </div>
                                      ) : null}
                                    </div>
                                  ) : null}
                                  <div className="space-y-2">
                                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                                      propose next batch
                                    </p>
                                    <p className="text-xs text-muted-foreground">
                                      Decision-support: proposes the next batch as a new{" "}
                                      <span className="font-medium text-foreground">draft</span> cycle. It executes
                                      nothing — committing an execution batch still needs human signoff and passes the
                                      safety gate.
                                    </p>
                                    <div className="flex flex-wrap items-center gap-3">
                                      <Button
                                        type="button"
                                        size="sm"
                                        disabled={!canProposeNext || proposeBusy}
                                        onClick={() => void proposeNextBatch(cid)}
                                      >
                                        {proposeBusy ? "Proposing…" : "Propose next batch"}
                                      </Button>
                                      {!canProposeNext ? (
                                        <span className="text-xs text-muted-foreground">
                                          {latestDecision != null
                                            ? `Unlocks after a "continue optimization" decision — latest is "${latestDecision.replace(/_/g, " ")}".`
                                            : "Record a “continue optimization” decision on this cycle to unlock."}
                                        </span>
                                      ) : null}
                                    </div>
                                    {canProposeNext ? (
                                      <p className="text-[11px] text-muted-foreground">
                                        Sends the Bayesian-Optimization run settings from the{" "}
                                        <button
                                          type="button"
                                          className={INLINE_LINK_BUTTON_CLASS}
                                          onClick={() => setActiveTab("optimization")}
                                        >
                                          Optimization tab
                                        </button>
                                        :{" "}
                                        <span className="font-mono text-foreground">
                                          {boAlgorithm.replace(/_/g, " ")}
                                        </span>{" "}
                                        · batch{" "}
                                        <span className="font-mono text-foreground">
                                          {(() => {
                                            const b = proposeNextRequestBody({ batchSize: boBatchSize })
                                            return typeof b.batch_size === "number" ? b.batch_size : "default"
                                          })()}
                                        </span>{" "}
                                        · safety-aware{" "}
                                        <span className="font-mono text-foreground">
                                          {boSafetyAware ? "on" : "off"}
                                        </span>
                                        .
                                      </p>
                                    ) : null}
                                  </div>
                                  <Separator />
                                  <form className="space-y-4" onSubmit={(e) => void submitOptimizationCycleDecision(cid, e)}>
                                    <p className="text-xs font-medium text-muted-foreground">Record decision</p>
                                    <div className="grid gap-4 md:grid-cols-2">
                                      <div className="space-y-2 md:col-span-2">
                                        <Label htmlFor={`opt-dec-${cid}`}>Decision</Label>
                                        <Select value={occDecision} onValueChange={setOccDecision}>
                                          <SelectTrigger id={`opt-dec-${cid}`}>
                                            <SelectValue />
                                          </SelectTrigger>
                                          <SelectContent>
                                            {REACTION_OPTIMIZATION_CYCLE_DECISION_OPTIONS.map((d) => (
                                              <SelectItem key={`${cid}-${d}`} value={d}>
                                                {optionLabel(d)}
                                              </SelectItem>
                                            ))}
                                          </SelectContent>
                                        </Select>
                                      </div>
                                      <div className="space-y-2 md:col-span-2">
                                        <Label htmlFor={`opt-rat-${cid}`}>Rationale</Label>
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
                                        <Label htmlFor={`opt-rev-${cid}`}>Reviewer name</Label>
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
                  <p className="text-sm text-muted-foreground">No optimization or advisor runs recorded yet.</p>
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

          <DeveloperOnly>
            <ModuleCard
              accent="violet"
              eyebrow="Execution · Developer JSON"
              title="Developer JSON"
              description="Raw execution data (for troubleshooting) — the same values shown elsewhere on this tab."
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
          </DeveloperOnly>
        </TabsContent>

        <TabsContent value="evidence" className="mt-4 space-y-6">
          <div className="space-y-1">
            <p
              className="font-mono text-[11px] font-bold uppercase tracking-[0.2em]"
              style={{ color: "var(--mt-violet-ink)" }}
            >
              Project · Evidence Links
            </p>
            <h2 className="font-mono text-2xl font-bold tracking-tight">SpectraCheck-linked analytical evidence</h2>
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
            title={
              <span className="inline-flex items-center gap-2">
                Evidence Links
                <InfoTooltip content={EVIDENCE_LINKS_TOOLTIP} label="What this table shows" />
              </span>
            }
            description="Every experiment linked to a SpectraCheck session."
          >
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Experiment ID</TableHead>
                    <TableHead>Experiment code</TableHead>
                    <TableHead className="font-mono text-xs">Linked SpectraCheck session</TableHead>
                    <TableHead className="text-xs">Sample ID</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">Unified status</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">Report status</TableHead>
                    <TableHead className="whitespace-nowrap text-xs">QC status</TableHead>
                    <TableHead className="text-right">Evidence records</TableHead>
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
                        No experiments are linked to a SpectraCheck session.
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </div>
          </ModuleCard>
        </TabsContent>

        <TabsContent value="developer" className="mt-4 space-y-6">
          <DeveloperOnly>
            <MlCapabilitiesPanel />
            <div className="space-y-1">
              <p
                className="font-mono text-[11px] font-bold uppercase tracking-[0.2em]"
                style={{ color: "var(--mt-violet-ink)" }}
              >
                Project · Developer JSON
              </p>
              <h2 className="font-mono text-2xl font-bold tracking-tight">{RAW_DATA_DISCLOSURE}</h2>
              <p className="text-sm text-muted-foreground">
                Everything this reaction project loaded in the current browser session — useful for checking exact
                values, audit fields, and warnings.
              </p>
            </div>
            <ModuleCard
              accent="violet"
              eyebrow="Reaction · Developer JSON"
              title="Developer JSON"
              description="Raw data from this reaction project workspace (troubleshooting only)."
            >
              <DeveloperJsonPanel data={devPayload} />
            </ModuleCard>
          </DeveloperOnly>
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
                  Experiment {linkDialogExperimentId}
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
              <Label htmlFor="link-sc-session-id">Session</Label>
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
                Note <span className="font-normal text-muted-foreground">(optional)</span>
              </Label>
              <Textarea
                id="link-sc-note"
                rows={3}
                value={linkNoteInput}
                onChange={(e) => setLinkNoteInput(e.target.value)}
                placeholder="Saved with the link's notes when provided."
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
                          ? "Edit checklist"
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
                      <Label htmlFor="ebd-operator">Operator name</Label>
                      <Input
                        id="ebd-operator"
                        autoComplete="name"
                        value={boardDialogOperator}
                        onChange={(e) => setBoardDialogOperator(e.target.value)}
                        placeholder="Optional"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="ebd-message">Message</Label>
                      <Textarea
                        id="ebd-message"
                        rows={3}
                        className="text-sm"
                        value={boardDialogMessage}
                        onChange={(e) => setBoardDialogMessage(e.target.value)}
                        placeholder={
                          boardDialog.kind === "done"
                            ? "Optional completion note."
                            : "Optional."
                        }
                      />
                    </div>
                  </>
                )}
                {boardDialog.kind === "fail" && (
                  <>
                    <div className="space-y-2">
                      <Label htmlFor="ebd-failure">Failure reason</Label>
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
                      <Label htmlFor="ebd-fail-operator">Operator name</Label>
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
                  <ObjectArrayField
                    key={`ebd-checklist-${boardDialog.itemId}`}
                    label="Checklist"
                    itemLabel="Step"
                    addLabel="Add step"
                    fields={[
                      { key: "task", label: "Task" },
                      { key: "done", label: "Done? (true/false)", type: "text" },
                    ]}
                    initialValue={boardDialogChecklist}
                    onChange={setBoardDialogChecklist}
                    idPrefix="ebd-checklist"
                  />
                )}
                {boardDialog.kind === "note" && (
                  <div className="space-y-2">
                    <Label htmlFor="ebd-note">Note</Label>
                    <Textarea
                      id="ebd-note"
                      rows={4}
                      className="text-sm"
                      value={boardDialogNote}
                      onChange={(e) => setBoardDialogNote(e.target.value)}
                      placeholder="Added to this item's notes."
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
