/**
 * The SpectraCheck section directory — the workspace's stage/section map as PLAIN DATA.
 *
 * Lives outside the workspace on purpose: the workspace is a ~4k-line client monolith loaded
 * through next/dynamic, and the command palette in the app shell needs this list to offer
 * "go to section" commands. Importing it from the workspace would pull the whole workspace chunk
 * into the shell bundle; importing it from here costs nothing but the data.
 *
 * `?section=<value>` on /spectracheck is the public deep-link contract for these values — the
 * workspace applies it on load and on change, the palette produces it, and a shared link lands
 * the reader on the section it names. Renaming a `value` therefore breaks saved links: add, don't
 * rename.
 */
import type { WorkspaceStageGroup } from "@/components/app/workspace-stage-nav"

export const SPECTRACHECK_NAV: WorkspaceStageGroup[] = [
  // Overview leads because it is where the workspace actually opens (`defaultTab`), and a nav
  // whose first item is not the one highlighted on arrival reads as though something was skipped.
  {
    id: "start",
    label: "Overview",
    sections: [
      { value: "tab-overview", label: "Overview", desc: "Summary of available evidence, connection status, and next recommended actions." },
      { value: "tab-workflow", label: "Workflow", desc: "A predefined sequence of analysis, QC, evidence, unified confidence, and report steps. Reproduces the session." },
    ],
  },
  {
    id: "session",
    label: "Session",
    sections: [
      {
        value: "tab-session",
        label: "Session",
        desc: "Choose the project and sample this work belongs to, load or save a session, and link supporting knowledge records.",
      },
    ],
  },
  {
    id: "inputs",
    label: "Evidence Inputs",
    sections: [
      { value: "tab-nmr-text", label: "NMR text + candidates", desc: "Enter candidate structures and literature-style 1H/13C NMR text for quick structure-evidence comparison." },
      { value: "tab-processed", label: "Processed 1H / 13C upload", desc: "CSV, TSV, TXT, or JCAMP-DX — for preview, peak picking, and evidence matching." },
      { value: "tab-raw-fid", label: "Raw FID upload", desc: "Upload raw Bruker or Agilent/Varian FID archives for non-destructive processing. Raw data should remain immutable." },
      { value: "tab-dept-2d", label: "DEPT/APT + 2D NMR", desc: "Use DEPT/APT carbon typing and COSY, HSQC/HMQC, or HMBC correlations as supporting connectivity evidence." },
      { value: "tab-ms-evidence", label: "MS Evidence", desc: "HRMS, formula search, adduct inference, MS/MS, fragmentation, and optional LC-MS feature workflows using shared session inputs." },
    ],
  },
  {
    id: "analysis",
    label: "Analysis",
    sections: [
      { value: "tab-predicted", label: "Predicted NMR matching", desc: "Compare observed NMR evidence against candidate-specific predicted 1H, 13C, and HSQC-style signals." },
      { value: "tab-evidence-queue", label: "Evidence Queue", desc: "Queue session evidence items for triage, review, and unified-evidence preparation." },
      { value: "tab-unified", label: "Unified evidence", desc: "Combine available NMR/MS evidence layers into a transparent candidate confidence summary." },
    ],
  },
  {
    id: "bench",
    label: "Bench",
    sections: [
      {
        value: "tab-bench",
        label: "Evidence Bench",
        desc: "Spectrum, picked peaks, and evidence side by side for every finished dataset, with the processing recipe underneath.",
      },
    ],
  },
  {
    id: "output",
    label: "Outputs",
    sections: [
      { value: "tab-report", label: "Report", desc: "Prepare a reviewer-ready structure elucidation report with evidence, warnings, provenance, and human approval state." },
      { value: "tab-benchmark", label: "Benchmark", desc: "Run the 5-layer SpectraCheck benchmark — peak-level accuracy, structural ranking, explainability, robustness, regulatory evidence." },
    ],
  },
  {
    id: "developer",
    label: "Developer",
    sections: [
      { value: "tab-dev-json", label: "Developer JSON", desc: "Raw results for troubleshooting, validation, and data-shape inspection." },
    ],
  },
]

/** Every section value with its display label and stage, flattened for pickers. */
export const SPECTRACHECK_SECTIONS: Array<{ value: string; label: string; stage: string }> =
  SPECTRACHECK_NAV.flatMap((group) =>
    group.sections.map((section) => ({ value: section.value, label: section.label, stage: group.label })),
  )

const SECTION_VALUES = new Set(SPECTRACHECK_SECTIONS.map((section) => section.value))

/** True for a value the workspace can actually show — the ?section= validator. */
export function isSpectraCheckSection(value: string | null | undefined): value is string {
  return value != null && SECTION_VALUES.has(value)
}
