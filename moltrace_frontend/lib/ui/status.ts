// Shared status/label humanization — turn the schema's vocabulary into the
// user's. statusTone() classifies any status token; statusLabel() / humanizeField()
// render readable text. Used by <StatusBadge> and to relabel snake_case fields.

export type StatusTone = "success" | "warning" | "danger" | "info" | "pending" | "neutral"

// Acronyms / brand words to keep cased correctly when humanizing.
const CASED: Record<string, string> = {
  qa: "QA", ai: "AI", ml: "ML", ood: "OOD", capa: "CAPA", sop: "SOP", urs: "URS",
  iq: "IQ", oq: "OQ", pq: "PQ", csa: "CSA", gamp: "GAMP", gmp: "GMP", rag: "RAG",
  ctd: "CTD", ich: "ICH", fda: "FDA", ema: "EMA", ms: "MS", nmr: "NMR", bo: "BO",
  id: "ID", json: "JSON", csv: "CSV", api: "API", roi: "ROI", url: "URL", smiles: "SMILES",
  spectracheck: "SpectraCheck", regentry: "Regentry", repho: "Repho", cas: "CAS",
}

const EXACT_TONE: Record<string, StatusTone> = {
  approved: "success", approved_internal: "success", complete: "success", completed: "success",
  succeeded: "success", success: "success", passed: "success", pass: "success", released: "success",
  active: "success", clear: "success", verified: "success", mitigated: "success", accepted: "success",
  executed: "success", ready: "success", enabled: "success", locked: "success",
  rejected: "danger", failed: "danger", fail: "danger", blocked: "danger", error: "danger",
  critical: "danger", revoked: "danger", reuse_detected: "danger", expired: "danger", denied: "danger",
  pending: "warning", review_pending: "warning", requires_review: "warning", requires_expert_review: "warning",
  in_review: "warning", ready_for_qa_review: "warning", ready_for_review: "warning", needs_review: "warning",
  gaps_identified: "warning", warning: "warning", high: "warning", open: "warning",
  change_controlled: "warning", insufficient_data: "warning", step_up_required: "warning",
  running: "info", queued: "info", in_progress: "info", processing: "info", proposed: "info",
  scheduled: "info", draft: "neutral", not_started: "neutral",
  archived: "neutral", retired: "neutral", inactive: "neutral", disabled: "neutral",
  not_required: "neutral", unknown: "neutral", superseded: "neutral", customer_supplied: "neutral",
  none: "neutral", low: "neutral", medium: "warning",
}

function norm(s: string): string {
  return s.trim().toLowerCase().replace(/[\s-]+/g, "_")
}

/** Classify any status token into a UI tone (keyword fallback for unknowns). */
export function statusTone(status: unknown): StatusTone {
  const s = typeof status === "string" ? norm(status) : ""
  if (!s) return "neutral"
  if (EXACT_TONE[s]) return EXACT_TONE[s]
  if (/(reject|fail|block|error|critical|revok|deni|expired|invalid)/.test(s)) return "danger"
  if (/(approv|pass|success|complete|verified|released|accept|mitigat|clear|active)/.test(s)) return "success"
  if (/(pending|review|warn|gap|hold|caution|attention)/.test(s)) return "warning"
  if (/(progress|running|queued|processing|propos|schedul|draft)/.test(s)) return "info"
  return "neutral"
}

function titleCaseWords(s: string, lowerConnectors: boolean): string {
  const words = norm(s).split("_").filter(Boolean)
  return words
    .map((w, i) => {
      if (CASED[w]) return CASED[w]
      if (lowerConnectors && i > 0 && (w === "for" || w === "of" || w === "and" || w === "to" || w === "by")) return w
      return i === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w
    })
    .join(" ")
}

/** Human label for a status enum: "ready_for_qa_review" → "Ready for QA review". */
export function statusLabel(status: unknown): string {
  const s = typeof status === "string" ? status.trim() : ""
  if (!s) return "—"
  return titleCaseWords(s, true)
}

/** Human label for a snake_case field name: "bo_run_id" → "BO run". Strips a
 *  trailing _id / _json so "linked_spectracheck_session_id" → "Linked SpectraCheck session". */
export function humanizeField(field: string): string {
  const stripped = field.trim().replace(/_(id|ids|json)$/i, "")
  return titleCaseWords(stripped || field, false)
}
