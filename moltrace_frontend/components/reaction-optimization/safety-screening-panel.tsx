"use client"

import { useEffect, useMemo, useState } from "react"
import {
  Check,
  ChevronDown,
  Loader2,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
  TriangleAlert,
  X,
} from "lucide-react"
import { ApiError } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { cn } from "@/lib/utils"
import {
  createScreening,
  getSafetyGate,
  listScreenings,
  reviewScreening,
  GATE_BANNER,
  REVIEW_BADGE_CLASS,
  REVIEW_STATUS_LABEL,
  RISK_BADGE_CLASS,
  type RiskLevel,
  type SafetyGate,
  type SafetyScreening,
} from "@/lib/reaction/safety-screenings"

const DISCLAIMER_FALLBACK =
  "Decision-support only; NOT a safety determination and never the sole basis for one. Any reaction flagged medium or above, and any energetic or reactive group, requires review by a qualified process-safety professional and a formal Process Hazard Analysis (PHA) before execution."

function smilesFromText(text: string): string[] {
  return text
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter(Boolean)
}

function RiskBadge({ risk, className }: { risk: RiskLevel; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium uppercase tracking-wide",
        RISK_BADGE_CLASS[risk],
        className,
      )}
    >
      {risk}
    </span>
  )
}

function GateIcon({ status }: { status: SafetyGate["status"] }) {
  if (status === "clear") return <ShieldCheck className="h-5 w-5 shrink-0" aria-hidden />
  if (status === "blocked") return <ShieldAlert className="h-5 w-5 shrink-0" aria-hidden />
  return <ShieldQuestion className="h-5 w-5 shrink-0" aria-hidden />
}

