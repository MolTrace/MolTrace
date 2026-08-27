"use client"

import { Card, CardContent } from "@/components/ui/card"
import { Settings2 } from "lucide-react"

/**
 * Friendly key/value display of the ``processing_parameters`` block returned
 * by ``/nmr/raw-fid/process``. Replaces the previous JSON-in-a-textarea dump
 * with a structured grid grouped by concern:
 *
 *   - Spectrum acquisition (zero-fill factor, line broadening, apodization)
 *   - Phase correction (auto / mode / P0 / P1)
 *   - Baseline correction (mode / order / lock)
 *   - Digital-filter / group-delay corrections (Bruker FID acquisition)
 *
 * Designed to mirror the industry-standard NMR "Processing Parameters" dialog
 * layout so reviewers recognise it at a glance. Unknown / forward-compatible
 * keys are rendered in an "Other parameters" group so future backend additions
 * surface without a frontend change.
 */

type Primitive = string | number | boolean | null

type FormattableValue = Primitive | Record<string, Primitive | unknown> | unknown[]

function isRecord(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v)
}

function isFiniteNumber(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v)
}

/** Pretty-print a single scalar value. Booleans render as Yes/No; numbers
 * stay numeric; strings pass through. ``null`` / ``undefined`` becomes "—".
 */
function formatValue(value: FormattableValue): string {
  if (value === null || value === undefined) return "—"
  if (typeof value === "boolean") return value ? "Yes" : "No"
  if (isFiniteNumber(value)) {
    // Whole numbers stay integer; small floats keep up to 3 decimals.
    return Number.isInteger(value) ? String(value) : Number(value.toFixed(3)).toString()
  }
  if (typeof value === "string") {
    if (value.length === 0) return "—"
    return value
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return "—"
    return value
      .map((entry) =>
        typeof entry === "object" && entry !== null
          ? JSON.stringify(entry)
          : String(entry),
      )
      .join(", ")
  }
  // Nested record — render as a brace-wrapped one-liner for readability.
  const entries = Object.entries(value as Record<string, unknown>)
  if (entries.length === 0) return "—"
  return entries
    .map(([k, v]) => `${humanizeLabel(k)}: ${formatValue(v as FormattableValue)}`)
    .join("; ")
}

/** "auto_phase" → "Auto phase", "phase_p0_deg" → "Phase P0 (deg)". */
function humanizeLabel(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\bp0\b/g, "P0")
    .replace(/\bp1\b/g, "P1")
    .replace(/\bppm\b/g, "ppm")
    .replace(/\bhz\b/g, "Hz")
    .replace(/\bdeg\b/g, "deg")
    .replace(/\bnmr\b/gi, "NMR")
    .replace(/\bfid\b/gi, "FID")
    .replace(/\bsmiles\b/gi, "SMILES")
    .replace(/^\w/, (c) => c.toUpperCase())
}

type Group = {
  id: string
  title: string
  picks: { key: string; label?: string }[]
}

/** Group definitions matching the industry-standard NMR Processing Parameters
 * dialog panes. Keys not picked by any group flow into "Other parameters". */
const GROUPS: Group[] = [
  {
    id: "spectrum",
    title: "Spectrum acquisition",
    picks: [
      { key: "zero_fill_factor" },
      { key: "line_broadening_hz" },
      { key: "apodization_mode" },
      { key: "vertical_gain" },
      { key: "display_mode" },
      { key: "mask_solvent_regions" },
    ],
  },
  {
    id: "phase",
    title: "Phase correction",
    picks: [
      { key: "phase_mode" },
      { key: "auto_phase" },
      { key: "automatic_phase_correction" },
      { key: "phase_p0", label: "Phase P0 (deg)" },
      { key: "phase_p1", label: "Phase P1 (deg)" },
    ],
  },
  {
    id: "baseline",
    title: "Baseline correction",
    picks: [
      { key: "baseline_correction" },
      { key: "baseline_order" },
      { key: "baseline_lock" },
      { key: "auto_baseline" },
      { key: "automatic_baseline_correction" },
    ],
  },
  {
    id: "fid",
    title: "FID / digital-filter corrections",
    picks: [
      { key: "apply_group_delay" },
      { key: "group_delay_correction_applied" },
      { key: "digital_filter_correction_status" },
      { key: "selected_preset" },
      { key: "peak_sensitivity" },
    ],
  },
]

type RenderedRow = { key: string; label: string; value: string }

