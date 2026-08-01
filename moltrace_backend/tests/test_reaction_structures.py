"""Structure & reaction scheme service: RDKit as the authority over the drawing editor.

The premise these tests defend is that Ketcher's in-browser engine draws and RDKit decides. A
drawing that RDKit reads differently must say so out loud, because a chemist who draws one
thing and gets another stored without being told is the worst outcome this service can produce.

So the coverage splits three ways:

* the engine reads what the declared ``format`` says it is, and refuses to guess;
* a structure changed by checking produces a warning, while a structure merely *re-written*
  (aromatic perception, Kekulé form) produces none — warning noise on every phenyl ring would
  train reviewers to ignore the panel, which is worse than no panel;
* the persistence layer keeps both blocks, owner-scopes access, and archives rather than
  destroys.
"""

from fastapi.testclient import TestClient
from rdkit import Chem
from rdkit.Chem import AllChem

from nmrcheck import reaction_structures as rs
from nmrcheck.compound_registry_store import derive_structure_metadata

# Blocks are generated through RDKit rather than hand-written: MDL atom lines are fixed-width,
# and a hand-typed block fails to parse for reasons that have nothing to do with the chemistry
# under test.
ASPIRIN_SMILES = "CC(=O)Oc1ccccc1C(=O)O"


def _mol_block(smiles: str, *, kekulize: bool = True) -> str:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None
    return Chem.MolToMolBlock(mol, kekulize=kekulize)


def _rxn_block(reaction_smiles: str) -> str:
    rxn = AllChem.ReactionFromSmarts(reaction_smiles, useSmiles=True)
    assert rxn is not None
    return AllChem.ReactionToRxnBlock(rxn)


def _codes(issues: list[dict]) -> set[str]:
    return {issue["code"] for issue in issues}


# --------------------------------------------------------------------------------------
# Engine: reading a drawing
# --------------------------------------------------------------------------------------


def test_molecule_is_canonicalized_with_an_inchikey():
    result = rs.validate_structure(
        block=_mol_block(ASPIRIN_SMILES), fmt="mol", smiles=ASPIRIN_SMILES
    )
    assert result["ok"] is True
    assert result["canonical_smiles"] == ASPIRIN_SMILES
    assert result["inchikey"] == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
    assert result["atom_count"] == 13
    assert result["normalized_block"]
    assert result["errors"] == []


def test_reaction_reports_component_counts_and_no_inchikey():
    result = rs.validate_structure(
        block=_rxn_block("CC(Cl)=O.OCC>>CC(OCC)=O"), fmt="rxn", smiles=""
    )
    assert result["ok"] is True
    assert result["component_counts"] == {"reactants": 2, "agents": 0, "products": 1}
    # A reaction is not one compound, so a key naming one would be a lie.
    assert result["inchikey"] is None
    assert result["canonical_smiles"] == "CC(=O)Cl.CCO>>CCOC(C)=O"


def test_format_is_load_bearing_and_never_sniffed():
    """An RXN block declared as a molfile is refused, not silently re-parsed as a reaction.

    Guessing would make the contract's ``format`` field decorative, and the editor genuinely
    cannot produce a molfile for anything carrying a reaction arrow.
    """
    rxn_block = _rxn_block("CC(Cl)=O.OCC>>CC(OCC)=O")
    as_mol = rs.validate_structure(block=rxn_block, fmt="mol", smiles="")
    assert as_mol["ok"] is False
    assert "structure_not_readable" in _codes(as_mol["errors"])

    as_rxn = rs.validate_structure(block=rxn_block, fmt="rxn", smiles="")
    assert as_rxn["ok"] is True


def test_empty_smiles_is_not_an_error():
    """SMILES generation fails on the exact drawings a SMARTS query is made of."""
    result = rs.validate_structure(block=_mol_block(ASPIRIN_SMILES), fmt="mol", smiles="")
    assert result["ok"] is True
    assert result["errors"] == []
    assert "drawn_smiles_differs" not in _codes(result["warnings"])
    assert "drawn_smiles_not_readable" not in _codes(result["warnings"])


def test_query_structure_is_valid_but_gets_no_inchikey():
    result = rs.validate_structure(block=_mol_block("[*:1]CC"), fmt="mol", smiles="")
    assert result["ok"] is True
    assert "query_atoms_present" in _codes(result["warnings"])
    # A key emitted here would name a compound the chemist never drew.
    assert result["inchikey"] is None


