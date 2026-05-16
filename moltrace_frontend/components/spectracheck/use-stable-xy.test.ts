import { renderHook } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { useStableXY, type StableXY } from "@/components/spectracheck/use-stable-xy"

/**
 * The chart-line "non-flicker" invariant lives here. The whole reason
 * SpectraCheck's analyze step looks calm — the observed spectrum line
 * doesn't repaint when /analyze returns the same x / y as /preview — is
 * that ``useStableXY`` collapses the new payload's xy reference back to
 * the previous one when their content is sample-equal. If that invariant
 * regresses, Plotly silently starts redrawing identical pixels on every
 * analyze; the regression isn't visible in component tests, only by eye.
 * These tests pin the invariant down.
 */

describe("useStableXY", () => {
  it("returns the same reference for identical x / y content across renders", () => {
    const a: StableXY = {
      x: [4.20, 4.19, 4.18, 4.17, 4.16, 4.15, 4.14, 4.13, 4.12, 4.11, 4.10],
      y: [0, 0.1, 0.4, 1.2, 2.1, 5.0, 2.0, 0.9, 0.4, 0.1, 0],
    }
    // Fresh object, fresh arrays — same numeric content as ``a``. This is
    // exactly the shape of ``/preview`` → ``/analyze`` for the same input.
    const b: StableXY = { x: [...a.x], y: [...a.y] }

    const { result, rerender } = renderHook(({ xy }) => useStableXY(xy), {
      initialProps: { xy: a },
    })
    const firstStable = result.current

    rerender({ xy: b })
    const secondStable = result.current

    expect(secondStable).toBe(firstStable)
    expect(secondStable?.x).toBe(firstStable?.x)
    expect(secondStable?.y).toBe(firstStable?.y)
  })

  it("returns the new reference when y content changes", () => {
    // Same x grid, different y peaks — a real spectrum change.
    const a: StableXY = {
      x: [4.20, 4.19, 4.18, 4.17, 4.16, 4.15, 4.14, 4.13, 4.12, 4.11, 4.10],
      y: [0, 0.1, 0.4, 1.2, 2.1, 5.0, 2.0, 0.9, 0.4, 0.1, 0],
    }
    const b: StableXY = {
      x: [...a.x],
      y: [0, 0.1, 0.4, 1.2, 2.1, 7.0, 2.0, 0.9, 0.4, 0.1, 0], // y[5] differs
    }

    const { result, rerender } = renderHook(({ xy }) => useStableXY(xy), {
      initialProps: { xy: a },
    })
    rerender({ xy: b })

    expect(result.current).toBe(b)
    expect(result.current?.y).toBe(b.y)
  })

  it("returns the new reference when length changes", () => {
    const a: StableXY = { x: [1, 2, 3], y: [0, 1, 0] }
    const b: StableXY = { x: [1, 2, 3, 4], y: [0, 1, 0, 1] }

    const { result, rerender } = renderHook(({ xy }) => useStableXY(xy), {
      initialProps: { xy: a },
    })
    rerender({ xy: b })

    expect(result.current).toBe(b)
  })

  it("handles transitions from null and back without throwing", () => {
    const a: StableXY = { x: [1, 2, 3], y: [0, 1, 0] }
    const { result, rerender } = renderHook(({ xy }) => useStableXY(xy), {
      initialProps: { xy: null as StableXY },
    })
    expect(result.current).toBeNull()
    rerender({ xy: a })
    expect(result.current).toBe(a)
    rerender({ xy: null as StableXY })
    expect(result.current).toBeNull()
    // Re-introduce identical-content xy after a null — must not pin the
    // prior (pre-null) reference; the new reference becomes the source of
    // truth because the ref was cleared by the null transition.
    const c: StableXY = { x: [...a.x], y: [...a.y] }
    rerender({ xy: c })
    expect(result.current).toBe(c)
  })

  it("preserves stability over realistic 8k-point spectrum fingerprints", () => {
    // 8k-point synthetic spectrum — typical NMR processed trace size. The
    // fingerprint samples 12 evenly spaced indices + the tail, so every
    // identical-content rerender must collapse to the prior reference.
    const N = 8192
    const x = new Array(N)
    const y = new Array(N)
    for (let i = 0; i < N; i++) {
      x[i] = 10 - (10 * i) / (N - 1)
      // Mostly noise + a peak around index 4096.
      y[i] = Math.sin(i * 0.01) * 0.05 + (Math.abs(i - 4096) < 20 ? 5 : 0)
    }
    const a: StableXY = { x, y }
    const b: StableXY = { x: [...x], y: [...y] }

    const { result, rerender } = renderHook(({ xy }) => useStableXY(xy), {
      initialProps: { xy: a },
    })
    const firstStable = result.current
    rerender({ xy: b })
    expect(result.current).toBe(firstStable)
  })
})
