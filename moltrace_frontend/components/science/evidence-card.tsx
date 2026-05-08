"use client"

import type { ReactNode } from "react"
import { AlertTriangle, CheckCircle2, Clock, Eye, ShieldAlert, XCircle } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn, formatStableUtcDateTime } from "@/lib/utils"

export type EvidenceModule = "spectracheck" | "regulatory" | "reactions" | "ai_services"

export type EvidenceStatus =
  | "draft"
  | "pending_review"
  | "approved"
  | "rejected"
  | "contradiction"
  | "unavailable"

export type EvidenceRiskLevel = "low" | "medium" | "high" | "critical" | "unknown"

type EvidenceCitation =
  | string
  | {
      id?: string | number
      label?: string
      ref?: string
      title?: string
      source?: string
      url?: string
      type?: string
    }

export type EvidenceCardProps = {
  title: ReactNode
  module: EvidenceModule
  status: EvidenceStatus
  confidence_score?: number | string | null
  confidence_label?: string | null
  risk_level?: EvidenceRiskLevel | null
  summary?: ReactNode
  evidence_items?: unknown[] | null
  contradictions?: unknown[] | null
  citations?: EvidenceCitation[] | null
  model_name?: string | null
  model_version?: string | null
  last_updated_at?: string | null
  reviewer_name?: string | null
  review_status?: string | null
  onApprove?: () => void
  onReject?: () => void
  onOpenDetails?: () => void
  className?: string
  compact?: boolean
}

const SENSITIVE_KEY_PATTERN =
  /(prompt|chain[_\s-]?of[_\s-]?thought|\bcot\b|reasoning_trace|secret|api[_-]?key|token|credential|password|authorization|bearer|service[_-]?account|private[_-]?key)/i

const SENSITIVE_TEXT_PATTERN =
  /\b(system prompt|developer prompt|chain of thought|chain-of-thought|api key|bearer token|service credential|private key)\b/i

function moduleLabel(module: EvidenceModule): string {
  switch (module) {
    case "spectracheck":
      return "SpectraCheck"
    case "regulatory":
      return "Regulatory Hub"
    case "reactions":
      return "Reaction Optimization"
    case "ai_services":
      return "AI Services"
    default:
      return module
  }
}

function statusLabel(status: EvidenceStatus): string {
  switch (status) {
    case "pending_review":
      return "Pending review"
    case "approved":
      return "Approved"
    case "rejected":
      return "Rejected"
    case "contradiction":
      return "Contradiction"
    case "unavailable":
      return "Unavailable"
    case "draft":
    default:
      return "Draft"
  }
}

function statusBadgeClass(status: EvidenceStatus): string {
  switch (status) {
    case "approved":
      return "border-success/50 bg-success/10 text-success"
    case "rejected":
      return "border-destructive/50 bg-destructive/10 text-destructive"
    case "contradiction":
      return "border-warning/60 bg-warning/10 text-warning-foreground"
    case "pending_review":
      return "border-primary/40 bg-primary/10 text-primary"
    case "unavailable":
      return "border-muted-foreground/30 text-muted-foreground"
    case "draft":
    default:
      return "border-border text-muted-foreground"
  }
}

function riskBadgeClass(risk: EvidenceRiskLevel): string {
  switch (risk) {
    case "low":
      return "border-success/50 text-success"
    case "medium":
      return "border-warning/50 text-warning-foreground"
    case "high":
      return "border-orange-500/60 text-orange-700 dark:text-orange-300"
    case "critical":
      return "border-destructive/60 bg-destructive/10 text-destructive"
    case "unknown":
    default:
      return "border-muted-foreground/30 text-muted-foreground"
  }
}

function statusIcon(status: EvidenceStatus) {
  switch (status) {
    case "approved":
      return <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
    case "rejected":
      return <XCircle className="h-3.5 w-3.5" aria-hidden />
    case "contradiction":
      return <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
    case "pending_review":
      return <Clock className="h-3.5 w-3.5" aria-hidden />
    case "unavailable":
      return <ShieldAlert className="h-3.5 w-3.5" aria-hidden />
    case "draft":
    default:
      return null
  }
}

function parseConfidence(value: EvidenceCardProps["confidence_score"]): number | null {
  if (value == null || value === "") return null
  const n = typeof value === "number" ? value : Number(value)
  if (!Number.isFinite(n)) return null
  const pct = n >= 0 && n <= 1 ? n * 100 : n
  return Math.max(0, Math.min(100, pct))
}

function formatDate(value: string | null | undefined): string | null {
  if (!value?.trim()) return null
  return formatStableUtcDateTime(value, "")
}

