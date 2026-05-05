"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { moltraceTraceClassName } from "@/components/branding/moltrace-wordmark"
import { MoleculeLogoMark } from "@/components/branding/molecule-logo-mark"
import { SpectraCheckLogoIcon } from "@/components/branding/spectracheck-logo-icon"
import type { LucideIcon } from "lucide-react"
import {
  LayoutDashboard,
  Bot,
  FolderOpen,
  FlaskConical,
  Scale,
  FileText,
  BarChart3,
  Settings,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  LineChart,
  SlidersHorizontal,
  Users,
  ClipboardList,
  Boxes,
  Package,
  Server,
  Shield,
  ScrollText,
  Bug,
  Rocket,
  Library,
} from "lucide-react"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"

export type SidebarNavItem = {
  name: string
  href: string
  icon: LucideIcon | typeof SpectraCheckLogoIcon
}

const navigation: SidebarNavItem[] = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "AI Services", href: "/ai", icon: Bot },
  { name: "Projects", href: "/projects", icon: FolderOpen },
  { name: "Compounds", href: "/compounds", icon: Boxes },
  { name: "Batches", href: "/batches", icon: Package },
  { name: "SpectraCheck", href: "/spectracheck", icon: SpectraCheckLogoIcon },
  { name: "Regulatory Hub", href: "/regulatory", icon: Scale },
  { name: "Reaction Optimization", href: "/reactions", icon: FlaskConical },
  { name: "Action Queue", href: "/actions", icon: ClipboardList },
  { name: "Knowledge Library", href: "/knowledge", icon: Library },
  { name: "Reports", href: "/reports", icon: FileText },
  { name: "Review", href: "/review", icon: ClipboardList },
  { name: "Automation ROI", href: "/roi", icon: BarChart3 },
  { name: "Platform", href: "/platform", icon: LineChart },
]

const adminNavigation: SidebarNavItem[] = [
  { name: "System", href: "/admin/system", icon: Server },
  { name: "Security", href: "/admin/security", icon: Shield },
  { name: "Audit", href: "/admin/audit", icon: ScrollText },
  { name: "Debug", href: "/admin/debug", icon: Bug },
  { name: "Deployment", href: "/settings/deployment", icon: Rocket },
]

export const appNavigation = navigation
export const appAdminNavigation = adminNavigation

const teamNav: SidebarNavItem[] = [
  { name: "Team", href: "/settings/team", icon: Users },
]

const bottomNav: SidebarNavItem[] = [
  { name: "Settings", href: "/dashboard/settings", icon: Settings },
]

export const appTeamNavigation = teamNav
export const appBottomNavigation = bottomNav

interface AppSidebarProps {
  collapsed: boolean
  onToggle: () => void
}

function adminPathActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(href + "/")
}

function isAnyAdminRoute(pathname: string) {
  return adminNavigation.some((item) => adminPathActive(pathname, item.href))
}

export function AppSidebar({ collapsed, onToggle }: AppSidebarProps) {
  const pathname = usePathname()
  const [adminExpanded, setAdminExpanded] = useState(() =>
    isAnyAdminRoute(pathname)
  )
  const prevPathnameRef = useRef(pathname)

  useEffect(() => {
    const prev = prevPathnameRef.current
    prevPathnameRef.current = pathname
    const enteredAdmin =
      isAnyAdminRoute(pathname) && !isAnyAdminRoute(prev)
    if (enteredAdmin) setAdminExpanded(true)
  }, [pathname])

  const NavLink = ({
    item,
    nested,
  }: {
    item: SidebarNavItem
    nested?: boolean
  }) => {
    const isActive = adminPathActive(pathname, item.href)

    const linkContent = (
      <Link
        href={item.href}
        className={cn(
          "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
          isActive
            ? "bg-secondary text-foreground"
            : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground",
          collapsed && "justify-center px-2",
          nested && !collapsed && "ml-2 border-l border-border pl-3"
        )}
      >
        <item.icon className="h-4 w-4 shrink-0" />
        {!collapsed && <span>{item.name}</span>}
      </Link>
    )

    if (collapsed) {
      return (
        <Tooltip>
          <TooltipTrigger asChild>{linkContent}</TooltipTrigger>
          <TooltipContent side="right">{item.name}</TooltipContent>
        </Tooltip>
      )
    }

    return linkContent
  }

  const adminSectionActive = isAnyAdminRoute(pathname)

  return (
    <TooltipProvider delayDuration={0}>
      <aside
        className={cn(
          "flex h-full flex-col border-r bg-sidebar transition-all duration-200",
          collapsed ? "w-14" : "w-56"
        )}
      >
        {/* Logo */}
        <div className={cn(
          "flex h-14 items-center border-b px-3",
          collapsed ? "justify-center" : "justify-between"
        )}>
          <Link href="/" className="flex items-center gap-2">
            <MoleculeLogoMark className="h-7 w-7" />
            {!collapsed && (
              <span className="font-semibold">
                <span className="text-foreground">Mol</span>
                <span className={moltraceTraceClassName}>Trace</span>
              </span>
            )}
          </Link>
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggle}
            className={cn("h-7 w-7", collapsed && "absolute -right-3.5 top-3.5 z-10 rounded-full border bg-background shadow-sm")}
          >
            {collapsed ? (
              <ChevronRight className="h-3.5 w-3.5" />
            ) : (
              <ChevronLeft className="h-3.5 w-3.5" />
            )}
          </Button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 overflow-y-auto p-2">
          {navigation.map((item) => (
            <NavLink key={item.name} item={item} />
          ))}
        </nav>

        {/* Team — above Admin */}
        <div className="border-t p-2">
          {teamNav.map((item) => (
            <NavLink key={item.name} item={item} />
          ))}
        </div>

        {/* Admin — collapsible, above Settings */}
        <div className="border-t p-2">
          {collapsed ? (
            <div className="space-y-1">
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    onClick={() => setAdminExpanded((e) => !e)}
                    className={cn(
                      "flex w-full items-center justify-center rounded-md px-2 py-2 text-sm font-medium transition-colors",
                      adminSectionActive
                        ? "bg-secondary text-foreground"
                        : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
                    )}
                    aria-expanded={adminExpanded}
                    aria-label="Admin"
                  >
                    <SlidersHorizontal className="h-4 w-4 shrink-0" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="right">Admin</TooltipContent>
              </Tooltip>
              {adminExpanded &&
                adminNavigation.map((item) => (
                  <NavLink key={item.name} item={item} nested />
                ))}
            </div>
          ) : (
            <div className="space-y-1">
              <button
                type="button"
                onClick={() => setAdminExpanded((e) => !e)}
                className={cn(
                  "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  adminSectionActive
                    ? "bg-secondary text-foreground"
                    : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground"
                )}
                aria-expanded={adminExpanded}
              >
                <SlidersHorizontal className="h-4 w-4 shrink-0" />
                <span className="flex-1 text-left">Admin</span>
                <ChevronDown
                  className={cn(
                    "h-4 w-4 shrink-0 transition-transform",
                    adminExpanded && "rotate-180"
                  )}
                />
              </button>
              {adminExpanded &&
                adminNavigation.map((item) => (
                  <NavLink key={item.name} item={item} nested />
                ))}
            </div>
          )}
        </div>

        {/* Bottom Navigation */}
        <div className="border-t p-2">
          {bottomNav.map((item) => (
            <NavLink key={item.name} item={item} />
          ))}
        </div>
      </aside>
    </TooltipProvider>
  )
}
