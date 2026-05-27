import { readFileSync } from "node:fs"
import path from "node:path"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { DeploymentSettingsWorkspace } from "@/components/settings/deployment-settings-workspace"

const mockApiFetch = vi.fn<(path: string, init?: unknown) => Promise<unknown>>()

function readJsonContract(relativePath: string): Record<string, unknown> {
  const candidates = [
    path.resolve(process.cwd(), relativePath),
    path.resolve(process.cwd(), "..", relativePath),
  ]
  for (const candidate of candidates) {
    try {
      return JSON.parse(readFileSync(candidate, "utf8")) as Record<string, unknown>
    } catch {
      // Try the next working-directory layout.
    }
  }
  throw new Error(`Unable to load JSON contract ${relativePath}`)
}

const rawFidPromptSidecarSmoke = readJsonContract(
  "tests/contracts/release-health/raw_fid_prompt_sidecar_smoke.v1.json",
).raw_fid_prompt_sidecar_smoke as Record<string, unknown>

vi.mock("@/components/app/backend-status-indicator", () => ({
  BackendStatusIndicator: () => <span>Backend status</span>,
}))

vi.mock("@/lib/api/client", () => ({
  API_BASE: "/api",
  ApiError: class MockApiError extends Error {
    data?: unknown
    constructor(message: string, data?: unknown) {
      super(message)
      this.data = data
    }
  },
  apiFetch: (path: string, init?: unknown) => mockApiFetch(path, init),
}))

