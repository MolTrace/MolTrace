"use client"

import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import {
  KNOWLEDGE_BENCHMARK_TYPES,
  KNOWLEDGE_LINK_CONFIDENCE_LABELS,
  KNOWLEDGE_LINK_TARGET_TYPES,
  KNOWLEDGE_TRAINING_DATASET_TYPES,
  knowledgeLabel,
} from "@/components/knowledge/knowledge-constants"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ModuleCard } from "@/components/dashboard/module-card"
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
import { AlertTriangle, ArrowLeft, ClipboardCheck, Database, ListChecks, Loader2 } from "lucide-react"

export type KnowledgeRecordKind = "reaction" | "analytical" | "regulatory"

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

function readIntList(v: unknown): number[] {
  if (!Array.isArray(v)) return []
  return v.filter((x): x is number => typeof x === "number" && Number.isFinite(x))
}

function readStringList(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.filter((x): x is string => typeof x === "string" && x.trim().length > 0)
}

function jsonPretty(v: unknown): string {
  try {
    return JSON.stringify(v, null, 2)
  } catch {
    return String(v)
  }
}

function endpointPath(kind: KnowledgeRecordKind, runId: number): string {
  const seg =
    kind === "reaction" ? "reactions" : kind === "analytical" ? "analytical" : "regulatory"
  return `/knowledge/extractions/${runId}/${seg}`
}

function recordTypePayload(kind: KnowledgeRecordKind): "reaction" | "analytical" | "regulatory" {
  return kind
}

function pageHeading(kind: KnowledgeRecordKind): string {
  if (kind === "reaction") return "Reaction extraction records"
  if (kind === "analytical") return "Analytical extraction records"
  return "Regulatory extraction records"
}

