import { describe, expect, it } from "vitest"
import { isMfaChallenge, isStepUpRequired } from "@/lib/auth/mfa"
import { ApiError } from "@/lib/api/client"

describe("isMfaChallenge", () => {
  it("detects a 202 challenge body by mfa_required", () => {
    expect(isMfaChallenge({ mfa_required: true, mfa_token: "x", factors: ["totp"] })).toBe(true)
  })
  it("rejects a normal token response and junk", () => {
    expect(isMfaChallenge({ access_token: "tok", user: {} })).toBe(false)
    expect(isMfaChallenge({ mfa_required: false })).toBe(false)
    expect(isMfaChallenge(null)).toBe(false)
    expect(isMfaChallenge("nope")).toBe(false)
  })
})

describe("isStepUpRequired", () => {
  it("is true only for a 401 whose detail is step_up_required", () => {
    expect(isStepUpRequired(new ApiError(401, { detail: "step_up_required" }, "x"))).toBe(true)
  })
  it("is false for a normal 401, a 403 step_up, or non-ApiError", () => {
    expect(isStepUpRequired(new ApiError(401, { detail: "not authenticated" }, "x"))).toBe(false)
    expect(isStepUpRequired(new ApiError(403, { detail: "step_up_required" }, "x"))).toBe(false)
    expect(isStepUpRequired(new Error("step_up_required"))).toBe(false)
  })
})
