import Link from "next/link"
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  Beaker,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileCheck,
  FileText,
  FlaskConical,
  Gauge,
  GitBranch,
  Lock,
  Microscope,
  Pill,
  PlayCircle,
  Rocket,
  Search,
  ShieldCheck,
  Sparkles,
  Target,
  Workflow,
  XCircle,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Footer } from "@/components/marketing/footer"
import { Header } from "@/components/marketing/header"

/**
 * Pharmaceutical R&D solution page — full marketing-shell route at
 * /pharmaceutical-rd. First of the four "Solutions" header pages.
 *
 * Solution pages differ from the Platform module pages by AXIS:
 *   - Platform pages answer "what does this module do?" (Spectroscopy,
 *     Regulatory Hub, ReactionIQ, Integrations).
 *   - Solution pages answer "what does MolTrace do for ME?" — they are
 *     audience-first, organised around a persona's jobs-to-be-done and
 *     the lifecycle they live in.
 *
 * This page is targeted at pharmaceutical R&D scientists and program
 * leads. It maps MolTrace capabilities onto the discovery → development
 * → submission lifecycle, then names the concrete workflows it lights up.
 *
 * Distinct visual identity vs the other pages:
 *   - Indigo hero badge (Spectroscopy=emerald, Regulatory=cyan,
 *     ReactionIQ=violet, Integrations=amber).
 *   - Hero visual is a live PROGRAM-LIFECYCLE card (phases with status),
 *     not a layer stack or audit ledger.
 *   - Lifecycle-phase capability grid is unique to the solution pages.
 *
 * All content grounded in real MolTrace capabilities: the 40-layer
 * evidence stack, SpectraCheck cross-modal confirmation, the ICH-aware
 * Regulatory Hub, ReactionIQ Bayesian optimization, recipe-hash
 * provenance, and the published validation numbers (94.4% solvent
 * auto-detect, 8.5× dense-¹³C speedup, ALCOA+ ledger).
 */

type Phase = {
  code: string
  name: string
  fits: string[]
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties; "aria-hidden"?: boolean }>
}

