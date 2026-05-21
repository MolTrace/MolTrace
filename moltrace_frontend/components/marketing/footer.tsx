import Link from "next/link"
import { moltraceTraceClassName, moltraceWordmark3DStyle } from "@/components/branding/moltrace-wordmark"
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

/**
 * Brand-accurate social glyphs for the "Join our Community" row.
 *
 * Each glyph is an inline SVG of the platform's *official* brand mark
 * (Simple Icons-style paths) rendered in its *default company colour* —
 * LinkedIn blue, Facebook blue, Instagram rainbow gradient, X black,
 * YouTube red, GitHub dark, WhatsApp green, Discord blurple, Slack
 * four-colour pinwheel. The previous implementation used lucide's
 * stroke-style icons which read as a stylised approximation rather than
 * the recognisable brand logo; this implementation uses the official
 * glyph paths so each platform reads at a glance.
 *
 * All glyphs share:
 *   - a uniform 24×24 viewBox
 *   - a uniform rendered size (``h-5 w-5`` → 20 px)
 *   - solid ``fill`` (no stroke); the chip wrapper provides the hover
 *     affordance and the spacing
 *
 * Adding a new platform: create a new ``<PlatformGlyph />`` component,
 * register it in ``socialLinks`` below.
 */

const SOCIAL_SVG_CLASS = "h-5 w-5 shrink-0"
const COMMON_SVG_PROPS = {
  viewBox: "0 0 24 24",
  className: SOCIAL_SVG_CLASS,
  xmlns: "http://www.w3.org/2000/svg",
  "aria-hidden": true,
} as const

// ─── LinkedIn — solid blue (#0A66C2) ────────────────────────────────────
function LinkedInGlyph() {
  return (
    <svg {...COMMON_SVG_PROPS}>
      <path
        fill="#0A66C2"
        d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 0 1-2.063-2.065 2.063 2.063 0 1 1 2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"
      />
    </svg>
  )
}

// ─── Facebook — solid blue (#1877F2) ────────────────────────────────────
function FacebookGlyph() {
  return (
    <svg {...COMMON_SVG_PROPS}>
      <path
        fill="#1877F2"
        d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"
      />
    </svg>
  )
}

// ─── Instagram — rainbow gradient (warm-yellow → magenta → purple) ──────
const INSTAGRAM_GRADIENT_ID = "moltrace-footer-instagram-gradient"
function InstagramGlyph() {
  return (
    <svg {...COMMON_SVG_PROPS}>
      <defs>
        <linearGradient
          id={INSTAGRAM_GRADIENT_ID}
          x1="0"
          y1="24"
          x2="24"
          y2="0"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0%" stopColor="#FEDA75" />
          <stop offset="30%" stopColor="#FA7E1E" />
          <stop offset="55%" stopColor="#D62976" />
          <stop offset="80%" stopColor="#962FBF" />
          <stop offset="100%" stopColor="#4F5BD5" />
        </linearGradient>
      </defs>
      <path
        fill={`url(#${INSTAGRAM_GRADIENT_ID})`}
        d="M12 0C8.74 0 8.333.015 7.053.072 5.775.132 4.905.333 4.14.63c-.789.306-1.459.717-2.126 1.384S.935 3.35.63 4.14C.333 4.905.131 5.775.072 7.053.012 8.333 0 8.74 0 12s.015 3.667.072 4.947c.06 1.277.261 2.148.558 2.913.306.788.717 1.459 1.384 2.126.667.666 1.336 1.079 2.126 1.384.766.296 1.636.499 2.913.558C8.333 23.988 8.74 24 12 24s3.667-.015 4.947-.072c1.277-.06 2.148-.262 2.913-.558.788-.306 1.459-.718 2.126-1.384.666-.667 1.079-1.335 1.384-2.126.296-.765.499-1.636.558-2.913.06-1.28.072-1.687.072-4.947s-.015-3.667-.072-4.947c-.06-1.277-.262-2.149-.558-2.913-.306-.789-.718-1.459-1.384-2.126C21.319 1.347 20.651.935 19.86.63c-.765-.297-1.636-.499-2.913-.558C15.667.012 15.26 0 12 0zm0 2.16c3.203 0 3.585.016 4.85.071 1.17.055 1.805.249 2.227.415.562.217.96.477 1.382.896.419.42.679.819.896 1.381.164.422.36 1.057.413 2.227.057 1.266.07 1.646.07 4.85s-.015 3.585-.074 4.85c-.061 1.17-.256 1.805-.421 2.227-.224.562-.479.96-.897 1.382-.419.419-.824.679-1.38.896-.42.164-1.065.36-2.235.413-1.274.057-1.649.07-4.859.07-3.211 0-3.586-.015-4.859-.074-1.171-.061-1.816-.256-2.236-.421-.569-.224-.96-.479-1.379-.897-.421-.419-.69-.824-.9-1.38-.165-.42-.359-1.065-.42-2.235-.045-1.26-.061-1.649-.061-4.844 0-3.196.016-3.586.061-4.861.061-1.17.255-1.814.42-2.234.21-.57.479-.96.9-1.381.419-.419.81-.689 1.379-.898.42-.166 1.051-.361 2.221-.421 1.275-.045 1.65-.06 4.859-.06l.045.03zm0 3.678c-3.405 0-6.162 2.76-6.162 6.162 0 3.405 2.76 6.162 6.162 6.162 3.405 0 6.162-2.76 6.162-6.162 0-3.405-2.76-6.162-6.162-6.162zM12 16c-2.21 0-4-1.79-4-4s1.79-4 4-4 4 1.79 4 4-1.79 4-4 4zm7.846-10.405c0 .795-.646 1.44-1.44 1.44-.795 0-1.44-.646-1.44-1.44 0-.794.646-1.439 1.44-1.439.793-.001 1.44.645 1.44 1.439z"
      />
    </svg>
  )
}

