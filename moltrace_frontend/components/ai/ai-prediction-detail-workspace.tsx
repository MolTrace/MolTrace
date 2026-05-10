"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { FeedbackButton } from "@/src/components/analytics/FeedbackButton"
import { ApiError, apiFetch } from "@/lib/api/client"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertTriangle } from "lucide-react"

type Row = Record<string, unknown>

function isRecord(v: unknown): v is Row {
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

function summarizeValue(v: unknown): string {
  if (v == null) return "-"
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return String(v)
  if (Array.isArray(v)) return v.map((x) => summarizeValue(x)).join(", ")
  return JSON.stringify(v)
}

function readWarnings(row: Row): string[] {
  const candidates = [row.warnings, row.prediction_warnings, row.review_warnings]
  for (const item of candidates) {
    if (Array.isArray(item)) {
      return item.map((x) => summarizeValue(x)).filter((x) => x.trim().length > 0)
    }
    if (typeof item === "string" && item.trim()) return [item.trim()]
  }
  return []
}

function readBoolLike(row: Row, keys: string[]): boolean | null {
  for (const key of keys) {
    const value = row[key]
    if (typeof value === "boolean") return value
    if (typeof value === "string") {
      const t = value.trim().toLowerCase()
      if (t === "true") return true
      if (t === "false") return false
    }
  }
  return null
}

export function AiPredictionDetailWorkspace({ predictionId }: { predictionId: string }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [prediction, setPrediction] = useState<Row | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError("")
    void (async () => {
      try {
        const raw = await apiFetch<unknown>(`/ai/predictions/${encodeURIComponent(predictionId)}`, { method: "GET" })
        if (!cancelled && isRecord(raw)) setPrediction(raw)
      } catch (err) {
        if (!cancelled) {
          setPrediction(null)
          setError(formatErr(err, `Could not load /ai/predictions/${predictionId}.`))
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [predictionId])

  const warnings = useMemo(() => (prediction ? readWarnings(prediction) : []), [prediction])
  const confidence = prediction ? readRecordNumber(prediction, "confidence") ?? readRecordNumber(prediction, "confidence_score") : null
  const uncertainty = prediction
    ? readRecordNumber(prediction, "uncertainty") ?? readRecordNumber(prediction, "uncertainty_score")
    : null
  const isOod =
    prediction != null ? readBoolLike(prediction, ["is_ood", "out_of_domain"]) : null
  const humanReviewRequired = prediction != null ? readBoolLike(prediction, ["human_review_required", "review_required"]) : null

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="space-y-1">
          <h1 className="font-mono text-2xl font-bold tracking-tight">Prediction Detail</h1>
          <p className="text-sm text-muted-foreground">Prediction output requires review before scientific or regulatory use.</p>
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link href="/ai/predictions">Back to predictions</Link>
        </Button>
      </div>

      {loading ? <p className="text-sm text-muted-foreground">Loading prediction detail...</p> : null}
      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Load error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {prediction ? (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>service key</CardDescription>
                <CardTitle className="text-base">{readRecordString(prediction, "service_key") ?? "-"}</CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>model artifact ID</CardDescription>
                <CardTitle className="text-base">{readRecordString(prediction, "model_artifact_id") ?? "-"}</CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>deployment candidate ID</CardDescription>
                <CardTitle className="text-base">{readRecordString(prediction, "deployment_candidate_id") ?? "-"}</CardTitle>
              </CardHeader>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>status</CardDescription>
                <CardTitle className="text-base">
                  <Badge variant="outline">{readRecordString(prediction, "status") ?? "-"}</Badge>
                </CardTitle>
              </CardHeader>
            </Card>
          </div>

          {confidence != null && confidence < 0.5 ? (
            <Alert className="border-amber-500/30 bg-amber-500/10">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
              <AlertTitle>low confidence</AlertTitle>
              <AlertDescription>This prediction has low confidence and requires review.</AlertDescription>
            </Alert>
          ) : null}

          {isOod === true ? (
            <Alert className="border-amber-500/30 bg-amber-500/10">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
              <AlertTitle>out-of-domain warning</AlertTitle>
              <AlertDescription>This prediction indicates out-of-domain warning and requires review.</AlertDescription>
            </Alert>
          ) : null}

          <Card>
            <CardHeader>
              <CardTitle>Prediction result</CardTitle>
              <CardDescription>Review summary values before any downstream decision.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>
                <span className="font-medium">prediction result:</span> {summarizeValue(prediction.prediction_result ?? prediction.result)}
              </p>
              <p>
                <span className="font-medium">confidence:</span> {confidence == null ? "-" : confidence}
              </p>
              <p>
                <span className="font-medium">uncertainty:</span> {uncertainty == null ? "-" : uncertainty}
              </p>
              <p>
                <span className="font-medium">OOD status:</span>{" "}
                {summarizeValue(prediction.ood_status ?? prediction.is_ood ?? prediction.out_of_domain)}
              </p>
              <p>
                <span className="font-medium">explanation:</span> {summarizeValue(prediction.explanation)}
              </p>
              <p>
                <span className="font-medium">warnings:</span> {warnings.length ? warnings.join("; ") : "-"}
              </p>
              <p>
                <span className="font-medium">notes:</span> {summarizeValue(prediction.notes)}
              </p>
              <p>
                <span className="font-medium">human review required:</span>{" "}
                {humanReviewRequired == null ? "requires review" : humanReviewRequired ? "requires review" : "not flagged"}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Feedback form</CardTitle>
              <CardDescription>Submit workflow feedback without scientific payloads.</CardDescription>
            </CardHeader>
            <CardContent>
              <FeedbackButton
                module="ai-predictions-detail"
                projectId={readRecordNumber(prediction, "project_id") ?? null}
                sessionId={readRecordNumber(prediction, "session_id") ?? null}
              />
            </CardContent>
          </Card>

          <DeveloperJsonPanel data={prediction} />
        </>
      ) : null}
    </div>
  )
}
