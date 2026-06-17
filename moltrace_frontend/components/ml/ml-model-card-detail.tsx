"use client"

import Link from "next/link"
import { useParams } from "next/navigation"
import { useCallback, useEffect, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import {
  AlertTriangle,
  ArrowLeft,
  Database,
  ListChecks,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Target,
} from "lucide-react"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function summarizeJson(raw: unknown, maxLen = 200): string {
  if (raw == null) return "—"
  if (typeof raw === "object") {
    const s = JSON.stringify(raw)
    return s.length > maxLen ? `${s.slice(0, maxLen)}…` : s
  }
  return String(raw)
}

function objectRows(raw: unknown): { key: string; value: string }[] {
  if (!isRecord(raw)) return []
  return Object.entries(raw).map(([k, v]) => ({ key: k, value: summarizeJson(v, 240) }))
}

const CARD_TOOLTIP =
  "Model cards document intended use, training data, evaluation, limitations, calibration, out-of-domain risk, and human review status."

const APPROVAL_OPTIONS = ["draft", "ready_for_review", "approved", "rejected", "deprecated"] as const

export function MlModelCardDetail() {
  const params = useParams()
  const rawId = params?.modelCardId
  const cardIdNum =
    typeof rawId === "string" ? Number.parseInt(rawId, 10) : Array.isArray(rawId) ? Number.parseInt(rawId[0] ?? "", 10) : NaN

  const [reload, setReload] = useState(0)
  const [loading, setLoading] = useState(true)
  const [card, setCard] = useState<Record<string, unknown> | null>(null)
  const [err, setErr] = useState("")

  const [intendedUse, setIntendedUse] = useState("")
  const [limitations, setLimitations] = useState("")
  const [trainingSummaryJson, setTrainingSummaryJson] = useState("{}")
  const [evaluationSummaryJson, setEvaluationSummaryJson] = useState("{}")
  const [biasJson, setBiasJson] = useState("{}")
  const [oodJson, setOodJson] = useState("{}")
  const [calibrationJson, setCalibrationJson] = useState("{}")
  const [humanReviewJson, setHumanReviewJson] = useState("{}")
  const [approvalDraft, setApprovalDraft] = useState<string>("draft")

  const [saveBusy, setSaveBusy] = useState(false)
  const [saveErr, setSaveErr] = useState("")
  const [saveOk, setSaveOk] = useState("")

  const load = useCallback(async () => {
    if (!Number.isFinite(cardIdNum) || cardIdNum < 1) {
      setLoading(false)
      return
    }
    setLoading(true)
    setErr("")
    try {
      const raw = await apiFetch<unknown>(`/ml/model-cards/${cardIdNum}`, { method: "GET" })
      if (!isRecord(raw)) {
        setCard(null)
      } else {
        setCard(raw)
        setIntendedUse(readRecordString(raw, "intended_use") ?? "")
        setLimitations(readRecordString(raw, "limitations") ?? "")
        setTrainingSummaryJson(JSON.stringify(raw["training_data_summary_json"] ?? {}, null, 2))
        setEvaluationSummaryJson(JSON.stringify(raw["evaluation_summary_json"] ?? {}, null, 2))
        setBiasJson(JSON.stringify(raw["bias_risk_summary_json"] ?? {}, null, 2))
        setOodJson(JSON.stringify(raw["out_of_domain_summary_json"] ?? {}, null, 2))
        setCalibrationJson(JSON.stringify(raw["calibration_summary_json"] ?? {}, null, 2))
        setHumanReviewJson(JSON.stringify(raw["human_review_summary_json"] ?? {}, null, 2))
        setApprovalDraft(readRecordString(raw, "approval_status") ?? "draft")
      }
    } catch (e) {
      setErr(formatApiError(e, "Could not load model card."))
      setCard(null)
    }
    setLoading(false)
  }, [cardIdNum])

  useEffect(() => {
    void load()
  }, [load, reload])

  async function savePatch() {
    setSaveErr("")
    setSaveOk("")
    const parseObj = (raw: string, label: string): Record<string, unknown> => {
      try {
        const o = JSON.parse(raw.trim() || "{}") as unknown
        if (!o || typeof o !== "object" || Array.isArray(o)) throw new Error(label)
        return o as Record<string, unknown>
      } catch {
        throw new Error(label)
      }
    }
    let training_data_summary_json: Record<string, unknown>
    let evaluation_summary_json: Record<string, unknown>
    let bias_risk_summary_json: Record<string, unknown>
    let out_of_domain_summary_json: Record<string, unknown>
    let calibration_summary_json: Record<string, unknown>
    let human_review_summary_json: Record<string, unknown>
    try {
      training_data_summary_json = parseObj(trainingSummaryJson, "training_data_summary_json")
      evaluation_summary_json = parseObj(evaluationSummaryJson, "evaluation_summary_json")
      bias_risk_summary_json = parseObj(biasJson, "bias_risk_summary_json")
      out_of_domain_summary_json = parseObj(oodJson, "out_of_domain_summary_json")
      calibration_summary_json = parseObj(calibrationJson, "calibration_summary_json")
      human_review_summary_json = parseObj(humanReviewJson, "human_review_summary_json")
    } catch (e) {
      setSaveErr(e instanceof Error ? `${e.message} must be valid JSON objects.` : "Invalid JSON.")
      return
    }

    setSaveBusy(true)
    try {
      await apiFetch(`/ml/model-cards/${cardIdNum}`, {
        method: "PATCH",
        body: {
          intended_use: intendedUse.trim() || undefined,
          limitations: limitations.trim() || undefined,
          training_data_summary_json,
          evaluation_summary_json,
          bias_risk_summary_json,
          out_of_domain_summary_json,
          calibration_summary_json,
          human_review_summary_json,
          approval_status: approvalDraft,
        },
      })
      setSaveOk("Model card updated.")
      setReload((x) => x + 1)
    } catch (e) {
      setSaveErr(formatApiError(e, "Could not update model card."))
    } finally {
      setSaveBusy(false)
    }
  }

  if (!Number.isFinite(cardIdNum) || cardIdNum < 1) {
    return (
      <div className="p-6">
        <p className="text-sm text-destructive">Invalid model card id.</p>
      </div>
    )
  }

  const artifactLinkId = card ? readRecordNumber(card, "model_artifact_id") : undefined

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <div className="mb-1">
            <Button variant="ghost" size="sm" className="h-8 px-2" asChild>
              <Link href="/ml/models" className="inline-flex items-center gap-1 text-muted-foreground">
                <ArrowLeft className="h-4 w-4" aria-hidden />
                Model artifacts
              </Link>
            </Button>
          </div>
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-teal-ink)" }}
          >
            MolTrace · ML Model Factory · Model Card
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="font-mono text-2xl font-bold tracking-tight">Model card</h1>
            <InfoTooltip content={CARD_TOOLTIP} label="About model cards" />
          </div>
          <p className="font-mono text-sm text-muted-foreground">id {cardIdNum}</p>
        </div>
        <BackendStatusIndicator />
      </div>

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => setReload((x) => x + 1)}>
          {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : <RefreshCw className="mr-2 h-4 w-4" aria-hidden />}
          Refresh
        </Button>
        {artifactLinkId != null ? (
          <Button variant="outline" size="sm" asChild>
            <Link href={`/ml/models/${artifactLinkId}`}>Model artifact</Link>
          </Button>
        ) : null}
      </div>

      {err ? (
        <AlertCard
          variant="error"
          title={`GET /ml/model-cards/{model_card_id}`}
          description={err}
        />
      ) : null}

      {card ? (
        <>
          <ModuleCard
            accent="teal"
            eyebrow="Validation"
            title="approval_status"
            icon={ShieldCheck}
            description="Shown from the API only — do not treat models as cleared for production outside this workflow."
          >
            <Badge variant="outline" className="text-sm">
              {readRecordString(card, "approval_status") ?? "—"}
            </Badge>
          </ModuleCard>

          <ModuleCard
            accent="teal"
            eyebrow="Intended Use"
            title="intended_use"
            icon={Target}
          >
            <div className="whitespace-pre-wrap text-sm">{readRecordString(card, "intended_use") ?? "—"}</div>
          </ModuleCard>

          <ModuleCard
            accent="teal"
            eyebrow="Limitations"
            title="limitations"
            icon={AlertTriangle}
          >
            <div className="whitespace-pre-wrap text-sm">{readRecordString(card, "limitations") ?? "—"}</div>
          </ModuleCard>

          <SummaryTable title="training_data_summary_json" rows={objectRows(card["training_data_summary_json"])} />
          <SummaryTable title="evaluation_summary_json" rows={objectRows(card["evaluation_summary_json"])} />
          <SummaryTable title="bias_risk_summary_json" rows={objectRows(card["bias_risk_summary_json"])} />
          <SummaryTable title="out_of_domain_summary_json" rows={objectRows(card["out_of_domain_summary_json"])} />
          <SummaryTable title="calibration_summary_json" rows={objectRows(card["calibration_summary_json"])} />
          <SummaryTable title="human_review_summary_json" rows={objectRows(card["human_review_summary_json"])} />

          <DeveloperJsonPanel data={card} />

          <ModuleCard
            accent="teal"
            eyebrow="Distribution"
            title={
              <span className="flex flex-wrap items-center gap-2">
                Create / update model card
                <InfoTooltip content={CARD_TOOLTIP} label="About model cards" />
              </span>
            }
            icon={ListChecks}
            description="Update the model card — revise intended use, limitations, training data summary, and evaluation summary for governance review."
          >
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="iu2">intended_use</Label>
                <Textarea id="iu2" value={intendedUse} onChange={(e) => setIntendedUse(e.target.value)} rows={5} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="lm2">limitations</Label>
                <Textarea id="lm2" value={limitations} onChange={(e) => setLimitations(e.target.value)} rows={5} />
              </div>
              <JsonArea label="training_data_summary_json" value={trainingSummaryJson} onChange={setTrainingSummaryJson} />
              <JsonArea label="evaluation_summary_json" value={evaluationSummaryJson} onChange={setEvaluationSummaryJson} />
              <JsonArea label="bias_risk_summary_json" value={biasJson} onChange={setBiasJson} />
              <JsonArea label="out_of_domain_summary_json" value={oodJson} onChange={setOodJson} />
              <JsonArea label="calibration_summary_json" value={calibrationJson} onChange={setCalibrationJson} />
              <JsonArea label="human_review_summary_json" value={humanReviewJson} onChange={setHumanReviewJson} />
              <div className="space-y-2">
                <Label>approval_status</Label>
                <Select value={approvalDraft} onValueChange={setApprovalDraft}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {APPROVAL_OPTIONS.map((o) => (
                      <SelectItem key={o} value={o}>
                        {o}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {saveErr ? <p className="text-sm text-destructive">{saveErr}</p> : null}
              {saveOk ? <p className="text-sm text-muted-foreground">{saveOk}</p> : null}
              <Button type="button" disabled={saveBusy || loading} onClick={() => void savePatch()}>
                {saveBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : null}
                Update model card
              </Button>
            </div>
          </ModuleCard>
        </>
      ) : !loading && !err ? (
        <p className="text-sm text-muted-foreground">No card loaded.</p>
      ) : null}
    </div>
  )
}

function SummaryTable({ title, rows }: { title: string; rows: { key: string; value: string }[] }) {
  return (
    <ModuleCard accent="teal" eyebrow="Summary" title={title} icon={Database}>
      <div className="table-scroll min-w-0">
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">—</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>key</TableHead>
                <TableHead>value (summary)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.key}>
                  <TableCell className="font-mono text-xs">{r.key}</TableCell>
                  <TableCell className="max-w-[480px] text-xs">{r.value}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </ModuleCard>
  )
}

function JsonArea({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={`jf-${label}`}>{label}</Label>
      <Textarea
        id={`jf-${label}`}
        className="min-h-[88px] font-mono text-xs"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
      />
    </div>
  )
}
