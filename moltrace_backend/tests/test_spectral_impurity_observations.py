"""B2b slice 2: the spectral impurity observation is scoped by the ANALYSIS owner.

The scoping choice is the whole security story here. A reaction project widens to active
organization members (`reaction_access.project_scope_predicate` grants
``owner_id == caller OR organization_id IN active_orgs``), but ``analyses`` has no organization
column at all. So if these rows were scoped by the reaction project, a campaign teammate could
read the compound name and chemical shift out of a spectrum whose analysis they provably cannot
open — verbatim spectral content, leaked across a boundary the analysis side never widened.

These tests pin that boundary, plus the two adjacent traps found in neighbouring code: a
NULL-owner row must not become visible to everyone, and "missing" must be indistinguishable from
"not yours".
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from nmrcheck.orm import AnalysisORM, Base, SpectralImpurityObservationORM
from nmrcheck.spectral_impurity_observations_store import (
    get_spectral_impurity_observation,
    list_spectral_impurity_observations,
    record_spectral_impurity_observation,
)

OWNER = 11
INTRUDER = 22


def _factory():
    engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _analysis(factory, *, user_id: int | None) -> int:
    with factory() as session:
        row = AnalysisORM(
            user_id=user_id,
            smiles="CCO",
            nmr_text="1H NMR (CDCl3): 2.05 (s, 3H)",
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


# --- the boundary ------------------------------------------------------------------------------


def test_an_observation_is_invisible_to_someone_who_does_not_own_the_analysis():
    factory = _factory()
    analysis_id = _analysis(factory, user_id=OWNER)
    record = record_spectral_impurity_observation(
        factory, analysis_id=analysis_id, nucleus="1H", shift_ppm=2.05, solvent="CDCl3"
    )
    assert record is not None

    assert get_spectral_impurity_observation(factory, record.id, user_id=OWNER) is not None
    assert get_spectral_impurity_observation(factory, record.id, user_id=INTRUDER) is None
    assert list_spectral_impurity_observations(factory, user_id=INTRUDER) == []


def test_missing_and_not_yours_are_indistinguishable():
    """Both return None, so the route's 404 cannot leak existence."""
    factory = _factory()
    analysis_id = _analysis(factory, user_id=OWNER)
    record = record_spectral_impurity_observation(
        factory, analysis_id=analysis_id, nucleus="1H", shift_ppm=2.05, solvent="CDCl3"
    )
    assert record is not None

    not_yours = get_spectral_impurity_observation(factory, record.id, user_id=INTRUDER)
    never_existed = get_spectral_impurity_observation(factory, 999_999, user_id=INTRUDER)
    assert not_yours is never_existed is None


def test_a_null_owner_row_is_not_visible_to_every_caller():
    """The trap next door: `if row.user_id in {None, user_id}` makes orphans world-readable.

    `analyses.user_id` is nullable, so an orphaned analysis is a real state, not a hypothetical.
    """
    factory = _factory()
    analysis_id = _analysis(factory, user_id=None)
    record = record_spectral_impurity_observation(
        factory, analysis_id=analysis_id, nucleus="1H", shift_ppm=2.05, solvent="CDCl3"
    )
    assert record is not None

    assert get_spectral_impurity_observation(factory, record.id, user_id=OWNER) is None
    assert list_spectral_impurity_observations(factory, user_id=OWNER) == []
    # An unrestricted caller (system key) still sees it.
    assert get_spectral_impurity_observation(factory, record.id, user_id=None) is not None


def test_recording_against_an_analysis_you_do_not_own_is_refused():
    factory = _factory()
    analysis_id = _analysis(factory, user_id=OWNER)

    refused = record_spectral_impurity_observation(
        factory,
        analysis_id=analysis_id,
        nucleus="1H",
        shift_ppm=2.05,
        solvent="CDCl3",
        user_id=INTRUDER,
    )
    assert refused is None
    with factory() as session:
        assert session.query(SpectralImpurityObservationORM).count() == 0


