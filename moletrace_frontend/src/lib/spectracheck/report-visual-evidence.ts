/**
 * Selected-queue visual evidence summaries for report compose (references only; no plot binaries).
 */

import { isRecord } from "@/components/spectracheck/spectracheck-nmr-result-parse"
import {
  extractArtifactIdFromEvidence,
  extractChromatogramTracesForEvidence,
  extractFragmentationGraphForEvidence,
  extractMsmsMirrorBundleForEvidence,
  extractNmr2dPeaksForEvidence,
  getEvidenceVisualPayload,
  hasSpectrumXyPreview,
} from "@/src/lib/spectracheck/evidence-visual-extract"
import type { EvidenceItem } from "@/src/lib/spectracheck/evidence-types"

function readStr(v: unknown): string | null {
  if (typeof v === "string") return v
  if (typeof v === "number") return String(v)
  return null
}

function extractJobIdFromEvidence(response: unknown): string | null {
  if (!isRecord(response)) return null
  const top = readStr(response.job_id ?? response.analysis_job_id ?? response.jobId)
  if (top) return top
  const payload = getEvidenceVisualPayload(response)
  if (!isRecord(payload)) return null
  return readStr(payload.job_id ?? payload.analysis_job_id ?? payload.jobId)
}

function extractArtifactTypeFromEvidence(response: unknown): string | null {
  if (!isRecord(response)) return null
  const t = readStr(response.artifact_type ?? response.type ?? response.kind)
  if (t) return t
  const payload = getEvidenceVisualPayload(response)
  if (!isRecord(payload)) return null
  return readStr(payload.artifact_type ?? payload.type ?? payload.kind)
}

function extractArtifactSha256(response: unknown): string | null {
  if (!isRecord(response)) return null
  const direct = readStr(response.sha256 ?? response.file_sha256 ?? response.checksum_sha256)
  if (direct?.trim()) return direct.trim()
  const payload = getEvidenceVisualPayload(response)
  if (!isRecord(payload)) return null
  const h = readStr(payload.sha256 ?? payload.file_sha256 ?? payload.checksum_sha256)
  return h?.trim() || null
}

export type SelectedVisualEvidenceEntry = {
  evidence_item_id: string
  artifact_id: string | null
  artifact_type: string | null
  title: string
  sha256: string | null
  source_file_sha256: string | null
  job_id: string | null
  qc_status: string | null
  visual_reviewed: boolean
  visual_review_comment: string | null
  preview_kinds: string[]
  plot_image_placeholders: string[]
}

const PLACEHOLDER_SUFFIX = "plot_export_placeholder"

function placeholdersForKinds(kinds: string[]): string[] {
  return kinds.map((k) => `${k}_${PLACEHOLDER_SUFFIX}`)
}

/** Analyze one queue item; preview kinds are stable labels for UI + compose metadata (no binaries). */
export function analyzeVisualEvidenceItem(item: EvidenceItem): {
  previewKinds: string[]
} {
  const payload = getEvidenceVisualPayload(item.response)
  const kinds: string[] = []

  if (extractArtifactIdFromEvidence(item.response)) {
    kinds.push("artifact_reference")
  }
  if (hasSpectrumXyPreview(payload)) {
    kinds.push("spectrum_1d")
  }
  const msms = extractMsmsMirrorBundleForEvidence(payload ?? {})
  if (msms != null) {
    kinds.push("msms_mirror")
  }
  if (extractChromatogramTracesForEvidence(payload ?? {}).length > 0) {
    kinds.push("lcms_chromatogram")
  }
  if (extractNmr2dPeaksForEvidence(payload ?? {}).length > 0) {
    kinds.push("nmr_2d_peaks")
  }
  const frag = extractFragmentationGraphForEvidence(payload ?? {})
  if (frag.nodes.length > 0 || frag.edges.length > 0) {
    kinds.push("fragmentation_tree")
  }

  return { previewKinds: [...new Set(kinds)] }
}

export function buildSelectedVisualEvidenceEntries(items: EvidenceItem[]): SelectedVisualEvidenceEntry[] {
  const out: SelectedVisualEvidenceEntry[] = []
  for (const item of items) {
    if (!item.selectedForUnified) continue
    const { previewKinds } = analyzeVisualEvidenceItem(item)
    if (previewKinds.length === 0) continue

    const aid = extractArtifactIdFromEvidence(item.response)
    const atype = extractArtifactTypeFromEvidence(item.response)
    const jobId = extractJobIdFromEvidence(item.response)
    const artifactSha = extractArtifactSha256(item.response) ?? item.provenance?.sha256?.trim() ?? null

    out.push({
      evidence_item_id: item.id,
      artifact_id: aid,
      artifact_type: atype,
      title: item.title,
      sha256: artifactSha,
      source_file_sha256: item.provenance?.sha256?.trim() ?? null,
      job_id: jobId,
      qc_status: item.qcStatus ?? null,
      visual_reviewed: Boolean(item.visualReviewed),
      visual_review_comment: item.visualReviewComment?.trim() || null,
      preview_kinds: previewKinds,
      plot_image_placeholders: placeholdersForKinds(previewKinds),
    })
  }
  return out
}
