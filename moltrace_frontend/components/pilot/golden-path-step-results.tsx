"use client"

// Golden Path — the per-step result renderers.
//
// Every renderer in this file reads the REAL response body of the endpoint its
// step called. None of them reads a `PilotRunStep`: the recorder's step
// summaries are canned literals, and rendering one as analysis output is what
// turns a demo into theatre.
//
// Two narration rules live here because this is where the words are:
//
//   • Step 2 is ranked candidate evidence. The deterministic verifier
//     (`verify_structure`) has no API route, so nothing on this page may say
//     "the verifier confirmed the structure".
//   • `human_review_required` is rendered, never styled away.

import Link from "next/link"
import { ExternalLink } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { statusLabel } from "@/lib/ui/status"
import { readRunRegulatorySummary } from "@/lib/reaction/regulatory-proposal"
import type {
  CandidateComparisonResult,
  DossierStepResult,
  FIDProcessResult,
  GoldenPathStepKey,
  ImpurityAssessResult,
  ReactionBoRun,
} from "@/lib/pilot/golden-path"

function isRecord(v: unknown): v is Record<string, unknown> {
  return v != null && typeof v === "object" && !Array.isArray(v)
}

function Facts({ rows }: { rows: { label: string; value: React.ReactNode }[] }) {
  return (
    <dl className="grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-sm">
      {rows.map((r) => (
        <div key={r.label} className="contents">
          <dt className="text-muted-foreground">{r.label}</dt>
          <dd className="min-w-0 font-medium tabular-nums">{r.value}</dd>
        </div>
      ))}
    </dl>
  )
}

function WarningList({ items, tone = "amber" }: { items: string[]; tone?: "amber" | "red" }) {
  if (items.length === 0) return null
  return (
    <ul
      className={cn(
        "space-y-1 rounded-md border p-2.5 text-xs",
        tone === "red"
          ? "border-red-500/40 bg-red-500/5"
          : "border-amber-500/40 bg-amber-500/5",
      )}
    >
      {items.map((w) => (
        <li key={w}>{w}</li>
      ))}
    </ul>
  )
}

/** Rendered on every regulatory result. Never collapsed, never styled away. */
function HumanReviewBadge({ required }: { required: boolean }) {
  if (!required) return null
  return (
    <Badge variant="outline" className="border-amber-500/50 text-amber-700 dark:text-amber-400">
      Human review required
    </Badge>
  )
}

