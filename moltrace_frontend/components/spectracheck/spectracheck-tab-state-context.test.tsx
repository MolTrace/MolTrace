import { describe, expect, it } from "vitest"
import { act, render, renderHook } from "@testing-library/react"
import type { ReactNode } from "react"
import {
  SpectraCheckTabStateProvider,
  useOptionalSpectraCheckTabState,
  useProcessedTabState,
  useRawFidTabState,
} from "@/components/spectracheck/spectracheck-tab-state-context"

function wrap({ children }: { children: ReactNode }) {
  return <SpectraCheckTabStateProvider>{children}</SpectraCheckTabStateProvider>
}

describe("SpectraCheck tab state context", () => {
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

    const { rerender, unmount, getByTestId } = render(
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
    // New provider → state resets to defaults (fresh workspace mount).
    expect(second.getByTestId("b").textContent).toBe("—")
    second.unmount()

    // Now keep the provider mounted and toggle the consumer to verify the
    // state genuinely survives a child unmount.
    let renderedTag = "first"
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

    renderedTag = "second"
    // Re-render the same provider with a different child key to simulate
    // Radix TabsContent swapping which child it shows. The provider stays put.
    harness.rerender(
      <Wrapper>
        <Consumer key="alt" tag="second" />
      </Wrapper>,
    )
    expect(harness.getByTestId("second").textContent).toBe("persisted.zip")
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
})
