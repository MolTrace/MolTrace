import Link from "next/link"
import {
  Facebook,
  Github,
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

type SocialLink =
  | { label: string; href: string; Icon: LucideIcon; kind: "fill"; solidColor: string }
  | { label: string; href: string; kind: "instagram" }
  | { label: string; href: string; kind: "x" }
  | { label: string; href: string; Icon: LucideIcon; kind: "github" }
  | { label: string; href: string; Icon: LucideIcon; kind: "stroke" }
  | { label: string; href: string; Icon: LucideIcon; kind: "youtube" }

/** Primary brand solids (filled glyphs where paths allow; stroked marks otherwise). */
const socialLinks: SocialLink[] = [
  { label: "LinkedIn", href: "#", Icon: Linkedin, kind: "fill", solidColor: "#0A66C2" },
  { label: "Facebook", href: "#", Icon: Facebook, kind: "fill", solidColor: "#1877F2" },
  { label: "Instagram", href: "#", kind: "instagram" },
  { label: "X", href: "#", kind: "x" },
  { label: "YouTube", href: "#", Icon: Youtube, kind: "youtube" },
  { label: "GitHub", href: "#", Icon: Github, kind: "github" },
]

/** Lucide’s Instagram mixes rect + arc + hairline line — single-fill breaks the lens; use brand gradient + white detail */
const INSTAGRAM_GRADIENT_ID = "moltrace-footer-instagram-gradient"

/** Lucide X is two bare strokes — dedicated SVG matches brand weight/contrast at footer size */
function XGlyph() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-5 w-5 shrink-0 text-black dark:text-neutral-50"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <path d="M5 5 L19 19" stroke="currentColor" strokeWidth="2.75" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M19 5 L5 19" stroke="currentColor" strokeWidth="2.75" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function InstagramGlyph() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-5 w-5 shrink-0"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <defs>
        <linearGradient id={INSTAGRAM_GRADIENT_ID} x1="2" y1="22" x2="22" y2="2" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#FCAF45" />
          <stop offset="33%" stopColor="#E1306C" />
          <stop offset="66%" stopColor="#C13584" />
          <stop offset="100%" stopColor="#833AB4" />
        </linearGradient>
      </defs>
      <rect width="20" height="20" x="2" y="2" rx="5" ry="5" fill={`url(#${INSTAGRAM_GRADIENT_ID})`} />
      <path
        d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"
        fill="none"
        stroke="#FFFFFF"
        strokeWidth="1.65"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="17.5" cy="6.5" r="1.05" fill="#FFFFFF" />
    </svg>
  )
}

function SocialGlyph({ link }: { link: SocialLink }) {
  if (link.kind === "instagram") {
    return <InstagramGlyph />
  }
  if (link.kind === "x") {
    return <XGlyph />
  }
  if (link.kind === "youtube") {
    return (
      <link.Icon
        className="h-5 w-5 shrink-0 [&_path:nth-of-type(1)]:fill-[#FF0000] [&_path:nth-of-type(1)]:stroke-none [&_path:nth-of-type(2)]:fill-[#FFFFFF] [&_path:nth-of-type(2)]:stroke-none"
        fill="none"
        stroke="none"
        strokeWidth={0}
        aria-hidden
      />
    )
  }
  if (link.kind === "github") {
    return (
      <link.Icon
        className="h-5 w-5 shrink-0 text-[#181717] dark:text-neutral-100"
        fill="currentColor"
        stroke="none"
        strokeWidth={0}
        aria-hidden
      />
    )
  }
  if (link.kind === "fill") {
    return (
      <link.Icon className="h-5 w-5 shrink-0" fill={link.solidColor} stroke="none" strokeWidth={0} aria-hidden />
    )
  }
  return <link.Icon className="h-5 w-5 shrink-0" aria-hidden />
}

export function Footer() {
  return (
    <footer id="docs" className="border-t bg-muted/30">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8 lg:py-16">
        <div className="grid grid-cols-2 gap-8 lg:grid-cols-5">
          <div className="col-span-2 lg:col-span-1">
            <Link href="/" className="flex items-center gap-2">
              <MoleculeLogoMark className="h-8 w-8" />
              <span className="text-lg font-semibold tracking-tight">
                <span className="font-bold text-foreground">Mol</span>
                <span className={moltraceTraceClassName}>Trace</span>
              </span>
            </Link>
            <p className="mt-4 text-sm text-muted-foreground">
              AI-native scientific intelligence for chemistry and pharmaceutical R&D.
            </p>
          </div>
          <div>
            <h3 className="text-sm font-medium">Platform</h3>
            <ul className="mt-4 space-y-2">
              {navigation.platform.map((item) => (
                <li key={item.name}>
                  <Link href={item.href} className="text-sm text-muted-foreground hover:text-foreground">
                    {item.name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="text-sm font-medium">Company</h3>
            <ul className="mt-4 space-y-2">
              {navigation.company.map((item) => (
                <li key={item.name}>
                  <Link href={item.href} className="text-sm text-muted-foreground hover:text-foreground">
                    {item.name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="text-sm font-medium">Resources</h3>
            <ul className="mt-4 space-y-2">
              {navigation.resources.map((item) => (
                <li key={item.name}>
                  <Link href={item.href} className="text-sm text-muted-foreground hover:text-foreground">
                    {item.name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3 className="text-sm font-medium">Legal</h3>
            <ul className="mt-4 space-y-2">
              {navigation.legal.map((item) => (
                <li key={item.name}>
                  <Link href={item.href} className="text-sm text-muted-foreground hover:text-foreground">
                    {item.name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>
        <nav
          className="mt-10 flex flex-wrap items-center justify-center gap-x-8 gap-y-2"
          aria-label="MolTrace social media"
        >
          {socialLinks.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className="rounded-md p-2 transition-opacity hover:opacity-80"
              aria-label={link.label}
            >
              <SocialGlyph link={link} />
            </Link>
          ))}
        </nav>
        <div className="mt-10 border-t pt-8 sm:mt-12">
          <div className="flex flex-col items-center gap-4 sm:flex-row sm:justify-between">
            <p className="text-sm text-muted-foreground">
              &copy; {COPYRIGHT_YEAR} MolTrace Technologies, Inc. All rights reserved.
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {["SOC 2 Type II", "ICH Compliant", "GDPR Ready", "GxP Validated"].map((badge) => (
                <span
                  key={badge}
                  className="rounded border border-muted-foreground/20 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/50"
                >
                  {badge}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </footer>
  )
}
