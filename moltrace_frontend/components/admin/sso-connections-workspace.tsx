"use client"

import { useCallback, useEffect, useState } from "react"
import { Check, Copy, KeyRound, Loader2, Pencil, ShieldAlert, Trash2, X } from "lucide-react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { ModuleCard } from "@/components/dashboard/module-card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ScimProvisioningSection } from "@/components/admin/scim-provisioning-section"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { cn } from "@/lib/utils"
import type { components } from "@/src/lib/api/schema"

type SSOConnection = components["schemas"]["SSOConnectionOut"]
type SSOConnectionList = components["schemas"]["SSOConnectionList"]
type SSOConnectionCreate = components["schemas"]["SSOConnectionCreate"]
type SSOConnectionUpdate = components["schemas"]["SSOConnectionUpdate"]

// Mirrors the backend slug constraint: lowercase, digits, hyphens; 2+ chars.
const SLUG_RE = /^[a-z0-9][a-z0-9-]*[a-z0-9]$/

// The IdP redirect URI is `{API_ORIGIN}/auth/sso/callback`, computed server-side
// by the backend. Surface the exact value when the API origin is configured for
// the client; otherwise show a clear template the admin completes.
const SSO_API_ORIGIN = (process.env.NEXT_PUBLIC_SSO_API_ORIGIN || "").trim().replace(/\/$/, "")
const REDIRECT_URI = SSO_API_ORIGIN ? `${SSO_API_ORIGIN}/auth/sso/callback` : ""
const REDIRECT_URI_PLACEHOLDER = "https://<your-api-origin>/auth/sso/callback"

type FormState = {
  organization_id: string
  slug: string
  display_name: string
  issuer: string
  client_id: string
  client_secret: string
  email_domains: string
  enabled: boolean
  enforce_sso: boolean
}

const EMPTY_FORM: FormState = {
  organization_id: "",
  slug: "",
  display_name: "",
  issuer: "",
  client_id: "",
  client_secret: "",
  email_domains: "",
  enabled: true,
  enforce_sso: false,
}

function parseDomains(raw: string): string[] {
  return raw
    .split(/[\s,]+/)
    .map((d) => d.trim().toLowerCase())
    .filter(Boolean)
}

