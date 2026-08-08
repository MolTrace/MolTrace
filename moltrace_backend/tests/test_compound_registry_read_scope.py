"""Who can read a compound someone else registered.

This reverses a decision that was deliberate and documented, so the reasoning
for the reversal belongs next to it. ``update_compound`` carried:

    Reads stay open deliberately. A compound registry is a shared reference:
    people look up structures registered by colleagues, and closing reads
    would break the feature rather than secure it.

That is a fair description of one lab. It is the wrong default for a hosted
multi-tenant product: probed live, a second account read another account's
preferred name, registry id and InChIKey, and found the row by searching for the
registry id. For a pharma customer a compound's *existence under a code name* is
the confidential part -- the structure has not been disclosed yet, and the
registry id is the thing that leaks a program.

So the shared-reference case is kept and made explicit rather than deleted:

* ``compound_registry_visibility="owner"`` (default) -- you see what you
  registered. Admins and the system api key still see everything.
* ``compound_registry_visibility="shared"`` -- the previous behaviour, for a
  single-lab deployment where the registry really is a shared reference.

Two details that follow from the threat rather than from habit:

* A miss is **404, not 403**. Existence is the secret here. A 403 on
  ``/compounds/{id}`` confirms a compound exists at that id, and the ids are
  sequential, so 403 hands over an enumerable index of how many compounds a
  competitor tenant has registered.
* Child records inherit the parent compound's scope. Every child table --
  structures, aliases, batches, aliquots, relationships, evidence links --
  links back to a compound, so the alias list is exactly as sensitive as the
  compound and must not be the way around the check.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _app(tmp_path, **overrides):
    return create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'registry_scope.sqlite3'}",
            require_verified_email=False,
            api_key="test-key",
            raw_vault_dir=str(tmp_path / "vault"),
            raw_data_vault_dir=str(tmp_path / "vault"),
            **overrides,
        )
    )


def _signup(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _register(client: TestClient, headers: dict[str, str], name: str, registry_id: str) -> int:
    res = client.post(
        "/compound-registry/compounds",
        headers=headers,
        json={
            "preferred_name": name,
            "registry_id": registry_id,
            "original_structure_input": "CCO",
            "original_structure_format": "smiles",
        },
    )
    assert res.status_code == 201, res.text
    return int(res.json()["id"])


@pytest.fixture
def owner_scoped(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        yield client


@pytest.fixture
def shared(tmp_path):
    client = TestClient(_app(tmp_path, compound_registry_visibility="shared"))
    with client:
        yield client


class TestOwnerScopedIsTheDefault:
    def test_a_stranger_cannot_read_the_compound(self, owner_scoped) -> None:
        alice = _signup(owner_scoped, "alice@example.com")
        bob = _signup(owner_scoped, "bob@example.com")
        compound_id = _register(owner_scoped, alice, "Lead series A", "ACME-0001")

        res = owner_scoped.get(f"/compound-registry/compounds/{compound_id}", headers=bob)
        assert res.status_code == 404, (
            f"another account read the compound: {res.status_code} {res.text[:200]}"
        )

    def test_the_miss_is_404_so_ids_stay_unenumerable(self, owner_scoped) -> None:
        """403 would confirm the row exists, and the ids are sequential."""
        alice = _signup(owner_scoped, "alice2@example.com")
        bob = _signup(owner_scoped, "bob2@example.com")
        compound_id = _register(owner_scoped, alice, "Lead series B", "ACME-0002")

        existing = owner_scoped.get(f"/compound-registry/compounds/{compound_id}", headers=bob)
        absent = owner_scoped.get("/compound-registry/compounds/999999", headers=bob)
        assert existing.status_code == absent.status_code == 404
        assert existing.json() == absent.json(), (
            "a compound that exists is distinguishable from one that does not"
        )

    def test_the_list_shows_only_your_own(self, owner_scoped) -> None:
        alice = _signup(owner_scoped, "alice3@example.com")
        bob = _signup(owner_scoped, "bob3@example.com")
        _register(owner_scoped, alice, "Alice compound", "ACME-0003")
        _register(owner_scoped, bob, "Bob compound", "BOB-0001")

        res = owner_scoped.get("/compound-registry/compounds", headers=bob)
        assert res.status_code == 200, res.text
        names = [row["preferred_name"] for row in res.json()]
        assert names == ["Bob compound"], f"the list leaked: {names}"

    def test_search_is_not_the_way_around_the_list(self, owner_scoped) -> None:
        """The registry id is exactly what a competitor would search for.

        Both surfaces are probed with the method and body each actually accepts.
        `/search` is a POST, and a GET returns 405 -- which says nothing about
        whether the search leaks, so probing it the wrong way would have
        recorded a pass for a route that was never exercised.
        """
        alice = _signup(owner_scoped, "alice4@example.com")
        bob = _signup(owner_scoped, "bob4@example.com")
        _register(owner_scoped, alice, "Confidential lead", "ACME-SECRET-01")

        listed = owner_scoped.get("/compound-registry/compounds?q=ACME-SECRET", headers=bob)
        assert listed.status_code == 200, listed.text
        assert listed.json() == [], f"the q= filter leaked: {listed.json()}"

        for body in (
            {"registry_id": "ACME-SECRET-01"},
            {"name": "Confidential"},
            {"inchikey": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"},
        ):
            res = owner_scoped.post("/compound-registry/search", headers=bob, json=body)
            assert res.status_code == 200, f"{body} -> {res.status_code} {res.text[:200]}"
            payload = res.json()
            rows = payload if isinstance(payload, list) else payload.get("compounds", [])
            assert rows == [], f"search by {body} leaked another account's compound: {rows}"

    @pytest.mark.parametrize(
        "suffix", ["structures", "aliases", "relationships", "evidence-links"]
    )
    def test_child_records_inherit_the_parent_scope(self, owner_scoped, suffix) -> None:
        """The alias list is as sensitive as the compound it belongs to."""
        alice = _signup(owner_scoped, f"alice-{suffix}@example.com")
        bob = _signup(owner_scoped, f"bob-{suffix}@example.com")
        compound_id = _register(owner_scoped, alice, "Parent", f"ACME-{suffix}")

        res = owner_scoped.get(
            f"/compound-registry/compounds/{compound_id}/{suffix}", headers=bob
        )
        assert res.status_code == 404, (
            f"{suffix} was readable on another account's compound: "
            f"{res.status_code} {res.text[:200]}"
        )

    def test_the_write_refusal_stops_leaking_existence_too(self, owner_scoped) -> None:
        """The write route justified its 403 with "reads are open". They are not now.

        Left as 403, the PATCH would confirm a compound exists at an id the
        caller cannot read -- handing back exactly what scoping the reads was
        meant to take away.
        """
        alice = _signup(owner_scoped, "alice-write@example.com")
        bob = _signup(owner_scoped, "bob-write@example.com")
        compound_id = _register(owner_scoped, alice, "Not yours", "ACME-0007")

        existing = owner_scoped.patch(
            f"/compound-registry/compounds/{compound_id}",
            headers=bob,
            json={"preferred_name": "renamed"},
        )
        absent = owner_scoped.patch(
            "/compound-registry/compounds/999999",
            headers=bob,
            json={"preferred_name": "renamed"},
        )
        assert existing.status_code == 404, (
            f"the write refusal still distinguishes existence: {existing.status_code}"
        )
        assert existing.json() == absent.json()

    def test_you_can_still_read_your_own(self, owner_scoped) -> None:
        """The scope must not break the feature for its owner."""
        alice = _signup(owner_scoped, "alice5@example.com")
        compound_id = _register(owner_scoped, alice, "Mine", "ACME-0005")

        assert (
            owner_scoped.get(
                f"/compound-registry/compounds/{compound_id}", headers=alice
            ).status_code
            == 200
        )
        assert (
            owner_scoped.get(
                f"/compound-registry/compounds/{compound_id}/aliases", headers=alice
            ).status_code
            == 200
        )

    def test_an_admin_still_sees_everything(self, owner_scoped) -> None:
        alice = _signup(owner_scoped, "alice6@example.com")
        compound_id = _register(owner_scoped, alice, "Ops visible", "ACME-0006")

        res = owner_scoped.get(
            f"/compound-registry/compounds/{compound_id}", headers={"x-api-key": "test-key"}
        )
        assert res.status_code == 200, res.text


class TestYouCannotAttachToSomeoneElsesCompound:
    """The other half of the same hole, closed in the same change.

    Scoping the reads alone would have been a half-applied guard: eight write
    functions resolved a compound through the unscoped ``_require_compound``, so
    a stranger could still hang an alias, structure record, batch, aliquot,
    relationship or evidence link off a compound they could not read -- and the
    201-vs-404 would confirm the compound existed.

    Attaching stays owner-scoped in **both** visibility modes, matching the
    compound PATCH: looking up a colleague's compound is reasonable, editing
    what hangs off it is not.
    """

    @pytest.mark.parametrize(
        ("suffix", "body"),
        [
            ("aliases", {"alias": "planted", "alias_type": "internal_code"}),
            (
                "structures",
                {"structure_input": "CCO", "structure_format": "smiles"},
            ),
        ],
    )
    def test_a_stranger_cannot_attach_a_child_record(
        self, owner_scoped, suffix, body
    ) -> None:
        alice = _signup(owner_scoped, f"alice-attach-{suffix}@example.com")
        bob = _signup(owner_scoped, f"bob-attach-{suffix}@example.com")
        compound_id = _register(owner_scoped, alice, "Target", f"ACME-ATT-{suffix}")

        res = owner_scoped.post(
            f"/compound-registry/compounds/{compound_id}/{suffix}", headers=bob, json=body
        )
        assert res.status_code == 404, (
            f"a stranger attached a {suffix} record to another account's compound: "
            f"{res.status_code} {res.text[:200]}"
        )

    def test_a_stranger_cannot_create_a_batch_on_it(self, owner_scoped) -> None:
        alice = _signup(owner_scoped, "alice-batch@example.com")
        bob = _signup(owner_scoped, "bob-batch@example.com")
        compound_id = _register(owner_scoped, alice, "Target", "ACME-BATCH")

        res = owner_scoped.post(
            "/compound-registry/batches",
            headers=bob,
            json={"compound_id": compound_id, "batch_code": "PLANTED-001"},
        )
        assert res.status_code == 404, (
            f"a stranger created a batch on another account's compound: "
            f"{res.status_code} {res.text[:200]}"
        )

    def test_the_refusal_is_not_a_500(self, owner_scoped) -> None:
        """CompoundRegistryAccessError does not inherit CompoundRegistryError.

        Without an explicit branch in the error mapper it falls through to a
        bare re-raise, and a correctly-refused attach surfaces as a server
        error -- which reads as "MolTrace is broken", not "you may not do that".
        """
        alice = _signup(owner_scoped, "alice-500@example.com")
        bob = _signup(owner_scoped, "bob-500@example.com")
        compound_id = _register(owner_scoped, alice, "Target", "ACME-500")

        res = owner_scoped.post(
            f"/compound-registry/compounds/{compound_id}/aliases",
            headers=bob,
            json={"alias": "planted", "alias_type": "internal_code"},
        )
        assert res.status_code < 500, f"the refusal was a server error: {res.text[:200]}"

    def test_the_owner_can_still_attach(self, owner_scoped) -> None:
        alice = _signup(owner_scoped, "alice-attach-ok@example.com")
        compound_id = _register(owner_scoped, alice, "Mine", "ACME-ATT-OK")

        res = owner_scoped.post(
            f"/compound-registry/compounds/{compound_id}/aliases",
            headers=alice,
            json={"alias": "my alias", "alias_type": "internal_code"},
        )
        assert res.status_code == 201, res.text


class TestSharedModeKeepsTheSingleLabCase:
    """The old behaviour is a supported configuration, not a deleted one."""

    def test_a_colleague_can_read_the_compound(self, shared) -> None:
        alice = _signup(shared, "alice-shared@example.com")
        bob = _signup(shared, "bob-shared@example.com")
        compound_id = _register(shared, alice, "Shared reference", "LAB-0001")

        res = shared.get(f"/compound-registry/compounds/{compound_id}", headers=bob)
        assert res.status_code == 200, (
            f"shared mode did not restore the shared reference: {res.text[:200]}"
        )

    def test_writes_stay_owner_scoped_even_when_reads_are_shared(self, shared) -> None:
        """Sharing a reference is not the same as letting anyone edit it.

        This was already true and must survive the change: looking up a
        colleague's compound is reasonable, renaming it is not.
        """
        alice = _signup(shared, "alice-shared2@example.com")
        bob = _signup(shared, "bob-shared2@example.com")
        compound_id = _register(shared, alice, "Shared reference", "LAB-0002")

        res = shared.patch(
            f"/compound-registry/compounds/{compound_id}",
            headers=bob,
            json={"preferred_name": "renamed by a stranger"},
        )
        assert res.status_code in (403, 404), (
            f"shared reads also opened writes: {res.status_code} {res.text[:200]}"
        )
