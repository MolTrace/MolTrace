"use client"

import { Building2, CheckCircle2, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useIsMobile } from "@/hooks/use-mobile"
import { useTenant } from "@/src/lib/tenant/tenant-context"

export function TenantSelector() {
  const isMobile = useIsMobile()
  const {
    currentTenantId,
    tenantDisplayName,
    tenantStatus,
    tenants,
    isAdmin,
    loading,
    error,
    setCurrentTenantId,
    refreshTenantContext,
  } = useTenant()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="min-w-0 gap-2">
          <Building2 className="h-4 w-4 shrink-0" />
          <span className="max-w-36 truncate">{isMobile ? "Organization" : tenantDisplayName}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuLabel>
          <div className="flex flex-col gap-1">
            <span className="truncate">{tenantDisplayName}</span>
            <span className="text-xs font-normal text-muted-foreground">
              {tenantStatus}
              {error ? " · Organization details unavailable" : ""}
            </span>
          </div>
        </DropdownMenuLabel>

        {isAdmin ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="text-xs text-muted-foreground">Switch organization</DropdownMenuLabel>
            {tenants.map((tenant) => (
              <DropdownMenuItem
                key={tenant.id}
                disabled={loading || tenant.id === currentTenantId}
                onSelect={() => setCurrentTenantId(tenant.id)}
              >
                <Building2 className="mr-2 h-4 w-4" />
                <span className="min-w-0 flex-1 truncate">{tenant.display_name}</span>
                {tenant.id === currentTenantId ? <CheckCircle2 className="h-4 w-4" /> : null}
              </DropdownMenuItem>
            ))}
          </>
        ) : null}

        {/* The per-module licensing readout that used to sit here is gone. It rendered
            tenant entitlement rows, which enforce nothing — so it needed a footnote
            saying as much, and a badge row carrying a disclaimer is worse than no badge
            row. What a workspace actually includes is deployment-scoped and answered by
            `useIncludedModules` (GET /system/capabilities); that is the readout the nav
            and route guards already obey. Do not reinstate this one on entitlements. */}

        <DropdownMenuSeparator />
        <DropdownMenuItem disabled={loading} onSelect={() => void refreshTenantContext()}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh organization access
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
