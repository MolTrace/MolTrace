"""Build the frozen NMR gold set from the repo's own NMRShiftDB2 Bruker fixtures.

Joins ``tests/fixtures/nmrshiftdb2/expected/*.json`` (expert-assigned peak lists,
nucleus, provenance, archive sha256) to structures from the bundled NMReDATA
export (``tests/fixtures/nmrshiftdb2/source/nmrshiftdb2rawdata.nmredata.sd``) by
NMRShiftDB2 db id — the same join ``scripts/measure_verifier_margin.py`` uses,
molblock rather than the SMILES tag (the tag drops E/Z stereo on 129/196
records). Emits ``tests/fixtures/nmr_gold_set/gold_set_v1.json`` with the
harness checksum embedded, so :func:`moltrace.spectroscopy.eval.ci_gate.
load_gold_set` pins content integrity on every load.

Every record's ``reviewer_verdict`` is True with the proposed structure equal to
the true one: NMRShiftDB2 assignments are the expert adjudication. v1 therefore
measures confirmation of correct structures, shift MAE, calibration and latency;
it contains no decoy records, so ``false_confirmation_rate`` stays honestly
``None`` until wrong-structure records are added (Prompt 5 §11's follow-up).

Deterministic: same inputs -> byte-identical output. Rerun after adding
fixtures, and commit the diff — the rolled checksum is the change-control
record.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from build_hose_kb import _sd_records  # noqa: E402
from rdkit import Chem  # noqa: E402

from moltrace.spectroscopy.infra.contract import content_hash  # noqa: E402

_BACKEND = Path(__file__).resolve().parents[1]
_FIXTURES = _BACKEND / "tests/fixtures/nmrshiftdb2"
_OUT = _BACKEND / "tests/fixtures/nmr_gold_set/gold_set_v1.json"
_DIR_NAME = re.compile(r"nmrshiftdb2_(\d+)_(1h|13c)_bruker", re.IGNORECASE)
_NUCLEUS = {"1h": "1H", "13c": "13C"}


_SPECTRUM_ID = re.compile(r"spectrumid=(\d+)")


def _structure_indexes() -> tuple[dict[str, str], dict[str, str]]:
    """(by_db_id, by_spectrum_id) -> molblock — the measure_verifier_margin join."""

    by_db: dict[str, str] = {}
    by_spectrum: dict[str, str] = {}
    for molblock, props in _sd_records(_FIXTURES / "source/nmrshiftdb2rawdata.nmredata.sd"):
        lines = molblock.split("\n")
        db_id = lines[2].split()[-1] if len(lines) > 2 and lines[2].strip() else ""
        if db_id:
            by_db.setdefault(db_id, molblock)
        for rows in props.values():
            for row in rows:
                for match in _SPECTRUM_ID.finditer(row):
                    by_spectrum.setdefault(match.group(1), molblock)
    return by_db, by_spectrum


def _record_from(
    meta: dict[str, Any],
    identifier: str,
    molblock: str | None,
    skipped: list[str],
) -> dict[str, Any] | None:
    nucleus = _NUCLEUS.get(str(meta.get("nucleus", "")).lower())
    peaks = meta.get("expected_peak_ppm") or meta.get("reference_peak_ppm") or []
    extracted = meta.get("extracted_path", "")
    if not (nucleus and peaks and extracted and molblock):
        skipped.append(identifier)
        return None
    mol = Chem.MolFromMolBlock(molblock)
    if mol is None:
        skipped.append(f"{identifier} (molblock unparseable)")
        return None
    smiles = Chem.MolToSmiles(mol)
    inchikey = Chem.MolToInchiKey(mol)
    return {
        "identifier": identifier,
        "source": "nmrshiftdb2",
        "true_inchikey": inchikey,
        "proposed_inchikey": inchikey,
        "reviewer_verdict": True,
        "reference_shifts": {nucleus: [float(p) for p in peaks]},
        "spectrum": {
            "fixture_dir": extracted,
            "archive_sha256": meta.get("archive_sha256"),
            "nucleus": nucleus,
            "field_mhz": meta.get("field_mhz"),
            "proposed_smiles": smiles,
        },
    }


def main() -> int:
    by_db, by_spectrum = _structure_indexes()
    records: list[dict[str, Any]] = []
    skipped: list[str] = []
    seen_dirs: set[str] = set()

    for expected_path in sorted((_FIXTURES / "expected").glob("nmrshiftdb2_*_bruker.json")):
        meta = json.loads(expected_path.read_text(encoding="utf-8"))
        molblock = by_db.get(str(meta.get("db_id", ""))) or by_spectrum.get(
            str(meta.get("spectrum_id", ""))
        )
        record = _record_from(meta, expected_path.stem, molblock, skipped)
        if record is not None:
            seen_dirs.add(record["spectrum"]["fixture_dir"])
            records.append(record)

    batch_path = _FIXTURES / "expected/nmrshiftdb2_bruker_20.json"
    if batch_path.exists():
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        for meta in batch.get("fixtures", []):
            extracted = meta.get("extracted_path", "")
            if extracted in seen_dirs:
                continue  # the per-fixture files above take precedence
            match = _DIR_NAME.search(extracted)
            identifier = match.group(0).lower() if match else str(meta.get("spectrum_id", ""))
            molblock = by_spectrum.get(str(meta.get("spectrum_id", "")))
            record = _record_from(meta, identifier, molblock, skipped)
            if record is not None:
                seen_dirs.add(extracted)
                records.append(record)

    records.sort(key=lambda r: r["identifier"])
    name = "nmr_gold_set_v1_regression_sentinel"
    # Mirror GoldSet.checksum(): content_hash over the harness's _content() view.
    ordered = [
        {
            "identifier": r["identifier"],
            "source": r["source"],
            "true_inchikey": r["true_inchikey"],
            "proposed_inchikey": r["proposed_inchikey"],
            "reviewer_verdict": r["reviewer_verdict"],
            "reference_shifts": {k: list(v) for k, v in sorted(r["reference_shifts"].items())},
            "spectrum": r["spectrum"],
        }
        for r in records
    ]
    payload = {
        "name": name,
        "note": (
            "Regression sentinel over the repo's real NMRShiftDB2 Bruker fixtures — NOT a "
            "held-out accuracy claim (several molecules are in the shipped KB's training "
            "data; held-out numbers come from eval/shift_accuracy.py). No decoy records "
            "yet, so false_confirmation_rate is unmeasured rather than perfect."
        ),
        "record_count": len(records),
        "checksum": content_hash({"name": name, "records": ordered}),
        "records": records,
    }
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"{len(records)} records -> {_OUT}")
    print(f"checksum {payload['checksum']}")
    for item in skipped:
        print(f"skipped: {item}", file=sys.stderr)
    return 0 if records else 1


if __name__ == "__main__":
    raise SystemExit(main())
