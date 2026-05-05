from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .database import session_scope
from .models import (
    CompoundAlias,
    CompoundAliasCreate,
    CompoundBatch,
    CompoundBatchCreate,
    CompoundBatchUpdate,
    CompoundEntity,
    CompoundEntityCreate,
    CompoundEntityUpdate,
    CompoundEvidenceLink,
    CompoundEvidenceLinkCreate,
    CompoundRegistryLinkRequest,
    CompoundRegistryLinkResponse,
    CompoundRegistrySearchRequest,
    CompoundRegistrySearchResult,
    CompoundRelationship,
    CompoundRelationshipCreate,
    CompoundStructureRecord,
    CompoundStructureRecordCreate,
    SampleAliquot,
    SampleAliquotCreate,
    ScientificKnowledgeGraph,
    ScientificKnowledgeGraphEdge,
    ScientificKnowledgeGraphEdgeCreate,
    ScientificKnowledgeGraphNode,
)
from .orm import (
    CompoundAliasORM,
    CompoundBatchORM,
    CompoundEntityORM,
    CompoundEvidenceLinkORM,
    CompoundRelationshipORM,
    CompoundStructureRecordORM,
    RegulatoryDossierORM,
    ReportORM,
    ReactionExperimentORM,
    ReactionProjectORM,
    SampleAliquotORM,
    ScientificKnowledgeGraphEdgeORM,
    SpectraCheckEvidenceRecordORM,
    SpectraCheckReviewDecisionORM,
    SpectraCheckSessionORM,
    utcnow,
)


class CompoundRegistryError(ValueError):
    pass


class CompoundRegistryNotFoundError(CompoundRegistryError):
    pass


class CompoundRegistryValidationError(CompoundRegistryError):
    pass


@dataclass(frozen=True)
class DerivedStructureMetadata:
    canonical_smiles: str | None = None
    inchi: str | None = None
    inchikey: str | None = None
    formula: str | None = None
    exact_mass: float | None = None
    validation_status: str = "not_checked"
    warnings: tuple[str, ...] = ()


def _json_dump(value: Any, *, default: Any) -> str:
    return json.dumps(default if value is None else value, sort_keys=True, separators=(",", ":"))


def _json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        return [str(item) for item in parsed if str(item).strip()]
    return []


def _resource_id(value: str | int | None) -> str | int:
    if value is None:
        return ""
    if isinstance(value, int):
        return value
    text = str(value)
    return int(text) if text.isdigit() else text


def _resource_id_text(value: str | int) -> str:
    return str(value)


def _load_rdkit() -> tuple[Any | None, Any | None, Any | None, str | None]:
    try:
        from rdkit import Chem
        from rdkit.Chem import rdMolDescriptors
        from rdkit.Chem import inchi as rd_inchi
    except Exception as exc:  # pragma: no cover - depends on optional chemistry runtime.
        return None, None, None, str(exc)
    return Chem, rdMolDescriptors, rd_inchi, None


def _mol_from_structure(Chem: Any, rd_inchi: Any, structure_input: str, structure_format: str) -> Any | None:
    if structure_format == "smiles":
        return Chem.MolFromSmiles(structure_input)
    if structure_format == "mol":
        return Chem.MolFromMolBlock(structure_input, sanitize=True)
    if structure_format == "sdf":
        first_record = structure_input.split("$$$$", 1)[0]
        return Chem.MolFromMolBlock(first_record, sanitize=True)
    if structure_format == "inchi":
        if hasattr(Chem, "MolFromInchi"):
            return Chem.MolFromInchi(structure_input)
        if hasattr(rd_inchi, "MolFromInchi"):
            return rd_inchi.MolFromInchi(structure_input)
    return None