const LIFECYCLE: Phase[] = [
  {
    code: "DSC",
    name: "Discovery & hit identification",
    icon: Search,
    fits: [
      "Confirm hit structures from NMR + HRMS in one evidence stack",
      "Cross-modal contradiction warnings rule out mis-assignments early",
      "Artifact / solvent / impurity auto-classification on every peak",
    ],
  },
  {
    code: "LO",
    name: "Lead optimization",
    icon: Beaker,
    fits: [
      "ReactionIQ proposes the next experiment by Bayesian optimization",
      "Track analog series with traceable structure evidence per compound",
      "Surface process impurities while the route is still cheap to change",
    ],
  },
  {
    code: "CS",
    name: "Candidate selection",
    icon: Target,
    fits: [
      "Definitive elucidation with DP4 confidence + a full evidence trail",
      "Nominate a candidate with the data package already assembled",
      "Every numerical claim hyperlinked back to the spectrum it came from",
    ],
  },
  {
    code: "CMC",
    name: "Process & CMC development",
    icon: Gauge,
    fits: [
      "Impurity profiling against ICH Q3A / Q3B / Q3C / Q3D + M7",
      "Analytical method validation tracked across the Q2(R2) lifecycle",
      "Batch-to-batch comparison with recipe-hash-reproducible processing",
    ],
  },
  {
    code: "IND",
    name: "IND / submission",
    icon: FileCheck,
    fits: [
      "CTD dossier-section drafts composed from the underlying evidence",
      "ALCOA+ audit ledger + human signoff gate before any release",
      "Regulatory surveillance routes guidance changes to affected items",
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
    icon: Rocket,
    title: "Adopt AI — but prove it",
    body: "Leadership wants AI-accelerated discovery. Regulators (FDA Jan 2025, EMA reflection paper) want every AI-assisted claim reproducible, documented, and subordinate to human review. You need both at once.",
  },
  {
    icon: GitBranch,
    title: "Reproducibility is now table stakes",
    body: "ICH Q2(R2) raised the bar on analytical method validation. 'It looked similar when we re-ran it' no longer survives an inspection. Every processing step has to be replayable bit-for-bit.",
  },
  {
    icon: AlertTriangle,
    title: "Impurities decide timelines",
    body: "A nitrosamine flag or an unresolved degradant can stall a program for months. The earlier in the lifecycle you catch and classify it, the cheaper the route change.",
  },
  {
    icon: Activity,
    title: "The toolchain is fragmented",
    body: "NMR in one app, LC-MS in another, impurity tables in spreadsheets, the dossier in Word, the audit trail reconstructed from email. The handoffs are where evidence — and weeks — go missing.",
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
    icon: Microscope,
    name: "Structure confirmation & elucidation",
    blurb:
      "NMR, HRMS, and MS/MS scored together against candidate SMILES with DP4 confidence. Cross-modal disagreement surfaces as a first-class warning before you commit.",
    inputs: "Raw FID · mzML · candidate SMILES",
    outputs: "Ranked candidates · DP4 · evidence trail",
  },
  {
    icon: AlertTriangle,
    name: "Impurity & degradant profiling",
    blurb:
      "Peaks auto-classified against curated impurity-shift tables and mapped onto ICH Q3A/Q3B (organic), Q3C (residual solvent), and Q3D (elemental) acceptance windows.",
    inputs: "Spectra · solvent_hit table · drug substance",
    outputs: "Classified impurities · ICH verdict · open items",
  },
  {
    icon: Search,
    name: "Nitrosamine & genotoxic risk (M7)",
    blurb:
      "Structural-alert detection plus literature priors flag candidate nitrosamines and mutagenic impurities, and recommend the confirmatory MS/MS acquisition to settle them.",
    inputs: "Structure · synthesis route · spectra",
    outputs: "M7 verdict · risk tier · recommended MS/MS",
  },
  {
    icon: FlaskConical,
    name: "Reaction & route optimization",
    blurb:
      "ReactionIQ runs multi-objective Bayesian optimization over yield, selectivity, and impurity limits — and accepts those limits as priors so the next route is cleaner by design.",
    inputs: "Reaction recipe · objectives · constraints",
    outputs: "Next experiment · Pareto front · rationale",
  },
  {
    icon: ClipboardCheck,
    name: "Analytical method validation (Q2(R2))",
    blurb:
      "Track specificity, linearity, accuracy, precision, range, and robustness across a validation campaign — every parameter recipe-hash-linked to the run that produced it.",
    inputs: "Method runs · acceptance criteria · campaigns",
    outputs: "Q2(R2) report · parameter coverage · gaps",
  },
  {
    icon: FileText,
    name: "Submission-ready reporting",
    blurb:
      "Structure-elucidation and impurity reports compose into CTD dossier-section drafts, each numerical claim hyperlinked to source and gated behind explicit human signoff.",
    inputs: "Reviewed evidence · framework refs",
    outputs: "CTD drafts · ALCOA+ ledger · signoff record",
  },
]

type Outcome = {
  value: string
  label: string
  detail: string
}

const OUTCOMES: Outcome[] = [
  {
    value: "40",
    label: "Evidence layers",
    detail:
      "Typed, additive evidence layers — NMR, HRMS, MS/MS, predicted shifts, fragmentation trees, reaction history, J-couplings — fused into one confidence score per candidate.",
  },
  {
    value: "8.5×",
    label: "Faster dense ¹³C",
    detail:
      "Heavy ¹³C raw FIDs that previously took 5+ minutes now process in under a minute (v0.5.0) — so confirmation keeps pace with synthesis.",
  },
  {
    value: "94.4%",
    label: "Solvent auto-detect",
    detail:
      "Residual-solvent peaks identified automatically on the NMRShiftDB2 corpus, masked out of candidate scoring, and routed to ICH Q3C classification.",
  },
  {
    value: "Bit-identical",
    label: "Recipe-hash replay",
    detail:
      "Re-derive any processed spectrum or report from any prior date and get byte-for-byte identical output. Reproducibility is structural, not aspirational.",
  },
]

type Comparison = {
  dimension: string
  before: string
  after: string
}

const COMPARISON: Comparison[] = [
  {
    dimension: "Confirming a structure",
    before: "NMR app + MS app + manual reconciliation, judgement call recorded in a notebook",
    after: "Cross-modal evidence stack with DP4 confidence and contradiction warnings in one view",
  },
  {
    dimension: "Impurity audit trail",
    before: "Spreadsheet of shifts, hand-typed ICH class, limits looked up per project",
    after: "Auto-classified peaks mapped to Q3A/B/C/D + M7 with cited reference shifts and deltas",
  },
  {
    dimension: "Chem ↔ analytical ↔ regulatory handoff",
    before: "Files emailed between teams; context and provenance lost at each boundary",
    after: "One evidence object flows through the modules; every handoff written to the audit ledger",
  },
  {
    dimension: "Reproducing an analysis months later",
    before: "Re-run from scratch; 'looks close enough' is usually the verdict",
    after: "Recipe-hash replay yields bit-identical output — the same numbers, every time",
  },
  {
    dimension: "Reaching a submission-ready section",
    before: "Dossier written in parallel in week 11, reconciled against raw data by hand",
    after: "CTD draft composed from the evidence as a by-product of the science, claim-by-claim cited",
  },
  {
    dimension: "AI evidence under inspection",
    before: "Hard to show how a model reached a call; documentation assembled retroactively",
    after: "FDA-aligned model documentation + human signoff gate + ALCOA+ ledger, inspection-ready",
  },
]

type LoopStep = {
  step: string
  body: string
}

const WORKED_EXAMPLE: LoopStep[] = [
  {
    step: "SpectraCheck detects",
    body: "A peak at 2.10 ppm is auto-classified as acetic acid (residual), 93% confidence, and HRMS corroborates the implied formula. No mis-assignment slips through.",
  },
  {
    step: "Regulatory Hub classifies",
    body: "ICH Q3C: acetic acid is Class 3, no action below 5000 ppm. The finding lands in dossier section 3.2.S.3.2 as informational — no human review queued.",
  },
  {
    step: "ReactionIQ constrains",
    body: "The impurity limit propagates as a Bayesian prior on the next route. Workup and solvent are adjusted automatically so the following batch is cleaner by design.",
  },
  {
    step: "The loop closes",
    body: "The re-acquired spectrum confirms the impurity below threshold. The audit ledger records every step — FID hash → recipe → classification → route update → signoff.",
  },
]

type TrustPillar = {
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties; "aria-hidden"?: boolean }>
  title: string
  body: string
}

