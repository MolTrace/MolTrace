"use client"

import Link from "next/link"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import {
  DATASET_SPLIT_RECOMMENDATIONS,
  DATASET_VERSION_STATUSES,
  KNOWLEDGE_BENCHMARK_TYPES,
  KNOWLEDGE_CANDIDATE_STATUSES,
  KNOWLEDGE_REVIEW_RECORD_TYPES,
  KNOWLEDGE_TRAINING_DATASET_TYPES,
  LEAKAGE_RISK_LABELS,
} from "@/components/knowledge/knowledge-constants"
import { InfoTooltip } from "@/components/ui/info-tooltip"
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
import { TooltipProvider } from "@/components/ui/tooltip"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import {
  ArrowLeft,
  BarChart3,
  Database,
  GitBranch,
  Loader2,
  RefreshCw,
  ShieldAlert,
} from "lucide-react"

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

function parseCommaInts(raw: string): number[] {
  return raw
    .split(/[,;\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => Number.parseInt(s, 10))
    .filter((n) => Number.isFinite(n) && n >= 1)
}

function readIntList(v: unknown): number[] {
  if (!Array.isArray(v)) return []
  return v.filter((x): x is number => typeof x === "number" && Number.isFinite(x))
}

function readStringList(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.filter((x): x is string => typeof x === "string" && x.trim().length > 0)
}

function readStringListFromComma(raw: string): string[] {
  return raw
    .split(/[,;\n]+/)
    .map((s) => s.trim())
    .filter(Boolean)
}

function formatWhen(iso: string | undefined): string {
  if (!iso?.trim()) return "—"
  const d = Date.parse(iso)
  if (Number.isNaN(d)) return iso
  return new Date(d).toLocaleString()
}

function readHumanReviewRequired(obj: unknown): string {
  if (!obj || typeof obj !== "object") return "—"
  const v = (obj as Record<string, unknown>).human_review_required
  if (typeof v === "boolean") return v ? "true" : "false"
  return "—"
}

function truncateSummary(s: string, max = 160): string {
  const t = s.trim()
  if (t.length <= max) return t
  return `${t.slice(0, max)}…`
}

const SPLIT_KEYS = ["train", "validation", "test", "holdout"] as const

const DATASET_TOOLTIP =
  "Dataset candidates are reviewed records that may become training, validation, test, or benchmark data. They must preserve citations and avoid leakage."

export function KnowledgeDatasetsDashboard() {
  const [loading, setLoading] = useState(true)
  const [reloadToken, setReloadToken] = useState(0)

  const [training, setTraining] = useState<Record<string, unknown>[]>([])
  const [benchmark, setBenchmark] = useState<Record<string, unknown>[]>([])
  const [versions, setVersions] = useState<Record<string, unknown>[]>([])

  const [errTraining, setErrTraining] = useState("")
  const [errBenchmark, setErrBenchmark] = useState("")
  const [errVersions, setErrVersions] = useState("")

  const [filterTrainStatus, setFilterTrainStatus] = useState("")
  const [filterBenchStatus, setFilterBenchStatus] = useState("")
  const [filterVersionStatus, setFilterVersionStatus] = useState("")

  const [selTrain, setSelTrain] = useState<Record<string, unknown> | null>(null)
  const [selBench, setSelBench] = useState<Record<string, unknown> | null>(null)
  const [selVersion, setSelVersion] = useState<Record<string, unknown> | null>(null)
  const [versionDetail, setVersionDetail] = useState<Record<string, unknown> | null>(null)
  const [versionDetailLoading, setVersionDetailLoading] = useState(false)
  const [versionDetailErr, setVersionDetailErr] = useState("")

  const [patchTrainStatus, setPatchTrainStatus] = useState("proposed")
  const [patchTrainFlags, setPatchTrainFlags] = useState("")
  const [patchTrainCitations, setPatchTrainCitations] = useState("")
  const [patchTrainBusy, setPatchTrainBusy] = useState(false)
  const [patchTrainErr, setPatchTrainErr] = useState("")
  const [patchTrainOk, setPatchTrainOk] = useState("")

  const [patchBenchStatus, setPatchBenchStatus] = useState("proposed")
  const [patchBenchSplit, setPatchBenchSplit] = useState<string>("unknown")
  const [patchBenchLeak, setPatchBenchLeak] = useState<string>("unknown")
  const [patchBenchFlags, setPatchBenchFlags] = useState("")
  const [patchBenchBusy, setPatchBenchBusy] = useState(false)
  const [patchBenchErr, setPatchBenchErr] = useState("")
  const [patchBenchOk, setPatchBenchOk] = useState("")

  const [createTrainSourceId, setCreateTrainSourceId] = useState("")
  const [createTrainRecordType, setCreateTrainRecordType] = useState<string>("reaction")
  const [createTrainRecordId, setCreateTrainRecordId] = useState("")
  const [createTrainDatasetType, setCreateTrainDatasetType] = useState<string>("reaction_optimization")
  const [createTrainCitations, setCreateTrainCitations] = useState("")
  const [createTrainFlags, setCreateTrainFlags] = useState("")
  const [createTrainBusy, setCreateTrainBusy] = useState(false)
  const [createTrainErr, setCreateTrainErr] = useState("")
  const [createTrainOk, setCreateTrainOk] = useState("")

  const [createBenchSourceId, setCreateBenchSourceId] = useState("")
  const [createBenchRecordType, setCreateBenchRecordType] = useState<string>("reaction")
  const [createBenchRecordId, setCreateBenchRecordId] = useState("")
  const [createBenchType, setCreateBenchType] = useState<string>("reaction_optimization")
  const [createBenchFlags, setCreateBenchFlags] = useState("")
  const [createBenchBusy, setCreateBenchBusy] = useState(false)
  const [createBenchErr, setCreateBenchErr] = useState("")
  const [createBenchOk, setCreateBenchOk] = useState("")

  const [dvName, setDvName] = useState("")
  const [dvDatasetType, setDvDatasetType] = useState<string>("reaction_optimization")
  const [dvVersion, setDvVersion] = useState("")
  const [dvTrainIds, setDvTrainIds] = useState("")
  const [dvValIds, setDvValIds] = useState("")
  const [dvTestIds, setDvTestIds] = useState("")
  const [dvHoldoutIds, setDvHoldoutIds] = useState("")
  const [createDvBusy, setCreateDvBusy] = useState(false)
  const [createDvErr, setCreateDvErr] = useState("")
  const [createDvOk, setCreateDvOk] = useState("")

  const [patchVName, setPatchVName] = useState("")
  const [patchVVersion, setPatchVVersion] = useState("")
  const [patchVStatus, setPatchVStatus] = useState<string>("draft")
  const [patchVBusy, setPatchVBusy] = useState(false)
  const [patchVErr, setPatchVErr] = useState("")
  const [patchVOk, setPatchVOk] = useState("")

  const loadAll = useCallback(async () => {
    setLoading(true)
    setErrTraining("")
    setErrBenchmark("")
    setErrVersions("")
    const trainParams = new URLSearchParams()
    trainParams.set("limit", "500")
    if (filterTrainStatus.trim()) trainParams.set("status", filterTrainStatus.trim())
    const benchParams = new URLSearchParams()
    benchParams.set("limit", "500")
    if (filterBenchStatus.trim()) benchParams.set("status", filterBenchStatus.trim())
    const verParams = new URLSearchParams()
    verParams.set("limit", "500")
    if (filterVersionStatus.trim()) verParams.set("status", filterVersionStatus.trim())

    const [tr, bc, dv] = await Promise.all([
      apiFetch<unknown>(`/knowledge/training-dataset-candidates?${trainParams}`, { method: "GET" }).catch((e) => {
        setErrTraining(formatApiError(e, "Could not load training dataset candidates."))
        return []
      }),
      apiFetch<unknown>(`/knowledge/benchmark-dataset-candidates?${benchParams}`, { method: "GET" }).catch((e) => {
        setErrBenchmark(formatApiError(e, "Could not load benchmark dataset candidates."))
        return []
      }),
      apiFetch<unknown>(`/knowledge/dataset-versions?${verParams}`, { method: "GET" }).catch((e) => {
        setErrVersions(formatApiError(e, "Could not load dataset versions."))
        return []
      }),
    ])
    setTraining(asArray(tr).filter(isRecord) as Record<string, unknown>[])
    setBenchmark(asArray(bc).filter(isRecord) as Record<string, unknown>[])
    setVersions(asArray(dv).filter(isRecord) as Record<string, unknown>[])
    setLoading(false)
  }, [filterTrainStatus, filterBenchStatus, filterVersionStatus])

  useEffect(() => {
    void loadAll()
  }, [loadAll, reloadToken])

  const leakageAnalytics = useMemo(() => {
    const counts: Record<string, number> = { low: 0, medium: 0, high: 0, unknown: 0 }
    for (const row of benchmark) {
      const lab = (readRecordString(row, "leakage_risk_label") ?? "unknown").toLowerCase()
      if (lab in counts) counts[lab]++
      else counts.unknown++
    }
    const warnings: string[] = []
    const seen = new Set<string>()
    for (const row of versions) {
      for (const w of readStringList(row["leakage_warnings_json"])) {
        if (!seen.has(w)) {
          seen.add(w)
          warnings.push(w)
        }
      }
    }
    return { counts, warnings }
  }, [benchmark, versions])

  const qualityFlagAnalytics = useMemo(() => {
    const tally = new Map<string, number>()
    for (const row of training) {
      for (const f of readStringList(row["quality_flags_json"])) {
        tally.set(f, (tally.get(f) ?? 0) + 1)
      }
    }
    for (const row of benchmark) {
      for (const f of readStringList(row["quality_flags_json"])) {
        tally.set(f, (tally.get(f) ?? 0) + 1)
      }
    }
    return [...tally.entries()].sort((a, b) => b[1] - a[1])
  }, [training, benchmark])

  useEffect(() => {
    if (!selTrain) return
    setPatchTrainStatus(readRecordString(selTrain, "status") ?? "proposed")
    setPatchTrainFlags(readStringList(selTrain["quality_flags_json"]).join(", "))
    setPatchTrainCitations(readIntList(selTrain["citation_ids_json"]).join(", "))
  }, [selTrain])

  useEffect(() => {
    if (!selBench) return
    setPatchBenchStatus(readRecordString(selBench, "status") ?? "proposed")
    setPatchBenchSplit(readRecordString(selBench, "split_recommendation") ?? "unknown")
    setPatchBenchLeak(readRecordString(selBench, "leakage_risk_label") ?? "unknown")
    setPatchBenchFlags(readStringList(selBench["quality_flags_json"]).join(", "))
  }, [selBench])

  useEffect(() => {
    if (!selVersion) return
    setPatchVName(readRecordString(selVersion, "name") ?? "")
    setPatchVVersion(readRecordString(selVersion, "version") ?? "")
    setPatchVStatus(readRecordString(selVersion, "status") ?? "draft")
  }, [selVersion])

  useEffect(() => {
    const id = selVersion ? readRecordNumber(selVersion, "id") : undefined
    if (id == null) {
      setVersionDetail(null)
      setVersionDetailErr("")
      return
    }
    let cancelled = false
    setVersionDetailLoading(true)
    setVersionDetail(null)
    setVersionDetailErr("")
    void (async () => {
      try {
        const raw = await apiFetch<unknown>(`/knowledge/dataset-versions/${id}`, { method: "GET" })
        if (cancelled) return
        setVersionDetail(isRecord(raw) ? raw : null)
      } catch (e) {
        if (cancelled) return
        setVersionDetail(null)
        setVersionDetailErr(formatApiError(e, "Could not load dataset version."))
      } finally {
        if (!cancelled) setVersionDetailLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selVersion])

  async function submitPatchTraining() {
    const id = selTrain ? readRecordNumber(selTrain, "id") : null
    if (id == null) return
    setPatchTrainErr("")
    setPatchTrainOk("")
    setPatchTrainBusy(true)
    try {
      await apiFetch(`/knowledge/training-dataset-candidates/${id}`, {
        method: "PATCH",
        body: {
          status: patchTrainStatus,
          quality_flags_json: readStringListFromComma(patchTrainFlags),
          citation_ids_json: parseCommaInts(patchTrainCitations),
          metadata_json: {},
        },
      })
      setPatchTrainOk("training-dataset-candidates updated.")
      setReloadToken((x) => x + 1)
    } catch (e) {
      setPatchTrainErr(formatApiError(e, "Patch failed."))
    } finally {
      setPatchTrainBusy(false)
    }
  }

  async function submitPatchBenchmark() {
    const id = selBench ? readRecordNumber(selBench, "id") : null
    if (id == null) return
    setPatchBenchErr("")
    setPatchBenchOk("")
    setPatchBenchBusy(true)
    try {
      await apiFetch(`/knowledge/benchmark-dataset-candidates/${id}`, {
        method: "PATCH",
        body: {
          status: patchBenchStatus,
          split_recommendation: patchBenchSplit,
          leakage_risk_label: patchBenchLeak,
          quality_flags_json: readStringListFromComma(patchBenchFlags),
          metadata_json: {},
        },
      })
      setPatchBenchOk("benchmark-dataset-candidates updated.")
      setReloadToken((x) => x + 1)
    } catch (e) {
      setPatchBenchErr(formatApiError(e, "Patch failed."))
    } finally {
      setPatchBenchBusy(false)
    }
  }

  async function submitCreateTraining() {
    const rid = Number.parseInt(createTrainRecordId.trim(), 10)
    if (!Number.isFinite(rid) || rid < 1) {
      setCreateTrainErr("record_id must be a positive integer.")
      return
    }
    const sidRaw = createTrainSourceId.trim()
    let source_id: number | undefined
    if (sidRaw) {
      const s = Number.parseInt(sidRaw, 10)
      if (!Number.isFinite(s) || s < 1) {
        setCreateTrainErr("source_id must be empty or a positive integer.")
        return
      }
      source_id = s
    }
    setCreateTrainErr("")
    setCreateTrainOk("")
    setCreateTrainBusy(true)
    try {
      await apiFetch("/knowledge/training-dataset-candidates", {
        method: "POST",
        body: {
          source_id,
          record_type: createTrainRecordType,
          record_id: rid,
          dataset_type: createTrainDatasetType,
          status: "proposed",
          quality_flags_json: readStringListFromComma(createTrainFlags),
          citation_ids_json: parseCommaInts(createTrainCitations),
          metadata_json: {},
        },
      })
      setCreateTrainOk("POST /knowledge/training-dataset-candidates succeeded.")
      setReloadToken((x) => x + 1)
    } catch (e) {
      setCreateTrainErr(formatApiError(e, "Create failed."))
    } finally {
      setCreateTrainBusy(false)
    }
  }

  async function submitCreateBenchmark() {
    const rid = Number.parseInt(createBenchRecordId.trim(), 10)
    if (!Number.isFinite(rid) || rid < 1) {
      setCreateBenchErr("record_id must be a positive integer.")
      return
    }
    const sidRaw = createBenchSourceId.trim()
    let source_id: number | undefined
    if (sidRaw) {
      const s = Number.parseInt(sidRaw, 10)
      if (!Number.isFinite(s) || s < 1) {
        setCreateBenchErr("source_id must be empty or a positive integer.")
        return
      }
      source_id = s
    }
    setCreateBenchErr("")
    setCreateBenchOk("")
    setCreateBenchBusy(true)
    try {
      await apiFetch("/knowledge/benchmark-dataset-candidates", {
        method: "POST",
        body: {
          source_id,
          record_type: createBenchRecordType,
          record_id: rid,
          benchmark_type: createBenchType,
          status: "proposed",
          split_recommendation: "unknown",
          leakage_risk_label: "unknown",
          quality_flags_json: readStringListFromComma(createBenchFlags),
          metadata_json: {},
        },
      })
      setCreateBenchOk("POST /knowledge/benchmark-dataset-candidates succeeded.")
      setReloadToken((x) => x + 1)
    } catch (e) {
      setCreateBenchErr(formatApiError(e, "Create failed."))
    } finally {
      setCreateBenchBusy(false)
    }
  }

  async function submitCreateDatasetVersion() {
    const name = dvName.trim()
    const ver = dvVersion.trim()
    const dt = dvDatasetType.trim()
    if (!name || !ver || !dt) {
      setCreateDvErr("name, version, and dataset_type are required.")
      return
    }
    const train = parseCommaInts(dvTrainIds)
    const validation = parseCommaInts(dvValIds)
    const test = parseCommaInts(dvTestIds)
    const holdout = parseCommaInts(dvHoldoutIds)
    const split_json: Record<string, number[]> = {
      train,
      validation,
      test,
      holdout,
    }
    const union = Array.from(new Set([...train, ...validation, ...test, ...holdout]))
    setCreateDvErr("")
    setCreateDvOk("")
    setCreateDvBusy(true)
    try {
      await apiFetch("/knowledge/dataset-versions", {
        method: "POST",
        body: {
          dataset_type: dt,
          name,
          version: ver,
          source_record_ids_json: union,
          split_json,
          quality_summary_json: {},
          leakage_warnings_json: [],
          status: "draft",
          metadata_json: {},
        },
      })
      setCreateDvOk("POST /knowledge/dataset-versions succeeded.")
      setReloadToken((x) => x + 1)
    } catch (e) {
      setCreateDvErr(formatApiError(e, "Create failed."))
    } finally {
      setCreateDvBusy(false)
    }
  }

  async function submitPatchVersion() {
    const id = selVersion ? readRecordNumber(selVersion, "id") : null
    if (id == null) return
    setPatchVErr("")
    setPatchVOk("")
    setPatchVBusy(true)
    try {
      await apiFetch(`/knowledge/dataset-versions/${id}`, {
        method: "PATCH",
        body: {
          name: patchVName.trim() || undefined,
          version: patchVVersion.trim() || undefined,
          status: patchVStatus,
          metadata_json: {},
        },
      })
      setPatchVOk("dataset-versions updated.")
      setReloadToken((x) => x + 1)
    } catch (e) {
      setPatchVErr(formatApiError(e, "Patch failed."))
    } finally {
      setPatchVBusy(false)
    }
  }

  const trainId = selTrain ? readRecordNumber(selTrain, "id") : null
  const benchId = selBench ? readRecordNumber(selBench, "id") : null
  const verId = selVersion ? readRecordNumber(selVersion, "id") : null

  return (
    <TooltipProvider delayDuration={200}>
      <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="ghost" size="sm" asChild>
            <Link href="/knowledge">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Knowledge Library
            </Link>
          </Button>
          <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void loadAll()}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : <RefreshCw className="mr-2 h-4 w-4" aria-hidden />}
            Refresh
          </Button>
          <div className="inline-flex items-center gap-1.5">
            <span className="text-sm font-medium">ML / AI dataset candidates</span>
            <InfoTooltip content={DATASET_TOOLTIP} label="About dataset candidates" />
          </div>
        </div>

        <div className="space-y-1">
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-amber)" }}
          >
            MolTrace · Knowledge · Dataset Candidates
          </p>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Dataset candidate dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Governance-focused listing: identifiers and review metadata only. Do not treat aggregates as validation of
            underlying chemistry or confidential content.
          </p>
        </div>

        <AlertCard
          variant="warning"
          title="Review before ML use"
          description="Dataset candidates reference reviewed records; approval workflows and leakage checks must complete before training or benchmarking."
        />

        {/* 1. Training */}
        <ModuleCard
          accent="teal"
          eyebrow="Training"
          title="1. Training dataset candidates"
          icon={Database}
          description="Curated knowledge claims nominated for ML model training — identifiers, record type, review metadata, and curation status."
        >
          <div className="space-y-4">
            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-2">
                <Label>status filter</Label>
                <Select value={filterTrainStatus || "__all"} onValueChange={(v) => setFilterTrainStatus(v === "__all" ? "" : v)}>
                  <SelectTrigger className="w-[200px]">
                    <SelectValue placeholder="All" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all">All</SelectItem>
                    {KNOWLEDGE_CANDIDATE_STATUSES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {errTraining ? (
              <p className="text-sm text-muted-foreground">{errTraining}</p>
            ) : loading ? (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                Loading…
              </p>
            ) : (
              <div className="table-scroll min-w-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[72px]">id</TableHead>
                      <TableHead>status</TableHead>
                      <TableHead>dataset_type</TableHead>
                      <TableHead>record_type</TableHead>
                      <TableHead className="w-[88px]">record_id</TableHead>
                      <TableHead className="w-[88px]">source_id</TableHead>
                      <TableHead className="text-right">citation_ids_json</TableHead>
                      <TableHead>quality_flags_json</TableHead>
                      <TableHead>created_at</TableHead>
                      <TableHead>human_review_required</TableHead>
                      <TableHead className="w-[90px]">open</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {training.map((row, idx) => {
                      const id = readRecordNumber(row, "id")
                      const cit = readIntList(row["citation_ids_json"]).length
                      const flags = readStringList(row["quality_flags_json"])
                      const flagPreview = flags.length ? truncateSummary(flags.join(" · "), 80) : "—"
                      return (
                        <TableRow key={id != null ? `tr-${id}` : `tr-${idx}`}>
                          <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                          <TableCell>
                            <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
                          </TableCell>
                          <TableCell className="font-mono text-xs">{readRecordString(row, "dataset_type") ?? "—"}</TableCell>
                          <TableCell className="font-mono text-xs">{readRecordString(row, "record_type") ?? "—"}</TableCell>
                          <TableCell className="font-mono text-xs">{readRecordNumber(row, "record_id") ?? "—"}</TableCell>
                          <TableCell className="font-mono text-xs">{readRecordNumber(row, "source_id") ?? "—"}</TableCell>
                          <TableCell className="text-right tabular-nums text-xs">{cit}</TableCell>
                          <TableCell className="max-w-[140px] truncate text-xs" title={flags.join(", ")}>
                            {flagPreview}
                          </TableCell>
                          <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                            {formatWhen(readRecordString(row, "created_at"))}
                          </TableCell>
                          <TableCell className="font-mono text-xs">{readHumanReviewRequired(row)}</TableCell>
                          <TableCell>
                            <Button
                              type="button"
                              size="sm"
                              variant={selTrain === row ? "secondary" : "outline"}
                              className="h-8"
                              onClick={() => setSelTrain(row)}
                            >
                              Open
                            </Button>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
                {training.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No rows returned.</p> : null}
              </div>
            )}

            <Card className="border-dashed">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Nominate training candidate</CardTitle>
                <CardDescription>
                  Nominate a knowledge claim as a training candidate by specifying the record type, record ID, dataset type, source, citation IDs, and quality flags.
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                <div className="space-y-2">
                  <Label htmlFor="ct-source">source_id (optional)</Label>
                  <Input id="ct-source" className="font-mono" value={createTrainSourceId} onChange={(e) => setCreateTrainSourceId(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>record_type</Label>
                  <Select value={createTrainRecordType} onValueChange={setCreateTrainRecordType}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {KNOWLEDGE_REVIEW_RECORD_TYPES.map((t) => (
                        <SelectItem key={t} value={t}>
                          {t}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="ct-rid">record_id</Label>
                  <Input id="ct-rid" className="font-mono" value={createTrainRecordId} onChange={(e) => setCreateTrainRecordId(e.target.value)} />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label>dataset_type</Label>
                  <Select value={createTrainDatasetType} onValueChange={setCreateTrainDatasetType}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {KNOWLEDGE_TRAINING_DATASET_TYPES.map((t) => (
                        <SelectItem key={t} value={t}>
                          {t}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2 md:col-span-3">
                  <Label htmlFor="ct-cit">citation_ids_json (comma-separated integers)</Label>
                  <Input id="ct-cit" className="font-mono text-xs" value={createTrainCitations} onChange={(e) => setCreateTrainCitations(e.target.value)} />
                </div>
                <div className="space-y-2 md:col-span-3">
                  <Label htmlFor="ct-fl">quality_flags_json (comma-separated)</Label>
                  <Input id="ct-fl" className="font-mono text-xs" value={createTrainFlags} onChange={(e) => setCreateTrainFlags(e.target.value)} />
                </div>
                <div className="md:col-span-3 flex flex-wrap items-center gap-2">
                  <Button type="button" disabled={createTrainBusy} onClick={() => void submitCreateTraining()}>
                    {createTrainBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                    Create
                  </Button>
                  {createTrainErr ? <span className="text-sm text-destructive">{createTrainErr}</span> : null}
                  {createTrainOk ? <span className="text-sm text-muted-foreground">{createTrainOk}</span> : null}
                </div>
              </CardContent>
            </Card>

            {selTrain && trainId != null ? (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">
                    PATCH training candidate{" "}
                    <code className="text-xs font-mono">
                      /knowledge/training-dataset-candidates/{trainId}
                    </code>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid gap-3 md:grid-cols-3">
                    <div className="space-y-2">
                      <Label>status</Label>
                      <Select value={patchTrainStatus} onValueChange={setPatchTrainStatus}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {KNOWLEDGE_CANDIDATE_STATUSES.map((s) => (
                            <SelectItem key={s} value={s}>
                              {s}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2 md:col-span-2">
                      <Label htmlFor="pt-cit">citation_ids_json</Label>
                      <Input id="pt-cit" className="font-mono text-xs" value={patchTrainCitations} onChange={(e) => setPatchTrainCitations(e.target.value)} />
                    </div>
                    <div className="space-y-2 md:col-span-3">
                      <Label htmlFor="pt-fl">quality_flags_json</Label>
                      <Textarea id="pt-fl" className="font-mono text-xs" rows={2} value={patchTrainFlags} onChange={(e) => setPatchTrainFlags(e.target.value)} />
                    </div>
                  </div>
                  <Button type="button" disabled={patchTrainBusy} onClick={() => void submitPatchTraining()}>
                    {patchTrainBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                    Save PATCH
                  </Button>
                  {patchTrainErr ? <p className="text-sm text-destructive">{patchTrainErr}</p> : null}
                  {patchTrainOk ? <p className="text-sm text-muted-foreground">{patchTrainOk}</p> : null}
                  <DeveloperJsonPanel data={selTrain} />
                </CardContent>
              </Card>
            ) : null}
          </div>
        </ModuleCard>

        {/* 2. Benchmark */}
        <ModuleCard
          accent="teal"
          eyebrow="Benchmark"
          title="2. Benchmark dataset candidates"
          icon={Database}
          description="Knowledge claims nominated for ML benchmark evaluation — includes leakage risk label and split recommendation. Citation IDs are not modeled on benchmark candidates and display as blank."
        >
          <div className="space-y-4">
            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-2">
                <Label>status filter</Label>
                <Select value={filterBenchStatus || "__all"} onValueChange={(v) => setFilterBenchStatus(v === "__all" ? "" : v)}>
                  <SelectTrigger className="w-[200px]">
                    <SelectValue placeholder="All" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all">All</SelectItem>
                    {KNOWLEDGE_CANDIDATE_STATUSES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {errBenchmark ? (
              <p className="text-sm text-muted-foreground">{errBenchmark}</p>
            ) : loading ? (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                Loading…
              </p>
            ) : (
              <div className="table-scroll min-w-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[72px]">id</TableHead>
                      <TableHead>status</TableHead>
                      <TableHead>benchmark_type</TableHead>
                      <TableHead>record_type</TableHead>
                      <TableHead className="w-[88px]">record_id</TableHead>
                      <TableHead className="w-[88px]">source_id</TableHead>
                      <TableHead className="text-right">citation_ids_json</TableHead>
                      <TableHead>quality_flags_json</TableHead>
                      <TableHead>leakage_risk_label</TableHead>
                      <TableHead>split_recommendation</TableHead>
                      <TableHead>created_at</TableHead>
                      <TableHead>human_review_required</TableHead>
                      <TableHead className="w-[90px]">open</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {benchmark.map((row, idx) => {
                      const id = readRecordNumber(row, "id")
                      const flags = readStringList(row["quality_flags_json"])
                      const flagPreview = flags.length ? truncateSummary(flags.join(" · "), 80) : "—"
                      return (
                        <TableRow key={id != null ? `bc-${id}` : `bc-${idx}`}>
                          <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                          <TableCell>
                            <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
                          </TableCell>
                          <TableCell className="font-mono text-xs">{readRecordString(row, "benchmark_type") ?? "—"}</TableCell>
                          <TableCell className="font-mono text-xs">{readRecordString(row, "record_type") ?? "—"}</TableCell>
                          <TableCell className="font-mono text-xs">{readRecordNumber(row, "record_id") ?? "—"}</TableCell>
                          <TableCell className="font-mono text-xs">{readRecordNumber(row, "source_id") ?? "—"}</TableCell>
                          <TableCell className="text-right tabular-nums text-xs text-muted-foreground" title="Not modeled on benchmark candidates">
                            —
                          </TableCell>
                          <TableCell className="max-w-[140px] truncate text-xs" title={flags.join(", ")}>
                            {flagPreview}
                          </TableCell>
                          <TableCell className="font-mono text-xs">{readRecordString(row, "leakage_risk_label") ?? "—"}</TableCell>
                          <TableCell className="font-mono text-xs">{readRecordString(row, "split_recommendation") ?? "—"}</TableCell>
                          <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                            {formatWhen(readRecordString(row, "created_at"))}
                          </TableCell>
                          <TableCell className="font-mono text-xs">{readHumanReviewRequired(row)}</TableCell>
                          <TableCell>
                            <Button
                              type="button"
                              size="sm"
                              variant={selBench === row ? "secondary" : "outline"}
                              className="h-8"
                              onClick={() => setSelBench(row)}
                            >
                              Open
                            </Button>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
                {benchmark.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No rows returned.</p> : null}
              </div>
            )}

            <Card className="border-dashed">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Nominate benchmark candidate</CardTitle>
                <CardDescription>
                  Nominate a knowledge claim as a benchmark evaluation candidate by specifying the record type, record ID, benchmark type, and leakage risk classification.
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                <div className="space-y-2">
                  <Label htmlFor="cb-source">source_id (optional)</Label>
                  <Input id="cb-source" className="font-mono" value={createBenchSourceId} onChange={(e) => setCreateBenchSourceId(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>record_type</Label>
                  <Select value={createBenchRecordType} onValueChange={setCreateBenchRecordType}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {KNOWLEDGE_REVIEW_RECORD_TYPES.map((t) => (
                        <SelectItem key={t} value={t}>
                          {t}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cb-rid">record_id</Label>
                  <Input id="cb-rid" className="font-mono" value={createBenchRecordId} onChange={(e) => setCreateBenchRecordId(e.target.value)} />
                </div>
                <div className="space-y-2 md:col-span-3">
                  <Label>benchmark_type</Label>
                  <Select value={createBenchType} onValueChange={setCreateBenchType}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {KNOWLEDGE_BENCHMARK_TYPES.map((t) => (
                        <SelectItem key={t} value={t}>
                          {t}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2 md:col-span-3">
                  <Label htmlFor="cb-fl">quality_flags_json (comma-separated)</Label>
                  <Input id="cb-fl" className="font-mono text-xs" value={createBenchFlags} onChange={(e) => setCreateBenchFlags(e.target.value)} />
                </div>
                <div className="md:col-span-3 flex flex-wrap items-center gap-2">
                  <Button type="button" disabled={createBenchBusy} onClick={() => void submitCreateBenchmark()}>
                    {createBenchBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                    Create
                  </Button>
                  {createBenchErr ? <span className="text-sm text-destructive">{createBenchErr}</span> : null}
                  {createBenchOk ? <span className="text-sm text-muted-foreground">{createBenchOk}</span> : null}
                </div>
              </CardContent>
            </Card>

            {selBench && benchId != null ? (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">
                    PATCH benchmark candidate{" "}
                    <code className="text-xs font-mono">
                      /knowledge/benchmark-dataset-candidates/{benchId}
                    </code>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
                    <div className="space-y-2">
                      <Label>status</Label>
                      <Select value={patchBenchStatus} onValueChange={setPatchBenchStatus}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {KNOWLEDGE_CANDIDATE_STATUSES.map((s) => (
                            <SelectItem key={s} value={s}>
                              {s}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>split_recommendation</Label>
                      <Select value={patchBenchSplit} onValueChange={setPatchBenchSplit}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {DATASET_SPLIT_RECOMMENDATIONS.map((s) => (
                            <SelectItem key={s} value={s}>
                              {s}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>leakage_risk_label</Label>
                      <Select value={patchBenchLeak} onValueChange={setPatchBenchLeak}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {LEAKAGE_RISK_LABELS.map((s) => (
                            <SelectItem key={s} value={s}>
                              {s}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2 md:col-span-4">
                      <Label htmlFor="pb-fl">quality_flags_json</Label>
                      <Textarea id="pb-fl" className="font-mono text-xs" rows={2} value={patchBenchFlags} onChange={(e) => setPatchBenchFlags(e.target.value)} />
                    </div>
                  </div>
                  <Button type="button" disabled={patchBenchBusy} onClick={() => void submitPatchBenchmark()}>
                    {patchBenchBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                    Save PATCH
                  </Button>
                  {patchBenchErr ? <p className="text-sm text-destructive">{patchBenchErr}</p> : null}
                  {patchBenchOk ? <p className="text-sm text-muted-foreground">{patchBenchOk}</p> : null}
                  <DeveloperJsonPanel data={selBench} />
                </CardContent>
              </Card>
            ) : null}
          </div>
        </ModuleCard>

        {/* 3. Dataset versions */}
        <ModuleCard
          accent="teal"
          eyebrow="Versions"
          title="3. Dataset versions"
          icon={GitBranch}
          description="Versioned snapshots of training and benchmark splits — each version locks candidate IDs into train, validation, test, and holdout partitions for reproducible model training."
        >
          <div className="space-y-4">
            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-2">
                <Label>status filter</Label>
                <Select value={filterVersionStatus || "__all"} onValueChange={(v) => setFilterVersionStatus(v === "__all" ? "" : v)}>
                  <SelectTrigger className="w-[220px]">
                    <SelectValue placeholder="All" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__all">All</SelectItem>
                    {DATASET_VERSION_STATUSES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {s}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <Card className="border-dashed">
              <CardHeader className="pb-2">
                <CardTitle className="text-base">POST dataset version</CardTitle>
                <CardDescription>
                  Populate <code className="text-xs">split_json</code> with keys <code className="text-xs">train</code>,{" "}
                  <code className="text-xs">validation</code>, <code className="text-xs">test</code>,{" "}
                  <code className="text-xs">holdout</code> (comma-separated candidate IDs per field).{" "}
                  <code className="text-xs">source_record_ids_json</code> is the deduplicated union of split IDs.
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-3 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="dv-name">name</Label>
                  <Input id="dv-name" value={dvName} onChange={(e) => setDvName(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>dataset_type</Label>
                  <Select value={dvDatasetType} onValueChange={setDvDatasetType}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {KNOWLEDGE_TRAINING_DATASET_TYPES.map((t) => (
                        <SelectItem key={t} value={t}>
                          {t}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="dv-ver">version</Label>
                  <Input id="dv-ver" className="font-mono" value={dvVersion} onChange={(e) => setDvVersion(e.target.value)} />
                </div>
                {SPLIT_KEYS.map((key) => (
                  <div key={key} className="space-y-2 md:col-span-2">
                    <Label htmlFor={`dv-${key}`}>
                      split_json · <code className="text-xs">{key}</code> (comma-separated candidate IDs)
                    </Label>
                    <Input
                      id={`dv-${key}`}
                      className="font-mono text-xs"
                      value={
                        key === "train"
                          ? dvTrainIds
                          : key === "validation"
                            ? dvValIds
                            : key === "test"
                              ? dvTestIds
                              : dvHoldoutIds
                      }
                      onChange={(e) => {
                        const v = e.target.value
                        if (key === "train") setDvTrainIds(v)
                        else if (key === "validation") setDvValIds(v)
                        else if (key === "test") setDvTestIds(v)
                        else setDvHoldoutIds(v)
                      }}
                    />
                  </div>
                ))}
                <div className="md:col-span-2 flex flex-wrap items-center gap-2">
                  <Button type="button" disabled={createDvBusy} onClick={() => void submitCreateDatasetVersion()}>
                    {createDvBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                    POST /knowledge/dataset-versions
                  </Button>
                  {createDvErr ? <span className="text-sm text-destructive">{createDvErr}</span> : null}
                  {createDvOk ? <span className="text-sm text-muted-foreground">{createDvOk}</span> : null}
                </div>
              </CardContent>
            </Card>

            {errVersions ? (
              <p className="text-sm text-muted-foreground">{errVersions}</p>
            ) : loading ? (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                Loading…
              </p>
            ) : (
              <div className="table-scroll min-w-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-[72px]">id</TableHead>
                      <TableHead>name</TableHead>
                      <TableHead>dataset_type</TableHead>
                      <TableHead>version</TableHead>
                      <TableHead>status</TableHead>
                      <TableHead className="text-right">source_record_ids_json</TableHead>
                      <TableHead>split_json</TableHead>
                      <TableHead>quality_summary_json</TableHead>
                      <TableHead>leakage_warnings_json</TableHead>
                      <TableHead>human_review_required</TableHead>
                      <TableHead>created_at</TableHead>
                      <TableHead className="w-[90px]">open</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {versions.map((row, idx) => {
                      const id = readRecordNumber(row, "id")
                      const src = row["source_record_ids_json"]
                      const srcLen = Array.isArray(src) ? src.length : 0
                      const sj = row["split_json"]
                      const splitKeys =
                        sj && typeof sj === "object" && !Array.isArray(sj)
                          ? Object.keys(sj as Record<string, unknown>)
                              .map((k) => {
                                const v = (sj as Record<string, unknown>)[k]
                                const n = Array.isArray(v) ? v.length : 0
                                return `${k}:${n}`
                              })
                              .join(" ")
                          : "—"
                      const qs = row["quality_summary_json"]
                      const qsHint =
                        qs && typeof qs === "object" && !Array.isArray(qs)
                          ? `${Object.keys(qs as Record<string, unknown>).length} keys`
                          : "—"
                      const lw = readStringList(row["leakage_warnings_json"]).length
                      return (
                        <TableRow key={id != null ? `dv-${id}` : `dv-${idx}`}>
                          <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                          <TableCell className="max-w-[160px] truncate text-sm">{readRecordString(row, "name") ?? "—"}</TableCell>
                          <TableCell className="font-mono text-xs">{readRecordString(row, "dataset_type") ?? "—"}</TableCell>
                          <TableCell className="font-mono text-xs">{readRecordString(row, "version") ?? "—"}</TableCell>
                          <TableCell>
                            <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
                          </TableCell>
                          <TableCell className="text-right tabular-nums text-xs">{srcLen}</TableCell>
                          <TableCell className="font-mono text-xs">{splitKeys}</TableCell>
                          <TableCell className="text-xs">{qsHint}</TableCell>
                          <TableCell className="text-right tabular-nums text-xs">{lw}</TableCell>
                          <TableCell className="font-mono text-xs">{readHumanReviewRequired(row)}</TableCell>
                          <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{formatWhen(readRecordString(row, "created_at"))}</TableCell>
                          <TableCell>
                            <Button
                              type="button"
                              size="sm"
                              variant={selVersion === row ? "secondary" : "outline"}
                              className="h-8"
                              onClick={() => setSelVersion(row)}
                            >
                              Open
                            </Button>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
                {versions.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No rows returned.</p> : null}
              </div>
            )}

            {selVersion && verId != null ? (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">
                    Dataset version{" "}
                    <code className="font-mono text-xs">
                      GET /knowledge/dataset-versions/{verId}
                    </code>
                  </CardTitle>
                  <CardDescription>
                    PATCH{" "}
                    <code className="text-xs">
                      /knowledge/dataset-versions/{verId}
                    </code>
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {versionDetailErr ? <p className="text-sm text-destructive">{versionDetailErr}</p> : null}
                  {versionDetailLoading ? (
                    <p className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                      Loading detail…
                    </p>
                  ) : versionDetail ? (
                    <div className="grid gap-2 text-sm">
                      <p>
                        <span className="text-muted-foreground">name · version · dataset_type · status</span>
                        <br />
                        {readRecordString(versionDetail, "name")} · {readRecordString(versionDetail, "version")} ·{" "}
                        {readRecordString(versionDetail, "dataset_type")} · {readRecordString(versionDetail, "status")}
                      </p>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">Detail not available.</p>
                  )}

                  <div className="grid gap-3 md:grid-cols-3">
                    <div className="space-y-2 md:col-span-3">
                      <Label htmlFor="pv-name">name</Label>
                      <Input id="pv-name" value={patchVName} onChange={(e) => setPatchVName(e.target.value)} />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="pv-ver">version</Label>
                      <Input id="pv-ver" className="font-mono" value={patchVVersion} onChange={(e) => setPatchVVersion(e.target.value)} />
                    </div>
                    <div className="space-y-2">
                      <Label>status</Label>
                      <Select value={patchVStatus} onValueChange={setPatchVStatus}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {DATASET_VERSION_STATUSES.map((s) => (
                            <SelectItem key={s} value={s}>
                              {s}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <Button type="button" disabled={patchVBusy} onClick={() => void submitPatchVersion()}>
                    {patchVBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                    Save PATCH
                  </Button>
                  {patchVErr ? <p className="text-sm text-destructive">{patchVErr}</p> : null}
                  {patchVOk ? <p className="text-sm text-muted-foreground">{patchVOk}</p> : null}

                  {versionDetail ? (
                    <>
                      <div className="space-y-1">
                        <p className="text-xs font-medium text-muted-foreground">split_json (structure only)</p>
                        <pre className="max-h-48 overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-[11px]">
                          {jsonPretty(versionDetail["split_json"])}
                        </pre>
                      </div>
                      <div className="space-y-1">
                        <p className="text-xs font-medium text-muted-foreground">source_record_ids_json</p>
                        <pre className="max-h-32 overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-[11px]">
                          {jsonPretty(versionDetail["source_record_ids_json"])}
                        </pre>
                      </div>
                      <DeveloperJsonPanel data={versionDetail} />
                    </>
                  ) : null}
                </CardContent>
              </Card>
            ) : null}
          </div>
        </ModuleCard>

        {/* 4. Leakage */}
        <ModuleCard
          accent="teal"
          eyebrow="Leakage"
          title="4. Leakage risk warnings"
          icon={ShieldAlert}
          description="Aggregated from benchmark leakage_risk_label and dataset version leakage_warnings_json (summaries only)."
        >
          <div className="space-y-4">
            <div className="flex flex-wrap gap-3">
              {(["low", "medium", "high", "unknown"] as const).map((k) => {
                const stripe =
                  k === "high"
                    ? "var(--mt-red)"
                    : k === "medium"
                      ? "var(--mt-amber)"
                      : k === "low"
                        ? "var(--mt-green)"
                        : "var(--mt-teal)"
                return (
                  <Card
                    key={k}
                    className="min-w-[140px] flex-1 overflow-hidden rounded-xl py-0"
                    style={{ borderTop: `3px solid ${stripe}` }}
                  >
                    <CardContent className="space-y-1 pt-5 pb-5">
                      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                        leakage_risk_label · {k}
                      </p>
                      <div
                        className="font-mono text-3xl font-bold tabular-nums leading-none"
                        style={{ color: stripe }}
                      >
                        {leakageAnalytics.counts[k] ?? 0}
                      </div>
                      <p className="text-xs text-muted-foreground">benchmark rows</p>
                    </CardContent>
                  </Card>
                )
              })}
            </div>
            {leakageAnalytics.warnings.length === 0 ? (
              <p className="text-sm text-muted-foreground">No leakage_warnings_json entries on loaded dataset versions.</p>
            ) : (
              <ul className="list-inside list-disc space-y-1 text-sm">
                {leakageAnalytics.warnings.map((w, i) => (
                  <li key={`${i}-${w.slice(0, 24)}`} title={w}>
                    {truncateSummary(w, 200)}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </ModuleCard>

        {/* 5. Quality */}
        <ModuleCard
          accent="teal"
          eyebrow="Quality"
          title="5. Quality flags"
          icon={BarChart3}
          description="Counts from training and benchmark quality_flags_json (flag strings only)."
        >
          <div>
            {qualityFlagAnalytics.length === 0 ? (
              <p className="text-sm text-muted-foreground">No quality flags on loaded candidates.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>flag</TableHead>
                    <TableHead className="text-right">count</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {qualityFlagAnalytics.map(([flag, count]) => (
                    <TableRow key={flag}>
                      <TableCell className="font-mono text-xs">{flag}</TableCell>
                      <TableCell className="text-right tabular-nums">{count}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        </ModuleCard>
      </div>
    </TooltipProvider>
  )
}

function jsonPretty(v: unknown): string {
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}
