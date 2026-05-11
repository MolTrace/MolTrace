import { describe, expect, it, vi, beforeEach } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { AiModulePredictionAugmentation } from "@/components/ai/ai-module-prediction-augmentation"

/**
 * Strong baseline render + interaction tests for the centralized
 * AiModulePredictionAugmentation component used across all 4 module variants.
 *
 * These guard the component contract end-to-end so the redesign cannot:
 *   - drop the "Run approved AI model" button
 *   - drop the safety alert ("Use IDs and summaries only…")
 *   - break the service-key dropdown wiring
 *   - change the POST /ai/predictions request body shape
 *   - drop the IDs / experimental-mode / notes fields
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
  usePathname: () => "/regulatory/dossiers/1",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({}),
}))

const REGULATORY_PROPS = {
  moduleKey: "regulatory" as const,
  moduleTitle: "Regulatory Dossier",
  serviceOptions: [
    {
      id: "regulatory-extraction-classifier",
      label: "regulatory extraction classifier",
      serviceKey: "regulatory_extraction_classifier",
      taskKey: "regulatory_extraction_classification",
    },
  ],
}
const REACTION_PROPS = {
  moduleKey: "reaction_optimization" as const,
  moduleTitle: "Reaction Studio (project-level)",
  serviceOptions: [
    {
      id: "reaction-outcome-predictor",
      label: "reaction outcome predictor",
      serviceKey: "reaction_outcome_predictor",
      taskKey: "reaction_outcome_prediction",
    },
  ],
}
const KNOWLEDGE_PROPS = {
  moduleKey: "knowledge_extraction" as const,
  moduleTitle: "Knowledge",
  serviceOptions: [
    {
      id: "record-quality-scorer",
      label: "record quality scorer",
      serviceKey: "knowledge_record_quality_scorer",
      taskKey: "record_quality_scoring",
    },
  ],
}
const SPECTRACHECK_PROPS = {
  moduleKey: "spectracheck" as const,
  moduleTitle: "SpectraCheck",
  serviceOptions: [
    {
      id: "evidence-confidence-scorer",
      label: "evidence confidence scorer",
      serviceKey: "spectracheck_evidence_confidence_scorer",
      taskKey: "evidence_confidence_scoring",
    },
  ],
}

beforeEach(() => {
  apiFetchMock.mockReset()
  apiFetchMock.mockResolvedValue({})
})

describe("AiModulePredictionAugmentation — contract preservation", () => {
  it("renders the module-titled card title for all 4 variants", () => {
    const { unmount: u1 } = render(<AiModulePredictionAugmentation {...REGULATORY_PROPS} />)
    expect(screen.getByText(/Regulatory Dossier: Optional controlled AI prediction/i)).toBeInTheDocument()
    u1()

    const { unmount: u2 } = render(<AiModulePredictionAugmentation {...REACTION_PROPS} />)
    expect(screen.getByText(/Reaction Studio \(project-level\): Optional controlled AI prediction/i)).toBeInTheDocument()
    u2()

    const { unmount: u3 } = render(<AiModulePredictionAugmentation {...KNOWLEDGE_PROPS} />)
    expect(screen.getByText(/Knowledge: Optional controlled AI prediction/i)).toBeInTheDocument()
    u3()

    render(<AiModulePredictionAugmentation {...SPECTRACHECK_PROPS} />)
    expect(screen.getByText(/SpectraCheck: Optional controlled AI prediction/i)).toBeInTheDocument()
  })

  it("renders the 'Run approved AI model' button + safety alert", () => {
    render(<AiModulePredictionAugmentation {...REGULATORY_PROPS} />)
    expect(screen.getByRole("button", { name: /Run approved AI model/i })).toBeInTheDocument()
    expect(screen.getByText(/Use IDs and summaries only/i)).toBeInTheDocument()
  })

  it("renders the input fields (artifact / evidence / compound / session IDs + notes + JSON)", () => {
    render(<AiModulePredictionAugmentation {...REGULATORY_PROPS} />)
    // Use case-insensitive partial regex since labels use lowercase + 'optional' suffix
    expect(screen.getByText(/^artifact ID/i)).toBeInTheDocument()
    expect(screen.getByText(/^evidence item ID/i)).toBeInTheDocument()
    expect(screen.getByText(/^compound ID/i)).toBeInTheDocument()
    expect(screen.getByText(/^session ID/i)).toBeInTheDocument()
    expect(screen.getByText(/^input summary JSON/i)).toBeInTheDocument()
    expect(screen.getByText(/^notes/i)).toBeInTheDocument()
    expect(screen.getByText(/^experimental mode/i)).toBeInTheDocument()
  })

  it("submits POST /ai/predictions with the correct module/service/task keys when Run is clicked", async () => {
    const user = userEvent.setup()
    render(<AiModulePredictionAugmentation {...REGULATORY_PROPS} />)
    await user.click(screen.getByRole("button", { name: /Run approved AI model/i }))
    await waitFor(() =>
      expect(
        apiFetchMock.mock.calls.find(([endpoint]) => endpoint === "/ai/predictions"),
      ).toBeDefined(),
    )
    const predictionCall = apiFetchMock.mock.calls.find(([endpoint]) => endpoint === "/ai/predictions")
    expect(predictionCall).toBeDefined()
    const [, init] = predictionCall as [string, { method?: string; body?: unknown }]
    expect(init?.method).toBe("POST")
    const body = init?.body as Record<string, unknown>
    expect(body.service_key).toBe("regulatory_extraction_classifier")
    expect(body.target_module).toBe("regulatory")
    expect(body.task_key).toBe("regulatory_extraction_classification")
    expect(body.experimental_mode).toBe(false)
    // input_summary_json should be a parsed object, not a string
    expect(typeof body.input_summary_json).toBe("object")
  })
})