const TRUST: TrustPillar[] = [
  {
    icon: Database,
    title: "Immutable raw vault",
    body: "Every FID is SHA-256 hashed, vault-path-policy enforced, and never overwritten. The original evidence survives every reprocess.",
  },
  {
    icon: GitBranch,
    title: "Recipe-hash provenance",
    body: "Every processing run links a recipe hash to the unchanged raw archive. Bit-identical replay from any prior date, forever.",
  },
  {
    icon: ClipboardCheck,
    title: "Human signoff queue",
    body: "No regulatory document is released without an explicit qualified-human attribution — the FDA Stage 4 oversight gate, in code.",
  },
  {
    icon: BadgeCheck,
    title: "ALCOA+ audit ledger",
    body: "Attributable · Legible · Contemporaneous · Original · Accurate · Complete · Consistent · Enduring · Available — on every event.",
  },
  {
    icon: AlertTriangle,
    title: "Cross-modal contradiction warnings",
    body: "HRMS exact mass disagreeing with the NMR-implied formula raises a first-class warning before signoff — every time.",
  },
  {
    icon: Lock,
    title: "Tenant isolation by default",
    body: "SOC 2 Type II controls, GDPR-compliant data residency, and a role-scoped audit-event ledger isolate each organization's data.",
  },
]

