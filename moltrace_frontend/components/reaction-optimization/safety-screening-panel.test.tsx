import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { SafetyScreeningPanel } from "@/components/reaction-optimization/safety-screening-panel"
import type { SafetyGate, SafetyScreening } from "@/lib/reaction/safety-screenings"

const api = vi.hoisted(() => ({
  getSafetyGate: vi.fn(),
  listScreenings: vi.fn(),
  createScreening: vi.fn(),
  reviewScreening: vi.fn(),
}))

// Partial mock — keep the real parsers + style maps; stub the network calls.
vi.mock("@/lib/reaction/safety-screenings", async (orig) => ({
  ...(await orig<typeof import("@/lib/reaction/safety-screenings")>()),
  getSafetyGate: (...a: unknown[]) => api.getSafetyGate(...a),
  listScreenings: (...a: unknown[]) => api.listScreenings(...a),
  createScreening: (...a: unknown[]) => api.createScreening(...a),
  reviewScreening: (...a: unknown[]) => api.reviewScreening(...a),
}))

const SCREENING: SafetyScreening = {
  id: 1,
  reactionProjectId: 4,
  label: "Step 3 azide displacement",
  overallRisk: "critical",
  requiresExpertReview: true,
  reviewStatus: "pending",
  reviewNote: null,
  reviewedByUserId: null,
  reviewedAt: null,
  createdAt: "2026-06-16T00:00:00Z",
  disclaimer: "Decision-support only; NOT a safety determination.",
  species: [
    {
      role: "reactant",
      smiles: "CCN=[N+]=[N-]",
      parsed: true,
      overallRisk: "critical",
      flaggedGroups: [
        { key: "azide", label: "Organic azide", severity: "critical", count: 1, mitigation: "Keep dilute and cold." },
      ],
    },
  ],
  energeticGroupsFound: ["azide"],
  inputJson: {},
}

const GATE_PENDING: SafetyGate = {
  reactionProjectId: 4,
  status: "review_pending",
  screeningsTotal: 1,
  blockingScreeningIds: [1],
  summary: "1 screening(s) await expert review before execution.",
}
const GATE_CLEAR: SafetyGate = {
  reactionProjectId: 4,
  status: "clear",
  screeningsTotal: 0,
  blockingScreeningIds: [],
  summary: "No screenings require review.",
}

beforeEach(() => {
  api.getSafetyGate.mockReset().mockResolvedValue(GATE_CLEAR)
  api.listScreenings.mockReset().mockResolvedValue([])
  api.createScreening.mockReset().mockResolvedValue(SCREENING)
  api.reviewScreening.mockReset().mockResolvedValue({ ...SCREENING, reviewStatus: "approved" })
})

describe("SafetyScreeningPanel", () => {
  it("renders the gate banner + summary + blocking link, and always shows the disclaimer", async () => {
    api.getSafetyGate.mockResolvedValue(GATE_PENDING)
    api.listScreenings.mockResolvedValue([SCREENING])
    render(<SafetyScreeningPanel projectId={4} />)
    await waitFor(() => expect(screen.getByText(/expert review pending/i)).toBeInTheDocument())
    expect(screen.getByText(/await expert review before execution/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "#1" })).toBeInTheDocument() // blocking quick-link
    expect(screen.getByText("Decision-support only; NOT a safety determination.")).toBeInTheDocument() // standing disclaimer (collapsed row)
  })

  it("lists a screening and reveals its flagged groups + mitigation on expand", async () => {
    const user = userEvent.setup()
    api.listScreenings.mockResolvedValue([SCREENING])
    render(<SafetyScreeningPanel projectId={4} />)
    await waitFor(() => expect(screen.getByText("Step 3 azide displacement")).toBeInTheDocument())

    await user.click(screen.getByText("Step 3 azide displacement"))
    const row = screen.getByTestId("screening-1")
    expect(within(row).getByText("Organic azide")).toBeInTheDocument()
    expect(within(row).getByText(/Keep dilute and cold/i)).toBeInTheDocument()
  })

  it("runs a screen with the entered SMILES", async () => {
    const user = userEvent.setup()
    render(<SafetyScreeningPanel projectId={4} />)
    await waitFor(() => expect(api.listScreenings).toHaveBeenCalledWith(4))

    await user.click(screen.getByText("Run a safety screen")) // open the collapsible
    await user.type(screen.getByLabelText(/Reactant SMILES/i), "CCO")
    await user.click(screen.getByRole("button", { name: /Run safety screen/i }))

    await waitFor(() => expect(api.createScreening).toHaveBeenCalled())
    const call = api.createScreening.mock.calls[0]
    expect(call[0]).toBe(4)
    expect(call[1]).toMatchObject({ reactant_smiles: ["CCO"] })
  })

  it("submits an approve review with the required note for a pending screening", async () => {
    const user = userEvent.setup()
    api.listScreenings.mockResolvedValue([SCREENING])
    render(<SafetyScreeningPanel projectId={4} />)
    await waitFor(() => expect(screen.getByText("Step 3 azide displacement")).toBeInTheDocument())
    await user.click(screen.getByText("Step 3 azide displacement"))

    const approve = screen.getByRole("button", { name: /Approve/i })
    expect(approve).toBeDisabled() // requires a note first
    await user.type(screen.getByLabelText(/Expert review note/i), "PHA complete.")
    await user.click(approve)

    await waitFor(() => expect(api.reviewScreening).toHaveBeenCalledWith(4, 1, { decision: "approved", note: "PHA complete." }))
  })
})
