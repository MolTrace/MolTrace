"use client"

import Link from "next/link"
import { Button } from "@/components/ui/button"
import { ThemeToggle } from "@/components/theme-toggle"
import { moltraceTraceClassName } from "@/components/branding/moltrace-wordmark"
import { MoleculeLogoMark } from "@/components/branding/molecule-logo-mark"
import { useIsMobile } from "@/hooks/use-mobile"
import { Menu, ChevronDown } from "lucide-react"
import { useState } from "react"
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet"

const navItems = [
  { label: "Platform", href: "/platform#platform" },
  { label: "Solutions", href: "/platform#solutions" },
  { label: "Enterprise", href: "/platform#enterprise" },
  { label: "Documentation", href: "/platform#docs" },
]

const dropdowns: Record<string, { label: string; sub: string }[]> = {
  Platform: [
    { label: "Spectroscopy Intelligence",   sub: "NMR · MS · Structure elucidation"  },
    { label: "Regulatory Intelligence Hub", sub: "ICH · FDA · EMA compliance"        },
    { label: "Reaction Optimization",       sub: "Bayesian · Multi-objective"         },
    { label: "Integrations",                sub: "Bruker · Agilent · LIMS"           },
  ],
  Solutions: [
    { label: "Pharmaceutical R&D",  sub: "Drug discovery & development" },
    { label: "Academic Research",   sub: "University & institute labs"  },
    { label: "CRO / Analytical",    sub: "Contract research orgs"       },
    { label: "Regulatory Affairs",  sub: "Dossier & submission teams"   },
  ],
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
            <span className="text-lg font-semibold tracking-tight">
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
                        {dropdowns[item.label].map((sub) => (
                          <a
                            key={sub.label}
                            href="#"
                            className="block rounded-lg px-3 py-2.5 transition-colors hover:bg-muted"
                          >
                            <div className="text-sm font-semibold text-foreground">{sub.label}</div>
                            <div className="mt-0.5 font-mono text-[10px] tracking-wider text-muted-foreground">
                              {sub.sub}
                            </div>
                          </a>
                        ))}
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
              <SheetContent side="right" className="w-[300px]">
                <SheetTitle className="sr-only">Navigation Menu</SheetTitle>
                <nav className="flex flex-col gap-4 pt-8">
                  {navItems.map((item) => {
                    const hasDropdown = item.label in dropdowns
                    return (
                      <div key={item.label}>
                        <Link
                          href={item.href}
                          onClick={() => setOpen(false)}
                          className="text-lg text-muted-foreground transition-colors hover:text-foreground"
                        >
                          {item.label}
                        </Link>
                        {hasDropdown && (
                          <div className="ml-3 mt-2 flex flex-col gap-1.5 border-l pl-3">
                            {dropdowns[item.label].map((sub) => (
                              <a
                                key={sub.label}
                                href="#"
                                onClick={() => setOpen(false)}
                                className="text-sm text-muted-foreground hover:text-foreground"
                              >
                                {sub.label}
                              </a>
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })}
                  <div className="mt-4 flex flex-col gap-2">
                    <Button variant="outline" asChild>
                      <Link href="/sign-in">Sign In</Link>
                    </Button>
                    <Button variant="secondary" asChild>
                      <Link href="/sign-up">Sign Up</Link>
                    </Button>
                    <Button asChild>
                      <Link href="#demo">Request Demo</Link>
                    </Button>
                  </div>
                </nav>
              </SheetContent>
            </Sheet>
          ) : null}
        </div>
      </div>
    </header>
  )
}
