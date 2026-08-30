import { describe, expect, it } from "vitest"

import { formatUncertaintyDisplay } from "@/components/reaction-optimization/reaction-project-detail"

/**
 * The "model uncertainty" column dumped `uncertainty_json` as a truncated JSON blob, so a
 * reader got `{"uncertainty": 3.7, "confidence_label": "uncertain", ...}` in a table cell.
 *
 * The number alone is not readable either, because the four predictor branches emit two
 * different quantities: a unit-free 0-1 value, and a posterior standard deviation in the
 * objective's own units. 0.62 and 3.7 are not the same kind of thing, and a column that
 * shows both as plain numbers invites comparing them.
 */
describe("formatUncertaintyDisplay", () => {
  it("says a fallback run is not modelled rather than showing nothing", () => {
    expect(formatUncertaintyDisplay({})).toBe("not modeled")
    expect(formatUncertaintyDisplay({ uncertainty_json: {} })).toBe("not modeled")
    expect(formatUncertaintyDisplay({ uncertainty_json: { uncertainty: null } })).toBe("not modeled")
  })

  it("marks a relative 0-1 value as relative", () => {
    const out = formatUncertaintyDisplay({
      uncertainty_json: { uncertainty: 0.62, uncertainty_scale: "unit_interval" },
    })
    expect(out).toContain("0.62")
    expect(out).toContain("relative")
  })

  it("marks a posterior standard deviation as being in objective units", () => {
    const out = formatUncertaintyDisplay({
      uncertainty_json: { uncertainty: 3.7, uncertainty_scale: "objective_units" },
    })
    expect(out).toContain("3.7")
    expect(out).toContain("objective units")
    // It must not read as a probability or a 0-1 confidence.
    expect(out).not.toContain("%")
  })

  it("says the scale is unrecorded for a candidate written before it existed", () => {
    // Rows persisted before uncertainty_scale was added carry the number and no scale.
    // Showing the bare figure would invite reading it on whichever scale the reader assumes.
    const out = formatUncertaintyDisplay({ uncertainty_json: { uncertainty: 4.1 } })
    expect(out).toContain("4.1")
    expect(out).toContain("scale not recorded")
  })

  it("reads the flat column when the json block is absent", () => {
    // Some rows carry `uncertainty` directly rather than nested.
    const out = formatUncertaintyDisplay({ uncertainty: 0.5, uncertainty_scale: "unit_interval" })
    expect(out).toContain("0.5")
    expect(out).toContain("relative")
  })
})
