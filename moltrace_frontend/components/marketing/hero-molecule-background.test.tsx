import { act, render } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// Stub @react-three/fiber + drei so the component mounts in jsdom (no WebGL).
// We expose `frameloop` as a data attribute so the test can read it back.
vi.mock("@react-three/fiber", () => ({
  Canvas: ({ frameloop }: { frameloop?: string }) => (
    <div data-testid="r3f-canvas" data-frameloop={frameloop ?? "always"} />
  ),
  useFrame: vi.fn(),
}))

vi.mock("@react-three/drei", () => ({
  Environment: () => null,
}))

import { HeroMoleculeBackground } from "@/components/marketing/hero-molecule-background"

type Captured = {
  callback: IntersectionObserverCallback
  observe: ReturnType<typeof vi.fn>
  disconnect: ReturnType<typeof vi.fn>
  unobserve: ReturnType<typeof vi.fn>
}

let observers: Captured[] = []
const originalIO = globalThis.IntersectionObserver

beforeEach(() => {
  observers = []
  class MockIntersectionObserver {
    callback: IntersectionObserverCallback
    observe = vi.fn()
    disconnect = vi.fn()
    unobserve = vi.fn()
    takeRecords = () => []
    root: Element | null = null
    rootMargin = ""
    thresholds: ReadonlyArray<number> = []
    constructor(cb: IntersectionObserverCallback) {
      this.callback = cb
      observers.push({
        callback: cb,
        observe: this.observe,
        disconnect: this.disconnect,
        unobserve: this.unobserve,
      })
    }
  }
  globalThis.IntersectionObserver =
    MockIntersectionObserver as unknown as typeof IntersectionObserver
})

afterEach(() => {
  globalThis.IntersectionObserver = originalIO
})

function fireIntersection(idx: number, isIntersecting: boolean) {
  act(() => {
    observers[idx].callback(
      [{ isIntersecting } as IntersectionObserverEntry],
      // Real IO instances pass themselves as the second arg; the component
      // doesn't read it, so a minimal cast keeps the test focused.
      {} as IntersectionObserver,
    )
  })
}

describe("HeroMoleculeBackground", () => {
  it("starts with frameloop=always so the first paint is not blocked by IO timing", () => {
    const { getByTestId } = render(<HeroMoleculeBackground />)
    expect(getByTestId("r3f-canvas")).toHaveAttribute("data-frameloop", "always")
  })

  it("observes the wrapper element on mount", () => {
    render(<HeroMoleculeBackground />)
    expect(observers).toHaveLength(1)
    expect(observers[0].observe).toHaveBeenCalledOnce()
  })

  it("switches frameloop to 'never' when the wrapper scrolls out of view", () => {
    const { getByTestId } = render(<HeroMoleculeBackground />)
    fireIntersection(0, false)
    expect(getByTestId("r3f-canvas")).toHaveAttribute("data-frameloop", "never")
  })

  it("resumes frameloop=always when the wrapper scrolls back into view", () => {
    const { getByTestId } = render(<HeroMoleculeBackground />)
    fireIntersection(0, false)
    fireIntersection(0, true)
    expect(getByTestId("r3f-canvas")).toHaveAttribute("data-frameloop", "always")
  })

  it("disconnects the observer on unmount", () => {
    const { unmount } = render(<HeroMoleculeBackground />)
    const obs = observers[0]
    unmount()
    expect(obs.disconnect).toHaveBeenCalledOnce()
  })
})
