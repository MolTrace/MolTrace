"""A moved rule set must move its declared version — T11, and the delta rests on it.

A content address answers "are these the same bytes?" and nothing else: `sha256(A) < sha256(B)`
says nothing about which was authored first. So an installation cannot tell from the hash alone
whether it is behind a deployment, and the ordered answer has to come from a version declared in
source beside the content.

Declared versions rot. Someone edits a rule payload, the hash moves, the semver does not, and two
different rule sets now claim the same version — at which point an installation carrying either
one believes it is current. Nothing at runtime can catch that: both sides compute honestly from
what they were given.

**This test is the whole enforcement.** The `AHEAD` policy — permitting computation from a newer
rule set rather than refusing it — was adopted on the explicit condition that this test exists,
because permitting fails *open* on a forgotten bump where refusing fails closed. Deleting or
weakening this test withdraws the condition that policy was granted under.

Its honest limit: this catches a forgotten bump in CI, not on a customer's deployment. A
deployment running a locally-modified rule set still produces a version claim nobody checked. That
is the same exposure every golden fixture here carries, and it is why the policy sits behind one
named constant that can be flipped back.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from moltrace.regulatory.impurities import (
    cpca_classifier,
    m7_classifier,
    q3ab_calculator,
    q3c_solvents,
    q3d_elements,
)

#: lineage -> the engine module that declares it. The lineage names match the registry seeds in
#: ``regulatory/ai/registry.py`` so one engine is never catalogued under two names.
ENGINES = {
    "ich_q3ab": q3ab_calculator,
    "ich_q3c": q3c_solvents,
    "ich_q3d": q3d_elements,
    "ich_m7": m7_classifier,
    "cpca": cpca_classifier,
}

#: The compiled-in method constants are versioned the same way and enforced by the same test.
#: They are NOT a rule set — they are the qNMR / multiplet / GSD literals an engine computes
#: with — but they have the identical failure mode: the constants live in three modules, nothing
#: at the edit site prompts a bump, and a forgotten one makes an installation believe its
#: constants match a deployment's when they do not.
METHOD_DEFAULTS_KEY = "supplier_defaults"

MANIFEST_PATH = Path(__file__).parent / "data" / "rule_set_revisions.json"


def _manifest() -> dict[str, dict[str, str]]:
    return json.loads(MANIFEST_PATH.read_text())["engines"]


def test_the_manifest_covers_every_engine_that_versions_itself() -> None:
    """A sixth engine must not be able to appear uncovered.

    The failure this prevents is silent: an engine absent from the manifest is an engine whose
    content can move freely, and the loop below would simply not look at it.
    """
    assert set(_manifest()) == set(ENGINES) | {METHOD_DEFAULTS_KEY}, (
        "the revision manifest and the versioned-artifact set disagree — something was added or "
        "renamed without pinning its revision"
    )


@pytest.mark.parametrize("lineage", sorted(ENGINES))
def test_a_moved_content_hash_forces_a_moved_semver(lineage: str) -> None:
    """T11. Recompute the address; if it moved, the declared version must have moved too.

    Fails in both directions on purpose. A changed hash against an unchanged semver is the
    forgotten bump. A changed semver against an unchanged hash is a version claiming a revision
    that never happened — harmless to a regulator, but it makes every later comparison say
    "behind" for content that is byte-identical.
    """
    pinned = _manifest()[lineage]
    artifact = ENGINES[lineage]._RULE_SET_ARTIFACT

    if artifact.identity_hash != pinned["identity_hash"]:
        assert artifact.semver != pinned["semver"], (
            f"{lineage}: the rule set changed and its version did not. Bump _RULE_SET_SEMVER in "
            f"the same change that altered the rule set, then regenerate the manifest — do NOT "
            f"paste the new hash in beside the old version, which is the failure this catches."
        )
    else:
        assert artifact.semver == pinned["semver"], (
            f"{lineage}: the version moved but the rule set did not. A revision that changed "
            f"nothing makes every later comparison report byte-identical content as stale."
        )


def test_every_engine_carries_an_ordered_version_beside_its_identity() -> None:
    """Identity and order must travel together, computed rather than pasted.

    ``artifact_for`` derives the hash FROM the payload, so the pair cannot drift the way two
    hand-maintained constants beside each other would.
    """
    for lineage, module in ENGINES.items():
        artifact = module._RULE_SET_ARTIFACT
        assert artifact.identity_hash.startswith("sha256:"), lineage
        assert artifact.semver, f"{lineage} declares no ordered version"
        # The legacy name still resolves to the same address, so existing callers are unmoved.
        assert module._RULE_SET_VERSION == artifact.identity_hash, lineage


def test_a_moved_method_constant_forces_a_moved_semver() -> None:
    """The method constants get the same enforcement as a rule set, and need it more.

    A rule set is edited in the file that declares its version. These constants are spread over
    three modules and their version is declared in a fourth, so nothing at the edit site prompts
    a bump — which makes this the likeliest forgotten one in the codebase.

    The consequence of forgetting is specific: two installations with different qNMR uncertainty
    defaults would compare as *current*, and each would emit a purity figure the other's
    deployment would not reproduce.
    """
    from moltrace.regulatory.infra.versioning import content_hash
    from nmrcheck.active_versions import METHOD_DEFAULTS_SEMVER, method_defaults_payload

    pinned = _manifest()[METHOD_DEFAULTS_KEY]
    identity = content_hash(method_defaults_payload())

    if identity != pinned["identity_hash"]:
        assert METHOD_DEFAULTS_SEMVER != pinned["semver"], (
            "a built-in method constant changed and METHOD_DEFAULTS_SEMVER did not. Bump it in "
            "the same change, then regenerate the manifest."
        )
    else:
        assert METHOD_DEFAULTS_SEMVER == pinned["semver"], (
            "METHOD_DEFAULTS_SEMVER moved but no constant did — every later comparison would "
            "report identical constants as stale."
        )
