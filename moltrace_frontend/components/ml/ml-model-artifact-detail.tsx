"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { trackMlModelCardCreated } from "@/src/lib/analytics/analytics-client"
import { ArrowLeft, Loader2, RefreshCw } from "lucide-react"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(row: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = row[k]
    if (typeof v === "string" && v.trim()) return v.trim()
    if (typeof v === "number" && Number.isFinite(v)) return String(v)
  }
  return ""
}

function readStringList(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.filter((x): x is string => typeof x === "string" && x.trim().length > 0)
}

function readMetadataWarnings(artifact: Record<string, unknown> | null): string[] {
  if (!artifact) return []
  const m = artifact["metadata_json"]
  if (!m || typeof m !== "object" || Array.isArray(m)) return []
  const w = (m as Record<string, unknown>)["warnings"]
  return readStringList(w)
}

const CARD_TOOLTIP =
  "Model cards document intended use, training data, evaluation, limitations, calibration, out-of-domain risk, and human review status."

const APPROVAL_OPTIONS = ["draft", "ready_for_review", "approved", "rejected", "deprecated"] as const

export function MlModelArtifactDetail() {
  const params = useParams()
  const rawId = params?.modelArtifactId
  const artifactIdNum =
    typeof rawId === "string" ? Number.parseInt(rawId, 10) : Array.isArray(rawId) ? Number.parseInt(rawId[0] ?? "", 10) : NaN

  const [reload, setReload] = useState(0)
  const [loading, setLoading] = useState(true)
  const [artifact, setArtifact] = useState<Record<string, unknown> | null>(null)
  const [errArtifact, setErrArtifact] = useState("")
  const [evalRuns, setEvalRuns] = useState<Record<string, unknown>[]>([])
  const [errEval, setErrEval] = useState("")
  const [cards, setCards] = useState<Record<string, unknown>[]>([])
  const [errCards, setErrCards] = useState("")
  const [deployments, setDeployments] = useState<Record<string, unknown>[]>([])
  const [errDeploy, setErrDeploy] = useState("")

  const [createBusy, setCreateBusy] = useState(false)
  const [createErr, setCreateErr] = useState("")
  const [createOk, setCreateOk] = useState("")
  const [intendedUse, setIntendedUse] = useState("")
  const [limitations, setLimitations] = useState("")
  const [trainingSummaryJson, setTrainingSummaryJson] = useState("{}")
  const [evaluationSummaryJson, setEvaluationSummaryJson] = useState("{}")
  const [biasJson, setBiasJson] = useState("{}")
  const [oodJson, setOodJson] = useState("{}")
  const [calibrationJson, setCalibrationJson] = useState("{}")
  const [humanReviewJson, setHumanReviewJson] = useState("{}")
  const [approvalDraft, setApprovalDraft] = useState<string>("draft")

  const loadAll = useCallback(async () => {
    if (!Number.isFinite(artifactIdNum) || artifactIdNum < 1) {
      setLoading(false)
      return
    }
    setLoading(true)
    setErrArtifact("")
    setErrEval("")
    setErrCards("")
    setErrDeploy("")

    try {
      const a = await apiFetch<unknown>(`/ml/model-artifacts/${artifactIdNum}`, { method: "GET" })
      setArtifact(isRecord(a) ? a : null)
    } catch (e) {
      setErrArtifact(formatApiError(e, "Artifact not found."))
      setArtifact(null)
    }

    try {
      const er = await apiFetch<unknown>("/ml/evaluation-runs?limit=500", { method: "GET" })
      const all = Array.isArray(er) ? er.filter(isRecord) : []
      setEvalRuns(
        (all as Record<string, unknown>[]).filter((r) => readRecordNumber(r, "model_artifact_id") === artifactIdNum),
      )
    } catch (e) {
      setErrEval(formatApiError(e, "Could not load evaluation runs."))
      setEvalRuns([])
    }

    try {
      const c = await apiFetch<unknown>(
        `/ml/model-cards?model_artifact_id=${encodeURIComponent(String(artifactIdNum))}&limit=50`,
        { method: "GET" },
      )
      setCards(Array.isArray(c) ? (c.filter(isRecord) as Record<string, unknown>[]) : [])
    } catch (e) {
      setErrCards(formatApiError(e, "Could not load model cards."))
      setCards([])
    }

    try {
      const d = await apiFetch<unknown>("/ml/deployment-candidates?limit=500", { method: "GET" })
      const all = Array.isArray(d) ? d.filter(isRecord) : []
      setDeployments(
        (all as Record<string, unknown>[]).filter((r) => readRecordNumber(r, "model_artifact_id") === artifactIdNum),
      )
    } catch (e) {
      setErrDeploy(formatApiError(e, "Could not load deployment candidates."))
      setDeployments([])
    }

    setLoading(false)
  }, [artifactIdNum])

  useEffect(() => {
    void loadAll()
  }, [loadAll, reload])

  const metaWarnings = useMemo(() => readMetadataWarnings(artifact), [artifact])

  async function createModelCard() {
    setCreateErr("")
    setCreateOk("")
    if (!artifact) return
    const tk = readRecordString(artifact, "task_key") ?? ""
    if (!intendedUse.trim() || !limitations.trim()) {
      setCreateErr("intended_use and limitations are required.")
      return
    }
    const parseObj = (raw: string, label: string): Record<string, unknown> => {
      try {
        const o = JSON.parse(raw.trim() || "{}") as unknown
        if (!o || typeof o !== "object" || Array.isArray(o)) throw new Error("object")
        return o as Record<string, unknown>
      } catch {
        throw new Error(label)
      }
    }
    let training_data_summary_json: Record<string, unknown>
    let evaluation_summary_json: Record<string, unknown>
    let bias_risk_summary_json: Record<string, unknown>
    let out_of_domain_summary_json: Record<string, unknown>
    let calibration_summary_json: Record<string, unknown>
    let human_review_summary_json: Record<string, unknown>
    try {
      training_data_summary_json = parseObj(trainingSummaryJson, "training_data_summary_json")
      evaluation_summary_json = parseObj(evaluationSummaryJson, "evaluation_summary_json")
      bias_risk_summary_json = parseObj(biasJson, "bias_risk_summary_json")
      out_of_domain_summary_json = parseObj(oodJson, "out_of_domain_summary_json")
      calibration_summary_json = parseObj(calibrationJson, "calibration_summary_json")
      human_review_summary_json = parseObj(humanReviewJson, "human_review_summary_json")
    } catch (e) {
      setCreateErr(e instanceof Error ? `${e.message} must be valid JSON objects.` : "Invalid JSON.")
      return
    }

    setCreateBusy(true)
    try {
      await apiFetch("/ml/model-cards", {
        method: "POST",
        body: {
          model_artifact_id: artifactIdNum,
          task_key: tk,
          intended_use: intendedUse.trim(),
          limitations: limitations.trim(),
          training_data_summary_json,
          evaluation_summary_json,
          bias_risk_summary_json,
          out_of_domain_summary_json,
          calibration_summary_json,
          human_review_summary_json,
          approval_status: approvalDraft,
          metadata_json: {},
        },
      })
      const summaryBlobs = [
        training_data_summary_json,
        evaluation_summary_json,
        bias_risk_summary_json,
        out_of_domain_summary_json,
        calibration_summary_json,
        human_review_summary_json,
      ]
      trackMlModelCardCreated({
        task_key: tk,
        model_family: readStr(artifact, ["model_family"]),
        status: readStr(artifact, ["status"]) || undefined,
        approval_status: approvalDraft,
        has_model_card: true,
        metric_count: summaryBlobs.filter((o) => Object.keys(o).length > 0).length,
        warning_count: readMetadataWarnings(artifact).length,
      })
      setCreateOk("Model card created.")
      setReload((x) => x + 1)
    } catch (e) {
      setCreateErr(formatApiError(e, "Could not create model card."))
    } finally {
      setCreateBusy(false)
    }
  }

  if (!Number.isFinite(artifactIdNum) || artifactIdNum < 1) {
    return (
      <div className="p-6">
        <p className="text-sm text-destructive">Invalid model artifact id.</p>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <Button variant="ghost" size="sm" className="h-8 px-2" asChild>
              <Link href="/ml/models" className="inline-flex items-center gap-1 text-muted-foreground">
                <ArrowLeft className="h-4 w-4" aria-hidden />
                Model artifacts
              </Link>
            </Button>
          </div>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Model artifact</h1>
          <p className="font-mono text-sm text-muted-foreground">id {artifactIdNum}</p>
        </div>
        <BackendStatusIndicator />
      </div>

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => setReload((x) => x + 1)}>
          {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : <RefreshCw className="mr-2 h-4 w-4" aria-hidden />}
          Refresh
        </Button>
      </div>

      {errArtifact ? (
        <Alert variant="destructive">
          <AlertTitle>GET /ml/model-artifacts/{"{model_artifact_id}"}</AlertTitle>
          <AlertDescription>{errArtifact}</AlertDescription>
        </Alert>
      ) : null}

      {!artifact && !errArtifact && !loading ? (
        <p className="text-sm text-muted-foreground">No artifact loaded.</p>
      ) : null}

      {artifact ? (
        <>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg">Summary</CardTitle>
              <CardDescription>Operational fields from the API — release claims follow approval_status on model cards.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">model_name / model_version</p>
                <p className="text-sm font-medium">
                  {readRecordString(artifact, "model_name") ?? "—"} · {readRecordString(artifact, "model_version") ?? "—"}
                </p>
              </div>
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">task_key</p>
                <p className="font-mono text-sm">{readRecordString(artifact, "task_key") ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">model_family</p>
                <p className="font-mono text-sm">{readRecordString(artifact, "model_family") ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">training_run_id</p>
                <p className="font-mono text-sm">{readRecordNumber(artifact, "training_run_id") ?? "—"}</p>
              </div>
              <div className="sm:col-span-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">artifact_sha256</p>
                <p className="break-all font-mono text-xs">{readRecordString(artifact, "artifact_sha256") ?? "—"}</p>
              </div>
              <div className="sm:col-span-2">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">model_hash</p>
                <p className="break-all font-mono text-xs">{readRecordString(artifact, "model_hash") ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">status</p>
                <Badge variant="secondary">{readRecordString(artifact, "status") ?? "—"}</Badge>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg">Evaluation runs</CardTitle>
              <CardDescription>
                Evaluation runs filtered to this model artifact — status and dataset version for each completed or pending evaluation.
              </CardDescription>
            </CardHeader>
            <CardContent className="table-scroll min-w-0">
              {errEval ? (
                <p className="text-sm text-destructive">{errEval}</p>
              ) : evalRuns.length === 0 ? (
                <p className="text-sm text-muted-foreground">No matching evaluation runs.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[72px]">id</TableHead>
                      <TableHead>status</TableHead>
                      <TableHead>dataset_version_id</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {evalRuns.slice(0, 50).map((row, idx) => {
                      const id = readRecordNumber(row, "id")
                      return (
                        <TableRow key={id != null ? `ev-${id}` : `ev-${idx}`}>
                          <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                          <TableCell>
                            <Badge variant="outline">{readStr(row, ["status"]) || "—"}</Badge>
                          </TableCell>
                          <TableCell className="font-mono text-xs">
                            {readRecordNumber(row, "dataset_version_id") ?? "—"}
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
            <CardHeader className="pb-2">
              <CardTitle className="text-lg">Model card</CardTitle>
              <CardDescription className="flex flex-wrap items-center gap-2">
                <span>Structured model card for this artifact — intended use, limitations, training data summary, and evaluation summary.</span>
                <span className="inline-flex shrink-0">
                  <InfoTooltip content={CARD_TOOLTIP} label="About model cards" />
                </span>
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {errCards ? <p className="text-sm text-destructive">{errCards}</p> : null}
              {cards.length > 0 ? (
                <ul className="space-y-2 text-sm">
                  {cards.map((c, i) => {
                    const cid = readRecordNumber(c, "id")
                    const st = readRecordString(c, "approval_status")
                    return (
                      <li key={cid ?? i}>
                        {cid != null ? (
                          <Link className="font-medium text-primary underline-offset-4 hover:underline" href={`/ml/model-cards/${cid}`}>
                            Model card #{cid}
                          </Link>
                        ) : (
                          "—"
                        )}
                        {st ? (
                          <span className="ml-2 text-muted-foreground">
                            approval_status: <span className="font-mono text-xs">{st}</span>
                          </span>
                        ) : null}
                      </li>
                    )
                  })}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">No model cards for this artifact.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg">Deployment candidates</CardTitle>
              <CardDescription>
                Deployment candidate records for this artifact — open the ML factory dashboard for the full deployment workflow.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {errDeploy ? <p className="text-sm text-destructive">{errDeploy}</p> : null}
              {deployments.length === 0 ? (
                <p className="text-sm text-muted-foreground">No deployment candidates for this artifact.</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {deployments.map((d, i) => {
                    const cid = readRecordNumber(d, "id")
                    const st = readRecordString(d, "status")
                    return (
                      <li key={cid ?? i} className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs">candidate_id {cid ?? "—"}</span>
                        <Badge variant="outline">{st ?? "—"}</Badge>
                        <Link className="text-xs text-primary underline-offset-4 hover:underline" href="/ml">
                          ML factory dashboard
                        </Link>
                      </li>
                    )
                  })}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-lg">Warnings</CardTitle>
              <CardDescription>From artifact metadata_json when present.</CardDescription>
            </CardHeader>
            <CardContent>
              {metaWarnings.length ? (
                <ul className="list-inside list-disc text-sm text-muted-foreground">
                  {metaWarnings.map((w, i) => (
                    <li key={`w-${i}`}>{w}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">—</p>
              )}
            </CardContent>
          </Card>

          <DeveloperJsonPanel data={artifact} />

          {cards.length === 0 ? (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-lg flex items-center gap-2">
                  Create model card
                  <InfoTooltip content={CARD_TOOLTIP} label="About model cards" />
                </CardTitle>
                <CardDescription>
                  Draft a structured model card capturing intended use, limitations, training data summary, and evaluation summary for governance review.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="iu">intended_use</Label>
                  <Textarea id="iu" value={intendedUse} onChange={(e) => setIntendedUse(e.target.value)} rows={4} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="lim">limitations</Label>
                  <Textarea id="lim" value={limitations} onChange={(e) => setLimitations(e.target.value)} rows={4} />
                </div>
                <JsonField label="training_data_summary_json" value={trainingSummaryJson} onChange={setTrainingSummaryJson} />
                <JsonField label="evaluation_summary_json" value={evaluationSummaryJson} onChange={setEvaluationSummaryJson} />
                <JsonField label="bias_risk_summary_json" value={biasJson} onChange={setBiasJson} />
                <JsonField label="out_of_domain_summary_json" value={oodJson} onChange={setOodJson} />
                <JsonField label="calibration_summary_json" value={calibrationJson} onChange={setCalibrationJson} />
                <JsonField label="human_review_summary_json" value={humanReviewJson} onChange={setHumanReviewJson} />
                <div className="space-y-2">
                  <Label>approval_status</Label>
                  <Select value={approvalDraft} onValueChange={setApprovalDraft}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {APPROVAL_OPTIONS.map((o) => (
                        <SelectItem key={o} value={o}>
                          {o}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {createErr ? <p className="text-sm text-destructive">{createErr}</p> : null}
                {createOk ? <p className="text-sm text-muted-foreground">{createOk}</p> : null}
                <Button type="button" disabled={createBusy || loading} onClick={() => void createModelCard()}>
                  {createBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                  Create model card
                </Button>
              </CardContent>
            </Card>
          ) : (
            <p className="text-xs text-muted-foreground">
              Update fields on the{" "}
              {readRecordNumber(cards[0] ?? {}, "id") != null ? (
                <Link
                  className="font-medium text-primary underline-offset-4 hover:underline"
                  href={`/ml/model-cards/${readRecordNumber(cards[0] ?? {}, "id")}`}
                >
                  model card page
                </Link>
              ) : (
                "model card page"
              )}
              .
            </p>
          )}
        </>
      ) : null}
    </div>
  )
}

function JsonField({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={label}>{label}</Label>
      <Textarea id={label} className="min-h-[80px] font-mono text-xs" value={value} onChange={(e) => onChange(e.target.value)} spellCheck={false} />
    </div>
  )
}
