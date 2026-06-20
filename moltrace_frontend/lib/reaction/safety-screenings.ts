// Repho R6 — structural safety screening + review gate.
//
// DECISION-SUPPORT ONLY. This is a deterministic RDKit-SMARTS energetic/reactive-
// group screen, NOT a safety determination. Always surface the backend `disclaimer`
// verbatim and never present a "clear" gate as a safety clearance. Distinct from the
// manual safety-constraint profile. 5 owner-scoped routes (non-owner ⇒ 404).
// result_json is a free-form engine object — read defensively.

import { apiFetch } from "@/lib/api/client"

export type RiskLevel = "low" | "medium" | "high" | "critical" | "unknown"
export type ReviewStatus = "not_required" | "pending" | "approved" | "rejected"
export type GateStatus = "clear" | "review_pending" | "blocked"

export type FlaggedGroup = {
  key: string
  label: string
  severity: RiskLevel
  count: number | null
  mitigation: string | null
}

export type SafetySpecies = {
  role: string
  smiles: string
  parsed: boolean
  overallRisk: RiskLevel
  flaggedGroups: FlaggedGroup[]
}

export type SafetyScreening = {
  id: number
  reactionProjectId: number | null
  label: string | null
  overallRisk: RiskLevel
  requiresExpertReview: boolean
  reviewStatus: ReviewStatus
  reviewNote: string | null
  reviewedByUserId: number | null
  reviewedAt: string | null
  createdAt: string | null
  disclaimer: string
  species: SafetySpecies[]
  energeticGroupsFound: string[]
  inputJson: Record<string, unknown> | null
}

export type SafetyGate = {
  reactionProjectId: number | null
  status: GateStatus
  screeningsTotal: number
  blockingScreeningIds: number[]
  summary: string
}

export type SafetyScreenRequest = {
  reactant_smiles: string[]
  reagent_smiles?: string[]
  product_smiles?: string | null
  label?: string | null
}

export type SafetyReviewRequest = { decision: "approved" | "rejected"; note?: string | null }

function isRecord(v: unknown): v is Record<string, unknown> {
  return v != null && typeof v === "object" && !Array.isArray(v)
}
function readNum(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v
  return null
}
function readStr(v: unknown): string | null {
  return typeof v === "string" && v.trim() !== "" ? v : null
}
function readStrArray(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []
}
const RISK_SET: RiskLevel[] = ["low", "medium", "high", "critical", "unknown"]
function readRisk(v: unknown): RiskLevel {
  return typeof v === "string" && (RISK_SET as string[]).includes(v) ? (v as RiskLevel) : "unknown"
}
const REVIEW_SET: ReviewStatus[] = ["not_required", "pending", "approved", "rejected"]
function readReviewStatus(v: unknown): ReviewStatus {
  return typeof v === "string" && (REVIEW_SET as string[]).includes(v) ? (v as ReviewStatus) : "not_required"
}
const GATE_SET: GateStatus[] = ["clear", "review_pending", "blocked"]
function readGateStatus(v: unknown): GateStatus {
  return typeof v === "string" && (GATE_SET as string[]).includes(v) ? (v as GateStatus) : "clear"
}

function parseFlaggedGroup(v: unknown): FlaggedGroup | null {
  if (!isRecord(v)) return null
  const key = readStr(v.key)
  const label = readStr(v.label) ?? key
  if (!label) return null
  return {
    key: key ?? label,
    label,
    severity: readRisk(v.severity),
    count: readNum(v.count),
    mitigation: readStr(v.mitigation),
  }
}

function parseSpecies(v: unknown): SafetySpecies | null {
  if (!isRecord(v)) return null
  return {
    role: readStr(v.role) ?? "species",
    smiles: readStr(v.smiles) ?? "",
    parsed: v.parsed !== false,
    overallRisk: readRisk(v.overall_risk),
    flaggedGroups: Array.isArray(v.flagged_groups)
      ? v.flagged_groups.map(parseFlaggedGroup).filter((g): g is FlaggedGroup => g != null)
      : [],
  }
}

