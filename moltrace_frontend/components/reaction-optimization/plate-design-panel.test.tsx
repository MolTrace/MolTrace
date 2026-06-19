import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { PlateDesignPanel } from "@/components/reaction-optimization/plate-design-panel"

const api = vi.hoisted(() => ({
  listPlateDesigns: vi.fn(),
  createPlateDesign: vi.fn(),
  exportPlateDesign: vi.fn(),
  downloadText: vi.fn(),
}))

// Partial mock — keep the real readers/helpers (parsePlateDesign, plateGeometry,
// buildPlateLegend, cellTint, prefillFromVariables, constants); stub network + download.
vi.mock("@/lib/reaction/plate-designs", async (orig) => ({
  ...(await orig<typeof import("@/lib/reaction/plate-designs")>()),
  listPlateDesigns: (...a: unknown[]) => api.listPlateDesigns(...a),
  createPlateDesign: (...a: unknown[]) => api.createPlateDesign(...a),
  exportPlateDesign: (...a: unknown[]) => api.exportPlateDesign(...a),
  downloadText: (...a: unknown[]) => api.downloadText(...a),
}))

const VARIABLES = [
  { name: "temperature_c", variable_type: "numeric", min_value: 40, max_value: 80 },
  { name: "solvent", variable_type: "categorical", allowed_values_json: ["MeCN", "THF"] },
  { name: "inert_atmosphere", variable_type: "boolean" },
]

const DESIGN = {
  id: 7,
  reactionProjectId: 3,
  plateFormat: "96",
  strategy: "sobol",
  wellCount: 2,
  wells: [
    { wellId: "A1", conditions: { temperature_c: 55, solvent: "MeCN", inert_atmosphere: true } },
    { wellId: "A2", conditions: { temperature_c: 72, solvent: "THF", inert_atmosphere: false } },
  ],
  dimensions: ["temperature_c", "solvent", "inert_atmosphere"],
  capacity: 96,
  rows: 8,
  cols: 12,
  provenance: { rows: 8, cols: 12 },
  inputsJson: {},
  warnings: [],
  notes: ["Advisory; requires human review."],
  humanReviewRequired: true,
  createdAt: null,
}

beforeEach(() => {
  api.listPlateDesigns.mockReset().mockResolvedValue([])
  api.createPlateDesign.mockReset().mockResolvedValue(DESIGN)
  api.exportPlateDesign.mockReset().mockResolvedValue({ target: "csv", content: "well_id,solvent\nA1,MeCN" })
  api.downloadText.mockReset()
})

describe("PlateDesignPanel", () => {
  it("prefills the variable editors from the project's design-space variables", async () => {
    render(<PlateDesignPanel projectId={3} variables={VARIABLES} />)
    await waitFor(() => expect(api.listPlateDesigns).toHaveBeenCalledWith(3))
    expect(screen.getByDisplayValue("temperature_c")).toBeInTheDocument()
    expect(screen.getByDisplayValue("40")).toBeInTheDocument()
    expect(screen.getByDisplayValue("80")).toBeInTheDocument()
    expect(screen.getByDisplayValue("MeCN, THF")).toBeInTheDocument()
    expect(screen.getByDisplayValue("inert_atmosphere")).toBeInTheDocument()
  })

  it("shows the empty state when no designs exist yet", async () => {
    render(<PlateDesignPanel projectId={3} variables={VARIABLES} />)
    await waitFor(() => expect(screen.getByText(/No plate designs yet/i)).toBeInTheDocument())
  })

  it("generates a plate with the prefilled design space and renders the map", async () => {
    const user = userEvent.setup()
    render(<PlateDesignPanel projectId={3} variables={VARIABLES} />)
    await waitFor(() => expect(api.listPlateDesigns).toHaveBeenCalled())

    await user.click(screen.getByRole("button", { name: /Generate plate/i }))

    await waitFor(() => expect(api.createPlateDesign).toHaveBeenCalled())
    const call = api.createPlateDesign.mock.calls[0]
    expect(call[0]).toBe(3)
    expect(call[1]).toMatchObject({
      plate_format: "96",
      strategy: "sobol",
      numeric_json: { temperature_c: [40, 80] },
      categorical_json: { solvent: ["MeCN", "THF"] },
      boolean_json: ["inert_atmosphere"],
      seed: 20260615,
    })
    // the returned plate renders as a map (filled wells show their well id)
    await waitFor(() => expect(screen.getByText("A1")).toBeInTheDocument())
    expect(screen.getByText("A2")).toBeInTheDocument()
    expect(screen.getByText("Advisory; requires human review.")).toBeInTheDocument() // the note, not the card description
  })

  it("exports the selected design as CSV via a file download", async () => {
    const user = userEvent.setup()
    api.listPlateDesigns.mockResolvedValue([DESIGN])
    render(<PlateDesignPanel projectId={3} variables={VARIABLES} />)
    await waitFor(() => expect(screen.getByText("A1")).toBeInTheDocument())

    await user.click(screen.getByRole("button", { name: /^CSV$/ }))

    await waitFor(() => expect(api.exportPlateDesign).toHaveBeenCalledWith(3, 7, "csv"))
    await waitFor(() => expect(api.downloadText).toHaveBeenCalled())
    const dl = api.downloadText.mock.calls[0]
    expect(String(dl[0])).toMatch(/plate-7.*\.csv/)
    expect(dl[2]).toBe("text/csv")
  })
})
