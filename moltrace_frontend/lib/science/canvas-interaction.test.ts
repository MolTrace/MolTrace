import { describe, expect, it } from "vitest"
import {
  CANVAS_ZOOM_IN_FACTOR,
  CANVAS_ZOOM_OUT_FACTOR,
  canvasKeyAction,
  clampSpanToDomain,
  isZoomWindowChord,
  panSpan,
  spanFromDrag,
  wheelIntensityFactor,
  zoomSpanAboutCentre,
} from "@/lib/science/canvas-interaction"

const DOMAIN = { min: 0, max: 10 }

describe("clampSpanToDomain", () => {
  it("slides a window back inside the domain without shrinking it", () => {
    expect(clampSpanToDomain({ min: -2, max: 1 }, DOMAIN)).toEqual({ min: 0, max: 3 })
    expect(clampSpanToDomain({ min: 8, max: 11 }, DOMAIN)).toEqual({ min: 7, max: 10 })
  })

  it("returns the domain for a window wider than it", () => {
    expect(clampSpanToDomain({ min: -5, max: 20 }, DOMAIN)).toEqual(DOMAIN)
  })
})

describe("panSpan", () => {
  it("pans view-left toward HIGHER ppm on a reversed axis", () => {
    // High ppm is drawn on the left of every NMR plot. Pressing ArrowLeft moves the view left,
    // which must reveal higher shifts — the stack viewer originally had this inverted, and the
    // mistake is invisible in review because both signs "work".
    const next = panSpan({ min: 4, max: 6 }, DOMAIN, -1, { reversedX: true })
    expect(next).toEqual({ min: 4.2, max: 6.2 })
  })

  it("pans view-left toward LOWER values on a normal axis", () => {
    const next = panSpan({ min: 4, max: 6 }, DOMAIN, -1, { reversedX: false })
    expect(next).toEqual({ min: 3.8, max: 5.8 })
  })

  it("stops at the domain edge instead of walking off the data", () => {
    // Reversed axis: view-LEFT is toward higher ppm, and {9,10} already touches the top of the
    // domain — the pan must clamp there, not slide past the data.
    const next = panSpan({ min: 9, max: 10 }, DOMAIN, -1, { reversedX: true })
    expect(next).toEqual({ min: 9, max: 10 })
  })

  it("returns null at full range, so callers no-op rather than jitter", () => {
    expect(panSpan({ min: 0, max: 10 }, DOMAIN, 1)).toBeNull()
  })
})

describe("zoomSpanAboutCentre", () => {
  it("halves and doubles about the centre with the shared factors", () => {
    const zoomedIn = zoomSpanAboutCentre({ min: 2, max: 6 }, DOMAIN, CANVAS_ZOOM_IN_FACTOR, 0.02)
    expect(zoomedIn).toEqual({ min: 3, max: 5 })
    const zoomedOut = zoomSpanAboutCentre({ min: 3, max: 5 }, DOMAIN, CANVAS_ZOOM_OUT_FACTOR, 0.02)
    expect(zoomedOut).toEqual({ min: 2, max: 6 })
  })

  it("cannot zoom below the minimum span", () => {
    const next = zoomSpanAboutCentre({ min: 4.99, max: 5.01 }, DOMAIN, CANVAS_ZOOM_IN_FACTOR, 0.02)
    expect(next.max - next.min).toBeCloseTo(0.02, 10)
  })

  it("zooming out at full range stays the domain", () => {
    expect(zoomSpanAboutCentre(DOMAIN, DOMAIN, CANVAS_ZOOM_OUT_FACTOR, 0.02)).toEqual(DOMAIN)
  })
})

describe("spanFromDrag", () => {
  it("orders the endpoints", () => {
    expect(spanFromDrag(7, 3, 0.02)).toEqual({ min: 3, max: 7 })
  })

  it("refuses a stray click", () => {
    expect(spanFromDrag(5, 5.001, 0.02)).toBeNull()
  })
})

describe("keymap", () => {
  it("maps the shared keys and nothing else", () => {
    expect(canvasKeyAction("ArrowLeft")).toEqual({ kind: "pan", screenDirection: -1 })
    expect(canvasKeyAction("ArrowRight")).toEqual({ kind: "pan", screenDirection: 1 })
    expect(canvasKeyAction("+")).toEqual({ kind: "zoom", factor: CANVAS_ZOOM_IN_FACTOR })
    expect(canvasKeyAction("=")).toEqual({ kind: "zoom", factor: CANVAS_ZOOM_IN_FACTOR })
    expect(canvasKeyAction("-")).toEqual({ kind: "zoom", factor: CANVAS_ZOOM_OUT_FACTOR })
    expect(canvasKeyAction("0")).toEqual({ kind: "reset" })
    // Esc must NOT reset — cancelling transients is per-viewer, resetting is forbidden.
    expect(canvasKeyAction("Escape")).toBeNull()
    expect(canvasKeyAction("a")).toBeNull()
  })
})

describe("wheel intensity", () => {
  it("is a ratio: one notch up exactly undoes one notch down", () => {
    expect(wheelIntensityFactor(100) * wheelIntensityFactor(-100)).toBeCloseTo(1, 12)
  })

  it("scroll up grows the peaks", () => {
    expect(wheelIntensityFactor(-100)).toBeGreaterThan(1)
  })
})

describe("zoom chord", () => {
  it("shift is the explicit opt-in", () => {
    expect(isZoomWindowChord({ shiftKey: true })).toBe(true)
    expect(isZoomWindowChord({ shiftKey: false })).toBe(false)
  })
})
