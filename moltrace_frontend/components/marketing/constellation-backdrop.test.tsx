import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { ConstellationBackdrop, generateStars } from "./constellation-backdrop"

/**
 * The one property worth a test here is DETERMINISM, because its failure mode is
 * invisible. A backdrop built with Math.random() renders one sky on the server
 * and a different one on the client; React patches the difference, the page
 * looks fine, and the only trace is a hydration error in the console and a
 * second paint. Nobody notices until someone reads the console — which is
 * exactly the class of bug a screenshot cannot catch.
 */

function positions(container: HTMLElement) {
  return Array.from(container.querySelectorAll("circle.mt-star")).map(
    (c) => `${c.getAttribute("cx")},${c.getAttribute("cy")},${c.getAttribute("r")}`,
  )
}

describe("ConstellationBackdrop", () => {
  it("generates the same sky on two independent runs", () => {
    // THE GENERATOR, not the render. Rendering the component twice reuses one
    // module-level array, so it compares that array to itself and passes even
    // with Math.random — mutation-checked, and it is why generateStars is
    // exported at all.
    expect(generateStars()).toEqual(generateStars())
    expect(generateStars(12)).toEqual(generateStars(12))
  })

  it("puts that same sky into the DOM", () => {
    const { container } = render(<ConstellationBackdrop />)
    const drawn = positions(container)
    expect(drawn).toEqual(
      generateStars().map((s) => `${s.x},${s.y},${s.r}`),
    )
  })

  it("fills the field in both axes, not a diagonal", () => {
    // A seeded generator wired up wrong — sharing one draw between x and y —
    // is still perfectly deterministic and still looks broken, and it passes a
    // min/max range check because the diagonal spans the full range on both
    // axes. Quadrant coverage is what actually catches it: a diagonal populates
    // two corners and leaves the other two empty. Mutation-checked.
    const stars = generateStars()
    const quadrants = new Set(
      stars.map((s) => `${s.x > 1200 / 2 ? "R" : "L"}${s.y > 600 / 2 ? "B" : "T"}`),
    )
    expect(quadrants).toEqual(new Set(["LT", "LB", "RT", "RB"]))
    // ...and each corner holds a real share, not one stray point.
    for (const corner of ["LT", "LB", "RT", "RB"]) {
      const inCorner = stars.filter(
        (s) => `${s.x > 600 ? "R" : "L"}${s.y > 300 ? "B" : "T"}` === corner,
      )
      expect(inCorner.length).toBeGreaterThan(stars.length / 10)
    }
  })

  it("carries each star's resting brightness as an attribute, not only in CSS", () => {
    // The twinkle keyframe dims from --mt-star-o. The opacity attribute is both
    // the value it rests at and the fallback under reduced motion, where the
    // animation is switched off entirely — without it the stars would be
    // invisible for exactly the users who disabled the animation.
    const { container } = render(<ConstellationBackdrop />)
    for (const star of container.querySelectorAll("circle.mt-star")) {
      const opacity = Number(star.getAttribute("opacity"))
      expect(opacity).toBeGreaterThan(0)
      expect(opacity).toBeLessThanOrEqual(1)
    }
  })

  it("is hidden from assistive technology", () => {
    // Pure decoration. The section's argument is entirely in its text.
    const { container } = render(<ConstellationBackdrop />)
    expect(container.firstElementChild?.getAttribute("aria-hidden")).toBe("true")
  })

  it("keeps stars round by slicing rather than stretching the viewBox", () => {
    // preserveAspectRatio="none" on a wide band turns every circle into an
    // ellipse. It is a one-word regression with no other symptom.
    const { container } = render(<ConstellationBackdrop />)
    const svg = container.querySelector("svg")!
    expect(svg.getAttribute("preserveAspectRatio")).toBe("xMidYMid slice")
  })
})
