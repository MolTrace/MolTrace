import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { StringListField } from "@/components/ui/string-list-field"
import { PairListField } from "@/components/ui/pair-list-field"

describe("StringListField", () => {
  it("emits a string array from rows, omitting blanks", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <StringListField
        label="Blocked reagents"
        itemLabel="Reagent"
        addLabel="Add reagent"
        onChange={onChange}
      />,
    )

    await user.click(screen.getByRole("button", { name: "Add reagent" }))
    await user.type(screen.getByLabelText("Reagent (row)"), "DMF")
    await user.click(screen.getByRole("button", { name: "Add reagent" }))
    // Second row left blank -> omitted.

    expect(onChange.mock.calls.at(-1)![0]).toEqual(["DMF"])
  })

  it("seeds from initialValue and supports removal", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <StringListField label="Controls" initialValue={["blast shield", "N2"]} onChange={onChange} />,
    )

    expect(screen.getByDisplayValue("blast shield")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Remove N2" }))
    expect(onChange.mock.calls.at(-1)![0]).toEqual(["blast shield"])
  })

  it("round-trips through the raw-JSON escape hatch", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<StringListField label="Controls" onChange={onChange} />)

    await user.click(screen.getByRole("button", { name: "Edit as JSON" }))
    await user.type(screen.getByLabelText("Controls (raw JSON)"), '[["slow addition"]')
    expect(onChange.mock.calls.at(-1)![0]).toEqual(["slow addition"])

    await user.click(screen.getByRole("button", { name: "Use list" }))
    expect(screen.getByDisplayValue("slow addition")).toBeInTheDocument()
  })

  it("rejects a non-array in raw mode", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<StringListField label="Controls" onChange={onChange} />)

    await user.click(screen.getByRole("button", { name: "Edit as JSON" }))
    await user.type(screen.getByLabelText("Controls (raw JSON)"), '{{"a": 1}')

    expect(screen.getByText(/Must be a JSON array/i)).toBeInTheDocument()
  })

  it("drops empty-string elements in raw mode to match the list view", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<StringListField label="Controls" onChange={onChange} />)

    await user.click(screen.getByRole("button", { name: "Edit as JSON" }))
    await user.type(screen.getByLabelText("Controls (raw JSON)"), '[["DMF", ""]')

    expect(onChange.mock.calls.at(-1)![0]).toEqual(["DMF"])
  })
})

describe("PairListField", () => {
  it("emits pairs and omits half-filled rows", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <PairListField
        label="Incompatible pairs"
        leftLabel="Component A"
        rightLabel="Component B"
        addLabel="Add pair"
        onChange={onChange}
      />,
    )

    await user.click(screen.getByRole("button", { name: "Add pair" }))
    await user.type(screen.getByLabelText("Component A (row)"), "oxidizer")
    // Only one side filled -> nothing emitted yet.
    expect(onChange.mock.calls.at(-1)![0]).toEqual([])
    await user.type(screen.getByLabelText("Component B (row)"), "amine")
    expect(onChange.mock.calls.at(-1)![0]).toEqual([["oxidizer", "amine"]])
  })

  it("seeds from 2-lists and left/right objects", () => {
    render(
      <PairListField
        label="Incompatible pairs"
        initialValue={[["a", "b"], { left: "c", right: "d" }, "junk"]}
        onChange={vi.fn()}
      />,
    )

    expect(screen.getByDisplayValue("a")).toBeInTheDocument()
    expect(screen.getByDisplayValue("c")).toBeInTheDocument()
    expect(screen.getByDisplayValue("d")).toBeInTheDocument()
  })

  it("rejects non-pair arrays in raw mode", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<PairListField label="Pairs" onChange={onChange} />)

    await user.click(screen.getByRole("button", { name: "Edit as JSON" }))
    await user.type(screen.getByLabelText("Pairs (raw JSON)"), '[["oxidizer"]')

    expect(screen.getByText(/array of pairs/i)).toBeInTheDocument()
  })

  it("drops half-blank pairs in raw mode to match the table", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<PairListField label="Pairs" onChange={onChange} />)

    await user.click(screen.getByRole("button", { name: "Edit as JSON" }))
    // userEvent needs "[[" for a literal "[", so an outer+inner array needs four.
    await user.type(screen.getByLabelText("Pairs (raw JSON)"), '[[[["oxidizer", ""]]')

    // A pair with a blank side is a shape the table can't hold — never emitted.
    expect(onChange.mock.calls.at(-1)![0]).toEqual([])
  })
})
