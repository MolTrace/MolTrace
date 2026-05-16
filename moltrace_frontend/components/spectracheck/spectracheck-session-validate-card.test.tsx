import { describe, expect, it, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

import { SessionValidateCard } from "@/components/spectracheck/spectracheck-session-validate-card"

const apiFetchMock = vi.fn()

vi.mock("@/lib/api/client", () => ({
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
  ApiError: class ApiError extends Error {
    status: number
    data: unknown
    constructor(status: number, data: unknown, message?: string) {
      super(message ?? String(status))
      this.status = status
      this.data = data
    }
  },
  // formatApiError (used inside the validate card to surface network failures)
  // calls sanitizePublicApiErrorMessage — preserve that export so the test
  // mock matches the real module's public surface.
  sanitizePublicApiErrorMessage: (msg: string) => msg,
}))

const DEFAULT_CANDIDATES = `Methanol | CO | starting material
Ethanol | CCO | proposed
Propanol | CCCO | possible impurity`

const DEFAULT_PROTON =
  "1H NMR (400 MHz, CDCl3) δ 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"

const DEFAULT_CARBON = "13C NMR (101 MHz, CDCl3) δ 58.3, 18.2."

const DEFAULTS = {
  candidates: DEFAULT_CANDIDATES,
  proton: DEFAULT_PROTON,
  carbon: DEFAULT_CARBON,
}

/** Backend ``ValidationReport`` shape — kept inline so the test asserts on
 * the exact wire contract the frontend must keep consuming. */
type ValidationReport = {
  sample_id: string | null
  solvent: string | null
  structure_valid: boolean
  nmr_text_valid: boolean
  structure_nmr_match: boolean
  analysis_ready: boolean
  parseable_peak_count: number
  expected_visible_h: number | null
  observed_total_h: number | null
  adjusted_observed_total_h: number | null
  delta_visible_h: number | null
  parsed_peaks: unknown[]
  structure: unknown | null
  warnings: string[]
  errors: string[]
}

function makeReport(overrides: Partial<ValidationReport>): ValidationReport {
  return {
    sample_id: null,
    solvent: null,
    structure_valid: false,
    nmr_text_valid: false,
    structure_nmr_match: false,
    analysis_ready: false,
    parseable_peak_count: 0,
    expected_visible_h: null,
    observed_total_h: null,
    adjusted_observed_total_h: null,
    delta_visible_h: null,
    parsed_peaks: [],
    structure: null,
    warnings: [],
    errors: [],
    ...overrides,
  }
}

describe("SessionValidateCard — default vs modified detection", () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it("renders the 'Example data' chip on every input when textareas hold the bundled defaults", () => {
    render(
      <SessionValidateCard
        sampleId="SAMPLE-001"
        solvent="CDCl3"
        candidatesText={DEFAULT_CANDIDATES}
        protonText={DEFAULT_PROTON}
        carbonText={DEFAULT_CARBON}
        defaults={DEFAULTS}
      />,
    )
    // All three field-status pills must read "Example data"
    expect(screen.getAllByTestId("session-field-status-default")).toHaveLength(3)
    expect(screen.queryByTestId("session-field-status-modified")).toBeNull()
    expect(screen.getByTestId("session-validate-default-hint")).toBeInTheDocument()
  })

  it("switches a pill to 'Your data' when the user modifies the matching textarea", () => {
    render(
      <SessionValidateCard
        sampleId="SAMPLE-001"
        solvent="CDCl3"
        candidatesText="My compound | C1=CC=CC=C1"
        protonText={DEFAULT_PROTON}
        carbonText={DEFAULT_CARBON}
        defaults={DEFAULTS}
      />,
    )
    expect(screen.getAllByTestId("session-field-status-default")).toHaveLength(2)
    expect(screen.getAllByTestId("session-field-status-modified")).toHaveLength(1)
    // "Heads up" example hint disappears as soon as one field is user-modified.
    expect(screen.queryByTestId("session-validate-default-hint")).toBeNull()
  })

  it("renders the 'Empty' status when a textarea is blank", () => {
    render(
      <SessionValidateCard
        sampleId="SAMPLE-001"
        solvent="CDCl3"
        candidatesText=""
        protonText={DEFAULT_PROTON}
        carbonText=""
        defaults={DEFAULTS}
      />,
    )
    expect(screen.getAllByTestId("session-field-status-empty")).toHaveLength(2)
  })
})

