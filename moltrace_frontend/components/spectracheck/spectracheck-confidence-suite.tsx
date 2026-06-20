"use client"

import { createContext, FormEvent, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { DeveloperOnly } from "@/components/developer-mode-provider"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { ConfidenceRing } from "@/components/science/confidence-ring"
import { Checkbox } from "@/components/ui/checkbox"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { MlModelProvenanceSummary } from "@/components/ml/ml-model-provenance-summary"
import { AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react"
import type { EvidenceItem, EvidenceLayerType } from "@/src/lib/spectracheck/evidence-types"
import {
  buildQcProvenanceForReport,
  effectiveEvidenceReadiness,
  summarizeUnifiedEvidenceQueueQc,
} from "@/src/lib/spectracheck/evidence-queue-qc"
import { useSpectraCheckEvidence } from "@/src/lib/spectracheck/useSpectraCheckEvidence"
import { SpectraCheckSavedSessionReviewAudit } from "@/components/spectracheck/spectracheck-review-audit"
import type { SessionFileRecord } from "@/src/lib/spectracheck/session-file-record"
import { fetchSessionAudit, fetchSessionReview } from "@/src/lib/spectracheck/spectracheck-backend-session"
import {
  buildReportProvenanceMetadata,
  fetchReportProvenanceData,
  filterJobsForSession,
  type ReportProvenanceMetadata,
} from "@/src/lib/spectracheck/report-provenance-bundle"
import { loadWorkflowProvenanceForReport } from "@/src/lib/spectracheck/report-workflow-provenance"
import { buildMethodProvenanceForReport } from "@/src/lib/spectracheck/report-method-provenance"
import { buildSelectedVisualEvidenceEntries } from "@/src/lib/spectracheck/report-visual-evidence"
import { ReportVisualEvidenceInlinePreviews } from "@/components/spectracheck/report-visual-evidence-inline-previews"
import { ReportLockControls } from "@/components/reports/report-lock-controls"
import { SecureShareDialog } from "@/src/components/collaboration/SecureShareDialog"
import { trackReportGenerated } from "@/src/lib/analytics/analytics-client"

type SuiteProps = {
  sampleId: string
  solvent: string
  candidatesText: string
  protonText: string
  carbonText: string
  /**
   * Compound-class hint from the shared session card. Forwarded to every
   * unified-confidence / report build call as ``compound_class`` so the
   * backend's class-conditioned scoring is consistent with the analyze runs.
   */
  compoundClass?: string
  /** Backend SpectraCheck session id when connected; enables saved-session review and audit. */
  backendSessionId?: string | null
}

function parseCandidateInputs(text: string): { name?: string; smiles: string; role?: string }[] {
  const out: { name?: string; smiles: string; role?: string }[] = []
  for (const line of text.split(/\r?\n/)) {
    const t = line.trim()
    if (!t) continue
    const parts = t.split("|").map((p) => p.trim())
    if (parts.length >= 2 && parts[1]) {
      out.push({ name: parts[0] || undefined, smiles: parts[1], role: parts[2] || undefined })
    } else if (parts.length === 1 && parts[0]) {
      out.push({ smiles: parts[0] })
    }
  }
  return out
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

type AiPredictionProvenance = NonNullable<ReportProvenanceMetadata["ai_prediction_provenance"]>

function firstString(records: Array<Record<string, unknown>>, keys: string[]): string | null {
  for (const r of records) {
    for (const k of keys) {
      const v = r[k]
      if (typeof v === "string" && v.trim()) return v.trim()
      if (typeof v === "number" && Number.isFinite(v)) return String(v)
    }
  }
  return null
}

function firstNumber(records: Array<Record<string, unknown>>, keys: string[]): number | null {
  for (const r of records) {
    for (const k of keys) {
      const v = r[k]
      if (typeof v === "number" && Number.isFinite(v)) return v
      if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Number(v)
    }
  }
  return null
}

function firstBoolean(records: Array<Record<string, unknown>>, keys: string[]): boolean | null {
  for (const r of records) {
    for (const k of keys) {
      const v = r[k]
      if (typeof v === "boolean") return v
      if (typeof v === "string") {
        const n = v.trim().toLowerCase()
        if (n === "true") return true
        if (n === "false") return false
      }
    }
  }
  return null
}

function pickHtmlFromWorkflowReportPayload(root: Record<string, unknown>): string | null {
  if (typeof root.html_report === "string") return root.html_report
  if (typeof root.html === "string") return root.html
  const aj = root.artifact_json
  if (isRecord(aj)) {
    if (typeof aj.html_report === "string") return aj.html_report
    if (typeof aj.html === "string") return aj.html
  }
  return null
}

function sanitizeReportHtml(html: string): string {
  return html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script\s*>/gi, "")
    .replace(/<script\b[^>]*\/\s*>/gi, "")
    .replace(/<script\b[^>]*>/gi, "")
}

function normalizeAuditEventsPayload(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (isRecord(data)) {
    if (Array.isArray(data.events)) return data.events
    if (Array.isArray(data.items)) return data.items
    if (Array.isArray(data.audit_events)) return data.audit_events
  }
  return []
}

function pickSessionSavedReviewStatus(data: unknown): string | null {
  if (!isRecord(data)) return null
  const v = data.review_status ?? data.reviewStatus
  return typeof v === "string" && v.trim() ? v.trim() : null
}

function auditEventSummaryLine(ev: unknown): string {
  if (!isRecord(ev)) return "—"
  for (const k of ["action", "event_type", "type", "message"]) {
    const v = ev[k]
    if (typeof v === "string" && v.trim()) return v.trim()
  }
  return "—"
}

function downloadText(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

/** Maps backend status labels to review UX copy */
const REPORT_STATUS_DISPLAY: Record<string, string> = {
  draft_requires_review: "Draft",
  review_ready: "Review required",
  approved_for_release: "Approved",
  blocked_by_contradictions: "Blocked by contradictions",
  insufficient_evidence: "Insufficient evidence",
}

const BUNDLE_UNAVAILABLE_MSG =
  "Unified evidence bundle endpoint not available yet. Ask Codex to add or update the unified evidence endpoint."

/** Layers treated as optional coverage targets for the synthesis summary (excludes unified_confidence and report). */
const SYNTHESIS_EXPECTED_LAYERS: EvidenceLayerType[] = [
  "nmr_text_candidates",
  "processed_1h",
  "processed_13c",
  "raw_fid_1h",
  "raw_fid_13c",
  "dept_apt",
  "nmr_2d",
  "predicted_nmr",
  "spectral_similarity",
  "hrms_exact_mass",
  "formula_search",
  "adduct_isotope",
  "msms_annotation",
  "fragmentation_tree",
  "lcms_import",
  "lcms_feature_detection",
  "lcms_feature_grouping",
  "lcms_feature_family_consensus",
  "lcms_dereplication",
  "lcms_confidence_bridge",
]

function collectEvidenceQueueHandoff(selected: EvidenceItem[]) {
  const hashes = new Set<string>()
  for (const i of selected) {
    const h = i.provenance?.sha256?.trim()
    if (h) hashes.add(h)
  }
  return {
    selected_evidence_items: selected.map((i) => ({
      id: i.id,
      layer: i.layer,
      title: i.title,
      provenance: i.provenance ?? null,
    })),
    raw_data_hashes_from_queue: [...hashes],
    selected_count: selected.length,
  }
}

function summarizeUnifiedResultForReport(data: unknown): string | null {
  if (!isRecord(data)) return null
  const best = data.best_candidate && isRecord(data.best_candidate) ? data.best_candidate : null
  if (best) {
    const label = typeof best.label === "string" ? best.label : null
    const name = typeof best.name === "string" ? best.name : null
    const smi = typeof best.smiles === "string" ? best.smiles : null
    const ikey = typeof best.inchikey === "string" ? best.inchikey : null
    const parts = [label, name, smi ?? ikey].filter(Boolean)
    if (parts.length > 0) return parts.join(" · ")
  }
  if (typeof data.confidence_score === "number") return `confidence_score ${data.confidence_score}`
  return null
}

function serializeEvidenceItemsForBundle(items: EvidenceItem[]) {
  return items.map((i) => ({
    id: i.id,
    layer: i.layer,
    title: i.title,
    source_tab: i.sourceTab,
    sample_id: i.sampleId ?? null,
    status: i.status,
    score: i.score ?? null,
    label: i.label ?? null,
    summary: i.summary ?? null,
    evidence_summary: i.evidenceSummary ?? null,
    contradictions: i.contradictions ?? null,
    warnings: i.warnings ?? null,
    notes: i.notes ?? null,
    endpoint: i.endpoint ?? null,
    request_preview: i.requestPreview ?? null,
    response: i.response,
    created_at: i.createdAt,
    selected_for_unified: i.selectedForUnified,
    provenance: i.provenance ?? null,
    qcStatus: i.qcStatus ?? null,
    readinessStatus: effectiveEvidenceReadiness(i),
    qualityAssessmentId: i.qualityAssessmentId ?? null,
    overrideStatus: i.overrideStatus ?? null,
    ...(i.overrideReason?.trim() ? { overrideReason: i.overrideReason.trim() } : {}),
  }))
}

function useUnifiedAdvancedState() {
  const [nmr2dText, setNmr2dText] = useState("")
  const [nmr2dExp, setNmr2dExp] = useState("")
  const [hrmsMz, setHrmsMz] = useState("")
  const [hrmsAdduct, setHrmsAdduct] = useState("[M+H]+")
  const [ionMode, setIonMode] = useState("")
  const [hrmsPpm, setHrmsPpm] = useState("5")
  const [m1, setM1] = useState("")
  const [m2, setM2] = useState("")
  const [ms1Peaks, setMs1Peaks] = useState("")
  const [useInfAdduct, setUseInfAdduct] = useState(true)
  const [addPpm, setAddPpm] = useState("10")
  const [isoTol, setIsoTol] = useState("0.02")
  const [ms1MinRi, setMs1MinRi] = useState("0.2")
  const [ms1MaxPk, setMs1MaxPk] = useState("200")
  const [msmsPeaks, setMsmsPeaks] = useState("")
  const [msmsPrec, setMsmsPrec] = useState("")
  const [msmsAdduct, setMsmsAdduct] = useState("")
  const [mzTol, setMzTol] = useState("0.02")
  const [msmsPpm, setMsmsPpm] = useState("20")
  const [msmsMinRi, setMsmsMinRi] = useState("1")
  const [msmsMaxPk, setMsmsMaxPk] = useState("75")
  const [maxTree, setMaxTree] = useState("3")
  const [lcmsTable, setLcmsTable] = useState("")
  const [lcmsAnchor, setLcmsAnchor] = useState("")
  const [lcmsMzTol, setLcmsMzTol] = useState("0.02")
  const [lcmsPpm, setLcmsPpm] = useState("10")
  const [lcmsMinFam, setLcmsMinFam] = useState("0.42")
  const [lcmsReqProm, setLcmsReqProm] = useState(true)
  const [lcmsFamId, setLcmsFamId] = useState("")

  return {
    nmr2dText,
    setNmr2dText,
    nmr2dExp,
    setNmr2dExp,
    hrmsMz,
    setHrmsMz,
    hrmsAdduct,
    setHrmsAdduct,
    ionMode,
    setIonMode,
    hrmsPpm,
    setHrmsPpm,
    m1,
    setM1,
    m2,
    setM2,
    ms1Peaks,
    setMs1Peaks,
    useInfAdduct,
    setUseInfAdduct,
    addPpm,
    setAddPpm,
    isoTol,
    setIsoTol,
    ms1MinRi,
    setMs1MinRi,
    ms1MaxPk,
    setMs1MaxPk,
    msmsPeaks,
    setMsmsPeaks,
    msmsPrec,
    setMsmsPrec,
    msmsAdduct,
    setMsmsAdduct,
    mzTol,
    setMzTol,
    msmsPpm,
    setMsmsPpm,
    msmsMinRi,
    setMsmsMinRi,
    msmsMaxPk,
    setMsmsMaxPk,
    maxTree,
    setMaxTree,
    lcmsTable,
    setLcmsTable,
    lcmsAnchor,
    setLcmsAnchor,
    lcmsMzTol,
    setLcmsMzTol,
    lcmsPpm,
    setLcmsPpm,
    lcmsMinFam,
    setLcmsMinFam,
    lcmsReqProm,
    setLcmsReqProm,
    lcmsFamId,
    setLcmsFamId,
  }
}

type UnifiedAdv = ReturnType<typeof useUnifiedAdvancedState>

const SpectraCheckConfidenceAdvContext = createContext<UnifiedAdv | null>(null)

/** Share unified/report advanced MS/LC form state across SpectraCheck tabs (single hook). */
export function SpectraCheckConfidenceAdvProvider({ children }: { children: ReactNode }) {
  const adv = useUnifiedAdvancedState()
  return <SpectraCheckConfidenceAdvContext.Provider value={adv}>{children}</SpectraCheckConfidenceAdvContext.Provider>
}

export type SpectraCheckConfidenceSuiteEmbedMode = "tabs" | "unified-only" | "report-only"

function SpectraCheckConfidenceSuiteSelfContained(
  props: SuiteProps & { embedMode?: SpectraCheckConfidenceSuiteEmbedMode }
) {
  const adv = useUnifiedAdvancedState()
  return <SpectraCheckConfidenceSuiteInner {...props} adv={adv} />
}

function SpectraCheckConfidenceSuiteInner(
  props: SuiteProps & { adv: UnifiedAdv; embedMode?: SpectraCheckConfidenceSuiteEmbedMode }
) {
  const { embedMode, adv, ...suiteProps } = props
  const mode = embedMode ?? "tabs"
  if (mode === "unified-only") {
    return <UnifiedConfidenceTab {...suiteProps} adv={adv} />
  }
  if (mode === "report-only") {
    return <ReportComposerTab {...suiteProps} adv={adv} />
  }
  return (
    <Tabs defaultValue="unified" className="w-full min-w-0">
      <div className="overflow-x-auto pb-2 [-webkit-overflow-scrolling:touch]">
        <TabsList className="inline-flex h-auto min-h-9 w-max flex-wrap justify-start gap-1">
          <TabsTrigger
            value="unified"
            className="font-mono data-[state=active]:[background-color:var(--mt-teal)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground"
          >
            Unified Confidence
          </TabsTrigger>
          <TabsTrigger
            value="report"
            className="font-mono data-[state=active]:[background-color:var(--mt-teal)] data-[state=active]:[color:#04080F] data-[state=active]:font-bold data-[state=active]:shadow-sm data-[state=inactive]:text-muted-foreground"
          >
            Report Composer
          </TabsTrigger>
        </TabsList>
      </div>
      <TabsContent value="unified" className="mt-4">
        <UnifiedConfidenceTab {...suiteProps} adv={adv} />
      </TabsContent>
      <TabsContent value="report" className="mt-4">
        <ReportComposerTab {...suiteProps} adv={adv} />
      </TabsContent>
    </Tabs>
  )
}

export function SpectraCheckConfidenceSuite(props: SuiteProps & { embedMode?: SpectraCheckConfidenceSuiteEmbedMode }) {
  const shared = useContext(SpectraCheckConfidenceAdvContext)
  if (shared) {
    return <SpectraCheckConfidenceSuiteInner {...props} adv={shared} />
  }
  return <SpectraCheckConfidenceSuiteSelfContained {...props} />
}

type TabProps = SuiteProps & { adv: UnifiedAdv }

function UnifiedQueueSynthesisSection({ items }: { items: EvidenceItem[] }) {
  const layerSet = new Set(items.map((i) => i.layer))
  const missingLayers = SYNTHESIS_EXPECTED_LAYERS.filter((l) => !layerSet.has(l))
  const contradictionLines = Array.from(new Set(items.flatMap((i) => i.contradictions ?? [])))
  const warningLines = Array.from(new Set(items.flatMap((i) => i.warnings ?? [])))

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <ModuleCard
        accent="teal"
        eyebrow="Unified · Selected"
        title="Selected evidence layer summary"
        description="Items checked for Unified Evidence in the Evidence Queue."
        className="min-w-0"
      >
        <div className="text-sm">
          {items.length === 0 ? (
            <p className="text-muted-foreground">No queue items selected yet.</p>
          ) : (
            <ul className="space-y-2">
              {items.map((it) => (
                <li key={it.id} className="rounded-md border px-2 py-1.5">
                  <span className="font-medium">{it.title}</span>
                  <span className="text-muted-foreground"> · </span>
                  <code className="text-xs">{it.layer}</code>
                  {it.score !== undefined && (
                    <span className="text-muted-foreground"> · score {typeof it.score === "number" ? it.score.toFixed(2) : it.score}</span>
                  )}
                  <Badge variant="outline" className="ml-2 align-middle text-[10px]">
                    {it.status}
                  </Badge>
                  <MlModelProvenanceSummary
                    className="mt-1.5 border-l-2 border-muted py-1 pl-2"
                    itemFields={{
                      modelArtifactId: it.modelArtifactId,
                      datasetVersionId: it.datasetVersionId,
                      evaluationRunId: it.evaluationRunId,
                      deploymentCandidateId: it.deploymentCandidateId,
                      modelCardId: it.modelCardId,
                      approvalStatus: it.approvalStatus,
                      methodId: it.methodId,
                      modelName: it.modelName,
                      modelVersion: it.modelVersion,
                    }}
                    sources={[it.response, it.requestPreview]}
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Unified · Missing"
        title="Missing evidence layers"
        description="Expected layers not yet represented among selected queue items."
        className="min-w-0"
      >
        <div className="text-sm">
          {missingLayers.length === 0 ? (
            <p className="text-muted-foreground">All synthesis targets covered (or see Developer JSON for nuance).</p>
          ) : (
            <ul className="list-inside list-disc space-y-1 text-muted-foreground">
              {missingLayers.map((l) => (
                <li key={l}>
                  <code className="text-xs">{l}</code>
                </li>
              ))}
            </ul>
          )}
        </div>
      </ModuleCard>

      <AlertCard
        variant="error"
        title="Contradiction summary"
        description="Aggregated from selected queue entries (pre-synthesis)."
      >
        {contradictionLines.length === 0 ? (
          <p className="text-sm text-muted-foreground">None listed on selected items.</p>
        ) : (
          <ul className="list-inside list-disc space-y-1 text-sm">
            {contradictionLines.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        )}
      </AlertCard>

      <AlertCard
        variant="warning"
        title="Warnings summary"
        description="Aggregated from selected queue entries (pre-synthesis)."
      >
        {warningLines.length === 0 ? (
          <p className="text-sm text-muted-foreground">None listed on selected items.</p>
        ) : (
          <ul className="list-inside list-disc space-y-1 text-sm">
            {warningLines.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        )}
      </AlertCard>
    </div>
  )
}

function UnifiedConfidenceTab({
  sampleId,
  solvent,
  candidatesText,
  protonText,
  carbonText,
  compoundClass,
  adv,
  backendSessionId = null,
}: TabProps) {
  const { evidenceItems, setLatestUnifiedConfidenceResult } = useSpectraCheckEvidence()
  const selectedQueueItems = useMemo(
    () => evidenceItems.filter((i) => i.selectedForUnified),
    [evidenceItems],
  )

  const unifiedQcSummary = useMemo(
    () => summarizeUnifiedEvidenceQueueQc(selectedQueueItems),
    [selectedQueueItems],
  )

  const [busy, setBusy] = useState(false)
  const [buildBusy, setBuildBusy] = useState(false)
  const [error, setError] = useState("")
  const [result, setResult] = useState<unknown>(null)

  async function run(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    setBusy(true)
    setError("")
    setResult(null)
    const fd = new FormData()
    fd.append("candidates_text", candidatesText)
    if (protonText.trim()) fd.append("observed_proton_text", protonText)
    if (carbonText.trim()) fd.append("observed_carbon13_text", carbonText)
    if (compoundClass && compoundClass !== "unspecified") {
      fd.append("compound_class", compoundClass)
    }
    appendUnifiedFormData(fd, sampleId, solvent, adv)
    try {
      const data = await apiFetch<unknown>("/confidence/candidates/unified/evidence", { method: "POST", body: fd })
      setResult(data)
    } catch (err) {
      setError(formatApiError(err, "Unified confidence failed"))
    } finally {
      setBusy(false)
    }
  }

  async function buildUnifiedEvidence() {
    if (selectedQueueItems.length === 0) {
      setError("Select evidence items in the Evidence Queue (checkboxes), then build unified evidence.")
      return
    }
    const qcGate = summarizeUnifiedEvidenceQueueQc(selectedQueueItems)
    if (qcGate.gate_blocks_build) {
      setError(
        `QC readiness blocks unified build until review or an allowed override clears blocked items: ${qcGate.blocked_items.map((b) => b.title).join("; ")}`,
      )
      return
    }
    setBuildBusy(true)
    setError("")
    setResult(null)
    const serialized = serializeEvidenceItemsForBundle(selectedQueueItems)
    const advancedJson = buildUnifiedConfidenceRequestJson(sampleId, solvent, candidatesText, protonText, carbonText, adv)
    const bundleBody = {
      sample_id: sampleId.trim() || null,
      solvent: solvent.trim() || null,
      candidates_text: candidatesText,
      candidates: parseCandidateInputs(candidatesText),
      observed_proton_text: protonText.trim() || null,
      observed_carbon13_text: carbonText.trim() || null,
      selected_evidence_items: serialized,
      raw_evidence_responses: selectedQueueItems.map((i) => ({
        id: i.id,
        layer: i.layer,
        response: i.response,
      })),
      metadata: {
        queue_selected_count: selectedQueueItems.length,
        layers_present: [...new Set(selectedQueueItems.map((i) => i.layer))],
        unified_advanced_request: advancedJson,
        qc_evidence_gate: qcGate,
      },
    }

    try {
      const data = await apiFetch<unknown>("/confidence/candidates/unified/evidence-bundle", {
        method: "POST",
        body: bundleBody,
      })
      setResult(data)
    } catch (e1) {
      const s1 = e1 instanceof ApiError ? e1.status : 0
      if (s1 === 404 || s1 === 405 || s1 === 501) {
        try {
          const fallbackBody = {
            ...advancedJson,
            selected_evidence_items: serialized,
            raw_evidence_responses: bundleBody.raw_evidence_responses,
            evidence_bundle_metadata: bundleBody.metadata,
          }
          const data = await apiFetch<unknown>("/confidence/candidates/unified/evidence", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(fallbackBody),
          })
          setResult(data)
        } catch {
          setError(BUNDLE_UNAVAILABLE_MSG)
        }
      } else {
        setError(formatApiError(e1, "Build unified evidence failed"))
      }
    } finally {
      setBuildBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <SpectraCheckSavedSessionReviewAudit backendSessionId={backendSessionId} />
      <ModuleCard
        accent="teal"
        eyebrow="Spectroscopy · Unified Confidence"
        title="Unified candidate confidence"
        description="Compute a unified confidence score by integrating NMR, MS, and LC-MS evidence layers across all session candidates."
      />

      <UnifiedQueueSynthesisSection items={selectedQueueItems} />

      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="secondary"
          disabled={buildBusy || selectedQueueItems.length === 0 || unifiedQcSummary.gate_blocks_build}
          className="w-full sm:w-auto"
          onClick={() => void buildUnifiedEvidence()}
        >
          {buildBusy ? "Building…" : "Build Unified Evidence"}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={buildBusy || busy || result == null}
          className="w-full sm:w-auto"
          onClick={() => setLatestUnifiedConfidenceResult(result)}
        >
          Use this result in Report
        </Button>
      </div>

      <DeveloperOnly>
        {selectedQueueItems.length > 0 && (
          <Collapsible className="rounded-lg border bg-muted/20">
            <CollapsibleTrigger className="flex w-full items-center px-4 py-3 text-left text-sm font-medium hover:bg-muted/40">
              Source evidence details
            </CollapsibleTrigger>
            <CollapsibleContent className="border-t px-4 pb-4">
              <p className="mb-2 text-xs text-muted-foreground">
                Raw JSON payloads from selected queue items — not the full MS Evidence workspace tables.
              </p>
              <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted/40 p-3 text-[10px] leading-relaxed">
                {JSON.stringify(
                  selectedQueueItems.map((i) => ({ id: i.id, layer: i.layer, title: i.title, response: i.response })),
                  null,
                  2,
                )}
              </pre>
            </CollapsibleContent>
          </Collapsible>
        )}
      </DeveloperOnly>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
        <ModuleCard
          accent="teal"
          eyebrow="Unified · Run"
          title="Run analysis"
          description="Candidates, 1H, and 13C default from Shared session inputs."
          className="min-w-0"
        >
            <form onSubmit={run} className="space-y-4">
              <AdvancedUnifiedFields state={adv} />
              <Button type="submit" disabled={busy || buildBusy} className="w-full sm:w-auto">
                {busy ? "Running…" : "Run unified confidence"}
              </Button>
            </form>
        </ModuleCard>

        <div className="min-w-0 space-y-4">
          {error && (
            <AlertCard variant="error" title="Request failed" description={error} />
          )}
          {(busy || buildBusy) && (
            <AlertCard
              variant="info"
              title={busy ? "Running unified confidence" : "Building unified evidence"}
              description={
                busy
                  ? "Synthesizing unified candidate confidence from evidence layers…"
                  : "Bundling evidence into a unified synthesis…"
              }
            />
          )}
          {!busy && !buildBusy && result != null ? <UnifiedConfidencePanels data={result} /> : null}
          {!busy && !buildBusy && !result && !error && (
            <Card>
              <CardContent className="border-dashed py-10 text-center text-sm text-muted-foreground">
                Build from the Evidence Queue or run unified confidence to see synthesis results.
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}

function ReportComposerTab({
  sampleId,
  solvent,
  candidatesText,
  protonText,
  carbonText,
  adv,
  backendSessionId = null,
}: TabProps) {
  const { evidenceItems, latestUnifiedConfidenceResult, latestReportResult, getSelectedEvidenceItems } =
    useSpectraCheckEvidence()
  const evidenceQueueHandoff = useMemo(
    () => collectEvidenceQueueHandoff(getSelectedEvidenceItems()),
    [evidenceItems, getSelectedEvidenceItems],
  )
  const selectedVisualEvidence = useMemo(
    () => buildSelectedVisualEvidenceEntries(getSelectedEvidenceItems()),
    [evidenceItems, getSelectedEvidenceItems],
  )
  const reportVisualPreviewItems = useMemo(() => {
    const byId = new Map(getSelectedEvidenceItems().map((i) => [i.id, i]))
    return selectedVisualEvidence
      .map((e) => byId.get(e.evidence_item_id))
      .filter((i): i is EvidenceItem => i != null)
  }, [selectedVisualEvidence, evidenceItems, getSelectedEvidenceItems])
  const unifiedHandoffSummary = useMemo(
    () => summarizeUnifiedResultForReport(latestUnifiedConfidenceResult),
    [latestUnifiedConfidenceResult],
  )

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [result, setResult] = useState<unknown>(null)
  const [htmlPreview, setHtmlPreview] = useState("")

  useEffect(() => {
    if (latestReportResult == null) return
    setResult(latestReportResult)
    if (!isRecord(latestReportResult)) return
    const html = pickHtmlFromWorkflowReportPayload(latestReportResult)
    if (html) setHtmlPreview(sanitizeReportHtml(html))
  }, [latestReportResult])

  const [reportTitle, setReportTitle] = useState("Regulatory-ready Structure Elucidation Report")
  const [projectName, setProjectName] = useState("")
  const [preparedBy, setPreparedBy] = useState("")
  const [reviewerName, setReviewerName] = useState("")
  const [reviewStatus, setReviewStatus] = useState("pending_review")
  const [reviewerComment, setReviewerComment] = useState("")
  const [intendedUse, setIntendedUse] = useState("research_decision_support")
  const [requireHumanApproval, setRequireHumanApproval] = useState(true)
  const [requestorNotes, setRequestorNotes] = useState("")
  const [rawDataSha256, setRawDataSha256] = useState("")
  const [sourceFilesText, setSourceFilesText] = useState("")
  const [processingHistoryText, setProcessingHistoryText] = useState("")

  const [provBusy, setProvBusy] = useState(false)
  const [provErr, setProvErr] = useState("")
  const [sessionFiles, setSessionFiles] = useState<SessionFileRecord[]>([])
  const [jobsForSession, setJobsForSession] = useState<Record<string, unknown>[]>([])
  const [artifactRecords, setArtifactRecords] = useState<Record<string, unknown>[]>([])
  const [sessionReviewSnap, setSessionReviewSnap] = useState<unknown>(null)
  const [auditEvents, setAuditEvents] = useState<unknown[]>([])
  const [sessionQcPayload, setSessionQcPayload] = useState<unknown | null>(null)
  const [workflowProvPayload, setWorkflowProvPayload] = useState<Record<string, unknown> | null>(null)
  const [workflowProvErr, setWorkflowProvErr] = useState("")
  const [workflowProvBusy, setWorkflowProvBusy] = useState(false)

  const processingHistoryLines = useMemo(
    () =>
      processingHistoryText
        .split(/\r?\n/)
        .map((l) => l.trim())
        .filter(Boolean),
    [processingHistoryText],
  )

  useEffect(() => {
    const sid = backendSessionId?.trim()
    if (!sid) {
      setSessionFiles([])
      setJobsForSession([])
      setArtifactRecords([])
      setSessionReviewSnap(null)
      setAuditEvents([])
      setProvErr("")
      setProvBusy(false)
      return
    }
    let cancelled = false
    setProvBusy(true)
    setProvErr("")
    void (async () => {
      try {
        const [prov, rev, aud, sqc] = await Promise.all([
          fetchReportProvenanceData(sid),
          fetchSessionReview(sid).catch(() => null),
          fetchSessionAudit(sid).catch(() => null),
          apiFetch<unknown>(`/quality-control/sessions/${encodeURIComponent(sid)}`, { method: "GET" }).catch(() => null),
        ])
        if (cancelled) return
        const fj = filterJobsForSession(prov.allJobs, sid)
        setSessionFiles(prov.files)
        setJobsForSession(fj)
        setArtifactRecords(prov.artifacts)
        setSessionReviewSnap(rev)
        setAuditEvents(normalizeAuditEventsPayload(aud))
        setSessionQcPayload(sqc ?? null)
      } catch (err) {
        if (!cancelled) setProvErr(formatApiError(err, "Provenance load failed"))
      } finally {
        if (!cancelled) setProvBusy(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [backendSessionId])

  useEffect(() => {
    let cancelled = false
    setWorkflowProvBusy(true)
    setWorkflowProvErr("")
    const selected = getSelectedEvidenceItems()
    void loadWorkflowProvenanceForReport(backendSessionId?.trim() ?? null, selected)
      .then((res) => {
        if (cancelled) return
        setWorkflowProvPayload(res.payload)
        if (res.loadErrors.length > 0) {
          setWorkflowProvErr(
            res.loadErrors.some((e) => e === "session_workflow_runs_unavailable")
              ? "Session workflow list unavailable — run-level workflow data may still load from queue-linked run ids."
              : "Some workflow run details could not be loaded.",
          )
        } else {
          setWorkflowProvErr("")
        }
      })
      .catch(() => {
        if (!cancelled) {
          setWorkflowProvPayload({
            workflow_runs: [],
            evidence_queue_items_selected: [],
            workflow_provenance_load_errors: ["workflow_provenance_loader_failed"],
          })
          setWorkflowProvErr("Workflow provenance could not be assembled.")
        }
      })
      .finally(() => {
        if (!cancelled) setWorkflowProvBusy(false)
      })
    return () => {
      cancelled = true
    }
  }, [backendSessionId, evidenceItems, getSelectedEvidenceItems])

  const sessionProvenanceBase = useMemo(() => {
    return buildReportProvenanceMetadata({
      backendSessionId,
      sampleId,
      sessionFiles,
      jobsForSession,
      artifactRecords,
      evidenceQueueHandoff:
        evidenceQueueHandoff.selected_count > 0 ? (evidenceQueueHandoff as unknown) : null,
      latestUnifiedConfidenceResult,
      reviewStatusCompose: reviewStatus,
      sessionReviewSnapshot: sessionReviewSnap,
      auditEvents,
      processingHistoryLines,
      selectedVisualEvidence,
    })
  }, [
    backendSessionId,
    sampleId,
    sessionFiles,
    jobsForSession,
    artifactRecords,
    evidenceQueueHandoff,
    latestUnifiedConfidenceResult,
    reviewStatus,
    sessionReviewSnap,
    auditEvents,
    processingHistoryLines,
    selectedVisualEvidence,
  ])

  const workflowProvenanceMerged = useMemo((): Record<string, unknown> | null => {
    if (!workflowProvPayload) return null
    return {
      ...(workflowProvPayload as Record<string, unknown>),
      unified_evidence_result_included: latestUnifiedConfidenceResult != null,
      review_decision: {
        compose_review_status: reviewStatus.trim() || null,
        saved_session_review_status: pickSessionSavedReviewStatus(sessionReviewSnap),
      },
      file_hashes: {
        session_source_sha256: sessionProvenanceBase.source_file_sha256_list,
        session_derived_artifact_sha256: sessionProvenanceBase.derived_artifact_sha256_list,
        queue_raw_data_sha256: evidenceQueueHandoff.raw_data_hashes_from_queue,
      },
      selected_evidence_qc_snapshot: getSelectedEvidenceItems().map((i) => ({
        evidence_item_id: i.id,
        qc_status: i.qcStatus ?? null,
        readiness_status: i.readinessStatus ?? null,
      })),
    }
  }, [
    workflowProvPayload,
    latestUnifiedConfidenceResult,
    reviewStatus,
    sessionReviewSnap,
    sessionProvenanceBase,
    evidenceQueueHandoff.raw_data_hashes_from_queue,
    getSelectedEvidenceItems,
    evidenceItems,
  ])

  const methodProvenancePayload = useMemo(
    () =>
      buildMethodProvenanceForReport({
        selectedEvidence: getSelectedEvidenceItems(),
        workflowProvenanceMerged,
        sessionQcRaw: sessionQcPayload,
        latestUnifiedResult: latestUnifiedConfidenceResult,
        intendedUse,
        reviewStatus,
      }),
    [
      getSelectedEvidenceItems,
      evidenceItems,
      workflowProvenanceMerged,
      sessionQcPayload,
      latestUnifiedConfidenceResult,
      intendedUse,
      reviewStatus,
    ],
  )

  const aiPredictionProvenance = useMemo((): AiPredictionProvenance | null => {
    const selectedEvidence = getSelectedEvidenceItems()
    const records: Array<Record<string, unknown>> = []
    if (isRecord(latestUnifiedConfidenceResult)) records.push(latestUnifiedConfidenceResult)
    for (const row of methodProvenancePayload.evidence_items) {
      if (isRecord(row)) records.push(row)
    }
    for (const item of selectedEvidence) {
      if (isRecord(item.response)) records.push(item.response)
      if (isRecord(item.requestPreview)) records.push(item.requestPreview)
    }
    if (records.length === 0) return null

    const prediction_run_id = firstString(records, ["prediction_run_id", "prediction_id", "run_id"])
    const model_artifact_id = firstNumber(records, ["model_artifact_id"])
    const deployment_candidate_id = firstNumber(records, ["deployment_candidate_id"])
    const service_key = firstString(records, ["service_key"])
    const confidence_score = firstNumber(records, ["confidence_score", "confidence"])
    const uncertainty = firstNumber(records, ["uncertainty", "uncertainty_score"])
    const ood_status = firstString(records, ["ood_status", "out_of_domain_status", "is_ood"])
    const human_review_required = firstBoolean(records, ["human_review_required", "review_required"])
    const feedback_status = firstString(records, ["feedback_status", "review_status"])
    const model_version = firstString(records, ["model_version"])
    const active_learning_flag = firstBoolean(records, ["active_learning_flag", "queued_for_active_learning"])

    return {
      prediction_run_id,
      model_artifact_id,
      deployment_candidate_id,
      service_key,
      confidence_score,
      uncertainty,
      ood_status,
      human_review_required,
      feedback_status,
      model_version,
      active_learning_flag,
    }
  }, [getSelectedEvidenceItems, evidenceItems, latestUnifiedConfidenceResult, methodProvenancePayload.evidence_items])

  const provenanceMetadata = useMemo((): ReportProvenanceMetadata => {
    const qc = buildQcProvenanceForReport({
      sessionQcRaw: sessionQcPayload,
      selectedEvidence: getSelectedEvidenceItems(),
      sourceFileSha256List: sessionProvenanceBase.source_file_sha256_list,
    })
    return {
      ...sessionProvenanceBase,
      qc_provenance_section: qc,
      ...(workflowProvenanceMerged != null ? { workflow_provenance: workflowProvenanceMerged } : {}),
      method_provenance: methodProvenancePayload,
      ai_prediction_provenance: aiPredictionProvenance,
    }
  }, [
    sessionProvenanceBase,
    sessionQcPayload,
    getSelectedEvidenceItems,
    workflowProvenanceMerged,
    methodProvenancePayload,
    aiPredictionProvenance,
  ])

  const reportPayloadJson = useMemo(
    () =>
      buildStructureElucidationReportRequestJson({
        reportTitle,
        projectName,
        preparedBy,
        reviewerName,
        reviewStatus,
        reviewerComment,
        intendedUse,
        requireHumanApproval,
        requestorNotes,
        rawDataSha256,
        sourceFilesText,
        processingHistoryText,
        sampleId,
        solvent,
        candidatesText,
        protonText,
        carbonText,
        adv,
        latestUnifiedConfidenceResult,
        evidenceQueueHandoff,
        provenanceMetadata,
      }),
    [
      reportTitle,
      projectName,
      preparedBy,
      reviewerName,
      reviewStatus,
      reviewerComment,
      intendedUse,
      requireHumanApproval,
      requestorNotes,
      rawDataSha256,
      sourceFilesText,
      processingHistoryText,
      sampleId,
      solvent,
      candidatesText,
      protonText,
      carbonText,
      adv,
      latestUnifiedConfidenceResult,
      evidenceQueueHandoff,
      provenanceMetadata,
    ],
  )

  async function compose(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    setBusy(true)
    setError("")
    setResult(null)
    setHtmlPreview("")
    const fd = new FormData()
    fd.append("candidates_text", candidatesText)
    if (protonText.trim()) fd.append("observed_proton_text", protonText)
    if (carbonText.trim()) fd.append("observed_carbon13_text", carbonText)
    appendUnifiedFormData(fd, sampleId, solvent, adv)

    fd.append("report_title", reportTitle.trim() || "Regulatory-ready Structure Elucidation Report")
    if (projectName.trim()) fd.append("project_name", projectName.trim())
    if (preparedBy.trim()) fd.append("prepared_by", preparedBy.trim())
    if (reviewerName.trim()) fd.append("reviewer_name", reviewerName.trim())
    if (reviewStatus.trim()) fd.append("review_status", reviewStatus.trim())
    if (reviewerComment.trim()) fd.append("reviewer_comment", reviewerComment.trim())
    fd.append("intended_use", intendedUse)
    fd.append("require_human_approval", requireHumanApproval ? "true" : "false")
    if (requestorNotes.trim()) fd.append("requestor_notes", requestorNotes.trim())
    if (rawDataSha256.trim()) fd.append("raw_data_sha256", rawDataSha256.trim())
    if (sourceFilesText.trim()) fd.append("source_files_text", sourceFilesText)
    if (processingHistoryText.trim()) fd.append("processing_history_text", processingHistoryText)
    if (sampleId.trim()) fd.append("sample_id", sampleId.trim())
    if (solvent.trim()) fd.append("solvent", solvent.trim())
    if (latestUnifiedConfidenceResult != null) {
      fd.append("unified_confidence_result_json", JSON.stringify(latestUnifiedConfidenceResult))
    }
    if (evidenceQueueHandoff.selected_count > 0) {
      fd.append("evidence_queue_handoff_json", JSON.stringify(evidenceQueueHandoff))
    }
    fd.append("provenance_metadata_json", JSON.stringify(provenanceMetadata))

    try {
      const data = await apiFetch<unknown>("/reports/structure-elucidation/compose/evidence", {
        method: "POST",
        body: fd,
      })
      setResult(data)
      {
        const evidence_layer_count = getSelectedEvidenceItems().length
        const report_status =
          isRecord(data) && typeof data.status === "string" ? data.status : "composed"
        trackReportGenerated({
          session_id: backendSessionId ?? undefined,
          metadata: {
            report_status,
            evidence_layer_count,
          },
        })
      }
      if (isRecord(data) && typeof data.html_report === "string") {
        setHtmlPreview(sanitizeReportHtml(data.html_report))
      }
    } catch (err) {
      let msg = formatApiError(err, "Report compose failed")
      if (err instanceof ApiError && (err.status === 404 || err.status === 405 || err.status === 503)) {
        msg +=
          " The report-composition service may be unavailable — check the deployment or API proxy."
      }
      if (err instanceof ApiError && (err.status === 400 || err.status === 422)) {
        msg +=
          " If the server rejected the payload, inspect the response body — nested workflow_provenance under provenance_metadata_json may need API support."
      }
      setError(msg)
    } finally {
      setBusy(false)
    }
  }

  async function fetchHtmlAlternate() {
    setBusy(true)
    setError("")
    try {
      const html = await apiFetch("/reports/structure-elucidation/compose/html", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(reportPayloadJson),
      })
      if (typeof html === "string") setHtmlPreview(sanitizeReportHtml(html))
    } catch (err) {
      let msg = formatApiError(err, "HTML compose failed")
      if (err instanceof ApiError && (err.status === 404 || err.status === 405 || err.status === 503)) {
        msg += " The alternate HTML compose route may be unavailable."
      }
      setError(msg)
    } finally {
      setBusy(false)
    }
  }

  function downloadReportJson() {
    if (!result || !isRecord(result)) return
    const jr = result.json_report
    const body = jr !== undefined ? JSON.stringify(jr, null, 2) : JSON.stringify(result, null, 2)
    downloadText(body, "structure-elucidation-report.json", "application/json")
  }

  function downloadReportHtml() {
    const html =
      htmlPreview ||
      (result && isRecord(result) && typeof result.html_report === "string" ? result.html_report : "")
    if (!html) return
    downloadText(html, "structure-elucidation-report.html", "text/html;charset=utf-8")
  }

  const statusLabel =
    result && isRecord(result) && typeof result.status === "string"
      ? REPORT_STATUS_DISPLAY[result.status] ?? result.status
      : null
  const releaseGate =
    result && isRecord(result) && typeof result.release_gate === "string" ? String(result.release_gate) : null
  const resultBackendStatus =
    result && isRecord(result) && typeof result.status === "string" ? String(result.status) : null
  const resultReviewStatusStr =
    result && isRecord(result) && typeof result.review_status === "string" ? String(result.review_status) : null
  const humanReviewApprovedFlag = Boolean(
    result && isRecord(result) && "human_review_approved" in result && result.human_review_approved === true,
  )
  const releaseGateSupportsApproval = releaseGate === "approved_for_release"
  const workflowStatusSupportsApproval = resultBackendStatus === "approved_for_release"
  const echoedReviewSupportsApproval =
    resultReviewStatusStr === "approved" || resultReviewStatusStr === "approved_for_release"
  const humanApprovalClaimSupported =
    humanReviewApprovedFlag &&
    (releaseGateSupportsApproval || workflowStatusSupportsApproval || echoedReviewSupportsApproval)

  const qcProv = provenanceMetadata.qc_provenance_section

  const composedReportNumericId = useMemo(() => {
    if (!result || !isRecord(result)) return null
    const id = result.report_id
    if (typeof id === "number" && Number.isFinite(id)) return Math.trunc(id)
    if (typeof id === "string" && id.trim()) {
      const n = Number(id.trim())
      return Number.isFinite(n) ? Math.trunc(n) : null
    }
    return null
  }, [result])

  const backendSessionNumericForLock = useMemo(() => {
    const s = backendSessionId?.trim()
    if (!s) return null
    const n = Number(s)
    return Number.isFinite(n) ? Math.trunc(n) : null
  }, [backendSessionId])

  return (
    <div className="space-y-6">
      <SpectraCheckSavedSessionReviewAudit backendSessionId={backendSessionId} />
      <ModuleCard
        accent="teal"
        eyebrow="Spectroscopy · Report Composer"
        title="Structure elucidation report composer"
        description="Compose a structure-elucidation report from your evidence — with an optional HTML preview."
      />

      <ModuleCard
        accent="teal"
        eyebrow="Report · Session context"
        title="Session context for compose"
        description="Uses shared sample ID, stored Unified Evidence result, and evidence queue selections (provenance and hashes when present)."
      >
        <div className="grid gap-4 text-sm md:grid-cols-2">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">Sample ID</p>
            <p className="break-all font-mono text-xs">{sampleId.trim() || "—"}</p>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">Unified confidence result (handoff)</p>
            {latestUnifiedConfidenceResult != null ? (
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="secondary">Stored for report</Badge>
                {unifiedHandoffSummary ? (
                  <span className="text-xs text-muted-foreground">{unifiedHandoffSummary}</span>
                ) : null}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                Not set — run Unified Evidence and choose &quot;Use this result in Report&quot;.
              </p>
            )}
          </div>
          <div className="space-y-1 md:col-span-2">
            <p className="text-xs font-medium text-muted-foreground">Selected evidence queue</p>
            {evidenceQueueHandoff.selected_count > 0 ? (
              <ul className="mt-1 max-h-40 list-inside list-disc space-y-1 overflow-y-auto text-xs">
                {getSelectedEvidenceItems().map((i) => (
                  <li key={i.id}>
                    <span className="font-mono">{i.layer}</span>
                    <span className="text-muted-foreground"> — </span>
                    {i.title}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">No queue items selected for unified synthesis.</p>
            )}
          </div>
          <div className="space-y-1 md:col-span-2">
            <p className="text-xs font-medium text-muted-foreground">Raw data hashes (queue provenance)</p>
            {evidenceQueueHandoff.raw_data_hashes_from_queue.length > 0 ? (
              <ul className="mt-1 space-y-1 font-mono text-[10px] leading-snug break-all">
                {evidenceQueueHandoff.raw_data_hashes_from_queue.map((h) => (
                  <li key={h}>{h}</li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">None recorded on selected items.</p>
            )}
          </div>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Report · Method Provenance"
        title="Scientific Method Provenance"
        description={
          <>
            Fields from selected Evidence Queue items, linked workflow runs, session QC, unified confidence, and composer
            choices — serialized under <code className="text-xs">method_provenance</code> inside{" "}
            <code className="text-xs">provenance_metadata_json</code>.
          </>
        }
      >
        <div className="space-y-3 text-sm">
          {methodProvenancePayload.warning_legacy_evidence_without_method_provenance ? (
            <Alert variant="default" className="border-amber-500/40 bg-amber-500/5">
              <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
              <AlertTitle className="text-sm">Legacy evidence</AlertTitle>
              <AlertDescription className="text-xs">
                Some evidence items were generated before method provenance tracking was enabled.
              </AlertDescription>
            </Alert>
          ) : null}
          {methodProvenancePayload.warning_legacy_evidence_without_ml_registry_provenance ? (
            <Alert variant="default" className="border-muted">
              <AlertTriangle className="h-4 w-4 text-muted-foreground" />
              <AlertTitle className="text-sm">ML registry provenance</AlertTitle>
              <AlertDescription className="text-xs text-muted-foreground">
                Some selected items have no model artifact / dataset / evaluation / deployment registry fields on the
                response — this is expected for older runs.
              </AlertDescription>
            </Alert>
          ) : null}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
            <span>
              QC session snapshot: {methodProvenancePayload.qc_session_snapshot_present ? "present" : "not loaded"}
            </span>
            <span>
              Unified confidence snapshot:{" "}
              {methodProvenancePayload.unified_confidence_snapshot_present ? "present" : "not stored"}
            </span>
            {methodProvenancePayload.unified_validation_status ? (
              <span>Unified validation label: {methodProvenancePayload.unified_validation_status}</span>
            ) : null}
          </div>
          <p className="text-[11px] text-muted-foreground">
            Composer context — intended_use:{" "}
            <span className="font-mono">{methodProvenancePayload.composer_context.intended_use ?? "—"}</span>
            {" · "}review_status:{" "}
            <span className="font-mono">{methodProvenancePayload.composer_context.review_status ?? "—"}</span>
          </p>
          {methodProvenancePayload.evidence_items.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No evidence items selected for unified synthesis — add selections in the Evidence Queue.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">Evidence layer</TableHead>
                    <TableHead className="text-xs">Method name</TableHead>
                    <TableHead className="text-xs">Method version</TableHead>
                    <TableHead className="text-xs">Model version</TableHead>
                    <TableHead className="text-xs">Scoring profile</TableHead>
                    <TableHead className="text-xs">Threshold profile</TableHead>
                    <TableHead className="text-xs">Workflow template version</TableHead>
                    <TableHead className="text-xs">Validation status</TableHead>
                    <TableHead className="text-xs">model_artifact_id</TableHead>
                    <TableHead className="text-xs">model card / model line</TableHead>
                    <TableHead className="text-xs">dataset_version_id</TableHead>
                    <TableHead className="text-xs">evaluation_run_id</TableHead>
                    <TableHead className="text-xs">deployment_candidate_id</TableHead>
                    <TableHead className="text-xs">approval_status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {methodProvenancePayload.evidence_items.map((row: Record<string, unknown>, idx: number) => {
                    const recorded = row.method_provenance_recorded === true
                    const mlOk = row.ml_registry_provenance_recorded === true
                    const layer = typeof row.evidence_layer === "string" ? row.evidence_layer : "—"
                    return (
                      <TableRow key={typeof row.evidence_item_id === "string" ? row.evidence_item_id : `prov-${idx}`}>
                        <TableCell className="max-w-[9rem] align-top font-mono text-[10px] break-all">{layer}</TableCell>
                        <TableCell className="max-w-[11rem] align-top text-xs">
                          {recorded ? (
                            typeof row.method_name === "string" && row.method_name.trim() ? (
                              row.method_name
                            ) : (
                              "—"
                            )
                          ) : (
                            <span className="italic text-muted-foreground">
                              Not recorded for this evidence item.
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="align-top text-xs">
                          {recorded ? (typeof row.method_version === "string" ? row.method_version : "—") : "—"}
                        </TableCell>
                        <TableCell className="max-w-[12rem] align-top text-xs">
                          {recorded ? (typeof row.model_version === "string" ? row.model_version : "—") : "—"}
                        </TableCell>
                        <TableCell className="max-w-[10rem] align-top text-xs">
                          {recorded ? (typeof row.scoring_profile === "string" ? row.scoring_profile : "—") : "—"}
                        </TableCell>
                        <TableCell className="max-w-[10rem] align-top text-xs">
                          {recorded ? (typeof row.threshold_profile === "string" ? row.threshold_profile : "—") : "—"}
                        </TableCell>
                        <TableCell className="max-w-[11rem] align-top text-xs">
                          {typeof row.workflow_template_version === "string" ? row.workflow_template_version : "—"}
                        </TableCell>
                        <TableCell className="max-w-[12rem] align-top text-[11px]">
                          {typeof row.validation_status === "string" ? row.validation_status : "—"}
                        </TableCell>
                        <TableCell className="align-top font-mono text-[10px] tabular-nums">
                          {!mlOk ? (
                            <span className="font-sans font-normal italic text-muted-foreground">Not recorded</span>
                          ) : typeof row.model_artifact_id === "number" ? (
                            row.model_artifact_id
                          ) : (
                            "—"
                          )}
                        </TableCell>
                        <TableCell className="max-w-[10rem] align-top text-[10px]">
                          {mlOk ? (
                            <>
                              <span className="font-mono">
                                {typeof row.model_card_id === "number" ? row.model_card_id : "—"}
                              </span>
                              {typeof row.registry_model_display === "string" && row.registry_model_display.trim() ? (
                                <span className="mt-0.5 block text-muted-foreground">{row.registry_model_display}</span>
                              ) : null}
                            </>
                          ) : (
                            <span className="italic text-muted-foreground">Not recorded</span>
                          )}
                        </TableCell>
                        <TableCell className="align-top font-mono text-[10px] tabular-nums">
                          {!mlOk ? (
                            <span className="font-sans font-normal italic text-muted-foreground">—</span>
                          ) : typeof row.dataset_version_id === "number" ? (
                            row.dataset_version_id
                          ) : (
                            "—"
                          )}
                        </TableCell>
                        <TableCell className="align-top font-mono text-[10px] tabular-nums">
                          {!mlOk ? (
                            <span className="font-sans font-normal italic text-muted-foreground">—</span>
                          ) : typeof row.evaluation_run_id === "number" ? (
                            row.evaluation_run_id
                          ) : (
                            "—"
                          )}
                        </TableCell>
                        <TableCell className="align-top font-mono text-[10px] tabular-nums">
                          {!mlOk ? (
                            <span className="font-sans font-normal italic text-muted-foreground">—</span>
                          ) : typeof row.deployment_candidate_id === "number" ? (
                            row.deployment_candidate_id
                          ) : (
                            "—"
                          )}
                        </TableCell>
                        <TableCell className="max-w-[8rem] align-top text-[10px]">
                          {!mlOk ? (
                            <span className="font-sans font-normal italic text-muted-foreground">—</span>
                          ) : typeof row.approval_status === "string" ? (
                            row.approval_status
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
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Report · Visual Evidence"
        title="Selected Visual Evidence"
        description={
          <>
            Queue rows selected for unified synthesis that carry visualizable payloads (kinds below). Compose sends{" "}
            <code className="text-xs">selected_visual_evidence</code> inside{" "}
            <code className="text-xs">provenance_metadata</code> — artifact references and plot-export placeholders only;
            raster or Plotly embeds are not included until export support is stable. Compact previews below are for this
            workspace only (orientation).
          </>
        }
      >
        <div className="space-y-3 text-sm">
          {selectedVisualEvidence.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              None — select evidence for unified synthesis and ensure items include spectrum, MS/MS, chromatogram,
              fragmentation, or related preview data.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">Evidence ID</TableHead>
                    <TableHead className="text-xs">Title</TableHead>
                    <TableHead className="text-xs">Artifact ID</TableHead>
                    <TableHead className="text-xs">Types / previews</TableHead>
                    <TableHead className="text-xs">Artifact SHA-256</TableHead>
                    <TableHead className="text-xs">Source file SHA-256</TableHead>
                    <TableHead className="text-xs">Job ID</TableHead>
                    <TableHead className="text-xs">QC</TableHead>
                    <TableHead className="text-xs">Visual review</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {selectedVisualEvidence.map((row) => (
                    <TableRow key={row.evidence_item_id}>
                      <TableCell className="max-w-[8rem] align-top font-mono text-[10px] break-all">
                        {row.evidence_item_id}
                      </TableCell>
                      <TableCell className="max-w-[10rem] align-top text-xs">{row.title}</TableCell>
                      <TableCell className="max-w-[8rem] align-top font-mono text-[10px] break-all">
                        {row.artifact_id ?? "—"}
                      </TableCell>
                      <TableCell className="max-w-[12rem] align-top text-[10px] text-muted-foreground">
                        <span className="block font-mono">{row.artifact_type ?? "—"}</span>
                        <span className="mt-1 block text-[10px]">{row.preview_kinds.join(", ") || "—"}</span>
                      </TableCell>
                      <TableCell className="max-w-[9rem] align-top font-mono text-[10px] break-all">
                        {row.sha256 ?? "—"}
                      </TableCell>
                      <TableCell className="max-w-[9rem] align-top font-mono text-[10px] break-all">
                        {row.source_file_sha256 ?? "—"}
                      </TableCell>
                      <TableCell className="max-w-[7rem] align-top font-mono text-[10px] break-all">
                        {row.job_id ?? "—"}
                      </TableCell>
                      <TableCell className="align-top text-xs">{row.qc_status ?? "—"}</TableCell>
                      <TableCell className="align-top text-xs">
                        {row.visual_reviewed ? "Recorded" : "Not recorded"}
                        {row.visual_review_comment ? (
                          <span className="mt-0.5 block text-[10px] text-muted-foreground">
                            {row.visual_review_comment}
                          </span>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
          {selectedVisualEvidence.length > 0 ? (
            <p className="text-[10px] text-muted-foreground">
              Plot placeholders sent with compose:{" "}
              {selectedVisualEvidence
                .flatMap((r) => r.plot_image_placeholders)
                .filter((v, i, a) => a.indexOf(v) === i)
                .slice(0, 24)
                .join(", ")}
              {selectedVisualEvidence.flatMap((r) => r.plot_image_placeholders).length > 24 ? " …" : ""}
            </p>
          ) : null}
          {reportVisualPreviewItems.length > 0 ? (
            <div className="space-y-4 border-t border-border/60 pt-4">
              <div>
                <p className="text-xs font-medium text-muted-foreground">Workspace previews</p>
                <p className="mt-0.5 text-[10px] text-muted-foreground">
                  Compact plots from queued payloads — not serialized into compose; interpretation requires expert review.
                </p>
              </div>
              <div className="space-y-4">
                {reportVisualPreviewItems.map((item) => (
                  <div key={item.id} className="rounded-md border border-border/60 bg-muted/20 p-3">
                    <p className="mb-2 truncate text-xs font-medium leading-snug" title={item.title}>
                      {item.title}
                    </p>
                    <ReportVisualEvidenceInlinePreviews item={item} plotHeight={150} />
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Report · AI Prediction"
        title="AI Prediction Provenance"
        description={
          <>
            Controlled AI prediction metadata included in <code className="text-xs">provenance_metadata_json</code> when available.
            Predictions remain decision support and require review.
          </>
        }
      >
        <div className="grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <span className="text-muted-foreground">prediction run ID</span>
            <p className="font-mono text-xs">{aiPredictionProvenance?.prediction_run_id ?? "—"}</p>
          </div>
          <div>
            <span className="text-muted-foreground">service key</span>
            <p className="font-mono text-xs">{aiPredictionProvenance?.service_key ?? "—"}</p>
          </div>
          <div>
            <span className="text-muted-foreground">model artifact ID</span>
            <p className="font-mono text-xs">{aiPredictionProvenance?.model_artifact_id ?? "—"}</p>
          </div>
          <div>
            <span className="text-muted-foreground">model version</span>
            <p className="text-xs">{aiPredictionProvenance?.model_version ?? "—"}</p>
          </div>
          <div>
            <span className="text-muted-foreground">deployment candidate ID</span>
            <p className="font-mono text-xs">{aiPredictionProvenance?.deployment_candidate_id ?? "—"}</p>
          </div>
          <div>
            <span className="text-muted-foreground">confidence</span>
            <p className="text-xs">{aiPredictionProvenance?.confidence_score ?? "—"}</p>
          </div>
          <div>
            <span className="text-muted-foreground">uncertainty</span>
            <p className="text-xs">{aiPredictionProvenance?.uncertainty ?? "—"}</p>
          </div>
          <div>
            <span className="text-muted-foreground">OOD status</span>
            <p className="text-xs">{aiPredictionProvenance?.ood_status ?? "—"}</p>
          </div>
          <div>
            <span className="text-muted-foreground">human feedback/review state</span>
            <p className="text-xs">{aiPredictionProvenance?.feedback_status ?? "—"}</p>
          </div>
          <div>
            <span className="text-muted-foreground">human review required</span>
            <p className="text-xs">
              {aiPredictionProvenance?.human_review_required == null
                ? "—"
                : aiPredictionProvenance.human_review_required
                  ? "requires review"
                  : "not flagged"}
            </p>
          </div>
          <div>
            <span className="text-muted-foreground">active-learning flag</span>
            <p className="text-xs">
              {aiPredictionProvenance?.active_learning_flag == null
                ? "—"
                : aiPredictionProvenance.active_learning_flag
                  ? "true"
                  : "false"}
            </p>
          </div>
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Report · Workflow Provenance"
        title="Workflow provenance"
        description={
          <>
            Included under <code className="text-xs">workflow_provenance</code> inside{" "}
            <code className="text-xs">provenance_metadata_json</code> on compose. Summaries require live workflow APIs —
            does not assert final approval or identification.
          </>
        }
      >
        <div className="space-y-4 text-sm">
          {workflowProvBusy ? <p className="text-xs text-muted-foreground">Loading workflow trace…</p> : null}
          {workflowProvErr ? <p className="text-xs text-warning">{workflowProvErr}</p> : null}
          {workflowProvenanceMerged ? (
            <>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">Unified evidence result (included)</p>
                  <p className="font-mono text-xs">
                    {workflowProvenanceMerged.unified_evidence_result_included === true ? "yes" : "no"}
                  </p>
                </div>
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">Review decision (compose / saved session)</p>
                  <p className="break-all font-mono text-xs">
                    {(isRecord(workflowProvenanceMerged.review_decision)
                      ? String(
                          (workflowProvenanceMerged.review_decision as Record<string, unknown>).compose_review_status ??
                            "",
                        )
                      : "—") || "—"}{" "}
                    /{" "}
                    {(isRecord(workflowProvenanceMerged.review_decision)
                      ? String(
                          (workflowProvenanceMerged.review_decision as Record<string, unknown>)
                            .saved_session_review_status ?? "",
                        )
                      : "—") || "—"}
                  </p>
                </div>
              </div>
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground">File hashes (session + queue)</p>
                <p className="text-xs text-muted-foreground">
                  {(() => {
                    const fh = workflowProvenanceMerged.file_hashes
                    if (!isRecord(fh)) return "Source 0 · Derived 0 · Queue raw 0"
                    const src = fh.session_source_sha256
                    const der = fh.session_derived_artifact_sha256
                    const q = fh.queue_raw_data_sha256
                    const srcN = Array.isArray(src) ? src.length : 0
                    const derN = Array.isArray(der) ? der.length : 0
                    const qN = Array.isArray(q) ? q.length : 0
                    return `Source ${srcN} · Derived ${derN} · Queue raw ${qN}`
                  })()}
                </p>
              </div>
              {Array.isArray(workflowProvenanceMerged["workflow_runs"]) &&
              (workflowProvenanceMerged["workflow_runs"] as unknown[]).length > 0 ? (
                <div className="min-w-0 overflow-x-auto">
                  <p className="text-xs font-medium text-muted-foreground">Workflow runs</p>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">Template</TableHead>
                        <TableHead className="text-xs">Run ID</TableHead>
                        <TableHead className="text-xs">Status</TableHead>
                        <TableHead className="text-xs">Steps</TableHead>
                        <TableHead className="text-xs">Artifacts</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(workflowProvenanceMerged["workflow_runs"] as Record<string, unknown>[]).map((wr, idx) => (
                        <TableRow key={`${String(wr.workflow_run_id ?? idx)}`}>
                          <TableCell className="max-w-[120px] truncate text-xs">
                            {typeof wr.template_name === "string" ? wr.template_name : "—"}
                          </TableCell>
                          <TableCell className="max-w-[120px] truncate font-mono text-[10px]">
                            {typeof wr.workflow_run_id === "string" ? wr.workflow_run_id : "—"}
                          </TableCell>
                          <TableCell className="text-xs">
                            {typeof wr.workflow_run_status === "string" ? wr.workflow_run_status : "—"}
                          </TableCell>
                          <TableCell className="max-w-[180px] text-[10px] text-muted-foreground">
                            {Array.isArray(wr.steps_completed_summary)
                              ? (wr.steps_completed_summary as string[]).slice(0, 4).join("; ")
                              : "—"}
                          </TableCell>
                          <TableCell className="text-xs">
                            {Array.isArray(wr.artifacts_included) ? wr.artifacts_included.length : 0}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">No workflow runs resolved yet (check queue run ids or session).</p>
              )}
              {Array.isArray(workflowProvenanceMerged["evidence_queue_items_selected"]) &&
              (workflowProvenanceMerged["evidence_queue_items_selected"] as unknown[]).length > 0 ? (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Evidence queue (selected for compose)</p>
                  <ul className="mt-1 max-h-36 list-inside list-disc space-y-1 overflow-y-auto text-xs">
                    {(workflowProvenanceMerged["evidence_queue_items_selected"] as Record<string, unknown>[]).map(
                      (row) => (
                        <li key={String(row.evidence_item_id ?? "")}>
                          <span className="font-mono">{String(row.layer ?? "")}</span>
                          <span className="text-muted-foreground"> — </span>
                          {String(row.title ?? "")}
                          {row.workflow_run_id ? (
                            <span className="text-muted-foreground"> · run {String(row.workflow_run_id)}</span>
                          ) : null}
                        </li>
                      ))}
                  </ul>
                </div>
              ) : null}
            </>
          ) : (
            <p className="text-xs text-muted-foreground">Workflow provenance loads after the evidence queue snapshot.</p>
          )}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Report · Evidence Quality"
        title="Evidence quality & session QC"
        description={
          <>
            QC and provenance context included under <code className="text-xs">qc_provenance_section</code> inside{" "}
            <code className="text-xs">provenance_metadata_json</code>. Language stays non-identifying unless human review
            signals support stronger statements.
          </>
        }
      >
        <div className="space-y-4 text-sm">
          {qcProv ? (
            <>
              <div className="rounded-md border bg-muted/20 p-3">
                <p className="text-xs font-medium text-muted-foreground">Summary</p>
                <p className="mt-1 text-sm font-medium">
                  {qcProv.narrative_key === "requires_human_review"
                    ? qcProv.report_language.requires_human_review
                    : qcProv.narrative_key === "usable_with_warnings"
                      ? qcProv.report_language.usable_with_warnings
                      : qcProv.report_language.evidence_quality_reviewed}
                </p>
                <p className="mt-2 text-xs text-muted-foreground">
                  Use &quot;Evidence quality reviewed&quot;, &quot;Usable with warnings&quot;, or &quot;Requires human
                  review&quot; per readiness — avoid implying structure identification beyond what review status supports.
                </p>
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">Session QC status (when loaded)</p>
                  <p className="break-all font-mono text-xs">
                    {qcProv.session_qc?.sessionReadiness ?? (backendSessionId?.trim() ? "—" : "No backend session")}
                  </p>
                </div>
                <div className="space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">Evidence QC snapshot (selected queue)</p>
                  <p className="text-xs text-muted-foreground">
                    {getSelectedEvidenceItems().length} item(s); human review suggested:{" "}
                    {qcProv.human_review_suggested ? "yes" : "no"}
                  </p>
                </div>
              </div>

              {qcProv.session_qc ? (
                <div className="grid gap-2 text-xs md:grid-cols-2 lg:grid-cols-4">
                  <div>
                    <span className="text-muted-foreground">Assessed</span>{" "}
                    <span className="font-mono">{qcProv.session_qc.totalAssessed ?? "—"}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Passed</span>{" "}
                    <span className="font-mono">{qcProv.session_qc.qcPassed ?? "—"}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Warnings</span>{" "}
                    <span className="font-mono">{qcProv.session_qc.warnings ?? "—"}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Failed</span>{" "}
                    <span className="font-mono">{qcProv.session_qc.failed ?? "—"}</span>
                  </div>
                </div>
              ) : null}

              {qcProv.failed_or_overridden_evidence.length > 0 ? (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Failed or overridden evidence (selected)</p>
                  <ul className="mt-1 list-inside list-disc space-y-1 text-xs">
                    {qcProv.failed_or_overridden_evidence.map((row) => (
                      <li key={`${row.title}-${row.detail}`}>
                        <span className="font-medium">{row.title}</span>
                        <span className="text-muted-foreground"> ({row.layer})</span>
                        <span className="text-muted-foreground"> — {row.detail}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">No failed or blocked evidence rows in the current selection.</p>
              )}

              {qcProv.reviewer_override_reasons.length > 0 ? (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Reviewer override reasons</p>
                  <ul className="mt-1 list-inside list-disc space-y-1 text-xs">
                    {qcProv.reviewer_override_reasons.map((r) => (
                      <li key={r} className="break-words">
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {qcProv.recommended_actions.length > 0 ? (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Recommended actions (session QC)</p>
                  <ol className="mt-1 list-inside list-decimal space-y-1 text-xs">
                    {qcProv.recommended_actions.map((a, i) => (
                      <li key={`${a}-${i}`}>{a}</li>
                    ))}
                  </ol>
                </div>
              ) : null}

              <div>
                <p className="text-xs font-medium text-muted-foreground">Source file hashes (provenance)</p>
                {qcProv.source_file_sha256_list.length > 0 ? (
                  <ul className="mt-1 max-h-32 space-y-1 overflow-y-auto font-mono text-[10px] leading-snug break-all">
                    {qcProv.source_file_sha256_list.map((h) => (
                      <li key={h}>{h}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-muted-foreground">None listed on session files.</p>
                )}
              </div>
            </>
          ) : (
            <p className="text-xs text-muted-foreground">QC provenance block unavailable.</p>
          )}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Report · Session Provenance"
        title="Provenance"
        description={
          <>
            Session files, jobs, and artifacts for this SpectraCheck session. Included in{" "}
            <code className="text-xs">provenance_metadata_json</code> on compose.
          </>
        }
      >
        <div className="space-y-4 text-sm">
          {!backendSessionId?.trim() ? (
            <p className="text-xs text-muted-foreground">
              Connect a backend session to load file, job, and artifact provenance.
            </p>
          ) : null}
          {backendSessionId?.trim() && provBusy ? (
            <p className="text-xs text-muted-foreground">Loading session provenance…</p>
          ) : null}
          {provErr ? <p className="text-xs text-warning">{provErr}</p> : null}

          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">Saved session review</p>
              <p className="break-all font-mono text-xs">{pickSessionSavedReviewStatus(sessionReviewSnap) ?? "—"}</p>
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">Compose review status</p>
              <p className="break-all font-mono text-xs">{reviewStatus.trim() || "—"}</p>
            </div>
          </div>

          {provenanceMetadata.processing_history_lines.length > 0 ? (
            <div>
              <p className="text-xs font-medium text-muted-foreground">Processing history (form)</p>
              <ol className="mt-1 list-inside list-decimal text-xs text-muted-foreground">
                {provenanceMetadata.processing_history_lines.map((line, i) => (
                  <li key={`${line}-${i}`}>{line}</li>
                ))}
              </ol>
            </div>
          ) : null}

          {provenanceMetadata.source_file_sha256_list.length > 0 ? (
            <div>
              <p className="text-xs font-medium text-muted-foreground">Raw data hashes (session files)</p>
              <ul className="mt-1 max-h-28 space-y-1 overflow-y-auto font-mono text-[10px] leading-snug break-all">
                {provenanceMetadata.source_file_sha256_list.map((h) => (
                  <li key={h}>{h}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {provenanceMetadata.derived_artifact_sha256_list.length > 0 ? (
            <div>
              <p className="text-xs font-medium text-muted-foreground">Derived artifact hashes</p>
              <ul className="mt-1 max-h-28 space-y-1 overflow-y-auto font-mono text-[10px] leading-snug break-all">
                {provenanceMetadata.derived_artifact_sha256_list.map((h) => (
                  <li key={h}>{h}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {provenanceMetadata.session_files.length > 0 ? (
            <div className="min-w-0 overflow-x-auto">
              <p className="text-xs font-medium text-muted-foreground">Session files</p>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">File</TableHead>
                    <TableHead className="text-xs">Kind</TableHead>
                    <TableHead className="text-xs">SHA-256</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {provenanceMetadata.session_files.map((f) => (
                    <TableRow key={f.file_id}>
                      <TableCell className="max-w-[140px] truncate text-xs font-mono" title={f.filename}>
                        {f.filename}
                      </TableCell>
                      <TableCell className="text-xs">{f.file_kind}</TableCell>
                      <TableCell className="max-w-[180px] truncate font-mono text-[10px]" title={f.sha256 ?? ""}>
                        {f.sha256 ?? "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : null}

          {provenanceMetadata.job_timeline_summary.length > 0 ? (
            <div>
              <p className="text-xs font-medium text-muted-foreground">Job timeline summary</p>
              <ul className="mt-1 max-h-36 space-y-1 overflow-y-auto text-xs text-muted-foreground">
                {provenanceMetadata.job_timeline_summary.map((line, i) => (
                  <li key={`job-tl-${i}`}>{line}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {provenanceMetadata.artifacts.length > 0 ? (
            <div className="min-w-0 overflow-x-auto">
              <p className="text-xs font-medium text-muted-foreground">Artifacts</p>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">ID</TableHead>
                    <TableHead className="text-xs">Type</TableHead>
                    <TableHead className="text-xs">Title</TableHead>
                    <TableHead className="text-xs">SHA-256</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {provenanceMetadata.artifacts.map((a) => (
                    <TableRow key={a.artifact_id}>
                      <TableCell className="max-w-[100px] truncate font-mono text-[10px]">{a.artifact_id}</TableCell>
                      <TableCell className="text-xs">{a.artifact_type}</TableCell>
                      <TableCell className="max-w-[120px] truncate text-xs" title={a.title}>
                        {a.title}
                      </TableCell>
                      <TableCell className="max-w-[140px] truncate font-mono text-[10px]">{a.sha256 ?? "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : null}

          {auditEvents.length > 0 ? (
            <div>
              <p className="text-xs font-medium text-muted-foreground">Recent audit events ({auditEvents.length})</p>
              <ul className="mt-1 list-inside list-disc space-y-1 text-xs text-muted-foreground">
                {auditEvents.slice(0, 5).map((ev, i) => (
                  <li key={i}>{auditEventSummaryLine(ev)}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </ModuleCard>

      <DeveloperOnly>
        <details className="rounded-lg border bg-card p-4">
          <summary className="cursor-pointer text-sm font-medium">Compose request (developer JSON)</summary>
          <pre className="mt-4 max-h-[360px] overflow-x-auto overflow-y-auto whitespace-pre-wrap rounded-md bg-muted/40 p-4 text-xs leading-5">
            {JSON.stringify(reportPayloadJson, null, 2)}
          </pre>
        </details>
      </DeveloperOnly>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
        <ModuleCard
          accent="teal"
          eyebrow="Report · Compose"
          title="Compose settings"
          description="Metadata, provenance, and evidence layers (advanced)."
          className="min-w-0"
        >
            <form onSubmit={compose} className="space-y-4">
              <label className="block space-y-2">
                <span className="text-sm font-medium">Report title</span>
                <Input value={reportTitle} onChange={(e) => setReportTitle(e.target.value)} />
              </label>
              <label className="block space-y-2">
                <span className="text-sm font-medium">Project name (optional)</span>
                <Input value={projectName} onChange={(e) => setProjectName(e.target.value)} />
              </label>
              <label className="block space-y-2">
                <span className="text-sm font-medium">Prepared by</span>
                <Input value={preparedBy} onChange={(e) => setPreparedBy(e.target.value)} />
              </label>
              <label className="block space-y-2">
                <span className="text-sm font-medium">Reviewer</span>
                <Input value={reviewerName} onChange={(e) => setReviewerName(e.target.value)} />
              </label>
              <label className="block space-y-2">
                <span className="text-sm font-medium">Review status</span>
                <select
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                  value={reviewStatus}
                  onChange={(e) => setReviewStatus(e.target.value)}
                >
                  <option value="">(unset)</option>
                  <option value="pending_review">pending_review</option>
                  <option value="approved">approved</option>
                  <option value="rejected">rejected</option>
                  <option value="needs_revision">needs_revision</option>
                </select>
              </label>
              <label className="block space-y-2">
                <span className="text-sm font-medium">Intended use</span>
                <select
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none"
                  value={intendedUse}
                  onChange={(e) => setIntendedUse(e.target.value)}
                >
                  <option value="research_decision_support">research_decision_support</option>
                  <option value="qc_batch_record">qc_batch_record</option>
                  <option value="regulatory_support">regulatory_support</option>
                  <option value="training_or_education">training_or_education</option>
                </select>
              </label>
              <label className="block space-y-2">
                <span className="text-sm font-medium">Reviewer comment</span>
                <Textarea value={reviewerComment} onChange={(e) => setReviewerComment(e.target.value)} rows={2} />
              </label>
              <label className="block space-y-2">
                <span className="text-sm font-medium">Requestor notes</span>
                <Textarea value={requestorNotes} onChange={(e) => setRequestorNotes(e.target.value)} rows={2} />
              </label>
              <label className="block space-y-2">
                <span className="text-sm font-medium">Raw data hash (SHA-256)</span>
                <Input
                  value={rawDataSha256}
                  onChange={(e) => setRawDataSha256(e.target.value)}
                  placeholder="optional hex digest"
                />
              </label>
              <label className="block space-y-2">
                <span className="text-sm font-medium">Source files (one path per line)</span>
                <Textarea value={sourceFilesText} onChange={(e) => setSourceFilesText(e.target.value)} rows={3} />
              </label>
              <label className="block space-y-2">
                <span className="text-sm font-medium">Processing history (one step per line)</span>
                <Textarea
                  value={processingHistoryText}
                  onChange={(e) => setProcessingHistoryText(e.target.value)}
                  rows={3}
                />
              </label>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="req-human"
                  checked={requireHumanApproval}
                  onCheckedChange={(v) => setRequireHumanApproval(v === true)}
                />
                <Label htmlFor="req-human" className="text-sm font-normal">
                  Require human approval gate
                </Label>
              </div>

              <AdvancedUnifiedFields state={adv} />

              <div className="flex flex-wrap gap-2">
                <Button type="submit" disabled={busy}>
                  {busy ? "Composing…" : "Compose report"}
                </Button>
                <Button type="button" variant="outline" disabled={busy} onClick={() => void fetchHtmlAlternate()}>
                  Fetch HTML (JSON body)
                </Button>
              </div>
            </form>
        </ModuleCard>

        <div className="min-w-0 space-y-4">
          <ModuleCard
            accent="teal"
            eyebrow="Report · Form Preview"
            title="Report form preview"
            description="Values that will be submitted with Compose report (same fields as the form)."
          >
            <div className="grid gap-2 text-sm sm:grid-cols-2">
              <div>
                <span className="text-muted-foreground">Title</span>
                <p className="font-medium">{reportTitle.trim() || "—"}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Sample ID</span>
                <p className="break-all font-mono text-xs">{sampleId.trim() || "—"}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Prepared by</span>
                <p>{preparedBy.trim() || "—"}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Reviewer</span>
                <p>{reviewerName.trim() || "—"}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Review status</span>
                <p>{reviewStatus.trim() || "—"}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Intended use</span>
                <p>{intendedUse}</p>
              </div>
              <div className="sm:col-span-2">
                <span className="text-muted-foreground">Source files (lines)</span>
                <p className="mt-1 text-xs">
                  {sourceFilesText.trim()
                    ? `${sourceFilesText.split(/\r?\n/).filter((l) => l.trim()).length} line(s)`
                    : "—"}
                </p>
              </div>
              <div className="sm:col-span-2">
                <span className="text-muted-foreground">Raw data hash (field)</span>
                <p className="mt-1 font-mono text-[10px] break-all">{rawDataSha256.trim() || "—"}</p>
              </div>
              <div className="sm:col-span-2">
                <span className="text-muted-foreground">Processing history (lines)</span>
                <p className="mt-1 text-xs">
                  {processingHistoryText.trim()
                    ? `${processingHistoryText.split(/\r?\n/).filter((l) => l.trim()).length} step(s)`
                    : "—"}
                </p>
              </div>
            </div>
          </ModuleCard>

          {error && (
            <AlertCard variant="error" title="Request failed" description={error} />
          )}

          {result != null && isRecord(result) ? (
            <>
              <ModuleCard
                accent="teal"
                eyebrow="Result · Metadata"
                title="Report metadata"
                description="Title, roles, and intent echoed from the composed report."
              >
                <div className="grid gap-2 text-sm sm:grid-cols-2">
                  <div>
                    <span className="text-muted-foreground">Title</span>
                    <p className="font-medium">{String(result.report_title ?? "—")}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Intended use</span>
                    <p className="font-medium">{String(result.intended_use ?? "—")}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Prepared by</span>
                    <p>{String(result.prepared_by ?? "—")}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Reviewer</span>
                    <p>{String(result.reviewer_name ?? "—")}</p>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Review status</span>
                    <p>{String(result.review_status ?? "—")}</p>
                  </div>
                </div>
              </ModuleCard>

              <ModuleCard
                accent="teal"
                eyebrow="Result · Status"
                title="Report status"
                description="Backend workflow labels for release."
              >
                <div className="flex flex-wrap gap-2">
                  {statusLabel && (
                    <Badge variant="secondary" className="text-sm">
                      {statusLabel}
                    </Badge>
                  )}
                  {releaseGate && (
                    <Badge variant="outline" className="font-mono text-xs">
                      release_gate: {releaseGate}
                    </Badge>
                  )}
                  {"human_review_required" in result && result.human_review_required === true && (
                    <Badge variant="destructive">Human review required</Badge>
                  )}
                  {humanReviewApprovedFlag && humanApprovalClaimSupported && (
                    <Badge className="bg-success text-success-foreground">Human review approved for release</Badge>
                  )}
                  {humanReviewApprovedFlag && !humanApprovalClaimSupported && (
                    <Badge variant="outline" className="font-mono text-xs">
                      human_review_approved (verify release gate / review_status)
                    </Badge>
                  )}
                </div>
              </ModuleCard>

              <ModuleCard
                accent="teal"
                eyebrow="Result · Provenance"
                title="Provenance snapshot"
              >
                <div className="space-y-2 text-sm">
                  <div>
                    <span className="text-muted-foreground">Report ID:</span>{" "}
                    <span className="font-mono">{String(result.report_id ?? "—")}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Raw data hash (report):</span>{" "}
                    <span className="font-mono break-all">
                      {isRecord(result.provenance) && typeof result.provenance.raw_data_sha256 === "string"
                        ? result.provenance.raw_data_sha256
                        : rawDataSha256 || "—"}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Report SHA-256:</span>{" "}
                    <span className="font-mono break-all text-xs">
                      {isRecord(result.provenance) && typeof result.provenance.report_sha256 === "string"
                        ? result.provenance.report_sha256
                        : "—"}
                    </span>
                  </div>
                </div>
              </ModuleCard>

              {composedReportNumericId != null && backendSessionId?.trim() ? (
                <ModuleCard
                  accent="teal"
                  eyebrow="Result · Lock & Release"
                  title="Report lock & release"
                  description={
                    <>
                      Lock status comes from the report itself. Release follows the session&apos;s
                      approval record (status <em>approved &amp; confirmed</em>) unless an admin override
                      is recorded in the release dialog.
                    </>
                  }
                >
                  <ReportLockControls
                    reportId={composedReportNumericId}
                    sessionIdStr={backendSessionId.trim()}
                    sessionNumericId={backendSessionNumericForLock}
                  />
                </ModuleCard>
              ) : null}

              {composedReportNumericId != null ? (
                <ModuleCard
                  accent="teal"
                  eyebrow="Result · Secure Share"
                  title="Secure share"
                  description="Generate a scoped share link — permissions and expiry follow your tenant's policy."
                >
                  <SecureShareDialog
                    scope="report"
                    lockScope
                    lockTargetId
                    defaultReportId={composedReportNumericId}
                    trigger={<Button type="button" variant="outline" size="sm">Secure share</Button>}
                  />
                </ModuleCard>
              ) : null}

              <ModuleCard
                accent="teal"
                eyebrow="Result · Source Files"
                title="Source files and processing history"
                description="Values submitted with this compose request (line-oriented lists)."
              >
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <p className="text-xs font-medium text-muted-foreground">Source files</p>
                    {sourceFilesText.trim() ? (
                      <ul className="mt-2 list-inside list-disc space-y-1 text-sm">
                        {sourceFilesText
                          .split(/\r?\n/)
                          .map((l) => l.trim())
                          .filter(Boolean)
                          .map((line) => (
                            <li key={line} className="break-all font-mono text-xs">
                              {line}
                            </li>
                          ))}
                      </ul>
                    ) : (
                      <p className="mt-2 text-sm text-muted-foreground">—</p>
                    )}
                  </div>
                  <div>
                    <p className="text-xs font-medium text-muted-foreground">Processing history</p>
                    {processingHistoryText.trim() ? (
                      <ol className="mt-2 list-inside list-decimal space-y-1 text-sm">
                        {processingHistoryText
                          .split(/\r?\n/)
                          .map((l) => l.trim())
                          .filter(Boolean)
                          .map((line, i) => (
                            <li key={`${line}-${i}`}>{line}</li>
                          ))}
                      </ol>
                    ) : (
                      <p className="mt-2 text-sm text-muted-foreground">—</p>
                    )}
                  </div>
                </div>
              </ModuleCard>

              {Array.isArray(result.sections) && result.sections.length > 0 && (
                <ModuleCard
                  accent="teal"
                  eyebrow="Result · Sections"
                  title="Report sections"
                >
                  <div className="space-y-4">
                    {result.sections.map((sec, i) => {
                      if (!isRecord(sec)) return null
                      const title = typeof sec.title === "string" ? sec.title : `Section ${i + 1}`
                      const items = Array.isArray(sec.items) ? sec.items.filter((x): x is string => typeof x === "string") : []
                      return (
                        <div key={`${title}-${i}`} className="rounded-md border px-3 py-2">
                          <p className="font-medium">{title}</p>
                          {items.length > 0 && (
                            <ul className="mt-2 list-inside list-disc text-sm text-muted-foreground">
                              {items.map((it) => (
                                <li key={it}>{it}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </ModuleCard>
              )}

              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" size="sm" onClick={downloadReportJson}>
                  Download JSON
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={downloadReportHtml}>
                  Download HTML
                </Button>
              </div>

              {(htmlPreview ||
                (typeof result.html_report === "string" && result.html_report.length > 0)) && (
                <Card
                  className="min-w-0 overflow-hidden rounded-xl py-0"
                  style={{ borderTop: "3px solid var(--mt-teal)" }}
                >
                  <CardHeader className="gap-1 pt-5 pb-2">
                    <span
                      className="font-mono text-[9px] font-bold uppercase tracking-[0.2em]"
                      style={{ color: "var(--mt-teal-ink)" }}
                    >
                      Result · HTML Preview
                    </span>
                    <CardTitle className="font-mono text-base font-bold tracking-tight">
                      HTML preview
                    </CardTitle>
                    <CardDescription>Sandboxed iframe — content from composed report.</CardDescription>
                  </CardHeader>
                  <CardContent className="p-0">
                    <iframe
                      title="Structure elucidation report preview"
                      className="h-[min(70vh,720px)] w-full border-0 bg-white"
                      sandbox="allow-same-origin"
                      srcDoc={
                        htmlPreview ||
                        (typeof result.html_report === "string" ? sanitizeReportHtml(result.html_report) : "")
                      }
                    />
                  </CardContent>
                </Card>
              )}

              <DeveloperJsonPanel data={result} />
            </>
          ) : null}

          {!busy && !result && !error && (
            <Card>
              <CardContent className="border-dashed py-10 text-center text-sm text-muted-foreground">
                Compose a report to see status, preview, and downloads.
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}

function appendUnifiedFormData(fd: FormData, sampleId: string, solvent: string, u: UnifiedAdv) {
  if (sampleId.trim()) fd.append("sample_id", sampleId.trim())
  if (solvent.trim()) fd.append("solvent", solvent.trim())
  if (u.nmr2dText.trim()) fd.append("observed_nmr2d_text", u.nmr2dText)
  if (u.nmr2dExp.trim()) fd.append("observed_nmr2d_experiment_type", u.nmr2dExp.trim())
  const hm = Number(u.hrmsMz.trim())
  if (Number.isFinite(hm) && hm > 0) fd.append("hrms_observed_mz", String(hm))
  if (u.hrmsAdduct.trim()) fd.append("hrms_adduct", u.hrmsAdduct.trim())
  if (u.ionMode.trim()) fd.append("ion_mode", u.ionMode.trim())
  fd.append("hrms_ppm_tolerance", u.hrmsPpm.trim() || "5")
  const om1 = u.m1.trim()
  const om2 = u.m2.trim()
  if (om1) fd.append("observed_m_plus_1_percent", om1)
  if (om2) fd.append("observed_m_plus_2_percent", om2)
  if (u.ms1Peaks.trim()) fd.append("ms1_peak_list_text", u.ms1Peaks)
  fd.append("use_inferred_adduct", u.useInfAdduct ? "true" : "false")
  fd.append("adduct_ppm_tolerance", u.addPpm.trim() || "10")
  fd.append("isotope_mz_tolerance_da", u.isoTol.trim() || "0.02")
  fd.append("ms1_min_relative_intensity", u.ms1MinRi.trim() || "0.2")
  fd.append("ms1_max_peaks_to_analyze", u.ms1MaxPk.trim() || "200")
  if (u.msmsPeaks.trim()) fd.append("msms_peak_list_text", u.msmsPeaks)
  const pm = Number(u.msmsPrec.trim())
  if (Number.isFinite(pm) && pm > 0) fd.append("msms_precursor_mz", String(pm))
  if (u.msmsAdduct.trim()) fd.append("msms_adduct", u.msmsAdduct.trim())
  fd.append("mz_tolerance_da", u.mzTol.trim() || "0.02")
  fd.append("msms_ppm_tolerance", u.msmsPpm.trim() || "20")
  fd.append("msms_min_relative_intensity", u.msmsMinRi.trim() || "1")
  fd.append("msms_max_peaks_to_analyze", u.msmsMaxPk.trim() || "75")
  fd.append("max_tree_depth", u.maxTree.trim() || "3")
  if (u.lcmsTable.trim()) fd.append("lcms_family_table_text", u.lcmsTable)
  if (u.lcmsAnchor.trim()) fd.append("lcms_anchor_adduct", u.lcmsAnchor.trim())
  fd.append("lcms_mz_tolerance_da", u.lcmsMzTol.trim() || "0.02")
  fd.append("lcms_ppm_tolerance", u.lcmsPpm.trim() || "10")
  fd.append("lcms_min_family_consensus_score", u.lcmsMinFam.trim() || "0.42")
  fd.append("lcms_require_promoted_family", u.lcmsReqProm ? "true" : "false")
  if (u.lcmsFamId.trim()) fd.append("lcms_selected_family_id", u.lcmsFamId.trim())
}

function AdvancedUnifiedFields({ state }: { state: UnifiedAdv }) {
  const u = state
  return (
    <Collapsible className="rounded-md border">
      <CollapsibleTrigger className="flex w-full px-4 py-3 text-left text-sm font-medium hover:bg-muted/50">
        Advanced MS / LC-MS inputs
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-3 border-t px-4 py-4">
        <label className="block space-y-1">
          <span className="text-xs text-muted-foreground">2D NMR text (optional)</span>
          <Textarea value={u.nmr2dText} onChange={(e) => u.setNmr2dText(e.target.value)} rows={2} />
        </label>
        <label className="block space-y-1">
          <span className="text-xs text-muted-foreground">2D experiment type</span>
          <Input value={u.nmr2dExp} onChange={(e) => u.setNmr2dExp(e.target.value)} />
        </label>
        <p className="text-xs font-medium text-muted-foreground">HRMS / MS1</p>
        <div className="grid gap-2 sm:grid-cols-2">
          <Input placeholder="HRMS observed m/z" value={u.hrmsMz} onChange={(e) => u.setHrmsMz(e.target.value)} />
          <Input placeholder="HRMS adduct" value={u.hrmsAdduct} onChange={(e) => u.setHrmsAdduct(e.target.value)} />
          <Input placeholder="Ion mode" value={u.ionMode} onChange={(e) => u.setIonMode(e.target.value)} />
          <Input placeholder="HRMS ppm tol." value={u.hrmsPpm} onChange={(e) => u.setHrmsPpm(e.target.value)} />
          <Input placeholder="M+1 %" value={u.m1} onChange={(e) => u.setM1(e.target.value)} />
          <Input placeholder="M+2 %" value={u.m2} onChange={(e) => u.setM2(e.target.value)} />
        </div>
        <label className="block space-y-1">
          <span className="text-xs text-muted-foreground">MS1 peak list text</span>
          <Textarea value={u.ms1Peaks} onChange={(e) => u.setMs1Peaks(e.target.value)} rows={2} />
        </label>
        <div className="flex items-center gap-2">
          <Checkbox
            id="u-inf"
            checked={u.useInfAdduct}
            onCheckedChange={(v) => u.setUseInfAdduct(v === true)}
          />
          <Label htmlFor="u-inf" className="text-sm font-normal">
            Use inferred adduct
          </Label>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <Input placeholder="Adduct ppm tol." value={u.addPpm} onChange={(e) => u.setAddPpm(e.target.value)} />
          <Input placeholder="Isotope m/z tol. Da" value={u.isoTol} onChange={(e) => u.setIsoTol(e.target.value)} />
          <Input placeholder="MS1 min rel. int." value={u.ms1MinRi} onChange={(e) => u.setMs1MinRi(e.target.value)} />
          <Input placeholder="MS1 max peaks" value={u.ms1MaxPk} onChange={(e) => u.setMs1MaxPk(e.target.value)} />
        </div>
        <p className="text-xs font-medium text-muted-foreground">MS/MS & tree</p>
        <Textarea
          placeholder="MS/MS peak list text"
          value={u.msmsPeaks}
          onChange={(e) => u.setMsmsPeaks(e.target.value)}
          rows={2}
        />
        <div className="grid gap-2 sm:grid-cols-2">
          <Input placeholder="Precursor m/z" value={u.msmsPrec} onChange={(e) => u.setMsmsPrec(e.target.value)} />
          <Input placeholder="MS/MS adduct" value={u.msmsAdduct} onChange={(e) => u.setMsmsAdduct(e.target.value)} />
          <Input placeholder="m/z tol. Da" value={u.mzTol} onChange={(e) => u.setMzTol(e.target.value)} />
          <Input placeholder="MS/MS ppm tol." value={u.msmsPpm} onChange={(e) => u.setMsmsPpm(e.target.value)} />
          <Input placeholder="MS/MS min rel. int." value={u.msmsMinRi} onChange={(e) => u.setMsmsMinRi(e.target.value)} />
          <Input placeholder="MS/MS max peaks" value={u.msmsMaxPk} onChange={(e) => u.setMsmsMaxPk(e.target.value)} />
          <Input placeholder="Max tree depth" value={u.maxTree} onChange={(e) => u.setMaxTree(e.target.value)} />
        </div>
        <p className="text-xs font-medium text-muted-foreground">LC-MS family bridge</p>
        <Textarea
          placeholder="LC-MS family table text"
          value={u.lcmsTable}
          onChange={(e) => u.setLcmsTable(e.target.value)}
          rows={2}
        />
        <div className="grid gap-2 sm:grid-cols-2">
          <Input placeholder="LCMS anchor adduct" value={u.lcmsAnchor} onChange={(e) => u.setLcmsAnchor(e.target.value)} />
          <Input placeholder="LCMS m/z tol." value={u.lcmsMzTol} onChange={(e) => u.setLcmsMzTol(e.target.value)} />
          <Input placeholder="LCMS ppm tol." value={u.lcmsPpm} onChange={(e) => u.setLcmsPpm(e.target.value)} />
          <Input placeholder="Min family consensus" value={u.lcmsMinFam} onChange={(e) => u.setLcmsMinFam(e.target.value)} />
          <Input placeholder="Selected family id" value={u.lcmsFamId} onChange={(e) => u.setLcmsFamId(e.target.value)} />
        </div>
        <div className="flex items-center gap-2">
          <Checkbox
            id="lcms-prom"
            checked={u.lcmsReqProm}
            onCheckedChange={(v) => u.setLcmsReqProm(v === true)}
          />
          <Label htmlFor="lcms-prom" className="text-sm font-normal">
            Require promoted LC-MS family
          </Label>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function UnifiedConfidencePanels({ data }: { data: unknown }) {
  if (!isRecord(data)) return null

  const ranked = Array.isArray(data.ranked_candidates) ? data.ranked_candidates.filter(isRecord) : []
  const layersUsed = Array.isArray(data.evidence_layers_used)
    ? data.evidence_layers_used.filter((x): x is string => typeof x === "string")
    : []
  const globalCx = Array.isArray(data.global_contradictions)
    ? data.global_contradictions.filter((x): x is string => typeof x === "string")
    : []
  const ambiguity = Array.isArray(data.ambiguity_alerts)
    ? data.ambiguity_alerts.filter((x): x is string => typeof x === "string")
    : []
  const warnings = Array.isArray(data.warnings) ? data.warnings.filter((x): x is string => typeof x === "string") : []
  const notesList = Array.isArray(data.notes) ? data.notes.filter((x): x is string => typeof x === "string") : []

  const best = data.best_candidate && isRecord(data.best_candidate) ? data.best_candidate : null
  const bestLayers = best && Array.isArray(best.layers) ? best.layers.filter(isRecord) : []

  const agreementCount = typeof data.agreement_count === "number" ? data.agreement_count : null
  const contradictionCount =
    typeof data.contradiction_count === "number" ? data.contradiction_count : null
  const humanReviewRequired = data.human_review_required === true
  const synthConfidence =
    typeof data.confidence_score === "number"
      ? data.confidence_score
      : best && typeof best.confidence_score === "number"
        ? best.confidence_score
        : null

  const missingSet = new Set<string>()
  for (const row of ranked) {
    const ml = row.missing_layers
    if (Array.isArray(ml)) {
      ml.forEach((x) => {
        if (typeof x === "string") missingSet.add(x)
      })
    }
  }

  const gateActive =
    humanReviewRequired ||
    globalCx.length > 0 ||
    warnings.length > 0 ||
    ambiguity.length > 0 ||
    notesList.length > 0 ||
    ranked.some((r) => typeof r.label === "string" && /conflict|insufficient|invalid/i.test(r.label))

  return (
    <div className="space-y-4">
      <AlertCard
        variant="success"
        title="Unified synthesis response"
        description={
          <span>
            Selected adduct: <code className="text-xs">{String(data.selected_adduct ?? "—")}</code>
          </span>
        }
      />

      <ModuleCard
        accent="teal"
        eyebrow="Unified · Metrics"
        title="Synthesis metrics"
        description="Summary fields returned by the unified confidence endpoint."
        className="min-w-0"
      >
        <div className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4 items-center">
          <div className="flex items-center gap-3">
            {synthConfidence !== null ? (
              <ConfidenceRing
                value={synthConfidence * 100}
                size={56}
                ariaLabel={`Confidence ${(synthConfidence * 100).toFixed(0)} percent`}
              />
            ) : (
              <div className="font-mono text-lg font-semibold">—</div>
            )}
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
              Confidence score
            </p>
          </div>
          <div>
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
              Agreement count
            </p>
            <p
              className="font-mono text-2xl font-bold tabular-nums"
              style={{ color: "var(--mt-green)" }}
            >
              {agreementCount !== null ? agreementCount : "—"}
            </p>
          </div>
          <div>
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
              Contradiction count
            </p>
            <p
              className="font-mono text-2xl font-bold tabular-nums"
              style={{ color: "var(--mt-red)" }}
            >
              {contradictionCount !== null ? contradictionCount : globalCx.length > 0 ? globalCx.length : "—"}
            </p>
          </div>
          <div>
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">
              Evidence layers used
            </p>
            <p
              className="font-mono text-2xl font-bold tabular-nums"
              style={{ color: "var(--mt-teal-ink)" }}
            >
              {layersUsed.length > 0 ? layersUsed.length : "—"}
            </p>
          </div>
        </div>
      </ModuleCard>

      {best && (
        <ModuleCard
          accent="teal"
          eyebrow="Unified · Best Candidate"
          title="Best candidate"
          className="min-w-0"
          badge={
            typeof best.confidence_score === "number" ? (
              <ConfidenceRing
                value={best.confidence_score * 100}
                size={48}
                ariaLabel={`Best candidate confidence ${(best.confidence_score * 100).toFixed(0)} percent`}
              />
            ) : null
          }
        >
          <div className="grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <span className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Name</span>
              <p className="font-medium">{String(best.name ?? "—")}</p>
            </div>
            <div>
              <span className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">SMILES</span>
              <p className="break-all font-mono text-xs">{String(best.smiles ?? "—")}</p>
            </div>
            {typeof best.confidence_score === "number" && (
              <div>
                <span className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Confidence score</span>
                <p className="font-mono">{best.confidence_score.toFixed(3)}</p>
              </div>
            )}
            {typeof best.confidence_band === "string" && best.confidence_band && (
              <div>
                <span className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground">Band</span>
                <p>{best.confidence_band}</p>
              </div>
            )}
          </div>
        </ModuleCard>
      )}

      <ModuleCard
        accent="teal"
        eyebrow="Unified · Layers"
        title="Evidence layers used"
        className="min-w-0"
      >
        <div className="flex flex-wrap gap-2">
          {layersUsed.length === 0 ? (
            <span className="text-sm text-muted-foreground">—</span>
          ) : (
            layersUsed.map((layer) => (
              <Badge key={layer} variant="outline">
                {layer.replaceAll("_", " ")}
              </Badge>
            ))
          )}
        </div>
      </ModuleCard>

      <ModuleCard
        accent="teal"
        eyebrow="Unified · Ranked Candidates"
        title="Candidate confidence"
        description="Ranked candidates from the synthesis response."
        className="min-w-0"
      >
        <div className="overflow-x-auto">
          {ranked.length === 0 ? (
            <p className="text-sm text-muted-foreground">No ranked rows.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Rank</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Label</TableHead>
                  <TableHead>Band</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Missing layers</TableHead>
                  <TableHead>Δ count</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {ranked.map((row, i) => (
                  <TableRow key={`${String(row.smiles)}-${i}`}>
                    <TableCell>{String(row.rank ?? i + 1)}</TableCell>
                    <TableCell className="max-w-[140px] truncate">{String(row.name ?? "—")}</TableCell>
                    <TableCell className="max-w-[160px] truncate text-xs">{String(row.label ?? "")}</TableCell>
                    <TableCell>{String(row.confidence_band ?? "")}</TableCell>
                    <TableCell>
                      {typeof row.confidence_score === "number" ? row.confidence_score.toFixed(3) : "—"}
                    </TableCell>
                    <TableCell className="max-w-[220px] text-xs text-muted-foreground">
                      {Array.isArray(row.missing_layers) ? row.missing_layers.join(", ") : "—"}
                    </TableCell>
                    <TableCell>{String(row.contradiction_count ?? "0")}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </ModuleCard>

      {missingSet.size > 0 && (
        <AlertCard
          variant="warning"
          title="Missing evidence (aggregated)"
          description="Layers not populated across candidates — strengthen inputs where applicable."
        >
          <ul className="list-inside list-disc space-y-1 text-sm">
            {Array.from(missingSet).map((m) => (
              <li key={m}>{m.replaceAll("_", " ")}</li>
            ))}
          </ul>
        </AlertCard>
      )}

      {globalCx.length > 0 && (
        <AlertCard variant="error" title="Contradictions (global)">
          <ul className="space-y-2 text-sm">
            {globalCx.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </AlertCard>
      )}

      {ranked.some((r) => Array.isArray(r.contradictions) && r.contradictions.length > 0) && (
        <ModuleCard
          accent="amber"
          eyebrow="Unified · Per-Candidate Contradictions"
          title="Per-candidate contradictions"
          className="min-w-0"
        >
          <div className="space-y-4">
            {ranked.map((row, i) => {
              const cx = Array.isArray(row.contradictions)
                ? row.contradictions.filter((x): x is string => typeof x === "string")
                : []
              if (cx.length === 0) return null
              return (
                <div key={`cx-${i}`} className="rounded-md border px-3 py-2 text-sm">
                  <div className="font-medium">{String(row.name ?? row.smiles ?? `Candidate ${i + 1}`)}</div>
                  <ul className="mt-1 list-inside list-disc text-muted-foreground">
                    {cx.map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>
                </div>
              )
            })}
          </div>
        </ModuleCard>
      )}

      {(ambiguity.length > 0 || warnings.length > 0 || notesList.length > 0) && (
        <AlertCard variant="warning" title="Ambiguity, warnings & notes">
          <div className="space-y-2 text-sm">
            {ambiguity.length > 0 && (
              <div>
                <p className="font-medium">Ambiguity alerts</p>
                <ul className="list-inside list-disc">
                  {ambiguity.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </div>
            )}
            {warnings.length > 0 && (
              <div>
                <p className="font-medium">Warnings</p>
                <ul className="list-inside list-disc">
                  {warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
            {notesList.length > 0 && (
              <div>
                <p className="font-medium">Notes</p>
                <ul className="list-inside list-disc">
                  {notesList.map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </AlertCard>
      )}

      {bestLayers.length > 0 && (
        <Collapsible className="rounded-lg border">
          <CollapsibleTrigger className="flex w-full px-4 py-3 text-left text-sm font-medium hover:bg-muted/50">
            Source evidence details (layer breakdown)
          </CollapsibleTrigger>
          <CollapsibleContent className="border-t px-4 pb-4">
            <div className="overflow-x-auto pt-4">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Layer</TableHead>
                    <TableHead>Score</TableHead>
                    <TableHead>Weight</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Agree</TableHead>
                    <TableHead>Contradict</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {bestLayers.map((layer, i) => (
                    <TableRow key={`${String(layer.layer)}-${i}`}>
                      <TableCell className="font-mono text-xs">{String(layer.layer ?? "")}</TableCell>
                      <TableCell>{typeof layer.score === "number" ? layer.score.toFixed(3) : "—"}</TableCell>
                      <TableCell>{typeof layer.weight === "number" ? layer.weight.toFixed(3) : "—"}</TableCell>
                      <TableCell className="max-w-[200px] truncate text-xs">{String(layer.status ?? "")}</TableCell>
                      <TableCell>{layer.agreement === true ? "yes" : "no"}</TableCell>
                      <TableCell>{layer.contradiction === true ? "yes" : "no"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}

      <Card className="min-w-0">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Human review gate</CardTitle>
          <CardDescription>
            Backend <code className="text-xs">human_review_required</code> plus automated flags from labels and
            contradictions.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          {humanReviewRequired && (
            <Badge variant="destructive" className="font-mono text-xs">
              human_review_required
            </Badge>
          )}
          {gateActive ? (
            <>
              <ShieldAlert className="h-5 w-5 text-warning" />
              <Badge variant="destructive">Review required before release decisions</Badge>
            </>
          ) : (
            <>
              <CheckCircle2 className="h-5 w-5 text-success" />
              <Badge variant="secondary">No automatic hard-stop flags (still verify experimentally)</Badge>
            </>
          )}
        </CardContent>
      </Card>

      <DeveloperJsonPanel data={data} />
    </div>
  )
}

function buildUnifiedConfidenceRequestJson(
  sampleId: string,
  solvent: string,
  candidatesText: string,
  protonText: string,
  carbonText: string,
  adv: UnifiedAdv,
) {
  const candidates = parseCandidateInputs(candidatesText)
  const hrmsObservedMz = Number(adv.hrmsMz.trim())
  const msmsPrecursorMz = Number(adv.msmsPrec.trim())

  return {
    sample_id: sampleId.trim() || null,
    solvent: solvent.trim() || null,
    candidates,
    observed_proton_text: protonText.trim() || null,
    observed_carbon13_text: carbonText.trim() || null,
    observed_nmr2d_text: adv.nmr2dText.trim() || null,
    observed_nmr2d_experiment_type: adv.nmr2dExp.trim() || null,
    hrms_observed_mz: Number.isFinite(hrmsObservedMz) && hrmsObservedMz > 0 ? hrmsObservedMz : null,
    hrms_adduct: adv.hrmsAdduct.trim() || null,
    ion_mode: adv.ionMode.trim() || null,
    hrms_ppm_tolerance: Number(adv.hrmsPpm.trim() || "5"),
    observed_m_plus_1_percent: adv.m1.trim() ? Number(adv.m1.trim()) : null,
    observed_m_plus_2_percent: adv.m2.trim() ? Number(adv.m2.trim()) : null,
    ms1_peak_list_text: adv.ms1Peaks.trim() || null,
    use_inferred_adduct: adv.useInfAdduct,
    adduct_ppm_tolerance: Number(adv.addPpm.trim() || "10"),
    isotope_mz_tolerance_da: Number(adv.isoTol.trim() || "0.02"),
    ms1_min_relative_intensity: Number(adv.ms1MinRi.trim() || "0.2"),
    ms1_max_peaks_to_analyze: Number(adv.ms1MaxPk.trim() || "200"),
    msms_peak_list_text: adv.msmsPeaks.trim() || null,
    msms_precursor_mz: Number.isFinite(msmsPrecursorMz) && msmsPrecursorMz > 0 ? msmsPrecursorMz : null,
    msms_adduct: adv.msmsAdduct.trim() || null,
    mz_tolerance_da: Number(adv.mzTol.trim() || "0.02"),
    msms_ppm_tolerance: Number(adv.msmsPpm.trim() || "20"),
    msms_min_relative_intensity: Number(adv.msmsMinRi.trim() || "1"),
    msms_max_peaks_to_analyze: Number(adv.msmsMaxPk.trim() || "75"),
    max_tree_depth: Number(adv.maxTree.trim() || "3"),
    lcms_family_table_text: adv.lcmsTable.trim() || null,
    lcms_anchor_adduct: adv.lcmsAnchor.trim() || null,
    lcms_mz_tolerance_da: Number(adv.lcmsMzTol.trim() || "0.02"),
    lcms_ppm_tolerance: Number(adv.lcmsPpm.trim() || "10"),
    lcms_min_family_consensus_score: Number(adv.lcmsMinFam.trim() || "0.42"),
    lcms_require_promoted_family: adv.lcmsReqProm,
    lcms_selected_family_id: adv.lcmsFamId.trim() || null,
  }
}

function buildStructureElucidationReportRequestJson(args: {
  reportTitle: string
  projectName: string
  preparedBy: string
  reviewerName: string
  reviewStatus: string
  reviewerComment: string
  intendedUse: string
  requireHumanApproval: boolean
  requestorNotes: string
  rawDataSha256: string
  sourceFilesText: string
  processingHistoryText: string
  sampleId: string
  solvent: string
  candidatesText: string
  protonText: string
  carbonText: string
  adv: UnifiedAdv
  latestUnifiedConfidenceResult: unknown | null
  evidenceQueueHandoff: ReturnType<typeof collectEvidenceQueueHandoff>
  provenanceMetadata: ReportProvenanceMetadata
}) {
  const source_files = args.sourceFilesText
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)
  const processing_history = args.processingHistoryText
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)

  return {
    report_title: args.reportTitle.trim() || "Regulatory-ready Structure Elucidation Report",
    sample_id: args.sampleId.trim() || null,
    project_name: args.projectName.trim() || null,
    prepared_by: args.preparedBy.trim() || null,
    reviewer_name: args.reviewerName.trim() || null,
    reviewer_comment: args.reviewerComment.trim() || null,
    review_status: args.reviewStatus.trim() || null,
    intended_use: args.intendedUse,
    require_human_approval: args.requireHumanApproval,
    requestor_notes: args.requestorNotes.trim() || null,
    raw_data_sha256: args.rawDataSha256.trim() || null,
    source_files,
    processing_history,
    unified_confidence_request: buildUnifiedConfidenceRequestJson(
      args.sampleId,
      args.solvent,
      args.candidatesText,
      args.protonText,
      args.carbonText,
      args.adv,
    ),
    ...(args.latestUnifiedConfidenceResult != null
      ? { unified_confidence_result: args.latestUnifiedConfidenceResult }
      : {}),
    ...(args.evidenceQueueHandoff.selected_count > 0
      ? { evidence_queue_handoff: args.evidenceQueueHandoff }
      : {}),
    provenance_metadata: args.provenanceMetadata,
  }
}
