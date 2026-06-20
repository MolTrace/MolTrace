import { beforeAll, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MultiEntityPicker } from "@/components/ui/multi-entity-picker"
import type { EntityOption } from "@/components/ui/entity-picker"

beforeAll(() => {
  Element.prototype.hasPointerCapture = vi.fn()
  Element.prototype.setPointerCapture = vi.fn()
  Element.prototype.releasePointerCapture = vi.fn()
  Element.prototype.scrollIntoView = vi.fn()
})

const OPTIONS: EntityOption[] = [
  { id: 10, label: "URS validation", description: "gamp_category_4" },
  { id: 11, label: "Method transfer", description: "change_validation" },
]

describe("MultiEntityPicker", () => {
  it("adds an entity's id when chosen", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<MultiEntityPicker value={[]} onChange={onChange} options={OPTIONS} placeholder="Select projects" />)

    expect(screen.getByRole("combobox")).toHaveTextContent("Select projects")
    await user.click(screen.getByRole("combobox"))
    await user.click(await screen.findByText("Method transfer"))
    expect(onChange).toHaveBeenCalledWith([11])
  })

  it("renders chosen ids as named chips and removes on click", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<MultiEntityPicker value={[10]} onChange={onChange} options={OPTIONS} />)

    // chip shows the human label, not the raw id
    expect(screen.getByText("URS validation")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /Remove URS validation/i }))
    expect(onChange).toHaveBeenCalledWith([])
  })
})
