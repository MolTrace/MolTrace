"use client"

import Link from "next/link"
import { useCallback, useEffect, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  KNOWLEDGE_RELIABILITY_LABELS,
  KNOWLEDGE_SOURCE_STATUS,
  KNOWLEDGE_SOURCE_TYPES,
} from "@/components/knowledge/knowledge-constants"
import { AlertTriangle, ArrowLeft, Loader2 } from "lucide-react"

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

function readStringList(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.filter((x): x is string => typeof x === "string" && x.trim().length > 0)
}

function formatWhen(iso: string | undefined): string {
  if (!iso?.trim()) return "—"
  const d = Date.parse(iso)
  if (Number.isNaN(d)) return iso
  return new Date(d).toLocaleString()
}

function formatPublicationDateForApi(dateInput: string): string | null {
  const t = dateInput.trim()
  if (!t) return null
  if (/^\d{4}-\d{2}-\d{2}$/.test(t)) return `${t}T12:00:00`
  return t
}

export function KnowledgeSourceLibraryWorkspace() {
  const [sources, setSources] = useState<Record<string, unknown>[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [listErr, setListErr] = useState("")

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailErr, setDetailErr] = useState("")

  const [files, setFiles] = useState<Record<string, unknown>[]>([])
  const [filesLoading, setFilesLoading] = useState(false)
  const [filesErr, setFilesErr] = useState("")

  const [createTitle, setCreateTitle] = useState("")
  const [createSourceType, setCreateSourceType] = useState<string>("other")
  const [createDoi, setCreateDoi] = useState("")
  const [createPatent, setCreatePatent] = useState("")
  const [createUrl, setCreateUrl] = useState("")
  const [createPublisher, setCreatePublisher] = useState("")
  const [createPubDate, setCreatePubDate] = useState("")
  const [createReliability, setCreateReliability] = useState<string>("unknown")
  const [createStatus, setCreateStatus] = useState<string>("draft")
  const [createBusy, setCreateBusy] = useState(false)
  const [createErr, setCreateErr] = useState("")
  const [createOk, setCreateOk] = useState("")

  const [patchTitle, setPatchTitle] = useState("")
  const [patchSourceType, setPatchSourceType] = useState<string>("other")
  const [patchDoi, setPatchDoi] = useState("")
  const [patchPatent, setPatchPatent] = useState("")
  const [patchUrl, setPatchUrl] = useState("")
  const [patchPublisher, setPatchPublisher] = useState("")
  const [patchPubDate, setPatchPubDate] = useState("")
  const [patchReliability, setPatchReliability] = useState<string>("unknown")
  const [patchStatus, setPatchStatus] = useState<string>("draft")
  const [patchBusy, setPatchBusy] = useState(false)
  const [patchErr, setPatchErr] = useState("")
  const [patchOk, setPatchOk] = useState("")

  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadBusy, setUploadBusy] = useState(false)
  const [uploadErr, setUploadErr] = useState("")
  const [uploadOk, setUploadOk] = useState("")

  const loadSources = useCallback(async () => {
    setListLoading(true)
    setListErr("")
    try {
      const raw = await apiFetch<unknown>("/knowledge/sources?limit=500", { method: "GET" })
      setSources(asArray(raw).filter(isRecord) as Record<string, unknown>[])
    } catch (e) {
      setSources([])
      setListErr(formatApiError(e, "Could not load knowledge sources."))
    } finally {
      setListLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadSources()
  }, [loadSources])

  useEffect(() => {
    if (selectedId == null) {
      setDetail(null)
      setFiles([])
      setDetailErr("")
      setFilesErr("")
      return
    }
    let cancelled = false
    setDetailLoading(true)
    setFilesLoading(true)
    setDetailErr("")
    setFilesErr("")
    setDetail(null)
    setFiles([])
    void (async () => {
      try {
        const d = await apiFetch<unknown>(`/knowledge/sources/${selectedId}`, { method: "GET" })
        if (cancelled) return
        setDetail(isRecord(d) ? d : null)
      } catch (e) {
        if (!cancelled) setDetailErr(formatApiError(e, "Could not load source detail."))
      } finally {
        if (!cancelled) setDetailLoading(false)
      }
    })()
    void (async () => {
      try {
        const f = await apiFetch<unknown>(`/knowledge/sources/${selectedId}/files`, { method: "GET" })
        if (cancelled) return
        setFiles(asArray(f).filter(isRecord) as Record<string, unknown>[])
      } catch (e) {
        if (!cancelled) setFilesErr(formatApiError(e, "Could not load source files."))
      } finally {
        if (!cancelled) setFilesLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selectedId])

  useEffect(() => {
    if (!detail) return
    setPatchTitle(readRecordString(detail, "title") ?? "")
    setPatchSourceType(readRecordString(detail, "source_type") ?? "other")
    setPatchDoi(readRecordString(detail, "doi") ?? "")
    setPatchPatent(readRecordString(detail, "patent_number") ?? "")
    setPatchUrl(readRecordString(detail, "source_url") ?? "")
    setPatchPublisher(readRecordString(detail, "publisher") ?? "")
    const pd = detail.publication_date
    if (typeof pd === "string" && pd.trim()) {
      const slice = pd.slice(0, 10)
      setPatchPubDate(/^\d{4}-\d{2}-\d{2}$/.test(slice) ? slice : "")
    } else {
      setPatchPubDate("")
    }
    setPatchReliability(readRecordString(detail, "reliability_label") ?? "unknown")
    setPatchStatus(readRecordString(detail, "status") ?? "draft")
  }, [detail])

  async function submitCreate() {
    setCreateErr("")
    setCreateOk("")
    const title = createTitle.trim()
    if (!title) {
      setCreateErr("title is required.")
      return
    }
    setCreateBusy(true)
    try {
      const body: Record<string, unknown> = {
        title,
        source_type: createSourceType,
        status: createStatus,
        reliability_label: createReliability,
        metadata_json: {},
      }
      const doi = createDoi.trim()
      if (doi) body.doi = doi
      const patent = createPatent.trim()
      if (patent) body.patent_number = patent
      const url = createUrl.trim()
      if (url) body.source_url = url
      const pub = createPublisher.trim()
      if (pub) body.publisher = pub
      const pdate = formatPublicationDateForApi(createPubDate)
      if (pdate) body.publication_date = pdate

      await apiFetch("/knowledge/sources", { method: "POST", body })
      setCreateOk("Source created.")
      setCreateTitle("")
      setCreateDoi("")
      setCreatePatent("")
      setCreateUrl("")
      setCreatePublisher("")
      setCreatePubDate("")
      setCreateSourceType("other")
      setCreateReliability("unknown")
      setCreateStatus("draft")
      await loadSources()
    } catch (e) {
      setCreateErr(formatApiError(e, "Create source failed."))
    } finally {
      setCreateBusy(false)
    }
  }

  async function submitPatch() {
    if (selectedId == null) return
    setPatchErr("")
    setPatchOk("")
    if (!patchTitle.trim()) {
      setPatchErr("title is required.")
      return
    }
    setPatchBusy(true)
    try {
      const body: Record<string, unknown> = {
        title: patchTitle.trim(),
        source_type: patchSourceType,
        doi: patchDoi.trim() || null,
        patent_number: patchPatent.trim() || null,
        source_url: patchUrl.trim() || null,
        publisher: patchPublisher.trim() || null,
        publication_date: formatPublicationDateForApi(patchPubDate),
        status: patchStatus,
        reliability_label: patchReliability,
        metadata_json: {},
      }
      const updated = await apiFetch<unknown>(`/knowledge/sources/${selectedId}`, { method: "PATCH", body })
      setDetail(isRecord(updated) ? updated : null)
      setPatchOk("Source updated.")
      await loadSources()
    } catch (e) {
      setPatchErr(formatApiError(e, "Update source failed."))
    } finally {
      setPatchBusy(false)
    }
  }

  async function submitUpload() {
    if (selectedId == null) return
    setUploadErr("")
    setUploadOk("")
    if (!uploadFile || uploadFile.size === 0) {
      setUploadErr("file is required.")
      return
    }
    setUploadBusy(true)
    try {
      const fd = new FormData()
      fd.append("file", uploadFile, uploadFile.name)
      fd.append("metadata_json", "{}")
      await apiFetch<unknown>(`/knowledge/sources/${selectedId}/files`, { method: "POST", body: fd })
      setUploadOk("File uploaded.")
      setUploadFile(null)
      const f = await apiFetch<unknown>(`/knowledge/sources/${selectedId}/files`, { method: "GET" })
      setFiles(asArray(f).filter(isRecord) as Record<string, unknown>[])
    } catch (e) {
      setUploadErr(formatApiError(e, "Upload failed."))
    } finally {
      setUploadBusy(false)
    }
  }

  const sourceWarnings = detail ? readStringList(detail.warnings) : []

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/knowledge">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Knowledge Library
          </Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/knowledge/extractions">Extractions</Link>
        </Button>
      </div>

      <div>
        <h1 className="font-mono text-2xl font-bold tracking-tight">Knowledge sources</h1>
        <p className="text-sm text-muted-foreground">
          Register bibliographic metadata and upload files for extraction. Operational signals from your tenant API —
          not legal or publication advice.
        </p>
      </div>

      <Alert>
        <AlertTriangle className="h-4 w-4" aria-hidden />
        <AlertTitle className="text-sm">Human review</AlertTitle>
        <AlertDescription className="text-sm text-muted-foreground">
          Parsed content and hashes support traceability; reviewers must confirm citations and provenance before reuse.
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-lg">Create source</CardTitle>
          <CardDescription>
            Register a new knowledge source — scientific literature, structured databases, or curated reference documents — for extraction and review.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {createErr ? (
            <Alert variant="destructive">
              <AlertDescription className="text-sm">{createErr}</AlertDescription>
            </Alert>
          ) : null}
          {createOk ? (
            <Alert>
              <AlertDescription className="text-sm">{createOk}</AlertDescription>
            </Alert>
          ) : null}
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="ks-title">title</Label>
              <Input
                id="ks-title"
                value={createTitle}
                onChange={(e) => setCreateTitle(e.target.value)}
                autoComplete="off"
              />
            </div>
            <div className="space-y-2">
              <Label>source_type</Label>
              <Select value={createSourceType} onValueChange={setCreateSourceType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {KNOWLEDGE_SOURCE_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="ks-doi">doi</Label>
              <Input id="ks-doi" value={createDoi} onChange={(e) => setCreateDoi(e.target.value)} autoComplete="off" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ks-patent">patent_number</Label>
              <Input
                id="ks-patent"
                value={createPatent}
                onChange={(e) => setCreatePatent(e.target.value)}
                autoComplete="off"
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="ks-url">source_url</Label>
              <Input id="ks-url" value={createUrl} onChange={(e) => setCreateUrl(e.target.value)} autoComplete="off" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ks-publisher">publisher</Label>
              <Input
                id="ks-publisher"
                value={createPublisher}
                onChange={(e) => setCreatePublisher(e.target.value)}
                autoComplete="off"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ks-pubdate">publication_date</Label>
              <Input
                id="ks-pubdate"
                type="date"
                value={createPubDate}
                onChange={(e) => setCreatePubDate(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>reliability_label</Label>
              <Select value={createReliability} onValueChange={setCreateReliability}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {KNOWLEDGE_RELIABILITY_LABELS.map((r) => (
                    <SelectItem key={r} value={r}>
                      {r}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>status</Label>
              <Select value={createStatus} onValueChange={setCreateStatus}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {KNOWLEDGE_SOURCE_STATUS.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <Button type="button" disabled={createBusy} onClick={() => void submitCreate()}>
            {createBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Create source
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-lg">Source table</CardTitle>
          <CardDescription>
            All knowledge sources — filterable by type, status, and reliability label.
          </CardDescription>
        </CardHeader>
        <CardContent className="table-scroll min-w-0">
          {listLoading ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              Loading…
            </p>
          ) : listErr ? (
            <p className="text-sm text-muted-foreground">{listErr}</p>
          ) : sources.length === 0 ? (
            <p className="text-sm text-muted-foreground">No sources returned.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[80px]">id</TableHead>
                  <TableHead>title</TableHead>
                  <TableHead>source_type</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead>reliability_label</TableHead>
                  <TableHead className="w-[120px]">select</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sources.map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  return (
                    <TableRow key={id != null ? `s-${id}` : `s-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell className="max-w-[240px] truncate text-sm font-medium">
                        {readRecordString(row, "title") ?? "—"}
                      </TableCell>
                      <TableCell className="font-mono text-xs">{readRecordString(row, "source_type") ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
                      </TableCell>
                      <TableCell className="text-xs">{readRecordString(row, "reliability_label") ?? "—"}</TableCell>
                      <TableCell>
                        {id != null ? (
                          <Button
                            type="button"
                            variant={selectedId === id ? "secondary" : "outline"}
                            size="sm"
                            className="h-8"
                            onClick={() => setSelectedId(id)}
                          >
                            Open
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
          )}
        </CardContent>
      </Card>

      {selectedId != null ? (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">Selected source</CardTitle>
            <CardDescription>
              Detail and edit panel for the selected knowledge source — update status, reliability label, and source metadata.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {detailLoading ? (
              <p className="text-sm text-muted-foreground">Loading detail…</p>
            ) : detailErr ? (
              <p className="text-sm text-destructive">{detailErr}</p>
            ) : detail ? (
              <>
                {sourceWarnings.length > 0 ? (
                  <Alert variant="destructive">
                    <AlertTitle className="text-sm">warnings</AlertTitle>
                    <AlertDescription>
                      <ul className="list-inside list-disc text-sm">
                        {sourceWarnings.map((w, i) => (
                          <li key={`${i}-${w.slice(0, 80)}`}>{w}</li>
                        ))}
                      </ul>
                    </AlertDescription>
                  </Alert>
                ) : null}

                {patchErr ? (
                  <Alert variant="destructive">
                    <AlertDescription className="text-sm">{patchErr}</AlertDescription>
                  </Alert>
                ) : null}
                {patchOk ? (
                  <Alert>
                    <AlertDescription className="text-sm">{patchOk}</AlertDescription>
                  </Alert>
                ) : null}

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="kp-title">title</Label>
                    <Input id="kp-title" value={patchTitle} onChange={(e) => setPatchTitle(e.target.value)} />
                  </div>
                  <div className="space-y-2">
                    <Label>source_type</Label>
                    <Select value={patchSourceType} onValueChange={setPatchSourceType}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {KNOWLEDGE_SOURCE_TYPES.map((t) => (
                          <SelectItem key={t} value={t}>
                            {t}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="kp-doi">doi</Label>
                    <Input id="kp-doi" value={patchDoi} onChange={(e) => setPatchDoi(e.target.value)} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="kp-patent">patent_number</Label>
                    <Input id="kp-patent" value={patchPatent} onChange={(e) => setPatchPatent(e.target.value)} />
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="kp-url">source_url</Label>
                    <Input id="kp-url" value={patchUrl} onChange={(e) => setPatchUrl(e.target.value)} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="kp-publisher">publisher</Label>
                    <Input id="kp-publisher" value={patchPublisher} onChange={(e) => setPatchPublisher(e.target.value)} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="kp-pubdate">publication_date</Label>
                    <Input
                      id="kp-pubdate"
                      type="date"
                      value={patchPubDate}
                      onChange={(e) => setPatchPubDate(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>reliability_label</Label>
                    <Select value={patchReliability} onValueChange={setPatchReliability}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {KNOWLEDGE_RELIABILITY_LABELS.map((r) => (
                          <SelectItem key={r} value={r}>
                            {r}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>status</Label>
                    <Select value={patchStatus} onValueChange={setPatchStatus}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {KNOWLEDGE_SOURCE_STATUS.map((s) => (
                          <SelectItem key={s} value={s}>
                            {s}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <Button type="button" disabled={patchBusy} onClick={() => void submitPatch()}>
                  {patchBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                  Save changes
                </Button>

                <DeveloperJsonPanel data={detail} />
              </>
            ) : (
              <p className="text-sm text-muted-foreground">No detail loaded.</p>
            )}
          </CardContent>
        </Card>
      ) : null}

      {selectedId != null ? (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">Source files</CardTitle>
            <CardDescription>
              Upload and manage files attached to this knowledge source.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
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
            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-2">
                <Label htmlFor="ks-file">file</Label>
                <Input
                  id="ks-file"
                  type="file"
                  onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
                />
              </div>
              <Button type="button" disabled={uploadBusy} onClick={() => void submitUpload()}>
                {uploadBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                Upload file
              </Button>
            </div>

            {filesLoading ? (
              <p className="text-sm text-muted-foreground">Loading files…</p>
            ) : filesErr ? (
              <p className="text-sm text-muted-foreground">{filesErr}</p>
            ) : files.length === 0 ? (
              <p className="text-sm text-muted-foreground">No files returned.</p>
            ) : (
              <div className="table-scroll min-w-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[72px]">id</TableHead>
                      <TableHead>filename</TableHead>
                      <TableHead className="font-mono text-[11px]">sha256</TableHead>
                      <TableHead>parse_status</TableHead>
                      <TableHead className="text-right">warnings</TableHead>
                  <TableHead>created_at</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {files.map((row, idx) => {
                      const fid = readRecordNumber(row, "id")
                      const sha = readRecordString(row, "sha256")
                      const warnCt = readStringList(row["warnings_json"]).length
                      return (
                        <TableRow key={fid != null ? `f-${fid}` : `f-${idx}`}>
                          <TableCell className="font-mono text-xs">{fid ?? "—"}</TableCell>
                          <TableCell className="max-w-[200px] truncate text-sm">
                            {readRecordString(row, "filename") ?? "—"}
                          </TableCell>
                          <TableCell className="max-w-[min(280px,40vw)] truncate font-mono text-[10px] text-muted-foreground">
                            {sha ?? "—"}
                          </TableCell>
                          <TableCell>
                            <Badge variant="secondary">{readRecordString(row, "parse_status") ?? "—"}</Badge>
                          </TableCell>
                          <TableCell className="text-right tabular-nums text-xs">{warnCt}</TableCell>
                          <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                            {formatWhen(readRecordString(row, "created_at"))}
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
      ) : null}
    </div>
  )
}
