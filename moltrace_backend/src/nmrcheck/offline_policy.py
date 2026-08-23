"""§7.8 — the operation offline-policy table.

"Classify every operation as offline-view, offline-draft, offline-compute,
sync-required, or online-only, in one policy table that is the single source for
the interface, the adapter, and the tests."

The failure this prevents is drift between three readers: the interface deciding
an operation is available offline, the adapter deciding it is not, and the tests
asserting a third thing. There is one table, and a test asserts no other module
in ``src/`` hard-codes a class name — a second source of truth is where the drift
starts.

**An operation absent from the table has no class, and asking for one raises.**
Not ``online-only``, which would look responsible and would still hide the gap:
an unreviewed operation would silently acquire a policy nobody chose. The whole
value of a policy table is that a missing entry is loud.

This table is deliberately SMALL. Phase 0 classified all 928 API operations, but
that classification is a program artifact rather than a tested one, and importing
it wholesale would move 928 unreviewed decisions into a file that claims to be
reviewed. Entries are added as the local service learns to serve them, each with
a reason when it is withheld.
"""

from __future__ import annotations

#: The five classes, in the order §7.8 names them.
OFFLINE_CLASSES: tuple[str, ...] = (
    "offline-view",
    "offline-draft",
    "offline-compute",
    "sync-required",
    "online-only",
)

#: The classes the local service will serve. The other two are online by
#: definition: ``sync-required`` needs the server to reconcile, ``online-only``
#: needs it to authorize or to hold the canonical record.
SERVED_LOCALLY: tuple[str, ...] = ("offline-view", "offline-draft", "offline-compute")


class UnclassifiedOperation(KeyError):
    """Asked for the offline class of an operation nobody has classified."""


POLICY: dict[str, str] = {
    # The health probe: no record, no authorization, no data.
    "system.health": "offline-view",
    # Reading records already on this device. §9.2 is absolute that an expired
    # entitlement must not block reading local records, so this cannot be online.
    "records.read.local": "offline-view",
    # Composing work that is not yet a record. A draft is not a regulated output.
    "analysis.draft": "offline-draft",
    # The reason the desktop exists: deterministic science on local bytes.
    "fid.process": "offline-compute",
    # Signing is server-authoritative — identity, step-up and record binding all
    # live there, and §6.5 refuses offline signing in every profile.
    "signature.create": "online-only",
    # The entitlement statement is issued by the deployment, never minted here.
    "entitlement.issue": "online-only",
    # A local record becomes canonical only when the server has observed it.
    "records.submit": "sync-required",
}

#: Why an operation is withheld from offline use. §7.8 wants this in the table
#: rather than in a comment somewhere, because it is a product decision and the
#: next person to want it offline needs the reason, not the verdict.
WITHHELD_REASONS: dict[str, str] = {
    "signature.create": (
        "The server is authoritative for signer identity, current authorization, step-up and "
        "record-snapshot binding, so a signature made offline could not be bound to any of them."
    ),
    "entitlement.issue": (
        "An entitlement statement is issued by the deployment and verified here against a pinned "
        "public key. A client that could mint one would be its own licensing authority."
    ),
    "records.submit": (
        "A record is canonical once the server has observed it and written it into the audit "
        "chain. Until then the device journal holds it, and reconciliation is what promotes it."
    ),
}


def offline_class(operation: str) -> str:
    """The operation's class, or raise. There is no default."""
    try:
        return POLICY[operation]
    except KeyError:
        raise UnclassifiedOperation(
            f"{operation!r} has no offline class. Classify it in the policy table before "
            f"the interface, the adapter or a test decides for itself."
        ) from None


def is_served_locally(operation: str) -> bool:
    """Whether the local service may serve this operation at all."""
    return offline_class(operation) in SERVED_LOCALLY
