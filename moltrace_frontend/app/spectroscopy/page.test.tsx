import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { SpectraCheckWorkspace } from "@/components/spectracheck/spectracheck-workspace"

vi.mock("next/navigation", () => ({
  usePathname: () => "/spectracheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))

describe("SpectraCheck page", () => {
  it("renders Run SpectraCheck Analysis button", () => {
    render(<SpectraCheckWorkspace defaultTab="tab-predicted" />)
    expect(screen.getByRole("button", { name: "Run SpectraCheck Analysis" })).toBeInTheDocument()
  })
})
