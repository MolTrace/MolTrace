import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

const apiFetch = vi.fn()
vi.mock("@/lib/api/client", () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }))
vi.mock("@/lib/ui/entity-options", () => ({
  loadCompounds: async () => [],
  loadReactionProjects: async () => [],
}))

/** Stands in for the canvas: a button that hands back a fixed capture. */
let captureFormat: "mol" | "rxn" = "mol"
vi.mock("@/src/components/chemistry/LazyStructureCanvas", () => ({
  LazyStructureCanvas: ({ onCapture }: { onCapture: (s: unknown) => void }) => (
    <button
      type="button"
      onClick={() => onCapture({ block: "BLOCK", format: captureFormat, smiles: "OCC" })}
    >
      fake-capture
    </button>
  ),
}))

import { StructureEditorPanel } from "@/src/components/chemistry/StructureEditorPanel"

const OK_CLEAN = { ok: true, format: "mol", canonical_smiles: "CCO", inchikey: "LFQ-X", atom_count: 3, bond_count: 2, warnings: [], errors: [], validator_version: "reaction_structures.v1" }

async function captureWith(response: unknown | (() => Promise<never>), format: "mol" | "rxn" = "mol") {
  captureFormat = format
  apiFetch.mockReset()
  if (typeof response === "function") apiFetch.mockImplementation(response as () => Promise<never>)
  else apiFetch.mockResolvedValue(response)
  const user = userEvent.setup()
  render(<StructureEditorPanel />)
  await user.click(screen.getByRole("button", { name: /Open drawing canvas/i }))
  await user.click(screen.getByRole("button", { name: "fake-capture" }))
  return user
}

