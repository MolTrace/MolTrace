import { render } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { DevToolsBridge } from "@/components/dev/devtools-bridge"

afterEach(() => {
  // Vitest restores the original NODE_ENV automatically. Calling this is
  // belt-and-suspenders to avoid stub bleed across parallel workers.
  vi.unstubAllEnvs()
})

describe("DevToolsBridge", () => {
  it("stays silent in development by default (no script, no console refused noise)", () => {
    vi.stubEnv("NODE_ENV", "development")
    vi.stubEnv("NEXT_PUBLIC_ENABLE_REACT_DEVTOOLS_BRIDGE", "")
    const { container } = render(<DevToolsBridge />)
    expect(container.querySelector("script")).toBeNull()
    expect(container.firstChild).toBeNull()
  })

  it("renders the connector when explicitly opted in via env var", () => {
    vi.stubEnv("NODE_ENV", "development")
    vi.stubEnv("NEXT_PUBLIC_ENABLE_REACT_DEVTOOLS_BRIDGE", "1")
    const { container } = render(<DevToolsBridge />)
    expect(container.querySelector('script[src="http://localhost:8097"]')).not.toBeNull()
  })

  it("does not render even when opted in if NODE_ENV is production", () => {
    vi.stubEnv("NODE_ENV", "production")
    vi.stubEnv("NEXT_PUBLIC_ENABLE_REACT_DEVTOOLS_BRIDGE", "1")
    const { container } = render(<DevToolsBridge />)
    expect(container.querySelector("script")).toBeNull()
    expect(container.firstChild).toBeNull()
  })
})
