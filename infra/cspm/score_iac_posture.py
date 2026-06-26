#!/usr/bin/env python3
"""CSPM-lite: score the repo's IaC posture against a committed baseline; fail on drift.

Security Prompt 18 (zero-trust infrastructure). The Prompt 14 ``iac`` CI gate already
runs Trivy ``config`` over the declarative infrastructure (the ``render.yaml``
blueprints + the GitHub Actions workflows) and hard-blocks on CRITICAL
misconfigurations. This adds a *continuously-scored, drift-alerting* layer on top:
it records the accepted set of HIGH/CRITICAL misconfigurations in a committed
baseline and FAILS on any NEW misconfiguration not already accepted — so posture
drift is caught the moment it lands, not only when it escalates to CRITICAL.

The baseline IS the score: an empty ``accepted`` list means a clean posture; every
entry is an explicitly-accepted misconfiguration (with a justification in the
``notes`` map), mirroring the ``.trivyignore`` VEX register used for dependencies.

Usage (CI, after a ``trivy config --format json`` pass):

    python3 infra/cspm/score_iac_posture.py \
        --trivy-json trivy-iac.json \
        --baseline infra/cspm/iac_posture_baseline.json

Exit codes: ``0`` = no drift (current findings are a subset of the baseline);
``1`` = drift (new findings); ``2`` = usage/parse error.

To accept the current posture as the new baseline (a deliberate, reviewed act —
record why in the baseline's ``notes``):

    python3 infra/cspm/score_iac_posture.py --trivy-json trivy-iac.json \
        --baseline infra/cspm/iac_posture_baseline.json --update
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Score on HIGH+CRITICAL misconfigurations (the CI report pass already emits these to
# the Security tab). The existing Trivy gate still independently hard-blocks CRITICAL;
# this drift gate additionally blocks any NEW HIGH/CRITICAL relative to the baseline.
_SCORED_SEVERITIES = frozenset({"HIGH", "CRITICAL"})


def finding_key(misconf_id: str, target: str, severity: str) -> str:
    """Stable identity for a misconfiguration: its check id, the file it was found in,
    and its severity — so a severity change (e.g. HIGH->CRITICAL, or a downgrade) reads
    as resolve-old + new-drift rather than being silently absorbed under the same key.
    """
    return f"{misconf_id}::{target}::{severity.upper()}"


def extract_findings(
    trivy_report: dict, severities: frozenset[str] = _SCORED_SEVERITIES
) -> set[str]:
    """The set of FAILing misconfiguration keys at the scored severities."""
    out: set[str] = set()
    for result in trivy_report.get("Results") or []:
        target = result.get("Target") or "?"
        for misconf in result.get("Misconfigurations") or []:
            if (misconf.get("Status") or "FAIL").upper() != "FAIL":
                continue
            severity = (misconf.get("Severity") or "").upper()
            if severity not in severities:
                continue
            mid = misconf.get("ID") or misconf.get("AVDID") or "UNKNOWN"
            out.add(finding_key(mid, target, severity))
    return out


def compute_drift(current: set[str], accepted: set[str]) -> set[str]:
    """New findings present now but not accepted in the baseline."""
    return current - accepted


def load_accepted(baseline_path: Path) -> set[str]:
    if not baseline_path.exists():
        return set()
    data = json.loads(baseline_path.read_text())
    return set(data.get("accepted") or [])


def write_baseline(baseline_path: Path, accepted: set[str]) -> None:
    payload = {
        "_comment": (
            "CSPM IaC posture baseline (Security Prompt 18). Each entry is an "
            "explicitly-accepted HIGH/CRITICAL Trivy-config misconfiguration "
            "(id::target::severity). An empty list = clean posture. Update only via "
            "score_iac_posture.py --update, recording the justification in notes."
        ),
        "accepted": sorted(accepted),
        "notes": {},
    }
    baseline_path.write_text(json.dumps(payload, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score IaC posture vs a committed baseline; fail on drift."
    )
    parser.add_argument("--trivy-json", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument(
        "--update",
        action="store_true",
        help="accept the current findings as the new baseline",
    )
    args = parser.parse_args(argv)

    try:
        report = json.loads(args.trivy_json.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"CSPM: cannot read Trivy JSON {args.trivy_json}: {exc}", file=sys.stderr)
        return 2

    # Integrity guard: a real Trivy report always carries SchemaVersion (a *clean*
    # config scan omits the Results key entirely, but still has SchemaVersion). Refuse
    # to score a ``{}``/``null``/garbage file — otherwise a silently-failed scan would
    # look like a clean posture (false negative).
    if not isinstance(report, dict) or "SchemaVersion" not in report:
        print(
            f"CSPM: {args.trivy_json} is not a valid Trivy report (no SchemaVersion) — "
            "refusing to score a possibly-failed scan.",
            file=sys.stderr,
        )
        return 2

    current = extract_findings(report)

    if args.update:
        write_baseline(args.baseline, current)
        print(f"CSPM: baseline updated — {len(current)} accepted misconfiguration(s).")
        return 0

    accepted = load_accepted(args.baseline)
    drift = compute_drift(current, accepted)
    resolved = accepted - current  # accepted entries that no longer fire (informational)

    print(
        f"CSPM IaC posture: {len(current)} HIGH/CRITICAL finding(s); "
        f"{len(accepted)} accepted; {len(drift)} drift; {len(resolved)} resolved."
    )
    if resolved:
        print("  resolved (consider pruning from the baseline):")
        for key in sorted(resolved):
            print(f"    - {key}")
    if drift:
        print("  DRIFT — new misconfigurations not in the baseline:", file=sys.stderr)
        for key in sorted(drift):
            print(f"    + {key}", file=sys.stderr)
        print(
            "  Fix the misconfiguration, or (if accepted) run "
            "score_iac_posture.py --update with a justification.",
            file=sys.stderr,
        )
        return 1
    print("CSPM: no posture drift.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
