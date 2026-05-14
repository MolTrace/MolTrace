/**
 * Unit tests for the Step 2 / 3 / 6 building blocks of the spectrum
 * stabilization plan: Zustand store, LTTB downsampler, peak picker, and the
 * requestAnimationFrame coalescer.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { rafThrottle } from "@/src/lib/spectracheck/raf-throttle"
import {
  selectActiveSpectrum,
  toSpectrumRecord,
  useSpectrumStore,
} from "@/src/lib/spectracheck/spectrum-store"
import { __spectrumProcessor } from "@/src/lib/spectracheck/spectrum-worker"

beforeEach(() => {
  useSpectrumStore.setState({ records: {}, activeId: null, processingProgress: 0 })
})

afterEach(() => {
  vi.useRealTimers()
})

describe("spectrum-store", () => {
  it("upserts a spectrum and sets it as the active record on first insert", () => {
    const record = toSpectrumRecord({
      id: "trace-1",
      x: [10, 9.5, 9, 8.5, 8],
      y: [0, 1, 5, 1, 0],
    })
    useSpectrumStore.getState().upsertSpectrum(record)
    const state = useSpectrumStore.getState()
    expect(state.activeId).toBe("trace-1")
    expect(selectActiveSpectrum(state)?.ppmAxis).toBeInstanceOf(Float32Array)
    expect(selectActiveSpectrum(state)?.intensities[2]).toBeCloseTo(5)
  })

  it("removes a spectrum and clears activeId only when the active record is removed", () => {
    const a = toSpectrumRecord({ id: "a", x: [1, 0], y: [1, 0] })
    const b = toSpectrumRecord({ id: "b", x: [2, 1], y: [2, 1] })
    const s = useSpectrumStore.getState()
    s.upsertSpectrum(a)
    s.upsertSpectrum(b)
    s.setActive("b")
    s.removeSpectrum("a")
    expect(useSpectrumStore.getState().activeId).toBe("b")
    s.removeSpectrum("b")
    expect(useSpectrumStore.getState().activeId).toBeNull()
  })

  it("setProgress is a separate slice from records (no spurious data invalidation)", () => {
    const record = toSpectrumRecord({ id: "p", x: [1, 0], y: [1, 0] })
    useSpectrumStore.getState().upsertSpectrum(record)
    const before = useSpectrumStore.getState().records["p"]
    useSpectrumStore.getState().setProgress(0.42)
    const after = useSpectrumStore.getState().records["p"]
    expect(useSpectrumStore.getState().processingProgress).toBe(0.42)
    // The record reference must not change when only progress moves —
    // that's the whole point of having a separate slice.
    expect(after).toBe(before)
  })
})

describe("spectrum-worker (inline processor)", () => {
  it("downsample reduces a large array while preserving endpoints", () => {
    const n = 1000
    const x = Float32Array.from({ length: n }, (_, i) => i)
    const y = Float32Array.from({ length: n }, (_, i) => Math.sin(i / 30))
    const out = __spectrumProcessor.downsample(x, y, 50)
    expect(out.ppm.length).toBe(50)
    expect(out.intensity.length).toBe(50)
    // First and last points are anchored.
    expect(out.ppm[0]).toBe(x[0])
    expect(out.ppm[49]).toBe(x[n - 1])
  })

  it("downsample passes through arrays smaller than the target", () => {
    const x = Float32Array.from([0, 1, 2])
    const y = Float32Array.from([0, 5, 0])
    const out = __spectrumProcessor.downsample(x, y, 50)
    expect(out.ppm).toBe(x)
    expect(out.intensity).toBe(y)
  })

  it("pickPeaks finds a sharp peak in the middle of the trace", () => {
    const x = Float32Array.from([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
    const y = Float32Array.from([0, 0, 0, 1, 5, 1, 0, 0, 0, 0])
    const peaks = __spectrumProcessor.pickPeaks(x, y, 0.5)
    expect(peaks).toHaveLength(1)
    expect(peaks[0]?.ppm).toBe(4)
    expect(peaks[0]?.intensity).toBe(5)
  })

  it("pickPeaks skips below-threshold maxima", () => {
    const y = Float32Array.from([0, 0, 0, 0.1, 0.2, 0.1, 0, 0])
    const x = Float32Array.from([0, 1, 2, 3, 4, 5, 6, 7])
    expect(__spectrumProcessor.pickPeaks(x, y, 1.0)).toEqual([])
  })
})

describe("rafThrottle", () => {
  it("coalesces a burst of calls into a single invocation per frame", async () => {
    const spy = vi.fn()
    const throttled = rafThrottle(spy)
    // Fire ten calls synchronously — only the last args should land.
    for (let i = 0; i < 10; i++) throttled(i)
    // Wait one frame.
    await new Promise((resolve) => requestAnimationFrame(() => resolve(null)))
    expect(spy).toHaveBeenCalledTimes(1)
    expect(spy).toHaveBeenLastCalledWith(9)
  })

  it("rearms after the frame fires so subsequent bursts also coalesce", async () => {
    const spy = vi.fn()
    const throttled = rafThrottle(spy)
    throttled("first")
    await new Promise((resolve) => requestAnimationFrame(() => resolve(null)))
    throttled("second")
    await new Promise((resolve) => requestAnimationFrame(() => resolve(null)))
    expect(spy).toHaveBeenCalledTimes(2)
    expect(spy.mock.calls.map((c) => c[0])).toEqual(["first", "second"])
  })
})
