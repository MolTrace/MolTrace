"use client"

import { useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { trackOutboundSyncJobCreated } from "@/src/lib/analytics/analytics-client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  AlertTriangle,
  Beaker,
  CheckCircle2,
  FlaskConical,
  Grid3X3,
  LineChart,
  Lock,
  Shield,
  Sparkles,
  Target,
} from "lucide-react"

/** Static fictional numbers for layout only — not computed by MolTrace or any backend. */
const DEMO_CONDITION_ROWS = [
  { run: "R-01", solvent: "THF", temperature_C: 65, catalyst: "Pd(PPh₃)₄", base: "K₂CO₃", equiv: 2.0 },
  { run: "R-02", solvent: "DMF", temperature_C: 85, catalyst: "Pd(OAc)₂", base: "Et₃N", equiv: 2.5 },
  { run: "R-03", solvent: "Dioxane", temperature_C: 75, catalyst: "Pd(PPh₃)₄", base: "Cs₂CO₃", equiv: 2.0 },
  { run: "R-04", solvent: "THF", temperature_C: 90, catalyst: "Pd/C", base: "NaOH", equiv: 3.0 },
] as const

/** Demo outcomes — illustrative only. */
const DEMO_OUTCOME_ROWS = [
  { run: "R-01", yield_pct: 72, selectivity_pct: 91, major_impurity_area_pct: 2.1, notes: "Baseline" },
  { run: "R-02", yield_pct: 68, selectivity_pct: 88, major_impurity_area_pct: 3.4, notes: "Higher T" },
  { run: "R-03", yield_pct: 81, selectivity_pct: 93, major_impurity_area_pct: 1.6, notes: "Cs base" },
  { run: "R-04", yield_pct: 59, selectivity_pct: 86, major_impurity_area_pct: 4.8, notes: "Heterogeneous cat." },
] as const

const DEMO_PREDICTION = {
  label: "Illustrative model output",
  predicted_yield_pct: 76,
  predicted_selectivity_pct: 90,
  disclaimer:
    "Figures below are placeholders for a future surrogate model. No inference has been run in this build.",
}

const DEMO_UNCERTAINTY = {
  yield_ci_pct: [68, 83] as const,
  selectivity_ci_pct: [84, 94] as const,
  epistemic_note:
    "Uncertainty bands are demo annotations only; connect calibration data when the prediction API is available.",
}

const DEMO_NEXT_EXPERIMENT = {
  solvent: "THF",
  temperature_C: 78,
  catalyst: "Pd(PPh₃)₄",
  base: "Cs₂CO₃",
  rationale:
    "Placeholder suggestion — replace with acquisition policy once experiments are logged and scored server-side.",
}

