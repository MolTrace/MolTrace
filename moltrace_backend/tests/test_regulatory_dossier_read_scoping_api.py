"""Regulatory dossier READS are scoped to the creating user.

A dossier carries created_by_user_id (set from the acting user at create; NULL for a
system api key). Reads are gated by that owner: a bearer caller may read only dossiers
they own (and their sub-resources / by-child records); a system api key or an admin sees
all. Missing and owned-by-another-user both return the same non-leaking 404. Legacy NULL
owners are backfilled from the regulatory.dossier.create audit event (migration 0015).
"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from nmrcheck.api import create_app
from nmrcheck.mobile_store import (
    MobileActor,
    _mobile_can_access_action_item,
    _mobile_can_access_dossier,
)
from nmrcheck.orm import (
    AuditEventORM,
    Base,
    RegulatoryActionItemORM,
    RegulatoryDossierORM,
    UserORM,
)
from nmrcheck.regulatory_intelligence import dossier_owned_by
from nmrcheck.settings import Settings

SYSTEM = {"x-api-key": "test-key"}
ADMIN_EMAIL = "admin@example.com"


def _app(tmp_path):
    return create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'dossier_read_scope.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
            admin_emails=(ADMIN_EMAIL,),
        )
    )


def _sign_up(client: TestClient, email: str) -> dict:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _create_dossier(client: TestClient, headers: dict, title: str = "Read-scope dossier") -> int:
    res = client.post("/regulatory/dossiers", headers=headers, json={"title": title})
    assert res.status_code == 201, res.text
    return res.json()["id"]


# --------------------------------------------------------------------------- #
# Top-level get + sub-resources
# --------------------------------------------------------------------------- #
def test_owner_reads_own_dossier_non_owner_404_system_200(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        bob = _sign_up(client, "bob@example.com")
        did = _create_dossier(client, alice)
        # Top-level GET.
        assert client.get(f"/regulatory/dossiers/{did}", headers=alice).status_code == 200
        assert client.get(f"/regulatory/dossiers/{did}", headers=bob).status_code == 404
        assert client.get(f"/regulatory/dossiers/{did}", headers=SYSTEM).status_code == 200
        # Sub-resources are gated by the same dependency (empty owned dossier still 200s).
        for sub in ("impurity-risk-register", "nitrosamine-cumulative-risk", "batch-assessment"):
            assert client.get(f"/regulatory/dossiers/{did}/{sub}", headers=alice).status_code == 200, sub
            assert client.get(f"/regulatory/dossiers/{did}/{sub}", headers=bob).status_code == 404, sub
            assert client.get(f"/regulatory/dossiers/{did}/{sub}", headers=SYSTEM).status_code == 200, sub


def test_mobile_summary_is_scoped(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        bob = _sign_up(client, "bob@example.com")
        did = _create_dossier(client, alice)
        assert client.get(f"/mobile/regulatory/dossiers/{did}/summary", headers=alice).status_code == 200
        assert client.get(f"/mobile/regulatory/dossiers/{did}/summary", headers=bob).status_code == 404


def test_list_is_scoped_to_owner(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        bob = _sign_up(client, "bob@example.com")
        a = _create_dossier(client, alice, "alice dossier")
        b = _create_dossier(client, bob, "bob dossier")

        def ids(headers):
            res = client.get("/regulatory/dossiers", headers=headers)
            assert res.status_code == 200, res.text
            return {row["id"] for row in res.json()}

        assert ids(alice) == {a}
        assert ids(bob) == {b}
        assert {a, b} <= ids(SYSTEM)  # system sees both


def test_system_created_dossier_is_invisible_to_bearer(tmp_path):
    # owner=NULL (system-key create) -> bearer cannot read or list it; system still can.
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        did = _create_dossier(client, SYSTEM)
        assert client.get(f"/regulatory/dossiers/{did}", headers=alice).status_code == 404
        assert client.get(f"/regulatory/dossiers/{did}", headers=SYSTEM).status_code == 200
        listed = {row["id"] for row in client.get("/regulatory/dossiers", headers=alice).json()}
        assert did not in listed


def test_admin_sees_all_dossiers(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        admin = _sign_up(client, ADMIN_EMAIL)
        bob = _sign_up(client, "bob@example.com")
        did = _create_dossier(client, bob)
        # Admin is collapsed to the unrestricted scope, like a system key.
        assert client.get(f"/regulatory/dossiers/{did}", headers=admin).status_code == 200
        listed = {row["id"] for row in client.get("/regulatory/dossiers", headers=admin).json()}
        assert did in listed


def test_404_is_non_leaking(tmp_path):
    # Another user's dossier and a truly-missing id return identical responses.
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        bob = _sign_up(client, "bob@example.com")
        did = _create_dossier(client, alice)
        unowned = client.get(f"/regulatory/dossiers/{did}", headers=bob)
        missing = client.get("/regulatory/dossiers/999999", headers=bob)
        assert unowned.status_code == missing.status_code == 404
        assert unowned.json() == missing.json()


# --------------------------------------------------------------------------- #
# By-child-id reads (no dossier in the path) — readiness report
# --------------------------------------------------------------------------- #
def test_by_child_readiness_report_is_scoped_via_parent(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        bob = _sign_up(client, "bob@example.com")
        did = _create_dossier(client, alice)
        created = client.post(f"/regulatory/dossiers/{did}/readiness-report", headers=alice, json={})
        assert created.status_code == 201, created.text
        report_id = created.json()["id"]
        assert client.get(f"/regulatory/readiness-reports/{report_id}", headers=alice).status_code == 200
        assert client.get(f"/regulatory/readiness-reports/{report_id}", headers=bob).status_code == 404
        assert client.get(f"/regulatory/readiness-reports/{report_id}", headers=SYSTEM).status_code == 200


# --------------------------------------------------------------------------- #
# Migration 0015 backfill — recover legacy owners from the audit trail
# --------------------------------------------------------------------------- #
# Kept in sync with _BACKFILL_SQL in alembic/versions/0015_dossier_created_by_user_id.py.
_BACKFILL_SQL = """
UPDATE regulatory_dossiers
SET created_by_user_id = (
    SELECT ae.actor_user_id
    FROM audit_events AS ae
    WHERE ae.entity_type = 'regulatory_dossier'
      AND ae.entity_id = regulatory_dossiers.id
      AND ae.event_type = 'regulatory.dossier.create'
      AND ae.actor_user_id IS NOT NULL
    ORDER BY ae.id DESC
    LIMIT 1
)
WHERE created_by_user_id IS NULL
"""


def test_audit_backfill_recovers_owner(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'backfill.sqlite3'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine)
    with Session() as s:
        alice = UserORM(email="alice@example.com", password_hash="x")
        s.add(alice)
        s.flush()
        # Legacy bearer-created dossier: owner NULL, but the create audit recorded alice.
        d_bearer = RegulatoryDossierORM(title="legacy bearer", created_by_user_id=None)
        s.add(d_bearer)
        s.flush()
        s.add(
            AuditEventORM(
                event_type="regulatory.dossier.create",
                message="m",
                actor_user_id=alice.id,
                entity_type="regulatory_dossier",
                entity_id=d_bearer.id,
            )
        )
        # System-created dossier: owner NULL, create audit has no actor -> stays NULL.
        d_system = RegulatoryDossierORM(title="legacy system", created_by_user_id=None)
        s.add(d_system)
        s.flush()
        s.add(
            AuditEventORM(
                event_type="regulatory.dossier.create",
                message="m",
                actor_user_id=None,
                entity_type="regulatory_dossier",
                entity_id=d_system.id,
            )
        )
        s.commit()
        alice_id, bearer_id, system_id = alice.id, d_bearer.id, d_system.id

    with engine.begin() as conn:
        conn.execute(text(_BACKFILL_SQL))

    with Session() as s:
        assert s.get(RegulatoryDossierORM, bearer_id).created_by_user_id == alice_id
        assert s.get(RegulatoryDossierORM, system_id).created_by_user_id is None


# --------------------------------------------------------------------------- #
# Query-param dossier reads (sibling endpoints filtered by ?dossier_id) are scoped
# via the same dossier-ownership join in the store.
# --------------------------------------------------------------------------- #
def test_action_items_list_is_owner_scoped(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        bob = _sign_up(client, "bob@example.com")
        did = _create_dossier(client, alice)
        # A parseable nitrosamine watch raises a review action item on alice's dossier.
        watch = client.post(
            f"/regulatory/dossiers/{did}/nitrosamine-watch",
            headers=alice,
            json={"structure_text": "CN(C)N=O"},
        )
        assert watch.status_code == 201, watch.text

        def items(headers, **params):
            res = client.get("/regulatory/action-items", headers=headers, params=params)
            assert res.status_code == 200, res.text
            return res.json()

        alice_ids = {it["id"] for it in items(alice, dossier_id=did)}
        assert alice_ids  # owner sees the action item
        assert {it["id"] for it in items(SYSTEM, dossier_id=did)} >= alice_ids  # system sees all
        # Bob cannot pull alice's dossier's action items via ?dossier_id ...
        assert items(bob, dossier_id=did) == []
        # ... nor via the unfiltered enumeration.
        assert alice_ids <= {it["id"] for it in items(alice)}
        assert alice_ids.isdisjoint({it["id"] for it in items(bob)})


def test_query_param_dossier_reads_reject_cross_user(tmp_path):
    # Notifications + spectroscopy bridges take ?dossier_id and are scoped by the same
    # store-level dossier-ownership join proven for action items above. A non-owner gets
    # nothing for another user's dossier; the system key stays unrestricted.
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        bob = _sign_up(client, "bob@example.com")
        did = _create_dossier(client, alice)
        for ep in ("/regulatory/notifications", "/bridges/spectroscopy-to-regulatory"):
            bob_res = client.get(ep, headers=bob, params={"dossier_id": did})
            assert bob_res.status_code == 200, bob_res.text
            assert bob_res.json() == []
            assert client.get(ep, headers=SYSTEM, params={"dossier_id": did}).status_code == 200


# --------------------------------------------------------------------------- #
# Write access: the same owner gate now guards POST/PATCH under a dossier.
# --------------------------------------------------------------------------- #
def test_write_to_dossier_requires_ownership(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        bob = _sign_up(client, "bob@example.com")
        did = _create_dossier(client, alice)

        def watch(headers):
            return client.post(
                f"/regulatory/dossiers/{did}/nitrosamine-watch",
                headers=headers,
                json={"structure_text": "CN(C)N=O"},
            )

        # A non-owner POST is blocked at the access gate; owner + system succeed.
        assert watch(bob).status_code == 404
        assert watch(alice).status_code == 201
        assert watch(SYSTEM).status_code == 201
        # PATCH is gated identically.
        assert client.patch(f"/regulatory/dossiers/{did}", headers=bob, json={"title": "x"}).status_code == 404
        assert client.patch(f"/regulatory/dossiers/{did}", headers=alice, json={"title": "x"}).status_code == 200


def test_bridge_by_id_reads_404_for_unknown_id(tmp_path):
    # Wiring smoke for the cross-module bridge by-id gate (the ownership logic is the same
    # _readable_via_parent_dossier helper proven by the readiness-report by-child test).
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        for ep in ("/bridges/spectroscopy-to-regulatory/999999", "/bridges/regulatory-to-reaction/999999"):
            assert client.get(ep, headers=alice).status_code == 404


# --------------------------------------------------------------------------- #
# Mobile review-decision sync: a draft may mutate a dossier only if the actor owns it.
# --------------------------------------------------------------------------- #
def test_mobile_dossier_access_rule():
    owned = RegulatoryDossierORM(title="owned", created_by_user_id=7)
    system_made = RegulatoryDossierORM(title="system", created_by_user_id=None)
    assert _mobile_can_access_dossier(owned, MobileActor(user_id=7)) is True
    assert _mobile_can_access_dossier(owned, MobileActor(user_id=8)) is False
    assert _mobile_can_access_dossier(owned, MobileActor(system_api_key=True)) is True
    # A NULL-owner (system-created) dossier is reachable only by the system key.
    assert _mobile_can_access_dossier(system_made, MobileActor(user_id=7)) is False
    assert _mobile_can_access_dossier(system_made, MobileActor(system_api_key=True)) is True


# --------------------------------------------------------------------------- #
# By-child-id writes: mutating a dossier child requires owning the parent dossier
# (require_dossier_access can't apply — the path is keyed by the child id).
# --------------------------------------------------------------------------- #
def test_requirement_patch_requires_ownership(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        bob = _sign_up(client, "bob@example.com")
        did = _create_dossier(client, alice)
        req = client.post(
            f"/regulatory/dossiers/{did}/requirements",
            headers=alice,
            json={"title": "Identity", "requirement_text": "Document the identity."},
        )
        assert req.status_code == 201, req.text
        rid = req.json()["id"]
        assert client.patch(f"/regulatory/requirements/{rid}", headers=bob, json={"title": "x"}).status_code == 404
        assert client.patch(f"/regulatory/requirements/{rid}", headers=alice, json={"title": "owned"}).status_code == 200
        assert client.patch(f"/regulatory/requirements/{rid}", headers=SYSTEM, json={"title": "sys"}).status_code == 200


def test_action_item_patch_requires_ownership(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        bob = _sign_up(client, "bob@example.com")
        did = _create_dossier(client, alice)
        # A nitrosamine watch raises a review action item on alice's dossier.
        assert client.post(
            f"/regulatory/dossiers/{did}/nitrosamine-watch",
            headers=alice,
            json={"structure_text": "CN(C)N=O"},
        ).status_code == 201
        items = client.get("/regulatory/action-items", headers=alice, params={"dossier_id": did}).json()
        assert items
        ai = items[0]["id"]
        assert client.patch(f"/regulatory/action-items/{ai}", headers=bob, json={"title": "x"}).status_code == 404
        assert client.patch(f"/regulatory/action-items/{ai}", headers=alice, json={"title": "owned"}).status_code == 200


def test_dossier_owned_by_rule(tmp_path):
    # The canonical in-session rule the by-child write gates funnel through (each store mirrors it).
    engine = create_engine(f"sqlite:///{tmp_path / 'owned.sqlite3'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine)
    with Session() as s:
        owner = UserORM(email="owner@example.com", password_hash="x")
        s.add(owner)
        s.flush()
        owned = RegulatoryDossierORM(title="owned", created_by_user_id=owner.id)
        unowned = RegulatoryDossierORM(title="system", created_by_user_id=None)
        s.add_all([owned, unowned])
        s.commit()
        assert dossier_owned_by(s, owned.id, None) is True             # system / admin
        assert dossier_owned_by(s, owned.id, owner.id) is True          # owner
        assert dossier_owned_by(s, owned.id, owner.id + 999) is False   # another user
        assert dossier_owned_by(s, unowned.id, owner.id) is False       # NULL owner, user-scoped
        assert dossier_owned_by(s, unowned.id, None) is True            # NULL owner, system
        assert dossier_owned_by(s, 999_999, owner.id) is False          # missing dossier
        assert dossier_owned_by(s, None, owner.id) is False             # no dossier anchor


def test_mobile_action_item_access_rule(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'mobile_ai.sqlite3'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine)
    with Session() as s:
        alice = UserORM(email="alice@example.com", password_hash="x")
        s.add(alice)
        s.flush()
        dossier = RegulatoryDossierORM(title="d", created_by_user_id=alice.id)
        s.add(dossier)
        s.flush()
        owned_item = RegulatoryActionItemORM(dossier_id=dossier.id, title="t", description="d")
        orphan_item = RegulatoryActionItemORM(dossier_id=None, title="o", description="d")
        s.add_all([owned_item, orphan_item])
        s.commit()
        assert _mobile_can_access_action_item(owned_item, s, MobileActor(user_id=alice.id)) is True
        assert _mobile_can_access_action_item(owned_item, s, MobileActor(user_id=alice.id + 999)) is False
        assert _mobile_can_access_action_item(owned_item, s, MobileActor(system_api_key=True)) is True
        assert _mobile_can_access_action_item(orphan_item, s, MobileActor(user_id=alice.id)) is False
        assert _mobile_can_access_action_item(orphan_item, s, MobileActor(system_api_key=True)) is True


# --------------------------------------------------------------------------- #
# Cross-module bridge CREATE: must not write/read dossier children on a body-supplied
# dossier the caller does not own.
# --------------------------------------------------------------------------- #
def test_spectroscopy_bridge_create_requires_dossier_ownership(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        bob = _sign_up(client, "bob@example.com")
        did = _create_dossier(client, alice)

        def make(headers):
            return client.post(
                "/bridges/spectroscopy-to-regulatory", headers=headers, json={"dossier_id": did}
            )

        assert make(bob).status_code == 404      # non-owner cannot inject action items
        assert make(alice).status_code == 201    # owner
        assert make(SYSTEM).status_code == 201   # system unrestricted


def test_regulatory_to_reaction_bridge_create_requires_dossier_ownership(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        bob = _sign_up(client, "bob@example.com")
        did = _create_dossier(client, alice)
        # A non-owner is stopped at the ownership gate (404) before any further work; the owner
        # and the system key pass the gate and only then fail on the missing reaction project
        # (400) — which isolates the 404 as the ownership check, not incidental validation.
        assert client.post(
            "/bridges/regulatory-to-reaction", headers=bob, json={"dossier_id": did}
        ).status_code == 404
        assert client.post(
            "/bridges/regulatory-to-reaction", headers=alice, json={"dossier_id": did}
        ).status_code == 400
        assert client.post(
            "/bridges/regulatory-to-reaction", headers=SYSTEM, json={"dossier_id": did}
        ).status_code == 400


# --------------------------------------------------------------------------- #
# Surveillance is a privileged platform process: runs (which fan out review children
# across dossiers) and source-watcher config are admin / system-only.
# --------------------------------------------------------------------------- #
def test_surveillance_writes_are_privileged(tmp_path):
    client = TestClient(_app(tmp_path))
    with client:
        alice = _sign_up(client, "alice@example.com")
        admin = _sign_up(client, ADMIN_EMAIL)
        # A non-admin bearer is blocked at the gate (403) before any cross-dossier fan-out runs.
        assert client.post("/regulatory/surveillance/runs", headers=alice, json={}).status_code == 403
        assert (
            client.post("/regulatory/surveillance/sources", headers=alice, json={"title": "w"}).status_code
            == 403
        )
        # The system key (the platform job) and admins pass the gate; the watcher create succeeds.
        assert client.post("/regulatory/surveillance/runs", headers=SYSTEM, json={}).status_code != 403
        assert (
            client.post("/regulatory/surveillance/sources", headers=SYSTEM, json={"title": "w"}).status_code
            == 201
        )
        assert (
            client.post("/regulatory/surveillance/sources", headers=admin, json={"title": "w"}).status_code
            == 201
        )
