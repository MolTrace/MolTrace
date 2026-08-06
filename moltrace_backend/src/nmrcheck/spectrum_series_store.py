"""Persistence for spectrum series, and the rate fitted over one.

Owner-scoped by ``user_id``, matching the impurity observations and for the same reason: points
reference analyses, and ``analyses`` carries no organization widening, so a series must not be
reachable through a wider lattice than the spectra it is assembled from. ``user_id=None`` is an
unrestricted caller; missing and not-yours both return ``None`` so a route cannot leak existence.

The store's only job beyond scoping is to hand the engine a series ordered in time. It never
interprets a refusal — a :class:`KineticRefusal` is returned to the caller intact, because
collapsing it into a null rate would discard the one thing that says why no rate exists.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from moltrace.spectroscopy.kinetics import KineticFit, KineticRefusal, identify_order

from .database import session_scope
from .orm import SpectrumSeriesORM, SpectrumSeriesPointORM


@dataclass(frozen=True)
class SpectrumSeriesRecord:
    id: int
    user_id: int | None
    name: str
    tracked_quantity: str
    point_count: int


@dataclass(frozen=True)
class SpectrumSeriesPointRecord:
    id: int
    series_id: int
    analysis_id: int | None
    elapsed_seconds: float
    observed_value: float


def _readable(row: SpectrumSeriesORM | None, user_id: int | None) -> bool:
    """Not ``row.user_id in {None, user_id}`` — an orphan is not a public record."""
    if row is None:
        return False
    return user_id is None or row.user_id == user_id


def _to_record(session: Session, row: SpectrumSeriesORM) -> SpectrumSeriesRecord:
    count = len(
        session.scalars(
            select(SpectrumSeriesPointORM.id).where(
                SpectrumSeriesPointORM.series_id == row.id
            )
        ).all()
    )
    return SpectrumSeriesRecord(
        id=int(row.id),
        user_id=row.user_id,
        name=row.name,
        tracked_quantity=row.tracked_quantity,
        point_count=count,
    )


def create_spectrum_series(
    session_factory: sessionmaker[Session],
    *,
    user_id: int | None,
    name: str,
    tracked_quantity: str,
) -> SpectrumSeriesRecord:
    with session_scope(session_factory) as session:
        row = SpectrumSeriesORM(
            user_id=user_id, name=name, tracked_quantity=tracked_quantity
        )
        session.add(row)
        session.flush()
        return _to_record(session, row)


def get_spectrum_series(
    session_factory: sessionmaker[Session], series_id: int, *, user_id: int | None = None
) -> SpectrumSeriesRecord | None:
    with session_scope(session_factory) as session:
        row = session.get(SpectrumSeriesORM, series_id)
        if not _readable(row, user_id):
            return None
        assert row is not None
        return _to_record(session, row)


def add_series_point(
    session_factory: sessionmaker[Session],
    *,
    series_id: int,
    elapsed_seconds: float,
    observed_value: float,
    analysis_id: int | None = None,
    user_id: int | None = None,
) -> SpectrumSeriesPointRecord | None:
    """Append one timed observation. ``None`` when the series is absent or not the caller's."""
    with session_scope(session_factory) as session:
        series = session.get(SpectrumSeriesORM, series_id)
        if not _readable(series, user_id):
            return None
        row = SpectrumSeriesPointORM(
            series_id=series_id,
            analysis_id=analysis_id,
            elapsed_seconds=float(elapsed_seconds),
            observed_value=float(observed_value),
        )
        session.add(row)
        session.flush()
        return SpectrumSeriesPointRecord(
            id=int(row.id),
            series_id=series_id,
            analysis_id=row.analysis_id,
            elapsed_seconds=row.elapsed_seconds,
            observed_value=row.observed_value,
        )


def fit_series_kinetics(
    session_factory: sessionmaker[Session], series_id: int, *, user_id: int | None = None
) -> KineticFit | KineticRefusal | None:
    """Fit a rate over a series. ``None`` only when the series is absent or not the caller's.

    A refusal from the engine is returned as-is: it names why no rate exists, and that is
    information the caller needs, not an error to flatten.
    """
    with session_scope(session_factory) as session:
        series = session.get(SpectrumSeriesORM, series_id)
        if not _readable(series, user_id):
            return None
        points = session.scalars(
            select(SpectrumSeriesPointORM)
            .where(SpectrumSeriesPointORM.series_id == series_id)
            .order_by(SpectrumSeriesPointORM.elapsed_seconds.asc())
        ).all()

    times = [float(p.elapsed_seconds) for p in points]
    values = [float(p.observed_value) for p in points]
    return identify_order(times, values)