// ─── X — black/light-mode-aware ─────────────────────────────────────────
function XGlyph() {
  return (
    <svg
      {...COMMON_SVG_PROPS}
      className={`${SOCIAL_SVG_CLASS} text-black dark:text-neutral-50`}
    >
      <path
        fill="currentColor"
        d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"
      />
    </svg>
  )
}

// ─── YouTube — solid red (#FF0000) ──────────────────────────────────────
function YouTubeGlyph() {
  return (
    <svg {...COMMON_SVG_PROPS}>
      <path
        fill="#FF0000"
        d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"
      />
    </svg>
  )
}

// ─── GitHub — dark/light-mode-aware (#181717) ───────────────────────────
function GitHubGlyph() {
  return (
    <svg
      {...COMMON_SVG_PROPS}
      className={`${SOCIAL_SVG_CLASS} text-[#181717] dark:text-neutral-100`}
    >
      <path
        fill="currentColor"
        d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"
      />
    </svg>
  )
}

// ─── WhatsApp — solid green (#25D366) ───────────────────────────────────
function WhatsAppGlyph() {
  return (
    <svg {...COMMON_SVG_PROPS}>
      <path
        fill="#25D366"
        d="M.057 24l1.687-6.163a11.867 11.867 0 0 1-1.587-5.946C.16 5.335 5.495 0 12.05 0a11.817 11.817 0 0 1 8.413 3.488 11.824 11.824 0 0 1 3.48 8.414c-.003 6.557-5.338 11.892-11.893 11.892a11.9 11.9 0 0 1-5.688-1.448L.057 24zm6.597-3.807c1.676.995 3.276 1.591 5.392 1.592 5.448 0 9.886-4.434 9.889-9.885.002-5.462-4.415-9.89-9.881-9.892-5.452 0-9.887 4.434-9.889 9.884-.001 2.225.651 3.891 1.746 5.634l-.999 3.648 3.742-.981zm11.387-5.464c-.074-.124-.272-.198-.57-.347-.296-.149-1.758-.868-2.031-.967-.272-.099-.47-.149-.669.149-.198.297-.768.967-.941 1.165-.173.198-.347.223-.644.074-.297-.149-1.255-.462-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.521.151-.172.2-.296.3-.495.099-.198.05-.372-.025-.521-.075-.148-.669-1.611-.916-2.206-.242-.579-.487-.501-.669-.51l-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.095 3.2 5.076 4.487.709.306 1.263.489 1.694.626.712.226 1.36.194 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.695.248-1.29.173-1.414z"
      />
    </svg>
  )
}

