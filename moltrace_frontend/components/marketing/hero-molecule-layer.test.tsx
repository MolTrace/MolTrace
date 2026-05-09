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
})
