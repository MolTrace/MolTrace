"""A reviewer can find, open and read the run they are being asked to sign off.

``653b402`` opened the four review routes to any authenticated user who is not the run's
author, so a senior chemist rather than an IT admin could approve an analysis. It opened
only the write side. Discovery still ran through ``_user_scope_for_context``, which returns
the caller's own id for anyone who is not an admin, so a peer could record a verdict on a
run they could not list, open, or read the decision history of. The capability was
unreachable for exactly the population it was built for, and the cross-user review queue
was populated for admins only.

The rule now: read access is co-extensive with the review duty. A run is visible when you
wrote it, when it is an **open** item (``pending_review`` / ``needs_revision``) produced by
somebody who shares an active organization with you, or when you have already recorded a
decision on it. Nothing else — a colleague's *approved* run is not browsable, because the
duty that justified the disclosure is discharged.

This is an authorization predicate, so the negatives carry the weight. Each of these must
still be a non-leaking 404: a different organization, a *disabled* membership, no team at
all, and a run whose author is on no team. Access widens only where a team genuinely exists.

Two behaviours this file pins that are re-baselines of ``653b402``, not new ground — see
``test_fid_run_review_separation.py`` for the originals:

- **The write side is now scoped too.** Reviewing what you cannot see is not a capability,
  and leaving the POST unscoped meant a caller could write a verdict onto another
  customer's run by guessing an integer id. You may review exactly what you may open.
- **A NULL-author run no longer reaches a peer.** There is no author to resolve a team
  from. ``653b402`` allowed it on the grounds that refusing was obstruction with no upside;
  that premise no longer holds, because there is now an upside (no cross-tenant reach) and
  still a path (admin).

Segregation of duties is unchanged and is asserted here as well as there: the author is
refused with **409**, not 403 and not 404 — they can see the run perfectly well, they just
may not be the one to approve it.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from nmrcheck.models import FIDPreviewReport, FIDProcessingMetadata, FIDQADiagnostics
from nmrcheck.orm import OrganizationORM, TeamMemberORM


def _sign_up(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _user_id(client: TestClient, headers: dict[str, str]) -> int:
    res = client.get("/auth/me", headers=headers)
    assert res.status_code == 200, res.text
    return int(res.json()["id"])


def _org_with_members(app, name: str, members: list[tuple[str, str]]) -> int:
    """An organization and its ``(email, status)`` memberships, written directly."""
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


def _seed_run(app, owner_id: int | None, *, review_status: str = "pending_review") -> int:
    """A persisted FID run owned by ``owner_id``.

    Written through the store rather than raw SQL so ``preview_json`` is a payload the read
    routes can actually deserialize — these tests exercise GET, not only POST.
    """
    from nmrcheck.database import save_fid_run

    preview = FIDPreviewReport(
        filename="run.zip",
        format_detected="bruker",
        source_mode="trace",
        point_count=0,
        processing_metadata=FIDProcessingMetadata(
            vendor_format_detected="bruker",
            dataset_folder="1",
            human_review_status=review_status,
            qa_diagnostics=FIDQADiagnostics(
                quality_score=0.9,
                quality_label="good",
                dynamic_range=100.0,
                noise_estimate=0.01,
                baseline_offset_ratio=0.0,
                saturation_clipping_proxy=0.0,
                point_count=0,
            ),
        ),
    )
    run = save_fid_run(app.state.session_factory, preview, user_id=owner_id, sample_id="S-1")
    if review_status != run.review_status:  # pragma: no cover - defensive
        from sqlalchemy import text as sa_text

        with app.state.session_factory() as session:
            session.execute(
                sa_text("UPDATE fid_runs SET review_status = :s WHERE id = :i"),
                {"s": review_status, "i": run.id},
            )
            session.commit()
    return int(run.id)


def _emails() -> tuple[str, str]:
    tag = uuid.uuid4().hex[:8]
    return f"fid-author-{tag}@example.com", f"fid-reviewer-{tag}@example.com"


def _ids(payload: list[dict]) -> set[int]:
    return {int(row["id"]) for row in payload}


# --------------------------------------------------------------------------- #
# The capability: a peer can now reach the run they are asked to review
# --------------------------------------------------------------------------- #
def test_a_teammate_can_list_open_and_read_a_colleagues_run(client, app):
    """The whole point. Before this, every one of these four calls was a 404."""
    author_email, reviewer_email = _emails()
    with client:
        author = _sign_up(client, author_email)
        reviewer = _sign_up(client, reviewer_email)
        _org_with_members(
            app,
            f"lab-{uuid.uuid4().hex[:8]}",
            [(author_email, "active"), (reviewer_email, "active")],
        )
        run_id = _seed_run(app, _user_id(client, author))

        listed = client.get("/fid/runs", headers=reviewer)
        assert listed.status_code == 200, listed.text
        assert run_id in _ids(listed.json()), (
            "a colleague's run awaiting review is missing from the reviewer's list — "
            "the review queue is unreachable again"
        )

        detail = client.get(f"/fid/runs/{run_id}", headers=reviewer)
        assert detail.status_code == 200, detail.text

        decisions = client.get(f"/fid/runs/{run_id}/review-decisions", headers=reviewer)
        assert decisions.status_code == 200, decisions.text

        report = client.get(f"/fid/runs/{run_id}/report", headers=reviewer)
        assert report.status_code == 200, (
            "a reviewer can list the run but not read its report — the report IS the "
            "material being signed off"
        )


@pytest.mark.parametrize("action", ["review", "approve", "reject", "request-changes"])
def test_a_teammate_can_record_every_verdict(client, app, action):
    author_email, reviewer_email = _emails()
    with client:
        author = _sign_up(client, author_email)
        reviewer = _sign_up(client, reviewer_email)
        _org_with_members(
            app,
            f"lab-{uuid.uuid4().hex[:8]}",
            [(author_email, "active"), (reviewer_email, "active")],
        )
        run_id = _seed_run(app, _user_id(client, author))

        res = client.post(
            f"/fid/runs/{run_id}/{action}", headers=reviewer, json={"comment": "second pair"}
        )
        assert res.status_code == 200, (
            f"a same-team colleague could not {action}: {res.status_code} {res.text[:200]}"
        )


def test_the_reviewer_can_still_see_what_they_signed(client, app):
    """Visibility from the queue lapses on approval; visibility as reviewer of record does not.

    Without this clause a reviewer loses the evidence at the exact instant they approve it,
    which for a Part 11 signature is backwards: the person who signed must be able to open
    what they signed.
    """
    author_email, reviewer_email = _emails()
    with client:
        author = _sign_up(client, author_email)
        reviewer = _sign_up(client, reviewer_email)
        _org_with_members(
            app,
            f"lab-{uuid.uuid4().hex[:8]}",
            [(author_email, "active"), (reviewer_email, "active")],
        )
        run_id = _seed_run(app, _user_id(client, author))

        approved = client.post(
            f"/fid/runs/{run_id}/approve", headers=reviewer, json={"comment": "looks right"}
        )
        assert approved.status_code == 200, approved.text

        after = client.get(f"/fid/runs/{run_id}", headers=reviewer)
        assert after.status_code == 200, (
            "the reviewer lost sight of the run the moment they approved it"
        )
        assert after.json()["review_status"] == "approved"

        history = client.get(f"/fid/runs/{run_id}/review-decisions", headers=reviewer)
        assert history.status_code == 200, history.text
        assert any(d["action"] == "approve" for d in history.json())


def test_the_author_never_loses_their_own_run(client, app):
    """Opening the read side must not narrow it. Every status, still the author's."""
    author_email, _ = _emails()
    with client:
        author = _sign_up(client, author_email)
        for status in ("pending_review", "needs_revision", "approved", "rejected"):
            run_id = _seed_run(app, _user_id(client, author), review_status=status)
            res = client.get(f"/fid/runs/{run_id}", headers=author)
            assert res.status_code == 200, f"the author lost their own {status} run: {res.text}"


