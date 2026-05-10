import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { SpectraCheckWorkspace } from "@/components/spectracheck/spectracheck-workspace"

vi.mock("next/navigation", () => ({
  usePathname: () => "/spectracheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))

describe("spectracheck page", () => {
  it("renders analysis button and core input textareas", () => {
    const view = render(<SpectraCheckWorkspace defaultTab="tab-nmr-text" />)

    expect(screen.getByLabelText("Candidate structures")).toBeInTheDocument()
    expect(screen.getByLabelText("1H NMR text")).toBeInTheDocument()
    expect(screen.getByLabelText("13C NMR text")).toBeInTheDocument()

    view.unmount()
    render(<SpectraCheckWorkspace defaultTab="tab-predicted" />)
    expect(
      screen.getByRole("button", { name: /Run 1H \/ 13C evidence match/i }),
    ).toBeInTheDocument()
  })
})
