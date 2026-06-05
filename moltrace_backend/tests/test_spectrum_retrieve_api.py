"""Wire-level contract for ``POST /spectrum/retrieve`` (Prompt 8 retrieval endpoint).

Pins the request/response shape, the server-configured-index behaviour (graceful
when unset, real hits when set), the SMILES + shift-list query modes, the 400 /
422 paths, auth, and OpenAPI registration (so the FE's ``npm run generate:openapi``
picks up the typed contract). The encoding / index numerics are covered in
``tests/spectroscopy/test_similarity_scoring.py``.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from moltrace.spectroscopy.similarity import SpectrumIndex, encode_spectrum
from nmrcheck.api import create_app
from nmrcheck.settings import Settings


def _app(tmp_path):
    return create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'retrieve.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
            admin_emails=("admin@example.com",),
        )
    )


def _client(tmp_path) -> TestClient:
    return TestClient(_app(tmp_path))


def _post(client: TestClient, body: dict, key: str | None = "test-key"):
    headers = {"x-api-key": key} if key else {}
    return client.post("/spectrum/retrieve", headers=headers, json=body)


def _build_index(tmp_path) -> str:
    """A tiny FAISS index of three distinct reference spectra; returns its path."""
    refs = {
        "ethanol": ([3.6, 1.2], [58.0, 18.0]),
        "benzene": ([7.26], [128.4]),
        "acetone": ([2.1], [206.0, 30.0]),
    }
    index = SpectrumIndex()
    for name, (shifts_1h, shifts_13c) in refs.items():
        index.add(encode_spectrum(shifts_1h, shifts_13c), [name])
    path = tmp_path / "ref.faiss"
    index.save(str(path))
    return str(path)


def test_retrieve_not_configured_is_graceful(tmp_path, monkeypatch):
    monkeypatch.delenv("MOLTRACE_SIMILARITY_INDEX", raising=False)
    client = _client(tmp_path)
    with client:
        res = _post(client, {"shifts_1h": [7.26], "shifts_13c": [128.4]})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["index_available"] is False
    assert body["results"] == []
    assert body["query_source"] == "shifts"
    assert body["method"] == "vector_l2"
    assert any("not configured" in w.lower() for w in body["warnings"])


def test_retrieve_configured_index_finds_match(tmp_path, monkeypatch):
    path = _build_index(tmp_path)
    monkeypatch.setenv("MOLTRACE_SIMILARITY_INDEX", path)
    client = _client(tmp_path)
    with client:
        res = _post(client, {"shifts_1h": [7.26], "shifts_13c": [128.4], "top_k": 3})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["index_available"] is True
    assert body["index_size"] == 3
    assert body["results"]
    # benzene query -> benzene is the nearest neighbour (distance ~ 0)
    assert body["results"][0]["id"] == "benzene"
    assert body["results"][0]["l2_distance"] < 1e-3
    # results are sorted ascending by distance
    distances = [r["l2_distance"] for r in body["results"]]
    assert distances == sorted(distances)


def test_retrieve_smiles_mode(tmp_path, monkeypatch):
    monkeypatch.delenv("MOLTRACE_SIMILARITY_INDEX", raising=False)
    client = _client(tmp_path)
    with client:
        res = _post(client, {"smiles": "c1ccccc1"})
    assert res.status_code == 200, res.text
    assert res.json()["query_source"] == "smiles"


def test_retrieve_empty_query_is_400(tmp_path):
    client = _client(tmp_path)
    with client:
        res = _post(client, {})
    assert res.status_code == 400


def test_retrieve_invalid_smiles_is_400(tmp_path):
    client = _client(tmp_path)
    with client:
        res = _post(client, {"smiles": "not_a_smiles)("})
    assert res.status_code == 400


def test_retrieve_top_k_bounds_are_validated(tmp_path):
    client = _client(tmp_path)
    with client:
        assert _post(client, {"shifts_1h": [1.0], "top_k": 0}).status_code == 422
        assert _post(client, {"shifts_1h": [1.0], "top_k": 5000}).status_code == 422


def test_retrieve_requires_auth(tmp_path):
    client = _client(tmp_path)
    with client:
        res = _post(client, {"shifts_1h": [1.0]}, key=None)
    assert res.status_code in (401, 403)


def test_retrieve_registered_in_openapi(tmp_path):
    paths = _app(tmp_path).openapi()["paths"]
    assert "/spectrum/retrieve" in paths
    assert "post" in paths["/spectrum/retrieve"]
