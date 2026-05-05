import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import ApiTestPage from "@/app/api-test/page"

vi.mock("next/navigation", () => ({
  usePathname: () => "/api-test",
  useRouter: () => ({ push: vi.fn() }),
}))

describe("api test page", () => {
  it("renders Test backend connection button", () => {
    render(<ApiTestPage />)
    expect(screen.getByRole("button", { name: "Test backend connection" })).toBeInTheDocument()
  })
})
