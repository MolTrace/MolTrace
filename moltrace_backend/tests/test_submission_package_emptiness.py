"""A submission package with no evidence must not report itself ready.

Probed live during the B2 loop test:

    POST /regulatory/dossiers/{id}/submission-package  {}   -> 201
      file_ids_json:     []
      artifact_ids_json: []
      warnings:          []
      status:            "ready_for_review"
      package_sha256:    "882564c4e0594a58cb931549200b2cb1dae087964e90b1ce2f68250daad5c0ce"

A regulatory submission package containing nothing came back marked ready for
review, over a valid-looking SHA-256 of an empty manifest, with no warning.

What makes that a defect rather than a design choice is the asymmetry. Reference
a file that does not exist and the manifest DOES warn:

    {"file_ids_json": [999999]}
      warnings: ['File 999999 was not found for the export package manifest.']

So absent-referent was caught and absent-reference was not — the same
half-applied-guard shape as the action-item hole (b049003), the compound
registry (32b7c5c), the FID review gate, and the Repho single-candidate case.
And the empty package is the more dangerous of the two, because it looks
complete: real digest, empty warnings, ready status, nothing to alert a
reviewer. A caller that simply omits ``file_ids_json`` — an FE bug, a
mis-shaped request — gets a submission package with no evidence and no
complaint.

The caller choosing the contents is deliberate and stays that way; this only
insists that choosing *nothing* is reported rather than blessed.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _dossier(client: TestClient, headers: dict[str, str], title: str = "Package emptiness") -> int:
    res = client.post("/regulatory/dossiers", headers=headers, json={"title": title})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _package(client: TestClient, headers: dict[str, str], dossier_id: int, **body) -> dict:
    res = client.post(
        f"/regulatory/dossiers/{dossier_id}/submission-package", headers=headers, json=body
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_an_empty_package_is_warned_about(client, api_headers):
    dossier_id = _dossier(client, api_headers)
    package = _package(client, api_headers, dossier_id)

    manifest = package["package_manifest_json"]
    assert manifest["files"] == [] and manifest["artifacts"] == []

    warnings = manifest.get("warnings") or []
    assert any("no files" in w.lower() or "no evidence" in w.lower() for w in warnings), (
        f"an empty submission package produced no warning: {warnings}"
    )


def test_an_empty_package_is_not_ready_for_review(client, api_headers):
    """Status is what a reviewer reads first, so it must not say ready."""
    dossier_id = _dossier(client, api_headers)
    package = _package(client, api_headers, dossier_id, status="ready_for_review")

    assert package["status"] != "ready_for_review", (
        "a package with no files and no artifacts still reports ready_for_review"
    )
    assert package["package_manifest_json"]["review_status"] != "ready_for_review", (
        "the manifest's review_status disagrees with the record's status"
    )


def test_a_package_with_evidence_is_untouched(client, api_headers):
    """The guard must not fire on a real package."""
    upload = client.post(
        "/files/upload",
        headers=api_headers,
        files={"file": ("coa.csv", b"evidence,value\npurity,99.1\n", "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    file_id = upload.json()["id"]

    dossier_id = _dossier(client, api_headers, "With evidence")
    package = _package(
        client, api_headers, dossier_id, file_ids_json=[file_id], status="ready_for_review"
    )

    manifest = package["package_manifest_json"]
    assert len(manifest["files"]) == 1
    assert manifest["files"][0]["file_id"] == file_id
    assert package["status"] == "ready_for_review", "a populated package was downgraded"
    assert not [w for w in (manifest.get("warnings") or []) if "no files" in w.lower()]


def test_a_missing_referent_still_warns(client, api_headers):
    """The half of the guard that already worked, pinned so it stays."""
    dossier_id = _dossier(client, api_headers, "Missing referent")
    package = _package(client, api_headers, dossier_id, file_ids_json=[999999])

    warnings = package["package_manifest_json"].get("warnings") or []
    assert any("999999" in w for w in warnings), (
        f"a reference to a non-existent file stopped warning: {warnings}"
    )


def test_the_digest_still_covers_the_warnings(client, api_headers):
    """The warning must be inside the hashed manifest, not bolted on beside it.

    A caveat that is not covered by ``package_sha256`` can be stripped without
    invalidating the digest, which would make the digest attest to a package
    more complete than the one that was built.
    """
    import hashlib
    import json

    dossier_id = _dossier(client, api_headers, "Digest covers warnings")
    package = _package(client, api_headers, dossier_id)

    manifest = package["package_manifest_json"]
    assert manifest.get("warnings"), "expected the empty-package warning in the manifest"

    recomputed = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert package["package_sha256"] == recomputed, (
        "package_sha256 no longer covers the manifest verbatim, so the warning "
        "it contains is not protected by the digest"
    )
