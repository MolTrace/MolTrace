"""Repho R8 — Claude reaction-planning agent (math frozen, provider-portable).

A Coscientist/ChemCrow-style planner that orchestrates the existing reaction
methods as Anthropic *tool definitions*. The language model **plans, narrates,
and re-ranks with citations**; it **never computes** a quantitative value
(yields, scores, costs, hypervolume, safety verdicts). Every number that reaches
a consumer originates from a frozen deterministic tool whose output is recorded
verbatim in :class:`ReactionAgentToolCall`. This mirrors the Regentry
"narrative, math frozen" pattern.

Design notes
------------
* **Engine-first / collision-safe.** This module is self-contained: it declares
  the tool *schemas* and runs the agentic loop, but the actual frozen engines are
  injected as ``tool_executors`` (name -> callable). The monolith wiring (a
  follow-up) builds those executors from ``reaction_bo`` / ``reaction_safety`` /
  green-metrics / precedent-RAG / plate-design / ``reaction_loop`` and persists
  the transcript + provenance onto the advisor-run / audit record.
* **Works with and without an API key.** When the ``anthropic`` SDK is absent or
  no key is configured, the agent degrades to a deterministic rule-based path
  (``mode="rule_based_fallback"``) that still runs the frozen tools and records
  full provenance — no LLM, no fabricated numbers.
* **Mandatory, fail-closed safety pre-check.** Before the planner runs, an
  ``assess_safety`` executor is invoked. If it is absent or returns ``blocked``,
  ``execution_blocked`` is set and the model is instructed it may not recommend
  any physical experiment. The model cannot route around this.
* **Provider-portable.** Pass ``client`` or ``client_factory`` to target Amazon
  Bedrock / Vertex AI; the default builds a first-party ``anthropic.Anthropic``
  client. Default model is :data:`DEFAULT_MODEL`.

This module intentionally performs no database or network I/O of its own beyond
the injected executors and the (optional) Anthropic client.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# Latest Claude Opus; provider-portable via client/client_factory injection.
DEFAULT_MODEL = "claude-opus-4-8"
_MAX_AGENT_ITERATIONS = 8
_MAX_TOKENS = 4096

AGENT_DISCLAIMER = (
    "Reaction agent output is explanatory decision support produced by a language model that "
    "plans and narrates only. Every quantitative value (yield, score, cost, hypervolume, safety "
    "verdict) originates from a frozen deterministic tool, never from the model. The agent "
    "schedules nothing and requires human review before any physical action."
)
_LLM_NOT_CONFIGURED_NOTE = (
    "External LLM guidance is not configured. The deterministic rule-based reaction agent was used."
)
_NO_SAFETY_EXECUTOR_NOTE = (
    "No safety executor was supplied; the safety pre-check failed closed and execution is blocked."
)

SYSTEM_PROMPT = (
    "You are MolTrace's reaction-optimization planning assistant for process chemists. "
    "You orchestrate frozen, deterministic tools and you DO NOT perform arithmetic yourself.\n\n"
    "Hard rules (non-negotiable):\n"
    "1. You must NOT compute, estimate, or invent any quantitative value — yields, conversions, "
    "scores, uncertainties, costs, hypervolume, green metrics, or safety verdicts. Every number "
    "you state must come verbatim from a tool result, and you must cite the tool by name.\n"
    "2. A mandatory safety pre-check has already been run. If its status is not 'clear', you must "
    "not recommend that any physical experiment be run; say so explicitly and recommend the human "
    "reviewer resolve the safety screening first.\n"
    "3. Before recommending any physical action, the safety pre-check (or an assess_safety call) "
    "must support it. Safety verdicts come only from the tool.\n"
    "4. You plan, narrate, prioritize, and re-rank with citations. The chemist reviews and "
    "decides; you schedule nothing.\n\n"
    "Produce a short, cited plan grounded only in tool outputs. When you have nothing further to "
    "compute, stop calling tools and give the plan."
)


# --------------------------------------------------------------------------- #
# Anthropic tool definitions (schemas only; executors are injected at runtime).
# --------------------------------------------------------------------------- #
REACTION_AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "recommend_next_batch",
        "description": (
            "Return the frozen Bayesian-optimization-ranked next batch of candidate reaction "
            "conditions with their predicted scores, expected improvement, and uncertainty. Call "
            "this when the chemist asks what to run next. Do not invent candidates or scores — "
            "they come only from this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "batch_size": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "How many candidates to rank (defaults to the project setting).",
                },
                "algorithm": {
                    "type": "string",
                    "description": "Acquisition strategy identifier (optional; uses the default).",
                },
                "safety_aware": {
                    "type": "boolean",
                    "description": "Whether to keep safety-aware acquisition filtering on.",
                },
                "cost_aware": {
                    "type": "boolean",
                    "description": "Whether to keep cost-aware acquisition filtering on.",
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "assess_safety",
        "description": (
            "Return the frozen structural safety screen and gate status (clear / review_pending / "
            "blocked) for a reaction or proposed conditions. Call this before recommending any "
            "physical experiment. Safety verdicts originate only from this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "conditions": {
                    "type": "object",
                    "description": "Proposed reaction conditions to screen (optional).",
                    "additionalProperties": True,
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "calculate_green_metrics",
        "description": (
            "Return frozen green-chemistry metrics (e.g. PMI, E-factor, solvent score, atom "
            "economy) for a route or condition set. Call this to compare candidates on "
            "sustainability. All metric values come only from this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "conditions": {
                    "type": "object",
                    "description": "Conditions or route reference to score (optional).",
                    "additionalProperties": True,
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "retrieve_precedents",
        "description": (
            "Return frozen, cited literature/precedent matches for a query. Every precedent or "
            "citation you mention must come from this tool — never from your own memory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text precedent query (reaction class, substrate, motif).",
                },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "How many precedent matches to return (optional).",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "design_plate",
        "description": (
            "Return a frozen, deterministic high-throughput-experimentation plate map for the "
            "given format and variables. Plate layouts come only from this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "plate_format": {
                    "type": "string",
                    "enum": ["24", "48", "96", "384"],
                    "description": "Well-plate format.",
                },
                "variables": {
                    "type": "object",
                    "description": "Factors and levels to lay out across the plate (optional).",
                    "additionalProperties": True,
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "summarize_cycle",
        "description": (
            "Return frozen design-make-test-analyze loop metrics for a cycle "
            "(experiments-to-target, phase latencies, best objective and gap to target). All "
            "metrics come only from this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cycle_id": {
                    "type": "integer",
                    "description": "Optimization cycle to summarize (optional; uses the latest).",
                },
            },
            "additionalProperties": False,
        },
    },
]

REACTION_AGENT_TOOL_NAMES: frozenset[str] = frozenset(tool["name"] for tool in REACTION_AGENT_TOOLS)
# Tools that imply or precede physical action and therefore require a clear safety gate.
_ACTION_TOOLS: frozenset[str] = frozenset({"recommend_next_batch", "design_plate"})

ToolExecutor = Callable[[dict[str, Any]], dict[str, Any]]


# --------------------------------------------------------------------------- #
# Result types.
# --------------------------------------------------------------------------- #
@dataclass
class ReactionAgentToolCall:
    """One frozen tool invocation — the *only* source of quantitative truth."""

    name: str
    arguments: dict[str, Any]
    output: dict[str, Any]
    tool_use_id: str | None = None
    is_error: bool = False
    source: str = "tool"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "output": self.output,
            "tool_use_id": self.tool_use_id,
            "is_error": self.is_error,
            "source": self.source,
        }


@dataclass
class ReactionAgentResult:
    """Math-frozen agent output.

    Consumers must read quantitative values from :attr:`tool_calls` (the frozen
    provenance) — never parse them out of :attr:`narrative`, which is untrusted
    model prose by design.
    """

    mode: str  # "claude_tool_agent" | "rule_based_fallback"
    llm_used: bool
    model_version: str | None
    narrative: str
    plan: list[str] = field(default_factory=list)
    tool_calls: list[ReactionAgentToolCall] = field(default_factory=list)
    safety_precheck: dict[str, Any] | None = None
    execution_blocked: bool = True
    warnings: list[str] = field(default_factory=list)
    transcript: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str | None = None
    disclaimer: str = AGENT_DISCLAIMER
    human_review_required: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "llm_used": self.llm_used,
            "model_version": self.model_version,
            "narrative": self.narrative,
            "plan": list(self.plan),
            "tool_calls": [call.as_dict() for call in self.tool_calls],
            "safety_precheck": self.safety_precheck,
            "execution_blocked": self.execution_blocked,
            "warnings": list(self.warnings),
            "transcript": self.transcript,
            "stop_reason": self.stop_reason,
            "disclaimer": self.disclaimer,
            "human_review_required": self.human_review_required,
            "engine": "reaction_agent.v1",
        }


class ReactionAgentError(Exception):
    """Raised for caller/configuration errors (not for model refusals)."""


# --------------------------------------------------------------------------- #
# Public entrypoint.
# --------------------------------------------------------------------------- #
def run_reaction_agent(
    *,
    goal: str,
    tool_executors: Mapping[str, ToolExecutor],
    safety_precheck_arguments: dict[str, Any] | None = None,
    fallback_tool_plan: Sequence[tuple[str, dict[str, Any]]] = (),
    extra_context: str | None = None,
    client: Any | None = None,
    client_factory: Callable[[], Any] | None = None,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    max_iterations: int = _MAX_AGENT_ITERATIONS,
    max_tokens: int = _MAX_TOKENS,
) -> ReactionAgentResult:
    """Run the math-frozen reaction planner.

    Parameters
    ----------
    goal:
        The chemist's natural-language objective for this planning turn.
    tool_executors:
        Mapping of tool name -> frozen deterministic callable. Keys must be a
        subset of :data:`REACTION_AGENT_TOOL_NAMES`. Each callable receives the
        model's validated tool input and returns a JSON-serialisable ``dict``.
    safety_precheck_arguments:
        Arguments passed to the mandatory ``assess_safety`` pre-check.
    fallback_tool_plan:
        Ordered ``(tool_name, arguments)`` pairs run deterministically when no
        LLM is available, so the no-key path still produces grounded provenance.
    client / client_factory / model / api_key:
        Provider-portable client wiring. ``client`` wins; else ``client_factory``;
        else a first-party ``anthropic.Anthropic`` client is built lazily. When
        none can be constructed, the rule-based fallback path runs.
    """

    unknown = set(tool_executors) - REACTION_AGENT_TOOL_NAMES
    if unknown:
        raise ReactionAgentError(f"Unknown reaction tool(s): {sorted(unknown)}")

    warnings: list[str] = []
    tool_calls: list[ReactionAgentToolCall] = []

    # --- Mandatory, fail-closed safety pre-check ------------------------------
    safety_precheck, execution_blocked, precheck_call = _run_safety_precheck(
        tool_executors, safety_precheck_arguments or {}, warnings
    )
    if precheck_call is not None:
        tool_calls.append(precheck_call)

    resolved_client = _resolve_client(client, client_factory, api_key)
    if resolved_client is None:
        warnings.append(_LLM_NOT_CONFIGURED_NOTE)
        return _run_fallback(
            goal=goal,
            tool_executors=tool_executors,
            fallback_tool_plan=fallback_tool_plan,
            safety_precheck=safety_precheck,
            execution_blocked=execution_blocked,
            warnings=warnings,
            tool_calls=tool_calls,
        )

    return _run_llm_agent(
        goal=goal,
        tool_executors=tool_executors,
        safety_precheck=safety_precheck,
        execution_blocked=execution_blocked,
        extra_context=extra_context,
        client=resolved_client,
        model=model,
        max_iterations=max_iterations,
        max_tokens=max_tokens,
        warnings=warnings,
        tool_calls=tool_calls,
    )


def assert_math_frozen(result: ReactionAgentResult) -> None:
    """Best-effort structural guarantee that no number originates in the model.

    The invariant holds *by construction* — quantitative values live only in
    recorded tool outputs. This checks that contract: every tool call carries a
    dict output sourced from a tool, and the model-authored fields are strings.
    """

    for call in result.tool_calls:
        if call.source != "tool":
            raise ReactionAgentError(f"Tool call {call.name!r} is not tool-sourced.")
        if not isinstance(call.output, dict):
            raise ReactionAgentError(f"Tool call {call.name!r} output is not a frozen dict.")
    if not isinstance(result.narrative, str):
        raise ReactionAgentError("Agent narrative must be model prose (str), not a computed value.")
    if any(not isinstance(step, str) for step in result.plan):
        raise ReactionAgentError("Agent plan steps must be model prose (str).")


# --------------------------------------------------------------------------- #
# Safety pre-check.
# --------------------------------------------------------------------------- #
def _verdict_blocked(output: dict[str, Any]) -> bool:
    """Fail-closed: execution is blocked unless the frozen verdict is exactly 'clear'.

    The reaction safety engine emits only ``clear`` / ``review_pending`` / ``blocked``; anything
    that is not the literal ``clear`` (including a missing/empty status) blocks execution.
    """

    status = str(output.get("status") or output.get("gate_status") or "").lower()
    return status != "clear"


def _run_safety_precheck(
    tool_executors: Mapping[str, ToolExecutor],
    arguments: dict[str, Any],
    warnings: list[str],
) -> tuple[dict[str, Any] | None, bool, ReactionAgentToolCall | None]:
    executor = tool_executors.get("assess_safety")
    if executor is None:
        # Fail closed: with no safety executor we cannot certify safe, so block execution.
        warnings.append(_NO_SAFETY_EXECUTOR_NOTE)
        return None, True, None
    call = _dispatch_tool("assess_safety", executor, arguments, tool_use_id=None)
    if call.is_error:
        warnings.append("Safety pre-check failed to run; execution is blocked.")
        return call.output, True, call
    blocked = _verdict_blocked(call.output)
    if blocked:
        status = call.output.get("status") or call.output.get("gate_status") or "unknown"
        warnings.append(f"Safety pre-check status is {status!r}; execution is blocked.")
    return call.output, blocked, call


# --------------------------------------------------------------------------- #
# Rule-based (no-LLM) fallback path.
# --------------------------------------------------------------------------- #
def _run_fallback(
    *,
    goal: str,
    tool_executors: Mapping[str, ToolExecutor],
    fallback_tool_plan: Sequence[tuple[str, dict[str, Any]]],
    safety_precheck: dict[str, Any] | None,
    execution_blocked: bool,
    warnings: list[str],
    tool_calls: list[ReactionAgentToolCall],
) -> ReactionAgentResult:
    plan: list[str] = []
    for name, arguments in fallback_tool_plan:
        if name not in REACTION_AGENT_TOOL_NAMES:
            raise ReactionAgentError(f"Unknown reaction tool in fallback plan: {name!r}")
        executor = tool_executors.get(name)
        if executor is None:
            warnings.append(f"Fallback tool {name!r} is not available; skipped.")
            continue
        if name in _ACTION_TOOLS and execution_blocked:
            warnings.append(
                f"Fallback skipped action tool {name!r} because the safety gate is not clear."
            )
            continue
        call = _dispatch_tool(name, executor, dict(arguments), tool_use_id=None)
        tool_calls.append(call)
        plan.append(f"Ran {name} (frozen); see recorded tool output for values.")

    narrative = (
        f"{_LLM_NOT_CONFIGURED_NOTE} Goal: {goal}. The deterministic agent executed the configured "
        "frozen tools and recorded their outputs verbatim; no value was computed by a model. "
    )
    if execution_blocked:
        narrative += (
            "The safety gate is not clear, so no physical experiment is recommended; resolve the "
            "safety screening first."
        )
    else:
        narrative += "Human review is required before scheduling any experiment."

    return ReactionAgentResult(
        mode="rule_based_fallback",
        llm_used=False,
        model_version=None,
        narrative=narrative,
        plan=plan,
        tool_calls=tool_calls,
        safety_precheck=safety_precheck,
        execution_blocked=execution_blocked,
        warnings=warnings,
        transcript=[{"role": "user", "content": goal}],
        stop_reason="fallback",
    )


# --------------------------------------------------------------------------- #
# Claude tool-use agentic loop.
# --------------------------------------------------------------------------- #
def _run_llm_agent(
    *,
    goal: str,
    tool_executors: Mapping[str, ToolExecutor],
    safety_precheck: dict[str, Any] | None,
    execution_blocked: bool,
    extra_context: str | None,
    client: Any,
    model: str,
    max_iterations: int,
    max_tokens: int,
    warnings: list[str],
    tool_calls: list[ReactionAgentToolCall],
) -> ReactionAgentResult:
    # Advertise only tools we can actually execute (math stays frozen + grounded).
    tools = [tool for tool in REACTION_AGENT_TOOLS if tool["name"] in tool_executors]

    opening = _opening_user_message(goal, safety_precheck, execution_blocked, extra_context)
    messages: list[dict[str, Any]] = [{"role": "user", "content": opening}]
    transcript: list[dict[str, Any]] = [{"role": "user", "content": opening}]

    model_version: str | None = None
    narrative_parts: list[str] = []
    stop_reason: str | None = None

    for _ in range(max_iterations):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )
        except Exception as exc:  # noqa: BLE001  (provider/transport error -> degrade, keep provenance)
            request_id = getattr(exc, "request_id", None) or getattr(exc, "_request_id", None)
            suffix = f" (request_id={request_id})" if request_id else ""
            warnings.append(f"Model request failed; returning partial provenance: {exc}{suffix}")
            stop_reason = "api_error"
            break
        model_version = getattr(response, "model", None) or model
        stop_reason = getattr(response, "stop_reason", None)
        content = list(getattr(response, "content", []) or [])
        transcript.append({"role": "assistant", "content": [_block_to_dict(b) for b in content]})

        if stop_reason == "refusal":
            warnings.append("The model declined this planning request (refusal).")
            break

        # Preserve full assistant content (incl. thinking blocks) for the next turn.
        messages.append({"role": "assistant", "content": content})

        for block in content:
            if _block_type(block) == "text":
                text = _block_text(block)
                if text:
                    narrative_parts.append(text)

        if stop_reason == "pause_turn":
            # Server-side tool loop paused; resend to resume (no extra user text).
            continue

        tool_use_blocks = [b for b in content if _block_type(b) == "tool_use"]
        if stop_reason != "tool_use" or not tool_use_blocks:
            break

        # Dispatch safety re-checks first so a fresh non-clear verdict tightens the gate BEFORE
        # any action tool requested in the same turn is evaluated.
        tool_use_blocks.sort(key=lambda b: 0 if _block_name(b) == "assess_safety" else 1)

        tool_results: list[dict[str, Any]] = []
        for block in tool_use_blocks:
            name = _block_name(block)
            arguments = _block_input(block)
            tool_use_id = _block_id(block)
            executor = tool_executors.get(name)
            if executor is None:
                call = ReactionAgentToolCall(
                    name=name,
                    arguments=arguments,
                    output={"error": "tool_not_available"},
                    tool_use_id=tool_use_id,
                    is_error=True,
                )
            elif name in _ACTION_TOOLS and execution_blocked:
                call = ReactionAgentToolCall(
                    name=name,
                    arguments=arguments,
                    output={"error": "safety_gate_not_clear", "execution_blocked": True},
                    tool_use_id=tool_use_id,
                    is_error=True,
                )
            else:
                call = _dispatch_tool(name, executor, arguments, tool_use_id=tool_use_id)
                # A mid-loop safety re-check can only ever TIGHTEN the gate (never relax it),
                # and it becomes the authoritative verdict surfaced as safety_precheck so the
                # returned gate flag matches the latest frozen safety output.
                if name == "assess_safety" and (call.is_error or _verdict_blocked(call.output)):
                    if not execution_blocked:
                        warnings.append(
                            "A mid-plan safety re-check is not clear; execution is now blocked."
                        )
                    execution_blocked = True
                    safety_precheck = call.output
            tool_calls.append(call)
            # A tool_result with a null tool_use_id is an invalid Anthropic request; record the
            # malformed call as an error but never echo a null id back to the API.
            if not tool_use_id:
                call.is_error = True
                continue
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": _json_dump(call.output),
                    "is_error": call.is_error,
                }
            )

        user_turn = {"role": "user", "content": tool_results}
        messages.append(user_turn)
        transcript.append(user_turn)
    else:
        warnings.append(f"Agent reached the {max_iterations}-iteration cap before finishing.")

    narrative = "\n\n".join(part for part in narrative_parts if part).strip()
    if not narrative:
        narrative = "The model produced no final plan text."

    return ReactionAgentResult(
        mode="claude_tool_agent",
        llm_used=True,
        model_version=model_version,
        narrative=narrative,
        plan=_narrative_to_plan(narrative),
        tool_calls=tool_calls,
        safety_precheck=safety_precheck,
        execution_blocked=execution_blocked,
        warnings=warnings,
        transcript=transcript,
        stop_reason=stop_reason,
    )


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
def _resolve_client(
    client: Any | None,
    client_factory: Callable[[], Any] | None,
    api_key: str | None,
) -> Any | None:
    if client is not None:
        return client
    if client_factory is not None:
        return client_factory()
    return _default_anthropic_client(api_key)


def _default_anthropic_client(api_key: str | None) -> Any | None:
    try:
        import anthropic  # noqa: PLC0415  (optional dependency; imported lazily)
    except ImportError:
        return None
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    return anthropic.Anthropic(api_key=key)


def _dispatch_tool(
    name: str,
    executor: ToolExecutor,
    arguments: dict[str, Any],
    *,
    tool_use_id: str | None,
) -> ReactionAgentToolCall:
    try:
        output = executor(arguments)
    except Exception as exc:  # noqa: BLE001  (record, never crash the loop)
        return ReactionAgentToolCall(
            name=name,
            arguments=arguments,
            output={"error": "tool_execution_failed", "detail": str(exc)},
            tool_use_id=tool_use_id,
            is_error=True,
        )
    if not isinstance(output, dict):
        return ReactionAgentToolCall(
            name=name,
            arguments=arguments,
            output={"error": "tool_output_not_dict", "value": str(output)},
            tool_use_id=tool_use_id,
            is_error=True,
        )
    return ReactionAgentToolCall(
        name=name,
        arguments=arguments,
        output=output,
        tool_use_id=tool_use_id,
        is_error=False,
    )


def _opening_user_message(
    goal: str,
    safety_precheck: dict[str, Any] | None,
    execution_blocked: bool,
    extra_context: str | None,
) -> str:
    lines = [f"Goal: {goal}"]
    if safety_precheck is not None:
        status = safety_precheck.get("status") or safety_precheck.get("gate_status") or "unknown"
        lines.append(f"Mandatory safety pre-check status: {status}.")
    else:
        lines.append("Mandatory safety pre-check: unavailable (treat execution as blocked).")
    if execution_blocked:
        lines.append(
            "The safety gate is NOT clear: do not recommend running any physical experiment; "
            "recommend resolving the safety screening first."
        )
    if extra_context:
        lines.append(f"Context: {extra_context}")
    lines.append(
        "Use the tools to ground every quantitative claim, cite each tool by name, and return a "
        "short plan."
    )
    return "\n".join(lines)


def _narrative_to_plan(narrative: str) -> list[str]:
    steps: list[str] = []
    for raw in narrative.splitlines():
        line = raw.strip().lstrip("-*0123456789. )").strip()
        if line:
            steps.append(line)
    return steps[:12]


def _json_dump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, default=str)


# --- response-block accessors (tolerate SDK objects and plain dicts) -------- #
def _block_type(block: Any) -> str:
    if isinstance(block, dict):
        return str(block.get("type") or "")
    return str(getattr(block, "type", "") or "")


def _block_text(block: Any) -> str:
    if isinstance(block, dict):
        return str(block.get("text") or "")
    return str(getattr(block, "text", "") or "")


def _block_name(block: Any) -> str:
    if isinstance(block, dict):
        return str(block.get("name") or "")
    return str(getattr(block, "name", "") or "")


def _block_id(block: Any) -> str | None:
    if isinstance(block, dict):
        value = block.get("id")
    else:
        value = getattr(block, "id", None)
    return str(value) if value is not None else None


def _block_input(block: Any) -> dict[str, Any]:
    if isinstance(block, dict):
        value = block.get("input")
    else:
        value = getattr(block, "input", None)
    return value if isinstance(value, dict) else {}


def _block_to_dict(block: Any) -> dict[str, Any]:
    btype = _block_type(block)
    if btype == "text":
        return {"type": "text", "text": _block_text(block)}
    if btype == "tool_use":
        return {
            "type": "tool_use",
            "id": _block_id(block),
            "name": _block_name(block),
            "input": _block_input(block),
        }
    if btype == "thinking":
        if isinstance(block, dict):
            thinking = block.get("thinking")
        else:
            thinking = getattr(block, "thinking", "")
        return {"type": "thinking", "thinking": str(thinking or "")}
    return {"type": btype or "unknown"}
