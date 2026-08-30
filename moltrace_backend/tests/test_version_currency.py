"""The currency algebra: eight branches, six of which refuse.

Every version identifier the platform carries for a rule set is a content address, which has no
order. So the interesting property of this comparator is not what it decides — it is **what it
declines to decide**. A comparison that guessed would be worse than useless: it would let an
installation emit a regulated number while believing it matched a deployment it had never
actually been compared against.
"""

from __future__ import annotations

import pytest

from nmrcheck import version_currency as vc
from nmrcheck.version_currency import CurrencyState, VersionCoordinate, compare

H1 = "sha256:" + "11" * 32
H2 = "sha256:" + "22" * 32


def coord(**over) -> VersionCoordinate:
    base = dict(lineage="ich_q3c", display_name="the Q3C rule set", identity=H1, revision="1.0.0")
    base.update(over)
    return VersionCoordinate(**base)


# --------------------------------------------------------------------------------- T2
def test_identical_content_is_current() -> None:
    """§2.3 step 3."""
    decision = compare(coord(), coord())
    assert decision.state is CurrencyState.CURRENT
    assert decision.permits_new_regulated_result and decision.permits_signature
    assert decision.adoption_gap is None


def test_identical_content_is_current_even_across_differently_spelled_lineages() -> None:
    """Step 3 precedes step 4 deliberately: the bytes are the ground truth, and lineage is only
    a comparability guard. Two catalogues that name the same rule set differently still agree
    about it when the content addresses match."""
    decision = compare(coord(lineage="ich_q3c"), coord(lineage="regulatory/ich_q3c"))
    assert decision.state is CurrencyState.CURRENT


# --------------------------------------------------------------------------------- T3
def test_identical_content_at_two_revisions_is_unknown() -> None:
    """§2.3 step 3a. Identical bytes under contradictory versions means one of the two pinned
    catalogues is wrong, and nothing here can tell which — so neither is trusted."""
    decision = compare(coord(revision="1.0.0"), coord(revision="2.0.0"))
    assert decision.state is CurrencyState.UNKNOWN
    assert "two different versions" in decision.cause
    assert not decision.permits_new_regulated_result


# --------------------------------------------------------------------------------- T4
@pytest.mark.parametrize(
    "local_rev, canonical_rev",
    [(None, "1.0.0"), ("1.0.0", None), ("conformal-v1", "1.0.0"), ("1.0.0", "2024-06-r2"),
     ("v1.0.0", "1.0.0"), ("1.0", "1.0.0"), ("1.0.0.1", "1.0.0")],
)
def test_unordered_or_absent_revision_refuses_rather_than_guesses(
    local_rev: str | None, canonical_rev: str | None
) -> None:
    """§2.3 step 5 — the load-bearing test of the delta.

    Each of these is a string a permissive comparator would happily rank. ``"v1.0.0"`` sorts
    after ``"1.0.0"`` lexically; ``"1.0"`` looks like a smaller version; ``"conformal-v1"`` is
    not a version at all. Ranking any of them invents an ordering the platform never declared.
    """
    decision = compare(
        coord(identity=H1, revision=local_rev), coord(identity=H2, revision=canonical_rev)
    )
    assert decision.state is CurrencyState.UNKNOWN, f"{local_rev!r} vs {canonical_rev!r} was ranked"
    assert "no ordered revision" in decision.cause
    assert not decision.permits_new_regulated_result


def test_one_revision_over_two_contents_is_unknown() -> None:
    """§2.3 step 8, and a real failure mode rather than a theoretical one — the same shape
    ``promote_to_serving`` already refuses for models: one version pointing at two different
    sets of bytes means one of them is not what was reviewed."""
    decision = compare(coord(identity=H1), coord(identity=H2))
    assert decision.state is CurrencyState.UNKNOWN
    assert "two different contents" in decision.cause


def test_a_missing_side_is_never_treated_as_agreement() -> None:
    """§2.3 steps 1 and 2. Absence is the most tempting thing to treat as 'fine'."""
    assert compare(coord(), None).state is CurrencyState.UNKNOWN
    assert compare(None, coord()).state is CurrencyState.UNKNOWN
    assert compare(None, None).state is CurrencyState.UNKNOWN


def test_different_lineages_are_not_rankable() -> None:
    """§2.3 step 4 — what stops a Q3C revision being ranked against a Q3D one."""
    decision = compare(coord(lineage="ich_q3c", identity=H1), coord(lineage="ich_q3d", identity=H2))
    assert decision.state is CurrencyState.UNKNOWN
    assert "common line" in decision.cause


# --------------------------------------------------------------------------------- T5
def test_behind_refuses_a_new_regulated_result() -> None:
    decision = compare(coord(identity=H1, revision="1.0.0"), coord(identity=H2, revision="1.1.0"))
    assert decision.state is CurrencyState.BEHIND
    assert not decision.permits_new_regulated_result
    assert not decision.permits_signature


def test_ahead_computes_but_never_signs_and_is_never_reported_as_staleness() -> None:
    """The owner decision (§9.2): permit and stamp, gate at signature.

    ``AHEAD`` is the expected steady state — the client auto-updates on MolTrace's cadence while a
    validated deployment moves on a requalification window — so refusing it would be a scheduled
    outage rather than a control. The regulated act is the signature, and that is what stays shut.
    """
    decision = compare(coord(identity=H1, revision="2.0.0"), coord(identity=H2, revision="1.0.0"))
    assert decision.state is CurrencyState.AHEAD
    assert decision.permits_new_regulated_result, "the owner decision permits computation"
    assert not decision.permits_signature, "a result outside the adopted configuration is not signable"
    assert decision.adoption_gap, "a permitted result MUST carry the gap, or it is unattributable"
    # Distinct from staleness, in the copy a person reads — an installation that is ahead has the
    # opposite problem from one that is behind, and telling a scientist to update would be wrong.
    assert "newer" in decision.cause
    behind = compare(coord(identity=H1, revision="1.0.0"), coord(identity=H2, revision="2.0.0"))
    assert decision.cause != behind.cause


def test_the_ahead_policy_is_one_constant_and_reverses_cleanly(monkeypatch) -> None:
    """§9.4. The frequency argument rests on release cadences, which change — so flipping the
    decision must be one line, not a re-derivation of the algebra."""
    monkeypatch.setattr(vc, "AHEAD_PERMITS_COMPUTATION", False)
    decision = compare(coord(identity=H1, revision="2.0.0"), coord(identity=H2, revision="1.0.0"))
    assert decision.state is CurrencyState.AHEAD, "the STATE is a measurement and must not move"
    assert not decision.permits_new_regulated_result, "only the policy changed, and it applied"


def test_semver_precedence_not_string_or_lexical_order() -> None:
    """The comparator must order by precedence, not by the string. ``"1.10.0"`` is NEWER than
    ``"1.9.0"`` and sorts BEFORE it lexically — a string comparator reports it as behind."""
    decision = compare(coord(identity=H1, revision="1.10.0"), coord(identity=H2, revision="1.9.0"))
    assert decision.state is CurrencyState.AHEAD, "1.10.0 was ranked below 1.9.0 — lexical order"


def test_parse_revision_refuses_everything_that_is_not_a_strict_triple() -> None:
    assert vc.parse_revision("1.2.3") == (1, 2, 3)
    for bad in (None, "", "1.2", "1.2.3.4", "v1.2.3", "1.2.3-rc1", "conformal-v1", "  "):
        assert vc.parse_revision(bad) is None, f"{bad!r} was parsed as orderable"
