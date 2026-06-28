"""Backup / disaster-recovery restore-integrity verifier (Security Prompt 21).

After a restore (a region-loss DR drill or a routine restore), this proves the
restored database is **intact and un-tampered** by re-running the tamper-evident
audit-chain verification (Prompt 10) + restore-sanity checks. A restored DB whose
per-row SHA-256 chain + HMAC anchors + signed high-water mark still verify is
*provable* evidence that nothing was lost or altered in transit — the audit chain is
the natural restore-integrity oracle. This is the **"verified for integrity"** half of
the DR acceptance criterion; the cross-region/immutable backup storage and *running*
the restore are operational (see docs/security/backup_dr.md).

Library + thin CLI, no app/runtime coupling:

    python -m nmrcheck.dr_verify                              # verify the configured DATABASE_URL
    python -m nmrcheck.dr_verify --min-rows audit_events=1,users=1

Exit codes: ``0`` = integrity verified · ``1`` = a check failed · ``2`` = could not run.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .audit_chain import _DEV_FALLBACK, key_id

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session, sessionmaker

    from .models import AuditChainVerification
    from .settings import Settings

# key_id of the dev-fallback signing key — a restored *prod* DB still resolving to this
# means AUDIT_SIGNING_KEY is unset, so the chain's tamper-evidence can't be trusted.
_DEV_KEY_ID = key_id(_DEV_FALLBACK)
# Core tables a restored MolTrace DB must contain; a wrong/empty restore is caught when
# one is missing or below its baseline count.
_DEFAULT_TABLES: tuple[str, ...] = ("audit_events", "users", "security_events")
_IDENT = re.compile(r"[a-z_][a-z0-9_]*\Z")


@dataclass
class IntegrityCheck:
    name: str
    ok: bool
    detail: str


@dataclass
class RestoreIntegrityReport:
    ok: bool
    checks: list[IntegrityCheck] = field(default_factory=list)
    audit_chain_ok: bool = False
    chained_events: int = 0
    signing_key_is_dev: bool = False
    row_counts: dict[str, int] = field(default_factory=dict)


def assess(
    verification: AuditChainVerification,
    *,
    row_counts: dict[str, int],
    baseline: dict[str, int] | None = None,
) -> RestoreIntegrityReport:
    """Pure decision: given an audit-chain verification + restored row counts (and an
    optional pre-loss baseline of minimum expected counts per table), decide whether the
    restore is integrity-verified. No DB access — unit-testable in isolation."""
    baseline = baseline or {}
    checks: list[IntegrityCheck] = []

    chain_ok = bool(verification.ok)
    chain_detail = "ok"
    if not chain_ok:
        chain_detail = f"chain verification failed: {verification.detail}"
        if verification.first_break_seq is not None:
            chain_detail += f" @seq {verification.first_break_seq}"
    checks.append(IntegrityCheck("audit_chain", chain_ok, chain_detail))

    has_history = int(verification.total_chained) > 0
    checks.append(
        IntegrityCheck(
            "audit_history_present",
            has_history,
            f"{verification.total_chained} chained events"
            if has_history
            else "no chained audit events — empty or wrong database?",
        )
    )

    key_is_dev = verification.key_id == _DEV_KEY_ID
    checks.append(
        IntegrityCheck(
            "signing_key_not_dev",
            not key_is_dev,
            "production audit signing key in use"
            if not key_is_dev
            else "DEV-FALLBACK signing key — set AUDIT_SIGNING_KEY before trusting a restore",
        )
    )

    # Every counted table must exist/queryable (_count_rows reports -1 for a missing or
    # unqueryable table) — catches a structurally-incomplete / wrong restore even when no
    # baseline is supplied (the default CLI run).
    missing = sorted(table for table, count in row_counts.items() if count < 0)
    checks.append(
        IntegrityCheck(
            "core_tables_present",
            not missing,
            "all checked tables present"
            if not missing
            else "missing/unqueryable tables (wrong or incomplete restore): "
            + ", ".join(missing),
        )
    )

    shortfalls = [
        f"{table}: {row_counts.get(table, 0)} < {minimum}"
        for table, minimum in baseline.items()
        if row_counts.get(table, 0) < minimum
    ]
    counts_ok = not shortfalls
    checks.append(
        IntegrityCheck(
            "row_counts_meet_baseline",
            counts_ok,
            "all tracked tables meet baseline"
            if counts_ok
            else "below baseline (possible data loss): " + "; ".join(shortfalls),
        )
    )

    return RestoreIntegrityReport(
        ok=all(c.ok for c in checks),
        checks=checks,
        audit_chain_ok=chain_ok,
        chained_events=int(verification.total_chained),
        signing_key_is_dev=key_is_dev,
        row_counts=dict(row_counts),
    )


def _count_rows(session_factory: sessionmaker[Session], tables: tuple[str, ...]) -> dict[str, int]:
    """COUNT(*) per table; a missing/unqueryable table reports ``-1``. Table names are
    identifier-validated (they are config/CLI, never request data) before interpolation."""
    from sqlalchemy import text

    counts: dict[str, int] = {}
    with session_factory() as session:
        for table in tables:
            if not _IDENT.match(table):
                counts[table] = -1
                continue
            try:
                # nosemgrep: python.sqlalchemy.security.sqlalchemy-text-sql-expression
                value = session.execute(text(f"SELECT count(*) FROM {table}")).scalar()  # noqa: S608
                counts[table] = int(value or 0)
            except Exception:
                counts[table] = -1
    return counts


def verify_restore(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    tables: tuple[str, ...] = _DEFAULT_TABLES,
    baseline: dict[str, int] | None = None,
) -> RestoreIntegrityReport:
    """Run the full restore-integrity check against a (restored) database."""
    from . import operations_store

    verification = operations_store.verify_audit_chain(session_factory, settings=settings)
    wanted = tuple(dict.fromkeys((*tables, *(baseline or {}).keys())))
    row_counts = _count_rows(session_factory, wanted)
    return assess(verification, row_counts=row_counts, baseline=baseline)


def _parse_min_rows(value: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for part in (value or "").split(","):
        part = part.strip()
        if not part:
            continue
        key, _, raw = part.partition("=")
        out[key.strip()] = int(raw)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a restored MolTrace database's integrity (DR drill check)."
    )
    parser.add_argument(
        "--min-rows", default="", help="baseline as comma-separated table=minrows (e.g. users=1)"
    )
    parser.add_argument("--tables", default=",".join(_DEFAULT_TABLES))
    args = parser.parse_args(argv)

    try:
        baseline = _parse_min_rows(args.min_rows)
    except ValueError as exc:
        print(f"dr_verify: invalid --min-rows ({exc})", file=sys.stderr)
        return 2

    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from .settings import get_settings

        settings = get_settings()
        # Use the resolved settings URL (a bare DATABASE_URL can default to an
        # uninstalled driver — see the Render ops notes).
        engine = create_engine(settings.database_url)
        session_factory = sessionmaker(bind=engine)
    except Exception as exc:  # pragma: no cover - environment/connection failure
        print(f"dr_verify: cannot connect to the database: {exc}", file=sys.stderr)
        return 2

    tables = tuple(t.strip() for t in args.tables.split(",") if t.strip())
    report = verify_restore(session_factory, settings, tables=tables, baseline=baseline)
    for check in report.checks:
        print(f"[{'PASS' if check.ok else 'FAIL'}] {check.name}: {check.detail}")
    print(f"dr_verify: {'INTEGRITY VERIFIED' if report.ok else 'INTEGRITY CHECK FAILED'}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