def derive_structure_metadata(
    structure_input: str | None,
    structure_format: str | None,
) -> DerivedStructureMetadata:
    if structure_input is None or structure_input == "":
        return DerivedStructureMetadata(
            validation_status="not_checked",
            warnings=(
                "No structure input was submitted; structure metadata needs review.",
            ),
        )
    structure_format = structure_format or "unknown"
    if structure_format in {"name_only", "unknown"}:
        return DerivedStructureMetadata(
            validation_status="ambiguous" if structure_format == "name_only" else "not_checked",
            warnings=(
                "Structure input was preserved, but canonical representation derived was not attempted for this format.",
            ),
        )
    Chem, rdMolDescriptors, rd_inchi, import_error = _load_rdkit()
    if Chem is None or rdMolDescriptors is None or rd_inchi is None:
        return DerivedStructureMetadata(
            validation_status="not_checked",
            warnings=(
                "Chemistry toolkit unavailable; original structure input preserved and canonical representation derived was not produced.",
                f"Toolkit import warning: {import_error}",
            ),
        )
    try:
        mol = _mol_from_structure(Chem, rd_inchi, structure_input, structure_format)
    except Exception as exc:
        return DerivedStructureMetadata(
            validation_status="invalid",
            warnings=(
                "Structure parsing failed; original structure input preserved and marked needs review.",
                str(exc),
            ),
        )
    if mol is None:
        return DerivedStructureMetadata(
            validation_status="invalid",
            warnings=(
                "Structure parsing failed; original structure input preserved and marked needs review.",
            ),
        )
    warnings = ["canonical representation derived as structure metadata; original structure input preserved."]
    try:
        canonical_smiles = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
    except Exception as exc:
        canonical_smiles = None
        warnings.append(f"Canonical SMILES metadata could not be derived: {exc}")
    if canonical_smiles and structure_format == "smiles" and canonical_smiles != structure_input:
        warnings.append(
            "Canonical representation derived differs from submitted structure notation; original structure input preserved."
        )
    try:
        formula = rdMolDescriptors.CalcMolFormula(mol)
    except Exception as exc:
        formula = None
        warnings.append(f"Molecular formula structure metadata could not be derived: {exc}")
    try:
        exact_mass = round(float(rdMolDescriptors.CalcExactMolWt(mol)), 6)
    except Exception as exc:
        exact_mass = None
        warnings.append(f"Exact mass structure metadata could not be derived: {exc}")
    try:
        inchi_value = rd_inchi.MolToInchi(mol)
        inchikey = rd_inchi.InchiToInchiKey(inchi_value) if inchi_value else None
    except Exception as exc:
        inchi_value = None
        inchikey = None
        warnings.append(f"InChI/InChIKey structure metadata could not be derived: {exc}")
    return DerivedStructureMetadata(
        canonical_smiles=canonical_smiles,
        inchi=inchi_value,
        inchikey=inchikey,
        formula=formula,
        exact_mass=exact_mass,
        validation_status="valid",
        warnings=tuple(warnings),
    )


def _metadata_with_structure(
    metadata: dict[str, Any] | None,
    derived: DerivedStructureMetadata,
) -> dict[str, Any]:
    output = dict(metadata or {})
    output["structure_metadata"] = {
        "canonical_representation_derived": bool(derived.canonical_smiles),
        "validation_status": derived.validation_status,
        "normalization_warnings_json": list(derived.warnings),
    }
    if derived.warnings:
        existing_warnings = output.get("warnings")
        warnings = list(existing_warnings) if isinstance(existing_warnings, list) else []
        for warning in derived.warnings:
            if warning not in warnings:
                warnings.append(warning)
        output["warnings"] = warnings
    return output


def _row_warnings(row: Any) -> list[str]:
    metadata = _json_dict(getattr(row, "metadata_json", None))
    warnings = metadata.get("warnings")
    return [str(item) for item in warnings] if isinstance(warnings, list) else []


def _compound_to_record(row: CompoundEntityORM) -> CompoundEntity:
    return CompoundEntity(
        id=row.id,
        preferred_name=row.preferred_name,
        registry_id=row.registry_id,
        compound_type=row.compound_type,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        original_structure_input=row.original_structure_input,
        original_structure_format=row.original_structure_format,  # type: ignore[arg-type]
        canonical_smiles=row.canonical_smiles,
        inchi=row.inchi,
        inchikey=row.inchikey,
        molecular_formula=row.molecular_formula,
        exact_mass=row.exact_mass,
        stereochemistry_status=row.stereochemistry_status,  # type: ignore[arg-type]
        salt_solvent_status=row.salt_solvent_status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=_row_warnings(row),
        notes=[
            "Compound registry stores linked compound records and derived structure metadata only.",
            "Canonical representation derived does not replace the original structure input.",
        ],
    )


