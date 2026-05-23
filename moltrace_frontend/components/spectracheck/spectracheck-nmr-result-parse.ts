import type { SpectrumOverlays, SpectrumPeakAnnotation } from "@/components/science/SpectrumViewer"

export function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function coerceNumArray(v: unknown): number[] | null {
  if (!Array.isArray(v)) return null
  const out = v.map((x) => Number(x)).filter((n) => Number.isFinite(n))
  return out.length === v.length ? out : null
}

export function extractSpectrumXY(payload: unknown): { x: number[]; y: number[] } | null {
  if (!isRecord(payload)) return null
  const seen = new WeakSet<Record<string, unknown>>()

  const tryPointRows = (rows: unknown) => {
    if (!Array.isArray(rows)) return null
    const x: number[] = []
    const y: number[] = []
    for (const row of rows) {
      if (Array.isArray(row) && row.length >= 2) {
        const xv = Number(row[0])
        const yv = Number(row[1])
        if (!Number.isFinite(xv) || !Number.isFinite(yv)) return null
        x.push(xv)
        y.push(yv)
        continue
      }
      if (!isRecord(row)) return null
      const xv = Number(row.shift_ppm ?? row.ppm ?? row.shift ?? row.delta ?? row.x)
      const yv = Number(row.intensity ?? row.signal ?? row.y ?? row.amplitude ?? row.height ?? row.area)
      if (!Number.isFinite(xv) || !Number.isFinite(yv)) return null
      x.push(xv)
      y.push(yv)
    }
    return x.length > 0 && x.length === y.length ? { x, y } : null
  }

  const tryPair = (r: Record<string, unknown>) => {
    const xk = ["x", "ppm", "ppm_values", "chemical_shifts", "shifts"] as const
    const yk = ["y", "intensity", "intensities", "i", "absorption"] as const
    for (const xKey of xk) {
      if (!(xKey in r)) continue
      const xv = r[xKey]
      const xArr = coerceNumArray(xv)
      if (!xArr) continue
      for (const yKey of yk) {
        if (!(yKey in r)) continue
        const yArr = coerceNumArray(r[yKey])
        if (yArr && xArr.length > 0 && yArr.length === xArr.length) return { x: xArr, y: yArr }
      }
    }
    const rowKeys = ["preview_points", "points", "data", "trace"] as const
    for (const key of rowKeys) {
      if (!(key in r)) continue
      const rows = tryPointRows(r[key])
      if (rows) return rows
    }
    return null
  }

  const scan = (r: Record<string, unknown>, depth = 0): { x: number[]; y: number[] } | null => {
    if (seen.has(r) || depth > 4) return null
    seen.add(r)

    const direct = tryPair(r)
    if (direct) return direct

    const nestedKeys = [
      "spectrum",
      "processed_spectrum",
      "plot",
      "preview",
      "processed_preview",
      "fid_preview",
      "raw_preview",
      "result",
      "payload",
      "response",
      "metadata",
      "original_spectrum_state",
    ] as const

    for (const key of nestedKeys) {
      if (!(key in r) || !isRecord(r[key])) continue
      const nested = scan(r[key], depth + 1)
      if (nested) return nested
    }

    return null
  }

  return scan(payload)
}

export function extractPeaksFromPayload(payload: unknown): SpectrumPeakAnnotation[] {
  if (!isRecord(payload)) return []
  const raw =
    payload.peaks ??
    payload.picked_peaks ??
    payload.peak_list ??
    payload.peak_table ??
    payload.annotations
  if (!Array.isArray(raw)) return []
  const out: SpectrumPeakAnnotation[] = []
  for (const p of raw) {
    if (!isRecord(p)) continue
    const ppm = Number(p.ppm ?? p.shift ?? p.x ?? p.shift_ppm)
    if (!Number.isFinite(ppm)) continue
    const intensity = p.intensity != null ? Number(p.intensity) : p.height != null ? Number(p.height) : undefined
    const label = p.label != null ? String(p.label) : p.assignment != null ? String(p.assignment) : undefined
    // ``category`` flows through unchanged when the backend's enrich_peaks
    // attached one (processed analyze + raw-FID process responses both do).
    // The viewer reads it to color-code markers per category.
    const category = typeof p.category === "string" && p.category.length > 0 ? p.category : undefined
    out.push({
      ppm,
      intensity: intensity != null && Number.isFinite(intensity) ? intensity : undefined,
      label,
      category,
    })
  }
  return out
}

export function extractPredictedOverlay(payload: unknown): SpectrumOverlays | undefined {
  if (!isRecord(payload)) return undefined
  const keys = [
    "predicted_overlay",
    "predicted_spectrum",
    "theoretical_spectrum",
    "overlay_predicted",
  ] as const
  for (const k of keys) {
    if (k in payload) {
      const xy = extractSpectrumXY(payload[k])
      if (xy) return { predicted: { ...xy, label: "Predicted" } }
    }
  }
  if ("overlays" in payload && isRecord(payload.overlays) && "predicted" in payload.overlays) {
    const xy = extractSpectrumXY((payload.overlays as Record<string, unknown>).predicted)
    if (xy) return { predicted: { ...xy, label: "Predicted" } }
  }
  return undefined
}

export function extractNumericSummary(payload: unknown, keys: string[]): number | null {
  if (!isRecord(payload)) return null
  for (const k of keys) {
    if (k in payload) {
      const n = Number((payload as Record<string, unknown>)[k])
      if (Number.isFinite(n)) return n
    }
  }
  return null
}

export function extractStringSummary(payload: unknown, keys: string[]): string | null {
  if (!isRecord(payload)) return null
  for (const k of keys) {
    if (k in payload) {
      const v = (payload as Record<string, unknown>)[k]
      if (typeof v === "string" && v.trim()) return v
    }
  }
  return null
}

export function extractWarnings(payload: unknown): string[] {
  if (!isRecord(payload)) return []
  const w = payload.warnings ?? payload.solvent_warnings ?? payload.impurity_warnings
  if (Array.isArray(w)) return w.map((x) => String(x))
  if (typeof w === "string" && w.trim()) return [w]
  return []
}

export function extractNotes(payload: unknown): string | null {
  if (!isRecord(payload)) return null
  const n = payload.notes ?? payload.note ?? payload.message
  if (typeof n === "string" && n.trim()) return n
  return null
}
