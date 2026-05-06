"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
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

function formatWhen(iso: string | undefined): string {
  if (!iso?.trim()) return "—"
  const d = Date.parse(iso)
  if (Number.isNaN(d)) return iso
  return new Date(d).toLocaleString()
}

function readStringList(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.filter((x): x is string => typeof x === "string" && x.trim().length > 0)
}

function readIntList(v: unknown): number[] {
  if (!Array.isArray(v)) return []
  return v.filter((x): x is number => typeof x === "number" && Number.isFinite(x))
}

export function RegulatorySourceVersionTimelineWorkspace({ sourceId }: { sourceId: number }) {
  const [loading, setLoading] = useState(true)
  const [loadErr, setLoadErr] = useState("")
  const [versions, setVersions] = useState<Record<string, unknown>[]>([])

  const [oldVersionId, setOldVersionId] = useState<string>("")
  const [newVersionId, setNewVersionId] = useState<string>("")
  const [oldDetail, setOldDetail] = useState<Record<string, unknown> | null>(null)
  const [newDetail, setNewDetail] = useState<Record<string, unknown> | null>(null)
  const [compareBusy, setCompareBusy] = useState(false)
  const [compareErr, setCompareErr] = useState("")
  const [compareResult, setCompareResult] = useState<Record<string, unknown> | null>(null)

  const loadVersions = useCallback(async () => {
    if (!Number.isFinite(sourceId) || sourceId < 1) {
      setLoading(false)
      setLoadErr("Invalid source id.")
      setVersions([])
      return
    }
    setLoading(true)
    setLoadErr("")
    try {
      const raw = await apiFetch<unknown>(`/regulatory/sources/${sourceId}/versions`, { method: "GET" })
      const rows = asArray(raw).filter(isRecord) as Record<string, unknown>[]
      setVersions(rows)
      const firstId = rows[0] ? readRecordNumber(rows[0], "id") : null
      const secondId = rows[1] ? readRecordNumber(rows[1], "id") : null
      setNewVersionId(firstId != null ? String(firstId) : "")
      setOldVersionId(secondId != null ? String(secondId) : firstId != null ? String(firstId) : "")
    } catch (e) {
      setLoadErr(formatApiError(e, "Could not load source versions."))
      setVersions([])
      setOldVersionId("")
      setNewVersionId("")
    } finally {
      setLoading(false)
    }
  }, [sourceId])

  useEffect(() => {
    void loadVersions()
  }, [loadVersions])

  useEffect(() => {
    let cancelled = false
    async function loadOne(versionId: string, setFn: (v: Record<string, unknown> | null) => void) {
      if (!versionId) {
        setFn(null)
        return
      }
      try {
        const res = await apiFetch<unknown>(`/regulatory/sources/${sourceId}/versions/${versionId}`, { method: "GET" })
        if (!cancelled) setFn(isRecord(res) ? res : null)
      } catch {
        if (!cancelled) setFn(null)
      }
    }
    void loadOne(oldVersionId, setOldDetail)
    void loadOne(newVersionId, setNewDetail)
    return () => {
      cancelled = true
    }
  }, [sourceId, oldVersionId, newVersionId])

  const sourceTitle = useMemo(() => {
    const r = newDetail ?? oldDetail ?? versions[0] ?? null
    return readRecordString(r, "title") ?? `source_id ${sourceId}`
  }, [sourceId, newDetail, oldDetail, versions])

  async function runCompare() {
    if (!oldVersionId || !newVersionId) {
      setCompareErr("Choose old and new versions.")
      return
    }
    const oldNum = Number.parseInt(oldVersionId, 10)
    const newNum = Number.parseInt(newVersionId, 10)
    if (!Number.isFinite(oldNum) || !Number.isFinite(newNum)) {
      setCompareErr("version ids must be numeric.")
      return
    }
    setCompareBusy(true)
    setCompareErr("")
    try {
      const res = await apiFetch<unknown>(`/regulatory/sources/${sourceId}/versions/compare`, {
        method: "POST",
        body: { old_version_id: oldNum, new_version_id: newNum, metadata_json: {} },
      })
      setCompareResult(isRecord(res) ? res : {})
    } catch (e) {
      setCompareErr(formatApiError(e, "Compare failed."))
      setCompareResult(null)
    } finally {
      setCompareBusy(false)
    }
  }

  const topics = readStringList(compareResult?.affected_topics_json)
  const citationIds = readIntList(compareResult?.citation_ids_json)

  return (
    <div className="mx-auto max-w-[1200px] space-y-6 p-4 md:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/regulatory/sources">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Regulatory Source Library
          </Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/regulatory/surveillance">Surveillance dashboard</Link>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link href="/regulatory/rule-updates">Rule update proposals</Link>
        </Button>
      </div>

      <header className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Source Version Timeline</h1>
        <p className="text-sm text-muted-foreground">
          Source text changed, potential impact, and requires review indicators are shown from API comparison output.
        </p>
      </header>

      <Alert>
        <AlertTriangle className="h-4 w-4" aria-hidden />
        <AlertTitle>Requires review</AlertTitle>
        <AlertDescription className="text-sm text-muted-foreground">
          Source text changed output is decision support and potential impact triage only. Qualified human review is required.
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Version timeline</CardTitle>
          <CardDescription>GET /regulatory/sources/{`{source_id}`}/versions</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="mb-3 text-sm">
            <span className="font-medium">{sourceTitle}</span>{" "}
            <span className="font-mono text-xs text-muted-foreground">source_id {sourceId}</span>
          </p>
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading versions…</p>
          ) : loadErr ? (
            <Alert variant="destructive">
              <AlertDescription className="text-sm">{loadErr}</AlertDescription>
            </Alert>
          ) : versions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No versions available.</p>
          ) : (
            <div className="table-scroll">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>version timeline</TableHead>
                    <TableHead>version label</TableHead>
                    <TableHead>source date</TableHead>
                    <TableHead>retrieved date</TableHead>
                    <TableHead>SHA-256/content hash</TableHead>
                    <TableHead>status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {versions.map((row, idx) => {
                    const id = readRecordNumber(row, "id")
                    const sha = readRecordString(row, "sha256")
                    const ch = readRecordString(row, "content_hash")
                    return (
                      <TableRow key={id != null ? `ver-${id}` : `ver-${idx}`}>
                        <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                        <TableCell className="text-xs">{readRecordString(row, "version_label") ?? "—"}</TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                          {formatWhen(readRecordString(row, "source_date") ?? undefined)}
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                          {formatWhen(readRecordString(row, "retrieved_at") ?? undefined)}
                        </TableCell>
                        <TableCell className="max-w-[220px] truncate font-mono text-[10px]" title={`${sha ?? ""} ${ch ?? ""}`.trim()}>
                          {sha ?? ch ?? "—"}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
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

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Compare versions</CardTitle>
          <CardDescription>GET /regulatory/sources/{`{source_id}`}/versions/{`{version_id}`} · POST …/versions/compare</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>old version</Label>
              <Select value={oldVersionId || "__none__"} onValueChange={(v) => setOldVersionId(v === "__none__" ? "" : v)}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Choose old version" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Choose old version</SelectItem>
                  {versions.map((row, idx) => {
                    const id = readRecordNumber(row, "id")
                    if (id == null) return null
                    const label = readRecordString(row, "version_label") ?? `version ${id}`
                    return (
                      <SelectItem key={`old-${id}-${idx}`} value={String(id)}>
                        {label} (id {id})
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>new version</Label>
              <Select value={newVersionId || "__none__"} onValueChange={(v) => setNewVersionId(v === "__none__" ? "" : v)}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Choose new version" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">Choose new version</SelectItem>
                  {versions.map((row, idx) => {
                    const id = readRecordNumber(row, "id")
                    if (id == null) return null
                    const label = readRecordString(row, "version_label") ?? `version ${id}`
                    return (
                      <SelectItem key={`new-${id}-${idx}`} value={String(id)}>
                        {label} (id {id})
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
            </div>
          </div>
          {compareErr ? (
            <Alert variant="destructive">
              <AlertDescription className="text-sm">{compareErr}</AlertDescription>
            </Alert>
          ) : null}
          <Button type="button" disabled={compareBusy} onClick={() => void runCompare()}>
            {compareBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Compare
          </Button>

          <div className="grid gap-4 md:grid-cols-2">
            <Card className="border-muted">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Old version details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-xs">
                <p>version label: {readRecordString(oldDetail, "version_label") ?? "—"}</p>
                <p>source date: {formatWhen(readRecordString(oldDetail, "source_date") ?? undefined)}</p>
                <p>retrieved date: {formatWhen(readRecordString(oldDetail, "retrieved_at") ?? undefined)}</p>
                <p className="font-mono break-all">SHA-256/content hash: {readRecordString(oldDetail, "sha256") ?? readRecordString(oldDetail, "content_hash") ?? "—"}</p>
                <p>status: {readRecordString(oldDetail, "status") ?? "—"}</p>
              </CardContent>
            </Card>
            <Card className="border-muted">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">New version details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-xs">
                <p>version label: {readRecordString(newDetail, "version_label") ?? "—"}</p>
                <p>source date: {formatWhen(readRecordString(newDetail, "source_date") ?? undefined)}</p>
                <p>retrieved date: {formatWhen(readRecordString(newDetail, "retrieved_at") ?? undefined)}</p>
                <p className="font-mono break-all">SHA-256/content hash: {readRecordString(newDetail, "sha256") ?? readRecordString(newDetail, "content_hash") ?? "—"}</p>
                <p>status: {readRecordString(newDetail, "status") ?? "—"}</p>
              </CardContent>
            </Card>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Diff viewer</CardTitle>
          <CardDescription>Source text changed · Potential impact · Requires review</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!compareResult ? (
            <p className="text-sm text-muted-foreground">Run compare to view diff summary.</p>
          ) : (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">before excerpt</p>
                  <blockquote className="mt-1 rounded-md border border-dashed bg-muted/40 px-3 py-2 text-sm leading-relaxed">
                    {readRecordString(compareResult, "before_excerpt") ?? "—"}
                  </blockquote>
                </div>
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">after excerpt</p>
                  <blockquote className="mt-1 rounded-md border border-dashed bg-muted/40 px-3 py-2 text-sm leading-relaxed">
                    {readRecordString(compareResult, "after_excerpt") ?? "—"}
                  </blockquote>
                </div>
              </div>

              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">diff summary</p>
                <p className="mt-1 text-sm">{readRecordString(compareResult, "diff_summary") ?? "—"}</p>
              </div>

              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">affected topics</p>
                {topics.length === 0 ? (
                  <p className="mt-1 text-sm text-muted-foreground">—</p>
                ) : (
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {topics.map((topic, idx) => (
                      <Badge key={`topic-${idx}`} variant="secondary">
                        {topic}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">citations if returned</p>
                {citationIds.length === 0 ? (
                  <p className="mt-1 text-sm text-muted-foreground">—</p>
                ) : (
                  <p className="mt-1 font-mono text-xs">{citationIds.join(", ")}</p>
                )}
              </div>

              <DeveloperJsonPanel data={compareResult} />
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
