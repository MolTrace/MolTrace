import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
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

describe("AppSidebar show/hide control", () => {
  it("offers the control in BOTH states, always in the sidebar itself", () => {
    // The regression this guards: the toggle was only rendered as an absolutely
    // positioned chip in the collapsed state, and the <aside> had no positioning
    // context — so it resolved against <body> and landed at the far edge of the
    // viewport. The collapsed rail then had no reachable way to bring labels back.
    const { unmount } = render(<AppSidebar collapsed={false} onToggle={() => {}} />)
    expect(screen.getByRole("button", { name: "Hide item names" })).toBeInTheDocument()
    unmount()

    render(<AppSidebar collapsed onToggle={() => {}} />)
    expect(screen.getByRole("button", { name: "Show item names" })).toBeInTheDocument()
  })

  it("anchors the control to the sidebar, not to a distant ancestor", () => {
    const { container } = render(<AppSidebar collapsed onToggle={() => {}} />)
    const aside = container.querySelector("aside")
    const handle = screen.getByRole("button", { name: "Show item names" })

    // Absolute positioning only lands on the sidebar edge if the sidebar is the
    // containing block. Without `relative` here the chip flies to the viewport.
    expect(aside?.className).toContain("relative")
    expect(aside?.contains(handle)).toBe(true)
  })

  it("reports its state to assistive tech", () => {
    const { unmount } = render(<AppSidebar collapsed={false} onToggle={() => {}} />)
    expect(screen.getByRole("button", { name: "Hide item names" })).toHaveAttribute(
      "aria-expanded",
      "true",
    )
    unmount()

    render(<AppSidebar collapsed onToggle={() => {}} />)
    expect(screen.getByRole("button", { name: "Show item names" })).toHaveAttribute(
      "aria-expanded",
      "false",
    )
  })

  it("calls back when the control is used", async () => {
    const onToggle = vi.fn()
    const user = userEvent.setup()
    render(<AppSidebar collapsed onToggle={onToggle} />)

    await user.click(screen.getByRole("button", { name: "Show item names" }))
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it("hides item names when collapsed but keeps every destination reachable", () => {
    render(<AppSidebar collapsed onToggle={() => {}} />)

    // No visible label text…
    expect(screen.queryByText("Compounds & Batches")).not.toBeInTheDocument()
    // …but the link is still there, named for screen readers and pointer users.
    expect(screen.getByRole("link", { name: "Compounds & Batches" })).toHaveAttribute(
      "href",
      "/compounds",
    )
  })
})
