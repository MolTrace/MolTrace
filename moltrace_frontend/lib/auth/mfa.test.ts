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
  // Re-baselined: these asserted the `detail`-based behaviour, which encoded a bug rather
  // than a contract. The proxy replaces `detail` on every 401/403, so the old implementation
  // returned false for every real step-up and `withStepUp` never ran the ceremony.
  it("is true only for a 401 whose code is step_up_required", () => {
    expect(isStepUpRequired(new ApiError(401, { code: "step_up_required" }, "x"))).toBe(true)
  })
  it("is true even though the proxy replaced detail with its generic copy", () => {
    // The shape a browser actually receives: the code survives, the prose does not. The old
    // implementation returned false here, which is the whole defect.
    const asProxied = new ApiError(
      401,
      { code: "step_up_required", detail: "Sign in to access live MolTrace data." },
      "x"
    )
    expect(isStepUpRequired(asProxied)).toBe(true)
  })
  it("is false for a normal 401, a 403 step_up, or non-ApiError", () => {
    expect(isStepUpRequired(new ApiError(401, { code: "unauthenticated" }, "x"))).toBe(false)
    expect(isStepUpRequired(new ApiError(403, { code: "step_up_required" }, "x"))).toBe(false)
    expect(isStepUpRequired(new Error("step_up_required"))).toBe(false)
  })
  it("does not fall back to matching the prose", () => {
    // A backend that put the token in `detail` is exactly what this moved away from; matching
    // it here would quietly reintroduce the coupling the delta removed.
    expect(isStepUpRequired(new ApiError(401, { detail: "step_up_required" }, "x"))).toBe(false)
  })
})
