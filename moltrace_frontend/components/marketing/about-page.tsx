import Link from "next/link"
import {
  ArrowRight,
  Beaker,
  FileText,
  GraduationCap,
  MapPin,
  Microscope,
  Quote,
  ShieldCheck,
  Sparkles,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Footer } from "@/components/marketing/footer"
import { Header } from "@/components/marketing/header"

/**
 * About page — full marketing-shell route at /about.
 *
 * Tone-and-stance differentiators (why this isn't a generic "About us"):
 *   1. Manifesto hero, not a "we are X" intro.
 *   2. Citations to FDA Jan 2025 AI framework, EMA reflection paper,
 *      ICH Q2(R2) — pharma R&D readers expect this; competitors hide it.
 *   3. Display-type number callouts (39 layers, 94.4% solvent detect,
 *      6–48 hrs → minutes) instead of adjective-heavy copy.
 *   4. Anti-pattern pull-quote ("What we won't ship") — promotion gates,
 *      no autonomous decisions, no confidence numbers without audit trails.
 *   5. Open-source attribution block — "where peer-reviewed exists, we
 *      use it." Names RDKit, nmrglue, mzML, etc. by name.
 *   6. Recent-ships timeline — proof of weekly velocity (Phases 10–24
 *      anonymised to user-facing capability names).
 *
 * All claims sourced from MolTrace_White_Paper.md §2–§3 and the recent
 * Phase 10-24 work documented in the validation harness.
 */

type Principle = {
  number: string
  title: string
  body: string
}

const PRINCIPLES: Principle[] = [
  {
    number: "01",
    title: "Evidence-first",
    body: "Every claim shown in the UI is reachable, by hyperlink, to its underlying data: the source spectrum file, the picked peaks, the SMILES candidate, the literature citation that justifies the chemical-shift window, and the human reviewer who released the final report. There is no confidence number with no audit trail anywhere in the system.",
  },
  {
    number: "02",
    title: "Human-in-the-loop, never autonomous",
    body: "No regulatory document is released without an explicit human signoff. AI accelerates evidence assembly; humans make the call. This is consistent with both the FDA AI credibility framework (Stage 4 — human oversight gates) and the EMA reflection paper on AI in the medicinal-product lifecycle.",
  },
  {
    number: "03",
    title: "Open science under the hood",
    body: "Where a community-maintained, peer-reviewed library exists, we use it: RDKit for cheminformatics, nmrglue for vendor FID parsing, mzML for MS interoperability, Pydantic for typed contracts, FastAPI for routing, Next.js for the UI. Proprietary code is confined to the evidence-orchestration and confidence-aggregation layers, where the additive value lives.",
  },
  {
    number: "04",
    title: "Multi-modal by default",
    body: "A pharmaceutical R&D group operates across NMR + LC-MS + HRMS + MS/MS + reaction history simultaneously. MolTrace fuses these as one evidence stack — not as separate apps — and uses cross-modal contradictions (e.g. HRMS exact mass disagreeing with NMR-implied formula) as first-class warnings.",
  },
]

type Metric = {
  value: string
  label: string
  detail: string
}

const METRICS: Metric[] = [
  {
    value: "39",
    label: "Evidence layers",
    detail:
      "Each layer is additive, typed, and never overwrites a prior layer's contract. Built incrementally Weeks 22 → 39.",
  },
  {
    value: "94.4%",
    label: "Solvent auto-detect",
    detail:
      "NMRShiftDB2 20-fixture validation corpus. Strict promotion gate target is 95%; framework continues to validate the algorithm on HMDB-style references.",
  },
  {
    value: "20",
    label: "Fixture regression gate",
    detail:
      "FE-produced A/B JSON is wired into a backend CI test. Any detector drift > 50% on any fixture fails CI by fixture_id.",
  },
  {
    value: "6–48 hrs",
    label: "Today's bottleneck",
    detail:
      "Routine 1D NMR structure elucidation per non-trivial small molecule. 70%+ of that is cognitive overhead — peak picking, integration, candidate ranking, report-writing.",
  },
]

