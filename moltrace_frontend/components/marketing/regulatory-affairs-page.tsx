import Link from "next/link"
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  BookOpenCheck,
  CheckCircle2,
  Database,
  FileCheck,
  FileSignature,
  FileText,
  Globe,
  GitBranch,
  Landmark,
  Lock,
  MessagesSquare,
  Microscope,
  PlayCircle,
  RefreshCw,
  ScrollText,
  Search,
  ShieldCheck,
  Sparkles,
  Workflow,
  XCircle,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Footer } from "@/components/marketing/footer"
import { Header } from "@/components/marketing/header"

/**
 * Regulatory Affairs solution page — full marketing-shell route at
 * /regulatory-affairs. Fourth of the four "Solutions" header pages.
 *
 * IMPORTANT — this is the PERSONA page, deliberately distinct from the
 * ComplianceCore MODULE page (/regulatory-hub):
 *   - /regulatory-hub answers "how does the module work?" — its
 *     Map→Classify→Assess→Cite→Compose→Sign→Ledger pipeline, the
 *     frameworks matrix, the anatomy of an ALCOA+ ledger entry.
 *   - /regulatory-affairs answers "what does MolTrace do for a
 *     regulatory affairs / submission professional?" — the submission
 *     lifecycle, multi-jurisdiction packaging, health-authority query
 *     response, staying current with guidance, and inspection readiness.
 *   This page cross-links prominently INTO /regulatory-hub as the module
 *   the RA team lives in.
 *
 * Distinct visual identity vs every other page:
 *   - Blue hero badge (Pharma=indigo, Academic=rose, CRO=orange,
 *     Spectroscopy=emerald, ComplianceCore=cyan, ReactionIQ=violet,
 *     Integrations=amber).
 *   - Hero visual is a live SUBMISSION / CTD-dossier checklist card with
 *     jurisdiction chips — not the module page's audit-ledger event.
 *
 * All content grounded in real MolTrace capabilities: ICH-aware
 * classification, CTD dossier-section composition, the FDA Jan 2025 AI
 * framework + EMA reflection paper alignment, ALCOA+ ledger (nine
 * fields), 21 CFR Part 11, recipe-hash reproducibility, regulatory
 * surveillance, human signoff gate.
 */

type Stage = {
  code: string
  name: string
  fits: string[]
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties; "aria-hidden"?: boolean }>
}

const STAGES: Stage[] = [
  {
    code: "INTAKE",
    name: "Evidence intake",
    icon: Microscope,
    fits: [
      "Findings arrive from R&D and CRO partners as structured evidence",
      "Every claim already carries its trail back to the raw spectrum",
      "No re-keying numbers out of PDFs into a submission spreadsheet",
    ],
  },
  {
    code: "ASSESS",
    name: "Classification & assessment",
    icon: ShieldCheck,
    fits: [
      "Findings mapped to ICH Q3A/Q3B/Q3C/Q3D and M7 frameworks",
      "Risk-based credibility + FDA Stage 1-4 oversight gates evaluated",
      "Items needing human review surface with the exact gate that fired",
    ],
  },
  {
    code: "AUTHOR",
    name: "Dossier authoring",
    icon: FileSignature,
    fits: [
      "CTD section drafts composed from the underlying evidence",
      "Module 3.2.S.3.2, 3.2.S.4, 3.2.P.5 + AI/ML model documentation",
      "Every numerical claim hyperlinked to its source — no orphan numbers",
    ],
  },
  {
    code: "PACKAGE",
    name: "Multi-jurisdiction packaging",
    icon: Globe,
    fits: [
      "Reuse one evidence base across FDA, EMA, PMDA, and Health Canada",
      "Regional templates + dossier-section mapping kept aligned to CTD",
      "Jurisdiction-specific content gated until the framework is verified",
    ],
  },
  {
    code: "MAINTAIN",
    name: "Query response & lifecycle",
    icon: RefreshCw,
    fits: [
      "Answer a health-authority query by retrieving the cited evidence chain",
      "Surveillance watches guidance sources and routes changes to your items",
      "ALCOA+ ledger keeps the whole submission inspection-ready over its life",
    ],
  },
]

