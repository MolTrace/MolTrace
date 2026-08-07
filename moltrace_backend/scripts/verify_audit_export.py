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

* **That MolTrace wrote these entries.** Anchors are signed with a symmetric HMAC key, so
  authenticity cannot be checked without a secret that would also let its holder forge
  entries. A clean result here means the export is internally consistent, not that it is
  authentic. Anyone claiming otherwise from this tool's output is overstating it.

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("export", help="JSON file from /audit/{subject_type}/{id}/entries")
    parser.add_argument(
        "--tip-hash",
        default=None,
        help="an anchor's tip_hash, to confirm the export matches a published checkpoint",
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

    findings = verify(entries, tip_hash=args.tip_hash)
    first = min((e.get("chain_seq") for e in entries), default=None)
    last = max((e.get("chain_seq") for e in entries), default=None)
    print(f"{len(entries)} entries, chain_seq {first}..{last}")
    if findings:
        print("\nNOT VERIFIED:")
        for finding in findings:
            print(f"  - {finding}")
        return 1

    print("\nVERIFIED — integrity only:")
    print("  no entry altered, none removed or reordered"
          + (", and the export matches the anchor" if args.tip_hash else ""))
    print("  this does NOT establish that MolTrace authored these entries; anchor")
    print("  signatures are symmetric (HMAC) and cannot be checked without a secret")
    print("  that would also allow forging them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
