"""Wire-level contract for ``POST /spectrum/reason`` (Prompt 14 RAG reasoner endpoint).

Pins the request/response shape and the graceful-degradation behaviour that makes
the endpoint safe to wire to the UI:

* retrieval runs whenever ``MOLTRACE_SIMILARITY_INDEX`` is configured (and the
  optional ``MOLTRACE_SIMILARITY_METADATA`` sidecar grounds analogue SMILES /
  licenses), reported via ``index_available`` + ``retrieved``;
* reasoning runs only when the model backend is available, reported via
  ``reasoner_available`` — when unavailable the endpoint returns retrieval only
  rather than failing;
* the verifier (not the model) decides ``accepted`` — the response separates
  verifier-accepted ``candidates`` from ``rejected`` ones for audit.

The reasoning model is never called here: the happy path injects a fake
``propose_structures`` (the LLM + verifier are exercised in
``tests/test_ai_rag.py`` and the verification suite). Retrieval numerics live in
``tests/spectroscopy/test_similarity_scoring.py``.
"""

from __future__ import annotations

import json

import numpy as np
from fastapi.testclient import TestClient

from moltrace.spectroscopy.ai import rag as rag_module
from moltrace.spectroscopy.ai.rag import (
    Candidate,
    ProposalResult,
    RAGAudit,
)
from moltrace.spectroscopy.similarity import SpectrumIndex, encode_spectrum
from nmrcheck import api as api_module
from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _app(tmp_path):
    return create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'reason.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
            admin_emails=("admin@example.com",),
        )
    )


def _client(tmp_path) -> TestClient:
    return TestClient(_app(tmp_path))


def _post(client: TestClient, body: dict, key: str | None = "test-key"):
    headers = {"x-api-key": key} if key else {}
    return client.post("/spectrum/reason", headers=headers, json=body)


def _synth_spectrum(n: int = 2048) -> tuple[list[float], list[float]]:
    """A clean 1H spectrum with three well-separated Lorentzian peaks.

    GSD reliably picks these, but retrieval is robust even to a degenerate
    encoding (a zero query still returns the k nearest), so the exact peak set
    does not matter to these wire-level assertions.
    """
    x = np.linspace(0.0, 10.0, n)
    y = np.zeros_like(x)
    for centre, amp, hwhm in ((7.26, 1.0, 0.01), (3.60, 0.8, 0.01), (1.20, 0.9, 0.01)):
        y += amp * hwhm * hwhm / ((x - centre) ** 2 + hwhm * hwhm)
    return x.tolist(), y.tolist()


def _build_index(tmp_path, refs: dict[str, tuple[list[float], list[float]]]) -> str:
    index = SpectrumIndex()
    for name, (shifts_1h, shifts_13c) in refs.items():
        index.add(encode_spectrum(shifts_1h, shifts_13c), [name])
    path = tmp_path / "ref.faiss"
    index.save(str(path))
    return str(path)


def _default_refs() -> dict[str, tuple[list[float], list[float]]]:
    return {
        "ethanol": ([3.6, 1.2], [58.0, 18.0]),
        "benzene": ([7.26], [128.4]),
        "acetone": ([2.1], [206.0, 30.0]),
    }


def _reason_body(**overrides) -> dict:
    ppm_axis, intensity = _synth_spectrum()
    body = {
        "ppm_axis": ppm_axis,
        "intensity": intensity,
        "nucleus": "1H",
        "top_k": 3,
        "max_candidates": 3,
    }
    body.update(overrides)
    return body


# --------------------------------------------------------------------------- #
# Graceful degradation
# --------------------------------------------------------------------------- #
def test_reason_not_configured_index_is_graceful(tmp_path, monkeypatch):
    monkeypatch.delenv("MOLTRACE_SIMILARITY_INDEX", raising=False)
    client = _client(tmp_path)
    with client:
        res = _post(client, _reason_body())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["index_available"] is False
    assert body["retrieved"] == []
    assert body["candidates"] == []
    assert body["rejected"] == []
    assert body["audit"] is None
    assert body["query_nucleus"] == "1H"
    assert any("not configured" in w.lower() for w in body["warnings"])


