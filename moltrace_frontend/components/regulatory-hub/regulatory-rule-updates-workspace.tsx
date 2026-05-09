"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { useSearchParams } from "next/navigation"
import {
  trackRegulatoryRuleUpdateProposalApproved,
  trackRegulatoryRuleUpdateProposalCreated,
  trackRegulatoryRuleUpdateProposalRejected,
} from "@/src/lib/analytics/analytics-client"
import { apiFetch } from "@/lib/api/client"
import { formatStableUtcDateTime } from "@/lib/utils"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
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
import { AlertTriangle, ArrowLeft, Loader2 } from "lucide-react"

const PROPOSAL_TYPES = [
  "create_rule",
  "update_threshold",
  "update_citation",
  "deprecate_rule",
  "create_action_item",
  "update_jurisdiction_map",
  "other",
] as const

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

function parseOptionalJsonObject(input: string, fieldName: string): { ok: true; value: Record<string, unknown> } | { ok: false; error: string } {
  const t = input.trim()
  if (!t) return { ok: true, value: {} }
  try {
    const parsed = JSON.parse(t)
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { ok: false, error: `${fieldName} must be a JSON object.` }
    }
    return { ok: true, value: parsed as Record<string, unknown> }
  } catch {
    return { ok: false, error: `${fieldName} must be valid JSON.` }
  }
}

function parseOptionalCsvInts(input: string): number[] {
  if (!input.trim()) return []
  return input
    .split(",")
    .map((p) => Number.parseInt(p.trim(), 10))
    .filter((n) => Number.isFinite(n) && n >= 1)
}

