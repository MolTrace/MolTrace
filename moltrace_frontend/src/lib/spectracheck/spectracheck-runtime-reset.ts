"use client"

type ResetCallback = () => void

const resetCallbacks = new Set<ResetCallback>()

export function registerSpectraCheckRuntimeReset(callback: ResetCallback): () => void {
  resetCallbacks.add(callback)
  return () => {
    resetCallbacks.delete(callback)
  }
}

export function clearSpectraCheckRuntimeState(): void {
  for (const callback of resetCallbacks) {
    try {
      callback()
    } catch {
      // Reset is best-effort; one stale cache should not block sign-out.
    }
  }
}
