"use client"

import { useEffect, useState } from "react"
import { Loader2 } from "lucide-react"
import { apiFetch } from "@/lib/api/client"
import type { components } from "@/src/lib/api/schema"

type Manifestation = components["schemas"]["ESignatureManifestation"]
type Verification = components["schemas"]["ESignatureVerification"]

/**
 * Signature inspection — the §11.70 binding and the §11.50 manifestation.
 *
 * TWO RULES THIS COMPONENT EXISTS TO HOLD:
 *
 *  - `attestation_text` and `compliance_notice` are rendered VERBATIM. §11.50
 *    requires the signature manifestation be displayable, which means the text the
 *    signer was shown, not our summary of it. Do not truncate them, do not
 *    line-clamp them, do not reword them, and do not move them behind a "read
 *    more". They are reproduced with whitespace preserved for the same reason.
 *
 *  - The content hash is explained in plain language rather than shown as a bare
 *    digest. `record_content_hash` is what ties this signature to one exact
 *    snapshot; a reader who does not know that reads it as decoration.
 */

type Load<T> = { status: "loading" } | { status: "ready"; data: T } | { status: "error" }

export function SignatureInspection({ signatureId }: { signatureId: number }) {
  const [manifest, setManifest] = useState<Load<Manifestation>>({ status: "loading" })
  const [check, setCheck] = useState<Load<Verification> | { status: "idle" }>({ status: "idle" })

  useEffect(() => {
    let active = true
    setManifest({ status: "loading" })
    apiFetch<Manifestation>(`/esignatures/records/${signatureId}/manifestation`, { method: "GET" })
      .then((data) => active && setManifest({ status: "ready", data }))
      .catch(() => active && setManifest({ status: "error" }))
    return () => {
      active = false
    }
  }, [signatureId])

  async function runCheck() {
    setCheck({ status: "loading" })
    try {
      const data = await apiFetch<Verification>(`/esignatures/records/${signatureId}/verify`, {
        method: "GET",
      })
      setCheck({ status: "ready", data })
    } catch {
      setCheck({ status: "error" })
    }
  }

  if (manifest.status === "loading") {
    return <p className="text-xs text-muted-foreground">Loading signature record…</p>
  }
  if (manifest.status === "error") {
    return (
      <p className="text-xs" style={{ color: "var(--mt-amber-ink)" }}>
        This signature record could not be loaded.
      </p>
    )
  }

  const m = manifest.data
  const rows: Array<[string, string | null | undefined]> = [
    ["Signed by", m.printed_name],
    ["Email", m.signer_email],
    ["Meaning", m.meaning_label],
    ["Reason", m.reason],
    ["Signed at (UTC)", m.signed_at_utc],
    ["Applies to", `${m.target_type} #${m.target_id}`],
    ["Authentication", m.authentication_method],
  ]

  return (
    <div className="space-y-4 text-xs">
      <dl className="grid grid-cols-[9rem_1fr] gap-x-4 gap-y-1.5">
        {rows.map(([k, v]) =>
          v ? (
            <div key={k} className="contents">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="text-foreground">{v}</dd>
            </div>
          ) : null,
        )}
      </dl>

      {/* The §11.70 binding, explained rather than displayed as an ornament. */}
      <div className="rounded-lg border bg-muted/30 p-3">
        <div className="font-semibold text-foreground">
          What this signature is bound to
          {m.binding_status === "unbound" ? " — not bound" : null}
        </div>
        <p className="mt-1 text-muted-foreground">
          This signature is bound to a specific snapshot of this record. If the record changes, the
          signature no longer matches.
        </p>
        {m.record_content_hash ? (
          <p className="mt-2 break-all font-mono text-[11px] text-muted-foreground">
            {m.record_content_hash}
          </p>
        ) : (
          <p className="mt-2" style={{ color: "var(--mt-amber-ink)" }}>
            No content hash is recorded for this signature, so it is not bound to a snapshot.
          </p>
        )}

        <button
          type="button"
          onClick={runCheck}
          disabled={check.status === "loading"}
          className="mt-3 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60"
        >
          {check.status === "loading" ? <Loader2 className="h-3 w-3 animate-spin" aria-hidden /> : null}
          Check this signature still matches
        </button>

        {check.status === "error" ? (
          <p className="mt-2" style={{ color: "var(--mt-amber-ink)" }}>
            The check could not be completed. This is not a finding about the signature.
          </p>
        ) : null}

        {check.status === "ready" ? <VerificationReadout result={check.data} /> : null}
      </div>

      {/* §11.50 — verbatim, both of them. */}
      <div className="rounded-lg border p-3">
        <div className="mb-1 font-semibold text-foreground">Signature manifestation</div>
        <p className="whitespace-pre-wrap leading-relaxed text-foreground">{m.attestation_text}</p>
        <p className="mt-2 whitespace-pre-wrap leading-relaxed text-muted-foreground">
          {m.compliance_notice}
        </p>
      </div>
    </div>
  )
}

/**
 * `bound` and `valid` are separate questions and stay separate: a signature can be
 * bound to a snapshot that no longer matches. Only fields the server returned are
 * shown — nothing is inferred from the absence of one.
 */
function VerificationReadout({ result }: { result: Verification }) {
  const lines: Array<[string, boolean | null | undefined]> = [
    ["Bound to a snapshot", result.bound],
    ["Stored hash matches the record", result.hash_matches],
    ["Record content unchanged", result.content_matches],
    ["Signature valid", result.valid],
  ]
  return (
    <div className="mt-2 space-y-1">
      {lines.map(([label, state]) =>
        state == null ? null : (
          <div key={label} className="text-foreground">
            {state ? "✓" : "✕"} {label}
          </div>
        ),
      )}
      {result.reason ? <p className="mt-1 text-muted-foreground">{result.reason}</p> : null}
      {result.recomputed_content_hash && result.recomputed_content_hash !== result.record_content_hash ? (
        <p className="mt-1 break-all font-mono text-[11px]" style={{ color: "var(--mt-amber-ink)" }}>
          Recomputed: {result.recomputed_content_hash}
        </p>
      ) : null}
    </div>
  )
}
