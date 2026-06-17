import Link from "next/link"
import {
  ArrowRight,
  Briefcase,
  CalendarCheck2,
  Compass,
  FileText,
  FlaskConical,
  GitBranch,
  Globe2,
  GraduationCap,
  Headphones,
  Layers,
  Mail,
  MapPin,
  Microscope,
  Scale,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Footer } from "@/components/marketing/footer"
import { Header } from "@/components/marketing/header"

/**
 * Careers page — full marketing-shell route at /careers.
 *
 * Tone-and-stance differentiators:
 *   1. "We hire the way we ship" — promotion-gate culture as a recruiting
 *      pitch, not boilerplate values copy.
 *   2. "What you'll actually build" pulls real shipped Phase 10-24 work
 *      into capability descriptions. Candidates can see the depth of
 *      work before they apply.
 *   3. Transparent hiring rubric — what we test for, what we don't.
 *   4. Compensation philosophy stated up front (bands, equity, geo parity).
 *   5. Open roles section honestly empty by team where we're not hiring,
 *      with a "register interest" path rather than fake postings.
 *   6. Benefits framed around the work (publication budget, scientific
 *      compute, regulatory-conference travel) rather than generic perks.
 */

type Reason = {
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties; "aria-hidden"?: boolean }>
  number: string
  title: string
  body: string
}

const WHY_JOIN: Reason[] = [
  {
    icon: ShieldCheck,
    number: "01",
    title: "Regulatory-grade engineering, not compliance theatre",
    body: "FDA Jan 2025 AI framework, EMA reflection paper, ICH Q2(R2), ALCOA+ — these aren't boxes we tick. They're the design constraint. You'll learn pharma data integrity at depth most engineers never touch.",
  },
  {
    icon: GitBranch,
    number: "02",
    title: "Promotion-gate culture",
    body: "We don't ship AI defaults until they clear strict statistical validation. New detection backends launch as opt-in, get measured against an expert-curated corpus, and only become default when they cross a published threshold. If you've watched AI startups ship and patch, this will feel like sanity.",
  },
  {
    icon: Layers,
    number: "03",
    title: "Real instrument data, multi-modal by default",
    body: "Bruker FIDs, Agilent-Varian acquisitions, real LC-MS feature tables, HRMS exact masses, MS/MS fragmentation. No synthetic-only demos. The platform fuses these as one evidence stack with cross-modal contradictions surfaced as first-class warnings.",
  },
  {
    icon: CalendarCheck2,
    number: "04",
    title: "Weekly ship cadence, in public",
    body: "Every existing endpoint and regression test stays green as new evidence layers land. We publish our recent ships, our validation corpus, our gate thresholds. You'll see your work referenced in changelogs and white papers within weeks.",
  },
]

type WorkExample = {
  area: string
  title: string
  body: string
}

// Real Phase 10-24 work, framed as candidate-facing capability descriptions.
const WORK_EXAMPLES: WorkExample[] = [
  {
    area: "ML systems",
    title: "Close a corpus-vs-detector granularity gap with a clustering layer",
    body: "Expert NMR references count chemical environments; peak-pickers find multiplet lines. Build the algorithm that bridges them, validate it against a 20-fixture corpus, and clear the strict median-Δ≤2 promotion gate.",
  },
  {
    area: "Backend · Python",
    title: "Cut a 5.5-minute Bruker FT pipeline to 3.6 minutes",
    body: "Profile a 98,304-point ¹³C dense-spectrum hot path. Find the bottleneck without changing the public response envelope or any audit ledger entry. Re-bench against the regression corpus and ship the gain by fixture_id.",
  },
  {
    area: "Frontend · TypeScript",
    title: "Build a detector-agnostic results panel",
    body: "Two detection backends return different per-peak shapes (GSD's open `metadata` dict vs legacy's typed top-level fields). Design the adapter + unified envelope so a single React component renders both, columns adapting to whichever fields the backend populated.",
  },
  {
    area: "Scientific computing",
    title: "Per-peak QC fit metrics, surfaced honestly",
    body: "Expose reduced χ², RMSE, FWHM, S/N, and baseline σ as a green / yellow / red traffic light per peak. Catch the case where one detector reports raw signal-domain values while another reports normalised — and surface the units mismatch instead of papering over it.",
  },
  {
    area: "Validation infrastructure",
    title: "A regression test that fails by fixture_id",
    body: "Generate per-fixture A/B JSON between two detection backends on a 20-fixture corpus. Wire it into CI so any > 50% drift on any single fixture surfaces with the failing fixture_id called out by name.",
  },
  {
    area: "Product · Regulatory",
    title: "Wire spectroscopy evidence into regulatory action items",
    body: "Close the loop between a detected impurity, a residual-solvent class, an ICH Q3D limit, and a dossier-linked action item — with the audit ledger entry preserved every step of the way.",
  },
]

