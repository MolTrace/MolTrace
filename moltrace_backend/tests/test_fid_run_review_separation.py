"""A second qualified person reviews a FID run — not a platform administrator.

All four review routes were `Depends(require_admin)`, so the chemist who ran an
analysis could not have it reviewed unless a platform admin did it. That is not
segregation of duties; it conflates *can administer the system* with *is
qualified to approve an analysis*. In a lab the reviewer is a senior chemist,
not IT, and the practical effect was a dead end: probed live, the person who
created a run got 403 on `POST /fid/runs/{id}/review`.

The product already had the right model and bypassed it here —
`session_reviewers`, `review_tasks`, `approval_records` — and the sibling route
`POST /spectracheck/sessions/{id}/review` uses `require_access_context`, so the
two surfaces disagreed with each other.

Now: a **colleague** may review, except the run's own creator, with admin and the system
key as overrides. `fid_runs` already carried `user_id` (creator) alongside
`reviewer_user_id`, so the check needed no schema change.

The self-review refusal is **409, not 403**. It is not a privilege failure —
the caller is perfectly entitled to review runs, just not this one — and a 403
here would be both semantically wrong and swallowed by the global
`PUBLIC_ACCESS_DENIED_DETAIL` sanitiser, which is what made the original
"You do not have access to perform this action" so unhelpful. A reviewer reading
that concludes the feature is broken.

**Re-baselined when reviewer visibility landed.** This file originally asserted that
*any* authenticated user could review any run, and that an unattributed run was reviewable
by anyone. Both were written before there was a reviewer scope to gate on, and together
they meant a caller could write a verdict onto another customer's run by guessing an
integer id — a cross-tenant write, reachable while the run itself stayed unreadable to
them. Read access is now scoped to your team's open review queue, and write access is
defined to be the same set: you may review exactly what you may open. The two tests below
carry the change; `test_fid_run_reviewer_visibility.py` holds the full rule and its
negatives. What has *not* changed is everything this file was protecting — a non-admin can
still review, the author still cannot, and the refusal is still a 409 that says why.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _signup(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _seed_run(client: TestClient, owner_id: int) -> int:
    """A FID run owned by ``owner_id``, written directly to keep the test on point."""
    from sqlalchemy import text as sa_text

    engine = client.app.state.session_factory.kw["bind"]
    with engine.begin() as conn:
        conn.execute(
            sa_text(
                "INSERT INTO fid_runs ("
                "  user_id, filename, selected_preset, quality_label, quality_score,"
                "  review_status, preview_json, metadata_json, processing_recipe_json,"
                "  derived_spectrum_metadata_json, created_at"
                ") VALUES ("
                "  :u, 'run.zip', 'standard', 'good', 0.9,"
                "  'pending_review', '{}', '{}', '{}',"
                "  '{}', CURRENT_TIMESTAMP"
                ")"
            ),
            {"u": owner_id},
        )
        return int(conn.execute(sa_text("SELECT MAX(id) FROM fid_runs")).scalar_one())


def _same_team(client: TestClient, *emails: str, name: str) -> None:
    """Put ``emails`` on one organization as active members.

    Review is a team act now: the reviewer has to be a colleague, not merely somebody
    other than the author. See ``test_fid_run_reviewer_visibility.py``.
    """
    from nmrcheck.orm import OrganizationORM, TeamMemberORM

    with client.app.state.session_factory() as session:
        org = OrganizationORM(name=name)
        session.add(org)
        session.flush()
        for email in emails:
            session.add(
                TeamMemberORM(
                    organization_id=org.id,
                    user_email=email.strip().lower(),
                    role="scientist",
                    status="active",
                )
            )
        session.commit()


def _user_id(client: TestClient, headers: dict[str, str]) -> int:
    res = client.get("/auth/me", headers=headers)
    assert res.status_code == 200, res.text
    return int(res.json()["id"])


@pytest.mark.parametrize("action", ["review", "approve", "reject", "request-changes"])
def test_a_colleague_can_review_without_being_an_admin(client, api_headers, action):
    """The whole point: a lab reviewer is a chemist, not IT.

    Re-baselined: the colleague is now put on the author's team. This test used to pass
    with two unrelated accounts, which is what revealed the problem — "somebody else" was
    being read as *anybody* else, so the reviewer did not have to be a colleague at all.
    """
    author_email = f"sep-author-{action}@example.com"
    colleague_email = f"sep-colleague-{action}@example.com"
    author = _signup(client, author_email)
    colleague = _signup(client, colleague_email)
    _same_team(client, author_email, colleague_email, name=f"sep-lab-{action}")
    run_id = _seed_run(client, _user_id(client, author))

    res = client.post(
        f"/fid/runs/{run_id}/{action}",
        headers=colleague,
        json={"comment": "second pair of eyes"},
    )
    assert res.status_code == 200, (
        f"a non-admin colleague could not {action} a run: {res.status_code} {res.text[:200]}"
    )


@pytest.mark.parametrize("action", ["review", "approve", "reject", "request-changes"])
def test_the_author_cannot_review_their_own_run(client, api_headers, action):
    """Segregation of duties is the rule the admin gate was standing in for."""
    author = _signup(client, f"sep-self-{action}@example.com")
    run_id = _seed_run(client, _user_id(client, author))

    res = client.post(
        f"/fid/runs/{run_id}/{action}",
        headers=author,
        json={"comment": "approving my own work"},
    )
    assert res.status_code == 409, (
        f"the author self-{action}d their run: {res.status_code} {res.text[:200]}"
    )


def test_the_refusal_says_why(client, api_headers):
    """A 403 here would be wrong AND stripped by the global sanitiser.

    The caller is entitled to review runs — just not this one — so the message
    has to survive and has to name the reason, or a reviewer reads it as a bug.
    """
    author = _signup(client, "sep-msg@example.com")
    run_id = _seed_run(client, _user_id(client, author))

    res = client.post(f"/fid/runs/{run_id}/review", headers=author, json={"comment": "x"})
    detail = res.json().get("detail", "")
    assert res.status_code == 409
    assert "own" in detail.lower() or "author" in detail.lower() or "created" in detail.lower(), (
        f"the refusal does not say why: {detail!r}"
    )
    assert "do not have access" not in detail.lower(), (
        "the refusal was routed through the generic access-denied wording"
    )


def test_an_admin_may_still_review_anything(client, api_headers):
    """Admin is the override, not the gate."""
    author = _signup(client, "sep-admin-author@example.com")
    run_id = _seed_run(client, _user_id(client, author))

    res = client.post(
        f"/fid/runs/{run_id}/approve", headers=api_headers, json={"comment": "ops override"}
    )
    assert res.status_code == 200, res.text


def test_an_unowned_legacy_run_is_reviewable_only_by_an_admin(client, api_headers):
    """A run with no recorded creator predates attribution — and now reaches no peer.

    **Reversed.** This originally asserted that any authenticated user could review such a
    run: the separation check has nothing to compare against, and blocking review of every
    historical run seemed worse than allowing it, on the reasoning that refusing was
    obstruction with no upside.

    That premise did not survive the introduction of a reviewer scope. With no author there
    is no team to derive, so "allow" no longer means "allow a colleague" — it means allow
    *any* authenticated caller anywhere, on a run they cannot read. There is now an upside
    to refusing (no cross-tenant reach) and there is still a path (admin), so the asymmetry
    with managed files — where a NULL owner means refuse — is gone rather than deliberate.
    """
    from sqlalchemy import text as sa_text

    reviewer = _signup(client, "sep-legacy@example.com")
    run_id = _seed_run(client, _user_id(client, reviewer))
    engine = client.app.state.session_factory.kw["bind"]
    with engine.begin() as conn:
        conn.execute(
            sa_text("UPDATE fid_runs SET user_id = NULL WHERE id = :i"), {"i": run_id}
        )

    peer = client.post(f"/fid/runs/{run_id}/review", headers=reviewer, json={"comment": "ok"})
    assert peer.status_code == 404, (
        f"a peer acted on a run with no recorded author: {peer.status_code} {peer.text[:200]}"
    )

    ops = client.post(f"/fid/runs/{run_id}/review", headers=api_headers, json={"comment": "ok"})
    assert ops.status_code == 200, (
        f"an unattributed run became unreviewable by anyone at all: {ops.text[:200]}"
    )
