"""Review tasks can be raised against a filing or a campaign, not only a spectroscopy session.

Team review was a SpectraCheck-only feature because ``review_tasks.session_id`` was required.
Regentry could not say "someone look at this filing" and Repho could not say "someone check this
campaign" — most of what a regulated team actually does with a record.

The subject pair makes the record addressable across all three products. What matters for
correctness is that authorization is *the subject's own rule*, not a new one: a task can only be
raised against something the caller can already open, and a teammate sees the queue for anything
their team owns. The negative cases below are the ones that would otherwise leak one customer's
filing into another's review queue.
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


def _dossier(client: TestClient, headers: dict[str, str]) -> dict:
    res = client.post(
        "/regulatory/dossiers",
        headers=headers,
        json={"title": "Filing", "product_name": "Example", "intended_use": "Decision support"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _campaign(client: TestClient, headers: dict[str, str]) -> dict:
    res = client.post(
        "/reaction-projects", headers=headers, json={"name": "Campaign", "objective": "maximize_yield"}
    )
    assert res.status_code == 201, res.text
    return res.json()


def _task(client, headers, subject_type: str, subject_id: int, title: str = "Please review"):
    return client.post(
        "/review-tasks",
        headers=headers,
        json={
            "subject_type": subject_type,
            "subject_id": subject_id,
            "title": title,
            "assigned_to": "reviewer@example.com",
        },
    )


def _emails() -> tuple[str, str]:
    tag = uuid.uuid4().hex[:8]
    return f"lead-{tag}@example.com", f"mate-{tag}@example.com"


# --------------------------------------------------------------------------- #
# The capability, for both products
# --------------------------------------------------------------------------- #
def test_a_filing_can_carry_a_review_task(client, api_headers):
    with client:
        dossier = _dossier(client, api_headers)
        created = _task(client, api_headers, "regulatory_dossier", dossier["id"])
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["subject_type"] == "regulatory_dossier"
        assert body["subject_id"] == dossier["id"]
        assert body["session_id"] is None
        # The record names its product so a mixed queue is readable without re-deriving it.
        assert body["module"] == "regulatory_hub"

        listed = client.get(
            f"/review-tasks?subject_type=regulatory_dossier&subject_id={dossier['id']}",
            headers=api_headers,
        )
        assert listed.status_code == 200, listed.text
        assert [row["id"] for row in listed.json()] == [body["id"]]


def test_a_campaign_can_carry_a_review_task(client, api_headers):
    with client:
        campaign = _campaign(client, api_headers)
        created = _task(client, api_headers, "reaction_project", campaign["id"])
        assert created.status_code == 201, created.text
        assert created.json()["module"] == "reaction_optimization"


def test_a_task_can_be_progressed(client, api_headers):
    with client:
        dossier = _dossier(client, api_headers)
        task = _task(client, api_headers, "regulatory_dossier", dossier["id"]).json()
        patched = client.patch(
            f"/review-tasks/{task['id']}", headers=api_headers, json={"status": "resolved"}
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["status"] == "resolved"


# --------------------------------------------------------------------------- #
# Authorization is the subject's own rule
# --------------------------------------------------------------------------- #
def test_a_teammate_shares_the_review_queue(client, app):
    lead_email, mate_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        mate = _sign_up(client, mate_email)
        _org_with_members(app, "Regulatory Affairs", [(lead_email, "active"), (mate_email, "active")])
        dossier = _dossier(client, lead)

        created = _task(client, lead, "regulatory_dossier", dossier["id"])
        assert created.status_code == 201, created.text

        listed = client.get(
            f"/review-tasks?subject_type=regulatory_dossier&subject_id={dossier['id']}",
            headers=mate,
        )
        assert listed.status_code == 200, listed.text
        assert [row["id"] for row in listed.json()] == [created.json()["id"]]

        # And a teammate can act on it, not merely read it.
        patched = client.patch(
            f"/review-tasks/{created.json()['id']}", headers=mate, json={"status": "in_progress"}
        )
        assert patched.status_code == 200, patched.text


def test_an_outsider_cannot_raise_read_or_progress_a_task(client, app):
    lead_email, outsider_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        outsider = _sign_up(client, outsider_email)
        _org_with_members(app, "Regulatory Affairs", [(lead_email, "active")])
        _org_with_members(app, "Another Company", [(outsider_email, "active")])
        dossier = _dossier(client, lead)
        task = _task(client, lead, "regulatory_dossier", dossier["id"]).json()

        # Raising a task against someone else's filing must not be a way to discover it exists.
        assert _task(client, outsider, "regulatory_dossier", dossier["id"]).status_code == 404
        assert (
            client.get(
                f"/review-tasks?subject_type=regulatory_dossier&subject_id={dossier['id']}",
                headers=outsider,
            ).status_code
            == 404
        )
        assert (
            client.patch(
                f"/review-tasks/{task['id']}", headers=outsider, json={"status": "resolved"}
            ).status_code
            == 404
        )


def test_a_missing_subject_is_indistinguishable_from_a_forbidden_one(client, app):
    lead_email, _ = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        assert _task(client, lead, "regulatory_dossier", 999_999).status_code == 404


# --------------------------------------------------------------------------- #
# Boundaries of the surface itself
# --------------------------------------------------------------------------- #
def test_spectroscopy_sessions_keep_their_own_review_surface(client, api_headers):
    """The session surface carries per-session reviewer roles this one does not, so accepting
    session subjects here would be a second, weaker path to the same records."""
    with client:
        res = _task(client, api_headers, "spectracheck_session", 1)
        assert res.status_code == 403, res.text


def test_an_unknown_subject_type_is_rejected(client, api_headers):
    with client:
        res = _task(client, api_headers, "compound_batch", 1)
        assert res.status_code == 422, res.text


# --------------------------------------------------------------------------- #
# Comments — the same registry, the same rules
# --------------------------------------------------------------------------- #
def _comment(client, headers, subject_type: str, subject_id: int, text: str = "Looks fine to me"):
    return client.post(
        "/comments",
        headers=headers,
        json={"subject_type": subject_type, "subject_id": subject_id, "comment": text},
    )


def test_a_filing_can_carry_a_comment(client, api_headers):
    with client:
        dossier = _dossier(client, api_headers)
        created = _comment(client, api_headers, "regulatory_dossier", dossier["id"])
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["subject_type"] == "regulatory_dossier"
        assert body["session_id"] is None
        assert body["module"] == "regulatory_hub"

        listed = client.get(
            f"/comments?subject_type=regulatory_dossier&subject_id={dossier['id']}",
            headers=api_headers,
        )
        assert listed.status_code == 200, listed.text
        assert [row["id"] for row in listed.json()] == [body["id"]]


def test_a_campaign_can_carry_a_comment(client, api_headers):
    with client:
        campaign = _campaign(client, api_headers)
        created = _comment(client, api_headers, "reaction_project", campaign["id"])
        assert created.status_code == 201, created.text
        assert created.json()["module"] == "reaction_optimization"


def test_a_teammate_can_read_and_resolve_a_comment(client, app):
    lead_email, mate_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        mate = _sign_up(client, mate_email)
        _org_with_members(app, "Regulatory Affairs", [(lead_email, "active"), (mate_email, "active")])
        dossier = _dossier(client, lead)
        created = _comment(client, lead, "regulatory_dossier", dossier["id"])
        assert created.status_code == 201, created.text

        listed = client.get(
            f"/comments?subject_type=regulatory_dossier&subject_id={dossier['id']}", headers=mate
        )
        assert listed.status_code == 200, listed.text
        assert [row["id"] for row in listed.json()] == [created.json()["id"]]

        resolved = client.patch(
            f"/comments/{created.json()['id']}", headers=mate, json={"resolved": True}
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["resolved"] is True


def test_an_outsider_cannot_comment_read_or_resolve(client, app):
    lead_email, outsider_email = _emails()
    with client:
        lead = _sign_up(client, lead_email)
        outsider = _sign_up(client, outsider_email)
        _org_with_members(app, "Regulatory Affairs", [(lead_email, "active")])
        _org_with_members(app, "Another Company", [(outsider_email, "active")])
        dossier = _dossier(client, lead)
        comment = _comment(client, lead, "regulatory_dossier", dossier["id"]).json()

        assert _comment(client, outsider, "regulatory_dossier", dossier["id"]).status_code == 404
        assert (
            client.get(
                f"/comments?subject_type=regulatory_dossier&subject_id={dossier['id']}",
                headers=outsider,
            ).status_code
            == 404
        )
        assert (
            client.patch(
                f"/comments/{comment['id']}", headers=outsider, json={"resolved": True}
            ).status_code
            == 404
        )


def test_spectroscopy_sessions_keep_their_own_comment_surface(client, api_headers):
    """The session surface can anchor a note to a specific piece of evidence; this one cannot."""
    with client:
        assert _comment(client, api_headers, "spectracheck_session", 1).status_code == 403
