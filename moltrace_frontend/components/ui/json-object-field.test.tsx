import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { JsonObjectField } from "@/components/ui/json-object-field"

describe("JsonObjectField", () => {
  it("defaults to structured mode and emits typed rows", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<JsonObjectField label="Profile" onChange={onChange} addLabel="Add field" />)

    await user.click(screen.getByRole("button", { name: "Add field" }))
    await user.type(screen.getByPlaceholderText("key"), "target")
    await user.type(screen.getByPlaceholderText("value"), "purity")

    expect(onChange.mock.calls.at(-1)![0]).toEqual({ target: "purity" })
  })

  it("switches to raw JSON, accepting a nested object the flat editor can't express", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<JsonObjectField label="Profile" onChange={onChange} />)

    await user.click(screen.getByRole("button", { name: "Edit as raw JSON" }))
    const raw = screen.getByLabelText("Profile (raw JSON)")
    // userEvent treats "{" as a special sequence; escape as "{{".
    await user.type(raw, '{{"limits": {{"loq": 0.05}}}')

    expect(onChange.mock.calls.at(-1)![0]).toEqual({ limits: { loq: 0.05 } })
  })

  it("shows an inline error on invalid JSON and does not emit garbage", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<JsonObjectField label="Profile" onChange={onChange} />)

    await user.click(screen.getByRole("button", { name: "Edit as raw JSON" }))
    await user.type(screen.getByLabelText("Profile (raw JSON)"), "not json")

    expect(screen.getByText(/Enter valid JSON/i)).toBeInTheDocument()
    // The last emitted value is never the invalid text.
    for (const call of onChange.mock.calls) {
      expect(typeof call[0]).toBe("object")
    }
  })

  it("carries raw-mode edits back into structured mode", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<JsonObjectField label="Profile" onChange={onChange} allowCustomKeys />)

    await user.click(screen.getByRole("button", { name: "Edit as raw JSON" }))
    await user.type(screen.getByLabelText("Profile (raw JSON)"), '{{"method": "qNMR"}')
    await user.click(screen.getByRole("button", { name: "Use structured fields" }))

    // The key/value row seeded from the raw edit is now visible.
    expect(screen.getByDisplayValue("method")).toBeInTheDocument()
    expect(screen.getByDisplayValue("qNMR")).toBeInTheDocument()
  })
})
