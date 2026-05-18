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

  it("renders the nine brand-accurate social icons under a 'Join our Community' eyebrow title", () => {
    render(<Footer />)
    // The eyebrow title sits in the social section above the icon row.
    const title = screen.getByTestId("footer-social-title")
    expect(title).toHaveTextContent(/Join our Community/i)
    expect(title.className).toMatch(/uppercase/)
    expect(title.className).toMatch(/tracking-\[0\.22em\]/)
    // The nine icons render in order — LinkedIn / Facebook / Instagram / X /
    // YouTube / GitHub / WhatsApp / Discord / Slack.
    const socialNav = screen.getByTestId("footer-social-nav")
    const links = within(socialNav).getAllByRole("link")
    expect(links).toHaveLength(9)
    const labels = links.map((l) => l.getAttribute("aria-label"))
    expect(labels).toEqual([
      "LinkedIn",
      "Facebook",
      "Instagram",
      "X",
      "YouTube",
      "GitHub",
      "WhatsApp",
      "Discord",
      "Slack",
    ])
  })

  it("paints LinkedIn / Facebook / YouTube / WhatsApp / Discord with their solid brand fills", () => {
    render(<Footer />)
    const socialNav = screen.getByTestId("footer-social-nav")
    const cases: Array<[label: string, color: string]> = [
      ["LinkedIn",  "#0A66C2"],
      ["Facebook",  "#1877F2"],
      ["YouTube",   "#FF0000"],
      ["WhatsApp",  "#25D366"],
      ["Discord",   "#5865F2"],
    ]
    for (const [label, color] of cases) {
      const link = within(socialNav).getByLabelText(label)
      // Brand-accurate glyphs paint the path itself (not the svg root) with
      // the official brand colour. The chip wrapper stays neutral.
      const path = link.querySelector("path")
      expect(path).not.toBeNull()
      expect(path?.getAttribute("fill")).toBe(color)
    }
  })

  it("renders Instagram with its rainbow brand gradient", () => {
    render(<Footer />)
    const instagram = screen.getByLabelText("Instagram")
    const gradient = instagram.querySelector("linearGradient")
    expect(gradient).toBeInTheDocument()
    // Five stops define the warm-yellow → orange → magenta → purple → indigo
    // gradient the brand mark is famous for.
    const stops = instagram.querySelectorAll("stop")
    expect(stops.length).toBeGreaterThanOrEqual(4)
    // The glyph path references the gradient by id.
    const path = instagram.querySelector("path")
    expect(path?.getAttribute("fill") ?? "").toMatch(/moltrace-footer-instagram-gradient/)
  })

  it("renders Slack with its four-colour pinwheel (cyan / green / yellow / red)", () => {
    render(<Footer />)
    const slack = screen.getByLabelText("Slack")
    const paths = slack.querySelectorAll("path")
    expect(paths).toHaveLength(4)
    const fills = Array.from(paths).map((p) => p.getAttribute("fill"))
    expect(new Set(fills)).toEqual(
      new Set(["#36C5F0", "#2EB67D", "#ECB22E", "#E01E5A"]),
    )
  })

  it("renders every social glyph at the same h-5 w-5 size for visual consistency", () => {
    render(<Footer />)
    const socialNav = screen.getByTestId("footer-social-nav")
    const svgs = socialNav.querySelectorAll("svg")
    // All nine SVGs share the h-5 w-5 size class so the row reads as a
    // uniform mosaic — the explicit user requirement for this revision.
    expect(svgs.length).toBe(9)
    for (const svg of Array.from(svgs)) {
      expect(svg.className.baseVal).toContain("h-5")
      expect(svg.className.baseVal).toContain("w-5")
      expect(svg.getAttribute("viewBox")).toBe("0 0 24 24")
    }
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
