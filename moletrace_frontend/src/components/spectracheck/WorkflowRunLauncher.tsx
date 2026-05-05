"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import type { WorkflowTemplateCardModel } from "@/src/components/spectracheck/WorkflowTemplateGallery"
import { WorkflowRunTimeline } from "@/src/components/spectracheck/WorkflowRunTimeline"
import type { EvidenceItem } from "@/src/lib/spectracheck/evidence-types"
import type { SessionFileRecord } from "@/src/lib/spectracheck/session-file-record"
import { useSpectraCheckEvidence } from "@/src/lib/spectracheck/useSpectraCheckEvidence"
import { trackWorkflowStarted } from "@/src/lib/analytics/analytics-client"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(o: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "string" && v.trim()) return v.trim()
    if (typeof v === "number" && Number.isFinite(v)) return String(v)
  }
  return ""
}

function extractKeyFromInputSpec(spec: unknown): string | null {
  if (typeof spec === "string" && spec.trim()) return spec.trim().toLowerCase().replace(/\s+/g, "_")
  if (!isRecord(spec)) return null
  const k = readStr(spec, ["key", "name", "field", "id", "input_key", "inputKey"])
  return k ? k.trim().toLowerCase().replace(/\s+/g, "_") : null
}

/** Common workflow input keys supported by this launcher (matches backend contract names). */
const FALLBACK_INPUT_KEYS = [
  "session_id",
  "sample_id",
  "solvent",
  "candidates_text",
  "observed_proton_text",
  "observed_carbon13_text",
  "file_ids",
  "observed_mz",
  "adduct",
  "msms_peak_list_text",
  "lcms_file_id",
  "blank_file_id",
  "include_report_draft",
] as const

function collectKeysFromTemplate(template: WorkflowTemplateCardModel | null): string[] {
  if (!template) return []
  const keys = new Set<string>()
  for (const s of template.requiredInputSpecs) {
    const k = extractKeyFromInputSpec(s)
    if (k) keys.add(k)
  }
  for (const s of template.optionalInputSpecs) {
    const k = extractKeyFromInputSpec(s)
    if (k) keys.add(k)
  }
  if (keys.size === 0) return [...FALLBACK_INPUT_KEYS]
  const ordered: string[] = []
  for (const fk of FALLBACK_INPUT_KEYS) {
    if (keys.has(fk)) ordered.push(fk)
  }
  for (const k of keys) {
    if (!ordered.includes(k)) ordered.push(k)
  }
  return ordered
}

function extractWorkflowRunId(data: unknown): string | null {
  if (typeof data === "string" && data.trim()) return data.trim()
  if (!isRecord(data)) return null
  const id =
    readStr(data, ["workflow_run_id", "workflowRunId", "id", "run_id", "runId"]) ?? ""
  if (id.trim()) return id.trim()
  const nested = data.data
  if (isRecord(nested)) {
    const inner =
      readStr(nested, ["workflow_run_id", "workflowRunId", "id", "run_id", "runId"]) ?? ""
    if (inner.trim()) return inner.trim()
  }
  return null
}

export type WorkflowRunLauncherProps = {
  selectedTemplate: WorkflowTemplateCardModel | null
  backendSessionId: string | null
  sampleId: string
  solvent: string
  candidatesText: string
  protonText: string
  carbonText: string
  sessionFiles: SessionFileRecord[]
  /** Navigate SpectraCheck tabs (e.g. Report / Unified) after workflow handoff. */
  onNavigateToTab?: (tab: string) => void
}

