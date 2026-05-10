import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen } from "@testing-library/react"
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
    expect(screen.getByText("Configure & upload spectrum")).toBeInTheDocument()
    // Action tile buttons (Step 2) — text is concatenated from inner spans.
    expect(screen.getByRole("button", { name: /Inspect spectrum/i })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Run evidence match/i })).toBeInTheDocument()
  })

  it("raw FID section shows title and Preview / Process actions", () => {
    render(<SpectraCheckRawFidSection sampleId="t1" onSampleIdChange={() => {}} solvent="CDCl3" />)
    expect(screen.getByText("Configure & upload raw FID archive")).toBeInTheDocument()
    // Action tile buttons (Step 2).
    expect(screen.getByRole("button", { name: /Preview metadata/i })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Process FID/i })).toBeInTheDocument()
  })

  it("processed spectrum drop-zone opens the native file picker", () => {
    render(
      <SpectraCheckProcessedSpectrumSection
        sampleId="t1"
        onSampleIdChange={() => {}}
        solvent="CDCl3"
        candidatesText="A | CCO"
      />
    )
    const input = screen.getByLabelText(/Processed spectrum file/i, { selector: "input" }) as HTMLInputElement
    const clickSpy = vi.spyOn(input, "click").mockImplementation(() => undefined)

    fireEvent.click(screen.getByRole("button", { name: /Drop processed spectrum file/i }))

    expect(clickSpy).toHaveBeenCalled()
    clickSpy.mockRestore()
  })

  it("processed spectrum picker includes parseable NMR spectrum file formats", () => {
    render(
      <SpectraCheckProcessedSpectrumSection
        sampleId="t1"
        onSampleIdChange={() => {}}
        solvent="CDCl3"
        candidatesText="A | CCO"
      />
    )
    const input = screen.getByLabelText(/Processed spectrum file/i, { selector: "input" }) as HTMLInputElement

    expect(input.accept).toContain(".jcamp")
    expect(input.accept).toContain(".xy")
    expect(input.accept).toContain(".asc")
    expect(input.accept).toContain(".dat")
    expect(input.accept).not.toContain(".fid")
    expect(input.accept).not.toContain(".mnova")
  })

  it("raw FID drop-zone opens the native file picker", () => {
    render(<SpectraCheckRawFidSection sampleId="t1" onSampleIdChange={() => {}} solvent="CDCl3" />)
    const input = screen.getByLabelText(/Raw FID archive/i, { selector: "input" }) as HTMLInputElement
    const clickSpy = vi.spyOn(input, "click").mockImplementation(() => undefined)

    fireEvent.click(screen.getByRole("button", { name: /Drop raw FID archive/i }))

    expect(clickSpy).toHaveBeenCalled()
    clickSpy.mockRestore()
  })

  it("raw FID picker includes every supported raw archive format", () => {
    render(<SpectraCheckRawFidSection sampleId="t1" onSampleIdChange={() => {}} solvent="CDCl3" />)
    const input = screen.getByLabelText(/Raw FID archive/i, { selector: "input" }) as HTMLInputElement

    expect(input.accept).toContain(".zip")
    expect(input.accept).toContain(".tar.gz")
    expect(input.accept).toContain(".tgz")
    expect(input.accept).not.toContain(".fid")
    expect(input.accept).not.toContain(".mnova")
  })
})

describe("SpectrumViewer", () => {
  it("renders placeholder state without crashing when arrays are empty", () => {
    render(<SpectrumViewer x={[]} y={[]} />)
    expect(screen.getByText(/No spectrum loaded/i)).toBeInTheDocument()
  })
})
