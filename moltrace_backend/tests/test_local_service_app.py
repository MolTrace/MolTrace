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


def test_every_mounted_route_corresponds_to_a_declared_operation() -> None:
    """Routes and the served list were separate, and nothing tied them.

    The construction check validated the LIST while @app.get registered routes
    independently — so a route could be mounted for an operation the list did not
    contain, and the check would pass. Routes are now derived from ROUTES, and
    this asserts the app's actual route table matches it.
    """
    from nmrcheck.local_service_app import ROUTES, create_local_app

    app = create_local_app(credential=CRED)
    mounted = {
        (next(iter(r.methods - {"HEAD"})), r.path)
        for r in app.routes
        if getattr(r, "methods", None) and not r.path.startswith("/openapi")
    }
    declared = set(ROUTES.values())
    assert declared <= mounted, f"declared but not mounted: {declared - mounted}"
    extra = {m for m in mounted if m not in declared and not m[1].startswith("/docs")}
    assert not extra, f"mounted but not declared in ROUTES: {extra}"


def test_a_route_declared_with_no_handler_fails_at_construction(monkeypatch) -> None:
    from nmrcheck import local_service_app

    monkeypatch.setattr(
        local_service_app,
        "ROUTES",
        {**local_service_app.ROUTES, "analysis.draft": ("POST", "/draft")},
    )
    with pytest.raises(ValueError, match="no handler"):
        local_service_app.create_local_app(credential=CRED)


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


def test_an_unauthenticated_caller_cannot_grow_the_journal_without_bound(client: TestClient) -> None:
    """Measured before the cap: 200 unauthenticated requests produced 200 entries.

    Two harms and the second is worse — unbounded growth, and DILUTION: a genuine
    refusal worth investigating buried under thousands of manufactured ones.
    """
    from nmrcheck.local_service_app import JOURNAL, REFUSAL_ENTRY_CAP

    JOURNAL.clear()
    for _ in range(REFUSAL_ENTRY_CAP * 5):
        client.get("/health")
    assert len(JOURNAL) == REFUSAL_ENTRY_CAP, (
        f"{REFUSAL_ENTRY_CAP * 5} unauthenticated requests produced {len(JOURNAL)} entries"
    )


def test_the_cap_is_RECORDED_not_silent(client: TestClient) -> None:
    """Dropping entries silently would leave a journal that looks complete."""
    from nmrcheck.local_service_app import JOURNAL, REFUSAL_ENTRY_CAP

    JOURNAL.clear()
    for _ in range(REFUSAL_ENTRY_CAP * 2):
        client.get("/health")
    assert JOURNAL[-1].payload["operation"] == "journal.refusals-capped"
    assert "not being written" in JOURNAL[-1].payload["cause"]


def test_capping_refusals_never_suppresses_a_SUCCESS(client: TestClient) -> None:
    """Successes require the credential, so their volume is not attacker-controlled.

    A cap that silenced them would let an attacker erase the record of real work
    by flooding refusals first — turning a denial-of-service into an evidence
    problem, which is the worse of the two.
    """
    from nmrcheck.local_service_app import JOURNAL, REFUSAL_ENTRY_CAP

    JOURNAL.clear()
    for _ in range(REFUSAL_ENTRY_CAP * 3):
        client.get("/health")
    for _ in range(5):
        client.get("/health", headers=auth())
    successes = [e for e in JOURNAL if not e.payload["refused"]]
    assert len(successes) == 5, "authenticated work was suppressed by a refusal flood"


def test_the_journal_never_records_the_credential(client: TestClient) -> None:
    from nmrcheck.local_service_app import JOURNAL

    JOURNAL.clear()
    client.get("/health", headers=auth())
    client.get("/health", headers={"x-moltrace-local-service": "d" * 43})
    assert CRED not in str([e.payload for e in JOURNAL])
    assert "d" * 43 not in str([e.payload for e in JOURNAL])


# --- reading a spectrum off this computer -----------------------------------


def test_reading_a_spectrum_refuses_when_no_file_is_named(client: TestClient) -> None:
    """A rejection names its cause. An empty path is a caller mistake, not a 500."""
    for body in ({}, {"path": ""}, {"path": None}):
        r = client.post("/fid/open", json=body, headers=auth())
        assert r.status_code == 400, body
        assert "no file was named" in r.json()["detail"]


def test_a_file_that_is_not_there_is_refused_without_echoing_its_path(
    client: TestClient,
) -> None:
    """The refusal is written to the device journal, so it must not carry a path.

    A filename can carry a compound name — which is exactly the class of thing
    this platform does not put into durable records without being asked.
    """
    secret_ish = "/tmp/AcmeCorp-CANDIDATE-7731/acquisition"
    r = client.post("/fid/open", json={"path": secret_ish}, headers=auth())
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert secret_ish not in detail, "the refusal echoed the path back"
    assert "AcmeCorp" not in detail and "CANDIDATE" not in detail
    assert len(detail) > 10, "the refusal names no cause"


def test_a_file_that_is_not_a_spectrum_is_refused_not_guessed(
    client: TestClient, tmp_path
) -> None:
    """Refusing beats returning zero peaks: they are different answers.

    Zero peaks from a file that was never a spectrum is a true statement about a
    question nobody asked, and a caller cannot tell it apart from "the analysis
    found nothing" — which is a real and meaningful result.
    """
    junk = tmp_path / "notes.txt"
    junk.write_text("this is not an acquisition")
    r = client.post("/fid/open", json={"path": str(junk)}, headers=auth())
    assert r.status_code == 400
    assert r.json()["detail"], "refused with no cause"


def test_reading_a_spectrum_needs_the_credential_like_everything_else(
    client: TestClient,
) -> None:
    r = client.post("/fid/open", json={"path": "/anything"})
    assert r.status_code == 401
    assert "fid.open" not in HANDLER_CALLS, "the handler was reached without a credential"
