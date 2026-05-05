import { CTASection } from "@/components/marketing/cta-section"
import { DashboardPreview } from "@/components/marketing/dashboard-preview"
import { EnterpriseSection } from "@/components/marketing/enterprise-section"
import { EvidenceSection } from "@/components/marketing/evidence-section"
import { Footer } from "@/components/marketing/footer"
import { Header } from "@/components/marketing/header"
import { Hero } from "@/components/marketing/hero"
import { ModuleCards } from "@/components/marketing/module-cards"
import { WorkflowStrip } from "@/components/marketing/workflow-strip"

export function MarketingPage() {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main>
        <Hero />
        <ModuleCards />
        <WorkflowStrip />
        <EvidenceSection />
        <EnterpriseSection />
        <DashboardPreview />
        <CTASection />
      </main>
      <Footer />
    </div>
  )
}
