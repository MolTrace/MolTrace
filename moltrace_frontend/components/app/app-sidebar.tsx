"use client"

import { useMemo } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
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
  BarChart3,
  Settings,
  ChevronLeft,
  ChevronRight,
  SlidersHorizontal,
  Users,
  ClipboardList,
  ClipboardCheck,
  Boxes,
  Server,
  Shield,
  ShieldCheck,
  ScrollText,
  Bug,
  Rocket,
  Activity,
  FlaskConical,
  FileCheck2,
  FileText,
  FileSpreadsheet,
  Signature,
  Package,
  Library,
  Cpu,
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
  /** Optional one-line descriptor, shown under the name (modules only). */
  sub?: string
}

type SidebarGroup = { label: string; items: SidebarNavItem[] }

// Grouped, module-forward navigation. The three flagship modules lead; the rest
// is grouped by job so every surface has a discoverable home.
const navGroups: SidebarGroup[] = [
  {
    label: "Modules",
    items: [
      { name: "SpectraCheck", href: "/spectracheck", icon: SpectraCheckLogoIcon, sub: "NMR · MS · structure" },
      { name: "Repho", href: "/reactions", icon: FlaskConical, sub: "Reaction optimization" },
      { name: "Regentry", href: "/regulatory", icon: ShieldCheck, sub: "Dossiers & submissions" },
    ],
  },
  {
    label: "Workspace",
    items: [
      { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
      { name: "Projects", href: "/projects", icon: FolderOpen },
      { name: "Compounds & Batches", href: "/compounds", icon: Boxes },
      { name: "Action Queue", href: "/actions", icon: ClipboardList },
      { name: "Review", href: "/review", icon: ClipboardCheck },
    ],
  },
  {
    // Group name is the hub; "Overview" is the hub landing, the rest are its sections.
    label: "Validation Center",
    items: [
      { name: "Overview", href: "/validation-center", icon: FileCheck2 },
      { name: "Controlled Records", href: "/validation-center/controlled-records", icon: FileText },
      { name: "e-Signatures", href: "/validation-center/esignatures", icon: Signature },
      { name: "System Releases", href: "/validation-center/releases", icon: Package },
    ],
  },
  {
    label: "AI / ML",
    items: [
      { name: "AI / ML Governance", href: "/ai", icon: Bot },
      { name: "Model Factory", href: "/ml", icon: Cpu },
    ],
  },
  {
    label: "Knowledge & Analytics",
    items: [
      { name: "Knowledge Library", href: "/knowledge", icon: Library },
      { name: "Reports", href: "/reports", icon: FileSpreadsheet },
      { name: "Automation ROI", href: "/roi", icon: BarChart3 },
    ],
  },
]

const teamNav: SidebarNavItem[] = [{ name: "Team", href: "/settings/team", icon: Users }]
const bottomNav: SidebarNavItem[] = [{ name: "Settings", href: "/dashboard/settings", icon: Settings }]
const adminItem: SidebarNavItem = { name: "Admin", href: "/admin/system", icon: SlidersHorizontal }

const adminNavigation: SidebarNavItem[] = [
  { name: "System", href: "/admin/system", icon: Server },
  { name: "Security", href: "/admin/security", icon: Shield },
  { name: "Audit", href: "/admin/audit", icon: ScrollText },
  { name: "Debug", href: "/admin/debug", icon: Bug },
  { name: "Ops", href: "/admin/ops", icon: Activity },
  { name: "Deployment", href: "/settings/deployment", icon: Rocket },
]

// Back-compat exports (flattened primary nav).
export const appNavigation: SidebarNavItem[] = navGroups.flatMap((g) => g.items)
export const appAdminNavigation = adminNavigation
export const appTeamNavigation = teamNav
export const appBottomNavigation = bottomNav

interface AppSidebarProps {
  collapsed: boolean
  onToggle: () => void
}

/** Boundary-safe prefix match: pathname is exactly href or a child segment of it. */
function isUnder(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(href + "/")
}

/** The single most-specific nav href the current path falls under, so nested
 *  routes (e.g. /validation-center/esignatures) light up exactly one item. */
function mostSpecificActiveHref(pathname: string, hrefs: string[]): string | null {
  return hrefs.filter((h) => isUnder(pathname, h)).sort((a, b) => b.length - a.length)[0] ?? null
}

export function AppSidebar({ collapsed, onToggle }: AppSidebarProps) {
  const pathname = usePathname()

  const primaryHrefs = useMemo(
    () => [...navGroups.flatMap((g) => g.items), ...teamNav, ...bottomNav].map((i) => i.href),
    [],
  )
  const activeHref = useMemo(
    () => mostSpecificActiveHref(pathname, primaryHrefs),
    [pathname, primaryHrefs],
  )
  const adminActive = isUnder(pathname, "/admin")

  const NavLink = ({ item, active }: { item: SidebarNavItem; active: boolean }) => {
    const linkContent = (
      <Link
        href={item.href}
        aria-current={active ? "page" : undefined}
        aria-label={collapsed ? item.name : undefined}
        className={cn(
          "group/navlink relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold tracking-tight transition-all duration-200",
          active
            ? "bg-secondary text-foreground shadow-sm"
            : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground hover:shadow-sm",
          collapsed && "justify-center px-2",
        )}
        style={active ? { boxShadow: `inset ${collapsed ? 2 : 3}px 0 0 0 var(--mt-teal)` } : undefined}
      >
        <item.icon
          className="h-4 w-4 shrink-0"
          style={active ? { color: "var(--mt-teal)" } : undefined}
          aria-hidden
        />
        {!collapsed && (
          <span className="min-w-0 flex-1">
            <span className="block truncate">{item.name}</span>
            {item.sub ? (
              <span className="block truncate text-[11px] font-normal text-muted-foreground">{item.sub}</span>
            ) : null}
          </span>
        )}
      </Link>
    )

    if (collapsed) {
      return (
        <Tooltip>
          <TooltipTrigger asChild>{linkContent}</TooltipTrigger>
          <TooltipContent side="right">{item.sub ? `${item.name} — ${item.sub}` : item.name}</TooltipContent>
        </Tooltip>
      )
    }
    return linkContent
  }

  const SectionLabel = ({ label }: { label: string }) =>
    collapsed ? null : (
      <p className="px-3 pt-1 pb-2 font-mono text-[9px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </p>
    )

  return (
    <TooltipProvider delayDuration={0}>
      <aside
        className={cn(
          // Solid bg-sidebar (no alpha) + no backdrop-blur — a blurred sidebar
          // promotes itself to a persistent GPU layer and can cull/repaint the
          // main scroll column. Solid stays in flow and never triggers promotion.
          "flex h-full flex-col border-r border-border/70 bg-sidebar transition-[width] duration-200",
          collapsed ? "w-14" : "w-56",
        )}
      >
        {/* Logo / home */}
        <div className={cn("flex h-14 items-center border-b border-border/70 px-3", collapsed ? "justify-center" : "justify-between")}>
          <Link href="/" className="flex items-center gap-2" aria-label="MolTrace home">
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
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={cn("h-7 w-7", collapsed && "absolute -right-3.5 top-3.5 z-10 rounded-full border border-border/70 bg-background/95 shadow-sm backdrop-blur-sm")}
          >
            {collapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
          </Button>
        </div>

        {/* Primary navigation — grouped by job */}
        <nav className="flex-1 space-y-3 overflow-y-auto p-2" aria-label="Primary">
          {navGroups.map((group) => (
            <div key={group.label} role="group" aria-label={group.label} className="space-y-1">
              <SectionLabel label={group.label} />
              {group.items.map((item) => (
                <NavLink key={item.href} item={item} active={item.href === activeHref} />
              ))}
            </div>
          ))}
        </nav>

        {/* Team */}
        <div role="group" aria-label="Team" className="border-t border-border/70 p-2">
          <SectionLabel label="Team" />
          {teamNav.map((item) => (
            <NavLink key={item.href} item={item} active={item.href === activeHref} />
          ))}
        </div>

        {/* Admin */}
        <div role="group" aria-label="Admin" className="border-t border-border/70 p-2">
          <SectionLabel label="Admin" />
          <NavLink item={adminItem} active={adminActive} />
        </div>

        {/* Settings */}
        <div role="group" aria-label="Settings" className="border-t border-border/70 p-2">
          <SectionLabel label="Settings" />
          {bottomNav.map((item) => (
            <NavLink key={item.href} item={item} active={item.href === activeHref} />
          ))}
        </div>
      </aside>
    </TooltipProvider>
  )
}
