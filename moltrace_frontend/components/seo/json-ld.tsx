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
        // Declares the spellings the brand is written as, so a lowercase-t or
        // spaced rendering resolves to this entity rather than to something
        // else. Verified 2026-08-02: Google renders the brand as "Moltrace" and
        // offers "Did you mean: moltres" on the brand query, so the collision is
        // live rather than hypothetical.
        //
        // Every entry must be a name the brand is ACTUALLY known by — a
        // spelling variant, or the registered legal form. Descriptive phrases
        // ("MolTrace Intelligence", "MolTrace ai") are deliberately excluded:
        // they are not names anyone uses, the domain is .co rather than .ai,
        // and padding this list with keyword variants both dilutes the real
        // signals and asserts an identity the company does not hold.
        //
        // "MolTrace Technologies, Inc." is the registered entity, as carried in
        // the footer copyright line.
        alternateName: [
          "Moltrace",
          "Mol Trace",
          "MolTrace platform",
          "MolTrace Technologies",
          "MolTrace Technologies, Inc.",
        ],
        url: SITE_URL,
        logo: {
          "@type": "ImageObject",
          url: `${SITE_URL}/icons/icon-512.png`,
          width: 512,
          height: 512,
        },
        description: SITE_DESCRIPTION,
        // Mirrors the claimed entries in `socialLinks`
        // (components/marketing/footer.tsx). `sameAs` is what ties this domain,
        // the repo, and the social profiles into a single brand entity — which
        // matters here because the bare term "MolTrace" collides with unrelated
        // content in search results.
        //
        // These MUST be the clean canonical profile URLs — no query strings.
        // The footer's LinkedIn href carries `?viewAsMember=true` (a UI fix so
        // page admins aren't bounced to the admin dashboard); that parameter
        // must NOT leak in here, because an entity URL that doesn't match the
        // profile's own canonical is a weaker match for the knowledge graph.
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
