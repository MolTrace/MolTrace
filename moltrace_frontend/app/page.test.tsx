import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import HomePage from "@/app/page"

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ push: vi.fn() }),
}))

describe("home page", () => {
  it("renders the MolTrace marketing landing page", () => {
    render(<HomePage />)
    expect(
      screen.getByRole("heading", {
        name: /Analytical evidence you can trace under audit/i,
      }),
    ).toBeInTheDocument()
    expect(screen.getAllByText("Request Demo")[0]).toBeInTheDocument()
  })

  // THE CRAWL PATH. The tabs and "Explore Module" in the platform section are
  // buttons — correctly, since they switch and toggle rather than navigate —
  // and the overlay's launch links point at the app, which robots.txt
  // disallows. So the module marketing pages depend on ordinary <a href>s
  // rendering with no interaction at all, because a crawler never clicks.
  //
  // Asserted at the PAGE level on purpose. This used to be tested inside
  // module-cards, which pinned one component's implementation rather than the
  // thing that matters; when those links were removed as clutter the guarantee
  // survived intact via the footer and the header dropdown, and a
  // component-level test would have failed for a page that was still correct.
  it.each([
    ["SpectraCheck", "/spectroscopy"],
    ["Regentry", "/regulatory-hub"],
    ["Repho", "/reaction-optimization"],
  ])("links to the %s module page with no interaction", (name, href) => {
    const { container } = render(<HomePage />)
    const links = container.querySelectorAll(`a[href="${href}"]`)
    expect(links.length, `no crawlable link to ${name} (${href}) on the homepage`).toBeGreaterThan(0)
  })
})
