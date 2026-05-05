"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { SecureShareDialog } from "@/src/components/collaboration/SecureShareDialog"
import { useMemo } from "react"

export type SessionSaveFeedback = "idle" | "saving" | "saved" | "unsaved" | "error" | "unavailable"

type Props = {
  projects: unknown[]
  samples: unknown[]
  selectedProjectId: string
  selectedSampleId: string
  onProjectChange: (id: string) => void
  onSampleChange: (id: string) => void
  backendSessionId: string | null
  sessionIdInput: string
  onSessionIdInputChange: (v: string) => void
  reviewState: unknown
  saveFeedback: SessionSaveFeedback
  saveMessage: string
  busy: boolean
  onLoadSession: () => void
  onSaveSession: () => void
  onNewSession: () => void
  onSaveEvidenceQueue: () => void
  onSaveUnified: () => void
  onSaveReview: () => void
}

function projectLabel(p: unknown): string {
  if (!p || typeof p !== "object") return "—"
  const o = p as Record<string, unknown>
  return readRecordString(o, "name") ?? readRecordString(o, "project_name") ?? String(readRecordNumber(o, "id") ?? "")
}

function projectValue(p: unknown): string | undefined {
  if (!p || typeof p !== "object") return undefined
  const o = p as Record<string, unknown>
  const id = readRecordNumber(o, "id")
  return id != null ? String(id) : readRecordString(o, "id")
}

function sampleLabel(s: unknown): string {
  if (!s || typeof s !== "object") return "—"
  const o = s as Record<string, unknown>
  return (
    readRecordString(o, "sample_id") ??
    readRecordString(o, "name") ??
    (readRecordNumber(o, "id") != null ? String(readRecordNumber(o, "id")) : "—")
  )
}

function sampleValue(s: unknown): string | undefined {
  if (!s || typeof s !== "object") return undefined
  const o = s as Record<string, unknown>
  const sid = readRecordString(o, "sample_id")
  if (sid) return sid
  const id = readRecordNumber(o, "id")
  return id != null ? String(id) : readRecordString(o, "id")
}

function feedbackBadgeClass(f: SessionSaveFeedback): string {
  switch (f) {
    case "saving":
      return "border-transparent bg-secondary text-secondary-foreground"
    case "saved":
      return "border-transparent bg-emerald-600/15 text-emerald-900 dark:text-emerald-100"
    case "unsaved":
      return "border-amber-500/50 bg-amber-500/10 text-amber-900 dark:text-amber-100"
    case "error":
      return "border-transparent bg-destructive text-destructive-foreground"
    case "unavailable":
      return "border-warning/50 bg-warning/10 text-warning"
    default:
      return "border-transparent bg-muted text-muted-foreground"
  }
}

function feedbackLabel(f: SessionSaveFeedback): string {
  switch (f) {
    case "saving":
      return "saving…"
    case "saved":
      return "saved"
    case "unsaved":
      return "unsaved changes"
    case "error":
      return "save failed"
    case "unavailable":
      return "backend unavailable"
    default:
      return "idle"
  }
}

export function SpectraCheckSessionControls({
  projects,
  samples,
  selectedProjectId,
  selectedSampleId,
  onProjectChange,
  onSampleChange,
  backendSessionId,
  sessionIdInput,
  onSessionIdInputChange,
  reviewState,
  saveFeedback,
  saveMessage,
  busy,
  onLoadSession,
  onSaveSession,
  onNewSession,
  onSaveEvidenceQueue,
  onSaveUnified,
  onSaveReview,
}: Props) {
  const sessionNumericId = useMemo(() => {
    const s = backendSessionId?.trim()
    if (!s) return null
    const n = Number(s)
    return Number.isFinite(n) ? Math.trunc(n) : null
  }, [backendSessionId])

  return (
    <Card className="min-w-0 border-muted">
      <CardHeader className="pb-2">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="text-base">Session</CardTitle>
            <CardDescription>Backend SpectraCheck session, project/sample context, and saves.</CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <SecureShareDialog
              scope="session"
              lockScope
              lockTargetId
              defaultSessionId={sessionNumericId}
              disabled={sessionNumericId == null}
              trigger={
                <Button type="button" size="sm" variant="outline" disabled={sessionNumericId == null}>
                  Secure share
                </Button>
              }
            />
            <Badge variant="outline" className={cn("font-normal", feedbackBadgeClass(saveFeedback))}>
              {feedbackLabel(saveFeedback)}
            </Badge>
            {saveMessage ? (
              <span className="max-w-[min(100%,20rem)] text-xs text-muted-foreground">{saveMessage}</span>
            ) : null}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid min-w-0 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Project</Label>
            <Select value={selectedProjectId || "__none__"} onValueChange={(v) => onProjectChange(v === "__none__" ? "" : v)}>
              <SelectTrigger className="w-full min-w-0">
                <SelectValue placeholder="Select project" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">(none)</SelectItem>
                {projects.map((p, i) => {
                  const v = projectValue(p)
                  if (!v) return null
                  return (
                    <SelectItem key={`${v}-${i}`} value={v}>
                      {projectLabel(p)}
                    </SelectItem>
                  )
                })}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Sample</Label>
            <Select
              value={selectedSampleId || "__none__"}
              onValueChange={(v) => onSampleChange(v === "__none__" ? "" : v)}
              disabled={!selectedProjectId}
            >
              <SelectTrigger className="w-full min-w-0">
                <SelectValue placeholder="Select sample" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">(none)</SelectItem>
                {samples.map((s, i) => {
                  const v = sampleValue(s)
                  if (!v) return null
                  return (
                    <SelectItem key={`${v}-${i}`} value={v}>
                      {sampleLabel(s)}
                    </SelectItem>
                  )
                })}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5 sm:col-span-2 lg:col-span-2">
            <Label className="text-xs">Session id (load)</Label>
            <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
              <Input
                className="min-w-0 font-mono text-xs"
                value={sessionIdInput}
                onChange={(e) => onSessionIdInputChange(e.target.value)}
                placeholder="session id"
              />
              <div className="flex shrink-0 flex-wrap gap-2">
                <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={onLoadSession}>
                  Load session
                </Button>
                <Button type="button" size="sm" variant="outline" disabled={busy} onClick={onNewSession}>
                  New session
                </Button>
              </div>
            </div>
            {backendSessionId ? (
              <p className="text-xs text-muted-foreground">
                Active backend session: <span className="font-mono">{backendSessionId}</span>
              </p>
            ) : null}
          </div>
        </div>

        <div className="flex min-w-0 flex-wrap gap-2">
          <Button type="button" size="sm" disabled={busy} onClick={onSaveSession}>
            Save session
          </Button>
          <Button type="button" size="sm" variant="outline" disabled={busy || !backendSessionId} onClick={onSaveEvidenceQueue}>
            Save evidence queue
          </Button>
          <Button type="button" size="sm" variant="outline" disabled={busy || !backendSessionId} onClick={onSaveUnified}>
            Save unified evidence
          </Button>
          <Button type="button" size="sm" variant="outline" disabled={busy || !backendSessionId} onClick={onSaveReview}>
            Save review
          </Button>
        </div>

        {reviewState != null ? (
          <div className="min-w-0">
            <p className="mb-1 text-xs font-medium text-muted-foreground">Review (developer)</p>
            <DeveloperJsonPanel data={reviewState} />
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