function rowsForGroup(group: Group, source: Record<string, unknown>): RenderedRow[] {
  const rows: RenderedRow[] = []
  for (const pick of group.picks) {
    if (pick.key in source) {
      rows.push({
        key: pick.key,
        label: pick.label ?? humanizeLabel(pick.key),
        value: formatValue(source[pick.key] as FormattableValue),
      })
    }
  }
  return rows
}

function unconsumedKeys(source: Record<string, unknown>): string[] {
  const consumed = new Set<string>(GROUPS.flatMap((g) => g.picks.map((p) => p.key)))
  return Object.keys(source).filter((k) => !consumed.has(k))
}

/**
 * The Raw FID process response packs all processing knobs into a *flat* dict
 * under ``processing_parameters`` AND a nested ``processing_recipe`` /
 * ``phase_settings`` / ``baseline_correction`` block. We flatten the nested
 * fields so each appears in its natural group, then any leftover keys land
 * in the "Other parameters" group at the bottom.
 */
function flattenProcessingParameters(raw: Record<string, unknown>): Record<string, unknown> {
  const flat: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(raw)) {
    if (key === "processing_parameters" && isRecord(value)) {
      Object.assign(flat, value)
      continue
    }
    if (key === "phase_settings" && isRecord(value)) {
      Object.assign(flat, value)
      continue
    }
    if (key === "baseline_correction" && isRecord(value)) {
      // The dict's own primitives become baseline_* keys; nested keys stay
      // accessible under the original key name.
      for (const [subKey, subValue] of Object.entries(value)) {
        flat[`baseline_${subKey}`] =
          subKey === "mode" || subKey === "order" || subKey === "lock"
            ? subValue
            : subValue
      }
      // Also keep the top-level alias so the row "Baseline correction: X"
      // appears as the group's primary entry.
      flat.baseline_correction =
        (value as Record<string, unknown>).mode ?? (value as Record<string, unknown>).method ?? value
      continue
    }
    flat[key] = value
  }
  return flat
}

/**
 * Friendly flat-dict display, used for acquisition metadata (NS / SW / SFO1
 * / etc). Renders every primitive key/value as a row, hides nested or empty
 * fields. Sister to ProcessingParametersCard.
 */
/**
 * The acquisition fields a chemist reads first — nucleus, field, solvent, pulse
 * programme, and the four numbers that describe the acquisition itself. Lower
 * case because vendor dumps disagree on capitalisation (PULPROG vs pulprog).
 */
const PRIMARY_ACQUISITION_KEYS = new Set([
  "nucleus",
  "solvent",
  "pulprog",
  "pulse_program",
  "sfo1",
  "sfo1_mhz",
  "bf1",
  "field_mhz",
  "td",
  "sw",
  "sw_h",
  "sw_hz",
  "ns",
  "rg",
  "instrument",
  "probe",
])

