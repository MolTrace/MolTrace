import asyncio
import io
from tempfile import mkdtemp

from fastapi import UploadFile
from starlette.requests import Request

from nmrcheck.api import (
    AccessContext,
    analyze,
    create_app,
    login_json,
    metrics_summary,
    project_dashboard,
    register,
    report_detail,
    report_from_analysis,
    review_approve,
    sample_analyses,
    sample_compare,
    sample_detail,
    sample_reports,
    sample_timeline,
    spectrum_analyze,
    validate as validate_endpoint,
    workspace_create_project,
    workspace_create_project_sample,
    workspace_link_project_sample_analysis,
)
from nmrcheck.database import init_db
from nmrcheck.models import (
    AnalysisInputs,
    ProjectCreate,
    ProjectSampleAnalysisLink,
    ProjectSampleCreate,
    ReviewDecisionCreate,
    UserCreate,
    UserLogin,
)
from nmrcheck.settings import Settings


def _build_request() -> Request:
    tmpdir = mkdtemp(prefix="nmrcheck-e2e-")
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmpdir}/e2e.sqlite3",
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
        "path": "/e2e/test",
        "query_string": b"",
    }
    return Request(scope)


def test_product_end_to_end_regression_flow() -> None:
    request = _build_request()
    user = register(UserCreate(email="chemist@example.com", password="ChemPass123!"), request)
    admin = register(UserCreate(email="admin@example.com", password="AdminPass123!"), request)

    user_login = login_json(UserLogin(email=user.email, password="ChemPass123!"), request)
    admin_login = login_json(UserLogin(email=admin.email, password="AdminPass123!"), request)
    assert admin_login.user.is_admin is True

    user_context = AccessContext(user=user_login.user, raw_token=user_login.access_token)
    admin_context = AccessContext(user=admin_login.user, raw_token=admin_login.access_token)

    invalid = validate_endpoint(
        AnalysisInputs(sample_id="bad-smiles", smiles="not-a-smiles", nmr_text="3.00 (s, 1H)")
    )
    assert invalid.structure_valid is False
    assert invalid.errors

    ethanol_payload = AnalysisInputs(
        sample_id="e2e-ethanol",
        smiles="CCO",
        nmr_text="3.65 (q, 2H), 1.26 (t, 3H), 2.10 (br s, 1H)",
        solvent="CDCl3",
    )
    ethanol = analyze(ethanol_payload, request, user_context)
    assert ethanol.sample_id == "e2e-ethanol"

    async def run_spectrum_upload() -> None:
        result = await spectrum_analyze(
            request=request,
            file=UploadFile(
                filename="ethanol-peaks.csv",
                file=io.BytesIO(
                    b"shift_ppm,multiplicity,integration_h\n3.65,q,2\n1.26,t,3\n2.10,br s,1\n"
                ),
            ),
            smiles="CCO",
            sample_id="e2e-spectrum",
            solvent="CDCl3",
            frequency_mhz=400.0,
            reference_ppm=None,
            reference_nmr_text=None,
            manual_nmr_text=None,
            peak_sensitivity=None,
            mask_solvent_regions=False,
            context=user_context,
        )
        assert result.preview.source_mode == "peak_table"
        assert result.analysis.sample_id == "e2e-spectrum"

    asyncio.run(run_spectrum_upload())

    project = workspace_create_project(
        ProjectCreate(name="E2E project", description="Regression workspace"),
        request,
        user=user_login.user,
    )
    sample = workspace_create_project_sample(
        project.id,
        ProjectSampleCreate(
            sample_id="e2e-ethanol",
            smiles="CCO",
            nmr_text=ethanol_payload.nmr_text,
            solvent="CDCl3",
        ),
        request,
        user=user_login.user,
    )

    analyses = sample_analyses(str(sample.id), request, user=user_login.user)
    ethanol_analysis = next(item for item in analyses if item.sample_id == "e2e-ethanol")
    linked = workspace_link_project_sample_analysis(
        project.id,
        sample.id,
        ProjectSampleAnalysisLink(analysis_id=ethanol_analysis.id),
        request,
        user=user_login.user,
    )
    assert linked.analysis_id == ethanol_analysis.id

    detail = sample_detail(str(sample.id), request, user=user_login.user)
    assert detail.latest_analysis is not None
    comparison = sample_compare(str(sample.id), request, user=user_login.user)
    assert comparison.items

    decision = review_approve(
        ethanol_analysis.id,
        ReviewDecisionCreate(comment="Approved in e2e regression"),
        request,
        admin_context,
    )
    assert decision.new_status == "approved"

    stored_report = report_from_analysis(ethanol_analysis.id, request, user_context)
    assert stored_report.report.review_decisions
    assert report_detail(stored_report.id, request, user_context).id == stored_report.id

    reports = sample_reports(str(sample.id), request, user=user_login.user)
    assert any(report.id == stored_report.id for report in reports.reports)
    timeline = sample_timeline(str(sample.id), request, user=user_login.user)
    assert any(item.action == "approve" for item in timeline.review_decisions)

    dashboard = project_dashboard(project.id, request, user=user_login.user)
    assert dashboard.sample_count == 1
    assert dashboard.analysis_count == 1
    assert dashboard.approved_reviews == 1
    assert dashboard.solvent_distribution["CDCl3"] == 1

    metrics = metrics_summary(request, context=admin_context)
    assert metrics.total_analyses >= 2
    assert metrics.approved_reviews >= 1
    assert metrics.hours_saved_estimate > 0