def test_impossible_valence_is_reported_against_the_atom():
    mol = Chem.MolFromSmiles("CN(C)(C)C", sanitize=False)
    mol.UpdatePropertyCache(strict=False)
    result = rs.validate_structure(
        block=Chem.MolToMolBlock(mol, kekulize=False), fmt="mol", smiles=""
    )
    assert result["ok"] is False
    (error,) = [e for e in result["errors"] if e["code"] == "impossible_valence"]
    assert error["atom_indices"] == [1]
    assert "Nitrogen" in error["message"]
    assert "4 bonds" in error["message"]


def test_empty_drawing_is_reported_plainly():
    result = rs.validate_structure(block="   ", fmt="mol", smiles="")
    assert result["ok"] is False
    assert _codes(result["errors"]) == {"empty_drawing"}


def test_oversized_block_is_refused_before_parsing():
    result = rs.validate_structure(
        block="x" * (rs.MAX_BLOCK_CHARS + 1), fmt="mol", smiles=""
    )
    assert result["ok"] is False
    assert _codes(result["errors"]) == {"too_large"}


# --------------------------------------------------------------------------------------
# Engine: telling the chemist what changed — and staying quiet when nothing did
# --------------------------------------------------------------------------------------


def test_a_kekulized_aromatic_drawing_produces_no_warnings():
    """The anti-noise invariant.

    Perceiving benzene as aromatic is representation, not a change to the compound. If this
    ever starts warning, every drawing containing a phenyl ring warns, and a warning that
    fires on everything is one reviewers learn to dismiss.
    """
    result = rs.validate_structure(
        block=_mol_block("c1ccccc1O"), fmt="mol", smiles="Oc1ccccc1"
    )
    assert result["ok"] is True
    assert result["warnings"] == []


def test_explicitly_aromatic_bonds_are_reported_as_rewritten_not_as_changed():
    result = rs.validate_structure(
        block=_mol_block("c1ccccc1O", kekulize=False), fmt="mol", smiles=""
    )
    assert result["ok"] is True
    assert "aromatic_rings_written_out" in _codes(result["warnings"])
    # Representation only: the compound itself is untouched.
    assert result["canonical_smiles"] == "Oc1ccccc1"
    assert "hydrogen_count_changed" not in _codes(result["warnings"])


def test_editor_smiles_that_disagrees_with_the_drawing_is_surfaced():
    """The two-engine failure this service exists to catch."""
    result = rs.validate_structure(
        block=_mol_block(ASPIRIN_SMILES), fmt="mol", smiles="CCO"
    )
    assert result["ok"] is True
    assert "drawn_smiles_differs" in _codes(result["warnings"])
    # The drawing wins, and the message says which structure was kept.
    assert result["canonical_smiles"] == ASPIRIN_SMILES


def test_unreadable_editor_smiles_falls_back_to_the_drawing():
    result = rs.validate_structure(
        block=_mol_block(ASPIRIN_SMILES), fmt="mol", smiles="not a structure"
    )
    assert result["ok"] is True
    assert "drawn_smiles_not_readable" in _codes(result["warnings"])
    assert result["canonical_smiles"] == ASPIRIN_SMILES


def test_undefined_stereocentres_are_flagged():
    result = rs.validate_structure(block=_mol_block("CC(N)C(=O)O"), fmt="mol", smiles="")
    assert result["ok"] is True
    assert "stereochemistry_undefined" in _codes(result["warnings"])


def test_ordinary_reaction_components_are_not_called_query_structures():
    """Regression: RDKit wraps every atom of an RXN template as a query atom.

    Trusting ``HasQuery()`` on reaction templates labelled every ordinary reaction an R-group
    family — three spurious warnings on a plain esterification.
    """
    result = rs.validate_structure(
        block=_rxn_block("CC(Cl)=O.OCC>>CC(OCC)=O"), fmt="rxn", smiles=""
    )
    assert "query_atoms_present" not in _codes(result["warnings"])


def test_a_genuine_r_group_in_a_reaction_still_warns_and_names_the_component():
    result = rs.validate_structure(
        block=_rxn_block("[*:1]C(=O)Cl.OCC>>[*:1]C(=O)OCC"), fmt="rxn", smiles=""
    )
    flagged = [w for w in result["warnings"] if w["code"] == "query_atoms_present"]
    assert flagged, "an R-group drawn into a reaction must still be reported"
    assert any(w["message"].startswith("In reactant 1,") for w in flagged)


