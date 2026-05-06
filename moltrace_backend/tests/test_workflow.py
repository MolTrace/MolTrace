import asyncio
import inspect
import io
import json
from tempfile import mkdtemp

from fastapi import BackgroundTasks, UploadFile
from starlette.requests import Request

from nmrcheck.api import (
    AccessContext,
    analyze,
    create_app,
    history_export_csv,
    job_export_csv,
    job_export_json,
    login_json,
    register,
    review_approve,
    review_decisions,
    review_reject,
    reviews,
    spectrum_analyze,
    spectrum_preview,
    submit_job,
    validate as validate_endpoint,
)
from nmrcheck.database import init_db
from nmrcheck.models import AnalysisInputs, BatchAnalysisInputs, ReviewDecisionCreate, UserCreate, UserLogin
from nmrcheck.settings import Settings

TOBRAMYCIN_SMILES = "O[C@@]1([H])[C@]([C@@H](O)[C@@H](O[C@@]([C@]2(O)[H])([H])[C@@H](C([H])[C@H](N)[C@H]2O[C@@H](O[C@]([C@@]3([H])O)([H])CN)[C@@H](C3([H])[H])N)N)O[C@@H]1CO)([H])N"
TOBRAMYCIN_REFERENCE_TEXT = """'H NMR (500 MHz, D2O) 8 5.23 (d, J = 3.6 Hz, 1H), 5.08 (d, J = 3.9 Hz, 1H), 3.95 (ddd,
J= 10.3, 4.6, 2.6 Hz, 1H), 3.80 (dd, J = 6.6, 3.6 Hz, 2H), 3.68 (tdd, J = 9.2, 5.6, 3.1 Hz,
2H), 3.60 - 3.53 (т, 3H), 3.40 - 3.33 (m, 3H), 3.32 - 3.23 (m, 1H), 3.11 - 2.98 (m, 4H),
2.93 (tdd, J = 11.9,9.7, 4.1 Hz, 3H), 2.83 (dd, J = 13.6, 7.5 Hz, 1H), 2.07 (dt, J = 11.8,
4.5 Hz, 1H), 2.00 (dt, J = 13.0, 4.2 Hz, 1H), 1.71 - 1.60 (m, 1H), 1.27 (q, J = 12.5 Hz,
1H)"""
TRACE_CSV = """ppm,intensity
5.50,0
5.35,1
5.28,4
5.23,8
5.18,4
5.12,1
5.02,3
4.95,24
4.88,36
4.81,44
4.74,34
4.67,18
4.60,5
4.20,0
4.08,1
4.00,4
3.95,7
3.90,3
3.84,1
3.72,2
3.68,5
3.64,2
3.20,0
"""


def _build_request() -> Request:
    tmpdir = mkdtemp(prefix="nmrcheck-workflow-")
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmpdir}/workflow.sqlite3",
            require_verified_email=False,
            api_key="test-key",
            admin_emails=("admin@example.com",),
        )
    )
    init_db(app.state.session_factory)
    scope = {
        "type": "http",
        "app": app,
        "headers": [],
        "method": "POST",
        "path": "/workflow/test",
        "query_string": b"",
    }
    return Request(scope)


def _run_background_tasks(background_tasks: BackgroundTasks) -> None:
    for task in background_tasks.tasks:
        result = task.func(*task.args, **task.kwargs)
        if inspect.isawaitable(result):
            asyncio.run(result)


async def _read_streaming_response(response) -> str:
    chunks: list[bytes] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8"))
    return b"".join(chunks).decode("utf-8")


