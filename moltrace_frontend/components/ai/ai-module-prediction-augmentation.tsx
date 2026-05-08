"use client"

import { useMemo, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import {
  trackAiActiveLearningCandidateCreated,
  trackAiPredictionFeedbackSubmitted,
  trackAiPredictionRunCompleted,
  trackAiPredictionRunStarted,
} from "@/src/lib/analytics/analytics-client"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { AlertTriangle, Loader2 } from "lucide-react"
import {
  EvidenceCard,
  type EvidenceModule,
  type EvidenceRiskLevel,
  type EvidenceStatus,
} from "@/components/science/evidence-card"

type ServiceOption = {
  id: string
  label: string
  serviceKey: string
  taskKey: string
}

type Props = {
  moduleKey: "spectracheck" | "reaction_optimization" | "regulatory" | "knowledge_extraction"
  moduleTitle: string
  serviceOptions: ServiceOption[]
  summarySeed?: Record<string, unknown>
}

type AnyRecord = Record<string, unknown>

function isRecord(v: unknown): v is AnyRecord {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
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

function confidenceBucket(value: unknown): string {
  let n: number | null = null
  if (typeof value === "number" && Number.isFinite(value)) n = value
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) n = Number(value)
  if (n == null) return "unknown"
  if (n <= 1) return n < 0.5 ? "low" : n < 0.8 ? "medium" : "high"
  return n < 50 ? "low" : n < 80 ? "medium" : "high"
}

function evidenceModuleFor(moduleKey: Props["moduleKey"]): EvidenceModule {
  if (moduleKey === "reaction_optimization") return "reactions"
  if (moduleKey === "knowledge_extraction") return "ai_services"
  return moduleKey
}

function evidenceStatusFor(status: string | undefined, humanReviewRequired: boolean): EvidenceStatus {
  const normalized = (status ?? "").trim().toLowerCase().replace(/\s+/g, "_")
  if (normalized === "approved") return "approved"
  if (normalized === "rejected") return "rejected"
  if (normalized === "contradiction") return "contradiction"
  if (humanReviewRequired || normalized === "pending_review" || normalized === "submitted") return "pending_review"
  if (normalized === "failed" || normalized === "error") return "unavailable"
  return "draft"
}

function evidenceRiskFor(prediction: AnyRecord | null, humanReviewRequired: boolean): EvidenceRiskLevel {
  if (!prediction) return "unknown"
  const ood =
    prediction.is_ood === true ||
    readRecordString(prediction, "ood_status")?.toLowerCase() === "ood" ||
    readRecordString(prediction, "is_ood")?.toLowerCase() === "true"
  if (ood) return "high"
  if (humanReviewRequired) return "medium"
  return "unknown"
}

export function AiModulePredictionAugmentation({
  moduleKey,
  moduleTitle,
  serviceOptions,
  summarySeed = {},
}: Props) {
  const [selectedServiceId, setSelectedServiceId] = useState(serviceOptions[0]?.id ?? "")
  const selected = useMemo(
    () => serviceOptions.find((s) => s.id === selectedServiceId) ?? serviceOptions[0],
    [selectedServiceId, serviceOptions],
  )

  const [inputSummaryJson, setInputSummaryJson] = useState(
    JSON.stringify(
      {
        ...summarySeed,
        module: moduleKey,
        note: "IDs and summaries only",
      },
      null,
      2,
    ),
  )
  const [artifactId, setArtifactId] = useState("")
  const [evidenceItemId, setEvidenceItemId] = useState("")
  const [compoundId, setCompoundId] = useState("")
  const [sessionId, setSessionId] = useState("")
  const [experimentalMode, setExperimentalMode] = useState(false)
  const [notes, setNotes] = useState("")
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState("")
  const [ok, setOk] = useState("")
  const [prediction, setPrediction] = useState<AnyRecord | null>(null)

  const [feedbackType, setFeedbackType] = useState("useful")
  const [feedbackComment, setFeedbackComment] = useState("")
  const [feedbackBusy, setFeedbackBusy] = useState(false)
  const [feedbackErr, setFeedbackErr] = useState("")
  const [feedbackOk, setFeedbackOk] = useState("")
  const [queueBusy, setQueueBusy] = useState(false)
  const [queueMsg, setQueueMsg] = useState("")

  const predictionId = readRecordString(prediction ?? {}, "prediction_id") ?? readRecordString(prediction ?? {}, "id")
  const confidence = readRecordNumber(prediction ?? {}, "confidence") ?? readRecordNumber(prediction ?? {}, "confidence_score")
  const predictionStatus = readRecordString(prediction ?? {}, "status")
  const humanReviewRequired =
    readRecordString(prediction ?? {}, "human_review_required")?.toLowerCase() === "true" ||
    (prediction?.human_review_required as boolean | undefined) === true

  async function runPrediction() {
    setErr("")
    setOk("")
    setPrediction(null)
    let parsedSummary: Record<string, unknown>
    try {
      const parsed = JSON.parse(inputSummaryJson.trim() || "{}") as unknown
      if (!isRecord(parsed)) {
        setErr("input summary JSON must be an object.")
        return
      }
      parsedSummary = parsed
    } catch {
      setErr("input summary JSON must be valid JSON.")
      return
    }
    trackAiPredictionRunStarted({
      service_key: selected.serviceKey,
      target_module: moduleKey,
      task_key: selected.taskKey,
      status: "started",
    })
    setBusy(true)
    try {
      const artifact = Number.parseInt(artifactId, 10)
      const evidence = Number.parseInt(evidenceItemId, 10)
      const compound = Number.parseInt(compoundId, 10)
      const session = Number.parseInt(sessionId, 10)
      const res = await apiFetch<unknown>("/ai/predictions", {
        method: "POST",
        body: {
          service_key: selected.serviceKey,
          target_module: moduleKey,
          task_key: selected.taskKey,
          input_summary_json: parsedSummary,
          artifact_id: Number.isFinite(artifact) && artifact > 0 ? artifact : null,
          evidence_item_id: Number.isFinite(evidence) && evidence > 0 ? evidence : null,
          compound_id: Number.isFinite(compound) && compound > 0 ? compound : null,
          session_id: Number.isFinite(session) && session > 0 ? session : null,
          experimental_mode: experimentalMode,
          notes: notes.trim() || null,
        },
      })
      if (isRecord(res)) {
        setPrediction(res)
        trackAiPredictionRunCompleted({
          service_key: selected.serviceKey,
          target_module: moduleKey,
          task_key: selected.taskKey,
          status: readRecordString(res, "status") ?? "submitted",
          confidence_bucket: confidenceBucket(res.confidence_score ?? res.confidence),
          ood_status: readRecordString(res, "ood_status") ?? readRecordString(res, "is_ood") ?? "unknown",
          warning_count: Array.isArray(res.warnings) ? res.warnings.length : 0,
        })
      }
      setOk("Prediction request submitted.")
    } catch (e) {
      setErr(formatErr(e, "Could not submit prediction request."))
    } finally {
      setBusy(false)
    }
  }

  async function submitFeedback() {
    if (!predictionId) return
    setFeedbackErr("")
    setFeedbackOk("")
    setFeedbackBusy(true)
    try {
      await apiFetch(`/ai/predictions/${encodeURIComponent(predictionId)}/feedback`, {
        method: "POST",
        body: {
          feedback_type: feedbackType,
          reviewer_comment: feedbackComment.trim() || null,
        },
      })
      trackAiPredictionFeedbackSubmitted({
        service_key: selected.serviceKey,
        target_module: moduleKey,
        task_key: selected.taskKey,
        feedback_type: feedbackType,
        status: "submitted",
      })
      setFeedbackOk("Prediction feedback submitted.")
    } catch (e) {
      setFeedbackErr(formatErr(e, "Could not submit prediction feedback."))
    } finally {
      setFeedbackBusy(false)
    }
  }

  async function queueLowConfidenceCase() {
    if (!predictionId) return
    setQueueMsg("")
    setQueueBusy(true)
    try {
      await apiFetch("/ai/active-learning/candidates", {
        method: "POST",
        body: {
          source_module: moduleKey,
          reason:
            confidence != null && confidence < 0.5
              ? "low_confidence_prediction"
              : "prediction_feedback_case",
          priority: confidence != null && confidence < 0.5 ? "high" : "medium",
          status: "new",
          linked_prediction: Number(predictionId),
          linked_model_improvement_item: null,
        },
      })
      trackAiActiveLearningCandidateCreated({
        target_module: moduleKey,
        active_learning_reason: confidence != null && confidence < 0.5 ? "low_confidence_prediction" : "prediction_feedback_case",
        status: "new",
      })
      setQueueMsg("Added to Active Learning Queue.")
    } catch (e) {
      setQueueMsg(formatErr(e, "Could not add to Active Learning Queue."))
    } finally {
      setQueueBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{moduleTitle}: Optional controlled AI prediction</CardTitle>
        <CardDescription>
          Optional augmentation only. Existing scientific workflows remain unchanged and human review is required.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Alert className="border-amber-500/30 bg-amber-500/10">
          <AlertTriangle className="h-4 w-4 text-amber-600" />
          <AlertDescription>Use IDs and summaries only. Do not include raw spectra, full structures, or source text.</AlertDescription>
        </Alert>

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label>Prediction service</Label>
            <Select value={selectedServiceId} onValueChange={setSelectedServiceId}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {serviceOptions.map((opt) => (
                  <SelectItem key={opt.id} value={opt.id}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Service key</Label>
            <Input value={selected.serviceKey} readOnly />
          </div>
          <div className="space-y-2">
            <Label>Task key</Label>
            <Input value={selected.taskKey} readOnly />
          </div>
          <div className="space-y-2">
            <Label>artifact ID optional</Label>
            <Input inputMode="numeric" value={artifactId} onChange={(e) => setArtifactId(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>evidence item ID optional</Label>
            <Input inputMode="numeric" value={evidenceItemId} onChange={(e) => setEvidenceItemId(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>compound ID optional</Label>
            <Input inputMode="numeric" value={compoundId} onChange={(e) => setCompoundId(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>session ID optional</Label>
            <Input inputMode="numeric" value={sessionId} onChange={(e) => setSessionId(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>experimental mode</Label>
            <Select value={experimentalMode ? "true" : "false"} onValueChange={(v) => setExperimentalMode(v === "true")}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="false">false</SelectItem>
                <SelectItem value="true">true</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="space-y-2">
          <Label>input summary JSON</Label>
          <Textarea rows={5} value={inputSummaryJson} onChange={(e) => setInputSummaryJson(e.target.value)} />
        </div>
        <div className="space-y-2">
          <Label>notes</Label>
          <Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional notes (no raw data)." />
        </div>
        {err ? <p className="text-sm text-destructive">{err}</p> : null}
        {ok ? <p className="text-sm text-emerald-700">{ok}</p> : null}
        <Button type="button" onClick={() => void runPrediction()} disabled={busy}>
          {busy ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
          Run approved AI model
        </Button>

        {prediction ? (
          <div className="space-y-3 rounded-md border p-3">
            <EvidenceCard
              title={`Prediction ${predictionId ?? "-"}`}
              module={evidenceModuleFor(moduleKey)}
              status={evidenceStatusFor(predictionStatus, humanReviewRequired)}
              confidence_score={confidence}
              confidence_label={confidenceBucket(confidence)}
              risk_level={evidenceRiskFor(prediction, humanReviewRequired)}
              summary={readRecordString(prediction, "prediction_result") ?? readRecordString(prediction, "result") ?? "Prediction result unavailable."}
              evidence_items={[
                `Service: ${selected.serviceKey}`,
                `Task: ${selected.taskKey}`,
                `Status: ${predictionStatus ?? "-"}`,
                `Model artifact: ${readRecordString(prediction, "model_artifact_id") ?? "-"}`,
                `Deployment candidate: ${readRecordString(prediction, "deployment_candidate_id") ?? "-"}`,
              ]}
              citations={[]}
              model_name={readRecordString(prediction, "model_name") ?? selected.label}
              model_version={readRecordString(prediction, "model_version") ?? readRecordString(prediction, "model_artifact_id")}
              last_updated_at={readRecordString(prediction, "updated_at") ?? readRecordString(prediction, "created_at")}
              review_status={humanReviewRequired ? "human review required" : "requires review"}
            />

            <div className="grid gap-2 md:grid-cols-3">
              <Select value={feedbackType} onValueChange={setFeedbackType}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="accepted">accepted</SelectItem>
                  <SelectItem value="rejected">rejected</SelectItem>
                  <SelectItem value="corrected">corrected</SelectItem>
                  <SelectItem value="uncertain">uncertain</SelectItem>
                  <SelectItem value="useful">useful</SelectItem>
                  <SelectItem value="not_useful">not_useful</SelectItem>
                  <SelectItem value="error_case">error_case</SelectItem>
                  <SelectItem value="other">other</SelectItem>
                </SelectContent>
              </Select>
              <Input value={feedbackComment} onChange={(e) => setFeedbackComment(e.target.value)} placeholder="Feedback comment" />
              <div className="flex gap-2">
                <Button type="button" variant="outline" onClick={() => void submitFeedback()} disabled={feedbackBusy}>
                  {feedbackBusy ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
                  Feedback
                </Button>
                <Button type="button" variant="outline" onClick={() => void queueLowConfidenceCase()} disabled={queueBusy}>
                  {queueBusy ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
                  Add to Active Learning Queue
                </Button>
              </div>
            </div>
            {feedbackErr ? <p className="text-sm text-destructive">{feedbackErr}</p> : null}
            {feedbackOk ? <p className="text-sm text-emerald-700">{feedbackOk}</p> : null}
            {queueMsg ? <p className="text-sm text-muted-foreground">{queueMsg}</p> : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
