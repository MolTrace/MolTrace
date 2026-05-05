/**
 * Guards privacy-safe closed-loop reaction analytics — not E2E; complement with visual/E2E if adopted.
 */
import { afterEach, describe, expect, it, vi } from "vitest"

const apiFetchMock = vi.fn()

vi.mock("@/lib/api/client", () => ({
  apiFetch: (...args: unknown[]) => apiFetchMock(...args),
}))

import {
  CLOSED_LOOP_OUTCOME_SCALAR_KEYS,
  countClosedLoopOutcomeFieldKeys,
  trackAliquotCreated,
  trackBatchCreated,
  trackCompoundCreated,
  trackCompoundGraphViewed,
  trackCompoundLinkedToReaction,
  trackReactionAnalyticalResultLinked,
  trackReactionCycleDecisionSaved,
  trackReactionExecutionBatchCreated,
  trackReactionExecutionItemCompleted,
  trackReactionExecutionItemFailed,
  trackReactionExecutionItemStarted,
  trackReactionOptimizationCycleCreated,
  trackReactionOutcomeConfirmed,
  trackReactionOutcomeExtractionRun,
  trackReactionRecommendationConvertedToExperiment,
  trackRegulatoryChangeDetectedViewed,
  trackRegulatoryDossierCreated,
  trackRegulatoryImpactAssessmentRun,
  trackRegulatoryNotificationResolved,
  trackRegulatoryQueryAnswered,
  trackRegulatoryReadinessReportGenerated,
  trackRegulatoryRequirementAdded,
  trackRegulatoryReviewCompleted,
  trackRegulatoryRuleUpdateProposalApproved,
  trackRegulatoryRuleUpdateProposalCreated,
  trackRegulatoryRuleUpdateProposalRejected,
  trackRegulatorySurveillanceRunStarted,
  trackRegulatoryWatcherCreated,
  trackUsageEvent,
} from "@/src/lib/analytics/analytics-client"

const ALLOWED_METADATA_KEY_SET = new Set([
  "batch_id",
  "cycle_number",
  "has_artifact_id",
  "has_spectracheck_link",
  "item_id",
  "outcome_fields_count",
  "reaction_project_id",
  "result_type",
  "status",
])

const REGULATORY_METADATA_KEY_SET = new Set([
  "dossier_id",
  "jurisdiction_id",
  "status",
  "requirement_count",
  "evidence_link_count",
  "risk_level",
  "review_status",
])

const REGULATORY_SURVEILLANCE_METADATA_KEY_SET = new Set([
  "watcher_id",
  "source_type",
  "jurisdiction_id",
  "change_type",
  "severity",
  "affected_dossier_count",
  "affected_rule_count",
  "proposal_type",
  "status",
])

const COMPOUND_REGISTRY_METADATA_KEY_SET = new Set([
  "compound_id",
  "batch_id",
  "compound_type",
  "source_type",
  "has_structure",
  "has_batch",
  "linked_resource_type",
  "status",
])

function lastAnalyticsPayload(): { event_source?: string; event_type?: string; metadata?: Record<string, unknown> } {
  expect(apiFetchMock).toHaveBeenCalled()
  const call = apiFetchMock.mock.calls[apiFetchMock.mock.calls.length - 1] as [string, RequestInit]
  const raw = call[1]?.body
  /** Mock replaces `apiFetch` before stringify — body is usually the POST object envelope. */
  if (typeof raw === "string") {
    return JSON.parse(raw) as { event_source?: string; event_type?: string; metadata?: Record<string, unknown> }
  }
  if (raw != null && typeof raw === "object" && !Array.isArray(raw)) {
    return raw as { event_source?: string; event_type?: string; metadata?: Record<string, unknown> }
  }
  throw new Error("unexpected analytics request body shape")
}

afterEach(() => {
  vi.clearAllMocks()
})

