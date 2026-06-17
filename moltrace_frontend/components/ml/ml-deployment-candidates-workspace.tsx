"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import {
  trackMlDeploymentCandidateApproved,
  trackMlDeploymentCandidateCreated,
  trackMlDeploymentCandidateRejected,
} from "@/src/lib/analytics/analytics-client"
import { AlertTriangle, ArrowLeft, ListChecks, Loader2, Plus, RefreshCw } from "lucide-react"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function summarizeJson(raw: unknown, maxLen = 160): string {
  if (raw == null) return "—"
  if (typeof raw === "object") {
    const s = JSON.stringify(raw)
    return s.length > maxLen ? `${s.slice(0, maxLen)}…` : s
  }
  return String(raw)
}

const TARGET_MODULES = [
  "spectracheck",
  "msms",
  "lcms",
  "reaction_optimization",
  "regulatory",
  "report",
  "knowledge_extraction",
] as const

const REVIEWABLE_STATUSES = ["proposed", "in_review"] as const

function artifactLabel(row: Record<string, unknown>): string {
  const id = readRecordNumber(row, "id")
  const name = readRecordString(row, "model_name") ?? ""
  const ver = readRecordString(row, "model_version") ?? ""
  if (id == null) return "—"
  return `#${id} ${name} ${ver}`.trim()
}

