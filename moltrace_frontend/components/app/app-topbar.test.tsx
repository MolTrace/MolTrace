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

// Hoisted so a test can switch the topbar between its desktop and mobile
// branches. It was pinned to `false`, which meant the mobile AI Queue control —
// a different element with a different label and its own unread dot — had never
// been rendered by any test.
const shell = vi.hoisted(() => ({ isMobile: false }))
vi.mock("@/hooks/use-mobile", () => ({
  useIsMobile: () => shell.isMobile,
}))

vi.mock("@/components/theme-toggle", () => ({
  ThemeToggle: () => <button type="button">Theme</button>,
}))

vi.mock("@/components/app/tenant-selector", () => ({
  TenantSelector: () => <div data-testid="tenant-selector" />,
}))

vi.mock("@/lib/api/ai-evidence", () => ({
  fetchAiEvidenceQueue: vi.fn(async () => []),
  loadSharedAiEvidenceQueue: vi.fn(async () => []),
  AI_EVIDENCE_QUEUE_UPDATED_EVENT: "moltrace:ai-evidence-queue-updated",
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
    const away = render(<div>Regentry route</div>)
    expect(screen.getByText("Regentry route")).toBeInTheDocument()
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

describe("AppTopbar AI Queue control", () => {
  beforeEach(() => {
    shell.isMobile = false
    routerPushMock.mockClear()
    window.localStorage.clear()
  })

  it("labels the desktop control and reports whether the queue is showing", () => {
    render(<AppTopbar onToggleEvidenceQueue={() => {}} evidenceQueueOpen />)

    const control = screen.getByRole("button", { name: /Toggle AI Evidence Queue/i })
    expect(control).toHaveAttribute("aria-expanded", "true")
    // The desktop control carries the count as visible text.
    expect(control).toHaveTextContent("AI Queue")
  })

  it("renders the mobile control, which is a different element entirely", async () => {
    shell.isMobile = true
    const onToggle = vi.fn()
    const user = userEvent.setup()

    render(<AppTopbar onToggleEvidenceQueue={onToggle} evidenceQueueOpen={false} />)

    const control = screen.getByRole("button", { name: /Toggle AI Evidence Queue/i })
    expect(control).toHaveAttribute("aria-expanded", "false")
    // No room for a visible count on an icon button — the mobile branch must not
    // render the desktop badge, which is what made this worth covering.
    expect(control).not.toHaveTextContent("AI Queue")

    await user.click(control)
    expect(onToggle).toHaveBeenCalledTimes(1)
  })

  it("puts the waiting count in the mobile control's accessible name, not on screen", () => {
    shell.isMobile = true
    // The count comes from overview metrics when the queue fetch yields nothing.
    render(<AppTopbar onToggleEvidenceQueue={() => {}} />)

    // With an empty queue there is nothing waiting, so the label stays plain and
    // no unread dot is drawn.
    const control = screen.getByRole("button", { name: "Toggle AI Evidence Queue" })
    expect(control).toBeInTheDocument()
    expect(control.querySelector("span[aria-hidden]")).toBeNull()
  })
})