type Principle = {
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties; "aria-hidden"?: boolean }>
  title: string
  body: string
}

const HOW_WE_WORK: Principle[] = [
  {
    icon: GitBranch,
    title: "Additive, never destructive.",
    body: "Every endpoint, every regression test, every white-paper claim must stay green across releases. New evidence layers ship alongside old ones; we don't break the contract.",
  },
  {
    icon: FileText,
    title: "Write the doc with the code.",
    body: "The technical white paper is part of the product, not a separate deliverable. Every important change updates the relevant section in the same task that ships the change.",
  },
  {
    icon: Users,
    title: "Pair-by-default for cross-discipline work.",
    body: "ML engineer + analytical chemist + regulatory affairs reviewer on the same feature. The combinations are the moat.",
  },
  {
    icon: Compass,
    title: "Strong opinions, gated by data.",
    body: "Have a view. Then publish the corpus, the gate, and the threshold that would change your mind. We pre-register validation methodology before shipping.",
  },
]

type RubricItem = { test: boolean; label: string }

const WE_TEST_FOR: RubricItem[] = [
  { test: true, label: "Pharma / regulated-science domain literacy (or willingness to acquire it fast)" },
  { test: true, label: "System design under audit constraints — immutability, traceability, signoff" },
  { test: true, label: "Reading + writing typed contracts (Pydantic models, OpenAPI schemas, TS types)" },
  { test: true, label: "Honest debugging — describing what you'd measure, not what you'd guess" },
  { test: true, label: "Code review against published methodology (we'll share a real PR)" },
]

const WE_DONT_TEST: RubricItem[] = [
  { test: false, label: "Leetcode-style algorithmic puzzles unrelated to the work" },
  { test: false, label: "Whiteboard coding without a real spec, real data, or real failure modes" },
  { test: false, label: "Trick-question system-design hypotheticals that ignore regulatory constraints" },
  { test: false, label: "Cultural-fit interviews without a written rubric" },
]

type RoleCategory = {
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties; "aria-hidden"?: boolean }>
  name: string
  description: string
  openCount: number
  registerLabel: string
}

// Honest empty state — when no role is open in a category, we link to a
// "register interest" path instead of fabricating a posting. Update the
// openCount when real postings ship.
const ROLE_CATEGORIES: RoleCategory[] = [
  {
    icon: Microscope,
    name: "Engineering",
    description:
      "Backend (Python · FastAPI), Frontend (TypeScript · Next.js · React), ML systems, infrastructure, data integrity.",
    openCount: 0,
    registerLabel: "Register interest — Engineering",
  },
  {
    icon: FlaskConical,
    name: "Science",
    description:
      "Analytical chemistry, NMR / LC-MS / HRMS / MS/MS, peak categorisation curation, validation-corpus design.",
    openCount: 0,
    registerLabel: "Register interest — Science",
  },
  {
    icon: ShieldCheck,
    name: "Regulatory affairs",
    description:
      "FDA AI framework + EMA reflection paper alignment, ICH Q2(R2) audit-ledger expertise, dossier-template authoring.",
    openCount: 0,
    registerLabel: "Register interest — Regulatory",
  },
  {
    icon: Briefcase,
    name: "Go-to-market",
    description:
      "Sales (pharma R&D + CRO), customer success, partnerships, scientific marketing.",
    openCount: 0,
    registerLabel: "Register interest — GTM",
  },
]

type Benefit = {
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties; "aria-hidden"?: boolean }>
  name: string
  body: string
}

const BENEFITS: Benefit[] = [
  {
    icon: GraduationCap,
    name: "Conference + publication budget",
    body: "ACS, Pittcon, RSC-ICMS, ENC, ASMS, plus your travel + paper-processing fees. We want you publishing what you build.",
  },
  {
    icon: Sparkles,
    name: "Scientific compute, not just dev laptops",
    body: "Real budget for retraining shift-prediction models, running corpus expansions, and benchmarking on instrument data — not just running unit tests.",
  },
  {
    icon: Headphones,
    name: "On-instrument time",
    body: "Quarterly site visits to partner labs. The platform feels different after you've watched an analyst use it for a real submission.",
  },
  {
    icon: Globe2,
    name: "Remote-friendly within hub timezones",
    body: "Most roles support hybrid or remote within Americas / EMEA / APAC. We anchor synchronous work to your office timezone, not a single HQ.",
  },
  {
    icon: Scale,
    name: "Transparent bands, geo-parity within seniority",
    body: "Salary bands published at offer time, indexed annually. Equity meaningful at every level. Region parity within seniority — we don't discount EMEA / APAC offers below market.",
  },
  {
    icon: Mail,
    name: "Health, parental, retirement — covered as the floor",
    body: "Comprehensive medical / dental / vision in every hub, 16 weeks paid parental leave, retirement match. Standard expectations; not a perk.",
  },
]

