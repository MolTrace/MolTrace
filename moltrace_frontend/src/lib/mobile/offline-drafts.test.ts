import { beforeEach, describe, expect, it, vi } from "vitest"
import { addOfflineDraft, getOfflineDrafts } from "@/src/lib/mobile/offline-drafts"

vi.mock("@/lib/api/client", () => ({
  apiFetch: vi.fn(),
}))

describe("offline draft sanitizer", () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it("rejects raw spectrum-like keys", () => {
    const result = addOfflineDraft({
      action_type: "review_raw_spectra",
      target_type: "spectra",
      target_id: "sample-1",
      short_comment: "contains raw_fid marker",
      decision_status: "draft",
    })
    expect(result.ok).toBe(false)
    expect(getOfflineDrafts()).toHaveLength(0)
  })

  it("rejects token/password/secret keys", () => {
    const tokenResult = addOfflineDraft({
      action_type: "share",
      target_type: "report",
      target_id: "token-123",
      short_comment: "token present",
      decision_status: "draft",
    })
    const passwordResult = addOfflineDraft({
      action_type: "approve",
      target_type: "report",
      target_id: "report-1",
      short_comment: "password in note",
      decision_status: "approve",
    })
    const secretResult = addOfflineDraft({
      action_type: "comment",
      target_type: "report",
      target_id: "report-1",
      short_comment: "secret in note",
      decision_status: "draft",
    })
    expect(tokenResult.ok).toBe(false)
    expect(passwordResult.ok).toBe(false)
    expect(secretResult.ok).toBe(false)
    expect(getOfflineDrafts()).toHaveLength(0)
  })
})
