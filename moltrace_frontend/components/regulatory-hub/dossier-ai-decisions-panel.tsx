"use client"

import { useState } from "react"
import { AlertTriangle, CheckCircle2, Link2, Loader2, ShieldAlert, ShieldCheck, XCircle } from "lucide-react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import type { components } from "@/src/lib/api/schema"

/**
 * EU GMP Draft Annex 22 AI-decision records on a dossier.
 *
 * The Annex is a DRAFT and not in force: this panel renders the `disclaimer`
 * string the API returns and never labels anything "Annex 22 compliant". It is
 * decision-support + an audit/governance surface — a tamper-evident hash chain
 * of AI decisions, each with its risk level, compliance checklist, and (where
 * required) a human-in-the-loop review gate.
 *
 * Read/review only from the FE: records are normally created by the backend
 * governed path. The workspace owns the list state + load-time fetch; this
 * panel renders it, runs the HITL review POST, and the chain-verify GET.
 */

export type AIDecision = components["schemas"]["RegulatoryAIDecision"]
type ChainStatus = components["schemas"]["RegulatoryAIDecisionChainStatus"]

/** risk_level → badge palette. */
function riskClass(level: string): string {
  switch (level.toLowerCase()) {
    case "high":
    case "critical":
      return "border-destructive/50 text-destructive"
    case "medium":
    case "moderate":
      return "border-warning/50 text-warning"
    case "low":
      return "border-success/50 text-success"
    default:
      return "text-muted-foreground"
  }
}

function shortHash(h: string | null | undefined): string {
  if (!h) return "—"
  return h.length > 12 ? `${h.slice(0, 10)}…` : h
}

function confidencePct(c: number): string {
  if (!Number.isFinite(c)) return "—"
  return `${Math.round(c * 100)}%`
}

/** humanize a checklist key: human_oversight → "human oversight". */
function humanizeKey(key: string): string {
  return key.replace(/_/g, " ")
}

