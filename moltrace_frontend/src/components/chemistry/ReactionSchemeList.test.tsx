import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

const apiFetch = vi.fn()
vi.mock("@/lib/api/client", () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }))

import { ReactionSchemeList } from "@/src/components/chemistry/ReactionSchemeList"

const live = {
  id: 7,
  reaction_project_id: 12,
  name: "Step 3 esterification",
  format: "rxn",
  source_block: "B",
  canonical_smiles: "CC(=O)Cl.CCO>>CCOC(C)=O",
  atom_count: 9,
  bond_count: 8,
  warnings: [{ code: "stereochemistry_undefined", message: "Stereochemistry is not defined." }],
  created_at: "2026-07-01T10:00:00Z",
  updated_at: "2026-07-01T10:00:00Z",
}

const archived = {
  ...live,
  id: 8,
  name: "Old route",
  deleted_at: "2026-07-20T09:00:00Z",
  reason_for_change: "superseded by the revised route",
}

describe("ReactionSchemeList", () => {
  // Braces matter: an expression-bodied arrow returns the mock, and vitest calls a value
  // returned from beforeEach as the test's teardown — re-invoking the mock after the test.
  beforeEach(() => {
    apiFetch.mockReset()
  })

  it("lists what is attached, with the warnings still visible after capture", async () => {
    apiFetch.mockResolvedValue([live])
    render(<ReactionSchemeList reactionProjectId={12} />)
    await waitFor(() => expect(screen.getByText("Step 3 esterification")).toBeInTheDocument())
    // A warning that only ever appeared at capture time is a warning nobody acts on.
    expect(screen.getByText("Stereochemistry is not defined.")).toBeInTheDocument()
    expect(screen.getByText(/CC\(=O\)Cl\.CCO>>CCOC\(C\)=O/)).toBeInTheDocument()
    expect(screen.getByText(/components sorted/i)).toBeInTheDocument()
  })

  it("excludes archived schemes by default and asks for them only when told to", async () => {
    apiFetch.mockResolvedValue([live])
    const user = userEvent.setup()
    render(<ReactionSchemeList reactionProjectId={12} />)
    await waitFor(() => expect(apiFetch).toHaveBeenCalled())
    expect(String(apiFetch.mock.calls[0]![0])).toContain("include_deleted=false")

    apiFetch.mockResolvedValue([live, archived])
    await user.click(screen.getByLabelText(/Include archived/i))
    await waitFor(() =>
      expect(String(apiFetch.mock.calls.at(-1)![0])).toContain("include_deleted=true"),
    )
    await waitFor(() => expect(screen.getByText("Old route")).toBeInTheDocument())
  })

  it("shows an archived scheme as retained, with the reason it stopped being current", async () => {
    apiFetch.mockResolvedValue([archived])
    render(<ReactionSchemeList reactionProjectId={12} />)
    await waitFor(() => expect(screen.getByText("Old route")).toBeInTheDocument())
    expect(screen.getByText(/superseded by the revised route/)).toBeInTheDocument()
    // Already archived: no second archive control.
    expect(screen.queryByRole("button", { name: /^Archive$/ })).toBeNull()
  })

  it("will not submit a blank reason — the server 422s it, so the gate is here too", async () => {
    apiFetch.mockResolvedValue([live])
    const user = userEvent.setup()
    render(<ReactionSchemeList reactionProjectId={12} />)
    await waitFor(() => expect(screen.getByText("Step 3 esterification")).toBeInTheDocument())
    await user.click(screen.getByRole("button", { name: /^Archive$/ }))

    const submit = screen.getByRole("button", { name: /Archive scheme/i })
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText(/Why is this no longer current/i), "   ")
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText(/Why is this no longer current/i), "superseded")
    expect(submit).toBeEnabled()
  })

  it("posts the reason to the archive route, then reloads the list", async () => {
    apiFetch.mockResolvedValue([live])
    const user = userEvent.setup()
    render(<ReactionSchemeList reactionProjectId={12} />)
    await waitFor(() => expect(screen.getByText("Step 3 esterification")).toBeInTheDocument())
    await user.click(screen.getByRole("button", { name: /^Archive$/ }))
    await user.type(screen.getByLabelText(/Why is this no longer current/i), "superseded")

    apiFetch.mockResolvedValue({ ...archived, id: 7 })
    await user.click(screen.getByRole("button", { name: /Archive scheme/i }))

    await waitFor(() => {
      const call = apiFetch.mock.calls.find(([p]) => String(p).includes("/archive"))
      expect(call?.[0]).toBe("/reaction-projects/12/schemes/7/archive")
      expect((call?.[1] as { body: Record<string, unknown> }).body).toEqual({
        reason_for_change: "superseded",
      })
    })
    // A reload follows, so the row reflects its new state rather than the stale one.
    await waitFor(() =>
      expect(apiFetch.mock.calls.filter(([p]) => String(p).includes("include_deleted")).length).toBeGreaterThan(1),
    )
  })

  it("says nothing is attached rather than showing an empty frame", async () => {
    apiFetch.mockResolvedValue([])
    render(<ReactionSchemeList reactionProjectId={12} />)
    await waitFor(() => expect(screen.getByText(/No schemes attached yet/i)).toBeInTheDocument())
  })

  it("reports a failed load without pretending the project has no schemes", async () => {
    // "Could not load" and "there are none" are different facts and must not share a rendering.
    apiFetch.mockImplementation(async () => {
      throw new Error("Not found.")
    })
    render(<ReactionSchemeList reactionProjectId={12} />)
    await waitFor(() => expect(screen.getByText(/Could not load schemes/i)).toBeInTheDocument())
    expect(screen.queryByText(/No schemes attached yet/i)).toBeNull()
  })

  it("survives a row list containing junk", async () => {
    apiFetch.mockResolvedValue([live, null, "nope", { no_id: true }])
    render(<ReactionSchemeList reactionProjectId={12} />)
    await waitFor(() => expect(screen.getByTestId("reaction-scheme-7")).toBeInTheDocument())
  })
})
