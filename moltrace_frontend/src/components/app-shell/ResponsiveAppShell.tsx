"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { AppSidebar } from "@/components/app/app-sidebar"
import { AppTopbar } from "@/components/app/app-topbar"
import { AIEvidenceQueue } from "@/components/app/ai-evidence-queue"
import { OverviewDataProvider } from "@/components/app/overview-data-context"
import { useIsMobile } from "@/hooks/use-mobile"
import { cn } from "@/lib/utils"
import { MobileBottomNav } from "@/src/components/app-shell/MobileBottomNav"
import { TenantProvider } from "@/src/lib/tenant/tenant-context"
import { StepUpProvider } from "@/components/auth/step-up-provider"

export function ResponsiveAppShell({ children }: { children: React.ReactNode }) {
  const isMobile = useIsMobile()
  const router = useRouter()
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [evidenceQueueOpen, setEvidenceQueueOpen] = useState(true)

  // When a refresh fails (idle/absolute expiry, invalid, or reuse-detected), the
  // client clears the token family and dispatches this event — send the user to a
  // fresh login rather than leaving them on a now-unauthenticated page.
  useEffect(() => {
    function onAuthReset(event: Event) {
      const reason = (event as CustomEvent<{ reason?: string }>).detail?.reason
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
          {!isMobile ? (
            <AppSidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} />
          ) : null}
          <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
            <AppTopbar onToggleEvidenceQueue={() => setEvidenceQueueOpen(!evidenceQueueOpen)} />
            <div className="flex min-w-0 flex-1 overflow-hidden">
              <main
                className={cn(
                  "min-w-0 flex-1 overflow-x-hidden overflow-y-auto p-4 sm:p-6",
                  isMobile ? "pb-[calc(env(safe-area-inset-bottom)+5.5rem)] sm:pb-[calc(env(safe-area-inset-bottom)+6rem)]" : "pb-6",
                  evidenceQueueOpen && !isMobile && "mr-80",
                )}
              >
                {children}
              </main>
              {evidenceQueueOpen && !isMobile ? <AIEvidenceQueue onClose={() => setEvidenceQueueOpen(false)} /> : null}
            </div>
          </div>
          {isMobile ? <MobileBottomNav /> : null}
        </div>
      </OverviewDataProvider>
      </StepUpProvider>
    </TenantProvider>
  )
}