export function RegulatoryRuleUpdatesWorkspace() {
  const searchParams = useSearchParams()

  const [loading, setLoading] = useState(true)
  const [loadErr, setLoadErr] = useState("")
  const [changes, setChanges] = useState<Record<string, unknown>[]>([])
  const [proposals, setProposals] = useState<Record<string, unknown>[]>([])
  const [ruleSets, setRuleSets] = useState<Record<string, unknown>[]>([])

  const [createChangeId, setCreateChangeId] = useState("")
  const [createProposalType, setCreateProposalType] = useState<string>("other")
  const [createTitle, setCreateTitle] = useState("")
  const [createRationale, setCreateRationale] = useState("")
  const [createRuleSetId, setCreateRuleSetId] = useState("")
  const [createProposedChangesJson, setCreateProposedChangesJson] = useState("{}")
  const [createCitationIds, setCreateCitationIds] = useState("")
  const [createBusy, setCreateBusy] = useState(false)
  const [createErr, setCreateErr] = useState("")
  const [createOk, setCreateOk] = useState("")

  const [selectedProposalId, setSelectedProposalId] = useState<number | null>(null)
  const [selectedProposal, setSelectedProposal] = useState<Record<string, unknown> | null>(null)
  const [selectedProposalLoading, setSelectedProposalLoading] = useState(false)
  const [selectedProposalErr, setSelectedProposalErr] = useState("")

  const [reviewerName, setReviewerName] = useState("")
  const [reviewComment, setReviewComment] = useState("")
  const [reviewBusy, setReviewBusy] = useState(false)
  const [reviewErr, setReviewErr] = useState("")
  const [reviewOk, setReviewOk] = useState("")

  const ruleSetNameById = useMemo(() => {
    const m = new Map<number, string>()
    for (const row of ruleSets) {
      const id = readRecordNumber(row, "id")
      const name = readRecordString(row, "name")
      if (id != null && name) m.set(id, name)
    }
    return m
  }, [ruleSets])

  const changeTitleById = useMemo(() => {
    const m = new Map<number, string>()
    for (const row of changes) {
      const id = readRecordNumber(row, "id")
      const title = readRecordString(row, "title")
      if (id != null && title) m.set(id, title)
    }
    return m
  }, [changes])

  const load = useCallback(async () => {
    setLoading(true)
    setLoadErr("")
    try {
      const [changesRaw, proposalsRaw, ruleSetsRaw] = await Promise.all([
        apiFetch<unknown>("/regulatory/changes?limit=500", { method: "GET" }).catch(() => []),
        apiFetch<unknown>("/regulatory/rule-update-proposals?limit=500", { method: "GET" }),
        apiFetch<unknown>("/regulatory/rule-sets?limit=500", { method: "GET" }).catch(() => []),
      ])
      setChanges(asArray(changesRaw).filter(isRecord) as Record<string, unknown>[])
      setProposals(asArray(proposalsRaw).filter(isRecord) as Record<string, unknown>[])
      setRuleSets(asArray(ruleSetsRaw).filter(isRecord) as Record<string, unknown>[])
    } catch (e) {
      setLoadErr(formatApiError(e, "Could not load rule update proposals."))
      setChanges([])
      setProposals([])
      setRuleSets([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    const qChange = searchParams.get("change_id")
    const qProposal = searchParams.get("proposal_id")
    if (qChange && /^\d+$/.test(qChange)) setCreateChangeId(qChange)
    if (qProposal && /^\d+$/.test(qProposal)) setSelectedProposalId(Number.parseInt(qProposal, 10))
  }, [searchParams])

  useEffect(() => {
    let cancelled = false
    async function loadProposal() {
      if (selectedProposalId == null) {
        setSelectedProposal(null)
        return
      }
      setSelectedProposalLoading(true)
      setSelectedProposalErr("")
      try {
        const raw = await apiFetch<unknown>(`/regulatory/rule-update-proposals/${selectedProposalId}`, { method: "GET" })
        if (!cancelled) setSelectedProposal(isRecord(raw) ? raw : null)
      } catch (e) {
        if (!cancelled) {
          setSelectedProposalErr(formatApiError(e, "Could not load proposal detail."))
          setSelectedProposal(null)
        }
      } finally {
        if (!cancelled) setSelectedProposalLoading(false)
      }
    }
    void loadProposal()
    return () => {
      cancelled = true
    }
  }, [selectedProposalId])

  async function createProposal() {
    setCreateErr("")
    setCreateOk("")
    const changeIdNum = Number.parseInt(createChangeId.trim(), 10)
    if (!Number.isFinite(changeIdNum) || changeIdNum < 1) {
      setCreateErr("source change is required.")
      return
    }
    const title = createTitle.trim()
    if (!title) {
      setCreateErr("title is required.")
      return
    }
    const rationale = createRationale.trim()
    if (!rationale) {
      setCreateErr("rationale is required.")
      return
    }
    const parsedJson = parseOptionalJsonObject(createProposedChangesJson, "proposed changes JSON")
    if (!parsedJson.ok) {
      setCreateErr(parsedJson.error)
      return
    }
    setCreateBusy(true)
    try {
      const body: Record<string, unknown> = {
        proposal_type: createProposalType,
        title,
        rationale,
        proposed_changes_json: parsedJson.value,
        citation_ids_json: parseOptionalCsvInts(createCitationIds),
        metadata_json: {},
      }
      const rsid = Number.parseInt(createRuleSetId.trim(), 10)
      if (Number.isFinite(rsid) && rsid >= 1) body.rule_set_id = rsid
      await apiFetch(`/regulatory/changes/${changeIdNum}/rule-update-proposal`, { method: "POST", body })
      trackRegulatoryRuleUpdateProposalCreated({
        proposal_type: createProposalType,
        status: "proposed",
      })
      setCreateOk("Rule update proposal created.")
      setCreateTitle("")
      setCreateRationale("")
      setCreateRuleSetId("")
      setCreateCitationIds("")
      setCreateProposedChangesJson("{}")
      await load()
    } catch (e) {
      setCreateErr(formatApiError(e, "Create rule update proposal failed."))
    } finally {
      setCreateBusy(false)
    }
  }

  async function submitProposalReview(action: "approve" | "reject") {
    if (selectedProposalId == null) return
    setReviewErr("")
    setReviewOk("")
    const reviewer = reviewerName.trim()
    const comment = reviewComment.trim()
    if (!reviewer) {
      setReviewErr("reviewer name is required.")
      return
    }
    if (!comment) {
      setReviewErr("reviewer comment/rationale is required.")
      return
    }
    setReviewBusy(true)
    try {
      await apiFetch(`/regulatory/rule-update-proposals/${selectedProposalId}/${action}`, {
        method: "POST",
        body: {
          reviewer_name: reviewer,
          reviewer_comment: comment,
          rationale: comment,
          metadata_json: {},
        },
      })
      const proposalType = readRecordString(selectedProposal ?? {}, "proposal_type")
      if (action === "approve") {
        trackRegulatoryRuleUpdateProposalApproved({
          proposal_type: proposalType,
          status: "approved",
        })
      } else {
        trackRegulatoryRuleUpdateProposalRejected({
          proposal_type: proposalType,
          status: "rejected",
        })
      }
      setReviewOk(action === "approve" ? "Proposal approved." : "Proposal rejected.")
      await load()
      const fresh = await apiFetch<unknown>(`/regulatory/rule-update-proposals/${selectedProposalId}`, { method: "GET" })
      setSelectedProposal(isRecord(fresh) ? fresh : null)
    } catch (e) {
      setReviewErr(formatApiError(e, `${action === "approve" ? "Approve" : "Reject"} failed.`))
    } finally {
      setReviewBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/regulatory/surveillance">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Regulatory Surveillance
          </Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/regulatory">Regulatory home</Link>
        </Button>
      </div>

      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Rule Update Proposals</h1>
        <p className="text-sm text-muted-foreground">
          Proposed rule updates require reviewer rationale and do not automatically alter source documents.
        </p>
      </header>

      <Alert>
        <AlertTriangle className="h-4 w-4" aria-hidden />
        <AlertTitle>Review required</AlertTitle>
        <AlertDescription className="text-sm text-muted-foreground">
          Proposal approval requires rationale and does not silently apply changes to prior source records.
        </AlertDescription>
      </Alert>

      {loadErr ? (
        <Alert variant="destructive">
          <AlertDescription className="text-sm">{loadErr}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Create proposal</CardTitle>
          <CardDescription>Propose a rule set or guidance update in response to a detected regulatory change — includes proposal type, rationale, and affected rule set.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {createErr ? (
            <Alert variant="destructive">
              <AlertDescription className="text-sm">{createErr}</AlertDescription>
            </Alert>
          ) : null}
          {createOk ? (
            <Alert>
              <AlertDescription className="text-sm">{createOk}</AlertDescription>
            </Alert>
          ) : null}
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="rup-change-id">source change</Label>
              <Select value={createChangeId || "__none__"} onValueChange={(v) => setCreateChangeId(v === "__none__" ? "" : v)}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select change_id" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Select change_id</SelectItem>
                  {changes.map((row, idx) => {
                    const id = readRecordNumber(row, "id")
                    if (id == null) return null
                    const title = readRecordString(row, "title") ?? `change ${id}`
                    return (
                      <SelectItem key={`chg-${id}-${idx}`} value={String(id)}>
                        {title} ({id})
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>proposal type</Label>
              <Select value={createProposalType} onValueChange={setCreateProposalType}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PROPOSAL_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="rup-title">title</Label>
              <Input id="rup-title" value={createTitle} onChange={(e) => setCreateTitle(e.target.value)} autoComplete="off" />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="rup-rationale">rationale</Label>
              <Textarea
                id="rup-rationale"
                rows={4}
                value={createRationale}
                onChange={(e) => setCreateRationale(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="rup-rule-set">rule set optional</Label>
              <Input
                id="rup-rule-set"
                value={createRuleSetId}
                onChange={(e) => setCreateRuleSetId(e.target.value)}
                placeholder="rule_set_id"
                autoComplete="off"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="rup-citations">citation IDs optional</Label>
              <Input
                id="rup-citations"
                value={createCitationIds}
                onChange={(e) => setCreateCitationIds(e.target.value)}
                placeholder="1,2,3"
                autoComplete="off"
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="rup-json">proposed changes JSON</Label>
              <Textarea
                id="rup-json"
                rows={6}
                value={createProposedChangesJson}
                onChange={(e) => setCreateProposedChangesJson(e.target.value)}
              />
            </div>
          </div>
          <Button type="button" disabled={createBusy} onClick={() => void createProposal()}>
            {createBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Create rule update proposal
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Proposal table</CardTitle>
          <CardDescription>All rule update proposals across regulatory changes — filter by status, proposal type, or source change to manage the review queue.</CardDescription>
        </CardHeader>
        <CardContent className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : proposals.length === 0 ? (
            <p className="text-sm text-muted-foreground">No rule update proposals.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>title</TableHead>
                  <TableHead>proposal type</TableHead>
                  <TableHead>source change</TableHead>
                  <TableHead>rule set</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead>reviewer</TableHead>
                  <TableHead>updated date</TableHead>
                  <TableHead>open button</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {proposals.map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  const changeEventId = readRecordNumber(row, "change_event_id")
                  const ruleSetId = readRecordNumber(row, "rule_set_id")
                  return (
                    <TableRow key={id != null ? `prop-${id}` : `prop-${idx}`}>
                      <TableCell className="max-w-[220px] font-medium">{readRecordString(row, "title") ?? "—"}</TableCell>
                      <TableCell className="text-xs">{readRecordString(row, "proposal_type") ?? "—"}</TableCell>
                      <TableCell className="text-xs">
                        {changeEventId != null ? (
                          <Link
                            href={`/regulatory/changes/${changeEventId}`}
                            className="text-primary underline-offset-4 hover:underline"
                            title={changeTitleById.get(changeEventId) ?? ""}
                          >
                            change {changeEventId}
                          </Link>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell className="text-xs">
                        {ruleSetId != null ? ruleSetNameById.get(ruleSetId) ?? `id ${ruleSetId}` : "—"}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
                      </TableCell>
                      <TableCell className="text-xs">{readRecordString(row, "reviewer_name") ?? "—"}</TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatWhen(readRecordString(row, "updated_at") ?? undefined)}
                      </TableCell>
                      <TableCell>
                        {id != null ? (
                          <Button type="button" variant="outline" size="sm" onClick={() => setSelectedProposalId(id)}>
                            Open
                          </Button>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Proposal detail & review</CardTitle>
          <CardDescription>
            Review a rule update proposal in detail and record a formal approval or rejection decision with reviewer attribution.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {selectedProposalErr ? (
            <Alert variant="destructive">
              <AlertDescription className="text-sm">{selectedProposalErr}</AlertDescription>
            </Alert>
          ) : null}
          {reviewErr ? (
            <Alert variant="destructive">
              <AlertDescription className="text-sm">{reviewErr}</AlertDescription>
            </Alert>
          ) : null}
          {reviewOk ? (
            <Alert>
              <AlertDescription className="text-sm">{reviewOk}</AlertDescription>
            </Alert>
          ) : null}

          {selectedProposalLoading ? (
            <p className="text-sm text-muted-foreground">Loading proposal…</p>
          ) : selectedProposal == null ? (
            <p className="text-sm text-muted-foreground">Select a proposal with Open.</p>
          ) : (
            <>
              <div className="rounded-md border bg-muted/20 p-3 text-sm">
                <p className="font-medium">{readRecordString(selectedProposal, "title") ?? "—"}</p>
                <p className="text-muted-foreground">{readRecordString(selectedProposal, "rationale") ?? "—"}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  status {readRecordString(selectedProposal, "status") ?? "—"} · proposal_id{" "}
                  {readRecordNumber(selectedProposal, "id") ?? "—"}
                </p>
                {readRecordString(selectedProposal, "status") === "applied" ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Backend returned applied status. This page displays status only and does not apply updates from the frontend.
                  </p>
                ) : null}
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="rup-reviewer">reviewer name</Label>
                  <Input
                    id="rup-reviewer"
                    value={reviewerName}
                    onChange={(e) => setReviewerName(e.target.value)}
                    autoComplete="off"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="rup-comment">reviewer comment/rationale required</Label>
                  <Textarea
                    id="rup-comment"
                    rows={4}
                    value={reviewComment}
                    onChange={(e) => setReviewComment(e.target.value)}
                  />
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button type="button" disabled={reviewBusy} onClick={() => void submitProposalReview("approve")}>
                  {reviewBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                  Approve
                </Button>
                <Button type="button" variant="destructive" disabled={reviewBusy} onClick={() => void submitProposalReview("reject")}>
                  {reviewBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                  Reject
                </Button>
              </div>

              <DeveloperJsonPanel data={selectedProposal} />
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
