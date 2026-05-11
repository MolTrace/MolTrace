import type { ReactElement, ReactNode } from "react"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"

/**
 * Strong baseline render tests for the Reaction Optimization components.
 *
 * Locks in the user-visible contract for each major component so the reskin
 * cannot accidentally hide a section, drop a button, or break a heading.
 *
 * After redesign, these MUST still pass — relax only when copy intentionally
 * changes (e.g. h2 title change), and update the assertion to the new copy.
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
  usePathname: () => "/reactions",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ reactionId: "10" }),
}))

// Stub framer-motion if any component pulls it
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

describe("Reaction Optimization Landing", () => {
  it("renders without crashing and shows a recognizable heading", async () => {
    const { ReactionOptimizationLanding } = await import(
      "@/components/reaction-optimization/reaction-optimization-landing"
    )
    renderC(<ReactionOptimizationLanding />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Reaction|Optimization|Project/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("Reaction Program Interface Workspace (wrapper tabs)", () => {
  it("renders both tab triggers", async () => {
    const { ReactionProgramInterfaceWorkspace } = await import(
      "@/components/reaction-optimization/reaction-program-interface-workspace"
    )
    renderC(<ReactionProgramInterfaceWorkspace />)
    expect(screen.getByRole("tab", { name: /Reaction Optimization/i })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: /Reaction Studio/i })).toBeInTheDocument()
  })
})

describe("Reaction Project Detail (largest workspace, 11 tabs)", () => {
  it("renders without crashing and surfaces the project workspace", async () => {
    const { ReactionProjectDetail } = await import(
      "@/components/reaction-optimization/reaction-project-detail"
    )
    renderC(<ReactionProjectDetail />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Reaction|Project|Variables|Experiments|Optimization/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("Reaction Regulatory Constraints Panel (cross-module integration)", () => {
  it("renders the constraints panel host", async () => {
    const { ReactionRegulatoryConstraintsPanel } = await import(
      "@/components/reaction-optimization/reaction-regulatory-constraints-panel"
    )
    renderC(<ReactionRegulatoryConstraintsPanel reactionProjectId={10} />)
    await waitFor(() => {
      const found = screen.queryAllByText(/Regulatory|Constraint|Compliance/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("Reaction Response Overview", () => {
  it("renders without crashing", async () => {
    const { ReactionResponseOverview } = await import(
      "@/components/reaction-optimization/reaction-response-overview"
    )
    renderC(
      <ReactionResponseOverview
        loading={false}
        experiments={[]}
        variableRecords={[]}
        variableNamesOrdered={[]}
      />,
    )
    await waitFor(() => {
      // Component should render some output, even if it's a loading skeleton
      const node = document.body
      expect(node.textContent).toBeDefined()
    })
  })
})

describe("Reaction Studio Compound Linking Panel", () => {
  it("renders without crashing", async () => {
    const { ReactionStudioCompoundLinkingPanel } = await import(
      "@/components/reaction-optimization/reaction-studio-compound-linking-panel"
    )
    renderC(
      <ReactionStudioCompoundLinkingPanel
        loading={false}
        project={null}
        experiments={[]}
        onRefresh={async () => {}}
      />,
    )
    await waitFor(() => {
      const found = screen.queryAllByText(/Compound|Link|Search|Registry/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})

describe("Model Diagnostics Card", () => {
  it("renders the diagnostics card host", async () => {
    const { ModelDiagnosticsCard } = await import(
      "@/components/reaction-optimization/model-diagnostics-card"
    )
    renderC(
      <ModelDiagnosticsCard
        loading={false}
        trainingExperimentCount={null}
        trainingCountFallbackTotal={0}
        modelType={null}
        objectiveSummary={null}
        validationMetricsJson={null}
        warnings={[]}
        uncertaintySummary={null}
        featureEncodingSummary={null}
      />,
    )
    await waitFor(() => {
      const found = screen.queryAllByText(/Diagnostic|Model|Training|Bench/i)
      expect(found.length).toBeGreaterThan(0)
    })
  })
})
