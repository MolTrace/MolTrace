"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { EntityPicker } from "@/components/ui/entity-picker"
import { loadDossiers } from "@/lib/ui/entity-options"
import { JsonObjectField } from "@/components/ui/json-object-field"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { DeveloperJsonPanel } from "@/components/spectracheck/spectracheck-result-panels"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { ChevronDown, Loader2, Scale } from "lucide-react"

const CONSTRAINT_TYPES = [
  "impurity_limit",
  "residual_solvent_limit",
  "nitrosamine_risk_avoidance",
  "qnmr_validation_requirement",
  "ai_governance_requirement",
  "jurisdictional_requirement",
  "other",
] as const

type OptimizationCompliancePayload = {
  regulatory_constraints: Record<string, unknown>[]
  compliance_objective: Record<string, unknown> | null
}

type Props = {
  reactionProjectId: number
  onPayloadChange?: (payload: OptimizationCompliancePayload | null) => void
  onUseInOptimizationChange?: (enabled: boolean) => void
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return Boolean(v) && typeof v === "object" && !Array.isArray(v)
}

function asRows(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data.filter(isRecord) as Record<string, unknown>[]
  if (!isRecord(data)) return []
  const items = data.items
  if (Array.isArray(items)) return items.filter(isRecord) as Record<string, unknown>[]
  return []
}

function readStr(o: Record<string, unknown>, ...keys: string[]): string {
  for (const k of keys) {
    const v = o[k]
    if (typeof v === "string" && v.trim()) return v.trim()
    if (typeof v === "number" && Number.isFinite(v)) return String(v)
  }
  return ""
}

function readString(v: unknown): string {
  if (typeof v === "string" && v.trim()) return v.trim()
  if (typeof v === "number" && Number.isFinite(v)) return String(v)
  return ""
}

function parseNum(v: string): number | null {
  const t = v.trim()
  if (!t) return null
  const n = Number(t)
  return Number.isFinite(n) ? n : null
}

function parseJsonOrText(v: string): unknown {
  const t = v.trim()
  if (!t) return {}
  try {
    return JSON.parse(t) as unknown
  } catch {
    return { text: t }
  }
}

// Map a JsonObjectField's emitted object back to the string state the submit
// already parses via parseJsonOrText. Empty object → "" → parseJsonOrText → {},
// identical to leaving the old textarea blank; the wire payload is unchanged.
function jsonStringFromObject(obj: Record<string, unknown>): string {
  return Object.keys(obj).length > 0 ? JSON.stringify(obj) : ""
}

