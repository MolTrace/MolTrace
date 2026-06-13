import Link from "next/link"
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Atom,
  BadgeCheck,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileText,
  FlaskConical,
  GitBranch,
  Lock,
  Microscope,
  PlayCircle,
  ShieldCheck,
  Sparkles,
  Waves,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Footer } from "@/components/marketing/footer"
import { Header } from "@/components/marketing/header"

/**
 * Spectroscopy module page — full marketing-shell route at /spectroscopy.
 *
 * This is the canonical product overview for SpectraCheck, MolTrace's
 * spectroscopy intelligence engine. It links DOWN into the in-product
 * workspace at /spectracheck and stands at the top of the platform
 * funnel.
 *
 * Tone-and-stance differentiators (why this isn't a generic "Features"
 * page):
 *   1. Hero pairs an opinionated claim with an immediately scannable
 *      end-to-end workflow figure (no marketing word salad).
 *   2. The workflow is rendered as an actual visual diagram with named
 *      stages, not a list of bullet points.
 *   3. Modality-by-modality capability matrix with concrete inputs /
 *      outputs / file formats — credible to analysts at a glance.
 *   4. The 39-layer evidence stack rendered as a multi-band visual,
 *      not paragraphs of prose.
 *   5. Two-detector comparison table — the legacy / GSD honesty that no
 *      competitor exposes.
 *   6. Validation numbers up front (94.4% solvent detect, env Δ=2 gate,
 *      20-fixture regression).
 *   7. The closing-loop diagram showing spectroscopy → regulatory →
 *      reaction optimization.
 */

type WorkflowStage = {
  stage: string
  title: string
  detail: string
  outputs: string
}

const WORKFLOW: WorkflowStage[] = [
  {
    stage: "01",
    title: "Ingest",
    detail:
      "Raw FID archive (Bruker / Agilent-Varian) lands in the immutable vault. SHA-256 hashed. Vendor metadata extracted: SFO1/BF1 (Bruker) or sfrq/reffrq (Varian).",
    outputs: "Archive · vendor · field_mhz · acquisition params",
  },
  {
    stage: "02",
    title: "Process",
    detail:
      "Fourier transform + apodization + phasing + baseline correction. Every parameter recipe-hash-linked to the unchanged raw archive. Recipe is reproducible byte-for-byte.",
    outputs: "Processed spectrum (ppm + intensity) · processing_metadata",
  },
  {
    stage: "03",
    title: "Detect",
    detail:
      "Legacy detector (default) or GSD-Prompt-3 (experimental opt-in). Both surface the same envelope: peaks, environments, category_counts, environment_counts.",
    outputs: "Peaks · environments · category mix · per-peak fit metrics",
  },
  {
    stage: "04",
    title: "Categorize",
    detail:
      "Each peak auto-classified: compound / solvent / impurity / artifact / ¹³C satellite. Curated impurity-shift tables match labels (residual CHCl₃, methanol, acetic acid, BHT, …).",
    outputs: "Category · category_reason · impurity_match / solvent_hit",
  },
  {
    stage: "05",
    title: "Score",
    detail:
      "39-layer evidence stack scores candidate SMILES across NMR, HRMS, MS/MS, predicted shifts, fragmentation trees, and reaction history. Cross-modal contradictions surface as warnings.",
    outputs: "Ranked candidates · DP4 confidence · multi-layer evidence",
  },
  {
    stage: "06",
    title: "Report",
    detail:
      "Regulatory-ready structure-elucidation report composer. Every numerical claim is hyperlinked to its source. Human signoff required before release.",
    outputs: "Audit-grade report · ALCOA+ ledger entry",
  },
]

type Modality = {
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties; "aria-hidden"?: boolean }>
  name: string
  formats: string
  capabilities: string[]
  layers: string
}

