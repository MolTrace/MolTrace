import Link from "next/link"
import {
  AlertTriangle,
  ArrowRight,
  Atom,
  BookOpen,
  CheckCircle2,
  Database,
  Eye,
  FileText,
  FlaskConical,
  GitBranch,
  GraduationCap,
  Library,
  Lightbulb,
  Microscope,
  PlayCircle,
  Quote,
  Repeat,
  Share2,
  ShieldCheck,
  Sparkles,
  Users,
  Workflow,
  XCircle,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Footer } from "@/components/marketing/footer"
import { Header } from "@/components/marketing/header"

/**
 * Academic Research solution page — full marketing-shell route at
 * /academic-research. Second of the four "Solutions" header pages.
 *
 * Audience: university + institute labs — PIs, graduate students,
 * postdocs, and shared NMR/MS core-facility staff. The argument is
 * organised around the things academic chemists actually fight with:
 * the reproducibility crisis, teaching structure elucidation without a
 * black box, core-facility throughput + consistency, and constrained
 * grant budgets.
 *
 * Distinct visual identity vs the other solution/module pages:
 *   - Rose hero badge (Pharma=indigo, Spectroscopy=emerald,
 *     Regulatory=cyan, Repho=violet, Integrations=amber).
 *   - Hero visual is a live PUBLICATION-REPRODUCIBILITY card — an
 *     auto-generated methods / supporting-information snapshot — not a
 *     lifecycle rail, layer stack, or audit ledger.
 *   - "Across the academic workflow" maps research contexts (teaching,
 *     bench, core facility, publication, open science) to MolTrace fit.
 *
 * All content grounded in real MolTrace capabilities: the 40-layer
 * evidence stack, cross-modal confirmation, per-peak QC fit metrics,
 * recipe-hash reproducibility, vendor-agnostic raw FID + open formats,
 * the explainable evidence trail, and the published validation numbers.
 */

type Context = {
  code: string
  name: string
  fits: string[]
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties; "aria-hidden"?: boolean }>
}

