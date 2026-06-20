import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"

import { MobileBottomNav } from "@/src/components/app-shell/MobileBottomNav"

// Stub Next.js link + router internals so the nav can render in jsdom without
// the surrounding app shell.
vi.mock("next/link", () => ({
  __esModule: true,
  default: function MockLink({
    href,
    className,
    children,
    ...rest
  }: {
    href: string
    className?: string
    children?: React.ReactNode
  }) {
    return (
      <a href={href} className={className} {...rest}>
        {children}
      </a>
    )
  },
}))

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}))

// MobileBottomNav reads tenant role to gate admin-only More items; stub a
// minimal non-admin context so we exercise just the primary tabs + More.
vi.mock("@/src/lib/tenant/tenant-context", () => ({
  useTenant: () => ({ isAdmin: false }),
}))

describe("MobileBottomNav", () => {
  it("renders the primary tabs in the expected order with 'Home' replacing 'Landing'", () => {
    render(<MobileBottomNav />)
    const labels = screen.getAllByTestId("mobile-nav-label").map((el) => el.textContent)
    // The rename must land; "Landing" must NOT appear anywhere as a label.
    expect(labels).toEqual([
      "Home",
      "Dashboard",
      "SpectraCheck",
      "Regentry",
      "Repho",
    ])
    expect(labels).not.toContain("Landing")
  })

  it("constrains each primary-tab label so it can truncate inside its grid cell", () => {
    // Regression for the mobile-overlap bug: the label span MUST carry
    // ``w-full`` + ``truncate`` so long labels like "SpectraCheck" /
    // "Regulatory" clip with an ellipsis instead of bleeding into the
    // neighbouring cell. The parent grid cell's ``items-center`` would
    // otherwise shrink the span to its content width, defeating ``truncate``.
    render(<MobileBottomNav />)
    const labels = screen.getAllByTestId("mobile-nav-label")
    expect(labels.length).toBeGreaterThan(0)
    for (const span of labels) {
      const classes = span.className
      expect(classes).toContain("w-full")
      expect(classes).toContain("truncate")
      expect(classes).toContain("text-center")
    }
  })

  it("links the Home tab to the root path", () => {
    render(<MobileBottomNav />)
    const homeLabel = screen.getByText("Home")
    // Walk up to the nearest anchor.
    const anchor = homeLabel.closest("a")
    expect(anchor).not.toBeNull()
    expect(anchor?.getAttribute("href")).toBe("/")
  })
})
