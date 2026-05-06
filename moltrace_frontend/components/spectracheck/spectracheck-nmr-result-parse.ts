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
        if (yArr && yArr.length === xArr.length) return { x: xArr, y: yArr }
      }
    }
    return null
  }

  const direct = tryPair(payload)
  if (direct) return direct

  if ("spectrum" in payload && isRecord(payload.spectrum)) {
    const s = tryPair(payload.spectrum)
    if (s) return s
  }
  if ("processed_spectrum" in payload && isRecord(payload.processed_spectrum)) {
    const s = tryPair(payload.processed_spectrum)
    if (s) return s
  }
  if ("plot" in payload && isRecord(payload.plot)) {
    const s = tryPair(payload.plot)
    if (s) return s
  }
  return null
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
    const ppm = Number(p.ppm ?? p.shift ?? p.x)
    if (!Number.isFinite(ppm)) continue
    const intensity = p.intensity != null ? Number(p.intensity) : p.height != null ? Number(p.height) : undefined
    const label = p.label != null ? String(p.label) : p.assignment != null ? String(p.assignment) : undefined
    out.push({
      ppm,
      intensity: intensity != null && Number.isFinite(intensity) ? intensity : undefined,
      label,
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
