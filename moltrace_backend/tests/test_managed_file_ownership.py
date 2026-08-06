"""Uploaded files belong to whoever uploaded them.

Before migration 0043 ``managed_file_records`` recorded no owner at all, so
there was nothing to compare a caller against and every read route was open.
Probed against a running server with auth enforced, a second unrelated account:

    GET /files/{id}            -> 200   the record
    GET /files/{id}/download   -> 200   *** the bytes ***
    GET /files                 -> 200   the file listed

For a product whose users upload proprietary FIDs that is one customer reading
another customer's raw spectral data — the most confidential thing the system
holds, and a worse leak than any of the regulatory holes fixed alongside it,
because those disclosed metadata ABOUT records while this disclosed the records.

The gate follows the DOSSIER pattern, not the compound registry's: a non-owner
gets a non-leaking 404 rather than a 403, because an uploaded spectrum's
existence is itself confidential. The registry could afford 403 — a shared
reference row's existence is not a secret, and a chemist looking at the record
on screen would only be confused by a 404.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _signup(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _upload(client: TestClient, headers: dict[str, str], name: str) -> int:
    res = client.post(
        "/files/upload",
        headers=headers,
        files={"file": (name, b"ppm,intensity\n1.0,10\n2.0,20\n", "text/csv")},
    )
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_a_stranger_cannot_read_or_download_your_upload(client, api_headers):
    alice = _signup(client, "file-alice@example.com")
    bob = _signup(client, "file-bob@example.com")
    fid = _upload(client, alice, "alice_private.csv")

    record = client.get(f"/files/{fid}", headers=bob)
    assert record.status_code == 404, (
        f"a stranger read the file record: {record.status_code} {record.text[:200]}"
    )

    download = client.get(f"/files/{fid}/download", headers=bob)
    assert download.status_code == 404, (
        f"a stranger DOWNLOADED the bytes: {download.status_code}"
    )


def test_the_refusal_does_not_confirm_the_file_exists(client, api_headers):
    """404 and not 403: existence is the secret here.

    A 403 would tell a stranger that file 7 exists and belongs to someone —
    enough to enumerate how many files a competitor has uploaded.
    """
    alice = _signup(client, "file-alice2@example.com")
    bob = _signup(client, "file-bob2@example.com")
    fid = _upload(client, alice, "alice_private.csv")

    real = client.get(f"/files/{fid}", headers=bob)
    absent = client.get("/files/99999", headers=bob)
    assert real.status_code == absent.status_code == 404
    assert real.json()["detail"] == absent.json()["detail"], (
        "the refusal for an existing file differs from one for a missing file, "
        "so existence leaks through the message"
    )


def test_the_listing_shows_only_your_own_files(client, api_headers):
    alice = _signup(client, "file-alice3@example.com")
    bob = _signup(client, "file-bob3@example.com")
    _upload(client, alice, "alice_one.csv")
    _upload(client, alice, "alice_two.csv")
    bob_file = _upload(client, bob, "bob_one.csv")

    alice_ids = {row["id"] for row in client.get("/files", headers=alice).json()}
    bob_ids = {row["id"] for row in client.get("/files", headers=bob).json()}

    assert len(alice_ids) == 2 and bob_ids == {bob_file}
    assert not (alice_ids & bob_ids), "file listings overlap across users"


def test_the_owner_keeps_full_access(client, api_headers):
    """The gate must not close on the person it exists to protect.

    This is not a formality: the read path refuses NULL-owner rows, so if the
    upload route ever stops stamping ``created_by_user_id`` the uploader loses
    their own file. That failure would look like a permissions bug rather than
    a missing write, so it is pinned separately.
    """
    alice = _signup(client, "file-alice4@example.com")
    fid = _upload(client, alice, "alice_private.csv")

    assert client.get(f"/files/{fid}", headers=alice).status_code == 200
    download = client.get(f"/files/{fid}/download", headers=alice)
    assert download.status_code == 200
    assert b"ppm,intensity" in download.content
    assert [row["id"] for row in client.get("/files", headers=alice).json()] == [fid]


def test_the_system_key_keeps_the_unscoped_view(client, api_headers):
    """Reserved for system/admin, matching every other gate in this codebase."""
    alice = _signup(client, "file-alice5@example.com")
    fid = _upload(client, alice, "alice_private.csv")

    assert client.get(f"/files/{fid}", headers=api_headers).status_code == 200
    assert client.get(f"/files/{fid}/download", headers=api_headers).status_code == 200


def test_a_legacy_unattributed_file_is_refused_to_non_admins(client, api_headers):
    """NULL owner means "uploaded before attribution existed".

    Treating that as unowned-and-therefore-public would leave the original hole
    open for exactly the oldest files. The system key can still reach them.
    """
    from sqlalchemy import text as sa_text

    alice = _signup(client, "file-alice6@example.com")
    bob = _signup(client, "file-bob6@example.com")
    fid = _upload(client, alice, "legacy.csv")

    engine = client.app.state.session_factory.kw["bind"]
    with engine.begin() as conn:
        conn.execute(
            sa_text("UPDATE managed_file_records SET created_by_user_id = NULL WHERE id = :i"),
            {"i": fid},
        )

    assert client.get(f"/files/{fid}", headers=bob).status_code == 404
    assert client.get(f"/files/{fid}", headers=alice).status_code == 404, (
        "even the original uploader cannot be identified on a NULL row"
    )
    assert client.get(f"/files/{fid}", headers=api_headers).status_code == 200
