import userEvent from "@testing-library/user-event"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ProgramsInterfaceWorkspace } from "@/components/programs/programs-interface-workspace"
import { clearSpectraCheckTabStatePersistence } from "@/components/spectracheck/spectracheck-tab-state-context"
import { apiFetch } from "@/lib/api/client"
import { invalidateSpectraCheckSessionReadCache } from "@/src/lib/spectracheck/spectracheck-evidence-session"
import { clearSpectraCheckRuntimeState } from "@/src/lib/spectracheck/spectracheck-runtime-reset"

vi.mock("next/navigation", () => ({
  usePathname: () => "/programs",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}))

vi.mock("@/hooks/use-mobile", () => ({
  useIsMobile: () => false,
}))

vi.mock("@/components/ai/ai-module-prediction-augmentation", () => ({
  AiModulePredictionAugmentation: () => <div data-testid="ai-module-prediction-augmentation" />,
}))

vi.mock("@/components/regulatory-hub/regulatory-intelligence-landing", () => ({
  RegulatoryIntelligenceLanding: () => <section>Regulatory Hub workspace placeholder</section>,
}))

vi.mock("@/components/reaction-optimization/reaction-program-interface-workspace", () => ({
  ReactionProgramInterfaceWorkspace: () => <section>ReactionIQ workspace placeholder</section>,
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

describe("ProgramsInterfaceWorkspace SpectraCheck persistence", () => {
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

  it("logs privacy-safe core module openings for SpectraCheck, Regulatory Hub, and ReactionIQ", async () => {
    const user = userEvent.setup()
    render(<ProgramsInterfaceWorkspace />)

    await waitFor(() => {
      expect(
        analyticsPayloads().some(
          (payload) =>
            payload.event_type === "core_module_opened" &&
            payload.metadata?.module === "spectracheck" &&
            payload.metadata?.surface === "programs_workspace",
        ),
      ).toBe(true)
    })

    await user.click(screen.getByRole("tab", { name: /^Regulatory Hub$/i }))
    await user.click(screen.getByRole("tab", { name: /^ReactionIQ$/i }))

    await waitFor(() => {
      const openedModules = analyticsPayloads()
        .filter((payload) => payload.event_type === "core_module_opened")
        .map((payload) => payload.metadata?.module)
      expect(openedModules).toEqual(expect.arrayContaining(["spectracheck", "regulatory_hub", "reactioniq"]))
    })
  })

  it("keeps raw and processed SpectraCheck uploads while switching between Programs modules", async () => {
    const user = userEvent.setup()
    render(<ProgramsInterfaceWorkspace />)

    const rawFile = new File(["pretend-fid"], "program-raw.zip", { type: "application/zip" })
    await user.click(screen.getByRole("tab", { name: /Raw FID upload/i }))
    fireEvent.drop(screen.getByRole("button", { name: /Drop raw FID archive/i }), {
      dataTransfer: { files: [rawFile], types: ["Files"] },
    })
    expect(screen.getAllByText("program-raw.zip").length).toBeGreaterThan(0)

    const processedFile = new File(["##TITLE=processed"], "program-processed.jdx", {
      type: "text/plain",
    })
    await user.click(screen.getByRole("tab", { name: /Processed 1H \/ 13C upload/i }))
    fireEvent.drop(screen.getByRole("button", { name: /Drop processed spectrum file/i }), {
      dataTransfer: { files: [processedFile], types: ["Files"] },
    })
    expect(screen.getAllByText("program-processed.jdx").length).toBeGreaterThan(0)

    await user.click(screen.getByRole("tab", { name: /^Regulatory Hub$/i }))
    expect(screen.getByText("Regulatory Hub workspace placeholder")).toBeInTheDocument()

    await user.click(screen.getByRole("tab", { name: /^ReactionIQ$/i }))
    expect(screen.getByText("ReactionIQ workspace placeholder")).toBeInTheDocument()

    await user.click(screen.getByRole("tab", { name: /^SpectraCheck$/i }))
    await user.click(screen.getByRole("tab", { name: /Raw FID upload/i }))
    await waitFor(() => {
      expect(screen.getAllByText("program-raw.zip").length).toBeGreaterThan(0)
    })

    await user.click(screen.getByRole("tab", { name: /Processed 1H \/ 13C upload/i }))
    await waitFor(() => {
      expect(screen.getAllByText("program-processed.jdx").length).toBeGreaterThan(0)
    })
  })
})
