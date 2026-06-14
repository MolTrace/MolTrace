import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { MfaPolicyPanel } from "@/components/admin/mfa-policy-panel"

const mfa = vi.hoisted(() => ({
  getMfaPolicy: vi.fn(),
  setMfaPolicy: vi.fn(),
  isStepUpRequired: () => false, // withStepUp imports this
}))
vi.mock("@/lib/auth/mfa", () => mfa)
vi.mock("@/components/auth/step-up-provider", () => ({
  useStepUp: () => ({ ensureStepUp: vi.fn().mockResolvedValue(true) }),
}))

const POLICY = {
  organization_id: 1,
  mfa_required: false,
  grace_period_days: 7,
  allowed_factors: ["totp", "webauthn"],
  enforce_for_sso: false,
  require_step_up_for_signing: true,
}

beforeEach(() => {
  mfa.getMfaPolicy.mockReset()
  mfa.setMfaPolicy.mockReset()
})

describe("MfaPolicyPanel", () => {
  it("loads the policy and saves an update with the edited body", async () => {
    const user = userEvent.setup()
    mfa.getMfaPolicy.mockResolvedValue(POLICY)
    mfa.setMfaPolicy.mockResolvedValue({ ...POLICY, mfa_required: true })
    render(<MfaPolicyPanel organizationId={1} />)

    await waitFor(() => expect(screen.getByLabelText("Grace period (days)")).toHaveValue("7"))
    await user.click(screen.getByRole("switch", { name: /All members must enrol/ }))
    await user.click(screen.getByRole("button", { name: "Save policy" }))

    await waitFor(() => expect(mfa.setMfaPolicy).toHaveBeenCalled())
    const [, body] = mfa.setMfaPolicy.mock.calls[0]
    expect(body).toMatchObject({
      mfa_required: true,
      grace_period_days: 7,
      allowed_factors: ["totp", "webauthn"],
      enforce_for_sso: false,
      require_step_up_for_signing: true,
    })
    expect(screen.getByText("MFA policy saved.")).toBeInTheDocument()
  })

  it("rejects a negative grace period without calling the API", async () => {
    const user = userEvent.setup()
    mfa.getMfaPolicy.mockResolvedValue(POLICY)
    render(<MfaPolicyPanel organizationId={1} />)
    await waitFor(() => expect(screen.getByLabelText("Grace period (days)")).toBeInTheDocument())

    const grace = screen.getByLabelText("Grace period (days)")
    await user.clear(grace)
    await user.type(grace, "-3")
    await user.click(screen.getByRole("button", { name: "Save policy" }))

    expect(screen.getByText(/non-negative whole number/i)).toBeInTheDocument()
    expect(mfa.setMfaPolicy).not.toHaveBeenCalled()
  })
})