const CONTEXTS: Context[] = [
  {
    code: "TEACH",
    name: "Teaching & training",
    icon: BookOpen,
    fits: [
      "Show the reasoning behind every assignment, layer by layer",
      "Students see why a peak is solvent, impurity, or signal — not a verdict",
      "Turn a real spectrum into a worked problem with the answer key attached",
    ],
  },
  {
    code: "BENCH",
    name: "Bench research & characterization",
    icon: Microscope,
    fits: [
      "Confirm what you made from NMR + HRMS in one evidence stack",
      "Full elucidation for unknowns, natural products, and metabolites",
      "Cross-modal contradiction warnings catch mis-assignments early",
    ],
  },
  {
    code: "CORE",
    name: "Core & shared facilities",
    icon: Users,
    fits: [
      "Consistent processing + per-peak QC across every group you serve",
      "Bruker and Agilent/Varian raw FID parsed the same way, every time",
      "8.5× faster dense ¹³C keeps the instrument queue moving",
    ],
  },
  {
    code: "PUB",
    name: "Publication & peer review",
    icon: Quote,
    fits: [
      "Auto-generated supporting information with every claim cited to source",
      "A methods section detailed enough for a reviewer to actually reproduce",
      "Recipe-hash replay reproduces a figure bit-for-bit, years later",
    ],
  },
  {
    code: "OPEN",
    name: "Open science & data deposition",
    icon: Share2,
    fits: [
      "Open formats throughout — JCAMP-DX, mzML, CSV — nothing locked in",
      "Immutable raw archive preserved alongside processed output",
      "Provenance travels with the data when you deposit it",
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
    icon: Repeat,
    title: "The reproducibility crisis is real",
    body: "Most methods sections are too thin to reproduce — the processing parameters, the software version, the exact phasing are gone. When a result can't be re-derived, it can't be trusted, and increasingly it can't be published.",
  },
  {
    icon: Lightbulb,
    title: "Black boxes don't teach",
    body: "A tool that prints an answer teaches students nothing. They need to see how an assignment was reached — shift windows, multiplicity, coupling, integration, cross-modal corroboration — to learn to do it themselves.",
  },
  {
    icon: Users,
    title: "One facility, many groups",
    body: "A shared NMR/MS core serves dozens of labs with wildly different samples. Consistency of processing and QC — not heroics by one expert operator — is what keeps the data comparable across the building.",
  },
  {
    icon: GitBranch,
    title: "Grant budgets are finite",
    body: "Academic groups can't absorb per-seat enterprise pricing or a six-month integration project. The tooling has to earn its place by saving time on characterization and SI assembly from day one.",
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
    icon: CheckCircle2,
    name: "Routine characterization",
    blurb:
      "Confirm a freshly synthesized compound matches its intended structure. NMR + HRMS scored together with DP4 confidence and an evidence trail you can paste into a notebook.",
    inputs: "Raw FID · mzML · target SMILES",
    outputs: "Match verdict · DP4 · per-peak assignment",
  },
  {
    icon: Atom,
    name: "Unknown & natural-product elucidation",
    blurb:
      "Work a true unknown across 1D/2D NMR and MS/MS. Candidate ranking, fragmentation trees, and cross-modal checks narrow the structure with the reasoning kept visible.",
    inputs: "1D / 2D NMR · MS/MS · constraints",
    outputs: "Ranked candidates · connectivity · evidence",
  },
  {
    icon: FileText,
    name: "Publication-ready SI & methods",
    blurb:
      "Generate a supporting-information package and a methods section from the analysis itself — instrument, solvent, processing recipe, software version, and per-signal assignments, all cited.",
    inputs: "Reviewed analysis · instrument metadata",
    outputs: "SI tables · methods draft · recipe hash",
  },
  {
    icon: Eye,
    name: "Teaching the evidence",
    blurb:
      "Hand a class a real spectrum and let them see the layered reasoning behind each assignment. Transparency is the feature — every category and confidence number traces to its source.",
    inputs: "Course spectra · candidate structures",
    outputs: "Layer-by-layer reasoning · answer key",
  },
  {
    icon: ShieldCheck,
    name: "Core-facility QC & consistency",
    blurb:
      "Per-peak fit metrics (χ²ᵣ, RMSE, FWHM, S/N, baseline σ) and identical processing across every user mean the data your facility hands back is comparable group-to-group.",
    inputs: "Instrument output · processing recipe",
    outputs: "QC metrics · consistent processed spectra",
  },
  {
    icon: FlaskConical,
    name: "Methodology & reaction screening",
    blurb:
      "Methodology groups developing new reactions use Repho to plan screens by Bayesian optimization over yield and selectivity — fewer reactions to find the conditions worth publishing.",
    inputs: "Reaction recipe · objectives · constraints",
    outputs: "Next experiment · Pareto front · rationale",
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
      "Typed, additive evidence layers fuse NMR, HRMS, MS/MS, predicted shifts, fragmentation trees, and J-couplings into one transparent confidence score per candidate.",
  },
  {
    value: "8.5×",
    label: "Faster dense ¹³C",
    detail:
      "Heavy ¹³C raw FIDs that previously took 5+ minutes now process in under a minute (v0.5.0) — real throughput for a busy shared facility.",
  },
  {
    value: "94.4%",
    label: "Solvent auto-detect",
    detail:
      "Residual-solvent peaks identified automatically on the NMRShiftDB2 corpus and masked from candidate scoring — fewer manual corrections per spectrum.",
  },
  {
    value: "Bit-identical",
    label: "Recipe-hash replay",
    detail:
      "Re-derive any processed spectrum or figure from any prior date with byte-for-byte identical output — reproducibility a reviewer can actually verify.",
  },
]

type Comparison = {
  dimension: string
  before: string
  after: string
}

const COMPARISON: Comparison[] = [
  {
    dimension: "Methods section detail",
    before: "Hand-written, often missing processing params and software version",
    after: "Auto-generated from the analysis with recipe hash, params, and version pinned",
  },
  {
    dimension: "Reproducing a result later",
    before: "A new student re-runs from scratch and hopes it looks the same",
    after: "Recipe-hash replay yields bit-identical output — the same numbers, every time",
  },
  {
    dimension: "Teaching how an assignment was reached",
    before: "A printout of peaks; the reasoning lives only in the expert's head",
    after: "Layer-by-layer evidence trail — students see shift, multiplicity, coupling, cross-modal",
  },
  {
    dimension: "Supporting information assembly",
    before: "Manual table-building the week before submission; transcription errors creep in",
    after: "SI tables composed from the analysis, each value cited to the spectrum it came from",
  },
  {
    dimension: "Core-facility consistency across users",
    before: "Quality depends on which operator processed it that day",
    after: "Identical processing + per-peak QC for every group — comparable data building-wide",
  },
  {
    dimension: "Open science & deposition",
    before: "Vendor-locked formats; provenance lost when data leaves the instrument PC",
    after: "Open formats (JCAMP-DX, mzML, CSV) with the immutable raw archive and provenance attached",
  },
]

type LoopStep = {
  step: string
  body: string
}

const WORKED_EXAMPLE: LoopStep[] = [
  {
    step: "A student characterizes",
    body: "A freshly made compound goes in as a raw Bruker FID. SpectraCheck confirms the structure with DP4 96%, and flags a residual CDCl₃ peak at 7.26 ppm so it isn't mistaken for signal.",
  },
  {
    step: "Evidence stays visible",
    body: "Every assignment shows its reasoning — shift window, multiplicity, J-coupling, integration, and the HRMS exact mass that corroborates the formula. Nothing is a black-box verdict.",
  },
  {
    step: "SI writes itself",
    body: "A supporting-information table and a methods paragraph are generated from the analysis — instrument, solvent, processing recipe hash, software version, and per-signal assignments, all cited.",
  },
  {
    step: "A labmate reproduces it",
    body: "Months later a co-author replays the recipe hash and gets bit-identical output. The reviewer's reproducibility question answers itself.",
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
    title: "Immutable raw archive",
    body: "Every FID is SHA-256 hashed and never overwritten, so the original evidence behind a published figure survives every reprocess.",
  },
  {
    icon: GitBranch,
    title: "Recipe-hash reproducibility",
    body: "Every processing run links a recipe hash to the unchanged raw archive. Replay any prior date and get bit-identical output.",
  },
  {
    icon: Eye,
    title: "Transparent, explainable evidence",
    body: "No black box. Every category, confidence number, and assignment traces to the layer and source that produced it — ideal for teaching and review.",
  },
  {
    icon: Library,
    title: "Open formats, no lock-in",
    body: "JCAMP-DX, mzML, and CSV throughout. Your data stays portable for deposition, collaboration, and the next tool you use.",
  },
  {
    icon: AlertTriangle,
    title: "Contradiction warnings",
    body: "HRMS exact mass disagreeing with the NMR-implied formula raises a first-class warning before you publish — not after a reviewer finds it.",
  },
  {
    icon: ShieldCheck,
    title: "Your data stays yours",
    body: "Per-tenant isolation, GDPR-compliant residency, and a role-scoped event ledger keep each group's unpublished work private by default.",
  },
]

export function AcademicResearchPage() {
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
                    className="border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300"
                  >
                    <GraduationCap className="mr-1 h-3 w-3" aria-hidden />
                    Solution · Academic Research
                  </Badge>
                  <Badge variant="outline" className="text-muted-foreground">
                    Teaching · Research · Core facilities
                  </Badge>
                </div>
                <h1 className="mt-5 max-w-3xl text-4xl font-semibold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl">
                  Science your students can{" "}
                  <span style={{ color: "var(--mt-teal)" }}>see</span> — and your reviewers can
                  reproduce.
                </h1>
                <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted-foreground sm:text-xl">
                  MolTrace turns every spectrum into transparent, reproducible evidence. Confirm
                  structures, elucidate unknowns, run a busy core facility, and generate
                  publication-ready supporting information — with the reasoning kept visible and the
                  trail back to raw data intact.
                </p>
                <div className="mt-10 flex flex-wrap items-center gap-4">
                  <Button asChild size="lg" className="gap-2">
                    <Link href="/contact?reason=Academic%20Research">
                      Talk to us
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

              {/* Hero visual — publication / reproducibility card */}
              <aside className="relative overflow-hidden rounded-3xl border bg-card p-6 shadow-sm">
                <div className="flex items-center justify-between">
                  <p
                    className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                    style={{ color: "var(--mt-teal)" }}
                  >
                    Supporting info · auto-generated
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
                    Reproducible
                  </span>
                </div>
                <p className="mt-3 font-mono text-xs text-muted-foreground">
                  SI · methods.md · recipe r9c2…1d3a
                </p>
                <p className="mt-1 text-sm font-medium">Figure 2 · compound 4b characterization</p>

                <div className="mt-6 space-y-1.5">
                  {[
                    { k: "Instrument", v: "Bruker AVANCE 400 · ¹H 400 MHz" },
                    { k: "Solvent", v: "CDCl₃ · ref 7.26 ppm (auto)" },
                    { k: "Processing", v: "recipe r9c2…1d3a · replayable" },
                    { k: "Software", v: "MolTrace · version pinned" },
                    { k: "Assignments", v: "12 / 12 signals · each cited" },
                    { k: "Raw archive", v: "FID SHA-256 4f7a…b29e · vaulted" },
                  ].map((row) => (
                    <div
                      key={row.k}
                      className="flex items-center gap-3 rounded-md border bg-background/80 px-3 py-2"
                    >
                      <span
                        className="w-20 shrink-0 font-mono text-[9px] font-bold uppercase tracking-[0.12em]"
                        style={{ color: "var(--mt-teal)" }}
                      >
                        {row.k}
                      </span>
                      <span className="flex-1 truncate font-mono text-[11px]">{row.v}</span>
                      <CheckCircle2
                        className="h-3.5 w-3.5 shrink-0"
                        style={{ color: "var(--mt-teal)" }}
                        aria-hidden
                      />
                    </div>
                  ))}
                </div>
                <p className="mt-5 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                  every figure traces back to a raw FID
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
                Why academic labs
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Four problems every chemistry department knows.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Academic labs don't have a compliance department to absorb the busywork. They need
                reproducibility, teaching transparency, facility-wide consistency, and budget
                discipline — from the same tool, on day one.
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

        {/* ── Across the academic workflow ────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Across the academic workflow
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                From the teaching lab to the data repository.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                The same evidence object serves every context a department lives in — so what gets
                taught, characterized, and measured ends up legible in the paper and the deposited
                dataset too.
              </p>
            </div>

            <div className="mt-12 overflow-hidden rounded-2xl border bg-card">
              <div className="border-b bg-muted/40 px-4 py-2.5">
                <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
                  The workflow, at a glance
                </p>
              </div>
              <pre className="overflow-x-auto px-4 py-5 font-mono text-[11px] leading-relaxed text-foreground sm:px-8 sm:text-xs">
{`  Teaching ──► Bench ──► Core facility ──► Publication ──► Open science
     │           │            │                 │               │
     ▼           ▼            ▼                 ▼               ▼
  see the     confirm /    consistent QC     SI + methods    open formats
  reasoning   elucidate    every group       auto-composed   + provenance
  (no black   (NMR + MS)   (per-peak fit)    (each cited)    (deposit-ready)
   box)`}
              </pre>
            </div>

            <div className="mt-8 grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
              {CONTEXTS.map((ctx) => {
                const Icon = ctx.icon
                return (
                  <article
                    key={ctx.code}
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
                          {ctx.code}
                        </p>
                        <h3 className="text-base font-semibold tracking-tight">{ctx.name}</h3>
                      </div>
                    </div>
                    <ul className="mt-5 space-y-2">
                      {ctx.fits.map((fit) => (
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
                Six academic workflows, with their inputs and outputs.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Each is a typed pipeline that ships today. Inputs come from your instruments or your
                course materials; outputs land in the evidence stack, the SI composer, and the
                reproducible-methods record.
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
                Numbers you can check yourself.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Every figure below is reproducible from a publicly-described corpus or a shipped
                release note. The regression gate runs in CI on every detector change — the kind of
                rigor you'd expect from a paper, applied to the software.
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
                What changes for an academic group.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Most labs run characterization through vendor software, a spreadsheet, and a methods
                section written from memory. Here's what flips when the evidence — and its provenance
                — travels with the result.
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
                From a student's FID to a reproducible figure.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                A single characterization, followed from the instrument to the supporting
                information — and reproduced by a co-author months later.
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
                      The evidence engine behind every confirmation and elucidation.
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
                    <p className="text-sm font-semibold">Repho →</p>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      Plan methodology screens with fewer reactions to publishable conditions.
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
                href="https://docs.moltrace.co/guides/quickstart/"
                target="_blank"
                rel="noopener noreferrer"
                className="group flex items-center justify-between gap-4 rounded-2xl border bg-card p-5 transition-all hover:-translate-y-0.5 hover:shadow-md"
              >
                <div className="flex items-start gap-3">
                  <BookOpen
                    className="mt-0.5 h-5 w-5 shrink-0"
                    style={{ color: "var(--mt-teal)" }}
                    aria-hidden
                  />
                  <div>
                    <p className="text-sm font-semibold">Quick start →</p>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      Five minutes from sign-up to a reproducible, exported result.
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

        {/* ── Trust + transparency ────────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="grid gap-10 lg:grid-cols-[1fr_1.6fr]">
              <div>
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                  style={{ color: "var(--mt-teal)" }}
                >
                  Built for trust
                </p>
                <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                  Transparency and reproducibility, by construction.
                </h2>
                <p className="mt-4 text-base text-muted-foreground">
                  The same provenance machinery that satisfies a pharmaceutical inspector is exactly
                  what an academic group needs for a defensible paper and an honest classroom — open,
                  explainable, and reproducible by anyone who has the data.
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
                Bring your hardest spectrum.
              </h2>
              <p className="mt-4 text-base text-muted-foreground sm:text-lg">
                An unassigned unknown, a teaching example, or a backlog at the core facility — we'll
                show how MolTrace carries the evidence from the FID to a reproducible figure.
              </p>
              <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
                <Button asChild size="lg" className="gap-2">
                  <Link href="/contact?reason=Academic%20Research">
                    Talk to us
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
