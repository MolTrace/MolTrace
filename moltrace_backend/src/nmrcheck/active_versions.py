"""What this deployment is actually running, as coordinates an installation can compare.

Four axes, each assembled from the thing that already owns it rather than from a second
catalogue written here:

* **rule sets** — the five deterministic engines, read from their own ``_RULE_SET_ARTIFACT``.
* **model artifacts** — whatever the registry currently resolves as ``production``, through
  ``ai_engine_adapter``, which is the documented single import boundary onto the AI layer.
* **reference packs** — the HOSE knowledge base, addressed by digest.
* **method defaults** — the constants compiled into this build, as ONE content address.

**Report only what the comparison consumes.** No file paths, no module paths, no training-data
summaries, no corpus counts. The catalogue names which regulated rule sets a customer has adopted
and which artifacts they serve, which is a description of their validated configuration — it is
not ours to publish, and it is not something a caller needs in order to compare.

An axis that cannot be determined yields a coordinate with ``identity=None``, which the comparator
turns into *unknown* and refuses on. Absence is never reported as agreement.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import ai_engine_adapter
from .version_currency import VersionCoordinate

__all__ = [
    "METHOD_DEFAULTS_LINEAGE",
    "METHOD_DEFAULTS_SEMVER",
    "active_version_coordinates",
    "assertion_payload",
    "method_defaults_payload",
    "sign_version_assertion",
    "verify_version_assertion",
]

#: One lineage for the whole compiled-in constant set. There is no laboratory-supersedable
#: method profile in this platform — the constants below are module-level literals in the
#: engines — so the honest thing to publish is a single content address for "the defaults this
#: build shipped", not an invented per-constant version. An installation compares it to detect
#: that its constants differ at all; it cannot be told WHICH differ, because nothing here
#: declares them individually.
METHOD_DEFAULTS_LINEAGE = "supplier_defaults"

#: The ORDERED version of the constant set below. Bump it in the same change that alters any
#: constant `method_defaults_payload` reads.
#:
#: Without this the method axis had an identity and no ordering, so any constant change compared
#: as *unknown* — "cannot establish currency" — and refused. That is safe but blunt and, worse,
#: uninformative: an installation was taken out of service with no way to say whether it was
#: ahead or behind, and a scientist could not be told to update. With a declared version the same
#: change reports *behind*, which is true, actionable, and lets the AHEAD policy apply here as it
#: does to the rule sets.
#:
#: The constants themselves live in three other modules, so nothing at the edit site prompts this
#: bump. `tests/test_rule_set_revisions.py` is the enforcement, exactly as it is for the five
#: rule sets: it fails when the payload's content hash moves and this does not.
METHOD_DEFAULTS_SEMVER = "1.1.0"

#: lineage -> (display name, import path of the engine module).
_RULE_ENGINES: tuple[tuple[str, str, str], ...] = (
    ("ich_q3ab", "ICH Q3A/Q3B impurity rule set", "q3ab_calculator"),
    ("ich_q3c", "ICH Q3C residual-solvent rule set", "q3c_solvents"),
    ("ich_q3d", "ICH Q3D elemental-impurity rule set", "q3d_elements"),
    ("ich_m7", "ICH M7 mutagenic-impurity rule set", "m7_classifier"),
    ("cpca", "CPCA nitrosamine rule set", "cpca_classifier"),
)


def method_defaults_payload() -> dict[str, Any]:
    """The compiled-in method constants, as a plain mapping to be content-addressed.

    Deliberately explicit rather than reflected out of the modules: a reflective sweep would
    silently change the address whenever an unrelated module-level constant was added, and an
    address that moves for reasons nobody intended is worse than no address at all.
    """

    from moltrace.spectroscopy.multiplet import analysis as multiplet
    from moltrace.spectroscopy.peaks import gsd
    from moltrace.spectroscopy.qnmr import purity

    return {
        "qnmr": {
            "integral_rel_u": purity._DEFAULT_INTEGRAL_REL_U,
            "mass_rel_u": purity._DEFAULT_MASS_REL_U,
            "pulse_rel_u": purity._DEFAULT_PULSE_REL_U,
            "conc_rel_u": purity._DEFAULT_CONC_REL_U,
        },
        "multiplet": {"min_j_hz": multiplet._MIN_J_HZ, "max_j_hz": multiplet._MAX_J_HZ},
        "gsd": {
            "max_peaks_by_level": dict(gsd._MAX_PEAKS_BY_LEVEL),
            "min_satellite_ratio": gsd._MIN_SATELLITE_RATIO,
            "max_satellite_ratio": gsd._MAX_SATELLITE_RATIO,
            "default_field_mhz": gsd._DEFAULT_FIELD_MHZ,
        },
    }


def _rule_set_coordinates() -> list[VersionCoordinate]:
    import importlib

    coordinates: list[VersionCoordinate] = []
    for lineage, display_name, module_name in _RULE_ENGINES:
        module = importlib.import_module(f"moltrace.regulatory.impurities.{module_name}")
        artifact = module._RULE_SET_ARTIFACT
        coordinates.append(
            VersionCoordinate(
                lineage=lineage,
                display_name=display_name,
                identity=artifact.identity_hash,
                revision=artifact.semver,
                kind="rule_set",
            )
        )
    return coordinates


def _model_coordinates(session_factory: Any) -> list[VersionCoordinate]:
    """Only what the router would actually resolve.

    Keyed by role and nucleus rather than by ``model_id``: an installation compares "the proton
    shift predictor" against "the proton shift predictor", and model ids are per-registration.
    """

    coordinates: list[VersionCoordinate] = []
    for artifact in ai_engine_adapter.serving_artifacts(session_factory):
        suffix = f":{artifact.nucleus}" if artifact.nucleus else ""
        nucleus_copy = f" ({artifact.nucleus})" if artifact.nucleus else ""
        coordinates.append(
            VersionCoordinate(
                lineage=f"model:{artifact.role}{suffix}",
                display_name=f"{artifact.role.replace('_', ' ')} model{nucleus_copy}",
                identity=f"sha256:{artifact.artifact_sha256}",
                revision=artifact.semantic_version,
                kind="model_artifact",
            )
        )
    return coordinates


def _reference_pack_coordinate() -> VersionCoordinate:
    """The HOSE knowledge base.

    It carries **no** ordered revision, and that is a fact rather than an omission: the pack is a
    deployment-configured file with no declared version anywhere. So two different packs compare
    as *unknown* and refuse, while byte-identical ones are current by identity alone (step 3 of
    the algebra, which precedes any ordering).
    """

    from moltrace.spectroscopy.predict.nmrnet_wrapper import knowledge_base_identity

    return VersionCoordinate(
        lineage="reference_pack:hose",
        display_name="reference shift knowledge base",
        identity=knowledge_base_identity(),
        revision=None,
        kind="reference_pack",
    )


def _method_defaults_coordinate() -> VersionCoordinate:
    from moltrace.regulatory.infra.versioning import content_hash

    return VersionCoordinate(
        lineage=METHOD_DEFAULTS_LINEAGE,
        display_name="built-in method-constant set",
        identity=content_hash(method_defaults_payload()),
        revision=METHOD_DEFAULTS_SEMVER,
        kind="method_defaults",
    )


def active_version_coordinates(session_factory: Any) -> list[VersionCoordinate]:
    """Every coordinate this deployment publishes, in a stable order.

    Sorted by lineage so the serialized catalogue is byte-stable for a given deployment state —
    which matters because it is signed, and a signature over a set whose order wandered would
    fail to verify for no reason a person could see.
    """

    coordinates = [
        *_rule_set_coordinates(),
        *_model_coordinates(session_factory),
        _reference_pack_coordinate(),
        _method_defaults_coordinate(),
    ]
    return sorted(coordinates, key=lambda c: c.lineage)


# --------------------------------------------------------------------------------------------
# The signed assertion (§4)
# --------------------------------------------------------------------------------------------
#: The catalogue must be authenticated for an installation that is offline: an unsigned version
#: list is forgeable by anything that can write to the local data plane, and the whole point is
#: to refuse a stale REGULATED result.
#:
#: It is a SEPARATE document from the entitlement statement, signed by the same deployment
#: sub-key and verified through the same certificate chain to the same pinned root. Separate
#: because the two have opposite lifetimes: an entitlement statement is commercial state with a
#: hard expiry, and rule packs ship on a content cadence. Binding versions into the statement
#: would make every pack release either invalidate outstanding entitlements or force a reissue
#: storm — and worse, it would let a content release expire something, which inverts the rule
#: that expiry never blocks reading existing records.
#:
#: **Delivered on this route rather than with the entitlement exchange.** §4 leaves that open.
#: Bundling it into the exchange would re-couple the two round trips even though the documents
#: stayed separate, which gives back the independence the separation was for. A client already
#: has to call this route to compare, so riding here costs no extra request.
#:
#: No commercial expiry, deliberately. Freshness is judged by comparing coordinates, never by a
#: deadline — which is what keeps a content release from ever touching a licence.
_ASSERTION_SCHEMA = "moltrace.deployment.version-assertion/1"


def assertion_payload(coordinates: list[VersionCoordinate]) -> dict[str, Any]:
    """The exact mapping that gets canonically serialized and signed.

    Field order is irrelevant (the canonical serializer sorts), but coordinate order is not —
    it comes from ``active_version_coordinates``, which sorts by lineage so the bytes are stable
    for a given deployment state.
    """

    return {
        "assertion_schema": _ASSERTION_SCHEMA,
        "versions": [
            {
                "kind": coordinate.kind,
                "lineage": coordinate.lineage,
                "identity": coordinate.identity,
                "revision": coordinate.revision,
            }
            for coordinate in coordinates
        ],
    }


def sign_version_assertion(settings: Any, coordinates: list[VersionCoordinate]) -> str | None:
    """Sign the catalogue with this deployment's issuing key, or ``None`` if it has none.

    ``None`` rather than an error: a deployment that licenses no offline installations still
    serves this route to its browser clients, and a missing signature is not a fault there. A
    desktop that requires an authenticated catalogue treats the absence as *cannot establish
    currency* and refuses, which is the correct answer for it and the wrong one for a browser.
    """

    from . import entitlement_statement as es

    seed = getattr(settings, "entitlement_issuing_private_key", None)
    if not seed:
        return None
    try:
        return es.sign_payload(es.VERSION_ASSERTION_DOMAIN, assertion_payload(coordinates), seed)
    except Exception:  # noqa: BLE001 - an unsigned catalogue is degraded, never a failed read
        return None


def verify_version_assertion(
    *, payload: Mapping[str, Any], signature: str, issuing_public_key: str | None
) -> bool:
    """Verify an assertion against the deployment's issuing public key.

    Offline by construction: everything needed is the stored payload, its signature and the
    certificate the installation already holds. No nonce, no clock, no round trip — a nonce
    could not work here, because the assertion has to keep verifying from local storage across
    restarts with no server to ask.

    The domain prefix is what stops an entitlement statement being presented here, or this being
    presented as one. It is prepended at signing and again at verification, never stored.
    """

    from . import entitlement_statement as es

    return es.verify_payload(
        es.VERSION_ASSERTION_DOMAIN,
        es.canonical_bytes(payload),
        signature,
        issuing_public_key,
    )
