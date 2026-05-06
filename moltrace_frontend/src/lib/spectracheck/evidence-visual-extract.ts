/**
 * Read-only helpers to detect visualizable payloads inside EvidenceItem.response (no mutation).
 */

import type { ChromatogramFeature, ChromatogramTrace } from "@/components/science/ChromatogramViewer"
import type {
  MsmsMirrorFragmentMatch,
  MsmsMirrorObservedPeak,
  MsmsMirrorReferencePeak,
} from "@/components/science/MsmsMirrorPlot"
import type { FragmentTreeEdge, FragmentTreeNode } from "@/src/components/science/FragmentTreeViewer"
import type { Nmr2DPeak } from "@/src/components/science/Nmr2DViewer"
import {
  extractPeaksFromPayload,
  extractSpectrumXY,
  isRecord,
} from "@/components/spectracheck/spectracheck-nmr-result-parse"

function readStr(v: unknown): string | null {
  if (typeof v === "string") return v
  if (typeof v === "number") return String(v)
  return null
}

function coerceNumArray(v: unknown): number[] | null {
  if (!Array.isArray(v)) return null
  const out = v.map((x) => Number(x)).filter((n) => Number.isFinite(n))
  return out.length === v.length ? out : null
}

/** Nested JSON typically stored on queued artifact evidence. */
export function getEvidenceVisualPayload(response: unknown): unknown {
  if (!isRecord(response)) return response
  return (
    response.artifact_json ??
    response.payload ??
    response.data ??
    response.content ??
    response.result ??
    response
  )
}

export function extractArtifactIdFromEvidence(response: unknown): string | null {
  if (!isRecord(response)) return null
  const id = response.artifact_id ?? response.artifactId
  return typeof id === "string" && id.trim() ? id.trim() : null
}

export function hasSpectrumXyPreview(payload: unknown): boolean {
  const xy = extractSpectrumXY(payload ?? {})
  return xy != null && xy.x.length > 0 && xy.y.length > 0
}

function coerceMzIntensityPeaks(raw: unknown): MsmsMirrorObservedPeak[] {
  if (!Array.isArray(raw)) return []
  const out: MsmsMirrorObservedPeak[] = []
  for (const p of raw) {
    if (!isRecord(p)) continue
    const mz = Number(p.mz ?? p.m_z ?? p.mass)
    const intensity = Number(p.intensity ?? p.i ?? p.rel_abundance ?? p.relative_intensity ?? p.height)
    if (!Number.isFinite(mz)) continue
    out.push({
      mz,
      intensity: Number.isFinite(intensity) ? intensity : 1,
      label: readStr(p.label) ?? undefined,
    })
  }
  return out
}

export type MsmsMirrorBundle = {
  observedPeaks: MsmsMirrorObservedPeak[]
  referencePeaks: MsmsMirrorReferencePeak[]
  fragmentMatches: MsmsMirrorFragmentMatch[]
  precursorMz?: number
  adduct?: string
  toleranceDa?: number
  tolerancePpm?: number
}

