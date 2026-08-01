"""Structure & reaction-scheme service — RDKit validation, canonicalization, persistence.

The drawing canvas in Reaction Studio captures what a chemist drew as an MDL molfile or RXN
block. Ketcher's in-browser Indigo engine produced that block; **RDKit is the authority** here,
because every other MolTrace chemistry decision (qNMR purity, verification scoring, NMR
prediction, MS models, Q3C solvents, M7 classifier) already runs on RDKit. Two chemistry
engines silently disagreeing is precisely the failure a regulated workspace cannot absorb.

So this module never sanitizes quietly. It parses the block twice — once as drawn, once
sanitized — and reports every difference that a chemist would call *a change to my structure*
(hydrogen counts, formal charges, unpaired electrons) as a plain-language warning. Aromatic
perception and resonance-form choice are representation rather than structure, and are reported
once per drawing at most, so a phenyl ring does not generate warning noise that trains reviewers
to ignore the panel.

Three properties of the captured payload drive the design, all observed rather than assumed:

* ``format`` is load-bearing. An RXN block is not a molfile and must be parsed with
  ``ReactionFromRxnBlock``, not ``MolFromMolBlock``. The declared format is trusted over any
  attempt to sniff the string.
* ``smiles`` may legitimately be empty. SMILES generation fails on valid-but-exotic drawings
  (query atoms, R-groups) — exactly the drawings a SMARTS query is made of. ``block`` is the
  source of truth; ``smiles`` is a convenience, and when present it is *cross-checked* rather
  than trusted.
* Blocks are small but unbounded, so the payload is capped with a plain-language rejection.

**This is not a second compound registry.** A single registered compound already has a home in
``compound_registry_store``, which canonicalizes a molblock on the way in; that path is not
rebuilt here, and its format vocabulary deliberately has no ``rxn`` — a reaction is not a
compound structure. What this module adds is the two things that path structurally cannot do:
check a drawing *before* anything is committed, and hold a reaction. Where both paths read the
same molfile they must produce the same answer, so canonical output here is deliberately
H-suppressed to match the registry (see ``_suppress_explicit_hydrogens``) and a test pins the
two together.

The validation/screening functions are pure RDKit + stdlib and deterministic. A persistence
layer below stores a captured scheme against a reaction project, retaining both the block as
drawn (the audit record) and the normalized block (what downstream code computes on).
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .alcoa import apply_soft_delete
from .database import session_scope
from .orm import (
    AuditEventORM,
    ReactionProjectORM,
    ReactionStructureSchemeORM,
    utcnow,
)
from .reaction_store import ReactionActor, ReactionError

# A drawn scheme is small; a pasted SDF need not be. Cap the payload rather than letting an
# arbitrarily large block reach the parser.
MAX_BLOCK_CHARS = 1_000_000
MAX_SMARTS_CHARS = 4_000
MAX_SMARTS_TARGETS = 500

VALIDATOR_VERSION = "reaction_structures.v1"

_FORMATS = ("mol", "rxn")


# --------------------------------------------------------------------------------------
# Plain-language rendering of RDKit's structured chemistry problems.
#
# These strings go straight onto a chemist's screen, so they carry no RDKit exception text,
# no function names and no status codes (see feedback_no_backend_jargon_in_user_copy).
# --------------------------------------------------------------------------------------

_ELEMENT_NAMES = {
    "C": "Carbon", "N": "Nitrogen", "O": "Oxygen", "S": "Sulfur", "P": "Phosphorus",
    "F": "Fluorine", "Cl": "Chlorine", "Br": "Bromine", "I": "Iodine", "B": "Boron",
    "Si": "Silicon", "Se": "Selenium", "H": "Hydrogen",
}


def _load_rdkit():
    """Import RDKit lazily so the module imports even where the wheel is absent."""
    try:
        from rdkit import Chem  # noqa: PLC0415
        from rdkit.Chem import AllChem, rdChemReactions  # noqa: PLC0415

        return Chem, AllChem, rdChemReactions
    except Exception:  # pragma: no cover - rdkit is a hard dependency in this deployment
        return None, None, None


def _element_name(symbol: str) -> str:
    return _ELEMENT_NAMES.get(symbol, symbol)


def _issue(code: str, message: str, atom_indices: list[int] | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "atom_indices": atom_indices or []}


def _problem_to_error(problem: Any, mol: Any, *, where: str = "") -> dict[str, Any]:
    """Translate one RDKit chemistry problem into a chemist-readable error.

    ``where`` prefixes the message for reaction components ("In reactant 2, ") so a role stays
    legible without changing the documented warning shape.
    """
    kind = ""
    try:
        kind = str(problem.GetType())
    except Exception:
        kind = ""

    if kind == "AtomValenceException":
        idx = int(problem.GetAtomIdx())
        atom = mol.GetAtomWithIdx(idx) if idx < mol.GetNumAtoms() else None
        symbol = atom.GetSymbol() if atom is not None else "atom"
        bonds = atom.GetExplicitValence() if atom is not None else 0
        charge = atom.GetFormalCharge() if atom is not None else 0
        charge_text = "no charge" if charge == 0 else f"a charge of {charge:+d}"
        return _issue(
            "impossible_valence",
            f"{where}{_element_name(symbol)} at atom {idx} has {bonds} bonds and {charge_text}, "
            "which is more than it can hold. Check the bonds on that atom, or add the charge "
            "it should carry.",
            [idx],
        )

    if kind in ("KekulizeException", "AtomKekulizeException"):
        indices = _problem_atom_indices(problem)
        return _issue(
            "ring_not_readable",
            f"{where}A ring drawn as aromatic has no alternating single/double bond pattern "
            "that works. Check the ring's bonds, and any hydrogens or charges on its atoms.",
            indices,
        )

    return _issue(
        "structure_not_readable",
        f"{where}Part of this drawing could not be read as valid chemistry. Check for unusual "
        "bonds, charges or hydrogen counts.",
    )


def _problem_atom_indices(problem: Any) -> list[int]:
    for accessor in ("GetAtomIndices", "GetAtomIdx"):
        getter = getattr(problem, accessor, None)
        if getter is None:
            continue
        try:
            value = getter()
        except Exception:
            continue
        if isinstance(value, int):
            return [value]
        try:
            return [int(v) for v in value]
        except (TypeError, ValueError):
            continue
    return []


# --------------------------------------------------------------------------------------
# Sanitization diffing — "did checking this structure change it?"
# --------------------------------------------------------------------------------------


def _atom_invariants(mol: Any) -> list[tuple[int, int, int]]:
    """Per-atom (total hydrogens, formal charge, radical electrons).

    Deliberately excludes aromaticity and bond order: perceiving benzene as aromatic, or
    picking a different Kekulé form of the same ring, does not change the compound. These
    three do — they are what a chemist means by "that is not what I drew".
    """
    return [
        (a.GetTotalNumHs(), a.GetFormalCharge(), a.GetNumRadicalElectrons())
        for a in mol.GetAtoms()
    ]


def _describe_invariant_changes(before: list, after: list) -> list[dict[str, Any]]:
    if len(before) != len(after):
        # Atom count changed under sanitization; report it wholesale rather than pretending
        # to align two different atom lists.
        return [
            _issue(
                "atom_list_changed",
                "Checking this structure changed how many atoms it contains. The stored form "
                "is not the one that was drawn — please re-check the drawing.",
            )
        ]

    h_changed: list[int] = []
    charge_changed: list[int] = []
    radical_changed: list[int] = []
    # strict=True is safe: the length guard above already returned for a mismatch.
    for idx, (was, now) in enumerate(zip(before, after, strict=True)):
        if was[0] != now[0]:
            h_changed.append(idx)
        if was[1] != now[1]:
            charge_changed.append(idx)
        if was[2] != now[2]:
            radical_changed.append(idx)

    warnings: list[dict[str, Any]] = []
    if h_changed:
        warnings.append(
            _issue(
                "hydrogen_count_changed",
                f"The hydrogen count changed on {_atoms_phrase(len(h_changed))} when this "
                "structure was checked. The stored structure differs from the drawing — "
                "confirm the hydrogens are what you intended.",
                h_changed,
            )
        )
    if charge_changed:
        warnings.append(
            _issue(
                "charge_changed",
                f"The charge changed on {_atoms_phrase(len(charge_changed))} when this "
                "structure was checked. Confirm the charges are what you intended.",
                charge_changed,
            )
        )
    if radical_changed:
        warnings.append(
            _issue(
                "unpaired_electrons",
                f"{_atoms_phrase(len(radical_changed)).capitalize()} were read as carrying an "
                "unpaired electron. If a radical was not intended, check the bonds and "
                "hydrogens there.",
                radical_changed,
            )
        )
    return warnings


def _atoms_phrase(count: int) -> str:
    return "1 atom" if count == 1 else f"{count} atoms"


def _query_atom_indices(mol: Any, *, trust_has_query: bool = True) -> list[int]:
    """Atoms that stand for a family of structures rather than one element (R-groups, A/Q/*).

    ``trust_has_query`` must be False for reaction templates. RDKit wraps *every* atom of a
    template parsed from an RXN block as a query atom, so ``HasQuery()`` there says nothing
    about the drawing — believing it would label every ordinary reaction an R-group family.
    An atomic number of 0 stays meaningful in both cases.
    """
    indices = []
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() == 0 or (trust_has_query and atom.HasQuery()):
            indices.append(atom.GetIdx())
    return indices


def _undefined_stereocentres(chem: Any, mol: Any) -> list[int]:
    try:
        centres = chem.FindMolChiralCenters(
            mol, includeUnassigned=True, useLegacyImplementation=False
        )
    except Exception:
        return []
    return [int(idx) for idx, label in centres if label == "?"]


def _has_explicit_aromatic_bonds(mol: Any, chem: Any) -> bool:
    return any(bond.GetBondType() == chem.BondType.AROMATIC for bond in mol.GetBonds())


def _prepare(chem: Any, mol: Any) -> None:
    """Compute the property cache without full sanitization, so a before/after diff is fair."""
    try:
        mol.UpdatePropertyCache(strict=False)
    except Exception:
        pass


def _inspect_mol(
    chem: Any, raw: Any, *, where: str = "", is_reaction_template: bool = False
) -> dict[str, Any]:
    """Sanitize a copy of ``raw`` and report what that changed. Never mutates ``raw``.

    Returns ``{clean, errors, warnings}``; ``clean`` is None when the structure cannot be
    sanitized at all.
    """
    _prepare(chem, raw)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    problems = []
    try:
        problems = chem.DetectChemistryProblems(raw)
    except Exception:
        problems = []
    for problem in problems:
        errors.append(_problem_to_error(problem, raw, where=where))
    if errors:
        return {"clean": None, "errors": errors, "warnings": warnings}

    before = _atom_invariants(raw)
    clean = chem.Mol(raw)
    try:
        chem.SanitizeMol(clean)
    except Exception:
        return {
            "clean": None,
            "errors": [
                _issue(
                    "structure_not_readable",
                    f"{where}This structure could not be checked as valid chemistry. Look for "
                    "unusual bonds, charges or hydrogen counts.",
                )
            ],
            "warnings": warnings,
        }

    warnings.extend(_describe_invariant_changes(before, _atom_invariants(clean)))

    if _has_explicit_aromatic_bonds(raw, chem):
        warnings.append(
            _issue(
                "aromatic_rings_written_out",
                f"{where}Aromatic rings are stored with explicit alternating single and double "
                "bonds. The chemistry is unchanged; only how the ring is written down differs.",
            )
        )

    query_atoms = _query_atom_indices(clean, trust_has_query=not is_reaction_template)
    if query_atoms:
        warnings.append(
            _issue(
                "query_atoms_present",
                f"{where}This drawing contains R-groups or query atoms, so it describes a "
                "family of structures rather than one compound.",
                query_atoms,
            )
        )

    undefined = _undefined_stereocentres(chem, clean)
    if undefined:
        warnings.append(
            _issue(
                "stereochemistry_undefined",
                f"{where}{_centres_phrase(len(undefined))} drawn without defined "
                "stereochemistry. The stored structure covers both arrangements.",
                undefined,
            )
        )

    return {"clean": clean, "errors": errors, "warnings": warnings}


def _centres_phrase(count: int) -> str:
    return (
        "1 stereocentre is" if count == 1 else f"{count} stereocentres are"
    )


# --------------------------------------------------------------------------------------
# Endpoint 1 — validate & canonicalize
# --------------------------------------------------------------------------------------


def _empty_result(fmt: str, errors: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "ok": False,
        "format": fmt,
        "canonical_smiles": None,
        "normalized_block": None,
        "inchikey": None,
        "atom_count": 0,
        "bond_count": 0,
        "component_counts": None,
        "warnings": [],
        "errors": errors,
        "validator_version": VALIDATOR_VERSION,
    }


def validate_structure(
    *, block: str, fmt: str, smiles: str | None = None
) -> dict[str, Any]:
    """Read a captured drawing with RDKit and report what it is — and what changed.

    A structure that fails its chemistry checks is still a *successful* validation: the verdict
    lives in ``ok``/``errors``, never in a transport status code. ``fmt`` selects the parser and
    is trusted over the string's contents. ``smiles``, when supplied and non-empty, is
    cross-checked against RDKit's own reading rather than believed.
    """
    if fmt not in _FORMATS:
        return _empty_result(
            fmt,
            [
                _issue(
                    "unsupported_format",
                    "This drawing format is not supported. Capture it again from the editor.",
                )
            ],
        )

    if len(block or "") > MAX_BLOCK_CHARS:
        return _empty_result(
            fmt,
            [
                _issue(
                    "too_large",
                    "This drawing is too large to check. Try attaching a single scheme rather "
                    "than a whole structure file.",
                )
            ],
        )

    chem, allchem, _rdrxn = _load_rdkit()
    if chem is None:  # pragma: no cover - rdkit is installed in this deployment
        return _empty_result(
            fmt,
            [
                _issue(
                    "checks_unavailable",
                    "Structure checking is not available in this deployment.",
                )
            ],
        )

    if not (block or "").strip():
        return _empty_result(
            fmt,
            [_issue("empty_drawing", "There is nothing drawn yet to check.")],
        )

    if fmt == "rxn":
        result = _validate_reaction(chem, allchem, block)
    else:
        result = _validate_molecule(chem, block)

    _cross_check_supplied_smiles(chem, allchem, result, smiles=smiles, fmt=fmt)
    return result


def _validate_molecule(chem: Any, block: str) -> dict[str, Any]:
    with _quiet(chem):
        try:
            raw = chem.MolFromMolBlock(
                block, sanitize=False, removeHs=False, strictParsing=False
            )
        except Exception:
            raw = None

        if raw is None:
            return _empty_result(
                "mol",
                [
                    _issue(
                        "structure_not_readable",
                        "This drawing could not be read as a structure. Try capturing it again "
                        "from the editor.",
                    )
                ],
            )
        if raw.GetNumAtoms() == 0:
            return _empty_result(
                "mol", [_issue("empty_drawing", "There is nothing drawn yet to check.")]
            )

        inspected = _inspect_mol(chem, raw)
        clean = inspected["clean"]
        if clean is None:
            failed = _empty_result("mol", inspected["errors"])
            failed["warnings"] = inspected["warnings"]
            return failed

        warnings = inspected["warnings"]
        display, folded_hydrogens = _suppress_explicit_hydrogens(chem, clean)
        if folded_hydrogens:
            warnings.append(
                _issue(
                    "explicit_hydrogens_folded_in",
                    f"{_atoms_phrase(folded_hydrogens).capitalize()} drawn as separate hydrogen "
                    "atoms are counted on the atoms they belong to instead. The compound is "
                    "unchanged, and the original drawing is kept as it was drawn.",
                )
            )

        canonical = chem.MolToSmiles(display)
        normalized = chem.MolToMolBlock(display, kekulize=True)
        has_query = bool(_query_atom_indices(display))
        return {
            "ok": True,
            "format": "mol",
            "canonical_smiles": canonical or None,
            "normalized_block": normalized,
            # Only for a single, fully-defined structure: a key emitted for an R-group drawing
            # would name a compound the chemist never drew.
            "inchikey": None if has_query else _inchikey(chem, display),
            "atom_count": display.GetNumAtoms(),
            "bond_count": display.GetNumBonds(),
            "component_counts": None,
            "warnings": warnings,
            "errors": [],
            "validator_version": VALIDATOR_VERSION,
        }


def _validate_reaction(chem: Any, allchem: Any, block: str) -> dict[str, Any]:
    with _quiet(chem):
        try:
            rxn = allchem.ReactionFromRxnBlock(block, sanitize=False)
        except Exception:
            rxn = None
        if rxn is None:
            return _empty_result(
                "rxn",
                [
                    _issue(
                        "structure_not_readable",
                        "This reaction scheme could not be read. Try capturing it again from "
                        "the editor.",
                    )
                ],
            )

        counts = {
            "reactants": rxn.GetNumReactantTemplates(),
            "agents": rxn.GetNumAgentTemplates(),
            "products": rxn.GetNumProductTemplates(),
        }
        if sum(counts.values()) == 0:
            empty = _empty_result(
                "rxn", [_issue("empty_drawing", "There is nothing drawn yet to check.")]
            )
            empty["component_counts"] = counts
            return empty

        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        atom_count = 0
        bond_count = 0
        folded_hydrogens = 0
        # Each role's components, canonicalized exactly as a standalone molecule would be, so a
        # reaction and a molecule never disagree about the same drawn structure.
        by_role: dict[str, list[Any]] = {"reactant": [], "agent": [], "product": []}
        for role, templates in (
            ("reactant", rxn.GetReactants()),
            ("agent", rxn.GetAgents()),
            ("product", rxn.GetProducts()),
        ):
            for position, template in enumerate(templates, start=1):
                where = f"In {role} {position}, "
                inspected = _inspect_mol(
                    chem, template, where=where, is_reaction_template=True
                )
                errors.extend(inspected["errors"])
                warnings.extend(inspected["warnings"])
                clean = inspected["clean"]
                if clean is not None:
                    display, folded = _suppress_explicit_hydrogens(
                        chem, clean, is_reaction_template=True
                    )
                    folded_hydrogens += folded
                    by_role[role].append(display)
                    atom_count += display.GetNumAtoms()
                    bond_count += display.GetNumBonds()

        if errors:
            failed = _empty_result("rxn", errors)
            failed["warnings"] = _collapse_whole_drawing_notes(warnings)
            failed["component_counts"] = counts
            return failed

        if folded_hydrogens:
            warnings.append(
                _issue(
                    "explicit_hydrogens_folded_in",
                    f"{_atoms_phrase(folded_hydrogens).capitalize()} drawn as separate hydrogen "
                    "atoms are counted on the atoms they belong to instead. The chemistry is "
                    "unchanged, and the original drawing is kept as it was drawn.",
                )
            )
        warnings = _collapse_whole_drawing_notes(warnings)

        try:
            canonical = _reaction_smiles(chem, by_role)
            normalized = _reaction_block(allchem, by_role)
        except Exception:
            failed = _empty_result(
                "rxn",
                [
                    _issue(
                        "structure_not_readable",
                        "This reaction scheme could not be checked as a whole. Confirm every "
                        "structure and the reaction arrow are complete.",
                    )
                ],
            )
            failed["warnings"] = warnings
            failed["component_counts"] = counts
            return failed

        return {
            "ok": True,
            "format": "rxn",
            "canonical_smiles": canonical or None,
            "normalized_block": normalized,
            # A reaction is not one compound, so it has no InChIKey.
            "inchikey": None,
            "atom_count": atom_count,
            "bond_count": bond_count,
            "component_counts": counts,
            "warnings": warnings,
            "errors": [],
            "validator_version": VALIDATOR_VERSION,
        }


# Notes that describe how the whole drawing was written down rather than something about one
# component. Reported once per drawing: emitting them per component means a three-component
# aromatic coupling raises the same note three times, which is the alert fatigue this module
# is otherwise careful to avoid.
_WHOLE_DRAWING_NOTES = ("aromatic_rings_written_out", "explicit_hydrogens_folded_in")


def _collapse_whole_drawing_notes(warnings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    collapsed: list[dict[str, Any]] = []
    for warning in warnings:
        code = warning["code"]
        if code in _WHOLE_DRAWING_NOTES:
            if code in seen:
                continue
            seen.add(code)
            # Strip the "In reactant 2, " prefix: the note is about the drawing, not that piece.
            message = warning["message"]
            if message.startswith("In "):
                _, _, rest = message.partition(", ")
                warning = _issue(code, rest[:1].upper() + rest[1:] if rest else message)
        collapsed.append(warning)
    return collapsed


def _reaction_smiles(chem: Any, by_role: dict[str, list[Any]]) -> str:
    """Build reaction SMILES from per-component canonical SMILES, sorted within each role.

    Not ``ReactionToSmiles`` on the parsed reaction: templates read from an RXN block are
    *query* molecules, and RDKit writes those in query form — a benzene ring comes out as
    ``C1:C:C:C:C:C:1`` rather than ``c1ccccc1``. Canonicalizing each component as an ordinary
    molecule keeps one answer across the molecule and reaction paths, and inherits the same
    hydrogen suppression that keeps both agreeing with the compound registry.

    Components are **sorted** because ``A.B>>C`` and ``B.A>>C`` are the same reaction: a
    canonical form that changes with the order someone happened to draw things in is not
    canonical. Left unsorted, the editor-disagreement warning fired on most reactions purely
    because RDKit's own writer orders components differently — a warning that cries wolf is
    worse than no warning, and this one exists to catch genuine two-engine disagreement. The
    stored ``normalized_block`` keeps the drawn order, so the scheme still renders as drawn.
    """
    parts = []
    for role in ("reactant", "agent", "product"):
        parts.append(".".join(sorted(chem.MolToSmiles(mol) for mol in by_role[role])))
    return ">".join(parts)


def _reaction_components(chem: Any, rxn: Any) -> dict[str, list[Any]]:
    """Split a parsed reaction into per-role component molecules, hydrogens suppressed."""
    by_role: dict[str, list[Any]] = {"reactant": [], "agent": [], "product": []}
    for role, templates in (
        ("reactant", rxn.GetReactants()),
        ("agent", rxn.GetAgents()),
        ("product", rxn.GetProducts()),
    ):
        for template in templates:
            display, _folded = _suppress_explicit_hydrogens(chem, template)
            by_role[role].append(display)
    return by_role


def _reaction_block(allchem: Any, by_role: dict[str, list[Any]]) -> str:
    """Rebuild the RXN block from the same components the canonical SMILES came from."""
    rebuilt = allchem.ChemicalReaction()
    for mol in by_role["reactant"]:
        rebuilt.AddReactantTemplate(mol)
    for mol in by_role["agent"]:
        rebuilt.AddAgentTemplate(mol)
    for mol in by_role["product"]:
        rebuilt.AddProductTemplate(mol)
    return allchem.ReactionToRxnBlock(rebuilt)


def _suppress_explicit_hydrogens(
    chem: Any, mol: Any, *, is_reaction_template: bool = False
) -> tuple[Any, int]:
    """Fold separately-drawn hydrogens onto their parent atoms for the reported structure.

    This exists to keep one answer in the product. The compound registry canonicalizes a
    molblock with ``MolFromMolBlock(..., sanitize=True)``, whose default suppresses explicit
    hydrogens; parsing with ``removeHs=False`` — which this module must do, so the
    before/after sanitization diff compares like with like — otherwise reports ``CCO`` as
    ``[H]OC([H])([H])C([H])([H])[H]``. Same compound, two canonical forms, one product: the
    exact drift this service exists to prevent, one layer below the editor.

    ``is_reaction_template`` additionally clears hydrogens carried as query atoms. Plain
    ``RemoveHs`` leaves those alone, and every atom of a template parsed from an RXN block is
    a query atom, so without this a reaction drawn with explicit hydrogens keeps them while
    the same molecule drawn alone does not — the fix applied to one side of a symmetric hole.

    Returns the H-suppressed molecule and how many atoms went away. RDKit keeps hydrogens
    that carry information (isotopes, charges, defined stereo), so a deuterium label survives
    either way.
    """
    try:
        if is_reaction_template:
            from rdkit.Chem import rdmolops  # noqa: PLC0415

            params = rdmolops.RemoveHsParameters()
            params.removeWithQuery = True
            reduced = rdmolops.RemoveHs(chem.Mol(mol), params)
        else:
            reduced = chem.RemoveHs(chem.Mol(mol))
    except Exception:
        return mol, 0
    removed = mol.GetNumAtoms() - reduced.GetNumAtoms()
    return (reduced, removed) if removed > 0 else (mol, 0)


def _inchikey(chem: Any, mol: Any) -> str | None:
    try:
        key = chem.MolToInchiKey(mol)
    except Exception:
        return None
    return key or None


def _cross_check_supplied_smiles(
    chem: Any, allchem: Any, result: dict[str, Any], *, smiles: str | None, fmt: str
) -> None:
    """Compare the editor's own SMILES against RDKit's reading of the block.

    An empty SMILES is not an error — it is the expected outcome for query structures, which
    is exactly what a SMARTS query is drawn from. A *disagreement*, though, is the two-engine
    failure this service exists to surface, so it is reported.
    """
    candidate = (smiles or "").strip()
    if not candidate or not result.get("ok"):
        return
    ours = result.get("canonical_smiles")
    if not ours:
        return

    with _quiet(chem):
        try:
            if fmt == "rxn":
                parsed = allchem.ReactionFromSmarts(candidate, useSmiles=True)
                # Canonicalize the editor's reaction through the same path as ours, so the
                # comparison tests the chemistry rather than each writer's component ordering.
                theirs = (
                    _reaction_smiles(chem, _reaction_components(chem, parsed))
                    if parsed is not None
                    else None
                )
            else:
                mol = chem.MolFromSmiles(candidate)
                theirs = chem.MolToSmiles(mol) if mol is not None else None
        except Exception:
            theirs = None

    if theirs is None:
        result["warnings"].append(
            _issue(
                "drawn_smiles_not_readable",
                "The editor's own text form of this structure could not be read back. The "
                "drawing itself was used instead, which is the more reliable record.",
            )
        )
        return
    if theirs != ours:
        result["warnings"].append(
            _issue(
                "drawn_smiles_differs",
                "The editor's text form of this structure does not match the drawing it came "
                f"from. The drawing was used: {ours}",
            )
        )


class _quiet:
    """Silence RDKit's console logging for one parse; problems are reported structurally."""

    def __init__(self, chem: Any) -> None:
        self._chem = chem
        self._block = None

    def __enter__(self) -> None:
        try:
            from rdkit import rdBase  # noqa: PLC0415

            self._block = rdBase.BlockLogs()
        except Exception:
            self._block = None

    def __exit__(self, *exc: object) -> None:
        self._block = None


# --------------------------------------------------------------------------------------
# Endpoint 3 — SMARTS matching
# --------------------------------------------------------------------------------------


def match_smarts(*, smarts: str, targets: list[str]) -> dict[str, Any]:
    """Match one SMARTS query against target SMILES, using the R6 screen's engine.

    Deliberately the same RDKit code path as ``reaction_safety`` rather than a second matcher:
    two SMARTS engines in one product drift apart, and the safety screen is the one with an
    expert-review gate already built around it.
    """
    chem, _allchem, _rdrxn = _load_rdkit()
    if chem is None:  # pragma: no cover - rdkit is installed in this deployment
        raise ReactionError("Structure matching is not available in this deployment.")

    query = (smarts or "").strip()
    if not query:
        raise ReactionError("Enter a query structure to search for.")
    if len(query) > MAX_SMARTS_CHARS:
        raise ReactionError("That query structure is too long to use.")
    if len(targets) > MAX_SMARTS_TARGETS:
        raise ReactionError(
            f"Too many structures to check at once (limit {MAX_SMARTS_TARGETS})."
        )

    with _quiet(chem):
        pattern = chem.MolFromSmarts(query)
    if pattern is None:
        raise ReactionError("That query structure could not be read as a search pattern.")

    results: list[dict[str, Any]] = []
    for target in targets:
        with _quiet(chem):
            mol = chem.MolFromSmiles(target) if target else None
        if mol is None:
            # Fail visible, not silent: an unreadable target is reported as unreadable rather
            # than folded in with the genuine non-matches.
            results.append(
                {"smiles": target, "parsed": False, "matched": False, "match_count": 0,
                 "atom_indices": []}
            )
            continue
        matches = mol.GetSubstructMatches(pattern)
        results.append(
            {
                "smiles": target,
                "parsed": True,
                "matched": bool(matches),
                "match_count": len(matches),
                "atom_indices": [int(i) for i in matches[0]] if matches else [],
            }
        )

    return {
        "smarts": query,
        "results": results,
        "matched_count": sum(1 for r in results if r["matched"]),
        "unreadable_count": sum(1 for r in results if not r["parsed"]),
    }


# --------------------------------------------------------------------------------------
# Endpoint 2 — persistence: a captured scheme attached to a reaction project
#
# Both blocks are retained. The source block is what the chemist drew and is the audit record;
# the normalized block is what downstream code should compute on. Storing only one of them
# would either lose the original intent or force every consumer to re-derive it.
# --------------------------------------------------------------------------------------


def _json_dump(value: Any) -> str:
    return json.dumps(
        value if value is not None else {}, sort_keys=True, separators=(",", ":"), default=str
    )


def _json_list(value: str | None) -> list[dict[str, Any]]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _project_or_raise(session: Session, project_id: int) -> ReactionProjectORM:
    row = session.get(ReactionProjectORM, project_id)
    if row is None:
        raise KeyError("Reaction project not found.")
    return row


def _actor_label(actor: ReactionActor) -> str:
    if actor.email:
        return actor.email
    if actor.user_id is not None:
        return f"user:{actor.user_id}"
    return "system"


def _audit(
    session: Session,
    *,
    actor: ReactionActor,
    event_type: str,
    message: str,
    entity_id: int | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEventORM(
            event_type=event_type,
            message=message,
            actor_user_id=actor.user_id,
            actor_email=actor.email,
            entity_type="reaction_structure_scheme",
            entity_id=entity_id,
            metadata_json=_json_dump(metadata or {}),
        )
    )


def _to_record(row: ReactionStructureSchemeORM) -> dict[str, Any]:
    return {
        "id": row.id,
        "reaction_project_id": row.reaction_project_id,
        "name": row.name or None,
        "format": row.format,
        "source_block": row.source_block,
        "normalized_block": row.normalized_block or None,
        "canonical_smiles": row.canonical_smiles or None,
        "inchikey": row.inchikey or None,
        "atom_count": row.atom_count,
        "bond_count": row.bond_count,
        "component_counts": _json_dict(row.component_counts_json) or None,
        "warnings": _json_list(row.warnings_json),
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "reason_for_change": row.reason_for_change,
        "deleted_at": row.deleted_at,
        "deleted_by": row.deleted_by,
        "metadata_json": _json_dict(row.metadata_json),
    }


def create_scheme(
    session_factory: sessionmaker[Session],
    project_id: int,
    payload: Any,
    *,
    actor: ReactionActor,
) -> dict[str, Any]:
    """Validate a captured drawing and attach it to a reaction project.

    A drawing RDKit cannot read is refused rather than stored: attaching it would let the rest
    of the product treat an unreadable structure as a checked one. Warnings, by contrast, are
    stored alongside the scheme — they are information the chemist has been shown, not a bar
    to attaching.
    """
    verdict = validate_structure(
        block=payload.block, fmt=payload.format, smiles=payload.smiles
    )
    if not verdict["ok"]:
        first = verdict["errors"][0]["message"] if verdict["errors"] else (
            "This drawing could not be checked."
        )
        raise ReactionError(first)

    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        row = ReactionStructureSchemeORM(
            reaction_project_id=project_id,
            name=(payload.name or "").strip(),
            format=verdict["format"],
            source_block=payload.block,
            normalized_block=verdict["normalized_block"] or "",
            canonical_smiles=verdict["canonical_smiles"] or "",
            inchikey=verdict["inchikey"] or "",
            atom_count=verdict["atom_count"],
            bond_count=verdict["bond_count"],
            component_counts_json=_json_dump(verdict["component_counts"] or {}),
            warnings_json=_json_dump(verdict["warnings"]),
            created_by_user_id=actor.user_id,
            metadata_json=_json_dump(payload.metadata_json),
        )
        session.add(row)
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.structure_scheme.created",
            message=f"Attached a {verdict['format']} scheme to reaction project {project_id}.",
            entity_id=row.id,
            metadata={
                "reaction_project_id": project_id,
                "format": verdict["format"],
                "canonical_smiles": verdict["canonical_smiles"],
                "inchikey": verdict["inchikey"],
                "warning_codes": [w["code"] for w in verdict["warnings"]],
            },
        )
        session.flush()
        return _to_record(row)


def list_schemes(
    session_factory: sessionmaker[Session],
    project_id: int,
    *,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    """List a project's schemes, newest first. Soft-deleted rows are excluded by default."""
    with session_scope(session_factory) as session:
        _project_or_raise(session, project_id)
        stmt = select(ReactionStructureSchemeORM).where(
            ReactionStructureSchemeORM.reaction_project_id == project_id
        )
        if not include_deleted:
            stmt = stmt.where(ReactionStructureSchemeORM.deleted_at.is_(None))
        rows = session.execute(
            stmt.order_by(ReactionStructureSchemeORM.created_at.desc(),
                          ReactionStructureSchemeORM.id.desc())
        ).scalars().all()
        return [_to_record(row) for row in rows]


def get_scheme(
    session_factory: sessionmaker[Session],
    project_id: int,
    scheme_id: int,
    *,
    include_deleted: bool = False,
) -> dict[str, Any] | None:
    with session_scope(session_factory) as session:
        row = session.get(ReactionStructureSchemeORM, scheme_id)
        if row is None or row.reaction_project_id != project_id:
            return None
        if row.deleted_at is not None and not include_deleted:
            return None
        return _to_record(row)


def delete_scheme(
    session_factory: sessionmaker[Session],
    project_id: int,
    scheme_id: int,
    *,
    reason: str | None,
    actor: ReactionActor,
) -> dict[str, Any] | None:
    """Soft-delete a scheme: retained in full, marked removed, with the reason recorded.

    Never a physical delete — the record endures so the removal is reversible-by-record and
    inspectable (ALCOA+, Security Prompt 12).
    """
    with session_scope(session_factory) as session:
        row = session.get(ReactionStructureSchemeORM, scheme_id)
        if row is None or row.reaction_project_id != project_id:
            return None
        if row.deleted_at is not None:
            return _to_record(row)
        apply_soft_delete(
            row, reason=reason, actor=_actor_label(actor), now=utcnow()
        )
        session.flush()
        _audit(
            session,
            actor=actor,
            event_type="reaction.structure_scheme.deleted",
            message=f"Removed a scheme from reaction project {project_id}.",
            entity_id=row.id,
            metadata={
                "reaction_project_id": project_id,
                "reason_for_change": row.reason_for_change,
            },
        )
        session.flush()
        return _to_record(row)
