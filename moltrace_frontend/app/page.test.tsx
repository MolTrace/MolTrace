import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import HomePage from "@/app/page"

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn() }),
}))

describe("home page", () => {
  it("renders the MolTrace marketing landing page", () => {
    render(<HomePage />)
    expect(
      screen.getByRole("heading", {
        name: /Unified Intelligence Platform for Chemical and Pharmaceutical R&D/i,
      }),
    ).toBeInTheDocument()
    expect(screen.getAllByText("Request Demo")[0]).toBeInTheDocument()
  })
})
