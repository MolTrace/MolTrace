import { afterEach, describe, expect, it } from "vitest"
import { act, render, renderHook, screen } from "@testing-library/react"
import {
  DeveloperModeProvider,
  DeveloperOnly,
  useDeveloperMode,
} from "@/components/developer-mode-provider"

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <DeveloperModeProvider>{children}</DeveloperModeProvider>
)

afterEach(() => {
  window.localStorage.clear()
})

describe("developer-mode-provider", () => {
  it("defaults to OFF and hides DeveloperOnly content", () => {
    render(
      <DeveloperModeProvider>
        <DeveloperOnly>
          <span>secret payload</span>
        </DeveloperOnly>
      </DeveloperModeProvider>,
    )
    expect(screen.queryByText("secret payload")).not.toBeInTheDocument()
  })

  it("reveals DeveloperOnly content once enabled and persists to localStorage", () => {
    const { result } = renderHook(() => useDeveloperMode(), { wrapper })
    expect(result.current.enabled).toBe(false)

    act(() => result.current.setEnabled(true))
    expect(result.current.enabled).toBe(true)
    expect(window.localStorage.getItem("moltrace:developer-mode")).toBe("true")

    act(() => result.current.toggle())
    expect(result.current.enabled).toBe(false)
    expect(window.localStorage.getItem("moltrace:developer-mode")).toBe("false")
  })

  it("rehydrates a previously-stored preference", () => {
    window.localStorage.setItem("moltrace:developer-mode", "true")
    const { result } = renderHook(() => useDeveloperMode(), { wrapper })
    expect(result.current.enabled).toBe(true)
  })

  it("falls back to OFF with no provider (no throw)", () => {
    const { result } = renderHook(() => useDeveloperMode())
    expect(result.current.enabled).toBe(false)
    // no-op setters must not throw without a provider
    expect(() => act(() => result.current.toggle())).not.toThrow()
  })
})
