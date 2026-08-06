"""An action item you raised is an action item you can see.

An action item may legitimately hang off a batch, a compound, an evidence link, a requirement — or
nothing at all. But the list reached items only through an inner join on the dossier, so anything
without one was created successfully and then permanently invisible to the person who created it.
The API answered 201 and the work disappeared, which is the worst kind of bug: it reports success.

Requiring a dossier would have closed the hole by deleting a real capability — batch- and
compound-anchored tasks would have gone with it. So the item records who raised it and their team
instead, exactly as a dossier does.

The list and the update gate have to agree. A queue that shows a task which then refuses to be
progressed is worse than one that never showed it, so both are tested here together.
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


def _emails() -> tuple[str, str]:
    tag = uuid.uuid4().hex[:8]
    return f"lead-{tag}@example.com", f"mate-{tag}@example.com"


def _item(client, headers, **overrides):
    body = {
        "action_type": "human_review",
        "severity": "info",
        "title": "Ad-hoc compliance task",
        "description": "Raised without a dossier.",
    }
    body.update(overrides)
    return client.post("/regulatory/action-items", headers=headers, json=body)


def _listed_ids(client, headers) -> list[int]:
    res = client.get("/regulatory/action-items", headers=headers)
    assert res.status_code == 200, res.text
    return [row["id"] for row in res.json()]


# --------------------------------------------------------------------------- #
# The defect
# --------------------------------------------------------------------------- #
def test_an_item_raised_without_a_dossier_is_visible_to_its_creator(client, app):
    """The bug in one test: this used to return 201 and then never appear anywhere."""
    lead_email, _ = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        created = _item(client, lead)
        assert created.status_code == 201, created.text
        assert created.json()["id"] in _listed_ids(client, lead)


def test_the_creator_can_also_progress_it(client, app):
    """The list and the update gate must agree — a visible task has to be actionable."""
    lead_email, _ = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        item = _item(client, lead).json()
        patched = client.patch(
            f"/regulatory/action-items/{item['id']}", headers=lead, json={"status": "resolved"}
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["status"] == "resolved"


def test_a_teammate_sees_and_can_progress_it(client, app):
    lead_email, mate_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        mate = _sign_up(client, mate_email)
        _org_with_members(app, "Regulatory Affairs", [(lead_email, "active"), (mate_email, "active")])
        item = _item(client, lead).json()

        assert item["id"] in _listed_ids(client, mate)
        assert (
            client.patch(
                f"/regulatory/action-items/{item['id']}", headers=mate, json={"status": "in_progress"}
            ).status_code
            == 200
        )


# --------------------------------------------------------------------------- #
# The boundary — widening reachability must not widen it to everyone
# --------------------------------------------------------------------------- #
def test_an_outsider_sees_nothing_and_can_progress_nothing(client, app):
    lead_email, outsider_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        outsider = _sign_up(client, outsider_email)
        _org_with_members(app, "Regulatory Affairs", [(lead_email, "active")])
        _org_with_members(app, "Another Company", [(outsider_email, "active")])
        item = _item(client, lead).json()

        assert item["id"] not in _listed_ids(client, outsider)
        assert (
            client.patch(
                f"/regulatory/action-items/{item['id']}", headers=outsider, json={"status": "resolved"}
            ).status_code
            == 404
        ), "an unreachable item must be a non-leaking 404, not a refusal that confirms it exists"


def test_a_user_with_no_team_shares_with_nobody(client, app):
    lead_email, other_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        other = _sign_up(client, other_email)
        item = _item(client, lead).json()  # neither belongs to an organization

        assert item["id"] in _listed_ids(client, lead)
        assert item["id"] not in _listed_ids(client, other)


# --------------------------------------------------------------------------- #
# The capability that requiring a dossier would have deleted
# --------------------------------------------------------------------------- #
def test_an_item_anchored_to_something_other_than_a_dossier_still_works(client, app, api_headers):
    """Batch- and compound-anchored tasks were equally invisible under the old inner join. They are
    why the fix is ownership rather than making dossier_id required."""
    lead_email, _ = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        compound = client.post(
            "/compound-registry/compounds",
            headers=api_headers,
            json={"preferred_name": "Example analyte"},
        )
        assert compound.status_code == 201, compound.text
        created = _item(client, lead, compound_id=compound.json()["id"])
        assert created.status_code == 201, created.text
        assert created.json()["id"] in _listed_ids(client, lead)


def test_the_operator_still_sees_everything(client, app, api_headers):
    lead_email, _ = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        item = _item(client, lead).json()
        assert item["id"] in _listed_ids(client, api_headers)
