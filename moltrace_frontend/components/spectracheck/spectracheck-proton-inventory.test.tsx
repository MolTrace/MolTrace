import { describe, expect, it } from "vitest"
import { render, screen, within } from "@testing-library/react"
import {
  ProtonInventoryPanel,
  inventoryRowsWithWarnings,
  warningRefersToInventoryRow,
} from "@/components/spectracheck/spectracheck-evidence-panels"

/**
 * The handoff's verification case: an aromatic-protected aminoglycoside (per-Cbz
 * tobramycin derivative) in CD3OD. Expected UI: zero amber warnings, one neutral
 * note explaining the exchange, a cap annotation, and nested sub-count rows.
 */
const CD3OD_PAYLOAD = {
  proton_inventory: {
    nucleus: "1H",
    integration_basis: "nmr_text_guided",
    observed: {
      aromatic: 35.0,
      anomeric_or_olefinic: 2.0,
      carbohydrate_sugar: 18.0,
      aliphatic: 26.0,
      labile: 0.0,
      total: 63.0,
    },
    expected: { aromatic: 35, anomeric_or_olefinic: 2, aliphatic: 26, labile: 6, total: 69 },
    deltas: { aromatic: 0.0, anomeric_or_olefinic: 0.0, aliphatic: 0.0, labile: -6.0, total: -6.0 },
    warnings: [],
    notes: [
      "CD3OD exchanges NH/OH/SH protons for deuterium, so the 6 labile H are expected to be " +
        "absent from the 1H spectrum. Observed 0.0 H — consistent with exchange.",
    ],
    anomeric_cap: {
      applied: true,
      limit: 2,
      method: "structural_anomeric_olefinic_budget",
      reassigned_h: 8.0,
    },
    bucket_hierarchy: { carbohydrate_sugar: "aliphatic", carboxylic_acid: "labile" },
  },
}

describe("proton inventory — warning/row association (no client-side threshold)", () => {
  it("matches the backend's per-bucket warning phrasing", () => {
    const w = "Observed aromatic integration is -3.0 H below the structural expectation (35 H) — …"
    expect(warningRefersToInventoryRow(w, "aromatic")).toBe(true)
    expect(warningRefersToInventoryRow(w, "aliphatic")).toBe(false)
    // must not match a bucket merely mentioned mid-sentence
    expect(warningRefersToInventoryRow("Total looks odd vs aromatic expectation", "aromatic")).toBe(false)
  })

  it("flags exactly the rows the backend warned about", () => {
    const flagged = inventoryRowsWithWarnings(
      [
        "Observed labile integration is -6.0 H below the structural expectation (6 H) — …",
        "Observed total integration is -6.0 H below the structural expectation (69 H) — …",
      ],
      ["aromatic", "labile", "total", "aliphatic"],
    )
    expect(flagged.has("labile")).toBe(true)
    expect(flagged.has("total")).toBe(true)
    expect(flagged.has("aromatic")).toBe(false)
    expect(flagged.has("aliphatic")).toBe(false)
  })
})

