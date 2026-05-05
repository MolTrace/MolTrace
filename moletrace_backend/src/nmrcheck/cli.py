from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analysis import analyze_nmr_text
from .database import create_session_factory, init_db
from .settings import get_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze a 1H NMR text peak list against a SMILES string.")
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("reset-dev-db", help="Reset and initialize the local SQLite development database.")
    parser.add_argument("--smiles", help="SMILES representation of the molecule")
    parser.add_argument("--nmr", help="1H NMR peak text, e.g. '7.26 (m, 5H), 3.65 (q, 2H)'")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the JSON report")
    return parser


def reset_dev_db() -> None:
    settings = get_settings()
    db_url = settings.database_url
    if not db_url.startswith("sqlite:///"):
        raise SystemExit("reset-dev-db is only available for local SQLite database URLs.")

    db_path = Path(db_url.replace("sqlite:///", "", 1))
    if db_path.exists():
        db_path.unlink()
        print(f"Removed development database at {db_path}")
    else:
        print(f"No existing development database found at {db_path}")

    session_factory = create_session_factory(db_url)
    init_db(session_factory)
    print("Initialized fresh development database.")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "reset-dev-db":
        reset_dev_db()
        return
    if not args.smiles or not args.nmr:
        parser.error("--smiles and --nmr are required unless a subcommand is used.")
    report = analyze_nmr_text(smiles=args.smiles, nmr_text=args.nmr)
    if args.pretty:
        print(json.dumps(report.model_dump(), indent=2))
    else:
        print(report.model_dump_json())


if __name__ == "__main__":
    main()