function truncate(value: string, max = 220): string {
  const clean = value.replace(/\s+/g, " ").trim()
  if (clean.length <= max) return clean
  return `${clean.slice(0, max - 1).trim()}...`
}

function primitiveToSafeText(value: unknown): string | null {
  if (value == null) return null
  if (typeof value === "string") {
    const clean = value.trim()
    if (!clean) return null
    if (SENSITIVE_TEXT_PATTERN.test(clean)) return "Redacted internal evidence metadata."
    return truncate(clean)
  }
  if (typeof value === "number" || typeof value === "boolean") return String(value)
  return null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function evidenceItemText(item: unknown): string {
  const direct = primitiveToSafeText(item)
  if (direct) return direct
  if (!isRecord(item)) return "Evidence metadata attached."

  for (const key of ["summary", "label", "title", "finding", "message", "description", "status", "value"]) {
    if (SENSITIVE_KEY_PATTERN.test(key)) continue
    const value = primitiveToSafeText(item[key])
    if (value) return value
  }

  const safePairs = Object.entries(item)
    .filter(([key, value]) => !SENSITIVE_KEY_PATTERN.test(key) && primitiveToSafeText(value))
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${primitiveToSafeText(value)}`)

  return safePairs.length ? truncate(safePairs.join(" | ")) : "Evidence metadata attached."
}

function citationText(citation: EvidenceCitation): { label: string; href?: string } {
  if (typeof citation === "string") return { label: truncate(citation) }
  const label =
    primitiveToSafeText(citation.label) ??
    primitiveToSafeText(citation.ref) ??
    primitiveToSafeText(citation.title) ??
    primitiveToSafeText(citation.source) ??
    (citation.id != null ? `Citation ${citation.id}` : "Citation attached")
  const href = typeof citation.url === "string" && /^https?:\/\//i.test(citation.url) ? citation.url : undefined
  return { label, href }
}

function safeSummaryNode(summary: ReactNode): ReactNode {
  if (typeof summary === "string") return primitiveToSafeText(summary) ?? "Evidence summary unavailable."
  if (typeof summary === "number" || typeof summary === "boolean") return String(summary)
  return summary
}

export function EvidenceCard({
  title,
  module,
  status,
  confidence_score,
  confidence_label,
  risk_level = "unknown",
  summary,
  evidence_items,
  contradictions,
  citations,
  model_name,
  model_version,
  last_updated_at,
  reviewer_name,
  review_status,
  onApprove,
  onReject,
  onOpenDetails,
  className,
  compact = false,
}: EvidenceCardProps) {
  const confidence = parseConfidence(confidence_score)
  const normalizedRisk = risk_level ?? "unknown"
  const evidenceItems = Array.isArray(evidence_items) ? evidence_items : []
  const contradictionItems = Array.isArray(contradictions) ? contradictions : []
  const citationItems = Array.isArray(citations) ? citations : []
  const updated = formatDate(last_updated_at)
  const hasActions = Boolean(onApprove || onReject || onOpenDetails)

  return (
    <Card className={cn("min-w-0 border-muted", compact && "gap-3 py-4", className)}>
      <CardHeader className={cn("space-y-2", compact ? "px-4 pb-1" : "pb-3")}>
        <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
          <div className="min-w-0 space-y-1">
            <CardTitle className={cn("min-w-0 leading-snug", compact ? "text-sm" : "text-base")}>{title}</CardTitle>
            <CardDescription className="flex flex-wrap items-center gap-1.5 text-xs">
              <Badge variant="outline" className="font-normal">
                {moduleLabel(module)}
              </Badge>
              <Badge variant="outline" className={cn("gap-1 font-normal", statusBadgeClass(status))}>
                {statusIcon(status)}
                {statusLabel(status)}
              </Badge>
              <Badge variant="outline" className={cn("font-normal capitalize", riskBadgeClass(normalizedRisk))}>
                Risk: {normalizedRisk}
              </Badge>
            </CardDescription>
          </div>
        </div>
      </CardHeader>

      <CardContent className={cn("min-w-0 space-y-4", compact && "px-4")}>
        {status === "pending_review" ? (
          <Alert className="border-primary/30 bg-primary/5 py-2">
            <Clock className="h-4 w-4" aria-hidden />
            <AlertTitle className="text-sm">Human review required.</AlertTitle>
          </Alert>
        ) : null}

        {status === "contradiction" ? (
          <Alert className="border-warning/50 bg-warning/10 py-2">
            <AlertTriangle className="h-4 w-4 text-warning" aria-hidden />
            <AlertTitle className="text-sm">Contradiction warning</AlertTitle>
            <AlertDescription className="text-xs">
              Review conflicting evidence before using this result for decisions.
            </AlertDescription>
          </Alert>
        ) : null}

        {summary ? (
          <div className="text-sm leading-relaxed text-muted-foreground">{safeSummaryNode(summary)}</div>
        ) : null}

        <div className="rounded-md border bg-muted/20 px-3 py-2">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Estimated confidence
              </p>
              <p className="mt-1 font-mono text-xl font-semibold tabular-nums">
                {confidence == null ? "Confidence unavailable." : `${confidence.toFixed(confidence % 1 === 0 ? 0 : 1)}%`}
              </p>
            </div>
            {confidence_label ? (
              <Badge variant="secondary" className="shrink-0 capitalize">
                {confidence_label}
              </Badge>
            ) : null}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Model estimate only. Treat as decision support, not absolute truth.
          </p>
        </div>

        {compact ? null : (
          <Tabs defaultValue="evidence" className="min-w-0">
            <TabsList className="w-full justify-start">
              <TabsTrigger value="evidence">Evidence</TabsTrigger>
              <TabsTrigger value="citations">Citations</TabsTrigger>
            </TabsList>
            <TabsContent value="evidence" className="mt-3 space-y-3">
              {evidenceItems.length > 0 ? (
                <ul className="space-y-2 text-sm">
                  {evidenceItems.slice(0, 6).map((item, index) => (
                    <li key={index} className="rounded-md border bg-card px-3 py-2 text-muted-foreground">
                      {evidenceItemText(item)}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground">
                  No evidence items attached.
                </p>
              )}
              {contradictionItems.length > 0 ? (
                <div className="space-y-2">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Contradictions</p>
                  <ul className="space-y-2 text-sm">
                    {contradictionItems.slice(0, 4).map((item, index) => (
                      <li key={index} className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2">
                        {evidenceItemText(item)}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </TabsContent>
            <TabsContent value="citations" className="mt-3">
              {citationItems.length > 0 ? (
                <ul className="space-y-2 text-sm">
                  {citationItems.slice(0, 6).map((citation, index) => {
                    const c = citationText(citation)
                    return (
                      <li key={index} className="flex min-w-0 items-start gap-2 rounded-md border bg-card px-3 py-2">
                        <Badge variant="outline" className="shrink-0 font-mono text-[10px]">
                          {index + 1}
                        </Badge>
                        {c.href ? (
                          <a
                            href={c.href}
                            target="_blank"
                            rel="noreferrer"
                            className="min-w-0 break-words text-muted-foreground underline-offset-4 hover:underline"
                          >
                            {c.label}
                          </a>
                        ) : (
                          <span className="min-w-0 break-words text-muted-foreground">{c.label}</span>
                        )}
                      </li>
                    )
                  })}
                </ul>
              ) : (
                <p className="rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground">
                  No citations attached.
                </p>
              )}
            </TabsContent>
          </Tabs>
        )}

        {compact ? (
          <p className="text-xs text-muted-foreground">
            {citationItems.length > 0 ? `${citationItems.length} citations attached.` : "No citations attached."}
          </p>
        ) : null}

        <Separator />

        <div className="grid gap-1.5 text-xs text-muted-foreground sm:grid-cols-2">
          {model_name ? (
            <p>
              <span className="text-foreground/80">Model: </span>
              {model_name}
            </p>
          ) : null}
          {model_version ? (
            <p>
              <span className="text-foreground/80">Version: </span>
              {model_version}
            </p>
          ) : null}
          {reviewer_name ? (
            <p>
              <span className="text-foreground/80">Reviewer: </span>
              {reviewer_name}
            </p>
          ) : null}
          {review_status ? (
            <p>
              <span className="text-foreground/80">Review: </span>
              {review_status}
            </p>
          ) : null}
          {updated ? (
            <p className="sm:col-span-2">
              <span className="text-foreground/80">Updated: </span>
              {updated}
            </p>
          ) : null}
        </div>
      </CardContent>

      {hasActions ? (
        <CardFooter className={cn("flex flex-wrap gap-2", compact && "px-4 pt-1")}>
          {onApprove ? (
            <Button type="button" size="sm" onClick={onApprove}>
              Approve
            </Button>
          ) : null}
          {onReject ? (
            <Button type="button" size="sm" variant="outline" onClick={onReject}>
              Reject
            </Button>
          ) : null}
          {onOpenDetails ? (
            <Button type="button" size="sm" variant="secondary" onClick={onOpenDetails}>
              <Eye className="h-4 w-4" aria-hidden />
              View details
            </Button>
          ) : null}
        </CardFooter>
      ) : null}
    </Card>
  )
}
