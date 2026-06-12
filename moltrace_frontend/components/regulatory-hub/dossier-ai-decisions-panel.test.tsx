import { render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import {
  DossierAIDecisionsPanel,
  type AIDecision,
} from "@/components/regulatory-hub/dossier-ai-decisions-panel"

const mockApiFetch = vi.hoisted(() => vi.fn<(path: string, init?: unknown) => Promise<unknown>>())

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  apiFetch: (path: string, init?: unknown) => mockApiFetch(path, init),
}))

const CHECKLIST = {
  intended_use_documented: true,
  model_version_logged: true,
  confidence_calibrated: true,
  feature_attribution_computed: true,
  hitl_opportunity_for_high_risk: true,
  audit_trail_tamper_evident: true,
  regulatory_basis_cited: false,
}

function decision(overrides: Partial<AIDecision>): AIDecision {
  return {
    id: 1,
    dossier_id: 4,
    entry_hash: "sha256:f310e0230aaaa",
    previous_entry_hash: "sha256:000000000",
    timestamp_utc: "2026-06-12T00:00:00Z",
    user_id: "system",
    decision_type: "structure_elucidation",
    model_name: "nmrnet",
    model_version: "1.0.0",
    input_data_hash: "sha256:abc",
    confidence: 0.91,
    regulatory_basis: "EU GMP Draft Annex 22",
    risk_level: "high",
    hitl_required: true,
    hitl_approved: null,
    reviews_entry_hash: null,
    created_at: "2026-06-12T00:00:00Z",
    disclaimer: "Supports the direction of EU GMP DRAFT Annex 22 (July 2025); the Annex is not in force.",
    compliance_checklist: CHECKLIST,
    ...overrides,
  }
}

describe("DossierAIDecisionsPanel", () => {
  beforeEach(() => mockApiFetch.mockReset())

  it("shows the empty state when there are no decisions", () => {
    render(<DossierAIDecisionsPanel decisions={[]} dossierId={4} onReviewed={vi.fn()} />)
    expect(screen.getByText("No AI decisions recorded yet.")).toBeInTheDocument()
  })

  it("renders the draft disclaimer and never claims compliance", () => {
    render(<DossierAIDecisionsPanel decisions={[decision({})]} dossierId={4} onReviewed={vi.fn()} />)
    expect(screen.getByText("Draft guidance — not in force")).toBeInTheDocument()
    expect(screen.getByText(/Supports the direction of EU GMP DRAFT Annex 22/)).toBeInTheDocument()
    // never label anything "Annex 22 compliant"
    expect(screen.queryByText(/Annex 22 compliant/i)).not.toBeInTheDocument()
  })

  it("renders a decision with risk badge, confidence, and the 7-check compliance list", () => {
    render(<DossierAIDecisionsPanel decisions={[decision({})]} dossierId={4} onReviewed={vi.fn()} />)
    expect(screen.getByText("structure_elucidation")).toBeInTheDocument()
    expect(screen.getByText("high risk")).toBeInTheDocument()
    expect(screen.getByText("conf 91%")).toBeInTheDocument()
    expect(screen.getByText("intended use documented")).toBeInTheDocument()
    expect(screen.getByText("regulatory basis cited")).toBeInTheDocument()
  })

  it("shows the HITL gate for a pending high-risk decision and submits a review", async () => {
    const { default: userEvent } = await import("@testing-library/user-event")
    const user = userEvent.setup()
    const onReviewed = vi.fn()
    mockApiFetch.mockResolvedValue({})
    render(<DossierAIDecisionsPanel decisions={[decision({})]} dossierId={4} onReviewed={onReviewed} />)

    expect(screen.getByText("Pending human review")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Approve" }))

    await waitFor(() => expect(onReviewed).toHaveBeenCalled())
    expect(mockApiFetch).toHaveBeenCalledWith(
      "/regulatory/dossiers/4/ai-decisions/sha256%3Af310e0230aaaa/review",
      expect.objectContaining({ method: "POST", body: expect.objectContaining({ approved: true }) }),
    )
  })

  it("associates a .hitl_review row with its decision and shows the verdict (not pending)", () => {
    const reviewed = decision({ entry_hash: "sha256:f310e0230aaaa", hitl_approved: null })
    const reviewRow = decision({
      id: 2,
      decision_type: "structure_elucidation.hitl_review",
      entry_hash: "sha256:review999",
      reviews_entry_hash: "sha256:f310e0230aaaa",
      hitl_approved: true,
      user_id: "reviewer-1",
    })
    render(<DossierAIDecisionsPanel decisions={[reviewRow, reviewed]} dossierId={4} onReviewed={vi.fn()} />)
    // review row is filtered out of the main list; verdict shows on the decision
    expect(screen.getByText(/approved · reviewer-1/)).toBeInTheDocument()
    expect(screen.queryByText("Pending human review")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument()
    // only one decision card (the .hitl_review row is not rendered as a card)
    expect(screen.getAllByText(/structure_elucidation$/).length).toBe(1)
  })

  it("verifies the chain and shows the ok state", async () => {
    const { default: userEvent } = await import("@testing-library/user-event")
    const user = userEvent.setup()
    mockApiFetch.mockResolvedValue({ ok: true, count: 2, breaks: [] })
    render(<DossierAIDecisionsPanel decisions={[decision({})]} dossierId={4} onReviewed={vi.fn()} />)

    await user.click(screen.getByRole("button", { name: /Verify chain/ }))
    await waitFor(() => expect(screen.getByText(/chain verified · 2 entries/)).toBeInTheDocument())
  })
})
