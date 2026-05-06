/**
 * Route composition regression: `/dashboard` still mounts `DashboardV0` beneath the dashboard layout.
 * This is not screenshot/visual-diff coverage; adopt Playwright + baseline images if pixel-parity QA is required.
 */
import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import DashboardLayout from "@/app/dashboard/layout"
import DashboardPage from "@/app/dashboard/page"

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock("@/components/app/backend-status-indicator", () => ({
  BackendStatusIndicator: () => <span>Backend connected</span>,
}))

describe("dashboard page", () => {
  it("renders MolTrace app shell branding and metric cards", () => {
    render(
      <DashboardLayout>
        <DashboardPage />
      </DashboardLayout>
    )

    expect(
      screen.getAllByText((_, node) => (node?.textContent || "").replace(/\s+/g, "") === "MolTrace")[0]
    ).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument()
    expect(screen.getByText("Active Analyses")).toBeInTheDocument()
    expect(screen.getByText("Review Required")).toBeInTheDocument()
  })
})
