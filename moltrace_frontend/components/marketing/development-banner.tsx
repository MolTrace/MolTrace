"use client"

import { useEffect, useState } from "react"

/**
 * Public disclaimer for the marketing landing page: MolTrace is hosted publicly
 * but still actively being built, so visitors should set expectations. Rendered
 * as a slim strip above the (sticky) Header so it is the first thing seen on
 * load, then scrolls away — a standard announcement-bar pattern.
 *
 * The statement runs a looping JS typewriter: it types itself out character by
 * character behind a blinking terminal caret, holds the full line so it can be
 * read, then backspace-erases and types again — repeating indefinitely. An
 * invisible full-text copy is always rendered (so the text is present in the
 * server HTML for SEO and reserves the final single-line width), and the typed
 * copy is absolutely positioned over it, so the centered row never jitters.
 * `prefers-reduced-motion` shows the full text immediately with no typing,
 * looping, or caret. SSR and the first client render both start empty, so there
 * is no hydration mismatch and no flash of full text.
 */
const KEY = "Actively in development"
const REST = " — MolTrace is a live work-in-progress; features, data & pages may change."
const FULL = KEY + REST

const TYPE_MS = 30 // per-character typing speed
const ERASE_MS = 16 // per-character erase speed (snappier than typing)
const HOLD_MS = 3000 // pause on the fully-typed line before erasing
const BLANK_MS = 500 // pause on empty before typing again

export function DevelopmentBanner() {
  // Number of characters revealed. Starts at 0 on both server and client.
  const [shown, setShown] = useState(0)

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
    // The typewriter is desktop-only (it needs the full single line to fit). Mobile renders
    // the full statement statically + wrapped below, so always target the full line here.
    const end = FULL.length

    if (reduceMotion) {
      setShown(end)
      return
    }

    let i = 0
    let erasing = false
    let timer: ReturnType<typeof setTimeout>

    const tick = () => {
      if (!erasing) {
        if (i < end) {
          i += 1
          setShown(i)
          timer = setTimeout(tick, TYPE_MS)
        } else {
          // fully typed — hold so it can be read, then start erasing
          erasing = true
          timer = setTimeout(tick, HOLD_MS)
        }
      } else {
        if (i > 0) {
          i -= 1
          setShown(i)
          timer = setTimeout(tick, ERASE_MS)
        } else {
          // fully erased — brief pause, then type again
          erasing = false
          timer = setTimeout(tick, BLANK_MS)
        }
      }
    }

    setShown(0)
    timer = setTimeout(tick, TYPE_MS)
    return () => clearTimeout(timer)
  }, [])

  const keyShown = KEY.slice(0, Math.min(shown, KEY.length))
  const restShown = shown > KEY.length ? REST.slice(0, shown - KEY.length) : ""

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

        {/* Looping typewriter — interactive on every breakpoint. Desktop (>=md): one
            nowrap line over an invisible width reserve. Mobile (<md): the SAME typewriter,
            but the line wraps inside a max-width box — the invisible full-text copy reserves
            the wrapped HEIGHT and the typed overlay (inset-0, left-aligned) wraps identically,
            so the box never reflows. Either way the full statement types out char-by-char. */}
        <span
          aria-hidden
          className="dev-banner-typewrap relative inline-block max-w-[17rem] whitespace-normal text-left font-mono text-[10px] font-medium uppercase leading-snug tracking-[0.07em] sm:text-[11px] md:max-w-none md:whitespace-nowrap md:leading-tight md:tracking-[0.16em]"
        >
          {/* invisible copy: reserves the final box (wrapped on mobile, single line on desktop)
              so the row never jitters, and keeps the text in the HTML for SEO. */}
          <span className="invisible">{FULL}</span>
          {/* typed copy, revealed/erased char-by-char. inset-0 makes it wrap to the reserved
              box width on mobile; right/bottom auto on desktop -> natural single-line width. */}
          <span className="absolute inset-0 md:bottom-auto md:right-auto">
            <span className="dev-banner-shimmer font-semibold">{keyShown}</span>
            {/* fixed light color: the banner surface is always dark, so this must not depend on
                the theme (text-muted-foreground is dark in light mode -> invisible). */}
            <span className="text-slate-400">{restShown}</span>
            <span className="dev-banner-caret">▌</span>
          </span>
        </span>
      </div>

      {/* animated accent scan-line along the bottom edge */}
      <span aria-hidden className="dev-banner-scan pointer-events-none absolute inset-x-0 bottom-0 h-px" />
    </div>
  )
}