def _rxn_block_with_explicit_hydrogens(reaction_smiles: str) -> str:
    rxn = AllChem.ReactionFromSmarts(reaction_smiles, useSmiles=True)
    rebuilt = AllChem.ChemicalReaction()
    for mol in rxn.GetReactants():
        Chem.SanitizeMol(mol)
        rebuilt.AddReactantTemplate(Chem.AddHs(mol))
    for mol in rxn.GetProducts():
        Chem.SanitizeMol(mol)
        rebuilt.AddProductTemplate(Chem.AddHs(mol))
    return AllChem.ReactionToRxnBlock(rebuilt)


def test_a_reaction_canonicalizes_the_same_however_its_hydrogens_were_drawn():
    """Regression: the hydrogen fix was first applied to molecules only.

    Every atom of a template parsed from an RXN block is a query atom, and plain ``RemoveHs``
    leaves query hydrogens alone — so the same esterification came back as ``CC(=O)Cl.CCO>>…``
    when drawn one way and ``[H]C([H])([H])C(=O)Cl.…`` when drawn the other. One drawing, two
    answers, which is the whole failure this module exists to prevent.
    """
    esterification = "CC(Cl)=O.OCC>>CC(OCC)=O"
    plain = rs.validate_structure(block=_rxn_block(esterification), fmt="rxn", smiles="")
    with_hydrogens = rs.validate_structure(
        block=_rxn_block_with_explicit_hydrogens(esterification), fmt="rxn", smiles=""
    )
    assert plain["ok"] and with_hydrogens["ok"]
    assert plain["canonical_smiles"] == with_hydrogens["canonical_smiles"]
    assert "explicit_hydrogens_folded_in" in _codes(with_hydrogens["warnings"])
    assert plain["warnings"] == []


def test_an_aromatic_reaction_reads_back_as_aromatic_and_warns_only_once():
    """Regression: `ReactionToSmiles` writes query templates in query form.

    A biaryl coupling came back as ``BrC1:C:C:C:C:C:1.…`` — technically parseable, but not
    what a chemist expects to see — and raised the same representational note once per
    aromatic component, which is precisely the alert fatigue the design avoids elsewhere.
    """
    result = rs.validate_structure(
        block=_rxn_block("c1ccccc1Br.OB(O)c1ccccc1>>c1ccccc1-c1ccccc1"),
        fmt="rxn",
        smiles="",
    )
    assert result["ok"] is True
    assert result["canonical_smiles"] == "Brc1ccccc1.OB(O)c1ccccc1>>c1ccc(-c2ccccc2)cc1"
    assert [w["code"] for w in result["warnings"]].count("aromatic_rings_written_out") == 1
    # A whole-drawing note must not be attributed to one component.
    note = next(w for w in result["warnings"] if w["code"] == "aromatic_rings_written_out")
    assert not note["message"].startswith("In ")
    # Both forms must survive a round trip.
    assert AllChem.ReactionFromSmarts(result["canonical_smiles"], useSmiles=True) is not None
    assert AllChem.ReactionFromRxnBlock(result["normalized_block"]) is not None


def test_a_reactions_canonical_form_does_not_depend_on_the_order_it_was_drawn_in():
    """`A.B>>C` and `B.A>>C` are the same reaction, so they must canonicalize identically.

    Regression, and a sharp one: while components were left in drawing order, feeding the
    service its *own* canonical SMILES back raised `drawn_smiles_differs` on three of four
    test reactions — purely because RDKit's reaction writer orders components differently.
    The one warning whose whole job is to catch genuine two-engine disagreement was crying
    wolf on most reactions, which is worse than not having it.
    """
    one_way = rs.validate_structure(
        block=_rxn_block("OCC.CC(Cl)=O>>CC(OCC)=O"), fmt="rxn", smiles=""
    )
    other_way = rs.validate_structure(
        block=_rxn_block("CC(Cl)=O.OCC>>CC(OCC)=O"), fmt="rxn", smiles=""
    )
    assert one_way["canonical_smiles"] == other_way["canonical_smiles"]

    # Feeding our own answer back must be silent.
    echoed = rs.validate_structure(
        block=_rxn_block("C[C@H](N)C(=O)O.CCO>>C[C@H](N)C(=O)OCC"),
        fmt="rxn",
        smiles=rs.validate_structure(
            block=_rxn_block("C[C@H](N)C(=O)O.CCO>>C[C@H](N)C(=O)OCC"), fmt="rxn", smiles=""
        )["canonical_smiles"],
    )
    assert "drawn_smiles_differs" not in _codes(echoed["warnings"])

    # But a real disagreement must still be caught — the check has to stay useful.
    genuine = rs.validate_structure(
        block=_rxn_block("CC(Cl)=O.OCC>>CC(OCC)=O"), fmt="rxn", smiles="CCO.CCO>>CCOCC"
    )
    assert "drawn_smiles_differs" in _codes(genuine["warnings"])


