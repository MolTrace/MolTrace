import { beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import { apiFetch } from "@/lib/api/client"
import { MlModelArtifactsList } from "@/components/ml/ml-model-artifacts-list"

vi.mock("@/lib/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/client")>("@/lib/api/client")
  return { ...actual, apiFetch: vi.fn() }
})

const apiFetchMock = vi.mocked(apiFetch)

const APPROVED_NOT_REGISTERED = {
  id: 11,
  model_name: "nmrnet-13c",
  model_version: "1.4.0",
  task_key: "nmr_shift_prediction",
  model_family: "graph_neural_network",
  status: "approved",
  registry_model_id: null,
  registry_status: null,
}

const SERVING = {
  id: 12,
  model_name: "nmrnet-13c",
  model_version: "1.5.0",
  task_key: "nmr_shift_prediction",
  model_family: "graph_neural_network",
  status: "approved",
  registry_model_id: "reg-99",
  registry_status: "production",
  registry_role: "nmrnet_checkpoint",
  registry_nucleus: "13C",
}

const RETIRED = {
  id: 13,
  model_name: "nmrnet-13c",
  model_version: "1.3.0",
  task_key: "nmr_shift_prediction",
  model_family: "graph_neural_network",
  status: "approved",
  registry_model_id: "reg-98",
  registry_status: "retired",
  registry_role: "nmrnet_checkpoint",
  registry_nucleus: "13C",
}

describe("MlModelArtifactsList — approved is not serving", () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it("shows approval and serving as two separate states", async () => {
    apiFetchMock.mockResolvedValue([APPROVED_NOT_REGISTERED, SERVING, RETIRED])
    render(<MlModelArtifactsList />)

    await waitFor(() => expect(screen.getByText("1.4.0")).toBeInTheDocument())

    // Two independent columns, so the table can no longer say only one of the two things.
    expect(screen.getByRole("columnheader", { name: "Approval" })).toBeInTheDocument()
    expect(screen.getByRole("columnheader", { name: "Serving" })).toBeInTheDocument()

    // All three rows are "approved"; only one of them answers predictions. Scoped to the
    // badge because the column header carries the same word.
    expect(screen.getAllByText("Approved", { selector: "span" })).toHaveLength(3)
    expect(screen.getByText("Serving", { selector: "span" })).toBeInTheDocument()
    expect(screen.getByText("Not serving", { selector: "span" })).toBeInTheDocument()
    expect(screen.getByText("Retired", { selector: "span" })).toBeInTheDocument()
  })

  it("says outright that an approved artifact is not answering predictions", async () => {
    apiFetchMock.mockResolvedValue([APPROVED_NOT_REGISTERED])
    render(<MlModelArtifactsList />)

    await waitFor(() => expect(screen.getByText("Not serving", { selector: "span" })).toBeInTheDocument())
    // The regression this column exists to prevent: "approved" reading as "deployed".
    expect(screen.getByText("Approved, not answering predictions.")).toBeInTheDocument()
  })

  it("names the role and nucleus scope a serving entry resolves for", async () => {
    apiFetchMock.mockResolvedValue([SERVING])
    render(<MlModelArtifactsList />)

    await waitFor(() => expect(screen.getByText("Serving", { selector: "span" })).toBeInTheDocument())
    expect(screen.getByText("nmrnet_checkpoint · 13C")).toBeInTheDocument()
    // No contradiction to flag when approval and the registry agree.
    expect(screen.queryByText("Approved, not answering predictions.")).not.toBeInTheDocument()
  })

  it("renders a row from before the registry fields without claiming it serves", async () => {
    apiFetchMock.mockResolvedValue([{ id: 4, model_name: "old", model_version: "0.1", status: "trained" }])
    render(<MlModelArtifactsList />)

    await waitFor(() => expect(screen.getByText("Not serving", { selector: "span" })).toBeInTheDocument())
    // The badge never reads bare "Serving" for an unregistered artifact.
    expect(screen.queryByText("Serving", { selector: "span" })).not.toBeInTheDocument()
  })
})
