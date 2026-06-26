"""Unit tests for the Repho R8 Claude reaction agent (math frozen, no network).

Every test runs without an API key: the LLM path is exercised with a scripted
fake Anthropic client, and the no-key path is exercised directly.
"""

from __future__ import annotations

from typing import Any

import pytest

from nmrcheck.reaction_agent import (
    REACTION_AGENT_TOOL_NAMES,
    REACTION_AGENT_TOOLS,
    ReactionAgentError,
    assert_math_frozen,
    run_reaction_agent,
)


# --------------------------------------------------------------------------- #
# Scripted fake Anthropic client (no network).
# --------------------------------------------------------------------------- #
class _Block:
    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


class _Response:
    def __init__(self, content: list[_Block], stop_reason: str, model: str = "claude-opus-4-8"):
        self.content = content
        self.stop_reason = stop_reason
        self.model = model


class _FakeMessages:
    def __init__(self, scripted: list[_Response]) -> None:
        self._scripted = list(scripted)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _Response:
        self.calls.append(kwargs)
        return self._scripted.pop(0)


class _FakeClient:
    def __init__(self, scripted: list[_Response]) -> None:
        self.messages = _FakeMessages(scripted)


def _text(text: str) -> _Block:
    return _Block(type="text", text=text)


def _tool_use(name: str, inp: dict[str, Any], tid: str = "toolu_1") -> _Block:
    return _Block(type="tool_use", id=tid, name=name, input=inp)


# --------------------------------------------------------------------------- #
# Deterministic frozen executors.
# --------------------------------------------------------------------------- #
def _safety_clear(_args: dict[str, Any]) -> dict[str, Any]:
    return {"status": "clear", "screen": "no_structural_alerts"}


def _safety_blocked(_args: dict[str, Any]) -> dict[str, Any]:
    return {"status": "blocked", "reason": "energetic_motif"}


def _safety_by_conditions(args: dict[str, Any]) -> dict[str, Any]:
    # Clear at the project level (no conditions -> the mandatory pre-check), but blocked when
    # the model re-screens specific candidate conditions mid-loop.
    if args.get("conditions"):
        return {"status": "blocked", "reason": "candidate_specific_hazard"}
    return {"status": "clear"}


class _RaisingMessages:
    def create(self, **_kwargs: Any) -> Any:
        raise RuntimeError("provider boom")


class _RaisingClient:
    def __init__(self) -> None:
        self.messages = _RaisingMessages()


# --------------------------------------------------------------------------- #
# Tool definitions.
# --------------------------------------------------------------------------- #
def test_tool_definitions_are_valid_anthropic_schemas():
    assert {t["name"] for t in REACTION_AGENT_TOOLS} == REACTION_AGENT_TOOL_NAMES
    assert REACTION_AGENT_TOOL_NAMES == {
        "recommend_next_batch",
        "assess_safety",
        "calculate_green_metrics",
        "retrieve_precedents",
        "design_plate",
        "summarize_cycle",
    }
    for tool in REACTION_AGENT_TOOLS:
        assert tool["description"]
        schema = tool["input_schema"]
        assert schema["type"] == "object"
        assert "properties" in schema


def test_unknown_executor_is_rejected():
    with pytest.raises(ReactionAgentError):
        run_reaction_agent(goal="x", tool_executors={"not_a_tool": _safety_clear})


