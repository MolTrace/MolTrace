import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

const apiFetch = vi.fn()
vi.mock("@/lib/api/client", () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }))

import { SubstructureQueryPanel } from "@/src/components/chemistry/SubstructureQueryPanel"

const row = (over: Record<string, unknown> = {}) => ({
  smiles: "CCO",
  parsed: true,
  matched: false,
  match_count: 0,
  atom_indices: [],
  ...over,
})

/** Fills in a pattern and two targets, then runs the search. */
async function search(response: unknown | (() => Promise<never>), targets = "CCO\nCCC") {
  apiFetch.mockReset()
  // ...Once, not a standing implementation: vitest reports the rejection of a persistent
  // rejecting mock as an unhandled error and fails the test even when the component has caught
  // it. One call is also exactly what this panel should make.
  if (typeof response === "function") apiFetch.mockImplementationOnce(response as () => Promise<never>)
  else apiFetch.mockResolvedValue(response)
  const user = userEvent.setup()
  render(<SubstructureQueryPanel />)
  await user.type(screen.getByLabelText(/Motif to search for/i), "c1ccccc1")
  await user.type(screen.getByLabelText(/Structures to search/i), targets)
  await user.click(screen.getByRole("button", { name: /Find matches/i }))
  return user
}

describe("SubstructureQueryPanel", () => {
  beforeEach(() => apiFetch.mockReset())

  it("sends exactly smarts and targets, one target per line", async () => {
    await search({ smarts: "c1ccccc1", results: [] })
    await waitFor(() => expect(apiFetch).toHaveBeenCalled())
    const [path, init] = apiFetch.mock.calls[0]!
    expect(path).toBe("/reactions/structures/smarts-match")
    expect(Object.keys(init.body as object).sort()).toEqual(["smarts", "targets"])
    expect((init.body as { targets: string[] }).targets).toEqual(["CCO", "CCC"])
  })

  it("shows an unreadable target as unreadable, never as a structure lacking the motif", async () => {
    // The failure this panel is built to prevent: a reaction pasted in comes back unparsed, and
    // reading that as "does not contain it" is a false negative over a structure never searched.
    await search({
      smarts: "c1ccccc1",
      results: [row({ smiles: "aspirin", matched: true, match_count: 1 }), row({ parsed: false })],
    })
    await waitFor(() => expect(screen.getByText(/1 of 2 contains it/i)).toBeInTheDocument())
    const rows = screen.getAllByRole("listitem").map((li) => li.textContent ?? "")
    expect(rows[0]).toContain("Contains it")
    expect(rows[1]).toContain("Could not be read")
    // Nothing here is a genuine miss — the unreadable one must not have been counted as one.
    expect(rows.some((r) => r.includes("Does not contain it"))).toBe(false)
    expect(screen.getByText(/unanswered, not misses/i)).toBeInTheDocument()
  })

  it("says plainly that only the listed structures were searched", async () => {
    // Without this the reader can take a clean result as "nothing in my workspace has this motif",
    // which is a claim no request here ever made.
    await search({ smarts: "c1ccccc1", results: [row()] })
    await waitFor(() => expect(screen.getByText(/Does not contain it/i)).toBeInTheDocument())
    expect(screen.getByText(/nothing else in the workspace was looked at/i)).toBeInTheDocument()
  })

  it("renders the server's refusal message as sent, rather than replacing it", async () => {
    await search(async () => {
      throw new Error("That query structure could not be read as a search pattern.")
    })
    await waitFor(() =>
      expect(
        screen.getByText("That query structure could not be read as a search pattern."),
      ).toBeInTheDocument(),
    )
  })

  it("will not search with no pattern or no structures", async () => {
    const user = userEvent.setup()
    render(<SubstructureQueryPanel />)
    expect(screen.getByRole("button", { name: /Find matches/i })).toBeDisabled()
    await user.type(screen.getByLabelText(/Motif to search for/i), "c1ccccc1")
    expect(screen.getByRole("button", { name: /Find matches/i })).toBeDisabled()
    await user.type(screen.getByLabelText(/Structures to search/i), "CCO")
    expect(screen.getByRole("button", { name: /Find matches/i })).toBeEnabled()
    expect(apiFetch).not.toHaveBeenCalled()
  })

  it("takes the query pattern off the canvas when one is offered", async () => {
    const user = userEvent.setup()
    // A pattern, not a SMILES: query atoms are the whole point, and they are what getSmiles fails on.
    render(<SubstructureQueryPanel getQueryFromCanvas={async () => "[#6;R]1[#6][#6][#6][#6][#6]1"} />)
    await user.click(screen.getByRole("button", { name: /Use the drawing/i }))
    await waitFor(() =>
      expect(screen.getByLabelText(/Motif to search for/i)).toHaveValue("[#6;R]1[#6][#6][#6][#6][#6]1"),
    )
  })

  it("does not silently accept an empty canvas as a query", async () => {
    const user = userEvent.setup()
    render(<SubstructureQueryPanel getQueryFromCanvas={async () => "   "} />)
    await user.click(screen.getByRole("button", { name: /Use the drawing/i }))
    await waitFor(() =>
      expect(screen.getByText(/nothing on the canvas to search for/i)).toBeInTheDocument(),
    )
  })
})
