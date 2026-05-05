"use client"

import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Progress } from "@/components/ui/progress"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { EvidenceLayerType } from "@/src/lib/spectracheck/evidence-types"
import { extractMethodProvenanceFromUnknown } from "@/src/lib/spectracheck/evidence-method-provenance"
import { extractMlModelProvenanceFromUnknown } from "@/src/lib/ml/model-provenance-extract"
import type { AnalysisJobStatus, UseAnalysisJobReturn } from "@/src/lib/spectracheck/useAnalysisJob"
import { useSpectraCheckEvidence } from "@/src/lib/spectracheck/useSpectraCheckEvidence"
import { ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"

function statusBadgeClass(s: AnalysisJobStatus | null): string {
  switch (s) {
    case "queued":
      return "border-muted-foreground/40 text-muted-foreground"
    case "running":
      return "border-accent/50 text-accent"
    case "succeeded":
      return "border-success/50 text-success"
    case "failed":
      return "border-destructive/60 text-destructive"
    case "canceled":
      return "border-warning/50 text-warning"
    default:
      return "border-muted-foreground/40 text-muted-foreground"
  }
}

export function AnalysisJobTimeline({
  job,
  variant = "full",
  evidenceLayer = "report",
  sourceTab = "Analysis job",
}: {
  job: UseAnalysisJobReturn
  variant?: "full" | "compact"
  evidenceLayer?: EvidenceLayerType
  sourceTab?: string
}) {
  const { addEvidenceItem } = useSpectraCheckEvidence()
  const {
    jobId,
    status,
    progressPercent,
    currentStep,
    error,
    events,
    artifactIds,
    result,
    backendUnavailable,
    rawJob,
    rawEventsPayload,
    polling,
    cancelBusy,
    cancelJob,
  } = job

  const canCancel = status === "queued" || status === "running"
  const progressValue =
    progressPercent != null && Number.isFinite(progressPercent)
      ? Math.max(0, Math.min(100, progressPercent))
      : status === "succeeded"
        ? 100
        : 0

  const compact = variant === "compact"

  return (
    <Card className="min-w-0">
      <CardHeader className={cn("pb-2", compact && "py-3")}>
        <CardTitle className={cn("flex flex-wrap items-center gap-2", compact ? "text-sm" : "text-base")}>
          Analysis job timeline
          {!compact ? (
            <InfoTooltip
              content="Analysis jobs track long-running processing tasks such as raw FID processing, LC-MS import, feature detection, and report generation."
              label="Analysis job timeline information"
            />
          ) : null}
        </CardTitle>
        {!compact ? (
          <CardDescription>
            Job status updates from the backend. Polling pauses when the job reaches a terminal state.
          </CardDescription>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-4">
        {backendUnavailable ? (
          <p className="text-sm text-warning">
            Backend unavailable or unreachable — job actions may fail until the API is reachable.
          </p>
        ) : null}
        {error ? <p className="text-sm text-destructive">{error}</p> : null}

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">Status</span>
          <Badge variant="outline" className={cn("gap-1", statusBadgeClass(status))}>
            {status ?? "—"}
          </Badge>
          {polling ? (
            <Badge variant="secondary" className="text-[10px]">
              polling
            </Badge>
          ) : null}
        </div>

        {jobId ? (
          <p className="font-mono text-xs text-muted-foreground break-all">
            job id: {jobId}
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">No active job id.</p>
        )}

        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2 text-xs">
            <span className="text-muted-foreground">Progress</span>
            <span className="font-mono text-muted-foreground">
              {progressPercent != null ? `${Math.round(progressValue)}%` : "—"}
            </span>
          </div>
          <Progress value={progressValue} className="h-2" />
        </div>

        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Current step</p>
          <p className="text-sm">{currentStep?.trim() ? currentStep : "—"}</p>
        </div>

        {artifactIds.length > 0 ? (
          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground">Artifacts</p>
            <ul className="space-y-2">
              {artifactIds.map((artifactId) => (
                <li
                  key={artifactId}
                  className="rounded-md border bg-muted/20 p-2 text-sm"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className="font-mono text-[10px]">
                      {artifactId}
                    </Badge>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        const response = {
                          artifact_id: artifactId,
                          job_id: jobId,
                          job_result: result,
                        }
                        addEvidenceItem({
                          layer: evidenceLayer,
                          title: `Artifact ${artifactId}`,
                          sourceTab,
                          status: "ready",
                          response,
                          ...extractMethodProvenanceFromUnknown(result, response),
                          ...extractMlModelProvenanceFromUnknown(result, response),
                        })
                      }}
                    >
                      Add artifact to Evidence Queue
                    </Button>
                  </div>
                  <Collapsible className="mt-2 rounded-md border bg-background">
                    <CollapsibleTrigger className="flex w-full items-center justify-between px-2 py-1.5 text-left text-xs font-medium hover:bg-muted/40">
                      <span>View artifact JSON</span>
                      <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-70" />
                    </CollapsibleTrigger>
                    <CollapsibleContent className="border-t px-2 pb-2">
                      <DeveloperJsonPanel
                        data={{
                          artifact_id: artifactId,
                          job_id: jobId,
                          job_result: result,
                        }}
                      />
                    </CollapsibleContent>
                  </Collapsible>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {status === "succeeded" && result != null ? (
          <Collapsible className="rounded-lg border">
            <CollapsibleTrigger className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-medium hover:bg-muted/40">
              <span>Job result JSON</span>
              <ChevronDown className="h-4 w-4 shrink-0 opacity-70" />
            </CollapsibleTrigger>
            <CollapsibleContent className="border-t px-3 pb-3">
              <DeveloperJsonPanel data={result} />
            </CollapsibleContent>
          </Collapsible>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="destructive"
            size="sm"
            disabled={!canCancel || cancelBusy}
            onClick={() => void cancelJob()}
          >
            {cancelBusy ? "Canceling..." : "Cancel job"}
          </Button>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">Events</p>
          <ScrollArea className={cn("rounded-md border", compact ? "max-h-32" : "max-h-48")}>
            <ul className="divide-y p-2 text-sm">
              {events.length === 0 ? (
                <li className="list-none px-1 py-2 text-muted-foreground">No events yet.</li>
              ) : (
                events.map((ev, i) => (
                  <li key={ev.id ?? `${ev.timestamp ?? "ev"}-${i}`} className="list-none space-y-0.5 py-2">
                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      {ev.timestamp ? <span>{ev.timestamp}</span> : null}
                      {ev.type ? (
                        <Badge variant="secondary" className="text-[10px]">
                          {ev.type}
                        </Badge>
                      ) : null}
                    </div>
                    {ev.message ? <p className="text-sm">{ev.message}</p> : null}
                  </li>
                ))
              )}
            </ul>
          </ScrollArea>
        </div>

        <Collapsible className="rounded-lg border">
          <CollapsibleTrigger className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-medium hover:bg-muted/40">
            <span>Developer JSON</span>
            <ChevronDown className="h-4 w-4 shrink-0 opacity-70" />
          </CollapsibleTrigger>
          <CollapsibleContent className="border-t px-3 pb-3">
            <DeveloperJsonPanel data={{ job: rawJob, events: rawEventsPayload }} />
          </CollapsibleContent>
        </Collapsible>
      </CardContent>
    </Card>
  )
}
