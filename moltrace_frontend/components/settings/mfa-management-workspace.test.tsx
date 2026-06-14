import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { MfaManagementWorkspace } from "@/components/settings/mfa-management-workspace"

const mfa = vi.hoisted(() => ({
  getMfaStatus: vi.fn(),
  listPasskeys: vi.fn(),
  enrollTotp: vi.fn(),
  confirmTotp: vi.fn(),
  deleteTotp: vi.fn(),
  registerPasskey: vi.fn(),
  renamePasskey: vi.fn(),
  deletePasskey: vi.fn(),
  regenerateRecoveryCodes: vi.fn(),
  browserSupportsWebAuthn: vi.fn(() => true),
  // withStepUp imports this from the same module
  isStepUpRequired: () => false,
}))
vi.mock("@/lib/auth/mfa", () => mfa)
vi.mock("@/components/auth/step-up-provider", () => ({
  useStepUp: () => ({ ensureStepUp: vi.fn().mockResolvedValue(true) }),
}))

const STATUS = {
  factors: [] as string[],
  totp_confirmed: false,
  passkey_count: 0,
  recovery_remaining: 0,
  org_mfa_required: false,
  in_grace: false,
}

beforeEach(() => {
  Object.values(mfa).forEach((m) => typeof m === "function" && "mockReset" in m && (m as ReturnType<typeof vi.fn>).mockReset?.())
  mfa.browserSupportsWebAuthn.mockReturnValue(true)
  mfa.listPasskeys.mockResolvedValue([])
})

describe("MfaManagementWorkspace", () => {
  it("renders factor status and shows the org-requires-MFA banner", async () => {
    mfa.getMfaStatus.mockResolvedValue({ ...STATUS, org_mfa_required: true, in_grace: true })
    render(<MfaManagementWorkspace />)
    await waitFor(() => expect(screen.getByText("not set up")).toBeInTheDocument())
    expect(screen.getByText(/organization requires multi-factor/i)).toBeInTheDocument()
  })

  it("starts TOTP enrollment and renders the secret to copy", async () => {
    const user = userEvent.setup()
    mfa.getMfaStatus.mockResolvedValue(STATUS)
    mfa.enrollTotp.mockResolvedValue({ otpauth_uri: "otpauth://totp/MolTrace:me?secret=JBSWY3DPEHPK3PXP&issuer=MolTrace" })
    render(<MfaManagementWorkspace />)
    await waitFor(() => expect(screen.getByRole("button", { name: "Set up" })).toBeInTheDocument())
    await user.click(screen.getByRole("button", { name: "Set up" }))
    await waitFor(() => expect(screen.getByText("JBSWY3DPEHPK3PXP")).toBeInTheDocument())
  })

  it("regenerates recovery codes and shows them once", async () => {
    const user = userEvent.setup()
    vi.spyOn(window, "confirm").mockReturnValue(true)
    mfa.getMfaStatus.mockResolvedValue({ ...STATUS, recovery_remaining: 3 })
    mfa.regenerateRecoveryCodes.mockResolvedValue({ recovery_codes: ["aaa-111", "bbb-222"], remaining: 2 })
    render(<MfaManagementWorkspace />)
    await waitFor(() => expect(screen.getByRole("button", { name: "Regenerate" })).toBeInTheDocument())
    await user.click(screen.getByRole("button", { name: "Regenerate" }))
    await waitFor(() => expect(screen.getByText("aaa-111")).toBeInTheDocument())
    expect(screen.getByText(/save your recovery codes/i)).toBeInTheDocument()
    expect(screen.getByText("bbb-222")).toBeInTheDocument()
  })

  it("adds a passkey", async () => {
    const user = userEvent.setup()
    vi.spyOn(window, "prompt").mockReturnValue("My laptop")
    mfa.getMfaStatus.mockResolvedValue(STATUS)
    mfa.registerPasskey.mockResolvedValue({ id: 1 })
    render(<MfaManagementWorkspace />)
    await waitFor(() => expect(screen.getByRole("button", { name: /Add passkey/ })).toBeInTheDocument())
    await user.click(screen.getByRole("button", { name: /Add passkey/ }))
    await waitFor(() => expect(mfa.registerPasskey).toHaveBeenCalledWith("My laptop"))
  })
})
