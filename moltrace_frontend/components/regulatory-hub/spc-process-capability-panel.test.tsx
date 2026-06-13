import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { SPCProcessCapabilityPanel } from "@/components/regulatory-hub/spc-process-capability-panel"
import type { components } from "@/src/lib/api/schema"

const mockApiFetch = vi.hoisted(() => vi.fn<(path: string, init?: unknown) => Promise<unknown>>())

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  apiFetch: (path: string, init?: unknown) => mockApiFetch(path, init),
}))

type SPCResult = components["schemas"]["SPCAnalyzeResult"]
type SPCCapability = components["schemas"]["SPCCapabilityOut"]

const DISCLAIMER = "Decision-support only, NOT a batch disposition. Human review of the trend is required."

function capability(overrides: Partial<SPCCapability> = {}): SPCCapability {
  return {
    n: 20,
    mean: 100.7,
    sigma_within: 0.42,
    sigma_overall: 1.1,
    usl: 103,
    lsl: 97,
    target: 100,
    cp: 1.51,
    cpk: 1.34,
    cpu: 1.34,
    cpl: 1.68,
    pp: 0.9,
    ppk: 0.82,
    cpm: 0.78,
    rating: "capable",
    interpretation: "Process is capable (Cpk 1.34 ≥ 1.33).",
    is_capable: true,
    warnings: [],
    ...overrides,
  }
}

function result(overrides: Partial<SPCResult> = {}): SPCResult {
  return {
    product: "Examplinib tablets",
    parameter: "Assay",
    n: 20,
    rule_set: "western_electric",
    capability: capability(),
    spc_signals: [
      {
        rule_number: 3,
        rule_name: "6 points trending",
        method: "shewhart",
        description: "Six consecutive points steadily increasing.",
        indices: [12, 13, 14, 15, 16, 17],
        side: "upper",
      },
    ],
    cusum_signals: [],
    ewma_signals: [],
    alerts: [
      { severity: "critical", category: "oos", message: "2 points out of specification.", indices: [18, 19] },
      { severity: "warning", category: "spc", message: "Upward trend detected.", indices: [12, 13, 14, 15, 16, 17] },
    ],
    oos_indices: [18, 19],
    first_signal_index: 12,
    first_oos_index: 18,
    lead_points: 6,
    disclaimer: DISCLAIMER,
    human_review_required: true,
    ...overrides,
  }
}

