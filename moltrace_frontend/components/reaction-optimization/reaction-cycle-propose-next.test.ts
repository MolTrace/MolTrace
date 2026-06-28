import { describe, expect, it, vi } from "vitest"

// The R5 helpers live in the heavy reaction-project-detail module; mock its
// runtime/browser deps so importing the pure helpers doesn't boot the page.
vi.mock("next/navigation", () => ({
  usePathname: () => "/reactions",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ reactionId: "10" }),
}))
// Use the REAL @/lib/api/client — the test makes no network calls, and the error
// helper relies on the real ApiError + sanitizePublicApiErrorMessage.
vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (p: { children?: unknown }) => p.children }),
  AnimatePresence: (p: { children?: unknown }) => p.children,
}))

import { ApiError } from "@/lib/api/client"
import {
  cycleCanProposeNext,
  cycleDmtaInfoFromCycle,
  cycleLoopMetricsFromCycle,
  cycleProposeNextInfoFromCycle,
  proposeNextErrorMessage,
  proposeNextRequestBody,
} from "@/components/reaction-optimization/reaction-project-detail"

const cycleWithDecision = (decision: string) => ({
  metadata_json: { latest_decision: { decision } },
})

describe("R5 propose-next cycle helpers", () => {
  it("unlocks propose-next ONLY on a continue_optimization decision (the disabled-button gate)", () => {
    expect(cycleCanProposeNext(cycleWithDecision("continue_optimization"))).toBe(true)
    // every other decision keeps the action locked
    for (const d of [
      "pause",
      "stop_success",
      "stop_insufficient_progress",
      "revise_design_space",
      "revise_objective",
      "requires_review",
    ]) {
      expect(cycleCanProposeNext(cycleWithDecision(d))).toBe(false)
    }
    // and a cycle with no recorded decision stays locked
    expect(cycleCanProposeNext({ metadata_json: {} })).toBe(false)
    expect(cycleCanProposeNext({})).toBe(false)
  })

  it("reads loop metrics from metadata_json.cycle_metrics.metrics", () => {
    const cycle = {
      metadata_json: {
        cycle_metrics: { metrics: { total_experiments: 5, new_experiments: 5, target_met: false } },
      },
    }
    expect(cycleLoopMetricsFromCycle(cycle)).toEqual({
      total_experiments: 5,
      new_experiments: 5,
      target_met: false,
    })
    expect(cycleLoopMetricsFromCycle({ metadata_json: { cycle_metrics: {} } })).toBeNull()
    expect(cycleLoopMetricsFromCycle({ metadata_json: {} })).toBeNull()
    expect(cycleLoopMetricsFromCycle({})).toBeNull()
  })

  it("reads the half-closed-loop banner info (flags + note + proposed_from) on a proposed draft", () => {
    const info = cycleProposeNextInfoFromCycle({
      metadata_json: {
        propose_next: {
          requires_human_signoff_before_execution: true,
          execution_blocked_by_safety: true,
          safety_gate_status: "blocked",
        },
        note: "Proposed next batch (decision-support).",
        proposed_from_cycle_id: 41,
      },
    })
    expect(info?.flags.requires_human_signoff_before_execution).toBe(true)
    expect(info?.flags.execution_blocked_by_safety).toBe(true)
    expect(info?.flags.safety_gate_status).toBe("blocked")
    expect(info?.note).toContain("decision-support")
    expect(info?.proposedFrom).toBe(41)
    // a normal (non-proposed) cycle has no banner
    expect(cycleProposeNextInfoFromCycle({ metadata_json: {} })).toBeNull()
    expect(cycleProposeNextInfoFromCycle({})).toBeNull()
  })

  it("reads the DMTA sequence + per-phase latencies + provenance for the stepper", () => {
    const info = cycleDmtaInfoFromCycle({
      metadata_json: {
        cycle_metrics: {
          dmta_sequence: ["propose", "safety_gate", "make", "test", "learn", "decision"],
          engine: "reaction_loop.v1",
          metrics: { phase_latencies_seconds: { propose: 1.2, safety_gate: 0.3 } },
          provenance: { surrogate_model_version: "gp-1", spectracheck_session_ids: [7, 9] },
        },
      },
    })
    expect(info?.sequence).toEqual(["propose", "safety_gate", "make", "test", "learn", "decision"])
    expect(info?.engine).toBe("reaction_loop.v1")
    expect(info?.phaseLatencies).toEqual({ propose: 1.2, safety_gate: 0.3 })
    expect(info?.provenance?.surrogate_model_version).toBe("gp-1")
    // missing cycle_metrics → null; missing dmta_sequence → empty sequence (stepper hides)
    expect(cycleDmtaInfoFromCycle({ metadata_json: {} })).toBeNull()
    expect(cycleDmtaInfoFromCycle({ metadata_json: { cycle_metrics: {} } })?.sequence).toEqual([])
  })
})

