"use client"

/**
 * Spawn one spectrum worker per page-load and reuse it for every analysis.
 *
 * Step 4 of the stabilization plan: creating a Web Worker costs 100–300 ms.
 * If we re-create one for every spectrum, that cost lands inside the user's
 * "Analyze" click and feels like the same kind of UI freeze we're trying to
 * eliminate. ``useSpectrumWorker`` mounts a single worker the first time the
 * hook fires and terminates it on tear-down.
 *
 * The hook gracefully degrades when Web Workers aren't available (SSR or
 * an old test runtime): it falls back to running the processor functions
 * inline on the main thread. Callers see the same async API either way.
 */

import { useEffect, useRef } from "react"
import * as Comlink from "comlink"
import {
  __spectrumProcessor,
  type SpectrumProcessor,
} from "@/src/lib/spectracheck/spectrum-worker"

export type SpectrumWorkerHandle = Comlink.Remote<SpectrumProcessor> | SpectrumProcessor | null

export function useSpectrumWorker(): { current: SpectrumWorkerHandle } {
  const ref = useRef<SpectrumWorkerHandle>(null)

  useEffect(() => {
    if (typeof window === "undefined") return
    if (typeof Worker === "undefined") {
      // Test / SSR fallback — just expose the synchronous processor so the
      // calling code's `await worker.downsample(...)` still resolves.
      ref.current = __spectrumProcessor
      return () => {
        ref.current = null
      }
    }
    let worker: Worker | null = null
    try {
      worker = new Worker(
        new URL("./spectrum-worker.ts", import.meta.url),
        { type: "module" },
      )
      ref.current = Comlink.wrap<SpectrumProcessor>(worker)
    } catch {
      // Some bundlers / older browsers can't spawn module workers — fall
      // back to inline execution so the surrounding code keeps working.
      ref.current = __spectrumProcessor
    }
    return () => {
      ref.current = null
      worker?.terminate()
    }
  }, [])

  return ref
}