def test_core_user_workflow_smoke() -> None:
    request = _build_request()
    user = register(UserCreate(email="chemist@example.com", password="ChemPass123!"), request)
    admin = register(UserCreate(email="admin@example.com", password="AdminPass123!"), request)

    user_login = login_json(UserLogin(email=user.email, password="ChemPass123!"), request)
    admin_login = login_json(UserLogin(email=admin.email, password="AdminPass123!"), request)
    user_context = AccessContext(user=user_login.user, raw_token=user_login.access_token)
    admin_context = AccessContext(user=admin_login.user, raw_token=admin_login.access_token)

    analysis_payload = AnalysisInputs(
        sample_id="workflow-ethanol",
        smiles="CCO",
        nmr_text="3.65 (q, 2H), 1.26 (t, 3H), 2.10 (br s, 1H)",
        solvent="CDCl3",
    )

    validation = validate_endpoint(analysis_payload)
    assert validation.structure_valid is True
    assert validation.nmr_text_valid is True
    assert validation.structure_nmr_match is True

    report = analyze(analysis_payload, request, user_context)
    assert report.sample_id == "workflow-ethanol"
    assert report.parsed_peak_count == 3

    async def run_spectrum_flow() -> tuple[object, object]:
        preview = await spectrum_preview(
            request=request,
            file=UploadFile(filename="tobramycin.csv", file=io.BytesIO(TRACE_CSV.encode("utf-8"))),
            smiles=TOBRAMYCIN_SMILES,
            solvent="D2O",
            frequency_mhz=None,
            reference_ppm=None,
            reference_nmr_text=TOBRAMYCIN_REFERENCE_TEXT,
            peak_sensitivity=None,
            mask_solvent_regions=True,
            context=user_context,
        )
        analyzed = await spectrum_analyze(
            request=request,
            file=UploadFile(filename="tobramycin.csv", file=io.BytesIO(TRACE_CSV.encode("utf-8"))),
            smiles=TOBRAMYCIN_SMILES,
            sample_id="workflow-spectrum",
            solvent="D2O",
            frequency_mhz=None,
            reference_ppm=None,
            reference_nmr_text=TOBRAMYCIN_REFERENCE_TEXT,
            manual_nmr_text=None,
            peak_sensitivity=None,
            mask_solvent_regions=True,
            context=user_context,
        )
        return preview, analyzed

    spectrum_preview_result, spectrum_analyze_result = asyncio.run(run_spectrum_flow())
    assert spectrum_preview_result.comparison is not None
    assert spectrum_preview_result.comparison.matched_count >= 1
    assert spectrum_analyze_result.analysis.sample_id == "workflow-spectrum"

    background_tasks = BackgroundTasks()
    batch = BatchAnalysisInputs(
        items=[
            AnalysisInputs(
                sample_id="workflow-job-1",
                smiles="CCO",
                nmr_text="3.65 (q, 2H), 1.26 (t, 3H), 2.10 (br s, 1H)",
                solvent="CDCl3",
            ),
            AnalysisInputs(
                sample_id="workflow-job-2",
                smiles="CCO",
                nmr_text="3.65 (q, 2H), 1.26 (t, 3H), 2.10 (br s, 1H)",
                solvent="CDCl3",
            ),
        ]
    )
    accepted = submit_job(batch, request, background_tasks, user_context, job_name="workflow-smoke")
    assert accepted.accepted is True
    _run_background_tasks(background_tasks)

    queue_items = reviews(request, context=admin_context, review_status=None, limit=50)
    assert len(queue_items) >= 2

    approved = review_approve(
        queue_items[0].analysis.id,
        ReviewDecisionCreate(comment="Approved in workflow smoke test"),
        request,
        admin_context,
    )
    rejected = review_reject(
        queue_items[1].analysis.id,
        ReviewDecisionCreate(comment="Rejected in workflow smoke test"),
        request,
        admin_context,
    )
    assert approved.action == "approve"
    assert rejected.action == "reject"

    decisions = review_decisions(queue_items[0].analysis.id, request, admin_context)
    assert any(decision.action == "approve" for decision in decisions)

    history_csv = asyncio.run(
        _read_streaming_response(history_export_csv(request, limit=None, context=user_context))
    )
    assert "workflow-ethanol" in history_csv or "workflow-spectrum" in history_csv

    job_csv = asyncio.run(_read_streaming_response(job_export_csv(accepted.job.id, request, user_context)))
    assert "workflow-job-1" in job_csv
    job_json = asyncio.run(_read_streaming_response(job_export_json(accepted.job.id, request, user_context)))
    exported_job = json.loads(job_json)
    assert exported_job["job"]["job_name"] == "workflow-smoke"
    assert any(item["sample_id"] == "workflow-job-2" for item in exported_job["items"])
