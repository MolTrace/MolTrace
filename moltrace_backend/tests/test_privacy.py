"""DSAR + right-to-erasure planner (Security Prompt 23).

The important tests here are the HONESTY invariants: pseudonymisation must never be
reported as erasure, the immutable ledger must never be marked erasable, and a legal
hold must veto destruction everywhere.
"""

from __future__ import annotations

from datetime import UTC, datetime

from nmrcheck import privacy

_T0 = datetime(2026, 6, 26, 9, 0, 0, tzinfo=UTC)


def _by_store(entries):
    return {e.store: e for e in entries}


# --------------------------------------------------------------------------- data map


def test_data_map_entries_are_well_formed():
    assert privacy.DATA_MAP, "the personal-data map must not be empty"
    for entry in privacy.DATA_MAP:
        assert entry.store and entry.basis, f"{entry.store}: missing store/basis"
        assert entry.data_classes, f"{entry.store}: no data classes"
        assert entry.disposition in (
            "erase",
            "pseudonymise_restrict",
            "retain_legal_obligation",
            "immutable_ledger",
        )


def test_erasable_and_still_personal_are_mutually_exclusive():
    # The core honesty invariant: nothing can be both destroyed and still personal data.
    for entry in privacy.DATA_MAP:
        assert not (entry.erasable and entry.still_personal_data), entry.store


def test_audit_chain_and_bound_esignatures_are_immutable_never_erasable():
    entries = _by_store(privacy.DATA_MAP)
    ledger = entries["audit_events / audit_checkpoints / audit_chain_head"]
    esign = entries["electronic_signature_records (content-bound)"]
    for entry in (ledger, esign):
        assert entry.disposition == "immutable_ledger"
        assert entry.still_personal_data is True
        assert entry.erasable is False


def test_pilot_signoff_is_not_claimed_immutable():
    # Regression: pilot_signoff_records carry NO digest/chain columns and their linked
    # signature is unbound, so an edit is undetectable — never present them as
    # tamper-evident. They are retained by policy, not immutable by construction.
    entry = _by_store(privacy.DATA_MAP)["pilot_signoff_records + legacy unbound signature rows"]
    assert entry.disposition == "retain_legal_obligation"
    assert entry.disposition != "immutable_ledger"
    assert "not" in entry.note.lower()


def test_known_stores_pin_their_expected_disposition():
    # Non-tautological: pin the dispositions that carry legal meaning, so a future edit
    # that (say) marks the ledger erasable fails loudly.
    expected = {
        "audit_events / audit_checkpoints / audit_chain_head": "immutable_ledger",
        "electronic_signature_records (content-bound)": "immutable_ledger",
        "security_events": "pseudonymise_restrict",
        "users": "pseudonymise_restrict",
        "raw_archives / the write-once raw-data vault": "retain_legal_obligation",
        "mfa_* (TOTP / WebAuthn credentials + challenges / recovery codes)": "erase",
    }
    actual = {e.store: e.disposition for e in privacy.DATA_MAP}
    for store, disposition in expected.items():
        assert actual[store] == disposition, f"{store} changed disposition"


def test_unknown_disposition_is_rejected():
    import pytest

    with pytest.raises(ValueError):
        privacy.StoreDisposition(
            store="x", data_classes=("y",), disposition="deleted", basis="b"
        )


def test_security_events_are_pseudonymisable_not_immutable():
    # security_events is a separate table with no hash chain over it, so the identity
    # columns CAN be cleared — but the row survives, so it stays personal data.
    entry = _by_store(privacy.DATA_MAP)["security_events"]
    assert entry.disposition == "pseudonymise_restrict"
    assert entry.still_personal_data is True
    assert entry.erasable is False


def test_credential_material_is_genuinely_erasable():
    entry = _by_store(privacy.DATA_MAP)[
        "session_tokens / session_families / refresh_tokens / user_action_tokens"
    ]
    assert entry.erasable is True and entry.still_personal_data is False


# --------------------------------------------------------------------------- erasure plan


def test_erasure_plan_reports_pseudonymisation_as_retained_not_erased():
    plan = privacy.erasure_plan("subject@acme.com", now=_T0)
    privacy.assert_no_erasure_overclaim(plan)
    summary = plan.summary()
    # The summary must say plainly that pseudonymised records remain personal data.
    assert "REMAIN PERSONAL DATA" in summary
    assert "pseudonymisation, not erasure" in summary
    # Every pseudonymised/retained/immutable store is reported under "restricted".
    assert all(d.still_personal_data for d in plan.restricted)
    assert all(d.erasable for d in plan.erasable)


def test_legal_hold_suspends_records_but_not_credential_material_by_default():
    # Art. 17(3) applies only "to the extent necessary" — a hold must NOT blanket-sweep
    # authenticator secrets or push endpoints, which are never necessary to defend a claim.
    plan = privacy.erasure_plan("subject@acme.com", legal_hold=True, now=_T0)
    assert "LEGAL HOLD" in plan.summary()
    held = _by_store(plan.dispositions)
    assert held["security_events"].disposition == "retain_legal_obligation"  # evidentiary
    mfa = held["mfa_* (TOTP / WebAuthn credentials + challenges / recovery codes)"]
    assert mfa.disposition == "erase", "a hold must not sweep in authenticator secrets"


