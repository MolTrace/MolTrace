import { describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"

import { Footer, socialLinks } from "@/components/marketing/footer"

/**
 * Brand artwork is asserted against the social registry directly, not via the
 * rendered footer: unclaimed platforms keep their artwork ready but are not
 * rendered (no `href="#"` dead links), so these assertions must not depend on
 * whether a given profile has been claimed yet.
 */
function glyphFor(label: string) {
  const entry = socialLinks.find((link) => link.label === label)
  if (!entry) throw new Error(`No social registry entry for "${label}"`)
  return entry.Glyph
}

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
      "SpectraCheck",
      "Repho",
      "About",
      "Documentation",
      "Privacy",
    ]) {
      expect(screen.getByText(link)).toBeInTheDocument()
    }
  })

  it("wires every footer link to its specific docs page (and opens in a new tab)", () => {
    // Every footer item across all four sections (Platform, Company,
    // Resources, Legal) must land on its dedicated MolTrace docs URL —
    // the docs site (https://docs.moltrace.co/) is the canonical
    // discovery surface for these pages, so the mapping has to be exact,
    // not approximate. Category items without an index page (Integrations,
    // Case Studies, Webinars) and stand-ins for not-yet-built pages (Blog)
    // land on the canonical primary entry — see the comments in
    // ``footer.tsx`` for which slug was chosen and why.
    const expectedDestinations: Array<[label: string, href: string]> = [
      // ── Platform ────────────────────────────────────────────────────
      // SpectraCheck is in-app at /spectroscopy.
      ["SpectraCheck", "/spectroscopy"],
      // Regentry is in-app at /regulatory-hub.
      ["Regentry", "/regulatory-hub"],
      // Repho is in-app at /reaction-optimization.
      ["Repho", "/reaction-optimization"],
      // Integrations is in-app at /integrations.
      ["Integrations", "/integrations"],
      // ── Company ─────────────────────────────────────────────────────
      // All four Company links are in-app routes (manifesto / careers /
      // editorial index / contact form). External docs links live in
      // Platform, Resources, and Legal sections.
      ["About", "/about"],
      ["Careers", "/careers"],
      ["Blog", "/blog"],
      ["Contact", "/contact"],
      // ── Resources ───────────────────────────────────────────────────
      ["Documentation", "https://docs.moltrace.co/"],
      ["API Reference", "https://docs.moltrace.co/guides/api/"],
      // "Case Studies" removed pre-launch (no consented customer engagement yet).
      [
        "Webinars",
        "https://docs.moltrace.co/guides/resources/webinar-getting-started/",
      ],
      // ── Legal ───────────────────────────────────────────────────────
      ["Privacy", "https://docs.moltrace.co/guides/legal/privacy-policy/"],
      ["Terms", "https://docs.moltrace.co/guides/legal/terms-of-service/"],
      ["Security", "https://docs.moltrace.co/guides/legal/security-policy/"],
      ["Compliance", "https://docs.moltrace.co/guides/legal/compliance/"],
    ]
    render(<Footer />)
    for (const [label, expected] of expectedDestinations) {
      const link = screen.getByText(label).closest("a")
      expect(link, `${label} link not found`).not.toBeNull()
      expect(link?.getAttribute("href"), `${label} href`).toBe(expected)
      // External docs links must open in a new tab with a safe ``rel`` so
      // opener leaks and stale referrer headers cannot be exploited.
      // In-app routes (e.g. ``/contact``) navigate same-tab and have no
      // ``target``/``rel`` since they don't leave the application origin.
      const isExternal = /^https?:\/\//i.test(expected)
      if (isExternal) {
        expect(link?.getAttribute("target"), `${label} target`).toBe("_blank")
        const rel = link?.getAttribute("rel") ?? ""
        expect(rel, `${label} rel`).toContain("noopener")
        expect(rel, `${label} rel`).toContain("noreferrer")
      } else {
        expect(link?.getAttribute("target"), `${label} target`).not.toBe("_blank")
      }
    }
  })

  it("renders only claimed social profiles under a 'Join our Community' eyebrow title", () => {
    render(<Footer />)
    // The eyebrow title sits in the social section above the icon row.
    const title = screen.getByTestId("footer-social-title")
    expect(title).toHaveTextContent(/Join our Community/i)
    expect(title.className).toMatch(/uppercase/)
    expect(title.className).toMatch(/tracking-\[0\.22em\]/)
    // Only profiles that actually exist are rendered. The other platforms stay
    // in the registry (artwork ready) with `href: null` until they're claimed —
    // previously they shipped as `href="#"` dead links.
    const socialNav = screen.getByTestId("footer-social-nav")
    const links = within(socialNav).getAllByRole("link")
    const labels = links.map((l) => l.getAttribute("aria-label"))
    // Registry order, filtered to claimed profiles. Crunchbase joins this list
    // once its profile exists; the rest stay hidden rather than dead-linked.
    expect(labels).toEqual(["LinkedIn", "X", "GitHub"])
  })

  it("keeps LinkedIn, X and Crunchbase artwork ready so publishing is a URL-only edit", () => {
    // These three are the priority profiles. Their glyphs must stay registered
    // (and renderable) while unclaimed, so going live is a one-line change:
    // swap `href: null` for the profile URL here + add it to the Organization
    // `sameAs` in components/seo/json-ld.tsx.
    for (const label of ["LinkedIn", "X", "Crunchbase"]) {
      const entry = socialLinks.find((link) => link.label === label)
      expect(entry, `${label} registry entry`).toBeDefined()
      const Glyph = entry!.Glyph
      const { container, unmount } = render(<Glyph />)
      expect(container.querySelector("svg"), `${label} artwork`).not.toBeNull()
      unmount()
    }
  })

  it("never renders a placeholder or dead social link", () => {
    render(<Footer />)
    const socialNav = screen.getByTestId("footer-social-nav")
    // The invariant that matters: every social icon points at a real absolute
    // profile URL. A regression here (re-adding `href="#"`) ships broken links
    // to users and a low-quality signal to crawlers.
    for (const link of within(socialNav).getAllByRole("link")) {
      const href = link.getAttribute("href")
      expect(href, `${link.getAttribute("aria-label")} href`).toBeTruthy()
      expect(href).not.toBe("#")
      expect(href).toMatch(/^https?:\/\//i)
    }
  })

  it("paints LinkedIn / Facebook / YouTube / WhatsApp / Discord with their solid brand fills", () => {
    const cases: Array<[label: string, color: string]> = [
      ["LinkedIn",  "#0A66C2"],
      ["Facebook",  "#1877F2"],
      ["YouTube",   "#FF0000"],
      ["WhatsApp",  "#25D366"],
      ["Discord",   "#5865F2"],
    ]
    for (const [label, color] of cases) {
      const Glyph = glyphFor(label)
      const { container, unmount } = render(<Glyph />)
      // Brand-accurate glyphs paint the path itself (not the svg root) with
      // the official brand colour. The chip wrapper stays neutral.
      const path = container.querySelector("path")
      expect(path, `${label} path`).not.toBeNull()
      expect(path?.getAttribute("fill"), `${label} fill`).toBe(color)
      unmount()
    }
  })

  it("renders Instagram with its rainbow brand gradient", () => {
    const Instagram = glyphFor("Instagram")
    const { container } = render(<Instagram />)
    const gradient = container.querySelector("linearGradient")
    expect(gradient).toBeInTheDocument()
    // Five stops define the warm-yellow → orange → magenta → purple → indigo
    // gradient the brand mark is famous for.
    const stops = container.querySelectorAll("stop")
    expect(stops.length).toBeGreaterThanOrEqual(4)
    // The glyph path references the gradient by id.
    const path = container.querySelector("path")
    expect(path?.getAttribute("fill") ?? "").toMatch(/moltrace-footer-instagram-gradient/)
  })

  it("renders Slack with its four-colour pinwheel (cyan / green / yellow / red)", () => {
    const Slack = glyphFor("Slack")
    const { container } = render(<Slack />)
    const paths = container.querySelectorAll("path")
    expect(paths).toHaveLength(4)
    const fills = Array.from(paths).map((p) => p.getAttribute("fill"))
    expect(new Set(fills)).toEqual(
      new Set(["#36C5F0", "#2EB67D", "#ECB22E", "#E01E5A"]),
    )
  })

  it("renders every social glyph at the same h-5 w-5 size for visual consistency", () => {
    // Asserted over the whole registry, not just the rendered footer, so the
    // artwork of an as-yet-unclaimed platform stays covered and drops into a
    // uniform row the moment its profile is claimed.
    expect(socialLinks.length).toBe(10)
    for (const { label, Glyph } of socialLinks) {
      const { container, unmount } = render(<Glyph />)
      const svg = container.querySelector("svg")
      expect(svg, `${label} svg`).not.toBeNull()
      expect(svg?.getAttribute("class") ?? "").toContain("h-5")
      expect(svg?.getAttribute("class") ?? "").toContain("w-5")
      expect(svg?.getAttribute("viewBox"), `${label} viewBox`).toBe("0 0 24 24")
      unmount()
    }
  })

  it("renders the four designed-to-support posture badges in teal-tinted pill style", () => {
    render(<Footer />)
    const badges = screen.getByTestId("footer-compliance-badges")
    // The badges are framed as design intent, not held certifications.
    expect(within(badges).getByText(/^Designed to support$/i)).toBeInTheDocument()
    const labels = within(badges)
      .getAllByText(/^(SOC 2 Type II|ICH Q2\(R2\)|GDPR|GxP \/ GAMP 5)$/i)
      .map((node) => node.textContent)
    expect(new Set(labels)).toEqual(
      new Set(["SOC 2 Type II", "ICH Q2(R2)", "GDPR", "GxP / GAMP 5"]),
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
