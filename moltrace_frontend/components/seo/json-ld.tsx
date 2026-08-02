import { SITE_URL, SITE_NAME, SITE_DESCRIPTION } from "@/lib/seo/site"

/**
 * Structured data (schema.org / JSON-LD) for the site root. Rendered once in the
 * root layout so it appears on every page. Three graph nodes:
 *
 *  - Organization  → powers the Google knowledge panel / brand entity
 *  - WebSite       → declares the canonical site + name for sitelinks
 *  - SoftwareApplication → the product itself, eligible for rich results
 *
 * Emitted as a server component with a raw <script type="application/ld+json">.
 * The content is a static, developer-authored constant (no user input), so
 * dangerouslySetInnerHTML is safe here.
 */
export function OrganizationJsonLd() {
  const graph = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": `${SITE_URL}/#organization`,
        name: SITE_NAME,
        url: SITE_URL,
        logo: {
          "@type": "ImageObject",
          url: `${SITE_URL}/icons/icon-512.png`,
          width: 512,
          height: 512,
        },
        description: SITE_DESCRIPTION,
        // Keep in sync with the claimed entries in `socialLinks`
        // (components/marketing/footer.tsx). `sameAs` is what ties this domain,
        // the repo, and the social profiles into a single brand entity — which
        // matters here because the bare term "MolTrace" collides with unrelated
        // content in search results.
        sameAs: [
          "https://github.com/MolTrace/MolTrace",
          "https://www.linkedin.com/company/moltrace/",
          "https://x.com/moltrace_co",
        ],
      },
      {
        "@type": "WebSite",
        "@id": `${SITE_URL}/#website`,
        url: SITE_URL,
        name: SITE_NAME,
        description: SITE_DESCRIPTION,
        publisher: { "@id": `${SITE_URL}/#organization` },
        inLanguage: "en-US",
      },
      {
        "@type": "SoftwareApplication",
        "@id": `${SITE_URL}/#software`,
        name: SITE_NAME,
        applicationCategory: "BusinessApplication",
        applicationSubCategory: "Scientific Intelligence Platform",
        operatingSystem: "Web",
        url: SITE_URL,
        description: SITE_DESCRIPTION,
        publisher: { "@id": `${SITE_URL}/#organization` },
        offers: {
          "@type": "Offer",
          category: "SaaS",
        },
      },
    ],
  }

  return (
    <script
      type="application/ld+json"
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{ __html: JSON.stringify(graph) }}
    />
  )
}
