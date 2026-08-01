"""Regentry dossiers are owned by a team, not just their creator.

Ownership was creator-only, which is right for a lone analyst and wrong for regulatory affairs: a
reviewer, a toxicologist and a QA lead all touch one filing, and none of them could see a
colleague's. A dossier now also carries an ``organization_id``, and an active member of that
organization has the same access as the creator.

This is an authorization predicate, so the negative cases carry the weight: a user in a *different*
organization, a *disabled* member, and a dossier with no organization at all must each still get
the non-leaking 404. Access widens only where a team genuinely exists.
"""

import uuid

from fastapi.testclient import TestClient

from nmrcheck.orm import OrganizationORM, TeamMemberORM


def _sign_up(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _org_with_members(app, name: str, members: list[tuple[str, str]]) -> int:
    """Create an organization and its ``(email, status)`` memberships directly."""
    with app.state.session_factory() as session:
        org = OrganizationORM(name=name)
        session.add(org)
        session.flush()
        for email, status in members:
            session.add(
                TeamMemberORM(
                    organization_id=org.id,
                    user_email=email.strip().lower(),
                    role="scientist",
                    status=status,
                )
            )
        session.commit()
        return int(org.id)


def _dossier(client: TestClient, headers: dict[str, str], title: str = "Filing") -> dict:
    res = client.post(
        "/regulatory/dossiers",
        headers=headers,
        json={"title": title, "product_name": "Example", "intended_use": "Decision support"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _emails() -> tuple[str, str]:
    tag = uuid.uuid4().hex[:8]
    return f"lead-{tag}@example.com", f"reviewer-{tag}@example.com"


# --------------------------------------------------------------------------- #
# The capability
# --------------------------------------------------------------------------- #
def test_a_teammate_can_open_and_list_a_colleagues_dossier(client, app):
    lead_email, reviewer_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        reviewer = _sign_up(client, reviewer_email)
        _org_with_members(app, "Regulatory Affairs", [(lead_email, "active"), (reviewer_email, "active")])

        dossier = _dossier(client, lead, "Nitrosamine filing")

        opened = client.get(f"/regulatory/dossiers/{dossier['id']}", headers=reviewer)
        assert opened.status_code == 200, opened.text
        assert opened.json()["title"] == "Nitrosamine filing"

        # The list and the gate must agree, or the queue shows rows that 404 when clicked.
        listed = client.get("/regulatory/dossiers", headers=reviewer)
        assert listed.status_code == 200, listed.text
        assert dossier["id"] in [row["id"] for row in listed.json()]


def test_a_teammate_can_work_the_dossier_not_merely_read_it(client, app):
    lead_email, reviewer_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        reviewer = _sign_up(client, reviewer_email)
        _org_with_members(app, "Regulatory Affairs", [(lead_email, "active"), (reviewer_email, "active")])
        dossier = _dossier(client, lead)

        created = client.post(
            f"/regulatory/dossiers/{dossier['id']}/requirements",
            headers=reviewer,
            json={
                "title": "Identity evidence",
                "category": "identity",
                "requirement_text": "Provide source-supported identity evidence.",
            },
        )
        assert created.status_code == 201, created.text


# --------------------------------------------------------------------------- #
# The boundaries — these are the ones that matter
# --------------------------------------------------------------------------- #
def test_a_user_in_another_organization_still_gets_a_non_leaking_404(client, app):
    lead_email, outsider_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        outsider = _sign_up(client, outsider_email)
        _org_with_members(app, "Regulatory Affairs", [(lead_email, "active")])
        _org_with_members(app, "Some Other Company", [(outsider_email, "active")])

        dossier = _dossier(client, lead)

        assert client.get(f"/regulatory/dossiers/{dossier['id']}", headers=outsider).status_code == 404
        listed = client.get("/regulatory/dossiers", headers=outsider)
        assert listed.status_code == 200
        assert dossier["id"] not in [row["id"] for row in listed.json()]


def test_a_disabled_member_loses_access(client, app):
    lead_email, former_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        former = _sign_up(client, former_email)
        # "disabled" is a valid TeamMemberStatus; only "active" grants membership.
        _org_with_members(
            app, "Regulatory Affairs", [(lead_email, "active"), (former_email, "disabled")]
        )
        dossier = _dossier(client, lead)

        assert client.get(f"/regulatory/dossiers/{dossier['id']}", headers=former).status_code == 404


def test_a_dossier_with_no_organization_stays_creator_only(client, app):
    """The pre-existing behaviour, unchanged. A user with no team shares with nobody."""
    lead_email, other_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        other = _sign_up(client, other_email)
        dossier = _dossier(client, lead)  # neither user belongs to an organization

        with app.state.session_factory() as session:
            from nmrcheck.orm import RegulatoryDossierORM

            row = session.get(RegulatoryDossierORM, dossier["id"])
            assert row.organization_id is None, "no membership must not stamp an organization"

        assert client.get(f"/regulatory/dossiers/{dossier['id']}", headers=other).status_code == 404
        assert client.get(f"/regulatory/dossiers/{dossier['id']}", headers=lead).status_code == 200


def test_ambiguous_membership_does_not_over_share(client, app):
    """A creator in two organizations gets creator-only ownership rather than a guessed team."""
    lead_email, bystander_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        bystander = _sign_up(client, bystander_email)
        _org_with_members(app, "Org One", [(lead_email, "active"), (bystander_email, "active")])
        _org_with_members(app, "Org Two", [(lead_email, "active")])

        dossier = _dossier(client, lead)

        with app.state.session_factory() as session:
            from nmrcheck.orm import RegulatoryDossierORM

            assert session.get(RegulatoryDossierORM, dossier["id"]).organization_id is None

        # The bystander shares an organization with the creator but the dossier claims none,
        # so there is nothing to share through.
        assert client.get(f"/regulatory/dossiers/{dossier['id']}", headers=bystander).status_code == 404


def test_the_creator_and_the_operator_are_unaffected(client, app, api_headers):
    lead_email, _ = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        _org_with_members(app, "Regulatory Affairs", [(lead_email, "active")])
        dossier = _dossier(client, lead)

        assert client.get(f"/regulatory/dossiers/{dossier['id']}", headers=lead).status_code == 200
        assert client.get(f"/regulatory/dossiers/{dossier['id']}", headers=api_headers).status_code == 200


def test_a_teammate_sees_the_dossiers_action_items_not_an_empty_inbox(client, app):
    """The gap the first pass left: opening a dossier is useless if its contents are invisible.

    ``regulatory_compliance_store`` kept its own copy of the ownership predicate, so widening the
    original did not widen the action-item queue — a colleague could open a filing and find its
    task inbox empty. The copies now delegate to one implementation, and this pins that they
    cannot drift apart again.
    """
    lead_email, reviewer_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        reviewer = _sign_up(client, reviewer_email)
        _org_with_members(app, "Regulatory Affairs", [(lead_email, "active"), (reviewer_email, "active")])
        dossier = _dossier(client, lead)

        created = client.post(
            "/regulatory/action-items",
            headers=lead,
            json={
                "dossier_id": dossier["id"],
                "action_type": "human_review",
                "severity": "info",
                "title": "Confirm the impurity limit",
                "description": "Check the reported limit against the current guidance.",
            },
        )
        assert created.status_code == 201, created.text

        lead_items = client.get("/regulatory/action-items", headers=lead)
        reviewer_items = client.get("/regulatory/action-items", headers=reviewer)
        assert lead_items.status_code == 200 and reviewer_items.status_code == 200
        assert [row["id"] for row in reviewer_items.json()] == [
            row["id"] for row in lead_items.json()
        ], "a teammate must see the same action items as the dossier's creator"
        assert created.json()["id"] in [row["id"] for row in reviewer_items.json()]
