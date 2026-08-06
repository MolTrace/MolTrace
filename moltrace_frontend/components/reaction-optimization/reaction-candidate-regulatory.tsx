"use client"

// Repho — proposal-time regulatory verdict, rendered on a BO candidate and on the
// run that produced it.
//
// Three rules this file exists to hold (see the FE handoff, §4):
//   1. The unchecked-limits warning renders ABOVE the figures it qualifies —
//      same rule as qNMR purity, a caveat goes above the number it caveats.
//   2. A verdict is never rendered as cleared unless it genuinely was: `feasible`
//      only means "no hard violation". See `regulatory-proposal.ts`.
//   3. The link back to the source Regentry action item is the audit trail, so it
//      is a real deep link into the action queue, not a bare id.

import Link from "next/link"
import { ChevronDown, ExternalLink } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { cn } from "@/lib/utils"
import { statusLabel } from "@/lib/ui/status"
import {
  SEVERITY_BADGE_CLASS,
  type ComplianceViolation,
} from "@/lib/reaction/regulatory-compliance"
import {
  PROPOSAL_REGULATORY_STATE,
  humanizeObjectiveField,
  proposalRegulatoryState,
  violationSentence,
  type CandidateRegulatory,
  type RunRegulatorySummary,
} from "@/lib/reaction/regulatory-proposal"

/** Deep link to the source action item in the Regentry queue. The queue reads
 *  `item` and focuses that row — a link into an unfiltered 200-row list would not
 *  be an audit trail. */
export function regulatoryActionItemHref(id: number): string {
  return `/regulatory/action-queue?item=${id}`
}

function SourceActionItems({ ids }: { ids: number[] }) {
  if (ids.length === 0) {
    return (
      <span className="text-muted-foreground">
        No source action item recorded on this limit.
      </span>
    )
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {ids.map((id) => (
        <Link
          key={id}
          href={regulatoryActionItemHref(id)}
          className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[11px] underline-offset-4 hover:bg-muted hover:underline"
        >
          Action item {id}
          <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
        </Link>
      ))}
    </span>
  )
}

function ViolationDetail({ v }: { v: ComplianceViolation }) {
  return (
    <div className="rounded-md border bg-muted/20 p-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{violationSentence(v)}</span>
        {v.severity ? (
          <Badge variant="secondary" className={cn("uppercase", SEVERITY_BADGE_CLASS[v.severity] ?? "")}>
            {statusLabel(v.severity)}
          </Badge>
        ) : null}
        <Badge variant="outline">{v.isHard ? "hard limit" : "soft limit"}</Badge>
      </div>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        {v.basis ? (
          <>
            <dt className="text-muted-foreground">basis</dt>
            <dd className="italic">{v.basis}</dd>
          </>
        ) : null}
        <dt className="text-muted-foreground">source</dt>
        <dd>
          <SourceActionItems ids={v.sourceActionItemIds} />
        </dd>
      </dl>
    </div>
  )
}

export function CandidateRegulatoryBadge({ reg }: { reg: CandidateRegulatory }) {
  const meta = PROPOSAL_REGULATORY_STATE[proposalRegulatoryState(reg)]
  return (
    <Badge variant="secondary" className={meta.badgeClass} title={meta.description}>
      {meta.label}
    </Badge>
  )
}

/** The expandable body for one candidate: what was breached, on what basis, and
 *  which limits could not be checked at all. */
export function CandidateRegulatoryDetail({ reg }: { reg: CandidateRegulatory }) {
  const state = proposalRegulatoryState(reg)
  const meta = PROPOSAL_REGULATORY_STATE[state]
  return (
    <div className="space-y-2 py-1">
      <p className="text-xs text-muted-foreground">{meta.description}</p>
      {reg.violations.map((v, i) => (
        <ViolationDetail key={i} v={v} />
      ))}
      {reg.unmeasured.length > 0 ? (
        <div className="rounded-md border border-dashed p-3 text-xs">
          <p className="font-medium">Could not be checked against this proposal</p>
          <p className="mt-1 text-muted-foreground">
            {reg.unmeasured.map(humanizeObjectiveField).join(", ")} — a limit applies, but the
            optimizer scores a candidate on one combined objective and predicts no value for these.
            They are checked once the experiment is recorded and a result exists. Never counted as
            passing.
          </p>
        </div>
      ) : null}
      {reg.penalty != null && reg.penalty > 0 ? (
        <p className="text-xs text-muted-foreground">
          Ranking was reduced by {reg.penalty} for the breaches above.
        </p>
      ) : null}
    </div>
  )
}

