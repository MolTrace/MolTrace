"use client"

import { useMemo } from "react"
import {
  AlertTriangle,
  CheckCircle2,
  FileJson,
  FlaskConical,
  Layers,
  Scale,
  Shield,
  Trophy,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Progress } from "@/components/ui/progress"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { SpectraCheckUseUnifiedEvidenceButton } from "@/components/spectracheck/spectracheck-use-unified-evidence-button"
import { EvidenceCard } from "@/components/science/evidence-card"
import {
  candidateLabel,
  candidateScore,
  summarizeResult,
  type Summary,
} from "@/components/spectracheck/spectracheck-summary"
import type { SpectraCheckUnifiedEvidenceMeta } from "@/src/lib/spectracheck/evidence-enqueue"

export function DeveloperJsonPanel({ data }: { data: unknown }) {
  return (
    <details className="rounded-lg border bg-card p-4">
      <summary className="flex cursor-pointer items-center gap-2 text-sm font-medium">
        <FileJson className="h-4 w-4" />
        Developer JSON
        <span
          className="inline-flex shrink-0"
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
          }}
        >
          <InfoTooltip
            label="Developer JSON"
            content="Raw API response JSON for debugging, audit trails, and reproducibility."
            className="size-4"
          />
        </span>
      </summary>
      <pre className="mt-4 max-h-[520px] overflow-x-auto overflow-y-auto whitespace-pre-wrap rounded-md bg-muted/40 p-4 text-xs leading-5">
        {JSON.stringify(data, null, 2)}
      </pre>
    </details>
  )
}