type Stage = {
  step: string
  title: string
  duration: string
  body: string
}

const INTERVIEW_PROCESS: Stage[] = [
  {
    step: "01",
    title: "Intro call",
    duration: "30 min",
    body: "Hiring manager. We share the role spec, the team you'd work with, the actual problems open. You share what you'd want to build. No screen-share, no surprise quizzes.",
  },
  {
    step: "02",
    title: "Domain conversation",
    duration: "60 min",
    body: "A specialist on the team. We walk through a real shipped artifact (a Phase release, a validation gate, a regulatory dossier template) and you tell us what you'd change, what you'd measure, what you'd test.",
  },
  {
    step: "03",
    title: "Take-home (paid)",
    duration: "4-6 hours",
    body: "A real PR-style task scoped to a few hours. We pay for your time. You get the same spec a teammate would get and you can ask clarifying questions throughout. No artificial time limit.",
  },
  {
    step: "04",
    title: "Team panel + reference",
    duration: "Half day",
    body: "Three short conversations with future peers — one technical, one cross-functional, one with someone whose work yours would block on. We ping a reference of your choice. Decision within five business days.",
  },
]

type Office = {
  city: string
  framing: string
  remoteNote: string
}

const HUBS: Office[] = [
  {
    city: "Boston, MA",
    framing: "Headquarters · Americas",
    remoteNote: "Hybrid (2-3 days in-office) within MA, NH, RI · Remote within ET / CT timezones",
  },
  {
    city: "London, UK",
    framing: "EMEA hub · Regulatory liaison",
    remoteNote: "Hybrid within Greater London · Remote within GMT / CET timezones",
  },
  {
    city: "Singapore",
    framing: "APAC hub",
    remoteNote: "Hybrid within Singapore · Remote within SGT / JST timezones",
  },
]

