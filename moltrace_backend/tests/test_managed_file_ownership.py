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

That first pass closed the three READ routes and stopped there, which left the
routes that *write* against a caller-supplied ``file_id`` wide open — the same
hole, reached by a different verb:

    DELETE /files/{id}                    destroys the record and its session links
    POST   /files/{id}/normalize          reads the bytes into a derived artifact
    GET    /files/{id}/normalization-runs lists the derived runs and artifact ids
    GET    /normalization-runs/{id}       the same run, addressed by run id
    POST   /integrations/reactions/import-experiment-table
                                          normalizes a body-supplied file_id

Normalize is the one that matters most: it is the download hole wearing a
disguise. The bytes come back as a parsed artifact instead of a stream, so the
data leaves by a route nobody thought of as a read.
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


# --- the write and derive paths -------------------------------------------
#
# Everything below reaches the same file by a caller-supplied id, so each one
# needs the same gate the read routes got.


def _normalize(client: TestClient, headers: dict[str, str], file_id: int):
    return client.post(f"/files/{file_id}/normalize", headers=headers, json={})


def test_a_stranger_cannot_delete_your_upload(client, api_headers):
    """The worst of the three: it is destructive and needs nothing but the id.

    A stranger walking the id space could have emptied every other account's
    file table, and the cascade takes the SpectraCheck session links with it.
    """
    alice = _signup(client, "file-alice7@example.com")
    bob = _signup(client, "file-bob7@example.com")
    fid = _upload(client, alice, "alice_private.csv")

    removed = client.delete(f"/files/{fid}", headers=bob)
    assert removed.status_code == 404, (
        f"a stranger deleted the file record: {removed.status_code} {removed.text[:200]}"
    )
    assert client.get(f"/files/{fid}", headers=alice).status_code == 200, (
        "the refusal returned 404 but the row was destroyed anyway"
    )


def test_the_delete_refusal_does_not_confirm_the_file_exists(client, api_headers):
    alice = _signup(client, "file-alice8@example.com")
    bob = _signup(client, "file-bob8@example.com")
    fid = _upload(client, alice, "alice_private.csv")

    real = client.delete(f"/files/{fid}", headers=bob)
    absent = client.delete("/files/99999", headers=bob)
    assert real.status_code == absent.status_code == 404
    assert real.json()["detail"] == absent.json()["detail"], (
        "deleting someone else's file answers differently from deleting a missing one"
    )


def test_a_stranger_cannot_normalize_your_upload(client, api_headers):
    """Normalization parses the source bytes into an artifact it hands back.

    So this is a content leak, not a metadata one — the same bytes the download
    gate protects, returned in a different shape.
    """
    alice = _signup(client, "file-alice9@example.com")
    bob = _signup(client, "file-bob9@example.com")
    fid = _upload(client, alice, "alice_private.csv")

    run = _normalize(client, bob, fid)
    assert run.status_code == 404, (
        f"a stranger normalized the file: {run.status_code} {run.text[:200]}"
    )
    assert "ppm" not in run.text, "the source content came back inside the response"
    assert client.get(f"/files/{fid}/normalization-runs", headers=alice).json() == [], (
        "the refusal still wrote a normalization run against the owner's file"
    )


def test_a_stranger_cannot_list_your_normalization_runs(client, api_headers):
    """The run rows carry output_artifact_id, which is the handle to the bytes."""
    alice = _signup(client, "file-alice10@example.com")
    bob = _signup(client, "file-bob10@example.com")
    fid = _upload(client, alice, "alice_private.csv")
    assert _normalize(client, alice, fid).status_code == 201

    listed = client.get(f"/files/{fid}/normalization-runs", headers=bob)
    assert listed.status_code == 404, (
        f"a stranger listed the runs: {listed.status_code} {listed.text[:200]}"
    )
    absent = client.get("/files/99999/normalization-runs", headers=bob)
    assert absent.status_code == 404 and absent.json()["detail"] == listed.json()["detail"], (
        "an existing file answers differently from a missing one"
    )


def test_a_stranger_cannot_read_a_normalization_run_by_its_own_id(client, api_headers):
    """Gating the by-file listing alone would just move the leak one id over."""
    alice = _signup(client, "file-alice11@example.com")
    bob = _signup(client, "file-bob11@example.com")
    fid = _upload(client, alice, "alice_private.csv")
    run_id = _normalize(client, alice, fid).json()["id"]

    fetched = client.get(f"/normalization-runs/{run_id}", headers=bob)
    assert fetched.status_code == 404, (
        f"a stranger read the run by id: {fetched.status_code} {fetched.text[:200]}"
    )


