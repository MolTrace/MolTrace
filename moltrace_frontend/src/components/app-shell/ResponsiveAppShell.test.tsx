import { render, screen, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ResponsiveAppShell } from "@/src/components/app-shell/ResponsiveAppShell"

vi.mock("@/components/app/app-sidebar", () => ({
  AppSidebar: () => <aside data-testid="desktop-sidebar" />,
}))

vi.mock("@/components/app/app-topbar", () => ({
  AppTopbar: () => <header data-testid="app-topbar" />,
}))

vi.mock("@/components/app/ai-evidence-queue", () => ({
  AIEvidenceQueue: () => <aside data-testid="evidence-queue" />,
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
      const matches =
        query.includes("max-width")
          ? width < 768
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
    expect(screen.queryByTestId("evidence-queue")).not.toBeInTheDocument()
  })
})