// ── 1 · Raw FID → spectrum ────────────────────────────────────────────────────
function FidResult({ payload }: { payload: FIDProcessResult }) {
  const preview = payload.preview
  const analysis = payload.analysis
  return (
    <div className="space-y-3">
      <WarningList items={preview?.warnings ?? []} />
      <Facts
        rows={[
          { label: "Vendor format", value: preview?.format_detected ?? "—" },
          { label: "Data points", value: preview?.point_count?.toLocaleString() ?? "—" },
          { label: "Peaks parsed", value: analysis?.parsed_peak_count?.toLocaleString() ?? "—" },
          {
            label: "Proton inventory",
            value:
              analysis == null
                ? "—"
                : `${analysis.observed_total_h} observed / ${analysis.expected_total_h} expected`,
          },
          {
            label: "Consistency",
            value: analysis ? <Badge variant="outline">{statusLabel(analysis.label)}</Badge> : "—",
          },
        ]}
      />
      {analysis?.notes?.length ? (
        <ul className="space-y-1 text-xs text-muted-foreground">
          {analysis.notes.slice(0, 4).map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

// ── 2 · Spectrum → structure evidence ─────────────────────────────────────────
function CandidateEvidenceResult({ payload }: { payload: CandidateComparisonResult }) {
  const best = payload.best_candidate ?? null
  const ranked = payload.ranked_candidates ?? []
  return (
    <div className="space-y-3">
      <p className="rounded-md border bg-muted/20 p-2.5 text-xs text-muted-foreground">
        Candidates ranked against the observed spectrum. This is the evidence ranking, not a
        structure verdict — nothing here confirms a structure.
      </p>
      <WarningList items={payload.warnings ?? []} />
      <WarningList items={payload.ambiguity_alerts ?? []} />
      <Facts
        rows={[
          { label: "Candidates compared", value: payload.candidate_count?.toLocaleString() ?? "—" },
          {
            label: "Best supported",
            value: best ? (
              <span className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{best.name ?? best.smiles}</span>
                <Badge variant="outline">{statusLabel(best.label)}</Badge>
                <span className="text-muted-foreground">score {best.total_score.toFixed(2)}</span>
              </span>
            ) : (
              "No candidate was best-supported"
            ),
          },
          {
            label: "Evidence layers",
            value: (payload.evidence_layers_used ?? []).join(", ") || "—",
          },
        ]}
      />
      {ranked.length > 1 ? (
        <ol className="space-y-1 text-xs">
          {ranked.slice(0, 5).map((c) => (
            <li key={`${c.rank}-${c.smiles}`} className="flex items-center gap-2">
              <span className="w-5 shrink-0 text-muted-foreground tabular-nums">{c.rank}.</span>
              <span className="min-w-0 flex-1 truncate">{c.name ?? c.smiles}</span>
              <span className="shrink-0 text-muted-foreground tabular-nums">
                {c.total_score.toFixed(2)}
              </span>
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  )
}

// ── 3 · Impurity assessment ───────────────────────────────────────────────────
function ImpurityResult({ payload }: { payload: ImpurityAssessResult }) {
  const t = payload.thresholds
  const versions = Object.entries(payload.rule_set_versions ?? {})
  return (
    <div className="space-y-3">
      <WarningList items={payload.warnings ?? []} />
      <div className="flex flex-wrap items-center gap-2">
        <HumanReviewBadge required={payload.human_review_required !== false} />
        {versions.map(([name, version]) => (
          <Badge key={name} variant="secondary" className="font-mono text-[10px]">
            {name} {version}
          </Badge>
        ))}
      </div>
      <Facts
        rows={[
          { label: "Reporting threshold", value: `${t.reporting_percent}%` },
          { label: "Identification threshold", value: `${t.identification_percent}%` },
          { label: "Qualification threshold", value: `${t.qualification_percent}%` },
          { label: "Basis", value: <span className="font-normal">{t.regulatory_basis}</span> },
          { label: "Table", value: <span className="font-normal">{t.table_reference}</span> },
        ]}
      />
      {payload.disclaimer ? (
        <p className="text-xs italic text-muted-foreground">{payload.disclaimer}</p>
      ) : null}
    </div>
  )
}

// ── 4 · Compliant design ──────────────────────────────────────────────────────
function BoRunResult({ payload }: { payload: ReactionBoRun }) {
  const summary = readRunRegulatorySummary(payload)
  const declined = payload.status === "requires_review" || (summary.feasibilityKnown && (summary.feasibleCount ?? 0) === 0)

  return (
    <div className="space-y-3">
      {/* The unchecked-limits caveat goes ABOVE the figures it qualifies. */}
      {summary.uncheckedWarning ? <WarningList items={[summary.uncheckedWarning]} /> : null}
      <WarningList items={summary.otherWarnings} />

      {declined ? (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
          <div className="font-medium">The optimizer declined to recommend.</div>
          <p className="mt-1 text-xs text-muted-foreground">
            Every proposal it scored breached a hard regulatory limit, so this run is returned for
            review rather than presented as a recommendation.
          </p>
        </div>
      ) : null}

      <Facts
        rows={[
          {
            label: "Run outcome",
            value: (
              <Badge
                variant="outline"
                className={cn(
                  declined && "border-amber-500/50 text-amber-700 dark:text-amber-400",
                )}
              >
                {statusLabel(payload.status)}
              </Badge>
            ),
          },
          {
            label: "Proposals within limits",
            // Absent means unknown, never "nothing was blocked".
            value: summary.feasibilityKnown ? (summary.feasibleCount ?? 0).toLocaleString() : "Not recorded",
          },
          { label: "Proposals blocked by a limit", value: summary.blockedCount.toLocaleString() },
          { label: "Experiments used as input", value: payload.input_experiment_count?.toLocaleString() ?? "—" },
        ]}
      />
    </div>
  )
}

// ── 5 · Dossier + provenance ──────────────────────────────────────────────────
function DossierResult({ payload }: { payload: DossierStepResult }) {
  const { dossier, links } = payload
  return (
    <div className="space-y-3">
      <Facts
        rows={[
          {
            label: "Dossier",
            value: (
              <Link
                href={`/regulatory/dossiers/${dossier.id}`}
                className="inline-flex items-center gap-1 underline underline-offset-4 hover:text-foreground"
              >
                {dossier.title}
                <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
              </Link>
            ),
          },
          { label: "State", value: <Badge variant="outline">{statusLabel(dossier.status)}</Badge> },
          { label: "Evidence links", value: links.length.toLocaleString() },
        ]}
      />
      {links.length > 0 ? (
        <ul className="space-y-1 text-xs">
          {links.map((l) => (
            <li key={l.id} className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/20 p-2">
              <span className="font-medium">{l.title}</span>
              <Badge variant="outline" className="text-[10px]">
                {statusLabel(l.status)}
              </Badge>
              <span className="min-w-0 flex-1 text-muted-foreground">{l.summary}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">
          No evidence was linked, so this dossier does not yet carry the arc&rsquo;s provenance.
        </p>
      )}
    </div>
  )
}

/** Dispatch on the step, rendering that endpoint's real response body. */
export function GoldenPathStepResult({
  stepKey,
  payload,
}: {
  stepKey: GoldenPathStepKey
  payload: unknown
}) {
  if (payload == null) return null
  switch (stepKey) {
    case "raw_fid_process":
      return <FidResult payload={payload as FIDProcessResult} />
    case "candidate_evidence":
      return <CandidateEvidenceResult payload={payload as CandidateComparisonResult} />
    case "impurity_assess":
      return <ImpurityResult payload={payload as ImpurityAssessResult} />
    case "bo_run":
      return <BoRunResult payload={payload as ReactionBoRun} />
    case "dossier_evidence":
      return isRecord(payload) && isRecord(payload.dossier) ? (
        <DossierResult payload={payload as DossierStepResult} />
      ) : null
    default:
      return null
  }
}
