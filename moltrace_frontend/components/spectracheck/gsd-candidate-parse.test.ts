import { describe, it, expect } from "vitest"

import { parseCandidatesFromText } from "@/components/spectracheck/gsd-jcoupling-panel"

describe("parseCandidatesFromText", () => {
  it("extracts the SMILES from the 'name | smiles | role' display form (regression)", () => {
    // Previously the whole labeled string was sent to RDKit → "Could not parse
    // SMILES: 'C11 | … | Product'". The SMILES is the second pipe field.
    expect(parseCandidatesFromText("C11 | O=C(NC1=CC=CC2=C1C=CC=C2)O | Product")).toEqual([
      { name: "C11", smiles: "O=C(NC1=CC=CC2=C1C=CC=C2)O" },
    ])
  })

  it("handles the compact 'name|smiles' round-trip form this panel builds", () => {
    expect(parseCandidatesFromText("aspirin|CC(=O)Oc1ccccc1C(=O)O")).toEqual([
      { name: "aspirin", smiles: "CC(=O)Oc1ccccc1C(=O)O" },
    ])
  })

  it("treats an empty name in the pipe form as null", () => {
    expect(parseCandidatesFromText("|CCO")).toEqual([{ name: null, smiles: "CCO" }])
  })

  it("still supports the 'name: smiles' colon form", () => {
    expect(parseCandidatesFromText("mol A: CCO")).toEqual([{ name: "mol A", smiles: "CCO" }])
  })

  it("treats a bare token as the SMILES", () => {
    expect(parseCandidatesFromText("CCO")).toEqual([{ smiles: "CCO" }])
  })

  it("parses multiple lines and skips blanks and comments", () => {
    expect(parseCandidatesFromText("# note\nA | CCO | Reactant\n\nB | CCN | Product")).toEqual([
      { name: "A", smiles: "CCO" },
      { name: "B", smiles: "CCN" },
    ])
  })

  it("drops a pipe line with no SMILES token", () => {
    expect(parseCandidatesFromText("just-a-name |  | Product")).toEqual([])
  })
})
