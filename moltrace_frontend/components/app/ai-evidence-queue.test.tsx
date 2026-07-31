import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AIEvidenceQueuePanel } from "@/components/app/ai-evidence-queue"
import { AI_EVIDENCE_QUEUE_UPDATED_EVENT, type AIEvidenceItem } from "@/lib/api/ai-evidence"

const fetchQueue = vi.fn<() => Promise<AIEvidenceItem[]>>()
const loadShared = vi.fn<() => Promise<AIEvidenceItem[]>>()

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}))

vi.mock("@/lib/api/ai-evidence", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/ai-evidence")>()
  return {
    ...actual,
    fetchAiEvidenceQueue: () => fetchQueue(),
    loadSharedAiEvidenceQueue: () => loadShared(),
  }
})

let overviewValue: unknown = null
vi.mock("@/components/app/overview-data-context", () => ({
  useOptionalOverviewData: () => overviewValue,
}))

function item(over: Partial<AIEvidenceItem> & { id: number }): AIEvidenceItem {
  return {
    module: "spectracheck",
    entity_type: "analysis_session",
    entity_id: 1,
    status: "pending_review",
    confidence_score: 0.8,
    risk_level: "medium",
    summary: "Suggested structure assignment needs a reviewer.",
    created_at: "2026-07-30T10:00:00Z",
    updated_at: "2026-07-30T10:00:00Z",
    ...over,
  }
}

beforeEach(() => {
  fetchQueue.mockReset()
  loadShared.mockReset()
  fetchQueue.mockResolvedValue([])
  loadShared.mockResolvedValue([])
  overviewValue = null
})

describe("AIEvidenceQueuePanel", () => {
  it("still reports platform activity when the review queue is empty", async () => {
    overviewValue = {
      loading: false,
      metrics: {
        activeAnalyses: 4,
        reviewRequired: 2,
        reportsReady: 7,
        evidenceQueue: 0,
        jobsFailed: 3,
      },
      sessionsDataAvailable: true,
      jobsDataAvailable: true,
      workflowRunsDataAvailable: true,
      workflowStatusSummary: { active: 5, reviewRequired: 0, failed: 0, completed: 9 },
    }

    render(<AIEvidenceQueuePanel onClose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText("Nothing waiting on you here")).toBeInTheDocument()
    })

    const activity = screen.getByText("Platform activity").closest("div") as HTMLElement
    expect(within(activity).getByText("Analyses running")).toBeInTheDocument()
    expect(within(activity).getByText("4")).toBeInTheDocument()
    expect(within(activity).getByText("2")).toBeInTheDocument()
    expect(within(activity).getByText("7")).toBeInTheDocument()
    expect(within(activity).getByText("5")).toBeInTheDocument()
    expect(within(activity).getByText("3")).toBeInTheDocument()
  })

  it("shows an em dash, never a zero, for a count whose source did not load", async () => {
    overviewValue = {
      loading: false,
      metrics: { activeAnalyses: 4, reviewRequired: 2, reportsReady: 7, evidenceQueue: 0 },
      sessionsDataAvailable: true,
      // Jobs and workflow runs failed to load — those rows must not read "0".
      jobsDataAvailable: false,
      workflowRunsDataAvailable: false,
      workflowStatusSummary: null,
    }

    render(<AIEvidenceQueuePanel onClose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText("Platform activity")).toBeInTheDocument()
    })

    const activity = screen.getByText("Platform activity").closest("div") as HTMLElement
    const jobsRow = within(activity).getByText("Jobs failed").closest("a") as HTMLElement
    expect(within(jobsRow).getByText("—")).toBeInTheDocument()
    const workflowRow = within(activity).getByText("Workflows running").closest("a") as HTMLElement
    expect(within(workflowRow).getByText("—")).toBeInTheDocument()
  })

  it("groups queued evidence by module and filters to one module", async () => {
    loadShared.mockResolvedValue([
      item({ id: 1, module: "spectracheck" }),
      item({ id: 2, module: "regulatory" }),
      item({ id: 3, module: "regulatory" }),
    ])

    const user = userEvent.setup()
    render(<AIEvidenceQueuePanel onClose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /All\s*3/i })).toBeInTheDocument()
    })
    expect(screen.getByRole("button", { name: /Regentry\s*2/i })).toBeInTheDocument()
    expect(screen.getByText("3 items need your review.")).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: /Regentry\s*2/i }))

    expect(screen.getByText("Evidence 2")).toBeInTheDocument()
    expect(screen.getByText("Evidence 3")).toBeInTheDocument()
    expect(screen.queryByText("Evidence 1")).not.toBeInTheDocument()
  })

  it("explains an empty module filter instead of showing a blank list", async () => {
    loadShared.mockResolvedValue([item({ id: 1, module: "spectracheck" })])

    const user = userEvent.setup()
    render(<AIEvidenceQueuePanel onClose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Reactions\s*0/i })).toBeInTheDocument()
    })
    await user.click(screen.getByRole("button", { name: /Reactions\s*0/i }))

    expect(screen.getByText("No evidence from Reaction Optimization right now.")).toBeInTheDocument()
  })

  it("surfaces a plain-language notice when the queue cannot be read", async () => {
    loadShared.mockRejectedValue(new Error("network down"))

    render(<AIEvidenceQueuePanel onClose={() => {}} />)

    await waitFor(() => {
      expect(screen.getByText("Review queue data is temporarily unavailable.")).toBeInTheDocument()
    })
    // The panel still does its other job rather than going blank.
    expect(screen.getByText("Platform activity")).toBeInTheDocument()
  })

  it("refetches on demand from the refresh control", async () => {
    loadShared.mockResolvedValue([item({ id: 1 })])
    fetchQueue.mockResolvedValue([item({ id: 1 }), item({ id: 2 })])

    const user = userEvent.setup()
    render(<AIEvidenceQueuePanel onClose={() => {}} />)

    await waitFor(() => expect(screen.getByText("Evidence 1")).toBeInTheDocument())

    await user.click(screen.getByRole("button", { name: "Refresh AI Evidence Queue" }))

    await waitFor(() => expect(screen.getByText("Evidence 2")).toBeInTheDocument())
    expect(fetchQueue).toHaveBeenCalledTimes(1)
  })

  it("announces a manual refresh so the topbar badge cannot disagree with the list", async () => {
    loadShared.mockResolvedValue([item({ id: 1 })])
    fetchQueue.mockResolvedValue([item({ id: 1 }), item({ id: 2 }), item({ id: 3 })])

    const announced: number[] = []
    const onUpdate = (event: Event) => {
      announced.push((event as CustomEvent<number>).detail)
    }
    window.addEventListener(AI_EVIDENCE_QUEUE_UPDATED_EVENT, onUpdate)

    const user = userEvent.setup()
    render(<AIEvidenceQueuePanel onClose={() => {}} />)
    await waitFor(() => expect(screen.getByText("Evidence 1")).toBeInTheDocument())

    await user.click(screen.getByRole("button", { name: "Refresh AI Evidence Queue" }))
    await waitFor(() => expect(screen.getByText("Evidence 3")).toBeInTheDocument())

    window.removeEventListener(AI_EVIDENCE_QUEUE_UPDATED_EVENT, onUpdate)
    expect(announced).toEqual([3])
  })
})
