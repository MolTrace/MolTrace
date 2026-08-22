"""THE HARD RULE — reading, exporting and verifying existing records never stop.

A regulated customer must not be locked out of their own records by a commercial term. An
expired licence that made a batch record unreadable during an inspection would be a
data-integrity failure caused by the vendor's billing system, and no amount of "designed to
support ALCOA+" survives that.

The brief is explicit that it must be impossible to violate *by accident*, so discipline is not
the control. Three devices enforce it, and this file is where each is pinned:

* **behavioural (T9)** — twelve cells: four entitlement states × three surfaces, all 200. This
  is the control that actually holds, and it is the one that would catch a violation however it
  was introduced.
* **structural (T10, T11)** — the entitlement modules cannot themselves become a dependency,
  and no route carries one. See T10's docstring for what this does and does NOT establish: it
  is a speed bump, not a proof, and the document that specified it claimed more than it can
  deliver.
* **type-level (T12)** — the decision type can only ever ADD a capability. A denial is not
  representable, so there is no field a read path could branch on to refuse.
"""

from __future__ import annotations

import ast
import dataclasses
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nmrcheck import entitlement_statement as es
from nmrcheck import orm
from nmrcheck.entitlement_statement import EntitlementDecision
from nmrcheck.models import ENTITLEMENT_REFUSAL_DETAILS, ENTITLEMENT_UNAVAILABLE_DETAILS

SRC = Path(es.__file__).parent
ENTITLEMENT_STATEMENT_PATH = SRC / "entitlement_statement.py"
ENTITLEMENT_STORE_PATH = SRC / "entitlement_store.py"

RECORDS_GUARANTEE_SENTENCE = (
    "Your existing records remain available to read, export and verify."
)