def test_legal_hold_can_be_widened_to_named_stores():
    store = "mfa_* (TOTP / WebAuthn credentials + challenges / recovery codes)"
    plan = privacy.erasure_plan(
        "s@acme.com", legal_hold=True, hold_covers=(store,), now=_T0
    )
    assert _by_store(plan.dispositions)[store].disposition == "retain_legal_obligation"


def test_legal_hold_preserves_the_original_note():
    plan = privacy.erasure_plan("s@acme.com", legal_hold=True, now=_T0)
    held = _by_store(plan.dispositions)[
        "controlled_records (locked / under a retention policy or legal hold)"
    ]
    # The executable/context note from the base map must survive the hold rewrite.
    assert "Absent the hold" in held.note and "ALCOA+" in held.note


def test_legal_hold_does_not_downgrade_the_immutable_ledger():
    plan = privacy.erasure_plan("s@acme.com", legal_hold=True, now=_T0)
    ledger = _by_store(plan.dispositions)["audit_events / audit_checkpoints / audit_chain_head"]
    assert ledger.disposition == "immutable_ledger"  # still immutable, not merely "retained"


def test_erasure_plan_without_hold_keeps_original_dispositions():
    plan = privacy.erasure_plan("s@acme.com", now=_T0)
    # Compare per-entry, not as sets — a dropped or reordered store must fail.
    assert [(d.store, d.disposition) for d in plan.dispositions] == [
        (d.store, d.disposition) for d in privacy.DATA_MAP
    ]


def test_summary_counts_account_for_every_store():
    plan = privacy.erasure_plan("s@acme.com", now=_T0)
    counts = {
        d: sum(1 for e in plan.dispositions if e.disposition == d)
        for d in ("erase", "pseudonymise_restrict", "retain_legal_obligation", "immutable_ledger")
    }
    assert sum(counts.values()) == len(plan.dispositions)


# --------------------------------------------------------------------------- access report


def test_access_report_lists_even_non_exportable_stores():
    report = privacy.access_report("subject@acme.com", now=_T0)
    stores = {e.store for e in report.stores}
    # The controller must be told what EXISTS, including what can't be erased/exported.
    assert "audit_events / audit_checkpoints / audit_chain_head" in stores
    assert report.controller_facts and report.limits
    # The processor-assists-only limit must be stated.
    assert any("processor" in limit.lower() for limit in report.limits)


def test_access_report_states_automated_decision_position():
    report = privacy.access_report("s@acme.com", now=_T0)
    assert any("Automated decision-making" in fact for fact in report.controller_facts)


# --------------------------------------------------------------------------- deadlines


def test_response_deadline_uses_calendar_months():
    deadline = privacy.response_deadline(_T0)  # 2026-06-26
    assert deadline.due_at == datetime(2026, 7, 26, 9, 0, tzinfo=UTC)
    # The extension must be NOTIFIED within the first month (same instant)...
    assert deadline.extension_notice_due_at == deadline.due_at
    # ...and buys two further months (three total).
    assert deadline.extended_due_at == datetime(2026, 9, 26, 9, 0, tzinfo=UTC)
    assert "without undue delay" in deadline.note


def test_response_deadline_clamps_short_months():
    # Regression: fixed 30-day arithmetic computes a LATE deadline. GDPR periods run in
    # calendar months (Reg. 1182/71), so 31 Jan + 1 month = 28 Feb, not 2 Mar.
    received = datetime(2026, 1, 31, 12, 0, tzinfo=UTC)
    deadline = privacy.response_deadline(received)
    assert deadline.due_at == datetime(2026, 2, 28, 12, 0, tzinfo=UTC)
    assert deadline.extended_due_at == datetime(2026, 4, 30, 12, 0, tzinfo=UTC)


def test_response_deadline_handles_year_rollover():
    received = datetime(2026, 11, 30, 8, 0, tzinfo=UTC)
    deadline = privacy.response_deadline(received)
    assert deadline.due_at == datetime(2026, 12, 30, 8, 0, tzinfo=UTC)
    assert deadline.extended_due_at == datetime(2027, 2, 28, 8, 0, tzinfo=UTC)


def test_response_deadline_coerces_naive_datetime():
    deadline = privacy.response_deadline(datetime(2026, 6, 26, 9, 0, 0))
    assert deadline.received_at.tzinfo is not None


# --------------------------------------------------------------------------- rendering


def test_render_data_map_round_trips_every_entry():
    rendered = privacy.render_data_map()
    assert len(rendered) == len(privacy.DATA_MAP)
    for row, entry in zip(rendered, privacy.DATA_MAP, strict=True):
        assert row.store == entry.store
        assert row.still_personal_data == entry.still_personal_data
