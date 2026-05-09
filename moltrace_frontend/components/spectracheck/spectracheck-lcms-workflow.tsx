"use client"

import { FormEvent, useMemo, useRef, useState } from "react"
import { ApiError, apiFetch } from "@/lib/api/client"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { SpectraCheckUseUnifiedEvidenceButton } from "@/components/spectracheck/spectracheck-use-unified-evidence-button"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { LcmsWorkflowMetrics } from "@/components/spectracheck/spectracheck-lcms-metrics"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertCard } from "@/components/dashboard/alert-card"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Checkbox } from "@/components/ui/checkbox"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"
import type { EvidenceLayerType } from "@/src/lib/spectracheck/evidence-types"

const STEP_UNIFIED_META: Record<string, { layer: EvidenceLayerType; endpoint: string; title: string }> = {
  import: {
    layer: "lcms_import",
    endpoint: "/ms/lcms/import/bridge/upload",
    title: "LC-MS import bridge",
  },
  detect: {
    layer: "lcms_feature_detection",
    endpoint: "/ms/lcms/features/detect/upload",
    title: "LC-MS feature detection",
  },
  group: {
    layer: "lcms_feature_grouping",
    endpoint: "/ms/lcms/features/group/upload",
    title: "LC-MS feature grouping",
  },
  consensus: {
    layer: "lcms_feature_family_consensus",
    endpoint: "/ms/lcms/features/consensus/upload",
    title: "LC-MS feature-family consensus",
  },
  dereplication: {
    layer: "lcms_dereplication",
    endpoint: "/ms/lcms/dereplication/upload",
    title: "LC-MS library dereplication",
  },
  bridge: {
    layer: "lcms_confidence_bridge",
    endpoint: "/confidence/candidates/lcms-consensus-bridge",
    title: "LC-MS consensus bridge",
  },
}

type Props = {
  sampleId: string
  candidatesText: string
}

type StepDef = {
  key: string
  title: string
  endpoint: string
}

const STEPS: StepDef[] = [
  { key: "import", title: "Import Bridge", endpoint: "Ingest LC-MS data and prepare it for downstream analysis." },
  { key: "detect", title: "Feature Detection", endpoint: "Detect chromatographic features (peaks) across runs." },
  { key: "group", title: "Grouping / Blank / RT align", endpoint: "Group features, subtract blanks, and align retention times." },
  { key: "consensus", title: "Feature-Family Consensus", endpoint: "Combine feature families into a per-sample consensus." },
  { key: "dereplication", title: "Library Dereplication", endpoint: "Match features against compound libraries to remove known hits." },
  { key: "bridge", title: "LC-MS Consensus Bridge", endpoint: "Bridge the LC-MS consensus into the unified candidate confidence." },
]

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

