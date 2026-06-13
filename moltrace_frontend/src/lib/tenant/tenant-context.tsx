"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import {
  AUTH_USER_STORAGE_KEY,
  TENANT_ID_STORAGE_KEY,
  apiFetch,
  readStoredTenantId,
} from "@/lib/api/client"

type Row = Record<string, unknown>

export type TenantRecord = {
  id: string
  tenant_key: string
  display_name: string
  tenant_type: string
  status: string
}

export type TenantEntitlementRecord = {
  id: string
  feature_key: string
  program: string
  enabled: boolean
  limit_json: unknown
  status?: string
}

export type TenantFeatureFlagRecord = {
  id: string
  flag_key: string
  display_name: string
  program: string
  default_enabled: boolean
  status: string
}

export type TenantModuleAccess = {
  key: "spectracheck" | "regulatory_hub" | "reaction_optimization"
  label: "SpectraCheck" | "Regentry" | "Reaction Optimization"
  enabled: boolean
}

type TenantContextValue = {
  currentTenantId: string
  tenantDisplayName: string
  tenantStatus: string
  tenant: TenantRecord
  tenants: TenantRecord[]
  entitlements: TenantEntitlementRecord[]
  featureFlags: TenantFeatureFlagRecord[]
  moduleAccess: TenantModuleAccess[]
  isAdmin: boolean
  loading: boolean
  error: string
  setCurrentTenantId: (tenantId: string) => void
  refreshTenantContext: () => Promise<void>
  isProgramEnabled: (program: TenantModuleAccess["key"] | string) => boolean
  isFeatureEnabled: (featureKey: string) => boolean
}

const LOCAL_TENANT_ID = "local-development"
const FALLBACK_TENANT_DISPLAY_NAME =
  process.env.NODE_ENV === "production" ? "MolTrace workspace" : "Local development tenant"
const FALLBACK_TENANT_STATUS = process.env.NODE_ENV === "production" ? "workspace" : "local"

const LOCAL_TENANT: TenantRecord = {
  id: LOCAL_TENANT_ID,
  tenant_key: "local_development",
  display_name: FALLBACK_TENANT_DISPLAY_NAME,
  tenant_type: "sandbox",
  status: FALLBACK_TENANT_STATUS,
}

const CORE_MODULES: Omit<TenantModuleAccess, "enabled">[] = [
  { key: "spectracheck", label: "SpectraCheck" },
  { key: "regulatory_hub", label: "Regentry" },
  { key: "reaction_optimization", label: "Reaction Optimization" },
]

const LOCAL_MODULE_ACCESS: TenantModuleAccess[] = CORE_MODULES.map((module) => ({
  ...module,
  enabled: true,
}))

const LOCAL_TENANT_CONTEXT: TenantContextValue = {
  currentTenantId: LOCAL_TENANT.id,
  tenantDisplayName: LOCAL_TENANT.display_name,
  tenantStatus: LOCAL_TENANT.status,
  tenant: LOCAL_TENANT,
  tenants: [LOCAL_TENANT],
  entitlements: [],
  featureFlags: [],
  moduleAccess: LOCAL_MODULE_ACCESS,
  isAdmin: false,
  loading: false,
  error: "",
  setCurrentTenantId: () => {},
  refreshTenantContext: async () => {},
  isProgramEnabled: () => true,
  isFeatureEnabled: () => true,
}

const TenantContext = createContext<TenantContextValue | null>(null)

function isRecord(value: unknown): value is Row {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function readStr(value: unknown): string {
  if (typeof value === "string" && value.trim()) return value.trim()
  if (typeof value === "number" && Number.isFinite(value)) return String(value)
  if (typeof value === "boolean") return String(value)
  return ""
}

function readBool(value: unknown): boolean {
  if (typeof value === "boolean") return value
  if (typeof value === "number") return value > 0
  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase()
    return normalized === "true" || normalized === "enabled" || normalized === "active" || normalized === "yes"
  }
  return false
}

function asRows(payload: unknown, keys: string[] = []): Row[] {
  if (Array.isArray(payload)) return payload.filter(isRecord)
  if (!isRecord(payload)) return []
  for (const key of [...keys, "items", "results", "rows", "data"]) {
    const value = payload[key]
    if (Array.isArray(value)) return value.filter(isRecord)
  }
  return []
}

function unwrapRecord(payload: unknown, keys: string[] = []): Row | null {
  if (!isRecord(payload)) return null
  for (const key of [...keys, "item", "record", "data"]) {
    const value = payload[key]
    if (isRecord(value)) return value
  }
  return payload
}

function parseTenant(row: Row): TenantRecord | null {
  const id = readStr(row.id ?? row.tenant_id)
  if (!id) return null
  return {
    id,
    tenant_key: readStr(row.tenant_key) || "tenant",
    display_name: readStr(row.display_name) || readStr(row.name) || "Tenant",
    tenant_type: readStr(row.tenant_type) || "customer",
    status: readStr(row.status) || "unknown",
  }
}

function parseEntitlement(row: Row): TenantEntitlementRecord | null {
  const id = readStr(row.id ?? row.entitlement_id)
  const featureKey = readStr(row.feature_key)
  const program = readStr(row.program)
  if (!id || !featureKey || !program) return null
  return {
    id,
    feature_key: featureKey,
    program,
    enabled: readBool(row.enabled),
    limit_json: row.limit_json ?? {},
    status: readStr(row.status),
  }
}

function formatErr(error: unknown): string {
  if (error instanceof Error) return error.message
  return "Tenant context is unavailable."
}

