import { Shield, Users, Lock, Server, FileCheck, Globe } from "lucide-react"

const features = [
  {
    icon: Users,
    title: "Role-Based Access",
    desc: "Granular permissions for analysts, reviewers, and administrators with project-level isolation.",
  },
  {
    icon: FileCheck,
    title: "Complete Audit Logs",
    desc: "Every action timestamped and attributed. Export audit packages for regulatory inspection.",
  },
  {
    icon: Lock,
    title: "End-to-End Encryption",
    desc: "Designed to encrypt data at rest (AES-256) and in transit. Customer-managed keys available for enterprise deployments.",
  },
  {
    icon: Server,
    title: "Flexible Deployment",
    desc: "Cloud SaaS, VPC deployment, or on-premises installation for air-gapped environments.",
  },
  {
    icon: Shield,
    title: "Designed for SOC 2 Type II",
    desc: "Security controls designed to support a SOC 2 Type II audit and enterprise requirements.",
  },
  {
    icon: Globe,
    title: "Data Residency",
    desc: "Choose storage regions designed to support data residency requirements.",
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
            Built for regulated industries. Your data stays yours, with the controls
            and audit trails required for GxP environments.
          </p>
        </div>

        {/* Divided grid — gap-px + bg-border creates hairline dividers between cells */}
        <div className="grid grid-cols-1 gap-px overflow-hidden rounded-xl bg-border sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => (
            <div key={f.title} className="flex flex-col bg-card p-7">
              <div className="mb-5 flex h-10 w-10 items-center justify-center rounded-lg border border-cyan-500/30 bg-cyan-500/10">
                <f.icon
                  className="h-[18px] w-[18px] text-cyan-500 dark:text-cyan-400"
                  strokeWidth={1.8}
                />
              </div>
              <div className="mb-2 text-sm font-bold text-foreground">{f.title}</div>
              <div className="text-sm leading-relaxed text-muted-foreground">{f.desc}</div>
            </div>
          ))}
        </div>

      </div>
    </section>
  )
}
