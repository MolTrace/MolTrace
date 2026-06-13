"use client"

import Link from "next/link"
import { useCallback, useEffect, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

type Row = Record<string, unknown>
type BadgeVariant = "default" | "secondary" | "destructive" | "outline"
type ModuleScope = "spectracheck" | "regulatory_hub" | "reaction_optimization"

type Snapshot = {
  loading: boolean
  partial: boolean
  error: string
  projects: Row[]
  signatures: Row[]
  controlledRecords: Row[]
  dataIntegrityAssessments: Row[]
  deviations: Row[]
  capa: Row[]
}

const EMPTY_SNAPSHOT: Snapshot = {
  loading: true,
  partial: false,
  error: "",
  projects: [],
  signatures: [],
  controlledRecords: [],
  dataIntegrityAssessments: [],
  deviations: [],
  capa: [],
}

function isRecord(value: unknown): value is Row {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function asRows(payload: unknown, keys: string[] = []): Row[] {
  if (Array.isArray(payload)) return payload.filter(isRecord)
  if (!isRecord(payload)) return []
  for (const key of [...keys, "items", "results", "rows", "data"]) {
    const value = payload[key]
    if (Array.isArray(value)) return value.filter(isRecord)
  }
  return []
}

function readStr(value: unknown): string {
  if (typeof value === "string" && value.trim()) return value.trim()
  if (typeof value === "number" && Number.isFinite(value)) return String(value)
  if (typeof value === "boolean") return String(value)
  return ""
}

function readStatus(row: Row | null | undefined): string {
  return readStr(row?.status ?? row?.assessment_status ?? row?.package_status ?? row?.approval_status)
}

function readMetadata(row: Row | null | undefined): Row {
  return isRecord(row?.metadata_json) ? row.metadata_json : {}
}

function readNumber(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) return value
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) return Number(value)
  return 0
}

function textHaystack(row: Row): string {
  const meta = readMetadata(row)
  return [
    row.record_type,
    row.resource_id,
    row.title,
    row.description,
    row.source_type,
    row.source_id,
    meta.module,
    meta.scope,
    meta.resource_type,
    meta.target_type,
  ]
    .map(readStr)
    .filter(Boolean)
    .join(" ")
    .toLowerCase()
}

function statusVariant(status: string): BadgeVariant {
  if (status === "approved" || status === "pass" || status === "locked" || status === "closed" || status === "resolved") {
    return "default"
  }
  if (
    status === "fail" ||
    status === "failed" ||
    status === "error" ||
    status === "rejected" ||
    status === "canceled" ||
    status === "critical"
  ) {
    return "destructive"
  }
  if (
    status === "warning" ||
    status === "requires_review" ||
    status === "ready_for_qa_review" ||
    status === "in_review" ||
    status === "investigation" ||
    status === "in_progress" ||
    status === "effectiveness_check"
  ) {
    return "secondary"
  }
  return "outline"
}

function formatCount(snapshot: Snapshot, count: number): string {
  if (snapshot.loading) return "..."
  if (snapshot.error && !snapshot.partial) return "-"
  return String(count)
}

function formatErr(err: unknown): string {
  if (err instanceof ApiError) return err.message || "Validation readiness endpoint unavailable."
  if (err instanceof Error) return err.message
  return "Validation readiness endpoint unavailable."
}

function latestByDate(rows: Row[], dateKey = "updated_at"): Row | null {
  if (!rows.length) return null
  return [...rows].sort((a, b) => {
    const aDate = Date.parse(readStr(a[dateKey] ?? a.created_at ?? a.signed_at))
    const bDate = Date.parse(readStr(b[dateKey] ?? b.created_at ?? b.signed_at))
    return (Number.isNaN(bDate) ? 0 : bDate) - (Number.isNaN(aDate) ? 0 : aDate)
  })[0] ?? null
}

function countByStatus(rows: Row[], statuses: string[]): number {
  return rows.filter((row) => statuses.includes(readStatus(row))).length
}

function moduleProjects(projects: Row[], scope: ModuleScope): Row[] {
  return projects.filter((project) => {
    const projectScope = readStr(project.scope)
    return projectScope === scope || projectScope === "cross_module" || projectScope === "full_platform"
  })
}

function failedValidationTestsFromProjects(projects: Row[]): number {
  return projects.reduce((total, project) => {
    const meta = readMetadata(project)
    return (
      total +
      readNumber(meta.failed_validation_tests) +
      readNumber(meta.failed_tests) +
      readNumber(meta.failed_test_count)
    )
  }, 0)
}

function openDeviations(deviations: Row[]): Row[] {
  return deviations.filter((deviation) => {
    const status = readStatus(deviation)
    return status !== "closed" && status !== "resolved" && status !== "rejected"
  })
}

