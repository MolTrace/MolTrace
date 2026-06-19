import { describe, expect, it } from "vitest"
import {
  buildPlateLegend,
  cellTint,
  parsePlateDesign,
  parseWellId,
  plateGeometry,
  prefillFromVariables,
  rowLabel,
} from "@/lib/reaction/plate-designs"

const RAW = {
  id: 7,
  reaction_project_id: 3,
  plate_format: "96",
  strategy: "sobol",
  well_count: 2,
  warnings: ["factorial truncated to 96 wells"],
  notes: ["Advisory; requires human review."],
  human_review_required: true,
  created_at: "2026-06-16T00:00:00Z",
  inputs_json: { seed: 20260615 },
  design_json: {
    capacity: 96,
    dimensions: ["temperature_c", "solvent", "inert_atmosphere"],
    provenance: { rows: 8, cols: 12, seed: 20260615, engine: "sobol" },
    wells: [
      { well_id: "A1", conditions: { temperature_c: 55.1, solvent: "MeCN", inert_atmosphere: true } },
      { well_id: "A2", conditions: { temperature_c: 72.5, solvent: "THF", inert_atmosphere: false } },
    ],
  },
}

describe("plate-designs lib", () => {
  it("parses a plate design response defensively", () => {
    const d = parsePlateDesign(RAW)!
    expect(d).not.toBeNull()
    expect(d.id).toBe(7)
    expect(d.plateFormat).toBe("96")
    expect(d.capacity).toBe(96)
    expect(d.rows).toBe(8)
    expect(d.cols).toBe(12)
    expect(d.wells).toHaveLength(2)
    expect(d.wells[0]).toEqual({
      wellId: "A1",
      conditions: { temperature_c: 55.1, solvent: "MeCN", inert_atmosphere: true },
    })
    expect(d.dimensions).toContain("solvent")
    expect(d.warnings[0]).toMatch(/truncated/)
    expect(d.notes[0]).toMatch(/Advisory/)
  })

  it("returns null without an id, and falls back to condition keys when dimensions are absent", () => {
    expect(parsePlateDesign({})).toBeNull()
    const d = parsePlateDesign({ id: 1, design_json: { wells: [{ well_id: "A1", conditions: { x: 1, y: 2 } }] } })!
    expect(d.dimensions.sort()).toEqual(["x", "y"])
  })

  it("parses and formats well ids", () => {
    expect(parseWellId("A1")).toEqual({ row: 0, col: 0 })
    expect(parseWellId("H12")).toEqual({ row: 7, col: 11 })
    expect(parseWellId("P24")).toEqual({ row: 15, col: 23 })
    expect(parseWellId("nope")).toBeNull()
    expect(rowLabel(0)).toBe("A")
    expect(rowLabel(7)).toBe("H")
    expect(rowLabel(15)).toBe("P")
  })

  it("resolves plate geometry from provenance, else the format default", () => {
    expect(plateGeometry({ plateFormat: "96", rows: 8, cols: 12 })).toEqual({ rows: 8, cols: 12 })
    expect(plateGeometry({ plateFormat: "384", rows: null, cols: null })).toEqual({ rows: 16, cols: 24 })
    expect(plateGeometry({ plateFormat: "24", rows: null, cols: null })).toEqual({ rows: 4, cols: 6 })
  })

  it("prefills numeric / categorical / boolean editors from variable records", () => {
    const pf = prefillFromVariables([
      { name: "temperature_c", variable_type: "numeric", min_value: 40, max_value: 80 },
      { name: "solvent", variable_type: "categorical", allowed_values_json: ["MeCN", "THF"] },
      { name: "inert_atmosphere", variable_type: "boolean" },
      { name: "", variable_type: "numeric" },
      "junk",
    ])
    expect(pf.numeric).toEqual([{ name: "temperature_c", low: "40", high: "80" }])
    expect(pf.categorical).toEqual([{ name: "solvent", levels: "MeCN, THF" }])
    expect(pf.boolean).toEqual(["inert_atmosphere"])
  })

  it("builds a legend and tints cells per dimension kind", () => {
    const d = parsePlateDesign(RAW)!
    const cat = buildPlateLegend(d.wells, "solvent")
    expect(cat.kind).toBe("categorical")
    const bool = buildPlateLegend(d.wells, "inert_atmosphere")
    expect(bool.kind).toBe("boolean")
    const num = buildPlateLegend(d.wells, "temperature_c")
    expect(num.kind).toBe("numeric")
    if (num.kind === "numeric") {
      expect(num.min).toBeCloseTo(55.1)
      expect(num.max).toBeCloseTo(72.5)
    }
    expect(buildPlateLegend(d.wells, null).kind).toBe("none")
    // a matching value tints; the "none" legend never tints
    expect(cellTint(cat, "MeCN")).not.toBe("transparent")
    expect(cellTint({ kind: "none" }, "MeCN")).toBe("transparent")
  })
})
