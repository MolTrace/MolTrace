import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Shield, Users, Lock, Server, FileCheck, Globe } from "lucide-react"

const features = [
  {
    icon: Users,
    title: "Role-Based Access Control",
    description: "Granular permissions for analysts, reviewers, and administrators with project-level isolation.",
  },
  {
    icon: FileCheck,
    title: "Complete Audit Logs",
    description: "Every action timestamped and attributed. Export audit packages for regulatory inspection.",
  },
  {
    icon: Lock,
    title: "End-to-End Encryption",
    description: "Data encrypted at rest and in transit. Customer-managed keys available for enterprise.",
  },
  {
    icon: Server,
    title: "Flexible Deployment",
    description: "Cloud-hosted SaaS, VPC deployment, or on-premises installation for air-gapped environments.",
  },
  {
    icon: Shield,
    title: "SOC 2 Type II Certified",
    description: "Annual third-party audits verify our security controls meet enterprise requirements.",
  },
  {
    icon: Globe,
    title: "Data Residency Options",
    description: "Choose data storage regions to comply with local data sovereignty requirements.",
  },
]

export function EnterpriseSection() {
  return (
    <section className="py-24" id="enterprise">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="text-center">
          <h2 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            Enterprise-grade security and compliance
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-muted-foreground">
            Built for regulated industries. Your data stays yours, with the controls 
            and audit trails required for GxP environments.
          </p>
        </div>
        <div className="mt-16 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((feature) => (
            <Card key={feature.title} className="border-0 bg-muted/30 shadow-none">
              <CardHeader className="pb-2">
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-secondary">
                  <feature.icon className="h-5 w-5" />
                </div>
                <CardTitle className="text-base">{feature.title}</CardTitle>
              </CardHeader>
              <CardContent>
                <CardDescription className="text-sm">{feature.description}</CardDescription>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  )
}
