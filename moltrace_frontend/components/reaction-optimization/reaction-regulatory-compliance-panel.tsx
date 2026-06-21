"use client"

import { useEffect, useMemo, useState } from "react"
import { ChevronDown, Loader2, Scale, ShieldAlert, ShieldCheck } from "lucide-react"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Badge } from "@/components/ui/badge"
import { Collapsible, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { cn } from "@/lib/utils"
import {
  COMPLIANCE_STATUS,
  SEVERITY_BADGE_CLASS,
  getRegulatoryCompliance,
  itemStatus,
  type ComplianceItem,
  type ComplianceReport,
  type ComplianceViolation,
} from "@/lib/reaction/regulatory-compliance"

function fmtNum(v: number | null): string {
  return v == null ? "—" : String(v)
}

function ViolationDetail({ v }: { v: ComplianceViolation }) {
  const rule = [v.objectiveField ?? "value", v.comparator ?? "max", fmtNum(v.limitValue), v.limitUnit ?? ""]
    .filter(Boolean)
    .join(" ")
  return (
    <div className="rounded-md border bg-muted/20 p-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono font-medium">{rule}</span>
        {v.severity ? (
          <Badge
            variant="secondary"
            className={cn("uppercase", SEVERITY_BADGE_CLASS[v.severity] ?? "")}
          >
            {v.severity}
          </Badge>
        ) : null}
        <Badge variant="outline">{v.isHard ? "hard limit" : "soft limit"}</Badge>
      </div>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <dt className="text-muted-foreground">measured</dt>
        <dd className="font-mono">{fmtNum(v.predictedValue)}{v.limitUnit ? ` ${v.limitUnit}` : ""}</dd>
        {v.basis ? (
          <>
            <dt className="text-muted-foreground">basis</dt>
            <dd className="italic">{v.basis}</dd>
          </>
        ) : null}
        {v.sourceActionItemIds.length > 0 ? (
          <>
            <dt className="text-muted-foreground">source</dt>
            <dd>regulatory action item{v.sourceActionItemIds.length > 1 ? "s" : ""} {v.sourceActionItemIds.join(", ")}</dd>
          </>
        ) : null}
      </dl>
    </div>
  )
}

function ComplianceRow({ item }: { item: ComplianceItem }) {
  const [open, setOpen] = useState(false)
  const status = itemStatus(item)
  const meta = COMPLIANCE_STATUS[status]
  const hasDetail = item.violations.length > 0 || item.unmeasured.length > 0
  return (
    <>
      <TableRow>
        <TableCell className="font-mono text-sm">{item.experimentCode}</TableCell>
        <TableCell>
          <Badge variant="secondary" className={meta.badgeClass}>
            {meta.label}
          </Badge>
        </TableCell>
        <TableCell className="text-muted-foreground">{item.status}</TableCell>
        <TableCell className="text-right">
          {hasDetail ? (
            <Collapsible open={open} onOpenChange={setOpen}>
              <CollapsibleTrigger className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                {item.violations.length > 0
                  ? `${item.violations.length} violation${item.violations.length > 1 ? "s" : ""}`
                  : "details"}
                <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
              </CollapsibleTrigger>
            </Collapsible>
          ) : (
            <span className="text-xs text-muted-foreground">—</span>
          )}
        </TableCell>
      </TableRow>
      {open && hasDetail ? (
        <TableRow>
          <TableCell colSpan={4} className="bg-muted/10">
            <div className="space-y-2 py-1">
              {item.violations.map((v, i) => (
                <ViolationDetail key={i} v={v} />
              ))}
              {item.unmeasured.length > 0 ? (
                <p className="text-xs text-muted-foreground">
                  Not measured for this experiment (a limit existed, but the outcome had no value —
                  never counted as passing): {item.unmeasured.join(", ")}
                </p>
              ) : null}
            </div>
          </TableCell>
        </TableRow>
      ) : null}
    </>
  )
}

export function ReactionRegulatoryCompliancePanel({ reactionProjectId }: { reactionProjectId: number }) {
  const [report, setReport] = useState<ComplianceReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError("")
    getRegulatoryCompliance(reactionProjectId)
      .then((r) => {
        if (!cancelled) setReport(r)
      })
      .catch((e) => {
        if (!cancelled) setError(formatApiError(e, "Could not load regulatory-compliance evaluation."))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [reactionProjectId])

  const nonCompliant = report?.nonCompliantExperimentCount ?? 0
  const HeaderIcon = nonCompliant > 0 ? ShieldAlert : ShieldCheck

  const body = useMemo(() => {
    if (loading) {
      return (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Evaluating recorded outcomes…
        </p>
      )
    }
    if (error) {
      return <p className="text-sm text-destructive">{error}</p>
    }
    if (!report) return null

    return (
      <div className="space-y-4">
        <p className="text-xs text-muted-foreground">
          Recorded experiment outcomes checked against the project&rsquo;s active regulatory
          constraints that carry a numeric limit. Evaluated from measured results — not applied at
          recommendation time.
        </p>

        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-lg border p-3">
            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
              Experiments evaluated
            </p>
            <p className="mt-1 font-mono text-2xl font-bold tabular-nums">{report.experimentsEvaluated}</p>
          </div>
          <div className="rounded-lg border p-3">
            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
              Non-compliant experiments
            </p>
            <p
              className="mt-1 font-mono text-2xl font-bold tabular-nums"
              style={nonCompliant > 0 ? { color: "var(--mt-red, #dc2626)" } : undefined}
            >
              {nonCompliant}
            </p>
          </div>
          <div className="rounded-lg border p-3">
            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
              Limits enforced
            </p>
            <p className="mt-1 font-mono text-2xl font-bold tabular-nums">{report.enforcedConstraintCount}</p>
          </div>
        </div>

        {report.constraintBases.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-muted-foreground">Bases:</span>
            {report.constraintBases.map((b, i) => (
              <Badge key={i} variant="outline" className="font-normal">
                {b}
              </Badge>
            ))}
          </div>
        ) : null}

        {report.notes.length > 0 ? (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3">
            <ul className="space-y-0.5 text-xs text-amber-900 dark:text-amber-200">
              {report.notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {report.items.length > 0 ? (
          <div className="table-scroll">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>experiment</TableHead>
                  <TableHead>compliance</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead className="text-right">detail</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {report.items.map((item) => (
                  <ComplianceRow key={item.experimentId ?? item.experimentCode} item={item} />
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <Scale />
              </EmptyMedia>
              <EmptyTitle>Nothing to evaluate yet</EmptyTitle>
              <EmptyDescription>
                Record experiment outcomes and activate a regulatory constraint with a numeric limit
                to see compliance here.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        )}
      </div>
    )
  }, [loading, error, report, nonCompliant])

  return (
    <ModuleCard
      accent="cyan"
      eyebrow="Regulatory · Compliance"
      title="Outcome compliance vs active limits"
      icon={HeaderIcon}
      description="Enforced end of the Regentry → Repho loop"
    >
      {body}
    </ModuleCard>
  )
}