describe("countClosedLoopOutcomeFieldKeys", () => {
  it("counts scalar outcome keys without embedding values in metadata usage sites", () => {
    expect(countClosedLoopOutcomeFieldKeys({})).toBe(0)
    expect(countClosedLoopOutcomeFieldKeys({ yield_percent: 12.5, conversion_percent: NaN })).toBe(1)
    expect(
      countClosedLoopOutcomeFieldKeys({
        yield_percent: 1,
        conversion_percent: 2,
        notes: "  secret workflow  ",
      }),
    ).toBe(3)
    const full: Record<string, unknown> = {}
    for (const k of CLOSED_LOOP_OUTCOME_SCALAR_KEYS) full[k] = 1
    full.notes = "n"
    expect(countClosedLoopOutcomeFieldKeys(full)).toBeLessThanOrEqual(32)
  })

  it("does not treat arbitrary keys as outcomes", () => {
    expect(
      countClosedLoopOutcomeFieldKeys({
        conditions_json: { a: 1 },
        smiles: "CCO",
        summary_text: "huge blob",
      }),
    ).toBe(0)
  })
})

describe("closed-loop track* helpers", () => {
  it("each sends the expected event_type", () => {
    apiFetchMock.mockResolvedValue(undefined)
    trackReactionRecommendationConvertedToExperiment({ reaction_project_id: 1, status: "planned" })
    expect(lastAnalyticsPayload().event_type).toBe("reaction_recommendation_converted_to_experiment")
    apiFetchMock.mockResolvedValue(undefined)
    trackReactionExecutionBatchCreated({ reaction_project_id: 1, batch_id: 10, status: "draft" })
    expect(lastAnalyticsPayload().event_type).toBe("reaction_execution_batch_created")
    apiFetchMock.mockResolvedValue(undefined)
    trackReactionExecutionItemStarted({ reaction_project_id: 1, item_id: 3, batch_id: 10, status: "running" })
    expect(lastAnalyticsPayload().event_type).toBe("reaction_execution_item_started")
    apiFetchMock.mockResolvedValue(undefined)
    trackReactionExecutionItemCompleted({ reaction_project_id: 1, item_id: 3, status: "completed" })
    expect(lastAnalyticsPayload().event_type).toBe("reaction_execution_item_completed")
    apiFetchMock.mockResolvedValue(undefined)
    trackReactionExecutionItemFailed({ reaction_project_id: 1, item_id: 3, status: "failed" })
    expect(lastAnalyticsPayload().event_type).toBe("reaction_execution_item_failed")
    apiFetchMock.mockResolvedValue(undefined)
    trackReactionAnalyticalResultLinked({
      reaction_project_id: 1,
      item_id: 3,
      result_type: "lcms",
      has_spectracheck_link: false,
      has_artifact_id: true,
    })
    expect(lastAnalyticsPayload().event_type).toBe("reaction_analytical_result_linked")
    apiFetchMock.mockResolvedValue(undefined)
    trackReactionOutcomeExtractionRun({ reaction_project_id: 1, item_id: 3, outcome_fields_count: 2, status: "requires_review" })
    expect(lastAnalyticsPayload().event_type).toBe("reaction_outcome_extraction_run")
    apiFetchMock.mockResolvedValue(undefined)
    trackReactionOutcomeConfirmed({ reaction_project_id: 1, item_id: 3, outcome_fields_count: 2 })
    expect(lastAnalyticsPayload().event_type).toBe("reaction_outcome_confirmed")
    apiFetchMock.mockResolvedValue(undefined)
    trackReactionOptimizationCycleCreated({ reaction_project_id: 1, cycle_number: 1, batch_id: 9, status: "draft" })
    expect(lastAnalyticsPayload().event_type).toBe("reaction_optimization_cycle_created")
    apiFetchMock.mockResolvedValue(undefined)
    trackReactionCycleDecisionSaved({
      reaction_project_id: 1,
      cycle_number: 2,
      batch_id: 9,
      status: "pause",
    })
    expect(lastAnalyticsPayload().event_type).toBe("reaction_cycle_decision_saved")
  })

  it("metadata contains only privacy-safe whitelist keys + numeric/string hygiene", () => {
    apiFetchMock.mockResolvedValue(undefined)
    trackReactionOutcomeConfirmed({
      reaction_project_id: 42,
      batch_id: 7,
      item_id: 99,
      status: "without_extraction_run",
      outcome_fields_count: 3,
      has_spectracheck_link: true,
      has_artifact_id: false,
      result_type: "nmr",
    })
    const { metadata, event_source } = lastAnalyticsPayload()
    expect(event_source).toBe("frontend")
    expect(metadata).toBeDefined()
    const keys = Object.keys(metadata as object)
    for (const k of keys) {
      expect(ALLOWED_METADATA_KEY_SET.has(k)).toBe(true)
    }
    expect(keys.length).toBeGreaterThan(0)
    expect((metadata as { outcome_fields_count: number }).outcome_fields_count).toBe(3)
    expect((metadata as { reaction_project_id: number }).reaction_project_id).toBe(42)
  })

  it("does not throw when apiFetch fails (non-blocking analytics)", async () => {
    apiFetchMock.mockRejectedValueOnce(new Error("network unavailable"))
    expect(() =>
      trackReactionOutcomeConfirmed({
        reaction_project_id: 1,
        item_id: 2,
      }),
    ).not.toThrow()
    await new Promise((r) => setTimeout(r, 0))
  })
})

