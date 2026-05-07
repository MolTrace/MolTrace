"use client"

import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { apiFetch, ApiError } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { normalizeProjectListPayload, readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { parseReactionProjectList, type ReactionProjectRow } from "@/src/lib/reaction-projects/reaction-projects-data"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
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
import { Textarea } from "@/components/ui/textarea"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { trackRegulatoryDossierCreated } from "@/src/lib/analytics/analytics-client"
import { RegulatoryNotificationsCompactCard } from "@/components/regulatory-hub/regulatory-notifications-compact-card"
import { RegulatoryHubValidationReadinessCard } from "@/components/validation/validation-readiness-summary"
import { AlertTriangle, BookOpen, ClipboardList, Eye, FolderOpen, Loader2 } from "lucide-react"

type DossierRow = Record<string, unknown>
type JurisdictionRow = { id: number; name: string }
type SampleOption = { id: number; label: string }
type DossierEnrichment = {
  requirementsCount: number
  missingEvidenceCount: number
  risk?: string
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function asArray(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (data && typeof data === "object") {
    const o = data as Record<string, unknown>
    if (Array.isArray(o.items)) return o.items
    if (Array.isArray(o.results)) return o.results
  }
  return []
}

function normalizeDossierList(payload: unknown): DossierRow[] {
  return asArray(payload).filter(isRecord) as DossierRow[]
}

function normalizeRequirementsList(payload: unknown): Record<string, unknown>[] {
  return asArray(payload).filter(isRecord) as Record<string, unknown>[]
}

function dossierNumericId(row: DossierRow): number | undefined {
  const id = readRecordNumber(row, "id")
  return id
}

function formatWhen(iso: string | undefined): string {
  if (!iso?.trim()) return "—"
  const d = Date.parse(iso)
  if (Number.isNaN(d)) return iso
  return new Date(d).toLocaleString()
}

function parseJurisdictionList(raw: unknown): JurisdictionRow[] {
  const rows = asArray(raw).filter(isRecord)
  const out: JurisdictionRow[] = []
  for (const row of rows) {
    const id = readRecordNumber(row, "id")
    const name = readRecordString(row, "name")
    if (id != null && name) out.push({ id, name })
  }
  return out
}

function parseSourceRows(raw: unknown): { id: number; title: string; source_type: string; status: string; version?: string }[] {
  const rows = asArray(raw).filter(isRecord)
  const out: { id: number; title: string; source_type: string; status: string; version?: string }[] = []
  for (const row of rows) {
    const id = readRecordNumber(row, "id")
    const title = readRecordString(row, "title")
    const source_type = readRecordString(row, "source_type") ?? "—"
    const status = readRecordString(row, "status") ?? "—"
    const version = readRecordString(row, "version")
    if (id != null && title) out.push({ id, title, source_type, status, version })
  }
  return out
}

function requirementStatus(row: Record<string, unknown>): string {
  return readRecordString(row, "status") ?? ""
}

async function mapInChunks<T, R>(items: T[], size: number, fn: (item: T) => Promise<R>): Promise<R[]> {
  const out: R[] = []
  for (let i = 0; i < items.length; i += size) {
    const chunk = items.slice(i, i + size)
    out.push(...(await Promise.all(chunk.map(fn))))
  }
  return out
}

async function fetchOverallRisk(dossierId: number): Promise<string | undefined> {
  try {
    const r = await apiFetch<Record<string, unknown>>(`/regulatory/dossiers/${dossierId}/risk-assessment`, {
      method: "GET",
    })
    const level = readRecordString(r, "overall_risk")
    return level || undefined
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return undefined
    return undefined
  }
}

function SummaryMetricCard({
  title,
  icon,
  value,
  sub,
}: {
  title: string
  icon: React.ReactNode
  value: string
  sub: React.ReactNode
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold tabular-nums">{value}</div>
        {sub}
      </CardContent>
    </Card>
  )
}

export function RegulatoryIntelligenceLanding() {
  const searchParams = useSearchParams()
  const appliedQueryParams = useRef(false)

  const [loading, setLoading] = useState(true)
  const [dossiers, setDossiers] = useState<DossierRow[]>([])
  const [dossierListError, setDossierListError] = useState("")
  const [enrichBusy, setEnrichBusy] = useState(false)
  const [enrichmentById, setEnrichmentById] = useState<Record<number, DossierEnrichment>>({})
  const [jurisdictions, setJurisdictions] = useState<JurisdictionRow[]>([])
  const [sources, setSources] = useState<ReturnType<typeof parseSourceRows>>([])
  const [sourcesUnavailable, setSourcesUnavailable] = useState(false)

  const [projects, setProjects] = useState<{ id: number; name: string }[]>([])
  const [samples, setSamples] = useState<SampleOption[]>([])
  const [reactionProjects, setReactionProjects] = useState<ReactionProjectRow[]>([])

  const [selectedProjectId, setSelectedProjectId] = useState<string>("")

  const [createTitle, setCreateTitle] = useState("")
  const [createSampleId, setCreateSampleId] = useState<string>("")
  const [spectraSessionId, setSpectraSessionId] = useState("")
  const [reactionProjectId, setReactionProjectId] = useState<string>("")
  const [createJurisdictionId, setCreateJurisdictionId] = useState<string>("")
  const [intendedUse, setIntendedUse] = useState("")
  const [compoundName, setCompoundName] = useState("")
  const [productName, setProductName] = useState("")
  const [createBusy, setCreateBusy] = useState(false)
  const [createError, setCreateError] = useState("")
  const [createSucceeded, setCreateSucceeded] = useState(false)

  const loadAuxLists = useCallback(async () => {
    try {
      const pr = await apiFetch<unknown>("/projects", { method: "GET" })
      const projectRows = normalizeProjectListPayload(pr)
      const parsed: { id: number; name: string }[] = []
      for (const raw of projectRows) {
        if (!isRecord(raw)) continue
        const id = readRecordNumber(raw, "id")
        const name = readRecordString(raw, "name") ?? readRecordString(raw, "project_name")
        if (id != null && name) parsed.push({ id, name })
      }
      setProjects(parsed)
    } catch {
      setProjects([])
    }

    try {
      const rr = await apiFetch<unknown>("/reaction-projects", { method: "GET" })
      setReactionProjects(parseReactionProjectList(rr))
    } catch {
      setReactionProjects([])
    }
  }, [])

  const loadSamplesForProject = useCallback(async (projectIdNum: number) => {
    try {
      const raw = await apiFetch<unknown>(`/projects/${encodeURIComponent(projectIdNum)}/samples`, { method: "GET" })
      const rows = asArray(raw).filter(isRecord)
      const opts: SampleOption[] = []
      for (const row of rows) {
        const id = readRecordNumber(row, "id")
        if (id == null) continue
        const human = readRecordString(row, "sample_id")
        opts.push({ id, label: human ? `${human} (#${id})` : `Sample #${id}` })
      }
      setSamples(opts)
    } catch {
      setSamples([])
    }
  }, [])

  const enrichDossiers = useCallback(async (rows: DossierRow[]) => {
    setEnrichBusy(true)
    const next: Record<number, DossierEnrichment> = {}
    try {
      const enriched = await mapInChunks(rows, 4, async (row) => {
        const did = dossierNumericId(row)
        if (did == null) return { did: -1, data: { requirementsCount: 0, missingEvidenceCount: 0, risk: undefined } }
        let requirementsCount = 0
        let missingEvidenceCount = 0
        try {
          const reqRaw = await apiFetch<unknown>(`/regulatory/dossiers/${did}/requirements`, { method: "GET" })
          const reqs = normalizeRequirementsList(reqRaw)
          requirementsCount = reqs.length
          missingEvidenceCount = reqs.filter((r) => requirementStatus(r) === "evidence_needed").length
        } catch {
          /* retain zero counts when requirements are unavailable */
        }
        const risk = await fetchOverallRisk(did)
        return { did, data: { requirementsCount, missingEvidenceCount, risk } }
      })
      for (const item of enriched) {
        if (item.did >= 0) next[item.did] = item.data
      }
      setEnrichmentById(next)
    } finally {
      setEnrichBusy(false)
    }
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setDossierListError("")
    setCreateSucceeded(false)
    setSourcesUnavailable(false)

    await loadAuxLists()

    const [dossierOutcome, jurOutcome] = await Promise.allSettled([
      apiFetch<unknown>("/regulatory/dossiers", { method: "GET" }),
      apiFetch<unknown>("/regulatory/jurisdictions", { method: "GET" }),
    ])

    if (jurOutcome.status === "fulfilled") {
      setJurisdictions(parseJurisdictionList(jurOutcome.value))
    } else {
      setJurisdictions([])
    }

    const list: DossierRow[] =
      dossierOutcome.status === "fulfilled" ? normalizeDossierList(dossierOutcome.value) : []

    if (dossierOutcome.status === "fulfilled") {
      setDossiers(list)
      try {
        const srcPayload = await apiFetch<unknown>("/regulatory/sources", { method: "GET" })
        setSources(parseSourceRows(srcPayload))
        setSourcesUnavailable(false)
      } catch {
        setSources([])
        setSourcesUnavailable(true)
      }
    } else {
      setDossiers([])
      setSources([])
      setSourcesUnavailable(true)
      setDossierListError(
        formatApiError(dossierOutcome.reason, "Regulatory dossier service is unavailable.")
      )
    }

    setLoading(false)

    if (list.length) void enrichDossiers(list)
    else setEnrichmentById({})
  }, [enrichDossiers, loadAuxLists])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (appliedQueryParams.current) return
    const sid = searchParams.get("spectracheck_session_id") ?? searchParams.get("session")
    if (sid && /^\d+$/.test(sid.trim())) {
      setSpectraSessionId(sid.trim())
      appliedQueryParams.current = true
    }
  }, [searchParams])

  useEffect(() => {
    if (!selectedProjectId) {
      setSamples([])
      setCreateSampleId("")
      return
    }
    const n = Number.parseInt(selectedProjectId, 10)
    if (!Number.isFinite(n)) return
    void loadSamplesForProject(n)
  }, [selectedProjectId, loadSamplesForProject])

  const jurisdictionNameById = useMemo(() => {
    const m = new Map<number, string>()
    for (const j of jurisdictions) m.set(j.id, j.name)
    return m
  }, [jurisdictions])

  const unavailableSub = (
    <p className="text-xs text-muted-foreground">
      {dossierListError ? "Backend unavailable." : "Loading…"}
    </p>
  )

  const summary = useMemo(() => {
    if (dossierListError || (loading && !dossiers.length)) {
      return {
        mode: "unavailable" as const,
        activeDossiers: "—",
        reqsNeedEvidence: "—",
        inReview: "—",
        sourceDocs: "—",
        highRisk: "—",
      }
    }
    const active = dossiers.filter((d) => readRecordString(d, "status") !== "archived").length
    const inReview = dossiers.filter((d) => readRecordString(d, "status") === "in_review").length
    let reqsNeedEvidence = 0
    let highRisk = 0
    for (const d of dossiers) {
      const did = dossierNumericId(d)
      if (did == null) continue
      const e = enrichmentById[did]
      if (e) reqsNeedEvidence += e.missingEvidenceCount
      const r = e?.risk?.toLowerCase()
      if (r === "high" || r === "critical") highRisk += 1
    }
    return {
      mode: "live" as const,
      activeDossiers: String(active),
      reqsNeedEvidence: String(reqsNeedEvidence),
      inReview: String(inReview),
      sourceDocs: sourcesUnavailable ? "—" : String(sources.length),
      highRisk: String(highRisk),
    }
  }, [dossierListError, loading, dossiers, enrichmentById, sources.length, sourcesUnavailable])

  const liveMetricsSub = (
    <p className="text-xs text-muted-foreground">
      {enrichBusy ? "Refreshing requirement and risk aggregates…" : "Derived from loaded dossiers and evidence."}
    </p>
  )

  const sourceDocsSub =
    summary.mode === "live" ? (
      <p className="text-xs text-muted-foreground">
        {sourcesUnavailable ? "Source list unavailable." : "Registered regulatory source documents."}
      </p>
    ) : (
      unavailableSub
    )

  const reviewQueueRows = useMemo(() => {
    return dossiers.filter((d) => readRecordString(d, "status") === "in_review")
  }, [dossiers])

  async function submitCreate() {
    setCreateBusy(true)
    setCreateError("")
    setCreateSucceeded(false)
    try {
      const body: Record<string, unknown> = {
        title: createTitle.trim(),
      }
      if (!body.title || typeof body.title !== "string") {
        setCreateError("Title is required.")
        setCreateBusy(false)
        return
      }

      const pid = selectedProjectId ? Number.parseInt(selectedProjectId, 10) : NaN
      if (selectedProjectId && Number.isFinite(pid)) body.project_id = pid

      const sid = createSampleId ? Number.parseInt(createSampleId, 10) : NaN
      if (createSampleId && Number.isFinite(sid)) body.sample_id = sid

      const ssid = spectraSessionId.trim()
      if (ssid) {
        const n = Number.parseInt(ssid, 10)
        if (!Number.isFinite(n)) {
          setCreateError("SpectraCheck session ID must be numeric.")
          setCreateBusy(false)
          return
        }
        body.spectracheck_session_id = n
      }

      const rpid = reactionProjectId.trim()
      if (rpid) {
        const n = Number.parseInt(rpid, 10)
        if (!Number.isFinite(n)) {
          setCreateError("Reaction project ID must be numeric.")
          setCreateBusy(false)
          return
        }
        body.reaction_project_id = n
      }

      const jid = createJurisdictionId.trim()
      if (jid) {
        const n = Number.parseInt(jid, 10)
        if (!Number.isFinite(n)) {
          setCreateError("Jurisdiction selection is invalid.")
          setCreateBusy(false)
          return
        }
        body.jurisdiction_id = n
      }

      const use = intendedUse.trim()
      if (use) body.intended_use = use

      const cn = compoundName.trim()
      if (cn) body.compound_name = cn

      const pn = productName.trim()
      if (pn) body.product_name = pn

      const created = await apiFetch<DossierRow>("/regulatory/dossiers", {
        method: "POST",
        body,
      })
      const newId = readRecordNumber(created, "id")
      if (newId != null) {
        trackRegulatoryDossierCreated({
          dossier_id: newId,
          jurisdiction_id:
            typeof body.jurisdiction_id === "number" && Number.isFinite(body.jurisdiction_id)
              ? body.jurisdiction_id
              : null,
          status: readRecordString(created, "status") ?? "draft",
          requirement_count: 0,
          evidence_link_count: 0,
        })
      }

      setCreateSucceeded(true)
      setCreateTitle("")
      setSpectraSessionId("")
      setReactionProjectId("")
      setCreateJurisdictionId("")
      setIntendedUse("")
      setCompoundName("")
      setProductName("")
      await load()
    } catch (err) {
      setCreateError(formatApiError(err, "Create dossier failed."))
    } finally {
      setCreateBusy(false)
    }
  }

  const scrollToReview = () => {
    document.getElementById("regulatory-review-queue")?.scrollIntoView({ behavior: "smooth", block: "start" })
  }

  return (
    <div className="mx-auto max-w-[1200px] space-y-8 pb-12">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Regulatory Intelligence</h1>
        <p className="max-w-3xl text-muted-foreground">
          Build cited, reviewable dossiers from analytical evidence, requirements, and source documents.
        </p>
      </header>

      {dossierListError ? (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Backend unavailable</AlertTitle>
          <AlertDescription className="text-sm">{dossierListError}</AlertDescription>
        </Alert>
      ) : null}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5" aria-label="Summary">
        <SummaryMetricCard
          title="Active dossiers"
          icon={<FolderOpen className="h-4 w-4 text-muted-foreground" />}
          value={summary.activeDossiers}
          sub={
            summary.mode === "unavailable" ? (
              unavailableSub
            ) : (
              <p className="text-xs text-muted-foreground">Excludes archived dossiers.</p>
            )
          }
        />
        <SummaryMetricCard
          title="Requirements needing evidence"
          icon={<ClipboardList className="h-4 w-4 text-muted-foreground" />}
          value={summary.reqsNeedEvidence}
          sub={summary.mode === "unavailable" ? unavailableSub : liveMetricsSub}
        />
        <SummaryMetricCard
          title="Dossiers in review"
          icon={<Eye className="h-4 w-4 text-muted-foreground" />}
          value={summary.inReview}
          sub={summary.mode === "unavailable" ? unavailableSub : liveMetricsSub}
        />
        <SummaryMetricCard
          title="Source documents"
          icon={<BookOpen className="h-4 w-4 text-muted-foreground" />}
          value={summary.sourceDocs}
          sub={sourceDocsSub}
        />
        <SummaryMetricCard
          title="High-risk dossiers"
          icon={<AlertTriangle className="h-4 w-4 text-muted-foreground" />}
          value={summary.highRisk}
          sub={
            summary.mode === "unavailable" ? (
              unavailableSub
            ) : (
              <p className="text-xs text-muted-foreground">Latest saved risk level high or critical.</p>
            )
          }
        />
      </section>

      <RegulatoryHubValidationReadinessCard />

      <RegulatoryNotificationsCompactCard />

      <section aria-labelledby="create-dossier-heading">
        <Card>
          <CardHeader>
            <CardTitle id="create-dossier-heading" className="text-lg">
              Create dossier
            </CardTitle>
            <CardDescription>POST /regulatory/dossiers — optional links are omitted when empty.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="reg-create-title">title</Label>
                <Input
                  id="reg-create-title"
                  value={createTitle}
                  onChange={(e) => setCreateTitle(e.target.value)}
                  placeholder="Dossier title"
                  disabled={loading}
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label>project selector optional</Label>
                <Select
                  value={selectedProjectId || "none"}
                  onValueChange={(v) => setSelectedProjectId(v === "none" ? "" : v)}
                  disabled={loading}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="No project linked" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">No project</SelectItem>
                    {projects.map((p) => (
                      <SelectItem key={p.id} value={String(p.id)}>
                        {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>sample selector optional</Label>
                <Select
                  value={createSampleId || "none"}
                  onValueChange={(v) => setCreateSampleId(v === "none" ? "" : v)}
                  disabled={loading || !selectedProjectId || samples.length === 0}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={selectedProjectId ? "Select sample" : "Choose a project first"} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">No sample</SelectItem>
                    {samples.map((s) => (
                      <SelectItem key={s.id} value={String(s.id)}>
                        {s.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="reg-spectra-session">SpectraCheck session ID optional</Label>
                <Input
                  id="reg-spectra-session"
                  value={spectraSessionId}
                  onChange={(e) => setSpectraSessionId(e.target.value)}
                  placeholder="Numeric session id"
                  inputMode="numeric"
                  disabled={loading}
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label>reaction project ID optional</Label>
                <Select
                  value={reactionProjectId || "none"}
                  onValueChange={(v) => setReactionProjectId(v === "none" ? "" : v)}
                  disabled={loading}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="No reaction project" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">No reaction project</SelectItem>
                    {reactionProjects.map((p) => (
                      <SelectItem key={p.id} value={String(p.id)}>
                        {p.name} (#{p.id})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>jurisdiction selector</Label>
                <Select
                  value={createJurisdictionId || "none"}
                  onValueChange={(v) => setCreateJurisdictionId(v === "none" ? "" : v)}
                  disabled={loading}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={jurisdictions.length ? "Select jurisdiction" : "No jurisdictions loaded"} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Not specified</SelectItem>
                    {jurisdictions.map((j) => (
                      <SelectItem key={j.id} value={String(j.id)}>
                        {j.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="reg-intended-use">intended use</Label>
                <Textarea
                  id="reg-intended-use"
                  rows={3}
                  value={intendedUse}
                  onChange={(e) => setIntendedUse(e.target.value)}
                  placeholder="Describe scope for this dossier record"
                  disabled={loading}
                />
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="reg-compound">compound/product name optional</Label>
                <div className="grid gap-2 sm:grid-cols-2">
                  <Input
                    id="reg-compound"
                    value={compoundName}
                    onChange={(e) => setCompoundName(e.target.value)}
                    placeholder="compound_name"
                    disabled={loading}
                    autoComplete="off"
                  />
                  <Input
                    id="reg-product"
                    value={productName}
                    onChange={(e) => setProductName(e.target.value)}
                    placeholder="product_name"
                    disabled={loading}
                    autoComplete="off"
                  />
                </div>
              </div>
            </div>
            {createError ? (
              <Alert variant="destructive">
                <AlertTitle>Create failed</AlertTitle>
                <AlertDescription className="text-sm">{createError}</AlertDescription>
              </Alert>
            ) : null}
            {createSucceeded ? (
              <Alert>
                <AlertTitle>Dossier created</AlertTitle>
                <AlertDescription className="text-sm">The list below was refreshed from the server.</AlertDescription>
              </Alert>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button className="gap-2" disabled={createBusy || loading} onClick={() => void submitCreate()}>
                {createBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                Create dossier
              </Button>
            </div>
          </CardContent>
        </Card>
      </section>

      <section aria-labelledby="dossiers-table-heading" className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 id="dossiers-table-heading" className="text-lg font-semibold tracking-tight">
              Dossiers
            </h2>
            <p className="text-sm text-muted-foreground">GET /regulatory/dossiers</p>
          </div>
          {enrichBusy ? (
            <Badge variant="outline" className="gap-1 font-normal">
              <Loader2 className="h-3 w-3 animate-spin" />
              Loading evidence metrics
            </Badge>
          ) : null}
        </div>
        <Card>
          <CardContent className="pt-6">
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading dossiers…</p>
            ) : dossierListError ? (
              <p className="text-sm text-muted-foreground">Dossier list could not be loaded.</p>
            ) : dossiers.length === 0 ? (
              <p className="text-sm text-muted-foreground">No dossiers yet.</p>
            ) : (
              <div className="table-scroll">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>title</TableHead>
                      <TableHead>jurisdiction</TableHead>
                      <TableHead>intended use</TableHead>
                      <TableHead>status</TableHead>
                      <TableHead className="text-right">requirements count</TableHead>
                      <TableHead className="text-right">missing evidence count</TableHead>
                      <TableHead>risk</TableHead>
                      <TableHead>updated date</TableHead>
                      <TableHead className="w-[100px]">open button</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {dossiers.map((row) => {
                      const id = dossierNumericId(row)
                      const title = readRecordString(row, "title") ?? "—"
                      const jid = readRecordNumber(row, "jurisdiction_id")
                      const jLabel =
                        jid != null ? jurisdictionNameById.get(jid) ?? `jurisdiction_id ${jid}` : "—"
                      const use = readRecordString(row, "intended_use") ?? "—"
                      const status = readRecordString(row, "status") ?? "—"
                      const updated = formatWhen(readRecordString(row, "updated_at") ?? readRecordString(row, "updatedAt"))
                      const e = id != null ? enrichmentById[id] : undefined
                      const reqC = e?.requirementsCount
                      const missC = e?.missingEvidenceCount
                      const risk = e?.risk ?? "—"
                      return (
                        <TableRow key={id ?? title}>
                          <TableCell className="max-w-[200px] font-medium">{title}</TableCell>
                          <TableCell>{jLabel}</TableCell>
                          <TableCell className="max-w-[220px] text-muted-foreground">{use}</TableCell>
                          <TableCell>
                            <Badge variant="outline" className="capitalize">
                              {status.replace(/_/g, " ")}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right tabular-nums">{reqC !== undefined ? reqC : "—"}</TableCell>
                          <TableCell className="text-right tabular-nums">{missC !== undefined ? missC : "—"}</TableCell>
                          <TableCell className="capitalize">{risk}</TableCell>
                          <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{updated}</TableCell>
                          <TableCell>
                            {id != null ? (
                              <Button variant="outline" size="sm" asChild>
                                <Link href={`/regulatory/dossiers/${encodeURIComponent(String(id))}`}>Open</Link>
                              </Button>
                            ) : (
                              "—"
                            )}
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      <section className="flex flex-wrap gap-3" aria-label="Shortcuts">
        <Button type="button" variant="secondary" asChild>
          <Link href="/regulatory/sources">Open source library</Link>
        </Button>
        <Button type="button" variant="secondary" asChild>
          <Link href="/regulatory/surveillance">Open surveillance dashboard</Link>
        </Button>
        <Button type="button" variant="secondary" asChild>
          <Link href="/regulatory/rule-updates">Open rule update proposals</Link>
        </Button>
        <Button type="button" variant="secondary" asChild>
          <Link href="/regulatory/action-queue">Open action queue</Link>
        </Button>
        <Button type="button" variant="secondary" onClick={scrollToReview}>
          Open regulatory review
        </Button>
      </section>

      <section id="regulatory-source-library" className="space-y-3 scroll-mt-8">
        <h2 className="text-lg font-semibold tracking-tight">Source library</h2>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">GET /regulatory/sources</CardTitle>
            <CardDescription>Catalog entries only — file contents are not shown here.</CardDescription>
          </CardHeader>
          <CardContent>
            {dossierListError && !sources.length ? (
              <p className="text-sm text-muted-foreground">Unavailable while the dossier service is unreachable.</p>
            ) : sourcesUnavailable && !sources.length ? (
              <p className="text-sm text-muted-foreground">Source list could not be loaded.</p>
            ) : sources.length === 0 ? (
              <p className="text-sm text-muted-foreground">No source documents registered.</p>
            ) : (
              <div className="table-scroll">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>title</TableHead>
                      <TableHead>source_type</TableHead>
                      <TableHead>status</TableHead>
                      <TableHead>version</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sources.map((s) => (
                      <TableRow key={s.id}>
                        <TableCell className="max-w-[280px] font-medium">{s.title}</TableCell>
                        <TableCell className="font-mono text-xs">{s.source_type}</TableCell>
                        <TableCell>{s.status}</TableCell>
                        <TableCell>{s.version ?? "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      <section id="regulatory-review-queue" className="space-y-3 scroll-mt-8">
        <h2 className="text-lg font-semibold tracking-tight">Regulatory review queue</h2>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Dossiers with status in_review</CardTitle>
            <CardDescription>Human review is required before relying on outputs for regulatory decisions.</CardDescription>
          </CardHeader>
          <CardContent>
            {dossierListError ? (
              <p className="text-sm text-muted-foreground">Unavailable while the dossier service is unreachable.</p>
            ) : reviewQueueRows.length === 0 ? (
              <p className="text-sm text-muted-foreground">No dossiers are currently in review.</p>
            ) : (
              <div className="table-scroll">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>title</TableHead>
                      <TableHead>jurisdiction</TableHead>
                      <TableHead>updated date</TableHead>
                      <TableHead className="w-[100px]">open button</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {reviewQueueRows.map((row) => {
                      const id = dossierNumericId(row)
                      const title = readRecordString(row, "title") ?? "—"
                      const jid = readRecordNumber(row, "jurisdiction_id")
                      const jLabel =
                        jid != null ? jurisdictionNameById.get(jid) ?? `jurisdiction_id ${jid}` : "—"
                      const updated = formatWhen(readRecordString(row, "updated_at"))
                      return (
                        <TableRow key={id ?? title}>
                          <TableCell className="font-medium">{title}</TableCell>
                          <TableCell>{jLabel}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">{updated}</TableCell>
                          <TableCell>
                            {id != null ? (
                              <Button variant="outline" size="sm" asChild>
                                <Link href={`/regulatory/dossiers/${encodeURIComponent(String(id))}`}>Open</Link>
                              </Button>
                            ) : (
                              "—"
                            )}
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      <Card className="border-dashed bg-muted/30">
        <CardContent className="py-4 text-xs text-muted-foreground">
          Outputs are workflow aids only. Cited sources and qualified review are required before any regulatory submission
          use.
        </CardContent>
      </Card>
    </div>
  )
}
