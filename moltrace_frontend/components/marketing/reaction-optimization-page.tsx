import Link from "next/link"
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  CheckCircle2,
  Database,
  DollarSign,
  FileText,
  FlaskConical,
  GitBranch,
  History,
  Microscope,
  PlayCircle,
  Repeat,
  ShieldCheck,
  Sparkles,
  Target,
  Thermometer,
  TrendingUp,
  XCircle,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Footer } from "@/components/marketing/footer"
import { Header } from "@/components/marketing/header"

/**
 * Reaction Optimization (ReactionIQ) module page — full marketing-shell
 * route at /reaction-optimization.
 *
 * Differentiation from /spectroscopy and /regulatory-hub:
 *   - Hero visual is a LIVE experiment-campaign snapshot showing
 *     round-by-round Bayesian iterations with acquisition function +
 *     measured vs predicted yield. (Spectroscopy = layer stack;
 *     Regulatory = audit ledger.)
 *   - Pipeline framed around the optimization loop: Define → Constrain
 *     → Propose → Run → Measure → Update → Decide.
 *   - "Frameworks coverage" pattern becomes a "Methods we ship" matrix
 *     (Bayesian / Multi-objective / Active learning / Closed-loop).
 *   - Comparison table is "Trial-and-error vs ReactionIQ".
 *   - Closing loop completes the three-pillar narrative: Spectroscopy
 *     evidence + Regulatory constraints → ReactionIQ next experiment.
 *
 * Backend grounding: nmrcheck/reaction_bo.py (run_bayesian_optimization,
 * expected_improvement, acquisition_score), reaction_advisor.py,
 * reaction_store.py. Methods reference matches what the backend ships.
 */

type Stage = {
  stage: string
  title: string
  detail: string
  artifact: string
}

const PIPELINE: Stage[] = [
  {
    stage: "01",
    title: "Define",
    detail:
      "Set the design space: input variables (solvent, temperature, equivalents, time, catalyst loading), discrete or continuous bounds, encoded categoricals. The same Pydantic model the backend's ConditionDomain consumes.",
    artifact: "design_space · variable_bounds · categoricals",
  },
  {
    stage: "02",
    title: "Constrain",
    detail:
      "Hard limits from Regentry auto-load: ICH Q3C residual-solvent ceilings, Q3D PDE limits, M7 nitrosamine alerts. Plus safety + cost guardrails from your operational profile.",
    artifact: "objective_profile · cost · safety · regulatory_priors",
  },
  {
    stage: "03",
    title: "Propose",
    detail:
      "Bayesian acquisition over a Gaussian-process surrogate. Expected Improvement (single objective), q-Noisy Expected Hypervolume Improvement (multi-objective batch), upper confidence bound for exploration. Reproducible — same seed, same batch.",
    artifact: "recommendation_batch · acquisition_score · expected_improvement",
  },
  {
    stage: "04",
    title: "Run",
    detail:
      "Execute the proposed batch in the lab (manual) or on an autonomous platform (closed-loop). Recipe + parameters pinned by recipe-hash; cross-modal evidence pulled in automatically when the batch finishes.",
    artifact: "run_id · recipe_hash · operator · timestamp",
  },
  {
    stage: "05",
    title: "Measure",
    detail:
      "Spectroscopy evidence lands automatically. Yield, purity, selectivity, impurity profile, residual solvent — all per-condition, all hyperlinked to source spectra.",
    artifact: "yield · purity · impurity_set · ee · spectra_uris",
  },
  {
    stage: "06",
    title: "Update",
    detail:
      "Surrogate refit with the new observation. Posterior mean + variance over the design space recompute. Constraint-aware: violated points get masked out before the next proposal.",
    artifact: "posterior · constraint_mask · pareto_set",
  },
  {
    stage: "07",
    title: "Decide",
    detail:
      "Continue, stop, or pivot. Stopping rules built in: hypervolume convergence, budget exhaustion, hyper-parameter saturation. Human reviewer signs every campaign decision into the audit ledger.",
    artifact: "decision · rationale · reviewer · audit_event",
  },
]

type Method = {
  acronym: string
  full: string
  scope: string
  bullets: string[]
}