def test_no_warning_or_error_text_leaks_backend_jargon():
    """Every string here lands on a chemist's screen (feedback_no_backend_jargon_in_user_copy)."""
    banned = (
        "rdkit", "molfrommolblock", "sanitiz", "kekuliz", "exception", "traceback",
        "_json", "backend", "http", "422", "none", "null", "smarts", "valenceerror",
    )
    blocks = [
        (_mol_block(ASPIRIN_SMILES), "mol", "CCO"),
        (_mol_block("c1ccccc1O", kekulize=False), "mol", ""),
        (_mol_block("[*:1]CC"), "mol", ""),
        (_mol_block("CC(N)C(=O)O"), "mol", ""),
        (_rxn_block("[*:1]C(=O)Cl.OCC>>[*:1]C(=O)OCC"), "rxn", ""),
        ("", "mol", ""),
        ("x" * (rs.MAX_BLOCK_CHARS + 1), "mol", ""),
    ]
    seen = 0
    for block, fmt, smiles in blocks:
        result = rs.validate_structure(block=block, fmt=fmt, smiles=smiles)
        for issue in result["warnings"] + result["errors"]:
            seen += 1
            lowered = issue["message"].lower()
            for word in banned:
                assert word not in lowered, f"{issue['code']} leaks {word!r}: {issue['message']}"
    assert seen > 0, "the jargon sweep must actually have messages to inspect"


# --------------------------------------------------------------------------------------
# One product, one answer: this validator vs the compound registry's canonicalizer
# --------------------------------------------------------------------------------------


def test_this_validator_and_the_compound_registry_canonicalize_identically():
    """Two canonicalizers in one backend is the same drift risk as two chemistry engines.

    ``compound_registry_store.derive_structure_metadata`` already canonicalizes a molblock, and
    a chemist can reach both paths with the same drawing. If they ever disagree, the registry
    and the editor panel show different structures for one drawing.

    This caught a real defect: parsing with ``removeHs=False`` — which this module must do so
    its sanitization diff compares like with like — reported ethanol drawn with explicit
    hydrogens as ``[H]OC([H])([H])C([H])([H])[H]`` while the registry said ``CCO``.
    """
    cases = [
        "CCO",
        ASPIRIN_SMILES,
        "c1ccccc1O",
        "C[C@H](N)C(=O)O",       # defined stereocentre
        "[2H]C(Cl)(Cl)Cl",       # isotope label must survive
        "CC(=O)[O-].[Na+]",      # salt: two components
    ]
    for smiles in cases:
        for explicit_hydrogens in (False, True):
            mol = Chem.MolFromSmiles(smiles)
            if explicit_hydrogens:
                mol = Chem.AddHs(mol)
            AllChem.Compute2DCoords(mol)
            block = Chem.MolToMolBlock(mol)

            registry = derive_structure_metadata(block, "mol")
            mine = rs.validate_structure(block=block, fmt="mol", smiles="")

            label = f"{smiles}{' with explicit hydrogens' if explicit_hydrogens else ''}"
            assert mine["canonical_smiles"] == registry.canonical_smiles, label
            assert mine["inchikey"] == registry.inchikey, label


def test_folding_in_drawn_hydrogens_is_reported_but_isotope_labels_are_kept():
    with_hydrogens = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    AllChem.Compute2DCoords(with_hydrogens)
    folded = rs.validate_structure(
        block=Chem.MolToMolBlock(with_hydrogens), fmt="mol", smiles=""
    )
    assert folded["canonical_smiles"] == "CCO"
    assert "explicit_hydrogens_folded_in" in _codes(folded["warnings"])

    # A deuterium is information, not clutter: RDKit keeps it, so nothing was folded away.
    deuterated = Chem.AddHs(Chem.MolFromSmiles("[2H]C(Cl)(Cl)Cl"))
    AllChem.Compute2DCoords(deuterated)
    kept = rs.validate_structure(block=Chem.MolToMolBlock(deuterated), fmt="mol", smiles="")
    assert kept["canonical_smiles"] == "[2H]C(Cl)(Cl)Cl"
    assert "explicit_hydrogens_folded_in" not in _codes(kept["warnings"])


