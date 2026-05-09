"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import {
  trackAiCanaryDeploymentApproved,
  trackAiCanaryDeploymentCreated,
  trackAiCanaryDeploymentRejected,
} from "@/src/lib/analytics/analytics-client"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { AlertTriangle, Loader2, RefreshCw } from "lucide-react"

type Row = Record<string, unknown>

const CANARY_KEYS = ["canary_deployments", "items", "results", "rows", "data"]
const ARTIFACT_KEYS = ["model_artifacts", "items", "results", "rows", "data"]
const CARD_KEYS = ["model_cards", "items", "results", "rows", "data"]
const EVAL_KEYS = ["evaluation_runs", "items", "results", "rows", "data"]

function isRecord(v: unknown): v is Row {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function extractRows(data: unknown, keys: string[]): Row[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Row[]
  if (!isRecord(data)) return []
  for (const key of keys) {
    const value = data[key]
    if (Array.isArray(value)) return value.filter(isRecord) as Row[]
  }
  return []
}

function formatErr(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const data = err.data
    if (isRecord(data) && typeof data.detail === "string" && data.detail.trim()) return data.detail
    return `HTTP ${err.status}: ${err.message || fallback}`
  }
  if (err instanceof Error) return err.message
  return fallback
}

function formatWhen(iso: string): string {
  if (iso === "-") return iso
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return iso
  return new Date(t).toLocaleString()
}

function readStr(row: Row, keys: string[]): string {
  for (const key of keys) {
    const value = row[key]
    if (typeof value === "string" && value.trim()) return value.trim()
    if (typeof value === "number" && Number.isFinite(value)) return String(value)
  }
  return "-"
}

