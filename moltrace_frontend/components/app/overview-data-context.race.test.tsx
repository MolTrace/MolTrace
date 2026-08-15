/**
 * The dashboard cold-load race (P4 §7): on a full page load the capabilities
 * readout is still resolving when OverviewDataProvider's effect first runs, so
 * `isIncluded("spectracheck")` answered false, the snapshot was built without
 * sessions AND stamped fresh — and the corrected refetch after capabilities
 * resolved then hit the 30-second freshness gate. The dashboard read as
 * empty/slow on every cold load, self-correcting only on a much later
 * navigation. The provider must not build a snapshot until the capability
 * answer is real.
 */
import { act, render } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const loadShellSnapshotMock = vi.fn()
const modulesState: { loading: boolean; included: Set<string> } = {
  loading: true,
  included: new Set(),
}

vi.mock("@/src/lib/shell/shell-snapshot-cache", () => ({
  SHELL_SNAPSHOT_KEYS: { overviewData: "overview-data" },
  SHELL_SNAPSHOT_MAX_AGE_MS: 30_000,
  isShellSnapshotFresh: () => false,
  readShellSnapshot: () => null,
  loadShellSnapshot: (...args: unknown[]) => {
    loadShellSnapshotMock(...args)
    return new Promise(() => {}) // never resolves — assertions are about the call
  },
}))

vi.mock("@/src/lib/modules/included-modules-provider", () => ({
  useIncludedModules: () => ({
    loading: modulesState.loading,
    isIncluded: (key: string) => (modulesState.loading ? false : modulesState.included.has(key)),
  }),
}))

import { OverviewDataProvider } from "@/components/app/overview-data-context"

describe("overview snapshot vs the capabilities race", () => {
  beforeEach(() => {
    loadShellSnapshotMock.mockClear()
    modulesState.loading = true
    modulesState.included = new Set()
  })

  it("does not build a snapshot while capabilities are still loading", async () => {
    const view = render(
      <OverviewDataProvider>
        <div />
      </OverviewDataProvider>,
    )
    expect(loadShellSnapshotMock).not.toHaveBeenCalled()

    // Capabilities resolve with SpectraCheck included; the provider re-renders
    // and only now builds the snapshot — with the real answer, not the
    // loading-phase false.
    modulesState.loading = false
    modulesState.included = new Set(["spectracheck"])
    await act(async () => {
      view.rerender(
        <OverviewDataProvider>
          <span />
        </OverviewDataProvider>,
      )
    })
    expect(loadShellSnapshotMock).toHaveBeenCalledTimes(1)
  })
})