describe("SessionValidateCard — backend roundtrip", () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it("posts JSON to /analyze/validate using the first SMILES + 1H text + solvent", async () => {
    apiFetchMock.mockResolvedValueOnce(
      makeReport({
        structure_valid: true,
        nmr_text_valid: true,
        structure_nmr_match: true,
        analysis_ready: true,
        expected_visible_h: 5,
        observed_total_h: 5,
        adjusted_observed_total_h: 5,
        delta_visible_h: 0,
        parseable_peak_count: 3,
      }),
    )
    const user = userEvent.setup()
    render(
      <SessionValidateCard
        sampleId="My Sample"
        solvent="CDCl3"
        candidatesText="Ethanol | CCO"
        protonText={DEFAULT_PROTON}
        carbonText=""
        defaults={DEFAULTS}
      />,
    )
    await user.click(screen.getByTestId("session-validate-button"))

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(1))
    const [path, init] = apiFetchMock.mock.calls[0]
    expect(path).toBe("/analyze/validate")
    expect(init?.method).toBe("POST")
    // Body is a plain object — apiFetch will JSON.stringify it.
    const body = init?.body as Record<string, unknown>
    expect(body.smiles).toBe("CCO")
    expect(body.nmr_text).toBe(DEFAULT_PROTON)
    expect(body.solvent).toBe("CDCl3")
    expect(body.sample_id).toBe("My Sample")
  })

  it("renders the 'analysis ready' state on a fully-matching response", async () => {
    apiFetchMock.mockResolvedValueOnce(
      makeReport({
        structure_valid: true,
        nmr_text_valid: true,
        structure_nmr_match: true,
        analysis_ready: true,
        expected_visible_h: 5,
        observed_total_h: 5,
        adjusted_observed_total_h: 5,
        delta_visible_h: 0,
      }),
    )
    const user = userEvent.setup()
    render(
      <SessionValidateCard
        sampleId="SAMPLE-001"
        solvent="CDCl3"
        candidatesText="Ethanol | CCO"
        protonText={DEFAULT_PROTON}
        carbonText=""
        defaults={DEFAULTS}
      />,
    )
    await user.click(screen.getByTestId("session-validate-button"))

    const result = await screen.findByTestId("session-validate-result")
    expect(result.dataset.state).toBe("passed")
    expect(screen.getByText(/Validation passed/i)).toBeInTheDocument()
    expect(screen.getByTestId("structure-chip").dataset.state).toBe("ok")
    expect(screen.getByTestId("nmr-text-chip").dataset.state).toBe("ok")
    expect(screen.getByTestId("match-chip").dataset.state).toBe("ok")
  })

  it("renders 'Validation failed' with the backend errors when SMILES ↔ NMR disagree", async () => {
    apiFetchMock.mockResolvedValueOnce(
      makeReport({
        structure_valid: true,
        nmr_text_valid: true,
        structure_nmr_match: false,
        analysis_ready: false,
        errors: ["Observed total H exceeds expected visible H by 4.0; integrations are inconsistent."],
        warnings: [],
      }),
    )
    const user = userEvent.setup()
    render(
      <SessionValidateCard
        sampleId="SAMPLE-001"
        solvent="CDCl3"
        candidatesText="Ethanol | CCO"
        protonText="1H NMR (CDCl3) δ 7.5 (m, 9H)"
        carbonText=""
        defaults={DEFAULTS}
      />,
    )
    await user.click(screen.getByTestId("session-validate-button"))

    const result = await screen.findByTestId("session-validate-result")
    expect(result.dataset.state).toBe("failed")
    expect(screen.getByTestId("match-chip").dataset.state).toBe("fail")
    expect(screen.getByTestId("session-validate-errors")).toHaveTextContent(
      /Observed total H exceeds expected visible H/i,
    )
  })

  it("renders 'Partial inputs' status when only SMILES is supplied", async () => {
    apiFetchMock.mockResolvedValueOnce(
      makeReport({
        structure_valid: true,
        nmr_text_valid: false,
        structure_nmr_match: false,
        analysis_ready: false,
        warnings: ["Enter 1H NMR text before running analysis."],
      }),
    )
    const user = userEvent.setup()
    render(
      <SessionValidateCard
        sampleId="SAMPLE-001"
        solvent="CDCl3"
        candidatesText="Ethanol | CCO"
        protonText=""
        carbonText=""
        defaults={DEFAULTS}
      />,
    )
    await user.click(screen.getByTestId("session-validate-button"))

    const result = await screen.findByTestId("session-validate-result")
    expect(result.dataset.state).toBe("partial")
    expect(screen.getByText(/can still proceed/i)).toBeInTheDocument()
    expect(screen.getByTestId("structure-chip").dataset.state).toBe("ok")
    expect(screen.getByTestId("nmr-text-chip").dataset.state).toBe("missing")
    expect(screen.getByTestId("match-chip").dataset.state).toBe("na")
  })

  it("renders 'Partial inputs' status when only 1H NMR text is supplied", async () => {
    apiFetchMock.mockResolvedValueOnce(
      makeReport({
        structure_valid: false,
        nmr_text_valid: true,
        structure_nmr_match: false,
        analysis_ready: false,
        parseable_peak_count: 3,
        warnings: ["Enter a SMILES structure before running analysis."],
      }),
    )
    const user = userEvent.setup()
    render(
      <SessionValidateCard
        sampleId="SAMPLE-001"
        solvent="CDCl3"
        candidatesText=""
        protonText={DEFAULT_PROTON}
        carbonText=""
        defaults={DEFAULTS}
      />,
    )
    await user.click(screen.getByTestId("session-validate-button"))

    const result = await screen.findByTestId("session-validate-result")
    expect(result.dataset.state).toBe("partial")
    expect(screen.getByTestId("structure-chip").dataset.state).toBe("missing")
    expect(screen.getByTestId("nmr-text-chip").dataset.state).toBe("ok")
  })

  it("surfaces network errors without crashing", async () => {
    apiFetchMock.mockRejectedValueOnce(new Error("network down"))
    const user = userEvent.setup()
    render(
      <SessionValidateCard
        sampleId="SAMPLE-001"
        solvent="CDCl3"
        candidatesText="Ethanol | CCO"
        protonText={DEFAULT_PROTON}
        carbonText=""
        defaults={DEFAULTS}
      />,
    )
    await user.click(screen.getByTestId("session-validate-button"))

    await waitFor(() =>
      expect(screen.getByTestId("session-validate-network-error")).toBeInTheDocument(),
    )
    expect(screen.queryByTestId("session-validate-result")).toBeNull()
  })

  it("validation never gates downstream analysis — button stays enabled after a failure", async () => {
    apiFetchMock.mockResolvedValueOnce(
      makeReport({
        structure_valid: true,
        nmr_text_valid: true,
        structure_nmr_match: false,
        errors: ["mismatch"],
      }),
    )
    const user = userEvent.setup()
    render(
      <SessionValidateCard
        sampleId="SAMPLE-001"
        solvent="CDCl3"
        candidatesText="Ethanol | CCO"
        protonText={DEFAULT_PROTON}
        carbonText=""
        defaults={DEFAULTS}
      />,
    )
    await user.click(screen.getByTestId("session-validate-button"))
    await screen.findByTestId("session-validate-result")
    // Button is still clickable so the user can re-validate after editing.
    expect(screen.getByTestId("session-validate-button")).not.toBeDisabled()
  })
})