export function SSOConnectionsWorkspace() {
  const [connections, setConnections] = useState<SSOConnection[]>([])
  const [loading, setLoading] = useState(true)
  const [loadErr, setLoadErr] = useState("")

  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [formErr, setFormErr] = useState("")
  const [formMsg, setFormMsg] = useState("")
  const [busyId, setBusyId] = useState<number | null>(null)
  const [copied, setCopied] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadErr("")
    try {
      const res = await apiFetch<SSOConnectionList>("/auth/sso/connections", { method: "GET" })
      setConnections(Array.isArray(res?.connections) ? res.connections : [])
    } catch (err) {
      setLoadErr(formatApiError(err, "Could not load SSO connections."))
      setConnections([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  function resetForm() {
    setForm(EMPTY_FORM)
    setEditingId(null)
    setFormErr("")
    setFormMsg("")
  }

  function startEdit(c: SSOConnection) {
    setEditingId(c.id)
    setFormErr("")
    setFormMsg("")
    setForm({
      organization_id: String(c.organization_id),
      slug: c.slug,
      display_name: c.display_name,
      issuer: c.issuer,
      client_id: c.client_id,
      client_secret: "", // write-only — never read back; blank keeps the stored secret
      email_domains: (c.email_domains ?? []).join(", "),
      enabled: c.enabled,
      enforce_sso: c.enforce_sso,
    })
  }

  async function copyRedirectUri() {
    if (!REDIRECT_URI) return
    try {
      await navigator.clipboard.writeText(REDIRECT_URI)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      // clipboard unavailable — the value is visible to copy manually
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setFormErr("")
    setFormMsg("")

    const orgId = Number(form.organization_id)
    if (!Number.isInteger(orgId) || orgId < 1) {
      setFormErr("Organization ID must be a positive integer.")
      return
    }
    const slug = form.slug.trim().toLowerCase()
    if (!editingId && !SLUG_RE.test(slug)) {
      setFormErr("Slug must be lowercase letters, digits, and hyphens (e.g. acme).")
      return
    }
    if (!form.display_name.trim()) return setFormErr("Display name is required.")
    if (!form.issuer.trim()) return setFormErr("Issuer URL is required.")
    if (!form.client_id.trim()) return setFormErr("Client ID is required.")
    if (!editingId && !form.client_secret.trim()) {
      return setFormErr("Client secret is required when creating a connection.")
    }

    setSubmitting(true)
    try {
      if (editingId) {
        const body: SSOConnectionUpdate = {
          display_name: form.display_name.trim(),
          issuer: form.issuer.trim(),
          client_id: form.client_id.trim(),
          email_domains: parseDomains(form.email_domains),
          enabled: form.enabled,
          enforce_sso: form.enforce_sso,
        }
        // Only send client_secret when rotating — a blank field keeps the stored one.
        if (form.client_secret.trim()) body.client_secret = form.client_secret
        await apiFetch(`/auth/sso/connections/${editingId}`, { method: "PATCH", body })
        setFormMsg("Connection updated.")
      } else {
        const body: SSOConnectionCreate = {
          organization_id: orgId,
          slug,
          display_name: form.display_name.trim(),
          issuer: form.issuer.trim(),
          client_id: form.client_id.trim(),
          client_secret: form.client_secret,
          email_domains: parseDomains(form.email_domains),
          enabled: form.enabled,
          enforce_sso: form.enforce_sso,
        }
        await apiFetch("/auth/sso/connections", { method: "POST", body })
        setFormMsg("Connection created.")
      }
      resetForm()
      await load()
    } catch (err) {
      setFormErr(formatApiError(err, "Could not save the connection."))
    } finally {
      setSubmitting(false)
    }
  }

  async function remove(c: SSOConnection) {
    if (
      typeof window !== "undefined" &&
      !window.confirm(
        `Delete SSO connection "${c.display_name}" (${c.slug})? Users in this organization will fall back to password login.`,
      )
    ) {
      return
    }
    setBusyId(c.id)
    setLoadErr("")
    try {
      await apiFetch(`/auth/sso/connections/${c.id}`, { method: "DELETE" })
      if (editingId === c.id) resetForm()
      await load()
    } catch (err) {
      setLoadErr(formatApiError(err, "Could not delete the connection."))
    } finally {
      setBusyId(null)
    }
  }

  const enforceDomains = parseDomains(form.email_domains)
  // The SAVED connection being edited — drives the SCIM gate off persisted
  // `enabled`, not the form's unsaved toggle.
  const editingConn = editingId != null ? connections.find((c) => c.id === editingId) ?? null : null

  return (
    <div className="space-y-6">
      <ModuleCard
        accent="violet"
        eyebrow="Admin · Authentication"
        title={
          <span className="inline-flex items-center gap-2">
            <KeyRound className="h-4 w-4" aria-hidden />
            Enterprise SSO (OIDC)
          </span>
        }
        description="Per-organization OpenID Connect federation. Each connection points an organization's email domains at its identity provider; first-time users are provisioned on sign-in (JIT). Connection management is admin-only."
      >
        {/* Redirect URI to register with the IdP */}
        <div className="rounded-lg border bg-muted/20 p-3">
          <div className="flex items-center justify-between gap-2">
            <Label className="text-xs uppercase tracking-wide text-muted-foreground">Redirect URI to register with the IdP</Label>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => void copyRedirectUri()}
              disabled={!REDIRECT_URI}
              aria-label="Copy redirect URI"
            >
              {copied ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
              <span className="ml-1.5 text-xs">{copied ? "Copied" : "Copy"}</span>
            </Button>
          </div>
          <code className="mt-1 block break-all font-mono text-xs">{REDIRECT_URI || REDIRECT_URI_PLACEHOLDER}</code>
          <p className="mt-1 text-xs text-muted-foreground">
            Add this exact URI to the IdP application&apos;s allowed redirect URIs. The backend computes it from its own
            base URL — it is never client-supplied.
            {REDIRECT_URI ? null : " Set NEXT_PUBLIC_SSO_API_ORIGIN to display the exact value."}
          </p>
        </div>
      </ModuleCard>

      {/* Connections table */}
      <ModuleCard accent="slate" eyebrow="Admin · Authentication" title="SSO connections">
        {loadErr ? <AlertCard variant="error" title="Could not load connections" description={loadErr} /> : null}
        {loading ? (
          <p className="text-sm text-muted-foreground">
            <Loader2 className="mr-2 inline h-4 w-4 animate-spin" aria-hidden />
            Loading connections…
          </p>
        ) : connections.length === 0 ? (
          <p className="text-sm text-muted-foreground">No SSO connections yet. Create one below.</p>
        ) : (
          <div className="overflow-x-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Display name</TableHead>
                  <TableHead>Slug</TableHead>
                  <TableHead>Issuer</TableHead>
                  <TableHead>Email domains</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {connections.map((c) => (
                  <TableRow key={c.id} data-testid={`sso-row-${c.id}`}>
                    <TableCell className="font-medium">{c.display_name}</TableCell>
                    <TableCell className="font-mono text-xs">{c.slug}</TableCell>
                    <TableCell className="max-w-[220px] truncate font-mono text-xs" title={c.issuer}>
                      {c.issuer}
                    </TableCell>
                    <TableCell className="text-xs">
                      {c.email_domains.length ? c.email_domains.join(", ") : <span className="text-muted-foreground">any</span>}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        <Badge
                          variant="outline"
                          className={cn("font-normal", c.enabled ? "border-success/50 text-success" : "text-muted-foreground")}
                        >
                          {c.enabled ? "enabled" : "disabled"}
                        </Badge>
                        {c.enforce_sso ? (
                          <Badge variant="outline" className="gap-1 border-warning/50 font-normal text-warning">
                            <ShieldAlert className="h-3 w-3" aria-hidden />
                            enforced
                          </Badge>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="inline-flex gap-1">
                        <Button type="button" size="sm" variant="ghost" onClick={() => startEdit(c)} aria-label={`Edit ${c.slug}`}>
                          <Pencil className="h-3.5 w-3.5" aria-hidden />
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          onClick={() => void remove(c)}
                          disabled={busyId === c.id}
                          aria-label={`Delete ${c.slug}`}
                        >
                          {busyId === c.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                          ) : (
                            <Trash2 className="h-3.5 w-3.5 text-destructive" aria-hidden />
                          )}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </ModuleCard>

      {/* Create / edit form */}
      <ModuleCard
        accent="violet"
        eyebrow="Admin · Authentication"
        title={editingId ? `Edit connection — ${form.display_name || form.slug}` : "New SSO connection"}
      >
        <form className="space-y-4" onSubmit={submit}>
          {formErr ? <AlertCard variant="error" title="Could not save" description={formErr} /> : null}
          {formMsg ? <AlertCard variant="success" title={formMsg} /> : null}

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="sso-org">Organization ID</Label>
              <Input
                id="sso-org"
                inputMode="numeric"
                value={form.organization_id}
                onChange={(e) => set("organization_id", e.target.value)}
                disabled={editingId != null}
                placeholder="12"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sso-slug-field">Slug</Label>
              <Input
                id="sso-slug-field"
                value={form.slug}
                onChange={(e) => set("slug", e.target.value)}
                disabled={editingId != null}
                placeholder="acme"
                spellCheck={false}
              />
              <p className="text-xs text-muted-foreground">
                URL-safe; used in <code>/auth/sso/{form.slug.trim() || "{slug}"}/login</code>. Immutable after creation.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sso-display">Display name</Label>
              <Input id="sso-display" value={form.display_name} onChange={(e) => set("display_name", e.target.value)} placeholder="Acme Okta" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sso-issuer">Issuer</Label>
              <Input
                id="sso-issuer"
                value={form.issuer}
                onChange={(e) => set("issuer", e.target.value)}
                placeholder="https://acme.okta.com"
                spellCheck={false}
              />
              <p className="text-xs text-muted-foreground">OIDC issuer; discovery is {`{issuer}`}/.well-known/openid-configuration.</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sso-client-id">Client ID</Label>
              <Input id="sso-client-id" value={form.client_id} onChange={(e) => set("client_id", e.target.value)} spellCheck={false} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sso-client-secret">Client secret {editingId ? "(rotate)" : ""}</Label>
              <Input
                id="sso-client-secret"
                type="password"
                value={form.client_secret}
                onChange={(e) => set("client_secret", e.target.value)}
                placeholder={editingId ? "leave blank to keep current" : "stored encrypted; never displayed"}
                autoComplete="new-password"
                spellCheck={false}
              />
              <p className="text-xs text-muted-foreground">
                Write-only — stored AES-256-GCM encrypted and never returned by the API.
                {editingId ? " Leave blank to keep the current secret." : ""}
              </p>
            </div>
            <div className="space-y-1.5 md:col-span-2">
              <Label htmlFor="sso-domains">Email domains</Label>
              <Input
                id="sso-domains"
                value={form.email_domains}
                onChange={(e) => set("email_domains", e.target.value)}
                placeholder="acme.com, acme.co.uk"
                spellCheck={false}
              />
              <p className="text-xs text-muted-foreground">Comma- or space-separated. Empty = any asserted email domain is accepted.</p>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex items-center justify-between gap-3 rounded-md border p-3" htmlFor="sso-enabled">
              <span>
                <span className="block text-sm font-medium">Enabled</span>
                <span className="block text-xs text-muted-foreground">Allow sign-in through this connection.</span>
              </span>
              <Switch id="sso-enabled" checked={form.enabled} onCheckedChange={(v) => set("enabled", v)} />
            </label>
            <label className="flex items-center justify-between gap-3 rounded-md border p-3" htmlFor="sso-enforce">
              <span>
                <span className="block text-sm font-medium">Enforce SSO</span>
                <span className="block text-xs text-muted-foreground">Block password login for these domains.</span>
              </span>
              <Switch id="sso-enforce" checked={form.enforce_sso} onCheckedChange={(v) => set("enforce_sso", v)} />
            </label>
          </div>

          {form.enforce_sso ? (
            <AlertCard
              variant="warning"
              icon={ShieldAlert}
              title="Password login will be blocked"
              description={
                enforceDomains.length
                  ? `Users with email domains ${enforceDomains.join(", ")} must sign in through the identity provider; their password sign-in will be rejected.`
                  : "Add at least one email domain — enforce-SSO applies to the connection's email domains."
              }
            />
          ) : null}

          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={submitting}>
              {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
              {editingId ? "Save changes" : "Create connection"}
            </Button>
            {editingId ? (
              <Button type="button" variant="ghost" onClick={resetForm} disabled={submitting}>
                <X className="mr-1.5 h-4 w-4" aria-hidden />
                Cancel edit
              </Button>
            ) : null}
          </div>
        </form>

        {/* SCIM provisioning — token management for this connection (outside the
            form so its actions never submit the connection). Edit view only. */}
        {editingId != null ? (
          <div className="mt-6 border-t pt-6">
            <h3 className="text-sm font-semibold">SCIM provisioning</h3>
            <p className="mb-3 mt-0.5 text-xs text-muted-foreground">
              Issue the bearer token your identity provider uses to auto-provision (and deprovision) users into this
              organization via SCIM 2.0. The token is machine-facing — the IdP calls <code>/scim/v2</code> directly.
            </p>
            <ScimProvisioningSection connectionId={editingId} enabled={editingConn?.enabled ?? false} />
          </div>
        ) : null}
      </ModuleCard>
    </div>
  )
}
