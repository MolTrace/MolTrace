"use client"

import { useEffect, useState } from "react"

/**
 * Public disclaimer for the marketing landing page: MolTrace is hosted publicly
 * but still actively being built, so visitors should set expectations. Rendered
 * as a slim strip above the (sticky) Header so it is the first thing seen on
 * load, then scrolls away — a standard announcement-bar pattern.
 *
 * The statement "types itself out" on load via a small JS typewriter: a timer
 * reveals the text one character at a time behind a blinking terminal caret.
 * An invisible full-text copy is always rendered (so the text is present in the
 * server HTML for SEO and stays in the layout) and reserves the final single-
 * line width — the typed copy is absolutely positioned over it, so the centered
 * row never jitters while it types. `prefers-reduced-motion` shows the full text
 * immediately with no typing or caret. SSR and the first client render both
 * start empty, so there is no hydration mismatch and no flash of full text.
 */
const KEY = "Actively in development"
const REST = " — MolTrace is a live work-in-progress; features, data & pages may change."
const FULL = KEY + REST
const TYPE_MS = 28

export function DevelopmentBanner() {
  // Number of characters revealed so far. Starts at 0 on both server and client.
  const [shown, setShown] = useState(0)
  // Length to type to: full line on >=md, just the key phrase on small screens.
  const [target, setTarget] = useState(FULL.length)

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    const wide = window.matchMedia("(min-width: 768px)").matches
    const end = wide ? FULL.length : KEY.length
    setTarget(end)

    if (reduceMotion) {
      setShown(end)
      return
    }

    setShown(0)
    let i = 0
    const id = window.setInterval(() => {
      i += 1
      setShown(i)
      if (i >= end) window.clearInterval(id)
    }, TYPE_MS)
    return () => window.clearInterval(id)
  }, [])

  const keyShown = KEY.slice(0, Math.min(shown, KEY.length))
  const restShown = shown > KEY.length ? REST.slice(0, shown - KEY.length) : ""
  const done = shown >= target

  return (
    <div
      role="status"
      aria-label="MolTrace is actively in development — a live work-in-progress; features, data, and pages may change."
      className="dev-banner relative isolate w-full overflow-hidden border-b border-[color:var(--mt-cyan)]/15 bg-[#04070E]"
    >
      {/* slow diagonal light sheen drifting across the strip */}
      <span aria-hidden className="dev-banner-sheen pointer-events-none absolute inset-0" />

      <div className="relative mx-auto flex max-w-7xl items-center justify-center gap-2.5 px-4 py-2">
        {/* pulsing "live" indicator */}
        <span aria-hidden className="relative flex h-2 w-2 shrink-0">
          <span className="dev-banner-ping absolute inline-flex h-full w-full rounded-full" />
          <span className="dev-banner-dot relative inline-flex h-2 w-2 rounded-full" />
        </span>

        <span
          aria-hidden
          className="dev-banner-typewrap relative inline-block whitespace-nowrap font-mono text-[10.5px] font-medium uppercase leading-tight tracking-[0.16em] sm:text-[11px]"
        >
          {/* invisible copy: reserves the final single-line width (no jitter) and keeps the text in the HTML */}
          <span className="invisible">
            {KEY}
            <span className="hidden md:inline">{REST}</span>
          </span>
          {/* typed copy, revealed character-by-character over the reserved width */}
          <span className="absolute left-0 top-0">
            <span className="dev-banner-shimmer font-semibold">{keyShown}</span>
            <span className="text-muted-foreground">{restShown}</span>
            <span className={done ? "dev-banner-caret dev-banner-caret-done" : "dev-banner-caret"}>▌</span>
          </span>
        </span>
      </div>

      {/* animated accent scan-line along the bottom edge */}
      <span aria-hidden className="dev-banner-scan pointer-events-none absolute inset-x-0 bottom-0 h-px" />
    </div>
  )
}
