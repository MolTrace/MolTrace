import type { ReactElement, ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"

/**
 * The three §8 surfaces, tested for what they must not say.
 *
 * Each of these components can be rendered "correctly" and still assert
 * something the corpus does not know, or offer a step the service will refuse.
 * These tests are about that, not about layout.
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
  usePathname: () => "/knowledge/datasets",
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

// ── locators ──────────────────────────────────────────────────────────────────

describe("KnowledgeRecordLocators", () => {
  it("says the passage was not recorded rather than inventing a location", async () => {
    const { KnowledgeRecordLocators } = await import("@/components/knowledge/knowledge-record-locators")
    renderC(<KnowledgeRecordLocators locators={[]} />)
    expect(screen.getByText(/Source passage not recorded/i)).toBeTruthy()
    // No page, paragraph or section may appear when none was recorded.
    expect(screen.queryByText(/^Page \d/i)).toBeNull()
  })

  it("renders the quote as the evidence and the page as the address", async () => {
    const { KnowledgeRecordLocators } = await import("@/components/knowledge/knowledge-record-locators")
    renderC(
      <KnowledgeRecordLocators
        locators={[
          {
            citation_id: 7,
            citation_label: "Smith 2024, SI",
            source_id: 3,
            source_revision_id: 2,
            source_file_id: null,
            page_number: 12,
            section_title: "Methods",
            paragraph_number: 3,
            quote_excerpt: "The reaction was run at 40 °C for 6 h.",
          },
        ]}
      />,
    )
    expect(screen.getByText(/The reaction was run at 40 °C for 6 h\./)).toBeTruthy()
    expect(screen.getByText(/Page 12 · Methods · Paragraph 3/)).toBeTruthy()
    expect(screen.getByText(/Smith 2024, SI/)).toBeTruthy()
  })

  it("marks an unrecorded location without claiming the quote is unsourced", async () => {
    const { KnowledgeRecordLocators } = await import("@/components/knowledge/knowledge-record-locators")
    renderC(
      <KnowledgeRecordLocators
        locators={[
          {
            citation_id: 9,
            citation_label: "Patent US1234",
            source_id: 4,
            source_revision_id: null,
            source_file_id: null,
            page_number: null,
            section_title: null,
            paragraph_number: null,
            quote_excerpt: null,
          },
        ]}
      />,
    )
    expect(screen.getByText(/Location within the source not recorded/i)).toBeTruthy()
    expect(screen.getByText(/No quoted passage was recorded/i)).toBeTruthy()
  })
})

// ── two-person promotion ──────────────────────────────────────────────────────

describe("KnowledgeDatasetVersionApprovals", () => {
  it("shows progress as a count and names the state as awaiting a second approver", async () => {
    apiFetchMock.mockImplementation(async () => ({
      dataset_version_id: 5,
      status: "ready_for_review",
      approvals: [{ id: 1, dataset_version_id: 5, approver_user_id: 2, approver_email: "a@example.com", comment: "Splits look right.", created_at: "2026-08-01T10:00:00Z" }],
      distinct_approvers: 1,
      approvals_required: 2,
      promoted: false,
      human_review_required: true,
    }))
    const { KnowledgeDatasetVersionApprovals } = await import(
      "@/components/knowledge/knowledge-dataset-version-approvals"
    )
    renderC(<KnowledgeDatasetVersionApprovals datasetVersionId={5} />)
    await waitFor(() => {
      expect(screen.getByText(/1 of 2 approvals/)).toBeTruthy()
    })
    expect(screen.getByText(/Awaiting a second approver/i)).toBeTruthy()
    expect(screen.getByText(/Splits look right\./)).toBeTruthy()
  })

  it("offers no field for naming who approved", async () => {
    apiFetchMock.mockImplementation(async () => ({
      dataset_version_id: 5,
      status: "draft",
      approvals: [],
      distinct_approvers: 0,
      approvals_required: 2,
      promoted: false,
      human_review_required: true,
    }))
    const { KnowledgeDatasetVersionApprovals } = await import(
      "@/components/knowledge/knowledge-dataset-version-approvals"
    )
    const { container } = renderC(<KnowledgeDatasetVersionApprovals datasetVersionId={5} />)
    await waitFor(() => {
      expect(screen.getByText(/Not approved yet\./i)).toBeTruthy()
    })
    // The only input is the optional comment. A field naming the approver would
    // let one person nominate another as the second.
    const fields = Array.from(container.querySelectorAll("input, textarea"))
    expect(fields).toHaveLength(1)
    expect(fields[0].tagName.toLowerCase()).toBe("textarea")
  })

  it("hides the approval control once the required approvals are in", async () => {
    apiFetchMock.mockImplementation(async () => ({
      dataset_version_id: 5,
      status: "approved",
      approvals: [],
      distinct_approvers: 2,
      approvals_required: 2,
      promoted: true,
      human_review_required: true,
    }))
    const { KnowledgeDatasetVersionApprovals } = await import(
      "@/components/knowledge/knowledge-dataset-version-approvals"
    )
    renderC(<KnowledgeDatasetVersionApprovals datasetVersionId={5} />)
    await waitFor(() => {
      expect(screen.getByText(/2 of 2 approvals/)).toBeTruthy()
    })
    expect(screen.queryByRole("button", { name: /Record my approval/i })).toBeNull()
  })
})

// ── the deployment conveyor ───────────────────────────────────────────────────

function candidate(overrides: Record<string, unknown>) {
  return {
    id: 11,
    dataset_version_id: 5,
    model_artifact_id: null,
    model_version: "v3",
    metrics_json: {},
    incumbent_metrics_json: {},
    metric_directions_json: {},
    blocking_metric_name: "citation_support_recall",
    blocking_metric_value: 0.91,
    incumbent_blocking_metric_value: 0.9,
    status: "draft",
    gate_verdict_json: {},
    canary_started_at: null,
    promoted_at: null,
    created_by: "a@example.com",
    created_at: "2026-08-01T10:00:00Z",
    warnings: [],
    notes: [],
    human_review_required: true,
    ...overrides,
  }
}

describe("KnowledgeDeploymentConveyor", () => {
  it("does not offer a rollout on a candidate that has not been checked", async () => {
    apiFetchMock.mockImplementation(async () => [candidate({ status: "draft" })])
    const { KnowledgeDeploymentConveyor } = await import(
      "@/components/knowledge/knowledge-deployment-conveyor"
    )
    renderC(<KnowledgeDeploymentConveyor />)
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^Open$/ })).toBeTruthy()
    })
    screen.getByRole("button", { name: /^Open$/ }).click()
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Run the check/i })).toBeTruthy()
    })
    expect(screen.queryByRole("button", { name: /Start a limited rollout/i })).toBeNull()
    expect(screen.getByText(/Run the check first/i)).toBeTruthy()
  })

  it("does not offer promotion straight off a passed check", async () => {
    apiFetchMock.mockImplementation(async () => [
      candidate({ status: "gate_passed", gate_verdict_json: { promotable: true, requires_human_signoff: true, rollback_available: true, reasons: ["Eligible: no safety regression and metric-vector dominance — human sign-off required."], excluded_metrics: [], blocking_metric_name: "citation_support_recall" } }),
    ])
    const { KnowledgeDeploymentConveyor } = await import(
      "@/components/knowledge/knowledge-deployment-conveyor"
    )
    renderC(<KnowledgeDeploymentConveyor />)
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^Open$/ })).toBeTruthy()
    })
    screen.getByRole("button", { name: /^Open$/ }).click()
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Start a limited rollout/i })).toBeTruthy()
    })
    expect(screen.queryByRole("button", { name: /Put into service/i })).toBeNull()
    // And a cleared check must never be presented as a completed promotion.
    expect(screen.getAllByText(/not sign-off/i).length).toBeGreaterThan(0)
  })

  it("shows a refusal's reasons verbatim rather than summarising them", async () => {
    const reason = "Safety-flag recall is missing or out of range [0, 1]; failing closed."
    apiFetchMock.mockImplementation(async () => [
      candidate({
        status: "gate_failed",
        gate_verdict_json: {
          promotable: false,
          safety_regression: true,
          dominates: false,
          requires_human_signoff: true,
          rollback_available: true,
          reasons: [reason],
          excluded_metrics: ["shift_mae"],
          blocking_metric_name: "citation_support_recall",
        },
      }),
    ])
    const { KnowledgeDeploymentConveyor } = await import(
      "@/components/knowledge/knowledge-deployment-conveyor"
    )
    renderC(<KnowledgeDeploymentConveyor />)
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^Open$/ })).toBeTruthy()
    })
    screen.getByRole("button", { name: /^Open$/ }).click()
    await waitFor(() => {
      expect(screen.getByText(reason)).toBeTruthy()
    })
    // A refusal that looks thin is usually a missing measure, not a close call.
    expect(screen.getByText(/fails closed/i)).toBeTruthy()
    expect(screen.getByText(/Shift mae/i)).toBeTruthy()
    expect(screen.queryByRole("button", { name: /Start a limited rollout/i })).toBeNull()
  })

  it("says it is a different queue from the model factory's deployment reviews", async () => {
    const { KnowledgeDeploymentConveyor } = await import(
      "@/components/knowledge/knowledge-deployment-conveyor"
    )
    renderC(<KnowledgeDeploymentConveyor />)
    await waitFor(() => {
      expect(screen.getByText(/separate queue from the model factory/i)).toBeTruthy()
    })
  })
})
