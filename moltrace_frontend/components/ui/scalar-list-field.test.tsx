import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ScalarListField } from "@/components/ui/scalar-list-field"

describe("ScalarListField", () => {
  it("adds numbers as chips and emits the array", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ScalarListField label="Requirement IDs" onChange={onChange} addLabel="Add" />)

    const input = screen.getByLabelText("Requirement IDs")
    await user.type(input, "4")
    await user.click(screen.getByRole("button", { name: "Add" }))
    await user.type(input, "9{Enter}")

    expect(onChange.mock.calls.at(-1)![0]).toEqual([4, 9])
    expect(screen.getByText("4")).toBeInTheDocument()
    expect(screen.getByText("9")).toBeInTheDocument()
  })

  it("dedupes and rejects non-numbers", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ScalarListField label="IDs" onChange={onChange} addLabel="Add" />)
    const input = screen.getByLabelText("IDs")

    await user.type(input, "7{Enter}")
    await user.type(input, "7{Enter}") // dup → ignored
    expect(onChange.mock.calls.at(-1)![0]).toEqual([7])

    await user.type(input, "abc{Enter}") // non-number → error, not added
    expect(screen.getByText("Enter a number.")).toBeInTheDocument()
    expect(onChange.mock.calls.at(-1)![0]).toEqual([7])
  })

  it("removes a chip", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ScalarListField label="IDs" onChange={onChange} initialValue={[1, 2]} addLabel="Add" />)

    await user.click(screen.getByRole("button", { name: "Remove 1" }))
    expect(onChange.mock.calls.at(-1)![0]).toEqual([2])
  })
})