const METHODS: Method[] = [
  {
    acronym: "BO",
    full: "Bayesian Optimization",
    scope: "Single-objective · model-based",
    bullets: [
      "Gaussian-process surrogate with Matern / RBF kernels",
      "Expected Improvement (EI) + UCB acquisition",
      "Categorical encoding for solvents, catalysts, additives",
      "Reproducible by seed — same campaign re-runs bit-identically",
      "Backend: run_bayesian_optimization() · acquisition_score",
    ],
  },
  {
    acronym: "MOBO",
    full: "Multi-Objective Bayesian Optimization",
    scope: "Pareto-frontier · batch-aware",
    bullets: [
      "Yield × purity × cost × impurity-load trade-off",
      "q-Noisy Expected Hypervolume Improvement (qNEHVI)",
      "Batch recommendations — propose N reactions at once",
      "Pareto-set visualisation with non-dominated frontier",
      "Diversity penalty against redundant proposals",
    ],
  },
  {
    acronym: "AL",
    full: "Active Learning",
    scope: "Uncertainty-driven · explore + exploit",
    bullets: [
      "Variance-weighted sampling for under-explored regions",
      "Curiosity-driven probes inside safety guardrails",
      "Useful for discovery campaigns, not optimisation",
      "Integrates with literature priors + predicted-shift models",
      "Stops automatically when surrogate variance plateaus",
    ],
  },
  {
    acronym: "CL",
    full: "Closed-Loop Autonomous",
    scope: "Robot-driven · continuous campaign",
    bullets: [
      "Direct integration with autonomous synthesis platforms",
      "Spectroscopy auto-acquired between rounds",
      "Hands-off campaigns running 24/7 with audit attribution",
      "Safety abort triggers wired to live sensor streams",
      "Reviewer signs off pivots, not individual rounds",
    ],
  },
]

type UseCase = {
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties; "aria-hidden"?: boolean }>
  name: string
  blurb: string
  inputs: string
  outputs: string
}

const USE_CASES: UseCase[] = [
  {
    icon: Target,
    name: "Reaction screening",
    blurb:
      "Hit-finding across solvent / base / catalyst combinatorial space. Discrete-categorical Bayesian search with diversity-aware proposals.",
    inputs: "Categorical design space · screening budget",
    outputs: "Top-N hits · uncertainty bounds · suggested follow-up",
  },
  {
    icon: TrendingUp,
    name: "Yield + selectivity optimisation",
    blurb:
      "Continuous-variable optimisation over temperature, equivalents, residence time. Multi-objective when selectivity matters as much as yield.",
    inputs: "Continuous bounds · objective weights",
    outputs: "Pareto frontier · best-by-objective conditions",
  },
  {
    icon: AlertTriangle,
    name: "Impurity suppression",
    blurb:
      "Regulatory-Hub impurity limits become hard constraints. Optimiser proposes only conditions predicted to clear ICH Q3A/Q3B thresholds.",
    inputs: "Impurity limits from regulatory · prior runs",
    outputs: "Compliant conditions · constraint-aware ranking",
  },
  {
    icon: DollarSign,
    name: "Cost-aware development",
    blurb:
      "Cost surrogate co-trained alongside yield. Proposes the cheapest condition that still hits the objective — useful for late-stage process work.",
    inputs: "Reagent unit costs · time budget · operator load",
    outputs: "Cost-Pareto frontier · sensitivity report",
  },
  {
    icon: Thermometer,
    name: "Conditions for scale-up",
    blurb:
      "Optimises for robustness at scale: temperature insensitivity, mixing-time tolerance, work-up reproducibility. Variance-weighted objective.",
    inputs: "Lab-scale data · scale-up risk profile",
    outputs: "Robust conditions · sensitivity heatmap",
  },
  {
    icon: Repeat,
    name: "Method-development DOE",
    blurb:
      "HPLC method dev, work-up optimisation, crystallisation polymorph search. Same engine, different objectives — purity + recovery + crystal habit.",
    inputs: "Design variables · purity targets",
    outputs: "Validated method · Q2(R2)-ready parameters",
  },
]

type CampaignRow = {
  round: string
  acquisition: string
  proposed: string
  measured: string
  status: "explore" | "exploit" | "constrained" | "best"
}