def test_the_compound_registry_does_not_accept_reactions():
    """Why reactions need this service at all, asserted rather than assumed.

    The registry's format enum has no ``rxn`` — that is the registry stating a reaction is not
    a compound structure. Widening it would be the wrong fix; reactions belong to a project.
    """
    from nmrcheck.models import CompoundStructureRecordCreate

    allowed = CompoundStructureRecordCreate.model_fields["structure_format"].annotation
    assert "rxn" not in str(allowed)


# --------------------------------------------------------------------------------------
# Engine: SMARTS matching
# --------------------------------------------------------------------------------------


def test_smarts_match_reports_hits_misses_and_unreadable_targets_separately():
    result = rs.match_smarts(
        smarts="[NX3][CX3](=O)", targets=["CC(=O)NC", "CCO", "definitely not a structure"]
    )
    assert result["matched_count"] == 1
    # An unreadable target is reported as unreadable, never folded in with the genuine misses.
    assert result["unreadable_count"] == 1
    by_smiles = {r["smiles"]: r for r in result["results"]}
    assert by_smiles["CC(=O)NC"]["matched"] is True
    assert by_smiles["CC(=O)NC"]["atom_indices"]
    assert by_smiles["CCO"]["parsed"] is True and by_smiles["CCO"]["matched"] is False


def test_unreadable_smarts_is_a_plain_language_refusal():
    try:
        rs.match_smarts(smarts="[[[", targets=["CCO"])
    except rs.ReactionError as exc:
        assert "could not be read" in str(exc)
    else:  # pragma: no cover - the query above is not a valid pattern
        raise AssertionError("an unreadable query pattern must be refused")


# --------------------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------------------