type Pain = {
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties; "aria-hidden"?: boolean }>
  title: string
  body: string
}

const PRESSURES: Pain[] = [
  {
    icon: FileText,
    title: "The submission is hand-reconciled",
    body: "The bridge from a final interpretation to a regulatory argument is, in most orgs, invisible by default. RA spends weeks reconciling a narrative against the raw evidence that R&D and the CROs produced.",
  },
  {
    icon: RefreshCw,
    title: "The guidance keeps moving",
    body: "ICH Q2(R2), the FDA's January 2025 AI framework, the EMA reflection paper, nitrosamine expectations, and pharmacopoeia versions all shift — often at once. Keeping every affected item current is a job in itself.",
  },
  {
    icon: MessagesSquare,
    title: "Queries arrive with a clock",
    body: "A health-authority deficiency letter needs an evidence-backed answer fast. Reassembling the trail for one claim — across files, emails, and people — is exactly the work that eats the response window.",
  },
  {
    icon: BadgeCheck,
    title: "You own data integrity",
    body: "When an inspector arrives, RA owns the ALCOA+ story for the whole organization. 'We can reconstruct it' is not the same as 'it's queryable right now' — and only one of those survives the audit.",
  },
]

type UseCase = {
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties; "aria-hidden"?: boolean }>
  name: string
  blurb: string
  inputs: string
  outputs: string
}

const WORKFLOWS: UseCase[] = [
  {
    icon: FileSignature,
    name: "CTD dossier-section drafting",
    blurb:
      "Draft Module 3 sections — 3.2.S.3.2 Impurities, 3.2.S.4 Control of Drug Substance, 3.2.P.5 Control of Drug Product — directly from the evidence, each claim cited to source.",
    inputs: "Structured evidence · framework refs",
    outputs: "CTD drafts · citation chain · open items",
  },
  {
    icon: AlertTriangle,
    name: "Impurity & nitrosamine packaging",
    blurb:
      "Assemble the impurity argument: Q3A/Q3B organic, Q3C residual solvent, Q3D elemental, and M7 mutagenic + nitrosamine risk, each with acceptance windows and the data behind them.",
    inputs: "Classified findings · pharmacopoeia priors",
    outputs: "Impurity dossier · risk tier · recommendations",
  },
  {
    icon: ScrollText,
    name: "AI / ML model documentation",
    blurb:
      "Produce the FDA January-2025 model-card package: training-data lineage, performance bounds, validation corpus, intended use, and known limitations — Stage 1-4 ready.",
    inputs: "Model artefacts · validation runs · changelogs",
    outputs: "Model documentation · Stage mapping · audit trail",
  },
  {
    icon: Globe,
    name: "Multi-jurisdiction management",
    blurb:
      "Run one evidence base into multiple regional submissions. Shared content stays in sync; jurisdiction-specific sections are gated until the corresponding framework content is verified.",
    inputs: "Core dossier · regional templates",
    outputs: "Per-jurisdiction package · alignment report",
  },
  {
    icon: MessagesSquare,
    name: "Health-authority query response",
    blurb:
      "Answer a deficiency letter by pulling the exact citation chain for the claim in question — spectrum, peak, reference window, reviewer — instead of reconstructing it from scratch.",
    inputs: "Query · claim reference",
    outputs: "Evidence chain · drafted response · ledger entry",
  },
  {
    icon: BookOpenCheck,
    name: "Surveillance & change impact",
    blurb:
      "Watch ICH, FDA, EMA, and pharmacopoeia sources for version changes, and auto-route the impact to the affected dossiers, rules, and action items with an ETA.",
    inputs: "Source feeds · pharmacopoeia versions",
    outputs: "Change-impact report · routed items · ETA",
  },
]

type Outcome = {
  value: string
  label: string
  detail: string
}