function readStoredUserIsAdmin(): boolean {
  if (typeof window === "undefined") return false
  try {
    const raw = window.localStorage.getItem(AUTH_USER_STORAGE_KEY)
    if (!raw) return false
    const user = JSON.parse(raw) as Row
    const role = readStr(user.role ?? user.member_role).toLowerCase()
    return user.is_admin === true || role === "admin" || role === "owner"
  } catch {
    return false
  }
}

function storeTenantId(tenantId: string) {
  if (typeof window === "undefined") return
  try {
    if (!tenantId || tenantId === LOCAL_TENANT_ID) {
      window.localStorage.removeItem(TENANT_ID_STORAGE_KEY)
    } else {
      window.localStorage.setItem(TENANT_ID_STORAGE_KEY, tenantId)
    }
  } catch {
    // Tenant selection is a convenience, not a data store.
  }
}

function programEnabled(entitlements: TenantEntitlementRecord[], program: string): boolean {
  const matches = entitlements.filter((entitlement) => entitlement.program === program)
  if (matches.length === 0) return true
  return matches.some((entitlement) => entitlement.enabled)
}

function featureEnabled(entitlements: TenantEntitlementRecord[], featureKey: string): boolean {
  const matches = entitlements.filter((entitlement) => entitlement.feature_key === featureKey)
  if (matches.length === 0) return true
  return matches.some((entitlement) => entitlement.enabled)
}

export function TenantProvider({ children }: { children: ReactNode }) {
  const [tenants, setTenants] = useState<TenantRecord[]>([LOCAL_TENANT])
  const [tenant, setTenant] = useState<TenantRecord>(LOCAL_TENANT)
  const [entitlements, setEntitlements] = useState<TenantEntitlementRecord[]>([])
  const [featureFlags] = useState<TenantFeatureFlagRecord[]>([])
  const [isAdmin, setIsAdmin] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  const loadTenantDetail = useCallback(async (tenantId: string, tenantList: TenantRecord[]) => {
    if (!tenantId || tenantId === LOCAL_TENANT_ID) {
      setTenant(LOCAL_TENANT)
      setEntitlements([])
      storeTenantId(LOCAL_TENANT_ID)
      return
    }

    storeTenantId(tenantId)
    const headers = { "x-tenant-id": tenantId }
    const [tenantPayload, entitlementPayload] = await Promise.all([
      apiFetch<unknown>(`/tenants/${encodeURIComponent(tenantId)}`, { method: "GET", headers }),
      apiFetch<unknown>(`/tenants/${encodeURIComponent(tenantId)}/entitlements`, { method: "GET", headers }),
    ])
    const parsedTenant =
      parseTenant(unwrapRecord(tenantPayload, ["tenant"]) ?? {}) ??
      tenantList.find((candidate) => candidate.id === tenantId) ??
      LOCAL_TENANT
    const parsedEntitlements = asRows(entitlementPayload, ["entitlements", "tenant_entitlements"])
      .map(parseEntitlement)
      .filter((item): item is TenantEntitlementRecord => item != null)
    setTenant(parsedTenant)
    setEntitlements(parsedEntitlements)
  }, [])

  const refreshTenantContext = useCallback(async () => {
    setLoading(true)
    setError("")
    setIsAdmin(readStoredUserIsAdmin())

    try {
      const payload = await apiFetch<unknown>("/tenants", { method: "GET" })
      const parsedTenants = asRows(payload, ["tenants"])
        .map(parseTenant)
        .filter((item): item is TenantRecord => item != null)
      const nextTenants = parsedTenants.length > 0 ? parsedTenants : [LOCAL_TENANT]
      const storedTenantId = readStoredTenantId()
      const nextTenantId =
        storedTenantId && nextTenants.some((candidate) => candidate.id === storedTenantId)
          ? storedTenantId
          : nextTenants[0]?.id ?? LOCAL_TENANT_ID
      setTenants(nextTenants)
      await loadTenantDetail(nextTenantId, nextTenants)
    } catch (err) {
      setTenants([LOCAL_TENANT])
      setTenant(LOCAL_TENANT)
      setEntitlements([])
      storeTenantId(LOCAL_TENANT_ID)
      setError(formatErr(err))
    } finally {
      setLoading(false)
    }
  }, [loadTenantDetail])

  useEffect(() => {
    void refreshTenantContext()
  }, [refreshTenantContext])

  const setCurrentTenantId = useCallback(
    (tenantId: string) => {
      const nextTenants = tenants.length > 0 ? tenants : [LOCAL_TENANT]
      setLoading(true)
      setError("")
      void loadTenantDetail(tenantId, nextTenants)
        .catch((err) => {
          setError(formatErr(err))
        })
        .finally(() => setLoading(false))
    },
    [loadTenantDetail, tenants],
  )

  const moduleAccess = useMemo<TenantModuleAccess[]>(
    () =>
      CORE_MODULES.map((module) => ({
        ...module,
        enabled: programEnabled(entitlements, module.key),
      })),
    [entitlements],
  )

  const value = useMemo<TenantContextValue>(
    () => ({
      currentTenantId: tenant.id,
      tenantDisplayName: tenant.display_name,
      tenantStatus: tenant.status,
      tenant,
      tenants,
      entitlements,
      featureFlags,
      moduleAccess,
      isAdmin,
      loading,
      error,
      setCurrentTenantId,
      refreshTenantContext,
      isProgramEnabled: (program) => programEnabled(entitlements, program),
      isFeatureEnabled: (featureKey) => featureEnabled(entitlements, featureKey),
    }),
    [
      tenant,
      tenants,
      entitlements,
      featureFlags,
      moduleAccess,
      isAdmin,
      loading,
      error,
      setCurrentTenantId,
      refreshTenantContext,
    ],
  )

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>
}

export function useTenant() {
  const value = useContext(TenantContext)
  return value ?? LOCAL_TENANT_CONTEXT
}
