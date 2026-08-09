import { describe, expect, it } from "vitest"
import { readErrorStatus, readRefusalDetail } from "@/src/lib/api/refusal-detail"

/** Shaped like the thrown ApiError: a generic `message`, with the raw body kept on `data`. */
function apiError(status: number, data: unknown) {
  return Object.assign(new Error("Could not reach the MolTrace service. Please retry in a moment."), {
    status,
    data,
  })
}

describe("refusal detail", () => {
  it("recovers the engine's 503 detail the generic formatter would have replaced", () => {
    const err = apiError(503, { detail: "The prediction engine is not available for nmr_shift_prediction." })
    expect(readRefusalDetail(err, 503)).toBe(
      "The prediction engine is not available for nmr_shift_prediction.",
    )
    // The message itself stays generic — that is why the body has to be read.
    expect(err.message).toContain("Could not reach")
  })

  it("recovers the metric named in an approval 400", () => {
    const err = apiError(400, { detail: "Candidate regresses on ece: 0.043 -> 0.081." })
    expect(readRefusalDetail(err, 400)).toBe("Candidate regresses on ece: 0.043 -> 0.081.")
  })

  it("only answers for the status asked about", () => {
    const err = apiError(503, { detail: "engine down" })
    expect(readRefusalDetail(err, 400)).toBeNull()
    expect(readErrorStatus(err)).toBe(503)
  })

  it("declines a validation-shaped detail", () => {
    // A list of field errors is the 422 shape and does not belong in a verbatim banner.
    const err = apiError(400, { detail: [{ loc: ["body", "role"], msg: "field required" }] })
    expect(readRefusalDetail(err, 400)).toBeNull()
  })

  it("returns null for anything without a usable detail", () => {
    expect(readRefusalDetail(apiError(503, {}), 503)).toBeNull()
    expect(readRefusalDetail(apiError(503, { detail: "   " }), 503)).toBeNull()
    expect(readRefusalDetail(apiError(503, null), 503)).toBeNull()
    expect(readRefusalDetail(new Error("boom"), 503)).toBeNull()
    expect(readRefusalDetail(null, 503)).toBeNull()
    expect(readErrorStatus("nope")).toBeNull()
  })
})