export function ReactionRegulatoryConstraintsPanel({
  reactionProjectId,
  onPayloadChange,
  onUseInOptimizationChange,
}: Props) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState("")
  const [constraints, setConstraints] = useState<Record<string, unknown>[]>([])
  const [complianceObjective, setComplianceObjective] = useState<Record<string, unknown> | null>(null)
  const [useInOptimization, setUseInOptimization] = useState(true)

  const [constraintType, setConstraintType] = useState<string>(CONSTRAINT_TYPES[0])
  const [sourceDossierId, setSourceDossierId] = useState("")
  const [sourceActionItemId, setSourceActionItemId] = useState("")
  const [severity, setSeverity] = useState("warning")
  const [constraintStatus, setConstraintStatus] = useState("draft")
  const [constraintDetails, setConstraintDetails] = useState("")

  const [objectiveYieldSelectivity, setObjectiveYieldSelectivity] = useState("")
  const [impurityPenalty, setImpurityPenalty] = useState("")
  const [residualPenalty, setResidualPenalty] = useState("")
  const [nitrosaminePenalty, setNitrosaminePenalty] = useState("")
  const [objectiveHardConstraints, setObjectiveHardConstraints] = useState("")
  const [objectiveSoftConstraints, setObjectiveSoftConstraints] = useState("")
  const [objectiveReviewStatus, setObjectiveReviewStatus] = useState("draft")

  const load = useCallback(async () => {
    setLoading(true)
    setErr("")
    try {
      const [constraintsRaw, objectiveRaw] = await Promise.all([
        apiFetch<unknown>(`/reaction-projects/${reactionProjectId}/regulatory-constraints`, { method: "GET" }),
        apiFetch<unknown>(`/reaction-projects/${reactionProjectId}/compliance-objective`, { method: "GET" }).catch(() => null),
      ])
      const rows = asRows(constraintsRaw)
      setConstraints(rows)
      const objectiveRec = isRecord(objectiveRaw) ? objectiveRaw : null
      setComplianceObjective(objectiveRec)
      if (objectiveRec) {
        setObjectiveReviewStatus(readStr(objectiveRec, "status") || "draft")
      }
    } catch (e) {
      setErr(formatApiError(e, "Could not load regulatory constraints."))
      setConstraints([])
      setComplianceObjective(null)
    } finally {
      setLoading(false)
    }
  }, [reactionProjectId])

  useEffect(() => {
    void load()
  }, [load])

  const optimizationPayload = useMemo<OptimizationCompliancePayload | null>(() => {
    if (!constraints.length && !complianceObjective) return null
    return {
      regulatory_constraints: constraints,
      compliance_objective: complianceObjective,
    }
  }, [constraints, complianceObjective])

  useEffect(() => {
    onPayloadChange?.(optimizationPayload)
  }, [optimizationPayload, onPayloadChange])

  useEffect(() => {
    onUseInOptimizationChange?.(useInOptimization)
  }, [useInOptimization, onUseInOptimizationChange])

  async function createConstraint() {
    setSaving(true)
    setErr("")
    try {
      const body: Record<string, unknown> = {
        constraint_type: constraintType,
        severity,
        status: constraintStatus,
        constraint_json: parseJsonOrText(constraintDetails),
      }
      const dossierId = parseNum(sourceDossierId)
      if (dossierId != null) body.dossier_id = dossierId
      const actionId = parseNum(sourceActionItemId)
      if (actionId != null) body.source_action_item_ids_json = [actionId]
      await apiFetch(`/reaction-projects/${reactionProjectId}/regulatory-constraints`, {
        method: "POST",
        body,
      })
      await load()
    } catch (e) {
      setErr(formatApiError(e, "Create regulatory constraint failed."))
    } finally {
      setSaving(false)
    }
  }

  async function setConstraintReviewState(constraintId: number, status: string) {
    setSaving(true)
    setErr("")
    try {
      await apiFetch(`/reaction-regulatory-constraints/${constraintId}`, {
        method: "PATCH",
        body: { status },
      })
      await load()
    } catch (e) {
      setErr(formatApiError(e, "Update regulatory constraint failed."))
    } finally {
      setSaving(false)
    }
  }

  async function saveComplianceObjective() {
    setSaving(true)
    setErr("")
    try {
      const objective_json = {
        yield_selectivity_objective: objectiveYieldSelectivity.trim() || null,
        impurity_penalty: impurityPenalty.trim() || null,
        residual_solvent_penalty: residualPenalty.trim() || null,
        nitrosamine_risk_penalty: nitrosaminePenalty.trim() || null,
        review_status: objectiveReviewStatus,
      }
      await apiFetch(`/reaction-projects/${reactionProjectId}/compliance-objective`, {
        method: "POST",
        body: {
          objective_json,
          hard_constraints_json: parseJsonOrText(objectiveHardConstraints),
          soft_constraints_json: parseJsonOrText(objectiveSoftConstraints),
          status: objectiveReviewStatus,
        },
      })
      await load()
    } catch (e) {
      setErr(formatApiError(e, "Save compliance objective failed."))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      {err ? <p className="text-xs text-destructive">{err}</p> : null}

      <Card className="border-muted">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Regulatory Constraints</CardTitle>
          <CardDescription>
            Regulatory constraints applied to candidate conditions during optimization — solvent class limits, banned reagents, and jurisdiction-specific boundaries.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-2">
              <Label>constraint type</Label>
              <Select value={constraintType} onValueChange={setConstraintType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CONSTRAINT_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>source dossier</Label>
              <EntityPicker
                ariaLabel="Source dossier"
                value={sourceDossierId || null}
                onChange={(id) => setSourceDossierId(id == null ? "" : String(id))}
                load={loadDossiers}
                placeholder="Select a dossier"
                searchPlaceholder="Search dossiers…"
                allowClear
              />
            </div>
            <div className="space-y-2">
              <Label>source action item</Label>
              <Input value={sourceActionItemId} onChange={(e) => setSourceActionItemId(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>severity</Label>
              <Select value={severity} onValueChange={setSeverity}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="info">info</SelectItem>
                  <SelectItem value="warning">warning</SelectItem>
                  <SelectItem value="high">high</SelectItem>
                  <SelectItem value="critical">critical</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>review state</Label>
              <Select value={constraintStatus} onValueChange={setConstraintStatus}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="draft">draft</SelectItem>
                  <SelectItem value="active">active</SelectItem>
                  <SelectItem value="reviewed">reviewed</SelectItem>
                  <SelectItem value="archived">archived</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2 md:col-span-2">
              <JsonObjectField
                idPrefix="constraint-details"
                label="constraint details"
                onChange={(obj) => setConstraintDetails(jsonStringFromObject(obj))}
              />
            </div>
          </div>
          <Button type="button" disabled={saving} onClick={() => void createConstraint()}>
            {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Add regulatory constraint
          </Button>

          <div className="table-scroll">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>constraint type</TableHead>
                  <TableHead>source dossier</TableHead>
                  <TableHead>source action item</TableHead>
                  <TableHead>severity</TableHead>
                  <TableHead>constraint details</TableHead>
                  <TableHead>status</TableHead>
                  <TableHead>review state</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-sm text-muted-foreground">
                      Loading…
                    </TableCell>
                  </TableRow>
                ) : constraints.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7}>
                      <Empty>
                        <EmptyHeader>
                          <EmptyMedia variant="icon">
                            <Scale />
                          </EmptyMedia>
                          <EmptyTitle>No regulatory constraints</EmptyTitle>
                          <EmptyDescription>Add a constraint above to enforce it on the optimizer.</EmptyDescription>
                        </EmptyHeader>
                      </Empty>
                    </TableCell>
                  </TableRow>
                ) : (
                  constraints.map((row, idx) => {
                    const constraintId = row.id
                    const actionIds = Array.isArray(row.source_action_item_ids_json)
                      ? row.source_action_item_ids_json.map((v) => readString(v)).filter(Boolean).join(", ")
                      : "—"
                    return (
                      <TableRow key={readString(constraintId) || `c-${idx}`}>
                        <TableCell className="font-mono text-xs">{readStr(row, "constraint_type") || "—"}</TableCell>
                        <TableCell className="font-mono text-xs">{readStr(row, "dossier_id") || "—"}</TableCell>
                        <TableCell className="font-mono text-xs">{actionIds || "—"}</TableCell>
                        <TableCell className="text-xs">{readStr(row, "severity") || "—"}</TableCell>
                        <TableCell className="max-w-[260px] text-xs text-muted-foreground">
                          {JSON.stringify(row.constraint_json ?? {})}
                        </TableCell>
                        <TableCell className="text-xs">{readStr(row, "status") || "—"}</TableCell>
                        <TableCell>
                          {typeof constraintId === "number" ? (
                            <div className="flex flex-wrap gap-1">
                              <Button size="sm" variant="outline" onClick={() => void setConstraintReviewState(constraintId, "reviewed")}>
                                reviewed
                              </Button>
                              <Button size="sm" variant="outline" onClick={() => void setConstraintReviewState(constraintId, "active")}>
                                active
                              </Button>
                            </div>
                          ) : (
                            "—"
                          )}
                        </TableCell>
                      </TableRow>
                    )
                  })
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Card className="border-muted">
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Compliance-Driven Objective</CardTitle>
          <CardDescription>
            Compliance-informed optimization objective — yield or selectivity targets adjusted for regulatory feasibility, with impurity penalty weighting.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-2">
              <Label>yield/selectivity objective</Label>
              <Input value={objectiveYieldSelectivity} onChange={(e) => setObjectiveYieldSelectivity(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>impurity penalty</Label>
              <Input value={impurityPenalty} onChange={(e) => setImpurityPenalty(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>residual solvent penalty</Label>
              <Input value={residualPenalty} onChange={(e) => setResidualPenalty(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>nitrosamine risk penalty</Label>
              <Input value={nitrosaminePenalty} onChange={(e) => setNitrosaminePenalty(e.target.value)} />
            </div>
            <div className="space-y-2 md:col-span-2">
              <JsonObjectField
                idPrefix="hard-constraints"
                label="hard constraints"
                onChange={(obj) => setObjectiveHardConstraints(jsonStringFromObject(obj))}
              />
            </div>
            <div className="space-y-2 md:col-span-2">
              <JsonObjectField
                idPrefix="soft-constraints"
                label="soft constraints"
                onChange={(obj) => setObjectiveSoftConstraints(jsonStringFromObject(obj))}
              />
            </div>
            <div className="space-y-2">
              <Label>review status</Label>
              <Select value={objectiveReviewStatus} onValueChange={setObjectiveReviewStatus}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="draft">draft</SelectItem>
                  <SelectItem value="active">active</SelectItem>
                  <SelectItem value="reviewed">reviewed</SelectItem>
                  <SelectItem value="archived">archived</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" disabled={saving} onClick={() => void saveComplianceObjective()}>
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Save compliance objective
            </Button>
            <Button
              type="button"
              variant={useInOptimization ? "default" : "outline"}
              onClick={() => setUseInOptimization((v) => !v)}
            >
              Use in optimization
            </Button>
            <Badge variant="outline">{useInOptimization ? "enabled" : "disabled"}</Badge>
          </div>

          <div className="rounded-md border bg-muted/20 px-3 py-2 text-xs">
            <p className="font-medium text-muted-foreground">Current objective summary</p>
            {(() => {
              const objectiveJson =
                complianceObjective && isRecord(complianceObjective.objective_json)
                  ? (complianceObjective.objective_json as Record<string, unknown>)
                  : null
              return (
                <>
                  <p className="mt-1 text-muted-foreground">
                    yield/selectivity objective: {readStr(objectiveJson ?? {}, "yield_selectivity_objective") || "—"}
                  </p>
                  <p className="text-muted-foreground">review status: {readStr(complianceObjective ?? {}, "status") || "—"}</p>
                </>
              )
            })()}
          </div>

          <Collapsible className="rounded-md border">
            <CollapsibleTrigger className="flex w-full items-center justify-between px-3 py-2 text-left text-xs font-medium hover:bg-muted/50">
              Developer JSON
              <ChevronDown className="h-4 w-4" />
            </CollapsibleTrigger>
            <CollapsibleContent className="border-t px-3 py-3">
              <DeveloperJsonPanel data={{ constraints, compliance_objective: complianceObjective }} />
            </CollapsibleContent>
          </Collapsible>
        </CardContent>
      </Card>
    </div>
  )
}
