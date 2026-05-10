"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useMemo } from "react"
import {
  Bot,
  Boxes,
  Building2,
  ClipboardCheck,
  ClipboardList,
  FileText,
  FlaskConical,
  FolderOpen,
  HeartPulse,
  Home,
  Library,
  PackageCheck,
  Scale,
  Settings,
  SlidersHorizontal,
} from "lucide-react"
import { SpectraCheckLogoIcon } from "@/components/branding/spectracheck-logo-icon"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"
import { cn } from "@/lib/utils"
import { useTenant } from "@/src/lib/tenant/tenant-context"

type PrimaryNavItem = {
  href: string
  label: string
  icon: React.ComponentType<{ className?: string }>
}

type MoreNavItem = {
  href: string
  label: string
  icon: React.ComponentType<{ className?: string }>
}

const primaryNavItems: PrimaryNavItem[] = [
  { href: "/dashboard", label: "Home", icon: Home },
  { href: "/spectracheck", label: "SpectraCheck", icon: SpectraCheckLogoIcon },
  { href: "/regulatory", label: "Regulatory", icon: Scale },
  { href: "/reactions", label: "Reactions", icon: FlaskConical },
]

const baseMoreNavItems: MoreNavItem[] = [
  { href: "/projects", label: "Projects", icon: FolderOpen },
  { href: "/compounds", label: "Compounds", icon: Boxes },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/actions", label: "Action Queue", icon: ClipboardList },
  { href: "/knowledge", label: "Knowledge", icon: Library },
  { href: "/ml", label: "ML / AI", icon: Bot },
  { href: "/admin/system", label: "Admin", icon: SlidersHorizontal },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
]

const adminMoreNavItems: MoreNavItem[] = [
  { href: "/admin/tenants", label: "Tenant Admin", icon: Building2 },
  { href: "/admin/tenant-summary#onboarding", label: "Onboarding", icon: ClipboardCheck },
  { href: "/admin/tenant-summary#health-score", label: "Health Score", icon: HeartPulse },
  { href: "/admin/tenant-summary#procurement-packages", label: "Procurement Packages", icon: PackageCheck },
]

function hrefPath(href: string) {
  return href.split(/[?#]/)[0] || href
}

export function MobileBottomNav() {
  const pathname = usePathname()
  const { isAdmin } = useTenant()
  const moreNavItems = useMemo(
    () => (isAdmin ? [...baseMoreNavItems, ...adminMoreNavItems] : baseMoreNavItems),
    [isAdmin],
  )
  const moreActive = useMemo(
    () => moreNavItems.some((item) => pathname === hrefPath(item.href) || pathname.startsWith(`${hrefPath(item.href)}/`)),
    [moreNavItems, pathname],
  )

  return (
    <nav
      aria-label="Mobile bottom navigation"
      className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/90 lg:hidden"
    >
      <div className="mx-auto grid max-w-screen-sm grid-cols-5 gap-1 px-2 pt-2 pb-[calc(env(safe-area-inset-bottom)+0.5rem)]">
        {primaryNavItems.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`)
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "relative inline-flex min-h-12 min-w-0 flex-col items-center justify-center gap-1 rounded-md px-1 text-[11px] font-medium",
                isActive ? "bg-secondary text-foreground" : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground",
              )}
              style={
                isActive
                  ? { boxShadow: "inset 0 2px 0 0 var(--mt-teal)" }
                  : undefined
              }
            >
              <item.icon
                className={cn(
                  "h-4 w-4 shrink-0",
                  isActive && "text-[color:var(--mt-teal)]",
                )}
              />
              <span className="truncate">{item.label}</span>
            </Link>
          )
        })}
        <Sheet>
          <SheetTrigger asChild>
            <Button
              type="button"
              variant={moreActive ? "secondary" : "ghost"}
              className={cn(
                "min-h-12 min-w-0 flex-col gap-1 rounded-md px-1 text-[11px]",
                !moreActive && "text-muted-foreground hover:bg-secondary/50 hover:text-foreground",
              )}
            >
              <SlidersHorizontal className="h-4 w-4 shrink-0" />
              <span className="truncate">More</span>
            </Button>
          </SheetTrigger>
          <SheetContent side="bottom" className="max-h-[80vh] rounded-t-2xl px-0 pb-[calc(env(safe-area-inset-bottom)+1rem)]">
            <SheetHeader className="px-4">
              <SheetTitle>More</SheetTitle>
            </SheetHeader>
            <div className="mt-3 grid grid-cols-1 gap-1 px-2">
              {moreNavItems.map((item) => {
                const itemPath = hrefPath(item.href)
                const isActive = pathname === itemPath || pathname.startsWith(`${itemPath}/`)
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "relative inline-flex min-h-12 items-center gap-3 rounded-md px-3 text-sm font-medium",
                      isActive
                        ? "bg-secondary text-foreground"
                        : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground",
                    )}
                    style={
                      isActive
                        ? { boxShadow: "inset 3px 0 0 0 var(--mt-teal)" }
                        : undefined
                    }
                  >
                    <item.icon
                      className={cn(
                        "h-4 w-4 shrink-0",
                        isActive && "text-[color:var(--mt-teal)]",
                      )}
                    />
                    {item.label}
                  </Link>
                )
              })}
            </div>
          </SheetContent>
        </Sheet>
      </div>
    </nav>
  )
}
