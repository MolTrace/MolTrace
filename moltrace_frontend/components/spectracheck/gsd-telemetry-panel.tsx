"use client"

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Atom,
  BadgeCheck,
  CheckCircle,
  Clock,
  ExternalLink,
  Gauge,
  GraduationCap,
  HelpCircle,
  Hourglass,
  Loader2,
  ServerCrash,
  Sparkles,
  XCircle,
  Zap,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { apiFetch } from "@/lib/api/client"
import { cn } from "@/lib/utils"
import type { components } from "@/src/lib/api/schema"

type UserPublic = components["schemas"]["UserPublic"]
type AdminUserGSDGraduationRequest = components["schemas"]["AdminUserGSDGraduationRequest"]

/** Minimum length for the regulatory-traceable graduation reason. */
const GRADUATION_REASON_MIN_LENGTH = 10

/**
 * GSD telemetry hook + panel.
 *
 * Phase 25b: replaces the client-side aggregation of /audit/events with
 * the typed pre-aggregated endpoint
 *   GET /spectrum/analyze/gsd/telemetry-summary?window_days=N
 *
 * The backend now owns the rollup AND the readiness verdict:
 *   - invocations / errors / error_rate
 *   - median_wall_ms + p95_wall_ms
 *   - solvent_detected_count over fixtures_with_solvent_declared
 *   - by_nucleus + by_level slices
 *   - flip_readiness_verdict ("insufficient_data" | "clear" | "blocked")
 *   - flip_readiness_reasons[]
 *   - flip_readiness_policy (min_invocations, max_error_rate,
 *     min_solvent_detect_rate) — pulled live so the FE never hard-codes
 *     the gate target.
 *
 * One module-level cache, shared by the SpectraCheck Overview panel +
 * the admin readiness page + the Experimental-badge tooltip. 30s TTL,
 * dedupes concurrent in-flight requests.
 */

type SpectrumGSDTelemetrySummary = components["schemas"]["SpectrumGSDTelemetrySummary"]
type FlipReadinessVerdict = SpectrumGSDTelemetrySummary["flip_readiness_verdict"]

export type GsdTelemetryState =
  | { status: "loading"; summary: SpectrumGSDTelemetrySummary | null; error: null }
  | { status: "ready"; summary: SpectrumGSDTelemetrySummary; error: null }
  | { status: "error"; summary: null; error: string }

const DEFAULT_WINDOW_DAYS = 90
const CACHE_TTL_MS = 30_000

type CacheEntry = { summary: SpectrumGSDTelemetrySummary; fetchedAt: number }
/** Cache + in-flight maps keyed by `${windowDays}|${actorUserId ?? "global"}` so
    the global rollup, per-user rollups, and different window sizes never collide. */
const TELEMETRY_CACHE = new Map<string, CacheEntry>()
const TELEMETRY_PROMISES = new Map<string, Promise<SpectrumGSDTelemetrySummary>>()

function cacheKey(windowDays: number, actorUserId: number | null | undefined): string {
  return `${windowDays}|${actorUserId == null ? "global" : actorUserId}`
}

function fetchSummary(
  windowDays: number,
  actorUserId: number | null | undefined,
): Promise<SpectrumGSDTelemetrySummary> {
  const key = cacheKey(windowDays, actorUserId)
  const cached = TELEMETRY_CACHE.get(key)
  if (cached && Date.now() - cached.fetchedAt < CACHE_TTL_MS) {
    return Promise.resolve(cached.summary)
  }
  const inflight = TELEMETRY_PROMISES.get(key)
  if (inflight) return inflight
  const params = new URLSearchParams({ window_days: String(windowDays) })
  if (actorUserId != null) params.set("actor_user_id", String(actorUserId))
  const promise = apiFetch<SpectrumGSDTelemetrySummary>(
    `/spectrum/analyze/gsd/telemetry-summary?${params.toString()}`,
  )
    .then((summary) => {
      TELEMETRY_CACHE.set(key, { summary, fetchedAt: Date.now() })
      return summary
    })
    .finally(() => {
      TELEMETRY_PROMISES.delete(key)
    })
  TELEMETRY_PROMISES.set(key, promise)
  return promise
}

export function useGsdTelemetry(
  enabled: boolean = true,
  windowDays: number = DEFAULT_WINDOW_DAYS,
  actorUserId: number | null = null,
): GsdTelemetryState {
  const initialCache = TELEMETRY_CACHE.get(cacheKey(windowDays, actorUserId))
  const [state, setState] = useState<GsdTelemetryState>(() =>
    initialCache
      ? { status: "ready", summary: initialCache.summary, error: null }
      : { status: "loading", summary: null, error: null },
  )
  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    setState((prev) =>
      prev.status === "ready" ? prev : { status: "loading", summary: null, error: null },
    )
    fetchSummary(windowDays, actorUserId)
      .then((summary) => {
        if (cancelled) return
        setState({ status: "ready", summary, error: null })
      })
      .catch((err) => {
        if (cancelled) return
        setState({
          status: "error",
          summary: null,
          error: String((err as { message?: string })?.message ?? err),
        })
      })
    return () => {
      cancelled = true
    }
  }, [enabled, windowDays, actorUserId])
  return state
}