export function PharmaRdPage() {
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
                <div className="flex items-center gap-2">
                  <Badge
                    variant="outline"
                    className="border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-900 dark:bg-indigo-950/40 dark:text-indigo-300"
                  >
                    <Pill className="mr-1 h-3 w-3" aria-hidden />
                    Solution · Pharmaceutical R&amp;D
                  </Badge>
                  <Badge variant="outline" className="text-muted-foreground">
                    Discovery → Development → Submission
                  </Badge>
                </div>
                <h1 className="mt-5 max-w-3xl text-4xl font-semibold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl">
                  Move faster on the molecule.{" "}
                  <span style={{ color: "var(--mt-teal)" }}>Never</span> on the evidence.
                </h1>
                <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted-foreground sm:text-xl">
                  MolTrace gives pharmaceutical R&amp;D teams one audit-grade evidence stack from the
                  first hit spectrum to the IND dossier. Confirm structures, profile impurities,
                  optimize routes, and compose submission-ready sections — without ever losing the
                  trail back to the raw data.
                </p>
                <div className="mt-10 flex flex-wrap items-center gap-4">
                  <Button asChild size="lg" className="gap-2">
                    <Link href="/contact?reason=Pharmaceutical%20R%26D">
                      Request a demo
                      <ArrowRight className="h-4 w-4" />
                    </Link>
                  </Button>
                  <Button asChild size="lg" variant="outline" className="gap-2">
                    <Link href="/spectracheck">
                      Open SpectraCheck
                      <PlayCircle className="h-4 w-4" />
                    </Link>
                  </Button>
                </div>
              </div>

              {/* Hero visual — live program-lifecycle card */}
              <aside className="relative overflow-hidden rounded-3xl border bg-card p-6 shadow-sm">
                <div className="flex items-center justify-between">
                  <p
                    className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                    style={{ color: "var(--mt-teal)" }}
                  >
                    Program lifecycle · live
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
                    On track
                  </span>
                </div>
                <p className="mt-3 font-mono text-xs text-muted-foreground">
                  program · MOL-2041 · ibuprofen analog
                </p>
                <p className="mt-1 text-sm font-medium">Evidence assembled across five phases</p>

                <div className="mt-6 space-y-1.5">
                  {[
                    { code: "DSC", title: "Discovery — hit confirmed", state: "done" },
                    { code: "LO", title: "Lead opt — 18 analogs traced", state: "done" },
                    { code: "CS", title: "Candidate selected · DP4 96%", state: "done" },
                    { code: "CMC", title: "Impurities → ICH Q3C / Q3D", state: "active" },
                    { code: "IND", title: "Dossier 3.2.S drafting", state: "queued" },
                  ].map((row) => (
                    <div
                      key={row.code}
                      className="flex items-center gap-3 rounded-md border bg-background/80 px-3 py-2"
                    >
                      <span
                        className="inline-flex h-6 w-9 shrink-0 items-center justify-center rounded font-mono text-[9px] font-bold"
                        style={{
                          backgroundColor: "var(--mt-teal-soft)",
                          color: "var(--mt-teal)",
                        }}
                      >
                        {row.code}
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
                  every phase · one audit trail · zero re-keying
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
                Why pharma R&amp;D
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Four pressures, hitting at the same time.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Discovery teams are asked to go faster with AI, prove more to regulators, catch
                impurities earlier, and do it across a toolchain that was never designed to hold
                evidence together. MolTrace is built for exactly that intersection.
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

        {/* ── Lifecycle fit ───────────────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Across the lifecycle
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                One evidence stack, five phases deep.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                MolTrace isn't a point tool you bolt onto one step. The same audit-grade evidence
                object follows the molecule from the first hit spectrum to the submission — so what
                discovery learns is still legible to CMC and regulatory months later.
              </p>
            </div>

            {/* Phase rail */}
            <div className="mt-12 overflow-hidden rounded-2xl border bg-card">
              <div className="border-b bg-muted/40 px-4 py-2.5">
                <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
                  The lifecycle, at a glance
                </p>
              </div>
              <pre className="overflow-x-auto px-4 py-5 font-mono text-[11px] leading-relaxed text-foreground sm:px-8 sm:text-xs">
{`  Discovery ──► Lead opt ──► Candidate ──► Process / CMC ──► IND / Submission
     │            │             │              │                    │
     ▼            ▼             ▼              ▼                    ▼
  confirm     optimize      definitive     impurity +          dossier +
  hits        the route     elucidation    method val.         ALCOA+ ledger
  (NMR+MS)    (ReactionIQ)  (DP4 + trail)  (Q3x · Q2(R2))      (signoff gate)`}
              </pre>
            </div>

            <div className="mt-8 grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
              {LIFECYCLE.map((phase) => {
                const Icon = phase.icon
                return (
                  <article
                    key={phase.code}
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
                          {phase.code}
                        </p>
                        <h3 className="text-base font-semibold tracking-tight">{phase.name}</h3>
                      </div>
                    </div>
                    <ul className="mt-5 space-y-2">
                      {phase.fits.map((fit) => (
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
                Six R&amp;D workflows, with their inputs and outputs.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Each of these is a typed pipeline that ships today — not a bespoke build. Inputs come
                from your instruments or your data lake; outputs land in the evidence stack, the
                audit ledger, and the dossier composer.
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
                What the platform actually delivers.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Every number below is reproducible from a publicly-described corpus or a shipped
                release note — not a marketing estimate. The regression gate runs in CI on every
                detector change.
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
                What changes for an R&amp;D program.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Most teams today run discovery through a stack of disconnected apps, spreadsheets, and
                email. Here's exactly what flips when the evidence travels with the molecule.
              </p>
            </div>
            <div className="mt-12 overflow-hidden rounded-2xl border bg-card shadow-sm">
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
                An impurity, end-to-end — and back into the next batch.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                The modules aren't separate apps you stitch together. Here is a single finding
                travelling across all three, with the audit ledger recording every handoff.
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
                      The evidence engine that detects and confirms every finding.
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
                    <p className="text-sm font-semibold">Regulatory Hub →</p>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      Routes the finding to ICH classes and drafts the dossier section.
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
                href="/reaction-optimization"
                className="group flex items-center justify-between gap-4 rounded-2xl border bg-card p-5 transition-all hover:-translate-y-0.5 hover:shadow-md"
              >
                <div className="flex items-start gap-3">
                  <FlaskConical
                    className="mt-0.5 h-5 w-5 shrink-0"
                    style={{ color: "var(--mt-teal)" }}
                    aria-hidden
                  />
                  <div>
                    <p className="text-sm font-semibold">ReactionIQ →</p>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      Feeds the impurity limit into the next route as a Bayesian prior.
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

        {/* ── Trust + compliance ──────────────────────────────────────────── */}
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
                  Speed that survives an audit.
                </h2>
                <p className="mt-4 text-base text-muted-foreground">
                  Going faster only helps if the work holds up when an inspector arrives. Every
                  acceleration in MolTrace is backed by the same provenance machinery — designed
                  against ICH Q2(R2) ALCOA+, the FDA's January 2025 AI framework, and the EMA
                  reflection paper from day one.
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
                Bring a program you're stuck on.
              </h2>
              <p className="mt-4 text-base text-muted-foreground sm:text-lg">
                Pick a compound where the structure, the impurity profile, or the submission section
                is eating weeks. We'll walk through how MolTrace would carry the evidence end-to-end.
              </p>
              <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
                <Button asChild size="lg" className="gap-2">
                  <Link href="/contact?reason=Pharmaceutical%20R%26D">
                    Request a demo
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="outline" className="gap-2">
                  <Link href="/platform#platform">
                    Explore the platform
                    <Workflow className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="ghost" className="gap-2">
                  <Link
                    href="https://docs.moltrace.co/guides/quickstart/"
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
