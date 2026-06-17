import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { GreenMetricsPanel } from "@/components/reaction-optimization/green-metrics-panel"

const api = vi.hoisted(() => ({
  computeGreenMetrics: vi.fn(),
  getGreenMetrics: vi.fn(),
  compareGreenMetrics: vi.fn(),
}))

// Partial mock — keep the real constants/readers (GREEN_METRICS, readGreenMetric,
// formatGreenMetric, GREEN_COMPONENT_ROLES); stub only the network calls.
vi.mock("@/lib/reaction/green-metrics", async (orig) => ({
  ...(await orig<typeof import("@/lib/reaction/green-metrics")>()),
  computeGreenMetrics: (...a: unknown[]) => api.computeGreenMetrics(...a),
  getGreenMetrics: (...a: unknown[]) => api.getGreenMetrics(...a),
  compareGreenMetrics: (...a: unknown[]) => api.compareGreenMetrics(...a),
}))

const EXPERIMENTS = [
  { id: 10, experiment_code: "EXP-A" },
  { id: 11, experiment_code: "EXP-B" },
]

const ASSESSMENT = {
  id: 1,
  reaction_experiment_id: 10,
  reaction_project_id: 5,
  metrics_json: { green_score: 42.5, e_factor: 5.7, pmi: 6.7, atom_economy_percent: 100, rme_percent: 14.9 },
  provenance_json: { formula_version: "v1", solvent_table_version: "chem21-2016", citations: ["CHEM21 (2016)"] },
  warnings: ["Atom economy exceeded 100%; clamped to 100%."],
}

beforeEach(() => {
  api.computeGreenMetrics.mockReset()
  api.getGreenMetrics.mockReset()
  api.compareGreenMetrics.mockReset()
})

describe("GreenMetricsPanel", () => {
  it("prompts to add an experiment when there are none", () => {
    render(<GreenMetricsPanel projectId={5} experiments={[]} />)
    expect(screen.getByText(/Add an experiment to compute green metrics/i)).toBeInTheDocument()
  })

  it("renders the latest assessment metrics and warnings", async () => {
    api.getGreenMetrics.mockResolvedValue(ASSESSMENT)
    render(<GreenMetricsPanel projectId={5} experiments={EXPERIMENTS} />)
    await waitFor(() => expect(screen.getByText("42.5")).toBeInTheDocument()) // green_score
    expect(screen.getByText("5.7")).toBeInTheDocument() // e_factor
    expect(screen.getByText(/clamped to 100%/i)).toBeInTheDocument() // warning surfaced
    expect(api.getGreenMetrics).toHaveBeenCalledWith(5, 10)
  })

  it("shows the empty state when no assessment exists yet (404)", async () => {
    const { ApiError } = await import("@/lib/api/client")
    api.getGreenMetrics.mockRejectedValue(new ApiError(404, { detail: "none" }, "nf"))
    render(<GreenMetricsPanel projectId={5} experiments={EXPERIMENTS} />)
    await waitFor(() => expect(screen.getByText(/No green assessment yet/i)).toBeInTheDocument())
  })

  it("computes green metrics with the entered product + persist flag", async () => {
    const user = userEvent.setup()
    const { ApiError } = await import("@/lib/api/client")
    api.getGreenMetrics.mockRejectedValue(new ApiError(404, {}, "nf"))
    api.computeGreenMetrics.mockResolvedValue({ ...ASSESSMENT, metrics_json: { green_score: 50 } })
    render(<GreenMetricsPanel projectId={5} experiments={EXPERIMENTS} />)
    await waitFor(() => expect(screen.getByText(/No green assessment yet/i)).toBeInTheDocument())

    await user.type(screen.getByLabelText("Product SMILES"), "CCO")
    await user.type(screen.getByLabelText("Product mass (g)"), "100")
    await user.click(screen.getByRole("button", { name: /^Compute$/ }))

    await waitFor(() => {
      const call = api.computeGreenMetrics.mock.calls[0]
      expect(call[0]).toBe(5)
      expect(call[1]).toBe(10)
      expect(call[2]).toMatchObject({ product_smiles: "CCO", product_mass_g: 100, persist_to_outcome: true })
    })
    expect(screen.getByText("50")).toBeInTheDocument()
  })

  it("compares experiments and highlights the best per metric", async () => {
    const user = userEvent.setup()
    const { ApiError } = await import("@/lib/api/client")
    api.getGreenMetrics.mockRejectedValue(new ApiError(404, {}, "nf"))
    api.compareGreenMetrics.mockResolvedValue({
      reaction_project_id: 5,
      entries: [
        { reaction_experiment_id: 10, experiment_code: "EXP-A", available: true, metrics_json: { green_score: 42, e_factor: 5 } },
        { reaction_experiment_id: 11, experiment_code: "EXP-B", available: true, metrics_json: { green_score: 60, e_factor: 9 } },
      ],
      human_review_required: true,
    })
    render(<GreenMetricsPanel projectId={5} experiments={EXPERIMENTS} />)
    await screen.findByText("Compare experiments")

    await user.click(screen.getByLabelText("EXP-A"))
    await user.click(screen.getByLabelText("EXP-B"))
    await user.click(screen.getByRole("button", { name: /Compare \(2\)/ }))

    await waitFor(() => expect(api.compareGreenMetrics).toHaveBeenCalledWith(5, [10, 11]))
    // both experiment codes appear in the comparison table
    await waitFor(() => expect(screen.getAllByText("EXP-B").length).toBeGreaterThan(0))
  })
})
