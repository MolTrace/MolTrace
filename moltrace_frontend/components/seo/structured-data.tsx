import { SITE_URL, SITE_NAME } from "@/lib/seo/site"

export type FaqItem = { q: string; a: string }

/**
 * Per-module structured data. Emits one JSON-LD @graph with:
 *  - SoftwareApplication  → the module as a product, linked (`isPartOf`) to the
 *    site-level SoftwareApplication + published by the Organization declared in
 *    the root layout (cross-page @id references form one entity graph).
 *  - BreadcrumbList       → Home › Module, so crawlers understand site structure.
 *  - FAQPage (optional)   → machine-readable Q&A for answer-engine extraction.
 *
 * Content is a static, developer-authored constant (grounded copy, no user
 * input) so dangerouslySetInnerHTML is safe.
 */
export function ModuleJsonLd({
  name,
  path,
  description,
  applicationCategory,
  faqs,
}: {
  name: string
  path: string
  description: string
  applicationCategory: string
  faqs?: FaqItem[]
}) {
  const url = `${SITE_URL}${path}`
  const graph: Record<string, unknown>[] = [
    {
      "@type": "SoftwareApplication",
      "@id": `${url}#software`,
      name,
      applicationCategory,
      operatingSystem: "Web",
      url,
      description,
      isPartOf: { "@id": `${SITE_URL}/#software` },
      publisher: { "@id": `${SITE_URL}/#organization` },
      offers: { "@type": "Offer", category: "SaaS" },
    },
    {
      "@type": "BreadcrumbList",
      "@id": `${url}#breadcrumb`,
      itemListElement: [
        { "@type": "ListItem", position: 1, name: "Home", item: SITE_URL },
        { "@type": "ListItem", position: 2, name, item: url },
      ],
    },
  ]

  if (faqs?.length) {
    graph.push({
      "@type": "FAQPage",
      "@id": `${url}#faq`,
      mainEntity: faqs.map((f) => ({
        "@type": "Question",
        name: f.q,
        acceptedAnswer: { "@type": "Answer", text: f.a },
      })),
    })
  }

  return (
    <script
      type="application/ld+json"
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{
        __html: JSON.stringify({ "@context": "https://schema.org", "@graph": graph }),
      }}
    />
  )
}

/** Standalone FAQPage JSON-LD (for surfaces like the home page that already
 *  emit their own Organization/WebSite graph in the root layout). */
export function FaqJsonLd({ path, faqs }: { path: string; faqs: FaqItem[] }) {
  if (!faqs?.length) return null
  const url = `${SITE_URL}${path === "/" ? "" : path}`
  return (
    <script
      type="application/ld+json"
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{
        __html: JSON.stringify({
          "@context": "https://schema.org",
          "@type": "FAQPage",
          "@id": `${url}/#faq`,
          name: `${SITE_NAME} — FAQ`,
          mainEntity: faqs.map((f) => ({
            "@type": "Question",
            name: f.q,
            acceptedAnswer: { "@type": "Answer", text: f.a },
          })),
        }),
      }}
    />
  )
}
