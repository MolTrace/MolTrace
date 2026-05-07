import { render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { SystemStatusWorkspace } from "@/components/admin/system-status-workspace"

const mockApiFetch = vi.fn<(path: string) => Promise<unknown>>()

vi.mock("@/components/app/backend-status-indicator", () => ({
  BackendStatusIndicator: () => <span>Backend status</span>,
}))

vi.mock("@/lib/api/client", () => ({
  ApiError: class MockApiError extends Error {
    data?: unknown
    constructor(message: string, data?: unknown) {
      super(message)
      this.data = data
    }
  },
  apiFetch: (path: string) => mockApiFetch(path),
}))

describe("SystemStatusWorkspace connector health fallback", () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
    mockApiFetch.mockRejectedValue(new Error("backend unavailable"))
  })

  it("shows connector health backend unavailable message", async () => {
    render(<SystemStatusWorkspace />)

    await waitFor(() => {
      expect(screen.getAllByText("Connector health").length).toBeGreaterThan(0)
      expect(screen.getByText("Connector health unavailable — current admin system content continues.")).toBeInTheDocument()
    })
  })
})
