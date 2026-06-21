import { render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ProgramsInterfaceWorkspace } from "@/components/programs/programs-interface-workspace"
import { clearSpectraCheckTabStatePersistence } from "@/components/spectracheck/spectracheck-tab-state-context"
import { apiFetch } from "@/lib/api/client"
import { invalidateSpectraCheckSessionReadCache } from "@/src/lib/spectracheck/spectracheck-evidence-session"
import { clearSpectraCheckRuntimeState } from "@/src/lib/spectracheck/spectracheck-runtime-reset"

vi.mock("next/navigation", () => ({
  usePathname: () => "/spectracheck",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))

vi.mock("@/hooks/use-mobile", () => ({
  useIsMobile: () => false,
}))

vi.mock("@/components/ai/ai-module-prediction-augmentation", () => ({
  AiModulePredictionAugmentation: () => <div data-testid="ai-module-prediction-augmentation" />,
}))

vi.mock("@/src/components/mobile/MobileSpectraCheckReview", () => ({
  MobileSpectraCheckReview: () => null,
}))

vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>()
  return {
    ...actual,
    apiFetch: vi.fn(async () => []),
  }
})

const apiFetchMock = vi.mocked(apiFetch)

function analyticsPayloads() {
  return apiFetchMock.mock.calls
    .filter(([url]) => url === "/analytics/events")
    .map(([, options]) => {
      const body = options?.body
      const payload =
        typeof body === "string"
          ? (JSON.parse(body) as { event_type?: string; metadata?: Record<string, unknown>; metadata_json?: Record<string, unknown> })
          : (body as { event_type?: string; metadata?: Record<string, unknown>; metadata_json?: Record<string, unknown> })
      return {
        event_type: payload.event_type,
        metadata: payload.metadata ?? payload.metadata_json,
      }
    })
}

describe("ProgramsInterfaceWorkspace (post-reorg: SpectraCheck only)", () => {
  beforeEach(() => {
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiFetchMock.mockClear()
    apiFetchMock.mockImplementation(async () => [])
    clearSpectraCheckRuntimeState()
    clearSpectraCheckTabStatePersistence()
    invalidateSpectraCheckSessionReadCache()
  })

  afterEach(() => {
    window.localStorage.clear()
    window.sessionStorage.clear()
    clearSpectraCheckRuntimeState()
    clearSpectraCheckTabStatePersistence()
    invalidateSpectraCheckSessionReadCache()
  })

  it("renders the SpectraCheck workspace without the cross-module tab switcher", () => {
    render(<ProgramsInterfaceWorkspace />)
    // The cross-module switcher (SpectraCheck / Regentry / Repho) lives on the sidebar
    // now, not in-page. So /spectracheck must NOT render any of those as page tabs.
    expect(screen.queryByRole("tab", { name: /^Regentry$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole("tab", { name: /^Repho$/i })).not.toBeInTheDocument()
    // SpectraCheck's own content + AI augmentation are still mounted.
    expect(screen.getByTestId("ai-module-prediction-augmentation")).toBeInTheDocument()
  })

  it("logs a privacy-safe core_module_opened event for SpectraCheck on mount", async () => {
    render(<ProgramsInterfaceWorkspace />)
    await waitFor(() => {
      const openings = analyticsPayloads().filter(
        (payload) => payload.event_type === "core_module_opened",
      )
      expect(
        openings.some(
          (payload) =>
            payload.metadata?.module === "spectracheck" &&
            payload.metadata?.surface === "programs_workspace",
        ),
      ).toBe(true)
    })
  })
})