export function CareersPage() {
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
          <div className="relative mx-auto max-w-7xl px-5 py-20 sm:px-6 lg:px-8 lg:py-28">
            <p
              className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
              style={{ color: "var(--mt-teal-ink)" }}
            >
              Careers at MolTrace
            </p>
            <h1 className="mt-3 max-w-4xl text-4xl font-semibold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl">
              We hire the way we{" "}
              <span style={{ color: "var(--mt-teal-ink)" }}>ship</span> — deliberately, with clear gates.
            </h1>
            <p className="mt-6 max-w-3xl text-lg leading-relaxed text-muted-foreground sm:text-xl">
              If you've worked in regulated science and been frustrated by the toolchain, you'll
              feel at home. The bar is high, the compensation matches, and the work outlasts you in
              regulatory ledgers.
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-4">
              <Button asChild size="lg" className="gap-2">
                <Link href="#open-roles">
                  See open roles
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline" className="gap-2">
                <Link href="/contact">
                  Talk to us first
                  <Mail className="h-4 w-4" />
                </Link>
              </Button>
            </div>
          </div>
        </section>

        {/* ── Why join ─────────────────────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal-ink)" }}
              >
                Why join MolTrace
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Four things you won't find at most "AI startups".
              </h2>
            </div>
            <div className="mt-12 grid gap-6 sm:grid-cols-2">
              {WHY_JOIN.map((reason) => {
                const Icon = reason.icon
                return (
                  <article
                    key={reason.number}
                    className="group rounded-2xl border bg-card p-6 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md sm:p-7"
                    style={{ borderTop: "3px solid var(--mt-teal)" }}
                  >
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
                        <span
                          className="font-mono text-xs font-bold tabular-nums tracking-tight"
                          style={{ color: "var(--mt-teal-ink)" }}
                        >
                          {reason.number}
                        </span>
                        <h3 className="mt-1 text-lg font-semibold leading-tight tracking-tight sm:text-xl">
                          {reason.title}
                        </h3>
                      </div>
                    </div>
                    <p className="mt-4 text-sm leading-relaxed text-muted-foreground">{reason.body}</p>
                  </article>
                )
              })}
            </div>
          </div>
        </section>

        {/* ── What you'll actually work on ──────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal-ink)" }}
              >
                What you'll actually work on
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Six examples of recent work, written like a teammate would describe them.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                These aren't hypothetical roadmap items — they're capabilities that shipped in the
                last few release cycles. Open the docs to verify. The work is real.
              </p>
            </div>
            <div className="mt-12 grid gap-6 lg:grid-cols-2">
              {WORK_EXAMPLES.map((work) => (
                <article
                  key={work.title}
                  className="rounded-2xl border bg-card p-6 shadow-sm sm:p-7"
                  style={{ borderLeft: "3px solid var(--mt-teal)" }}
                >
                  <p
                    className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                    style={{ color: "var(--mt-teal-ink)" }}
                  >
                    {work.area}
                  </p>
                  <h3 className="mt-2 text-lg font-semibold leading-tight tracking-tight sm:text-xl">
                    {work.title}
                  </h3>
                  <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{work.body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        {/* ── How we work ─────────────────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal-ink)" }}
              >
                How we work
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Working principles, extended from the architecture.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Our four design commitments don't stop at the codebase. They shape how we run
                meetings, how we review PRs, and how we decide what to ship.
              </p>
            </div>
            <div className="mt-12 grid gap-6 sm:grid-cols-2">
              {HOW_WE_WORK.map((p) => {
                const Icon = p.icon
                return (
                  <div
                    key={p.title}
                    className="rounded-2xl border bg-card p-6 sm:p-7"
                    style={{ borderTop: "3px solid var(--mt-teal)" }}
                  >
                    <Icon
                      className="h-6 w-6"
                      style={{ color: "var(--mt-teal)" }}
                      aria-hidden
                    />
                    <h3 className="mt-4 text-lg font-semibold tracking-tight">{p.title}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{p.body}</p>
                  </div>
                )
              })}
            </div>
          </div>
        </section>

        {/* ── Hiring rubric ───────────────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal-ink)" }}
              >
                Our hiring philosophy
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Published rubric. Same one for every candidate.
              </h2>
            </div>
            <div className="mt-12 grid gap-6 lg:grid-cols-2">
              <div className="rounded-2xl border bg-card p-6 shadow-sm sm:p-7">
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]"
                  style={{ color: "var(--mt-teal-ink)" }}
                >
                  We test for
                </p>
                <ul className="mt-5 space-y-3.5">
                  {WE_TEST_FOR.map((item) => (
                    <li key={item.label} className="flex gap-3 text-sm leading-relaxed">
                      <span
                        className="mt-1 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full font-mono text-[9px] font-bold"
                        style={{
                          backgroundColor: "var(--mt-teal-soft)",
                          color: "var(--mt-teal)",
                        }}
                        aria-hidden
                      >
                        ✓
                      </span>
                      <span className="text-foreground">{item.label}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div
                className="rounded-2xl border bg-muted/30 p-6 sm:p-7"
                style={{ borderColor: "color-mix(in oklab, var(--mt-amber, #B45309) 30%, transparent)" }}
              >
                <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-amber-700 dark:text-amber-400">
                  We won't waste your time on
                </p>
                <ul className="mt-5 space-y-3.5">
                  {WE_DONT_TEST.map((item) => (
                    <li key={item.label} className="flex gap-3 text-sm leading-relaxed">
                      <span
                        className="mt-1 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-amber-100 font-mono text-[9px] font-bold text-amber-700 dark:bg-amber-950/40 dark:text-amber-300"
                        aria-hidden
                      >
                        ✗
                      </span>
                      <span className="text-muted-foreground">{item.label}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* ── Open roles ─────────────────────────────────────────────────── */}
        <section id="open-roles" className="border-b scroll-mt-20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="flex flex-wrap items-end justify-between gap-6">
              <div className="max-w-3xl">
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                  style={{ color: "var(--mt-teal-ink)" }}
                >
                  Open roles
                </p>
                <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                  Honest about what's open. Honest about what isn't.
                </h2>
                <p className="mt-4 text-base text-muted-foreground">
                  We don't post placeholder roles to look like we're hiring. When a category is
                  empty, register interest — we route shortlisted intros directly to the hiring
                  manager when the role does open.
                </p>
              </div>
              <Badge variant="outline" className="border-dashed text-xs">
                Updated {new Date().toLocaleDateString("en-US", { year: "numeric", month: "short" })}
              </Badge>
            </div>
            <div className="mt-12 space-y-4">
              {ROLE_CATEGORIES.map((cat) => {
                const Icon = cat.icon
                const hasOpen = cat.openCount > 0
                return (
                  <div
                    key={cat.name}
                    className="rounded-2xl border bg-card p-6 shadow-sm sm:p-7"
                    style={{ borderLeft: "3px solid var(--mt-teal)" }}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-5">
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
                          <div className="flex items-center gap-3">
                            <h3 className="text-lg font-semibold tracking-tight sm:text-xl">
                              {cat.name}
                            </h3>
                            {hasOpen ? (
                              <Badge
                                className="border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300"
                                variant="outline"
                              >
                                {cat.openCount} open
                              </Badge>
                            ) : (
                              <Badge variant="outline" className="text-muted-foreground">
                                Not currently hiring
                              </Badge>
                            )}
                          </div>
                          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                            {cat.description}
                          </p>
                        </div>
                      </div>
                      <Button
                        asChild
                        variant={hasOpen ? "default" : "outline"}
                        size="sm"
                        className="shrink-0 gap-1.5"
                      >
                        <Link
                          href={`/contact?reason=${encodeURIComponent(cat.registerLabel)}`}
                        >
                          {hasOpen ? "View role" : "Register interest"}
                          <ArrowRight className="h-3.5 w-3.5" />
                        </Link>
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </section>

        {/* ── Compensation + benefits ────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal-ink)" }}
              >
                Compensation & benefits
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Framed around the work, not generic perks.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                The benefits below are the ones we picked because they make the work better. The
                standard health / parental / retirement floor is covered too — it's the floor, not
                the differentiator.
              </p>
            </div>
            <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {BENEFITS.map((b) => {
                const Icon = b.icon
                return (
                  <div
                    key={b.name}
                    className="rounded-2xl border bg-card p-5 sm:p-6"
                  >
                    <Icon
                      className="h-5 w-5"
                      style={{ color: "var(--mt-teal)" }}
                      aria-hidden
                    />
                    <p className="mt-3 text-base font-semibold tracking-tight">{b.name}</p>
                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{b.body}</p>
                  </div>
                )
              })}
            </div>
          </div>
        </section>

        {/* ── Interview process ──────────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal-ink)" }}
              >
                Interview process
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Four stages, written down, with timelines you can plan around.
              </h2>
            </div>
            <ol className="mt-12 grid gap-4 lg:grid-cols-4">
              {INTERVIEW_PROCESS.map((stage) => (
                <li
                  key={stage.step}
                  className="relative flex flex-col rounded-2xl border bg-card p-6 shadow-sm sm:p-7"
                  style={{ borderTop: "3px solid var(--mt-teal)" }}
                >
                  <span
                    className="font-mono text-3xl font-bold tabular-nums tracking-tight"
                    style={{ color: "var(--mt-teal-ink)" }}
                  >
                    {stage.step}
                  </span>
                  <h3 className="mt-3 text-lg font-semibold tracking-tight">{stage.title}</h3>
                  <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                    {stage.duration}
                  </p>
                  <p className="mt-4 flex-1 text-sm leading-relaxed text-muted-foreground">
                    {stage.body}
                  </p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* ── Where we work ──────────────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal-ink)" }}
              >
                Hubs & remote
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Three hubs. Remote within your hub timezone.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                We anchor synchronous work to your office timezone — never a single HQ. The hubs
                are chosen for proximity to pharma R&amp;D and regulatory ecosystems.
              </p>
            </div>
            <div className="mt-12 grid gap-6 lg:grid-cols-3">
              {HUBS.map((office) => (
                <div
                  key={office.city}
                  className="rounded-2xl border bg-card p-6 shadow-sm"
                  style={{ borderTop: "3px solid var(--mt-teal)" }}
                >
                  <MapPin className="h-5 w-5 text-muted-foreground" aria-hidden />
                  <p className="mt-4 text-lg font-semibold tracking-tight">{office.city}</p>
                  <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                    {office.framing}
                  </p>
                  <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
                    {office.remoteNote}
                  </p>
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
                Don't see your role?
              </h2>
              <p className="mt-4 text-base text-muted-foreground sm:text-lg">
                Tell us what you'd build. The strongest hires we've made started with a one-line
                pitch that didn't match any open posting.
              </p>
              <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
                <Button asChild size="lg" className="gap-2">
                  <Link href="/contact?reason=Careers%20%E2%80%94%20unsolicited%20pitch">
                    Pitch us a role
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="outline" className="gap-2">
                  <Link href="/about">
                    Read about MolTrace
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
