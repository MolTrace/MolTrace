import { describe, expect, it, vi } from "vitest"
import { withStepUp } from "@/lib/auth/with-step-up"
import { ApiError } from "@/lib/api/client"

// The shape a browser actually receives: `code` carries the signal, and `detail` is the
// proxy's generic copy. Built with `detail: "step_up_required"` — as this did — these tests
// passed against a body no client is ever sent, which is why the live defect in
// `isStepUpRequired` survived having a green test suite.
const stepUp401 = () =>
  new ApiError(
    401,
    { code: "step_up_required", detail: "Sign in to access live MolTrace data." },
    "step up required",
  )

describe("withStepUp", () => {
  it("returns the result without any ceremony when the call succeeds", async () => {
    const ensure = vi.fn<() => Promise<boolean>>()
    const out = await withStepUp(async () => "ok", ensure)
    expect(out).toBe("ok")
    expect(ensure).not.toHaveBeenCalled()
  })

  it("runs the ceremony and retries exactly once on 401 step_up_required", async () => {
    const ensure = vi.fn<() => Promise<boolean>>().mockResolvedValue(true)
    let calls = 0
    const out = await withStepUp(async () => {
      calls += 1
      if (calls === 1) throw stepUp401()
      return "ok"
    }, ensure)
    expect(out).toBe("ok")
    expect(calls).toBe(2)
    expect(ensure).toHaveBeenCalledTimes(1)
  })

  it("rethrows the original 401 when the user cancels the ceremony (no retry)", async () => {
    const ensure = vi.fn<() => Promise<boolean>>().mockResolvedValue(false)
    const err = stepUp401()
    let calls = 0
    await expect(
      withStepUp(async () => {
        calls += 1
        throw err
      }, ensure),
    ).rejects.toBe(err)
    expect(ensure).toHaveBeenCalledTimes(1)
    expect(calls).toBe(1)
  })

  it("does not trigger step-up on an ordinary error (403 / non-step-up 401)", async () => {
    const ensure = vi.fn<() => Promise<boolean>>()
    const forbidden = new ApiError(403, { code: "forbidden" }, "no")
    await expect(withStepUp(async () => { throw forbidden }, ensure)).rejects.toBe(forbidden)
    const plain401 = new ApiError(401, { code: "unauthenticated" }, "no")
    await expect(withStepUp(async () => { throw plain401 }, ensure)).rejects.toBe(plain401)
    expect(ensure).not.toHaveBeenCalled()
  })
})
