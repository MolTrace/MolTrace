import { beforeEach, describe, expect, it, vi } from "vitest"
import {
  attachReactionScheme,
  isHeadlineWarning,
  issueAtomIndices,
  matchSmarts,
  orderIssues,
  parseTargetList,
  readSmartsMatch,
  readVerdict,
  validateStructure,
} from "@/src/lib/chemistry/structure-validation"

const apiFetch = vi.fn()
vi.mock("@/lib/api/client", () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }))

const issue = (code: string, message = "m", atom_indices?: number[]) => ({ code, message, atom_indices })

describe("validateStructure", () => {
  beforeEach(() => {
    apiFetch.mockReset()
    apiFetch.mockResolvedValue({ ok: true, format: "mol" })
  })

  it("sends block/format/smiles and NOTHING else — every model here is extra=forbid", async () => {
    await validateStructure({ block: "B", format: "mol", smiles: "CCO" })
    const [path, init] = apiFetch.mock.calls[0]!
    expect(path).toBe("/reactions/structures/validate")
    expect(init.method).toBe("POST")
    expect(Object.keys(init.body as object).sort()).toEqual(["block", "format", "smiles"])
  })

  it('keeps smiles:"" rather than dropping it — that is the expected value for query drawings', async () => {
    await validateStructure({ block: "B", format: "rxn", smiles: "" })
    const [, init] = apiFetch.mock.calls[0]!
    const body = init.body as Record<string, unknown>
    expect(body).toHaveProperty("smiles")
    expect(body.smiles).toBe("")
  })
})

describe("attachReactionScheme", () => {
  beforeEach(() => {
    apiFetch.mockReset()
    apiFetch.mockResolvedValue({ id: 1, reaction_project_id: 12, format: "rxn", source_block: "B" })
  })

  it("posts to the project's schemes route with only the declared keys", async () => {
    await attachReactionScheme(12, { block: "B", format: "rxn", smiles: "" }, " Step 3 ")
    const [path, init] = apiFetch.mock.calls[0]!
    expect(path).toBe("/reaction-projects/12/schemes")
    const body = init.body as Record<string, unknown>
    expect(Object.keys(body).sort()).toEqual(["block", "format", "metadata_json", "name", "smiles"])
    expect(body.name).toBe("Step 3")
  })

  it("sends a null name rather than an empty string when none was typed", async () => {
    await attachReactionScheme(12, { block: "B", format: "rxn", smiles: "" }, "   ")
    const [, init] = apiFetch.mock.calls[0]!
    expect((init.body as Record<string, unknown>).name).toBeNull()
  })
})

describe("readVerdict", () => {
  it("treats ok:false as a real answer, not a failure — the verdict is in the body", () => {
    const v = readVerdict({
      ok: false,
      format: "mol",
      errors: [issue("impossible_valence", "Carbon has five bonds.")],
      warnings: [],
    })
    expect(v).not.toBeNull()
    expect(v!.ok).toBe(false)
    expect(v!.errors).toHaveLength(1)
    expect(v!.clean).toBe(false)
  })

  it("only a literal true counts as ok — a missing or truthy-ish flag must not read as fine", () => {
    for (const bad of [undefined, null, "true", 1, {}]) {
      expect(readVerdict({ ok: bad, format: "mol" })!.ok).toBe(false)
    }
  })

  it("is clean only when ok AND nothing at all was flagged", () => {
    expect(readVerdict({ ok: true, format: "mol" })!.clean).toBe(true)
    expect(
      readVerdict({ ok: true, format: "mol", warnings: [issue("charge_changed")] })!.clean,
    ).toBe(false)
  })

  it("returns null for a payload that is not an object", () => {
    for (const bad of [null, undefined, "x", 3, []]) {
      expect(readVerdict(bad)).toBeNull()
    }
  })

  it("drops malformed issues instead of rendering undefined at a chemist", () => {
    const v = readVerdict({
      ok: true,
      format: "mol",
      warnings: [issue("charge_changed"), { code: 5 }, { message: "no code" }, null],
    })
    expect(v!.warnings).toHaveLength(1)
  })

  it("leaves component_counts null for a single structure rather than zeroing it", () => {
    expect(readVerdict({ ok: true, format: "mol" })!.componentCounts).toBeNull()
    expect(
      readVerdict({ ok: true, format: "rxn", component_counts: { reactants: 2, agents: 1, products: 1 } })!
        .componentCounts,
    ).toEqual({ reactants: 2, agents: 1, products: 1 })
  })

  it("normalizes blank strings to null so the UI does not render an empty field", () => {
    const v = readVerdict({ ok: true, format: "mol", canonical_smiles: "  ", inchikey: "" })!
    expect(v.canonicalSmiles).toBeNull()
    expect(v.inchikey).toBeNull()
  })
})