/** One table cell: badge plus an inline expander. Kept self-contained so the row
 *  it lives in does not have to own the open state. */
export function CandidateRegulatoryCell({ reg }: { reg: CandidateRegulatory | null }) {
  if (reg == null) {
    return (
      <span className="text-xs text-muted-foreground" title="This project has no active limit carrying a numeric bound.">
        No active limits
      </span>
    )
  }
  const hasDetail = reg.violations.length > 0 || reg.unmeasured.length > 0
  if (!hasDetail) {
    return <CandidateRegulatoryBadge reg={reg} />
  }
  return (
    <Collapsible>
      <div className="flex flex-col items-start gap-1">
        <CandidateRegulatoryBadge reg={reg} />
        <CollapsibleTrigger className="group inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground">
          {reg.violations.length > 0
            ? `${reg.violations.length} breach${reg.violations.length > 1 ? "es" : ""}`
            : "why"}
          <ChevronDown className="h-3 w-3 shrink-0 transition-transform group-data-[state=open]:rotate-180" />
        </CollapsibleTrigger>
      </div>
      <CollapsibleContent>
        <CandidateRegulatoryDetail reg={reg} />
      </CollapsibleContent>
    </Collapsible>
  )
}

/** Run-level strip. Renders the unchecked-limits caveat FIRST, then the counts it
 *  qualifies — never the other way round.
 *
 *  `hasActiveLimits` says whether this project actually has enforceable regulatory
 *  limits in play. Without it the strip cannot tell "nothing was blocked" from
 *  "there was nothing to block with", and the feasibility count is a general
 *  survived-every-filter number (safety included), not a regulatory one — so a
 *  zero is never attributed to a regulatory limit unless one did the blocking. */
export function RunRegulatoryStrip({
  summary,
  hasActiveLimits = false,
}: {
  summary: RunRegulatorySummary
  hasActiveLimits?: boolean
}) {
  const { feasibleCount, blockedCount, feasibilityKnown, uncheckedWarning, readyToSchedule } =
    summary
  const regulatoryInPlay = hasActiveLimits || blockedCount > 0 || uncheckedWarning != null
  if (!regulatoryInPlay) return null

  return (
    <div className="space-y-3">
      {uncheckedWarning != null ? (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3">
          <p className="text-xs font-medium text-amber-900 dark:text-amber-200">
            Limits that could not be checked against these proposals
          </p>
          <p className="mt-1 text-xs text-amber-900/90 dark:text-amber-200/90">{uncheckedWarning}</p>
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border p-3">
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
            Candidates that passed every filter
          </p>
          <p className="mt-1 font-mono text-2xl font-bold tabular-nums">
            {feasibilityKnown ? feasibleCount : "unknown"}
          </p>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {feasibilityKnown
              ? "Counts every filter the run applied, including safety — not regulatory alone."
              : "This run was recorded before proposals carried a feasibility count. Unknown — not zero blocked."}
          </p>
        </div>
        <div className="rounded-lg border p-3">
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
            Filtered by a hard limit
          </p>
          <p
            className="mt-1 font-mono text-2xl font-bold tabular-nums"
            style={blockedCount > 0 ? { color: "var(--mt-red, #dc2626)" } : undefined}
          >
            {blockedCount}
          </p>
        </div>
      </div>

      {feasibilityKnown && feasibleCount === 0 ? (
        <p className="text-xs font-medium text-destructive">
          {blockedCount > 0
            ? "No candidate survived this run's filters, and a hard regulatory limit filtered some of them. There is nothing here to schedule — this run needs review."
            : "No candidate survived this run's filters. There is nothing here to schedule — this run needs review."}
        </p>
      ) : null}
      {!readyToSchedule && feasibilityKnown && (feasibleCount ?? 0) > 0 ? (
        <p className="text-xs text-muted-foreground">
          Proposals still require human review before scheduling.
        </p>
      ) : null}
    </div>
  )
}
