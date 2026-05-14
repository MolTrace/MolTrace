/**
 * requestAnimationFrame coalescer for high-frequency callbacks.
 *
 * Step 6 of the spectrum-stabilization plan: ResizeObserver / scroll /
 * mousemove can fire hundreds of times per second. Wrapping the handler in
 * ``rafThrottle`` collapses every burst into a single call per frame (60 Hz
 * max), so the canvas never thrashes mid-paint and the shake disappears.
 *
 * The returned wrapper keeps the most recent arguments — by the time the
 * frame fires, you're called once with the freshest state.
 */
export function rafThrottle<TArgs extends unknown[]>(
  fn: (...args: TArgs) => void,
): (...args: TArgs) => void {
  let scheduled = false
  let lastArgs: TArgs | null = null
  // SSR fallback: requestAnimationFrame is undefined on the server. Run
  // synchronously so the throttled callable is still safe to import.
  const raf: (cb: FrameRequestCallback) => number =
    typeof requestAnimationFrame === "function"
      ? requestAnimationFrame
      : (cb) => {
          cb(0)
          return 0
        }
  return (...args: TArgs) => {
    lastArgs = args
    if (scheduled) return
    scheduled = true
    raf(() => {
      const a = lastArgs
      lastArgs = null
      scheduled = false
      if (a) fn(...a)
    })
  }
}
