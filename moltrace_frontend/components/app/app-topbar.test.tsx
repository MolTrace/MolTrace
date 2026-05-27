import userEvent from "@testing-library/user-event"
import { act, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { AppTopbar } from "@/components/app/app-topbar"
import {
  clearSpectraCheckTabStatePersistence,
  SpectraCheckTabStateProvider,
  useProcessedTabState,
  useRawFidTabState,
} from "@/components/spectracheck/spectracheck-tab-state-context"
import { AUTH_TOKEN_STORAGE_KEY } from "@/lib/api/client"
import { clearSpectraCheckRuntimeState } from "@/src/lib/spectracheck/spectracheck-runtime-reset"

const routerPushMock = vi.hoisted(() => vi.fn())

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPushMock, replace: vi.fn() }),
}))

vi.mock("@/hooks/use-mobile", () => ({
  useIsMobile: () => false,
}))

vi.mock("@/components/theme-toggle", () => ({
  ThemeToggle: () => <button type="button">Theme</button>,
}))

vi.mock("@/components/app/tenant-selector", () => ({
  TenantSelector: () => <div data-testid="tenant-selector" />,
}))

vi.mock("@/lib/api/ai-evidence", () => ({
  fetchAiEvidenceQueue: vi.fn(async () => []),
}))

vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>()
  return {
    ...actual,
    apiFetch: vi.fn(async () => []),
  }
})

let rawSlice: ReturnType<typeof useRawFidTabState> | null = null
let processedSlice: ReturnType<typeof useProcessedTabState> | null = null

function SpectraCheckStateProbe() {
  rawSlice = useRawFidTabState()
  processedSlice = useProcessedTabState()
  return (
    <div>
      <span data-testid="raw-file">{rawSlice.state.selectedFileName ?? "empty"}</span>
      <span data-testid="processed-file">{processedSlice.state.selectedFileName ?? "empty"}</span>
      <span data-testid="raw-preview">{rawSlice.state.previewResult ? "has raw preview" : "no raw preview"}</span>
      <span data-testid="processed-analysis">
        {processedSlice.state.analyzeResult ? "has processed analysis" : "no processed analysis"}
      </span>
    </div>
  )
}

function TopbarHarness() {
  return (
    <SpectraCheckTabStateProvider>
      <SpectraCheckStateProbe />
      <AppTopbar onToggleEvidenceQueue={() => {}} />
    </SpectraCheckTabStateProvider>
  )
}

function seedSpectraCheckState() {
  act(() => {
    rawSlice!.update({
      selectedFileName: "signout-raw.zip",
      previewResult: { archive_id: "raw-1" },
    })
    processedSlice!.update({
      selectedFileName: "signout-processed.jdx",
      analyzeResult: { peak_count: 12 },
    })
  })
}

describe("AppTopbar sign out", () => {
  beforeEach(() => {
    routerPushMock.mockClear()
    window.localStorage.clear()
    window.sessionStorage.clear()
    clearSpectraCheckRuntimeState()
    clearSpectraCheckTabStatePersistence()
    rawSlice = null
    processedSlice = null
  })

  it("preserves SpectraCheck state across ordinary app navigation and clears it on sign out", async () => {
    const user = userEvent.setup()
    window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, "test-token")
    window.localStorage.setItem("moltrace.tenant_id", "tenant-1")
    window.sessionStorage.setItem("unrelated-session", "kept-until-signout")

    let view = render(<TopbarHarness />)
    seedSpectraCheckState()

    expect(screen.getByTestId("raw-file")).toHaveTextContent("signout-raw.zip")
    expect(screen.getByTestId("processed-file")).toHaveTextContent("signout-processed.jdx")
    expect(screen.getByTestId("raw-preview")).toHaveTextContent("has raw preview")
    expect(screen.getByTestId("processed-analysis")).toHaveTextContent("has processed analysis")

    view.unmount()
    const away = render(<div>Regulatory Hub route</div>)
    expect(screen.getByText("Regulatory Hub route")).toBeInTheDocument()
    away.unmount()

    view = render(<TopbarHarness />)
    expect(screen.getByTestId("raw-file")).toHaveTextContent("signout-raw.zip")
    expect(screen.getByTestId("processed-file")).toHaveTextContent("signout-processed.jdx")
    expect(screen.getByTestId("raw-preview")).toHaveTextContent("has raw preview")
    expect(screen.getByTestId("processed-analysis")).toHaveTextContent("has processed analysis")

    await user.click(screen.getByRole("button", { name: /Open profile menu/i }))
    await user.click(await screen.findByRole("menuitem", { name: /Sign Out/i }))

    expect(routerPushMock).toHaveBeenCalledWith("/sign-in")
    expect(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)).toBeNull()
    expect(window.localStorage.getItem("moltrace.tenant_id")).toBeNull()
    expect(window.sessionStorage.length).toBe(0)
    expect(screen.getByTestId("raw-file")).toHaveTextContent("empty")
    expect(screen.getByTestId("processed-file")).toHaveTextContent("empty")
    expect(screen.getByTestId("raw-preview")).toHaveTextContent("no raw preview")
    expect(screen.getByTestId("processed-analysis")).toHaveTextContent("no processed analysis")

    view.unmount()
    render(<TopbarHarness />)
    expect(screen.getByTestId("raw-file")).toHaveTextContent("empty")
    expect(screen.getByTestId("processed-file")).toHaveTextContent("empty")
  })
})
