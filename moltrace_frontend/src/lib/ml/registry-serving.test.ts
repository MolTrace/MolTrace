import { describe, expect, it } from "vitest"
import {
  nucleusScopeLabel,
  readServingState,
  SERVING_REGISTRY_STATUS,
} from "@/src/lib/ml/registry-serving"

describe("registry serving state", () => {
  it("treats an approved artifact with no registry entry as not serving", () => {
    // The case the listing used to render as deployed.
    const state = readServingState({ id: 7, status: "approved", registry_model_id: null })
    expect(state.serving).toBe(false)
    expect(state.contradictsApproval).toBe(true)
    expect(state.label).toBe("Not serving")
    expect(state.detail).toContain("Not in the model registry")
  })

  it("serves only on production", () => {
    expect(SERVING_REGISTRY_STATUS).toBe("production")
    const serving = readServingState({
      status: "approved",
      registry_model_id: "m-1",
      registry_status: "production",
      registry_role: "nmrnet_checkpoint",
      registry_nucleus: "13C",
    })
    expect(serving.serving).toBe(true)
    expect(serving.contradictsApproval).toBe(false)
    expect(serving.label).toBe("Serving")
    // The nucleus keeps its own casing — "13c" would name a different thing.
    expect(serving.detail).toBe("Predictions resolve to this artifact for nmrnet_checkpoint · 13C.")
  })

  it("names the all-nuclei scope inline when the entry has no nucleus", () => {
    const state = readServingState({
      registry_model_id: "m-5",
      registry_status: "production",
      registry_role: "hose_kb",
      registry_nucleus: null,
    })
    expect(state.detail).toBe("Predictions resolve to this artifact for hose_kb · all nuclei.")
  })

  it.each([
    ["shadow", "Shadow only"],
    ["candidate", "Registered, not serving"],
    ["retired", "Retired"],
  ] as const)("does not treat %s as serving", (registryStatus, label) => {
    const state = readServingState({
      status: "approved",
      registry_model_id: "m-2",
      registry_status: registryStatus,
    })
    expect(state.serving).toBe(false)
    expect(state.label).toBe(label)
    // Approved but not answering is exactly the disagreement the reviewer must see.
    expect(state.contradictsApproval).toBe(true)
  })

  it("requires both the entry id and the production status", () => {
    // A half-populated row must not read as live in either direction.
    expect(readServingState({ registry_status: "production" }).serving).toBe(false)
    expect(readServingState({ registry_model_id: "m-3" }).serving).toBe(false)
  })

  it("ignores a registry status outside the known vocabulary", () => {
    const state = readServingState({ registry_model_id: "m-4", registry_status: "live" })
    expect(state.registryStatus).toBeNull()
    expect(state.serving).toBe(false)
  })

  it("reads a row that predates the registry fields without inventing a state", () => {
    const state = readServingState({ id: 3, status: "trained" })
    expect(state.registryModelId).toBeNull()
    expect(state.registryStatus).toBeNull()
    expect(state.serving).toBe(false)
    // Not approved, so there is no contradiction to flag — just not serving.
    expect(state.contradictsApproval).toBe(false)
  })

  it("survives a non-record row", () => {
    expect(readServingState(null).serving).toBe(false)
    expect(readServingState("nope").serving).toBe(false)
  })

  it("states the all-nuclei scope rather than leaving it blank", () => {
    expect(nucleusScopeLabel(null)).toBe("All nuclei")
    expect(nucleusScopeLabel("1H")).toBe("1H")
  })
})
