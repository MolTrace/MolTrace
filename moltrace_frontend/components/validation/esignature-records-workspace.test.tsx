import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ESignatureRecordsWorkspace } from "@/components/validation/esignature-records-workspace"

const apiMock = vi.hoisted(() => ({ fn: vi.fn() }))
const vmock = vi.hoisted(() => ({ verify: vi.fn(), manifest: vi.fn(), print: vi.fn() }))
let lastPostBody: Record<string, unknown> | null = null

vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  apiFetch: (...a: unknown[]) => apiMock.fn(...a),
}))
vi.mock("@/components/auth/step-up-provider", () => ({
  useStepUp: () => ({ ensureStepUp: vi.fn().mockResolvedValue(true) }),
}))
vi.mock("@/lib/auth/with-step-up", () => ({
  withStepUp: (fn: () => unknown) => fn(),
}))
vi.mock("@/components/app/backend-status-indicator", () => ({
  BackendStatusIndicator: () => null,
}))
vi.mock("@/lib/validation/esignature-verify", async (orig) => ({
  ...(await orig<typeof import("@/lib/validation/esignature-verify")>()),
  verifySignature: (...a: unknown[]) => vmock.verify(...a),
  getManifestationJson: (...a: unknown[]) => vmock.manifest(...a),
  printManifestation: (...a: unknown[]) => vmock.print(...a),
}))

const REC = {
  id: 5,
  signer_name: "Authenticated User",
  signer_user_id: 7,
  signature_meaning: "approved",
  target_type: "reaction_project",
  target_id: 2,
  signed_at: "2026-06-16T00:00:00Z",
  signature_hash: "abc123",
  record_content_hash: null,
}

beforeEach(() => {
  lastPostBody = null
  vmock.verify.mockReset()
  vmock.manifest.mockReset()
  vmock.print.mockReset()
  apiMock.fn.mockReset().mockImplementation((path: string, opts?: { method?: string; body?: Record<string, unknown> }) => {
    const method = opts?.method ?? "GET"
    if (path === "/esignatures/records" && method === "GET") return Promise.resolve([REC])
    if (path.startsWith("/esignatures/records/") && method === "GET") return Promise.resolve(REC)
    if (path === "/esignatures/records" && method === "POST") {
      lastPostBody = opts?.body ?? null
      return Promise.resolve({ ...REC, id: 6 })
    }
    return Promise.resolve({})
  })
})

describe("ESignatureRecordsWorkspace — Part 11 hardening", () => {
  it("makes the signing form server-authoritative (no signer-name field)", async () => {
    render(<ESignatureRecordsWorkspace />)
    await waitFor(() => expect(apiMock.fn).toHaveBeenCalledWith("/esignatures/records", { method: "GET" }))
    expect(screen.queryByLabelText("signer name")).not.toBeInTheDocument()
    expect(screen.getByText(/sign as the authenticated user/i)).toBeInTheDocument()
  })

  it("creates a signature without sending client signer identity", async () => {
    const user = userEvent.setup()
    render(<ESignatureRecordsWorkspace />)
    await waitFor(() => expect(apiMock.fn).toHaveBeenCalled())

    await user.type(screen.getByLabelText("target type"), "reaction_project")
    await user.type(screen.getByLabelText("target ID"), "2")
    await user.type(screen.getByLabelText("reason"), "Approving the batch.")
    await user.click(screen.getByRole("button", { name: /Create e-signature record/i }))

    await waitFor(() => expect(lastPostBody).not.toBeNull())
    expect(lastPostBody).toMatchObject({
      signature_meaning: "reviewed",
      target_type: "reaction_project",
      target_id: 2,
      reason: "Approving the batch.",
    })
    expect(lastPostBody).not.toHaveProperty("signer_name")
    expect(lastPostBody).not.toHaveProperty("signer_email")
  })

  it("verifies a record and renders the unbound/legacy status", async () => {
    const user = userEvent.setup()
    vmock.verify.mockResolvedValue({
      signatureId: 5,
      bound: false,
      valid: null,
      hashMatches: null,
      contentMatches: null,
      recordContentHash: null,
      recomputedContentHash: null,
      reason: "legacy_unbound_signature",
    })
    render(<ESignatureRecordsWorkspace />)
    await waitFor(() => expect(screen.getAllByRole("button", { name: "Open" }).length).toBeGreaterThan(0))
    await user.click(screen.getAllByRole("button", { name: "Open" })[0])
    await user.click(await screen.findByRole("button", { name: /Verify integrity/i }))

    await waitFor(() => expect(vmock.verify).toHaveBeenCalledWith("5"))
    expect(await screen.findByText("Unbound (legacy)")).toBeInTheDocument()
  })

  it("shows the manifestation with the compliance notice verbatim", async () => {
    const user = userEvent.setup()
    vmock.manifest.mockResolvedValue({
      printedName: "Authenticated User",
      signerEmail: null,
      signatureMeaning: "approved",
      meaningLabel: "Approved by",
      signedAtUtc: "2026-06-16T00:00:00+00:00",
      reason: "release",
      targetType: "reaction_project",
      targetId: 2,
      recordContentHash: null,
      signatureDigest: null,
      bindingStatus: "unbound",
      authenticationMethod: null,
      stepUpFactor: null,
      stepUpAal: null,
      attestationText: "Approved by Authenticated User — meaning: approved.",
      complianceNotice: "Supports 21 CFR Part 11; not a compliance determination for your use.",
    })
    render(<ESignatureRecordsWorkspace />)
    await waitFor(() => expect(screen.getAllByRole("button", { name: "Open" }).length).toBeGreaterThan(0))
    await user.click(screen.getAllByRole("button", { name: "Open" })[0])
    await user.click(await screen.findByRole("button", { name: /View signature/i }))

    await waitFor(() => expect(vmock.manifest).toHaveBeenCalledWith("5"))
    expect(await screen.findByText("Approved by")).toBeInTheDocument()
    expect(
      screen.getByText("Supports 21 CFR Part 11; not a compliance determination for your use."),
    ).toBeInTheDocument()
  })
})