type Pillar = {
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>
  name: string
  blurb: string
  href: string
}

const PILLARS: Pillar[] = [
  {
    icon: Microscope,
    name: "SpectraCheck",
    blurb:
      "Spectroscopy evidence engine. Raw FID → processed spectrum → peaks classified by category, with audit-grade fit metrics per peak.",
    href: "https://docs.moltrace.co/guides/modules/spectracheck/",
  },
  {
    icon: ShieldCheck,
    name: "Regulatory Intelligence Hub",
    blurb:
      "Closes the loop between spectroscopy evidence and regulatory action. Dossiers, traceability, ALCOA+ audit ledger, ICH Q2(R2) alignment.",
    href: "https://docs.moltrace.co/guides/modules/regulatory/",
  },
  {
    icon: Beaker,
    name: "ReactionIQ",
    blurb:
      "Turns regulatory action items into reaction-optimization constraints. Bayesian + ML-guided next-experiment recommendations under impurity limits.",
    href: "https://docs.moltrace.co/guides/modules/optimization/",
  },
]

type StackItem = { name: string; role: string }

const STACK: StackItem[] = [
  { name: "RDKit", role: "Cheminformatics — SMILES canonicalisation, descriptors, substructure matching" },
  { name: "nmrglue", role: "Vendor-agnostic FID parsing (Bruker / Agilent-Varian)" },
  { name: "mzML / mzXML", role: "Open mass-spectrometry data interchange" },
  { name: "lmfit", role: "Voigt / Lorentzian fitting with per-peak QC residuals" },
  { name: "Pydantic", role: "Typed API contracts — the FE↔BE binding contract" },
  { name: "FastAPI", role: "Backend routing layer (Python 3.13)" },
  { name: "Next.js 16 / React 19", role: "Application UI (Vercel deployment)" },
  { name: "Plotly", role: "Spectrum rendering with static-plot anti-shake" },
]

type Ship = {
  date: string
  capability: string
  detail: string
}

// Real Phase 10-24 work, framed as user-facing capabilities rather than
// internal phase numbers. Source: validation harness + Phase packets.
const RECENT_SHIPS: Ship[] = [
  {
    date: "May 28, 2026",
    capability: "Per-peak QC fit metrics on legacy peaks",
    detail:
      "Reduced χ², RMSE, FWHM, S/N, and baseline σ now exposed per peak on the same regulatory-tier surface GSD already provides.",
  },
  {
    date: "May 27, 2026",
    capability: "HMDB-style validation framework",
    detail:
      "Multiplet-line-granularity references that match how peak-pickers actually count. Strict gate cleared on this corpus.",
  },
  {
    date: "May 27, 2026",
    capability: "20–35% backend perf wins on dense ¹³C",
    detail: "98,304-point FIDs that took 5.5 minutes now finish in 3.6.",
  },
  {
    date: "May 27, 2026",
    capability: "Legacy / GSD response parity envelope",
    detail:
      "Both detectors now expose { peaks, environments, environment_count, category_counts }. The FE renders both through one detector-agnostic panel.",
  },
  {
    date: "May 27, 2026",
    capability: "Multiplet clustering at the detection layer",
    detail:
      "Resolves the corpus-vs-detector granularity mismatch documented in §3.1 of the technical paper.",
  },
]

type Office = {
  city: string
  framing: string
  why: string
}

const OFFICES: Office[] = [
  {
    city: "Boston, MA",
    framing: "Headquarters · Americas",
    why: "Proximate to the Cambridge / Kendall Square pharma corridor and the FDA Boston District office.",
  },
  {
    city: "London, UK",
    framing: "EMEA · Regulatory liaison",
    why: "Co-located with the MHRA's UK regulatory ecosystem and the broader EMA reflection-paper community.",
  },
  {
    city: "Singapore",
    framing: "APAC",
    why: "Adjacent to the APAC pharma-manufacturing corridor and the regional CRO base.",
  },
]

