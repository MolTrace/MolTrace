import { render } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { HeroMoleculeLayer } from "@/components/marketing/hero-molecule-layer"

function installMatchMedia(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
}

describe("HeroMoleculeLayer", () => {
  it("uses a static hero backdrop on mobile or reduced motion", () => {
    installMatchMedia(false)

    const { container } = render(<HeroMoleculeLayer />)

    expect(container.querySelector("canvas")).not.toBeInTheDocument()
    expect(container.firstElementChild).toHaveAttribute("aria-hidden", "true")
  })

  it("activates the animated canvas path on desktop with no reduced motion", () => {
    installMatchMedia(true)

    const { container } = render(<HeroMoleculeLayer />)

    // Layer routes to the dynamic <HeroMoleculeBackground />; loading state
    // is null in jsdom (no SSR, chunk not yet resolved). The key regression
    // signal is that the static fallback div is *not* rendered here.
    expect(container.querySelector('[aria-hidden="true"]')).toBeNull()
  })
})
