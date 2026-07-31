"use client"

/**
 * Repho Phase C / R12 — "Predict yield" card (Optimization tab, beside the warm-start card).
 *
 * Fits the lightweight surrogate on the project's OWN completed experiments and predicts each
 * pasted/edited condition set. Honesty contract: the producing backend ("k-NN surrogate" /
 * "GP surrogate") and the ±std uncertainty band ALWAYS render with the number; a prediction
 * with warnings is disclosed-degraded, not clean.
 */
import { useState } from "react"
import { LineChart } from "lucide-react"
import { ApiError } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { ObjectArrayField } from "@/components/ui/object-array-field"
import type { StructuredJsonField } from "@/components/ui/structured-json-editor"
import {
  parseYieldPredictionRun,
  postYieldPredictions,
  type YieldPredictionRun,
} from "@/lib/reaction/phase-c"

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v)
}

/**
 * Mechanism only. "Advisory", "never a synthesis instruction" and the
 * model-and-uncertainty disclosure promise stay in the visible description.
 */
const YIELD_PREDICTION_TOOLTIP =
  "Fits a surrogate model (k-nearest-neighbour or Gaussian process, whichever the data supports) on this project's own completed experiments only — no other campaign and no shared corpus — then scores each condition set you enter."

/** Parse the conditions textarea: one JSON object per line, or a JSON array. */
export function parseConditionsInput(text: string): {
  conditions: Record<string, unknown>[]
  error: string | null
} {
  const t = (text ?? "").trim()
  if (!t) return { conditions: [], error: "Enter at least one condition set." }
  try {
    if (t.startsWith("[")) {
      const arr: unknown = JSON.parse(t)
      if (Array.isArray(arr) && arr.every(isRecord) && arr.length > 0) {
        // Same cap as the line path — the backend rejects >200.
        if (arr.length > 200) return { conditions: [], error: "At most 200 condition sets per run." }
        return { conditions: arr, error: null }
      }
      return { conditions: [], error: "The JSON array must contain condition objects." }
    }
    const rows: Record<string, unknown>[] = []
    for (const line of t.split("\n")) {
      const s = line.trim()
      if (!s) continue
      const obj: unknown = JSON.parse(s)
      if (!isRecord(obj)) return { conditions: [], error: `Not a condition object: ${s.slice(0, 40)}` }
      rows.push(obj)
    }
    if (rows.length === 0) return { conditions: [], error: "Enter at least one condition set." }
    if (rows.length > 200) return { conditions: [], error: "At most 200 condition sets per run." }
    return { conditions: rows, error: null }
  } catch {
    return {
      conditions: [],
      error: 'Each line must be a JSON object, e.g. {"temperature": 80} — or paste one JSON array.',
    }
  }
}

/** Build a prefill template line from the project's design-space variables (R3 pattern). */
export function conditionsTemplateFromVariables(variables: unknown[]): string {
  const obj: Record<string, unknown> = {}
  for (const v of variables) {
    if (!isRecord(v)) continue
    const name = typeof v.name === "string" ? v.name : ""
    if (!name) continue
    const vt = typeof v.variable_type === "string" ? v.variable_type : ""
    if (vt === "numeric") {
      const lo = typeof v.min_value === "number" ? v.min_value : null
      const hi = typeof v.max_value === "number" ? v.max_value : null
      obj[name] = lo != null && hi != null ? (lo + hi) / 2 : 0
    } else if (vt === "categorical") {
      obj[name] = Array.isArray(v.allowed_values_json) && v.allowed_values_json.length > 0
        ? v.allowed_values_json[0]
        : ""
    } else if (vt === "boolean") {
      obj[name] = false
    }
  }
  return Object.keys(obj).length > 0 ? JSON.stringify(obj) : ""
}

/** Labeled fields for each design-space variable, so a condition row shows named inputs. */
export function conditionFieldsFromVariables(variables: unknown[]): StructuredJsonField[] {
  const fields: StructuredJsonField[] = []
  for (const v of variables) {
    if (!isRecord(v)) continue
    const name = typeof v.name === "string" ? v.name.trim() : ""
    if (!name) continue
    const vt = typeof v.variable_type === "string" ? v.variable_type : ""
    fields.push({
      key: name,
      label: name,
      type: vt === "numeric" ? "number" : "text",
      help: vt === "categorical" && Array.isArray(v.allowed_values_json) && v.allowed_values_json.length
        ? `e.g. ${v.allowed_values_json.slice(0, 3).map((x) => String(x)).join(", ")}`
        : undefined,
    })
  }
  return fields
}

