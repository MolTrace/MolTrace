"""§7.8 — the operation offline-policy table.

"Classify every operation as offline-view, offline-draft, offline-compute,
sync-required, or online-only, in one policy table that is the single source for
the interface, the adapter, and the tests." And: "The policy table is the only
place an operation's offline class is defined, asserted by test."

The failure this prevents is drift: the interface deciding an operation is
available offline, the adapter deciding it is not, and the tests asserting a
third thing. One table, consulted by all three.
"""

from __future__ import annotations

import pytest

from nmrcheck.offline_policy import (
    OFFLINE_CLASSES,
    SERVED_LOCALLY,
    UnclassifiedOperation,
    is_served_locally,
    offline_class,
)


def test_the_five_classes_are_exactly_the_five_the_spec_names() -> None:
    assert OFFLINE_CLASSES == (
        "offline-view",
        "offline-draft",
        "offline-compute",
        "sync-required",
        "online-only",
    )


def test_a_classified_operation_returns_its_class() -> None:
    assert offline_class("system.health") in OFFLINE_CLASSES


def test_an_UNCLASSIFIED_operation_raises_rather_than_defaulting() -> None:
    """Fail closed and loud. A default here would silently grant an unreviewed
    operation whatever the default happens to be, and 'online-only' as a default
    is just as wrong as 'offline-compute' — it would hide the gap either way."""
    with pytest.raises(UnclassifiedOperation):
        offline_class("something.nobody.classified")


def test_only_offline_capable_classes_are_served_locally() -> None:
    assert SERVED_LOCALLY == ("offline-view", "offline-draft", "offline-compute")


@pytest.mark.parametrize("cls", ["sync-required", "online-only"])
def test_the_two_online_classes_are_never_served_locally(cls: str) -> None:
    assert cls not in SERVED_LOCALLY


def test_is_served_locally_refuses_an_unclassified_operation() -> None:
    with pytest.raises(UnclassifiedOperation):
        is_served_locally("something.nobody.classified")


def test_every_entry_in_the_table_has_a_valid_class() -> None:
    from nmrcheck.offline_policy import POLICY

    for op, cls in POLICY.items():
        assert cls in OFFLINE_CLASSES, f"{op} has an unreviewed class: {cls}"


def test_the_table_is_the_only_place_a_class_is_defined() -> None:
    """§7.8's "asserted by test", made literal.

    Any other module that hard-codes one of the class names is a second source of
    truth, and the drift this table exists to prevent starts there.
    """
    import pathlib

    src_root = pathlib.Path(__file__).resolve().parents[1] / "src"
    offenders: list[str] = []
    for path in src_root.rglob("*.py"):
        if path.name == "offline_policy.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for cls in OFFLINE_CLASSES:
            if f'"{cls}"' in text or f"'{cls}'" in text:
                offenders.append(f"{path.relative_to(src_root)} hard-codes {cls!r}")
    assert not offenders, "the offline class vocabulary is defined in more than one place:\n" + "\n".join(offenders)


def test_a_reason_is_recorded_for_every_operation_that_is_NOT_served_locally() -> None:
    """An operation withheld from offline use is a product decision, and §7.8
    wants the table to be where it is written down — not a comment somewhere."""
    from nmrcheck.offline_policy import POLICY, WITHHELD_REASONS

    for op, cls in POLICY.items():
        if cls not in SERVED_LOCALLY:
            assert op in WITHHELD_REASONS, f"{op} is withheld from offline use with no reason recorded"
            assert len(WITHHELD_REASONS[op]) > 15, f"{op}'s reason is not a sentence"