# --------------------------------------------------------------------------- #
# No-key rule-based fallback.
# --------------------------------------------------------------------------- #
def test_fallback_runs_frozen_tools_without_a_model(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    calls: list[dict[str, Any]] = []

    def _recommend(args: dict[str, Any]) -> dict[str, Any]:
        calls.append(args)
        return {"candidates": [{"rank": 1, "predicted_score": 0.91}]}

    result = run_reaction_agent(
        goal="What should we run next?",
        tool_executors={"assess_safety": _safety_clear, "recommend_next_batch": _recommend},
        fallback_tool_plan=[("recommend_next_batch", {"batch_size": 3})],
        # Force the fallback path explicitly (no client, no key).
        client=None,
    )

    assert result.mode == "rule_based_fallback"
    assert result.llm_used is False
    assert result.model_version is None
    assert result.execution_blocked is False
    assert result.safety_precheck == {"status": "clear", "screen": "no_structural_alerts"}
    # The frozen recommend tool actually ran and its output is recorded provenance.
    assert calls == [{"batch_size": 3}]
    names = [c.name for c in result.tool_calls]
    assert "assess_safety" in names and "recommend_next_batch" in names
    rec = next(c for c in result.tool_calls if c.name == "recommend_next_batch")
    assert rec.output["candidates"][0]["predicted_score"] == 0.91
    assert_math_frozen(result)


def test_no_safety_executor_fails_closed(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = run_reaction_agent(goal="plan", tool_executors={}, client=None)
    assert result.execution_blocked is True
    assert result.safety_precheck is None
    assert any("safety" in w.lower() for w in result.warnings)


def test_fallback_skips_action_tool_when_safety_blocked(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ran: list[str] = []

    def _recommend(_args: dict[str, Any]) -> dict[str, Any]:
        ran.append("recommend")
        return {"candidates": []}

    result = run_reaction_agent(
        goal="run next",
        tool_executors={"assess_safety": _safety_blocked, "recommend_next_batch": _recommend},
        fallback_tool_plan=[("recommend_next_batch", {})],
        client=None,
    )
    assert result.execution_blocked is True
    assert ran == []  # action tool skipped because the safety gate is not clear
    assert any("safety gate is not clear" in w for w in result.warnings)


# --------------------------------------------------------------------------- #
# Claude tool-use loop (scripted client).
# --------------------------------------------------------------------------- #
def test_llm_loop_dispatches_tool_and_records_provenance():
    seen: list[dict[str, Any]] = []

    def _recommend(args: dict[str, Any]) -> dict[str, Any]:
        seen.append(args)
        return {"candidates": [{"rank": 1, "predicted_score": 0.88}]}

    client = _FakeClient(
        [
            _Response([_tool_use("recommend_next_batch", {"batch_size": 4})], "tool_use"),
            _Response([_text("Run candidate 1 (recommend_next_batch).")], "end_turn"),
        ]
    )
    result = run_reaction_agent(
        goal="Plan the next batch.",
        tool_executors={"assess_safety": _safety_clear, "recommend_next_batch": _recommend},
        client=client,
    )

    assert result.mode == "claude_tool_agent"
    assert result.llm_used is True
    assert result.model_version == "claude-opus-4-8"
    assert result.stop_reason == "end_turn"
    assert seen == [{"batch_size": 4}]  # model's tool input reached the frozen executor
    rec = next(c for c in result.tool_calls if c.name == "recommend_next_batch")
    assert rec.is_error is False
    assert rec.output["candidates"][0]["predicted_score"] == 0.88
    assert "recommend_next_batch" in result.narrative
    # Only executable tools are advertised to the model.
    advertised = {t["name"] for t in client.messages.calls[0]["tools"]}
    assert advertised == {"assess_safety", "recommend_next_batch"}
    assert_math_frozen(result)


def test_llm_loop_blocks_action_tool_when_safety_not_clear():
    ran: list[str] = []

    def _recommend(_args: dict[str, Any]) -> dict[str, Any]:
        ran.append("recommend")
        return {"candidates": []}

    client = _FakeClient(
        [
            _Response([_tool_use("recommend_next_batch", {})], "tool_use"),
            _Response([_text("Safety gate is blocked; resolve screening first.")], "end_turn"),
        ]
    )
    result = run_reaction_agent(
        goal="Run the next batch now.",
        tool_executors={"assess_safety": _safety_blocked, "recommend_next_batch": _recommend},
        client=client,
    )

    assert result.execution_blocked is True
    assert ran == []  # the harness refused to execute the action tool — model cannot route around it
    rec = next(c for c in result.tool_calls if c.name == "recommend_next_batch")
    assert rec.is_error is True
    assert rec.output["execution_blocked"] is True


def test_llm_refusal_is_recorded_and_stops():
    client = _FakeClient([_Response([], "refusal")])
    result = run_reaction_agent(
        goal="something",
        tool_executors={"assess_safety": _safety_clear},
        client=client,
    )
    assert result.stop_reason == "refusal"
    assert result.llm_used is True
    assert any("refus" in w.lower() for w in result.warnings)
    assert len(client.messages.calls) == 1  # stopped immediately, no extra turns


def test_client_factory_is_used():
    client = _FakeClient([_Response([_text("done")], "end_turn")])
    result = run_reaction_agent(
        goal="plan",
        tool_executors={"assess_safety": _safety_clear},
        client_factory=lambda: client,
    )
    assert result.llm_used is True
    assert len(client.messages.calls) == 1


def test_midloop_safety_recheck_tightens_gate_for_later_action():
    ran: list[str] = []

    def _recommend(_args: dict[str, Any]) -> dict[str, Any]:
        ran.append("recommend")
        return {"candidates": []}

    client = _FakeClient(
        [
            _Response([_tool_use("assess_safety", {"conditions": {"temp_c": 120}}, "t1")], "tool_use"),
            _Response([_tool_use("recommend_next_batch", {}, "t2")], "tool_use"),
            _Response([_text("Safety re-check is blocked; resolve screening first.")], "end_turn"),
        ]
    )
    result = run_reaction_agent(
        goal="What should we run next?",
        tool_executors={
            "assess_safety": _safety_by_conditions,
            "recommend_next_batch": _recommend,
        },
        client=client,
    )

    # Pre-check was clear, but a mid-loop condition-specific re-check returns blocked: the gate
    # must tighten (never relax) and the surfaced verdict must match the latest frozen output.
    assert result.execution_blocked is True
    assert result.safety_precheck == {"status": "blocked", "reason": "candidate_specific_hazard"}
    assert ran == []  # the later action tool is blocked by the tightened gate
    rec = next(c for c in result.tool_calls if c.name == "recommend_next_batch")
    assert rec.is_error is True
    assert rec.output["execution_blocked"] is True


def test_same_turn_safety_recheck_blocks_action_via_ordering():
    ran: list[str] = []

    def _recommend(_args: dict[str, Any]) -> dict[str, Any]:
        ran.append("recommend")
        return {"candidates": []}

    # The model requests the action tool and a condition-specific safety re-check in the SAME turn.
    client = _FakeClient(
        [
            _Response(
                [
                    _tool_use("recommend_next_batch", {}, "tA"),
                    _tool_use("assess_safety", {"conditions": {"x": 1}}, "tB"),
                ],
                "tool_use",
            ),
            _Response([_text("done")], "end_turn"),
        ]
    )
    result = run_reaction_agent(
        goal="run now",
        tool_executors={
            "assess_safety": _safety_by_conditions,
            "recommend_next_batch": _recommend,
        },
        client=client,
    )

    # assess_safety is dispatched first within the turn, so the action tool sees the tightened gate.
    assert ran == []
    assert result.execution_blocked is True
    rec = next(c for c in result.tool_calls if c.name == "recommend_next_batch")
    assert rec.is_error is True


def test_api_error_degrades_with_partial_provenance():
    result = run_reaction_agent(
        goal="plan",
        tool_executors={"assess_safety": _safety_clear},
        client=_RaisingClient(),
    )
    assert result.stop_reason == "api_error"
    assert result.llm_used is True
    assert any("Model request failed" in w for w in result.warnings)
    # The mandatory safety pre-check provenance survives a provider failure.
    assert any(c.name == "assess_safety" for c in result.tool_calls)


def test_null_tool_use_id_does_not_crash_or_echo_null():
    client = _FakeClient(
        [
            _Response([_Block(type="tool_use", id=None, name="assess_safety", input={})], "tool_use"),
            _Response([_text("done")], "end_turn"),
        ]
    )
    result = run_reaction_agent(
        goal="plan",
        tool_executors={"assess_safety": _safety_clear},
        client=client,
    )
    assert result.stop_reason == "end_turn"
    # The malformed (null-id) call is recorded as an error rather than echoed back to the API.
    malformed = [
        c for c in result.tool_calls if c.tool_use_id is None and c.name == "assess_safety" and c.is_error
    ]
    assert malformed


def test_assert_math_frozen_rejects_non_tool_source():
    result = run_reaction_agent(
        goal="x",
        tool_executors={"assess_safety": _safety_clear},
        client=_FakeClient([_Response([_text("ok")], "end_turn")]),
    )
    assert_math_frozen(result)  # the happy path is frozen by construction
    result.tool_calls[0].source = "model"  # tamper: pretend a number came from the model
    with pytest.raises(ReactionAgentError):
        assert_math_frozen(result)