def _sign_up(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _project(client: TestClient, headers: dict[str, str]) -> int:
    res = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": "Scheme project", "objective": "maximize_yield", "status": "active"},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_validate_route_answers_200_even_when_the_structure_is_unsound(
    client: TestClient, api_headers: dict[str, str]
):
    """The verdict belongs in the body. Asking "is this sound?" and hearing "no" succeeded."""
    mol = Chem.MolFromSmiles("CN(C)(C)C", sanitize=False)
    mol.UpdatePropertyCache(strict=False)
    res = client.post(
        "/reactions/structures/validate",
        headers=api_headers,
        json={"block": Chem.MolToMolBlock(mol, kekulize=False), "format": "mol", "smiles": ""},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is False
    assert body["errors"][0]["code"] == "impossible_valence"


def test_validate_route_rejects_an_extra_key(client: TestClient, api_headers: dict[str, str]):
    """The models are ``extra="forbid"``; an extra key is a 100%-reproducible 422."""
    res = client.post(
        "/reactions/structures/validate",
        headers=api_headers,
        json={
            "block": _mol_block(ASPIRIN_SMILES),
            "format": "mol",
            "smiles": "",
            "molfile": "duplicate of block",
        },
    )
    assert res.status_code == 422, res.text


def test_attaching_a_scheme_keeps_both_the_drawing_and_the_normalized_form(
    client: TestClient, api_headers: dict[str, str]
):
    project_id = _project(client, api_headers)
    source = _mol_block(ASPIRIN_SMILES, kekulize=False)
    res = client.post(
        f"/reaction-projects/{project_id}/schemes",
        headers=api_headers,
        json={"block": source, "format": "mol", "smiles": "", "name": "Aspirin"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    # Both, not one: the source is the audit record, the normalized form is what downstream
    # chemistry computes on.
    assert body["source_block"] == source
    assert body["normalized_block"] and body["normalized_block"] != source
    assert body["canonical_smiles"] == ASPIRIN_SMILES
    assert body["inchikey"] == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
    # The warnings shown at capture time are retained with the record.
    assert "aromatic_rings_written_out" in {w["code"] for w in body["warnings"]}


def test_a_reaction_scheme_attaches_and_survives_a_round_trip(
    client: TestClient, api_headers: dict[str, str]
):
    """The primary case: a reaction is what the compound registry cannot hold."""
    project_id = _project(client, api_headers)
    source = _rxn_block("CC(Cl)=O.OCC>>CC(OCC)=O")
    res = client.post(
        f"/reaction-projects/{project_id}/schemes",
        headers=api_headers,
        json={"block": source, "format": "rxn", "smiles": "", "name": "Step 3"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["format"] == "rxn"
    assert body["canonical_smiles"] == "CC(=O)Cl.CCO>>CCOC(C)=O"
    assert body["component_counts"] == {"reactants": 2, "agents": 0, "products": 1}
    # A reaction is not one compound.
    assert body["inchikey"] is None
    # What we stored must be readable back as a reaction, or downstream cannot use it.
    assert AllChem.ReactionFromRxnBlock(body["normalized_block"]) is not None
    assert body["source_block"] == source

    fetched = client.get(
        f"/reaction-projects/{project_id}/schemes/{body['id']}", headers=api_headers
    )
    assert fetched.status_code == 200
    assert fetched.json()["canonical_smiles"] == body["canonical_smiles"]


def test_an_unreadable_drawing_is_not_attached(
    client: TestClient, api_headers: dict[str, str]
):
    """Storing it would let the rest of the product treat an unchecked structure as checked."""
    project_id = _project(client, api_headers)
    res = client.post(
        f"/reaction-projects/{project_id}/schemes",
        headers=api_headers,
        json={"block": "not a molfile at all", "format": "mol", "smiles": ""},
    )
    assert res.status_code == 400, res.text
    listed = client.get(
        f"/reaction-projects/{project_id}/schemes", headers=api_headers
    )
    assert listed.json() == []


def test_schemes_are_owner_scoped_with_a_non_leaking_404(client: TestClient):
    owner = _sign_up(client, "scheme-owner@example.com")
    intruder = _sign_up(client, "scheme-intruder@example.com")
    project_id = _project(client, owner)
    created = client.post(
        f"/reaction-projects/{project_id}/schemes",
        headers=owner,
        json={"block": _mol_block(ASPIRIN_SMILES), "format": "mol", "smiles": ""},
    )
    assert created.status_code == 201, created.text
    scheme_id = created.json()["id"]

    for response in (
        client.get(f"/reaction-projects/{project_id}/schemes", headers=intruder),
        client.get(f"/reaction-projects/{project_id}/schemes/{scheme_id}", headers=intruder),
        client.post(
            f"/reaction-projects/{project_id}/schemes",
            headers=intruder,
            json={"block": _mol_block("CCO"), "format": "mol", "smiles": ""},
        ),
    ):
        assert response.status_code == 404, response.text
        # Non-leaking: the same answer a missing project gives.
        assert response.json()["detail"] == "Not found."


def test_archiving_retains_the_record_and_requires_a_reason(
    client: TestClient, api_headers: dict[str, str]
):
    project_id = _project(client, api_headers)
    created = client.post(
        f"/reaction-projects/{project_id}/schemes",
        headers=api_headers,
        json={"block": _mol_block(ASPIRIN_SMILES), "format": "mol", "smiles": ""},
    )
    scheme_id = created.json()["id"]

    blank = client.post(
        f"/reaction-projects/{project_id}/schemes/{scheme_id}/archive",
        headers=api_headers,
        json={"reason_for_change": ""},
    )
    assert blank.status_code == 422, blank.text

    archived = client.post(
        f"/reaction-projects/{project_id}/schemes/{scheme_id}/archive",
        headers=api_headers,
        json={"reason_for_change": "Superseded by the revised route."},
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["deleted_at"] is not None
    assert archived.json()["reason_for_change"] == "Superseded by the revised route."

    default_list = client.get(
        f"/reaction-projects/{project_id}/schemes", headers=api_headers
    )
    assert default_list.json() == []

    # Retained, not destroyed: still inspectable on request.
    with_archived = client.get(
        f"/reaction-projects/{project_id}/schemes?include_deleted=true", headers=api_headers
    )
    assert [row["id"] for row in with_archived.json()] == [scheme_id]
    assert with_archived.json()[0]["source_block"]


def test_smarts_match_route_uses_the_shared_engine(
    client: TestClient, api_headers: dict[str, str]
):
    res = client.post(
        "/reactions/structures/smarts-match",
        headers=api_headers,
        json={"smarts": "[NX3][CX3](=O)", "targets": ["CC(=O)NC", "CCO"]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["matched_count"] == 1
