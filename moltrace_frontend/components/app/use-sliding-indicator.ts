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

/**
 * Both axes, not just the horizontal one. A strip that wraps onto a second row —
 * which any of these will do once the labels are long enough or the column is
 * narrow enough — puts the active item at a different `top`, and an indicator
 * that only tracks `left` lands on the wrong row while looking confidently
 * correct on the first.
 */
export type IndicatorRect = { left: number; top: number; width: number; height: number }

export function useSlidingIndicator<T extends HTMLElement = HTMLDivElement>(
  /** Changing this re-measures — pass whatever identifies the active item. */
  activeKey: string | undefined,
  /**
   * How the active item marks itself. Defaults to our own `data-active`, but
   * Radix-driven strips pass `[data-state="active"]` so they can reuse this
   * without being rewritten to carry a second attribute that means the same
   * thing.
   */
  activeSelector = '[data-active="true"]',
) {
  const containerRef = useRef<T | null>(null)
  const [rect, setRect] = useState<IndicatorRect | null>(null)

  const measure = useCallback(() => {
    const container = containerRef.current
    if (!container) return
    const active = container.querySelector<HTMLElement>(activeSelector)
    if (!active || active.offsetWidth === 0) {
      setRect(null)
      return
    }
    setRect((prev) =>
      prev &&
      prev.left === active.offsetLeft &&
      prev.top === active.offsetTop &&
      prev.width === active.offsetWidth &&
      prev.height === active.offsetHeight
        ? prev
        : {
            left: active.offsetLeft,
            top: active.offsetTop,
            width: active.offsetWidth,
            height: active.offsetHeight,
          },
    )
  }, [activeSelector])

  // Layout effect so the indicator is placed in the same frame the active item
  // changes — measuring in a passive effect lets one frame paint with the
  // indicator still under the previous tab, which reads as a flicker.
  useLayoutEffect(() => {
    measure()
  }, [measure, activeKey])

  /**
   * Observer-driven re-measures are COALESCED to one animation frame, and this
   * is what stops the indicator flicking to the wrong tab.
   *
   * Both observers below fire while the DOM is mid-update — a ResizeObserver
   * reports each item as it reflows, a MutationObserver fires per attribute
   * mutation — so measuring on every callback samples the strip in states that
   * never actually paint. Every sample is published, and the indicator animates
   * to it over 300ms, so ONE bad intermediate reading turns into a visible
   * swing. Measured while changing stage on Regentry: the bar went from x=80 to
   * x=465 and then back to x=297, i.e. it travelled past the tab it was heading
   * for and came back. That is the shake, and it is worst when the surrounding
   * layout is also moving, which is why collapsing the sidebar made it obvious.
   *
   * Deferring to the next frame collapses a burst of callbacks into a single
   * measurement of the settled layout. The layout effect above is deliberately
   * left synchronous: on an actual selection change the indicator must be
   * placed in the same frame, or the first frame paints it under the old tab.
   */
  const frame = useRef<number | null>(null)
  const scheduleMeasure = useCallback(() => {
    if (typeof requestAnimationFrame === "undefined") {
      measure()
      return
    }
    if (frame.current !== null) cancelAnimationFrame(frame.current)
    frame.current = requestAnimationFrame(() => {
      frame.current = null
      measure()
    })
  }, [measure])

  useEffect(() => {
    return () => {
      if (frame.current !== null && typeof cancelAnimationFrame !== "undefined") {
        cancelAnimationFrame(frame.current)
      }
    }
  }, [])

  // Re-measure when the strip or its items resize: a font swap, a badge
  // appearing, or the container being scrolled into a narrower column all move
  // the target out from under the indicator.
  useEffect(() => {
    const container = containerRef.current
    if (!container || typeof ResizeObserver === "undefined") return
    const observer = new ResizeObserver(() => scheduleMeasure())
    observer.observe(container)
    for (const child of Array.from(container.children)) {
      // NOT the indicator itself. It is a child of the strip, and the hook sets
      // its width — so observing it means every measurement resizes the thing
      // being observed, which schedules another measurement. The equality check
      // in `measure` stops that becoming an infinite loop, but it still doubles
      // the callback traffic during exactly the reflow where the readings are
      // least trustworthy.
      if (child.getAttribute("aria-hidden") === "true") continue
      observer.observe(child)
    }
    return () => observer.disconnect()
  }, [scheduleMeasure])

  // Watch the marker attribute itself. Callers that own the selected value pass
  // it as `activeKey` and are already covered by the layout effect above, but a
  // strip whose selection lives inside a third-party primitive (Radix Tabs) never
  // tells us it changed — the only signal is the attribute flipping in the DOM.
  useEffect(() => {
    const container = containerRef.current
    if (!container || typeof MutationObserver === "undefined") return
    const observer = new MutationObserver(() => scheduleMeasure())
    observer.observe(container, {
      attributes: true,
      attributeFilter: ["data-state", "data-active"],
      subtree: true,
    })
    return () => observer.disconnect()
  }, [scheduleMeasure])

  return { containerRef, rect }
}
