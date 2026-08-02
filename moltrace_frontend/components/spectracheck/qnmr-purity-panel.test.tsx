import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { QnmrPurityPanel } from "@/components/spectracheck/qnmr-purity-panel"

const mockApiFetch = vi.hoisted(() => vi.fn<(path: string, init?: unknown) => Promise<unknown>>())

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  apiFetch: (path: string, init?: unknown) => mockApiFetch(path, init),
}))

// Captured verbatim from the running backend, so the panel is tested against
// the shape the routes actually return rather than an invented one.
const INTERNAL_STANDARD_RESULT = {
  purity_percent: 100.0,
  uncertainty_percent: 1.4213,
  relative_uncertainty: 0.014213,
  method: "internal_standard",
  inputs: {
    analyte_integral: 2.0,
    standard_integral: 1.0,
    analyte_protons: 2,
    standard_protons: 1,
    analyte_molar_mass: 100.0,
    standard_molar_mass: 100.0,
    analyte_mass_mg: 10.0,
    standard_mass_mg: 10.0,
    standard_purity_percent: 100.0,
    integral_rel_u: 0.01,
    mass_rel_u: 0.001,
    standard_purity_rel_u: 0.0,
    molar_mass_rel_u: 0.0,
  },
  intermediates: {
    ratio_integral: 2.0,
    ratio_protons: 0.5,
    ratio_molar_mass: 1.0,
    ratio_mass: 1.0,
    standard_purity_percent: 100.0,
  },
  warnings: [],
  notes: [
    "Purity is computed from the integrals you supply; it is only as good as the integration and the weighing behind them.",
    "The reported uncertainty is a combined standard uncertainty (k = 1) propagated from the supplied relative uncertainties. Supply your own to make it your laboratory's estimate.",
    "Decision support for human review — not a certificate of analysis.",
  ],
}

const PULCON_RESULT = {
  ...INTERNAL_STANDARD_RESULT,
  uncertainty_percent: 2.1213,
  relative_uncertainty: 0.021213,
  method: "pulcon",
  intermediates: {
    reference_concentration_true: 10.0,
    ratio_signal_per_spin: 1.0,
    ratio_pulse_width: 1.0,
    correction: 1.0,
    measured_concentration: 10.0,
    nominal_concentration: 10.0,
  },
}

/** The eight numbers of the routine determination — this set returns 100 %. */
const INTERNAL_STANDARD_ENTRY: [string, string][] = [
  ["Analyte Integral", "2"],
  ["Analyte Protons (N)", "2"],
  ["Analyte Molar mass (g/mol)", "100"],
  ["Analyte Mass weighed (mg)", "10"],
  ["Internal standard Integral", "1"],
  ["Internal standard Protons (N)", "1"],
  ["Internal standard Molar mass (g/mol)", "100"],
  ["Internal standard Mass weighed (mg)", "10"],
]

const PULCON_ENTRY: [string, string][] = [
  ["Analyte Integral", "2"],
  ["Analyte Protons (N)", "2"],
  ["Analyte Nominal concentration", "10"],
  ["External reference Integral", "1"],
  ["External reference Protons (N)", "1"],
  ["External reference Concentration", "10"],
]

async function fillAll(user: ReturnType<typeof userEvent.setup>, entries: [string, string][]) {
  for (const [label, value] of entries) {
    await user.type(screen.getByLabelText(label), value)
  }
}

function lastBody(): Record<string, unknown> {
  const call = mockApiFetch.mock.calls.at(-1)
  return (call?.[1] as { body: Record<string, unknown> }).body
}

