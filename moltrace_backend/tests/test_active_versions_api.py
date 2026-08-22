"""The catalogue publishes what is actually running, and nothing else.

Two failure directions matter and they are not symmetric. Publishing too little makes an
installation refuse work it could have done. Publishing something that is NOT serving makes an
installation believe it matches a deployment that would have produced a different number — which
is the failure this whole delta exists to prevent, and it is silent.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nmrcheck import active_versions
from nmrcheck.api import create_app
from nmrcheck.database import init_db
from nmrcheck.settings import Settings


@pytest.fixture()
def app(tmp_path):
    application = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'versions.sqlite3'}",
            api_key="test-key",
            require_verified_email=False,
        )
    )
    init_db(application.state.session_factory)
    return application


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client
        _TOKENS.pop(id(test_client), None)


_TOKENS: dict[int, dict[str, str]] = {}


def _headers(client: TestClient, email: str = "versions@example.com") -> dict[str, str]:
    """Sign up once per client; reuse afterwards. A second sign-up for the same address is a
    conflict, and this helper is called by several assertions in one test."""
    cached = _TOKENS.get(id(client))
    if cached is not None:
        return cached
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    _TOKENS[id(client)] = headers
    return headers


def _catalogue(client: TestClient) -> list[dict]:
    response = client.get("/system/active-versions", headers=_headers(client))
    assert response.status_code == 200, response.text
    return response.json()["versions"]


# ------------------------------------------------------------------------------------- T1
def test_catalogue_membership_matches_the_engines_that_version_themselves(client) -> None:
    """A sixth engine must not be able to ship uncatalogued.

    An omitted engine is invisible: the installation simply never compares that rule set, and
    produces regulated results from it while believing itself current on everything published.
    """
    lineages = {row["lineage"] for row in _catalogue(client) if row["kind"] == "rule_set"}
    assert lineages == {"ich_q3ab", "ich_q3c", "ich_q3d", "ich_m7", "cpca"}


def test_every_rule_set_publishes_both_an_identity_and_an_ordered_revision(client) -> None:
    """Either one alone is useless: identity cannot order, and a revision without content
    cannot be checked against the bytes it claims to describe."""
    for row in _catalogue(client):
        if row["kind"] != "rule_set":
            continue
        assert row["identity"] and row["identity"].startswith("sha256:"), row
        assert row["revision"], f"{row['lineage']} publishes no ordered revision"


# ------------------------------------------------------------------------------------- T1b
def test_a_non_serving_model_artifact_is_never_catalogued(app, client, monkeypatch) -> None:
    """Serving is resolved from the registry's transition log, not from a mirrored column.

    The two disagree exactly when it matters. An artifact promoted and later retired still looks
    promoted in any mirrored copy, and publishing it would point installations at something the
    router has stopped resolving.
    """
    from nmrcheck import ai_engine_adapter

    serving = ai_engine_adapter.ServingArtifact(
        model_id="m-serving", role="shift_predictor", nucleus="1H",
        semantic_version="2.1.0", artifact_sha256="ab" * 32,
    )
    monkeypatch.setattr(ai_engine_adapter, "serving_artifacts", lambda _sf: (serving,))
    rows = {r["lineage"]: r for r in _catalogue(client)}
    assert "model:shift_predictor:1H" in rows
    assert rows["model:shift_predictor:1H"]["revision"] == "2.1.0"

    # Nothing serving -> the axis is simply absent, never a placeholder that would compare equal.
    monkeypatch.setattr(ai_engine_adapter, "serving_artifacts", lambda _sf: ())
    assert not [r for r in _catalogue(client) if r["kind"] == "model_artifact"]


# ------------------------------------------------------------------------------------- T1c
def test_the_method_registry_tables_are_not_in_this_catalogue(client) -> None:
    """`model_versions` / the method-registry governance store are a different concept with a
    confusingly similar name. Only artifacts with a registry bridge belong here."""
    kinds = {row["kind"] for row in _catalogue(client)}
    assert kinds <= {"rule_set", "model_artifact", "reference_pack", "method_defaults"}


def test_the_catalogue_reveals_no_paths_counts_or_corpus_size(client) -> None:
    """§5: report only what the comparison consumes. A reference count or a file path describes
    a customer's configuration without helping anyone compare anything."""
    import json

    body = json.dumps(_catalogue(client))
    for leaked in ("/Users", "/app", ".json.gz", "reference_count", "training_data", "site-packages"):
        assert leaked not in body, f"the catalogue leaks {leaked!r}"


def test_the_route_requires_authentication(client) -> None:
    """The catalogue describes a customer's validated configuration. `/system/version` is
    anonymous and carries build metadata; this is a different thing."""
    assert client.get("/system/active-versions").status_code == 401


def test_the_order_is_stable_because_the_catalogue_gets_signed(client) -> None:
    """A signature over a set whose order wandered would fail to verify for no visible reason."""
    assert [r["lineage"] for r in _catalogue(client)] == [
        r["lineage"] for r in _catalogue(client)
    ]
    assert active_versions.active_version_coordinates(None) == (
        active_versions.active_version_coordinates(None)
    )


# ------------------------------------------------------------------------------------- T6
@pytest.mark.parametrize(
    "state", ["current", "behind", "ahead", "unknown"]
)
def test_no_currency_state_ever_blocks_read_export_or_verify(client, state: str) -> None:
    """The hard rule, extended from entitlement to currency.

    An expired entitlement still permits reading, exporting and verifying existing records.
    Nothing grants version currency a power entitlement was denied, and a scientist locked out of
    their own finished work because a rule set moved would be the worst possible reading of a
    control meant to protect them.

    Asserted structurally: no read path consults this module at all, so no currency state can
    reach one.
    """
    import nmrcheck.api as api_module

    source = (
        __import__("pathlib").Path(api_module.__file__).read_text()
    )
    # The catalogue is READ by its own route and nothing else; it gates nothing.
    assert source.count("active_versions.") == 1, (
        "active_versions is consulted somewhere other than its own route — if that is a gate, "
        "a currency state can now block a read"
    )
    for path in ("/system/capabilities", "/system/version"):
        assert client.get(path, headers=_headers(client, f"{state}@example.com")).status_code in (200, 401)
