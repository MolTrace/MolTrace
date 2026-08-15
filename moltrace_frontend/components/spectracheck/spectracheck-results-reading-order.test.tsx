/**
 * Reading order of a finished raw-FID analysis.
 *
 * The page had reference material interleaved with output: the citation list closed the evidence
 * composite about a third of the way down, and the two candidate tools sat between the integration
 * panels and the detection summary. A chemist reading the numbers their own upload had just
 * produced had to scroll past a bibliography and two structure-prediction tools to reach the rest
 * of them.
 *
 * The distinction the order encodes is what a block is ABOUT. Everything above is a result of the
 * run; the citations document that run, and the two candidate tools answer questions about a
 * CANDIDATE STRUCTURE from a SMILES — they are not derived from this spectrum at all, which is why
 * they self-gate on the candidate list and sit empty until one is entered.
 *
 * Asserted as relative document position rather than by index, so inserting a new panel between
 * any two of these does not fail the test — only moving reference material back above the results
 * does.
 */
import { fireEvent, render, screen } from "@testing-library/react"
import type { ReactElement } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { apiFetch } from "@/lib/api/client"
import { SpectraCheckRawFidSection } from "@/components/spectracheck/spectracheck-raw-fid-section"
import { SpectraCheckEvidenceProvider } from "@/src/lib/spectracheck/useSpectraCheckEvidence"

vi.mock("@/lib/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/client")>("@/lib/api/client")
  return { ...actual, apiFetch: vi.fn() }
})

vi.mock("@/components/science/SpectrumViewer", () => ({
  SpectrumViewer: () => <div data-testid="spectrum-viewer" />,
}))

const apiFetchMock = vi.mocked(apiFetch)

/** A completed process response carrying peaks AND references, so both blocks render. */
function processResponse() {
  const x: number[] = []
  const y: number[] = []
  for (let i = 0; i < 64; i++) {
    x.push(i / 8)
    y.push(i === 30 ? 100 : 1)
  }
  return {
    sample_id: "sample-1",
    vendor_detected: "bruker",
    nucleus: "1H",
    point_count: 64,
    x,
    y,
    peaks: [{ shift_ppm: 3.75 }, { shift_ppm: 1.2 }],
    references: [
      { authors: "Gottlieb H. E.; Kotlyar V.; Nudelman A.", title: "NMR Chemical Shifts of Common Laboratory Solvents as Trace Impurities", source: "J. Org. Chem.", year: 1997 },
    ],
    warnings: [],
    metadata: {},
  }
}

function renderSection(): ReturnType<typeof render> {
  const ui: ReactElement = (
    <SpectraCheckRawFidSection
      sampleId="sample-1"
      onSampleIdChange={() => {}}
      solvent="CDCl3"
      // Both candidate tools return null with no candidate — they are ABOUT a candidate
      // structure, which is the same reason they do not belong among the spectrum results.
      // One is supplied here so they render and their position can be asserted at all.
      candidatesText="CCO"
    />
  )
  return render(<SpectraCheckEvidenceProvider>{ui}</SpectraCheckEvidenceProvider>)
}

/** True when `a` appears before `b` in document order. */
function precedes(a: Element, b: Element): boolean {
  return Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)
}

beforeEach(() => {
  apiFetchMock.mockReset()
})

describe("a finished raw-FID analysis reads results first", () => {
  async function renderFinished() {
    // Only the analysis routes get the process payload. The run-review list below the results
    // fetches on its own and expects an array — answering it with a process response throws.
    apiFetchMock.mockImplementation(async (path: string) =>
      String(path).startsWith("/nmr/raw-fid/") ? (processResponse() as never) : ([] as never),
    )
    renderSection()
    fireEvent.drop(screen.getByRole("button", { name: /Drop raw FID archive/i }), {
      dataTransfer: { files: [new File(["fid"], "a.zip", { type: "application/zip" })], types: ["Files"] },
    })
    fireEvent.click(screen.getByTestId("raw-fid-queue-run-all"))
    expect(await screen.findByText(/Processed FID output/i)).toBeInTheDocument()
  }

  it("puts the picked peaks above the citation list", async () => {
    await renderFinished()
    const peaks = screen.getByTestId("enriched-picked-peaks")
    const references = screen.getByTestId("references-panel")
    expect(precedes(peaks, references)).toBe(true)
  })

  it("puts the citation list below the processing parameters it used to sit above", async () => {
    await renderFinished()
    // The discriminating pair. Asserting only that references follow the picked peaks would pass
    // in the OLD layout too, because the composite that carried them already sat below the peaks.
    // What actually changed is that references now come after the run review and the processing
    // parameters instead of interrupting the page ahead of them.
    expect(
      precedes(screen.getByTestId("processing-parameters-collapsible"), screen.getByTestId("references-panel")),
    ).toBe(true)
  })

  it("puts the candidate tools below the detection summary they used to split off", async () => {
    await renderFinished()
    // Likewise discriminating: the tools were always below the picked peaks, so only their
    // position relative to the LAST result block — the detection summary that used to follow
    // them — distinguishes the new order from the old.
    const detection = screen.getByTestId("raw-fid-legacy-results-surface")
    expect(precedes(detection, screen.getByTestId("raw-fid-shift-prediction-surface"))).toBe(true)
    expect(precedes(detection, screen.getByTestId("raw-fid-spectrum-retrieve-surface"))).toBe(true)
  })

  it("keeps reference material in a stable order among itself", async () => {
    await renderFinished()
    const references = screen.getByTestId("references-panel")
    const shiftPrediction = screen.getByTestId("raw-fid-shift-prediction-surface")
    expect(precedes(references, shiftPrediction)).toBe(true)
    expect(precedes(shiftPrediction, screen.getByTestId("raw-fid-spectrum-retrieve-surface"))).toBe(true)
  })
})