# --------------------------------------------------------------------------- #
# The negatives — each must be a non-leaking 404, on reads AND on writes
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("membership", "why"),
    [
        ("other_org", "a member of a different organization is not a colleague"),
        ("disabled", "a disabled membership is not a membership"),
        ("no_team", "a user on no team has no colleagues to review for"),
    ],
)
def test_a_stranger_cannot_see_the_run(client, app, membership, why):
    author_email, outsider_email = _emails()
    with client:
        author = _sign_up(client, author_email)
        outsider = _sign_up(client, outsider_email)
        tag = uuid.uuid4().hex[:8]
        if membership == "other_org":
            _org_with_members(app, f"lab-a-{tag}", [(author_email, "active")])
            _org_with_members(app, f"lab-b-{tag}", [(outsider_email, "active")])
        elif membership == "disabled":
            _org_with_members(
                app, f"lab-{tag}", [(author_email, "active"), (outsider_email, "disabled")]
            )
        else:
            _org_with_members(app, f"lab-{tag}", [(author_email, "active")])
        run_id = _seed_run(app, _user_id(client, author))

        assert client.get(f"/fid/runs/{run_id}", headers=outsider).status_code == 404, why
        assert (
            client.get(f"/fid/runs/{run_id}/review-decisions", headers=outsider).status_code == 404
        ), why
        assert client.get(f"/fid/runs/{run_id}/report", headers=outsider).status_code == 404, why
        assert run_id not in _ids(client.get("/fid/runs", headers=outsider).json()), why


