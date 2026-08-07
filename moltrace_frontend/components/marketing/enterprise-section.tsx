import { FileCheck, KeyRound, Lock, PackageCheck, ShieldCheck, Users } from "lucide-react"
import { AccentCard } from "./accent-card"

const CYAN = { accent: "var(--mt-cyan)", ink: "var(--mt-cyan-ink)", soft: "var(--mt-cyan-soft)" }

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
  },
  {
    // "Customer-managed keys available for enterprise deployments" came out:
    // there is no CMEK or customer-key wiring anywhere in the repo. The Cloud KMS
    // key named in the README is MolTrace's own field-encryption key.
    icon: Lock,
    title: "No public database interface",
    pill: "Encryption",
    desc: "PostgreSQL runs on a private IP with no public interface, reached over Direct VPC egress. Credentials come from Secret Manager, and field encryption uses Cloud KMS.",
  },
  {
    icon: KeyRound,
    title: "MFA, passkeys and step-up",
    pill: "Identity",
    desc: "TOTP and WebAuthn passkeys, with step-up re-authentication before sensitive actions. Enterprise SSO over OIDC, with SCIM provisioning.",
  },
  {
    icon: ShieldCheck,
    title: "Designed for SOC 2 Type II",
    pill: "Compliance",
    desc: "Access control, audit trail, secret scanning and dependency scanning run as controls in the pipeline — the evidence a Type II audit samples.",
  },
  {
    icon: PackageCheck,
    title: "Verified supply chain",
    pill: "Provenance",
    desc: "Each release carries a software bill of materials and signed build provenance, and the deploy is blocked unless both verify.",
  },
]

export function EnterpriseSection() {
  return (
    <section className="border-t py-24" id="enterprise">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">

        {/* Section header */}
        <div className="mb-16 text-center">
          <p className="mb-4 text-xs font-bold uppercase tracking-[0.2em] text-cyan-500 dark:text-cyan-400">
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

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => (
            <AccentCard key={f.title} {...f} {...CYAN} />
          ))}
        </div>

      </div>
    </section>
  )
}
