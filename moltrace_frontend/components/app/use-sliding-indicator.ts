"use client"

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react"

/**
 * Tracks the position and width of the active item in a horizontal strip so a
 * single indicator element can travel between items instead of each item fading
 * its own background in and out.
 *
 * The difference is the whole point: N independent fades read as N things
 * blinking, while one element moving reads as a selection being carried from
 * here to there. Only the moving version survives being watched closely.
 *
 * The active item is found by `[data-active="true"]` rather than by index, so
 * the hook does not need to know how the strip is built or how many tiers use it.
 *
 * jsdom returns 0 for every offset, so under test the indicator measures to a
 * zero-width box and simply never shows. That is deliberate — the tests are about
 * tab semantics, and a layout-measuring hook should not be able to fail them.
 */

export type IndicatorRect = { left: number; width: number }

export function useSlidingIndicator<T extends HTMLElement = HTMLDivElement>(
  /** Changing this re-measures — pass whatever identifies the active item. */
  activeKey: string | undefined,
) {
  const containerRef = useRef<T | null>(null)
  const [rect, setRect] = useState<IndicatorRect | null>(null)

  const measure = useCallback(() => {
    const container = containerRef.current
    if (!container) return
    const active = container.querySelector<HTMLElement>('[data-active="true"]')
    if (!active || active.offsetWidth === 0) {
      setRect(null)
      return
    }
    setRect((prev) =>
      prev && prev.left === active.offsetLeft && prev.width === active.offsetWidth
        ? prev
        : { left: active.offsetLeft, width: active.offsetWidth },
    )
  }, [])

  // Layout effect so the indicator is placed in the same frame the active item
  // changes — measuring in a passive effect lets one frame paint with the
  // indicator still under the previous tab, which reads as a flicker.
  useLayoutEffect(() => {
    measure()
  }, [measure, activeKey])

  // Re-measure when the strip or its items resize: a font swap, a badge
  // appearing, or the container being scrolled into a narrower column all move
  // the target out from under the indicator.
  useEffect(() => {
    const container = containerRef.current
    if (!container || typeof ResizeObserver === "undefined") return
    const observer = new ResizeObserver(() => measure())
    observer.observe(container)
    for (const child of Array.from(container.children)) observer.observe(child)
    return () => observer.disconnect()
  }, [measure])

  return { containerRef, rect }
}
