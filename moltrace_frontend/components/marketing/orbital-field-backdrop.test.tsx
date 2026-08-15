import { readFileSync } from "node:fs"
import { join } from "node:path"

import { render } from "@testing-library/react"
import { act } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { OrbitalFieldBackdrop } from "./orbital-field-backdrop"

/**
 * These assert the SHIPPED ARTIFACT — the generated stylesheet and the markup
 * that names it — rather than a generator function. That is deliberate: the
 * dots are committed CSS now, so what a generator would produce is beside the
 * point; what the browser downloads is the thing that can regress.
 *
 * Note what is NOT tested any more: hydration determinism. It mattered when the
 * field was built during render, where a Math.random() field renders one way on
 * the server and another on the client. A static stylesheet cannot have that
 * bug at all, so the risk is designed out rather than guarded.
 *
 * The two live risks both fail silently:
 *
 *   PER FRAME — the field must animate the LAYER, not the particle. A version
 *   that puts every dot in the DOM looks identical and asks the engine to carry
 *   hundreds of nodes and transform vector geometry every frame.
 *
 *   PER RESPONSE — the dots must live in CSS, not in inline styles. As a style
 *   prop they ship twice in every HTML response (style attribute + RSC flight
 *   payload); measured, that was 32% of the homepage document.
 */

const CSS = readFileSync(join(__dirname, "orbital-field.css"), "utf8")
const LAYER_RULES = [...CSS.matchAll(/\.mt-orbit-(\d+)\s*\{([^}]*)\}/g)]

/** Every dot's centre, parsed back out of the generated data URIs. */
function dotCentres() {
  return [...CSS.matchAll(/cx='(-?\d+)' cy='(-?\d+)'/g)].map((m) => ({
    x: Number(m[1]),
    y: Number(m[2]),
  }))
}

describe("OrbitalFieldBackdrop markup", () => {
  it("ships six empty layers and NO inline styles", () => {
    // The payload guarantee. A style attribute here means the data URIs are
    // back in the HTML — and in the flight payload alongside it.
    const { container } = render(<OrbitalFieldBackdrop />)
    const layers = container.querySelectorAll(".mt-orbit")

    expect(layers.length).toBe(LAYER_RULES.length)
    for (const layer of layers) {
      expect(layer.getAttribute("style")).toBeNull()
      expect(layer.children.length).toBe(0)
    }
    expect(container.querySelectorAll("circle").length).toBe(0)
    expect(container.querySelectorAll("*").length).toBeLessThan(20)
  })

  it("names a layer class that the stylesheet actually defines", () => {
    // A renamed class in either file leaves an invisible backdrop.
    const { container } = render(<OrbitalFieldBackdrop />)
    const defined = new Set(LAYER_RULES.map((m) => `mt-orbit-${m[1]}`))
    for (const layer of container.querySelectorAll(".mt-orbit")) {
      const own = [...layer.classList].find((c) => /^mt-orbit-\d+$/.test(c))
      expect(own, `layer has no numbered class: ${layer.className}`).toBeDefined()
      expect(defined.has(own!)).toBe(true)
    }
  })

  it("is hidden from assistive technology", () => {
    const { container } = render(<OrbitalFieldBackdrop />)
    expect(container.firstElementChild?.getAttribute("aria-hidden")).toBe("true")
  })
})

