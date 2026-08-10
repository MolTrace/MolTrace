import { act, fireEvent, render, screen, within } from "@testing-library/react"
import { FileCheck, KeyRound, Lock, PackageCheck, ShieldCheck, Users } from "lucide-react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { StackedDeck, ringOffset, type DeckItem } from "./stacked-deck"

/**
 * These assert the two things a deck can silently get wrong.
 *
 * The first is the ring: with an even card count the far side is ambiguous, and
 * an off-by-one there parks a card on the wrong flank so it slides in from the
 * direction it just left.
 *
 * The second is that the depth is PRESENTATION. A carousel that drops content
 * from the accessibility tree, or that leaves six tab stops behind to change
 * which card is in front, is a worse page than the grid it replaced — and
 * neither failure is visible in a screenshot.
 */

/** Distinct colours per card, so a swapped role shows up as a wrong hex. */
const COLOURS = [
  { accent: "#6B3FE0", ink: "#5B3FB8", soft: "rgba(107,63,224,0.1)" },
  { accent: "#00B8D9", ink: "#0B6E8C", soft: "rgba(0,184,217,0.1)" },
  { accent: "#00DFA0", ink: "#0B6E5A", soft: "rgba(0,223,160,0.1)" },
  { accent: "#E8A030", ink: "#8F5C00", soft: "rgba(232,160,48,0.1)" },
  { accent: "#22C55E", ink: "#15803D", soft: "rgba(34,197,94,0.1)" },
  { accent: "#64748B", ink: "#475569", soft: "rgba(100,116,139,0.1)" },
]

const ITEMS: DeckItem[] = [
  { icon: Users, title: "Alpha", pill: "A", desc: "first", ...COLOURS[0] },
  { icon: FileCheck, title: "Bravo", pill: "B", desc: "second", ...COLOURS[1] },
  { icon: Lock, title: "Charlie", pill: "C", desc: "third", ...COLOURS[2] },
  { icon: KeyRound, title: "Delta", pill: "D", desc: "fourth", ...COLOURS[3] },
  { icon: ShieldCheck, title: "Echo", pill: "E", desc: "fifth", ...COLOURS[4] },
  { icon: PackageCheck, title: "Foxtrot", pill: "F", desc: "sixth", ...COLOURS[5] },
]

/** jsdom has no matchMedia; the deck reads it for prefers-reduced-motion. */
function stubMatchMedia(reduced: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduced && query.includes("prefers-reduced-motion"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }))
}

/** The deck only advances while on screen, which needs a real observer here. */
function stubIntersectionObserver(intersecting: boolean) {
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(private cb: (e: Array<{ isIntersecting: boolean }>) => void) {}
      observe() {
        this.cb([{ isIntersecting: intersecting }])
      }
      disconnect() {}
    },
  )
}