def test_a_stranger_cannot_normalize_your_upload_through_the_reaction_import(client, api_headers):
    """The reaction importer owner-scopes its project id but not its file id.

    It then calls the very same normalize_file, so leaving it alone would keep
    the content leak alive behind a second door.
    """
    alice = _signup(client, "file-alice12@example.com")
    bob = _signup(client, "file-bob12@example.com")
    fid = _upload(client, alice, "alice_private.csv")

    imported = client.post(
        "/integrations/reactions/import-experiment-table",
        headers=bob,
        json={"file_id": fid},
    )
    assert imported.status_code == 404, (
        f"a stranger normalized the file via the importer: "
        f"{imported.status_code} {imported.text[:200]}"
    )
    assert "ppm" not in imported.text


def test_the_owner_keeps_the_write_paths(client, api_headers):
    """The same guard against over-correction the read paths already carry."""
    alice = _signup(client, "file-alice13@example.com")
    fid = _upload(client, alice, "alice_private.csv")

    run = _normalize(client, alice, fid)
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]

    assert client.get(f"/normalization-runs/{run_id}", headers=alice).status_code == 200
    runs = client.get(f"/files/{fid}/normalization-runs", headers=alice)
    assert runs.status_code == 200 and [row["id"] for row in runs.json()] == [run_id]

    assert client.delete(f"/files/{fid}", headers=alice).status_code == 200
    assert client.get(f"/files/{fid}", headers=alice).status_code == 404


def test_the_system_key_keeps_the_unscoped_write_view(client, api_headers):
    alice = _signup(client, "file-alice14@example.com")
    fid = _upload(client, alice, "alice_private.csv")

    run = _normalize(client, api_headers, fid)
    assert run.status_code == 201, run.text
    assert client.get(f"/normalization-runs/{run.json()['id']}", headers=api_headers).status_code == 200
    assert client.get(f"/files/{fid}/normalization-runs", headers=api_headers).status_code == 200
    assert client.delete(f"/files/{fid}", headers=api_headers).status_code == 200


def test_an_ingested_file_is_attributed_to_whoever_ingested_it(client, api_headers):
    """The second way a managed file gets created, and it stamped no owner.

    Read-side that is not a leak but its mirror image: the read gate refuses
    NULL-owner rows, so an ingested file was invisible to the very person who
    ingested it. The whole scheme rests on this column being written on EVERY
    creation path, not just the one the upload route uses.
    """
    alice = _signup(client, "file-alice15@example.com")
    run = client.post(
        "/ingestion-runs",
        headers=alice,
        json={
            "source_system": "instrument",
            "files_json": [
                {
                    "filename": "run-001.csv",
                    "content_text": "ppm,intensity\n1.0,10\n",
                    "content_type": "text/csv",
                    "file_kind": "processed_nmr",
                }
            ],
        },
    )
    assert run.status_code == 201, run.text
    file_ids = run.json()["metadata_json"]["file_ids_json"]
    assert file_ids, "the ingestion run recorded no files"

    for file_id in file_ids:
        assert client.get(f"/files/{file_id}", headers=alice).status_code == 200, (
            "an ingested file is unattributed, so its own ingester cannot read it"
        )


def test_a_watch_folder_scan_attributes_the_files_it_imports(client, api_headers, tmp_path):
    """The third creation path, and the one easiest to miss.

    It reaches ``upload_file_record`` two calls deep by way of the ingestion
    run, so a fix applied only to the routes that mint files directly would
    leave this one writing NULL-owner rows.
    """
    watch_dir = tmp_path / "instrument"
    watch_dir.mkdir()
    (watch_dir / "run-001.csv").write_text("ppm,intensity\n1.0,10\n")

    alice = _signup(client, "file-alice16@example.com")
    folder = client.post(
        "/instrument-watch-folders",
        headers=alice,
        json={
            "folder_path": str(watch_dir),
            "file_patterns_json": ["*.csv"],
            "recursive": False,
            "target_program": "spectracheck",
            "target_route": "processed_nmr",
            "status": "active",
        },
    )
    assert folder.status_code == 201, folder.text

    scan = client.post(
        f"/instrument-watch-folders/{folder.json()['id']}/scan", headers=alice, json={}
    )
    assert scan.status_code == 201, scan.text
    file_ids = scan.json()["metadata_json"]["file_ids_json"]
    assert file_ids, "the scan imported no files"

    for file_id in file_ids:
        assert client.get(f"/files/{file_id}", headers=alice).status_code == 200, (
            "a scanned file is unattributed, so the person who scanned cannot read it"
        )
