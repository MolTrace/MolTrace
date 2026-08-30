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
    # Matches the artifact form the engines now use. They used to call `rule_set_version()`
    # directly, which returned the bare content address and discarded the ordered version with
    # it; each now builds a `RegulatoryArtifact` so identity and semver are computed together
    # and cannot drift. Discovery has to follow that, or this test quietly measures nothing —
    # which is exactly what it did for one commit.
    out = subprocess.run(
        ["grep", "-rn", "_RULE_SET_ARTIFACT = artifact_for(", str(root)],
        capture_output=True, text=True, check=False,
    ).stdout
    callers = {line.split("/")[-1].split(".py")[0] for line in out.splitlines() if line.strip()}
    expected = {"m7_classifier", "q3ab_calculator", "q3c_solvents", "q3d_elements", "cpca_classifier"}
    assert callers == expected, (
        f"the set of self-versioning engines has changed: {callers ^ expected}. "
        f"Add it to ENGINES and to the manifest, or this test covers less than it claims."
    )
    # The manifest also pins the built-in method-constant set, which is not a rule engine but
    # carries the identical invariant and is enforced by the same file below. One manifest for
    # one idea: a second would be the duplication this codebase keeps paying for.
    assert set(_manifest()) == set(ENGINES) | {"supplier_defaults"}


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


# --------------------------------------------------------------------------------------------
# The built-in method constants get the same guarantee, and need it more
# --------------------------------------------------------------------------------------------
def test_the_method_constant_set_carries_an_ordered_revision_too() -> None:
    """Without one, ANY change to a built-in constant compares as unknown and refuses.

    That is safe but blunt and uninformative — an installation is taken out of service with no
    way to say whether it is ahead or behind — and it silently excludes the method axis from the
    AHEAD decision, so a desktop running newer constants refuses where for a rule set it would
    compute with a stamp.
    """
    from nmrcheck.active_versions import METHOD_DEFAULTS_SEMVER

    parts = METHOD_DEFAULTS_SEMVER.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts), METHOD_DEFAULTS_SEMVER


def test_a_moved_method_constant_forces_a_moved_revision() -> None:
    """Same invariant as a rule set, and the likelier one to be forgotten.

    A rule set is edited in the file that declares its version. These constants live in three
    modules — qNMR, multiplet, GSD — and their version in a fourth, so nothing at the edit site
    prompts a bump. The consequence is specific: two installations with different qNMR
    uncertainty defaults would compare as CURRENT and each emit a purity figure the other's
    deployment would not reproduce.
    """
    from moltrace.regulatory.infra.versioning import content_hash

    from nmrcheck.active_versions import METHOD_DEFAULTS_SEMVER, method_defaults_payload

    recorded = _manifest()["supplier_defaults"]
    observed = content_hash(method_defaults_payload())
    assert observed == recorded["identity_hash"], (
        "a built-in method constant changed and tests/golden/rule_set_revisions.json still "
        f"records the old hash.\n  recorded: {recorded['identity_hash']}\n  observed: {observed}\n"
        "Bump METHOD_DEFAULTS_SEMVER in nmrcheck/active_versions.py and update the hash IN THE "
        "SAME EDIT."
    )
    assert METHOD_DEFAULTS_SEMVER == recorded["semver"]


def test_the_legacy_version_name_still_resolves_to_the_artifact_address() -> None:
    """`_RULE_SET_VERSION` is what every stored regulatory result carries as provenance. Routing
    the engines through `artifact_for` must not have moved it, or those results are orphaned."""
    from moltrace.regulatory.impurities import (
        cpca_classifier, m7_classifier, q3ab_calculator, q3c_solvents, q3d_elements,
    )

    for module in (q3ab_calculator, q3c_solvents, q3d_elements, m7_classifier, cpca_classifier):
        assert module._RULE_SET_VERSION == module._RULE_SET_ARTIFACT.identity_hash
