import { describe, expect, it, vi } from "vitest"

// The R5 helpers live in the heavy reaction-project-detail module; mock its
// runtime/browser deps so importing the pure helpers doesn't boot the page.
vi.mock("next/navigation", () => ({
  usePathname: () => "/reactions",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ reactionId: "10" }),
}))
vi.mock("@/lib/api/client", () => ({
  apiFetch: vi.fn(async () => []),
  ApiError: class ApiError extends Error {},
}))
vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (p: { children?: unknown }) => p.children }),
  AnimatePresence: (p: { children?: unknown }) => p.children,
}))

import {
  cycleCanProposeNext,
  cycleLoopMetricsFromCycle,
  cycleProposeNextInfoFromCycle,
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
})
