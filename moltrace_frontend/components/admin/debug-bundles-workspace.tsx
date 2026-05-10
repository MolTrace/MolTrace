"use client"

import { useCallback, useState } from "react"
import { ApiError, apiFetch, readStoredAuthToken, buildApiPath } from "@/lib/api/client"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { ServerOff, Download, FileText, FolderDown, Plus } from "lucide-react"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

const DEBUG_BUNDLE_TOOLTIP =
  "Debug bundles collect safe diagnostic metadata such as versions, statuses, job events, artifact IDs, file hashes, warnings, and audit events."

const SCOPE_OPTIONS = ["system", "project", "sample", "session", "job", "report"] as const

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function readStr(o: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "string" && v.trim()) return v.trim()
    if (typeof v === "number" && Number.isFinite(v)) return String(v)
  }
  return ""
}

function formatErr(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const d = err.data
    if (isRecord(d) && typeof d.detail === "string") return d.detail
    return err.message || fallback
  }
  if (err instanceof Error) return err.message
  return fallback
}

function readStringList(o: Record<string, unknown>, key: string): string[] {
  const v = o[key]
  if (!Array.isArray(v)) return []
  return v.filter((x): x is string => typeof x === "string")
}

export function DebugBundlesWorkspace() {
  const [title, setTitle] = useState("")
  const [scope, setScope] = useState<string>("system")
  const [resourceId, setResourceId] = useState("")
  const [includeRecentAudit, setIncludeRecentAudit] = useState(true)
  const [includeFileHashes, setIncludeFileHashes] = useState(true)

  const [loadingCreate, setLoadingCreate] = useState(false)
  const [loadingGet, setLoadingGet] = useState(false)
  const [err, setErr] = useState("")
  const [bundle, setBundle] = useState<Record<string, unknown> | null>(null)
  const [loadId, setLoadId] = useState("")

  const [downloading, setDownloading] = useState(false)

  const createBundle = useCallback(async () => {
    setLoadingCreate(true)
    setErr("")
    try {
      const payload: Record<string, unknown> = {
        title: title.trim() || null,
        scope,
        resource_id: resourceId.trim() || null,
        include_recent_audit_events: includeRecentAudit,
        include_file_hashes: includeFileHashes,
        metadata_json: {},
      }
      const data = await apiFetch<Record<string, unknown>>("/admin/debug-bundles", {
        method: "POST",
        body: payload,
      })
      setBundle(data)
    } catch (e) {
      setErr(formatErr(e, "Create debug bundle failed."))
    } finally {
      setLoadingCreate(false)
    }
  }, [includeFileHashes, includeRecentAudit, resourceId, scope, title])

  const getBundle = useCallback(async (idStr: string) => {
    const id = Math.floor(Number(idStr.trim()))
    if (!Number.isFinite(id) || id < 1) {
      setErr("Enter a valid bundle id.")
      return
    }
    setLoadingGet(true)
    setErr("")
    try {
      const data = await apiFetch<Record<string, unknown>>(`/admin/debug-bundles/${id}`, { method: "GET" })
      setBundle(data)
    } catch (e) {
      setErr(formatErr(e, "Could not load debug bundle."))
    } finally {
      setLoadingGet(false)
    }
  }, [])

  const downloadBundle = useCallback(async (id: number) => {
    setDownloading(true)
    setErr("")
    try {
      const token = readStoredAuthToken()
      const url = buildApiPath(`/admin/debug-bundles/${id}/download`)
      const headers: HeadersInit = {}
      if (token) headers.authorization = `Bearer ${token}`
      const res = await fetch(url, { method: "GET", headers, cache: "no-store" })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || res.statusText)
      }
      const blob = await res.blob()
      const a = document.createElement("a")
      a.href = URL.createObjectURL(blob)
      a.download = `debug-bundle-${id}.json`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (e) {
      setErr(formatErr(e, "Download failed."))
    } finally {
      setDownloading(false)
    }
  }, [])

  const status = bundle ? readStr(bundle, ["status"]) : ""
  const bundleId = bundle && typeof bundle.id === "number" ? bundle.id : null
  const canDownload = Boolean(
    bundleId && status === "created" && readStr(bundle ?? {}, ["bundle_sha256"]),
  )
  const warnings = bundle ? readStringList(bundle, "warnings_json") : []
  const notes = bundle ? readStringList(bundle, "notes_json") : []

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-mono text-2xl font-bold tracking-tight">Debug Bundles</h1>
            <InfoTooltip content={DEBUG_BUNDLE_TOOLTIP} label="About debug bundles" />
          </div>
          <p className="text-muted-foreground">
            Generate safe diagnostic bundles for troubleshooting failed workflows, jobs, sessions, reports, or system
            issues.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      <Alert>
        <AlertTitle>Content safety</AlertTitle>
        <AlertDescription className="text-sm">
          Debug bundles must not contain raw uploaded files, secrets, passwords, tokens, or private user data.
        </AlertDescription>
      </Alert>

      {err ? (
        <Alert variant="destructive">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription className="flex items-start gap-2 text-xs">
            <ServerOff className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>{err}</span>
          </AlertDescription>
        </Alert>
      ) : null}

      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Create bundle</h2>
        <ModuleCard
          accent="slate"
          eyebrow="Create"
          title="New debug bundle"
          icon={Plus}
          description="Capture a snapshot of session, project, or sample state for support investigations. Includes job summaries and artifact metadata; recent audit events and file hashes are optional."
        >
          <div className="space-y-4 text-sm">
            <div className="space-y-2">
              <Label htmlFor="db-title">title</Label>
              <Input
                id="db-title"
                placeholder="Optional title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={300}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>scope</Label>
                <Select value={scope} onValueChange={setScope}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="scope" />
                  </SelectTrigger>
                  <SelectContent>
                    {SCOPE_OPTIONS.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="db-resource">resource ID (optional)</Label>
                <Input
                  id="db-resource"
                  placeholder="resource_id"
                  value={resourceId}
                  onChange={(e) => setResourceId(e.target.value)}
                  maxLength={100}
                />
              </div>
            </div>
            <div className="flex flex-col gap-4 rounded-md border p-3">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <Label htmlFor="sw-audit" className="text-sm font-medium">
                    include recent audit events
                  </Label>
                  <p className="text-xs text-muted-foreground">Append the most recent audit log entries scoped to the bundle.</p>
                </div>
                <Switch
                  id="sw-audit"
                  checked={includeRecentAudit}
                  onCheckedChange={setIncludeRecentAudit}
                  disabled={loadingCreate}
                />
              </div>
              <div className="flex items-center justify-between gap-4">
                <div>
                  <Label htmlFor="sw-hash" className="text-sm font-medium">
                    include file hashes
                  </Label>
                  <p className="text-xs text-muted-foreground">Capture SHA-256 hashes of every artifact for integrity verification.</p>
                </div>
                <Switch
                  id="sw-hash"
                  checked={includeFileHashes}
                  onCheckedChange={setIncludeFileHashes}
                  disabled={loadingCreate}
                />
              </div>
              <div className="space-y-1 border-t pt-3 text-xs text-muted-foreground">
                <p className="font-medium text-foreground">Other bundle content</p>
                <p>
                  Job summaries and artifact metadata are always included; they aren&apos;t configurable per bundle.
                </p>
              </div>
            </div>
            <Button type="button" disabled={loadingCreate} onClick={() => void createBundle()}>
              {loadingCreate ? "Creating…" : "Create debug bundle"}
            </Button>
          </div>
        </ModuleCard>
      </div>

      <div>
        <h2 className="mb-3 text-sm font-medium text-muted-foreground">Load existing</h2>
        <ModuleCard
          accent="slate"
          eyebrow="Load"
          title="Fetch bundle"
          icon={FolderDown}
          description="Load a previously created debug bundle by its ID."
        >
          <div className="flex flex-wrap items-end gap-2">
            <div className="space-y-2">
              <Label htmlFor="db-load-id">bundle id</Label>
              <Input
                id="db-load-id"
                inputMode="numeric"
                className="w-40"
                value={loadId}
                onChange={(e) => setLoadId(e.target.value)}
              />
            </div>
            <Button type="button" variant="secondary" disabled={loadingGet} onClick={() => void getBundle(loadId)}>
              {loadingGet ? "Loading…" : "Load bundle"}
            </Button>
          </div>
        </ModuleCard>
      </div>

      {bundle ? (
        <div>
          <h2 className="mb-3 text-sm font-medium text-muted-foreground">Latest bundle</h2>
          <ModuleCard
            accent="slate"
            eyebrow="Detail"
            title="Bundle details"
            icon={FileText}
          >
            <div className="space-y-3 text-sm">
              <dl className="grid gap-2 text-xs sm:grid-cols-2">
                <div>
                  <dt className="text-muted-foreground">id</dt>
                  <dd className="font-mono">{bundleId != null ? String(bundleId) : "—"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">status</dt>
                  <dd className="font-mono">{status || "—"}</dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="text-muted-foreground">bundle_sha256</dt>
                  <dd className="break-all font-mono text-[10px]">{readStr(bundle, ["bundle_sha256"]) || "—"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">title</dt>
                  <dd>{readStr(bundle, ["title"]) || "—"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">scope</dt>
                  <dd className="font-mono">{readStr(bundle, ["scope"]) || "—"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">resource_id</dt>
                  <dd className="font-mono">{readStr(bundle, ["resource_id"]) || "—"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">created_at</dt>
                  <dd className="font-mono text-[10px]">{readStr(bundle, ["created_at"]) || "—"}</dd>
                </div>
              </dl>
              {warnings.length > 0 ? (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">warnings_json</p>
                  <ul className="mt-1 list-inside list-disc text-xs">
                    {warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {notes.length > 0 ? (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">notes_json</p>
                  <ul className="mt-1 list-inside list-disc text-xs">
                    {notes.map((n, i) => (
                      <li key={i}>{n}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {bundleId != null && canDownload ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={downloading}
                  className="gap-2"
                  onClick={() => void downloadBundle(bundleId)}
                >
                  <Download className="h-4 w-4" aria-hidden />
                  {downloading ? "Downloading…" : "Download JSON"}
                </Button>
              ) : bundleId != null ? (
                <p className="text-xs text-muted-foreground">
                  Download becomes available once the bundle finishes building and its checksum is recorded.
                </p>
              ) : null}
            </div>
          </ModuleCard>
        </div>
      ) : null}
    </div>
  )
}
