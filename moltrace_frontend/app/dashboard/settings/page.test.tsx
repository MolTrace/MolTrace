import { describe, expect, it, vi } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"

import SettingsPage from "@/app/dashboard/settings/page"

// The connector/instrument/mapping/MFA workspaces each talk to the API on mount.
// Only the default ("Profile") tab panel mounts under Radix Tabs, but stub them
// anyway so this stays a layout test.
vi.mock("@/components/settings/connectors-center-workspace", () => ({
  ConnectorsCenterWorkspace: () => <div />,
}))
vi.mock("@/components/settings/mfa-management-workspace", () => ({
  MfaManagementWorkspace: () => <div />,
}))
vi.mock("@/components/settings/instrument-watch-folder-workspace", () => ({
  InstrumentWatchFolderWorkspace: () => <div />,
}))
vi.mock("@/components/settings/mapping-templates-workspace", () => ({
  MappingTemplatesWorkspace: () => <div />,
}))
vi.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children?: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}))

const SETTINGS_TABS = ["Profile", "Notifications", "Security", "API", "Organization", "Connectors"]

describe("Settings page tab strip", () => {
  it("renders every settings tab", () => {
    render(<SettingsPage />)
    for (const label of SETTINGS_TABS) {
      expect(screen.getByRole("tab", { name: label })).toBeInTheDocument()
    }
  })

  // Regression guard for the mobile bug: the default TabsList is a fixed-height
  // `w-fit` row with no overflow handling, so six icon+label triggers spilled
  // outside the container on a phone — the trailing tabs were clipped with no
  // way to scroll or drag to them. Wrapping keeps all of them reachable.
  it("lets the tab strip wrap instead of overflowing its container", () => {
    render(<SettingsPage />)
    const lists = screen.getAllByRole("tablist")
    expect(lists.length).toBeGreaterThan(0)

    for (const list of lists) {
      expect(list.className).toContain("flex-wrap")
      expect(list.className).toContain("w-full")
      // `h-9` would pin the strip to a single row's height and clip the
      // wrapped rows.
      expect(list.className).toContain("h-auto")
      expect(list.className).not.toMatch(/\bw-fit\b/)
    }
  })

  it("applies the same treatment to the nested Connectors strip", async () => {
    render(<SettingsPage />)
    // Radix only mounts the active panel, so the nested strip has to be opened.
    // Tabs activate on mousedown (plus focus in automatic activation mode), not
    // on a synthesized click.
    const connectorsTab = screen.getByRole("tab", { name: "Connectors" })
    fireEvent.mouseDown(connectorsTab)
    fireEvent.focus(connectorsTab)

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: "Connector Center" })).toBeInTheDocument()
    })
    const nested = screen.getByRole("tab", { name: "Connector Center" }).closest('[role="tablist"]')
    expect(nested?.className).toContain("flex-wrap")
    expect(nested?.className).toContain("w-full")
    expect(nested?.className).toContain("h-auto")
  })
})
