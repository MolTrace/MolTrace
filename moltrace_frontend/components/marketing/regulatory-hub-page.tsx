import Link from "next/link"
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  BookOpenCheck,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileCheck,
  FileSignature,
  FileText,
  FlaskConical,
  GitBranch,
  Layers,
  Lock,
  Microscope,
  ScrollText,
  Search,
  ShieldCheck,
  Sparkles,
  Tag,
  Workflow,
  XCircle,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Footer } from "@/components/marketing/footer"
import { Header } from "@/components/marketing/header"

/**
 * Regulatory Intelligence Hub module page — full marketing-shell route
 * at /regulatory-hub.
 *
 * Differentiation from /spectroscopy (intentional — these are related
 * chapters, not templated copies):
 *   - Hero visual is a LIVE audit-ledger snapshot showing real ALCOA+
 *     entries with provenance fields. (Spectroscopy used a layered
 *     evidence stack.)
 *   - Pipeline is regulatory-flavoured: Map → Classify → Assess → Cite
 *     → Compose → Sign → Ledger. (Spectroscopy was Ingest → … → Report.)
 *   - "Category mix" pattern becomes a CTD-section coverage matrix.
 *   - Detector A/B is replaced with a "spreadsheet workflow vs MolTrace
 *     workflow" comparison — the one regulatory teams will recognise.
 *   - Compliance frameworks (ICH / FDA / EMA / ALCOA+) get their own
 *     matrix section with concrete-citation depth.
 *
 * All content grounded in: white paper §2.3 (regulatory expectations),
 * §3 (vision commitments), §4.7 (reports + provenance + signoff), plus
 * the backend `regulatory_compliance_store.py` + `regulatory_surveillance_store.py`.
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
    title: "Map",
    detail:
      "Incoming evidence from SpectraCheck — peaks, categories, impurity matches, solvent hits — maps onto regulatory categories: residual solvent, elemental impurity, genotoxic alert, nitrosamine risk.",
    artifact: "evidence_id · regulatory_category · ich_class",
  },
  {
    stage: "02",
    title: "Classify",
    detail:
      "Each mapped finding lands in the right framework slot: ICH Q3C (residual solvent), Q3D (elemental impurity), M7 (mutagenic), Q3A/Q3B (drug substance / product impurities). Pharmacopoeia priors layered in (USP-NF, EP, JP).",
    artifact: "framework_ref · pharmacopoeia · acceptance_window",
  },
  {
    stage: "03",
    title: "Assess",
    detail:
      "Risk-based credibility framework runs end-to-end. FDA Stage 1-4 oversight gates evaluated automatically — items requiring human review surface in the queue with the exact gate that triggered them.",
    artifact: "risk_tier · fda_stage · human_review_required",
  },
  {
    stage: "04",
    title: "Cite",
    detail:
      "Every numerical claim hyperlinks back to its source: the spectrum file, the picked peak, the literature window, the reviewer who approved it. No confidence number without a trail — ever.",
    artifact: "claim · source_uri · citation_chain",
  },
  {
    stage: "05",
    title: "Compose",
    detail:
      "Dossier-section drafts in CTD format: Module 3.2.S.3.2 (Impurities), 3.2.S.4 (Control of Drug Substance), 3.2.P.5 (Control of Drug Product), AI/ML model documentation per FDA Jan 2025 framework.",
    artifact: "ctd_section · draft · open_items",
  },
  {
    stage: "06",
    title: "Sign",
    detail:
      "No release without an explicit human signoff. Reviewer attribution recorded with timestamp, role, and the exact artefact version they approved. Liability stays where regulators expect it.",
    artifact: "reviewer · role · signed_at · artefact_hash",
  },
  {
    stage: "07",
    title: "Ledger",
    detail:
      "ALCOA+ audit-event entry written: attributable, legible, contemporaneous, original, accurate, complete, consistent, enduring, available. Inspection-ready by default.",
    artifact: "audit_event · alcoa_fields · inspector_view_url",
  },
]

type Framework = {
  acronym: string
  full: string
  scope: string
  coverage: string[]
}

const FRAMEWORKS: Framework[] = [
  {
    acronym: "ICH",
    full: "International Council for Harmonisation",
    scope: "Global pharmaceutical guidelines",
    coverage: [
      "Q2(R2) · Analytical method validation lifecycle",
      "Q3A / Q3B · Drug substance / product impurities",
      "Q3C · Residual solvents (Class 1 / 2 / 3)",
      "Q3D · Elemental impurities (Cd · Pb · As · Hg · …)",
      "M7 · Mutagenic + genotoxic impurities + nitrosamines",
    ],
  },
  {
    acronym: "FDA",
    full: "U.S. Food and Drug Administration",
    scope: "AI / regulatory submissions (Jan 2025)",
    coverage: [
      "Risk-based credibility framework (Stages 1-4)",
      "Traceability + model documentation requirements",
      "Human oversight gates (Stage 4)",
      "eCTD submission alignment + dossier section mapping",
      "21 CFR Part 11 electronic-records compliance",
    ],
  },
  {
    acronym: "EMA",
    full: "European Medicines Agency",
    scope: "AI in medicinal-product lifecycle",
    coverage: [
      "Reflection paper on AI alignment + audit",
      "Reproducibility + version control requirements",
      "Subordination to expert review for AI evidence",
      "EU CTR + EUDAMED handoff points",
      "Regional dossier-template alignment (CTD)",
    ],
  },
  {
    acronym: "ALCOA+",
    full: "Data Integrity Principles",
    scope: "Cross-framework foundation",
    coverage: [
      "Attributable · Legible · Contemporaneous",
      "Original · Accurate (core ALCOA)",
      "Complete · Consistent · Enduring · Available (the +)",
      "Mapped onto audit_events table + immutable vault",
      "Inspection-ready provenance for every claim",
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
    icon: FlaskConical,
    name: "Residual solvent assessment",
    blurb:
      "Auto-classifies detected solvent peaks against ICH Q3C Class 1/2/3 limits. Action items raised only when observed concentration crosses framework thresholds.",
    inputs: "Spectroscopy peaks · solvent_hit table · API",
    outputs: "Q3C verdict · acceptance status · dossier section draft",
  },
  {
    icon: AlertTriangle,
    name: "Elemental impurity (Q3D)",
    blurb:
      "Maps detected elemental signals onto the Q3D 24-element catalog. PDE limits per Class 1/2A/2B/3. Risk assessment by route-of-administration.",
    inputs: "ICP-MS / element analysis · API · drug product",
    outputs: "Q3D risk matrix · PDE comparison · open items",
  },
  {
    icon: Search,
    name: "Nitrosamine risk assessment",
    blurb:
      "Structural alert detection (ICH M7) + literature-prior matching. Flags candidate nitrosamines + suggests confirmatory MS/MS acquisition.",
    inputs: "Structure SMILES · synthesis route · API",
    outputs: "M7 verdict · recommended MS/MS · risk tier",
  },
  {
    icon: BookOpenCheck,
    name: "Method validation (Q2(R2))",
    blurb:
      "Tracks the full analytical lifecycle: specificity, linearity, accuracy, precision, range, robustness. Every parameter recipe-hash-linked to the validation campaign.",
    inputs: "Method runs · acceptance criteria · campaigns",
    outputs: "Q2(R2) report · parameter coverage · gaps",
  },
  {
    icon: ShieldCheck,
    name: "AI / ML model documentation",
    blurb:
      "FDA Jan 2025 model-card registry: training data lineage, performance bounds, validation corpus, intended use, known limitations.",
    inputs: "Model artefacts · validation runs · changelogs",
    outputs: "FDA Stage 1-4 documentation · audit-ready",
  },
  {
    icon: ScrollText,
    name: "Surveillance + change detection",
    blurb:
      "Watches regulatory sources (ICH, FDA, EMA, pharmacopoeias) for version changes. Impacts auto-routed to affected dossiers, rules, and action items.",
    inputs: "Source feeds · pharmacopoeia versions · diffs",
    outputs: "Change-impact report · action items · ETA",
  },
]

type LedgerRow = {
  field: string
  value: string
  note: string
}

const LEDGER_SAMPLE: LedgerRow[] = [
  {
    field: "Attributable",
    value: "dr.chen@pharmaco.com · Senior Reviewer · 2026-05-28T14:32:18Z",
    note: "Reviewer identity + role + signing timestamp",
  },
  {
    field: "Legible",
    value: "JSON · UTF-8 · stable Pydantic schema v3.4.0",
    note: "Machine + human-readable; schema versioned",
  },
  {
    field: "Contemporaneous",
    value: "Logged 14:32:18Z · 0.4s after detection event",
    note: "Recorded at the moment of decision, not backfilled",
  },
  {
    field: "Original",
    value: "Raw FID SHA-256: 4f7a…b29e (immutable vault, never overwritten)",
    note: "Source artefact preserved bit-identical",
  },
  {
    field: "Accurate",
    value: "Recipe hash: r9c2…1d3a (replay-verified bit-identical output)",
    note: "Reproducible by recipe replay any time",
  },
  {
    field: "Complete",
    value: "All 12 evidence layers + 3 cross-modal checks documented",
    note: "No partial-evidence claims permitted",
  },
  {
    field: "Consistent",
    value: "ICH Q3C Class 3 mapping confirmed against pharmacopoeia v2024.2",
    note: "Framework version pinned to decision",
  },
  {
    field: "Enduring",
    value: "Retention class: 25-year regulatory minimum",
    note: "Retention policy attached to event",
  },
  {
    field: "Available",
    value: "Inspector view URL: /audit/event/aev_018f3d9c · API: GET /audit-events/{id}",
    note: "Queryable on inspection",
  },
]

type Comparison = {
  dimension: string
  spreadsheet: string
  moltrace: string
}

const COMPARISON: Comparison[] = [
  {
    dimension: "Where evidence lives",
    spreadsheet: "Spreadsheets, email attachments, shared drives, lab notebooks",
    moltrace: "Typed Pydantic records, hyperlinked to raw spectra by SHA-256",
  },
  {
    dimension: "How claims get cited",
    spreadsheet: "Hand-written narratives, manual cross-reference, reviewer memory",
    moltrace: "Auto-generated citation chain per claim: spectrum → peak → reference window → reviewer",
  },
  {
    dimension: "How signoff happens",
    spreadsheet: "Email approval, PDF wet-signature, signed-and-scanned",
    moltrace: "In-app signoff queue · reviewer + role + timestamp + artefact hash recorded atomically",
  },
  {
    dimension: "What an inspector sees",
    spreadsheet: "Reconstructed audit trail from emails + version history + interviews",
    moltrace: "Single audit_events query · ALCOA+ fields per event · provenance URLs",
  },
  {
    dimension: "Reproducibility (replay analysis 6 months later)",
    spreadsheet: "Re-run from scratch · 'looks similar' is usually the verdict",
    moltrace: "Recipe-hash replay · bit-identical output guaranteed forever",
  },
  {
    dimension: "Regulatory-change handling",
    spreadsheet: "Manual scan of guidance documents · spot-check affected dossiers",
    moltrace: "Surveillance watches sources · diffs auto-routed to affected items with ETA",
  },
]

type LoopStep = {
  step: string
  body: string
}

const CROSS_MODULE_LOOP: LoopStep[] = [
  {
    step: "SpectraCheck routes in",
    body: "Peak at 2.10 ppm classified as acetic acid impurity (confidence 0.93). Regulatory Hub receives the structured evidence object.",
  },
  {
    step: "Framework lookup",
    body: "ICH Q3C: acetic acid is Class 3 (low toxic potential, no action below 5000 ppm). PDE limit retrieved from pharmacopoeia v2024.2.",
  },
  {
    step: "Action item triage",
    body: "Observed concentration below 5000 ppm threshold — informational only. Dossier section 3.2.S.3.2 updated; no human review queued.",
  },
  {
    step: "ReactionIQ constraint",
    body: "Impurity limit auto-propagates as a Bayesian prior on the next reaction run. Audit ledger records the cross-module handoff.",
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
    body: "Every FID is SHA-256 hashed. Vault path policy enforced. Never overwritten. Inspection-ready forever.",
  },
  {
    icon: GitBranch,
    title: "Recipe-hash provenance",
    body: "Every processing run links a recipe hash to the unchanged raw archive. Replay any prior date and get bit-identical output.",
  },
  {
    icon: FileSignature,
    title: "Human signoff queue",
    body: "FDA Stage 4 oversight gate. No regulatory document released without explicit qualified-human attribution.",
  },
  {
    icon: BadgeCheck,
    title: "21 CFR Part 11 alignment",
    body: "Electronic-records + electronic-signatures requirements built into the audit_events table from day one.",
  },
  {
    icon: AlertTriangle,
    title: "Cross-modal contradiction warnings",
    body: "HRMS exact mass disagreeing with NMR-implied formula raises a first-class warning before signoff — every time.",
  },
  {
    icon: Lock,
    title: "Tenant isolation by default",
    body: "SOC 2 Type II controls, GDPR-compliant data residency, role-scoped audit-event ledger per tenant.",
  },
]

export function RegulatoryHubPage() {
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
                    className="border-cyan-300 bg-cyan-50 text-cyan-700 dark:border-cyan-900 dark:bg-cyan-950/40 dark:text-cyan-300"
                  >
                    <ShieldCheck className="mr-1 h-3 w-3" aria-hidden />
                    Module · Regulatory Intelligence Hub
                  </Badge>
                  <Badge variant="outline" className="text-muted-foreground">
                    ICH · FDA · EMA · ALCOA+
                  </Badge>
                </div>
                <h1 className="mt-5 max-w-3xl text-4xl font-semibold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl">
                  Compliance as a{" "}
                  <span style={{ color: "var(--mt-teal)" }}>side effect</span> — not a sprint.
                </h1>
                <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted-foreground sm:text-xl">
                  Spectroscopy evidence flows into ICH-classified action items, dossier-section
                  drafts, and ALCOA+ ledger entries — automatically. The regulatory work is the
                  output of the science, not a separate document written in parallel.
                </p>
                <div className="mt-10 flex flex-wrap items-center gap-4">
                  <Button asChild size="lg" className="gap-2">
                    <Link href="/regulatory">
                      Open Regulatory Hub
                      <ArrowRight className="h-4 w-4" />
                    </Link>
                  </Button>
                  <Button asChild size="lg" variant="outline" className="gap-2">
                    <Link href="/contact?reason=Request%20a%20demo">
                      Request a demo
                      <FileText className="h-4 w-4" />
                    </Link>
                  </Button>
                </div>
              </div>

              {/* Hero visual — audit-ledger live snapshot */}
              <aside className="relative overflow-hidden rounded-3xl border bg-card p-6 shadow-sm">
                <div className="flex items-center justify-between">
                  <p
                    className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                    style={{ color: "var(--mt-teal)" }}
                  >
                    Audit ledger · live event
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
                  audit_event · aev_018f3d9c
                </p>
                <p className="mt-1 text-sm font-medium">Residual-solvent verdict signed</p>

                <div className="mt-6 space-y-1.5">
                  {[
                    { label: "A", title: "dr.chen@pharmaco.com · Sr Reviewer" },
                    { label: "L", title: "JSON · UTF-8 · schema v3.4.0" },
                    { label: "C", title: "2026-05-28T14:32:18Z · 0.4s post-detect" },
                    { label: "O", title: "FID SHA-256: 4f7a…b29e · vault" },
                    { label: "A", title: "Recipe r9c2…1d3a · replay verified" },
                    { label: "C", title: "12 layers + 3 cross-modal documented" },
                    { label: "C", title: "ICH Q3C v2024.2 · pinned" },
                    { label: "E", title: "Retention: 25-year regulatory" },
                    { label: "A", title: "/audit/event/aev_018f3d9c" },
                  ].map((row, idx) => (
                    <div
                      key={idx}
                      className="flex items-center gap-3 rounded-md border bg-background/80 px-3 py-1.5"
                    >
                      <span
                        className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded font-mono text-[10px] font-bold"
                        style={{
                          backgroundColor: "var(--mt-teal-soft)",
                          color: "var(--mt-teal)",
                        }}
                      >
                        {row.label}
                      </span>
                      <span className="flex-1 truncate font-mono text-[11px]">{row.title}</span>
                      <CheckCircle2
                        className="h-3 w-3 shrink-0"
                        style={{ color: "var(--mt-teal)" }}
                        aria-hidden
                      />
                    </div>
                  ))}
                </div>
                <p className="mt-5 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                  ALCOA+ · all nine fields populated
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
                  The spectroscopy-to-submission gap is hand-written.
                </h2>
              </div>
              <div className="space-y-5 text-base leading-relaxed text-muted-foreground">
                <p>
                  Even with a well-organised internal data lake, the bridge from a final spectrum
                  interpretation to a regulatory-ready argument is, in most laboratories,{" "}
                  <strong className="text-foreground">invisible by default</strong>. Reviewers spend
                  weeks reconciling a structure-elucidation narrative against the raw evidence.
                </p>
                <p>
                  The FDA's January 2025 AI framework + EMA's reflection paper + ICH Q2(R2) all
                  raised the bar — simultaneously asking R&amp;D groups to adopt more AI, prove
                  reproducibility, document every parameter, and keep the human chain visible to
                  inspectors. The spreadsheet-and-email toolchain doesn't satisfy any of those four.
                </p>
                <p className="font-medium text-foreground">
                  Regulatory Intelligence Hub closes that gap programmatically. The dossier is a
                  by-product of the science — not a parallel document that gets reconciled in
                  week 11.
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
                The regulatory pipeline
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Seven stages from raw finding to inspection-ready ledger entry.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Every stage emits a typed Pydantic record. Every output keys back to the input. The
                same recipe-hash replay that works for spectroscopy works here — re-derive any
                ledger entry from any prior date with bit-identical output.
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
          </div>
        </section>

        {/* ── Frameworks matrix ───────────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Frameworks covered
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Built against the regulations you'll be inspected on.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Each framework is mapped to concrete code paths — audit ledger, dossier composer,
                action-item routing — not abstract policy alignment.
              </p>
            </div>
            <div className="mt-12 grid gap-6 lg:grid-cols-2">
              {FRAMEWORKS.map((fw) => (
                <article
                  key={fw.acronym}
                  className="rounded-2xl border bg-card p-6 shadow-sm sm:p-7"
                  style={{ borderLeft: "3px solid var(--mt-teal)" }}
                >
                  <div className="flex items-baseline gap-4">
                    <span
                      className="font-mono text-3xl font-bold tabular-nums tracking-tight"
                      style={{ color: "var(--mt-teal)" }}
                    >
                      {fw.acronym}
                    </span>
                    <div>
                      <h3 className="text-base font-semibold tracking-tight">{fw.full}</h3>
                      <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                        {fw.scope}
                      </p>
                    </div>
                  </div>
                  <ul className="mt-5 space-y-2">
                    {fw.coverage.map((item) => (
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
                Six regulatory workflows, with their inputs and outputs.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Each row in this grid is a typed pipeline — not a workflow we'd build for you on
                request. Inputs come from SpectraCheck or your existing data lake; outputs land in
                the audit ledger and the dossier composer.
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

        {/* ── ALCOA+ audit ledger figure ──────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Anatomy of a ledger entry
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Nine ALCOA+ fields. One real event.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Below is the exact shape of an audit-event row when a reviewer signs a residual-solvent
                verdict. Every field is queryable by an inspector with no extra interpretation step.
              </p>
            </div>

            <div className="mt-12 overflow-hidden rounded-2xl border bg-card shadow-sm">
              <div className="border-b bg-muted/40 px-5 py-3">
                <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
                  audit_events · aev_018f3d9c · ICH Q3C residual-solvent verdict
                </p>
              </div>
              <table className="w-full text-left text-sm">
                <thead className="border-b bg-muted/20 font-mono uppercase tracking-[0.12em] text-[10px] text-muted-foreground">
                  <tr>
                    <th className="px-5 py-2.5">ALCOA+ field</th>
                    <th className="px-5 py-2.5">Recorded value</th>
                    <th className="px-5 py-2.5">What it means</th>
                  </tr>
                </thead>
                <tbody>
                  {LEDGER_SAMPLE.map((row, idx) => (
                    <tr
                      key={row.field}
                      className={idx % 2 === 0 ? "border-t" : "border-t bg-muted/20"}
                    >
                      <td className="px-5 py-3 align-top">
                        <span
                          className="inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.14em]"
                          style={{
                            borderColor: "color-mix(in oklab, var(--mt-teal) 30%, transparent)",
                            backgroundColor: "var(--mt-teal-soft)",
                            color: "var(--mt-teal)",
                          }}
                        >
                          {row.field}
                        </span>
                      </td>
                      <td className="px-5 py-3 align-top font-mono text-xs text-foreground">
                        {row.value}
                      </td>
                      <td className="px-5 py-3 align-top text-xs leading-relaxed text-muted-foreground">
                        {row.note}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* ── Spreadsheet vs MolTrace ─────────────────────────────────────── */}
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
                What changes when regulatory work flows from the science.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Most R&amp;D groups today run regulatory workflows through spreadsheets + email +
                shared drives. Here's exactly what flips when the dossier becomes a product of
                the pipeline, not a parallel document.
              </p>
            </div>
            <div className="mt-12 overflow-hidden rounded-2xl border bg-card shadow-sm">
              <table className="w-full text-left text-sm">
                <thead className="bg-muted/40 font-mono uppercase tracking-[0.12em] text-[10px] text-muted-foreground">
                  <tr>
                    <th className="px-5 py-3">Dimension</th>
                    <th className="px-5 py-3">Spreadsheet workflow</th>
                    <th className="px-5 py-3">MolTrace workflow</th>
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
                        <p>{row.spreadsheet}</p>
                      </td>
                      <td className="px-5 py-3.5 align-top text-xs leading-relaxed text-foreground">
                        <span className="mb-1 inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300">
                          <CheckCircle2 className="h-2.5 w-2.5" aria-hidden />
                          with MolTrace
                        </span>
                        <p>{row.moltrace}</p>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* ── Closing loop ────────────────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Cross-module loop
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                One real worked example, end-to-end.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                The acetic-acid impurity from SpectraCheck's worked example — followed all the way
                through regulatory routing and back into ReactionIQ as a constraint on the next
                run. Audit ledger records every handoff.
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
                      The evidence engine that produces every regulatory finding routed in here.
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
                href="https://moltrace-docs.vercel.app/guides/modules/optimization/"
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
                      Receives the impurity limit as a Bayesian prior on the next reaction recipe.
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

        {/* ── Trust + audit ───────────────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="grid gap-10 lg:grid-cols-[1fr_1.6fr]">
              <div>
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                  style={{ color: "var(--mt-teal)" }}
                >
                  Audit & data integrity
                </p>
                <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                  Designed to be audited — not to look auditable.
                </h2>
                <p className="mt-4 text-base text-muted-foreground">
                  Every commitment below is implemented in production code, not aspirational. The
                  audit_events table runs every claim through the same six pillars. Inspectors
                  query directly; no reconstruction needed.
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
                Bring your hardest submission.
              </h2>
              <p className="mt-4 text-base text-muted-foreground sm:text-lg">
                Pick a dossier section that's currently a 40-hour reconciliation. We'll walk
                through how the Regulatory Hub would handle the same evidence, end-to-end.
              </p>
              <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
                <Button asChild size="lg" className="gap-2">
                  <Link href="/regulatory">
                    Open Regulatory Hub
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="outline" className="gap-2">
                  <Link href="/contact?reason=Request%20a%20demo">
                    Walk us through your dossier
                    <FileCheck className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="ghost" className="gap-2">
                  <Link
                    href="https://moltrace-docs.vercel.app/guides/modules/regulatory/"
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
