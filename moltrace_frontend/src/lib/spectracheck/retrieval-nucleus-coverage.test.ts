import { describe, expect, it } from "vitest"
import {
  explainPartialCoverage,
  readRetrievalCoverage,
} from "@/src/lib/spectracheck/retrieval-nucleus-coverage"

/**
 * The four coverage shapes from the handoff's §5, using the real payload values from the live
 * 42,449-molecule index.
 */
describe("retrieval per-nucleus coverage", () => {
  it("both nuclei compared, nothing absent → full coverage, no marker", () => {
    const c = readRetrievalCoverage({
      id: "nmrshiftdb2:10009222",
      l2_distance: 0.1337,
      nuclei_compared: ["1h", "13c"],
      nuclei_absent: [],
    })
    expect(c.matchedOnLabel).toBe("¹H + ¹³C")
    expect(c.unknown).toBe(false)
    expect(c.partial).toBe(false)
    expect(c.partialExplanation).toBeNull()
  })

  it("¹³C-only REFERENCE against a both-nuclei query → partial, and says ¹H is missing", () => {
    const c = readRetrievalCoverage({
      id: "nmrshiftdb2:20208905",
      l2_distance: 0.05,
      nuclei_compared: ["13c"],
      nuclei_absent: ["1h"],
    })
    expect(c.matchedOnLabel).toBe("¹³C")
    expect(c.partial).toBe(true)
    expect(c.partialExplanation).toContain("no ¹H data")
    expect(c.partialExplanation).toContain("only its ¹³C was compared")
    // The distance is mostly penalty — the copy must say so, not imply disagreement.
    expect(c.partialExplanation).toContain("rather than disagreement")
  })

  it("THE TRAP: a ¹³C-only QUERY has nothing absent → one nucleus, but NOT partial", () => {
    // nuclei_absent is relative to the query. The user simply did not run a proton experiment,
    // so rendering "missing ¹H" here would be a false claim about the reference.
    const c = readRetrievalCoverage({
      id: "nmrshiftdb2:20208905",
      l2_distance: 0.0848,
      nuclei_compared: ["13c"],
      nuclei_absent: [],
    })
    expect(c.matchedOnLabel).toBe("¹³C")
    expect(c.partial).toBe(false)
    expect(c.partialExplanation).toBeNull()
  })

  it("empty coverage means UNKNOWN (single-index deployment), never 'matched on nothing'", () => {
    for (const hit of [
      { id: "x", l2_distance: 0.5 }, // fields absent entirely
      { id: "x", l2_distance: 0.5, nuclei_compared: [], nuclei_absent: [] },
      { id: "x", l2_distance: 0.5, nuclei_compared: null, nuclei_absent: undefined },
    ]) {
      const c = readRetrievalCoverage(hit)
      expect(c.unknown).toBe(true)
      expect(c.matchedOnLabel).toBe("—") // falls back, asserts nothing
      expect(c.partial).toBe(false)
    }
  })

  it("survives malformed input without throwing", () => {
    for (const bad of [null, undefined, "nope", 42, { nuclei_compared: [1, null, ""] }]) {
      expect(() => readRetrievalCoverage(bad)).not.toThrow()
    }
    expect(readRetrievalCoverage({ nuclei_compared: [1, null, ""] }).unknown).toBe(true)
  })

  it("passes through an unrecognised nucleus key rather than dropping it", () => {
    const c = readRetrievalCoverage({ nuclei_compared: ["19f"], nuclei_absent: [] })
    expect(c.matchedOnLabel).toBe("19f")
  })
})

describe("partial-coverage wording", () => {
  it("does NOT present the two directions as equivalent — ¹³C carries more weight", () => {
    const missingCarbon = explainPartialCoverage(["13c"])
    const missingProton = explainPartialCoverage(["1h"])
    // A reference lacking carbon is penalised ~5x more heavily; the copy must flag that.
    expect(missingCarbon).toContain("weighted far more heavily")
    expect(missingProton).not.toContain("weighted far more heavily")
  })

  it("uses plain language — no wire keys, field names, or 'penalty term'", () => {
    for (const text of [explainPartialCoverage(["1h"]), explainPartialCoverage(["13c"])]) {
      expect(text).not.toMatch(/nuclei_absent|nuclei_compared|l2_distance|penalty term|_json/)
      expect(text).not.toMatch(/\b1h\b|\b13c\b/)
    }
  })

  it("handles both nuclei missing without claiming a specific comparison was made", () => {
    const text = explainPartialCoverage(["1h", "13c"])
    expect(text).toContain("¹H and ¹³C")
    expect(text).toContain("very little of it could be compared")
  })
})
