"use client"

import { FormEvent, type ReactNode, useEffect, useRef, useState } from "react"
import { useOptionalSpectraCheckWorkspaceSession } from "@/components/spectracheck/spectracheck-workspace-session-context"
import { apiFetch } from "@/lib/api/client"
import { AnalysisJobTimeline } from "@/src/components/spectracheck/AnalysisJobTimeline"
import { buildAnalysisJobPayload } from "@/src/lib/spectracheck/buildAnalysisJobPayload"
import { normalizeSessionFileRecord } from "@/src/lib/spectracheck/session-file-record"
import { useAnalysisJob } from "@/src/lib/spectracheck/useAnalysisJob"
import { trackFileUploaded } from "@/src/lib/analytics/analytics-client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { cn } from "@/lib/utils"
import { TabResultSection } from "@/components/spectracheck/spectracheck-result-panels"

const DEFAULT_MS1_PEAKS = "m/z,intensity\n47.04914,100\n48.05249,2.3\n69.03109,24\n"

const DEFAULT_MSMS_PEAKS = "m/z,intensity\n47.04914,10\n29.03858,100\n31.01839,25\n"

const HRMS_ADDUCT_OPTIONS = [
  "[M+H]+",
  "[M+Na]+",
  "[M+K]+",
  "[M+NH4]+",
  "[M-H]-",
  "[M+Cl]-",
  "[M+FA-H]-",
  "[M+Ac-H]-",
  "M",
] as const

const ION_MODE_OPTIONS: { value: string; label: string }[] = [
  { value: "auto", label: "auto" },
  { value: "positive", label: "positive" },
  { value: "negative", label: "negative" },
  { value: "neutral", label: "neutral" },
]

const ADDUCT_INFERENCE_ION_MODE_OPTIONS: { value: string; label: string }[] = [
  { value: "auto", label: "auto" },
  { value: "positive", label: "positive" },
  { value: "negative", label: "negative" },
]

const LC_MS_UPLOAD_ACCEPT = ".mzML,.mzXML,.xml,.csv,.tsv,.txt"

/** Matches SpectraCheck `tabTriggerClass`: outer `TabsTrigger` owns active teal-coded highlight; tooltip wraps label span only. */
const MS_EVIDENCE_TABS_TRIGGER_CLASS = cn(
  "shrink-0 whitespace-normal text-left text-xs sm:text-sm sm:text-center sm:whitespace-nowrap",
  "font-mono",
  "data-[state=active]:[background-color:var(--mt-teal)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm",
  "data-[state=inactive]:text-muted-foreground",
)

function MsEvidenceTabWithTooltip({
  value,
  tooltip,
  children,
}: {
  value: string
  tooltip: string
  children: ReactNode
}) {
  return (
    <TabsTrigger className={MS_EVIDENCE_TABS_TRIGGER_CLASS} value={value}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="inline-flex w-full min-w-0 items-center justify-center gap-1 text-center">{children}</span>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-[260px] text-xs">
          {tooltip}
        </TooltipContent>
      </Tooltip>
    </TabsTrigger>
  )
}