beforeEach(() => {
  stubMatchMedia(false)
  stubIntersectionObserver(true)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

function renderDeck() {
  const view = render(<StackedDeck items={ITEMS} label="Test deck" />)
  const stage = screen.getByRole("group", { name: "Test deck" })
  const cards = () => Array.from(stage.querySelectorAll<HTMLButtonElement>(":scope > button"))
  const activeTitle = () =>
    cards().find((c) => c.getAttribute("aria-current") === "true")?.querySelector("h3")?.textContent
  return { ...view, stage, cards, activeTitle }
}

describe("ringOffset", () => {
  it("walks the shorter way round, so cards recede on the nearer flank", () => {
    // Active 0 of 6: forward, two to the right, the far side, two to the left.
    expect([0, 1, 2, 3, 4, 5].map((i) => ringOffset(i, 0, 6))).toEqual([0, 1, 2, 3, -2, -1])
  })

  it("keeps the same shape once the active card is not the first", () => {
    expect([0, 1, 2, 3, 4, 5].map((i) => ringOffset(i, 3, 6))).toEqual([3, -2, -1, 0, 1, 2])
  })

  it("puts the far card on exactly one flank, never both", () => {
    // With an even count the antipode could go either way; it must be decided,
    // or the card crosses the deck instead of fading where it stands.
    for (let active = 0; active < 6; active++) {
      const offsets = [0, 1, 2, 3, 4, 5].map((i) => ringOffset(i, active, 6))
      expect(offsets.filter((o) => Math.abs(o) === 3)).toHaveLength(1)
      expect(new Set(offsets).size).toBe(6)
    }
  })
})

describe("StackedDeck", () => {
  it("starts with the first card forward", () => {
    const { activeTitle, cards } = renderDeck()
    expect(activeTitle()).toBe("Alpha")
    expect(cards()[0].style.opacity).toBe("1")
    expect(cards()[0].style.transform).toContain("translateX(0%)")
  })

  it("brings a card forward when it is clicked", () => {
    const { cards, activeTitle } = renderDeck()
    fireEvent.click(cards()[2])
    expect(activeTitle()).toBe("Charlie")
    expect(cards()[2].style.opacity).toBe("1")
    // ...and the one that was forward has stepped back rather than vanished.
    expect(Number(cards()[0].style.opacity)).toBeGreaterThan(0)
    expect(Number(cards()[0].style.opacity)).toBeLessThan(1)
  })

  it("recedes cards symmetrically either side of the front", () => {
    const { cards } = renderDeck()
    fireEvent.click(cards()[2])
    const opacity = (i: number) => Number(cards()[i].style.opacity)
    expect(opacity(1)).toBe(opacity(3)) // one step out, both flanks
    expect(opacity(0)).toBe(opacity(4)) // two steps out
    expect(opacity(1)).toBeGreaterThan(opacity(0)) // and it falls off monotonically
  })

  it("moves with arrow keys and wraps at both ends", () => {
    const { stage, activeTitle } = renderDeck()
    fireEvent.keyDown(stage, { key: "ArrowRight" })
    expect(activeTitle()).toBe("Bravo")
    fireEvent.keyDown(stage, { key: "ArrowLeft" })
    fireEvent.keyDown(stage, { key: "ArrowLeft" })
    // Past the first card, round to the last rather than dead-stopping.
    expect(activeTitle()).toBe("Foxtrot")
  })

  it("jumps to the ends with Home and End", () => {
    const { stage, activeTitle } = renderDeck()
    fireEvent.keyDown(stage, { key: "End" })
    expect(activeTitle()).toBe("Foxtrot")
    fireEvent.keyDown(stage, { key: "Home" })
    expect(activeTitle()).toBe("Alpha")
  })

  it("offers the deck as ONE tab stop, not six", () => {
    // Six stops that only change which card is in front is noise for a keyboard
    // user. The arrows above are how you move inside it.
    const { cards } = renderDeck()
    expect(cards().filter((c) => c.tabIndex === 0)).toHaveLength(1)
    fireEvent.click(cards()[4])
    const tabbable = cards().filter((c) => c.tabIndex === 0)
    expect(tabbable).toHaveLength(1)
    expect(tabbable[0].getAttribute("aria-current")).toBe("true")
  })

  it("keeps every card readable, however far back it is", () => {
    // The depth is presentation. A screen reader should get all six regardless
    // of which one is visually forward — otherwise this loses five sixths of the
    // section's content against the grid it replaced.
    const { activeTitle } = renderDeck()
    expect(activeTitle()).toBe("Alpha")
    for (const item of ITEMS) {
      expect(screen.getByRole("heading", { name: item.title })).toBeInTheDocument()
      expect(screen.getByText(item.desc)).toBeInTheDocument()
    }
  })

  it("does not leave the invisible card clickable, but keeps it announced", () => {
    // It is at opacity 0 on the far side of the ring, so a pointer must not land
    // on it and it must not be a tab stop. It is NOT aria-hidden: being on the
    // far side is a property of where the deck is pointed right now, not a claim
    // that the control is not part of the section.
    const { cards } = renderDeck()
    const far = cards().find((c) => c.style.opacity === "0")
    expect(far).toBeDefined()
    expect(far!.className).toContain("pointer-events-none")
    expect(far!.tabIndex).toBe(-1)
    expect(far!.getAttribute("aria-hidden")).toBeNull()
  })

  it("gives every dot an accessible name, so the control row is not six blanks", () => {
    const { container } = renderDeck()
    const dots = Array.from(container.querySelectorAll("[data-deck-dot]"))
    expect(dots).toHaveLength(ITEMS.length)
    expect(dots.map((d) => d.getAttribute("aria-label"))).toEqual(ITEMS.map((i) => i.title))
  })

  it("tracks the front card from the dots too", () => {
    const { container, activeTitle } = renderDeck()
    const dots = Array.from(container.querySelectorAll<HTMLButtonElement>("[data-deck-dot]"))
    fireEvent.click(dots[5])
    expect(activeTitle()).toBe("Foxtrot")
    expect(dots[5].getAttribute("aria-current")).toBe("true")
    expect(dots[0].getAttribute("aria-current")).toBeNull()
  })

  it("colours type with the AA-safe ink, never the vivid accent", () => {
    // The vivid tokens sit at 2-3:1 as text and fail AA; they are for rules and
    // icons. Swapping them is an easy and invisible regression.
    const { stage } = renderDeck()
    const front = stage.querySelector<HTMLButtonElement>(":scope > button")!
    expect(within(front).getByRole("heading", { name: "Alpha" })).toHaveStyle({ color: COLOURS[0].ink })
    expect(front.querySelector("svg")).toHaveStyle({ color: COLOURS[0].accent })
  })

  it("advances on its own", () => {
    vi.useFakeTimers()
    const { activeTitle } = renderDeck()
    expect(activeTitle()).toBe("Alpha")
    act(() => void vi.advanceTimersByTime(6500))
    expect(activeTitle()).toBe("Bravo")
    act(() => void vi.advanceTimersByTime(6500))
    expect(activeTitle()).toBe("Charlie")
  })

  it("wraps round rather than stopping at the last card", () => {
    vi.useFakeTimers()
    const { activeTitle } = renderDeck()
    act(() => void vi.advanceTimersByTime(6500 * 6))
    expect(activeTitle()).toBe("Alpha")
  })

  it("stops for good once the reader picks a card", () => {
    // The single most irritating carousel behaviour is moving the card away
    // after someone has chosen it.
    vi.useFakeTimers()
    const { cards, activeTitle } = renderDeck()
    fireEvent.click(cards()[4])
    expect(activeTitle()).toBe("Echo")
    act(() => void vi.advanceTimersByTime(6500 * 3))
    expect(activeTitle()).toBe("Echo")
  })

  it("stops for good on an arrow key too, not just a click", () => {
    vi.useFakeTimers()
    const { stage, activeTitle } = renderDeck()
    fireEvent.keyDown(stage, { key: "ArrowRight" })
    expect(activeTitle()).toBe("Bravo")

    // Blur FIRST. Arrowing moves focus onto the newly-front card, which
    // suspends autoplay all by itself — without this line the test passes
    // whether or not selection stops autoplay permanently, which is the wrong
    // reason to be green. Mutation-checked: removing setAutoplay(false) must
    // fail this test as well as the click one.
    fireEvent.blur(stage)
    act(() => void vi.advanceTimersByTime(6500 * 2))
    expect(activeTitle()).toBe("Bravo")
  })

  it("pauses while hovered, and resumes when the pointer leaves", () => {
    vi.useFakeTimers()
    const { stage, activeTitle } = renderDeck()
    fireEvent.mouseEnter(stage)
    act(() => void vi.advanceTimersByTime(6500 * 2))
    expect(activeTitle()).toBe("Alpha") // held still under the pointer
    fireEvent.mouseLeave(stage)
    act(() => void vi.advanceTimersByTime(6500))
    expect(activeTitle()).toBe("Bravo") // ...and picks up again
  })

  it("stops on a tap anywhere, WITHOUT changing which card is shown", () => {
    // This is the WCAG 2.2.2 mechanism now that there is no play/pause button,
    // so it has to work on the empty stage and on the front card — not only on
    // the cards you would be choosing between. Being forced to change what you
    // are reading in order to stop it is not a way to stop it.
    vi.useFakeTimers()
    const { stage, activeTitle } = renderDeck()
    fireEvent.pointerDown(stage)
    fireEvent.mouseLeave(stage) // rule out hover doing the work
    act(() => void vi.advanceTimersByTime(6500 * 3))
    expect(activeTitle()).toBe("Alpha")
  })

  it("stops when the card already in front is tapped", () => {
    // Fires both events, because a real tap does. That means this one passes
    // via `select` even if pointerDown were removed — the test above is the one
    // that isolates the pointerDown path. What this asserts is the end-to-end
    // gesture: tapping what you are already reading stops the deck and leaves
    // it exactly where it was.
    vi.useFakeTimers()
    const { cards, activeTitle } = renderDeck()
    fireEvent.pointerDown(cards()[0])
    fireEvent.click(cards()[0])
    fireEvent.mouseLeave(screen.getByRole("group", { name: "Test deck" }))
    act(() => void vi.advanceTimersByTime(6500 * 3))
    expect(activeTitle()).toBe("Alpha")
  })

  it("has no play/pause control", () => {
    // Removed deliberately — the tap mechanism above replaces it. Asserted so
    // the two decisions cannot silently drift apart.
    renderDeck()
    expect(screen.queryByRole("button", { name: /^(Pause|Play) / })).toBeNull()
  })

  it("never starts under prefers-reduced-motion", () => {
    vi.useFakeTimers()
    stubMatchMedia(true)
    const { activeTitle } = renderDeck()
    act(() => void vi.advanceTimersByTime(6500 * 4))
    expect(activeTitle()).toBe("Alpha")
  })

  it("does not advance while the deck is off screen", () => {
    // Otherwise a reader scrolling down arrives at whichever card a timer
    // wandered to while the section was three screens away.
    vi.useFakeTimers()
    stubIntersectionObserver(false)
    const { activeTitle } = renderDeck()
    act(() => void vi.advanceTimersByTime(6500 * 4))
    expect(activeTitle()).toBe("Alpha")
  })

  it("gives every card its own colour rather than one shared accent", () => {
    // The whole point of the change: six families, not six shades of cyan.
    const { cards } = renderDeck()
    const rules = cards().map((c) => c.style.borderLeftColor)
    expect(new Set(rules).size).toBe(ITEMS.length)
  })

  it("keeps each card's ink paired with its own accent", () => {
    // A mis-paired row — card 3's hue with card 4's ink — is invisible in a
    // screenshot and is exactly what a hand-maintained colour list gets wrong.
    const { cards } = renderDeck()
    cards().forEach((card, i) => {
      expect(card.querySelector("h3")).toHaveStyle({ color: COLOURS[i].ink })
      expect(card.querySelector("svg")).toHaveStyle({ color: COLOURS[i].accent })
    })
  })
})