// ─── Discord — solid blurple (#5865F2) ──────────────────────────────────
function DiscordGlyph() {
  return (
    <svg {...COMMON_SVG_PROPS}>
      <path
        fill="#5865F2"
        d="M20.317 4.3698a19.7913 19.7913 0 0 0-4.8851-1.5152.0741.0741 0 0 0-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 0 0-.0785-.037 19.7363 19.7363 0 0 0-4.8852 1.515.0699.0699 0 0 0-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 0 0 .0312.0561c2.0528 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 0 0 .0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 0 0-.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 0 1-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743.0743 0 0 1 .0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 0 1 .0785.0095c.1202.099.246.1981.3728.2924a.077.077 0 0 1-.0066.1276 12.2986 12.2986 0 0 1-1.873.8914.0766.0766 0 0 0-.0407.1067c.3604.698.7719 1.3628 1.225 1.9932a.076.076 0 0 0 .0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 0 0 .0313-.0552c.5004-5.177-.8382-9.6739-3.5485-13.6604a.061.061 0 0 0-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z"
      />
    </svg>
  )
}

// ─── Slack — four-colour pinwheel (cyan / green / yellow / red) ─────────
// Drawn as four separate paths each in their official colour. The exact
// Slack brand-guidelines palette is hard-coded so the mark reads correctly
// without depending on the surrounding theme.
function SlackGlyph() {
  return (
    <svg {...COMMON_SVG_PROPS}>
      {/* Bottom-left blob — cyan */}
      <path
        fill="#36C5F0"
        d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313z"
      />
      {/* Top-left blob — green */}
      <path
        fill="#2EB67D"
        d="M8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zM8.834 6.313a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312z"
      />
      {/* Top-right blob — yellow */}
      <path
        fill="#ECB22E"
        d="M18.956 8.834a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zM17.688 8.834a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312z"
      />
      {/* Bottom-right blob — red */}
      <path
        fill="#E01E5A"
        d="M15.165 18.956a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.522v-2.522h2.52zM15.165 17.688a2.527 2.527 0 0 1-2.52-2.523 2.526 2.526 0 0 1 2.52-2.52h6.313A2.527 2.527 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z"
      />
    </svg>
  )
}

type SocialLink = {
  label: string
  href: string
  Glyph: React.ComponentType
}

const socialLinks: SocialLink[] = [
  { label: "LinkedIn",  href: "#", Glyph: LinkedInGlyph  },
  { label: "Facebook",  href: "#", Glyph: FacebookGlyph  },
  { label: "Instagram", href: "#", Glyph: InstagramGlyph },
  { label: "X",         href: "#", Glyph: XGlyph         },
  { label: "YouTube",   href: "#", Glyph: YouTubeGlyph   },
  { label: "GitHub",    href: "#", Glyph: GitHubGlyph    },
  { label: "WhatsApp",  href: "#", Glyph: WhatsAppGlyph  },
  { label: "Discord",   href: "#", Glyph: DiscordGlyph   },
  { label: "Slack",     href: "#", Glyph: SlackGlyph     },
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
            <span
              className="text-lg font-semibold tracking-tight"
              style={moltraceWordmark3DStyle}
            >
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
          Bottom row: social section (title + brand-coloured icons) + compliance
          badges + copyright.
          - Social icons render in each platform's default brand colour
            (LinkedIn blue, Facebook blue, Instagram rainbow gradient, X
            black, YouTube red, GitHub dark) so the "Join our Community"
            framing reads instantly. The chip wrapper keeps the modern
            soft-lift hover from the previous monochrome version, just
            without recolouring the glyph itself.
          - Compliance badges read like trust seals: teal-tinted border,
            soft-teal fill, monospaced uppercase label.
        */}
        <div className="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
          <section
            data-testid="footer-social-section"
            className="space-y-3"
          >
            <p
              data-testid="footer-social-title"
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              Join our Community
            </p>
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
                  className="group flex h-10 w-10 items-center justify-center rounded-xl border border-transparent transition-all hover:-translate-y-px hover:border-[color:var(--mt-teal)]/30 hover:bg-muted/40 active:translate-y-0"
                >
                  <Glyph />
                </Link>
              ))}
            </nav>
          </section>

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
