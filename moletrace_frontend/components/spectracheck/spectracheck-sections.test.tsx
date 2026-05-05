import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { SpectrumViewer } from "@/components/science/SpectrumViewer"
import { SpectraCheckProcessedSpectrumSection } from "@/components/spectracheck/spectracheck-processed-spectrum-section"
import { SpectraCheckRawFidSection } from "@/components/spectracheck/spectracheck-raw-fid-section"
describe("SpectraCheck processed / raw sections", () => {
  it("processed section shows title and Preview / Analyze actions", () => {
    render(
      <SpectraCheckProcessedSpectrumSection
        sampleId="t1"
        onSampleIdChange={() => {}}
        solvent="CDCl3"
        candidatesText="A | CCO"
      />
    )
    expect(screen.getByText("Processed 1H / 13C Spectrum Upload")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Preview processed spectrum/i })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Analyze processed spectrum/i })).toBeInTheDocument()
  })

  it("raw FID section shows title and Preview / Process actions", () => {
    render(<SpectraCheckRawFidSection sampleId="t1" onSampleIdChange={() => {}} solvent="CDCl3" />)
    expect(screen.getByText("Raw FID Upload / Non-destructive Processing")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Preview raw metadata/i })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Process raw FID/i })).toBeInTheDocument()
  })
})

describe("SpectrumViewer", () => {
  it("renders placeholder state without crashing when arrays are empty", () => {
    render(<SpectrumViewer x={[]} y={[]} />)
    expect(screen.getByText(/No spectrum loaded/i)).toBeInTheDocument()
  })
})