export function KnowledgeExtractionRecordsWorkspace({ recordKind }: { recordKind: KnowledgeRecordKind }) {
  const searchParams = useSearchParams()
  const qRun = searchParams.get("run_id")

  const [runIdInput, setRunIdInput] = useState("")
  const [rows, setRows] = useState<Record<string, unknown>[]>([])
  const [loading, setLoading] = useState(false)
  const [loadErr, setLoadErr] = useState("")

  const [selected, setSelected] = useState<Record<string, unknown> | null>(null)

  const [reviewerName, setReviewerName] = useState("")
  const [reviewerComment, setReviewerComment] = useState("")
  const [busyApprove, setBusyApprove] = useState(false)
  const [busyReject, setBusyReject] = useState(false)
  const [actionErr, setActionErr] = useState("")
  const [actionOk, setActionOk] = useState("")

  const [linkTargetType, setLinkTargetType] = useState<string>("compound")
  const [linkTargetId, setLinkTargetId] = useState("")
  const [linkRelation, setLinkRelation] = useState("linked_to")
  const [linkConfidence, setLinkConfidence] = useState<string>("requires_review")
  const [busyLink, setBusyLink] = useState(false)

  const [trainDatasetType, setTrainDatasetType] = useState<string>("reaction_optimization")
  const [busyTrain, setBusyTrain] = useState(false)

  const [benchType, setBenchType] = useState<string>("reaction_optimization")
  const [busyBench, setBusyBench] = useState(false)

  useEffect(() => {
    if (qRun && /^\d+$/.test(qRun)) setRunIdInput(qRun)
  }, [qRun])

  const rtPayload = useMemo(() => recordTypePayload(recordKind), [recordKind])

  const loadRecords = useCallback(async () => {
    const n = Number.parseInt(runIdInput.trim(), 10)
    if (!Number.isFinite(n) || n < 1) {
      setLoadErr("Enter an extraction run ID as a positive whole number.")
      return
    }
    setLoading(true)
    setLoadErr("")
    try {
      const raw = await apiFetch<unknown>(endpointPath(recordKind, n), { method: "GET" })
      setRows(asArray(raw).filter(isRecord) as Record<string, unknown>[])
      setSelected(null)
    } catch (e) {
      setRows([])
      setLoadErr(formatApiError(e, "Could not load extraction records."))
    } finally {
      setLoading(false)
    }
  }, [runIdInput, recordKind])

  const selectedId = selected ? readRecordNumber(selected, "id") : null
  const reviewStatus = selected ? readRecordString(selected, "review_status") ?? "" : ""
  const citationIds = selected ? readIntList(selected["citation_ids_json"]) : []
  const citationMissing = selected != null && citationIds.length === 0
  const warningLines = selected ? readStringList(selected["warnings_json"]) : []
  const noteLines = selected ? readStringList(selected["notes_json"]) : []

  async function refreshAfterAction() {
    await loadRecords()
    setSelected(null)
    setActionErr("")
  }

  async function submitApprove() {
    if (selectedId == null || !selected) return
    const name = reviewerName.trim()
    const comment = reviewerComment.trim()
    if (!name || !comment) {
      setActionErr("Reviewer name and comment are required for approval.")
      return
    }
    setActionErr("")
    setActionOk("")
    setBusyApprove(true)
    try {
      await apiFetch(`/knowledge/records/${selectedId}/approve`, {
        method: "POST",
        body: {
          record_type: rtPayload,
          reviewer_name: name,
          reviewer_comment: comment,
          metadata_json: {},
        },
      })
      setActionOk("Record approved.")
      setReviewerComment("")
      await refreshAfterAction()
    } catch (e) {
      setActionErr(formatApiError(e, "Could not approve the record."))
    } finally {
      setBusyApprove(false)
    }
  }

  async function submitReject() {
    if (selectedId == null || !selected) return
    const name = reviewerName.trim()
    const comment = reviewerComment.trim()
    if (!name || !comment) {
      setActionErr("Reviewer name and comment are required for rejection.")
      return
    }
    setActionErr("")
    setActionOk("")
    setBusyReject(true)
    try {
      await apiFetch(`/knowledge/records/${selectedId}/reject`, {
        method: "POST",
        body: {
          record_type: rtPayload,
          reviewer_name: name,
          reviewer_comment: comment,
          metadata_json: {},
        },
      })
      setActionOk("Record rejected (audit trail retained).")
      setReviewerComment("")
      await refreshAfterAction()
    } catch (e) {
      setActionErr(formatApiError(e, "Could not reject the record."))
    } finally {
      setBusyReject(false)
    }
  }

  async function submitLink() {
    if (selectedId == null || !selected) return
    if (reviewStatus !== "accepted") {
      setActionErr("Linking requires an accepted review status; approve the record first.")
      return
    }
    const rel = linkRelation.trim()
    if (!rel) {
      setActionErr("A relationship is required.")
      return
    }
    const tidRaw = linkTargetId.trim()
    if (!tidRaw) {
      setActionErr("A target ID is required.")
      return
    }
    let target_id: string | number = tidRaw
    if (/^\d+$/.test(tidRaw)) target_id = Number.parseInt(tidRaw, 10)
    setActionErr("")
    setActionOk("")
    setBusyLink(true)
    try {
      await apiFetch(`/knowledge/records/${selectedId}/link`, {
        method: "POST",
        body: {
          record_type: rtPayload,
          target_type: linkTargetType,
          target_id,
          relation_type: rel,
          confidence_label: linkConfidence,
          metadata_json: {},
        },
      })
      setActionOk("Link created.")
    } catch (e) {
      setActionErr(formatApiError(e, "Could not create the link."))
    } finally {
      setBusyLink(false)
    }
  }

  async function submitTrainingCandidate() {
    if (selectedId == null || !selected) return
    const sid = readRecordNumber(selected, "source_id")
    setActionErr("")
    setActionOk("")
    setBusyTrain(true)
    try {
      await apiFetch("/knowledge/training-dataset-candidates", {
        method: "POST",
        body: {
          source_id: sid != null ? sid : undefined,
          record_type: rtPayload,
          record_id: selectedId,
          dataset_type: trainDatasetType,
          status: "proposed",
          quality_flags_json: [],
          citation_ids_json: citationIds,
          metadata_json: {},
        },
      })
      setActionOk("Training dataset candidate created.")
    } catch (e) {
      setActionErr(formatApiError(e, "Could not create the training candidate."))
    } finally {
      setBusyTrain(false)
    }
  }

  async function submitBenchmarkCandidate() {
    if (selectedId == null || !selected) return
    const sid = readRecordNumber(selected, "source_id")
    setActionErr("")
    setActionOk("")
    setBusyBench(true)
    try {
      await apiFetch("/knowledge/benchmark-dataset-candidates", {
        method: "POST",
        body: {
          source_id: sid != null ? sid : undefined,
          record_type: rtPayload,
          record_id: selectedId,
          benchmark_type: benchType,
          status: "proposed",
          split_recommendation: "unknown",
          leakage_risk_label: "unknown",
          quality_flags_json: [],
          metadata_json: {},
        },
      })
      setActionOk("Benchmark dataset candidate created.")
    } catch (e) {
      setActionErr(formatApiError(e, "Could not create the benchmark candidate."))
    } finally {
      setBusyBench(false)
    }
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/knowledge">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Knowledge Library
          </Link>
        </Button>
        {/* These three are NOT sibling navigation and must not be removed with it.
            This component serves /knowledge/reactions, /knowledge/analytical and
            /knowledge/regulatory from one file, switched by the `recordKind`
            prop, so this row is the page's only control for changing which kind
            of record you are looking at. The `secondary` variant marks the
            current one. The plain links that used to sit beside them — pointing
            back at Extractions and Review tasks — were duplicating the Knowledge
            Library landing nav and have gone. */}
        <Button variant={recordKind === "reaction" ? "secondary" : "outline"} size="sm" asChild>
          <Link href="/knowledge/reactions">Reactions</Link>
        </Button>
        <Button variant={recordKind === "analytical" ? "secondary" : "outline"} size="sm" asChild>
          <Link href="/knowledge/analytical">Analytical</Link>
        </Button>
        <Button variant={recordKind === "regulatory" ? "secondary" : "outline"} size="sm" asChild>
          <Link href="/knowledge/regulatory">Regulatory</Link>
        </Button>
      </div>

      <div className="space-y-1">
        <p
          className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
          style={{ color: "var(--mt-amber)" }}
        >
          MolTrace · Knowledge · {recordKind === "reaction" ? "Reaction" : recordKind === "analytical" ? "Analytical" : "Regulatory"} Records
        </p>
        <h1 className="font-mono text-2xl font-bold tracking-tight">{pageHeading(recordKind)}</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Review machine-extracted fields before accepting them for downstream use. Extracted values are not validated as correct until review completes.
        </p>
      </div>

      <Alert>
        <AlertTriangle className="h-4 w-4" aria-hidden />
        <AlertTitle className="text-sm">Unverified extraction</AlertTitle>
        <AlertDescription className="text-sm text-muted-foreground">
          Do not treat extracted structures, NMR text, or regulatory language as authoritative until a qualified
          reviewer accepts the record.
        </AlertDescription>
      </Alert>

      <ModuleCard
        accent="teal"
        eyebrow="Load"
        title="Load records by extraction run"
        icon={Database}
        description={`Enter the extraction run ID to list its ${
          recordKind === "reaction" ? "reaction" : recordKind === "analytical" ? "analytical" : "regulatory"
        } records.`}
      >
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-2">
            <Label htmlFor="k-run-id">Extraction run ID</Label>
            <Input
              id="k-run-id"
              className="w-[140px] font-mono"
              value={runIdInput}
              onChange={(e) => setRunIdInput(e.target.value)}
              placeholder="e.g. 1"
              autoComplete="off"
            />
          </div>
          <Button type="button" disabled={loading} onClick={() => void loadRecords()}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
            Load
          </Button>
        </div>
      </ModuleCard>

      {loadErr ? (
        <Alert variant="destructive">
          <AlertDescription className="text-sm">{loadErr}</AlertDescription>
        </Alert>
      ) : null}

      <ModuleCard
        accent="teal"
        eyebrow="Records"
        title="Records"
        icon={ListChecks}
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No records loaded. Enter an extraction run ID, then choose Load.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">ID</TableHead>
                  {recordKind === "reaction" ? (
                    <>
                      <TableHead>Reaction type</TableHead>
                      <TableHead>Substrate</TableHead>
                      <TableHead>Product</TableHead>
                      <TableHead className="text-right">Yield (%)</TableHead>
                    </>
                  ) : null}
                  {recordKind === "analytical" ? (
                    <>
                      <TableHead>Compound</TableHead>
                      <TableHead>Formula</TableHead>
                      <TableHead className="text-right">Exact mass</TableHead>
                    </>
                  ) : null}
                  {recordKind === "regulatory" ? (
                    <>
                      <TableHead>Topic</TableHead>
                      <TableHead className="max-w-[200px]">Requirement</TableHead>
                    </>
                  ) : null}
                  <TableHead>Citations</TableHead>
                  <TableHead>Review status</TableHead>
                  <TableHead className="w-[90px]">Open</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  const cit = readIntList(row["citation_ids_json"]).length
                  const rs = knowledgeLabel(readRecordString(row, "review_status"))
                  return (
                    <TableRow key={id != null ? `row-${id}` : `row-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      {recordKind === "reaction" ? (
                        <>
                          <TableCell className="text-xs">{readRecordString(row, "reaction_type") ?? "—"}</TableCell>
                          <TableCell className="max-w-[140px] truncate text-xs">
                            {readRecordString(row, "substrate_summary") ?? "—"}
                          </TableCell>
                          <TableCell className="max-w-[140px] truncate text-xs">
                            {readRecordString(row, "product_summary") ?? "—"}
                          </TableCell>
                          <TableCell className="text-right font-mono text-xs">
                            {typeof row["yield_percent"] === "number" ? row["yield_percent"] : "—"}
                          </TableCell>
                        </>
                      ) : null}
                      {recordKind === "analytical" ? (
                        <>
                          <TableCell className="max-w-[160px] truncate text-sm">
                            {readRecordString(row, "compound_name") ?? "—"}
                          </TableCell>
                          <TableCell className="font-mono text-xs">{readRecordString(row, "formula") ?? "—"}</TableCell>
                          <TableCell className="text-right font-mono text-xs">
                            {typeof row["exact_mass"] === "number" ? row["exact_mass"] : "—"}
                          </TableCell>
                        </>
                      ) : null}
                      {recordKind === "regulatory" ? (
                        <>
                          <TableCell className="font-mono text-xs">{readRecordString(row, "topic") ?? "—"}</TableCell>
                          <TableCell className="max-w-[220px] truncate text-xs">
                            {readRecordString(row, "requirement_text") ?? "—"}
                          </TableCell>
                        </>
                      ) : null}
                      <TableCell className="tabular-nums text-xs">
                        {cit === 0 ? (
                          <Badge variant="destructive" className="font-mono">
                            0
                          </Badge>
                        ) : (
                          cit
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{rs}</Badge>
                      </TableCell>
                      <TableCell>
                        {id != null ? (
                          <Button
                            type="button"
                            size="sm"
                            variant={selectedId === id ? "secondary" : "outline"}
                            className="h-8"
                            onClick={() => setSelected(row)}
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
        </div>
      </ModuleCard>

      {selected ? (
        <ModuleCard
          accent="teal"
          eyebrow="Detail"
          title="Record detail & review"
          icon={ClipboardCheck}
          description="Extracted values are shown read-only; approval requires reviewer identity and a comment."
        >
          <div className="space-y-4">
            {citationMissing ? (
              <Alert variant="destructive">
                <AlertTitle className="text-sm">Citation missing</AlertTitle>
                <AlertDescription className="text-sm">
                  No citations are attached — verify provenance before accepting this record.
                </AlertDescription>
              </Alert>
            ) : null}

            {warningLines.length > 0 ? (
              <Alert variant="destructive">
                <AlertTitle className="text-sm">Extraction warnings</AlertTitle>
                <AlertDescription>
                  <ul className="list-inside list-disc text-sm">
                    {warningLines.map((w, i) => (
                      <li key={`${i}-${w.slice(0, 80)}`}>{w}</li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            ) : null}

            {noteLines.length > 0 ? (
              <Alert>
                <AlertTitle className="text-sm">Extraction notes</AlertTitle>
                <AlertDescription>
                  <ul className="list-inside list-disc text-sm">
                    {noteLines.map((n, i) => (
                      <li key={`${i}-${n.slice(0, 80)}`}>{n}</li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            ) : null}

            {recordKind === "reaction" && selected ? (
              <div className="grid gap-3 md:grid-cols-2">
                <DetailKV label="Reaction name" value={readRecordString(selected, "reaction_name")} />
                <DetailKV label="Reaction type" value={readRecordString(selected, "reaction_type")} />
                <DetailKV label="Review status" value={knowledgeLabel(readRecordString(selected, "review_status"))} />
                <DetailKV label="Substrate" value={readRecordString(selected, "substrate_summary")} wide />
                <DetailKV label="Product" value={readRecordString(selected, "product_summary")} wide />
                <DetailBlock label="Product SMILES" mono value={readRecordString(selected, "product_smiles")} />
                <DetailKV
                  label="Conditions"
                  value={[
                    typeof selected["temperature_c"] === "number" ? `Temperature: ${selected["temperature_c"]} °C` : null,
                    typeof selected["time_h"] === "number" ? `Time: ${selected["time_h"]} h` : null,
                    readRecordString(selected, "concentration") ? `Concentration: ${readRecordString(selected, "concentration")}` : null,
                    readRecordString(selected, "scale") ? `Scale: ${readRecordString(selected, "scale")}` : null,
                  ]
                    .filter(Boolean)
                    .join(" · ") || "—"}
                  wide
                />
                <DetailKV
                  label="Yield / conversion / selectivity / ee (%)"
                  value={`${typeof selected["yield_percent"] === "number" ? selected["yield_percent"] : "—"} / ${typeof selected["conversion_percent"] === "number" ? selected["conversion_percent"] : "—"} / ${typeof selected["selectivity_percent"] === "number" ? selected["selectivity_percent"] : "—"} / ${typeof selected["ee_percent"] === "number" ? selected["ee_percent"] : "—"}`}
                  wide
                />
                <DetailKV label="Impurities" value={readRecordString(selected, "impurity_summary")} wide />
                <DetailKV
                  label="Confidence score"
                  value={
                    typeof selected["confidence_score"] === "number" ? String(selected["confidence_score"]) : "—"
                  }
                />
                <DetailKV
                  label="Citation IDs"
                  value={readIntList(selected["citation_ids_json"]).join(", ") || "—"}
                  wide
                />
                <div className="md:col-span-2">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Reagents</p>
                  <pre className="max-h-32 overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-[11px] leading-relaxed">
                    {jsonPretty(selected["reagent_json"])}
                  </pre>
                </div>
                <div className="md:col-span-2">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Solvents</p>
                  <pre className="max-h-32 overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-[11px] leading-relaxed">
                    {jsonPretty(selected["solvent_json"])}
                  </pre>
                </div>
                <div className="md:col-span-2">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Catalysts</p>
                  <pre className="max-h-28 overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-[11px] leading-relaxed">
                    {jsonPretty(selected["catalyst_json"])}
                  </pre>
                </div>
                <div className="md:col-span-2">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Ligands</p>
                  <pre className="max-h-28 overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-[11px] leading-relaxed">
                    {jsonPretty(selected["ligand_json"])}
                  </pre>
                </div>
                <div className="md:col-span-2">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Bases</p>
                  <pre className="max-h-28 overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-[11px] leading-relaxed">
                    {jsonPretty(selected["base_json"])}
                  </pre>
                </div>
                <div className="md:col-span-2">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Additives</p>
                  <pre className="max-h-28 overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-[11px] leading-relaxed">
                    {jsonPretty(selected["additive_json"])}
                  </pre>
                </div>
                <div className="md:col-span-2">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Reaction conditions</p>
                  <pre className="max-h-40 overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-[11px] leading-relaxed">
                    {jsonPretty(selected["conditions_json"])}
                  </pre>
                </div>
                <div className="md:col-span-2">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Reaction outcome</p>
                  <pre className="max-h-36 overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-[11px] leading-relaxed">
                    {jsonPretty(selected["outcome_json"])}
                  </pre>
                </div>
              </div>
            ) : null}

            {recordKind === "analytical" && selected ? (
              <div className="grid gap-3 md:grid-cols-2">
                <DetailKV label="Compound name" value={readRecordString(selected, "compound_name")} wide />
                <DetailKV label="Review status" value={knowledgeLabel(readRecordString(selected, "review_status"))} />
                <DetailBlock label="Structure input" mono value={readRecordString(selected, "structure_input")} />
                <DetailKV label="Structure format" value={readRecordString(selected, "structure_format")} />
                <DetailKV label="Formula" value={readRecordString(selected, "formula")} />
                <DetailKV
                  label="Exact mass"
                  value={typeof selected["exact_mass"] === "number" ? String(selected["exact_mass"]) : "—"}
                />
                <DetailKV label="Solvent" value={readRecordString(selected, "solvent")} />
                <DetailKV
                  label="Frequency (MHz)"
                  value={typeof selected["frequency_mhz"] === "number" ? String(selected["frequency_mhz"]) : "—"}
                />
                <DetailKV
                  label="Confidence score"
                  value={
                    typeof selected["confidence_score"] === "number" ? String(selected["confidence_score"]) : "—"
                  }
                />
                <DetailKV
                  label="Citation IDs"
                  value={readIntList(selected["citation_ids_json"]).join(", ") || "—"}
                  wide
                />
                <DetailKV label="Analytical method" value={readRecordString(selected, "analytical_method")} wide />
                <div className="md:col-span-2">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">1H NMR</p>
                  <pre className="max-h-36 overflow-auto whitespace-pre-wrap rounded-md border bg-muted/30 p-3 font-mono text-[11px]">
                    {readRecordString(selected, "nmr_1h_text") ?? "—"}
                  </pre>
                </div>
                <div className="md:col-span-2">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">13C NMR</p>
                  <pre className="max-h-36 overflow-auto whitespace-pre-wrap rounded-md border bg-muted/30 p-3 font-mono text-[11px]">
                    {readRecordString(selected, "nmr_13c_text") ?? "—"}
                  </pre>
                </div>
                <div className="md:col-span-2">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">HRMS</p>
                  <pre className="max-h-28 overflow-auto whitespace-pre-wrap rounded-md border bg-muted/30 p-3 font-mono text-[11px]">
                    {readRecordString(selected, "hrms_text") ?? "—"}
                  </pre>
                </div>
                <div className="md:col-span-2">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">MS/MS summary</p>
                  <pre className="max-h-28 overflow-auto whitespace-pre-wrap rounded-md border bg-muted/30 p-3 font-mono text-[11px]">
                    {readRecordString(selected, "msms_summary") ?? "—"}
                  </pre>
                </div>
                <div className="md:col-span-2">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">2D NMR summary</p>
                  <pre className="max-h-28 overflow-auto whitespace-pre-wrap rounded-md border bg-muted/30 p-3 font-mono text-[11px]">
                    {readRecordString(selected, "nmr_2d_summary") ?? "—"}
                  </pre>
                </div>
              </div>
            ) : null}

            {recordKind === "regulatory" && selected ? (
              <div className="grid gap-3 md:grid-cols-2">
                <DetailKV
                  label="Topic"
                  value={readRecordString(selected, "topic") ?? (typeof selected["topic"] === "string" ? selected["topic"] : undefined)}
                />
                <DetailKV label="Review status" value={knowledgeLabel(readRecordString(selected, "review_status"))} />
                <DetailKV
                  label="Jurisdiction ID"
                  value={
                    typeof selected["jurisdiction_id"] === "number" ? String(selected["jurisdiction_id"]) : "—"
                  }
                />
                <div className="md:col-span-2">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Requirement text</p>
                  <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-md border bg-muted/30 p-3 text-sm">
                    {readRecordString(selected, "requirement_text") ?? "—"}
                  </pre>
                </div>
                <div className="md:col-span-2">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Threshold summary</p>
                  <pre className="max-h-36 overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-[11px]">
                    {jsonPretty(selected.threshold_summary_json)}
                  </pre>
                </div>
                <div className="md:col-span-2">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Rule candidate</p>
                  <pre className="max-h-36 overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-[11px]">
                    {jsonPretty(selected.rule_candidate_json)}
                  </pre>
                </div>
                <div className="md:col-span-2">
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Action candidate</p>
                  <pre className="max-h-36 overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-[11px]">
                    {jsonPretty(selected.action_candidate_json)}
                  </pre>
                </div>
                <DetailKV
                  label="Confidence score"
                  value={
                    typeof selected["confidence_score"] === "number" ? String(selected["confidence_score"]) : "—"
                  }
                />
                <DetailKV
                  label="Citation IDs"
                  value={readIntList(selected["citation_ids_json"]).join(", ") || "—"}
                  wide
                />
              </div>
            ) : null}

            <div className="space-y-2 border-t pt-4">
              <Label htmlFor="kr-reviewer">Reviewer name</Label>
              <Input
                id="kr-reviewer"
                value={reviewerName}
                onChange={(e) => setReviewerName(e.target.value)}
                autoComplete="name"
              />
              <Label htmlFor="kr-comment">Reviewer comment</Label>
              <Textarea
                id="kr-comment"
                value={reviewerComment}
                onChange={(e) => setReviewerComment(e.target.value)}
                rows={3}
              />
              {actionErr ? (
                <Alert variant="destructive">
                  <AlertDescription className="text-sm">{actionErr}</AlertDescription>
                </Alert>
              ) : null}
              {actionOk ? (
                <Alert>
                  <AlertDescription className="text-sm">{actionOk}</AlertDescription>
                </Alert>
              ) : null}
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="default" disabled={busyApprove} onClick={() => void submitApprove()}>
                  {busyApprove ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                  Approve
                </Button>
                <Button type="button" variant="destructive" disabled={busyReject} onClick={() => void submitReject()}>
                  {busyReject ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                  Reject
                </Button>
              </div>
            </div>

            <div className="space-y-3 border-t pt-4">
              <p className="text-sm font-medium">Link to a related record</p>
              <p className="text-xs text-muted-foreground">
                Attach this extracted record to a project, sample, compound, or batch. Available once review status is <strong>accepted</strong>.
              </p>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-2">
                  <Label>Target type</Label>
                  <Select value={linkTargetType} onValueChange={setLinkTargetType}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {KNOWLEDGE_LINK_TARGET_TYPES.map((t) => (
                        <SelectItem key={t} value={t}>
                          {knowledgeLabel(t)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="link-tid">Target ID</Label>
                  <Input
                    id="link-tid"
                    value={linkTargetId}
                    onChange={(e) => setLinkTargetId(e.target.value)}
                    placeholder="Numeric or text ID"
                    className="font-mono text-sm"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="link-rel">Relationship</Label>
                  <Input id="link-rel" value={linkRelation} onChange={(e) => setLinkRelation(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Confidence</Label>
                  <Select value={linkConfidence} onValueChange={setLinkConfidence}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {KNOWLEDGE_LINK_CONFIDENCE_LABELS.map((c) => (
                        <SelectItem key={c} value={c}>
                          {knowledgeLabel(c)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <Button type="button" variant="outline" disabled={busyLink} onClick={() => void submitLink()}>
                {busyLink ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                Create link
              </Button>
            </div>

            <div className="grid gap-4 border-t pt-4 md:grid-cols-2">
              <div className="space-y-2">
                <p className="text-sm font-medium">Training dataset candidate</p>
                <Select value={trainDatasetType} onValueChange={setTrainDatasetType}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {KNOWLEDGE_TRAINING_DATASET_TYPES.map((t) => (
                      <SelectItem key={t} value={t}>
                        {knowledgeLabel(t)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button type="button" variant="secondary" size="sm" disabled={busyTrain} onClick={() => void submitTrainingCandidate()}>
                  {busyTrain ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                  Create training candidate
                </Button>
                <p className="text-xs text-muted-foreground">
                  Adds this record to the training pool.
                </p>
              </div>
              <div className="space-y-2">
                <p className="text-sm font-medium">Benchmark dataset candidate</p>
                <Select value={benchType} onValueChange={setBenchType}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {KNOWLEDGE_BENCHMARK_TYPES.map((t) => (
                      <SelectItem key={t} value={t}>
                        {knowledgeLabel(t)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button type="button" variant="secondary" size="sm" disabled={busyBench} onClick={() => void submitBenchmarkCandidate()}>
                  {busyBench ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                  Create benchmark candidate
                </Button>
                <p className="text-xs text-muted-foreground">
                  Holds this record out for model evaluation.
                </p>
              </div>
            </div>

            <DeveloperJsonPanel data={selected} />
          </div>
        </ModuleCard>
      ) : null}
    </div>
  )
}

function DetailKV({
  label,
  value,
  wide,
}: {
  label: string
  value: string | undefined | null
  wide?: boolean
}) {
  const text = value != null && String(value).trim() !== "" ? String(value) : "—"
  return (
    <div className={wide ? "md:col-span-2" : ""}>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="text-sm">{text}</p>
    </div>
  )
}

function DetailBlock({
  label,
  value,
  mono,
  wide,
}: {
  label: string
  value: string | undefined | null
  mono?: boolean
  wide?: boolean
}) {
  const text = value != null && String(value).trim() !== "" ? String(value) : "—"
  return (
    <div className={wide ? "md:col-span-2" : ""}>
      <p className="mb-1 text-xs font-medium text-muted-foreground">{label}</p>
      <pre
        className={`max-h-32 overflow-auto rounded-md border bg-muted/30 p-3 text-sm ${mono ? "font-mono text-[11px]" : ""}`}
      >
        {text}
      </pre>
    </div>
  )
}