export function parseScreening(raw: unknown): SafetyScreening | null {
  if (!isRecord(raw)) return null
  const id = readNum(raw.id)
  if (id == null) return null
  const rj = isRecord(raw.result_json) ? raw.result_json : {}
  return {
    id,
    reactionProjectId: readNum(raw.reaction_project_id),
    label: readStr(raw.label),
    overallRisk: readRisk(raw.overall_risk),
    requiresExpertReview: raw.requires_expert_review === true,
    reviewStatus: readReviewStatus(raw.review_status),
    reviewNote: readStr(raw.review_note),
    reviewedByUserId: readNum(raw.reviewed_by_user_id),
    reviewedAt: readStr(raw.reviewed_at),
    createdAt: readStr(raw.created_at),
    disclaimer: typeof raw.disclaimer === "string" ? raw.disclaimer : "",
    species: Array.isArray(rj.species)
      ? rj.species.map(parseSpecies).filter((s): s is SafetySpecies => s != null)
      : [],
    energeticGroupsFound: readStrArray(rj.energetic_groups_found),
    inputJson: isRecord(raw.input_json) ? raw.input_json : null,
  }
}

export function parseGate(raw: unknown): SafetyGate {
  const r = isRecord(raw) ? raw : {}
  return {
    reactionProjectId: readNum(r.reaction_project_id),
    status: readGateStatus(r.status),
    screeningsTotal: readNum(r.screenings_total) ?? 0,
    blockingScreeningIds: Array.isArray(r.blocking_screening_ids)
      ? r.blocking_screening_ids.map(readNum).filter((n): n is number => n != null)
      : [],
    summary: typeof r.summary === "string" ? r.summary : "",
  }
}

// ── API ──────────────────────────────────────────────────────────────────────
const base = (projectId: number) => `/reaction-projects/${projectId}/safety-screenings`

export async function createScreening(projectId: number, body: SafetyScreenRequest): Promise<SafetyScreening | null> {
  return parseScreening(await apiFetch<unknown>(base(projectId), { method: "POST", body }))
}
export async function listScreenings(projectId: number): Promise<SafetyScreening[]> {
  const raw = await apiFetch<unknown>(base(projectId), { method: "GET" })
  return (Array.isArray(raw) ? raw : []).map(parseScreening).filter((s): s is SafetyScreening => s != null)
}
export async function getScreening(projectId: number, id: number): Promise<SafetyScreening | null> {
  return parseScreening(await apiFetch<unknown>(`${base(projectId)}/${id}`, { method: "GET" }))
}
export async function reviewScreening(
  projectId: number,
  id: number,
  body: SafetyReviewRequest,
): Promise<SafetyScreening | null> {
  return parseScreening(await apiFetch<unknown>(`${base(projectId)}/${id}/review`, { method: "POST", body }))
}
export async function getSafetyGate(projectId: number): Promise<SafetyGate> {
  return parseGate(await apiFetch<unknown>(`/reaction-projects/${projectId}/safety-gate`, { method: "GET" }))
}

// ── Theme-safe styling (semantic Tailwind classes carry their own dark: variant) ─
export const RISK_BADGE_CLASS: Record<RiskLevel, string> = {
  critical: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  high: "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300",
  medium: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  low: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  unknown: "bg-muted text-muted-foreground",
}

export const REVIEW_BADGE_CLASS: Record<ReviewStatus, string> = {
  approved: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  rejected: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  pending: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  not_required: "bg-muted text-muted-foreground",
}

export const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  approved: "approved",
  rejected: "rejected",
  pending: "review pending",
  not_required: "not required",
}

export type GateTone = "clear" | "pending" | "blocked"
export const GATE_BANNER: Record<GateStatus, { tone: GateTone; title: string; className: string }> = {
  clear: {
    tone: "clear",
    title: "Safety screening — clear",
    className:
      "border-emerald-500/40 bg-emerald-500/10 text-emerald-900 dark:text-emerald-200",
  },
  review_pending: {
    tone: "pending",
    title: "Safety screening — expert review pending",
    className: "border-amber-500/50 bg-amber-500/10 text-amber-900 dark:text-amber-200",
  },
  blocked: {
    tone: "blocked",
    title: "Safety screening — blocked",
    className: "border-red-500/50 bg-red-500/10 text-red-900 dark:text-red-200",
  },
}
