from fastapi import status
from starlette.requests import Request

from nmrcheck.api import (
    AccessContext,
    analyze,
    audit_log,
    create_app,
    evidence_report_html,
    evidence_report_json,
    history,
    login_json,
    register,
    review_decisions,
    workspace_create_project,
    workspace_create_project_sample,
    workspace_link_project_sample_analysis,
    workspace_project_samples,
    workspace_projects,
)
from nmrcheck.database import init_db
from nmrcheck.models import (
    AnalysisInputs,
    ProjectCreate,
    ProjectSampleAnalysisLink,
    ProjectSampleCreate,
    UserCreate,
    UserLogin,
)
from nmrcheck.settings import Settings


def _build_request() -> Request:
    from tempfile import mkdtemp

    tmpdir = mkdtemp(prefix="nmrcheck-workspaces-")
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmpdir}/workspaces.sqlite3",
            require_verified_email=False,
            api_key="test-key",
        )
    )
    init_db(app.state.session_factory)
    scope = {
        "type": "http",
        "app": app,
        "headers": [],
        "method": "POST",
        "path": "/workspaces/test",
        "query_string": b"",
    }
    return Request(scope)


def test_workspaces_and_evidence_reports_flow() -> None:
    request = _build_request()
    user = register(UserCreate(email="workspace@example.com", password="ChemPass123!"), request)
    login = login_json(UserLogin(email=user.email, password="ChemPass123!"), request)
    context = AccessContext(user=login.user, raw_token=login.access_token)

    report = analyze(
        AnalysisInputs(
            sample_id="workspace-ethanol",
            smiles="CCO",
            nmr_text="1H NMR (400 MHz, CDCl3) δ 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)",
            solvent="CDCl3",
        ),
        request,
        context,
    )
    assert report.sample_id == "workspace-ethanol"

    history_items = history(request, limit=10, context=context)
    assert history_items
    latest = history_items[0]

    project = workspace_create_project(
        ProjectCreate(name="Launch campaign", description="Primary synthesis workspace"),
        request,
        user=login.user,
    )
    assert project.name == "Launch campaign"

    projects = workspace_projects(request, limit=20, user=login.user)
    assert any(item.id == project.id for item in projects)

    sample = workspace_create_project_sample(
        project.id,
        ProjectSampleCreate(
            sample_id=latest.sample_id,
            smiles=latest.smiles,
            nmr_text=latest.nmr_text,
            solvent=latest.solvent,
            analysis_id=latest.id,
        ),
        request,
        user=login.user,
    )
    assert sample.analysis_id == latest.id

    samples = workspace_project_samples(project.id, request, limit=20, user=login.user)
    assert any(item.id == sample.id for item in samples)

    linked_sample = workspace_link_project_sample_analysis(
        project.id,
        sample.id,
        ProjectSampleAnalysisLink(analysis_id=latest.id),
        request,
        user=login.user,
    )
    assert linked_sample.analysis_id == latest.id

    projects_after_link = workspace_projects(request, limit=20, user=login.user)
    linked_project = next(item for item in projects_after_link if item.id == project.id)
    assert linked_project.sample_count == 1
    assert linked_project.analysis_count == 1
    assert linked_project.linked_analysis_count == 1

    evidence_json = evidence_report_json(latest.id, request, context=context)
    assert evidence_json.analysis.id == latest.id
    assert evidence_json.parsed_nmr_text == latest.nmr_text
    assert evidence_json.time_saved_estimate >= 0.0

    owner_decisions = review_decisions(latest.id, request, context=context)
    assert owner_decisions == []

    owner_audit = audit_log(request, context=context, entity_type="analysis", entity_id=latest.id)
    assert any(item.entity_id == latest.id for item in owner_audit)

    evidence_html = evidence_report_html(latest.id, request, context=context)
    assert evidence_html.status_code == status.HTTP_200_OK
    body = evidence_html.body.decode("utf-8")
    assert "Evidence Report" in body
    assert "workspace-ethanol" in body
    assert "Parsed ¹H NMR text" in body
