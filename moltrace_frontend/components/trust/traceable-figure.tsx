"use client"

import { useState } from "react"
import { AlertTriangle, FileWarning, Link2, Loader2 } from "lucide-react"
import { apiFetch } from "@/lib/api/client"
import { CitationDetail, type RegulatoryCitation } from "./citation-detail"
import {
  chainFindings,
  chainOutcome,
  describeBreak,
  type SubjectAuditChainVerification,
  type TraceableSubject,
} from "./chain-verification"

/**
 * TraceableFigure — the wrapper every number that claims to be evidence goes in.
 *
 * The product claim is that a figure without a trail is identifiable as one. That
 * only holds if the component makes it structurally hard to render a bare number,
 * so the rules below are enforced here rather than left to each call site:
 *
 *  1. ABSENCE IS A STATE, NOT A BLANK. No citation renders a visible "not traced"
 *     marker. A number that quietly appears with nothing beside it is exactly the
 *     failure this component exists to prevent.
 *  2. NEVER FABRICATE A LINK. Handled in CitationDetail: an unresolvable source
 *     says so and offers nothing to click.
 *  3. `rule_set_version` IS PART OF THE FIGURE. It sits inline with the value, not
 *     in a footnote — a threshold means nothing without the guidance version that
 *     produced it.
 *  4. `human_review_required` STAYS VISIBLE. It is never styled down, collapsed,
 *     or moved below the fold.
 *  5. NO COLOUR-CODED CONFIDENCE and no pass/fail the backend did not compute.
 *     Every state shown here is one the server returned; nothing is derived from a
 *     threshold invented on this side.
 */

export type TraceableFigureProps = {
  /** The figure itself. `null`/`undefined` renders "—" rather than a fabricated 0. */
  value: number | string | null | undefined
  unit?: string
  label?: string
  /** Scope for the audit-trail check. Omit when the figure has no verifiable subject. */
  subject?: TraceableSubject | null
  citation?: RegulatoryCitation | null
  ruleSetVersion?: string | null
  reviewRequired?: boolean
  className?: string
}

type VerifyState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; result: SubjectAuditChainVerification }
  | { status: "error" }

export function TraceableFigure({
  value,
  unit,
  label,
  subject,
  citation,
  ruleSetVersion,
  reviewRequired = false,
  className,
}: TraceableFigureProps) {
  const [showCitation, setShowCitation] = useState(false)
  const [verify, setVerify] = useState<VerifyState>({ status: "idle" })

  async function runVerify() {
    if (!subject) return
    setVerify({ status: "loading" })
    try {
      const result = await apiFetch<SubjectAuditChainVerification>(
        `/audit/${subject.type}/${subject.id}/verify`,
        { method: "GET" },
      )
      setVerify({ status: "done", result })
    } catch {
      setVerify({ status: "error" })
    }
  }

  return (
    <div className={className}>
      {label ? <div className="text-xs text-muted-foreground">{label}</div> : null}

      {/* Rule 3 — the guidance version rides with the number, not under it. */}
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="text-2xl font-semibold tabular-nums text-foreground">
          {value ?? "—"}
          {value != null && unit ? <span className="ml-0.5 text-base font-normal">{unit}</span> : null}
        </span>
        {ruleSetVersion ? (
          <span className="font-mono text-[11px] text-muted-foreground">{ruleSetVersion}</span>
        ) : null}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        {/* Rule 1 — absence is rendered, never omitted. */}
        {citation ? (
          <button
            type="button"
            onClick={() => setShowCitation((open) => !open)}
            aria-expanded={showCitation}
            className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            style={{ color: "var(--mt-cyan-ink)" }}
          >
            <Link2 className="h-3 w-3" aria-hidden />
            {showCitation ? "Hide source" : "Traced to source"}
          </button>
        ) : (
          <span
            className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium"
            style={{ color: "var(--mt-amber-ink)", borderColor: "var(--mt-amber)" }}
          >
            <FileWarning className="h-3 w-3" aria-hidden />
            Not traced — no citation recorded
          </span>
        )}

        {/* Rule 4 — visible, every time, never styled away. */}
        {reviewRequired ? (
          <span
            className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium"
            style={{ backgroundColor: "var(--mt-amber-soft)", color: "var(--mt-amber-ink)" }}
          >
            <AlertTriangle className="h-3 w-3" aria-hidden />
            Human review required
          </span>
        ) : null}

        {subject ? (
          <button
            type="button"
            onClick={runVerify}
            disabled={verify.status === "loading"}
            className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-60"
          >
            {verify.status === "loading" ? (
              <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
            ) : null}
            Verify the trail behind this number
          </button>
        ) : null}
      </div>

      {showCitation && citation ? (
        <div className="mt-2">
          <CitationDetail citation={citation} />
        </div>
      ) : null}

      {verify.status === "error" ? (
        <p className="mt-2 text-xs" style={{ color: "var(--mt-amber-ink)" }}>
          The trail could not be checked just now. This is not a finding about the record.
        </p>
      ) : null}

      {verify.status === "done" ? <ChainResult result={verify.result} /> : null}
    </div>
  )
}

/**
 * The verification readout.
 *
 * Two things are load-bearing here. `entry_count: 0` is rendered as "nothing was
 * checked" and is never a pass — the backend returns `no_chained_entries` for it,
 * and a tick there would assert something no one established. And the two findings
 * stay two: the subject's own slice can prove nothing was altered, but only the
 * global walk can show nothing was removed, so merging them would overstate what
 * was checked.
 */
function ChainResult({ result }: { result: SubjectAuditChainVerification }) {
  const outcome = chainOutcome(result)
  const cause = describeBreak(result)

  if (outcome === "unchecked") {
    return (
      <div className="mt-2 rounded-lg border bg-muted/30 p-3 text-xs">
        <div className="font-semibold text-foreground">Nothing was checked</div>
        <p className="mt-1 text-muted-foreground">
          No audit entries are chained for this record yet, so its trail has not been established
          either way. This is not a pass.
        </p>
      </div>
    )
  }

  return (
    <div className="mt-2 rounded-lg border bg-muted/30 p-3 text-xs">
      <div className="font-semibold text-foreground">
        {outcome === "verified" ? "Trail verified" : "Trail could not be verified"}
      </div>

      {outcome === "broken" ? (
        <p className="mt-1" style={{ color: "var(--mt-amber-ink)" }}>
          {/* Only a cause the server named. An unrecognised break kind says the trail
              failed without inventing a reason for it. */}
          {cause ?? "The chain did not verify. Contact an administrator with this record's id."}
          {result.first_break_seq != null ? ` (first break at entry ${result.first_break_seq})` : null}
        </p>
      ) : null}

      <ul className="mt-2 space-y-1.5">
        {chainFindings(result).map((f) => (
          <li key={f.label}>
            <span className="font-medium text-foreground">
              {f.ok ? "✓" : "✕"} {f.label}
            </span>
            <span className="block text-muted-foreground">{f.covers}</span>
          </li>
        ))}
      </ul>

      <p className="mt-2 text-muted-foreground">
        {result.verified_count} of {result.entry_count} entries about this record checked.
      </p>
    </div>
  )
}