function ScreeningRow({
  screening,
  expanded,
  onToggle,
  onReview,
  reviewing,
}: {
  screening: SafetyScreening
  expanded: boolean
  onToggle: () => void
  onReview: (decision: "approved" | "rejected", note: string) => void
  reviewing: boolean
}) {
  const [note, setNote] = useState("")
  const isPending = screening.reviewStatus === "pending"

  return (
    <div className="rounded-md border border-border" data-testid={`screening-${screening.id}`}>
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-muted/40"
      >
        <ChevronDown className={cn("h-4 w-4 shrink-0 opacity-70 transition-transform", expanded && "rotate-180")} aria-hidden />
        <span className="min-w-0 flex-1 truncate text-sm font-medium">
          {screening.label || `Screening #${screening.id}`}
        </span>
        <RiskBadge risk={screening.overallRisk} />
        <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", REVIEW_BADGE_CLASS[screening.reviewStatus])}>
          {REVIEW_STATUS_LABEL[screening.reviewStatus]}
        </span>
      </button>

      {expanded ? (
        <div className="space-y-3 border-t border-border px-3 py-3">
          {screening.energeticGroupsFound.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-muted-foreground">Energetic groups:</span>
              {screening.energeticGroupsFound.map((g) => (
                <Badge key={g} variant="outline" className="text-[11px]">
                  {g}
                </Badge>
              ))}
            </div>
          ) : null}

          {screening.species.map((sp, i) => (
            <div key={`${sp.role}-${i}`} className="rounded-md bg-muted/30 p-2.5">
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-[11px]">
                  {sp.role}
                </Badge>
                <code className="truncate text-xs text-muted-foreground">{sp.smiles}</code>
                {!sp.parsed ? <span className="text-[11px] text-red-600 dark:text-red-400">unparsed</span> : null}
                <RiskBadge risk={sp.overallRisk} className="ml-auto" />
              </div>
              {sp.flaggedGroups.length > 0 ? (
                <ul className="mt-2 space-y-1.5">
                  {sp.flaggedGroups.map((fg) => (
                    <li key={fg.key} className="text-xs">
                      <span className="inline-flex items-center gap-1.5">
                        <RiskBadge risk={fg.severity} />
                        <span className="font-medium">{fg.label}</span>
                        {fg.count != null ? <span className="text-muted-foreground">×{fg.count}</span> : null}
                      </span>
                      {fg.mitigation ? (
                        <p className="mt-0.5 pl-1 text-muted-foreground">↳ {fg.mitigation}</p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1.5 text-xs text-muted-foreground">No energetic/reactive groups flagged for this species.</p>
              )}
            </div>
          ))}

          {/* Review action — only for pending screenings. The backend enforces
              owner/system/admin authorization; gate to qualified reviewers there. */}
          {isPending ? (
            <div className="space-y-2 rounded-md border border-dashed border-border p-2.5">
              <Label className="text-xs" htmlFor={`review-note-${screening.id}`}>
                Expert review note (required)
              </Label>
              <Textarea
                id={`review-note-${screening.id}`}
                className="min-h-[36px] text-xs"
                placeholder="PHA reference, mitigations, rationale…"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
              <div className="flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  className="gap-1.5"
                  disabled={reviewing || note.trim() === ""}
                  onClick={() => onReview("approved", note.trim())}
                >
                  {reviewing ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Check className="h-3.5 w-3.5" aria-hidden />}
                  Approve
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="gap-1.5 text-red-700 hover:text-red-700 dark:text-red-400"
                  disabled={reviewing || note.trim() === ""}
                  onClick={() => onReview("rejected", note.trim())}
                >
                  <X className="h-3.5 w-3.5" aria-hidden />
                  Reject
                </Button>
              </div>
            </div>
          ) : screening.reviewNote ? (
            <p className="text-xs text-muted-foreground">
              <span className="font-medium">Review note:</span> {screening.reviewNote}
            </p>
          ) : null}

          {screening.disclaimer ? (
            <p className="border-t border-border pt-2 text-[11px] italic text-muted-foreground">{screening.disclaimer}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

export function SafetyScreeningPanel({
  projectId,
  productSmilesHint,
}: {
  projectId: number
  productSmilesHint?: string | null
}) {
  const [gate, setGate] = useState<SafetyGate | null>(null)
  const [screenings, setScreenings] = useState<SafetyScreening[]>([])
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)
  const [reviewingId, setReviewingId] = useState<number | null>(null)
  const [error, setError] = useState("")
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const [reactantText, setReactantText] = useState("")
  const [reagentText, setReagentText] = useState("")
  const [productSmiles, setProductSmiles] = useState(productSmilesHint ?? "")
  const [label, setLabel] = useState("")

  async function refresh() {
    const [g, list] = await Promise.all([getSafetyGate(projectId), listScreenings(projectId)])
    setGate(g)
    setScreenings(list)
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void Promise.all([getSafetyGate(projectId), listScreenings(projectId)])
      .then(([g, list]) => {
        if (cancelled) return
        setGate(g)
        setScreenings(list)
      })
      .catch((e) => {
        if (!cancelled) setError(formatApiError(e, "Could not load safety screenings."))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  async function handleRun() {
    const reactant_smiles = smilesFromText(reactantText)
    if (reactant_smiles.length === 0) {
      setError("Enter at least one reactant SMILES to screen.")
      return
    }
    setRunning(true)
    setError("")
    try {
      const created = await createScreening(projectId, {
        reactant_smiles,
        reagent_smiles: smilesFromText(reagentText),
        product_smiles: productSmiles.trim() || null,
        label: label.trim() || null,
      })
      if (created) {
        setScreenings((prev) => [created, ...prev])
        setExpandedId(created.id)
        await refresh()
      }
    } catch (e) {
      setError(formatApiError(e, "Could not run the safety screen."))
    } finally {
      setRunning(false)
    }
  }

  async function handleReview(id: number, decision: "approved" | "rejected", note: string) {
    setReviewingId(id)
    setError("")
    try {
      const updated = await reviewScreening(projectId, id, { decision, note })
      if (updated) setScreenings((prev) => prev.map((s) => (s.id === id ? updated : s)))
      await refresh()
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 403
          ? "You are not authorized to review safety screenings for this project."
          : formatApiError(e, "Could not record the review."),
      )
    } finally {
      setReviewingId(null)
    }
  }

  const disclaimer = useMemo(
    () => screenings.find((s) => s.disclaimer)?.disclaimer || DISCLAIMER_FALLBACK,
    [screenings],
  )
  const banner = gate ? GATE_BANNER[gate.status] : null

  return (
    <ModuleCard
      accent="amber"
      eyebrow="Reaction · Structural Safety Screening"
      title="energetic / reactive-group screening"
      description="Structural (RDKit-SMARTS) screen for energetic and reactive functional groups, with an expert-review gate. Decision-support only — NOT a safety determination, and a clear result is never a safety clearance."
    >
      <div className="space-y-5">
        {error ? (
          <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>{error}</span>
          </div>
        ) : null}

        {/* Project gate banner */}
        {banner && gate ? (
          <div className={cn("flex items-start gap-3 rounded-md border p-3", banner.className)}>
            <GateIcon status={gate.status} />
            <div className="min-w-0 flex-1 space-y-1">
              <p className="text-sm font-medium">{banner.title}</p>
              <p className="text-xs opacity-90">{gate.summary}</p>
              {gate.blockingScreeningIds.length > 0 ? (
                <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                  <span className="text-[11px] opacity-80">Blocking:</span>
                  {gate.blockingScreeningIds.map((id) => (
                    <button
                      key={id}
                      type="button"
                      onClick={() => setExpandedId(id)}
                      className="rounded border border-current/30 px-1.5 py-0.5 text-[11px] font-medium hover:bg-current/10"
                    >
                      #{id}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        ) : null}

        {/* Standing disclaimer — always visible, verbatim from the engine. */}
        <div className="flex items-start gap-2 rounded-md border border-dashed border-border bg-muted/30 p-3">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
          <p className="text-xs text-muted-foreground">{disclaimer}</p>
        </div>

        {/* Run a screen */}
        <Collapsible className="rounded-md border border-border">
          <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-sm font-medium hover:bg-muted/40">
            Run a safety screen
            <ChevronDown className="h-4 w-4 shrink-0 opacity-70" aria-hidden />
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-3 border-t border-border px-3 py-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label className="text-xs" htmlFor="ss-reactants">
                  Reactant SMILES (one per line)
                </Label>
                <Textarea
                  id="ss-reactants"
                  className="min-h-[64px] font-mono text-xs"
                  placeholder={"CCN=[N+]=[N-]\nBrCc1ccccc1"}
                  value={reactantText}
                  onChange={(e) => setReactantText(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs" htmlFor="ss-reagents">
                  Reagent SMILES (optional)
                </Label>
                <Textarea
                  id="ss-reagents"
                  className="min-h-[64px] font-mono text-xs"
                  placeholder="O=C([O-])[O-].[K+].[K+]"
                  value={reagentText}
                  onChange={(e) => setReagentText(e.target.value)}
                />
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label className="text-xs" htmlFor="ss-product">
                  Product SMILES (optional)
                </Label>
                <Input
                  id="ss-product"
                  className="font-mono text-xs"
                  value={productSmiles}
                  onChange={(e) => setProductSmiles(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs" htmlFor="ss-label">
                  Label (optional)
                </Label>
                <Input
                  id="ss-label"
                  className="text-xs"
                  placeholder="Step 3 azide displacement"
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                />
              </div>
            </div>
            <Button type="button" className="gap-2" onClick={handleRun} disabled={running}>
              {running ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <ShieldQuestion className="h-4 w-4" aria-hidden />}
              {running ? "Screening…" : "Run safety screen"}
            </Button>
          </CollapsibleContent>
        </Collapsible>

        {/* Screenings list */}
        {screenings.length > 0 ? (
          <div className="space-y-2">
            {screenings.map((s) => (
              <ScreeningRow
                key={s.id}
                screening={s}
                expanded={expandedId === s.id}
                onToggle={() => setExpandedId((cur) => (cur === s.id ? null : s.id))}
                onReview={(decision, note) => handleReview(s.id, decision, note)}
                reviewing={reviewingId === s.id}
              />
            ))}
          </div>
        ) : loading ? (
          <p className="text-sm text-muted-foreground">Loading safety screenings…</p>
        ) : (
          <p className="text-sm text-muted-foreground">
            No safety screenings yet — run one above to screen species for energetic/reactive groups.
          </p>
        )}
      </div>
    </ModuleCard>
  )
}