@pytest.mark.parametrize("action", ["review", "approve", "reject", "request-changes"])
def test_a_stranger_cannot_write_a_verdict_either(client, app, action):
    """The gap ``653b402`` left: the POST was ungated, so a verdict could be written onto a
    run in another customer's tenant by guessing an id. Reviewing what you cannot see is
    not a capability — it is a cross-tenant write."""
    author_email, outsider_email = _emails()
    with client:
        author = _sign_up(client, author_email)
        outsider = _sign_up(client, outsider_email)
        tag = uuid.uuid4().hex[:8]
        _org_with_members(app, f"lab-a-{tag}", [(author_email, "active")])
        _org_with_members(app, f"lab-b-{tag}", [(outsider_email, "active")])
        run_id = _seed_run(app, _user_id(client, author))

        res = client.post(
            f"/fid/runs/{run_id}/{action}", headers=outsider, json={"comment": "not mine to judge"}
        )
        assert res.status_code == 404, (
            f"a user from another organization {action}d a run they cannot read: "
            f"{res.status_code} {res.text[:200]}"
        )


def test_a_colleagues_finished_run_is_not_browsable(client, app):
    """Visibility is granted *because* there is a review to perform, and lapses when there
    is not. This is what keeps the change a review queue rather than a silent conversion of
    every FID run into a team-shared resource."""
    author_email, first_email = _emails()
    third_email = f"fid-third-{uuid.uuid4().hex[:8]}@example.com"
    with client:
        author = _sign_up(client, author_email)
        first = _sign_up(client, first_email)
        third = _sign_up(client, third_email)
        _org_with_members(
            app,
            f"lab-{uuid.uuid4().hex[:8]}",
            [(author_email, "active"), (first_email, "active"), (third_email, "active")],
        )
        run_id = _seed_run(app, _user_id(client, author))

        assert client.get(f"/fid/runs/{run_id}", headers=third).status_code == 200
        assert (
            client.post(
                f"/fid/runs/{run_id}/approve", headers=first, json={"comment": "signed"}
            ).status_code
            == 200
        )
        after = client.get(f"/fid/runs/{run_id}", headers=third)
        assert after.status_code == 404, (
            "an uninvolved colleague can still browse a run after it was signed off — "
            "the disclosure outlived the duty that justified it"
        )
        assert client.get(f"/fid/runs/{run_id}", headers=author).status_code == 200, (
            "the author lost their own approved run"
        )


def test_a_run_needing_revision_stays_on_the_queue(client, app):
    """``request_changes`` bounces the run back to its author, who cannot re-open it
    themselves (segregation of duties). If ``needs_revision`` dropped off the team queue the
    run would be stuck with nobody able to pick it up."""
    author_email, reviewer_email = _emails()
    with client:
        author = _sign_up(client, author_email)
        reviewer = _sign_up(client, reviewer_email)
        _org_with_members(
            app,
            f"lab-{uuid.uuid4().hex[:8]}",
            [(author_email, "active"), (reviewer_email, "active")],
        )
        run_id = _seed_run(app, _user_id(client, author), review_status="needs_revision")

        res = client.get(f"/fid/runs/{run_id}", headers=reviewer)
        assert res.status_code == 200, "a run awaiting revision fell off the team review queue"


def test_a_run_with_no_recorded_author_reaches_no_peer(client, app):
    """A re-baseline of ``653b402``, stated rather than hidden.

    That commit let any authenticated user review an unattributed run, reasoning that
    refusing was obstruction with no upside. With a tenancy rule in place the premise no
    longer holds: there is no author to derive a team from, so allowing it means *any*
    caller anywhere may act on it. An admin remains the path.
    """
    from sqlalchemy import text as sa_text

    _, peer_email = _emails()
    with client:
        peer = _sign_up(client, peer_email)
        _org_with_members(app, f"lab-{uuid.uuid4().hex[:8]}", [(peer_email, "active")])
        run_id = _seed_run(app, _user_id(client, peer))
        with app.state.session_factory() as session:
            session.execute(
                sa_text("UPDATE fid_runs SET user_id = NULL WHERE id = :i"), {"i": run_id}
            )
            session.commit()

        assert client.get(f"/fid/runs/{run_id}", headers=peer).status_code == 404
        assert (
            client.post(
                f"/fid/runs/{run_id}/review", headers=peer, json={"comment": "x"}
            ).status_code
            == 404
        )