export function MetadataKeyValueCard({
  payload,
  title,
  field,
  testId,
}: {
  payload: unknown
  title: string
  field: string
  testId?: string
}) {
  if (!isRecord(payload)) return null
  /**
   * Two shapes, because the raw-FID response does not carry this at the top level.
   *
   * Verified against a live /nmr/raw-fid/process response for a real Bruker archive: the
   * acquisition parameters a reviewer wants to audit — PULPROG, SFO1, TD, SW, RG and thirty more —
   * sit under `metadata.raw_upload_provenance`. Reading only the top level meant this card
   * rendered nothing at all on every real raw-FID upload, and rendering nothing is indistinguish-
   * able from "the instrument reported nothing", so there was no sign anything was missing.
   */
  const provenance = isRecord(payload.metadata) && isRecord(payload.metadata.raw_upload_provenance)
    ? payload.metadata.raw_upload_provenance
    : null
  const meta = isRecord(payload[field])
    ? (payload[field] as Record<string, unknown>)
    : provenance && isRecord(provenance[field])
      ? (provenance[field] as Record<string, unknown>)
      : null
  if (!meta) return null
  const allRows = Object.entries(meta)
    .filter(([, v]) => v !== null && v !== undefined && v !== "")
    .map(([k, v]) => ({ key: k, label: humanizeLabel(k), value: formatValue(v as FormattableValue) }))
  if (allRows.length === 0) return null

  /* A vendor dump repeats the same reading under more than one spelling — the
     instrument's own key and the canonical one. Two rows that normalise to the
     same key AND carry the same value are the same reading twice, so only the
     first is kept. Deliberately an exact normalised-key match rather than a
     fuzzy one: merging `sw_hz` into `SW_h` on a value coincidence would hide a
     genuinely different parameter, which is worse than showing one row twice. */
  const seen = new Set<string>()
  const rows = allRows.filter((row) => {
    const fingerprint = `${row.key.toLowerCase().replace(/[^a-z0-9]/g, "")}=${row.value}`
    if (seen.has(fingerprint)) return false
    seen.add(fingerprint)
    return true
  })

  /* ~38 rows arrived fully expanded, which buries the handful anyone reads. The
     fields a chemist checks first lead; the rest stay one disclosure away. */
  const primary = rows.filter((row) => PRIMARY_ACQUISITION_KEYS.has(row.key.toLowerCase()))
  const rest = rows.filter((row) => !PRIMARY_ACQUISITION_KEYS.has(row.key.toLowerCase()))
  const leading = primary.length > 0 ? primary : rows
  const remainder = primary.length > 0 ? rest : []
  return (
    <Card
      className="overflow-hidden rounded-xl py-0"
      style={{ borderTop: "3px solid var(--mt-teal)" }}
      data-testid={testId ?? "metadata-keyvalue-card"}
    >
      <CardContent className="space-y-2 py-3">
        <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
          <Settings2 className="h-3 w-3" aria-hidden />
          {title}
        </p>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-[11px] sm:grid-cols-2">
          {leading.map((row) => (
            <div key={row.key} className="flex justify-between gap-2">
              <dt className="text-muted-foreground">{row.label}</dt>
              <dd className="text-right font-mono font-medium">{row.value}</dd>
            </div>
          ))}
        </dl>
        {remainder.length > 0 ? (
          <details className="group">
            <summary className="cursor-pointer list-none font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground hover:text-foreground">
              {`Show all ${rows.length} acquisition parameters`}
            </summary>
            <dl className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 text-[11px] sm:grid-cols-2">
              {remainder.map((row) => (
                <div key={row.key} className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">{row.label}</dt>
                  <dd className="text-right font-mono font-medium">{row.value}</dd>
                </div>
              ))}
            </dl>
          </details>
        ) : null}
      </CardContent>
    </Card>
  )
}

export function ProcessingParametersCard({ payload }: { payload: unknown }) {
  if (!isRecord(payload)) return null
  const rawParams = isRecord(payload.processing_parameters)
    ? payload.processing_parameters
    : isRecord(payload.parameters)
      ? payload.parameters
      : null
  if (!rawParams) return null
  const params = flattenProcessingParameters(rawParams)
  if (Object.keys(params).length === 0) return null

  const groupRenders = GROUPS.map((g) => ({ group: g, rows: rowsForGroup(g, params) }))
    .filter((r) => r.rows.length > 0)

  const otherKeys = unconsumedKeys(params)
  const otherRows: RenderedRow[] = otherKeys.map((k) => ({
    key: k,
    label: humanizeLabel(k),
    value: formatValue(params[k] as FormattableValue),
  }))

  return (
    <Card
      className="overflow-hidden rounded-xl py-0"
      style={{ borderTop: "3px solid var(--mt-teal)" }}
      data-testid="processing-parameters-card"
    >
      <CardContent className="space-y-4 py-3">
        <p className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
          <Settings2 className="h-3 w-3" aria-hidden />
          Processing parameters
        </p>
        <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
          {groupRenders.map(({ group, rows }) => (
            <div key={group.id} className="space-y-2" data-testid={`processing-group-${group.id}`}>
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.16em]"
                style={{ color: "var(--mt-teal-ink)" }}
              >
                {group.title}
              </p>
              <dl className="space-y-1 text-[11px]">
                {rows.map((row) => (
                  <div key={row.key} className="flex justify-between gap-2">
                    <dt className="text-muted-foreground">{row.label}</dt>
                    <dd className="text-right font-mono font-medium">{row.value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
          {otherRows.length > 0 ? (
            <div className="space-y-2 sm:col-span-2" data-testid="processing-group-other">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.16em]"
                style={{ color: "var(--muted-foreground)" }}
              >
                Other parameters
              </p>
              <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-[11px] sm:grid-cols-2">
                {otherRows.map((row) => (
                  <div key={row.key} className="flex justify-between gap-2">
                    <dt className="text-muted-foreground">{row.label}</dt>
                    <dd className="text-right font-mono font-medium">{row.value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  )
}
