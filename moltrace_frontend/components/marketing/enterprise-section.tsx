// The deck is interactive, and `features` hands it Lucide components — which are
// functions, and functions cannot cross the server/client boundary ("Functions
// cannot be passed directly to Client Components"). Marking the section itself
// keeps the icons on one side of the line. The alternative, passing pre-rendered
// icon elements from the server, buys nothing here: everything below is static
// strings that Next still server-renders into the HTML.
"use client"

import { FileCheck, KeyRound, Lock, PackageCheck, ShieldCheck, Users } from "lucide-react"
import { StackedDeck } from "./stacked-deck"

/**
 * One brand family per control, so the deck reads as six distinct things rather
 * than six shades of the same thing.
 *
 * The colours are not decoration — moving through the deck re-tints the stage
 * behind it, so the hue is how you tell at a glance that the card changed. They
 * are assigned by subject, not cycled: access takes violet and the audit trail
 * cyan, the database boundary teal, identity amber, and the two attestation
 * controls green and slate. (An earlier version of this comment described a
 * different pairing than the code below actually ships — caught in review;
 * the list here is the mapping, read it against `features`.)
 *
 * Every family resolves through its `-ink` token for type. The vivid tokens sit
 * at 2-3:1 on the light card and fail AA as text; green-ink and slate-ink were
 * added for this and measure 5.02:1 and 7.58:1 light, 8.63:1 and 7.67:1 dark.
 */
const family = (name: string) => ({
  accent: `var(--mt-${name})`,
  ink: `var(--mt-${name}-ink)`,
  soft: `var(--mt-${name}-soft)`,
})

/**
 * Enterprise controls, each traced to the code or the pipeline that implements
 * it. Every sentence here should survive a buyer's security questionnaire.
 *
 * TWO CARDS WERE REMOVED because nothing implements them:
 *
 *   "Flexible Deployment — Cloud SaaS, VPC deployment, or on-premises
 *   installation for air-gapped environments."
 *     Only Cloud SaaS exists. The VPC in production is MolTrace's own Direct VPC
 *     egress to Cloud SQL, not a deployment into a customer's VPC, and the only
 *     compose file in the repo is `deploy/docker-compose.dev.yml` — a local dev
 *     convenience, not an offered on-prem installation.
 *
 *   "Data Residency — Choose storage regions designed to support data residency
 *   requirements."
 *     `TenantDataBoundaryORM` stores `allowed_regions_json` and
 *     `data_residency_notes`, but nothing reads them to route or restrict
 *     storage — they are written and read back, on a row whose `status` defaults
 *     to "draft". Production is single-region us-central1 with no customer
 *     choice. "Choose storage regions" is not something a customer can do.
 *
 * If either ships for real, add the card back with the code that implements it.
 * Do not restore them from this comment.
 */
const features = [
  {
    // Was "Granular permissions for analysts, reviewers, and administrators."
    // The real matrix is better than the generic claim, so it is named:
    // _ROLE_ACTIONS in nmrcheck/collaboration_store.py.
    icon: Users,
    title: "Roles that gate actions",
    pill: "Access",
    desc: "Five roles across eight actions, resolved per project and per team. A reviewer can approve but cannot upload a run; a scientist can upload but cannot approve.",
    ...family("violet"),
  },
  {
    // "HMAC-chained" was wrong, and the truth is the better claim. Per-entry
    // linkage is unkeyed SHA-256 (`compute_entry_hash` in audit_chain.py returns
    // "sha256:"), so the chain re-walks with no secret; HMAC is used only to sign
    // the periodic anchor. Saying HMAC implied a key is needed to check the trail,
    // which would have undercut the point of having one.
    icon: FileCheck,
    title: "Tamper-evident audit trail",
    pill: "Audit",
    desc: "Analyses, reviews and approvals are hash-chained with SHA-256 and server-timestamped, so the trail re-verifies without a secret and exports as an inspection package.",
    ...family("cyan"),
  },
  {
    // "Customer-managed keys available for enterprise deployments" came out:
    // there is no CMEK or customer-key wiring anywhere in the repo. The Cloud KMS
    // key named in the README is MolTrace's own field-encryption key.
    icon: Lock,
    title: "No public database interface",
    pill: "Encryption",
    desc: "PostgreSQL runs on a private IP with no public interface, reached over Direct VPC egress. Credentials come from Secret Manager, and field encryption uses Cloud KMS.",
    ...family("teal"),
  },
  {
    icon: KeyRound,
    title: "MFA, passkeys and step-up",
    pill: "Identity",
    desc: "TOTP and WebAuthn passkeys, with step-up re-authentication before sensitive actions. Enterprise SSO over OIDC, with SCIM provisioning.",
    ...family("amber"),
  },
  {
    icon: ShieldCheck,
    title: "Designed to support SOC 2 Type II",
    pill: "Compliance",
    desc: "Access control, audit trail, secret scanning and dependency scanning run as controls in the pipeline — the evidence a Type II audit samples.",
    ...family("green"),
  },
  {
    icon: PackageCheck,
    title: "Verified supply chain",
    pill: "Provenance",
    desc: "Each release carries a software bill of materials and signed build provenance, and the deploy is blocked unless both verify.",
    ...family("slate"),
  },
]

export function EnterpriseSection() {
  return (
    <section className="border-t py-24" id="enterprise">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">

        {/* Section header */}
        <div className="mb-16 text-center">
          {/* cyan-INK, not the vivid token: raw text-cyan-500 measures ~2.4:1
              on the light page — the exact failure the -ink variants exist for,
              and the same pattern the evidence section's eyebrow already uses. */}
          <p className="mb-4 text-xs font-bold uppercase tracking-[0.2em]" style={{ color: "var(--mt-cyan-ink)" }}>
            Enterprise
          </p>
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            Security and compliance controls designed for regulated industries.
          </h2>
          <p className="mx-auto mt-4 max-w-lg text-base leading-relaxed text-muted-foreground">
            {/* "Built for regulated industries." was here and is now gone: the h2
                directly above already ends on "designed for regulated
                industries", so the page said it twice, two lines apart. */}
            Your data stays yours, with the controls and audit trails required for
            GxP environments.
          </p>
        </div>

        {/* A deck rather than the 3x2 grid this replaces. Six cards laid out flat
            gave every control the same weight, so the section had no subject and
            a reader's eye had nowhere to start. The grid is still the right
            answer wherever items are meant to be compared — it is wrong here,
            where these are six independent assurances read one at a time. */}
        <StackedDeck items={features} label="Enterprise controls" />

      </div>
    </section>
  )
}
