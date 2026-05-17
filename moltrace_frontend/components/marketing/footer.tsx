import Link from "next/link"
import {
  Facebook,
  Github,
  Instagram,
  Linkedin,
  Youtube,
  type LucideIcon,
} from "lucide-react"
import { moltraceTraceClassName } from "@/components/branding/moltrace-wordmark"
import { MoleculeLogoMark } from "@/components/branding/molecule-logo-mark"

const navigation = {
  platform: [
    { name: "Spectroscopy", href: "#" },
    { name: "Regulatory Intelligence Hub", href: "#" },
    { name: "Reaction Optimization", href: "#" },
    { name: "Integrations", href: "#" },
  ],
  company: [
    { name: "About", href: "#" },
    { name: "Careers", href: "#" },
    { name: "Blog", href: "#" },
    { name: "Contact", href: "#" },
  ],
  resources: [
    { name: "Documentation", href: "#" },
    { name: "API Reference", href: "#" },
    { name: "Case Studies", href: "#" },
    { name: "Webinars", href: "#" },
  ],
  legal: [
    { name: "Privacy", href: "#" },
    { name: "Terms", href: "#" },
    { name: "Security", href: "#" },
    { name: "Compliance", href: "#" },
  ],
}
const COPYRIGHT_YEAR = new Date().getUTCFullYear()

const SECTIONS: { title: string; links: { name: string; href: string }[] }[] = [
  { title: "Platform", links: navigation.platform },
  { title: "Company", links: navigation.company },
  { title: "Resources", links: navigation.resources },
  { title: "Legal", links: navigation.legal },
]

type SocialLink = {
  label: string
  href: string
  Glyph: LucideIcon | React.ComponentType<{ className?: string }>
}

/**
 * Custom X glyph — lucide-react does not ship the X (formerly Twitter) wordmark.
 * Stays inline so the footer can colour it via ``currentColor`` for
 * consistency with the other social icons.
 */
function XGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden>
      <path
        d="M5 5 L19 19"
        stroke="currentColor"
        strokeWidth="2.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M19 5 L5 19"
        stroke="currentColor"
        strokeWidth="2.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

const socialLinks: SocialLink[] = [
  { label: "LinkedIn",  href: "#", Glyph: Linkedin  },
  { label: "Facebook",  href: "#", Glyph: Facebook  },
  { label: "Instagram", href: "#", Glyph: Instagram },
  { label: "X",         href: "#", Glyph: XGlyph    },
  { label: "YouTube",   href: "#", Glyph: Youtube   },
  { label: "GitHub",    href: "#", Glyph: Github    },
]

const COMPLIANCE_BADGES = ["SOC 2 Type II", "ICH Compliant", "GDPR Ready", "GxP Validated"]

export function Footer() {
  return (
    <footer
      id="docs"
      data-testid="marketing-footer"
      className="relative border-t bg-gradient-to-b from-muted/20 via-background to-muted/30"
    >
      {/*
        Top teal-gradient hairline — subtle brand accent that hints the
        boundary between page content and chrome. Sits flush against the
        existing ``border-t`` so the two read as a single ribbon.
      */}
      <div
        aria-hidden
        className="absolute inset-x-0 top-0 h-px"
        style={{
          background:
            "linear-gradient(90deg, transparent 0%, var(--mt-teal) 25%, var(--mt-teal) 75%, transparent 100%)",
          opacity: 0.5,
        }}
      />

      <div className="mx-auto max-w-7xl px-5 py-12 sm:px-6 lg:px-8 lg:py-16">
        {/* Brand block — single row of mark + wordmark + one-line tagline. */}
        <div className="space-y-3">
          <Link href="/" className="inline-flex items-center gap-2.5">
            <MoleculeLogoMark className="h-9 w-9" />
            <span className="text-lg font-semibold tracking-tight">
              <span className="font-bold text-foreground">Mol</span>
              <span className={moltraceTraceClassName}>Trace</span>
            </span>
          </Link>
          <p className="max-w-md text-sm text-muted-foreground">
            AI-native scientific intelligence for chemistry and pharmaceutical R&D.
          </p>
        </div>

        <div className="my-10 h-px bg-border/70" aria-hidden />

        {/*
          Link sections. 2-col on mobile (2×2 visual rhythm), 4-col on sm+.
          Tightened gap-y so the four blocks read as one footer, not four
          floating columns. Headings are eyebrow-styled (uppercase mono
          tracking-wide teal) — matches the rest of the brand.
        */}
        <div className="grid grid-cols-2 gap-x-6 gap-y-10 sm:grid-cols-4">
          {SECTIONS.map((section) => (
            <div key={section.title}>
              <h3
                data-testid={`footer-section-title-${section.title.toLowerCase()}`}
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                {section.title}
              </h3>
              <ul className="mt-4 space-y-2.5">
                {section.links.map((item) => (
                  <li key={item.name}>
                    <Link
                      href={item.href}
                      className="inline-block text-sm leading-snug text-foreground/70 transition-colors hover:text-foreground"
                    >
                      {item.name}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="my-10 h-px bg-border/70" aria-hidden />

        {/*
          Bottom row: social icons + copyright + compliance badges.
          - Social icons are monochrome and uniform (modern SaaS footer
            convention — Stripe / Linear / Vercel). On hover each glyph
            picks up a soft-teal background + brand-teal foreground.
          - Compliance badges read like trust seals: teal-tinted border,
            soft-teal fill, monospaced uppercase label.
        */}
        <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <nav
            aria-label="MolTrace social media"
            data-testid="footer-social-nav"
            className="flex flex-wrap items-center gap-1.5"
          >
            {socialLinks.map(({ label, href, Glyph }) => (
              <Link
                key={label}
                href={href}
                aria-label={label}
                className="group flex h-10 w-10 items-center justify-center rounded-xl border border-transparent text-muted-foreground transition-all hover:-translate-y-px hover:border-[color:var(--mt-teal)]/30 hover:bg-[color:var(--mt-teal-soft)] hover:text-[color:var(--mt-teal)] active:translate-y-0"
              >
                <Glyph className="h-4 w-4 transition-transform group-hover:scale-110" />
              </Link>
            ))}
          </nav>

          <div
            data-testid="footer-compliance-badges"
            className="flex flex-wrap items-center gap-1.5"
          >
            {COMPLIANCE_BADGES.map((badge) => (
              <span
                key={badge}
                className="rounded-md border px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em]"
                style={{
                  borderColor: "color-mix(in oklab, var(--mt-teal) 30%, transparent)",
                  backgroundColor: "var(--mt-teal-soft)",
                  color: "var(--mt-teal)",
                }}
              >
                {badge}
              </span>
            ))}
          </div>
        </div>

        <p className="mt-8 text-xs text-muted-foreground sm:text-sm">
          &copy; {COPYRIGHT_YEAR} MolTrace Technologies, Inc. All rights reserved.
        </p>
      </div>
    </footer>
  )
}
