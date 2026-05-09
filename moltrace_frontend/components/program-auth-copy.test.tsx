import { render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError, apiFetch } from "@/lib/api/client"
import { RegulatoryIntelligenceLanding } from "@/components/regulatory-hub/regulatory-intelligence-landing"
import { ReactionOptimizationLanding } from "@/components/reaction-optimization/reaction-optimization-landing"

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}))

vi.mock("@/lib/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/client")>("@/lib/api/client")
  return {
    ...actual,
    apiFetch: vi.fn(),
  }
})

vi.mock("@/src/lib/analytics/analytics-client", () => ({
  trackRegulatoryDossierCreated: vi.fn(),
  trackReactionProjectCreated: vi.fn(),
}))

const OLD_AUTH_COPY = "Sign in to continue. If you already signed in, your session may have expired."
const LIVE_DATA_AUTH_COPY = "Sign in to access live MolTrace data."

const mockedApiFetch = vi.mocked(apiFetch)

beforeEach(() => {
  mockedApiFetch.mockRejectedValue(
    new ApiError(401, { detail: OLD_AUTH_COPY }, OLD_AUTH_COPY)
  )
})

afterEach(() => {
  vi.clearAllMocks()
})

describe("program auth copy", () => {
  it("uses sanitized auth copy on Regulatory Hub backend failures", async () => {
    render(<RegulatoryIntelligenceLanding />)

    expect((await screen.findAllByText(LIVE_DATA_AUTH_COPY)).length).toBeGreaterThan(0)
    await waitFor(() => {
      expect(screen.queryByText(OLD_AUTH_COPY)).not.toBeInTheDocument()
    })
  })

  it("uses sanitized auth copy on Reaction Optimization backend failures", async () => {
    render(<ReactionOptimizationLanding />)

    expect(await screen.findByText(LIVE_DATA_AUTH_COPY)).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByText(OLD_AUTH_COPY)).not.toBeInTheDocument()
    })
  })
})