// ── Bar list — used for error breakdown + slice tiles ──────────────────
function BarList({
  items,
  emptyHint,
  tone = "neutral",
}: {
  items: { label: string; count: number }[]
  emptyHint: string
  tone?: "neutral" | "amber"
}) {
  if (items.length === 0) {
    return <p className="text-xs text-muted-foreground">{emptyHint}</p>
  }
  const max = Math.max(...items.map((i) => i.count), 1)
  const total = items.reduce((acc, i) => acc + i.count, 0)
  const barColor =
    tone === "amber"
      ? "color-mix(in oklab, var(--mt-amber, #B45309) 60%, transparent)"
      : "var(--mt-teal)"
  return (
    <ul className="space-y-1.5">
      {items.map((item) => {
        const width = (item.count / max) * 100
        const pct = total > 0 ? ((item.count / total) * 100).toFixed(0) : "0"
        return (
          <li key={item.label}>
            <div className="flex items-center justify-between gap-2 text-xs">
              <span className="truncate font-mono">{item.label}</span>
              <span className="shrink-0 font-mono tabular-nums text-muted-foreground">
                {item.count} <span className="opacity-60">· {pct}%</span>
              </span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
              <div className="h-full" style={{ width: `${width}%`, backgroundColor: barColor }} />
            </div>
          </li>
        )
      })}
    </ul>
  )
}

// ── Stacked-bar — used for error_kind_counts (single thin row) ─────────
function StackedBar({ items }: { items: { label: string; count: number }[] }) {
  if (items.length === 0) return null
  const total = items.reduce((acc, i) => acc + i.count, 0)
  if (total === 0) return null
  // Stable color spread per item (5 amber/rose shades — deterministic by index)
  const SHADES = ["#B45309", "#D97706", "#F59E0B", "#E11D48", "#9F1239"] as const
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted">
      {items.map((item, idx) => {
        const pct = (item.count / total) * 100
        if (pct <= 0) return null
        return (
          <div
            key={item.label}
            className="h-full"
            style={{ width: `${pct}%`, backgroundColor: SHADES[idx % SHADES.length] }}
            title={`${item.label}: ${item.count} (${pct.toFixed(1)}%)`}
          />
        )
      })}
    </div>
  )
}

// ── Helpers ────────────────────────────────────────────────────────────
function formatMs(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return "—"
  if (ms < 1000) return `${ms.toFixed(0)} ms`
  return `${(ms / 1000).toFixed(2)} s`
}

function toBarItems(record: { [key: string]: number } | undefined): { label: string; count: number }[] {
  if (!record) return []
  return Object.entries(record)
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count)
}

const VERDICT_STYLE: Record<FlipReadinessVerdict, { label: string; chip: string; dot: string; icon: typeof CheckCircle }> = {
  clear: {
    label: "Clear · ready to flip default",
    chip: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300",
    dot: "bg-emerald-500",
    icon: CheckCircle,
  },
  blocked: {
    label: "Blocked · gate criteria not met",
    chip: "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300",
    dot: "bg-rose-500",
    icon: AlertTriangle,
  },
  insufficient_data: {
    label: "Insufficient data · awaiting more tenant runs",
    chip: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300",
    dot: "bg-amber-500",
    icon: HelpCircle,
  },
}

// ── Panel ──────────────────────────────────────────────────────────────
export type GsdTelemetryPanelProps = {
  mode?: "tenant" | "admin"
  /** Time window for the rollup (server-side query parameter). Default 90 days. */
  windowDays?: number
  /** Scope the rollup to a single audit-event actor (per-user telemetry).
      When set, the response's `scope_actor_user_id` echoes it back for verification. */
  actorUserId?: number | null
  title?: string
  description?: string
  testId?: string
}

