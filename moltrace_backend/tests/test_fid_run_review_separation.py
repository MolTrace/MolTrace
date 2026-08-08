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

Now: any authenticated user may review, **except the run's own creator**, with
admin and the system key as overrides. `fid_runs` already carried `user_id`
(creator) alongside `reviewer_user_id`, so the check needed no schema change.

The self-review refusal is **409, not 403**. It is not a privilege failure —
the caller is perfectly entitled to review runs, just not this one — and a 403
here would be both semantically wrong and swallowed by the global
`PUBLIC_ACCESS_DENIED_DETAIL` sanitiser, which is what made the original
"You do not have access to perform this action" so unhelpful. A reviewer reading
that concludes the feature is broken.
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


def _user_id(client: TestClient, headers: dict[str, str]) -> int:
    res = client.get("/auth/me", headers=headers)
    assert res.status_code == 200, res.text
    return int(res.json()["id"])


@pytest.mark.parametrize("action", ["review", "approve", "reject", "request-changes"])
def test_a_colleague_can_review_without_being_an_admin(client, api_headers, action):
    """The whole point: a lab reviewer is a chemist, not IT."""
    author = _signup(client, f"sep-author-{action}@example.com")
    colleague = _signup(client, f"sep-colleague-{action}@example.com")
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


def test_an_unowned_legacy_run_is_reviewable(client, api_headers):
    """A run with no recorded creator predates attribution.

    Unlike a file, where NULL owner means "refuse", here it means the
    separation check has nothing to compare against — and blocking review of
    every historical run would be a worse outcome than allowing it. Recorded as
    a deliberate asymmetry rather than an oversight.
    """
    from sqlalchemy import text as sa_text

    reviewer = _signup(client, "sep-legacy@example.com")
    run_id = _seed_run(client, _user_id(client, reviewer))
    engine = client.app.state.session_factory.kw["bind"]
    with engine.begin() as conn:
        conn.execute(
            sa_text("UPDATE fid_runs SET user_id = NULL WHERE id = :i"), {"i": run_id}
        )

    res = client.post(f"/fid/runs/{run_id}/review", headers=reviewer, json={"comment": "ok"})
    assert res.status_code == 200, res.text
