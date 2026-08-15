"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import type { LucideIcon } from "lucide-react"

import { cn } from "@/lib/utils"

export type DeckItem = {
  icon: LucideIcon
  title: string
  pill: string
  desc: string
  /**
   * Colour roles, which must not be swapped. `accent` is the vivid token and
   * fills the rule and the icon; `ink` is the AA-safe variant and colours every
   * piece of type; `soft` is the low-alpha tint behind the pill and in the glow.
   * The vivid tokens sit at 2-3:1 as text and fail AA.
   */
  accent: string
  ink: string
  soft: string
}

/**
 * A ring of cards seen in perspective: one card forward and legible, its
 * neighbours falling back and dimming, the far side out of sight.
 *
 * WHY A RING AND NOT A ROW. Six cards laid out flat is the grid this replaces —
 * everything equally present, so nothing is. A deck gives the section a subject.
 * The cost is that only one card is fully readable at a time, which is the right
 * trade for a "here is what we do" band and the wrong one for anything a reader
 * needs to compare side by side. Do not reuse this for pricing tiers.
 *
 * The ring wraps, so the two ends never dead-stop and the far card fades out
 * rather than piling up at the edge. Offsets are a percentage of the card's own
 * width, so the whole thing is responsive without measuring anything: the same
 * transforms that fan the deck on a wide screen let it degrade to one card with
 * peeking edges on a phone.
 *
 * KEYBOARD AND SCREEN READERS. All six cards stay in the DOM and in reading
 * order, so a screen reader gets the whole section regardless of what is
 * visually forward — the depth is presentation, not content. Only the active
 * card is tabbable (roving tabindex), because six tab stops that merely change
 * which card is in front is noise; arrows move between them, which is the
 * standard composite-widget contract.
 *
 * AUTO-ADVANCE, AND THE FOUR THINGS THAT STOP IT. Content that moves on its own
 * is the classic carousel accessibility failure, and WCAG 2.2.2 (Pause, Stop,
 * Hide) makes it a hard AA requirement: anything auto-moving for more than five
 * seconds needs "a mechanism for the user to pause, stop, or hide it". So:
 *
 *   1. TOUCHING THE DECK STOPS IT, permanently. A pointer down anywhere on the
 *      stage — a card, the gap between cards, the card already in front — ends
 *      autoplay and does not resume. This is the mechanism 2.2.2 asks for.
 *   2. Hovering suspends it, so it cannot slide out from under a reader mid-
 *      sentence. Temporary: moving away resumes.
 *   3. Focus anywhere inside suspends it, the keyboard equivalent — and an arrow
 *      key, being a deliberate choice, stops it for good like a tap.
 *   4. It only runs while the deck is on screen, so a reader arrives at the
 *      first card rather than wherever a timer wandered to while the section was
 *      three screens down.
 *
 * THERE IS NO PLAY/PAUSE BUTTON, and that was a deliberate call. A dedicated
 * control is the belt-and-braces reading of 2.2.2; the criterion's actual text
 * asks for a mechanism, and "put your finger on it and it stops" is one that
 * every pointer and touch user already knows without being told. The case rests
 * on stopping being available WITHOUT having to change what you are reading —
 * hence rule 1 covering the front card and the empty space, not just the cards
 * you would be choosing between. What it gives up is discoverability: nothing on
 * screen announces that the deck can be stopped. If that is ever judged too
 * thin, the fix is to put the button back, not to weaken rule 1.
 *
 * Under prefers-reduced-motion it never starts at all.
 *
 * There is no aria-live region. Nothing is being inserted or removed; all six
 * cards are present the whole time and only their depth changes, so announcing
 * on each tick would narrate a purely visual event over whatever the reader is
 * actually doing.
 */

/**
 * Long enough to read a card. The descriptions run 25-40 words, which is around
 * 8 seconds of reading — this is deliberately a little shorter, because hovering
 * pauses it and a deck that waits for the slowest reader reads as broken.
 */
const AUTO_ADVANCE_MS = 6500

/** Tracks the OS "reduce motion" setting, including a change while open. */
function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)")
    const update = () => setReduced(query.matches)
    update()
    query.addEventListener("change", update)
    return () => query.removeEventListener("change", update)
  }, [])
  return reduced
}

/** Signed shortest way round a ring of `count` — 0, ±1, ±2, then the far side. */
export function ringOffset(index: number, active: number, count: number) {
  const raw = (index - active + count) % count
  return raw > count / 2 ? raw - count : raw
}

/**
 * Depth tiers by absolute distance from the front, index 0 being the front.
 *
 * `x` is a percentage of the card's own width. The values are not a smooth curve
 * on purpose: the gap from the front card to its neighbours is larger than the
 * gap between neighbours, so the front one reads as chosen rather than as merely
 * the middle of a fan.
 *
 * THE BLUR IS LOAD-BEARING, not decoration. Without it the neighbours sat at an
 * opacity where their sentences were still readable — and the front card slices
 * them mid-word, so the section looked like text failing to render rather than
 * cards receding. Defocusing them puts them decisively in the background: you
 * read the front card and register the others as depth, which is what a deck is
 * supposed to do. It scales with distance, so the effect reads as one continuous
 * recession rather than three discrete states.
 */
