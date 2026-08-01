"use client"

import { useMemo } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
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
import { useIncludedModules } from "@/src/lib/modules/included-modules-provider"

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
      { name: "Regentry", href: "/regulatory", icon: ShieldCheck, sub: "Dossiers & submissions" },
      { name: "Repho", href: "/reactions", icon: FlaskConical, sub: "Reaction optimization" },
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
  const { isRouteOffered } = useIncludedModules()
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
          //
          // `relative` is load-bearing: the edge handle below is absolutely
          // positioned against this element. Without it the handle resolved
          // against <body> and landed at the far edge of the *viewport* — which
          // is how the collapsed rail ended up with no way to reopen it.
          "relative flex h-full flex-col border-r border-border/70 bg-sidebar transition-[width] duration-200",
          collapsed ? "w-14" : "w-56",
        )}
      >
        {/* Logo / home */}
        <div className={cn("flex h-14 items-center border-b border-border/70 px-3", collapsed ? "justify-center" : "justify-start")}>
          <Link href="/" className="flex items-center gap-2" aria-label="MolTrace home">
            <MoleculeLogoMark className="h-7 w-7" />
            {!collapsed && (
              <span className="text-[15px] font-semibold tracking-tight">
                <span className="font-bold text-foreground">Mol</span>
                <span className={moltraceTraceClassName}>Trace</span>
              </span>
            )}
          </Link>
        </div>

        {/* Edge handle — the one control that shows or hides the item names.
            It rides the sidebar's own border, level with the header band, so it
            sits where the eye already goes on arrival and stays in the same
            place and the same shape whichever state you are in. Its predecessor
            only appeared once the rail was already collapsed, which is precisely
            when it was hardest to find. */}
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={onToggle}
              aria-label={collapsed ? "Show item names" : "Hide item names"}
              aria-expanded={!collapsed}
              // h-14 matches the header band exactly, so the chip lands on its
              // vertical centre — level with the wordmark, on the border.
              className="group/edge absolute -right-2.5 top-0 z-20 flex h-14 w-5 cursor-pointer items-center justify-center focus-visible:outline-none"
            >
              {/* Always a visible chip, never a hidden hover target. An earlier
                  pass had this rest as a faint hairline on the border and only
                  become a chip on hover — which reproduces the very problem it
                  exists to solve, since a control you cannot see is one you
                  cannot find. Hover and focus deepen it; they do not reveal it.
                  `motion-reduce` drops the tween but keeps every state change,
                  as globals.css carries no global reduced-motion rule. */}
              {/* Carries the brand accent rather than border grey. A neutral chip
                  reads as part of the divider it sits on — in dark mode especially,
                  where a muted ring on a near-black sidebar all but disappears.
                  Teal is the app's "you can act on this" colour, and on an icon
                  the vivid token is the correct one (the ink variants exist for
                  TEXT, which fails AA at these sizes). */}
              <span
                className={cn(
                  "flex h-7 w-7 items-center justify-center rounded-full border-2 bg-background shadow-md",
                  "transition-all duration-200 motion-reduce:transition-none",
                  "group-hover/edge:h-8 group-hover/edge:w-8 group-hover/edge:shadow-lg",
                  "group-focus-visible/edge:h-8 group-focus-visible/edge:w-8",
                  "group-focus-visible/edge:ring-2 group-focus-visible/edge:ring-ring group-focus-visible/edge:ring-offset-2",
                )}
                style={{ borderColor: "var(--mt-teal)" }}
              >
                {collapsed ? (
                  <ChevronRight className="h-4 w-4 shrink-0" style={{ color: "var(--mt-teal)" }} aria-hidden />
                ) : (
                  <ChevronLeft className="h-4 w-4 shrink-0" style={{ color: "var(--mt-teal)" }} aria-hidden />
                )}
              </span>
            </button>
          </TooltipTrigger>
          <TooltipContent side="right">{collapsed ? "Show item names" : "Hide item names"}</TooltipContent>
        </Tooltip>

        {/* Primary navigation — grouped by job */}
        <nav className="flex-1 space-y-3 overflow-y-auto p-2" aria-label="Primary">
          {/* Only offer what the server will serve. Routes belonging to a product this
              deployment does not include are refused with a 403, so showing them is a dead
              end; a group that empties out disappears entirely rather than leaving a header
              over nothing. Fails OPEN when the capability readout is unavailable. */}
          {navGroups
            .map((group) => ({ group, items: group.items.filter((i) => isRouteOffered(i.href)) }))
            .filter(({ items }) => items.length > 0)
            .map(({ group, items }) => (
              <div key={group.label} role="group" aria-label={group.label} className="space-y-1">
                <SectionLabel label={group.label} />
                {items.map((item) => (
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
