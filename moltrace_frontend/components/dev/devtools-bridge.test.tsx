import { render } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { DevToolsBridge } from "@/components/dev/devtools-bridge"

afterEach(() => {
  // Vitest restores the original NODE_ENV automatically. Calling this is
  // belt-and-suspenders to avoid stub bleed across parallel workers.
  vi.unstubAllEnvs()
})

describe("DevToolsBridge", () => {
  it("renders the React DevTools connector when NODE_ENV is not production", () => {
    vi.stubEnv("NODE_ENV", "development")
    const { container } = render(<DevToolsBridge />)
    const script = container.querySelector('script[src="http://localhost:8097"]')
    expect(script).not.toBeNull()
  })

  it("renders the connector in the test environment too (parity with dev)", () => {
    vi.stubEnv("NODE_ENV", "test")
    const { container } = render(<DevToolsBridge />)
    expect(container.querySelector('script[src="http://localhost:8097"]')).not.toBeNull()
  })

  it("renders nothing in production so it does not block LCP on Render or Vercel", () => {
    vi.stubEnv("NODE_ENV", "production")
    const { container } = render(<DevToolsBridge />)
    expect(container.querySelector("script")).toBeNull()
    expect(container.firstChild).toBeNull()
  })
})