def _signup(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/auth/sign-up",
        json={"email": email, "password": "password123", "password_confirm": "password123"},
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def _analysis_id(client: TestClient, headers: dict[str, str]) -> int:
    res = client.post(
        "/analyze",
        headers=headers,
        json={
            "sample_id": "entitlement-hard-rule",
            "smiles": "CCO",
            "nmr_text": (
                "1H NMR (400 MHz, CDCl3) δ 3.65 (q, J = 7.1 Hz, 2H), "
                "1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
            ),
            "solvent": "CDCl3",
        },
    )
    assert res.status_code == 200, res.text
    history = client.get("/history", headers=headers)
    assert history.status_code == 200, history.text
    return int(history.json()[0]["id"])


def _dossier_id(client: TestClient, headers: dict[str, str]) -> int:
    res = client.post(
        "/regulatory/dossiers", headers=headers, json={"title": "hard rule dossier"}
    )
    assert res.status_code in (200, 201), res.text
    return int(res.json()["id"])


# --------------------------------------------------------------------------- #
# The four entitlement states
# --------------------------------------------------------------------------- #
@dataclasses.dataclass(frozen=True)
class EntitlementState:
    name: str
    apply: object  # Callable[[FastAPI, TestClient, dict[str, str]], None]


def _never_provisioned(app, client, headers) -> None:
    app.state.settings = replace(
        app.state.settings,
        entitlement_issuing_private_key=None,
        entitlement_certificate_b64=None,
        entitlement_certificate_signature=None,
        entitlement_offline_period_days=None,
        entitlement_statement_validity_hours=None,
    )


def _certificate_expired(app, client, headers) -> None:
    from entitlement_authority import expired_authority

    authority = expired_authority()
    app.state.settings = replace(
        app.state.settings,
        entitlement_issuing_private_key=authority["issuing_seed"],
        entitlement_certificate_b64=authority["certificate_b64"],
        entitlement_certificate_signature=authority["certificate_signature"],
        entitlement_root_public_key=authority["root_public"],
        entitlement_offline_period_days=14,
        entitlement_statement_validity_hours=24,
    )


def _device_revoked(app, client, headers) -> None:
    created = client.post(
        "/mobile/device-sessions",
        headers=headers,
        json={"device_label": "revoked bench", "device_type": "desktop"},
    )
    assert created.status_code == 201, created.text
    with app.state.session_factory() as session:
        row = session.get(orm.MobileDeviceSessionORM, int(created.json()["id"]))
        row.status = "revoked"
        session.commit()


def _statement_expired_past_its_offline_period(app, client, headers) -> None:
    from entitlement_authority import valid_authority

    authority = valid_authority()
    app.state.settings = replace(
        app.state.settings,
        entitlement_issuing_private_key=authority["issuing_seed"],
        entitlement_certificate_b64=authority["certificate_b64"],
        entitlement_certificate_signature=authority["certificate_signature"],
        entitlement_root_public_key=authority["root_public"],
        # A statement issued under these terms lapsed long ago: its hard expiry plus the
        # published offline period are both in the past.
        entitlement_offline_period_days=1,
        entitlement_statement_validity_hours=1,
    )


ENTITLEMENT_STATES = (
    EntitlementState("never provisioned", _never_provisioned),
    EntitlementState("provisioned, certificate expired", _certificate_expired),
    EntitlementState("device revoked", _device_revoked),
    EntitlementState(
        "statement expired past its offline period", _statement_expired_past_its_offline_period
    ),
)


# --------------------------------------------------------------------------- #
# The three surfaces
# --------------------------------------------------------------------------- #
@dataclasses.dataclass(frozen=True)
class Surface:
    name: str
    call: object  # Callable[[TestClient, dict[str, str], dict[str, int]], Response]


SURFACES = (
    Surface("read a record", lambda c, h, ids: c.get(f"/history/{ids['analysis']}", headers=h)),
    Surface(
        "read a record in full",
        lambda c, h, ids: c.get(f"/history/{ids['analysis']}/full", headers=h),
    ),
    Surface("export the records", lambda c, h, ids: c.get("/history/export.csv", headers=h)),
    Surface(
        "verify the trail behind a record",
        lambda c, h, ids: c.get(
            f"/audit/regulatory_dossier/{ids['dossier']}/verify", headers=h
        ),
    ),
    Surface(
        "verify a signature on a record",
        lambda c, h, ids: c.get(f"/esignatures/records/{ids['signature']}/verify", headers=h),
    ),
)


@pytest.fixture()
def records(client: TestClient) -> tuple[dict[str, str], dict[str, int]]:
    headers = _signup(client, "hard-rule@example.com")
    analysis = _analysis_id(client, headers)
    dossier = _dossier_id(client, headers)

    record = client.post(
        "/controlled-records",
        headers=headers,
        json={"record_type": "sop", "title": "Hard rule SOP"},
    )
    assert record.status_code == 201, record.text
    step_up = client.post(
        "/auth/step-up/password", headers=headers, json={"password": "password123"}
    )
    assert step_up.status_code == 200, step_up.text
    signature = client.post(
        "/esignatures/records",
        headers=headers,
        json={
            "signer_name": "Hard Rule",
            "signature_meaning": "approved",
            "target_type": "controlled_record",
            "target_id": int(record.json()["id"]),
            "reason": "inspection copy",
        },
    )
    assert signature.status_code in (200, 201), signature.text
    return headers, {
        "analysis": analysis,
        "dossier": dossier,
        "signature": int(signature.json()["id"]),
    }


# --------------------------------------------------------------------------- #
# T9 — the behavioural cells. This is the device that actually holds.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("state", ENTITLEMENT_STATES, ids=lambda s: s.name)
@pytest.mark.parametrize("surface", SURFACES, ids=lambda s: s.name)
def test_reading_exporting_and_verifying_never_stop(app, client, records, state, surface):
    headers, ids = records
    state.apply(app, client, headers)

    response = surface.call(client, headers, ids)

    assert response.status_code == 200, (
        "an entitlement state made an existing record unreadable — a customer must never be "
        f"locked out of their own regulated records by a commercial term "
        f"({surface.name}, {state.name}): {response.status_code} {response.text[:200]}"
    )


# --------------------------------------------------------------------------- #
# T10 — structural. Read the docstring: it establishes less than it looks like it does.
# --------------------------------------------------------------------------- #
def test_the_entitlement_modules_cannot_become_a_gate() -> None:
    """Neither entitlement module can *itself* be dropped into a ``Depends(...)`` list.

    **What this does NOT establish.** A gate can still be *constructed elsewhere* from a module
    shaped exactly like these. ``module_access`` is the proof: it imports only ``__future__``
    and ``typing``, defines no ``require_*`` callable, and is nonetheless the entire basis of
    ``api._module_licence_gate``, which raises a 403. So this test is a speed bump — a
    deliberate act is still required to break the rule — and **T9 is the control that holds**.
    The design note this test came from claimed non-attachability was structural; it is not,
    and recording that honestly is worth more than the stronger-sounding claim.
    """
    for module_path in (ENTITLEMENT_STATEMENT_PATH, ENTITLEMENT_STORE_PATH):
        tree = ast.parse(module_path.read_text())

        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not any(
            name == "fastapi" or name.startswith("fastapi.") for name in imported
        ), f"{module_path.name} imports fastapi — it is one edit from becoming a gate"

        defined = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        assert not {name for name in defined if name.startswith("require_")}, (
            f"{module_path.name} defines a require_* callable — the shape of a dependency"
        )


def test_no_route_carries_an_entitlement_dependency(routed_app) -> None:
    """No route resolves an entitlement decision before its handler runs.

    Only the SUB-dependencies are flattened, not ``route.dependant`` itself: that node's
    ``call`` is the endpoint function, so flattening from the top matches any handler merely
    *named* for entitlement — every ``/tenant-entitlements`` route, and this delta's own
    issuance route. A guard that fires on the thing it is guarding is a name check, not a
    guard.
    """
    from test_module_access import _flatten

    offenders = []
    for route in routed_app.routes:
        path = getattr(route, "path", "")
        dependant = getattr(route, "dependant", None)
        if not path or dependant is None:
            continue
        names = {
            name
            for sub in getattr(dependant, "dependencies", [])
            for name in _flatten(sub)
        }
        if any("entitlement" in name.lower() for name in names):
            offenders.append(path)
    assert offenders == [], (
        "a route resolves entitlement before its handler runs — reading, exporting and "
        f"verifying must never be conditional on a commercial term: {offenders}"
    )


# --------------------------------------------------------------------------- #
# T12 — the decision type cannot express a denial
# --------------------------------------------------------------------------- #
FORBIDDEN_FIELD_SUBSTRINGS = ("denied", "blocked", "locked", "forbidden", "read_only")


def test_an_empty_entitlement_is_a_working_installation() -> None:
    """The empty decision is a *fully working* installation.

    It can open, read, export and verify every record it holds; it simply cannot acquire or
    analyse new data. There is no ``blocked``, no ``locked``, no ``read_only_denied`` — the
    type makes the lockout unrepresentable rather than merely discouraged.
    """
    decision = EntitlementDecision.empty(
        effective_now=datetime(2026, 8, 21, tzinfo=UTC),
        refusal=es.EntitlementVerifyRefusal("not_genuine", es.VERIFIER_MESSAGES["not_genuine"]),
    )
    assert decision.granted_modules == frozenset()
    assert decision.granted_package_profiles == frozenset()
    assert decision.refusal is not None, "an empty decision must explain itself"

    names = {field.name for field in dataclasses.fields(EntitlementDecision)}
    offending = {
        name for name in names if any(bad in name for bad in FORBIDDEN_FIELD_SUBSTRINGS)
    }
    assert not offending, (
        f"the decision type gained a field a read path could branch on to refuse: {offending}"
    )
    assert all(name.startswith("granted_") for name in names if "module" in name), (
        "a decision field names something other than a grant — 'granted_' is load-bearing"
    )


# --------------------------------------------------------------------------- #
# T13 — every refusal a CUSTOMER can see restates the guarantee.
#
# Ten strings, not five: the two §3.6 refusals a customer can see plus the eight verifier
# messages. The remaining four §3.6 refusals are deliberately EXCLUDED and pinned as such
# below — the guarantee answers a fear that only arises on a *loss* of access, and reassurance
# that appears everywhere stops being read anywhere.
# --------------------------------------------------------------------------- #
REFUSALS_THAT_CARRY_THE_GUARANTEE = ("device_revoked", "device_expired")
REFUSALS_THAT_DELIBERATELY_DO_NOT = (
    "device_not_enrolled",
    "device_identity_key_missing",
    "device_identity_key_mismatch",
    "no_licensed_modules",
)


def test_every_customer_facing_refusal_restates_the_records_guarantee() -> None:
    customer_visible = {
        code: ENTITLEMENT_REFUSAL_DETAILS[code] for code in REFUSALS_THAT_CARRY_THE_GUARANTEE
    }
    customer_visible.update(es.VERIFIER_MESSAGES)
    # ELEVEN codes, not the ten a first count suggests and not the five the design note said:
    # two issuance refusals plus NINE verifier codes. The verifier table reads as eight rows
    # because ``certificate_not_genuine`` and ``not_genuine`` share one row and one message —
    # they are two codes, and a count taken off the rendered table misses that.
    assert len(customer_visible) == 11, (
        f"expected eleven customer-visible refusal codes, counted {len(customer_visible)} — a "
        "test that pins the wrong number makes the wrong answer look deliberate"
    )
    assert len(set(customer_visible.values())) == 10, (
        "the eleven codes should render as ten distinct sentences; two of them deliberately "
        "share one, because a customer cannot act on the difference"
    )
    for code, message in customer_visible.items():
        assert RECORDS_GUARANTEE_SENTENCE in message, (
            f"the refusal {code!r} no longer tells a regulated user their records are safe, and "
            "a licence refusal is exactly the moment they need to hear it"
        )


def test_the_refusals_that_are_not_a_loss_of_access_stay_short() -> None:
    """Deliberately excluded, so the next reader does not 'fix' this in the other direction.

    Appending "your existing records remain available" to *"this installation has not been
    enrolled yet"* answers a question nobody asked.
    """
    for code in REFUSALS_THAT_DELIBERATELY_DO_NOT:
        assert RECORDS_GUARANTEE_SENTENCE not in ENTITLEMENT_REFUSAL_DETAILS[code], (
            f"{code!r} gained the records guarantee; it is not a loss of access, and "
            "reassurance that appears everywhere stops being read anywhere"
        )


def test_operator_diagnostics_are_excluded_from_the_guarantee() -> None:
    """An operator reading a provisioning diagnostic is not the person who fears losing their
    records. Padding every diagnostic with reassurance dilutes it where it matters."""
    for code, message in ENTITLEMENT_UNAVAILABLE_DETAILS.items():
        assert RECORDS_GUARANTEE_SENTENCE not in message, code
