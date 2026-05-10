"use client"

import Link from "next/link"
import { useCallback, useEffect, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { readRecordNumber, readRecordString } from "@/components/projects/project-workspace-utils"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Boxes } from "lucide-react"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { BackendStatusIndicator } from "@/components/app/backend-status-indicator"
import { ArrowLeft, Loader2, RefreshCw } from "lucide-react"

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

export function MlModelArtifactsList() {
  const [loading, setLoading] = useState(true)
  const [reload, setReload] = useState(0)
  const [rows, setRows] = useState<Record<string, unknown>[]>([])
  const [err, setErr] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setErr("")
    try {
      const data = await apiFetch<unknown>("/ml/model-artifacts?limit=500", { method: "GET" })
      setRows(Array.isArray(data) ? (data.filter(isRecord) as Record<string, unknown>[]) : [])
    } catch (e) {
      setErr(formatApiError(e, "Could not load model artifacts."))
      setRows([])
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load, reload])

  return (
    <div className="mx-auto max-w-[1400px] space-y-6 p-4 md:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="mb-1">
            <Button variant="ghost" size="sm" className="h-8 px-2" asChild>
              <Link href="/ml" className="inline-flex items-center gap-1 text-muted-foreground">
                <ArrowLeft className="h-4 w-4" aria-hidden />
                ML Model Factory
              </Link>
            </Button>
          </div>
          <h1 className="font-mono text-2xl font-bold tracking-tight">Model artifacts</h1>
          <p className="text-muted-foreground">
            Browse trained artifacts and open detail for evaluation links, model cards, and deployment context.
          </p>
        </div>
        <BackendStatusIndicator />
      </div>

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => setReload((x) => x + 1)}>
          {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden /> : <RefreshCw className="mr-2 h-4 w-4" aria-hidden />}
          Refresh
        </Button>
      </div>

      {err ? (
        <Alert variant="destructive">
          <AlertTitle>GET /ml/model-artifacts</AlertTitle>
          <AlertDescription>{err}</AlertDescription>
        </Alert>
      ) : null}

      <ModuleCard
        accent="teal"
        eyebrow="Artifacts"
        title="Artifacts"
        icon={Boxes}
        description="Model artifacts produced by completed training runs — name, task type, framework, and training dataset version."
      >
        <div className="table-scroll min-w-0">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : rows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No artifacts returned.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[72px]">id</TableHead>
                  <TableHead>model_name</TableHead>
                  <TableHead>model_version</TableHead>
                  <TableHead>task_key</TableHead>
                  <TableHead>model_family</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead className="w-[100px]" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row, idx) => {
                  const id = readRecordNumber(row, "id")
                  return (
                    <TableRow key={id != null ? `a-${id}` : `a-${idx}`}>
                      <TableCell className="font-mono text-xs">{id ?? "—"}</TableCell>
                      <TableCell className="text-sm">{readRecordString(row, "model_name") ?? "—"}</TableCell>
                      <TableCell className="font-mono text-xs">{readRecordString(row, "model_version") ?? "—"}</TableCell>
                      <TableCell className="font-mono text-xs">{readRecordString(row, "task_key") ?? "—"}</TableCell>
                      <TableCell className="font-mono text-xs">{readRecordString(row, "model_family") ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{readRecordString(row, "status") ?? "—"}</Badge>
                      </TableCell>
                      <TableCell>
                        {id != null ? (
                          <Button variant="outline" size="sm" asChild>
                            <Link href={`/ml/models/${id}`}>Open</Link>
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
    </div>
  )
}
