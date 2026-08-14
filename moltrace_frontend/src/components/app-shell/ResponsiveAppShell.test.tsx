import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ResponsiveAppShell } from "@/src/components/app-shell/ResponsiveAppShell"

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  // The shell now wraps its children in ModuleRouteGuard, which reads the current path to decide
  // whether the route belongs to a product this deployment serves. A shared path keeps these
  // shell-mode tests about layout rather than about gating.
  usePathname: () => "/dashboard",
}))

/** Records the `collapsed` value on EVERY render, so a test can assert what the
 *  FIRST render after a remount looked like. Asserting the settled DOM cannot:
 *  RTL flushes effects inside `render`, so the corrected value is already in
 *  place by the time it returns — which is exactly the frame the reader sees
 *  and the test would not. */
const sidebarRenders = vi.hoisted(() => [] as boolean[])

vi.mock("@/components/app/app-sidebar", () => ({
  AppSidebar: ({ collapsed }: { collapsed: boolean }) => {
    sidebarRenders.push(collapsed)
    return <aside data-testid="desktop-sidebar" data-collapsed={String(collapsed)} />
  },
}))

vi.mock("@/components/app/app-topbar", () => ({
  AppTopbar: ({ onToggleEvidenceQueue }: { onToggleEvidenceQueue: () => void }) => (
    <header data-testid="app-topbar">
      <button type="button" onClick={onToggleEvidenceQueue}>
        Toggle AI Evidence Queue
      </button>
    </header>
  ),
}))

vi.mock("@/components/app/ai-evidence-queue", () => ({
  AIEvidenceQueue: () => <aside data-testid="evidence-queue" />,
}))

vi.mock("@/src/components/app-shell/AIEvidenceQueueSheet", () => ({
  AIEvidenceQueueSheet: ({ open }: { open: boolean }) =>
    open ? <div data-testid="evidence-queue-sheet" /> : null,
}))

vi.mock("@/components/app/overview-data-context", () => ({
  OverviewDataProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

vi.mock("@/src/components/app-shell/MobileBottomNav", () => ({
  MobileBottomNav: () => <nav aria-label="Mobile bottom navigation" />,
}))

vi.mock("@/src/lib/tenant/tenant-context", () => ({
  TenantProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

function installViewport({
  width,
  coarsePointer,
  noHover,
  touchPoints = coarsePointer ? 5 : 0,
  platform = coarsePointer ? "iPhone" : "Win32",
  userAgent = coarsePointer
    ? "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148"
    : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}: {
  width: number
  coarsePointer: boolean
  noHover: boolean
  touchPoints?: number
  platform?: string
  userAgent?: string
}) {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width })
  Object.defineProperty(window.navigator, "platform", { configurable: true, value: platform })
  Object.defineProperty(window.navigator, "userAgent", { configurable: true, value: userAgent })
  Object.defineProperty(window.navigator, "maxTouchPoints", {
    configurable: true,
    value: touchPoints,
  })

  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn((query: string) => {
      // The shell asks for `(min-width: 1024px)` to decide whether there is room
      // to dock the evidence panel, so the mock has to answer width queries in
      // both directions rather than defaulting everything else to false.
      const minWidth = /\(min-width:\s*(\d+)px\)/.exec(query)
      const maxWidth = /\(max-width:\s*(\d+)px\)/.exec(query)
      const matches = minWidth
        ? width >= Number(minWidth[1])
        : maxWidth
          ? width <= Number(maxWidth[1])
          : query === "(pointer: coarse)"
            ? coarsePointer
            : query === "(hover: none)"
              ? noHover
              : false

      return {
        matches,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }
    }),
  })
}

describe("ResponsiveAppShell shell mode", () => {
  beforeEach(() => {
    installViewport({ width: 1200, coarsePointer: false, noHover: false })
    // The shell persists panel/sidebar choices, so one test's dismissal would
    // otherwise carry into the next.
    window.localStorage.clear()
  })

  it("keeps the desktop shell for a narrow desktop window", () => {
    installViewport({ width: 500, coarsePointer: false, noHover: false })

    render(
      <ResponsiveAppShell>
        <div>Content</div>
      </ResponsiveAppShell>,
    )

    expect(screen.getByTestId("desktop-sidebar")).toBeInTheDocument()
    expect(screen.getByTestId("evidence-queue")).toBeInTheDocument()
    expect(screen.queryByLabelText("Mobile bottom navigation")).not.toBeInTheDocument()
  })

  it("uses the mobile shell for narrow coarse-pointer devices", async () => {
    installViewport({ width: 500, coarsePointer: true, noHover: true })

    render(
      <ResponsiveAppShell>
        <div>Content</div>
      </ResponsiveAppShell>,
    )

    await waitFor(() => {
      expect(screen.getByLabelText("Mobile bottom navigation")).toBeInTheDocument()
    })
    expect(screen.queryByTestId("desktop-sidebar")).not.toBeInTheDocument()
    // The 320px docked slab still has no place on a phone — but see the next
    // test: the queue is now reachable there as a sheet. This assertion used to
    // be the whole story, which is what made the mobile AI Queue button dead.
    expect(screen.queryByTestId("evidence-queue")).not.toBeInTheDocument()
  })

  it("opens the evidence queue as a sheet when a phone taps the topbar control", async () => {
    installViewport({ width: 500, coarsePointer: true, noHover: true })
    const user = userEvent.setup()

    render(
      <ResponsiveAppShell>
        <div>Content</div>
      </ResponsiveAppShell>,
    )

    await waitFor(() => {
      expect(screen.getByLabelText("Mobile bottom navigation")).toBeInTheDocument()
    })
    // Closed until asked for: the shell remounts on every navigation, so a sheet
    // that defaulted open would cover the page on each nav tap.
    expect(screen.queryByTestId("evidence-queue-sheet")).not.toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /Toggle AI Evidence Queue/i }))
    expect(screen.getByTestId("evidence-queue-sheet")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /Toggle AI Evidence Queue/i }))
    expect(screen.queryByTestId("evidence-queue-sheet")).not.toBeInTheDocument()
  })

  it("remembers a dismissed desktop panel across a remount", async () => {
    installViewport({ width: 1200, coarsePointer: false, noHover: false })
    const user = userEvent.setup()

    const first = render(
      <ResponsiveAppShell>
        <div>Content</div>
      </ResponsiveAppShell>,
    )
    expect(screen.getByTestId("evidence-queue")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /Toggle AI Evidence Queue/i }))
    await waitFor(() => {
      expect(screen.queryByTestId("evidence-queue")).not.toBeInTheDocument()
    })
    first.unmount()

    render(
      <ResponsiveAppShell>
        <div>Content</div>
      </ResponsiveAppShell>,
    )
    await waitFor(() => {
      expect(screen.queryByTestId("evidence-queue")).not.toBeInTheDocument()
    })
  })
})

