"""Prompt 12 — EU GMP Draft Annex 22 AI-decision governance wrapper.

Covers: the tamper-evident hash chain, the three risk levels (low logs + QA-samples, medium
auto-approves, high blocks behind HITL), the human-review approve/reject flow, chain
verification, the per-decision compliance checklist, the draft-status framing, and integration
with the Prompt 13 deterministic RoutedResult.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime

import pytest

from moltrace.regulatory.ai import RegulatoryTask, Router, TaskKind
from moltrace.regulatory.compliance import (
    DRAFT_DISCLAIMER,
    AIDecisionRecord,
    Annex22Error,
    Annex22Log,
    Annex22PendingError,
    GovernedResult,
    annex22_compliance_checklist,
    governance_context,
    with_annex22_governance,
)
from moltrace.regulatory.compliance.annex22_wrapper import GENESIS_HASH


# --------------------------------------------------------------------------- #
# Draft framing
# --------------------------------------------------------------------------- #
def test_draft_disclaimer_never_claims_compliance() -> None:
    d = DRAFT_DISCLAIMER.lower()
    assert "draft" in d
    assert "not in force" in d
    assert "not a compliance certification" in d


# --------------------------------------------------------------------------- #
# Hash chain
# --------------------------------------------------------------------------- #
def test_records_form_a_verifiable_hash_chain() -> None:
    log = Annex22Log()

    @with_annex22_governance("low")
    def f(x: int) -> dict:
        return {"v": x}

    with governance_context("alice", log):
        f(1)
        f(2)
        f(3)

    recs = log.records()
    assert len(recs) == 3
    assert recs[0].previous_entry_hash == GENESIS_HASH
    assert recs[1].previous_entry_hash == recs[0].entry_hash
    assert recs[2].previous_entry_hash == recs[1].entry_hash
    ok, breaks = log.verify_chain()
    assert ok and not breaks


def test_verify_chain_detects_content_tampering() -> None:
    log = Annex22Log()

    @with_annex22_governance("low")
    def f(x: int) -> dict:
        return {"v": x}

    with governance_context("alice", log):
        f(1)
        f(2)
        f(3)

    assert log.verify_chain()[0]
    # Tamper with a record's output but leave its entry_hash unchanged.
    log._records[1] = dataclasses.replace(log._records[1], output={"v": 999})
    ok, breaks = log.verify_chain()
    assert not ok
    assert any("content tampered" in b for b in breaks)


# --------------------------------------------------------------------------- #
# Risk levels
# --------------------------------------------------------------------------- #
def test_medium_risk_is_auto_approved_and_output_passes_through() -> None:
    log = Annex22Log()

    @with_annex22_governance("medium", decision_type="ctd_section")
    def draft(x: str) -> dict:
        return {"section": x}

    with governance_context("alice", log):
        gov = draft("3.2.S.3.2")

    assert isinstance(gov, GovernedResult)
    assert gov.status == "approved"
    assert gov.output == {"section": "3.2.S.3.2"}
    assert gov.unwrap() == {"section": "3.2.S.3.2"}
    assert gov.record.user_id == "alice"
    assert gov.record.hitl_required is False
    assert log.is_approved(gov.record.entry_hash)


def test_low_risk_logs_and_exposes_a_deterministic_qa_sample() -> None:
    log = Annex22Log()

    @with_annex22_governance("low")
    def f(x: int) -> dict:
        return {"v": x}

    with governance_context("alice", log):
        results = [f(i) for i in range(300)]

    assert all(r.status == "logged" for r in results)
    assert all(r.output is not None for r in results)
    sample = log.qa_sample()
    # ~5% deterministic sample: a non-empty minority of the low-risk decisions.
    assert 0 < len(sample) < len(log.records())
    assert all(r.risk_level == "low" for r in sample)


def test_high_risk_blocks_until_a_human_approves() -> None:
    log = Annex22Log()

    @with_annex22_governance(
        "high", decision_type="cpca_classification", regulatory_basis="FDA Nitrosamine Rev 2"
    )
    def classify(smiles: str) -> dict:
        return {"category": 3, "ai_limit_ng_per_day": 100.0}

    with governance_context("alice", log):
        gov = classify(smiles="CN(C)N=O")

    assert gov.status == "pending"
    assert gov.needs_human_review
    assert gov.output is None
    with pytest.raises(Annex22PendingError):
        gov.unwrap()
    with pytest.raises(Annex22PendingError):
        log.released_output(gov.record.entry_hash)  # downstream is blocked
    assert gov.record in log.pending()

    review = log.submit_review(gov.record.entry_hash, reviewer_id="qa_bob", approved=True)
    assert review.hitl_approved is True
    assert review.hitl_reviewer_id == "qa_bob"
    assert log.is_approved(gov.record.entry_hash)
    assert log.released_output(gov.record.entry_hash) == {
        "category": 3,
        "ai_limit_ng_per_day": 100.0,
    }
    assert gov.record not in log.pending()
    assert log.verify_chain()[0]  # the review is appended, chain stays intact


def test_high_risk_rejected_stays_blocked() -> None:
    log = Annex22Log()

    @with_annex22_governance("high")
    def f(x: str) -> dict:
        return {"v": 1}

    with governance_context("alice", log):
        gov = f("z")

    log.submit_review(gov.record.entry_hash, reviewer_id="qa_bob", approved=False)
    assert not log.is_approved(gov.record.entry_hash)
    with pytest.raises(Annex22PendingError):
        log.released_output(gov.record.entry_hash)


def test_review_on_non_high_risk_or_double_review_raises() -> None:
    log = Annex22Log()

    @with_annex22_governance("medium")
    def med(x: str) -> dict:
        return {"v": 1}

    @with_annex22_governance("high")
    def high(x: str) -> dict:
        return {"v": 2}

    with governance_context("alice", log):
        gov_med = med("a")
        gov_high = high("b")

    with pytest.raises(Annex22Error):
        log.submit_review(gov_med.record.entry_hash, reviewer_id="bob", approved=True)

    log.submit_review(gov_high.record.entry_hash, reviewer_id="bob", approved=True)
    with pytest.raises(Annex22Error):
        log.submit_review(gov_high.record.entry_hash, reviewer_id="carol", approved=True)


# --------------------------------------------------------------------------- #
# Compliance checklist
# --------------------------------------------------------------------------- #
def test_compliance_checklist_all_true_for_a_well_formed_decision() -> None:
    log = Annex22Log()

    @with_annex22_governance("high", decision_type="m7_class", regulatory_basis="ICH M7(R2)")
    def classify(smiles: str) -> dict:
        return {
            "m7_class": "3",
            "confidence": 0.91,
            "model_name": "m7_classifier",
            "model_version": "1.0.0",
            "feature_attribution": {"structural_alert": "aromatic_amine"},
        }

    with governance_context("alice", log):
        gov = classify(smiles="c1ccccc1N")

    checklist = annex22_compliance_checklist(gov.record)
    assert checklist == {
        "intended_use_documented": True,
        "model_version_logged": True,
        "confidence_calibrated": True,
        "feature_attribution_computed": True,
        "hitl_opportunity_for_high_risk": True,
        "audit_trail_tamper_evident": True,
        "regulatory_basis_cited": True,
    }


# --------------------------------------------------------------------------- #
# Integration with the Prompt 13 deterministic router
# --------------------------------------------------------------------------- #
def test_governing_a_deterministic_routed_result_captures_provenance() -> None:
    log = Annex22Log()
    router = Router()

    @with_annex22_governance("medium", decision_type="q3d_pde")
    def assess(task: RegulatoryTask):
        return router.handle(task)

    with governance_context("alice", log):
        gov = assess(
            RegulatoryTask(TaskKind.QUANTITATIVE, "q3d_element_pde", {"element": "As", "route": "oral"})
        )

    rec = gov.record
    assert gov.status == "approved"
    assert rec.user_id == "alice"
    assert rec.confidence == 1.0  # deterministic rule-engine -> full confidence
    assert rec.model_version.startswith("sha256:")  # the rule_set_version
    assert "Q3D" in rec.regulatory_basis  # ICH Q3D(R2)
    assert rec.feature_attribution["engine"] == "deterministic"
    assert annex22_compliance_checklist(rec)["audit_trail_tamper_evident"]


def test_record_create_computes_chained_entry_hash() -> None:
    a = AIDecisionRecord.create(
        timestamp_utc=datetime(2026, 1, 1),
        user_id="u",
        decision_type="t",
        model_name="m",
        model_version="1",
        input_smiles=None,
        input_data_hash="sha256:abc",
        output={"x": 1},
        confidence=1.0,
        feature_attribution={},
        regulatory_basis="basis",
        risk_level="low",
        hitl_required=False,
        previous_entry_hash=GENESIS_HASH,
    )
    assert a.entry_hash == a.recompute_hash()
    assert a.entry_hash.startswith("sha256:")
