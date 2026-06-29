#!/usr/bin/env python3
"""Validate the MolTrace control->evidence register (Security Prompt 22).

Checks that the compliance register (``compliance/controls.json``) is well-formed and
that **every in-repo control cites at least one evidence path AND every cited evidence
path RESOLVES** (exists in the repo). This keeps the control-evidence map honest: a
control whose evidence file is deleted or moved fails the check, so the map can't
silently rot — the same fail-on-drift idea as the CSPM IaC baseline.

It validates control **coverage** only. SOC 2 and ISO/IEC 27001 are *audited*
certifications that MolTrace does not currently hold; this register and validator are
a self-assessment, **not an attestation** — only an auditor's report / certificate
confers assurance.

    python compliance/validate_controls.py     # exit 0 = valid · 1 = problems · 2 = can't read
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_REGISTER = Path(__file__).resolve().parent / "controls.json"

_REQUIRED_CONTROL_KEYS = (
    "id",
    "control",
    "summary",
    "soc2_tsc",
    "iso27001_annex_a",
    "type",
    "evidence",
)


def validate(register: dict, *, repo_root: Path) -> list[str]:
    """Return a list of problems (empty == valid). Pure: no printing, no exit."""
    problems: list[str] = []

    controls = register.get("controls")
    if not isinstance(controls, list) or not controls:
        problems.append("register has no 'controls' list")
        controls = []

    seen_ids: set[str] = set()
    for idx, control in enumerate(controls):
        if not isinstance(control, dict):
            problems.append(f"control #{idx}: entry is not an object")
            continue
        label = control.get("id") or control.get("control") or f"#{idx}"
        for key in _REQUIRED_CONTROL_KEYS:
            if key not in control:
                problems.append(f"control '{label}': missing key '{key}'")
        cid = control.get("id")
        if cid:
            if cid in seen_ids:
                problems.append(f"control '{label}': duplicate id '{cid}'")
            seen_ids.add(cid)
        if not control.get("soc2_tsc"):
            problems.append(f"control '{label}': no SOC 2 TSC mapping")
        if not control.get("iso27001_annex_a"):
            problems.append(f"control '{label}': no ISO 27001 Annex A mapping")

        # Only in-repo controls must cite resolvable evidence paths.
        if control.get("type") == "in-repo":
            evidence = control.get("evidence") or []
            if not isinstance(evidence, list) or not evidence:
                problems.append(f"control '{label}': in-repo control cites no evidence list")
                evidence = []
            for path in evidence:
                # Evidence must be a repo-relative path to an existing FILE (not a dir,
                # not an absolute path that escapes the repo root).
                if not isinstance(path, str) or Path(path).is_absolute():
                    problems.append(f"control '{label}': invalid evidence path: {path!r}")
                elif not (repo_root / path).is_file():
                    problems.append(
                        f"control '{label}': evidence path does not resolve to a file: {path}"
                    )

    # Inherited/operational entries are structurally checked (no in-repo evidence by design).
    for idx, entry in enumerate(register.get("inherited_or_operational") or []):
        label = entry.get("control") or f"#{idx}"
        if entry.get("type") not in ("inherited", "operational"):
            problems.append(f"inherited/operational '{label}': type must be inherited|operational")
        if not entry.get("via"):
            problems.append(f"inherited/operational '{label}': missing 'via' (who provides it)")

    return problems


def _summary(register: dict) -> str:
    controls = register.get("controls") or []
    tsc = sorted({c for ctrl in controls for c in (ctrl.get("soc2_tsc") or [])})
    annex = sorted({a for ctrl in controls for a in (ctrl.get("iso27001_annex_a") or [])})
    inherited = register.get("inherited_or_operational") or []
    return (
        f"{len(controls)} in-repo controls; {len(inherited)} inherited/operational. "
        f"SOC 2 TSC covered: {', '.join(tsc)}. ISO 27001 Annex A: {', '.join(annex)}."
    )


def main(argv: list[str] | None = None) -> int:
    path = Path(argv[0]) if argv else _REGISTER
    try:
        register = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"compliance: cannot read register {path}: {exc}", file=sys.stderr)
        return 2

    problems = validate(register, repo_root=_REPO_ROOT)
    print(f"compliance register: {_summary(register)}")
    if problems:
        print(f"  {len(problems)} problem(s):", file=sys.stderr)
        for problem in problems:
            print(f"    - {problem}", file=sys.stderr)
        return 1
    print("compliance: register valid — every in-repo control's evidence resolves.")
    print("  NOTE: this is control-coverage self-assessment, not a SOC 2 / ISO 27001 attestation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
