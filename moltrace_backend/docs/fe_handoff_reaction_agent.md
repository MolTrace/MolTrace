# FE Handoff — Repho R8: math-frozen Claude advisor agent

**Backend status:** shipped (engine `3c8e1078`, wiring `ec3539d3`). The agent is **opt-in and
advisory** and rides in the existing advisor-run record — **no schema change, no new endpoint**.
Do this in `moltrace_frontend/`. This is optional FE work (the LLM path is gated); surface it on the
existing advisor workspace per **integrate, don't clutter**.

> What it is: when an operator enables `MOLTRACE_REACTION_AGENT` **and** an Anthropic API key is
> configured, a request to `POST /reaction-projects/{id}/advisor/run` with an LLM `advisor_mode`
> (anything other than `rule_based_mechanistic`) layers a **math-frozen Claude agent** on top of the
> deterministic rule-based critique. The model **plans, narrates, and re-ranks with citations** and
> **never computes a number** — every quantitative value comes from a frozen tool and is recorded as
> provenance. A **fail-closed safety pre-check** gates the action tools. Without a key it degrades to
> the deterministic path. Default off → today's behaviour is unchanged.

## 1. No contract change
The agent output rides in the advisor run's untyped `metadata_json["agent"]`. `ReactionOptimizationAdvisorRun`
is unchanged, so **no `npm run generate:openapi` is required** for this. Read `metadata_json.agent`
defensively (it is absent unless the flag + an LLM mode are in play).

## 2. `metadata_json.agent` shape
```jsonc
{
  "engine": "reaction_agent.v1",
  "mode": "claude_tool_agent",          // or "rule_based_fallback" (no API key)
  "llm_used": true,
  "model_version": "claude-opus-4-8",   // null in fallback
  "narrative": "…model prose plan…",    // PROSE — never the source of numbers
  "plan": ["step 1", "step 2", …],       // model prose, split into steps
  "tool_calls": [                        // the ONLY source of quantitative truth
    { "name": "assess_safety", "arguments": {…}, "output": { "status": "clear", … },
      "tool_use_id": "toolu_…", "is_error": false, "source": "tool" },
    { "name": "recommend_next_batch", "arguments": {"batch_size": 5},
      "output": { "candidates": [{ "rank": 1, "predicted_score": 0.91, … }], "count": 5 }, … }
  ],
  "safety_precheck": { "status": "clear", "summary": "…", "blocking_screening_ids": [] },
  "execution_blocked": false,            // true ⇒ action tools were refused; resolve safety first
  "warnings": ["…"],
  "stop_reason": "end_turn",             // or "api_error" / "refusal" / "fallback"
  "disclaimer": "Reaction agent output is explanatory decision support …",
  "human_review_required": true
}
```
The six tools: `recommend_next_batch`, `assess_safety`, `calculate_green_metrics`,
`retrieve_precedents`, `design_plate`, `summarize_cycle`.

## 3. Math-frozen display rule (important)
**Render every quantitative value from `tool_calls[].output`, never from `narrative`/`plan`.** The
narrative is model prose; treat any number in it as a citation pointer, not a source of truth. Cite
each figure back to its tool call by `name`.

## 4. Suggested UI (on the advisor workspace)
1. **Agent plan panel** — show `narrative` + `plan` as the model's reasoning, with a clear "model
   prose" affordance, and the `disclaimer` verbatim.
2. **Tool-call provenance** — list `tool_calls` (name, arguments, output) as the grounded evidence;
   this is where candidates/scores/green metrics/precedents/plate maps/cycle metrics actually live.
3. **Safety banner** — render `safety_precheck.status` (clear / review_pending / blocked). If
   `execution_blocked` is true, show that the agent refused the action tools and link to the project
   `…/safety-gate` to resolve screenings first.
4. **Degraded badge** — when `mode === "rule_based_fallback"` (or `model_version` is null), label the
   plan as deterministic/no-LLM so reviewers aren't misled.
5. **Always-review** — `human_review_required` is always true; the agent schedules nothing.

## 5. Verify (FE session)
- `npm run test` (vitest/jsdom); mock `apiFetch` to return an advisor run with a `metadata_json.agent`
  block (both `claude_tool_agent` and `rule_based_fallback` shapes).
- Live-curl `:8000` (optional, requires the backend flag): set `MOLTRACE_REACTION_AGENT=1`, sign up →
  project (+ design-space + completed experiments + a BO run) → `POST …/advisor/run` with
  `advisor_mode:"llm_guided_placeholder"` → confirm `metadata_json.agent` is present with a frozen
  `assess_safety` tool call.

## 6. Notes
- The agent is **decision support only** — it re-ranks and explains; the chemist decides. Never
  present its plan as scheduling.
- Quantitative values are frozen-tool outputs; the model never computes them. Keep that distinction
  visible in the UI.