def _structure_to_record(row: CompoundStructureRecordORM) -> CompoundStructureRecord:
    return CompoundStructureRecord(
        id=row.id,
        compound_id=row.compound_id,
        structure_input=row.structure_input,
        structure_format=row.structure_format,  # type: ignore[arg-type]
        canonical_smiles=row.canonical_smiles,
        inchi=row.inchi,
        inchikey=row.inchikey,
        formula=row.formula,
        exact_mass=row.exact_mass,
        source=row.source,  # type: ignore[arg-type]
        normalization_warnings_json=_json_list(row.normalization_warnings_json),
        validation_status=row.validation_status,  # type: ignore[arg-type]
        reviewer_status=row.reviewer_status,  # type: ignore[arg-type]
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _alias_to_record(row: CompoundAliasORM) -> CompoundAlias:
    return CompoundAlias(
        id=row.id,
        compound_id=row.compound_id,
        alias=row.alias,
        alias_type=row.alias_type,  # type: ignore[arg-type]
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _batch_to_record(row: CompoundBatchORM) -> CompoundBatch:
    return CompoundBatch(
        id=row.id,
        compound_id=row.compound_id,
        batch_code=row.batch_code,
        lot_code=row.lot_code,
        source_type=row.source_type,  # type: ignore[arg-type]
        reaction_experiment_id=row.reaction_experiment_id,
        spectracheck_session_id=row.spectracheck_session_id,
        regulatory_dossier_id=row.regulatory_dossier_id,
        amount=row.amount,
        amount_unit=row.amount_unit,
        purity_percent=row.purity_percent,
        purity_method=row.purity_method,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=_row_warnings(row),
        notes=["Batch records link material history to compounds without overclaiming identity."],
    )


def _aliquot_to_record(row: SampleAliquotORM) -> SampleAliquot:
    return SampleAliquot(
        id=row.id,
        batch_id=row.batch_id,
        sample_id=row.sample_id,
        aliquot_code=row.aliquot_code,
        amount=row.amount,
        amount_unit=row.amount_unit,
        storage_location=row.storage_location,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _relationship_to_record(row: CompoundRelationshipORM) -> CompoundRelationship:
    return CompoundRelationship(
        id=row.id,
        source_compound_id=row.source_compound_id,
        target_compound_id=row.target_compound_id,
        relationship_type=row.relationship_type,  # type: ignore[arg-type]
        confidence_label=row.confidence_label,  # type: ignore[arg-type]
        evidence_summary_json=_json_dict(row.evidence_summary_json),
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=_row_warnings(row),
        notes=["Compound relationships are candidate relationships until reviewed."],
    )


def _evidence_link_to_record(row: CompoundEvidenceLinkORM) -> CompoundEvidenceLink:
    return CompoundEvidenceLink(
        id=row.id,
        compound_id=row.compound_id,
        batch_id=row.batch_id,
        sample_id=row.sample_id,
        resource_type=row.resource_type,  # type: ignore[arg-type]
        resource_id=_resource_id(row.resource_id),
        title=row.title,
        summary=row.summary,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
        warnings=_row_warnings(row),
        notes=["Evidence links record a linked compound context and may need review."],
    )


def _graph_edge_to_record(row: ScientificKnowledgeGraphEdgeORM) -> ScientificKnowledgeGraphEdge:
    return ScientificKnowledgeGraphEdge(
        id=row.id,
        source_type=row.source_type,
        source_id=_resource_id(row.source_id),
        target_type=row.target_type,
        target_id=_resource_id(row.target_id),
        relation_type=row.relation_type,
        label=row.label,
        confidence_label=row.confidence_label,  # type: ignore[arg-type]
        evidence_link_id=row.evidence_link_id,
        created_at=row.created_at,
        metadata_json=_json_dict(row.metadata_json),
    )


def _require_compound(session: Session, compound_id: int) -> CompoundEntityORM:
    row = session.get(CompoundEntityORM, compound_id)
    if row is None:
        raise CompoundRegistryNotFoundError("Compound not found.")
    return row


def _require_batch(session: Session, batch_id: int) -> CompoundBatchORM:
    row = session.get(CompoundBatchORM, batch_id)
    if row is None:
        raise CompoundRegistryNotFoundError("Compound batch not found.")
    return row


def _require_resource(session: Session, resource_type: str, resource_id: str | int) -> None:
    orm_map: dict[str, type[Any]] = {
        "spectracheck_session": SpectraCheckSessionORM,
        "evidence_item": SpectraCheckEvidenceRecordORM,
        "reaction_experiment": ReactionExperimentORM,
        "reaction_project": ReactionProjectORM,
        "regulatory_dossier": RegulatoryDossierORM,
        "report": ReportORM,
        "review_decision": SpectraCheckReviewDecisionORM,
    }
    orm_cls = orm_map.get(resource_type)
    if orm_cls is None:
        return
    try:
        numeric_id = int(resource_id)
    except (TypeError, ValueError) as exc:
        raise CompoundRegistryValidationError(f"{resource_type} resource_id must be numeric.") from exc
    if session.get(orm_cls, numeric_id) is None:
        raise CompoundRegistryNotFoundError(f"{resource_type} resource not found.")


def create_compound(
    session_factory: sessionmaker[Session],
    payload: CompoundEntityCreate,
) -> CompoundEntity:
    structure_format = payload.original_structure_format
    if payload.original_structure_input is not None and structure_format is None:
        structure_format = "unknown"
    derived = derive_structure_metadata(payload.original_structure_input, structure_format)
    metadata = _metadata_with_structure(payload.metadata_json, derived)
    with session_scope(session_factory) as session:
        row = CompoundEntityORM(
            preferred_name=payload.preferred_name,
            registry_id=payload.registry_id,
            compound_type=payload.compound_type,
            status=payload.status,
            original_structure_input=payload.original_structure_input,
            original_structure_format=structure_format,
            canonical_smiles=derived.canonical_smiles,
            inchi=derived.inchi,
            inchikey=derived.inchikey,
            molecular_formula=derived.formula,
            exact_mass=derived.exact_mass,
            stereochemistry_status=payload.stereochemistry_status,
            salt_solvent_status=payload.salt_solvent_status,
            metadata_json=_json_dump(metadata, default={}),
        )
        session.add(row)
        session.flush()
        if payload.original_structure_input is not None:
            structure_row = CompoundStructureRecordORM(
                compound_id=row.id,
                structure_input=payload.original_structure_input,
                structure_format=structure_format or "unknown",
                canonical_smiles=derived.canonical_smiles,
                inchi=derived.inchi,
                inchikey=derived.inchikey,
                formula=derived.formula,
                exact_mass=derived.exact_mass,
                source="user_entered",
                normalization_warnings_json=_json_dump(list(derived.warnings), default=[]),
                validation_status=derived.validation_status,
                reviewer_status="unreviewed",
                metadata_json=_json_dump({"created_from_compound": True}, default={}),
            )
            session.add(structure_row)
        session.flush()
        session.refresh(row)
        return _compound_to_record(row)


def list_compounds(
    session_factory: sessionmaker[Session],
    *,
    q: str | None = None,
    status: str | None = None,
    compound_type: str | None = None,
    limit: int = 100,
) -> list[CompoundEntity]:
    with session_scope(session_factory) as session:
        stmt = select(CompoundEntityORM).order_by(CompoundEntityORM.updated_at.desc(), CompoundEntityORM.id.desc())
        if q:
            pattern = f"%{q}%"
            alias_ids = select(CompoundAliasORM.compound_id).where(CompoundAliasORM.alias.ilike(pattern))
            stmt = stmt.where(
                or_(
                    CompoundEntityORM.preferred_name.ilike(pattern),
                    CompoundEntityORM.registry_id.ilike(pattern),
                    CompoundEntityORM.inchikey.ilike(pattern),
                    CompoundEntityORM.molecular_formula.ilike(pattern),
                    CompoundEntityORM.id.in_(alias_ids),
                )
            )
        if status:
            stmt = stmt.where(CompoundEntityORM.status == status)
        if compound_type:
            stmt = stmt.where(CompoundEntityORM.compound_type == compound_type)
        rows = session.scalars(stmt.limit(limit)).all()
        return [_compound_to_record(row) for row in rows]


def get_compound(session_factory: sessionmaker[Session], compound_id: int) -> CompoundEntity | None:
    with session_scope(session_factory) as session:
        row = session.get(CompoundEntityORM, compound_id)
        return _compound_to_record(row) if row is not None else None


def update_compound(
    session_factory: sessionmaker[Session],
    compound_id: int,
    payload: CompoundEntityUpdate,
) -> CompoundEntity | None:
    with session_scope(session_factory) as session:
        row = session.get(CompoundEntityORM, compound_id)
        if row is None:
            return None
        fields = payload.model_fields_set
        if "preferred_name" in fields:
            row.preferred_name = payload.preferred_name
        if "registry_id" in fields:
            row.registry_id = payload.registry_id
        if "compound_type" in fields and payload.compound_type is not None:
            row.compound_type = payload.compound_type
        if "status" in fields and payload.status is not None:
            row.status = payload.status
        if "stereochemistry_status" in fields and payload.stereochemistry_status is not None:
            row.stereochemistry_status = payload.stereochemistry_status
        if "salt_solvent_status" in fields and payload.salt_solvent_status is not None:
            row.salt_solvent_status = payload.salt_solvent_status
        metadata = _json_dict(row.metadata_json)
        if "metadata_json" in fields and payload.metadata_json is not None:
            metadata = dict(payload.metadata_json)
        if "original_structure_input" in fields or "original_structure_format" in fields:
            structure_input = payload.original_structure_input if "original_structure_input" in fields else row.original_structure_input
            structure_format = (
                payload.original_structure_format
                if "original_structure_format" in fields
                else row.original_structure_format
            )
            if structure_input is not None and structure_format is None:
                structure_format = "unknown"
            derived = derive_structure_metadata(structure_input, structure_format)
            row.original_structure_input = structure_input
            row.original_structure_format = structure_format
            row.canonical_smiles = derived.canonical_smiles
            row.inchi = derived.inchi
            row.inchikey = derived.inchikey
            row.molecular_formula = derived.formula
            row.exact_mass = derived.exact_mass
            metadata = _metadata_with_structure(metadata, derived)
            if "original_structure_input" in fields and structure_input is not None:
                session.add(
                    CompoundStructureRecordORM(
                        compound_id=row.id,
                        structure_input=structure_input,
                        structure_format=structure_format or "unknown",
                        canonical_smiles=derived.canonical_smiles,
                        inchi=derived.inchi,
                        inchikey=derived.inchikey,
                        formula=derived.formula,
                        exact_mass=derived.exact_mass,
                        source="user_entered",
                        normalization_warnings_json=_json_dump(list(derived.warnings), default=[]),
                        validation_status=derived.validation_status,
                        reviewer_status="unreviewed",
                        metadata_json=_json_dump({"created_from_compound_patch": True}, default={}),
                    )
                )
        row.metadata_json = _json_dump(metadata, default={})
        row.updated_at = utcnow()
        session.flush()
        session.refresh(row)
        return _compound_to_record(row)


def create_structure_record(
    session_factory: sessionmaker[Session],
    compound_id: int,
    payload: CompoundStructureRecordCreate,
) -> CompoundStructureRecord:
    derived = derive_structure_metadata(payload.structure_input, payload.structure_format)
    validation_status = payload.validation_status or derived.validation_status
    with session_scope(session_factory) as session:
        _require_compound(session, compound_id)
        row = CompoundStructureRecordORM(
            compound_id=compound_id,
            structure_input=payload.structure_input,
            structure_format=payload.structure_format,
            canonical_smiles=derived.canonical_smiles,
            inchi=derived.inchi,
            inchikey=derived.inchikey,
            formula=derived.formula,
            exact_mass=derived.exact_mass,
            source=payload.source,
            normalization_warnings_json=_json_dump(list(derived.warnings), default=[]),
            validation_status=validation_status,
            reviewer_status=payload.reviewer_status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _structure_to_record(row)


def list_structure_records(
    session_factory: sessionmaker[Session],
    compound_id: int,
) -> list[CompoundStructureRecord]:
    with session_scope(session_factory) as session:
        _require_compound(session, compound_id)
        rows = session.scalars(
            select(CompoundStructureRecordORM)
            .where(CompoundStructureRecordORM.compound_id == compound_id)
            .order_by(CompoundStructureRecordORM.id.desc())
        ).all()
        return [_structure_to_record(row) for row in rows]


def create_alias(
    session_factory: sessionmaker[Session],
    compound_id: int,
    payload: CompoundAliasCreate,
) -> CompoundAlias:
    with session_scope(session_factory) as session:
        _require_compound(session, compound_id)
        existing = session.scalar(
            select(CompoundAliasORM).where(
                CompoundAliasORM.compound_id == compound_id,
                CompoundAliasORM.alias == payload.alias,
                CompoundAliasORM.alias_type == payload.alias_type,
            )
        )
        if existing is not None:
            return _alias_to_record(existing)
        row = CompoundAliasORM(
            compound_id=compound_id,
            alias=payload.alias,
            alias_type=payload.alias_type,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            raise CompoundRegistryValidationError("Compound alias already exists.") from exc
        session.refresh(row)
        return _alias_to_record(row)


def list_aliases(session_factory: sessionmaker[Session], compound_id: int) -> list[CompoundAlias]:
    with session_scope(session_factory) as session:
        _require_compound(session, compound_id)
        rows = session.scalars(
            select(CompoundAliasORM)
            .where(CompoundAliasORM.compound_id == compound_id)
            .order_by(CompoundAliasORM.id.desc())
        ).all()
        return [_alias_to_record(row) for row in rows]


def create_batch(session_factory: sessionmaker[Session], payload: CompoundBatchCreate) -> CompoundBatch:
    with session_scope(session_factory) as session:
        _require_compound(session, payload.compound_id)
        if payload.reaction_experiment_id is not None:
            _require_resource(session, "reaction_experiment", payload.reaction_experiment_id)
        if payload.spectracheck_session_id is not None:
            _require_resource(session, "spectracheck_session", payload.spectracheck_session_id)
        if payload.regulatory_dossier_id is not None:
            _require_resource(session, "regulatory_dossier", payload.regulatory_dossier_id)
        row = CompoundBatchORM(
            compound_id=payload.compound_id,
            batch_code=payload.batch_code,
            lot_code=payload.lot_code,
            source_type=payload.source_type,
            reaction_experiment_id=payload.reaction_experiment_id,
            spectracheck_session_id=payload.spectracheck_session_id,
            regulatory_dossier_id=payload.regulatory_dossier_id,
            amount=payload.amount,
            amount_unit=payload.amount_unit,
            purity_percent=payload.purity_percent,
            purity_method=payload.purity_method,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _batch_to_record(row)


def list_batches(
    session_factory: sessionmaker[Session],
    *,
    compound_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[CompoundBatch]:
    with session_scope(session_factory) as session:
        stmt = select(CompoundBatchORM).order_by(CompoundBatchORM.updated_at.desc(), CompoundBatchORM.id.desc())
        if compound_id is not None:
            stmt = stmt.where(CompoundBatchORM.compound_id == compound_id)
        if status:
            stmt = stmt.where(CompoundBatchORM.status == status)
        rows = session.scalars(stmt.limit(limit)).all()
        return [_batch_to_record(row) for row in rows]


def get_batch(session_factory: sessionmaker[Session], batch_id: int) -> CompoundBatch | None:
    with session_scope(session_factory) as session:
        row = session.get(CompoundBatchORM, batch_id)
        return _batch_to_record(row) if row is not None else None


def update_batch(
    session_factory: sessionmaker[Session],
    batch_id: int,
    payload: CompoundBatchUpdate,
) -> CompoundBatch | None:
    with session_scope(session_factory) as session:
        row = session.get(CompoundBatchORM, batch_id)
        if row is None:
            return None
        fields = payload.model_fields_set
        for field_name in (
            "compound_id",
            "batch_code",
            "lot_code",
            "source_type",
            "reaction_experiment_id",
            "spectracheck_session_id",
            "regulatory_dossier_id",
            "amount",
            "amount_unit",
            "purity_percent",
            "purity_method",
            "status",
        ):
            if field_name in fields:
                value = getattr(payload, field_name)
                if field_name == "compound_id" and value is not None:
                    _require_compound(session, int(value))
                setattr(row, field_name, value)
        if "metadata_json" in fields and payload.metadata_json is not None:
            row.metadata_json = _json_dump(payload.metadata_json, default={})
        row.updated_at = utcnow()
        session.flush()
        session.refresh(row)
        return _batch_to_record(row)


def create_aliquot(
    session_factory: sessionmaker[Session],
    batch_id: int,
    payload: SampleAliquotCreate,
) -> SampleAliquot:
    with session_scope(session_factory) as session:
        _require_batch(session, batch_id)
        row = SampleAliquotORM(
            batch_id=batch_id,
            sample_id=payload.sample_id,
            aliquot_code=payload.aliquot_code,
            amount=payload.amount,
            amount_unit=payload.amount_unit,
            storage_location=payload.storage_location,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _aliquot_to_record(row)


def list_aliquots(session_factory: sessionmaker[Session], batch_id: int) -> list[SampleAliquot]:
    with session_scope(session_factory) as session:
        _require_batch(session, batch_id)
        rows = session.scalars(
            select(SampleAliquotORM)
            .where(SampleAliquotORM.batch_id == batch_id)
            .order_by(SampleAliquotORM.id.desc())
        ).all()
        return [_aliquot_to_record(row) for row in rows]


def create_relationship(
    session_factory: sessionmaker[Session],
    source_compound_id: int,
    payload: CompoundRelationshipCreate,
) -> CompoundRelationship:
    with session_scope(session_factory) as session:
        _require_compound(session, source_compound_id)
        _require_compound(session, payload.target_compound_id)
        row = CompoundRelationshipORM(
            source_compound_id=source_compound_id,
            target_compound_id=payload.target_compound_id,
            relationship_type=payload.relationship_type,
            confidence_label=payload.confidence_label,
            evidence_summary_json=_json_dump(payload.evidence_summary_json, default={}),
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        edge = ScientificKnowledgeGraphEdgeORM(
            source_type="compound",
            source_id=str(source_compound_id),
            target_type="compound",
            target_id=str(payload.target_compound_id),
            relation_type=payload.relationship_type,
            label=f"candidate relationship: {payload.relationship_type}",
            confidence_label=payload.confidence_label,
            metadata_json=_json_dump({"compound_relationship_id": row.id}, default={}),
        )
        session.add(edge)
        session.flush()
        session.refresh(row)
        return _relationship_to_record(row)


def list_relationships(
    session_factory: sessionmaker[Session],
    compound_id: int,
) -> list[CompoundRelationship]:
    with session_scope(session_factory) as session:
        _require_compound(session, compound_id)
        rows = session.scalars(
            select(CompoundRelationshipORM)
            .where(
                or_(
                    CompoundRelationshipORM.source_compound_id == compound_id,
                    CompoundRelationshipORM.target_compound_id == compound_id,
                )
            )
            .order_by(CompoundRelationshipORM.id.desc())
        ).all()
        return [_relationship_to_record(row) for row in rows]


def create_evidence_link(
    session_factory: sessionmaker[Session],
    payload: CompoundEvidenceLinkCreate,
) -> CompoundEvidenceLink:
    with session_scope(session_factory) as session:
        if payload.compound_id is not None:
            _require_compound(session, payload.compound_id)
        if payload.batch_id is not None:
            batch = _require_batch(session, payload.batch_id)
            if payload.compound_id is not None and batch.compound_id != payload.compound_id:
                raise CompoundRegistryValidationError("batch_id must belong to compound_id.")
        _require_resource(session, payload.resource_type, payload.resource_id)
        row = CompoundEvidenceLinkORM(
            compound_id=payload.compound_id,
            batch_id=payload.batch_id,
            sample_id=payload.sample_id,
            resource_type=payload.resource_type,
            resource_id=_resource_id_text(payload.resource_id),
            title=payload.title,
            summary=payload.summary,
            status=payload.status,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _evidence_link_to_record(row)


def list_compound_evidence_links(
    session_factory: sessionmaker[Session],
    compound_id: int,
) -> list[CompoundEvidenceLink]:
    with session_scope(session_factory) as session:
        _require_compound(session, compound_id)
        rows = session.scalars(
            select(CompoundEvidenceLinkORM)
            .where(CompoundEvidenceLinkORM.compound_id == compound_id)
            .order_by(CompoundEvidenceLinkORM.id.desc())
        ).all()
        return [_evidence_link_to_record(row) for row in rows]


def list_batch_evidence_links(
    session_factory: sessionmaker[Session],
    batch_id: int,
) -> list[CompoundEvidenceLink]:
    with session_scope(session_factory) as session:
        _require_batch(session, batch_id)
        rows = session.scalars(
            select(CompoundEvidenceLinkORM)
            .where(CompoundEvidenceLinkORM.batch_id == batch_id)
            .order_by(CompoundEvidenceLinkORM.id.desc())
        ).all()
        return [_evidence_link_to_record(row) for row in rows]


def create_graph_edge(
    session_factory: sessionmaker[Session],
    payload: ScientificKnowledgeGraphEdgeCreate,
) -> ScientificKnowledgeGraphEdge:
    with session_scope(session_factory) as session:
        if payload.evidence_link_id is not None and session.get(CompoundEvidenceLinkORM, payload.evidence_link_id) is None:
            raise CompoundRegistryNotFoundError("Evidence link not found.")
        row = ScientificKnowledgeGraphEdgeORM(
            source_type=payload.source_type,
            source_id=_resource_id_text(payload.source_id),
            target_type=payload.target_type,
            target_id=_resource_id_text(payload.target_id),
            relation_type=payload.relation_type,
            label=payload.label,
            confidence_label=payload.confidence_label,
            evidence_link_id=payload.evidence_link_id,
            metadata_json=_json_dump(payload.metadata_json, default={}),
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return _graph_edge_to_record(row)


def _compound_node(row: CompoundEntityORM) -> ScientificKnowledgeGraphNode:
    return ScientificKnowledgeGraphNode(
        node_type="compound",
        node_id=row.id,
        label=row.preferred_name or row.registry_id or f"Compound {row.id}",
        metadata_json={
            "registry_id": row.registry_id,
            "status": row.status,
            "compound_type": row.compound_type,
            "inchikey": row.inchikey,
        },
    )


def get_graph(
    session_factory: sessionmaker[Session],
    *,
    compound_id: int | None = None,
    limit: int = 500,
) -> ScientificKnowledgeGraph:
    with session_scope(session_factory) as session:
        edge_stmt = select(ScientificKnowledgeGraphEdgeORM).order_by(ScientificKnowledgeGraphEdgeORM.id.desc())
        if compound_id is not None:
            _require_compound(session, compound_id)
            compound_text = str(compound_id)
            edge_stmt = edge_stmt.where(
                or_(
                    (ScientificKnowledgeGraphEdgeORM.source_type == "compound")
                    & (ScientificKnowledgeGraphEdgeORM.source_id == compound_text),
                    (ScientificKnowledgeGraphEdgeORM.target_type == "compound")
                    & (ScientificKnowledgeGraphEdgeORM.target_id == compound_text),
                )
            )
        edge_rows = session.scalars(edge_stmt.limit(limit)).all()
        node_map: dict[tuple[str, str], ScientificKnowledgeGraphNode] = {}
        compound_ids: set[int] = set()
        if compound_id is not None:
            compound_ids.add(compound_id)
        for edge in edge_rows:
            for node_type, node_id in ((edge.source_type, edge.source_id), (edge.target_type, edge.target_id)):
                if node_type == "compound" and str(node_id).isdigit():
                    compound_ids.add(int(node_id))
                else:
                    node_map[(node_type, str(node_id))] = ScientificKnowledgeGraphNode(
                        node_type=node_type,
                        node_id=_resource_id(node_id),
                        label=None,
                        metadata_json={},
                    )
        if compound_id is None:
            for row in session.scalars(select(CompoundEntityORM).order_by(CompoundEntityORM.id.desc()).limit(100)).all():
                compound_ids.add(row.id)
        if compound_ids:
            rows = session.scalars(select(CompoundEntityORM).where(CompoundEntityORM.id.in_(compound_ids))).all()
            for row in rows:
                node_map[("compound", str(row.id))] = _compound_node(row)
        nodes = sorted(node_map.values(), key=lambda node: (node.node_type, str(node.node_id)))
        return ScientificKnowledgeGraph(
            nodes=nodes,
            edges=[_graph_edge_to_record(row) for row in edge_rows],
            notes=[
                "Graph edges represent linked compound context, candidate relationships, and evidence provenance.",
                "Edges with requires_review confidence need review before use in decisions.",
            ],
        )


def search_compounds(
    session_factory: sessionmaker[Session],
    payload: CompoundRegistrySearchRequest,
) -> CompoundRegistrySearchResult:
    with session_scope(session_factory) as session:
        stmt = select(CompoundEntityORM).order_by(CompoundEntityORM.updated_at.desc(), CompoundEntityORM.id.desc())
        if payload.name:
            pattern = f"%{payload.name}%"
            alias_ids = select(CompoundAliasORM.compound_id).where(CompoundAliasORM.alias.ilike(pattern))
            stmt = stmt.where(or_(CompoundEntityORM.preferred_name.ilike(pattern), CompoundEntityORM.id.in_(alias_ids)))
        if payload.alias:
            pattern = f"%{payload.alias}%"
            alias_ids = select(CompoundAliasORM.compound_id).where(CompoundAliasORM.alias.ilike(pattern))
            stmt = stmt.where(CompoundEntityORM.id.in_(alias_ids))
        if payload.registry_id:
            stmt = stmt.where(CompoundEntityORM.registry_id == payload.registry_id)
        if payload.inchikey:
            structure_ids = select(CompoundStructureRecordORM.compound_id).where(
                CompoundStructureRecordORM.inchikey == payload.inchikey
            )
            stmt = stmt.where(or_(CompoundEntityORM.inchikey == payload.inchikey, CompoundEntityORM.id.in_(structure_ids)))
        if payload.formula:
            structure_ids = select(CompoundStructureRecordORM.compound_id).where(
                CompoundStructureRecordORM.formula == payload.formula
            )
            stmt = stmt.where(
                or_(CompoundEntityORM.molecular_formula == payload.formula, CompoundEntityORM.id.in_(structure_ids))
            )
        if payload.exact_mass_min is not None or payload.exact_mass_max is not None:
            entity_mass_filters = []
            structure_mass_filters = []
            if payload.exact_mass_min is not None:
                entity_mass_filters.append(CompoundEntityORM.exact_mass >= payload.exact_mass_min)
                structure_mass_filters.append(CompoundStructureRecordORM.exact_mass >= payload.exact_mass_min)
            if payload.exact_mass_max is not None:
                entity_mass_filters.append(CompoundEntityORM.exact_mass <= payload.exact_mass_max)
                structure_mass_filters.append(CompoundStructureRecordORM.exact_mass <= payload.exact_mass_max)
            structure_ids = select(CompoundStructureRecordORM.compound_id).where(*structure_mass_filters)
            stmt = stmt.where(or_(*entity_mass_filters, CompoundEntityORM.id.in_(structure_ids)))
        rows = list(session.scalars(stmt.limit(max(payload.limit, 200))).all())
        if payload.metadata_json:
            rows = [
                row
                for row in rows
                if _metadata_matches(_json_dict(row.metadata_json), payload.metadata_json)
            ]
        rows = rows[: payload.limit]
        return CompoundRegistrySearchResult(
            compounds=[_compound_to_record(row) for row in rows],
            total=len(rows),
            notes=["Search returns registry matches for review; it does not overclaim identity."],
        )


def _metadata_matches(candidate: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, expected in query.items():
        if key not in candidate:
            return False
        actual = candidate[key]
        if isinstance(expected, dict) and isinstance(actual, dict):
            if not _metadata_matches(actual, expected):
                return False
        elif actual != expected:
            return False
    return True


def link_resource_to_compound(
    session_factory: sessionmaker[Session],
    *,
    resource_type: str,
    resource_id: int,
    payload: CompoundRegistryLinkRequest,
    default_title: str,
    default_relation_type: str = "linked_compound",
    compound_as_source: bool = False,
) -> CompoundRegistryLinkResponse:
    with session_scope(session_factory) as session:
        _require_compound(session, payload.compound_id)
        if payload.batch_id is not None:
            batch = _require_batch(session, payload.batch_id)
            if batch.compound_id != payload.compound_id:
                raise CompoundRegistryValidationError("batch_id must belong to compound_id.")
        _require_resource(session, resource_type, resource_id)
        title = payload.title or default_title
        metadata = dict(payload.metadata_json)
        metadata.setdefault("linked_compound", True)
        metadata.setdefault("needs_review", payload.confidence_label == "requires_review")
        link = CompoundEvidenceLinkORM(
            compound_id=payload.compound_id,
            batch_id=payload.batch_id,
            sample_id=payload.sample_id,
            resource_type=resource_type,
            resource_id=str(resource_id),
            title=title,
            summary=payload.summary,
            status=payload.status,
            metadata_json=_json_dump(metadata, default={}),
        )
        session.add(link)
        session.flush()
        relation_type = payload.relation_type or default_relation_type
        if compound_as_source:
            source_type = "compound"
            source_id = str(payload.compound_id)
            target_type = resource_type
            target_id = str(resource_id)
        else:
            source_type = resource_type
            source_id = str(resource_id)
            target_type = "compound"
            target_id = str(payload.compound_id)
        edge = ScientificKnowledgeGraphEdgeORM(
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            relation_type=relation_type,
            label=title,
            confidence_label=payload.confidence_label,
            evidence_link_id=link.id,
            metadata_json=_json_dump(
                {
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "linked_compound": True,
                    "needs_review": payload.confidence_label == "requires_review",
                },
                default={},
            ),
        )
        session.add(edge)
        session.flush()
        session.refresh(link)
        session.refresh(edge)
        return CompoundRegistryLinkResponse(
            evidence_link=_evidence_link_to_record(link),
            graph_edge=_graph_edge_to_record(edge),
            notes=["Linked compound context created with a knowledge graph edge."],
        )
