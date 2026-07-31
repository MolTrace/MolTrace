import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ResponsiveAppShell } from "@/src/components/app-shell/ResponsiveAppShell"

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}))

vi.mock("@/components/app/app-sidebar", () => ({
  AppSidebar: () => <aside data-testid="desktop-sidebar" />,
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
