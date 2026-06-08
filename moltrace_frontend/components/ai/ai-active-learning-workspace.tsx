"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import {
  trackAiActiveLearningCandidateCreated,
  trackAiPredictionFeedbackSubmitted,
} from "@/src/lib/analytics/analytics-client"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ModuleCard } from "@/components/dashboard/module-card"
import { ListChecks, MessageSquare, Plus } from "lucide-react"
import { Checkbox } from "@/components/ui/checkbox"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { AlertTriangle, Loader2, RefreshCw } from "lucide-react"
import {
  REASON_CODES,
  REASON_CODE_LABEL,
  isNegativeFeedbackType,
  type ReasonCode,
} from "@/components/ai/feedback-reason-code"

type Row = Record<string, unknown>

const FEEDBACK_TYPES = [
  "accepted",
  "rejected",
  "corrected",
  "uncertain",
  "useful",
  "not_useful",
  "error_case",
  "other",
] as const

const QUEUE_KEYS = ["candidates", "active_learning_candidates", "items", "results", "rows", "data"]
const SOURCE_MODULES = ["spectracheck", "reaction_optimization", "regulatory", "knowledge_extraction", "reports"] as const
const PRIORITIES = ["low", "medium", "high", "critical"] as const
const STATUSES = ["new", "in_review", "queued_for_dataset", "accepted", "rejected", "resolved"] as const

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

