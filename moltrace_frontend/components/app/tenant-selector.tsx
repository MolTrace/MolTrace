"use client"

import { Building2, CheckCircle2, Lock, RefreshCw } from "lucide-react"
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
import { useTenant } from "@/src/lib/tenant/tenant-context"

export function TenantSelector() {
  const {
    currentTenantId,
    tenantDisplayName,
    tenantStatus,
    tenants,
    isAdmin,
    loading,
    error,
    moduleAccess,
    setCurrentTenantId,
    refreshTenantContext,
  } = useTenant()

  const lockedCount = moduleAccess.filter((module) => !module.enabled).length

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="min-w-0 gap-2">
          <Building2 className="h-4 w-4 shrink-0" />
          <span className="hidden max-w-36 truncate lg:inline">{tenantDisplayName}</span>
          <span className="max-w-24 truncate lg:hidden">Tenant</span>
          {lockedCount > 0 ? (
            <Badge variant="outline" className="hidden h-5 px-1.5 text-[10px] sm:inline-flex">
              {lockedCount} locked
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
              {error ? " · Tenant service unavailable" : ""}
            </span>
          </div>
        </DropdownMenuLabel>

        {isAdmin ? (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="text-xs text-muted-foreground">Switch tenant</DropdownMenuLabel>
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

        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-xs text-muted-foreground">Module access</DropdownMenuLabel>
        {moduleAccess.map((module, index) => (
          <DropdownMenuItem key={module.key} disabled>
            {module.enabled ? <CheckCircle2 className="mr-2 h-4 w-4" /> : <Lock className="mr-2 h-4 w-4" />}
            <span className="min-w-0 flex-1 truncate">
              {index + 1}. {module.label}
            </span>
            <Badge variant={module.enabled ? "secondary" : "outline"}>{module.enabled ? "enabled" : "locked"}</Badge>
          </DropdownMenuItem>
        ))}

        <DropdownMenuSeparator />
        <DropdownMenuItem disabled={loading} onSelect={() => void refreshTenantContext()}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Refresh tenant context
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
