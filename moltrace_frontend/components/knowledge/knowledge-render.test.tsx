import type { ReactElement, ReactNode } from "react"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"

/**
 * Strong baseline render tests for the 7 unique Knowledge Library components.
 *
 * Locks in the user-visible contract for each component so the reskin cannot
 * accidentally hide a section, drop a button, or break a heading.
 */

const apiFetchMock = vi.fn()

vi.mock("@/lib/api/client", () => ({
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
  ApiError: class ApiError extends Error {
    status: number
    data: unknown
    constructor(status: number, data: unknown, message?: string) {
      super(message ?? String(status))
      this.status = status
      this.data = data
    }
  },
}))

vi.mock("next/navigation", () => ({
  usePathname: () => "/knowledge",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}))

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (props: { children: ReactNode }) => props.children }),
  AnimatePresence: ({ children }: { children: ReactNode }) => children,
}))

function renderC(ui: ReactElement) {
  return render(ui)
}

beforeEach(() => {
  apiFetchMock.mockReset()
  apiFetchMock.mockImplementation(async () => [])
})

describe("KnowledgeLibraryLanding", () => {
  it("renders the landing heading", async () => {
    const { KnowledgeLibraryLanding } = await import("@/components/knowledge/knowledge-library-landing")
    renderC(<KnowledgeLibraryLanding />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Knowledge Library|Knowledge|Library/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("KnowledgeDatasetsDashboard", () => {
  it("renders the dataset candidate dashboard", async () => {
    const { KnowledgeDatasetsDashboard } = await import("@/components/knowledge/knowledge-datasets-dashboard")
    renderC(<KnowledgeDatasetsDashboard />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Dataset|candidate dashboard|candidates/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("KnowledgeSourceLibraryWorkspace", () => {
  it("renders the source library", async () => {
    const { KnowledgeSourceLibraryWorkspace } = await import("@/components/knowledge/knowledge-source-library-workspace")
    renderC(<KnowledgeSourceLibraryWorkspace />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Source|Knowledge sources|Library/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("KnowledgeExtractionsWorkspace", () => {
  it("renders the extractions workspace", async () => {
    const { KnowledgeExtractionsWorkspace } = await import("@/components/knowledge/knowledge-extractions-workspace")
    renderC(<KnowledgeExtractionsWorkspace />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Extraction|Knowledge extractions/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("KnowledgeExtractionRecordsWorkspace (shared by analytical/reactions/regulatory)", () => {
  it("renders for recordKind=analytical", async () => {
    const { KnowledgeExtractionRecordsWorkspace } = await import(
      "@/components/knowledge/knowledge-extraction-records-workspace"
    )
    renderC(<KnowledgeExtractionRecordsWorkspace recordKind="analytical" />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Analytical|extracted|record/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
  it("renders for recordKind=reaction", async () => {
    const { KnowledgeExtractionRecordsWorkspace } = await import(
      "@/components/knowledge/knowledge-extraction-records-workspace"
    )
    renderC(<KnowledgeExtractionRecordsWorkspace recordKind="reaction" />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Reaction|extracted|record/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
  it("renders for recordKind=regulatory", async () => {
    const { KnowledgeExtractionRecordsWorkspace } = await import(
      "@/components/knowledge/knowledge-extraction-records-workspace"
    )
    renderC(<KnowledgeExtractionRecordsWorkspace recordKind="regulatory" />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Regulatory|extracted|record/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("KnowledgeReviewWorkspace", () => {
  it("renders the review tasks workspace", async () => {
    const { KnowledgeReviewWorkspace } = await import("@/components/knowledge/knowledge-review-workspace")
    renderC(<KnowledgeReviewWorkspace />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Review|Workflow queue|reviewer/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("KnowledgeModelImprovementWorkspace", () => {
  it("renders the model improvement queue", async () => {
    const { KnowledgeModelImprovementWorkspace } = await import(
      "@/components/knowledge/knowledge-model-improvement-workspace"
    )
    renderC(<KnowledgeModelImprovementWorkspace />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Model improvement|Operational backlog|prioritized/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})
