"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  CreditCard,
  FileText,
  ListOrdered,
  PlusCircle,
  ToggleRight,
} from "lucide-react"
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
import { Textarea } from "@/components/ui/textarea"
import { JsonObjectField } from "@/components/ui/json-object-field"
import { trackFeatureFlagUpdated } from "@/src/lib/analytics/analytics-client"

type Row = Record<string, unknown>

const PROGRAM_ORDER = [
  { label: "SpectraCheck", values: ["spectracheck"] },
  { label: "Regentry", values: ["regulatory_hub"] },
  { label: "Repho", values: ["reaction_optimization"] },
  { label: "Validation Center", values: ["validation_center"] },
  { label: "Connectors", values: ["connectors"] },
  { label: "ML / AI", values: ["ml_ai"] },
  { label: "Mobile", values: ["mobile"] },
  { label: "Admin / Cross-module", values: ["admin", "cross_module"] },
] as const

const PROGRAM_OPTIONS = [
  "spectracheck",
  "regulatory_hub",
  "reaction_optimization",
  "validation_center",
  "connectors",
  "ml_ai",
  "mobile",
  "admin",
  "cross_module",
] as const

const FEATURE_FLAG_STATUS_OPTIONS = ["active", "disabled", "archived"] as const
const SUBSCRIPTION_PLAN_STATUS_OPTIONS = ["active", "deprecated", "archived"] as const

