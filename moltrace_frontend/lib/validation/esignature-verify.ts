// 21 CFR Part 11 e-signature hardening (Security Prompt 11) — verify + manifestation.
//
// Hardening of the EXISTING signature surface: §11.70 integrity verify and §11.50
// manifestation. Decision-support framing only — surface `compliance_notice`
// verbatim; never upgrade it to "compliant". Responses are read defensively.

import { apiFetch } from "@/lib/api/client"

export type ESignatureVerification = {
  signatureId: number | null
  bound: boolean
  valid: boolean | null
  hashMatches: boolean | null
  contentMatches: boolean | null
  recordContentHash: string | null
  recomputedContentHash: string | null
  reason: string
}

export type ESignatureManifestation = {
  printedName: string | null
  signerEmail: string | null
  signatureMeaning: string
  meaningLabel: string
  signedAtUtc: string | null
  reason: string
  targetType: string
  targetId: number | null
  recordContentHash: string | null
  signatureDigest: string | null
  bindingStatus: string
  authenticationMethod: string | null
  stepUpFactor: string | null
  stepUpAal: string | null
  attestationText: string
  complianceNotice: string
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return v != null && typeof v === "object" && !Array.isArray(v)
}
function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null
}
function str(v: unknown): string {
  return typeof v === "string" ? v : ""
}
function strOrNull(v: unknown): string | null {
  return typeof v === "string" && v !== "" ? v : null
}
function boolOrNull(v: unknown): boolean | null {
  return typeof v === "boolean" ? v : null
}

export function parseVerification(raw: unknown): ESignatureVerification | null {
  if (!isRecord(raw)) return null
  return {
    signatureId: num(raw.signature_id),
    bound: raw.bound === true,
    valid: boolOrNull(raw.valid),
    hashMatches: boolOrNull(raw.hash_matches),
    contentMatches: boolOrNull(raw.content_matches),
    recordContentHash: strOrNull(raw.record_content_hash),
    recomputedContentHash: strOrNull(raw.recomputed_content_hash),
    reason: str(raw.reason),
  }
}

export function parseManifestation(raw: unknown): ESignatureManifestation | null {
  if (!isRecord(raw)) return null
  return {
    printedName: strOrNull(raw.printed_name),
    signerEmail: strOrNull(raw.signer_email),
    signatureMeaning: str(raw.signature_meaning),
    meaningLabel: str(raw.meaning_label),
    signedAtUtc: strOrNull(raw.signed_at_utc),
    reason: str(raw.reason),
    targetType: str(raw.target_type),
    targetId: num(raw.target_id),
    recordContentHash: strOrNull(raw.record_content_hash),
    signatureDigest: strOrNull(raw.signature_digest),
    bindingStatus: str(raw.binding_status),
    authenticationMethod: strOrNull(raw.authentication_method),
    stepUpFactor: strOrNull(raw.step_up_factor),
    stepUpAal: strOrNull(raw.step_up_aal),
    attestationText: str(raw.attestation_text),
    complianceNotice: str(raw.compliance_notice),
  }
}

// ── API ──────────────────────────────────────────────────────────────────────
const rec = (id: number | string) => `/esignatures/records/${encodeURIComponent(String(id))}`

/** §11.70 integrity check. recompute=true re-snapshots the live record to detect post-signing edits. */
export async function verifySignature(id: number | string): Promise<ESignatureVerification | null> {
  return parseVerification(await apiFetch<unknown>(`${rec(id)}/verify?recompute=true`, { method: "GET" }))
}

/** §11.50 manifestation as structured JSON. */
export async function getManifestationJson(id: number | string): Promise<ESignatureManifestation | null> {
  return parseManifestation(await apiFetch<unknown>(`${rec(id)}/manifestation?format=json`, { method: "GET" }))
}

/** §11.50 manifestation as a self-contained printable HTML block (raw text/html). */
export async function getManifestationHtml(id: number | string): Promise<string> {
  const out = await apiFetch<unknown>(`${rec(id)}/manifestation?format=html`, { method: "GET" })
  return typeof out === "string" ? out : ""
}

// ── Verify status → UI badge mapping ──────────────────────────────────────────
export type VerifyTone = "neutral" | "success" | "error" | "indeterminate"
export type VerifyStatus = { tone: VerifyTone; label: string; detail: string }

export function verifyStatus(v: ESignatureVerification): VerifyStatus {
  if (!v.bound) {
    return {
      tone: "neutral",
      label: "Unbound (legacy)",
      detail: "Signed before content-binding; integrity is not cryptographically verifiable.",
    }
  }
  if (v.valid === true) {
    return { tone: "success", label: "Verified", detail: "Signature digest and record content match." }
  }
  if (v.valid === false) {
    if (v.reason === "digest_mismatch") {
      return { tone: "error", label: "Integrity check failed", detail: "Digest mismatch — the record/row was tampered with." }
    }
    if (v.reason === "record_content_changed") {
      return { tone: "error", label: "Integrity check failed", detail: "The signed record was edited after signing." }
    }
    return { tone: "error", label: "Integrity check failed", detail: v.reason || "Verification failed." }
  }
  return { tone: "indeterminate", label: "Indeterminate", detail: v.reason || "Could not determine integrity." }
}

/** Open the printable manifestation in a new window and trigger the browser print dialog. */
export async function printManifestation(id: number | string): Promise<boolean> {
  const html = await getManifestationHtml(id)
  if (!html || typeof window === "undefined") return false
  const w = window.open("", "_blank")
  if (!w) return false
  w.document.write(
    `<!doctype html><html><head><meta charset="utf-8"><title>e-signature manifestation #${id}</title></head><body>${html}</body></html>`,
  )
  w.document.close()
  w.focus()
  w.print()
  return true
}
