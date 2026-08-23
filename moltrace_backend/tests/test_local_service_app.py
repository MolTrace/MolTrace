"""The local service app: the guards, the policy table and the journal, wired.

Everything before this was a component with its own tests. This is the assembly,
and the assembly is where components that each work correctly can still combine
into something that does not — a guard installed after routing, a handler reached
before authentication, an operation served that the policy table withholds.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from nmrcheck.local_service_app import HANDLER_CALLS, create_local_app

CRED = "c" * 43


@pytest.fixture
def client() -> TestClient:
    HANDLER_CALLS.clear()
    return TestClient(create_local_app(credential=CRED), raise_server_exceptions=False)


def auth() -> dict[str, str]:
    return {"x-moltrace-local-service": CRED}


# --- the guard runs BEFORE anything else -----------------------------------


def test_a_served_operation_works_with_the_credential(client: TestClient) -> None:
    r = client.get("/health", headers=auth())
    assert r.status_code == 200


def test_no_credential_never_reaches_the_handler(client: TestClient) -> None:
    """Not merely refused — the handler must not run at all. A guard that refuses
    after the handler has already touched the record is not a guard."""
    r = client.get("/health")
    assert r.status_code == 401
    assert HANDLER_CALLS == [], "the handler ran despite the request being refused"


def test_a_wrong_credential_never_reaches_the_handler(client: TestClient) -> None:
    r = client.get("/health", headers={"x-moltrace-local-service": "d" * 43})
    assert r.status_code == 401
    assert HANDLER_CALLS == []


def test_an_origin_header_never_reaches_the_handler(client: TestClient) -> None:
    r = client.get("/health", headers={**auth(), "origin": "https://evil.example"})
    assert r.status_code == 401
    assert HANDLER_CALLS == []


def test_a_credential_in_the_query_string_is_refused(client: TestClient) -> None:
    r = client.get(f"/health?access_token={CRED}", headers=auth())
    assert r.status_code == 401
    assert HANDLER_CALLS == []


# --- the policy table decides what exists ----------------------------------


def test_an_operation_the_policy_table_withholds_is_not_served(client: TestClient) -> None:
    """signature.create is online-only. It must not exist here at all — not
    "exists and refuses", which would still be a local signing surface."""
    r = client.post("/signature", headers=auth(), json={})
    assert r.status_code == 404


def test_the_app_serves_only_operations_the_table_permits() -> None:
    from nmrcheck.local_service_app import SERVED_OPERATIONS
    from nmrcheck.offline_policy import is_served_locally

    for op in SERVED_OPERATIONS:
        assert is_served_locally(op), f"{op} is mounted locally but the policy table withholds it"


def test_mounting_a_withheld_operation_fails_at_construction(monkeypatch) -> None:
    """The mount-time check, tested directly.

    Removing it is invisible while SERVED_OPERATIONS happens to be valid — the
    static test above still passes, because both check the same property from
    different sides. This drives the runtime branch by making the list invalid,
    which is the only way to see it. Same shape as a guard masked by a downstream
    check: it needs an input only it can refuse.
    """
    from nmrcheck import local_service_app

    monkeypatch.setattr(
        local_service_app, "SERVED_OPERATIONS", ("system.health", "signature.create")
    )
    with pytest.raises(ValueError, match="withholds it"):
        local_service_app.create_local_app(credential=CRED)


# --- what the local app must NOT inherit from the cloud --------------------


def test_the_query_parameter_token_acceptor_is_absent(client: TestClient) -> None:
    """§7.1: the desktop profile REMOVES the inherited acceptor rather than
    declining to use it. Checked against the generated contract, because a
    dependency override leaves the parameter in the schema while appearing fixed."""
    schema = client.get("/openapi.json", headers=auth()).json()
    rendered = str(schema)
    assert "access_token" not in rendered, "the local contract still advertises a query-parameter credential"


# --- audit goes to the journal, not the cloud chain ------------------------


def test_a_served_operation_writes_to_the_device_journal(client: TestClient) -> None:
    from nmrcheck.local_service_app import JOURNAL

    JOURNAL.clear()
    client.get("/health", headers=auth())
    assert len(JOURNAL) == 1, "the operation wrote no journal entry"
    assert JOURNAL[0].payload["operation"] == "system.health"


def test_a_refused_request_still_writes_a_journal_entry(client: TestClient) -> None:
    """A refusal is the event most worth keeping. Journalling only successes
    produces a record in which nothing was ever refused."""
    from nmrcheck.local_service_app import JOURNAL

    JOURNAL.clear()
    client.get("/health")
    assert len(JOURNAL) == 1, "a refused request left no trace"
    assert JOURNAL[0].payload["refused"] is True


def test_the_journal_never_records_the_credential(client: TestClient) -> None:
    from nmrcheck.local_service_app import JOURNAL

    JOURNAL.clear()
    client.get("/health", headers=auth())
    client.get("/health", headers={"x-moltrace-local-service": "d" * 43})
    assert CRED not in str([e.payload for e in JOURNAL])
    assert "d" * 43 not in str([e.payload for e in JOURNAL])
