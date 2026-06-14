import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { StepUpProvider, useStepUp } from "@/components/auth/step-up-provider"

const mfa = vi.hoisted(() => ({
  getStepUpOptions: vi.fn(),
  stepUpWithPassword: vi.fn(),
  stepUpWithTotp: vi.fn(),
  stepUpWithPasskey: vi.fn(),
  browserSupportsWebAuthn: vi.fn(() => true),
}))
vi.mock("@/lib/auth/mfa", () => mfa)

function Harness({ onResult }: { onResult: (v: boolean) => void }) {
  const { ensureStepUp } = useStepUp()
  return (
    <button type="button" onClick={async () => onResult(await ensureStepUp())}>
      trigger
    </button>
  )
}

describe("StepUpProvider", () => {
  beforeEach(() => {
    mfa.getStepUpOptions.mockReset()
    mfa.stepUpWithPassword.mockReset()
    mfa.browserSupportsWebAuthn.mockReturnValue(true)
  })

  it("runs a password step-up and resolves the ensureStepUp promise true", async () => {
    const user = userEvent.setup()
    mfa.getStepUpOptions.mockResolvedValue({ factors: ["password"] })
    mfa.stepUpWithPassword.mockResolvedValue({ stepped_up: true, factor: "password", aal: "aal1", expires_at: "z" })
    const onResult = vi.fn()
    render(
      <StepUpProvider>
        <Harness onResult={onResult} />
      </StepUpProvider>,
    )

    await user.click(screen.getByRole("button", { name: "trigger" }))
    const pw = await screen.findByLabelText("Password")
    await user.type(pw, "hunter2")
    await user.click(screen.getByRole("button", { name: "Verify" }))

    await waitFor(() => expect(onResult).toHaveBeenCalledWith(true))
    expect(mfa.stepUpWithPassword).toHaveBeenCalledWith("hunter2")
  })

  it("resolves false when the ceremony is cancelled", async () => {
    const user = userEvent.setup()
    mfa.getStepUpOptions.mockResolvedValue({ factors: ["password"] })
    const onResult = vi.fn()
    render(
      <StepUpProvider>
        <Harness onResult={onResult} />
      </StepUpProvider>,
    )

    await user.click(screen.getByRole("button", { name: "trigger" }))
    await screen.findByLabelText("Password")
    await user.click(screen.getByRole("button", { name: "Cancel" }))

    await waitFor(() => expect(onResult).toHaveBeenCalledWith(false))
    expect(mfa.stepUpWithPassword).not.toHaveBeenCalled()
  })
})