describe("qNMR purity panel", () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  it("blocks the determination until every required number is present", async () => {
    const user = userEvent.setup()
    render(<QnmrPurityPanel />)

    const button = screen.getByRole("button", { name: /Determine purity/i })
    expect(button).toBeDisabled()
    expect(screen.getByText(/8 values still needed/i)).toBeInTheDocument()

    await fillAll(user, INTERNAL_STANDARD_ENTRY)

    expect(button).toBeEnabled()
    expect(mockApiFetch).not.toHaveBeenCalled()
  })

  it("posts only the canonical keys and omits untouched uncertainty inputs", async () => {
    const user = userEvent.setup()
    mockApiFetch.mockImplementationOnce(() => Promise.resolve(INTERNAL_STANDARD_RESULT))
    render(<QnmrPurityPanel />)

    await fillAll(user, INTERNAL_STANDARD_ENTRY)
    await user.click(screen.getByRole("button", { name: /Determine purity/i }))

    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(1))
    expect(mockApiFetch.mock.calls[0][0]).toBe("/spectrum/qnmr/purity")
    // Both request models are ``extra="forbid"`` — an unrecognised key is a 422,
    // so the posted key set is pinned exactly.
    expect(Object.keys(lastBody()).sort()).toEqual(
      [
        "analyte_integral",
        "analyte_mass_mg",
        "analyte_molar_mass",
        "analyte_protons",
        "standard_integral",
        "standard_mass_mg",
        "standard_molar_mass",
        "standard_protons",
        "standard_purity_percent",
      ].sort(),
    )
    // Untouched uncertainty terms are absent, not zero: 0 would claim perfect
    // measurement and report an uncertainty far tighter than the lab can justify.
    expect(lastBody()).not.toHaveProperty("integral_rel_u")
    expect(lastBody()).not.toHaveProperty("mass_rel_u")
    expect(lastBody()).not.toHaveProperty("standard_purity_rel_u")
    expect(lastBody()).not.toHaveProperty("molar_mass_rel_u")
    expect(lastBody().standard_purity_percent).toBe(100)
  })

  it("sends a laboratory's own uncertainty inputs when supplied", async () => {
    const user = userEvent.setup()
    mockApiFetch.mockImplementationOnce(() => Promise.resolve(INTERNAL_STANDARD_RESULT))
    render(<QnmrPurityPanel />)

    await fillAll(user, INTERNAL_STANDARD_ENTRY)
    await user.click(screen.getByRole("button", { name: /Uncertainty inputs/i }))
    await user.type(screen.getByLabelText("Integral relative uncertainty"), "0.003")
    await user.type(screen.getByLabelText("Weighing relative uncertainty"), "0.0005")
    await user.click(screen.getByRole("button", { name: /Determine purity/i }))

    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(1))
    expect(lastBody().integral_rel_u).toBe(0.003)
    expect(lastBody().mass_rel_u).toBe(0.0005)
    // The two the lab did not supply stay absent so the engine default applies.
    expect(lastBody()).not.toHaveProperty("standard_purity_rel_u")
    expect(lastBody()).not.toHaveProperty("molar_mass_rel_u")
  })

  it("never renders the purity without its uncertainty", async () => {
    const user = userEvent.setup()
    mockApiFetch.mockImplementationOnce(() => Promise.resolve(INTERNAL_STANDARD_RESULT))
    render(<QnmrPurityPanel />)

    await fillAll(user, INTERNAL_STANDARD_ENTRY)
    await user.click(screen.getByRole("button", { name: /Determine purity/i }))

    const figure = await screen.findByTestId("qnmr-purity-figure")
    expect(figure).toHaveTextContent("100.00 ± 1.42 %")
    expect(screen.getByText(/Combined standard uncertainty at k\s*=\s*1/i)).toBeInTheDocument()
  })

  it("states a missing uncertainty rather than presenting the figure alone", async () => {
    const user = userEvent.setup()
    mockApiFetch.mockImplementationOnce(() =>
      Promise.resolve({
        ...INTERNAL_STANDARD_RESULT,
        uncertainty_percent: Number.NaN,
        relative_uncertainty: Number.NaN,
      }),
    )
    render(<QnmrPurityPanel />)

    await fillAll(user, INTERNAL_STANDARD_ENTRY)
    await user.click(screen.getByRole("button", { name: /Determine purity/i }))

    const figure = await screen.findByTestId("qnmr-purity-figure")
    expect(figure).toHaveTextContent("± unavailable")
    expect(
      screen.getByText(/purity figure alone is not a determination/i),
    ).toBeInTheDocument()
  })

  it("surfaces the derivation and the applied uncertainty budget", async () => {
    const user = userEvent.setup()
    mockApiFetch.mockImplementationOnce(() => Promise.resolve(INTERNAL_STANDARD_RESULT))
    render(<QnmrPurityPanel />)

    await fillAll(user, INTERNAL_STANDARD_ENTRY)
    await user.click(screen.getByRole("button", { name: /Determine purity/i }))
    await screen.findByTestId("qnmr-purity-figure")

    await user.click(screen.getByRole("button", { name: /Derivation/i }))

    // Every intermediate ratio the engine returned is reachable.
    for (const key of Object.keys(INTERNAL_STANDARD_RESULT.intermediates)) {
      expect(screen.getAllByText(key).length).toBeGreaterThan(0)
    }
    expect(screen.getByText(/Intermediate ratios/i)).toBeInTheDocument()
    expect(screen.getByText(/Inputs as received/i)).toBeInTheDocument()
    // Task 4: the budget actually used comes back from the response, so the
    // engine's defaults are visible rather than assumed.
    expect(screen.getByText(/Uncertainty budget applied/i)).toBeInTheDocument()
    const budget = screen.getByText(/Uncertainty budget applied/i).closest("div")
    expect(within(budget as HTMLElement).getByText("integral_rel_u")).toBeInTheDocument()
  })

  it("renders engine warnings above the figure and the notes verbatim", async () => {
    const user = userEvent.setup()
    const warning =
      "Computed purity 200.00% exceeds 100% — re-check proton counts, weighed masses, and that the integrals are baseline-resolved."
    mockApiFetch.mockImplementationOnce(() =>
      Promise.resolve({ ...INTERNAL_STANDARD_RESULT, purity_percent: 200.0, warnings: [warning] }),
    )
    render(<QnmrPurityPanel />)

    await fillAll(user, INTERNAL_STANDARD_ENTRY)
    await user.click(screen.getByRole("button", { name: /Determine purity/i }))

    const warningNode = await screen.findByText(warning)
    expect(warningNode).toBeInTheDocument()
    // A warning that means "the inputs are wrong" precedes the number it invalidates.
    const figure = screen.getByTestId("qnmr-purity-figure")
    expect(warningNode.compareDocumentPosition(figure) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    for (const note of INTERNAL_STANDARD_RESULT.notes) {
      expect(screen.getByText(note)).toBeInTheDocument()
    }
    // Not a certificate of analysis, and nothing is stored.
    expect(screen.getByText(/not stored/i)).toBeInTheDocument()
  })

  it("routes PULCON to its own path with the acquisition terms defaulted", async () => {
    const user = userEvent.setup()
    mockApiFetch.mockImplementationOnce(() => Promise.resolve(PULCON_RESULT))
    render(<QnmrPurityPanel />)

    await user.click(screen.getByRole("radio", { name: "PULCON" }))
    await fillAll(user, PULCON_ENTRY)
    await user.click(screen.getByRole("button", { name: /Determine purity/i }))

    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(1))
    expect(mockApiFetch.mock.calls[0][0]).toBe("/spectrum/qnmr/purity/pulcon")
    const body = lastBody()
    // Untouched acquisition terms carry the schema defaults, so each ratio
    // cancels and the routine case is a plain ratio-based answer.
    expect(body.analyte_pulse_width_us).toBe(1)
    expect(body.reference_pulse_width_us).toBe(1)
    expect(body.analyte_temperature_k).toBe(298.15)
    expect(body.reference_temperature_k).toBe(298.15)
    expect(body.analyte_receiver_gain).toBe(1)
    expect(body.reference_receiver_gain).toBe(1)
    expect(body.analyte_scans).toBe(1)
    expect(body.reference_scans).toBe(1)
    expect(body.reference_purity_percent).toBe(100)
    expect(body).not.toHaveProperty("standard_integral")
    expect(body).not.toHaveProperty("pulse_width_rel_u")
  })

  it("clears a stale determination as soon as an input changes", async () => {
    const user = userEvent.setup()
    mockApiFetch.mockImplementationOnce(() => Promise.resolve(INTERNAL_STANDARD_RESULT))
    render(<QnmrPurityPanel />)

    await fillAll(user, INTERNAL_STANDARD_ENTRY)
    await user.click(screen.getByRole("button", { name: /Determine purity/i }))
    await screen.findByTestId("qnmr-purity-figure")

    await user.type(screen.getByLabelText("Analyte Integral"), "5")

    // A purity figure must never sit next to numbers that did not produce it.
    expect(screen.queryByTestId("qnmr-purity-figure")).not.toBeInTheDocument()
  })

  it("reports a failed determination instead of leaving the panel blank", async () => {
    const user = userEvent.setup()
    mockApiFetch.mockImplementationOnce(() => Promise.reject(new Error("Service unavailable")))
    render(<QnmrPurityPanel />)

    await fillAll(user, INTERNAL_STANDARD_ENTRY)
    await user.click(screen.getByRole("button", { name: /Determine purity/i }))

    expect(await screen.findByText(/Purity determination failed/i)).toBeInTheDocument()
    expect(screen.queryByTestId("qnmr-purity-figure")).not.toBeInTheDocument()
  })
})