function openCapa(capa: Row[]): Row[] {
  return capa.filter((record) => {
    const status = readStatus(record)
    return status !== "closed" && status !== "canceled"
  })
}

function pendingSignatureTargets(snapshot: Snapshot): number {
  return (
    countByStatus(snapshot.projects, ["ready_for_qa_review"]) +
    countByStatus(snapshot.controlledRecords, ["in_review"])
  )
}

function coverageBadge(projects: Row[]): { label: string; variant: BadgeVariant } {
  if (projects.some((project) => readStatus(project) === "approved")) {
    return { label: "approved status present", variant: "default" }
  }
  if (projects.some((project) => readStatus(project) === "ready_for_qa_review")) {
    return { label: "requires QA review", variant: "secondary" }
  }
  if (projects.some((project) => readStatus(project) === "in_progress")) {
    return { label: "in progress", variant: "secondary" }
  }
  if (projects.some((project) => readStatus(project) === "draft")) {
    return { label: "draft coverage", variant: "outline" }
  }
  return { label: "no validation project coverage", variant: "outline" }
}

function recordsByType(records: Row[], types: string[]): Row[] {
  return records.filter((record) => types.includes(readStr(record.record_type)))
}

function recordsByText(records: Row[], patterns: RegExp[]): Row[] {
  return records.filter((record) => patterns.some((pattern) => pattern.test(textHaystack(record))))
}

function recordStatusSummary(records: Row[]): { label: string; variant: BadgeVariant; version: string } {
  const latest = latestByDate(records)
  const version = readStr(latest?.version) || "-"
  if (!records.length) return { label: "no controlled record", variant: "outline", version }
  if (records.some((record) => readStatus(record) === "locked")) return { label: "locked", variant: "default", version }
  if (records.some((record) => readStatus(record) === "approved")) return { label: "approved", variant: "default", version }
  if (records.some((record) => readStatus(record) === "in_review")) {
    return { label: "in review", variant: "secondary", version }
  }
  return { label: readStatus(latest) || "draft", variant: statusVariant(readStatus(latest)), version }
}

function latestAssessmentStatus(rows: Row[], scope?: string, scopeId?: string | null): { label: string; variant: BadgeVariant } {
  const scoped = rows.filter((assessment) => {
    const assessmentScope = readStr(assessment.scope)
    if (scope && assessmentScope !== scope) return false
    if (!scopeId) return true
    return readStr(assessment.scope_id) === scopeId
  })
  const latest = latestByDate(scoped, "created_at")
  const status = readStr(latest?.assessment_status)
  if (!status) return { label: "not run", variant: "outline" }
  return { label: status, variant: statusVariant(status) }
}

function latestSignatureLabel(rows: Row[]): { label: string; variant: BadgeVariant } {
  if (!rows.length) return { label: "no e-signature record", variant: "outline" }
  const latest = latestByDate(rows, "signed_at")
  const meaning = readStr(latest?.signature_meaning)
  if (meaning === "approved" || meaning === "released") return { label: meaning, variant: "default" }
  if (meaning === "rejected" || meaning === "override") return { label: meaning, variant: "destructive" }
  return { label: meaning || "recorded", variant: "secondary" }
}

function inspectionReadiness(snapshot: Snapshot): { label: string; variant: BadgeVariant } {
  if (openDeviations(snapshot.deviations).length || openCapa(snapshot.capa).length) {
    return { label: "review required", variant: "secondary" }
  }
  if (snapshot.controlledRecords.length && snapshot.signatures.length) {
    return { label: "ready to assemble", variant: "secondary" }
  }
  return { label: "not started", variant: "outline" }
}

function moduleIssueRows(rows: Row[], modulePattern: RegExp): Row[] {
  return rows.filter((row) => modulePattern.test(textHaystack(row)))
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-md border bg-muted/20 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-bold tabular-nums">{value}</p>
      {detail ? <p className="mt-1 text-xs text-muted-foreground">{detail}</p> : null}
    </div>
  )
}

function StatusLine({ label, status, detail }: { label: string; status: string; detail?: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-md border bg-muted/20 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <div>
        <Badge variant={statusVariant(status)}>{status || "-"}</Badge>
      </div>
      {detail ? <p className="text-xs text-muted-foreground">{detail}</p> : null}
    </div>
  )
}

function StatusBadgeLine({
  label,
  badge,
  detail,
}: {
  label: string
  badge: { label: string; variant: BadgeVariant }
  detail?: string
}) {
  return (
    <div className="flex flex-col gap-1 rounded-md border bg-muted/20 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <div>
        <Badge variant={badge.variant}>{badge.label}</Badge>
      </div>
      {detail ? <p className="text-xs text-muted-foreground">{detail}</p> : null}
    </div>
  )
}

