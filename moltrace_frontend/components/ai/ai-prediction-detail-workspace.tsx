"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { FeedbackButton } from "@/src/components/analytics/FeedbackButton"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { statusLabel } from "@/lib/ui/status"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import {
  readConfidence,
  readPredictionProvenance,
  readPredictionWarnings,
  readUncertainty,
  uncertaintyFacts,
} from "@/src/lib/ai/prediction-confidence"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import {
  Activity,
  ArrowRight,
  Fingerprint,
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

  // The server's own warnings, which name the cause of a review flag. Read them from the
  // response rather than re-deriving a threshold here: the screening rule lives on the
  // server, and a second copy of it in the interface would be a second, divergent rule.
  const warnings = useMemo(
    () => (prediction ? [...new Set([...readPredictionWarnings(prediction), ...readWarnings(prediction)])] : []),
    [prediction],
  )
  const confidence = useMemo(() => readConfidence(prediction), [prediction])
  const uncertainty = useMemo(() => readUncertainty(prediction), [prediction])
  const uncertaintyRows = useMemo(() => uncertaintyFacts(uncertainty), [uncertainty])
  const provenance = useMemo(() => readPredictionProvenance(prediction), [prediction])
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

          {/* A confidence the engine declined to report is a result, not a blank. It happens
              when the figure would carry no information — a posterior over a single candidate
              is 1.0 by construction — so the reason is shown instead of a gauge. */}
          {confidence.declined ? (
            <AlertCard
              variant="warning"
              title="The engine reported no confidence for this prediction"
              description={
                warnings.length > 0
                  ? warnings.join(" ")
                  : "The engine ran and declined to report a confidence figure, so this prediction cannot be screened automatically and requires review."
              }
            />
          ) : warnings.length > 0 ? (
            <AlertCard variant="warning" title="Review signals" description={warnings.join(" ")} />
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
              {/* The figure is never shown alone: the scale is what makes it mean anything, and
                  the two scales in use are not comparable to each other. */}
              <div className="rounded-md border p-3">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="font-medium">Confidence:</span>
                  <span className={confidence.value == null ? "text-muted-foreground" : "font-mono"}>
                    {confidence.display}
                  </span>
                  {confidence.scale ? (
                    <Badge variant="outline">{confidence.scale.label}</Badge>
                  ) : confidence.value != null ? (
                    <Badge variant="outline">Scale not reported</Badge>
                  ) : null}
                </div>
                {confidence.scale ? (
                  <p className="mt-1 text-xs text-muted-foreground">{confidence.scale.meaning}</p>
                ) : confidence.value != null ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    This figure arrived without the scale it was measured on, so it cannot be compared
                    against another prediction&rsquo;s confidence.
                  </p>
                ) : null}
              </div>
              {uncertaintyRows.length > 0 ? (
                <div>
                  <p className="font-medium">Uncertainty</p>
                  <dl className="mt-1 grid gap-x-4 gap-y-1 sm:grid-cols-2">
                    {uncertaintyRows.map((fact) => (
                      <div key={fact.label} className="flex flex-wrap justify-between gap-2 text-xs">
                        <dt className="text-muted-foreground">{fact.label}</dt>
                        <dd className="font-mono">{fact.value}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ) : (
                <p>
                  <span className="font-medium">Uncertainty:</span>{" "}
                  <span className="text-muted-foreground">Not reported for this prediction.</span>
                </p>
              )}
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

          {/* The audit answer to "which model produced this number". Rendered only when the
              response carries it — an absent block here means this response does not include
              provenance, not that nothing was recorded, so it must not claim the latter. */}
          {provenance ? (
            <ModuleCard
              accent="teal"
              eyebrow="Provenance"
              title="What produced this number"
              icon={Fingerprint}
              description="Every component that contributed to this prediction, at the version it ran."
            >
              <div className="space-y-3 text-sm">
                {provenance.engine ? (
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Engine</p>
                    <p className="break-all font-mono text-xs">{provenance.engine}</p>
                  </div>
                ) : null}
                {provenance.components.length > 0 ? (
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      Component versions
                    </p>
                    <dl className="mt-1 space-y-1">
                      {provenance.components.map((component) => (
                        <div key={component.name} className="flex flex-wrap justify-between gap-2 text-xs">
                          <dt className="font-mono text-muted-foreground">{component.name}</dt>
                          <dd className="break-all font-mono">{component.version}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                ) : null}
              </div>
            </ModuleCard>
          ) : null}

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
