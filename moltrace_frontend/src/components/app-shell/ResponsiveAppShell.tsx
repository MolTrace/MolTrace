"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { AppSidebar } from "@/components/app/app-sidebar"
import { AppTopbar } from "@/components/app/app-topbar"
import { AIEvidenceQueue } from "@/components/app/ai-evidence-queue"
import { AIEvidenceQueueSheet } from "@/src/components/app-shell/AIEvidenceQueueSheet"
import { OverviewDataProvider } from "@/components/app/overview-data-context"
import { useIsMobile } from "@/hooks/use-mobile"
import { cn } from "@/lib/utils"
import { MobileBottomNav } from "@/src/components/app-shell/MobileBottomNav"
import { invalidateShellSnapshots } from "@/src/lib/shell/shell-snapshot-cache"
import { TenantProvider } from "@/src/lib/tenant/tenant-context"
import { StepUpProvider } from "@/components/auth/step-up-provider"
import { ModuleRouteGuard } from "@/src/lib/modules/module-route-guard"

/** Remembers the reader's panel/sidebar choices across the shell remount that
 *  every navigation causes. Guarded: storage access throws outright in Safari
 *  private browsing and in some embedded webviews. */
const SHELL_PREF_PREFIX = "moltrace:shell:"

function readShellPref(key: string, fallback: boolean): boolean {
  if (typeof window === "undefined") return fallback
  try {
    const raw = window.localStorage.getItem(`${SHELL_PREF_PREFIX}${key}`)
    if (raw === "1") return true
    if (raw === "0") return false
  } catch {
    /* storage unavailable — use the default */
  }
  return fallback
}

function writeShellPref(key: string, value: boolean): void {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(`${SHELL_PREF_PREFIX}${key}`, value ? "1" : "0")
  } catch {
    /* storage unavailable — the choice just won't persist */
  }
}

export function ResponsiveAppShell({ children }: { children: React.ReactNode }) {
  const isMobile = useIsMobile()
  const router = useRouter()
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  // Docked panel: open by default on desktop, and the reader's choice is
  // restored after mount (see below) rather than read during render, which
  // would not match what the server rendered.
  const [evidenceQueueOpen, setEvidenceQueueOpen] = useState(true)
  // The mobile sheet is a separate, deliberately-closed-by-default state. It must
  // NOT ride on `evidenceQueueOpen`: that defaults to true and this shell remounts
  // on every navigation, so sharing it would slam a full-screen sheet over the
  // page on every single tap of the bottom nav.
  const [evidenceSheetOpen, setEvidenceSheetOpen] = useState(false)

  useEffect(() => {
    setSidebarCollapsed(readShellPref("sidebar-collapsed", false))
    setEvidenceQueueOpen(readShellPref("evidence-queue-open", true))
  }, [])

  function toggleSidebar() {
    setSidebarCollapsed((prev) => {
      const next = !prev
      writeShellPref("sidebar-collapsed", next)
      return next
    })
  }

  function setDockedQueueOpen(next: boolean) {
    setEvidenceQueueOpen(next)
    writeShellPref("evidence-queue-open", next)
  }

  // One button in the topbar drives two surfaces: the docked column when there is
  // room to dock it, and a sheet over the content when there is not. The docked
  // column's visibility is decided in CSS (`hidden lg:flex`), so this matching
  // media query only has to be right by the time someone clicks — not on the
  // first paint, which is what makes a JS breakpoint flash.
  const [canDock, setCanDock] = useState(false)
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return
    const mql = window.matchMedia("(min-width: 1024px)")
    const sync = () => setCanDock(mql.matches)
    sync()
    // Safari ≤13 has only the deprecated listener pair on MediaQueryList.
    if (typeof mql.addEventListener === "function") mql.addEventListener("change", sync)
    else if (typeof mql.addListener === "function") mql.addListener(sync)
    return () => {
      if (typeof mql.removeEventListener === "function") mql.removeEventListener("change", sync)
      else if (typeof mql.removeListener === "function") mql.removeListener(sync)
    }
  }, [])

  const docked = canDock && !isMobile

  function toggleEvidenceQueue() {
    if (docked) setDockedQueueOpen(!evidenceQueueOpen)
    else setEvidenceSheetOpen((prev) => !prev)
  }

  // When a refresh fails (idle/absolute expiry, invalid, or reuse-detected), the
  // client clears the token family and dispatches this event — send the user to a
  // fresh login rather than leaving them on a now-unauthenticated page.
  useEffect(() => {
    function onAuthReset(event: Event) {
      const reason = (event as CustomEvent<{ reason?: string }>).detail?.reason
      // Drop cached workspace data with the session it belonged to.
      invalidateShellSnapshots()
      router.replace(reason === "token_reuse_detected" ? "/sign-in?session_reset=reuse" : "/sign-in?session_reset=1")
    }
    window.addEventListener("moltrace:auth-reset", onAuthReset)
    return () => window.removeEventListener("moltrace:auth-reset", onAuthReset)
  }, [router])

  return (
    <TenantProvider>
      <StepUpProvider>
      <OverviewDataProvider>
        <div className="flex h-screen overflow-hidden overflow-x-hidden bg-background">
          {!isMobile ? <AppSidebar collapsed={sidebarCollapsed} onToggle={toggleSidebar} /> : null}
          <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
            <AppTopbar
              onToggleEvidenceQueue={toggleEvidenceQueue}
              evidenceQueueOpen={docked ? evidenceQueueOpen : evidenceSheetOpen}
            />
            <div className="flex min-w-0 flex-1 overflow-hidden">
              <main
                className={cn(
                  "min-w-0 flex-1 overflow-x-hidden overflow-y-auto p-4 sm:p-6",
                  isMobile ? "pb-[calc(env(safe-area-inset-bottom)+5.5rem)] sm:pb-[calc(env(safe-area-inset-bottom)+6rem)]" : "pb-6",
                )}
              >
                <ModuleRouteGuard>{children}</ModuleRouteGuard>
              </main>
              {/* A real flex column, not a fixed overlay. As an overlay it had to
                  guess where the topbar ended (`top-14`), which the offline
                  banner silently invalidates by pushing the whole shell down —
                  and it had to guess its own height from a viewport unit. As a
                  sibling it simply fills the row. `hidden lg:flex` keeps the
                  breakpoint in CSS so narrow viewports never paint it at all. */}
              {evidenceQueueOpen && !isMobile ? (
                <AIEvidenceQueue onClose={() => setDockedQueueOpen(false)} />
              ) : null}
            </div>
          </div>
          {/* Rendered at every size: below lg there is no room to dock, so the
              sheet is the only surface — including on a narrow desktop window,
              which is not "mobile" by any pointer/user-agent test. */}
          <AIEvidenceQueueSheet open={evidenceSheetOpen} onOpenChange={setEvidenceSheetOpen} />
          {isMobile ? <MobileBottomNav /> : null}
        </div>
      </OverviewDataProvider>
      </StepUpProvider>
    </TenantProvider>
  )
}
