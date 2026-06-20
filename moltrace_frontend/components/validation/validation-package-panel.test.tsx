import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError } from "@/lib/api/client"
import { ValidationPackagePanel } from "@/components/validation/validation-package-panel"
import type { ValidationPackage } from "@/lib/validation/validation-package"

const m = vi.hoisted(() => ({ get: vi.fn(), ingest: vi.fn() }))

vi.mock("@/lib/validation/validation-package", async (orig) => ({
  ...(await orig<typeof import("@/lib/validation/validation-package")>()),
  getValidationPackage: (...a: unknown[]) => m.get(...a),
  ingestReleaseEvidence: (...a: unknown[]) => m.ingest(...a),
}))

const PKG: ValidationPackage = {
  packageMetadata: { release_id: 1 },
  traceability: { status: "gaps_identified", note: "2 requirements without tests.", coverage: 80, gaps: [1, 2], raw: {} },
  iq: { status: "customer_supplied", note: "IQ is the customer's remit.", passed: null, failed: null, skipped: null, coveragePercent: null },
  oq: { status: "pass", note: "", passed: 142, failed: 0, skipped: 3, coveragePercent: 87.4 },
  pq: { status: "customer_supplied", note: "PQ is the customer's remit.", passed: null, failed: null, skipped: null, coveragePercent: null },
  riskSummary: { high: 1, open: 2 },
  changeControl: { validated: false, changeControlled: false, openDeviationCount: 0, projectStatus: null, releaseStatus: "draft" },
  signatures: [],
  notice: "This validation package SUPPORTS a customer's GAMP 5 / CSA effort; it does not replace the customer's CSV.",
}

beforeEach(() => {
  m.get.mockReset().mockResolvedValue(PKG)
  m.ingest.mockReset().mockResolvedValue({})
})

describe("ValidationPackagePanel", () => {
  it("renders OQ counts, traceability + change-control state, and the notice verbatim", async () => {
    render(<ValidationPackagePanel releaseId={1} />)
    await waitFor(() => expect(m.get).toHaveBeenCalledWith(1))
    expect(await screen.findByText(/142 passed · 0 failed/)).toBeInTheDocument()
    expect(screen.getByText("Gaps identified")).toBeInTheDocument()
    expect(screen.getByText("not validated")).toBeInTheDocument()
    expect(
      screen.getByText(/SUPPORTS a customer's GAMP 5 \/ CSA effort; it does not replace the customer's CSV/),
    ).toBeInTheDocument()
  })

  it("renders IQ and PQ as customer responsibility, never as passed", async () => {
    render(<ValidationPackagePanel releaseId={1} />)
    await waitFor(() => expect(m.get).toHaveBeenCalled())
    // IQ and PQ each carry the customer-responsibility badge
    expect(screen.getAllByText("Customer responsibility").length).toBe(2)
  })

  it("ingests CI evidence and surfaces a 409 when the release is already approved", async () => {
    const user = userEvent.setup()
    m.ingest.mockRejectedValue(new ApiError(409, { detail: "Release is already approved; evidence is locked." }, "Conflict"))
    render(<ValidationPackagePanel releaseId={1} />)
    await waitFor(() => expect(m.get).toHaveBeenCalled())

    await user.click(screen.getByRole("button", { name: /Attach CI evidence/i }))
    // userEvent treats { and [ as special — escape the brace so it types literally.
    await user.type(await screen.findByLabelText("test_summary_json"), '{{"passed":1}')
    await user.click(screen.getByRole("button", { name: /Ingest evidence/i }))

    await waitFor(() => expect(m.ingest).toHaveBeenCalledWith(1, expect.objectContaining({ source: "ci" })))
    expect(await screen.findByText(/already approved; evidence is locked/i)).toBeInTheDocument()
  })
})
