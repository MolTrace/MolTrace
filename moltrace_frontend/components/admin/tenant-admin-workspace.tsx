"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { ApiError, apiFetch } from "@/lib/api/client"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { trackTenantCreated } from "@/src/lib/analytics/analytics-client"

type Row = Record<string, unknown>

type TenantRow = {
  id: string
  display_name: string
  tenant_key: string
  tenant_type: string
  status: string
  primary_contact: string
  updated_date: string
  pilots_active: number
  at_risk: boolean
  go_live_ready: boolean
}

const TENANT_TYPE_OPTIONS = ["internal", "pilot", "customer", "sandbox", "demo", "regulated_customer"] as const
const TENANT_STATUS_OPTIONS = ["active", "suspended", "archived", "onboarding", "trial"] as const

function isRecord(value: unknown): value is Row {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function readStr(value: unknown): string {
  if (typeof value === "string" && value.trim()) return value.trim()
  if (typeof value === "number" && Number.isFinite(value)) return String(value)
  return ""
}

function readNum(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) return Math.max(0, Math.floor(value))
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) {
    return Math.max(0, Math.floor(Number(value)))
  }
  return 0
}

function readBool(value: unknown): boolean {
  if (typeof value === "boolean") return value
  if (typeof value === "number") return value > 0
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase()
    return normalized === "true" || normalized === "yes" || normalized === "ready" || normalized === "at_risk"
  }
  return false
}

function extractRows(payload: unknown): Row[] {
  if (Array.isArray(payload)) return payload.filter(isRecord)
  if (!isRecord(payload)) return []
  const keys = ["items", "results", "tenants", "rows", "data"]
  for (const key of keys) {
    const value = payload[key]
    if (Array.isArray(value)) return value.filter(isRecord)
  }
  return []
}

function parseTenantRow(row: Row): TenantRow | null {
  const id = readStr(row.id ?? row.tenant_id)
  if (!id) return null

  const status = readStr(row.status) || "—"
  const tenantType = readStr(row.tenant_type) || "—"
  const healthStatus = readStr(row.health_status ?? row.customer_success_status).toLowerCase()
  const onboardingStatus = readStr(row.onboarding_status ?? row.go_live_status).toLowerCase()

  return {
    id,
    display_name: readStr(row.display_name) || "—",
    tenant_key: readStr(row.tenant_key) || "—",
    tenant_type: tenantType,
    status,
    primary_contact: readStr(row.primary_contact ?? row.primary_contact_email) || "—",
    updated_date: readStr(row.updated_date ?? row.updated_at) || "—",
    pilots_active:
      readNum(row.pilots_active ?? row.active_pilots ?? row.active_pilot_programs_count) ||
      (tenantType.toLowerCase() === "pilot" && status.toLowerCase() === "active" ? 1 : 0),
    at_risk: readBool(row.at_risk) || healthStatus === "at_risk" || healthStatus === "at risk",
    go_live_ready:
      readBool(row.go_live_ready) || onboardingStatus === "ready_for_go_live" || onboardingStatus === "ready for go live",
  }
}

function formatErr(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (isRecord(error.data) && typeof error.data.detail === "string") return error.data.detail
    if (isRecord(error.data) && typeof error.data.message === "string") return error.data.message
    return error.message || fallback
  }
  if (error instanceof Error) return error.message
  return fallback
}

function statusBadgeVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  const normalized = status.toLowerCase()
  if (normalized === "active") return "default"
  if (normalized === "suspended") return "destructive"
  if (normalized === "onboarding" || normalized === "trial") return "secondary"
  return "outline"
}

