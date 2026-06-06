"""Prompt 12 — tests for the audit trail + GxP controls (21 CFR Part 11 support).

Exercises the cryptographic hash chain + HMAC signatures (tamper detection), the
``with_audit`` decorator (input/result hashing, parameter + model-checksum
capture, failure recording, user attribution), electronic signatures designed per
21 CFR Part 11.50/.70, append-only JSONL persistence, the 7-year retention floor,
and the deterministic archival report — including a guard that no user-facing
string claims the product is itself "21 CFR Part 11 compliant".
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from moltrace.spectroscopy.audit import (
    AuditConfigurationError,
    AuditContextError,
    AuditEntry,
    ChainIntegrityError,
    InMemoryAuditLog,
    JsonlAuditLog,
    ModelRegistry,
    Operation,
    PdfExportUnavailable,
    RetentionPolicy,
    SignatureMeaning,
    assert_chain_integrity,
    audit_context,
    audited,
    compute_signature,
    configure_audit,
    entry_hash,
    render_audit_report_html,
    render_audit_report_text,
    sign_record,
    static_key,
    verify_chain,
    verify_signature,
    with_audit,
)
from moltrace.spectroscopy.audit import trail as A

_KEY = b"unit-test-secret"


class _Clock:
    """Deterministic, monotonically increasing UTC clock."""

    def __init__(self) -> None:
        self._base = datetime(2026, 1, 1, tzinfo=UTC)
        self._n = 0

    def __call__(self) -> datetime:
        value = self._base + timedelta(seconds=self._n)
        self._n += 1
        return value


@pytest.fixture(autouse=True)
def _isolate():
    A.reset_default_recorder()
    A._warned.clear()
    yield
    A.reset_default_recorder()


@pytest.fixture
def recorder():
    return configure_audit(
        InMemoryAuditLog(),
        key_provider=static_key(_KEY),
        clock=_Clock(),
        software_version="nmrcheck/test",
        model_registry=ModelRegistry(),
    )


def _make_log(entries) -> InMemoryAuditLog:
    log = InMemoryAuditLog()
    for entry in entries:
        log.append(entry)
    return log


# --------------------------------------------------------------------------- #
# Hash chain + signing
# --------------------------------------------------------------------------- #
def test_record_builds_signed_chained_entry(recorder) -> None:
    e1 = recorder.record(
        operation=Operation.PEAK_PICK,
        user_id="alice",
        input_obj=np.arange(10.0),
        result_obj={"n_peaks": 3},
        parameters={"level": 2},
    )
    assert isinstance(e1, AuditEntry)
    assert e1.previous_entry_hash == A.GENESIS_HASH
    assert len(e1.input_hash) == 64 and len(e1.result_hash) == 64
    assert e1.parameters == {"level": 2}
    assert e1.software_version == "nmrcheck/test"

    e2 = recorder.record(
        operation=Operation.INTEGRATE,
        user_id="alice",
        input_obj=np.arange(10.0),
        result_obj={"value": 1.0},
        parameters={},
    )
    assert e2.previous_entry_hash == entry_hash(e1)

    report = verify_chain(recorder.log, key=_KEY)
    assert report.ok and report.entries_checked == 2 and report.signature_verified


def test_clean_chain_verifies_with_and_without_key(recorder) -> None:
    for i in range(3):
        recorder.record(operation="op", user_id="u", input_obj=i, result_obj=i, parameters={})
    assert verify_chain(recorder.log).ok  # keyless structural check
    assert verify_chain(recorder.log, key=_KEY).ok  # keyed authenticity check


def test_content_tamper_breaks_signature_and_chain(recorder) -> None:
    recorder.record(operation="a", user_id="u", input_obj=1, result_obj=1, parameters={})
    recorder.record(operation="b", user_id="u", input_obj=2, result_obj=2, parameters={})
    entries = list(recorder.log)
    tampered = _make_log([replace(entries[0], user_id="mallory"), entries[1]])

    keyed = verify_chain(tampered, key=_KEY)
    assert not keyed.ok
    assert "signature" in {b.reason for b in keyed.breaks}  # HMAC catches the edit

    keyless = verify_chain(tampered)
    assert not keyless.ok
    assert any(b.reason == "chain_link" for b in keyless.breaks)  # downstream link broke


def test_deletion_and_reorder_break_chain(recorder) -> None:
    for i in range(3):
        recorder.record(operation="op", user_id="u", input_obj=i, result_obj=i, parameters={})
    entries = list(recorder.log)

    deleted = _make_log([entries[0], entries[2]])  # drop the middle entry
    assert any(b.reason == "chain_link" for b in verify_chain(deleted).breaks)

    reordered = _make_log([entries[0], entries[2], entries[1]])
    assert not verify_chain(reordered).ok


def test_assert_chain_integrity_raises_on_tamper(recorder) -> None:
    recorder.record(operation="op", user_id="u", input_obj=1, result_obj=1, parameters={})
    assert assert_chain_integrity(recorder.log, key=_KEY).ok

    entries = list(recorder.log)
    bad = _make_log([replace(entries[0], operation="hacked")])
    with pytest.raises(ChainIntegrityError):
        assert_chain_integrity(bad, key=_KEY)


# --------------------------------------------------------------------------- #
# Content hashing
# --------------------------------------------------------------------------- #
def test_content_hash_deterministic_and_sensitive() -> None:
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([1.0, 2.0, 3.0])
    c = np.array([1.0, 2.0, 3.5])
    assert A._content_sha256(a) == A._content_sha256(b)
    assert A._content_sha256(a) != A._content_sha256(c)
    # mapping key order does not change the digest
    assert A._content_sha256({"x": 1, "y": 2}) == A._content_sha256({"y": 2, "x": 1})


# --------------------------------------------------------------------------- #
# with_audit decorator
# --------------------------------------------------------------------------- #
def test_with_audit_wraps_and_records(recorder) -> None:
    @with_audit(Operation.INTEGRATE, data_params=("spectrum",))
    def integrate(spectrum, *, method="edited_sum"):
        return {"value": float(spectrum.sum())}

    spec = np.array([1.0, 2.0, 3.0])
    with audit_context("bob"):
        out = integrate(spec, method="sum")

    assert out == {"value": 6.0}
    entries = list(recorder.log)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.operation == "integrate" and entry.user_id == "bob"
    assert entry.parameters == {"method": "sum"}  # spectrum excluded via data_params
    assert entry.input_hash == A._content_sha256((spec,))
    assert verify_chain(recorder.log, key=_KEY).ok


def test_with_audit_passthrough_without_recorder() -> None:
    A.reset_default_recorder()

    @with_audit("peak_pick")
    def doubler(x):
        return x * 2

    with pytest.warns(RuntimeWarning):
        assert doubler(21) == 42  # runs un-audited rather than failing


def test_with_audit_requires_authenticated_user(recorder) -> None:
    @with_audit("peak_pick")
    def noop(x):
        return x

    with pytest.raises(AuditContextError):
        noop(1)  # no audit_context → not attributable → rejected


def test_with_audit_records_failures_then_reraises(recorder) -> None:
    @with_audit("verify_structure")
    def boom(x):
        raise ValueError("nope")

    with audit_context("carol"), pytest.raises(ValueError):
        boom(5)

    entries = list(recorder.log)
    assert len(entries) == 1
    assert entries[0].parameters.get("audit_event") == "operation_error"
    assert verify_chain(recorder.log, key=_KEY).ok


def test_audited_programmatic_form(recorder) -> None:
    def raw(x):
        return x + 1

    wrapped = audited(raw, Operation.INTEGRATE)
    with audit_context("u"):
        assert wrapped(1) == 2
    assert wrapped.__audited_operation__ == "integrate"
    assert list(recorder.log)[0].operation == "integrate"


# --------------------------------------------------------------------------- #
# Model-weight checksum capture
# --------------------------------------------------------------------------- #
def test_model_versions_captured_in_entry(recorder) -> None:
    recorder.model_registry.register("nmrnet:13C", "abc123")
    recorder.model_registry.register("jtfnet", "def456")

    @with_audit(Operation.PREDICT_SHIFTS)
    def predict(smiles):
        return [1, 2, 3]

    with audit_context("dave"):
        predict("CCO")

    entry = list(recorder.log)[0]
    assert entry.model_versions == {"jtfnet": "def456", "nmrnet:13C": "abc123"}


def test_register_model_weights_hashes_file(tmp_path) -> None:
    reg = ModelRegistry()
    weights = tmp_path / "model.pt"
    weights.write_bytes(b"weight-bytes")
    digest = reg.register_weights("jtfnet", weights)
    assert digest == hashlib.sha256(b"weight-bytes").hexdigest()
    assert reg.snapshot() == {"jtfnet": digest}
    assert reg.register_weights("jtfnet", weights) == digest  # mtime/size cache hit


# --------------------------------------------------------------------------- #
# Electronic signatures (21 CFR Part 11.50 / 11.70)
# --------------------------------------------------------------------------- #
def test_signature_manifestation_carries_name_meaning_time() -> None:
    sig = sign_record(
        "a" * 64,
        signer_id="jdoe",
        signer_name="Jane Doe",
        meaning=SignatureMeaning.APPROVAL,
        key=_KEY,
        signed_at=datetime(2026, 6, 6, 9, 30, tzinfo=UTC),
    )
    # §11.50(a): printed name, meaning, and date/time of signing.
    assert "Jane Doe" in sig.manifestation
    assert "APPROVAL" in sig.manifestation
    assert "2026-06-06" in sig.manifestation
    assert verify_signature(sig, key=_KEY)
    assert not verify_signature(sig, key=b"wrong-key")


def test_signature_is_linked_to_its_record_11_70() -> None:
    sig = sign_record(
        "a" * 64, signer_id="u", signer_name="U", meaning="review", key=_KEY
    )
    # Transferring the signature to a different record (§11.70) must not verify.
    forged = replace(sig, record_hash="b" * 64)
    assert not verify_signature(forged, key=_KEY)


def test_signature_meaning_values() -> None:
    assert {m.value for m in SignatureMeaning} == {
        "authorship",
        "review",
        "approval",
        "responsibility",
    }


# --------------------------------------------------------------------------- #
# Retention policy
# --------------------------------------------------------------------------- #
def _entry_at(ts: datetime) -> AuditEntry:
    return AuditEntry(ts, "u", "op", "h", {}, "r", "v", {}, A.GENESIS_HASH, "s")


def test_retention_policy_default_seven_years() -> None:
    policy = RetentionPolicy()
    assert policy.minimum_years == 7
    entry = _entry_at(datetime(2020, 1, 15, tzinfo=UTC))
    assert policy.retention_floor(entry) == datetime(2027, 1, 15, tzinfo=UTC)
    assert not policy.is_destroyable(entry, datetime(2026, 1, 1, tzinfo=UTC))
    assert policy.is_destroyable(entry, datetime(2027, 1, 16, tzinfo=UTC))


def test_retention_handles_leap_day() -> None:
    entry = _entry_at(datetime(2020, 2, 29, tzinfo=UTC))
    assert RetentionPolicy().retention_floor(entry) == datetime(2027, 2, 28, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# Serialisation + durable JSONL persistence
# --------------------------------------------------------------------------- #
def test_entry_roundtrip_preserves_signature(recorder) -> None:
    entry = recorder.record(
        operation="op",
        user_id="u",
        input_obj=np.arange(5.0),
        result_obj={"x": [1, 2, 3]},
        parameters={"a": 1, "b": 0.97},
    )
    restored = A.entry_from_dict(A.entry_to_dict(entry))
    assert compute_signature(restored, _KEY) == entry.signature
    assert entry_hash(restored) == entry_hash(entry)


def test_jsonl_log_persists_and_verifies_across_reopen(tmp_path) -> None:
    path = tmp_path / "trail.jsonl"
    log = JsonlAuditLog(path)
    configure_audit(
        log, key_provider=static_key(_KEY), clock=_Clock(), model_registry=ModelRegistry()
    )

    @with_audit("op")
    def step(x):
        return x

    with audit_context("u"):
        step(1)
        step(2)
        step(3)

    reopened = JsonlAuditLog(path)
    assert len(reopened) == 3
    assert reopened.latest_entry_hash() == log.latest_entry_hash()
    assert verify_chain(reopened, key=_KEY).ok


# --------------------------------------------------------------------------- #
# Key providers
# --------------------------------------------------------------------------- #
def test_static_key_provider() -> None:
    assert static_key("secret")() == b"secret"
    with pytest.raises(AuditConfigurationError):
        static_key("")


def test_env_key_missing_raises(monkeypatch) -> None:
    monkeypatch.delenv(A.HMAC_KEY_ENV, raising=False)
    with pytest.raises(AuditConfigurationError):
        A._env_key()


def test_env_key_hex_prefix(monkeypatch) -> None:
    monkeypatch.setenv(A.HMAC_KEY_ENV, "hex:00ff10")
    assert A._env_key() == bytes([0x00, 0xFF, 0x10])


# --------------------------------------------------------------------------- #
# Archival report + the "no compliance claim" guard
# --------------------------------------------------------------------------- #
def test_report_is_deterministic_and_frames_as_support(recorder) -> None:
    @with_audit("peak_pick")
    def step(x):
        return x

    with audit_context("u"):
        step(1)
        step(2)

    when = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)
    r1 = render_audit_report_text(recorder.log, key=_KEY, generated_at=when)
    r2 = render_audit_report_text(recorder.log, key=_KEY, generated_at=when)
    assert r1 == r2
    assert "VERIFIED" in r1
    low = r1.lower()
    # The product must NOT be described as itself compliant …
    assert "21 cfr part 11 compliant" not in low
    # … but the report must frame the controls as SUPPORTING the rule.
    assert "support" in low and "21 cfr part 11" in low
    assert "responsibility" in low  # customer-responsibility disclaimer present


def test_report_includes_signature_manifestation(recorder) -> None:
    @with_audit("verify_structure")
    def step(x):
        return x

    with audit_context("u"):
        step(7)

    record_hash = entry_hash(list(recorder.log)[0])
    sig = sign_record(
        record_hash,
        signer_id="rev",
        signer_name="Rev Iewer",
        meaning="approval",
        key=_KEY,
        signed_at=datetime(2026, 6, 6, tzinfo=UTC),
    )
    text = render_audit_report_text(
        recorder.log, key=_KEY, signatures=[sig], generated_at=datetime(2026, 6, 6, tzinfo=UTC)
    )
    assert "Rev Iewer" in text and "APPROVAL" in text


def test_html_report_and_no_compliance_claim(recorder) -> None:
    @with_audit("op")
    def step(x):
        return x

    with audit_context("u"):
        step(1)

    html = render_audit_report_html(
        recorder.log, key=_KEY, generated_at=datetime(2026, 6, 6, tzinfo=UTC)
    )
    assert "<html" in html and "<pre>" in html
    assert "21 cfr part 11 compliant" not in html.lower()


def test_pdf_export_optional_dependency(recorder, tmp_path) -> None:
    @with_audit("op")
    def step(x):
        return x

    with audit_context("u"):
        step(1)

    out = tmp_path / "audit.pdf"
    try:
        import reportlab  # noqa: F401

        have_reportlab = True
    except Exception:
        have_reportlab = False

    if have_reportlab:  # pragma: no cover - depends on optional dep presence
        assert A.export_pdfa(recorder.log, out, key=_KEY).exists()
    else:
        with pytest.raises(PdfExportUnavailable):
            A.export_pdfa(recorder.log, out, key=_KEY)


# --------------------------------------------------------------------------- #
# Operation vocabulary (rollout manifest for Prompts 1-11)
# --------------------------------------------------------------------------- #
def test_operation_vocabulary_covers_prompt_surfaces() -> None:
    assert Operation.PEAK_PICK == "peak_pick"
    for name in ("predict_shifts", "qnmr_purity", "classify_peaks", "nus_reconstruct"):
        assert name in A.OPERATION_VOCABULARY