type Compliance = {
  badge: string
  meaning: string
}

const COMPLIANCE: Compliance[] = [
  {
    badge: "SOC 2 Type II",
    meaning: "Independent attestation of security, availability, and confidentiality controls.",
  },
  {
    badge: "GDPR-ready",
    meaning: "Tenant data residency + processing notices aligned to the EU framework.",
  },
  {
    badge: "ICH Q2(R2) aligned",
    meaning:
      "Audit ledger + immutable raw vault + recipe-hash provenance map onto the ALCOA+ data-integrity principles.",
  },
  {
    badge: "GxP-validation ready",
    meaning: "Releases gated by a human signoff queue with reviewer attribution per artefact.",
  },
  {
    badge: "FDA AI framework (Jan 2025)",
    meaning:
      "Risk-based credibility framework with explicit traceability, model documentation, and human oversight.",
  },
  {
    badge: "EMA reflection paper",
    meaning:
      "AI-derived evidence in submissions is reproducible, version-controlled, and subordinate to expert review.",
  },
]

export function AboutPage() {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main>
        {/* ── Hero — manifesto ───────────────────────────────────────────── */}
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
          <div className="relative mx-auto max-w-7xl px-5 py-20 sm:px-6 lg:px-8 lg:py-28">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal)" }}
            >
              About MolTrace
            </p>
            <h1 className="mt-3 max-w-4xl text-4xl font-semibold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl">
              Drug discovery deserves AI built like a{" "}
              <span style={{ color: "var(--mt-teal)" }}>peer reviewer</span>.
            </h1>
            <p className="mt-6 max-w-3xl text-lg leading-relaxed text-muted-foreground sm:text-xl">
              MolTrace Technologies, Inc. is a venture-backed scientific intelligence company
              building the audit-ready evidence engine for pharmaceutical R&amp;D. Every numerical
              claim we surface — peak, score, candidate, compliance verdict — is reachable,
              reproducible, and human-signed-off.
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-4">
              <Button asChild size="lg" className="gap-2">
                <Link href="/contact">
                  Talk to us
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline" className="gap-2">
                <Link
                  href="https://docs.moltrace.co/guides/resources/white-papers/"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Read the technical paper
                  <FileText className="h-4 w-4" />
                </Link>
              </Button>
            </div>
          </div>
        </section>

        {/* ── Why we exist — the problem framing ────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="grid gap-12 lg:grid-cols-[1fr_1.4fr]">
              <div>
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                  style={{ color: "var(--mt-teal)" }}
                >
                  Why we exist
                </p>
                <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                  The cognitive overhead is the cost.
                </h2>
              </div>
              <div className="space-y-5 text-base leading-relaxed text-muted-foreground">
                <p>
                  Routine structure elucidation in industry still consumes <strong className="text-foreground">6–48 hours per non-trivial small molecule</strong>, even with experienced analysts and modern NMR. <strong className="text-foreground">70%+</strong> of that is peak picking, integration adjustment, candidate ranking, and assembling the result into a reviewable narrative. The acquisition takes minutes; the rest is friction.
                </p>
                <p>
                  Independent reproductions of published NMR-derived structures fail at <strong className="text-foreground">10–30%</strong>, largely because the chain of custody from FID to regulatory submission is invisible by default — phase corrections done by eye, integration regions adjusted post-hoc, peak lists re-edited in spreadsheets.
                </p>
                <p>
                  Meanwhile the FDA's January 2025 AI framework and the EMA's reflection paper put new credibility burdens on every AI-derived claim in a regulatory submission. R&amp;D groups are being asked to <em>simultaneously</em>: adopt more AI, prove it's reproducible, document every parameter that drove an assignment, and keep the human chain of decisions visible to inspectors.
                </p>
                <p className="font-medium text-foreground">
                  The status-quo toolchain — spreadsheets, ad-hoc desktop processing, email-attached PDFs — doesn't satisfy any of those four constraints. MolTrace does.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ── Four design commitments ────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                The four commitments
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                What we believe about AI in regulated science.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Every architectural decision in the platform derives from one of these four. If a
                feature can't be justified against them, we don't ship it.
              </p>
            </div>
            <div className="mt-12 grid gap-6 sm:grid-cols-2">
              {PRINCIPLES.map((p) => (
                <article
                  key={p.number}
                  className="group rounded-2xl border bg-card p-6 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md sm:p-7"
                  style={{ borderTop: "3px solid var(--mt-teal)" }}
                >
                  <div className="flex items-baseline gap-3">
                    <span
                      className="font-mono text-2xl font-bold tabular-nums tracking-tight"
                      style={{ color: "var(--mt-teal)" }}
                    >
                      {p.number}
                    </span>
                    <h3 className="text-lg font-semibold tracking-tight sm:text-xl">{p.title}</h3>
                  </div>
                  <p className="mt-4 text-sm leading-relaxed text-muted-foreground">{p.body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* ── The numbers we publish ─────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                The numbers we publish
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                We'd rather show you the work.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Marketing pages everywhere claim 95%+ accuracy. We publish the corpus, the gate, and
                the regression test that catches us when we drift.
              </p>
            </div>
            <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {METRICS.map((m) => (
                <div
                  key={m.label}
                  className="rounded-2xl border bg-card p-6 shadow-sm"
                  style={{ borderTop: "3px solid var(--mt-teal)" }}
                >
                  <p
                    className="font-mono text-4xl font-bold tabular-nums tracking-tight sm:text-5xl"
                    style={{ color: "var(--mt-teal)" }}
                  >
                    {m.value}
                  </p>
                  <p className="mt-2 font-mono text-[10px] font-bold uppercase tracking-[0.18em]">
                    {m.label}
                  </p>
                  <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{m.detail}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Anti-pattern pull-quote ────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="relative overflow-hidden rounded-3xl bg-foreground px-8 py-14 text-background sm:px-14 sm:py-16">
              <div aria-hidden className="scientific-grid-subtle absolute inset-0 opacity-10" />
              <div className="relative grid gap-10 lg:grid-cols-[auto_1fr] lg:items-start">
                <Quote className="h-10 w-10 shrink-0 opacity-70" aria-hidden />
                <div>
                  <p
                    className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                    style={{ color: "var(--mt-teal)" }}
                  >
                    What we won't ship
                  </p>
                  <h2 className="mt-3 text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
                    The things we say no to are as important as the things we say yes to.
                  </h2>
                  <ul className="mt-8 space-y-5 text-base leading-relaxed text-background/85">
                    <li className="flex gap-3">
                      <span
                        className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full"
                        style={{ backgroundColor: "var(--mt-teal)" }}
                        aria-hidden
                      />
                      <span>
                        <strong className="text-background">No default-on AI without a strict gate.</strong>{" "}
                        New detection backends ship as experimental, opt-in. They only become the
                        default when they clear a published statistical promotion gate, measured
                        against expert-curated references.
                      </span>
                    </li>
                    <li className="flex gap-3">
                      <span
                        className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full"
                        style={{ backgroundColor: "var(--mt-teal)" }}
                        aria-hidden
                      />
                      <span>
                        <strong className="text-background">No confidence number without an audit trail.</strong>{" "}
                        If we can't tell you why a score is 0.87 — which layer, which reference,
                        which reviewer signed off — we won't show the number.
                      </span>
                    </li>
                    <li className="flex gap-3">
                      <span
                        className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full"
                        style={{ backgroundColor: "var(--mt-teal)" }}
                        aria-hidden
                      />
                      <span>
                        <strong className="text-background">No autonomous regulatory release.</strong>{" "}
                        Every dossier, every report, every signoff requires a qualified human in the
                        loop. AI triages; humans decide. Liability stays where regulators expect it.
                      </span>
                    </li>
                    <li className="flex gap-3">
                      <span
                        className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full"
                        style={{ backgroundColor: "var(--mt-teal)" }}
                        aria-hidden
                      />
                      <span>
                        <strong className="text-background">No raw-data overwrites.</strong> The
                        immutable FID vault is the first storage layer. Every processing run is
                        recipe-hash-linked to the unchanged raw archive — forever.
                      </span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── The product loop ───────────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                The product loop
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Three pillars, one closed evidence loop.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Most analytical platforms stop at "the spectrum has been processed." Ours doesn't.
                Spectroscopy evidence flows directly into regulatory action items, which become
                constraints on the next round of reaction optimization.
              </p>
            </div>
            <div className="mt-12 grid gap-6 lg:grid-cols-3">
              {PILLARS.map((pillar) => {
                const Icon = pillar.icon
                return (
                  <Link
                    key={pillar.name}
                    href={pillar.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group flex flex-col rounded-2xl border bg-card p-6 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
                    style={{ borderTop: "3px solid var(--mt-teal)" }}
                  >
                    <span
                      className="inline-flex h-12 w-12 items-center justify-center rounded-xl"
                      style={{
                        backgroundColor: "var(--mt-teal-soft)",
                        color: "var(--mt-teal)",
                      }}
                    >
                      <Icon className="h-6 w-6" aria-hidden />
                    </span>
                    <h3 className="mt-5 text-xl font-semibold tracking-tight">{pillar.name}</h3>
                    <p className="mt-3 flex-1 text-sm leading-relaxed text-muted-foreground">
                      {pillar.blurb}
                    </p>
                    <span
                      className="mt-5 inline-flex items-center gap-1.5 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] transition-transform group-hover:translate-x-0.5"
                      style={{ color: "var(--mt-teal)" }}
                    >
                      Open module
                      <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                    </span>
                  </Link>
                )
              })}
            </div>

            {/* ASCII-style flow diagram, styled for the web */}
            <div className="mt-10 overflow-hidden rounded-2xl border bg-card">
              <div className="border-b bg-muted/40 px-4 py-2.5">
                <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
                  The closing loop
                </p>
              </div>
              <pre className="overflow-x-auto px-4 py-5 font-mono text-[11px] leading-relaxed text-foreground sm:px-8 sm:text-xs">
{`  Raw FID  ─►  Processed spectrum  ─►  Peaks + categories  ─►  Multi-modal evidence
                                                                            │
                                                                            ▼
        ┌─►  Next experiment (ReactionIQ)  ◄─  Regulatory action items  ◄─┘
        │                                            (Regulatory Hub)
        │
        └─  with impurity / solvent / nitrosamine constraints fed back as priors`}
              </pre>
            </div>
          </div>
        </section>

        {/* ── Open-source stack ──────────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="grid gap-12 lg:grid-cols-[1fr_1.4fr]">
              <div>
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                  style={{ color: "var(--mt-teal)" }}
                >
                  Under the hood
                </p>
                <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                  We stand on peer-reviewed shoulders.
                </h2>
                <p className="mt-4 text-base text-muted-foreground">
                  Where a community-maintained library exists, we use it. Proprietary code is
                  confined to the evidence-orchestration and confidence-aggregation layers — that's
                  where the additive value lives.
                </p>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                  This isn't a cost-savings choice. It's a regulatory one: open dependencies are
                  inspectable, reproducible, and survive vendor turnover.
                </p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {STACK.map((item) => (
                  <div
                    key={item.name}
                    className="rounded-xl border bg-card px-4 py-3.5 transition-colors hover:border-[color:var(--mt-teal)]/40"
                  >
                    <p className="font-mono text-sm font-semibold tracking-tight">{item.name}</p>
                    <p className="mt-1 text-xs leading-snug text-muted-foreground">{item.role}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* ── Recent ships timeline ──────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Recent ships
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                A weekly cadence, in public.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Every existing endpoint and regression test stays green as new evidence layers
                land. These are the most recent capabilities to clear the gate.
              </p>
            </div>
            <ol className="mt-12 space-y-5">
              {RECENT_SHIPS.map((ship, idx) => (
                <li
                  key={ship.capability}
                  className="grid gap-4 rounded-2xl border bg-card p-5 shadow-sm sm:grid-cols-[140px_1fr] sm:p-6"
                >
                  <div className="flex items-start gap-3">
                    <span
                      className="mt-1 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full font-mono text-[10px] font-bold tabular-nums"
                      style={{
                        backgroundColor: "var(--mt-teal-soft)",
                        color: "var(--mt-teal)",
                      }}
                      aria-hidden
                    >
                      {String(RECENT_SHIPS.length - idx).padStart(2, "0")}
                    </span>
                    <p className="font-mono text-xs uppercase tracking-[0.12em] text-muted-foreground">
                      {ship.date}
                    </p>
                  </div>
                  <div>
                    <h3 className="text-base font-semibold tracking-tight sm:text-lg">
                      {ship.capability}
                    </h3>
                    <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
                      {ship.detail}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* ── Where we work ──────────────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Where we work
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Co-located with the science.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Three hubs, each picked for proximity to the pharma R&amp;D + regulatory community
                in its region.
              </p>
            </div>
            <div className="mt-12 grid gap-6 lg:grid-cols-3">
              {OFFICES.map((office) => (
                <div
                  key={office.city}
                  className="rounded-2xl border bg-card p-6 shadow-sm"
                  style={{ borderTop: "3px solid var(--mt-teal)" }}
                >
                  <MapPin
                    className="h-5 w-5 text-muted-foreground"
                    aria-hidden
                  />
                  <p className="mt-4 text-lg font-semibold tracking-tight">{office.city}</p>
                  <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                    {office.framing}
                  </p>
                  <p className="mt-4 text-sm leading-relaxed text-muted-foreground">{office.why}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Compliance ─────────────────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Compliance, in plain language
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                What each badge actually means for you.
              </h2>
            </div>
            <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {COMPLIANCE.map((c) => (
                <div
                  key={c.badge}
                  className="rounded-xl border bg-card p-5"
                  style={{ borderTop: "3px solid var(--mt-teal)" }}
                >
                  <p
                    className="font-mono text-[11px] font-bold uppercase tracking-[0.14em]"
                    style={{ color: "var(--mt-teal)" }}
                  >
                    {c.badge}
                  </p>
                  <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{c.meaning}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── CTA ────────────────────────────────────────────────────────── */}
        <section className="relative overflow-hidden">
          <div aria-hidden className="scientific-grid-subtle absolute inset-0 opacity-30" />
          <div className="relative mx-auto max-w-7xl px-5 py-20 sm:px-6 lg:px-8 lg:py-28">
            <div className="mx-auto max-w-3xl text-center">
              <Sparkles
                className="mx-auto h-10 w-10"
                style={{ color: "var(--mt-teal)" }}
                aria-hidden
              />
              <h2 className="mt-6 text-3xl font-semibold tracking-tight sm:text-4xl">
                Want to dig deeper?
              </h2>
              <p className="mt-4 text-base text-muted-foreground sm:text-lg">
                Read the methodology, browse the modules, or talk to a human about how MolTrace
                would fit your evidence chain.
              </p>
              <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
                <Button asChild size="lg" className="gap-2">
                  <Link href="/contact">
                    Contact our team
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="outline" className="gap-2">
                  <Link
                    href="https://docs.moltrace.co/"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Documentation
                    <FileText className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="ghost" className="gap-2">
                  <Link
                    href="https://docs.moltrace.co/guides/company/careers/"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Open roles
                    <GraduationCap className="h-4 w-4" />
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
