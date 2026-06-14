import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { MfaChallengeForm } from "@/components/marketing/mfa-challenge-form"

const mfa = vi.hoisted(() => ({
  loginWithTotp: vi.fn(),
  loginWithRecovery: vi.fn(),
  loginWithPasskey: vi.fn(),
  browserSupportsWebAuthn: vi.fn(() => true),
}))
vi.mock("@/lib/auth/mfa", () => mfa)

beforeEach(() => {
  mfa.loginWithRecovery.mockReset()
  mfa.loginWithPasskey.mockReset()
  mfa.browserSupportsWebAuthn.mockReturnValue(true)
})

describe("MfaChallengeForm", () => {
  it("verifies with a passkey when webauthn is offered", async () => {
    const user = userEvent.setup()
    mfa.loginWithPasskey.mockResolvedValue({ access_token: "t" })
    const onSuccess = vi.fn()
    render(
      <MfaChallengeForm
        challenge={{ mfa_required: true, mfa_token: "mt", factors: ["webauthn"], webauthn_options: { a: 1 } }}
        onSuccess={onSuccess}
      />,
    )
    await user.click(screen.getByRole("button", { name: /Verify with passkey/ }))
    await waitFor(() => expect(onSuccess).toHaveBeenCalled())
    expect(mfa.loginWithPasskey).toHaveBeenCalledWith("mt", { a: 1 })
  })

  it("falls back to a recovery code via the method switcher", async () => {
    const user = userEvent.setup()
    mfa.loginWithRecovery.mockResolvedValue({ access_token: "t" })
    const onSuccess = vi.fn()
    render(
      <MfaChallengeForm
        challenge={{ mfa_required: true, mfa_token: "mt", factors: ["totp", "recovery"], webauthn_options: null }}
        onSuccess={onSuccess}
      />,
    )
    await user.click(screen.getByRole("button", { name: /recovery code/ }))
    await user.type(screen.getByLabelText("Recovery code"), "abcde-fghij")
    await user.click(screen.getByRole("button", { name: "Verify" }))
    await waitFor(() => expect(onSuccess).toHaveBeenCalled())
    expect(mfa.loginWithRecovery).toHaveBeenCalledWith("mt", "abcde-fghij")
  })
})
