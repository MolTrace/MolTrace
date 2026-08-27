import { afterEach, beforeEach } from "vitest"
import { configure } from "@testing-library/react"
import "@testing-library/jest-dom/vitest"

/**
 * How long a `waitFor` / `findBy*` may wait for the DOM to catch up.
 *
 * Testing Library's 1000ms default is a second budget denominated in wall-clock,
 * next to Vitest's `testTimeout`, and it fails the same way: `--run` forks
 * `availableParallelism() - 1` workers, so a component that mounts in well under
 * a second alone takes several inside a full suite. It is the constraint that
 * survives once `testTimeout` is sized properly — `app/spectracheck/page.test.tsx`
 * kept failing on "Unable to find role=button and name /Drop raw FID archive/i"
 * with the per-test budget nowhere near spent.
 *
 * 5510ms = 923ms x 5.97. 923ms is the uncontended cost of the heaviest
 * render-then-wait test in the suite (reaction-optimization-render's "Reaction
 * Project Detail", measured running alone); 5.97 is the worst inflation measured
 * between running alone and running in a full suite (785ms -> 4689.4ms). A single
 * wait cannot outlast the test that contains it, so this bounds every wait here —
 * it clears the longest whole test ever recorded (4689.4ms) — while staying well
 * under `testTimeout`, so a real miss still reports WHICH element never arrived
 * instead of an anonymous "Test timed out".
 *
 * A test needing longer than this says so at its own call site, and says why.
 */
configure({ asyncUtilTimeout: 5510 })

class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

globalThis.ResizeObserver =
  globalThis.ResizeObserver ?? (ResizeObserverStub as unknown as typeof ResizeObserver)

// jsdom does not implement Element.prototype.scrollTo; some scroll-snap
// components (e.g. the spectrum carousel) call it from mount effects. Stub a
// no-op so those components can mount under test without throwing.
if (typeof Element !== "undefined" && typeof Element.prototype.scrollTo !== "function") {
  Element.prototype.scrollTo = function scrollTo() {}
}

// Radix Select drives its trigger through the Pointer Events capture API and
// scrolls the active item into view. jsdom implements neither, so opening a
// <Select> under test throws before the listbox ever renders.
if (typeof Element !== "undefined") {
  if (typeof Element.prototype.hasPointerCapture !== "function") {
    Element.prototype.hasPointerCapture = function hasPointerCapture() {
      return false
    }
  }
  if (typeof Element.prototype.setPointerCapture !== "function") {
    Element.prototype.setPointerCapture = function setPointerCapture() {}
  }
  if (typeof Element.prototype.releasePointerCapture !== "function") {
    Element.prototype.releasePointerCapture = function releasePointerCapture() {}
  }
  if (typeof Element.prototype.scrollIntoView !== "function") {
    Element.prototype.scrollIntoView = function scrollIntoView() {}
  }
}

// Several responsive client components read matchMedia in effects; jsdom
// does not provide it by default.
if (typeof window !== "undefined" && typeof window.matchMedia !== "function") {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
      dispatchEvent() {
        return false
      },
    }),
  })
}

function createMemoryStorage(): Storage {
  const store = new Map<string, string>()

  return {
    get length() {
      return store.size
    },
    clear() {
      store.clear()
    },
    getItem(key: string) {
      return store.get(key) ?? null
    },
    key(index: number) {
      return Array.from(store.keys())[index] ?? null
    },
    removeItem(key: string) {
      store.delete(key)
    },
    setItem(key: string, value: string) {
      store.set(key, value)
    },
  }
}

if (typeof window !== "undefined" && typeof window.localStorage?.getItem !== "function") {
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: createMemoryStorage(),
  })
}

// ---------------------------------------------------------------- console gate

/**
 * Fail a test that logs an unexpected console.error or console.warn.
 *
 * Without this a component can log an error on every render and the suite stays
 * green, so the noise accumulates until the console is useless for finding the
 * real failure. The gate is cheap and it protects everything built after it.
 *
 * Opt a test out with `allowConsole()` — no arguments allows both levels, or
 * name the ones you expect. That is deliberately per-test and must be called
 * INSIDE the test: a suite that asserts on an error path has a real reason to
 * log, and should say so at the point where it does, not once at the top of a
 * file where it also covers thirty tests that have no such reason.
 */
type ConsoleLevel = "error" | "warn"

/**
 * MIGRATION CARVE-OUT, to be deleted.
 *
 * Turning the gate on surfaced 37 violations. Exactly one was a product defect —
 * two dialogs in the regulatory action queue with no accessible description,
 * fixed in the same change. The other 36 are React's "not wrapped in act(...)"
 * warning across 12 test files, which says the TEST is racing the component, not
 * that the component is broken.
 *
 * Those 36 are ignored here rather than silenced with `allowConsole()` scattered
 * through a dozen files, for one reason: an opt-out inside a test disables the
 * gate for that whole test, so a real error logged beside the act warning would
 * go with it. One narrow pattern match keeps every other message failing
 * everywhere, and keeps the backlog countable — grep this constant to find it.
 *
 * Fixing them means awaiting the state update the test triggers. Delete this
 * once that is done; nothing else should ever be added to it.
 */
const MIGRATION_IGNORED = [/not wrapped in act\(/]

const consoleGate = {
  captured: [] as { level: ConsoleLevel; text: string }[],
  allowed: new Set<ConsoleLevel>(),
  original: {} as Partial<Record<ConsoleLevel, (...args: unknown[]) => void>>,
}

export function allowConsole(...levels: ConsoleLevel[]): void {
  const chosen = levels.length > 0 ? levels : (["error", "warn"] as ConsoleLevel[])
  for (const level of chosen) consoleGate.allowed.add(level)
}

beforeEach(() => {
  consoleGate.captured.length = 0
  consoleGate.allowed.clear()
  for (const level of ["error", "warn"] as ConsoleLevel[]) {
    consoleGate.original[level] = console[level] as (...args: unknown[]) => void
    console[level] = (...args: unknown[]) => {
      consoleGate.captured.push({ level, text: args.map((a) => String(a)).join(" ") })
      // Still print it. Swallowing the message would make a failing gate harder
      // to diagnose than the noise it exists to prevent.
      consoleGate.original[level]?.(...args)
    }
  }
})

afterEach(() => {
  for (const level of ["error", "warn"] as ConsoleLevel[]) {
    const original = consoleGate.original[level]
    if (original) console[level] = original
  }
  const unexpected = consoleGate.captured.filter(
    (c) => !consoleGate.allowed.has(c.level) && !MIGRATION_IGNORED.some((re) => re.test(c.text)),
  )
  if (unexpected.length === 0) return
  const lines = unexpected.slice(0, 5).map((c) => `  ${c.level}: ${c.text.slice(0, 200)}`)
  const more = unexpected.length > 5 ? `\n  …and ${unexpected.length - 5} more` : ""
  throw new Error(
    `Unexpected console output (${unexpected.length}).\n${lines.join("\n")}${more}\n` +
      `If this test asserts on an error path, call allowConsole("error") inside it.`,
  )
})
