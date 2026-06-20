"use client"

import Link from "next/link"
import { useCallback, useMemo, useState } from "react"
import { Atom } from "lucide-react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber as readRecordNumberField, readRecordString } from "@/components/projects/project-workspace-utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
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
import { trackBatchCreated, trackCompoundLinkedToReaction } from "@/src/lib/analytics/analytics-client"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function pickStr(row: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = readRecordString(row, k)
    if (v != null && String(v).trim() !== "") return String(v).trim()
  }
  return "—"
}

function readNum(row: Record<string, unknown>, key: string): number | undefined {
  return readRecordNumberField(row, key)
}

function normalizeCompoundSearchList(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord)
  if (isRecord(data)) {
    for (const k of ["compounds", "items", "results", "data", "rows"]) {
      const v = data[k]
      if (Array.isArray(v)) return v.filter(isRecord)
    }
  }
  return []
}

function compoundRowId(row: Record<string, unknown>): string | null {
  const n = readNum(row, "id")
  if (n != null) return String(n)
  const s = readRecordString(row, "id")?.trim()
  return s || null
}

function compoundRowLabel(row: Record<string, unknown>): string {
  const name = pickStr(row, ["preferred_name", "preferredName", "name"])
  const id = compoundRowId(row)
  if (id && name !== "—") return `${name} (${id})`
  return name
}

const LINK_ROLES = [
  { value: "target_product", label: "target product" },
  { value: "starting_material", label: "starting material" },
  { value: "product_intermediate", label: "product / intermediate" },
] as const

export type ReactionLinkRole = (typeof LINK_ROLES)[number]["value"]

function collectExperimentLinkHints(experiments: Record<string, unknown>[]): {
  targetIds: string[]
  startingLabels: string[]
  productLabels: string[]
  batchLabels: string[]
} {
  const targetIds = new Set<string>()
  const startingLabels = new Set<string>()
  const productLabels = new Set<string>()
  const batchLabels = new Set<string>()

  for (const e of experiments) {
    const tid =
      readNum(e, "linked_target_compound_id") ??
      readNum(e, "target_compound_id") ??
      readNum(e, "target_product_compound_id")
    if (tid != null) targetIds.add(String(tid))

    const sm = e.linked_starting_material_compound_ids ?? e.starting_material_compound_ids
    if (Array.isArray(sm)) {
      sm.forEach((x) => startingLabels.add(String(x)))
    }
    const sml = pickStr(e, ["linked_starting_materials_summary", "starting_materials_summary"])
    if (sml !== "—") startingLabels.add(sml)

    const pm = e.linked_product_compound_ids ?? e.product_intermediate_compound_ids
    if (Array.isArray(pm)) {
      pm.forEach((x) => productLabels.add(String(x)))
    }
    const pml = pickStr(e, ["linked_products_summary", "products_intermediates_summary"])
    if (pml !== "—") productLabels.add(pml)

    const st = String(e.status ?? "").toLowerCase()
    if (st === "completed") {
      const bc = pickStr(e, ["product_batch_code", "linked_batch_code", "batch_code", "output_batch_code"])
      if (bc !== "—") batchLabels.add(bc)
      const bid = readNum(e, "linked_product_batch_id") ?? readNum(e, "product_batch_id") ?? readNum(e, "batch_id")
      if (bid != null) batchLabels.add(`batch id ${bid}`)
    }
  }

  return {
    targetIds: [...targetIds],
    startingLabels: [...startingLabels],
    productLabels: [...productLabels],
    batchLabels: [...batchLabels],
  }
}