function useValidationReadinessSnapshot(): Snapshot {
  const [snapshot, setSnapshot] = useState<Snapshot>(EMPTY_SNAPSHOT)

  const load = useCallback(async () => {
    setSnapshot((current) => ({ ...current, loading: true, error: "" }))
    const requests = await Promise.allSettled([
      apiFetch<unknown>("/validation-center/projects", { method: "GET" }),
      apiFetch<unknown>("/esignatures/records", { method: "GET" }),
      apiFetch<unknown>("/controlled-records", { method: "GET" }),
      apiFetch<unknown>("/data-integrity/assessments", { method: "GET" }),
      apiFetch<unknown>("/deviations", { method: "GET" }),
      apiFetch<unknown>("/capa", { method: "GET" }),
    ])

    const failures = requests.filter((request) => request.status === "rejected")
    setSnapshot({
      loading: false,
      partial: failures.length > 0 && failures.length < requests.length,
      error: failures.length === requests.length ? formatErr(failures[0]?.reason) : "",
      projects: requests[0]?.status === "fulfilled" ? asRows(requests[0].value, ["validation_projects", "projects"]) : [],
      signatures: requests[1]?.status === "fulfilled" ? asRows(requests[1].value, ["esignatures", "esignature_records", "records"]) : [],
      controlledRecords: requests[2]?.status === "fulfilled" ? asRows(requests[2].value, ["controlled_records", "records"]) : [],
      dataIntegrityAssessments:
        requests[3]?.status === "fulfilled" ? asRows(requests[3].value, ["data_integrity_assessments", "assessments"]) : [],
      deviations: requests[4]?.status === "fulfilled" ? asRows(requests[4].value, ["deviations", "deviation_records"]) : [],
      capa: requests[5]?.status === "fulfilled" ? asRows(requests[5].value, ["capa", "capa_records"]) : [],
    })
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return snapshot
}

export function ValidationReadinessDashboardCards() {
  const snapshot = useValidationReadinessSnapshot()
  const activeProjects = snapshot.projects.filter((project) => readStatus(project) !== "archived")
  const moduleBadges = [
    ["SpectraCheck", moduleProjects(snapshot.projects, "spectracheck")],
    ["ComplianceCore", moduleProjects(snapshot.projects, "regulatory_hub")],
    ["Reaction Optimization", moduleProjects(snapshot.projects, "reaction_optimization")],
  ] as const

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Validation readiness</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="text-2xl font-bold tabular-nums">{formatCount(snapshot, activeProjects.length)}</div>
          <p className="text-xs text-muted-foreground">Active validation project records.</p>
          <div className="flex flex-wrap gap-1">
            {moduleBadges.map(([label, rows]) => {
              const badge = coverageBadge(rows)
              return (
                <Badge key={label} variant={badge.variant} className="font-normal">
                  {label}: {rows.length}
                </Badge>
              )
            })}
          </div>
          {snapshot.partial ? <p className="text-xs text-muted-foreground">Some readiness endpoints unavailable.</p> : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">open deviations</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold tabular-nums">{formatCount(snapshot, openDeviations(snapshot.deviations).length)}</div>
          <p className="text-xs text-muted-foreground">Open deviations — excludes closed, resolved, and rejected.</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">open CAPA</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold tabular-nums">{formatCount(snapshot, openCapa(snapshot.capa).length)}</div>
          <p className="text-xs text-muted-foreground">Open CAPA entries — excludes closed and canceled.</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">failed validation tests</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold tabular-nums">
            {formatCount(snapshot, failedValidationTestsFromProjects(snapshot.projects))}
          </div>
          <p className="text-xs text-muted-foreground">From validation project metadata when present.</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">pending signatures</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold tabular-nums">{formatCount(snapshot, pendingSignatureTargets(snapshot))}</div>
          <p className="text-xs text-muted-foreground">Review targets that may need e-signature records.</p>
        </CardContent>
      </Card>
    </div>
  )
}

export function SpectraCheckValidationReadinessCard({ sessionId }: { sessionId?: string | null }) {
  const snapshot = useValidationReadinessSnapshot()
  const projects = moduleProjects(snapshot.projects, "spectracheck")
  const coverage = coverageBadge(projects)
  const reportStatus = recordStatusSummary(recordsByType(snapshot.controlledRecords, ["report", "validation_result"]))
  const dataIntegrity = latestAssessmentStatus(snapshot.dataIntegrityAssessments, "spectracheck_session", sessionId)

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Validation readiness</CardTitle>
        <CardDescription>Compact readiness signals from Validation Center records.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-3 md:grid-cols-3">
          <StatusBadgeLine
            label="validation coverage badge"
            badge={coverage}
            detail={`${projects.length} SpectraCheck validation project record(s).`}
          />
          <StatusBadgeLine
            label="controlled record status for reports"
            badge={{ label: reportStatus.label, variant: reportStatus.variant }}
            detail={`Latest controlled record version: ${reportStatus.version}.`}
          />
          <StatusBadgeLine
            label="data integrity status for session"
            badge={dataIntegrity}
            detail={sessionId ? `scope_id ${sessionId}` : "No session ID selected."}
          />
        </div>
        <p className="text-xs text-muted-foreground">
          Readiness summaries do not mark a session validated unless an approved backend status exists.
        </p>
      </CardContent>
    </Card>
  )
}

export function RegulatoryHubValidationReadinessCard() {
  const snapshot = useValidationReadinessSnapshot()
  const dossierStatus = recordStatusSummary(recordsByType(snapshot.controlledRecords, ["regulatory_dossier", "ctd_bundle"]))
  const signatureStatus = latestSignatureLabel(snapshot.signatures)
  const packageReadiness = inspectionReadiness(snapshot)

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Validation readiness</CardTitle>
        <CardDescription>Controlled dossier, e-signature, and inspection package readiness signals.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-3 md:grid-cols-3">
          <StatusBadgeLine
            label="controlled dossier status"
            badge={{ label: dossierStatus.label, variant: dossierStatus.variant }}
            detail={`Latest controlled record version: ${dossierStatus.version}.`}
          />
          <StatusBadgeLine
            label="e-signature status"
            badge={signatureStatus}
            detail={`${snapshot.signatures.length} e-signature record(s) returned.`}
          />
          <StatusBadgeLine
            label="inspection package readiness"
            badge={packageReadiness}
            detail="Based on controlled records, signatures, deviations, and CAPA state."
          />
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link href="/validation-center/inspection-package">Open inspection package workspace</Link>
        </Button>
      </CardContent>
    </Card>
  )
}

