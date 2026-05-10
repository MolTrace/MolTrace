import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { SpectraCheckWorkspace } from "@/components/spectracheck/spectracheck-workspace"

vi.mock("next/navigation", () => ({
  usePathname: () => "/spectracheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))

describe("SpectraCheck page", () => {
  it("renders 1H/13C evidence match action tile", () => {
    render(<SpectraCheckWorkspace defaultTab="tab-predicted" />)
    expect(
      screen.getByRole("button", { name: /Run 1H \/ 13C evidence match/i }),
    ).toBeInTheDocument()
  })
})
