import Link from "next/link"
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  Boxes,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileCheck,
  FileText,
  Gauge,
  GitBranch,
  Lock,
  Microscope,
  PackageCheck,
  PlayCircle,
  Repeat,
  ShieldCheck,
  Sparkles,
  Timer,
  Truck,
  Workflow,
  XCircle,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Footer } from "@/components/marketing/footer"
import { Header } from "@/components/marketing/header"

/**
 * CRO / Analytical solution page — full marketing-shell route at
 * /cro-analytical. Third of the four "Solutions" header pages.
 *
 * Audience: contract research organizations and fee-for-service
 * analytical labs. Their world is volume under SLA, deliverables that
 * a sponsor (and the sponsor's regulator) will scrutinize, strict
 * client confidentiality, and margins that live or die on consistency
 * at scale.
 *
 * Distinct visual identity vs the other solution/module pages:
 *   - Orange hero badge (Pharma=indigo, Academic=rose,
 *     Spectroscopy=emerald, Regulatory=cyan, ReactionIQ=violet,
 *     Integrations=amber).
 *   - Hero visual is a live BATCH-THROUGHPUT queue card with per-client
 *     isolation tags — not a lifecycle rail, layer stack, audit ledger,
 *     or methods/SI card.
 *   - "Across the service workflow" maps the contract-lab pipeline
 *     (intake → acquisition → analysis/QC → deliverable → sponsor handoff).
 *
 * All content grounded in real MolTrace capabilities: the 40-layer
 * evidence stack, 8.5x dense-¹³C throughput, per-peak QC fit metrics,
 * recipe-hash reproducibility, per-tenant isolation, ICH-aware impurity
 * routing, ALCOA+ / 21 CFR Part 11 alignment, and the published numbers.
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
    name: "Intake & chain of custody",
    icon: Truck,
    fits: [
      "Each sample's raw FID is SHA-256 hashed and vaulted on arrival",
      "Per-sponsor isolation enforced from the first byte",
      "Provenance starts at intake and never breaks downstream",
    ],
  },
  {
    code: "ACQ",
    name: "Acquisition & processing",
    icon: Activity,
    fits: [
      "Bruker and Agilent/Varian FIDs processed by the same recipe",
      "8.5× faster dense ¹³C keeps the instrument queue moving",
      "Every run is recipe-hash-linked and replayable on demand",
    ],
  },
  {
    code: "QC",
    name: "Analysis & QC",
    icon: Gauge,
    fits: [
      "Per-peak fit metrics (χ²ᵣ, RMSE, FWHM, S/N, baseline σ) on every signal",
      "Cross-modal contradiction warnings catch problems before delivery",
      "Identical analysis regardless of which analyst ran it",
    ],
  },
  {
    code: "DELIVER",
    name: "Client deliverable & reporting",
    icon: PackageCheck,
    fits: [
      "Sponsor-ready reports with every claim cited back to the spectrum",
      "Impurities classified to ICH Q3A/Q3B/Q3C/Q3D for the sponsor's dossier",
      "Consistent format across every batch and every client",
    ],
  },
  {
    code: "AUDIT",
    name: "Sponsor handoff & audit support",
    icon: ShieldCheck,
    fits: [
      "ALCOA+ audit ledger + 21 CFR Part 11 alignment, inspection-ready",
      "Recipe-hash replay reproduces any deliverable, bit-for-bit, years on",
      "Hand the sponsor an evidence package their auditor can query directly",
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
    icon: Timer,
    title: "Turnaround is the product",
    body: "Sponsors choose a CRO on speed and reliability. Volume keeps climbing while SLAs tighten — and a single slow processing step on dense ¹³C can put a whole batch behind.",
  },
  {
    icon: ShieldCheck,
    title: "Every result is scrutinized twice",
    body: "Your deliverable is read by the sponsor and then, eventually, by the sponsor's regulator. A number without a defensible trail back to the raw data is a liability you signed for.",
  },
  {
    icon: Lock,
    title: "Many clients, zero leakage",
    body: "You run competing sponsors in the same building on the same instruments. Confidentiality can't depend on folder discipline — isolation has to be structural and provable.",
  },
  {
    icon: Repeat,
    title: "Margin lives in consistency",
    body: "Profitability comes from doing the same method the same way across analysts, shifts, and sites. Heroics by one expert operator don't scale; reproducible pipelines do.",
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
    icon: Boxes,
    name: "High-throughput confirmation",
    blurb:
      "Run identity confirmation across a full batch with consistent processing and QC. NMR + HRMS scored together so a mis-assignment never reaches a deliverable.",
    inputs: "Batch of raw FIDs · mzML · target SMILES",
    outputs: "Per-sample verdict · DP4 · QC metrics",
  },
  {
    icon: AlertTriangle,
    name: "Impurity & residual-solvent screening",
    blurb:
      "Auto-classify peaks against curated impurity tables and map them onto ICH Q3A/Q3B (organic), Q3C (residual solvent), and Q3D (elemental) limits for the sponsor's submission.",
    inputs: "Spectra · solvent_hit table · sponsor spec",
    outputs: "Classified impurities · ICH verdict · open items",
  },
  {
    icon: ClipboardCheck,
    name: "Method validation & transfer (Q2(R2))",
    blurb:
      "Validate a method once and transfer it between analysts and sites with the recipe pinned. Specificity, linearity, accuracy, precision, range, robustness — all tracked.",
    inputs: "Method runs · acceptance criteria · sites",
    outputs: "Q2(R2) report · transfer record · gaps",
  },
  {
    icon: Repeat,
    name: "Batch comparison & release testing",
    blurb:
      "Compare batch-to-batch with recipe-hash-reproducible processing, so a difference in the data is a difference in the sample — not a difference in how it was processed.",
    inputs: "Batch spectra · reference batch · spec",
    outputs: "Comparison · pass/fail · deviations",
  },
  {
    icon: FileCheck,
    name: "Sponsor-ready reporting",
    blurb:
      "Compose deliverables where every numerical claim hyperlinks to its source spectrum, formatted consistently across clients and ready to drop into a sponsor's CTD dossier.",
    inputs: "Reviewed analysis · sponsor template",
    outputs: "Cited report · CTD-aligned section · ledger",
  },
  {
    icon: Lock,
    name: "Multi-client isolation & audit support",
    blurb:
      "Per-tenant isolation keeps each sponsor's data separate by construction, while a role-scoped ALCOA+ ledger gives any auditor a queryable trail without exposing other clients.",
    inputs: "All client work · audit request",
    outputs: "Isolated data · scoped audit view · evidence",
  },
]

type Outcome = {
  value: string
  label: string
  detail: string
}

const OUTCOMES: Outcome[] = [
  {
    value: "8.5×",
    label: "Faster dense ¹³C",
    detail:
      "Heavy ¹³C raw FIDs that previously took 5+ minutes now process in under a minute (v0.5.0) — throughput that shows up directly in turnaround time.",
  },
  {
    value: "40",
    label: "Evidence layers",
    detail:
      "Typed, additive evidence layers fuse NMR, HRMS, MS/MS, predicted shifts, and fragmentation trees into one defensible confidence score per sample.",
  },
  {
    value: "94.4%",
    label: "Solvent auto-detect",
    detail:
      "Residual-solvent peaks identified automatically on the NMRShiftDB2 corpus and routed to ICH Q3C — fewer manual touches per sample at volume.",
  },
  {
    value: "Bit-identical",
    label: "Recipe-hash replay",
    detail:
      "Reproduce any deliverable from any prior date with byte-for-byte identical output — the answer to a sponsor auditor's hardest question.",
  },
]

type Comparison = {
  dimension: string
  before: string
  after: string
}

const COMPARISON: Comparison[] = [
  {
    dimension: "Turnaround per sample",
    before: "Dense ¹³C and manual QC create bottlenecks that ripple across the batch",
    after: "8.5× faster processing + automated per-peak QC keep the queue moving",
  },
  {
    dimension: "Defending a result to a sponsor's auditor",
    before: "Reconstruct the trail from instrument logs, emails, and analyst memory",
    after: "One ALCOA+ ledger query — every claim cited to its raw FID, replayable on demand",
  },
  {
    dimension: "Keeping clients' data separate",
    before: "Folder conventions and access lists that depend on people getting it right",
    after: "Per-tenant isolation enforced structurally — confidentiality you can prove",
  },
  {
    dimension: "Consistency across analysts & sites",
    before: "Output quality varies with who processed it and where",
    after: "Identical recipe + QC everywhere — comparable data across the whole org",
  },
  {
    dimension: "Producing the client deliverable",
    before: "Manual report assembly per sponsor; format drifts and errors creep in",
    after: "Consistent, cited reports composed from the analysis, CTD-aligned out of the box",
  },
  {
    dimension: "Transferring a method between sites",
    before: "Re-validate from scratch and hope the second site reproduces the first",
    after: "Recipe pinned and replayed — transfer is verification, not reinvention",
  },
]

type LoopStep = {
  step: string
  body: string
}

const WORKED_EXAMPLE: LoopStep[] = [
  {
    step: "A sponsor sends a batch",
    body: "Sixty samples land as raw FIDs. Each is SHA-256 hashed, vaulted, and tagged to the sponsor in an isolated tenant before any processing begins.",
  },
  {
    step: "Throughput holds",
    body: "Identical processing and per-peak QC run across every sample — dense ¹³C included, 8.5× faster — so the whole batch clears within the SLA window.",
  },
  {
    step: "An impurity is flagged",
    body: "A residual-solvent peak is auto-classified and mapped to ICH Q3C with its reference shift and delta cited — ready to drop straight into the sponsor's dossier.",
  },
  {
    step: "The package is audit-ready",
    body: "The deliverable hands the sponsor an evidence package their auditor can query directly: every claim cited to its FID, every step replayable bit-for-bit.",
  },
]

type TrustPillar = {
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties; "aria-hidden"?: boolean }>
  title: string
  body: string
}

const TRUST: TrustPillar[] = [
  {
    icon: Lock,
    title: "Per-tenant client isolation",
    body: "Each sponsor's data lives in an isolated tenant with role-scoped access. Confidentiality between competing clients is structural, not procedural.",
  },
  {
    icon: Database,
    title: "Immutable raw vault",
    body: "Every sample's FID is SHA-256 hashed at intake and never overwritten — chain of custody that survives every reprocess.",
  },
  {
    icon: GitBranch,
    title: "Recipe-hash provenance",
    body: "Every processing run links a recipe hash to the unchanged raw archive. Reproduce any deliverable, bit-identical, years later.",
  },
  {
    icon: BadgeCheck,
    title: "ALCOA+ & 21 CFR Part 11",
    body: "The audit ledger is built against ALCOA+ and electronic-records requirements, so your deliverables stand up in the sponsor's own inspection.",
  },
  {
    icon: AlertTriangle,
    title: "Cross-modal contradiction warnings",
    body: "HRMS exact mass disagreeing with the NMR-implied formula raises a first-class warning before a result ships — not after the sponsor finds it.",
  },
  {
    icon: ShieldCheck,
    title: "SOC 2 Type II controls",
    body: "GDPR-compliant data residency and SOC 2 Type II controls underpin the platform every sponsor's procurement team will ask about.",
  },
]

export function CroAnalyticalPage() {
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
                    className="border-orange-300 bg-orange-50 text-orange-700 dark:border-orange-900 dark:bg-orange-950/40 dark:text-orange-300"
                  >
                    <Microscope className="mr-1 h-3 w-3" aria-hidden />
                    Solution · CRO / Analytical
                  </Badge>
                  <Badge variant="outline" className="text-muted-foreground">
                    Throughput · Turnaround · Defensible
                  </Badge>
                </div>
                <h1 className="mt-5 max-w-3xl text-4xl font-semibold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl">
                  Defensible results, at the{" "}
                  <span style={{ color: "var(--mt-teal)" }}>volume</span> your clients demand.
                </h1>
                <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted-foreground sm:text-xl">
                  MolTrace gives contract and analytical labs one pipeline that runs every sponsor's
                  samples the same way — fast enough to hit the SLA, consistent enough to defend, and
                  isolated enough to keep competing clients fully separate.
                </p>
                <div className="mt-10 flex flex-wrap items-center gap-4">
                  <Button asChild size="lg" className="gap-2">
                    <Link href="/contact?reason=CRO%20%2F%20Analytical">
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

              {/* Hero visual — live batch-throughput queue card */}
              <aside className="relative overflow-hidden rounded-3xl border bg-card p-6 shadow-sm">
                <div className="flex items-center justify-between">
                  <p
                    className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                    style={{ color: "var(--mt-teal)" }}
                  >
                    Batch queue · live
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
                    On SLA
                  </span>
                </div>
                <p className="mt-3 font-mono text-xs text-muted-foreground">
                  batch B-2207 · 6 sponsors · isolated
                </p>
                <p className="mt-1 text-sm font-medium">
                  <span
                    className="font-mono text-2xl font-bold tabular-nums"
                    style={{ color: "var(--mt-teal)" }}
                  >
                    128
                  </span>{" "}
                  samples cleared today
                </p>

                <div className="mt-6 space-y-1.5">
                  {[
                    { id: "S-4012", client: "A", state: "done" },
                    { id: "S-4013", client: "A", state: "done" },
                    { id: "S-4014", client: "B", state: "done" },
                    { id: "S-4015", client: "C", state: "active" },
                    { id: "S-4016", client: "C", state: "queued" },
                    { id: "S-4017", client: "D", state: "queued" },
                  ].map((row) => (
                    <div
                      key={row.id}
                      className="flex items-center gap-3 rounded-md border bg-background/80 px-3 py-2"
                    >
                      <span className="font-mono text-[11px] tabular-nums text-foreground">
                        {row.id}
                      </span>
                      <span
                        className="inline-flex items-center rounded border px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.12em]"
                        style={{
                          borderColor: "color-mix(in oklab, var(--mt-teal) 25%, transparent)",
                          color: "var(--mt-teal)",
                        }}
                      >
                        client {row.client}
                      </span>
                      <span className="flex-1" />
                      {row.state === "done" ? (
                        <CheckCircle2
                          className="h-3.5 w-3.5 shrink-0"
                          style={{ color: "var(--mt-teal)" }}
                          aria-label="cleared"
                        />
                      ) : row.state === "active" ? (
                        <span
                          className="h-2 w-2 shrink-0 animate-pulse rounded-full"
                          style={{ backgroundColor: "var(--mt-teal)" }}
                          aria-label="processing"
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
                  each sponsor isolated · each result traces to its FID
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
                Why CROs &amp; analytical labs
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Four pressures, every batch, every client.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                A contract lab is judged on speed, defensibility, confidentiality, and consistency —
                simultaneously, across every sponsor in the building. MolTrace is built to deliver
                all four from one pipeline.
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

        {/* ── Across the service workflow ──────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Across the service workflow
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                From intake to sponsor handoff, one trail.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Provenance starts when a sample arrives and stays intact all the way to the
                deliverable — so the package you hand a sponsor is audit-ready the moment it leaves
                your lab.
              </p>
            </div>

            <div className="mt-12 overflow-hidden rounded-2xl border bg-card">
              <div className="border-b bg-muted/40 px-4 py-2.5">
                <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
                  The pipeline, at a glance
                </p>
              </div>
              <pre className="overflow-x-auto px-4 py-5 font-mono text-[11px] leading-relaxed text-foreground sm:px-8 sm:text-xs">
{`  Intake ──► Acquisition ──► Analysis / QC ──► Deliverable ──► Sponsor handoff
     │            │                │                │                  │
     ▼            ▼                ▼                ▼                  ▼
  hash +       one recipe       per-peak QC      cited report      ALCOA+ ledger
  isolate      8.5× ¹³C         + contradiction  ICH-classified    + replay
  per client   replayable       warnings         per sponsor       (audit-ready)`}
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
                Six contract-lab workflows, with their inputs and outputs.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Each is a typed pipeline that ships today. Inputs arrive from your instruments and
                your sponsors; outputs land in the evidence stack, the audit ledger, and a
                consistent, cited deliverable.
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
                The numbers that move turnaround and trust.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Every figure below is reproducible from a publicly-described corpus or a shipped
                release note. The regression gate runs in CI on every detector change — drift on any
                single fixture fails the build by name.
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
                What changes for a contract lab.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Most labs run on vendor software, spreadsheets, and per-sponsor report templates.
                Here's what flips when one reproducible pipeline carries every sample and its
                provenance.
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
                A sponsor's batch, from intake to audit-ready package.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                A single batch followed end-to-end — fast enough for the SLA, isolated for
                confidentiality, and defensible the moment it ships.
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
                      The evidence engine that processes and confirms every sample.
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
                    <p className="text-sm font-semibold">Regentry →</p>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      Classifies impurities to ICH and drafts the sponsor's dossier section.
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
                href="/integrations"
                className="group flex items-center justify-between gap-4 rounded-2xl border bg-card p-5 transition-all hover:-translate-y-0.5 hover:shadow-md"
              >
                <div className="flex items-start gap-3">
                  <Workflow
                    className="mt-0.5 h-5 w-5 shrink-0"
                    style={{ color: "var(--mt-teal)" }}
                    aria-hidden
                  />
                  <div>
                    <p className="text-sm font-semibold">Integrations →</p>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      Connect Bruker, Agilent, and your LIMS so batches flow in automatically.
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

        {/* ── Trust + isolation ───────────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="grid gap-10 lg:grid-cols-[1fr_1.6fr]">
              <div>
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                  style={{ color: "var(--mt-teal)" }}
                >
                  Built for sponsors
                </p>
                <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                  Confidentiality and defensibility, by construction.
                </h2>
                <p className="mt-4 text-base text-muted-foreground">
                  Your sponsors carry their own regulatory burden, and your deliverables become part
                  of it. Every control below is implemented in production code — designed against
                  ALCOA+, 21 CFR Part 11, and SOC 2 from day one.
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
                Send us a batch you're behind on.
              </h2>
              <p className="mt-4 text-base text-muted-foreground sm:text-lg">
                Pick a sponsor workflow where turnaround or audit prep is the bottleneck. We'll show
                how MolTrace runs the batch — fast, isolated, and defensible end-to-end.
              </p>
              <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
                <Button asChild size="lg" className="gap-2">
                  <Link href="/contact?reason=CRO%20%2F%20Analytical">
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