def test_reason_retrieval_only_when_reasoner_unavailable(tmp_path, monkeypatch):
    path = _build_index(tmp_path, _default_refs())
    monkeypatch.setenv("MOLTRACE_SIMILARITY_INDEX", path)
    monkeypatch.delenv("MOLTRACE_SIMILARITY_METADATA", raising=False)
    monkeypatch.setattr(api_module, "_reasoning_llm_available", lambda: False)
    client = _client(tmp_path)
    with client:
        res = _post(client, _reason_body())
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["index_available"] is True
    assert body["reasoner_available"] is False
    assert body["index_size"] == 3
    # Retrieval still ran: analogues populated with bounded similarity + license.
    assert body["retrieved"]
    first = body["retrieved"][0]
    assert {"analogue_id", "smiles", "similarity", "l2_distance", "rank", "license"} <= set(first)
    assert 0.0 < first["similarity"] <= 1.0
    assert first["rank"] == 0
    # No reasoning happened.
    assert body["candidates"] == []
    assert body["rejected"] == []
    assert body["audit"] is None
    assert any("model backend unavailable" in w.lower() for w in body["warnings"])


def test_reason_happy_path_injected_reasoner(tmp_path, monkeypatch):
    path = _build_index(tmp_path, _default_refs())
    monkeypatch.setenv("MOLTRACE_SIMILARITY_INDEX", path)
    monkeypatch.setattr(api_module, "_reasoning_llm_available", lambda: True)

    captured: dict = {}

    def _fake_propose(spectrum, context, *, max_candidates=5, model="m", **kwargs):
        captured["max_candidates"] = max_candidates
        captured["model"] = model
        captured["analogue_ids"] = [a.analogue_id for a in context.analogues]
        accepted = Candidate(
            smiles="c1ccccc1",
            rationale="ring shifts match the benzene precedent",
            cited_analogue_ids=["benzene"],
            self_confidence=0.95,  # advisory only
            cited_valid_ids=["benzene"],
            retrieval_supported=True,
            posterior_confidence=0.88,
            verdict="consistent",
            accepted=True,
        )
        guarded = Candidate(
            smiles="CCO",
            rationale="ungrounded guess",
            cited_analogue_ids=[],
            self_confidence=0.99,  # high self-confidence must NOT win
            cited_valid_ids=[],
            retrieval_supported=False,
            accepted=False,
            dropped_reason="hallucination_guard",
        )
        audit = RAGAudit(
            model=model,
            query_fingerprint=context.query_fingerprint,
            retrieved_ids=[a.analogue_id for a in context.analogues],
            system_prompt="SYS",
            user_prompt="USR",
            raw_completions=['{"candidates": []}'],
            retry_used=False,
            parsed_candidate_count=2,
            dropped_candidate_count=1,
            accepted_candidate_count=1,
        )
        return ProposalResult(candidates=[accepted, guarded], context=context, audit=audit)

    monkeypatch.setattr(rag_module, "propose_structures", _fake_propose)

    client = _client(tmp_path)
    with client:
        res = _post(client, _reason_body(max_candidates=4))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["index_available"] is True
    assert body["reasoner_available"] is True
    # The endpoint forwards its request bounds to the reasoner.
    assert captured["max_candidates"] == 4
    assert captured["model"] == "claude-opus-4-8"
    assert captured["analogue_ids"]  # real retrieval fed the (fake) reasoner

    # Verifier-accepted candidate surfaces in `candidates`; guarded one in `rejected`.
    assert len(body["candidates"]) == 1
    cand = body["candidates"][0]
    assert cand["smiles"] == "c1ccccc1"
    assert cand["accepted"] is True
    assert cand["verdict"] == "consistent"
    assert cand["posterior_confidence"] == 0.88
    assert cand["self_confidence"] == 0.95
    assert cand["dropped_reason"] is None

    assert len(body["rejected"]) == 1
    rej = body["rejected"][0]
    assert rej["smiles"] == "CCO"
    assert rej["accepted"] is False
    assert rej["dropped_reason"] == "hallucination_guard"

    # Audit summary surfaces the traceable essentials.
    audit = body["audit"]
    assert audit is not None
    assert audit["model"] == "claude-opus-4-8"
    assert audit["accepted_candidate_count"] == 1
    assert audit["dropped_candidate_count"] == 1
    assert audit["retry_used"] is False
    assert "benzene" in audit["retrieved_ids"] or audit["retrieved_ids"]


