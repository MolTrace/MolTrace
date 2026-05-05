"use client"

import Link from "next/link"
import { useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

type JsonRecord = Record<string, unknown>

type ModuleSummary = {
  title: "SpectraCheck" | "Regulatory Hub" | "Reaction Optimization"
  status: string
  openActionCount: number | null
  warnings: string[]
  nextRecommendedAction: string
  href: string
  buttonLabel: string
}

function isRecord(v: unknown): v is JsonRecord {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function asRecord(v: unknown): JsonRecord | null {
  return isRecord(v) ? v : null
}

function readStr(v: unknown): string {
  if (typeof v === "string" && v.trim()) return v.trim()
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return ""
}

function readNum(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return Math.floor(v)
  if (typeof v === "string" && v.trim() && Number.isFinite(Number(v))) return Math.floor(Number(v))
  return null
}

function readList(v: unknown): string[] {
  if (!Array.isArray(v)) return []
  return v.map(readStr).filter(Boolean)
}

function pickRecord(raw: unknown): JsonRecord | null {
  if (isRecord(raw)) return raw
  if (Array.isArray(raw)) {
    const first = raw.find(isRecord)
    return first ?? null
  }
  return null
}

function readFirstString(rec: JsonRecord | null, keys: string[]): string {
  if (!rec) return ""
  for (const key of keys) {
    const value = readStr(rec[key])
    if (value) return value
  }
  return ""
}

function readFirstNumber(rec: JsonRecord | null, keys: string[]): number | null {
  if (!rec) return null
  for (const key of keys) {
    const value = readNum(rec[key])
    if (value != null) return value
  }
  return null
}

function moduleWarnings(root: JsonRecord, summary: JsonRecord | null): string[] {
  const rootWarnings = [...readList(root.warnings), ...readList(root.warnings_json)]
  const summaryWarnings = summary ? [...readList(summary.warnings), ...readList(summary.warnings_json)] : []
  return Array.from(new Set([...rootWarnings, ...summaryWarnings]))
}

function buildModuleSummaries(root: JsonRecord): ModuleSummary[] {
  const spectracheckSummary = asRecord(root.spectracheck_summary_json) ?? asRecord(root.spectracheck_summary)
  const regulatorySummary = asRecord(root.regulatory_summary_json) ?? asRecord(root.regulatory_summary)
  const reactionSummary = asRecord(root.reaction_summary_json) ?? asRecord(root.reaction_summary)

  const globalNext =
    readFirstString(root, ["next_recommended_action", "next_action", "recommended_next_action"]) || "No recommendation."

  return [
    {
      title: "SpectraCheck",
      status:
        readFirstString(spectracheckSummary, ["status", "latest_evidence_status", "evidence_status"]) ||
        readFirstString(root, ["latest_spectracheck_evidence_status", "latestSpectraCheckEvidenceStatus"]) ||
        "Unknown",
      openActionCount:
        readFirstNumber(spectracheckSummary, ["open_action_items_count", "open_actions_count", "open_action_count"]) ??
        readFirstNumber(root, ["open_cross_module_action_items_count", "open_action_items_count"]),
      warnings: moduleWarnings(root, spectracheckSummary),
      nextRecommendedAction:
        readFirstString(spectracheckSummary, ["next_recommended_action", "next_action", "recommended_next_action"]) ||
        globalNext,
      href: "/spectracheck",
      buttonLabel: "Open SpectraCheck",
    },
    {
      title: "Regulatory Hub",
      status: readFirstString(regulatorySummary, ["status", "readiness_status", "overall_status"]) || "Unknown",
      openActionCount:
        readFirstNumber(regulatorySummary, [
          "linked_regulatory_action_items",
          "open_action_items_count",
          "open_regulatory_blockers",
          "open_blockers",
        ]) ??
        readFirstNumber(root, ["linked_regulatory_action_items", "open_regulatory_blockers"]),
      warnings: moduleWarnings(root, regulatorySummary),
      nextRecommendedAction:
        readFirstString(regulatorySummary, ["next_recommended_action", "next_action", "recommended_next_action"]) ||
        globalNext,
      href: "/regulatory",
      buttonLabel: "Open Regulatory Hub",
    },
    {
      title: "Reaction Optimization",
      status: readFirstString(reactionSummary, ["status", "optimization_status", "overall_status"]) || "Unknown",
      openActionCount:
        readFirstNumber(reactionSummary, [
          "open_action_items_count",
          "open_actions_count",
          "optimization_recommendations_affected_by_compliance",
        ]) ??
        readFirstNumber(root, [
          "optimization_recommendations_affected_by_compliance",
          "open_cross_module_action_items_count",
        ]),
      warnings: moduleWarnings(root, reactionSummary),
      nextRecommendedAction:
        readFirstString(reactionSummary, ["next_recommended_action", "next_action", "recommended_next_action"]) ||
        globalNext,
      href: "/reactions",
      buttonLabel: "Open Reaction Optimization",
    },
  ]
}

async function fetchMobileCommandCenter(): Promise<{ sourceEndpoint: string; modules: ModuleSummary[] } | null> {
  const endpoints = ["/mobile/command-center", "/cross-module/command-center"]
  for (const endpoint of endpoints) {
    try {
      const raw = await apiFetch<unknown>(endpoint, { method: "GET" })
      const root = pickRecord(raw)
      if (!root) continue
      return { sourceEndpoint: endpoint, modules: buildModuleSummaries(root) }
    } catch {
      // try fallback endpoint
    }
  }
  return null
}

export function MobileCommandCenter() {
  const [loading, setLoading] = useState(true)
  const [sourceEndpoint, setSourceEndpoint] = useState<string | null>(null)
  const [modules, setModules] = useState<ModuleSummary[]>([])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    void fetchMobileCommandCenter()
      .then((data) => {
        if (cancelled) return
        if (!data) {
          setModules([])
          setSourceEndpoint(null)
          return
        }
        setSourceEndpoint(data.sourceEndpoint)
        setModules(data.modules)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const orderedModules = useMemo(() => modules, [modules])

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Mobile Command Center</CardTitle>
        <CardDescription>
          <code className="text-xs">{`GET ${sourceEndpoint ?? "/mobile/command-center"}`}</code> with fallback to{" "}
          <code className="text-xs">GET /cross-module/command-center</code>.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {orderedModules.map((module, idx) => (
          <div key={module.title} className="rounded-md border bg-muted/20 p-3">
            <p className="text-xs font-medium uppercase text-muted-foreground">
              {idx + 1}. {module.title}
            </p>
            <div className="mt-2 space-y-1 text-xs text-muted-foreground">
              <p>
                <span className="font-medium text-foreground">status:</span> {module.status || "—"}
              </p>
              <p>
                <span className="font-medium text-foreground">open action count:</span>{" "}
                {module.openActionCount != null ? module.openActionCount : "—"}
              </p>
              <p>
                <span className="font-medium text-foreground">warnings:</span>{" "}
                {module.warnings.length > 0 ? module.warnings.slice(0, 3).join(" · ") : "—"}
              </p>
              <p>
                <span className="font-medium text-foreground">next recommended action:</span>{" "}
                {module.nextRecommendedAction || "—"}
              </p>
            </div>
            <div className="mt-3">
              <Button type="button" size="sm" asChild>
                <Link href={module.href}>{module.buttonLabel}</Link>
              </Button>
            </div>
          </div>
        ))}
        {loading ? <p className="text-xs text-muted-foreground">Loading mobile command center…</p> : null}
        {!loading && orderedModules.length === 0 ? (
          <p className="text-xs text-muted-foreground">Mobile command center summary unavailable.</p>
        ) : null}
      </CardContent>
    </Card>
  )
}
