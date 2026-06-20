"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import {
  trackRegulatoryChangeDetectedViewed,
  trackRegulatoryImpactAssessmentRun,
} from "@/src/lib/analytics/analytics-client"
import { apiFetch } from "@/lib/api/client"
import { formatStableUtcDateTime } from "@/lib/utils"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { DeveloperOnly } from "@/components/developer-mode-provider"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import {
  ArrowLeft,
  ClipboardList,
  FileSearch,
  FileText,
  GitBranch,
  Layers3,
  ListChecks,
  Loader2,
  Network,
  ScrollText,
  Tag,
} from "lucide-react"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function asArray(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (data && typeof data === "object") {
    const o = data as Record<string, unknown>
    if (Array.isArray(o.items)) return o.items
    if (Array.isArray(o.results)) return o.results
  }
  return []
}

function formatWhen(iso: string | undefined): string {
  return formatStableUtcDateTime(iso)
}

function readStringList(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.filter((x): x is string => typeof x === "string" && x.trim().length > 0)
}

function readIntList(v: unknown): number[] {
  if (!Array.isArray(v)) return []
  return v.filter((x): x is number => typeof x === "number" && Number.isFinite(x))
}

export function RegulatoryChangeDetailWorkspace({ changeId }: { changeId: number }) {
  const changeViewedForId = useRef<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadErr, setLoadErr] = useState("")
  const [change, setChange] = useState<Record<string, unknown> | null>(null)
  const [oldVersion, setOldVersion] = useState<Record<string, unknown> | null>(null)
  const [newVersion, setNewVersion] = useState<Record<string, unknown> | null>(null)
  const [impactRows, setImpactRows] = useState<Record<string, unknown>[]>([])
  const [proposalRows, setProposalRows] = useState<Record<string, unknown>[]>([])
  const [dossiers, setDossiers] = useState<Record<string, unknown>[]>([])
  const [actionItems, setActionItems] = useState<Record<string, unknown>[]>([])
  const [jurisdictions, setJurisdictions] = useState<Record<string, unknown>[]>([])
  const [impactBusy, setImpactBusy] = useState(false)
  const [impactErr, setImpactErr] = useState("")
  const [impactOk, setImpactOk] = useState("")

  const [reviewerName, setReviewerName] = useState("")
  const [reviewDecision, setReviewDecision] = useState("in_review")
  const [reviewRationale, setReviewRationale] = useState("")
  const [reviewBusy, setReviewBusy] = useState(false)
  const [reviewErr, setReviewErr] = useState("")
  const [reviewOk, setReviewOk] = useState("")

  const load = useCallback(async () => {
    if (!Number.isFinite(changeId) || changeId < 1) {
      setLoading(false)
      setLoadErr("Invalid change id.")
      setChange(null)
      return
    }
    setLoading(true)
    setLoadErr("")
    try {
      const cRaw = await apiFetch<unknown>(`/regulatory/changes/${changeId}`, { method: "GET" })
      const c = isRecord(cRaw) ? cRaw : null
      setChange(c)
      const srcId = c ? readRecordNumber(c, "source_id") : null
      const oldVerId = c ? readRecordNumber(c, "old_version_id") : null
      const newVerId = c ? readRecordNumber(c, "new_version_id") : null

      const [impactRaw, proposalsRaw, oldRaw, newRaw, dossiersRaw, actionItemsRaw, jurisdictionsRaw] = await Promise.all([
        apiFetch<unknown>(`/regulatory/changes/${changeId}/impact-assessment`, { method: "GET" }).catch(() => []),
        apiFetch<unknown>("/regulatory/rule-update-proposals?limit=500", { method: "GET" }).catch(() => []),
        srcId != null && oldVerId != null
          ? apiFetch<unknown>(`/regulatory/sources/${srcId}/versions/${oldVerId}`, { method: "GET" }).catch(() => null)
          : Promise.resolve(null),
        srcId != null && newVerId != null
          ? apiFetch<unknown>(`/regulatory/sources/${srcId}/versions/${newVerId}`, { method: "GET" }).catch(() => null)
          : Promise.resolve(null),
        apiFetch<unknown>("/regulatory/dossiers?limit=500", { method: "GET" }).catch(() => []),
        apiFetch<unknown>("/regulatory/action-items?limit=500", { method: "GET" }).catch(() => []),
        apiFetch<unknown>("/regulatory/jurisdictions", { method: "GET" }).catch(() => []),
      ])

      setImpactRows(asArray(impactRaw).filter(isRecord) as Record<string, unknown>[])
      const allProps = asArray(proposalsRaw).filter(isRecord) as Record<string, unknown>[]
      setProposalRows(allProps.filter((row) => readRecordNumber(row, "change_event_id") === changeId))
      setOldVersion(isRecord(oldRaw) ? oldRaw : null)
      setNewVersion(isRecord(newRaw) ? newRaw : null)
      setDossiers(asArray(dossiersRaw).filter(isRecord) as Record<string, unknown>[])
      setActionItems(asArray(actionItemsRaw).filter(isRecord) as Record<string, unknown>[])
      setJurisdictions(asArray(jurisdictionsRaw).filter(isRecord) as Record<string, unknown>[])

      if (c) {
        const st = readRecordString(c, "review_status")
        if (st === "accepted" || st === "rejected" || st === "deferred" || st === "in_review") {
          setReviewDecision(st)
        }
      }
    } catch (e) {
      setLoadErr(formatApiError(e, "Could not load change detail."))
      setChange(null)
      setImpactRows([])
      setProposalRows([])
      setOldVersion(null)
      setNewVersion(null)
      setDossiers([])
      setActionItems([])
      setJurisdictions([])
    } finally {
      setLoading(false)
    }
  }, [changeId])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (loading || !change) return
    if (changeViewedForId.current === changeId) return
    changeViewedForId.current = changeId
    trackRegulatoryChangeDetectedViewed({
      change_type: readRecordString(change, "change_type"),
      severity: readRecordString(change, "severity"),
      affected_dossier_count: readIntList(change?.affected_dossier_ids_json).length,
      affected_rule_count: readIntList(change?.affected_rule_set_ids_json).length,
    })
  }, [loading, change, changeId])

  const diffs = useMemo(() => {
    const raw = change?.diffs
    return asArray(raw).filter(isRecord) as Record<string, unknown>[]
  }, [change])

  async function saveReview() {
    const reviewer = reviewerName.trim()
    const rationale = reviewRationale.trim()
    setReviewErr("")
    setReviewOk("")
    if (!reviewer) {
      setReviewErr("reviewer name is required.")
      return
    }
    if (!rationale) {
      setReviewErr("rationale is required.")
      return
    }
    setReviewBusy(true)
    try {
      await apiFetch(`/regulatory/changes/${changeId}/review`, {
        method: "POST",
        body: {
          review_status: reviewDecision,
          reviewer_name: reviewer,
          reviewer_comment: rationale,
          metadata_json: {},
        },
      })
      setReviewOk("Change review saved.")
      await load()
    } catch (e) {
      setReviewErr(formatApiError(e, "Save change review failed."))
    } finally {
      setReviewBusy(false)
    }
  }

  const topicList = readStringList(change?.affected_topics_json)
  const affectedDossiers = readIntList(change?.affected_dossier_ids_json)
  const latestImpact = impactRows[0] ?? null
  const jurisdictionNameById = useMemo(() => {
    const m = new Map<number, string>()
    for (const row of jurisdictions) {
      const id = readRecordNumber(row, "id")
      const name = readRecordString(row, "name")
      if (id != null && name) m.set(id, name)
    }
    return m
  }, [jurisdictions])

  const impactedDossierIds = useMemo(() => readIntList(latestImpact?.impacted_dossiers_json), [latestImpact])
  const impactedRequirementIds = useMemo(
    () => readIntList(latestImpact?.impacted_requirements_json),
    [latestImpact],
  )
  const impactedActionItemIds = useMemo(
    () => readIntList(latestImpact?.impacted_action_items_json),
    [latestImpact],
  )
  const impactedRuleSetIds = useMemo(() => readIntList(latestImpact?.impacted_rule_sets_json), [latestImpact])
  const impactedAiGovIds = useMemo(
    () => readIntList(latestImpact?.impacted_ai_governance_records_json),
    [latestImpact],
  )
  const recommendedActions = useMemo(
    () => asArray(latestImpact?.recommended_actions_json).filter(isRecord) as Record<string, unknown>[],
    [latestImpact],
  )
  const warningLines = useMemo(() => readStringList(latestImpact?.warnings_json), [latestImpact])
  const noteLines = useMemo(() => readStringList(latestImpact?.notes_json), [latestImpact])

  async function runImpactAssessment() {
    if (!Number.isFinite(changeId) || changeId < 1) return
    setImpactBusy(true)
    setImpactErr("")
    setImpactOk("")
    try {
      await apiFetch(`/regulatory/changes/${changeId}/impact-assessment`, {
        method: "POST",
        body: { metadata_json: {} },
      })
      if (change) {
        trackRegulatoryImpactAssessmentRun({
          change_type: readRecordString(change, "change_type"),
          severity: readRecordString(change, "severity"),
          affected_dossier_count: readIntList(change.affected_dossier_ids_json).length,
          affected_rule_count: readIntList(change.affected_rule_set_ids_json).length,
        })
      }
      setImpactOk("Impact assessment completed.")
      await load()
    } catch (e) {
      setImpactErr(formatApiError(e, "Run impact assessment failed."))
    } finally {
      setImpactBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-[1200px] space-y-6 p-4 md:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/regulatory/surveillance">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Regulatory Surveillance
          </Link>
        </Button>
      </div>

      <header className="space-y-1">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: "var(--mt-cyan-ink)" }}
        >
          MolTrace · Regulatory · Change Detail
        </p>
        <h1 className="font-mono text-2xl font-bold tracking-tight">Regulatory Change Detail</h1>
        <p className="text-sm text-muted-foreground">
          source change detected signals, possible impact triage, and requires qualified review workflow.
        </p>
      </header>

      <AlertCard
        variant="warning"
        title="Requires qualified review"
        description="This page shows source change detected and possible impact summaries from backend records. It is not legal advice."
      />

      {loading ? <p className="text-sm text-muted-foreground">Loading…</p> : null}
      {loadErr ? <AlertCard variant="error" title="Error" description={loadErr} /> : null}

      {/* 1. Change summary */}
      <ModuleCard
        accent="cyan"
        eyebrow="Summary"
        title="Change summary"
        icon={FileText}
        description="Regulatory change event details — type, severity, review status, and affected source."
      >
        <div className="space-y-2 text-sm">
          <p className="font-medium">{readRecordString(change, "title") ?? "—"}</p>
          <p className="text-muted-foreground">{readRecordString(change, "summary") ?? "—"}</p>
          <div className="flex flex-wrap gap-2 text-xs">
            <Badge variant="outline">change_id {changeId}</Badge>
            <Badge variant="outline">change_type {readRecordString(change, "change_type") ?? "—"}</Badge>
            <Badge variant="outline">severity {readRecordString(change, "severity") ?? "—"}</Badge>
            <Badge variant="outline">review_status {readRecordString(change, "review_status") ?? "—"}</Badge>
            <Badge variant="outline">source_id {readRecordNumber(change, "source_id") ?? "—"}</Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            created_at {formatWhen(readRecordString(change, "created_at") ?? undefined)}
          </p>
        </div>
      </ModuleCard>

      {/* 2. Source versions */}
      <ModuleCard
        accent="cyan"
        eyebrow="Versions"
        title="Source versions"
        icon={GitBranch}
        description="Version links captured on the change event."
      >
        <div className="grid gap-4 md:grid-cols-2">
          <ModuleCard accent="cyan" eyebrow="Old" title="Old version" icon={FileText}>
            <div className="space-y-1 text-xs">
              <p className="font-mono">old_version_id {readRecordNumber(change, "old_version_id") ?? "—"}</p>
              <p>version label: {readRecordString(oldVersion, "version_label") ?? "—"}</p>
              <p>source date: {formatWhen(readRecordString(oldVersion, "source_date") ?? undefined)}</p>
              <p>retrieved date: {formatWhen(readRecordString(oldVersion, "retrieved_at") ?? undefined)}</p>
              <p className="font-mono break-all">
                SHA-256/content hash:{" "}
                {readRecordString(oldVersion, "sha256") ?? readRecordString(oldVersion, "content_hash") ?? "—"}
              </p>
              <p>status: {readRecordString(oldVersion, "status") ?? "—"}</p>
            </div>
          </ModuleCard>
          <ModuleCard accent="cyan" eyebrow="New" title="New version" icon={FileText}>
            <div className="space-y-1 text-xs">
              <p className="font-mono">new_version_id {readRecordNumber(change, "new_version_id") ?? "—"}</p>
              <p>version label: {readRecordString(newVersion, "version_label") ?? "—"}</p>
              <p>source date: {formatWhen(readRecordString(newVersion, "source_date") ?? undefined)}</p>
              <p>retrieved date: {formatWhen(readRecordString(newVersion, "retrieved_at") ?? undefined)}</p>
              <p className="font-mono break-all">
                SHA-256/content hash:{" "}
                {readRecordString(newVersion, "sha256") ?? readRecordString(newVersion, "content_hash") ?? "—"}
              </p>
              <p>status: {readRecordString(newVersion, "status") ?? "—"}</p>
            </div>
          </ModuleCard>
        </div>
      </ModuleCard>

      {/* 3. Diff excerpts */}
      <ModuleCard
        accent="cyan"
        eyebrow="Diff"
        title="Diff excerpts"
        icon={ScrollText}
        description="Structured diff rows from the change payload."
      >
        <div className="space-y-3">
          {diffs.length === 0 ? (
            <p className="text-sm text-muted-foreground">No diff excerpts returned.</p>
          ) : (
            diffs.map((row, idx) => (
              <ModuleCard
                key={readRecordNumber(row, "id") ?? idx}
                accent="cyan"
                eyebrow="Diff"
                title={`diff_type ${readRecordString(row, "diff_type") ?? "—"} · id ${readRecordNumber(row, "id") ?? "—"}`}
                icon={ScrollText}
              >
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">before excerpt</p>
                    <blockquote className="mt-1 rounded-md border border-dashed bg-muted/40 px-3 py-2 text-sm leading-relaxed">
                      {readRecordString(row, "before_excerpt") ?? "—"}
                    </blockquote>
                  </div>
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">after excerpt</p>
                    <blockquote className="mt-1 rounded-md border border-dashed bg-muted/40 px-3 py-2 text-sm leading-relaxed">
                      {readRecordString(row, "after_excerpt") ?? "—"}
                    </blockquote>
                  </div>
                  <div className="md:col-span-2">
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">diff summary</p>
                    <p className="mt-1 text-sm">{readRecordString(row, "diff_summary") ?? "—"}</p>
                  </div>
                </div>
              </ModuleCard>
            ))
          )}
        </div>
      </ModuleCard>

      {/* 4. Affected topics */}
      <ModuleCard
        accent="cyan"
        eyebrow="Topics"
        title="Affected topics"
        icon={Tag}
      >
        <div>
          {topicList.length === 0 ? (
            <p className="text-sm text-muted-foreground">No affected topics returned.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {topicList.map((t, i) => (
                <Badge key={`${t}-${i}`} variant="secondary">
                  {t}
                </Badge>
              ))}
            </div>
          )}
        </div>
      </ModuleCard>

      {/* 5. Affected dossiers */}
      <ModuleCard
        accent="cyan"
        eyebrow="Dossiers"
        title="Affected dossiers"
        icon={Layers3}
      >
        <div>
          {affectedDossiers.length === 0 ? (
            <p className="text-sm text-muted-foreground">No affected dossiers returned.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {affectedDossiers.map((id) => (
                <Button key={`dossier-${id}`} variant="outline" size="sm" asChild>
                  <Link href={`/regulatory/dossiers/${id}`}>dossier {id}</Link>
                </Button>
              ))}
            </div>
          )}
        </div>
      </ModuleCard>

      {/* 6. Rule update proposals */}
      <ModuleCard
        accent="cyan"
        eyebrow="Proposals"
        title="Rule update proposals"
        icon={ClipboardList}
        description="Rule update proposals linked to this regulatory change event — showing proposal type, status, and rationale."
      >
        <div className="space-y-2">
          <div>
            <Button type="button" variant="outline" size="sm" asChild>
              <Link href={`/regulatory/rule-updates?change_id=${changeId}`}>Open rule update proposals</Link>
            </Button>
          </div>
          {proposalRows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No rule update proposals linked to this change.</p>
          ) : (
            proposalRows.map((row, idx) => (
              <Card key={readRecordNumber(row, "id") ?? idx} className="border-muted">
                <CardContent className="pt-4 text-sm">
                  <p className="font-medium">{readRecordString(row, "title") ?? "—"}</p>
                  <p className="mt-1 text-muted-foreground">{readRecordString(row, "rationale") ?? "—"}</p>
                  <p className="mt-2 text-xs">
                    proposal_type {readRecordString(row, "proposal_type") ?? "—"} · status{" "}
                    {readRecordString(row, "status") ?? "—"}
                  </p>
                  {readRecordNumber(row, "id") != null ? (
                    <p className="mt-2">
                      <Link
                        href={`/regulatory/rule-updates?proposal_id=${readRecordNumber(row, "id")}`}
                        className="text-xs font-medium text-primary underline-offset-4 hover:underline"
                      >
                        Open proposal
                      </Link>
                    </p>
                  ) : null}
                </CardContent>
              </Card>
            ))
          )}
        </div>
      </ModuleCard>

      {/* 7. Impact assessment */}
      <ModuleCard
        accent="cyan"
        eyebrow="Impact"
        title={
          <span className="flex items-center gap-2">
            Change Impact Assessment
            <InfoTooltip
              label="Change Impact Assessment"
              content="Impact assessment maps a regulatory source change to affected dossiers, requirements, rule sets, action items, AI governance records, and reports."
            />
          </span>
        }
        icon={Network}
        description="Assess the downstream impact of this regulatory change across affected dossiers, requirements, rule sets, action items, and AI governance records."
      >
        <div className="space-y-4">
          {impactErr ? <AlertCard variant="error" title="Impact error" description={impactErr} /> : null}
          {impactOk ? <AlertCard variant="success" title="Recorded" description={impactOk} /> : null}
          <Button type="button" disabled={impactBusy} onClick={() => void runImpactAssessment()}>
            {impactBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Run impact assessment
          </Button>

          {latestImpact == null ? (
            <p className="text-sm text-muted-foreground">No impact assessments returned.</p>
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <Card
                  className="overflow-hidden rounded-xl py-0"
                  style={{ borderTop: "3px solid var(--mt-cyan)" }}
                >
                  <CardContent className="space-y-1 pt-5 pb-5 text-sm">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">impacted dossiers</p>
                    <p className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-cyan-ink)" }}>{impactedDossierIds.length}</p>
                  </CardContent>
                </Card>
                <Card
                  className="overflow-hidden rounded-xl py-0"
                  style={{ borderTop: "3px solid var(--mt-cyan)" }}
                >
                  <CardContent className="space-y-1 pt-5 pb-5 text-sm">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">impacted requirements</p>
                    <p className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-cyan-ink)" }}>{impactedRequirementIds.length}</p>
                  </CardContent>
                </Card>
                <Card
                  className="overflow-hidden rounded-xl py-0"
                  style={{ borderTop: "3px solid var(--mt-amber)" }}
                >
                  <CardContent className="space-y-1 pt-5 pb-5 text-sm">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">impacted action items</p>
                    <p className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-amber)" }}>{impactedActionItemIds.length}</p>
                  </CardContent>
                </Card>
                <Card
                  className="overflow-hidden rounded-xl py-0"
                  style={{ borderTop: "3px solid var(--mt-cyan)" }}
                >
                  <CardContent className="space-y-1 pt-5 pb-5 text-sm">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">impacted rule sets</p>
                    <p className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-cyan-ink)" }}>{impactedRuleSetIds.length}</p>
                  </CardContent>
                </Card>
                <Card
                  className="overflow-hidden rounded-xl py-0"
                  style={{ borderTop: "3px solid var(--mt-violet)" }}
                >
                  <CardContent className="space-y-1 pt-5 pb-5 text-sm">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">impacted AI governance records</p>
                    <p className="font-mono text-3xl font-bold tabular-nums leading-none" style={{ color: "var(--mt-violet-ink)" }}>{impactedAiGovIds.length}</p>
                  </CardContent>
                </Card>
                <Card
                  className="overflow-hidden rounded-xl py-0"
                  style={{ borderTop: `3px solid ${latestImpact.human_review_required ? "var(--mt-red)" : "var(--mt-cyan)"}` }}
                >
                  <CardContent className="space-y-1 pt-5 pb-5 text-sm">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">human review required</p>
                    <Badge variant={latestImpact.human_review_required ? "destructive" : "secondary"}>
                      {latestImpact.human_review_required ? "required" : "not flagged"}
                    </Badge>
                  </CardContent>
                </Card>
              </div>

              <div className="space-y-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">recommended actions</p>
                {recommendedActions.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No recommended actions returned.</p>
                ) : (
                  <div className="space-y-2">
                    {recommendedActions.map((act, idx) => (
                      <Card key={`ra-${idx}`} className="border-muted">
                        <CardContent className="pt-4 text-sm">
                          <p className="font-medium">{readRecordString(act, "title") ?? "—"}</p>
                          <p className="text-muted-foreground">{readRecordString(act, "description") ?? "—"}</p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            action_type {readRecordString(act, "action_type") ?? "—"}
                          </p>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">warnings</p>
                  {warningLines.length === 0 ? (
                    <p className="mt-1 text-sm text-muted-foreground">No warnings.</p>
                  ) : (
                    <ul className="mt-1 list-inside list-disc text-sm">
                      {warningLines.map((w, i) => (
                        <li key={`warn-${i}`}>{w}</li>
                      ))}
                    </ul>
                  )}
                </div>
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">notes</p>
                  {noteLines.length === 0 ? (
                    <p className="mt-1 text-sm text-muted-foreground">No notes.</p>
                  ) : (
                    <ul className="mt-1 list-inside list-disc text-sm">
                      {noteLines.map((n, i) => (
                        <li key={`note-${i}`}>{n}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>

              <div className="space-y-2">
                <p className="text-sm font-semibold">Affected Dossiers</p>
                {impactedDossierIds.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No impacted dossiers returned.</p>
                ) : (
                  <div className="table-scroll">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>dossier</TableHead>
                          <TableHead>jurisdiction</TableHead>
                          <TableHead>status</TableHead>
                          <TableHead>affected requirements</TableHead>
                          <TableHead>open action items</TableHead>
                          <TableHead>recommended action</TableHead>
                          <TableHead>open dossier button</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {impactedDossierIds.map((dossierId) => {
                          const dossier = dossiers.find((d) => readRecordNumber(d, "id") === dossierId)
                          const jid = readRecordNumber(dossier, "jurisdiction_id")
                          const openActionItems = actionItems.filter((row) => {
                            if (readRecordNumber(row, "dossier_id") !== dossierId) return false
                            const st = readRecordString(row, "status")
                            return st === "open" || st === "in_progress" || st === "deferred"
                          }).length
                          const rec = recommendedActions.find((act) =>
                            readIntList(act.affected_dossier_ids).includes(dossierId),
                          )
                          return (
                            <TableRow key={`aff-dossier-${dossierId}`}>
                              <TableCell className="font-mono text-xs">{dossierId}</TableCell>
                              <TableCell className="text-xs">
                                {jid != null ? jurisdictionNameById.get(jid) ?? `id ${jid}` : "—"}
                              </TableCell>
                              <TableCell className="text-xs">{readRecordString(dossier, "status") ?? "—"}</TableCell>
                              <TableCell className="tabular-nums text-xs">{impactedRequirementIds.length}</TableCell>
                              <TableCell className="tabular-nums text-xs">{openActionItems}</TableCell>
                              <TableCell className="text-xs">{readRecordString(rec, "title") ?? "—"}</TableCell>
                              <TableCell>
                                <Button type="button" variant="outline" size="sm" asChild>
                                  <Link href={`/regulatory/dossiers/${dossierId}`}>Open dossier</Link>
                                </Button>
                              </TableCell>
                            </TableRow>
                          )
                        })}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </div>

              <DeveloperJsonPanel data={latestImpact} />
            </>
          )}
        </div>
      </ModuleCard>

      {/* 8. Review decision */}
      <ModuleCard
        accent="cyan"
        eyebrow="Review"
        title="Review decision"
        icon={ListChecks}
        description="Record a formal review decision on this regulatory change — approve, reject, or escalate — with reviewer attribution and comment."
      >
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="chg-reviewer">reviewer name</Label>
              <Input
                id="chg-reviewer"
                value={reviewerName}
                onChange={(e) => setReviewerName(e.target.value)}
                autoComplete="off"
              />
            </div>
            <div className="space-y-2">
              <Label>decision</Label>
              <Select value={reviewDecision} onValueChange={setReviewDecision}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="accepted">accepted</SelectItem>
                  <SelectItem value="rejected">rejected</SelectItem>
                  <SelectItem value="deferred">deferred</SelectItem>
                  <SelectItem value="in_review">in_review</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="chg-rationale">rationale required</Label>
            <Textarea
              id="chg-rationale"
              rows={4}
              value={reviewRationale}
              onChange={(e) => setReviewRationale(e.target.value)}
            />
          </div>
          {reviewErr ? <AlertCard variant="error" title="Review error" description={reviewErr} /> : null}
          {reviewOk ? <AlertCard variant="success" title="Recorded" description={reviewOk} /> : null}
          <Button type="button" disabled={reviewBusy} onClick={() => void saveReview()}>
            {reviewBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Save change review
          </Button>
        </div>
      </ModuleCard>

      {/* 9. Developer JSON collapsed */}
      <DeveloperOnly>
        <ModuleCard
          accent="cyan"
          eyebrow="Audit"
          title="Developer JSON"
          icon={FileSearch}
          description="Collapsed raw payloads for debugging and audit."
        >
          <div className="space-y-3">
            <DeveloperJsonPanel data={{ change, source_versions: { old: oldVersion, new: newVersion }, impactRows, proposalRows }} />
          </div>
        </ModuleCard>
      </DeveloperOnly>
    </div>
  )
}