# --------------------------------------------------------------------------- #
# Metadata sidecar (analogue grounding) + license-aware retrieval
# --------------------------------------------------------------------------- #
def test_reason_metadata_sidecar_grounds_analogue(tmp_path, monkeypatch):
    # An index keyed by an opaque database id; the sidecar resolves it to SMILES.
    path = _build_index(tmp_path, {"db:001": ([7.26], [128.4])})
    meta_path = tmp_path / "meta.json"
    meta_path.write_text(
        json.dumps(
            {"db:001": {"smiles": "c1ccccc1", "license": "CC-BY-SA", "source": "nmrshiftdb2"}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MOLTRACE_SIMILARITY_INDEX", path)
    monkeypatch.setenv("MOLTRACE_SIMILARITY_METADATA", str(meta_path))
    monkeypatch.setattr(api_module, "_reasoning_llm_available", lambda: False)
    client = _client(tmp_path)
    with client:
        res = _post(client, _reason_body(top_k=1))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["retrieved"]
    hit = body["retrieved"][0]
    assert hit["analogue_id"] == "db:001"
    assert hit["smiles"] == "c1ccccc1"  # resolved from the sidecar, not the id
    assert hit["license"] == "CC-BY-SA"
    assert hit["source"] == "nmrshiftdb2"


def test_reason_license_allow_list_filters(tmp_path, monkeypatch):
    path = _build_index(tmp_path, {"db:001": ([7.26], [128.4])})
    meta_path = tmp_path / "meta.json"
    meta_path.write_text(
        json.dumps({"db:001": {"smiles": "c1ccccc1", "license": "CC-BY-SA"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MOLTRACE_SIMILARITY_INDEX", path)
    monkeypatch.setenv("MOLTRACE_SIMILARITY_METADATA", str(meta_path))
    monkeypatch.setattr(api_module, "_reasoning_llm_available", lambda: False)
    client = _client(tmp_path)
    with client:
        res = _post(client, _reason_body(top_k=1, allowed_licenses=["MIT"]))
    assert res.status_code == 200, res.text
    body = res.json()
    # The only analogue's CC-BY-SA license is not in the MIT allow-list -> dropped.
    assert body["retrieved"] == []
    assert any("allow-list" in w.lower() for w in body["warnings"])


# --------------------------------------------------------------------------- #
# Validation + auth + registration
# --------------------------------------------------------------------------- #
def test_reason_length_mismatch_is_400(tmp_path, monkeypatch):
    monkeypatch.delenv("MOLTRACE_SIMILARITY_INDEX", raising=False)
    client = _client(tmp_path)
    body = {"ppm_axis": [0.0] * 16, "intensity": [0.0] * 17}
    with client:
        res = _post(client, body)
    assert res.status_code == 400, res.text


def test_reason_array_too_short_is_422(tmp_path):
    client = _client(tmp_path)
    body = {"ppm_axis": [0.0] * 8, "intensity": [0.0] * 8}
    with client:
        res = _post(client, body)
    assert res.status_code == 422


def test_reason_bounds_are_validated(tmp_path):
    client = _client(tmp_path)
    with client:
        assert _post(client, _reason_body(top_k=0)).status_code == 422
        assert _post(client, _reason_body(top_k=5000)).status_code == 422
        assert _post(client, _reason_body(max_candidates=0)).status_code == 422
        assert _post(client, _reason_body(max_candidates=999)).status_code == 422


def test_reason_requires_auth(tmp_path):
    client = _client(tmp_path)
    with client:
        res = _post(client, _reason_body(), key=None)
    assert res.status_code in (401, 403)


def test_reason_registered_in_openapi(tmp_path):
    paths = _app(tmp_path).openapi()["paths"]
    assert "/spectrum/reason" in paths
    assert "post" in paths["/spectrum/reason"]
