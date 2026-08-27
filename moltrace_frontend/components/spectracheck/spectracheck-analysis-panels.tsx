"use client"

import type { ReactNode } from "react"

import { GsdIntegrationPanel } from "@/components/spectracheck/gsd-integration-panel"
import { GsdJCouplingPanel } from "@/components/spectracheck/gsd-jcoupling-panel"
import { GsdMultipletPanel } from "@/components/spectracheck/gsd-multiplet-panel"
import { GsdResultsPanel, type SpectrumGSDAnalyzeResult } from "@/components/spectracheck/gsd-analysis-ui"
import { ReferencesPanel } from "@/components/spectracheck/spectracheck-evidence-panels"
import { ShiftPredictionPanel } from "@/components/spectracheck/shift-prediction-panel"
import { SpectrumRetrievePanel } from "@/components/spectracheck/spectrum-retrieve-panel"

/**
 * The analysis tail both SpectraCheck upload tabs render below their results.
 *
 * Seven panels were duplicated verbatim across the Raw FID and Processed
 * sections with no shared component between them, which is precisely why the
 * two tabs drifted: the same concepts arrived in different orders, under
 * different labels, with different test ids.
 *
 * ORDER IS THE POINT, and it is enforced here rather than left to each caller:
 *
 *   1. what the run produced   — GSD detection, multiplets, J agreement,
 *                                region integrals, plus any tab-specific
 *                                results passed in via `resultsExtras`
 *   2. reference material      — citations, and the two candidate-derived
 *                                tools, which answer questions about a
 *                                CANDIDATE rather than about this spectrum
 *
 * Commit 181293b established that rule for Raw FID after the citation list was
 * found closing the evidence composite a third of the way down the page,
 * landing between two sets of numbers a reader was working through. Processed
 * then broke it again from the other end, rendering a spectrum-derived
 * reasoning panel *below* the reference material. Passing that panel through
 * `resultsExtras` puts it back where it belongs and makes the inversion
 * unrepresentable.
 */
export type SpectraCheckAnalysisPanelsProps = {
  gsdResult: SpectrumGSDAnalyzeResult | null
  /** Same ppm + intensity trace the SpectrumViewer renders. */
  trace: { x: number[]; y: number[] } | null
  nucleus: "1H" | "13C"
  solvent: string
  fieldMhz: number
  candidatesText: string
  sampleId: string
  compoundClass?: string
  displayPayload: unknown
  /** Prefix for panel test ids, e.g. "raw-fid" or "processed". */
  testIdPrefix: string
  /**
   * Tab-specific panels that are still RESULTS of the run — rendered inside
   * group 1 so they cannot drift below the reference material.
   */
  resultsExtras?: ReactNode
}

export function SpectraCheckAnalysisPanels({
  gsdResult,
  trace,
  nucleus,
  solvent,
  fieldMhz,
  candidatesText,
  sampleId,
  compoundClass,
  displayPayload,
  testIdPrefix,
  resultsExtras,
}: SpectraCheckAnalysisPanelsProps) {
  return (
    <>
      {/* ── What the run produced ─────────────────────────────────────── */}
      <GsdResultsPanel result={gsdResult} testId={`${testIdPrefix}-gsd-results-surface`} />

      {/* Chained off the GSD result: peaks above S/N > 3 go to first-order and
          complex multiplet detection. */}
      <GsdMultipletPanel gsdResult={gsdResult} testId={`${testIdPrefix}-multiplet-results-surface`} />

      {/* Scores candidate SMILES against the observed J couplings recovered by
          the multiplet pass. Shares the multiplet cache, so that request fires
          once for both panels. */}
      <GsdJCouplingPanel
        gsdResult={gsdResult}
        candidatesText={candidatesText}
        sampleId={sampleId}
        compoundClass={compoundClass}
        testId={`${testIdPrefix}-jcoupling-results-surface`}
      />

      {/* Integrates each detected multiplet range on the displayed trace.
          Without a structure these are RATIOS, not proton counts — the panel
          labels them accordingly. */}
      <GsdIntegrationPanel
        gsdResult={gsdResult}
        trace={trace}
        nucleus={nucleus}
        solvent={solvent}
        fieldMhz={fieldMhz}
        testId={`${testIdPrefix}-integration-results-surface`}
      />

      {resultsExtras}

      {/* ── Reference material ────────────────────────────────────────────
          Everything below documents or extends the analysis rather than being
          a result of it. The two candidate tools self-gate on the candidate
          list and stay empty until one is entered. */}
      {displayPayload != null ? <ReferencesPanel payload={displayPayload} /> : null}

      <ShiftPredictionPanel
        candidatesText={candidatesText}
        testId={`${testIdPrefix}-shift-prediction-surface`}
      />

      <SpectrumRetrievePanel
        candidatesText={candidatesText}
        testId={`${testIdPrefix}-spectrum-retrieve-surface`}
      />
    </>
  )
}
