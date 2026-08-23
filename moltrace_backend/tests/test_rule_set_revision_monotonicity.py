"""T11 — a rule set's content cannot change without its declared revision moving.

This is the condition the desktop programme's `AHEAD` decision was ratified on
(DELTA 4 §9.3). That decision permits a desktop whose local rule sets are NEWER
than its deployment's to compute and export, stamping the adoption gap and
refusing the signature — rather than refusing outright, because refusing fires in
the normal case and produces no record.

The whole thing rests on `AHEAD` being a MEASUREMENT rather than a guess. It is
measured by comparing declared revisions, and a revision is hand-authored, so a
forgotten bump produces a false `AHEAD` — which fails OPEN under the ratified
decision and closed under refusal. §9.3 is explicit that without this test the
permit path must not ship.

Content hashes are used for the "did it change" half because they are exact and
free. They cannot be used for the ORDER half: a hash has none. That is why a
declared revision exists at all.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from moltrace.regulatory.impurities.cpca_classifier import cpca_rule_set
from moltrace.regulatory.impurities.m7_classifier import m7_rule_set
from moltrace.regulatory.impurities.q3ab_calculator import q3ab_rule_set
from moltrace.regulatory.impurities.q3c_solvents import q3c_rule_set
from moltrace.regulatory.impurities.q3d_elements import q3d_rule_set
from moltrace.regulatory.infra.versioning import rule_set_version

MANIFEST = pathlib.Path(__file__).parent / "golden" / "rule_set_revisions.json"

#: Every engine that versions itself. Membership is asserted below against the
#: real callers, so a sixth engine cannot be silently omitted.
ENGINES = {
    "m7": m7_rule_set,
    "q3ab": q3ab_rule_set,
    "q3c": q3c_rule_set,
    "q3d": q3d_rule_set,
    "cpca": cpca_rule_set,
}


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text())["engines"]


@pytest.mark.parametrize("engine", sorted(ENGINES))
def test_a_changed_rule_set_must_carry_a_changed_revision(engine: str) -> None:
    """The invariant, per engine so a failure names which one moved."""
    recorded = _manifest()[engine]
    observed = rule_set_version(ENGINES[engine]())
    assert observed == recorded["identity_hash"], (
        f"the {engine} rule set's content has changed but tests/golden/"
        f"rule_set_revisions.json still records the old hash.\n"
        f"  recorded: {recorded['identity_hash']}\n"
        f"  observed: {observed}\n"
        f"If this change is intended, bump {engine}'s semver in that file and update the hash "
        f"IN THE SAME EDIT. Updating the hash alone is the failure this test exists to prevent: "
        f"it leaves a deployment unable to tell a newer rule set from an older one."
    )


def test_the_manifest_covers_exactly_the_engines_that_version_themselves() -> None:
    """A sixth engine calling rule_set_version must not be silently unversioned."""
    import subprocess

    root = pathlib.Path(__file__).parents[1] / "src" / "moltrace" / "regulatory"
    out = subprocess.run(
        ["grep", "-rn", "_RULE_SET_VERSION = rule_set_version(", str(root)],
        capture_output=True, text=True, check=False,
    ).stdout
    callers = {line.split("/")[-1].split(".py")[0] for line in out.splitlines() if line.strip()}
    expected = {"m7_classifier", "q3ab_calculator", "q3c_solvents", "q3d_elements", "cpca_classifier"}
    assert callers == expected, (
        f"the set of self-versioning engines has changed: {callers ^ expected}. "
        f"Add it to ENGINES and to the manifest, or this test covers less than it claims."
    )
    assert set(_manifest()) == set(ENGINES)


def test_every_engine_declares_an_ORDERED_revision() -> None:
    """A hash answers 'did it change'. Only this answers 'which is newer'.

    Without it the comparison algebra has no ordering input at all, and every
    comparison degrades to UNKNOWN — which is safe, and is also the whole
    capability the AHEAD decision depends on.
    """
    for engine, entry in _manifest().items():
        parts = entry["semver"].split(".")
        assert len(parts) == 3 and all(p.isdigit() for p in parts), (
            f"{engine} has no ordered revision: {entry['semver']!r}"
        )