export function TenantAdminWorkspace() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [tenants, setTenants] = useState<TenantRow[]>([])

  const [tenantKey, setTenantKey] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [tenantType, setTenantType] = useState<(typeof TENANT_TYPE_OPTIONS)[number]>("customer")
  const [primaryContactEmail, setPrimaryContactEmail] = useState("")
  const [status, setStatus] = useState<(typeof TENANT_STATUS_OPTIONS)[number]>("onboarding")
  const [createBusy, setCreateBusy] = useState(false)

  const loadTenants = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const payload = await apiFetch<unknown>("/tenants", { method: "GET" })
      const rows = extractRows(payload).map(parseTenantRow).filter((row): row is TenantRow => row != null)
      setTenants(rows)
    } catch (e) {
      setError(formatErr(e, "Could not load tenants."))
      setTenants([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadTenants()
  }, [loadTenants])

  async function createTenant() {
    setCreateBusy(true)
    setError("")
    try {
      await apiFetch("/tenants", {
        method: "POST",
        body: {
          tenant_key: tenantKey.trim(),
          display_name: displayName.trim(),
          tenant_type: tenantType,
          primary_contact_email: primaryContactEmail.trim(),
          status,
        },
      })
      trackTenantCreated({ tenant_type: tenantType, status })
      setTenantKey("")
      setDisplayName("")
      setPrimaryContactEmail("")
      setTenantType("customer")
      setStatus("onboarding")
      await loadTenants()
    } catch (e) {
      setError(formatErr(e, "Could not create tenant."))
    } finally {
      setCreateBusy(false)
    }
  }

  const summary = useMemo(() => {
    const activeTenants = tenants.filter((tenant) => tenant.status.toLowerCase() === "active").length
    const pilotsActive = tenants.reduce((sum, tenant) => sum + tenant.pilots_active, 0)
    const tenantsOnboarding = tenants.filter((tenant) => tenant.status.toLowerCase() === "onboarding").length
    const tenantsAtRisk = tenants.filter((tenant) => tenant.at_risk).length
    const goLiveReady = tenants.filter((tenant) => tenant.go_live_ready).length
    return { activeTenants, pilotsActive, tenantsOnboarding, tenantsAtRisk, goLiveReady }
  }, [tenants])

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Tenant Admin</h1>
          <p className="text-muted-foreground">
            Manage customer tenants, environments, entitlements, pilot programs, onboarding, validation profiles, and
            procurement evidence.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      <Alert className="border-warning/40 bg-warning/10">
        <AlertDescription className="text-xs text-warning">
          Tenant summaries must never display raw scientific data, connector credentials, or secrets.
        </AlertDescription>
      </Alert>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">active tenants</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{summary.activeTenants}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">pilots active</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{summary.pilotsActive}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">tenants onboarding</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{summary.tenantsOnboarding}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">tenants at risk</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{summary.tenantsAtRisk}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">go-live ready</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{summary.goLiveReady}</CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Tenant table</CardTitle>
          <CardDescription>
            <code className="text-xs">GET /tenants</code>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {error ? <p className="text-xs text-destructive">{error}</p> : null}
          {loading ? <p className="text-sm text-muted-foreground">Loading tenants…</p> : null}
          {!loading ? (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>display name</TableHead>
                    <TableHead>tenant key</TableHead>
                    <TableHead>tenant type</TableHead>
                    <TableHead>status</TableHead>
                    <TableHead>primary contact</TableHead>
                    <TableHead>updated date</TableHead>
                    <TableHead>open</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tenants.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-xs text-muted-foreground">
                        No tenants returned.
                      </TableCell>
                    </TableRow>
                  ) : (
                    tenants.map((tenant) => (
                      <TableRow key={tenant.id}>
                        <TableCell className="text-xs">{tenant.display_name}</TableCell>
                        <TableCell className="text-xs">{tenant.tenant_key}</TableCell>
                        <TableCell className="text-xs">{tenant.tenant_type}</TableCell>
                        <TableCell className="text-xs">
                          <Badge variant={statusBadgeVariant(tenant.status)}>{tenant.status}</Badge>
                        </TableCell>
                        <TableCell className="text-xs">{tenant.primary_contact}</TableCell>
                        <TableCell className="text-xs">{tenant.updated_date}</TableCell>
                        <TableCell>
                          <Button type="button" size="sm" variant="outline" asChild>
                            <Link href={`/admin/tenants/${encodeURIComponent(tenant.id)}`}>Open</Link>
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Create tenant card</CardTitle>
          <CardDescription>
            <code className="text-xs">POST /tenants</code>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="tenant-admin-tenant-key">tenant key</Label>
              <Input id="tenant-admin-tenant-key" value={tenantKey} onChange={(e) => setTenantKey(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="tenant-admin-display-name">display name</Label>
              <Input
                id="tenant-admin-display-name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="tenant-admin-tenant-type">tenant type</Label>
              <Select value={tenantType} onValueChange={(value) => setTenantType(value as typeof tenantType)}>
                <SelectTrigger id="tenant-admin-tenant-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TENANT_TYPE_OPTIONS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="tenant-admin-status">status</Label>
              <Select value={status} onValueChange={(value) => setStatus(value as typeof status)}>
                <SelectTrigger id="tenant-admin-status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TENANT_STATUS_OPTIONS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1 sm:col-span-2">
              <Label htmlFor="tenant-admin-primary-contact-email">primary contact email</Label>
              <Input
                id="tenant-admin-primary-contact-email"
                type="email"
                value={primaryContactEmail}
                onChange={(e) => setPrimaryContactEmail(e.target.value)}
              />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" disabled={createBusy} onClick={() => void createTenant()}>
              {createBusy ? "Creating…" : "Create tenant"}
            </Button>
            <Button type="button" variant="outline" disabled={loading} onClick={() => void loadTenants()}>
              Refresh tenants
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
