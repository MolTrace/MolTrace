"use client"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function num(v: unknown): string {
  return typeof v === "number" && Number.isFinite(v) ? String(v) : "—"
}

export function LcmsWorkflowMetrics({ stepKey, data }: { stepKey: string; data: unknown }) {
  if (!isRecord(data)) return null

  if (stepKey === "import") {
    return (
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Total scans" value={num(data.scan_count)} />
        <Metric label="MS1 scans" value={num(data.ms1_scan_count)} />
        <Metric label="MS2 scans" value={num(data.ms2_scan_count)} />
        <Metric label="Extracted MS1 peaks" value={num(data.extracted_ms1_peak_count)} />
        <Metric label="Label" value={typeof data.label === "string" ? data.label : "—"} wide />
      </div>
    )
  }

  if (stepKey === "detect") {
    const features = Array.isArray(data.features) ? data.features : []
    let puritySum = 0
    let purityN = 0
    const purityLabels: Record<string, number> = {}
    for (const f of features) {
      if (!isRecord(f)) continue
      const p = f.purity
      if (isRecord(p)) {
        const pct = p.purity_percent
        if (typeof pct === "number") {
          puritySum += pct
          purityN += 1
        }
        const pl = p.label
        if (typeof pl === "string") purityLabels[pl] = (purityLabels[pl] ?? 0) + 1
      }
    }
    const avgPurity = purityN > 0 ? (puritySum / purityN).toFixed(1) : "—"

    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Feature count" value={num(data.feature_count)} />
          <Metric label="Clean features" value={num(data.clean_feature_count)} />
          <Metric label="Co-eluting" value={num(data.coeluting_feature_count)} />
          <Metric label="Weak / sparse" value={num(data.weak_feature_count)} />
          <Metric label="Avg peak purity %" value={avgPurity} />
          <Metric label="Features assessed" value={String(purityN)} />
        </div>
        {Object.keys(purityLabels).length > 0 && (
          <div className="flex flex-wrap gap-2">
            {Object.entries(purityLabels).map(([k, v]) => (
              <Badge key={k} variant="secondary">
                {k.replaceAll("_", " ")}: {v}
              </Badge>
            ))}
          </div>
        )}
      </div>
    )
  }

  if (stepKey === "group") {
    const groups = Array.isArray(data.groups) ? data.groups : []
    let blankLike = 0
    for (const g of groups) {
      if (isRecord(g) && g.label === "blank_like_feature") blankLike += 1
    }
    const summaries = Array.isArray(data.alignment_summaries) ? data.alignment_summaries : []

    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Groups" value={num(data.group_count)} />
          <Metric label="Sample-enriched groups" value={num(data.sample_enriched_group_count)} />
          <Metric label="Background groups" value={num(data.background_group_count)} />
          <Metric label="Blank-like features" value={String(blankLike)} />
          <Metric label="Runs" value={num(data.run_count)} />
          <Metric label="Workflow label" value={typeof data.label === "string" ? data.label : "—"} wide />
        </div>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">RT alignment status</CardTitle>
            <CardDescription>Per-run alignment summary from the backend.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {summaries.length === 0 ? (
              <p className="text-muted-foreground">No alignment summaries returned.</p>
            ) : (
              <ul className="space-y-2">
                {summaries.map((s, i) => {
                  if (!isRecord(s)) return null
                  return (
                    <li key={`${String(s.run_id)}-${i}`} className="rounded-md border px-3 py-2">
                      <span className="font-medium">{String(s.run_id ?? "run")}</span>
                      <span className="text-muted-foreground"> · role </span>
                      {String(s.role ?? "—")}
                      <span className="text-muted-foreground"> · ΔRT </span>
                      {num(s.rt_shift_min)} min
                      <span className="text-muted-foreground"> · anchors </span>
                      {num(s.anchor_match_count)}
                      <span className="text-muted-foreground"> · aligned </span>
                      {num(s.aligned_feature_count)} / {num(s.raw_feature_count)}
                    </li>
                  )
                })}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    )
  }

  if (stepKey === "consensus") {
    const families = Array.isArray(data.families) ? data.families : []
    const promotedIds = families
      .filter((f) => isRecord(f) && f.promoted_for_candidate_scoring === true)
      .map((f) => (isRecord(f) ? String(f.family_id ?? "") : ""))
      .filter(Boolean)

    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Families" value={num(data.family_count)} />
          <Metric label="Promoted families" value={num(data.promoted_family_count)} />
          <Metric label="Conflicting families" value={num(data.conflicting_family_count)} />
          <Metric label="Input groups" value={num(data.input_group_count)} />
          <Metric label="Result label" value={typeof data.label === "string" ? data.label : "—"} wide />
        </div>
        {promotedIds.length > 0 && (
          <div>
            <p className="mb-2 text-sm font-medium">Promoted family IDs</p>
            <div className="flex flex-wrap gap-2">
              {promotedIds.slice(0, 24).map((id) => (
                <Badge key={id} variant="outline">
                  {id}
                </Badge>
              ))}
              {promotedIds.length > 24 && (
                <Badge variant="secondary">+{promotedIds.length - 24} more</Badge>
              )}
            </div>
          </div>
        )}
      </div>
    )
  }

  if (stepKey === "bridge") {
    const matches = Array.isArray(data.matches) ? data.matches : []

    return (
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Candidates scored" value={num(data.candidate_count)} />
          <Metric label="Consensus families" value={num(data.family_count)} />
          <Metric label="Eligible families" value={num(data.eligible_family_count)} />
          <Metric label="Promoted families (layer)" value={num(data.promoted_family_count)} />
        </div>
        <Card className="min-w-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">LC-MS candidate seed hits</CardTitle>
            <CardDescription>Ranked matches against LC-MS consensus families (requires review).</CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            {matches.length === 0 ? (
              <p className="text-sm text-muted-foreground">No seed hits returned.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Rank</TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead>Score</TableHead>
                    <TableHead>Label</TableHead>
                    <TableHead>Family</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {matches.slice(0, 25).map((row, i) => {
                    if (!isRecord(row)) return null
                    return (
                      <TableRow key={`${String(row.smiles)}-${i}`}>
                        <TableCell>{num(row.rank)}</TableCell>
                        <TableCell className="font-medium">{String(row.name ?? "—")}</TableCell>
                        <TableCell>{typeof row.score === "number" ? row.score.toFixed(3) : "—"}</TableCell>
                        <TableCell className="max-w-[220px] truncate text-xs">{String(row.label ?? "—")}</TableCell>
                        <TableCell className="max-w-[140px] truncate text-xs">{String(row.best_family_id ?? "—")}</TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <p className="text-sm text-muted-foreground">
      Run this step to populate LC-MS metrics. Developer JSON below holds the full payload.
    </p>
  )
}

function Metric({ label, value, wide }: { label: string; value: string; wide?: boolean }) {
  return (
    <div className={`rounded-md border bg-card px-3 py-2 ${wide ? "sm:col-span-2 lg:col-span-4" : ""}`}>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="font-mono text-sm font-semibold">{value}</div>
    </div>
  )
}
