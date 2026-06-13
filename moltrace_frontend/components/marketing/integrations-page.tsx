import Link from "next/link"
import {
  AlertCircle,
  ArrowRight,
  BadgeCheck,
  Building2,
  CheckCircle2,
  Database,
  FileCheck,
  FileText,
  FlaskConical,
  GitBranch,
  Key,
  Layers,
  Lock,
  Microscope,
  Network,
  Plug,
  Server,
  ShieldCheck,
  Sparkles,
  Webhook,
  XCircle,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Footer } from "@/components/marketing/footer"
import { Header } from "@/components/marketing/header"

/**
 * Integrations module page — full marketing-shell route at /integrations.
 *
 * Differentiation from the other three Platform pages:
 *   - Hero visual is a LIVE CONNECTOR ROSTER (always-on status rather
 *     than iterative campaign or audit ledger). Vendors named, statuses
 *     coloured, ingestion counts and last-sync timestamps shown.
 *   - Pipeline is the connector lifecycle: Discover → Authenticate →
 *     Map → Normalize → Validate → Sync → Audit.
 *   - "Methods" matrix becomes a 4-category connector matrix:
 *     Instruments / LIMS+ELN / Identity / Regulatory data.
 *   - Use cases are integration scenarios (watch-folder ingest, ELN
 *     handoff, eCTD submission package, etc.).
 *   - Comparison flips to "siloed toolchain vs unified stack".
 *
 * Backend grounding: nmrcheck/interoperability_store.py — references
 * ConnectorRegistry, IngestionRun, MappingTemplate, WebhookSubscription,
 * OutboundSyncJob, RegulatorySubmissionPackage. All real entities.
 */

type LifecycleStage = {
  stage: string
  title: string
  detail: string
  artifact: string
}

const LIFECYCLE: LifecycleStage[] = [
  {
    stage: "01",
    title: "Discover",
    detail:
      "Auto-detect instrument watch-folders, LIMS endpoints, ELN APIs, and SSO discovery URLs. Catalog the system's data model — what objects it has, what we can read, what we can write.",
    artifact: "connector_registry · external_system · model_card",
  },
  {
    stage: "02",
    title: "Authenticate",
    detail:
      "OAuth 2.0, SAML 2.0, OIDC, mTLS, API keys, or signed JWTs — whichever the source supports. Credentials live in a vault reference (never in plaintext); rotations propagate via the credential-reference table.",
    artifact: "connector_credential_reference · scopes · rotation",
  },
  {
    stage: "03",
    title: "Map",
    detail:
      "Typed mapping templates define how the source system's fields become MolTrace projects, samples, sessions, dossiers, experiments, files, or action items. Versioned + signed by an admin reviewer.",
    artifact: "mapping_template · field_map · transformations",
  },
  {
    stage: "04",
    title: "Normalize",
    detail:
      "Vendor formats become canonical: Bruker FID through nmrglue, Agilent through proprietary parsers, mzML / mzXML kept as-is, JCAMP-DX normalized in-flight. Every conversion recipe-hash-linked.",
    artifact: "normalization_run · canonical_form · recipe_hash",
  },
  {
    stage: "05",
    title: "Validate",
    detail:
      "Schema + integrity checks before commit. SHA-256 of every binary, structural validation against the typed contract, regulatory-flag review for inbound submissions.",
    artifact: "integrity_check · schema_verdict · audit_event",
  },
  {
    stage: "06",
    title: "Sync",
    detail:
      "Real-time via signed webhooks (subscription-based) or batch via outbound sync jobs (back-pressure aware). Outbound pushes carry the audit-event ID so downstream systems can cite back.",
    artifact: "webhook_subscription · outbound_sync_job · checkpoint",
  },
  {
    stage: "07",
    title: "Audit",
    detail:
      "Every byte that crossed the connector boundary is logged with attribution. Inspectors query connector_events the same way they query audit_events — one ledger, end-to-end provenance.",
    artifact: "connector_event · external_object_link · provenance_uri",
  },
]

type ConnectorCategory = {
  acronym: string
  full: string
  scope: string
  bullets: string[]
}