export function GsdTelemetryPanel({
  mode = "tenant",
  windowDays = DEFAULT_WINDOW_DAYS,
  actorUserId = null,
  title,
  description,
  testId,
}: GsdTelemetryPanelProps) {
  const state = useGsdTelemetry(true, windowDays, actorUserId)
  const summary = state.summary

  const errorItems = useMemo(() => toBarItems(summary?.error_kind_counts), [summary])
  const nucleusItems = useMemo(() => toBarItems(summary?.by_nucleus), [summary])
  const levelItems = useMemo(
    () =>
      toBarItems(summary?.by_level)
        .map((i) => ({ ...i, label: `level ${i.label}` }))
        .sort((a, b) => Number(a.label.split(" ")[1]) - Number(b.label.split(" ")[1])),
    [summary],
  )

  const resolvedTitle =
    title ??
    (mode === "admin"
      ? "GSD readiness · server-aggregated telemetry"
      : "GSD telemetry · this tenant")
  const resolvedDescription =
    description ??
    (mode === "admin"
      ? "Pre-aggregated rollup of every spectrum.analyze_gsd audit event over the trailing window. Backend now owns the rollup and the promotion-gate verdict — FE renders both as-is."
      : "Pre-aggregated rollup of your tenant's experimental-backend usage. Use to verify performance on your spectra and size opt-in adoption before the promotion gate clears.")

  if (state.status === "loading") {
    return (
      <div
        data-testid={testId ?? "gsd-telemetry-panel-loading"}
        className="flex items-center gap-3 rounded-2xl border bg-card px-5 py-6 text-sm text-muted-foreground"
        style={{ borderTop: "3px solid var(--mt-teal)" }}
      >
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        Loading GSD telemetry…
      </div>
    )
  }

  // The "unavailable" branch covers three operational cases that all
  // collapse to the same UX outcome: hook error, missing summary, or a
  // summary that's structurally incomplete (e.g. a hostile proxy stripped
  // fields, a test/mock primed the cache with a partial object, or the
  // backend ever drifts from its own schema). `flip_readiness_policy` is
  // the only nested object the renderer dereferences without a fallback,
  // so guarding it here keeps the whole tree from unmounting on partial
  // data.
  if (state.status === "error" || !summary || !summary.flip_readiness_policy) {
    return (
      <div
        data-testid={testId ?? "gsd-telemetry-panel-error"}
        className="flex items-start gap-3 rounded-2xl border bg-card px-5 py-5 text-sm"
        style={{ borderTop: "3px solid var(--mt-amber, #B45309)" }}
      >
        <ServerCrash className="mt-0.5 h-4 w-4 text-amber-700 dark:text-amber-400" aria-hidden />
        <div>
          <p className="font-semibold">Telemetry unavailable</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Could not load /spectrum/analyze/gsd/telemetry-summary. The panel reloads on the next
            mount.
          </p>
        </div>
      </div>
    )
  }

  const targetRuns = summary.flip_readiness_policy.min_invocations
  const targetPct = targetRuns > 0 ? Math.min(100, (summary.invocations / targetRuns) * 100) : 0
  const errorRate = summary.error_rate
  const maxErrorRate = summary.flip_readiness_policy.max_error_rate
  const minSolventRate = summary.flip_readiness_policy.min_solvent_detect_rate
  const solventRate = summary.solvent_detect_rate
  const verdict = VERDICT_STYLE[summary.flip_readiness_verdict] ?? VERDICT_STYLE.insufficient_data
  const VerdictIcon = verdict.icon

  return (
    <section
      data-testid={testId ?? `gsd-telemetry-panel-${mode}`}
      className="rounded-2xl border bg-card p-6 shadow-sm sm:p-7"
      style={{ borderTop: "3px solid var(--mt-teal)" }}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p
            className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
            style={{ color: "var(--mt-teal)" }}
          >
            {mode === "admin" ? "Readiness · live" : "Telemetry · live"}
          </p>
          <h3 className="mt-1 text-lg font-semibold tracking-tight sm:text-xl">{resolvedTitle}</h3>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {mode === "admin" ? (
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em]",
                verdict.chip,
              )}
            >
              <VerdictIcon className="h-3 w-3" aria-hidden />
              {verdict.label}
            </span>
          ) : null}
          <span
            className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em]"
            style={{
              borderColor: "color-mix(in oklab, var(--mt-teal) 30%, transparent)",
              backgroundColor: "var(--mt-teal-soft)",
              color: "var(--mt-teal)",
            }}
          >
            <span
              className="h-1.5 w-1.5 animate-pulse rounded-full"
              style={{ backgroundColor: "var(--mt-teal)" }}
              aria-hidden
            />
            generated {new Date(summary.generated_at).toLocaleString()}
          </span>
        </div>
      </div>
      <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted-foreground">
        {resolvedDescription} <span className="font-mono">window_days={summary.window_days}</span>.
      </p>

      {/* Quarter readiness band + adoption callout — paired narrative:
          "how close to evaluating the gate?" + "how many already graduated?". */}
      <div className="mt-6 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div className="rounded-xl border bg-background/50 p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
              Quarter readiness band
            </p>
            <p className="font-mono text-xs tabular-nums">
              <span className="text-2xl font-bold tracking-tight" style={{ color: "var(--mt-teal)" }}>
                {summary.invocations.toLocaleString()}
              </span>
              <span className="text-muted-foreground"> / {targetRuns.toLocaleString()} calls</span>
            </p>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full"
              style={{
                width: `${targetPct.toFixed(1)}%`,
                backgroundColor: "var(--mt-teal)",
              }}
            />
          </div>
          <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            {targetPct.toFixed(1)}% toward minimum invocations to evaluate the gate
          </p>
        </div>
        <AdoptionCallout
          count={summary.graduated_user_count}
          scopedToUser={actorUserId != null}
        />
      </div>

      {/* KPI strip */}
      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi
          icon={Activity}
          label="Invocations"
          value={summary.invocations.toLocaleString()}
          sub={
            summary.errors === 0
              ? "no errors recorded"
              : `${summary.errors} errors · ${errorRate != null ? (errorRate * 100).toFixed(2) + "%" : "—"}`
          }
          tone={errorRate == null ? "neutral" : errorRate <= maxErrorRate ? "ok" : "bad"}
        />
        <Kpi
          icon={Zap}
          label="Solvent auto-detect"
          value={solventRate == null ? "no data" : `${(solventRate * 100).toFixed(1)}%`}
          sub={
            summary.fixtures_with_solvent_declared === 0
              ? "no fixtures declared a solvent"
              : `${summary.solvent_detected_count} / ${summary.fixtures_with_solvent_declared} with declared solvent`
          }
          tone={solventRate == null ? "neutral" : solventRate >= minSolventRate ? "ok" : "warn"}
        />
        <Kpi
          icon={Clock}
          label="Median wall_ms"
          value={formatMs(summary.median_wall_ms)}
          sub="p50 of measured runs"
        />
        <Kpi
          icon={Gauge}
          label="P95 wall_ms"
          value={formatMs(summary.p95_wall_ms)}
          sub="tail latency · 95th percentile"
        />
      </div>

      {/* Detail row: error breakdown + slice tiles */}
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="rounded-xl border bg-background/40 p-4">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
              Error kind breakdown
            </p>
          </div>
          <div className="mt-3">
            {errorItems.length > 0 ? <StackedBar items={errorItems} /> : null}
          </div>
          <div className="mt-3">
            <BarList
              items={errorItems.slice(0, 5)}
              emptyHint="No errors in the trailing window. Healthy."
              tone="amber"
            />
          </div>
        </div>
        <div className="rounded-xl border bg-background/40 p-4">
          <div className="flex items-center gap-2">
            <Atom className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
              By nucleus
            </p>
          </div>
          <div className="mt-4">
            <BarList items={nucleusItems} emptyHint="No invocations to slice by nucleus." />
          </div>
        </div>
        <div className="rounded-xl border bg-background/40 p-4">
          <div className="flex items-center gap-2">
            <Sparkles className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
              By GSD level
            </p>
          </div>
          <div className="mt-4">
            <BarList items={levelItems} emptyHint="No invocations to slice by level." />
          </div>
        </div>
      </div>

      {/* Admin verdict reasons */}
      {mode === "admin" && summary.flip_readiness_reasons && summary.flip_readiness_reasons.length > 0 ? (
        <div className="mt-6 rounded-xl border border-dashed bg-muted/30 p-4">
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
            Verdict reasons (backend-owned)
          </p>
          <ul className="mt-3 space-y-1.5">
            {summary.flip_readiness_reasons.map((reason, idx) => (
              <li key={idx} className="flex items-start gap-2 text-xs leading-relaxed">
                <span
                  className={`mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full ${verdict.dot}`}
                  aria-hidden
                />
                <span className="text-foreground">{reason}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Policy snapshot footer */}
      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-dashed bg-muted/20 px-4 py-3 text-xs">
        <p className="text-muted-foreground">
          <span className="font-mono font-bold uppercase tracking-[0.12em] text-foreground">
            Gate policy
          </span>{" "}
          · invocations ≥ {targetRuns.toLocaleString()} · error rate ≤{" "}
          {(maxErrorRate * 100).toFixed(2)}% · solvent detect ≥ {(minSolventRate * 100).toFixed(0)}%
        </p>
        <p className="font-mono tabular-nums text-muted-foreground">
          (policy snapshot returned with this rollup)
        </p>
      </div>
    </section>
  )
}

/**
 * Phase 25f — platform-wide adoption stat.
 *
 * `graduated_user_count` is the cumulative number of tenant users the
 * backend has marked `gsd_graduated_at != null`. Same value regardless
 * of `actor_user_id` (it's a platform-wide count). On the admin
 * readiness page it reads as "how far has rollout gone?"; on the
 * tenant-detail card it reads as "you wouldn't be the first."
 */
function AdoptionCallout({
  count,
  scopedToUser,
}: {
  count: number
  scopedToUser: boolean
}) {
  const noneYet = count === 0
  return (
    <div className="flex flex-col justify-between rounded-xl border bg-background/50 p-4">
      <div className="flex items-center gap-2">
        <GraduationCap className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
          Adoption · graduated tenants
        </p>
      </div>
      <div className="mt-2">
        <p
          className="font-mono text-3xl font-bold tabular-nums tracking-tight sm:text-4xl"
          style={{ color: noneYet ? "var(--muted-foreground)" : "var(--mt-teal)" }}
        >
          {count.toLocaleString()}
        </p>
        <p className="mt-1 text-[11px] leading-snug text-muted-foreground">
          {noneYet
            ? scopedToUser
              ? "No tenants graduated yet — this user would be first."
              : "No tenants graduated yet across the platform."
            : scopedToUser
              ? `${count.toLocaleString()} other tenant${count === 1 ? "" : "s"} already default to gsd_prompt3.`
              : `${count.toLocaleString()} tenant${count === 1 ? "" : "s"} default to gsd_prompt3 platform-wide.`}
        </p>
      </div>
    </div>
  )
}

function Kpi({
  icon: Icon,
  label,
  value,
  sub,
  tone = "neutral",
}: {
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>
  label: string
  value: string
  sub: string
  tone?: "ok" | "warn" | "bad" | "neutral"
}) {
  const toneClass =
    tone === "ok"
      ? "text-emerald-600 dark:text-emerald-400"
      : tone === "warn"
        ? "text-amber-600 dark:text-amber-400"
        : tone === "bad"
          ? "text-rose-600 dark:text-rose-400"
          : "text-foreground"
  return (
    <div className="rounded-xl border bg-background/50 p-4">
      <div className="flex items-center gap-2">
        <Icon className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
          {label}
        </p>
      </div>
      <p className={cn("mt-2 font-mono text-2xl font-bold tabular-nums tracking-tight sm:text-3xl", toneClass)}>
        {value}
      </p>
      <p className="mt-1 text-[11px] leading-snug text-muted-foreground">{sub}</p>
    </div>
  )
}

// ── Verdict-driven action card ─────────────────────────────────────────
// The packet asks for an action-shaped switch over `flip_readiness_verdict`:
//   - insufficient_data → progress widget toward target
//   - clear            → primary CTA to kick off the flip-review process
//   - blocked          → reasons list with severity styling
// Lives alongside the telemetry panel so any future surface (admin email,
// status page, slack bot) can drop it in with the same single fetch.

export type GsdReadinessVerdictCardProps = {
  /**
   * Optional href the "Request flip review" CTA opens. Defaults to the
   * in-app contact form with a pre-filled reason. Replace with a real
   * intake endpoint when one ships.
   */
  flipReviewHref?: string
  /** Optional override for the data-testid root. */
  testId?: string
  /** Override the time window the underlying hook queries. Default 90. */
  windowDays?: number
  /**
   * Scope the readiness verdict to a single audit-event actor — i.e.
   * "is THIS user (often the primary tenant admin) ready to graduate
   * from experimental?". When null/omitted, the platform-wide rollup is
   * used. The CTA copy + scope chip shift to "this user" when set.
   */
  actorUserId?: number | null
  /**
   * Human label for the scoped subject (e.g. tenant slug or display
   * name). Shown in the scope chip and CTA copy when actorUserId is
   * set. Falls back to "user #N".
   */
  scopeLabel?: string
  /**
   * Pre-fetched graduation timestamp for the scoped user (from
   * `UserPublic.gsd_graduated_at` / `AdminUserRecord.gsd_graduated_at`).
   * When provided, the card renders the "already graduated" state
   * directly without showing the graduate form. When omitted, the card
   * starts in the action state and updates locally after a successful
   * POST.
   */
  gsdGraduatedAt?: string | null
}

const DEFAULT_FLIP_REVIEW_HREF = "/contact?reason=Request%20GSD%20default-flip%20review"

export function GsdReadinessVerdictCard({
  flipReviewHref = DEFAULT_FLIP_REVIEW_HREF,
  testId = "gsd-readiness-verdict-card",
  windowDays = DEFAULT_WINDOW_DAYS,
  actorUserId = null,
  scopeLabel,
  gsdGraduatedAt,
}: GsdReadinessVerdictCardProps) {
  const state = useGsdTelemetry(true, windowDays, actorUserId)
  const scope = actorUserId != null
    ? { kind: "user" as const, label: scopeLabel ?? `user #${actorUserId}`, actorUserId }
    : { kind: "platform" as const, label: "platform-wide", actorUserId: null }
  if (state.status === "loading") {
    return (
      <div
        data-testid={`${testId}-loading`}
        className="flex items-center gap-3 rounded-2xl border bg-card px-5 py-6 text-sm text-muted-foreground"
        style={{ borderTop: "3px solid var(--mt-teal)" }}
      >
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
        Loading readiness verdict…
      </div>
    )
  }
  // Mirror GsdTelemetryPanel's guard — fall back to the "unavailable"
  // card when the summary is missing or structurally incomplete, since
  // every verdict branch dereferences `flip_readiness_policy`.
  if (state.status === "error" || !state.summary || !state.summary.flip_readiness_policy) {
    return (
      <div
        data-testid={`${testId}-error`}
        className="flex items-start gap-3 rounded-2xl border bg-card px-5 py-5 text-sm"
        style={{ borderTop: "3px solid var(--mt-amber, #B45309)" }}
      >
        <ServerCrash className="mt-0.5 h-4 w-4 text-amber-700 dark:text-amber-400" aria-hidden />
        <div>
          <p className="font-semibold">Readiness verdict unavailable</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Could not load /spectrum/analyze/gsd/telemetry-summary. The card reloads on the next
            mount.
          </p>
        </div>
      </div>
    )
  }
  const s = state.summary
  switch (s.flip_readiness_verdict) {
    case "insufficient_data":
      return (
        <NeedMoreData
          progress={s.invocations}
          target={s.flip_readiness_policy.min_invocations}
          windowDays={s.window_days}
          reasons={s.flip_readiness_reasons ?? []}
          scope={scope}
          testId={testId}
        />
      )
    case "clear":
      return (
        <ReadyToFlip
          flipReviewHref={flipReviewHref}
          summary={s}
          scope={scope}
          gsdGraduatedAt={gsdGraduatedAt ?? null}
          testId={testId}
        />
      )
    case "blocked":
      return <Blocked summary={s} scope={scope} testId={testId} />
    default:
      // Exhaustive — the enum has three values. If a future verdict
      // ships ahead of FE typegen, fall back to the "insufficient" shape
      // rather than render nothing.
      return (
        <NeedMoreData
          progress={s.invocations}
          target={s.flip_readiness_policy.min_invocations}
          windowDays={s.window_days}
          reasons={s.flip_readiness_reasons ?? ["Unknown verdict from backend — defaulting to insufficient_data."]}
          scope={scope}
          testId={testId}
        />
      )
  }
}

type VerdictScope =
  | { kind: "platform"; label: string; actorUserId: null }
  | { kind: "user"; label: string; actorUserId: number }

function ScopeChip({ scope }: { scope: VerdictScope }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border bg-background/60 px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-muted-foreground"
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: scope.kind === "user" ? "var(--mt-teal)" : "currentColor" }}
        aria-hidden
      />
      Scope · {scope.label}
    </span>
  )
}

