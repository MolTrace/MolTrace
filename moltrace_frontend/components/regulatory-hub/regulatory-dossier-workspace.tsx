"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch, ApiError } from "@/lib/api/client"
import { formatStableUtcDateTime } from "@/lib/utils"
import {
  trackRegulatoryAiGovernanceRecordCreated,
  trackRegulatoryBatchAssessmentRun,
  trackRegulatoryImpurityRegisterCreated,
  trackRegulatoryJurisdictionalMapCreated,
  trackRegulatoryMethodValidationAssessed,
  trackRegulatoryNitrosamineWatchRun,
  trackRegulatoryQnmrComplianceAssessed,
  trackRegulatoryQueryAnswered,
  trackRegulatoryReadinessReportGenerated,
  trackRegulatoryRequirementAdded,
  trackRegulatoryResidualSolventAssessed,
  trackRegulatoryReviewCompleted,
  trackSubmissionPackageCreated,
} from "@/src/lib/analytics/analytics-client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { cn } from "@/lib/utils"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { MlModelProvenanceSummary } from "@/components/ml/ml-model-provenance-summary"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import {
  NitrosamineCumulativeRiskCard,
  type NitrosamineCumulativeRisk,
} from "@/components/regulatory-hub/nitrosamine-cumulative-risk-card"
import {
  DossierAIDecisionsPanel,
  type AIDecision,
} from "@/components/regulatory-hub/dossier-ai-decisions-panel"
import { Checkbox } from "@/components/ui/checkbox"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { AlertTriangle, ArrowLeft, ChevronDown, Loader2 } from "lucide-react"
import { RegulatoryDossierLinkedCompoundCard } from "@/components/regulatory-hub/regulatory-dossier-linked-compound-card"
import { RegulatoryDossierKnowledgeLinksCard } from "@/components/knowledge/knowledge-links-integration"
import { RegulatoryNotificationsCompactCard } from "@/components/regulatory-hub/regulatory-notifications-compact-card"
import { RegulatoryActionQueue, RegulatoryActionQueueCard } from "@/components/regulatory-hub/regulatory-action-queue"
import { BatchRegulatoryAssessmentPanel } from "@/components/regulatory-hub/batch-regulatory-assessment-panel"
import { ReactionOptimizationHandoffCard } from "@/components/regulatory-hub/reaction-optimization-handoff-card"
import { CtdModule3BundleCard } from "@/components/regulatory-hub/ctd-module3-bundle-card"

const DOSSIER_STATUSES = ["draft", "in_review", "ready", "blocked", "approved", "archived"] as const

const REVIEW_DECISIONS = ["approve", "needs_changes", "reject", "defer"] as const

const REQUIREMENT_CATEGORIES = [
  "identity",
  "analytical_evidence",
  "impurities",
  "safety",
  "stability",
  "manufacturing",
  "documentation",
  "labeling",
  "submission",
  "claim_support",
  "other",
] as const

const REQUIREMENT_PRIORITIES = ["low", "medium", "high", "critical"] as const

const REQUIREMENT_STATUSES = [
  "not_started",
  "in_progress",
  "evidence_needed",
  "review_needed",
  "satisfied",
  "blocked",
  "not_applicable",
] as const

const EVIDENCE_TYPES = [
  "spectracheck_report",
  "unified_evidence",
  "qc_assessment",
  "raw_file_hash",
  "reaction_experiment",
  "reaction_report",
  "analytical_artifact",
  "human_note",
  "other",
] as const

const EVIDENCE_STATUSES = ["linked", "needs_review", "accepted", "rejected"] as const

const QA_SOURCE_SCOPE_OPTIONS = [
  { value: "all_dossier_sources", label: "All dossier sources" },
  { value: "jurisdiction_sources", label: "Jurisdiction sources" },
  { value: "internal_sops", label: "Internal SOPs" },
  { value: "analytical_reports", label: "Analytical reports" },
] as const

const INSUFFICIENT_SOURCES_USER_MESSAGE =
  "Insufficient cited sources are available to answer this question. Upload or select source documents."

const QA_MANDATORY_WARNING =
  "Draft regulatory interpretation. Requires qualified human review."

const IMPURITY_REGISTER_TOOLTIP =
  "Tracks process impurities, degradation products, residual solvents, nitrosamine risks, unknown features, and regulatory threshold triggers for the dossier."

const IMPURITY_TYPES = [
  "process_impurity",
  "degradation_product",
  "residual_solvent",
  "nitrosamine",
  "unknown",
  "other",
] as const

const IMPURITY_SOURCES = [
  "nmr_peak",
  "ms_peak",
  "lcms_feature",
  "reaction_route",
  "user_entered",
  "report",
  "unknown",
] as const

const RESIDUAL_SOLVENT_WATCH_TOOLTIP =
  "Maps detected or reported residual solvents to regulatory solvent classes, permitted exposure concepts, and dossier action items."

const RESIDUAL_SOURCE_EVIDENCE_OPTIONS = [
  { value: "spectracheck_report", label: "SpectraCheck report" },
  { value: "nmr_solvent_flag", label: "NMR solvent/impurity flag" },
  { value: "lcms_feature", label: "LC-MS feature" },
  { value: "user_entered", label: "user-entered" },
  { value: "reaction_route", label: "reaction route" },
] as const

const RESIDUAL_RULE_NOT_CONFIGURED_MSG =
  "Source rule not configured. Add or select a regulatory rule set."

const NITROSAMINE_WATCH_TOOLTIP =
  "Screens structures, impurity records, and evidence links for nitrosamine-related review triggers. Results require qualified review."

const QNMR_METHOD_VALIDATION_TOOLTIP =
  "Assesses whether qNMR or analytical-method outputs include the documentation needed for review, such as ATP, validation parameters, calibration, uncertainty, audit trail, and source hashes."

const AI_GOVERNANCE_RECORD_TOOLTIP =
  "Documents model/method versions, explainability, validation status, human oversight, and audit trail for AI-assisted analytical or regulatory outputs."

const AI_GOVERNANCE_STATUSES = [
  "not_assessed",
  "gaps_identified",
  "ready_for_review",
  "reviewed",
] as const

const SUBMISSION_PACKAGE_TYPES = [
  "ctd_module3",
  "impurity_report",
  "qnmr_validation",
  "ai_governance",
  "readiness_bundle",
  "other",
] as const

const METADATA_REDACT_KEY_RE =
  /secret|token|password|api_key|authorization|bearer|credential|private_key/i

const ANALYTICAL_METHOD_TYPES = [
  "qnmr",
  "nmr_qualitative",
  "hrms",
  "lcms",
  "msms",
  "hplc",
  "uplc",
  "other",
] as const

const REQUIREMENTS_CHECKLIST_TOOLTIP =
  "Requirements are checklist items for a dossier. They should be supported by citations, analytical evidence, or reviewer justification."

const JURISDICTIONAL_MAP_TOOLTIP =
  "Compares dossier requirements, thresholds, source documents, and action items across selected jurisdictions."

const JURISDICTION_MAP_RULE_SOURCE_MSG = "Rule source not configured for this jurisdiction."

const JURISDICTION_PRESET_LABELS = [
  "FDA",
  "EMA",
  "PMDA",
  "Health Canada",
  "MHRA",
  "USP",
  "ICH",
] as const

// ── Two-tier dossier section navigation ──────────────────────────────────
// The dossier has 18 sections. They are organised into discoverable primary
// groups; any group with more than one section exposes a persistent secondary
// nav so every sibling is always visible. This replaces the prior pattern of
// two hidden Select dropdowns (+ "Back to …" buttons) where sub-sections were
// invisible until a dropdown was opened and couldn't be seen once you drilled in.
type DossierNavGroup = { id: string; label: string; sections: string[] }

const DOSSIER_NAV: DossierNavGroup[] = [
  { id: "overview", label: "Overview", sections: ["overview"] },
  { id: "requirements", label: "Requirements & Evidence", sections: ["requirements", "evidence", "compliance-rules"] },
  { id: "impurity-safety", label: "Impurity & Safety", sections: ["impurity-register", "residual-solvents", "nitrosamine-watch"] },
  { id: "quality", label: "Quality & Governance", sections: ["qnmr-method-validation", "ai-governance"] },
  { id: "jurisdiction", label: "Jurisdiction", sections: ["jurisdictional-map", "change-impact"] },
  { id: "review", label: "Review & Readiness", sections: ["action-items", "qa", "risk", "review", "readiness"] },
  { id: "submission", label: "Submission", sections: ["submission-package"] },
  { id: "developer", label: "Developer JSON", sections: ["json"] },
]

const DOSSIER_SECTIONS = DOSSIER_NAV.flatMap((g) => g.sections)

const DOSSIER_SECTION_LABEL: Record<string, string> = {
  overview: "Overview",
  requirements: "Requirements",
  evidence: "Evidence Links",
  "compliance-rules": "Compliance Rules",
  "impurity-register": "Impurity Register",
  "residual-solvents": "Residual Solvent",
  "nitrosamine-watch": "Nitrosamine Watch",
  "qnmr-method-validation": "qNMR / Method Validation",
  "ai-governance": "AI Governance",
  "jurisdictional-map": "Jurisdictional Map",
  "change-impact": "Change Impact",
  "action-items": "Action Items",
  qa: "Cited Q&A",
  risk: "Risk Assessment",
  review: "Review",
  readiness: "Readiness",
  "submission-package": "Submission Package",
  json: "Developer JSON",
}

/** overall_risk → badge palette (high/critical red · medium amber · low green). */
function riskBadgeClass(level: string): string {
  const l = level.toLowerCase()
  if (l === "high" || l === "critical") return "border-destructive/50 text-destructive"
  if (l === "medium" || l === "moderate") return "border-warning/50 text-warning"
  if (l === "low") return "border-success/50 text-success"
  return "text-muted-foreground"
}

function requirementStatusColor(status: string | null | undefined): string | undefined {
  switch ((status ?? "").toLowerCase()) {
    case "satisfied":
      return "var(--mt-green)"
    case "in_progress":
      return "var(--mt-cyan)"
    case "evidence_needed":
    case "review_needed":
      return "var(--mt-amber)"
    case "blocked":
      return "var(--mt-red)"
    default:
      return undefined
  }
}

function resolvePresetJurisdictionId(
  preset: (typeof JURISDICTION_PRESET_LABELS)[number],
  rows: { id: number; name: string }[]
): number | undefined {
  const nm = (re: RegExp) => rows.find((r) => re.test(r.name))?.id
  switch (preset) {
    case "FDA":
      return nm(/\bFDA\b/i) ?? nm(/Food and Drug Administration/i)
    case "EMA":
      return nm(/\bEMA\b/i) ?? nm(/European Medicines Agency/i)
    case "PMDA":
      return nm(/\bPMDA\b/i) ?? nm(/Pharmaceuticals and Medical Devices Agency/i)
    case "Health Canada":
      return nm(/Health Canada/i) ?? nm(/Santé Canada/i)
    case "MHRA":
      return nm(/\bMHRA\b/i) ?? nm(/Medicines and Healthcare products Regulatory Agency/i)
    case "USP":
      return nm(/\bUSP\b/i) ?? nm(/United States Pharmacopeia/i)
    case "ICH":
      return nm(/\bICH\b/i) ?? nm(/International Council for Harmonisation/i)
    default:
      return undefined
  }
}

function jurisdictionalMapWarningLines(rec: Record<string, unknown>): string[] {
  if (Array.isArray(rec.warnings)) {
    return rec.warnings.filter((x): x is string => typeof x === "string")
  }
  return readStringArray(rec, "warnings_json")
}

function jurisdictionalMapNoteLines(rec: Record<string, unknown>): string[] {
  if (Array.isArray(rec.notes)) {
    return rec.notes.filter((x): x is string => typeof x === "string")
  }
  return readStringArray(rec, "notes_json")
}

function countIntListField(row: Record<string, unknown>, key: string): number {
  const v = row[key]
  if (!Array.isArray(v)) return 0
  return v.filter((x) => typeof x === "number" && Number.isFinite(x)).length
}

function readIntListField(row: Record<string, unknown>, key: string): number[] {
  const v = row[key]
  if (!Array.isArray(v)) return []
  return v.filter((x): x is number => typeof x === "number" && Number.isFinite(x))
}

function openEvidenceSourceHref(evidenceType: string | undefined, resourceId: number | undefined): string | null {
  if (!evidenceType) return null
  if (evidenceType === "spectracheck_report" || evidenceType === "unified_evidence" || evidenceType === "qc_assessment") {
    return "/spectracheck"
  }
  if (evidenceType === "analytical_artifact") {
    return "/reports"
  }
  if (
    (evidenceType === "reaction_experiment" || evidenceType === "reaction_report") &&
    resourceId != null &&
    Number.isFinite(resourceId)
  ) {
    return `/reactions/${encodeURIComponent(String(resourceId))}`
  }
  return null
}

function readStringArray(row: Record<string, unknown>, key: string): string[] {
  const v = row[key]
  if (!Array.isArray(v)) return []
  return v.filter((x): x is string => typeof x === "string")
}

function dictListField(row: Record<string, unknown>, key: string): Record<string, unknown>[] {
  const v = row[key]
  if (!Array.isArray(v)) return []
  return v.filter(isRecord) as Record<string, unknown>[]
}

function readReportHashFromMetadata(row: Record<string, unknown>): string | undefined {
  const m = row.metadata_json
  if (!isRecord(m)) return undefined
  return (
    readRecordString(m, "report_hash") ?? readRecordString(m, "sha256") ?? readRecordString(m, "hash") ?? undefined
  )
}

function downloadLinksFromMetadata(row: Record<string, unknown>): { key: string; url: string }[] {
  const m = row.metadata_json
  if (!isRecord(m)) return []
  const out: { key: string; url: string }[] = []
  for (const [k, v] of Object.entries(m)) {
    if (typeof v !== "string" || !v.trim().startsWith("http")) continue
    if (k.toLowerCase().includes("download") || k.toLowerCase().endsWith("_url")) {
      out.push({ key: k, url: v.trim() })
    }
  }
  return out
}

function countRequirementStatus(rows: Record<string, unknown>[], status: string): number {
  return rows.filter((r) => readRecordString(r, "status") === status).length
}

function reviewStatusDisplay(row: Record<string, unknown>): string {
  if ("human_review_required" in row && typeof row.human_review_required === "boolean") {
    return row.human_review_required ? "true" : "false"
  }
  const meta = row.metadata_json
  if (isRecord(meta)) {
    const rs = readRecordString(meta, "review_status")
    if (rs) return rs
  }
  return "—"
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function asArray(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (data && typeof data === "object") {
    const o = data as Record<string, unknown>
    if (Array.isArray(o.items)) return o.items
    if (Array.isArray(o.results)) return o.results
  }
  return []
}

function formatWhen(iso: string | undefined): string {
  return formatStableUtcDateTime(iso)
}

function truncateText(s: string, max: number): string {
  const t = s.trim()
  if (t.length <= max) return t
  return `${t.slice(0, max)}…`
}

type JurisdictionRow = { id: number; name: string }

function parseJurisdictions(raw: unknown): JurisdictionRow[] {
  const rows = asArray(raw).filter(isRecord)
  const out: JurisdictionRow[] = []
  for (const row of rows) {
    const id = readRecordNumber(row, "id")
    const name = readRecordString(row, "name")
    if (id != null && name) out.push({ id, name })
  }
  return out
}

function latestReviewRow(rows: Record<string, unknown>[]): Record<string, unknown> | undefined {
  if (!rows.length) return undefined
  return [...rows].sort((a, b) => {
    const ta = Date.parse(readRecordString(a, "created_at") ?? "") || 0
    const tb = Date.parse(readRecordString(b, "created_at") ?? "") || 0
    return tb - ta
  })[0]
}

function impurityObservedLevelDisplay(row: Record<string, unknown>): string {
  const pct = row.observed_level_percent
  const amt = row.observed_amount
  const parts: string[] = []
  if (typeof pct === "number" && Number.isFinite(pct)) parts.push(`${pct}%`)
  if (typeof amt === "number" && Number.isFinite(amt)) parts.push(`amount ${amt}`)
  return parts.length ? parts.join(" · ") : "—"
}

function impurityWarningsForRow(row: Record<string, unknown>): string[] {
  if (Array.isArray(row.warnings)) {
    return row.warnings.filter((x): x is string => typeof x === "string")
  }
  return readStringArray(row, "warnings_json")
}

function parseResidualSolventLines(text: string): { solvent_name: string; observed_ppm?: number }[] {
  const out: { solvent_name: string; observed_ppm?: number }[] = []
  for (const raw of text.split("\n")) {
    const line = raw.trim()
    if (!line || line.startsWith("#")) continue
    const lastComma = line.lastIndexOf(",")
    if (lastComma > 0) {
      const name = line.slice(0, lastComma).trim()
      const num = Number.parseFloat(line.slice(lastComma + 1).trim())
      if (name && Number.isFinite(num)) {
        out.push({ solvent_name: name, observed_ppm: num })
        continue
      }
    }
    out.push({ solvent_name: line })
  }
  return out
}

function pairResidualSolventRowActions(
  matches: Record<string, unknown>[],
  actionIds: number[]
): (number | undefined)[] {
  let j = 0
  return matches.map((m) => {
    const needs = m.threshold_triggered === true || m.review_required === true
    if (needs && j < actionIds.length) {
      return actionIds[j++]
    }
    return undefined
  })
}

function residualSolventClassLabel(raw: string | undefined): string {
  if (!raw) return "—"
  return raw.replace(/_/g, " ")
}

function regulatoryAssessmentWarnings(a: Record<string, unknown>): string[] {
  if (Array.isArray(a.warnings)) {
    return a.warnings.filter((x): x is string => typeof x === "string")
  }
  return readStringArray(a, "warnings_json")
}

function parseJsonObjectInput(
  raw: string,
  label: string
): { ok: true; value: Record<string, unknown> } | { ok: false; error: string } {
  const t = raw.trim()
  if (!t) return { ok: true, value: {} }
  try {
    const v = JSON.parse(t) as unknown
    if (!v || typeof v !== "object" || Array.isArray(v)) {
      return { ok: false, error: `${label} must be a JSON object.` }
    }
    return { ok: true, value: v as Record<string, unknown> }
  } catch {
    return { ok: false, error: `${label} is not valid JSON.` }
  }
}

function parseOptionalJsonObjectInput(
  raw: string,
  label: string
): { ok: true; value: Record<string, unknown> | undefined } | { ok: false; error: string } {
  const t = raw.trim()
  if (!t) return { ok: true, value: undefined }
  return parseJsonObjectInput(raw, label)
}

function parseCommaSeparatedInts(raw: string): number[] {
  const out: number[] = []
  for (const line of raw.split(/\r?\n/)) {
    for (const part of line.split(",")) {
      const t = part.trim()
      if (!t) continue
      const n = Number.parseInt(t, 10)
      if (Number.isFinite(n)) out.push(n)
    }
  }
  return out
}

function parseOptionalIdField(
  raw: string,
  label: string
): { ok: true; value: number | null } | { ok: false; error: string } {
  const t = raw.trim()
  if (!t) return { ok: true, value: null }
  const n = Number.parseInt(t, 10)
  if (!Number.isFinite(n) || n < 1) {
    return { ok: false, error: `${label} must be empty or a positive integer.` }
  }
  return { ok: true, value: n }
}

function redactValueForDisplay(key: string, value: unknown): unknown {
  if (METADATA_REDACT_KEY_RE.test(key)) return "[redacted]"
  if (Array.isArray(value)) {
    return value.map((item) =>
      item && typeof item === "object" && !Array.isArray(item)
        ? redactMetadataForDisplay(item as Record<string, unknown>)
        : item
    )
  }
  if (value && typeof value === "object") {
    return redactMetadataForDisplay(value as Record<string, unknown>)
  }
  return value
}

function redactMetadataForDisplay(meta: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(meta)) {
    out[k] = redactValueForDisplay(k, v)
  }
  return out
}

function readinessLabel(raw: string | undefined): string {
  if (!raw) return "—"
  return raw.replace(/_/g, " ")
}

function reviewDecisionBadgeVariant(
  decision: string | undefined
): "default" | "secondary" | "destructive" | "outline" {
  if (decision === "reject") return "destructive"
  if (decision === "needs_changes") return "outline"
  if (decision === "defer") return "secondary"
  return "default"
}

