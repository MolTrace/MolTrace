import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { StructuredJsonObjectEditor, type StructuredJsonField } from "@/components/ui/structured-json-editor"

const FIELDS: StructuredJsonField[] = [
  { key: "summary", label: "Summary", type: "text" },
  { key: "passed", label: "Passed", type: "number" },
  { key: "failed", label: "Failed", type: "number" },
]

describe("StructuredJsonObjectEditor", () => {
  it("emits {} while empty and assembles typed fields (numbers coerced)", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<StructuredJsonObjectEditor fields={FIELDS} onChange={onChange} />)

    await user.type(screen.getByLabelText("Summary"), "all green")
    await user.type(screen.getByLabelText("Passed"), "42")

    const last = onChange.mock.calls.at(-1)![0]
    expect(last).toEqual({ summary: "all green", passed: 42 })
    // 'failed' was never filled, so it is omitted (not 0, not "")
    expect(last).not.toHaveProperty("failed")
  })

  it("omits a field again when it is cleared", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<StructuredJsonObjectEditor fields={FIELDS} onChange={onChange} />)

    const passed = screen.getByLabelText("Passed")
    await user.type(passed, "5")
    expect(onChange.mock.calls.at(-1)![0]).toEqual({ passed: 5 })
    await user.clear(passed)
    expect(onChange.mock.calls.at(-1)![0]).toEqual({})
  })

  it("supports free-form key/value rows with number coercion", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(
      <StructuredJsonObjectEditor
        onChange={onChange}
        allowCustomKeys
        customValueType="number"
        addLabel="Add metric"
      />,
    )

    await user.click(screen.getByRole("button", { name: "Add metric" }))
    const keyInput = screen.getByPlaceholderText("key")
    const valueInput = screen.getByPlaceholderText("value")
    await user.type(keyInput, "r2")
    await user.type(valueInput, "0.987")

    expect(onChange.mock.calls.at(-1)![0]).toEqual({ r2: 0.987 })
  })

  it("auto-detects value types (number vs string) for custom rows", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<StructuredJsonObjectEditor onChange={onChange} allowCustomKeys customValueType="auto" addLabel="Add" />)

    await user.click(screen.getByRole("button", { name: "Add" }))
    await user.type(screen.getByPlaceholderText("key"), "loq")
    await user.type(screen.getByPlaceholderText("value"), "0.05")
    expect(onChange.mock.calls.at(-1)![0]).toEqual({ loq: 0.05 })

    await user.clear(screen.getByPlaceholderText("value"))
    await user.type(screen.getByPlaceholderText("value"), "pass")
    expect(onChange.mock.calls.at(-1)![0]).toEqual({ loq: "pass" })
  })

  it("keeps identifier-like values as strings (lossless round-trip only)", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<StructuredJsonObjectEditor onChange={onChange} allowCustomKeys customValueType="auto" addLabel="Add" />)

    await user.click(screen.getByRole("button", { name: "Add" }))
    await user.type(screen.getByPlaceholderText("key"), "lot")
    // "007" would lose its leading zeros if coerced — must stay a string.
    await user.type(screen.getByPlaceholderText("value"), "007")
    expect(onChange.mock.calls.at(-1)![0]).toEqual({ lot: "007" })
  })

  it("seeds fields from initialValue", () => {
    const onChange = vi.fn()
    render(
      <StructuredJsonObjectEditor
        fields={FIELDS}
        initialValue={{ summary: "seeded", passed: 3 }}
        onChange={onChange}
      />,
    )
    expect(screen.getByLabelText("Summary")).toHaveValue("seeded")
    expect(screen.getByLabelText("Passed")).toHaveValue("3")
  })
})
