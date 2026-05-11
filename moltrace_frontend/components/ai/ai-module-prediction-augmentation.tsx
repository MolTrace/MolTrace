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
import { ModuleCard } from "@/components/dashboard/module-card"
import { cn } from "@/lib/utils"
import { AlertTriangle, BarChart3, Brain, Loader2, Settings2, Sparkles, Zap } from "lucide-react"
import {
  EvidenceCard,
  type EvidenceModule,
  type EvidenceRiskLevel,
  type EvidenceStatus,
} from "@/components/science/evidence-card"

type ModuleKey = "spectracheck" | "reaction_optimization" | "regulatory" | "knowledge_extraction"

const MODULE_ACCENT: Record<ModuleKey, "teal" | "violet" | "cyan" | "amber"> = {
  spectracheck: "teal",
  reaction_optimization: "violet",
  regulatory: "cyan",
  knowledge_extraction: "amber",
}

const MODULE_VAR: Record<ModuleKey, string> = {
  spectracheck: "var(--mt-teal)",
  reaction_optimization: "var(--mt-violet)",
  regulatory: "var(--mt-cyan)",
  knowledge_extraction: "var(--mt-amber)",
}

const MODULE_LABEL: Record<ModuleKey, string> = {
  spectracheck: "SpectraCheck",
  reaction_optimization: "Reaction Optimization",
  regulatory: "Regulatory",
  knowledge_extraction: "Knowledge Extraction",
}

type ServiceOption = {
  id: string
  label: string
  serviceKey: string
  taskKey: string
}

type Props = {
  moduleKey: ModuleKey
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

  const accent = MODULE_ACCENT[moduleKey]
  const accentColor = MODULE_VAR[moduleKey]
  const moduleLabel = MODULE_LABEL[moduleKey]

  return (
    <div className="space-y-6">
      {/* Section header — eyebrow + h2 + subtitle (consistent with all other modules) */}
      <div className="space-y-1">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: accentColor }}
        >
          {moduleLabel} · Optional AI Prediction
        </p>
        <h2 className="inline-flex items-center gap-2 font-mono text-xl font-bold tracking-tight">
          <Brain className="h-5 w-5" style={{ color: accentColor }} aria-hidden />
          {moduleTitle}: Optional controlled AI prediction
        </h2>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Optional augmentation only. Existing scientific workflows remain unchanged and human review is required.
        </p>
      </div>

      {/* Safety alert — banner above all steps */}
      <Alert className="border-amber-500/30 bg-amber-500/10">
        <AlertTriangle className="h-4 w-4 text-amber-600" />
        <AlertDescription>Use IDs and summaries only. Do not include raw spectra, full structures, or source text.</AlertDescription>
      </Alert>

      {/* Step 1 — Setup */}
      <ModuleCard
        accent={accent}
        eyebrow={`${moduleLabel} AI · Step 1 · Setup`}
        title="Configure prediction inputs"
        icon={Settings2}
        description="Pick a service, attach optional ID anchors (artifact / evidence / compound / session), then provide an input summary JSON. IDs and summaries only — never raw data."
        className="min-w-0"
      >
        <div className="space-y-5">
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
              <Input value={selected.serviceKey} readOnly className="font-mono text-xs" />
            </div>
            <div className="space-y-2">
              <Label>Task key</Label>
              <Input value={selected.taskKey} readOnly className="font-mono text-xs" />
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
            <Textarea rows={5} value={inputSummaryJson} onChange={(e) => setInputSummaryJson(e.target.value)} className="font-mono text-xs" />
          </div>
          <div className="space-y-2">
            <Label>notes</Label>
            <Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional notes (no raw data)." />
          </div>
        </div>
      </ModuleCard>

      {/* Step 2 — Run */}
      <ModuleCard
        accent={accent}
        eyebrow={`${moduleLabel} AI · Step 2 · Run`}
        title="Run approved AI model"
        icon={Zap}
        description="Submit the prediction request to the controlled AI service. Returns a draft prediction that requires human review before use."
        className="min-w-0"
      >
        <div className="space-y-4">
          <button
            type="button"
            onClick={() => void runPrediction()}
            disabled={busy}
            aria-label="Run approved AI model"
            className={cn(
              "group relative flex w-full flex-col items-start gap-2 overflow-hidden rounded-xl border p-4 text-left transition-all",
              "hover:-translate-y-px hover:shadow-md",
              busy ? "cursor-wait opacity-70" : "hover:shadow-md",
            )}
            style={{
              borderTop: `3px solid ${accentColor}`,
              borderColor: `${accentColor}66`,
              backgroundColor: `color-mix(in oklab, ${accentColor} 12%, transparent)`,
            }}
          >
            <div className="flex w-full items-center justify-between">
              <span
                className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                style={{ color: accentColor }}
              >
                <Sparkles className="h-3.5 w-3.5" aria-hidden />
                Predict
              </span>
              <span
                className="font-mono text-[10px] font-bold uppercase tracking-[0.12em]"
                style={{ color: accentColor }}
              >
                Optional
              </span>
            </div>
            <span className="font-mono text-base font-bold leading-tight">
              {busy ? (
                <span className="inline-flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" /> Running prediction…
                </span>
              ) : (
                "Run approved AI model"
              )}
            </span>
            <span className="text-xs text-muted-foreground">
              POST /ai/predictions — submits a draft prediction request through the controlled AI service.
            </span>
          </button>
          {err ? <p className="text-sm text-destructive">{err}</p> : null}
          {ok ? <p className="text-sm text-emerald-700">{ok}</p> : null}
        </div>
      </ModuleCard>

      {/* Step 3 — Result + Feedback */}
      {prediction ? (
        <ModuleCard
          accent={accent}
          eyebrow={`${moduleLabel} AI · Step 3 · Result`}
          title="Prediction result &amp; reviewer feedback"
          icon={BarChart3}
          description="Draft prediction with confidence and OOD flags — review, then submit feedback or escalate low-confidence cases to the Active Learning queue."
          className="min-w-0"
        >
          <div className="space-y-4">
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

            <div
              className="rounded-md border p-3"
              style={{ borderColor: `${accentColor}33`, backgroundColor: `color-mix(in oklab, ${accentColor} 5%, transparent)` }}
            >
              <p
                className="mb-3 font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                style={{ color: accentColor }}
              >
                Reviewer feedback
              </p>
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
              {feedbackErr ? <p className="mt-2 text-sm text-destructive">{feedbackErr}</p> : null}
              {feedbackOk ? <p className="mt-2 text-sm text-emerald-700">{feedbackOk}</p> : null}
              {queueMsg ? <p className="mt-2 text-sm text-muted-foreground">{queueMsg}</p> : null}
            </div>
          </div>
        </ModuleCard>
      ) : null}
    </div>
  )
}
