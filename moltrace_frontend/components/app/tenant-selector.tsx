"use client"

import { Building2, CheckCircle2, MinusCircle, RefreshCw } from "lucide-react"
import { Badge } from "@/components/ui/badge"
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
    moduleAccess,
    licensingConfigured,
    setCurrentTenantId,
    refreshTenantContext,
  } = useTenant()

  // Only meaningful once this organization actually has entitlement records —
  // with none, every module reads as permitted by default rather than by grant.
  const unlicensedCount = licensingConfigured
    ? moduleAccess.filter((module) => !module.enabled).length
    : 0

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="min-w-0 gap-2">
          <Building2 className="h-4 w-4 shrink-0" />
          <span className="max-w-36 truncate">{isMobile ? "Organization" : tenantDisplayName}</span>
          {unlicensedCount > 0 ? (
            <Badge variant="outline" className={isMobile ? "hidden" : "inline-flex h-5 px-1.5 text-[10px]"}>
              {unlicensedCount} not licensed
            </Badge>
          ) : null}
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

        {/* Shown only when this organization has entitlement records. With none,
            every module resolves to permitted because nothing is configured, and
            a row of "licensed" badges would read as a grant that was never made.
            The wording says licensing, not access, because the app does not yet
            restrict anything on this basis. */}
        {licensingConfigured ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="text-xs text-muted-foreground">Module licensing</DropdownMenuLabel>
            {moduleAccess.map((module, index) => (
              <DropdownMenuItem key={module.key} disabled>
                {module.enabled ? (
                  <CheckCircle2 className="mr-2 h-4 w-4" />
                ) : (
                  <MinusCircle className="mr-2 h-4 w-4" />
                )}
                <span className="min-w-0 flex-1 truncate">
                  {index + 1}. {module.label}
                </span>
                <Badge variant={module.enabled ? "secondary" : "outline"}>
                  {module.enabled ? "licensed" : "not licensed"}
                </Badge>
              </DropdownMenuItem>
            ))}
            <p className="px-2 pb-1 pt-0.5 text-[11px] text-muted-foreground">
              Licensing record only — MolTrace does not restrict module access on this yet.
            </p>
          </>
        ) : null}

        <DropdownMenuSeparator />
        <DropdownMenuItem disabled={loading} onSelect={() => void refreshTenantContext()}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh organization access
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
