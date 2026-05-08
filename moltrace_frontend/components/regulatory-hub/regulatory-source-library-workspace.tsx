"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatStableUtcDateTime } from "@/lib/utils"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
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
import { AlertTriangle, ArrowLeft, Loader2 } from "lucide-react"

const SOURCE_TYPES = [
  "guidance",
  "regulation",
  "internal_sop",
  "company_policy",
  "scientific_report",
  "analytical_report",
  "other",
] as const

type JurisdictionRow = { id: number; name: string }

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

function parseJurisdictions(raw: unknown): JurisdictionRow[] {
  const rows = asArray(raw).filter(isRecord)
  const out: JurisdictionRow[] = []
  for (const row of rows) {
    const id = readRecordNumber(row, "id")
    const name = readRecordString(row, "name")
    if (id != null && name) out.push({ id, name })
  }
  return out
}

function formatWhen(iso: string | undefined): string {
  return formatStableUtcDateTime(iso)
}

function parseCitationRow(raw: unknown): Record<string, unknown> | null {
  return isRecord(raw) ? raw : null
}

export function RegulatorySourceLibraryWorkspace() {
  const [jurisdictions, setJurisdictions] = useState<JurisdictionRow[]>([])
  const [sources, setSources] = useState<Record<string, unknown>[]>([])
  const [sourcesErr, setSourcesErr] = useState("")
  const [sourcesLoading, setSourcesLoading] = useState(true)

  const [uploadTitle, setUploadTitle] = useState("")
  const [uploadSourceType, setUploadSourceType] = useState<string>("other")
  const [uploadJurisdictionId, setUploadJurisdictionId] = useState<string>("")
  const [uploadSourceUrl, setUploadSourceUrl] = useState("")
  const [uploadSourceDate, setUploadSourceDate] = useState("")
  const [uploadVersion, setUploadVersion] = useState("")
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [uploadErr, setUploadErr] = useState("")
  const [uploadOk, setUploadOk] = useState("")
  const [connectorImportConnector, setConnectorImportConnector] = useState("")
  const [connectorImportExternalRecord, setConnectorImportExternalRecord] = useState("")
  const [connectorImportSourceType, setConnectorImportSourceType] = useState<string>("guidance")
  const [connectorImportJurisdiction, setConnectorImportJurisdiction] = useState("")
  const [connectorImportDossier, setConnectorImportDossier] = useState("")
  const [connectorImportFileId, setConnectorImportFileId] = useState("")
  const [connectorImportExternalObjectId, setConnectorImportExternalObjectId] = useState("")
  const [connectorImportBusy, setConnectorImportBusy] = useState(false)
  const [connectorImportErr, setConnectorImportErr] = useState("")
  const [connectorImportResult, setConnectorImportResult] = useState<Record<string, unknown> | null>(null)

  const [searchQuery, setSearchQuery] = useState("")
  const [searchJurisdictionId, setSearchJurisdictionId] = useState<string>("")
  const [searchSourceType, setSearchSourceType] = useState<string>("")
  const [searchBusy, setSearchBusy] = useState(false)
  const [searchErr, setSearchErr] = useState("")
  const [searchResult, setSearchResult] = useState<Record<string, unknown> | null>(null)

  const [selectedSourceId, setSelectedSourceId] = useState<number | null>(null)
  const [citations, setCitations] = useState<Record<string, unknown>[]>([])
  const [citationsLoading, setCitationsLoading] = useState(false)
  const [citationsErr, setCitationsErr] = useState("")

  const jurisdictionNameById = useMemo(() => {
    const m = new Map<number, string>()
    for (const j of jurisdictions) m.set(j.id, j.name)
    return m
  }, [jurisdictions])

  const loadJurisdictions = useCallback(async () => {
    try {
      const raw = await apiFetch<unknown>("/regulatory/jurisdictions", { method: "GET" })
      setJurisdictions(parseJurisdictions(raw))
    } catch {
      setJurisdictions([])
    }
  }, [])

  const loadSources = useCallback(async () => {
    setSourcesLoading(true)
    setSourcesErr("")
    try {
      const raw = await apiFetch<unknown>("/regulatory/sources", { method: "GET" })
      setSources(asArray(raw).filter(isRecord) as Record<string, unknown>[])
    } catch (e) {
      setSources([])
      setSourcesErr(formatApiError(e, "Could not load sources."))
    } finally {
      setSourcesLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadJurisdictions()
    void loadSources()
  }, [loadJurisdictions, loadSources])

  useEffect(() => {
    if (selectedSourceId == null) {
      setCitations([])
      return
    }
    let cancelled = false
    setCitationsLoading(true)
    setCitationsErr("")
    setCitations([])
    void (async () => {
      try {
        const raw = await apiFetch<unknown>(`/regulatory/sources/${selectedSourceId}/citations`, {
          method: "GET",
        })
        if (cancelled) return
        const rows = asArray(raw).map(parseCitationRow).filter(Boolean) as Record<string, unknown>[]
        setCitations(rows)
      } catch (e) {
        if (!cancelled) setCitationsErr(formatApiError(e, "Could not load citations."))
      } finally {
        if (!cancelled) setCitationsLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selectedSourceId])

  async function submitUpload() {
    setUploadErr("")
    setUploadOk("")
    const title = uploadTitle.trim()
    if (!title) {
      setUploadErr("title is required.")
      return
    }
    if (!uploadFile || uploadFile.size === 0) {
      setUploadErr("The upload API requires a non-empty file.")
      return
    }
    setUploadBusy(true)
    try {
      const fd = new FormData()
      fd.append("title", title)
      fd.append("source_type", uploadSourceType)
      fd.append("status", "active")
      const jid = uploadJurisdictionId.trim()
      if (jid) fd.append("jurisdiction_id", jid)
      const url = uploadSourceUrl.trim()
      if (url) fd.append("source_url", url)
      const sd = uploadSourceDate.trim()
      if (sd) fd.append("source_date", sd)
      const ver = uploadVersion.trim()
      if (ver) fd.append("version", ver)
      fd.append("file", uploadFile, uploadFile.name)

      await apiFetch<unknown>("/regulatory/sources/upload", {
        method: "POST",
        body: fd,
      })
      setUploadOk("Source registered.")
      setUploadTitle("")
      setUploadSourceUrl("")
      setUploadSourceDate("")
      setUploadVersion("")
      setUploadFile(null)
      setUploadJurisdictionId("")
      await loadSources()
    } catch (e) {
      setUploadErr(formatApiError(e, "Upload failed."))
    } finally {
      setUploadBusy(false)
    }
  }

  async function submitSearch() {
    const q = searchQuery.trim()
    if (!q) {
      setSearchErr("Search query is required.")
      return
    }
    setSearchBusy(true)
    setSearchErr("")
    try {
      const body: Record<string, unknown> = { query: q, limit: 25 }
      const sj = searchJurisdictionId.trim()
      if (sj) {
        const n = Number.parseInt(sj, 10)
        if (Number.isFinite(n)) body.jurisdiction_id = n
      }
      const st = searchSourceType.trim()
      if (st) body.source_type = st
      const res = await apiFetch<Record<string, unknown>>("/regulatory/sources/search", {
        method: "POST",
        body,
      })
      setSearchResult(res)
    } catch (e) {
      setSearchErr(formatApiError(e, "Search failed."))
      setSearchResult(null)
    } finally {
      setSearchBusy(false)
    }
  }

  const selectedSourceTitle = useMemo(() => {
    if (selectedSourceId == null) return ""
    const row = sources.find((s) => readRecordNumber(s, "id") === selectedSourceId)
    return readRecordString(row ?? null, "title") ?? `source_id ${selectedSourceId}`
  }, [selectedSourceId, sources])

  function renderCitationCard(c: Record<string, unknown>, key: string | number) {
    const label = readRecordString(c, "citation_label") ?? "—"
    const section = readRecordString(c, "section_title")
    const page = readRecordNumber(c, "page_number")
    const para = readRecordNumber(c, "paragraph_number")
    const quote = readRecordString(c, "quote_excerpt")
    const summary = readRecordString(c, "summary")
    return (
      <Card key={key} className="border-muted">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">{label}</CardTitle>
          {section ? <CardDescription>{section}</CardDescription> : null}
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p className="text-xs text-muted-foreground">
            page_number / paragraph_number:{" "}
            <span className="font-mono text-foreground">
              {page != null ? page : "—"} / {para != null ? para : "—"}
            </span>
          </p>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">quote excerpt</p>
            <blockquote className="mt-1 rounded-md border border-dashed bg-muted/40 px-3 py-2 text-sm leading-relaxed">
              {quote?.trim() ? quote : "—"}
            </blockquote>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">summary</p>
            <p className="mt-1 text-muted-foreground">{summary?.trim() ? summary : "—"}</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  const searchSources = searchResult ? (asArray(searchResult.sources).filter(isRecord) as Record<string, unknown>[]) : []
  const searchCitations = searchResult
    ? (asArray(searchResult.citations).filter(isRecord) as Record<string, unknown>[])
    : []

  function readConnectorImportString(keys: string[]): string {
    if (!connectorImportResult) return ""
    for (const key of keys) {
      const value = connectorImportResult[key]
      if (typeof value === "string" && value.trim()) return value.trim()
      if (typeof value === "number" && Number.isFinite(value)) return String(value)
    }
    return ""
  }

  function readConnectorImportWarnings(): string[] {
    if (!connectorImportResult) return []
    const warnings = connectorImportResult.warnings
    if (Array.isArray(warnings)) {
      return warnings
        .map((item) => (typeof item === "string" ? item.trim() : ""))
        .filter((item) => item.length > 0)
    }
    if (typeof warnings === "string" && warnings.trim()) return [warnings.trim()]
    return []
  }

  async function submitConnectorImport() {
    setConnectorImportBusy(true)
    setConnectorImportErr("")
    try {
      const body: Record<string, unknown> = {
        connector: connectorImportConnector.trim(),
        external_record: connectorImportExternalRecord.trim(),
        source_type: connectorImportSourceType,
        jurisdiction: connectorImportJurisdiction.trim(),
      }
      const dossier = connectorImportDossier.trim()
      if (dossier) body.dossier = dossier
      const fileId = connectorImportFileId.trim()
      if (fileId) body.file_id = fileId
      const externalObjectId = connectorImportExternalObjectId.trim()
      if (externalObjectId) body.external_object_id = externalObjectId
      const data = await apiFetch<unknown>("/integrations/regulatory/import-source", {
        method: "POST",
        body,
      })
      if (isRecord(data)) {
        setConnectorImportResult(data)
      } else {
        setConnectorImportResult({ result: data })
      }
      await loadSources()
    } catch (e) {
      setConnectorImportErr(formatApiError(e, "Import source from connector failed."))
      setConnectorImportResult(null)
    } finally {
      setConnectorImportBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-[1200px] space-y-8 pb-12">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/regulatory">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Regulatory Intelligence
          </Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/regulatory/surveillance">Surveillance dashboard</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/regulatory/rule-updates">Rule update proposals</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/regulatory/action-queue">Action queue</Link>
        </Button>
      </div>

      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Regulatory Source Library</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Register documents, list catalog entries, search indexed sources, and inspect citations returned by the
          service only.
        </p>
      </header>

      <Alert>
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>Important</AlertTitle>
        <AlertDescription className="text-sm">
          Citations and excerpts are shown exactly as returned by the backend. Do not treat search or excerpt text as
          final regulatory authority without controlled sources and qualified review.
        </AlertDescription>
      </Alert>

      {/* 1. Upload */}
      <section aria-labelledby="upload-heading">
        <Card>
          <CardHeader>
            <CardTitle id="upload-heading" className="text-lg">
              Upload / source registration
            </CardTitle>
            <CardDescription>POST /regulatory/sources/upload (multipart form)</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-xs text-muted-foreground">
              The server rejects empty files. Choose a non-empty file, or skip registration until a file is available.
            </p>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="src-title">title</Label>
                <Input
                  id="src-title"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label>source type</Label>
                <Select value={uploadSourceType} onValueChange={setUploadSourceType}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SOURCE_TYPES.map((t) => (
                      <SelectItem key={t} value={t}>
                        {t}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>jurisdiction selector optional</Label>
                <Select value={uploadJurisdictionId || "none"} onValueChange={(v) => setUploadJurisdictionId(v === "none" ? "" : v)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Not specified" />
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
                <Label htmlFor="src-url">source URL optional</Label>
                <Input
                  id="src-url"
                  value={uploadSourceUrl}
                  onChange={(e) => setUploadSourceUrl(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="src-date">source date optional</Label>
                <Input
                  id="src-date"
                  type="date"
                  value={uploadSourceDate}
                  onChange={(e) => setUploadSourceDate(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="src-version">version optional</Label>
                <Input
                  id="src-version"
                  value={uploadVersion}
                  onChange={(e) => setUploadVersion(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="src-file">file upload optional</Label>
                <Input
                  id="src-file"
                  type="file"
                  onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
                  className="cursor-pointer text-sm"
                />
              </div>
            </div>
            {uploadErr ? (
              <Alert variant="destructive">
                <AlertDescription className="text-sm">{uploadErr}</AlertDescription>
              </Alert>
            ) : null}
            {uploadOk ? (
              <Alert>
                <AlertDescription className="text-sm">{uploadOk}</AlertDescription>
              </Alert>
            ) : null}
            <Button type="button" disabled={uploadBusy} onClick={() => void submitUpload()}>
              {uploadBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Register source
            </Button>
          </CardContent>
        </Card>
      </section>

      <section aria-labelledby="connector-import-heading">
        <Card>
          <CardHeader>
            <CardTitle id="connector-import-heading" className="text-lg">
              Import source from connector
            </CardTitle>
            <CardDescription>POST /integrations/regulatory/import-source</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="connector-import-connector">connector</Label>
                <Input
                  id="connector-import-connector"
                  value={connectorImportConnector}
                  onChange={(e) => setConnectorImportConnector(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="connector-import-external-record">external record</Label>
                <Input
                  id="connector-import-external-record"
                  value={connectorImportExternalRecord}
                  onChange={(e) => setConnectorImportExternalRecord(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label>source type</Label>
                <Select value={connectorImportSourceType} onValueChange={setConnectorImportSourceType}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SOURCE_TYPES.map((t) => (
                      <SelectItem key={t} value={t}>
                        {t}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="connector-import-jurisdiction">jurisdiction</Label>
                <Input
                  id="connector-import-jurisdiction"
                  value={connectorImportJurisdiction}
                  onChange={(e) => setConnectorImportJurisdiction(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="connector-import-dossier">dossier optional</Label>
                <Input
                  id="connector-import-dossier"
                  value={connectorImportDossier}
                  onChange={(e) => setConnectorImportDossier(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="connector-import-file-id">file ID</Label>
                <Input
                  id="connector-import-file-id"
                  value={connectorImportFileId}
                  onChange={(e) => setConnectorImportFileId(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="connector-import-external-object-id">external object ID</Label>
                <Input
                  id="connector-import-external-object-id"
                  value={connectorImportExternalObjectId}
                  onChange={(e) => setConnectorImportExternalObjectId(e.target.value)}
                  autoComplete="off"
                />
              </div>
            </div>
            {connectorImportErr ? (
              <Alert variant="destructive">
                <AlertDescription className="text-sm">{connectorImportErr}</AlertDescription>
              </Alert>
            ) : null}
            <Button type="button" disabled={connectorImportBusy} onClick={() => void submitConnectorImport()}>
              {connectorImportBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Import regulatory source
            </Button>
            {connectorImportResult ? (
              <Card className="border-muted">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Imported source</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-2 text-sm sm:grid-cols-2">
                  <p className="sm:col-span-2">
                    <span className="text-muted-foreground">imported source title:</span>{" "}
                    {readConnectorImportString(["imported_source_title", "title", "source_title"]) || "—"}
                  </p>
                  <p className="sm:col-span-2">
                    <span className="text-muted-foreground">SHA-256:</span>{" "}
                    {readConnectorImportString(["sha256", "file_sha256"]) || "—"}
                  </p>
                  <p>
                    <span className="text-muted-foreground">source type:</span>{" "}
                    {readConnectorImportString(["source_type"]) || "—"}
                  </p>
                  <p>
                    <span className="text-muted-foreground">citation extraction status:</span>{" "}
                    {readConnectorImportString(["citation_extraction_status", "citation_status"]) || "—"}
                  </p>
                  <p className="sm:col-span-2">
                    <span className="text-muted-foreground">warnings:</span>{" "}
                    {readConnectorImportWarnings().join("; ") || "—"}
                  </p>
                  <details className="sm:col-span-2 rounded-md border p-2">
                    <summary className="cursor-pointer text-xs font-medium">Developer JSON</summary>
                    <pre className="mt-2 overflow-x-auto text-[10px]">{JSON.stringify(connectorImportResult, null, 2)}</pre>
                  </details>
                </CardContent>
              </Card>
            ) : null}
          </CardContent>
        </Card>
      </section>

      {/* 2. Table */}
      <section aria-labelledby="sources-table-heading" className="space-y-3">
        <div>
          <h2 id="sources-table-heading" className="text-lg font-semibold tracking-tight">
            Source documents
          </h2>
          <p className="text-sm text-muted-foreground">GET /regulatory/sources</p>
        </div>
        <Card>
          <CardContent className="pt-6">
            {sourcesLoading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : sourcesErr ? (
              <Alert variant="destructive">
                <AlertDescription className="text-sm">{sourcesErr}</AlertDescription>
              </Alert>
            ) : sources.length === 0 ? (
              <p className="text-sm text-muted-foreground">No sources registered.</p>
            ) : (
              <div className="table-scroll">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>title</TableHead>
                      <TableHead>source type</TableHead>
                      <TableHead>jurisdiction</TableHead>
                      <TableHead>version</TableHead>
                      <TableHead>source date</TableHead>
                      <TableHead>SHA-256</TableHead>
                      <TableHead>status</TableHead>
                      <TableHead className="w-[90px]">open button</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sources.map((row) => {
                      const id = readRecordNumber(row, "id")
                      const title = readRecordString(row, "title") ?? "—"
                      const st = readRecordString(row, "source_type") ?? "—"
                      const jid = readRecordNumber(row, "jurisdiction_id")
                      const jLabel = jid != null ? jurisdictionNameById.get(jid) ?? `id ${jid}` : "—"
                      const version = readRecordString(row, "version") ?? "—"
                      const srcDateRaw = readRecordString(row, "source_date")
                      const srcDate = srcDateRaw ? formatWhen(srcDateRaw) : "—"
                      const sha = readRecordString(row, "sha256")
                      const status = readRecordString(row, "status") ?? "—"
                      return (
                        <TableRow key={id ?? title}>
                          <TableCell className="max-w-[220px] font-medium">{title}</TableCell>
                          <TableCell className="text-xs">{st}</TableCell>
                          <TableCell className="text-xs">{jLabel}</TableCell>
                          <TableCell className="text-xs">{version}</TableCell>
                          <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{srcDate}</TableCell>
                          <TableCell className="max-w-[140px] truncate font-mono text-[10px]" title={sha ?? ""}>
                            {sha ?? "—"}
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className="text-xs">
                              {status}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            {id != null ? (
                              <div className="flex flex-wrap gap-1">
                                <Button
                                  type="button"
                                  variant={selectedSourceId === id ? "default" : "outline"}
                                  size="sm"
                                  onClick={() => setSelectedSourceId(id)}
                                >
                                  Open
                                </Button>
                                <Button type="button" variant="outline" size="sm" asChild>
                                  <Link href={`/regulatory/sources/${id}`}>Timeline</Link>
                                </Button>
                              </div>
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

      {/* 3. Search */}
      <section aria-labelledby="search-heading">
        <Card>
          <CardHeader>
            <CardTitle id="search-heading" className="text-lg">
              Source search
            </CardTitle>
            <CardDescription>POST /regulatory/sources/search</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="src-search-q">query</Label>
              <Textarea id="src-search-q" rows={3} value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} />
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>jurisdiction_id optional</Label>
                <Select value={searchJurisdictionId || "none"} onValueChange={(v) => setSearchJurisdictionId(v === "none" ? "" : v)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Any" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Any</SelectItem>
                    {jurisdictions.map((j) => (
                      <SelectItem key={j.id} value={String(j.id)}>
                        {j.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>source_type optional</Label>
                <Select value={searchSourceType || "none"} onValueChange={(v) => setSearchSourceType(v === "none" ? "" : v)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Any" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Any</SelectItem>
                    {SOURCE_TYPES.map((t) => (
                      <SelectItem key={t} value={t}>
                        {t}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {searchErr ? (
              <Alert variant="destructive">
                <AlertDescription className="text-sm">{searchErr}</AlertDescription>
              </Alert>
            ) : null}
            <Button type="button" disabled={searchBusy} onClick={() => void submitSearch()}>
              {searchBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Search
            </Button>

            {searchResult ? (
              <div className="space-y-4 border-t pt-4">
                <p className="text-xs font-medium uppercase text-muted-foreground">Search response</p>
                {Array.isArray(searchResult.warnings) && searchResult.warnings.length > 0 ? (
                  <ul className="list-inside list-disc text-xs text-muted-foreground">
                    {(searchResult.warnings as unknown[]).filter((w) => typeof w === "string").map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                ) : null}
                <div>
                  <p className="mb-2 text-sm font-medium">sources</p>
                  {searchSources.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No sources in this result.</p>
                  ) : (
                    <ul className="space-y-1 text-sm">
                      {searchSources.map((s) => (
                        <li key={readRecordNumber(s, "id") ?? readRecordString(s, "title")}>
                          <button
                            type="button"
                            className="text-left font-medium text-primary underline-offset-4 hover:underline"
                            onClick={() => {
                              const sid = readRecordNumber(s, "id")
                              if (sid != null) setSelectedSourceId(sid)
                            }}
                          >
                            {readRecordString(s, "title") ?? "—"}{" "}
                            <span className="font-mono text-xs text-muted-foreground">
                              (id {readRecordNumber(s, "id") ?? "—"})
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div>
                  <p className="mb-2 text-sm font-medium">citations</p>
                  {searchCitations.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No citations in this result.</p>
                  ) : (
                    <div className="grid gap-3 md:grid-cols-2">
                      {searchCitations.map((c, i) => renderCitationCard(c, `search-${i}`))}
                    </div>
                  )}
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </section>

      {/* 4. Citation viewer */}
      <section aria-labelledby="citations-heading">
        <Card>
          <CardHeader>
            <CardTitle id="citations-heading" className="text-lg">
              Citation viewer
            </CardTitle>
            <CardDescription>GET /regulatory/sources/{"{source_id}"}/citations</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {selectedSourceId == null ? (
              <p className="text-sm text-muted-foreground">Select a source with Open to load citations.</p>
            ) : (
              <>
                <p className="text-sm font-medium">
                  Selected: <span className="text-muted-foreground">{selectedSourceTitle}</span>{" "}
                  <span className="font-mono text-xs">source_id {selectedSourceId}</span>
                </p>
                {citationsErr ? (
                  <Alert variant="destructive">
                    <AlertDescription className="text-sm">{citationsErr}</AlertDescription>
                  </Alert>
                ) : citationsLoading ? (
                  <p className="text-sm text-muted-foreground">Loading citations…</p>
                ) : citations.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No citations extracted yet.</p>
                ) : (
                  <div className="grid gap-3 md:grid-cols-2">
                    {citations.map((c, i) => renderCitationCard(c, `cit-${selectedSourceId}-${i}`))}
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  )
}
