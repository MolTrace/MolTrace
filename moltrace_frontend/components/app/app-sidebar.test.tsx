import { render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { AppSidebar } from "@/components/app/app-sidebar"

const nav = vi.hoisted(() => ({ path: "/dashboard" }))
vi.mock("next/navigation", () => ({ usePathname: () => nav.path }))

function renderSidebar(path: string) {
  nav.path = path
  return render(<AppSidebar collapsed={false} onToggle={() => {}} />)
}

afterEach(() => {
  nav.path = "/dashboard"
})

describe("AppSidebar", () => {
  it("leads with the three flagship modules (named + described) and groups the rest", () => {
    renderSidebar("/dashboard")
    expect(screen.getByText("SpectraCheck")).toBeInTheDocument()
    expect(screen.getByText("Repho")).toBeInTheDocument()
    expect(screen.getByText("Regentry")).toBeInTheDocument()
    expect(screen.getByText("Reaction optimization")).toBeInTheDocument() // module subtitle
    // group eyebrows
    for (const label of ["Modules", "Workspace", "Validation Center", "AI / ML", "Knowledge & Analytics"]) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    // previously URL-only / orphaned surfaces now have a home
    expect(screen.getByRole("link", { name: "e-Signatures" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Knowledge Library" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Model Factory" })).toBeInTheDocument()
  })

  it("highlights exactly the most-specific item on a nested route", () => {
    renderSidebar("/validation-center/esignatures")
    expect(screen.getByRole("link", { name: "e-Signatures" })).toHaveAttribute("aria-current", "page")
    // the hub "Overview" (/validation-center) must NOT also light up
    expect(screen.getByRole("link", { name: "Overview" })).not.toHaveAttribute("aria-current")
  })

  it("keeps Dashboard inactive when on a deeper /dashboard child", () => {
    renderSidebar("/dashboard/settings")
    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute("aria-current", "page")
    expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current")
  })

  it("marks Admin active for any /admin/* path", () => {
    renderSidebar("/admin/security")
    expect(screen.getByRole("link", { name: "Admin" })).toHaveAttribute("aria-current", "page")
  })
})
