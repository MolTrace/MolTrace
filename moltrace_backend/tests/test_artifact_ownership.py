"""Derived artifacts belong to whoever caused them.

``artifact_records`` gained ``created_by_user_id`` in migration 0043 and the
read gates were wired to it at the same time — ``get_artifact_record`` and
``get_artifact_download`` both refuse a row whose owner is not the caller.

But **nothing ever wrote the column.** All four sites that build an
``ArtifactRecordORM`` left it NULL, and a NULL owner is refused to every scoped
caller by design (see the managed-file gate: "nobody is recorded as
responsible" must not read as "anyone may read it"). The result was a gate that
refused everyone:

    owner: POST /files/{id}/normalize -> 201, output_artifact_id = 1
    owner: GET  /artifacts/1          -> 404   *** their own artifact ***

So the leak the gate was written to stop was never open here, and the gate
instead made every derived artifact unreachable to the person who produced it.
That is the same shape as the unattributed ingestion fixed in 6089cea, one
table over: a read gate landed without its write.

An artifact has no owner of its own to inherit at read time, so the stamp is
the only thing that can carry attribution. The rules used below:

  * a job's artifacts are stamped with the actor who submitted the job
  * a workflow step's artifacts likewise, threaded from the run's actor
  * a NORMALIZATION artifact is stamped with the SOURCE FILE's owner, not the
    caller: it is a derived output, so it follows the data rather than whoever
    happened to press the button. A system key normalising A's file must not
    produce an artifact A cannot read.
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


def _normalize_artifact(client: TestClient, headers: dict[str, str], file_id: int) -> int:
    res = client.post(f"/files/{file_id}/normalize", headers=headers, json={})
    assert res.status_code == 201, res.text
    artifact_id = res.json()["output_artifact_id"]
    assert artifact_id, "normalization produced no artifact to test"
    return int(artifact_id)


def _report_job_artifact(client: TestClient, headers: dict[str, str]) -> int:
    """A report_compose job takes only parameters, so it needs no other fixture."""
    res = client.post(
        "/jobs",
        headers=headers,
        json={
            "job_type": "report_compose",
            "parameters_json": {
                "report_title": "Ownership fixture report",
                "report_json": {"summary": "fixture", "human_review_required": True},
            },
        },
    )
    assert res.status_code == 201, res.text
    ids = res.json()["artifact_ids"]
    assert ids, "the job produced no artifact"
    return int(ids[0])


def test_the_owner_can_read_the_artifact_their_normalization_produced(client, api_headers):
    """The gate must not close on the person it exists to protect."""
    alice = _signup(client, "art-alice@example.com")
    fid = _upload(client, alice, "alice_private.csv")
    artifact_id = _normalize_artifact(client, alice, fid)

    record = client.get(f"/artifacts/{artifact_id}", headers=alice)
    assert record.status_code == 200, (
        f"the owner cannot read their own derived artifact: "
        f"{record.status_code} {record.text[:200]}"
    )
    download = client.get(f"/artifacts/{artifact_id}/download", headers=alice)
    assert download.status_code == 200, "the owner cannot download their own artifact"


def test_a_stranger_cannot_read_the_artifact_from_your_file(client, api_headers):
    """The artifact carries the parsed contents of the source spectrum."""
    alice = _signup(client, "art-alice2@example.com")
    bob = _signup(client, "art-bob2@example.com")
    fid = _upload(client, alice, "alice_private.csv")
    artifact_id = _normalize_artifact(client, alice, fid)

    record = client.get(f"/artifacts/{artifact_id}", headers=bob)
    assert record.status_code == 404, (
        f"a stranger read the derived artifact: {record.status_code} {record.text[:200]}"
    )
    download = client.get(f"/artifacts/{artifact_id}/download", headers=bob)
    assert download.status_code == 404, "a stranger downloaded the derived artifact"


def test_a_normalization_artifact_follows_the_file_not_the_caller(client, api_headers):
    """A derived output belongs to the data's owner, not whoever ran the job.

    The system key can normalise anyone's file. If the artifact were stamped
    with the caller, that would be a NULL owner and the file's actual owner
    could never read the thing derived from their own spectrum.
    """
    alice = _signup(client, "art-alice3@example.com")
    fid = _upload(client, alice, "alice_private.csv")
    artifact_id = _normalize_artifact(client, api_headers, fid)

    assert client.get(f"/artifacts/{artifact_id}", headers=alice).status_code == 200, (
        "the file's owner cannot read an artifact derived from their own file"
    )


def test_the_owner_can_read_the_artifact_their_job_produced(client, api_headers):
    alice = _signup(client, "art-alice4@example.com")
    artifact_id = _report_job_artifact(client, alice)

    assert client.get(f"/artifacts/{artifact_id}", headers=alice).status_code == 200, (
        "the submitter cannot read the artifact their own job produced"
    )


def test_a_stranger_cannot_read_the_artifact_your_job_produced(client, api_headers):
    alice = _signup(client, "art-alice5@example.com")
    bob = _signup(client, "art-bob5@example.com")
    artifact_id = _report_job_artifact(client, alice)

    record = client.get(f"/artifacts/{artifact_id}", headers=bob)
    assert record.status_code == 404, (
        f"a stranger read the artifact from another account's job: "
        f"{record.status_code} {record.text[:200]}"
    )


def test_the_system_key_keeps_the_unscoped_artifact_view(client, api_headers):
    alice = _signup(client, "art-alice7@example.com")
    fid = _upload(client, alice, "alice_private.csv")
    artifact_id = _normalize_artifact(client, alice, fid)

    assert client.get(f"/artifacts/{artifact_id}", headers=api_headers).status_code == 200