const CAMPAIGN_SAMPLE: CampaignRow[] = [
  {
    round: "01",
    acquisition: "Latin Hypercube · seed",
    proposed: "T 25 °C · 1.2 eq · DCM · 4 h",
    measured: "yield 41% · imp 3.2% · cost low",
    status: "explore",
  },
  {
    round: "02",
    acquisition: "EI · α 0.84",
    proposed: "T 50 °C · 1.5 eq · DCM · 6 h",
    measured: "yield 67% · imp 1.8% · cost low",
    status: "exploit",
  },
  {
    round: "03",
    acquisition: "qNEHVI batch · k=3",
    proposed: "T 65 °C · 1.5 eq · MeCN · 8 h",
    measured: "yield 74% · imp 1.1% · cost mid",
    status: "exploit",
  },
  {
    round: "04",
    acquisition: "UCB · β 1.6",
    proposed: "T 80 °C · 2.0 eq · MeCN · 4 h",
    measured: "ABORT · imp 5.8% > Q3C cap",
    status: "constrained",
  },
  {
    round: "05",
    acquisition: "EI · constrained",
    proposed: "T 60 °C · 1.8 eq · MeCN · 6 h",
    measured: "yield 81% · imp 0.7% · cost mid",
    status: "best",
  },
]

const STATUS_CHIP: Record<CampaignRow["status"], { label: string; chip: string; dot: string }> = {
  explore: {
    label: "Explore",
    chip: "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/40 dark:text-sky-300 dark:border-sky-900",
    dot: "bg-sky-500",
  },
  exploit: {
    label: "Exploit",
    chip: "bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-950/40 dark:text-violet-300 dark:border-violet-900",
    dot: "bg-violet-500",
  },
  constrained: {
    label: "Constraint",
    chip: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-900",
    dot: "bg-rose-500",
  },
  best: {
    label: "Best so far",
    chip: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-900",
    dot: "bg-emerald-500",
  },
}

type Comparison = {
  dimension: string
  trialAndError: string
  reactioniq: string
}

const COMPARISON: Comparison[] = [
  {
    dimension: "Experiment selection",
    trialAndError: "Intuition + last-week's lab meeting + grad-school heuristics",
    reactioniq: "Acquisition-function-driven · Expected Improvement over the live surrogate",
  },
  {
    dimension: "Constraint handling",
    trialAndError: "Hope the operator remembers the impurity limit · catch in QC later",
    reactioniq: "Hard constraint at proposal time · violated points masked before the optimiser ever sees them",
  },
  {
    dimension: "Batch parallelism",
    trialAndError: "One reaction at a time · serialised round-trip on the bench",
    reactioniq: "qNEHVI batch proposes N diverse runs · plate-aware suggestions",
  },
  {
    dimension: "Replay 6 months later",
    trialAndError: "Lab notebook + memory · 'we tried that, didn't work, can't remember why'",
    reactioniq: "Recipe-hash replay · same surrogate, same posterior, same proposal — forever",
  },
  {
    dimension: "Stopping decision",
    trialAndError: "Run until budget runs out · or until someone gets frustrated",
    reactioniq: "Hypervolume convergence · explicit stopping criteria · auditable decision",
  },
  {
    dimension: "Cross-module evidence",
    trialAndError: "Yield in a spreadsheet · impurity in a PDF · cost in an email",
    reactioniq: "One typed record per round · spectra hyperlinked · cost + impurity + audit entry together",
  },
]

type LoopStep = {
  step: string
  body: string
}

const CROSS_MODULE_LOOP: LoopStep[] = [
  {
    step: "Spectroscopy says",
    body: "Round 4 shows acetic acid impurity at 2.10 ppm climbed to 5.8% — over the ICH Q3C Class 3 informational threshold for this drug substance.",
  },
  {
    step: "Regentry routes",
    body: "Constraint flips from 'informational' to 'hard limit' for subsequent rounds. ReactionIQ receives the new constraint vector via the typed cross-module API.",
  },
  {
    step: "ReactionIQ reacts",
    body: "Surrogate masks the violating region. Round 5 acquisition function only proposes conditions predicted to keep acetic acid below 2%. Result: 81% yield, 0.7% impurity.",
  },
  {
    step: "Audit ledger records",
    body: "Cross-module handoff captured as a single audit_event with full provenance. Inspector can replay every decision from FID hash to recipe update.",
  },
]

