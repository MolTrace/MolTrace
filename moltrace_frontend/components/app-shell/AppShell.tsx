"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { BarChart3, FileText, FlaskConical, Home, LineChart, Settings, ShieldCheck } from "lucide-react"
import { cn } from "@/lib/utils"
import { moltraceTraceClassName } from "@/components/branding/moltrace-wordmark"
import { MoleculeLogoMark } from "@/components/branding/molecule-logo-mark"
import { SpectraCheckLogoIcon } from "@/components/branding/spectracheck-logo-icon"
import { useIsMobile } from "@/hooks/use-mobile"

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: Home },
  { href: "/platform", label: "Platform", icon: LineChart },
  { href: "/spectracheck", label: "SpectraCheck", icon: SpectraCheckLogoIcon },
  { href: "/regulatory", label: "Regentry", icon: ShieldCheck },
  { href: "/reactions", label: "Reaction Optimization", icon: FlaskConical },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/roi", label: "Automation ROI", icon: BarChart3 },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
]

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const isMobile = useIsMobile()
  const renderNavLink = (item: (typeof navItems)[number], mode: "desktop" | "mobile") => {
    const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href))
    const Icon = item.icon

    return (
      <Link
        key={item.href}
        href={item.href}
        className={
          mode === "mobile"
            ? cn(
                "inline-flex min-h-10 shrink-0 items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-4 text-sm text-slate-300",
                active && "border-cyan-300/30 bg-cyan-400/10 text-cyan-100",
              )
            : cn(
                "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-slate-300 transition hover:bg-white/[0.06] hover:text-white",
                active && "bg-cyan-400/10 text-cyan-100 ring-1 ring-cyan-300/20",
              )
        }
      >
        <Icon className="h-4 w-4" aria-hidden="true" />
        {item.label}
      </Link>
    )
  }

  return (
    <div className="min-h-screen overflow-x-hidden bg-[#070b12] text-white">
      <div className={cn("flex min-h-screen", isMobile ? "flex-col" : "flex-row")}>
        {!isMobile ? (
          <aside className="w-72 shrink-0 border-r border-white/10 bg-white/[0.035] px-4 py-5 backdrop-blur">
            <Link href="/" className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3">
              <MoleculeLogoMark className="h-10 w-10 rounded-xl" />
              <span>
                <span className="block text-sm font-semibold tracking-wide">
                  <span className="font-bold text-white">Mol</span>
                  <span className={moltraceTraceClassName}>Trace</span>
                </span>
                <span className="block text-xs text-slate-400">Scientific intelligence</span>
              </span>
            </Link>
            <nav className="mt-6 space-y-1">
              {navItems.map((item) => renderNavLink(item, "desktop"))}
            </nav>
          </aside>
        ) : null}

        <div className="flex min-w-0 flex-1 flex-col">
          {isMobile ? (
            <header className="sticky top-0 z-30 border-b border-white/10 bg-[#070b12]/90 backdrop-blur">
              <div className="flex items-center justify-between px-4 py-3">
                <Link href="/" className="flex items-center gap-2 font-semibold">
                  <MoleculeLogoMark className="h-5 w-5 rounded-sm" />
                  <span>
                    <span className="font-bold text-white">Mol</span>
                    <span className={moltraceTraceClassName}>Trace</span>
                  </span>
                </Link>
              </div>
              <nav className="flex gap-2 overflow-x-auto px-4 pb-3 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                {navItems.map((item) => renderNavLink(item, "mobile"))}
              </nav>
            </header>
          ) : null}

          <main className={cn("min-w-0 flex-1 overflow-x-hidden", isMobile ? "px-4 py-6 sm:px-6" : "px-8 py-8")}>
            {children}
          </main>
        </div>
      </div>
    </div>
  )
}
