import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import { EntityPicker } from "@/components/ui/entity-picker"
import { ApiError } from "@/lib/api/client"

async function openWith(load: () => Promise<never>) {
  const user = userEvent.setup()
  render(<EntityPicker value={null} onChange={() => {}} load={load} placeholder="Choose one" />)
  await user.click(screen.getByRole("combobox"))
}

describe("EntityPicker load failures", () => {
  it("tells a signed-out reader to sign in, rather than that something broke", async () => {
    // The case seen in production: the list needs a session, and "Could not load
    // options." gave no hint that signing in was the fix.
    await openWith(() => Promise.reject(new ApiError(401, null)))
    await waitFor(() => {
      expect(screen.getByText("Sign in to load these options.")).toBeInTheDocument()
    })
  })

  it("separates a licensing refusal from a permission failure", async () => {
    await openWith(() =>
      Promise.reject(new ApiError(403, null, undefined, "reaction_optimization")),
    )
    await waitFor(() => {
      expect(
        screen.getByText("This list belongs to a product this workspace does not include."),
      ).toBeInTheDocument()
    })
  })

  it("says the service is unreachable when it is, and suggests retrying", async () => {
    await openWith(() => Promise.reject(new ApiError(503, null)))
    await waitFor(() => {
      expect(screen.getByText("The service could not be reached. Try again shortly.")).toBeInTheDocument()
    })
  })

  it("falls back to the generic message for anything it cannot name", async () => {
    await openWith(() => Promise.reject(new Error("boom")))
    await waitFor(() => {
      expect(screen.getByText("Could not load options.")).toBeInTheDocument()
    })
  })
})