export function WorkflowRunLauncher({
  selectedTemplate,
  backendSessionId,
  sampleId,
  solvent,
  candidatesText,
  protonText,
  carbonText,
  sessionFiles,
  onNavigateToTab,
}: WorkflowRunLauncherProps) {
  const { evidenceItems } = useSpectraCheckEvidence()

  const inputKeys = useMemo(() => collectKeysFromTemplate(selectedTemplate), [selectedTemplate])

  const [sessionIdField, setSessionIdField] = useState("")
  const [sampleIdField, setSampleIdField] = useState("")
  const [solventField, setSolventField] = useState("")
  const [candidatesField, setCandidatesField] = useState("")
  const [protonField, setProtonField] = useState("")
  const [carbonField, setCarbonField] = useState("")
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([])
  const [observedMz, setObservedMz] = useState("")
  const [adduct, setAdduct] = useState("[M+H]+")
  const [msmsPeakList, setMsmsPeakList] = useState("")
  const [lcmsFileId, setLcmsFileId] = useState("")
  const [blankFileId, setBlankFileId] = useState("")
  const [includeReportDraft, setIncludeReportDraft] = useState(false)
  const [extraInputs, setExtraInputs] = useState<Record<string, string>>({})

  const [workflowRunId, setWorkflowRunId] = useState<string | null>(null)
  const [createResponse, setCreateResponse] = useState<unknown>(null)
  const [startResponse, setStartResponse] = useState<unknown>(null)
  const [phase, setPhase] = useState<"idle" | "created" | "started">("idle")
  const [createBusy, setCreateBusy] = useState(false)
  const [startBusy, setStartBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setSessionIdField(backendSessionId?.trim() ?? "")
    setSampleIdField(sampleId)
    setSolventField(solvent)
    setCandidatesField(candidatesText)
    setProtonField(protonText)
    setCarbonField(carbonText)
    setSelectedFileIds([])
    setObservedMz("")
    setAdduct("[M+H]+")
    setMsmsPeakList("")
    setLcmsFileId("")
    setBlankFileId("")
    setIncludeReportDraft(false)
    setExtraInputs({})
    setWorkflowRunId(null)
    setCreateResponse(null)
    setStartResponse(null)
    setPhase("idle")
    setError(null)
  }, [
    selectedTemplate?.id,
    backendSessionId,
    sampleId,
    solvent,
    candidatesText,
    protonText,
    carbonText,
  ])

  function toggleFileId(fid: string, checked: boolean) {
    setSelectedFileIds((prev) =>
      checked ? [...prev.filter((x) => x !== fid), fid] : prev.filter((x) => x !== fid),
    )
  }

  const buildInputsObject = useCallback((): Record<string, unknown> => {
    const inputs: Record<string, unknown> = {}
    const want = new Set(inputKeys.length ? inputKeys : [...FALLBACK_INPUT_KEYS])

    const setIf = (key: string, value: unknown) => {
      if (!want.has(key)) return
      if (value === undefined || value === null) return
      if (typeof value === "string" && !value.trim() && key !== "include_report_draft") return
      inputs[key] = value
    }

    setIf("session_id", sessionIdField.trim() || null)
    setIf("sample_id", sampleIdField.trim())
    setIf("solvent", solventField.trim())
    setIf("candidates_text", candidatesField)
    setIf("observed_proton_text", protonField)
    setIf("observed_carbon13_text", carbonField)
    if (want.has("file_ids") && selectedFileIds.length > 0) inputs.file_ids = selectedFileIds
    setIf("observed_mz", observedMz.trim())
    setIf("adduct", adduct.trim())
    setIf("msms_peak_list_text", msmsPeakList.trim())
    setIf("lcms_file_id", lcmsFileId.trim())
    setIf("blank_file_id", blankFileId.trim())
    if (want.has("include_report_draft")) inputs.include_report_draft = includeReportDraft

    const builtIn = new Set<string>([...FALLBACK_INPUT_KEYS])
    for (const key of inputKeys) {
      if (builtIn.has(key)) continue
      const v = extraInputs[key]?.trim()
      if (v) inputs[key] = v
    }

    return inputs
  }, [
    inputKeys,
    sessionIdField,
    sampleIdField,
    solventField,
    candidatesField,
    protonField,
    carbonField,
    selectedFileIds,
    observedMz,
    adduct,
    msmsPeakList,
    lcmsFileId,
    blankFileId,
    includeReportDraft,
    extraInputs,
  ])

  const buildMetadata = useCallback(
    (items: EvidenceItem[]) => ({
      spectracheck_evidence_queue: items.map((i) => ({
        id: i.id,
        layer: i.layer,
        title: i.title,
        selected_for_unified: i.selectedForUnified,
      })),
    }),
    [],
  )

  async function handleCreateRun() {
    if (!selectedTemplate) return
    setCreateBusy(true)
    setError(null)
    try {
      const inputs = buildInputsObject()
      const body = {
        template_id: selectedTemplate.id,
        template_slug: selectedTemplate.templateSlug,
        session_id: sessionIdField.trim() || null,
        sample_id: sampleIdField.trim() || null,
        inputs,
        metadata: buildMetadata(evidenceItems),
      }
      const data = await apiFetch<unknown>("/workflow-runs", { method: "POST", body })
      setCreateResponse(data)
      const rid = extractWorkflowRunId(data)
      setWorkflowRunId(rid)
      setPhase(rid ? "created" : "idle")
      if (!rid) {
        setError(
          "Workflow run was created but no workflow_run_id was found in the response. Check the summary below or Developer JSON.",
        )
      }
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message || `Create failed (${err.status})`
          : err instanceof Error
            ? err.message
            : "Failed to create workflow run."
      setError(msg)
      setWorkflowRunId(null)
      setCreateResponse(null)
      setPhase("idle")
    } finally {
      setCreateBusy(false)
    }
  }

  async function handleStartRun() {
    if (!workflowRunId?.trim()) return
    setStartBusy(true)
    setError(null)
    try {
      const data = await apiFetch<unknown>(`/workflow-runs/${encodeURIComponent(workflowRunId.trim())}/start`, {
        method: "POST",
        body: {},
      })
      setStartResponse(data ?? {})
      setPhase("started")
      if (selectedTemplate) {
        trackWorkflowStarted({
          workflow_run_id: workflowRunId.trim(),
          session_id: sessionIdField.trim() || undefined,
          metadata: {
            workflow_template_slug: selectedTemplate.templateSlug ?? "unknown",
          },
        })
      }
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message || `Start failed (${err.status})`
          : err instanceof Error
            ? err.message
            : "Failed to start workflow run."
      setError(msg)
    } finally {
      setStartBusy(false)
    }
  }

  function renderField(key: string) {
    switch (key) {
      case "session_id":
        return (
          <div key={key} className="space-y-2">
            <Label htmlFor={`wf-${key}`}>session_id</Label>
            <Input
              id={`wf-${key}`}
              value={sessionIdField}
              onChange={(e) => setSessionIdField(e.target.value)}
              className="font-mono text-xs"
              placeholder="SpectraCheck session UUID"
            />
          </div>
        )
      case "sample_id":
        return (
          <div key={key} className="space-y-2">
            <Label htmlFor={`wf-${key}`}>sample_id</Label>
            <Input id={`wf-${key}`} value={sampleIdField} onChange={(e) => setSampleIdField(e.target.value)} />
          </div>
        )
      case "solvent":
        return (
          <div key={key} className="space-y-2">
            <Label htmlFor={`wf-${key}`}>solvent</Label>
            <Input id={`wf-${key}`} value={solventField} onChange={(e) => setSolventField(e.target.value)} />
          </div>
        )
      case "candidates_text":
        return (
          <div key={key} className="space-y-2">
            <Label htmlFor={`wf-${key}`}>candidates_text</Label>
            <Textarea
              id={`wf-${key}`}
              value={candidatesField}
              onChange={(e) => setCandidatesField(e.target.value)}
              rows={4}
              className="min-h-[88px] resize-y font-mono text-xs"
            />
          </div>
        )
      case "observed_proton_text":
        return (
          <div key={key} className="space-y-2">
            <Label htmlFor={`wf-${key}`}>observed_proton_text</Label>
            <Textarea
              id={`wf-${key}`}
              value={protonField}
              onChange={(e) => setProtonField(e.target.value)}
              rows={4}
              className="min-h-[88px] resize-y text-sm"
            />
          </div>
        )
      case "observed_carbon13_text":
        return (
          <div key={key} className="space-y-2">
            <Label htmlFor={`wf-${key}`}>observed_carbon13_text</Label>
            <Textarea
              id={`wf-${key}`}
              value={carbonField}
              onChange={(e) => setCarbonField(e.target.value)}
              rows={4}
              className="min-h-[88px] resize-y text-sm"
            />
          </div>
        )
      case "file_ids":
        return (
          <div key={key} className="space-y-2">
            <Label>file_ids (session files)</Label>
            {sessionFiles.length === 0 ? (
              <p className="text-xs text-muted-foreground">No session files loaded for this SpectraCheck session.</p>
            ) : (
              <ul className="max-h-40 space-y-2 overflow-y-auto rounded-md border bg-muted/20 p-2 text-xs">
                {sessionFiles.map((f) => (
                  <li key={f.file_id} className="flex items-start gap-2">
                    <Checkbox
                      id={`wf-file-${f.file_id}`}
                      checked={selectedFileIds.includes(f.file_id)}
                      onCheckedChange={(c) => toggleFileId(f.file_id, c === true)}
                    />
                    <label htmlFor={`wf-file-${f.file_id}`} className="cursor-pointer leading-snug">
                      <span className="font-mono text-[10px]">{f.file_id}</span>
                      <span className="text-muted-foreground"> · </span>
                      <span>{f.filename}</span>
                      <Badge variant="outline" className="ml-1 align-middle text-[9px] font-normal">
                        {f.file_kind}
                      </Badge>
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )
      case "observed_mz":
        return (
          <div key={key} className="space-y-2">
            <Label htmlFor={`wf-${key}`}>observed_mz</Label>
            <Input id={`wf-${key}`} value={observedMz} onChange={(e) => setObservedMz(e.target.value)} />
          </div>
        )
      case "adduct":
        return (
          <div key={key} className="space-y-2">
            <Label htmlFor={`wf-${key}`}>adduct</Label>
            <Input id={`wf-${key}`} value={adduct} onChange={(e) => setAdduct(e.target.value)} />
          </div>
        )
      case "msms_peak_list_text":
        return (
          <div key={key} className="space-y-2">
            <Label htmlFor={`wf-${key}`}>msms_peak_list_text</Label>
            <Textarea
              id={`wf-${key}`}
              value={msmsPeakList}
              onChange={(e) => setMsmsPeakList(e.target.value)}
              rows={5}
              className="min-h-[100px] resize-y font-mono text-xs"
            />
          </div>
        )
      case "lcms_file_id":
        return (
          <div key={key} className="space-y-2">
            <Label htmlFor={`wf-${key}`}>lcms_file_id</Label>
            <Select value={lcmsFileId || "__none__"} onValueChange={(v) => setLcmsFileId(v === "__none__" ? "" : v)}>
              <SelectTrigger id={`wf-${key}`} className="font-mono text-xs">
                <SelectValue placeholder="Select file id" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">—</SelectItem>
                {sessionFiles.map((f) => (
                  <SelectItem key={f.file_id} value={f.file_id} className="font-mono text-xs">
                    {f.file_id} ({f.filename})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )
      case "blank_file_id":
        return (
          <div key={key} className="space-y-2">
            <Label htmlFor={`wf-${key}`}>blank_file_id (optional)</Label>
            <Select value={blankFileId || "__none__"} onValueChange={(v) => setBlankFileId(v === "__none__" ? "" : v)}>
              <SelectTrigger id={`wf-${key}`} className="font-mono text-xs">
                <SelectValue placeholder="Optional blank reference file" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">—</SelectItem>
                {sessionFiles.map((f) => (
                  <SelectItem key={`b-${f.file_id}`} value={f.file_id} className="font-mono text-xs">
                    {f.file_id} ({f.filename})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )
      case "include_report_draft":
        return (
          <div key={key} className="flex items-center gap-2 space-y-0">
            <Checkbox
              id={`wf-${key}`}
              checked={includeReportDraft}
              onCheckedChange={(c) => setIncludeReportDraft(c === true)}
            />
            <Label htmlFor={`wf-${key}`} className="cursor-pointer font-normal">
              include_report_draft
            </Label>
          </div>
        )
      default:
        return (
          <div key={key} className="space-y-2">
            <Label htmlFor={`wf-${key}`}>{key}</Label>
            <Input
              id={`wf-${key}`}
              value={extraInputs[key] ?? ""}
              onChange={(e) => setExtraInputs((p) => ({ ...p, [key]: e.target.value }))}
              className="font-mono text-xs"
              placeholder="Template-defined input"
            />
          </div>
        )
    }
  }

  const noTemplate = selectedTemplate == null

  return (
    <Card className="min-w-0 border-muted">
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Workflow Run Launcher</CardTitle>
        <CardDescription>
          Create a workflow run with <code className="text-xs">POST /workflow-runs</code>, then start it with{" "}
          <code className="text-xs">POST /workflow-runs/{"{workflow_run_id}"}/start</code>. Runs are not started
          automatically.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {noTemplate ? (
          <p className="text-sm text-muted-foreground">Select a workflow template above to configure inputs.</p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">{selectedTemplate.name}</span>
              <Badge variant="secondary" className="text-[10px] font-normal">
                {selectedTemplate.category}
              </Badge>
            </div>

            <div className="grid gap-4 md:grid-cols-2">{inputKeys.map((k) => renderField(k))}</div>

            <div className="rounded-md border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
              <p className="font-medium text-foreground">Evidence queue (metadata only)</p>
              <p className="mt-1">
                {evidenceItems.length} item(s) in queue
                {evidenceItems.filter((i) => i.selectedForUnified).length > 0
                  ? ` · ${evidenceItems.filter((i) => i.selectedForUnified).length} selected for Unified`
                  : ""}
                . Sent under <code className="text-[10px]">metadata</code> — file binaries are not stored in localStorage.
              </p>
            </div>
          </>
        )}

        {error ? (
          <Alert variant="destructive">
            <AlertTitle className="text-sm">Request failed</AlertTitle>
            <AlertDescription className="text-xs">{error}</AlertDescription>
          </Alert>
        ) : null}

        {phase === "started" && !error ? (
          <Alert className="border-emerald-600/40 bg-emerald-50/50 dark:bg-emerald-950/20">
            <AlertTitle className="text-sm">Workflow started</AlertTitle>
            <AlertDescription className="text-xs text-muted-foreground">
              Start request completed. Monitor jobs from Recent analysis jobs on the Overview tab when available.
            </AlertDescription>
          </Alert>
        ) : null}

        {createResponse != null && workflowRunId ? (
          <div className="rounded-md border bg-card p-3 text-xs">
            <p className="font-medium text-foreground">Workflow run summary</p>
            <p className="mt-1 font-mono text-[10px] text-muted-foreground break-all">
              workflow_run_id: {workflowRunId}
            </p>
            <pre className="mt-2 max-h-48 overflow-auto rounded bg-muted/40 p-2 text-[10px] leading-relaxed">
              {JSON.stringify(createResponse, null, 2)}
            </pre>
            {startResponse != null ? (
              <>
                <p className="mt-3 font-medium text-foreground">Start response</p>
                <pre className="mt-2 max-h-36 overflow-auto rounded bg-muted/40 p-2 text-[10px] leading-relaxed">
                  {JSON.stringify(startResponse, null, 2)}
                </pre>
              </>
            ) : null}
          </div>
        ) : null}

        {workflowRunId ? (
          <WorkflowRunTimeline
            workflowRunId={workflowRunId}
            onNavigateToTab={onNavigateToTab}
            sampleId={sampleId}
            workflowTemplateSlug={selectedTemplate?.templateSlug ?? null}
          />
        ) : null}
      </CardContent>
      <CardFooter className="flex flex-wrap gap-2 border-t pt-4">
        <Button type="button" disabled={noTemplate || createBusy} onClick={() => void handleCreateRun()}>
          {createBusy ? "Creating…" : "Create Workflow Run"}
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={!workflowRunId || startBusy || phase === "started"}
          onClick={() => void handleStartRun()}
        >
          {startBusy ? "Starting…" : "Start Workflow"}
        </Button>
      </CardFooter>
    </Card>
  )
}
