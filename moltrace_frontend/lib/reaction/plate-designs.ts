// Repho R3 — HTE/DoE plate designs.
//
// Four owner-scoped routes nested under a reaction project (a non-owner gets a
// non-leaking 404). Designs are deterministic for a given request + seed.
// design_json / inputs_json are free-form objects — read defensively.

import { apiFetch } from "@/lib/api/client"

export type PlateFormat = "24" | "96" | "384"
export type PlateStrategy = "sobol" | "lhs" | "factorial" | "bo_init"

export const PLATE_FORMATS: { value: PlateFormat; rows: number; cols: number; label: string }[] = [
  { value: "24", rows: 4, cols: 6, label: "24-well (4×6)" },
  { value: "96", rows: 8, cols: 12, label: "96-well (8×12)" },
  { value: "384", rows: 16, cols: 24, label: "384-well (16×24)" },
]

export const PLATE_STRATEGIES: { value: PlateStrategy; label: string; help: string }[] = [
  { value: "sobol", label: "Sobol", help: "Low-discrepancy quasi-random — even space-filling coverage." },
  { value: "lhs", label: "Latin hypercube", help: "Stratified random sampling across each dimension." },
  { value: "factorial", label: "Factorial", help: "Full grid of level combinations (truncated to capacity)." },
  { value: "bo_init", label: "BO init seed", help: "~15–25-well seed population to bootstrap Bayesian optimization." },
]

export type PlateDesignRequest = {
  plate_format: PlateFormat
  strategy: PlateStrategy
  numeric_json?: Record<string, [number, number]>
  categorical_json?: Record<string, string[]>
  boolean_json?: string[]
  fixed_json?: Record<string, unknown>
  excluded_json?: Record<string, unknown>[]
  seed?: number
  metadata_json?: Record<string, unknown>
}

export type PlateWell = { wellId: string; conditions: Record<string, unknown> }

export type PlateDesign = {
  id: number
  reactionProjectId: number | null
  plateFormat: string
  strategy: string
  wellCount: number
  wells: PlateWell[]
  dimensions: string[]
  capacity: number | null
  rows: number | null
  cols: number | null
  provenance: Record<string, unknown> | null
  inputsJson: Record<string, unknown> | null
  warnings: string[]
  notes: string[]
  humanReviewRequired: boolean
  createdAt: string | null
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return v != null && typeof v === "object" && !Array.isArray(v)
}
function readNum(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v
  if (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v))) return Number(v)
  return null
}
function readStrArray(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []
}

function parseWells(v: unknown): PlateWell[] {
  if (!Array.isArray(v)) return []
  const out: PlateWell[] = []
  for (const w of v) {
    if (!isRecord(w)) continue
    const wellId = typeof w.well_id === "string" ? w.well_id : null
    if (!wellId) continue
    out.push({ wellId, conditions: isRecord(w.conditions) ? w.conditions : {} })
  }
  return out
}

export function parsePlateDesign(raw: unknown): PlateDesign | null {
  if (!isRecord(raw)) return null
  const id = readNum(raw.id)
  if (id == null) return null
  const dj = isRecord(raw.design_json) ? raw.design_json : {}
  const prov = isRecord(dj.provenance) ? dj.provenance : null
  const wells = parseWells(dj.wells)
  let dimensions = readStrArray(dj.dimensions)
  if (dimensions.length === 0 && wells.length > 0) {
    // Fall back to the union of condition keys if dimensions weren't provided.
    const seen = new Set<string>()
    for (const w of wells) for (const k of Object.keys(w.conditions)) seen.add(k)
    dimensions = [...seen]
  }
  return {
    id,
    reactionProjectId: readNum(raw.reaction_project_id),
    plateFormat: typeof raw.plate_format === "string" ? raw.plate_format : "",
    strategy: typeof raw.strategy === "string" ? raw.strategy : "",
    wellCount: readNum(raw.well_count) ?? wells.length,
    wells,
    dimensions,
    capacity: readNum(dj.capacity),
    rows: readNum(prov?.rows),
    cols: readNum(prov?.cols),
    provenance: prov,
    inputsJson: isRecord(raw.inputs_json) ? raw.inputs_json : null,
    warnings: readStrArray(raw.warnings),
    notes: readStrArray(raw.notes),
    humanReviewRequired: raw.human_review_required !== false,
    createdAt: typeof raw.created_at === "string" ? raw.created_at : null,
  }
}

