import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { AppShell } from "@/components/app-shell/AppShell"

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}))

describe("AppShell", () => {
  it("renders nav links", () => {
    render(
      <AppShell>
        <div>Content</div>
      </AppShell>
    )

    expect(
      screen.getAllByText((_, node) => (node?.textContent || "").replace(/\s+/g, "") === "MolTrace")[0]
    ).toBeInTheDocument()
    expect(screen.getAllByText("SpectraCheck")[0]).toBeInTheDocument()
    expect(screen.getAllByText("Reports")[0]).toBeInTheDocument()
    expect(screen.getAllByText("Automation ROI")[0]).toBeInTheDocument()
  })
})