const OUTCOMES: Outcome[] = [
  {
    value: "9",
    label: "ALCOA+ fields per event",
    detail:
      "Attributable · Legible · Contemporaneous · Original · Accurate · Complete · Consistent · Enduring · Available — populated on every audit event, queryable by an inspector.",
  },
  {
    value: "40",
    label: "Evidence layers per claim",
    detail:
      "Every regulatory claim rests on a typed, additive evidence stack — so a citation chain goes all the way down to the spectrum it came from.",
  },
  {
    value: "Bit-identical",
    label: "Recipe-hash replay",
    detail:
      "Re-derive any processed result or report from any prior date with byte-for-byte identical output — the reproducibility ICH Q2(R2) now expects.",
  },
  {
    value: "94.4%",
    label: "Solvent auto-detect",
    detail:
      "Residual-solvent peaks identified automatically and routed straight into ICH Q3C classification — the impurity argument starts itself.",
  },
]

type Comparison = {
  dimension: string
  before: string
  after: string
}

const COMPARISON: Comparison[] = [
  {
    dimension: "Assembling a CTD section",
    before: "Hand-written narrative; numbers re-keyed from R&D and CRO reports",
    after: "Draft composed from the evidence, each claim hyperlinked to its source",
  },
  {
    dimension: "Reconciling narrative vs raw evidence",
    before: "Weeks of cross-referencing in week 11, often by a single reviewer",
    after: "The dossier is a by-product of the science — the reconciliation never happens",
  },
  {
    dimension: "Responding to a health-authority query",
    before: "Reassemble the trail for one claim from files, emails, and memory",
    after: "Pull the citation chain for that exact claim in one query",
  },
  {
    dimension: "Staying current with guidance",
    before: "Manual scan of new guidance; spot-check which dossiers are affected",
    after: "Surveillance routes each change to the affected items with an ETA",
  },
  {
    dimension: "Proving data integrity at inspection",
    before: "Reconstruct an audit trail from version history and interviews",
    after: "One ALCOA+ ledger query — nine fields per event, replayable on demand",
  },
  {
    dimension: "Reusing a submission across jurisdictions",
    before: "Re-derive each regional package by hand; content drifts apart",
    after: "One evidence base; shared content stays in sync, regional gated until verified",
  },
]

type LoopStep = {
  step: string
  body: string
}

const WORKED_EXAMPLE: LoopStep[] = [
  {
    step: "Evidence arrives",
    body: "A residual-solvent finding comes from R&D as a structured evidence object — acetic acid at 2.10 ppm, 93% confidence, already cited back to the raw FID and the HRMS that corroborated it.",
  },
  {
    step: "It classifies itself",
    body: "ComplianceCore maps it to ICH Q3C Class 3 (no action below 5000 ppm) and slots it into dossier section 3.2.S.3.2 with the reference shift, observed shift, and delta cited.",
  },
  {
    step: "The section drafts",
    body: "The CTD draft is composed from the evidence and packaged for FDA and EMA from the same base — shared content in sync, regional content gated until the framework is verified.",
  },
  {
    step: "An inspector asks",
    body: "Months later a reviewer questions the impurity claim. One ALCOA+ ledger query returns the full chain — FID hash, recipe, classification, signoff — and replays bit-identical.",
  },
]

type TrustPillar = {
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties; "aria-hidden"?: boolean }>
  title: string
  body: string
}

const TRUST: TrustPillar[] = [
  {
    icon: BadgeCheck,
    title: "ALCOA+ audit ledger",
    body: "Every event carries all nine ALCOA+ fields. Inspectors query directly — no reconstruction from emails and version history.",
  },
  {
    icon: FileCheck,
    title: "21 CFR Part 11 alignment",
    body: "Electronic-records and electronic-signature requirements are built into the audit-event model, not bolted on for show.",
  },
  {
    icon: FileSignature,
    title: "Human signoff gate",
    body: "No submission artefact is released without explicit qualified-human attribution — the FDA Stage 4 oversight gate, enforced in code.",
  },
  {
    icon: GitBranch,
    title: "Recipe-hash provenance",
    body: "Every processing run links a recipe hash to the unchanged raw archive, so any claim in the dossier replays bit-identical years later.",
  },
  {
    icon: Database,
    title: "Immutable raw vault",
    body: "The original evidence behind every regulatory claim is SHA-256 hashed and never overwritten — provenance that survives the product lifecycle.",
  },
  {
    icon: Lock,
    title: "Tenant isolation & residency",
    body: "Per-tenant isolation, GDPR-compliant data residency, and SOC 2 Type II controls underpin the whole submission record.",
  },
]

