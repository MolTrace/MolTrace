import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { KeyNumberTableField } from "@/components/ui/key-number-table-field"

describe("KeyNumberTableField", () => {
  it("emits a name→number map from table rows", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <KeyNumberTableField
        label="Reagent costs"
        keyLabel="Reagent"
        valueLabel="Cost"
        unit="$/g"
        addLabel="Add reagent"
        onChange={onChange}
      />,
    )

    await user.click(screen.getByRole("button", { name: "Add reagent" }))
    await user.type(screen.getByLabelText("Reagent (row)"), "Pd(OAc)2")
    await user.type(screen.getByLabelText("Cost ($/g) (row)"), "12.5")

    expect(onChange.mock.calls.at(-1)![0]).toEqual({ "Pd(OAc)2": 12.5 })
  })

  it("omits incomplete rows and never emits NaN", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<KeyNumberTableField label="Costs" addLabel="Add row" onChange={onChange} />)

    await user.click(screen.getByRole("button", { name: "Add row" }))
    await user.type(screen.getByLabelText("Name (row)"), "THF")
    await user.type(screen.getByLabelText("Value (row)"), "abc")

    for (const call of onChange.mock.calls) {
      expect(call[0]).toEqual({})
    }
  })

  it("seeds rows from initialValue and supports removal", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <KeyNumberTableField
        label="Costs"
        initialValue={{ MeCN: 3, THF: 5 }}
        onChange={onChange}
      />,
    )

    expect(screen.getByDisplayValue("MeCN")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Remove THF" }))
    expect(onChange.mock.calls.at(-1)![0]).toEqual({ MeCN: 3 })
  })

  it("flags duplicate names and lets the last row win", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <KeyNumberTableField
        label="Costs"
        keyLabel="Solvent"
        initialValue={{ MeCN: 3 }}
        addLabel="Add row"
        onChange={onChange}
      />,
    )

    await user.click(screen.getByRole("button", { name: "Add row" }))
    const keyInputs = screen.getAllByLabelText("Solvent (row)")
    await user.type(keyInputs[1], "MeCN")
    const valueInputs = screen.getAllByLabelText("Value (row)")
    await user.type(valueInputs[1], "9")

    expect(screen.getByText(/Duplicate solvent/i)).toBeInTheDocument()
    expect(onChange.mock.calls.at(-1)![0]).toEqual({ MeCN: 9 })
  })

  it("round-trips through the raw-JSON escape hatch", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<KeyNumberTableField label="Costs" onChange={onChange} />)

    await user.click(screen.getByRole("button", { name: "Edit as JSON" }))
    // userEvent treats "{" as a special sequence; escape as "{{".
    await user.type(screen.getByLabelText("Costs (raw JSON)"), '{{"XPhos": 45}')
    expect(onChange.mock.calls.at(-1)![0]).toEqual({ XPhos: 45 })

    // Back to the table: the raw edit is now a row.
    await user.click(screen.getByRole("button", { name: "Use table" }))
    expect(screen.getByDisplayValue("XPhos")).toBeInTheDocument()
    expect(screen.getByDisplayValue("45")).toBeInTheDocument()
  })

  it("rejects non-numeric values in raw mode with an inline error", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<KeyNumberTableField label="Costs" onChange={onChange} />)

    await user.click(screen.getByRole("button", { name: "Edit as JSON" }))
    await user.type(screen.getByLabelText("Costs (raw JSON)"), '{{"THF": "cheap"}')

    expect(screen.getByText(/"THF" must be a number/i)).toBeInTheDocument()
    for (const call of onChange.mock.calls) {
      expect(call[0]).toEqual({})
    }
  })

  it("does not fabricate numbers from null/empty/array values in raw mode", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<KeyNumberTableField label="Costs" onChange={onChange} />)

    await user.click(screen.getByRole("button", { name: "Edit as JSON" }))
    const raw = screen.getByLabelText("Costs (raw JSON)")
    // Number(null)/Number("")/Number([5]) are all finite in JS — must still be refused.
    await user.type(raw, '{{"Pd": null}')
    expect(screen.getByText(/"Pd" must be a number/i)).toBeInTheDocument()
    // onChange never received a fabricated {Pd: 0}.
    for (const call of onChange.mock.calls) {
      expect(call[0]).toEqual({})
    }
  })

  it("offers datalist suggestions for the name column", async () => {
    const user = userEvent.setup()
    render(
      <KeyNumberTableField
        label="Catalyst costs"
        keyLabel="Catalyst"
        suggestions={["Pd(OAc)2", "Pd2(dba)3"]}
        suggestionsHint="Suggestions come from this project's design space."
        addLabel="Add catalyst"
        onChange={vi.fn()}
      />,
    )

    await user.click(screen.getByRole("button", { name: "Add catalyst" }))
    const input = screen.getByLabelText("Catalyst (row)")
    expect(input).toHaveAttribute("list")
    expect(
      screen.getByText("Suggestions come from this project's design space."),
    ).toBeInTheDocument()
  })
})
