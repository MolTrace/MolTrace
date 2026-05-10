import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import type { ReactElement } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { apiFetch } from "@/lib/api/client"
import { SpectraCheckProcessedSpectrumSection } from "@/components/spectracheck/spectracheck-processed-spectrum-section"
import { SpectraCheckRawFidSection } from "@/components/spectracheck/spectracheck-raw-fid-section"
import { SpectraCheckEvidenceProvider } from "@/src/lib/spectracheck/useSpectraCheckEvidence"

vi.mock("@/lib/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/client")>("@/lib/api/client")
  return {
    ...actual,
    apiFetch: vi.fn(),
  }
})

const apiFetchMock = vi.mocked(apiFetch)

function renderWithEvidence(ui: ReactElement) {
  return render(<SpectraCheckEvidenceProvider>{ui}</SpectraCheckEvidenceProvider>)
}

describe("SpectraCheck preview rendering", () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it("renders processed preview spectra without the empty placeholder", async () => {
    apiFetchMock.mockResolvedValueOnce({
      sample_id: "sample-1",
      nucleus: "1H",
      filename: "trace.csv",
      point_count: 3,
      x: [4.2, 4.1, 4],
      y: [0, 3, 0],
      warnings: [],
      notes: [],
      metadata: {},
    })

    renderWithEvidence(
      <SpectraCheckProcessedSpectrumSection
        sampleId="sample-1"
        onSampleIdChange={() => {}}
        solvent="CDCl3"
        candidatesText=""
      />
    )

    // Disambiguate — the drop-zone div has aria-label="Drop processed spectrum file..."
    // which also matches the regex; restrict to the actual <input>.
    fireEvent.change(screen.getByLabelText(/Processed spectrum file/i, { selector: "input" }), {
      target: { files: [new File(["ppm,intensity\n4.2,0\n4.1,3\n4.0,0\n"], "trace.csv")] },
    })
    // Step 2 "Preview" action tile — accessible name includes the headline "Inspect spectrum".
    fireEvent.click(screen.getByRole("button", { name: /Inspect spectrum/i }))

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/nmr/processed/preview", expect.any(Object)))
    expect(await screen.findByText(/Nucleus context/i)).toBeInTheDocument()
    expect(screen.queryByText(/No spectrum loaded/i)).not.toBeInTheDocument()
  })

  it("runs processed preview from a dropped spectrum file", async () => {
    apiFetchMock.mockResolvedValueOnce({
      sample_id: "sample-1",
      nucleus: "1H",
      filename: "dropped.csv",
      point_count: 2,
      x: [4.2, 4.1],
      y: [0, 2],
      warnings: [],
      notes: [],
      metadata: {},
    })

    renderWithEvidence(
      <SpectraCheckProcessedSpectrumSection
        sampleId="sample-1"
        onSampleIdChange={() => {}}
        solvent="CDCl3"
        candidatesText=""
      />
    )

    fireEvent.drop(screen.getByRole("button", { name: /Drop processed spectrum file/i }), {
      dataTransfer: {
        files: [new File(["ppm,intensity\n4.2,0\n4.1,2\n"], "dropped.csv")],
      },
    })
    expect(await screen.findByText("dropped.csv")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /Inspect spectrum/i }))

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/nmr/processed/preview", expect.any(Object)))
  })

  it("does not show the spectrum placeholder for raw metadata-only preview", async () => {
    apiFetchMock.mockResolvedValueOnce({
      sample_id: "sample-1",
      filename: "raw.zip",
      raw_sha256: "a".repeat(64),
      vendor_detected: "Bruker",
      nucleus: "1H",
      acquisition_parameters: {},
      file_inventory: {},
      warnings: [],
      notes: [],
      metadata: {},
    })

    renderWithEvidence(
      <SpectraCheckRawFidSection sampleId="sample-1" onSampleIdChange={() => {}} solvent="CDCl3" />,
    )

    fireEvent.change(screen.getByLabelText(/Raw FID archive/i, { selector: "input" }), {
      target: { files: [new File(["raw"], "raw.zip", { type: "application/zip" })] },
    })
    // Step 2 "Inspect" action tile — accessible name includes the headline "Preview metadata".
    fireEvent.click(screen.getByRole("button", { name: /Preview metadata/i }))

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/nmr/raw-fid/preview", expect.any(Object)))
    expect(await screen.findByText(/Raw spectrum not generated yet/i)).toBeInTheDocument()
    expect(screen.queryByText(/No spectrum loaded/i)).not.toBeInTheDocument()
  })

  it("runs raw FID preview from a dropped archive", async () => {
    apiFetchMock.mockResolvedValueOnce({
      sample_id: "sample-1",
      filename: "dropped.zip",
      raw_sha256: "a".repeat(64),
      vendor_detected: "Bruker",
      nucleus: "1H",
      acquisition_parameters: {},
      file_inventory: {},
      warnings: [],
      notes: [],
      metadata: {},
    })

    renderWithEvidence(
      <SpectraCheckRawFidSection sampleId="sample-1" onSampleIdChange={() => {}} solvent="CDCl3" />,
    )

    fireEvent.drop(screen.getByRole("button", { name: /Drop raw FID archive/i }), {
      dataTransfer: {
        files: [new File(["raw"], "dropped.zip", { type: "application/zip" })],
      },
    })
    expect(await screen.findByText("dropped.zip")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: /Preview metadata/i }))

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/nmr/raw-fid/preview", expect.any(Object)))
  })
})
