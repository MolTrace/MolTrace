from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from pydantic import ValidationError

from .exceptions import PeakParseError
from .models import AnalysisInputs, BatchAnalysisInputs
from .settings import get_settings


class UploadParseError(PeakParseError):
    """Raised when an uploaded batch file cannot be parsed."""


ALIASES = {
    "sample_id": {"sample_id", "sample id", "sample", "id", "name"},
    "smiles": {"smiles", "structure", "smile"},
    "nmr_text": {"nmr_text", "nmr text", "1h nmr", "1h nmr text", "proton nmr", "hnmr", "1h_nmr_text"},
    "solvent": {"solvent", "nmr solvent", "medium"},
}


def _allowed_upload_suffixes() -> set[str]:
    return {f".{suffix}" for suffix in get_settings().allowed_upload_types}


def _normalize_header(name: str | None) -> str:
    if not name:
        return ""
    return " ".join(str(name).strip().lower().replace("_", " ").split())


def _canonical_key(name: str | None) -> str | None:
    normalized = _normalize_header(name)
    for canonical, aliases in ALIASES.items():
        if normalized in aliases:
            return canonical
    return None


def _normalize_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized_rows: list[dict[str, str]] = []
    for row in rows:
        mapped: dict[str, str] = {}
        for key, value in row.items():
            canonical = _canonical_key(key)
            if canonical is None:
                continue
            mapped[canonical] = value
        normalized_rows.append(mapped)
    return normalized_rows


def parse_batch_upload(filename: str, content: bytes) -> BatchAnalysisInputs:
    suffix = Path(filename).suffix.lower()
    allowed_upload_suffixes = _allowed_upload_suffixes()
    if suffix not in allowed_upload_suffixes:
        supported = ", ".join(sorted(allowed_upload_suffixes))
        raise UploadParseError(f"Only {supported} batch uploads are supported.")

    try:
        if suffix == ".json":
            payload = json.loads(content.decode("utf-8"))
            if isinstance(payload, list):
                payload = {"items": payload}
            batch_payload = BatchAnalysisInputs.model_validate(payload)
        else:
            text = content.decode("utf-8-sig")
            rows = list(csv.DictReader(io.StringIO(text)))
            if not rows:
                raise UploadParseError("Uploaded CSV file contains no rows.")
            rows = _normalize_rows(rows)
            if not all((row.get("smiles") or "").strip() and (row.get("nmr_text") or "").strip() for row in rows):
                raise UploadParseError(
                    "CSV batch uploads must include recognizable SMILES and 1H NMR text columns. Accepted headers include 'smiles', 'sample_id', 'nmr_text', '1H NMR text', and 'solvent'."
                )
            items = [
                AnalysisInputs(
                    sample_id=(row.get("sample_id") or None),
                    smiles=(row.get("smiles") or "").strip(),
                    nmr_text=(row.get("nmr_text") or "").strip(),
                    solvent=(row.get("solvent") or None),
                )
                for row in rows
            ]
            batch_payload = BatchAnalysisInputs(items=items)

        max_batch_size = get_settings().max_batch_size
        if len(batch_payload.items) > max_batch_size:
            raise UploadParseError(
                f"Uploaded batch contains {len(batch_payload.items)} records, which exceeds MAX_BATCH_SIZE={max_batch_size}."
            )
        return batch_payload
    except UnicodeDecodeError as exc:
        raise UploadParseError("Uploaded file must be UTF-8 encoded.") from exc
    except json.JSONDecodeError as exc:
        raise UploadParseError("Uploaded JSON batch file is not valid JSON.") from exc
    except ValidationError as exc:
        raise UploadParseError(f"Uploaded batch data failed validation: {exc.errors()}") from exc
