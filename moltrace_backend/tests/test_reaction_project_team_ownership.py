"""Repho campaigns belong to the team, not just their author.

The counterpart of ``test_regulatory_dossier_team_ownership``. A process-chemistry campaign is run
by a group — someone designs the plate, someone runs it, someone reads the results — but ownership
was creator-only, so a five-chemist team had to share one login.

Reaction access has three entry points that must agree, and each is exercised below: the path gate
(``require_reaction_access``, covering every id-bearing route), the body-id checks
(``reaction_project_owned_by`` / ``reaction_experiment_owned_by``, for ids the path gate cannot
reach), and the campaign list. If any one lagged, a chemist would see a campaign they cannot open,
or open one they cannot list.
"""

import uuid

from fastapi.testclient import TestClient

from nmrcheck.orm import OrganizationORM, ReactionProjectORM, TeamMemberORM


def _sign_up(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _org_with_members(app, name: str, members: list[tuple[str, str]]) -> int:
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


def _project(client: TestClient, headers: dict[str, str], name: str = "Campaign") -> dict:
    res = client.post(
        "/reaction-projects",
        headers=headers,
        json={"name": name, "objective": "maximize_yield"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _emails() -> tuple[str, str]:
    tag = uuid.uuid4().hex[:8]
    return f"lead-{tag}@example.com", f"chemist-{tag}@example.com"


# --------------------------------------------------------------------------- #
# The capability
# --------------------------------------------------------------------------- #
def test_a_teammate_can_open_and_list_a_colleagues_campaign(client, app):
    lead_email, chemist_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        chemist = _sign_up(client, chemist_email)
        _org_with_members(app, "Process Chemistry", [(lead_email, "active"), (chemist_email, "active")])

        project = _project(client, lead, "Suzuki optimization")

        opened = client.get(f"/reaction-projects/{project['id']}", headers=chemist)
        assert opened.status_code == 200, opened.text
        assert opened.json()["name"] == "Suzuki optimization"

        listed = client.get("/reaction-projects", headers=chemist)
        assert listed.status_code == 200, listed.text
        assert project["id"] in [row["id"] for row in listed.json()]


def test_a_teammate_can_work_the_campaign_not_merely_read_it(client, app):
    lead_email, chemist_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        chemist = _sign_up(client, chemist_email)
        _org_with_members(app, "Process Chemistry", [(lead_email, "active"), (chemist_email, "active")])
        project = _project(client, lead)

        created = client.post(
            f"/reaction-projects/{project['id']}/experiments",
            headers=chemist,
            json={
                "experiment_code": "EXP-TEAM-001",
                "conditions_json": {"temperature_c": 80},
                "outcome_json": {"yield_percent": 71.0},
            },
        )
        assert created.status_code == 201, created.text


# --------------------------------------------------------------------------- #
# The boundaries
# --------------------------------------------------------------------------- #
def test_a_chemist_in_another_organization_still_gets_a_non_leaking_404(client, app):
    lead_email, outsider_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        outsider = _sign_up(client, outsider_email)
        _org_with_members(app, "Process Chemistry", [(lead_email, "active")])
        _org_with_members(app, "Another CDMO", [(outsider_email, "active")])

        project = _project(client, lead)

        assert client.get(f"/reaction-projects/{project['id']}", headers=outsider).status_code == 404
        listed = client.get("/reaction-projects", headers=outsider)
        assert listed.status_code == 200
        assert project["id"] not in [row["id"] for row in listed.json()]


def test_a_disabled_member_loses_access(client, app):
    lead_email, former_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        former = _sign_up(client, former_email)
        _org_with_members(
            app, "Process Chemistry", [(lead_email, "active"), (former_email, "disabled")]
        )
        project = _project(client, lead)

        assert client.get(f"/reaction-projects/{project['id']}", headers=former).status_code == 404


def test_a_campaign_with_no_organization_stays_creator_only(client, app):
    lead_email, other_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        other = _sign_up(client, other_email)
        project = _project(client, lead)  # neither user belongs to an organization

        with app.state.session_factory() as session:
            assert session.get(ReactionProjectORM, project["id"]).organization_id is None

        assert client.get(f"/reaction-projects/{project['id']}", headers=other).status_code == 404
        assert client.get(f"/reaction-projects/{project['id']}", headers=lead).status_code == 200


def test_ambiguous_membership_does_not_over_share(client, app):
    lead_email, bystander_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        bystander = _sign_up(client, bystander_email)
        _org_with_members(app, "Org One", [(lead_email, "active"), (bystander_email, "active")])
        _org_with_members(app, "Org Two", [(lead_email, "active")])

        project = _project(client, lead)

        with app.state.session_factory() as session:
            assert session.get(ReactionProjectORM, project["id"]).organization_id is None

        assert client.get(f"/reaction-projects/{project['id']}", headers=bystander).status_code == 404


def test_the_creator_and_the_operator_are_unaffected(client, app, api_headers):
    lead_email, _ = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        _org_with_members(app, "Process Chemistry", [(lead_email, "active")])
        project = _project(client, lead)

        assert client.get(f"/reaction-projects/{project['id']}", headers=lead).status_code == 200
        assert client.get(f"/reaction-projects/{project['id']}", headers=api_headers).status_code == 200