describe("issue ordering", () => {
  it("floats the two codes this service exists to catch, without dropping the rest", () => {
    const ordered = orderIssues([
      issue("charge_changed"),
      issue("hydrogen_count_changed"),
      issue("stereochemistry_undefined"),
      issue("drawn_smiles_differs"),
    ])
    expect(ordered.slice(0, 2).map((i) => i.code)).toEqual([
      "hydrogen_count_changed",
      "drawn_smiles_differs",
    ])
    expect(ordered).toHaveLength(4)
  })

  it("knows which codes are the headline ones", () => {
    expect(isHeadlineWarning(issue("drawn_smiles_differs"))).toBe(true)
    expect(isHeadlineWarning(issue("hydrogen_count_changed"))).toBe(true)
    expect(isHeadlineWarning(issue("charge_changed"))).toBe(false)
  })
})

describe("issueAtomIndices", () => {
  it("keeps 0 — it is a valid 0-based atom position, not an absent value", () => {
    expect(issueAtomIndices(issue("c", "m", [0, 4]))).toEqual([0, 4])
  })

  it("returns an empty list when there are no indices", () => {
    expect(issueAtomIndices(issue("c"))).toEqual([])
    expect(issueAtomIndices({ code: "c", message: "m", atom_indices: ["x"] } as never)).toEqual([])
  })
})

describe("matchSmarts", () => {
  beforeEach(() => {
    apiFetch.mockReset()
    apiFetch.mockResolvedValue({ smarts: "c1ccccc1", results: [] })
  })

  it("sends smarts/targets and NOTHING else — this model is extra=forbid too", async () => {
    await matchSmarts("  c1ccccc1  ", ["CCO"])
    const [path, init] = apiFetch.mock.calls[0]!
    expect(path).toBe("/reactions/structures/smarts-match")
    expect(init.method).toBe("POST")
    expect(Object.keys(init.body as object).sort()).toEqual(["smarts", "targets"])
    expect((init.body as { smarts: string }).smarts).toBe("c1ccccc1")
  })
})

describe("parseTargetList", () => {
  it("splits on line breaks only — a '.' and a '>>' are inside a SMILES, not between two", () => {
    // Splitting on those would be the frontend deciding where one structure ends, which is a
    // chemistry judgement it is not entitled to make.
    expect(parseTargetList("CC(=O)Cl.OCC>>CC(=O)OCC\nCCO")).toEqual([
      "CC(=O)Cl.OCC>>CC(=O)OCC",
      "CCO",
    ])
  })

  it("drops blank lines and surrounding whitespace", () => {
    expect(parseTargetList("  CCO  \n\n\t\nCCC\n")).toEqual(["CCO", "CCC"])
    expect(parseTargetList("   ")).toEqual([])
  })
})

describe("readSmartsMatch", () => {
  const row = (over: Record<string, unknown> = {}) => ({
    smiles: "CCO",
    parsed: true,
    matched: false,
    match_count: 0,
    atom_indices: [],
    ...over,
  })

  it("counts an unreadable target as unreadable, never as a miss", () => {
    // The distinction the whole panel exists for: a target that did not parse was not searched,
    // so reporting it as "does not contain it" would be a false negative a chemist would act on.
    const out = readSmartsMatch({
      smarts: "c1ccccc1",
      results: [row({ smiles: "aspirin", matched: true, match_count: 1 }), row({ parsed: false })],
    })!
    expect(out.matchedCount).toBe(1)
    expect(out.unreadableCount).toBe(1)
    expect(out.rows[1]!.matched).toBe(false)
    expect(out.rows[1]!.parsed).toBe(false)
  })

  it("will not call a target matched when the engine could not read it", () => {
    // A contradictory row — matched:true on something that never parsed — resolves to the
    // careful answer, not the flattering one.
    const out = readSmartsMatch({ results: [row({ parsed: false, matched: true, match_count: 3 })] })!
    expect(out.rows[0]!.matched).toBe(false)
    expect(out.matchedCount).toBe(0)
  })

  it("counts from the rows, so the headline cannot disagree with the list under it", () => {
    const out = readSmartsMatch({
      matched_count: 99,
      unreadable_count: 99,
      results: [row({ matched: true }), row()],
    })!
    expect(out.matchedCount).toBe(1)
    expect(out.unreadableCount).toBe(0)
  })

  it("survives a malformed body rather than inventing a verdict", () => {
    expect(readSmartsMatch(null)).toBeNull()
    expect(readSmartsMatch([])).toBeNull()
    expect(readSmartsMatch({})!.rows).toEqual([])
    expect(readSmartsMatch({ results: "nope" })!.rows).toEqual([])
  })
})
