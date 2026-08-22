"""Is this installation's science current with the deployment's?

A desktop installation carries its own copy of the rule sets, method constants, model artifacts
and reference packs. The deployment carries the ones its quality unit has adopted. When they
differ, a regulated result computed locally is not the result the deployment would have produced,
and the difference has to be visible rather than inferred.

**Nothing in this module can order two versions by itself, and that is the point.** Every version
identifier the platform carries for a rule set is a content address — ``sha256:<hex>`` — which
answers "are these the same bytes?" and nothing more. ``sha256(A) < sha256(B)`` says nothing about
which was authored first. So ordering comes from a semver declared in source beside the content
(``_RULE_SET_SEMVER`` in each engine), pinned against its content address by
``tests/test_rule_set_revisions.py``.

**A comparison that cannot order two versions refuses; it never guesses.** Six of the eight
branches below produce ``UNKNOWN``, each naming the measure that failed.

This module is pure: no HTTP, no ORM, no clock, no randomness. That makes it cheap to test
exhaustively — it does *not* make it unable to gate anything, and nobody should claim otherwise.
A gate is built at the consumer, and ``module_access`` is the proof: it imports no ``fastapi`` and
is the entire basis of a 403.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "AHEAD_PERMITS_COMPUTATION",
    "CurrencyDecision",
    "CurrencyState",
    "VersionCoordinate",
    "compare",
    "parse_revision",
]

# --------------------------------------------------------------------------------------------
# The policy point (§9.4)
# --------------------------------------------------------------------------------------------
#: What happens when an installation carries a NEWER version than the deployment has adopted.
#:
#: ``True``  — compute and export, stamp the adoption gap on the record, refuse the SIGNATURE.
#: ``False`` — refuse the result outright, exactly as ``BEHIND`` is refused.
#:
#: One constant, consulted in one place, so reversing this decision is a one-line change with a
#: test rather than a re-derivation of the algebra below. It is deliberately *not* woven into
#: ``compare``: the frequency argument it rests on is about release cadences, and those change.
#:
#: **Owner decision, 2026-08-22: permit and stamp.** ``AHEAD`` is not a rare race — it is the
#: expected steady state. A desktop auto-updates on MolTrace's release schedule; a validated
#: deployment upgrades only in a requalification window, weeks to a quarter out. So the fast side
#: is the client and the slow side is the server, and every content release would otherwise put
#: every installation into refusal until qualification cleared. A control that fires in the normal
#: case is not a control, it is a scheduled outage.
#:
#: The regulator's concern is not that a newer number is wrong; it is that the number was produced
#: outside the adopted configuration. **A refusal produces no record; a stamp produces an
#: attributable, contemporaneous one**, which is what ALCOA+ asks for — and Part 11 bites at
#: signature, so that is where the hard gate belongs.
#:
#: This permits where refusing would deny, so it fails OPEN on a forgotten version bump. It was
#: adopted on the explicit condition that ``tests/test_rule_set_revisions.py`` exists and catches
#: that. Removing that test withdraws the condition this was granted under.
AHEAD_PERMITS_COMPUTATION = True

_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class CurrencyState(StrEnum):
    """The four answers. Only ``CURRENT`` and ``AHEAD`` can permit a new regulated result."""

    CURRENT = "current"
    BEHIND = "behind"
    AHEAD = "ahead"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class VersionCoordinate:
    """One comparable position for one artifact.

    ``identity`` and ``revision`` answer different questions and neither substitutes for the
    other: identity is an equality test over bytes, revision is the ordering. ``lineage`` is the
    namespace that makes two coordinates comparable at all — it is what stops a Q3C revision
    being ranked against a Q3D one, or a rule set against a model.
    """

    #: Ordering namespace. Two coordinates are comparable only when these are equal.
    lineage: str
    #: Human copy. Never an endpoint path, HTTP verb, status code or wire field name.
    display_name: str
    #: ``"sha256:<hex>"`` content address, or ``None`` when this side declares none.
    identity: str | None = None
    #: Declared ordered version, or ``None`` when absent or unparseable. ``None`` means
    #: unorderable, which means refuse.
    revision: str | None = None
    #: What sort of artifact this is, for display grouping only. Never compared.
    kind: str = "rule_set"


@dataclass(frozen=True, slots=True)
class CurrencyDecision:
    """The verdict, and what it permits.

    ``cause`` names the measure that failed, per the standing rule that a rejection names its
    cause. It is operator/scientist copy and carries no wire vocabulary.
    """

    state: CurrencyState
    cause: str
    #: May a NEW regulated result be emitted? False for ``BEHIND`` and ``UNKNOWN`` always, and
    #: for ``AHEAD`` only when the policy above is off.
    permits_new_regulated_result: bool
    #: May that result be e-signed? ``AHEAD`` computes but never signs — the adoption gap must be
    #: closed before a regulated record is created.
    permits_signature: bool
    #: Stamped onto the record when the result is permitted despite a gap. ``None`` when current.
    adoption_gap: str | None = None

    @property
    def is_current(self) -> bool:
        return self.state is CurrencyState.CURRENT


def parse_revision(revision: str | None) -> tuple[int, int, int] | None:
    """A strict ``major.minor.patch`` triple, or ``None`` — which means *unorderable*.

    Deliberately strict. ``ModelEntry.semantic_version`` is a free, unvalidated string, and a
    permissive parser would invent an ordering for something like ``"conformal-v1"`` or
    ``"2024-06-r2"``. Refusing to parse is the correct answer for those: the caller turns it into
    ``UNKNOWN`` and the result is refused rather than ranked on a guess.

    Compared as a tuple, by semver precedence, rather than packed into one integer. A packing base
    would introduce an overflow at which versions silently reorder; a tuple has no such bound and
    therefore no bound to get wrong. (Measured across the tree: the largest component present in
    any ``semantic_version`` is 3.)
    """

    if not revision:
        return None
    match = _SEMVER_RE.match(revision.strip())
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _decide(
    state: CurrencyState, cause: str, *, gap: str | None = None
) -> CurrencyDecision:
    """Apply the policy in ONE place, so no branch can disagree with another about it."""

    if state is CurrencyState.CURRENT:
        return CurrencyDecision(state, cause, True, True)
    if state is CurrencyState.AHEAD and AHEAD_PERMITS_COMPUTATION:
        # Computes and exports, carrying the gap on the record; never signable, because that is
        # the step that creates the regulated record.
        return CurrencyDecision(state, cause, True, False, adoption_gap=gap or cause)
    return CurrencyDecision(state, cause, False, False, adoption_gap=gap or cause)


def compare(
    local: VersionCoordinate | None, canonical: VersionCoordinate | None
) -> CurrencyDecision:
    """Order one installation's artifact against the deployment's, or refuse.

    Evaluated in exactly this order; the order is load-bearing and the notes say why.
    """

    name = (canonical or local).display_name if (canonical or local) else "this artifact"

    # 1-2. One side asserted nothing. Absence is never treated as agreement.
    if canonical is None:
        return _decide(
            CurrencyState.UNKNOWN, f"the workspace asserted no version for {name}"
        )
    if local is None:
        return _decide(CurrencyState.UNKNOWN, f"this installation carries no {name}")

    # 3. Byte-identical content is current even when the two sides spell `lineage` differently —
    #    the bytes are the ground truth and lineage is only a comparability guard, so this
    #    precedes the lineage check deliberately.
    if local.identity and canonical.identity and local.identity == canonical.identity:
        if local.revision != canonical.revision:
            # Identical bytes carrying contradictory versions means one of the two pinned
            # catalogues is wrong, and there is no way to tell which — so neither is trusted.
            return _decide(
                CurrencyState.UNKNOWN,
                f"{name} is identical on both sides but is declared at two different versions",
            )
        return _decide(CurrencyState.CURRENT, f"{name} matches the workspace")

    # 4. Different lines are not rankable against each other at all.
    if local.lineage != canonical.lineage:
        return _decide(
            CurrencyState.UNKNOWN, f"the two versions of {name} are not on a common line"
        )

    # 5. No ordering input on one side.
    local_revision = parse_revision(local.revision)
    canonical_revision = parse_revision(canonical.revision)
    if local_revision is None or canonical_revision is None:
        return _decide(
            CurrencyState.UNKNOWN,
            f"one of the two versions of {name} declares no ordered revision",
        )

    # 6-7. The orderable cases.
    if local_revision < canonical_revision:
        return _decide(
            CurrencyState.BEHIND,
            f"this installation's {name} is older than the version this workspace has adopted",
        )
    if local_revision > canonical_revision:
        return _decide(
            CurrencyState.AHEAD,
            f"this installation carries a newer {name} than this workspace has adopted",
            gap=(
                f"computed with {name} {local.revision}, which this workspace has not adopted "
                f"(it uses {canonical.revision})"
            ),
        )

    # 8. Equal revisions over different content: one version, two different sets of bytes. The
    #    same thing `promote_to_serving` already refuses for models — one of the two is not what
    #    was reviewed, and nothing here can tell which.
    return _decide(
        CurrencyState.UNKNOWN,
        f"one version of {name} is declared over two different contents",
    )
