/**
 * Display labels for SpectraCheck's stored file-kind / session-role /
 * import-target values, plus the workflow-template input keys.
 *
 * These maps affect ONLY what a scientist reads. The stored values and the
 * request keys they map from are unchanged — never substitute a label where a
 * value is sent or read.
 */

import { humanizeField } from "@/lib/ui/status"

export const FILE_KIND_LABELS: Record<string, string> = {
  processed_nmr: "Processed NMR spectrum",
  raw_fid: "Raw FID",
  nmr2d_peak_table: "2D NMR peak table",
  dept_apt_peak_table: "DEPT / APT peak table",
  ms_peak_table: "MS peak table",
  msms_spectrum: "MS/MS spectrum",
  ms_raw: "Raw MS data",
  lcms_mzml: "LC-MS (mzML)",
  lcms_mzxml: "LC-MS (mzXML)",
  lcms_raw: "Raw LC-MS data",
  lcms_peak_table: "LC-MS peak table",
  spectrum_table: "Spectrum table",
  spectrum_jcamp: "Spectrum (JCAMP-DX)",
  spectrum_vendor: "Spectrum (vendor format)",
  spectrum_archive: "Spectrum archive",
  report: "Report",
  other: "Other",
}

export const SESSION_ROLE_LABELS: Record<string, string> = {
  processed_1h: "Processed 1H",
  processed_13c: "Processed 13C",
  raw_fid_1h: "Raw FID (1H)",
  raw_fid_13c: "Raw FID (13C)",
  nmr2d: "2D NMR",
  dept_apt: "DEPT / APT",
  ms1: "MS1",
  msms: "MS/MS",
  lcms: "LC-MS",
  spectrum_reference: "Reference spectrum",
  report_source: "Report source",
  other: "Other",
}

export const CONNECTOR_TARGET_LABELS: Record<string, string> = {
  processed_nmr: "Processed NMR spectrum",
  raw_fid: "Raw FID",
  nmr2d: "2D NMR",
  dept_apt: "DEPT / APT",
  msms: "MS/MS",
  ms_raw: "Raw MS data",
  lcms: "LC-MS",
  lcms_raw: "Raw LC-MS data",
  spectrum_file: "Spectrum file",
}

/** Stored artifact types → the label a scientist reads in artifact tables. */
export const ARTIFACT_TYPE_LABELS: Record<string, string> = {
  spectrum_preview: "Spectrum preview",
  processed_spectrum: "Processed spectrum",
  peak_table: "Peak table",
  nmr_metadata: "NMR metadata",
  nmr2d_peak_table: "2D NMR peak table",
  dept_apt: "DEPT / APT",
  dept_apt_peak_table: "DEPT / APT peak table",
  msms_annotation: "MS/MS annotation",
  lcms_feature_table: "LC-MS feature table",
  unified_evidence: "Unified evidence",
  report_json: "Report data",
  report_html: "Report document",
  other: "Other",
}

/** Workflow-template input keys → the label a scientist reads on the field. */
export const WORKFLOW_INPUT_LABELS: Record<string, string> = {
  session_id: "Session ID",
  sample_id: "Sample ID",
  solvent: "Solvent",
  candidates_text: "Candidate structures",
  observed_proton_text: "Observed 1H peaks",
  observed_carbon13_text: "Observed 13C peaks",
  file_ids: "Session files",
  observed_mz: "Observed m/z",
  adduct: "Adduct",
  msms_peak_list_text: "MS/MS peak list",
  lcms_file_id: "LC-MS data file",
  blank_file_id: "Blank reference file",
  include_report_draft: "Include a report draft",
}

/** Fall back to a spaced, sentence-cased form for values without a mapping. */
export function humanizeStoredValue(value: string): string {
  const trimmed = value.trim()
  if (!trimmed) return "—"
  const spaced = trimmed.replace(/_/g, " ")
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export function fileKindLabel(value: string): string {
  return FILE_KIND_LABELS[value] ?? humanizeStoredValue(value)
}

export function sessionRoleLabel(value: string): string {
  return SESSION_ROLE_LABELS[value] ?? humanizeStoredValue(value)
}

export function workflowInputLabel(key: string): string {
  return WORKFLOW_INPUT_LABELS[key] ?? humanizeStoredValue(key)
}

export function artifactTypeLabel(value: string): string {
  const key = value.trim().toLowerCase()
  return ARTIFACT_TYPE_LABELS[key] ?? humanizeStoredValue(value)
}

/**
 * Humanize a stored token only when it still looks like one (snake_case, no
 * spaces). Fields such as quality-control readiness can arrive either as a
 * stored token or as a sentence already written for a reader — leave the
 * latter exactly as-is rather than re-casing it.
 */
export function humanizeTokenForDisplay(value: string | null | undefined): string {
  const trimmed = typeof value === "string" ? value.trim() : ""
  if (!trimmed) return "—"
  if (/\s/.test(trimmed) || !trimmed.includes("_")) return trimmed
  return humanizeField(trimmed)
}
