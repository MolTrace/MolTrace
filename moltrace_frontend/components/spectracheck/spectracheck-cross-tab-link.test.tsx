import { describe, expect, it } from "vitest"
import { act, render, renderHook } from "@testing-library/react"
import type { ReactNode } from "react"
import {
  SpectraCheckTabStateProvider,
  useOptionalSpectraCheckTabState,
  useSpectraCheckTabLink,
} from "@/components/spectracheck/spectracheck-tab-state-context"

function wrap({ children }: { children: ReactNode }) {
  return <SpectraCheckTabStateProvider>{children}</SpectraCheckTabStateProvider>
}

describe("Cross-tab handoff (pendingLink slot)", () => {
  it("useSpectraCheckTabLink is a no-op outside of a provider", () => {
    const { result } = renderHook(() => useSpectraCheckTabLink())
    // Just call it — no provider, no error, no state change.
    act(() => result.current({ kind: "raw_fid_to_processed", sourceLabel: "x", payload: { nucleus: "1H", x: [], y: [] } }))
    expect(typeof result.current).toBe("function")
  })

  it("writes raw_fid_to_processed payload into the pendingLink slot", () => {
    let ctx: ReturnType<typeof useOptionalSpectraCheckTabState> = null
    let sendLink: ReturnType<typeof useSpectraCheckTabLink> | null = null
    function Probe() {
      ctx = useOptionalSpectraCheckTabState()
      sendLink = useSpectraCheckTabLink()
      return null
    }
    render(
      <SpectraCheckTabStateProvider>
        <Probe />
      </SpectraCheckTabStateProvider>,
    )
    expect(ctx).not.toBeNull()
    expect(ctx!.pendingLink).toBeNull()
    act(() =>
      sendLink!({
        kind: "raw_fid_to_processed",
        sourceLabel: "Raw FID · trace.zip",
        payload: { nucleus: "1H", x: [1, 2], y: [10, 20] },
      }),
    )
    expect(ctx!.pendingLink).toEqual({
      kind: "raw_fid_to_processed",
      sourceLabel: "Raw FID · trace.zip",
      payload: { nucleus: "1H", x: [1, 2], y: [10, 20] },
    })
  })

  it("writes peaks_to_proton_text payload into the pendingLink slot", () => {
    let ctx: ReturnType<typeof useOptionalSpectraCheckTabState> = null
    let sendLink: ReturnType<typeof useSpectraCheckTabLink> | null = null
    function Probe() {
      ctx = useOptionalSpectraCheckTabState()
      sendLink = useSpectraCheckTabLink()
      return null
    }
    render(
      <SpectraCheckTabStateProvider>
        <Probe />
      </SpectraCheckTabStateProvider>,
    )
    act(() =>
      sendLink!({
        kind: "peaks_to_proton_text",
        sourceLabel: "Processed 1H · spec.csv",
        payload: { text: "1H NMR (400 MHz, CDCl3) δ 3.65", solvent: "CDCl3", spectrometerMhz: "400" },
      }),
    )
    expect(ctx!.pendingLink?.kind).toBe("peaks_to_proton_text")
  })

  it("clears the pendingLink when setPendingLink(null) is called", () => {
    const wrapper = ({ children }: { children: ReactNode }) => wrap({ children })
    const ctxRef = renderHook(() => useOptionalSpectraCheckTabState(), { wrapper })
    act(() =>
      ctxRef.result.current!.setPendingLink({
        kind: "peaks_to_carbon_text",
        sourceLabel: "Processed 13C",
        payload: { text: "13C NMR" },
      }),
    )
    expect(ctxRef.result.current!.pendingLink).not.toBeNull()
    act(() => ctxRef.result.current!.setPendingLink(null))
    expect(ctxRef.result.current!.pendingLink).toBeNull()
  })

  it("stores linkedFromSource on the receiving tab slice when written directly", () => {
    const wrapper = ({ children }: { children: ReactNode }) => wrap({ children })
    const { result } = renderHook(() => useOptionalSpectraCheckTabState(), { wrapper })
    act(() => result.current!.setProcessed({ linkedFromSource: "Raw FID · sample.zip" }))
    expect(result.current!.processed.linkedFromSource).toBe("Raw FID · sample.zip")
    act(() => result.current!.setProcessed({ linkedFromSource: null }))
    expect(result.current!.processed.linkedFromSource).toBeNull()
  })
})