const CONNECTORS: ConnectorCategory[] = [
  {
    acronym: "INST",
    full: "Instruments",
    scope: "NMR · LC-MS · HRMS · MS/MS",
    bullets: [
      "Bruker · TopSpin / IconNMR · watch-folder + IconNMR queue",
      "Varian / Agilent · VnmrJ · FID parsing via nmrglue",
      "JEOL · Delta · raw + processed exports",
      "Agilent · MassHunter · mzML / vendor-raw",
      "Thermo · Xcalibur · mzML / RAW",
      "Waters · MassLynx · mzML / RAW",
    ],
  },
  {
    acronym: "LIMS",
    full: "LIMS · ELN · sample registry",
    scope: "Sample + experiment lineage",
    bullets: [
      "LabWare LIMS · bidirectional sample + result sync",
      "STARLIMS · STARLIMS Connector + project lineage",
      "Benchling ELN · experiment handoff + protocol mapping",
      "IDBS E-WorkBook · result + audit-event push",
      "BIOVIA OneLab · workflow trigger + result push",
    ],
  },
  {
    acronym: "AUTH",
    full: "Identity · SSO · directory",
    scope: "Zero-trust authentication",
    bullets: [
      "Okta · SAML 2.0 + SCIM provisioning",
      "Azure Active Directory · OIDC + group mapping",
      "Google Workspace · SAML / OIDC",
      "Ping Identity · SAML / OIDC",
      "Auth0 · SAML / OIDC / social",
      "Generic OIDC / SAML 2.0 with metadata import",
    ],
  },
  {
    acronym: "REG",
    full: "Regulatory data · pharmacopoeia",
    scope: "Versioned standards + change feeds",
    bullets: [
      "USP-NF · monograph + acceptance window updates",
      "European Pharmacopoeia (EP) · diff feed",
      "Japanese Pharmacopoeia (JP) · diff feed",
      "ICH guideline tracking · Q2 / Q3 / M7 versions",
      "FDA guidance change detection · Jan 2025 framework feed",
      "EMA reflection-paper updates · regional supplements",
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
    icon: Server,
    name: "Instrument watch-folder ingest",
    blurb:
      "Drop a Bruker / Agilent / Thermo acquisition into the watched folder; SpectraCheck picks it up, hashes it into the vault, runs the pipeline, files the result.",
    inputs: "Folder path · vendor · acquisition policy",
    outputs: "Vault record · SpectraCheck session · audit_event",
  },
  {
    icon: FlaskConical,
    name: "ELN handoff (Benchling, IDBS)",
    blurb:
      "Experiment metadata from the ELN auto-binds to incoming spectra. Reverse: result + interpretation push back into the ELN as a structured attachment.",
    inputs: "ELN experiment ID · field mapping template",
    outputs: "Bound MolTrace session · ELN attachment + link",
  },
  {
    icon: Building2,
    name: "LIMS bidirectional sync",
    blurb:
      "Sample registry, batch IDs, project lineage stay synchronized. Inbound: sample → MolTrace context. Outbound: result + audit event → LIMS attachment.",
    inputs: "LIMS endpoint · sample object map · webhook hooks",
    outputs: "Synced project · result push · provenance link",
  },
  {
    icon: Key,
    name: "Single sign-on + provisioning",
    blurb:
      "Okta / Azure AD / Google SAML — same identity, same group membership, same audit attribution. SCIM provisioning keeps role grants in sync.",
    inputs: "IdP metadata · group → role map",
    outputs: "Provisioned users · scoped tenant access",
  },
  {
    icon: FileCheck,
    name: "eCTD submission package",
    blurb:
      "Bundle dossier sections + audit ledger + raw-data hashes into an eCTD-conformant package. Hand off to the regulatory-affairs team or submission-management system.",
    inputs: "Dossier ID · package profile (FDA / EMA / PMDA)",
    outputs: "Submission package · checksum manifest · audit trail",
  },
  {
    icon: Webhook,
    name: "Webhook events (real-time)",
    blurb:
      "Signed webhook subscriptions push events as they happen: new acquisition processed, dossier section signed, reaction round complete. HMAC-verified per delivery.",
    inputs: "Webhook URL · event topics · signing secret",
    outputs: "Signed payload · retry queue · delivery audit",
  },
]

type RosterRow = {
  vendor: string
  category: string
  status: "connected" | "syncing" | "pending" | "error"
  detail: string
  lastSync: string
}

const ROSTER_SAMPLE: RosterRow[] = [
  {
    vendor: "Bruker TopSpin · 4 instruments",
    category: "INST",
    status: "connected",
    detail: "247 acquisitions · 1.2 TB this week",
    lastSync: "Now",
  },
  {
    vendor: "Agilent MassHunter · 2 instruments",
    category: "INST",
    status: "syncing",
    detail: "189 mzML · 412 GB this week",
    lastSync: "2 min ago",
  },
  {
    vendor: "Benchling ELN",
    category: "ELN",
    status: "connected",
    detail: "31 experiments · bidirectional",
    lastSync: "4 min ago",
  },
  {
    vendor: "LabWare LIMS",
    category: "LIMS",
    status: "connected",
    detail: "186 samples · webhook + batch",
    lastSync: "8 min ago",
  },
  {
    vendor: "Okta SSO",
    category: "AUTH",
    status: "connected",
    detail: "47 users · SAML + SCIM",
    lastSync: "Continuous",
  },
  {
    vendor: "USP-NF feed",
    category: "REG",
    status: "pending",
    detail: "monograph diff queued",
    lastSync: "Ready",
  },
  {
    vendor: "Thermo Xcalibur · 1 instrument",
    category: "INST",
    status: "error",
    detail: "Vault credential expired — rotate",
    lastSync: "23 min ago",
  },
]

const STATUS_STYLE: Record<RosterRow["status"], { label: string; chip: string; dot: string; pulse: boolean }> = {
  connected: {
    label: "Connected",
    chip: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-900",
    dot: "bg-emerald-500",
    pulse: false,
  },
  syncing: {
    label: "Syncing",
    chip: "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/40 dark:text-sky-300 dark:border-sky-900",
    dot: "bg-sky-500",
    pulse: true,
  },
  pending: {
    label: "Pending",
    chip: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900",
    dot: "bg-amber-500",
    pulse: false,
  },
  error: {
    label: "Action needed",
    chip: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-900",
    dot: "bg-rose-500",
    pulse: false,
  },
}

type Comparison = {
  dimension: string
  silo: string
  unified: string
}

const COMPARISON: Comparison[] = [
  {
    dimension: "Where instrument data lives",
    silo: "On the vendor PC next to the spectrometer · vendor file-format · only the operator can find it",
    unified: "SHA-256-hashed in the central immutable vault · vendor-vendor canonical access · auditable per tenant",
  },
  {
    dimension: "ELN ↔ result handoff",
    silo: "Manual copy of the spectrum image into the experiment + a PDF of the interpretation",
    unified: "Structured spectrum reference + interpretation + audit ID attached to the ELN experiment automatically",
  },
  {
    dimension: "Sample / batch IDs",
    silo: "Different IDs in LIMS, ELN, lab notebook, and analyst's spreadsheet · reconciliation by hand",
    unified: "Single canonical lineage · external_object_link table maps every system's ID to the same MolTrace context",
  },
  {
    dimension: "Identity + access",
    silo: "Local accounts per tool · shared logins · audit attribution to 'admin'",
    unified: "SSO via Okta / Azure AD / Google · SCIM-synced groups · every audit event carries a real human identity",
  },
  {
    dimension: "Regulatory data freshness",
    silo: "Whoever last subscribed to USP-NF emails the office when monographs change",
    unified: "Versioned diff feed · affected dossiers + samples auto-routed when standards change",
  },
  {
    dimension: "Inspection-readiness across systems",
    silo: "Two-week reconciliation project per inspection · multiple tools, multiple owners, multiple ledgers",
    unified: "Single connector_event ledger · provenance links resolve cross-system in one click",
  },
]

type LoopStep = {
  step: string
  body: string
}

const CROSS_MODULE_LOOP: LoopStep[] = [
  {
    step: "Instrument watch-folder ingests",
    body: "Bruker TopSpin drops an acquisition into the watched folder. nmrglue normalizes the FID; SHA-256 lands in the immutable vault; SpectraCheck session starts.",
  },
  {
    step: "ELN binding picks up the context",
    body: "Benchling experiment ID matches the acquisition's sample registry tag. Experiment metadata auto-binds. Result: spectrum + protocol + sample are one row.",
  },
  {
    step: "Regulatory feed informs the verdict",
    body: "USP-NF monograph for this drug substance is v2024.2 (pinned to today). Q3C residual-solvent thresholds applied automatically.",
  },
  {
    step: "Outbound sync pushes the result",
    body: "Signed webhook fires to the LIMS with sample ID, verdict, audit-event link. eCTD submission package re-bundled on next dossier export.",
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
    title: "Credentials never plaintext",
    body: "Every secret lives in a vault reference. connector_credential_reference rows carry the rotation date, the scope, the next-rotation deadline — never the secret itself.",
  },
  {
    icon: BadgeCheck,
    title: "Signed webhooks · HMAC verified",
    body: "Outbound webhooks are HMAC-SHA-256 signed with per-subscription secrets. Receivers reject unsigned payloads. Replay attacks blocked by timestamp + nonce.",
  },
  {
    icon: Network,
    title: "mTLS + IP allowlists where it matters",
    body: "Instrument vendors that support it get mutual-TLS. LIMS / ELN endpoints get IP allowlists. PrivateLink / VPC peering available for AWS / Azure / GCP tenants.",
  },
  {
    icon: GitBranch,
    title: "Schema versioning on every mapping",
    body: "MappingTemplate rows are versioned. Activating a new version requires an admin signoff + audit-event entry. Old versions stay queryable for inspection.",
  },
  {
    icon: AlertCircle,
    title: "Failure modes are observable, not invisible",
    body: "Connector health checks run continuously. Errors surface in the live roster with the exact next action. Silent failure is impossible — we don't ship that.",
  },
  {
    icon: Database,
    title: "Tenant isolation extends to integrations",
    body: "Every connector_event is tenant-scoped. Cross-tenant data exchange requires explicit per-event provisioning. SOC 2 Type II controls apply end-to-end.",
  },
]

export function IntegrationsPage() {
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
                    className="border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300"
                  >
                    <Plug className="mr-1 h-3 w-3" aria-hidden />
                    Module · Integrations
                  </Badge>
                  <Badge variant="outline" className="text-muted-foreground">
                    Bruker · Agilent · LIMS · ELN · SSO
                  </Badge>
                </div>
                <h1 className="mt-5 max-w-3xl text-4xl font-semibold leading-[1.05] tracking-tight sm:text-5xl lg:text-6xl">
                  Your existing stack —{" "}
                  <span style={{ color: "var(--mt-teal)" }}>spoken natively</span>, end to end.
                </h1>
                <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted-foreground sm:text-xl">
                  Instruments. LIMS. ELN. Identity providers. Pharmacopoeia feeds. MolTrace
                  connects to all of them with typed mappings, signed webhooks, and a single audit
                  ledger that resolves cross-system in one click.
                </p>
                <div className="mt-10 flex flex-wrap items-center gap-4">
                  <Button asChild size="lg" className="gap-2">
                    <Link href="/contact?reason=Integration%20questions">
                      Talk to integrations
                      <ArrowRight className="h-4 w-4" />
                    </Link>
                  </Button>
                  <Button asChild size="lg" variant="outline" className="gap-2">
                    <Link
                      href="https://docs.moltrace.co/guides/integrations/lims/"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Read connector docs
                      <FileText className="h-4 w-4" />
                    </Link>
                  </Button>
                </div>
              </div>

              {/* Hero visual — live connector roster */}
              <aside className="relative overflow-hidden rounded-3xl border bg-card p-6 shadow-sm">
                <div className="flex items-center justify-between">
                  <p
                    className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                    style={{ color: "var(--mt-teal)" }}
                  >
                    Connector roster · live
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
                    7 active
                  </span>
                </div>
                <p className="mt-3 font-mono text-xs text-muted-foreground">
                  tenant · pharmaco · 47 users · 6 connectors healthy
                </p>
                <p className="mt-1 text-sm font-medium">All sources in one ledger</p>

                <div className="mt-6 space-y-1.5">
                  {ROSTER_SAMPLE.map((row) => {
                    const status = STATUS_STYLE[row.status]
                    return (
                      <div
                        key={row.vendor}
                        className="rounded-md border bg-background/80 px-3 py-2"
                      >
                        <div className="flex items-center gap-2">
                          <span
                            className="inline-flex h-5 w-12 shrink-0 items-center justify-center rounded font-mono text-[9px] font-bold tracking-[0.12em]"
                            style={{
                              backgroundColor: "var(--mt-teal-soft)",
                              color: "var(--mt-teal)",
                            }}
                          >
                            {row.category}
                          </span>
                          <span
                            className={`inline-flex items-center gap-1.5 rounded-full border px-1.5 py-0 font-mono text-[8px] font-bold uppercase tracking-[0.14em] ${status.chip}`}
                          >
                            <span
                              className={`h-1 w-1 rounded-full ${status.dot} ${status.pulse ? "animate-pulse" : ""}`}
                              aria-hidden
                            />
                            {status.label}
                          </span>
                          <span className="ml-auto font-mono text-[9px] text-muted-foreground">
                            {row.lastSync}
                          </span>
                        </div>
                        <p className="mt-1 truncate font-mono text-[10px] text-foreground">
                          {row.vendor}
                        </p>
                        <p className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground">
                          {row.detail}
                        </p>
                      </div>
                    )
                  })}
                </div>
                <p className="mt-5 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                  connector_events · one ledger · end-to-end
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
                  Two analytical universes per tenant — until now.
                </h2>
              </div>
              <div className="space-y-5 text-base leading-relaxed text-muted-foreground">
                <p>
                  The dominant analytical software stacks — proprietary processing apps, vendor
                  LIMS, hardware-tied data formats — raise switching costs and silo the data. An
                  R&amp;D group running Bruker NMR and Agilent LC-MS operates two essentially{" "}
                  <strong className="text-foreground">disjoint analytical universes</strong>, each
                  with its own audit conventions.
                </p>
                <p>
                  Closing this gap by hand means analysts maintain a parallel spreadsheet of which
                  Bruker acquisition matches which LIMS sample matches which ELN experiment. Every
                  reconciliation step is a place a regulator can find a discrepancy.
                </p>
                <p className="font-medium text-foreground">
                  MolTrace Integrations replaces that reconciliation with typed mappings, signed
                  events, and a single connector ledger. The two universes become one, queryable
                  surface — without forcing you to abandon the vendor stack you already paid for.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ── Connector lifecycle ─────────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Connector lifecycle
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Seven stages from discovery to audit-replay.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Every stage emits a typed record. Every record is queryable. The same{" "}
                <code className="font-mono text-foreground">connector_event</code> ledger covers
                instrument ingest, LIMS sync, ELN handoff, and regulatory feed updates — one
                schema, one inspection-ready surface.
              </p>
            </div>

            <ol className="mt-12 grid gap-4 lg:grid-cols-3 xl:grid-cols-4">
              {LIFECYCLE.map((s, idx) => (
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
                    {idx < LIFECYCLE.length - 1 ? (
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

        {/* ── Connector matrix ────────────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Connectors shipped
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                Four categories. Every vendor named.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                If a vendor isn't on the list, ask. Generic OAuth / SAML / OIDC + a typed mapping
                template covers most LIMS and ELN systems with a one-day integration. New
                instrument vendors integrate via{" "}
                <code className="font-mono text-foreground">nmrglue</code> or vendor-supplied
                exporters.
              </p>
            </div>
            <div className="mt-12 grid gap-6 lg:grid-cols-2">
              {CONNECTORS.map((cat) => (
                <article
                  key={cat.acronym}
                  className="rounded-2xl border bg-card p-6 shadow-sm sm:p-7"
                  style={{ borderLeft: "3px solid var(--mt-teal)" }}
                >
                  <div className="flex items-baseline gap-4">
                    <span
                      className="font-mono text-3xl font-bold tabular-nums tracking-tight"
                      style={{ color: "var(--mt-teal)" }}
                    >
                      {cat.acronym}
                    </span>
                    <div>
                      <h3 className="text-base font-semibold tracking-tight">{cat.full}</h3>
                      <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                        {cat.scope}
                      </p>
                    </div>
                  </div>
                  <ul className="mt-5 space-y-2">
                    {cat.bullets.map((item) => (
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
                Six integration patterns we ship in production.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Each pattern maps to typed entities in the backend{" "}
                <code className="font-mono text-foreground">interoperability_store</code>. Inputs +
                outputs are real Pydantic shapes — not roadmap items.
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

        {/* ── Integration topology figure ─────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                Topology at a glance
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                MolTrace as a hub. Every line is a typed contract.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Inbound edges carry vendor data into the canonical model. Outbound edges push
                results, dossier sections, and webhook events back to the systems that need them.
                One ledger covers both directions.
              </p>
            </div>

            <div className="mt-12 overflow-hidden rounded-2xl border bg-card">
              <div className="border-b bg-muted/40 px-4 py-2.5">
                <p className="font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
                  Integration topology · simplified
                </p>
              </div>
              <pre className="overflow-x-auto px-4 py-6 font-mono text-[11px] leading-relaxed text-foreground sm:px-8 sm:text-xs">
{`     ┌──────────────────────┐                              ┌──────────────────────┐
     │  Instruments         │  ──── ingest (watch-folder) ──►│                      │
     │  Bruker · Agilent    │                                │                      │
     │  Thermo · Waters     │                                │                      │
     └──────────────────────┘                                │                      │
                                                             │                      │
     ┌──────────────────────┐                                │                      │   ──── webhook ───►  Customer apps
     │  LIMS · ELN          │  ◄──── bidirectional sync ────►│      MolTrace        │
     │  LabWare · Benchling │                                │  ────────────────    │   ──── eCTD ───────►  Regulatory submission
     │  STARLIMS · BIOVIA   │                                │  · connector ledger  │
     └──────────────────────┘                                │  · audit ledger      │   ──── push ───────►  Downstream LIMS
                                                             │  · raw vault         │
     ┌──────────────────────┐                                │  · interoperability  │
     │  Identity · SSO      │  ──── SAML / OIDC / SCIM ─────►│    store             │
     │  Okta · Azure AD     │                                │                      │
     │  Google · Ping       │                                │                      │
     └──────────────────────┘                                │                      │
                                                             │                      │
     ┌──────────────────────┐                                │                      │
     │  Regulatory feeds    │  ──── versioned diffs ────────►│                      │
     │  USP-NF · EP · JP    │                                │                      │
     │  ICH · FDA · EMA     │                                │                      │
     └──────────────────────┘                                └──────────────────────┘`}
              </pre>
            </div>
          </div>
        </section>

        {/* ── Siloed vs unified comparison ────────────────────────────────── */}
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
                What changes when the systems share one ledger.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Most R&amp;D groups have all the tools. They just don't share a vocabulary. Here's
                what flips when MolTrace becomes the connective tissue.
              </p>
            </div>
            <div className="mt-12 overflow-hidden rounded-2xl border bg-card shadow-sm">
              <table className="w-full text-left text-sm">
                <thead className="bg-muted/40 font-mono uppercase tracking-[0.12em] text-[10px] text-muted-foreground">
                  <tr>
                    <th className="px-5 py-3">Dimension</th>
                    <th className="px-5 py-3">Siloed toolchain</th>
                    <th className="px-5 py-3">Unified via MolTrace</th>
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
                        <p>{row.silo}</p>
                      </td>
                      <td className="px-5 py-3.5 align-top text-xs leading-relaxed text-foreground">
                        <span className="mb-1 inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300">
                          <CheckCircle2 className="h-2.5 w-2.5" aria-hidden />
                          unified
                        </span>
                        <p>{row.unified}</p>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* ── Cross-module loop ───────────────────────────────────────────── */}
        <section className="border-b">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="max-w-3xl">
              <p
                className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                style={{ color: "var(--mt-teal)" }}
              >
                What integrations make possible
              </p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                The full three-pillar loop, end to end.
              </h2>
              <p className="mt-4 text-base text-muted-foreground">
                Integrations is what connects the dots. Spectroscopy, ComplianceCore, and
                ReactionIQ deliver value individually — together, through connectors, they're a
                closed evidence loop that survives inspection and outlasts personnel.
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
                      Receives every instrument acquisition that arrives through a connector.
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
                    <p className="text-sm font-semibold">ComplianceCore →</p>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      Consumes regulatory-feed diffs; emits eCTD submission packages outbound.
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
                      Pushes campaign recommendations into ELN experiments via outbound sync.
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

        {/* ── Trust & security ────────────────────────────────────────────── */}
        <section className="border-b bg-muted/20">
          <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
            <div className="grid gap-10 lg:grid-cols-[1fr_1.6fr]">
              <div>
                <p
                  className="font-mono text-[10px] font-bold uppercase tracking-[0.22em]"
                  style={{ color: "var(--mt-teal)" }}
                >
                  Security & data integrity
                </p>
                <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
                  Integrations is the attack surface. We treat it that way.
                </h2>
                <p className="mt-4 text-base text-muted-foreground">
                  Every connector is zero-trust by default. Credentials are vault-referenced,
                  webhooks are HMAC-signed, mapping templates are versioned, and silent failures
                  are impossible.
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
                Tell us your stack.
              </h2>
              <p className="mt-4 text-base text-muted-foreground sm:text-lg">
                Bruker + LabWare + Benchling + Okta? Done. Something more exotic? Generic OAuth +
                a typed mapping template usually gets us to a one-day integration. Send us your
                inventory and we'll come back with the plan.
              </p>
              <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
                <Button asChild size="lg" className="gap-2">
                  <Link href="/contact?reason=Integration%20inventory">
                    Send your stack
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="outline" className="gap-2">
                  <Link
                    href="https://docs.moltrace.co/guides/integrations/lims/"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    LIMS integration docs
                    <FileText className="h-4 w-4" />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="ghost" className="gap-2">
                  <Link href="/about">
                    Back to platform overview
                    <Layers className="h-4 w-4" />
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