const DEPTH = [
  { x: 0, scale: 1, opacity: 1, blur: 0, z: 40 },
  // 3px, not the 1.5 this started at. At 1.5 the neighbour was still readable —
  // and half-readable is the worst setting of the three, because you start the
  // sentence before noticing the front card has cut it off. Either a card is
  // legible or it is scenery; this one is scenery.
  { x: 62, scale: 0.88, opacity: 0.4, blur: 3, z: 30 },
  { x: 108, scale: 0.76, opacity: 0.18, blur: 5, z: 20 },
  // Anything further is the far side of the ring: parked and invisible, so it
  // fades in from the correct direction rather than appearing out of nowhere.
  { x: 134, scale: 0.7, opacity: 0, blur: 6, z: 10 },
]

type StackedDeckProps = {
  /** Each card carries its own colour — see DeckItem. */
  items: readonly DeckItem[]
  /** Names the deck for assistive technology. */
  label: string
}

export function StackedDeck({ items, label }: StackedDeckProps) {
  const [active, setActive] = useState(0)
  const cardRefs = useRef<Array<HTMLButtonElement | null>>([])
  const stageRef = useRef<HTMLDivElement>(null)

  const reducedMotion = usePrefersReducedMotion()
  /** False once the reader has touched the deck or chosen a card. Never resumes. */
  const [autoplay, setAutoplay] = useState(true)
  /** Temporary: pointer over the deck, or focus inside it. */
  const [suspended, setSuspended] = useState(false)
  const [onScreen, setOnScreen] = useState(false)

  // Only run while the section is actually being looked at.
  useEffect(() => {
    const node = stageRef.current
    if (!node) return

    // FEATURE-DETECT, and fall back to "visible" rather than to nothing.
    // Calling this unguarded threw `IntersectionObserver is not defined` in
    // jsdom and took down the homepage render test — the same guard
    // hero-molecule-background.tsx already carries, which is why that one never
    // broke. The on-screen check is an OPTIMISATION: it stops a timer running
    // for a section nobody is looking at. Losing the optimisation must not lose
    // the feature, so where the API is missing the deck simply plays.
    if (typeof IntersectionObserver === "undefined") {
      setOnScreen(true)
      return
    }

    const observer = new IntersectionObserver(
      ([entry]) => setOnScreen(entry.isIntersecting),
      { threshold: 0.4 },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  const running = autoplay && !suspended && onScreen && !reducedMotion

  useEffect(() => {
    if (!running) return
    // Advances state directly rather than through `select`, which is reserved
    // for deliberate input — routing the timer through it would have the deck
    // switch itself off on its own first tick.
    const id = window.setInterval(
      () => setActive((current) => (current + 1) % items.length),
      AUTO_ADVANCE_MS,
    )
    return () => window.clearInterval(id)
  }, [running, items.length])

  /**
   * Deliberate selection — a card, a dot, an arrow key. Always ends autoplay:
   * once a reader has said which card they want, moving it again is the single
   * most irritating thing a carousel does.
   */
  const select = useCallback((next: number, moveFocus: boolean) => {
    const wrapped = (next + items.length) % items.length
    setActive(wrapped)
    setAutoplay(false)
    if (moveFocus) cardRefs.current[wrapped]?.focus()
  }, [items.length])

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      const step: Record<string, number> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }
      if (event.key in step) {
        event.preventDefault()
        select(active + step[event.key], true)
      } else if (event.key === "Home") {
        event.preventDefault()
        select(0, true)
      } else if (event.key === "End") {
        event.preventDefault()
        select(items.length - 1, true)
      }
    },
    [active, items.length, select],
  )

  return (
    <div
      onFocus={() => setSuspended(true)}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setSuspended(false)
        }
      }}
    >
      {/* The stage. `overflow-hidden` is what lets the receding cards run past
          the content width and get clipped, which is the effect — without it
          they would widen the page instead. */}
      <div
        ref={stageRef}
        className="relative isolate flex h-[22rem] items-center justify-center overflow-hidden sm:h-[20rem]"
        onKeyDown={onKeyDown}
        // Hover and focus only SUSPEND — they do not switch autoplay off, so
        // moving the pointer away or tabbing out resumes it. Only a deliberate
        // choice is permanent.
        onMouseEnter={() => setSuspended(true)}
        onMouseLeave={() => setSuspended(false)}
        // Focus handlers live on the OUTER wrapper below, not here: the dot
        // row is outside this stage, and rule 3 says focus ANYWHERE inside
        // suspends. Handlers here left the dots running autoplay under a
        // focused control.
        // Touching the deck ANYWHERE stops it for good — this is the 2.2.2
        // mechanism, so it deliberately covers the gaps between cards and the
        // card already in front, not only the cards you might be choosing
        // between. Stopping must not require changing what you are reading.
        // pointerdown rather than click: it fires on touch without waiting to
        // see whether the gesture becomes a scroll.
        onPointerDown={() => setAutoplay(false)}
        role="group"
        aria-label={label}
      >
        {/* Light pooled behind the front card, so it sits in something rather
            than floating — and it takes the FRONT CARD'S colour, so moving
            through the deck re-tints the whole stage. That is what stops the six
            colours reading as decoration: the hue tracks what you are reading.
            Purely decorative in itself. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-1/2 -z-10 h-64 -translate-y-1/2 opacity-70 blur-3xl transition-all duration-700 motion-reduce:transition-none"
          style={{
            background: `radial-gradient(45% 60% at 50% 50%, ${items[active].soft} 0%, transparent 100%)`,
          }}
        />

        {items.map((item, index) => {
          const offset = ringOffset(index, active, items.length)
          const depth = DEPTH[Math.min(Math.abs(offset), DEPTH.length - 1)]
          const isActive = offset === 0
          const Icon = item.icon
          const hidden = depth.opacity === 0
          const { accent, ink, soft } = item

          return (
            <button
              key={item.title}
              ref={(node) => {
                cardRefs.current[index] = node
              }}
              type="button"
              // Roving tabindex: one stop for the whole deck, arrows move within.
              tabIndex={isActive ? 0 : -1}
              aria-current={isActive ? "true" : undefined}
              // Deliberately NOT aria-hidden, even though it is invisible. Being
              // on the far side of the ring is a transient property of where the
              // deck happens to be pointed, not a statement that this control is
              // not part of the section — hiding it would hand a screen reader
              // five of six enterprise controls, which is a real content loss
              // against the grid this replaced. It is unclickable by pointer and
              // untabbable, which is what "invisible" actually needs to mean.
              onClick={() => select(index, false)}
              className={cn(
                "absolute w-[min(88vw,26rem)] cursor-pointer rounded-2xl border p-6 text-left",
                // FULLY opaque. At 95% the card behind showed through the front
                // card's own paragraph — two sentences overlapping at low
                // contrast, which looked like a rendering fault rather than
                // depth. Translucency is the wrong instinct when the thing
                // behind is text.
                "bg-card transition-all duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]",
                "focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring",
                "motion-reduce:transition-none",
                isActive ? "shadow-2xl" : "shadow-sm",
                hidden && "pointer-events-none",
              )}
              style={{
                transform: `translateX(${Math.sign(offset) * depth.x}%) scale(${depth.scale})`,
                opacity: depth.opacity,
                filter: depth.blur ? `blur(${depth.blur}px)` : undefined,
                zIndex: depth.z,
                // The front card gets the accent ring; the rest stay quiet, so
                // the colour marks the subject instead of decorating everything.
                //
                // Four longhands rather than the `borderColor` shorthand. Setting
                // the shorthand alongside `borderLeftColor` makes React warn that
                // it "can lead to styling bugs" — and it means it: on re-render
                // the shorthand is removed while the longhand stays, and which
                // border you end up with depends on property order.
                borderTopColor: isActive ? accent : undefined,
                borderRightColor: isActive ? accent : undefined,
                borderBottomColor: isActive ? accent : undefined,
                borderLeftWidth: "3px",
                borderLeftColor: accent,
              }}
            >
              <div className="flex items-center gap-2.5">
                <Icon className="h-5 w-5 shrink-0" style={{ color: accent }} aria-hidden />
                <h3 className="text-base font-semibold" style={{ color: ink }}>
                  {item.title}
                </h3>
              </div>

              <span
                className="mt-3 inline-block rounded-full px-2.5 py-0.5 text-[11px] font-medium"
                style={{ backgroundColor: soft, color: ink }}
              >
                {item.pill}
              </span>

              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{item.desc}</p>
            </button>
          )
        })}
      </div>

      {/* Position, and a second way in. The cards are the obvious control, but a
          card you cannot see is not a control — these always are.

          THE BUTTON IS THE HIT AREA AND THE SPAN IS THE DOT. globals.css puts a
          2.5rem min-height on every button, which is a tap-target rule worth
          keeping — a 6px control is unhittable on a phone. Styling the button
          itself as the dot loses that argument twice over: the rule wins, so the
          dots rendered as 40px-tall bars. Splitting them gives a full-size
          target with a small mark inside, which is what both want. */}
      <div className="mt-6 flex items-center justify-center gap-1">
        {items.map((item, index) => (
          <button
            key={item.title}
            type="button"
            onClick={() => select(index, false)}
            aria-label={item.title}
            aria-current={index === active ? "true" : undefined}
            // A stable hook: "a button with no heading inside" used to identify
            // a dot, until the pause control became one too.
            data-deck-dot=""
            className="group flex w-6 items-center justify-center rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            {/* Each dot carries its own card's colour even when it is not the
                front one, so the row reads as a palette you are moving through
                rather than six identical dots and one highlight. */}
            <span
              className={cn(
                "h-1.5 rounded-full transition-all duration-300 motion-reduce:transition-none",
                index === active ? "w-6" : "w-1.5 opacity-40 group-hover:opacity-80",
              )}
              style={{ backgroundColor: item.accent }}
            />
          </button>
        ))}
      </div>
    </div>
  )
}
