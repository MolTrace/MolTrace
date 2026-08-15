/**
 * The dashboard cold-load race (P4 §7) and its own regression guard.
 *
 * Original defect: on a full page load the capabilities readout is still
 * resolving when OverviewDataProvider's effect first runs, so
 * `isIncluded("spectracheck")` answered false, the snapshot was built without
 * sessions AND stamped fresh — and the corrected refetch after capabilities
 * resolved then hit the 30-second freshness gate. The dashboard read as
 * empty/slow on every cold load.
 *
 * The fix must hold BOTH ways, which is what these tests pin:
 *   1. the provisional (capabilities-unresolved) fetch still goes out — three
 *      of the four requests do not depend on the capability answer, and
 *      apiFetch has no timeout, so *waiting* on a stalled /system/capabilities
 *      would leave the dashboard permanently empty: worse than the bug;
 *   2. that provisional result is never written to the snapshot cache, so
 *      the refetch once capabilities land is not short-circuited as "fresh";
 *   3. the refetch consults the REAL capability answer (the sessions request
 *      is actually issued) rather than a value captured during loading.
 */
import { act, render } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const apiFetchMock = vi.fn()
const sessionsListMock = vi.fn()
const loadShellSnapshotMock = vi.fn()
const modulesState: { loading: boolean; included: Set<string> } = {
  loading: true,
  included: new Set(),
}

vi.mock("@/lib/api/client", () => ({
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
  ApiError: class ApiError extends Error {},
}))

vi.mock("@/src/lib/spectracheck/spectracheck-backend-session", () => ({
  fetchSpectraCheckSessionsList: (...args: unknown[]) => sessionsListMock(...args),
}))

vi.mock("@/src/lib/shell/shell-snapshot-cache", () => ({
  SHELL_SNAPSHOT_KEYS: { overviewData: "overview-data" },
  SHELL_SNAPSHOT_MAX_AGE_MS: 30_000,
  isShellSnapshotFresh: () => false,
  readShellSnapshot: () => null,
  // Unlike the first version of this test, the mock INVOKES the loader — so the
  // assertions observe which capability answer the snapshot was actually built
  // with, not merely that a load was requested.
  loadShellSnapshot: (key: string, loader: () => Promise<unknown>) => {
    loadShellSnapshotMock(key)
    return loader()
  },
}))

// The real provider memoizes its value on `[state]`, so `isIncluded` is stable
// between capability changes and the consumer's effect deps behave. The mock
// must match that: returning a fresh closure per render would re-run the effect
// on every render (fetch -> setState -> render -> fetch ...) and mis-attribute
// the resulting loop to the code under test.
const isIncludedStable = (key: string) =>
  modulesState.loading ? false : modulesState.included.has(key)
let modulesValue = { loading: true, isIncluded: isIncludedStable }
function setModules(loading: boolean, included: Set<string>) {
  modulesState.loading = loading
  modulesState.included = included
  modulesValue = { loading, isIncluded: isIncludedStable }
}

vi.mock("@/src/lib/modules/included-modules-provider", () => ({
  useIncludedModules: () => modulesValue,
}))

import { OverviewDataProvider } from "@/components/app/overview-data-context"

describe("overview snapshot vs the capabilities race", () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
    sessionsListMock.mockReset()
    loadShellSnapshotMock.mockReset()
    apiFetchMock.mockResolvedValue([])
    sessionsListMock.mockResolvedValue([])
    setModules(true, new Set())
  })

  it("still fetches while capabilities load, but never caches that provisional result", async () => {
    const view = render(
      <OverviewDataProvider>
        <div />
      </OverviewDataProvider>,
    )
    await act(async () => {})

    // Not blocked: the capability-independent requests went out immediately.
    const paths = apiFetchMock.mock.calls.map((c) => c[0])
    expect(paths).toContain("/projects")
    expect(paths).toContain("/jobs")
    expect(paths).toContain("/workflow-runs")
    // ...but nothing was written to the shared snapshot cache, so the corrected
    // refetch below cannot be short-circuited by the freshness gate.
    expect(loadShellSnapshotMock).not.toHaveBeenCalled()
    // And the capability-dependent leg was correctly skipped while unknown.
    expect(sessionsListMock).not.toHaveBeenCalled()

    // Capabilities resolve with SpectraCheck included.
    setModules(false, new Set(["spectracheck"]))
    await act(async () => {
      view.rerender(
        <OverviewDataProvider>
          <span />
        </OverviewDataProvider>,
      )
    })

    // Now the snapshot is built — and with the REAL answer, proven by the
    // sessions request actually being issued.
    expect(loadShellSnapshotMock).toHaveBeenCalledWith("overview-data")
    expect(sessionsListMock).toHaveBeenCalled()
  })
})