export function ReactionValidationReadinessCard() {
  const snapshot = useValidationReadinessSnapshot()
  const reactionProjects = moduleProjects(snapshot.projects, "reaction_optimization")
  const workflowCoverage = coverageBadge(reactionProjects)
  const experimentStatus = recordStatusSummary(recordsByText(snapshot.controlledRecords, [/reaction/, /experiment/]))
  const reactionDeviations = moduleIssueRows(openDeviations(snapshot.deviations), /reaction|optimization|execution/)

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Validation readiness</CardTitle>
        <CardDescription>Controlled experiment records, validation workflow status, and deviation links.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-3 md:grid-cols-3">
          <StatusBadgeLine
            label="controlled experiment record status"
            badge={{ label: experimentStatus.label, variant: experimentStatus.variant }}
            detail={`Latest controlled record version: ${experimentStatus.version}.`}
          />
          <StatusBadgeLine
            label="validated optimization workflow status"
            badge={workflowCoverage}
            detail={`${reactionProjects.length} Reaction Optimization validation project record(s).`}
          />
          <Metric
            label="deviation links"
            value={formatCount(snapshot, reactionDeviations.length)}
            detail="Open deviations mentioning reaction, optimization, or execution."
          />
        </div>
        <p className="text-xs text-muted-foreground">
          The workflow status mirrors backend validation project status and does not imply an optimum.
        </p>
      </CardContent>
    </Card>
  )
}

export function ReportsValidationReadinessCard() {
  const snapshot = useValidationReadinessSnapshot()
  const reportStatus = recordStatusSummary(recordsByType(snapshot.controlledRecords, ["report", "validation_result"]))
  const signatureStatus = latestSignatureLabel(snapshot.signatures)
  const releaseStatus = reportStatus.label === "approved" || reportStatus.label === "locked" ? reportStatus.label : "review required"

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Validation readiness</CardTitle>
        <CardDescription>Controlled report version, e-signature records, inspection package link, and release status.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-3 md:grid-cols-4">
          <StatusLine
            label="controlled record version"
            status={reportStatus.version}
            detail={`Controlled record status: ${reportStatus.label}.`}
          />
          <StatusBadgeLine
            label="signatures"
            badge={signatureStatus}
            detail={`${snapshot.signatures.length} e-signature record(s) returned.`}
          />
          <div className="rounded-md border bg-muted/20 p-3">
            <p className="text-xs text-muted-foreground">inspection package link</p>
            <Button variant="outline" size="sm" className="mt-2" asChild>
              <Link href="/validation-center/inspection-package">Open package</Link>
            </Button>
          </div>
          <StatusLine
            label="release status"
            status={releaseStatus}
            detail="Shows approved only when controlled record status is approved."
          />
        </div>
      </CardContent>
    </Card>
  )
}