describe("orbital-field.css", () => {
  it("animates the layer, so the per-frame cost cannot grow with density", () => {
    expect(CSS).toMatch(/\.mt-orbit\s*\{[^}]*animation-name:\s*mt-orbit-spin/)
    expect(CSS).toMatch(/@keyframes mt-orbit-spin/)
    // Each layer carries its dots as ONE background image.
    for (const [, index, body] of LAYER_RULES) {
      expect(body, `layer ${index}`).toContain("data:image/svg+xml")
    }
  })

  it("keeps particles round rather than stretching them to the section", () => {
    // cover preserves the authored 2:1 ratio and crops; scaling the axes
    // independently turns every dot into an oval.
    expect(CSS).toMatch(/\.mt-orbit\s*\{[^}]*background-size:\s*cover/)
  })

  it("stops the motion under prefers-reduced-motion", () => {
    const block = CSS.match(/@media \(prefers-reduced-motion: reduce\)\s*\{([\s\S]*?)\n\}/)
    expect(block, "no reduced-motion block").not.toBeNull()
    expect(block![1]).toMatch(/animation:\s*none/)
  })

  it("gives the layers different speeds so the field drifts rather than spins", () => {
    const durations = LAYER_RULES.map((m) => m[2].match(/animation-duration:\s*(\d+)s/)?.[1])
    const directions = LAYER_RULES.map((m) => m[2].match(/animation-direction:\s*(\w+)/)?.[1])
    expect(durations.every(Boolean)).toBe(true)
    // Identical durations make a rotating point cloud read as one rigid wheel.
    expect(new Set(durations).size).toBe(durations.length)
    expect(new Set(directions).size).toBe(2)
  })

  it("leaves the middle open, where the heading and cards sit", () => {
    const centres = dotCentres()
    expect(centres.length).toBeGreaterThan(500)
    for (const p of centres) {
      expect(Math.hypot(p.x - 600, p.y - 300)).toBeGreaterThan(280)
    }
  })

  it("encodes the dots compactly, because this file is downloaded", () => {
    const dots = dotCentres().length
    const uriBytes = [...CSS.matchAll(/data:image\/svg\+xml,[^"]+/g)].reduce(
      (n, m) => n + m[0].length,
      0,
    )
    // ~43 bytes/dot with fill and opacity hoisted onto groups and only #, < and
    // > escaped. Per-dot attributes plus encodeURIComponent was 90.
    expect(uriBytes / dots).toBeLessThan(50)

    // Never a fill or opacity attribute on an individual circle.
    expect(CSS).not.toMatch(/<circle[^/]*fill=/)
    expect(CSS).not.toMatch(/circle[^/]*opacity=/)
    // Whole-unit coordinates, not full-precision floats.
    expect(CSS).not.toMatch(/cx='\d+\.\d/)
    // Minimal escaping only — encodeURIComponent creeping back would escape
    // the spaces and quotes that make up most of the string.
    expect(CSS).not.toContain("%20")
    expect(CSS).not.toContain("%27")
  })

  it("is marked generated, so nobody hand-edits a file a script overwrites", () => {
    expect(CSS.slice(0, 200)).toMatch(/GENERATED by scripts\/generate-orbital-field\.mjs/)
  })
})

/**
 * The off-screen pause (P4 §8). Six section-sized composited layers with
 * will-change stay resident on the GPU and keep ticking for the tab's lifetime
 * unless something stops them — and every part of that mechanism fails
 * silently: a renamed class, a dropped CSS rule (a re-run of the generator
 * would drop it if it is not in the generator), or an observer that never
 * toggles all leave the layers spinning with no visible symptom.
 */
describe("off-screen pause", () => {
  const originalIO = globalThis.IntersectionObserver
  let callback: IntersectionObserverCallback | null = null

  beforeEach(() => {
    callback = null
    class MockIntersectionObserver {
      constructor(cb: IntersectionObserverCallback) {
        callback = cb
      }
      observe = vi.fn()
      disconnect = vi.fn()
      unobserve = vi.fn()
      takeRecords = () => []
      root: Element | null = null
      rootMargin = ""
      thresholds: ReadonlyArray<number> = []
    }
    globalThis.IntersectionObserver =
      MockIntersectionObserver as unknown as typeof IntersectionObserver
  })

  afterEach(() => {
    globalThis.IntersectionObserver = originalIO
  })

  it("carries a paused rule that stops the animation and releases the layers", () => {
    expect(CSS).toMatch(/\.mt-orbit-paused \.mt-orbit\s*\{[^}]*animation-play-state:\s*paused/)
    expect(CSS).toMatch(/\.mt-orbit-paused \.mt-orbit\s*\{[^}]*will-change:\s*auto/)
  })

  it("toggles that class as the section leaves and re-enters the viewport", () => {
    const { container } = render(<OrbitalFieldBackdrop />)
    const root = container.firstElementChild as HTMLElement
    expect(callback).toBeTypeOf("function")

    act(() => {
      callback?.([{ isIntersecting: false } as IntersectionObserverEntry], {} as IntersectionObserver)
    })
    expect(root.classList.contains("mt-orbit-paused")).toBe(true)

    act(() => {
      callback?.([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver)
    })
    expect(root.classList.contains("mt-orbit-paused")).toBe(false)
  })
})