describe("regulatory track* helpers", () => {
  it("each sends the expected event_type", () => {
    apiFetchMock.mockResolvedValue(undefined)
    trackRegulatoryDossierCreated({ dossier_id: 1, status: "draft" })
    expect(lastAnalyticsPayload().event_type).toBe("regulatory_dossier_created")
    apiFetchMock.mockResolvedValue(undefined)
    trackRegulatoryRequirementAdded({ dossier_id: 1, requirement_count: 2 })
    expect(lastAnalyticsPayload().event_type).toBe("regulatory_requirement_added")
    apiFetchMock.mockResolvedValue(undefined)
    trackRegulatoryQueryAnswered({ dossier_id: 1, review_status: "answered" })
    expect(lastAnalyticsPayload().event_type).toBe("regulatory_query_answered")
    apiFetchMock.mockResolvedValue(undefined)
    trackRegulatoryReadinessReportGenerated({ dossier_id: 1, status: "draft" })
    expect(lastAnalyticsPayload().event_type).toBe("regulatory_readiness_report_generated")
    apiFetchMock.mockResolvedValue(undefined)
    trackRegulatoryReviewCompleted({ dossier_id: 1, review_status: "approve" })
    expect(lastAnalyticsPayload().event_type).toBe("regulatory_review_completed")
  })

  it("regulatory metadata keys stay on the privacy-safe allowlist", () => {
    apiFetchMock.mockResolvedValue(undefined)
    trackRegulatoryReadinessReportGenerated({
      dossier_id: 9,
      jurisdiction_id: 3,
      status: "requires_review",
      requirement_count: 2,
      evidence_link_count: 1,
      risk_level: "high",
      review_status: "ready_for_review",
    })
    const { metadata, event_source } = lastAnalyticsPayload()
    expect(event_source).toBe("frontend")
    expect(metadata).toBeDefined()
    for (const k of Object.keys(metadata as object)) {
      expect(REGULATORY_METADATA_KEY_SET.has(k)).toBe(true)
    }
  })

  it("regulatory surveillance helpers emit expected event_type values", () => {
    apiFetchMock.mockResolvedValue(undefined)
    trackRegulatoryWatcherCreated({ watcher_id: 3, source_type: "fda_guidance", jurisdiction_id: 2 })
    expect(lastAnalyticsPayload().event_type).toBe("regulatory_watcher_created")
    apiFetchMock.mockResolvedValue(undefined)
    trackRegulatorySurveillanceRunStarted({ watcher_id: 3, source_type: "custom_url" })
    expect(lastAnalyticsPayload().event_type).toBe("regulatory_surveillance_run_started")
    apiFetchMock.mockResolvedValue(undefined)
    trackRegulatoryChangeDetectedViewed({ change_type: "substantive_update", severity: "warning", affected_dossier_count: 2 })
    expect(lastAnalyticsPayload().event_type).toBe("regulatory_change_detected_viewed")
    apiFetchMock.mockResolvedValue(undefined)
    trackRegulatoryImpactAssessmentRun({ affected_rule_count: 4, severity: "high" })
    expect(lastAnalyticsPayload().event_type).toBe("regulatory_impact_assessment_run")
    apiFetchMock.mockResolvedValue(undefined)
    trackRegulatoryRuleUpdateProposalCreated({ proposal_type: "update_threshold", status: "proposed" })
    expect(lastAnalyticsPayload().event_type).toBe("regulatory_rule_update_proposal_created")
    apiFetchMock.mockResolvedValue(undefined)
    trackRegulatoryRuleUpdateProposalApproved({ proposal_type: "deprecate_rule", status: "approved" })
    expect(lastAnalyticsPayload().event_type).toBe("regulatory_rule_update_proposal_approved")
    apiFetchMock.mockResolvedValue(undefined)
    trackRegulatoryRuleUpdateProposalRejected({ proposal_type: "create_rule", status: "rejected" })
    expect(lastAnalyticsPayload().event_type).toBe("regulatory_rule_update_proposal_rejected")
    apiFetchMock.mockResolvedValue(undefined)
    trackRegulatoryNotificationResolved({ severity: "warning", status: "resolved" })
    expect(lastAnalyticsPayload().event_type).toBe("regulatory_notification_resolved")
  })

  it("regulatory surveillance metadata keys stay on the privacy-safe allowlist", () => {
    apiFetchMock.mockResolvedValue(undefined)
    trackRegulatoryWatcherCreated({
      watcher_id: 5,
      source_type: "ich_guideline",
      jurisdiction_id: 1,
      change_type: "substantive_update",
      severity: "critical",
      affected_dossier_count: 2,
      affected_rule_count: 1,
      proposal_type: "other",
      status: "active",
    })
    const { metadata, event_source } = lastAnalyticsPayload()
    expect(event_source).toBe("frontend")
    for (const k of Object.keys(metadata as object)) {
      expect(REGULATORY_SURVEILLANCE_METADATA_KEY_SET.has(k)).toBe(true)
    }
  })

  it("strips sensitive keys from arbitrary metadata payloads", () => {
    apiFetchMock.mockResolvedValue(undefined)
    trackUsageEvent({
      event_type: "regulatory_query_answered",
      metadata: {
        dossier_id: 1,
        question: "structure of compound X",
        answer_text: "classified",
      } as Record<string, unknown>,
    })
    const { metadata } = lastAnalyticsPayload()
    expect(metadata?.question).toBeUndefined()
    expect(metadata?.answer_text).toBeUndefined()
    expect((metadata as { dossier_id: number }).dossier_id).toBe(1)
  })
})