function SummaryPanels({
  summary,
  jsonPayload,
  tone = "standard",
  unifiedEvidence,
}: {
  summary: Summary
  jsonPayload: unknown
  tone?: "standard" | "ms"
  unifiedEvidence?: SpectraCheckUnifiedEvidenceMeta
}) {
  const topRankLabel = tone === "ms" ? "Top-ranked entry" : "Best candidate"
  return (
    <>
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-success/30 bg-success/5 px-3 py-2 text-sm text-foreground">
        <CheckCircle2 className="h-4 w-4 text-success" aria-hidden="true" />
        <span className="font-medium">Request completed</span>
        <span className="text-muted-foreground">
          {tone === "ms"
            ? "Review summaries as plausible evidence—ambiguous cases require expert review."
            : "Review summaries and raw JSON below."}
        </span>
      </div>

      {unifiedEvidence && jsonPayload != null && (
        <div className="flex flex-wrap items-center gap-2">
          <SpectraCheckUseUnifiedEvidenceButton meta={unifiedEvidence} response={jsonPayload} summary={summary} />
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {summary.panels.showBestCandidate && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                <Trophy className="h-4 w-4" />
                {topRankLabel}
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm font-medium">{summary.bestCandidate}</CardContent>
          </Card>
        )}

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <FlaskConical className="h-4 w-4" />
              Candidates
            </CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{summary.candidateCount ?? "—"}</CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <CheckCircle2 className="h-4 w-4" />
              Score / confidence
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="font-mono text-2xl font-semibold">
              {summary.confidence === null ? "—" : `${summary.confidence.toFixed(1)}%`}
            </div>
            {summary.confidence !== null && <Progress value={summary.confidence} className="mt-2 h-1.5" />}
            {tone === "ms" && (
              <p className="mt-2 text-xs text-muted-foreground">
                Numeric scores indicate relative fit to these inputs—not structural proof or identity.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {summary.panels.showEvidenceLayers && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Layers className="h-4 w-4" />
              Evidence layers
            </CardTitle>
            <CardDescription>
              From <code className="text-xs">evidence_layers_used</code> and related keys.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {summary.evidenceLayers.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {summary.evidenceLayers.map((layer) => (
                  <Badge key={layer} variant="secondary" className="capitalize">
                    {layer}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No evidence layer list could be parsed.</p>
            )}
          </CardContent>
        </Card>
      )}

      {summary.panels.showHumanReview && summary.humanReviewLabel && (
        <Card className="border-primary/20">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Shield className="h-4 w-4" />
              Human review / QC
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Badge variant="outline" className="font-mono text-sm">
              {summary.humanReviewLabel}
            </Badge>
          </CardContent>
        </Card>
      )}

      {summary.panels.showRankedTable && summary.rankedCandidates.length > 0 && (
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>{tone === "ms" ? "Ranked rows (supports / contradicts review)" : "Ranked candidates"}</CardTitle>
            <CardDescription>
              {tone === "ms" ? (
                <>
                  Ordering reflects automated scoring—entries may <strong>support</strong> or <strong>contradict</strong> a
                  candidate vs. these inputs; conflicting signals <strong>require review</strong>.
                </>
              ) : (
                <>
                  From <code className="text-xs">ranked_candidates</code> when present.
                </>
              )}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Rank</TableHead>
                    <TableHead>Candidate</TableHead>
                    <TableHead>Score</TableHead>
                    <TableHead>Confidence</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {summary.rankedCandidates.map((candidate, index) => (
                    <TableRow key={`${candidateLabel(candidate, index)}-${index}`}>
                      <TableCell>{index + 1}</TableCell>
                      <TableCell className="font-medium">{candidateLabel(candidate, index)}</TableCell>
                      <TableCell>{candidateScore(candidate)?.toFixed(1) ?? "—"}</TableCell>
                      <TableCell>{String(candidate.confidence_band || candidate.confidence_label || "—")}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {summary.panels.showContradictions && summary.contradictions.length > 0 && (
        <Card className="border-destructive/40 bg-destructive/5">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base text-destructive">
              <Scale className="h-4 w-4" />
              Contradictions
            </CardTitle>
            {tone === "ms" && (
              <CardDescription className="text-destructive/90">
                These signals may <strong>contradict</strong> a candidate relative to this request—not definitive structural
                falsification without expert review.
              </CardDescription>
            )}
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {summary.contradictions.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {summary.panels.showWarnings && summary.warnings.length > 0 && (
        <Card className="border-warning/40">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-warning">
              <AlertTriangle className="h-4 w-4" />
              Warnings
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {summary.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {summary.panels.showNotes && summary.notes.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Notes</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {summary.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <DeveloperJsonPanel data={jsonPayload} />
    </>
  )
}

export function SummarizedEvidenceView({
  result,
  unifiedEvidence,
}: {
  result: unknown
  unifiedEvidence?: SpectraCheckUnifiedEvidenceMeta
}) {
  const summary = useMemo(() => summarizeResult(result), [result])
  return <SummaryPanels summary={summary} jsonPayload={result} unifiedEvidence={unifiedEvidence} />
}

export function TabResultSection({
  error,
  loading,
  loadingTitle,
  loadingHint,
  emptyHint,
  result,
  summaryTone = "standard",
  unifiedEvidence,
}: {
  error: string
  loading: boolean
  loadingTitle: string
  loadingHint: string
  emptyHint: string
  result: unknown | null
  summaryTone?: "standard" | "ms"
  unifiedEvidence?: SpectraCheckUnifiedEvidenceMeta
}) {
  const summary = useMemo(() => (result ? summarizeResult(result) : null), [result])

  return (
    <div className="min-w-0 space-y-6">
      {error && (
        <Card className="border-warning/40 bg-warning/10">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base text-warning">
              <AlertTriangle className="h-4 w-4" />
              Request failed
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-warning">{error}</CardContent>
        </Card>
      )}

      {loading && (
        <EvidenceCard
          title={loadingTitle}
          module="spectracheck"
          status="unavailable"
          risk_level="unknown"
          summary={loadingHint}
          evidence_items={["Calling the backend through /api/backend."]}
          citations={[]}
          review_status="waiting for evidence"
        />
      )}

      {summary && !loading ? (
        <SummaryPanels
          summary={summary}
          jsonPayload={result}
          tone={summaryTone}
          unifiedEvidence={unifiedEvidence}
        />
      ) : !loading && !error ? (
        <EvidenceCard
          title="Results"
          module="spectracheck"
          status="unavailable"
          risk_level="unknown"
          summary={emptyHint}
          evidence_items={["Run an analysis to see evidence summaries and developer JSON."]}
          citations={[]}
          review_status="not generated"
        />
      ) : null}
    </div>
  )
}