export function YieldPredictionPanel({
  projectId,
  variables,
}: {
  projectId: number
  variables: unknown[]
}) {
  const [conditions, setConditions] = useState<Record<string, unknown>[]>([])
  const [requireVerified, setRequireVerified] = useState(false)
  const [run, setRun] = useState<YieldPredictionRun | null>(null)
  const [busy, setBusy] = useState(false)
  const [inputError, setInputError] = useState("")
  /** Amber guidance is reserved for the "no data to fit yet" path — not for real failures. */
  const [guidance, setGuidance] = useState("")
  const [msg, setMsg] = useState("")

  async function predict(e: React.FormEvent) {
    e.preventDefault()
    setGuidance("")
    setMsg("")
    const rows = conditions.filter((c) => Object.keys(c).length > 0)
    if (rows.length === 0) {
      setInputError("Enter at least one condition set.")
      return
    }
    if (rows.length > 200) {
      setInputError("At most 200 condition sets per run.")
      return
    }
    setInputError("")
    setBusy(true)
    try {
      const created = await postYieldPredictions(projectId, {
        conditions: rows,
        require_verified: requireVerified,
      })
      setRun(parseYieldPredictionRun(created))
    } catch (err) {
      // A 400 "Cannot fit on zero examples." is guidance (record experiments first), not a failure.
      if (err instanceof ApiError && err.status === 400) {
        const detail =
          isRecord(err.data) && typeof err.data.detail === "string" ? err.data.detail : ""
        setGuidance(
          detail.includes("zero examples")
            ? requireVerified
              ? "No verified yields yet — confirm outcomes, or turn off verified-only."
              : "No recorded yields yet — complete an experiment and record its yield."
            : detail || "The surrogate could not fit on this project's data yet.",
        )
      } else {
        // A genuine failure is not guidance — render it in the neutral message style.
        setMsg(formatApiError(err, "Could not run the yield prediction."))
      }
    } finally {
      setBusy(false)
    }
  }

  const conditionFields = conditionFieldsFromVariables(variables)

  return (
    <ModuleCard
      accent="violet"
      eyebrow="Optimization · Yield surrogate"
      title={
        <span className="inline-flex items-center gap-2">
          Predict yield
          <InfoTooltip content={YIELD_PREDICTION_TOOLTIP} label="How the yield surrogate works" />
        </span>
      }
      icon={LineChart}
      description="Ranks candidate condition sets by predicted yield. Advisory — never a synthesis instruction; the producing model and its uncertainty always show with the number."
    >
      <form className="space-y-3" onSubmit={(e) => void predict(e)}>
        <div className="space-y-1">
          <ObjectArrayField
            label="Condition sets (max 200)"
            itemLabel="Condition set"
            addLabel="Add condition set"
            fields={conditionFields}
            initialValue={conditions}
            onChange={setConditions}
            description="Each set predicts one yield. Fields come from the design-space variables."
            idPrefix="yp-conditions"
          />
          {inputError ? (
            <p role="alert" className="text-[11px] text-destructive">
              {inputError}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <Switch id="yp-verified" checked={requireVerified} onCheckedChange={setRequireVerified} />
            <Label htmlFor="yp-verified" className="text-xs">
              fit on verified outcomes only
            </Label>
          </div>
          <Button type="submit" size="sm" disabled={busy}>
            {busy ? "Predicting…" : "Predict yield"}
          </Button>
        </div>
      </form>
      {guidance ? (
        <p
          role="status"
          className="mt-3 rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground"
          style={{ borderLeft: "3px solid var(--mt-amber)" }}
        >
          {guidance}
        </p>
      ) : null}
      {msg ? (
        <p role="status" className="mt-3 text-xs text-muted-foreground">
          {msg}
        </p>
      ) : null}
      {run != null ? (
        <div className="mt-4 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary" className="text-xs">advisory</Badge>
            {/* Honesty contract: the producing model is always visible with the numbers. */}
            <Badge variant="outline" className="font-mono text-[11px]">
              model: {run.backend ?? "—"}
            </Badge>
            <Badge variant="outline" className="tabular-nums text-[11px]">
              training examples: {run.trainedN ?? "—"}
            </Badge>
            <Badge variant="outline" className="text-[11px]">
              {run.requireVerified ? "verified-only fit" : "all completed experiments"}
            </Badge>
          </div>
          <div className="space-y-2">
            {run.predictions.map((p, i) => (
              <div
                key={`yp-${i}`}
                className="space-y-1 rounded-md border px-3 py-2"
                style={p.warnings.length > 0 ? { borderLeft: "3px solid var(--mt-amber)" } : undefined}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm tabular-nums text-foreground">
                    {p.mean != null ? `${p.mean.toFixed(1)}%` : "—"}
                  </span>
                  <span className="font-mono text-xs tabular-nums text-muted-foreground">
                    ± {p.std != null ? p.std.toFixed(1) : "—"} (std)
                  </span>
                  <Badge variant="outline" className="font-mono text-[10px]">
                    {p.backend ?? run.backend ?? "—"}
                  </Badge>
                  <span className="text-[10px] text-muted-foreground">
                    n={p.nSamples ?? "—"}
                  </span>
                  {p.warnings.length > 0 ? (
                    <Badge variant="secondary" className="text-[10px]">degraded — see warnings</Badge>
                  ) : null}
                </div>
                <pre className="overflow-auto whitespace-pre-wrap break-words rounded bg-muted/40 p-2 text-[10px] leading-snug">
                  {JSON.stringify(p.conditions)}
                </pre>
                {p.warnings.length > 0 ? (
                  <ul className="list-inside list-disc text-[11px] text-muted-foreground">
                    {p.warnings.map((w, wi) => (
                      <li key={`yp-${i}-w-${wi}`}>{w}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ))}
          </div>
          {/* The disclaimer below points the reader at capability_provenance — so it must resolve
              somewhere in-product, not just exist server-side. */}
          {run.capabilityProvenance != null ? (
            <details className="rounded-md border">
              <summary className="cursor-pointer px-3 py-2 text-[11px] font-medium focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                Capability provenance — why this model produced these numbers
              </summary>
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words border-t bg-muted/40 p-2 text-[10px] leading-snug">
                {JSON.stringify(run.capabilityProvenance, null, 2)}
              </pre>
            </details>
          ) : null}
          {run.disclaimer ? (
            <p className="text-[11px] italic text-muted-foreground">{run.disclaimer}</p>
          ) : null}
        </div>
      ) : null}
    </ModuleCard>
  )
}
