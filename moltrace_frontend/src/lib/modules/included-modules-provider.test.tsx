import { describe, expect, it, vi, beforeEach } from "vitest"
import { act, render, screen, waitFor } from "@testing-library/react"

const apiFetch = vi.fn()
vi.mock("@/lib/api/client", () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }))

import {
  IncludedModulesProvider,
  useIncludedModules,
} from "@/src/lib/modules/included-modules-provider"

/**
 * Regression test for a race found against a live single-module backend.
 *
 * /system/capabilities is itself a request, so it lands AFTER the requests it is supposed to
 * gate. The provider originally treated "in flight" the same as "unreadable" and failed OPEN for
 * both, so every gated fetch answered "included" and fired anyway — the browser console showed
 * eight refused regulatory requests arriving BEFORE the capabilities response.
 *
 * The three states must stay distinct: in-flight says no (don't act yet), unreadable says yes
 * (fail open), readable answers for real.
 */
function Probe() {
  const { isIncluded, isRouteOffered, loading } = useIncludedModules()
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="reg">{String(isIncluded("regulatory_hub"))}</span>
      <span data-testid="spec">{String(isIncluded("spectracheck"))}</span>
      <span data-testid="route">{String(isRouteOffered("/regulatory"))}</span>
    </div>
  )
}

const read = (id: string) => screen.getByTestId(id).textContent

function renderProbe() {
  return render(
    <IncludedModulesProvider>
      <Probe />
    </IncludedModulesProvider>,
  )
}

const SINGLE_MODULE = {
  modules: [
    { module: "spectracheck", display_name: "SpectraCheck", included: true },
    { module: "regulatory_hub", display_name: "Regentry", included: false },
    { module: "reaction_optimization", display_name: "Repho", included: false },
  ],
}

describe("IncludedModulesProvider", () => {
  beforeEach(() => {
    apiFetch.mockReset()
  })

  it("answers NO while the readout is in flight, so gated fetches cannot race ahead of it", async () => {
    let release: (v: unknown) => void = () => {}
    apiFetch.mockImplementation(() => new Promise((res) => (release = res)))

    renderProbe()

    // First paint: the request has not returned. Nothing may claim to be included yet — this is
    // the exact window in which every gated fetch used to fire.
    expect(read("loading")).toBe("true")
    expect(read("reg")).toBe("false")
    expect(read("spec")).toBe("false")
    expect(read("route")).toBe("false")

    release(SINGLE_MODULE)
    await waitFor(() => expect(read("loading")).toBe("false"))
  })

  it("answers for real once the readout lands", async () => {
    apiFetch.mockResolvedValue(SINGLE_MODULE)
    renderProbe()
    await waitFor(() => expect(read("loading")).toBe("false"))
    expect(read("spec")).toBe("true")
    expect(read("reg")).toBe("false")
    expect(read("route")).toBe("false")
  })

  it("FAILS OPEN once the readout has definitively failed", async () => {
    // Losing the readout must never hide what a customer bought. This is why "in flight" and
    // "unreadable" have to be separate states rather than one falsy blob.
    apiFetch.mockImplementation(async () => {
      throw new Error("404")
    })
    renderProbe()
    await waitFor(() => expect(read("loading")).toBe("false"))
    expect(read("reg")).toBe("true")
    expect(read("spec")).toBe("true")
    expect(read("route")).toBe("true")
  })

  it("fails open on a payload it cannot parse", async () => {
    apiFetch.mockResolvedValue({ unexpected: "shape" })
    renderProbe()
    await waitFor(() => expect(read("loading")).toBe("false"))
    expect(read("reg")).toBe("true")
  })

  it("treats a missing included flag as not-included, never as permission", async () => {
    apiFetch.mockResolvedValue({
      modules: [
        { module: "spectracheck", included: true },
        { module: "regulatory_hub" },
      ],
    })
    renderProbe()
    await waitFor(() => expect(read("loading")).toBe("false"))
    expect(read("spec")).toBe("true")
    expect(read("reg")).toBe("false")
  })

  it("asks the server exactly once", async () => {
    apiFetch.mockResolvedValue(SINGLE_MODULE)
    renderProbe()
    await waitFor(() => expect(read("loading")).toBe("false"))
    expect(apiFetch).toHaveBeenCalledTimes(1)
    expect(apiFetch.mock.calls[0]?.[0]).toBe("/system/capabilities")
  })
})

describe("IncludedModulesProvider — lazy on first subscriber", () => {
  beforeEach(() => {
    apiFetch.mockReset()
  })

  it("makes NO capabilities request when nothing subscribes (a marketing page)", async () => {
    apiFetch.mockResolvedValue(SINGLE_MODULE)
    render(
      <IncludedModulesProvider>
        {/* Marketing content: children that never call useIncludedModules. */}
        <p>public homepage</p>
      </IncludedModulesProvider>,
    )
    // Flush effects; the provider is mounted in the ROOT layout, so before this
    // change every public marketing pageview fired a backend request here.
    await act(async () => {})
    expect(apiFetch).not.toHaveBeenCalled()
  })

  it("fetches exactly once when the first consumer mounts", async () => {
    apiFetch.mockResolvedValue(SINGLE_MODULE)
    renderProbe()
    await waitFor(() => expect(read("loading")).toBe("false"))
    expect(apiFetch).toHaveBeenCalledTimes(1)
    expect(read("spec")).toBe("true")
    expect(read("reg")).toBe("false")
  })
})