const MODALITIES: Modality[] = [
  {
    icon: Waves,
    name: "1D NMR (¹H, ¹³C)",
    formats: "Raw FID · JCAMP-DX · CSV · vendor exports",
    capabilities: [
      "Bruker + Agilent-Varian FID parsing via nmrglue",
      "Solvent-aware shift windows + residual-peak masking",
      "Voigt / Lorentzian fitting with per-peak QC residuals",
      "Multiplet clustering for environment counting",
    ],
    layers: "Layers 22 · 24",
  },
  {
    icon: Atom,
    name: "2D NMR (COSY · HSQC · HMQC · HMBC)",
    formats: "Processed 2D NMR · vendor archives",
    capabilities: [
      "Guarded behind ENABLE_2D_NMR feature flag",
      "Cross-peak detection + connectivity assignment",
      "Symmetrisation + denoise pipelines",
      "Evidence consumed by candidate-scoring layers",
    ],
    layers: "Layers 23 · 25",
  },
  {
    icon: Microscope,
    name: "HRMS · MS/MS",
    formats: "mzML · mzXML · processed peak lists",
    capabilities: [
      "HRMS exact-mass candidate + bounded formula search",
      "MS1 adduct + isotope pattern inference",
      "MS/MS fragmentation tree + diagnostic neutral losses",
      "Processed MS/MS annotation (precursor, neutral loss)",
    ],
    layers: "Layers 29 · 30 · 31 · 32",
  },
  {
    icon: Activity,
    name: "LC-MS features",
    formats: "mzML · mzXML · processed peak tables",
    capabilities: [
      "Feature detection + EIC / XIC + peak purity",
      "Feature grouping + blank subtraction + RT alignment",
      "Cross-modal corroboration with NMR-implied formula",
      "Contradictions surface as first-class warnings",
    ],
    layers: "Layers 35 · 36 · 37",
  },
]

type CategorySwatch = {
  key: string
  label: string
  example: string
  swatch: string
  dot: string
}

const PEAK_CATEGORIES: CategorySwatch[] = [
  {
    key: "compound",
    label: "Compound",
    example: "Target analyte signals — passed to candidate scoring.",
    swatch: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-900",
    dot: "bg-emerald-500",
  },
  {
    key: "solvent",
    label: "Solvent",
    example: "Residual CHCl₃ at 7.26, DMSO-d₆ at 2.50, CD₃OD at 3.31. Auto-masked from candidate scoring.",
    swatch: "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/40 dark:text-sky-300 dark:border-sky-900",
    dot: "bg-sky-500",
  },
  {
    key: "impurity",
    label: "Impurity",
    example: "Curated shift-table match — methanol, ethyl acetate, acetic acid, DMF, dichloromethane, BHT, …",
    swatch: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900",
    dot: "bg-amber-500",
  },
  {
    key: "artifact",
    label: "Artifact",
    example: "Phasing distortions, sidebands, t₁ noise. Excluded from candidate scoring; flagged for reviewer.",
    swatch: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-900",
    dot: "bg-rose-500",
  },
  {
    key: "13C_satellite",
    label: "¹³C satellite",
    example: "Spinning sidebands of strong ¹H peaks at natural-abundance ¹³C positions. Down-weighted.",
    swatch: "bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-950/40 dark:text-violet-300 dark:border-violet-900",
    dot: "bg-violet-500",
  },
]

type Validation = {
  value: string
  label: string
  detail: string
}

const VALIDATION: Validation[] = [
  {
    value: "94.4%",
    label: "Solvent auto-detect",
    detail:
      "NMRShiftDB2 20-fixture corpus. 17 of 18 fixtures with a reference. Strict gate target: 95%.",
  },
  {
    value: "Δ ≤ 2",
    label: "Compound-count median",
    detail:
      "Median absolute peak-count delta vs expert-curated references on the HMDB-style multiplet-line corpus. Strict gate cleared.",
  },
  {
    value: "20",
    label: "Fixture regression gate",
    detail:
      "Every detector change runs against a curated corpus before merge. CI fails by fixture_id when any single fixture drifts > 50%.",
  },
  {
    value: "39",
    label: "Evidence layers",
    detail:
      "Built additively Weeks 22 → 39. Every layer's output is a typed Pydantic model with stable JSON keys.",
  },
]

