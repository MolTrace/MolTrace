#!/usr/bin/env python3
"""Re-verify an exported MolTrace audit chain, offline, with nothing but the standard library.

Point it at the JSON body of ``GET /audit/{subject_type}/{subject_id}/entries``::

    python verify_audit_export.py entries.json
    python verify_audit_export.py entries.json --tip-hash sha256:abc123...

**This file deliberately imports nothing from MolTrace.** An auditor should be able to copy
it onto a machine that has never seen this product, run it against an export we handed
them, and reach their own verdict — a verification you can only run inside the system you
are verifying is not much of a verification.

WHAT THIS ESTABLISHES, AND WHAT IT DOES NOT
-------------------------------------------
Establishes, with no key and no trust in us:

* **No entry was altered.** Each entry's digest is recomputed from its own fields; the
  digest covers the raw ``metadata_json`` text, so any edit to content changes it.
* **No entry was removed or reordered.** ``chain_seq`` must be contiguous and each entry's
  ``prev_hash`` must equal the previous entry's ``entry_hash``.
* **The export matches a checkpoint** — if you pass ``--tip-hash`` from an anchor MolTrace
  published, the final entry must hash to it.

Does NOT establish:

* **That MolTrace wrote these entries** — unless you pass ``--anchor`` and
  ``--public-key``. Anchors sealed with the older symmetric HMAC scheme cannot be verified
  by an outsider at all, because the key that verifies is the key that forges; for those, a
  clean result here means internally consistent, not authentic, and anyone claiming
  otherwise from this output is overstating it. Anchors sealed with Ed25519 CAN be checked
  from the published public key (``GET /audit/anchor-public-key``), and that check needs the
  ``cryptography`` package — the only part of this tool that is not standard library. Run it
  without those flags and everything above still works with no dependencies at all.

Exit codes: 0 verified · 1 a break was found · 2 the file could not be read as an export.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Any

GENESIS_HASH = "sha256:" + "0" * 64

#: The exact fields the digest covers, in the order the server canonicalises them. Keep in
#: step with ``nmrcheck.audit_chain._canonical_payload`` — if they drift, this tool reports a
#: mismatch on a healthy export, which is the safe direction to fail.
COVERED_FIELDS = (
    "chain_seq",
    "chain_ts",
    "created_at",
    "event_type",
    "message",
    "actor_user_id",
    "actor_email",
    "entity_type",
    "entity_id",
    "metadata_json",
    "prev_hash",
)


def canonical_digest(entry: dict[str, Any]) -> str:
    """Recompute one entry's ``entry_hash`` from its own fields."""

    payload = {name: entry.get(name) for name in COVERED_FIELDS}
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def verify(entries: list[dict[str, Any]], *, tip_hash: str | None = None) -> list[str]:
    """Return a list of findings; empty means the export verified."""

    findings: list[str] = []
    if not entries:
        return ["export contains no entries — nothing was checked, which is not a pass"]

    ordered = sorted(entries, key=lambda e: e["chain_seq"])
    if [e["chain_seq"] for e in ordered] != [e["chain_seq"] for e in entries]:
        findings.append("entries were not in chain_seq order (sorted before checking)")

    expected_prev = None
    expected_seq = None
    for entry in ordered:
        seq = entry["chain_seq"]
        if expected_seq is not None and seq != expected_seq:
            findings.append(
                f"sequence_gap at chain_seq {seq}: expected {expected_seq} — an entry was "
                "removed, or the export is partial"
            )
        if expected_prev is not None and entry.get("prev_hash") != expected_prev:
            findings.append(
                f"prev_hash_mismatch at chain_seq {seq}: entries were reordered or re-linked"
            )
        recomputed = canonical_digest(entry)
        if recomputed != entry.get("entry_hash"):
            findings.append(
                f"entry_hash_mismatch at chain_seq {seq}: this entry's content was altered "
                f"(recomputed {recomputed}, recorded {entry.get('entry_hash')})"
            )
        expected_prev = entry.get("entry_hash")
        expected_seq = seq + 1

    if tip_hash is not None and expected_prev != tip_hash:
        findings.append(
            f"tip_mismatch: the export ends at {expected_prev}, but the anchor commits to "
            f"{tip_hash} — this export is not the run that checkpoint covers"
        )
    return findings


