import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
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

vi.mock("@/components/science/SpectrumViewer", () => ({
  SpectrumViewer: ({ nucleus, peaks }: { nucleus?: "1H" | "13C"; peaks?: unknown[] }) => (
    <div data-testid="spectrum-viewer" data-peak-count={peaks?.length ?? 0}>
      Nucleus context: <span>{nucleus}</span>
    </div>
  ),
}))

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

  it("renders processed analyze spectra from direct x/y arrays", async () => {
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
    apiFetchMock.mockResolvedValueOnce({
      sample_id: "sample-1",
      nucleus: "1H",
      filename: "trace.csv",
      point_count: 3,
      peak_count: 1,
      peaks: [{ shift_ppm: 4.1, intensity: 3 }],
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
      />,
    )

    fireEvent.change(screen.getByLabelText(/Processed spectrum file/i, { selector: "input" }), {
      target: { files: [new File(["ppm,intensity\n4.2,0\n4.1,3\n4.0,0\n"], "trace.csv")] },
    })
    fireEvent.click(screen.getByRole("button", { name: /Run evidence match/i }))

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/nmr/processed/preview", expect.any(Object)))
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/nmr/processed/analyze", expect.any(Object)))
    const analyzeCall = apiFetchMock.mock.calls.find(([path]) => path === "/nmr/processed/analyze")
    expect((analyzeCall?.[1]?.body as FormData).get("include_spectrum")).toBe("false")
    expect((analyzeCall?.[1]?.body as FormData).get("preview_points_json")).toBeTruthy()
    expect(await screen.findByText(/Nucleus context/i)).toBeInTheDocument()
    expect(screen.queryByText(/No spectrum loaded/i)).not.toBeInTheDocument()
  })

  it("shows the processed analysis interface immediately while first analyze is pending", async () => {
    apiFetchMock.mockResolvedValueOnce({
      sample_id: "sample-1",
      nucleus: "1H",
      filename: "trace.csv",
      point_count: 3,
      x: [4.2, 4.1, 4.0],
      y: [0, 3, 0],
      warnings: [],
      notes: [],
      metadata: {},
    })
    let resolveAnalyze: ((value: unknown) => void) | null = null
    apiFetchMock.mockImplementationOnce(
      () =>
        new Promise<unknown>((resolve) => {
          resolveAnalyze = resolve
        }),
    )

    renderWithEvidence(
      <SpectraCheckProcessedSpectrumSection
        sampleId="sample-1"
        onSampleIdChange={() => {}}
        solvent="CDCl3"
        candidatesText=""
      />,
    )

    fireEvent.change(screen.getByLabelText(/Processed spectrum file/i, { selector: "input" }), {
      target: { files: [new File(["ppm,intensity\n4.2,0\n4.1,3\n4.0,0\n"], "trace.csv")] },
    })
    fireEvent.click(screen.getByRole("button", { name: /Run evidence match/i }))

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/nmr/processed/preview", expect.any(Object)))
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/nmr/processed/analyze", expect.any(Object)))
    expect(screen.getByText(/Analysis output/i)).toBeInTheDocument()
    expect(screen.getByText(/Nucleus context/i)).toBeInTheDocument()
    expect(screen.queryByTestId("processed-results-pending-spectrum")).not.toBeInTheDocument()
    expect(screen.queryByText(/Waiting for API response/i)).not.toBeInTheDocument()

    expect(resolveAnalyze).not.toBeNull()
    await act(async () => {
      ;(resolveAnalyze as unknown as (value: unknown) => void)({
        sample_id: "sample-1",
        nucleus: "1H",
        filename: "trace.csv",
        point_count: 3,
        x: [4.2, 4.1, 4.0],
        y: [0, 3, 0],
        warnings: [],
        notes: [],
        metadata: {},
      })
    })
  })

  it("raw FID preview automatically generates and displays a quick spectrum", async () => {
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
      metadata: { raw_archive_id: "a".repeat(64) },
    })
    apiFetchMock.mockResolvedValueOnce({
      sample_id: "sample-1",
      filename: "raw.zip",
      nucleus: "1H",
      processing_preset: "safe_automatic",
      point_count: 3,
      x: [4.2, 4.1, 4.0],
      y: [0, 5, 0],
      peaks: [{ shift_ppm: 4.1, intensity: 5, category: "oxygenated" }],
      x_label: "ppm",
      y_label: "intensity",
      reversed_x_axis: true,
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
    fireEvent.click(screen.getByRole("button", { name: /Preview spectrum/i }))

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/nmr/raw-fid/preview", expect.any(Object)))
    await waitFor(() =>
      expect(apiFetchMock).toHaveBeenCalledWith(`/raw-fid/${"a".repeat(64)}/preview`, expect.any(Object)),
    )
    expect(await screen.findByText(/Auto-FT preview/i)).toBeInTheDocument()
    expect(screen.queryByText(/Raw spectrum not generated yet/i)).not.toBeInTheDocument()
  })

  it("raw FID preview uses inline spectrum data without a second processing request", async () => {
    apiFetchMock.mockResolvedValueOnce({
      sample_id: "sample-1",
      filename: "raw.zip",
      raw_sha256: "a".repeat(64),
      vendor_detected: "Bruker",
      nucleus: "1H",
      processing_preset: "balanced",
      point_count: 3,
      x: [4.2, 4.1, 4.0],
      y: [0, 5, 0],
      peaks: [{ shift_ppm: 4.1, intensity: 5, category: "oxygenated" }],
      x_label: "ppm",
      y_label: "intensity",
      reversed_x_axis: true,
      acquisition_parameters: {},
      file_inventory: {},
      warnings: [],
      notes: [],
      metadata: { raw_archive_id: "a".repeat(64), inline_spectrum_generated: true },
    })

    renderWithEvidence(
      <SpectraCheckRawFidSection sampleId="sample-1" onSampleIdChange={() => {}} solvent="CDCl3" />,
    )

    fireEvent.change(screen.getByLabelText(/Raw FID archive/i, { selector: "input" }), {
      target: { files: [new File(["raw"], "raw.zip", { type: "application/zip" })] },
    })
    fireEvent.click(screen.getByRole("button", { name: /Preview spectrum/i }))

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(1))
    expect(apiFetchMock).toHaveBeenCalledWith("/nmr/raw-fid/preview", expect.any(Object))
    expect(await screen.findByText(/Auto-FT preview/i)).toBeInTheDocument()
    expect(screen.queryByText(/Raw spectrum not generated yet/i)).not.toBeInTheDocument()
  })

  it("raw FID process always calls the process endpoint after preview", async () => {
    apiFetchMock.mockResolvedValueOnce({
      sample_id: "sample-1",
      filename: "raw.zip",
      raw_sha256: "a".repeat(64),
      vendor_detected: "Bruker",
      nucleus: "1H",
      processing_preset: "balanced",
      point_count: 3,
      x: [4.2, 4.1, 4.0],
      y: [0, 5, 0],
      peaks: [{ shift_ppm: 4.1, intensity: 5, category: "oxygenated" }],
      x_label: "ppm",
      y_label: "intensity",
      reversed_x_axis: true,
      acquisition_parameters: {},
      file_inventory: {},
      warnings: [],
      notes: [],
      metadata: { raw_archive_id: "a".repeat(64), inline_spectrum_generated: true },
    })
    apiFetchMock.mockResolvedValueOnce({
      sample_id: "sample-1",
      filename: "raw.zip",
      vendor_detected: "Bruker",
      nucleus: "1H",
      processing_preset: "safe_automatic",
      point_count: 3,
      x: [4.2, 4.1, 4.0],
      y: [0, 6, 0],
      x_label: "ppm",
      y_label: "intensity",
      reversed_x_axis: true,
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
    fireEvent.click(screen.getByRole("button", { name: /Preview spectrum/i }))

    expect(await screen.findByText(/Auto-FT preview/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /Process FID/i }))

    await screen.findByText(/Processed FID output/i)
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/nmr/raw-fid/process", expect.any(Object)))
    expect(apiFetchMock).toHaveBeenCalledTimes(2)
  })

  it("raw FID preview renders a trace-only spectrum even when payload contains peaks", async () => {
    apiFetchMock.mockResolvedValueOnce({
      sample_id: "sample-1",
      filename: "raw.zip",
      raw_sha256: "a".repeat(64),
      vendor_detected: "Bruker",
      nucleus: "1H",
      processing_preset: "balanced",
      point_count: 3,
      x: [4.2, 4.1, 4.0],
      y: [0, 5, 0],
      peaks: [{ shift_ppm: 4.1, intensity: 5, category: "unknown" }],
      x_label: "ppm",
      y_label: "intensity",
      reversed_x_axis: true,
      acquisition_parameters: {},
      file_inventory: {},
      warnings: [],
      notes: [],
      metadata: { raw_archive_id: "a".repeat(64), inline_spectrum_generated: true },
    })

    renderWithEvidence(
      <SpectraCheckRawFidSection sampleId="sample-1" onSampleIdChange={() => {}} solvent="CDCl3" />,
    )

    fireEvent.change(screen.getByLabelText(/Raw FID archive/i, { selector: "input" }), {
      target: { files: [new File(["raw"], "raw.zip", { type: "application/zip" })] },
    })
    fireEvent.click(screen.getByRole("button", { name: /Preview spectrum/i }))

    const viewer = await screen.findByTestId("spectrum-viewer")
    expect(viewer).toHaveAttribute("data-peak-count", "0")
  })

  it("raw FID process displays returned spectrum points", async () => {
    apiFetchMock.mockResolvedValueOnce({
      sample_id: "sample-1",
      filename: "raw.zip",
      vendor_detected: "Bruker",
      nucleus: "1H",
      processing_preset: "safe_automatic",
      point_count: 3,
      x: [4.2, 4.1, 4.0],
      y: [0, 5, 0],
      peaks: [{ shift_ppm: 4.1, intensity: 5, category: "oxygenated" }],
      x_label: "ppm",
      y_label: "intensity",
      reversed_x_axis: true,
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
    fireEvent.click(screen.getByRole("button", { name: /Process FID/i }))

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/nmr/raw-fid/process", expect.any(Object)))
    expect(await screen.findByText(/Nucleus context/i)).toBeInTheDocument()
    expect(screen.getByTestId("spectrum-viewer")).toHaveAttribute("data-peak-count", "1")
    expect(screen.queryByText(/No spectrum loaded/i)).not.toBeInTheDocument()
  })

  it("shows the raw FID processing interface immediately while first process is pending", async () => {
    let resolveProcess: ((value: unknown) => void) | null = null
    apiFetchMock.mockImplementationOnce(
      () =>
        new Promise<unknown>((resolve) => {
          resolveProcess = resolve
        }),
    )

    renderWithEvidence(
      <SpectraCheckRawFidSection sampleId="sample-1" onSampleIdChange={() => {}} solvent="CDCl3" />,
    )

    fireEvent.change(screen.getByLabelText(/Raw FID archive/i, { selector: "input" }), {
      target: { files: [new File(["raw"], "raw.zip", { type: "application/zip" })] },
    })
    fireEvent.click(screen.getByRole("button", { name: /Process FID/i }))

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/nmr/raw-fid/process", expect.any(Object)))
    expect(screen.getByText(/Processed FID output/i)).toBeInTheDocument()
    expect(screen.getByTestId("raw-fid-results-pending-spectrum")).toBeInTheDocument()
    expect(screen.queryByText(/Waiting for API response/i)).not.toBeInTheDocument()

    expect(resolveProcess).not.toBeNull()
    await act(async () => {
      ;(resolveProcess as unknown as (value: unknown) => void)({
        sample_id: "sample-1",
        filename: "raw.zip",
        vendor_detected: "Bruker",
        nucleus: "1H",
        point_count: 3,
        x: [4.2, 4.1, 4.0],
        y: [0, 5, 0],
        warnings: [],
        notes: [],
        metadata: {},
      })
    })
  })

  it("keeps the prior chart mounted while analyze is in-flight (no flash)", async () => {
    // Preview returns a working spectrum first.
    apiFetchMock.mockResolvedValueOnce({
      sample_id: "sample-1",
      nucleus: "1H",
      filename: "preview.csv",
      point_count: 3,
      x: [4.2, 4.1, 4.0],
      y: [0, 5, 0],
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
      />,
    )

    fireEvent.change(screen.getByLabelText(/Processed spectrum file/i, { selector: "input" }), {
      target: { files: [new File(["ppm,intensity\n4.2,0\n4.1,5\n4.0,0\n"], "preview.csv")] },
    })
    fireEvent.click(screen.getByRole("button", { name: /Inspect spectrum/i }))
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/nmr/processed/preview", expect.any(Object)))
    expect(await screen.findByText(/Nucleus context/i)).toBeInTheDocument()

    // Now stage the analyze response as a deferred promise so we can
    // observe the in-flight state. The previous chart MUST stay mounted
    // (Nucleus-context text present) while the analyze is pending.
    let resolveAnalyze: ((value: unknown) => void) | null = null
    apiFetchMock.mockImplementationOnce(
      () =>
        new Promise<unknown>((resolve) => {
          resolveAnalyze = resolve
        }),
    )

    fireEvent.click(screen.getByRole("button", { name: /Run evidence match/i }))

    // While the analyze promise is unresolved, the chart's "Nucleus context"
    // line — which only renders inside ``SpectrumViewer`` — must still be
    // on screen. If the section pre-cleared the previous result the
    // SpectrumViewer would have unmounted and this assertion would fail.
    await waitFor(() =>
      expect(apiFetchMock).toHaveBeenCalledWith("/nmr/processed/analyze", expect.any(Object)),
    )
    const analyzeCall = apiFetchMock.mock.calls.find(([path]) => path === "/nmr/processed/analyze")
    expect((analyzeCall?.[1]?.body as FormData).get("include_spectrum")).toBe("false")
    expect((analyzeCall?.[1]?.body as FormData).get("preview_points_json")).toBeTruthy()
    expect(screen.getByText(/Nucleus context/i)).toBeInTheDocument()

    // Resolve the analyze; chart updates atomically.
    expect(resolveAnalyze).not.toBeNull()
    ;(resolveAnalyze as unknown as (value: unknown) => void)({
      sample_id: "sample-1",
      nucleus: "1H",
      filename: "analyze.csv",
      point_count: 3,
      x: [4.2, 4.1, 4.0],
      y: [0, 7, 0],
      peak_count: 1,
      peaks: [{ shift_ppm: 4.1, integration_h: 1, multiplicity: "s" }],
      warnings: [],
      notes: [],
      metadata: {},
    })
    await waitFor(() =>
      expect(screen.getByText(/Nucleus context/i)).toBeInTheDocument(),
    )
  })

  it("replaces stale analyze output when a later preview finishes", async () => {
    apiFetchMock.mockResolvedValueOnce({
      sample_id: "sample-1",
      nucleus: "1H",
      filename: "analyze.csv",
      point_count: 3,
      x: [4.2, 4.1, 4.0],
      y: [0, 7, 0],
      warnings: [],
      notes: [],
      metadata: {},
    })
    apiFetchMock.mockResolvedValueOnce({
      sample_id: "sample-1",
      nucleus: "1H",
      filename: "analyze.csv",
      point_count: 3,
      peak_count: 1,
      analysis_score: 0.91,
      peaks: [{ shift_ppm: 4.1, integration_h: 1, multiplicity: "s" }],
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
      />,
    )

    fireEvent.change(screen.getByLabelText(/Processed spectrum file/i, { selector: "input" }), {
      target: { files: [new File(["ppm,intensity\n4.2,0\n4.1,7\n4.0,0\n"], "analyze.csv")] },
    })
    fireEvent.click(screen.getByRole("button", { name: /Run evidence match/i }))
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/nmr/processed/analyze", expect.any(Object)))
    expect(await screen.findByText(/Analysis score/i)).toBeInTheDocument()

    apiFetchMock.mockResolvedValueOnce({
      sample_id: "sample-1",
      nucleus: "1H",
      filename: "preview.csv",
      point_count: 3,
      x: [4.2, 4.1, 4.0],
      y: [0, 5, 0],
      warnings: [],
      notes: [],
      metadata: {},
    })

    fireEvent.click(screen.getByRole("button", { name: /Inspect spectrum/i }))

    await waitFor(() =>
      expect(apiFetchMock).toHaveBeenCalledWith("/nmr/processed/preview", expect.any(Object)),
    )
    await waitFor(() => expect(screen.queryByText(/Analysis score/i)).not.toBeInTheDocument())
    expect(screen.getByText(/Nucleus context/i)).toBeInTheDocument()
  })

  it("ignores an analyze response that resolves after Clear", async () => {
    apiFetchMock.mockResolvedValueOnce({
      sample_id: "sample-1",
      nucleus: "1H",
      filename: "pending.csv",
      point_count: 3,
      x: [4.2, 4.1, 4.0],
      y: [0, 7, 0],
      warnings: [],
      notes: [],
      metadata: {},
    })
    let resolveAnalyze: ((value: unknown) => void) | null = null
    apiFetchMock.mockImplementationOnce(
      () =>
        new Promise<unknown>((resolve) => {
          resolveAnalyze = resolve
        }),
    )

    renderWithEvidence(
      <SpectraCheckProcessedSpectrumSection
        sampleId="sample-1"
        onSampleIdChange={() => {}}
        solvent="CDCl3"
        candidatesText=""
      />,
    )

    fireEvent.change(screen.getByLabelText(/Processed spectrum file/i, { selector: "input" }), {
      target: { files: [new File(["ppm,intensity\n4.2,0\n4.1,7\n4.0,0\n"], "pending.csv")] },
    })
    fireEvent.click(screen.getByRole("button", { name: /Run evidence match/i }))
    await waitFor(() =>
      expect(apiFetchMock).toHaveBeenCalledWith("/nmr/processed/analyze", expect.any(Object)),
    )

    fireEvent.click(screen.getByRole("button", { name: /^Clear$/i }))
    expect(screen.queryByTestId("processed-results-loading-badge")).not.toBeInTheDocument()

    expect(resolveAnalyze).not.toBeNull()
    await act(async () => {
      ;(resolveAnalyze as unknown as (value: unknown) => void)({
        sample_id: "sample-1",
        nucleus: "1H",
        filename: "pending.csv",
        point_count: 3,
        x: [4.2, 4.1, 4.0],
        y: [0, 7, 0],
        analysis_score: 0.91,
        warnings: [],
        notes: [],
        metadata: {},
      })
    })

    expect(screen.queryByText(/Nucleus context/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Analysis score/i)).not.toBeInTheDocument()
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

    fireEvent.click(screen.getByRole("button", { name: /Preview spectrum/i }))

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledWith("/nmr/raw-fid/preview", expect.any(Object)))
  })
})