export function extractMsmsMirrorBundleForEvidence(json: unknown): MsmsMirrorBundle | null {
  if (!isRecord(json)) return null
  const root = isRecord(json.msms) ? json.msms : isRecord(json.annotation) ? json.annotation : json

  const obsRaw =
    root.observed_peaks ??
    root.experimental_peaks ??
    root.peaks_observed ??
    root.observed ??
    json.observed_peaks
  const refRaw =
    root.reference_peaks ??
    root.theoretical_peaks ??
    root.synthetic_peaks ??
    json.reference_peaks

  let observedPeaks = coerceMzIntensityPeaks(obsRaw)
  if (observedPeaks.length === 0) {
    observedPeaks = coerceMzIntensityPeaks(json.peaks)
  }

  const referencePeaks: MsmsMirrorReferencePeak[] = coerceMzIntensityPeaks(refRaw).map((p) => ({
    mz: p.mz,
    intensity: p.intensity,
    label: p.label,
  }))

  const fragRaw =
    root.fragment_matches ??
    root.annotations ??
    root.matches ??
    json.fragment_matches
  const fragmentMatches: MsmsMirrorFragmentMatch[] = []
  if (Array.isArray(fragRaw)) {
    for (const m of fragRaw.filter(isRecord)) {
      const sc = Number(m.score)
      fragmentMatches.push({
        observed_mz: Number(m.observed_mz ?? m.obs_mz ?? m.mz),
        theoretical_mz: Number(m.theoretical_mz ?? m.theo_mz ?? m.expected_mz),
        label: readStr(m.label ?? m.ion ?? m.formula) ?? undefined,
        score: Number.isFinite(sc) ? sc : undefined,
      })
    }
  }

  const precursorMz = Number(
    root.precursor_mz ?? root.precursor_m_z ?? json.precursor_mz ?? json.precursorMz,
  )
  const adduct = readStr(root.adduct ?? json.adduct) ?? undefined
  const toleranceDa = Number(root.tolerance_da ?? root.mass_tolerance_da)
  const tolerancePpm = Number(root.tolerance_ppm ?? root.msms_ppm_tolerance ?? json.msms_ppm_tolerance)

  if (observedPeaks.length === 0 && referencePeaks.length === 0 && fragmentMatches.length === 0) {
    return null
  }

  return {
    observedPeaks,
    referencePeaks,
    fragmentMatches,
    precursorMz: Number.isFinite(precursorMz) ? precursorMz : undefined,
    adduct,
    toleranceDa: Number.isFinite(toleranceDa) ? toleranceDa : undefined,
    tolerancePpm: Number.isFinite(tolerancePpm) ? tolerancePpm : undefined,
  }
}

export function extractChromatogramTracesForEvidence(json: unknown): ChromatogramTrace[] {
  if (!isRecord(json)) return []
  const candidates: unknown[] = [
    json.chromatogram_traces,
    json.traces,
    json.chromatograms,
    json.xics,
    isRecord(json.lcms) ? json.lcms.traces : undefined,
    isRecord(json.feature_summary) ? json.feature_summary.traces : undefined,
  ].filter(Boolean) as unknown[]

  for (const c of candidates) {
    if (!Array.isArray(c) || c.length === 0) continue
    const traces: ChromatogramTrace[] = []
    for (const item of c) {
      if (!isRecord(item)) continue
      const name = String(item.name ?? item.label ?? item.id ?? "trace")
      const rt = coerceNumArray(item.rt ?? item.time ?? item.retention_time ?? item.rt_min)
      const intensity = coerceNumArray(item.intensity ?? item.i ?? item.y ?? item.intensities)
      if (!rt || !intensity || rt.length === 0 || rt.length !== intensity.length) continue
      const typeRaw = item.type ?? item.trace_type
      const type =
        typeof typeRaw === "string" && ["TIC", "BPC", "XIC", "EIC"].includes(typeRaw.toUpperCase())
          ? (typeRaw.toUpperCase() as ChromatogramTrace["type"])
          : undefined
      const mzNum = Number(item.mz ?? item.m_z ?? item.precursor_mz)
      traces.push({
        name,
        rt,
        intensity,
        type,
        mz: Number.isFinite(mzNum) ? mzNum : undefined,
      })
    }
    if (traces.length > 0) return traces
  }
  return []
}

export function extractChromatogramFeaturesForEvidence(json: unknown): ChromatogramFeature[] {
  if (!isRecord(json)) return []
  const raw =
    json.features ??
    json.feature_list ??
    json.lcms_features ??
    (isRecord(json.lcms) ? json.lcms.features : undefined)
  if (!Array.isArray(raw)) return []
  const out: ChromatogramFeature[] = []
  for (const f of raw) {
    if (!isRecord(f)) continue
    const rtStart = Number(f.rt_start ?? f.rtStart ?? f.start_rt)
    const rtEnd = Number(f.rt_end ?? f.rtEnd ?? f.end_rt)
    const rtApex = Number(f.rt_apex ?? f.rtApex ?? f.apex_rt)
    const mzNum = Number(f.mz ?? f.m_z ?? f.precursor_mz)
    out.push({
      id: readStr(f.id) ?? undefined,
      mz: Number.isFinite(mzNum) ? mzNum : undefined,
      rtStart: Number.isFinite(rtStart) ? rtStart : undefined,
      rtEnd: Number.isFinite(rtEnd) ? rtEnd : undefined,
      rtApex: Number.isFinite(rtApex) ? rtApex : undefined,
      label: readStr(f.label ?? f.name) ?? undefined,
      purityLabel: readStr(f.purity_label ?? f.purity) ?? undefined,
    })
  }
  return out
}