def test_reaction_project_id_is_recorded_but_never_authorizes():
    """Provenance, not permission: it must not widen who can read the row."""
    factory = _factory()
    analysis_id = _analysis(factory, user_id=OWNER)
    record = record_spectral_impurity_observation(
        factory,
        analysis_id=analysis_id,
        nucleus="1H",
        shift_ppm=2.05,
        solvent="CDCl3",
        reaction_project_id=77,
    )
    assert record is not None and record.reaction_project_id == 77
    assert get_spectral_impurity_observation(factory, record.id, user_id=INTRUDER) is None


# --- the record carries the resolution, refusals included ---------------------------------------


def test_a_resolved_observation_persists_its_limit_and_provenance():
    factory = _factory()
    analysis_id = _analysis(factory, user_id=OWNER)
    record = record_spectral_impurity_observation(
        factory, analysis_id=analysis_id, nucleus="1H", shift_ppm=2.05, solvent="CDCl3"
    )

    assert record is not None
    assert record.compound == "ethyl acetate"
    assert record.identity_status == "resolved"
    assert record.q3c_class_number == 3
    assert record.concentration_limit_ppm == 5000.0
    assert record.rule_set_version is not None and record.rule_set_version.startswith("sha256:")
    assert record.human_review_required is True
    # A limit is not a measurement.
    assert record.quantitation_available is False
    assert record.observed_level_ppm is None
    assert "not quantitated" in record.compliance_note.lower()


def test_a_refusal_is_storable_with_every_regulatory_column_null():
    """Forcing NOT NULL on rule_set_version would make all three refusal branches unstorable."""
    factory = _factory()
    analysis_id = _analysis(factory, user_id=OWNER)
    record = record_spectral_impurity_observation(
        factory, analysis_id=analysis_id, nucleus="1H", shift_ppm=0.86, solvent="CDCl3"
    )

    assert record is not None
    assert record.identity_status == "unresolved"
    assert record.unresolved_reason == "not_in_q3c_subset"
    assert record.compound == "grease"
    assert record.rule_set_version is None
    assert record.concentration_limit_ppm is None
    assert record.q3c_class_number is None
    assert record.unresolved_detail is not None


def test_recording_against_a_missing_analysis_returns_none():
    factory = _factory()
    assert (
        record_spectral_impurity_observation(
            factory, analysis_id=424_242, nucleus="1H", shift_ppm=2.05, solvent="CDCl3"
        )
        is None
    )


# --- the migration must build the same table the ORM does ---------------------------------------


def test_migration_0041_and_the_orm_agree_on_the_schema():
    """Alembic migrations are Postgres deltas over an ORM-created schema — they cannot bootstrap.

    Tests build via ``create_all`` and production arrives via Alembic, so the two paths must land
    on the same table. Drift here is invisible until a production column is missing.
    """
    import importlib.util as _ilu
    from pathlib import Path

    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    table = SpectralImpurityObservationORM.__tablename__

    spec = _ilu.spec_from_file_location(
        "m0041",
        str(
            Path(__file__).resolve().parents[1]
            / "alembic/versions/0041_spectral_impurity_observations.py"
        ),
    )
    module = _ilu.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    migrated = sa.create_engine("sqlite:///:memory:")
    # The FK parents must exist before the table that references them.
    Base.metadata.tables["analyses"].create(migrated)
    Base.metadata.tables["reaction_projects"].create(migrated)
    with migrated.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            module.upgrade()

    from_orm = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(from_orm)

    def shape(engine):
        inspector = sa.inspect(engine)
        return (
            {c["name"]: (str(c["type"]), c["nullable"]) for c in inspector.get_columns(table)},
            {i["name"] for i in inspector.get_indexes(table)},
        )

    migrated_columns, migrated_indexes = shape(migrated)
    orm_columns, orm_indexes = shape(from_orm)

    assert migrated_columns == orm_columns
    assert migrated_indexes == orm_indexes
    # The refusal branches depend on these staying nullable.
    for column in ("rule_set_version", "concentration_limit_ppm", "q3c_class_number"):
        assert migrated_columns[column][1] is True, f"{column} must stay nullable"
