"use client"

/**
 * Repho Phase C / R13 — route scoring panel ("Routes" tab).
 *
 * Input is paste/build-a-tree ONLY — there is deliberately no "Propose routes" button; route
 * generation is an unwired heavy path (see the capability readout). Scores are advisory: the
 * risk badge treats `unknown` as WORSE than critical (unreviewable), reagent screen hits are
 * shown, and the disclaimer + human-review affordances render verbatim.
 */
import { useEffect, useState } from "react"
import { GitBranch } from "lucide-react"
import { ApiError } from "@/lib/api/client"
import { formatApiError } from "@/components/spectracheck/spectracheck-helpers"
import { ModuleCard } from "@/components/dashboard/module-card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { RouteTreeField } from "@/components/ui/route-tree-field"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { ChevronDown } from "lucide-react"
import {
  listRouteScores,
  parseRouteScoreRecord,
  postRouteScore,
  routeRiskBadgeClass,
  routeRiskLabel,
  type RouteScoreView,
} from "@/lib/reaction/phase-c"

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v)
}

/**
 * Mechanism only. Every caveat ("Advisory decision support", "never a safety
 * determination or synthesis instruction", "Route GENERATION is not available
 * in this app") stays in the visible description.
 */
const ROUTE_SCORE_TOOLTIP =
  "Every node in the tree is scored by the same frozen safety and green-chemistry engines used elsewhere in Repho, with reagent screen hits listed per step. A node that cannot be scored ranks worse than critical rather than passing."

/** Native, dependency-free render of the nested route tree (product → precursors). */
function RouteTreeNode({ node, depth }: { node: Record<string, unknown>; depth: number }) {
  const smiles = typeof node.smiles === "string" ? node.smiles : "?"
  const reagents = Array.isArray(node.reagents)
    ? node.reagents.filter((r): r is string => typeof r === "string")
    : []
  const solvent = typeof node.solvent === "string" ? node.solvent : null
  const children = Array.isArray(node.children) ? node.children.filter(isRecord) : []
  return (
    <>
      <div className="flex min-w-0 flex-wrap items-center gap-2 py-0.5">
        {/* SMILES have no natural break points — break anywhere rather than clip. */}
        <span className="min-w-0 break-all font-mono text-xs text-foreground">{smiles}</span>
        {reagents.length > 0 ? (
          <span className="min-w-0 text-[10px] text-muted-foreground">
            reagents: <span className="break-all font-mono">{reagents.join(", ")}</span>
          </span>
        ) : null}
        {solvent ? (
          <span className="min-w-0 text-[10px] text-muted-foreground">
            solvent: <span className="break-all font-mono">{solvent}</span>
          </span>
        ) : null}
      </div>
      {children.length > 0 ? (
        <ul className="ml-4 list-none border-l border-border pl-3">
          {children.map((c, i) => (
            <li key={`${depth}-${i}`} className="min-w-0">
              <RouteTreeNode node={c} depth={depth + 1} />
            </li>
          ))}
        </ul>
      ) : null}
    </>
  )
}

/** Copy affordance for the mermaid source (the app has no mermaid renderer dependency). */
function MermaidCopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      className="h-7 text-[11px]"
      onClick={() => {
        try {
          void navigator.clipboard.writeText(value).then(
            () => {
              setCopied(true)
              window.setTimeout(() => setCopied(false), 2000)
            },
            () => setCopied(false),
          )
        } catch {
          // clipboard unavailable — the source stays visible below for manual copy
        }
      }}
    >
      {copied ? "Copied" : "Copy"}
    </Button>
  )
}