export function RegulatoryAffairsPage() {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main>
        {/* ── Hero ────────────────────────────────────────────────────────── */}
        <section className="relative overflow-hidden border-b">
          <div
            aria-hidden
            className="absolute inset-x-0 top-0 h-px"
            style={{
              background:
                "linear-gradient(90deg, transparent 0%, var(--mt-teal) 25%, var(--mt-teal) 75%, transparent 100%)",
              opacity: 0.5,
            }}
          />
          <div aria-hidden className="scientific-grid-subtle absolute inset-0 opacity-30" />
          <div className="relative mx-auto max-w-7xl px-5 py-20 sm:px-6 lg:px-8 lg:py-24">
            <div className="grid gap-12 lg:grid-cols-[1.2fr_1fr] lg:items-center">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge
                    variant="outline"
                    className="border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-900 dark:bg-blue-950/40 dark:text-blue-300"
                  >
                    <FileCheck className="mr-1 h-3 w-3" aria-hidden />
                    Solution · Regulatory Affairs
                  </Badge>
                  <Badge variant="outline" className="text-muted-foreground">
                    Dossier · Submission · Inspection
                  </Badge>
                </div>
                <h1 className="mt-5 max-w-3xl text-4xl font-semibold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl">
                  Submissions that{" "}
                  <span style={{ color: "var(--mt-teal)" }}>assemble themselves</span> from the
                  evidence.
                </h1>
                <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted-foreground sm:text-xl">
                  MolTrace turns structured scientific evidence into CTD dossier sections,
                  multi-jurisdiction packages, and inspection-ready ledger entries. The regulatory
                  work becomes the output of the science — not a parallel document reconciled by hand
                  in week eleven.
                </p>
                <div className="mt-10 flex flex-wrap items-center gap-4">
                  <Button asChild size="lg" className="gap-2">
                    <Link href="/contact?reason=Regulatory%20Affairs">
                      Request a demo
                      <ArrowRight className="h-4 w-4" />
                    </Link>
                  </Button>
                  <Button asChild size="lg" variant="outline" className="gap-2">
                    <Link href="/regulatory">
                      Open ComplianceCore
                      <PlayCircle className="h-4 w-4" />
                    </Link>
                  </Button>
                </div>
              </div>

              {/* Hero visual — submission / CTD-dossier checklist card */}
              <aside className="relative overflow-hidden rounded-3xl border bg-card p-6 shadow-sm">
                <div className="flex items-center justify-between">
                  <p
                    className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                    style={{ color: "var(--mt-teal)" }}
                  >
                    Submission package · live
                  </p>
                  <span
                    className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.14em]"
                    style={{
                      borderColor: "color-mix(in oklab, var(--mt-teal) 30%, transparent)",
                      backgroundColor: "var(--mt-teal-soft)",
                      color: "var(--mt-teal)",
                    }}
                  >
                    <span
                      className="h-1.5 w-1.5 rounded-full"
                      style={{ backgroundColor: "var(--mt-teal)" }}
                      aria-hidden
                    />
                    Inspection-ready
                  </span>
                </div>
                <p className="mt-3 font-mono text-xs text-muted-foreground">
                  dossier · MAA-2026 · CTD Module 3
                </p>

                {/* jurisdiction chips */}
                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  <Landmark className="h-3.5 w-3.5" style={{ color: "var(--mt-teal)" }} aria-hidden />
                  {["FDA", "EMA", "PMDA"].map((j) => (
                    <span
                      key={j}
                      className="inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.12em]"
                      style={{
                        borderColor: "color-mix(in oklab, var(--mt-teal) 25%, transparent)",
                        color: "var(--mt-teal)",
                      }}
                    >
                      {j}
                    </span>
                  ))}
                </div>

                <div className="mt-6 space-y-1.5">
                  {[
                    { sec: "3.2.S.3.2", title: "Impurities · cited", state: "done" },
                    { sec: "3.2.S.4", title: "Control of drug substance", state: "done" },
                    { sec: "3.2.P.5", title: "Control of drug product", state: "done" },
                    { sec: "M7", title: "Nitrosamine risk · assessed", state: "done" },
                    { sec: "AI/ML", title: "Model documentation · attached", state: "active" },
                    { sec: "Mod 1", title: "Regional admin · per region", state: "queued" },
                  ].map((row) => (
                    <div
                      key={row.sec}
                      className="flex items-center gap-3 rounded-md border bg-background/80 px-3 py-2"
                    >
                      <span
                        className="inline-flex h-5 min-w-[3.5rem] shrink-0 items-center justify-center rounded px-1 font-mono text-[9px] font-bold"
                        style={{
                          backgroundColor: "var(--mt-teal-soft)",
                          color: "var(--mt-teal)",
                        }}
                      >
                        {row.sec}
                      </span>
                      <span className="flex-1 truncate text-xs">{row.title}</span>
                      {row.state === "done" ? (
                        <CheckCircle2
                          className="h-3.5 w-3.5 shrink-0"
                          style={{ color: "var(--mt-teal)" }}
                          aria-label="complete"
                        />
                      ) : row.state === "active" ? (
                        <span
                          className="h-2 w-2 shrink-0 animate-pulse rounded-full"
                          style={{ backgroundColor: "var(--mt-teal)" }}
                          aria-label="in progress"
                        />
                      ) : (
                        <span
                          className="h-2 w-2 shrink-0 rounded-full border"
                          style={{ borderColor: "color-mix(in oklab, var(--mt-teal) 40%, transparent)" }}
                          aria-label="queued"
                        />
                      )}
                    </div>
                  ))}
                </div>
                <p className="mt-5 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                  every section traces to its source evidence
                </p>
              </aside>
            </div>
          </div>
        </section>

        {/* ── The pressure ────────────────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Why regulatory affairs
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Four things that make submissions hard.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                RA sits between the science and the agency. The job is reconciliation, currency,
                responsiveness, and integrity — usually against a deadline, and usually with the
                evidence scattered across teams and tools.
              </p>
            </div>
            <div className="mt-12 grid gap-6 sm:grid-cols-2">
              {PRESSURES.map((p) => {
                const Icon = p.icon
                return (
                  <article
                    key={p.title}
                    className="rounded-2xl border bg-card p-6 shadow-sm sm:p-7"
                    style={{ borderLeft: "3px solid var(--mt-teal)" }}
                  >
                    <div className="flex items-start gap-4">
                      <span
                        className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl"
                        style={{ backgroundColor: "var(--mt-teal-soft)", color: "var(--mt-teal)" }}
                      >
                        <Icon className="h-5 w-5" aria-hidden />
                      </span>
                      <div>
                        <h3 className="text-lg font-semibold tracking-tight">{p.title}</h3>
                        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                          {p.body}
                        </p>
                      </div>
                    </div>
                  </article>
                )
              })}
            </div>
          </div>
        </section>

        {/* ── Across the submission lifecycle ──────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Across the submission lifecycle
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                From evidence intake to lifecycle maintenance.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                The same evidence object that R&amp;D and your CRO partners produced flows through
                classification, authoring, and packaging — and stays inspection-ready for the life of
                the product.
              </p>
            </div>

            <div className="mt-12 overflow-hidden rounded-2xl border bg-card">
              <div className="border-b bg-muted/40 px-4 py-2.5">
                <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
                  The lifecycle, at a glance
                </p>
              </div>
              <pre className="overflow-x-auto px-4 py-5 font-mono text-[11px] leading-relaxed text-foreground sm:px-8 sm:text-xs">
{`  Intake ──► Assess ──► Author ──► Package ──► Maintain
     │          │          │           │           │
     ▼          ▼          ▼           ▼           ▼
  cited       ICH +      CTD draft   FDA · EMA   query response
  evidence    risk +     per claim   · PMDA      + surveillance
  (from R&D   FDA Stage  (3.2.S/P)   (one base)  + ALCOA+ ledger
   / CRO)     gates                              (inspection-ready)`}
              </pre>
            </div>

            <div className="mt-8 grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
              {STAGES.map((stage) => {
                const Icon = stage.icon
                return (
                  <article
                    key={stage.code}
                    className="flex flex-col rounded-2xl border bg-card p-6 shadow-sm"
                    style={{ borderTop: "3px solid var(--mt-teal)" }}
                  >
                    <div className="flex items-center gap-3">
                      <span
                        className="inline-flex h-11 w-11 items-center justify-center rounded-xl"
                        style={{ backgroundColor: "var(--mt-teal-soft)", color: "var(--mt-teal)" }}
                      >
                        <Icon className="h-5 w-5" aria-hidden />
                      </span>
                      <div>
                        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">
                          {stage.code}
                        </p>
                        <h3 className="text-base font-semibold tracking-tight">{stage.name}</h3>
                      </div>
                    </div>
                    <ul className="mt-5 space-y-2">
                      {stage.fits.map((fit) => (
                        <li
                          key={fit}
                          className="flex items-start gap-2.5 text-sm leading-relaxed text-muted-foreground"
                        >
                          <CheckCircle2
                            className="mt-0.5 h-3.5 w-3.5 shrink-0"
                            style={{ color: "var(--mt-teal)" }}
                            aria-hidden
                          />
                          <span>{fit}</span>
                        </li>
                      ))}
                    </ul>
                  </article>
                )
              })}
            </div>
          </div>
        </section>

        {/* ── Workflows ───────────────────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Workflows we light up
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Six regulatory workflows, with their inputs and outputs.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Each is a typed pipeline that ships today. Inputs arrive as structured evidence from
                the science; outputs are dossier-ready artefacts, every one cited and ledger-backed.
              </p>
            </div>
            <div className="mt-12 grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
              {WORKFLOWS.map((u) => {
                const Icon = u.icon
                return (
                  <article
                    key={u.name}
                    className="flex flex-col rounded-2xl border bg-card p-6 shadow-sm"
                    style={{ borderTop: "3px solid var(--mt-teal)" }}
                  >
                    <span
                      className="inline-flex h-11 w-11 items-center justify-center rounded-xl"
                      style={{ backgroundColor: "var(--mt-teal-soft)", color: "var(--mt-teal)" }}
                    >
                      <Icon className="h-5 w-5" aria-hidden />
                    </span>
                    <h3 className="mt-4 text-base font-semibold tracking-tight">{u.name}</h3>
                    <p className="mt-2 flex-1 text-sm leading-relaxed text-muted-foreground">
                      {u.blurb}
                    </p>
                    <div className="mt-5 space-y-2 border-t pt-4">
                      <div>
                        <p className="font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground">
                          Inputs
                        </p>
                        <p className="mt-0.5 font-mono text-[11px] text-foreground">{u.inputs}</p>
                      </div>
                      <div>
                        <p className="font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground">
                          Outputs
                        </p>
                        <p className="mt-0.5 font-mono text-[11px] text-foreground">{u.outputs}</p>
                      </div>
                    </div>
                  </article>
                )
              })}
            </div>
          </div>
        </section>

        {/* ── Outcomes / numbers ──────────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Measured, not claimed
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                The numbers behind a defensible submission.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Every figure below is implemented in production code or reproducible from a
                publicly-described corpus. Provenance isn't a promise here — it's the data model.
              </p>
            </div>
            <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {OUTCOMES.map((o) => (
                <div
                  key={o.label}
                  className="rounded-2xl border bg-card p-6 shadow-sm"
                  style={{ borderTop: "3px solid var(--mt-teal)" }}
                >
                  <p
                    className="font-mono text-3xl font-bold tabular-nums tracking-tight sm:text-4xl"
                    style={{ color: "var(--mt-teal)" }}
                  >
                    {o.value}
                  </p>
                  <p className="mt-2 font-mono text-[10px] font-bold uppercase tracking-[0.18em]">
                    {o.label}
                  </p>
                  <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{o.detail}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Before / after comparison ───────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                The honest comparison
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                What changes for a submission team.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Most RA teams run on documents, spreadsheets, and email threads that get reconciled
                under deadline. Here's what flips when the evidence — and its provenance — flows into
                the dossier directly.
              </p>
            </div>
            <div className="mt-12 overflow-x-auto rounded-2xl border bg-card shadow-sm">
              <table className="w-full text-left text-sm">
                <thead className="bg-muted/40 font-mono uppercase tracking-[0.12em] text-[10px] text-muted-foreground">
                  <tr>
                    <th className="px-5 py-3">Dimension</th>
                    <th className="px-5 py-3">Today</th>
                    <th className="px-5 py-3">With MolTrace</th>
                  </tr>
                </thead>
                <tbody>
                  {COMPARISON.map((row, idx) => (
                    <tr
                      key={row.dimension}
                      className={idx % 2 === 0 ? "border-t" : "border-t bg-muted/20"}
                    >
                      <td className="px-5 py-3.5 align-top text-sm font-semibold text-foreground">
                        {row.dimension}
                      </td>
                      <td className="px-5 py-3.5 align-top text-xs leading-relaxed text-muted-foreground">
                        <span className="mb-1 inline-flex items-center gap-1.5 rounded-full border border-rose-200 bg-rose-50 px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
                          <XCircle className="h-2.5 w-2.5" aria-hidden />
                          today
                        </span>
                        <p>{row.before}</p>
                      </td>
                      <td className="px-5 py-3.5 align-top text-xs leading-relaxed text-foreground">
                        <span className="mb-1 inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300">
                          <CheckCircle2 className="h-2.5 w-2.5" aria-hidden />
                          with MolTrace
                        </span>
                        <p>{row.after}</p>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* ── Worked example loop ─────────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                One worked example
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                A finding, from evidence to inspection answer.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                A single residual-solvent finding followed from R&amp;D into a multi-jurisdiction
                dossier — and answered cleanly when a reviewer asks about it years later.
              </p>
            </div>
            <ol className="mt-12 grid gap-4 lg:grid-cols-4">
              {WORKED_EXAMPLE.map((step, idx) => (
                <li
                  key={step.step}
                  className="relative flex flex-col rounded-2xl border bg-card p-6 shadow-sm sm:p-7"
                  style={{ borderTop: "3px solid var(--mt-teal)" }}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="inline-flex h-7 w-7 items-center justify-center rounded-full font-mono text-[11px] font-bold tabular-nums"
                      style={{ backgroundColor: "var(--mt-teal-soft)", color: "var(--mt-teal)" }}
                      aria-hidden
                    >
                      {idx + 1}
                    </span>
                    <h3 className="text-base font-semibold tracking-tight">{step.step}</h3>
                  </div>
                  <p className="mt-4 flex-1 text-sm leading-relaxed text-muted-foreground">
                    {step.body}
                  </p>
                </li>
              ))}
            </ol>

            {/* Module cross-links */}
            <div className="mt-10 grid gap-4 sm:grid-cols-3">
              <Link
                href="/regulatory-hub"
                className="group flex items-center justify-between gap-4 rounded-2xl border bg-card p-5 transition-all hover:-translate-y-0.5 hover:shadow-md"
              >
                <div className="flex items-start gap-3">
                  <ShieldCheck
                    className="mt-0.5 h-5 w-5 shrink-0"
                    style={{ color: "var(--mt-teal)" }}
                    aria-hidden
                  />
                  <div>
                    <p className="text-sm font-semibold">ComplianceCore →</p>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      The module you'll live in — pipeline, frameworks, and the ALCOA+ ledger.
                    </p>
                  </div>
                </div>
                <ArrowRight
                  className="h-4 w-4 shrink-0 transition-transform group-hover:translate-x-0.5"
                  style={{ color: "var(--mt-teal)" }}
                  aria-hidden
                />
              </Link>
              <Link
                href="/spectroscopy"
                className="group flex items-center justify-between gap-4 rounded-2xl border bg-card p-5 transition-all hover:-translate-y-0.5 hover:shadow-md"
              >
                <div className="flex items-start gap-3">
                  <Microscope
                    className="mt-0.5 h-5 w-5 shrink-0"
                    style={{ color: "var(--mt-teal)" }}
                    aria-hidden
                  />
                  <div>
                    <p className="text-sm font-semibold">Spectroscopy →</p>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      The evidence engine that produces every finding you'll submit.
                    </p>
                  </div>
                </div>
                <ArrowRight
                  className="h-4 w-4 shrink-0 transition-transform group-hover:translate-x-0.5"
                  style={{ color: "var(--mt-teal)" }}
                  aria-hidden
                />
              </Link>
              <Link
                href="/pharmaceutical-rd"
                className="group flex items-center justify-between gap-4 rounded-2xl border bg-card p-5 transition-all hover:-translate-y-0.5 hover:shadow-md"
              >
                <div className="flex items-start gap-3">
                  <Search
                    className="mt-0.5 h-5 w-5 shrink-0"
                    style={{ color: "var(--mt-teal)" }}
                    aria-hidden
                  />
                  <div>
                    <p className="text-sm font-semibold">Pharmaceutical R&amp;D →</p>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      Where the evidence originates, already cited back to the raw data.
                    </p>
                  </div>
                </div>
                <ArrowRight
                  className="h-4 w-4 shrink-0 transition-transform group-hover:translate-x-0.5"
                  style={{ color: "var(--mt-teal)" }}
                  aria-hidden
                />
              </Link>
            </div>
          </div>
        </section>

        {/* ── Trust + data integrity ──────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="grid gap-10 lg:grid-cols-[1fr_1.6fr]">
              <div>
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                  style={{ color: "var(--mt-teal)" }}
                >
                  Built for inspection
                </p>
                <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                  Data integrity you can hand to an inspector.
                </h2>
                <p className="mt-4 text-base text-muted-foreground">
                  Every control below is implemented in production code — designed against ICH
                  Q2(R2) ALCOA+, the FDA's January 2025 AI framework, the EMA reflection paper, and
                  21 CFR Part 11 from day one. Not compliance theater; the data model itself.
                </p>
              </div>
              <ul className="space-y-3">
                {TRUST.map((item) => {
                  const Icon = item.icon
                  return (
                    <li
                      key={item.title}
                      className="flex items-start gap-3.5 rounded-xl border bg-card p-4 sm:p-5"
                    >
                      <Icon
                        className="mt-0.5 h-5 w-5 shrink-0"
                        style={{ color: "var(--mt-teal)" }}
                        aria-hidden
                      />
                      <div>
                        <p className="text-sm font-semibold tracking-tight">{item.title}</p>
                        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                          {item.body}
                        </p>
                      </div>
                    </li>
                  )
                })}
              </ul>
            </div>
          </div>
        </section>

        {/* ── CTA ────────────────────────────────────────────────────────── */}
        <section className="relative overflow-hidden">
          <div aria-hidden className="scientific-grid-subtle absolute inset-0 opacity-30" />
          <div className="relative mx-auto max-w-7xl px-5 py-20 sm:px-6 lg:px-8 lg:py-28">
            <div className="mx-auto max-w-3xl text-center">
              <Sparkles className="mx-auto h-10 w-10" style={{ color: "var(--mt-teal)" }} aria-hidden />
              <h2 className="mt-6 text-3xl font-semibold tracking-tight sm:text-4xl">
                Bring your hardest submission section.
              </h2>
              <p className="mt-4 text-base text-muted-foreground sm:text-lg">
                Pick a CTD section that's currently a 40-hour reconciliation, or a query you're still
                chasing evidence for. We'll show how MolTrace would carry it — cited and
                inspection-ready — end to end.
              </p>
              <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
                <Button asChild size="lg" className="gap-2">
                  <Link href="/contact?reason=Regulatory%20Affairs">
                    Request a demo
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="outline" className="gap-2">
                  <Link href="/regulatory-hub">
                    Explore ComplianceCore
                    <Workflow className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="ghost" className="gap-2">
                  <Link
                    href="https://docs.moltrace.co/guides/modules/regulatory/"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Read the docs
                    <FileText className="h-4 w-4" />
                  </Link>
                </Button>
              </div>
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </div>
  )
}