function textToUploadFile(content: string, filename: string) {
  return new File([content], filename, { type: "text/plain;charset=utf-8" })
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

export function SpectraCheckLcmsWorkflow({ sampleId, candidatesText }: Props) {
  const [stepIndex, setStepIndex] = useState(0)

  const [chainRawFile, setChainRawFile] = useState<File | null>(null)

  const [importErr, setImportErr] = useState("")
  const [detectErr, setDetectErr] = useState("")
  const [groupErr, setGroupErr] = useState("")
  const [consensusErr, setConsensusErr] = useState("")
  const [dereplicationErr, setDereplicationErr] = useState("")
  const [bridgeErr, setBridgeErr] = useState("")

  const [importResult, setImportResult] = useState<unknown>(null)
  const [detectResult, setDetectResult] = useState<unknown>(null)
  const [groupResult, setGroupResult] = useState<unknown>(null)
  const [consensusResult, setConsensusResult] = useState<unknown>(null)
  const [dereplicationResult, setDereplicationResult] = useState<unknown>(null)
  const [bridgeResult, setBridgeResult] = useState<unknown>(null)

  const [importBusy, setImportBusy] = useState(false)
  const [detectBusy, setDetectBusy] = useState(false)
  const [groupBusy, setGroupBusy] = useState(false)
  const [consensusBusy, setConsensusBusy] = useState(false)
  const [dereplicationBusy, setDereplicationBusy] = useState(false)
  const [bridgeBusy, setBridgeBusy] = useState(false)

  const importRef = useRef<HTMLInputElement>(null)
  const detectRef = useRef<HTMLInputElement>(null)
  const groupSampleRef = useRef<HTMLInputElement>(null)
  const groupBlankRef = useRef<HTMLInputElement>(null)
  const consensusFeatureRef = useRef<HTMLInputElement>(null)
  const consensusSampleRef = useRef<HTMLInputElement>(null)
  const consensusBlankRef = useRef<HTMLInputElement>(null)
  const derepRef = useRef<HTMLInputElement>(null)

  const [useChainForDetect, setUseChainForDetect] = useState(true)
  const [useChainForGroupSample, setUseChainForGroupSample] = useState(true)

  const [importFmt, setImportFmt] = useState("auto")
  const [detectFmt, setDetectFmt] = useState("auto")
  const [groupFmt, setGroupFmt] = useState("auto")
  const [consensusFmt, setConsensusFmt] = useState("auto")

  const [impPrecMz, setImpPrecMz] = useState("")
  const [impMinRi, setImpMinRi] = useState("0.5")
  const [impMaxMs1, setImpMaxMs1] = useState("250")
  const [impMaxMsms, setImpMaxMsms] = useState("250")
  const [impMaxPps, setImpMaxPps] = useState("50")
  const [impMaxScanRep, setImpMaxScanRep] = useState("250")
  const [impMzTol, setImpMzTol] = useState("0.02")
  const [impPpmTol, setImpPpmTol] = useState("20")

  const [detTargetMz, setDetTargetMz] = useState("")
  const [detMzTol, setDetMzTol] = useState("0.02")
  const [detPpmTol, setDetPpmTol] = useState("20")
  const [detMinFeatH, setDetMinFeatH] = useState("5")
  const [detMinPeakH, setDetMinPeakH] = useState("0")
  const [detMinScans, setDetMinScans] = useState("2")
  const [detSmooth, setDetSmooth] = useState("1")
  const [detPurityWin, setDetPurityWin] = useState("0.2")
  const [detTopCo, setDetTopCo] = useState("5")
  const [detMaxFeat, setDetMaxFeat] = useState("20")
  const [detMaxScanRep, setDetMaxScanRep] = useState("1000")
  const [detMaxXic, setDetMaxXic] = useState("5000")

  const [grpTargetMz, setGrpTargetMz] = useState("")
  const [grpAnchorMz, setGrpAnchorMz] = useState("")
  const [grpMzTol, setGrpMzTol] = useState("0.02")
  const [grpPpmTol, setGrpPpmTol] = useState("20")
  const [grpMinFeatH, setGrpMinFeatH] = useState("5")
  const [grpMinPeakH, setGrpMinPeakH] = useState("0")
  const [grpMinScans, setGrpMinScans] = useState("2")
  const [grpSmooth, setGrpSmooth] = useState("1")
  const [grpPurityWin, setGrpPurityWin] = useState("0.2")
  const [grpGrpRt, setGrpGrpRt] = useState("0.12")
  const [grpFamRt, setGrpFamRt] = useState("0.15")
  const [grpAlignWin, setGrpAlignWin] = useState("1.0")
  const [grpBlankRatio, setGrpBlankRatio] = useState("0.30")
  const [grpPossBg, setGrpPossBg] = useState("0.10")
  const [grpBlankFact, setGrpBlankFact] = useState("1.0")
  const [grpMaxFeatRun, setGrpMaxFeatRun] = useState("50")
  const [grpMaxGroups, setGrpMaxGroups] = useState("100")
  const [grpAlignRt, setGrpAlignRt] = useState(true)
  const [grpAnnotFam, setGrpAnnotFam] = useState(true)

  const [conTargetMz, setConTargetMz] = useState("")
  const [conFormula, setConFormula] = useState("")
  const [conAdduct, setConAdduct] = useState("[M+H]+")
  const [conMzTol, setConMzTol] = useState("0.02")
  const [conPpmTol, setConPpmTol] = useState("20")
  const [conFamRt, setConFamRt] = useState("0.15")
  const [conMinPromote, setConMinPromote] = useState("0.62")

  const [brAdduct, setBrAdduct] = useState("[M+H]+")
  const [brMzTol, setBrMzTol] = useState("0.02")
  const [brPpmTol, setBrPpmTol] = useState("10")
  const [brMinFam, setBrMinFam] = useState("0.42")
  const [brRequirePromoted, setBrRequirePromoted] = useState(true)
  const [brFamilyId, setBrFamilyId] = useState("")

  const current = STEPS[stepIndex] ?? STEPS[0]

  const resultsByKey = useMemo(
    () => ({
      import: importResult,
      detect: detectResult,
      group: groupResult,
      consensus: consensusResult,
      dereplication: dereplicationResult,
      bridge: bridgeResult,
    }),
    [importResult, detectResult, groupResult, consensusResult, dereplicationResult, bridgeResult],
  )

  function stepStatusLine(key: string): string {
    const r = resultsByKey[key as keyof typeof resultsByKey]
    if (!r || !isRecord(r)) return "Not run yet"
    if (key === "import") return `scans ${String(r.scan_count ?? "—")}`
    if (key === "detect") return `features ${String(r.feature_count ?? "—")}`
    if (key === "group") return `groups ${String(r.group_count ?? "—")}`
    if (key === "consensus") return `families ${String(r.family_count ?? "—")}, promoted ${String(r.promoted_family_count ?? "—")}`
    if (key === "bridge") return `hits ${Array.isArray(r.matches) ? r.matches.length : "—"}`
    if (key === "dereplication") return r ? "response received" : "Not run yet"
    return "Done"
  }

  async function runImport(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    setImportErr("")
    const f = importRef.current?.files?.[0]
    if (!f) {
      setImportErr("Choose an LC-MS/MS import file.")
      return
    }
    const fd = new FormData()
    fd.append("file", f)
    fd.append("source_format", importFmt.trim() || "auto")
    if (impPrecMz.trim()) fd.append("preferred_msms_precursor_mz", impPrecMz.trim())
    fd.append("min_relative_intensity", impMinRi.trim() || "0.5")
    fd.append("max_ms1_peaks", impMaxMs1.trim() || "250")
    fd.append("max_msms_peaks_per_spectrum", impMaxMsms.trim() || "250")
    fd.append("max_peaks_per_spectrum", impMaxPps.trim() || "50")
    fd.append("max_scans_to_report", impMaxScanRep.trim() || "250")
    fd.append("mz_tolerance_da", impMzTol.trim() || "0.02")
    fd.append("ppm_tolerance", impPpmTol.trim() || "20")
    if (sampleId.trim()) fd.append("sample_id", sampleId.trim())
    setImportBusy(true)
    try {
      const data = await apiFetch<unknown>("/ms/lcms/import/bridge/upload", { method: "POST", body: fd })
      setImportResult(data)
      setChainRawFile(f)
    } catch (err) {
      setImportErr(formatApiError(err, "Import bridge failed"))
    } finally {
      setImportBusy(false)
    }
  }

  async function runDetect(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    setDetectErr("")
    const fromChain = useChainForDetect && chainRawFile
    const f = fromChain ? chainRawFile : detectRef.current?.files?.[0]
    if (!f) {
      setDetectErr("Choose a file or run Import Bridge and enable “use cached file”.")
      return
    }
    const fd = new FormData()
    fd.append("file", f)
    fd.append("source_format", detectFmt.trim() || "auto")
    if (detTargetMz.trim()) fd.append("target_mz_text", detTargetMz.trim())
    fd.append("mz_tolerance_da", detMzTol.trim() || "0.02")
    fd.append("ppm_tolerance", detPpmTol.trim() || "20")
    fd.append("min_relative_feature_height", detMinFeatH.trim() || "5")
    fd.append("min_peak_height", detMinPeakH.trim() || "0")
    fd.append("min_scans_per_feature", detMinScans.trim() || "2")
    fd.append("smoothing_window", detSmooth.trim() || "1")
    fd.append("purity_rt_window_min", detPurityWin.trim() || "0.2")
    fd.append("top_coeluting_ions", detTopCo.trim() || "5")
    fd.append("max_features", detMaxFeat.trim() || "20")
    fd.append("max_scans_to_report", detMaxScanRep.trim() || "1000")
    fd.append("max_xic_points", detMaxXic.trim() || "5000")
    if (sampleId.trim()) fd.append("sample_id", sampleId.trim())
    setDetectBusy(true)
    try {
      const data = await apiFetch<unknown>("/ms/lcms/features/detect/upload", { method: "POST", body: fd })
      setDetectResult(data)
    } catch (err) {
      setDetectErr(formatApiError(err, "Feature detection failed"))
    } finally {
      setDetectBusy(false)
    }
  }

  async function runGroup(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    setGroupErr("")
    const fromChain = useChainForGroupSample && chainRawFile
    const sampleFile = fromChain ? chainRawFile : groupSampleRef.current?.files?.[0]
    if (!sampleFile) {
      setGroupErr("Choose a sample file or enable cached import file.")
      return
    }
    const fd = new FormData()
    fd.append("sample_file", sampleFile)
    const blank = groupBlankRef.current?.files?.[0]
    if (blank) fd.append("blank_file", blank)
    fd.append("source_format", groupFmt.trim() || "auto")
    if (grpTargetMz.trim()) fd.append("target_mz_text", grpTargetMz.trim())
    if (grpAnchorMz.trim()) fd.append("alignment_anchor_mz_text", grpAnchorMz.trim())
    fd.append("mz_tolerance_da", grpMzTol.trim() || "0.02")
    fd.append("ppm_tolerance", grpPpmTol.trim() || "20")
    fd.append("min_relative_feature_height", grpMinFeatH.trim() || "5")
    fd.append("min_peak_height", grpMinPeakH.trim() || "0")
    fd.append("min_scans_per_feature", grpMinScans.trim() || "2")
    fd.append("smoothing_window", grpSmooth.trim() || "1")
    fd.append("purity_rt_window_min", grpPurityWin.trim() || "0.2")
    fd.append("group_rt_tolerance_min", grpGrpRt.trim() || "0.12")
    fd.append("family_rt_tolerance_min", grpFamRt.trim() || "0.15")
    fd.append("rt_alignment_search_window_min", grpAlignWin.trim() || "1.0")
    fd.append("blank_area_ratio_threshold", grpBlankRatio.trim() || "0.30")
    fd.append("possible_background_ratio_threshold", grpPossBg.trim() || "0.10")
    fd.append("blank_subtraction_factor", grpBlankFact.trim() || "1.0")
    fd.append("max_features_per_run", grpMaxFeatRun.trim() || "50")
    fd.append("max_groups_to_report", grpMaxGroups.trim() || "100")
    fd.append("align_retention_times", grpAlignRt ? "true" : "false")
    fd.append("annotate_feature_families", grpAnnotFam ? "true" : "false")
    if (sampleId.trim()) fd.append("sample_id", sampleId.trim())
    setGroupBusy(true)
    try {
      const data = await apiFetch<unknown>("/ms/lcms/features/group/upload", { method: "POST", body: fd })
      setGroupResult(data)
    } catch (err) {
      setGroupErr(formatApiError(err, "Feature grouping failed"))
    } finally {
      setGroupBusy(false)
    }
  }

  async function runConsensus(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    setConsensusErr("")
    const fd = new FormData()
    let attached = false
    const gr = groupResult && isRecord(groupResult) ? groupResult : null
    const tableText = gr && typeof gr.feature_table_text === "string" ? gr.feature_table_text : ""
    const ft = consensusFeatureRef.current?.files?.[0]
    if (ft) {
      fd.append("feature_table_file", ft)
      attached = true
    } else if (tableText.trim()) {
      fd.append("feature_table_file", textToUploadFile(tableText, "feature_table.tsv"))
      attached = true
    }
    const cs = consensusSampleRef.current?.files?.[0]
    const cb = consensusBlankRef.current?.files?.[0]
    if (cs) {
      fd.append("sample_file", cs)
      attached = true
    }
    if (cb) fd.append("blank_file", cb)
    if (!attached) {
      setConsensusErr("Provide a feature table (from step 3, upload, or sample run).")
      return
    }
    fd.append("source_format", consensusFmt.trim() || "auto")
    if (conTargetMz.trim()) fd.append("target_mz_text", conTargetMz.trim())
    if (conFormula.trim()) fd.append("formula", conFormula.trim())
    fd.append("expected_anchor_adduct", conAdduct.trim() || "[M+H]+")
    fd.append("mz_tolerance_da", conMzTol.trim() || "0.02")
    fd.append("ppm_tolerance", conPpmTol.trim() || "20")
    fd.append("family_rt_tolerance_min", conFamRt.trim() || "0.15")
    fd.append("min_consensus_score_to_promote", conMinPromote.trim() || "0.62")
    if (sampleId.trim()) fd.append("sample_id", sampleId.trim())
    setConsensusBusy(true)
    try {
      const data = await apiFetch<unknown>("/ms/lcms/features/consensus/upload", { method: "POST", body: fd })
      setConsensusResult(data)
    } catch (err) {
      setConsensusErr(formatApiError(err, "Feature-family consensus failed"))
    } finally {
      setConsensusBusy(false)
    }
  }

  async function runDereplication(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    setDereplicationErr("")
    const f = derepRef.current?.files?.[0]
    if (!f) {
      setDereplicationErr("Choose a library file to dereplicate.")
      return
    }
    const fd = new FormData()
    fd.append("file", f)
    if (sampleId.trim()) fd.append("sample_id", sampleId.trim())
    setDereplicationBusy(true)
    try {
      const data = await apiFetch<unknown>("/ms/lcms/dereplication/upload", { method: "POST", body: fd })
      setDereplicationResult(data)
    } catch (err) {
      if (err instanceof ApiError && (err.status === 404 || err.status === 405)) {
        setDereplicationErr(
          "Library dereplication isn't available on this server build — the step is shown as a workflow placeholder only.",
        )
      } else {
        setDereplicationErr(formatApiError(err, "Library dereplication failed"))
      }
      setDereplicationResult(null)
    } finally {
      setDereplicationBusy(false)
    }
  }

  async function runBridge(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    setBridgeErr("")
    const candidates = parseCandidateInputs(candidatesText)
    if (candidates.length === 0) {
      setBridgeErr("Add at least one candidate line (SMILES) in shared session inputs.")
      return
    }
    if (!consensusResult || !isRecord(consensusResult)) {
      setBridgeErr("Run the Feature-Family Consensus step first so a consensus payload can be sent.")
      return
    }
    const payload = {
      sample_id: sampleId.trim() || null,
      candidates,
      lcms_consensus_result: consensusResult,
      adduct: brAdduct.trim() || "[M+H]+",
      mz_tolerance_da: Number(brMzTol.trim() || "0.02"),
      ppm_tolerance: Number(brPpmTol.trim() || "10"),
      min_family_consensus_score: Number(brMinFam.trim() || "0.42"),
      require_promoted_family: brRequirePromoted,
      selected_family_id: brFamilyId.trim() || null,
    }
    setBridgeBusy(true)
    try {
      const data = await apiFetch<unknown>("/confidence/candidates/lcms-consensus-bridge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      setBridgeResult(data)
    } catch (err) {
      setBridgeErr(formatApiError(err, "LC-MS consensus bridge failed"))
    } finally {
      setBridgeBusy(false)
    }
  }

  const activeResult = resultsByKey[current.key as keyof typeof resultsByKey]
  const activeErr =
    current.key === "import"
      ? importErr
      : current.key === "detect"
        ? detectErr
        : current.key === "group"
          ? groupErr
          : current.key === "consensus"
            ? consensusErr
            : current.key === "dereplication"
              ? dereplicationErr
              : bridgeErr

  const activeBusy =
    current.key === "import"
      ? importBusy
      : current.key === "detect"
        ? detectBusy
        : current.key === "group"
          ? groupBusy
          : current.key === "consensus"
            ? consensusBusy
            : current.key === "dereplication"
              ? dereplicationBusy
              : bridgeBusy

  function renderWarnings(data: unknown) {
    if (!isRecord(data)) return null
    const w = data.warnings
    if (!Array.isArray(w) || w.length === 0) return null
    const lines = w.filter((x): x is string => typeof x === "string")
    if (lines.length === 0) return null
    return (
      <AlertCard variant="warning" title="Warnings">
        <ul className="list-inside list-disc space-y-1 text-sm">
          {lines.slice(0, 12).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </AlertCard>
    )
  }

  return (
    <div className="space-y-4">
      <ModuleCard
        accent="teal"
        eyebrow="Spectroscopy · LC-MS Workflow"
        title="LC-MS workflow"
        description="Progressive LC-MS processing: run steps in order when possible—later steps can reuse outputs from earlier steps. Treat outputs as decision-support; confirm with experimental context."
      />

      <div className="flex flex-wrap gap-2">
        {STEPS.map((s, i) => (
          <Button
            key={s.key}
            type="button"
            size="sm"
            variant={i === stepIndex ? "default" : "outline"}
            className={cn(i === stepIndex && "ring-2 ring-ring")}
            onClick={() => setStepIndex(i)}
          >
            <span className="mr-1 font-mono text-xs opacity-80">{i + 1}</span>
            {s.title}
          </Button>
        ))}
      </div>

      <Collapsible className="rounded-lg border bg-muted/30">
        <CollapsibleTrigger className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium hover:bg-muted/50">
          Workflow summary (other steps)
          <Badge variant="secondary">{STEPS.length - 1} steps</Badge>
        </CollapsibleTrigger>
        <CollapsibleContent className="border-t px-4 py-3">
          <ul className="space-y-2 text-sm text-muted-foreground">
            {STEPS.map((s, i) =>
              i === stepIndex ? null : (
                <li key={s.key}>
                  <span className="font-medium text-foreground">{s.title}</span> — {stepStatusLine(s.key)}
                </li>
              ),
            )}
          </ul>
        </CollapsibleContent>
      </Collapsible>

      <ModuleCard
        accent="teal"
        eyebrow={`LC-MS · Step ${stepIndex + 1}`}
        title={current.title}
        description={current.endpoint}
        badge={
          <Badge variant="outline" className="shrink-0">
            Step {stepIndex + 1} / {STEPS.length}
          </Badge>
        }
        className="min-w-0"
      >
        <div className="space-y-6">
          {activeErr && (
            <AlertCard variant="error" title="Step failed" description={activeErr} />
          )}

          {current.key === "import" && (
            <form onSubmit={runImport} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="lcms-import-file">LC-MS/MS file</Label>
                <Input id="lcms-import-file" ref={importRef} type="file" required />
              </div>
              <label className="block space-y-2">
                <span className="text-sm font-medium">Source format</span>
                <Input value={importFmt} onChange={(e) => setImportFmt(e.target.value)} placeholder="auto" />
              </label>
              <Collapsible className="rounded-md border">
                <CollapsibleTrigger className="flex w-full px-4 py-3 text-left text-sm font-medium hover:bg-muted/50">
                  Advanced settings
                </CollapsibleTrigger>
                <CollapsibleContent className="space-y-3 border-t px-4 py-4">
                  <label className="block space-y-1">
                    <span className="text-xs text-muted-foreground">Preferred MS/MS precursor m/z</span>
                    <Input value={impPrecMz} onChange={(e) => setImpPrecMz(e.target.value)} />
                  </label>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="Min rel. intensity" value={impMinRi} onChange={setImpMinRi} />
                    <Field label="Max MS1 peaks" value={impMaxMs1} onChange={setImpMaxMs1} />
                    <Field label="Max MS/MS peaks / spectrum" value={impMaxMsms} onChange={setImpMaxMsms} />
                    <Field label="Max peaks / spectrum" value={impMaxPps} onChange={setImpMaxPps} />
                    <Field label="Max scans to report" value={impMaxScanRep} onChange={setImpMaxScanRep} />
                    <Field label="m/z tol. (Da)" value={impMzTol} onChange={setImpMzTol} />
                    <Field label="ppm tolerance" value={impPpmTol} onChange={setImpPpmTol} />
                  </div>
                </CollapsibleContent>
              </Collapsible>
              <Button type="submit" disabled={importBusy}>
                {importBusy ? "Uploading…" : "Run import bridge"}
              </Button>
            </form>
          )}

          {current.key === "detect" && (
            <form onSubmit={runDetect} className="space-y-4">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="det-chain"
                  checked={useChainForDetect}
                  onCheckedChange={(v) => setUseChainForDetect(v === true)}
                  disabled={!chainRawFile}
                />
                <Label htmlFor="det-chain" className="text-sm font-normal">
                  Use cached file from Import Bridge {chainRawFile ? `(${chainRawFile.name})` : "(run step 1 first)"}
                </Label>
              </div>
              {!useChainForDetect && (
                <div className="space-y-2">
                  <Label>Raw / peak-list file</Label>
                  <Input ref={detectRef} type="file" />
                </div>
              )}
              <label className="block space-y-2">
                <span className="text-sm font-medium">Source format</span>
                <Input value={detectFmt} onChange={(e) => setDetectFmt(e.target.value)} />
              </label>
              <Collapsible className="rounded-md border">
                <CollapsibleTrigger className="flex w-full px-4 py-3 text-left text-sm font-medium hover:bg-muted/50">
                  Advanced settings
                </CollapsibleTrigger>
                <CollapsibleContent className="space-y-3 border-t px-4 py-4">
                  <label className="block space-y-1">
                    <span className="text-xs text-muted-foreground">Target m/z text (optional)</span>
                    <Input value={detTargetMz} onChange={(e) => setDetTargetMz(e.target.value)} />
                  </label>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="m/z tol. (Da)" value={detMzTol} onChange={setDetMzTol} />
                    <Field label="ppm tolerance" value={detPpmTol} onChange={setDetPpmTol} />
                    <Field label="Min rel. feature height %" value={detMinFeatH} onChange={setDetMinFeatH} />
                    <Field label="Min peak height" value={detMinPeakH} onChange={setDetMinPeakH} />
                    <Field label="Min scans / feature" value={detMinScans} onChange={setDetMinScans} />
                    <Field label="Smoothing window" value={detSmooth} onChange={setDetSmooth} />
                    <Field label="Purity RT window (min)" value={detPurityWin} onChange={setDetPurityWin} />
                    <Field label="Top co-eluting ions" value={detTopCo} onChange={setDetTopCo} />
                    <Field label="Max features" value={detMaxFeat} onChange={setDetMaxFeat} />
                    <Field label="Max scans to report" value={detMaxScanRep} onChange={setDetMaxScanRep} />
                    <Field label="Max XIC points" value={detMaxXic} onChange={setDetMaxXic} />
                  </div>
                </CollapsibleContent>
              </Collapsible>
              <Button type="submit" disabled={detectBusy}>
                {detectBusy ? "Running…" : "Run feature detection"}
              </Button>
            </form>
          )}

          {current.key === "group" && (
            <form onSubmit={runGroup} className="space-y-4">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="grp-chain"
                  checked={useChainForGroupSample}
                  onCheckedChange={(v) => setUseChainForGroupSample(v === true)}
                  disabled={!chainRawFile}
                />
                <Label htmlFor="grp-chain" className="text-sm font-normal">
                  Use cached import file as sample {chainRawFile ? `(${chainRawFile.name})` : ""}
                </Label>
              </div>
              {!useChainForGroupSample && (
                <div className="space-y-2">
                  <Label>Sample run file</Label>
                  <Input ref={groupSampleRef} type="file" required />
                </div>
              )}
              <div className="space-y-2">
                <Label>Blank run file (optional)</Label>
                <Input ref={groupBlankRef} type="file" />
              </div>
              <label className="block space-y-2">
                <span className="text-sm font-medium">Source format</span>
                <Input value={groupFmt} onChange={(e) => setGroupFmt(e.target.value)} />
              </label>
              <Collapsible className="rounded-md border">
                <CollapsibleTrigger className="flex w-full px-4 py-3 text-left text-sm font-medium hover:bg-muted/50">
                  Advanced settings
                </CollapsibleTrigger>
                <CollapsibleContent className="space-y-3 border-t px-4 py-4">
                  <label className="block space-y-1">
                    <span className="text-xs text-muted-foreground">Target m/z text</span>
                    <Input value={grpTargetMz} onChange={(e) => setGrpTargetMz(e.target.value)} />
                  </label>
                  <label className="block space-y-1">
                    <span className="text-xs text-muted-foreground">Alignment anchor m/z text</span>
                    <Input value={grpAnchorMz} onChange={(e) => setGrpAnchorMz(e.target.value)} />
                  </label>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="m/z tol. (Da)" value={grpMzTol} onChange={setGrpMzTol} />
                    <Field label="ppm tolerance" value={grpPpmTol} onChange={setGrpPpmTol} />
                    <Field label="Min rel. feature height %" value={grpMinFeatH} onChange={setGrpMinFeatH} />
                    <Field label="Min peak height" value={grpMinPeakH} onChange={setGrpMinPeakH} />
                    <Field label="Min scans / feature" value={grpMinScans} onChange={setGrpMinScans} />
                    <Field label="Smoothing window" value={grpSmooth} onChange={setGrpSmooth} />
                    <Field label="Purity RT window (min)" value={grpPurityWin} onChange={setGrpPurityWin} />
                    <Field label="Group RT tol. (min)" value={grpGrpRt} onChange={setGrpGrpRt} />
                    <Field label="Family RT tol. (min)" value={grpFamRt} onChange={setGrpFamRt} />
                    <Field label="RT align search window (min)" value={grpAlignWin} onChange={setGrpAlignWin} />
                    <Field label="Blank area ratio threshold" value={grpBlankRatio} onChange={setGrpBlankRatio} />
                    <Field label="Possible background ratio" value={grpPossBg} onChange={setGrpPossBg} />
                    <Field label="Blank subtraction factor" value={grpBlankFact} onChange={setGrpBlankFact} />
                    <Field label="Max features / run" value={grpMaxFeatRun} onChange={setGrpMaxFeatRun} />
                    <Field label="Max groups to report" value={grpMaxGroups} onChange={setGrpMaxGroups} />
                  </div>
                  <div className="flex flex-wrap gap-4">
                    <div className="flex items-center gap-2">
                      <Checkbox id="grp-al" checked={grpAlignRt} onCheckedChange={(v) => setGrpAlignRt(v === true)} />
                      <Label htmlFor="grp-al">Align retention times</Label>
                    </div>
                    <div className="flex items-center gap-2">
                      <Checkbox id="grp-an" checked={grpAnnotFam} onCheckedChange={(v) => setGrpAnnotFam(v === true)} />
                      <Label htmlFor="grp-an">Annotate feature families</Label>
                    </div>
                  </div>
                </CollapsibleContent>
              </Collapsible>
              <Button type="submit" disabled={groupBusy}>
                {groupBusy ? "Running…" : "Run grouping / blank / alignment"}
              </Button>
            </form>
          )}

          {current.key === "consensus" && (
            <form onSubmit={runConsensus} className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Primary path: uses <strong>feature_table_text</strong> from step 3 when available. You may override with
                uploads.
              </p>
              {groupResult && isRecord(groupResult) && typeof groupResult.feature_table_text === "string" && groupResult.feature_table_text.trim() ? (
                <div
                  className="rounded-md border px-3 py-2 text-sm"
                  style={{ borderColor: "var(--mt-green)", background: "var(--mt-green-soft)" }}
                >
                  Feature table from step 3 will be sent ({groupResult.feature_table_text.length} chars).
                </div>
              ) : (
                <div
                  className="rounded-md border px-3 py-2 text-sm"
                  style={{ borderColor: "var(--mt-amber)", background: "var(--mt-amber-soft)" }}
                >
                  Run step 3 first or upload a feature table / sample below.
                </div>
              )}
              <div className="space-y-2">
                <Label>Feature table file (optional override)</Label>
                <Input ref={consensusFeatureRef} type="file" />
              </div>
              <div className="space-y-2">
                <Label>Sample file (optional)</Label>
                <Input ref={consensusSampleRef} type="file" />
              </div>
              <div className="space-y-2">
                <Label>Blank file (optional)</Label>
                <Input ref={consensusBlankRef} type="file" />
              </div>
              <label className="block space-y-2">
                <span className="text-sm font-medium">Source format</span>
                <Input value={consensusFmt} onChange={(e) => setConsensusFmt(e.target.value)} />
              </label>
              <Collapsible className="rounded-md border">
                <CollapsibleTrigger className="flex w-full px-4 py-3 text-left text-sm font-medium hover:bg-muted/50">
                  Advanced settings
                </CollapsibleTrigger>
                <CollapsibleContent className="space-y-3 border-t px-4 py-4">
                  <label className="block space-y-1">
                    <span className="text-xs text-muted-foreground">Target m/z text</span>
                    <Input value={conTargetMz} onChange={(e) => setConTargetMz(e.target.value)} />
                  </label>
                  <label className="block space-y-1">
                    <span className="text-xs text-muted-foreground">Formula hint</span>
                    <Input value={conFormula} onChange={(e) => setConFormula(e.target.value)} />
                  </label>
                  <Field label="Expected anchor adduct" value={conAdduct} onChange={setConAdduct} />
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="m/z tol. (Da)" value={conMzTol} onChange={setConMzTol} />
                    <Field label="ppm tolerance" value={conPpmTol} onChange={setConPpmTol} />
                    <Field label="Family RT tol. (min)" value={conFamRt} onChange={setConFamRt} />
                    <Field label="Min consensus score to promote" value={conMinPromote} onChange={setConMinPromote} />
                  </div>
                </CollapsibleContent>
              </Collapsible>
              <Button type="submit" disabled={consensusBusy}>
                {consensusBusy ? "Running…" : "Run feature-family consensus"}
              </Button>
            </form>
          )}

          {current.key === "dereplication" && (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Calls <code className="text-xs">/ms/lcms/dereplication/upload</code> when your backend exposes it. If the
                route is absent, you will see a clear error—no identity or library claims are made here.
              </p>
              <form onSubmit={runDereplication} className="space-y-4">
                <div className="space-y-2">
                  <Label>Library / feature file</Label>
                  <Input ref={derepRef} type="file" />
                </div>
                <Button type="submit" disabled={dereplicationBusy}>
                  {dereplicationBusy ? "Running…" : "Run library dereplication"}
                </Button>
              </form>
            </div>
          )}

          {current.key === "bridge" && (
            <form onSubmit={runBridge} className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Sends shared <strong>Candidate structures</strong> with the last consensus result. Complete consensus
                first.
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block space-y-1">
                  <span className="text-xs text-muted-foreground">Adduct</span>
                  <Input value={brAdduct} onChange={(e) => setBrAdduct(e.target.value)} />
                </label>
                <label className="block space-y-1">
                  <span className="text-xs text-muted-foreground">Selected family ID (optional)</span>
                  <Input value={brFamilyId} onChange={(e) => setBrFamilyId(e.target.value)} placeholder="anchor family" />
                </label>
                <Field label="m/z tol. (Da)" value={brMzTol} onChange={setBrMzTol} />
                <Field label="ppm tolerance" value={brPpmTol} onChange={setBrPpmTol} />
                <Field label="Min family consensus score" value={brMinFam} onChange={setBrMinFam} />
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="br-req"
                  checked={brRequirePromoted}
                  onCheckedChange={(v) => setBrRequirePromoted(v === true)}
                />
                <Label htmlFor="br-req">Require promoted family</Label>
              </div>
              <Collapsible className="rounded-md border">
                <CollapsibleTrigger className="flex w-full px-4 py-3 text-left text-sm font-medium hover:bg-muted/50">
                  Advanced (payload preview)
                </CollapsibleTrigger>
                <CollapsibleContent className="border-t px-4 py-3 text-xs text-muted-foreground">
                  Candidates are parsed from the shared session block (pipe-separated lines). The full consensus JSON is
                  attached as <code className="font-mono">lcms_consensus_result</code>.
                </CollapsibleContent>
              </Collapsible>
              <Button type="submit" disabled={bridgeBusy}>
                {bridgeBusy ? "Running…" : "Run LC-MS consensus bridge"}
              </Button>
            </form>
          )}

          {activeBusy && (
            <p className="text-sm text-muted-foreground">Calling backend via <code className="text-xs">/api/backend</code>…</p>
          )}

          {!activeBusy && activeResult != null ? (
            <div className="space-y-4">
              {STEP_UNIFIED_META[current.key] && (
                <div className="flex flex-wrap gap-2">
                  <SpectraCheckUseUnifiedEvidenceButton
                    response={activeResult}
                    meta={{
                      layer: STEP_UNIFIED_META[current.key]!.layer,
                      sourceTab: "MS Evidence",
                      title: STEP_UNIFIED_META[current.key]!.title,
                      endpoint: STEP_UNIFIED_META[current.key]!.endpoint,
                      sampleId: sampleId.trim() || undefined,
                    }}
                  />
                </div>
              )}
              <LcmsWorkflowMetrics stepKey={current.key} data={activeResult} />
              {renderWarnings(activeResult)}
              <DeveloperJsonPanel data={activeResult} />
            </div>
          ) : !activeBusy ? (
            <p className="text-sm text-muted-foreground">Run this step to see metrics and developer JSON.</p>
          ) : null}
        </div>
      </ModuleCard>
    </div>
  )
}

function Field({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (s: string) => void
}) {
  return (
    <label className="block space-y-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <Input value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  )
}