def check_anchor(anchor: dict[str, Any], public_key_hex: str | None) -> str:
    """Verify an Ed25519 anchor signature. Returns "OK" or a reason it could not be established.

    Deliberately never raises and never returns OK on a scheme it cannot check: "I could not
    verify this" and "this is valid" must not collapse into the same outcome.
    """

    signature = str(anchor.get("signature", ""))
    if not signature.startswith("ed25519:"):
        return "anchor is not Ed25519-signed; an outsider cannot verify it"
    if not public_key_hex:
        return "no --public-key supplied"
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return "the `cryptography` package is not installed (pip install cryptography)"

    # Verify the bytes that were actually signed. Re-deriving them here would reintroduce
    # the encoder mismatch this field exists to avoid (`anchored_at` renders as `Z` through
    # most JSON encoders, while the signature covers `+00:00`).
    signed_payload = anchor.get("signed_payload")
    if not signed_payload:
        return "anchor record carries no signed_payload; cannot verify the exact signed bytes"
    canonical = signed_payload.encode("utf-8")
    try:
        committed = json.loads(signed_payload)
    except ValueError:
        return "anchor signed_payload is not valid JSON"
    if committed.get("tip_hash") != anchor.get("tip_hash"):
        return "FAILED: the anchor's displayed tip_hash is not the one it signed"
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex)).verify(
            bytes.fromhex(signature[len("ed25519:"):]), canonical
        )
    except (InvalidSignature, ValueError):
        return "FAILED: the anchor signature does not match this public key"
    return "OK"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("export", help="JSON file from /audit/{subject_type}/{id}/entries")
    parser.add_argument(
        "--tip-hash",
        default=None,
        help="an anchor's tip_hash, to confirm the export matches a published checkpoint",
    )
    parser.add_argument(
        "--anchor",
        default=None,
        help="JSON file holding the anchor record (from_seq, tip_seq, tip_hash, row_count, "
             "anchored_at, signature) — checked for authenticity with --public-key",
    )
    parser.add_argument(
        "--public-key",
        default=None,
        help="hex Ed25519 public key from GET /audit/anchor-public-key; requires the "
             "`cryptography` package. Without it the run is integrity-only.",
    )
    args = parser.parse_args(argv)

    try:
        with open(args.export, encoding="utf-8") as handle:
            entries = json.load(handle)
        if not isinstance(entries, list):
            raise ValueError("expected a JSON array of entries")
    except (OSError, ValueError) as exc:
        print(f"could not read {args.export!r} as an audit export: {exc}", file=sys.stderr)
        return 2

    anchor_verdict: str | None = None
    if args.anchor:
        try:
            with open(args.anchor, encoding="utf-8") as handle:
                anchor = json.load(handle)
        except (OSError, ValueError) as exc:
            print(f"could not read {args.anchor!r} as an anchor: {exc}", file=sys.stderr)
            return 2
        anchor_verdict = check_anchor(anchor, args.public_key)
        if args.tip_hash is None:
            args.tip_hash = anchor.get("tip_hash")

    findings = verify(entries, tip_hash=args.tip_hash)
    if anchor_verdict is not None and anchor_verdict.startswith("FAILED"):
        findings.append(anchor_verdict)
    first = min((e.get("chain_seq") for e in entries), default=None)
    last = max((e.get("chain_seq") for e in entries), default=None)
    print(f"{len(entries)} entries, chain_seq {first}..{last}")
    if findings:
        print("\nNOT VERIFIED:")
        for finding in findings:
            print(f"  - {finding}")
        return 1

    authentic = anchor_verdict == "OK"
    print(
        "\nVERIFIED — integrity and authenticity:"
        if authentic
        else "\nVERIFIED — integrity only:"
    )
    print("  no entry altered, none removed or reordered"
          + (", and the export matches the anchor" if args.tip_hash else ""))
    if authentic:
        print("  the anchor's Ed25519 signature checks out against the public key you")
        print("  supplied, so this checkpoint was sealed by the holder of the private key.")
    else:
        if anchor_verdict:
            print(f"  anchor authenticity NOT established: {anchor_verdict}")
        print("  this does NOT establish who authored these entries. Supply --anchor and")
        print("  --public-key to check an Ed25519 checkpoint; anchors sealed with the older")
        print("  symmetric HMAC scheme cannot be verified by an outsider at all, because the")
        print("  key that verifies them is the key that forges them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