type TrustPillar = {
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties; "aria-hidden"?: boolean }>
  title: string
  body: string
}

const TRUST: TrustPillar[] = [
  {
    icon: GitBranch,
    title: "Seed-reproducible campaigns",
    body: "Same design space + same seed + same observations = same proposals. Forever. Recipe-hash-linked surrogate state pinned per round.",
  },
  {
    icon: ShieldCheck,
    title: "Constraint-aware by design",
    body: "Regulatory limits, safety thresholds, and cost ceilings enter the optimiser as hard constraints — not soft hints. No proposal ever violates a known limit.",
  },
  {
    icon: BadgeCheck,
    title: "Human signoff per pivot",
    body: "AI proposes batches. Humans approve campaigns. Every pivot (stop, continue, escalate) is signed and recorded with reviewer + role + rationale.",
  },
  {
    icon: AlertTriangle,
    title: "Safety abort wired live",
    body: "Closed-loop campaigns include live sensor streams. Out-of-bounds temperature / pressure / off-gas triggers immediate abort + ledger entry.",
  },
  {
    icon: Database,
    title: "Spectra linked per round",
    body: "Every measured outcome carries the SpectraCheck SHA-256 of the source spectrum + the regulatory verdict + the cost line — one row, full provenance.",
  },
  {
    icon: History,
    title: "Campaign replay forever",
    body: "Re-derive any historic Pareto front, any historic proposal, any historic decision from any prior date. Bit-identical, recipe-hash-pinned.",
  },
]