// ── API ──────────────────────────────────────────────────────────────────────
const base = (projectId: number) => `/reaction-projects/${projectId}/plate-designs`

export async function createPlateDesign(
  projectId: number,
  body: PlateDesignRequest,
): Promise<PlateDesign | null> {
  return parsePlateDesign(await apiFetch<unknown>(base(projectId), { method: "POST", body }))
}

export async function listPlateDesigns(projectId: number): Promise<PlateDesign[]> {
  const raw = await apiFetch<unknown>(base(projectId), { method: "GET" })
  return (Array.isArray(raw) ? raw : []).map(parsePlateDesign).filter((d): d is PlateDesign => d != null)
}

export async function getPlateDesign(projectId: number, id: number): Promise<PlateDesign | null> {
  return parsePlateDesign(await apiFetch<unknown>(`${base(projectId)}/${id}`, { method: "GET" }))
}

export async function exportPlateDesign(
  projectId: number,
  id: number,
  target: "csv" | "json",
): Promise<{ target: string; content: string }> {
  const raw = await apiFetch<unknown>(`${base(projectId)}/${id}/export?target=${target}`, { method: "GET" })
  const rec = isRecord(raw) ? raw : {}
  return {
    target: typeof rec.target === "string" ? rec.target : target,
    content: typeof rec.content === "string" ? rec.content : "",
  }
}

// ── Geometry + well placement ─────────────────────────────────────────────────
export function plateGeometry(design: Pick<PlateDesign, "plateFormat" | "rows" | "cols">): {
  rows: number
  cols: number
} {
  if (design.rows && design.cols) return { rows: design.rows, cols: design.cols }
  const fmt = PLATE_FORMATS.find((f) => f.value === design.plateFormat)
  return fmt ? { rows: fmt.rows, cols: fmt.cols } : { rows: 8, cols: 12 }
}

/** Parse a well id like "A1", "H12", "P24" → zero-based {row, col}. Multi-letter
 *  rows (AA+) are supported but plates here top out at 16 rows (A–P). */
export function parseWellId(wellId: string): { row: number; col: number } | null {
  const m = /^([A-Za-z]+)(\d+)$/.exec(wellId.trim())
  if (!m) return null
  let row = 0
  for (const ch of m[1].toUpperCase()) row = row * 26 + (ch.charCodeAt(0) - 64)
  const col = Number(m[2])
  if (!Number.isFinite(col) || col < 1) return null
  return { row: row - 1, col: col - 1 }
}

export function rowLabel(rowIdx: number): string {
  let n = rowIdx + 1
  let s = ""
  while (n > 0) {
    const r = (n - 1) % 26
    s = String.fromCharCode(65 + r) + s
    n = Math.floor((n - 1) / 26)
  }
  return s
}

// ── Prefill the variable editors from the project's design-space variables ─────
export type PlatePrefill = {
  numeric: { name: string; low: string; high: string }[]
  categorical: { name: string; levels: string }[]
  boolean: string[]
}