type DetectorRow = {
  capability: string
  legacy: string
  gsd: string
  winner?: "legacy" | "gsd" | "tie"
}

const DETECTOR_COMPARE: DetectorRow[] = [
  {
    capability: "Peak detection on NMRShiftDB2 corpus",
    legacy: "Median Δ = 14",
    gsd: "Median Δ = 19 (Δ = 5 compound-only)",
    winner: "tie",
  },
  {
    capability: "Solvent auto-detect (structured field)",
    legacy: "Inferred via impurity-match table",
    gsd: "94.4% on the 20-fixture corpus",
    winner: "gsd",
  },
  {
    capability: "Per-peak fit QC (χ²ᵣ, RMSE, FWHM, S/N, baseline σ)",
    legacy: "Now exposed (Phase 24, normalised pending)",
    gsd: "Native — normalised to baseline σ",
  },
  {
    capability: "Multiplicity + J-values + integration",
    legacy: "Native — multiplet notation per peak",
    gsd: "Not exposed",
    winner: "legacy",
  },
  {
    capability: "Candidate structure matching · DP4 ranking",
    legacy: "Full evidence pipeline",
    gsd: "Peak detection only — no candidate matching",
    winner: "legacy",
  },
  {
    capability: "Category classification (5-set)",
    legacy: "Open string (detection + chemical-region)",
    gsd: "Closed enum, native",
  },
  {
    capability: "Promotion status",
    legacy: "Default backend",
    gsd: "Experimental · opt-in · gated",
  },
]

type Loop = {
  step: string
  body: string
}

const CLOSING_LOOP: Loop[] = [
  {
    step: "Spectroscopy detects",
    body: "Impurity peak at 2.10 ppm matched to acetic acid CH₃ within 0.001 ppm. Confidence 93%.",
  },
  {
    step: "Regulatory routes",
    body: "Acetic acid is ICH Q3C Class 3 — no need for action below 5000 ppm. Action item raised only if observed concentration crosses threshold.",
  },
  {
    step: "Reaction optimization constrains",
    body: "Next experiment's reaction recipe receives the impurity limit as a Bayesian prior. Solvent + workup updated automatically.",
  },
  {
    step: "Loop closes",
    body: "Re-acquired spectrum confirms impurity below threshold. Audit ledger records every step from FID hash to recipe update.",
  },
]

