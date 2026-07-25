import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { KeyChoiceTableField } from "@/components/ui/key-choice-table-field"
import { RouteTreeField } from "@/components/ui/route-tree-field"

const DIRECTIONS = [
  { value: "higher", label: "Higher is better" },
  { value: "lower", label: "Lower is better" },
]

describe("KeyChoiceTableField", () => {
  it("omits a row until a valid choice is set (Radix Select isn't driveable in jsdom)", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <KeyChoiceTableField
        label="Directions"
        keyLabel="Metric"
        valueLabel="Direction"
        options={DIRECTIONS}
        addLabel="Add metric"
        onChange={onChange}
      />,
    )

    await user.click(screen.getByRole("button", { name: "Add metric" }))
    await user.type(screen.getByLabelText("Metric (row)"), "yield")
    // No choice picked yet → the incomplete row is omitted from the emitted map.
    expect(onChange.mock.calls.at(-1)![0]).toEqual({})
    // The value column is a constrained Select (not a free text input).
    expect(screen.getByLabelText("Direction (row)")).toBeInTheDocument()
  })

  it("accepts a valid choice and seeds from initialValue via the raw hatch", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <KeyChoiceTableField
        label="Directions"
        options={DIRECTIONS}
        initialValue={{ impurity: "lower" }}
        onChange={onChange}
      />,
    )
    expect(screen.getByDisplayValue("impurity")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Edit as JSON" }))
    const raw = screen.getByLabelText("Directions (raw JSON)")
    // enterRaw pre-fills the seeded value; clear before typing a fresh one.
    await user.clear(raw)
    await user.type(raw, '{{"yield": "higher"}')
    expect(onChange.mock.calls.at(-1)![0]).toEqual({ yield: "higher" })
  })

  it("rejects an out-of-vocabulary value in raw mode", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<KeyChoiceTableField label="Directions" options={DIRECTIONS} onChange={onChange} />)

    await user.click(screen.getByRole("button", { name: "Edit as JSON" }))
    await user.type(screen.getByLabelText("Directions (raw JSON)"), '{{"yield": "up"}')
    expect(screen.getByText(/must be one of/i)).toBeInTheDocument()
  })
})

describe("RouteTreeField", () => {
  it("builds a nested route object from the structured tree", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<RouteTreeField label="Route" onChange={onChange} />)

    await user.type(screen.getByLabelText("Target SMILES"), "CCOC(C)=O")
    await user.type(screen.getByLabelText("Target reagents"), "OS(O)(=O)=O")
    await user.type(screen.getByLabelText("Target solvent"), "ethanol")
    await user.click(screen.getByRole("button", { name: "Add precursor" }))
    await user.type(screen.getByLabelText("Precursor 1 SMILES"), "CC(O)=O")

    const last = onChange.mock.calls.at(-1)![0]
    expect(last).toEqual({
      smiles: "CCOC(C)=O",
      reagents: ["OS(O)(=O)=O"],
      solvent: "ethanol",
      children: [{ smiles: "CC(O)=O" }],
    })
  })

  it("seeds from an initial nested value and round-trips through the raw hatch", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <RouteTreeField
        label="Route"
        onChange={onChange}
        initialValue={{ smiles: "P", children: [{ smiles: "A" }, { smiles: "B" }] }}
      />,
    )
    expect(screen.getByDisplayValue("P")).toBeInTheDocument()
    expect(screen.getByDisplayValue("A")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Edit as JSON" }))
    const raw = screen.getByLabelText("Route (raw JSON)")
    expect((raw as HTMLTextAreaElement).value).toContain('"smiles": "P"')
  })

  it("omits empty reagents/solvent/children", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<RouteTreeField label="Route" onChange={onChange} />)

    await user.type(screen.getByLabelText("Target SMILES"), "X")
    expect(onChange.mock.calls.at(-1)![0]).toEqual({ smiles: "X" })
  })

  it("lets the user type multiple comma-separated reagents (no separator revert)", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<RouteTreeField label="Route" onChange={onChange} />)

    await user.type(screen.getByLabelText("Target SMILES"), "P")
    // Per-keystroke typing through the comma must not collapse the two reagents.
    await user.type(screen.getByLabelText("Target reagents"), "CC(=O)O, CCN")
    const last = onChange.mock.calls.at(-1)![0]
    expect(last.reagents).toEqual(["CC(=O)O", "CCN"])
  })

  it("keeps builder and emitted value in sync after clearing the raw JSON", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<RouteTreeField label="Route" onChange={onChange} />)

    await user.type(screen.getByLabelText("Target SMILES"), "CCO")
    await user.click(screen.getByRole("button", { name: "Edit as JSON" }))
    await user.clear(screen.getByLabelText("Route (raw JSON)"))
    await user.click(screen.getByRole("button", { name: "Use builder" }))

    // The builder must show an empty product, matching the emitted {}.
    expect((screen.getByLabelText("Target SMILES") as HTMLInputElement).value).toBe("")
    expect(onChange.mock.calls.at(-1)![0]).toEqual({ smiles: "" })
  })
})