function isRecord(value: unknown): value is Row {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function readStr(value: unknown): string {
  if (typeof value === "string" && value.trim()) return value.trim()
  if (typeof value === "number" && Number.isFinite(value)) return String(value)
  if (typeof value === "boolean") return String(value)
  return ""
}

function readFirst(row: Row | null | undefined, keys: string[]): string {
  if (!row) return ""
  for (const key of keys) {
    const value = readStr(row[key])
    if (value) return value
  }
  return ""
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

function formatErr(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    if (isRecord(error.data) && typeof error.data.detail === "string") return error.data.detail
    if (isRecord(error.data) && typeof error.data.message === "string") return error.data.message
    return error.message || fallback
  }
  if (error instanceof Error) return error.message
  return fallback
}

/**
 * Display-only label for a stored program value ("regulatory_hub" → "Regentry").
 * The stored value is what we send and sort on — never humanize that.
 */
function programLabel(program: string): string {
  const normalized = program.trim().toLowerCase()
  const match = PROGRAM_ORDER.find((item) => (item.values as readonly string[]).includes(normalized))
  if (match) return match.label
  const text = program.trim().replace(/_/g, " ")
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : program
}

/** Display-only label for a stored status value ("deprecated" → "Deprecated"). */
function statusLabel(status: string): string {
  const text = status.trim().replace(/_/g, " ")
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : status
}

function programSortIndex(program: string): number {
  const normalized = program.trim().toLowerCase()
  const index = PROGRAM_ORDER.findIndex((item) => (item.values as readonly string[]).includes(normalized))
  return index === -1 ? PROGRAM_ORDER.length : index
}

function formatValue(value: unknown, maxLength = 220): string {
  if (value == null || value === "") return "-"
  if (typeof value === "string") return value.trim() || "-"
  if (typeof value === "number" || typeof value === "boolean") return String(value)
  const text = JSON.stringify(value)
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text
}

function statusBadgeClass(status: string): string {
  const normalized = status.toLowerCase()
  if (normalized.includes("disabled") || normalized.includes("archived") || normalized.includes("deprecated")) {
    return "border-warning/50 text-warning"
  }
  return "text-muted-foreground"
}

export function FeatureFlagsWorkspace() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [featureFlags, setFeatureFlags] = useState<Row[]>([])
  const [subscriptionPlans, setSubscriptionPlans] = useState<Row[]>([])
  const [selectedFlagDetail, setSelectedFlagDetail] = useState<Row | null>(null)
  const [selectedFlagDetailError, setSelectedFlagDetailError] = useState("")

  const [planKey, setPlanKey] = useState("")
  const [planDisplayName, setPlanDisplayName] = useState("")
  const [planDescription, setPlanDescription] = useState("")
  const [planDefaultEntitlements, setPlanDefaultEntitlements] = useState<Record<string, unknown>>({})
  const [planFormKey, setPlanFormKey] = useState(0)
  const [planStatus, setPlanStatus] = useState<(typeof SUBSCRIPTION_PLAN_STATUS_OPTIONS)[number]>("active")
  const [planBusy, setPlanBusy] = useState(false)

  const [flagKey, setFlagKey] = useState("")
  const [flagDisplayName, setFlagDisplayName] = useState("")
  const [flagDescription, setFlagDescription] = useState("")
  const [flagProgram, setFlagProgram] = useState<(typeof PROGRAM_OPTIONS)[number]>("spectracheck")
  const [flagDefaultEnabled, setFlagDefaultEnabled] = useState("false")
  const [flagRolloutRules, setFlagRolloutRules] = useState<Record<string, unknown>>({})
  const [flagFormKey, setFlagFormKey] = useState(0)
  const [flagStatus, setFlagStatus] = useState<(typeof FEATURE_FLAG_STATUS_OPTIONS)[number]>("active")
  const [flagBusy, setFlagBusy] = useState(false)
  const [actionBusyId, setActionBusyId] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const [plansPayload, flagsPayload] = await Promise.all([
        apiFetch<unknown>("/subscription-plans", { method: "GET" }),
        apiFetch<unknown>("/feature-flags", { method: "GET" }),
      ])
      setSubscriptionPlans(asRows(plansPayload, ["subscription_plans", "plans"]))
      setFeatureFlags(asRows(flagsPayload, ["feature_flags", "flags"]))
    } catch (err) {
      setError(formatErr(err, "Could not load feature flags."))
      setSubscriptionPlans([])
      setFeatureFlags([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const sortedFeatureFlags = useMemo(
    () =>
      [...featureFlags].sort((a, b) => {
        const byProgram =
          programSortIndex(readFirst(a, ["program"])) - programSortIndex(readFirst(b, ["program"]))
        if (byProgram !== 0) return byProgram
        return readFirst(a, ["flag_key"]).localeCompare(readFirst(b, ["flag_key"]))
      }),
    [featureFlags],
  )

  async function createSubscriptionPlan() {
    setPlanBusy(true)
    setError("")
    try {
      await apiFetch("/subscription-plans", {
        method: "POST",
        body: {
          plan_key: planKey.trim(),
          display_name: planDisplayName.trim(),
          description: planDescription.trim(),
          default_entitlements_json: planDefaultEntitlements,
          status: planStatus,
        },
      })
      setPlanKey("")
      setPlanDisplayName("")
      setPlanDescription("")
      setPlanDefaultEntitlements({})
      setPlanFormKey((k) => k + 1)
      setPlanStatus("active")
      await load()
    } catch (err) {
      setError(formatErr(err, "Could not create subscription plan."))
    } finally {
      setPlanBusy(false)
    }
  }

  async function createFeatureFlag() {
    setFlagBusy(true)
    setError("")
    try {
      await apiFetch("/feature-flags", {
        method: "POST",
        body: {
          flag_key: flagKey.trim(),
          display_name: flagDisplayName.trim(),
          description: flagDescription.trim(),
          program: flagProgram,
          default_enabled: flagDefaultEnabled === "true",
          rollout_rules_json: flagRolloutRules,
          status: flagStatus,
        },
      })
      trackFeatureFlagUpdated({
        feature_key: flagKey.trim(),
        program: flagProgram,
        status: flagStatus,
      })
      setFlagKey("")
      setFlagDisplayName("")
      setFlagDescription("")
      setFlagProgram("spectracheck")
      setFlagDefaultEnabled("false")
      setFlagRolloutRules({})
      setFlagFormKey((k) => k + 1)
      setFlagStatus("active")
      await load()
    } catch (err) {
      setError(formatErr(err, "Could not create feature flag."))
    } finally {
      setFlagBusy(false)
    }
  }

  async function patchFeatureFlag(row: Row, body: Row) {
    const flagId = readFirst(row, ["id", "flag_id"])
    if (!flagId) return
    setActionBusyId(flagId)
    setError("")
    try {
      await apiFetch(`/feature-flags/${encodeURIComponent(flagId)}`, {
        method: "PATCH",
        body,
      })
      trackFeatureFlagUpdated({
        feature_key: readFirst(row, ["flag_key", "feature_key"]),
        program: readFirst(row, ["program"]),
        status: readFirst(body, ["status"]) || "updated",
      })
      await load()
    } catch (err) {
      setError(formatErr(err, "Could not update feature flag."))
    } finally {
      setActionBusyId("")
    }
  }

  async function loadFeatureFlagDetail(row: Row) {
    const flagId = readFirst(row, ["id", "flag_id"])
    if (!flagId) return
    setActionBusyId(flagId)
    setSelectedFlagDetailError("")
    try {
      const payload = await apiFetch<unknown>(`/feature-flags/${encodeURIComponent(flagId)}`, { method: "GET" })
      setSelectedFlagDetail(unwrapRecord(payload, ["feature_flag", "flag"]))
    } catch (err) {
      setSelectedFlagDetail(null)
      setSelectedFlagDetailError(formatErr(err, "Could not load feature flag detail."))
    } finally {
      setActionBusyId("")
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-slate)" }}
          >
            MolTrace · Admin · Feature Flags
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Feature Flags</h1>
          <p className="text-sm text-muted-foreground">
            Manage subscription plans and feature flags without changing MolTrace’s core product sequence.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      <AlertCard
        variant="warning"
        title="Entitlements scope"
        description="Entitlements enable or disable features; they do not change MolTrace’s core product sequence."
      />

      <ModuleCard
        accent="slate"
        eyebrow="Order"
        title="Entitlements display order"
        icon={ListOrdered}
        description="Fixed across tenant entitlement and feature flag views."
      >
        <div className="space-y-2 text-sm">
          {PROGRAM_ORDER.map((item, index) => (
            <div key={item.label} className="rounded-md border bg-muted/20 px-3 py-2">
              {index + 1}. {item.label}
            </div>
          ))}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="slate"
        eyebrow="Flags"
        title="Feature flags"
        icon={ToggleRight}
        description="Default values and tenant overrides for every registered flag."
      >
        <div className="space-y-3">
          {error ? <p className="text-xs text-destructive">{error}</p> : null}
          {loading ? <p className="text-sm text-muted-foreground">Loading feature flags...</p> : null}
          <div className="overflow-x-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Flag key</TableHead>
                  <TableHead className="text-xs">Display name</TableHead>
                  <TableHead className="text-xs">Program</TableHead>
                  <TableHead className="text-xs">Default enabled</TableHead>
                  <TableHead className="text-xs">Rollout rules</TableHead>
                  <TableHead className="text-xs">Status</TableHead>
                  <TableHead className="text-xs">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedFeatureFlags.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-xs text-muted-foreground">
                      No feature flags yet.
                    </TableCell>
                  </TableRow>
                ) : (
                  sortedFeatureFlags.map((row, index) => {
                    const flagId = readFirst(row, ["id", "flag_id"]) || `flag-${index}`
                    const defaultEnabled = readFirst(row, ["default_enabled"]).toLowerCase() === "true"
                    const status = readFirst(row, ["status"])
                    const nextStatus = status === "active" ? "disabled" : "active"
                    return (
                      <TableRow key={flagId}>
                        <TableCell className="text-xs">{readFirst(row, ["flag_key"]) || "-"}</TableCell>
                        <TableCell className="text-xs">{readFirst(row, ["display_name"]) || "-"}</TableCell>
                        <TableCell className="text-xs">
                          {readFirst(row, ["program"]) ? programLabel(readFirst(row, ["program"])) : "-"}
                        </TableCell>
                        <TableCell className="text-xs">
                          {readFirst(row, ["default_enabled"]) ? (defaultEnabled ? "Enabled" : "Disabled") : "-"}
                        </TableCell>
                        <TableCell className="max-w-[24rem] text-xs">{formatValue(row.rollout_rules_json)}</TableCell>
                        <TableCell className="text-xs">
                          {status ? (
                            <Badge variant="outline" className={`font-normal ${statusBadgeClass(status)}`}>
                              {statusLabel(status)}
                            </Badge>
                          ) : (
                            "-"
                          )}
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-wrap gap-2">
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              disabled={actionBusyId === flagId}
                              onClick={() => void patchFeatureFlag(row, { default_enabled: !defaultEnabled })}
                            >
                              Toggle default
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              disabled={actionBusyId === flagId}
                              onClick={() => void patchFeatureFlag(row, { status: nextStatus })}
                            >
                              {nextStatus === "active" ? "Enable" : "Disable"}
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              disabled={actionBusyId === flagId}
                              onClick={() => void loadFeatureFlagDetail(row)}
                            >
                              Load detail
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>
          </div>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="slate"
        eyebrow="Detail"
        title="Feature flag detail"
        icon={FileText}
        description="Definition, current value, and override history."
      >
        <div className="space-y-3">
          {selectedFlagDetailError ? <p className="text-xs text-destructive">{selectedFlagDetailError}</p> : null}
          {selectedFlagDetail ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <p className="text-xs font-medium text-muted-foreground">Flag key</p>
                <p className="mt-1 break-words text-sm">{readFirst(selectedFlagDetail, ["flag_key"]) || "-"}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground">Display name</p>
                <p className="mt-1 break-words text-sm">{readFirst(selectedFlagDetail, ["display_name"]) || "-"}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground">Program</p>
                <p className="mt-1 break-words text-sm">
                  {readFirst(selectedFlagDetail, ["program"])
                    ? programLabel(readFirst(selectedFlagDetail, ["program"]))
                    : "-"}
                </p>
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground">Default enabled</p>
                <p className="mt-1 break-words text-sm">
                  {readFirst(selectedFlagDetail, ["default_enabled"])
                    ? readFirst(selectedFlagDetail, ["default_enabled"]).toLowerCase() === "true"
                      ? "Enabled"
                      : "Disabled"
                    : "-"}
                </p>
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground">Status</p>
                <p className="mt-1 break-words text-sm">
                  {readFirst(selectedFlagDetail, ["status"])
                    ? statusLabel(readFirst(selectedFlagDetail, ["status"]))
                    : "-"}
                </p>
              </div>
              <div className="sm:col-span-2 lg:col-span-3">
                <p className="text-xs font-medium text-muted-foreground">Rollout rules</p>
                <p className="mt-1 break-words text-sm">{formatValue(selectedFlagDetail.rollout_rules_json)}</p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Choose Load detail on one of the feature flags above.</p>
          )}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="slate"
        eyebrow="Form"
        title="Create feature flag"
        icon={PlusCircle}
        description="Key, default value, and tenant scope."
      >
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="feature-flag-key">Flag key</Label>
              <Input id="feature-flag-key" value={flagKey} onChange={(event) => setFlagKey(event.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="feature-flag-display-name">Display name</Label>
              <Input
                id="feature-flag-display-name"
                value={flagDisplayName}
                onChange={(event) => setFlagDisplayName(event.target.value)}
              />
            </div>
            <div className="space-y-1 sm:col-span-2">
              <Label htmlFor="feature-flag-description">Description</Label>
              <Textarea
                id="feature-flag-description"
                value={flagDescription}
                onChange={(event) => setFlagDescription(event.target.value)}
                rows={2}
              />
              <p className="text-xs text-muted-foreground">What this flag controls. Required.</p>
            </div>
            <div className="space-y-1">
              <Label htmlFor="feature-flag-program">Program</Label>
              <Select value={flagProgram} onValueChange={(value) => setFlagProgram(value as typeof flagProgram)}>
                <SelectTrigger id="feature-flag-program">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PROGRAM_OPTIONS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {programLabel(option)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="feature-flag-default-enabled">Default enabled</Label>
              <Select value={flagDefaultEnabled} onValueChange={setFlagDefaultEnabled}>
                <SelectTrigger id="feature-flag-default-enabled">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="true">Enabled</SelectItem>
                  <SelectItem value="false">Disabled</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="feature-flag-status">Status</Label>
              <Select value={flagStatus} onValueChange={(value) => setFlagStatus(value as typeof flagStatus)}>
                <SelectTrigger id="feature-flag-status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FEATURE_FLAG_STATUS_OPTIONS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {statusLabel(option)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1 sm:col-span-2">
              <JsonObjectField
                key={`flag-rollout-${flagFormKey}`}
                idPrefix="feature-flag-rollout-rules-json"
                label="Rollout rules"
                initialValue={flagRolloutRules}
                onChange={setFlagRolloutRules}
                description="Targeting rules for this flag (name/value pairs, or raw JSON for nested tenant lists / percentages)."
              />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              disabled={flagBusy || !flagKey.trim() || !flagDisplayName.trim() || !flagDescription.trim()}
              onClick={() => void createFeatureFlag()}
            >
              {flagBusy ? "Creating..." : "Create feature flag"}
            </Button>
            <Button type="button" variant="outline" disabled={loading} onClick={() => void load()}>
              Refresh feature flags
            </Button>
          </div>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="slate"
        eyebrow="Plans"
        title="Subscription plans"
        icon={CreditCard}
        description="Tiers and the feature entitlements they grant."
      >
        <div className="space-y-3">
          <div className="overflow-x-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Plan key</TableHead>
                  <TableHead className="text-xs">Display name</TableHead>
                  <TableHead className="text-xs">Description</TableHead>
                  <TableHead className="text-xs">Default entitlements</TableHead>
                  <TableHead className="text-xs">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {subscriptionPlans.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="text-xs text-muted-foreground">
                      No subscription plans yet.
                    </TableCell>
                  </TableRow>
                ) : (
                  subscriptionPlans.map((row, index) => {
                    const planId = readFirst(row, ["id", "plan_id"]) || `plan-${index}`
                    const status = readFirst(row, ["status"])
                    return (
                      <TableRow key={planId}>
                        <TableCell className="text-xs">{readFirst(row, ["plan_key"]) || "-"}</TableCell>
                        <TableCell className="text-xs">{readFirst(row, ["display_name"]) || "-"}</TableCell>
                        <TableCell className="max-w-[18rem] text-xs">{formatValue(row.description)}</TableCell>
                        <TableCell className="max-w-[24rem] text-xs">{formatValue(row.default_entitlements_json)}</TableCell>
                        <TableCell className="text-xs">
                          {status ? (
                            <Badge variant="outline" className={`font-normal ${statusBadgeClass(status)}`}>
                              {statusLabel(status)}
                            </Badge>
                          ) : (
                            "-"
                          )}
                        </TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>
          </div>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="slate"
        eyebrow="Form"
        title="Create subscription plan"
        icon={PlusCircle}
        description="Entitlements and quotas the new tier grants."
      >
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="subscription-plan-key">Plan key</Label>
              <Input id="subscription-plan-key" value={planKey} onChange={(event) => setPlanKey(event.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="subscription-plan-display-name">Display name</Label>
              <Input
                id="subscription-plan-display-name"
                value={planDisplayName}
                onChange={(event) => setPlanDisplayName(event.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="subscription-plan-status">Status</Label>
              <Select value={planStatus} onValueChange={(value) => setPlanStatus(value as typeof planStatus)}>
                <SelectTrigger id="subscription-plan-status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SUBSCRIPTION_PLAN_STATUS_OPTIONS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {statusLabel(option)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1 sm:col-span-2">
              <Label htmlFor="subscription-plan-description">Description</Label>
              <Textarea
                id="subscription-plan-description"
                value={planDescription}
                onChange={(event) => setPlanDescription(event.target.value)}
                rows={3}
              />
            </div>
            <div className="space-y-1 sm:col-span-2">
              <JsonObjectField
                key={`plan-entitlements-${planFormKey}`}
                idPrefix="subscription-plan-default-entitlements-json"
                label="Default entitlements"
                initialValue={planDefaultEntitlements}
                onChange={setPlanDefaultEntitlements}
                description="Feature entitlements granted by this plan (feature → value)."
              />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" disabled={planBusy} onClick={() => void createSubscriptionPlan()}>
              {planBusy ? "Creating..." : "Create subscription plan"}
            </Button>
            <Button type="button" variant="outline" disabled={loading} onClick={() => void load()}>
              Refresh subscription plans
            </Button>
          </div>
        </div>
      </ModuleCard>
    </div>
  )
}
