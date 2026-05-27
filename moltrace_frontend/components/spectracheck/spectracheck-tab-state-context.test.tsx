import { beforeEach, describe, expect, it } from "vitest"
import { act, render, renderHook } from "@testing-library/react"
import type { ReactNode } from "react"
import {
  clearSpectraCheckTabStatePersistence,
  SPECTRACHECK_TAB_STATE_STORAGE_KEY,
  SpectraCheckTabStateProvider,
  useOptionalSpectraCheckTabState,
  useProcessedTabState,
  useRawFidTabState,
} from "@/components/spectracheck/spectracheck-tab-state-context"
import { clearSpectraCheckRuntimeState } from "@/src/lib/spectracheck/spectracheck-runtime-reset"

function wrap({ children }: { children: ReactNode }) {
  return <SpectraCheckTabStateProvider>{children}</SpectraCheckTabStateProvider>
}

describe("SpectraCheck tab state context", () => {
  beforeEach(() => {
    clearSpectraCheckRuntimeState()
    clearSpectraCheckTabStatePersistence()
  })

  it("returns null from useOptionalSpectraCheckTabState when no provider is mounted", () => {
    const { result } = renderHook(() => useOptionalSpectraCheckTabState())
    expect(result.current).toBeNull()
  })

  it("falls back to local state when no provider is mounted (raw-fid)", () => {
    const { result } = renderHook(() => useRawFidTabState())
    expect(result.current.state.previewResult).toBeNull()
    act(() => result.current.update({ previewResult: { hello: "world" } }))
    expect(result.current.state.previewResult).toEqual({ hello: "world" })
  })

  it("falls back to local state when no provider is mounted (processed)", () => {
    const { result } = renderHook(() => useProcessedTabState())
    expect(result.current.state.analyzeResult).toBeNull()
    act(() => result.current.update({ analyzeResult: { peaks: [1, 2] } }))
    expect(result.current.state.analyzeResult).toEqual({ peaks: [1, 2] })
  })

  it("survives consumer unmount + remount when provider is mounted (raw-fid)", () => {
    let lastSnapshot: ReturnType<typeof useRawFidTabState> | null = null
    function Consumer({ tag }: { tag: string }) {
      const slice = useRawFidTabState()
      lastSnapshot = slice
      return <span data-testid={tag}>{slice.state.selectedFileName ?? "—"}</span>
    }

    const { unmount, getByTestId } = render(
      <SpectraCheckTabStateProvider>
        <Consumer tag="a" />
      </SpectraCheckTabStateProvider>,
    )
    expect(getByTestId("a").textContent).toBe("—")

    act(() => {
      lastSnapshot!.update({ selectedFileName: "trace.zip" })
    })
    expect(getByTestId("a").textContent).toBe("trace.zip")

    // Unmount the consumer (simulating a tab switch) and re-render. The
    // provider remains mounted so the persisted state should still be there.
    unmount()
    const second = render(
      <SpectraCheckTabStateProvider>
        <Consumer tag="b" />
      </SpectraCheckTabStateProvider>,
    )
    // New provider → route-style remount. Normal navigation must not clear
    // uploaded/analysis state.
    expect(second.getByTestId("b").textContent).toBe("trace.zip")
    second.unmount()

    // Now keep the provider mounted and toggle the consumer to verify the
    // state genuinely survives a child unmount.
    const renderedTag = "first"
    function Wrapper({ children }: { children: ReactNode }) {
      return <SpectraCheckTabStateProvider>{children}</SpectraCheckTabStateProvider>
    }
    const harness = render(
      <Wrapper>
        <Consumer tag={renderedTag} />
      </Wrapper>,
    )
    act(() => {
      lastSnapshot!.update({ selectedFileName: "persisted.zip" })
    })
    expect(harness.getByTestId("first").textContent).toBe("persisted.zip")

    // Re-render the same provider with a different child key to simulate
    // Radix TabsContent swapping which child it shows. The provider stays put.
    harness.rerender(
      <Wrapper>
        <Consumer key="alt" tag="second" />
      </Wrapper>,
    )
    expect(harness.getByTestId("second").textContent).toBe("persisted.zip")
  })

  it("preserves raw and processed uploads/results across a route-level provider remount", () => {
    let raw: ReturnType<typeof useRawFidTabState> | null = null
    let proc: ReturnType<typeof useProcessedTabState> | null = null
    function Reader() {
      raw = useRawFidTabState()
      proc = useProcessedTabState()
      return null
    }

    const rawFile = new File(["raw"], "route-fid.zip", { type: "application/zip" })
    const processedFile = new File(["processed"], "route-spectrum.jdx", {
      type: "text/plain",
    })
    const first = render(
      <SpectraCheckTabStateProvider>
        <Reader />
      </SpectraCheckTabStateProvider>,
    )

    act(() => {
      raw!.update({
        selectedFile: rawFile,
        selectedFileName: rawFile.name,
        previewResult: { archive_id: "raw-1" },
        processResult: { spectrum: { x: [1], y: [2] } },
        previewSpectrum: { x: [8, 7], y: [1, 3], reversedXAxis: true },
        previewLoading: true,
        processLoading: true,
        previewSpectrumLoading: true,
      })
      proc!.update({
        selectedFile: processedFile,
        selectedFileName: processedFile.name,
        previewResult: { point_count: 2 },
        analyzeResult: { peak_count: 12 },
        nmrTextOptional: "1H NMR: δ 4.20",
        candidatesOptional: "C11 | CCO",
        previewLoading: true,
        analyzeLoading: true,
      })
    })

    first.unmount()

    render(
      <SpectraCheckTabStateProvider>
        <Reader />
      </SpectraCheckTabStateProvider>,
    )

    expect(raw!.state.selectedFile?.name).toBe("route-fid.zip")
    expect(raw!.state.selectedFileName).toBe("route-fid.zip")
    expect(raw!.state.previewResult).toEqual({ archive_id: "raw-1" })
    expect(raw!.state.processResult).toEqual({ spectrum: { x: [1], y: [2] } })
    expect(raw!.state.previewSpectrum).toEqual({ x: [8, 7], y: [1, 3], reversedXAxis: true })
    expect(raw!.state.previewLoading).toBe(false)
    expect(raw!.state.processLoading).toBe(false)
    expect(raw!.state.previewSpectrumLoading).toBe(false)

    expect(proc!.state.selectedFile?.name).toBe("route-spectrum.jdx")
    expect(proc!.state.selectedFileName).toBe("route-spectrum.jdx")
    expect(proc!.state.previewResult).toEqual({ point_count: 2 })
    expect(proc!.state.analyzeResult).toEqual({ peak_count: 12 })
    expect(proc!.state.nmrTextOptional).toBe("1H NMR: δ 4.20")
    expect(proc!.state.candidatesOptional).toBe("C11 | CCO")
    expect(proc!.state.previewLoading).toBe(false)
    expect(proc!.state.analyzeLoading).toBe(false)
  })

  it("hydrates serializable analysis state from session storage without reviving stale loading flags", () => {
    window.sessionStorage.setItem(
      SPECTRACHECK_TAB_STATE_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        rawFid: {
          selectedFileName: "stored-raw.zip",
          previewResult: { archive_id: "stored-raw" },
          previewSpectrum: { x: [1], y: [2] },
          previewLoading: true,
          processLoading: true,
        },
        processed: {
          selectedFileName: "stored-processed.jdx",
          analyzeResult: { peak_count: 5 },
          nmrTextOptional: "13C NMR: δ 72.1",
          analyzeLoading: true,
        },
      }),
    )

    let raw: ReturnType<typeof useRawFidTabState> | null = null
    let proc: ReturnType<typeof useProcessedTabState> | null = null
    function Reader() {
      raw = useRawFidTabState()
      proc = useProcessedTabState()
      return null
    }
    render(
      <SpectraCheckTabStateProvider>
        <Reader />
      </SpectraCheckTabStateProvider>,
    )

    expect(raw!.state.selectedFile).toBeNull()
    expect(raw!.state.selectedFileName).toBe("stored-raw.zip")
    expect(raw!.state.previewResult).toEqual({ archive_id: "stored-raw" })
    expect(raw!.state.previewSpectrum).toEqual({ x: [1], y: [2] })
    expect(raw!.state.previewLoading).toBe(false)
    expect(raw!.state.processLoading).toBe(false)

    expect(proc!.state.selectedFile).toBeNull()
    expect(proc!.state.selectedFileName).toBe("stored-processed.jdx")
    expect(proc!.state.analyzeResult).toEqual({ peak_count: 5 })
    expect(proc!.state.nmrTextOptional).toBe("13C NMR: δ 72.1")
    expect(proc!.state.analyzeLoading).toBe(false)
  })

  it("isolates raw-fid and processed slices under the same provider", () => {
    let raw: ReturnType<typeof useRawFidTabState> | null = null
    let proc: ReturnType<typeof useProcessedTabState> | null = null
    function Reader() {
      raw = useRawFidTabState()
      proc = useProcessedTabState()
      return null
    }
    render(
      <SpectraCheckTabStateProvider>
        <Reader />
      </SpectraCheckTabStateProvider>,
    )
    act(() => raw!.update({ nucleus: "13C" }))
    expect(raw!.state.nucleus).toBe("13C")
    expect(proc!.state.nucleus).toBe("1H")

    act(() => proc!.update({ nucleus: "13C" }))
    expect(proc!.state.nucleus).toBe("13C")
  })

  it("reset() restores defaults for the slice", () => {
    const wrapper = ({ children }: { children: ReactNode }) => wrap({ children })
    const { result } = renderHook(() => useRawFidTabState(), { wrapper })
    act(() => {
      result.current.update({ previewResult: { x: 1 }, selectedFileName: "a.zip" })
    })
    expect(result.current.state.previewResult).toEqual({ x: 1 })
    act(() => result.current.reset())
    expect(result.current.state.previewResult).toBeNull()
    expect(result.current.state.selectedFileName).toBeNull()
  })

  it("runtime reset clears live SpectraCheck state and persisted snapshots", () => {
    let raw: ReturnType<typeof useRawFidTabState> | null = null
    let proc: ReturnType<typeof useProcessedTabState> | null = null
    function Reader() {
      raw = useRawFidTabState()
      proc = useProcessedTabState()
      return null
    }
    render(
      <SpectraCheckTabStateProvider>
        <Reader />
      </SpectraCheckTabStateProvider>,
    )

    act(() => {
      raw!.update({ selectedFileName: "logout.zip", previewResult: { ok: true } })
      proc!.update({ selectedFileName: "logout.jdx", analyzeResult: { ok: true } })
    })
    expect(window.sessionStorage.getItem(SPECTRACHECK_TAB_STATE_STORAGE_KEY)).toBeTruthy()

    act(() => clearSpectraCheckRuntimeState())

    expect(raw!.state.selectedFileName).toBeNull()
    expect(raw!.state.previewResult).toBeNull()
    expect(proc!.state.selectedFileName).toBeNull()
    expect(proc!.state.analyzeResult).toBeNull()
    expect(window.sessionStorage.getItem(SPECTRACHECK_TAB_STATE_STORAGE_KEY)).toBeNull()
  })
})