function formatWhen(iso: string | undefined): string {
  if (!iso?.trim()) return "-"
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return iso
  return new Date(t).toLocaleString()
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

function hasSensitiveCorrectionContent(raw: string): boolean {
  const t = raw.toLowerCase()
  return [
    "rawspectrum",
    "spectrum",
    "smiles",
    "source_text",
    "source text",
    "private note",
    "token",
    "password",
    "secret",
  ].some((k) => t.includes(k))
}

export function AiActiveLearningWorkspace() {
  const [loading, setLoading] = useState(true)
  const [reloadToken, setReloadToken] = useState(0)
  const [queueRows, setQueueRows] = useState<Row[]>([])
  const [queueErr, setQueueErr] = useState("")

  const [predictionId, setPredictionId] = useState("")
  const [feedbackType, setFeedbackType] = useState<string>(FEEDBACK_TYPES[0])
  // reason_code (v0.19.1) — meaningful only on a negative feedback_type.
  // Empty-string sentinel = "not set" → wire value null. UI gates visibility
  // on isNegativeFeedbackType so a positive verdict never carries a stale
  // reason from a prior selection.
  const [reasonCode, setReasonCode] = useState<ReasonCode | "">("")
  const [reviewerName, setReviewerName] = useState("")
  const [reviewerComment, setReviewerComment] = useState("")
  const [correctedOutputJson, setCorrectedOutputJson] = useState("")
  const [sensitiveConfirmed, setSensitiveConfirmed] = useState(false)
  const [feedbackBusy, setFeedbackBusy] = useState(false)
  const [feedbackErr, setFeedbackErr] = useState("")
  const [feedbackOk, setFeedbackOk] = useState("")

  const [candidateSourceModule, setCandidateSourceModule] = useState<string>(SOURCE_MODULES[0])
  const [candidateReason, setCandidateReason] = useState("")
  const [candidatePriority, setCandidatePriority] = useState<string>(PRIORITIES[1])
  const [candidateStatus, setCandidateStatus] = useState<string>(STATUSES[0])
  const [candidatePredictionId, setCandidatePredictionId] = useState("")
  const [candidateModelImprovementId, setCandidateModelImprovementId] = useState("")
  const [candidateCreateBusy, setCandidateCreateBusy] = useState(false)
  const [candidateErr, setCandidateErr] = useState("")
  const [candidateOk, setCandidateOk] = useState("")
  const [rowBusyId, setRowBusyId] = useState<number | null>(null)

  const sensitiveWarning = useMemo(() => hasSensitiveCorrectionContent(correctedOutputJson), [correctedOutputJson])

  const loadQueue = useCallback(async () => {
    setLoading(true)
    setQueueErr("")
    try {
      const data = await apiFetch<unknown>("/ai/active-learning/candidates", { method: "GET" })
      setQueueRows(extractRows(data, QUEUE_KEYS))
    } catch (err) {
      setQueueErr(formatErr(err, "Could not load /ai/active-learning/candidates."))
      setQueueRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadQueue()
  }, [loadQueue, reloadToken])

  async function submitPredictionFeedback() {
    setFeedbackErr("")
    setFeedbackOk("")
    const id = Number.parseInt(predictionId, 10)
    if (!Number.isFinite(id) || id < 1) {
      setFeedbackErr("prediction_id is required.")
      return
    }
    if (sensitiveWarning && !sensitiveConfirmed) {
      setFeedbackErr("Sensitive-data warning requires confirmation before submitting correction.")
      return
    }

    let correctedOutputParsed: Record<string, unknown> | null = null
    if (correctedOutputJson.trim()) {
      try {
        const parsed = JSON.parse(correctedOutputJson) as unknown
        if (!isRecord(parsed)) {
          setFeedbackErr("corrected_output_json must be a JSON object when provided.")
          return
        }
        correctedOutputParsed = parsed
      } catch {
        setFeedbackErr("corrected_output_json must be valid JSON.")
        return
      }
    }

    setFeedbackBusy(true)
    try {
      // reason_code (v0.19.1) — only meaningful on a negative verdict.
      // Both endpoints accept it; sending null when it's not applicable
      // keeps the request shape backward-compatible with the pre-v0.19.1
      // contract (the field is optional + nullable in the schema).
      const wireReasonCode =
        isNegativeFeedbackType(feedbackType) && reasonCode ? reasonCode : null

      await apiFetch(`/ai/predictions/${id}/feedback`, {
        method: "POST",
        body: {
          feedback_type: feedbackType,
          reason_code: wireReasonCode,
          reviewer_name: reviewerName.trim() || null,
          reviewer_comment: reviewerComment.trim() || null,
          corrected_output_json: correctedOutputParsed,
        },
      })

      await apiFetch(`/ai/predictions/${id}/review`, {
        method: "POST",
        body: {
          reviewer_name: reviewerName.trim() || null,
          reviewer_comment: reviewerComment.trim() || null,
          reason_code: wireReasonCode,
          review_outcome: feedbackType,
        },
      })

      trackAiPredictionFeedbackSubmitted({
        feedback_type: feedbackType,
        status: "submitted",
      })
      setFeedbackOk("Prediction feedback submitted.")
    } catch (err) {
      setFeedbackErr(formatErr(err, "Could not submit prediction feedback/review."))
    } finally {
      setFeedbackBusy(false)
    }
  }

  async function createCandidate() {
    setCandidateErr("")
    setCandidateOk("")
    if (!candidateReason.trim()) {
      setCandidateErr("reason is required.")
      return
    }
    const predId = Number.parseInt(candidatePredictionId, 10)
    const miId = Number.parseInt(candidateModelImprovementId, 10)
    setCandidateCreateBusy(true)
    try {
      await apiFetch("/ai/active-learning/candidates", {
        method: "POST",
        body: {
          source_module: candidateSourceModule,
          reason: candidateReason.trim(),
          priority: candidatePriority,
          status: candidateStatus,
          linked_prediction: Number.isFinite(predId) && predId > 0 ? predId : null,
          linked_model_improvement_item: Number.isFinite(miId) && miId > 0 ? miId : null,
        },
      })
      trackAiActiveLearningCandidateCreated({
        target_module: candidateSourceModule,
        status: candidateStatus,
        active_learning_reason: candidateReason.trim(),
      })
      setCandidateOk("Active-learning candidate created.")
      setReloadToken((x) => x + 1)
    } catch (err) {
      setCandidateErr(formatErr(err, "Could not create active-learning candidate."))
    } finally {
      setCandidateCreateBusy(false)
    }
  }

  async function patchCandidateStatus(candidateId: number, nextStatus: string) {
    setCandidateErr("")
    setCandidateOk("")
    setRowBusyId(candidateId)
    try {
      await apiFetch(`/ai/active-learning/candidates/${candidateId}`, {
        method: "PATCH",
        body: { status: nextStatus },
      })
      setReloadToken((x) => x + 1)
    } catch (err) {
      setCandidateErr(formatErr(err, `Could not update /ai/active-learning/candidates/${candidateId}.`))
    } finally {
      setRowBusyId(null)
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <h1 className="font-mono text-2xl font-bold tracking-tight">Prediction Feedback and Active Learning Queue</h1>
          <InfoTooltip
            label="About Active Learning Queue"
            content="Active-learning candidates are low-confidence, out-of-domain, or human-corrected cases that can improve future dataset versions and models."
          />
        </div>
        <p className="text-sm text-muted-foreground">Submit prediction feedback and manage active-learning candidate lifecycle updates.</p>
      </div>

      <div className="flex items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => setReloadToken((x) => x + 1)} disabled={loading}>
          {loading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <RefreshCw className="mr-2 size-4" />}
          Refresh
        </Button>
      </div>

      <ModuleCard
        accent="teal"
        eyebrow="Feedback"
        title="Prediction feedback"
        icon={MessageSquare}
        description="Submit reviewer feedback or a formal review decision (accept, reject, escalate) on a specific prediction."
      >
        <div className="space-y-4">
          {feedbackErr ? <p className="text-sm text-destructive">{feedbackErr}</p> : null}
          {feedbackOk ? <p className="text-sm text-emerald-700">{feedbackOk}</p> : null}

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="feedback-prediction-id">prediction ID</Label>
              <Input id="feedback-prediction-id" value={predictionId} onChange={(e) => setPredictionId(e.target.value)} inputMode="numeric" placeholder="prediction_id" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="feedback-type">feedback type</Label>
              <Select value={feedbackType} onValueChange={setFeedbackType}>
                <SelectTrigger id="feedback-type">
                  <SelectValue placeholder="Select feedback type" />
                </SelectTrigger>
                <SelectContent>
                  {FEEDBACK_TYPES.map((opt) => (
                    <SelectItem key={opt} value={opt}>
                      {opt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="reviewer-name">reviewer name optional</Label>
              <Input id="reviewer-name" value={reviewerName} onChange={(e) => setReviewerName(e.target.value)} placeholder="reviewer_name" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="reviewer-comment">reviewer comment optional</Label>
              <Input id="reviewer-comment" value={reviewerComment} onChange={(e) => setReviewerComment(e.target.value)} placeholder="reviewer_comment" />
            </div>
            {/* reason_code (v0.19.1) — surfaces only on a negative verdict
                (rejected / corrected / error_case / uncertain). Orthogonal
                to feedback_type per the BE handoff. */}
            {isNegativeFeedbackType(feedbackType) ? (
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="feedback-reason-code">
                  reason_code optional
                  <span className="ml-2 font-normal text-muted-foreground">
                    · structured "why?" tag for the negative verdict
                  </span>
                </Label>
                <Select
                  value={reasonCode}
                  onValueChange={(v) => setReasonCode(v as ReasonCode)}
                >
                  <SelectTrigger id="feedback-reason-code">
                    <SelectValue placeholder="Choose a reason…" />
                  </SelectTrigger>
                  <SelectContent>
                    {REASON_CODES.map((code) => (
                      <SelectItem key={code} value={code}>
                        {REASON_CODE_LABEL[code]} <span className="ml-2 text-muted-foreground">({code})</span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="corrected-output-json">corrected output JSON optional</Label>
            <Textarea
              id="corrected-output-json"
              value={correctedOutputJson}
              onChange={(e) => setCorrectedOutputJson(e.target.value)}
              rows={5}
              placeholder='{"correction_summary":"ID-based correction only"}'
            />
          </div>

          {sensitiveWarning ? (
            <Alert className="border-amber-500/30 bg-amber-500/10">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
              <AlertTitle>Sensitive data warning</AlertTitle>
              <AlertDescription>
                Corrected output may include sensitive data. Confirm that corrected output does not include raw spectra, full source text, or secrets.
              </AlertDescription>
            </Alert>
          ) : null}

          {sensitiveWarning ? (
            <div className="flex items-center gap-2">
              <Checkbox id="sensitive-confirm" checked={sensitiveConfirmed} onCheckedChange={(v) => setSensitiveConfirmed(v === true)} />
              <Label htmlFor="sensitive-confirm">I confirm corrected output excludes raw/confidential content.</Label>
            </div>
          ) : null}

          <Button type="button" onClick={() => void submitPredictionFeedback()} disabled={feedbackBusy}>
            {feedbackBusy ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
            Submit feedback
          </Button>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Create"
        title="Create active-learning candidate"
        icon={Plus}
        description="Manually queue a prediction for human labeling — useful when a downstream reviewer flags a case the model missed."
      >
        <div className="space-y-4">
          {candidateErr ? <p className="text-sm text-destructive">{candidateErr}</p> : null}
          {candidateOk ? <p className="text-sm text-emerald-700">{candidateOk}</p> : null}
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="candidate-source-module">source module</Label>
              <Select value={candidateSourceModule} onValueChange={setCandidateSourceModule}>
                <SelectTrigger id="candidate-source-module">
                  <SelectValue placeholder="Select source module" />
                </SelectTrigger>
                <SelectContent>
                  {SOURCE_MODULES.map((opt) => (
                    <SelectItem key={opt} value={opt}>
                      {opt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="candidate-priority">priority</Label>
              <Select value={candidatePriority} onValueChange={setCandidatePriority}>
                <SelectTrigger id="candidate-priority">
                  <SelectValue placeholder="Select priority" />
                </SelectTrigger>
                <SelectContent>
                  {PRIORITIES.map((opt) => (
                    <SelectItem key={opt} value={opt}>
                      {opt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="candidate-status">status</Label>
              <Select value={candidateStatus} onValueChange={setCandidateStatus}>
                <SelectTrigger id="candidate-status">
                  <SelectValue placeholder="Select status" />
                </SelectTrigger>
                <SelectContent>
                  {STATUSES.map((opt) => (
                    <SelectItem key={opt} value={opt}>
                      {opt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="candidate-linked-prediction">linked prediction</Label>
              <Input
                id="candidate-linked-prediction"
                value={candidatePredictionId}
                onChange={(e) => setCandidatePredictionId(e.target.value)}
                inputMode="numeric"
                placeholder="prediction_id"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="candidate-linked-model-improvement">linked model improvement item</Label>
              <Input
                id="candidate-linked-model-improvement"
                value={candidateModelImprovementId}
                onChange={(e) => setCandidateModelImprovementId(e.target.value)}
                inputMode="numeric"
                placeholder="model_improvement_item_id"
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="candidate-reason">reason</Label>
              <Textarea
                id="candidate-reason"
                value={candidateReason}
                onChange={(e) => setCandidateReason(e.target.value)}
                rows={3}
                placeholder="Candidate reason (low-confidence, out-of-domain warning, or correction summary)."
              />
            </div>
          </div>
          <Button type="button" onClick={() => void createCandidate()} disabled={candidateCreateBusy}>
            {candidateCreateBusy ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
            Create candidate
          </Button>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Queue"
        title="Active Learning Queue"
        icon={ListChecks}
        description="Predictions awaiting human review, with status changes (accept, reject, escalate) tracked inline."
      >
        <div className="overflow-x-auto">
          {queueErr ? <p className="mb-3 text-sm text-destructive">{queueErr}</p> : null}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>source module</TableHead>
                <TableHead>reason</TableHead>
                <TableHead>priority</TableHead>
                <TableHead>status</TableHead>
                <TableHead>linked prediction</TableHead>
                <TableHead>linked model improvement item</TableHead>
                <TableHead>created date</TableHead>
                <TableHead>actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {queueRows.map((row, idx) => {
                const candidateId = readRecordNumber(row, "candidate_id") ?? readRecordNumber(row, "id")
                const busy = candidateId != null && rowBusyId === candidateId
                return (
                  <TableRow key={`${candidateId ?? "row"}-${idx}`}>
                    <TableCell>{readRecordString(row, "source_module") ?? "-"}</TableCell>
                    <TableCell className="max-w-[260px] truncate">{readRecordString(row, "reason") ?? "-"}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{readRecordString(row, "priority") ?? "-"}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{readRecordString(row, "status") ?? "-"}</Badge>
                    </TableCell>
                    <TableCell>{readRecordString(row, "linked_prediction") ?? "-"}</TableCell>
                    <TableCell>{readRecordString(row, "linked_model_improvement_item") ?? "-"}</TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {formatWhen(readRecordString(row, "created_at") ?? readRecordString(row, "timestamp"))}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        <Button size="sm" variant="outline" disabled={busy || candidateId == null} onClick={() => candidateId != null && void patchCandidateStatus(candidateId, "accepted")}>
                          accept
                        </Button>
                        <Button size="sm" variant="outline" disabled={busy || candidateId == null} onClick={() => candidateId != null && void patchCandidateStatus(candidateId, "rejected")}>
                          reject
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busy || candidateId == null}
                          onClick={() => candidateId != null && void patchCandidateStatus(candidateId, "queued_for_dataset")}
                        >
                          queue for dataset
                        </Button>
                        <Button size="sm" variant="outline" disabled={busy || candidateId == null} onClick={() => candidateId != null && void patchCandidateStatus(candidateId, "resolved")}>
                          resolve
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
              {queueRows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-muted-foreground">
                    No active-learning candidates returned.
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </div>
      </ModuleCard>
    </div>
  )
}
