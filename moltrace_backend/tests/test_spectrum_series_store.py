"""B1 slice 2: the spectrum series, owner-scoped, and the rate fitted over it.

Same boundary as the impurity observations, for the same reason: points reference analyses, and
``analyses`` has no organization widening, so a series must never be reachable through a wider
lattice than the spectra it is assembled from.

The fit itself is covered by ``tests/spectroscopy/test_kinetics_rates.py``. What is pinned here is
that the store hands the engine a correctly ordered series and passes its refusal through intact
rather than degrading it into a null rate.
"""

from __future__ import annotations

import math

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from moltrace.spectroscopy.kinetics import KineticFit, KineticRefusal
from nmrcheck.orm import AnalysisORM, Base
from nmrcheck.spectrum_series_store import (
    add_series_point,
    create_spectrum_series,
    fit_series_kinetics,
    get_spectrum_series,
)

OWNER = 31
INTRUDER = 42


def _factory():
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _analysis(factory, *, user_id: int | None = OWNER) -> int:
    with factory() as session:
        row = AnalysisORM(
            user_id=user_id,
            smiles="CCO",
            nmr_text="1H NMR",
            label="pass",
            expected_total_h=6.0,
            observed_total_h=6.0,
            confidence=0.9,
            notes_json="[]",
            full_report_json="{}",
        )
        session.add(row)
        session.commit()
        return int(row.id)


def _series_with_decay(factory, *, k=0.10, n=11, user_id=OWNER):
    series = create_spectrum_series(
        factory, user_id=user_id, name="hydrolysis", tracked_quantity="product integral (H)"
    )
    for i in range(n):
        add_series_point(
            factory,
            series_id=series.id,
            elapsed_seconds=float(i),
            observed_value=100.0 * math.exp(-k * i),
            analysis_id=_analysis(factory, user_id=user_id),
            user_id=user_id,
        )
    return series


# --- the boundary ------------------------------------------------------------------------------


def test_a_series_is_invisible_to_another_user():
    factory = _factory()
    series = _series_with_decay(factory)

    assert get_spectrum_series(factory, series.id, user_id=OWNER) is not None
    assert get_spectrum_series(factory, series.id, user_id=INTRUDER) is None
    assert fit_series_kinetics(factory, series.id, user_id=INTRUDER) is None


def test_a_point_cannot_be_added_to_a_series_you_do_not_own():
    factory = _factory()
    series = _series_with_decay(factory, n=5)

    added = add_series_point(
        factory,
        series_id=series.id,
        elapsed_seconds=99.0,
        observed_value=1.0,
        analysis_id=None,
        user_id=INTRUDER,
    )
    assert added is None


def test_missing_and_not_yours_are_indistinguishable():
    factory = _factory()
    series = _series_with_decay(factory, n=5)
    assert get_spectrum_series(factory, series.id, user_id=INTRUDER) is None
    assert get_spectrum_series(factory, 987_654, user_id=INTRUDER) is None


# --- the fit -------------------------------------------------------------------------------------


def test_a_clean_decay_series_yields_its_rate_constant_with_uncertainty():
    factory = _factory()
    series = _series_with_decay(factory, k=0.10)

    result = fit_series_kinetics(factory, series.id, user_id=OWNER)

    assert isinstance(result, KineticFit)
    assert result.order == "first"
    assert abs(result.rate_constant - 0.10) < 1e-6
    assert result.standard_error is not None
    assert result.point_count == 11


def test_points_are_ordered_by_time_regardless_of_insertion_order():
    """A series assembled out of order must still fit; the store sorts, the engine does not."""
    factory = _factory()
    series = create_spectrum_series(factory, user_id=OWNER, name="s", tracked_quantity="q")
    for i in [3, 0, 4, 1, 5, 2]:
        add_series_point(
            factory,
            series_id=series.id,
            elapsed_seconds=float(i),
            observed_value=100.0 * math.exp(-0.2 * i),
            analysis_id=None,
            user_id=OWNER,
        )

    result = fit_series_kinetics(factory, series.id, user_id=OWNER)
    assert isinstance(result, KineticFit)
    assert abs(result.rate_constant - 0.2) < 1e-6


def test_a_refusal_passes_through_intact_rather_than_becoming_a_null_rate():
    """Too few points must surface as the engine's named refusal, not as an empty result."""
    factory = _factory()
    series = _series_with_decay(factory, n=3)

    result = fit_series_kinetics(factory, series.id, user_id=OWNER)

    assert isinstance(result, KineticRefusal)
    assert result.reason == "too_few_points"
    assert not hasattr(result, "rate_constant")


def test_an_empty_series_refuses_with_the_engine_vocabulary():
    factory = _factory()
    series = create_spectrum_series(factory, user_id=OWNER, name="s", tracked_quantity="q")

    result = fit_series_kinetics(factory, series.id, user_id=OWNER)

    assert isinstance(result, KineticRefusal)
    assert result.reason == "too_few_points"


# --- the migration must build the same tables the ORM does --------------------------------------


def test_migration_0042_and_the_orm_agree_on_both_tables():
    import importlib.util as _ilu
    from pathlib import Path

    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    spec = _ilu.spec_from_file_location(
        "m0042",
        str(Path(__file__).resolve().parents[1] / "alembic/versions/0042_spectrum_series.py"),
    )
    module = _ilu.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    migrated = sa.create_engine("sqlite:///:memory:")
    Base.metadata.tables["analyses"].create(migrated)
    with migrated.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            module.upgrade()

    from_orm = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(from_orm)

    for table in ("spectrum_series", "spectrum_series_points"):
        migrated_inspector = sa.inspect(migrated)
        orm_inspector = sa.inspect(from_orm)
        assert {
            c["name"]: (str(c["type"]), c["nullable"])
            for c in migrated_inspector.get_columns(table)
        } == {
            c["name"]: (str(c["type"]), c["nullable"])
            for c in orm_inspector.get_columns(table)
        }, table
        assert {i["name"] for i in migrated_inspector.get_indexes(table)} == {
            i["name"] for i in orm_inspector.get_indexes(table)
        }, table