describe("compound registry analytics metadata", () => {
  it("compound_created uses allowlisted keys only", () => {
    apiFetchMock.mockResolvedValue(undefined)
    trackCompoundCreated({
      compound_id: 12,
      compound_type: "target",
      has_structure: true,
      status: "draft",
    })
    const { metadata, event_type } = lastAnalyticsPayload()
    expect(event_type).toBe("compound_created")
    for (const k of Object.keys(metadata ?? {})) {
      expect(COMPOUND_REGISTRY_METADATA_KEY_SET.has(k)).toBe(true)
    }
  })

  it("compound_linked_to_reaction uses allowlisted keys only", () => {
    apiFetchMock.mockResolvedValue(undefined)
    trackCompoundLinkedToReaction({
      compound_id: 3,
      batch_id: 9,
      has_batch: true,
      linked_resource_type: "reaction_experiment",
      status: "linked",
    })
    const { metadata, event_type } = lastAnalyticsPayload()
    expect(event_type).toBe("compound_linked_to_reaction")
    for (const k of Object.keys(metadata ?? {})) {
      expect(COMPOUND_REGISTRY_METADATA_KEY_SET.has(k)).toBe(true)
    }
  })

  it("batch_created and aliquot_created use allowlisted keys only", () => {
    apiFetchMock.mockResolvedValue(undefined)
    trackBatchCreated({ compound_id: 2, batch_id: 40, source_type: "synthesized", status: "active", has_batch: true })
    expect(lastAnalyticsPayload().event_type).toBe("batch_created")
    trackAliquotCreated({ batch_id: 40, compound_id: 2, status: "available" })
    const { metadata, event_type } = lastAnalyticsPayload()
    expect(event_type).toBe("aliquot_created")
    for (const k of Object.keys(metadata ?? {})) {
      expect(COMPOUND_REGISTRY_METADATA_KEY_SET.has(k)).toBe(true)
    }
  })

  it("compound_graph_viewed uses allowlisted keys only", () => {
    apiFetchMock.mockResolvedValue(undefined)
    trackCompoundGraphViewed({ compound_id: 7, status: "loaded" })
    const { metadata, event_type } = lastAnalyticsPayload()
    expect(event_type).toBe("compound_graph_viewed")
    for (const k of Object.keys(metadata ?? {})) {
      expect(COMPOUND_REGISTRY_METADATA_KEY_SET.has(k)).toBe(true)
    }
  })
})
