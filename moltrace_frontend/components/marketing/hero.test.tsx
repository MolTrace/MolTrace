import { render } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

// HeroMoleculeLayer reads window.matchMedia in a client effect; stub a
// reduced-motion match so the static fallback path renders synchronously
// and we can assert on the markup without booting a WebGL canvas.
vi.mock("@/components/marketing/hero-molecule-layer", () => ({
  HeroMoleculeLayer: () => <div data-testid="hero-molecule-layer" />,
}))

import { Hero } from "@/components/marketing/hero"

describe("Hero", () => {
  it("does not render the scientific gridline overlay", () => {
    const { container } = render(<Hero />)
    expect(container.querySelector(".scientific-grid-subtle")).toBeNull()
    expect(container.querySelector(".scientific-grid")).toBeNull()
  })

  it("still mounts the molecule layer behind the hero copy", () => {
    const { getByTestId } = render(<Hero />)
    expect(getByTestId("hero-molecule-layer")).toBeInTheDocument()
  })
})
