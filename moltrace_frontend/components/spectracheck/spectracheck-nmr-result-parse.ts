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

/**
 * `notes` is `list[str]` on every backend model that carries it, and `string[]`
 * in the generated schema — never a bare string. Accepting only the string
 * shape meant this returned null for every real payload and the Details card's
 * Notes block could not render at all. `extractWarnings` above already read
 * both shapes; this one had simply not been updated to match the contract.
 *
 * Both call sites render the result into a single `<p>`, so a list is joined
 * rather than returned as an array — keeping the shape the consumers expect.
 */
export function extractNotes(payload: unknown): string | null {
  if (!isRecord(payload)) return null
  const n = payload.notes ?? payload.note ?? payload.message
  if (Array.isArray(n)) {
    const parts = n.map((x) => String(x).trim()).filter((x) => x.length > 0)
    return parts.length > 0 ? parts.join(" ") : null
  }
  if (typeof n === "string" && n.trim()) return n
  return null
}

/**
 * Archive facts for the Raw FID results header.
 *
 * These three tiles were reading top-level keys — `raw_file_sha256`, `sha256`,
 * `checksum_sha256`, `spectral_width_hz`, `spectral_width`, `sw`,
 * `time_domain_points`, `td`, `np` — that the response models FORBID.
 * `SpectrumPreviewReport` is `extra="forbid"`, and none of those names is one
 * of its fields, so no such key could ever appear and all three tiles were
 * permanently blank.
 *
 * The values live nested, under the shapes the backend actually declares:
 *   sha  -> processing_metadata.raw_upload_provenance.sha256
 *   sw   -> processing_metadata.acquisition_parameters.sw_hz
 *   td   -> processing_metadata.acquisition_parameters.fid_points_after_group_delay
 *
 * Legacy top-level and `metadata.*` spellings are still accepted, matching the
 * both-shapes pattern `extractRawArchiveId` already uses in this module.
 */
export type RawFidArchiveFacts = {
  sha: string | null
  sweepWidthHz: number | null
  fidPoints: number | null
}

function firstString(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim()
  }
  return null
}

function firstFinite(...values: unknown[]): number | null {
  for (const value of values) {
    const n = typeof value === "string" ? Number(value) : value
    if (typeof n === "number" && Number.isFinite(n)) return n
  }
  return null
}

export function extractRawFidArchiveFacts(payload: unknown): RawFidArchiveFacts {
  if (!isRecord(payload)) return { sha: null, sweepWidthHz: null, fidPoints: null }
  const meta = isRecord(payload.metadata) ? payload.metadata : null
  const pm = isRecord(payload.processing_metadata) ? payload.processing_metadata : null
  const provenance = pm && isRecord(pm.raw_upload_provenance) ? pm.raw_upload_provenance : null
  const acq = pm && isRecord(pm.acquisition_parameters) ? pm.acquisition_parameters : null

  return {
    sha: firstString(
      provenance?.sha256,
      payload.raw_sha256,
      payload.content_sha256,
      meta?.sha256,
    ),
    sweepWidthHz: firstFinite(acq?.sw_hz, meta?.sw_hz, payload.sw_hz),
    fidPoints: firstFinite(
      acq?.fid_points_after_group_delay,
      acq?.fft_size,
      meta?.fid_points,
      payload.point_count,
    ),
  }
}

/** Filename the response itself reports, across the shapes it can arrive in. */
export function payloadFilename(payload: unknown): string | null {
  if (!isRecord(payload)) return null
  const metadata = isRecord(payload.metadata) ? payload.metadata : null
  const values = [
    payload.filename,
    payload.file_name,
    payload.name,
    metadata?.filename,
    metadata?.file_name,
    metadata?.name,
  ]
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim()
  }
  return null
}

/**
 * What to CALL the dataset currently on screen.
 *
 * The payload wins over the file input, and that order is the whole point. The
 * two disagree more often than it looks: the raw FID tab has a batch queue, a
 * separately selected file, and independent preview/process payloads, so
 * picking a new archive — or activating a different queue row — leaves
 * `selectedFileName` describing something other than the results being
 * displayed. Both the full-screen subtitle and the cross-tab handoff read that
 * name, so a mismatch does not just mislabel a header, it can carry the wrong
 * provenance into another tab.
 *
 * The selection is still the right answer before anything has run, which is
 * why it remains the fallback rather than being dropped.
 */
export function displayedDatasetName(
  payload: unknown,
  selectedFileName: string | null | undefined,
): string | null {
  const fromPayload = payloadFilename(payload)
  if (fromPayload) return fromPayload
  const selected = selectedFileName?.trim()
  return selected ? selected : null
}
