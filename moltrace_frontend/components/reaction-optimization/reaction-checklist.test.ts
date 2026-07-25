import { describe, expect, it } from "vitest"
import { checklistForWire } from "@/components/reaction-optimization/reaction-project-detail"

describe("checklistForWire", () => {
  it("coerces done-like text flags to real booleans", () => {
    expect(
      checklistForWire([
        { task: "rinse", done: "true" },
        { task: "heat", done: "false" },
        { task: "purge", completed: "yes", checked: "no" },
      ]),
    ).toEqual([
      { task: "rinse", done: true },
      { task: "heat", done: false },
      { task: "purge", completed: true, checked: false },
    ])
  })

  it("leaves real booleans and unrelated fields untouched", () => {
    expect(checklistForWire([{ task: "sample", done: true, note: "n/a" }])).toEqual([
      { task: "sample", done: true, note: "n/a" },
    ])
  })

  it("keeps a non-boolean string value as-is (not a done flag it recognizes)", () => {
    expect(checklistForWire([{ done: "maybe" }])).toEqual([{ done: "maybe" }])
  })
})