/**
 * THE SHELL REMOUNTS ON EVERY NAVIGATION — it is rendered by each page rather
 * than by a layout. Its panel states default to "expanded"/"open" and were
 * corrected in an effect after mount, so that correction replayed on every
 * route change: with the sidebar collapsed, each navigation rendered it at its
 * full 224px and animated back to 56px, jerking the page 168px sideways and
 * back. Measured in a browser across one navigation: 56 -> 224 -> 56.
 *
 * The defaults are still right for the FIRST render of a document, because they
 * are what the server sent and reading storage during render would hydrate into
 * a mismatch. A module-level cache separates the two cases.
 */
describe("ResponsiveAppShell — remount does not replay the layout", () => {
  it("first render of a document matches the server, then corrects", async () => {
    window.localStorage.setItem("moltrace:shell:sidebar-collapsed", "1")
    sidebarRenders.length = 0

    render(<ResponsiveAppShell>content</ResponsiveAppShell>)

    // The very first render must be the SERVER's value, or hydration mismatches.
    expect(sidebarRenders[0]).toBe(false)
    // ...and the stored preference is applied straight after.
    await waitFor(() =>
      expect(screen.getByTestId("desktop-sidebar")).toHaveAttribute("data-collapsed", "true"),
    )
  })

  it("a remount starts collapsed, with no expanded frame at all", async () => {
    window.localStorage.setItem("moltrace:shell:sidebar-collapsed", "1")

    // Prime the cache the way the first page load does.
    const first = render(<ResponsiveAppShell>content</ResponsiveAppShell>)
    await waitFor(() =>
      expect(screen.getByTestId("desktop-sidebar")).toHaveAttribute("data-collapsed", "true"),
    )
    first.unmount()

    // The remount every navigation causes.
    sidebarRenders.length = 0
    render(<ResponsiveAppShell>content</ResponsiveAppShell>)

    // The point of the fix: not "ends up collapsed" but "was never anything
    // else". A single `false` here is one painted frame of a 224px sidebar.
    expect(sidebarRenders).not.toContain(false)
    expect(sidebarRenders[0]).toBe(true)
  })
})