def test_an_admin_still_sees_and_reviews_everything(client, app, api_headers):
    """Admin is the override, not the gate — unchanged, and the path of last resort for
    the unattributed runs the peer rule above deliberately cannot reach."""
    author_email, _ = _emails()
    with client:
        author = _sign_up(client, author_email)
        run_id = _seed_run(app, _user_id(client, author), review_status="approved")

        assert client.get(f"/fid/runs/{run_id}", headers=api_headers).status_code == 200
        assert client.get(f"/fid/runs/{run_id}/report", headers=api_headers).status_code == 200
        res = client.post(
            f"/fid/runs/{run_id}/approve", headers=api_headers, json={"comment": "ops override"}
        )
        assert res.status_code == 200, res.text


# --------------------------------------------------------------------------- #
# Segregation of duties survives the widening
# --------------------------------------------------------------------------- #
def test_the_author_is_refused_with_409_not_404(client, app):
    """The order of the two gates matters. The author passes the visibility check — it is
    their run — and lands on the separation refusal, which is 409 because the caller *is*
    entitled to review runs, just not this one. A 404 here would tell them their own run
    does not exist."""
    author_email, _ = _emails()
    with client:
        author = _sign_up(client, author_email)
        run_id = _seed_run(app, _user_id(client, author))

        res = client.post(f"/fid/runs/{run_id}/review", headers=author, json={"comment": "mine"})
        assert res.status_code == 409, f"{res.status_code} {res.text[:200]}"
        detail = res.json().get("detail", "")
        assert "created" in detail.lower() or "own" in detail.lower(), detail
        assert "do not have access" not in detail.lower(), (
            "the refusal was routed through the generic access-denied wording"
        )


# --------------------------------------------------------------------------- #
# The contract the review surface consumes
# --------------------------------------------------------------------------- #
def test_the_record_says_whose_run_it_is_and_who_may_review_it(client, app):
    """The list is now mixed, so a client must be able to tell "mine" from "awaiting me"
    without comparing user ids itself, and must learn the self-review refusal before
    posting rather than from a 409."""
    author_email, reviewer_email = _emails()
    with client:
        author = _sign_up(client, author_email)
        reviewer = _sign_up(client, reviewer_email)
        _org_with_members(
            app,
            f"lab-{uuid.uuid4().hex[:8]}",
            [(author_email, "active"), (reviewer_email, "active")],
        )
        run_id = _seed_run(app, _user_id(client, author))

        mine = client.get(f"/fid/runs/{run_id}", headers=author).json()
        assert mine["viewer_is_author"] is True
        assert mine["viewer_can_review"] is False, (
            "the author is offered review controls they will be refused for"
        )

        theirs = client.get(f"/fid/runs/{run_id}", headers=reviewer).json()
        assert theirs["viewer_is_author"] is False
        assert theirs["viewer_can_review"] is True


def test_the_review_queue_excludes_your_own_runs(client, app):
    """``scope=review_queue`` is the population the surface exists for. A run you wrote is
    never on your own queue, and a page ordered newest-first must not let a prolific
    author's runs crowd the queue out of a bounded page."""
    author_email, reviewer_email = _emails()
    with client:
        author = _sign_up(client, author_email)
        reviewer = _sign_up(client, reviewer_email)
        _org_with_members(
            app,
            f"lab-{uuid.uuid4().hex[:8]}",
            [(author_email, "active"), (reviewer_email, "active")],
        )
        theirs = _seed_run(app, _user_id(client, author))
        own = _seed_run(app, _user_id(client, reviewer))

        queue = _ids(client.get("/fid/runs?scope=review_queue", headers=reviewer).json())
        assert theirs in queue
        assert own not in queue, "your own run appeared on your review queue"

        mine = _ids(client.get("/fid/runs?scope=mine", headers=reviewer).json())
        assert own in mine
        assert theirs not in mine

        everything = _ids(client.get("/fid/runs?scope=all", headers=reviewer).json())
        assert {theirs, own} <= everything


def test_the_process_response_names_the_run_it_created(client, app):
    """``POST /nmr/raw-fid/process`` always persisted a run but never said which, and the
    model is ``extra="forbid"`` — so the Raw FID tab could not anchor review to the run the
    user had just made and had to go find it in the list."""
    schema = client.get("/openapi.json").json()["components"]["schemas"]
    assert "fid_run_id" in schema["NMRRawFIDProcessResponse"]["properties"], (
        "the process response still cannot identify the run it created"
    )
