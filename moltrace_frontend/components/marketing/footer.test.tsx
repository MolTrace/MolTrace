import { describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"

import { Footer } from "@/components/marketing/footer"

vi.mock("next/link", () => ({
  __esModule: true,
  default: function MockLink({
    href,
    children,
    className,
    ...rest
  }: {
    href: string
    children?: React.ReactNode
    className?: string
    [key: string]: unknown
  }) {
    return (
      <a href={href} className={className} {...(rest as Record<string, unknown>)}>
        {children}
      </a>
    )
  },
}))

vi.mock("@/components/branding/molecule-logo-mark", () => ({
  MoleculeLogoMark: ({ className }: { className?: string }) => (
    <span data-testid="molecule-logo" className={className} />
  ),
}))

describe("Marketing Footer", () => {
  it("renders the four eyebrow-styled section titles", () => {
    render(<Footer />)
    const titles = ["Platform", "Company", "Resources", "Legal"]
    for (const title of titles) {
      const node = screen.getByTestId(`footer-section-title-${title.toLowerCase()}`)
      expect(node).toBeInTheDocument()
      expect(node).toHaveTextContent(title)
      // Eyebrow treatment: uppercase mono tracking-wide teal
      const classes = node.className
      expect(classes).toContain("uppercase")
      expect(classes).toContain("tracking-[0.22em]")
      expect(classes).toContain("font-mono")
    }
  })

  it("renders all four navigation sections with their original links", () => {
    render(<Footer />)
    // Sample one item per section
    for (const link of [
      "Spectroscopy",
      "Reaction Optimization",
      "About",
      "Documentation",
      "Privacy",
    ]) {
      expect(screen.getByText(link)).toBeInTheDocument()
    }
  })

  it("renders six monochrome social icons in a single nav", () => {
    render(<Footer />)
    const socialNav = screen.getByTestId("footer-social-nav")
    const links = within(socialNav).getAllByRole("link")
    expect(links).toHaveLength(6)
    const labels = links.map((l) => l.getAttribute("aria-label"))
    expect(labels).toEqual(["LinkedIn", "Facebook", "Instagram", "X", "YouTube", "GitHub"])
  })

  it("renders the four compliance trust seals in teal-tinted pill style", () => {
    render(<Footer />)
    const badges = screen.getByTestId("footer-compliance-badges")
    const labels = within(badges)
      .getAllByText(/^(SOC 2 Type II|ICH Compliant|GDPR Ready|GxP Validated)$/i)
      .map((node) => node.textContent)
    expect(new Set(labels)).toEqual(
      new Set(["SOC 2 Type II", "ICH Compliant", "GDPR Ready", "GxP Validated"]),
    )
    // Each pill must carry the teal-tinted treatment via inline styles.
    const pills = within(badges).getAllByText(/^(SOC|ICH|GDPR|GxP)/i)
    for (const pill of pills) {
      const style = pill.getAttribute("style") ?? ""
      expect(style).toContain("--mt-teal")
    }
  })

  it("renders the copyright with the current UTC year", () => {
    render(<Footer />)
    const year = new Date().getUTCFullYear()
    expect(
      screen.getByText(new RegExp(`© ${year} MolTrace Technologies, Inc\\. All rights reserved\\.`)),
    ).toBeInTheDocument()
  })
})
