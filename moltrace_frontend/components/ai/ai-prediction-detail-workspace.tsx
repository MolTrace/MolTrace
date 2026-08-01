"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { FeedbackButton } from "@/src/components/analytics/FeedbackButton"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { statusLabel } from "@/lib/ui/status"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import {
  Activity,
  ArrowRight,
  Gauge,
  MessageSquare,
  Sparkles,
} from "lucide-react"

type Row = Record<string, unknown>

function isRecord(v: unknown): v is Row {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

/**
 * A run's context references (evidence item, compound, session) are provenance, not columns: the
 * server persists them under request_summary_json.context, mirrored into metadata_json.context.
 * Reading them from the top level — as this file used to — silently yields null.
 *
 * The top-level lookup is kept as a last resort so a record that does carry them directly, now or
 * later, still reads.
 */
function readPredictionContextNumber(prediction: unknown, key: string): number | null {
  if (!isRecord(prediction)) return null
  for (const holder of ["request_summary_json", "metadata_json"]) {
    const outer = prediction[holder]
    if (!isRecord(outer)) continue
    const context = outer.context
    if (!isRecord(context)) continue
    const found = readRecordNumber(context, key)
    if (found != null) return found
  }
  return readRecordNumber(prediction, key) ?? null
}

function summarizeValue(v: unknown): string {
  if (v == null) return "-"
  if (typeof v === "boolean") return v ? "Yes" : "No"
  if (typeof v === "string" || typeof v === "number") return String(v)
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

/** Reader-facing out-of-domain wording; the stored value is unchanged. */
function oodDisplay(row: Row): string {
  const status = readRecordString(row, "ood_status")
  if (status?.trim()) return statusLabel(status)
  const flag = readBoolLike(row, ["is_ood", "out_of_domain"])
  if (flag != null) return flag ? "Out of domain" : "In domain"
  return "-"
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
          setError(formatApiError(err, `Could not load this prediction.`))
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
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-teal-ink)" }}
          >
            MolTrace · AI Services · Prediction
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Prediction Detail</h1>
          <p className="text-sm text-muted-foreground">Prediction output requires review before scientific or regulatory use.</p>
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link href="/ai/predictions">Back to predictions</Link>
        </Button>
      </div>

      {loading ? <p className="text-sm text-muted-foreground">Loading prediction detail...</p> : null}
      {error ? (
        <AlertCard variant="error" title="Couldn’t load this prediction" description={error} />
      ) : null}

      {prediction ? (
        <>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <ModuleCard
              accent="teal"
              eyebrow="Overview"
              title={readRecordString(prediction, "service_key") ?? "-"}
              icon={Activity}
              description="Service key"
            />
            <ModuleCard
              accent="teal"
              eyebrow="Inputs"
              title={
                (() => {
                  const artifactId = readRecordString(prediction, "model_artifact_id")
                  return artifactId ? (
                    <Link
                      href={`/ml/models/${encodeURIComponent(artifactId)}`}
                      className="underline-offset-2 hover:underline"
                      style={{ color: "var(--mt-teal-ink)" }}
                    >
                      {artifactId}
                    </Link>
                  ) : (
                    "-"
                  )
                })()
              }
              icon={ArrowRight}
              description="Model artifact"
            />
            <ModuleCard
              accent="teal"
              eyebrow="Inputs"
              title={readRecordString(prediction, "deployment_candidate_id") ?? "-"}
              icon={ArrowRight}
              description="Deployment candidate ID"
            />
            <ModuleCard
              accent="teal"
              eyebrow="Output"
              title={
                <span className="flex items-center gap-2">
                  <Badge variant="outline">{statusLabel(readRecordString(prediction, "status"))}</Badge>
                </span>
              }
              icon={Sparkles}
              description="Status"
            />
          </div>

          {confidence != null && confidence < 0.5 ? (
            <AlertCard
              variant="warning"
              title="Low confidence"
              description="This prediction has low confidence and requires review."
            />
          ) : null}

          {isOod === true ? (
            <AlertCard
              variant="warning"
              title="Out-of-domain warning"
              description="This prediction indicates out-of-domain warning and requires review."
            />
          ) : null}

          <ModuleCard
            accent="teal"
            eyebrow="Confidence"
            title="Prediction result"
            icon={Gauge}
            description="Review summary values before any downstream decision."
          >
            <div className="space-y-2 text-sm">
              <p>
                <span className="font-medium">Prediction result:</span> {summarizeValue(prediction.prediction_result ?? prediction.result)}
              </p>
              <p>
                <span className="font-medium">Confidence:</span> {confidence == null ? "-" : confidence}
              </p>
              <p>
                <span className="font-medium">Uncertainty:</span> {uncertainty == null ? "-" : uncertainty}
              </p>
              <p>
                <span className="font-medium">Out-of-domain status:</span>{" "}
                {oodDisplay(prediction)}
              </p>
              <p>
                <span className="font-medium">Explanation:</span> {summarizeValue(prediction.explanation)}
              </p>
              <p>
                <span className="font-medium">Warnings:</span> {warnings.length ? warnings.join("; ") : "-"}
              </p>
              <p>
                <span className="font-medium">Notes:</span> {summarizeValue(prediction.notes)}
              </p>
              <p>
                <span className="font-medium">Human review required:</span>{" "}
                {humanReviewRequired == null ? "requires review" : humanReviewRequired ? "requires review" : "not flagged"}
              </p>
            </div>
          </ModuleCard>

          <ModuleCard
            accent="teal"
            eyebrow="Feedback"
            title="Feedback form"
            icon={MessageSquare}
            description="Submit workflow feedback without scientific data."
          >
            <FeedbackButton
              module="ai-predictions-detail"
              projectId={readRecordNumber(prediction, "project_id") ?? null}
              sessionId={readPredictionContextNumber(prediction, "session_id")}
            />
          </ModuleCard>

          <DeveloperJsonPanel data={prediction} />
        </>
      ) : null}
    </div>
  )
}
