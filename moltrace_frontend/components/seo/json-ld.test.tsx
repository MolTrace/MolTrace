import { describe, expect, it } from "vitest"
import { render } from "@testing-library/react"

import { OrganizationJsonLd } from "@/components/seo/json-ld"
import { socialLinks } from "@/components/marketing/footer"

/** Pull the parsed JSON-LD @graph out of the rendered <script> tag. */
function renderGraph() {
  const { container } = render(<OrganizationJsonLd />)
  const script = container.querySelector('script[type="application/ld+json"]')
  expect(script, "json-ld script tag").not.toBeNull()
  const parsed = JSON.parse(script!.textContent ?? "{}")
  return parsed["@graph"] as Array<Record<string, unknown>>
}

describe("Organization JSON-LD", () => {
  it("emits a valid Organization / WebSite / SoftwareApplication graph", () => {
    const graph = renderGraph()
    const types = graph.map((node) => node["@type"])
    expect(types).toEqual(
      expect.arrayContaining(["Organization", "WebSite", "SoftwareApplication"]),
    )
  })

  it("lists every claimed social profile in sameAs", () => {
    const graph = renderGraph()
    const org = graph.find((n) => n["@type"] === "Organization")!
    const sameAs = org.sameAs as string[]

    // Every profile rendered in the footer must also be declared as a sameAs
    // entity URL — that pairing is what identifies the brand to search engines.
    const claimedHosts = socialLinks
      .filter((l) => typeof l.href === "string")
      .map((l) => new URL(l.href as string).host)
    for (const host of claimedHosts) {
      expect(
        sameAs.some((url) => new URL(url).host === host),
        `sameAs is missing a profile on ${host}`,
      ).toBe(true)
    }
  })

  it("keeps sameAs entries as clean canonical URLs with no query string", () => {
    const graph = renderGraph()
    const org = graph.find((n) => n["@type"] === "Organization")!
    for (const url of org.sameAs as string[]) {
      const parsed = new URL(url)
      // The footer's LinkedIn link carries ?viewAsMember=true so page admins
      // aren't redirected to the admin dashboard. That UI-only parameter must
      // never leak into the entity graph — sameAs has to match the profile's
      // own canonical URL to be a strong identity signal.
      expect(parsed.search, `${url} should have no query string`).toBe("")
      expect(parsed.hash, `${url} should have no fragment`).toBe("")
      expect(parsed.protocol).toBe("https:")
    }
  })
})
