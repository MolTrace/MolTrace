import { readFileSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"
import { parseReleaseHealthDiagnostics } from "@/src/lib/admin/release-health"

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

describe("parseReleaseHealthDiagnostics", () => {
  it("parses the shared raw FID prompt sidecar contract into stable frontend fields", () => {
    const contract = readJsonContract("tests/contracts/release-health/raw_fid_prompt_sidecar_smoke.v1.json")

    const diagnostics = parseReleaseHealthDiagnostics(contract)
    const smoke = diagnostics.rawFidPromptSidecarSmoke

    expect(smoke).not.toBeNull()
    expect(smoke?.policy).toBe("reporting_only_no_runtime_wiring")
    expect(smoke?.activeVisiblePipeline).toBe("legacy")
    expect(smoke?.promptPipelineActive).toBe(false)
    expect(smoke?.runtimeEffect.processed_spectrum_pipeline).toBe("unchanged")
    expect(smoke?.manualPromotionGate?.ciArtifact).toBe("raw-fid-prompt-manual-promotion-gate")
    expect(smoke?.manualPromotionGate?.runtimeActivationAllowed).toBe(false)
    expect(smoke?.manualPromotionDesign?.docPath).toBe("docs/raw_fid_prompt_manual_promotion_design.md")
    expect(smoke?.manualPromotionDesign?.runtimeActivationAllowed).toBe(false)
    expect(smoke?.manualPromotionDesign?.requiredGuardrailCommand).toBe("./scripts/run_prompt_sidecar_guardrails.sh")
    expect(smoke?.manualPromotionDesign?.rollbackMode).toBe("MOLTRACE_RAW_FID_PIPELINE=legacy")
    expect(smoke?.manualPromotionDesign?.requiredGates).toContain("no_runtime_activation")
    expect(smoke?.manualPromotionDesign?.promotionStages).toContain("stage_0_metadata_only_current_state")
    expect(smoke?.provenanceChecksumArtifact?.ciArtifact).toBe("raw-fid-prompt-provenance-checksums")
    expect(smoke?.provenanceChecksumArtifact?.files).toEqual([
      "raw_fid_prompt_sidecar_fixture_report.json",
      "raw_fid_prompt_sidecar_fixture_report.csv",
      "raw_fid_prompt_sidecar_provenance_checksums.json",
      "raw_fid_prompt_sidecar_provenance_checksums.csv",
    ])
    expect(smoke?.shadowComparisonArtifact?.ciArtifact).toBe("raw-fid-prompt-shadow-comparison")
    expect(smoke?.shadowComparisonArtifact?.runtimeActivationAllowed).toBe(false)
    expect(smoke?.shadowComparisonArtifact?.files).toEqual([
      "raw_fid_prompt_shadow_comparison_summary.json",
      "raw_fid_prompt_shadow_comparison_summary.csv",
    ])
    expect(smoke?.releaseReadinessArtifact?.ciArtifact).toBe("raw-fid-prompt-release-readiness")
    expect(smoke?.releaseReadinessArtifact?.runtimeActivationAllowed).toBe(false)
    expect(smoke?.releaseReadinessArtifact?.files).toEqual(["raw_fid_prompt_release_readiness.md"])
  })

  it("returns a null sidecar for missing or malformed release-health payloads", () => {
    expect(parseReleaseHealthDiagnostics(null).rawFidPromptSidecarSmoke).toBeNull()
    expect(parseReleaseHealthDiagnostics({}).rawFidPromptSidecarSmoke).toBeNull()
    expect(parseReleaseHealthDiagnostics({ raw_fid_prompt_sidecar_smoke: [] }).rawFidPromptSidecarSmoke).toBeNull()
  })

  it("filters unknown runtime-effect and artifact-file shapes without throwing", () => {
    const diagnostics = parseReleaseHealthDiagnostics({
      raw_fid_prompt_sidecar_smoke: {
        status: "passed",
        prompt_pipeline_active: "false",
        runtime_effect: {
          processed_spectrum_pipeline: "unchanged",
          nested: { ignored: true },
          files: ["ignored"],
        },
        provenance_checksum_artifact: {
          files: ["a.json", "", 7, "b.csv"],
        },
        shadow_comparison_artifact: {
          files: ["shadow.json", 4, "shadow.csv"],
        },
        release_readiness_artifact: {
          files: ["readiness.md", "", 7],
        },
      },
    })

    expect(diagnostics.rawFidPromptSidecarSmoke?.promptPipelineActive).toBe(false)
    expect(diagnostics.rawFidPromptSidecarSmoke?.runtimeEffect).toEqual({
      processed_spectrum_pipeline: "unchanged",
    })
    expect(diagnostics.rawFidPromptSidecarSmoke?.provenanceChecksumArtifact?.files).toEqual(["a.json", "b.csv"])
    expect(diagnostics.rawFidPromptSidecarSmoke?.shadowComparisonArtifact?.files).toEqual(["shadow.json", "shadow.csv"])
    expect(diagnostics.rawFidPromptSidecarSmoke?.releaseReadinessArtifact?.files).toEqual(["readiness.md"])
  })
})