/** Inline label + InfoTooltip; keeps visible label text unchanged. */
function FieldLabelTip({ label, tip }: { label: string; tip: string }) {
  return (
    <span className="inline-flex max-w-full items-center gap-1">
      <span className="text-sm font-medium">{label}</span>
      <InfoTooltip label={label} content={tip} className="size-4 shrink-0" />
    </span>
  )
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function parseCandidateInputs(text: string): { name?: string; smiles: string; role?: string }[] {
  const out: { name?: string; smiles: string; role?: string }[] = []
  for (const line of text.split(/\r?\n/)) {
    const t = line.trim()
    if (!t) continue
    const parts = t.split("|").map((p) => p.trim())
    if (parts.length >= 2 && parts[1]) {
      out.push({
        name: parts[0] || undefined,
        smiles: parts[1],
        role: parts[2] || undefined,
      })
    } else if (parts.length === 1 && parts[0]) {
      out.push({ smiles: parts[0] })
    }
  }
  return out
}

function LcmsAdvGroupingDetailTables({ result }: { result: unknown }) {
  if (!isRecord(result)) return null
  const summaries = Array.isArray(result.alignment_summaries) ? result.alignment_summaries.filter(isRecord) : []
  const groups = Array.isArray(result.groups) ? result.groups.filter(isRecord) : []
  const warnings = Array.isArray(result.warnings) ? result.warnings.map(String) : []
  const notes = Array.isArray(result.notes) ? result.notes.map(String) : []
  const ft = typeof result.feature_table_text === "string" ? result.feature_table_text : ""

  return (
    <div className="space-y-4">
      <div className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <span className="text-muted-foreground">Group count</span>
          <p className="font-medium">{typeof result.group_count === "number" ? result.group_count : "—"}</p>
        </div>
        <div>
          <span className="text-muted-foreground">Sample-enriched count</span>
          <p className="font-medium">
            {typeof result.sample_enriched_group_count === "number" ? result.sample_enriched_group_count : "—"}
          </p>
        </div>
        <div>
          <span className="text-muted-foreground">Blank-like / background count</span>
          <p className="font-medium">
            {typeof result.background_group_count === "number" ? result.background_group_count : "—"}
          </p>
        </div>
        <div>
          <span className="text-muted-foreground">Label</span>
          <p className="font-mono text-xs font-medium">{String(result.label ?? "—")}</p>
        </div>
      </div>

      {summaries.length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">RT shift summary</CardTitle>
            <CardDescription>Per-run alignment summaries from the response payload.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Run</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>RT shift (min)</TableHead>
                  <TableHead>Aligned features</TableHead>
                  <TableHead>Anchor matches</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {summaries.map((row, i) => (
                  <TableRow key={`rt-${i}`}>
                    <TableCell className="font-mono text-xs">{String(row.run_id ?? "—")}</TableCell>
                    <TableCell>{String(row.role ?? "—")}</TableCell>
                    <TableCell>
                      {typeof row.rt_shift_min === "number" ? row.rt_shift_min.toFixed(4) : "—"}
                    </TableCell>
                    <TableCell>
                      {typeof row.aligned_feature_count === "number" ? row.aligned_feature_count : "—"}
                    </TableCell>
                    <TableCell>
                      {typeof row.anchor_match_count === "number" ? row.anchor_match_count : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {groups.length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Family hints (group labels)</CardTitle>
            <CardDescription>Condensed group rows—review full JSON for member-level detail.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Group ID</TableHead>
                  <TableHead>Representative m/z</TableHead>
                  <TableHead>RT (min)</TableHead>
                  <TableHead>Label</TableHead>
                  <TableHead>Blank ratio</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {groups.slice(0, 50).map((g, i) => (
                  <TableRow key={`grp-${i}`}>
                    <TableCell className="font-mono text-xs">{String(g.group_id ?? "—")}</TableCell>
                    <TableCell>
                      {typeof g.representative_mz === "number" ? g.representative_mz.toFixed(5) : "—"}
                    </TableCell>
                    <TableCell>
                      {typeof g.representative_rt_min === "number" ? g.representative_rt_min.toFixed(3) : "—"}
                    </TableCell>
                    <TableCell className="max-w-[140px] truncate text-xs">{String(g.label ?? "—")}</TableCell>
                    <TableCell>{typeof g.blank_ratio === "number" ? g.blank_ratio.toFixed(3) : "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {groups.length > 50 && (
              <p className="mt-2 text-xs text-muted-foreground">Showing first 50 of {groups.length} groups.</p>
            )}
          </CardContent>
        </Card>
      )}

      {ft.trim().length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Grouped feature table (text)</CardTitle>
            <CardDescription>Server-exported <code className="text-xs">feature_table_text</code>.</CardDescription>
          </CardHeader>
          <CardContent>
            <pre className="max-h-[320px] overflow-auto whitespace-pre-wrap rounded-md border bg-muted/30 p-3 text-xs">{ft}</pre>
          </CardContent>
        </Card>
      )}

      {(warnings.length > 0 || notes.length > 0) && (
        <AlertCard variant="warning" title="Warnings">
          <div className="space-y-2 text-sm">
            {warnings.map((w, i) => (
              <p key={`w-${i}`} className="text-foreground">
                {w}
              </p>
            ))}
            {notes.map((n, i) => (
              <p key={`n-${i}`} className="text-muted-foreground">
                {n}
              </p>
            ))}
          </div>
        </AlertCard>
      )}

    </div>
  )
}

function LcmsAdvConsensusDetailTables({ result }: { result: unknown }) {
  if (!isRecord(result)) return null
  const families = Array.isArray(result.families) ? result.families.filter(isRecord) : []
  let high = 0
  let moderate = 0
  let low = 0
  for (const f of families) {
    const lab = String(f.label ?? "")
    if (lab === "high_confidence_feature_family") high += 1
    else if (lab === "moderate_confidence_feature_family") moderate += 1
    else if (lab === "low_confidence_feature_family") low += 1
  }
  const best = isRecord(result.best_family) ? result.best_family : null
  const aggregateScore = best && typeof best.consensus_score === "number" ? best.consensus_score : null
  const promoted = families.filter((f) => f.promoted_for_candidate_scoring === true)
  const layerRows: { layer: string; label: string; score: number | null; contradiction: boolean }[] = []
  for (const fam of families.slice(0, 5)) {
    const layers = Array.isArray(fam.layer_scores) ? fam.layer_scores.filter(isRecord) : []
    for (const L of layers) {
      layerRows.push({
        layer: String(L.layer ?? "—"),
        label: String(L.label ?? "—"),
        score: typeof L.score === "number" ? L.score : null,
        contradiction: L.contradiction === true,
      })
    }
  }
  const contradictions: string[] = []
  for (const fam of families) {
    if (typeof fam.contradiction_count === "number" && fam.contradiction_count > 0) {
      contradictions.push(`Family ${String(fam.family_id ?? "")}: ${fam.contradiction_count} contradiction(s)`)
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <span className="text-muted-foreground">Consensus score (best family)</span>
          <p className="font-medium">{aggregateScore != null ? aggregateScore.toFixed(3) : "—"}</p>
        </div>
        <div>
          <span className="text-muted-foreground">Promoted family count</span>
          <p className="font-medium">{typeof result.promoted_family_count === "number" ? result.promoted_family_count : "—"}</p>
        </div>
        <div>
          <span className="text-muted-foreground">High / moderate / low confidence</span>
          <p className="font-medium">
            {high} / {moderate} / {low}
          </p>
        </div>
        <div>
          <span className="text-muted-foreground">Result label</span>
          <p className="font-mono text-xs font-medium">{String(result.label ?? "—")}</p>
        </div>
      </div>

      {layerRows.length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Layer scores (subset)</CardTitle>
            <CardDescription>From <code className="text-xs">layer_scores</code> on the first few families.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Layer</TableHead>
                  <TableHead>Label</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Contradiction</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {layerRows.slice(0, 40).map((row, i) => (
                  <TableRow key={`lay-${i}`}>
                    <TableCell className="font-mono text-xs">{row.layer}</TableCell>
                    <TableCell className="max-w-[180px] truncate text-xs">{row.label}</TableCell>
                    <TableCell>{row.score != null ? row.score.toFixed(3) : "—"}</TableCell>
                    <TableCell>{row.contradiction ? "yes" : "no"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {contradictions.length > 0 && (
        <AlertCard variant="error" title="Contradictions">
          <div className="space-y-1 text-sm">
            {contradictions.map((c, i) => (
              <p key={`cx-${i}`}>{c}</p>
            ))}
          </div>
        </AlertCard>
      )}

      {promoted.length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Promoted feature family table</CardTitle>
            <CardDescription>Families with <code className="text-xs">promoted_for_candidate_scoring</code>.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Family ID</TableHead>
                  <TableHead>Anchor m/z</TableHead>
                  <TableHead>Anchor RT (min)</TableHead>
                  <TableHead>Consensus score</TableHead>
                  <TableHead>Label</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {promoted.map((f, i) => (
                  <TableRow key={`pf-${i}`}>
                    <TableCell className="font-mono text-xs">{String(f.family_id ?? "—")}</TableCell>
                    <TableCell>{typeof f.anchor_mz === "number" ? f.anchor_mz.toFixed(5) : "—"}</TableCell>
                    <TableCell>{typeof f.anchor_rt_min === "number" ? f.anchor_rt_min.toFixed(3) : "—"}</TableCell>
                    <TableCell>{typeof f.consensus_score === "number" ? f.consensus_score.toFixed(3) : "—"}</TableCell>
                    <TableCell className="max-w-[160px] truncate text-xs">{String(f.label ?? "—")}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function LcmsAdvDereplicationDetailTables({ result }: { result: unknown }) {
  if (!isRecord(result)) return null
  const matches = Array.isArray(result.matches) ? result.matches.filter(isRecord) : []
  const best = isRecord(result.best_match) ? result.best_match : null
  const warnings = Array.isArray(result.warnings) ? result.warnings.map(String) : []

  return (
    <div className="space-y-4">
      {best && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Top library hit</CardTitle>
            <CardDescription>Highest-ranked row from <code className="text-xs">best_match</code> — decision-support only.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <span className="text-muted-foreground">SMILES</span>
              <p className="font-mono text-xs break-all">{String(best.smiles ?? "—")}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Score</span>
              <p className="font-medium">{typeof best.score === "number" ? best.score.toFixed(4) : "—"}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Mass match (Δ Da)</span>
              <p className="font-medium">
                {typeof best.mz_error_da === "number" ? best.mz_error_da.toFixed(5) : "—"}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">Best family anchor RT (min)</span>
              <p className="font-medium">
                {typeof best.best_family_anchor_rt_min === "number" ? best.best_family_anchor_rt_min.toFixed(3) : "—"}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">Label</span>
              <p className="font-mono text-xs">{String(best.label ?? "—")}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Spectral / consensus shape</span>
              <p className="text-xs text-muted-foreground">
                Rank uses LC-MS consensus bridge scoring on this endpoint—not a full spectral library match unless your
                upstream evidence included MS/MS similarity fields in metadata.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {matches.length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Ranked hits</CardTitle>
            <CardDescription>Score, mass error, and family anchor RT when present.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Rank</TableHead>
                  <TableHead>SMILES</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Δ m/z (Da)</TableHead>
                  <TableHead>ppm</TableHead>
                  <TableHead>Anchor RT</TableHead>
                  <TableHead>Label</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {matches.map((m, i) => (
                  <TableRow key={`dm-${i}`}>
                    <TableCell>{typeof m.rank === "number" ? m.rank : i + 1}</TableCell>
                    <TableCell className="max-w-[140px] truncate font-mono text-xs">{String(m.smiles ?? "—")}</TableCell>
                    <TableCell>{typeof m.score === "number" ? m.score.toFixed(4) : "—"}</TableCell>
                    <TableCell>{typeof m.mz_error_da === "number" ? m.mz_error_da.toFixed(5) : "—"}</TableCell>
                    <TableCell>{typeof m.mz_error_ppm === "number" ? m.mz_error_ppm.toFixed(2) : "—"}</TableCell>
                    <TableCell>
                      {typeof m.best_family_anchor_rt_min === "number" ? m.best_family_anchor_rt_min.toFixed(3) : "—"}
                    </TableCell>
                    <TableCell className="max-w-[120px] truncate text-xs">{String(m.label ?? "—")}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {typeof result.metadata === "object" && result.metadata != null && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Provenance</CardTitle>
            <CardDescription>Subset of <code className="text-xs">metadata</code> from the response.</CardDescription>
          </CardHeader>
          <CardContent>
            <pre className="max-h-[200px] overflow-auto rounded-md border bg-muted/30 p-3 text-xs">
              {JSON.stringify(result.metadata, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}

      <Card className="min-w-0">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Seed candidates for unified confidence</CardTitle>
          <CardDescription>Use bridge / unified confidence workflows downstream with the same candidate lines and hashes.</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Candidate rows submitted here are parsed server-side; reuse them when linking LC-MS layers into unified scoring.
        </CardContent>
      </Card>

      {warnings.length > 0 && (
        <AlertCard variant="warning" title="Warnings">
          <div className="space-y-1 text-sm">
            {warnings.map((w, i) => (
              <p key={`dw-${i}`}>{w}</p>
            ))}
          </div>
        </AlertCard>
      )}
    </div>
  )
}

function LcmsAdvBridgeDetailTables({ result }: { result: unknown }) {
  if (!isRecord(result)) return null
  const matches = Array.isArray(result.matches) ? result.matches.filter(isRecord) : []
  const best = isRecord(result.best_match) ? result.best_match : null
  const meta = isRecord(result.metadata) ? result.metadata : null
  const bridgeHash =
    meta && typeof meta.bridge_result_sha256 === "string"
      ? meta.bridge_result_sha256
      : meta && typeof (meta as { bridge_result_hash?: string }).bridge_result_hash === "string"
        ? (meta as { bridge_result_hash: string }).bridge_result_hash
        : null
  const contradictions = matches.filter((m) => m.contradiction === true)

  return (
    <div className="space-y-4">
      <div className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <span className="text-muted-foreground">Matched candidates (rows)</span>
          <p className="font-medium">{matches.length}</p>
        </div>
        <div>
          <span className="text-muted-foreground">Families (total)</span>
          <p className="font-medium">{typeof result.family_count === "number" ? result.family_count : "—"}</p>
        </div>
        <div>
          <span className="text-muted-foreground">Eligible families</span>
          <p className="font-medium">{typeof result.eligible_family_count === "number" ? result.eligible_family_count : "—"}</p>
        </div>
        <div>
          <span className="text-muted-foreground">LC-MS candidate support (best score)</span>
          <p className="font-medium">{best && typeof best.score === "number" ? best.score.toFixed(4) : "—"}</p>
        </div>
      </div>

      {contradictions.length > 0 && (
        <AlertCard variant="error" title="Contradictions">
          <div className="space-y-2 text-sm">
            {contradictions.map((m, i) => (
              <p key={`bc-${i}`} className="font-mono text-xs">
                {String(m.smiles ?? "")} — {String(m.label ?? "")}
              </p>
            ))}
          </div>
        </AlertCard>
      )}

      {bridgeHash && (
        <p className="text-sm">
          <span className="text-muted-foreground">Bridge result hash</span>{" "}
          <code className="rounded bg-muted px-1 text-xs">{bridgeHash}</code>
        </p>
      )}

      {matches.length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Matches</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Rank</TableHead>
                  <TableHead>SMILES</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Family</TableHead>
                  <TableHead>Contradiction</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {matches.map((m, i) => (
                  <TableRow key={`bm-${i}`}>
                    <TableCell>{typeof m.rank === "number" ? m.rank : i + 1}</TableCell>
                    <TableCell className="max-w-[160px] truncate font-mono text-xs">{String(m.smiles ?? "")}</TableCell>
                    <TableCell>{typeof m.score === "number" ? m.score.toFixed(4) : "—"}</TableCell>
                    <TableCell className="font-mono text-xs">{String(m.best_family_id ?? "—")}</TableCell>
                    <TableCell>{m.contradiction === true ? "yes" : "no"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function formatMsmsAnnotationSupportLabel(label: unknown): string {
  if (label === "consistent_with_msms") return "Consistent with MS/MS"
  if (label === "partial_msms_support") return "Partial support"
  if (label === "weak_or_no_msms_support") return "Weak / no support"
  if (label === "invalid_structure") return "Requires review"
  return typeof label === "string" ? label : "Requires review"
}

function formatFragmentationTreeSupportLabel(label: unknown): string {
  if (label === "strong_fragmentation_tree_support") return "Supports (strong — requires review)"
  if (label === "plausible_fragmentation_tree_support") return "Supports (plausible)"
  if (label === "weak_fragmentation_tree_support") return "Weak support"
  if (label === "contradictory_fragmentation_tree") return "Contradicts"
  if (label === "invalid_structure") return "Requires review"
  return typeof label === "string" ? label : "Requires review"
}

function formatLcmsFeaturePurityLabel(label: unknown): string {
  if (label === "high_purity") return "High purity"
  if (label === "possible_coelution") return "Possible co-elution"
  if (label === "poor_peak_purity") return "Poor peak purity"
  if (label === "not_assessed") return "Not assessed"
  return typeof label === "string" ? label : "—"
}

function HrmsMatchDetailTables({ result }: { result: unknown }) {
  if (!isRecord(result)) return null
  const exactCount = result.exact_match_count
  const ranked = Array.isArray(result.ranked_candidates)
    ? result.ranked_candidates.filter(isRecord)
    : []

  return (
    <div className="space-y-4">
      {typeof exactCount === "number" && (
        <p className="text-sm text-muted-foreground">
          Exact mass matches within tolerance:{" "}
          <span className="font-medium text-foreground">{exactCount}</span>
        </p>
      )}
      {ranked.length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Candidate metrics</CardTitle>
            <CardDescription>Theoretical m/z, ppm error, score, and DBE/IHD from the backend payload.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Rank</TableHead>
                  <TableHead>SMILES</TableHead>
                  <TableHead>Formula</TableHead>
                  <TableHead>Theoretical m/z</TableHead>
                  <TableHead>ppm error</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>DBE / IHD</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {ranked.map((row, i) => (
                  <TableRow key={`hrms-row-${i}`}>
                    <TableCell>{typeof row.rank === "number" ? row.rank : i + 1}</TableCell>
                    <TableCell className="max-w-[180px] truncate font-mono text-xs" title={String(row.smiles ?? "")}>
                      {String(row.smiles ?? "—")}
                    </TableCell>
                    <TableCell>{String(row.formula ?? "—")}</TableCell>
                    <TableCell>
                      {typeof row.theoretical_mz === "number" ? row.theoretical_mz.toFixed(5) : "—"}
                    </TableCell>
                    <TableCell>
                      {typeof row.ppm_error === "number" ? row.ppm_error.toFixed(2) : "—"}
                    </TableCell>
                    <TableCell>
                      {typeof row.ppm_score === "number" ? (row.ppm_score <= 1 ? (row.ppm_score * 100).toFixed(1) : row.ppm_score.toFixed(1)) : "—"}
                    </TableCell>
                    <TableCell>{typeof row.dbe === "number" ? row.dbe.toFixed(2) : "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function AdductInferenceDetailTables({ result }: { result: unknown }) {
  if (!isRecord(result)) return null

  const primaryMz = result.primary_mz
  const inferredCharge = result.inferred_charge
  const m1 = result.inferred_m_plus_1_percent
  const m2 = result.inferred_m_plus_2_percent
  const best = isRecord(result.best_adduct_candidate) ? result.best_adduct_candidate : null
  const bestAdduct = best && isRecord(best.adduct) ? best.adduct : null
  const bestAdductName =
    isRecord(bestAdduct) && typeof bestAdduct.name === "string" ? bestAdduct.name : "—"
  const ranked = Array.isArray(result.adduct_candidates) ? result.adduct_candidates.filter(isRecord) : []
  const clusters = Array.isArray(result.isotope_clusters) ? result.isotope_clusters.filter(isRecord) : []

  return (
    <div className="space-y-4">
      <Card className="min-w-0">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Inferred metrics</CardTitle>
          <CardDescription>Primary m/z, charge state, and isotope ratios from the response payload.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="text-sm">
            <span className="text-muted-foreground">Primary m/z</span>
            <p className="font-mono font-medium">
              {typeof primaryMz === "number" ? primaryMz.toFixed(5) : "—"}
            </p>
          </div>
          <div className="text-sm">
            <span className="text-muted-foreground">Inferred charge</span>
            <p className="font-medium">{typeof inferredCharge === "number" ? inferredCharge : "—"}</p>
          </div>
          <div className="text-sm">
            <span className="text-muted-foreground">M+1 %</span>
            <p className="font-medium">{typeof m1 === "number" ? m1.toFixed(2) : "—"}</p>
          </div>
          <div className="text-sm">
            <span className="text-muted-foreground">M+2 %</span>
            <p className="font-medium">{typeof m2 === "number" ? m2.toFixed(2) : "—"}</p>
          </div>
        </CardContent>
      </Card>

      {best && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Best adduct candidate</CardTitle>
            <CardDescription>Top-ranked hypothesis from <code className="text-xs">best_adduct_candidate</code>.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>
              <span className="text-muted-foreground">Adduct</span>{" "}
              <span className="font-mono font-medium">{bestAdductName}</span>
            </p>
            {typeof best.candidate_score === "number" && (
              <p>
                <span className="text-muted-foreground">Score</span>{" "}
                <span className="font-medium">
                  {best.candidate_score <= 1 ? (best.candidate_score * 100).toFixed(1) : best.candidate_score.toFixed(1)}
                </span>
              </p>
            )}
            {typeof best.neutral_mass === "number" && (
              <p>
                <span className="text-muted-foreground">Neutral mass</span>{" "}
                <span className="font-mono">{best.neutral_mass.toFixed(5)}</span>
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {clusters.length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Isotope clusters</CardTitle>
            <CardDescription>Detected clusters and matched peak positions.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6 overflow-x-auto">
            {clusters.map((cluster, ci) => {
              const peaks = Array.isArray(cluster.peaks) ? cluster.peaks.filter(isRecord) : []
              const mono = cluster.monoisotopic_mz
              return (
                <div key={`cluster-${ci}`} className="space-y-2">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>m/z (M)</TableHead>
                        <TableHead>Charge</TableHead>
                        <TableHead>M+1 %</TableHead>
                        <TableHead>M+2 %</TableHead>
                        <TableHead>Carbon est.</TableHead>
                        <TableHead>Halogen pattern</TableHead>
                        <TableHead>Label</TableHead>
                        <TableHead>Score</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      <TableRow>
                        <TableCell>{typeof mono === "number" ? mono.toFixed(5) : "—"}</TableCell>
                        <TableCell>{typeof cluster.charge === "number" ? cluster.charge : "—"}</TableCell>
                        <TableCell>
                          {typeof cluster.m_plus_1_percent === "number" ? cluster.m_plus_1_percent.toFixed(2) : "—"}
                        </TableCell>
                        <TableCell>
                          {typeof cluster.m_plus_2_percent === "number" ? cluster.m_plus_2_percent.toFixed(2) : "—"}
                        </TableCell>
                        <TableCell>
                          {typeof cluster.estimated_carbon_count === "number"
                            ? cluster.estimated_carbon_count.toFixed(1)
                            : "—"}
                        </TableCell>
                        <TableCell>{String(cluster.halogen_signature ?? "—")}</TableCell>
                        <TableCell>{String(cluster.label ?? "—")}</TableCell>
                        <TableCell>
                          {typeof cluster.confidence_score === "number"
                            ? cluster.confidence_score <= 1
                              ? (cluster.confidence_score * 100).toFixed(1)
                              : cluster.confidence_score.toFixed(1)
                            : "—"}
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                  {peaks.length > 0 && (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Isotope</TableHead>
                          <TableHead>m/z</TableHead>
                          <TableHead>Expected m/z</TableHead>
                          <TableHead>Δ Da</TableHead>
                          <TableHead>Rel. %</TableHead>
                          <TableHead>ppm error</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {peaks.map((pk, pi) => (
                          <TableRow key={`cluster-${ci}-pk-${pi}`}>
                            <TableCell>{String(pk.isotope_label ?? "—")}</TableCell>
                            <TableCell>{typeof pk.mz === "number" ? pk.mz.toFixed(5) : "—"}</TableCell>
                            <TableCell>{typeof pk.expected_mz === "number" ? pk.expected_mz.toFixed(5) : "—"}</TableCell>
                            <TableCell>{typeof pk.delta_da === "number" ? pk.delta_da.toFixed(4) : "—"}</TableCell>
                            <TableCell>
                              {typeof pk.relative_intensity === "number" ? pk.relative_intensity.toFixed(2) : "—"}
                            </TableCell>
                            <TableCell>{typeof pk.ppm_error === "number" ? pk.ppm_error.toFixed(2) : "—"}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </div>
              )
            })}
          </CardContent>
        </Card>
      )}

      {ranked.length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Ranked adduct candidates</CardTitle>
            <CardDescription>Scores and formula hints per ranked hypothesis.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto space-y-6">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Rank</TableHead>
                  <TableHead>Adduct</TableHead>
                  <TableHead>Neutral mass</TableHead>
                  <TableHead>Formula count</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Label</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {ranked.map((row, i) => {
                  const ad = isRecord(row.adduct) ? row.adduct : null
                  const adName = isRecord(ad) && typeof ad.name === "string" ? ad.name : "—"
                  return (
                    <TableRow key={`adduct-rank-${i}`}>
                      <TableCell>{typeof row.rank === "number" ? row.rank : i + 1}</TableCell>
                      <TableCell className="font-mono text-sm">{adName}</TableCell>
                      <TableCell>
                        {typeof row.neutral_mass === "number" ? row.neutral_mass.toFixed(5) : "—"}
                      </TableCell>
                      <TableCell>{typeof row.formula_count === "number" ? row.formula_count : "—"}</TableCell>
                      <TableCell>
                        {typeof row.candidate_score === "number"
                          ? row.candidate_score <= 1
                            ? (row.candidate_score * 100).toFixed(1)
                            : row.candidate_score.toFixed(1)
                          : "—"}
                      </TableCell>
                      <TableCell>{String(row.label ?? "—")}</TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
            {ranked.map((row, i) => {
              const topFormulas = Array.isArray(row.top_formulas) ? row.top_formulas.filter(isRecord) : []
              if (topFormulas.length === 0) return null
              const ad = isRecord(row.adduct) ? row.adduct : null
              const adName = isRecord(ad) && typeof ad.name === "string" ? ad.name : `Rank ${i + 1}`
              return (
                <div key={`adduct-formulas-${i}`} className="space-y-2">
                  <p className="text-sm font-medium">Formula candidates — {adName}</p>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Formula</TableHead>
                        <TableHead>Exact mass</TableHead>
                        <TableHead>DBE / IHD</TableHead>
                        <TableHead>M+1 %</TableHead>
                        <TableHead>M+2 %</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {topFormulas.map((f, fi) => (
                        <TableRow key={`af-${i}-${fi}`}>
                          <TableCell className="font-mono text-sm">{String(f.formula ?? "—")}</TableCell>
                          <TableCell>
                            {typeof f.exact_mass === "number" ? f.exact_mass.toFixed(5) : "—"}
                          </TableCell>
                          <TableCell>{typeof f.dbe === "number" ? f.dbe.toFixed(2) : "—"}</TableCell>
                          <TableCell>
                            {typeof f.isotope_m_plus_1_percent === "number"
                              ? f.isotope_m_plus_1_percent.toFixed(2)
                              : "—"}
                          </TableCell>
                          <TableCell>
                            {typeof f.isotope_m_plus_2_percent === "number"
                              ? f.isotope_m_plus_2_percent.toFixed(2)
                              : "—"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )
            })}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function MsmsAnnotationDetailTables({ result }: { result: unknown }) {
  if (!isRecord(result)) return null
  const best = isRecord(result.best_candidate) ? result.best_candidate : null
  const ranked = Array.isArray(result.ranked_candidates) ? result.ranked_candidates.filter(isRecord) : []
  const globalLosses = Array.isArray(result.neutral_loss_hits) ? result.neutral_loss_hits.filter(isRecord) : []
  const fragMatches =
    best && Array.isArray(best.fragment_matches) ? best.fragment_matches.filter(isRecord) : []
  const adductName =
    isRecord(result.adduct) && typeof result.adduct.name === "string" ? result.adduct.name : "—"

  return (
    <div className="space-y-4">
      <Card className="min-w-0">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Precursor consistency</CardTitle>
          <CardDescription>
            Labels indicate how well the precursor hypothesis fits these MS/MS inputs — not compound identity.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>
            <span className="text-muted-foreground">Precursor m/z</span>{" "}
            <span className="font-mono font-medium">
              {typeof result.precursor_mz === "number" ? result.precursor_mz.toFixed(5) : "—"}
            </span>
          </p>
          <p>
            <span className="text-muted-foreground">Precursor adduct</span>{" "}
            <span className="font-mono">{adductName}</span>
          </p>
          {best ? (
            <>
              <p>
                <span className="text-muted-foreground">Support vs spectrum</span>{" "}
                <span className="font-medium">{formatMsmsAnnotationSupportLabel(best.label)}</span>
              </p>
              {typeof best.precursor_ppm_error === "number" && (
                <p>
                  <span className="text-muted-foreground">Precursor ppm error</span>{" "}
                  <span className="font-mono">{best.precursor_ppm_error.toFixed(2)}</span>
                </p>
              )}
              {typeof best.precursor_score === "number" && (
                <p>
                  <span className="text-muted-foreground">Precursor score</span>{" "}
                  <span className="font-medium">
                    {best.precursor_score <= 1
                      ? `${(best.precursor_score * 100).toFixed(1)}%`
                      : best.precursor_score.toFixed(2)}
                  </span>
                </p>
              )}
            </>
          ) : (
            <p className="text-muted-foreground">No best candidate row returned.</p>
          )}
        </CardContent>
      </Card>

      <Card className="min-w-0">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Explained peaks</CardTitle>
          <CardDescription>Counts and intensity recovery from the annotation layer.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <span className="text-muted-foreground">Peaks in list</span>
            <p className="font-medium">{typeof result.peak_count === "number" ? result.peak_count : "—"}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Annotated peaks</span>
            <p className="font-medium">
              {typeof result.annotated_peak_count === "number" ? result.annotated_peak_count : "—"}
            </p>
          </div>
          <div>
            <span className="text-muted-foreground">Explained peak count</span>
            <p className="font-medium">
              {best && typeof best.explained_peak_count === "number" ? best.explained_peak_count : "—"}
            </p>
          </div>
          <div>
            <span className="text-muted-foreground">Explained intensity fraction</span>
            <p className="font-medium">
              {best && typeof best.explained_intensity_fraction === "number"
                ? `${(best.explained_intensity_fraction * 100).toFixed(1)}%`
                : "—"}
            </p>
          </div>
        </CardContent>
      </Card>

      {globalLosses.length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Neutral-loss hits</CardTitle>
            <CardDescription>Diagnostic neutral losses aligned to centroid peaks.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Fragment m/z</TableHead>
                  <TableHead>Loss</TableHead>
                  <TableHead>Obs. loss Da</TableHead>
                  <TableHead>Exp. loss Da</TableHead>
                  <TableHead>Error Da</TableHead>
                  <TableHead>Rel. %</TableHead>
                  <TableHead>Note</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {globalLosses.map((hit, i) => (
                  <TableRow key={`nl-${i}`}>
                    <TableCell>
                      {typeof hit.fragment_mz === "number" ? hit.fragment_mz.toFixed(5) : "—"}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{String(hit.loss_name ?? "—")}</TableCell>
                    <TableCell>
                      {typeof hit.observed_loss_da === "number" ? hit.observed_loss_da.toFixed(4) : "—"}
                    </TableCell>
                    <TableCell>
                      {typeof hit.expected_loss_da === "number" ? hit.expected_loss_da.toFixed(4) : "—"}
                    </TableCell>
                    <TableCell>{typeof hit.error_da === "number" ? hit.error_da.toFixed(4) : "—"}</TableCell>
                    <TableCell>
                      {typeof hit.relative_intensity === "number" ? hit.relative_intensity.toFixed(1) : "—"}
                    </TableCell>
                    <TableCell className="max-w-[220px] text-xs">{String(hit.interpretation ?? "")}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {fragMatches.length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Fragment matches (best-ranked candidate)</CardTitle>
            <CardDescription>Assignment-level hits only — expert review still applies.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Peak m/z</TableHead>
                  <TableHead>Theoretical m/z</TableHead>
                  <TableHead>ppm</TableHead>
                  <TableHead>Rel. %</TableHead>
                  <TableHead>Formula</TableHead>
                  <TableHead>Type</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {fragMatches.map((m, i) => (
                  <TableRow key={`fm-${i}`}>
                    <TableCell>{typeof m.peak_mz === "number" ? m.peak_mz.toFixed(5) : "—"}</TableCell>
                    <TableCell>
                      {typeof m.theoretical_mz === "number" ? m.theoretical_mz.toFixed(5) : "—"}
                    </TableCell>
                    <TableCell>{typeof m.ppm_error === "number" ? m.ppm_error.toFixed(2) : "—"}</TableCell>
                    <TableCell>
                      {typeof m.relative_intensity === "number" ? m.relative_intensity.toFixed(1) : "—"}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{String(m.formula ?? "—")}</TableCell>
                    <TableCell className="text-xs">{String(m.fragment_type ?? "—")}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {ranked.length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Ranked candidate support</CardTitle>
            <CardDescription>Ordering reflects automated scoring — conflicting rows require review.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Rank</TableHead>
                  <TableHead>Candidate</TableHead>
                  <TableHead>Support vs spectrum</TableHead>
                  <TableHead>Explained peaks</TableHead>
                  <TableHead>Explained intensity</TableHead>
                  <TableHead>Score</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {ranked.map((row, i) => (
                  <TableRow key={`msms-r-${i}`}>
                    <TableCell>{typeof row.rank === "number" ? row.rank : i + 1}</TableCell>
                    <TableCell className="max-w-[200px] truncate font-mono text-xs" title={String(row.smiles ?? "")}>
                      {String(row.smiles ?? row.name ?? "—")}
                    </TableCell>
                    <TableCell className="text-sm">{formatMsmsAnnotationSupportLabel(row.label)}</TableCell>
                    <TableCell>
                      {typeof row.explained_peak_count === "number" ? row.explained_peak_count : "—"}
                    </TableCell>
                    <TableCell>
                      {typeof row.explained_intensity_fraction === "number"
                        ? `${(row.explained_intensity_fraction * 100).toFixed(1)}%`
                        : "—"}
                    </TableCell>
                    <TableCell>
                      {typeof row.candidate_score === "number"
                        ? row.candidate_score <= 1
                          ? `${(row.candidate_score * 100).toFixed(1)}%`
                          : row.candidate_score.toFixed(2)
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function FragmentationTreeDetailTables({ result }: { result: unknown }) {
  if (!isRecord(result)) return null
  const best = isRecord(result.best_candidate) ? result.best_candidate : null
  const edges = best && Array.isArray(best.edges) ? best.edges.filter(isRecord) : []
  const diagnosticHits =
    best && Array.isArray(best.diagnostic_hits) ? best.diagnostic_hits.filter(isRecord) : []
  const contradictionFlags =
    best && Array.isArray(best.contradiction_flags)
      ? best.contradiction_flags.filter((x): x is string => typeof x === "string")
      : []

  return (
    <div className="space-y-4">
      {best && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Tree reasoning summary</CardTitle>
            <CardDescription>
              Scores summarize fit to this spectrum and candidate — they support or contradict hypotheses; they do not
              confirm identity.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <span className="text-muted-foreground">Support vs tree</span>
              <p className="font-medium">{formatFragmentationTreeSupportLabel(best.label)}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Tree score</span>
              <p className="font-medium">
                {typeof best.tree_score === "number"
                  ? best.tree_score <= 1
                    ? `${(best.tree_score * 100).toFixed(1)}%`
                    : best.tree_score.toFixed(2)
                  : "—"}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">Precursor score</span>
              <p className="font-medium">
                {typeof best.precursor_score === "number"
                  ? best.precursor_score <= 1
                    ? `${(best.precursor_score * 100).toFixed(1)}%`
                    : best.precursor_score.toFixed(2)
                  : "—"}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">Explained intensity fraction</span>
              <p className="font-medium">
                {typeof best.explained_intensity_fraction === "number"
                  ? `${(best.explained_intensity_fraction * 100).toFixed(1)}%`
                  : "—"}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">Diagnostic loss count</span>
              <p className="font-medium">
                {typeof best.diagnostic_loss_count === "number" ? best.diagnostic_loss_count : "—"}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">Contradiction count</span>
              <p className="font-medium">
                {typeof best.contradiction_count === "number" ? best.contradiction_count : "—"}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">Max tree depth</span>
              <p className="font-medium">{typeof best.max_tree_depth === "number" ? best.max_tree_depth : "—"}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {edges.length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Edge table</CardTitle>
            <CardDescription>Precursor→fragment and fragment→subfragment relationships.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Parent</TableHead>
                  <TableHead>Child</TableHead>
                  <TableHead>Relation</TableHead>
                  <TableHead>Loss</TableHead>
                  <TableHead>Δ Da</TableHead>
                  <TableHead>Diagnostic</TableHead>
                  <TableHead>Note</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {edges.map((e, i) => (
                  <TableRow key={`edge-${i}`}>
                    <TableCell className="font-mono text-xs">{String(e.parent_id ?? "—")}</TableCell>
                    <TableCell className="font-mono text-xs">{String(e.child_id ?? "—")}</TableCell>
                    <TableCell className="text-xs">{String(e.relation_type ?? "—")}</TableCell>
                    <TableCell className="font-mono text-xs">{String(e.loss_name ?? "—")}</TableCell>
                    <TableCell>
                      {typeof e.observed_loss_da === "number" ? e.observed_loss_da.toFixed(4) : "—"}
                    </TableCell>
                    <TableCell>{e.diagnostic === true ? "yes" : "no"}</TableCell>
                    <TableCell className="max-w-[200px] text-xs">{String(e.explanation ?? "")}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {diagnosticHits.length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Diagnostic hits</CardTitle>
            <CardDescription>Losses flagged as structurally informative for review.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Loss</TableHead>
                  <TableHead>Fragment m/z</TableHead>
                  <TableHead>Obs. loss Da</TableHead>
                  <TableHead>Rel. %</TableHead>
                  <TableHead>Class</TableHead>
                  <TableHead>Interpretation</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {diagnosticHits.map((h, i) => (
                  <TableRow key={`dh-${i}`}>
                    <TableCell className="font-mono text-xs">{String(h.loss_name ?? "—")}</TableCell>
                    <TableCell>
                      {typeof h.fragment_mz === "number" ? h.fragment_mz.toFixed(5) : "—"}
                    </TableCell>
                    <TableCell>
                      {typeof h.observed_loss_da === "number" ? h.observed_loss_da.toFixed(4) : "—"}
                    </TableCell>
                    <TableCell>
                      {typeof h.relative_intensity === "number" ? h.relative_intensity.toFixed(1) : "—"}
                    </TableCell>
                    <TableCell className="text-xs">{String(h.diagnostic_class ?? "—")}</TableCell>
                    <TableCell className="max-w-[220px] text-xs">{String(h.interpretation ?? "")}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {contradictionFlags.length > 0 && (
        <Card className="min-w-0 border-destructive/30">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Contradiction flags</CardTitle>
            <CardDescription>These items contradict parts of the tree or candidate — review before relying on them.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {contradictionFlags.map((c, i) => (
                <li key={`cf-${i}`}>{c}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function LcmsImportBridgeDetailTables({ result }: { result: unknown }) {
  if (!isRecord(result)) return null
  const precursors = Array.isArray(result.extracted_precursors)
    ? result.extracted_precursors.filter(isRecord)
    : []
  const actions = Array.isArray(result.recommended_next_actions)
    ? result.recommended_next_actions.filter((x): x is string => typeof x === "string")
    : []
  const ms1Text =
    typeof result.extracted_ms1_peak_list_text === "string" ? result.extracted_ms1_peak_list_text : ""
  const msmsText =
    typeof result.extracted_msms_peak_list_text === "string" ? result.extracted_msms_peak_list_text : ""

  return (
    <div className="space-y-4">
      <Card className="min-w-0">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Import summary</CardTitle>
          <CardDescription>Hashed file metadata and scan counts from the bridge response.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <span className="text-muted-foreground">Source format</span>
            <p className="font-mono font-medium">{String(result.source_format ?? "—")}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Filename</span>
            <p className="break-all font-mono text-xs">{String(result.filename ?? "—")}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Source SHA-256</span>
            <p className="break-all font-mono text-xs">{String(result.file_sha256 ?? "—")}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Scan count</span>
            <p className="font-medium">{typeof result.scan_count === "number" ? result.scan_count : "—"}</p>
          </div>
          <div>
            <span className="text-muted-foreground">MS1 count</span>
            <p className="font-medium">{typeof result.ms1_scan_count === "number" ? result.ms1_scan_count : "—"}</p>
          </div>
          <div>
            <span className="text-muted-foreground">MS2 count</span>
            <p className="font-medium">{typeof result.ms2_scan_count === "number" ? result.ms2_scan_count : "—"}</p>
          </div>
        </CardContent>
      </Card>

      {precursors.length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Precursor inventory</CardTitle>
            <CardDescription>Precursor ions extracted for downstream MS/MS alignment.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Scan ID</TableHead>
                  <TableHead>Precursor m/z</TableHead>
                  <TableHead>RT (min)</TableHead>
                  <TableHead>Peaks</TableHead>
                  <TableHead>TIC</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {precursors.map((p, i) => (
                  <TableRow key={`prec-${i}`}>
                    <TableCell className="font-mono text-xs">{String(p.scan_id ?? "—")}</TableCell>
                    <TableCell>
                      {typeof p.precursor_mz === "number" ? p.precursor_mz.toFixed(5) : "—"}
                    </TableCell>
                    <TableCell>
                      {typeof p.retention_time_min === "number" ? p.retention_time_min.toFixed(3) : "—"}
                    </TableCell>
                    <TableCell>{typeof p.peak_count === "number" ? p.peak_count : "—"}</TableCell>
                    <TableCell>
                      {typeof p.total_ion_current === "number" ? p.total_ion_current.toExponential(2) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <Card className="min-w-0">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Selected MS/MS</CardTitle>
          <CardDescription>Backend-selected scan when applicable.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>
            <span className="text-muted-foreground">Scan ID</span>{" "}
            <span className="font-mono">{String(result.selected_msms_scan_id ?? "—")}</span>
          </p>
          <p>
            <span className="text-muted-foreground">Precursor m/z</span>{" "}
            <span className="font-mono">
              {typeof result.selected_msms_precursor_mz === "number"
                ? result.selected_msms_precursor_mz.toFixed(5)
                : "—"}
            </span>
          </p>
        </CardContent>
      </Card>

      <Card className="min-w-0">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Extracted MS1 peak list</CardTitle>
        </CardHeader>
        <CardContent>
          <Textarea readOnly value={ms1Text} rows={6} className="font-mono text-xs" />
        </CardContent>
      </Card>

      <Card className="min-w-0">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Selected MS/MS peak list</CardTitle>
        </CardHeader>
        <CardContent>
          <Textarea readOnly value={msmsText} rows={6} className="font-mono text-xs" />
        </CardContent>
      </Card>

      {actions.length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Recommended next actions</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {actions.map((a, i) => (
                <li key={`na-${i}`}>{a}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function LcmsFeatureDetectionDetailTables({ result }: { result: unknown }) {
  if (!isRecord(result)) return null
  const feats = Array.isArray(result.features) ? result.features.filter(isRecord) : []
  const best = isRecord(result.best_feature) ? result.best_feature : null
  const xicN = Array.isArray(result.xic_points) ? result.xic_points.length : 0

  return (
    <div className="space-y-4">
      <Card className="min-w-0">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Feature overview</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <span className="text-muted-foreground">Feature count</span>
            <p className="text-2xl font-semibold">
              {typeof result.feature_count === "number" ? result.feature_count : "—"}
            </p>
          </div>
          <div>
            <span className="text-muted-foreground">Source format</span>
            <p className="font-mono">{String(result.source_format ?? "—")}</p>
          </div>
        </CardContent>
      </Card>

      {best && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Best feature</CardTitle>
            <CardDescription>Highest-scoring feature row for quick review (not a compound ID).</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p>
              <span className="text-muted-foreground">Feature ID</span>{" "}
              <span className="font-mono">{String(best.feature_id ?? "—")}</span>
            </p>
            <p>
              <span className="text-muted-foreground">Apex RT (min)</span>{" "}
              <span className="font-mono">
                {typeof best.apex_rt_min === "number" ? best.apex_rt_min.toFixed(4) : "—"}
              </span>
            </p>
            <p>
              <span className="text-muted-foreground">Observed m/z</span>{" "}
              <span className="font-mono">
                {typeof best.observed_mz === "number" ? best.observed_mz.toFixed(5) : "—"}
              </span>
            </p>
            <p>
              <span className="text-muted-foreground">Area</span>{" "}
              {typeof best.area === "number" ? best.area.toExponential(3) : "—"}
            </p>
            <p>
              <span className="text-muted-foreground">Width (min)</span>{" "}
              {typeof best.width_min === "number" ? best.width_min.toFixed(4) : "—"}
            </p>
            {isRecord(best.purity) && (
              <p>
                <span className="text-muted-foreground">Purity label</span>{" "}
                <span className="font-medium">{formatLcmsFeaturePurityLabel(best.purity.label)}</span>
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <Card className="min-w-0 border-dashed">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">XIC / EIC preview</CardTitle>
          <CardDescription>
            Placeholder for extracted-ion chromatograms ({xicN} trace points in payload). Plotting integration can replace
            this panel later.
          </CardDescription>
        </CardHeader>
        <CardContent className="rounded-md border border-dashed bg-muted/30 py-8 text-center text-sm text-muted-foreground">
          Interactive trace preview not loaded — data available in developer JSON and backend tables.
        </CardContent>
      </Card>

      {feats.length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Feature table</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Apex RT</TableHead>
                  <TableHead>Obs. m/z</TableHead>
                  <TableHead>Area</TableHead>
                  <TableHead>Width</TableHead>
                  <TableHead>Purity</TableHead>
                  <TableHead>Linked MS/MS</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {feats.map((f, i) => {
                  const pur = isRecord(f.purity) ? f.purity : null
                  const linked = Array.isArray(f.linked_msms_spectra)
                    ? f.linked_msms_spectra.filter(isRecord)
                    : []
                  return (
                    <TableRow key={`feat-${i}`}>
                      <TableCell className="font-mono text-xs">{String(f.feature_id ?? "—")}</TableCell>
                      <TableCell>
                        {typeof f.apex_rt_min === "number" ? f.apex_rt_min.toFixed(3) : "—"}
                      </TableCell>
                      <TableCell>
                        {typeof f.observed_mz === "number" ? f.observed_mz.toFixed(5) : "—"}
                      </TableCell>
                      <TableCell>{typeof f.area === "number" ? f.area.toExponential(2) : "—"}</TableCell>
                      <TableCell>{typeof f.width_min === "number" ? f.width_min.toFixed(4) : "—"}</TableCell>
                      <TableCell className="text-xs">
                        {pur ? formatLcmsFeaturePurityLabel(pur.label) : "—"}
                      </TableCell>
                      <TableCell className="max-w-[140px] truncate text-xs">
                        {linked.length > 0
                          ? linked
                              .map((l) => (typeof l.scan_id === "string" ? l.scan_id : ""))
                              .filter(Boolean)
                              .join(", ")
                          : "—"}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function FormulaSearchDetailTables({ result }: { result: unknown }) {
  if (!isRecord(result)) return null
  const neutral = result.neutral_mass
  const fCount = result.formula_count
  const formulas = Array.isArray(result.formulas) ? result.formulas.filter(isRecord) : []

  return (
    <div className="space-y-4">
      {typeof neutral === "number" && (
        <p className="text-sm text-muted-foreground">
          Neutral mass: <span className="font-mono font-medium text-foreground">{neutral.toFixed(5)}</span>
        </p>
      )}
      {typeof fCount === "number" && (
        <p className="text-sm text-muted-foreground">
          Formula count: <span className="font-medium text-foreground">{fCount}</span>
        </p>
      )}
      {formulas.length > 0 && (
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Formula table</CardTitle>
            <CardDescription>Exact mass, DBE/IHD, and isotope predictions from the backend.</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Formula</TableHead>
                  <TableHead>Exact mass</TableHead>
                  <TableHead>DBE / IHD</TableHead>
                  <TableHead>M+1 %</TableHead>
                  <TableHead>M+2 %</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {formulas.map((row, i) => (
                  <TableRow key={`form-${i}`}>
                    <TableCell className="font-mono text-sm">{String(row.formula ?? "—")}</TableCell>
                    <TableCell>
                      {typeof row.exact_mass === "number" ? row.exact_mass.toFixed(5) : "—"}
                    </TableCell>
                    <TableCell>{typeof row.dbe === "number" ? row.dbe.toFixed(2) : "—"}</TableCell>
                    <TableCell>
                      {typeof row.isotope_m_plus_1_percent === "number"
                        ? row.isotope_m_plus_1_percent.toFixed(2)
                        : "—"}
                    </TableCell>
                    <TableCell>
                      {typeof row.isotope_m_plus_2_percent === "number"
                        ? row.isotope_m_plus_2_percent.toFixed(2)
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

type Props = {
  sampleId: string
  candidatesText: string
  /** When true together with `onLcmsHashForReport`, enables copying import SHA-256 into reporting UI */
  lcmsReportReady?: boolean
  onLcmsHashForReport?: (sha256: string) => void
}

export function SpectraCheckMsEvidence({
  sampleId,
  candidatesText,
  lcmsReportReady = false,
  onLcmsHashForReport,
}: Props) {
  const [hrmsObservedMz, setHrmsObservedMz] = useState("47.04914")
  const [hrmsAdduct, setHrmsAdduct] = useState<string>("[M+H]+")
  const [hrmsIonMode, setHrmsIonMode] = useState("auto")
  const [hrmsPpmTol, setHrmsPpmTol] = useState("5")
  const [hrmsM1, setHrmsM1] = useState("")
  const [hrmsM2, setHrmsM2] = useState("")
  const [hrmsCandidatesText, setHrmsCandidatesText] = useState(candidatesText)

  const [formulaObservedMz, setFormulaObservedMz] = useState("47.04914")
  const [formulaAdduct, setFormulaAdduct] = useState<string>("[M+H]+")
  const [formulaPpmTol, setFormulaPpmTol] = useState("5")
  const [formulaMaxC, setFormulaMaxC] = useState("40")
  const [formulaMaxResults, setFormulaMaxResults] = useState("50")

  useEffect(() => {
    setHrmsCandidatesText(candidatesText)
  }, [candidatesText])

  useEffect(() => {
    setMsmsCandidatesText(candidatesText)
  }, [candidatesText])

  useEffect(() => {
    setFragCandidatesText(candidatesText)
  }, [candidatesText])

  const [ms1PeakList, setMs1PeakList] = useState(DEFAULT_MS1_PEAKS)
  const [adductIonMode, setAdductIonMode] = useState("auto")
  const [adductTargetMz, setAdductTargetMz] = useState("")
  const [adductMzTolDa, setAdductMzTolDa] = useState("0.02")
  const [adductPpmTol, setAdductPpmTol] = useState("10")
  const [adductIsoTolDa, setAdductIsoTolDa] = useState("0.02")
  const [adductMinRelInt, setAdductMinRelInt] = useState("0.2")
  const [adductMaxPeaks, setAdductMaxPeaks] = useState("200")
  const [adductMaxCharge, setAdductMaxCharge] = useState("3")
  const [adductFormulaSearch, setAdductFormulaSearch] = useState(true)
  const [adductFormulaPerAdduct, setAdductFormulaPerAdduct] = useState("5")
  const [adductMaxC, setAdductMaxC] = useState("20")

  const [msmsPeakList, setMsmsPeakList] = useState(DEFAULT_MSMS_PEAKS)
  const [msmsPrecursorMz, setMsmsPrecursorMz] = useState("181.07066")
  const [msmsAdduct, setMsmsAdduct] = useState("[M+H]+")
  const [msmsMzTolDa, setMsmsMzTolDa] = useState("0.02")
  const [msmsPpmTol, setMsmsPpmTol] = useState("20")
  const [msmsMinRelInt, setMsmsMinRelInt] = useState("1")
  const [msmsMaxPeaks, setMsmsMaxPeaks] = useState("50")
  const [msmsCandidatesText, setMsmsCandidatesText] = useState(candidatesText)

  const [fragPeakList, setFragPeakList] = useState(DEFAULT_MSMS_PEAKS)
  const [fragPrecursorMz, setFragPrecursorMz] = useState("47.04914")
  const [fragAdduct, setFragAdduct] = useState("[M+H]+")
  const [fragMzTolDa, setFragMzTolDa] = useState("0.02")
  const [fragPpmTol, setFragPpmTol] = useState("20")
  const [fragMinRelInt, setFragMinRelInt] = useState("1")
  const [fragMaxPeaks, setFragMaxPeaks] = useState("75")
  const [fragMaxDepth, setFragMaxDepth] = useState("3")
  const [fragCandidatesText, setFragCandidatesText] = useState(candidatesText)

  const [hrmsMatchResult, setHrmsMatchResult] = useState<unknown>(null)
  const [hrmsMatchError, setHrmsMatchError] = useState("")
  const [hrmsMatchLoading, setHrmsMatchLoading] = useState(false)

  const [formulaResult, setFormulaResult] = useState<unknown>(null)
  const [formulaError, setFormulaError] = useState("")
  const [formulaLoading, setFormulaLoading] = useState(false)

  const [adductResult, setAdductResult] = useState<unknown>(null)
  const [adductError, setAdductError] = useState("")
  const [adductLoading, setAdductLoading] = useState(false)

  const [msmsResult, setMsmsResult] = useState<unknown>(null)
  const [msmsError, setMsmsError] = useState("")
  const [msmsLoading, setMsmsLoading] = useState(false)

  const [fragResult, setFragResult] = useState<unknown>(null)
  const [fragError, setFragError] = useState("")
  const [fragLoading, setFragLoading] = useState(false)

  const lcmsImportFileRef = useRef<HTMLInputElement>(null)
  const lcmsFeatureFileRef = useRef<HTMLInputElement>(null)

  const [lcmsImportSourceLabel, setLcmsImportSourceLabel] = useState("")
  const [lcmsImportPrecursorMz, setLcmsImportPrecursorMz] = useState("")
  const [lcmsImportResult, setLcmsImportResult] = useState<unknown>(null)
  const [lcmsImportError, setLcmsImportError] = useState("")
  const [lcmsImportLoading, setLcmsImportLoading] = useState(false)

  const [lcmsFeatTargetMz, setLcmsFeatTargetMz] = useState("")
  const [lcmsFeatMzTol, setLcmsFeatMzTol] = useState("0.02")
  const [lcmsFeatPpmTol, setLcmsFeatPpmTol] = useState("20")
  const [lcmsFeatMinRelH, setLcmsFeatMinRelH] = useState("5")
  const [lcmsFeatMinScans, setLcmsFeatMinScans] = useState("2")
  const [lcmsFeatSmooth, setLcmsFeatSmooth] = useState("1")
  const [lcmsFeatPurityWin, setLcmsFeatPurityWin] = useState("0.2")
  const [lcmsFeatTopCo, setLcmsFeatTopCo] = useState("5")
  const [lcmsFeatMaxFeat, setLcmsFeatMaxFeat] = useState("20")
  const [lcmsFeatureResult, setLcmsFeatureResult] = useState<unknown>(null)
  const [lcmsFeatureError, setLcmsFeatureError] = useState("")
  const [lcmsFeatureLoading, setLcmsFeatureLoading] = useState(false)

  const [lcmsImportSessionFileId, setLcmsImportSessionFileId] = useState("")
  const [lcmsFeatureSessionFileId, setLcmsFeatureSessionFileId] = useState("")
  const [msmsSessionFileId, setMsmsSessionFileId] = useState("")
  const [lcmsImportJobErr, setLcmsImportJobErr] = useState("")
  const [lcmsFeatureJobErr, setLcmsFeatureJobErr] = useState("")

  const lcmsGrpSampleFileRef = useRef<HTMLInputElement>(null)
  const lcmsGrpBlankFileRef = useRef<HTMLInputElement>(null)
  const lcmsConFeatFileRef = useRef<HTMLInputElement>(null)
  const lcmsDerLibraryFileRef = useRef<HTMLInputElement>(null)

  const [lcmsGrpSampleText, setLcmsGrpSampleText] = useState("")
  const [lcmsGrpBlankText, setLcmsGrpBlankText] = useState("")
  const [lcmsGrpRtTol, setLcmsGrpRtTol] = useState("0.12")
  const [lcmsGrpMzTol, setLcmsGrpMzTol] = useState("0.02")
  const [lcmsGrpPpmTol, setLcmsGrpPpmTol] = useState("20")
  const [lcmsGrpBlankRatio, setLcmsGrpBlankRatio] = useState("0.30")
  const [lcmsGrpPossBg, setLcmsGrpPossBg] = useState("0.10")
  const [lcmsGrpBlankFact, setLcmsGrpBlankFact] = useState("1.0")
  const [lcmsGrpResult, setLcmsGrpResult] = useState<unknown>(null)
  const [lcmsGrpError, setLcmsGrpError] = useState("")
  const [lcmsGrpLoading, setLcmsGrpLoading] = useState(false)

  const [lcmsConFeatTable, setLcmsConFeatTable] = useState("")
  const [lcmsConFormula, setLcmsConFormula] = useState("")
  const [lcmsConPromote, setLcmsConPromote] = useState("0.62")
  const [lcmsConIso, setLcmsConIso] = useState(true)
  const [lcmsConAdductScore, setLcmsConAdductScore] = useState(true)
  const [lcmsConLoss, setLcmsConLoss] = useState(true)
  const [lcmsConExpectedAdduct, setLcmsConExpectedAdduct] = useState<string>("[M+H]+")
  const [lcmsConResult, setLcmsConResult] = useState<unknown>(null)
  const [lcmsConError, setLcmsConError] = useState("")
  const [lcmsConLoading, setLcmsConLoading] = useState(false)

  const [lcmsDerCandidatesText, setLcmsDerCandidatesText] = useState(candidatesText)
  const [lcmsDerFamilyTable, setLcmsDerFamilyTable] = useState("")
  const [lcmsDerPrecursorMz, setLcmsDerPrecursorMz] = useState("")
  const [lcmsDerMsmsPeaks, setLcmsDerMsmsPeaks] = useState("")
  const [lcmsDerRt, setLcmsDerRt] = useState("")
  const [lcmsDerCcs, setLcmsDerCcs] = useState("")
  const [lcmsDerAdduct, setLcmsDerAdduct] = useState("[M+H]+")
  const [lcmsDerMzTol, setLcmsDerMzTol] = useState("0.02")
  const [lcmsDerPpmTol, setLcmsDerPpmTol] = useState("10")
  const [lcmsDerMinFam, setLcmsDerMinFam] = useState("0.42")
  const [lcmsDerReqPromoted, setLcmsDerReqPromoted] = useState(true)
  const [lcmsDerSelectedFamilyId, setLcmsDerSelectedFamilyId] = useState("")
  const [lcmsDerResult, setLcmsDerResult] = useState<unknown>(null)
  const [lcmsDerError, setLcmsDerError] = useState("")
  const [lcmsDerLoading, setLcmsDerLoading] = useState(false)

  const [lcmsBridgeCandidatesText, setLcmsBridgeCandidatesText] = useState(candidatesText)
  const [lcmsBridgeAdduct, setLcmsBridgeAdduct] = useState("[M+H]+")
  const [lcmsBridgePpm, setLcmsBridgePpm] = useState("10")
  const [lcmsBridgeMzDa, setLcmsBridgeMzDa] = useState("0.02")
  const [lcmsBridgeMinFam, setLcmsBridgeMinFam] = useState("0.42")
  const [lcmsBridgeReqPromoted, setLcmsBridgeReqPromoted] = useState(true)
  const [lcmsBridgeFamilyTable, setLcmsBridgeFamilyTable] = useState("")
  const [lcmsBridgeSelectedFamilyId, setLcmsBridgeSelectedFamilyId] = useState("")
  const [lcmsBridgeResult, setLcmsBridgeResult] = useState<unknown>(null)
  const [lcmsBridgeError, setLcmsBridgeError] = useState("")
  const [lcmsBridgeLoading, setLcmsBridgeLoading] = useState(false)

  useEffect(() => {
    setLcmsDerCandidatesText(candidatesText)
  }, [candidatesText])

  useEffect(() => {
    setLcmsBridgeCandidatesText(candidatesText)
  }, [candidatesText])

  const reportHashCopyEnabled = Boolean(lcmsReportReady && onLcmsHashForReport)

  const ws = useOptionalSpectraCheckWorkspaceSession()
  const lcmsImportJob = useAnalysisJob()
  const lcmsFeatureJob = useAnalysisJob()

  const lcmsSessionLikeFiles = (ws?.sessionFiles ?? []).filter(
    (f) =>
      f.file_kind.startsWith("lcms") ||
      /\.(mzml|mzxml|xml|csv|tsv|txt)$/i.test(f.filename),
  )

  function inferLcmsUploadKind(file: File): string {
    const n = file.name.toLowerCase()
    if (n.endsWith(".mzml")) return "lcms_mzml"
    if (n.endsWith(".mzxml")) return "lcms_mzxml"
    return "lcms_peak_table"
  }

  async function ensureLcmsImportFileId(): Promise<string | null> {
    if (lcmsImportSessionFileId.trim()) return lcmsImportSessionFileId.trim()
    const f = lcmsImportFileRef.current?.files?.[0]
    if (!f) return null
    const fd = new FormData()
    fd.append("file", f)
    fd.append("file_kind", inferLcmsUploadKind(f))
    const data = await apiFetch<unknown>("/files/upload", { method: "POST", body: fd })
    const rec = normalizeSessionFileRecord(data)
    const kind = inferLcmsUploadKind(f)
    trackFileUploaded({
      session_id: ws?.backendSessionId ?? undefined,
      metadata: {
        file_kind: kind,
        file_size_bytes: f.size,
        has_sha256: Boolean(rec?.sha256),
      },
    })
    await ws?.refreshSessionFiles()
    return rec?.file_id ?? null
  }

  async function ensureLcmsFeatureFileId(): Promise<string | null> {
    if (lcmsFeatureSessionFileId.trim()) return lcmsFeatureSessionFileId.trim()
    const f = lcmsFeatureFileRef.current?.files?.[0]
    if (!f) return null
    const fd = new FormData()
    fd.append("file", f)
    fd.append("file_kind", inferLcmsUploadKind(f))
    const data = await apiFetch<unknown>("/files/upload", { method: "POST", body: fd })
    const rec = normalizeSessionFileRecord(data)
    const kind = inferLcmsUploadKind(f)
    trackFileUploaded({
      session_id: ws?.backendSessionId ?? undefined,
      metadata: {
        file_kind: kind,
        file_size_bytes: f.size,
        has_sha256: Boolean(rec?.sha256),
      },
    })
    await ws?.refreshSessionFiles()
    return rec?.file_id ?? null
  }

  async function startLcmsImportJob() {
    setLcmsImportJobErr("")
    try {
      const fid = await ensureLcmsImportFileId()
      if (!fid) {
        setLcmsImportJobErr("Choose a session LC-MS file or pick a local file.")
        return
      }
      const sid = lcmsImportSourceLabel.trim() || sampleId.trim()
      const jid = await lcmsImportJob.createJob(
        buildAnalysisJobPayload({
          sessionId: ws?.backendSessionId ?? null,
          sampleId,
          jobType: "lcms_import",
          inputFileIds: [fid],
          parameters: {
            source_format: "auto",
            ...(sid ? { sample_id: sid } : {}),
            ...(lcmsImportPrecursorMz.trim() ? { preferred_msms_precursor_mz: lcmsImportPrecursorMz.trim() } : {}),
          },
        }),
      )
      if (jid) ws?.registerAnalysisJob(jid)
    } catch (e) {
      setLcmsImportJobErr(formatApiError(e, "Could not start LC-MS import job"))
    }
  }

  async function startLcmsFeatureDetectionJob() {
    setLcmsFeatureJobErr("")
    try {
      const fid = await ensureLcmsFeatureFileId()
      if (!fid) {
        setLcmsFeatureJobErr("Choose a session LC-MS file or pick a local file.")
        return
      }
      const jid = await lcmsFeatureJob.createJob(
        buildAnalysisJobPayload({
          sessionId: ws?.backendSessionId ?? null,
          sampleId,
          jobType: "lcms_feature_detection",
          inputFileIds: [fid],
          parameters: {
            source_format: "auto",
            ...(lcmsFeatTargetMz.trim() ? { target_mz_text: lcmsFeatTargetMz.trim() } : {}),
            mz_tolerance_da: Number(lcmsFeatMzTol.trim() || "0.02"),
            ppm_tolerance: Number(lcmsFeatPpmTol.trim() || "20"),
            min_relative_feature_height: Number(lcmsFeatMinRelH.trim() || "5"),
            min_scans_per_feature: Number(lcmsFeatMinScans.trim() || "2"),
            smoothing_window: Number(lcmsFeatSmooth.trim() || "1"),
            purity_rt_window_min: Number(lcmsFeatPurityWin.trim() || "0.2"),
            top_coeluting_ions: Number(lcmsFeatTopCo.trim() || "5"),
            max_features: Number(lcmsFeatMaxFeat.trim() || "20"),
            ...(sampleId.trim() ? { sample_id: sampleId.trim() } : {}),
          },
        }),
      )
      if (jid) ws?.registerAnalysisJob(jid)
    } catch (e) {
      setLcmsFeatureJobErr(formatApiError(e, "Could not start LC-MS feature detection job"))
    }
  }

  function copyLcmsImportToMsWorkflows() {
    if (!isRecord(lcmsImportResult)) return
    const ms1 =
      typeof lcmsImportResult.extracted_ms1_peak_list_text === "string"
        ? lcmsImportResult.extracted_ms1_peak_list_text
        : ""
    const msms =
      typeof lcmsImportResult.extracted_msms_peak_list_text === "string"
        ? lcmsImportResult.extracted_msms_peak_list_text
        : ""
    if (ms1.trim()) setMs1PeakList(ms1)
    if (msms.trim()) {
      setMsmsPeakList(msms)
      setFragPeakList(msms)
    }
    const pmz = lcmsImportResult.primary_ms1_mz
    if (typeof pmz === "number") {
      const s = String(pmz)
      setAdductTargetMz(s)
      setMsmsPrecursorMz(s)
      setFragPrecursorMz(s)
    }
  }

  function copyImportHashForReport() {
    if (!reportHashCopyEnabled || !isRecord(lcmsImportResult) || !onLcmsHashForReport) return
    const h = lcmsImportResult.file_sha256
    if (typeof h === "string" && h.length > 0) onLcmsHashForReport(h)
  }

  function applyBestAdductFromInference() {
    if (!isRecord(adductResult)) return
    const best = adductResult.best_adduct_candidate
    if (!isRecord(best)) return
    const addObj = isRecord(best.adduct) ? best.adduct : null
    const adductName =
      isRecord(addObj) && typeof addObj.name === "string" && addObj.name.length > 0 ? addObj.name : "[M+H]+"
    const obsMz =
      typeof best.observed_mz === "number"
        ? String(best.observed_mz)
        : typeof adductResult.primary_mz === "number"
          ? String(adductResult.primary_mz)
          : ""
    if (obsMz) {
      setHrmsObservedMz(obsMz)
      setMsmsPrecursorMz(obsMz)
    }
    setHrmsAdduct(adductName)
    setMsmsAdduct(adductName)
    setFragAdduct(adductName)
    if (typeof adductResult.inferred_m_plus_1_percent === "number") {
      setHrmsM1(String(adductResult.inferred_m_plus_1_percent))
    }
    if (typeof adductResult.inferred_m_plus_2_percent === "number") {
      setHrmsM2(String(adductResult.inferred_m_plus_2_percent))
    }
  }

  function copyAdductInferenceToHrms() {
    if (!isRecord(adductResult)) return
    if (typeof adductResult.primary_mz === "number") {
      setHrmsObservedMz(String(adductResult.primary_mz))
    }
    const best = adductResult.best_adduct_candidate
    if (isRecord(best) && isRecord(best.adduct) && typeof best.adduct.name === "string") {
      setHrmsAdduct(best.adduct.name)
    }
  }

  function copyAdductInferenceToMsms() {
    if (!isRecord(adductResult)) return
    const best = adductResult.best_adduct_candidate
    const prec =
      isRecord(best) && typeof best.observed_mz === "number"
        ? String(best.observed_mz)
        : typeof adductResult.primary_mz === "number"
          ? String(adductResult.primary_mz)
          : null
    if (prec) setMsmsPrecursorMz(prec)
    if (isRecord(best) && isRecord(best.adduct) && typeof best.adduct.name === "string") {
      setMsmsAdduct(best.adduct.name)
    }
  }

  async function runHrmsMatch(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    setHrmsMatchLoading(true)
    setHrmsMatchError("")
    setHrmsMatchResult(null)
    const fd = new FormData()
    fd.append("candidates_text", hrmsCandidatesText.trim())
    fd.append("observed_mz", hrmsObservedMz.trim())
    fd.append("adduct", hrmsAdduct.trim() || "[M+H]+")
    if (hrmsIonMode !== "auto") fd.append("ion_mode", hrmsIonMode.trim())
    fd.append("ppm_tolerance", hrmsPpmTol.trim() || "5")
    if (hrmsM1.trim()) fd.append("observed_m_plus_1_percent", hrmsM1.trim())
    if (hrmsM2.trim()) fd.append("observed_m_plus_2_percent", hrmsM2.trim())
    if (sampleId.trim()) fd.append("sample_id", sampleId.trim())
    try {
      const data = await apiFetch<unknown>("/ms/hrms/candidates/match/evidence", { method: "POST", body: fd })
      setHrmsMatchResult(data)
    } catch (err) {
      setHrmsMatchError(formatApiError(err, "HRMS candidate match failed"))
    } finally {
      setHrmsMatchLoading(false)
    }
  }

  async function runFormulaSearch(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    setFormulaLoading(true)
    setFormulaError("")
    setFormulaResult(null)
    const observed = Number(formulaObservedMz.trim())
    if (!Number.isFinite(observed) || observed <= 0) {
      setFormulaError("Enter a positive observed m/z.")
      setFormulaLoading(false)
      return
    }
    const maxC = Number(formulaMaxC.trim() || "40")
    const maxResults = Number(formulaMaxResults.trim() || "50")
    const payload = {
      observed_mz: observed,
      adduct: formulaAdduct.trim() || "[M+H]+",
      ppm_tolerance: Number(formulaPpmTol.trim() || "5"),
      max_c: Number.isFinite(maxC) ? maxC : 40,
      max_results: Number.isFinite(maxResults) ? maxResults : 50,
    }
    try {
      const data = await apiFetch<unknown>("/ms/hrms/formulas/search", {
        method: "POST",
        body: JSON.stringify(payload),
      })
      setFormulaResult(data)
    } catch (err) {
      setFormulaError(formatApiError(err, "HRMS formula search failed"))
    } finally {
      setFormulaLoading(false)
    }
  }

  async function runAdductInfer(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    setAdductLoading(true)
    setAdductError("")
    setAdductResult(null)
    const fd = new FormData()
    fd.append("peak_list_text", ms1PeakList)
    if (adductIonMode !== "auto") fd.append("ion_mode", adductIonMode.trim() || "positive")
    if (adductTargetMz.trim()) fd.append("target_mz", adductTargetMz.trim())
    fd.append("mz_tolerance_da", adductMzTolDa.trim() || "0.02")
    fd.append("ppm_tolerance", adductPpmTol.trim() || "10")
    fd.append("isotope_mz_tolerance_da", adductIsoTolDa.trim() || "0.02")
    fd.append("min_relative_intensity", adductMinRelInt.trim() || "0.2")
    fd.append("max_peaks_to_analyze", adductMaxPeaks.trim() || "200")
    fd.append("max_charge", adductMaxCharge.trim() || "3")
    fd.append("perform_formula_search", adductFormulaSearch ? "true" : "false")
    fd.append("formula_candidates_per_adduct", adductFormulaPerAdduct.trim() || "5")
    fd.append("max_c", adductMaxC.trim() || "20")
    if (sampleId.trim()) fd.append("sample_id", sampleId.trim())
    try {
      const data = await apiFetch<unknown>("/ms/adducts/infer/evidence", { method: "POST", body: fd })
      setAdductResult(data)
    } catch (err) {
      setAdductError(formatApiError(err, "Adduct / isotope inference failed"))
    } finally {
      setAdductLoading(false)
    }
  }

  async function runMsmsAnnotate(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    setMsmsLoading(true)
    setMsmsError("")
    setMsmsResult(null)
    const fd = new FormData()
    fd.append("peak_list_text", msmsPeakList)
    fd.append("precursor_mz", msmsPrecursorMz.trim())
    fd.append("adduct", msmsAdduct.trim() || "[M+H]+")
    fd.append("mz_tolerance_da", msmsMzTolDa.trim() || "0.02")
    fd.append("ppm_tolerance", msmsPpmTol.trim() || "20")
    fd.append("min_relative_intensity", msmsMinRelInt.trim() || "1")
    fd.append("max_peaks_to_annotate", msmsMaxPeaks.trim() || "50")
    if (msmsCandidatesText.trim()) fd.append("candidates_text", msmsCandidatesText.trim())
    if (sampleId.trim()) fd.append("sample_id", sampleId.trim())
    try {
      const data = await apiFetch<unknown>("/ms/msms/annotate/evidence", { method: "POST", body: fd })
      setMsmsResult(data)
    } catch (err) {
      setMsmsError(formatApiError(err, "Processed MS/MS annotation failed"))
    } finally {
      setMsmsLoading(false)
    }
  }

  async function runFragTree(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    setFragLoading(true)
    setFragError("")
    setFragResult(null)
    const fd = new FormData()
    fd.append("peak_list_text", fragPeakList)
    fd.append("precursor_mz", fragPrecursorMz.trim())
    fd.append("adduct", fragAdduct.trim() || "[M+H]+")
    fd.append("mz_tolerance_da", fragMzTolDa.trim() || "0.02")
    fd.append("ppm_tolerance", fragPpmTol.trim() || "20")
    fd.append("min_relative_intensity", fragMinRelInt.trim() || "1")
    fd.append("max_peaks_to_analyze", fragMaxPeaks.trim() || "75")
    fd.append("max_tree_depth", fragMaxDepth.trim() || "3")
    if (fragCandidatesText.trim()) fd.append("candidates_text", fragCandidatesText.trim())
    if (sampleId.trim()) fd.append("sample_id", sampleId.trim())
    try {
      const data = await apiFetch<unknown>("/ms/msms/fragmentation-tree/evidence", { method: "POST", body: fd })
      setFragResult(data)
    } catch (err) {
      setFragError(formatApiError(err, "Fragmentation-tree evidence failed"))
    } finally {
      setFragLoading(false)
    }
  }

  async function runLcmsImport(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    const f = lcmsImportFileRef.current?.files?.[0]
    if (!f) {
      setLcmsImportError("Choose an LC-MS/MS file.")
      return
    }
    setLcmsImportLoading(true)
    setLcmsImportError("")
    setLcmsImportResult(null)
    const fd = new FormData()
    fd.append("file", f)
    fd.append("source_format", "auto")
    const sid = lcmsImportSourceLabel.trim() || sampleId.trim()
    if (sid) fd.append("sample_id", sid)
    if (lcmsImportPrecursorMz.trim()) fd.append("preferred_msms_precursor_mz", lcmsImportPrecursorMz.trim())
    try {
      const data = await apiFetch<unknown>("/ms/lcms/import/bridge/upload", { method: "POST", body: fd })
      setLcmsImportResult(data)
    } catch (err) {
      setLcmsImportError(formatApiError(err, "LC-MS import bridge failed"))
    } finally {
      setLcmsImportLoading(false)
    }
  }

  async function runLcmsFeatureDetect(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    const f = lcmsFeatureFileRef.current?.files?.[0]
    if (!f) {
      setLcmsFeatureError("Choose an LC-MS/MS file.")
      return
    }
    setLcmsFeatureLoading(true)
    setLcmsFeatureError("")
    setLcmsFeatureResult(null)
    const fd = new FormData()
    fd.append("file", f)
    fd.append("source_format", "auto")
    if (lcmsFeatTargetMz.trim()) fd.append("target_mz_text", lcmsFeatTargetMz.trim())
    fd.append("mz_tolerance_da", lcmsFeatMzTol.trim() || "0.02")
    fd.append("ppm_tolerance", lcmsFeatPpmTol.trim() || "20")
    fd.append("min_relative_feature_height", lcmsFeatMinRelH.trim() || "5")
    fd.append("min_scans_per_feature", lcmsFeatMinScans.trim() || "2")
    fd.append("smoothing_window", lcmsFeatSmooth.trim() || "1")
    fd.append("purity_rt_window_min", lcmsFeatPurityWin.trim() || "0.2")
    fd.append("top_coeluting_ions", lcmsFeatTopCo.trim() || "5")
    fd.append("max_features", lcmsFeatMaxFeat.trim() || "20")
    if (sampleId.trim()) fd.append("sample_id", sampleId.trim())
    try {
      const data = await apiFetch<unknown>("/ms/lcms/features/detect/upload", { method: "POST", body: fd })
      setLcmsFeatureResult(data)
    } catch (err) {
      setLcmsFeatureError(formatApiError(err, "LC-MS feature detection failed"))
    } finally {
      setLcmsFeatureLoading(false)
    }
  }

  function fillConsensusTableFromGrouping() {
    if (!isRecord(lcmsGrpResult)) return
    const ft = lcmsGrpResult.feature_table_text
    if (typeof ft === "string" && ft.trim().length > 0) setLcmsConFeatTable(ft)
  }

  function fillBridgeTableFromConsensus() {
    if (!isRecord(lcmsConResult)) return
    const ft = lcmsConResult.family_table_text
    if (typeof ft === "string" && ft.trim().length > 0) setLcmsBridgeFamilyTable(ft)
  }

  function fillDerepFamilyTableFromConsensus() {
    if (!isRecord(lcmsConResult)) return
    const ft = lcmsConResult.family_table_text
    if (typeof ft === "string" && ft.trim().length > 0) setLcmsDerFamilyTable(ft)
  }

  async function runLcmsAdvGroup(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    setLcmsGrpLoading(true)
    setLcmsGrpError("")
    setLcmsGrpResult(null)
    let sampleText = lcmsGrpSampleText.trim()
    const sf = lcmsGrpSampleFileRef.current?.files?.[0]
    if (sf) sampleText = await sf.text()
    let blankText = lcmsGrpBlankText.trim()
    const bf = lcmsGrpBlankFileRef.current?.files?.[0]
    if (bf) blankText = await bf.text()
    if (!sampleText.trim()) {
      setLcmsGrpError("Provide sample peak table text or upload a sample file.")
      setLcmsGrpLoading(false)
      return
    }
    const fd = new FormData()
    fd.append("sample_source_text", sampleText)
    if (blankText.trim()) fd.append("blank_source_text", blankText)
    fd.append("source_format", "auto")
    fd.append("group_rt_tolerance_min", lcmsGrpRtTol.trim() || "0.12")
    fd.append("mz_tolerance_da", lcmsGrpMzTol.trim() || "0.02")
    fd.append("ppm_tolerance", lcmsGrpPpmTol.trim() || "20")
    fd.append("blank_area_ratio_threshold", lcmsGrpBlankRatio.trim() || "0.30")
    fd.append("possible_background_ratio_threshold", lcmsGrpPossBg.trim() || "0.10")
    fd.append("blank_subtraction_factor", lcmsGrpBlankFact.trim() || "1.0")
    if (sampleId.trim()) fd.append("sample_id", sampleId.trim())
    try {
      const data = await apiFetch<unknown>("/ms/lcms/features/group/evidence", { method: "POST", body: fd })
      setLcmsGrpResult(data)
    } catch (err) {
      setLcmsGrpError(formatApiError(err, "LC-MS feature grouping failed"))
    } finally {
      setLcmsGrpLoading(false)
    }
  }

  async function runLcmsAdvConsensus(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    setLcmsConLoading(true)
    setLcmsConError("")
    setLcmsConResult(null)
    let featText = lcmsConFeatTable.trim()
    const ftFile = lcmsConFeatFileRef.current?.files?.[0]
    if (ftFile) featText = await ftFile.text()
    if (!featText.trim()) {
      setLcmsConError("Provide grouped feature table text or upload a feature table file.")
      setLcmsConLoading(false)
      return
    }
    const fd = new FormData()
    fd.append("feature_table_text", featText)
    if (lcmsConFormula.trim()) fd.append("formula", lcmsConFormula.trim())
    fd.append("min_consensus_score_to_promote", lcmsConPromote.trim() || "0.62")
    fd.append("expected_anchor_adduct", lcmsConExpectedAdduct.trim() || "[M+H]+")
    fd.append("score_isotope_relationships", lcmsConIso ? "true" : "false")
    fd.append("score_adduct_relationships", lcmsConAdductScore ? "true" : "false")
    fd.append("score_in_source_losses", lcmsConLoss ? "true" : "false")
    if (sampleId.trim()) fd.append("sample_id", sampleId.trim())
    try {
      const data = await apiFetch<unknown>("/ms/lcms/features/consensus/evidence", { method: "POST", body: fd })
      setLcmsConResult(data)
    } catch (err) {
      setLcmsConError(formatApiError(err, "LC-MS feature-family consensus failed"))
    } finally {
      setLcmsConLoading(false)
    }
  }

  async function runLcmsAdvDereplication(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    setLcmsDerLoading(true)
    setLcmsDerError("")
    setLcmsDerResult(null)
    let candText = lcmsDerCandidatesText.trim()
    const libFile = lcmsDerLibraryFileRef.current?.files?.[0]
    if (libFile) candText = await libFile.text()
    const commentLines: string[] = []
    if (lcmsDerPrecursorMz.trim()) commentLines.push(`# user_precursor_mz: ${lcmsDerPrecursorMz.trim()}`)
    if (lcmsDerRt.trim()) commentLines.push(`# user_rt_min: ${lcmsDerRt.trim()}`)
    if (lcmsDerCcs.trim()) commentLines.push(`# user_ccs: ${lcmsDerCcs.trim()}`)
    let msmsSection = ""
    if (lcmsDerMsmsPeaks.trim()) {
      msmsSection = lcmsDerMsmsPeaks
        .trim()
        .split("\n")
        .map((ln) => (ln.trim() ? `# msms ${ln}` : ""))
        .filter(Boolean)
        .join("\n")
    }
    const mergedCandidates = [commentLines.join("\n"), msmsSection, candText].filter((s) => s.trim().length > 0).join("\n\n")
    if (!mergedCandidates.trim() && !lcmsDerFamilyTable.trim()) {
      setLcmsDerError("Provide library candidates and/or LC-MS family table text (or upload a library file).")
      setLcmsDerLoading(false)
      return
    }
    const fd = new FormData()
    if (mergedCandidates.trim()) fd.append("candidates_text", mergedCandidates)
    if (lcmsDerFamilyTable.trim()) fd.append("lcms_family_table_text", lcmsDerFamilyTable.trim())
    fd.append("adduct", lcmsDerAdduct.trim() || "[M+H]+")
    fd.append("mz_tolerance_da", lcmsDerMzTol.trim() || "0.02")
    fd.append("ppm_tolerance", lcmsDerPpmTol.trim() || "10")
    fd.append("min_family_consensus_score", lcmsDerMinFam.trim() || "0.42")
    fd.append("require_promoted_family", lcmsDerReqPromoted ? "true" : "false")
    if (lcmsDerSelectedFamilyId.trim()) fd.append("selected_family_id", lcmsDerSelectedFamilyId.trim())
    if (sampleId.trim()) fd.append("sample_id", sampleId.trim())
    try {
      const data = await apiFetch<unknown>("/ms/lcms/dereplication/evidence", { method: "POST", body: fd })
      setLcmsDerResult(data)
    } catch (err) {
      setLcmsDerError(formatApiError(err, "LC-MS library dereplication failed"))
    } finally {
      setLcmsDerLoading(false)
    }
  }

  async function runLcmsAdvBridge(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    setLcmsBridgeLoading(true)
    setLcmsBridgeError("")
    setLcmsBridgeResult(null)
    const candidates = parseCandidateInputs(lcmsBridgeCandidatesText)
    if (candidates.length === 0) {
      setLcmsBridgeError("Provide at least one candidate structure line (name | SMILES | role).")
      setLcmsBridgeLoading(false)
      return
    }
    const tableText = lcmsBridgeFamilyTable.trim()
    const hasConsensusObj = isRecord(lcmsConResult)
    if (!tableText && !hasConsensusObj) {
      setLcmsBridgeError("Paste consensus family table text, or run feature-family consensus in this panel first.")
      setLcmsBridgeLoading(false)
      return
    }
    const payload: Record<string, unknown> = {
      candidates,
      adduct: lcmsBridgeAdduct.trim() || "[M+H]+",
      mz_tolerance_da: Number(lcmsBridgeMzDa.trim() || "0.02"),
      ppm_tolerance: Number(lcmsBridgePpm.trim() || "10"),
      min_family_consensus_score: Number(lcmsBridgeMinFam.trim() || "0.42"),
      require_promoted_family: lcmsBridgeReqPromoted,
      selected_family_id: lcmsBridgeSelectedFamilyId.trim() || null,
      lcms_family_table_text: tableText || null,
    }
    if (sampleId.trim()) payload.sample_id = sampleId.trim()
    if (hasConsensusObj) payload.lcms_consensus_result = lcmsConResult
    try {
      const data = await apiFetch<unknown>("/confidence/candidates/lcms-consensus-bridge", {
        method: "POST",
        body: JSON.stringify(payload),
      })
      setLcmsBridgeResult(data)
    } catch (err) {
      setLcmsBridgeError(formatApiError(err, "LC-MS consensus bridge failed"))
    } finally {
      setLcmsBridgeLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <ModuleCard
        accent="teal"
        eyebrow="MS · Interpretation"
        title={
          <span className="inline-flex items-center gap-2">
            MS evidence interpretation
            <InfoTooltip
              label="MS evidence"
              content="Mass spectrometry evidence modules; all outputs are decision-support and need expert review."
            />
          </span>
        }
        description={
          <>
            Outputs are decision-support only. Labels describe how experimental inputs relate to each row—they may{" "}
            <strong>support</strong> or <strong>contradict</strong> a candidate; ambiguous cases{" "}
            <strong>require review</strong>. Treat strong agreement as <strong>plausible evidence</strong>, not proof of
            identity or connectivity.
          </>
        }
      />

      <Tabs defaultValue="hrms-exact" className="w-full min-w-0">
        <div className="min-w-0 overflow-x-auto pb-2 [-webkit-overflow-scrolling:touch]">
          <TabsList className="inline-flex h-auto min-h-9 w-max min-w-0 max-w-full flex-nowrap justify-start gap-1 sm:flex-wrap">
            <MsEvidenceTabWithTooltip
              value="hrms-exact"
              tooltip="Exact-mass (HRMS) match of candidates to an observed m/z and adduct."
            >
              HRMS exact mass
            </MsEvidenceTabWithTooltip>
            <MsEvidenceTabWithTooltip
              value="formula-search"
              tooltip="Enumerate plausible formulas from accurate mass, adduct, and ppm bounds."
            >
              Formula search
            </MsEvidenceTabWithTooltip>
            <MsEvidenceTabWithTooltip
              value="adduct"
              tooltip="Infer adducts, charge, and isotope clusters from processed MS1 peak lists."
            >
              Adduct + isotope
            </MsEvidenceTabWithTooltip>
            <MsEvidenceTabWithTooltip
              value="msms"
              tooltip="Annotate centroid MS/MS spectra vs. candidates and neutral losses."
            >
              Processed MS/MS
            </MsEvidenceTabWithTooltip>
            <MsEvidenceTabWithTooltip
              value="frag-tree"
              tooltip="Hypothesized fragmentation pathways and diagnostic neutral losses."
            >
              Fragmentation tree
            </MsEvidenceTabWithTooltip>
            <MsEvidenceTabWithTooltip
              value="lcms-import"
              tooltip="Import mzML/mzXML or tables; extract MS1/MS2 peaks and traceability hashes."
            >
              LC-MS import
            </MsEvidenceTabWithTooltip>
            <MsEvidenceTabWithTooltip
              value="lcms-features"
              tooltip="Chromatographic features, XIC/EIC, purity, and linked MS/MS context."
            >
              LC-MS features
            </MsEvidenceTabWithTooltip>
            <MsEvidenceTabWithTooltip
              value="lcms-adv-group"
              tooltip="Align retention times, subtract blank/QC signal, and group ions across runs."
            >
              LC-MS grouping
            </MsEvidenceTabWithTooltip>
            <MsEvidenceTabWithTooltip
              value="lcms-adv-consensus"
              tooltip="Feature-family scoring: isotope, adduct, in-source loss, and linkage consistency."
            >
              LC-MS consensus
            </MsEvidenceTabWithTooltip>
            <MsEvidenceTabWithTooltip
              value="lcms-adv-derep"
              tooltip="Rank library candidates vs. LC-MS consensus evidence (decision-support)."
            >
              LC-MS dereplication
            </MsEvidenceTabWithTooltip>
            <MsEvidenceTabWithTooltip
              value="lcms-adv-bridge"
              tooltip="Map theoretical candidate m/z to promoted LC-MS feature-family anchors."
            >
              LC-MS bridge
            </MsEvidenceTabWithTooltip>
          </TabsList>
        </div>

        <TabsContent value="hrms-exact" className="mt-4 space-y-6">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
            <ModuleCard
              accent="teal"
              eyebrow="MS · HRMS"
              title={
                <span className="inline-flex items-center gap-2">
                  HRMS exact-mass candidate match
                  <InfoTooltip
                    label="About HRMS candidate match"
                    content="Use high-resolution MS to constrain candidates by exact mass, adduct, ppm error, isotope hints, and DBE/IHD."
                  />
                </span>
              }
              description="Match candidates by high-resolution exact mass, adduct form, ppm error tolerance, isotope pattern, and degree of unsaturation (DBE/IHD)."
              className="min-w-0"
            >
                <form onSubmit={runHrmsMatch} className="space-y-4">
                  <label className="block space-y-2">
                    <FieldLabelTip label="Observed m/z" tip="Monoisotopic or centroid m/z used as the experimental ion mass." />
                    <Input value={hrmsObservedMz} onChange={(e) => setHrmsObservedMz(e.target.value)} required />
                  </label>
                  <div className="space-y-2">
                    <FieldLabelTip label="Adduct" tip="Ionizing adduct for theoretical neutral mass and fragment annotation." />
                    <Select value={hrmsAdduct} onValueChange={setHrmsAdduct}>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Adduct" />
                      </SelectTrigger>
                      <SelectContent>
                        {HRMS_ADDUCT_OPTIONS.map((a) => (
                          <SelectItem key={a} value={a}>
                            {a}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <label className="block space-y-2">
                    <FieldLabelTip label="ppm tolerance" tip="Mass accuracy window in parts per million vs. theoretical m/z." />
                    <Input value={hrmsPpmTol} onChange={(e) => setHrmsPpmTol(e.target.value)} />
                  </label>
                  <div className="space-y-2">
                    <span className="text-sm font-medium">Ion mode</span>
                    <Select value={hrmsIonMode} onValueChange={setHrmsIonMode}>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {ION_MODE_OPTIONS.map((o) => (
                          <SelectItem key={o.label} value={o.value}>
                            {o.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Observed M+1 % (optional)</span>
                    <Input value={hrmsM1} onChange={(e) => setHrmsM1(e.target.value)} />
                  </label>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Observed M+2 % (optional)</span>
                    <Input value={hrmsM2} onChange={(e) => setHrmsM2(e.target.value)} />
                  </label>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Candidate structures</span>
                    <Textarea
                      value={hrmsCandidatesText}
                      onChange={(e) => setHrmsCandidatesText(e.target.value)}
                      rows={6}
                      placeholder="Pipe-separated name | SMILES | role lines — synced from Shared session inputs when they change."
                    />
                  </label>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button type="submit" disabled={hrmsMatchLoading} className="w-full sm:w-auto">
                        {hrmsMatchLoading ? "Running…" : "Match candidates by HRMS"}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs text-xs">
                      Submit HRMS candidate match with current m/z, adduct, and ppm window.
                    </TooltipContent>
                  </Tooltip>
                </form>
            </ModuleCard>
            <div className="min-w-0 space-y-6">
              <TabResultSection
                error={hrmsMatchError}
                loading={hrmsMatchLoading}
                loadingTitle="Running HRMS candidate match"
                loadingHint="Matching candidates against HRMS data…"
                emptyHint="Enter observed m/z and candidate structures, then run."
                result={hrmsMatchResult}
                summaryTone="ms"
                unifiedEvidence={{
                  layer: "hrms_exact_mass",
                  sourceTab: "MS Evidence",
                  title: "HRMS candidate match",
                  endpoint: "/ms/hrms/candidates/match/evidence",
                  sampleId: sampleId.trim() || undefined,
                }}
              />
              {!hrmsMatchLoading && hrmsMatchResult != null && (
                <HrmsMatchDetailTables result={hrmsMatchResult} />
              )}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="formula-search" className="mt-4 space-y-6">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
            <ModuleCard
              accent="teal"
              eyebrow="MS · Formula"
              title={
                <span className="inline-flex items-center gap-2">
                  Formula search beta
                  <InfoTooltip
                    label="About formula search"
                    content="Search bounded CHNOPSClBr formulas from exact mass. Use this as formula triage, not final identification."
                  />
                </span>
              }
              description="Search candidate molecular formulas from observed exact mass within CHNOPSClBr composition limits. Use as a screening step, not final identification."
              className="min-w-0"
            >
                <form onSubmit={runFormulaSearch} className="space-y-4">
                  <label className="block space-y-2">
                    <FieldLabelTip label="Observed m/z" tip="Monoisotopic or centroid m/z used as the experimental ion mass." />
                    <Input value={formulaObservedMz} onChange={(e) => setFormulaObservedMz(e.target.value)} required />
                  </label>
                  <div className="space-y-2">
                    <FieldLabelTip label="Adduct" tip="Ionizing adduct for theoretical neutral mass and fragment annotation." />
                    <Select value={formulaAdduct} onValueChange={setFormulaAdduct}>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Adduct" />
                      </SelectTrigger>
                      <SelectContent>
                        {HRMS_ADDUCT_OPTIONS.map((a) => (
                          <SelectItem key={a} value={a}>
                            {a}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <label className="block space-y-2">
                    <FieldLabelTip label="ppm tolerance" tip="Mass accuracy window in parts per million vs. theoretical m/z." />
                    <Input value={formulaPpmTol} onChange={(e) => setFormulaPpmTol(e.target.value)} />
                  </label>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Max C</span>
                    <Input value={formulaMaxC} onChange={(e) => setFormulaMaxC(e.target.value)} />
                  </label>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Max results</span>
                    <Input value={formulaMaxResults} onChange={(e) => setFormulaMaxResults(e.target.value)} />
                  </label>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button type="submit" disabled={formulaLoading} className="w-full sm:w-auto">
                        {formulaLoading ? "Searching…" : "Search formulas"}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs text-xs">
                      Run bounded HRMS formula enumeration from observed mass and adduct.
                    </TooltipContent>
                  </Tooltip>
                </form>
            </ModuleCard>
            <div className="min-w-0 space-y-6">
              <TabResultSection
                error={formulaError}
                loading={formulaLoading}
                loadingTitle="Searching formulas by HRMS"
                loadingHint="Searching molecular formulas for the target mass…"
                emptyHint="Set observed m/z, adduct, and tolerances, then search."
                result={formulaResult}
                summaryTone="ms"
                unifiedEvidence={{
                  layer: "formula_search",
                  sourceTab: "MS Evidence",
                  title: "Formula search",
                  endpoint: "/ms/hrms/formulas/search",
                  sampleId: sampleId.trim() || undefined,
                }}
              />
              {!formulaLoading && formulaResult != null && <FormulaSearchDetailTables result={formulaResult} />}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="adduct" className="mt-4 space-y-6">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
            <ModuleCard
              accent="teal"
              eyebrow="MS · Adduct"
              title={
                <span className="inline-flex items-center gap-2">
                  Adduct + isotope pattern inference
                  <InfoTooltip
                    label="About adduct + isotope inference"
                    content="Infer likely adducts, charge state, isotope clusters, carbon-count hints, halogen patterns, and formula candidates from processed MS1/HRMS peaks."
                  />
                </span>
              }
              description="Infer adduct form, charge state, isotope cluster, and halogen signature from MS1 or HRMS peak data."
              className="min-w-0"
            >
                <form onSubmit={runAdductInfer} className="space-y-4">
                  <label className="block space-y-2">
                    <FieldLabelTip label="Target precursor m/z" tip="Optional lock-on m/z for clustering around a chromatographic precursor." />
                    <Input
                      value={adductTargetMz}
                      onChange={(e) => setAdductTargetMz(e.target.value)}
                      placeholder="Optional"
                      inputMode="decimal"
                    />
                  </label>
                  <div className="space-y-2">
                    <span className="text-sm font-medium">Ion mode</span>
                    <Select value={adductIonMode} onValueChange={setAdductIonMode}>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Ion mode" />
                      </SelectTrigger>
                      <SelectContent>
                        {ADDUCT_INFERENCE_ION_MODE_OPTIONS.map((o) => (
                          <SelectItem key={o.value} value={o.value}>
                            {o.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">m/z tolerance Da</span>
                      <Input value={adductMzTolDa} onChange={(e) => setAdductMzTolDa(e.target.value)} />
                    </label>
                    <label className="block space-y-2">
                      <FieldLabelTip label="ppm tolerance" tip="Mass accuracy window in parts per million vs. theoretical m/z." />
                      <Input value={adductPpmTol} onChange={(e) => setAdductPpmTol(e.target.value)} />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Isotope spacing tolerance Da</span>
                      <Input value={adductIsoTolDa} onChange={(e) => setAdductIsoTolDa(e.target.value)} />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Max charge state</span>
                      <Input value={adductMaxCharge} onChange={(e) => setAdductMaxCharge(e.target.value)} />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Min relative intensity %</span>
                      <Input value={adductMinRelInt} onChange={(e) => setAdductMinRelInt(e.target.value)} />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Max MS1 peaks</span>
                      <Input value={adductMaxPeaks} onChange={(e) => setAdductMaxPeaks(e.target.value)} />
                    </label>
                  </div>
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id="adduct-formula-search"
                      checked={adductFormulaSearch}
                      onCheckedChange={(v) => setAdductFormulaSearch(v === true)}
                    />
                    <Label htmlFor="adduct-formula-search" className="inline-flex items-center gap-1 text-sm font-normal">
                      Formula search
                      <InfoTooltip
                        label="Formula search"
                        content="Optional bounded formula enumeration from MS1 peaks alongside adduct scoring."
                        className="size-4"
                      />
                    </Label>
                  </div>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Max C</span>
                    <Input value={adductMaxC} onChange={(e) => setAdductMaxC(e.target.value)} />
                  </label>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Formula candidates per adduct</span>
                    <Input value={adductFormulaPerAdduct} onChange={(e) => setAdductFormulaPerAdduct(e.target.value)} />
                  </label>
                  <label className="block space-y-2">
                    <FieldLabelTip label="Processed MS1/HRMS peak list" tip="Centroid MS1 peaks for clustering adducts and isotopes." />
                    <Textarea
                      value={ms1PeakList}
                      onChange={(e) => setMs1PeakList(e.target.value)}
                      rows={6}
                      required
                      placeholder={"m/z,intensity\n47.04914,100\n48.05249,2.3\n69.03109,24"}
                    />
                  </label>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button type="submit" disabled={adductLoading} className="w-full sm:w-auto">
                        {adductLoading ? "Running…" : "Infer adducts + isotopes"}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs text-xs">
                      Infer adduct hypotheses and isotope clusters from the MS1 peak list.
                    </TooltipContent>
                  </Tooltip>
                  {adductResult != null && (
                    <div className="flex flex-wrap gap-2 pt-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={
                          !isRecord(adductResult) || !isRecord(adductResult.best_adduct_candidate)
                        }
                        onClick={applyBestAdductFromInference}
                      >
                        Use best adduct
                      </Button>
                      <Button type="button" variant="outline" size="sm" onClick={copyAdductInferenceToHrms}>
                        Copy to HRMS
                      </Button>
                      <Button type="button" variant="outline" size="sm" onClick={copyAdductInferenceToMsms}>
                        Copy to MS/MS
                      </Button>
                    </div>
                  )}
                </form>
            </ModuleCard>
            <div className="min-w-0 space-y-6">
              <TabResultSection
                error={adductError}
                loading={adductLoading}
                loadingTitle="Inferring adducts and isotope clusters"
                loadingHint="Inferring adducts and charge states…"
                emptyHint="Paste a peak list and run."
                result={adductResult}
                summaryTone="ms"
                unifiedEvidence={{
                  layer: "adduct_isotope",
                  sourceTab: "MS Evidence",
                  title: "Adduct + isotope inference",
                  endpoint: "/ms/adducts/infer/evidence",
                  sampleId: sampleId.trim() || undefined,
                }}
              />
              {!adductLoading && adductResult != null && <AdductInferenceDetailTables result={adductResult} />}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="msms" className="mt-4 space-y-6">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
            <ModuleCard
              accent="teal"
              eyebrow="MS · MS/MS"
              title={
                <span className="inline-flex items-center gap-2">
                  Processed MS/MS annotation
                  <InfoTooltip
                    label="About processed MS/MS annotation"
                    content="Annotate processed centroid MS/MS peaks using precursor m/z, adduct, candidate structures, fragment matches, and diagnostic neutral losses."
                  />
                </span>
              }
              description="Annotate centroid MS/MS fragments with candidate-specific matches, neutral losses, and diagnostic ion series."
              className="min-w-0"
            >
                <form onSubmit={runMsmsAnnotate} className="space-y-4">
                  <div className="space-y-2">
                    <span className="text-sm font-medium">Session MS/MS file (optional)</span>
                    <select
                      className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                      value={msmsSessionFileId}
                      onChange={(e) => setMsmsSessionFileId(e.target.value)}
                    >
                      <option value="">— none —</option>
                      {(ws?.sessionFiles ?? [])
                        .filter((f) => f.file_kind === "ms_peak_table" || f.file_kind === "other")
                        .map((f) => (
                          <option key={f.file_id} value={f.file_id}>
                            {f.filename} ({f.file_kind})
                          </option>
                        ))}
                    </select>
                    {msmsSessionFileId ? (
                      <p className="break-all font-mono text-xs text-muted-foreground">file_id: {msmsSessionFileId}</p>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        Traceability only — paste peak list below or use LC-MS tabs for file-based jobs.
                      </p>
                    )}
                  </div>
                  <label className="block space-y-2">
                    <FieldLabelTip label="Precursor m/z" tip="Isolation or selected precursor m/z for MS/MS interpretation." />
                    <Input value={msmsPrecursorMz} onChange={(e) => setMsmsPrecursorMz(e.target.value)} required />
                  </label>
                  <div className="space-y-2">
                    <FieldLabelTip label="Precursor adduct" tip="Ionizing adduct assumed for the MS/MS precursor ion." />
                    <Select value={msmsAdduct} onValueChange={setMsmsAdduct}>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Adduct" />
                      </SelectTrigger>
                      <SelectContent>
                        {HRMS_ADDUCT_OPTIONS.map((a) => (
                          <SelectItem key={a} value={a}>
                            {a}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">m/z tolerance Da</span>
                      <Input value={msmsMzTolDa} onChange={(e) => setMsmsMzTolDa(e.target.value)} />
                    </label>
                    <label className="block space-y-2">
                      <FieldLabelTip label="ppm tolerance" tip="Mass accuracy window in parts per million vs. theoretical m/z." />
                      <Input value={msmsPpmTol} onChange={(e) => setMsmsPpmTol(e.target.value)} />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Minimum relative intensity %</span>
                      <Input value={msmsMinRelInt} onChange={(e) => setMsmsMinRelInt(e.target.value)} />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Max peaks</span>
                      <Input value={msmsMaxPeaks} onChange={(e) => setMsmsMaxPeaks(e.target.value)} />
                    </label>
                  </div>
                  <label className="block space-y-2">
                    <FieldLabelTip label="Processed MS/MS peak list" tip="Centroid fragment ions as m/z and intensity rows." />
                    <Textarea
                      value={msmsPeakList}
                      onChange={(e) => setMsmsPeakList(e.target.value)}
                      rows={6}
                      required
                      placeholder={"m/z,intensity\n47.04914,10\n29.03858,100\n31.01839,25"}
                    />
                  </label>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Candidate structures</span>
                    <Textarea
                      value={msmsCandidatesText}
                      onChange={(e) => setMsmsCandidatesText(e.target.value)}
                      rows={5}
                      placeholder="Pipe-separated name | SMILES | role — synced from shared session when it changes."
                    />
                  </label>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button type="submit" disabled={msmsLoading} className="w-full sm:w-auto">
                        {msmsLoading ? "Running…" : "Annotate MS/MS"}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs text-xs">
                      Annotate MS/MS peaks and neutral losses vs. optional candidates.
                    </TooltipContent>
                  </Tooltip>
                </form>
            </ModuleCard>
            <div className="min-w-0 space-y-6">
              <TabResultSection
                error={msmsError}
                loading={msmsLoading}
                loadingTitle="Annotating processed MS/MS"
                loadingHint="Annotating MS/MS fragments…"
                emptyHint="Provide precursor m/z and daughter-ion peak list."
                result={msmsResult}
                summaryTone="ms"
                unifiedEvidence={{
                  layer: "msms_annotation",
                  sourceTab: "MS Evidence",
                  title: "MS/MS annotation",
                  endpoint: "/ms/msms/annotate/evidence",
                  sampleId: sampleId.trim() || undefined,
                }}
              />
              {!msmsLoading && msmsResult != null && <MsmsAnnotationDetailTables result={msmsResult} />}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="frag-tree" className="mt-4 space-y-6">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
            <ModuleCard
              accent="teal"
              eyebrow="MS · Fragmentation Tree"
              title={
                <span className="inline-flex items-center gap-2">
                  MS/MS fragmentation-tree reasoning
                  <InfoTooltip
                    label="About fragmentation-tree reasoning"
                    content="Build precursor-to-fragment and fragment-to-subfragment relationships using diagnostic neutral losses and candidate-specific plausibility."
                  />
                </span>
              }
              description="Build a precursor-to-fragment tree using diagnostic neutral losses and candidate-specific bond-cleavage plausibility."
              className="min-w-0"
            >
                <form onSubmit={runFragTree} className="space-y-4">
                  <label className="block space-y-2">
                    <FieldLabelTip label="Precursor m/z" tip="Isolation or selected precursor m/z for MS/MS interpretation." />
                    <Input value={fragPrecursorMz} onChange={(e) => setFragPrecursorMz(e.target.value)} required />
                  </label>
                  <div className="space-y-2">
                    <FieldLabelTip label="Adduct" tip="Ionizing adduct for theoretical neutral mass and fragment annotation." />
                    <Select value={fragAdduct} onValueChange={setFragAdduct}>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Adduct" />
                      </SelectTrigger>
                      <SelectContent>
                        {HRMS_ADDUCT_OPTIONS.map((a) => (
                          <SelectItem key={a} value={a}>
                            {a}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">m/z tolerance Da</span>
                      <Input value={fragMzTolDa} onChange={(e) => setFragMzTolDa(e.target.value)} />
                    </label>
                    <label className="block space-y-2">
                      <FieldLabelTip label="ppm tolerance" tip="Mass accuracy window in parts per million vs. theoretical m/z." />
                      <Input value={fragPpmTol} onChange={(e) => setFragPpmTol(e.target.value)} />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Minimum relative intensity %</span>
                      <Input value={fragMinRelInt} onChange={(e) => setFragMinRelInt(e.target.value)} />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Max peaks</span>
                      <Input value={fragMaxPeaks} onChange={(e) => setFragMaxPeaks(e.target.value)} />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Max tree depth</span>
                      <Input value={fragMaxDepth} onChange={(e) => setFragMaxDepth(e.target.value)} />
                    </label>
                  </div>
                  <label className="block space-y-2">
                    <FieldLabelTip label="Processed MS/MS peak list" tip="Centroid fragment ions as m/z and intensity rows." />
                    <Textarea
                      value={fragPeakList}
                      onChange={(e) => setFragPeakList(e.target.value)}
                      rows={6}
                      required
                      placeholder={"m/z,intensity\n47.04914,10\n29.03858,100\n31.01839,25"}
                    />
                  </label>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Candidate structures</span>
                    <Textarea
                      value={fragCandidatesText}
                      onChange={(e) => setFragCandidatesText(e.target.value)}
                      rows={5}
                      placeholder="Pipe-separated name | SMILES | role — synced from shared session when it changes."
                    />
                  </label>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button type="submit" disabled={fragLoading} className="w-full sm:w-auto">
                        {fragLoading ? "Running…" : "Build fragmentation tree"}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs text-xs">
                      Build fragmentation-tree evidence from the peak list and tolerances.
                    </TooltipContent>
                  </Tooltip>
                </form>
            </ModuleCard>
            <div className="min-w-0 space-y-6">
              <TabResultSection
                error={fragError}
                loading={fragLoading}
                loadingTitle="Building fragmentation-tree evidence"
                loadingHint="Building MS/MS fragmentation tree…"
                emptyHint="Provide precursor and MS/MS peak list; optionally include shared candidates."
                result={fragResult}
                summaryTone="ms"
                unifiedEvidence={{
                  layer: "fragmentation_tree",
                  sourceTab: "MS Evidence",
                  title: "Fragmentation tree",
                  endpoint: "/ms/msms/fragmentation-tree/evidence",
                  sampleId: sampleId.trim() || undefined,
                }}
              />
              {!fragLoading && fragResult != null && <FragmentationTreeDetailTables result={fragResult} />}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="lcms-import" className="mt-4 space-y-6">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
            <ModuleCard
              accent="teal"
              eyebrow="LC-MS · Import"
              title={
                <span className="inline-flex items-center gap-2">
                  Raw LC-MS/MS mzML + processed peak import bridge
                  <InfoTooltip
                    label="About LC-MS import bridge"
                    content="Import mzML/mzXML or processed LC-MS/MS peak tables, compute source hashes, summarize scans, and extract MS1/MS2 peak lists for downstream analysis."
                  />
                </span>
              }
              description="Import mzML/mzXML or a processed peak table. The file is parsed server-side; scan summaries and MS1/MS2 peak lists are extracted for downstream analysis."
              className="min-w-0"
            >
                <form onSubmit={runLcmsImport} className="space-y-4">
                  <div className="space-y-2">
                    <span className="text-sm font-medium">LC-MS/MS file</span>
                    <input
                      ref={lcmsImportFileRef}
                      type="file"
                      accept={LC_MS_UPLOAD_ACCEPT}
                      className={cn(
                        "file:text-foreground border-input flex h-9 w-full min-w-0 cursor-pointer rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium",
                        "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
                      )}
                    />
                  </div>
                  <div className="space-y-2">
                    <span className="text-sm font-medium">Session LC-MS file (optional)</span>
                    <select
                      className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                      value={lcmsImportSessionFileId}
                      onChange={(e) => setLcmsImportSessionFileId(e.target.value)}
                    >
                      <option value="">— none — use file input above</option>
                      {lcmsSessionLikeFiles.map((f) => (
                        <option key={f.file_id} value={f.file_id}>
                          {f.filename} ({f.file_kind})
                        </option>
                      ))}
                    </select>
                  </div>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Source label</span>
                    <Input
                      value={lcmsImportSourceLabel}
                      onChange={(e) => setLcmsImportSourceLabel(e.target.value)}
                      placeholder="Optional — sent as sample_id when set; otherwise session sample ID is used"
                    />
                  </label>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Preferred MS/MS precursor m/z (optional)</span>
                    <Input
                      value={lcmsImportPrecursorMz}
                      onChange={(e) => setLcmsImportPrecursorMz(e.target.value)}
                      placeholder="Selects MS/MS extraction when supported"
                      inputMode="decimal"
                    />
                  </label>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button type="submit" disabled={lcmsImportLoading} className="w-full sm:w-auto">
                        {lcmsImportLoading ? "Importing…" : "Import LC-MS/MS"}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs text-xs">
                      Upload LC-MS data for server-side parsing and peak extraction.
                    </TooltipContent>
                  </Tooltip>
                  <div className="space-y-2 border-t pt-4">
                    <p className="text-xs font-medium text-muted-foreground">Long-running analysis job</p>
                    <Button type="button" variant="outline" className="w-full sm:w-auto" onClick={() => void startLcmsImportJob()}>
                      Start as job (lcms_import)
                    </Button>
                    {lcmsImportJobErr ? (
                      <p className="text-sm" style={{ color: "var(--mt-red)" }}>{lcmsImportJobErr}</p>
                    ) : null}
                  </div>
                  {lcmsImportJob.jobId ? (
                    <AnalysisJobTimeline
                      job={lcmsImportJob}
                      variant="compact"
                      evidenceLayer="lcms_import"
                      sourceTab="MS Evidence"
                    />
                  ) : null}
                  {lcmsImportResult != null && (
                    <div className="flex flex-wrap gap-2 pt-2">
                      <Button type="button" variant="outline" size="sm" onClick={copyLcmsImportToMsWorkflows}>
                        Copy to MS workflows
                      </Button>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span className="inline-block">
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              disabled={!reportHashCopyEnabled}
                              onClick={copyImportHashForReport}
                            >
                              Copy hash to report
                            </Button>
                          </span>
                        </TooltipTrigger>
                        <TooltipContent>
                          {reportHashCopyEnabled
                            ? "Append this run’s SHA-256 to the connected report capture."
                            : "Connect a report workflow (lcmsReportReady + handler) to enable copying the hash into reporting."}
                        </TooltipContent>
                      </Tooltip>
                    </div>
                  )}
                </form>
            </ModuleCard>
            <div className="min-w-0 space-y-6">
              <TabResultSection
                error={lcmsImportError}
                loading={lcmsImportLoading}
                loadingTitle="Importing LC-MS/MS source"
                loadingHint="Importing LC-MS data through the ingest bridge…"
                emptyHint="Upload a raw or processed LC-MS file to extract peaks."
                result={lcmsImportResult}
                summaryTone="ms"
                unifiedEvidence={{
                  layer: "lcms_import",
                  sourceTab: "MS Evidence",
                  title: "LC-MS import bridge",
                  endpoint: "/ms/lcms/import/bridge/upload",
                  sampleId: sampleId.trim() || undefined,
                }}
              />
              {!lcmsImportLoading && lcmsImportResult != null && (
                <LcmsImportBridgeDetailTables result={lcmsImportResult} />
              )}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="lcms-features" className="mt-4 space-y-6">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
            <ModuleCard
              accent="teal"
              eyebrow="LC-MS · Features"
              title={
                <span className="inline-flex items-center gap-2">
                  LC-MS feature detection + EIC/XIC + peak purity
                  <InfoTooltip
                    label="About LC-MS feature detection"
                    content="Detect chromatographic features, extract EIC/XIC traces, estimate peak purity, and link nearby MS/MS scans."
                  />
                </span>
              }
              description="Detect chromatographic features, extract EIC/XIC traces, estimate co-elution purity, and link proximal MS/MS scans."
              className="min-w-0"
            >
                <form onSubmit={runLcmsFeatureDetect} className="space-y-4">
                  <div className="space-y-2">
                    <span className="text-sm font-medium">LC-MS/MS file</span>
                    <input
                      ref={lcmsFeatureFileRef}
                      type="file"
                      accept={LC_MS_UPLOAD_ACCEPT}
                      className={cn(
                        "file:text-foreground border-input flex h-9 w-full min-w-0 cursor-pointer rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium",
                        "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
                      )}
                    />
                  </div>
                  <div className="space-y-2">
                    <span className="text-sm font-medium">Session LC-MS file (optional)</span>
                    <select
                      className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                      value={lcmsFeatureSessionFileId}
                      onChange={(e) => setLcmsFeatureSessionFileId(e.target.value)}
                    >
                      <option value="">— none — use file input above</option>
                      {lcmsSessionLikeFiles.map((f) => (
                        <option key={f.file_id} value={f.file_id}>
                          {f.filename} ({f.file_kind})
                        </option>
                      ))}
                    </select>
                  </div>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Target m/z values</span>
                    <Textarea
                      value={lcmsFeatTargetMz}
                      onChange={(e) => setLcmsFeatTargetMz(e.target.value)}
                      rows={4}
                      placeholder="One m/z per line or comma-separated"
                    />
                  </label>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">m/z tolerance Da</span>
                      <Input value={lcmsFeatMzTol} onChange={(e) => setLcmsFeatMzTol(e.target.value)} />
                    </label>
                    <label className="block space-y-2">
                      <FieldLabelTip label="ppm tolerance" tip="Mass accuracy window in parts per million vs. theoretical m/z." />
                      <Input value={lcmsFeatPpmTol} onChange={(e) => setLcmsFeatPpmTol(e.target.value)} />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Minimum relative feature height</span>
                      <Input value={lcmsFeatMinRelH} onChange={(e) => setLcmsFeatMinRelH(e.target.value)} />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Minimum scans per feature</span>
                      <Input value={lcmsFeatMinScans} onChange={(e) => setLcmsFeatMinScans(e.target.value)} />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Smoothing window</span>
                      <Input value={lcmsFeatSmooth} onChange={(e) => setLcmsFeatSmooth(e.target.value)} />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Purity RT window</span>
                      <Input value={lcmsFeatPurityWin} onChange={(e) => setLcmsFeatPurityWin(e.target.value)} />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Top coeluting ions</span>
                      <Input value={lcmsFeatTopCo} onChange={(e) => setLcmsFeatTopCo(e.target.value)} />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Maximum features</span>
                      <Input value={lcmsFeatMaxFeat} onChange={(e) => setLcmsFeatMaxFeat(e.target.value)} />
                    </label>
                  </div>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button type="submit" disabled={lcmsFeatureLoading} className="w-full sm:w-auto">
                        {lcmsFeatureLoading ? "Running…" : "Detect features + XICs"}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs text-xs">
                      Run chromatographic feature detection and XIC extraction on the uploaded file.
                    </TooltipContent>
                  </Tooltip>
                  <div className="space-y-2 border-t pt-4">
                    <p className="text-xs font-medium text-muted-foreground">Long-running analysis job</p>
                    <Button
                      type="button"
                      variant="outline"
                      className="w-full sm:w-auto"
                      onClick={() => void startLcmsFeatureDetectionJob()}
                    >
                      Start as job (lcms_feature_detection)
                    </Button>
                    {lcmsFeatureJobErr ? (
                      <p className="text-sm" style={{ color: "var(--mt-red)" }}>{lcmsFeatureJobErr}</p>
                    ) : null}
                  </div>
                  {lcmsFeatureJob.jobId ? (
                    <AnalysisJobTimeline
                      job={lcmsFeatureJob}
                      variant="compact"
                      evidenceLayer="lcms_feature_detection"
                      sourceTab="MS Evidence"
                    />
                  ) : null}
                </form>
            </ModuleCard>
            <div className="min-w-0 space-y-6">
              <TabResultSection
                error={lcmsFeatureError}
                loading={lcmsFeatureLoading}
                loadingTitle="Detecting LC-MS features"
                loadingHint="Detecting LC-MS features…"
                emptyHint="Upload a file and target m/z list to detect features."
                result={lcmsFeatureResult}
                summaryTone="ms"
                unifiedEvidence={{
                  layer: "lcms_feature_detection",
                  sourceTab: "MS Evidence",
                  title: "LC-MS feature detection",
                  endpoint: "/ms/lcms/features/detect/upload",
                  sampleId: sampleId.trim() || undefined,
                }}
              />
              {!lcmsFeatureLoading && lcmsFeatureResult != null && (
                <LcmsFeatureDetectionDetailTables result={lcmsFeatureResult} />
              )}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="lcms-adv-group" className="mt-4 space-y-6">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
            <ModuleCard
              accent="teal"
              eyebrow="LC-MS · Grouping"
              title={
                <span className="inline-flex items-center gap-2">
                  Feature grouping + blank subtraction + RT alignment
                  <InfoTooltip
                    label="About LC-MS grouping"
                    content="Group sample, blank, QC, and reference LC-MS features; align retention time; subtract blank/background signals; and flag sample-enriched features."
                  />
                </span>
              }
              description="Group and align features across sample, blank, QC, and reference runs; subtract background signals; flag sample-enriched peaks."
              className="min-w-0"
            >
                <form onSubmit={runLcmsAdvGroup} className="space-y-4">
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Sample peak table</span>
                    <Textarea
                      value={lcmsGrpSampleText}
                      onChange={(e) => setLcmsGrpSampleText(e.target.value)}
                      rows={5}
                      placeholder="Feature or peak list text (required if no sample file)"
                    />
                  </label>
                  <div className="space-y-2">
                    <span className="text-sm font-medium">Sample file (optional)</span>
                    <input
                      ref={lcmsGrpSampleFileRef}
                      type="file"
                      accept=".csv,.tsv,.txt"
                      className={cn(
                        "file:text-foreground border-input flex h-9 w-full min-w-0 cursor-pointer rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium",
                        "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
                      )}
                    />
                  </div>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Blank peak table (optional)</span>
                    <Textarea
                      value={lcmsGrpBlankText}
                      onChange={(e) => setLcmsGrpBlankText(e.target.value)}
                      rows={4}
                      placeholder="Blank run feature list"
                    />
                  </label>
                  <div className="space-y-2">
                    <span className="text-sm font-medium">Blank file (optional)</span>
                    <input
                      ref={lcmsGrpBlankFileRef}
                      type="file"
                      accept=".csv,.tsv,.txt"
                      className={cn(
                        "file:text-foreground border-input flex h-9 w-full min-w-0 cursor-pointer rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium",
                        "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
                      )}
                    />
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block space-y-2">
                      <FieldLabelTip label="RT tolerance (min)" tip="Retention-time window for aligning and clustering ions across runs." />
                      <Input value={lcmsGrpRtTol} onChange={(e) => setLcmsGrpRtTol(e.target.value)} inputMode="decimal" />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">m/z tolerance (Da)</span>
                      <Input value={lcmsGrpMzTol} onChange={(e) => setLcmsGrpMzTol(e.target.value)} inputMode="decimal" />
                    </label>
                    <label className="block space-y-2">
                      <FieldLabelTip label="ppm tolerance" tip="Mass accuracy window in parts per million vs. theoretical m/z." />
                      <Input value={lcmsGrpPpmTol} onChange={(e) => setLcmsGrpPpmTol(e.target.value)} inputMode="decimal" />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Blank-like threshold</span>
                      <Input value={lcmsGrpBlankRatio} onChange={(e) => setLcmsGrpBlankRatio(e.target.value)} inputMode="decimal" />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Possible-background threshold</span>
                      <Input value={lcmsGrpPossBg} onChange={(e) => setLcmsGrpPossBg(e.target.value)} inputMode="decimal" />
                    </label>
                    <label className="block space-y-2">
                      <FieldLabelTip label="Blank subtraction factor" tip="Scalar applied to blank-feature areas before subtracting from sample areas." />
                      <Input value={lcmsGrpBlankFact} onChange={(e) => setLcmsGrpBlankFact(e.target.value)} inputMode="decimal" />
                    </label>
                  </div>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button type="submit" disabled={lcmsGrpLoading} className="w-full sm:w-auto">
                        {lcmsGrpLoading ? "Running…" : "Group features"}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs text-xs">
                      Group ions across runs with blank subtraction and RT alignment.
                    </TooltipContent>
                  </Tooltip>
                </form>
            </ModuleCard>
            <div className="min-w-0 space-y-6">
              <TabResultSection
                error={lcmsGrpError}
                loading={lcmsGrpLoading}
                loadingTitle="Grouping LC-MS features"
                loadingHint="Grouping LC-MS features and aligning retention times…"
                emptyHint="Paste sample (and optional blank) peak tables, then run."
                result={lcmsGrpResult}
                summaryTone="ms"
                unifiedEvidence={{
                  layer: "lcms_feature_grouping",
                  sourceTab: "MS Evidence",
                  title: "LC-MS feature grouping",
                  endpoint: "/ms/lcms/features/group/evidence",
                  sampleId: sampleId.trim() || undefined,
                }}
              />
              {!lcmsGrpLoading && lcmsGrpResult != null && <LcmsAdvGroupingDetailTables result={lcmsGrpResult} />}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="lcms-adv-consensus" className="mt-4 space-y-6">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
            <ModuleCard
              accent="teal"
              eyebrow="LC-MS · Consensus"
              title={
                <span className="inline-flex items-center gap-2">
                  LC-MS isotope/adduct consensus + feature-family confidence
                  <InfoTooltip
                    label="About feature-family consensus"
                    content="Score feature families using blank subtraction, peak purity, isotope envelope, adduct consistency, in-source loss, and MS/MS linkage."
                  />
                </span>
              }
              description="Score feature families using blank subtraction, isotope envelope fit, adduct consistency, and MS/MS linkage evidence."
              className="min-w-0"
            >
                <form onSubmit={runLcmsAdvConsensus} className="space-y-4">
                  {lcmsGrpResult != null && (
                    <Button type="button" variant="outline" size="sm" onClick={fillConsensusTableFromGrouping}>
                      Use grouping result table
                    </Button>
                  )}
                  <label className="block space-y-2">
                    <FieldLabelTip label="Grouped feature table" tip="Feature-group rows from detection or grouping for family-level consensus scoring." />
                    <Textarea
                      value={lcmsConFeatTable}
                      onChange={(e) => setLcmsConFeatTable(e.target.value)}
                      rows={6}
                      placeholder="Paste feature_table_text from grouping or detection exports"
                    />
                  </label>
                  <div className="space-y-2">
                    <span className="text-sm font-medium">Feature table file (optional)</span>
                    <input
                      ref={lcmsConFeatFileRef}
                      type="file"
                      accept=".csv,.tsv,.txt"
                      className={cn(
                        "file:text-foreground border-input flex h-9 w-full min-w-0 cursor-pointer rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium",
                        "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
                      )}
                    />
                  </div>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Formula (optional)</span>
                    <Input value={lcmsConFormula} onChange={(e) => setLcmsConFormula(e.target.value)} placeholder="e.g. C8H10N4O2" />
                  </label>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Promotion threshold</span>
                    <Input value={lcmsConPromote} onChange={(e) => setLcmsConPromote(e.target.value)} inputMode="decimal" />
                  </label>
                  <div className="space-y-2">
                    <span className="text-sm font-medium">Expected anchor adduct</span>
                    <Select value={lcmsConExpectedAdduct} onValueChange={setLcmsConExpectedAdduct}>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {HRMS_ADDUCT_OPTIONS.map((a) => (
                          <SelectItem key={a} value={a}>
                            {a}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex flex-col gap-3">
                    <div className="flex items-center gap-2">
                      <Checkbox id="lcms-con-iso" checked={lcmsConIso} onCheckedChange={(v) => setLcmsConIso(v === true)} />
                      <Label htmlFor="lcms-con-iso" className="text-sm font-normal">
                        Isotope scoring
                      </Label>
                    </div>
                    <div className="flex items-center gap-2">
                      <Checkbox
                        id="lcms-con-add"
                        checked={lcmsConAdductScore}
                        onCheckedChange={(v) => setLcmsConAdductScore(v === true)}
                      />
                      <Label htmlFor="lcms-con-add" className="text-sm font-normal">
                        Adduct scoring
                      </Label>
                    </div>
                    <div className="flex items-center gap-2">
                      <Checkbox id="lcms-con-loss" checked={lcmsConLoss} onCheckedChange={(v) => setLcmsConLoss(v === true)} />
                      <Label htmlFor="lcms-con-loss" className="text-sm font-normal">
                        In-source-loss scoring
                      </Label>
                    </div>
                  </div>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button type="submit" disabled={lcmsConLoading} className="w-full sm:w-auto">
                        {lcmsConLoading ? "Running…" : "Score feature-family consensus"}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs text-xs">
                      Score feature-family consistency (isotope, adduct, in-source loss toggles).
                    </TooltipContent>
                  </Tooltip>
                </form>
            </ModuleCard>
            <div className="min-w-0 space-y-6">
              <TabResultSection
                error={lcmsConError}
                loading={lcmsConLoading}
                loadingTitle="Scoring LC-MS feature-family consensus"
                loadingHint="Building feature-family consensus across runs…"
                emptyHint="Paste a grouped feature table (or load from grouping), then run."
                result={lcmsConResult}
                summaryTone="ms"
                unifiedEvidence={{
                  layer: "lcms_feature_family_consensus",
                  sourceTab: "MS Evidence",
                  title: "LC-MS feature-family consensus",
                  endpoint: "/ms/lcms/features/consensus/evidence",
                  sampleId: sampleId.trim() || undefined,
                }}
              />
              {!lcmsConLoading && lcmsConResult != null && <LcmsAdvConsensusDetailTables result={lcmsConResult} />}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="lcms-adv-derep" className="mt-4 space-y-6">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
            <ModuleCard
              accent="teal"
              eyebrow="LC-MS · Dereplication"
              title={
                <span className="inline-flex items-center gap-2">
                  LC-MS/MS library dereplication + candidate seed retrieval
                  <InfoTooltip
                    label="About LC-MS dereplication"
                    content="Rank supplied local or curated library candidates against precursor m/z, MS/MS similarity, optional RT/CCS, feature-family consensus, and library provenance."
                  />
                </span>
              }
              description="Rank candidates against the spectral library using precursor m/z, MS/MS dot-product similarity, optional RT/CCS, and feature-family provenance. Comment lines (prefixed #) are retained in the audit trail."
              className="min-w-0"
            >
                <form onSubmit={runLcmsAdvDereplication} className="space-y-4">
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Precursor m/z (optional, audit comment)</span>
                    <Input value={lcmsDerPrecursorMz} onChange={(e) => setLcmsDerPrecursorMz(e.target.value)} inputMode="decimal" />
                  </label>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">MS/MS peak list (optional, audit comments)</span>
                    <Textarea
                      value={lcmsDerMsmsPeaks}
                      onChange={(e) => setLcmsDerMsmsPeaks(e.target.value)}
                      rows={4}
                      placeholder="m/z,intensity rows — stored as # msms … comment lines"
                    />
                  </label>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Optional RT (min)</span>
                      <Input value={lcmsDerRt} onChange={(e) => setLcmsDerRt(e.target.value)} inputMode="decimal" />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Optional CCS</span>
                      <Input value={lcmsDerCcs} onChange={(e) => setLcmsDerCcs(e.target.value)} inputMode="decimal" />
                    </label>
                  </div>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Library candidates</span>
                    <Textarea
                      value={lcmsDerCandidatesText}
                      onChange={(e) => setLcmsDerCandidatesText(e.target.value)}
                      rows={5}
                      placeholder="Pipe-separated name | SMILES | role — synced from session candidates when updated"
                    />
                  </label>
                  <div className="space-y-2">
                    <span className="text-sm font-medium">Library file (optional)</span>
                    <input
                      ref={lcmsDerLibraryFileRef}
                      type="file"
                      accept=".csv,.tsv,.txt,.json"
                      className={cn(
                        "file:text-foreground border-input flex h-9 w-full min-w-0 cursor-pointer rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium",
                        "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
                      )}
                    />
                  </div>
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">LC-MS family table (optional)</span>
                    <Textarea
                      value={lcmsDerFamilyTable}
                      onChange={(e) => setLcmsDerFamilyTable(e.target.value)}
                      rows={4}
                      placeholder="family_id, anchor_mz, … from consensus export"
                    />
                  </label>
                  {lcmsConResult != null && (
                    <Button type="button" variant="outline" size="sm" onClick={fillDerepFamilyTableFromConsensus}>
                      Use consensus family table
                    </Button>
                  )}
                  <div className="space-y-2">
                    <FieldLabelTip label="Adduct" tip="Ionizing adduct for theoretical neutral mass and fragment annotation." />
                    <Select value={lcmsDerAdduct} onValueChange={setLcmsDerAdduct}>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {HRMS_ADDUCT_OPTIONS.map((a) => (
                          <SelectItem key={a} value={a}>
                            {a}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">m/z tolerance (Da)</span>
                      <Input value={lcmsDerMzTol} onChange={(e) => setLcmsDerMzTol(e.target.value)} inputMode="decimal" />
                    </label>
                    <label className="block space-y-2">
                      <FieldLabelTip label="ppm tolerance" tip="Mass accuracy window in parts per million vs. theoretical m/z." />
                      <Input value={lcmsDerPpmTol} onChange={(e) => setLcmsDerPpmTol(e.target.value)} inputMode="decimal" />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Min family consensus score</span>
                      <Input value={lcmsDerMinFam} onChange={(e) => setLcmsDerMinFam(e.target.value)} inputMode="decimal" />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Selected family ID (optional)</span>
                      <Input value={lcmsDerSelectedFamilyId} onChange={(e) => setLcmsDerSelectedFamilyId(e.target.value)} />
                    </label>
                  </div>
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id="lcms-der-req"
                      checked={lcmsDerReqPromoted}
                      onCheckedChange={(v) => setLcmsDerReqPromoted(v === true)}
                    />
                    <Label htmlFor="lcms-der-req" className="text-sm font-normal">
                      Use feature-family consensus (require_promoted_family)
                    </Label>
                  </div>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button type="submit" disabled={lcmsDerLoading} className="w-full sm:w-auto">
                        {lcmsDerLoading ? "Running…" : "Run dereplication"}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs text-xs">
                      Rank library candidates against LC-MS family evidence and tolerances.
                    </TooltipContent>
                  </Tooltip>
                </form>
            </ModuleCard>
            <div className="min-w-0 space-y-6">
              <TabResultSection
                error={lcmsDerError}
                loading={lcmsDerLoading}
                loadingTitle="Running LC-MS dereplication"
                loadingHint="Running library dereplication…"
                emptyHint="Provide candidates and/or family table evidence to rank library entries."
                result={lcmsDerResult}
                summaryTone="ms"
                unifiedEvidence={{
                  layer: "lcms_dereplication",
                  sourceTab: "MS Evidence",
                  title: "LC-MS library dereplication",
                  endpoint: "/ms/lcms/dereplication/evidence",
                  sampleId: sampleId.trim() || undefined,
                }}
              />
              {!lcmsDerLoading && lcmsDerResult != null && <LcmsAdvDereplicationDetailTables result={lcmsDerResult} />}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="lcms-adv-bridge" className="mt-4 space-y-6">
          <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
            <ModuleCard
              accent="teal"
              eyebrow="LC-MS · Bridge"
              title={
                <span className="inline-flex items-center gap-2">
                  LC-MS consensus → unified confidence bridge
                  <InfoTooltip
                    label="About LC-MS consensus bridge"
                    content="Connect promoted LC-MS feature families to candidate confidence when theoretical adduct m/z matches a non-conflicting feature-family anchor."
                  />
                </span>
              }
              description="Link promoted LC-MS feature families to candidate confidence scoring when theoretical adduct masses match a consensus anchor. Run LC-MS consensus above to populate automatically."
              className="min-w-0"
            >
                <form onSubmit={runLcmsAdvBridge} className="space-y-4">
                  <label className="block space-y-2">
                    <span className="text-sm font-medium">Candidate structures</span>
                    <Textarea
                      value={lcmsBridgeCandidatesText}
                      onChange={(e) => setLcmsBridgeCandidatesText(e.target.value)}
                      rows={6}
                      placeholder="name | SMILES | role"
                    />
                  </label>
                  <div className="space-y-2">
                    <FieldLabelTip label="Adduct" tip="Ionizing adduct for theoretical neutral mass and fragment annotation." />
                    <Select value={lcmsBridgeAdduct} onValueChange={setLcmsBridgeAdduct}>
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {HRMS_ADDUCT_OPTIONS.map((a) => (
                          <SelectItem key={a} value={a}>
                            {a}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block space-y-2">
                      <FieldLabelTip label="ppm tolerance" tip="Mass accuracy window in parts per million vs. theoretical m/z." />
                      <Input value={lcmsBridgePpm} onChange={(e) => setLcmsBridgePpm(e.target.value)} inputMode="decimal" />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">m/z tolerance (Da)</span>
                      <Input value={lcmsBridgeMzDa} onChange={(e) => setLcmsBridgeMzDa(e.target.value)} inputMode="decimal" />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Bridge threshold (min_family_consensus_score)</span>
                      <Input value={lcmsBridgeMinFam} onChange={(e) => setLcmsBridgeMinFam(e.target.value)} inputMode="decimal" />
                    </label>
                    <label className="block space-y-2">
                      <span className="text-sm font-medium">Selected family ID (optional)</span>
                      <Input value={lcmsBridgeSelectedFamilyId} onChange={(e) => setLcmsBridgeSelectedFamilyId(e.target.value)} />
                    </label>
                  </div>
                  <label className="block space-y-2">
                    <FieldLabelTip
                      label="Consensus family table"
                      tip="Exportable family rows (or full consensus result from the prior step) for mass alignment."
                    />
                    <Textarea
                      value={lcmsBridgeFamilyTable}
                      onChange={(e) => setLcmsBridgeFamilyTable(e.target.value)}
                      rows={5}
                      placeholder="Week 38 family_table_text CSV — optional if consensus was run in-panel"
                    />
                  </label>
                  {lcmsConResult != null && (
                    <Button type="button" variant="outline" size="sm" onClick={fillBridgeTableFromConsensus}>
                      Fill from last consensus run
                    </Button>
                  )}
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id="lcms-br-req"
                      checked={lcmsBridgeReqPromoted}
                      onCheckedChange={(v) => setLcmsBridgeReqPromoted(v === true)}
                    />
                    <Label htmlFor="lcms-br-req" className="text-sm font-normal">
                      Require promoted families (require_promoted_family)
                    </Label>
                  </div>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Button type="submit" disabled={lcmsBridgeLoading} className="w-full sm:w-auto">
                        {lcmsBridgeLoading ? "Running…" : "Bridge LC-MS evidence to candidate confidence"}
                      </Button>
                    </TooltipTrigger>
                    <TooltipContent side="top" className="max-w-xs text-xs">
                      Map candidate theoretical m/z to promoted LC-MS feature-family anchors.
                    </TooltipContent>
                  </Tooltip>
                </form>
            </ModuleCard>
            <div className="min-w-0 space-y-6">
              <TabResultSection
                error={lcmsBridgeError}
                loading={lcmsBridgeLoading}
                loadingTitle="Bridging LC-MS consensus to candidates"
                loadingHint="Bridging LC-MS consensus into unified confidence…"
                emptyHint="Enter candidates and supply consensus evidence (table or prior consensus run)."
                result={lcmsBridgeResult}
                summaryTone="ms"
                unifiedEvidence={{
                  layer: "lcms_confidence_bridge",
                  sourceTab: "MS Evidence",
                  title: "LC-MS consensus bridge",
                  endpoint: "/confidence/candidates/lcms-consensus-bridge",
                  sampleId: sampleId.trim() || undefined,
                }}
              />
              {!lcmsBridgeLoading && lcmsBridgeResult != null && <LcmsAdvBridgeDetailTables result={lcmsBridgeResult} />}
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