describe("proton inventory panel — CD3OD aromatic-protected aminoglycoside", () => {
  it("labels the anomeric row plainly and annotates the cap only when applied", () => {
    render(<ProtonInventoryPanel payload={CD3OD_PAYLOAD} />)
    const row = screen.getByTestId("proton-inventory-anomeric_or_olefinic")
    // The static "(structure-capped)" assertion is gone…
    expect(row.textContent).not.toContain("(structure-capped)")
    expect(row.textContent).toContain("Anomeric / olefinic")
    // …replaced by the payload-substantiated annotation.
    expect(row.textContent).toContain("capped at 2 H")
    expect(row.textContent).toContain("8.0 H reassigned")
  })

  it("claims no cap when the backend did not apply one", () => {
    const noCap = {
      proton_inventory: {
        ...CD3OD_PAYLOAD.proton_inventory,
        anomeric_cap: { applied: false, limit: null, method: "x", reassigned_h: 0.0 },
      },
    }
    render(<ProtonInventoryPanel payload={noCap} />)
    const row = screen.getByTestId("proton-inventory-anomeric_or_olefinic")
    expect(row.textContent).not.toContain("capped at")
    expect(row.textContent).not.toContain("structure-capped")
  })

  it("nests sub-count rows DIRECTLY under their true parent row", () => {
    const withCarboxyl = {
      proton_inventory: {
        ...CD3OD_PAYLOAD.proton_inventory,
        observed: { ...CD3OD_PAYLOAD.proton_inventory.observed, carboxylic_acid: 0.0 },
      },
    }
    const { container } = render(<ProtonInventoryPanel payload={withCarboxyl} />)
    const keys = Array.from(container.querySelectorAll("[data-testid^='proton-inventory-']"))
      .map((el) => el.getAttribute("data-testid")?.replace("proton-inventory-", "") ?? "")
      .filter((k) => k && k !== "warnings" && k !== "notes")
    // Adjacency is the whole point: an indent under the wrong row is a FALSE
    // containment claim (sugar is part of aliphatic, not of anomeric/olefinic).
    expect(keys[keys.indexOf("carbohydrate_sugar") - 1]).toBe("aliphatic")
    expect(keys[keys.indexOf("carboxylic_acid") - 1]).toBe("labile")

    const sugar = screen.getByTestId("proton-inventory-carbohydrate_sugar")
    expect(sugar.querySelector('[data-nested="true"]')).not.toBeNull()
    // Screen readers get the human label, not the wire key.
    expect(sugar.textContent).toContain("sub-count of Aliphatic (incl. O/N-adjacent)")
    // a top-level bucket is NOT nested
    expect(
      screen.getByTestId("proton-inventory-aliphatic").querySelector('[data-nested="true"]'),
    ).toBeNull()
  })

  it("falls back to a flat row when the declared parent is not on screen", () => {
    // aliphatic absent from the payload → sugar must NOT float indented under
    // whatever row happens to precede it.
    const orphan = {
      proton_inventory: {
        nucleus: "1H",
        observed: { aromatic: 5.0, carbohydrate_sugar: 3.0 },
        expected: { aromatic: 5 },
        deltas: { aromatic: 0.0 },
        warnings: [],
        bucket_hierarchy: { carbohydrate_sugar: "aliphatic" },
      },
    }
    render(<ProtonInventoryPanel payload={orphan} />)
    const sugar = screen.getByTestId("proton-inventory-carbohydrate_sugar")
    expect(sugar.querySelector('[data-nested="true"]')).toBeNull()
    expect(sugar.textContent).not.toContain("sub-count of")
  })

  it("renders notes in the positive channel, distinct from warnings", () => {
    render(<ProtonInventoryPanel payload={CD3OD_PAYLOAD} />)
    const notes = screen.getByTestId("proton-inventory-notes")
    expect(within(notes).getByText(/consistent with exchange/i)).toBeTruthy()
    // zero amber warnings for this sample
    expect(screen.queryByTestId("proton-inventory-warnings")).toBeNull()
    expect(notes.getAttribute("style") ?? "").not.toContain("--mt-amber")
  })

  it("does not paint a delta amber when the backend raised no warning for that row", () => {
    render(<ProtonInventoryPanel payload={CD3OD_PAYLOAD} />)
    // labile is -6.0 (|Δ| >= 1) but the backend suppressed the warning for CD3OD:
    // the old client-side threshold would have painted it amber.
    const labile = screen.getByTestId("proton-inventory-labile")
    expect(labile.innerHTML).not.toContain("--mt-amber")
    expect(labile.textContent).toContain("-6.0")
  })

  it("paints amber only the rows the backend flagged", () => {
    const warned = {
      proton_inventory: {
        ...CD3OD_PAYLOAD.proton_inventory,
        notes: [],
        warnings: [
          "Observed aromatic integration is +3.0 H above the structural expectation (35 H) — …",
        ],
      },
    }
    render(<ProtonInventoryPanel payload={warned} />)
    expect(screen.getByTestId("proton-inventory-aromatic").innerHTML).toContain("--mt-amber")
    expect(screen.getByTestId("proton-inventory-aliphatic").innerHTML).not.toContain("--mt-amber")
  })

  it("renders the aldehyde row when the structure now supplies an expectation", () => {
    const withAldehyde = {
      proton_inventory: {
        ...CD3OD_PAYLOAD.proton_inventory,
        observed: { ...CD3OD_PAYLOAD.proton_inventory.observed, aldehyde: 1.0 },
        expected: { ...CD3OD_PAYLOAD.proton_inventory.expected, aldehyde: 1 },
        deltas: { ...CD3OD_PAYLOAD.proton_inventory.deltas, aldehyde: 0.0 },
      },
    }
    render(<ProtonInventoryPanel payload={withAldehyde} />)
    const row = screen.getByTestId("proton-inventory-aldehyde")
    expect(row.textContent).toContain("1.0") // observed, no longer permanently "—"
  })

  it("tolerates a payload without the new fields (incremental backend rollout)", () => {
    const legacy = {
      proton_inventory: {
        nucleus: "1H",
        observed: { aromatic: 5.0 },
        expected: { aromatic: 5 },
        deltas: { aromatic: 0.0 },
        warnings: [],
      },
    }
    expect(() => render(<ProtonInventoryPanel payload={legacy} />)).not.toThrow()
    expect(screen.getByTestId("proton-inventory-aromatic").textContent).toContain("5.0")
  })
})