export function MlDeploymentCandidatesWorkspace() {
  const [reload, setReload] = useState(0)
  const [loading, setLoading] = useState(true)
  const [errLoad, setErrLoad] = useState("")
  const [artifacts, setArtifacts] = useState<Record<string, unknown>[]>([])
  const [modelCards, setModelCards] = useState<Record<string, unknown>[]>([])
  const [evalRuns, setEvalRuns] = useState<Record<string, unknown>[]>([])
  const [calibrationRows, setCalibrationRows] = useState<Record<string, unknown>[]>([])
  const [oodRows, setOodRows] = useState<Record<string, unknown>[]>([])
  const [candidates, setCandidates] = useState<Record<string, unknown>[]>([])

  const [createArtifactId, setCreateArtifactId] = useState("")
  const [createCardId, setCreateCardId] = useState("")
  const [createTargetModule, setCreateTargetModule] = useState<string>("spectracheck")
  const [createEndpoint, setCreateEndpoint] = useState("")
  const [createBusy, setCreateBusy] = useState(false)
  const [createErr, setCreateErr] = useState("")
  const [createOk, setCreateOk] = useState("")

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [approveName, setApproveName] = useState("")
  const [approveComment, setApproveComment] = useState("")
  const [approveLevel, setApproveLevel] = useState<string>("approved_for_internal_use")
  const [approveBusy, setApproveBusy] = useState(false)
  const [approveErr, setApproveErr] = useState("")

  const [rejectName, setRejectName] = useState("")
  const [rejectReason, setRejectReason] = useState("")
  const [rejectBusy, setRejectBusy] = useState(false)
  const [rejectErr, setRejectErr] = useState("")

  const [getSnapshot, setGetSnapshot] = useState<Record<string, unknown> | null>(null)
  const [getSnapshotLoading, setGetSnapshotLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setErrLoad("")
    try {
      const [a, c, e, cal, ood, dc] = await Promise.all([
        apiFetch<unknown>("/ml/model-artifacts?limit=500", { method: "GET" }),
        apiFetch<unknown>("/ml/model-cards?limit=500", { method: "GET" }),
        apiFetch<unknown>("/ml/evaluation-runs?limit=500", { method: "GET" }),
        apiFetch<unknown>("/ml/calibration-assessments?limit=500", { method: "GET" }),
        apiFetch<unknown>("/ml/ood-assessments?limit=500", { method: "GET" }),
        apiFetch<unknown>("/ml/deployment-candidates?limit=500", { method: "GET" }),
      ])
      setArtifacts(Array.isArray(a) ? (a.filter(isRecord) as Record<string, unknown>[]) : [])
      setModelCards(Array.isArray(c) ? (c.filter(isRecord) as Record<string, unknown>[]) : [])
      setEvalRuns(Array.isArray(e) ? (e.filter(isRecord) as Record<string, unknown>[]) : [])
      setCalibrationRows(Array.isArray(cal) ? (cal.filter(isRecord) as Record<string, unknown>[]) : [])
      setOodRows(Array.isArray(ood) ? (ood.filter(isRecord) as Record<string, unknown>[]) : [])
      setCandidates(Array.isArray(dc) ? (dc.filter(isRecord) as Record<string, unknown>[]) : [])
    } catch (er) {
      setErrLoad(formatApiError(er, "Could not load deployment candidate data."))
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load, reload])

  useEffect(() => {
    if (selectedId == null) {
      setGetSnapshot(null)
      return
    }
    let cancelled = false
    setGetSnapshotLoading(true)
    setGetSnapshot(null)
    void (async () => {
      try {
        const raw = await apiFetch<unknown>(`/ml/deployment-candidates/${selectedId}`, {
          method: "GET",
        })
        if (!cancelled && isRecord(raw)) setGetSnapshot(raw)
      } catch {
        if (!cancelled) setGetSnapshot(null)
      } finally {
        if (!cancelled) setGetSnapshotLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selectedId, reload])

  const cardsForArtifact = useMemo(() => {
    const aid = Number.parseInt(createArtifactId, 10)
    if (!Number.isFinite(aid) || aid < 1) return []
    return modelCards.filter((row) => readRecordNumber(row, "model_artifact_id") === aid)
  }, [createArtifactId, modelCards])

  const selected = useMemo(() => {
    if (selectedId == null) return null
    return candidates.find((r) => readRecordNumber(r, "id") === selectedId) ?? null
  }, [candidates, selectedId])

  const selectedArtifactId = selected ? readRecordNumber(selected, "model_artifact_id") : null

  const gateChecks = useMemo(() => {
    if (selectedArtifactId == null) {
      return {
        hasSucceededEval: false,
        hasCalibration: false,
        hasOod: false,
        latestEvalSummary: "—" as string,
        calibrationLine: "—" as string,
        oodLine: "—" as string,
      }
    }
    const aid = selectedArtifactId
    const evalsForArt = evalRuns.filter((r) => readRecordNumber(r, "model_artifact_id") === aid)
    const succeeded = evalsForArt.filter((r) => readRecordString(r, "status") === "succeeded")
    let latestEvalSummary = "—"
    if (succeeded.length > 0) {
      const best = succeeded.reduce((acc, r) => {
        const id = readRecordNumber(r, "id") ?? 0
        const accId = readRecordNumber(acc, "id") ?? 0
        return id > accId ? r : acc
      })
      const eid = readRecordNumber(best, "id")
      const mj = best["metrics_json"]
      latestEvalSummary = `evaluation_run_id ${eid ?? "—"}; metrics_json ${summarizeJson(mj)}`
    }
    const calFor = calibrationRows.filter((r) => readRecordNumber(r, "model_artifact_id") === aid)
    const oodFor = oodRows.filter((r) => readRecordNumber(r, "model_artifact_id") === aid)
    let calibrationLine = "—"
    if (calFor.length > 0) {
      const row = calFor.reduce((acc, r) => {
        const id = readRecordNumber(r, "id") ?? 0
        const accId = readRecordNumber(acc, "id") ?? 0
        return id > accId ? r : acc
      })
      calibrationLine = `status ${readRecordString(row, "status") ?? "—"}; method ${readRecordString(row, "calibration_method") ?? "—"}`
    }
    let oodLine = "—"
    if (oodFor.length > 0) {
      const row = oodFor.reduce((acc, r) => {
        const id = readRecordNumber(r, "id") ?? 0
        const accId = readRecordNumber(acc, "id") ?? 0
        return id > accId ? r : acc
      })
      oodLine = `status ${readRecordString(row, "status") ?? "—"}; method ${readRecordString(row, "method") ?? "—"}`
    }
    return {
      hasSucceededEval: succeeded.length > 0,
      hasCalibration: calFor.length > 0,
      hasOod: oodFor.length > 0,
      latestEvalSummary,
      calibrationLine,
      oodLine,
    }
  }, [selectedArtifactId, evalRuns, calibrationRows, oodRows])

  const selectedCard = useMemo(() => {
    if (!selected) return null
    const cid = readRecordNumber(selected, "model_card_id")
    if (cid == null) return null
    return modelCards.find((c) => readRecordNumber(c, "id") === cid) ?? null
  }, [selected, modelCards])

  const selectedArtifact = useMemo(() => {
    if (selectedArtifactId == null) return null
    return artifacts.find((a) => readRecordNumber(a, "id") === selectedArtifactId) ?? null
  }, [artifacts, selectedArtifactId])

  const canSubmitApprove =
    selected &&
    REVIEWABLE_STATUSES.includes(readRecordString(selected, "status") as (typeof REVIEWABLE_STATUSES)[number]) &&
    readRecordNumber(selected, "model_card_id") != null &&
    approveComment.trim().length > 0

  const missingGateWarnings = useMemo(() => {
    const w: string[] = []
    if (!gateChecks.hasSucceededEval) {
      w.push("No succeeded evaluation run is associated with this model_artifact_id; the approve endpoint is expected to reject approval until one exists.")
    }
    if (!gateChecks.hasCalibration) {
      w.push("No calibration assessment found for this artifact.")
    }
    if (!gateChecks.hasOod) {
      w.push("No out-of-domain assessment found for this artifact.")
    }
    return w
  }, [gateChecks])

  async function submitCreate() {
    setCreateErr("")
    setCreateOk("")
    const aid = Number.parseInt(createArtifactId, 10)
    const cid = Number.parseInt(createCardId, 10)
    if (!Number.isFinite(aid) || aid < 1) {
      setCreateErr("model_artifact_id is required.")
      return
    }
    if (!Number.isFinite(cid) || cid < 1) {
      setCreateErr("model_card_id is required (backend rejects null).")
      return
    }
    const endpoint = createEndpoint.trim() || null
    setCreateBusy(true)
    try {
      await apiFetch("/ml/deployment-candidates", {
        method: "POST",
        body: {
          model_artifact_id: aid,
          model_card_id: cid,
          target_module: createTargetModule,
          target_endpoint: endpoint,
          status: "proposed",
          metadata_json: {},
        },
      })
      const cardPick = cardsForArtifact.find((r) => readRecordNumber(r, "id") === cid)
      trackMlDeploymentCandidateCreated({
        target_module: createTargetModule,
        status: "proposed",
        has_model_card: true,
        approval_status: readRecordString(cardPick ?? {}, "approval_status") || undefined,
      })
      setCreateOk("Deployment candidate created as proposed; human approval is still required.")
      setReload((x) => x + 1)
    } catch (er) {
      setCreateErr(formatApiError(er, "Could not create deployment candidate."))
    } finally {
      setCreateBusy(false)
    }
  }

  async function submitApprove() {
    if (!selected || selectedId == null) return
    setApproveErr("")
    if (!canSubmitApprove) {
      setApproveErr("Approval requires model_card_id and a non-empty reviewer_comment.")
      return
    }
    setApproveBusy(true)
    try {
      await apiFetch(`/ml/deployment-candidates/${selectedId}/approve`, {
        method: "POST",
        body: {
          reviewer_name: approveName.trim() || "reviewer",
          reviewer_comment: approveComment.trim(),
          status: approveLevel,
          metadata_json: {},
        },
      })
      trackMlDeploymentCandidateApproved({
        target_module: readRecordString(selected, "target_module") || undefined,
        status: approveLevel,
        has_model_card: selectedCard != null,
        approval_status: selectedCard ? readRecordString(selectedCard, "approval_status") || undefined : undefined,
      })
      setApproveComment("")
      setReload((x) => x + 1)
    } catch (er) {
      setApproveErr(formatApiError(er, "Approval request failed."))
    } finally {
      setApproveBusy(false)
    }
  }

  async function submitReject() {
    if (!selected || selectedId == null) return
    setRejectErr("")
    const rc = rejectReason.trim()
    if (!rc) {
      setRejectErr("rejection reason is required (sent as reviewer_comment).")
      return
    }
    if (!REVIEWABLE_STATUSES.includes(readRecordString(selected, "status") as (typeof REVIEWABLE_STATUSES)[number])) {
      setRejectErr("This candidate is not in a reviewable status.")
      return
    }
    setRejectBusy(true)
    try {
      await apiFetch(`/ml/deployment-candidates/${selectedId}/reject`, {
        method: "POST",
        body: {
          reviewer_name: rejectName.trim() || "reviewer",
          reviewer_comment: rc,
          metadata_json: {},
        },
      })
      trackMlDeploymentCandidateRejected({
        target_module: readRecordString(selected, "target_module") || undefined,
        status: "rejected",
        has_model_card: selectedCard != null,
        approval_status: selectedCard ? readRecordString(selectedCard, "approval_status") || undefined : undefined,
      })
      setRejectReason("")
      setReload((x) => x + 1)
    } catch (er) {
      setRejectErr(formatApiError(er, "Reject request failed."))
    } finally {
      setRejectBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <Button variant="ghost" size="sm" className="mb-1 h-8 px-2" asChild>
            <Link href="/ml" className="inline-flex items-center gap-1 text-muted-foreground">
              <ArrowLeft className="h-4 w-4" aria-hidden />
              ML Model Factory
            </Link>
          </Button>
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-teal-ink)" }}
          >
            MolTrace · ML Deployment Candidates
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Deployment candidate review</h1>
          <p className="text-sm text-muted-foreground">
            Create deployment candidates, then record human approval or rejection. Registry status updates only through the approve and reject endpoints—nothing here activates production routing.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      <Alert>
        <AlertTriangle className="h-4 w-4" aria-hidden />
        <AlertTitle className="text-sm">Human gate</AlertTitle>
        <AlertDescription className="text-sm text-muted-foreground">
          Approving or rejecting here only updates the registry status. A separate prediction-service deployment step is required before any model can serve real traffic.
        </AlertDescription>
      </Alert>

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => setReload((x) => x + 1)}>
          {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : <RefreshCw className="mr-2 h-4 w-4" aria-hidden />}
          Refresh
        </Button>
      </div>

      {errLoad ? (
        <Alert variant="destructive">
          <AlertTitle>Load error</AlertTitle>
          <AlertDescription>{errLoad}</AlertDescription>
        </Alert>
      ) : null}

      <ModuleCard
        accent="teal"
        eyebrow="Create"
        title="Create deployment candidate"
        icon={Plus}
        description="Submit a model artifact and its approved model card for deployment review. New candidates start in &ldquo;proposed&rdquo; status."
      >
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>model_artifact_id</Label>
              <Select
                value={createArtifactId || undefined}
                onValueChange={(v) => {
                  setCreateArtifactId(v)
                  setCreateCardId("")
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select artifact" />
                </SelectTrigger>
                <SelectContent>
                  {artifacts.map((row) => {
                    const id = readRecordNumber(row, "id")
                    if (id == null) return null
                    return (
                      <SelectItem key={id} value={String(id)}>
                        {artifactLabel(row)}
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>model_card_id</Label>
              <Select value={createCardId || undefined} onValueChange={setCreateCardId} disabled={!createArtifactId}>
                <SelectTrigger>
                  <SelectValue placeholder={createArtifactId ? "Select model card" : "Choose artifact first"} />
                </SelectTrigger>
                <SelectContent>
                  {cardsForArtifact.map((row) => {
                    const id = readRecordNumber(row, "id")
                    if (id == null) return null
                    return (
                      <SelectItem key={id} value={String(id)}>
                        #{id} {readRecordString(row, "approval_status") ?? ""}
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>target_module</Label>
              <Select value={createTargetModule} onValueChange={setCreateTargetModule}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TARGET_MODULES.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="te">target_endpoint (optional)</Label>
              <Input id="te" value={createEndpoint} onChange={(e) => setCreateEndpoint(e.target.value)} autoComplete="off" />
            </div>
          </div>
          {createErr ? <p className="text-sm text-destructive">{createErr}</p> : null}
          {createOk ? <p className="text-sm text-muted-foreground">{createOk}</p> : null}
          <Button type="button" disabled={createBusy || loading} onClick={() => void submitCreate()}>
            {createBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Create candidate
          </Button>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Records"
        title="Candidates"
        icon={ListChecks}
        description="All proposed and reviewed deployment candidates. Click a row to review and record an approval or rejection."
      >
        <div className="space-y-4">
          <div className="table-scroll min-w-0">
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : candidates.length === 0 ? (
              <p className="text-sm text-muted-foreground">No deployment candidates.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[72px]">id</TableHead>
                    <TableHead>model_artifact_id</TableHead>
                    <TableHead>model_card_id</TableHead>
                    <TableHead>target_module</TableHead>
                    <TableHead>status</TableHead>
                    <TableHead>artifact status</TableHead>
                    <TableHead className="w-[90px]" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {candidates.map((row, idx) => {
                    const id = readRecordNumber(row, "id")
                    const aid = readRecordNumber(row, "model_artifact_id")
                    const art = aid != null ? artifacts.find((a) => readRecordNumber(a, "id") === aid) : null
                    return (
                      <TableRow key={id != null ? `dc-${id}` : `dc-${idx}`}>
                        <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                        <TableCell className="font-mono text-xs">{aid ?? "—"}</TableCell>
                        <TableCell className="font-mono text-xs">{readRecordNumber(row, "model_card_id") ?? "—"}</TableCell>
                        <TableCell className="font-mono text-xs">{readRecordString(row, "target_module") ?? "—"}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
                        </TableCell>
                        <TableCell className="text-xs">{art ? <Badge variant="secondary">{readRecordString(art, "status") ?? "—"}</Badge> : "—"}</TableCell>
                        <TableCell>
                          {id != null ? (
                            <Button
                              type="button"
                              variant={selectedId === id ? "default" : "outline"}
                              size="sm"
                              onClick={() => setSelectedId(id)}
                            >
                              Select
                            </Button>
                          ) : null}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            )}
          </div>

          {selected ? (
            <div className="space-y-4 rounded-lg border p-4">
              <h3 className="text-sm font-medium">Selected candidate id {readRecordNumber(selected, "id") ?? "—"}</h3>

              <div className="rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">Deployment candidate {selectedId}</span>
                {getSnapshotLoading ? (
                  <Loader2 className="ml-2 inline h-3 w-3 animate-spin" aria-hidden />
                ) : getSnapshot ? (
                  <span className="ml-2">
                    registry_status {readRecordString(getSnapshot, "status") ?? "—"}; candidate_id{" "}
                    {readRecordNumber(getSnapshot, "candidate_id") ?? "—"}
                  </span>
                ) : (
                  <span className="ml-2">snapshot unavailable</span>
                )}
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Model artifact</p>
                  <p className="text-sm">{selectedArtifact ? artifactLabel(selectedArtifact) : "—"}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Model card (approval_status)</p>
                  <p className="text-sm">
                    {selectedCard ? (
                      <>
                        model_card_id {readRecordNumber(selectedCard, "id") ?? "—"} —{" "}
                        <Badge variant="outline">{readRecordString(selectedCard, "approval_status") ?? "—"}</Badge>
                      </>
                    ) : (
                      <span className="text-destructive">model_card_id missing — approval cannot proceed.</span>
                    )}
                  </p>
                </div>
                <div className="sm:col-span-2">
                  <p className="text-xs font-medium text-muted-foreground">Evaluation summary (latest succeeded run)</p>
                  <p className="text-xs text-muted-foreground">{gateChecks.latestEvalSummary}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Calibration (latest assessment)</p>
                  <p className="text-xs text-muted-foreground">{gateChecks.calibrationLine}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">OOD (latest assessment)</p>
                  <p className="text-xs text-muted-foreground">{gateChecks.oodLine}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Deployment candidate status (registry)</p>
                  <Badge variant="outline">{readRecordString(selected, "status") ?? "—"}</Badge>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">target_endpoint</p>
                  <p className="font-mono text-xs">{readRecordString(selected, "target_endpoint") ?? "—"}</p>
                </div>
              </div>

              {(() => {
                const fromList = Array.isArray(selected["warnings"]) ? (selected["warnings"] as unknown[]) : []
                const fromGet = Array.isArray(getSnapshot?.["warnings"]) ? (getSnapshot?.["warnings"] as unknown[]) : []
                const merged = [...fromList]
                for (const w of fromGet) {
                  const s = typeof w === "string" ? w : summarizeJson(w)
                  if (!merged.some((x) => (typeof x === "string" ? x : summarizeJson(x)) === s)) merged.push(w)
                }
                if (merged.length === 0) return null
                return (
                  <div>
                    <p className="mb-1 text-xs font-medium text-muted-foreground">warnings</p>
                    <ul className="list-inside list-disc text-sm text-muted-foreground">
                      {merged.map((w, i) => (
                        <li key={`w-${i}`}>{typeof w === "string" ? w : summarizeJson(w)}</li>
                      ))}
                    </ul>
                  </div>
                )
              })()}

              {missingGateWarnings.length > 0 ? (
                <Alert>
                  <AlertTriangle className="h-4 w-4" aria-hidden />
                  <AlertTitle className="text-sm">Readiness checks</AlertTitle>
                  <AlertDescription>
                    <ul className="mt-2 list-inside list-disc text-sm text-muted-foreground">
                      {missingGateWarnings.map((m) => (
                        <li key={m}>{m}</li>
                      ))}
                    </ul>
                  </AlertDescription>
                </Alert>
              ) : null}

              <div>
                <p className="mb-1 text-xs font-medium text-muted-foreground">Reviewer fields on record</p>
                <p className="text-sm">
                  reviewer_name: {readRecordString(selected, "reviewer_name") ?? "—"}
                </p>
                <p className="mt-1 text-sm">
                  reviewer_comment: {readRecordString(selected, "reviewer_comment") ?? "—"}
                </p>
              </div>

              {selected && REVIEWABLE_STATUSES.includes(readRecordString(selected, "status") as (typeof REVIEWABLE_STATUSES)[number]) ? (
                <div className="grid gap-6 border-t pt-4 lg:grid-cols-2">
                  <div className="space-y-3">
                    <p className="text-sm font-medium">Approve candidate</p>
                    <div className="space-y-2">
                      <Label htmlFor="an">reviewer_name</Label>
                      <Input id="an" value={approveName} onChange={(e) => setApproveName(e.target.value)} autoComplete="name" />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="ac">reviewer_comment (required)</Label>
                      <Input id="ac" value={approveComment} onChange={(e) => setApproveComment(e.target.value)} />
                    </div>
                    <div className="space-y-2">
                      <Label>status (approval level)</Label>
                      <Select value={approveLevel} onValueChange={setApproveLevel}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="approved_for_internal_use">approved_for_internal_use</SelectItem>
                          <SelectItem value="approved_for_production">approved_for_production</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    {approveErr ? <p className="text-sm text-destructive">{approveErr}</p> : null}
                    <Button
                      type="button"
                      disabled={
                        approveBusy ||
                        !canSubmitApprove ||
                        !readRecordNumber(selected, "model_card_id")
                      }
                      onClick={() => void submitApprove()}
                    >
                      {approveBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                      Submit approval record
                    </Button>
                    {!readRecordNumber(selected, "model_card_id") ? (
                      <p className="text-xs text-destructive">Approve action disabled until model_card_id is present.</p>
                    ) : null}
                    {!approveComment.trim() ? (
                      <p className="text-xs text-muted-foreground">Enter reviewer_comment to enable approval.</p>
                    ) : null}
                  </div>

                  <div className="space-y-3">
                    <p className="text-sm font-medium">Reject candidate</p>
                    <div className="space-y-2">
                      <Label htmlFor="rn">reviewer_name</Label>
                      <Input id="rn" value={rejectName} onChange={(e) => setRejectName(e.target.value)} autoComplete="name" />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="rr">rejection reason → reviewer_comment (required)</Label>
                      <Input id="rr" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
                    </div>
                    {rejectErr ? <p className="text-sm text-destructive">{rejectErr}</p> : null}
                    <Button type="button" variant="destructive" disabled={rejectBusy || !rejectReason.trim()} onClick={() => void submitReject()}>
                      {rejectBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                      Submit rejection record
                    </Button>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  This candidate has already been reviewed. Approval and rejection forms are hidden; current status is shown above.
                </p>
              )}

              <DeveloperJsonPanel data={selected} />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Select a candidate to inspect gates and reviewer fields.</p>
          )}
        </div>
      </ModuleCard>
    </div>
  )
}
