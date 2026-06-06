"use client"

import Link from "next/link"
import { Button } from "@/components/ui/button"
import { ThemeToggle } from "@/components/theme-toggle"
import { moltraceTraceClassName, moltraceWordmark3DStyle } from "@/components/branding/moltrace-wordmark"
import { MoleculeLogoMark } from "@/components/branding/molecule-logo-mark"
import { useIsMobile } from "@/hooks/use-mobile"
import {
  ArrowRight,
  BookOpen,
  Building2,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  FileCheck,
  FlaskConical,
  GraduationCap,
  Menu,
  Microscope,
  Pill,
  ShieldCheck,
  Waves,
  Workflow,
  type LucideIcon,
} from "lucide-react"
import { useState } from "react"
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet"

const navItems = [
  { label: "Platform", href: "/platform#platform" },
  { label: "Solutions", href: "/platform#solutions" },
  { label: "Enterprise", href: "/platform#enterprise" },
  { label: "Documentation", href: "/platform#docs" },
]

type DropdownItem = { label: string; sub: string; icon: LucideIcon; href: string }

// All four Platform module pages are in-app marketing routes. Each
// lives at a top-level slug matching its dropdown label (slight rename
// for /reaction-optimization vs ReactionIQ, /regulatory-hub vs Regulatory
// Intelligence Hub). External docs links are reserved for deeper
// technical-reference content under docs.moltrace.co.
const dropdowns: Record<string, DropdownItem[]> = {
  Platform: [
    { label: "Spectroscopy Intelligence",   sub: "NMR · MS · Structure elucidation",  icon: Waves,        href: "/spectroscopy" },
    { label: "Regulatory Intelligence Hub", sub: "ICH · FDA · EMA compliance",        icon: ShieldCheck,  href: "/regulatory-hub" },
    { label: "Reaction Optimization",       sub: "Bayesian · Multi-objective",        icon: FlaskConical, href: "/reaction-optimization" },
    { label: "Integrations",                sub: "Bruker · Agilent · LIMS",           icon: Workflow,     href: "/integrations" },
  ],
  Solutions: [
    { label: "Pharmaceutical R&D",  sub: "Drug discovery & development", icon: Pill,          href: "/pharmaceutical-rd" },
    { label: "Academic Research",   sub: "University & institute labs",  icon: GraduationCap, href: "/academic-research" },
    { label: "CRO / Analytical",    sub: "Contract research orgs",       icon: Microscope,    href: "/cro-analytical" },
    { label: "Regulatory Affairs",  sub: "Dossier & submission teams",   icon: FileCheck,     href: "/regulatory-affairs" },
  ],
}

// Icons for the top-level nav entries that don't have a dropdown (Enterprise,
// Documentation). Keyed by label so the mobile sheet can render a single
// icon-led card per entry — same visual language as the dropdown children.
const topLevelIcons: Record<string, LucideIcon> = {
  Enterprise: Building2,
  Documentation: BookOpen,
}

