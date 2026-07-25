import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ObjectArrayField } from "@/components/ui/object-array-field"

describe("ObjectArrayField", () => {
  it("adds rows and emits an array of the non-empty row objects", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ObjectArrayField label="Steps" onChange={onChange} itemLabel="Step" addLabel="Add step" />)

    await user.click(screen.getByRole("button", { name: "Add step" }))
    // Each row exposes the structured editor's "Add field" affordance.
    await user.click(screen.getByRole("button", { name: "Add field" }))
    await user.type(screen.getByPlaceholderText("key"), "action")
    await user.type(screen.getByPlaceholderText("value"), "heat to reflux")

    expect(onChange.mock.calls.at(-1)![0]).toEqual([{ action: "heat to reflux" }])
  })

  it("removes a row", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <ObjectArrayField
        label="Steps"
        onChange={onChange}
        itemLabel="Step"
        addLabel="Add step"
        initialValue={[{ action: "a" }, { action: "b" }]}
      />,
    )

    await user.click(screen.getByRole("button", { name: "Remove Step 1" }))
    expect(onChange.mock.calls.at(-1)![0]).toEqual([{ action: "b" }])
  })

  it("displays seeded labeled-field values and preserves siblings on edit", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <ObjectArrayField
        label="Checklist"
        onChange={onChange}
        itemLabel="Step"
        addLabel="Add step"
        fields={[
          { key: "task", label: "Task" },
          { key: "done", label: "Done" },
        ]}
        initialValue={[{ task: "rinse", done: "true" }]}
      />,
    )

    // The seeded values must RENDER in the labeled inputs (not blank).
    expect(screen.getByDisplayValue("rinse")).toBeInTheDocument()
    expect(screen.getByDisplayValue("true")).toBeInTheDocument()

    // Editing one field must not drop the sibling field's value.
    const doneInput = screen.getByDisplayValue("true")
    await user.clear(doneInput)
    await user.type(doneInput, "false")
    expect(onChange.mock.calls.at(-1)![0]).toEqual([{ task: "rinse", done: "false" }])
  })
})
