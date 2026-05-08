"use client"

import { useCallback, useEffect, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { InfoTooltip } from "@/components/ui/info-tooltip"

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

function readBool(o: Record<string, unknown>, keys: string[]): boolean | undefined {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "boolean") return v
    if (v === "true") return true
    if (v === "false") return false
  }
  return undefined
}

function readNum(o: Record<string, unknown>, keys: string[]): number | undefined {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "number" && Number.isFinite(v)) return v
    if (typeof v === "string" && v.trim()) {
      const n = Number(v)
      if (Number.isFinite(n)) return n
    }
  }
  return undefined
}

export type WorkflowTemplateStep = {
  label: string
  detail: string
}

export type WorkflowTemplateCardModel = {
  id: string
  /** Same as `id` when the API only provides one identifier. */
  templateSlug: string
  name: string
  category: string
  description: string
  requiredInputsCount: number
  estimatedStepsCount: number
  humanReviewRequired: boolean
  steps: WorkflowTemplateStep[]
  /** Raw-ish rows from `required_inputs` / `requiredInputs` for workflow run forms. */
  requiredInputSpecs: unknown[]
  /** Raw-ish rows from `optional_inputs` / `optionalInputs`. */
  optionalInputSpecs: unknown[]
}

function extractTemplatesArray(root: unknown): unknown[] {
  if (Array.isArray(root)) return root
  if (!isRecord(root)) return []
  for (const k of ["templates", "items", "workflows", "results", "data"]) {
    const v = root[k]
    if (Array.isArray(v)) return v
  }
  return []
}

function normalizeStepRow(raw: unknown): WorkflowTemplateStep | null {
  if (!isRecord(raw)) return null
  const label =
    readStr(raw, ["title", "name", "label", "step_name", "stepName", "stage"]) ||
    readStr(raw, ["type", "kind"]) ||
    "Step"
  const detail =
    readStr(raw, ["description", "detail", "summary", "message"]) ||
    readStr(raw, ["action", "operation"]) ||
    ""
  return { label, detail }
}

function normalizeWorkflowTemplate(raw: unknown): WorkflowTemplateCardModel | null {
  if (!isRecord(raw)) return null
  const id =
    readStr(raw, ["id", "workflow_id", "workflowId", "slug", "template_id", "templateId"]) || ""
  const name =
    readStr(raw, ["name", "title", "workflow_name", "workflowName", "display_name", "displayName"]) || ""
  if (!name.trim()) return null

  const category =
    readStr(raw, ["category", "workflow_category", "workflowCategory", "group", "kind"]) || "General"
  const description =
    readStr(raw, ["description", "summary", "about"]) ||
    "Predefined workflow for SpectraCheck sessions."

  const requiredInputsCount =
    readNum(raw, [
      "required_inputs_count",
      "requiredInputsCount",
      "inputs_required",
      "inputsRequired",
      "required_input_count",
    ]) ??
    (Array.isArray(raw.required_inputs) ? raw.required_inputs.length : undefined) ??
    (Array.isArray(raw.inputs) ? raw.inputs.length : undefined) ??
    0

  let estimatedStepsCount =
    readNum(raw, ["estimated_steps_count", "estimatedStepsCount", "step_count", "steps_count", "stage_count"]) ?? 0

  const stepsRaw = raw.steps ?? raw.workflow_steps ?? raw.stages ?? raw.phases
  const stepsList: WorkflowTemplateStep[] = []
  if (Array.isArray(stepsRaw)) {
    for (const s of stepsRaw) {
      const row = normalizeStepRow(s)
      if (row) stepsList.push(row)
    }
  }
  if (estimatedStepsCount <= 0 && stepsList.length > 0) estimatedStepsCount = stepsList.length

  const humanReviewRequired =
    readBool(raw, ["human_review_required", "humanReviewRequired", "requires_human_review", "needs_human_review"]) ??
    false

  const resolvedId = id.trim() || name.trim().toLowerCase().replace(/\s+/g, "-")
  const slug =
    readStr(raw, ["slug", "template_slug", "templateSlug"])?.trim() || resolvedId
  const requiredInputSpecs = Array.isArray(raw.required_inputs)
    ? raw.required_inputs
    : Array.isArray(raw.requiredInputs)
      ? raw.requiredInputs
      : []
  const optionalInputSpecs = Array.isArray(raw.optional_inputs)
    ? raw.optional_inputs
    : Array.isArray(raw.optionalInputs)
      ? raw.optionalInputs
      : []

  return {
    id: resolvedId,
    templateSlug: slug,
    name: name.trim(),
    category: category.trim() || "General",
    description: description.trim(),
    requiredInputsCount: Math.max(0, Math.floor(requiredInputsCount)),
    estimatedStepsCount: Math.max(0, Math.floor(estimatedStepsCount)),
    humanReviewRequired,
    steps: stepsList,
    requiredInputSpecs,
    optionalInputSpecs,
  }
}

function templatesFromPayload(data: unknown): WorkflowTemplateCardModel[] {
  const rows = extractTemplatesArray(data)
  const out: WorkflowTemplateCardModel[] = []
  for (const r of rows) {
    const m = normalizeWorkflowTemplate(r)
    if (m) out.push(m)
  }
  return out
}

const GALLERY_TOOLTIP =
  "Workflow templates run a predefined sequence of analysis, QC, evidence, unified confidence, and report steps so the session can be reproduced."

type LoadState =
  | { status: "loading" }
  | { status: "ok"; templates: WorkflowTemplateCardModel[] }
  | { status: "error"; message: string }