export function SpectroscopyPage() {
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
                    className="border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300"
                  >
                    <Waves className="mr-1 h-3 w-3" aria-hidden />
                    Module · SpectraCheck
                  </Badge>
                  <Badge variant="outline" className="text-muted-foreground">
                    Layers 22 → 39
                  </Badge>
                </div>
                <h1 className="mt-5 max-w-3xl text-4xl font-semibold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl">
                  Spectroscopy with an{" "}
                  <span style={{ color: "var(--mt-teal)" }}>audit trail</span> — from raw FID to regulatory-ready.
                </h1>
                <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted-foreground sm:text-xl">
                  SpectraCheck is the spectroscopy intelligence engine inside MolTrace. NMR, LC-MS,
                  HRMS, and MS/MS arrive as one evidence stack — typed, traceable, multi-modal by
                  default. Every numerical claim links back to the spectrum it came from.
                </p>
                <div className="mt-10 flex flex-wrap items-center gap-4">
                  <Button asChild size="lg" className="gap-2">
                    <Link href="/spectracheck">
                      Open SpectraCheck
                      <ArrowRight className="h-4 w-4" />
                    </Link>
                  </Button>
                  <Button asChild size="lg" variant="outline" className="gap-2">
                    <Link href="/contact?reason=Request%20a%20demo">
                      Request a demo
                      <PlayCircle className="h-4 w-4" />
                    </Link>
                  </Button>
                </div>
              </div>

              {/* Hero visual: layered evidence stack glyph */}
              <aside className="relative overflow-hidden rounded-3xl border bg-card p-6 shadow-sm">
                <div
                  aria-hidden
                  className="absolute inset-0 opacity-20"
                  style={{
                    backgroundImage:
                      "repeating-linear-gradient(0deg, transparent, transparent 22px, color-mix(in oklab, var(--mt-teal) 30%, transparent) 22px, color-mix(in oklab, var(--mt-teal) 30%, transparent) 23px)",
                  }}
                />
                <div className="relative">
                  <p
                    className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                    style={{ color: "var(--mt-teal)" }}
                  >
                    Evidence stack · live snapshot
                  </p>
                  <p
                    className="mt-4 font-mono text-5xl font-bold tabular-nums tracking-tight sm:text-6xl"
                    style={{ color: "var(--mt-teal)" }}
                  >
                    39
                  </p>
                  <p className="mt-2 text-sm font-medium text-foreground">layers active</p>

                  <div className="mt-8 space-y-1.5">
                    {[
                      { label: "L22", title: "¹H / ¹³C scoring vs SMILES", on: true },
                      { label: "L24", title: "Immutable raw FID vault", on: true },
                      { label: "L28", title: "Predicted-NMR matching", on: true },
                      { label: "L29", title: "HRMS exact-mass candidate", on: true },
                      { label: "L32", title: "MS/MS fragmentation tree", on: true },
                      { label: "L33", title: "Cross-modal confidence", on: true },
                      { label: "L34", title: "Regulatory report composer", on: true },
                      { label: "L37", title: "LC-MS feature grouping", on: true },
                    ].map((layer) => (
                      <div
                        key={layer.label}
                        className="flex items-center gap-3 rounded-md border bg-background/80 px-3 py-1.5"
                      >
                        <span
                          className="font-mono text-[10px] font-bold tabular-nums"
                          style={{ color: "var(--mt-teal)" }}
                        >
                          {layer.label}
                        </span>
                        <span className="flex-1 truncate text-xs">{layer.title}</span>
                        <span
                          className="h-1.5 w-1.5 rounded-full"
                          style={{ backgroundColor: "var(--mt-teal)" }}
                          aria-label="active"
                        />
                      </div>
                    ))}
                  </div>
                  <p className="mt-5 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                    + 31 more · additive, never destructive
                  </p>
                </div>
              </aside>
            </div>
          </div>
        </section>

        {/* ── Workflow figure ─────────────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                The pipeline, end-to-end
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Six stages. Recipe-hash-linked. Audit-grade.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Every stage emits a typed Pydantic model with stable JSON keys. Every emission is
                pinned to the immutable raw archive by SHA-256 + recipe hash. You can replay any
                report from any prior date and get bit-identical output.
              </p>
            </div>

            <ol className="mt-12 grid gap-4 lg:grid-cols-3">
              {WORKFLOW.map((s, idx) => (
                <li
                  key={s.stage}
                  className="relative flex flex-col rounded-2xl border bg-card p-6 shadow-sm sm:p-7"
                  style={{ borderTop: "3px solid var(--mt-teal)" }}
                >
                  <div className="flex items-center gap-3">
                    <span
                      className="font-mono text-3xl font-bold tabular-nums tracking-tight"
                      style={{ color: "var(--mt-teal)" }}
                    >
                      {s.stage}
                    </span>
                    {idx < WORKFLOW.length - 1 ? (
                      <ArrowRight
                        className="hidden h-5 w-5 lg:inline"
                        style={{ color: "var(--mt-teal)" }}
                        aria-hidden
                      />
                    ) : null}
                  </div>
                  <h3 className="mt-3 text-lg font-semibold tracking-tight">{s.title}</h3>
                  <p className="mt-3 flex-1 text-sm leading-relaxed text-muted-foreground">
                    {s.detail}
                  </p>
                  <div className="mt-5 border-t pt-3">
                    <p className="font-mono text-[9px] uppercase tracking-[0.2em] text-muted-foreground">
                      Outputs
                    </p>
                    <p className="mt-1.5 font-mono text-[11px] leading-relaxed text-foreground">
                      {s.outputs}
                    </p>
                  </div>
                </li>
              ))}
            </ol>

            {/* Inline pipeline diagram for at-a-glance scan */}
            <div className="mt-10 overflow-hidden rounded-2xl border bg-card">
              <div className="border-b bg-muted/40 px-4 py-2.5">
                <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
                  At a glance
                </p>
              </div>
              <pre className="overflow-x-auto px-4 py-5 font-mono text-[11px] leading-relaxed text-foreground sm:px-8 sm:text-xs">
{`  Raw FID  ──►  Process FID  ──►  Detect peaks  ──►  Categorise
     │              │                  │                   │
     │              │                  │                   ▼
     │              │                  │            Cross-modal score
     │              │                  │             (HRMS · MS/MS · 2D NMR)
     │              │                  │                   │
     ▼              ▼                  ▼                   ▼
  SHA-256       recipe_hash        per-peak QC      candidate ranking + DP4
  immutable     reproducible       (χ²ᵣ, RMSE,      with audit-grade trail
  vault         processing         FWHM, S/N)        and human signoff gate`}
              </pre>
            </div>
          </div>
        </section>

        {/* ── Modalities ──────────────────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Modalities supported
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                One evidence stack. Four modalities. No silos.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                A pharmaceutical R&amp;D group operates across NMR + LC-MS + HRMS + MS/MS
                simultaneously. SpectraCheck fuses these as one evidence stack — not separate apps
                — and uses cross-modal contradictions (HRMS exact mass disagreeing with
                NMR-implied formula) as first-class warnings.
              </p>
            </div>
            <div className="mt-12 grid gap-6 lg:grid-cols-2">
              {MODALITIES.map((mod) => {
                const Icon = mod.icon
                return (
                  <article
                    key={mod.name}
                    className="rounded-2xl border bg-card p-6 shadow-sm sm:p-7"
                    style={{ borderLeft: "3px solid var(--mt-teal)" }}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-4">
                        <span
                          className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl"
                          style={{
                            backgroundColor: "var(--mt-teal-soft)",
                            color: "var(--mt-teal)",
                          }}
                        >
                          <Icon className="h-5 w-5" aria-hidden />
                        </span>
                        <div>
                          <h3 className="text-lg font-semibold tracking-tight sm:text-xl">
                            {mod.name}
                          </h3>
                          <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                            {mod.layers}
                          </p>
                        </div>
                      </div>
                    </div>
                    <p className="mt-5 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
                      Accepts
                    </p>
                    <p className="mt-1.5 font-mono text-xs leading-relaxed text-foreground">
                      {mod.formats}
                    </p>
                    <ul className="mt-5 space-y-2">
                      {mod.capabilities.map((cap) => (
                        <li
                          key={cap}
                          className="flex items-start gap-2.5 text-sm leading-relaxed text-muted-foreground"
                        >
                          <CheckCircle2
                            className="mt-0.5 h-3.5 w-3.5 shrink-0"
                            style={{ color: "var(--mt-teal)" }}
                            aria-hidden
                          />
                          <span>{cap}</span>
                        </li>
                      ))}
                    </ul>
                  </article>
                )
              })}
            </div>
          </div>
        </section>

        {/* ── Auto-classification ─────────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="grid gap-12 lg:grid-cols-[1fr_1.4fr]">
              <div>
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                  style={{ color: "var(--mt-teal)" }}
                >
                  Auto-classification
                </p>
                <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                  Every peak gets a category.
                </h2>
                <p className="mt-4 text-base text-muted-foreground">
                  Peaks aren't just numbers. SpectraCheck applies a 5-category taxonomy — backed by
                  curated impurity-shift tables and solvent residual-peak windows — so reviewers
                  can scan a peak list and immediately see what's signal, what's noise, and what
                  needs follow-up.
                </p>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                  Categories are exposed as structured fields ({" "}
                  <code className="font-mono text-foreground">peak.category</code>,{" "}
                  <code className="font-mono text-foreground">peak.solvent_hit</code>,{" "}
                  <code className="font-mono text-foreground">peak.impurity_match</code>) — not
                  buried in a confidence number. Each impurity match cites the reference shift, the
                  observed shift, and the delta.
                </p>
              </div>
              <ul className="space-y-3">
                {PEAK_CATEGORIES.map((cat) => (
                  <li
                    key={cat.key}
                    className="flex items-start gap-3.5 rounded-xl border bg-card p-4"
                  >
                    <span
                      className={`mt-1 inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em] ${cat.swatch}`}
                    >
                      <span className={`h-1.5 w-1.5 rounded-full ${cat.dot}`} aria-hidden />
                      {cat.label}
                    </span>
                    <p className="flex-1 text-sm leading-relaxed text-muted-foreground">
                      {cat.example}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        {/* ── Detector backends ───────────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Two detectors, one envelope
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Legacy by default. GSD by opt-in. Both behind the same gate.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                We ship a stable, evidence-pipeline legacy detector as the default. The experimental
                GSD-Prompt-3 backend (industry-standard peak detection with auto-classification)
                ships as opt-in until it clears a published validation gate. Both return the same{" "}
                <code className="font-mono text-foreground">{`{ peaks, environments, category_counts }`}</code>{" "}
                envelope so consumer code is detector-agnostic.
              </p>
            </div>
            <div className="mt-12 overflow-hidden rounded-2xl border bg-card shadow-sm">
              <table className="w-full text-left text-sm">
                <thead className="bg-muted/40 font-mono uppercase tracking-[0.12em] text-[10px] text-muted-foreground">
                  <tr>
                    <th className="px-5 py-3">Capability</th>
                    <th className="px-5 py-3">Legacy (default)</th>
                    <th className="px-5 py-3">GSD (experimental)</th>
                  </tr>
                </thead>
                <tbody>
                  {DETECTOR_COMPARE.map((row, idx) => (
                    <tr
                      key={row.capability}
                      className={idx % 2 === 0 ? "border-t" : "border-t bg-muted/20"}
                    >
                      <td className="px-5 py-3.5 align-top text-foreground">{row.capability}</td>
                      <td
                        className={`px-5 py-3.5 align-top text-muted-foreground ${
                          row.winner === "legacy" ? "font-semibold text-foreground" : ""
                        }`}
                      >
                        {row.legacy}
                      </td>
                      <td
                        className={`px-5 py-3.5 align-top text-muted-foreground ${
                          row.winner === "gsd" ? "font-semibold text-foreground" : ""
                        }`}
                      >
                        {row.gsd}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-5 font-mono text-xs text-muted-foreground">
              Full A/B methodology + per-fixture numbers published in{" "}
              <Link
                href="/blog"
                className="text-foreground underline-offset-4 hover:underline"
              >
                Field notes
              </Link>{" "}
              and the technical white paper §3.1.
            </p>
          </div>
        </section>

        {/* ── Validation numbers ──────────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Measured, not claimed
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                The numbers we publish.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Every claim below is reproducible from the publicly-described corpus. The
                regression gate runs in CI; any drift larger than 50% on any single fixture fails
                the build with the fixture_id called out by name.
              </p>
            </div>
            <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {VALIDATION.map((v) => (
                <div
                  key={v.label}
                  className="rounded-2xl border bg-card p-6 shadow-sm"
                  style={{ borderTop: "3px solid var(--mt-teal)" }}
                >
                  <p
                    className="font-mono text-4xl font-bold tabular-nums tracking-tight sm:text-5xl"
                    style={{ color: "var(--mt-teal)" }}
                  >
                    {v.value}
                  </p>
                  <p className="mt-2 font-mono text-[10px] font-bold uppercase tracking-[0.18em]">
                    {v.label}
                  </p>
                  <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{v.detail}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Closing loop ────────────────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                The closing loop
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Spectroscopy isn't the end. It's the start of a loop.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Most analytical platforms stop at "the spectrum has been processed." Ours doesn't.
                A real worked example with acetic acid impurity:
              </p>
            </div>
            <ol className="mt-12 grid gap-4 lg:grid-cols-4">
              {CLOSING_LOOP.map((step, idx) => (
                <li
                  key={step.step}
                  className="relative flex flex-col rounded-2xl border bg-card p-6 shadow-sm sm:p-7"
                  style={{ borderTop: "3px solid var(--mt-teal)" }}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="inline-flex h-7 w-7 items-center justify-center rounded-full font-mono text-[11px] font-bold tabular-nums"
                      style={{
                        backgroundColor: "var(--mt-teal-soft)",
                        color: "var(--mt-teal)",
                      }}
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

            {/* Module-cross-link cards */}
            <div className="mt-10 grid gap-4 sm:grid-cols-2">
              <Link
                href="https://docs.moltrace.co/guides/modules/regulatory/"
                target="_blank"
                rel="noopener noreferrer"
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
                      Routes the impurity to ICH Q3C / Q3D, raises action items, drafts dossier
                      section.
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
                href="https://docs.moltrace.co/guides/modules/optimization/"
                target="_blank"
                rel="noopener noreferrer"
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
                      Feeds the impurity limit back into the reaction recipe as a Bayesian prior on
                      the next experiment.
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

        {/* ── Trust signals + audit ───────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="grid gap-10 lg:grid-cols-[1fr_1.6fr]">
              <div>
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                  style={{ color: "var(--mt-teal)" }}
                >
                  Audit & compliance
                </p>
                <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                  Designed against the regulations you'll be audited on.
                </h2>
                <p className="mt-4 text-base text-muted-foreground">
                  SpectraCheck isn't compliant by accident. The audit ledger, the immutable raw
                  vault, the recipe-hash provenance, and the human-signoff release gate were
                  designed against ICH Q2(R2) ALCOA+, the FDA's January 2025 AI framework, and the
                  EMA reflection paper from day one.
                </p>
              </div>
              <ul className="space-y-3">
                {[
                  {
                    icon: Database,
                    title: "Immutable raw vault",
                    body: "Every FID is SHA-256 hashed, vault path policy enforced, and never overwritten.",
                  },
                  {
                    icon: GitBranch,
                    title: "Recipe-hash provenance",
                    body: "Every processing run links a recipe hash to the unchanged raw archive. Bit-identical replay forever.",
                  },
                  {
                    icon: ClipboardCheck,
                    title: "Human signoff queue",
                    body: "No regulatory document is released without an explicit qualified-human attribution.",
                  },
                  {
                    icon: BadgeCheck,
                    title: "ALCOA+ audit ledger",
                    body: "Attributable · Legible · Contemporaneous · Original · Accurate · Complete · Consistent · Enduring · Available.",
                  },
                  {
                    icon: AlertTriangle,
                    title: "Cross-modal contradiction warnings",
                    body: "HRMS exact mass disagreeing with NMR-implied formula raises a first-class warning before signoff.",
                  },
                  {
                    icon: Lock,
                    title: "Tenant isolation by default",
                    body: "SOC 2 Type II controls, GDPR-compliant data residency, role-scoped audit-event ledger.",
                  },
                ].map((item) => {
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
                See it on your own spectra.
              </h2>
              <p className="mt-4 text-base text-muted-foreground sm:text-lg">
                Open SpectraCheck on the platform or schedule a 30-minute walkthrough on a real
                analyte from your workflow.
              </p>
              <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
                <Button asChild size="lg" className="gap-2">
                  <Link href="/spectracheck">
                    Open SpectraCheck
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="outline" className="gap-2">
                  <Link href="/contact?reason=Request%20a%20demo">
                    Talk to a specialist
                    <PlayCircle className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="ghost" className="gap-2">
                  <Link
                    href="https://docs.moltrace.co/guides/modules/spectracheck/"
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