export function AiCanaryDeploymentsWorkspace() {
  const [loading, setLoading] = useState(true)
  const [reloadToken, setReloadToken] = useState(0)
  const [rows, setRows] = useState<Row[]>([])
  const [artifacts, setArtifacts] = useState<Row[]>([])
  const [modelCards, setModelCards] = useState<Row[]>([])
  const [evaluationRuns, setEvaluationRuns] = useState<Row[]>([])
  const [selectedDetail, setSelectedDetail] = useState<Row | null>(null)
  const [loadErr, setLoadErr] = useState("")
  const [detailErr, setDetailErr] = useState("")

  const [serviceKey, setServiceKey] = useState("")
  const [candidateModelArtifact, setCandidateModelArtifact] = useState("")
  const [targetModule, setTargetModule] = useState("spectracheck")
  const [trafficPercent, setTrafficPercent] = useState("5")
  const [submitBusy, setSubmitBusy] = useState(false)
  const [formErr, setFormErr] = useState("")
  const [formOk, setFormOk] = useState("")

  const [reviewerName, setReviewerName] = useState("")
  const [reviewerComment, setReviewerComment] = useState("")
  const [actionBusyId, setActionBusyId] = useState<number | null>(null)
  const [actionErr, setActionErr] = useState("")

  const candidateArtifactId = Number.parseInt(candidateModelArtifact, 10)
  const hasModelCard = useMemo(
    () => Number.isFinite(candidateArtifactId) && modelCards.some((r) => readRecordNumber(r, "model_artifact_id") === candidateArtifactId),
    [candidateArtifactId, modelCards],
  )
  const hasEvaluation = useMemo(
    () =>
      Number.isFinite(candidateArtifactId) &&
      evaluationRuns.some(
        (r) =>
          readRecordNumber(r, "model_artifact_id") === candidateArtifactId &&
          (readRecordString(r, "status") || "").toLowerCase() === "succeeded",
      ),
    [candidateArtifactId, evaluationRuns],
  )

  const load = useCallback(async () => {
    setLoading(true)
    setLoadErr("")
    try {
      const [canaryData, artifactData, cardData, evalData] = await Promise.all([
        apiFetch<unknown>("/ai/canary-deployments", { method: "GET" }),
        apiFetch<unknown>("/ml/model-artifacts", { method: "GET" }),
        apiFetch<unknown>("/ml/model-cards", { method: "GET" }),
        apiFetch<unknown>("/ml/evaluation-runs", { method: "GET" }),
      ])
      setRows(extractRows(canaryData, CANARY_KEYS))
      setArtifacts(extractRows(artifactData, ARTIFACT_KEYS))
      setModelCards(extractRows(cardData, CARD_KEYS))
      setEvaluationRuns(extractRows(evalData, EVAL_KEYS))
    } catch (err) {
      setLoadErr(formatErr(err, "Could not load canary deployment data."))
      setRows([])
      setArtifacts([])
      setModelCards([])
      setEvaluationRuns([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load, reloadToken])

  async function loadDetail(canaryId: string) {
    setDetailErr("")
    try {
      const data = await apiFetch<unknown>(`/ai/canary-deployments/${canaryId}`, { method: "GET" })
      setSelectedDetail(isRecord(data) ? data : null)
    } catch (err) {
      setSelectedDetail(null)
      setDetailErr(formatErr(err, `Could not load /ai/canary-deployments/${canaryId}.`))
    }
  }

  async function proposeCanary() {
    setFormErr("")
    setFormOk("")
    const artifactId = Number.parseInt(candidateModelArtifact, 10)
    const traffic = Number.parseFloat(trafficPercent)
    if (!serviceKey.trim() || !targetModule.trim() || !Number.isFinite(artifactId) || artifactId < 1 || !Number.isFinite(traffic)) {
      setFormErr("service key, candidate model artifact, target module, and traffic percent are required.")
      return
    }
    setSubmitBusy(true)
    try {
      await apiFetch("/ai/canary-deployments", {
        method: "POST",
        body: {
          service_key: serviceKey.trim(),
          candidate_model_artifact: artifactId,
          target_module: targetModule.trim(),
          traffic_percent: traffic,
        },
      })
      trackAiCanaryDeploymentCreated({
        service_key: serviceKey.trim(),
        target_module: targetModule.trim(),
        status: "proposed",
      })
      setFormOk("Canary deployment proposed.")
      setReloadToken((x) => x + 1)
    } catch (err) {
      setFormErr(formatErr(err, "Could not propose canary deployment."))
    } finally {
      setSubmitBusy(false)
    }
  }

  async function reviewCanary(canaryId: number, action: "approve" | "reject") {
    setActionErr("")
    if (!reviewerComment.trim()) {
      setActionErr("reviewer comment required.")
      return
    }
    setActionBusyId(canaryId)
    try {
      await apiFetch(`/ai/canary-deployments/${canaryId}/${action}`, {
        method: "POST",
        body: {
          reviewer_name: reviewerName.trim() || "reviewer",
          reviewer_comment: reviewerComment.trim(),
        },
      })
      if (action === "approve") {
        trackAiCanaryDeploymentApproved({
          service_key: serviceKey.trim() || undefined,
          target_module: targetModule.trim() || undefined,
          status: "approved",
        })
      } else {
        trackAiCanaryDeploymentRejected({
          service_key: serviceKey.trim() || undefined,
          target_module: targetModule.trim() || undefined,
          status: "rejected",
        })
      }
      setReloadToken((x) => x + 1)
    } catch (err) {
      setActionErr(formatErr(err, `Could not ${action} canary deployment ${canaryId}.`))
    } finally {
      setActionBusyId(null)
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Canary Deployments</h1>
        <p className="text-sm text-muted-foreground">Propose, review, and resolve canary deployments with human approval workflow.</p>
      </div>

      <Alert className="border-amber-500/30 bg-amber-500/10">
        <AlertTriangle className="h-4 w-4 text-amber-600" />
        <AlertTitle>Human review required</AlertTitle>
        <AlertDescription>Canary approval does not automatically activate a model unless backend policy explicitly performs activation.</AlertDescription>
      </Alert>

      {!hasModelCard || !hasEvaluation ? (
        <Alert className="border-amber-500/30 bg-amber-500/10">
          <AlertTriangle className="h-4 w-4 text-amber-600" />
          <AlertTitle>Missing readiness checks</AlertTitle>
          <AlertDescription>
            {`${!hasModelCard ? "Model card missing. " : ""}${!hasEvaluation ? "Succeeded evaluation missing." : ""}`.trim()}
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="flex items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => setReloadToken((x) => x + 1)} disabled={loading}>
          {loading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <RefreshCw className="mr-2 size-4" />} Refresh
        </Button>
      </div>

      {loadErr ? <p className="text-sm text-destructive">{loadErr}</p> : null}

      <Card>
        <CardHeader>
          <CardTitle>Propose canary deployment</CardTitle>
          <CardDescription>Route a fraction of live traffic to a candidate model artifact before promoting to full production.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {formErr ? <p className="text-sm text-destructive">{formErr}</p> : null}
          {formOk ? <p className="text-sm text-emerald-700">{formOk}</p> : null}
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2"><Label htmlFor="cd-service-key">service key</Label><Input id="cd-service-key" value={serviceKey} onChange={(e) => setServiceKey(e.target.value)} /></div>
            <div className="space-y-2">
              <Label htmlFor="cd-candidate-artifact">candidate model artifact</Label>
              <select
                id="cd-candidate-artifact"
                value={candidateModelArtifact}
                onChange={(e) => setCandidateModelArtifact(e.target.value)}
                className="h-10 w-full rounded-md border bg-background px-3 text-sm"
              >
                <option value="">Select artifact</option>
                {artifacts.map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  if (id == null) return null
                  return <option key={`${id}-${idx}`} value={String(id)}>{`#${id} ${readStr(row, ["model_name", "model_version"])}`}</option>
                })}
              </select>
            </div>
            <div className="space-y-2"><Label htmlFor="cd-target-module">target module</Label><Input id="cd-target-module" value={targetModule} onChange={(e) => setTargetModule(e.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="cd-traffic">traffic percent</Label><Input id="cd-traffic" value={trafficPercent} onChange={(e) => setTrafficPercent(e.target.value)} inputMode="decimal" /></div>
          </div>
          <Button type="button" onClick={() => void proposeCanary()} disabled={submitBusy}>
            {submitBusy ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
            Start/propose
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Canary deployments</CardTitle>
          <CardDescription>All proposed, active, and retired canary rollouts with their candidate artifact and traffic share.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 overflow-x-auto">
          <Table>
            <TableHeader><TableRow><TableHead>canary</TableHead><TableHead>service key</TableHead><TableHead>candidate artifact</TableHead><TableHead>status</TableHead><TableHead>created</TableHead><TableHead>actions</TableHead></TableRow></TableHeader>
            <TableBody>
              {rows.map((row, idx) => {
                const canaryId = readRecordNumber(row, "canary_id") ?? readRecordNumber(row, "id")
                const busy = canaryId != null && actionBusyId === canaryId
                return (
                  <TableRow key={`${canaryId ?? "row"}-${idx}`}>
                    <TableCell>{readStr(row, ["canary_id", "id"])}</TableCell>
                    <TableCell>{readStr(row, ["service_key"])}</TableCell>
                    <TableCell>{readStr(row, ["candidate_model_artifact"])}</TableCell>
                    <TableCell><Badge variant="outline">{readStr(row, ["status"])}</Badge></TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatWhen(readStr(row, ["created_at", "timestamp"]))}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        <Button size="sm" variant="outline" disabled={busy || canaryId == null} onClick={() => canaryId != null && void loadDetail(String(canaryId))}>Open</Button>
                        <Button size="sm" variant="outline" disabled={busy || canaryId == null} onClick={() => canaryId != null && void reviewCanary(canaryId, "approve")}>Approve</Button>
                        <Button size="sm" variant="outline" disabled={busy || canaryId == null} onClick={() => canaryId != null && void reviewCanary(canaryId, "reject")}>Reject</Button>
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
              {rows.length === 0 ? <TableRow><TableCell colSpan={6} className="text-muted-foreground">No canary deployments returned.</TableCell></TableRow> : null}
            </TableBody>
          </Table>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2"><Label htmlFor="cd-reviewer-name">reviewer name</Label><Input id="cd-reviewer-name" value={reviewerName} onChange={(e) => setReviewerName(e.target.value)} /></div>
            <div className="space-y-2"><Label htmlFor="cd-reviewer-comment">reviewer comment required</Label><Input id="cd-reviewer-comment" value={reviewerComment} onChange={(e) => setReviewerComment(e.target.value)} /></div>
          </div>
          {actionErr ? <p className="text-sm text-destructive">{actionErr}</p> : null}
          {detailErr ? <p className="text-sm text-destructive">{detailErr}</p> : null}
          {selectedDetail ? (
            <div className="rounded-md border bg-muted/20 p-3 text-sm">
              <p><span className="font-medium">canary:</span> {readRecordString(selectedDetail, "canary_id") ?? readRecordString(selectedDetail, "id") ?? "-"}</p>
              <p><span className="font-medium">status:</span> {readRecordString(selectedDetail, "status") ?? "-"}</p>
              <p><span className="font-medium">summary:</span> {readRecordString(selectedDetail, "summary") ?? "-"}</p>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}
