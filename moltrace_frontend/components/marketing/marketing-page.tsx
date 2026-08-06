import { CTASection } from "@/components/marketing/cta-section"
import { FaqSection } from "@/components/marketing/faq-section"
import { FaqJsonLd } from "@/components/seo/structured-data"
import { HOME_FAQS } from "@/lib/seo/modules"
import { EnterpriseSection } from "@/components/marketing/enterprise-section"
import { EvidenceSection } from "@/components/marketing/evidence-section"
import { Footer } from "@/components/marketing/footer"
import { Header } from "@/components/marketing/header"
import { Hero } from "@/components/marketing/hero"
import { ModuleCards } from "@/components/marketing/module-cards"

/**
 * The home page, cut from nine sections to six.
 *
 * What came off, and why — each was a repeat, not a cut for its own sake:
 *
 *   TrustBar          The hero already ends on the compliance line; this
 *                     restated the same five standards immediately below it.
 *                     The badge row now appears once, in the Footer, and
 *                     Enterprise states the same standards in prose — see the
 *                     note below, that pairing is still one repeat too many.
 *
 *   WorkflowStrip     Told the same four-beat story as the hero's module row —
 *                     and called two of the products "Regulatory Hub" and
 *                     "Optimization", names they no longer go by. The hero row
 *                     carries it now, in each product's own colour.
 *
 *   DashboardPreview  Four figures, every one captioned "SAMPLE DATA". A
 *                     section that asks to be believed while labelling itself
 *                     illustrative argues against the page. It should come back
 *                     when the numbers are real.
 *
 * The components are all still on disk and still exported — this is a change of
 * composition, so putting any of them back is a one-line edit.
 */
export function MarketingPage() {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main>
        <Hero />
        <ModuleCards />
        <EvidenceSection />
        <EnterpriseSection />
        <FaqSection items={HOME_FAQS} title="Frequently asked questions about MolTrace" />
        <CTASection />
      </main>
      <FaqJsonLd path="/" faqs={HOME_FAQS} />
      <Footer />
    </div>
  )
}
