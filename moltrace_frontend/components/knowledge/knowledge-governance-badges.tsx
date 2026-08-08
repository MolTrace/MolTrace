"use client"

// Shared markers for corpus governance, so every surface says the same thing
// about the same state. See `lib/knowledge/corpus-governance.ts` for why each
// state exists and what collapsing it into a neighbour would assert.

import { AlertTriangle, CheckCircle2, CircleHelp, HelpCircle, XCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import {
  PROVENANCE_PRESENTATION,
  REVIEW_STATE_PRESENTATION,
  type ProvenanceState,
  type ReviewState,
} from "@/lib/knowledge/corpus-governance"

const REVIEW_TONE_CLASS: Record<ReviewState, string> = {
  accepted: "border-emerald-500/50 text-emerald-700 dark:text-emerald-400",
  // A refused record must not merely sort lower — it has to look different.
  rejected: "border-red-500/60 bg-red-500/10 text-red-700 dark:text-red-400",
  unreviewed: "border-muted-foreground/40 text-muted-foreground",
}

const REVIEW_ICON: Record<ReviewState, typeof CheckCircle2> = {
  accepted: CheckCircle2,
  rejected: XCircle,
  unreviewed: CircleHelp,
}

export function ReviewStateBadge({ state, className }: { state: ReviewState; className?: string }) {
  const presentation = REVIEW_STATE_PRESENTATION[state]
  const Icon = REVIEW_ICON[state]
  return (
    <Badge
      variant="outline"
      title={presentation.description}
      className={cn("gap-1 whitespace-nowrap", REVIEW_TONE_CLASS[state], className)}
    >
      <Icon className="h-3 w-3 shrink-0" aria-hidden />
      {presentation.label}
    </Badge>
  )
}

/** Row emphasis for a refused hit. Paired with the badge, never instead of it. */
export function rejectedRowClass(state: ReviewState): string {
  return state === "rejected" ? "bg-red-500/5" : ""
}

const PROVENANCE_TONE_CLASS: Record<ProvenanceState, string> = {
  current: "border-muted-foreground/30 text-muted-foreground",
  superseded: "border-amber-500/60 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  // Unknown is styled as unknown, not as a mild version of fine.
  unknown: "border-muted-foreground/50 text-muted-foreground",
}

const PROVENANCE_ICON: Record<ProvenanceState, typeof CheckCircle2> = {
  current: CheckCircle2,
  superseded: AlertTriangle,
  unknown: HelpCircle,
}

export function ProvenanceBadge({
  state,
  className,
  /** `current` is the quiet default — hide it where it would just add noise. */
  hideWhenCurrent = false,
}: {
  state: ProvenanceState
  className?: string
  hideWhenCurrent?: boolean
}) {
  if (hideWhenCurrent && state === "current") return null
  const presentation = PROVENANCE_PRESENTATION[state]
  const Icon = PROVENANCE_ICON[state]
  return (
    <Badge
      variant="outline"
      title={presentation.description}
      className={cn("gap-1 whitespace-nowrap", PROVENANCE_TONE_CLASS[state], className)}
    >
      <Icon className="h-3 w-3 shrink-0" aria-hidden />
      {presentation.label}
    </Badge>
  )
}