const FALLBACK = "POST …/propose-next failed."

describe("R5 propose-next error message", () => {
  it("surfaces the 409 'why you can't propose' reason directly from detail", () => {
    const reason = "Latest decision is 'pause'; record a 'continue_optimization' decision first."
    expect(proposeNextErrorMessage(new ApiError(409, { detail: reason }), FALLBACK)).toBe(reason)
  })

  it("a 409 with no string detail is NOT surfaced raw — it falls through", () => {
    const out = proposeNextErrorMessage(new ApiError(409, {}), FALLBACK)
    expect(typeof out).toBe("string")
    expect(out).not.toBe("")
  })

  it("routes the non-owner / generic 404 through formatApiError (non-leaking), not the 409 path", () => {
    // a non-leaking 404 ("Not Found") becomes the generic endpoint message, never the raw detail
    expect(proposeNextErrorMessage(new ApiError(404, { detail: "Not Found" }), FALLBACK)).toContain(
      "not available",
    )
    // a 404 carrying a real resource detail surfaces that detail
    expect(
      proposeNextErrorMessage(new ApiError(404, { detail: "Reaction project not found." }), FALLBACK),
    ).toContain("project not found")
  })
})

describe("R5 propose-next request body (optional BO params)", () => {
  it("stays {}-valid when nothing usable is supplied (server defaults all fields)", () => {
    expect(proposeNextRequestBody({})).toEqual({})
    expect(proposeNextRequestBody({ algorithm: "", batchSize: "", safetyAware: null })).toEqual({})
    // a blank/zero/negative/non-numeric batch is omitted, not sent as 0/NaN
    expect(proposeNextRequestBody({ batchSize: "0" })).toEqual({})
    expect(proposeNextRequestBody({ batchSize: "-3" })).toEqual({})
    expect(proposeNextRequestBody({ batchSize: "abc" })).toEqual({})
  })

  it("carries the configured algorithm / batch_size / safety_aware when set", () => {
    expect(
      proposeNextRequestBody({ algorithm: "gaussian_process_ucb", batchSize: "8", safetyAware: true }),
    ).toEqual({ algorithm: "gaussian_process_ucb", batch_size: 8, safety_aware: true })
    // safety_aware:false is a real value (not omitted); numeric batch passes through
    expect(proposeNextRequestBody({ batchSize: 3, safetyAware: false })).toEqual({
      batch_size: 3,
      safety_aware: false,
    })
  })

  it("floors a fractional batch_size on BOTH the numeric and string paths (server wants an int)", () => {
    expect(proposeNextRequestBody({ batchSize: 2.9 })).toEqual({ batch_size: 2 })
    expect(proposeNextRequestBody({ batchSize: "4.7" })).toEqual({ batch_size: 4 })
    // floors to 0 → below the >= 1 floor → omitted
    expect(proposeNextRequestBody({ batchSize: 0.6 })).toEqual({})
  })
})
