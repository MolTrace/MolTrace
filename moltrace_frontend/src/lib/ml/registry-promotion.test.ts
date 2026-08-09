import { describe, expect, it } from "vitest"
import {
  buildRegistryPromotionBody,
  EMPTY_PROMOTION_DRAFT,
  isPromotionDraftEmpty,
  promotionRoleLabel,
  readMetricComparison,
  type PromotionDraft,
} from "@/src/lib/ml/registry-promotion"

const COMPLETE: PromotionDraft = {
  ...EMPTY_PROMOTION_DRAFT,
  role: "nmrnet_checkpoint",
  semanticVersion: "2.1.0",
  datasetSnapshotHash: "snap-abc123",
  datasetRowCount: "41822",
}

describe("registry promotion request", () => {
  it("defaults nothing — an empty draft is the approve-without-promoting case", () => {
    expect(isPromotionDraftEmpty(EMPTY_PROMOTION_DRAFT)).toBe(true)
    const built = buildRegistryPromotionBody(EMPTY_PROMOTION_DRAFT)
    expect(built.ok).toBe(false)
    if (built.ok) return
    // Every required field is asked for, none is filled in on the reviewer's behalf.
    expect(Object.keys(built.errors).sort()).toEqual([
      "datasetRowCount",
      "datasetSnapshotHash",
      "role",
      "semanticVersion",
    ])
  })

  it("builds only the four required keys when the optional boxes are blank", () => {
    const built = buildRegistryPromotionBody(COMPLETE)
    expect(built.ok).toBe(true)
    if (!built.ok) return
    // The block rejects keys it does not declare, and "" is not the same as "not supplied".
    expect(built.body).toEqual({
      role: "nmrnet_checkpoint",
      semantic_version: "2.1.0",
      dataset_snapshot_hash: "snap-abc123",
      dataset_row_count: 41822,
    })
  })

  it("sends the optional fields under their wire names when supplied", () => {
    const built = buildRegistryPromotionBody({
      ...COMPLETE,
      role: "lora_adapter",
      nucleus: "13C",
      datasetTag: "nmrexp-2026-07",
      datasetSource: "NMRexp",
      artifactSha256: "a".repeat(64),
      confidenceBandPpm: "2.5",
    })
    expect(built.ok).toBe(true)
    if (!built.ok) return
    expect(built.body.nucleus).toBe("13C")
    expect(built.body.dataset_tag).toBe("nmrexp-2026-07")
    expect(built.body.dataset_source).toBe("NMRexp")
    expect(built.body.artifact_sha256).toBe("a".repeat(64))
    expect(built.body.confidence_band_ppm).toBe(2.5)
  })

  it("accepts a zero row count but rejects a non-integer one", () => {
    expect(buildRegistryPromotionBody({ ...COMPLETE, datasetRowCount: "0" }).ok).toBe(true)
    for (const bad of ["12.5", "-1", "1e4", "many"]) {
      const built = buildRegistryPromotionBody({ ...COMPLETE, datasetRowCount: bad })
      expect(built.ok, bad).toBe(false)
    }
  })

  it("rejects a digest that is not 64 hex characters", () => {
    for (const bad of ["a".repeat(63), "a".repeat(65), `${"a".repeat(63)}z`]) {
      const built = buildRegistryPromotionBody({ ...COMPLETE, artifactSha256: bad })
      expect(built.ok, bad).toBe(false)
      if (built.ok) return
      expect(built.errors.artifactSha256).toContain("64 hexadecimal")
    }
  })

  it("requires a confidence band above zero when one is given", () => {
    for (const bad of ["0", "-2", "nope"]) {
      expect(buildRegistryPromotionBody({ ...COMPLETE, confidenceBandPpm: bad }).ok, bad).toBe(false)
    }
  })

  it("rejects a role outside the served vocabulary", () => {
    const built = buildRegistryPromotionBody({ ...COMPLETE, role: "shift_predictor" })
    expect(built.ok).toBe(false)
    if (built.ok) return
    expect(built.errors.role).toContain("not a role the registry serves")
  })

  it("enforces the field bounds so one box is named rather than the whole form", () => {
    const built = buildRegistryPromotionBody({
      ...COMPLETE,
      semanticVersion: "v".repeat(65),
      datasetSnapshotHash: "h".repeat(201),
      nucleus: "n".repeat(17),
    })
    expect(built.ok).toBe(false)
    if (built.ok) return
    expect(built.errors.semanticVersion).toBeDefined()
    expect(built.errors.datasetSnapshotHash).toBeDefined()
    expect(built.errors.nucleus).toBeDefined()
  })

  it("spells the roles the humanizer would get wrong", () => {
    expect(promotionRoleLabel("hose_kb")).toBe("HOSE knowledge base")
    expect(promotionRoleLabel("lora_adapter")).toBe("LoRA adapter")
    expect(promotionRoleLabel("csi_fingerid")).toBe("CSI:FingerID")
    // An unknown role is shown as-is rather than hidden.
    expect(promotionRoleLabel("future_role")).toBe("future_role")
  })
})

describe("metric comparison note", () => {
  it("separates a comparison that ran from one that stood aside", () => {
    const applied = readMetricComparison([
      "Human review required.",
      "Metric comparison: candidate improves ece from 0.081 to 0.043.",
    ])
    expect(applied).toEqual({
      reason: "candidate improves ece from 0.081 to 0.043",
      applied: true,
    })

    const skipped = readMetricComparison([
      "Metric comparison skipped: no incumbent artifact for this task family.",
    ])
    // A gate with no opinion must never be reported as an endorsement.
    expect(skipped).toEqual({
      reason: "no incumbent artifact for this task family",
      applied: false,
    })
  })

  it("does not mistake the skipped line for an applied one", () => {
    // "Metric comparison skipped:" also starts with "Metric comparison", so order matters.
    const skipped = readMetricComparison(["Metric comparison skipped: nothing to compare."])
    expect(skipped?.applied).toBe(false)
  })

  it("returns null when no comparison line is present", () => {
    expect(readMetricComparison(["Human review required."])).toBeNull()
    expect(readMetricComparison([])).toBeNull()
    expect(readMetricComparison(undefined)).toBeNull()
    expect(readMetricComparison("Metric comparison: not a list.")).toBeNull()
  })
})
