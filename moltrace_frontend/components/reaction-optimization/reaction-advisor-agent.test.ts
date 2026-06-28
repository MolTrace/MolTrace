import { describe, expect, it, vi } from "vitest"

// The R8 reader lives in the heavy reaction-project-detail module; mock its
// runtime/browser deps so importing the pure helper doesn't boot the page.
vi.mock("next/navigation", () => ({
  usePathname: () => "/reactions",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ reactionId: "10" }),
}))
vi.mock("framer-motion", () => ({
  motion: new Proxy({}, { get: () => (p: { children?: unknown }) => p.children }),
  AnimatePresence: (p: { children?: unknown }) => p.children,
}))

import { advisorAgentFromRun } from "@/components/reaction-optimization/reaction-project-detail"

const fullAgentRun = {
  advisor_mode: "llm_guided_placeholder",
  metadata_json: {
    agent: {
      engine: "reaction_agent.v1",
      mode: "claude_tool_agent",
      llm_used: true,
      model_version: "claude-opus-4-8",
      narrative: "We should prioritise the higher-temperature corner…",
      plan: ["Assess safety", "Recommend next batch", "Summarise"],
      tool_calls: [
        {
          name: "assess_safety",
          arguments: {},
          output: { status: "clear", blocking_screening_ids: [] },
          tool_use_id: "toolu_a",
          is_error: false,
          source: "tool",
        },
        {
          name: "recommend_next_batch",
          arguments: { batch_size: 5 },
          output: { candidates: [{ rank: 1, predicted_score: 0.91 }], count: 5 },
          is_error: false,
        },
        "not-a-record", // must be filtered out
      ],
      safety_precheck: { status: "clear", summary: "No blocking screenings.", blocking_screening_ids: [] },
      execution_blocked: false,
      warnings: ["low data regime"],
      stop_reason: "end_turn",
      disclaimer: "Reaction agent output is explanatory decision support …",
      human_review_required: true,
    },
  },
}

describe("R8 advisorAgentFromRun reader", () => {
  it("returns null when there is no agent block (default path / unchanged behaviour)", () => {
    expect(advisorAgentFromRun(null)).toBeNull()
    expect(advisorAgentFromRun(undefined)).toBeNull()
    expect(advisorAgentFromRun({})).toBeNull()
    expect(advisorAgentFromRun({ metadata_json: {} })).toBeNull()
    expect(advisorAgentFromRun({ metadata_json: { agent: "nope" } })).toBeNull()
  })

  it("parses the math-frozen claude_tool_agent shape and filters non-record tool calls", () => {
    const a = advisorAgentFromRun(fullAgentRun)
    expect(a).not.toBeNull()
    expect(a?.engine).toBe("reaction_agent.v1")
    expect(a?.mode).toBe("claude_tool_agent")
    expect(a?.llmUsed).toBe(true)
    expect(a?.modelVersion).toBe("claude-opus-4-8")
    expect(a?.narrative).toContain("higher-temperature")
    expect(a?.plan).toEqual(["Assess safety", "Recommend next batch", "Summarise"])
    // the string tool_call entry is dropped — only records survive
    expect(a?.toolCalls).toHaveLength(2)
    expect(a?.toolCalls[1].name).toBe("recommend_next_batch")
    expect(a?.safetyStatus).toBe("clear")
    expect(a?.executionBlocked).toBe(false)
    expect(a?.warnings).toEqual(["low data regime"])
    expect(a?.stopReason).toBe("end_turn")
    expect(a?.disclaimer).toContain("decision support")
    expect(a?.humanReviewRequired).toBe(true)
    expect(a?.isFallback).toBe(false)
  })

  it("flags the rule_based_fallback (no-LLM) path as degraded", () => {
    const a = advisorAgentFromRun({
      metadata_json: {
        agent: {
          engine: "reaction_agent.v1",
          mode: "rule_based_fallback",
          llm_used: false,
          model_version: null,
          narrative: "Deterministic baseline plan.",
          tool_calls: [{ name: "assess_safety", output: { status: "clear" } }],
          safety_precheck: { status: "clear" },
        },
      },
    })
    expect(a?.isFallback).toBe(true)
    expect(a?.llmUsed).toBe(false)
    expect(a?.modelVersion).toBeNull()
    // always-review defaults true even when the field is absent (agent schedules nothing)
    expect(a?.humanReviewRequired).toBe(true)
  })

  it("treats a null model_version as degraded even if mode looks LLM-ish, and surfaces execution_blocked", () => {
    const a = advisorAgentFromRun({
      metadata_json: {
        agent: {
          mode: "claude_tool_agent",
          model_version: null, // no version → degraded label so reviewers aren't misled
          execution_blocked: true,
          safety_precheck: { status: "blocked", summary: "Energetic hazard match." },
          human_review_required: false, // explicit false is the ONLY way it reads false
        },
      },
    })
    expect(a?.isFallback).toBe(true)
    expect(a?.executionBlocked).toBe(true)
    expect(a?.safetyStatus).toBe("blocked")
    expect(a?.humanReviewRequired).toBe(false)
  })
})
