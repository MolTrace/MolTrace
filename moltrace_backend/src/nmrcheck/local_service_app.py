"""The local scientific service, assembled.

The guards, the policy table and the device journal, wired into one ASGI app.
Everything it composes has its own tests; this file exists because an assembly of
correct components can still be wrong — a guard installed after routing, a handler
reached before authentication, an operation served that the policy table withholds.

**The guard is raw ASGI middleware, not a dependency.** A FastAPI dependency runs
after routing and after the request has been matched, and §7.1 requires the
credential be compared "before any request body is read". Middleware is the only
layer that can promise that, and it also means an unauthenticated request never
reaches a handler at all rather than reaching one that refuses.

**Routes are mounted from an explicit list checked against the policy table.**
An operation the table withholds is not mounted, so it 404s rather than existing
and refusing — an endpoint that exists and refuses is still a local surface for
that operation, and for signing that distinction is the whole point.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .desktop_transport import DesktopTransportGuard, TransportRefusal
from .device_journal import ClockState, JournalEntry, append
from .local_science import process_spectrum
from .offline_policy import is_served_locally

#: Operations this app serves, and the route each one is reached by. Routes are
#: DERIVED from this map rather than declared separately with @app.get.
#:
#: They were separate, and nothing tied them: the construction check validated the
#: LIST while the routes were registered independently, so a route could be
#: mounted for an operation the list did not contain and the check would pass.
#: One definition, so they cannot diverge -- the same fix as the hashed body
#: written out twice, and the same reason.
ROUTES: dict[str, tuple[str, str]] = {
    # operation -> (method, path)
    "system.health": ("GET", "/health"),
    "fid.process": ("POST", "/fid/process"),
}

#: Kept as a name because tests and callers read it, derived so it cannot drift.
SERVED_OPERATIONS: tuple[str, ...] = tuple(ROUTES)

#: Process-local for now. The durable store lands with §7.8's storage work; the
#: chain logic does not change when it does.
JOURNAL: list[JournalEntry] = []

#: How many REFUSAL entries an unauthenticated caller may add before the journal
#: stops accepting more from that path.
#:
#: Measured: 200 unauthenticated requests produced 200 journal entries, so a local
#: process with no credential controlled the journal's size. Two harms, and the
#: second is worse: it grows without bound, and it DILUTES — a genuine refusal
#: worth investigating is buried under thousands of manufactured ones.
#:
#: Successes are never suppressed: they require the credential, so their volume is
#: not attacker-controlled. Only refusals are capped, and the cap is recorded once
#: rather than silently discarding.
REFUSAL_ENTRY_CAP = 64

#: Test observability: which handlers actually ran. A refused request must leave
#: this empty, and asserting on it is how "never reaches the handler" is checked
#: rather than assumed.
HANDLER_CALLS: list[str] = []


def _clock() -> ClockState:
    # Honest defaults until the time source is wired: the clock is NOT known to be
    # synchronized, so every entry says so. Claiming synchronization we have not
    # established would be the §8.4 defect exactly.
    return ClockState(
        device_now=datetime.now(UTC),
        synchronized=False,
        offset_seconds=None,
        last_sync_age_seconds=None,
        source="device",
    )


def _journal(operation: str, *, refused: bool, cause: str | None = None) -> None:
    # `cause` is the guard's own message, which never contains the credential --
    # desktop_transport is tested for that. Nothing from the request is copied in.
    if refused:
        refusals = sum(1 for e in JOURNAL if e.payload.get("refused"))
        if refusals >= REFUSAL_ENTRY_CAP:
            # Already capped, and the cap entry is already written. Dropped
            # silently HERE but not silently overall: the entry written at the
            # boundary said it was happening and how many were kept.
            return
        if refusals == REFUSAL_ENTRY_CAP - 1:
            JOURNAL.append(
                append(
                    JOURNAL,
                    payload={
                        "operation": "journal.refusals-capped",
                        "refused": True,
                        "cause": (
                            f"{REFUSAL_ENTRY_CAP} refusals recorded; further refusals are "
                            f"not being written, so an unauthenticated caller cannot "
                            f"dilute this journal"
                        ),
                    },
                    clock=_clock(),
                )
            )
            return
    JOURNAL.append(
        append(
            JOURNAL,
            payload={"operation": operation, "refused": refused, "cause": cause},
            clock=_clock(),
        )
    )


async def _health() -> dict[str, Any]:
    HANDLER_CALLS.append("system.health")
    _journal("system.health", refused=False)
    return {"status": "ok"}


#: Module-level singleton, because ruff's B008 is right: a call in a default
#: argument is evaluated once at import and shared, which is fine here and
#: surprising everywhere else.
_BODY = Body(...)


async def _fid_process(payload: dict = _BODY) -> dict[str, Any]:
    HANDLER_CALLS.append("fid.process")
    try:
        peaks = process_spectrum(
            ppm_axis=payload.get("ppm_axis", []),
            intensity=payload.get("intensity", []),
            nucleus=str(payload.get("nucleus", "unknown")),
            field_mhz=float(payload.get("field_mhz", 0.0)),
        )
    except ValueError as bad_input:
        # Journalled as a refusal: an analysis that could not run is an event
        # worth keeping, and the cause is the engine's own message about the
        # SHAPE of the input -- it carries no spectral data.
        _journal("fid.process", refused=True, cause=str(bad_input))
        raise HTTPException(status_code=400, detail=str(bad_input)) from None

    # The count, not the peaks. A journal that carried the results would become a
    # second copy of the science, and the record of what was DONE is the thing
    # this journal is for.
    _journal("fid.process", refused=False, cause=f"{len(peaks)} peaks")
    # No timestamp in the response. §8.4: a device clock is not a record time, and
    # a result that carries one starts being read as a record.
    return {"peaks": [p.to_dict() for p in peaks]}


class TransportGuardMiddleware:
    """Runs before routing, before the body, before any handler."""

    def __init__(self, app: ASGIApp, guard: DesktopTransportGuard) -> None:
        self.app = app
        self.guard = guard

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Every scope type that is NOT http is REFUSED, not waved through.
        #
        # A first version passed them to the app unguarded on the reasoning that
        # the app has no websocket routes. That is true today and is exactly the
        # kind of premise that stops being true quietly: the first websocket route
        # anyone adds would be unauthenticated, and nothing here would say so.
        # `lifespan` is the one legitimate non-http scope and it is startup
        # signalling, not a request, so it passes.
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":
            _journal(
                "unsupported-scope",
                refused=True,
                cause=f"scope type {scope['type']!r} is not served",
            )
            return
        try:
            self.guard.check(scope)
        except TransportRefusal as refusal:
            _journal(_operation_for(scope.get("path", "")), refused=True, cause=str(refusal))
            response = JSONResponse(
                status_code=401,
                content={"detail": "This request was not accepted by the local science service."},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _operation_for(path: str) -> str:
    # Also derived from ROUTES. A third hand-maintained copy of the path->operation
    # mapping is a third thing to drift.
    for operation, (_method, route_path) in ROUTES.items():
        if route_path == path:
            return operation
    return "unknown"


def create_local_app(
    *,
    credential: str,
    bound_host: str | None = None,
    bound_port: int | None = None,
) -> FastAPI:
    for operation in SERVED_OPERATIONS:
        if not is_served_locally(operation):
            raise ValueError(
                f"{operation!r} is mounted in the local service but the offline policy table "
                f"withholds it from local execution"
            )

    app = FastAPI(title="MolTrace local science service", docs_url=None, redoc_url=None)

    # One handler per declared route, registered from the map. Adding a route
    # means adding a line to ROUTES, which is the line the policy check reads.
    handlers = {"system.health": _health, "fid.process": _fid_process}
    for operation, (method, path) in ROUTES.items():
        handler = handlers.get(operation)
        if handler is None:
            raise ValueError(f"{operation!r} is declared in ROUTES with no handler")
        app.add_api_route(path, handler, methods=[method])

    app.add_middleware(
        TransportGuardMiddleware,
        guard=DesktopTransportGuard(
            credential=credential, bound_host=bound_host, bound_port=bound_port
        ),
    )
    return app