export function RegulatoryDossierWorkspace() {
  const params = useParams()
  const rawParam = params?.dossierId
  const dossierId =
    typeof rawParam === "string" && /^\d+$/.test(rawParam) ? Number.parseInt(rawParam, 10) : Number.NaN

  const [loadErr, setLoadErr] = useState("")
  const [loading, setLoading] = useState(true)
  const [dossier, setDossier] = useState<Record<string, unknown> | null>(null)
  const [jurisdictionNameById, setJurisdictionNameById] = useState<Map<number, string>>(new Map())
  const [requirements, setRequirements] = useState<Record<string, unknown>[]>([])
  const [evidenceLinks, setEvidenceLinks] = useState<Record<string, unknown>[]>([])
  const [riskAssessment, setRiskAssessment] = useState<Record<string, unknown> | null>(null)
  const [riskMissing, setRiskMissing] = useState(false)
  const [reviews, setReviews] = useState<Record<string, unknown>[]>([])
  const [readinessReport, setReadinessReport] = useState<Record<string, unknown> | null>(null)

  const [statusDraft, setStatusDraft] = useState<string>("")
  const [patchBusy, setPatchBusy] = useState(false)
  const [patchErr, setPatchErr] = useState("")

  const [qaQuestion, setQaQuestion] = useState("")
  const [qaJurisdictionId, setQaJurisdictionId] = useState<string>("")
  const [qaSourceScope, setQaSourceScope] = useState<string>("")
  const [qaBusy, setQaBusy] = useState(false)
  const [qaErr, setQaErr] = useState("")
  const [queryResult, setQueryResult] = useState<Record<string, unknown> | null>(null)

  const [riskRefreshBusy, setRiskRefreshBusy] = useState(false)
  const [riskActionErr, setRiskActionErr] = useState("")
  const [readinessBusy, setReadinessBusy] = useState(false)
  const [readinessErr, setReadinessErr] = useState("")

  const [reviewReviewerName, setReviewReviewerName] = useState("")
  const [reviewDecision, setReviewDecision] = useState<string>("needs_changes")
  const [reviewRationale, setReviewRationale] = useState("")
  const [reviewSaveBusy, setReviewSaveBusy] = useState(false)
  const [reviewSaveErr, setReviewSaveErr] = useState("")

  const [reqTitle, setReqTitle] = useState("")
  const [reqCategory, setReqCategory] = useState<string>("other")
  const [reqText, setReqText] = useState("")
  const [reqPriority, setReqPriority] = useState<string>("medium")
  const [reqStatus, setReqStatus] = useState<string>("not_started")
  const [reqAddBusy, setReqAddBusy] = useState(false)
  const [reqAddErr, setReqAddErr] = useState("")
  const [reqPatchBusyKey, setReqPatchBusyKey] = useState<string | null>(null)
  const [reqPatchErr, setReqPatchErr] = useState("")
  const [statusDraftByReqId, setStatusDraftByReqId] = useState<Record<number, string>>({})

  const [evRequirementId, setEvRequirementId] = useState<string>("")
  const [evEvidenceType, setEvEvidenceType] = useState<string>("other")
  const [evResourceId, setEvResourceId] = useState("")
  const [evTitle, setEvTitle] = useState("")
  const [evSummary, setEvSummary] = useState("")
  const [evStatus, setEvStatus] = useState<string>("linked")
  const [evAddBusy, setEvAddBusy] = useState(false)
  const [evAddErr, setEvAddErr] = useState("")

  const [impurityRegisterRows, setImpurityRegisterRows] = useState<Record<string, unknown>[]>([])
  const [impName, setImpName] = useState("")
  const [impType, setImpType] = useState<string>("unknown")
  const [impSource, setImpSource] = useState<string>("user_entered")
  const [impLevelPct, setImpLevelPct] = useState("")
  const [impAmount, setImpAmount] = useState("")
  const [impStructural, setImpStructural] = useState("")
  const [impCompoundId, setImpCompoundId] = useState("")
  const [impEvidenceLink, setImpEvidenceLink] = useState("")
  const [impNotes, setImpNotes] = useState("")
  const [impAddBusy, setImpAddBusy] = useState(false)
  const [impAddErr, setImpAddErr] = useState("")
  const [impAssessBusy, setImpAssessBusy] = useState(false)
  const [impAssessErr, setImpAssessErr] = useState("")

  const [residualAssessments, setResidualAssessments] = useState<Record<string, unknown>[]>([])
  const [ruleSets, setRuleSets] = useState<Record<string, unknown>[]>([])
  const [rsSolventLines, setRsSolventLines] = useState("")
  const [rsSourceEvidence, setRsSourceEvidence] = useState("user_entered")
  const [rsRuleSetId, setRsRuleSetId] = useState<string>("none")
  const [rsAssessBusy, setRsAssessBusy] = useState(false)
  const [rsAssessErr, setRsAssessErr] = useState("")

  const [nitrosamineAssessments, setNitrosamineAssessments] = useState<Record<string, unknown>[]>([])
  const [nitrosamineCumulativeRisk, setNitrosamineCumulativeRisk] = useState<NitrosamineCumulativeRisk | null>(null)
  const [naCompoundId, setNaCompoundId] = useState<string>("none")
  const [naImpurityId, setNaImpurityId] = useState<string>("none")
  const [naStructureText, setNaStructureText] = useState("")
  const [naEvidenceLinkId, setNaEvidenceLinkId] = useState<string>("none")
  const [naRuleSetId, setNaRuleSetId] = useState<string>("none")
  const [naBatchId, setNaBatchId] = useState("")
  const [naMeasuredNgPerDay, setNaMeasuredNgPerDay] = useState("")
  const [naBusy, setNaBusy] = useState(false)
  const [naErr, setNaErr] = useState("")

  const [qnmrProfiles, setQnmrProfiles] = useState<Record<string, unknown>[]>([])
  const [methodProfiles, setMethodProfiles] = useState<Record<string, unknown>[]>([])
  const [mvMethodType, setMvMethodType] = useState<string>("qnmr")
  const [mvAtpJson, setMvAtpJson] = useState("{}")
  const [mvValParamsJson, setMvValParamsJson] = useState("{}")
  const [mvCalibration, setMvCalibration] = useState("")
  const [mvInternalStandard, setMvInternalStandard] = useState("")
  const [mvAcqJson, setMvAcqJson] = useState("{}")
  const [mvUncJson, setMvUncJson] = useState("{}")
  const [mvQnmrMetaJson, setMvQnmrMetaJson] = useState("{}")
  const [mvAccuracyJson, setMvAccuracyJson] = useState("")
  const [mvPrecisionJson, setMvPrecisionJson] = useState("")
  const [mvSpecificityJson, setMvSpecificityJson] = useState("")
  const [mvLinearityJson, setMvLinearityJson] = useState("")
  const [mvRangeJson, setMvRangeJson] = useState("")
  const [mvRobustnessJson, setMvRobustnessJson] = useState("")
  const [mvLodLoqJson, setMvLodLoqJson] = useState("")
  const [mvMethodMetaJson, setMvMethodMetaJson] = useState("{}")
  const [mvSourceHash, setMvSourceHash] = useState("")
  const [mvMethodValSource, setMvMethodValSource] = useState("")
  const [mvSpectraEvidenceId, setMvSpectraEvidenceId] = useState<string>("none")
  const [mvAssessBusy, setMvAssessBusy] = useState(false)
  const [mvAssessErr, setMvAssessErr] = useState("")

  const [aiGovernanceRecords, setAiGovernanceRecords] = useState<Record<string, unknown>[]>([])
  const [aiDecisions, setAiDecisions] = useState<AIDecision[]>([])
  const [agName, setAgName] = useState("")
  const [agModelVersionId, setAgModelVersionId] = useState("")
  const [agMethodId, setAgMethodId] = useState("")
  const [agWorkflowRunId, setAgWorkflowRunId] = useState("")
  const [agEvidenceIds, setAgEvidenceIds] = useState("")
  const [agExplainJson, setAgExplainJson] = useState("{}")
  const [agHumanOverride, setAgHumanOverride] = useState(false)
  const [agValidationRecordIds, setAgValidationRecordIds] = useState("")
  const [agGovernanceStatus, setAgGovernanceStatus] = useState("")
  const [agNotesLines, setAgNotesLines] = useState("")
  const [agCreateBusy, setAgCreateBusy] = useState(false)
  const [agCreateErr, setAgCreateErr] = useState("")

  const [jurisdictionalMaps, setJurisdictionalMaps] = useState<Record<string, unknown>[]>([])
  const [jmSelectedIds, setJmSelectedIds] = useState<number[]>([])
  const [jmRuleSetId, setJmRuleSetId] = useState<string>("none")
  const [jmIncNitrosamine, setJmIncNitrosamine] = useState(true)
  const [jmIncResidual, setJmIncResidual] = useState(true)
  const [jmIncQnmr, setJmIncQnmr] = useState(true)
  const [jmIncAiGov, setJmIncAiGov] = useState(true)
  const [jmBuildBusy, setJmBuildBusy] = useState(false)
  const [jmBuildErr, setJmBuildErr] = useState("")
  const [compoundLinkVersion, setCompoundLinkVersion] = useState(0)

  const [changeImpact, setChangeImpact] = useState<Record<string, unknown> | null>(null)
  const [changeImpactErr, setChangeImpactErr] = useState("")
  const [activeTab, setActiveTab] = useState("overview")

  const [submissionPackageByDossier, setSubmissionPackageByDossier] = useState<Record<string, unknown> | null>(null)
  const [submissionPackageById, setSubmissionPackageById] = useState<Record<string, unknown> | null>(null)
  const [submissionPackageIdInput, setSubmissionPackageIdInput] = useState("")
  const [submissionPackageType, setSubmissionPackageType] = useState<string>("readiness_bundle")
  const [spIncludeSpectraCheckReport, setSpIncludeSpectraCheckReport] = useState(true)
  const [spIncludeImpurityRegister, setSpIncludeImpurityRegister] = useState(true)
  const [spIncludeResidualSolventAssessment, setSpIncludeResidualSolventAssessment] = useState(true)
  const [spIncludeNitrosamineWatch, setSpIncludeNitrosamineWatch] = useState(true)
  const [spIncludeQnmrValidation, setSpIncludeQnmrValidation] = useState(true)
  const [spIncludeAiGovernanceRecord, setSpIncludeAiGovernanceRecord] = useState(true)
  const [spIncludeSourceCitations, setSpIncludeSourceCitations] = useState(true)
  const [spIncludeProvenanceHashes, setSpIncludeProvenanceHashes] = useState(true)
  const [spIncludeReviewDecisions, setSpIncludeReviewDecisions] = useState(true)
  const [submissionPackageBusy, setSubmissionPackageBusy] = useState(false)
  const [submissionPackageLookupBusy, setSubmissionPackageLookupBusy] = useState(false)
  const [submissionPackageErr, setSubmissionPackageErr] = useState("")

  const jurisdictions = useMemo(() => {
    return [...jurisdictionNameById.entries()]
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name))
  }, [jurisdictionNameById])

  const jmPresetRows = useMemo(
    () =>
      JURISDICTION_PRESET_LABELS.map((label) => ({
        label,
        id: resolvePresetJurisdictionId(label, jurisdictions),
      })),
    [jurisdictions]
  )

  const load = useCallback(async () => {
    if (!Number.isFinite(dossierId)) {
      setLoading(false)
      setLoadErr("Invalid dossier id.")
      return
    }
    setLoading(true)
    setLoadErr("")
    setRiskMissing(false)
    setReadinessReport(null)
    setQueryResult(null)
    try {
      const [jurRaw, d, reqRaw, evRaw, revRaw] = await Promise.all([
        apiFetch<unknown>("/regulatory/jurisdictions", { method: "GET" }),
        apiFetch<Record<string, unknown>>(`/regulatory/dossiers/${dossierId}`, { method: "GET" }),
        apiFetch<unknown>(`/regulatory/dossiers/${dossierId}/requirements`, { method: "GET" }),
        apiFetch<unknown>(`/regulatory/dossiers/${dossierId}/evidence-links`, { method: "GET" }),
        apiFetch<unknown>(`/regulatory/dossiers/${dossierId}/review`, { method: "GET" }),
      ])
      const jmap = new Map<number, string>()
      for (const j of parseJurisdictions(jurRaw)) jmap.set(j.id, j.name)
      setJurisdictionNameById(jmap)

      setDossier(d)
      setStatusDraft(readRecordString(d, "status") ?? "draft")

      setRequirements(asArray(reqRaw).filter(isRecord) as Record<string, unknown>[])
      setEvidenceLinks(asArray(evRaw).filter(isRecord) as Record<string, unknown>[])
      setReviews(asArray(revRaw).filter(isRecord) as Record<string, unknown>[])

      try {
        const irrRaw = await apiFetch<unknown>(
          `/regulatory/dossiers/${dossierId}/impurity-risk-register`,
          { method: "GET" }
        )
        setImpurityRegisterRows(asArray(irrRaw).filter(isRecord) as Record<string, unknown>[])
      } catch {
        setImpurityRegisterRows([])
      }

      try {
        const rsRaw = await apiFetch<unknown>(
          `/regulatory/dossiers/${dossierId}/residual-solvent-assessment`,
          { method: "GET" }
        )
        setResidualAssessments(asArray(rsRaw).filter(isRecord) as Record<string, unknown>[])
      } catch {
        setResidualAssessments([])
      }

      try {
        // Rehydrate a persisted readiness report on load (v0.24.5). load()
        // resets readinessReport to null above; the in-session generate is a
        // POST, so without this GET a saved report never reappears on reload.
        // The dossier-scoped list read returns newest-first — take [0].
        const rrRaw = await apiFetch<unknown>(
          `/regulatory/dossiers/${dossierId}/readiness-report`,
          { method: "GET" }
        )
        const reports = asArray(rrRaw).filter(isRecord) as Record<string, unknown>[]
        setReadinessReport(reports[0] ?? null)
      } catch {
        setReadinessReport(null)
      }

      try {
        const rulesRaw = await apiFetch<unknown>("/regulatory/rule-sets?status=active", { method: "GET" })
        setRuleSets(asArray(rulesRaw).filter(isRecord) as Record<string, unknown>[])
      } catch {
        setRuleSets([])
      }

      try {
        const nawRaw = await apiFetch<unknown>(
          `/regulatory/dossiers/${dossierId}/nitrosamine-watch`,
          { method: "GET" }
        )
        setNitrosamineAssessments(asArray(nawRaw).filter(isRecord) as Record<string, unknown>[])
      } catch {
        setNitrosamineAssessments([])
      }

      try {
        const ncrRaw = await apiFetch<NitrosamineCumulativeRisk>(
          `/regulatory/dossiers/${dossierId}/nitrosamine-cumulative-risk`,
          { method: "GET" }
        )
        setNitrosamineCumulativeRisk(ncrRaw ?? null)
      } catch {
        setNitrosamineCumulativeRisk(null)
      }

      try {
        const qnmrRaw = await apiFetch<unknown>(`/regulatory/dossiers/${dossierId}/qnmr-compliance`, { method: "GET" })
        setQnmrProfiles(asArray(qnmrRaw).filter(isRecord) as Record<string, unknown>[])
      } catch {
        setQnmrProfiles([])
      }

      try {
        const mvRaw = await apiFetch<unknown>(
          `/regulatory/dossiers/${dossierId}/method-validation-profile`,
          { method: "GET" }
        )
        setMethodProfiles(asArray(mvRaw).filter(isRecord) as Record<string, unknown>[])
      } catch {
        setMethodProfiles([])
      }

      try {
        const agRaw = await apiFetch<unknown>(
          `/regulatory/dossiers/${dossierId}/ai-governance-record`,
          { method: "GET" }
        )
        setAiGovernanceRecords(asArray(agRaw).filter(isRecord) as Record<string, unknown>[])
      } catch {
        setAiGovernanceRecords([])
      }

      try {
        // EU GMP Draft Annex 22 AI-decision chain (newest-first). Empty until
        // the governed AI path writes records; render the empty state.
        const aidRaw = await apiFetch<AIDecision[]>(
          `/regulatory/dossiers/${dossierId}/ai-decisions`,
          { method: "GET" }
        )
        setAiDecisions(Array.isArray(aidRaw) ? aidRaw : [])
      } catch {
        setAiDecisions([])
      }

      try {
        const jmRaw = await apiFetch<unknown>(
          `/regulatory/dossiers/${dossierId}/jurisdictional-map`,
          { method: "GET" }
        )
        setJurisdictionalMaps(asArray(jmRaw).filter(isRecord) as Record<string, unknown>[])
      } catch {
        setJurisdictionalMaps([])
      }

      try {
        const risk = await apiFetch<Record<string, unknown>>(
          `/regulatory/dossiers/${dossierId}/risk-assessment`,
          { method: "GET" }
        )
        setRiskAssessment(risk)
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) {
          setRiskAssessment(null)
          setRiskMissing(true)
        } else {
          setRiskAssessment(null)
          setRiskMissing(false)
        }
      }

      setChangeImpactErr("")
      try {
        const ciRaw = await apiFetch<unknown>(`/regulatory/dossiers/${dossierId}/change-impact`, { method: "GET" })
        setChangeImpact(isRecord(ciRaw) ? ciRaw : null)
      } catch (e) {
        setChangeImpact(null)
        setChangeImpactErr(formatApiError(e, "Could not load change impact."))
      }
    } catch (e) {
      setDossier(null)
      setImpurityRegisterRows([])
      setResidualAssessments([])
      setRuleSets([])
      setNitrosamineAssessments([])
      setQnmrProfiles([])
      setMethodProfiles([])
      setAiGovernanceRecords([])
      setJurisdictionalMaps([])
      setChangeImpact(null)
      setChangeImpactErr("")
      setLoadErr(formatApiError(e, "Could not load dossier."))
    } finally {
      setLoading(false)
    }
  }, [dossierId])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    const next: Record<number, string> = {}
    for (const r of requirements) {
      const id = readRecordNumber(r, "id")
      if (id != null) next[id] = readRecordString(r, "status") ?? "not_started"
    }
    setStatusDraftByReqId(next)
  }, [requirements])

  const refreshRequirements = useCallback(async (): Promise<number | undefined> => {
    if (!Number.isFinite(dossierId)) return undefined
    try {
      const reqRaw = await apiFetch<unknown>(`/regulatory/dossiers/${dossierId}/requirements`, { method: "GET" })
      const rows = asArray(reqRaw).filter(isRecord) as Record<string, unknown>[]
      setRequirements(rows)
      return rows.length
    } catch {
      /* list refresh is best-effort */
      return undefined
    }
  }, [dossierId])

  const refreshEvidenceLinks = useCallback(async (): Promise<number | undefined> => {
    if (!Number.isFinite(dossierId)) return undefined
    try {
      const raw = await apiFetch<unknown>(`/regulatory/dossiers/${dossierId}/evidence-links`, { method: "GET" })
      const rows = asArray(raw).filter(isRecord) as Record<string, unknown>[]
      setEvidenceLinks(rows)
      return rows.length
    } catch {
      /* list refresh is best-effort */
      return undefined
    }
  }, [dossierId])

  const refreshImpurityRegister = useCallback(async () => {
    if (!Number.isFinite(dossierId)) return
    try {
      const raw = await apiFetch<unknown>(
        `/regulatory/dossiers/${dossierId}/impurity-risk-register`,
        { method: "GET" }
      )
      setImpurityRegisterRows(asArray(raw).filter(isRecord) as Record<string, unknown>[])
    } catch {
      /* list refresh is best-effort */
    }
  }, [dossierId])

  const refreshResidualAssessments = useCallback(async () => {
    if (!Number.isFinite(dossierId)) return
    try {
      const raw = await apiFetch<unknown>(
        `/regulatory/dossiers/${dossierId}/residual-solvent-assessment`,
        { method: "GET" }
      )
      setResidualAssessments(asArray(raw).filter(isRecord) as Record<string, unknown>[])
    } catch {
      /* list refresh is best-effort */
    }
  }, [dossierId])

  const refreshRuleSets = useCallback(async () => {
    try {
      const rulesRaw = await apiFetch<unknown>("/regulatory/rule-sets?status=active", { method: "GET" })
      setRuleSets(asArray(rulesRaw).filter(isRecord) as Record<string, unknown>[])
    } catch {
      /* list refresh is best-effort */
    }
  }, [])

  const refreshNitrosamineAssessments = useCallback(async () => {
    if (!Number.isFinite(dossierId)) return
    try {
      const raw = await apiFetch<unknown>(
        `/regulatory/dossiers/${dossierId}/nitrosamine-watch`,
        { method: "GET" }
      )
      setNitrosamineAssessments(asArray(raw).filter(isRecord) as Record<string, unknown>[])
    } catch {
      /* list refresh is best-effort */
    }
  }, [dossierId])

  const refreshNitrosamineCumulativeRisk = useCallback(async () => {
    if (!Number.isFinite(dossierId)) return
    try {
      const raw = await apiFetch<NitrosamineCumulativeRisk>(
        `/regulatory/dossiers/${dossierId}/nitrosamine-cumulative-risk`,
        { method: "GET" }
      )
      setNitrosamineCumulativeRisk(raw ?? null)
    } catch {
      /* rollup refresh is best-effort; null renders an "unavailable" note */
      setNitrosamineCumulativeRisk(null)
    }
  }, [dossierId])

  const refreshQnmrProfiles = useCallback(async () => {
    if (!Number.isFinite(dossierId)) return
    try {
      const raw = await apiFetch<unknown>(`/regulatory/dossiers/${dossierId}/qnmr-compliance`, { method: "GET" })
      setQnmrProfiles(asArray(raw).filter(isRecord) as Record<string, unknown>[])
    } catch {
      /* list refresh is best-effort */
    }
  }, [dossierId])

  const refreshMethodProfiles = useCallback(async () => {
    if (!Number.isFinite(dossierId)) return
    try {
      const raw = await apiFetch<unknown>(
        `/regulatory/dossiers/${dossierId}/method-validation-profile`,
        { method: "GET" }
      )
      setMethodProfiles(asArray(raw).filter(isRecord) as Record<string, unknown>[])
    } catch {
      /* list refresh is best-effort */
    }
  }, [dossierId])

  const refreshAiGovernanceRecords = useCallback(async () => {
    if (!Number.isFinite(dossierId)) return
    try {
      const raw = await apiFetch<unknown>(
        `/regulatory/dossiers/${dossierId}/ai-governance-record`,
        { method: "GET" }
      )
      setAiGovernanceRecords(asArray(raw).filter(isRecord) as Record<string, unknown>[])
    } catch {
      /* list refresh is best-effort */
    }
  }, [dossierId])

  const refreshAiDecisions = useCallback(async () => {
    if (!Number.isFinite(dossierId)) return
    try {
      const raw = await apiFetch<AIDecision[]>(
        `/regulatory/dossiers/${dossierId}/ai-decisions`,
        { method: "GET" }
      )
      setAiDecisions(Array.isArray(raw) ? raw : [])
    } catch {
      /* list refresh is best-effort */
    }
  }, [dossierId])

  const refreshJurisdictionalMaps = useCallback(async () => {
    if (!Number.isFinite(dossierId)) return
    try {
      const raw = await apiFetch<unknown>(
        `/regulatory/dossiers/${dossierId}/jurisdictional-map`,
        { method: "GET" }
      )
      setJurisdictionalMaps(asArray(raw).filter(isRecord) as Record<string, unknown>[])
    } catch {
      /* list refresh is best-effort */
    }
  }, [dossierId])

  const refreshReviews = useCallback(async () => {
    if (!Number.isFinite(dossierId)) return
    try {
      const revRaw = await apiFetch<unknown>(`/regulatory/dossiers/${dossierId}/review`, { method: "GET" })
      setReviews(asArray(revRaw).filter(isRecord) as Record<string, unknown>[])
    } catch {
      /* list refresh is best-effort */
    }
  }, [dossierId])

  const refreshDossier = useCallback(async (): Promise<Record<string, unknown> | null> => {
    if (!Number.isFinite(dossierId)) return null
    try {
      const d = await apiFetch<Record<string, unknown>>(`/regulatory/dossiers/${dossierId}`, { method: "GET" })
      setDossier(d)
      setStatusDraft(readRecordString(d, "status") ?? "draft")
      return d
    } catch {
      /* best-effort */
      return null
    }
  }, [dossierId])

  const requirementTitleById = useMemo(() => {
    const m = new Map<number, string>()
    for (const r of requirements) {
      const id = readRecordNumber(r, "id")
      if (id != null) m.set(id, readRecordString(r, "title") ?? `requirement_id ${id}`)
    }
    return m
  }, [requirements])

  const jurisdictionLabel = useMemo(() => {
    if (!dossier) return "—"
    const jid = readRecordNumber(dossier, "jurisdiction_id")
    if (jid == null) return "—"
    return jurisdictionNameById.get(jid) ?? `jurisdiction_id ${jid}`
  }, [dossier, jurisdictionNameById])

  const changeImpactAssessments = useMemo(() => {
    if (!changeImpact) return []
    return asArray(changeImpact["impact_assessments"]).filter(isRecord) as Record<string, unknown>[]
  }, [changeImpact])

  const dossierChangeImpactEvents = useMemo(() => {
    if (!changeImpact) return []
    return asArray(changeImpact["change_events"]).filter(isRecord) as Record<string, unknown>[]
  }, [changeImpact])

  const dossierMergedRequirementIds = useMemo(() => {
    const s = new Set<number>()
    for (const a of changeImpactAssessments) {
      for (const n of readIntListField(a, "impacted_requirements_json")) s.add(n)
    }
    return [...s].sort((x, y) => x - y)
  }, [changeImpactAssessments])

  const dossierMergedActionItemIds = useMemo(() => {
    const s = new Set<number>()
    if (changeImpact) {
      for (const n of readIntListField(changeImpact, "action_item_ids_json")) s.add(n)
    }
    for (const a of changeImpactAssessments) {
      for (const n of readIntListField(a, "impacted_action_items_json")) s.add(n)
    }
    return [...s].sort((x, y) => x - y)
  }, [changeImpact, changeImpactAssessments])

  const dossierMergedRuleSetIds = useMemo(() => {
    const s = new Set<number>()
    for (const a of changeImpactAssessments) {
      for (const n of readIntListField(a, "impacted_rule_sets_json")) s.add(n)
    }
    return [...s].sort((x, y) => x - y)
  }, [changeImpactAssessments])

  const dossierMergedRecommendedActions = useMemo(() => {
    const out: Record<string, unknown>[] = []
    for (const a of changeImpactAssessments) {
      const raw = a["recommended_actions_json"]
      if (!Array.isArray(raw)) continue
      for (const item of raw) {
        if (isRecord(item)) out.push(item)
      }
    }
    return out
  }, [changeImpactAssessments])

  const requirementsSummary = useMemo(() => {
    const total = requirements.length
    const need = requirements.filter((r) => readRecordString(r, "status") === "evidence_needed").length
    return { total, need }
  }, [requirements])

  const evidenceGapCount = useMemo(() => {
    if (riskAssessment && Array.isArray(riskAssessment.missing_evidence_json)) {
      return riskAssessment.missing_evidence_json.length
    }
    return requirementsSummary.need
  }, [riskAssessment, requirementsSummary.need])

  const complianceCategoryCounts = useMemo(() => {
    const m = new Map<string, number>()
    for (const c of REQUIREMENT_CATEGORIES) m.set(c, 0)
    for (const r of requirements) {
      const c = readRecordString(r, "category") ?? "other"
      m.set(c, (m.get(c) ?? 0) + 1)
    }
    return m
  }, [requirements])

  const latestReview = useMemo(() => latestReviewRow(reviews), [reviews])

  const reviewStateLabel = useMemo(() => {
    if (!latestReview) return "No review decisions recorded."
    const dec = readRecordString(latestReview, "decision") ?? "—"
    const when = formatWhen(readRecordString(latestReview, "created_at"))
    return `Latest: ${dec.replace(/_/g, " ")} (${when})`
  }, [latestReview])

  const activeRuleSetsForDossier = useMemo(() => {
    if (!dossier) return []
    const jid = readRecordNumber(dossier, "jurisdiction_id")
    return ruleSets.filter((r) => {
      if (readRecordString(r, "status") !== "active") return false
      const j = readRecordNumber(r, "jurisdiction_id")
      return j == null || j === jid
    })
  }, [dossier, ruleSets])

  const latestResidualSolventAssessment = useMemo(() => {
    for (const a of residualAssessments) {
      const summary = a.residual_solvent_summary_json
      if (!summary || typeof summary !== "object") continue
      const m = (summary as Record<string, unknown>).matched_solvents
      if (Array.isArray(m) && m.length > 0) return a
    }
    return null
  }, [residualAssessments])

  const residualSolventMissingRuleHint = useMemo(() => {
    if (activeRuleSetsForDossier.length === 0) return true
    const latest = latestResidualSolventAssessment
    if (!latest) return false
    return regulatoryAssessmentWarnings(latest).some((w) => w.includes("source_needed"))
  }, [activeRuleSetsForDossier.length, latestResidualSolventAssessment])

  const nitrosamineCompoundChoices = useMemo(() => {
    const s = new Set<number>()
    for (const r of impurityRegisterRows) {
      const c = readRecordNumber(r, "compound_id")
      if (c != null) s.add(c)
    }
    return [...s].sort((a, b) => a - b)
  }, [impurityRegisterRows])

  const latestNitrosamineAssessment = useMemo(() => {
    for (const a of nitrosamineAssessments) {
      const s = a.nitrosamine_summary_json
      if (s && typeof s === "object" && Object.keys(s as Record<string, unknown>).length > 0) return a
    }
    return null
  }, [nitrosamineAssessments])

  const latestQnmrProfile = useMemo(() => qnmrProfiles[0] ?? null, [qnmrProfiles])

  const latestMethodProfile = useMemo(() => methodProfiles[0] ?? null, [methodProfiles])

  async function addRequirement() {
    if (!Number.isFinite(dossierId)) return
    const title = reqTitle.trim()
    const requirement_text = reqText.trim()
    if (!title) {
      setReqAddErr("title is required.")
      return
    }
    if (!requirement_text) {
      setReqAddErr("requirement_text is required.")
      return
    }
    setReqAddBusy(true)
    setReqAddErr("")
    try {
      await apiFetch(`/regulatory/dossiers/${dossierId}/requirements`, {
        method: "POST",
        body: {
          title,
          category: reqCategory,
          requirement_text,
          priority: reqPriority,
          status: reqStatus,
          citation_ids_json: [],
          evidence_link_ids_json: [],
        },
      })
      setReqTitle("")
      setReqText("")
      setReqCategory("other")
      setReqPriority("medium")
      setReqStatus("not_started")
      const reqCount = await refreshRequirements()
      if (dossier && reqCount != null) {
        const jid = readRecordNumber(dossier, "jurisdiction_id")
        const evCount = evidenceLinks.length
        trackRegulatoryRequirementAdded({
          dossier_id: dossierId,
          jurisdiction_id: jid ?? null,
          status: readRecordString(dossier, "status") ?? undefined,
          requirement_count: reqCount,
          evidence_link_count: evCount,
        })
      }
    } catch (e) {
      setReqAddErr(formatApiError(e, "Add requirement failed."))
    } finally {
      setReqAddBusy(false)
    }
  }

  async function addImpurityRegisterEntry() {
    if (!Number.isFinite(dossierId)) return
    setImpAddBusy(true)
    setImpAddErr("")
    try {
      const body: Record<string, unknown> = {
        impurity_type: impType,
        source: impSource,
        warnings_json: [],
        notes_json: impNotes.trim() ? [impNotes.trim()] : [],
        metadata_json: {},
      }
      const name = impName.trim()
      if (name) body.impurity_name = name
      if (impLevelPct.trim()) {
        const n = Number.parseFloat(impLevelPct)
        if (!Number.isFinite(n) || n < 0) {
          setImpAddErr("observed_level_percent must be a number ≥ 0.")
          return
        }
        body.observed_level_percent = n
      }
      if (impAmount.trim()) {
        const n = Number.parseFloat(impAmount)
        if (!Number.isFinite(n) || n < 0) {
          setImpAddErr("observed_amount must be a number ≥ 0.")
          return
        }
        body.observed_amount = n
      }
      if (impStructural.trim()) body.structural_assignment = impStructural.trim()
      const cid = impCompoundId.trim()
      if (cid) {
        const n = Number.parseInt(cid, 10)
        if (!Number.isFinite(n) || n < 1) {
          setImpAddErr("compound_id must be a positive integer when provided.")
          return
        }
        body.compound_id = n
      }
      if (impEvidenceLink.trim()) {
        const n = Number.parseInt(impEvidenceLink, 10)
        if (!Number.isFinite(n) || n < 1) {
          setImpAddErr("evidence_link_id must be a positive integer when provided.")
          return
        }
        body.evidence_link_id = n
      }
      await apiFetch(`/regulatory/dossiers/${dossierId}/impurity-risk-register`, {
        method: "POST",
        body,
      })
      trackRegulatoryImpurityRegisterCreated({
        dossier_id: dossierId,
        risk_category: impType,
        status: impSource,
      })
      setImpName("")
      setImpLevelPct("")
      setImpAmount("")
      setImpStructural("")
      setImpCompoundId("")
      setImpEvidenceLink("")
      setImpNotes("")
      setImpType("unknown")
      setImpSource("user_entered")
      await refreshImpurityRegister()
    } catch (e) {
      setImpAddErr(formatApiError(e, "Add impurity register entry failed."))
    } finally {
      setImpAddBusy(false)
    }
  }

  async function runRegisterAssessment() {
    if (!Number.isFinite(dossierId)) return
    setImpAssessBusy(true)
    setImpAssessErr("")
    try {
      await apiFetch(`/regulatory/dossiers/${dossierId}/batch-assessment`, {
        method: "POST",
        body: { metadata_json: {} },
      })
      trackRegulatoryBatchAssessmentRun({ dossier_id: dossierId, status: "register_assessment" })
    } catch (e) {
      setImpAssessErr(formatApiError(e, "Run register assessment failed."))
    } finally {
      setImpAssessBusy(false)
    }
  }

  async function runAssessResidualSolvents() {
    if (!Number.isFinite(dossierId)) return
    const parsed = parseResidualSolventLines(rsSolventLines)
    if (parsed.length === 0) {
      setRsAssessErr("Add at least one detected solvent (one per line).")
      return
    }
    setRsAssessBusy(true)
    setRsAssessErr("")
    try {
      const solvents_json = parsed.map((s) => {
        const row: Record<string, unknown> = { solvent_name: s.solvent_name }
        if (s.observed_ppm !== undefined) row.observed_ppm = s.observed_ppm
        return row
      })
      const metadata_json: Record<string, unknown> = {
        source_evidence: rsSourceEvidence,
      }
      if (rsRuleSetId !== "none" && rsRuleSetId.trim()) {
        const n = Number.parseInt(rsRuleSetId, 10)
        if (Number.isFinite(n) && n >= 1) {
          metadata_json.selected_rule_set_id = n
        }
      }
      await apiFetch(`/regulatory/dossiers/${dossierId}/residual-solvent-assessment`, {
        method: "POST",
        body: { solvents_json, metadata_json },
      })
      trackRegulatoryResidualSolventAssessed({
        dossier_id: dossierId,
        action_item_count: solvents_json.length,
        status: rsRuleSetId !== "none" && rsRuleSetId.trim() ? "rule_set_selected" : "no_rule_set",
      })
      await Promise.all([refreshResidualAssessments(), refreshRuleSets()])
    } catch (e) {
      setRsAssessErr(formatApiError(e, "Assess residual solvents failed."))
    } finally {
      setRsAssessBusy(false)
    }
  }

  async function runNitrosamineWatch() {
    if (!Number.isFinite(dossierId)) return
    const hasInput =
      naStructureText.trim().length > 0 || naImpurityId !== "none" || naEvidenceLinkId !== "none"
    if (!hasInput) {
      setNaErr(
        "Add structure_text and/or select an impurity risk register row or regulatory evidence link so risk_signals_json is meaningful."
      )
      return
    }
    setNaBusy(true)
    setNaErr("")
    try {
      const risk_signals_json: Record<string, unknown>[] = []
      if (naImpurityId !== "none") {
        const iid = Number.parseInt(naImpurityId, 10)
        if (Number.isFinite(iid)) {
          const row = impurityRegisterRows.find((r) => readRecordNumber(r, "id") === iid)
          const sig: Record<string, unknown> = { impurity_risk_register_id: iid }
          const iname = row ? readRecordString(row, "impurity_name") : undefined
          const iassign = row ? readRecordString(row, "structural_assignment") : undefined
          if (iname) sig.impurity_name = iname
          if (iassign) sig.structural_assignment = iassign
          risk_signals_json.push(sig)
        }
      }
      if (naEvidenceLinkId !== "none") {
        const eid = Number.parseInt(naEvidenceLinkId, 10)
        if (Number.isFinite(eid)) {
          const ev = evidenceLinks.find((r) => readRecordNumber(r, "id") === eid)
          const sig: Record<string, unknown> = { regulatory_evidence_link_id: eid }
          const title = ev ? readRecordString(ev, "title") : undefined
          const summary = ev ? readRecordString(ev, "summary") : undefined
          if (title) sig.evidence_title = title
          if (summary) sig.evidence_summary = summary
          risk_signals_json.push(sig)
        }
      }
      const metadata_json: Record<string, unknown> = {}
      if (naRuleSetId !== "none" && naRuleSetId.trim()) {
        const rsid = Number.parseInt(naRuleSetId, 10)
        if (Number.isFinite(rsid) && rsid >= 1) metadata_json.selected_rule_set_id = rsid
      }
      if (naImpurityId !== "none") {
        const iid = Number.parseInt(naImpurityId, 10)
        if (Number.isFinite(iid) && iid >= 1) metadata_json.impurity_risk_register_id = iid
      }
      if (naEvidenceLinkId !== "none") {
        const eid = Number.parseInt(naEvidenceLinkId, 10)
        if (Number.isFinite(eid) && eid >= 1) metadata_json.regulatory_evidence_link_id = eid
      }
      const body: Record<string, unknown> = {
        risk_signals_json,
        metadata_json,
      }
      const st = naStructureText.trim()
      if (st) body.structure_text = st
      if (naCompoundId !== "none") {
        const cid = Number.parseInt(naCompoundId, 10)
        if (Number.isFinite(cid) && cid >= 1) body.compound_id = cid
      }
      const bid = naBatchId.trim()
      if (bid) {
        const b = Number.parseInt(bid, 10)
        if (Number.isFinite(b) && b >= 1) body.batch_id = b
      }
      const mngpd = naMeasuredNgPerDay.trim()
      if (mngpd) {
        const m = Number.parseFloat(mngpd)
        if (Number.isFinite(m) && m >= 0) body.measured_ng_per_day = m
      }
      await apiFetch(`/regulatory/dossiers/${dossierId}/nitrosamine-watch`, {
        method: "POST",
        body,
      })
      trackRegulatoryNitrosamineWatchRun({
        dossier_id: dossierId,
        action_item_count: risk_signals_json.length,
        risk_category: naRuleSetId !== "none" && naRuleSetId.trim() ? "rule_set_selected" : "no_rule_set",
      })
      await Promise.all([
        refreshNitrosamineAssessments(),
        refreshNitrosamineCumulativeRisk(),
        refreshRuleSets(),
      ])
    } catch (e) {
      setNaErr(formatApiError(e, "Run nitrosamine watch failed."))
    } finally {
      setNaBusy(false)
    }
  }

  async function runAssessMethodValidationReadiness() {
    if (!Number.isFinite(dossierId)) return
    setMvAssessBusy(true)
    setMvAssessErr("")
    try {
      const atp = parseJsonObjectInput(mvAtpJson, "analytical_target_profile_json")
      if (!atp.ok) {
        setMvAssessErr(atp.error)
        return
      }
      const vp = parseJsonObjectInput(mvValParamsJson, "validation_parameters_json")
      if (!vp.ok) {
        setMvAssessErr(vp.error)
        return
      }
      const acq = parseJsonObjectInput(mvAcqJson, "acquisition_parameters_json")
      if (!acq.ok) {
        setMvAssessErr(acq.error)
        return
      }
      const unc = parseJsonObjectInput(mvUncJson, "uncertainty_summary_json")
      if (!unc.ok) {
        setMvAssessErr(unc.error)
        return
      }
      const qmeta = parseJsonObjectInput(mvQnmrMetaJson, "metadata_json")
      if (!qmeta.ok) {
        setMvAssessErr(qmeta.error)
        return
      }
      const metadataQnmr: Record<string, unknown> = { ...qmeta.value }
      if (mvSourceHash.trim()) metadataQnmr.source_hash = mvSourceHash.trim()
      if (mvSpectraEvidenceId !== "none") {
        const eid = Number.parseInt(mvSpectraEvidenceId, 10)
        if (Number.isFinite(eid) && eid >= 1) metadataQnmr.regulatory_evidence_link_id = eid
      }
      const sess = dossier ? readRecordNumber(dossier, "spectracheck_session_id") : null
      if (sess != null && metadataQnmr.spectracheck_session_id === undefined) {
        metadataQnmr.spectracheck_session_id = sess
      }

      const qnmrBody: Record<string, unknown> = {
        analytical_target_profile_json: atp.value,
        validation_parameters_json: vp.value,
        acquisition_parameters_json: acq.value,
        uncertainty_summary_json: unc.value,
        metadata_json: metadataQnmr,
        warnings_json: [],
        notes_json: [],
        citations_json: [],
      }
      const cal = mvCalibration.trim()
      if (cal) qnmrBody.calibration_method = cal
      const istd = mvInternalStandard.trim()
      if (istd) qnmrBody.internal_standard = istd

      const acc = parseOptionalJsonObjectInput(mvAccuracyJson, "accuracy_json")
      if (!acc.ok) {
        setMvAssessErr(acc.error)
        return
      }
      const prec = parseOptionalJsonObjectInput(mvPrecisionJson, "precision_json")
      if (!prec.ok) {
        setMvAssessErr(prec.error)
        return
      }
      const spec = parseOptionalJsonObjectInput(mvSpecificityJson, "specificity_json")
      if (!spec.ok) {
        setMvAssessErr(spec.error)
        return
      }
      const lin = parseOptionalJsonObjectInput(mvLinearityJson, "linearity_json")
      if (!lin.ok) {
        setMvAssessErr(lin.error)
        return
      }
      const rng = parseOptionalJsonObjectInput(mvRangeJson, "range_json")
      if (!rng.ok) {
        setMvAssessErr(rng.error)
        return
      }
      const rob = parseOptionalJsonObjectInput(mvRobustnessJson, "robustness_json")
      if (!rob.ok) {
        setMvAssessErr(rob.error)
        return
      }
      const lod = parseOptionalJsonObjectInput(mvLodLoqJson, "lod_loq_json")
      if (!lod.ok) {
        setMvAssessErr(lod.error)
        return
      }
      const mmeta = parseJsonObjectInput(mvMethodMetaJson, "metadata_json")
      if (!mmeta.ok) {
        setMvAssessErr(mmeta.error)
        return
      }
      const methodMeta: Record<string, unknown> = { ...mmeta.value }
      const mvs = mvMethodValSource.trim()
      if (mvs) methodMeta.method_validation_source = mvs

      const methodBody: Record<string, unknown> = {
        method_type: mvMethodType,
        analytical_target_profile_json: atp.value,
        warnings_json: [],
        notes_json: [],
        metadata_json: methodMeta,
      }
      if (acc.value !== undefined) methodBody.accuracy_json = acc.value
      if (prec.value !== undefined) methodBody.precision_json = prec.value
      if (spec.value !== undefined) methodBody.specificity_json = spec.value
      if (lin.value !== undefined) methodBody.linearity_json = lin.value
      if (rng.value !== undefined) methodBody.range_json = rng.value
      if (rob.value !== undefined) methodBody.robustness_json = rob.value
      if (lod.value !== undefined) methodBody.lod_loq_json = lod.value

      await apiFetch(`/regulatory/dossiers/${dossierId}/qnmr-compliance`, {
        method: "POST",
        body: qnmrBody,
      })
      await apiFetch(`/regulatory/dossiers/${dossierId}/method-validation-profile`, {
        method: "POST",
        body: methodBody,
      })
      const citJson = qnmrBody.citations_json
      const hasCit = Array.isArray(citJson) && citJson.length > 0
      trackRegulatoryQnmrComplianceAssessed({
        dossier_id: dossierId,
        readiness_status: mvCalibration.trim() ? "calibration_declared" : "no_calibration_declared",
        has_citations: hasCit,
      })
      trackRegulatoryMethodValidationAssessed({
        dossier_id: dossierId,
        readiness_status: mvMethodType,
      })
      await Promise.all([refreshQnmrProfiles(), refreshMethodProfiles()])
    } catch (e) {
      setMvAssessErr(formatApiError(e, "Assess method validation readiness failed."))
    } finally {
      setMvAssessBusy(false)
    }
  }

  async function createAiGovernanceRecord() {
    if (!Number.isFinite(dossierId)) return
    const name = agName.trim()
    if (!name) {
      setAgCreateErr("ai_system_name is required.")
      return
    }
    setAgCreateBusy(true)
    setAgCreateErr("")
    try {
      const explain = parseJsonObjectInput(agExplainJson, "explainability_summary_json")
      if (!explain.ok) {
        setAgCreateErr(explain.error)
        return
      }
      const mvid = parseOptionalIdField(agModelVersionId, "model_version_id")
      if (!mvid.ok) {
        setAgCreateErr(mvid.error)
        return
      }
      const mid = parseOptionalIdField(agMethodId, "method_id")
      if (!mid.ok) {
        setAgCreateErr(mid.error)
        return
      }
      const wf = parseOptionalIdField(agWorkflowRunId, "workflow_run_id")
      if (!wf.ok) {
        setAgCreateErr(wf.error)
        return
      }

      const body: Record<string, unknown> = {
        ai_system_name: name,
        model_version_id: mvid.value,
        method_id: mid.value,
        workflow_run_id: wf.value,
        evidence_item_ids_json: parseCommaSeparatedInts(agEvidenceIds),
        explainability_summary_json: explain.value,
        human_override_available: agHumanOverride,
        validation_record_ids_json: parseCommaSeparatedInts(agValidationRecordIds),
        warnings_json: [],
        notes_json: agNotesLines.split(/\r?\n/).map((s) => s.trim()).filter(Boolean),
        metadata_json: {},
      }
      const gs = agGovernanceStatus.trim()
      body.governance_status = gs ? gs : null

      await apiFetch(`/regulatory/dossiers/${dossierId}/ai-governance-record`, {
        method: "POST",
        body,
      })
      trackRegulatoryAiGovernanceRecordCreated({
        dossier_id: dossierId,
        status: gs || undefined,
      })
      await refreshAiGovernanceRecords()
    } catch (e) {
      setAgCreateErr(formatApiError(e, "Create AI governance record failed."))
    } finally {
      setAgCreateBusy(false)
    }
  }

  const toggleJmJurisdictionId = useCallback((id: number, checked: boolean) => {
    setJmSelectedIds((prev) => {
      const s = new Set(prev)
      if (checked) s.add(id)
      else s.delete(id)
      return [...s].sort((a, b) => a - b)
    })
  }, [])

  async function buildJurisdictionalMap() {
    if (!Number.isFinite(dossierId)) return
    const sorted = [...new Set(jmSelectedIds)].sort((a, b) => a - b)
    if (sorted.length === 0) {
      setJmBuildErr("Select at least one jurisdiction.")
      return
    }
    setJmBuildBusy(true)
    setJmBuildErr("")
    try {
      const jurisdiction_id = sorted[0]
      const compare_jurisdiction_ids_json = sorted.slice(1)
      let rule_set_id: number | null = null
      if (jmRuleSetId !== "none") {
        const rs = Number.parseInt(jmRuleSetId, 10)
        if (!Number.isFinite(rs) || rs < 1) {
          setJmBuildErr("rule_set_id must be empty or a positive integer.")
          return
        }
        rule_set_id = rs
      }
      const body: Record<string, unknown> = {
        jurisdiction_id,
        rule_set_id,
        compare_jurisdiction_ids_json,
        metadata_json: {
          include_nitrosamine_rules: jmIncNitrosamine,
          include_residual_solvent_rules: jmIncResidual,
          include_qnmr_method_validation_rules: jmIncQnmr,
          include_ai_governance_rules: jmIncAiGov,
        },
      }
      await apiFetch(`/regulatory/dossiers/${dossierId}/jurisdictional-map`, {
        method: "POST",
        body,
      })
      trackRegulatoryJurisdictionalMapCreated({
        dossier_id: dossierId,
        jurisdiction_count: sorted.length,
      })
      await refreshJurisdictionalMaps()
    } catch (e) {
      setJmBuildErr(formatApiError(e, "Build jurisdictional map failed."))
    } finally {
      setJmBuildBusy(false)
    }
  }

  async function linkEvidence() {
    if (!Number.isFinite(dossierId)) return
    const title = evTitle.trim()
    const summary = evSummary.trim()
    if (!title) {
      setEvAddErr("title is required.")
      return
    }
    if (!summary) {
      setEvAddErr("summary is required.")
      return
    }
    setEvAddBusy(true)
    setEvAddErr("")
    try {
      const body: Record<string, unknown> = {
        evidence_type: evEvidenceType,
        title,
        summary,
        status: evStatus,
        metadata_json: {},
      }
      const rid = evResourceId.trim()
      if (rid) {
        const n = Number.parseInt(rid, 10)
        if (!Number.isFinite(n)) {
          setEvAddErr("resource_id must be numeric when provided.")
          setEvAddBusy(false)
          return
        }
        body.resource_id = n
      }
      const reqSel = evRequirementId.trim()
      if (reqSel) {
        const n = Number.parseInt(reqSel, 10)
        if (!Number.isFinite(n)) {
          setEvAddErr("requirement_id must be numeric when provided.")
          setEvAddBusy(false)
          return
        }
        body.requirement_id = n
      }
      await apiFetch(`/regulatory/dossiers/${dossierId}/evidence-links`, {
        method: "POST",
        body,
      })
      setEvTitle("")
      setEvSummary("")
      setEvResourceId("")
      setEvRequirementId("")
      setEvEvidenceType("other")
      setEvStatus("linked")
      await refreshEvidenceLinks()
      await refreshRequirements()
    } catch (e) {
      setEvAddErr(formatApiError(e, "Link evidence failed."))
    } finally {
      setEvAddBusy(false)
    }
  }

  async function patchRequirementStatus(requirementId: number) {
    const status = statusDraftByReqId[requirementId]
    if (!status) return
    setReqPatchBusyKey(`id-${requirementId}`)
    setReqPatchErr("")
    try {
      await apiFetch(`/regulatory/requirements/${requirementId}`, {
        method: "PATCH",
        body: { status },
      })
      await refreshRequirements()
    } catch (e) {
      setReqPatchErr(formatApiError(e, "Update requirement failed."))
    } finally {
      setReqPatchBusyKey(null)
    }
  }

  async function saveStatus() {
    if (!Number.isFinite(dossierId) || !dossier) return
    setPatchBusy(true)
    setPatchErr("")
    try {
      const updated = await apiFetch<Record<string, unknown>>(`/regulatory/dossiers/${dossierId}`, {
        method: "PATCH",
        body: { status: statusDraft },
      })
      setDossier(updated)
      setStatusDraft(readRecordString(updated, "status") ?? statusDraft)
    } catch (e) {
      setPatchErr(formatApiError(e, "PATCH failed."))
    } finally {
      setPatchBusy(false)
    }
  }

  async function askWithCitedSources() {
    if (!Number.isFinite(dossierId)) return
    const q = qaQuestion.trim()
    if (!q) {
      setQaErr("Question is required.")
      return
    }
    setQaBusy(true)
    setQaErr("")
    setQueryResult(null)
    try {
      const metadata_json: Record<string, unknown> = {}
      const scope = qaSourceScope.trim()
      if (scope) metadata_json.source_scope = scope

      const body: Record<string, unknown> = {
        question: q,
        metadata_json,
      }
      const jid = qaJurisdictionId.trim()
      if (jid) {
        const n = Number.parseInt(jid, 10)
        if (Number.isFinite(n)) body.jurisdiction_id = n
      }
      const created = await apiFetch<Record<string, unknown>>(`/regulatory/dossiers/${dossierId}/query`, {
        method: "POST",
        body,
      })
      const qid = readRecordNumber(created, "id")
      let resolved: Record<string, unknown> = created
      if (qid != null) {
        try {
          resolved = await apiFetch<Record<string, unknown>>(`/regulatory/queries/${qid}`, { method: "GET" })
        } catch {
          resolved = created
        }
      }
      setQueryResult(resolved)
      setQaQuestion("")
      if (dossier) {
        let risk_level: string | undefined
        const ans = resolved.answer
        if (isRecord(ans)) risk_level = readRecordString(ans, "confidence_label") ?? undefined
        trackRegulatoryQueryAnswered({
          dossier_id: dossierId,
          jurisdiction_id: readRecordNumber(dossier, "jurisdiction_id") ?? null,
          status: readRecordString(dossier, "status") ?? undefined,
          review_status: readRecordString(resolved, "status") ?? undefined,
          requirement_count: requirements.length,
          evidence_link_count: evidenceLinks.length,
          risk_level,
        })
      }
    } catch (e) {
      setQaErr(formatApiError(e, "Query failed."))
    } finally {
      setQaBusy(false)
    }
  }

  async function createRiskAssessment() {
    if (!Number.isFinite(dossierId)) return
    setRiskRefreshBusy(true)
    setRiskActionErr("")
    try {
      await apiFetch(`/regulatory/dossiers/${dossierId}/risk-assessment`, {
        method: "POST",
        body: {},
      })
      const risk = await apiFetch<Record<string, unknown>>(`/regulatory/dossiers/${dossierId}/risk-assessment`, {
        method: "GET",
      })
      setRiskAssessment(risk)
      setRiskMissing(false)
    } catch (e) {
      setRiskActionErr(formatApiError(e, "Could not create or load risk assessment."))
    } finally {
      setRiskRefreshBusy(false)
    }
  }

  async function generateReadinessReport() {
    if (!Number.isFinite(dossierId)) return
    setReadinessBusy(true)
    setReadinessErr("")
    try {
      const rep = await apiFetch<Record<string, unknown>>(`/regulatory/dossiers/${dossierId}/readiness-report`, {
        method: "POST",
        body: {},
      })
      const rid = readRecordNumber(rep, "id")
      let finalReport: Record<string, unknown> = rep
      if (rid != null) {
        try {
          const fresh = await apiFetch<Record<string, unknown>>(`/regulatory/readiness-reports/${rid}`, {
            method: "GET",
          })
          setReadinessReport(fresh)
          finalReport = fresh
        } catch {
          setReadinessReport(rep)
          finalReport = rep
        }
      } else {
        setReadinessReport(rep)
      }
      if (dossier) {
        const risks = finalReport.risks_json
        const risk_level = isRecord(risks) ? readRecordString(risks, "overall_risk") ?? undefined : undefined
        trackRegulatoryReadinessReportGenerated({
          dossier_id: dossierId,
          jurisdiction_id: readRecordNumber(dossier, "jurisdiction_id") ?? null,
          status: readRecordString(finalReport, "status") ?? undefined,
          requirement_count: dictListField(finalReport, "requirements_json").length,
          evidence_link_count: dictListField(finalReport, "evidence_json").length,
          risk_level,
        })
      }
    } catch (e) {
      setReadinessErr(formatApiError(e, "Readiness report request failed."))
    } finally {
      setReadinessBusy(false)
    }
  }

  async function saveRegulatoryReview() {
    if (!Number.isFinite(dossierId)) return
    const reviewer_name = reviewReviewerName.trim()
    const rationale = reviewRationale.trim()
    if (!reviewer_name) {
      setReviewSaveErr("reviewer_name is required.")
      return
    }
    if (!rationale) {
      setReviewSaveErr("rationale is required.")
      return
    }
    if (!REVIEW_DECISIONS.includes(reviewDecision as (typeof REVIEW_DECISIONS)[number])) {
      setReviewSaveErr("decision must be approve, needs_changes, reject, or defer.")
      return
    }
    setReviewSaveBusy(true)
    setReviewSaveErr("")
    try {
      const rec = await apiFetch<Record<string, unknown>>(`/regulatory/dossiers/${dossierId}/review`, {
        method: "POST",
        body: {
          reviewer_name,
          decision: reviewDecision,
          rationale,
        },
      })
      setReviewRationale("")
      await refreshReviews()
      const d = await refreshDossier()
      if (dossier) {
        trackRegulatoryReviewCompleted({
          dossier_id: dossierId,
          jurisdiction_id: readRecordNumber(dossier, "jurisdiction_id") ?? null,
          status: d ? readRecordString(d, "status") ?? undefined : readRecordString(dossier, "status") ?? undefined,
          review_status: readRecordString(rec, "decision") ?? undefined,
          requirement_count: requirements.length,
          evidence_link_count: evidenceLinks.length,
        })
      }
    } catch (e) {
      setReviewSaveErr(formatApiError(e, "Save regulatory review failed."))
    } finally {
      setReviewSaveBusy(false)
    }
  }

  async function refreshSubmissionPackageByDossier() {
    if (!Number.isFinite(dossierId)) return
    try {
      const rec = await apiFetch<Record<string, unknown>>(`/regulatory/dossiers/${dossierId}/submission-package`, {
        method: "GET",
      })
      setSubmissionPackageByDossier(rec)
    } catch {
      setSubmissionPackageByDossier(null)
    }
  }

  async function createSubmissionPackage() {
    if (!Number.isFinite(dossierId)) return
    setSubmissionPackageBusy(true)
    setSubmissionPackageErr("")
    try {
      const rec = await apiFetch<Record<string, unknown>>(`/regulatory/dossiers/${dossierId}/submission-package`, {
        method: "POST",
        body: {
          package_type: submissionPackageType,
          include_spectracheck_report: spIncludeSpectraCheckReport,
          include_impurity_register: spIncludeImpurityRegister,
          include_residual_solvent_assessment: spIncludeResidualSolventAssessment,
          include_nitrosamine_watch: spIncludeNitrosamineWatch,
          include_qnmr_method_validation: spIncludeQnmrValidation,
          include_ai_governance_record: spIncludeAiGovernanceRecord,
          include_source_citations: spIncludeSourceCitations,
          include_provenance_hashes: spIncludeProvenanceHashes,
          include_review_decisions: spIncludeReviewDecisions,
        },
      })
      setSubmissionPackageByDossier(rec)
      trackSubmissionPackageCreated({
        target_program: "regulatory_hub",
        status: readRecordString(rec, "status") ?? "created",
        file_kind: submissionPackageType,
        warning_count: readWarningLines(rec).length,
      })
      const packageId = readRecordNumber(rec, "id") ?? readRecordNumber(rec, "package_id")
      if (packageId != null) {
        setSubmissionPackageIdInput(String(packageId))
      }
    } catch (e) {
      setSubmissionPackageErr(formatApiError(e, "Create package failed."))
    } finally {
      setSubmissionPackageBusy(false)
    }
  }

  async function loadSubmissionPackageById() {
    const raw = submissionPackageIdInput.trim()
    if (!raw) {
      setSubmissionPackageErr("package_id is required.")
      return
    }
    setSubmissionPackageLookupBusy(true)
    setSubmissionPackageErr("")
    try {
      const rec = await apiFetch<Record<string, unknown>>(
        `/regulatory/submission-packages/${encodeURIComponent(raw)}`,
        { method: "GET" }
      )
      setSubmissionPackageById(rec)
    } catch (e) {
      setSubmissionPackageErr(formatApiError(e, "Load package failed."))
      setSubmissionPackageById(null)
    } finally {
      setSubmissionPackageLookupBusy(false)
    }
  }

  function readNumericListFromKeys(row: Record<string, unknown> | null, keys: string[]): number[] {
    if (!row) return []
    for (const key of keys) {
      const val = row[key]
      if (!Array.isArray(val)) continue
      const parsed = val.filter((x): x is number => typeof x === "number" && Number.isFinite(x))
      if (parsed.length > 0) return parsed
    }
    return []
  }

  function readWarningLines(row: Record<string, unknown> | null): string[] {
    if (!row) return []
    const merged = [...readStringArray(row, "warnings"), ...readStringArray(row, "warnings_json")]
    return merged
  }

  useEffect(() => {
    if (!Number.isFinite(dossierId)) return
    void refreshSubmissionPackageByDossier()
  }, [dossierId])

  const devPayload = useMemo(
    () => ({
      dossier,
      requirements,
      evidence_links: evidenceLinks,
      risk_assessment: riskAssessment,
      review_decisions: reviews,
      readiness_report: readinessReport,
      regulatory_query_result: queryResult,
      submission_package_by_dossier: submissionPackageByDossier,
      submission_package_by_id: submissionPackageById,
      // Previously omitted — these are all loaded into state by this workspace
      // but were absent from the Developer JSON, so the panel showed only a
      // partial view. Surface every loaded sub-resource for parity.
      impurity_register: impurityRegisterRows,
      residual_solvent_assessments: residualAssessments,
      nitrosamine_assessments: nitrosamineAssessments,
      nitrosamine_cumulative_risk: nitrosamineCumulativeRisk,
      rule_sets: ruleSets,
      qnmr_profiles: qnmrProfiles,
      method_validation_profiles: methodProfiles,
      ai_governance_records: aiGovernanceRecords,
      ai_decisions: aiDecisions,
      jurisdictional_maps: jurisdictionalMaps,
      change_impact: changeImpact,
    }),
    [
      dossier,
      requirements,
      evidenceLinks,
      riskAssessment,
      reviews,
      readinessReport,
      queryResult,
      submissionPackageByDossier,
      submissionPackageById,
      impurityRegisterRows,
      residualAssessments,
      nitrosamineAssessments,
      nitrosamineCumulativeRisk,
      ruleSets,
      qnmrProfiles,
      methodProfiles,
      aiGovernanceRecords,
      aiDecisions,
      jurisdictionalMaps,
      changeImpact,
    ]
  )

  // Dossier state surfaced as nav badges so reviewers see risk / readiness
  // without opening a section.
  const dossierRiskLevel = readRecordString(riskAssessment ?? {}, "overall_risk") ?? ""
  const dossierReadinessStatus = readRecordString(readinessReport ?? {}, "status") ?? ""

  const dossierJurisdictionLine = useMemo(() => {
    if (!dossier) return "—"
    const jid = readRecordNumber(dossier, "jurisdiction_id")
    if (jid == null) return "—"
    const name = jurisdictionNameById.get(jid)
    return name ? `${name} (jurisdiction_id ${jid})` : `jurisdiction_id ${jid}`
  }, [dossier, jurisdictionNameById])
  const dossierReactionProjectId = useMemo(
    () => (dossier ? (readRecordNumber(dossier, "reaction_project_id") ?? null) : null),
    [dossier],
  )
  const dossierCompoundId = useMemo(
    () => (dossier ? (readRecordNumber(dossier, "compound_id") ?? null) : null),
    [dossier],
  )
  const dossierBatchId = useMemo(() => (dossier ? (readRecordNumber(dossier, "batch_id") ?? null) : null), [dossier])

  if (!Number.isFinite(dossierId)) {
    return (
      <div className="mx-auto max-w-[1200px] space-y-6 pb-12">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/spectracheck?program=regulatory_hub">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Link>
        </Button>
        <AlertCard
          variant="error"
          title="Invalid dossier"
          description="Use a numeric dossier id in the URL."
        />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-[1200px] space-y-6 pb-12">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/spectracheck?program=regulatory_hub">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Regulatory Intelligence
          </Link>
        </Button>
      </div>

      <header className="space-y-1">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: "var(--mt-cyan)" }}
        >
          MolTrace · Regulatory Dossier
        </p>
        <h1 className="font-mono text-2xl font-bold tracking-tight">Regulatory Dossier</h1>
        {dossier ? (
          <p className="text-sm text-muted-foreground">
            {readRecordString(dossier, "title") ?? `dossier_id ${dossierId}`}
          </p>
        ) : null}
      </header>

      <AlertCard
        variant="warning"
        title="Important"
        description="Regulatory Intelligence provides cited decision support and requires qualified human review. It is not legal advice or final regulatory approval."
      />

      <AlertCard
        variant="info"
        title="Draft regulatory intelligence"
        description="Requires qualified human review. Not legal advice or final regulatory determination."
      />

      {loadErr ? (
        <AlertCard variant="error" title="Load error" description={loadErr} />
      ) : null}

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading dossier…
        </div>
      ) : dossier ? (
        <Tabs value={activeTab} onValueChange={setActiveTab} className="gap-4">
          {/* Section nav — one grouped tablist (matches SpectraCheck): every
              section is visible and one click away, organised into labelled
              groups with dividers. Arrow / Home / End roam across all sections;
              risk / readiness state surface as badges on their tabs. Drives the
              same activeTab the 18 TabsContent panels read. */}
          <div className="space-y-2">
            <div className="min-w-0 overflow-x-auto pb-1 [-webkit-overflow-scrolling:touch]">
              <div
                role="tablist"
                aria-label="Dossier sections"
                className="inline-flex w-max items-center gap-1 rounded-lg border bg-muted/20 p-1"
                onKeyDown={(e) => {
                  const all = DOSSIER_SECTIONS
                  const idx = all.indexOf(activeTab)
                  let next = -1
                  if (e.key === "ArrowRight" || e.key === "ArrowDown") next = (idx + 1) % all.length
                  else if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = (idx - 1 + all.length) % all.length
                  else if (e.key === "Home") next = 0
                  else if (e.key === "End") next = all.length - 1
                  else return
                  e.preventDefault()
                  setActiveTab(all[next])
                  e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus()
                }}
              >
                {DOSSIER_NAV.map((g, gi) => (
                  <div key={g.id} className="inline-flex items-center gap-1">
                    {gi > 0 ? <span aria-hidden className="mx-1 h-5 w-px shrink-0 bg-border" /> : null}
                    <span
                      aria-hidden
                      className="shrink-0 px-1 font-mono text-[9px] font-bold uppercase tracking-[0.12em]"
                      style={{ color: "var(--mt-cyan)" }}
                    >
                      {g.label}
                    </span>
                    {g.sections.map((s) => {
                      const on = activeTab === s
                      return (
                        <button
                          key={s}
                          type="button"
                          role="tab"
                          aria-selected={on}
                          tabIndex={on ? 0 : -1}
                          onClick={() => setActiveTab(s)}
                          className={cn(
                            "inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-md px-2.5 py-1 text-xs transition-colors",
                            on
                              ? "bg-[color:var(--mt-cyan)] font-semibold text-[#04080F] shadow-sm"
                              : "text-muted-foreground hover:bg-muted hover:text-foreground",
                          )}
                        >
                          {DOSSIER_SECTION_LABEL[s] ?? s}
                          {s === "risk" && dossierRiskLevel ? (
                            <span
                              className={cn(
                                "rounded-full border px-1 text-[9px] font-bold uppercase",
                                riskBadgeClass(dossierRiskLevel),
                              )}
                            >
                              {dossierRiskLevel}
                            </span>
                          ) : null}
                          {s === "readiness" && dossierReadinessStatus ? (
                            <span className="rounded-full border px-1 text-[9px] font-bold uppercase text-muted-foreground">
                              {dossierReadinessStatus.replace(/_/g, " ")}
                            </span>
                          ) : null}
                        </button>
                      )
                    })}
                  </div>
                ))}
              </div>
            </div>
          </div>

          <TabsContent value="overview" className="min-w-0 max-w-full space-y-6">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-cyan)" }}
              >
                Dossier · Overview
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Dossier metadata at a glance</h2>
              <p className="text-sm text-muted-foreground">
                Title, jurisdiction, intended use, status, last update, and review state — the source of truth for the rest of the workspace.
              </p>
            </div>
            {Number.isFinite(dossierId) ? <RegulatoryNotificationsCompactCard dossierId={dossierId} /> : null}
            <ModuleCard
              accent="cyan"
              eyebrow="Dossier · Overview"
              title="Overview"
              description="Dossier metadata — jurisdiction, intended use, status, and review state."
            >
                <dl className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">dossier title</dt>
                    <dd className="mt-1 text-sm font-medium">{readRecordString(dossier, "title") ?? "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">jurisdiction</dt>
                    <dd className="mt-1 text-sm">{jurisdictionLabel}</dd>
                  </div>
                  <div className="sm:col-span-2">
                    <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">intended use</dt>
                    <dd className="mt-1 text-sm text-muted-foreground">
                      {readRecordString(dossier, "intended_use") ?? "—"}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">status</dt>
                    <dd className="mt-1">
                      <Badge variant="outline" className="capitalize">
                        {(readRecordString(dossier, "status") ?? "—").replace(/_/g, " ")}
                      </Badge>
                    </dd>
                  </div>
                  <div>
                    <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">updated</dt>
                    <dd className="mt-1 text-xs text-muted-foreground">
                      {formatWhen(readRecordString(dossier, "updated_at"))}
                    </dd>
                  </div>
                </dl>

                <Separator />

                <div>
                  <h3 className="font-mono text-xs font-bold uppercase tracking-[0.14em] text-muted-foreground">Linked records</h3>
                  <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                    <li>
                      project_id:{" "}
                      {readRecordNumber(dossier, "project_id") != null ? (
                        <Link
                          className="font-mono text-foreground underline-offset-4 hover:underline"
                          href={`/projects/${encodeURIComponent(String(readRecordNumber(dossier, "project_id")))}`}
                        >
                          {readRecordNumber(dossier, "project_id")}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </li>
                    <li>
                      sample_id:{" "}
                      {readRecordNumber(dossier, "project_id") != null && readRecordNumber(dossier, "sample_id") != null ? (
                        <Link
                          className="font-mono text-foreground underline-offset-4 hover:underline"
                          href={`/projects/${encodeURIComponent(String(readRecordNumber(dossier, "project_id")))}/samples/${encodeURIComponent(String(readRecordNumber(dossier, "sample_id")))}`}
                        >
                          {readRecordNumber(dossier, "sample_id")}
                        </Link>
                      ) : (
                        <span className="font-mono">{readRecordNumber(dossier, "sample_id") ?? "—"}</span>
                      )}
                    </li>
                    <li>
                      spectracheck_session_id:{" "}
                      {readRecordNumber(dossier, "spectracheck_session_id") != null ? (
                        <Link
                          className="font-mono text-foreground underline-offset-4 hover:underline"
                          href="/spectracheck"
                        >
                          {readRecordNumber(dossier, "spectracheck_session_id")}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </li>
                    <li>
                      reaction_project_id:{" "}
                      {readRecordNumber(dossier, "reaction_project_id") != null ? (
                        <Link
                          className="font-mono text-foreground underline-offset-4 hover:underline"
                          href={`/reactions/${encodeURIComponent(String(readRecordNumber(dossier, "reaction_project_id")))}`}
                        >
                          {readRecordNumber(dossier, "reaction_project_id")}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </li>
                  </ul>
                </div>

                <Separator />

                <div className="grid gap-4 md:grid-cols-3">
                  <Card
                    className="overflow-hidden rounded-xl border-muted py-0"
                    style={{ borderTop: "3px solid var(--mt-cyan)" }}
                  >
                    <CardHeader className="pt-4 pb-2">
                      <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                        Requirements summary
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-1 pb-4 text-sm text-muted-foreground">
                      <p>
                        Total:{" "}
                        <span
                          className="font-mono text-base font-bold"
                          style={{ color: "var(--mt-cyan)" }}
                        >
                          {requirementsSummary.total}
                        </span>
                      </p>
                      <p>
                        Evidence needed:{" "}
                        <span
                          className="font-mono text-base font-bold"
                          style={{ color: "var(--mt-cyan)" }}
                        >
                          {requirementsSummary.need}
                        </span>
                      </p>
                    </CardContent>
                  </Card>
                  <Card
                    className="overflow-hidden rounded-xl border-muted py-0"
                    style={{ borderTop: "3px solid var(--mt-amber)" }}
                  >
                    <CardHeader className="pt-4 pb-2">
                      <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                        Evidence gaps
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-1 pb-4 text-sm text-muted-foreground">
                      <p>
                        Count:{" "}
                        <span
                          className="font-mono text-base font-bold"
                          style={{ color: "var(--mt-amber)" }}
                        >
                          {evidenceGapCount}
                        </span>
                      </p>
                      <p className="text-xs">
                        Uses missing_evidence_json from the latest risk assessment when present; otherwise requirements
                        in evidence_needed.
                      </p>
                    </CardContent>
                  </Card>
                  <Card
                    className="overflow-hidden rounded-xl border-muted py-0"
                    style={{ borderTop: "3px solid var(--mt-cyan)" }}
                  >
                    <CardHeader className="pt-4 pb-2">
                      <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                        Review state
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="pb-4 text-sm text-muted-foreground">
                      {reviewStateLabel}
                    </CardContent>
                  </Card>
                </div>

                <Separator />

                <div className="space-y-2">
                  <Label className="text-sm font-medium">Update dossier status</Label>
                  <div className="flex flex-wrap items-center gap-2">
                    <Select value={statusDraft} onValueChange={setStatusDraft}>
                      <SelectTrigger className="w-[220px]">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {DOSSIER_STATUSES.map((s) => (
                          <SelectItem key={s} value={s}>
                            {s.replace(/_/g, " ")}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button type="button" size="sm" disabled={patchBusy} onClick={() => void saveStatus()}>
                      {patchBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                      Save status
                    </Button>
                  </div>
                  {patchErr ? (
                    <AlertCard variant="error" title="Save failed" description={patchErr} />
                  ) : null}
                </div>
            </ModuleCard>
            <RegulatoryDossierLinkedCompoundCard
              dossierId={dossierId}
              evidenceLinks={evidenceLinks}
              onRegistryLinked={() => {
                setCompoundLinkVersion((v) => v + 1)
                void load()
              }}
            />
            {Number.isFinite(dossierId) ? <RegulatoryDossierKnowledgeLinksCard dossierId={dossierId} /> : null}
            {Number.isFinite(dossierId) ? (
              <BatchRegulatoryAssessmentPanel
                dossierId={dossierId}
                compoundLinkVersion={compoundLinkVersion}
                compact
              />
            ) : null}
            <ReactionOptimizationHandoffCard
              dossierId={dossierId}
              reactionProjectId={dossierReactionProjectId}
              compoundId={dossierCompoundId}
              batchId={dossierBatchId}
            />
          </TabsContent>

          <TabsContent value="requirements" className="min-w-0 max-w-full space-y-6">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-cyan)" }}
              >
                Dossier · Requirements
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Requirements & evidence sections</h2>
              <p className="text-sm text-muted-foreground">
                Per-section coverage status and shortcuts to evidence, compliance rules, impurity register, solvents, nitrosamine watch, qNMR validation, and AI governance.
              </p>
            </div>
            <ModuleCard
              accent="cyan"
              eyebrow="Dossier · Requirements"
              title={
                <span className="inline-flex items-center gap-2">
                  Requirements
                  <InfoTooltip label="Requirements checklist" content={REQUIREMENTS_CHECKLIST_TOOLTIP} />
                </span>
              }
              description="Regulatory requirements checklist for this dossier — track completion status, add new requirements, and update individual items as evidence is gathered."
            >
                <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
                  <h3 className="text-sm font-semibold">Add requirement</h3>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="req-add-title">title</Label>
                      <Input
                        id="req-add-title"
                        value={reqTitle}
                        onChange={(e) => setReqTitle(e.target.value)}
                        autoComplete="off"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>category</Label>
                      <Select value={reqCategory} onValueChange={setReqCategory}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {REQUIREMENT_CATEGORIES.map((c) => (
                            <SelectItem key={c} value={c}>
                              {c}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>priority</Label>
                      <Select value={reqPriority} onValueChange={setReqPriority}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {REQUIREMENT_PRIORITIES.map((p) => (
                            <SelectItem key={p} value={p}>
                              {p}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>status</Label>
                      <Select value={reqStatus} onValueChange={setReqStatus}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {REQUIREMENT_STATUSES.map((s) => (
                            <SelectItem key={s} value={s}>
                              {s.replace(/_/g, " ")}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="req-add-text">requirement text</Label>
                      <Textarea
                        id="req-add-text"
                        rows={5}
                        value={reqText}
                        onChange={(e) => setReqText(e.target.value)}
                        className="font-mono text-sm"
                      />
                    </div>
                  </div>
                  {reqAddErr ? (
                    <AlertCard variant="error" title="Add requirement failed" description={reqAddErr} />
                  ) : null}
                  <Button type="button" disabled={reqAddBusy} onClick={() => void addRequirement()}>
                    {reqAddBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    Add requirement
                  </Button>
                </div>

                <Separator />

                {reqPatchErr ? (
                  <AlertCard variant="error" title="Update status failed" description={reqPatchErr} />
                ) : null}

                {requirements.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No requirements.</p>
                ) : (
                  <div className="table-scroll">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>title</TableHead>
                          <TableHead>category</TableHead>
                          <TableHead>priority</TableHead>
                          <TableHead>status</TableHead>
                          <TableHead className="text-right">citations count</TableHead>
                          <TableHead className="text-right">evidence links count</TableHead>
                          <TableHead className="min-w-[220px]">update status action</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {requirements.map((r) => {
                          const id = readRecordNumber(r, "id")
                          const citCount = countIntListField(r, "citation_ids_json")
                          const evCount = countIntListField(r, "evidence_link_ids_json")
                          const busy = id != null && reqPatchBusyKey === `id-${id}`
                          const draft = id != null ? statusDraftByReqId[id] : undefined
                          const status = readRecordString(r, "status")
                          const stripe = requirementStatusColor(status)
                          return (
                            <TableRow
                              key={id ?? readRecordString(r, "title")}
                              style={stripe ? { boxShadow: `inset 3px 0 0 0 ${stripe}` } : undefined}
                            >
                              <TableCell className="max-w-[220px] font-medium">
                                {readRecordString(r, "title") ?? "—"}
                              </TableCell>
                              <TableCell className="text-xs">{readRecordString(r, "category") ?? "—"}</TableCell>
                              <TableCell className="text-xs">{readRecordString(r, "priority") ?? "—"}</TableCell>
                              <TableCell>
                                <Badge
                                  variant="outline"
                                  className="text-xs capitalize"
                                  style={stripe ? { borderColor: stripe, color: stripe } : undefined}
                                >
                                  {(status ?? "—").replace(/_/g, " ")}
                                </Badge>
                              </TableCell>
                              <TableCell className="text-right font-mono text-xs tabular-nums">{citCount}</TableCell>
                              <TableCell className="text-right font-mono text-xs tabular-nums">{evCount}</TableCell>
                              <TableCell>
                                {id != null ? (
                                  <div className="flex flex-wrap items-center gap-2">
                                    <Select
                                      value={
                                        (draft ?? readRecordString(r, "status") ?? "not_started") as string
                                      }
                                      onValueChange={(v) =>
                                        setStatusDraftByReqId((prev) => ({ ...prev, [id]: v }))
                                      }
                                    >
                                      <SelectTrigger className="h-8 w-[160px]">
                                        <SelectValue />
                                      </SelectTrigger>
                                      <SelectContent>
                                        {REQUIREMENT_STATUSES.map((s) => (
                                          <SelectItem key={s} value={s}>
                                            {s.replace(/_/g, " ")}
                                          </SelectItem>
                                        ))}
                                      </SelectContent>
                                    </Select>
                                    <Button
                                      type="button"
                                      variant="outline"
                                      size="sm"
                                      disabled={
                                        busy ||
                                        (draft ?? readRecordString(r, "status")) ===
                                          readRecordString(r, "status")
                                      }
                                      onClick={() => void patchRequirementStatus(id)}
                                    >
                                      {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                                      Update status
                                    </Button>
                                  </div>
                                ) : (
                                  "—"
                                )}
                              </TableCell>
                            </TableRow>
                          )
                        })}
                      </TableBody>
                    </Table>
                  </div>
                )}
            </ModuleCard>
          </TabsContent>

          <TabsContent value="evidence" className="min-w-0 max-w-full space-y-6">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-cyan)" }}
              >
                Dossier · Evidence Links
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Linked evidence & artifacts</h2>
              <p className="text-sm text-muted-foreground">
                SpectraCheck evidence items, dossier artifacts, and external citations attached to this dossier.
              </p>
            </div>
            <ModuleCard
              accent="cyan"
              eyebrow="Dossier · Evidence Links"
              title="Evidence Links"
              description="Link analytical or reaction artefacts to dossier requirements by ID and summary — open SpectraCheck or Reaction Studio for full evidence detail without copying raw payloads here."
            >
              <div className="space-y-6">
                <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
                  <h3 className="text-sm font-semibold">Link evidence</h3>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2 md:col-span-2">
                      <Label>requirement selector optional</Label>
                      <Select value={evRequirementId || "none"} onValueChange={(v) => setEvRequirementId(v === "none" ? "" : v)}>
                        <SelectTrigger>
                          <SelectValue placeholder="No requirement linked" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">No requirement</SelectItem>
                          {requirements.flatMap((r) => {
                            const id = readRecordNumber(r, "id")
                            if (id == null) return []
                            return [
                              <SelectItem key={id} value={String(id)}>
                                {readRecordString(r, "title") ?? `requirement_id ${id}`}
                              </SelectItem>,
                            ]
                          })}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>evidence type</Label>
                      <Select value={evEvidenceType} onValueChange={setEvEvidenceType}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {EVIDENCE_TYPES.map((t) => (
                            <SelectItem key={t} value={t}>
                              {t}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="ev-resource-id">resource ID optional</Label>
                      <Input
                        id="ev-resource-id"
                        value={evResourceId}
                        onChange={(e) => setEvResourceId(e.target.value)}
                        inputMode="numeric"
                        autoComplete="off"
                        placeholder="resource_id"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="ev-title">title</Label>
                      <Input id="ev-title" value={evTitle} onChange={(e) => setEvTitle(e.target.value)} autoComplete="off" />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="ev-summary">summary</Label>
                      <Textarea
                        id="ev-summary"
                        rows={4}
                        value={evSummary}
                        onChange={(e) => setEvSummary(e.target.value)}
                        className="text-sm"
                        placeholder="Short pointer to the backing artefact (no raw spectra or reaction dumps)."
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>status</Label>
                      <Select value={evStatus} onValueChange={setEvStatus}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {EVIDENCE_STATUSES.map((s) => (
                            <SelectItem key={s} value={s}>
                              {s.replace(/_/g, " ")}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  {evAddErr ? (
                    <Alert variant="destructive">
                      <AlertDescription className="text-sm">{evAddErr}</AlertDescription>
                    </Alert>
                  ) : null}
                  <Button type="button" disabled={evAddBusy} onClick={() => void linkEvidence()}>
                    {evAddBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    Link evidence
                  </Button>
                </div>

                <Separator />

                {evidenceLinks.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No evidence links.</p>
                ) : (
                  <div className="table-scroll">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>evidence type</TableHead>
                          <TableHead>title</TableHead>
                          <TableHead>linked requirement</TableHead>
                          <TableHead>status</TableHead>
                          <TableHead>resource ID</TableHead>
                          <TableHead>review status</TableHead>
                          <TableHead className="w-[120px]">open source</TableHead>
                          <TableHead>summary (truncated)</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {evidenceLinks.map((r) => {
                          const id = readRecordNumber(r, "id")
                          const reqId = readRecordNumber(r, "requirement_id")
                          const reqTitleCell =
                            reqId != null ? requirementTitleById.get(reqId) ?? `requirement_id ${reqId}` : "—"
                          const resId = readRecordNumber(r, "resource_id")
                          const et = readRecordString(r, "evidence_type")
                          const href = openEvidenceSourceHref(et ?? undefined, resId ?? undefined)
                          return (
                            <TableRow key={id ?? readRecordString(r, "title")}>
                              <TableCell className="text-xs">{et ?? "—"}</TableCell>
                              <TableCell className="max-w-[200px] font-medium">
                                {readRecordString(r, "title") ?? "—"}
                              </TableCell>
                              <TableCell className="max-w-[200px] text-xs text-muted-foreground">{reqTitleCell}</TableCell>
                              <TableCell>
                                <Badge variant="outline" className="text-xs capitalize">
                                  {(readRecordString(r, "status") ?? "—").replace(/_/g, " ")}
                                </Badge>
                              </TableCell>
                              <TableCell className="font-mono text-xs">{resId ?? "—"}</TableCell>
                              <TableCell className="text-xs text-muted-foreground">{reviewStatusDisplay(r)}</TableCell>
                              <TableCell>
                                {href ? (
                                  <Button variant="outline" size="sm" asChild>
                                    <Link href={href}>Open source</Link>
                                  </Button>
                                ) : (
                                  <span className="text-xs text-muted-foreground">—</span>
                                )}
                              </TableCell>
                              <TableCell className="max-w-[240px] text-xs text-muted-foreground">
                                {truncateText(readRecordString(r, "summary") ?? "", 160)}
                              </TableCell>
                            </TableRow>
                          )
                        })}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </div>
            </ModuleCard>
          </TabsContent>

          <TabsContent value="compliance-rules" className="min-w-0 max-w-full space-y-6">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-cyan)" }}
              >
                Dossier · Compliance Rules
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Active rule sets & coverage</h2>
              <p className="text-sm text-muted-foreground">
                Tenant rule sets evaluated against this dossier — open the rule-updates workspace to propose changes.
              </p>
            </div>
            <ModuleCard
              accent="cyan"
              eyebrow="Dossier · Compliance Rules"
              title="Compliance Rules"
              description={
                <>
                  Counts of requirement rows on this dossier by <span className="font-mono">category</span> (GET
                  /regulatory/dossiers/{"{dossier_id}"}/requirements). For editing rows, use the Requirements tab.
                </>
              }
            >
              <div className="table-scroll">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>category</TableHead>
                        <TableHead className="text-right">count</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {REQUIREMENT_CATEGORIES.map((c) => (
                        <TableRow key={c}>
                          <TableCell className="font-mono text-xs">{c}</TableCell>
                          <TableCell className="text-right font-mono text-xs tabular-nums">
                            {complianceCategoryCounts.get(c) ?? 0}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
            </ModuleCard>

            {/* Active rule sets — the actual tenant rule sets the section
                header promises ("Active rule sets … evaluated against this
                dossier"). Previously only the requirement-category counts
                rendered, so the header oversold the content; this table renders
                the loaded `ruleSets` (GET /regulatory/rule-sets?status=active). */}
            <ModuleCard
              accent="cyan"
              eyebrow="Dossier · Compliance Rules"
              title="Active rule sets"
              description={
                <>
                  Tenant rule sets currently <span className="font-mono">active</span> (GET
                  /regulatory/rule-sets?status=active). Manage them in the rule-updates workspace.
                </>
              }
            >
              {ruleSets.length === 0 ? (
                <p className="text-sm text-muted-foreground">No active rule sets loaded for this tenant.</p>
              ) : (
                <div className="table-scroll">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>name</TableHead>
                        <TableHead>version</TableHead>
                        <TableHead>source</TableHead>
                        <TableHead>jurisdiction</TableHead>
                        <TableHead>status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {ruleSets.map((r, i) => {
                        const jid = readRecordNumber(r, "jurisdiction_id")
                        const status = readRecordString(r, "status") ?? "—"
                        return (
                          <TableRow key={readRecordNumber(r, "id") ?? i}>
                            <TableCell className="font-medium">{readRecordString(r, "name") ?? "—"}</TableCell>
                            <TableCell className="font-mono text-xs">{readRecordString(r, "version") ?? "—"}</TableCell>
                            <TableCell className="font-mono text-xs uppercase">{readRecordString(r, "source_type") ?? "—"}</TableCell>
                            <TableCell className="font-mono text-xs">{jid != null ? jid : "—"}</TableCell>
                            <TableCell>
                              <Badge
                                variant="outline"
                                className={`font-normal ${
                                  status === "active" ? "border-success/50 text-success" : "text-muted-foreground"
                                }`}
                              >
                                {status}
                              </Badge>
                            </TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                </div>
              )}
            </ModuleCard>
          </TabsContent>

          <TabsContent value="impurity-register" className="min-w-0 max-w-full space-y-6">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-cyan)" }}
              >
                Dossier · Impurity Register
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Specified & unspecified impurities</h2>
              <p className="text-sm text-muted-foreground">
                ICH Q3A/Q3B-aligned register with thresholds, identification status, and qualified justifications.
              </p>
            </div>
            <ModuleCard
              accent="cyan"
              eyebrow="Dossier · Impurity Register"
              title={
                <span className="inline-flex items-center gap-2">
                  Impurity Risk Register
                  <InfoTooltip label="Impurity risk register" content={IMPURITY_REGISTER_TOOLTIP} />
                </span>
              }
              description="Identified impurity entries with assessed risk levels — add new impurities, run a batch regulatory assessment, and track review status against applicable limits."
              badge={
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={impAssessBusy}
                  onClick={() => void runRegisterAssessment()}
                >
                  {impAssessBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Run register assessment
                </Button>
              }
            >
              <div className="space-y-6">
                <AlertCard
                  variant="info"
                  title="Workspace labels"
                  description={
                    <>
                      Impurity name and structural_assignment are workspace labels; they do not assert confirmed identity
                      unless supported by linked evidence (<span className="font-mono">evidence_link_id</span>) and qualified
                      review.
                    </>
                  }
                />
                {impAssessErr ? (
                  <AlertCard variant="error" title="Assessment failed" description={impAssessErr} />
                ) : null}

                <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
                  <h3 className="text-sm font-semibold">Add impurity</h3>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="reg-imp-name">impurity_name</Label>
                      <Input
                        id="reg-imp-name"
                        value={impName}
                        onChange={(e) => setImpName(e.target.value)}
                        autoComplete="off"
                        placeholder="Optional"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>impurity_type</Label>
                      <Select value={impType} onValueChange={setImpType}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {IMPURITY_TYPES.map((t) => (
                            <SelectItem key={t} value={t}>
                              {t}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>source</Label>
                      <Select value={impSource} onValueChange={setImpSource}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {IMPURITY_SOURCES.map((s) => (
                            <SelectItem key={s} value={s}>
                              {s}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="reg-imp-pct">observed_level_percent</Label>
                      <Input
                        id="reg-imp-pct"
                        value={impLevelPct}
                        onChange={(e) => setImpLevelPct(e.target.value)}
                        inputMode="decimal"
                        autoComplete="off"
                        placeholder="Optional"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="reg-imp-amt">observed_amount</Label>
                      <Input
                        id="reg-imp-amt"
                        value={impAmount}
                        onChange={(e) => setImpAmount(e.target.value)}
                        inputMode="decimal"
                        autoComplete="off"
                        placeholder="Optional"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="reg-imp-struct">structural_assignment</Label>
                      <Textarea
                        id="reg-imp-struct"
                        rows={3}
                        value={impStructural}
                        onChange={(e) => setImpStructural(e.target.value)}
                        className="text-sm"
                        placeholder="Optional"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="reg-imp-compound">compound_id</Label>
                      <Input
                        id="reg-imp-compound"
                        value={impCompoundId}
                        onChange={(e) => setImpCompoundId(e.target.value)}
                        inputMode="numeric"
                        autoComplete="off"
                        placeholder="Optional"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="reg-imp-evidence">evidence_link_id</Label>
                      <Input
                        id="reg-imp-evidence"
                        value={impEvidenceLink}
                        onChange={(e) => setImpEvidenceLink(e.target.value)}
                        inputMode="numeric"
                        autoComplete="off"
                        placeholder="Optional — compound evidence link id when applicable"
                      />
                      <p className="text-xs text-muted-foreground">
                        Uses <span className="font-mono">compound_evidence_links.id</span>; dossier Evidence Links use a
                        separate regulatory table and ids may differ.
                      </p>
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="reg-imp-notes">notes</Label>
                      <Textarea
                        id="reg-imp-notes"
                        rows={3}
                        value={impNotes}
                        onChange={(e) => setImpNotes(e.target.value)}
                        className="text-sm"
                        placeholder="Sent as notes_json (one string when a single block is entered)."
                      />
                    </div>
                  </div>
                  {impAddErr ? (
                    <Alert variant="destructive" className="mt-2">
                      <AlertDescription className="text-sm">{impAddErr}</AlertDescription>
                    </Alert>
                  ) : null}
                  <Button type="button" disabled={impAddBusy} onClick={() => void addImpurityRegisterEntry()}>
                    {impAddBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    Add impurity
                  </Button>
                </div>

                <Separator />

                {impurityRegisterRows.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No impurity risk register rows.</p>
                ) : (
                  <div className="table-scroll">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>impurity</TableHead>
                          <TableHead>source</TableHead>
                          <TableHead>observed level</TableHead>
                          <TableHead>threshold triggered</TableHead>
                          <TableHead>structural assignment</TableHead>
                          <TableHead>linked evidence</TableHead>
                          <TableHead>status</TableHead>
                          <TableHead>warnings</TableHead>
                          <TableHead>action item</TableHead>
                          <TableHead>review status</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {impurityRegisterRows.map((row) => {
                          const id = readRecordNumber(row, "id")
                          const evId = readRecordNumber(row, "evidence_link_id")
                          const actionId = readRecordNumber(row, "action_item_id")
                          const tt = readRecordString(row, "threshold_triggered") ?? "none"
                          const st = readRecordString(row, "status") ?? "—"
                          const warnList = impurityWarningsForRow(row)
                          const hr =
                            typeof row.human_review_required === "boolean" ? row.human_review_required : undefined
                          return (
                            <TableRow key={id ?? readRecordString(row, "impurity_name")}>
                              <TableCell className="max-w-[180px]">
                                <div className="font-medium">{readRecordString(row, "impurity_name") ?? "—"}</div>
                                <div className="text-xs text-muted-foreground">
                                  {readRecordString(row, "impurity_type") ?? "—"}
                                </div>
                              </TableCell>
                              <TableCell className="text-xs">{readRecordString(row, "source") ?? "—"}</TableCell>
                              <TableCell className="text-xs">{impurityObservedLevelDisplay(row)}</TableCell>
                              <TableCell>
                                <Badge variant="outline" className="text-xs capitalize">
                                  {tt.replace(/_/g, " ")}
                                </Badge>
                              </TableCell>
                              <TableCell className="max-w-[160px] text-xs text-muted-foreground" title={readRecordString(row, "structural_assignment") ?? undefined}>
                                {truncateText(readRecordString(row, "structural_assignment") ?? "", 96)}
                              </TableCell>
                              <TableCell className="font-mono text-xs">{evId ?? "—"}</TableCell>
                              <TableCell>
                                <Badge variant="secondary" className="text-xs capitalize">
                                  {st.replace(/_/g, " ")}
                                </Badge>
                              </TableCell>
                              <TableCell className="max-w-[200px] text-xs text-muted-foreground">
                                {warnList.length ? (
                                  <ul className="list-inside list-disc space-y-0.5">
                                    {warnList.map((w, i) => (
                                      <li key={`${id}-w-${i}`}>{w}</li>
                                    ))}
                                  </ul>
                                ) : (
                                  "—"
                                )}
                              </TableCell>
                              <TableCell className="font-mono text-xs">{actionId ?? "—"}</TableCell>
                              <TableCell>
                                {hr === true ? (
                                  <Badge variant="outline" className="text-xs">
                                    human review required
                                  </Badge>
                                ) : (
                                  <span className="text-xs text-muted-foreground">—</span>
                                )}
                              </TableCell>
                            </TableRow>
                          )
                        })}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </div>
            </ModuleCard>
            <ReactionOptimizationHandoffCard
              dossierId={dossierId}
              reactionProjectId={dossierReactionProjectId}
              compoundId={dossierCompoundId}
              batchId={dossierBatchId}
            />
          </TabsContent>

          <TabsContent value="residual-solvents" className="min-w-0 max-w-full space-y-6">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-cyan)" }}
              >
                Dossier · Residual Solvents
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">ICH Q3C residual-solvent watch</h2>
              <p className="text-sm text-muted-foreground">
                Class 1 / 2 / 3 solvent levels and PDE compliance against the active rule set.
              </p>
            </div>
            <ModuleCard
              accent="cyan"
              eyebrow="Dossier · Residual Solvents"
              title={
                <span className="inline-flex items-center gap-2">
                  Residual Solvent Watch
                  <InfoTooltip label="Residual solvent watch" content={RESIDUAL_SOLVENT_WATCH_TOOLTIP} />
                </span>
              }
              description="ICH Q3C residual solvent assessment — detected solvents are matched against active regulatory rule sets for this dossier's jurisdiction. Rule set and source evidence are recorded with each run."
            >
              <div className="space-y-6">
                {residualSolventMissingRuleHint ? (
                  <AlertCard variant="info" title="Rule set not configured" description={RESIDUAL_RULE_NOT_CONFIGURED_MSG} />
                ) : null}

                <div className="rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                  Active rule sets for this dossier jurisdiction:{" "}
                  {activeRuleSetsForDossier.length ? (
                    <span className="font-mono text-foreground">
                      {activeRuleSetsForDossier.map((r) => readRecordNumber(r, "id")).filter((x) => x != null).join(", ")}
                    </span>
                  ) : (
                    "—"
                  )}
                  . Manage sources via{" "}
                  <Link href="/regulatory/sources" className="underline-offset-4 hover:underline">
                    Regulatory Sources
                  </Link>
                  .
                </div>

                <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
                  <h3 className="text-sm font-semibold">Detected solvent list</h3>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="reg-rs-solvents">solvents_json</Label>
                      <Textarea
                        id="reg-rs-solvents"
                        rows={6}
                        value={rsSolventLines}
                        onChange={(e) => setRsSolventLines(e.target.value)}
                        className="font-mono text-sm"
                        placeholder={"One solvent per line. Optional observed ppm after the last comma, e.g. MeOH, 1200"}
                      />
                      <p className="text-xs text-muted-foreground">
                        Parsed into POST body <span className="font-mono">solvents_json</span> with{" "}
                        <span className="font-mono">solvent_name</span> and optional{" "}
                        <span className="font-mono">observed_ppm</span>.
                      </p>
                    </div>
                    <div className="space-y-2">
                      <Label>source evidence (metadata_json.source_evidence)</Label>
                      <Select value={rsSourceEvidence} onValueChange={setRsSourceEvidence}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {RESIDUAL_SOURCE_EVIDENCE_OPTIONS.map((o) => (
                            <SelectItem key={o.value} value={o.value}>
                              {o.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>jurisdiction / rule set (metadata_json.selected_rule_set_id)</Label>
                      <Select value={rsRuleSetId} onValueChange={setRsRuleSetId}>
                        <SelectTrigger>
                          <SelectValue placeholder="Optional traceability" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">none</SelectItem>
                          {ruleSets.map((r) => {
                            const id = readRecordNumber(r, "id")
                            if (id == null) return null
                            return (
                              <SelectItem key={id} value={String(id)}>
                                {readRecordString(r, "name") ?? `rule_set id ${id}`} (id {id})
                              </SelectItem>
                            )
                          })}
                        </SelectContent>
                      </Select>
                      <p className="text-xs text-muted-foreground">
                        Selection is stored in assessment metadata; threshold matching still follows server active rule sets
                        for the dossier.
                      </p>
                    </div>
                  </div>
                  {rsAssessErr ? (
                    <Alert variant="destructive">
                      <AlertDescription className="text-sm">{rsAssessErr}</AlertDescription>
                    </Alert>
                  ) : null}
                  <Button type="button" disabled={rsAssessBusy} onClick={() => void runAssessResidualSolvents()}>
                    {rsAssessBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    Assess residual solvents
                  </Button>
                </div>

                <Separator />

                {(() => {
                  const assess = latestResidualSolventAssessment
                  if (!assess) {
                    return <p className="text-sm text-muted-foreground">No residual solvent assessment rows yet.</p>
                  }
                  const summary = assess.residual_solvent_summary_json
                  const sumRec = summary && typeof summary === "object" ? (summary as Record<string, unknown>) : null
                  const rawMatches = sumRec?.matched_solvents
                  const matches = Array.isArray(rawMatches)
                    ? (rawMatches.filter(isRecord) as Record<string, unknown>[])
                    : []
                  const actionIds = readIntListField(assess, "action_item_ids_json")
                  const paired = pairResidualSolventRowActions(matches, actionIds)
                  const assessWarnings = regulatoryAssessmentWarnings(assess)
                  const assessNotes = Array.isArray(assess.notes)
                    ? assess.notes.filter((x): x is string => typeof x === "string")
                    : readStringArray(assess, "notes_json")
                  return (
                    <div className="space-y-4">
                      <div className="text-xs text-muted-foreground">
                        Latest assessment id{" "}
                        <span className="font-mono text-foreground">{readRecordNumber(assess, "id") ?? "—"}</span> ·
                        created_at{" "}
                        <span className="font-mono text-foreground">
                          {formatWhen(readRecordString(assess, "created_at"))}
                        </span>{" "}
                        · overall_status{" "}
                        <Badge variant="outline" className="text-xs capitalize">
                          {(readRecordString(assess, "overall_status") ?? "—").replace(/_/g, " ")}
                        </Badge>
                      </div>
                      {assessWarnings.length ? (
                        <div>
                          <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">warnings</p>
                          <ul className="list-inside list-disc space-y-1 text-xs text-muted-foreground">
                            {assessWarnings.map((w, i) => (
                              <li key={`rw-${i}`}>{w}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                      {assessNotes.length ? (
                        <div>
                          <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">notes</p>
                          <ul className="list-inside list-disc space-y-1 text-xs text-muted-foreground">
                            {assessNotes.map((n, i) => (
                              <li key={`rn-${i}`}>{n}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                      {matches.length === 0 ? (
                        <p className="text-sm text-muted-foreground">No matched_solvents in this assessment.</p>
                      ) : (
                        <div className="table-scroll">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>solvent</TableHead>
                                <TableHead>solvent_class</TableHead>
                                <TableHead>PDE / limit</TableHead>
                                <TableHead>observed level</TableHead>
                                <TableHead>action required</TableHead>
                                <TableHead>citation / source</TableHead>
                                <TableHead>warnings</TableHead>
                                <TableHead>action item</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {matches.map((m, idx) => {
                                const name =
                                  readRecordString(m, "input_solvent_name") ??
                                  readRecordString(m, "normalized_solvent_name") ??
                                  "—"
                                const norm = readRecordString(m, "normalized_solvent_name")
                                const obs = m.observed_concentration
                                const obsLabel =
                                  typeof obs === "number" && Number.isFinite(obs) ? String(obs) : "—"
                                const need =
                                  m.threshold_triggered === true ||
                                  m.review_required === true
                                const rowWarn = assessWarnings.filter(
                                  (w) =>
                                    name !== "—" && (w.includes(name) || (norm ? w.includes(norm) : false))
                                )
                                const pde = m.permitted_daily_exposure
                                const lim = m.concentration_limit
                                const pdeLim =
                                  (typeof pde === "number" && Number.isFinite(pde)) ||
                                  (typeof lim === "number" && Number.isFinite(lim)) ? (
                                    <span className="font-mono text-[11px]">
                                      {typeof pde === "number" && Number.isFinite(pde) ? (
                                        <span className="block">permitted_daily_exposure: {pde}</span>
                                      ) : null}
                                      {typeof lim === "number" && Number.isFinite(lim) ? (
                                        <span className="block">concentration_limit: {lim}</span>
                                      ) : null}
                                    </span>
                                  ) : (
                                    "—"
                                  )
                                const ruleFound = m.rule_found === true
                                const aid = paired[idx]
                                return (
                                  <TableRow key={`${readRecordNumber(assess, "id")}-rs-${idx}`}>
                                    <TableCell className="max-w-[160px]">
                                      <div className="font-medium">{name}</div>
                                      {norm ? (
                                        <div className="text-xs text-muted-foreground">{norm}</div>
                                      ) : null}
                                    </TableCell>
                                    <TableCell className="text-xs">
                                      {residualSolventClassLabel(readRecordString(m, "solvent_class"))}
                                    </TableCell>
                                    <TableCell className="max-w-[140px]">{pdeLim}</TableCell>
                                    <TableCell className="font-mono text-xs">{obsLabel}</TableCell>
                                    <TableCell>
                                      {need ? (
                                        <Badge variant="outline" className="text-xs">
                                          required
                                        </Badge>
                                      ) : (
                                        <span className="text-xs text-muted-foreground">—</span>
                                      )}
                                    </TableCell>
                                    <TableCell className="max-w-[140px] text-xs">
                                      {ruleFound ? (
                                        <Badge variant="secondary" className="text-xs">
                                          rule
                                        </Badge>
                                      ) : (
                                        <Badge variant="outline" className="text-xs">
                                          source_needed
                                        </Badge>
                                      )}
                                    </TableCell>
                                    <TableCell className="max-w-[200px] text-xs text-muted-foreground">
                                      {rowWarn.length ? (
                                        <ul className="list-inside list-disc space-y-0.5">
                                          {rowWarn.map((w, wi) => (
                                            <li key={`${idx}-ww-${wi}`}>{w}</li>
                                          ))}
                                        </ul>
                                      ) : (
                                        "—"
                                      )}
                                    </TableCell>
                                    <TableCell className="font-mono text-xs">{aid ?? "—"}</TableCell>
                                  </TableRow>
                                )
                              })}
                            </TableBody>
                          </Table>
                        </div>
                      )}
                      {actionIds.length ? (
                        <p className="text-xs text-muted-foreground">
                          action_item_ids_json:{" "}
                          <span className="font-mono text-foreground">{actionIds.join(", ")}</span>
                        </p>
                      ) : null}
                    </div>
                  )
                })()}
              </div>
            </ModuleCard>
          </TabsContent>

          <TabsContent value="nitrosamine-watch" className="min-w-0 max-w-full space-y-6">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-cyan)" }}
              >
                Dossier · Nitrosamine Watch
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Nitrosamine risk assessment</h2>
              <p className="text-sm text-muted-foreground">
                FDA / EMA nitrosamine risk-narrative coverage with cited evidence and reviewer signoff state.
              </p>
            </div>
            <ModuleCard
              accent="cyan"
              eyebrow="Dossier · Nitrosamine Watch"
              title={
                <span className="inline-flex items-center gap-2">
                  Nitrosamine Watch
                  <InfoTooltip label="Nitrosamine watch" content={NITROSAMINE_WATCH_TOOLTIP} />
                </span>
              }
              description={
                <>
                  Nitrosamine risk review — monitors for structural and process signals that may indicate nitrosamine impurity risk. Treat all outputs as{" "}
                  <span className="font-medium text-foreground">review required</span> unless a qualified reviewer explicitly confirms or dismisses each signal.
                </>
              }
            >
              <div className="space-y-6">
                <AlertCard
                  variant="info"
                  title="Triage signals only"
                  description={
                    <>
                      Signals here are nitrosamine-related review triggers only. They indicate possible nitrosamine risk for
                      triage, not a confirmed structural finding. Do not treat results as confirmed nitrosamine unless the
                      backend response explicitly marks confirmation (see <span className="font-mono">nitrosamine_confirmed</span>
                      ).
                    </>
                  }
                />

                <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
                  <h3 className="text-sm font-semibold">Run nitrosamine watch</h3>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label>compound_id</Label>
                      {nitrosamineCompoundChoices.length > 0 ? (
                        <Select value={naCompoundId} onValueChange={setNaCompoundId}>
                          <SelectTrigger>
                            <SelectValue placeholder="Optional" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="none">none</SelectItem>
                            {nitrosamineCompoundChoices.map((id) => (
                              <SelectItem key={id} value={String(id)}>
                                {id}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <Input
                          id="reg-na-compound"
                          inputMode="numeric"
                          autoComplete="off"
                          placeholder="Optional — type compound_id if known"
                          value={naCompoundId === "none" ? "" : naCompoundId}
                          onChange={(e) => {
                            const v = e.target.value.trim()
                            setNaCompoundId(v ? v : "none")
                          }}
                        />
                      )}
                    </div>
                    <div className="space-y-2">
                      <Label>batch_id</Label>
                      <Input
                        id="reg-na-batch"
                        inputMode="numeric"
                        autoComplete="off"
                        placeholder="Optional"
                        value={naBatchId}
                        onChange={(e) => setNaBatchId(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="reg-na-measured">measured_ng_per_day</Label>
                      <Input
                        id="reg-na-measured"
                        inputMode="decimal"
                        autoComplete="off"
                        placeholder="Optional — ng/day, feeds cumulative risk"
                        value={naMeasuredNgPerDay}
                        onChange={(e) => setNaMeasuredNgPerDay(e.target.value)}
                      />
                      <p className="text-xs text-muted-foreground">
                        A watch counts toward the cumulative-risk rollup only with both a parseable nitrosamine{" "}
                        <span className="font-mono">structure_text</span> and this measured value.
                      </p>
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="reg-na-structure">structure_text</Label>
                      <Textarea
                        id="reg-na-structure"
                        rows={4}
                        value={naStructureText}
                        onChange={(e) => setNaStructureText(e.target.value)}
                        className="font-mono text-sm"
                        placeholder="Optional structure or motif text for pattern screening"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label>impurity risk register (risk_signals_json)</Label>
                      <Select value={naImpurityId} onValueChange={setNaImpurityId}>
                        <SelectTrigger>
                          <SelectValue placeholder="Optional" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">none</SelectItem>
                          {impurityRegisterRows.flatMap((r) => {
                            const id = readRecordNumber(r, "id")
                            if (id == null) return []
                            return [
                              <SelectItem key={id} value={String(id)}>
                                {readRecordString(r, "impurity_name") ?? `impurity_risk_register id ${id}`}
                              </SelectItem>,
                            ]
                          })}
                        </SelectContent>
                      </Select>
                      <p className="text-xs text-muted-foreground">
                        Adds a dict to <span className="font-mono">risk_signals_json</span> with{" "}
                        <span className="font-mono">impurity_risk_register_id</span> and text fields for screening.
                      </p>
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label>regulatory evidence link</Label>
                      <Select value={naEvidenceLinkId} onValueChange={setNaEvidenceLinkId}>
                        <SelectTrigger>
                          <SelectValue placeholder="Optional" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">none</SelectItem>
                          {evidenceLinks.flatMap((r) => {
                            const id = readRecordNumber(r, "id")
                            if (id == null) return []
                            return [
                              <SelectItem key={id} value={String(id)}>
                                {readRecordString(r, "title") ?? `regulatory evidence id ${id}`}
                              </SelectItem>,
                            ]
                          })}
                        </SelectContent>
                      </Select>
                      <p className="text-xs text-muted-foreground">
                        Adds <span className="font-mono">regulatory_evidence_link_id</span> and titles to{" "}
                        <span className="font-mono">risk_signals_json</span>. Uses dossier evidence link ids (not compound
                        evidence links).
                      </p>
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label>rule set / jurisdiction trace (metadata_json.selected_rule_set_id)</Label>
                      <Select value={naRuleSetId} onValueChange={setNaRuleSetId}>
                        <SelectTrigger>
                          <SelectValue placeholder="Optional" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">none</SelectItem>
                          {ruleSets.flatMap((r) => {
                            const id = readRecordNumber(r, "id")
                            if (id == null) return []
                            return [
                              <SelectItem key={id} value={String(id)}>
                                {readRecordString(r, "name") ?? `rule_set id ${id}`} (id {id})
                              </SelectItem>,
                            ]
                          })}
                        </SelectContent>
                      </Select>
                      <p className="text-xs text-muted-foreground">
                        Matching uses active rule sets for the dossier on the server; this field is recorded in{" "}
                        <span className="font-mono">metadata_json</span> for traceability.
                      </p>
                    </div>
                  </div>
                  {naErr ? (
                    <Alert variant="destructive">
                      <AlertDescription className="text-sm">{naErr}</AlertDescription>
                    </Alert>
                  ) : null}
                  <Button type="button" disabled={naBusy} onClick={() => void runNitrosamineWatch()}>
                    {naBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    Run nitrosamine watch
                  </Button>
                </div>

                <Separator />

                {/* Dossier-level FDA-Rev-2 cumulative-risk rollup — sits between
                    the watch-create form and the per-watch assessment results,
                    beside the watch list. Best-effort fetch; null → muted note. */}
                <NitrosamineCumulativeRiskCard data={nitrosamineCumulativeRisk} />

                {latestNitrosamineAssessment ? (
                  (() => {
                    const assess = latestNitrosamineAssessment
                    const sumRaw = assess.nitrosamine_summary_json
                    const sum = sumRaw && typeof sumRaw === "object" ? (sumRaw as Record<string, unknown>) : null
                    const matched =
                      sum && Array.isArray(sum.matched_rules)
                        ? (sum.matched_rules.filter(isRecord) as Record<string, unknown>[])
                        : []
                    const rsj =
                      sum && Array.isArray(sum.risk_signals_json)
                        ? (sum.risk_signals_json.filter(isRecord) as Record<string, unknown>[])
                        : []
                    const meta = assess.metadata_json
                    const metaRec = meta && typeof meta === "object" ? (meta as Record<string, unknown>) : null
                    const reviewReq = sum?.review_required === true
                    const riskCat = sum ? readRecordString(sum, "risk_category") : undefined
                    const nitroConf = sum?.nitrosamine_confirmed
                    const cpcaLike =
                      riskCat === "cpca_review_required" || (riskCat ?? "").toLowerCase().includes("cpca")
                    const warnList = regulatoryAssessmentWarnings(assess)
                    const actionIds = readIntListField(assess, "action_item_ids_json")
                    const hr =
                      typeof assess.human_review_required === "boolean" ? assess.human_review_required : undefined
                    return (
                      <div className="space-y-4">
                        <div className="text-xs text-muted-foreground">
                          Latest assessment id{" "}
                          <span className="font-mono text-foreground">{readRecordNumber(assess, "id") ?? "—"}</span> ·
                          created_at{" "}
                          <span className="font-mono text-foreground">
                            {formatWhen(readRecordString(assess, "created_at"))}
                          </span>{" "}
                          · overall_status{" "}
                          <Badge variant="outline" className="text-xs capitalize">
                            {(readRecordString(assess, "overall_status") ?? "—").replace(/_/g, " ")}
                          </Badge>
                        </div>

                        <div className="flex flex-wrap gap-2">
                          <span className="text-xs text-muted-foreground">risk_category:</span>
                          <Badge variant="secondary" className="font-mono text-xs">
                            {riskCat ?? "—"}
                          </Badge>
                          {reviewReq ? (
                            <Badge variant="outline" className="text-xs">
                              review required
                            </Badge>
                          ) : null}
                          {cpcaLike ? (
                            <Badge variant="outline" className="text-xs">
                              CPCA-like review context (API risk_category)
                            </Badge>
                          ) : null}
                        </div>

                        <div className="rounded-md border bg-muted/30 px-3 py-2 text-xs">
                          <span className="font-medium text-foreground">nitrosamine_confirmed (API field): </span>
                          <span className="font-mono">{String(nitroConf)}</span>
                          <p className="mt-1 text-muted-foreground">
                            Backend flag only; a value of false does not eliminate all possible nitrosamine risk without
                            further evidence and qualified review.
                          </p>
                        </div>

                        {metaRec && Object.keys(metaRec).length > 0 ? (
                          <div>
                            <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                              evidence source (metadata_json)
                            </p>
                            <ul className="space-y-1 font-mono text-[11px] text-muted-foreground">
                              {Object.entries(metaRec).map(([k, v]) => (
                                <li key={k}>
                                  {k}: {typeof v === "object" ? JSON.stringify(v) : String(v)}
                                </li>
                              ))}
                            </ul>
                          </div>
                        ) : (
                          <p className="text-xs text-muted-foreground">metadata_json: —</p>
                        )}

                        {rsj.length ? (
                          <div>
                            <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                              risk_signals_json (returned)
                            </p>
                            <pre className="max-h-40 overflow-auto rounded-md border bg-muted/30 p-2 text-[11px]">
                              {JSON.stringify(rsj, null, 2)}
                            </pre>
                          </div>
                        ) : null}

                        {warnList.length ? (
                          <div>
                            <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">warnings</p>
                            <ul className="list-inside list-disc space-y-1 text-xs text-muted-foreground">
                              {warnList.map((w, i) => (
                                <li key={`nw-${i}`}>{w}</li>
                              ))}
                            </ul>
                          </div>
                        ) : null}

                        {matched.length === 0 ? (
                          <p className="text-sm text-muted-foreground">No matched_rules in nitrosamine_summary_json.</p>
                        ) : (
                          <div className="table-scroll">
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead>risk_category</TableHead>
                                  <TableHead>structural_pattern</TableHead>
                                  <TableHead>acceptable_intake</TableHead>
                                  <TableHead>ai_limit</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {matched.map((row, i) => (
                                  <TableRow key={`nm-${i}`}>
                                    <TableCell className="text-xs">
                                      {readRecordString(row, "risk_category") ?? "—"}
                                    </TableCell>
                                    <TableCell className="max-w-[220px] text-xs text-muted-foreground">
                                      {truncateText(readRecordString(row, "structural_pattern") ?? "", 120)}
                                    </TableCell>
                                    <TableCell className="font-mono text-xs">
                                      {typeof row.acceptable_intake === "number" && Number.isFinite(row.acceptable_intake)
                                        ? String(row.acceptable_intake)
                                        : "—"}
                                    </TableCell>
                                    <TableCell className="font-mono text-xs">
                                      {typeof row.ai_limit === "number" && Number.isFinite(row.ai_limit)
                                        ? String(row.ai_limit)
                                        : "—"}
                                    </TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </div>
                        )}

                        <div className="flex flex-wrap items-center gap-2 text-xs">
                          <span className="text-muted-foreground">human_review_required:</span>
                          {hr === true ? (
                            <Badge variant="outline" className="text-xs">
                              true
                            </Badge>
                          ) : hr === false ? (
                            <Badge variant="secondary" className="text-xs">
                              false
                            </Badge>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </div>

                        {actionIds.length ? (
                          <p className="text-xs text-muted-foreground">
                            action_item_ids_json:{" "}
                            <span className="font-mono text-foreground">{actionIds.join(", ")}</span>
                          </p>
                        ) : (
                          <p className="text-xs text-muted-foreground">action_item_ids_json: —</p>
                        )}
                      </div>
                    )
                  })()
                ) : (
                  <p className="text-sm text-muted-foreground">No nitrosamine watch assessment rows yet.</p>
                )}
              </div>
            </ModuleCard>
          </TabsContent>

          <TabsContent value="qnmr-method-validation" className="min-w-0 max-w-full space-y-6">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-cyan)" }}
              >
                Dossier · qNMR Validation
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">qNMR / method validation evidence</h2>
              <p className="text-sm text-muted-foreground">
                Method validation parameters, qualified-reference traceability, and reviewer signoff for quantitative NMR.
              </p>
            </div>
            <ModuleCard
              accent="cyan"
              eyebrow="Dossier · qNMR Validation"
              title={
                <span className="inline-flex items-center gap-2">
                  qNMR / Method Validation
                  <InfoTooltip label="qNMR / Method Validation" content={QNMR_METHOD_VALIDATION_TOOLTIP} />
                </span>
              }
              description="qNMR compliance readiness and method validation profile — readiness states are ready for review, gaps identified, or not assessed. Do not equate with validated unless both backend outputs and a qualified reviewer explicitly support that qualification."
            >
              <div className="space-y-6">
                <AlertCard
                  variant="info"
                  title="Documentation readiness signals only"
                  description="This workspace captures documentation readiness signals only. Use “ready for review”, “gaps identified”, or “not assessed” when describing states; avoid calling a method “validated” unless both backend outputs and qualified review explicitly support that wording."
                />

                <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
                  <h3 className="text-sm font-semibold">Assess method validation readiness</h3>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2 md:col-span-2">
                      <Label>method_type</Label>
                      <Select value={mvMethodType} onValueChange={setMvMethodType}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {ANALYTICAL_METHOD_TYPES.map((t) => (
                            <SelectItem key={t} value={t}>
                              {t}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="mv-atp">analytical_target_profile_json</Label>
                      <Textarea
                        id="mv-atp"
                        rows={4}
                        className="font-mono text-xs"
                        value={mvAtpJson}
                        onChange={(e) => setMvAtpJson(e.target.value)}
                        placeholder="{}"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="mv-valp">validation_parameters_json</Label>
                      <Textarea
                        id="mv-valp"
                        rows={4}
                        className="font-mono text-xs"
                        value={mvValParamsJson}
                        onChange={(e) => setMvValParamsJson(e.target.value)}
                        placeholder='e.g. {"specificity": {}, "accuracy": {}, "precision": {}}'
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="mv-cal">calibration_method</Label>
                      <Input
                        id="mv-cal"
                        value={mvCalibration}
                        onChange={(e) => setMvCalibration(e.target.value)}
                        autoComplete="off"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="mv-is">internal_standard</Label>
                      <Input
                        id="mv-is"
                        value={mvInternalStandard}
                        onChange={(e) => setMvInternalStandard(e.target.value)}
                        autoComplete="off"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="mv-acq">acquisition_parameters_json</Label>
                      <Textarea
                        id="mv-acq"
                        rows={3}
                        className="font-mono text-xs"
                        value={mvAcqJson}
                        onChange={(e) => setMvAcqJson(e.target.value)}
                        placeholder="{}"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="mv-unc">uncertainty_summary_json</Label>
                      <Textarea
                        id="mv-unc"
                        rows={3}
                        className="font-mono text-xs"
                        value={mvUncJson}
                        onChange={(e) => setMvUncJson(e.target.value)}
                        placeholder="{}"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="mv-qmeta">metadata_json (qNMR row — audit trail / hashes)</Label>
                      <Textarea
                        id="mv-qmeta"
                        rows={3}
                        className="font-mono text-xs"
                        value={mvQnmrMetaJson}
                        onChange={(e) => setMvQnmrMetaJson(e.target.value)}
                        placeholder='e.g. {"audit_trail": true}'
                      />
                      <p className="text-xs text-muted-foreground">
                        Optional <span className="font-mono">spectracheck_session_id</span> is added from the dossier when
                        omitted. Use <span className="font-mono">source_hash</span> / sample identifiers per your process.
                      </p>
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="mv-sh">linked raw file hash (metadata_json.source_hash)</Label>
                      <Input
                        id="mv-sh"
                        value={mvSourceHash}
                        onChange={(e) => setMvSourceHash(e.target.value)}
                        autoComplete="off"
                        placeholder="Optional"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label>linked SpectraCheck report (regulatory evidence)</Label>
                      <Select value={mvSpectraEvidenceId} onValueChange={setMvSpectraEvidenceId}>
                        <SelectTrigger>
                          <SelectValue placeholder="Optional" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">none</SelectItem>
                          {evidenceLinks.flatMap((r) => {
                            const id = readRecordNumber(r, "id")
                            if (id == null) return []
                            const et = readRecordString(r, "evidence_type")
                            if (et !== "spectracheck_report" && et !== "unified_evidence" && et !== "qc_assessment") {
                              return []
                            }
                            return [
                              <SelectItem key={id} value={String(id)}>
                                {et}: {readRecordString(r, "title") ?? `id ${id}`}
                              </SelectItem>,
                            ]
                          })}
                        </SelectContent>
                      </Select>
                      <p className="text-xs text-muted-foreground">
                        Stored under <span className="font-mono">metadata_json.regulatory_evidence_link_id</span> on the
                        qNMR compliance POST.
                      </p>
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="mv-mmeta">metadata_json (method-validation-profile)</Label>
                      <Textarea
                        id="mv-mmeta"
                        rows={3}
                        className="font-mono text-xs"
                        value={mvMethodMetaJson}
                        onChange={(e) => setMvMethodMetaJson(e.target.value)}
                        placeholder="{}"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="mv-mvs">linked method validation source</Label>
                      <Input
                        id="mv-mvs"
                        value={mvMethodValSource}
                        onChange={(e) => setMvMethodValSource(e.target.value)}
                        autoComplete="off"
                        placeholder="Stored as metadata_json.method_validation_source"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="mv-acc">accuracy_json</Label>
                      <Textarea
                        id="mv-acc"
                        rows={2}
                        className="font-mono text-xs"
                        value={mvAccuracyJson}
                        onChange={(e) => setMvAccuracyJson(e.target.value)}
                        placeholder="Optional object JSON"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="mv-prec">precision_json</Label>
                      <Textarea
                        id="mv-prec"
                        rows={2}
                        className="font-mono text-xs"
                        value={mvPrecisionJson}
                        onChange={(e) => setMvPrecisionJson(e.target.value)}
                        placeholder="Optional object JSON"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="mv-spec">specificity_json</Label>
                      <Textarea
                        id="mv-spec"
                        rows={2}
                        className="font-mono text-xs"
                        value={mvSpecificityJson}
                        onChange={(e) => setMvSpecificityJson(e.target.value)}
                        placeholder="Optional object JSON"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="mv-lin">linearity_json</Label>
                      <Textarea
                        id="mv-lin"
                        rows={2}
                        className="font-mono text-xs"
                        value={mvLinearityJson}
                        onChange={(e) => setMvLinearityJson(e.target.value)}
                        placeholder="Optional object JSON"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="mv-range">range_json</Label>
                      <Textarea
                        id="mv-range"
                        rows={2}
                        className="font-mono text-xs"
                        value={mvRangeJson}
                        onChange={(e) => setMvRangeJson(e.target.value)}
                        placeholder="Optional object JSON"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="mv-rob">robustness_json</Label>
                      <Textarea
                        id="mv-rob"
                        rows={2}
                        className="font-mono text-xs"
                        value={mvRobustnessJson}
                        onChange={(e) => setMvRobustnessJson(e.target.value)}
                        placeholder="Optional object JSON"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="mv-lod">lod_loq_json</Label>
                      <Textarea
                        id="mv-lod"
                        rows={2}
                        className="font-mono text-xs"
                        value={mvLodLoqJson}
                        onChange={(e) => setMvLodLoqJson(e.target.value)}
                        placeholder="Optional object JSON"
                      />
                    </div>
                  </div>
                  {mvAssessErr ? (
                    <Alert variant="destructive">
                      <AlertDescription className="text-sm">{mvAssessErr}</AlertDescription>
                    </Alert>
                  ) : null}
                  <Button type="button" disabled={mvAssessBusy} onClick={() => void runAssessMethodValidationReadiness()}>
                    {mvAssessBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    Assess method validation readiness
                  </Button>
                </div>

                <Separator />

                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="space-y-3 rounded-lg border p-4">
                    <h3 className="text-sm font-semibold">Latest qNMR compliance (GET …/qnmr-compliance)</h3>
                    {latestQnmrProfile ? (
                      <>
                        <div className="text-xs text-muted-foreground">
                          id <span className="font-mono text-foreground">{readRecordNumber(latestQnmrProfile, "id")}</span> ·
                          created_at{" "}
                          <span className="font-mono text-foreground">
                            {formatWhen(readRecordString(latestQnmrProfile, "created_at"))}
                          </span>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-xs text-muted-foreground">q2_q14_readiness_status:</span>
                          <Badge variant="outline" className="text-xs capitalize">
                            {readinessLabel(readRecordString(latestQnmrProfile, "q2_q14_readiness_status"))}
                          </Badge>
                        </div>
                        <div>
                          <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                            missing validation items (metadata_json.missing_metadata)
                          </p>
                          {(() => {
                            const m = latestQnmrProfile.metadata_json
                            const miss =
                              m && typeof m === "object" && Array.isArray((m as Record<string, unknown>).missing_metadata)
                                ? ((m as Record<string, unknown>).missing_metadata as unknown[]).filter(
                                    (x): x is string => typeof x === "string"
                                  )
                                : []
                            return miss.length ? (
                              <ul className="list-inside list-disc text-xs text-muted-foreground">
                                {miss.map((x, i) => (
                                  <li key={`miss-${i}`}>{x}</li>
                                ))}
                              </ul>
                            ) : (
                              <p className="text-xs text-muted-foreground">—</p>
                            )
                          })()}
                        </div>
                        <div>
                          <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">warnings</p>
                          <ul className="list-inside list-disc space-y-0.5 text-xs text-muted-foreground">
                            {regulatoryAssessmentWarnings(latestQnmrProfile).map((w, i) => (
                              <li key={`qw-${i}`}>{w}</li>
                            ))}
                          </ul>
                        </div>
                        <div>
                          <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">notes</p>
                          <ul className="list-inside list-disc space-y-0.5 text-xs text-muted-foreground">
                            {(Array.isArray(latestQnmrProfile.notes)
                              ? latestQnmrProfile.notes.filter((x): x is string => typeof x === "string")
                              : readStringArray(latestQnmrProfile, "notes_json")
                            ).map((n, i) => (
                              <li key={`qn-${i}`}>{n}</li>
                            ))}
                          </ul>
                        </div>
                        <div>
                          <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                            recommended actions (metadata_json.action_item_ids)
                          </p>
                          {(() => {
                            const m = latestQnmrProfile.metadata_json
                            const ids =
                              m && typeof m === "object"
                                ? readIntListField(m as Record<string, unknown>, "action_item_ids")
                                : []
                            return ids.length ? (
                              <p className="font-mono text-xs text-foreground">{ids.join(", ")}</p>
                            ) : (
                              <p className="text-xs text-muted-foreground">—</p>
                            )
                          })()}
                        </div>
                        <div>
                          <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">citations_json</p>
                          <pre className="max-h-32 overflow-auto rounded-md border bg-muted/30 p-2 text-[11px]">
                            {JSON.stringify(latestQnmrProfile.citations_json ?? [], null, 2)}
                          </pre>
                        </div>
                        <div className="flex flex-wrap items-center gap-2 text-xs">
                          <span className="text-muted-foreground">human_review_required:</span>
                          <Badge variant="outline" className="text-xs">
                            {String(latestQnmrProfile.human_review_required ?? "—")}
                          </Badge>
                        </div>
                      </>
                    ) : (
                      <p className="text-sm text-muted-foreground">No qNMR compliance profile rows yet.</p>
                    )}
                  </div>

                  <div className="space-y-3 rounded-lg border p-4">
                    <h3 className="text-sm font-semibold">Latest method validation profile (GET …/method-validation-profile)</h3>
                    {latestMethodProfile ? (
                      <>
                        <div className="text-xs text-muted-foreground">
                          id <span className="font-mono text-foreground">{readRecordNumber(latestMethodProfile, "id")}</span>{" "}
                          · method_type{" "}
                          <span className="font-mono text-foreground">
                            {readRecordString(latestMethodProfile, "method_type") ?? "—"}
                          </span>{" "}
                          · created_at{" "}
                          <span className="font-mono text-foreground">
                            {formatWhen(readRecordString(latestMethodProfile, "created_at"))}
                          </span>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-xs text-muted-foreground">validation_status:</span>
                          <Badge variant="outline" className="text-xs capitalize">
                            {readinessLabel(readRecordString(latestMethodProfile, "validation_status"))}
                          </Badge>
                        </div>
                        <div>
                          <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                            missing validation items (metadata_json.missing_categories)
                          </p>
                          {(() => {
                            const m = latestMethodProfile.metadata_json
                            const miss =
                              m && typeof m === "object" && Array.isArray((m as Record<string, unknown>).missing_categories)
                                ? ((m as Record<string, unknown>).missing_categories as unknown[]).filter(
                                    (x): x is string => typeof x === "string"
                                  )
                                : []
                            return miss.length ? (
                              <ul className="list-inside list-disc text-xs text-muted-foreground">
                                {miss.map((x, i) => (
                                  <li key={`mc-${i}`}>{x}</li>
                                ))}
                              </ul>
                            ) : (
                              <p className="text-xs text-muted-foreground">—</p>
                            )
                          })()}
                        </div>
                        <div>
                          <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">warnings</p>
                          <ul className="list-inside list-disc space-y-0.5 text-xs text-muted-foreground">
                            {readStringArray(latestMethodProfile, "warnings_json").map((w, i) => (
                              <li key={`mw-${i}`}>{w}</li>
                            ))}
                          </ul>
                        </div>
                        <div>
                          <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">notes</p>
                          <ul className="list-inside list-disc space-y-0.5 text-xs text-muted-foreground">
                            {readStringArray(latestMethodProfile, "notes_json").map((n, i) => (
                              <li key={`mn-${i}`}>{n}</li>
                            ))}
                          </ul>
                        </div>
                        <div className="flex flex-wrap items-center gap-2 text-xs">
                          <span className="text-muted-foreground">human_review_required:</span>
                          <Badge variant="outline" className="text-xs">
                            {String(latestMethodProfile.human_review_required ?? "—")}
                          </Badge>
                        </div>
                      </>
                    ) : (
                      <p className="text-sm text-muted-foreground">No analytical method validation profile rows yet.</p>
                    )}
                  </div>
                </div>

                <Collapsible className="rounded-lg border">
                  <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left text-sm font-medium hover:bg-muted/40">
                    Developer JSON
                    <ChevronDown className="h-4 w-4 shrink-0 opacity-70" />
                  </CollapsibleTrigger>
                  <CollapsibleContent className="border-t px-4 pb-4 pt-2">
                    <DeveloperJsonPanel
                      data={{
                        latest_qnmr_compliance_profile: latestQnmrProfile,
                        latest_method_validation_profile: latestMethodProfile,
                      }}
                    />
                  </CollapsibleContent>
                </Collapsible>
              </div>
            </ModuleCard>
          </TabsContent>

          <TabsContent value="ai-governance" className="min-w-0 max-w-full space-y-6">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-cyan)" }}
              >
                Dossier · AI Governance
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">AI / model-governance trail</h2>
              <p className="text-sm text-muted-foreground">
                Model versions, prompts, validation evidence, and human-review checkpoints for AI-assisted dossier content.
              </p>
            </div>
            <ModuleCard
              accent="cyan"
              eyebrow="Dossier · AI Governance"
              title={
                <span className="inline-flex items-center gap-2">
                  AI Governance
                  <InfoTooltip label="AI Governance" content={AI_GOVERNANCE_RECORD_TOOLTIP} />
                </span>
              }
              description="AI governance record for this dossier — documents the AI system name, version, intended use, and human oversight requirements for regulatory traceability."
            >
              <div className="space-y-6">
                {agCreateErr ? (
                  <Alert variant="destructive">
                    <AlertDescription className="text-sm">{agCreateErr}</AlertDescription>
                  </Alert>
                ) : null}

                <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
                  <h3 className="text-sm font-semibold">Create AI governance</h3>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="ag-name">ai_system_name</Label>
                      <Input
                        id="ag-name"
                        value={agName}
                        onChange={(e) => setAgName(e.target.value)}
                        autoComplete="off"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="ag-mvid">model_version_id</Label>
                      <Input
                        id="ag-mvid"
                        className="font-mono text-xs"
                        value={agModelVersionId}
                        onChange={(e) => setAgModelVersionId(e.target.value)}
                        placeholder="optional positive integer"
                        autoComplete="off"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="ag-mid">method_id</Label>
                      <Input
                        id="ag-mid"
                        className="font-mono text-xs"
                        value={agMethodId}
                        onChange={(e) => setAgMethodId(e.target.value)}
                        placeholder="optional positive integer"
                        autoComplete="off"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="ag-wf">workflow_run_id</Label>
                      <Input
                        id="ag-wf"
                        className="font-mono text-xs"
                        value={agWorkflowRunId}
                        onChange={(e) => setAgWorkflowRunId(e.target.value)}
                        placeholder="optional positive integer"
                        autoComplete="off"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="ag-ev">evidence_item_ids_json</Label>
                      <Textarea
                        id="ag-ev"
                        rows={2}
                        className="font-mono text-xs"
                        value={agEvidenceIds}
                        onChange={(e) => setAgEvidenceIds(e.target.value)}
                        placeholder="Comma- or newline-separated integers, e.g. 12, 34"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="ag-explain">explainability_summary_json</Label>
                      <Textarea
                        id="ag-explain"
                        rows={4}
                        className="font-mono text-xs"
                        value={agExplainJson}
                        onChange={(e) => setAgExplainJson(e.target.value)}
                        placeholder="{}"
                      />
                    </div>
                    <div className="flex items-center gap-3 md:col-span-2">
                      <Switch
                        id="ag-override"
                        checked={agHumanOverride}
                        onCheckedChange={setAgHumanOverride}
                      />
                      <Label htmlFor="ag-override" className="cursor-pointer font-mono text-sm">
                        human_override_available
                      </Label>
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="ag-val">validation_record_ids_json</Label>
                      <Textarea
                        id="ag-val"
                        rows={2}
                        className="font-mono text-xs"
                        value={agValidationRecordIds}
                        onChange={(e) => setAgValidationRecordIds(e.target.value)}
                        placeholder="Comma- or newline-separated integers"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="ag-gs">governance_status</Label>
                      <Select
                        value={agGovernanceStatus || "__unset__"}
                        onValueChange={(v) => setAgGovernanceStatus(v === "__unset__" ? "" : v)}
                      >
                        <SelectTrigger id="ag-gs">
                          <SelectValue placeholder="optional" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__unset__">— optional (backend default)</SelectItem>
                          {AI_GOVERNANCE_STATUSES.map((s) => (
                            <SelectItem key={s} value={s}>
                              {readinessLabel(s)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="ag-notes">notes_json (one line per entry)</Label>
                      <Textarea
                        id="ag-notes"
                        rows={3}
                        className="text-sm"
                        value={agNotesLines}
                        onChange={(e) => setAgNotesLines(e.target.value)}
                      />
                    </div>
                  </div>
                  <Button type="button" disabled={agCreateBusy} onClick={() => void createAiGovernanceRecord()}>
                    {agCreateBusy ? <Loader2 className="mr-2 size-4 animate-spin" aria-hidden /> : null}
                    Create AI governance
                  </Button>
                </div>

                <div className="space-y-3">
                  <h3 className="text-sm font-semibold">AI governance records</h3>
                  {aiGovernanceRecords.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No AI governance records yet.</p>
                  ) : (
                    aiGovernanceRecords.map((rec, idx) => {
                      const rid = readRecordNumber(rec, "id")
                      const key = rid != null ? `ag-${rid}` : `ag-i-${idx}`
                      const sys = readRecordString(rec, "ai_system_name") ?? "—"
                      const mvid = readRecordNumber(rec, "model_version_id")
                      const mid = readRecordNumber(rec, "method_id")
                      const wf = readRecordNumber(rec, "workflow_run_id")
                      const evid = readIntListField(rec, "evidence_item_ids_json")
                      const valIds = readIntListField(rec, "validation_record_ids_json")
                      const gov = readRecordString(rec, "governance_status")
                      const hOverride =
                        typeof rec.human_override_available === "boolean"
                          ? rec.human_override_available
                          : "—"
                      const hReview =
                        typeof rec.human_review_required === "boolean" ? String(rec.human_review_required) : "—"
                      const warnList =
                        Array.isArray(rec.warnings) && rec.warnings.every((x) => typeof x === "string")
                          ? (rec.warnings as string[])
                          : readStringArray(rec, "warnings_json")
                      const noteList =
                        Array.isArray(rec.notes) && rec.notes.every((x) => typeof x === "string")
                          ? (rec.notes as string[])
                          : readStringArray(rec, "notes_json")
                      const metaRaw = rec.metadata_json
                      const meta = isRecord(metaRaw) ? metaRaw : {}
                      const metaSafe = redactMetadataForDisplay(meta)
                      const actionIds = readIntListField(meta, "action_item_ids")
                      const gapItems = Array.isArray(meta.gaps)
                        ? (meta.gaps as unknown[]).filter((x): x is string => typeof x === "string")
                        : []
                      const explainRaw = rec.explainability_summary_json
                      const explain =
                        explainRaw && typeof explainRaw === "object" && !Array.isArray(explainRaw)
                          ? explainRaw
                          : {}
                      return (
                        <Card key={key} className="border-muted">
                          <CardHeader className="pb-2">
                            <CardTitle className="text-base">
                              {rid != null ? (
                                <span className="font-mono text-sm text-muted-foreground">#{rid}</span>
                              ) : null}{" "}
                              <span className="font-medium">{sys}</span>
                            </CardTitle>
                            <CardDescription className="text-xs">
                              created_at {formatWhen(readRecordString(rec, "created_at"))}
                            </CardDescription>
                          </CardHeader>
                          <CardContent className="space-y-4 text-sm">
                            <dl className="grid gap-3 sm:grid-cols-2">
                              <div>
                                <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                                  AI system
                                </dt>
                                <dd className="mt-1">{sys}</dd>
                              </div>
                              <div>
                                <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                                  method / model version
                                </dt>
                                <dd className="mt-1 font-mono text-xs">
                                  model_version_id {mvid ?? "—"} · method_id {mid ?? "—"}
                                </dd>
                              </div>
                              <div>
                                <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                                  workflow version
                                </dt>
                                <dd className="mt-1 font-mono text-xs">
                                  workflow_run_id {wf ?? "—"}
                                </dd>
                              </div>
                              <div>
                                <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                                  validation records
                                </dt>
                                <dd className="mt-1 font-mono text-xs">
                                  {valIds.length ? valIds.join(", ") : "—"}
                                </dd>
                              </div>
                              <div>
                                <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                                  evidence_item_ids_json
                                </dt>
                                <dd className="mt-1 font-mono text-xs">
                                  {evid.length ? evid.join(", ") : "—"}
                                </dd>
                              </div>
                              <div>
                                <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                                  human override state
                                </dt>
                                <dd className="mt-1 font-mono text-xs">{String(hOverride)}</dd>
                              </div>
                              <div>
                                <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                                  human_review_required
                                </dt>
                                <dd className="mt-1 font-mono text-xs">{hReview}</dd>
                              </div>
                              <div>
                                <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                                  governance status
                                </dt>
                                <dd className="mt-1">
                                  <Badge variant="outline" className="font-normal">
                                    {gov ? readinessLabel(gov) : "—"}
                                  </Badge>
                                </dd>
                              </div>
                            </dl>
                            {gapItems.length > 0 ? (
                              <p className="text-xs text-amber-800 dark:text-amber-200">
                                Gaps flagged (metadata): {gapItems.join(", ")}
                              </p>
                            ) : null}
                            {actionIds.length > 0 ? (
                              <p className="text-xs text-muted-foreground">
                                Linked action item IDs (audit trail):{" "}
                                <span className="font-mono">{actionIds.join(", ")}</span>
                              </p>
                            ) : null}
                            <div>
                              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                                warnings
                              </p>
                              {warnList.length ? (
                                <ul className="mt-1 list-inside list-disc text-xs leading-relaxed">
                                  {warnList.map((w, i) => (
                                    <li key={`${key}-w-${i}`}>{w}</li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="mt-1 text-xs text-muted-foreground">—</p>
                              )}
                            </div>
                            <div>
                              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                                notes
                              </p>
                              {noteList.length ? (
                                <ul className="mt-1 list-inside list-disc text-xs leading-relaxed">
                                  {noteList.map((n, i) => (
                                    <li key={`${key}-n-${i}`}>{n}</li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="mt-1 text-xs text-muted-foreground">—</p>
                              )}
                            </div>
                            <Collapsible className="rounded-md border bg-muted/15">
                              <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs font-medium hover:bg-muted/40">
                                <span>Explainability &amp; metadata (developer JSON)</span>
                                <ChevronDown className="h-4 w-4 shrink-0 opacity-70" />
                              </CollapsibleTrigger>
                              <CollapsibleContent className="space-y-3 border-t px-3 pb-3 pt-2">
                                <p className="text-xs text-muted-foreground">explainability_summary_json</p>
                                <DeveloperJsonPanel data={explain} />
                                <p className="text-xs text-muted-foreground">metadata_json (sensitive keys redacted)</p>
                                <DeveloperJsonPanel data={metaSafe} />
                              </CollapsibleContent>
                            </Collapsible>
                          </CardContent>
                        </Card>
                      )
                    })
                  )}
                </div>
              </div>
            </ModuleCard>

            {/* EU GMP Draft Annex 22 AI-decision records — beneath the existing
                AI-governance content. Draft framing: renders the API disclaimer,
                never claims compliance. */}
            {Number.isFinite(dossierId) ? (
              <DossierAIDecisionsPanel
                decisions={aiDecisions}
                dossierId={dossierId}
                onReviewed={refreshAiDecisions}
              />
            ) : null}
          </TabsContent>

          <TabsContent value="jurisdictional-map" className="min-w-0 max-w-full space-y-6">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-cyan)" }}
              >
                Dossier · Jurisdictional Map
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Per-region requirement coverage</h2>
              <p className="text-sm text-muted-foreground">
                FDA / EMA / PMDA / multi-region requirement matrix with coverage status and missing-evidence callouts.
              </p>
            </div>
            <ModuleCard
              accent="cyan"
              eyebrow="Dossier · Jurisdictions"
              title={
                <span className="inline-flex items-center gap-2">
                  Jurisdictional Map
                  <InfoTooltip label="Jurisdictional map" content={JURISDICTIONAL_MAP_TOOLTIP} />
                </span>
              }
              description={
                <>
                  Maps this dossier's requirements and evidence to applicable jurisdictions and rule sets. Jurisdiction catalogue and source catalogue are available via{" "}
                  <Link href="/regulatory/sources" className="underline-offset-4 hover:underline">
                    Regulatory Sources
                  </Link>
                  .
                </>
              }
            >
                <AlertCard
                  variant="info"
                  title="Compliance API outputs"
                  description="Outputs below come from the regulatory compliance API (rule sets, thresholds, and dossier metadata). This view does not assert jurisdiction-specific legal obligations."
                />

                <dl className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                      dossier jurisdiction
                    </dt>
                    <dd className="mt-1 text-sm">{jurisdictionLabel}</dd>
                  </div>
                  <div>
                    <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">jurisdiction_id</dt>
                    <dd className="mt-1 font-mono text-sm">{readRecordNumber(dossier, "jurisdiction_id") ?? "—"}</dd>
                  </div>
                </dl>

                {jmBuildErr ? (
                  <AlertCard variant="error" title="Build failed" description={jmBuildErr} />
                ) : null}

                <div className="space-y-4 rounded-lg border bg-muted/20 p-4">
                  <h3 className="text-sm font-semibold">Build jurisdictional map</h3>
                  <p className="text-xs text-muted-foreground">
                    Select one or more jurisdictions. The lowest numeric <span className="font-mono">jurisdiction_id</span>{" "}
                    in the selection is sent as <span className="font-mono">jurisdiction_id</span>; the remainder populate{" "}
                    <span className="font-mono">compare_jurisdiction_ids_json</span>. With only one selected, the server
                    compares against the dossier baseline when configured.
                  </p>

                  <div className="space-y-2">
                    <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                      Jurisdiction presets
                    </p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {jmPresetRows.map(({ label, id }) => (
                        <div key={label} className="flex items-start gap-2 rounded-md border bg-background/60 p-2">
                          <Checkbox
                            id={`jm-preset-${label}`}
                            checked={id != null && jmSelectedIds.includes(id)}
                            disabled={id == null}
                            onCheckedChange={(v) => {
                              if (id == null) return
                              toggleJmJurisdictionId(id, v === true)
                            }}
                          />
                          <div className="min-w-0 flex-1">
                            <Label htmlFor={`jm-preset-${label}`} className="cursor-pointer text-sm font-medium">
                              {label}
                            </Label>
                            <p className="font-mono text-[11px] text-muted-foreground">
                              {id != null ? `${jurisdictions.find((j) => j.id === id)?.name ?? "—"} (id {id})` : "— not in catalogue"}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-2">
                    <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                      Other / custom (all jurisdictions)
                    </p>
                    <div className="max-h-48 space-y-2 overflow-y-auto rounded-md border bg-background/60 p-2">
                      {jurisdictions.map((j) => (
                        <div key={j.id} className="flex items-center gap-2">
                          <Checkbox
                            id={`jm-jur-${j.id}`}
                            checked={jmSelectedIds.includes(j.id)}
                            onCheckedChange={(v) => toggleJmJurisdictionId(j.id, v === true)}
                          />
                          <Label htmlFor={`jm-jur-${j.id}`} className="cursor-pointer font-mono text-xs font-normal">
                            {j.name} <span className="text-muted-foreground">({j.id})</span>
                          </Label>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="jm-ruleset">rule_set_id</Label>
                    <Select value={jmRuleSetId} onValueChange={setJmRuleSetId}>
                      <SelectTrigger id="jm-ruleset">
                        <SelectValue placeholder="Optional" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">none</SelectItem>
                        {ruleSets.flatMap((r) => {
                          const id = readRecordNumber(r, "id")
                          if (id == null) return []
                          return [
                            <SelectItem key={id} value={String(id)}>
                              {readRecordString(r, "name") ?? `rule_set id ${id}`} (id {id})
                            </SelectItem>,
                          ]
                        })}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="flex items-center gap-2">
                      <Switch
                        id="jm-nitro"
                        checked={jmIncNitrosamine}
                        onCheckedChange={setJmIncNitrosamine}
                      />
                      <Label htmlFor="jm-nitro" className="cursor-pointer font-mono text-xs">
                        include_nitrosamine_rules (metadata_json)
                      </Label>
                    </div>
                    <div className="flex items-center gap-2">
                      <Switch
                        id="jm-res"
                        checked={jmIncResidual}
                        onCheckedChange={setJmIncResidual}
                      />
                      <Label htmlFor="jm-res" className="cursor-pointer font-mono text-xs">
                        include_residual_solvent_rules (metadata_json)
                      </Label>
                    </div>
                    <div className="flex items-center gap-2">
                      <Switch
                        id="jm-qnmr"
                        checked={jmIncQnmr}
                        onCheckedChange={setJmIncQnmr}
                      />
                      <Label htmlFor="jm-qnmr" className="cursor-pointer font-mono text-xs">
                        include_qnmr_method_validation_rules (metadata_json)
                      </Label>
                    </div>
                    <div className="flex items-center gap-2">
                      <Switch
                        id="jm-ai"
                        checked={jmIncAiGov}
                        onCheckedChange={setJmIncAiGov}
                      />
                      <Label htmlFor="jm-ai" className="cursor-pointer font-mono text-xs">
                        include_ai_governance_rules (metadata_json)
                      </Label>
                    </div>
                  </div>

                  <Button type="button" disabled={jmBuildBusy} onClick={() => void buildJurisdictionalMap()}>
                    {jmBuildBusy ? <Loader2 className="mr-2 size-4 animate-spin" aria-hidden /> : null}
                    Build jurisdictional map
                  </Button>
                </div>

                <div className="space-y-3">
                  <h3 className="text-sm font-semibold">Jurisdictional maps</h3>
                  {jurisdictionalMaps.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No jurisdictional maps saved for this dossier yet.</p>
                  ) : (
                    jurisdictionalMaps.map((row, idx) => {
                      const mapId = readRecordNumber(row, "id")
                      const key = mapId != null ? `jm-${mapId}` : `jm-row-${idx}`
                      const jid = readRecordNumber(row, "jurisdiction_id")
                      const jname = jid != null ? jurisdictionNameById.get(jid) ?? `jurisdiction_id ${jid}` : "—"
                      const rsid = readRecordNumber(row, "rule_set_id")
                      const rsRow = rsid != null ? ruleSets.find((r) => readRecordNumber(r, "id") === rsid) : undefined
                      const rsLabel =
                        rsid == null
                          ? "—"
                          : readRecordString(rsRow, "name") ?? `rule_set_id ${rsid}`
                      const warnList = jurisdictionalMapWarningLines(row)
                      const noteList = jurisdictionalMapNoteLines(row)
                      const thresholdSummary = row.threshold_summary_json
                      const differences = row.differences_json
                      const reqSummary = row.requirement_summary_json
                      const meta = row.metadata_json
                      const missingSrc = warnList.some((w) => /source_needed|no active rule sets/i.test(w))
                      const missingSourceNotes = warnList.filter((w) => /source/i.test(w))
                      return (
                        <Card key={key} className="border-muted">
                          <CardHeader className="pb-2">
                            <CardTitle className="text-base">
                              Map{" "}
                              <span className="font-mono text-sm text-muted-foreground">#{mapId ?? "—"}</span>
                            </CardTitle>
                            <CardDescription className="text-xs">
                              created_at {formatWhen(readRecordString(row, "created_at"))}
                            </CardDescription>
                          </CardHeader>
                          <CardContent className="space-y-4 text-sm">
                            <dl className="grid gap-3 sm:grid-cols-2">
                              <div>
                                <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                                  jurisdiction
                                </dt>
                                <dd className="mt-1">
                                  {jname}{" "}
                                  {jid != null ? (
                                    <span className="font-mono text-xs text-muted-foreground">(id {jid})</span>
                                  ) : null}
                                </dd>
                              </div>
                              <div>
                                <dt className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                                  rule set
                                </dt>
                                <dd className="mt-1 text-sm">
                                  {rsLabel}{" "}
                                  {rsid != null ? (
                                    <span className="font-mono text-xs text-muted-foreground">(id {rsid})</span>
                                  ) : (
                                    <span className="text-xs text-muted-foreground">(rule_set_id null)</span>
                                  )}
                                </dd>
                              </div>
                            </dl>

                            {missingSrc ? (
                              <Alert>
                                <AlertDescription className="text-sm">{JURISDICTION_MAP_RULE_SOURCE_MSG}</AlertDescription>
                              </Alert>
                            ) : null}

                            <div>
                              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                                threshold summary
                              </p>
                              <div className="mt-2">
                                <DeveloperJsonPanel data={thresholdSummary && typeof thresholdSummary === "object" ? thresholdSummary : {}} />
                              </div>
                            </div>

                            <div>
                              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                                requirement differences
                              </p>
                              <div className="mt-2">
                                <DeveloperJsonPanel data={differences && typeof differences === "object" ? differences : {}} />
                              </div>
                            </div>

                            <div>
                              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                                requirement_summary_json
                              </p>
                              <div className="mt-2">
                                <DeveloperJsonPanel data={reqSummary && typeof reqSummary === "object" ? reqSummary : {}} />
                              </div>
                            </div>

                            <div>
                              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                                missing sources
                              </p>
                              {missingSourceNotes.length ? (
                                <ul className="mt-1 list-inside list-disc text-xs leading-relaxed">
                                  {missingSourceNotes.map((w, i) => (
                                    <li key={`${key}-ms-${i}`}>{w}</li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="mt-1 text-xs text-muted-foreground">—</p>
                              )}
                            </div>

                            <div>
                              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                                warnings
                              </p>
                              {warnList.length ? (
                                <ul className="mt-1 list-inside list-disc text-xs leading-relaxed">
                                  {warnList.map((w, i) => (
                                    <li key={`${key}-w-${i}`}>{w}</li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="mt-1 text-xs text-muted-foreground">—</p>
                              )}
                            </div>

                            <div>
                              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">notes</p>
                              {noteList.length ? (
                                <ul className="mt-1 list-inside list-disc text-xs leading-relaxed">
                                  {noteList.map((n, i) => (
                                    <li key={`${key}-n-${i}`}>{n}</li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="mt-1 text-xs text-muted-foreground">—</p>
                              )}
                            </div>

                            <Collapsible className="rounded-md border bg-muted/15">
                              <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs font-medium hover:bg-muted/40">
                                metadata_json
                                <ChevronDown className="h-4 w-4 shrink-0 opacity-70" />
                              </CollapsibleTrigger>
                              <CollapsibleContent className="border-t px-3 pb-3 pt-2">
                                <DeveloperJsonPanel data={meta && typeof meta === "object" ? meta : {}} />
                              </CollapsibleContent>
                            </Collapsible>
                          </CardContent>
                        </Card>
                      )
                    })
                  )}
                </div>

                <div className="space-y-2">
                  <h3 className="text-sm font-semibold">Action items</h3>
                  <p className="text-xs text-muted-foreground">
                    Dossier-scoped queue (same as the Action Items tab).{" "}
                    <Link href="/regulatory/action-queue" className="underline-offset-4 hover:underline">
                      Open full queue
                    </Link>
                    .
                  </p>
                  {Number.isFinite(dossierId) ? (
                    <RegulatoryActionQueue dossierId={dossierId} compact />
                  ) : null}
                </div>

                <Collapsible className="rounded-lg border">
                  <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left text-sm font-medium hover:bg-muted/40">
                    Jurisdiction catalogue
                    <ChevronDown className="h-4 w-4 shrink-0 opacity-70" />
                  </CollapsibleTrigger>
                  <CollapsibleContent className="border-t px-4 pb-4 pt-2">
                    <div className="table-scroll">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>id</TableHead>
                            <TableHead>name</TableHead>
                            <TableHead className="w-[140px]">sources</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {jurisdictions.map((j) => (
                            <TableRow key={j.id}>
                              <TableCell className="font-mono text-xs">{j.id}</TableCell>
                              <TableCell className="text-sm">{j.name}</TableCell>
                              <TableCell>
                                <Button variant="outline" size="sm" asChild>
                                  <Link href="/regulatory/sources">Open sources</Link>
                                </Button>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </CollapsibleContent>
                </Collapsible>
            </ModuleCard>
          </TabsContent>

          <TabsContent value="change-impact" className="min-w-0 max-w-full space-y-6">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-cyan)" }}
              >
                Dossier · Change Impact
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Detected regulatory changes affecting this dossier</h2>
              <p className="text-sm text-muted-foreground">
                Downstream impact of detected regulatory changes on this dossier's requirements, evidence links, rule sets, and action items.
              </p>
            </div>
            <ModuleCard
              accent="cyan"
              eyebrow="Dossier · Change Impact"
              title="Change Impact"
              description="Downstream impact of detected regulatory changes on this dossier's requirements, evidence links, rule sets, and action items."
            >
                {changeImpactErr ? (
                  <AlertCard variant="error" title="Change impact failed" description={changeImpactErr} />
                ) : null}

                {!changeImpactErr && changeImpact ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                      human_review_required
                    </span>
                    <Badge
                      variant="outline"
                      style={
                        changeImpact.human_review_required
                          ? { borderColor: "var(--mt-amber)", color: "var(--mt-amber)" }
                          : { borderColor: "var(--mt-green)", color: "var(--mt-green)" }
                      }
                    >
                      {changeImpact.human_review_required ? "required" : "not flagged"}
                    </Badge>
                  </div>
                ) : null}

                {!changeImpactErr && dossierChangeImpactEvents.length === 0 ? (
                  <div className="space-y-2 text-sm text-muted-foreground">
                    <p>No regulatory source changes currently mapped to this dossier.</p>
                    <p>
                      Absence of mapped changes does not indicate compliance status.
                    </p>
                  </div>
                ) : null}

                {!changeImpactErr && dossierChangeImpactEvents.length > 0 ? (
                  <>
                    <div className="table-scroll">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>change_event_id</TableHead>
                            <TableHead>title</TableHead>
                            <TableHead>review_status</TableHead>
                            <TableHead className="w-[130px]">open change button</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {dossierChangeImpactEvents.map((row, idx) => {
                            const cid = readRecordNumber(row, "id")
                            return (
                              <TableRow key={cid != null ? `dce-${cid}` : `dce-${idx}`}>
                                <TableCell className="font-mono text-xs">{cid ?? "—"}</TableCell>
                                <TableCell className="max-w-[280px] text-sm">
                                  {readRecordString(row, "title") ?? "—"}
                                </TableCell>
                                <TableCell className="text-xs">
                                  <Badge variant="outline">{readRecordString(row, "review_status") ?? "—"}</Badge>
                                </TableCell>
                                <TableCell>
                                  {cid != null ? (
                                    <Button variant="outline" size="sm" asChild>
                                      <Link href={`/regulatory/changes/${cid}`}>Open change</Link>
                                    </Button>
                                  ) : (
                                    "—"
                                  )}
                                </TableCell>
                              </TableRow>
                            )
                          })}
                        </TableBody>
                      </Table>
                    </div>

                    <div className="grid gap-4 md:grid-cols-3">
                      <Card
                        className="overflow-hidden rounded-xl border-muted py-0"
                        style={{ borderTop: "3px solid var(--mt-cyan)" }}
                      >
                        <CardHeader className="pt-4 pb-2">
                          <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                            Impacted requirements
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-1 pb-4 text-xs">
                          <p
                            className="font-mono text-2xl font-bold tabular-nums leading-none"
                            style={{ color: "var(--mt-cyan)" }}
                          >
                            {dossierMergedRequirementIds.length}
                          </p>
                          <p className="break-all font-mono text-[11px] text-muted-foreground">
                            {dossierMergedRequirementIds.length ? dossierMergedRequirementIds.join(", ") : "—"}
                          </p>
                        </CardContent>
                      </Card>
                      <Card
                        className="overflow-hidden rounded-xl border-muted py-0"
                        style={{ borderTop: "3px solid var(--mt-amber)" }}
                      >
                        <CardHeader className="pt-4 pb-2">
                          <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                            Impacted action items
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-1 pb-4 text-xs">
                          <p
                            className="font-mono text-2xl font-bold tabular-nums leading-none"
                            style={{ color: "var(--mt-amber)" }}
                          >
                            {dossierMergedActionItemIds.length}
                          </p>
                          <p className="break-all font-mono text-[11px] text-muted-foreground">
                            {dossierMergedActionItemIds.length ? dossierMergedActionItemIds.join(", ") : "—"}
                          </p>
                        </CardContent>
                      </Card>
                      <Card
                        className="overflow-hidden rounded-xl border-muted py-0"
                        style={{ borderTop: "3px solid var(--mt-cyan)" }}
                      >
                        <CardHeader className="pt-4 pb-2">
                          <CardTitle className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                            Impacted rule sets
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-1 pb-4 text-xs">
                          <p
                            className="font-mono text-2xl font-bold tabular-nums leading-none"
                            style={{ color: "var(--mt-cyan)" }}
                          >
                            {dossierMergedRuleSetIds.length}
                          </p>
                          <p className="break-all font-mono text-[11px] text-muted-foreground">
                            {dossierMergedRuleSetIds.length ? dossierMergedRuleSetIds.join(", ") : "—"}
                          </p>
                        </CardContent>
                      </Card>
                    </div>

                    <div className="space-y-2">
                      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                        recommended actions
                      </p>
                      {dossierMergedRecommendedActions.length === 0 ? (
                        <p className="text-sm text-muted-foreground">No recommended actions returned.</p>
                      ) : (
                        <div className="space-y-2">
                          {dossierMergedRecommendedActions.map((act, i) => (
                            <Card key={`dca-${i}`} className="border-muted">
                              <CardContent className="pt-4 text-sm">
                                <p className="font-medium">{readRecordString(act, "title") ?? "—"}</p>
                                <p className="mt-1 text-muted-foreground">{readRecordString(act, "description") ?? "—"}</p>
                                <p className="mt-2 text-xs text-muted-foreground">
                                  action_type {readRecordString(act, "action_type") ?? "—"}
                                </p>
                              </CardContent>
                            </Card>
                          ))}
                        </div>
                      )}
                    </div>
                  </>
                ) : null}

                {!changeImpactErr && changeImpact ? (
                  <DeveloperJsonPanel data={changeImpact} />
                ) : null}
            </ModuleCard>
          </TabsContent>

          <TabsContent value="action-items" className="min-w-0 max-w-full space-y-6">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-cyan)" }}
              >
                Dossier · Action Items
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Reviewer & operational workflow</h2>
              <p className="text-sm text-muted-foreground">
                Cited Q&amp;A, risk hot-spots, review checkpoints, and submission-readiness — each routes to the global Action Queue when escalated.
              </p>
            </div>
            {Number.isFinite(dossierId) ? (
              <RegulatoryActionQueueCard dossierId={dossierId} />
            ) : (
              <AlertCard
                variant="error"
                title="Invalid dossier"
                description="Action Items unavailable — use a numeric dossier id in the URL."
              />
            )}
            <ReactionOptimizationHandoffCard
              dossierId={dossierId}
              reactionProjectId={dossierReactionProjectId}
              compoundId={dossierCompoundId}
              batchId={dossierBatchId}
            />
          </TabsContent>

          <TabsContent value="qa" className="min-w-0 max-w-full space-y-6">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-cyan)" }}
              >
                Dossier · Cited Q&amp;A
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Reviewer Q&amp;A with citations</h2>
              <p className="text-sm text-muted-foreground">
                Question / answer pairs that must cite source evidence. Required before promoting to in-review.
              </p>
            </div>
            <Alert>
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Mandatory</AlertTitle>
              <AlertDescription className="space-y-1 text-sm leading-relaxed">
                <p>{QA_MANDATORY_WARNING}</p>
                <p className="text-muted-foreground">This workflow is not legal advice.</p>
              </AlertDescription>
            </Alert>

            <ModuleCard
              accent="cyan"
              eyebrow="Dossier · Cited Q&A"
              title="Cited Q&A"
              description="Cited regulatory Q&A — questions are answered by the backend using source-referenced guidance; responses are not synthesized in the browser. This is not legal advice."
            >
              <div className="space-y-4">
                <div className="rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">Dossier jurisdiction: </span>
                  {dossierJurisdictionLine}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="reg-qa-q">question</Label>
                  <Textarea
                    id="reg-qa-q"
                    rows={4}
                    value={qaQuestion}
                    onChange={(e) => setQaQuestion(e.target.value)}
                    placeholder="Enter a question for cited retrieval"
                  />
                </div>
                <div className="space-y-2">
                  <Label>jurisdiction selector optional</Label>
                  <Select value={qaJurisdictionId || "none"} onValueChange={(v) => setQaJurisdictionId(v === "none" ? "" : v)}>
                    <SelectTrigger className="max-w-md">
                      <SelectValue placeholder="Use dossier default when unset" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">Use dossier default</SelectItem>
                      {jurisdictions.map((j) => (
                        <SelectItem key={j.id} value={String(j.id)}>
                          {j.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>source scope selector optional</Label>
                  <Select value={qaSourceScope || "none"} onValueChange={(v) => setQaSourceScope(v === "none" ? "" : v)}>
                    <SelectTrigger className="max-w-md">
                      <SelectValue placeholder="No explicit scope in metadata_json" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">No explicit scope</SelectItem>
                      {QA_SOURCE_SCOPE_OPTIONS.map((o) => (
                        <SelectItem key={o.value} value={o.value}>
                          {o.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    When set, stored under <span className="font-mono">metadata_json.source_scope</span> on the query
                    request body.
                  </p>
                </div>
                {qaErr ? (
                  <Alert variant="destructive">
                    <AlertDescription className="text-sm">{qaErr}</AlertDescription>
                  </Alert>
                ) : null}
                <Button type="button" disabled={qaBusy} onClick={() => void askWithCitedSources()}>
                  {qaBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Ask with cited sources
                </Button>
              </div>
            </ModuleCard>

            {queryResult ? (
              <ModuleCard
                accent="cyan"
                eyebrow="QA · Query Response"
                title="Query response"
                description={
                  <>
                    status:{" "}
                    <span className="font-mono text-xs">{readRecordString(queryResult, "status") ?? "—"}</span>
                  </>
                }
                badge={
                  <Badge variant="secondary" className="shrink-0">
                    human_review_required: {String(queryResult.human_review_required ?? "—")}
                  </Badge>
                }
              >
                <div className="space-y-4 text-sm">
                  {readRecordString(queryResult, "status") === "insufficient_sources" ? (
                    <AlertCard variant="info" title="Insufficient sources" description={INSUFFICIENT_SOURCES_USER_MESSAGE} />
                  ) : null}

                  <div>
                    <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">question</p>
                    <p className="mt-1 whitespace-pre-wrap">{readRecordString(queryResult, "question") ?? "—"}</p>
                  </div>

                  {isRecord(queryResult.answer) ? (
                    <div className="space-y-4 rounded-md border bg-muted/30 p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">answer</p>
                        <Badge variant="outline" className="text-xs capitalize">
                          human_review_required:{" "}
                          {String((queryResult.answer as Record<string, unknown>).human_review_required ?? "—")}
                        </Badge>
                      </div>
                      <div>
                        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">answer_text</p>
                        <p className="mt-1 whitespace-pre-wrap leading-relaxed">
                          {readRecordString(queryResult.answer as Record<string, unknown>, "answer_text") ?? "—"}
                        </p>
                      </div>
                      <div>
                        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">confidence_label</p>
                        <p className="mt-1 font-mono text-xs">
                          {readRecordString(queryResult.answer as Record<string, unknown>, "confidence_label") ?? "—"}
                        </p>
                      </div>

                      <div className="rounded-md border border-dashed bg-background/50 px-3 py-2">
                        <MlModelProvenanceSummary
                          sources={[queryResult.answer, queryResult]}
                          humanReviewExtras={
                            <div className="mt-2 space-y-1 border-t border-border pt-2 text-[11px] text-muted-foreground">
                              <p>
                                <span className="font-mono text-foreground/80">human_review_required (answer): </span>
                                {String((queryResult.answer as Record<string, unknown>).human_review_required ?? "—")}
                              </p>
                              {readRecordString(
                                queryResult.answer as Record<string, unknown>,
                                "human_review_state",
                              ) ? (
                                <p>
                                  <span className="font-mono text-foreground/80">human_review_state: </span>
                                  {readRecordString(
                                    queryResult.answer as Record<string, unknown>,
                                    "human_review_state",
                                  )}
                                </p>
                              ) : null}
                            </div>
                          }
                        />
                      </div>

                      {Array.isArray((queryResult.answer as Record<string, unknown>).citations) &&
                      ((queryResult.answer as Record<string, unknown>).citations as unknown[]).filter(isRecord).length >
                        0 ? (
                        <div>
                          <p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">citations</p>
                          <ul className="space-y-3">
                            {((queryResult.answer as Record<string, unknown>).citations as unknown[])
                              .filter(isRecord)
                              .map((c, i) => (
                                <li key={i} className="rounded-md border bg-card px-3 py-2 text-xs">
                                  <p className="font-mono font-medium">
                                    id {readRecordNumber(c, "id") ?? "—"} · {readRecordString(c, "citation_label") ?? "—"}
                                  </p>
                                  {readRecordString(c, "section_title") ? (
                                    <p className="mt-1 text-muted-foreground">{readRecordString(c, "section_title")}</p>
                                  ) : null}
                                  <p className="mt-1 text-muted-foreground">
                                    page_number / paragraph_number: {readRecordNumber(c, "page_number") ?? "—"} /{" "}
                                    {readRecordNumber(c, "paragraph_number") ?? "—"}
                                  </p>
                                  {readRecordString(c, "quote_excerpt") ? (
                                    <blockquote className="mt-2 border-l-2 pl-2 text-muted-foreground">
                                      {readRecordString(c, "quote_excerpt")}
                                    </blockquote>
                                  ) : null}
                                  {readRecordString(c, "summary") ? (
                                    <p className="mt-2 text-muted-foreground">{readRecordString(c, "summary")}</p>
                                  ) : null}
                                </li>
                              ))}
                          </ul>
                        </div>
                      ) : (
                        <p className="text-xs text-muted-foreground">No citations returned on this answer.</p>
                      )}

                      <div>
                        <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">missing_sources_json</p>
                        {Array.isArray((queryResult.answer as Record<string, unknown>).missing_sources_json) &&
                        ((queryResult.answer as Record<string, unknown>).missing_sources_json as unknown[]).length >
                          0 ? (
                          <ul className="list-inside list-disc space-y-1 font-mono text-[11px] text-muted-foreground">
                            {((queryResult.answer as Record<string, unknown>).missing_sources_json as unknown[])
                              .filter(isRecord)
                              .map((row, i) => (
                                <li key={i} className="break-all">
                                  {JSON.stringify(row)}
                                </li>
                              ))}
                          </ul>
                        ) : (
                          <p className="text-xs text-muted-foreground">—</p>
                        )}
                      </div>

                      <div>
                        <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">warnings</p>
                        {(() => {
                          const ans = queryResult.answer as Record<string, unknown>
                          const merged = [
                            ...readStringArray(queryResult, "warnings"),
                            ...readStringArray(ans, "warnings"),
                            ...readStringArray(ans, "warnings_json"),
                          ]
                          return merged.length ? (
                            <ul className="space-y-1 text-xs text-muted-foreground">
                              {merged.map((w, i) => (
                                <li key={`w-${i}`}>{w}</li>
                              ))}
                            </ul>
                          ) : (
                            <p className="text-xs text-muted-foreground">—</p>
                          )
                        })()}
                      </div>

                      <div>
                        <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">notes</p>
                        {(() => {
                          const ans = queryResult.answer as Record<string, unknown>
                          const merged = [
                            ...readStringArray(queryResult, "notes"),
                            ...readStringArray(ans, "notes"),
                            ...readStringArray(ans, "notes_json"),
                          ]
                          return merged.length ? (
                            <ul className="space-y-1 text-xs text-muted-foreground">
                              {merged.map((n, i) => (
                                <li key={`n-${i}`}>{n}</li>
                              ))}
                            </ul>
                          ) : (
                            <p className="text-xs text-muted-foreground">—</p>
                          )
                        })()}
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">No answer object returned for this query.</p>
                  )}

                  <DeveloperJsonPanel data={queryResult} />
                </div>
              </ModuleCard>
            ) : null}
          </TabsContent>

          <TabsContent value="risk" className="min-w-0 max-w-full space-y-6">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-cyan)" }}
              >
                Dossier · Risk Assessment
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Risk hot-spots & mitigation status</h2>
              <p className="text-sm text-muted-foreground">
                Per-requirement risk hints and overall dossier risk level — feeds the High-risk dossier KPI on the landing page.
              </p>
            </div>
            <ModuleCard
              accent="cyan"
              eyebrow="Dossier · Risk Assessment"
              title="Risk Assessment"
              description="Source-supported risk signals for this dossier — highlights gaps and contradictions for internal readiness review. Output requires qualified regulatory judgment and is not a substitute for it."
              badge={
                <Button type="button" variant="outline" size="sm" disabled={riskRefreshBusy} onClick={() => void createRiskAssessment()}>
                  {riskRefreshBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Run risk assessment
                </Button>
              }
            >
              <div className="space-y-4">
                <AlertCard
                  variant="info"
                  title="Draft input — review required"
                  description={
                    <>
                      Risk views highlight gaps and contradictions for internal readiness; treat as draft input that{" "}
                      <span className="font-medium text-foreground">requires review</span> before decisions.
                    </>
                  }
                />
                {riskActionErr ? (
                  <AlertCard variant="error" title="Risk action failed" description={riskActionErr} />
                ) : null}
                {!riskAssessment && riskMissing ? (
                  <p className="text-sm text-muted-foreground">No saved risk assessment yet.</p>
                ) : !riskAssessment ? (
                  <p className="text-sm text-muted-foreground">Risk assessment unavailable.</p>
                ) : (
                  <>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm text-muted-foreground">overall risk</span>
                      <Badge variant="outline" className="capitalize">
                        {readRecordString(riskAssessment, "overall_risk") ?? "—"}
                      </Badge>
                      <Badge variant="secondary" className="text-xs">
                        human_review_required: {String(riskAssessment.human_review_required ?? "—")}
                      </Badge>
                    </div>

                    <div>
                      <p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">risk factors</p>
                      {dictListField(riskAssessment, "risk_factors_json").length ? (
                        <ul className="space-y-2 font-mono text-[11px] text-muted-foreground">
                          {dictListField(riskAssessment, "risk_factors_json").map((row, i) => (
                            <li key={i} className="break-all rounded-md border bg-muted/30 p-2">
                              {JSON.stringify(row)}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-xs text-muted-foreground">—</p>
                      )}
                    </div>

                    <div>
                      <p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">missing evidence</p>
                      {dictListField(riskAssessment, "missing_evidence_json").length ? (
                        <ul className="space-y-2 font-mono text-[11px] text-muted-foreground">
                          {dictListField(riskAssessment, "missing_evidence_json").map((row, i) => (
                            <li key={i} className="break-all rounded-md border bg-muted/30 p-2">
                              {JSON.stringify(row)}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-xs text-muted-foreground">—</p>
                      )}
                    </div>

                    <div>
                      <p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">contradictions</p>
                      {dictListField(riskAssessment, "contradictions_json").length ? (
                        <ul className="space-y-2 font-mono text-[11px] text-muted-foreground">
                          {dictListField(riskAssessment, "contradictions_json").map((row, i) => (
                            <li key={i} className="break-all rounded-md border bg-muted/30 p-2">
                              {JSON.stringify(row)}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-xs text-muted-foreground">—</p>
                      )}
                    </div>

                    <div>
                      <p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">recommended actions</p>
                      {dictListField(riskAssessment, "recommended_actions_json").length ? (
                        <ul className="space-y-2 font-mono text-[11px] text-muted-foreground">
                          {dictListField(riskAssessment, "recommended_actions_json").map((row, i) => (
                            <li key={i} className="break-all rounded-md border bg-muted/30 p-2">
                              {JSON.stringify(row)}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-xs text-muted-foreground">—</p>
                      )}
                    </div>

                    <div>
                      <p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">citations</p>
                      {Array.isArray(riskAssessment.citation_ids_json) &&
                      (riskAssessment.citation_ids_json as unknown[]).length > 0 ? (
                        <p className="font-mono text-xs text-muted-foreground">
                          {(riskAssessment.citation_ids_json as unknown[])
                            .filter((x) => typeof x === "number" && Number.isFinite(x))
                            .join(", ")}
                        </p>
                      ) : (
                        <p className="text-xs text-muted-foreground">—</p>
                      )}
                    </div>

                    <DeveloperJsonPanel data={riskAssessment} />
                  </>
                )}
              </div>
            </ModuleCard>
          </TabsContent>

          <TabsContent value="review" className="min-w-0 max-w-full space-y-6">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-cyan)" }}
              >
                Dossier · Review
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Reviewer decision &amp; attribution</h2>
              <p className="text-sm text-muted-foreground">
                Record an internal review decision (approve / reject / escalate) with reviewer attribution. Not legal advice or external regulatory approval.
              </p>
            </div>
            <ModuleCard
              accent="cyan"
              eyebrow="Dossier · Review"
              title="Review"
              description="Record an internal review decision on this dossier — approve, reject, or escalate — with reviewer attribution. Not legal advice or external regulatory approval."
            >
              <div className="space-y-4">
                <Alert>
                  <AlertTriangle className="h-4 w-4" />
                  <AlertTitle>Internal review</AlertTitle>
                  <AlertDescription className="text-sm leading-relaxed">
                    Internal review decision. Not legal advice or external regulatory approval.
                  </AlertDescription>
                </Alert>
                {reviewSaveErr ? (
                  <Alert variant="destructive">
                    <AlertDescription className="text-sm">{reviewSaveErr}</AlertDescription>
                  </Alert>
                ) : null}

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="reg-review-reviewer" className="text-sm">
                      reviewer_name
                    </Label>
                    <Input
                      id="reg-review-reviewer"
                      value={reviewReviewerName}
                      onChange={(e) => setReviewReviewerName(e.target.value)}
                      placeholder="Reviewer name"
                      autoComplete="name"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="reg-review-decision" className="text-sm">
                      decision
                    </Label>
                    <Select value={reviewDecision} onValueChange={setReviewDecision}>
                      <SelectTrigger id="reg-review-decision" className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {REVIEW_DECISIONS.map((d) => (
                          <SelectItem key={d} value={d}>
                            {d.replace(/_/g, " ")}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="reg-review-rationale" className="text-sm">
                    rationale <span className="text-destructive">*</span>
                  </Label>
                  <Textarea
                    id="reg-review-rationale"
                    value={reviewRationale}
                    onChange={(e) => setReviewRationale(e.target.value)}
                    rows={4}
                    placeholder="Required rationale for this regulatory review decision."
                  />
                </div>

                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={reviewSaveBusy}
                  onClick={() => void saveRegulatoryReview()}
                >
                  {reviewSaveBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Save regulatory review
                </Button>

                {latestReview ? (
                  <div className="rounded-md border border-border bg-muted/30 p-4 space-y-3">
                    <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Latest review (from server)</p>
                    <div>
                      <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">decision</p>
                      <Badge variant={reviewDecisionBadgeVariant(readRecordString(latestReview, "decision"))}>
                        {readRecordString(latestReview, "decision") ?? "—"}
                      </Badge>
                    </div>
                    <div>
                      <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">status</p>
                      <Badge variant="outline">{readRecordString(dossier ?? {}, "status") ?? "—"}</Badge>
                    </div>
                    <div>
                      <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">reviewer_name</p>
                      <p className="text-sm">{readRecordString(latestReview, "reviewer_name") ?? "—"}</p>
                    </div>
                    <div>
                      <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">rationale</p>
                      <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                        {readRecordString(latestReview, "rationale") ?? "—"}
                      </p>
                    </div>
                    <div>
                      <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">created_at</p>
                      <p className="text-sm text-muted-foreground">
                        {formatWhen(readRecordString(latestReview, "created_at"))}
                      </p>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No review decisions loaded yet.</p>
                )}

                {reviews.length > 0 ? (
                  <>
                    <Separator />
                    <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">All review decisions</p>
                    <div className="table-scroll">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>id</TableHead>
                            <TableHead>decision</TableHead>
                            <TableHead>reviewer_name</TableHead>
                            <TableHead>created_at</TableHead>
                            <TableHead>rationale (truncated)</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {reviews.map((r) => (
                            <TableRow key={readRecordNumber(r, "id")}>
                              <TableCell className="font-mono text-xs">{readRecordNumber(r, "id") ?? "—"}</TableCell>
                              <TableCell className="capitalize">{readRecordString(r, "decision") ?? "—"}</TableCell>
                              <TableCell>{readRecordString(r, "reviewer_name") ?? "—"}</TableCell>
                              <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                                {formatWhen(readRecordString(r, "created_at"))}
                              </TableCell>
                              <TableCell className="max-w-[360px] text-xs text-muted-foreground">
                                {truncateText(readRecordString(r, "rationale") ?? "", 240)}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </>
                ) : null}
              </div>
            </ModuleCard>
          </TabsContent>

          <TabsContent value="readiness" className="min-w-0 max-w-full space-y-6">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-cyan)" }}
              >
                Dossier · Readiness Report
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Submission readiness snapshot</h2>
              <p className="text-sm text-muted-foreground">
                Pre-submission checklist with per-section coverage and reviewer signoff state — share with the regulatory affairs team.
              </p>
            </div>
            <ModuleCard
              accent="cyan"
              eyebrow="Dossier · Readiness"
              title="Readiness Report"
              description={
                <>
                  Generate a readiness report summarizing evidence coverage and identified gaps. Readiness summaries{" "}
                  <span className="font-medium text-foreground">require review</span> and are not compliance certificates.
                </>
              }
              badge={
                <Button type="button" variant="outline" size="sm" disabled={readinessBusy} onClick={() => void generateReadinessReport()}>
                  {readinessBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Generate readiness report
                </Button>
              }
            >
              <div className="space-y-4">
                <AlertCard
                  variant="info"
                  title="Source-supported only after citations attached"
                  description={
                    <>
                      Use <span className="font-medium text-foreground">readiness summary</span> fields together with
                      source-backed citations; where citations are missing, treat the package as{" "}
                      <span className="font-medium text-foreground">source-supported</span> only after you attach them.
                    </>
                  }
                />
                {readinessErr ? (
                  <Alert variant="destructive">
                    <AlertDescription className="text-sm">{readinessErr}</AlertDescription>
                  </Alert>
                ) : null}
                {!readinessReport ? (
                  <p className="text-sm text-muted-foreground">No readiness report loaded in this session.</p>
                ) : (
                  <>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">dossier status</p>
                        <p className="mt-1 text-sm">
                          {isRecord(readinessReport.review_status_json)
                            ? readRecordString(readinessReport.review_status_json as Record<string, unknown>, "dossier_status") ?? "—"
                            : "—"}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Readiness record <span className="font-mono">status</span>:{" "}
                          <Badge variant="outline" className="align-middle text-xs">
                            {readRecordString(readinessReport, "status") ?? "—"}
                          </Badge>
                        </p>
                      </div>
                      <div>
                        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">report hash (if returned)</p>
                        <p className="mt-1 break-all font-mono text-xs">
                          {readReportHashFromMetadata(readinessReport) ?? "—"}
                        </p>
                      </div>
                    </div>

                    <div>
                      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">readiness summary</p>
                      {isRecord(readinessReport.summary_json) ? (
                        <dl className="mt-2 grid gap-2 rounded-md border bg-muted/30 p-3 text-xs sm:grid-cols-2">
                          {Object.entries(readinessReport.summary_json as Record<string, unknown>).map(([k, v]) => (
                            <div key={k}>
                              <dt className="font-mono text-muted-foreground">{k}</dt>
                              <dd className="mt-0.5 break-words">
                                {typeof v === "object" ? JSON.stringify(v) : String(v)}
                              </dd>
                            </div>
                          ))}
                        </dl>
                      ) : (
                        <p className="text-xs text-muted-foreground">—</p>
                      )}
                    </div>

                    {(() => {
                      const reqRows = dictListField(readinessReport, "requirements_json")
                      const sat = countRequirementStatus(reqRows, "satisfied")
                      const blocked = countRequirementStatus(reqRows, "blocked")
                      return (
                        <div className="grid gap-3 sm:grid-cols-2">
                          <div className="rounded-md border bg-card p-3">
                            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">requirements satisfied</p>
                            <p className="mt-1 text-2xl font-semibold tabular-nums">{sat}</p>
                          </div>
                          <div className="rounded-md border bg-card p-3">
                            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">requirements blocked</p>
                            <p className="mt-1 text-2xl font-semibold tabular-nums">{blocked}</p>
                          </div>
                        </div>
                      )
                    })()}

                    <div>
                      <p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">evidence gap</p>
                      {dictListField(readinessReport, "gaps_json").length ? (
                        <ul className="space-y-2 font-mono text-[11px] text-muted-foreground">
                          {dictListField(readinessReport, "gaps_json").map((row, i) => (
                            <li key={i} className="break-all rounded-md border bg-muted/30 p-2">
                              {JSON.stringify(row)}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-xs text-muted-foreground">—</p>
                      )}
                    </div>

                    {/* evidence_json from the readiness report — the satisfied
                        requirement→evidence links the report rolled up. Previously
                        loaded but only counted for analytics (evidence_link_count);
                        now rendered so reviewers see what evidence backs the report. */}
                    <div>
                      <p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
                        evidence links · {dictListField(readinessReport, "evidence_json").length}
                      </p>
                      {dictListField(readinessReport, "evidence_json").length ? (
                        <ul className="space-y-2 font-mono text-[11px] text-muted-foreground">
                          {dictListField(readinessReport, "evidence_json").map((row, i) => (
                            <li key={i} className="break-all rounded-md border bg-muted/30 p-2">
                              {JSON.stringify(row)}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-xs text-muted-foreground">—</p>
                      )}
                    </div>

                    <div>
                      <p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">citations</p>
                      {Array.isArray(readinessReport.citation_ids_json) &&
                      (readinessReport.citation_ids_json as unknown[]).length > 0 ? (
                        <p className="font-mono text-xs text-muted-foreground">
                          {(readinessReport.citation_ids_json as unknown[])
                            .filter((x) => typeof x === "number" && Number.isFinite(x))
                            .join(", ")}
                        </p>
                      ) : (
                        <p className="text-xs text-muted-foreground">—</p>
                      )}
                    </div>

                    <div>
                      <p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">risk summary</p>
                      {isRecord(readinessReport.risks_json) ? (
                        <pre className="max-h-64 overflow-auto rounded-md border bg-muted/30 p-3 text-[11px] leading-relaxed">
                          {JSON.stringify(readinessReport.risks_json, null, 2)}
                        </pre>
                      ) : (
                        <p className="text-xs text-muted-foreground">—</p>
                      )}
                    </div>

                    <div>
                      <p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">review status</p>
                      {isRecord(readinessReport.review_status_json) ? (
                        <dl className="grid gap-2 rounded-md border bg-muted/30 p-3 text-xs sm:grid-cols-2">
                          {Object.entries(readinessReport.review_status_json as Record<string, unknown>).map(([k, v]) => (
                            <div key={k}>
                              <dt className="font-mono text-muted-foreground">{k}</dt>
                              <dd className="mt-0.5 break-words">
                                {typeof v === "object" && v !== null ? JSON.stringify(v) : String(v)}
                              </dd>
                            </div>
                          ))}
                        </dl>
                      ) : (
                        <p className="text-xs text-muted-foreground">—</p>
                      )}
                    </div>

                    {(() => {
                      const links = downloadLinksFromMetadata(readinessReport)
                      return (
                        <div>
                          <p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">downloads</p>
                          {links.length ? (
                            <div className="flex flex-wrap gap-2">
                              {links.map((l) => (
                                <Button key={l.key} variant="outline" size="sm" asChild>
                                  <a href={l.url} target="_blank" rel="noreferrer">
                                    Download ({l.key})
                                  </a>
                                </Button>
                              ))}
                            </div>
                          ) : (
                            <p className="text-xs text-muted-foreground">No download URLs returned in metadata_json.</p>
                          )}
                        </div>
                      )
                    })()}

                    <div>
                      <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">warnings</p>
                      {(() => {
                        const merged = [
                          ...readStringArray(readinessReport, "warnings"),
                          ...readStringArray(readinessReport, "warnings_json"),
                        ]
                        return merged.length ? (
                          <ul className="list-inside list-disc text-xs text-muted-foreground">
                            {merged.map((w, i) => (
                              <li key={i}>{w}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-xs text-muted-foreground">—</p>
                        )
                      })()}
                    </div>

                    <DeveloperJsonPanel data={readinessReport} />
                  </>
                )}
              </div>
            </ModuleCard>
            <CtdModule3BundleCard dossierId={dossierId} />
          </TabsContent>

          <TabsContent value="submission-package" className="min-w-0 max-w-full space-y-6">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-cyan)" }}
              >
                Dossier · Submission Package
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Assemble draft submission artefacts</h2>
              <p className="text-sm text-muted-foreground">
                Source-backed artefacts staged for review. Package status is backend-driven — treat as ready only when the status field explicitly says so.
              </p>
            </div>
            <ModuleCard
              accent="cyan"
              eyebrow="Dossier · Submission Package"
              title="Submission Package Builder"
              description={
                <>
                  Assemble a draft regulatory submission package with source-backed artefacts. Package status is backend-driven — treat as{" "}
                  <span className="font-medium text-foreground">ready for review</span> only when the status field explicitly indicates it.
                </>
              }
            >
                <AlertCard
                  variant="info"
                  title="Draft package"
                  description={
                    <>
                      Build a <span className="font-medium text-foreground">draft package</span> with source-backed artifacts.
                      Package status is backend-driven; treat outputs as <span className="font-medium text-foreground">ready for review</span> or{" "}
                      <span className="font-medium text-foreground">exported package</span> only when status fields explicitly say so.
                    </>
                  }
                />

                {submissionPackageErr ? (
                  <AlertCard variant="error" title="Submission package failed" description={submissionPackageErr} />
                ) : null}

                <div className="grid gap-3 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label>package type</Label>
                    <Select value={submissionPackageType} onValueChange={setSubmissionPackageType}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {SUBMISSION_PACKAGE_TYPES.map((t) => (
                          <SelectItem key={t} value={t}>
                            {t}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="sp-package-id">package id lookup</Label>
                    <div className="flex flex-wrap items-center gap-2">
                      <Input
                        id="sp-package-id"
                        value={submissionPackageIdInput}
                        onChange={(e) => setSubmissionPackageIdInput(e.target.value)}
                        placeholder="package_id"
                        className="max-w-[220px]"
                      />
                      <Button type="button" variant="outline" size="sm" disabled={submissionPackageLookupBusy} onClick={() => void loadSubmissionPackageById()}>
                        {submissionPackageLookupBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                        Load package
                      </Button>
                    </div>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="flex items-center justify-between rounded-md border p-3">
                    <Label htmlFor="sp-include-sr">include SpectraCheck report</Label>
                    <Switch id="sp-include-sr" checked={spIncludeSpectraCheckReport} onCheckedChange={setSpIncludeSpectraCheckReport} />
                  </div>
                  <div className="flex items-center justify-between rounded-md border p-3">
                    <Label htmlFor="sp-include-ir">include impurity register</Label>
                    <Switch id="sp-include-ir" checked={spIncludeImpurityRegister} onCheckedChange={setSpIncludeImpurityRegister} />
                  </div>
                  <div className="flex items-center justify-between rounded-md border p-3">
                    <Label htmlFor="sp-include-rs">include residual solvent assessment</Label>
                    <Switch id="sp-include-rs" checked={spIncludeResidualSolventAssessment} onCheckedChange={setSpIncludeResidualSolventAssessment} />
                  </div>
                  <div className="flex items-center justify-between rounded-md border p-3">
                    <Label htmlFor="sp-include-na">include nitrosamine watch</Label>
                    <Switch id="sp-include-na" checked={spIncludeNitrosamineWatch} onCheckedChange={setSpIncludeNitrosamineWatch} />
                  </div>
                  <div className="flex items-center justify-between rounded-md border p-3">
                    <Label htmlFor="sp-include-qnmr">include qNMR/method validation</Label>
                    <Switch id="sp-include-qnmr" checked={spIncludeQnmrValidation} onCheckedChange={setSpIncludeQnmrValidation} />
                  </div>
                  <div className="flex items-center justify-between rounded-md border p-3">
                    <Label htmlFor="sp-include-ai">include AI governance record</Label>
                    <Switch id="sp-include-ai" checked={spIncludeAiGovernanceRecord} onCheckedChange={setSpIncludeAiGovernanceRecord} />
                  </div>
                  <div className="flex items-center justify-between rounded-md border p-3">
                    <Label htmlFor="sp-include-citations">include source citations</Label>
                    <Switch id="sp-include-citations" checked={spIncludeSourceCitations} onCheckedChange={setSpIncludeSourceCitations} />
                  </div>
                  <div className="flex items-center justify-between rounded-md border p-3">
                    <Label htmlFor="sp-include-hashes">include provenance hashes</Label>
                    <Switch id="sp-include-hashes" checked={spIncludeProvenanceHashes} onCheckedChange={setSpIncludeProvenanceHashes} />
                  </div>
                  <div className="flex items-center justify-between rounded-md border p-3 sm:col-span-2">
                    <Label htmlFor="sp-include-review-decisions">include review decisions</Label>
                    <Switch id="sp-include-review-decisions" checked={spIncludeReviewDecisions} onCheckedChange={setSpIncludeReviewDecisions} />
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button type="button" disabled={submissionPackageBusy} onClick={() => void createSubmissionPackage()}>
                    {submissionPackageBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                    Create package
                  </Button>
                  <Button type="button" variant="outline" disabled={submissionPackageLookupBusy} onClick={() => void refreshSubmissionPackageByDossier()}>
                    Refresh package
                  </Button>
                </div>

                {(() => {
                  const pkg = submissionPackageById ?? submissionPackageByDossier
                  if (!pkg) {
                    return <p className="text-sm text-muted-foreground">No package loaded yet.</p>
                  }
                  const packageSha =
                    readRecordString(pkg, "sha256") ??
                    readRecordString(pkg, "package_sha256") ??
                    readRecordString(pkg, "hash")
                  const packageStatus = readRecordString(pkg, "status") ?? "—"
                  const packageManifest = pkg.manifest_json && isRecord(pkg.manifest_json) ? pkg.manifest_json : pkg
                  const fileIds = readNumericListFromKeys(pkg, ["included_file_ids", "file_ids", "included_files"])
                  const artifactIds = readNumericListFromKeys(pkg, [
                    "included_artifact_ids",
                    "artifact_ids",
                    "included_artifacts",
                  ])
                  const warnings = readWarningLines(pkg)
                  const downloadLinks = downloadLinksFromMetadata(pkg)
                  const directUrl =
                    readRecordString(pkg, "download_url") ??
                    readRecordString(pkg, "package_url") ??
                    readRecordString(pkg, "open_url")
                  return (
                    <div className="space-y-4 rounded-md border p-3">
                      <div className="grid gap-3 sm:grid-cols-2">
                        <div>
                          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">status</p>
                          <p className="mt-1 text-sm">{packageStatus}</p>
                        </div>
                        <div>
                          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">package SHA-256</p>
                          <p className="mt-1 break-all font-mono text-xs">{packageSha ?? "—"}</p>
                        </div>
                      </div>

                      <div>
                        <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">package manifest</p>
                        <pre className="max-h-72 overflow-auto rounded-md border bg-muted/30 p-3 text-[11px] leading-relaxed">
                          {JSON.stringify(packageManifest, null, 2)}
                        </pre>
                      </div>

                      <div className="grid gap-3 sm:grid-cols-2">
                        <div>
                          <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">included file IDs</p>
                          <p className="font-mono text-xs text-muted-foreground">
                            {fileIds.length ? fileIds.join(", ") : "—"}
                          </p>
                        </div>
                        <div>
                          <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">included artifact IDs</p>
                          <p className="font-mono text-xs text-muted-foreground">
                            {artifactIds.length ? artifactIds.join(", ") : "—"}
                          </p>
                        </div>
                      </div>

                      <div>
                        <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">warnings</p>
                        {warnings.length ? (
                          <ul className="list-inside list-disc text-xs text-muted-foreground">
                            {warnings.map((w, i) => (
                              <li key={i}>{w}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-xs text-muted-foreground">—</p>
                        )}
                      </div>

                      <div>
                        <p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">download/open package</p>
                        <div className="flex flex-wrap gap-2">
                          {directUrl ? (
                            <Button variant="outline" size="sm" asChild>
                              <a href={directUrl} target="_blank" rel="noreferrer">
                                Open package
                              </a>
                            </Button>
                          ) : null}
                          {downloadLinks.map((l) => (
                            <Button key={l.key} variant="outline" size="sm" asChild>
                              <a href={l.url} target="_blank" rel="noreferrer">
                                Download ({l.key})
                              </a>
                            </Button>
                          ))}
                          {!directUrl && downloadLinks.length === 0 ? (
                            <p className="text-xs text-muted-foreground">No package URL returned.</p>
                          ) : null}
                        </div>
                      </div>

                      <details className="rounded-md border p-2">
                        <summary className="cursor-pointer text-xs font-medium">Developer JSON</summary>
                        <pre className="mt-2 max-h-72 overflow-auto text-[11px] leading-relaxed">
                          {JSON.stringify(pkg, null, 2)}
                        </pre>
                      </details>
                    </div>
                  )
                })()}
            </ModuleCard>
          </TabsContent>

          <TabsContent value="json" className="min-w-0 max-w-full space-y-6">
            <div className="space-y-1">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-cyan)" }}
              >
                Dossier · Developer JSON
              </p>
              <h2 className="font-mono text-xl font-bold tracking-tight">Raw payloads for debugging</h2>
              <p className="text-sm text-muted-foreground">
                Aggregated dossier payloads in this browser session — use to inspect backend response shape, warnings, and audit fields.
              </p>
            </div>
            <ModuleCard
              accent="cyan"
              eyebrow="Dossier · Developer JSON"
              title="Developer JSON"
              description="Aggregated payloads from this workspace (no automatic refresh on tab change)."
            >
              <DeveloperJsonPanel data={devPayload} />
            </ModuleCard>
          </TabsContent>
        </Tabs>
      ) : !loadErr ? (
        <p className="text-sm text-muted-foreground">Dossier not found.</p>
      ) : null}
    </div>
  )
}
