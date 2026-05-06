"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export type ModelDiagnosticsCardProps = {
  loading: boolean
  trainingExperimentCount: number | null
  trainingCountFallbackTotal: number
  modelType: string | null
  objectiveSummary: string | null
  validationMetricsJson: unknown | null
  warnings: string[]
  uncertaintySummary: string | null
  featureEncodingSummary: string | null
}

function jsonPreview(raw: unknown, maxChars = 4000): string {
  try {
    const s = JSON.stringify(raw, null, 2)
    if (s.length <= maxChars) return s
    return `${s.slice(0, maxChars)}…`
  } catch {
    return String(raw)
  }
}

export function ModelDiagnosticsCard({
  loading,
  trainingExperimentCount,
  trainingCountFallbackTotal,
  modelType,
  objectiveSummary,
  validationMetricsJson,
  warnings,
  uncertaintySummary,
  featureEncodingSummary,
}: ModelDiagnosticsCardProps) {
  const trainingDisplay =
    trainingExperimentCount != null ? String(trainingExperimentCount) : String(trainingCountFallbackTotal)
  const trainingNote =
    trainingExperimentCount != null ? null : (
      <p className="text-[10px] text-muted-foreground">
        No training count in run response — showing total experiment count as fallback.
      </p>
    )

  const hasValidation =
    validationMetricsJson != null &&
    typeof validationMetricsJson === "object" &&
    !Array.isArray(validationMetricsJson) &&
    Object.keys(validationMetricsJson as object).length > 0

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Model diagnostics</CardTitle>
        <CardDescription>
          Summary from the latest Bayesian optimization run or heuristic optimization run response when fields are
          present — indicative only, not proof of predictive accuracy.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {loading ? (
          <p className="text-muted-foreground">…</p>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground">training experiment count</p>
                <p className="font-mono text-sm tabular-nums">{trainingDisplay}</p>
                {trainingNote}
              </div>
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground">model type</p>
                <p className="font-mono text-sm">{modelType ?? "—"}</p>
              </div>
              <div className="space-y-1 sm:col-span-2">
                <p className="text-xs font-medium text-muted-foreground">objective summary</p>
                <p className="font-mono text-sm">{objectiveSummary ?? "—"}</p>
              </div>
            </div>

            <div className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground">validation / fit metrics</p>
              {hasValidation ? (
                <pre className="max-h-48 overflow-auto rounded-md bg-muted/40 p-3 text-xs leading-relaxed">
                  {jsonPreview(validationMetricsJson, 8000)}
                </pre>
              ) : (
                <p className="text-xs text-muted-foreground">—</p>
              )}
            </div>

            <div className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground">warnings</p>
              {warnings.length > 0 ? (
                <ul className="list-inside list-disc text-xs text-muted-foreground">
                  {warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-muted-foreground">warnings: none</p>
              )}
            </div>

            <div className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground">uncertainty summary</p>
              <p className="text-xs leading-relaxed text-muted-foreground">{uncertaintySummary ?? "—"}</p>
            </div>

            <div className="space-y-2">
              <p className="text-xs font-medium text-muted-foreground">feature encoding summary</p>
              <p className="text-xs leading-relaxed text-muted-foreground">{featureEncodingSummary ?? "—"}</p>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