describe("DeploymentSettingsWorkspace release diagnostics", () => {
  beforeEach(() => {
    mockApiFetch.mockReset()
    mockApiFetch.mockImplementation(async (path: string) => {
      if (path === "/system/environment-check") {
        return {
          environment: "test",
          required_variables_present: true,
          missing_variables: [],
          unsafe_variables: [],
          public_variables: {},
        }
      }
      if (path === "/system/version") {
        return {
          api_version: "test-api",
          backend_version: "test-backend",
          environment: "test",
          timestamp: "2026-05-24T00:00:00Z",
        }
      }
      if (path === "/system/dependencies") return []
      if (path === "/admin/release-health") {
        return {
          raw_fid_prompt_sidecar_smoke: rawFidPromptSidecarSmoke,
        }
      }
      if (path === "/admin/raw-fid/prompt-sidecar/fixture-report?limit=1&include_varian=false") {
        return {
          version: "raw_fid_prompt_sidecar_fixture_report_v1",
          route_policy: "admin_diagnostic_reporting_only",
          activation_policy: "reporting_only_no_runtime_wiring",
          active_visible_pipeline: "legacy",
          prompt_pipeline_active: false,
          fixture_count: 1,
          provenance: {
            version: "raw_fid_prompt_report_provenance_v1",
            route_policy: "admin_diagnostic_reporting_only",
            parameters: { include_varian: false, limit: 1, strict: false },
            fixture_count: 1,
            row_count: 1,
            fixture_identity_sha256:
              "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            row_fingerprint_sha256:
              "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            row_payload_sha256:
              "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
            shadow_comparison_sha256:
              "9999999999999999999999999999999999999999999999999999999999999999",
            report_payload_sha256:
              "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
            runtime_effect_sha256:
              "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
            requested_by_sha256:
              "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
          },
          reporting_only_smoke: {
            passed: true,
            failure_count: 0,
            failures: [],
          },
          shadow_comparison_summary: {
            version: "raw_fid_prompt_shadow_comparison_v1",
            visibility: "admin_diagnostic_only",
            reporting_policy: "read_only_shadow_comparison_no_runtime_activation",
            status: "review_required",
            decision_guidance: "review_required_before_any_manual_promotion",
            active_visible_pipeline: "legacy",
            prompt_pipeline_active: false,
            runtime_activation_allowed: false,
            fixture_count: 1,
            prompt_sidecar_available: 1,
            prompt_sidecar_unavailable: 0,
            reference_rows: 1,
            ppm_reference_rows: 1,
            prompt_peak_count_within_reference_tolerance: 0,
            prompt_peak_count_review_required: 1,
            prompt_reference_ppm_within_tolerance: 1,
            prompt_reference_ppm_review_required: 0,
            prompt_runtime_within_target: 1,
            prompt_runtime_review_required: 0,
            row_status_counts: { review_required: 1 },
            activation_status_counts: { review_required: 1 },
            max_peak_count_delta_legacy_prompt: 1,
            max_prompt_reference_peak_count_delta: 1,
            max_prompt_reference_ppm_error: 0.002,
            max_phase_delta_degrees: 3.4,
            max_baseline_rmse_fraction_full_scale: 0.002,
            max_prompt_runtime_ms: 42,
            review_fixture_ids: ["nmrshiftdb2-bruker-001"],
            runtime_effect: {
              spectracheck_visible_pipeline: "unchanged_legacy",
              processed_spectrum_pipeline: "unchanged",
              raw_fid_plotting: "unchanged",
              prompt_sidecar_runtime: "diagnostic_only",
            },
          },
          activation_readiness: {
            version: "raw_fid_prompt_activation_readiness_v1",
            visibility: "admin_diagnostic_only",
            active_visible_pipeline: "legacy",
            prompt_pipeline_active: false,
            activation_allowed: false,
            overall_status: "review_required",
            gate_count: 2,
            activation_policy:
              "blocked_until_all_gates_pass_and_a_separate_manual_promotion_is_implemented",
            gates: [
              {
                name: "ppm_axis_alignment",
                status: "passed",
                target: "Prompt and legacy ppm range endpoints must agree within 0.01 ppm.",
                passed: 1,
                review_required: 0,
                failed: 0,
              },
              {
                name: "phase_delta",
                status: "review_required",
                target: "Prompt phase angle delta must be within 5 degrees.",
                passed: 0,
                review_required: 1,
                failed: 0,
              },
            ],
          },
          promotion_gate: {
            version: "raw_fid_prompt_manual_promotion_gate_v1",
            visibility: "ci_admin_gate_only",
            status: "blocked",
            eligible_for_manual_promotion: false,
            runtime_activation_allowed: false,
            active_visible_pipeline: "legacy",
            prompt_pipeline_active: false,
            failure_count: 1,
            failures: ["activation_readiness_status:review_required"],
            ci_command:
              "PYTHONPATH=src uv run moltrace-raw-fid-sidecar-report --limit 20 --include-varian --quiet --promotion-gate",
          },
          rows: [
            {
              fixture_id: "nmrshiftdb2-bruker-001",
              archive: "raw/nmrshiftdb2-bruker-001.zip",
              archive_sha256: "1111111111111111111111111111111111111111111111111111111111111111",
              archive_size_bytes: 12345,
              nucleus: "13C",
              legacy_peak_count: 10,
              prompt_peak_count: 11,
              reference_peak_count: 12,
              safe_to_activate: false,
              activation_readiness_status: "review_required",
              validation_visibility: "hidden_metadata_only",
            },
          ],
        }
      }
      throw new Error(`Unexpected path ${path}`)
    })
  })

  it("shows the raw FID sidecar smoke as reporting-only and inactive", async () => {
    render(<DeploymentSettingsWorkspace />)

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith("/admin/release-health", { method: "GET" })
      expect(screen.getByText("Prompt 1/2 sidecar smoke")).toBeInTheDocument()
    })

    expect(screen.getByText("reporting_only_no_runtime_wiring")).toBeInTheDocument()
    expect(screen.getByText(/active visible pipeline legacy/)).toBeInTheDocument()
    expect(screen.getByText(/prompt active false/)).toBeInTheDocument()
    expect(screen.getByText("guardrail_only_not_scientific_review_rows")).toBeInTheDocument()
    expect(screen.getByText("manual promotion gate")).toBeInTheDocument()
    expect(screen.getByText("ci_admin_gate_only_no_runtime_activation")).toBeInTheDocument()
    expect(screen.getAllByText("ci_artifact_and_admin_release_health_only").length).toBeGreaterThanOrEqual(4)
    expect(screen.getByText("raw-fid-prompt-manual-promotion-gate")).toBeInTheDocument()
    expect(screen.getAllByText(/runtime activation allowed false/).length).toBeGreaterThanOrEqual(4)
    expect(screen.getByText("manual promotion design")).toBeInTheDocument()
    expect(screen.getByText("design_doc_no_runtime_activation")).toBeInTheDocument()
    expect(screen.getByText("docs/raw_fid_prompt_manual_promotion_design.md")).toBeInTheDocument()
    expect(screen.getByText("./scripts/run_prompt_sidecar_guardrails.sh")).toBeInTheDocument()
    expect(screen.getByText("MOLTRACE_RAW_FID_PIPELINE=legacy")).toBeInTheDocument()
    expect(screen.getByText(/prompt_sidecar_available/)).toBeInTheDocument()
    expect(screen.getByText(/stage_0_metadata_only_current_state/)).toBeInTheDocument()
    expect(screen.getByText("provenance checksum artifact")).toBeInTheDocument()
    expect(screen.getByText("checksum_export_no_runtime_activation")).toBeInTheDocument()
    expect(screen.getByText("raw-fid-prompt-provenance-checksums")).toBeInTheDocument()
    expect(screen.getByText("$RUNNER_TEMP/raw_fid_prompt_provenance_checksums")).toBeInTheDocument()
    expect(
      screen.getByText(
        "raw_fid_prompt_sidecar_fixture_report.json, raw_fid_prompt_sidecar_fixture_report.csv, raw_fid_prompt_sidecar_provenance_checksums.json, raw_fid_prompt_sidecar_provenance_checksums.csv",
      ),
    ).toBeInTheDocument()
    expect(screen.getByText("shadow comparison artifact")).toBeInTheDocument()
    expect(screen.getByText("shadow_comparison_export_no_runtime_activation")).toBeInTheDocument()
    expect(screen.getByText("raw-fid-prompt-shadow-comparison")).toBeInTheDocument()
    expect(screen.getByText("$RUNNER_TEMP/raw_fid_prompt_shadow_comparison")).toBeInTheDocument()
    expect(
      screen.getByText(
        "raw_fid_prompt_shadow_comparison_summary.json, raw_fid_prompt_shadow_comparison_summary.csv",
      ),
    ).toBeInTheDocument()
    expect(screen.getByText("release readiness artifact")).toBeInTheDocument()
    expect(screen.getByText("release_readiness_markdown_no_runtime_activation")).toBeInTheDocument()
    expect(screen.getByText("raw-fid-prompt-release-readiness")).toBeInTheDocument()
    expect(screen.getByText("$RUNNER_TEMP/raw_fid_prompt_release_readiness")).toBeInTheDocument()
    expect(screen.getByText("raw_fid_prompt_release_readiness.md")).toBeInTheDocument()
    expect(screen.getByText("processed_spectrum_pipeline")).toBeInTheDocument()
    expect(screen.getAllByText("unchanged").length).toBeGreaterThanOrEqual(3)
  })

  it("runs the read-only fixture smoke report on demand", async () => {
    render(<DeploymentSettingsWorkspace />)

    await waitFor(() => {
      expect(screen.getByText("Prompt 1/2 sidecar smoke")).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole("button", { name: /run fixture smoke report/i }))

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/admin/raw-fid/prompt-sidecar/fixture-report?limit=1&include_varian=false",
        { method: "GET" },
      )
      expect(screen.getByText(/report raw_fid_prompt_sidecar_fixture_report_v1/)).toBeInTheDocument()
    })

    expect(screen.getAllByText("admin_diagnostic_reporting_only").length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText(/smoke passed true/)).toBeInTheDocument()
    expect(screen.getByText(/promotion gate raw_fid_prompt_manual_promotion_gate_v1/)).toBeInTheDocument()
    expect(screen.getByText(/status blocked/)).toBeInTheDocument()
    expect(screen.getByText(/eligible false/)).toBeInTheDocument()
    expect(screen.getByText("activation_readiness_status:review_required")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /download json report/i })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /download csv rows/i })).toBeInTheDocument()
    expect(screen.getByText(/local export of this read-only diagnostic response/i)).toBeInTheDocument()
    expect(screen.getByText(/provenance raw_fid_prompt_report_provenance_v1/)).toBeInTheDocument()
    expect(screen.getByText(/checksums identify the exact fixture set/i)).toBeInTheDocument()
    expect(
      screen.getByText("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
    ).toBeInTheDocument()
    expect(
      screen.getByText("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"),
    ).toBeInTheDocument()
    expect(
      screen.getByText("dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"),
    ).toBeInTheDocument()
    expect(
      screen.getByText("9999999999999999999999999999999999999999999999999999999999999999"),
    ).toBeInTheDocument()
    expect(
      screen.getByText("eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"),
    ).toBeInTheDocument()
    expect(screen.getByText('{"include_varian":false,"limit":1,"strict":false}')).toBeInTheDocument()
    expect(screen.getByText(/shadow comparison raw_fid_prompt_shadow_comparison_v1/)).toBeInTheDocument()
    expect(screen.getByText("read_only_shadow_comparison_no_runtime_activation")).toBeInTheDocument()
    expect(screen.getByText("review_required_before_any_manual_promotion")).toBeInTheDocument()
    expect(screen.getAllByText(/runtime activation allowed false/).length).toBeGreaterThanOrEqual(3)
    expect(screen.getByText(/"prompt_sidecar_runtime":"diagnostic_only"/)).toBeInTheDocument()
    expect(screen.getByText(/readiness review_required/)).toBeInTheDocument()
    expect(screen.getAllByText(/activation allowed false/).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/raw_fid_prompt_activation_readiness_v1/)).toBeInTheDocument()
    expect(screen.getByText("ppm_axis_alignment")).toBeInTheDocument()
    expect(screen.getByText("phase_delta")).toBeInTheDocument()
    expect(screen.getAllByText("review_required").length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText("nmrshiftdb2-bruker-001").length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText("hidden_metadata_only")).toBeInTheDocument()
  })

  it("downloads the current read-only fixture report as local JSON and CSV", async () => {
    const createObjectURL = vi.fn(() => "blob:raw-fid-sidecar-report")
    const revokeObjectURL = vi.fn()
    Object.defineProperty(window.URL, "createObjectURL", { configurable: true, value: createObjectURL })
    Object.defineProperty(window.URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL })
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {})

    render(<DeploymentSettingsWorkspace />)

    await waitFor(() => {
      expect(screen.getByText("Prompt 1/2 sidecar smoke")).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole("button", { name: /run fixture smoke report/i }))

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /download json report/i })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole("button", { name: /download json report/i }))
    fireEvent.click(screen.getByRole("button", { name: /download csv rows/i }))

    expect(clickSpy).toHaveBeenCalledTimes(2)
    expect(createObjectURL).toHaveBeenCalledTimes(2)
    expect(revokeObjectURL).toHaveBeenCalledTimes(2)
    await expect((createObjectURL.mock.calls[0]?.[0] as Blob).text()).resolves.toContain(
      "raw_fid_prompt_sidecar_fixture_report_v1",
    )
    await expect((createObjectURL.mock.calls[0]?.[0] as Blob).text()).resolves.toContain(
      "raw_fid_prompt_report_provenance_v1",
    )
    await expect((createObjectURL.mock.calls[1]?.[0] as Blob).text()).resolves.toContain(
      "nmrshiftdb2-bruker-001",
    )
    await expect((createObjectURL.mock.calls[1]?.[0] as Blob).text()).resolves.toContain("archive_sha256")
    await expect((createObjectURL.mock.calls[1]?.[0] as Blob).text()).resolves.toContain(
      "1111111111111111111111111111111111111111111111111111111111111111",
    )

    clickSpy.mockRestore()
  })
})