export function ReactionStudioCompoundLinkSummary({
  loading,
  project,
  experiments,
}: {
  loading: boolean
  project: Record<string, unknown> | null
  experiments: Record<string, unknown>[]
}) {
  const hints = useMemo(() => collectExperimentLinkHints(experiments), [experiments])
  const targetName = project ? pickStr(project, ["target_product_name", "targetProductName"]) : "—"
  const targetSmiles = project ? pickStr(project, ["target_product_smiles", "targetProductSmiles"]) : "—"
  const projTargetCompoundId =
    project != null
      ? readNum(project, "target_product_compound_id") ??
        readNum(project, "linked_target_compound_id") ??
        readNum(project, "target_compound_registry_id")
      : undefined

  const targetLine =
    hints.targetIds.length > 0
      ? hints.targetIds.join(" · ")
      : projTargetCompoundId != null
        ? `compound ${projTargetCompoundId}`
        : targetName !== "—"
          ? `${targetName}${targetSmiles !== "—" ? ` (${targetSmiles})` : ""}`
          : "—"

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Linked compounds (summary)</CardTitle>
        <CardDescription>
          Registry links and product batches are managed on the Evidence Links tab. Summaries below are parsed from
          project and experiment payloads when those fields are returned.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {loading ? <p className="text-muted-foreground">…</p> : null}
        {!loading ? (
          <>
            <p>
              <span className="text-muted-foreground">target product: </span>
              <span className="font-medium">{targetLine}</span>
            </p>
            <p>
              <span className="text-muted-foreground">linked starting materials: </span>
              <span>{hints.startingLabels.length > 0 ? hints.startingLabels.join(" · ") : "—"}</span>
            </p>
            <p>
              <span className="text-muted-foreground">linked products / intermediates: </span>
              <span>{hints.productLabels.length > 0 ? hints.productLabels.join(" · ") : "—"}</span>
            </p>
            <p>
              <span className="text-muted-foreground">batches (completed experiments): </span>
              <span>{hints.batchLabels.length > 0 ? hints.batchLabels.join(" · ") : "—"}</span>
            </p>
            <p className="text-xs text-muted-foreground">
              Open SpectraCheck evidence from the Evidence Links table — full analytical payloads are not copied here.
            </p>
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}

export function ReactionStudioCompoundLinkingPanel({
  loading,
  project,
  experiments,
  onRefresh,
}: {
  loading: boolean
  project: Record<string, unknown> | null
  experiments: Record<string, unknown>[]
  onRefresh: () => Promise<void>
}) {
  const [selectedExperimentId, setSelectedExperimentId] = useState("")
  const [searchQuery, setSearchQuery] = useState("")
  const [searchBusy, setSearchBusy] = useState(false)
  const [searchErr, setSearchErr] = useState("")
  const [searchHits, setSearchHits] = useState<Record<string, unknown>[]>([])
  const [selectedCompoundId, setSelectedCompoundId] = useState("")
  const [linkRole, setLinkRole] = useState<ReactionLinkRole>("target_product")
  const [linkBusy, setLinkBusy] = useState(false)
  const [linkErr, setLinkErr] = useState("")

  const [batchCode, setBatchCode] = useState("")
  const [batchCompoundId, setBatchCompoundId] = useState("")
  const [batchBusy, setBatchBusy] = useState(false)
  const [batchErr, setBatchErr] = useState("")

  const hints = useMemo(() => collectExperimentLinkHints(experiments), [experiments])
  const targetName = project ? pickStr(project, ["target_product_name", "targetProductName"]) : "—"

  const runCompoundSearch = useCallback(async () => {
    setSearchErr("")
    setSearchBusy(true)
    setSearchHits([])
    try {
      const body: Record<string, unknown> = {}
      const q = searchQuery.trim()
      if (q) body.name_alias = q
      const raw = await apiFetch<unknown>("/compound-registry/search", { method: "POST", body })
      setSearchHits(normalizeCompoundSearchList(raw))
    } catch (e) {
      setSearchErr(formatApiError(e, "Compound search failed."))
    } finally {
      setSearchBusy(false)
    }
  }, [searchQuery])

  async function handleLinkCompound() {
    const eid = selectedExperimentId.trim()
    if (!eid) {
      setLinkErr("Select an experiment.")
      return
    }
    const expId = Number.parseInt(eid, 10)
    if (!Number.isFinite(expId)) {
      setLinkErr("experiment_id must be a positive integer.")
      return
    }
    const cid = selectedCompoundId.trim()
    if (!cid) {
      setLinkErr("Select a compound from search results.")
      return
    }
    const compound_id = Number.parseInt(cid, 10)
    if (!Number.isFinite(compound_id)) {
      setLinkErr("compound_id must be a positive integer.")
      return
    }
    setLinkBusy(true)
    setLinkErr("")
    try {
      const body: Record<string, unknown> = {
        compound_id,
        link_role: linkRole,
      }
      const res = await apiFetch<Record<string, unknown>>(
        `/reaction-experiments/${encodeURIComponent(String(expId))}/link-compound`,
        { method: "POST", body },
      )
      const ev = isRecord(res.evidence_link) ? res.evidence_link : null
      const evCompoundId = ev ? readNum(ev, "compound_id") : undefined
      const evBatchId = ev ? readNum(ev, "batch_id") : undefined
      trackCompoundLinkedToReaction({
        compound_id: evCompoundId ?? compound_id,
        batch_id: evBatchId ?? undefined,
        has_batch: evBatchId != null,
        linked_resource_type: "reaction_experiment",
        status: ev ? readRecordString(ev, "status") ?? undefined : undefined,
      })
      await onRefresh()
    } catch (e) {
      setLinkErr(formatApiError(e, "Link compound failed."))
    } finally {
      setLinkBusy(false)
    }
  }

  async function handleCreateAndHintBatchLink() {
    const eid = selectedExperimentId.trim()
    const expId = Number.parseInt(eid, 10)
    const cid = batchCompoundId.trim() || selectedCompoundId.trim()
    const bc = batchCode.trim()
    if (!cid || !bc) {
      setBatchErr("batch compound id and batch_code are required.")
      return
    }
    const compound_id = Number.parseInt(cid, 10)
    if (!Number.isFinite(compound_id)) {
      setBatchErr("compound_id must be a positive integer.")
      return
    }
    if (!Number.isFinite(expId)) {
      setBatchErr("Select an experiment before creating a product batch link.")
      return
    }
    setBatchBusy(true)
    setBatchErr("")
    try {
      const created = await apiFetch<Record<string, unknown>>("/compound-registry/batches", {
        method: "POST",
        body: {
          compound_id,
          batch_code: bc,
          source_type: "synthesized",
          status: "active",
        },
      })
      const batchId = readNum(created, "id") ?? readNum(created, "batch_id")
      if (batchId == null) {
        setBatchErr("Batch created but response had no batch id — link batch manually when id is available.")
        await onRefresh()
        return
      }
      trackBatchCreated({
        compound_id,
        batch_id: batchId,
        source_type: "synthesized",
        status: "active",
        has_batch: true,
      })
      const linkRes = await apiFetch<Record<string, unknown>>(
        `/reaction-experiments/${encodeURIComponent(String(expId))}/link-compound`,
        {
          method: "POST",
          body: {
            compound_id,
            batch_id: batchId,
            link_role: "product_batch",
          },
        },
      )
      const ev = isRecord(linkRes.evidence_link) ? linkRes.evidence_link : null
      const evCompoundId = ev ? readNum(ev, "compound_id") : undefined
      const evBatchId = ev ? readNum(ev, "batch_id") : undefined
      trackCompoundLinkedToReaction({
        compound_id: evCompoundId ?? compound_id,
        batch_id: evBatchId ?? batchId,
        has_batch: true,
        linked_resource_type: "reaction_experiment",
        status: ev ? readRecordString(ev, "status") ?? undefined : undefined,
      })
      setBatchCode("")
      await onRefresh()
    } catch (e) {
      setBatchErr(formatApiError(e, "Create or link batch failed."))
    } finally {
      setBatchBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Linked compounds</CardTitle>
          <CardDescription>
            Registry compound links and material batches (summary). Use SpectraCheck or compound detail for full
            payloads.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {loading ? <p className="text-muted-foreground">…</p> : null}
          {!loading ? (
            <>
              <p>
                <span className="text-muted-foreground">target product (project): </span>
                <span className="font-medium">{targetName !== "—" ? targetName : "—"}</span>
              </p>
              <p>
                <span className="text-muted-foreground">linked starting materials: </span>
                {hints.startingLabels.length > 0 ? hints.startingLabels.join(" · ") : "—"}
              </p>
              <p>
                <span className="text-muted-foreground">linked products / intermediates: </span>
                {hints.productLabels.length > 0 ? hints.productLabels.join(" · ") : "—"}
              </p>
              <p>
                <span className="text-muted-foreground">batches (completed experiments): </span>
                {hints.batchLabels.length > 0 ? hints.batchLabels.join(" · ") : "—"}
              </p>
            </>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Link compound to experiment</CardTitle>
          <CardDescription>Select an experiment, search the registry, choose link role, then link.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="rs-exp">experiment</Label>
            <Select value={selectedExperimentId || "__none__"} onValueChange={(v) => setSelectedExperimentId(v === "__none__" ? "" : v)}>
              <SelectTrigger id="rs-exp">
                <SelectValue placeholder="experiment_id" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">—</SelectItem>
                {experiments
                  .filter((e) => readNum(e, "id") != null)
                  .map((e) => {
                    const id = readNum(e, "id")!
                    const code = pickStr(e, ["experiment_code", "experimentCode"])
                    return (
                      <SelectItem key={id} value={String(id)}>
                        {id} {code !== "—" ? `· ${code}` : ""}
                      </SelectItem>
                    )
                  })}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="min-w-0 flex-1 space-y-2">
              <Label htmlFor="rs-csearch">compound search</Label>
              <Input id="rs-csearch" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} placeholder="name/alias" />
            </div>
            <Button type="button" variant="secondary" size="sm" disabled={searchBusy} onClick={() => void runCompoundSearch()}>
              {searchBusy ? "Searching…" : "Search"}
            </Button>
          </div>
          {searchErr ? <p className="text-xs text-destructive">{searchErr}</p> : null}
          <div className="space-y-2">
            <Label htmlFor="rs-cpick">compound</Label>
            <Select value={selectedCompoundId || "__none__"} onValueChange={(v) => setSelectedCompoundId(v === "__none__" ? "" : v)}>
              <SelectTrigger id="rs-cpick">
                <SelectValue placeholder="Pick from search results" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">—</SelectItem>
                {searchHits.map((row) => {
                  const id = compoundRowId(row)
                  if (!id) return null
                  return (
                    <SelectItem key={id} value={id}>
                      {compoundRowLabel(row)}
                    </SelectItem>
                  )
                })}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="rs-role">link role</Label>
            <Select value={linkRole} onValueChange={(v) => setLinkRole(v as ReactionLinkRole)}>
              <SelectTrigger id="rs-role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LINK_ROLES.map((r) => (
                  <SelectItem key={r.value} value={r.value}>
                    {r.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {linkErr ? (
            <Alert variant="destructive">
              <AlertTitle className="text-sm">Link</AlertTitle>
              <AlertDescription className="text-xs">{linkErr}</AlertDescription>
            </Alert>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button type="button" disabled={linkBusy} onClick={() => void handleLinkCompound()}>
              {linkBusy ? "Linking…" : "Link compound to experiment"}
            </Button>
            {selectedCompoundId ? (
              <Button variant="outline" size="sm" asChild>
                <Link href={`/compounds/${encodeURIComponent(selectedCompoundId)}`}>Open compound detail</Link>
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Product batch from completed experiment</CardTitle>
          <CardDescription>
            Register a product batch in the compound registry and link it to the completed experiment with batch provenance context.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="rs-bcid">compound_id for batch (defaults to selected compound)</Label>
            <Input
              id="rs-bcid"
              value={batchCompoundId}
              onChange={(e) => setBatchCompoundId(e.target.value)}
              placeholder={selectedCompoundId || "compound_id"}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="rs-bcode">batch_code</Label>
            <Input id="rs-bcode" value={batchCode} onChange={(e) => setBatchCode(e.target.value)} />
          </div>
          {batchErr ? (
            <Alert variant="destructive">
              <AlertTitle className="text-sm">Batch</AlertTitle>
              <AlertDescription className="text-xs">{batchErr}</AlertDescription>
            </Alert>
          ) : null}
          <Button type="button" variant="outline" disabled={batchBusy} onClick={() => void handleCreateAndHintBatchLink()}>
            {batchBusy ? "Working…" : "Create batch and link to experiment"}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Experiment compound links (summary)</CardTitle>
        </CardHeader>
        <CardContent className="table-scroll">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>experiment_id</TableHead>
                <TableHead>code</TableHead>
                <TableHead>status</TableHead>
                <TableHead>link hints</TableHead>
                <TableHead>open</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {experiments
              .filter((e) => readNum(e, "id") != null)
              .map((e) => {
                const id = readNum(e, "id")!
                const parts: string[] = []
                const t = readNum(e, "linked_target_compound_id") ?? readNum(e, "target_compound_id")
                if (t != null) parts.push(`target ${t}`)
                const b = readNum(e, "linked_product_batch_id") ?? readNum(e, "product_batch_id")
                if (b != null) parts.push(`batch ${b}`)
                const hint = parts.length > 0 ? parts.join(" · ") : "—"
                const firstCompound =
                  readNum(e, "linked_target_compound_id") ??
                  readNum(e, "target_compound_id") ??
                  readNum(e, "linked_product_compound_id")
                const href = firstCompound != null ? `/compounds/${encodeURIComponent(String(firstCompound))}` : null
                return (
                  <TableRow key={String(id)}>
                    <TableCell className="font-mono text-xs">{id}</TableCell>
                    <TableCell className="font-mono text-xs">{pickStr(e, ["experiment_code", "experimentCode"])}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{pickStr(e, ["status", "state"])}</Badge>
                    </TableCell>
                    <TableCell className="max-w-[220px] text-xs text-muted-foreground">{hint}</TableCell>
                    <TableCell>
                      {href ? (
                        <Button variant="link" className="h-auto p-0 text-xs" asChild>
                          <Link href={href}>Open compound detail</Link>
                        </Button>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
              {!loading && experiments.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5}>
                    <Empty>
                      <EmptyHeader>
                        <EmptyMedia variant="icon">
                          <Atom />
                        </EmptyMedia>
                        <EmptyTitle>No experiments</EmptyTitle>
                        <EmptyDescription>
                          Experiments and their compound links appear here once added.
                        </EmptyDescription>
                      </EmptyHeader>
                    </Empty>
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