// ── insufficient_data — progress band ──────────────────────────────────
function NeedMoreData({
  progress,
  target,
  windowDays,
  reasons,
  scope,
  testId,
}: {
  progress: number
  target: number
  windowDays: number
  reasons: string[]
  scope: VerdictScope
  testId: string
}) {
  const pct = target > 0 ? Math.min(100, (progress / target) * 100) : 0
  const remaining = Math.max(0, target - progress)
  return (
    <section
      data-testid={`${testId}-insufficient`}
      className="rounded-2xl border border-amber-300 bg-amber-50 p-6 shadow-sm dark:border-amber-900 dark:bg-amber-950/30 sm:p-7"
    >
      <div className="flex items-start gap-4">
        <Hourglass className="mt-0.5 h-7 w-7 shrink-0 text-amber-800 dark:text-amber-300" aria-hidden />
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-amber-800 dark:text-amber-300">
              Verdict · insufficient data
            </p>
            <ScopeChip scope={scope} />
          </div>
          <h2 className="mt-1 text-xl font-semibold tracking-tight sm:text-2xl">
            {scope.kind === "user"
              ? `Awaiting more runs from ${scope.label}.`
              : "Awaiting more tenant runs."}
          </h2>
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-foreground/85">
            Invocation count is below the threshold required to evaluate the promotion gate. The
            gate can't fail or pass yet — it can only wait.{" "}
            {scope.kind === "user"
              ? "Reach out to this user to encourage GSD opt-in on their next SpectraCheck session."
              : "Encourage opt-in adoption in tenant accounts (the SpectraCheck Overview panel surfaces the per-tenant invitation)."}
          </p>
          <div className="mt-6 rounded-xl border bg-background/50 p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                Progress toward minimum invocations
              </p>
              <p className="font-mono text-xs tabular-nums">
                <span className="text-2xl font-bold tracking-tight text-foreground">
                  {progress.toLocaleString()}
                </span>
                <span className="text-muted-foreground"> / {target.toLocaleString()}</span>
              </p>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full bg-amber-500"
                style={{ width: `${pct.toFixed(1)}%` }}
              />
            </div>
            <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              {pct.toFixed(1)}% · {remaining.toLocaleString()} more runs needed within{" "}
              {windowDays}-day window
            </p>
          </div>
          {reasons.length > 0 ? (
            <ul className="mt-4 space-y-1.5">
              {reasons.map((r, idx) => (
                <li key={idx} className="flex items-start gap-2 text-xs leading-relaxed">
                  <span className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" aria-hidden />
                  <span className="text-foreground">{r}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </section>
  )
}

// ── clear — primary CTA to kick off the flip-review process ────────────
// When scoped to a user, the CTA POSTs to /admin/users/{id}/gsd-graduation
// directly with a required reason (regulatory-traceable). For the
// platform-wide case the CTA stays a mailto:/contact handoff because
// platform default-flip is a deploy-time decision, not a per-user POST.
function ReadyToFlip({
  flipReviewHref,
  summary,
  scope,
  gsdGraduatedAt,
  testId,
}: {
  flipReviewHref: string
  summary: SpectrumGSDTelemetrySummary
  scope: VerdictScope
  gsdGraduatedAt: string | null
  testId: string
}) {
  // Local mirror of the graduation timestamp — starts from the prop and
  // updates after a successful POST so the success view persists across
  // re-renders without prop refetch.
  const [localGraduatedAt, setLocalGraduatedAt] = useState<string | null>(gsdGraduatedAt)
  const effectiveGraduatedAt = localGraduatedAt ?? gsdGraduatedAt
  const isGraduated = Boolean(effectiveGraduatedAt)
  const isUserScoped = scope.kind === "user"

  return (
    <section
      data-testid={`${testId}-clear`}
      className="rounded-2xl border border-emerald-300 bg-emerald-50 p-6 shadow-sm dark:border-emerald-900 dark:bg-emerald-950/30 sm:p-7"
    >
      <div className="flex items-start gap-4">
        <CheckCircle className="mt-0.5 h-7 w-7 shrink-0 text-emerald-700 dark:text-emerald-300" aria-hidden />
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-emerald-700 dark:text-emerald-300">
              Verdict · clear
            </p>
            <ScopeChip scope={scope} />
            {isGraduated ? (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-100 px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/60 dark:text-emerald-200">
                <BadgeCheck className="h-3 w-3" aria-hidden />
                Graduated
              </span>
            ) : null}
          </div>
          <h2 className="mt-1 text-xl font-semibold tracking-tight sm:text-2xl">
            {isGraduated
              ? isUserScoped
                ? `${scope.label} graduated from experimental.`
                : "Default flipped."
              : isUserScoped
                ? `Gate criteria met for ${scope.label}. Ready to graduate.`
                : "Gate criteria met. Ready to flip the default."}
          </h2>
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-foreground/85">
            {isGraduated ? (
              <>
                {isUserScoped ? (
                  <>
                    Subsequent <code className="font-mono">/spectrum/analyze/gsd</code> calls from{" "}
                    {scope.label} now return{" "}
                    <code className="font-mono">experimental: false</code> in both the response
                    and the audit telemetry. Graduation recorded{" "}
                    {effectiveGraduatedAt
                      ? new Date(effectiveGraduatedAt).toLocaleString()
                      : "just now"}
                    .
                  </>
                ) : (
                  <>
                    Platform-wide flip-review has been recorded. The next FE deploy can ship the
                    one-line default change with the documented change-control trail.
                  </>
                )}
              </>
            ) : isUserScoped ? (
              <>
                Every promotion-gate criterion is satisfied for {scope.label} in the trailing{" "}
                {summary.window_days}-day window. Graduating this user moves their default from{" "}
                <code className="font-mono">legacy</code> to{" "}
                <code className="font-mono">gsd_prompt3</code> on their next session — without
                affecting other tenants. A reason is required and recorded in the audit ledger.
              </>
            ) : (
              <>
                Every promotion-gate criterion is satisfied in the trailing {summary.window_days}
                -day window. Kick off a flip-review with change-control: a one-line FE change moves
                the selector default from <code className="font-mono">legacy</code> to{" "}
                <code className="font-mono">gsd_prompt3</code> and the GSD_EXPERIMENTAL_TOOLTIP
                copy should update at the same time.
              </>
            )}
          </p>
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            <Stat label="Invocations" value={summary.invocations.toLocaleString()} sub="≥ target" />
            <Stat
              label="Error rate"
              value={
                summary.error_rate != null
                  ? `${(summary.error_rate * 100).toFixed(2)}%`
                  : "—"
              }
              sub={`≤ ${(summary.flip_readiness_policy.max_error_rate * 100).toFixed(2)}% target`}
            />
            <Stat
              label="Solvent detect"
              value={
                summary.solvent_detect_rate != null
                  ? `${(summary.solvent_detect_rate * 100).toFixed(1)}%`
                  : "—"
              }
              sub={`≥ ${(summary.flip_readiness_policy.min_solvent_detect_rate * 100).toFixed(0)}% target`}
            />
          </div>
          <div className="mt-6">
            {isUserScoped && !isGraduated ? (
              <UserGraduationForm
                actorUserId={scope.actorUserId}
                scopeLabel={scope.label}
                onSuccess={(graduatedAt) => setLocalGraduatedAt(graduatedAt)}
              />
            ) : !isUserScoped && !isGraduated ? (
              <div className="flex flex-wrap items-center gap-3">
                <Button asChild size="lg" className="gap-2">
                  <Link href={flipReviewHref}>
                    Request flip-review
                    <ArrowRight className="h-4 w-4" aria-hidden />
                  </Link>
                </Button>
                <Button asChild variant="outline" size="lg" className="gap-2">
                  <Link
                    href="https://docs.moltrace.co/guides/resources/white-papers/"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Technical paper §3.1
                    <ExternalLink className="h-4 w-4" aria-hidden />
                  </Link>
                </Button>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  )
}

// ── Inline form for the per-user POST ──────────────────────────────────
function UserGraduationForm({
  actorUserId,
  scopeLabel,
  onSuccess,
}: {
  actorUserId: number
  scopeLabel: string
  onSuccess: (graduatedAt: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const trimmed = reason.trim()
  const canSubmit = trimmed.length >= GRADUATION_REASON_MIN_LENGTH && !submitting

  if (!open) {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <Button size="lg" className="gap-2" onClick={() => setOpen(true)}>
          <GraduationCap className="h-4 w-4" aria-hidden />
          Graduate {scopeLabel} from experimental
        </Button>
        <Button asChild variant="outline" size="lg" className="gap-2">
          <Link
            href="https://docs.moltrace.co/guides/resources/white-papers/"
            target="_blank"
            rel="noopener noreferrer"
          >
            Technical paper §3.1
            <ExternalLink className="h-4 w-4" aria-hidden />
          </Link>
        </Button>
      </div>
    )
  }

  const handleSubmit: React.FormEventHandler<HTMLFormElement> = async (event) => {
    event.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    setError(null)
    try {
      const body: AdminUserGSDGraduationRequest = { graduated: true, reason: trimmed }
      const updated = await apiFetch<UserPublic>(
        `/admin/users/${actorUserId}/gsd-graduation`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        },
      )
      // Backend returns the updated UserPublic — read the canonical
      // gsd_graduated_at timestamp from the response rather than mint a
      // client-side one, so the displayed timestamp matches the audit
      // ledger entry that the backend just wrote.
      const graduatedAt = updated.gsd_graduated_at ?? new Date().toISOString()
      onSuccess(graduatedAt)
    } catch (err) {
      setError(String((err as { message?: string })?.message ?? err))
      setSubmitting(false)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-emerald-200 bg-background/70 p-4 dark:border-emerald-900"
      data-testid="graduate-user-form"
    >
      <div className="flex items-center gap-2">
        <GraduationCap className="h-4 w-4 text-emerald-700 dark:text-emerald-300" aria-hidden />
        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-700 dark:text-emerald-300">
          Graduate {scopeLabel} — required reason
        </p>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
        Every graduation is recorded in the audit ledger with the reason you provide. Be specific
        enough that a regulator could understand the decision later (validation metrics met,
        change-control reference, internal ticket ID).
      </p>
      <div className="mt-4">
        <Label htmlFor="gsd-graduation-reason" className="text-xs font-semibold">
          Reason <span className="text-rose-500">*</span>
        </Label>
        <Textarea
          id="gsd-graduation-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder={`e.g. Cleared validation gate per CC-2026-058; ${scopeLabel} has 642 calls in the trailing 90-day window with error rate 0.6% and solvent detect 96.3%.`}
          rows={3}
          required
          minLength={GRADUATION_REASON_MIN_LENGTH}
          disabled={submitting}
        />
        <p className="mt-1.5 text-[11px] text-muted-foreground">
          {trimmed.length < GRADUATION_REASON_MIN_LENGTH
            ? `${GRADUATION_REASON_MIN_LENGTH} characters minimum (${trimmed.length} so far).`
            : `${trimmed.length} characters.`}
        </p>
      </div>
      {error ? (
        <div className="mt-3 flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          <span>{error}</span>
        </div>
      ) : null}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={!canSubmit} className="gap-2">
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              Graduating…
            </>
          ) : (
            <>
              <GraduationCap className="h-4 w-4" aria-hidden />
              Confirm graduation
            </>
          )}
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            setOpen(false)
            setReason("")
            setError(null)
          }}
          disabled={submitting}
        >
          Cancel
        </Button>
      </div>
    </form>
  )
}

// ── blocked — reasons list with severity ───────────────────────────────
function Blocked({
  summary,
  scope,
  testId,
}: {
  summary: SpectrumGSDTelemetrySummary
  scope: VerdictScope
  testId: string
}) {
  const reasons = summary.flip_readiness_reasons ?? []
  return (
    <section
      data-testid={`${testId}-blocked`}
      className="rounded-2xl border border-rose-300 bg-rose-50 p-6 shadow-sm dark:border-rose-900 dark:bg-rose-950/30 sm:p-7"
    >
      <div className="flex items-start gap-4">
        <XCircle className="mt-0.5 h-7 w-7 shrink-0 text-rose-700 dark:text-rose-300" aria-hidden />
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-rose-700 dark:text-rose-300">
              Verdict · blocked
            </p>
            <ScopeChip scope={scope} />
          </div>
          <h2 className="mt-1 text-xl font-semibold tracking-tight sm:text-2xl">
            {scope.kind === "user"
              ? `${scope.label}: not ready to graduate.`
              : "Gate criteria not met. Do not flip the FE default."}
          </h2>
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-foreground/85">
            {scope.kind === "user" ? (
              <>
                One or more criteria failed for {scope.label} in the trailing{" "}
                {summary.window_days}-day window. The backend's reasons are the actionable list —
                each maps to a specific metric in the per-user telemetry panel.
              </>
            ) : (
              <>
                One or more criteria failed in the trailing {summary.window_days}-day window. The
                backend's reasons are the actionable list — each maps to a specific metric in the
                telemetry panel below.
              </>
            )}
          </p>
          {reasons.length > 0 ? (
            <ul className="mt-5 space-y-2">
              {reasons.map((r, idx) => (
                <li
                  key={idx}
                  className="flex items-start gap-3 rounded-xl border border-rose-200 bg-background/60 p-3 dark:border-rose-900"
                >
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-700 dark:text-rose-300" aria-hidden />
                  <span className="text-sm leading-relaxed text-foreground">{r}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm text-muted-foreground">
              No reasons returned. Inspect the telemetry panel below for the failing metric.
            </p>
          )}
          <p className="mt-5 font-mono text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
            Policy snapshot · invocations ≥{" "}
            {summary.flip_readiness_policy.min_invocations.toLocaleString()} · error rate ≤{" "}
            {(summary.flip_readiness_policy.max_error_rate * 100).toFixed(2)}% · solvent detect ≥{" "}
            {(summary.flip_readiness_policy.min_solvent_detect_rate * 100).toFixed(0)}%
          </p>
        </div>
      </div>
    </section>
  )
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-xl border bg-background/60 p-3">
      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 font-mono text-xl font-bold tabular-nums tracking-tight text-foreground">
        {value}
      </p>
      <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
        {sub}
      </p>
    </div>
  )
}