export function DossierAIDecisionsPanel({
  decisions,
  dossierId,
  onReviewed,
}: {
  decisions: AIDecision[]
  dossierId: number
  onReviewed: () => void | Promise<void>
}) {
  const [verify, setVerify] = useState<ChainStatus | null>(null)
  const [verifyBusy, setVerifyBusy] = useState(false)
  const [verifyErr, setVerifyErr] = useState("")
  const [reviewBusyHash, setReviewBusyHash] = useState<string | null>(null)
  const [reviewErr, setReviewErr] = useState("")
  const [reasonByHash, setReasonByHash] = useState<Record<string, string>>({})

  // Review rows come back as their own entries (decision_type ends
  // ".hitl_review", reviews_entry_hash → the reviewed decision). Filter them
  // out of the main list and associate the verdict back onto the reviewed row.
  const reviewRows = decisions.filter((d) => d.decision_type.endsWith(".hitl_review"))
  const mainDecisions = decisions.filter((d) => !d.decision_type.endsWith(".hitl_review"))
  const reviewByTarget = new Map<string, AIDecision>()
  for (const r of reviewRows) {
    if (r.reviews_entry_hash) reviewByTarget.set(r.reviews_entry_hash, r)
  }

  const disclaimer = decisions.find((d) => d.disclaimer)?.disclaimer ?? ""

  async function runVerify() {
    if (!Number.isFinite(dossierId)) return
    setVerifyBusy(true)
    setVerifyErr("")
    try {
      const data = await apiFetch<ChainStatus>(
        `/regulatory/dossiers/${dossierId}/ai-decisions/verify`,
        { method: "GET" },
      )
      setVerify(data)
    } catch (e) {
      setVerify(null)
      setVerifyErr(formatApiError(e, "Chain verification failed."))
    } finally {
      setVerifyBusy(false)
    }
  }

  async function submitReview(entryHash: string, approved: boolean) {
    if (!Number.isFinite(dossierId)) return
    setReviewBusyHash(entryHash)
    setReviewErr("")
    try {
      const reason = (reasonByHash[entryHash] ?? "").trim()
      await apiFetch(`/regulatory/dossiers/${dossierId}/ai-decisions/${encodeURIComponent(entryHash)}/review`, {
        method: "POST",
        body: { approved, reason: reason || null },
      })
      await onReviewed()
    } catch (e) {
      setReviewErr(formatApiError(e, "Review submission failed."))
    } finally {
      setReviewBusyHash(null)
    }
  }

  return (
    <ModuleCard
      accent="cyan"
      eyebrow="Dossier · AI Governance · Draft Annex 22"
      title="AI decision records"
      icon={ShieldCheck}
      description="Tamper-evident hash chain of governed AI decisions for this dossier under EU GMP Draft Annex 22 — each with its risk level, compliance checklist, and human-review state."
    >
      <div className="space-y-4">
        {/* Draft framing — render the disclaimer the API returns; never claim compliance. */}
        {disclaimer ? (
          <AlertCard variant="warning" title="Draft guidance — not in force" description={disclaimer} />
        ) : null}

        {/* Chain-verify affordance — the audit proof point. */}
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" size="sm" className="gap-1.5" onClick={() => void runVerify()} disabled={verifyBusy}>
            {verifyBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <ShieldCheck className="h-3.5 w-3.5" aria-hidden />}
            Verify chain
          </Button>
          {verify ? (
            verify.ok ? (
              <Badge variant="outline" className="gap-1 border-success/50 font-normal text-success">
                <CheckCircle2 className="h-3 w-3" aria-hidden />
                chain verified · {verify.count} {verify.count === 1 ? "entry" : "entries"}
              </Badge>
            ) : (
              <Badge variant="outline" className="gap-1 border-destructive/50 font-normal text-destructive">
                <ShieldAlert className="h-3 w-3" aria-hidden />
                tamper detected · {(verify.breaks ?? []).length} break{(verify.breaks ?? []).length === 1 ? "" : "s"}
              </Badge>
            )
          ) : null}
        </div>
        {verifyErr ? <AlertCard variant="error" title="Verify failed" description={verifyErr} /> : null}
        {verify && !verify.ok && (verify.breaks ?? []).length > 0 ? (
          <AlertCard variant="error" title="Chain breaks">
            <ul className="ml-4 list-disc space-y-0.5 text-xs text-foreground/90">
              {(verify.breaks ?? []).map((b, i) => (
                <li key={`break-${i}`} className="break-all font-mono">{b}</li>
              ))}
            </ul>
          </AlertCard>
        ) : null}

        {reviewErr ? <AlertCard variant="error" title="Review failed" description={reviewErr} /> : null}

        {mainDecisions.length === 0 ? (
          <div className="rounded-md border border-dashed bg-muted/20 px-4 py-8 text-center">
            <p className="text-sm font-medium text-foreground">No AI decisions recorded yet.</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Governed AI decisions are written to the dossier&apos;s tamper-evident chain by the backend
              as the AI-assisted path runs; they will appear here.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {mainDecisions.map((d) => {
              const reviewRow = reviewByTarget.get(d.entry_hash)
              const reviewed = d.hitl_approved != null || reviewRow != null
              const pending = d.hitl_required && !reviewed
              const approved = d.hitl_approved ?? reviewRow?.hitl_approved ?? null
              const reviewer = d.hitl_reviewer_id ?? reviewRow?.user_id ?? null
              const checklist = Object.entries(d.compliance_checklist ?? {})
              return (
                <div key={d.entry_hash} className="space-y-3 rounded-md border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{d.decision_type}</span>
                    <code className="font-mono text-xs text-muted-foreground">
                      {d.model_name}@{d.model_version}
                    </code>
                    <Badge variant="outline" className={cn("font-normal uppercase", riskClass(d.risk_level))}>
                      {d.risk_level} risk
                    </Badge>
                    <span className="font-mono text-xs tabular-nums text-muted-foreground">
                      conf {confidencePct(d.confidence)}
                    </span>
                    {pending ? (
                      <Badge variant="outline" className="ml-auto gap-1 border-warning/50 font-normal text-warning">
                        <AlertTriangle className="h-3 w-3" aria-hidden />
                        Pending human review
                      </Badge>
                    ) : d.hitl_required ? (
                      <Badge
                        variant="outline"
                        className={cn(
                          "ml-auto gap-1 font-normal",
                          approved === true
                            ? "border-success/50 text-success"
                            : approved === false
                              ? "border-destructive/50 text-destructive"
                              : "text-muted-foreground",
                        )}
                      >
                        {approved === true ? (
                          <CheckCircle2 className="h-3 w-3" aria-hidden />
                        ) : approved === false ? (
                          <XCircle className="h-3 w-3" aria-hidden />
                        ) : null}
                        {approved === true ? "approved" : approved === false ? "rejected" : "reviewed"}
                        {reviewer ? ` · ${reviewer}` : ""}
                      </Badge>
                    ) : null}
                  </div>

                  <p className="text-xs text-muted-foreground">{d.regulatory_basis}</p>

                  {/* Compliance checklist — the 7 boolean checks as ✓/✗ rows. */}
                  {checklist.length > 0 ? (
                    <div className="grid gap-1 sm:grid-cols-2">
                      {checklist.map(([key, pass]) => (
                        <div key={key} className="flex items-center gap-1.5 text-xs">
                          {pass ? (
                            <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-success" aria-hidden />
                          ) : (
                            <XCircle className="h-3.5 w-3.5 shrink-0 text-destructive" aria-hidden />
                          )}
                          <span className={cn(pass ? "text-foreground" : "text-muted-foreground")}>{humanizeKey(key)}</span>
                        </div>
                      ))}
                    </div>
                  ) : null}

                  {/* HITL review gate. */}
                  {pending ? (
                    <div className="space-y-2 rounded-md border border-warning/40 bg-warning/5 p-2.5">
                      <p className="text-xs font-medium text-foreground">Human-in-the-loop review required</p>
                      <Input
                        value={reasonByHash[d.entry_hash] ?? ""}
                        onChange={(e) => setReasonByHash((m) => ({ ...m, [d.entry_hash]: e.target.value }))}
                        placeholder="Reason (optional)"
                        className="h-8 text-xs"
                        disabled={reviewBusyHash === d.entry_hash}
                      />
                      <div className="flex flex-wrap gap-2">
                        <Button
                          type="button"
                          size="sm"
                          className="gap-1.5"
                          disabled={reviewBusyHash === d.entry_hash}
                          onClick={() => void submitReview(d.entry_hash, true)}
                        >
                          {reviewBusyHash === d.entry_hash ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                          ) : (
                            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
                          )}
                          Approve
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="gap-1.5 border-destructive/40 text-destructive hover:bg-destructive/5"
                          disabled={reviewBusyHash === d.entry_hash}
                          onClick={() => void submitReview(d.entry_hash, false)}
                        >
                          <XCircle className="h-3.5 w-3.5" aria-hidden />
                          Reject
                        </Button>
                      </div>
                    </div>
                  ) : null}

                  {/* Hash chain — subtle tamper-evident provenance. */}
                  <p className="flex flex-wrap items-center gap-1.5 border-t pt-2 font-mono text-[10px] text-muted-foreground">
                    <span title={d.entry_hash}>entry {shortHash(d.entry_hash)}</span>
                    {d.previous_entry_hash ? (
                      <span className="inline-flex items-center gap-1" title={d.previous_entry_hash}>
                        <Link2 className="h-3 w-3" aria-hidden />
                        prev {shortHash(d.previous_entry_hash)}
                      </span>
                    ) : null}
                  </p>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </ModuleCard>
  )
}
