// Validation lifecycle (GAMP 5 / CSA, Security Prompt 13) — release validation package.
//
// Decision-support / evidence-assembly framing only: the package SUPPORTS a
// customer's CSV effort, it does not perform or replace it. Surface `notice`
// verbatim; present IQ/PQ as customer-supplied (never "passed"). Read defensively
// — the package's nested objects are free-form on the wire.

import { apiFetch } from "@/lib/api/client"

function isRecord(v: unknown): v is Record<string, unknown> {
  return v != null && typeof v === "object" && !Array.isArray(v)
}
function num(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v
  if (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v))) return Number(v)
  return null
}
function str(v: unknown): string {
  return typeof v === "string" ? v : ""
}

export type QualBlock = { status: string; note: string; passed: number | null; failed: number | null; skipped: number | null; coveragePercent: number | null }

export type ValidationPackage = {
  packageMetadata: Record<string, unknown>
  traceability: { status: string; note: string; coverage: number | null; gaps: unknown[]; raw: Record<string, unknown> }
  iq: QualBlock
  oq: QualBlock
  pq: QualBlock
  riskSummary: Record<string, number>
  changeControl: {
    validated: boolean
    changeControlled: boolean
    openDeviationCount: number
    projectStatus: string | null
    releaseStatus: string | null
  }
  signatures: Record<string, unknown>[]
  notice: string
}

function readQual(v: unknown): QualBlock {
  const r = isRecord(v) ? v : {}
  const ev = isRecord(r.evidence) ? r.evidence : {}
  return {
    status: str(r.status) || "unknown",
    note: str(r.note),
    passed: num(r.passed) ?? num(ev.passed),
    failed: num(r.failed) ?? num(ev.failed),
    skipped: num(r.skipped) ?? num(ev.skipped),
    coveragePercent: num(r.coverage_pct) ?? num(ev.coverage_percent) ?? num(r.coverage_percent),
  }
}

function readRiskSummary(v: unknown): Record<string, number> {
  if (!isRecord(v)) return {}
  const out: Record<string, number> = {}
  for (const [k, raw] of Object.entries(v)) {
    const n = num(raw)
    if (n != null) out[k] = n
  }
  return out
}

export function parseValidationPackage(raw: unknown): ValidationPackage | null {
  if (!isRecord(raw)) return null
  const trace = isRecord(raw.requirement_risk_test_traceability) ? raw.requirement_risk_test_traceability : {}
  const iqoqpq = isRecord(raw.iq_oq_pq_evidence) ? raw.iq_oq_pq_evidence : {}
  const cc = isRecord(raw.change_control_state) ? raw.change_control_state : {}
  return {
    packageMetadata: isRecord(raw.package_metadata) ? raw.package_metadata : {},
    traceability: {
      status: str(trace.status) || "unknown",
      note: str(trace.note),
      coverage: num(trace.coverage_percent) ?? num(trace.coverage),
      gaps: Array.isArray(trace.gaps) ? trace.gaps : [],
      raw: trace,
    },
    iq: readQual(iqoqpq.iq),
    oq: readQual(iqoqpq.oq),
    pq: readQual(iqoqpq.pq),
    riskSummary: readRiskSummary(raw.risk_summary),
    changeControl: {
      validated: cc.validated === true,
      changeControlled: cc.change_controlled === true,
      openDeviationCount: num(cc.open_deviation_count) ?? 0,
      projectStatus: str(cc.project_status) || null,
      releaseStatus: str(cc.release_status) || null,
    },
    signatures: Array.isArray(raw.signatures) ? raw.signatures.filter(isRecord) : [],
    notice: str(raw.notice),
  }
}

// ── API ──────────────────────────────────────────────────────────────────────
export async function getValidationPackage(releaseId: number | string): Promise<ValidationPackage | null> {
  return parseValidationPackage(
    await apiFetch<unknown>(`/system-releases/${encodeURIComponent(String(releaseId))}/validation-package`, {
      method: "GET",
    }),
  )
}

export type ReleaseEvidenceIngest = {
  test_summary_json?: Record<string, unknown>
  risk_summary_json?: Record<string, unknown>
  source?: "ci" | "manual"
  metadata_json?: Record<string, unknown>
}

export async function ingestReleaseEvidence(releaseId: number | string, body: ReleaseEvidenceIngest): Promise<unknown> {
  return apiFetch<unknown>(`/system-releases/${encodeURIComponent(String(releaseId))}/evidence`, {
    method: "POST",
    body,
  })
}

// ── UI helpers ────────────────────────────────────────────────────────────────
export type QualTone = "success" | "error" | "warning" | "customer" | "neutral"

/** Badge tone + label for a qualification / traceability status. IQ/PQ
 *  customer_supplied must read as a customer responsibility, never "passed". */
export function qualStatusBadge(status: string): { tone: QualTone; label: string } {
  switch (status) {
    case "pass":
      return { tone: "success", label: "Pass" }
    case "fail":
      return { tone: "error", label: "Fail" }
    case "customer_supplied":
      return { tone: "customer", label: "Customer responsibility" }
    case "complete":
      return { tone: "success", label: "Complete" }
    case "gaps_identified":
      return { tone: "warning", label: "Gaps identified" }
    case "no_traceability_generated":
      return { tone: "neutral", label: "Not generated" }
    default:
      return { tone: "neutral", label: status || "unknown" }
  }
}
