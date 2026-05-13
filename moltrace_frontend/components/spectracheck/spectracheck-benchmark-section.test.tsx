import { describe, expect, it, vi, beforeEach } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { apiFetch } from "@/lib/api/client"
import { SpectraCheckBenchmarkSection } from "@/components/spectracheck/spectracheck-benchmark-section"

vi.mock("@/lib/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/client")>("@/lib/api/client")
  return { ...actual, apiFetch: vi.fn() }
})
const apiFetchMock = vi.mocked(apiFetch)

const MOCK_RESPONSE = {
  case_count: 1,
  overall_mean_score: 0.78,
  aggregates: [
    { layer: "peak_level_accuracy", mean_score: 0.5, case_count: 1, min_score: 0.5, max_score: 0.5 },
    { layer: "structural_ranking", mean_score: 1.0, case_count: 1, min_score: 1.0, max_score: 1.0 },
    { layer: "explainability", mean_score: 1.0, case_count: 1, min_score: 1.0, max_score: 1.0 },
    { layer: "robustness", mean_score: 0.5, case_count: 1, min_score: 0.5, max_score: 0.5 },
    { layer: "regulatory_evidence", mean_score: 1.0, case_count: 1, min_score: 1.0, max_score: 1.0 },
  ],
  cases: [
    {
      case_id: "ethanol-1",
      smiles: "CCO",
      nucleus: "1H",
      solvent: "CDCl3",
      overall_score: 0.78,
      layers: [
        { name: "peak_level_accuracy", score: 0.5, components: { matched: 1 }, notes: [] },
        { name: "structural_ranking", score: 1.0, components: { rank_of_true_structure: 1 }, notes: [] },
        { name: "explainability", score: 1.0, components: { with_reason: 3, peak_count: 3 }, notes: [] },
        { name: "robustness", score: 0.5, components: { drop_peaks: 1 }, notes: [] },
        { name: "regulatory_evidence", score: 1.0, components: { has_sample_id: true }, notes: [] },
      ],
      summary: ["Overall 78% across 5 layers."],
      warnings: [],
    },
  ],
  notes: [],
}

describe("SpectraCheckBenchmarkSection", () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it("renders the suite input, drop-peaks input, and run button", () => {
    render(<SpectraCheckBenchmarkSection />)
    expect(screen.getByTestId("benchmark-section")).toBeInTheDocument()
    expect(screen.getByTestId("benchmark-suite-input")).toBeInTheDocument()
    expect(screen.getByTestId("benchmark-drop-input")).toBeInTheDocument()
    expect(screen.getByTestId("benchmark-run-button")).toBeInTheDocument()
  })

  it("rejects invalid JSON before calling the backend", async () => {
    render(<SpectraCheckBenchmarkSection />)
    const textarea = screen.getByTestId("benchmark-suite-input") as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: "not-json" } })
    fireEvent.click(screen.getByTestId("benchmark-run-button"))
    await waitFor(() => expect(screen.getByText(/Cases JSON is invalid/i)).toBeInTheDocument())
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it("rejects empty JSON arrays before calling the backend", async () => {
    render(<SpectraCheckBenchmarkSection />)
    fireEvent.change(screen.getByTestId("benchmark-suite-input"), { target: { value: "[]" } })
    fireEvent.click(screen.getByTestId("benchmark-run-button"))
    await waitFor(() =>
      expect(screen.getByText(/Cases must be a non-empty JSON array\./i)).toBeInTheDocument(),
    )
    expect(apiFetchMock).not.toHaveBeenCalled()
  })

  it("renders aggregate cards and per-case scorecards after a successful run", async () => {
    apiFetchMock.mockResolvedValueOnce(MOCK_RESPONSE)
    render(<SpectraCheckBenchmarkSection />)
    fireEvent.click(screen.getByTestId("benchmark-run-button"))

    await waitFor(() =>
      expect(apiFetchMock).toHaveBeenCalledWith(
        "/benchmark/spectracheck/run",
        expect.objectContaining({ method: "POST" }),
      ),
    )

    // All 5 layer cards rendered.
    expect(await screen.findByTestId("benchmark-aggregates")).toBeInTheDocument()
    expect(screen.getByTestId("benchmark-layer-peak_level_accuracy")).toBeInTheDocument()
    expect(screen.getByTestId("benchmark-layer-structural_ranking")).toBeInTheDocument()
    expect(screen.getByTestId("benchmark-layer-explainability")).toBeInTheDocument()
    expect(screen.getByTestId("benchmark-layer-robustness")).toBeInTheDocument()
    expect(screen.getByTestId("benchmark-layer-regulatory_evidence")).toBeInTheDocument()

    // Means rendered as percentages.
    expect(screen.getByTestId("benchmark-mean-explainability")).toHaveTextContent("100%")
    expect(screen.getByTestId("benchmark-mean-peak_level_accuracy")).toHaveTextContent("50%")

    // Per-case scorecard rendered with 5 layer rows.
    expect(screen.getByTestId("benchmark-case-ethanol-1")).toBeInTheDocument()
    expect(screen.getByTestId("benchmark-case-ethanol-1-peak_level_accuracy")).toBeInTheDocument()
    expect(screen.getByTestId("benchmark-case-ethanol-1-regulatory_evidence")).toBeInTheDocument()
  })

  it("surfaces backend errors via the error alert", async () => {
    apiFetchMock.mockRejectedValueOnce(new Error("server-on-fire"))
    render(<SpectraCheckBenchmarkSection />)
    fireEvent.click(screen.getByTestId("benchmark-run-button"))
    await waitFor(() => expect(screen.getByText(/server-on-fire/i)).toBeInTheDocument())
  })

  it("includes the robustness_drop_peaks value in the request body", async () => {
    apiFetchMock.mockResolvedValueOnce(MOCK_RESPONSE)
    render(<SpectraCheckBenchmarkSection />)
    fireEvent.change(screen.getByTestId("benchmark-drop-input"), { target: { value: "3" } })
    fireEvent.click(screen.getByTestId("benchmark-run-button"))

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled())
    const [, options] = apiFetchMock.mock.calls[0]
    const body = JSON.parse(String((options as RequestInit | undefined)?.body ?? "{}"))
    expect(body.robustness_drop_peaks).toBe(3)
    expect(Array.isArray(body.cases)).toBe(true)
    expect(body.cases.length).toBeGreaterThan(0)
  })
})
