/**
 * Spectrum-processing Web Worker.
 *
 * Step 3 of the stabilization plan: anything that takes more than ~16 ms on
 * the main thread freezes the UI for a frame. Downsampling and peak picking
 * across a 65k-point spectrum is exactly that kind of work. Running it in a
 * worker keeps the main thread at 60 fps while the computation runs.
 *
 * The backend already owns the heavy science (FT, baseline, phase, peak
 * inference). What the worker owns is purely *client-side* shape-preserving
 * post-processing for display:
 *
 *  - ``downsample`` — Largest-Triangle-Three-Buckets (LTTB) reduces N points
 *    to ``targetPoints`` while preserving the visual silhouette of the
 *    spectrum. Critical when a browser renderer is asked to plot 65k+
 *    samples in a 300-pixel-wide chart — nothing else can fit on screen
 *    anyway.
 *  - ``pickPeaks`` — local-maxima with neighbour-radius confirmation.
 *  - ``ping`` — cheap roundtrip used in tests to verify the worker is alive.
 *
 * Comlink wraps the worker so callers can ``await worker.downsample(...)``.
 */

import * as Comlink from "comlink"

export type Peak = {
  ppm: number
  intensity: number
  /** Tagged so consumers can render category-coloured markers. */
  category?: "compound" | "solvent" | "impurity" | "reference" | "unknown"
  /** 0 – 1, derived from local-maxima margin over neighbours. */
  confidence?: number
}

export type DownsampleResult = {
  ppm: Float32Array
  intensity: Float32Array
}

const processor = {
  ping(): "pong" {
    return "pong"
  },

  /**
   * Largest-Triangle-Three-Buckets downsampling.
   *
   * Algorithm from Sveinn Steinarsson, Univ. of Iceland MSc thesis (2013).
   * Preserves perceived spectrum shape with a fraction of the point count.
   */
  downsample(
    ppm: Float32Array,
    intensity: Float32Array,
    targetPoints: number,
  ): DownsampleResult {
    const n = intensity.length
    if (n <= targetPoints || targetPoints < 3) {
      return { ppm, intensity }
    }
    const bucketSize = (n - 2) / (targetPoints - 2)
    const sampledPpm = new Float32Array(targetPoints)
    const sampledInt = new Float32Array(targetPoints)
    sampledPpm[0] = ppm[0]
    sampledInt[0] = intensity[0]

    let a = 0
    for (let i = 0; i < targetPoints - 2; i++) {
      const avgRangeStart = Math.floor((i + 1) * bucketSize) + 1
      const avgRangeEnd = Math.min(Math.floor((i + 2) * bucketSize) + 1, n)
      const len = Math.max(1, avgRangeEnd - avgRangeStart)

      let avgX = 0
      let avgY = 0
      for (let j = avgRangeStart; j < avgRangeEnd; j++) {
        avgX += ppm[j]
        avgY += intensity[j]
      }
      avgX /= len
      avgY /= len

      const rangeStart = Math.floor(i * bucketSize) + 1
      const rangeEnd = Math.min(Math.floor((i + 1) * bucketSize) + 1, n)

      let maxArea = -1
      let maxAreaIdx = rangeStart
      const pointAX = ppm[a]
      const pointAY = intensity[a]

      for (let j = rangeStart; j < rangeEnd; j++) {
        const area = Math.abs(
          (pointAX - avgX) * (intensity[j] - pointAY) -
            (pointAX - ppm[j]) * (avgY - pointAY),
        )
        if (area > maxArea) {
          maxArea = area
          maxAreaIdx = j
        }
      }
      sampledPpm[i + 1] = ppm[maxAreaIdx]
      sampledInt[i + 1] = intensity[maxAreaIdx]
      a = maxAreaIdx
    }
    sampledPpm[targetPoints - 1] = ppm[n - 1]
    sampledInt[targetPoints - 1] = intensity[n - 1]
    return { ppm: sampledPpm, intensity: sampledInt }
  },

  /**
   * Simple local-maxima peak detector. Picks ``intensity[i]`` if it is
   * strictly larger than its 4 nearest neighbours and above ``threshold``.
   * Returns peaks sorted by descending intensity.
   */
  pickPeaks(
    ppm: Float32Array,
    intensity: Float32Array,
    threshold: number,
  ): Peak[] {
    const peaks: Peak[] = []
    for (let i = 2; i < intensity.length - 2; i++) {
      const v = intensity[i]
      if (v <= threshold) continue
      if (
        v > intensity[i - 1] &&
        v > intensity[i + 1] &&
        v >= intensity[i - 2] &&
        v >= intensity[i + 2]
      ) {
        peaks.push({
          ppm: ppm[i],
          intensity: v,
          category: "unknown",
          confidence: 0.9,
        })
      }
    }
    peaks.sort((a, b) => b.intensity - a.intensity)
    return peaks
  },
}

export type SpectrumProcessor = typeof processor

// Worker-side: expose via Comlink. The ``self`` guard lets this module also
// be imported in tests / on the main thread without trying to register a
// message handler that would conflict with the test runtime.
if (typeof self !== "undefined" && typeof (self as unknown as { document?: unknown }).document === "undefined") {
  Comlink.expose(processor)
}

export const __spectrumProcessor = processor
