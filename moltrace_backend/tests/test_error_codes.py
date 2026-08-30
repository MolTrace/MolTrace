"""Stable error codes: every failure carries one, and `detail` is no longer an API.

The audit chain split `break_kind` out of `detail` for this exact reason. Five codes were
riding inside `detail` here, kept alive by three separate allowlists — the server's 403 list,
two exception handlers that bypassed the sanitizer, and the frontend proxy's own list.

All three are now gone or derived: the 403 list and both bypasses were removed once every
client had moved to `code`, and the proxy's list is generated from `PUBLIC_CODES`. So these
no longer pin that the old shape still works — they pin that it does not, and that the
vocabulary which replaced it stays well-formed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nmrcheck import error_codes
from nmrcheck.api import create_app


@pytest.fixture(scope="module")
def anon() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


# --- the field is always there -----------------------------------------------------------
def test_an_unmatched_route_carries_a_code(anon: TestClient) -> None:
    """The gap found while building this: an unmatched route raises Starlette's HTTPException,
    which is the PARENT of FastAPI's, so a handler registered on the subclass never saw it.
    Plain 404 is the first error any client meets."""
    body = anon.get("/no-such-route").json()
    assert body["code"] == error_codes.NOT_FOUND


def test_a_validation_failure_carries_a_code(anon: TestClient) -> None:
    r = anon.post("/spectrum/retrieve", json={"nonsense": True})
    assert r.status_code in (401, 422)
    assert r.json()["code"] in (error_codes.UNPROCESSABLE, error_codes.UNAUTHENTICATED)


def test_every_registered_code_resolves_to_itself() -> None:
    """A raise site that already states a code must be picked up unchanged — that is how 800
    routes were migrated without editing any of them."""
    for code in error_codes.REGISTRY:
        assert error_codes.code_for(403, code) == code


def test_an_unregistered_detail_falls_back_to_the_status_never_to_nothing() -> None:
    """Absence of a specific code must never mean absence of the field; a client that has to
    handle "sometimes there is a code" has gained nothing over parsing prose."""
    assert error_codes.code_for(404, "Dossier not found.") == error_codes.NOT_FOUND
    assert error_codes.code_for(403, "Access denied.") == error_codes.FORBIDDEN
    assert error_codes.code_for(500, "boom") == error_codes.UNAVAILABLE
    assert error_codes.code_for(418, None) == error_codes.BAD_REQUEST


# --- `detail` is no longer a carrier ------------------------------------------------------
def test_a_public_code_no_longer_survives_in_detail() -> None:
    """Re-baselined, and inverted rather than moved.

    This used to assert the opposite -- that a 403 whose `detail` IS a public code is echoed
    verbatim -- justified by "the SPA branches on `detail === "step_up_required"` today and
    must keep working until it has moved." That justification had already stopped holding
    before this change: the /api/backend proxy replaces `detail` on every 401/403, including
    when it forwards a recognised code, so the branch it was protecting never fired. The
    passthrough was being preserved for a reader that had already stopped reading.

    It also meant every newly registered public code silently widened what a 403 `detail` may
    say, as a side effect of registration. `code` carries the signal now.
    """
    from nmrcheck.api import PUBLIC_ACCESS_DENIED_DETAIL, _safe_http_exception_detail

    assert _safe_http_exception_detail(403, error_codes.MODULE_NOT_LICENSED) == (
        PUBLIC_ACCESS_DENIED_DETAIL
    )


def test_module_not_licensed_is_still_a_public_code() -> None:
    """Re-homed, not deleted.

    This assertion used to sit beside one pinning `PUBLIC_MACHINE_READABLE_403_DETAILS is
    error_codes.PUBLIC_CODES` -- an alias that is gone with the passthrough it fed. But this
    half was never about the alias: it says `module_not_licensed` is public, which is still
    true and still worth pinning. Deleting the test wholesale would have dropped it silently.
    """
    assert error_codes.MODULE_NOT_LICENSED in error_codes.PUBLIC_CODES


def test_a_public_code_never_names_a_resource_a_user_or_a_reason() -> None:
    """Public codes cross a sanitized 401/403 boundary. They may name a SITUATION only —
    "this plan does not include that product" is safe, "you do not own dossier 7" is not."""
    for code in error_codes.PUBLIC_CODES:
        assert code.islower() and " " not in code
        assert not any(ch.isdigit() for ch in code), f"{code} looks resource-specific"


# --- upgrade state -----------------------------------------------------------------------
def test_the_four_locked_states_are_distinguishable() -> None:
    ok = dict(served_by_deployment=True, enabled_for_workspace=True,
              provisioned=True, user_has_role=True)
    assert error_codes.upgrade_state(**ok) is None
    assert error_codes.upgrade_state(**{**ok, "user_has_role": False}) == error_codes.ROLE_REQUIRED
    assert error_codes.upgrade_state(**{**ok, "provisioned": False}) == (
        error_codes.PRODUCT_NOT_PROVISIONED
    )
    assert error_codes.upgrade_state(**{**ok, "enabled_for_workspace": False}) == (
        error_codes.PRODUCT_NOT_ENABLED
    )
    assert error_codes.upgrade_state(**{**ok, "served_by_deployment": False}) == (
        error_codes.PRODUCT_NOT_IN_PLAN
    )


def test_upgrade_state_reports_the_outermost_blocker_not_the_last_check() -> None:
    """A user whose plan lacks the product must not be told to ask an admin for a role. The
    role would not help, and sending them there wastes their time and an admin's."""
    assert error_codes.upgrade_state(
        served_by_deployment=False, enabled_for_workspace=False,
        provisioned=False, user_has_role=False,
    ) == error_codes.PRODUCT_NOT_IN_PLAN
