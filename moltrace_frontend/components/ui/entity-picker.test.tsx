import { beforeAll, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { EntityPicker, type EntityOption } from "@/components/ui/entity-picker"

// Radix/cmdk rely on a few pointer/scroll APIs jsdom doesn't implement.
beforeAll(() => {
  Element.prototype.hasPointerCapture = vi.fn()
  Element.prototype.setPointerCapture = vi.fn()
  Element.prototype.releasePointerCapture = vi.fn()
  Element.prototype.scrollIntoView = vi.fn()
})

const OPTIONS: EntityOption[] = [
  { id: 10, label: "Aspirin synthesis", description: "compound · ASA-001" },
  { id: 11, label: "Ibuprofen route B", description: "compound · IBU-002" },
]

describe("EntityPicker", () => {
  it("shows the placeholder when empty and the entity label when a value is set", () => {
    const { rerender } = render(<EntityPicker value={null} onChange={() => {}} options={OPTIONS} placeholder="Pick a compound" />)
    expect(screen.getByRole("combobox")).toHaveTextContent("Pick a compound")
    rerender(<EntityPicker value={11} onChange={() => {}} options={OPTIONS} placeholder="Pick a compound" />)
    // resolves the id to the human label — never shows the raw id
    expect(screen.getByRole("combobox")).toHaveTextContent("Ibuprofen route B")
  })

  it("opens, filters, and returns the chosen entity's id (not typed)", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<EntityPicker value={null} onChange={onChange} options={OPTIONS} searchPlaceholder="Search compounds" />)

    await user.click(screen.getByRole("combobox"))
    const search = await screen.findByPlaceholderText("Search compounds")
    await user.type(search, "ibu")
    await user.click(await screen.findByText("Ibuprofen route B"))

    expect(onChange).toHaveBeenCalledWith(11)
  })

  it("lazy-loads options on first open", async () => {
    const user = userEvent.setup()
    const load = vi.fn().mockResolvedValue(OPTIONS)
    render(<EntityPicker value={null} onChange={() => {}} load={load} />)

    expect(load).not.toHaveBeenCalled() // not fetched until opened
    await user.click(screen.getByRole("combobox"))
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1))
    expect(await screen.findByText("Aspirin synthesis")).toBeInTheDocument()
  })
})