function parsePeakRecord2d(p: Record<string, unknown>): Nmr2DPeak | null {
  const f2 = Number(p.f2_ppm ?? p.f2 ?? p.H_ppm ?? p.h_ppm)
  const f1 = Number(p.f1_ppm ?? p.f1 ?? p.C_ppm ?? p.c_ppm)
  if (!Number.isFinite(f2) || !Number.isFinite(f1)) return null
  const intensity = p.intensity != null ? Number(p.intensity) : undefined
  return {
    f2_ppm: f2,
    f1_ppm: f1,
    intensity: intensity != null && Number.isFinite(intensity) ? intensity : undefined,
    assignment: readStr(p.assignment) ?? undefined,
    label: readStr(p.label) ?? undefined,
    status: readStr(p.status) ?? undefined,
  }
}

export function extractNmr2dPeaksForEvidence(payload: unknown): Nmr2DPeak[] {
  if (!isRecord(payload)) return []
  const keys = [
    payload.peaks_2d,
    payload.peaks2d,
    payload.nmr2d_peaks,
    payload.cross_peaks,
    payload.peaks,
    isRecord(payload.nmr2d) ? payload.nmr2d.peaks : undefined,
  ].filter(Boolean) as unknown[]
  for (const raw of keys) {
    if (!Array.isArray(raw) || raw.length === 0) continue
    const out: Nmr2DPeak[] = []
    for (const p of raw) {
      if (!isRecord(p)) continue
      const row = parsePeakRecord2d(p)
      if (row) out.push(row)
    }
    if (out.length > 0) return out
  }
  return []
}

function parseFragmentNode(n: Record<string, unknown>): FragmentTreeNode | null {
  const id = readStr(n.id ?? n.node_id)
  if (!id) return null
  const mz = n.mz != null ? Number(n.mz) : undefined
  return {
    id,
    mz: mz != null && Number.isFinite(mz) ? mz : undefined,
    label: readStr(n.label ?? n.name) ?? undefined,
    intensity: n.intensity != null && Number.isFinite(Number(n.intensity)) ? Number(n.intensity) : undefined,
    status: readStr(n.status) ?? undefined,
  }
}

function parseFragmentEdge(e: Record<string, unknown>): FragmentTreeEdge | null {
  const source = readStr(e.source ?? e.from ?? e.parent)
  const target = readStr(e.target ?? e.to ?? e.child)
  if (!source || !target) return null
  const dmz = e.delta_mz != null ? Number(e.delta_mz) : undefined
  return {
    source,
    target,
    loss: readStr(e.loss ?? e.neutral_loss) ?? undefined,
    delta_mz: dmz != null && Number.isFinite(dmz) ? dmz : undefined,
    supported: typeof e.supported === "boolean" ? e.supported : undefined,
    contradiction: typeof e.contradiction === "boolean" ? e.contradiction : undefined,
  }
}

export function extractFragmentationGraphForEvidence(payload: unknown): {
  nodes: FragmentTreeNode[]
  edges: FragmentTreeEdge[]
} {
  const nodes: FragmentTreeNode[] = []
  const edges: FragmentTreeEdge[] = []
  if (!isRecord(payload)) return { nodes, edges }

  const nRaw =
    payload.fragmentation_nodes ??
    payload.fragment_nodes ??
    payload.tree_nodes ??
    payload.nodes
  if (Array.isArray(nRaw)) {
    for (const x of nRaw) {
      if (!isRecord(x)) continue
      const n = parseFragmentNode(x)
      if (n) nodes.push(n)
    }
  }

  const eRaw =
    payload.fragmentation_edges ??
    payload.fragment_edges ??
    payload.tree_edges ??
    payload.edges
  if (Array.isArray(eRaw)) {
    for (const x of eRaw) {
      if (!isRecord(x)) continue
      const e = parseFragmentEdge(x)
      if (e) edges.push(e)
    }
  }

  return { nodes, edges }
}

export function peaks1DFromEvidencePayload(payload: unknown) {
  const raw = extractPeaksFromPayload(payload ?? {})
  return raw.map((p) => ({
    x: p.ppm,
    y: p.intensity,
    label: p.label,
  }))
}
