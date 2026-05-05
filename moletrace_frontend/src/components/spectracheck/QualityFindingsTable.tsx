"use client"

import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { QcFindingRow, QcFindingSeverity } from "@/src/lib/spectracheck/quality-control-assessment"
import { cn } from "@/lib/utils"

export type QualityFindingSeverity = QcFindingSeverity

export type QualityFindingRow = QcFindingRow

function severityClass(s: QualityFindingSeverity): string {
  switch (s) {
    case "error":
      return "border-transparent bg-destructive/90 text-destructive-foreground"
    case "warning":
      return "border border-amber-500/50 bg-amber-500/10 text-amber-900 dark:text-amber-100"
    case "info":
      return "border-transparent bg-secondary text-secondary-foreground"
    default:
      return "border-transparent bg-secondary text-secondary-foreground"
  }
}

export type QualityFindingsTableProps = {
  findings: QualityFindingRow[]
  emptyMessage?: string
}

export function QualityFindingsTable({
  findings,
  emptyMessage = "No findings recorded.",
}: QualityFindingsTableProps) {
  return (
    <div className="min-w-0 overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="text-xs">Severity</TableHead>
            <TableHead className="text-xs">Code</TableHead>
            <TableHead className="text-xs">Title</TableHead>
            <TableHead className="text-xs">Message</TableHead>
            <TableHead className="text-xs">Recommendation</TableHead>
            <TableHead className="text-xs">Layer</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {findings.length === 0 ? (
            <TableRow>
              <TableCell colSpan={6} className="text-sm text-muted-foreground">
                {emptyMessage}
              </TableCell>
            </TableRow>
          ) : (
            findings.map((row, i) => (
              <TableRow key={`${row.code}-${i}`}>
                <TableCell className="align-top">
                  <Badge variant="outline" className={cn("font-mono text-[10px]", severityClass(row.severity))}>
                    {row.severity}
                  </Badge>
                </TableCell>
                <TableCell className="max-w-[100px] align-top font-mono text-[10px] break-all">{row.code}</TableCell>
                <TableCell className="max-w-[140px] align-top text-sm">{row.title}</TableCell>
                <TableCell className="max-w-[220px] align-top text-xs text-muted-foreground">{row.message}</TableCell>
                <TableCell className="max-w-[200px] align-top text-xs">{row.recommendation}</TableCell>
                <TableCell className="max-w-[120px] align-top font-mono text-[10px]">{row.layer}</TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  )
}

/** Mock rows for Storybook-style wiring or tests. */
export const MOCK_QUALITY_FINDINGS: QualityFindingRow[] = [
  {
    severity: "warning",
    code: "HASH_MISMATCH",
    title: "Digest mismatch",
    message: "Artifact digest did not match the recorded value after transfer.",
    recommendation: "Re-upload the file or verify proxy configuration.",
    layer: "session_files",
  },
  {
    severity: "info",
    code: "LAYER_SPARSE",
    title: "Sparse MS layer",
    message: "MS/MS annotation layer has fewer peaks than typical for this workflow.",
    recommendation: "Confirm acquisition parameters before relying on fragmentation evidence.",
    layer: "msms_annotation",
  },
]
