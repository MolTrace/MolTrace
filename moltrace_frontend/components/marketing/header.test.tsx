import { describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"

import { Header } from "@/components/marketing/header"

// The marketing header switches between desktop nav and a mobile Sheet based
// on this hook. Force mobile so the new sidebar markup actually renders.
vi.mock("@/hooks/use-mobile", () => ({
  useIsMobile: () => true,
}))

vi.mock("next/link", () => ({
  __esModule: true,
  // Spread the rest so passthrough props like ``data-testid`` survive the
  // mock — Radix Slot relies on them when rendering Button asChild Link.
  default: function MockLink({
    href,
    children,
    ...rest
  }: {
    href: string
    children?: React.ReactNode
    [key: string]: unknown
  }) {
    return (
      <a href={href} {...(rest as Record<string, unknown>)}>
        {children}
      </a>
    )
  },
}))

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}))

vi.mock("@/components/theme-toggle", () => ({
  ThemeToggle: () => <span data-testid="theme-toggle-stub" />,
}))

vi.mock("@/components/branding/molecule-logo-mark", () => ({
  MoleculeLogoMark: ({ className }: { className?: string }) => (
    <span data-testid="molecule-logo" className={className} />
  ),
}))

describe("Marketing Header — mobile sidebar refresh", () => {
  it("renders the menu trigger on mobile", () => {
    render(<Header />)
    expect(screen.getByRole("button", { name: /toggle menu/i })).toBeInTheDocument()
  })

  it("opens the sidebar and shows the four marketing sections + items", async () => {
    const { default: userEvent } = await import("@testing-library/user-event")
    const user = userEvent.setup()
    render(<Header />)
    await user.click(screen.getByRole("button", { name: /toggle menu/i }))
    const sidebar = await screen.findByTestId("marketing-mobile-sidebar")

    // Section eyebrows — Platform + Solutions render with the teal eyebrow.
    expect(within(sidebar).getByText("Platform")).toBeInTheDocument()
    expect(within(sidebar).getByText("Solutions")).toBeInTheDocument()

    // Platform items
    expect(within(sidebar).getByText("SpectraCheck")).toBeInTheDocument()
    expect(within(sidebar).getByText("Regentry")).toBeInTheDocument()
    expect(within(sidebar).getByText("ReactionIQ")).toBeInTheDocument()
    expect(within(sidebar).getByText("Integrations")).toBeInTheDocument()

    // Solutions items
    expect(within(sidebar).getByText("Pharmaceutical R&D")).toBeInTheDocument()
    expect(within(sidebar).getByText("Academic Research")).toBeInTheDocument()
    expect(within(sidebar).getByText("CRO / Analytical")).toBeInTheDocument()
    expect(within(sidebar).getByText("Regulatory Affairs")).toBeInTheDocument()

    // Single-link sections
    expect(within(sidebar).getByText("Enterprise")).toBeInTheDocument()
    expect(within(sidebar).getByText("Documentation")).toBeInTheDocument()
  })

  it("lets long Solutions/Platform item text wrap instead of truncating on mobile", async () => {
    const { default: userEvent } = await import("@testing-library/user-event")
    const user = userEvent.setup()
    render(<Header />)
    await user.click(screen.getByRole("button", { name: /toggle menu/i }))
    const sidebar = await screen.findByTestId("marketing-mobile-sidebar")

    // The longest item descriptions used to be clipped by `truncate`
    // (white-space: nowrap + ellipsis) in the narrow mobile sheet. They must
    // now wrap so the full text stays legible on small/legacy viewports + PWA.
    const longDescriptions = [
      "Drug discovery & development", // Solutions · Pharmaceutical R&D
      "University & institute labs", //  Solutions · Academic Research
      "Dossier & submission teams", //   Solutions · Regulatory Affairs
      "ICH · FDA · EMA compliance", //   Platform · Regentry
    ]
    for (const text of longDescriptions) {
      const node = within(sidebar).getByText(text)
      expect(node.className).not.toContain("truncate")
      expect(node.className).toContain("break-words")
    }

    // Item titles must not be clipped either.
    for (const text of ["Pharmaceutical R&D", "Regentry"]) {
      const node = within(sidebar).getByText(text)
      expect(node.className).not.toContain("truncate")
      expect(node.className).toContain("break-words")
    }
  })

  it("renders three CTAs in the pinned footer, with Request Demo as the gradient primary", async () => {
    const { default: userEvent } = await import("@testing-library/user-event")
    const user = userEvent.setup()
    render(<Header />)
    await user.click(screen.getByRole("button", { name: /toggle menu/i }))
    const sidebar = await screen.findByTestId("marketing-mobile-sidebar")

    // Three CTAs in order.
    expect(within(sidebar).getByRole("link", { name: /sign in/i })).toBeInTheDocument()
    expect(within(sidebar).getByRole("link", { name: /sign up/i })).toBeInTheDocument()
    // Request Demo carries the teal-gradient primary treatment. The inner
    // anchor has the data-testid; the gradient style lives on the wrapping
    // Slot/Button parent (Radix asChild forwards via Slot.cloneElement which
    // merges className but the inline ``style`` lands on the outermost
    // rendered element — search via testid then walk up).
    const demoLink = within(sidebar).getByTestId("marketing-mobile-sidebar-demo-cta")
    expect(demoLink).toBeInTheDocument()
    // Request Demo routes to the Contact page (demo reason preselected),
    // matching the established /contact?reason=... convention used by the
    // product sub-pages' "Request a demo" CTAs.
    expect(demoLink).toHaveAttribute("href", "/contact?reason=Request%20a%20demo")
    // The gradient is applied to either the anchor itself (asChild Slot merges
    // it) or one of its ancestors up to the Sheet content — assert it exists
    // somewhere in the chain.
    let style = demoLink.getAttribute("style") ?? ""
    let node: HTMLElement | null = demoLink.parentElement
    while (!style.includes("linear-gradient") && node) {
      style = node.getAttribute("style") ?? ""
      node = node.parentElement
      if (node === sidebar) break
    }
    expect(style).toMatch(/linear-gradient/)
  })
})
