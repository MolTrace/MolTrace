import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { NumberListField } from "@/components/ui/number-list-field"

describe("NumberListField", () => {
  it("emits a number[] from rows, omitting blanks and non-numbers", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<NumberListField label="Evidence IDs" addLabel="Add ID" onChange={onChange} />)

    await user.click(screen.getByRole("button", { name: "Add ID" }))
    await user.type(screen.getByLabelText("ID (row)"), "42")
    expect(onChange.mock.calls.at(-1)![0]).toEqual([42])

    await user.click(screen.getByRole("button", { name: "Add ID" }))
    const inputs = screen.getAllByLabelText("ID (row)")
    await user.type(inputs[1], "abc")
    // Non-numeric row is dropped, not emitted as NaN.
    expect(onChange.mock.calls.at(-1)![0]).toEqual([42])
  })

  it("seeds from an int array and supports removal", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<NumberListField label="IDs" initialValue={[12, 47]} onChange={onChange} />)

    expect(screen.getByDisplayValue("12")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Remove 47" }))
    expect(onChange.mock.calls.at(-1)![0]).toEqual([12])
  })

  it("round-trips through the raw-JSON hatch and rejects a non-number", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<NumberListField label="IDs" onChange={onChange} />)

    await user.click(screen.getByRole("button", { name: "Edit as JSON" }))
    const raw = screen.getByLabelText("IDs (raw JSON)")
    // userEvent treats "[" as a special sequence; escape as "[[".
    await user.type(raw, "[[7, 9]")
    expect(onChange.mock.calls.at(-1)![0]).toEqual([7, 9])

    await user.clear(raw)
    await user.type(raw, '[[7, "x"]')
    expect(screen.getByText(/is not a number/i)).toBeInTheDocument()
  })

  it("keeps the list and emitted value in sync after clearing the raw JSON", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<NumberListField label="IDs" initialValue={[1, 2, 3]} onChange={onChange} />)

    await user.click(screen.getByRole("button", { name: "Edit as JSON" }))
    await user.clear(screen.getByLabelText("IDs (raw JSON)"))
    await user.click(screen.getByRole("button", { name: "Use list" }))

    // The list must be empty, matching the emitted [] — no stale rows left displayed.
    expect(screen.queryByDisplayValue("1")).not.toBeInTheDocument()
    expect(onChange.mock.calls.at(-1)![0]).toEqual([])
  })
})