describe("SPCProcessCapabilityPanel", () => {
  beforeEach(() => mockApiFetch.mockReset())

  it("renders the input form and no result before analysis", () => {
    render(<SPCProcessCapabilityPanel />)
    expect(screen.getByText("Process Capability & Trending")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Analyze series/ })).toBeInTheDocument()
    expect(screen.queryByTestId("spc-control-chart")).not.toBeInTheDocument()
  })

  it("blocks analysis with fewer than two measurements (no fetch)", async () => {
    const user = userEvent.setup()
    render(<SPCProcessCapabilityPanel />)
    const textarea = screen.getByLabelText("Measurements")
    await user.clear(textarea)
    await user.type(textarea, "100.0")
    await user.click(screen.getByRole("button", { name: /Analyze series/ }))
    expect(screen.getByText(/at least two measurements/i)).toBeInTheDocument()
    expect(mockApiFetch).not.toHaveBeenCalled()
  })

  it("blocks analysis when both spec limits are missing (no fetch)", async () => {
    const user = userEvent.setup()
    render(<SPCProcessCapabilityPanel />)
    await user.clear(screen.getByLabelText("USL"))
    await user.clear(screen.getByLabelText("LSL"))
    await user.click(screen.getByRole("button", { name: /Analyze series/ }))
    expect(screen.getByText(/at least one specification limit/i)).toBeInTheDocument()
    expect(mockApiFetch).not.toHaveBeenCalled()
  })

  it("POSTs the parsed series and renders capability, chart, signals, alerts, and the verbatim disclaimer", async () => {
    const user = userEvent.setup()
    mockApiFetch.mockResolvedValue(result())
    render(<SPCProcessCapabilityPanel />)

    await user.click(screen.getByRole("button", { name: /Analyze series/ }))

    await waitFor(() => expect(screen.getByTestId("spc-control-chart")).toBeInTheDocument())

    // request shape: hit the endpoint with the 20 seeded measurements + limits
    const [path, init] = mockApiFetch.mock.calls[0] as [string, { method: string; body: Record<string, unknown> }]
    expect(path).toBe("/regulatory/spc/analyze")
    expect(init.method).toBe("POST")
    expect((init.body.measurements as unknown[]).length).toBe(20)
    expect(init.body.usl).toBe(103)
    expect(init.body.lsl).toBe(97)
    expect(init.body.measurements).toEqual(
      expect.arrayContaining([expect.objectContaining({ value: 100.1, batch_id: "B01" })]),
    )

    // capability summary + rating badge (Cpk 1.34 appears as both headline + cell)
    expect(screen.getAllByText("1.34").length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText("1.68")).toBeInTheDocument() // Cpl cell (distinct value)
    expect(screen.getByText("capable")).toBeInTheDocument()
    expect(screen.getByText(/human review required/i)).toBeInTheDocument()
    // signals + alerts
    expect(screen.getByText(/6 points trending/)).toBeInTheDocument()
    expect(screen.getByText(/2 points out of specification/)).toBeInTheDocument()
    // disclaimer rendered verbatim, framed as decision-support not disposition
    expect(screen.getByText(DISCLAIMER)).toBeInTheDocument()
    expect(screen.getByText(/not a disposition/i)).toBeInTheDocument()
  })

  it("surfaces the early-warning lead banner when lead_points > 0", async () => {
    const user = userEvent.setup()
    mockApiFetch.mockResolvedValue(result({ lead_points: 6, first_signal_index: 12, first_oos_index: 18 }))
    render(<SPCProcessCapabilityPanel />)
    await user.click(screen.getByRole("button", { name: /Analyze series/ }))
    await waitFor(() =>
      expect(screen.getByText(/Early warning: 6 points of lead time/i)).toBeInTheDocument(),
    )
    // names the signal point (#13) and the first OOS point (#19)
    expect(screen.getByText(/point #13/)).toBeInTheDocument()
    expect(screen.getByText(/point #19/)).toBeInTheDocument()
  })

  it("warns on a drift signal with no spec breach yet (first_oos null)", async () => {
    const user = userEvent.setup()
    mockApiFetch.mockResolvedValue(
      result({ lead_points: 0, first_signal_index: 9, first_oos_index: null, oos_indices: [], alerts: [] }),
    )
    render(<SPCProcessCapabilityPanel />)
    await user.click(screen.getByRole("button", { name: /Analyze series/ }))
    await waitFor(() =>
      expect(screen.getByText(/Drift signal at point #10 — no spec breach yet/i)).toBeInTheDocument(),
    )
  })

  it("renders null capability indices as em-dashes and shows the zero-variation warning", async () => {
    const user = userEvent.setup()
    mockApiFetch.mockResolvedValue(
      result({
        capability: capability({
          cp: null,
          cpk: null,
          cpu: null,
          cpl: null,
          pp: null,
          ppk: null,
          cpm: null,
          sigma_within: 0,
          rating: "undefined",
          is_capable: false,
          interpretation: "Capability is undefined (zero within-variation).",
          warnings: ["zero within-variation: short-term capability is undefined/infinite"],
        }),
        spc_signals: [],
        alerts: [],
        oos_indices: [],
        first_signal_index: null,
        first_oos_index: null,
        lead_points: 0,
      }),
    )
    render(<SPCProcessCapabilityPanel />)
    await user.click(screen.getByRole("button", { name: /Analyze series/ }))
    await waitFor(() => expect(screen.getByTestId("spc-control-chart")).toBeInTheDocument())
    expect(screen.getByText("undefined")).toBeInTheDocument()
    expect(screen.getByText(/short-term capability is undefined\/infinite/i)).toBeInTheDocument()
    // capability cells fall back to em-dash, not "null"/"NaN"
    expect(screen.getAllByText("—").length).toBeGreaterThan(0)
    expect(screen.queryByText(/null|NaN/)).not.toBeInTheDocument()
  })
})
