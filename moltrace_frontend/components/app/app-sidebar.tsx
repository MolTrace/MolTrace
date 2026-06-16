"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { moltraceTraceClassName } from "@/components/branding/moltrace-wordmark"
import { MoleculeLogoMark } from "@/components/branding/molecule-logo-mark"
import { ProgramsLogoIcon } from "@/components/branding/programs-logo-icon"
import type { LucideIcon } from "lucide-react"
import {
  LayoutDashboard,
  Bot,
  FolderOpen,
  BarChart3,
  Settings,
  ChevronLeft,
  ChevronRight,
  LineChart,
  SlidersHorizontal,
  Users,
  ClipboardList,
  Boxes,
  Server,
  Shield,
  ScrollText,
  Bug,
  Rocket,
  Activity,
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
  icon: LucideIcon | typeof ProgramsLogoIcon
}

const navigation: SidebarNavItem[] = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "Projects", href: "/projects", icon: FolderOpen },
  { name: "Compound / Batch", href: "/compounds", icon: Boxes },
  { name: "Programs", href: "/spectracheck", icon: ProgramsLogoIcon },
  { name: "Action Queue", href: "/actions", icon: ClipboardList },
  { name: "Automation ROI", href: "/roi", icon: BarChart3 },
  { name: "ML / AI Governance", href: "/ai", icon: Bot },
  { name: "Home", href: "/platform", icon: LineChart },
]

const adminNavigation: SidebarNavItem[] = [
  { name: "System", href: "/admin/system", icon: Server },
  { name: "Security", href: "/admin/security", icon: Shield },
  { name: "Audit", href: "/admin/audit", icon: ScrollText },
  { name: "Debug", href: "/admin/debug", icon: Bug },
  { name: "Ops", href: "/admin/ops", icon: Activity },
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

export function AppSidebar({ collapsed, onToggle }: AppSidebarProps) {
  const pathname = usePathname()

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
          "group/navlink relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold tracking-tight transition-all duration-200",
          isActive
            ? "bg-secondary text-foreground shadow-sm"
            : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground hover:shadow-sm",
          collapsed && "justify-center px-2",
          nested && !collapsed && "ml-2 border-l border-border pl-3"
        )}
        style={
          isActive
            ? {
                boxShadow: collapsed
                  ? `inset 2px 0 0 0 var(--mt-teal)`
                  : `inset 3px 0 0 0 var(--mt-teal)`,
              }
            : undefined
        }
      >
        <item.icon
          className="h-4 w-4 shrink-0"
          style={isActive ? { color: "var(--mt-teal)" } : undefined}
        />
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

  return (
    <TooltipProvider delayDuration={0}>
      <aside
        className={cn(
          // Solid bg-sidebar (no /95 alpha) + no backdrop-blur. The blurred
          // frosted-glass sidebar promoted itself to a persistent GPU
          // compositor layer the full height of the viewport. With the main
          // scroll column next to it, Chrome/Safari can fail to keep both
          // layers stable as the user scrolls — culling the main content
          // intermittently and re-promoting it on the next paint, producing
          // the "entire area disappears and reappears" symptom. Solid
          // background stays in document flow and never triggers promotion.
          "flex h-full flex-col border-r border-border/70 bg-sidebar transition-[width] duration-200",
          collapsed ? "w-14" : "w-56"
        )}
      >
        {/* Logo */}
        <div className={cn(
          "flex h-14 items-center border-b border-border/70 px-3",
          collapsed ? "justify-center" : "justify-between"
        )}>
          <Link href="/" className="flex items-center gap-2">
            <MoleculeLogoMark className="h-7 w-7" />
            {!collapsed && (
              <span className="text-[15px] font-semibold tracking-tight">
                <span className="font-bold text-foreground">Mol</span>
                <span className={moltraceTraceClassName}>Trace</span>
              </span>
            )}
          </Link>
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggle}
            className={cn("h-7 w-7", collapsed && "absolute -right-3.5 top-3.5 z-10 rounded-full border border-border/70 bg-background/95 shadow-sm backdrop-blur-sm")}
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
          {!collapsed ? (
            <p className="px-3 pt-1 pb-2 font-mono text-[9px] font-bold uppercase tracking-[0.18em] text-muted-foreground/70">
              Workspace
            </p>
          ) : null}
          {navigation.map((item) => (
            <NavLink key={item.name} item={item} />
          ))}
        </nav>

        {/* Team — above Admin */}
        <div className="border-t border-border/70 p-2">
          {!collapsed ? (
            <p className="px-3 pt-1 pb-2 font-mono text-[9px] font-bold uppercase tracking-[0.18em] text-muted-foreground/70">
              Team
            </p>
          ) : null}
          {teamNav.map((item) => (
            <NavLink key={item.name} item={item} />
          ))}
        </div>

        {/* Admin — collapsible, above Settings */}
        <div className="border-t border-border/70 p-2">
          {!collapsed ? (
            <p className="px-3 pt-1 pb-2 font-mono text-[9px] font-bold uppercase tracking-[0.18em] text-muted-foreground/70">
              Admin
            </p>
          ) : null}
          <NavLink item={{ name: "Admin", href: "/admin/system", icon: SlidersHorizontal }} />
        </div>

        {/* Bottom Navigation */}
        <div className="border-t border-border/70 p-2">
          {!collapsed ? (
            <p className="px-3 pt-1 pb-2 font-mono text-[9px] font-bold uppercase tracking-[0.18em] text-muted-foreground/70">
              Settings
            </p>
          ) : null}
          {bottomNav.map((item) => (
            <NavLink key={item.name} item={item} />
          ))}
        </div>
      </aside>
    </TooltipProvider>
  )
}