describe("StructureEditorPanel verdict", () => {
  beforeEach(() => {
    apiFetch.mockReset()
    captureFormat = "mol"
  })

  it("sends the capture to the validator with exactly block/format/smiles", async () => {
    await captureWith(OK_CLEAN)
    await waitFor(() => expect(apiFetch).toHaveBeenCalled())
    const [path, init] = apiFetch.mock.calls[0]!
    expect(path).toBe("/reactions/structures/validate")
    expect(Object.keys(init.body as object).sort()).toEqual(["block", "format", "smiles"])
  })

  it("reports a clean read, and shows what the service made of it", async () => {
    await captureWith(OK_CLEAN)
    await waitFor(() => expect(screen.getByText(/Read cleanly/i)).toBeInTheDocument())
    // The canonical form, distinct from the "OCC" that was drawn — the panel shows both.
    expect(screen.getByText("CCO")).toBeInTheDocument()
    expect(screen.getByText("OCC")).toBeInTheDocument()
    expect(screen.getByText(/3 atoms · 2 bonds/)).toBeInTheDocument()
    // The old unconditional disclaimer must be gone once something has actually read it.
    expect(screen.queryByText(/no chemistry service has read this/i)).toBeNull()
  })

  it("renders warning messages verbatim, headline codes first", async () => {
    await captureWith({
      ...OK_CLEAN,
      warnings: [
        { code: "charge_changed", message: "A charge was adjusted." },
        { code: "hydrogen_count_changed", message: "Hydrogen count changed on atom 4.", atom_indices: [4] },
      ],
    })
    await waitFor(() => expect(screen.getByText(/something to look at/i)).toBeInTheDocument())
    const items = screen.getAllByRole("listitem").map((li) => li.textContent ?? "")
    // The code that means "stored is not what was drawn" is not buried below a cosmetic one.
    expect(items[0]).toContain("Hydrogen count changed on atom 4.")
    expect(items[0]).toContain("atom 4")
    expect(items[1]).toContain("A charge was adjusted.")
  })

  it("does NOT claim success when the drawing was refused, and blocks the registry attach", async () => {
    await captureWith({
      ...OK_CLEAN,
      ok: false,
      canonical_smiles: null,
      errors: [{ code: "impossible_valence", message: "Carbon has five bonds." }],
    })
    await waitFor(() => expect(screen.getByText(/will not do as chemistry/i)).toBeInTheDocument())
    expect(screen.getByText("Carbon has five bonds.")).toBeInTheDocument()
    expect(screen.queryByText(/Read cleanly/i)).toBeNull()
    // A structure the service refused must not be pushable into the compound registry.
    expect(screen.getByRole("button", { name: /Attach structure/i })).toBeDisabled()
  })

  it('says "could not check" — never "fine" — when the service is unreachable', async () => {
    // The distinction this whole readout exists for: an unreachable validator is not a verdict.
    await captureWith(async () => {
      throw new Error("Service unavailable")
    })
    await waitFor(() =>
      expect(screen.getByText(/could not be reached, so this is still just a drawing/i)).toBeInTheDocument(),
    )
    expect(screen.queryByText(/Read cleanly/i)).toBeNull()
    expect(screen.queryByText(/will not do as chemistry/i)).toBeNull()
    expect(screen.getByRole("button", { name: /Check again/i })).toBeInTheDocument()
  })

  it("labels a reaction's canonical string as component-sorted, so it is not read as drawn order", async () => {
    await captureWith(
      {
        ...OK_CLEAN,
        format: "rxn",
        inchikey: null,
        canonical_smiles: "CC(=O)Cl.CCO>>CCOC(C)=O",
        component_counts: { reactants: 2, agents: 0, products: 1 },
      },
      "rxn",
    )
    await waitFor(() => expect(screen.getByText(/components sorted/i)).toBeInTheDocument())
    expect(screen.getByText(/2 reactants, 0 agents, 1 product\b/)).toBeInTheDocument()
  })

  it("offers a reaction scheme its project home, not the compound registry", async () => {
    await captureWith({ ...OK_CLEAN, format: "rxn", inchikey: null }, "rxn")
    await waitFor(() => expect(screen.getByText(/Attach as a scheme on a reaction project/i)).toBeInTheDocument())
    expect(screen.queryByText(/this build does not yet call/i)).toBeNull()
    expect(screen.queryByRole("button", { name: /Attach structure/i })).toBeNull()
  })

  it("will not attach a scheme the service refused", async () => {
    await captureWith(
      { ...OK_CLEAN, format: "rxn", ok: false, errors: [{ code: "ring_not_readable", message: "A ring could not be read." }] },
      "rxn",
    )
    await waitFor(() => expect(screen.getByText("A ring could not be read.")).toBeInTheDocument())
    expect(screen.queryByRole("button", { name: /Attach scheme/i })).toBeNull()
    expect(screen.getByText(/cannot be attached until the problems above are resolved/i)).toBeInTheDocument()
  })

  it("attaches straight to the project it is standing in, without asking which", async () => {
    captureFormat = "rxn"
    apiFetch.mockResolvedValue({ ...OK_CLEAN, format: "rxn" })
    const user = userEvent.setup()
    render(<StructureEditorPanel reactionProjectId={12} />)
    await user.click(screen.getByRole("button", { name: /Open drawing canvas/i }))
    await user.click(screen.getByRole("button", { name: "fake-capture" }))
    await waitFor(() => expect(screen.getByRole("button", { name: /Attach scheme/i })).toBeInTheDocument())
    expect(screen.queryByLabelText(/Reaction project to attach this scheme to/i)).toBeNull()

    apiFetch.mockResolvedValue({ id: 7, reaction_project_id: 12, name: "Step 3", format: "rxn", source_block: "B" })
    await user.click(screen.getByRole("button", { name: /Attach scheme/i }))
    await waitFor(() => expect(screen.getByText(/Attached to the reaction project/i)).toBeInTheDocument())
    const call = apiFetch.mock.calls.find(([p]) => String(p).includes("/schemes"))
    expect(call?.[0]).toBe("/reaction-projects/12/schemes")
  })

  it("renders the server's refusal message as sent, rather than replacing it", async () => {
    captureFormat = "rxn"
    apiFetch.mockResolvedValue({ ...OK_CLEAN, format: "rxn" })
    const user = userEvent.setup()
    render(<StructureEditorPanel reactionProjectId={12} />)
    await user.click(screen.getByRole("button", { name: /Open drawing canvas/i }))
    await user.click(screen.getByRole("button", { name: "fake-capture" }))
    await waitFor(() => expect(screen.getByRole("button", { name: /Attach scheme/i })).toBeInTheDocument())

    apiFetch.mockImplementation(async () => {
      throw new Error("That drawing could not be read as chemistry.")
    })
    await user.click(screen.getByRole("button", { name: /Attach scheme/i }))
    await waitFor(() =>
      expect(screen.getByText("That drawing could not be read as chemistry.")).toBeInTheDocument(),
    )
  })
})