export type WorkflowTemplateGalleryProps = {
  /** When set with `onTemplateSelect`, selection is controlled by the parent (e.g. workflow run launcher). */
  selectedTemplateId?: string | null
  onTemplateSelect?: (template: WorkflowTemplateCardModel) => void
}

export function WorkflowTemplateGallery(props: WorkflowTemplateGalleryProps = {}) {
  const { selectedTemplateId: controlledSelectedId, onTemplateSelect } = props
  const [load, setLoad] = useState<LoadState>({ status: "loading" })
  const [internalSelectedId, setInternalSelectedId] = useState<string | null>(null)
  const controlledId = controlledSelectedId ?? null
  const selectedId = onTemplateSelect ? controlledId : internalSelectedId
  const [stepsFor, setStepsFor] = useState<WorkflowTemplateCardModel | null>(null)

  const fetchTemplates = useCallback(async () => {
    setLoad({ status: "loading" })
    try {
      const data = await apiFetch<unknown>("/workflow-templates", { method: "GET" })
      const templates = templatesFromPayload(data)
      setLoad({ status: "ok", templates })
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message || `Request failed (${err.status})`
          : err instanceof Error
            ? err.message
            : "Could not reach the workflow templates service."
      setLoad({ status: "error", message: msg })
    }
  }, [])

  useEffect(() => {
    void fetchTemplates()
  }, [fetchTemplates])

  return (
    <div className="space-y-4">
      <Card className="border-muted">
        <CardHeader className="pb-2">
          <CardTitle className="flex flex-wrap items-center gap-2 text-base">
            Workflow Template Gallery
            <InfoTooltip content={GALLERY_TOOLTIP} label="About workflow templates" />
          </CardTitle>
          <CardDescription>
            Browse predefined analysis workflows. Select one, then configure and create a run in the{" "}
            <span className="font-medium text-foreground">Workflow Run Launcher</span> below.
          </CardDescription>
        </CardHeader>
      </Card>

      {load.status === "loading" ? (
        <p className="text-sm text-muted-foreground">Loading workflow templates…</p>
      ) : null}

      {load.status === "error" ? (
        <Alert className="border-muted bg-muted/40">
          <AlertTitle className="text-sm">Workflow templates unavailable</AlertTitle>
          <AlertDescription className="text-xs text-muted-foreground">
            Workflow templates couldn&apos;t load ({load.message}). Check that the analysis service is
            running and reachable through your proxy. No template data is shown below to avoid
            misleading placeholders.
          </AlertDescription>
        </Alert>
      ) : null}

      {load.status === "ok" && load.templates.length === 0 ? (
        <p className="text-sm text-muted-foreground">No workflow templates were returned.</p>
      ) : null}

      {load.status === "ok" && load.templates.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2">
          {load.templates.map((t) => {
            const selected = selectedId === t.id
            return (
              <Card
                key={t.id}
                className={`min-w-0 flex flex-col border-muted shadow-sm ${selected ? "ring-2 ring-primary/30" : ""}`}
              >
                <CardHeader className="pb-2">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <CardTitle className="text-base leading-snug">{t.name}</CardTitle>
                    <Badge variant="secondary" className="shrink-0 text-[10px] font-normal">
                      {t.category}
                    </Badge>
                  </div>
                  <CardDescription className="text-sm leading-relaxed">{t.description}</CardDescription>
                </CardHeader>
                <CardContent className="flex flex-1 flex-col gap-3 pb-2 text-sm">
                  <div className="flex flex-wrap gap-2">
                    <Badge variant="outline" className="text-[10px] font-normal tabular-nums">
                      Required inputs: {t.requiredInputsCount}
                    </Badge>
                    <Badge variant="outline" className="text-[10px] font-normal tabular-nums">
                      Est. steps: {t.estimatedStepsCount}
                    </Badge>
                    {t.humanReviewRequired ? (
                      <Badge variant="outline" className="border-amber-600/40 text-[10px] font-normal text-amber-950">
                        Human review required
                      </Badge>
                    ) : null}
                  </div>
                </CardContent>
                <CardFooter className="mt-auto flex flex-wrap gap-2 border-t pt-4">
                  <Button
                    type="button"
                    size="sm"
                    variant={selected ? "default" : "secondary"}
                    className="w-full sm:w-auto"
                    onClick={() => {
                      if (onTemplateSelect) onTemplateSelect(t)
                      else setInternalSelectedId(t.id)
                    }}
                  >
                    Select workflow
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="w-full sm:w-auto"
                    onClick={() => setStepsFor(t)}
                  >
                    View steps
                  </Button>
                </CardFooter>
              </Card>
            )
          })}
        </div>
      ) : null}

      <Dialog open={stepsFor != null} onOpenChange={(o) => !o && setStepsFor(null)}>
        <DialogContent className="max-h-[min(80vh,520px)] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{stepsFor?.name ?? "Workflow steps"}</DialogTitle>
            <DialogDescription>
              Step outline from the template definition. Execution order may depend on session state when runs are enabled.
            </DialogDescription>
          </DialogHeader>
          {stepsFor && stepsFor.steps.length > 0 ? (
            <ol className="list-inside list-decimal space-y-3 text-sm">
              {stepsFor.steps.map((s, i) => (
                <li key={`${stepsFor.id}-step-${i}`} className="text-muted-foreground">
                  <span className="font-medium text-foreground">{s.label}</span>
                  {s.detail ? <p className="mt-1 pl-1 text-xs leading-relaxed">{s.detail}</p> : null}
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-muted-foreground">
              No step list was included for this template in the API response.
            </p>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
