import { describe, expect, it } from "vitest"
import { ANALYSIS_JOB_POLL_DELAYS_MS } from "@/src/lib/spectracheck/useAnalysisJob"

/** Cumulative wall-clock at which poll N fires, ignoring request time. */
function discoveryTimeline(ticks: number): number[] {
  const out: number[] = []
  let t = 0
  for (let i = 0; i < ticks; i++) {
    t += ANALYSIS_JOB_POLL_DELAYS_MS[Math.min(i, ANALYSIS_JOB_POLL_DELAYS_MS.length - 1)]!
    out.push(t)
  }
  return out
}

/** When would a job finishing at `jobMs` be OBSERVED, under a given schedule? */
function observedAt(jobMs: number, timeline: number[]): number {
  const hit = timeline.find((t) => t >= jobMs)
  return hit ?? Infinity
}

const FIXED_2S = Array.from({ length: 40 }, (_, i) => i * 2000)

describe("analysis job poll backoff", () => {
  it("fires the first poll immediately", () => {
    expect(ANALYSIS_JOB_POLL_DELAYS_MS[0]).toBe(0)
  })

  it("is monotonically non-decreasing and caps at the previous 2 s cadence", () => {
    const d = [...ANALYSIS_JOB_POLL_DELAYS_MS]
    for (let i = 1; i < d.length; i++) expect(d[i]!).toBeGreaterThanOrEqual(d[i - 1]!)
    expect(d[d.length - 1]).toBe(2000)
  })

  it("discovers a sub-second job MUCH sooner than the old flat 2 s interval", () => {
    const t = discoveryTimeline(12)
    // The measured backend cost for a real 3.5 MB Bruker folder was ~0.7 s.
    const backoff = observedAt(700, t)
    const fixed = observedAt(700, FIXED_2S)
    expect(fixed).toBe(2000) // old behaviour: a finished job waits for the 2 s grid
    expect(backoff).toBeLessThanOrEqual(1000)
    expect(backoff).toBeLessThan(fixed)
  })

  it("never discovers a job LATER than the old fixed interval would have", () => {
    const t = discoveryTimeline(60)
    for (const jobMs of [0, 100, 700, 1400, 2000, 3300, 5000, 9000, 15000]) {
      expect(observedAt(jobMs, t)).toBeLessThanOrEqual(observedAt(jobMs, FIXED_2S))
    }
  })

  it("does not issue materially more requests for a long job", () => {
    // Over 30 s, the backoff ladder must stay close to the flat-2 s request count (~15),
    // i.e. the early fast ticks are a small fixed surcharge, not sustained polling.
    const t = discoveryTimeline(60)
    const within30s = t.filter((x) => x <= 30_000).length
    const fixedWithin30s = FIXED_2S.filter((x) => x <= 30_000).length
    expect(within30s - fixedWithin30s).toBeLessThanOrEqual(4)
  })
})
