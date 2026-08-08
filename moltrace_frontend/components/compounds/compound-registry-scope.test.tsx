import { render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

/**
 * The compound registry is owner-scoped by default. A 404 no longer means the
 * compound is gone — it means either that or that it belongs to another
 * account, and the backend deliberately will not say which. These tests pin the
 * consequence for the UI: the refusal must never be rendered as a factual claim
 * about existence, and must never read as a failure.
 */

const mockApiFetch = vi.hoisted(() => vi.fn<(path: string, init?: unknown) => Promise<unknown>>())

// Partial mock: ApiError stays real, because the whole distinction under test is
// carried by its ``status`` rather than by any message.
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  apiFetch: (path: string, init?: unknown) => mockApiFetch(path, init),
}))

vi.mock("next/navigation", () => ({
  useParams: () => ({ compoundId: "42" }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/compounds/42",
}))

vi.mock("@/src/lib/analytics/analytics-client", () => ({
  trackCompoundGraphViewed: vi.fn(),
}))

import { ApiError } from "@/lib/api/client"
import { CompoundDetailWorkspace } from "@/components/compounds/compound-detail-workspace"
import { CompoundScientificKnowledgeGraphPanel } from "@/components/compounds/compound-scientific-knowledge-graph-panel"
import {
  COMPOUND_UNAVAILABLE_TITLE,
  isCompoundOutOfScope,
} from "@/components/compounds/compound-registry-access"

/** What the backend actually answers for a compound outside your scope. */
function outOfScope() {
  return new ApiError(404, { detail: "Compound not found." }, "Compound not found.")
}

describe("isCompoundOutOfScope", () => {
  it("is the 404, and only the 404", () => {
    expect(isCompoundOutOfScope(outOfScope())).toBe(true)
    // In `shared` deployments a write refusal is a 403 instead, because the row
    // is readable anyway — that is an ordinary permission answer, not a
    // visibility boundary.
    expect(isCompoundOutOfScope(new ApiError(403, { detail: "Forbidden" }))).toBe(false)
    expect(isCompoundOutOfScope(new ApiError(500, {}))).toBe(false)
    expect(isCompoundOutOfScope(new Error("network down"))).toBe(false)
  })
})

describe("CompoundDetailWorkspace — owner-scoped 404", () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  it("renders the neutral unavailable state rather than a hard error", async () => {
    mockApiFetch.mockRejectedValue(outOfScope())
    render(<CompoundDetailWorkspace />)

    await waitFor(() => {
      expect(screen.getByText(COMPOUND_UNAVAILABLE_TITLE)).toBeInTheDocument()
    })
    // The backend's own 404 detail asserts non-existence. Surfacing it would
    // tell a reader something the registry declined to tell them.
    expect(screen.queryByText(/Compound not found/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/could not load compound/i)).not.toBeInTheDocument()
    // And it must not read as the "no record for this id" state either.
    expect(screen.queryByText("No compound record")).not.toBeInTheDocument()
  })

  it("still reports a genuine failure as a failure", async () => {
    mockApiFetch.mockRejectedValue(new ApiError(500, { detail: "boom" }, "Server error."))
    render(<CompoundDetailWorkspace />)

    await waitFor(() => {
      expect(screen.getByText(/server error/i)).toBeInTheDocument()
    })
    expect(screen.queryByText(COMPOUND_UNAVAILABLE_TITLE)).not.toBeInTheDocument()
  })
})

describe("CompoundScientificKnowledgeGraphPanel — owner-scoped 404", () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
  })

  it("does not present an unreadable graph as an empty one", async () => {
    mockApiFetch.mockRejectedValue(outOfScope())
    render(<CompoundScientificKnowledgeGraphPanel compoundId="42" />)

    await waitFor(() => {
      expect(screen.getByText(COMPOUND_UNAVAILABLE_TITLE)).toBeInTheDocument()
    })
    // "No nodes" would assert the compound exists and simply has an empty graph.
    expect(screen.queryByText("No nodes")).not.toBeInTheDocument()
    expect(screen.queryByText(/Compound not found/i)).not.toBeInTheDocument()
  })

  it("shows the empty graph state when the graph really is readable and empty", async () => {
    mockApiFetch.mockResolvedValue({ nodes: [], edges: [], warnings: [], notes: [] })
    render(<CompoundScientificKnowledgeGraphPanel compoundId="42" />)

    await waitFor(() => {
      expect(screen.getByText("No nodes")).toBeInTheDocument()
    })
    expect(screen.queryByText(COMPOUND_UNAVAILABLE_TITLE)).not.toBeInTheDocument()
  })
})