export function ReactionStudioWorkspace() {
  const [importConnector, setImportConnector] = useState("")
  const [importExternalRecord, setImportExternalRecord] = useState("")
  const [importReactionProjectId, setImportReactionProjectId] = useState("")
  const [importMappingTemplate, setImportMappingTemplate] = useState("")
  const [importReviewRequired, setImportReviewRequired] = useState(true)
  const [importBusy, setImportBusy] = useState(false)
  const [importError, setImportError] = useState("")
  const [importResult, setImportResult] = useState<Record<string, unknown> | null>(null)

  const [exportConnector, setExportConnector] = useState("")
  const [exportReactionProjectId, setExportReactionProjectId] = useState("")
  const [exportApprovedItems, setExportApprovedItems] = useState("")
  const [exportTargetExternalRecord, setExportTargetExternalRecord] = useState("")
  const [exportBusy, setExportBusy] = useState(false)
  const [exportError, setExportError] = useState("")
  const [exportResult, setExportResult] = useState<Record<string, unknown> | null>(null)

  function readString(result: Record<string, unknown> | null, keys: string[]): string {
    if (!result) return ""
    for (const key of keys) {
      const value = result[key]
      if (typeof value === "string" && value.trim()) return value.trim()
      if (typeof value === "number" && Number.isFinite(value)) return String(value)
    }
    return ""
  }

  function readNumber(result: Record<string, unknown> | null, keys: string[]): number | null {
    if (!result) return null
    for (const key of keys) {
      const value = result[key]
      if (typeof value === "number" && Number.isFinite(value)) return Math.floor(value)
      if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) {
        return Math.floor(Number(value))
      }
    }
    return null
  }

  function readWarnings(result: Record<string, unknown> | null): string[] {
    if (!result) return []
    const warnings = result.warnings
    if (Array.isArray(warnings)) {
      return warnings
        .map((item) => (typeof item === "string" ? item.trim() : ""))
        .filter((item) => item.length > 0)
    }
    if (typeof warnings === "string" && warnings.trim()) return [warnings.trim()]
    return []
  }

  async function importExperimentTable() {
    setImportBusy(true)
    setImportError("")
    try {
      const payload = await apiFetch<unknown>("/integrations/reactions/import-experiment-table", {
        method: "POST",
        body: {
          connector: importConnector.trim(),
          external_record: importExternalRecord.trim(),
          reaction_project_id: importReactionProjectId.trim(),
          mapping_template: importMappingTemplate.trim(),
          review_required: importReviewRequired,
        },
      })
      if (payload && typeof payload === "object" && !Array.isArray(payload)) {
        setImportResult(payload as Record<string, unknown>)
      } else {
        setImportResult({ result: payload })
      }
    } catch (error) {
      setImportError(error instanceof Error ? error.message : "Could not import experiment table.")
      setImportResult(null)
    } finally {
      setImportBusy(false)
    }
  }

  async function exportApprovedExperiments() {
    if (!exportApprovedItems.trim()) {
      setExportError("approved recommendations / experiments is required.")
      return
    }
    setExportBusy(true)
    setExportError("")
    try {
      const payloadBody: Record<string, unknown> = {
        connector: exportConnector.trim(),
        reaction_project_id: exportReactionProjectId.trim(),
        approved_recommendations_experiments: exportApprovedItems.trim(),
      }
      if (exportTargetExternalRecord.trim()) {
        payloadBody.target_external_record = exportTargetExternalRecord.trim()
      }
      const payload = await apiFetch<unknown>("/integrations/reactions/export-approved-experiments", {
        method: "POST",
        body: payloadBody,
      })
      const rec =
        payload && typeof payload === "object" && !Array.isArray(payload) ? (payload as Record<string, unknown>) : null
      const warningCount = Array.isArray(rec?.warnings)
        ? rec!.warnings.filter((item) => typeof item === "string" && item.trim()).length
        : 0
      trackOutboundSyncJobCreated({
        connector_type: exportConnector.trim(),
        target_program: "reaction_optimization",
        status: readString(rec, ["status", "job_status", "sync_status"]) || "created",
        warning_count: warningCount,
        failure_count:
          readString(rec, ["status", "job_status"]).toLowerCase().includes("failed") ||
          readString(rec, ["status", "job_status"]).toLowerCase().includes("error")
            ? 1
            : 0,
      })
      if (payload && typeof payload === "object" && !Array.isArray(payload)) {
        setExportResult(payload as Record<string, unknown>)
      } else {
        setExportResult({ result: payload })
      }
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "Could not export approved experiments.")
      setExportResult(null)
    } finally {
      setExportBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-8 pb-12">
      <header className="space-y-3 border-b pb-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="font-mono text-xs">
                Reaction Studio (program-level)
              </Badge>
              <Badge variant="secondary" className="gap-1 border-dashed border-warning/60 bg-warning/10 text-warning-foreground">
                <AlertTriangle className="h-3 w-3" />
                Demo data — not live analysis
              </Badge>
            </div>
            <h1 className="text-2xl font-semibold tracking-tight">Optimization workspace</h1>
            <p className="max-w-3xl text-muted-foreground">
              Shell UI for reaction schemes, condition matrices, outcomes, and decision-support cards. Backend wiring is
              intentionally omitted until endpoints are available.
            </p>
          </div>
          <Button variant="outline" size="sm" disabled className="gap-2">
            <Lock className="h-4 w-4" />
            Sync experiments (disabled)
          </Button>
        </div>
      </header>

      {/* Reaction scheme */}
      <section aria-labelledby="scheme-heading">
        <Card className="overflow-hidden">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <FlaskConical className="h-5 w-5 text-muted-foreground" aria-hidden />
              <CardTitle id="scheme-heading" className="text-lg">
                Reaction scheme
              </CardTitle>
            </div>
            <CardDescription>
              Structure drawing / SMARTS canvas placeholder — attach structure editor or ELN link when integrated.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="scientific-grid-subtle flex min-h-[200px] flex-col items-center justify-center rounded-lg border border-dashed bg-muted/30 px-6 py-12 text-center">
              <Beaker className="mb-3 h-10 w-10 text-muted-foreground/70" aria-hidden />
              <p className="text-sm font-medium text-foreground">Scheme preview area</p>
              <p className="mt-2 max-w-md text-xs text-muted-foreground">
                Demo layout only. Import molfile / CXSMILES or render from route params when chemistry services exist.
              </p>
            </div>
          </CardContent>
        </Card>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Condition matrix */}
        <section aria-labelledby="conditions-heading">
          <Card className="h-full">
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <Grid3X3 className="h-5 w-5 text-muted-foreground" aria-hidden />
                <CardTitle id="conditions-heading" className="text-lg">
                  Condition matrix
                </CardTitle>
              </div>
              <CardDescription>Factor settings per experimental run (demo rows).</CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[72px]">Run</TableHead>
                    <TableHead>Solvent</TableHead>
                    <TableHead className="text-right">T (°C)</TableHead>
                    <TableHead>Catalyst</TableHead>
                    <TableHead>Base</TableHead>
                    <TableHead className="text-right">Equiv.</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {DEMO_CONDITION_ROWS.map((row) => (
                    <TableRow key={row.run}>
                      <TableCell className="font-mono text-xs">{row.run}</TableCell>
                      <TableCell>{row.solvent}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{row.temperature_C}</TableCell>
                      <TableCell className="max-w-[140px] truncate text-sm">{row.catalyst}</TableCell>
                      <TableCell>{row.base}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{row.equiv.toFixed(1)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </section>

        {/* Yield / selectivity / impurity */}
        <section aria-labelledby="outcomes-heading">
          <Card className="h-full">
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <Target className="h-5 w-5 text-muted-foreground" aria-hidden />
                <CardTitle id="outcomes-heading" className="text-lg">
                  Yield, selectivity &amp; impurities
                </CardTitle>
              </div>
              <CardDescription>Measured outcomes table — values are fictional for UI staging.</CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Run</TableHead>
                    <TableHead className="text-right">Yield (%)</TableHead>
                    <TableHead className="text-right">Sel. (%)</TableHead>
                    <TableHead className="text-right">Major imp. (% area)</TableHead>
                    <TableHead className="hidden sm:table-cell">Notes</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {DEMO_OUTCOME_ROWS.map((row) => (
                    <TableRow key={row.run}>
                      <TableCell className="font-mono text-xs">{row.run}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{row.yield_pct}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{row.selectivity_pct}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{row.major_impurity_area_pct}</TableCell>
                      <TableCell className="hidden max-w-[180px] truncate text-muted-foreground sm:table-cell">
                        {row.notes}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </section>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="connector-import-heading">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle id="connector-import-heading" className="text-lg">
                ELN / LIMS Experiment Import
              </CardTitle>
              <CardDescription>
                POST <code className="text-xs">/integrations/reactions/import-experiment-table</code>
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="rxn-import-connector">connector</Label>
                  <Input id="rxn-import-connector" value={importConnector} onChange={(e) => setImportConnector(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="rxn-import-external-record">external record</Label>
                  <Input
                    id="rxn-import-external-record"
                    value={importExternalRecord}
                    onChange={(e) => setImportExternalRecord(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="rxn-import-project-id">reaction project ID</Label>
                  <Input
                    id="rxn-import-project-id"
                    value={importReactionProjectId}
                    onChange={(e) => setImportReactionProjectId(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="rxn-import-mapping-template">mapping template</Label>
                  <Input
                    id="rxn-import-mapping-template"
                    value={importMappingTemplate}
                    onChange={(e) => setImportMappingTemplate(e.target.value)}
                  />
                </div>
                <div className="md:col-span-2 flex items-center gap-3 rounded-md border p-3">
                  <Checkbox
                    id="rxn-import-review-required"
                    checked={importReviewRequired}
                    onCheckedChange={(checked) => setImportReviewRequired(checked === true)}
                  />
                  <Label htmlFor="rxn-import-review-required">review required</Label>
                </div>
              </div>
              {importError ? <p className="text-xs text-destructive">{importError}</p> : null}
              <Button type="button" onClick={() => void importExperimentTable()} disabled={importBusy}>
                {importBusy ? "Importing…" : "Import experiments"}
              </Button>
              {importResult ? (
                <div className="space-y-2 rounded-md border p-3 text-sm">
                  <p>
                    <span className="text-muted-foreground">imported experiment count:</span>{" "}
                    {readNumber(importResult, ["imported_experiment_count", "imported_count"]) ?? "—"}
                  </p>
                  <p>
                    <span className="text-muted-foreground">skipped count:</span>{" "}
                    {readNumber(importResult, ["skipped_count"]) ?? "—"}
                  </p>
                  <p>
                    <span className="text-muted-foreground">records requiring review:</span>{" "}
                    {readNumber(importResult, ["records_requiring_review", "requiring_review_count"]) ?? "—"}
                  </p>
                  <p>
                    <span className="text-muted-foreground">warnings:</span> {readWarnings(importResult).join("; ") || "—"}
                  </p>
                  <details className="rounded-md border p-2">
                    <summary className="cursor-pointer text-xs font-medium">Developer JSON</summary>
                    <pre className="mt-2 overflow-x-auto text-[10px]">{JSON.stringify(importResult, null, 2)}</pre>
                  </details>
                </div>
              ) : null}
            </CardContent>
          </Card>
        </section>

        <section aria-labelledby="connector-export-heading">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle id="connector-export-heading" className="text-lg">
                Export approved experiments
              </CardTitle>
              <CardDescription>
                POST <code className="text-xs">/integrations/reactions/export-approved-experiments</code>
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="rxn-export-connector">connector</Label>
                  <Input id="rxn-export-connector" value={exportConnector} onChange={(e) => setExportConnector(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="rxn-export-project-id">reaction project ID</Label>
                  <Input
                    id="rxn-export-project-id"
                    value={exportReactionProjectId}
                    onChange={(e) => setExportReactionProjectId(e.target.value)}
                  />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="rxn-export-approved-items">approved recommendations / experiments</Label>
                  <Input
                    id="rxn-export-approved-items"
                    value={exportApprovedItems}
                    onChange={(e) => setExportApprovedItems(e.target.value)}
                    placeholder="ids or payload from approved recommendations / experiments"
                  />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="rxn-export-target-external-record">target external record optional</Label>
                  <Input
                    id="rxn-export-target-external-record"
                    value={exportTargetExternalRecord}
                    onChange={(e) => setExportTargetExternalRecord(e.target.value)}
                  />
                </div>
              </div>
              {exportError ? <p className="text-xs text-destructive">{exportError}</p> : null}
              <Button type="button" onClick={() => void exportApprovedExperiments()} disabled={exportBusy}>
                {exportBusy ? "Exporting…" : "Export approved experiments"}
              </Button>
              {exportResult ? (
                <div className="space-y-2 rounded-md border p-3 text-sm">
                  <p>
                    <span className="text-muted-foreground">status:</span>{" "}
                    {readString(exportResult, ["status", "export_status"]) || "—"}
                  </p>
                  <p>
                    <span className="text-muted-foreground">warnings:</span>{" "}
                    {readWarnings(exportResult).join("; ") || "—"}
                  </p>
                  <details className="rounded-md border p-2">
                    <summary className="cursor-pointer text-xs font-medium">Developer JSON</summary>
                    <pre className="mt-2 overflow-x-auto text-[10px]">{JSON.stringify(exportResult, null, 2)}</pre>
                  </details>
                </div>
              ) : null}
            </CardContent>
          </Card>
        </section>
      </div>

      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
        {/* Model prediction */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-muted-foreground" aria-hidden />
              <CardTitle className="text-base">Model prediction</CardTitle>
            </div>
            <CardDescription>{DEMO_PREDICTION.disclaimer}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{DEMO_PREDICTION.label}</p>
            <div className="grid grid-cols-2 gap-4">
              <div className="rounded-md border bg-card px-3 py-2">
                <p className="text-xs text-muted-foreground">Predicted yield</p>
                <p className="font-mono text-2xl font-semibold tabular-nums">{DEMO_PREDICTION.predicted_yield_pct}%</p>
              </div>
              <div className="rounded-md border bg-card px-3 py-2">
                <p className="text-xs text-muted-foreground">Predicted selectivity</p>
                <p className="font-mono text-2xl font-semibold tabular-nums">
                  {DEMO_PREDICTION.predicted_selectivity_pct}%
                </p>
              </div>
            </div>
            <Button variant="secondary" size="sm" className="w-full" disabled>
              Run predictor (no backend)
            </Button>
          </CardContent>
        </Card>

        {/* Uncertainty */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <LineChart className="h-5 w-5 text-muted-foreground" aria-hidden />
              <CardTitle className="text-base">Uncertainty</CardTitle>
            </div>
            <CardDescription>{DEMO_UNCERTAINTY.epistemic_note}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="text-xs text-muted-foreground">Yield (demo 95% interval)</p>
              <p className="font-mono text-lg tabular-nums">
                {DEMO_UNCERTAINTY.yield_ci_pct[0]}% — {DEMO_UNCERTAINTY.yield_ci_pct[1]}%
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Selectivity (demo interval)</p>
              <p className="font-mono text-lg tabular-nums">
                {DEMO_UNCERTAINTY.selectivity_ci_pct[0]}% — {DEMO_UNCERTAINTY.selectivity_ci_pct[1]}%
              </p>
            </div>
            <div className="rounded-md border border-dashed bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
              Calibration curves and posterior stacks will render here after model API integration.
            </div>
          </CardContent>
        </Card>

        {/* Next-best experiment */}
        <Card className="md:col-span-2 xl:col-span-1">
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Target className="h-5 w-5 text-muted-foreground" aria-hidden />
              <CardTitle className="text-base">Next-best experiment</CardTitle>
            </div>
            <CardDescription>{DEMO_NEXT_EXPERIMENT.rationale}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <dt className="text-muted-foreground">Solvent</dt>
              <dd className="font-medium">{DEMO_NEXT_EXPERIMENT.solvent}</dd>
              <dt className="text-muted-foreground">T</dt>
              <dd className="font-mono tabular-nums">{DEMO_NEXT_EXPERIMENT.temperature_C} °C</dd>
              <dt className="text-muted-foreground">Catalyst</dt>
              <dd className="font-medium">{DEMO_NEXT_EXPERIMENT.catalyst}</dd>
              <dt className="text-muted-foreground">Base</dt>
              <dd className="font-medium">{DEMO_NEXT_EXPERIMENT.base}</dd>
            </dl>
            <Separator />
            <Button variant="outline" size="sm" className="w-full" disabled>
              Queue in ELN (requires backend)
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Response surface placeholder */}
      <section aria-labelledby="surface-heading">
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <LineChart className="h-5 w-5 text-muted-foreground" aria-hidden />
              <CardTitle id="surface-heading" className="text-lg">
                Response surface
              </CardTitle>
            </div>
            <CardDescription>
              Contour / surface visualization placeholder — wire to DOE engine or plotting library when data pipelines
              exist.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="scientific-grid relative flex min-h-[280px] items-center justify-center overflow-hidden rounded-lg border bg-muted/20">
              <div className="absolute inset-0 bg-gradient-to-br from-chart-2/10 via-transparent to-chart-4/10" aria-hidden />
              <div className="relative z-[1] max-w-lg px-6 text-center">
                <p className="text-sm font-medium">Response surface preview</p>
                <p className="mt-2 text-xs text-muted-foreground">
                  Demo gradient only. No fitted surface or optimizer output is shown.
                </p>
                <div className="mt-6 flex justify-center gap-8 text-xs text-muted-foreground">
                  <span className="font-mono">x₁ · temperature</span>
                  <span className="font-mono">x₂ · loading</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* Human approval gate */}
      <section aria-labelledby="approval-heading">
        <Card className="border-primary/25 bg-primary/[0.03]">
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-start gap-3">
              <Shield className="mt-0.5 h-6 w-6 shrink-0 text-primary" aria-hidden />
              <div className="space-y-1">
                <CardTitle id="approval-heading" className="text-lg">
                  Human approval gate
                </CardTitle>
                <CardDescription>
                  Experimental decisions require qualified review. This gate will attach signatures and audit trails when
                  the workflow API is connected.
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-4 rounded-md border bg-background/80 px-4 py-3">
              <Checkbox id="demo-ack" disabled />
              <Label htmlFor="demo-ack" className="text-sm leading-snug text-muted-foreground">
                I acknowledge this screen shows demo data only and no experimental recommendation has been validated.
              </Label>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button disabled className="gap-2">
                <CheckCircle2 className="h-4 w-4" />
                Submit for approval (requires backend)
              </Button>
              <Button variant="outline" disabled className="gap-2">
                Request revision
              </Button>
            </div>
            <p className="flex items-start gap-2 text-xs text-muted-foreground">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
              Buttons stay disabled until approval endpoints and identity checks exist — avoids implying signed-off
              experiments from static UI.
            </p>
          </CardContent>
        </Card>
      </section>

      {/* Footer strip */}
      <Card className="border-dashed bg-muted/30">
        <CardContent className="flex flex-wrap items-center justify-between gap-3 py-4 text-xs text-muted-foreground">
          <span>MolTrace Reaction Studio (program-level) · shell build · no inference executed</span>
          <Badge variant="outline" className="font-normal">
            Progress: UI scaffold
          </Badge>
        </CardContent>
      </Card>
    </div>
  )
}
