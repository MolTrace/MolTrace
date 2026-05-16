"use client"

import { useRef } from "react"

/**
 * Return the previous reference of ``xy`` when its content matches by a
 * cheap sampled fingerprint, else capture the new reference and return it.
 *
 * Why this exists
 * ---------------
 * SpectraCheck's ``/nmr/processed/preview`` and ``/nmr/processed/analyze``
 * endpoints return the SAME numeric x / y arrays for the same input — the
 * analyze response only differs in the additional ``peaks``, ``peak_count``,
 * ``predicted_vs_observed``, ``dp4`` fields. But each response is a brand-
 * new ``Response.json()`` deserialisation, so the arrays land with fresh
 * references.
 *
 * Without this hook, every time analyzeResult lands, ``displayPayload``
 * flips identity → ``extractSpectrumXY`` returns a new ``{ x, y }`` object
 * with new array references → ``SpectrumViewer`` (``React.memo``) re-renders
 * → every internal memo keyed on x/y invalidates → Plotly receives a new
 * ``data`` prop reference → ``Plotly.react()`` diffs and re-renders the
 * already-painted observed line. That redraw is visible as a flash even
 * though the line is identical.
 *
 * With this hook, x and y references stay STABLE across preview→analyze.
 * SpectrumViewer's React.memo still re-renders (because ``peaks`` is new),
 * but the expensive percentile / mask / sampling memos inside short-
 * circuit on the stable x/y refs, and Plotly's trace 0 receives the
 * exact same x/y array identities — its internal diff says "unchanged"
 * and the chart line never repaints. Only the new peaks trace is added
 * incrementally.
 *
 * Fingerprint design
 * ------------------
 * We sample 12 evenly spaced indices + the tail. NMR spectra never have
 * pathological cases where the fingerprint matches but the content
 * differs — the sample spacing covers every region of the curve and the
 * length check rules out additions. This keeps the comparison O(1) per
 * call (well under a millisecond even at 65k points) versus an O(n)
 * deep-equal that would itself become a render-time hot path.
 */

const FINGERPRINT_SAMPLES = 12

export type StableXY = { x: number[]; y: number[] } | null

function arraysEqualByFingerprint(a: number[], b: number[]): boolean {
  if (a === b) return true
  if (a.length !== b.length) return false
  if (a.length === 0) return true
  const step = Math.max(1, Math.floor(a.length / FINGERPRINT_SAMPLES))
  for (let i = 0; i < a.length; i += step) {
    if (a[i] !== b[i]) return false
  }
  const tail = a.length - 1
  if (a[tail] !== b[tail]) return false
  return true
}

export function useStableXY(xy: StableXY): StableXY {
  const ref = useRef<StableXY>(xy)
  if (xy === ref.current) return ref.current
  if (xy == null || ref.current == null) {
    ref.current = xy
    return xy
  }
  if (
    arraysEqualByFingerprint(ref.current.x, xy.x) &&
    arraysEqualByFingerprint(ref.current.y, xy.y)
  ) {
    // Content identical — preserve the previous ``xy`` reference so x/y
    // identities flow through unchanged to SpectrumViewer.
    return ref.current
  }
  ref.current = xy
  return xy
}