export function Header() {
  const [open, setOpen] = useState(false)
  const [activeDropdown, setActiveDropdown] = useState<string | null>(null)
  const isMobile = useIsMobile()

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 md:backdrop-blur md:supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-8">
          <Link href="/" className="flex items-center gap-2">
            <MoleculeLogoMark className="h-8 w-8" />
            <span
              className="text-lg font-semibold tracking-tight"
              style={moltraceWordmark3DStyle}
            >
              <span className="font-bold text-foreground">Mol</span>
              <span className={moltraceTraceClassName}>Trace</span>
            </span>
          </Link>

          <nav className={`${isMobile ? "hidden" : "flex"} items-center gap-1`}>
            {navItems.map((item) => {
              const hasDropdown = item.label in dropdowns
              if (!hasDropdown) {
                return (
                  <Link
                    key={item.label}
                    href={item.href}
                    className="rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {item.label}
                  </Link>
                )
              }
              return (
                <div
                  key={item.label}
                  className="relative"
                  onMouseEnter={() => setActiveDropdown(item.label)}
                  onMouseLeave={() => setActiveDropdown(null)}
                >
                  <Link
                    href={item.href}
                    className="flex items-center gap-1 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {item.label}
                    <ChevronDown
                      className={`h-3 w-3 transition-transform duration-150 ${activeDropdown === item.label ? "rotate-180" : ""}`}
                    />
                  </Link>

                  {activeDropdown === item.label && (
                    <div className="absolute left-0 top-full z-50 pt-1">
                      <div className="min-w-[260px] overflow-hidden rounded-xl border bg-popover p-2 shadow-lg">
                        {dropdowns[item.label].map((sub) => {
                          const isExternal = /^https?:\/\//i.test(sub.href)
                          return (
                            <Link
                              key={sub.label}
                              href={sub.href}
                              className="block rounded-lg px-3 py-2.5 transition-colors hover:bg-muted"
                              {...(isExternal ? { target: "_blank", rel: "noopener noreferrer" } : null)}
                            >
                              <div className="text-sm font-semibold text-foreground">{sub.label}</div>
                              <div className="mt-0.5 font-mono text-[10px] tracking-wider text-muted-foreground">
                                {sub.sub}
                              </div>
                            </Link>
                          )
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </nav>
        </div>

        <div className="flex items-center gap-3">
          <ThemeToggle />
          <div className={`${isMobile ? "hidden" : "flex"} items-center gap-2`}>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/sign-in">Sign In</Link>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link href="/sign-up">Sign Up</Link>
            </Button>
            <Button size="sm" asChild>
              <Link href="#demo">Request Demo</Link>
            </Button>
          </div>

          {isMobile ? (
            <Sheet open={open} onOpenChange={setOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon">
                  <Menu className="h-5 w-5" />
                  <span className="sr-only">Toggle menu</span>
                </Button>
              </SheetTrigger>
              {/*
                Ultramodern mobile sidebar refresh:
                - Glassy gradient background + subtle radial tint behind the
                  brand block (teal soft glow)
                - Icon-led item cards with soft-teal squircle, label + sub,
                  trailing chevron that slides on hover
                - Section eyebrows in teal uppercase tracking (matches the
                  rest of the brand's eyebrow pattern)
                - Pinned CTA footer with gradient teal "Request Demo" button
              */}
              <SheetContent
                side="right"
                data-testid="marketing-mobile-sidebar"
                className="flex w-full max-w-[360px] flex-col gap-0 border-l border-l-[color:var(--mt-teal)]/15 bg-gradient-to-b from-background via-background to-background/95 p-0 backdrop-blur supports-[backdrop-filter]:bg-background/85"
              >
                <SheetTitle className="sr-only">Navigation Menu</SheetTitle>

                {/* Brand block */}
                <div
                  className="relative flex items-center gap-3 border-b border-b-[color:var(--mt-teal)]/10 px-5 py-5"
                  style={{
                    background:
                      "radial-gradient(circle at 0% 0%, var(--mt-teal-soft) 0%, transparent 60%)",
                  }}
                >
                  <Link
                    href="/"
                    onClick={() => setOpen(false)}
                    className="flex items-center gap-3"
                  >
                    <MoleculeLogoMark className="h-9 w-9 rounded-xl" />
                    <span>
                      <span
                        className="block text-base font-bold leading-tight tracking-tight"
                        style={moltraceWordmark3DStyle}
                      >
                        <span className="text-foreground">Mol</span>
                        <span className={moltraceTraceClassName}>Trace</span>
                      </span>
                      <span
                        className="block font-mono text-[10px] font-medium uppercase tracking-[0.22em] text-muted-foreground"
                      >
                        Scientific intelligence
                      </span>
                    </span>
                  </Link>
                </div>

                {/* Scrollable nav body */}
                <nav className="flex-1 space-y-6 overflow-y-auto px-5 py-6">
                  {/* Sectioned dropdowns (Platform, Solutions) */}
                  {(["Platform", "Solutions"] as const).map((sectionLabel) => {
                    const sectionHref = navItems.find((n) => n.label === sectionLabel)?.href ?? "#"
                    return (
                      <section key={sectionLabel} className="space-y-2.5">
                        <Link
                          href={sectionHref}
                          onClick={() => setOpen(false)}
                          className="inline-flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.22em] transition-colors hover:opacity-80"
                          style={{ color: "var(--mt-teal)" }}
                        >
                          {sectionLabel}
                          <ChevronRight className="h-3 w-3" aria-hidden />
                        </Link>
                        <div className="space-y-1">
                          {dropdowns[sectionLabel].map((sub) => {
                            const Icon = sub.icon
                            const isExternal = /^https?:\/\//i.test(sub.href)
                            return (
                              <Link
                                key={sub.label}
                                href={sub.href}
                                onClick={() => setOpen(false)}
                                className="group flex items-center gap-3 rounded-xl border border-transparent px-3 py-3 transition-all hover:-translate-y-px hover:border-[color:var(--mt-teal)]/30 hover:bg-[color:var(--mt-teal-soft)] active:translate-y-0"
                                {...(isExternal ? { target: "_blank", rel: "noopener noreferrer" } : null)}
                              >
                                <span
                                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-colors"
                                  style={{ backgroundColor: "var(--mt-teal-soft)" }}
                                >
                                  <Icon
                                    className="h-4 w-4 transition-transform group-hover:scale-110"
                                    style={{ color: "var(--mt-teal)" }}
                                    aria-hidden
                                  />
                                </span>
                                <span className="min-w-0 flex-1">
                                  {/* Wrap rather than truncate: the narrow mobile
                                      sheet (and smaller/legacy viewports) can't fit
                                      the longer item titles + descriptions on one
                                      line, and `truncate` clipped them with an
                                      ellipsis. `break-words` lets the full text flow
                                      onto multiple lines so every item stays legible. */}
                                  <span className="block break-words text-sm font-semibold text-foreground">
                                    {sub.label}
                                  </span>
                                  <span className="mt-0.5 block break-words font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                                    {sub.sub}
                                  </span>
                                </span>
                                <ChevronRight
                                  className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
                                  style={{ color: "var(--mt-teal)" }}
                                  aria-hidden
                                />
                              </Link>
                            )
                          })}
                        </div>
                      </section>
                    )
                  })}

                  {/* Single-link sections (Enterprise, Documentation) */}
                  <section className="space-y-1.5">
                    {navItems
                      .filter((item) => !(item.label in dropdowns))
                      .map((item) => {
                        const Icon = topLevelIcons[item.label]
                        return (
                          <Link
                            key={item.label}
                            href={item.href}
                            onClick={() => setOpen(false)}
                            className="group flex items-center gap-3 rounded-xl border border-transparent px-3 py-3 transition-all hover:-translate-y-px hover:border-[color:var(--mt-teal)]/30 hover:bg-[color:var(--mt-teal-soft)] active:translate-y-0"
                          >
                            <span
                              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
                              style={{ backgroundColor: "var(--mt-teal-soft)" }}
                            >
                              {Icon ? (
                                <Icon
                                  className="h-4 w-4 transition-transform group-hover:scale-110"
                                  style={{ color: "var(--mt-teal)" }}
                                  aria-hidden
                                />
                              ) : (
                                <ClipboardCheck
                                  className="h-4 w-4"
                                  style={{ color: "var(--mt-teal)" }}
                                  aria-hidden
                                />
                              )}
                            </span>
                            <span className="flex-1 text-sm font-semibold text-foreground">
                              {item.label}
                            </span>
                            <ChevronRight
                              className="h-3.5 w-3.5 shrink-0 transition-transform group-hover:translate-x-0.5"
                              style={{ color: "var(--mt-teal)" }}
                              aria-hidden
                            />
                          </Link>
                        )
                      })}
                  </section>
                </nav>

                {/* Pinned CTA footer */}
                <div
                  className="space-y-2 border-t border-t-[color:var(--mt-teal)]/10 bg-background/95 px-5 pt-4 pb-[calc(env(safe-area-inset-bottom)+1rem)] backdrop-blur"
                >
                  <div className="grid grid-cols-2 gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="font-mono text-[11px] font-bold uppercase tracking-[0.16em]"
                      asChild
                      onClick={() => setOpen(false)}
                    >
                      <Link href="/sign-in">Sign In</Link>
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="border-[color:var(--mt-teal)]/40 font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-foreground hover:border-[color:var(--mt-teal)] hover:bg-[color:var(--mt-teal-soft)]"
                      asChild
                      onClick={() => setOpen(false)}
                    >
                      <Link href="/sign-up">Sign Up</Link>
                    </Button>
                  </div>
                  <Button
                    asChild
                    onClick={() => setOpen(false)}
                    className="group h-11 w-full font-mono text-[11px] font-bold uppercase tracking-[0.18em] text-white shadow-lg transition-all hover:-translate-y-0.5 hover:shadow-xl hover:shadow-[color:var(--mt-teal)]/30 active:translate-y-0"
                    style={{
                      background:
                        "linear-gradient(135deg, var(--mt-teal) 0%, #00B884 100%)",
                    }}
                  >
                    <Link
                      href="#demo"
                      data-testid="marketing-mobile-sidebar-demo-cta"
                      className="inline-flex items-center justify-center gap-2"
                    >
                      Request Demo
                      <ArrowRight
                        className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5"
                        aria-hidden
                      />
                    </Link>
                  </Button>
                </div>
              </SheetContent>
            </Sheet>
          ) : null}
        </div>
      </div>
    </header>
  )
}
