import type { ReactElement } from "react"
import { describe, expect, it, vi, beforeEach } from "vitest"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { SpectraCheckMsEvidence } from "@/components/spectracheck/spectracheck-ms-evidence"
import { ApiError } from "@/lib/api/client"
import { SpectraCheckEvidenceProvider } from "@/src/lib/spectracheck/useSpectraCheckEvidence"

function renderSpectraCheckMsEvidence(ui: ReactElement) {
  return render(ui, {
    wrapper: ({ children }) => <SpectraCheckEvidenceProvider>{children}</SpectraCheckEvidenceProvider>,
  })
}

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

describe("SpectraCheckMsEvidence HRMS & formula", () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it("renders HRMS exact-mass candidate match card", () => {
    renderSpectraCheckMsEvidence(<SpectraCheckMsEvidence sampleId="S1" candidatesText="A | CCO" />)
    expect(screen.getByText("HRMS exact-mass candidate match")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Match candidates by HRMS" })).toBeInTheDocument()
  })

  it("renders Formula search beta card", async () => {
    const user = userEvent.setup()
    renderSpectraCheckMsEvidence(<SpectraCheckMsEvidence sampleId="S1" candidatesText="A | CCO" />)
    await user.click(screen.getByRole("tab", { name: "Formula search" }))
    expect(await screen.findByText("Formula search beta")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Search formulas" })).toBeInTheDocument()
  })

  it("submits HRMS match with FormData without setting Content-Type header on the request", async () => {
    apiFetchMock.mockResolvedValueOnce({
      observed_mz: 47.04914,
      adduct: { name: "[M+H]+" },
      candidate_count: 1,
      exact_match_count: 1,
      ranked_candidates: [],
    })
    renderSpectraCheckMsEvidence(<SpectraCheckMsEvidence sampleId="S1" candidatesText="Ethanol | CCO" />)
    fireEvent.click(screen.getByRole("button", { name: "Match candidates by HRMS" }))
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(1))
    const [, init] = apiFetchMock.mock.calls[0]
    expect(init?.method).toBe("POST")
    expect(init?.body).toBeInstanceOf(FormData)
    const fd = init?.body as FormData
    expect(fd.get("candidates_text")).toBe("Ethanol | CCO")
    expect(fd.get("observed_mz")).toBe("47.04914")
    expect(init?.headers == null || !(init.headers as Headers).has?.("content-type")).toBe(true)
  })

  it("posts formula search as JSON with required keys only", async () => {
    apiFetchMock.mockResolvedValueOnce({
      observed_mz: 47.04914,
      neutral_mass: 46.04,
      formula_count: 1,
      formulas: [{ formula: "CH4O", exact_mass: 32.0262, dbe: 0 }],
    })
    const user = userEvent.setup()
    renderSpectraCheckMsEvidence(<SpectraCheckMsEvidence sampleId="S1" candidatesText="A | CCO" />)
    await user.click(screen.getByRole("tab", { name: "Formula search" }))
    await user.click(await screen.findByRole("button", { name: "Search formulas" }))
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled())
    expect(apiFetchMock).toHaveBeenCalledWith("/ms/hrms/formulas/search", {
      method: "POST",
      body: JSON.stringify({
        observed_mz: 47.04914,
        adduct: "[M+H]+",
        ppm_tolerance: 5,
        max_c: 40,
        max_results: 50,
      }),
    })
  })

  it("renders extended HRMS table from mocked response", async () => {
    apiFetchMock.mockResolvedValueOnce({
      observed_mz: 47.04914,
      exact_match_count: 1,
      ranked_candidates: [
        {
          rank: 1,
          smiles: "CO",
          formula: "CH4O",
          theoretical_mz: 47.04914,
          ppm_error: 0.5,
          ppm_score: 0.99,
          dbe: 0,
        },
      ],
    })
    renderSpectraCheckMsEvidence(<SpectraCheckMsEvidence sampleId="S1" candidatesText="Methanol | CO" />)
    fireEvent.click(screen.getByRole("button", { name: "Match candidates by HRMS" }))
    expect(await screen.findByText("Exact mass matches within tolerance:")).toBeInTheDocument()
    expect(screen.getByText("Candidate metrics")).toBeInTheDocument()
    expect(screen.getByText("CO")).toBeInTheDocument()
  })

  it("renders Adduct + isotope pattern inference card and infer button", async () => {
    const user = userEvent.setup()
    renderSpectraCheckMsEvidence(<SpectraCheckMsEvidence sampleId="S1" candidatesText="A | CCO" />)
    await user.click(screen.getByRole("tab", { name: "Adduct + isotope" }))
    expect(await screen.findByText("Adduct + isotope pattern inference")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Infer adducts + isotopes" })).toBeInTheDocument()
  })

  it("renders isotope clusters from mocked adduct inference response", async () => {
    apiFetchMock.mockResolvedValueOnce({
      ion_mode: "positive",
      peak_count: 3,
      analyzed_peak_count: 3,
      primary_mz: 47.04914,
      inferred_charge: 1,
      inferred_m_plus_1_percent: 2,
      inferred_m_plus_2_percent: 0.5,
      best_adduct_candidate: {
        rank: 1,
        label: "plausible_adduct",
        adduct: { name: "[M+H]+", ion_mode: "positive", charge: 1, mass_shift: 1.0078, description: "" },
        observed_mz: 47.04914,
        neutral_mass: 31.01839,
        formula_count: 0,
        top_formulas: [],
        candidate_score: 0.95,
        evidence_summary: [],
        warnings: [],
        metadata: {},
      },
      adduct_candidates: [],
      isotope_clusters: [
        {
          monoisotopic_mz: 47.04914,
          charge: 1,
          label: "clear_isotope_cluster",
          confidence_score: 0.88,
          m_plus_1_percent: 2,
          m_plus_2_percent: 0.5,
          estimated_carbon_count: 1,
          halogen_signature: "unknown",
          peaks: [
            {
              isotope_label: "M",
              mz: 47.04914,
              expected_mz: 47.04914,
              delta_da: 0,
              relative_intensity: 100,
              ppm_error: 0.1,
              spacing_from_m0_da: 0,
            },
          ],
          evidence_summary: [],
          warnings: [],
          metadata: {},
        },
      ],
      warnings: [],
      notes: [],
      metadata: {},
    })
    const user = userEvent.setup()
    renderSpectraCheckMsEvidence(<SpectraCheckMsEvidence sampleId="S1" candidatesText="A | CCO" />)
    await user.click(screen.getByRole("tab", { name: "Adduct + isotope" }))
    await user.click(await screen.findByRole("button", { name: "Infer adducts + isotopes" }))
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled())
    const [path, init] = apiFetchMock.mock.calls[0]
    expect(path).toBe("/ms/adducts/infer/evidence")
    expect(init).toMatchObject({ method: "POST" })
    expect(init?.body).toBeInstanceOf(FormData)
    expect(await screen.findByText("Isotope clusters")).toBeInTheDocument()
    expect(screen.getByText("clear_isotope_cluster")).toBeInTheDocument()
  })

  it("renders Processed MS/MS annotation card and Annotate MS/MS button", async () => {
    const user = userEvent.setup()
    renderSpectraCheckMsEvidence(<SpectraCheckMsEvidence sampleId="S1" candidatesText="Ethanol | CCO" />)
    await user.click(screen.getByRole("tab", { name: "Processed MS/MS" }))
    expect(await screen.findByText("Processed MS/MS annotation")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Annotate MS/MS" })).toBeInTheDocument()
  })

  it("renders fragmentation-tree card and Build fragmentation tree button", async () => {
    const user = userEvent.setup()
    renderSpectraCheckMsEvidence(<SpectraCheckMsEvidence sampleId="S1" candidatesText="A | CCO" />)
    await user.click(screen.getByRole("tab", { name: "Fragmentation tree" }))
    expect(await screen.findByText("MS/MS fragmentation-tree reasoning")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Build fragmentation tree" })).toBeInTheDocument()
  })

  it("renders MS/MS neutral-loss and ranked tables from mocked response", async () => {
    apiFetchMock.mockResolvedValueOnce({
      precursor_mz: 181.07066,
      adduct: { name: "[M+H]+" },
      mz_tolerance_da: 0.02,
      ppm_tolerance: 20,
      peak_count: 3,
      annotated_peak_count: 3,
      candidate_count: 1,
      neutral_loss_hits: [
        {
          fragment_mz: 163.06,
          intensity: 1,
          relative_intensity: 30,
          loss_name: "H2O",
          observed_loss_da: 18.01,
          expected_loss_da: 18.01,
          error_da: 0.001,
          interpretation: "Test loss",
        },
      ],
      best_candidate: {
        rank: 1,
        smiles: "CCO",
        label: "consistent_with_msms",
        precursor_ppm_error: 1.2,
        precursor_score: 0.9,
        explained_peak_count: 2,
        explained_intensity_fraction: 0.45,
        fragment_matches: [
          {
            peak_mz: 45.0,
            intensity: 1,
            relative_intensity: 20,
            theoretical_mz: 45.0,
            ppm_error: 2,
            formula: "C2H5",
            fragment_type: "acyl",
            explanation: "Test match",
          },
        ],
        candidate_score: 0.85,
      },
      ranked_candidates: [
        {
          rank: 1,
          smiles: "CCO",
          label: "partial_msms_support",
          explained_peak_count: 1,
          explained_intensity_fraction: 0.3,
          candidate_score: 0.5,
        },
      ],
      warnings: ["Mock warning for review"],
      notes: ["Mock note"],
    })
    const user = userEvent.setup()
    renderSpectraCheckMsEvidence(<SpectraCheckMsEvidence sampleId="S1" candidatesText="Ethanol | CCO" />)
    await user.click(screen.getByRole("tab", { name: "Processed MS/MS" }))
    await user.click(await screen.findByRole("button", { name: "Annotate MS/MS" }))
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled())
    expect(await screen.findByText("Neutral-loss hits")).toBeInTheDocument()
    expect(screen.getByText("H2O")).toBeInTheDocument()
    expect(screen.getByText("Ranked candidate support")).toBeInTheDocument()
  })

  it("renders fragmentation tree edge table, warnings, and contradiction flags from mocked response", async () => {
    apiFetchMock.mockResolvedValueOnce({
      precursor_mz: 47.04914,
      adduct: { name: "[M+H]+" },
      peak_count: 2,
      analyzed_peak_count: 2,
      candidate_count: 1,
      best_candidate: {
        rank: 1,
        smiles: "CO",
        label: "weak_fragmentation_tree_support",
        tree_score: 0.4,
        precursor_score: 0.5,
        explained_intensity_fraction: 0.3,
        diagnostic_loss_count: 1,
        contradiction_count: 1,
        max_tree_depth: 2,
        edges: [
          {
            parent_id: "n0",
            child_id: "n1",
            relation_type: "neutral_loss",
            loss_name: "H2O",
            observed_loss_da: 18.01,
            explanation: "Test edge",
            diagnostic: true,
            chemically_plausible: true,
            metadata: {},
          },
        ],
        diagnostic_hits: [
          {
            loss_name: "H2O",
            fragment_mz: 29.0,
            observed_loss_da: 18.01,
            expected_loss_da: 18.01,
            relative_intensity: 20,
            chemically_plausible: true,
            diagnostic_class: "dehydration",
            interpretation: "diagnostic test",
          },
        ],
        contradiction_flags: ["Substructure mismatch under review"],
      },
      warnings: ["Tree is hypothesis-level only"],
      notes: [],
      metadata: {},
    })
    const user = userEvent.setup()
    renderSpectraCheckMsEvidence(<SpectraCheckMsEvidence sampleId="S1" candidatesText="A | CCO" />)
    await user.click(screen.getByRole("tab", { name: "Fragmentation tree" }))
    await user.click(await screen.findByRole("button", { name: "Build fragmentation tree" }))
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled())
    expect(await screen.findByText("Edge table")).toBeInTheDocument()
    expect(screen.getByText("Contradiction flags")).toBeInTheDocument()
    expect(screen.getAllByText("Substructure mismatch under review").length).toBeGreaterThan(0)
    expect(screen.getAllByText("Tree is hypothesis-level only").length).toBeGreaterThan(0)
  })

  it("renders LC-MS import bridge card", async () => {
    const user = userEvent.setup()
    renderSpectraCheckMsEvidence(<SpectraCheckMsEvidence sampleId="S1" candidatesText="A | CCO" />)
    await user.click(screen.getByRole("tab", { name: "LC-MS import" }))
    expect(await screen.findByText(/Raw LC-MS\/MS mzML \+ processed peak import bridge/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Import LC-MS/MS" })).toBeInTheDocument()
  })

  it("renders LC-MS feature detection card", async () => {
    const user = userEvent.setup()
    renderSpectraCheckMsEvidence(<SpectraCheckMsEvidence sampleId="S1" candidatesText="A | CCO" />)
    await user.click(screen.getByRole("tab", { name: "LC-MS features" }))
    expect(await screen.findByText(/LC-MS feature detection \+ EIC\/XIC \+ peak purity/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Detect features + XICs" })).toBeInTheDocument()
  })

  it("exposes file upload inputs on LC-MS tabs", async () => {
    const user = userEvent.setup()
    const { container } = renderSpectraCheckMsEvidence(<SpectraCheckMsEvidence sampleId="S1" candidatesText="A | CCO" />)
    await user.click(screen.getByRole("tab", { name: "LC-MS import" }))
    expect(container.querySelectorAll('input[type="file"]').length).toBeGreaterThanOrEqual(1)
    await user.click(screen.getByRole("tab", { name: "LC-MS features" }))
    expect(container.querySelectorAll('input[type="file"]').length).toBeGreaterThanOrEqual(1)
  })

  it("renders feature table from mocked LC-MS feature detection response", async () => {
    const purity = {
      feature_id: "f1",
      target_mz: 200,
      apex_rt_min: 1.2,
      rt_window_start_min: 0.5,
      rt_window_end_min: 1.9,
      purity_percent: 95,
      label: "high_purity",
      top_coeluting_ions: [],
      warnings: [],
    }
    const peak = {
      feature_id: "f1",
      target_mz: 200,
      observed_mz: 200.0105,
      apex_rt_min: 1.2,
      start_rt_min: 0.5,
      end_rt_min: 1.9,
      apex_intensity: 1000,
      area: 5000,
      width_min: 0.2,
      scan_count: 3,
      signal_to_noise: 10,
      purity,
      linked_msms_spectra: [{ scan_id: "ms2-1", precursor_mz: 200.01, retention_time_min: 1.21, precursor_error_da: 0.001, precursor_error_ppm: 5, peak_count: 12, total_ion_current: 100 }],
      label: "clean_feature",
      evidence_summary: [],
      warnings: [],
    }
    apiFetchMock.mockResolvedValueOnce({
      filename: "demo.csv",
      source_format: "csv",
      file_sha256: "abcd",
      immutable_raw_data: true,
      label: "ready_for_downstream_ms",
      scan_count: 10,
      ms1_scan_count: 5,
      ms2_scan_count: 5,
      target_count: 1,
      feature_count: 1,
      clean_feature_count: 1,
      coeluting_feature_count: 0,
      weak_feature_count: 0,
      best_feature: peak,
      features: [peak],
      xic_points: [{ target_mz: 200, scan_id: "s1", retention_time_min: 1.0, intensity: 1, relative_intensity: 50 }],
      chromatogram: [],
      recommended_next_actions: [],
      warnings: [],
      notes: [],
      metadata: {},
    })
    const user = userEvent.setup()
    const { container } = renderSpectraCheckMsEvidence(<SpectraCheckMsEvidence sampleId="S1" candidatesText="A | CCO" />)
    await user.click(screen.getByRole("tab", { name: "LC-MS features" }))
    const files = container.querySelectorAll('input[type="file"]')
    const featureFileInput = files[files.length - 1]
    expect(featureFileInput).toBeTruthy()
    await user.upload(featureFileInput as HTMLInputElement, new File(["x"], "demo.csv", { type: "text/csv" }))
    await user.click(screen.getByRole("button", { name: "Detect features + XICs" }))
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled())
    expect(await screen.findByText("Feature table")).toBeInTheDocument()
    expect(screen.getAllByText("f1").length).toBeGreaterThan(0)
  })

  it("renders advanced LC-MS grouping, consensus, dereplication, and bridge tabs", async () => {
    const user = userEvent.setup()
    renderSpectraCheckMsEvidence(<SpectraCheckMsEvidence sampleId="S1" candidatesText="A | CCO" />)
    await user.click(screen.getByRole("tab", { name: "LC-MS grouping" }))
    expect(await screen.findByText(/Feature grouping \+ blank subtraction \+ RT alignment/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Group features" })).toBeInTheDocument()
    await user.click(screen.getByRole("tab", { name: "LC-MS consensus" }))
    expect(await screen.findByText(/LC-MS isotope\/adduct consensus \+ feature-family confidence/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Score feature-family consensus" })).toBeInTheDocument()
    await user.click(screen.getByRole("tab", { name: "LC-MS dereplication" }))
    expect(await screen.findByText(/LC-MS\/MS library dereplication \+ candidate seed retrieval/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Run dereplication" })).toBeInTheDocument()
    await user.click(screen.getByRole("tab", { name: "LC-MS bridge" }))
    expect(await screen.findByText(/LC-MS consensus → unified confidence bridge/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Bridge LC-MS evidence to candidate confidence" })).toBeInTheDocument()
  })

  it("renders promoted feature family table from mocked consensus response", async () => {
    apiFetchMock.mockResolvedValueOnce({
      label: "ready_for_candidate_scoring",
      input_group_count: 2,
      family_count: 1,
      promoted_family_count: 1,
      conflicting_family_count: 0,
      relationship_count: 0,
      families: [
        {
          family_id: "fam1",
          anchor_group_id: "g1",
          anchor_mz: 200.1,
          anchor_rt_min: 1.5,
          label: "high_confidence_feature_family",
          promoted_for_candidate_scoring: true,
          consensus_score: 0.88,
          evidence_layer_count: 3,
          contradiction_count: 0,
          relationship_count: 0,
          member_count: 2,
          members: [],
          relationships: [],
          layer_scores: [],
          evidence_summary: [],
          warnings: [],
        },
      ],
      best_family: null,
      family_table_text: "",
      recommended_next_actions: [],
      warnings: [],
      notes: [],
      metadata: {},
    })
    const user = userEvent.setup()
    renderSpectraCheckMsEvidence(<SpectraCheckMsEvidence sampleId="S1" candidatesText="A | CCO" />)
    await user.click(screen.getByRole("tab", { name: "LC-MS consensus" }))
    await user.type(await screen.findByPlaceholderText(/Paste feature_table_text from grouping/), "group_id\nx\n")
    await user.click(screen.getByRole("button", { name: "Score feature-family consensus" }))
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalled())
    expect(await screen.findByText("Promoted feature family table")).toBeInTheDocument()
    expect(screen.getByText("fam1")).toBeInTheDocument()
  })

  it("shows backend-unavailable message when LC-MS grouping endpoint returns 404", async () => {
    apiFetchMock.mockRejectedValueOnce(new ApiError(404, { detail: "Not Found" }))
    const user = userEvent.setup()
    renderSpectraCheckMsEvidence(<SpectraCheckMsEvidence sampleId="S1" candidatesText="A | CCO" />)
    await user.click(screen.getByRole("tab", { name: "LC-MS grouping" }))
    await user.type(await screen.findByPlaceholderText(/Feature or peak list text/), "mz,rt\n100,1")
    await user.click(screen.getByRole("button", { name: "Group features" }))
    expect(await screen.findByText("Backend endpoint not available yet.")).toBeInTheDocument()
  })
})
