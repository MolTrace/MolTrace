"""The history export streams; it used to build itself twice in memory first.

``export_history_csv`` accumulated the whole export in a StringIO and returned
``getvalue()``, and the route then encoded that whole string — so a tenant's
entire history existed as ORM rows, as a str, AND as bytes before the first
byte reached the client. The ``StreamingResponse`` wrapping it yielded a single
chunk, so the streaming was decorative. ``limit`` defaulted to None, i.e.
unlimited, even though a supplied limit was capped at 10,000.

Inside a memory-capped Cloud Run container an OOM kill is a restart, and a
restart costs every other request on that instance a cold start.

The export format is user-facing, so the first test here is equivalence: the
streamed bytes must match what the accumulating implementation produced,
including CSV quoting of embedded commas, quotes and newlines.
"""

from __future__ import annotations

import csv
import io

from nmrcheck.analysis import analyze_inputs
from nmrcheck.database import (
    create_session_factory,
    create_user,
    export_history_csv,
    init_db,
    iter_analyses,
    save_analysis,
)
from nmrcheck.models import AnalysisInputs

_HEADER = [
    "id", "created_at", "label", "sample_id", "solvent", "smiles", "nmr_text",
    "expected_total_h", "observed_total_h", "confidence", "parsed_peak_count",
    "delta_total_h", "job_id", "notes",
]

# Values that exercise csv quoting — a naive row-at-a-time rewrite breaks here.
_AWKWARD = [
    "1H NMR (400 MHz, CDCl3) delta 3.65 (q, 2H), 1.26 (t, 3H)",
    '1H NMR (400 MHz, CDCl3) delta 7.26 (s, 1H), "quoted", 2.10 (br s, 1H)',
    "1H NMR (400 MHz, CDCl3) delta 3.65 (q, 2H)\nsecond line, with comma",
]


def _seed(tmp_path, count: int = 3):
    factory = create_session_factory(f"sqlite:///{tmp_path / 'export.sqlite3'}")
    init_db(factory)
    user = create_user(factory, email="export@example.com", password="correct-horse-1")
    for index in range(count):
        payload = AnalysisInputs(
            smiles="CCO",
            nmr_text=_AWKWARD[index % len(_AWKWARD)],
            solvent="CDCl3",
        )
        save_analysis(factory, analyze_inputs(payload), payload, user_id=user.id)
    return factory, user


def _accumulated_reference(factory, user_id: int) -> str:
    """The previous implementation, reproduced verbatim."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(_HEADER)
    for record in iter_analyses(factory, user_id=user_id):
        writer.writerow([
            record.id, record.created_at.isoformat(), record.label,
            record.sample_id or "", record.solvent or "", record.smiles,
            record.nmr_text, record.expected_total_h, record.observed_total_h,
            record.confidence, record.parsed_peak_count, record.delta_total_h,
            record.job_id or "", " | ".join(record.notes),
        ])
    return output.getvalue()


def test_streamed_export_is_byte_identical_to_the_accumulated_one(tmp_path):
    factory, user = _seed(tmp_path)
    streamed = "".join(export_history_csv(factory, user_id=user.id))
    assert streamed == _accumulated_reference(factory, user.id)


def test_quoting_survives_row_at_a_time(tmp_path):
    """Embedded commas, quotes and newlines must still parse back to one row each."""
    factory, user = _seed(tmp_path)
    rows = list(csv.reader(io.StringIO("".join(export_history_csv(factory, user_id=user.id)))))
    assert rows[0] == _HEADER
    assert len(rows) == 4  # header + 3 analyses, despite an embedded newline
    for row in rows[1:]:
        assert len(row) == len(_HEADER)


def test_the_export_is_a_generator_not_a_materialised_string(tmp_path):
    """The property that keeps memory flat: rows are produced on demand."""
    factory, user = _seed(tmp_path)
    stream = export_history_csv(factory, user_id=user.id)
    assert not isinstance(stream, str), "export_history_csv returned the whole export again"
    first = next(iter(stream))
    # The header arrives without the body having been built.
    assert first.startswith("id,created_at,")


def test_a_limit_is_honoured(tmp_path):
    factory, user = _seed(tmp_path, count=3)
    rows = list(csv.reader(io.StringIO("".join(export_history_csv(factory, limit=2, user_id=user.id)))))
    assert len(rows) == 3  # header + 2


def test_the_route_default_is_bounded():
    """A supplied limit was capped at 10,000 while the DEFAULT was unlimited —
    the guard existed and the ordinary call bypassed it."""
    from nmrcheck.api import _HISTORY_EXPORT_DEFAULT_ROWS

    assert _HISTORY_EXPORT_DEFAULT_ROWS == 10_000, (
        "the default must match the ceiling the query parameter already declares"
    )