export function ReactionOptimizationPage() {
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
                    className="border-violet-300 bg-violet-50 text-violet-700 dark:border-violet-900 dark:bg-violet-950/40 dark:text-violet-300"
                  >
                    <FlaskConical className="mr-1 h-3 w-3" aria-hidden />
                    Module · ReactionIQ
                  </Badge>
                  <Badge variant="outline" className="text-muted-foreground">
                    Bayesian · Multi-objective · Closed-loop
                  </Badge>
                </div>
                <h1 className="mt-5 max-w-3xl text-4xl font-semibold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl">
                  The next experiment, chosen by{" "}
                  <span style={{ color: "var(--mt-teal)" }}>the surrogate</span> — not by intuition.
                </h1>
                <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted-foreground sm:text-xl">
                  ReactionIQ runs the closed-loop optimisation engine inside MolTrace. Bayesian
                  acquisition over a live Gaussian-process surrogate proposes the conditions most
                  worth trying next — under hard constraints from your spectroscopy evidence and
                  regulatory framework.
                </p>
                <div className="mt-10 flex flex-wrap items-center gap-4">
                  <Button asChild size="lg" className="gap-2">
                    <Link href="/reactions">
                      Open ReactionIQ
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

              {/* Hero visual — live campaign snapshot */}
              <aside className="relative overflow-hidden rounded-3xl border bg-card p-6 shadow-sm">
                <div className="flex items-center justify-between">
                  <p
                    className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                    style={{ color: "var(--mt-teal)" }}
                  >
                    Campaign · live
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
                      className="h-1.5 w-1.5 animate-pulse rounded-full"
                      style={{ backgroundColor: "var(--mt-teal)" }}
                      aria-hidden
                    />
                    converging
                  </span>
                </div>
                <p className="mt-3 font-mono text-xs text-muted-foreground">
                  campaign · camp_2f8d · objective Yield × (1 − impurity)
                </p>
                <p className="mt-1 text-sm font-medium">5 rounds · best yield 81% · imp 0.7%</p>

                <div className="mt-6 space-y-1.5">
                  {CAMPAIGN_SAMPLE.map((row) => {
                    const status = STATUS_CHIP[row.status]
                    return (
                      <div
                        key={row.round}
                        className="rounded-md border bg-background/80 px-3 py-2"
                      >
                        <div className="flex items-center gap-2">
                          <span
                            className="font-mono text-[10px] font-bold tabular-nums"
                            style={{ color: "var(--mt-teal)" }}
                          >
                            R{row.round}
                          </span>
                          <span
                            className={`inline-flex items-center gap-1.5 rounded-full border px-1.5 py-0 font-mono text-[8px] font-bold uppercase tracking-[0.14em] ${status.chip}`}
                          >
                            <span className={`h-1 w-1 rounded-full ${status.dot}`} aria-hidden />
                            {status.label}
                          </span>
                          <span className="ml-auto truncate font-mono text-[9px] text-muted-foreground">
                            {row.acquisition}
                          </span>
                        </div>
                        <p className="mt-1 truncate font-mono text-[10px] text-foreground">
                          {row.proposed}
                        </p>
                        <p className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground">
                          → {row.measured}
                        </p>
                      </div>
                    )
                  })}
                </div>
                <p className="mt-5 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                  qNEHVI · constraint-aware · audit-event per round
                </p>
              </aside>
            </div>
          </div>
        </section>

        {/* ── Why this exists ─────────────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="grid gap-12 lg:grid-cols-[1fr_1.4fr]">
              <div>
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                  style={{ color: "var(--mt-teal)" }}
                >
                  Why this exists
                </p>
                <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                  Trial-and-error is expensive — and silent about what it missed.
                </h2>
              </div>
              <div className="space-y-5 text-base leading-relaxed text-muted-foreground">
                <p>
                  A typical process-chemistry campaign runs{" "}
                  <strong className="text-foreground">40–80 reactions</strong> to find a robust
                  optimum. Most of those reactions are wasted — they sample regions the team
                  already knew were bad, or repeat conditions a previous campaign explored two
                  years ago and forgot.
                </p>
                <p>
                  At the same time, regulatory burden is climbing.{" "}
                  <strong className="text-foreground">Every condition tried</strong> is a potential
                  data point that needs to be traceable. Every impurity that crosses an ICH limit
                  is a campaign-restart event. Spreadsheet-tracked reaction histories can't
                  withstand inspection — and don't survive the analyst who wrote them.
                </p>
                <p className="font-medium text-foreground">
                  ReactionIQ runs the acquisition function in your stead. It remembers every prior
                  campaign, respects every active regulatory constraint, and proposes the
                  experiment most likely to advance the Pareto frontier — with an auditable trail
                  of why.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ── Pipeline figure ─────────────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                The optimisation loop
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Seven stages, looping until the surrogate converges.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Each round emits a typed Pydantic record. The surrogate state, the acquisition
                proposal, the measured outcome, and the human decision are all recipe-hash-linked
                so any prior campaign replays bit-identically.
              </p>
            </div>

            <ol className="mt-12 grid gap-4 lg:grid-cols-3 xl:grid-cols-4">
              {PIPELINE.map((s, idx) => (
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
                    {idx < PIPELINE.length - 1 ? (
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
                      Emits
                    </p>
                    <p className="mt-1.5 font-mono text-[11px] leading-relaxed text-foreground">
                      {s.artifact}
                    </p>
                  </div>
                </li>
              ))}
            </ol>

            {/* The loop diagram — explicit feedback arrow */}
            <div className="mt-10 overflow-hidden rounded-2xl border bg-card">
              <div className="border-b bg-muted/40 px-4 py-2.5">
                <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
                  At a glance
                </p>
              </div>
              <pre className="overflow-x-auto px-4 py-5 font-mono text-[11px] leading-relaxed text-foreground sm:px-8 sm:text-xs">
{`     ┌─►  Define design space  ──►  Constrain (regulatory + safety + cost)
     │                                            │
     │                                            ▼
  Decide (stop / pivot / continue)         Propose (acquisition over GP surrogate)
     ▲                                            │
     │                                            ▼
  Update surrogate posterior  ◄──  Measure  ◄──  Run (manual or closed-loop)
        with constraint mask          (spectroscopy auto-attaches)`}
              </pre>
            </div>
          </div>
        </section>

        {/* ── Methods matrix ──────────────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Methods we ship
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Four optimisation regimes. One typed API.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Switch regimes by argument — the design-space + objective + constraint contract
                stays identical across all four. The backend uses{" "}
                <code className="font-mono text-foreground">run_bayesian_optimization()</code> with
                the same{" "}
                <code className="font-mono text-foreground">acquisition_score</code> +{" "}
                <code className="font-mono text-foreground">expected_improvement</code> fields.
              </p>
            </div>
            <div className="mt-12 grid gap-6 lg:grid-cols-2">
              {METHODS.map((m) => (
                <article
                  key={m.acronym}
                  className="rounded-2xl border bg-card p-6 shadow-sm sm:p-7"
                  style={{ borderLeft: "3px solid var(--mt-teal)" }}
                >
                  <div className="flex items-baseline gap-4">
                    <span
                      className="font-mono text-3xl font-bold tabular-nums tracking-tight"
                      style={{ color: "var(--mt-teal)" }}
                    >
                      {m.acronym}
                    </span>
                    <div>
                      <h3 className="text-base font-semibold tracking-tight">{m.full}</h3>
                      <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                        {m.scope}
                      </p>
                    </div>
                  </div>
                  <ul className="mt-5 space-y-2">
                    {m.bullets.map((item) => (
                      <li
                        key={item}
                        className="flex items-start gap-2.5 text-sm leading-relaxed text-muted-foreground"
                      >
                        <CheckCircle2
                          className="mt-0.5 h-3.5 w-3.5 shrink-0"
                          style={{ color: "var(--mt-teal)" }}
                          aria-hidden
                        />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* ── Use cases ───────────────────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Use cases shipped
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Six campaign templates, with inputs and outputs.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Each is a typed pipeline you parameterise — not a bespoke build. The same
                acquisition engine drives every template; the differences are in design-space
                encoding and objective weighting.
              </p>
            </div>
            <div className="mt-12 grid gap-6 lg:grid-cols-2 xl:grid-cols-3">
              {USE_CASES.map((u) => {
                const Icon = u.icon
                return (
                  <article
                    key={u.name}
                    className="flex flex-col rounded-2xl border bg-card p-6 shadow-sm"
                    style={{ borderTop: "3px solid var(--mt-teal)" }}
                  >
                    <span
                      className="inline-flex h-11 w-11 items-center justify-center rounded-xl"
                      style={{
                        backgroundColor: "var(--mt-teal-soft)",
                        color: "var(--mt-teal)",
                      }}
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

        {/* ── Campaign convergence figure ─────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Anatomy of a campaign
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Five rounds. One Pareto frontier. One audit ledger.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                The campaign below is the worked example threading through every module page —
                acetic-acid impurity suppression. Round 4 violates the Q3C constraint mid-flight;
                Round 5's acquisition mask routes around it.
              </p>
            </div>

            <div className="mt-12 overflow-hidden rounded-2xl border bg-card shadow-sm">
              <div className="border-b bg-muted/40 px-5 py-3">
                <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
                  bayesian_optimization_run · run_4f7a · 5 rounds · convergence reached
                </p>
              </div>
              <table className="w-full text-left text-sm">
                <thead className="border-b bg-muted/20 font-mono uppercase tracking-[0.12em] text-[10px] text-muted-foreground">
                  <tr>
                    <th className="px-5 py-2.5">Round</th>
                    <th className="px-5 py-2.5">Acquisition</th>
                    <th className="px-5 py-2.5">Proposed</th>
                    <th className="px-5 py-2.5">Measured</th>
                    <th className="px-5 py-2.5">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {CAMPAIGN_SAMPLE.map((row, idx) => {
                    const status = STATUS_CHIP[row.status]
                    return (
                      <tr
                        key={row.round}
                        className={idx % 2 === 0 ? "border-t" : "border-t bg-muted/20"}
                      >
                        <td className="px-5 py-3 align-top">
                          <span
                            className="font-mono text-base font-bold tabular-nums"
                            style={{ color: "var(--mt-teal)" }}
                          >
                            R{row.round}
                          </span>
                        </td>
                        <td className="px-5 py-3 align-top font-mono text-xs text-foreground">
                          {row.acquisition}
                        </td>
                        <td className="px-5 py-3 align-top font-mono text-xs text-foreground">
                          {row.proposed}
                        </td>
                        <td className="px-5 py-3 align-top font-mono text-xs text-muted-foreground">
                          {row.measured}
                        </td>
                        <td className="px-5 py-3 align-top">
                          <span
                            className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em] ${status.chip}`}
                          >
                            <span className={`h-1.5 w-1.5 rounded-full ${status.dot}`} aria-hidden />
                            {status.label}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Yield trajectory — text-mode bar visualization */}
            <div className="mt-6 overflow-hidden rounded-2xl border bg-card">
              <div className="border-b bg-muted/40 px-4 py-2.5">
                <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
                  Yield trajectory · convergence after constraint mask
                </p>
              </div>
              <pre className="overflow-x-auto px-4 py-5 font-mono text-[11px] leading-relaxed text-foreground sm:px-8 sm:text-xs">
{`  R01  ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  41 %   explore
  R02  █████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░  67 %   exploit
  R03  ██████████████░░░░░░░░░░░░░░░░░░░░░░░░░░  74 %   exploit
  R04  ██████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  ABORT  Q3C limit exceeded
  R05  ████████████████░░░░░░░░░░░░░░░░░░░░░░░░  81 %   best · constraint-aware

  Pareto best   81 % yield  ·  0.7 % impurity (Q3C compliant)  ·  mid cost
  Stop reason   hypervolume Δ < 0.01 over last 2 rounds`}
              </pre>
            </div>
          </div>
        </section>

        {/* ── Trial-and-error vs ReactionIQ ───────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                The honest comparison
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                What changes when the surrogate picks the next experiment.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Trial-and-error campaigns aren't bad — they're under-instrumented. ReactionIQ keeps
                the chemist as the decision-maker but moves the experiment-selection step from
                gut to acquisition function.
              </p>
            </div>
            <div className="mt-12 overflow-hidden rounded-2xl border bg-card shadow-sm">
              <table className="w-full text-left text-sm">
                <thead className="bg-muted/40 font-mono uppercase tracking-[0.12em] text-[10px] text-muted-foreground">
                  <tr>
                    <th className="px-5 py-3">Dimension</th>
                    <th className="px-5 py-3">Trial-and-error</th>
                    <th className="px-5 py-3">ReactionIQ</th>
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
                        <p>{row.trialAndError}</p>
                      </td>
                      <td className="px-5 py-3.5 align-top text-xs leading-relaxed text-foreground">
                        <span className="mb-1 inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300">
                          <CheckCircle2 className="h-2.5 w-2.5" aria-hidden />
                          with ReactionIQ
                        </span>
                        <p>{row.reactioniq}</p>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* ── Closing loop — three-pillar narrative ───────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Three pillars, one loop
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                The whole platform, on one acetic-acid impurity.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Picking up the cross-module worked example from Spectroscopy + Regentry —
                here's the role ReactionIQ plays when the impurity threshold is crossed mid-campaign.
              </p>
            </div>
            <ol className="mt-12 grid gap-4 lg:grid-cols-4">
              {CROSS_MODULE_LOOP.map((step, idx) => (
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

            <div className="mt-10 grid gap-4 sm:grid-cols-2">
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
                    <p className="text-sm font-semibold">← Spectroscopy (SpectraCheck)</p>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      Provides every measurement — yield, impurity profile, residual solvent — per
                      campaign round.
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
                    <p className="text-sm font-semibold">← Regentry</p>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      Translates compliance thresholds into hard constraints the optimiser respects
                      at proposal time.
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

        {/* ── Trust + reproducibility ─────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="grid gap-10 lg:grid-cols-[1fr_1.6fr]">
              <div>
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                  style={{ color: "var(--mt-teal)" }}
                >
                  Trust & reproducibility
                </p>
                <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                  Bayesian, yes. Black-box, no.
                </h2>
                <p className="mt-4 text-base text-muted-foreground">
                  Every campaign is replayable from any prior date. Every proposal is acquisition-attributed.
                  Every pivot is signed. The surrogate is a tool — the chemist is the decision-maker.
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
                Bring us a stalled campaign.
              </h2>
              <p className="mt-4 text-base text-muted-foreground sm:text-lg">
                Pick a reaction where you've already run 30+ conditions and can't tell what to try
                next. We'll show you the Pareto frontier ReactionIQ would propose — with your
                regulatory constraints already enforced.
              </p>
              <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
                <Button asChild size="lg" className="gap-2">
                  <Link href="/reactions">
                    Open ReactionIQ
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="outline" className="gap-2">
                  <Link href="/contact?reason=Request%20a%20demo">
                    Walk us through your campaign
                    <FlaskConical className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="ghost" className="gap-2">
                  <Link
                    href="https://docs.moltrace.co/guides/modules/optimization/"
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