function RouteScoreResult({ view }: { view: RouteScoreView }) {
  return (
    <div className="space-y-3 rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        {view.label ? <p className="text-sm font-medium text-foreground">{view.label}</p> : null}
        <Badge variant="secondary" className="text-xs">advisory</Badge>
        <Badge variant="outline" className="font-mono tabular-nums text-xs">
          Route score {view.routeScore != null ? view.routeScore.toFixed(3) : "—"}
        </Badge>
        {/* unknown renders as the WORST tier (unreviewable), never neutral */}
        <Badge className={`text-xs ${routeRiskBadgeClass(view.worstRisk)}`}>
          risk: {routeRiskLabel(view.worstRisk)}
        </Badge>
        {view.requiresExpertReview ? (
          <Badge variant="secondary" className="text-[10px]">expert review required</Badge>
        ) : null}
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          { label: "steps", value: view.stepCount },
          { label: "max depth", value: view.maxDepth },
          { label: "mean atom economy %", value: view.meanAtomEconomyPercent },
          { label: "mean solvent greenness", value: view.meanSolventGreenness },
        ].map((m) => (
          <div key={m.label} className="rounded-md border px-2 py-1.5">
            <p className="font-mono text-sm tabular-nums">{m.value != null ? m.value : "—"}</p>
            <p className="text-[10px] text-muted-foreground">{m.label}</p>
          </div>
        ))}
      </div>
      {view.scoreComponents.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {view.scoreComponents.map((c) => (
            <Badge key={c.name} variant="outline" className="font-mono tabular-nums text-[10px]">
              {c.name}: {c.value != null ? c.value.toFixed(2) : "—"}
              {c.weight != null ? ` (w ${c.weight})` : ""}
            </Badge>
          ))}
        </div>
      ) : null}
      <div className="min-w-0 space-y-1">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">route tree</p>
        <div aria-label="Route tree, product to precursors" className="min-w-0">
          <RouteTreeNode node={view.route} depth={0} />
        </div>
      </div>
      {view.startingMaterials.length > 0 ? (
        <p className="min-w-0 text-[11px] text-muted-foreground">
          starting materials:{" "}
          <span className="break-all font-mono text-foreground">{view.startingMaterials.join(", ")}</span>
        </p>
      ) : null}
      {view.screens.length > 0 ? (
        <div className="space-y-1">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            safety screens (molecules &amp; reagents)
          </p>
          <div className="space-y-1">
            {view.screens.map((s, i) => (
              <div key={`screen-${i}`} className="flex min-w-0 flex-wrap items-center gap-2 text-[11px]">
                <span className="min-w-0 break-all font-mono text-foreground">{s.smiles ?? "—"}</span>
                <Badge variant="outline" className="text-[10px]">{s.role ?? "molecule"}</Badge>
                {/* Always rendered: a missing risk has failed closed to "unknown" (unreviewable). */}
                <Badge className={`text-[10px] ${routeRiskBadgeClass(s.risk)}`}>
                  {routeRiskLabel(s.risk)}
                </Badge>
                {s.requiresExpertReview ? (
                  <Badge variant="secondary" className="text-[10px]">expert review</Badge>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {view.warnings.length > 0 ? (
        <ul className="list-inside list-disc text-[11px] text-muted-foreground">
          {view.warnings.map((w, i) => (
            <li key={`rw-${i}`}>{w}</li>
          ))}
        </ul>
      ) : null}
      {view.mermaid ? (
        <Collapsible className="rounded-md border">
          <CollapsibleTrigger className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs font-medium hover:bg-muted/50">
            Mermaid source
            <ChevronDown className="h-4 w-4 shrink-0 opacity-70" />
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-2 border-t px-3 py-2">
            <MermaidCopyButton value={view.mermaid} />
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all rounded bg-muted/40 p-2 font-mono text-[10px] leading-snug">
              {view.mermaid}
            </pre>
          </CollapsibleContent>
        </Collapsible>
      ) : null}
      {view.humanReviewRequired ? (
        <p className="text-[11px] font-medium text-foreground">
          Human review required — a qualified chemist must review every route before any use.
        </p>
      ) : null}
      {view.disclaimer ? (
        <p className="text-[11px] italic text-muted-foreground">{view.disclaimer}</p>
      ) : null}
    </div>
  )
}

export function RouteScoresPanel({ projectId }: { projectId: number }) {
  const [route, setRoute] = useState<Record<string, unknown>>({})
  const [label, setLabel] = useState("")
  const [inputError, setInputError] = useState("")
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState("")
  const [latest, setLatest] = useState<Record<string, unknown> | null>(null)
  const [history, setHistory] = useState<Record<string, unknown>[]>([])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const rows = await listRouteScores(projectId)
        if (!cancelled && Array.isArray(rows)) {
          setHistory(rows.filter(isRecord) as Record<string, unknown>[])
        }
      } catch {
        // list is best-effort; scoring still works
      }
    })()
    return () => {
      cancelled = true
    }
  }, [projectId])

  async function score(e: React.FormEvent) {
    e.preventDefault()
    setMsg("")
    if (typeof route.smiles !== "string" || route.smiles.trim() === "") {
      setInputError("The route's root node needs a product SMILES.")
      return
    }
    setInputError("")
    setBusy(true)
    try {
      const created = await postRouteScore(projectId, {
        route,
        label: label.trim(),
        route_format: "native",
      })
      if (isRecord(created)) {
        setLatest(created)
        setHistory((prev) => [created, ...prev])
      } else {
        // Never leave a stale score on screen pretending to be this submission's result.
        setLatest(null)
        setMsg("The score could not be read — retry, or check previous scores below.")
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 400 && isRecord(err.data) && typeof err.data.detail === "string") {
        setInputError(err.data.detail) // malformed route tree → inline validation message
      } else {
        setMsg(formatApiError(err, "Could not score the route."))
      }
    } finally {
      setBusy(false)
    }
  }

  const latestView = latest != null ? parseRouteScoreRecord(latest) : null

  return (
    <ModuleCard
      accent="violet"
      eyebrow="Routes · Scoring"
      title={
        <span className="inline-flex items-center gap-2">
          Score a synthesis route
          <InfoTooltip content={ROUTE_SCORE_TOOLTIP} label="How route scoring works" />
        </span>
      }
      icon={GitBranch}
      description="Rates a route tree on safety and green-chemistry risk. Advisory decision support — never a safety determination or synthesis instruction. Route GENERATION is not available in this app; input is manual by design."
    >
      <form className="space-y-3" onSubmit={(e) => void score(e)}>
        <div className="space-y-1">
          <RouteTreeField
            label="Route tree"
            initialValue={route}
            onChange={setRoute}
            description="Build the target product and its precursors, or paste JSON."
          />
          {inputError ? (
            <p role="alert" className="text-[11px] text-destructive">
              {inputError}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="rs-label" className="text-xs">label (optional)</Label>
            <Input
              id="rs-label"
              className="h-8 w-56 text-xs"
              maxLength={200}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="route A — acylation first"
            />
          </div>
          <Button type="submit" size="sm" disabled={busy}>
            {busy ? "Scoring…" : "Score route"}
          </Button>
        </div>
      </form>
      {msg ? (
        <p role="status" className="mt-3 text-xs text-muted-foreground">
          {msg}
        </p>
      ) : null}
      {latestView != null ? (
        <div className="mt-4">
          <RouteScoreResult view={latestView} />
        </div>
      ) : null}
      {history.length > (latest != null ? 1 : 0) ? (
        <div className="mt-4 space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            previous scores (newest first)
          </p>
          <div className="space-y-1">
            {history
              .filter((h) => latest == null || h !== latest)
              .slice(0, 10)
              .map((h, i) => {
                const v = parseRouteScoreRecord(h)
                if (v == null) return null
                // Expandable: a persisted risk verdict must carry its review affordances +
                // disclaimer too, not just a bare score row.
                return (
                  <Collapsible key={`hist-${v.id ?? i}`} className="rounded-md border">
                    <CollapsibleTrigger className="flex w-full flex-wrap items-center gap-2 px-2 py-1.5 text-left text-[11px] hover:bg-muted/50">
                      <span className="font-mono text-muted-foreground">#{v.id ?? "—"}</span>
                      {v.label ? <span className="text-foreground">{v.label}</span> : null}
                      <span className="font-mono tabular-nums">
                        score {v.routeScore != null ? v.routeScore.toFixed(3) : "—"}
                      </span>
                      <Badge className={`text-[10px] ${routeRiskBadgeClass(v.worstRisk)}`}>
                        {routeRiskLabel(v.worstRisk)}
                      </Badge>
                      {v.requiresExpertReview ? (
                        <Badge variant="secondary" className="text-[10px]">expert review required</Badge>
                      ) : null}
                      <span className="text-muted-foreground">{v.stepCount ?? "—"} steps</span>
                      <ChevronDown className="ml-auto h-4 w-4 shrink-0 opacity-70" />
                    </CollapsibleTrigger>
                    <CollapsibleContent className="border-t p-2">
                      <RouteScoreResult view={v} />
                    </CollapsibleContent>
                  </Collapsible>
                )
              })}
          </div>
        </div>
      ) : null}
    </ModuleCard>
  )
}