export function prefillFromVariables(variables: unknown[]): PlatePrefill {
  const numeric: PlatePrefill["numeric"] = []
  const categorical: PlatePrefill["categorical"] = []
  const boolean: string[] = []
  for (const v of variables) {
    if (!isRecord(v)) continue
    const name = typeof v.name === "string" ? v.name : ""
    if (!name) continue
    const vt = typeof v.variable_type === "string" ? v.variable_type : ""
    if (vt === "numeric") {
      const lo = readNum(v.min_value)
      const hi = readNum(v.max_value)
      numeric.push({ name, low: lo != null ? String(lo) : "", high: hi != null ? String(hi) : "" })
    } else if (vt === "categorical") {
      const levels = Array.isArray(v.allowed_values_json)
        ? v.allowed_values_json.map((x) => String(x)).join(", ")
        : ""
      categorical.push({ name, levels })
    } else if (vt === "boolean") {
      boolean.push(name)
    }
  }
  return { numeric, categorical, boolean }
}

// ── Theme-safe colouring of the plate by a chosen dimension ────────────────────
// Cells are filled with a low-alpha tint so the well-id text (foreground token)
// stays legible in both light and dark; legend swatches use the full colour.
const CATEGORY_PALETTE = ["#6B3FE0", "#00B8D9", "#00DFA0", "#E8A030", "#E84040", "#22C55E", "#64748B", "#EC4899"]

export type PlateLegend =
  | { kind: "categorical"; entries: { label: string; color: string }[] }
  | { kind: "boolean"; entries: { label: string; color: string }[] }
  | { kind: "numeric"; min: number; max: number; color: string }
  | { kind: "none" }

function distinctValues(wells: PlateWell[], dim: string): unknown[] {
  const seen: unknown[] = []
  const keys = new Set<string>()
  for (const w of wells) {
    const v = w.conditions[dim]
    const k = JSON.stringify(v)
    if (!keys.has(k)) {
      keys.add(k)
      seen.push(v)
    }
  }
  return seen
}

function dimensionKind(wells: PlateWell[], dim: string): "numeric" | "boolean" | "categorical" {
  let sawBool = false
  for (const w of wells) {
    const v = w.conditions[dim]
    if (typeof v === "boolean") sawBool = true
    else if (typeof v === "number") return "numeric"
    else if (v != null) return "categorical"
  }
  return sawBool ? "boolean" : "categorical"
}

export function buildPlateLegend(wells: PlateWell[], dim: string | null): PlateLegend {
  if (!dim || wells.length === 0) return { kind: "none" }
  const kind = dimensionKind(wells, dim)
  if (kind === "numeric") {
    const nums = wells.map((w) => w.conditions[dim]).filter((v): v is number => typeof v === "number")
    if (!nums.length) return { kind: "none" }
    return { kind: "numeric", min: Math.min(...nums), max: Math.max(...nums), color: "#6B3FE0" }
  }
  if (kind === "boolean") {
    return {
      kind: "boolean",
      entries: [
        { label: "true", color: "#00DFA0" },
        { label: "false", color: "#64748B" },
      ],
    }
  }
  const vals = distinctValues(wells, dim).map((v) => String(v))
  return {
    kind: "categorical",
    entries: vals.map((label, i) => ({ label, color: CATEGORY_PALETTE[i % CATEGORY_PALETTE.length] })),
  }
}

/** Background tint for a well cell given the active legend + the well's value. */
export function cellTint(legend: PlateLegend, value: unknown): string {
  if (legend.kind === "none") return "transparent"
  if (legend.kind === "numeric") {
    if (typeof value !== "number") return "transparent"
    const span = legend.max - legend.min
    const norm = span > 0 ? (value - legend.min) / span : 0.5
    const alpha = (0.12 + 0.5 * norm).toFixed(3)
    return `color-mix(in srgb, ${legend.color} ${(Number(alpha) * 100).toFixed(0)}%, transparent)`
  }
  const entries = legend.kind === "boolean" ? legend.entries : legend.entries
  const label = String(value)
  const hit = entries.find((e) => e.label === label)
  if (!hit) return "transparent"
  return `color-mix(in srgb, ${hit.color} 22%, transparent)`
}

/** Trigger a client-side file download of a text blob. */
export function downloadText(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
