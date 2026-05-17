
from __future__ import annotations

from html import escape

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .api import create_app
from .settings import get_settings
from .solvents import SOLVENT_PROFILES

settings = get_settings()
app: FastAPI = create_app(settings=settings)

DEFAULT_SMILES_FALLBACK = 'CCO'
DEFAULT_NMR_TEXT = '¹H NMR (400 MHz, CDCl3) δ 3.65 (q, J = 7.1 Hz, 2H), 1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)'
_SUBSCRIPT_TRANSLATION = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def _pretty_chemical_label(text: str) -> str:
    return text.translate(_SUBSCRIPT_TRANSLATION)


def _build_solvent_options(default_value: str) -> str:
    seen: set[str] = set()
    options: list[str] = []
    for profile in SOLVENT_PROFILES:
        name = profile.canonical_name
        if name in seen:
            continue
        seen.add(name)
        selected = " selected" if name == default_value else ""
        options.append(f'<option value="{escape(name)}"{selected}>{escape(_pretty_chemical_label(name))}</option>')
    if default_value and default_value not in seen:
        options.insert(0, f'<option value="{escape(default_value)}" selected>{escape(_pretty_chemical_label(default_value))}</option>')
    return "".join(options)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> str:
    default_smiles = escape(getattr(settings, "default_smiles", DEFAULT_SMILES_FALLBACK))
    default_solvent = escape(getattr(settings, "default_solvent", None) or "CDCl3")
    solvent_options = _build_solvent_options(default_solvent)
    default_nmr = escape(DEFAULT_NMR_TEXT)
    nmr2d_enabled = bool(getattr(settings, "enable_2d_nmr", True))
    nmr2d_contour_enabled = bool(getattr(settings, "enable_2d_contour_preview", True))
    nmr2d_raw_beta_enabled = bool(getattr(settings, "enable_raw_2d_fid_beta", False))
    nmr2d_feature_class = "" if nmr2d_enabled else "hidden"
    nmr2d_contour_disabled_attr = "" if nmr2d_contour_enabled else ' disabled aria-disabled="true"'
    nmr2d_raw_disabled_attr = "" if nmr2d_raw_beta_enabled else ' disabled aria-disabled="true"'
    nmr2d_flag_note = escape(
        "2D feature flag enabled. "
        f"Contour preview {'enabled' if nmr2d_contour_enabled else 'disabled'}. "
        f"Raw 2D FID beta {'enabled' if nmr2d_raw_beta_enabled else 'disabled'}."
    )
    html = r"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>NMRCheck</title>
      <style>
        :root {
          --bg: #f6f8fc;
          --panel: #ffffff;
          --panel-alt: #f9fbff;
          --border: #dce2ee;
          --text: #172033;
          --muted: #5d6b82;
          --primary: #2157d5;
          --primary-strong: #173a9a;
          --success: #14804a;
          --warn: #9a6700;
          --danger: #b42318;
          --success-bg: #ecfdf3;
          --warn-bg: #fff8e7;
          --danger-bg: #fef2f2;
          --shadow: 0 10px 30px rgba(12,31,61,.08);
          --radius: 18px;
        }
        * { box-sizing: border-box; }
        html, body { margin:0; padding:0; background:var(--bg); color:var(--text); font-family: Inter, Arial, sans-serif; }
        body { min-height:100vh; }
        a { color: var(--primary); text-decoration: none; }
        button { border:0; border-radius:12px; padding:.82rem 1rem; font-weight:600; cursor:pointer; transition:.15s ease; }
        button:hover { transform: translateY(-1px); }
        button.primary { background:var(--primary); color:#fff; }
        button.secondary { background:#eef2ff; color:var(--primary-strong); }
        button.ghost { background:#eef2f7; color:var(--text); }
        button.danger { background:#fee4e2; color:var(--danger); }
        button.inline-eye { background:transparent; color:var(--muted); padding:.25rem .5rem; border-radius:10px; margin:0; }
        button.inline-eye:hover { background:#eef2f7; transform:none; }
        input, textarea, select {
          width:100%; padding:.85rem .95rem; border:1px solid var(--border);
          border-radius:12px; background:#fff; color:var(--text); font-size:.96rem;
        }
        input[type="checkbox"] { width:auto; padding:0; accent-color:var(--primary); }
        textarea { min-height:160px; resize:vertical; }
        input.valid, textarea.valid, select.valid { border-color:#9fe3b2; background:#f7fff9; }
        input.invalid, textarea.invalid, select.invalid { border-color:#f4a4a4; background:#fff8f7; }
        .hidden { display:none !important; }
        .page { max-width: 1440px; margin:0 auto; padding:1.2rem; }
        .hero {
          background: linear-gradient(135deg,#173a9a 0%,#2855d9 65%,#6a88ff 100%);
          color:#fff; border-radius:24px; padding:1.4rem 1.6rem; box-shadow:var(--shadow); margin-bottom:1rem;
        }
        .hero h1 { margin:0 0 .35rem; font-size:2rem; }
        .hero p { margin:.2rem 0 .85rem; max-width:960px; line-height:1.45; }
        .hero-links { display:flex; flex-wrap:wrap; gap:.55rem; }
        .hero-links a {
          color:#fff; background:rgba(255,255,255,.14); padding:.45rem .8rem; border-radius:999px;
        }
        .auth-shell { min-height: calc(100vh - 2.4rem); display:grid; place-items:center; }
        .auth-card {
          width:min(980px, 100%); display:grid; grid-template-columns: 1.05fr .95fr; gap:1rem;
          background:transparent;
        }
        .card {
          background:var(--panel); border:1px solid var(--border); border-radius:var(--radius);
          padding:1rem; box-shadow:var(--shadow);
        }
        .card h2, .card h3 { margin:0 0 .7rem; }
        .muted { color:var(--muted); }
        .small { font-size:.9rem; }
        .field { margin-bottom:.85rem; }
        .field label { display:block; margin-bottom:.35rem; font-weight:600; }
        .input-wrap { position:relative; }
        .input-wrap input { padding-right:3rem; }
        .input-wrap .inline-eye {
          position:absolute; right:.35rem; top:50%; transform:translateY(-50%);
        }
        .layout {
          display:grid; grid-template-columns: 260px 1fr; gap:1rem;
        }
        .sidebar, .main { display:grid; gap:1rem; align-content:start; }
        .nav-list { display:grid; gap:.55rem; }
        .nav-btn { width:100%; text-align:left; background:#fff; color:var(--text); border:1px solid var(--border); }
        .nav-btn.active { background:var(--primary); color:#fff; border-color:var(--primary); }
        .status-badge {
          display:inline-flex; align-items:center; gap:.35rem; border-radius:999px; padding:.3rem .65rem;
          font-weight:700; font-size:.85rem; border:1px solid transparent;
        }
        .ok { background:var(--success-bg); color:var(--success); border-color:#9fe3b2; }
        .warn { background:var(--warn-bg); color:var(--warn); border-color:#f2d082; }
        .bad { background:var(--danger-bg); color:var(--danger); border-color:#f4a4a4; }
        .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:.8rem; }
        .summary-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:.75rem; margin-top:.7rem; }
        .metric { border:1px solid var(--border); border-radius:14px; padding:.8rem; background:#fff; }
        .metric .label { color:var(--muted); font-size:.82rem; text-transform:uppercase; }
        .metric .value { margin-top:.35rem; font-size:1.2rem; font-weight:700; }
        .panel { border:1px solid var(--border); border-radius:14px; padding:.85rem; background:var(--panel-alt); }
        .section { display:none; }
        .section.active { display:block; }
        .token-box, .json-box {
          width:100%; overflow:auto; background:#0e1528; color:#d8e0ff; padding:.85rem; border-radius:14px;
          font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:.83rem; line-height:1.45;
          word-break:break-all;
        }
        .token-box { min-height:76px; max-height:160px; }
        .json-box { min-height:180px; max-height:420px; white-space:pre-wrap; }
        table { width:100%; border-collapse:collapse; }
        th, td { text-align:left; padding:.65rem .55rem; border-bottom:1px solid var(--border); font-size:.92rem; }
        th { background:#f5f7fc; color:var(--muted); }
        .record-card {
          border:1px solid var(--border); border-radius:14px; padding:.85rem; background:#fff; margin-top:.7rem;
        }
        button:disabled { opacity:.55; cursor:not-allowed; transform:none; }
        button:disabled:hover { transform:none; }
        .project-grid, .sample-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:.75rem; }
        .project-card, .sample-card {
          border:1px solid var(--border); border-radius:8px; padding:.9rem; background:#fff;
          box-shadow:0 6px 18px rgba(12,31,61,.05);
        }
        .project-card.selected, .sample-card.selected { border-color:#9db6ff; box-shadow:0 8px 22px rgba(33,87,213,.12); }
        .project-card h4, .sample-card h4 { margin:0; font-size:1rem; }
        .card-kicker { color:var(--muted); font-size:.78rem; text-transform:uppercase; font-weight:700; letter-spacing:0; }
        .card-description { min-height:2.7em; margin:.55rem 0 .7rem; color:var(--muted); line-height:1.35; }
        .mini-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.55rem; }
        .mini-metric { border:1px solid var(--border); border-radius:8px; padding:.55rem; background:#f9fbff; min-width:0; }
        .mini-metric .label { color:var(--muted); font-size:.72rem; text-transform:uppercase; font-weight:700; }
        .mini-metric .value { margin-top:.25rem; font-weight:700; overflow-wrap:anywhere; }
        .sample-smiles { margin-top:.65rem; padding:.65rem; border-radius:8px; background:#0e1528; color:#d8e0ff; overflow:auto; }
        .report-preview { display:grid; gap:.85rem; }
        .report-section { border:1px solid var(--border); border-radius:8px; padding:.85rem; background:#fff; }
        .report-section h4 { margin:0 0 .55rem; }
        .row { display:flex; flex-wrap:wrap; gap:.6rem; align-items:center; }
        .checkbox-row { display:flex; gap:.7rem; align-items:flex-start; cursor:pointer; }
        .checkbox-row input { margin-top:.2rem; }
        .mono {
          font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
          font-size:.83rem;
          line-height:1.45;
        }
        .spectrum-shell { display:grid; gap:.8rem; margin-top:.8rem; }
        .spectrum-stage {
          position:relative; border:1px solid var(--border); border-radius:14px; background:#fff; overflow:hidden;
          min-height:340px;
        }
        .spectrum-plot { width:100%; min-height:340px; background:#fff; }
        .spectrum-hover-rail {
          position:absolute; top:12px; right:12px; bottom:12px; width:78px; display:flex; align-items:stretch;
          justify-content:center; opacity:0; pointer-events:none; transform:translateX(10px);
          transition:opacity .18s ease, transform .18s ease; z-index:10;
        }
        .spectrum-stage:hover .spectrum-hover-rail,
        .spectrum-stage:focus-within .spectrum-hover-rail {
          opacity:1; pointer-events:auto; transform:translateX(0);
        }
        .spectrum-gain-box {
          width:100%; display:flex; flex-direction:column; align-items:center; gap:.5rem; padding:.55rem .45rem;
          border-radius:999px; background:rgba(23,32,51,.78); color:#fff; box-shadow:0 12px 24px rgba(12,31,61,.22);
        }
        .spectrum-gain-btn {
          width:100%; padding:.42rem .25rem; border-radius:999px; background:rgba(255,255,255,.14); color:#fff;
        }
        .spectrum-gain-btn:hover { background:rgba(255,255,255,.22); transform:none; }
        .spectrum-gain-readout { font-size:.78rem; line-height:1.1; }
        .spectrum-gain-meter {
          position:relative; flex:1; width:12px; min-height:120px; border-radius:999px; background:rgba(255,255,255,.14);
          overflow:hidden;
        }
        .spectrum-gain-fill {
          position:absolute; left:0; right:0; bottom:0; min-height:14px;
          background:linear-gradient(180deg,#c9ddff 0%,#87b4ff 40%,#2157d5 100%);
        }
        .spectrum-gain-hint { font-size:.68rem; line-height:1.2; text-align:center; opacity:.88; }
        .spectrum-toolbar { display:flex; flex-wrap:wrap; gap:.6rem; }
        .spectrum-inline-note { display:flex; justify-content:space-between; gap:.8rem; flex-wrap:wrap; }
        .spectrum-context-menu {
          position:fixed; z-index:1000; min-width:220px; padding:.35rem; border:1px solid var(--border);
          border-radius:8px; background:#fff; box-shadow:0 18px 38px rgba(12,31,61,.18); display:none;
        }
        .spectrum-context-menu button {
          width:100%; display:block; text-align:left; padding:.48rem .6rem; border-radius:6px; background:transparent;
          color:var(--text); font-weight:600;
        }
        .spectrum-context-menu button:hover { background:#eef3ff; transform:none; }
        .spectrum-context-menu .context-divider { height:1px; background:var(--border); margin:.3rem .2rem; }
        .comparison-chip-row { display:flex; flex-wrap:wrap; gap:.5rem; margin-top:.7rem; }
        .timeline-list { display:grid; gap:.65rem; }
        .timeline-item { border:1px solid var(--border); border-radius:8px; padding:.7rem; background:#fff; }
        .timeline-meta { color:var(--muted); font-size:.82rem; margin-top:.25rem; }
        @media (max-width: 1120px) {
          .auth-card, .layout, .grid2 { grid-template-columns:1fr; }
        }
        @media (max-width: 760px) {
          body { font-size:15px; }
          .page { padding:.55rem; }
          .card { padding:.85rem; border-radius:8px; }
          .layout { display:block; }
          .sidebar { position:sticky; top:.35rem; z-index:10; margin-bottom:.8rem; }
          .sidebar .card { padding:.65rem; }
          .nav-list { display:flex; gap:.45rem; overflow-x:auto; padding-bottom:.25rem; -webkit-overflow-scrolling:touch; }
          .nav-btn { min-width:max-content; white-space:nowrap; padding:.65rem .85rem; }
          .main { display:block; }
          .main > .card { margin-bottom:.8rem; }
          .row { flex-direction:column; align-items:stretch; }
          .row button, .row a { width:100%; justify-content:center; }
          button, input, select, textarea { font-size:16px; }
          textarea { min-height:112px; }
          table { display:block; overflow-x:auto; white-space:nowrap; -webkit-overflow-scrolling:touch; }
          th, td { padding:.55rem .5rem; }
          .summary-grid { grid-template-columns:1fr 1fr; gap:.5rem; }
          .metric { padding:.65rem; }
          .metric .value { font-size:1rem; }
          .spectrum-toolbar { display:grid; grid-template-columns:1fr 1fr; }
          .spectrum-inline-note { display:block; }
          .json-box { max-height:300px; }
        }
        @media (max-width: 460px) {
          .summary-grid { grid-template-columns:1fr; }
          .hero h1 { font-size:1.6rem; }
          .card h2, .card h3 { font-size:1.1rem; }
          .status-badge { font-size:.78rem; padding:.25rem .5rem; }
          .spectrum-toolbar { grid-template-columns:1fr; }
        }
      </style>
      <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    </head>
    <body>
      <div class="page">
        <div id="authScreen" class="auth-shell">
          <div class="auth-card">
            <section class="hero">
              <h1>NMRCheck</h1>
              <p>
                Evidence-first NMR review workflow with human signoff, audit trails, solvent-aware interpretation,
                and measurable time savings for chemistry teams.
              </p>
              <div class="hero-links">
                <a href="/docs" target="_blank" rel="noreferrer">API docs</a>
                <a href="/health" target="_blank" rel="noreferrer">Health</a>
              </div>
            </section>

            <section class="card">
              <h2>Sign in</h2>
              <p class="muted small">Log in to access the analysis dashboard, jobs, history, review queue, and admin tools.</p>

              <div class="field">
                <label for="authEmail">Email</label>
                <input id="authEmail" type="email" placeholder="you@example.com" />
              </div>

              <div class="field">
                <label for="authPassword">Password</label>
                <div class="input-wrap">
                  <input id="authPassword" type="password" placeholder="Password" />
                  <button type="button" class="inline-eye" onclick="togglePassword('authPassword', this)" aria-label="Show password">👁</button>
                </div>
              </div>

              <div class="row">
                <button type="button" class="primary" onclick="login()">Log in</button>
                <button type="button" class="secondary" onclick="registerUser()">Register</button>
              </div>

              <div class="panel" style="margin-top:.9rem;">
                <div class="field">
                  <label for="resetEmail">Password reset email</label>
                  <input id="resetEmail" type="email" placeholder="you@example.com" />
                </div>
                <button type="button" class="secondary" onclick="requestPasswordReset()">Request reset token</button>

                <div class="field" style="margin-top:.8rem;">
                  <label for="resetToken">Reset token</label>
                  <input id="resetToken" type="text" placeholder="Paste reset token" />
                </div>
                <div class="field">
                  <label for="resetPassword">New password</label>
                  <div class="input-wrap">
                    <input id="resetPassword" type="password" placeholder="New password" />
                    <button type="button" class="inline-eye" onclick="togglePassword('resetPassword', this)" aria-label="Show password">👁</button>
                  </div>
                </div>
                <button type="button" class="primary" onclick="resetPassword()">Reset password</button>
              </div>

              <div id="authMessage" class="panel small" style="margin-top:.9rem;">No session yet.</div>
            </section>
          </div>
        </div>

        <div id="appShell" class="hidden">
          <section class="hero">
            <div style="display:flex; justify-content:space-between; gap:1rem; align-items:flex-start; flex-wrap:wrap;">
              <div>
                <h1>NMRCheck Dashboard</h1>
                <p>Structured analysis, reviewer oversight, auditability, and value metrics in one place.</p>
                <div class="hero-links">
                  <a href="/docs" target="_blank" rel="noreferrer">API docs</a>
                  <a href="/health" target="_blank" rel="noreferrer">Health</a>
                  <a href="/metrics/summary" target="_blank" rel="noreferrer">Metrics JSON</a>
                  <a href="/audit" target="_blank" rel="noreferrer">Audit JSON</a>
                </div>
              </div>
              <div class="card" style="min-width:280px;">
                <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                  <div>
                    <div class="muted small">Session</div>
                    <div id="sessionIdentity" style="font-weight:700;">Not loaded</div>
                  </div>
                  <span id="roleBadge" class="status-badge warn">Viewer</span>
                </div>
                <div class="token-box" id="tokenBox" style="margin-top:.75rem;">No token yet.</div>
                <div class="row" style="margin-top:.75rem;">
                  <button class="ghost" onclick="copyToken()">Copy token</button>
                  <button class="ghost" onclick="whoAmI()">Refresh me</button>
                  <button class="danger" onclick="logout()">Log out</button>
                </div>
              </div>
            </div>
          </section>

          <div class="layout">
            <aside class="sidebar">
              <section class="card">
                <h2>Navigation</h2>
                <div class="nav-list">
                  <button id="nav-dashboard" class="nav-btn active" onclick="showSection('dashboard')">Dashboard</button>
                  <button id="nav-analyze" class="nav-btn" onclick="showSection('analyze')">Analyze</button>
                  <button id="nav-workspaces" class="nav-btn" onclick="showSection('workspaces')">Workspaces</button>
                  <button id="nav-jobs" class="nav-btn" onclick="showSection('jobs')">Jobs</button>
                  <button id="nav-history" class="nav-btn" onclick="showSection('history')">History</button>
                  <button id="nav-reviews" class="nav-btn hidden" onclick="showSection('reviews')">Review Queue</button>
                  <button id="nav-admin" class="nav-btn hidden" onclick="showSection('admin')">Admin</button>
                </div>
              </section>

              <section class="card">
                <h2>Email verification</h2>
                <p class="muted small">Request and apply verification tokens after login.</p>
                <button class="secondary" onclick="requestVerification()">Request verification token</button>
                <div class="field" style="margin-top:.8rem;">
                  <label for="verifyToken">Verification token or link</label>
                  <input id="verifyToken" type="text" placeholder="Paste a raw token or full verification link" />
                </div>
                <div class="panel small" id="verificationTokenBox" style="margin-top:.7rem;">No verification token requested yet.</div>
                <div class="row" style="margin-top:.7rem;">
                  <button class="primary" onclick="verifyEmail()">Verify email</button>
                  <button class="ghost" onclick="copyVerificationToken()">Copy verification token</button>
                  <button class="ghost" onclick="loadOutbox()">View outbox</button>
                </div>
              </section>
            </aside>

            <main class="main">
              <section id="section-dashboard" class="section active">
                <div class="card">
                  <h2>Value dashboard</h2>
                  <div class="summary-grid" id="metricsGrid">
                    <div class="metric"><div class="label">Analyses</div><div class="value">—</div></div>
                    <div class="metric"><div class="label">Jobs</div><div class="value">—</div></div>
                    <div class="metric"><div class="label">Hours saved</div><div class="value">—</div></div>
                    <div class="metric"><div class="label">Validation fails caught</div><div class="value">—</div></div>
                  </div>
                  <div class="panel" id="dashboardNotes" style="margin-top:.85rem;">Load metrics to see automation, time saved, and reviewer activity.</div>
                  <div class="row" style="margin-top:.8rem;">
                    <button class="secondary" onclick="loadMetrics()">Refresh metrics</button>
                    <button class="ghost" onclick="loadAudit()">Load audit log</button>
                  </div>
                  <div id="auditPreview" style="margin-top:.8rem;"></div>
                </div>
              </section>

              <section id="section-analyze" class="section">
                <div class="card">
                  <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                    <div>
                      <h2>Validate and analyze</h2>
                      <p class="muted small">Use realistic ¹H NMR text directly, including δ, ranges, multiplicities, and coupling constants.</p>
                    </div>
                    <span id="validationBadge" class="status-badge warn">Not validated</span>
                  </div>

                  <div class="grid2">
                    <div class="field">
                      <label for="sampleId">Sample ID</label>
                      <input id="sampleId" data-clear-on-focus="true" value="cmpd-001" />
                    </div>
                    <div class="field">
                      <label for="jobName">Job name</label>
                      <input id="jobName" data-clear-on-focus="true" value="week9-demo" />
                    </div>
                  </div>

                  <div class="grid2">
                    <div class="field">
                      <label for="solvent">Solvent</label>
                      <select id="solvent">__SOLVENT_OPTIONS__</select>
                    </div>
                    <div class="field">
                      <label for="queueName">Queue action</label>
                      <select id="queueName">
                        <option value="analyze">Direct analysis</option>
                        <option value="submit">Async job submit</option>
                      </select>
                    </div>
                  </div>

                  <div class="field">
                    <label for="analysisInputMethod">Input method</label>
                    <select id="analysisInputMethod" onchange="setAnalysisInputMethod(this.value)">
                      <option value="paste">Paste processed ¹H NMR text</option>
                      <option value="processed">Upload processed spectrum (.csv, .tsv, .txt, .jcamp, .jdx, .dx, .xy, .asc, .dat)</option>
                      <option value="fid">Upload raw FID archive - Bruker or Varian/Agilent 1D .zip/.tar.gz/.tgz</option>
                    </select>
                    <div id="analysisInputMethodHint" class="small muted" style="margin-top:.5rem;">Paste parseable ¹H NMR text with shifts, multiplicities, and integrations.</div>
                  </div>

                  <div class="field">
                    <label for="smiles">SMILES</label>
                    <input id="smiles" value="__DEFAULT_SMILES__" required placeholder="Enter a valid SMILES string" />
                  </div>

                  <div id="manualNmrInputPanel" class="field">
                    <label for="nmrText">¹H NMR text</label>
                    <textarea id="nmrText" required placeholder="Enter parseable ¹H NMR text with shifts, multiplicities, and integrations">__DEFAULT_NMR__</textarea>
                  </div>

                  <div class="row">
                    <button class="secondary" onclick="validateInput()">Validate</button>
                    <button class="secondary" onclick="analyzeProtonEvidence()" title="Score the pasted ¹H NMR text peak-by-peak against the SMILES structure, solvent, water, and impurity windows.">¹H evidence</button>
                    <button id="analyzeBtn" class="primary" onclick="analyzeInput()" disabled>Analyze</button>
                    <button class="ghost" onclick="submitJob()">Submit async job</button>
                    <button class="ghost" onclick="clearAnalysisWorkspace()">Clear analysis</button>
                    <button class="ghost" onclick="clearValidationState()">Clear validation state</button>
                  </div>

                  <div id="validationSummary" class="panel" style="margin-top:.9rem;">
                    <strong>Validation summary</strong>
                    <p class="muted small">Run validation before analysis.</p>
                  </div>

                  <div id="protonEvidenceBox" class="panel" style="margin-top:.9rem;">
                    <strong>¹H evidence</strong>
                    <p class="muted small">Run ¹H evidence scoring to classify peaks, solvent/water hits, and proton-count consistency.</p>
                  </div>

                  <div id="rawFidPanel" class="panel hidden" style="margin-bottom:.9rem;">
	                    <h3 style="margin:0 0 .45rem;">Raw FID Upload</h3>
	                    <div class="panel" style="background:var(--warn-bg); border-color:#f2d082; margin-bottom:.85rem;">
	                      <strong style="color:var(--warn);">Immutable raw FID workflow</strong>
	                      <div class="small muted" style="margin-top:.35rem;">Original raw FID archive is never modified. Processing creates derived evidence only. Display gain does not alter evidence data.</div>
	                    </div>
	                    <div class="grid2">
	                      <div class="field">
	                        <label for="fidFile">Step 1: Upload raw vendor archive (.zip, .tar.gz, .tgz)</label>
	                        <input id="fidFile" type="file" accept=".zip,.tar.gz,.tgz,application/zip,application/x-zip-compressed,application/gzip" onchange="resetRawFidVaultSelection()" />
	                        <button class="secondary" style="margin-top:.55rem;" onclick="uploadRawFidArchive()" title="Hash, inspect, and store this archive as immutable raw source data.">Upload & Lock Raw Data</button>
	                      </div>
	                      <div class="field">
	                        <label for="fidProcessingPreset">Step 2: Phase/default processing recipe</label>
	                        <select id="fidProcessingPreset" onchange="applyFidProcessingPreset(this.value)">
                          <option value="baseline_preserve">Baseline preserve</option>
                          <option value="balanced" selected>Balanced</option>
                          <option value="sensitive_weak_peaks">Sensitive weak peaks</option>
                          <option value="higher_resolution">Higher resolution</option>
                          <option value="custom">Custom</option>
                        </select>
	                        <div id="fidPresetDescription" class="small muted" style="margin-top:.35rem;">Conservative default for routine Bruker or Varian/Agilent 1D ¹H FID review.</div>
	                      </div>
	                    </div>
	                    <div id="fidVaultStatus" class="panel small" style="margin:.8rem 0;">No immutable raw FID archive uploaded yet.</div>
                    <div class="grid2">
                      <div class="field">
                        <label for="fidNucleus">Nucleus</label>
                        <select id="fidNucleus">
                          <option value="1H">¹H</option>
                        </select>
                      </div>
                    </div>
                    <div class="grid2">
                      <div class="field">
                        <label for="fidSolvent">Solvent</label>
                        <select id="fidSolvent">__SOLVENT_OPTIONS__</select>
                      </div>
                      <div class="field">
                        <label for="fidReferencePPM">Reference ppm</label>
                        <input id="fidReferencePPM" placeholder="0.00" />
                      </div>
                    </div>
                    <div class="grid2">
	                      <div class="field">
	                        <label for="fidZeroFillFactor">Zero fill factor</label>
	                        <input id="fidZeroFillFactor" data-clear-on-focus="true" value="2" />
	                      </div>
	                      <div class="field">
	                        <label for="fidLineBroadeningHz">Line broadening (Hz)</label>
	                        <input id="fidLineBroadeningHz" data-clear-on-focus="true" value="0.3" />
	                      </div>
	                      <div class="field">
	                        <label for="fidApodizationMode">Apodization</label>
	                        <select id="fidApodizationMode" title="Applies the selected window function to an in-memory working copy only. The raw FID archive is never modified.">
	                          <option value="exponential" selected>Exponential</option>
	                          <option value="none">None</option>
	                        </select>
	                      </div>
	                    </div>
                    <div class="grid2">
                      <div class="field">
                        <label for="fidPeakSensitivity">Peak sensitivity</label>
                        <input id="fidPeakSensitivity" placeholder="0.12" />
                      </div>
                      <div class="field">
                        <label>Reference-assisted matching</label>
                        <div class="panel small">Uses the current SMILES and current ¹H NMR text as the comparison target when available.</div>
                      </div>
                    </div>
                    <div class="grid2">
                      <label class="checkbox-row" for="fidApplyGroupDelay">
                        <input id="fidApplyGroupDelay" type="checkbox" checked />
                        <span><strong>Group delay correction</strong></span>
                      </label>
                      <div class="field">
                        <label for="fidPhaseMode">Phase correction</label>
                        <select id="fidPhaseMode">
                          <option value="auto" selected>Auto phase correction</option>
                          <option value="auto_acme">Auto ACME</option>
                          <option value="auto_peak_minima">Auto peak-minima</option>
                          <option value="manual">Manual p0/p1</option>
                          <option value="none">None</option>
                        </select>
                      </div>
	                      <div class="field">
	                        <label for="fidBaselineCorrection">Step 2: Baseline/default processing recipe</label>
                        <select id="fidBaselineCorrection">
                          <option value="bernstein" selected>Bernstein polynomial fit</option>
                          <option value="preserve">Preserve / none</option>
                          <option value="median">Median</option>
                          <option value="percentile">5th percentile</option>
                        </select>
                      </div>
                      <label class="checkbox-row" for="fidMaskSolventRegions">
                        <input id="fidMaskSolventRegions" type="checkbox" checked />
                        <span><strong>Mask solvent/water regions</strong></span>
                      </label>
                    </div>
                    <div class="grid2">
                      <div class="field">
                        <label for="fidPhaseP0">Manual p0 phase (degrees)</label>
                        <input id="fidPhaseP0" value="0.0" />
                      </div>
                      <div class="field">
                        <label for="fidPhaseP1">Manual p1 phase (degrees)</label>
                        <input id="fidPhaseP1" value="0.0" />
                      </div>
                      <div class="field">
                        <label for="fidBaselineOrder">Baseline polynomial order</label>
                        <input id="fidBaselineOrder" value="3" min="1" max="8" />
                      </div>
                      <div class="field">
                        <label for="fidDisplayMode">Display mode</label>
                        <select id="fidDisplayMode">
                          <option value="real" selected>Real spectrum - original intensity</option>
                          <option value="magnifier">Real spectrum + weak-peak inset</option>
                        </select>
                      </div>
                      <div class="panel small">
                        <strong>Processing order</strong>
                        <div class="muted" style="margin-top:.25rem;">Phase correction is applied before baseline correction. Baseline correction uses Bernstein polynomial fit order 3 by default. Display gain does not alter evidence data.</div>
                      </div>
                    </div>
	                    <div class="row" style="margin-top:.8rem;">
	                      <button class="secondary" onclick="previewRawFid()" title="Preview from the immutable raw archive without modifying the raw upload.">Step 2: Preview from immutable raw archive</button>
	                      <button class="ghost" onclick="useRawFidPeaks()" title="Copy the reviewed FID-derived peak list into the main ¹H NMR text field.">Use extracted peaks as text</button>
	                      <button class="primary" onclick="analyzeRawFid()" title="Process the immutable archive as a new run, storing recipe and derived results.">Step 3: Process as new run</button>
	                      <button class="ghost" onclick="exportRawFidPackage()" title="Export raw archive provenance, recipe, evidence, peak CSV, audit trail, and manifest hashes.">Step 4: Export analysis package</button>
	                      <button class="ghost" onclick="clearAnalysisWorkspace()" title="Clear current analysis previews, files, and result panels.">Clear analysis</button>
	                    </div>
	                    <div id="fidExportStatus" class="small muted" style="margin-top:.55rem;">Export package includes manifest.json with SHA-256 hashes for the original archive and derived evidence files.</div>
                    <div class="panel" style="margin-top:.85rem;">
                      <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                        <strong>FID processing run history</strong>
                        <span id="fidRunSelectionBadge" class="status-badge warn">0 selected</span>
                      </div>
                      <div class="row" style="margin-top:.7rem;">
                        <button class="secondary" onclick="loadFidRuns()" title="Reload saved FID runs after processing Balanced, Sensitive weak peaks, or Higher resolution.">Refresh FID runs</button>
                        <button class="ghost" onclick="compareSelectedFidRuns()" title="Compare two or more selected runs by QA score, preset, peaks, and review status.">Compare selected</button>
                        <button class="ghost" onclick="openBestFidRun()" title="Open the highest-scoring selected run, or the highest-scoring recent run if none are selected.">Open best run</button>
                      </div>
                      <div id="fidRunHistoryBox" style="margin-top:.85rem;">No FID runs loaded yet.</div>
                      <div id="fidRunCompareBox" style="margin-top:.85rem;"></div>
                    </div>
                    <div id="fidPreviewBox" class="panel" style="margin-top:.8rem;">No raw FID preview yet.</div>
                  </div>

                  <div id="carbon13Panel" class="panel" style="margin-bottom:.9rem;">
                    <h3 style="margin:0 0 .45rem;">¹³C NMR Validation Beta</h3>
                    <div class="field">
                      <label for="carbon13InputMethod">¹³C input method</label>
                      <select id="carbon13InputMethod" onchange="setCarbon13InputMethod(this.value)">
                        <option value="text">Paste processed ¹³C NMR text</option>
                        <option value="processed">Upload processed ¹³C spectrum (.csv, .tsv, .jdx, .dx, .json)</option>
                        <option value="fid">Upload raw ¹³C FID beta - Bruker or Varian/Agilent 1D dataset .zip/.tar.gz</option>
                      </select>
                      <div id="carbon13InputMethodHint" class="small muted" style="margin-top:.5rem;">Paste parseable ¹³C NMR text with discrete carbon shifts.</div>
                    </div>

                    <div id="carbon13TextPanel" class="field">
                      <label for="carbon13Text">¹³C NMR text</label>
                      <textarea id="carbon13Text" rows="4" placeholder="¹³C NMR (101 MHz, CDCl3) δ 58.3, 18.2.">¹³C NMR (101 MHz, CDCl3) δ 58.3, 18.2.</textarea>
                      <div class="row" style="margin-top:.65rem;">
                        <button class="secondary" onclick="validateCarbon13Text()" title="Parse pasted ¹³C text and flag solvent or impurity-reference shifts.">Validate ¹³C text</button>
                        <button class="primary" onclick="analyzeCarbon13Text()" title="Compare ¹³C shifts with the SMILES-derived carbon count and expected regions.">Analyze ¹³C text</button>
                      </div>
                    </div>

                    <div id="carbon13ProcessedPanel" class="panel hidden" style="margin-top:.75rem;">
                      <div class="grid2">
                        <div class="field">
                          <label for="carbon13SpectrumFile">Processed ¹³C spectrum or peak table</label>
                          <input id="carbon13SpectrumFile" type="file" accept=".csv,.tsv,.txt,.json,.jcamp,.jdx,.dx,.xy,.asc,.dat" />
                        </div>
                        <div class="field">
                          <label for="carbon13PeakSensitivity">¹³C peak sensitivity</label>
                          <input id="carbon13PeakSensitivity" placeholder="0.12" />
                        </div>
                      <div class="field">
                        <label for="carbon13ProcessedDisplayMode">Display mode</label>
                        <select id="carbon13ProcessedDisplayMode">
                          <option value="real" selected>Real spectrum - original intensity</option>
                          <option value="magnifier">Real spectrum + weak-peak inset</option>
                        </select>
                      </div>
                      <div class="panel small">
                        <strong>Real ¹³C spectrum view</strong>
                        <div class="muted" style="margin-top:.25rem;">Uploaded ¹³C intensities are shown unchanged; weak-peak tools are viewer-only.</div>
                      </div>
                      <details class="panel small">
                        <summary><strong>Processed-file correction</strong></summary>
                        <div class="grid2" style="margin-top:.65rem;">
                          <div class="field">
                            <label for="carbon13ProcessedBaselineCorrection">Apply processed-file baseline correction</label>
                            <select id="carbon13ProcessedBaselineCorrection">
                              <option value="bernstein" selected>Bernstein polynomial fit</option>
                              <option value="none">Off / preserve uploaded trace</option>
                            </select>
                          </div>
                          <div class="field">
                            <label for="carbon13ProcessedBaselineOrder">Baseline polynomial order</label>
                            <input id="carbon13ProcessedBaselineOrder" value="3" min="1" max="8" />
                          </div>
                        </div>
                        <div class="muted" style="margin-top:.35rem;">For already processed ¹³C spectra, correction is optional and explicit.</div>
                      </details>
                    </div>
                      <div class="row">
                        <button class="secondary" onclick="previewCarbon13Spectrum()" title="Preview inferred ¹³C peaks from a processed spectrum or peak table.">Preview ¹³C spectrum</button>
                        <button class="primary" onclick="analyzeCarbon13Spectrum()" title="Analyze processed ¹³C spectrum peaks against the current SMILES.">Analyze ¹³C spectrum</button>
                      </div>
                    </div>

                    <div id="carbon13FidPanel" class="panel hidden" style="margin-top:.75rem;">
                      <div class="grid2">
                        <div class="field">
                          <label for="carbon13FidFile">Raw ¹³C FID dataset archive (.zip, .tar.gz)</label>
                          <input id="carbon13FidFile" type="file" accept=".zip,.tar.gz,.tgz,application/zip,application/x-zip-compressed,application/gzip" />
                        </div>
                        <div class="field">
                          <label for="carbon13FidReferencePPM">¹³C reference ppm</label>
                          <input id="carbon13FidReferencePPM" value="77.0" />
                        </div>
                      </div>
                      <div class="grid2">
                        <div class="field">
                          <label for="carbon13FidProcessingPreset">¹³C FID processing preset</label>
                          <select id="carbon13FidProcessingPreset" onchange="applyCarbon13FidProcessingPreset(this.value)">
                            <option value="baseline_preserve">Baseline preserve</option>
                            <option value="balanced" selected>Balanced</option>
                            <option value="sensitive_weak_peaks">Sensitive weak peaks</option>
                            <option value="higher_resolution">Higher resolution</option>
                            <option value="custom">Custom</option>
                          </select>
                        </div>
                      <div class="field">
                        <label for="carbon13FidPeakSensitivity">¹³C FID peak sensitivity</label>
                        <input id="carbon13FidPeakSensitivity" placeholder="0.12" />
                      </div>
                      <div class="panel small">
                        <strong>Real raw-FID spectrum view</strong>
                        <div class="muted" style="margin-top:.25rem;">The main trace uses raw FID-derived evidence intensities. Viewer controls adjust only the axes.</div>
                      </div>
                    </div>
                      <div class="grid2">
	                        <div class="field">
	                          <label for="carbon13FidZeroFillFactor">Zero fill factor</label>
	                          <input id="carbon13FidZeroFillFactor" value="2" />
	                        </div>
	                        <div class="field">
	                          <label for="carbon13FidLineBroadeningHz">Line broadening (Hz)</label>
	                          <input id="carbon13FidLineBroadeningHz" value="0.3" />
	                        </div>
	                        <div class="field">
	                          <label for="carbon13FidApodizationMode">Apodization</label>
	                          <select id="carbon13FidApodizationMode" title="Optional ¹³C apodization is applied to a copied working array only, never to the raw archive.">
	                            <option value="exponential" selected>Exponential</option>
	                            <option value="none">None</option>
	                          </select>
	                        </div>
	                      </div>
                      <div class="grid2">
                        <label class="checkbox-row" for="carbon13FidApplyGroupDelay">
                          <input id="carbon13FidApplyGroupDelay" type="checkbox" checked />
                          <span><strong>Group delay correction</strong></span>
                        </label>
                        <div class="field">
                          <label for="carbon13FidPhaseMode">Phase correction</label>
                          <select id="carbon13FidPhaseMode">
                            <option value="auto" selected>Auto phase correction</option>
                            <option value="auto_acme">Auto ACME</option>
                            <option value="auto_peak_minima">Auto peak-minima</option>
                            <option value="manual">Manual p0/p1</option>
                            <option value="none">None</option>
                          </select>
                        </div>
                        <div class="field">
                          <label for="carbon13FidBaselineCorrection">Baseline correction</label>
                          <select id="carbon13FidBaselineCorrection">
                            <option value="bernstein" selected>Bernstein polynomial fit</option>
                            <option value="preserve">Preserve / none</option>
                            <option value="median">Median</option>
                            <option value="percentile">5th percentile</option>
                          </select>
                        </div>
                        <label class="checkbox-row" for="carbon13FidMaskSolventRegions">
                          <input id="carbon13FidMaskSolventRegions" type="checkbox" checked />
                          <span><strong>Mask solvent regions</strong></span>
                        </label>
                      </div>
                      <div class="grid2">
                        <div class="field">
                          <label for="carbon13FidPhaseP0">Manual p0 phase (degrees)</label>
                          <input id="carbon13FidPhaseP0" value="0.0" />
                        </div>
                        <div class="field">
                          <label for="carbon13FidPhaseP1">Manual p1 phase (degrees)</label>
                          <input id="carbon13FidPhaseP1" value="0.0" />
                        </div>
                        <div class="field">
                          <label for="carbon13FidBaselineOrder">Baseline polynomial order</label>
                          <input id="carbon13FidBaselineOrder" value="3" min="1" max="8" />
                        </div>
                        <div class="field">
                          <label for="carbon13FidDisplayMode">Display mode</label>
                          <select id="carbon13FidDisplayMode">
                            <option value="real" selected>Real spectrum - original intensity</option>
                            <option value="magnifier">Real spectrum + weak-peak inset</option>
                          </select>
                        </div>
                        <div class="panel small">
                          <strong>Processing order</strong>
                          <div class="muted" style="margin-top:.25rem;">Phase correction is applied before baseline correction. Baseline correction uses Bernstein polynomial fit order 3 by default. Display gain does not alter evidence data.</div>
                        </div>
                      </div>
                      <div class="row" style="margin-top:.75rem;">
                        <button class="secondary" onclick="previewCarbon13Fid()" title="Process the selected raw ¹³C FID archive without modifying the raw upload; current SMILES/¹H context is used when available.">Preview raw ¹³C FID</button>
                        <button class="primary" onclick="analyzeCarbon13Fid()" title="Analyze raw ¹³C FID-derived peaks against the current SMILES and linked ¹H NMR context.">Analyze raw ¹³C FID</button>
                      </div>
                    </div>

                    <div id="carbon13Box" class="panel" style="margin-top:.8rem;">No ¹³C result yet.</div>
                  </div>

                  <div id="deptApt2dStudio" class="panel" style="margin-bottom:.9rem;">
                    <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; flex-wrap:wrap;">
                      <div>
                        <h3 style="margin:0 0 .35rem;">DEPT/APT + 2D NMR Evidence Studio</h3>
                        <p class="muted small" style="margin:.15rem 0 .7rem; max-width:76ch;">DEPT/APT and 2D NMR evidence are supportive connectivity evidence and require human review.</p>
                        <p class="muted small" style="margin:.15rem 0 .7rem; max-width:76ch;">HSQC/HMQC can use DEPT/APT to flag support or conflict. HMBC uses DEPT/APT as contextual evidence only.</p>
                      </div>
                      <span class="status-badge warn">Human review required</span>
                    </div>
                    <div class="summary-grid" style="margin:.7rem 0;">
                      <div class="metric"><div class="label">DEPT/APT</div><div class="value">Carbon type</div><div class="small muted">DEPT-90 / DEPT-135 / APT</div></div>
                      <div class="metric"><div class="label">COSY</div><div class="value">1H-1H</div><div class="small muted">Scalar connectivity</div></div>
                      <div class="metric"><div class="label">HSQC/HMQC</div><div class="value">Direct H-C</div><div class="small muted">Attachment evidence</div></div>
                      <div class="metric"><div class="label">HMBC</div><div class="value">Long range</div><div class="small muted">Contextual connectivity</div></div>
                    </div>

                    <div class="grid2">
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">A. DEPT / APT carbon-type evidence</h4>
                        <div class="field">
                          <label for="deptAptFile">DEPT/APT peak table CSV / TSV / TXT / JSON</label>
                          <input id="deptAptFile" type="file" accept=".csv,.tsv,.txt,.json,.xy,.asc,.dat" />
                        </div>
                        <div class="grid2">
                          <div class="field">
                            <label for="deptAptExperiment">Experiment</label>
                            <select id="deptAptExperiment">
                              <option value="">Auto-detect</option>
                              <option value="DEPT90">DEPT-90</option>
                              <option value="DEPT135">DEPT-135</option>
                              <option value="APT">APT</option>
                            </select>
                          </div>
                          <div class="field">
                            <label for="deptAptPositive">APT positive convention</label>
                            <select id="deptAptPositive">
                              <option value="CH_CH3" selected>positive = CH / CH3</option>
                              <option value="CH2_C">positive = CH2 / quaternary C</option>
                            </select>
                          </div>
                        </div>
                        <div class="row">
                          <button class="secondary" onclick="previewDeptApt()">Preview DEPT/APT</button>
                          <button class="primary" onclick="analyzeDeptApt()">Analyze DEPT/APT</button>
                        </div>
                        <div id="deptAptBox" class="panel" style="margin-top:.8rem;">No DEPT/APT evidence yet.</div>
                      </div>

                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">B. 2D correlation evidence</h4>
                        <div class="field">
                          <label for="nmr2dFile">2D peak table CSV / TSV / TXT / JSON</label>
                          <input id="nmr2dFile" type="file" accept=".csv,.tsv,.txt,.json,.jcamp,.jdx,.dx,.xy,.asc,.dat" />
                        </div>
                        <div class="grid2">
                          <div class="field">
                            <label for="nmr2dExperiment">Experiment type</label>
                            <select id="nmr2dExperiment">
                              <option value="">Auto-detect</option>
                              <option value="COSY">COSY</option>
                              <option value="HSQC">HSQC</option>
                              <option value="HMQC">HMQC</option>
                              <option value="HMBC">HMBC</option>
                            </select>
                          </div>
                          <div class="panel small">
                            <strong>Read-only context</strong>
                            <div class="muted" style="margin-top:.25rem;">Uses current ¹H text, ¹³C text, SMILES, solvent, and sample ID without mutating those inputs.</div>
                          </div>
                        </div>
                        <div class="row">
                          <button class="secondary" onclick="previewNMR2D()">Preview 2D</button>
                          <button class="primary" onclick="analyzeNMR2D()">Analyze 2D + DEPT/APT</button>
                        </div>
                        <div id="nmr2dBox" class="panel" style="margin-top:.8rem;">No 2D NMR evidence yet.</div>
                      </div>
                    </div>
                  </div>

                  <div id="candidateComparisonPanel" class="panel" style="margin-bottom:.9rem;">
                    <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; flex-wrap:wrap;">
                      <div>
                        <h3 style="margin:0 0 .35rem;">Candidate Comparison Engine</h3>
                        <p class="muted small" style="margin:.15rem 0 .7rem; max-width:76ch;">Rank proposed products, regioisomers, starting materials, and impurities against the same ¹H, ¹³C, DEPT/APT, and 2D NMR evidence. This is evidence ranking, not final structure confirmation.</p>
                      </div>
                      <span class="status-badge warn">Human review required</span>
                    </div>
                    <div class="grid2">
                      <div class="field">
                        <label for="candidateList">Candidate structures</label>
                        <textarea id="candidateList" rows="6" placeholder="Proposed product | CCO | proposed&#10;Starting material | CO | starting material&#10;Side product | CCCO | possible impurity"></textarea>
                        <div class="small muted">Use one candidate per line: <code>name | SMILES | role</code>. Current ¹H and ¹³C text are read-only evidence; selected DEPT/APT and 2D files are included when present.</div>
                      </div>
                      <div class="panel" style="margin:0;">
                        <strong>Evidence layers used</strong>
                        <ul class="small muted" style="margin:.5rem 0 0;">
                          <li>¹H text from the main NMR field</li>
                          <li>¹³C text from the carbon section</li>
                          <li>Selected DEPT/APT file, if present</li>
                          <li>Selected 2D peak table, if present</li>
                        </ul>
                        <div class="row" style="margin-top:.8rem;">
                          <button class="primary" onclick="compareCandidates()">Compare candidates</button>
                          <button class="ghost" onclick="clearCandidateComparison()">Clear comparison</button>
                        </div>
                      </div>
                    </div>
                    <div id="candidateComparisonBox" class="panel" style="margin-top:.8rem;">No candidate comparison yet.</div>
                  </div>

                  <div id="spectralSimilarityPanel" class="panel" style="margin-bottom:.9rem;">
                    <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; flex-wrap:wrap;">
                      <div>
                        <h3 style="margin:0 0 .35rem;">Spectral Similarity Scoring</h3>
                        <p class="muted small" style="margin:.15rem 0 .7rem; max-width:76ch;">Compare current observed ¹H and ¹³C text plus optional 2D peak tables against reference, literature, prediction, or previous-run spectra. Similarity is a confidence aid and ranking signal, not final confirmation.</p>
                      </div>
                      <span class="status-badge warn">Human review required</span>
                    </div>
                    <div class="grid2">
                      <div class="panel" style="margin:0;">
                        <strong>Observed spectra</strong>
                        <div class="small muted" style="margin-top:.35rem;">Uses current ¹H text, ¹³C text, and selected 2D file read-only.</div>
                        <div class="summary-grid" style="margin-top:.65rem;">
                          <div class="metric"><div class="label">1H source</div><div class="value">Current text</div></div>
                          <div class="metric"><div class="label">13C source</div><div class="value">Current text</div></div>
                          <div class="metric"><div class="label">2D source</div><div class="value">Current upload</div></div>
                        </div>
                      </div>
                      <div class="panel" style="margin:0;">
                        <strong>Method</strong>
                        <ul class="small muted" style="margin:.5rem 0 0;">
                          <li>¹H: Gaussian vector score plus integration-aware set matching</li>
                          <li>¹³C: chemical-shift-only vector and set matching</li>
                          <li>2D: cross-peak matching; COSY diagonal peaks excluded</li>
                        </ul>
                      </div>
                    </div>
                    <div class="grid2" style="margin-top:.8rem;">
                      <div class="field">
                        <label for="similarityReference1H">Reference ¹H NMR text</label>
                        <textarea id="similarityReference1H" rows="4" placeholder="Paste reference, predicted, literature, or previous-run ¹H NMR text."></textarea>
                      </div>
                      <div class="field">
                        <label for="similarityReference13C">Reference ¹³C NMR text</label>
                        <textarea id="similarityReference13C" rows="4" placeholder="Paste reference, predicted, literature, or previous-run ¹³C NMR text."></textarea>
                      </div>
                    </div>
                    <div class="grid2">
                      <div class="field">
                        <label for="similarityReference2DFile">Reference 2D peak table CSV / TSV / TXT / JSON</label>
                        <input id="similarityReference2DFile" type="file" accept=".csv,.tsv,.txt,.json,.jcamp,.jdx,.dx,.xy,.asc,.dat" />
                        <div class="small muted">Observed 2D file uses the current 2D upload above; reference 2D is optional.</div>
                      </div>
                      <div class="field">
                        <label for="similarity2DExperiment">2D experiment type</label>
                        <select id="similarity2DExperiment">
                          <option value="">Auto-detect</option>
                          <option value="COSY">COSY</option>
                          <option value="HSQC">HSQC</option>
                          <option value="HMQC">HMQC</option>
                          <option value="HMBC">HMBC</option>
                        </select>
                      </div>
                    </div>
                    <div class="row">
                      <button class="primary" onclick="scoreSpectralSimilarity()">Score spectral similarity</button>
                      <button class="ghost" onclick="copyCurrentSpectraToSimilarityReference()">Use current spectra as reference</button>
                      <button class="ghost" onclick="clearSpectralSimilarity()">Clear similarity</button>
                    </div>
                    <div id="spectralSimilarityBox" class="panel" style="margin-top:.8rem;">No spectral similarity score yet.</div>
                  </div>

                  <div id="predictedNMRMatchPanel" class="panel" style="margin-bottom:.9rem;">
                    <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; flex-wrap:wrap;">
                      <div>
                        <h3 style="margin:0 0 .35rem;">Candidate-specific Predicted NMR Matching</h3>
                        <p class="muted small" style="margin:.15rem 0 .7rem; max-width:78ch;">Predict approximate 1H, 13C, and direct HSQC-style C-H correlations for each candidate SMILES, then compare those predicted peaks against the current observed evidence. Predicted matching is ranking evidence and requires human review.</p>
                      </div>
                      <span class="status-badge warn">Human review required</span>
                    </div>
                    <div class="grid2">
                      <div class="field">
                        <label for="predictedCandidateList">Candidate structures for prediction</label>
                        <textarea id="predictedCandidateList" rows="6" placeholder="Proposed product | CCO | proposed&#10;Starting material | CO | starting material&#10;Side product | CCCO | possible impurity"></textarea>
                        <div class="small muted">Use one candidate per line: <code>name | SMILES | role</code>. Current 1H, 13C, and selected 2D upload are read-only evidence inputs.</div>
                      </div>
                      <div class="panel" style="margin:0;">
                        <strong>Predicted evidence layers</strong>
                        <ul class="small muted" style="margin:.5rem 0 0;">
                          <li>1H: observed text compared with candidate-specific predicted 1H shifts</li>
                          <li>13C: observed text compared with candidate-specific predicted 13C shifts</li>
                          <li>2D: selected HSQC/HMQC upload compared with predicted direct C-H cross-peaks</li>
                        </ul>
                        <p class="small muted" style="margin:.7rem 0 0;">The bundled predictor is a transparent heuristic for beta review. Unmatched peaks, uncertainty, and close candidate scores should be inspected manually.</p>
                      </div>
                    </div>
                    <div class="row">
                      <button class="primary" onclick="runPredictedNMRMatch()">Rank by predicted NMR</button>
                      <button class="ghost" onclick="copyCandidateListToPredictedNMR()">Copy candidate list</button>
                      <button class="ghost" onclick="clearPredictedNMRMatch()">Clear predicted match</button>
                    </div>
                    <div id="predictedNMRMatchBox" class="panel" style="margin-top:.8rem;">No candidate-specific predicted NMR match yet.</div>
                  </div>

                  <div id="hrmsPanel" class="panel" style="margin-bottom:.9rem;">
                    <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; flex-wrap:wrap;">
                      <div>
                        <h3 style="margin:0 0 .35rem;">HRMS / Exact-Mass Constraint Layer</h3>
                        <p class="muted small" style="margin:.15rem 0 .7rem; max-width:78ch;">Use high-resolution MS to constrain candidate formulas and structures by exact mass, adduct, ppm error, isotope hints, and DBE/IHD. HRMS exact mass constrains formula/candidate plausibility but does not prove connectivity or stereochemistry.</p>
                      </div>
                      <span class="status-badge warn">Human review required</span>
                    </div>
                    <div class="grid2">
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">Candidate exact-mass match</h4>
                        <div class="grid2">
                          <div class="field">
                            <label for="hrmsObservedMz">Observed m/z</label>
                            <input id="hrmsObservedMz" inputmode="decimal" placeholder="47.04914" value="47.04914" />
                          </div>
                          <div class="field">
                            <label for="hrmsAdduct">Adduct</label>
                            <select id="hrmsAdduct">
                              <option value="[M+H]+" selected>[M+H]+</option>
                              <option value="[M+Na]+">[M+Na]+</option>
                              <option value="[M+K]+">[M+K]+</option>
                              <option value="[M+NH4]+">[M+NH4]+</option>
                              <option value="[M-H]-">[M-H]-</option>
                              <option value="[M+Cl]-">[M+Cl]-</option>
                              <option value="[M+FA-H]-">[M+FA-H]-</option>
                              <option value="[M+Ac-H]-">[M+Ac-H]-</option>
                              <option value="M">M</option>
                            </select>
                          </div>
                        </div>
                        <div class="grid2">
                          <div class="field">
                            <label for="hrmsPpmTolerance">ppm tolerance</label>
                            <input id="hrmsPpmTolerance" inputmode="decimal" value="5" />
                          </div>
                          <div class="field">
                            <label for="hrmsIonMode">Ion mode</label>
                            <select id="hrmsIonMode">
                              <option value="">Auto from adduct</option>
                              <option value="positive">Positive</option>
                              <option value="negative">Negative</option>
                              <option value="neutral">Neutral</option>
                            </select>
                          </div>
                        </div>
                        <div class="grid2">
                          <div class="field">
                            <label for="hrmsMPlus1">Optional M+1 %</label>
                            <input id="hrmsMPlus1" inputmode="decimal" placeholder="optional" />
                          </div>
                          <div class="field">
                            <label for="hrmsMPlus2">Optional M+2 %</label>
                            <input id="hrmsMPlus2" inputmode="decimal" placeholder="optional" />
                          </div>
                        </div>
                        <div class="field">
                          <label for="hrmsCandidateList">Candidate structures</label>
                          <textarea id="hrmsCandidateList" rows="5" placeholder="Proposed product | CCO | proposed&#10;Starting material | CO | starting material&#10;Side product | CCCO | possible impurity"></textarea>
                          <div class="small muted">Use one candidate per line: <code>name | SMILES | role</code>. NMR evidence inputs are not modified by HRMS matching.</div>
                        </div>
                        <div class="row">
                          <button class="primary" onclick="runHRMSCandidateMatch()">Match candidates by HRMS</button>
                          <button class="ghost" onclick="copyCandidateListToHRMS()">Copy candidate list</button>
                          <button class="ghost" onclick="clearHRMSMatch()">Clear HRMS</button>
                        </div>
                      </div>
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">Formula search beta</h4>
                        <p class="muted small">Search bounded CHNOPSClBr formulas from exact mass. Use this as formula triage, not final identification.</p>
                        <div class="grid2">
                          <div class="field">
                            <label for="hrmsMaxC">Max C</label>
                            <input id="hrmsMaxC" inputmode="numeric" value="20" />
                          </div>
                          <div class="field">
                            <label for="hrmsMaxResults">Max results</label>
                            <input id="hrmsMaxResults" inputmode="numeric" value="50" />
                          </div>
                        </div>
                        <div class="row">
                          <button class="secondary" onclick="searchHRMSFormulas()">Search formulas</button>
                        </div>
                        <div id="hrmsFormulaBox" class="panel" style="margin-top:.8rem;">No formula search yet.</div>
                      </div>
                    </div>
                    <div id="hrmsMatchBox" class="panel" style="margin-top:.8rem;">No HRMS candidate match yet.</div>
                    <div class="panel spectrum-inline-note" style="margin-top:.8rem;">
                      <strong>Interpretation note</strong>
                      <div class="small muted">Combine HRMS exact mass with 1H, 13C, DEPT/APT, 2D NMR, prediction matching, and human review. This layer does not perform MS/MS annotation or raw LC-MS vendor parsing.</div>
                    </div>
                  </div>

                  <div id="adductPanel" class="panel" style="margin-bottom:.9rem;">
                    <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; flex-wrap:wrap;">
                      <div>
                        <h3 style="margin:0 0 .35rem;">Adduct + Isotope Pattern Inference</h3>
                        <p class="muted small" style="margin:.15rem 0 .7rem; max-width:78ch;">Infer isotope clusters, charge state, halogen signatures, paired adduct peaks, and likely precursor adducts from processed MS1/HRMS peak tables. This is triage evidence between exact-mass HRMS matching and processed MS/MS annotation.</p>
                      </div>
                      <span class="status-badge warn">Human review required</span>
                    </div>
                    <div class="grid2">
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">Processed MS1 / HRMS peak input</h4>
                        <div class="grid2">
                          <div class="field">
                            <label for="adductTargetMz">Target precursor m/z</label>
                            <input id="adductTargetMz" inputmode="decimal" placeholder="47.04914" value="47.04914" />
                          </div>
                          <div class="field">
                            <label for="adductIonMode">Ion mode</label>
                            <select id="adductIonMode">
                              <option value="positive" selected>Positive</option>
                              <option value="negative">Negative</option>
                              <option value="neutral">Neutral</option>
                            </select>
                          </div>
                        </div>
                        <div class="grid2">
                          <div class="field">
                            <label for="adductMzToleranceDa">m/z tolerance, Da</label>
                            <input id="adductMzToleranceDa" inputmode="decimal" value="0.02" />
                          </div>
                          <div class="field">
                            <label for="adductPpmTolerance">ppm tolerance</label>
                            <input id="adductPpmTolerance" inputmode="decimal" value="10" />
                          </div>
                        </div>
                        <div class="grid2">
                          <div class="field">
                            <label for="adductIsotopeToleranceDa">Isotope spacing tolerance, Da</label>
                            <input id="adductIsotopeToleranceDa" inputmode="decimal" value="0.02" />
                          </div>
                          <div class="field">
                            <label for="adductMaxCharge">Max charge state</label>
                            <input id="adductMaxCharge" inputmode="numeric" value="3" />
                          </div>
                        </div>
                        <div class="grid2">
                          <div class="field">
                            <label for="adductMinRelIntensity">Min relative intensity %</label>
                            <input id="adductMinRelIntensity" inputmode="decimal" value="0.2" />
                          </div>
                          <div class="field">
                            <label for="adductMaxPeaks">Max MS1 peaks</label>
                            <input id="adductMaxPeaks" inputmode="numeric" value="200" />
                          </div>
                        </div>
                        <div class="field">
                          <label for="adductPeakList">Processed MS1/HRMS peak list</label>
                          <textarea id="adductPeakList" rows="7" placeholder="m/z,intensity&#10;47.04914,100&#10;48.05249,2.3&#10;69.03109,24"></textarea>
                          <div class="small muted">Use processed centroid MS1 peak tables only: <code>m/z,intensity</code>. CSV, TSV, and whitespace rows are accepted; use the LC-MS/MS import bridge for mzML/mzXML or source-file imports.</div>
                        </div>
                      </div>
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">Formula/adduct constraints</h4>
                        <p class="muted small">Run bounded formula search under each plausible adduct and compare predicted isotope hints against the observed isotope cluster.</p>
                        <div class="grid2">
                          <div class="field">
                            <label for="adductMaxC">Max C</label>
                            <input id="adductMaxC" inputmode="numeric" value="20" />
                          </div>
                          <div class="field">
                            <label for="adductFormulaPerAdduct">Formula candidates per adduct</label>
                            <input id="adductFormulaPerAdduct" inputmode="numeric" value="5" />
                          </div>
                        </div>
                        <label class="small muted" style="display:flex; gap:.45rem; align-items:center; margin:.5rem 0 .9rem;">
                          <input id="adductFormulaSearch" type="checkbox" checked />
                          Run bounded formula search for candidate adducts
                        </label>
                        <div class="row">
                          <button class="primary" onclick="runAdductInference()">Infer adducts + isotopes</button>
                          <button class="ghost" onclick="copyHRMSToAdductInference()">Copy HRMS m/z</button>
                          <button class="ghost" onclick="applyBestAdductInference()">Use best adduct</button>
                          <button class="ghost" onclick="clearAdductInference()">Clear inference</button>
                        </div>
                      </div>
                    </div>
                    <div id="adductInferenceBox" class="panel" style="margin-top:.8rem;">No adduct/isotope inference yet.</div>
                    <div class="panel spectrum-inline-note" style="margin-top:.8rem;">
                      <strong>Interpretation note</strong>
                      <div class="small muted">Adduct and isotope inference proposes precursor-ion assignments, charge state, isotope signatures, and formula/adduct hypotheses. It does not prove identity; confirm with HRMS exact mass, MS/MS fragments, NMR evidence, and human review.</div>
                    </div>
                  </div>

                  <div id="msmsPanel" class="panel" style="margin-bottom:.9rem;">
                    <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; flex-wrap:wrap;">
                      <div>
                        <h3 style="margin:0 0 .35rem;">Processed MS/MS Annotation Beta</h3>
                        <p class="muted small" style="margin:.15rem 0 .7rem; max-width:78ch;">Annotate processed centroid tandem-MS peak lists with precursor/adduct checks, common neutral losses, simple candidate fragment hypotheses, and transparent evidence. MS/MS fragments and neutral losses support or weaken candidate structures, but do not prove complete connectivity or stereochemistry.</p>
                      </div>
                      <span class="status-badge warn">Human review required</span>
                    </div>
                    <div class="grid2">
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">MS/MS evidence input</h4>
                        <div class="grid2">
                          <div class="field">
                            <label for="msmsPrecursorMz">Precursor m/z</label>
                            <input id="msmsPrecursorMz" inputmode="decimal" placeholder="47.04914" value="47.04914" />
                          </div>
                          <div class="field">
                            <label for="msmsAdduct">Precursor adduct</label>
                            <select id="msmsAdduct">
                              <option value="[M+H]+" selected>[M+H]+</option>
                              <option value="[M+Na]+">[M+Na]+</option>
                              <option value="[M+K]+">[M+K]+</option>
                              <option value="[M+NH4]+">[M+NH4]+</option>
                              <option value="[M-H]-">[M-H]-</option>
                              <option value="[M+Cl]-">[M+Cl]-</option>
                              <option value="[M+FA-H]-">[M+FA-H]-</option>
                              <option value="[M+Ac-H]-">[M+Ac-H]-</option>
                              <option value="M">M</option>
                            </select>
                          </div>
                        </div>
                        <div class="grid2">
                          <div class="field">
                            <label for="msmsToleranceDa">m/z tolerance, Da</label>
                            <input id="msmsToleranceDa" inputmode="decimal" value="0.02" />
                          </div>
                          <div class="field">
                            <label for="msmsPpmTolerance">ppm tolerance</label>
                            <input id="msmsPpmTolerance" inputmode="decimal" value="20" />
                          </div>
                        </div>
                        <div class="grid2">
                          <div class="field">
                            <label for="msmsMinRelIntensity">Min relative intensity %</label>
                            <input id="msmsMinRelIntensity" inputmode="decimal" value="1" />
                          </div>
                          <div class="field">
                            <label for="msmsMaxPeaks">Max peaks</label>
                            <input id="msmsMaxPeaks" inputmode="numeric" value="50" />
                          </div>
                        </div>
                        <div class="field">
                          <label for="msmsPeakList">Processed MS/MS peak list</label>
                          <textarea id="msmsPeakList" rows="7" placeholder="m/z,intensity&#10;47.04914,10&#10;29.03913,100"></textarea>
                          <div class="small muted">Use processed centroid peak tables only: <code>m/z,intensity</code>. CSV, TSV, and whitespace rows are accepted; raw vendor LC-MS/MS files come later.</div>
                        </div>
                      </div>
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">Candidate-aware annotation</h4>
                        <p class="muted small">Candidate structures improve plausibility checks by formula, precursor exact mass, neutral losses, and simple fragment hypotheses.</p>
                        <div class="field">
                          <label for="msmsCandidateList">Candidate structures</label>
                          <textarea id="msmsCandidateList" rows="7" placeholder="Proposed product | CCO | proposed&#10;Starting material | CO | starting material&#10;Side product | CCCO | possible impurity"></textarea>
                          <div class="small muted">Optional. One candidate per line: <code>name | SMILES | role</code>. Leave blank for neutral-loss-only annotation.</div>
                        </div>
                        <div class="row">
                          <button class="primary" onclick="runMSMSAnnotation()">Annotate processed MS/MS</button>
                          <button class="ghost" onclick="copyCandidatesToMSMS()">Copy candidate list</button>
                          <button class="ghost" onclick="copyHRMSToMSMS()">Use HRMS precursor</button>
                          <button class="ghost" onclick="clearMSMSAnnotation()">Clear MS/MS</button>
                        </div>
                      </div>
                    </div>
                    <div id="msmsAnnotationBox" class="panel" style="margin-top:.8rem;">No MS/MS annotation yet.</div>
                    <div class="panel spectrum-inline-note" style="margin-top:.8rem;">
                      <strong>Interpretation note</strong>
                      <div class="small muted">Use MS/MS together with 1H/13C/2D NMR, predicted NMR matching, HRMS exact mass, and expert review. This beta does not perform raw LC-MS/MS import, database search, or exhaustive fragmentation-tree annotation.</div>
                    </div>
                  </div>

                  <div id="fragmentationTreePanel" class="panel" style="margin-bottom:.9rem;">
                    <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; flex-wrap:wrap;">
                      <div>
                        <h3 style="margin:0 0 .35rem;">MS/MS Fragmentation-Tree + Diagnostic Neutral-Loss Reasoning</h3>
                        <p class="muted small" style="margin:.15rem 0 .7rem; max-width:78ch;">Build an interpretable precursor-to-fragment-to-subfragment map from processed MS/MS peaks. The tree highlights diagnostic neutral losses, candidate-specific fragment hypotheses, contradiction flags, and human-review evidence.</p>
                      </div>
                      <span class="status-badge warn">Human review required</span>
                    </div>
                    <div class="grid2">
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">Fragmentation-tree input</h4>
                        <div class="grid2">
                          <div class="field">
                            <label for="fragTreePrecursorMz">Precursor m/z</label>
                            <input id="fragTreePrecursorMz" inputmode="decimal" placeholder="47.04914" value="47.04914" />
                          </div>
                          <div class="field">
                            <label for="fragTreeAdduct">Precursor adduct</label>
                            <select id="fragTreeAdduct">
                              <option value="[M+H]+" selected>[M+H]+</option>
                              <option value="[M+Na]+">[M+Na]+</option>
                              <option value="[M+K]+">[M+K]+</option>
                              <option value="[M+NH4]+">[M+NH4]+</option>
                              <option value="[M-H]-">[M-H]-</option>
                              <option value="[M+Cl]-">[M+Cl]-</option>
                              <option value="[M+FA-H]-">[M+FA-H]-</option>
                              <option value="[M+Ac-H]-">[M+Ac-H]-</option>
                              <option value="M">M</option>
                            </select>
                          </div>
                        </div>
                        <div class="grid2">
                          <div class="field">
                            <label for="fragTreeToleranceDa">m/z tolerance, Da</label>
                            <input id="fragTreeToleranceDa" inputmode="decimal" value="0.02" />
                          </div>
                          <div class="field">
                            <label for="fragTreePpmTolerance">ppm tolerance</label>
                            <input id="fragTreePpmTolerance" inputmode="decimal" value="20" />
                          </div>
                        </div>
                        <div class="grid2">
                          <div class="field">
                            <label for="fragTreeMinRelIntensity">Min relative intensity %</label>
                            <input id="fragTreeMinRelIntensity" inputmode="decimal" value="1" />
                          </div>
                          <div class="field">
                            <label for="fragTreeMaxPeaks">Max peaks</label>
                            <input id="fragTreeMaxPeaks" inputmode="numeric" value="75" />
                          </div>
                        </div>
                        <div class="field">
                          <label for="fragTreeMaxDepth">Max tree depth</label>
                          <input id="fragTreeMaxDepth" inputmode="numeric" value="3" />
                        </div>
                        <div class="field">
                          <label for="fragTreePeakList">Processed MS/MS peak list</label>
                          <textarea id="fragTreePeakList" rows="7" placeholder="m/z,intensity&#10;47.04914,10&#10;29.03858,100"></textarea>
                          <div class="small muted">Use processed centroid MS/MS peak tables only. This tree engine does not mutate raw spectra; use the LC-MS/MS import bridge to extract peak-list views from mzML/mzXML or source files.</div>
                        </div>
                      </div>
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">Candidate contradiction checks</h4>
                        <p class="muted small">Candidate structures let the tree flag whether losses such as H2O, NH3, CO2, HCl, HBr, and SO2 are chemically supported or contradictory.</p>
                        <div class="field">
                          <label for="fragTreeCandidateList">Candidate structures</label>
                          <textarea id="fragTreeCandidateList" rows="7" placeholder="Proposed product | CCO | proposed&#10;Starting material | CO | starting material&#10;Side product | CCCO | possible impurity"></textarea>
                          <div class="small muted">One candidate per line: <code>name | SMILES | role</code>.</div>
                        </div>
                        <div class="row">
                          <button class="primary" onclick="runFragmentationTree()">Build fragmentation tree</button>
                          <button class="ghost" onclick="copyMSMSToFragmentationTree()">Copy MS/MS inputs</button>
                          <button class="ghost" onclick="copyCandidatesToFragmentationTree()">Copy candidate list</button>
                          <button class="ghost" onclick="clearFragmentationTree()">Clear tree</button>
                        </div>
                      </div>
                    </div>
                    <div id="fragmentationTreeBox" class="panel" style="margin-top:.8rem;">No fragmentation tree yet.</div>
                    <div class="panel spectrum-inline-note" style="margin-top:.8rem;">
                      <strong>Interpretation note</strong>
                      <div class="small muted">Fragmentation-tree evidence is a transparent reasoning layer. It supports or weakens candidates, but final identity still requires HRMS, adduct/isotope evidence, MS/MS annotation, NMR, and human review.</div>
                    </div>
                  </div>

                  <div id="unifiedConfidencePanel" class="panel" style="margin-bottom:.9rem;">
                    <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; flex-wrap:wrap;">
                      <div>
                        <h3 style="margin:0 0 .35rem;">Unified Candidate Confidence Engine</h3>
                        <p class="muted small" style="margin:.15rem 0 .7rem; max-width:78ch;">Combine candidate-specific predicted NMR, HRMS exact mass, MS1 adduct/isotope inference, processed MS/MS annotation, and fragmentation-tree reasoning into one transparent ranked confidence report.</p>
                      </div>
                      <span class="status-badge warn">Decision support</span>
                    </div>
                    <div class="grid2">
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">Candidate + NMR evidence</h4>
                        <div class="field">
                          <label for="unifiedCandidateList">Candidate structures</label>
                          <textarea id="unifiedCandidateList" rows="6" placeholder="Proposed product | CCO | proposed&#10;Starting material | CO | starting material&#10;Side product | CCCO | possible impurity"></textarea>
                          <div class="small muted">One candidate per line: <code>name | SMILES | role</code>.</div>
                        </div>
                        <div class="field">
                          <label for="unifiedObservedProtonText">Observed 1H NMR text</label>
                          <textarea id="unifiedObservedProtonText" rows="4" placeholder="Current 1H text can be copied in read-only; it is not mutated by this layer."></textarea>
                        </div>
                        <div class="field">
                          <label for="unifiedObservedCarbonText">Observed 13C NMR text</label>
                          <textarea id="unifiedObservedCarbonText" rows="3" placeholder="Current 13C text can be copied in read-only; it is not mutated by this layer."></textarea>
                        </div>
                        <div class="grid2">
                          <div class="field">
                            <label for="unifiedNmr2dExperiment">Optional 2D NMR type</label>
                            <select id="unifiedNmr2dExperiment">
                              <option value="">Auto-detect</option>
                              <option value="COSY">COSY</option>
                              <option value="HSQC">HSQC</option>
                              <option value="HMQC">HMQC</option>
                              <option value="HMBC">HMBC</option>
                            </select>
                          </div>
                          <div class="field">
                            <label for="unifiedUseInferredAdduct">Use inferred adduct</label>
                            <select id="unifiedUseInferredAdduct">
                              <option value="true" selected>Yes</option>
                              <option value="false">No</option>
                            </select>
                          </div>
                        </div>
                        <div class="field">
                          <label for="unifiedObservedNmr2dText">Optional processed 2D NMR peak table</label>
                          <textarea id="unifiedObservedNmr2dText" rows="3" placeholder="f2_ppm,f1_ppm,intensity&#10;3.65,58.3,1200"></textarea>
                        </div>
                      </div>
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">HRMS, MS1, and MS/MS evidence</h4>
                        <div class="grid2">
                          <div class="field">
                            <label for="unifiedHrmsMz">HRMS observed m/z</label>
                            <input id="unifiedHrmsMz" inputmode="decimal" placeholder="47.04914" />
                          </div>
                          <div class="field">
                            <label for="unifiedHrmsAdduct">HRMS/adduct</label>
                            <select id="unifiedHrmsAdduct">
                              <option value="[M+H]+" selected>[M+H]+</option>
                              <option value="[M+Na]+">[M+Na]+</option>
                              <option value="[M+K]+">[M+K]+</option>
                              <option value="[M+NH4]+">[M+NH4]+</option>
                              <option value="[M-H]-">[M-H]-</option>
                              <option value="[M+Cl]-">[M+Cl]-</option>
                              <option value="[M+FA-H]-">[M+FA-H]-</option>
                              <option value="[M+Ac-H]-">[M+Ac-H]-</option>
                              <option value="M">M</option>
                            </select>
                          </div>
                        </div>
                        <div class="grid2">
                          <div class="field">
                            <label for="unifiedHrmsPpmTolerance">HRMS ppm tolerance</label>
                            <input id="unifiedHrmsPpmTolerance" inputmode="decimal" value="5" />
                          </div>
                          <div class="field">
                            <label for="unifiedMSMSPpmTolerance">MS/MS ppm tolerance</label>
                            <input id="unifiedMSMSPpmTolerance" inputmode="decimal" value="20" />
                          </div>
                        </div>
                        <div class="field">
                          <label for="unifiedMS1PeakList">Processed MS1/HRMS peak list optional</label>
                          <textarea id="unifiedMS1PeakList" rows="4" placeholder="m/z,intensity&#10;47.04914,100&#10;48.05249,2.3"></textarea>
                        </div>
                        <div class="field">
                          <label for="unifiedMSMSPrecursorMz">MS/MS precursor m/z</label>
                          <input id="unifiedMSMSPrecursorMz" inputmode="decimal" placeholder="47.04914" />
                        </div>
                        <div class="field">
                          <label for="unifiedMSMSPeakList">Processed MS/MS peak list optional</label>
                          <textarea id="unifiedMSMSPeakList" rows="4" placeholder="m/z,intensity&#10;47.04914,10&#10;29.03858,100"></textarea>
                        </div>
                        <div class="panel spectrum-inline-note" style="margin:.8rem 0;">
                          <strong>LC-MS consensus bridge</strong>
                          <div class="grid2" style="margin-top:.55rem;">
                            <label class="small"><input id="unifiedUseLCMSConsensus" type="checkbox" checked /> Include latest LC-MS feature-family consensus when available</label>
                            <div class="field" style="margin:0;"><label for="unifiedLCMSMinScore">Minimum family score</label><input id="unifiedLCMSMinScore" inputmode="decimal" value="0.42" /></div>
                          </div>
                        </div>
                        <div class="row">
                          <button class="primary" onclick="runUnifiedCandidateConfidence()">Build unified confidence</button>
                          <button class="ghost" onclick="copyInputsToUnifiedConfidence()">Copy current inputs</button>
                          <button class="ghost" onclick="clearUnifiedCandidateConfidence()">Clear unified result</button>
                        </div>
                      </div>
                    </div>
                    <div id="unifiedConfidenceBox" class="panel" style="margin-top:.8rem;">No unified candidate confidence result yet.</div>
                    <div class="panel spectrum-inline-note" style="margin-top:.8rem;">
                      <strong>Decision-support note</strong>
                      <div class="small muted">Unified confidence is a human-in-the-loop evidence dashboard, not an autonomous identity claim or calibrated DP4/DP5 probability. It highlights agreement, missing evidence, contradictions, and reviewer priorities.</div>
                    </div>
                  </div>

                  <div id="structureReportPanel" class="panel" style="margin-bottom:.9rem;">
                    <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; flex-wrap:wrap;">
                      <div>
                        <h3 style="margin:0 0 .35rem;">Regulatory-ready Structure Elucidation Report Composer</h3>
                        <p class="muted small" style="margin:.15rem 0 .7rem; max-width:78ch;">Convert the unified NMR/MS evidence stack into an audit-ready report with provenance hashes, processing history, ranked candidates, contradiction flags, and an explicit human approval gate.</p>
                      </div>
                      <span class="status-badge warn">Human review gate</span>
                    </div>
                    <div class="grid2">
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">Report metadata</h4>
                        <div class="field">
                          <label for="structureReportTitle">Report title</label>
                          <input id="structureReportTitle" value="Regulatory-ready Structure Elucidation Report" />
                        </div>
                        <div class="grid2">
                          <div class="field">
                            <label for="structureReportProject">Project name</label>
                            <input id="structureReportProject" placeholder="Project or study name" />
                          </div>
                          <div class="field">
                            <label for="structureReportPreparedBy">Prepared by</label>
                            <input id="structureReportPreparedBy" placeholder="Analyst name" />
                          </div>
                        </div>
                        <div class="grid2">
                          <div class="field">
                            <label for="structureReportReviewer">Reviewer</label>
                            <input id="structureReportReviewer" placeholder="Reviewer name" />
                          </div>
                          <div class="field">
                            <label for="structureReportReviewStatus">Review status</label>
                            <select id="structureReportReviewStatus">
                              <option value="">Not reviewed</option>
                              <option value="pending_review">Pending review</option>
                              <option value="approved">Approved</option>
                              <option value="rejected">Rejected</option>
                              <option value="needs_revision">Needs revision</option>
                            </select>
                          </div>
                        </div>
                        <div class="grid2">
                          <div class="field">
                            <label for="structureReportIntendedUse">Intended use</label>
                            <select id="structureReportIntendedUse">
                              <option value="research_decision_support" selected>Research decision support</option>
                              <option value="qc_batch_record">QC batch record</option>
                              <option value="regulatory_support">Regulatory support</option>
                              <option value="training_or_education">Training or education</option>
                            </select>
                          </div>
                          <div class="field">
                            <label for="structureReportRequireApproval">Require human approval</label>
                            <select id="structureReportRequireApproval">
                              <option value="true" selected>Yes</option>
                              <option value="false">No</option>
                            </select>
                          </div>
                        </div>
                        <div class="field">
                          <label for="structureReportReviewerComment">Reviewer comment</label>
                          <textarea id="structureReportReviewerComment" rows="3" placeholder="Add approval rationale, caveats, or requested changes"></textarea>
                        </div>
                      </div>
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">Provenance and processing record</h4>
                        <div class="field">
                          <label for="structureReportRawHash">Raw data SHA-256 optional</label>
                          <input id="structureReportRawHash" placeholder="Hash of immutable raw FID/MS upload" />
                        </div>
                        <div class="field">
                          <label for="structureReportSourceFiles">Source files</label>
                          <textarea id="structureReportSourceFiles" rows="4" placeholder="One file per line, e.g. sample_001_bruker.zip"></textarea>
                        </div>
                        <div class="field">
                          <label for="structureReportProcessingHistory">Processing history</label>
                          <textarea id="structureReportProcessingHistory" rows="5">Raw data preserved immutable
FT/phase/baseline processing stored as metadata
Peak picking and integration reviewed
Unified NMR/MS confidence generated</textarea>
                        </div>
                        <div class="field">
                          <label for="structureReportNotes">Report notes</label>
                          <textarea id="structureReportNotes" rows="3" placeholder="Study-specific notes or caveats"></textarea>
                        </div>
                        <div class="row">
                          <button class="primary" onclick="runStructureReportComposer()">Compose report</button>
                          <button class="ghost" onclick="copyInputsToStructureReport()">Copy unified inputs</button>
                          <button class="ghost" onclick="downloadStructureReportJson()">Download JSON</button>
                          <button class="ghost" onclick="downloadStructureReportHtml()">Download HTML</button>
                          <button class="ghost" onclick="clearStructureReport()">Clear report</button>
                        </div>
                      </div>
                    </div>
                    <div id="structureReportBox" class="panel" style="margin-top:.8rem;">No structure elucidation report yet.</div>
                    <div class="panel spectrum-inline-note" style="margin-top:.8rem;">
                      <strong>Release note</strong>
                      <div class="small muted">This composer creates an audit-ready decision record. It is not autonomous regulatory approval; release still requires human review, local SOP validation, and preservation of untouched raw spectral data.</div>
                    </div>
                  </div>

                  <div class="panel" style="margin-bottom:.9rem;">
                    <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; flex-wrap:wrap;">
                      <div>
                        <h3 style="margin:0 0 .35rem;">Raw LC-MS/MS mzML + Processed Peak Import Bridge</h3>
                        <p class="muted small" style="margin:.15rem 0 .7rem; max-width:76ch;">
                          Import mzML/mzXML or processed LC-MS peak tables into a non-destructive bridge that creates MS1, precursor, and MS/MS peak-list views for the HRMS, adduct/isotope, MS/MS, fragmentation-tree, unified confidence, and report layers.
                        </p>
                      </div>
                      <span class="status-badge ok">raw-MS bridge</span>
                    </div>
                    <div class="grid2">
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">A. Import source</h4>
                        <div class="field">
                          <label for="lcmsImportFile">Optional LC-MS/MS spectrum file</label>
                          <input id="lcmsImportFile" type="file" accept=".mzml,.mzxml,.mzdata,.imzml,.mgf,.cdf,.netcdf,.raw,.wiff,.wiff2,.d,.yep,.baf,.tdf,.tsf,.xml,.csv,.tsv,.txt,.json,.jcamp,.jdx,.dx,.xy,.asc,.dat" />
                          <div class="small muted">File upload is used when selected. Otherwise the text box below is imported.</div>
                        </div>
                        <div class="grid2">
                          <div class="field"><label for="lcmsImportFilename">Filename / source label</label><input id="lcmsImportFilename" placeholder="sample_001.mzML" /></div>
                          <div class="field">
                            <label for="lcmsImportFormat">Source format</label>
                            <select id="lcmsImportFormat">
                              <option value="auto" selected>Auto-detect</option>
                              <option value="mzML">mzML</option>
                              <option value="mzXML">mzXML</option>
                              <option value="processed_peak_table">Processed peak table</option>
                              <option value="unsupported_vendor">Unsupported vendor raw</option>
                            </select>
                          </div>
                        </div>
                        <div class="field">
                          <label for="lcmsImportText">mzML/mzXML text, vendor export, or processed peak table</label>
                          <textarea id="lcmsImportText" rows="8">scan_id,ms_level,rt_min,mz,intensity,precursor_mz
ms1_001,1,0.50,47.04914,100,
ms1_001,1,0.50,48.05249,2.3,
ms2_001,2,0.51,47.04914,10,47.04914
ms2_001,2,0.51,29.03858,100,47.04914
ms2_001,2,0.51,31.01839,25,47.04914</textarea>
                          <div class="small muted">CSV/TSV/space-delimited rows are accepted. Use columns such as scan_id, ms_level, rt_min, m/z, intensity, and precursor_mz.</div>
                        </div>
                      </div>
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">B. Downstream extraction controls</h4>
                        <div class="grid2">
                          <div class="field"><label for="lcmsPreferredPrecursor">Preferred MS/MS precursor m/z</label><input id="lcmsPreferredPrecursor" inputmode="decimal" placeholder="47.04914" /></div>
                          <div class="field"><label for="lcmsMinRelIntensity">Min relative intensity %</label><input id="lcmsMinRelIntensity" inputmode="decimal" value="0.5" /></div>
                        </div>
                        <div class="grid2">
                          <div class="field"><label for="lcmsMaxMS1Peaks">Max MS1 peaks</label><input id="lcmsMaxMS1Peaks" inputmode="numeric" value="250" /></div>
                          <div class="field"><label for="lcmsMaxMSMSPeaks">Max MS/MS peaks</label><input id="lcmsMaxMSMSPeaks" inputmode="numeric" value="250" /></div>
                        </div>
                        <div class="grid2">
                          <div class="field"><label for="lcmsMzToleranceDa">m/z tolerance, Da</label><input id="lcmsMzToleranceDa" inputmode="decimal" value="0.02" /></div>
                          <div class="field"><label for="lcmsPpmTolerance">ppm tolerance</label><input id="lcmsPpmTolerance" inputmode="decimal" value="20" /></div>
                        </div>
                        <div class="row">
                          <button class="primary" onclick="runLCMSImportBridge()">Import LC-MS/MS</button>
                          <button class="ghost" onclick="copyLCMSToMSWorkflows()">Copy to MS workflows</button>
                          <button class="ghost" onclick="copyLCMSHashToReport()">Copy hash to report</button>
                          <button class="ghost" onclick="clearLCMSImportBridge()">Clear import</button>
                        </div>
                        <div class="panel spectrum-inline-note" style="margin-top:.8rem;">
                          <strong>Raw-data rule</strong>
                          <div class="small muted">The bridge never overwrites raw LC-MS/MS data. It creates processed peak-list views, scan summaries, and SHA-256 provenance metadata for downstream analysis and human review.</div>
                        </div>
                      </div>
                    </div>
                    <div id="lcmsImportBridgeBox" class="panel" style="margin-top:.8rem;">No LC-MS/MS import bridge result yet.</div>
                  </div>

                  <div class="panel" style="margin-bottom:.9rem;">
                    <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; flex-wrap:wrap;">
                      <div>
                        <h3 style="margin:0 0 .35rem;">LC-MS Feature Detection + EIC/XIC + Peak Purity</h3>
                        <p class="muted small" style="margin:.15rem 0 .7rem; max-width:76ch;">
                          Detect chromatographic features from MS1 scans, extract EIC/XIC traces for target m/z values, estimate local peak purity, and link features back to nearby MS/MS precursor scans before candidate scoring.
                        </p>
                      </div>
                      <span class="status-badge ok">feature QC</span>
                    </div>
                    <div class="grid2">
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">A. Feature source</h4>
                        <div class="field">
                          <label for="lcmsFeatureFile">Optional LC-MS/MS spectrum file</label>
                          <input id="lcmsFeatureFile" type="file" accept=".mzml,.mzxml,.mzdata,.imzml,.mgf,.cdf,.netcdf,.raw,.wiff,.wiff2,.d,.yep,.baf,.tdf,.tsf,.xml,.csv,.tsv,.txt,.json,.jcamp,.jdx,.dx,.xy,.asc,.dat" />
                          <div class="small muted">Use the same LC-MS/MS spectrum or processed LC-MS peak table accepted by the import bridge.</div>
                        </div>
                        <div class="grid2">
                          <div class="field"><label for="lcmsFeatureFilename">Filename / source label</label><input id="lcmsFeatureFilename" placeholder="sample_001.mzML" /></div>
                          <div class="field">
                            <label for="lcmsFeatureFormat">Source format</label>
                            <select id="lcmsFeatureFormat">
                              <option value="auto" selected>Auto-detect</option>
                              <option value="mzML">mzML</option>
                              <option value="mzXML">mzXML</option>
                              <option value="processed_peak_table">Processed peak table</option>
                              <option value="unsupported_vendor">Unsupported vendor raw</option>
                            </select>
                          </div>
                        </div>
                        <div class="field">
                          <label for="lcmsFeatureText">mzML/mzXML text or processed LC-MS peak table</label>
                          <textarea id="lcmsFeatureText" rows="9">scan_id,ms_level,rt_min,mz,intensity,precursor_mz
ms1_001,1,0.00,47.04914,10,
ms1_002,1,0.10,47.04914,55,
ms1_003,1,0.20,47.04914,100,
ms1_003,1,0.20,59.04914,8,
ms1_004,1,0.30,47.04914,50,
ms1_005,1,0.40,47.04914,12,
ms2_001,2,0.20,29.03858,100,47.04914
ms2_001,2,0.20,31.01839,25,47.04914</textarea>
                          <div class="small muted">MS1 scans are used for chromatographic features. MS2 scans are linked by precursor m/z and retention time.</div>
                        </div>
                      </div>
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">B. EIC/XIC and purity controls</h4>
                        <div class="field"><label for="lcmsFeatureTargets">Target m/z values</label><input id="lcmsFeatureTargets" placeholder="47.04914, 69.03109" value="47.04914" /></div>
                        <div class="grid2">
                          <div class="field"><label for="lcmsFeatureMzTolDa">m/z tolerance, Da</label><input id="lcmsFeatureMzTolDa" inputmode="decimal" value="0.02" /></div>
                          <div class="field"><label for="lcmsFeaturePpmTol">ppm tolerance</label><input id="lcmsFeaturePpmTol" inputmode="decimal" value="20" /></div>
                        </div>
                        <div class="grid2">
                          <div class="field"><label for="lcmsFeatureMinRelHeight">Min relative feature height %</label><input id="lcmsFeatureMinRelHeight" inputmode="decimal" value="5" /></div>
                          <div class="field"><label for="lcmsFeatureMinScans">Min scans per feature</label><input id="lcmsFeatureMinScans" inputmode="numeric" value="2" /></div>
                        </div>
                        <div class="grid2">
                          <div class="field"><label for="lcmsFeatureSmoothing">Smoothing window</label><input id="lcmsFeatureSmoothing" inputmode="numeric" value="1" /></div>
                          <div class="field"><label for="lcmsFeaturePurityWindow">Purity RT window, min</label><input id="lcmsFeaturePurityWindow" inputmode="decimal" value="0.20" /></div>
                        </div>
                        <div class="grid2">
                          <div class="field"><label for="lcmsFeatureTopIons">Top coeluting ions</label><input id="lcmsFeatureTopIons" inputmode="numeric" value="5" /></div>
                          <div class="field"><label for="lcmsFeatureMaxFeatures">Max features</label><input id="lcmsFeatureMaxFeatures" inputmode="numeric" value="20" /></div>
                        </div>
                        <div class="row">
                          <button class="primary" onclick="runLCMSFeatureDetection()">Detect features + XICs</button>
                          <button class="ghost" onclick="useLatestLCMSImportForFeatures()">Use import bridge input</button>
                          <button class="ghost" onclick="copyLCMSFeatureToMSWorkflows()">Copy best feature</button>
                          <button class="ghost" onclick="copyLCMSFeaturePurityToReport()">Copy purity to report</button>
                          <button class="ghost" onclick="clearLCMSFeatureDetection()">Clear features</button>
                        </div>
                        <div class="panel spectrum-inline-note" style="margin-top:.8rem;">
                          <strong>Interpretation rule</strong>
                          <div class="small muted">Peak purity is chromatographic evidence only. Coelution, isotope clusters, in-source fragments, and adduct families still require human review before structural claims.</div>
                        </div>
                      </div>
                    </div>
                    <div id="lcmsFeatureBox" class="panel" style="margin-top:.8rem;">No LC-MS feature detection result yet.</div>
                  </div>

                  <div class="panel" style="margin-bottom:.9rem;">
                    <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; flex-wrap:wrap;">
                      <div>
                        <h3 style="margin:0 0 .35rem;">LC-MS Feature Grouping + Blank Subtraction + RT Alignment</h3>
                        <p class="muted small" style="margin:.15rem 0 .7rem; max-width:76ch;">
                          Group LC-MS features across sample, blank, QC, or reference runs; apply conservative retention-time alignment; subtract blank/background features; and flag isotope, adduct, and in-source-loss feature families before candidate scoring.
                        </p>
                      </div>
                      <span class="status-badge ok">feature table QC</span>
                    </div>
                    <div class="grid2">
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">A. Sample and blank runs</h4>
                        <div class="grid2">
                          <div class="field"><label for="lcmsGroupSampleFilename">Sample filename / run label</label><input id="lcmsGroupSampleFilename" placeholder="sample_001.csv" /></div>
                          <div class="field"><label for="lcmsGroupBlankFilename">Blank filename / run label</label><input id="lcmsGroupBlankFilename" placeholder="blank_001.csv" /></div>
                        </div>
                        <div class="field">
                          <label for="lcmsGroupFormat">Source format</label>
                          <select id="lcmsGroupFormat">
                            <option value="auto" selected>Auto-detect</option>
                            <option value="mzML">mzML</option>
                            <option value="mzXML">mzXML</option>
                            <option value="processed_peak_table">Processed peak table</option>
                            <option value="unsupported_vendor">Unsupported vendor raw</option>
                          </select>
                        </div>
                        <div class="field">
                          <label for="lcmsGroupSampleText">Sample LC-MS peak table or mzML/mzXML text</label>
                          <textarea id="lcmsGroupSampleText" rows="8">scan_id,ms_level,rt_min,mz,intensity,precursor_mz
s_ms1_001,1,0.00,47.04914,10,
s_ms1_002,1,0.10,47.04914,70,
s_ms1_003,1,0.20,47.04914,140,
s_ms1_004,1,0.30,47.04914,65,
s_ms1_005,1,0.40,47.04914,12,
s_ms2_001,2,0.20,29.03858,100,47.04914</textarea>
                        </div>
                        <div class="field">
                          <label for="lcmsGroupBlankText">Blank/background run optional</label>
                          <textarea id="lcmsGroupBlankText" rows="6">scan_id,ms_level,rt_min,mz,intensity,precursor_mz
b_ms1_001,1,0.02,47.04914,2,
b_ms1_002,1,0.12,47.04914,4,
b_ms1_003,1,0.22,47.04914,5,
b_ms1_004,1,0.32,47.04914,3,</textarea>
                        </div>
                      </div>
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">B. Alignment and grouping controls</h4>
                        <div class="field"><label for="lcmsGroupTargets">Target m/z values</label><input id="lcmsGroupTargets" placeholder="47.04914, 69.03109" value="47.04914" /></div>
                        <div class="field"><label for="lcmsGroupAnchorMz">RT alignment anchor m/z values optional</label><input id="lcmsGroupAnchorMz" placeholder="leave blank to use shared features" /></div>
                        <div class="grid2">
                          <div class="field"><label for="lcmsGroupMzTolDa">m/z tolerance, Da</label><input id="lcmsGroupMzTolDa" inputmode="decimal" value="0.02" /></div>
                          <div class="field"><label for="lcmsGroupPpmTol">ppm tolerance</label><input id="lcmsGroupPpmTol" inputmode="decimal" value="20" /></div>
                        </div>
                        <div class="grid2">
                          <div class="field"><label for="lcmsGroupRtTol">Group RT tolerance, min</label><input id="lcmsGroupRtTol" inputmode="decimal" value="0.12" /></div>
                          <div class="field"><label for="lcmsGroupFamilyRtTol">Family RT tolerance, min</label><input id="lcmsGroupFamilyRtTol" inputmode="decimal" value="0.15" /></div>
                        </div>
                        <div class="grid2">
                          <div class="field"><label for="lcmsGroupBlankRatio">Blank-like area ratio threshold</label><input id="lcmsGroupBlankRatio" inputmode="decimal" value="0.30" /></div>
                          <div class="field"><label for="lcmsGroupBackgroundRatio">Possible background ratio</label><input id="lcmsGroupBackgroundRatio" inputmode="decimal" value="0.10" /></div>
                        </div>
                        <div class="grid2">
                          <div class="field"><label for="lcmsGroupMaxFeatures">Max features per run</label><input id="lcmsGroupMaxFeatures" inputmode="numeric" value="50" /></div>
                          <div class="field"><label for="lcmsGroupMaxGroups">Max groups to report</label><input id="lcmsGroupMaxGroups" inputmode="numeric" value="100" /></div>
                        </div>
                        <div class="row">
                          <button class="primary" onclick="runLCMSFeatureGrouping()">Group features + subtract blank</button>
                          <button class="ghost" onclick="useLatestLCMSFeaturesForGrouping()">Use feature source</button>
                          <button class="ghost" onclick="copyLCMSFeatureGroupToMSWorkflows()">Copy best group</button>
                          <button class="ghost" onclick="copyLCMSFeatureGroupingToReport()">Copy table to report</button>
                          <button class="ghost" onclick="clearLCMSFeatureGrouping()">Clear grouping</button>
                        </div>
                        <div class="panel spectrum-inline-note" style="margin-top:.8rem;">
                          <strong>Evidence rule</strong>
                          <div class="small muted">Blank subtraction and RT alignment are feature-table triage. They should reduce false positives, but they do not prove identity or replace human inspection of chromatograms, isotope/adduct families, and carryover.</div>
                        </div>
                      </div>
                    </div>
                    <div id="lcmsFeatureGroupingBox" class="panel" style="margin-top:.8rem;">No LC-MS feature grouping result yet.</div>
                  </div>

                  <div class="panel" style="margin-bottom:.9rem;">
                    <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:1rem; flex-wrap:wrap;">
                      <div>
                        <h3 style="margin:0 0 .35rem;">LC-MS Isotope/Adduct Consensus + Feature-Family Confidence</h3>
                        <p class="muted small" style="margin:.15rem 0 .7rem; max-width:76ch;">
                          Score Week 37 grouped features as coeluting LC-MS feature families using isotope envelope agreement, adduct-pair consistency, in-source-loss hints, blank-subtraction gates, peak purity, and MS/MS precursor linkage.
                        </p>
                      </div>
                      <span class="status-badge ok">family consensus</span>
                    </div>
                    <div class="grid2">
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">A. Grouped feature input</h4>
                        <div class="field">
                          <label for="lcmsConsensusFeatureTable">Grouped feature table text</label>
                          <textarea id="lcmsConsensusFeatureTable" rows="8" placeholder="Paste the Week 37 exportable grouped feature table here, or use the latest grouping result."></textarea>
                          <div class="small muted">The latest Week 37 grouping result is used automatically when available. Pasted table text is useful for review-only reruns.</div>
                        </div>
                        <div class="grid2">
                          <div class="field"><label for="lcmsConsensusFormula">Optional formula for isotope scoring</label><input id="lcmsConsensusFormula" placeholder="C10H12O3" /></div>
                          <div class="field"><label for="lcmsConsensusAdduct">Expected anchor adduct</label><input id="lcmsConsensusAdduct" value="[M+H]+" /></div>
                        </div>
                        <div class="grid2">
                          <div class="field"><label for="lcmsConsensusAnchorGroup">Anchor group optional</label><input id="lcmsConsensusAnchorGroup" placeholder="G001" /></div>
                          <div class="field"><label for="lcmsConsensusMinScore">Promotion score gate</label><input id="lcmsConsensusMinScore" inputmode="decimal" value="0.62" /></div>
                        </div>
                      </div>
                      <div class="panel" style="margin:0;">
                        <h4 style="margin:.1rem 0 .45rem;">B. Consensus controls</h4>
                        <div class="grid2">
                          <div class="field"><label for="lcmsConsensusMzTolDa">m/z tolerance, Da</label><input id="lcmsConsensusMzTolDa" inputmode="decimal" value="0.02" /></div>
                          <div class="field"><label for="lcmsConsensusPpmTol">ppm tolerance</label><input id="lcmsConsensusPpmTol" inputmode="decimal" value="20" /></div>
                        </div>
                        <div class="grid2">
                          <div class="field"><label for="lcmsConsensusRtTol">Family RT tolerance, min</label><input id="lcmsConsensusRtTol" inputmode="decimal" value="0.15" /></div>
                          <div class="field"><label for="lcmsConsensusMinArea">Minimum blank-subtracted area</label><input id="lcmsConsensusMinArea" inputmode="decimal" value="0" /></div>
                        </div>
                        <div class="grid2">
                          <div class="field"><label for="lcmsConsensusBlankRatio">Blank-like threshold</label><input id="lcmsConsensusBlankRatio" inputmode="decimal" value="0.30" /></div>
                          <div class="field"><label for="lcmsConsensusMaxFamilies">Max families</label><input id="lcmsConsensusMaxFamilies" inputmode="numeric" value="50" /></div>
                        </div>
                        <div class="grid2">
                          <label class="small"><input id="lcmsConsensusIncludeBackground" type="checkbox" /> Include background groups</label>
                          <label class="small"><input id="lcmsConsensusRequireSample" type="checkbox" checked /> Require sample enrichment</label>
                        </div>
                        <div class="row" style="margin-top:.8rem;">
                          <button class="primary" onclick="runLCMSFeatureConsensus()">Score feature-family consensus</button>
                          <button class="ghost" onclick="useLatestLCMSGroupingForConsensus()">Use latest grouping table</button>
                          <button class="ghost" onclick="copyLCMSConsensusToReport()">Copy consensus to report</button>
                          <button class="ghost" onclick="clearLCMSFeatureConsensus()">Clear consensus</button>
                        </div>
                        <div class="panel spectrum-inline-note" style="margin-top:.8rem;">
                          <strong>Consensus rule</strong>
                          <div class="small muted">A promoted family is a better LC-MS evidence object, not a molecular identification. Candidate ranking still needs NMR, HRMS, MS/MS fragments, and reviewer approval.</div>
                        </div>
                      </div>
                    </div>
                    <div id="lcmsFeatureConsensusBox" class="panel" style="margin-top:.8rem;">No LC-MS feature-family consensus result yet.</div>
                  </div>

                  <div id="processedSpectrumPanel" class="panel hidden" style="margin-bottom:.9rem;">
                    <h3 style="margin:0 0 .45rem;">Processed spectrum upload</h3>
                    <div class="grid2">
                      <div class="field">
                        <label for="spectrumFile">Spectrum file (.csv, .tsv, .txt, .jcamp, .jdx, .dx, .xy, .asc, .dat)</label>
                        <input id="spectrumFile" type="file" accept=".csv,.tsv,.txt,.jcamp,.jdx,.dx,.xy,.asc,.dat" />
                      </div>
                      <div class="field">
                        <label for="frequencyMHz">Frequency (MHz)</label>
                        <input id="frequencyMHz" data-clear-on-focus="true" value="500" />
                      </div>
                    </div>
                    <div class="field">
                      <label for="referencePPM">Reference ppm (optional)</label>
                      <input id="referencePPM" data-clear-on-focus="true" value="0.00" />
                    </div>
                    <div class="field">
                      <label for="processedDisplayMode">Display mode</label>
                      <select id="processedDisplayMode">
                        <option value="real" selected>Real spectrum - original intensity</option>
                        <option value="magnifier">Real spectrum + weak-peak inset</option>
                      </select>
                    </div>
                    <div class="field">
                      <label for="referenceNmrText">Reference ¹H NMR text (optional)</label>
                      <textarea id="referenceNmrText" placeholder="Paste literature or copied ¹H NMR text to use as a target + diff comparison during spectrum peak picking."></textarea>
                    </div>
                    <div class="field">
                      <label class="checkbox-row" for="maskSolventRegions">
                        <input id="maskSolventRegions" type="checkbox" checked />
                        <span>
                          <strong>Mask solvent/water regions</strong><br />
                          <span class="muted small">Recommended for processed spectra with dominant solvent or HDO signals, especially in D₂O.</span>
                        </span>
                      </label>
                    </div>
                    <div class="panel small" style="margin-bottom:.75rem;">
                      <strong>Real spectrum view</strong>
                      <div class="muted" style="margin-top:.25rem;">Preview keeps uploaded intensities unchanged. Peak-height, clipping, and weak-peak magnifier controls are viewer-only.</div>
                    </div>
                    <details class="panel small" style="margin-bottom:.75rem;">
                      <summary><strong>Processed-file correction</strong></summary>
                      <div class="grid2" style="margin-top:.65rem;">
                        <div class="field">
                          <label for="processedBaselineCorrection">Apply processed-file baseline correction</label>
                          <select id="processedBaselineCorrection">
                            <option value="bernstein" selected>Bernstein polynomial fit</option>
                            <option value="none">Off / preserve uploaded trace</option>
                          </select>
                        </div>
                        <div class="field">
                          <label for="processedBaselineOrder">Baseline polynomial order</label>
                          <input id="processedBaselineOrder" value="3" min="1" max="8" />
                        </div>
                      </div>
                      <div class="muted" style="margin-top:.35rem;">For already processed spectra, correction is optional and explicit.</div>
                    </details>
                    <div class="row">
                      <button class="secondary" onclick="previewSpectrum()">Preview processed spectrum</button>
                      <button class="ghost" onclick="useSpectrumPeaks()">Use reviewed peaks as text</button>
                      <button class="primary" onclick="analyzeSpectrum()">Analyze uploaded spectrum</button>
                      <button class="ghost" onclick="clearAnalysisWorkspace()">Clear analysis</button>
                    </div>
                    <div id="spectrumPreviewBox" class="panel" style="margin-top:.8rem;">No processed spectrum preview yet.</div>
                  </div>

                </div>

                <div class="card">
                  <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                    <h2>Readable output</h2>
                    <span id="resultBadge" class="status-badge warn">No analysis yet</span>
                  </div>
                  <div id="readableOutput" class="panel">No output yet.</div>
                  <details style="margin-top:.85rem;" open>
                    <summary>Developer JSON</summary>
                    <pre id="jsonOutput" class="json-box">{}</pre>
                  </details>
                </div>
              </section>

              <section id="section-jobs" class="section">
                <div class="card">
                  <h2>Jobs</h2>
                  <p class="muted small">Batch upload lets you submit multiple analyses at once. Supported columns include <code>smiles</code>, <code>sample_id</code>, <code>nmr_text</code> (or <code>¹H NMR text</code>), and optional <code>solvent</code>.</p>
                  <div class="field">
                    <label for="uploadFile">CSV / JSON batch upload</label>
                    <input id="uploadFile" type="file" accept=".csv,.json" />
                  </div>
                  <div class="row">
                    <button class="primary" onclick="uploadJob()">Upload batch</button>
                    <button class="secondary" onclick="loadJobs()">Refresh jobs</button>
                    <button class="ghost" onclick="loadQueueStatus()">Queue status</button>
                  </div>
                  <div id="queueStatusBox" class="panel" style="margin-top:.85rem;">Queue status not loaded yet.</div>
                  <div id="jobsBox" style="margin-top:.85rem;">No jobs loaded yet.</div>
                </div>
              </section>

              <section id="section-workspaces" class="section">
                <div class="card">
                  <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                    <div>
                      <h2>Workspaces</h2>
                      <p class="muted small">Organize projects, save samples from the current analysis inputs, and open evidence reports without leaving the app.</p>
                    </div>
                    <span id="workspaceStatusBadge" class="status-badge warn">No project selected</span>
                  </div>
                  <div class="grid2" style="margin-top:.9rem;">
                    <div class="panel">
                      <h3 style="margin-top:0;">Projects</h3>
                      <div class="field">
                        <label for="workspaceProjectName">Project name</label>
                        <input id="workspaceProjectName" placeholder="Enter a project name" />
                      </div>
                      <div class="field">
                        <label for="workspaceProjectDescription">Description (optional)</label>
                        <textarea id="workspaceProjectDescription" style="min-height:110px;" placeholder="Optional workspace description"></textarea>
                      </div>
                      <div class="row">
                        <button class="primary" onclick="createWorkspaceProject()">Create project</button>
                        <button class="secondary" onclick="loadProjects()">Refresh projects</button>
                      </div>
                      <div id="workspaceProjectsBox" style="margin-top:.85rem;">No projects loaded yet.</div>
                    </div>
                    <div class="panel">
                      <h3 style="margin-top:0;">Samples</h3>
                      <div id="workspaceSelectionBox" class="panel small">No project selected yet.</div>
                      <div id="workspaceSeedNote" class="muted small" style="margin-top:.7rem;">Use the current analysis inputs or send a history record into Workspaces to save it as a sample.</div>
                      <div class="row" style="margin-top:.8rem;">
                        <button class="primary" onclick="createWorkspaceSampleFromCurrentInputs()">Create sample from current analysis inputs</button>
                        <button class="secondary" onclick="loadSelectedProjectSamples()">Load samples for selected project</button>
                      </div>
                      <div id="workspaceSamplesBox" style="margin-top:.85rem;">No samples loaded yet.</div>
                    </div>
                  </div>
                  <div class="panel" id="workspaceProjectDashboardBox" style="margin-top:.9rem;">No project selected yet.</div>
                  <div class="grid2" style="margin-top:.9rem;">
                    <div class="panel">
                      <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                        <h3 style="margin:0;">Sample detail</h3>
                        <span id="workspaceSampleBadge" class="status-badge warn">No sample opened</span>
                      </div>
                      <div id="workspaceSampleDetailBox" style="margin-top:.85rem;">No sample opened yet.</div>
                    </div>
                    <div class="panel">
                      <h3 style="margin-top:0;">Sample analysis comparison</h3>
                      <div id="workspaceComparisonBox">No sample opened yet.</div>
                    </div>
                  </div>
                  <div class="panel" style="margin-top:.9rem;">
                    <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                      <h3 style="margin:0;">Reviewer timeline and audit trail</h3>
                      <span id="workspaceTimelineBadge" class="status-badge warn">No linked analysis</span>
                    </div>
                    <div id="workspaceTimelineBox" style="margin-top:.85rem;">No linked analysis loaded yet.</div>
                  </div>
                  <div class="panel" style="margin-top:.9rem;">
                    <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                      <h3 style="margin:0;">Evidence reports</h3>
                      <span id="latestAnalysisBadge" class="status-badge warn">No latest analysis</span>
                    </div>
                    <div class="grid2">
                      <div class="field">
                        <label for="reportAnalysisId">Analysis ID</label>
                        <input id="reportAnalysisId" placeholder="Enter an analysis ID" />
                        <input id="workspaceAnalysisId" type="hidden" />
                      </div>
                      <div class="field">
                        <label>Actions</label>
                        <div class="row">
                          <button class="primary" onclick="generateReportFromCurrentLatestAnalysis()">Generate from current/latest</button>
                          <button class="primary" onclick="useLatestAnalysisReport()">Use latest analysis</button>
                          <button class="secondary" onclick="loadEvidenceReportJson()">Load report JSON</button>
                          <button class="ghost" onclick="openEvidenceReportHtml()">Open report HTML</button>
                        </div>
                      </div>
                    </div>
                    <div id="workspaceReportBox" style="margin-top:.85rem;">No report loaded yet.</div>
                  </div>
                </div>
              </section>

              <section id="section-history" class="section">
                <div class="card">
                  <h2>History</h2>
                  <div class="row">
                    <button class="secondary" onclick="loadHistory()">Refresh history</button>
                  </div>
                  <div id="historyBox" style="margin-top:.85rem;">No history loaded yet.</div>
                </div>
              </section>

              <section id="section-reviews" class="section">
                <div class="card">
                  <h2>Review queue</h2>
                  <p class="muted small">Admin-only view for approve / reject / override decisions.</p>
                  <div class="row">
                    <button class="secondary" onclick="loadReviews()">Load review queue</button>
                  </div>
                  <div id="reviewQueue" style="margin-top:.85rem;">No review data loaded yet.</div>
                </div>
              </section>

              <section id="section-admin" class="section">
                <div class="card">
                  <h2>Admin console</h2>
                  <div class="row">
                    <button class="secondary" onclick="loadAdminUsers()">Load users</button>
                    <button class="secondary" onclick="loadSystem()">Load system summary</button>
                  </div>
                  <div id="adminSystem" style="margin-top:.85rem;"></div>
                  <div id="adminUsers" style="margin-top:.85rem;"></div>
                </div>
              </section>
            </main>
          </div>
        </div>
      </div>
      <script>
        const state = { token: localStorage.getItem("nmrcheck_token") || "", validationOk: false, me: null, verificationToken: localStorage.getItem("nmrcheck_verification_token") || "", analysisInputMethod: "paste", carbon13InputMethod: "text", fidPresets: [], fidRuns: [], selectedFidRunIds: [], rawFidArchive: null, latestSpectrumPreview: null, latestRawFidPreview: null, latestCarbon13Preview: null, latestCarbon13SpectrumPreview: null, latestDeptAptPreview: null, latestDeptAptReport: null, latestNmr2dPreview: null, latestNmr2dReport: null, latestNmr2dSavedRunId: null, latestCandidateComparison: null, latestSpectralSimilarity: null, latestPredictedNMRMatch: null, latestHRMSMatch: null, latestHRMSFormulaSearch: null, latestAdductInference: null, latestMSMSAnnotation: null, latestFragmentationTree: null, latestUnifiedConfidence: null, latestStructureReport: null, latestLCMSImport: null, latestLCMSImportSourceText: null, latestLCMSFeatures: null, latestLCMSFeatureSourceText: null, latestLCMSFeatureGrouping: null, latestLCMSFeatureConsensus: null, latestSpectrumPlotId: "spectrumInteractivePlot", spectrumPreviewContexts: {}, latestSpectrumPreviewSignature: "", spectrumShowPeaks: true, spectrumTraceMode: "review", spectrumTraceModes: {}, latestSpectrumXRange: null, spectrumVerticalScale: 1.0, spectrumTallPeakClip: false, spectrumWeakPeakMagnifier: false, spectrumZeroLine: true, spectrumDragMode: "pan", spectrumLabelThreshold: 0.12, spectrumPeakDecisions: {}, spectrumDecisionUndoStack: [], selectedSpectrumMarker: null, defaultFormValues: null, historyItems: [], latestAnalysisId: null, workspaceProjects: [], selectedProjectId: null, workspaceSamples: [], workspaceProjectDashboard: null, selectedWorkspaceSampleId: null, selectedWorkspaceSample: null, workspaceSampleDetail: null, workspaceSampleComparison: null, workspaceSampleReports: null, workspaceSeedAnalysisId: null, workspaceSeedSnapshot: null, loadedEvidenceReport: null, workspaceSampleReport: null, workspaceTimeline: { analysisId: null, decisions: [], auditEvents: [] } };
        const el = (id) => document.getElementById(id);

        function escapeHtml(value) {
          return String(value).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");
        }
        function toSubscriptDigits(text) {
          const map = {"0":"₀","1":"₁","2":"₂","3":"₃","4":"₄","5":"₅","6":"₆","7":"₇","8":"₈","9":"₉"};
          return String(text).replace(/[0-9]/g, (d) => map[d] || d);
        }

        function prettyChemicalLabel(text) {
          if (text === null || text === undefined || text === "") return "—";
          return toSubscriptDigits(String(text));
        }

        function formatNucleusLabel(text) {
          return String(text || "¹H").replace(/13C/g, "¹³C").replace(/1H/g, "¹H");
        }

        function formatNmrLabelText(text) {
          return String(text || "").replace(/13C/g, "¹³C").replace(/1H/g, "¹H");
        }

        function prettyFormula(text) {
          if (text === null || text === undefined || text === "") return "—";
          return toSubscriptDigits(String(text));
        }

        function persistVerificationToken(token) {
          state.verificationToken = token || "";
          localStorage.setItem("nmrcheck_verification_token", state.verificationToken);
          const box = el("verificationTokenBox");
          if (box) box.textContent = state.verificationToken ? `Verification token: ${state.verificationToken}` : "No verification token requested yet.";
          const input = el("verifyToken");
          if (input && state.verificationToken) input.value = state.verificationToken;
        }

        function extractActionToken(rawValue) {
          const raw = String(rawValue || "").trim();
          if (!raw) return "";
          try {
            const parsed = JSON.parse(raw);
            if (parsed && typeof parsed === "object" && parsed.token) return String(parsed.token).trim();
          } catch (_) { }
          const urlMatch = raw.match(/[?&]token=([^&\s]+)/i);
          if (urlMatch) return decodeURIComponent(urlMatch[1]).trim();
          const tokenMatch = raw.match(/[A-Za-z0-9_-]{20,}/);
          return tokenMatch ? tokenMatch[0].trim() : raw;
        }

        function setJson(data) {
          const target = el("jsonOutput");
          if (target) target.textContent = typeof data === "string" ? data : JSON.stringify(data, null, 2);
        }

        function setValidationBadge(text, variantClass) {
          el("validationBadge").className = `status-badge ${variantClass}`;
          el("validationBadge").textContent = text;
        }

        function setResultBadge(text, variantClass) {
          el("resultBadge").className = `status-badge ${variantClass}`;
          el("resultBadge").textContent = text;
        }

        function persistToken(token) {
          state.token = token || "";
          if (state.token) {
            localStorage.setItem("nmrcheck_token", state.token);
            el("tokenBox").textContent = state.token;
          } else {
            localStorage.removeItem("nmrcheck_token");
            if (el("tokenBox")) el("tokenBox").textContent = "No token yet.";
          }
        }

        function withAccessToken(path) {
          if (!state.token) return path;
          const joiner = path.includes("?") ? "&" : "?";
          return `${path}${joiner}access_token=${encodeURIComponent(state.token)}`;
        }

        function openAuthedPath(path) {
          window.open(withAccessToken(path), "_blank", "noopener,noreferrer");
        }

        function setAuthMessage(text, good=false) {
          const box = el("authMessage");
          box.textContent = text;
          box.style.color = good ? "var(--success)" : "var(--muted)";
        }

        function togglePassword(inputId, button) {
          const input = el(inputId);
          if (!input) return;
          const show = input.type === "password";
          input.type = show ? "text" : "password";
          if (button) button.textContent = show ? "🙈" : "👁";
        }

        function installClearOnFocus() {
          document.querySelectorAll("[data-clear-on-focus='true']").forEach((node) => {
            node.dataset.original = node.value;
            node.dataset.pristine = "true";
            node.addEventListener("focus", () => {
              if (node.dataset.pristine === "true" && node.value === node.dataset.original) {
                node.value = "";
              }
            }, { once: true });
            node.addEventListener("input", () => {
              node.dataset.pristine = "false";
            });
          });
        }

        function installHelpfulTooltips() {
          const byId = {
            analysisInputMethod: "Choose whether to paste assigned ¹H NMR text, upload a processed spectrum, or process raw Bruker or Varian/Agilent FID data.",
            smiles: "Structure input used to calculate expected proton counts and compare against the extracted peak list.",
            nmrText: "Parseable ¹H NMR peak text used for validation and analysis.",
            carbon13InputMethod: "Choose whether to paste assigned ¹³C NMR text, upload a processed carbon spectrum, or process raw carbon FID data.",
            carbon13Text: "Parseable ¹³C NMR carbon-shift list used for carbon-count validation.",
            carbon13SpectrumFile: "Processed ¹³C spectrum trace, peak table, or simple JCAMP-DX file.",
            carbon13FidFile: "Bruker or Varian/Agilent 1D raw ¹³C FID archive; .zip, .tar.gz, and .tgz are accepted.",
            fidFile: "Raw Bruker or Varian/Agilent vendor archive. Upload & Lock stores this exact file immutably before preview or processing.",
            solvent: "Solvent context used for water, residual solvent, exchange, and impurity checks.",
            referenceNmrText: "Optional literature or expected ¹H NMR text used to match extracted spectrum peaks.",
            maskSolventRegions: "Exclude solvent and water windows during automatic peak picking.",
            fidProcessingPreset: "Balanced is conservative, Sensitive weak peaks lowers the threshold, Higher resolution increases zero filling.",
            fidReferencePPM: "Optional reference target; one observed FID peak is selected and shifted to this ppm.",
            fidPeakSensitivity: "Lower values call weaker peaks; higher values are more conservative.",
            fidPhaseMode: "Phase correction is applied to the complex spectrum before real extraction and baseline correction.",
            fidBaselineCorrection: "Raw FID baseline correction defaults to Bernstein polynomial fit, order 3.",
            fidBaselineOrder: "Polynomial order for Bernstein baseline correction; order 3 is the conservative default.",
            fidDisplayMode: "Real spectrum is the default; optional magnifier adds a display-only inset without changing evidence data.",
            processedDisplayMode: "Real spectrum is the default. Display choices do not change uploaded evidence intensities.",
            fidMaskSolventRegions: "Exclude solvent and water windows while detecting FID-derived peaks.",
            nmr2dFile: "Processed COSY, HSQC/HMQC, or HMBC peak table. Raw 2D FID/SER processing is deferred.",
            nmr2dExperiment: "Choose a 2D experiment type or let the parser infer it from the file and axis ranges.",
            deptAptFile: "Processed DEPT/APT peak table in CSV, TSV, or JSON format.",
            deptAptExperiment: "Choose DEPT-90, DEPT-135, or APT, or let the parser infer the experiment.",
            deptAptPositive: "APT sign conventions vary; choose the convention used during processing.",
            reportAnalysisId: "Analysis ID used to open or generate evidence reports.",
          };
          Object.entries(byId).forEach(([id, title]) => {
            const node = el(id);
            if (node && !node.title) node.title = title;
          });
          const byOnclick = {
            "validateInput()": "Validate SMILES, NMR text, solvent context, and proton counts before analysis.",
            "analyzeInput()": "Run the final text-based NMR consistency analysis.",
            "submitJob()": "Submit the current validated input as an asynchronous job.",
            "previewSpectrum()": "Build an interactive preview from the uploaded processed spectrum.",
            "analyzeSpectrum()": "Analyze the uploaded processed spectrum using the reviewed peak list.",
            "useSpectrumPeaks()": "Copy the reviewed processed-spectrum peaks into the main NMR text field.",
            "uploadRawFidArchive()": "Hash, inspect, and lock the selected raw FID archive in the immutable vault.",
            "previewRawFid()": "Preview from the locked raw archive without creating a permanent processing run.",
            "analyzeRawFid()": "Create a new derived processing run from the locked archive and save the recipe.",
            "exportRawFidPackage()": "Download a non-destructive package with the raw archive, recipe, evidence files, audit trail, and manifest hashes.",
            "previewDeptApt()": "Parse a processed DEPT/APT peak table without changing ¹³C or 2D inputs.",
            "analyzeDeptApt()": "Cross-check processed DEPT/APT carbon-type evidence against the read-only ¹³C text.",
            "previewNMR2D()": "Parse a processed 2D NMR peak table without creating a saved run.",
            "analyzeNMR2D()": "Score processed 2D correlations with optional DEPT/APT context without mutating 1D inputs.",
            "previewNmr2d()": "Parse a processed 2D NMR peak table without creating a saved run.",
            "analyzeNmr2d()": "Score processed 2D correlations with optional DEPT/APT context without mutating 1D inputs.",
            "saveNmr2dRun()": "Score processed 2D correlations and save a pending-review 2D run.",
            "exportNmr2dEvidence()": "Export the latest 2D preview and analysis to a local JSON evidence package.",
            "previewRawNmr2dStub()": "Show the guarded raw 2D status. Raw FID/SER production processing is not enabled in this release.",
            "loadHistory()": "Reload recent saved analyses.",
            "loadReviews()": "Reload the admin review queue.",
            "loadProjects()": "Reload workspace projects.",
            "generateReportFromCurrentLatestAnalysis()": "Create a versioned evidence report from the selected or latest analysis.",
            "useLatestAnalysisReport()": "Open the latest known analysis report in Workspaces.",
          };
          document.querySelectorAll("button[onclick]").forEach((button) => {
            const key = button.getAttribute("onclick") || "";
            if (byOnclick[key] && !button.title) button.title = byOnclick[key];
          });
        }

        function showSection(name) {
          ["dashboard","analyze","workspaces","jobs","history","reviews","admin"].forEach((section) => {
            const active = section === name;
            el(`section-${section}`)?.classList.toggle("active", active);
            el(`nav-${section}`)?.classList.toggle("active", active);
          });
        }

        function setAnalysisInputMethod(method) {
          const next = ["paste", "processed", "fid"].includes(method) ? method : "paste";
          state.analysisInputMethod = next;
          if (el("analysisInputMethod")) el("analysisInputMethod").value = next;
          el("manualNmrInputPanel")?.classList.toggle("hidden", next !== "paste");
          el("processedSpectrumPanel")?.classList.toggle("hidden", next !== "processed");
          el("rawFidPanel")?.classList.toggle("hidden", next !== "fid");
          const hint = el("analysisInputMethodHint");
          if (hint) {
            hint.textContent = next === "processed"
              ? "Upload a processed spectrum as CSV, TSV, TXT, JCAMP, JDX, DX, XY, ASC, or DAT."
              : (next === "fid"
                ? "Upload a Bruker 1D archive containing fid and acqus, or a Varian/Agilent archive containing fid and procpar. The raw archive is hashed and kept immutable."
                : "Paste parseable ¹H NMR text with shifts, multiplicities, and integrations.");
          }
        }

        function setCarbon13InputMethod(method) {
          const next = ["text", "processed", "fid"].includes(method) ? method : "text";
          state.carbon13InputMethod = next;
          if (el("carbon13InputMethod")) el("carbon13InputMethod").value = next;
          el("carbon13TextPanel")?.classList.toggle("hidden", next !== "text");
          el("carbon13ProcessedPanel")?.classList.toggle("hidden", next !== "processed");
          el("carbon13FidPanel")?.classList.toggle("hidden", next !== "fid");
          const hint = el("carbon13InputMethodHint");
          if (hint) {
            hint.textContent = next === "processed"
              ? "Upload a processed ¹³C spectrum trace, peak table, or simple JCAMP-DX export."
              : (next === "fid"
                ? "Upload a zipped or tarred Bruker/Varian 1D raw ¹³C FID dataset; the raw archive is hashed and kept immutable."
                : "Paste parseable ¹³C NMR text with discrete carbon shifts.");
          }
        }

        function showAppShell() {
          el("authScreen").classList.add("hidden");
          el("appShell").classList.remove("hidden");
        }

        function showAuthScreen() {
          el("authScreen").classList.remove("hidden");
          el("appShell").classList.add("hidden");
        }

        function updateRoleUI() {
          const isAdmin = Boolean(state.me && state.me.is_admin);
          el("roleBadge").textContent = isAdmin ? "Admin" : "User";
          el("roleBadge").className = `status-badge ${isAdmin ? "ok" : "warn"}`;
          el("sessionIdentity").textContent = state.me ? (state.me.email || "Signed in") : "Not loaded";
          el("nav-reviews").classList.toggle("hidden", !isAdmin);
          el("nav-admin").classList.toggle("hidden", !isAdmin);
        }

        async function api(path, options={}, auth=true) {
          const headers = new Headers(options.headers || {});
          if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
            headers.set("Content-Type", "application/json");
          }
          if (auth && state.token) headers.set("Authorization", `Bearer ${state.token}`);
          const response = await fetch(path, { ...options, headers });
          const text = await response.text();
          let data;
          try { data = text ? JSON.parse(text) : {}; } catch { data = text; }
          if (!response.ok) {
            const detail = data && data.detail ? data.detail : `HTTP ${response.status}`;
            if (auth && response.status === 401) {
              clearUserSessionState({ resetInputs: true });
              persistToken("");
              showAuthScreen();
              updateRoleUI();
              setAuthMessage("Your session expired. Sign in again.", false);
            }
            throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
          }
          return data;
        }

        const fallbackFidPresets = [
	          { id: "baseline_preserve", label: "Baseline preserve", description: "Preserves the Fourier-transformed FID evidence trace with no baseline correction, then reports baseline flatness for review.", settings: { zero_fill_factor: 2, apodization_mode: "none", line_broadening_hz: 0.0, peak_sensitivity: 0.1, apply_group_delay: true, auto_phase: true, phase_mode: "auto", phase_p0: 0.0, phase_p1: 0.0, auto_baseline: false, baseline_correction: "preserve", baseline_order: 3, mask_solvent_regions: true } },
	          { id: "balanced", label: "Balanced", description: "Conservative default for routine Bruker or Varian/Agilent 1D FID review with auto phasing and Bernstein order-3 baseline correction.", settings: { zero_fill_factor: 2, apodization_mode: "exponential", line_broadening_hz: 0.3, peak_sensitivity: 0.12, apply_group_delay: true, auto_phase: true, phase_mode: "auto", phase_p0: 0.0, phase_p1: 0.0, auto_baseline: true, baseline_correction: "bernstein", baseline_order: 3, mask_solvent_regions: true } },
	          { id: "sensitive_weak_peaks", label: "Sensitive weak peaks", description: "Adds mild apodization and lower peak threshold for weak signals with auto phasing and Bernstein baseline correction.", settings: { zero_fill_factor: 2, apodization_mode: "exponential", line_broadening_hz: 0.7, peak_sensitivity: 0.06, apply_group_delay: true, auto_phase: true, phase_mode: "auto", phase_p0: 0.0, phase_p1: 0.0, auto_baseline: true, baseline_correction: "bernstein", baseline_order: 3, mask_solvent_regions: true } },
	          { id: "higher_resolution", label: "Higher resolution", description: "Uses more zero filling and minimal line broadening for tighter peak shape with auto phasing and Bernstein baseline correction.", settings: { zero_fill_factor: 4, apodization_mode: "exponential", line_broadening_hz: 0.05, peak_sensitivity: 0.1, apply_group_delay: true, auto_phase: true, phase_mode: "auto", phase_p0: 0.0, phase_p1: 0.0, auto_baseline: true, baseline_correction: "bernstein", baseline_order: 3, mask_solvent_regions: true } },
          { id: "custom", label: "Custom", description: "Preserves manually selected processing controls.", settings: {} },
        ];

        function getFidPreset(presetId) {
          const presets = state.fidPresets.length ? state.fidPresets : fallbackFidPresets;
          return presets.find((preset) => preset.id === presetId) || presets[0] || fallbackFidPresets[0];
        }

        function renderFidPresetOptions() {
          const select = el("fidProcessingPreset");
          const presets = state.fidPresets.length ? state.fidPresets : fallbackFidPresets;
          if (select) {
            const current = select.value || "balanced";
            select.innerHTML = presets.map((preset) => `<option value="${escapeHtml(preset.id)}">${escapeHtml(preset.label)}</option>`).join("");
            select.value = presets.some((preset) => preset.id === current) ? current : "balanced";
            applyFidProcessingPreset(select.value, { updateControls: false });
          }
          const carbon13Select = el("carbon13FidProcessingPreset");
          if (carbon13Select) {
            const currentCarbon13 = carbon13Select.value || "balanced";
            carbon13Select.innerHTML = presets.map((preset) => `<option value="${escapeHtml(preset.id)}">${escapeHtml(preset.label)}</option>`).join("");
            carbon13Select.value = presets.some((preset) => preset.id === currentCarbon13) ? currentCarbon13 : "balanced";
          }
        }

        function setFidControlValue(id, value) {
          const control = el(id);
          if (!control || value === undefined || value === null) return;
          control.value = String(value);
        }

        function setFidCheckboxValue(id, value) {
          const control = el(id);
          if (!control || value === undefined || value === null) return;
          control.checked = Boolean(value);
        }

        function applyFidProcessingPreset(presetId, options={}) {
          const preset = getFidPreset(presetId);
          const select = el("fidProcessingPreset");
          if (select) select.value = preset.id;
          const description = el("fidPresetDescription");
          if (description) description.textContent = preset.description || "";
          if (preset.id === "custom" || options.updateControls === false) return;
	          const settings = preset.settings || {};
	          state.fidPresetApplying = true;
	          setFidControlValue("fidZeroFillFactor", settings.zero_fill_factor);
	          setFidControlValue("fidApodizationMode", settings.apodization_mode || (settings.line_broadening_hz > 0 ? "exponential" : "none"));
	          setFidControlValue("fidLineBroadeningHz", settings.line_broadening_hz);
          setFidControlValue("fidPeakSensitivity", settings.peak_sensitivity);
          setFidControlValue("fidPhaseMode", settings.phase_mode || (settings.auto_phase === false ? "none" : "auto"));
          setFidControlValue("fidPhaseP0", settings.phase_p0 ?? 0.0);
          setFidControlValue("fidPhaseP1", settings.phase_p1 ?? 0.0);
          setFidControlValue("fidBaselineCorrection", settings.baseline_correction || (settings.auto_baseline === false ? "preserve" : "bernstein"));
          setFidControlValue("fidBaselineOrder", settings.baseline_order ?? 3);
          setFidControlValue("fidDisplayMode", settings.display_mode || "real");
          setFidCheckboxValue("fidApplyGroupDelay", settings.apply_group_delay);
          setFidCheckboxValue("fidMaskSolventRegions", settings.mask_solvent_regions);
          state.fidPresetApplying = false;
        }

        function applyCarbon13FidProcessingPreset(presetId) {
          const preset = getFidPreset(presetId);
          const select = el("carbon13FidProcessingPreset");
          if (select) select.value = preset.id;
          if (preset.id === "custom") return;
	          const settings = preset.settings || {};
	          setFidControlValue("carbon13FidZeroFillFactor", settings.zero_fill_factor);
	          setFidControlValue("carbon13FidApodizationMode", settings.apodization_mode || (settings.line_broadening_hz > 0 ? "exponential" : "none"));
	          setFidControlValue("carbon13FidLineBroadeningHz", settings.line_broadening_hz);
          setFidControlValue("carbon13FidPeakSensitivity", settings.peak_sensitivity);
          setFidControlValue("carbon13FidPhaseMode", settings.phase_mode || (settings.auto_phase === false ? "none" : "auto"));
          setFidControlValue("carbon13FidPhaseP0", settings.phase_p0 ?? 0.0);
          setFidControlValue("carbon13FidPhaseP1", settings.phase_p1 ?? 0.0);
          setFidControlValue("carbon13FidBaselineCorrection", settings.baseline_correction || (settings.auto_baseline === false ? "preserve" : "bernstein"));
          setFidControlValue("carbon13FidBaselineOrder", settings.baseline_order ?? 3);
          setFidControlValue("carbon13FidDisplayMode", settings.display_mode || "real");
          setFidCheckboxValue("carbon13FidApplyGroupDelay", settings.apply_group_delay);
          setFidCheckboxValue("carbon13FidMaskSolventRegions", settings.mask_solvent_regions);
        }

        function markFidPresetCustom() {
          if (state.fidPresetApplying) return;
          const select = el("fidProcessingPreset");
          if (!select || select.value === "custom") return;
          select.value = "custom";
          applyFidProcessingPreset("custom", { updateControls: false });
        }

        function markCarbon13FidPresetCustom() {
          const select = el("carbon13FidProcessingPreset");
          if (!select || select.value === "custom") return;
          select.value = "custom";
        }

        function installFidPresetControlHandlers() {
          ["fidZeroFillFactor", "fidLineBroadeningHz", "fidPeakSensitivity", "fidPhaseP0", "fidPhaseP1", "fidBaselineOrder"].forEach((id) => {
            el(id)?.addEventListener("input", markFidPresetCustom);
          });
	          ["fidApplyGroupDelay", "fidApodizationMode", "fidPhaseMode", "fidBaselineCorrection", "fidDisplayMode", "fidMaskSolventRegions"].forEach((id) => {
	            el(id)?.addEventListener("change", markFidPresetCustom);
	          });
          ["carbon13FidZeroFillFactor", "carbon13FidLineBroadeningHz", "carbon13FidPeakSensitivity", "carbon13FidPhaseP0", "carbon13FidPhaseP1", "carbon13FidBaselineOrder"].forEach((id) => {
            el(id)?.addEventListener("input", markCarbon13FidPresetCustom);
          });
	          ["carbon13FidApplyGroupDelay", "carbon13FidApodizationMode", "carbon13FidPhaseMode", "carbon13FidBaselineCorrection", "carbon13FidDisplayMode", "carbon13FidMaskSolventRegions"].forEach((id) => {
	            el(id)?.addEventListener("change", markCarbon13FidPresetCustom);
	          });
        }

        async function loadFidPresets() {
          try {
            const data = await api("/fid/presets", { method: "GET" }, false);
            state.fidPresets = Array.isArray(data) && data.length ? data : fallbackFidPresets;
          } catch (_) {
            state.fidPresets = fallbackFidPresets;
          }
          renderFidPresetOptions();
        }

        function payload() {
          return {
            sample_id: el("sampleId").value.trim() || null,
            smiles: el("smiles").value.trim(),
            solvent: el("solvent").value || null,
            nmr_text: el("nmrText").value.trim(),
          };
        }

        function setFieldState(id, validity) {
          const node = el(id);
          node.classList.remove("valid", "invalid");
          if (validity === true) node.classList.add("valid");
          if (validity === false) node.classList.add("invalid");
        }

        function clearValidationState() {
          state.validationOk = false;
          setValidationBadge("Not validated", "warn");
          el("analyzeBtn").disabled = true;
          ["smiles","nmrText","solvent"].forEach((id) => el(id).classList.remove("valid", "invalid"));
          el("validationSummary").innerHTML = '<strong>Validation summary</strong><p class="muted small">Run validation before analysis.</p>';
        }

        function resetSpectrumPreviewState() {
          document.querySelectorAll(".spectrum-plot").forEach((plotTarget) => {
            if (plotTarget && window.Plotly) {
              try { window.Plotly.purge(plotTarget); } catch (_) {}
            }
          });
          state.latestSpectrumPreview = null;
          state.latestRawFidPreview = null;
	          state.rawFidArchive = null;
          state.latestCarbon13Preview = null;
          state.latestCarbon13SpectrumPreview = null;
          state.latestDeptAptPreview = null;
          state.latestDeptAptReport = null;
          state.latestNmr2dPreview = null;
          state.latestNmr2dReport = null;
          state.latestNmr2dSavedRunId = null;
          state.latestCandidateComparison = null;
          state.latestSpectralSimilarity = null;
          state.latestPredictedNMRMatch = null;
          state.latestHRMSMatch = null;
          state.latestHRMSFormulaSearch = null;
          state.latestAdductInference = null;
          state.latestMSMSAnnotation = null;
          state.latestFragmentationTree = null;
          state.fidRuns = [];
          state.selectedFidRunIds = [];
          state.latestSpectrumPlotId = "spectrumInteractivePlot";
          state.spectrumPreviewContexts = {};
          state.latestSpectrumPreviewSignature = "";
          state.latestSpectrumXRange = null;
          state.spectrumVerticalScale = 1;
          state.spectrumLabelThreshold = 0.12;
          state.spectrumShowPeaks = true;
          state.spectrumTraceMode = "review";
          state.spectrumTraceModes = {};
          state.spectrumDragMode = "pan";
          state.spectrumPeakDecisions = {};
          state.selectedSpectrumMarker = null;
          const previewBox = el("spectrumPreviewBox");
          if (previewBox) previewBox.innerHTML = 'No processed spectrum preview yet.';
	          const fidPreviewBox = el("fidPreviewBox");
	          if (fidPreviewBox) fidPreviewBox.innerHTML = 'No raw FID preview yet.';
	          renderRawFidVaultStatus(null);
	          if (el("fidExportStatus")) el("fidExportStatus").textContent = "Export package includes manifest.json with SHA-256 hashes for the original archive and derived evidence files.";
          if (el("fidRunHistoryBox")) el("fidRunHistoryBox").innerHTML = 'No FID runs loaded yet.';
          if (el("fidRunCompareBox")) el("fidRunCompareBox").innerHTML = '';
          renderFidRunSelectionBadge();
        }

        function clearAnalysisWorkspace() {
          clearValidationState();
          resetSpectrumPreviewState();
          state.workspaceSeedAnalysisId = null;
          state.workspaceSeedSnapshot = null;
          if (el("workspaceSeedNote")) el("workspaceSeedNote").textContent = "Use the current analysis inputs or send a history record into Workspaces to save it as a sample.";
          setResultBadge("No analysis yet", "warn");
          const output = el("readableOutput");
          if (output) output.innerHTML = 'No output yet.';
          const spectrumFile = el("spectrumFile");
          if (spectrumFile) spectrumFile.value = '';
          const fidFile = el("fidFile");
          if (fidFile) fidFile.value = '';
          const carbon13File = el("carbon13File");
          if (carbon13File) carbon13File.value = '';
          const carbon13SpectrumFile = el("carbon13SpectrumFile");
          if (carbon13SpectrumFile) carbon13SpectrumFile.value = '';
          const carbon13FidFile = el("carbon13FidFile");
          if (carbon13FidFile) carbon13FidFile.value = '';
          const nmr2dFile = el("nmr2dFile");
          if (nmr2dFile) nmr2dFile.value = '';
          const referenceText = el("referenceNmrText");
          if (referenceText) referenceText.value = '';
          const referencePpm = el("referencePPM");
          if (referencePpm && !referencePpm.value) referencePpm.value = '0.00';
          state.latestCarbon13Preview = null;
          state.latestCarbon13SpectrumPreview = null;
          if (el("protonEvidenceBox")) el("protonEvidenceBox").innerHTML = '<strong>¹H evidence</strong><p class="muted small">Run ¹H evidence scoring to classify peaks, solvent/water hits, and proton-count consistency.</p>';
          if (el("carbon13Box")) el("carbon13Box").innerHTML = 'No ¹³C result yet.';
          if (el("nmr2dBox")) el("nmr2dBox").innerHTML = 'No 2D NMR result yet.';
          if (el("nmr2dReviewBox")) el("nmr2dReviewBox").innerHTML = '<strong>Review</strong><div class="muted small" style="margin-top:.35rem;">2D NMR evidence is supportive connectivity evidence and requires human review.</div>';
          syncNmr2dContext();
          setJson({ detail: "Analysis workspace cleared." });
        }

        function captureAnalysisFormDefaults() {
          state.defaultFormValues = {
            sampleId: el("sampleId")?.value || "",
            jobName: el("jobName")?.value || "",
            solvent: el("solvent")?.value || "",
            queueName: el("queueName")?.value || "analyze",
            analysisInputMethod: el("analysisInputMethod")?.value || "paste",
            carbon13InputMethod: el("carbon13InputMethod")?.value || "text",
            carbon13Text: el("carbon13Text")?.value || "",
            carbon13PeakSensitivity: el("carbon13PeakSensitivity")?.value || "",
            carbon13ProcessedDisplayMode: el("carbon13ProcessedDisplayMode")?.value || "real",
            carbon13FidReferencePPM: el("carbon13FidReferencePPM")?.value || "77.0",
	            carbon13FidProcessingPreset: el("carbon13FidProcessingPreset")?.value || "balanced",
	            carbon13FidPeakSensitivity: el("carbon13FidPeakSensitivity")?.value || "",
	            carbon13FidZeroFillFactor: el("carbon13FidZeroFillFactor")?.value || "2",
	            carbon13FidApodizationMode: el("carbon13FidApodizationMode")?.value || "exponential",
	            carbon13FidLineBroadeningHz: el("carbon13FidLineBroadeningHz")?.value || "0.3",
            carbon13FidApplyGroupDelay: Boolean(el("carbon13FidApplyGroupDelay")?.checked),
            carbon13FidPhaseMode: el("carbon13FidPhaseMode")?.value || "auto",
            carbon13FidPhaseP0: el("carbon13FidPhaseP0")?.value || "0.0",
            carbon13FidPhaseP1: el("carbon13FidPhaseP1")?.value || "0.0",
            carbon13FidBaselineCorrection: el("carbon13FidBaselineCorrection")?.value || "bernstein",
            carbon13FidBaselineOrder: el("carbon13FidBaselineOrder")?.value || "3",
            carbon13FidDisplayMode: el("carbon13FidDisplayMode")?.value || "real",
            carbon13FidMaskSolventRegions: Boolean(el("carbon13FidMaskSolventRegions")?.checked),
            smiles: el("smiles")?.value || "",
            nmrText: el("nmrText")?.value || "",
            frequencyMHz: el("frequencyMHz")?.value || "",
            referencePPM: el("referencePPM")?.value || "",
            referenceNmrText: el("referenceNmrText")?.value || "",
            maskSolventRegions: Boolean(el("maskSolventRegions")?.checked),
            processedDisplayMode: el("processedDisplayMode")?.value || "real",
            processedBaselineCorrection: el("processedBaselineCorrection")?.value || "bernstein",
            processedBaselineOrder: el("processedBaselineOrder")?.value || "3",
            carbon13ProcessedBaselineCorrection: el("carbon13ProcessedBaselineCorrection")?.value || "bernstein",
            carbon13ProcessedBaselineOrder: el("carbon13ProcessedBaselineOrder")?.value || "3",
            fidProcessingPreset: el("fidProcessingPreset")?.value || "balanced",
            fidSolvent: el("fidSolvent")?.value || "",
	            fidNucleus: el("fidNucleus")?.value || "1H",
	            fidReferencePPM: el("fidReferencePPM")?.value || "",
	            fidZeroFillFactor: el("fidZeroFillFactor")?.value || "2",
	            fidApodizationMode: el("fidApodizationMode")?.value || "exponential",
	            fidLineBroadeningHz: el("fidLineBroadeningHz")?.value || "0.3",
            fidPeakSensitivity: el("fidPeakSensitivity")?.value || "",
            fidApplyGroupDelay: Boolean(el("fidApplyGroupDelay")?.checked),
            fidPhaseMode: el("fidPhaseMode")?.value || "auto",
            fidPhaseP0: el("fidPhaseP0")?.value || "0.0",
            fidPhaseP1: el("fidPhaseP1")?.value || "0.0",
            fidBaselineCorrection: el("fidBaselineCorrection")?.value || "bernstein",
            fidBaselineOrder: el("fidBaselineOrder")?.value || "3",
            fidDisplayMode: el("fidDisplayMode")?.value || "real",
            fidMaskSolventRegions: Boolean(el("fidMaskSolventRegions")?.checked),
          };
        }

        function resetAnalysisInputsToDefaults() {
          const defaults = state.defaultFormValues || {};
          if (el("sampleId")) el("sampleId").value = defaults.sampleId || "";
          if (el("jobName")) el("jobName").value = defaults.jobName || "";
          if (el("solvent")) el("solvent").value = defaults.solvent || "";
          if (el("queueName")) el("queueName").value = defaults.queueName || "analyze";
          setAnalysisInputMethod(defaults.analysisInputMethod || "paste");
          setCarbon13InputMethod(defaults.carbon13InputMethod || "text");
          if (el("smiles")) el("smiles").value = defaults.smiles || "";
          if (el("nmrText")) el("nmrText").value = defaults.nmrText || "";
          if (el("carbon13Text")) el("carbon13Text").value = defaults.carbon13Text || "";
          if (el("carbon13SpectrumFile")) el("carbon13SpectrumFile").value = "";
          if (el("carbon13FidFile")) el("carbon13FidFile").value = "";
          if (el("carbon13PeakSensitivity")) el("carbon13PeakSensitivity").value = defaults.carbon13PeakSensitivity || "";
          if (el("carbon13ProcessedDisplayMode")) el("carbon13ProcessedDisplayMode").value = defaults.carbon13ProcessedDisplayMode || "real";
          if (el("carbon13FidReferencePPM")) el("carbon13FidReferencePPM").value = defaults.carbon13FidReferencePPM || "77.0";
	          if (el("carbon13FidProcessingPreset")) el("carbon13FidProcessingPreset").value = defaults.carbon13FidProcessingPreset || "balanced";
	          if (el("carbon13FidPeakSensitivity")) el("carbon13FidPeakSensitivity").value = defaults.carbon13FidPeakSensitivity || "";
	          if (el("carbon13FidZeroFillFactor")) el("carbon13FidZeroFillFactor").value = defaults.carbon13FidZeroFillFactor || "2";
	          if (el("carbon13FidApodizationMode")) el("carbon13FidApodizationMode").value = defaults.carbon13FidApodizationMode || "exponential";
	          if (el("carbon13FidLineBroadeningHz")) el("carbon13FidLineBroadeningHz").value = defaults.carbon13FidLineBroadeningHz || "0.3";
          if (el("carbon13FidApplyGroupDelay")) el("carbon13FidApplyGroupDelay").checked = Boolean(defaults.carbon13FidApplyGroupDelay);
          if (el("carbon13FidPhaseMode")) el("carbon13FidPhaseMode").value = defaults.carbon13FidPhaseMode || "auto";
          if (el("carbon13FidPhaseP0")) el("carbon13FidPhaseP0").value = defaults.carbon13FidPhaseP0 || "0.0";
          if (el("carbon13FidPhaseP1")) el("carbon13FidPhaseP1").value = defaults.carbon13FidPhaseP1 || "0.0";
          if (el("carbon13FidBaselineCorrection")) el("carbon13FidBaselineCorrection").value = defaults.carbon13FidBaselineCorrection || "bernstein";
          if (el("carbon13FidBaselineOrder")) el("carbon13FidBaselineOrder").value = defaults.carbon13FidBaselineOrder || "3";
          if (el("carbon13FidDisplayMode")) el("carbon13FidDisplayMode").value = defaults.carbon13FidDisplayMode || "real";
          if (el("carbon13FidMaskSolventRegions")) el("carbon13FidMaskSolventRegions").checked = Boolean(defaults.carbon13FidMaskSolventRegions);
          if (el("frequencyMHz")) el("frequencyMHz").value = defaults.frequencyMHz || "";
          if (el("referencePPM")) el("referencePPM").value = defaults.referencePPM || "";
          if (el("referenceNmrText")) el("referenceNmrText").value = defaults.referenceNmrText || "";
          if (el("maskSolventRegions")) {
            el("maskSolventRegions").checked = Boolean(defaults.maskSolventRegions);
            el("maskSolventRegions").dataset.userChanged = "false";
          }
          if (el("spectrumFile")) el("spectrumFile").value = "";
          if (el("processedDisplayMode")) el("processedDisplayMode").value = defaults.processedDisplayMode || "real";
          if (el("processedBaselineCorrection")) el("processedBaselineCorrection").value = defaults.processedBaselineCorrection || "bernstein";
          if (el("processedBaselineOrder")) el("processedBaselineOrder").value = defaults.processedBaselineOrder || "3";
          if (el("carbon13ProcessedBaselineCorrection")) el("carbon13ProcessedBaselineCorrection").value = defaults.carbon13ProcessedBaselineCorrection || "bernstein";
          if (el("carbon13ProcessedBaselineOrder")) el("carbon13ProcessedBaselineOrder").value = defaults.carbon13ProcessedBaselineOrder || "3";
          if (el("fidFile")) el("fidFile").value = "";
          if (el("fidProcessingPreset")) {
            el("fidProcessingPreset").value = defaults.fidProcessingPreset || "balanced";
            applyFidProcessingPreset(el("fidProcessingPreset").value, { updateControls: false });
          }
          if (el("fidSolvent")) el("fidSolvent").value = defaults.fidSolvent || defaults.solvent || "";
	          if (el("fidNucleus")) el("fidNucleus").value = defaults.fidNucleus || "1H";
	          if (el("fidReferencePPM")) el("fidReferencePPM").value = defaults.fidReferencePPM || "";
	          if (el("fidZeroFillFactor")) el("fidZeroFillFactor").value = defaults.fidZeroFillFactor || "2";
	          if (el("fidApodizationMode")) el("fidApodizationMode").value = defaults.fidApodizationMode || "exponential";
	          if (el("fidLineBroadeningHz")) el("fidLineBroadeningHz").value = defaults.fidLineBroadeningHz || "0.3";
          if (el("fidPeakSensitivity")) el("fidPeakSensitivity").value = defaults.fidPeakSensitivity || "";
          if (el("fidApplyGroupDelay")) el("fidApplyGroupDelay").checked = Boolean(defaults.fidApplyGroupDelay);
          if (el("fidPhaseMode")) el("fidPhaseMode").value = defaults.fidPhaseMode || "auto";
          if (el("fidPhaseP0")) el("fidPhaseP0").value = defaults.fidPhaseP0 || "0.0";
          if (el("fidPhaseP1")) el("fidPhaseP1").value = defaults.fidPhaseP1 || "0.0";
          if (el("fidBaselineCorrection")) el("fidBaselineCorrection").value = defaults.fidBaselineCorrection || "bernstein";
          if (el("fidBaselineOrder")) el("fidBaselineOrder").value = defaults.fidBaselineOrder || "3";
          if (el("fidDisplayMode")) el("fidDisplayMode").value = defaults.fidDisplayMode || "real";
          if (el("fidMaskSolventRegions")) el("fidMaskSolventRegions").checked = Boolean(defaults.fidMaskSolventRegions);
          if (el("uploadFile")) el("uploadFile").value = "";
        }

        function renderWorkspaceStatusBadge(text, variantClass="warn") {
          const badge = el("workspaceStatusBadge");
          if (!badge) return;
          badge.className = `status-badge ${variantClass}`;
          badge.textContent = text;
        }

        function updateLatestAnalysisBadge() {
          const badge = el("latestAnalysisBadge");
          if (!badge) return;
          if (state.latestAnalysisId) {
            badge.className = "status-badge ok";
            badge.textContent = `Latest analysis #${state.latestAnalysisId}`;
          } else {
            badge.className = "status-badge warn";
            badge.textContent = "No latest analysis";
          }
        }

        function getReportAnalysisInputValue() {
          return (el("reportAnalysisId")?.value || el("workspaceAnalysisId")?.value || "").trim();
        }

        function setReportAnalysisInputValue(value, { overwrite = true } = {}) {
          const nextValue = value === null || value === undefined ? "" : String(value);
          ["reportAnalysisId","workspaceAnalysisId"].forEach((id) => {
            const input = el(id);
            if (!input) return;
            if (overwrite || !input.value.trim()) input.value = nextValue;
          });
        }

        function setLatestAnalysisId(analysisId) {
          const parsed = Number(analysisId);
          if (!Number.isFinite(parsed) || parsed <= 0) return null;
          state.latestAnalysisId = parsed;
          setReportAnalysisInputValue(parsed, { overwrite: false });
          updateLatestAnalysisBadge();
          return parsed;
        }

        function getLatestAvailableAnalysisId() {
          const candidates = [
            state.latestAnalysisId,
            state.workspaceSeedAnalysisId,
            getReportAnalysisInputValue(),
          ];
          for (const candidate of candidates) {
            const parsed = Number(candidate);
            if (Number.isFinite(parsed) && parsed > 0) return parsed;
          }
          return null;
        }

        function getReportAnalysisIdOrLatest() {
          const reportAnalysisId = Number(getReportAnalysisInputValue());
          if (Number.isFinite(reportAnalysisId) && reportAnalysisId > 0) return reportAnalysisId;
          return getLatestAvailableAnalysisId();
        }

        function resetWorkspaceState() {
          state.historyItems = [];
          state.latestAnalysisId = null;
          state.workspaceProjects = [];
          state.selectedProjectId = null;
          state.workspaceSamples = [];
          state.workspaceProjectDashboard = null;
          state.selectedWorkspaceSampleId = null;
          state.selectedWorkspaceSample = null;
          state.workspaceSampleDetail = null;
          state.workspaceSampleComparison = null;
          state.workspaceSampleReports = null;
          state.workspaceSeedAnalysisId = null;
          state.workspaceSeedSnapshot = null;
          state.loadedEvidenceReport = null;
          state.workspaceSampleReport = null;
          state.workspaceTimeline = { analysisId: null, decisions: [], auditEvents: [] };
          if (el("workspaceProjectName")) el("workspaceProjectName").value = "";
          if (el("workspaceProjectDescription")) el("workspaceProjectDescription").value = "";
          setReportAnalysisInputValue("");
          if (el("workspaceProjectsBox")) el("workspaceProjectsBox").innerHTML = "No projects loaded yet.";
          if (el("workspaceSamplesBox")) el("workspaceSamplesBox").innerHTML = "No samples loaded yet.";
          if (el("workspaceSelectionBox")) el("workspaceSelectionBox").innerHTML = "No project selected yet.";
          if (el("workspaceSeedNote")) el("workspaceSeedNote").textContent = "Use the current analysis inputs or send a history record into Workspaces to save it as a sample.";
          if (el("workspaceReportBox")) el("workspaceReportBox").innerHTML = "No report loaded yet.";
          if (el("workspaceProjectDashboardBox")) el("workspaceProjectDashboardBox").innerHTML = "No project selected yet.";
          if (el("workspaceSampleBadge")) {
            el("workspaceSampleBadge").className = "status-badge warn";
            el("workspaceSampleBadge").textContent = "No sample opened";
          }
          if (el("workspaceSampleDetailBox")) el("workspaceSampleDetailBox").innerHTML = "No sample opened yet.";
          if (el("workspaceComparisonBox")) el("workspaceComparisonBox").innerHTML = "No sample opened yet.";
          renderReviewerTimeline(null, [], []);
          renderWorkspaceStatusBadge("No project selected", "warn");
          updateLatestAnalysisBadge();
        }

        function updateWorkspaceSelectionBox() {
          const selected = state.workspaceProjects.find((project) => project.id === state.selectedProjectId) || null;
          if (el("workspaceSelectionBox")) {
            el("workspaceSelectionBox").innerHTML = selected
              ? `<strong>${escapeHtml(selected.name)}</strong><div class="muted small">Samples: ${escapeHtml(selected.sample_count ?? 0)} · Analyses: ${escapeHtml(selected.analysis_count ?? 0)} · Owner #${escapeHtml(selected.user_id ?? "—")}</div>`
              : "No project selected yet.";
          }
          renderWorkspaceStatusBadge(selected ? `Project: ${selected.name}` : "No project selected", selected ? "ok" : "warn");
          renderWorkspaceProjectDashboard();
        }

        function buildWorkspaceSeedSnapshot(record) {
          return record ? {
            sample_id: record.sample_id || null,
            smiles: record.smiles || "",
            solvent: record.solvent || null,
            nmr_text: record.nmr_text || "",
          } : null;
        }

        function getCurrentAnalysisInputsForWorkspace() {
          return payload();
        }

        function getLinkedWorkspaceAnalysisId() {
          if (!state.workspaceSeedAnalysisId || !state.workspaceSeedSnapshot) return null;
          const current = getCurrentAnalysisInputsForWorkspace();
          const seeded = state.workspaceSeedSnapshot;
          return (
            current.sample_id === seeded.sample_id
            && current.smiles === seeded.smiles
            && current.solvent === seeded.solvent
            && current.nmr_text === seeded.nmr_text
          ) ? state.workspaceSeedAnalysisId : null;
        }

        function clearUserSessionState({ resetInputs = false } = {}) {
          state.me = null;
          clearValidationState();
          resetSpectrumPreviewState();
          resetWorkspaceState();
          setResultBadge("No analysis yet", "warn");
          const output = el("readableOutput");
          if (output) output.innerHTML = 'No output yet.';
          if (resetInputs) resetAnalysisInputsToDefaults();
          if (el("historyBox")) el("historyBox").innerHTML = 'No history loaded yet.';
          if (el("jobsBox")) el("jobsBox").innerHTML = 'No jobs loaded yet.';
          if (el("queueStatusBox")) el("queueStatusBox").innerHTML = 'Queue status not loaded yet.';
          if (el("reviewQueue")) el("reviewQueue").innerHTML = 'No review data loaded yet.';
          if (el("adminUsers")) el("adminUsers").innerHTML = '';
          if (el("adminSystem")) el("adminSystem").innerHTML = '';
          if (el("auditPreview")) el("auditPreview").innerHTML = '';
          state.latestStructureReport = null;
          if (el("structureReportBox")) el("structureReportBox").innerHTML = 'No structure elucidation report yet.';
        }

        function buildPeakKey(peak) {
          if (!peak) return "";
          const shift = Number(peak.shift_ppm);
          const integration = Number(peak.integration_h);
          const jValues = Array.isArray(peak.j_values_hz)
            ? peak.j_values_hz.map((value) => Number(value)).filter((value) => Number.isFinite(value) && value > 0).map((value) => value.toFixed(1)).join("/")
            : "";
          return [
            Number.isFinite(shift) ? shift.toFixed(3) : String(peak.shift_ppm ?? ""),
            String(peak.multiplicity || "m").trim(),
            Number.isFinite(integration) ? integration.toFixed(1) : String(peak.integration_h ?? ""),
            jValues,
          ].join("|");
        }

        function getSpectrumPreviewSignature(data) {
          return JSON.stringify({
            filename: data?.filename || "",
            peakCount: Array.isArray(data?.inferred_peaks) ? data.inferred_peaks.length : 0,
            inferredText: data?.inferred_nmr_text || "",
            referenceText: data?.reference_nmr_text_normalized || "",
          });
        }

        function syncSpectrumReviewState(data) {
          const signature = getSpectrumPreviewSignature(data);
          const validKeys = new Set((Array.isArray(data?.inferred_peaks) ? data.inferred_peaks : []).map(buildPeakKey));
          if (signature !== state.latestSpectrumPreviewSignature) {
            state.latestSpectrumPreviewSignature = signature;
            state.spectrumPeakDecisions = {};
            state.spectrumDecisionUndoStack = [];
            state.selectedSpectrumMarker = null;
            state.spectrumTraceMode = "review";
            state.spectrumTraceModes = {};
            return;
          }
          state.spectrumPeakDecisions = Object.fromEntries(
            Object.entries(state.spectrumPeakDecisions || {}).filter(([peakKey]) => validKeys.has(peakKey))
          );
          if (state.selectedSpectrumMarker?.peakKey && !validKeys.has(state.selectedSpectrumMarker.peakKey)) {
            state.selectedSpectrumMarker = null;
          }
        }

        function getSpectrumPeakDecision(peakKey) {
          if (!peakKey) return "neutral";
          return state.spectrumPeakDecisions?.[peakKey] || "neutral";
        }

        function hasSpectrumManualReviewDecisions(data) {
          const peaks = Array.isArray(data?.inferred_peaks) ? data.inferred_peaks : [];
          return peaks.some((peak) => getSpectrumPeakDecision(buildPeakKey(peak)) !== "neutral");
        }

        function getSpectrumReviewedPeaks(data) {
          const peaks = Array.isArray(data?.inferred_peaks) ? data.inferred_peaks : [];
          return peaks.filter((peak) => getSpectrumPeakDecision(buildPeakKey(peak)) !== "excluded");
        }

        function buildSpectrumNmrTextFromPeaks(peaks) {
          if (!Array.isArray(peaks) || !peaks.length) return "";
          return peaks.map((peak) => formatSpectrumPeakSummary(peak)).join(", ");
        }

        function getSpectrumReviewedNmrText(data) {
          if (!hasSpectrumManualReviewDecisions(data)) {
            return String(data?.inferred_nmr_text || data?.metadata?.raw_extracted_nmr_text || "").trim();
          }
          return buildSpectrumNmrTextFromPeaks(getSpectrumReviewedPeaks(data));
        }

        function clearSpectrumPeakDecisions(plotId=null) {
          setActiveSpectrumPlot(plotId);
          pushSpectrumDecisionUndoState();
          state.spectrumPeakDecisions = {};
          rerenderSpectrumPreview(plotId);
        }

        function selectSpectrumMarker(markerPayload, plotId=null) {
          setActiveSpectrumPlot(plotId);
          state.selectedSpectrumMarker = markerPayload || null;
          rerenderSpectrumPreview(plotId);
        }

        function setSpectrumPeakDecision(decision, plotId=null) {
          setActiveSpectrumPlot(plotId);
          const selected = state.selectedSpectrumMarker;
          if (!selected?.peakKey) return;
          pushSpectrumDecisionUndoState();
          if (decision === "neutral") {
            delete state.spectrumPeakDecisions[selected.peakKey];
          } else {
            state.spectrumPeakDecisions[selected.peakKey] = decision;
          }
          rerenderSpectrumPreview(plotId);
        }

        function pushSpectrumDecisionUndoState() {
          const snapshot = {
            decisions: { ...(state.spectrumPeakDecisions || {}) },
            selected: state.selectedSpectrumMarker ? { ...state.selectedSpectrumMarker } : null,
          };
          state.spectrumDecisionUndoStack.push(snapshot);
          if (state.spectrumDecisionUndoStack.length > 50) state.spectrumDecisionUndoStack.shift();
        }

        function undoSpectrumPeakDecision(plotId=null) {
          setActiveSpectrumPlot(plotId);
          const snapshot = state.spectrumDecisionUndoStack.pop();
          if (!snapshot) {
            setJson({ detail: "No reviewer peak decision to undo." });
            return;
          }
          state.spectrumPeakDecisions = snapshot.decisions || {};
          state.selectedSpectrumMarker = snapshot.selected || null;
          rerenderSpectrumPreview(plotId);
        }

        function parseSpectrumMarkerPayload(markerPayload) {
          if (!markerPayload) return null;
          if (typeof markerPayload === 'string') {
            try {
              return JSON.parse(markerPayload);
            } catch (_) {
              return null;
            }
          }
          if (typeof markerPayload === 'object') {
            return markerPayload;
          }
          return null;
        }

        function getSpectrumClickPayload(point) {
          if (!point) return null;
          if (point.customdata !== undefined) return parseSpectrumMarkerPayload(point.customdata);
          const pointIndex = Number.isInteger(point.pointNumber) ? point.pointNumber : null;
          const traceCustomData = point?.data?.customdata;
          if (pointIndex !== null && Array.isArray(traceCustomData) && pointIndex < traceCustomData.length) {
            return parseSpectrumMarkerPayload(traceCustomData[pointIndex]);
          }
          return null;
        }

        function renderValidation(data) {
          const smilesProvided = Boolean(el("smiles").value.trim());
          const nmrProvided = Boolean(el("nmrText").value.trim());
          const structureValid = Boolean(data.structure_valid);
          const nmrValid = Boolean(data.nmr_text_valid);
          const structureNmrMatch = Boolean(data.structure_nmr_match);
          const analysisReady = Boolean(data.analysis_ready);
          const warnings = Array.isArray(data.warnings) ? data.warnings : [];
          const errors = Array.isArray(data.errors) ? data.errors : [];
          state.validationOk = analysisReady;

          setFieldState("smiles", smilesProvided ? structureValid : null);
          setFieldState("nmrText", nmrProvided ? nmrValid : null);
          const solventError = errors.some((e) => String(e).toLowerCase().includes("solvent"));
          const solventValue = el("solvent").value.trim();
          if (solventValue) {
            setFieldState("solvent", solventError ? false : true);
          } else {
            setFieldState("solvent", null);
          }

          if (state.validationOk) {
            setValidationBadge("Validation passed", "ok");
            el("analyzeBtn").disabled = false;
          } else if (errors.length) {
            setValidationBadge("Validation failed", "bad");
            el("analyzeBtn").disabled = true;
          } else {
            setValidationBadge("Validation incomplete", "warn");
            el("analyzeBtn").disabled = true;
          }

          const structure = data.structure || {};
          const metrics = [];
          if (structure.formula) metrics.push(["Formula", prettyFormula(structure.formula)]);
          if (structure.total_hydrogens !== undefined) metrics.push(["Total H", structure.total_hydrogens]);
          if (structure.labile_hydrogens !== undefined) metrics.push(["Labile H", structure.labile_hydrogens]);
          if (data.parseable_peak_count !== undefined) metrics.push(["Peaks parsed", data.parseable_peak_count]);
          if (data.expected_visible_h !== undefined && data.expected_visible_h !== null) metrics.push(["Expected visible H", data.expected_visible_h]);
          if (data.observed_total_h !== undefined && data.observed_total_h !== null) metrics.push(["Observed H", data.observed_total_h]);
          if (data.adjusted_observed_total_h !== undefined && data.adjusted_observed_total_h !== null) metrics.push(["Adjusted H", data.adjusted_observed_total_h]);
          if (data.delta_visible_h !== undefined && data.delta_visible_h !== null) metrics.push(["Δ visible H", data.delta_visible_h]);

          el("validationSummary").innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>Validation summary</strong>
              <span class="status-badge ${state.validationOk ? "ok" : (errors.length ? "bad" : "warn")}">${state.validationOk ? "Ready to analyze" : (errors.length ? "Fix inputs first" : "Complete both fields")}</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">SMILES</div><div class="value">${smilesProvided ? (structureValid ? "Valid" : "Invalid") : "Not provided"}</div></div>
              <div class="metric"><div class="label">NMR text</div><div class="value">${nmrProvided ? (nmrValid ? "Valid" : "Invalid") : "Not provided"}</div></div>
              <div class="metric"><div class="label">Structure ↔ NMR</div><div class="value">${structureValid && nmrValid ? (structureNmrMatch ? "Matched" : "Mismatch") : "Pending"}</div></div>
              <div class="metric"><div class="label">Warnings</div><div class="value">${warnings.length}</div></div>
              <div class="metric"><div class="label">Errors</div><div class="value">${errors.length}</div></div>
            </div>
            ${metrics.length ? `<div class="summary-grid">${metrics.map(([label, value]) => `<div class="metric"><div class="label">${label}</div><div class="value">${escapeHtml(value)}</div></div>`).join("")}</div>` : ""}
            ${errors.length ? `<div class="panel" style="margin-top:.85rem; background:var(--danger-bg);"><strong style="color:var(--danger);">Errors</strong><ul>${errors.map((e) => `<li>${escapeHtml(e)}</li>`).join("")}</ul></div>` : ""}
            ${warnings.length ? `<div class="panel" style="margin-top:.85rem; background:var(--warn-bg);"><strong style="color:var(--warn);">Warnings</strong><ul>${warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}</ul></div>` : ""}
          `;
        }

        function renderAnalysis(data) {
          const label = data.label || "result";
          const variant = /consistent|ok|complete|success/i.test(label) ? "ok" : (/impurity|invalid|error|fail/i.test(label) ? "bad" : "warn");
          setResultBadge(label, variant);
          const notes = Array.isArray(data.notes) ? data.notes : [];
          const peaks = Array.isArray(data.peaks) ? data.peaks : [];
          const structure = data.structure || {};
          const protonEvidenceScore = data.proton_evidence_score;
          el("readableOutput").innerHTML = `
            <div class="panel">
              <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                <div>
                  <strong>${escapeHtml(data.sample_id || "Current sample")}</strong>
                  <div class="muted small">${escapeHtml(prettyChemicalLabel(data.solvent || "No solvent supplied"))}</div>
                </div>
                <span class="status-badge ${variant}">${escapeHtml(label)}</span>
              </div>
              <div class="summary-grid">
                <div class="metric"><div class="label">Expected total H</div><div class="value">${data.expected_total_h ?? "—"}</div></div>
                <div class="metric"><div class="label">Observed total H</div><div class="value">${data.observed_total_h ?? "—"}</div></div>
                <div class="metric"><div class="label">Δ total H</div><div class="value">${data.delta_total_h ?? "—"}</div></div>
                <div class="metric"><div class="label">Confidence</div><div class="value">${data.confidence ?? "—"}</div></div>
                <div class="metric"><div class="label">¹H evidence</div><div class="value">${protonEvidenceScore !== undefined && protonEvidenceScore !== null ? Math.round(protonEvidenceScore * 100) + "%" : "—"}</div></div>
              </div>
            </div>
            <div class="panel">
              <strong>Structure summary</strong>
              <div class="summary-grid">
                <div class="metric"><div class="label">Formula</div><div class="value">${escapeHtml(prettyFormula(structure.formula || "—"))}</div></div>
                <div class="metric"><div class="label">Molecular weight</div><div class="value">${structure.molecular_weight ?? "—"}</div></div>
                <div class="metric"><div class="label">Total H</div><div class="value">${structure.total_hydrogens ?? "—"}</div></div>
                <div class="metric"><div class="label">Labile H</div><div class="value">${structure.labile_hydrogens ?? "—"}</div></div>
                <div class="metric"><div class="label">Non-labile H</div><div class="value">${structure.non_labile_hydrogens ?? "—"}</div></div>
                <div class="metric"><div class="label">Aromatic H</div><div class="value">${structure.aromatic_protons ?? "—"}</div></div>
                <div class="metric"><div class="label">Aliphatic H</div><div class="value">${structure.aliphatic_protons ?? "—"}</div></div>
                <div class="metric"><div class="label">Aromatic atoms</div><div class="value">${structure.aromatic_atom_count ?? "—"}</div></div>
              </div>
            </div>
            <div class="panel">
              <strong>Interpretation notes</strong>
              ${notes.length ? `<ul>${notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul>` : '<p class="muted small">No notes returned.</p>'}
            </div>
            <div class="panel">
              <strong>Parsed peaks</strong>
              ${peaks.length ? `<table><thead><tr><th>Shift (ppm)</th><th>Multiplicity</th><th>Coupling Constant</th><th>Integration</th></tr></thead><tbody>${peaks.map((peak) => `<tr><td>${peak.shift_ppm ?? "—"}</td><td>${escapeHtml(peak.multiplicity ?? "—")}</td><td>${escapeHtml(getSpectrumJValueText(peak) || "—")}</td><td>${peak.integration_h ?? "—"}</td></tr>`).join("")}</tbody></table>` : '<p class="muted small">No peaks returned.</p>'}
            </div>
          `;
          if (data.proton_evidence) renderProtonEvidence(data.proton_evidence);
        }

        function renderProtonEvidence(data) {
          const box = el("protonEvidenceBox");
          if (!box) return;
          const peaks = Array.isArray(data.peaks) ? data.peaks : [];
          const notes = Array.isArray(data.notes) ? data.notes : [];
          const warnings = Array.isArray(data.warnings) ? data.warnings : [];
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>¹H spectral evidence</strong>
              <span class="status-badge ${String(data.label || "").includes("consistent") ? "ok" : "warn"}">${escapeHtml(data.label || "evidence")}</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">Evidence score</div><div class="value">${Math.round((data.overall_score || 0) * 100)}%</div></div>
              <div class="metric"><div class="label">Expected H</div><div class="value">${escapeHtml(data.expected_total_h ?? "—")}</div></div>
              <div class="metric"><div class="label">Observed H</div><div class="value">${escapeHtml(data.observed_total_h ?? "—")}</div></div>
              <div class="metric"><div class="label">Non-solvent H</div><div class="value">${escapeHtml(data.observed_non_solvent_h ?? "—")}</div></div>
              <div class="metric"><div class="label">Solvent/water H</div><div class="value">${escapeHtml(data.solvent_or_water_h ?? "—")}</div></div>
              <div class="metric"><div class="label">Integration score</div><div class="value">${Math.round((data.integration_score || 0) * 100)}%</div></div>
            </div>
            ${warnings.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Warnings</strong><ul>${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul></div>` : ""}
            ${notes.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Notes</strong><ul>${notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul></div>` : ""}
            <details style="margin-top:.8rem;"><summary>¹H evidence peaks</summary>
              <table><thead><tr><th>ppm</th><th>Multiplicity</th><th>H</th><th>Region</th><th>Solvent/water?</th></tr></thead>
              <tbody>${peaks.map((peak) => `<tr><td>${escapeHtml(peak.shift_ppm)}</td><td>${escapeHtml(peak.multiplicity)}</td><td>${escapeHtml(peak.integration_h)}</td><td>${escapeHtml(peak.region || "—")}</td><td>${peak.is_likely_solvent || peak.is_likely_water ? "yes" : "no"}</td></tr>`).join("")}</tbody></table>
            </details>
          `;
        }

        async function analyzeProtonEvidence() {
          try {
            const data = await api("/proton/evidence", { method: "POST", body: JSON.stringify(payload()) });
            setJson(data);
            renderProtonEvidence(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("protonEvidenceBox")) el("protonEvidenceBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function getCarbon13ReportHtml(data) {
          const peaks = Array.isArray(data.peaks) ? data.peaks : [];
          const regions = Array.isArray(data.region_summary) ? data.region_summary : [];
          const notes = Array.isArray(data.notes) ? data.notes : [];
          const solventWarnings = Array.isArray(data.solvent_warnings) ? data.solvent_warnings : [];
          const warnings = Array.isArray(data.warnings) ? data.warnings : [];
          const evidenceSummary = Array.isArray(data.evidence_summary) ? data.evidence_summary : [];
          const status = data.label || "preview";
          return `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>¹³C NMR evidence</strong>
              <span class="status-badge ${String(status).includes("consistent") ? "ok" : "warn"}">${escapeHtml(status)}</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">Expected C</div><div class="value">${escapeHtml(data.expected_carbon_atoms ?? "—")}</div></div>
              <div class="metric"><div class="label">Observed signals</div><div class="value">${escapeHtml(data.observed_carbon_signals ?? data.observed_signal_count ?? peaks.length)}</div></div>
              <div class="metric"><div class="label">Delta signals</div><div class="value">${escapeHtml(data.delta_carbon_signals ?? "—")}</div></div>
              <div class="metric"><div class="label">Confidence</div><div class="value">${data.confidence !== undefined ? Math.round(data.confidence * 100) + "%" : "—"}</div></div>
              <div class="metric"><div class="label">¹³C evidence score</div><div class="value">${data.carbon13_match_score !== undefined && data.carbon13_match_score !== null ? Math.round(data.carbon13_match_score * 100) + "%" : "—"}</div></div>
              <div class="metric"><div class="label">Region score</div><div class="value">${data.region_consistency_score !== undefined && data.region_consistency_score !== null ? Math.round(data.region_consistency_score * 100) + "%" : "—"}</div></div>
            </div>
            ${regions.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Region summary</strong><ul>${regions.map((region) => `<li>${escapeHtml(region.region)}: ${escapeHtml(region.count)} signal(s)</li>`).join("")}</ul></div>` : ""}
            ${evidenceSummary.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Evidence summary</strong><ul>${evidenceSummary.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>` : ""}
            ${solventWarnings.length || warnings.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Warnings</strong><ul>${[...solventWarnings, ...warnings].map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul></div>` : ""}
            ${notes.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Notes</strong><ul>${notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul></div>` : ""}
            <details style="margin-top:.8rem;"><summary>¹³C peaks</summary>
              <table><thead><tr><th>ppm</th><th>Region</th><th>Solvent?</th><th>Impurity table?</th><th>Assignment</th></tr></thead>
              <tbody>${peaks.map((peak) => `<tr><td>${escapeHtml(peak.shift_ppm)}</td><td>${escapeHtml(peak.region || "—")}</td><td>${peak.is_likely_solvent ? "yes" : "no"}</td><td>${peak.is_likely_impurity ? "yes" : "no"}</td><td>${escapeHtml(peak.assignment || "—")}</td></tr>`).join("")}</tbody></table>
            </details>
          `;
        }

        function renderCarbon13Report(data) {
          const box = el("carbon13Box");
          if (!box) return;
          box.innerHTML = getCarbon13ReportHtml(data);
        }

        function synthesizeCarbon13PreviewPoints(peaks) {
          const valid = (Array.isArray(peaks) ? peaks : [])
            .map((peak) => ({
              shift: Number(peak.shift_ppm),
              intensity: Math.max(0.08, Math.abs(Number(peak.intensity ?? 1)) || 1),
            }))
            .filter((item) => Number.isFinite(item.shift));
          if (!valid.length) return [];
          const points = [];
          for (const item of valid) {
            points.push({ shift_ppm: Number((item.shift + 0.08).toFixed(4)), intensity: 0 });
            points.push({ shift_ppm: Number(item.shift.toFixed(4)), intensity: item.intensity });
            points.push({ shift_ppm: Number((item.shift - 0.08).toFixed(4)), intensity: 0 });
          }
          points.sort((a, b) => Number(b.shift_ppm) - Number(a.shift_ppm));
          return points;
        }

        function carbon13PeakToSpectrumPeak(peak) {
          const intensity = Number(peak?.intensity);
          return {
            shift_ppm: Number(peak?.shift_ppm),
            multiplicity: peak?.carbon_type || "s",
            integration_h: Math.max(0.1, Math.min(50, Number.isFinite(intensity) ? Math.abs(intensity) : 1)),
            intensity: Number.isFinite(intensity) ? intensity : null,
            assignment: peak?.assignment || null,
            carbon_type: peak?.carbon_type || null,
            region: peak?.region || null,
            is_likely_solvent: Boolean(peak?.is_likely_solvent),
            is_likely_impurity: Boolean(peak?.is_likely_impurity),
            nucleus: "13C",
          };
        }

        function buildCarbon13SpectrumPreviewData(data) {
          const peaks = Array.isArray(data?.peaks) ? data.peaks : [];
          const metadata = data?.metadata || {};
          const previewPoints = Array.isArray(metadata.preview_points) && metadata.preview_points.length
            ? metadata.preview_points
            : synthesizeCarbon13PreviewPoints(peaks);
          const inferredPeaks = peaks.map(carbon13PeakToSpectrumPeak).filter((peak) => Number.isFinite(Number(peak.shift_ppm)));
          return {
            filename: data?.filename || "carbon13-spectrum",
            format_detected: metadata.format_detected || metadata.format || data?.source_mode || "carbon13_upload",
            source_mode: data?.source_mode || "carbon13",
            solvent: metadata.solvent || el("solvent")?.value || null,
            point_count: metadata.point_count ?? previewPoints.length,
            preview_points: previewPoints,
            inferred_peaks: inferredPeaks,
            inferred_nmr_text: inferredPeaks.map(formatSpectrumPeakSummary).join(", "),
            reference_peaks: [],
            comparison: null,
            warnings: Array.isArray(data?.warnings) ? data.warnings : [],
            metadata: {
              ...metadata,
              nucleus: "13C",
              carbon13_report: data,
            },
          };
        }

        function renderCarbon13SpectrumWorkflow(data, { title="¹³C spectrum analysis", previewData=null }={}) {
          const sourceData = previewData || data;
          const spectrumData = buildCarbon13SpectrumPreviewData(sourceData);
          spectrumData.metadata.carbon13_report = data;
          state.latestCarbon13Preview = sourceData;
          state.latestCarbon13SpectrumPreview = spectrumData;
          if (Array.isArray(spectrumData.preview_points) && spectrumData.preview_points.length) {
            renderSpectrumPreview(spectrumData, {
              targetId: "carbon13Box",
              title,
              nucleus: "13C",
              extraHtmlBefore: getCarbon13ReportHtml(data),
            });
          } else {
            renderCarbon13Report(data);
          }
        }

        function hasReusableCarbon13Preview(file, sourceMode) {
          return Boolean(
            file
            && state.latestCarbon13Preview
            && state.latestCarbon13Preview.filename === file.name
            && (!sourceMode || state.latestCarbon13Preview.source_mode === sourceMode)
          );
        }

        function appendCarbon13ManualPeaksIfReviewed(formData) {
          const preview = state.latestCarbon13SpectrumPreview;
          if (!preview || !hasSpectrumManualReviewDecisions(preview)) return;
          const peaks = getSpectrumReviewedPeaks(preview).map((peak) => ({
            shift_ppm: peak.shift_ppm,
            intensity: peak.intensity ?? peak.integration_h ?? null,
            assignment: peak.assignment || null,
            carbon_type: peak.carbon_type || null,
          }));
          if (!peaks.length) throw new Error("All reviewed ¹³C peaks are excluded. Accept at least one peak before analyzing.");
          formData.append("manual_peaks_json", JSON.stringify({ peaks }));
        }

        async function validateCarbon13Text() {
          try {
            const data = await api("/carbon13/validate", {
              method: "POST",
              body: JSON.stringify({
                smiles: el("smiles").value.trim(),
                carbon13_text: el("carbon13Text").value.trim(),
                solvent: el("solvent").value.trim() || null,
                sample_id: el("sampleId").value.trim() || null,
              }),
            });
            setJson(data);
            renderCarbon13Report(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("carbon13Box")) el("carbon13Box").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        async function analyzeCarbon13Text() {
          try {
            const data = await api("/carbon13/analyze", {
              method: "POST",
              body: JSON.stringify({
                smiles: el("smiles").value.trim(),
                carbon13_text: el("carbon13Text").value.trim(),
                solvent: el("solvent").value.trim() || null,
                sample_id: el("sampleId").value.trim() || null,
              }),
            });
            setJson(data);
            renderCarbon13Report(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("carbon13Box")) el("carbon13Box").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function appendCarbon13ProcessedFormFields(formData, { includeSmiles=false }={}) {
          if (includeSmiles) formData.append("smiles", el("smiles").value.trim());
          const solvent = el("solvent").value.trim();
          const sampleId = el("sampleId").value.trim();
          const sensitivity = el("carbon13PeakSensitivity")?.value.trim();
          if (solvent) formData.append("solvent", solvent);
          if (sampleId) formData.append("sample_id", sampleId);
          if (sensitivity) formData.append("peak_sensitivity", sensitivity);
          const baselineMode = el("carbon13ProcessedBaselineCorrection")?.value || "bernstein";
          const baselineOrder = el("carbon13ProcessedBaselineOrder")?.value || "3";
          const displayMode = el("carbon13ProcessedDisplayMode")?.value || "real";
          formData.append("mask_solvent_regions", "true");
          formData.append("display_mode", displayMode);
          formData.append("vertical_gain", "1");
          formData.append("processed_baseline_correction", baselineMode);
          formData.append("processed_baseline_order", baselineOrder);
        }

        async function previewCarbon13Spectrum() {
          try {
            const file = el("carbon13SpectrumFile").files[0];
            if (!file) throw new Error("Choose a processed ¹³C spectrum or peak table first.");
            const formData = new FormData();
            formData.append("file", file);
            appendCarbon13ProcessedFormFields(formData);
            const data = await api("/carbon13/spectrum/preview", { method: "POST", body: formData });
            state.latestCarbon13Preview = data;
            setJson(data);
            renderCarbon13SpectrumWorkflow(data, { title: "¹³C processed spectrum preview" });
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("carbon13Box")) el("carbon13Box").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        async function analyzeCarbon13Spectrum() {
          try {
            const file = el("carbon13SpectrumFile").files[0];
            if (!file) throw new Error("Choose a processed ¹³C spectrum or peak table first.");
            let previewData = state.latestCarbon13Preview;
            if (!hasReusableCarbon13Preview(file, null)) {
              const previewFormData = new FormData();
              previewFormData.append("file", file);
              appendCarbon13ProcessedFormFields(previewFormData);
              previewData = await api("/carbon13/spectrum/preview", { method: "POST", body: previewFormData });
              state.latestCarbon13Preview = previewData;
              renderCarbon13SpectrumWorkflow(previewData, { title: "¹³C processed spectrum preview" });
            }
            const formData = new FormData();
            formData.append("file", file);
            appendCarbon13ProcessedFormFields(formData, { includeSmiles: true });
            appendCarbon13ManualPeaksIfReviewed(formData);
            const data = await api("/carbon13/spectrum/analyze", { method: "POST", body: formData });
            setJson({ preview: previewData, analysis: data });
            renderCarbon13SpectrumWorkflow(data, { title: "¹³C processed spectrum analysis", previewData });
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("carbon13Box")) el("carbon13Box").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function appendCarbon13FidFormFields(formData, { includeSmiles=true }={}) {
          const smiles = el("smiles").value.trim();
          const protonNmrText = el("nmrText").value.trim();
          if (includeSmiles && smiles) formData.append("smiles", smiles);
          if (protonNmrText) formData.append("proton_nmr_text", protonNmrText);
          const solvent = el("solvent").value.trim();
          const sampleId = el("sampleId").value.trim();
          const reference = el("carbon13FidReferencePPM")?.value.trim();
	          const preset = el("carbon13FidProcessingPreset")?.value.trim() || "balanced";
	          const zeroFill = el("carbon13FidZeroFillFactor")?.value.trim();
	          const apodizationMode = el("carbon13FidApodizationMode")?.value || "exponential";
	          const lineBroadening = el("carbon13FidLineBroadeningHz")?.value.trim();
          const sensitivity = el("carbon13FidPeakSensitivity")?.value.trim();
          if (solvent) formData.append("solvent", solvent);
          if (sampleId) formData.append("sample_id", sampleId);
          if (reference) formData.append("reference_ppm", reference);
	          if (preset) formData.append("selected_preset", preset);
	          if (zeroFill) formData.append("zero_fill_factor", zeroFill);
	          formData.append("apodization_mode", apodizationMode);
	          if (lineBroadening) formData.append("line_broadening_hz", lineBroadening);
          if (sensitivity) formData.append("peak_sensitivity", sensitivity);
          const phaseMode = el("carbon13FidPhaseMode")?.value || "auto";
          const phaseP0 = el("carbon13FidPhaseP0")?.value || "0.0";
          const phaseP1 = el("carbon13FidPhaseP1")?.value || "0.0";
          const baselineMode = el("carbon13FidBaselineCorrection")?.value || "bernstein";
          const baselineOrder = el("carbon13FidBaselineOrder")?.value || "3";
          const displayMode = el("carbon13FidDisplayMode")?.value || "real";
          formData.append("apply_group_delay", el("carbon13FidApplyGroupDelay").checked ? "true" : "false");
          formData.append("auto_phase", phaseMode === "none" ? "false" : "true");
          formData.append("phase_mode", phaseMode);
          formData.append("phase_p0", phaseP0);
          formData.append("phase_p1", phaseP1);
          formData.append("auto_baseline", ["none", "preserve"].includes(baselineMode) ? "false" : "true");
          formData.append("baseline_correction", baselineMode);
          formData.append("baseline_order", baselineOrder);
          formData.append("mask_solvent_regions", el("carbon13FidMaskSolventRegions").checked ? "true" : "false");
          formData.append("display_mode", displayMode);
          formData.append("vertical_gain", "1");
        }

        async function previewCarbon13Fid() {
          try {
            const file = el("carbon13FidFile").files[0];
            if (!file) throw new Error("Choose a raw ¹³C FID dataset .zip or .tar.gz archive first.");
            const formData = new FormData();
            formData.append("file", file);
            appendCarbon13FidFormFields(formData);
            const data = await api("/carbon13/fid/preview", { method: "POST", body: formData });
            state.latestCarbon13Preview = data;
            setJson(data);
            renderCarbon13SpectrumWorkflow(data, { title: "Raw ¹³C FID spectrum preview" });
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("carbon13Box")) el("carbon13Box").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        async function applyCarbon13FidPhaseCorrection() {
          const phaseControl = el("carbon13FidPhaseMode");
          if (phaseControl) phaseControl.value = "auto";
          markCarbon13FidPresetCustom();
          await previewCarbon13Fid();
        }

        async function applyCarbon13FidBaselineCorrection() {
          const baselineControl = el("carbon13FidBaselineCorrection");
          if (baselineControl) baselineControl.value = "bernstein";
          if (el("carbon13FidBaselineOrder")) el("carbon13FidBaselineOrder").value = "3";
          markCarbon13FidPresetCustom();
          await previewCarbon13Fid();
        }

        async function analyzeCarbon13Fid() {
          try {
            const file = el("carbon13FidFile").files[0];
            if (!file) throw new Error("Choose a raw ¹³C FID dataset .zip or .tar.gz archive first.");
            let previewData = state.latestCarbon13Preview;
            if (!hasReusableCarbon13Preview(file, "raw_fid")) {
              const previewFormData = new FormData();
              previewFormData.append("file", file);
              appendCarbon13FidFormFields(previewFormData);
              previewData = await api("/carbon13/fid/preview", { method: "POST", body: previewFormData });
              state.latestCarbon13Preview = previewData;
              renderCarbon13SpectrumWorkflow(previewData, { title: "Raw ¹³C FID spectrum preview" });
            }
            const formData = new FormData();
            formData.append("file", file);
            appendCarbon13FidFormFields(formData, { includeSmiles: true });
            appendCarbon13ManualPeaksIfReviewed(formData);
            const data = await api("/carbon13/fid/analyze", { method: "POST", body: formData });
            setJson({ preview: previewData, analysis: data });
            renderCarbon13SpectrumWorkflow(data, { title: "Raw ¹³C FID spectrum analysis", previewData });
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("carbon13Box")) el("carbon13Box").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        async function uploadCarbon13Table() {
          return analyzeCarbon13Spectrum();
        }

        function syncDeptAptContext() {
          return null;
        }

        function appendDeptAptFormFields(formData) {
          const experiment = el("deptAptExperiment")?.value || "";
          const aptPositive = el("deptAptPositive")?.value || "CH_CH3";
          const carbonText = el("carbon13Text")?.value.trim() || "";
          if (experiment) formData.append("experiment_type", experiment);
          formData.append("apt_positive", aptPositive);
          if (carbonText) formData.append("carbon13_text", carbonText);
          const solvent = el("solvent")?.value.trim() || "";
          if (solvent) formData.append("solvent", solvent);
        }

        function renderDeptAptResult(data, { analyzed=false } = {}) {
          const preview = analyzed ? (data?.preview || {}) : (data || {});
          const metadata = preview?.metadata || {};
          const typeSummary = analyzed ? (data?.type_summary || metadata.type_summary || {}) : (metadata.type_summary || {});
          const warnings = [...(Array.isArray(preview?.warnings) ? preview.warnings : []), ...(Array.isArray(data?.warnings) ? data.warnings : [])];
          const notes = Array.isArray(data?.notes) ? data.notes : [];
          const peaks = Array.isArray(preview?.peaks) ? preview.peaks : [];
          const rows = Object.entries(typeSummary).map(([key, value]) => `<tr><td>${escapeHtml(key)}</td><td>${escapeHtml(value)}</td></tr>`).join("");
          const peakRows = peaks.slice(0, 60).map((peak) => `
            <tr>
              <td>${escapeHtml(peak.experiment || "—")}</td>
              <td>${escapeHtml(peak.shift_ppm ?? "—")}</td>
              <td>${escapeHtml(peak.phase || "—")}</td>
              <td>${escapeHtml(peak.carbon_type || "—")}</td>
              <td>${escapeHtml(peak.matched_carbon13_shift_ppm ?? "—")}</td>
              <td>${escapeHtml(peak.assignment || "—")}</td>
              <td>${escapeHtml(Array.isArray(peak.warnings) ? peak.warnings.join("; ") : "")}</td>
            </tr>
          `).join("");
          if (el("deptAptBox")) {
            el("deptAptBox").innerHTML = `
              <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                <strong>DEPT/APT ${analyzed ? "analysis" : "preview"}</strong>
                <span class="status-badge warn">review required</span>
              </div>
              <div class="summary-grid">
                <div class="metric"><div class="label">Experiment detected</div><div class="value">${escapeHtml(preview?.experiment_detected || "—")}</div></div>
                <div class="metric"><div class="label">Peak count</div><div class="value">${escapeHtml(preview?.peak_count ?? 0)}</div></div>
                <div class="metric"><div class="label">Typed peak count</div><div class="value">${escapeHtml(data?.typed_peak_count ?? metadata.typed_peak_count ?? 0)}</div></div>
                <div class="metric"><div class="label">Matched 13C count</div><div class="value">${escapeHtml(data?.matched_carbon13_count ?? "—")}</div></div>
                <div class="metric"><div class="label">Consistency score</div><div class="value">${formatNmr2dPercent(data?.dept_apt_consistency_score)}</div></div>
              </div>
              ${rows ? `<details style="margin-top:.8rem;" open><summary>Type summary</summary><table><tbody>${rows}</tbody></table></details>` : ""}
              ${warnings.length ? renderNmr2dMessages("Warnings", warnings) : ""}
              ${notes.length ? renderNmr2dMessages("Notes", notes) : ""}
              ${peakRows ? `<details style="margin-top:.8rem;" open><summary>DEPT/APT peak table</summary><table><thead><tr><th>Experiment</th><th>13C ppm</th><th>Phase</th><th>Carbon type</th><th>Matched 13C</th><th>Assignment</th><th>Warnings</th></tr></thead><tbody>${peakRows}</tbody></table></details>` : ""}
            `;
          }
        }

        async function previewDeptApt() {
          try {
            syncDeptAptContext();
            const file = el("deptAptFile")?.files?.[0];
            if (!file) throw new Error("Choose a DEPT/APT peak table first.");
            const formData = new FormData();
            formData.append("file", file);
            appendDeptAptFormFields(formData);
            const data = await api("/carbon13/dept/preview", { method: "POST", body: formData });
            state.latestDeptAptPreview = data;
            setJson(data);
            renderDeptAptResult(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("deptAptBox")) el("deptAptBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        async function analyzeDeptApt() {
          try {
            syncDeptAptContext();
            const file = el("deptAptFile")?.files?.[0];
            if (!file) throw new Error("Choose a DEPT/APT peak table first.");
            const formData = new FormData();
            formData.append("file", file);
            appendDeptAptFormFields(formData);
            const data = await api("/carbon13/dept/analyze", { method: "POST", body: formData });
            state.latestDeptAptReport = data;
            setJson(data);
            renderDeptAptResult(data, { analyzed: true });
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("deptAptBox")) el("deptAptBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function useDeptAptWithNmr2d() {
          syncNmr2dContext();
          showSection("analyze");
          el("deptApt2dStudio")?.scrollIntoView({ behavior: "smooth", block: "start" });
        }

        function syncNmr2dContext() {
          return null;
        }

        function installNmr2dContextHandlers() {
          ["sampleId","solvent","nmrText","carbon13Text"].forEach((id) => {
            const node = el(id);
            if (!node) return;
            node.addEventListener("input", syncNmr2dContext);
            node.addEventListener("change", syncNmr2dContext);
          });
          syncNmr2dContext();
        }

        function appendNmr2dFormFields(formData, { includeStructure=false, saveRun=false } = {}) {
          syncNmr2dContext();
          const experiment = el("nmr2dExperiment")?.value || "";
          if (experiment) formData.append("experiment", experiment);
          formData.append("include_contour_preview", "false");
          if (includeStructure) {
            formData.append("smiles", el("smiles")?.value.trim() || "");
            const sampleId = el("sampleId")?.value.trim() || "";
            const solvent = el("solvent")?.value.trim() || "";
            const protonText = el("nmrText").value.trim();
            const carbonText = el("carbon13Text") ? el("carbon13Text").value.trim() : "";
            if (sampleId) formData.append("sample_id", sampleId);
            if (solvent) formData.append("solvent", solvent);
            if (protonText) formData.append("proton_nmr_text", protonText);
            if (carbonText) formData.append("carbon13_text", carbonText);
            const deptFile = el("deptAptFile")?.files?.[0] || null;
            const deptExperiment = el("deptAptExperiment")?.value || "";
            const aptPositive = el("deptAptPositive")?.value || "CH_CH3";
            if (deptFile) {
              formData.append("dept_apt_file", deptFile);
            }
            formData.append("dept_apt_experiment_type", deptExperiment);
            formData.append("apt_positive", aptPositive);
            formData.append("save_run", saveRun ? "true" : "false");
            const analysisId = getLatestAvailableAnalysisId();
            if (saveRun && analysisId) formData.append("analysis_id", String(analysisId));
          }
        }

        function formatNmr2dPercent(value) {
          const numeric = Number(value);
          return Number.isFinite(numeric) ? `${Math.round(numeric * 100)}%` : "—";
        }

        function renderNmr2dPeakTable(peaks) {
          const rows = (Array.isArray(peaks) ? peaks : []).slice(0, 40).map((peak) => `
            <tr>
              <td>${escapeHtml(peak.experiment || "—")}</td>
              <td>${escapeHtml(peak.f1_ppm ?? "—")}</td>
              <td>${escapeHtml(peak.f2_ppm ?? "—")}</td>
              <td>${escapeHtml(formatNucleusLabel(peak.f1_nucleus || "—"))}</td>
              <td>${escapeHtml(formatNucleusLabel(peak.f2_nucleus || "—"))}</td>
              <td>${peak.is_diagonal ? "Yes" : "No"}</td>
              <td>${peak.is_solvent_artifact ? "Yes" : "No"}</td>
              <td>${peak.is_suspicious ? "Yes" : "No"}</td>
              <td>${escapeHtml(peak.evidence_label || "review")}</td>
            </tr>
          `).join("");
          return rows
            ? `<details style="margin-top:.8rem;" open><summary>2D cross-peaks</summary><table><thead><tr><th>Experiment</th><th>F1 ppm</th><th>F2 ppm</th><th>F1 nucleus</th><th>F2 nucleus</th><th>Diagonal</th><th>Solvent/artifact</th><th>Suspicious</th><th>Evidence</th></tr></thead><tbody>${rows}</tbody></table></details>`
            : "";
        }

        function renderNmr2dCorrelationTable(correlations) {
          const rows = (Array.isArray(correlations) ? correlations : []).slice(0, 60).map((correlation) => `
            <tr>
              <td>${escapeHtml(correlation.correlation_type || "—")}</td>
              <td>${escapeHtml(correlation.observed_f2_ppm ?? "—")}</td>
              <td>${escapeHtml(correlation.observed_f1_ppm ?? "—")}</td>
              <td>${escapeHtml(correlation.matched_1h_peak ?? "—")}</td>
              <td>${escapeHtml(correlation.matched_13c_peak ?? "—")}</td>
              <td>${escapeHtml(correlation.plausibility_label || "review")}</td>
              <td>${formatNmr2dPercent(correlation.confidence)}</td>
              <td>${escapeHtml(Array.isArray(correlation.notes) ? correlation.notes.join("; ") : "")}</td>
            </tr>
          `).join("");
          return rows
            ? `<details style="margin-top:.8rem;" open><summary>Correlation table</summary><table><thead><tr><th>Type</th><th>F2 ppm</th><th>F1 ppm</th><th>Matched ¹H</th><th>Matched ¹³C</th><th>Plausibility</th><th>Confidence</th><th>Notes</th></tr></thead><tbody>${rows}</tbody></table></details>`
            : "";
        }

        function renderNmr2dConnectivityGraph(summary) {
          const graph = summary?.cosy_connectivity_graph || {};
          const nodes = Array.isArray(graph.nodes) ? graph.nodes : [];
          const edges = Array.isArray(graph.edges) ? graph.edges : [];
          const edgeText = edges.length ? edges.map((edge) => Array.isArray(edge) ? edge.join(" ↔ ") : String(edge)).join(", ") : "No non-diagonal COSY edges.";
          return `
            <div class="panel" style="margin-top:.8rem;">
              <strong>Connectivity graph summary</strong>
              <div class="summary-grid" style="margin-top:.55rem;">
                <div class="metric"><div class="label">Nodes</div><div class="value">${escapeHtml(nodes.length)}</div></div>
                <div class="metric"><div class="label">Edges</div><div class="value">${escapeHtml(edges.length)}</div></div>
              </div>
              <p class="muted small" style="margin-top:.55rem;">${escapeHtml(edgeText)}</p>
            </div>
          `;
        }

        function renderNmr2dContourSummary(preview) {
          const points = Array.isArray(preview?.contour_preview) ? preview.contour_preview : [];
          const metadata = preview?.metadata || {};
          const matrix = metadata.matrix_preview || metadata.contour_preview || {};
          const sampleRows = points.slice(0, 8).map((point) => `
            <tr><td>${escapeHtml(point.f2_ppm ?? "—")}</td><td>${escapeHtml(point.f1_ppm ?? "—")}</td><td>${escapeHtml(point.intensity ?? "—")}</td></tr>
          `).join("");
          return `
            <details style="margin-top:.8rem;" ${points.length ? "open" : ""}>
              <summary>Optional contour/matrix preview</summary>
              <div class="summary-grid" style="margin-top:.65rem;">
                <div class="metric"><div class="label">Preview points</div><div class="value">${escapeHtml(points.length)}</div></div>
                <div class="metric"><div class="label">Downsampling</div><div class="value">${escapeHtml(matrix.downsampling_method || metadata.downsampling_method || "display-only")}</div></div>
              </div>
              ${sampleRows ? `<table style="margin-top:.65rem;"><thead><tr><th>F2 ppm</th><th>F1 ppm</th><th>Intensity</th></tr></thead><tbody>${sampleRows}</tbody></table>` : `<p class="muted small">No contour points returned. Enable the option for processed grid or intensity-bearing files.</p>`}
            </details>
          `;
        }

        function renderNmr2dReviewBox(data, { saved=false } = {}) {
          const box = el("nmr2dReviewBox");
          if (!box) return;
          const runId = data?.run_id || state.latestNmr2dSavedRunId || null;
          const label = data?.label || "pending_review";
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>Review</strong>
              <span class="status-badge warn">human review required</span>
            </div>
            <div class="summary-grid" style="margin-top:.65rem;">
              <div class="metric"><div class="label">Review status</div><div class="value">pending</div></div>
              <div class="metric"><div class="label">Saved run</div><div class="value">${escapeHtml(runId ? `#${runId}` : (saved ? "saving" : "not saved"))}</div></div>
              <div class="metric"><div class="label">Evidence label</div><div class="value">${escapeHtml(label)}</div></div>
            </div>
            <p class="muted small" style="margin-top:.55rem;">2D NMR evidence is supportive connectivity evidence and requires human review.</p>
          `;
        }

        function renderNmr2dMessages(title, messages) {
          const items = (Array.isArray(messages) ? messages : []).filter(Boolean);
          return items.length ? `<div class="panel" style="margin-top:.8rem;"><strong>${escapeHtml(title)}</strong><ul>${items.map((message) => `<li>${escapeHtml(message)}</li>`).join("")}</ul></div>` : "";
        }

        function renderNmr2dPreview(data) {
          const box = el("nmr2dBox");
          if (!box) return;
          const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
          const experiments = Array.isArray(data?.experiments) && data.experiments.length ? data.experiments.join(", ") : (data?.experiment_detected || "—");
          const suspicious = (Array.isArray(data?.peaks) ? data.peaks : []).filter((peak) => peak.is_suspicious).length;
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>2D preview</strong>
              <span class="status-badge warn">review aid</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">Experiment detected</div><div class="value">${escapeHtml(experiments || "—")}</div></div>
              <div class="metric"><div class="label">Peak count</div><div class="value">${escapeHtml(data?.peak_count ?? 0)}</div></div>
              <div class="metric"><div class="label">Suspicious peaks</div><div class="value">${escapeHtml(suspicious)}</div></div>
              <div class="metric"><div class="label">Source mode</div><div class="value">${escapeHtml(data?.source_mode || "processed_peak_table")}</div></div>
            </div>
            ${renderNmr2dMessages("Warnings", warnings)}
            ${renderNmr2dPeakTable(data?.peaks)}
            ${renderNmr2dContourSummary(data)}
          `;
          renderNmr2dReviewBox(data);
        }

        function renderNmr2dReport(data, { saved=false } = {}) {
          const box = el("nmr2dBox");
          if (!box) return;
          const preview = data?.preview || {};
          const warnings = [...(Array.isArray(preview?.warnings) ? preview.warnings : []), ...(Array.isArray(data?.warnings) ? data.warnings : [])];
          const notes = Array.isArray(data?.notes) ? data.notes : [];
          const experiments = Array.isArray(data?.experiments) && data.experiments.length ? data.experiments.join(", ") : (preview?.experiment_detected || "—");
          const label = data?.label || "review";
          const scoreComponents = data?.metadata?.score_components || data?.correlation_summary?.score_components || {};
          const scoreRows = Object.entries(scoreComponents).map(([key, value]) => `<tr><td>${escapeHtml(key.replaceAll("_", " "))}</td><td>${escapeHtml(value)}</td></tr>`).join("");
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>2D NMR correlation evidence</strong>
              <span class="status-badge ${getStatusVariant(label)}">${escapeHtml(label)}</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">Experiment detected</div><div class="value">${escapeHtml(experiments || "—")}</div></div>
              <div class="metric"><div class="label">Peak count</div><div class="value">${escapeHtml(data?.peak_count ?? preview?.peak_count ?? 0)}</div></div>
              <div class="metric"><div class="label">Evidence score</div><div class="value">${formatNmr2dPercent(data?.evidence_score ?? data?.overall_score)}</div></div>
              <div class="metric"><div class="label">Cross-peaks used</div><div class="value">${escapeHtml(Array.isArray(data?.correlations) ? data.correlations.length : (data?.peak_count ?? preview?.peak_count ?? 0))}</div></div>
              <div class="metric"><div class="label">Suspicious peaks</div><div class="value">${escapeHtml(data?.suspicious_peak_count ?? 0)}</div></div>
              <div class="metric"><div class="label">Matched correlations</div><div class="value">${escapeHtml(data?.matched_correlation_count ?? 0)}</div></div>
              <div class="metric"><div class="label">Missing references</div><div class="value">${escapeHtml(data?.missing_reference_count ?? 0)}</div></div>
            </div>
            <div class="summary-grid" style="margin-top:.7rem;">
              <div class="metric"><div class="label">Correlation score</div><div class="value">${formatNmr2dPercent(data?.correlation_score)}</div></div>
              <div class="metric"><div class="label">Structure score</div><div class="value">${formatNmr2dPercent(data?.structure_consistency_score)}</div></div>
              <div class="metric"><div class="label">Confidence</div><div class="value">${formatNmr2dPercent(data?.confidence)}</div></div>
              <div class="metric"><div class="label">Linked 1D peaks</div><div class="value">${escapeHtml(data?.linked_1d_peak_count ?? 0)}</div></div>
              <div class="metric"><div class="label">DEPT/APT support</div><div class="value">${escapeHtml(data?.correlation_summary?.dept_apt_supported_correlations ?? 0)}</div></div>
              <div class="metric"><div class="label">DEPT/APT ambiguous</div><div class="value">${escapeHtml(data?.correlation_summary?.dept_apt_ambiguous_correlations ?? 0)}</div></div>
              <div class="metric"><div class="label">DEPT/APT conflicts</div><div class="value">${escapeHtml(data?.correlation_summary?.dept_apt_conflicting_correlations ?? 0)}</div></div>
              <div class="metric"><div class="label">HMBC DEPT context</div><div class="value">${escapeHtml(data?.correlation_summary?.dept_apt_contextual_correlations ?? 0)}</div></div>
            </div>
            ${renderNmr2dMessages("Notes", notes)}
            ${renderNmr2dMessages("Warnings", warnings)}
            ${renderNmr2dCorrelationTable(data?.correlations)}
            ${renderNmr2dConnectivityGraph(data?.correlation_summary || {})}
            ${scoreRows ? `<details style="margin-top:.8rem;"><summary>Score components</summary><table><thead><tr><th>Component</th><th>Value</th></tr></thead><tbody>${scoreRows}</tbody></table></details>` : ""}
            ${renderNmr2dPeakTable(data?.peaks || preview?.peaks)}
            ${renderNmr2dContourSummary(preview)}
          `;
          renderNmr2dReviewBox(data, { saved });
        }

        async function previewNMR2D() {
          try {
            const file = el("nmr2dFile")?.files?.[0];
            if (!file) throw new Error("Choose a processed 2D NMR peak table first.");
            const formData = new FormData();
            formData.append("file", file);
            appendNmr2dFormFields(formData);
            const data = await api("/nmr2d/preview", { method: "POST", body: formData });
            state.latestNmr2dPreview = data;
            setJson(data);
            renderNmr2dPreview(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("nmr2dBox")) el("nmr2dBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        async function previewNmr2d() {
          return previewNMR2D();
        }

        async function runNmr2dAnalysis({ saveRun=false } = {}) {
          try {
            const file = el("nmr2dFile")?.files?.[0];
            if (!file) throw new Error("Choose a processed 2D NMR peak table first.");
            const formData = new FormData();
            formData.append("file", file);
            appendNmr2dFormFields(formData, { includeStructure: true, saveRun });
            const data = await api("/nmr2d/analyze", { method: "POST", body: formData });
            state.latestNmr2dReport = data;
            if (data?.preview) state.latestNmr2dPreview = data.preview;
            if (saveRun && data?.run_id) state.latestNmr2dSavedRunId = data.run_id;
            setJson(data);
            renderNmr2dReport(data, { saved: saveRun });
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("nmr2dBox")) el("nmr2dBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        async function analyzeNMR2D() {
          return runNmr2dAnalysis({ saveRun: false });
        }

        async function analyzeNmr2d() {
          return analyzeNMR2D();
        }

        async function saveNmr2dRun() {
          return runNmr2dAnalysis({ saveRun: true });
        }

        function exportNmr2dEvidence() {
          try {
            const payload = {
              exported_at: new Date().toISOString(),
              human_review_required: true,
              note: "2D NMR evidence is supportive connectivity evidence and requires human review.",
              context: {
                sample_id: el("sampleId")?.value || "",
                solvent: el("solvent")?.value || "",
                proton_nmr_text: el("nmrText")?.value || "",
                carbon13_text: el("carbon13Text")?.value || "",
              },
              preview: state.latestNmr2dPreview || null,
              analysis: state.latestNmr2dReport || null,
              saved_run_id: state.latestNmr2dSavedRunId || state.latestNmr2dReport?.run_id || null,
            };
            if (!payload.preview && !payload.analysis) throw new Error("Preview or analyze 2D evidence before exporting.");
            const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            const sampleId = (payload.context.sample_id || "nmr2d").replace(/[^a-zA-Z0-9_-]+/g, "_");
            link.href = url;
            link.download = `${sampleId}_2d_nmr_evidence.json`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
            setJson(payload);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("nmr2dBox")) el("nmr2dBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        async function previewRawNmr2dStub() {
          try {
            const data = await api("/nmr2d/raw/preview", { method: "POST", body: JSON.stringify({}) });
            setJson(data);
            if (el("nmr2dBox")) {
              el("nmr2dBox").innerHTML = `<strong>Raw 2D FID/SER status</strong><p class="muted small">${escapeHtml(data.detail || "Raw 2D processing is not implemented in this guarded release.")}</p>`;
            }
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("nmr2dBox")) el("nmr2dBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function renderCandidateComparison(data) {
          state.latestCandidateComparison = data;
          const box = el("candidateComparisonBox");
          if (!box) return;
          const ranked = Array.isArray(data?.ranked_candidates) ? data.ranked_candidates : [];
          const alerts = Array.isArray(data?.ambiguity_alerts) ? data.ambiguity_alerts : [];
          const notes = Array.isArray(data?.notes) ? data.notes : [];
          const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
          const best = data?.best_candidate || null;
          const rows = ranked.map((item) => {
            const breakdown = item.score_breakdown || {};
            return `
              <tr>
                <td>${escapeHtml(item.rank ?? "—")}</td>
                <td>${escapeHtml(item.name || item.smiles || "—")}</td>
                <td>${escapeHtml(item.role || "—")}</td>
                <td>${escapeHtml(item.smiles || "—")}</td>
                <td>${escapeHtml(item.label || "review")}</td>
                <td>${formatNmr2dPercent(item.total_score)}</td>
                <td>${formatNmr2dPercent(breakdown.proton_score)}</td>
                <td>${formatNmr2dPercent(breakdown.carbon13_score)}</td>
                <td>${formatNmr2dPercent(breakdown.dept_apt_score)}</td>
                <td>${formatNmr2dPercent(breakdown.nmr2d_score)}</td>
                <td>${escapeHtml(Array.isArray(item.contradictions) ? item.contradictions.join("; ") : "")}</td>
              </tr>
            `;
          }).join("");
          const detailBlocks = ranked.map((item) => `
            <div class="panel" style="margin-top:.65rem;">
              <strong>#${escapeHtml(item.rank ?? "—")} ${escapeHtml(item.name || item.smiles || "Candidate")}</strong>
              <div class="small muted" style="margin-top:.25rem;">${escapeHtml([item.formula, item.exact_mass ? `MW ${item.exact_mass}` : ""].filter(Boolean).join(" · ") || "No formula summary.")}</div>
              ${(Array.isArray(item.evidence_summary) && item.evidence_summary.length) ? `<ul>${item.evidence_summary.map((value) => `<li>${escapeHtml(value)}</li>`).join("")}</ul>` : '<p class="muted small">No evidence summary.</p>'}
              ${(Array.isArray(item.warnings) && item.warnings.length) ? `<div class="small" style="color:var(--danger);">Warnings: ${escapeHtml(item.warnings.join("; "))}</div>` : ""}
            </div>
          `).join("");
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>Candidate ranking</strong>
              <span class="status-badge ${getStatusVariant(best?.label || "review")}">${best ? `Best: ${escapeHtml(best.name || best.smiles)}` : "No best candidate"}</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">Candidates</div><div class="value">${escapeHtml(data?.candidate_count ?? ranked.length)}</div></div>
              <div class="metric"><div class="label">Best score</div><div class="value">${formatNmr2dPercent(best?.total_score)}</div></div>
              <div class="metric"><div class="label">Evidence layers</div><div class="value">${escapeHtml((data?.evidence_layers_used || []).join(", ") || "structure only")}</div></div>
              <div class="metric"><div class="label">Review</div><div class="value">required</div></div>
            </div>
            ${alerts.length ? renderNmr2dMessages("Ambiguity alerts", alerts) : ""}
            ${warnings.length ? renderNmr2dMessages("Warnings", warnings) : ""}
            ${notes.length ? renderNmr2dMessages("Notes", notes) : ""}
            ${rows ? `<div style="overflow:auto; margin-top:.8rem;"><table><thead><tr><th>Rank</th><th>Name</th><th>Role</th><th>SMILES</th><th>Label</th><th>Total</th><th>1H</th><th>13C</th><th>DEPT/APT</th><th>2D</th><th>Contradictions</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<p class="muted small">No candidates returned.</p>'}
            ${detailBlocks ? `<details style="margin-top:.8rem;"><summary>Evidence details</summary>${detailBlocks}</details>` : ""}
          `;
        }

        async function compareCandidates() {
          try {
            const candidatesText = el("candidateList")?.value.trim() || "";
            if (!candidatesText) throw new Error("Enter at least one candidate structure.");
            const formData = new FormData();
            formData.append("candidates_text", candidatesText);

            const protonText = el("nmrText") ? el("nmrText").value.trim() : "";
            const carbonText = el("carbon13Text") ? el("carbon13Text").value.trim() : "";
            const solvent = el("solvent") ? el("solvent").value.trim() : "";
            const sampleId = el("sampleId") ? el("sampleId").value.trim() : "";
            if (protonText) formData.append("proton_nmr_text", protonText);
            if (carbonText) formData.append("carbon13_text", carbonText);
            if (solvent) formData.append("solvent", solvent);
            if (sampleId) formData.append("sample_id", sampleId);

            const deptFile = el("deptAptFile") ? el("deptAptFile").files[0] : null;
            const deptExp = el("deptAptExperiment") ? el("deptAptExperiment").value : "";
            const aptPositive = el("deptAptPositive") ? el("deptAptPositive").value : "CH_CH3";
            if (deptFile) formData.append("dept_apt_file", deptFile);
            if (deptExp) formData.append("dept_apt_experiment_type", deptExp);
            formData.append("apt_positive", aptPositive || "CH_CH3");

            const nmr2dFile = el("nmr2dFile") ? el("nmr2dFile").files[0] : null;
            const nmr2dExp = el("nmr2dExperiment") ? el("nmr2dExperiment").value : "";
            if (nmr2dFile) formData.append("nmr2d_file", nmr2dFile);
            if (nmr2dExp) formData.append("nmr2d_experiment_type", nmr2dExp);

            const data = await api("/candidates/compare/evidence", { method: "POST", body: formData });
            setJson(data);
            renderCandidateComparison(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("candidateComparisonBox")) el("candidateComparisonBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function clearCandidateComparison() {
          state.latestCandidateComparison = null;
          if (el("candidateComparisonBox")) el("candidateComparisonBox").innerHTML = "No candidate comparison yet.";
        }

        function renderSpectralSimilarity(data) {
          state.latestSpectralSimilarity = data;
          const box = el("spectralSimilarityBox");
          if (!box) return;
          const layers = Array.isArray(data?.layers) ? data.layers : [];
          const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
          const notes = Array.isArray(data?.notes) ? data.notes : [];
          const layerRows = layers.map((layer) => `
            <tr>
              <td>${escapeHtml(layer.layer || "—")}</td>
              <td>${formatNmr2dPercent(layer.combined_score)}</td>
              <td>${formatNmr2dPercent(layer.vector_score)}</td>
              <td>${formatNmr2dPercent(layer.set_score)}</td>
              <td>${escapeHtml(layer.matched_count ?? 0)}</td>
              <td>${escapeHtml(layer.unmatched_observed_count ?? 0)}</td>
              <td>${escapeHtml(layer.unmatched_reference_count ?? 0)}</td>
            </tr>
          `).join("");
          const detailBlocks = layers.map((layer) => {
            const peakMatches = Array.isArray(layer.matches) ? layer.matches : [];
            const crossMatches = Array.isArray(layer.crosspeak_matches) ? layer.crosspeak_matches : [];
            const peakRows = peakMatches.slice(0, 40).map((match) => `
              <tr><td>${escapeHtml(match.observed_ppm ?? "—")}</td><td>${escapeHtml(match.reference_ppm ?? "—")}</td><td>${escapeHtml(match.delta_ppm ?? "—")}</td><td>${formatNmr2dPercent(match.score)}</td></tr>
            `).join("");
            const crossRows = crossMatches.slice(0, 40).map((match) => `
              <tr><td>${escapeHtml(match.observed_f2_ppm ?? "—")}</td><td>${escapeHtml(match.observed_f1_ppm ?? "—")}</td><td>${escapeHtml(match.reference_f2_ppm ?? "—")}</td><td>${escapeHtml(match.reference_f1_ppm ?? "—")}</td><td>${formatNmr2dPercent(match.score)}</td></tr>
            `).join("");
            return `
              <div class="panel" style="margin-top:.65rem;">
                <strong>${escapeHtml(layer.layer || "Layer")} similarity</strong>
                ${(Array.isArray(layer.notes) && layer.notes.length) ? `<ul class="small muted">${layer.notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul>` : ""}
                ${peakRows ? `<table style="margin-top:.55rem;"><thead><tr><th>Observed ppm</th><th>Reference ppm</th><th>Delta ppm</th><th>Score</th></tr></thead><tbody>${peakRows}</tbody></table>` : ""}
                ${crossRows ? `<table style="margin-top:.55rem;"><thead><tr><th>Observed F2</th><th>Observed F1</th><th>Reference F2</th><th>Reference F1</th><th>Score</th></tr></thead><tbody>${crossRows}</tbody></table>` : ""}
              </div>
            `;
          }).join("");
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>Spectral similarity result</strong>
              <span class="status-badge ${getStatusVariant(data?.label || "review")}">${escapeHtml(data?.label || "similarity")}</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">Overall score</div><div class="value">${formatNmr2dPercent(data?.overall_score)}</div></div>
              <div class="metric"><div class="label">Layers used</div><div class="value">${escapeHtml((data?.evidence_layers_used || []).join(", ") || "—")}</div></div>
              <div class="metric"><div class="label">Layer count</div><div class="value">${escapeHtml(layers.length)}</div></div>
              <div class="metric"><div class="label">Review</div><div class="value">required</div></div>
            </div>
            ${layerRows ? `<div style="overflow:auto; margin-top:.8rem;"><table><thead><tr><th>Layer</th><th>Combined</th><th>Vector score</th><th>Set score</th><th>Matched</th><th>Unmatched observed</th><th>Unmatched reference</th></tr></thead><tbody>${layerRows}</tbody></table></div>` : '<p class="muted small">No comparable layers were scored.</p>'}
            ${warnings.length ? renderNmr2dMessages("Warnings", warnings) : ""}
            ${notes.length ? renderNmr2dMessages("Notes", notes) : ""}
            ${detailBlocks ? `<details style="margin-top:.8rem;"><summary>Peak and cross-peak matches</summary>${detailBlocks}</details>` : ""}
          `;
        }

        function copyCurrentSpectraToSimilarityReference() {
          if (el("similarityReference1H") && el("nmrText")) el("similarityReference1H").value = el("nmrText").value;
          if (el("similarityReference13C") && el("carbon13Text")) el("similarityReference13C").value = el("carbon13Text").value;
        }

        async function scoreSpectralSimilarity() {
          try {
            const formData = new FormData();
            const observed1H = el("nmrText") ? el("nmrText").value.trim() : "";
            const reference1H = el("similarityReference1H") ? el("similarityReference1H").value.trim() : "";
            const observed13C = el("carbon13Text") ? el("carbon13Text").value.trim() : "";
            const reference13C = el("similarityReference13C") ? el("similarityReference13C").value.trim() : "";
            const solvent = el("solvent") ? el("solvent").value.trim() : "";
            const sampleId = el("sampleId") ? el("sampleId").value.trim() : "";
            if (observed1H) formData.append("observed_proton_text", observed1H);
            if (reference1H) formData.append("reference_proton_text", reference1H);
            if (observed13C) formData.append("observed_carbon13_text", observed13C);
            if (reference13C) formData.append("reference_carbon13_text", reference13C);
            if (solvent) formData.append("solvent", solvent);
            if (sampleId) formData.append("sample_id", sampleId);

            const observed2D = el("nmr2dFile") ? el("nmr2dFile").files[0] : null;
            const reference2D = el("similarityReference2DFile") ? el("similarityReference2DFile").files[0] : null;
            const exp = el("similarity2DExperiment") ? el("similarity2DExperiment").value : "";
            if (observed2D) formData.append("observed_nmr2d_file", observed2D);
            if (reference2D) formData.append("reference_nmr2d_file", reference2D);
            if (exp) formData.append("nmr2d_experiment_type", exp);

            const data = await api("/similarity/score/evidence", { method: "POST", body: formData });
            setJson(data);
            renderSpectralSimilarity(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("spectralSimilarityBox")) el("spectralSimilarityBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function clearSpectralSimilarity() {
          state.latestSpectralSimilarity = null;
          if (el("spectralSimilarityBox")) el("spectralSimilarityBox").innerHTML = "No spectral similarity score yet.";
        }

        function renderPredictedNMRMatch(data) {
          state.latestPredictedNMRMatch = data;
          const box = el("predictedNMRMatchBox");
          if (!box) return;
          const ranked = Array.isArray(data?.ranked_candidates) ? data.ranked_candidates : [];
          const alerts = Array.isArray(data?.ambiguity_alerts) ? data.ambiguity_alerts : [];
          const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
          const notes = Array.isArray(data?.notes) ? data.notes : [];
          const best = data?.best_candidate || null;
          const rows = ranked.map((item) => {
            const prediction = item.prediction || {};
            const protonScore = item.proton_similarity ? formatNmr2dPercent(item.proton_similarity.combined_score) : "—";
            const carbonScore = item.carbon13_similarity ? formatNmr2dPercent(item.carbon13_similarity.combined_score) : "—";
            const nmr2dScore = item.nmr2d_similarity ? formatNmr2dPercent(item.nmr2d_similarity.combined_score) : "—";
            return `
              <tr>
                <td>${escapeHtml(item.rank ?? "—")}</td>
                <td><strong>${escapeHtml(item.name || item.smiles || "Candidate")}</strong><div class="small muted">${escapeHtml(item.smiles || "—")}</div></td>
                <td>${formatNmr2dPercent(item.total_score)}</td>
                <td>${protonScore}</td>
                <td>${carbonScore}</td>
                <td>${nmr2dScore}</td>
                <td>${escapeHtml((prediction.proton_peaks || []).length)} 1H / ${escapeHtml((prediction.carbon13_peaks || []).length)} 13C</td>
                <td><span class="status-badge ${getStatusVariant(item.label || "review")}">${escapeHtml(item.label || "review")}</span></td>
              </tr>
            `;
          }).join("");
          const detailBlocks = ranked.map((item) => {
            const prediction = item.prediction || {};
            const protonPeaks = Array.isArray(prediction.proton_peaks) ? prediction.proton_peaks : [];
            const carbonPeaks = Array.isArray(prediction.carbon13_peaks) ? prediction.carbon13_peaks : [];
            const protonRows = protonPeaks.slice(0, 24).map((peak) => `
              <tr><td>${escapeHtml(peak.shift_ppm ?? "—")}</td><td>${escapeHtml(peak.integration_h ?? "—")}</td><td>${escapeHtml(peak.environment || "—")}</td><td>${escapeHtml(peak.uncertainty_ppm ?? "—")}</td></tr>
            `).join("");
            const carbonRows = carbonPeaks.slice(0, 24).map((peak) => `
              <tr><td>${escapeHtml(peak.shift_ppm ?? "—")}</td><td>${escapeHtml(peak.carbon_type || "—")}</td><td>${escapeHtml(peak.environment || "—")}</td><td>${escapeHtml(peak.uncertainty_ppm ?? "—")}</td></tr>
            `).join("");
            return `
              <div class="panel" style="margin-top:.65rem;">
                <strong>#${escapeHtml(item.rank ?? "—")} ${escapeHtml(item.name || item.smiles || "Candidate")}</strong>
                ${(item.evidence_summary || []).length ? `<ul class="small muted">${item.evidence_summary.map((entry) => `<li>${escapeHtml(entry)}</li>`).join("")}</ul>` : ""}
                ${(item.contradictions || []).length ? `<div class="small" style="color:var(--danger);">Contradictions: ${escapeHtml(item.contradictions.join("; "))}</div>` : ""}
                ${(item.warnings || []).length ? `<div class="small muted">Warnings: ${escapeHtml(item.warnings.join("; "))}</div>` : ""}
                <div class="grid2" style="margin-top:.65rem;">
                  <div><strong>Predicted 1H</strong><table style="margin-top:.45rem;"><thead><tr><th>ppm</th><th>int.</th><th>environment</th><th>unc.</th></tr></thead><tbody>${protonRows}</tbody></table></div>
                  <div><strong>Predicted 13C</strong><table style="margin-top:.45rem;"><thead><tr><th>ppm</th><th>type</th><th>environment</th><th>unc.</th></tr></thead><tbody>${carbonRows}</tbody></table></div>
                </div>
              </div>
            `;
          }).join("");
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>Candidate-specific predicted NMR ranking</strong>
              <span class="status-badge ${getStatusVariant(best?.label || "review")}">${best ? `Best: ${escapeHtml(best.name || best.smiles)}` : "No best candidate"}</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">Candidates</div><div class="value">${escapeHtml(data?.candidate_count ?? ranked.length)}</div></div>
              <div class="metric"><div class="label">Best predicted score</div><div class="value">${formatNmr2dPercent(best?.total_score)}</div></div>
              <div class="metric"><div class="label">Evidence layers</div><div class="value">${escapeHtml((data?.evidence_layers_used || []).join(", ") || "—")}</div></div>
              <div class="metric"><div class="label">Prediction engine</div><div class="value">${escapeHtml((data?.metadata || {}).prediction_engine || "heuristic")}</div></div>
            </div>
            ${rows ? `<div style="overflow:auto; margin-top:.8rem;"><table><thead><tr><th>Rank</th><th>Candidate</th><th>Total</th><th>1H predicted</th><th>13C predicted</th><th>2D predicted</th><th>Predicted peaks</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<p class="muted small">No candidates were ranked.</p>'}
            ${alerts.length ? renderNmr2dMessages("Ambiguity alerts", alerts) : ""}
            ${warnings.length ? renderNmr2dMessages("Warnings", warnings) : ""}
            ${notes.length ? renderNmr2dMessages("Notes", notes) : ""}
            ${detailBlocks ? `<details style="margin-top:.8rem;"><summary>Predicted shift details</summary>${detailBlocks}</details>` : ""}
          `;
        }

        function copyCandidateListToPredictedNMR() {
          if (el("candidateList") && el("predictedCandidateList")) {
            el("predictedCandidateList").value = el("candidateList").value;
          }
        }

        async function runPredictedNMRMatch() {
          try {
            const candidatesText = el("predictedCandidateList").value.trim();
            if (!candidatesText) throw new Error("Enter at least one candidate structure.");
            const formData = new FormData();
            formData.append("candidates_text", candidatesText);
            const protonText = el("nmrText") ? el("nmrText").value.trim() : "";
            const carbonText = el("carbon13Text") ? el("carbon13Text").value.trim() : "";
            const solvent = el("solvent") ? el("solvent").value.trim() : "";
            const sampleId = el("sampleId") ? el("sampleId").value.trim() : "";
            if (protonText) formData.append("observed_proton_text", protonText);
            if (carbonText) formData.append("observed_carbon13_text", carbonText);
            if (solvent) formData.append("solvent", solvent);
            if (sampleId) formData.append("sample_id", sampleId);

            const nmr2dFile = el("nmr2dFile") ? el("nmr2dFile").files[0] : null;
            const nmr2dExp = el("nmr2dExperiment") ? el("nmr2dExperiment").value : "";
            if (nmr2dFile) formData.append("observed_nmr2d_file", nmr2dFile);
            if (nmr2dExp) formData.append("nmr2d_experiment_type", nmr2dExp);

            const data = await api("/prediction/nmr/match/evidence", { method: "POST", body: formData });
            setJson(data);
            renderPredictedNMRMatch(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("predictedNMRMatchBox")) el("predictedNMRMatchBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function clearPredictedNMRMatch() {
          state.latestPredictedNMRMatch = null;
          if (el("predictedNMRMatchBox")) el("predictedNMRMatchBox").innerHTML = "No candidate-specific predicted NMR match yet.";
        }

        function renderHRMSMatch(data) {
          state.latestHRMSMatch = data;
          const box = el("hrmsMatchBox");
          if (!box) return;
          const ranked = Array.isArray(data?.ranked_candidates) ? data.ranked_candidates : [];
          const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
          const notes = Array.isArray(data?.notes) ? data.notes : [];
          const best = data?.best_match || null;
          const rows = ranked.map((item) => `
            <tr>
              <td>${escapeHtml(item.rank ?? "—")}</td>
              <td><strong>${escapeHtml(item.name || item.smiles || "Candidate")}</strong><div class="small muted">${escapeHtml(item.smiles || "—")}</div></td>
              <td>${prettyFormula(item.formula || "—")}</td>
              <td>${escapeHtml(item.theoretical_mz ?? "—")}</td>
              <td>${item.ppm_error !== null && item.ppm_error !== undefined ? escapeHtml(item.ppm_error) : "—"}</td>
              <td>${formatNmr2dPercent(item.ppm_score)}</td>
              <td>${escapeHtml(item.dbe ?? "—")}</td>
              <td><span class="status-badge ${getStatusVariant(item.label || "review")}">${escapeHtml(item.label || "review")}</span></td>
            </tr>
          `).join("");
          const detailBlocks = ranked.map((item) => `
            <div class="panel" style="margin-top:.65rem;">
              <strong>#${escapeHtml(item.rank ?? "—")} ${escapeHtml(item.name || item.smiles || "Candidate")}</strong>
              ${(item.evidence_summary || []).length ? `<ul class="small muted">${item.evidence_summary.map((entry) => `<li>${escapeHtml(entry)}</li>`).join("")}</ul>` : ""}
              ${(item.warnings || []).length ? `<div class="small" style="color:var(--danger);">${escapeHtml(item.warnings.join("; "))}</div>` : ""}
            </div>
          `).join("");
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>HRMS candidate constraint result</strong>
              <span class="status-badge ${data?.exact_match_count ? "ok" : data?.possible_match_count ? "warn" : "bad"}">${escapeHtml(data?.exact_match_count || 0)} exact match(es)</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">Observed m/z</div><div class="value">${escapeHtml(data?.observed_mz ?? "—")}</div></div>
              <div class="metric"><div class="label">Adduct</div><div class="value">${escapeHtml((data?.adduct || {}).name || "—")}</div></div>
              <div class="metric"><div class="label">Tolerance</div><div class="value">${escapeHtml(data?.ppm_tolerance ?? "—")} ppm</div></div>
              <div class="metric"><div class="label">Best</div><div class="value">${best ? escapeHtml(best.name || best.smiles) : "—"}</div></div>
            </div>
            ${rows ? `<div style="overflow:auto; margin-top:.8rem;"><table><thead><tr><th>Rank</th><th>Candidate</th><th>Formula</th><th>Theoretical m/z</th><th>ppm error</th><th>Score</th><th>DBE/IHD</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<p class="muted small">No HRMS candidates were ranked.</p>'}
            ${warnings.length ? renderNmr2dMessages("Warnings", warnings) : ""}
            ${notes.length ? renderNmr2dMessages("Notes", notes) : ""}
            ${detailBlocks ? `<details style="margin-top:.8rem;"><summary>HRMS evidence details</summary>${detailBlocks}</details>` : ""}
          `;
        }

        function renderHRMSFormulaSearch(data) {
          state.latestHRMSFormulaSearch = data;
          const box = el("hrmsFormulaBox");
          if (!box) return;
          const formulas = Array.isArray(data?.formulas) ? data.formulas : [];
          const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
          const rows = formulas.map((formula) => `
            <tr>
              <td>${prettyFormula(formula.formula || "—")}</td>
              <td>${escapeHtml(formula.exact_mass ?? "—")}</td>
              <td>${escapeHtml(formula.dbe ?? "—")}</td>
              <td>${escapeHtml(formula.isotope_m_plus_1_percent ?? "—")}</td>
              <td>${escapeHtml(formula.isotope_m_plus_2_percent ?? "—")}</td>
            </tr>
          `).join("");
          box.innerHTML = `
            <strong>Formula search</strong>
            <div class="summary-grid">
              <div class="metric"><div class="label">Neutral mass</div><div class="value">${escapeHtml(data?.neutral_mass ?? "—")}</div></div>
              <div class="metric"><div class="label">Results</div><div class="value">${escapeHtml(data?.formula_count ?? formulas.length)}</div></div>
            </div>
            ${warnings.length ? renderNmr2dMessages("Warnings", warnings) : ""}
            ${rows ? `<div style="overflow:auto; margin-top:.65rem;"><table><thead><tr><th>Formula</th><th>Exact mass</th><th>DBE/IHD</th><th>M+1%</th><th>M+2%</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<p class="muted small">No formulas matched the selected bounds.</p>'}
          `;
        }

        function copyCandidateListToHRMS() {
          if (el("candidateList") && el("hrmsCandidateList")) {
            el("hrmsCandidateList").value = el("candidateList").value;
          } else if (el("predictedCandidateList") && el("hrmsCandidateList")) {
            el("hrmsCandidateList").value = el("predictedCandidateList").value;
          }
        }

        function hrmsCommonFormData(includeCandidates=true) {
          const formData = new FormData();
          const observedMz = el("hrmsObservedMz") ? el("hrmsObservedMz").value.trim() : "";
          const adduct = el("hrmsAdduct") ? el("hrmsAdduct").value : "";
          const ionMode = el("hrmsIonMode") ? el("hrmsIonMode").value : "";
          const ppmTolerance = el("hrmsPpmTolerance") ? el("hrmsPpmTolerance").value.trim() : "";
          const m1 = el("hrmsMPlus1") ? el("hrmsMPlus1").value.trim() : "";
          const m2 = el("hrmsMPlus2") ? el("hrmsMPlus2").value.trim() : "";
          if (!observedMz) throw new Error("Enter observed HRMS m/z.");
          formData.append("observed_mz", observedMz);
          formData.append("adduct", adduct || "[M+H]+");
          if (ionMode) formData.append("ion_mode", ionMode);
          formData.append("ppm_tolerance", ppmTolerance || "5");
          if (m1) formData.append("observed_m_plus_1_percent", m1);
          if (m2) formData.append("observed_m_plus_2_percent", m2);
          const sampleId = el("sampleId") ? el("sampleId").value.trim() : "";
          if (sampleId) formData.append("sample_id", sampleId);
          if (includeCandidates) {
            const candidatesText = el("hrmsCandidateList") ? el("hrmsCandidateList").value.trim() : "";
            if (!candidatesText) throw new Error("Enter at least one candidate SMILES for HRMS matching.");
            formData.append("candidates_text", candidatesText);
          }
          return formData;
        }

        async function runHRMSCandidateMatch() {
          try {
            const data = await api("/ms/hrms/candidates/match/evidence", { method: "POST", body: hrmsCommonFormData(true) });
            setJson(data);
            renderHRMSMatch(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("hrmsMatchBox")) el("hrmsMatchBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        async function searchHRMSFormulas() {
          try {
            const observedMz = el("hrmsObservedMz") ? el("hrmsObservedMz").value.trim() : "";
            if (!observedMz) throw new Error("Enter observed HRMS m/z.");
            const payload = {
              observed_mz: Number(observedMz),
              adduct: el("hrmsAdduct") ? el("hrmsAdduct").value || "[M+H]+" : "[M+H]+",
              ppm_tolerance: Number((el("hrmsPpmTolerance") ? el("hrmsPpmTolerance").value : "5") || "5"),
              max_c: Number((el("hrmsMaxC") ? el("hrmsMaxC").value : "20") || "20"),
              max_results: Number((el("hrmsMaxResults") ? el("hrmsMaxResults").value : "50") || "50")
            };
            const data = await api("/ms/hrms/formulas/search", { method: "POST", body: JSON.stringify(payload) });
            setJson(data);
            renderHRMSFormulaSearch(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("hrmsFormulaBox")) el("hrmsFormulaBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function clearHRMSMatch() {
          state.latestHRMSMatch = null;
          state.latestHRMSFormulaSearch = null;
          if (el("hrmsMatchBox")) el("hrmsMatchBox").innerHTML = "No HRMS candidate match yet.";
          if (el("hrmsFormulaBox")) el("hrmsFormulaBox").innerHTML = "No formula search yet.";
        }

        function renderAdductInference(data) {
          state.latestAdductInference = data;
          const box = el("adductInferenceBox");
          if (!box) return;
          const clusters = Array.isArray(data?.isotope_clusters) ? data.isotope_clusters : [];
          const candidates = Array.isArray(data?.adduct_candidates) ? data.adduct_candidates : [];
          const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
          const notes = Array.isArray(data?.notes) ? data.notes : [];
          const best = data?.best_adduct_candidate || null;
          const clusterRows = clusters.map((cluster) => `
            <tr>
              <td>${escapeHtml(cluster.monoisotopic_mz ?? "—")}</td>
              <td>${escapeHtml(cluster.charge ?? "—")}</td>
              <td>${cluster.m_plus_1_percent !== null && cluster.m_plus_1_percent !== undefined ? escapeHtml(cluster.m_plus_1_percent) : "—"}</td>
              <td>${cluster.m_plus_2_percent !== null && cluster.m_plus_2_percent !== undefined ? escapeHtml(cluster.m_plus_2_percent) : "—"}</td>
              <td>${cluster.estimated_carbon_count !== null && cluster.estimated_carbon_count !== undefined ? escapeHtml(cluster.estimated_carbon_count) : "—"}</td>
              <td>${escapeHtml(cluster.halogen_signature || "—")}</td>
              <td><span class="status-badge ${getStatusVariant(cluster.label || "review")}">${escapeHtml(cluster.label || "review")}</span></td>
              <td>${formatNmr2dPercent(cluster.confidence_score)}</td>
            </tr>
          `).join("");
          const candidateRows = candidates.map((item) => `
            <tr>
              <td>${escapeHtml(item.rank ?? "—")}</td>
              <td><strong>${escapeHtml((item.adduct || {}).name || "—")}</strong><div class="small muted">${escapeHtml((item.adduct || {}).description || "")}</div></td>
              <td>${escapeHtml(item.neutral_mass ?? "—")}</td>
              <td>${escapeHtml(item.formula_count || 0)}</td>
              <td>${(item.top_formulas || []).length ? prettyFormula(item.top_formulas[0].formula) : "—"}</td>
              <td>${escapeHtml(item.adduct_pair_count || 0)}</td>
              <td><span class="status-badge ${getStatusVariant(item.label || "review")}">${escapeHtml(item.label || "review")}</span></td>
              <td>${formatNmr2dPercent(item.candidate_score)}</td>
            </tr>
          `).join("");
          const details = candidates.map((item) => {
            const pairRows = (item.adduct_peak_matches || []).map((match) => `
              <tr>
                <td>${escapeHtml(match.adduct || "—")}</td>
                <td>${escapeHtml(match.observed_mz ?? "—")}</td>
                <td>${escapeHtml(match.expected_mz ?? "—")}</td>
                <td>${escapeHtml(match.ppm_error ?? "—")}</td>
                <td>${escapeHtml(match.relative_intensity ?? "—")}%</td>
              </tr>
            `).join("");
            const formulaRows = (item.top_formulas || []).slice(0, 8).map((formula) => `
              <tr>
                <td>${prettyFormula(formula.formula || "—")}</td>
                <td>${escapeHtml(formula.exact_mass ?? "—")}</td>
                <td>${formula.dbe !== null && formula.dbe !== undefined ? escapeHtml(formula.dbe) : "—"}</td>
                <td>${formula.isotope_m_plus_1_percent !== null && formula.isotope_m_plus_1_percent !== undefined ? escapeHtml(formula.isotope_m_plus_1_percent) : "—"}</td>
                <td>${formula.isotope_m_plus_2_percent !== null && formula.isotope_m_plus_2_percent !== undefined ? escapeHtml(formula.isotope_m_plus_2_percent) : "—"}</td>
              </tr>
            `).join("");
            return `
              <div class="panel" style="margin-top:.65rem;">
                <strong>#${escapeHtml(item.rank ?? "—")} ${escapeHtml((item.adduct || {}).name || "Adduct")}</strong>
                ${(item.evidence_summary || []).length ? `<ul class="small muted">${item.evidence_summary.map((entry) => `<li>${escapeHtml(entry)}</li>`).join("")}</ul>` : ""}
                ${formulaRows ? `<div style="overflow:auto; margin-top:.55rem;"><table><thead><tr><th>Formula</th><th>Exact mass</th><th>DBE</th><th>M+1 %</th><th>M+2 %</th></tr></thead><tbody>${formulaRows}</tbody></table></div>` : ""}
                ${pairRows ? `<div style="overflow:auto; margin-top:.55rem;"><table><thead><tr><th>Paired adduct</th><th>Observed m/z</th><th>Expected m/z</th><th>ppm</th><th>Rel. intensity</th></tr></thead><tbody>${pairRows}</tbody></table></div>` : ""}
                ${(item.warnings || []).length ? `<div class="small" style="color:var(--danger); margin-top:.45rem;">${escapeHtml(item.warnings.join("; "))}</div>` : ""}
              </div>
            `;
          }).join("");
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>Adduct + isotope inference result</strong>
              <span class="status-badge ${best ? getStatusVariant(best.label || "review") : "warn"}">${best ? `${escapeHtml((best.adduct || {}).name || "best adduct")} · ${formatNmr2dPercent(best.candidate_score)}` : "no adduct"}</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">Primary m/z</div><div class="value">${escapeHtml(data?.primary_mz ?? "—")}</div></div>
              <div class="metric"><div class="label">Ion mode</div><div class="value">${escapeHtml(data?.ion_mode || "—")}</div></div>
              <div class="metric"><div class="label">Peaks analyzed</div><div class="value">${escapeHtml(data?.analyzed_peak_count ?? 0)} / ${escapeHtml(data?.peak_count ?? 0)}</div></div>
              <div class="metric"><div class="label">Inferred charge</div><div class="value">${escapeHtml(data?.inferred_charge || "—")}</div></div>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">M+1 %</div><div class="value">${data?.inferred_m_plus_1_percent !== null && data?.inferred_m_plus_1_percent !== undefined ? escapeHtml(data.inferred_m_plus_1_percent) : "—"}</div></div>
              <div class="metric"><div class="label">M+2 %</div><div class="value">${data?.inferred_m_plus_2_percent !== null && data?.inferred_m_plus_2_percent !== undefined ? escapeHtml(data.inferred_m_plus_2_percent) : "—"}</div></div>
              <div class="metric"><div class="label">Best adduct</div><div class="value">${best ? escapeHtml((best.adduct || {}).name || "—") : "—"}</div></div>
              <div class="metric"><div class="label">Formula count</div><div class="value">${best ? escapeHtml(best.formula_count || 0) : "—"}</div></div>
            </div>
            ${warnings.length ? renderNmr2dMessages("Warnings", warnings) : ""}
            ${notes.length ? renderNmr2dMessages("Notes", notes) : ""}
            <div class="panel" style="margin-top:.8rem;">
              <strong>Isotope clusters</strong>
              ${clusterRows ? `<div style="overflow:auto; margin-top:.55rem;"><table><thead><tr><th>m/z M</th><th>z</th><th>M+1 %</th><th>M+2 %</th><th>Carbon est.</th><th>Halogen signature</th><th>Status</th><th>Score</th></tr></thead><tbody>${clusterRows}</tbody></table></div>` : '<p class="muted small">No isotope clusters detected within the selected tolerance.</p>'}
            </div>
            <div class="panel" style="margin-top:.8rem;">
              <strong>Ranked adduct hypotheses</strong>
              ${candidateRows ? `<div style="overflow:auto; margin-top:.55rem;"><table><thead><tr><th>Rank</th><th>Adduct</th><th>Neutral mass</th><th>Formula count</th><th>Top formula</th><th>Paired peaks</th><th>Status</th><th>Score</th></tr></thead><tbody>${candidateRows}</tbody></table></div>` : '<p class="muted small">No adduct hypotheses were generated.</p>'}
            </div>
            ${details ? `<details style="margin-top:.8rem;"><summary>Adduct/formula evidence details</summary>${details}</details>` : ""}
          `;
        }

        function adductInferenceFormData() {
          const formData = new FormData();
          const peakText = el("adductPeakList") ? el("adductPeakList").value.trim() : "";
          if (!peakText) throw new Error("Enter a processed MS1/HRMS peak list.");
          formData.append("peak_list_text", peakText);
          formData.append("ion_mode", el("adductIonMode") ? el("adductIonMode").value || "positive" : "positive");
          const targetMz = el("adductTargetMz") ? el("adductTargetMz").value.trim() : "";
          if (targetMz) formData.append("target_mz", targetMz);
          formData.append("mz_tolerance_da", (el("adductMzToleranceDa") ? el("adductMzToleranceDa").value.trim() : "") || "0.02");
          formData.append("ppm_tolerance", (el("adductPpmTolerance") ? el("adductPpmTolerance").value.trim() : "") || "10");
          formData.append("isotope_mz_tolerance_da", (el("adductIsotopeToleranceDa") ? el("adductIsotopeToleranceDa").value.trim() : "") || "0.02");
          formData.append("min_relative_intensity", (el("adductMinRelIntensity") ? el("adductMinRelIntensity").value.trim() : "") || "0.2");
          formData.append("max_peaks_to_analyze", (el("adductMaxPeaks") ? el("adductMaxPeaks").value.trim() : "") || "200");
          formData.append("max_charge", (el("adductMaxCharge") ? el("adductMaxCharge").value.trim() : "") || "3");
          formData.append("perform_formula_search", el("adductFormulaSearch") && el("adductFormulaSearch").checked ? "true" : "false");
          formData.append("max_c", (el("adductMaxC") ? el("adductMaxC").value.trim() : "") || "20");
          formData.append("formula_candidates_per_adduct", (el("adductFormulaPerAdduct") ? el("adductFormulaPerAdduct").value.trim() : "") || "5");
          const sampleId = el("sampleId") ? el("sampleId").value.trim() : "";
          if (sampleId) formData.append("sample_id", sampleId);
          return formData;
        }

        async function runAdductInference() {
          try {
            const data = await api("/ms/adducts/infer/evidence", { method: "POST", body: adductInferenceFormData() });
            setJson(data);
            renderAdductInference(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("adductInferenceBox")) el("adductInferenceBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function copyHRMSToAdductInference() {
          if (el("hrmsObservedMz") && el("adductTargetMz")) el("adductTargetMz").value = el("hrmsObservedMz").value;
          if (el("hrmsIonMode") && el("adductIonMode") && el("hrmsIonMode").value) el("adductIonMode").value = el("hrmsIonMode").value;
          if (el("hrmsPpmTolerance") && el("adductPpmTolerance")) el("adductPpmTolerance").value = el("hrmsPpmTolerance").value;
        }

        function applyBestAdductInference() {
          const best = state.latestAdductInference && state.latestAdductInference.best_adduct_candidate;
          if (!best) return;
          const adductName = (best.adduct || {}).name || "[M+H]+";
          if (el("hrmsObservedMz")) el("hrmsObservedMz").value = String(best.observed_mz || "");
          if (el("hrmsAdduct")) el("hrmsAdduct").value = adductName;
          if (el("msmsPrecursorMz")) el("msmsPrecursorMz").value = String(best.observed_mz || "");
          if (el("msmsAdduct")) el("msmsAdduct").value = adductName;
          if (state.latestAdductInference.inferred_m_plus_1_percent !== null && state.latestAdductInference.inferred_m_plus_1_percent !== undefined && el("hrmsMPlus1")) {
            el("hrmsMPlus1").value = String(state.latestAdductInference.inferred_m_plus_1_percent);
          }
          if (state.latestAdductInference.inferred_m_plus_2_percent !== null && state.latestAdductInference.inferred_m_plus_2_percent !== undefined && el("hrmsMPlus2")) {
            el("hrmsMPlus2").value = String(state.latestAdductInference.inferred_m_plus_2_percent);
          }
        }

        function clearAdductInference() {
          state.latestAdductInference = null;
          if (el("adductInferenceBox")) el("adductInferenceBox").innerHTML = "No adduct/isotope inference yet.";
        }

        function renderMSMSAnnotation(data) {
          state.latestMSMSAnnotation = data;
          const box = el("msmsAnnotationBox");
          if (!box) return;
          const ranked = Array.isArray(data?.ranked_candidates) ? data.ranked_candidates : [];
          const losses = Array.isArray(data?.neutral_loss_hits) ? data.neutral_loss_hits : [];
          const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
          const notes = Array.isArray(data?.notes) ? data.notes : [];
          const best = data?.best_candidate || null;
          const lossRows = losses.map((hit) => `
            <tr>
              <td>${escapeHtml(hit.fragment_mz ?? "—")}</td>
              <td><strong>${prettyFormula(hit.loss_name || "—")}</strong></td>
              <td>${escapeHtml(hit.observed_loss_da ?? "—")}</td>
              <td>${escapeHtml(hit.error_da ?? "—")}</td>
              <td>${escapeHtml(hit.relative_intensity ?? "—")}%</td>
              <td>${escapeHtml(hit.interpretation || "")}</td>
            </tr>
          `).join("");
          const rows = ranked.map((item) => `
            <tr>
              <td>${escapeHtml(item.rank ?? "—")}</td>
              <td><strong>${escapeHtml(item.name || item.smiles || "Candidate")}</strong><div class="small muted">${escapeHtml(item.smiles || "—")}</div></td>
              <td>${prettyFormula(item.formula || "—")}</td>
              <td>${item.precursor_ppm_error !== null && item.precursor_ppm_error !== undefined ? escapeHtml(item.precursor_ppm_error) : "—"}</td>
              <td>${escapeHtml(item.explained_peak_count || 0)}</td>
              <td>${formatNmr2dPercent(item.explained_intensity_fraction)}</td>
              <td>${escapeHtml(item.fragment_match_count || 0)}</td>
              <td><span class="status-badge ${getStatusVariant(item.label || "review")}">${escapeHtml(item.label || "review")}</span></td>
              <td>${formatNmr2dPercent(item.candidate_score)}</td>
            </tr>
          `).join("");
          const details = ranked.map((item) => {
            const fragmentRows = (item.fragment_matches || []).slice(0, 14).map((match) => `
              <tr><td>${escapeHtml(match.peak_mz ?? "—")}</td><td>${escapeHtml(match.theoretical_mz ?? "—")}</td><td>${escapeHtml(match.ppm_error ?? "—")}</td><td>${prettyFormula(match.formula || "—")}</td><td>${escapeHtml(match.fragment_type || "fragment")}</td></tr>
            `).join("");
            return `
              <div class="panel" style="margin-top:.65rem;">
                <strong>#${escapeHtml(item.rank ?? "—")} ${escapeHtml(item.name || item.smiles || "Candidate")}</strong>
                ${(item.evidence_summary || []).length ? `<ul class="small muted">${item.evidence_summary.map((entry) => `<li>${escapeHtml(entry)}</li>`).join("")}</ul>` : ""}
                ${fragmentRows ? `<table style="margin-top:.5rem;"><thead><tr><th>Peak</th><th>Theory</th><th>ppm</th><th>Formula</th><th>Type</th></tr></thead><tbody>${fragmentRows}</tbody></table>` : ""}
                ${(item.warnings || []).length ? `<div class="small" style="color:var(--danger);">${escapeHtml(item.warnings.join("; "))}</div>` : ""}
              </div>
            `;
          }).join("");
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>Processed MS/MS annotation result</strong>
              <span class="status-badge ${best ? getStatusVariant(best.label || "review") : "warn"}">${best ? `${formatNmr2dPercent(best.candidate_score)} best score` : "neutral losses only"}</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">Precursor m/z</div><div class="value">${escapeHtml(data?.precursor_mz ?? "—")}</div></div>
              <div class="metric"><div class="label">Adduct</div><div class="value">${escapeHtml((data?.adduct || {}).name || "—")}</div></div>
              <div class="metric"><div class="label">Peaks</div><div class="value">${escapeHtml(data?.peak_count ?? "—")} total</div></div>
              <div class="metric"><div class="label">Annotated</div><div class="value">${escapeHtml(data?.annotated_peak_count ?? 0)} peak(s)</div></div>
            </div>
            ${warnings.length ? renderNmr2dMessages("Warnings", warnings) : ""}
            ${notes.length ? renderNmr2dMessages("Notes", notes) : ""}
            <div class="panel" style="margin-top:.8rem;">
              <strong>Neutral-loss annotations</strong>
              ${lossRows ? `<div style="overflow:auto; margin-top:.55rem;"><table><thead><tr><th>Fragment m/z</th><th>Loss</th><th>Observed loss</th><th>Error Da</th><th>Rel. intensity</th><th>Interpretation</th></tr></thead><tbody>${lossRows}</tbody></table></div>` : '<p class="muted small">No common neutral-loss annotations within tolerance.</p>'}
            </div>
            ${rows ? `<div class="panel" style="margin-top:.8rem;"><strong>Ranked candidate MS/MS support</strong><div style="overflow:auto; margin-top:.55rem;"><table><thead><tr><th>Rank</th><th>Candidate</th><th>Formula</th><th>Precursor ppm</th><th>Explained peaks</th><th>Intensity explained</th><th>Fragments</th><th>Status</th><th>Score</th></tr></thead><tbody>${rows}</tbody></table></div></div>` : ""}
            ${details ? `<details style="margin-top:.8rem;"><summary>MS/MS candidate evidence details</summary>${details}</details>` : ""}
          `;
        }

        function copyCandidatesToMSMS() {
          if (el("candidateList") && el("msmsCandidateList")) {
            el("msmsCandidateList").value = el("candidateList").value;
          } else if (el("hrmsCandidateList") && el("msmsCandidateList")) {
            el("msmsCandidateList").value = el("hrmsCandidateList").value;
          }
        }

        function copyHRMSToMSMS() {
          if (el("hrmsObservedMz") && el("msmsPrecursorMz")) el("msmsPrecursorMz").value = el("hrmsObservedMz").value;
          if (el("hrmsAdduct") && el("msmsAdduct")) el("msmsAdduct").value = el("hrmsAdduct").value;
          if (el("hrmsCandidateList") && el("msmsCandidateList")) el("msmsCandidateList").value = el("hrmsCandidateList").value;
        }

        function msmsFormData() {
          const formData = new FormData();
          const precursorMz = el("msmsPrecursorMz") ? el("msmsPrecursorMz").value.trim() : "";
          const peakText = el("msmsPeakList") ? el("msmsPeakList").value.trim() : "";
          if (!precursorMz) throw new Error("Enter precursor m/z.");
          if (!peakText) throw new Error("Enter a processed MS/MS peak list.");
          formData.append("precursor_mz", precursorMz);
          formData.append("adduct", el("msmsAdduct") ? el("msmsAdduct").value || "[M+H]+" : "[M+H]+");
          formData.append("mz_tolerance_da", (el("msmsToleranceDa") ? el("msmsToleranceDa").value.trim() : "") || "0.02");
          formData.append("ppm_tolerance", (el("msmsPpmTolerance") ? el("msmsPpmTolerance").value.trim() : "") || "20");
          formData.append("min_relative_intensity", (el("msmsMinRelIntensity") ? el("msmsMinRelIntensity").value.trim() : "") || "1");
          formData.append("max_peaks_to_annotate", (el("msmsMaxPeaks") ? el("msmsMaxPeaks").value.trim() : "") || "50");
          formData.append("peak_list_text", peakText);
          const candidatesText = el("msmsCandidateList") ? el("msmsCandidateList").value.trim() : "";
          if (candidatesText) formData.append("candidates_text", candidatesText);
          const sampleId = el("sampleId") ? el("sampleId").value.trim() : "";
          if (sampleId) formData.append("sample_id", sampleId);
          return formData;
        }

        async function runMSMSAnnotation() {
          try {
            const data = await api("/ms/msms/annotate/evidence", { method: "POST", body: msmsFormData() });
            setJson(data);
            renderMSMSAnnotation(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("msmsAnnotationBox")) el("msmsAnnotationBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function clearMSMSAnnotation() {
          state.latestMSMSAnnotation = null;
          if (el("msmsAnnotationBox")) el("msmsAnnotationBox").innerHTML = "No MS/MS annotation yet.";
        }

        function renderFragmentationTree(data) {
          state.latestFragmentationTree = data;
          const box = el("fragmentationTreeBox");
          if (!box) return;
          const ranked = Array.isArray(data?.ranked_candidates) ? data.ranked_candidates : [];
          const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
          const notes = Array.isArray(data?.notes) ? data.notes : [];
          const best = data?.best_candidate || null;
          const globalLosses = Array.isArray(data?.global_neutral_loss_hits) ? data.global_neutral_loss_hits : [];
          const lossRows = globalLosses.slice(0, 24).map((hit) => `
            <tr>
              <td>${escapeHtml(hit.fragment_mz ?? "—")}</td>
              <td><strong>${prettyFormula(hit.loss_name || "—")}</strong></td>
              <td>${escapeHtml(hit.observed_loss_da ?? "—")}</td>
              <td>${escapeHtml(hit.error_da ?? "—")}</td>
              <td>${escapeHtml(hit.relative_intensity ?? "—")}%</td>
              <td>${escapeHtml(hit.interpretation || "")}</td>
            </tr>
          `).join("");
          const candidateRows = ranked.map((item) => `
            <tr>
              <td>${escapeHtml(item.rank ?? "—")}</td>
              <td><strong>${escapeHtml(item.name || item.smiles || "Candidate")}</strong><div class="small muted">${escapeHtml(item.smiles || "—")}</div></td>
              <td>${prettyFormula(item.formula || "—")}</td>
              <td>${item.precursor_ppm_error !== null && item.precursor_ppm_error !== undefined ? escapeHtml(item.precursor_ppm_error) : "—"}</td>
              <td>${escapeHtml(item.explained_peak_count || 0)}</td>
              <td>${formatNmr2dPercent(item.explained_intensity_fraction)}</td>
              <td>${escapeHtml(item.max_tree_depth || 0)}</td>
              <td>${escapeHtml(item.diagnostic_loss_count || 0)}</td>
              <td>${escapeHtml(item.contradiction_count || 0)}</td>
              <td><span class="status-badge ${getStatusVariant(item.label || "review")}">${escapeHtml(item.label || "review")}</span></td>
              <td>${formatNmr2dPercent(item.tree_score)}</td>
            </tr>
          `).join("");
          const details = ranked.map((item) => {
            const diagnosticRows = (item.diagnostic_hits || []).slice(0, 20).map((hit) => `
              <tr>
                <td>${prettyFormula(hit.loss_name || "—")}</td>
                <td>${escapeHtml(hit.fragment_mz ?? "—")}</td>
                <td>${escapeHtml(hit.observed_loss_da ?? "—")}</td>
                <td>${escapeHtml(hit.relative_intensity ?? "—")}%</td>
                <td>${escapeHtml(hit.diagnostic_class || "")}</td>
                <td>${hit.chemically_plausible ? "yes" : "no"}</td>
              </tr>
            `).join("");
            const edgeRows = (item.edges || []).slice(0, 35).map((edge) => `
              <tr>
                <td>${escapeHtml(edge.parent_id || "—")}</td>
                <td>${escapeHtml(edge.child_id || "—")}</td>
                <td>${escapeHtml(edge.relation_type || "—")}</td>
                <td>${edge.loss_name ? prettyFormula(edge.loss_name) : "—"}</td>
                <td>${edge.error_da !== null && edge.error_da !== undefined ? escapeHtml(edge.error_da) : "—"}</td>
                <td>${edge.ppm_error !== null && edge.ppm_error !== undefined ? escapeHtml(edge.ppm_error) : "—"}</td>
                <td>${escapeHtml(edge.explanation || "")}</td>
              </tr>
            `).join("");
            return `
              <div class="panel" style="margin-top:.65rem;">
                <strong>#${escapeHtml(item.rank ?? "—")} ${escapeHtml(item.name || item.smiles || "Candidate")}</strong>
                ${(item.evidence_summary || []).length ? `<ul class="small muted">${item.evidence_summary.map((entry) => `<li>${escapeHtml(entry)}</li>`).join("")}</ul>` : ""}
                ${diagnosticRows ? `<div style="overflow:auto; margin-top:.55rem;"><strong>Diagnostic-loss table</strong><table style="margin-top:.45rem;"><thead><tr><th>Loss</th><th>Fragment</th><th>Observed loss</th><th>Rel. intensity</th><th>Class</th><th>Supported?</th></tr></thead><tbody>${diagnosticRows}</tbody></table></div>` : ""}
                ${edgeRows ? `<div style="overflow:auto; margin-top:.55rem;"><strong>Edge table</strong><table style="margin-top:.45rem;"><thead><tr><th>Parent</th><th>Child</th><th>Type</th><th>Loss</th><th>Error Da</th><th>ppm</th><th>Explanation</th></tr></thead><tbody>${edgeRows}</tbody></table></div>` : ""}
                ${(item.contradiction_flags || []).length ? `<div class="panel" style="margin-top:.65rem; border-color:rgba(248,81,73,.45);"><strong>Contradiction flags</strong><ul>${item.contradiction_flags.map((entry) => `<li>${escapeHtml(entry)}</li>`).join("")}</ul></div>` : ""}
                ${(item.warnings || []).length ? `<div class="small" style="color:var(--danger); margin-top:.45rem;">${escapeHtml(item.warnings.join("; "))}</div>` : ""}
              </div>
            `;
          }).join("");
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>MS/MS fragmentation-tree result</strong>
              <span class="status-badge ${best ? getStatusVariant(best.label || "review") : "warn"}">${best ? `${formatNmr2dPercent(best.tree_score)} tree score` : "no candidates"}</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">Precursor m/z</div><div class="value">${escapeHtml(data?.precursor_mz ?? "—")}</div></div>
              <div class="metric"><div class="label">Adduct</div><div class="value">${escapeHtml((data?.adduct || {}).name || "—")}</div></div>
              <div class="metric"><div class="label">Peaks analyzed</div><div class="value">${escapeHtml(data?.analyzed_peak_count ?? 0)} / ${escapeHtml(data?.peak_count ?? 0)}</div></div>
              <div class="metric"><div class="label">Best candidate</div><div class="value">${best ? escapeHtml(best.name || best.smiles || "—") : "—"}</div></div>
            </div>
            ${warnings.length ? renderNmr2dMessages("Warnings", warnings) : ""}
            ${notes.length ? renderNmr2dMessages("Notes", notes) : ""}
            <div class="panel" style="margin-top:.8rem;">
              <strong>Global neutral-loss hits</strong>
              ${lossRows ? `<div style="overflow:auto; margin-top:.55rem;"><table><thead><tr><th>Fragment</th><th>Loss</th><th>Observed loss</th><th>Error Da</th><th>Rel. intensity</th><th>Interpretation</th></tr></thead><tbody>${lossRows}</tbody></table></div>` : '<p class="muted small">No common neutral-loss hits within tolerance.</p>'}
            </div>
            <div class="panel" style="margin-top:.8rem;">
              <strong>Ranked fragmentation-tree candidates</strong>
              ${candidateRows ? `<div style="overflow:auto; margin-top:.55rem;"><table><thead><tr><th>Rank</th><th>Candidate</th><th>Formula</th><th>Precursor ppm</th><th>Explained peaks</th><th>Intensity</th><th>Depth</th><th>Diagnostic</th><th>Contradictions</th><th>Status</th><th>Score</th></tr></thead><tbody>${candidateRows}</tbody></table></div>` : '<p class="muted small">No candidate structures were provided.</p>'}
            </div>
            ${details ? `<details style="margin-top:.8rem;"><summary>Fragmentation-tree evidence details</summary>${details}</details>` : ""}
          `;
        }

        function copyMSMSToFragmentationTree() {
          if (el("msmsPrecursorMz") && el("fragTreePrecursorMz")) el("fragTreePrecursorMz").value = el("msmsPrecursorMz").value;
          if (el("msmsAdduct") && el("fragTreeAdduct")) el("fragTreeAdduct").value = el("msmsAdduct").value;
          if (el("msmsToleranceDa") && el("fragTreeToleranceDa")) el("fragTreeToleranceDa").value = el("msmsToleranceDa").value;
          if (el("msmsPpmTolerance") && el("fragTreePpmTolerance")) el("fragTreePpmTolerance").value = el("msmsPpmTolerance").value;
          if (el("msmsMinRelIntensity") && el("fragTreeMinRelIntensity")) el("fragTreeMinRelIntensity").value = el("msmsMinRelIntensity").value;
          if (el("msmsMaxPeaks") && el("fragTreeMaxPeaks")) el("fragTreeMaxPeaks").value = el("msmsMaxPeaks").value;
          if (el("msmsPeakList") && el("fragTreePeakList")) el("fragTreePeakList").value = el("msmsPeakList").value;
          if (el("msmsCandidateList") && el("fragTreeCandidateList")) el("fragTreeCandidateList").value = el("msmsCandidateList").value;
        }

        function copyCandidatesToFragmentationTree() {
          if (el("candidateList") && el("fragTreeCandidateList")) {
            el("fragTreeCandidateList").value = el("candidateList").value;
          } else if (el("msmsCandidateList") && el("fragTreeCandidateList")) {
            el("fragTreeCandidateList").value = el("msmsCandidateList").value;
          } else if (el("hrmsCandidateList") && el("fragTreeCandidateList")) {
            el("fragTreeCandidateList").value = el("hrmsCandidateList").value;
          }
        }

        function fragmentationTreeFormData() {
          const formData = new FormData();
          const precursorMz = el("fragTreePrecursorMz") ? el("fragTreePrecursorMz").value.trim() : "";
          const peakText = el("fragTreePeakList") ? el("fragTreePeakList").value.trim() : "";
          if (!precursorMz) throw new Error("Enter precursor m/z for the fragmentation tree.");
          if (!peakText) throw new Error("Enter a processed MS/MS peak list for the fragmentation tree.");
          formData.append("precursor_mz", precursorMz);
          formData.append("adduct", el("fragTreeAdduct") ? el("fragTreeAdduct").value || "[M+H]+" : "[M+H]+");
          formData.append("mz_tolerance_da", (el("fragTreeToleranceDa") ? el("fragTreeToleranceDa").value.trim() : "") || "0.02");
          formData.append("ppm_tolerance", (el("fragTreePpmTolerance") ? el("fragTreePpmTolerance").value.trim() : "") || "20");
          formData.append("min_relative_intensity", (el("fragTreeMinRelIntensity") ? el("fragTreeMinRelIntensity").value.trim() : "") || "1");
          formData.append("max_peaks_to_analyze", (el("fragTreeMaxPeaks") ? el("fragTreeMaxPeaks").value.trim() : "") || "75");
          formData.append("max_tree_depth", (el("fragTreeMaxDepth") ? el("fragTreeMaxDepth").value.trim() : "") || "3");
          formData.append("peak_list_text", peakText);
          const candidatesText = el("fragTreeCandidateList") ? el("fragTreeCandidateList").value.trim() : "";
          if (candidatesText) formData.append("candidates_text", candidatesText);
          const sampleId = el("sampleId") ? el("sampleId").value.trim() : "";
          if (sampleId) formData.append("sample_id", sampleId);
          return formData;
        }

        async function runFragmentationTree() {
          try {
            const data = await api("/ms/msms/fragmentation-tree/evidence", { method: "POST", body: fragmentationTreeFormData() });
            setJson(data);
            renderFragmentationTree(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("fragmentationTreeBox")) el("fragmentationTreeBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function clearFragmentationTree() {
          state.latestFragmentationTree = null;
          if (el("fragmentationTreeBox")) el("fragmentationTreeBox").innerHTML = "No fragmentation tree yet.";
        }

        function renderUnifiedCandidateConfidence(data) {
          state.latestUnifiedConfidence = data;
          const box = el("unifiedConfidenceBox");
          if (!box) return;
          const ranked = Array.isArray(data?.ranked_candidates) ? data.ranked_candidates : [];
          const best = data?.best_candidate || null;
          const alerts = Array.isArray(data?.ambiguity_alerts) ? data.ambiguity_alerts : [];
          const contradictions = Array.isArray(data?.global_contradictions) ? data.global_contradictions : [];
          const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
          const notes = Array.isArray(data?.notes) ? data.notes : [];
          const layersUsed = Array.isArray(data?.evidence_layers_used) ? data.evidence_layers_used : [];
          const rows = ranked.map((item) => `
            <tr>
              <td>${escapeHtml(item.rank ?? "—")}</td>
              <td><strong>${escapeHtml(item.name || item.smiles || "Candidate")}</strong><div class="small muted">${escapeHtml(item.smiles || "—")}</div></td>
              <td>${prettyFormula(item.formula || "—")}</td>
              <td>${formatNmr2dPercent(item.confidence_score)}</td>
              <td>${escapeHtml(item.confidence_band || "—")}</td>
              <td>${escapeHtml(item.agreement_count || 0)}</td>
              <td>${escapeHtml(item.contradiction_count || 0)}</td>
              <td>${escapeHtml((item.missing_layers || []).length)}</td>
              <td><span class="status-badge ${getStatusVariant(item.label || "review")}">${escapeHtml(item.label || "review")}</span></td>
            </tr>
          `).join("");
          const details = ranked.map((item) => {
            const layerRows = (item.layers || []).map((layer) => `
              <tr>
                <td>${escapeHtml(layer.label || layer.layer || "—")}</td>
                <td>${layer.used ? "yes" : "no"}</td>
                <td>${formatNmr2dPercent(layer.score)}</td>
                <td>${escapeHtml(layer.status || "—")}</td>
                <td>${escapeHtml(layer.weight ?? "—")}</td>
                <td>${layer.contradiction ? "yes" : "no"}</td>
              </tr>
            `).join("");
            return `
              <div class="panel" style="margin-top:.65rem;">
                <strong>#${escapeHtml(item.rank ?? "—")} ${escapeHtml(item.name || item.smiles || "Candidate")}</strong>
                ${(item.evidence_summary || []).length ? `<ul class="small muted">${item.evidence_summary.map((entry) => `<li>${escapeHtml(entry)}</li>`).join("")}</ul>` : ""}
                ${(item.contradictions || []).length ? `<div class="panel" style="margin-top:.65rem; border-color:rgba(248,81,73,.45);"><strong>Candidate contradictions</strong><ul>${item.contradictions.map((entry) => `<li>${escapeHtml(entry)}</li>`).join("")}</ul></div>` : ""}
                ${layerRows ? `<div style="overflow:auto; margin-top:.55rem;"><table><thead><tr><th>Layer</th><th>Used</th><th>Score</th><th>Status</th><th>Weight</th><th>Contradiction</th></tr></thead><tbody>${layerRows}</tbody></table></div>` : ""}
                ${(item.missing_layers || []).length ? `<div class="small muted" style="margin-top:.45rem;">Missing layers: ${escapeHtml(item.missing_layers.join("; "))}</div>` : ""}
                ${(item.warnings || []).length ? `<div class="small" style="color:var(--danger); margin-top:.45rem;">${escapeHtml(item.warnings.join("; "))}</div>` : ""}
              </div>
            `;
          }).join("");
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>Unified candidate confidence result</strong>
              <span class="status-badge ${best ? getStatusVariant(best.label || "review") : "warn"}">${best ? `${formatNmr2dPercent(best.confidence_score)} confidence` : "no candidate"}</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">Best candidate</div><div class="value">${best ? escapeHtml(best.name || best.smiles) : "—"}</div></div>
              <div class="metric"><div class="label">Selected adduct</div><div class="value">${escapeHtml(data?.selected_adduct || "—")}</div></div>
              <div class="metric"><div class="label">Layers used</div><div class="value">${escapeHtml(layersUsed.length)}</div></div>
              <div class="metric"><div class="label">Candidate count</div><div class="value">${escapeHtml(data?.candidate_count ?? ranked.length)}</div></div>
            </div>
            ${layersUsed.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Evidence layers used</strong><div class="small muted">${layersUsed.map(escapeHtml).join(" · ")}</div></div>` : ""}
            ${alerts.length ? renderNmr2dMessages("Ambiguity alerts", alerts) : ""}
            ${contradictions.length ? `<div class="panel" style="margin-top:.8rem; border-color:rgba(248,81,73,.45);"><strong>Global contradictions</strong><ul>${contradictions.map((entry) => `<li>${escapeHtml(entry)}</li>`).join("")}</ul></div>` : ""}
            ${warnings.length ? renderNmr2dMessages("Warnings", warnings) : ""}
            ${notes.length ? renderNmr2dMessages("Notes", notes) : ""}
            ${rows ? `<div style="overflow:auto; margin-top:.8rem;"><table><thead><tr><th>Rank</th><th>Candidate</th><th>Formula</th><th>Confidence</th><th>Band</th><th>Agreement</th><th>Contradictions</th><th>Missing</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<p class="muted small">No unified candidates were ranked.</p>'}
            ${details ? `<details style="margin-top:.8rem;"><summary>Unified evidence details</summary>${details}</details>` : ""}
          `;
        }

        function copyInputsToUnifiedConfidence() {
          const candidateSources = ["candidateList", "predictedCandidateList", "hrmsCandidateList", "msmsCandidateList", "fragTreeCandidateList"];
          for (const id of candidateSources) {
            if (el(id) && el("unifiedCandidateList") && el(id).value.trim()) {
              el("unifiedCandidateList").value = el(id).value;
              break;
            }
          }
          if (el("nmrText") && el("unifiedObservedProtonText")) el("unifiedObservedProtonText").value = el("nmrText").value;
          if (el("carbon13Text") && el("unifiedObservedCarbonText")) el("unifiedObservedCarbonText").value = el("carbon13Text").value;
          if (el("hrmsObservedMz") && el("unifiedHrmsMz")) el("unifiedHrmsMz").value = el("hrmsObservedMz").value;
          if (el("hrmsAdduct") && el("unifiedHrmsAdduct")) el("unifiedHrmsAdduct").value = el("hrmsAdduct").value;
          if (el("hrmsPpmTolerance") && el("unifiedHrmsPpmTolerance")) el("unifiedHrmsPpmTolerance").value = el("hrmsPpmTolerance").value;
          if (el("adductPeakList") && el("unifiedMS1PeakList")) el("unifiedMS1PeakList").value = el("adductPeakList").value;
          if (el("fragTreePrecursorMz") && el("unifiedMSMSPrecursorMz")) el("unifiedMSMSPrecursorMz").value = el("fragTreePrecursorMz").value;
          else if (el("msmsPrecursorMz") && el("unifiedMSMSPrecursorMz")) el("unifiedMSMSPrecursorMz").value = el("msmsPrecursorMz").value;
          if (el("fragTreePpmTolerance") && el("unifiedMSMSPpmTolerance")) el("unifiedMSMSPpmTolerance").value = el("fragTreePpmTolerance").value;
          else if (el("msmsPpmTolerance") && el("unifiedMSMSPpmTolerance")) el("unifiedMSMSPpmTolerance").value = el("msmsPpmTolerance").value;
          if (el("fragTreePeakList") && el("unifiedMSMSPeakList")) el("unifiedMSMSPeakList").value = el("fragTreePeakList").value;
          else if (el("msmsPeakList") && el("unifiedMSMSPeakList")) el("unifiedMSMSPeakList").value = el("msmsPeakList").value;
          if (el("nmr2dExperiment") && el("unifiedNmr2dExperiment")) el("unifiedNmr2dExperiment").value = el("nmr2dExperiment").value;
          if (state.latestLCMSFeatureConsensus && el("unifiedUseLCMSConsensus")) el("unifiedUseLCMSConsensus").checked = true;
        }

        function unifiedConfidenceFormData() {
          const formData = new FormData();
          const candidatesText = el("unifiedCandidateList") ? el("unifiedCandidateList").value.trim() : "";
          if (!candidatesText) throw new Error("Enter candidate structures for unified confidence.");
          formData.append("candidates_text", candidatesText);
          const sampleId = el("sampleId") ? el("sampleId").value.trim() : "";
          const solvent = el("solvent") ? el("solvent").value.trim() : "";
          const protonText = (el("unifiedObservedProtonText")?.value || el("nmrText")?.value || "").trim();
          const carbonText = (el("unifiedObservedCarbonText")?.value || el("carbon13Text")?.value || "").trim();
          const nmr2dText = (el("unifiedObservedNmr2dText")?.value || "").trim();
          const nmr2dExperiment = el("unifiedNmr2dExperiment") ? el("unifiedNmr2dExperiment").value : "";
          const hrmsMz = el("unifiedHrmsMz") ? el("unifiedHrmsMz").value.trim() : "";
          const ms1Text = el("unifiedMS1PeakList") ? el("unifiedMS1PeakList").value.trim() : "";
          const msmsPrecursor = el("unifiedMSMSPrecursorMz") ? el("unifiedMSMSPrecursorMz").value.trim() : "";
          const msmsText = el("unifiedMSMSPeakList") ? el("unifiedMSMSPeakList").value.trim() : "";
          if (sampleId) formData.append("sample_id", sampleId);
          if (solvent) formData.append("solvent", solvent);
          if (protonText) formData.append("observed_proton_text", protonText);
          if (carbonText) formData.append("observed_carbon13_text", carbonText);
          if (nmr2dText) formData.append("observed_nmr2d_text", nmr2dText);
          if (nmr2dExperiment) formData.append("observed_nmr2d_experiment_type", nmr2dExperiment);
          if (hrmsMz) formData.append("hrms_observed_mz", hrmsMz);
          formData.append("hrms_adduct", el("unifiedHrmsAdduct") ? el("unifiedHrmsAdduct").value || "[M+H]+" : "[M+H]+");
          formData.append("hrms_ppm_tolerance", (el("unifiedHrmsPpmTolerance") ? el("unifiedHrmsPpmTolerance").value.trim() : "") || "5");
          formData.append("use_inferred_adduct", el("unifiedUseInferredAdduct") ? el("unifiedUseInferredAdduct").value || "true" : "true");
          if (ms1Text) formData.append("ms1_peak_list_text", ms1Text);
          if (msmsPrecursor) formData.append("msms_precursor_mz", msmsPrecursor);
          if (msmsText) formData.append("msms_peak_list_text", msmsText);
          formData.append("msms_adduct", el("unifiedHrmsAdduct") ? el("unifiedHrmsAdduct").value || "[M+H]+" : "[M+H]+");
          formData.append("mz_tolerance_da", "0.02");
          formData.append("msms_ppm_tolerance", (el("unifiedMSMSPpmTolerance") ? el("unifiedMSMSPpmTolerance").value.trim() : "") || "20");
          formData.append("msms_min_relative_intensity", "1");
          formData.append("msms_max_peaks_to_analyze", "75");
          formData.append("max_tree_depth", "3");
          if (el("unifiedUseLCMSConsensus") && el("unifiedUseLCMSConsensus").checked) {
            const consensus = state.latestLCMSFeatureConsensus;
            const table = consensus && consensus.family_table_text ? consensus.family_table_text : "";
            if (table) {
              formData.append("lcms_family_table_text", table);
              formData.append("lcms_anchor_adduct", el("unifiedHrmsAdduct") ? el("unifiedHrmsAdduct").value || "[M+H]+" : "[M+H]+");
              formData.append("lcms_mz_tolerance_da", el("lcmsConsensusMzTolDa") ? (el("lcmsConsensusMzTolDa").value || "0.02") : "0.02");
              formData.append("lcms_ppm_tolerance", el("lcmsConsensusPpmTol") ? (el("lcmsConsensusPpmTol").value || "10") : "10");
              formData.append("lcms_min_family_consensus_score", el("unifiedLCMSMinScore") ? (el("unifiedLCMSMinScore").value || "0.42") : "0.42");
              formData.append("lcms_require_promoted_family", "true");
            }
          }
          return formData;
        }

        async function runUnifiedCandidateConfidence() {
          try {
            const data = await api("/confidence/candidates/unified/evidence", { method: "POST", body: unifiedConfidenceFormData() });
            setJson(data);
            renderUnifiedCandidateConfidence(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("unifiedConfidenceBox")) el("unifiedConfidenceBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function clearUnifiedCandidateConfidence() {
          state.latestUnifiedConfidence = null;
          if (el("unifiedConfidenceBox")) el("unifiedConfidenceBox").innerHTML = "No unified candidate confidence result yet.";
        }

        function copyInputsToStructureReport() {
          copyInputsToUnifiedConfidence();
          if (el("sampleId") && el("structureReportProject") && !el("structureReportProject").value.trim()) {
            el("structureReportProject").value = state.selectedProjectId ? `Project ${state.selectedProjectId}` : "";
          }
        }

        function structureReportFormData() {
          const formData = unifiedConfidenceFormData();
          formData.append("report_title", (el("structureReportTitle") ? el("structureReportTitle").value.trim() : "") || "Regulatory-ready Structure Elucidation Report");
          const projectName = el("structureReportProject") ? el("structureReportProject").value.trim() : "";
          const preparedBy = el("structureReportPreparedBy") ? el("structureReportPreparedBy").value.trim() : "";
          const reviewerName = el("structureReportReviewer") ? el("structureReportReviewer").value.trim() : "";
          const reviewStatus = el("structureReportReviewStatus") ? el("structureReportReviewStatus").value : "";
          const reviewerComment = el("structureReportReviewerComment") ? el("structureReportReviewerComment").value.trim() : "";
          const rawHash = el("structureReportRawHash") ? el("structureReportRawHash").value.trim() : "";
          const sourceFiles = el("structureReportSourceFiles") ? el("structureReportSourceFiles").value.trim() : "";
          const processingHistory = el("structureReportProcessingHistory") ? el("structureReportProcessingHistory").value.trim() : "";
          const notes = el("structureReportNotes") ? el("structureReportNotes").value.trim() : "";
          if (projectName) formData.append("project_name", projectName);
          if (preparedBy) formData.append("prepared_by", preparedBy);
          if (reviewerName) formData.append("reviewer_name", reviewerName);
          if (reviewStatus) formData.append("review_status", reviewStatus);
          if (reviewerComment) formData.append("reviewer_comment", reviewerComment);
          formData.append("intended_use", el("structureReportIntendedUse") ? el("structureReportIntendedUse").value || "research_decision_support" : "research_decision_support");
          formData.append("require_human_approval", el("structureReportRequireApproval") ? el("structureReportRequireApproval").value || "true" : "true");
          if (rawHash) formData.append("raw_data_sha256", rawHash);
          if (sourceFiles) formData.append("source_files_text", sourceFiles);
          if (processingHistory) formData.append("processing_history_text", processingHistory);
          if (notes) formData.append("requestor_notes", notes);
          return formData;
        }

        function renderStructureReport(data) {
          state.latestStructureReport = data;
          const box = el("structureReportBox");
          if (!box) return;
          const best = data?.best_candidate || null;
          const ranked = Array.isArray(data?.ranked_candidates) ? data.ranked_candidates : [];
          const sections = Array.isArray(data?.sections) ? data.sections : [];
          const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
          const contradictions = Array.isArray(data?.global_contradictions) ? data.global_contradictions : [];
          const statusClass = data?.release_gate === "approved_for_release"
            ? "ok"
            : data?.release_gate === "blocked_by_contradictions" || data?.release_gate === "insufficient_evidence"
              ? "bad"
              : "warn";
          const rows = ranked.map((item) => `
            <tr>
              <td>${escapeHtml(item.rank ?? "—")}</td>
              <td><strong>${escapeHtml(item.name || item.smiles || "Candidate")}</strong><div class="small muted">${escapeHtml(item.smiles || "—")}</div></td>
              <td>${prettyFormula(item.formula || "—")}</td>
              <td>${formatNmr2dPercent(item.confidence_score)}</td>
              <td>${escapeHtml(item.confidence_band || "—")}</td>
              <td>${escapeHtml(item.agreement_count || 0)}</td>
              <td>${escapeHtml(item.contradiction_count || 0)}</td>
              <td><span class="status-badge ${getStatusVariant(item.label || "review")}">${escapeHtml(item.label || "review")}</span></td>
            </tr>
          `).join("");
          const sectionBlocks = sections.map((section) => `
            <div class="panel" style="margin-top:.6rem;">
              <strong>${escapeHtml(section.title || "Report section")}</strong>
              <ul>${(section.items || []).map((entry) => `<li>${escapeHtml(entry)}</li>`).join("")}</ul>
            </div>
          `).join("");
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>Structure elucidation report</strong>
              <span class="status-badge ${statusClass}">${escapeHtml(data?.status || "draft")}</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">Report ID</div><div class="value">${escapeHtml(data?.report_id || "—")}</div></div>
              <div class="metric"><div class="label">Release gate</div><div class="value">${escapeHtml(data?.release_gate || "—")}</div></div>
              <div class="metric"><div class="label">Best candidate</div><div class="value">${best ? escapeHtml(best.name || best.smiles) : "—"}</div></div>
              <div class="metric"><div class="label">Report SHA-256</div><div class="value small">${escapeHtml((data?.provenance || {}).report_sha256 || "—")}</div></div>
            </div>
            ${warnings.length ? renderNmr2dMessages("Warnings", warnings) : ""}
            ${contradictions.length ? `<div class="panel" style="margin-top:.8rem; border-color:rgba(248,81,73,.45);"><strong>Global contradictions</strong><ul>${contradictions.map((entry) => `<li>${escapeHtml(entry)}</li>`).join("")}</ul></div>` : ""}
            ${rows ? `<div style="overflow:auto; margin-top:.8rem;"><table><thead><tr><th>Rank</th><th>Candidate</th><th>Formula</th><th>Confidence</th><th>Band</th><th>Agreement</th><th>Contradictions</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table></div>` : '<p class="muted small">No candidates were included in this report.</p>'}
            ${sectionBlocks ? `<details style="margin-top:.8rem;"><summary>Report sections</summary>${sectionBlocks}</details>` : ""}
            ${data?.html_report ? `<details style="margin-top:.8rem;"><summary>HTML preview</summary><iframe title="Structure report preview" style="width:100%; min-height:420px; border:1px solid var(--border); border-radius:8px; background:white;" srcdoc="${escapeHtml(data.html_report)}"></iframe></details>` : ""}
          `;
        }

        async function runStructureReportComposer() {
          try {
            const data = await api("/reports/structure-elucidation/compose/evidence", { method: "POST", body: structureReportFormData() });
            setJson(data);
            renderStructureReport(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("structureReportBox")) el("structureReportBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function clearStructureReport() {
          state.latestStructureReport = null;
          if (el("structureReportBox")) el("structureReportBox").innerHTML = "No structure elucidation report yet.";
        }

        function lcmsImportBaseFormData() {
          const formData = new FormData();
          const sampleId = el("sampleId") ? el("sampleId").value.trim() : "";
          if (sampleId) formData.append("sample_id", sampleId);
          formData.append("source_format", el("lcmsImportFormat").value || "auto");
          const preferred = el("lcmsPreferredPrecursor").value.trim();
          if (preferred) formData.append("preferred_msms_precursor_mz", preferred);
          formData.append("min_relative_intensity", el("lcmsMinRelIntensity").value.trim() || "0.5");
          formData.append("max_ms1_peaks", el("lcmsMaxMS1Peaks").value.trim() || "250");
          formData.append("max_msms_peaks_per_spectrum", el("lcmsMaxMSMSPeaks").value.trim() || "250");
          formData.append("max_peaks_per_spectrum", "50");
          formData.append("max_scans_to_report", "250");
          formData.append("mz_tolerance_da", el("lcmsMzToleranceDa").value.trim() || "0.02");
          formData.append("ppm_tolerance", el("lcmsPpmTolerance").value.trim() || "20");
          return formData;
        }

        async function runLCMSImportBridge() {
          try {
            const formData = lcmsImportBaseFormData();
            const file = el("lcmsImportFile") && el("lcmsImportFile").files && el("lcmsImportFile").files[0] ? el("lcmsImportFile").files[0] : null;
            let endpoint = "/ms/lcms/import/bridge/evidence";
            if (file) {
              formData.append("file", file);
              endpoint = "/ms/lcms/import/bridge/upload";
            } else {
              const sourceText = el("lcmsImportText").value.trim();
              if (!sourceText) throw new Error("Paste mzML/mzXML text or a processed LC-MS peak table, or choose a file.");
              state.latestLCMSImportSourceText = sourceText;
              formData.append("source_text", sourceText);
              const filename = el("lcmsImportFilename").value.trim();
              if (filename) formData.append("filename", filename);
            }
            const data = await api(endpoint, { method: "POST", body: formData });
            setJson(data);
            renderLCMSImportBridge(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("lcmsImportBridgeBox")) el("lcmsImportBridgeBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function renderLCMSImportBridge(data) {
          state.latestLCMSImport = data;
          const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
          const actions = Array.isArray(data?.recommended_next_actions) ? data.recommended_next_actions : [];
          const scans = Array.isArray(data?.scans) ? data.scans : [];
          const precursors = Array.isArray(data?.extracted_precursors) ? data.extracted_precursors : [];
          const labelClass = data?.label === "ready_for_downstream_ms" ? "ok" : data?.label === "unsupported_vendor_format" || data?.label === "invalid_input" ? "bad" : "warn";
          const box = el("lcmsImportBridgeBox");
          if (!box) return;
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>LC-MS/MS import bridge</strong>
              <span class="status-badge ${labelClass}">${escapeHtml(data?.label || "metadata_only")}</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">Format</div><div class="value">${escapeHtml(data?.source_format || "—")}</div></div>
              <div class="metric"><div class="label">Scans</div><div class="value">${escapeHtml(data?.scan_count || 0)} total</div></div>
              <div class="metric"><div class="label">MS1 / MS2</div><div class="value">${escapeHtml(data?.ms1_scan_count || 0)} / ${escapeHtml(data?.ms2_scan_count || 0)}</div></div>
              <div class="metric"><div class="label">SHA-256</div><div class="value small">${escapeHtml(data?.file_sha256 || "—")}</div></div>
            </div>
            ${data?.primary_ms1_mz ? `<p class="small"><strong>Primary MS1 m/z:</strong> ${escapeHtml(data.primary_ms1_mz)}</p>` : ""}
            ${data?.selected_msms_precursor_mz ? `<p class="small"><strong>Selected MS/MS precursor:</strong> ${escapeHtml(data.selected_msms_precursor_mz)} from scan ${escapeHtml(data.selected_msms_scan_id || "—")}</p>` : ""}
            ${warnings.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Warnings</strong><ul>${warnings.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>` : ""}
            ${actions.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Recommended next actions</strong><ul>${actions.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>` : ""}
            ${precursors.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Extracted MS/MS precursors</strong><table style="margin-top:.5rem;"><thead><tr><th>Scan</th><th>RT min</th><th>Precursor m/z</th><th>Peaks</th><th>TIC</th></tr></thead><tbody>${precursors.slice(0, 20).map((p) => `<tr><td>${escapeHtml(p.scan_id)}</td><td>${p.retention_time_min ?? "—"}</td><td>${p.precursor_mz}</td><td>${p.peak_count}</td><td>${p.total_ion_current ?? "—"}</td></tr>`).join("")}</tbody></table></div>` : ""}
            ${scans.length ? `<details style="margin-top:.8rem;"><summary>Scan summary</summary><table style="margin-top:.5rem;"><thead><tr><th>Scan</th><th>MS</th><th>RT min</th><th>Precursor</th><th>Base m/z</th><th>Peaks</th></tr></thead><tbody>${scans.slice(0, 50).map((s) => `<tr><td>${escapeHtml(s.scan_id)}</td><td>MS${s.ms_level}</td><td>${s.retention_time_min ?? "—"}</td><td>${s.precursor_mz ?? "—"}</td><td>${s.base_peak_mz ?? "—"}</td><td>${s.peak_count}</td></tr>`).join("")}</tbody></table></details>` : ""}
            ${data?.extracted_ms1_peak_list_text ? `<details style="margin-top:.8rem;"><summary>Extracted MS1 peak list</summary><pre style="white-space:pre-wrap;">${escapeHtml(data.extracted_ms1_peak_list_text)}</pre></details>` : ""}
            ${data?.extracted_msms_peak_list_text ? `<details style="margin-top:.8rem;"><summary>Selected MS/MS peak list</summary><pre style="white-space:pre-wrap;">${escapeHtml(data.extracted_msms_peak_list_text)}</pre></details>` : ""}
          `;
        }

        function copyLCMSToMSWorkflows() {
          const data = state.latestLCMSImport;
          if (!data) {
            if (el("lcmsImportBridgeBox")) el("lcmsImportBridgeBox").innerHTML = `<p style="color:var(--danger);">Import LC-MS/MS data before copying.</p>`;
            return;
          }
          const ms1Text = data.extracted_ms1_peak_list_text || "";
          const msmsText = data.extracted_msms_peak_list_text || "";
          const primary = data.primary_ms1_mz || data.selected_msms_precursor_mz || "";
          const precursor = data.selected_msms_precursor_mz || data.primary_ms1_mz || "";
          if (ms1Text && el("adductPeakList")) el("adductPeakList").value = ms1Text;
          if (ms1Text && el("unifiedMS1PeakList")) el("unifiedMS1PeakList").value = ms1Text;
          if (primary && el("hrmsObservedMz")) el("hrmsObservedMz").value = String(primary);
          if (primary && el("unifiedHrmsMz")) el("unifiedHrmsMz").value = String(primary);
          if (precursor && el("msmsPrecursorMz")) el("msmsPrecursorMz").value = String(precursor);
          if (precursor && el("fragTreePrecursorMz")) el("fragTreePrecursorMz").value = String(precursor);
          if (precursor && el("unifiedMSMSPrecursorMz")) el("unifiedMSMSPrecursorMz").value = String(precursor);
          if (msmsText && el("msmsPeakList")) el("msmsPeakList").value = msmsText;
          if (msmsText && el("fragTreePeakList")) el("fragTreePeakList").value = msmsText;
          if (msmsText && el("unifiedMSMSPeakList")) el("unifiedMSMSPeakList").value = msmsText;
        }

        function copyLCMSHashToReport() {
          const data = state.latestLCMSImport;
          if (!data) {
            if (el("lcmsImportBridgeBox")) el("lcmsImportBridgeBox").innerHTML = `<p style="color:var(--danger);">Import LC-MS/MS data before copying provenance.</p>`;
            return;
          }
          if (el("structureReportRawHash")) el("structureReportRawHash").value = data.file_sha256 || "";
          if (el("structureReportSourceFiles")) {
            const current = el("structureReportSourceFiles").value.trim();
            const next = data.filename || `LC-MS import ${data.file_sha256 || ""}`.trim();
            el("structureReportSourceFiles").value = current ? `${current}\n${next}` : next;
          }
          if (el("structureReportProcessingHistory")) {
            const current = el("structureReportProcessingHistory").value.trim();
            const line = `LC-MS/MS import bridge: ${data.source_format || "unknown"}; raw hash ${data.file_sha256 || "unavailable"}; raw data not mutated`;
            el("structureReportProcessingHistory").value = current ? `${current}\n${line}` : line;
          }
        }

        function clearLCMSImportBridge() {
          state.latestLCMSImport = null;
          state.latestLCMSImportSourceText = null;
          if (el("lcmsImportFile")) el("lcmsImportFile").value = "";
          if (el("lcmsImportBridgeBox")) el("lcmsImportBridgeBox").innerHTML = "No LC-MS/MS import bridge result yet.";
        }

        function lcmsFeatureBaseFormData() {
          const formData = new FormData();
          const sampleId = el("sampleId") ? el("sampleId").value.trim() : "";
          if (sampleId) formData.append("sample_id", sampleId);
          formData.append("source_format", el("lcmsFeatureFormat").value || "auto");
          const targets = el("lcmsFeatureTargets").value.trim();
          if (targets) formData.append("target_mz_text", targets);
          formData.append("mz_tolerance_da", el("lcmsFeatureMzTolDa").value.trim() || "0.02");
          formData.append("ppm_tolerance", el("lcmsFeaturePpmTol").value.trim() || "20");
          formData.append("min_relative_feature_height", el("lcmsFeatureMinRelHeight").value.trim() || "5");
          formData.append("min_scans_per_feature", el("lcmsFeatureMinScans").value.trim() || "2");
          formData.append("smoothing_window", el("lcmsFeatureSmoothing").value.trim() || "1");
          formData.append("purity_rt_window_min", el("lcmsFeaturePurityWindow").value.trim() || "0.20");
          formData.append("top_coeluting_ions", el("lcmsFeatureTopIons").value.trim() || "5");
          formData.append("max_features", el("lcmsFeatureMaxFeatures").value.trim() || "20");
          formData.append("max_scans_to_report", "1000");
          formData.append("max_xic_points", "5000");
          return formData;
        }

        async function runLCMSFeatureDetection() {
          try {
            const formData = lcmsFeatureBaseFormData();
            const file = el("lcmsFeatureFile") && el("lcmsFeatureFile").files && el("lcmsFeatureFile").files[0] ? el("lcmsFeatureFile").files[0] : null;
            let endpoint = "/ms/lcms/features/detect/evidence";
            if (file) {
              formData.append("file", file);
              endpoint = "/ms/lcms/features/detect/upload";
            } else {
              const sourceText = el("lcmsFeatureText").value.trim();
              if (!sourceText) throw new Error("Paste mzML/mzXML text or a processed LC-MS peak table, or choose a file.");
              state.latestLCMSFeatureSourceText = sourceText;
              formData.append("source_text", sourceText);
              const filename = el("lcmsFeatureFilename").value.trim();
              if (filename) formData.append("filename", filename);
            }
            const data = await api(endpoint, { method: "POST", body: formData });
            setJson(data);
            renderLCMSFeatureDetection(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("lcmsFeatureBox")) el("lcmsFeatureBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function renderLCMSFeatureDetection(data) {
          state.latestLCMSFeatures = data;
          const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
          const actions = Array.isArray(data?.recommended_next_actions) ? data.recommended_next_actions : [];
          const features = Array.isArray(data?.features) ? data.features : [];
          const best = data?.best_feature || (features.length ? features[0] : null);
          const labelClass = (data?.clean_feature_count || 0) > 0 ? "ok" : (data?.coeluting_feature_count || 0) > 0 ? "warn" : "bad";
          const box = el("lcmsFeatureBox");
          if (!box) return;
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>LC-MS feature detection</strong>
              <span class="status-badge ${labelClass}">${escapeHtml(data?.label || "metadata_only")}</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">Features</div><div class="value">${escapeHtml(data?.feature_count || 0)}</div></div>
              <div class="metric"><div class="label">Clean / Coeluting / Weak</div><div class="value">${escapeHtml(data?.clean_feature_count || 0)} / ${escapeHtml(data?.coeluting_feature_count || 0)} / ${escapeHtml(data?.weak_feature_count || 0)}</div></div>
              <div class="metric"><div class="label">MS1 scans</div><div class="value">${escapeHtml(data?.ms1_scan_count || 0)}</div></div>
              <div class="metric"><div class="label">SHA-256</div><div class="value small">${escapeHtml(data?.file_sha256 || "—")}</div></div>
            </div>
            ${best ? `<p class="small"><strong>Best feature:</strong> ${escapeHtml(best.feature_id)} target m/z ${escapeHtml(best.target_mz)} at RT ${escapeHtml(best.apex_rt_min)} min; purity ${escapeHtml((best.purity || {}).purity_percent ?? "—")}%. Peak purity is supportive chromatographic evidence and requires human review.</p>` : ""}
            ${warnings.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Warnings</strong><ul>${warnings.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>` : ""}
            ${actions.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Recommended next actions</strong><ul>${actions.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>` : ""}
            ${features.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Detected features</strong><table style="margin-top:.5rem;"><thead><tr><th>ID</th><th>m/z</th><th>RT apex</th><th>Area</th><th>S/N</th><th>Purity</th><th>MS/MS</th><th>Label</th></tr></thead><tbody>${features.slice(0, 30).map((f) => `<tr><td>${escapeHtml(f.feature_id)}</td><td>${escapeHtml(f.observed_mz || f.target_mz)}</td><td>${escapeHtml(f.apex_rt_min)}</td><td>${escapeHtml(f.area)}</td><td>${escapeHtml(f.signal_to_noise)}</td><td>${escapeHtml((f.purity || {}).purity_percent ?? "—")}%</td><td>${escapeHtml((f.linked_msms_spectra || []).length)}</td><td><span class="status-badge ${f.label === "clean_feature" ? "ok" : f.label === "possible_coelution" ? "warn" : "bad"}">${escapeHtml(f.label)}</span></td></tr>`).join("")}</tbody></table></div>` : ""}
            ${features.length ? `<details style="margin-top:.8rem;"><summary>Peak purity details</summary>${features.slice(0, 10).map((f) => `<div class="panel" style="margin-top:.6rem;"><strong>${escapeHtml(f.feature_id)} - m/z ${escapeHtml(f.target_mz)}</strong><div class="small muted">${(f.evidence_summary || []).map(escapeHtml).join("<br>")}</div>${(f.purity || {}).top_coeluting_ions && f.purity.top_coeluting_ions.length ? `<table style="margin-top:.5rem;"><thead><tr><th>Coeluting m/z</th><th>Area</th><th>Relative area</th><th>Correlation</th></tr></thead><tbody>${f.purity.top_coeluting_ions.map((ion) => `<tr><td>${escapeHtml(ion.mz)}</td><td>${escapeHtml(ion.area)}</td><td>${escapeHtml(ion.relative_area_percent)}%</td><td>${ion.correlation_to_target == null ? "—" : escapeHtml(Number(ion.correlation_to_target).toFixed(3))}</td></tr>`).join("")}</tbody></table>` : '<p class="small muted">No major coeluting ions reported.</p>'}</div>`).join("")}</details>` : ""}
          `;
        }

        function useLatestLCMSImportForFeatures() {
          if (!el("lcmsFeatureText")) return;
          const sourceText = state.latestLCMSImportSourceText || (el("lcmsImportText") ? el("lcmsImportText").value.trim() : "");
          if (sourceText) {
            state.latestLCMSFeatureSourceText = sourceText;
            el("lcmsFeatureText").value = sourceText;
          }
          if (el("lcmsFeatureFilename") && el("lcmsImportFilename")) el("lcmsFeatureFilename").value = el("lcmsImportFilename").value;
          if (el("lcmsFeatureFormat") && el("lcmsImportFormat")) el("lcmsFeatureFormat").value = el("lcmsImportFormat").value;
          const imported = state.latestLCMSImport;
          if (imported && imported.primary_ms1_mz && el("lcmsFeatureTargets")) el("lcmsFeatureTargets").value = String(imported.primary_ms1_mz);
        }

        function copyLCMSFeatureToMSWorkflows() {
          const data = state.latestLCMSFeatures;
          const feature = data && (data.best_feature || (data.features || [])[0]);
          if (!feature) {
            if (el("lcmsFeatureBox")) el("lcmsFeatureBox").innerHTML = `<p style="color:var(--danger);">Detect LC-MS features before copying.</p>`;
            return;
          }
          const mz = feature.observed_mz || feature.target_mz;
          if (mz && el("hrmsObservedMz")) el("hrmsObservedMz").value = String(mz);
          if (mz && el("unifiedHrmsMz")) el("unifiedHrmsMz").value = String(mz);
          if (mz && el("lcmsPreferredPrecursor")) el("lcmsPreferredPrecursor").value = String(mz);
          const linked = feature.linked_msms_spectra && feature.linked_msms_spectra.length ? feature.linked_msms_spectra[0] : null;
          if (linked && el("msmsPrecursorMz")) el("msmsPrecursorMz").value = String(linked.precursor_mz);
          if (linked && el("fragTreePrecursorMz")) el("fragTreePrecursorMz").value = String(linked.precursor_mz);
          if (linked && el("unifiedMSMSPrecursorMz")) el("unifiedMSMSPrecursorMz").value = String(linked.precursor_mz);
        }

        function copyLCMSFeaturePurityToReport() {
          const data = state.latestLCMSFeatures;
          const feature = data && (data.best_feature || (data.features || [])[0]);
          if (!data || !feature) {
            if (el("lcmsFeatureBox")) el("lcmsFeatureBox").innerHTML = `<p style="color:var(--danger);">Detect LC-MS features before copying feature provenance.</p>`;
            return;
          }
          if (el("structureReportRawHash")) el("structureReportRawHash").value = data.file_sha256 || "";
          if (el("structureReportProcessingHistory")) {
            const current = el("structureReportProcessingHistory").value.trim();
            const line = `LC-MS feature detection: ${feature.feature_id} m/z ${feature.target_mz}; RT ${feature.apex_rt_min} min; purity ${(feature.purity || {}).purity_percent ?? "unavailable"}%; raw hash ${data.file_sha256 || "unavailable"}`;
            el("structureReportProcessingHistory").value = current ? `${current}\n${line}` : line;
          }
        }

        function clearLCMSFeatureDetection() {
          state.latestLCMSFeatures = null;
          state.latestLCMSFeatureSourceText = null;
          if (el("lcmsFeatureFile")) el("lcmsFeatureFile").value = "";
          if (el("lcmsFeatureBox")) el("lcmsFeatureBox").innerHTML = "No LC-MS feature detection result yet.";
        }

        function lcmsGroupBaseFormData() {
          const formData = new FormData();
          const sampleId = el("sampleId") ? el("sampleId").value.trim() : "";
          if (sampleId) formData.append("sample_id", sampleId);
          formData.append("source_format", el("lcmsGroupFormat").value || "auto");
          const targets = el("lcmsGroupTargets").value.trim();
          if (targets) formData.append("target_mz_text", targets);
          const anchors = el("lcmsGroupAnchorMz").value.trim();
          if (anchors) formData.append("alignment_anchor_mz_text", anchors);
          formData.append("mz_tolerance_da", el("lcmsGroupMzTolDa").value.trim() || "0.02");
          formData.append("ppm_tolerance", el("lcmsGroupPpmTol").value.trim() || "20");
          formData.append("group_rt_tolerance_min", el("lcmsGroupRtTol").value.trim() || "0.12");
          formData.append("family_rt_tolerance_min", el("lcmsGroupFamilyRtTol").value.trim() || "0.15");
          formData.append("blank_area_ratio_threshold", el("lcmsGroupBlankRatio").value.trim() || "0.30");
          formData.append("possible_background_ratio_threshold", el("lcmsGroupBackgroundRatio").value.trim() || "0.10");
          formData.append("blank_subtraction_factor", "1.0");
          formData.append("max_features_per_run", el("lcmsGroupMaxFeatures").value.trim() || "50");
          formData.append("max_groups_to_report", el("lcmsGroupMaxGroups").value.trim() || "100");
          formData.append("min_relative_feature_height", "5");
          formData.append("min_scans_per_feature", "2");
          formData.append("smoothing_window", "1");
          formData.append("purity_rt_window_min", "0.20");
          formData.append("align_retention_times", "true");
          formData.append("annotate_feature_families", "true");
          return formData;
        }

        async function runLCMSFeatureGrouping() {
          try {
            const sampleText = el("lcmsGroupSampleText").value.trim();
            if (!sampleText) throw new Error("Paste a sample LC-MS peak table or mzML/mzXML text before grouping.");
            const formData = lcmsGroupBaseFormData();
            formData.append("sample_source_text", sampleText);
            state.latestLCMSFeatureSourceText = sampleText;
            const sampleFilename = el("lcmsGroupSampleFilename").value.trim();
            if (sampleFilename) formData.append("sample_filename", sampleFilename);
            const blankText = el("lcmsGroupBlankText").value.trim();
            if (blankText) {
              formData.append("blank_source_text", blankText);
              const blankFilename = el("lcmsGroupBlankFilename").value.trim();
              if (blankFilename) formData.append("blank_filename", blankFilename);
            }
            const data = await api("/ms/lcms/features/group/evidence", { method: "POST", body: formData });
            setJson(data);
            renderLCMSFeatureGrouping(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("lcmsFeatureGroupingBox")) el("lcmsFeatureGroupingBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function lcmsFeatureGroupBadgeClass(label) {
          if (label === "sample_enriched_feature" || label === "sample_only_feature") return "ok";
          if (label === "possible_background_feature" || label === "low_abundance_feature" || label === "reference_or_qc_only") return "warn";
          if (label === "blank_like_feature" || label === "blank_only_background" || label === "invalid_input") return "bad";
          return "warn";
        }

        function renderLCMSFeatureGrouping(data) {
          state.latestLCMSFeatureGrouping = data;
          const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
          const actions = Array.isArray(data?.recommended_next_actions) ? data.recommended_next_actions : [];
          const notes = Array.isArray(data?.notes) ? data.notes : [];
          const alignments = Array.isArray(data?.alignment_summaries) ? data.alignment_summaries : [];
          const groups = Array.isArray(data?.groups) ? data.groups : [];
          const labelClass = data?.label === "ready_for_candidate_scoring" ? "ok" : data?.label === "review_background_before_scoring" ? "warn" : "bad";
          const box = el("lcmsFeatureGroupingBox");
          if (!box) return;
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>LC-MS feature grouping</strong>
              <span class="status-badge ${labelClass}">${escapeHtml(data?.label || "metadata_only")}</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">Runs</div><div class="value">${escapeHtml(data?.run_count || 0)}</div></div>
              <div class="metric"><div class="label">Groups</div><div class="value">${escapeHtml(data?.group_count || 0)}</div></div>
              <div class="metric"><div class="label">Sample enriched</div><div class="value">${escapeHtml(data?.sample_enriched_group_count || 0)}</div></div>
              <div class="metric"><div class="label">Background-like</div><div class="value">${escapeHtml(data?.background_group_count || 0)}</div></div>
              <div class="metric"><div class="label">Blank-subtracted</div><div class="value">${escapeHtml(data?.blank_subtracted_group_count || 0)}</div></div>
              <div class="metric"><div class="label">Family links</div><div class="value">${escapeHtml(data?.relationship_count || 0)}</div></div>
            </div>
            <p class="small muted" style="margin-top:.75rem;">Retention-time alignment uses transparent per-run shifts from shared feature anchors. Blank subtraction and feature-family hints are review aids, not identity claims.</p>
            ${warnings.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Warnings</strong><ul>${warnings.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>` : ""}
            ${actions.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Recommended next actions</strong><ul>${actions.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>` : ""}
            ${notes.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Notes</strong><ul>${notes.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>` : ""}
            ${alignments.length ? `<div class="panel" style="margin-top:.8rem;"><strong>RT alignment summary</strong><table style="margin-top:.5rem;"><thead><tr><th>Run</th><th>Role</th><th>Features</th><th>RT shift min</th><th>Anchors</th><th>SHA-256</th></tr></thead><tbody>${alignments.map((a) => `<tr><td>${escapeHtml(a.run_id)}</td><td>${escapeHtml(a.role)}</td><td>${escapeHtml(a.aligned_feature_count)} / ${escapeHtml(a.raw_feature_count)}</td><td>${escapeHtml(a.rt_shift_min)}</td><td>${escapeHtml(a.anchor_match_count)}</td><td class="small">${escapeHtml(a.file_sha256 || "—")}</td></tr>`).join("")}</tbody></table></div>` : ""}
            ${groups.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Grouped feature table</strong><table style="margin-top:.5rem;"><thead><tr><th>Group</th><th>m/z</th><th>Aligned RT</th><th>Label</th><th>Sample area</th><th>Blank area</th><th>Blank ratio</th><th>Blank-subtracted</th><th>Members</th><th>Family hints</th></tr></thead><tbody>${groups.slice(0, 40).map((g) => `<tr><td>${escapeHtml(g.group_id)}</td><td>${escapeHtml(g.representative_mz)}</td><td>${escapeHtml(g.representative_rt_min)}</td><td><span class="status-badge ${lcmsFeatureGroupBadgeClass(g.label)}">${escapeHtml(g.label)}</span></td><td>${escapeHtml(g.sample_area)}</td><td>${escapeHtml(g.blank_area)}</td><td>${escapeHtml(g.blank_ratio)}</td><td>${escapeHtml(g.blank_subtracted_area)}</td><td>${escapeHtml(g.member_count)}</td><td>${escapeHtml((g.relationships || []).length)}</td></tr>`).join("")}</tbody></table></div>` : ""}
            ${groups.length ? `<details style="margin-top:.8rem;"><summary>Group evidence details</summary>${groups.slice(0, 12).map((g) => `<div class="panel" style="margin-top:.6rem;"><strong>${escapeHtml(g.group_id)} - m/z ${escapeHtml(g.representative_mz)} at ${escapeHtml(g.representative_rt_min)} min</strong>${(g.evidence_summary || []).length ? `<ul class="small muted">${g.evidence_summary.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>` : ""}${(g.warnings || []).length ? `<div class="small" style="color:var(--warn);">${g.warnings.map(escapeHtml).join("<br>")}</div>` : ""}${(g.relationships || []).length ? `<table style="margin-top:.5rem;"><thead><tr><th>Relationship</th><th>Partner</th><th>Observed delta</th><th>Expected delta</th><th>RT delta</th></tr></thead><tbody>${g.relationships.map((r) => `<tr><td>${escapeHtml(r.label)}</td><td>${escapeHtml(r.partner_group_id)}</td><td>${escapeHtml(r.observed_delta_mz)}</td><td>${escapeHtml(r.expected_delta_mz)}</td><td>${escapeHtml(r.rt_delta_min)}</td></tr>`).join("")}</tbody></table>` : ""}${(g.members || []).length ? `<table style="margin-top:.5rem;"><thead><tr><th>Run</th><th>Role</th><th>Feature</th><th>Raw RT</th><th>Aligned RT</th><th>Area</th><th>Purity</th><th>Label</th></tr></thead><tbody>${g.members.map((m) => `<tr><td>${escapeHtml(m.run_id)}</td><td>${escapeHtml(m.role)}</td><td>${escapeHtml(m.feature_id)}</td><td>${escapeHtml(m.raw_apex_rt_min)}</td><td>${escapeHtml(m.aligned_apex_rt_min)}</td><td>${escapeHtml(m.area)}</td><td>${escapeHtml(m.purity_percent)}%</td><td>${escapeHtml(m.feature_label)}</td></tr>`).join("")}</tbody></table>` : ""}</div>`).join("")}</details>` : ""}
            ${data?.feature_table_text ? `<details style="margin-top:.8rem;"><summary>Exportable feature_table_text</summary><pre style="white-space:pre-wrap;">${escapeHtml(data.feature_table_text)}</pre></details>` : ""}
          `;
        }

        function useLatestLCMSFeaturesForGrouping() {
          const sourceText = state.latestLCMSFeatureSourceText || (el("lcmsFeatureText") ? el("lcmsFeatureText").value.trim() : "");
          if (sourceText && el("lcmsGroupSampleText")) el("lcmsGroupSampleText").value = sourceText;
          if (el("lcmsGroupSampleFilename") && el("lcmsFeatureFilename")) el("lcmsGroupSampleFilename").value = el("lcmsFeatureFilename").value;
          if (el("lcmsGroupFormat") && el("lcmsFeatureFormat")) el("lcmsGroupFormat").value = el("lcmsFeatureFormat").value;
          const features = state.latestLCMSFeatures;
          const best = features && (features.best_feature || (features.features || [])[0]);
          if (best && el("lcmsGroupTargets")) el("lcmsGroupTargets").value = String(best.observed_mz || best.target_mz);
        }

        function bestLCMSFeatureGroup() {
          const groups = state.latestLCMSFeatureGrouping && Array.isArray(state.latestLCMSFeatureGrouping.groups) ? state.latestLCMSFeatureGrouping.groups : [];
          return groups.find((g) => g.label === "sample_enriched_feature" || g.label === "sample_only_feature") || groups[0] || null;
        }

        function copyLCMSFeatureGroupToMSWorkflows() {
          const group = bestLCMSFeatureGroup();
          if (!group) {
            if (el("lcmsFeatureGroupingBox")) el("lcmsFeatureGroupingBox").innerHTML = `<p style="color:var(--danger);">Group LC-MS features before copying downstream.</p>`;
            return;
          }
          const mz = group.representative_mz;
          if (mz && el("hrmsObservedMz")) el("hrmsObservedMz").value = String(mz);
          if (mz && el("unifiedHrmsMz")) el("unifiedHrmsMz").value = String(mz);
          if (mz && el("adductTargetMz")) el("adductTargetMz").value = String(mz);
          if (mz && el("lcmsPreferredPrecursor")) el("lcmsPreferredPrecursor").value = String(mz);
          if (mz && el("msmsPrecursorMz")) el("msmsPrecursorMz").value = String(mz);
          if (mz && el("fragTreePrecursorMz")) el("fragTreePrecursorMz").value = String(mz);
          if (mz && el("unifiedMSMSPrecursorMz")) el("unifiedMSMSPrecursorMz").value = String(mz);
        }

        function copyLCMSFeatureGroupingToReport() {
          const data = state.latestLCMSFeatureGrouping;
          const group = bestLCMSFeatureGroup();
          if (!data || !group) {
            if (el("lcmsFeatureGroupingBox")) el("lcmsFeatureGroupingBox").innerHTML = `<p style="color:var(--danger);">Group LC-MS features before copying feature-table provenance.</p>`;
            return;
          }
          const hashes = (data.alignment_summaries || []).map((a) => a.file_sha256).filter(Boolean);
          if (hashes.length && el("structureReportRawHash")) el("structureReportRawHash").value = hashes[0];
          if (el("structureReportSourceFiles")) {
            const current = el("structureReportSourceFiles").value.trim();
            const files = (data.alignment_summaries || []).map((a) => a.filename || `${a.run_id}:${a.file_sha256 || "hash unavailable"}`).filter(Boolean);
            const next = files.length ? files.join("\n") : `LC-MS feature grouping ${data.reference_run_id || ""}`.trim();
            el("structureReportSourceFiles").value = current ? `${current}\n${next}` : next;
          }
          if (el("structureReportProcessingHistory")) {
            const current = el("structureReportProcessingHistory").value.trim();
            const line = `LC-MS feature grouping: ${data.group_count || 0} groups; ${data.sample_enriched_group_count || 0} sample-enriched; ${data.background_group_count || 0} background-like; best group ${group.group_id} m/z ${group.representative_mz} RT ${group.representative_rt_min} min; blank ratio ${group.blank_ratio}; human review required.`;
            el("structureReportProcessingHistory").value = current ? `${current}\n${line}` : line;
          }
          if (el("structureReportNotes") && data.feature_table_text) {
            const current = el("structureReportNotes").value.trim();
            const note = `LC-MS feature table QC:\n${data.feature_table_text}`;
            el("structureReportNotes").value = current ? `${current}\n\n${note}` : note;
          }
        }

        function clearLCMSFeatureGrouping() {
          state.latestLCMSFeatureGrouping = null;
          if (el("lcmsFeatureGroupingBox")) el("lcmsFeatureGroupingBox").innerHTML = "No LC-MS feature grouping result yet.";
        }

        function useLatestLCMSGroupingForConsensus() {
          const data = state.latestLCMSFeatureGrouping;
          if (data && data.feature_table_text && el("lcmsConsensusFeatureTable")) {
            el("lcmsConsensusFeatureTable").value = data.feature_table_text;
          }
          if (data && Array.isArray(data.groups) && data.groups.length && el("lcmsConsensusAnchorGroup")) {
            const group = data.groups.find((g) => g.label === "sample_enriched_feature" || g.label === "sample_only_feature") || data.groups[0];
            el("lcmsConsensusAnchorGroup").value = group.group_id || "";
          }
        }

        async function runLCMSFeatureConsensus() {
          try {
            const payload = {
              sample_id: el("sampleId") ? (el("sampleId").value.trim() || null) : null,
              grouping_result: state.latestLCMSFeatureGrouping || null,
              feature_table_text: el("lcmsConsensusFeatureTable") ? (el("lcmsConsensusFeatureTable").value.trim() || null) : null,
              formula: el("lcmsConsensusFormula") ? (el("lcmsConsensusFormula").value.trim() || null) : null,
              expected_anchor_adduct: el("lcmsConsensusAdduct") ? (el("lcmsConsensusAdduct").value.trim() || "[M+H]+") : "[M+H]+",
              anchor_group_id: el("lcmsConsensusAnchorGroup") ? (el("lcmsConsensusAnchorGroup").value.trim() || null) : null,
              mz_tolerance_da: Number(el("lcmsConsensusMzTolDa").value || "0.02"),
              ppm_tolerance: Number(el("lcmsConsensusPpmTol").value || "20"),
              family_rt_tolerance_min: Number(el("lcmsConsensusRtTol").value || "0.15"),
              min_blank_subtracted_area: Number(el("lcmsConsensusMinArea").value || "0"),
              blank_area_ratio_threshold: Number(el("lcmsConsensusBlankRatio").value || "0.30"),
              include_background_groups: Boolean(el("lcmsConsensusIncludeBackground") && el("lcmsConsensusIncludeBackground").checked),
              require_sample_enrichment: Boolean(!el("lcmsConsensusRequireSample") || el("lcmsConsensusRequireSample").checked),
              max_families_to_report: Number(el("lcmsConsensusMaxFamilies").value || "50"),
              min_consensus_score_to_promote: Number(el("lcmsConsensusMinScore").value || "0.62")
            };
            if (!payload.grouping_result && !payload.feature_table_text) throw new Error("Run LC-MS feature grouping or paste a grouped feature table first.");
            const data = await api("/ms/lcms/features/consensus", { method: "POST", body: JSON.stringify(payload) });
            setJson(data);
            renderLCMSFeatureConsensus(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("lcmsFeatureConsensusBox")) el("lcmsFeatureConsensusBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function renderLCMSFeatureConsensus(data) {
          state.latestLCMSFeatureConsensus = data;
          const families = Array.isArray(data?.families) ? data.families : [];
          const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
          const actions = Array.isArray(data?.recommended_next_actions) ? data.recommended_next_actions : [];
          const best = data?.best_family || families[0];
          const labelClass = data?.label === "ready_for_candidate_scoring" ? "ok" : data?.label === "review_conflicting_families" ? "warn" : "bad";
          const box = el("lcmsFeatureConsensusBox");
          if (!box) return;
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>LC-MS feature-family consensus</strong>
              <span class="status-badge ${labelClass}">${escapeHtml(data?.label || "insufficient_consensus")}</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">Input groups</div><div class="value">${escapeHtml(data?.input_group_count || 0)}</div></div>
              <div class="metric"><div class="label">Families</div><div class="value">${escapeHtml(data?.family_count || 0)}</div></div>
              <div class="metric"><div class="label">Promoted / Conflicting</div><div class="value">${escapeHtml(data?.promoted_family_count || 0)} / ${escapeHtml(data?.conflicting_family_count || 0)}</div></div>
              <div class="metric"><div class="label">Relationships</div><div class="value">${escapeHtml(data?.relationship_count || 0)}</div></div>
            </div>
            ${best ? `<p class="small"><strong>Best family:</strong> ${escapeHtml(best.family_id)} anchored on ${escapeHtml(best.anchor_group_id)}; score ${Math.round((best.consensus_score || 0) * 100)}%; ${best.promoted_for_candidate_scoring ? "promoted" : "review only"}.</p>` : ""}
            ${warnings.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Warnings</strong><ul>${warnings.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>` : ""}
            ${actions.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Recommended next actions</strong><ul>${actions.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></div>` : ""}
            ${families.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Family ranking</strong><table style="margin-top:.5rem;"><thead><tr><th>Family</th><th>Anchor</th><th>m/z</th><th>RT</th><th>Score</th><th>Relationships</th><th>Label</th><th>Gate</th></tr></thead><tbody>${families.slice(0, 40).map((f) => `<tr><td>${escapeHtml(f.family_id)}</td><td>${escapeHtml(f.anchor_group_id)}</td><td>${escapeHtml(f.anchor_mz)}</td><td>${escapeHtml(f.anchor_rt_min)}</td><td>${Math.round((f.consensus_score || 0) * 100)}%</td><td>${escapeHtml(f.relationship_count || 0)}</td><td><span class="status-badge ${f.promoted_for_candidate_scoring ? "ok" : f.label === "conflicting_or_background_family" ? "warn" : "bad"}">${escapeHtml(f.label)}</span></td><td>${f.promoted_for_candidate_scoring ? "promote" : "review"}</td></tr>`).join("")}</tbody></table></div>` : ""}
            ${families.length ? `<details style="margin-top:.8rem;"><summary>Consensus evidence details</summary>${families.slice(0, 12).map((f) => `<div class="panel" style="margin-top:.6rem;"><strong>${escapeHtml(f.family_id)} - ${escapeHtml(f.anchor_group_id)}</strong><div class="small muted">${(f.evidence_summary || []).map(escapeHtml).join("<br>")}</div>${(f.relationships || []).length ? `<ul>${f.relationships.map((r) => `<li>${escapeHtml(r.label)} with ${escapeHtml(r.partner_group_id)}; ratio ${escapeHtml(r.intensity_ratio_percent)}%</li>`).join("")}</ul>` : `<p class="small muted">No isotope/adduct/loss relationship detected.</p>`}<table style="margin-top:.5rem;"><thead><tr><th>Layer</th><th>Score</th><th>Status</th><th>Evidence</th></tr></thead><tbody>${(f.layer_scores || []).map((l) => `<tr><td>${escapeHtml(l.label)}</td><td>${l.score !== null && l.score !== undefined ? Math.round(l.score * 100) + "%" : "-"}</td><td>${escapeHtml(l.status)}</td><td>${escapeHtml((l.evidence_summary || []).join("; "))}</td></tr>`).join("")}</tbody></table></div>`).join("")}</details>` : ""}
            ${data?.family_table_text ? `<details style="margin-top:.8rem;"><summary>Exportable consensus table</summary><pre style="white-space:pre-wrap;">${escapeHtml(data.family_table_text)}</pre></details>` : ""}
          `;
        }

        function copyLCMSConsensusToReport() {
          const data = state.latestLCMSFeatureConsensus;
          if (!data) {
            if (el("lcmsFeatureConsensusBox")) el("lcmsFeatureConsensusBox").innerHTML = `<p style="color:var(--danger);">Score LC-MS feature-family consensus before copying report provenance.</p>`;
            return;
          }
          if (el("structureReportProcessingHistory")) {
            const current = el("structureReportProcessingHistory").value.trim();
            const line = `LC-MS feature-family consensus: ${data.family_count || 0} families; ${data.promoted_family_count || 0} promoted; ${data.conflicting_family_count || 0} conflicting; label ${data.label || "unavailable"}`;
            el("structureReportProcessingHistory").value = current ? `${current}\n${line}` : line;
          }
          if (el("structureReportNotes") && data.family_table_text) {
            const current = el("structureReportNotes").value.trim();
            const note = `LC-MS feature-family consensus table:\n${data.family_table_text}`;
            el("structureReportNotes").value = current ? `${current}\n\n${note}` : note;
          }
        }

        function clearLCMSFeatureConsensus() {
          state.latestLCMSFeatureConsensus = null;
          if (el("lcmsFeatureConsensusBox")) el("lcmsFeatureConsensusBox").innerHTML = "No LC-MS feature-family consensus result yet.";
        }

        function downloadBlob(text, filename, mimeType) {
          const blob = new Blob([text], { type: mimeType });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(url);
        }

        function downloadStructureReportJson() {
          if (!state.latestStructureReport) {
            if (el("structureReportBox")) el("structureReportBox").innerHTML = `<p style="color:var(--danger);">Compose a report before downloading.</p>`;
            return;
          }
          const filename = `${state.latestStructureReport.report_id || "structure_report"}.json`;
          downloadBlob(JSON.stringify(state.latestStructureReport.json_report || state.latestStructureReport, null, 2), filename, "application/json");
        }

        function downloadStructureReportHtml() {
          if (!state.latestStructureReport || !state.latestStructureReport.html_report) {
            if (el("structureReportBox")) el("structureReportBox").innerHTML = `<p style="color:var(--danger);">Compose a report before downloading HTML.</p>`;
            return;
          }
          const filename = `${state.latestStructureReport.report_id || "structure_report"}.html`;
          downloadBlob(state.latestStructureReport.html_report, filename, "text/html");
        }

        function renderMetricCards(summary) {
          const cards = [
            ["Analyses", summary.total_analyses ?? "—"],
            ["Jobs", summary.total_jobs ?? "—"],
            ["Hours saved", summary.hours_saved_estimate ?? "—"],
            ["Validation fails caught", summary.validation_failures ?? "—"],
            ["Pending review", summary.pending_review ?? "—"],
            ["Overrides", summary.overrides ?? "—"],
          ];
          el("metricsGrid").innerHTML = cards.map(([label, value]) => `<div class="metric"><div class="label">${escapeHtml(label)}</div><div class="value">${escapeHtml(value)}</div></div>`).join("");
          el("dashboardNotes").innerHTML = `<strong>Operational summary</strong><p class="muted small">Refresh metrics reloads the latest app-wide counts from the server so you can see analyses, jobs, review load, and estimated time saved. Metrics are admin-facing because they summarize the whole workspace.</p>`;
        }

        function getStatusVariant(value) {
          const text = String(value || "");
          if (/approved|consistent|complete|success|ok|exact_mass_match|consistent_with_msms|strong_adduct_evidence|clear_isotope_cluster|strong_fragmentation_tree_support|high_confidence_candidate|strong_agreement/i.test(text)) return "ok";
          if (/reject|invalid|error|fail|impurity|outside_tolerance|weak_or_no_msms_support|weak_adduct_evidence|incompatible_adduct|weak_fragmentation_tree_support|contradictory_fragmentation_tree|conflicting_evidence|insufficient_evidence|poor_agreement|contradiction/i.test(text)) return "bad";
          return "warn";
        }

        function getSelectedWorkspaceProject() {
          return state.workspaceProjects.find((project) => Number(project.id) === Number(state.selectedProjectId)) || null;
        }

        function formatDateTime(value) {
          if (!value) return "—";
          const parsed = new Date(value);
          if (Number.isNaN(parsed.getTime())) return String(value);
          return parsed.toLocaleString();
        }

        function getWorkspaceSampleById(sampleRecordId) {
          return (state.workspaceSamples || []).find((sample) => Number(sample.id) === Number(sampleRecordId)) || null;
        }

        function getWorkspaceSampleName(sample) {
          if (!sample) return "No sample";
          return sample.sample_id || `Sample #${sample.id ?? "?"}`;
        }

        function renderWorkspaceProjectDashboard() {
          const box = el("workspaceProjectDashboardBox");
          if (!box) return;
          const project = getSelectedWorkspaceProject();
          if (!project) {
            box.innerHTML = "No project selected yet.";
            return;
          }
          const samples = (state.workspaceSamples || []).filter((sample) => Number(sample.project_id) === Number(project.id));
          const dashboard = Number(state.workspaceProjectDashboard?.project?.id) === Number(project.id)
            ? state.workspaceProjectDashboard
            : null;
          const linkedAnalysisCount = samples.length
            ? samples.filter((sample) => sample.analysis_id).length
            : (project.linked_analysis_count ?? project.analysis_count ?? 0);
          const solventDistribution = dashboard?.solvent_distribution || {};
          const solvents = Object.keys(solventDistribution).length
            ? Object.entries(solventDistribution).map(([name, count]) => `${prettyChemicalLabel(name)} (${count})`)
            : [...new Set(samples.map((sample) => sample.solvent).filter(Boolean))].map(prettyChemicalLabel);
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:flex-start; flex-wrap:wrap;">
              <div>
                <div class="card-kicker">Project dashboard</div>
                <h3 style="margin:.2rem 0;">${escapeHtml(project.name || "Untitled project")}</h3>
                <p class="muted small" style="margin:.25rem 0 0;">${escapeHtml(project.description || "No description supplied.")}</p>
              </div>
              <span class="status-badge ok">Workspace view</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">Project name</div><div class="value">${escapeHtml(project.name || "—")}</div></div>
              <div class="metric"><div class="label">Description</div><div class="value">${escapeHtml(project.description || "—")}</div></div>
              <div class="metric"><div class="label">Sample count</div><div class="value">${escapeHtml(project.sample_count ?? samples.length)}</div></div>
              <div class="metric"><div class="label">Analysis count</div><div class="value">${escapeHtml(dashboard?.analysis_count ?? project.analysis_count ?? 0)}</div></div>
              <div class="metric"><div class="label">Linked-analysis count</div><div class="value">${escapeHtml(linkedAnalysisCount)}</div></div>
              <div class="metric"><div class="label">Approved reviews</div><div class="value">${escapeHtml(dashboard?.approved_reviews ?? "—")}</div></div>
              <div class="metric"><div class="label">Rejected reviews</div><div class="value">${escapeHtml(dashboard?.rejected_reviews ?? "—")}</div></div>
              <div class="metric"><div class="label">Pending review</div><div class="value">${escapeHtml(dashboard?.pending_review ?? "—")}</div></div>
              <div class="metric"><div class="label">Hours saved</div><div class="value">${escapeHtml(dashboard?.hours_saved_estimate ?? "—")}</div></div>
              <div class="metric"><div class="label">Likely impurity flags</div><div class="value">${escapeHtml(dashboard?.likely_impurity_flags ?? "—")}</div></div>
              <div class="metric"><div class="label">Solvents used</div><div class="value">${escapeHtml(solvents.length ? solvents.join(", ") : "—")}</div></div>
            </div>
            ${dashboard?.latest_activity?.length ? `<div class="report-section" style="margin-top:.85rem;"><h4>Latest activity</h4>${renderAuditEventTable(dashboard.latest_activity)}</div>` : ""}
          `;
        }

        function renderWorkspaceSampleDetail(sample, report=null) {
          const badge = el("workspaceSampleBadge");
          const box = el("workspaceSampleDetailBox");
          if (!box) return;
          if (!sample) {
            if (badge) {
              badge.className = "status-badge warn";
              badge.textContent = "No sample opened";
            }
            box.innerHTML = "No sample opened yet.";
            return;
          }
          const detail = Number(state.workspaceSampleDetail?.sample?.id) === Number(sample.id)
            ? state.workspaceSampleDetail
            : null;
          const notes = report && Array.isArray(report.confidence_notes)
            ? report.confidence_notes
            : (Array.isArray(detail?.notes) ? detail.notes : []);
          const latestAnalysisId = detail?.latest_analysis?.id || sample.analysis_id || null;
          if (badge) {
            badge.className = `status-badge ${latestAnalysisId ? "ok" : "warn"}`;
            badge.textContent = latestAnalysisId ? `Analysis #${latestAnalysisId}` : "Unlinked sample";
          }
          box.innerHTML = `
            <div class="summary-grid">
              <div class="metric"><div class="label">Sample name</div><div class="value">${escapeHtml(getWorkspaceSampleName(sample))}</div></div>
              <div class="metric"><div class="label">Sample ID</div><div class="value">${escapeHtml(sample.id ?? "—")}</div></div>
              <div class="metric"><div class="label">Solvent</div><div class="value">${escapeHtml(prettyChemicalLabel(sample.solvent || "—"))}</div></div>
              <div class="metric"><div class="label">Created time</div><div class="value">${escapeHtml(formatDateTime(sample.created_at))}</div></div>
              <div class="metric"><div class="label">Latest linked analysis</div><div class="value">${escapeHtml(latestAnalysisId || "—")}</div></div>
              <div class="metric"><div class="label">Stored reports</div><div class="value">${escapeHtml(detail?.reports_count ?? "—")}</div></div>
              <div class="metric"><div class="label">SMILES</div><div class="value mono">${escapeHtml(sample.smiles || "—")}</div></div>
            </div>
            <div class="report-section" style="margin-top:.85rem;">
              <h4>Notes</h4>
              ${renderTextList(notes, latestAnalysisId ? "No notes loaded for this linked analysis." : "No linked analysis notes.")}
            </div>
            <div class="row" style="margin-top:.85rem;">
              <button class="secondary" onclick="compareWorkspaceSampleAnalyses(${sample.id})">Compare analyses</button>
              ${latestAnalysisId ? `<button class="primary" onclick="loadSampleLatestReport(${sample.id})">Load latest report</button><button class="ghost" onclick="inspectSampleReviewerTimeline(${sample.id})">Inspect reviewer timeline</button>` : '<button class="ghost" disabled>Load latest report</button><button class="ghost" disabled>Inspect reviewer timeline</button>'}
            </div>
          `;
        }

        function getUniqueAnalysisRecords(records) {
          const seen = new Set();
          return (Array.isArray(records) ? records : []).filter((record) => {
            const id = Number(record?.id);
            if (!Number.isFinite(id) || seen.has(id)) return false;
            seen.add(id);
            return true;
          }).sort((a, b) => Number(b.id) - Number(a.id));
        }

        function getComparableAnalysesForSample(sample) {
          const records = [...(state.historyItems || [])];
          const loadedAnalysis = state.loadedEvidenceReport?.analysis || state.workspaceSampleReport?.analysis || null;
          if (loadedAnalysis) records.push(loadedAnalysis);
          const sampleId = String(sample?.sample_id || "").trim();
          let basis = "";
          let matches = [];
          if (sampleId) {
            matches = records.filter((record) => String(record.sample_id || "").trim() === sampleId);
            if (matches.length) basis = "Same sample ID";
          }
          if (!matches.length && sample?.smiles) {
            matches = records.filter((record) => String(record.smiles || "").trim() === String(sample.smiles || "").trim());
            if (matches.length) basis = "Same-SMILES fallback";
          }
          return { basis: basis || "No comparison basis", matches: getUniqueAnalysisRecords(matches) };
        }

        function renderSampleAnalysisComparison(sample) {
          const box = el("workspaceComparisonBox");
          if (!box) return;
          if (!sample) {
            box.innerHTML = "No sample opened yet.";
            return;
          }
          const backendComparison = Number(state.workspaceSampleComparison?.sample?.id) === Number(sample.id)
            ? state.workspaceSampleComparison
            : null;
          if (backendComparison) {
            const basisText = backendComparison.basis === "sample_id"
              ? "Same sample ID"
              : (backendComparison.basis === "smiles" ? "Same-SMILES fallback" : "No comparison basis");
            const items = Array.isArray(backendComparison.items) ? backendComparison.items : [];
            if (!items.length) {
              box.innerHTML = `<div class="card-kicker">Sample analysis comparison</div><p class="muted small">No comparable analyses found for this sample.</p>`;
              return;
            }
            box.innerHTML = `
              <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                <div>
                  <div class="card-kicker">Sample analysis comparison</div>
                  <strong>${escapeHtml(basisText)}</strong>
                </div>
                <span class="status-badge ok">${escapeHtml(items.length)} comparable</span>
              </div>
              <table style="margin-top:.75rem;">
                <thead><tr><th>Analysis</th><th>Label</th><th>Δ H</th><th>Confidence</th><th>Impurity</th><th>Review</th><th>Peaks</th><th>Time saved</th><th>Quick actions</th></tr></thead>
                <tbody>${items.map((record) => {
                  const statusText = record.reviewer_outcome || record.label || "analysis";
                  return `<tr>
                    <td>#${escapeHtml(record.analysis_id)}</td>
                    <td>${escapeHtml(record.final_label || record.label || "—")}</td>
                    <td>${escapeHtml(record.proton_count_delta ?? "—")}</td>
                    <td>${escapeHtml(record.confidence ?? "—")}</td>
                    <td>${escapeHtml(record.impurity_flags ?? 0)}</td>
                    <td><span class="status-badge ${getStatusVariant(statusText)}">${escapeHtml(statusText)}</span></td>
                    <td>${escapeHtml(record.peak_count ?? "—")} (${escapeHtml(record.peak_count_change ?? 0)})</td>
                    <td>${escapeHtml(record.time_saved ?? "—")}</td>
                    <td><button class="ghost" onclick="loadEvidenceReportJson(${record.analysis_id})">Report JSON</button><button class="ghost" onclick="openEvidenceReportHtml(${record.analysis_id})">HTML report</button></td>
                  </tr>`;
                }).join("")}</tbody>
              </table>
            `;
            return;
          }
          const comparison = getComparableAnalysesForSample(sample);
          if (!comparison.matches.length) {
            box.innerHTML = `
              <div class="card-kicker">Sample analysis comparison</div>
              <p class="muted small">No comparable analyses found in cached history.</p>
              <div class="summary-grid">
                <div class="metric"><div class="label">Sample ID match</div><div class="value">${escapeHtml(sample.sample_id || "—")}</div></div>
                <div class="metric"><div class="label">Same-SMILES fallback</div><div class="value mono">${escapeHtml(sample.smiles || "—")}</div></div>
              </div>
            `;
            return;
          }
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <div>
                <div class="card-kicker">Sample analysis comparison</div>
                <strong>${escapeHtml(comparison.basis)}</strong>
              </div>
              <span class="status-badge ok">${escapeHtml(comparison.matches.length)} comparable</span>
            </div>
            <table style="margin-top:.75rem;">
              <thead><tr><th>Analysis</th><th>Created</th><th>Status</th><th>Solvent</th><th>Confidence</th><th>Quick actions</th></tr></thead>
              <tbody>${comparison.matches.map((record) => {
                const statusText = record.review_status || record.label || "analysis";
                return `<tr>
                  <td>#${escapeHtml(record.id)}</td>
                  <td>${escapeHtml(formatDateTime(record.created_at))}</td>
                  <td><span class="status-badge ${getStatusVariant(statusText)}">${escapeHtml(statusText)}</span></td>
                  <td>${escapeHtml(prettyChemicalLabel(record.solvent || "—"))}</td>
                  <td>${escapeHtml(record.confidence ?? "—")}</td>
                  <td><button class="ghost" onclick="loadEvidenceReportJson(${record.id})">Report JSON</button><button class="ghost" onclick="openEvidenceReportHtml(${record.id})">HTML report</button></td>
                </tr>`;
              }).join("")}</tbody>
            </table>
          `;
        }

        function renderReviewerTimeline(analysisId, decisions=[], auditEvents=[], errorText="") {
          const badge = el("workspaceTimelineBadge");
          const box = el("workspaceTimelineBox");
          if (!box) return;
          const hasAnalysis = Number(analysisId) > 0;
          if (badge) {
            badge.className = `status-badge ${hasAnalysis ? "ok" : "warn"}`;
            badge.textContent = hasAnalysis ? `Analysis #${analysisId}` : "No linked analysis";
          }
          if (!hasAnalysis) {
            box.innerHTML = "No linked analysis loaded yet.";
            return;
          }
          const decisionItems = (Array.isArray(decisions) ? decisions : []).map((decision) => ({
            kind: "Reviewer action",
            title: decision.action || "review",
            body: `${decision.previous_status || "—"} -> ${decision.new_status || "—"}${decision.comment ? `: ${decision.comment}` : ""}`,
            created_at: decision.created_at,
          }));
          const auditItems = (Array.isArray(auditEvents) ? auditEvents : []).map((event) => ({
            kind: "Audit event",
            title: event.event_type || "audit",
            body: event.message || "—",
            created_at: event.created_at,
          }));
          const items = [...decisionItems, ...auditItems].sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
          box.innerHTML = `
            ${errorText ? `<p style="color:var(--danger);">${escapeHtml(errorText)}</p>` : ""}
            <div class="summary-grid">
              <div class="metric"><div class="label">Reviewer actions</div><div class="value">${escapeHtml(decisionItems.length)}</div></div>
              <div class="metric"><div class="label">Audit messages</div><div class="value">${escapeHtml(auditItems.length)}</div></div>
              <div class="metric"><div class="label">Analysis ID</div><div class="value">${escapeHtml(analysisId)}</div></div>
            </div>
            ${items.length ? `<div class="timeline-list" style="margin-top:.85rem;">${items.map((item) => `
              <div class="timeline-item">
                <div style="display:flex; justify-content:space-between; gap:.7rem; align-items:flex-start; flex-wrap:wrap;">
                  <strong>${escapeHtml(item.title)}</strong>
                  <span class="status-badge warn">${escapeHtml(item.kind)}</span>
                </div>
                <div class="timeline-meta">${escapeHtml(formatDateTime(item.created_at))}</div>
                <div class="small" style="margin-top:.35rem;">${escapeHtml(item.body)}</div>
              </div>
            `).join("")}</div>` : '<p class="muted small" style="margin-top:.85rem;">No reviewer timeline or audit trail entries recorded for this analysis.</p>'}
          `;
        }

        function renderTextList(items, emptyText) {
          const list = Array.isArray(items) ? items.filter((item) => item !== null && item !== undefined && String(item).trim()) : [];
          return list.length
            ? `<ul>${list.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
            : `<p class="muted small">${escapeHtml(emptyText)}</p>`;
        }

        function renderPeakListTable(peaks) {
          const rows = Array.isArray(peaks) ? peaks : [];
          if (!rows.length) return '<p class="muted small">No peaks available.</p>';
          return `<table><thead><tr><th>Shift (ppm)</th><th>Multiplicity</th><th>Coupling Constant</th><th>Integration</th></tr></thead><tbody>${rows.map((peak) => `<tr><td>${escapeHtml(peak.shift_ppm ?? "—")}</td><td>${escapeHtml(peak.multiplicity ?? "—")}</td><td>${escapeHtml(getSpectrumJValueText(peak) || "—")}</td><td>${escapeHtml(peak.integration_h ?? "—")}</td></tr>`).join("")}</tbody></table>`;
        }

        function renderReviewDecisionTable(decisions) {
          const rows = Array.isArray(decisions) ? decisions : [];
          if (!rows.length) return '<p class="muted small">No reviewer decisions recorded.</p>';
          return `<table><thead><tr><th>Action</th><th>Status</th><th>Comment</th><th>Created</th></tr></thead><tbody>${rows.map((decision) => `<tr><td>${escapeHtml(decision.action || "—")}</td><td>${escapeHtml(decision.new_status || "—")}</td><td>${escapeHtml(decision.comment || "—")}</td><td>${escapeHtml(decision.created_at || "—")}</td></tr>`).join("")}</tbody></table>`;
        }

        function renderAuditEventTable(events) {
          const rows = Array.isArray(events) ? events : [];
          if (!rows.length) return '<p class="muted small">No audit events recorded.</p>';
          return `<table><thead><tr><th>Event</th><th>Message</th><th>Created</th></tr></thead><tbody>${rows.slice(0, 12).map((event) => `<tr><td>${escapeHtml(event.event_type || "—")}</td><td>${escapeHtml(event.message || "—")}</td><td>${escapeHtml(event.created_at || "—")}</td></tr>`).join("")}</tbody></table>`;
        }

        function renderProjects(items) {
          state.workspaceProjects = Array.isArray(items) ? items : [];
          if (!state.workspaceProjects.length) {
            state.selectedProjectId = null;
            updateWorkspaceSelectionBox();
            if (el("workspaceProjectsBox")) el("workspaceProjectsBox").innerHTML = '<p class="muted">No projects found yet.</p>';
            return;
          }
          if (!state.workspaceProjects.some((project) => Number(project.id) === Number(state.selectedProjectId))) {
            state.selectedProjectId = state.workspaceProjects[0].id;
          }
          updateWorkspaceSelectionBox();
          el("workspaceProjectsBox").innerHTML = `<div class="project-grid">${state.workspaceProjects.map((project) => {
            const isSelected = Number(project.id) === Number(state.selectedProjectId);
            return `
              <article class="project-card ${isSelected ? "selected" : ""}">
                <div class="card-kicker">Project #${escapeHtml(project.id ?? "—")}</div>
                <div style="display:flex; justify-content:space-between; gap:.7rem; align-items:flex-start;">
                  <h4>${escapeHtml(project.name || "Untitled project")}</h4>
                  <span class="status-badge ${isSelected ? "ok" : "warn"}">${isSelected ? "Selected" : "Workspace"}</span>
                </div>
                <p class="card-description">${escapeHtml(project.description || "No description supplied.")}</p>
                <div class="mini-grid">
                  <div class="mini-metric"><div class="label">Sample count</div><div class="value">${escapeHtml(project.sample_count ?? 0)}</div></div>
                  <div class="mini-metric"><div class="label">Analysis count</div><div class="value">${escapeHtml(project.analysis_count ?? 0)}</div></div>
                  <div class="mini-metric"><div class="label">Owner ID</div><div class="value">${escapeHtml(project.user_id ?? "—")}</div></div>
                  <div class="mini-metric"><div class="label">Updated</div><div class="value">${escapeHtml(project.updated_at || "—")}</div></div>
                </div>
                <div class="row" style="margin-top:.75rem;">
                  <button class="${isSelected ? "secondary" : "primary"}" onclick="openWorkspaceProject(${project.id})">Open workspace</button>
                  <button class="ghost" onclick="prepareNewWorkspaceSample(${project.id})">New sample</button>
                </div>
              </article>
            `;
          }).join("")}</div>`;
        }

        function renderWorkspaceSamples(items) {
          state.workspaceSamples = Array.isArray(items) ? items : [];
          if (!state.workspaceSamples.length) {
            state.selectedWorkspaceSampleId = null;
            state.selectedWorkspaceSample = null;
            state.workspaceSampleReport = null;
            renderWorkspaceProjectDashboard();
            renderWorkspaceSampleDetail(null);
            renderSampleAnalysisComparison(null);
            if (el("workspaceSamplesBox")) el("workspaceSamplesBox").innerHTML = '<p class="muted">No samples stored for this project yet.</p>';
            return;
          }
          if (state.selectedWorkspaceSampleId && !getWorkspaceSampleById(state.selectedWorkspaceSampleId)) {
            state.selectedWorkspaceSampleId = null;
            state.selectedWorkspaceSample = null;
            state.workspaceSampleReport = null;
          }
          renderWorkspaceProjectDashboard();
          el("workspaceSamplesBox").innerHTML = `<div class="sample-grid">${state.workspaceSamples.map((sample) => {
            const latestAnalysisId = sample.analysis_id || null;
            const isSelected = Number(sample.id) === Number(state.selectedWorkspaceSampleId);
            return `
              <article class="sample-card ${isSelected ? "selected" : ""}">
                <div class="card-kicker">Sample name</div>
                <div style="display:flex; justify-content:space-between; gap:.7rem; align-items:flex-start;">
                  <h4>${escapeHtml(sample.sample_id || `Sample #${sample.id}`)}</h4>
                  <span class="status-badge ${isSelected ? "ok" : (latestAnalysisId ? "ok" : "warn")}">${isSelected ? "Opened" : (latestAnalysisId ? "Linked analysis" : "Unlinked")}</span>
                </div>
                <div class="mini-grid" style="margin-top:.7rem;">
                  <div class="mini-metric"><div class="label">Sample ID</div><div class="value">${escapeHtml(sample.id ?? "—")}</div></div>
                  <div class="mini-metric"><div class="label">Solvent</div><div class="value">${escapeHtml(prettyChemicalLabel(sample.solvent || "—"))}</div></div>
                  <div class="mini-metric"><div class="label">Latest linked analysis ID</div><div class="value">${escapeHtml(latestAnalysisId || "—")}</div></div>
                  <div class="mini-metric"><div class="label">Updated</div><div class="value">${escapeHtml(sample.updated_at || "—")}</div></div>
                </div>
                <div class="card-kicker" style="margin-top:.75rem;">Sample SMILES</div>
                <div class="sample-smiles mono">${escapeHtml(sample.smiles || "—")}</div>
                <div class="row" style="margin-top:.75rem;">
                  <button class="primary" onclick="openWorkspaceSampleDetail(${sample.id})">Open sample</button>
                  <button class="secondary" onclick="linkWorkspaceSampleToLatestAnalysis(${sample.project_id}, ${sample.id})">Link current analysis</button>
                  ${latestAnalysisId ? `<button class="ghost" onclick="loadEvidenceReportJson(${latestAnalysisId})">Open latest report</button>` : '<button class="ghost" disabled>Open latest report</button>'}
                </div>
              </article>
            `;
          }).join("")}</div>`;
          if (state.selectedWorkspaceSampleId) {
            const selectedSample = getWorkspaceSampleById(state.selectedWorkspaceSampleId);
            state.selectedWorkspaceSample = selectedSample;
            renderWorkspaceSampleDetail(selectedSample, state.workspaceSampleReport);
            renderSampleAnalysisComparison(selectedSample);
          }
        }

        function renderNmr2dEvidenceReportSections(sections) {
          const items = Array.isArray(sections) ? sections : [];
          if (!items.length) return "";
          return items.map((section) => {
            const scoreComponents = section.score_components || {};
            const componentRows = Object.entries(scoreComponents).map(([key, value]) => `<tr><td>${escapeHtml(key.replaceAll("_", " "))}</td><td>${escapeHtml(value)}</td></tr>`).join("");
            const deptTypeRows = Object.entries(section.dept_apt_type_summary || {}).map(([key, value]) => `<tr><td>${escapeHtml(key)}</td><td>${escapeHtml(value)}</td></tr>`).join("");
            return `
              <div class="report-section">
                <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                  <h4>2D NMR Evidence</h4>
                  <span class="status-badge warn">${escapeHtml(section.human_review_status || "pending_review")}</span>
                </div>
                <div class="summary-grid">
                  <div class="metric"><div class="label">Experiment type</div><div class="value">${escapeHtml(section.experiment_type || "—")}</div></div>
                  <div class="metric"><div class="label">Peak count</div><div class="value">${escapeHtml(section.peak_count ?? 0)}</div></div>
                  <div class="metric"><div class="label">Matched correlations</div><div class="value">${escapeHtml(section.matched_correlations ?? 0)}</div></div>
                  <div class="metric"><div class="label">Suspicious correlations</div><div class="value">${escapeHtml(section.suspicious_correlations ?? 0)}</div></div>
                  <div class="metric"><div class="label">Evidence score</div><div class="value">${formatNmr2dPercent(section.evidence_score)}</div></div>
                  <div class="metric"><div class="label">Run</div><div class="value">#${escapeHtml(section.run_id || "—")}</div></div>
                  <div class="metric"><div class="label">DEPT/APT experiment</div><div class="value">${escapeHtml(section.dept_apt_experiment_type || "—")}</div></div>
                  <div class="metric"><div class="label">Typed DEPT/APT peaks</div><div class="value">${escapeHtml(section.dept_apt_typed_peak_count ?? 0)}</div></div>
                  <div class="metric"><div class="label">Matched 13C count</div><div class="value">${escapeHtml(section.dept_apt_matched_carbon13_count ?? 0)}</div></div>
                  <div class="metric"><div class="label">DEPT/APT score</div><div class="value">${formatNmr2dPercent(section.dept_apt_consistency_score)}</div></div>
                  <div class="metric"><div class="label">HSQC/HMQC DEPT support</div><div class="value">${escapeHtml(section.hsqc_hmqc_dept_apt_supported_correlations ?? 0)}</div></div>
                  <div class="metric"><div class="label">HSQC/HMQC DEPT conflicts</div><div class="value">${escapeHtml(section.hsqc_hmqc_dept_apt_conflicting_correlations ?? 0)}</div></div>
                  <div class="metric"><div class="label">HMBC DEPT context</div><div class="value">${escapeHtml(section.hmbc_dept_apt_contextual_correlations ?? 0)}</div></div>
                </div>
                <div class="grid2" style="margin-top:.85rem;">
                  <div>${renderTextList(section.cosy_connectivity_notes || [], "No COSY connectivity notes.")}</div>
                  <div>${renderTextList(section.hsqc_hmqc_direct_attachment_notes || [], "No HSQC/HMQC direct attachment notes.")}</div>
                  <div>${renderTextList(section.hmbc_long_range_notes || [], "No HMBC long-range notes.")}</div>
                  <div>${renderTextList(section.missing_extra_correlation_notes || [], "No missing or extra correlation notes.")}</div>
                </div>
                ${section.warnings?.length ? `<div style="margin-top:.85rem;">${renderTextList(section.warnings, "No 2D warnings.")}</div>` : ""}
                ${deptTypeRows || section.dept_apt_apt_convention_warning ? `<details style="margin-top:.85rem;"><summary>DEPT/APT evidence</summary>${deptTypeRows ? `<table><tbody>${deptTypeRows}</tbody></table>` : ""}${section.dept_apt_apt_convention_warning ? `<p class="muted small">${escapeHtml(section.dept_apt_apt_convention_warning)}</p>` : ""}</details>` : ""}
                ${componentRows ? `<details style="margin-top:.85rem;"><summary>Score components</summary><table><tbody>${componentRows}</tbody></table></details>` : ""}
                <div class="row" style="margin-top:.75rem;"><button class="ghost" onclick="openAuthedPath('${escapeHtml(section.report_url || `/nmr2d/runs/${section.run_id}/report`)}')">Open 2D evidence</button></div>
              </div>
            `;
          }).join("");
        }

        function renderEvidenceReport(report) {
          state.loadedEvidenceReport = report || null;
          if (!report) {
            if (el("workspaceReportBox")) el("workspaceReportBox").innerHTML = "No report loaded yet.";
            return;
          }
          const analysis = report.analysis || {};
          const structure = report.structure || {};
          const notes = Array.isArray(report.confidence_notes) ? report.confidence_notes : [];
          const decisions = Array.isArray(report.review_decisions) ? report.review_decisions : [];
          const auditEvents = Array.isArray(report.audit_events) ? report.audit_events : [];
          const peaks = Array.isArray(report.parsed_peaks) ? report.parsed_peaks : [];
          const impurities = Array.isArray(report.impurity_candidates) ? report.impurity_candidates : [];
          const unmatched = Array.isArray(report.unmatched_peaks) ? report.unmatched_peaks : [];
          const rawFidProcessing = report.audit_metadata && report.audit_metadata.raw_fid_processing
            ? report.audit_metadata.raw_fid_processing
            : null;
          const nmr2dEvidence = Array.isArray(report.nmr2d_evidence) ? report.nmr2d_evidence : [];
          const project = getSelectedWorkspaceProject();
          const sampleContext = state.workspaceSamples.find((sample) => Number(sample.analysis_id) === Number(analysis.id))
            || state.workspaceSamples.find((sample) => sample.sample_id && analysis.sample_id && sample.sample_id === analysis.sample_id)
            || null;
          const statusText = analysis.review_status || analysis.label || "report";
          const statusVariant = getStatusVariant(statusText);
          const canReview = Boolean(state.me && state.me.is_admin && analysis.id);
          setLatestAnalysisId(analysis.id);
          renderReviewerTimeline(analysis.id, decisions, auditEvents);
          if (sampleContext && Number(sampleContext.id) === Number(state.selectedWorkspaceSampleId)) {
            state.workspaceSampleReport = report;
            renderWorkspaceSampleDetail(sampleContext, report);
            renderSampleAnalysisComparison(sampleContext);
          }
          el("workspaceReportBox").innerHTML = `
            <div class="report-preview">
              <div class="report-section">
                <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                  <div>
                    <div class="card-kicker">Evidence report</div>
                    <h4>${escapeHtml(analysis.sample_id || `Analysis #${analysis.id || "?"}`)}</h4>
                  </div>
                  <span class="status-badge ${statusVariant}">${escapeHtml(statusText)}</span>
                </div>
                <div class="summary-grid">
                  <div class="metric"><div class="label">Analysis ID</div><div class="value">${escapeHtml(analysis.id ?? "—")}</div></div>
                  <div class="metric"><div class="label">Confidence</div><div class="value">${escapeHtml(analysis.confidence ?? "—")}</div></div>
                  <div class="metric"><div class="label">Parsed peaks</div><div class="value">${escapeHtml(peaks.length)}</div></div>
                  <div class="metric"><div class="label">Time saved</div><div class="value">${escapeHtml(report.time_saved_estimate ?? analysis.hours_saved_estimate ?? "—")} h</div></div>
                </div>
                <div class="row" style="margin-top:.8rem;">
                  <button class="primary" onclick="openEvidenceReportHtml(${analysis.id})">Open HTML report</button>
                  <button class="ghost" onclick="openAuthedPath('/reports/${analysis.id}.json')">Open report JSON</button>
                </div>
              </div>

              <div class="report-section">
                <h4>Project / sample context</h4>
                <div class="summary-grid">
                  <div class="metric"><div class="label">Project</div><div class="value">${escapeHtml(project?.name || "No project selected")}</div></div>
                  <div class="metric"><div class="label">Owner ID</div><div class="value">${escapeHtml(project?.user_id ?? analysis.user_id ?? "—")}</div></div>
                  <div class="metric"><div class="label">Sample name</div><div class="value">${escapeHtml(sampleContext?.sample_id || analysis.sample_id || "—")}</div></div>
                  <div class="metric"><div class="label">Sample ID</div><div class="value">${escapeHtml(sampleContext?.id ?? "—")}</div></div>
                  <div class="metric"><div class="label">Solvent</div><div class="value">${escapeHtml(prettyChemicalLabel(analysis.solvent || sampleContext?.solvent || "—"))}</div></div>
                  <div class="metric"><div class="label">SMILES</div><div class="value mono">${escapeHtml(analysis.smiles || sampleContext?.smiles || "—")}</div></div>
                </div>
              </div>

              ${canReview ? `<div class="report-section">
                <h4>Reviewer signoff</h4>
                <div class="row">
                  <button class="secondary" onclick="approveReview(${analysis.id}, { refreshReport: true })">Approve</button>
                  <button class="danger" onclick="rejectReview(${analysis.id}, { refreshReport: true })">Reject</button>
                  <button class="ghost" onclick="overrideReview(${analysis.id}, { refreshReport: true })">Override</button>
                </div>
              </div>` : ""}

              <div class="report-section">
                <h4>Structured evidence</h4>
                <div class="summary-grid">
                  <div class="metric"><div class="label">Formula</div><div class="value">${escapeHtml(prettyFormula(structure.formula || "—"))}</div></div>
                  <div class="metric"><div class="label">Molecular weight</div><div class="value">${escapeHtml(structure.molecular_weight ?? "—")}</div></div>
                  <div class="metric"><div class="label">Expected total H</div><div class="value">${escapeHtml(analysis.expected_total_h ?? structure.total_hydrogens ?? "—")}</div></div>
                  <div class="metric"><div class="label">Observed total H</div><div class="value">${escapeHtml(analysis.observed_total_h ?? "—")}</div></div>
                  <div class="metric"><div class="label">Delta total H</div><div class="value">${escapeHtml(analysis.delta_total_h ?? "—")}</div></div>
                  <div class="metric"><div class="label">Review decisions</div><div class="value">${escapeHtml(decisions.length)}</div></div>
                </div>
                <div class="mono" style="margin-top:.75rem; white-space:pre-wrap;">${escapeHtml(report.parsed_nmr_text || analysis.nmr_text || "")}</div>
              </div>

              ${rawFidProcessing ? renderFidProcessingEvidence({ processing_metadata: rawFidProcessing }) : ""}

              ${renderNmr2dEvidenceReportSections(nmr2dEvidence)}

              <div class="report-section">
                <h4>Peak list table</h4>
                ${renderPeakListTable(peaks)}
              </div>

              <div class="report-section">
                <h4>Confidence notes</h4>
                ${renderTextList(notes, "No confidence notes recorded.")}
              </div>

              <div class="report-section">
                <h4>Impurity / unmatched evidence</h4>
                ${impurities.length ? renderTextList(impurities, "No likely impurity candidates recorded.") : renderPeakListTable(unmatched)}
              </div>

              <div class="report-section">
                <h4>Reviewer decisions</h4>
                ${renderReviewDecisionTable(decisions)}
              </div>

              <div class="report-section">
                <h4>Audit trail</h4>
                ${renderAuditEventTable(auditEvents)}
              </div>
            </div>
          `;
        }

        function renderJobs(items) {
          if (!Array.isArray(items) || !items.length) { el("jobsBox").innerHTML = '<p class="muted">No jobs found.</p>'; return; }
          el("jobsBox").innerHTML = items.map((job) => `<div class="record-card"><div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;"><strong>Job #${job.id ?? "?"}</strong><span class="status-badge warn">${escapeHtml(job.status || "unknown")}</span></div><div class="muted small">Name: ${escapeHtml(job.name || job.job_name || "Untitled")}</div><div class="muted small">Created: ${escapeHtml(job.created_at || "—")}</div><div class="row" style="margin-top:.65rem;"><button class="ghost" onclick="viewJobItems(${job.id})">Items</button><button class="ghost" onclick="openAuthedPath('/jobs/${job.id}/export.csv')">CSV</button><button class="ghost" onclick="openAuthedPath('/jobs/${job.id}/export.json')">JSON</button></div></div>`).join("");
        }

        function renderHistory(items) {
          state.historyItems = Array.isArray(items) ? items : [];
          if (state.historyItems.length) setLatestAnalysisId(state.historyItems[0].id);
          if (!Array.isArray(items) || !items.length) { el("historyBox").innerHTML = '<p class="muted">No history records found.</p>'; return; }
          el("historyBox").innerHTML = items.map((item) => `<div class="record-card"><div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;"><strong>${escapeHtml(item.sample_id || `History #${item.id ?? "?"}`)}</strong><span class="status-badge warn">${escapeHtml(item.label || "record")}</span></div><div class="muted small">Created: ${escapeHtml(item.created_at || "—")}</div><div class="summary-grid"><div class="metric"><div class="label">Expected H</div><div class="value">${item.expected_total_h ?? "—"}</div></div><div class="metric"><div class="label">Observed H</div><div class="value">${item.observed_total_h ?? "—"}</div></div><div class="metric"><div class="label">Confidence</div><div class="value">${item.confidence ?? "—"}</div></div></div><div class="row" style="margin-top:.65rem;"><button class="ghost" onclick="openAuthedPath('/reports/${item.id}.json')">Report JSON</button><button class="ghost" onclick="openAuthedPath('/reports/${item.id}.html')">Report HTML</button><button class="secondary" onclick="useHistoryRecordInWorkspaces(${item.id})">Use in Workspaces</button></div></div>`).join("");
        }

        function renderFidRunSelectionBadge() {
          const badge = el("fidRunSelectionBadge");
          if (!badge) return;
          const count = state.selectedFidRunIds.length;
          badge.className = `status-badge ${count >= 2 ? "ok" : "warn"}`;
          badge.textContent = `${count} selected`;
        }

        function scoreFidRun(run) {
          const qa = Number(run?.quality_score ?? run?.processing_metadata?.qa_diagnostics?.quality_score ?? 0);
          const peaks = Array.isArray(run?.preview?.inferred_peaks) ? run.preview.inferred_peaks.length : 0;
          const statusBoost = run?.review_status === "approved" ? 0.08 : 0;
          return qa + Math.min(peaks, 12) * 0.005 + statusBoost;
        }

        function getFidRunById(runId) {
          return (state.fidRuns || []).find((run) => Number(run.id) === Number(runId)) || null;
        }

        function getSelectedFidRuns() {
          return state.selectedFidRunIds.map(getFidRunById).filter(Boolean);
        }

        function getSelectedFidRunDropdownId() {
          const value = el("fidRunSelect")?.value;
          const parsed = Number(value);
          return Number.isFinite(parsed) ? parsed : null;
        }

        function openSelectedFidRunFromDropdown() {
          const runId = getSelectedFidRunDropdownId();
          if (runId !== null) openFidRun(runId);
        }

        function toggleSelectedFidRunFromDropdown() {
          const runId = getSelectedFidRunDropdownId();
          if (runId !== null) toggleFidRunSelection(runId);
        }

        function openSelectedFidRunReportFromDropdown() {
          const runId = getSelectedFidRunDropdownId();
          if (runId !== null) openAuthedPath(`/fid/runs/${runId}/report.html`);
        }

        function openSelectedFidRunPackageFromDropdown() {
          const runId = getSelectedFidRunDropdownId();
          if (runId !== null) openAuthedPath(`/fid/runs/${runId}/package`);
        }

        function renderFidRuns(items) {
          state.fidRuns = Array.isArray(items) ? items : [];
          const validIds = new Set(state.fidRuns.map((run) => Number(run.id)));
          state.selectedFidRunIds = state.selectedFidRunIds.filter((id) => validIds.has(Number(id)));
          renderFidRunSelectionBadge();
          const box = el("fidRunHistoryBox");
          if (!box) return;
          if (!state.fidRuns.length) {
            box.innerHTML = `
              <div class="panel fid-run-history-block">
                <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                  <div>
                    <strong>Saved FID processing runs</strong>
                    <div class="muted small">All recent Raw FID beta runs will appear here after processing.</div>
                  </div>
                  <span class="status-badge warn">0 runs</span>
                </div>
                <p class="muted small" style="margin:.75rem 0 0;">No saved FID runs found yet.</p>
              </div>`;
            return;
          }
          const options = state.fidRuns.map((run) => {
            const qa = run.processing_metadata?.qa_diagnostics || {};
            const peaks = Array.isArray(run.preview?.inferred_peaks) ? run.preview.inferred_peaks.length : 0;
            const label = `#${run.id} · ${run.sample_id || "Unlabeled"} · ${run.selected_preset || "preset"} · ${run.quality_label || "QA"} ${qa.quality_score ?? run.quality_score ?? "—"} · ${peaks} peaks · ${run.review_status || "pending_review"}`;
            return `<option value="${escapeHtml(run.id)}">${escapeHtml(label)}</option>`;
          }).join("");
          const latest = state.fidRuns[0];
          const latestPeaks = Array.isArray(latest?.preview?.inferred_peaks) ? latest.preview.inferred_peaks.length : 0;
          const rows = state.fidRuns.map((run) => {
            const selected = state.selectedFidRunIds.some((id) => Number(id) === Number(run.id));
            const qa = run.processing_metadata?.qa_diagnostics || {};
            const peaks = Array.isArray(run.preview?.inferred_peaks) ? run.preview.inferred_peaks.length : 0;
            const statusText = run.review_status || "pending_review";
            return `<tr class="${selected ? "selected-row" : ""}">
              <td><strong>${escapeHtml(run.sample_id || `FID run #${run.id}`)}</strong><div class="muted small">Run #${escapeHtml(run.id)} · Analysis ${escapeHtml(run.analysis_id || "—")}</div></td>
              <td>${escapeHtml(run.selected_preset || "—")}</td>
              <td>${escapeHtml(run.quality_label || "—")}<div class="muted small">Score ${escapeHtml(qa.quality_score ?? run.quality_score ?? "—")}</div></td>
              <td>${escapeHtml(peaks)}</td>
              <td><span class="status-badge ${getStatusVariant(statusText)}">${escapeHtml(statusText)}</span><div class="muted small">${escapeHtml(run.review_decision_count ?? 0)} decisions</div></td>
              <td>${escapeHtml(formatDateTime(run.created_at))}</td>
              <td><div class="row"><button class="primary" onclick="openFidRun(${run.id})" title="Open this run in the Raw FID spectrum reviewer.">Open</button><button class="${selected ? "secondary" : "ghost"}" onclick="toggleFidRunSelection(${run.id})" title="Select this run for side-by-side comparison.">${selected ? "Selected" : "Select"}</button><button class="ghost" onclick="openAuthedPath('/fid/runs/${run.id}/report.html')" title="Open the FID-derived evidence report.">Report</button><button class="ghost" onclick="openAuthedPath('/fid/runs/${run.id}/package')" title="Download the evidence package with provenance JSON and the immutable raw archive when available.">Package</button><button class="secondary" onclick="approveFidRun(${run.id})" title="Approve this FID run review status.">Approve</button><button class="danger" onclick="rejectFidRun(${run.id})" title="Reject this FID run review status.">Reject</button></div></td>
            </tr>`;
          }).join("");
          box.innerHTML = `
            <div class="panel fid-run-history-block">
              <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                <div>
                  <strong>Saved FID processing runs</strong>
                  <div class="muted small">Recent Raw FID beta runs are collapsed into this selector. Open details only when you need the full table.</div>
                </div>
                <span class="status-badge ok">${escapeHtml(state.fidRuns.length)} runs</span>
              </div>
              <div class="grid2" style="margin-top:.75rem;">
                <div class="field" style="margin-bottom:0;">
                  <label for="fidRunSelect">FID run</label>
                  <select id="fidRunSelect">${options}</select>
                </div>
                <div class="panel small" style="margin:0;">
                  Latest: #${escapeHtml(latest?.id || "—")} · ${escapeHtml(latest?.selected_preset || "—")} · ${escapeHtml(latest?.quality_label || "—")} · ${escapeHtml(latestPeaks)} peaks
                </div>
              </div>
              <div class="row" style="margin-top:.7rem;">
                <button class="primary" onclick="openSelectedFidRunFromDropdown()" title="Open the selected FID run in the spectrum reviewer.">Open selected</button>
                <button class="ghost" onclick="toggleSelectedFidRunFromDropdown()" title="Add or remove the selected FID run from comparison.">Select for compare</button>
                <button class="ghost" onclick="openSelectedFidRunReportFromDropdown()" title="Open the selected FID evidence report.">Report</button>
                <button class="ghost" onclick="openSelectedFidRunPackageFromDropdown()" title="Download the selected FID evidence package.">Package</button>
              </div>
              <details style="margin-top:.75rem;">
                <summary>Show full FID run table</summary>
                <div style="overflow:auto; margin-top:.75rem;">
                  <table>
                    <thead><tr><th>Run</th><th>Preset</th><th>QA</th><th>Peaks</th><th>Review</th><th>Created</th><th>Actions</th></tr></thead>
                    <tbody>${rows}</tbody>
                  </table>
                </div>
              </details>
            </div>`;
        }

        function toggleFidRunSelection(runId) {
          const parsed = Number(runId);
          if (!Number.isFinite(parsed)) return;
          if (state.selectedFidRunIds.some((id) => Number(id) === parsed)) {
            state.selectedFidRunIds = state.selectedFidRunIds.filter((id) => Number(id) !== parsed);
          } else {
            state.selectedFidRunIds.push(parsed);
          }
          renderFidRuns(state.fidRuns);
        }

        function renderFidRunComparison(runs) {
          const box = el("fidRunCompareBox");
          if (!box) return;
          if (!Array.isArray(runs) || runs.length < 2) {
            box.innerHTML = '<p class="muted small">Select at least two FID runs to compare.</p>';
            return;
          }
          const best = [...runs].sort((a, b) => scoreFidRun(b) - scoreFidRun(a))[0];
          box.innerHTML = `
            <div class="panel">
              <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                <strong>FID run comparison</strong>
                <span class="status-badge ok">Best run #${escapeHtml(best.id)}</span>
              </div>
              <table style="margin-top:.75rem;">
                <thead><tr><th>Run</th><th>Preset</th><th>QA</th><th>Peaks</th><th>Review</th><th>Actions</th></tr></thead>
                <tbody>${runs.map((run) => {
                  const peaks = Array.isArray(run.preview?.inferred_peaks) ? run.preview.inferred_peaks.length : 0;
                  const isBest = Number(run.id) === Number(best.id);
                  return `<tr>
                    <td>#${escapeHtml(run.id)} ${isBest ? '<span class="status-badge ok">best</span>' : ''}</td>
                    <td>${escapeHtml(run.selected_preset || "—")}</td>
                    <td>${escapeHtml(run.quality_label || "—")} (${escapeHtml(run.quality_score ?? "—")})</td>
                    <td>${escapeHtml(peaks)}</td>
                    <td><span class="status-badge ${getStatusVariant(run.review_status)}">${escapeHtml(run.review_status || "pending_review")}</span></td>
                    <td><button class="ghost" onclick="openFidRun(${run.id})">Open</button><button class="ghost" onclick="openAuthedPath('/fid/runs/${run.id}/report.html')">Report</button><button class="ghost" onclick="openAuthedPath('/fid/runs/${run.id}/package')">Package</button></td>
                  </tr>`;
                }).join("")}</tbody>
              </table>
            </div>`;
        }

        function renderReviewQueue(items) {
          if (!Array.isArray(items) || !items.length) { el("reviewQueue").innerHTML = '<p class="muted">No review items found.</p>'; return; }
          el("reviewQueue").innerHTML = items.map((item) => {
            const analysis = item.analysis || item;
            const analysisId = analysis.id || item.analysis_id;
            const statusText = analysis.review_status || analysis.label || item.recommended_action || "pending_review";
            return `<div class="record-card"><div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;"><strong>${escapeHtml(analysis.sample_id || `Analysis #${analysisId ?? "?"}`)}</strong><span class="status-badge ${getStatusVariant(statusText)}">${escapeHtml(statusText)}</span></div><div class="muted small">System label: ${escapeHtml(analysis.label || "—")} · Confidence: ${escapeHtml(analysis.confidence ?? "—")}</div><div class="row" style="margin-top:.65rem;"><button class="secondary" onclick="approveReview(${analysisId})">Approve</button><button class="danger" onclick="rejectReview(${analysisId})">Reject</button><button class="ghost" onclick="overrideReview(${analysisId})">Override</button><button class="ghost" onclick="loadReviewDecisions(${analysisId})">Decisions</button><button class="ghost" onclick="loadEvidenceReportJson(${analysisId})">Open report</button></div></div>`;
          }).join("");
        }

        function renderAdminUsers(items) {
          if (!Array.isArray(items) || !items.length) { el("adminUsers").innerHTML = '<p class="muted">No users found.</p>'; return; }
          el("adminUsers").innerHTML = `<table><thead><tr><th>Email</th><th>Verified</th><th>Admin</th><th>Actions</th></tr></thead><tbody>${items.map((user) => `<tr><td>${escapeHtml(user.email || "—")}</td><td>${user.is_verified ? "Yes" : "No"}</td><td>${user.is_admin ? "Yes" : "No"}</td><td><button class="secondary" onclick="promoteUser(${user.id})">Promote</button><button class="ghost" onclick="demoteUser(${user.id})">Demote</button></td></tr>`).join("")}</tbody></table>`;
        }

        function renderAudit(items) {
          if (!Array.isArray(items) || !items.length) { el("auditPreview").innerHTML = '<p class="muted">No audit events loaded.</p>'; return; }
          el("auditPreview").innerHTML = items.slice(0, 15).map((event) => `<div class="record-card"><strong>${escapeHtml(event.event_type || "event")}</strong><div class="muted small">${escapeHtml(event.created_at || "—")}</div><div class="muted small">${escapeHtml(event.summary || event.detail || "")}</div></div>`).join("");
        }

        function selectWorkspaceProject(projectId) {
          state.selectedProjectId = projectId;
          updateWorkspaceSelectionBox();
          renderProjects(state.workspaceProjects);
        }

        function openWorkspaceProject(projectId) {
          state.selectedProjectId = projectId;
          updateWorkspaceSelectionBox();
          renderProjects(state.workspaceProjects);
          loadProjectSamples(projectId).catch(() => null);
          showSection("workspaces");
        }

        function prepareNewWorkspaceSample(projectId) {
          state.selectedProjectId = projectId;
          state.workspaceSeedAnalysisId = null;
          state.workspaceSeedSnapshot = null;
          updateWorkspaceSelectionBox();
          renderProjects(state.workspaceProjects);
          if (el("workspaceSeedNote")) {
            el("workspaceSeedNote").textContent = "Project selected for a new sample. Review the current analysis inputs, then create the sample here.";
          }
          loadProjectSamples(projectId).catch(() => null);
          showSection("workspaces");
        }

        function loadSelectedProjectSamples() {
          if (!state.selectedProjectId) {
            setJson({ error: "Select a project first." });
            renderWorkspaceStatusBadge("Select a project first", "bad");
            return;
          }
          loadProjectSamples(state.selectedProjectId).catch(() => null);
        }

        async function loadReviewerTimelineForAnalysis(analysisId, { fallbackReport = null } = {}) {
          const parsed = Number(analysisId);
          if (!Number.isFinite(parsed) || parsed <= 0) {
            renderReviewerTimeline(null, [], []);
            return { decisions: [], auditEvents: [] };
          }
          const fallbackDecisions = Array.isArray(fallbackReport?.review_decisions) ? fallbackReport.review_decisions : [];
          const fallbackAuditEvents = Array.isArray(fallbackReport?.audit_events) ? fallbackReport.audit_events : [];
          const [decisionsResult, auditResult] = await Promise.allSettled([
            api(`/reviews/${parsed}/decisions`),
            api(`/audit?entity_type=analysis&entity_id=${encodeURIComponent(parsed)}&limit=200`),
          ]);
          const decisions = decisionsResult.status === "fulfilled" ? decisionsResult.value : fallbackDecisions;
          const auditEvents = auditResult.status === "fulfilled" ? auditResult.value : fallbackAuditEvents;
          const errors = [decisionsResult, auditResult]
            .filter((result) => result.status === "rejected")
            .map((result) => result.reason?.message || String(result.reason));
          state.workspaceTimeline = { analysisId: parsed, decisions, auditEvents };
          renderReviewerTimeline(parsed, decisions, auditEvents, errors.join(" "));
          return state.workspaceTimeline;
        }

        async function openWorkspaceSampleDetail(sampleRecordId) {
          let sample = getWorkspaceSampleById(sampleRecordId);
          if (!sample) {
            setJson({ error: "Sample is not loaded in the current workspace." });
            return;
          }
          try {
            const detail = await api(`/samples/${encodeURIComponent(sampleRecordId)}`);
            state.workspaceSampleDetail = detail;
            sample = detail.sample || sample;
            setJson(detail);
          } catch (err) {
            setJson({ error: String(err.message || err) });
          }
          state.selectedWorkspaceSampleId = sample.id;
          state.selectedWorkspaceSample = sample;
          state.workspaceSampleReport = null;
          setReportAnalysisInputValue(sample.analysis_id || "", { overwrite: false });
          renderWorkspaceSamples(state.workspaceSamples);
          renderWorkspaceSampleDetail(sample);
          renderSampleAnalysisComparison(sample);
          showSection("workspaces");
          if (sample.analysis_id) {
            setLatestAnalysisId(sample.analysis_id);
            const report = await loadEvidenceReportForSample(sample.analysis_id).catch(() => null);
            await inspectSampleReviewerTimeline(sample.id).catch(() => null);
            await compareWorkspaceSampleAnalyses(sample.id).catch(() => null);
          } else {
            renderReviewerTimeline(null, [], []);
            await compareWorkspaceSampleAnalyses(sample.id).catch(() => null);
          }
        }

        async function loadEvidenceReportForSample(analysisId) {
          const data = await api(`/reports/${analysisId}.json`);
          state.workspaceSampleReport = data;
          const sample = state.selectedWorkspaceSample;
          if (sample && Number(sample.analysis_id) === Number(analysisId)) {
            renderWorkspaceSampleDetail(sample, data);
            renderSampleAnalysisComparison(sample);
          }
          return data;
        }

        async function compareWorkspaceSampleAnalyses(sampleRecordId=null) {
          const sample = sampleRecordId ? getWorkspaceSampleById(sampleRecordId) : state.selectedWorkspaceSample;
          if (!sample) {
            setJson({ error: "Open a sample before comparing analyses." });
            return;
          }
          state.selectedWorkspaceSampleId = sample.id;
          state.selectedWorkspaceSample = sample;
          try {
            const comparison = await api(`/samples/${encodeURIComponent(sample.id)}/compare`);
            state.workspaceSampleComparison = comparison;
            setJson(comparison);
          } catch (err) {
            state.workspaceSampleComparison = null;
            if (!state.historyItems.length) await loadHistory().catch(() => []);
            setJson({ error: String(err.message || err) });
          }
          renderWorkspaceSamples(state.workspaceSamples);
          renderWorkspaceSampleDetail(sample, state.workspaceSampleReport);
          renderSampleAnalysisComparison(sample);
          showSection("workspaces");
        }

        async function loadSampleLatestReport(sampleRecordId) {
          const sample = getWorkspaceSampleById(sampleRecordId);
          if (!sample || !sample.analysis_id) {
            setJson({ error: "This sample does not have a linked analysis." });
            return null;
          }
          state.selectedWorkspaceSampleId = sample.id;
          state.selectedWorkspaceSample = sample;
          setReportAnalysisInputValue(sample.analysis_id);
          setLatestAnalysisId(sample.analysis_id);
          const report = await loadEvidenceReportJson(sample.analysis_id);
          state.workspaceSampleReport = report;
          renderWorkspaceSampleDetail(sample, report);
          renderSampleAnalysisComparison(sample);
          return report;
        }

        async function inspectSampleReviewerTimeline(sampleRecordId) {
          const sample = getWorkspaceSampleById(sampleRecordId);
          if (!sample || !sample.analysis_id) {
            setJson({ error: "This sample does not have a linked analysis timeline." });
            return null;
          }
          state.selectedWorkspaceSampleId = sample.id;
          state.selectedWorkspaceSample = sample;
          setLatestAnalysisId(sample.analysis_id);
          setReportAnalysisInputValue(sample.analysis_id);
          let timeline = null;
          try {
            timeline = await api(`/samples/${encodeURIComponent(sample.id)}/timeline`);
            state.workspaceTimeline = {
              analysisId: sample.analysis_id,
              decisions: timeline.review_decisions || [],
              auditEvents: timeline.audit_events || [],
            };
            renderReviewerTimeline(sample.analysis_id, timeline.review_decisions || [], timeline.audit_events || []);
            setJson(timeline);
          } catch (err) {
            timeline = await loadReviewerTimelineForAnalysis(sample.analysis_id, { fallbackReport: state.workspaceSampleReport });
          }
          showSection("workspaces");
          return timeline;
        }

        function useHistoryRecordInWorkspaces(analysisId) {
          const record = (state.historyItems || []).find((item) => Number(item.id) === Number(analysisId));
          if (!record) {
            setJson({ error: "That history record is no longer loaded." });
            return;
          }
          if (el("sampleId")) el("sampleId").value = record.sample_id || "";
          if (el("smiles")) el("smiles").value = record.smiles || "";
          if (el("nmrText")) el("nmrText").value = record.nmr_text || "";
          if (el("solvent")) el("solvent").value = record.solvent || "";
          setReportAnalysisInputValue(record.id || "");
          state.workspaceSeedAnalysisId = record.id || null;
          state.workspaceSeedSnapshot = buildWorkspaceSeedSnapshot(record);
          setLatestAnalysisId(record.id);
          if (el("workspaceSeedNote")) el("workspaceSeedNote").textContent = `History #${record.id} is now loaded into the current analysis inputs and ready to save into the selected project.`;
          clearValidationState();
          showSection("workspaces");
        }

        async function createWorkspaceProject() {
          try {
            const name = (el("workspaceProjectName")?.value || "").trim();
            const description = (el("workspaceProjectDescription")?.value || "").trim();
            if (!name) throw new Error("Enter a project name first.");
            const data = await api("/workspaces/projects", {
              method: "POST",
              body: JSON.stringify({ name, description: description || null }),
            });
            setJson(data);
            if (el("workspaceProjectName")) el("workspaceProjectName").value = "";
            if (el("workspaceProjectDescription")) el("workspaceProjectDescription").value = "";
            await loadProjects();
            if (data && data.id) {
              state.selectedProjectId = data.id;
              renderProjects(state.workspaceProjects);
            }
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("workspaceProjectsBox")) el("workspaceProjectsBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        async function loadProjects() {
          try {
            const data = await api("/workspaces/projects");
            setJson(data);
            renderProjects(Array.isArray(data) ? data : []);
            return data;
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("workspaceProjectsBox")) el("workspaceProjectsBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
            return [];
          }
        }

        async function loadProjectSamples(projectId) {
          try {
            const data = await api(`/workspaces/projects/${projectId}/samples`);
            setJson(data);
            state.selectedProjectId = projectId;
            updateWorkspaceSelectionBox();
            renderProjects(state.workspaceProjects);
            renderWorkspaceSamples(Array.isArray(data) ? data : []);
            loadProjectDashboard(projectId).catch(() => null);
            return data;
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("workspaceSamplesBox")) el("workspaceSamplesBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
            throw err;
          }
        }

        async function loadProjectDashboard(projectId) {
          try {
            const data = await api(`/projects/${projectId}/dashboard`);
            state.workspaceProjectDashboard = data;
            renderWorkspaceProjectDashboard();
            return data;
          } catch (err) {
            state.workspaceProjectDashboard = null;
            renderWorkspaceProjectDashboard();
            throw err;
          }
        }

        async function linkWorkspaceSampleToLatestAnalysis(projectId, sampleRecordId) {
          try {
            const analysisId = getLatestAvailableAnalysisId();
            if (!analysisId) throw new Error("Load history or a report first so Workspaces knows the latest analysis ID.");
            const data = await api(`/workspaces/projects/${projectId}/samples/${sampleRecordId}/link-analysis`, {
              method: "POST",
              body: JSON.stringify({ analysis_id: analysisId }),
            });
            setLatestAnalysisId(analysisId);
            setJson(data);
            if (el("workspaceSeedNote")) el("workspaceSeedNote").textContent = `Linked sample #${sampleRecordId} to Analysis #${analysisId}.`;
            await loadProjectSamples(projectId);
            await loadProjects();
            loadEvidenceReportJson(analysisId).catch(() => null);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("workspaceSamplesBox")) el("workspaceSamplesBox").insertAdjacentHTML("afterbegin", `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`);
          }
        }

        async function createWorkspaceSampleFromCurrentInputs() {
          try {
            if (!state.selectedProjectId) throw new Error("Select a project before creating a sample.");
            const current = getCurrentAnalysisInputsForWorkspace();
            if (!current.smiles) throw new Error("Enter or load a SMILES value before creating a sample.");
            if (!current.nmr_text) throw new Error("Enter or load ¹H NMR text before creating a sample.");
            const analysisId = getLinkedWorkspaceAnalysisId();
            const body = {
              sample_id: current.sample_id,
              smiles: current.smiles,
              solvent: current.solvent,
              nmr_text: current.nmr_text,
              analysis_id: analysisId,
            };
            const data = await api(`/workspaces/projects/${state.selectedProjectId}/samples`, {
              method: "POST",
              body: JSON.stringify(body),
            });
            setJson(data);
            if (data && data.analysis_id) setLatestAnalysisId(data.analysis_id);
            if (el("workspaceSeedNote")) {
              el("workspaceSeedNote").textContent = analysisId
                ? `Saved the current analysis inputs into the selected project and linked Analysis #${analysisId}.`
                : "Saved the current analysis inputs into the selected project.";
            }
            await loadProjects();
            await loadProjectSamples(state.selectedProjectId);
            showSection("workspaces");
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("workspaceSamplesBox")) el("workspaceSamplesBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        async function loadEvidenceReportJson(analysisIdOverride=null) {
          try {
            const analysisId = analysisIdOverride || getReportAnalysisInputValue();
            if (!analysisId) throw new Error("Enter an analysis ID first.");
            const data = await api(`/reports/${analysisId}.json`);
            setReportAnalysisInputValue(analysisId);
            setLatestAnalysisId(analysisId);
            setJson(data);
            renderEvidenceReport(data);
            await loadReviewerTimelineForAnalysis(analysisId, { fallbackReport: data });
            showSection("workspaces");
            return data;
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("workspaceReportBox")) el("workspaceReportBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
            return null;
          }
        }

        async function useLatestAnalysisReport() {
          try {
            let analysisId = getLatestAvailableAnalysisId();
            if (!analysisId) {
              const items = await loadHistory();
              analysisId = Array.isArray(items) && items.length ? setLatestAnalysisId(items[0].id) : null;
            }
            if (!analysisId) throw new Error("No analysis history is available yet.");
            setReportAnalysisInputValue(analysisId);
            return loadEvidenceReportJson(analysisId);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("workspaceReportBox")) el("workspaceReportBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
            return null;
          }
        }

        async function generateReportFromCurrentLatestAnalysis() {
          try {
            let analysisId = getReportAnalysisIdOrLatest();
            if (!analysisId) {
              const items = await loadHistory();
              analysisId = Array.isArray(items) && items.length ? setLatestAnalysisId(items[0].id) : null;
            }
            if (!analysisId) throw new Error("No current or latest analysis is available yet.");
            setReportAnalysisInputValue(analysisId);
            const stored = await api(`/reports/from-analysis/${analysisId}`, { method: "POST", body: JSON.stringify({}) });
            setJson(stored);
            if (stored?.report) {
              renderEvidenceReport(stored.report);
              await loadReviewerTimelineForAnalysis(analysisId, { fallbackReport: stored.report });
              if (el("workspaceReportBox")) {
                el("workspaceReportBox").insertAdjacentHTML(
                  "afterbegin",
                  `<div class="panel" style="margin-bottom:.85rem;"><strong>Versioned report #${escapeHtml(stored.id)}</strong><div class="small muted">Snapshot v${escapeHtml(stored.version)} generated from Analysis #${escapeHtml(stored.analysis_id)}.</div><div class="row" style="margin-top:.55rem;"><button class="ghost" onclick="openAuthedPath('/reports/${stored.id}')">Open stored JSON</button><button class="ghost" onclick="openAuthedPath('/reports/${stored.id}.html')">Open stored HTML</button></div></div>`
                );
              }
            }
            return stored;
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("workspaceReportBox")) el("workspaceReportBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
            return null;
          }
        }

        function openEvidenceReportHtml(analysisIdOverride=null) {
          const analysisId = analysisIdOverride || getReportAnalysisInputValue();
          if (!analysisId) {
            setJson({ error: "Enter an analysis ID first." });
            return;
          }
          setReportAnalysisInputValue(analysisId);
          setLatestAnalysisId(analysisId);
          openAuthedPath(`/reports/${analysisId}.html`);
        }

        function readAuthCredentials() {
          const email = (el("authEmail")?.value || "").trim();
          const password = el("authPassword")?.value || "";
          return { email, password };
        }

        function validateAuthCredentials(email, password) {
          if (!email) throw new Error("Enter your email address.");
          if (!/^\S+@\S+\.\S+$/.test(email)) throw new Error("Enter a valid email address.");
          if (!password) throw new Error("Enter your password.");
          if (password.length < 8) throw new Error("Password must be at least 8 characters.");
        }

        async function registerUser() {
          try {
            const { email, password } = readAuthCredentials();
            validateAuthCredentials(email, password);
            const data = await api("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) }, false);
            setAuthMessage("Registration succeeded. Logging you in now…", true);
            setJson(data);
            await login();
          } catch (err) {
            setAuthMessage(String(err.message || err), false);
            setJson({ error: String(err.message || err) });
          }
        }

        async function login() {
          try {
            const { email, password } = readAuthCredentials();
            validateAuthCredentials(email, password);
            const data = await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }, false);
            const token = data.access_token || data.token || data.bearer_token || "";
            if (!token) throw new Error("Login succeeded but no token was returned.");
            persistToken(token);
            showAppShell();
            setAuthMessage("Logged in successfully.", true);
            setJson(data);
            await whoAmI();
            loadMetrics().catch(() => null);
            loadProjects().catch(() => null);
            loadJobs().catch(() => null);
            loadHistory().catch(() => null);
            loadFidRuns().catch(() => null);
          } catch (err) {
            clearUserSessionState({ resetInputs: true });
            persistToken("");
            showAuthScreen();
            setAuthMessage(String(err.message || err), false);
            setJson({ error: String(err.message || err) });
          }
        }

        async function logout() {
          try { if (state.token) await api("/auth/logout", { method: "POST", body: JSON.stringify({}) }); } catch (_) {}
          clearUserSessionState({ resetInputs: true });
          persistToken("");
          showAuthScreen();
          updateRoleUI();
          setJson({ detail: "Logged out." });
        }

        async function whoAmI() {
          try {
            const data = await api("/auth/me");
            state.me = data;
            updateRoleUI();
            setJson(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
          }
        }

        async function copyToken() {
          try {
            if (!state.token) throw new Error("No token to copy.");
            await navigator.clipboard.writeText(state.token);
            setJson({ detail: "Token copied to clipboard." });
          } catch (err) {
            setJson({ error: String(err.message || err) });
          }
        }

        async function requestVerification() {
          try {
            const email = (state.me && state.me.email) || el("authEmail").value.trim();
            if (!email) throw new Error("Enter or load an email address before requesting verification.");
            const data = await api("/auth/request-email-verification", {
              method: "POST",
              body: JSON.stringify({ email }),
            });
            const token = extractActionToken(data.token || data.verification_link || "");
            if (token) persistVerificationToken(token);
            setJson(data);
            setAuthMessage("Verification token requested. Copy the preview token or paste the full link into the verify box.", true);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            setAuthMessage(String(err.message || err), false);
          }
        }

        async function copyVerificationToken() {
          try {
            const token = extractActionToken(el("verifyToken").value || state.verificationToken);
            if (!token) throw new Error("No verification token is available yet.");
            await navigator.clipboard.writeText(token);
            setJson({ detail: "Verification token copied to clipboard." });
          } catch (err) {
            setJson({ error: String(err.message || err) });
          }
        }

        async function verifyEmail() {
          try {
            const token = extractActionToken(el("verifyToken").value || state.verificationToken);
            if (!token) throw new Error("Paste a verification token or full verification link first.");
            const data = await api(`/auth/verify-email?token=${encodeURIComponent(token)}`, { method: "GET" }, false);
            persistVerificationToken("");
            el("verifyToken").value = "";
            setJson(data);
            setAuthMessage("Email verified successfully.", true);
            await whoAmI();
          } catch (err) {
            setJson({ error: String(err.message || err) });
            setAuthMessage(String(err.message || err), false);
          }
        }

        async function requestPasswordReset() {
          try {
            const email = el("resetEmail").value.trim() || el("authEmail").value.trim();
            const data = await api("/auth/request-password-reset", { method: "POST", body: JSON.stringify({ email }) }, false);
            setJson(data);
            setAuthMessage("Password reset token requested.", true);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            setAuthMessage(String(err.message || err), false);
          }
        }

        async function resetPassword() {
          try {
            const data = await api("/auth/reset-password", { method: "POST", body: JSON.stringify({ token: el("resetToken").value.trim(), new_password: el("resetPassword").value }) }, false);
            setJson(data);
            setAuthMessage("Password reset completed. Log in with the new password.", true);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            setAuthMessage(String(err.message || err), false);
          }
        }

        async function loadOutbox() {
          try {
            const data = await api("/auth/outbox");
            setJson(data);
            if (Array.isArray(data) && data.length) {
              const verification = data.find((item) => item.purpose === "verify_email") || data[0];
              const token = extractActionToken(verification.body || verification.token || "");
              if (token) persistVerificationToken(token);
              setAuthMessage("Latest outbox message loaded. Verification tokens can be copied from the preview box.", true);
            }
          } catch (err) {
            setJson({ error: String(err.message || err) });
          }
        }


        function findSpectrumPeakIntensity(points, shift) {
          if (!Array.isArray(points) || !points.length) return null;
          let best = points[0];
          let bestDelta = Math.abs(Number(points[0].shift_ppm) - Number(shift));
          for (const point of points) {
            const delta = Math.abs(Number(point.shift_ppm) - Number(shift));
            if (delta < bestDelta) {
              best = point;
              bestDelta = delta;
            }
          }
          return Number(best.intensity);
        }

        function findSpectrumPeakByShift(peaks, shift) {
          if (!Array.isArray(peaks) || !peaks.length) return null;
          let best = peaks[0];
          let bestDelta = Math.abs(Number(peaks[0].shift_ppm) - Number(shift));
          for (const peak of peaks) {
            const delta = Math.abs(Number(peak.shift_ppm) - Number(shift));
            if (delta < bestDelta) {
              best = peak;
              bestDelta = delta;
            }
          }
          return bestDelta <= 0.08 ? best : null;
        }

        function clampSpectrumVerticalScale(value) {
          if (!Number.isFinite(value) || value <= 1) return 1;
          return Math.min(value, 1e6);
        }

        function formatSpectrumVerticalScaleLabel(value) {
          const scale = clampSpectrumVerticalScale(Number(value) || 1);
          if (scale >= 1e5) return `${scale.toExponential(1).replace('+', '')}×`;
          if (scale >= 1e3) return `${Math.round(scale).toLocaleString()}×`;
          if (scale >= 10) return `${scale.toFixed(1).replace(/\.0$/, '')}×`;
          return `${scale.toFixed(1)}×`;
        }

        function getSpectrumVerticalMeterFillPercent() {
          const scale = clampSpectrumVerticalScale(Number(state.spectrumVerticalScale || 1));
          const fraction = Math.log2(scale) / 12;
          return Math.max(0.12, Math.min(1, fraction + 0.12));
        }

        function normalizeSpectrumPlotId(plotId=null) {
          return String(plotId || state.latestSpectrumPlotId || "spectrumInteractivePlot");
        }

        function setActiveSpectrumPlot(plotId=null) {
          const activeId = normalizeSpectrumPlotId(plotId);
          state.latestSpectrumPlotId = activeId;
          const context = state.spectrumPreviewContexts?.[activeId] || null;
          if (context?.data) state.latestSpectrumPreview = context.data;
          return activeId;
        }

        function getSpectrumContext(plotId=null) {
          const activeId = setActiveSpectrumPlot(plotId);
          return state.spectrumPreviewContexts?.[activeId] || {
            data: state.latestSpectrumPreview,
            options: { plotId: activeId, targetId: activeId === "spectrumInteractivePlot" ? "spectrumPreviewBox" : null },
          };
        }

        function rerenderSpectrumPreview(plotId=null) {
          const context = getSpectrumContext(plotId);
          const activeId = normalizeSpectrumPlotId(plotId);
          const plotTarget = el(activeId);
          if (context?.data && plotTarget && plotTarget.dataset.plotReady === 'true') {
            renderInteractiveSpectrumPlot(context.data, activeId);
            renderSpectrumGainControl(activeId);
            refreshSpectrumToolbarState(activeId, context.data);
            refreshSpectrumReviewUi(activeId);
            return;
          }
          if (context?.data) renderSpectrumPreview(context.data, context.options || {});
        }

        function renderSpectrumGainControl(plotId=null) {
          const activeId = normalizeSpectrumPlotId(plotId);
          const valueNode = el(`${activeId}ScaleValue`) || el('spectrumScaleValue');
          if (valueNode) valueNode.textContent = formatSpectrumVerticalScaleLabel(state.spectrumVerticalScale);
          const sliderNode = el(`${activeId}GainSlider`);
          if (sliderNode) sliderNode.value = String(Math.min(512, Math.max(1, Number(state.spectrumVerticalScale || 1))));
          const fillNode = el(`${activeId}ScaleFill`) || el('spectrumScaleFill');
          if (fillNode) fillNode.style.height = `${Math.round(getSpectrumVerticalMeterFillPercent() * 100)}%`;
        }

        function setSpectrumButtonState(id, active, label=null) {
          const node = el(id);
          if (!node) return;
          node.className = active ? "secondary" : "ghost";
          if (label !== null) node.textContent = label;
        }

        function refreshSpectrumToolbarState(plotId=null, data=null) {
          const activeId = normalizeSpectrumPlotId(plotId);
          const context = getSpectrumContext(activeId);
          const previewData = data || context?.data || null;
          const traceMode = previewData ? getSpectrumTraceMode(previewData, activeId) : state.spectrumTraceMode;
          setSpectrumButtonState(`${activeId}PanButton`, state.spectrumDragMode === 'pan');
          setSpectrumButtonState(`${activeId}ZoomButton`, state.spectrumDragMode === 'zoom');
          setSpectrumButtonState(`${activeId}TallPeakClipButton`, Boolean(state.spectrumTallPeakClip));
          setSpectrumButtonState(`${activeId}WeakPeakMagnifierButton`, Boolean(state.spectrumWeakPeakMagnifier));
          setSpectrumButtonState(`${activeId}ZeroLineButton`, Boolean(state.spectrumZeroLine));
          setSpectrumButtonState(
            `${activeId}PeaksButton`,
            !state.spectrumShowPeaks,
            state.spectrumShowPeaks ? 'Hide peaks' : 'Show peaks',
          );
          setSpectrumButtonState(`${activeId}RealViewButton`, traceMode === 'review');
          setSpectrumButtonState(`${activeId}OriginalViewButton`, traceMode === 'original');
        }

        function refreshSpectrumReviewUi(plotId=null) {
          const context = getSpectrumContext(plotId);
          const data = context?.data;
          const activeId = normalizeSpectrumPlotId(plotId);
          if (!data) return;
          const panel = el(`${activeId}ReviewerPanel`);
          if (panel) panel.innerHTML = renderSpectrumReviewerPanel(data, activeId);
          const peakList = el(`${activeId}ReviewedPeakList`);
          if (peakList) peakList.textContent = getSpectrumReviewedNmrText(data) || 'No peak list generated yet.';
        }

        function getSpectrumPlotTarget(plotId=null) {
          const activeId = setActiveSpectrumPlot(plotId);
          return el(activeId) || el("spectrumInteractivePlot");
        }

        function relayoutSpectrumPlot(update, plotId=null) {
          const plotTarget = getSpectrumPlotTarget(plotId);
          if (!plotTarget || !window.Plotly) return;
          window.Plotly.relayout(plotTarget, update);
        }

        function getSpectrumVerticalScaleFactor(scale) {
          if (scale < 8) return 1.35;
          if (scale < 64) return 1.18;
          return 1.12;
        }

        function percentileFromSorted(sortedValues, percentile) {
          if (!Array.isArray(sortedValues) || !sortedValues.length) return 0;
          const p = Math.max(0, Math.min(100, Number(percentile) || 0));
          const rank = (sortedValues.length - 1) * p / 100;
          const lower = Math.floor(rank);
          const upper = Math.ceil(rank);
          if (lower === upper) return sortedValues[lower];
          const fraction = rank - lower;
          return sortedValues[lower] * (1 - fraction) + sortedValues[upper] * fraction;
        }

        function getSpectrumBaselineAnchorFraction(data=null) {
          const nucleus = String(data?.metadata?.nucleus || data?.nucleus || "").toUpperCase();
          return nucleus === "13C" ? 0.10 : 0.08;
        }

        function shouldEqualizeSpectrumBaseline(data=null, usingOriginalState=false) {
          if (usingOriginalState) return false;
          const nucleus = String(data?.metadata?.nucleus || data?.nucleus || "1H").toUpperCase();
          return state.spectrumZeroLine && ["", "1H", "H1", "PROTON"].includes(nucleus);
        }

        function interpolateSpectrumBaseline(anchors, x) {
          if (!Array.isArray(anchors) || !anchors.length) return 0;
          if (x <= anchors[0].x) return anchors[0].y;
          if (x >= anchors[anchors.length - 1].x) return anchors[anchors.length - 1].y;
          let low = 0;
          let high = anchors.length - 1;
          while (high - low > 1) {
            const mid = Math.floor((low + high) / 2);
            if (anchors[mid].x <= x) low = mid;
            else high = mid;
          }
          const left = anchors[low];
          const right = anchors[high];
          const span = Math.max(Math.abs(right.x - left.x), 1e-12);
          const fraction = (x - left.x) / span;
          return left.y * (1 - fraction) + right.y * fraction;
        }

        function smoothSpectrumBaselineAnchors(anchors) {
          if (!Array.isArray(anchors) || anchors.length < 3) return anchors || [];
          return anchors.map((anchor, idx) => {
            if (idx === 0 || idx === anchors.length - 1) return anchor;
            const localY = [anchors[idx - 1].y, anchor.y, anchors[idx + 1].y].sort((a, b) => a - b);
            return { x: anchor.x, y: localY[1] };
          });
        }

        function getSpectrumBaselineEqualizedDisplay(points, data=null, { usingOriginalState=false } = {}) {
          const rawY = Array.isArray(points)
            ? points.map((p) => Number(p.intensity))
            : [];
          if (!shouldEqualizeSpectrumBaseline(data, usingOriginalState)) {
            return { y: rawY, points, applied: false, baseline: rawY.map(() => 0) };
          }
          const clean = (Array.isArray(points) ? points : [])
            .map((point, idx) => ({
              idx,
              x: Number(point.shift_ppm),
              y: Number(point.intensity),
            }))
            .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
          if (clean.length < 16) {
            return { y: rawY, points, applied: false, baseline: rawY.map(() => 0) };
          }
          const ordered = [...clean].sort((a, b) => a.x - b.x);
          const bins = Math.max(16, Math.min(96, Math.round(Math.sqrt(ordered.length) * 2)));
          const anchors = [];
          for (let idx = 0; idx < bins; idx += 1) {
            const start = Math.floor(idx * ordered.length / bins);
            const end = Math.floor((idx + 1) * ordered.length / bins);
            const bucket = ordered.slice(start, Math.max(start + 1, end));
            if (!bucket.length) continue;
            const ys = bucket.map((point) => point.y).sort((a, b) => a - b);
            anchors.push({
              x: bucket[Math.floor(bucket.length / 2)].x,
              y: percentileFromSorted(ys, 35),
            });
          }
          if (anchors.length < 4) {
            return { y: rawY, points, applied: false, baseline: rawY.map(() => 0) };
          }
          let smoothed = anchors;
          for (let pass = 0; pass < 3; pass += 1) {
            smoothed = smoothSpectrumBaselineAnchors(smoothed);
          }
          const baselineByIndex = rawY.map(() => 0);
          clean.forEach((point) => {
            baselineByIndex[point.idx] = interpolateSpectrumBaseline(smoothed, point.x);
          });
          let corrected = rawY.map((value, idx) => (
            Number.isFinite(value) ? value - baselineByIndex[idx] : value
          ));
          const finiteCorrected = corrected.filter((value) => Number.isFinite(value));
          if (finiteCorrected.length) {
            const sortedAbs = finiteCorrected.map((value) => Math.abs(value)).sort((a, b) => a - b);
            const baselineBand = Math.max(percentileFromSorted(sortedAbs, 35), 1e-12);
            const nearBaseline = finiteCorrected
              .filter((value) => Math.abs(value) <= baselineBand)
              .sort((a, b) => a - b);
            const residual = nearBaseline.length ? percentileFromSorted(nearBaseline, 50) : 0;
            corrected = corrected.map((value) => Number.isFinite(value) ? value - residual : value);
          }
          const displayPoints = (Array.isArray(points) ? points : []).map((point, idx) => ({
            ...point,
            intensity: corrected[idx],
            raw_intensity: rawY[idx],
          }));
          return {
            y: corrected,
            points: displayPoints,
            applied: true,
            baseline: baselineByIndex,
          };
        }

        function getSpectrumVerticalAxisRange(values, scale, baseline=0, { clipTallPeaks=false, baselineAnchorFraction=0.08 } = {}) {
          const finite = Array.isArray(values) ? values.filter((value) => Number.isFinite(value)) : [];
          if (!finite.length) return null;
          const sorted = [...finite].sort((a, b) => a - b);
          const rawMin = sorted[0];
          const rawMax = sorted[sorted.length - 1];
          const yMin = clipTallPeaks ? Math.min(rawMin, percentileFromSorted(sorted, 1)) : rawMin;
          const yMax = clipTallPeaks ? Math.max(percentileFromSorted(sorted, 96), 0) : rawMax;
          const span = yMax - yMin;
          if (!Number.isFinite(span) || span <= 0) return null;
          const base = Number(baseline);
          if (Number.isFinite(base)) {
            const positiveSpan = Math.max(yMax - base, percentileFromSorted(sorted, 99) - base, 1e-9);
            const verticalScale = clampSpectrumVerticalScale(Number(scale) || 1);
            const anchor = Math.max(0.04, Math.min(0.18, Number(baselineAnchorFraction) || 0.08));
            const upperSpan = Math.max(positiveSpan * 1.08 / verticalScale, positiveSpan * 0.002, 1e-9);
            const lowerSpan = Math.max(upperSpan * anchor / Math.max(1e-6, 1 - anchor), 1e-9);
            const lower = base - lowerSpan;
            const upper = base + upperSpan;
            return [lower, upper];
          }
          const margin = Math.max(span * 0.04, 1e-9);
          return [yMin - margin, yMax + margin];
        }

        function getSpectrumDisplayBaseline(values) {
          const finite = Array.isArray(values) ? values.filter((value) => Number.isFinite(value)).sort((a, b) => a - b) : [];
          if (!finite.length) return 0;
          const index = Math.max(0, Math.min(finite.length - 1, Math.floor(finite.length * 0.5)));
          return finite[index];
        }

        function getSpectrumPlotPoints(data, plotId=null) {
          const originalState = getOriginalSpectrumState(data);
          const traceMode = getSpectrumTraceMode(data, plotId);
          const pts = traceMode === "original" && originalState
            ? originalState.preview_points
            : (Array.isArray(data?.preview_points) ? data.preview_points : []);
          return {
            points: pts,
            usingOriginalState: traceMode === "original" && Boolean(originalState),
          };
        }

        function getSpectrumEvidenceYValues(data, plotId=null) {
          const { points: pts } = getSpectrumPlotPoints(data, plotId);
          return pts.map((p) => Number(p.intensity)).filter((value) => Number.isFinite(value));
        }

        function getSpectrumDisplayYValues(data, plotId=null) {
          const { points: pts, usingOriginalState } = getSpectrumPlotPoints(data, plotId);
          const display = getSpectrumBaselineEqualizedDisplay(pts, data, { usingOriginalState });
          return display.y.filter((value) => Number.isFinite(value));
        }

        function getSpectrumYAxisUpdate(data, plotId=null) {
          const values = getSpectrumDisplayYValues(data, plotId);
          const range = getSpectrumVerticalAxisRange(
            values,
            state.spectrumVerticalScale,
            state.spectrumZeroLine ? 0 : getSpectrumDisplayBaseline(values),
            {
              clipTallPeaks: state.spectrumTallPeakClip,
              baselineAnchorFraction: getSpectrumBaselineAnchorFraction(data),
            },
          );
          return range ? { 'yaxis.range': range, 'yaxis.autorange': false } : {};
        }

        function buildSpectrumFigure(data, plotId=null) {
          const originalState = getOriginalSpectrumState(data);
          const traceMode = getSpectrumTraceMode(data, plotId);
          const usingOriginalState = traceMode === "original" && originalState;
          const pts = usingOriginalState
            ? originalState.preview_points
            : (Array.isArray(data.preview_points) ? data.preview_points : []);
          const peaks = Array.isArray(data.inferred_peaks) ? data.inferred_peaks : [];
          const comparison = data?.comparison || {};
          const matchedItems = Array.isArray(comparison.matched) ? comparison.matched : [];
          const missingReference = Array.isArray(comparison.missing_reference) ? comparison.missing_reference : [];
          const impurityCandidates = Array.isArray(data?.metadata?.impurity_candidates) ? data.metadata.impurity_candidates : [];
          const x = pts.map((p) => Number(p.shift_ppm));
          const rawY = pts.map((p) => Number(p.intensity));
          const displayResult = getSpectrumBaselineEqualizedDisplay(pts, data, { usingOriginalState });
          const displayY = displayResult.y;
          const displayPts = displayResult.points;
          const finiteY = displayY.filter((v) => Number.isFinite(v));
          const yMin = finiteY.length ? Math.min(...finiteY) : 0;
          const yMax = finiteY.length ? Math.max(...finiteY) : 1;
          const verticalScale = usingOriginalState ? 1 : clampSpectrumVerticalScale(Number(state.spectrumVerticalScale || 1));
          const displayBaseline = state.spectrumZeroLine || displayResult.applied ? 0 : getSpectrumDisplayBaseline(displayY);
          const yAxisRange = getSpectrumVerticalAxisRange(
            displayY,
            verticalScale,
            displayBaseline,
            {
              clipTallPeaks: state.spectrumTallPeakClip,
              baselineAnchorFraction: getSpectrumBaselineAnchorFraction(data),
            },
          );
          const selectedPeakKey = state.selectedSpectrumMarker?.peakKey || "";
          const markerYForPeak = (peak, fallbackFraction = 0.94) => {
            const inferred = findSpectrumPeakIntensity(displayPts, peak?.shift_ppm);
            if (inferred !== null && Number.isFinite(inferred)) {
              return inferred;
            }
            return yMin + (yMax - yMin) * fallbackFraction;
          };
          const traceType = x.length > 1200 ? 'scattergl' : 'scatter';
          const traces = [
            {
              type: traceType,
              x,
              y: displayY,
              mode: 'lines',
              name: usingOriginalState
                ? 'Original uploaded spectrum state (preserved)'
                : `Real spectrum — original intensity preserved${displayResult.applied ? ' · baseline-locked display' : ''} (${formatSpectrumVerticalScaleLabel(verticalScale)} y-axis gain)`,
              line: { color: usingOriginalState ? '#64748b' : '#2855d9', width: 2 },
              customdata: rawY,
              hovertemplate: usingOriginalState
                ? 'ppm: %{x:.4f}<br>original intensity: %{customdata:.4f}<extra></extra>'
                : (displayResult.applied
                  ? 'ppm: %{x:.4f}<br>baseline-locked display: %{y:.4f}<br>evidence intensity: %{customdata:.4f}<extra></extra>'
                  : 'ppm: %{x:.4f}<br>raw intensity: %{customdata:.4f}<extra></extra>'),
            }
          ];

          if (state.spectrumShowPeaks && peaks.length) {
            const rawPeakY = peaks.map((p) => {
              const inferred = findSpectrumPeakIntensity(displayPts, p.shift_ppm);
              return inferred !== null && !Number.isNaN(inferred)
                ? inferred
                : Number(p.integration_h || 0);
            });
            const rawPeakFinite = rawPeakY.filter((v) => Number.isFinite(v));
            const peakMin = rawPeakFinite.length ? Math.min(...rawPeakFinite) : yMin;
            const peakMax = rawPeakFinite.length ? Math.max(...rawPeakFinite) : yMax;
            const denom = Math.max(peakMax - peakMin, 1e-9);

            const peakX = peaks.map((p) => Number(p.shift_ppm));
            const peakY = rawPeakY;
            const labelThreshold = Math.max(0, Math.min(1, Number(state.spectrumLabelThreshold ?? 0.12)));
            const nucleusForLabels = String(data?.metadata?.nucleus || data?.nucleus || "").toUpperCase();
            const maxPeakLabels = nucleusForLabels === "13C" ? 8 : 14;
            const minLabelSeparation = nucleusForLabels === "13C" ? 4.0 : 0.10;
            const labelCandidates = peaks.map((peak, idx) => ({
              idx,
              shift: Number(peak.shift_ppm),
              strength: Math.abs(Number(rawPeakY[idx]) - displayBaseline),
              rel: (rawPeakY[idx] - peakMin) / denom,
            })).filter((item) => Number.isFinite(item.shift) && item.rel >= labelThreshold)
              .sort((a, b) => b.strength - a.strength);
            const labelledIndices = new Set();
            for (const candidate of labelCandidates) {
              if (labelledIndices.size >= maxPeakLabels) break;
              const separated = [...labelledIndices].every((idx) => Math.abs(Number(peaks[idx]?.shift_ppm) - candidate.shift) >= minLabelSeparation);
              if (separated) labelledIndices.add(candidate.idx);
            }
            const peakText = peaks.map((p, idx) => {
              const peakKey = buildPeakKey(p);
              return labelledIndices.has(idx) || peakKey === selectedPeakKey ? `${Number(p.shift_ppm).toFixed(2)} ppm` : '';
            });
            const peakPayloads = peaks.map((peak) => {
              const peakKey = buildPeakKey(peak);
              return JSON.stringify({
                markerType: 'detected',
                peakKey,
                peak,
                label: formatSpectrumPeakSummary(peak),
              });
            });
            const peakMarkerColors = peaks.map((peak) => {
              const decision = getSpectrumPeakDecision(buildPeakKey(peak));
              if (decision === 'accepted') return '#14804a';
              if (decision === 'excluded') return '#98a2b3';
              return '#b42318';
            });
            const peakMarkerSymbols = peaks.map((peak) => {
              const decision = getSpectrumPeakDecision(buildPeakKey(peak));
              return decision === 'excluded' ? 'x' : 'diamond';
            });
            const peakMarkerSizes = peaks.map((peak) => (
              buildPeakKey(peak) === selectedPeakKey ? 11 : 8
            ));
            traces.push({
              x: peakX,
              y: peakY,
              mode: 'markers+text',
              name: 'Detected peaks',
              text: peakText,
              textposition: 'top center',
              customdata: peakPayloads,
              marker: {
                color: peakMarkerColors,
                size: peakMarkerSizes,
                symbol: peakMarkerSymbols,
                line: { color: '#ffffff', width: 0.8 },
              },
              hovertemplate: 'Detected peak: %{x:.4f} ppm<br>Click to review<extra></extra>',
            });
          }

          if (state.spectrumShowPeaks && matchedItems.length) {
            traces.push({
              x: matchedItems.map((item) => Number(item.extracted_peak?.shift_ppm)),
              y: matchedItems.map((item) => markerYForPeak(item.extracted_peak, 0.92)),
              mode: 'markers',
              name: 'Matched markers',
              text: matchedItems.map((item) => item.reference_raw_text || formatSpectrumPeakSummary(item.reference_peak)),
              customdata: matchedItems.map((item) => JSON.stringify({
                markerType: 'matched',
                peakKey: buildPeakKey(item.extracted_peak),
                peak: item.extracted_peak,
                referenceText: item.reference_raw_text || formatSpectrumPeakSummary(item.reference_peak),
                matchStatus: item.status || 'matched',
              })),
              marker: {
                color: 'rgba(20,128,74,0.16)',
                size: 15,
                symbol: 'circle-open',
                line: { color: '#14804a', width: 2.2 },
              },
              hovertemplate: 'Matched reference: %{text}<br>Click to review the linked extracted peak<extra></extra>',
            });
          }

          if (state.spectrumShowPeaks) {
            const referenceMarkerItems = [];
            for (const item of matchedItems) {
              referenceMarkerItems.push({
                shift: Number(item.reference_peak?.shift_ppm),
                y: markerYForPeak(item.extracted_peak, 0.97),
                text: item.reference_raw_text || formatSpectrumPeakSummary(item.reference_peak),
                peakKey: buildPeakKey(item.extracted_peak),
                peak: item.extracted_peak,
                matchStatus: item.status || 'matched',
              });
            }
            for (const item of missingReference) {
              referenceMarkerItems.push({
                shift: Number(item.reference_peak?.shift_ppm),
                y: markerYForPeak(item.reference_peak, 0.99),
                text: item.reference_raw_text || formatSpectrumPeakSummary(item.reference_peak),
                peakKey: null,
                peak: null,
                matchStatus: 'missing',
              });
            }
            if (!referenceMarkerItems.length) {
              const referencePeaks = Array.isArray(data.reference_peaks) ? data.reference_peaks : [];
              for (const peak of referencePeaks) {
                referenceMarkerItems.push({
                  shift: Number(peak.shift_ppm),
                  y: markerYForPeak(peak, 0.98),
                  text: formatSpectrumPeakSummary(peak),
                  peakKey: null,
                  peak: null,
                  matchStatus: 'reference',
                });
              }
            }
            if (referenceMarkerItems.length) {
              traces.push({
                x: referenceMarkerItems.map((item) => item.shift),
                y: referenceMarkerItems.map((item) => item.y),
                mode: 'markers',
                name: 'Reference markers',
                text: referenceMarkerItems.map((item) => item.text),
                customdata: referenceMarkerItems.map((item) => JSON.stringify({
                  markerType: 'reference',
                  peakKey: item.peakKey,
                  peak: item.peak,
                  referenceText: item.text,
                  matchStatus: item.matchStatus,
                })),
                marker: {
                  color: referenceMarkerItems.map((item) => item.matchStatus === 'missing' ? '#64748b' : '#2157d5'),
                  size: 12,
                  symbol: 'x',
                  line: { color: '#ffffff', width: 1.2 },
                },
                hovertemplate: 'Reference marker: %{text}<br>Click for match details<extra></extra>',
              });
            }
          }

          if (state.spectrumShowPeaks && impurityCandidates.length) {
            const impurityItems = impurityCandidates.map((candidate) => {
              const linkedPeak = findSpectrumPeakByShift(peaks, candidate.shift_ppm) || {
                shift_ppm: candidate.shift_ppm,
                multiplicity: 'm',
                integration_h: candidate.integration_h,
              };
              return {
                shift: Number(candidate.shift_ppm),
                y: markerYForPeak(linkedPeak, 0.9),
                text: `${Number(candidate.shift_ppm).toFixed(2)} ppm · ${candidate.reason || 'possible impurity candidate'}`,
                peakKey: buildPeakKey(linkedPeak),
                peak: linkedPeak,
                reason: candidate.reason || 'possible impurity candidate',
              };
            });
            traces.push({
              x: impurityItems.map((item) => item.shift),
              y: impurityItems.map((item) => item.y),
              mode: 'markers',
              name: 'Impurity markers',
              text: impurityItems.map((item) => item.text),
              customdata: impurityItems.map((item) => JSON.stringify({
                markerType: 'impurity',
                peakKey: item.peakKey,
                peak: item.peak,
                reason: item.reason,
              })),
              marker: {
                color: 'rgba(245,158,11,0.92)',
                size: 12,
                symbol: 'triangle-down',
                line: { color: '#9a6700', width: 1.6 },
              },
              hovertemplate: 'Impurity marker: %{text}<br>Click to accept or exclude this peak<extra></extra>',
            });
          }

          if (state.spectrumWeakPeakMagnifier && finiteY.length >= 3) {
            const sortedY = [...finiteY].sort((a, b) => a - b);
            const center = percentileFromSorted(sortedY, 50);
            const maxAbs = Math.max(...finiteY.map((value) => Math.abs(value - center)), 1e-9);
            const gain = 18;
            const denom = Math.log1p(gain);
            const magnifiedY = displayY.map((value) => {
              const delta = Number(value) - center;
              if (!Number.isFinite(delta)) return null;
              return Math.sign(delta) * Math.log1p(gain * Math.min(1, Math.abs(delta) / maxAbs)) / denom;
            });
            traces.push({
              type: traceType,
              x,
              y: magnifiedY,
              mode: 'lines',
              name: 'Weak peak magnifier',
              xaxis: 'x2',
              yaxis: 'y2',
              line: { color: '#0f766e', width: 1.6 },
              hovertemplate: 'ppm: %{x:.4f}<br>magnified relative intensity: %{y:.4f}<extra></extra>',
            });
          }

          const finiteX = x.filter((value) => Number.isFinite(value));
          const shapes = [];
          if (finiteX.length && Number.isFinite(displayBaseline)) {
            shapes.push({
              type: 'line',
              x0: Math.max(...finiteX),
              x1: Math.min(...finiteX),
              y0: displayBaseline,
              y1: displayBaseline,
              xref: 'x',
              yref: 'y',
              layer: 'below',
              line: { color: 'rgba(23,32,51,0.42)', width: 1 },
            });
          }
          const solvent = String(data.solvent || data.metadata?.solvent || '').toUpperCase();
          if (solvent === 'D2O') {
            shapes.push({ type: 'rect', x0: 4.6, x1: 5.1, y0: 0, y1: 1, yref: 'paper', fillcolor: 'rgba(255,193,7,0.12)', line: { width: 0 } });
          } else if (solvent === 'CDCL3') {
            shapes.push({ type: 'rect', x0: 7.15, x1: 7.35, y0: 0, y1: 1, yref: 'paper', fillcolor: 'rgba(255,193,7,0.12)', line: { width: 0 } });
          }

          return {
            data: traces,
            layout: {
              margin: { l: 48, r: 24, t: 22, b: 42 },
              paper_bgcolor: '#ffffff',
              plot_bgcolor: '#ffffff',
              dragmode: state.spectrumDragMode || 'pan',
              hovermode: 'closest',
              showlegend: true,
              legend: { orientation: 'h', yanchor: 'bottom', y: 1.02, x: 0 },
              uirevision: normalizeSpectrumPlotId(plotId),
              xaxis: {
                title: 'Chemical shift (ppm)',
                ...(Array.isArray(state.latestSpectrumXRange) ? { range: state.latestSpectrumXRange } : { autorange: 'reversed' }),
                showgrid: true,
                showline: true,
                linecolor: '#172033',
                linewidth: 1,
                mirror: true,
                ticks: 'outside',
                zeroline: false,
                gridcolor: '#f2f4f7',
              },
              yaxis: {
                title: usingOriginalState ? 'Original intensity' : 'Intensity',
                ...(Array.isArray(yAxisRange) ? { range: yAxisRange } : {}),
                autorange: false,
                fixedrange: true,
                side: 'right',
                automargin: true,
                showgrid: true,
                showline: true,
                linecolor: '#172033',
                linewidth: 1,
                mirror: true,
                zeroline: Boolean(state.spectrumZeroLine),
                zerolinecolor: 'rgba(23,32,51,0.42)',
                zerolinewidth: 1,
                gridcolor: '#eef2f7',
              },
              ...(state.spectrumWeakPeakMagnifier ? {
                xaxis2: {
                  domain: [0.58, 0.98],
                  anchor: 'y2',
                  ...(Array.isArray(state.latestSpectrumXRange) ? { range: state.latestSpectrumXRange } : { autorange: 'reversed' }),
                  showgrid: false,
                  zeroline: false,
                  showticklabels: false,
                  linecolor: '#0f766e',
                  linewidth: 1,
                  mirror: true,
                },
                yaxis2: {
                  title: 'Weak peak inset',
                  domain: [0.70, 0.98],
                  anchor: 'x2',
                  side: 'right',
                  range: [-1.08, 1.08],
                  showgrid: false,
                  zeroline: true,
                  zerolinecolor: 'rgba(15,118,110,0.25)',
                  tickfont: { color: '#0f766e' },
                  titlefont: { color: '#0f766e' },
                },
              } : {}),
              clickmode: 'event+select',
              shapes,
              transition: { duration: 0 },
            },
            config: {
              responsive: true,
              scrollZoom: true,
              displayModeBar: false,
              displaylogo: false,
              modeBarButtonsToRemove: ['select2d', 'lasso2d'],
            },
          };
        }

        function renderInteractiveSpectrumPlot(data, plotId=null) {
          const plotTarget = getSpectrumPlotTarget(plotId);
          if (!plotTarget) return;
          const figure = buildSpectrumFigure(data, plotId);
          if (window.Plotly) {
            const renderPromise = plotTarget.dataset.plotReady === 'true'
              ? window.Plotly.react(plotTarget, figure.data, figure.layout, figure.config)
              : window.Plotly.newPlot(plotTarget, figure.data, figure.layout, figure.config);
            Promise.resolve(renderPromise).then((gd) => {
              plotTarget.dataset.plotReady = 'true';
              if (gd.dataset.relayoutBound !== 'true') {
                gd.dataset.relayoutBound = 'true';
                gd.on('plotly_relayout', (eventData) => {
                  const min = eventData['xaxis.range[0]'];
                  const max = eventData['xaxis.range[1]'];
                  if (min !== undefined && max !== undefined) {
                    state.latestSpectrumXRange = [Number(min), Number(max)];
                  }
                });
              }
              if (gd.dataset.clickBound !== 'true') {
                gd.dataset.clickBound = 'true';
                gd.on('plotly_click', (eventData) => {
                  const markerPayload = getSpectrumClickPayload(eventData?.points?.[0]);
                  if (!markerPayload) return;
                  selectSpectrumMarker(markerPayload, plotTarget.id);
                });
              }
              gd.style.cursor = 'crosshair';
              if (gd.dataset.hoverBound !== 'true') {
                gd.dataset.hoverBound = 'true';
                gd.on('plotly_hover', () => {
                  if (gd) gd.style.cursor = 'pointer';
                });
                gd.on('plotly_unhover', () => {
                  if (gd) gd.style.cursor = 'crosshair';
                });
              }
              if (gd.dataset.contextMenuBound !== 'true') {
                gd.dataset.contextMenuBound = 'true';
                gd.addEventListener('contextmenu', (event) => {
                  showSpectrumContextMenu(event, plotTarget.id);
                });
              }
            });
          } else {
            plotTarget.innerHTML = '<p class="muted small">Interactive plotting library did not load. Preview is unavailable.</p>';
          }
        }

        function getSpectrumContextMenuNode() {
          let menu = el("spectrumContextMenu");
          if (!menu) {
            menu = document.createElement("div");
            menu.id = "spectrumContextMenu";
            menu.className = "spectrum-context-menu";
            document.body.appendChild(menu);
          }
          return menu;
        }

        function hideSpectrumContextMenu() {
          const menu = el("spectrumContextMenu");
          if (menu) menu.style.display = "none";
        }

        function getRawFidCorrectionKind(context) {
          const data = context?.data || {};
          const targetId = context?.options?.targetId || "";
          const nucleus = String(data?.metadata?.nucleus || data?.nucleus || "").toUpperCase();
          if (targetId === "fidPreviewBox") return "1H";
          if (targetId === "carbon13Box" && data.source_mode === "raw_fid") return "13C";
          if (data.source_mode === "raw_fid" && nucleus === "13C") return "13C";
          return "";
        }

        function formatRawFidCorrectionKind(kind) {
          if (kind === "13C") return "¹³C";
          if (kind === "1H") return "¹H";
          return "FID";
        }

        function spectrumContextMenuItems(context, plotId) {
          const data = context?.data || {};
          const hasOriginal = Boolean(getOriginalSpectrumState(data));
          const traceMode = getSpectrumTraceMode(data, plotId);
          const rawFidKind = getRawFidCorrectionKind(context);
          const showPeakLabel = state.spectrumShowPeaks ? "Hide peak markers" : "Show peak markers";
          const clipLabel = state.spectrumTallPeakClip ? "Disable tall-peak clipping" : "Enable tall-peak clipping";
          const magnifierLabel = state.spectrumWeakPeakMagnifier ? "Hide weak-peak magnifier" : "Show weak-peak magnifier";
          const zeroLineLabel = state.spectrumZeroLine ? "Hide zero baseline line" : "Show zero baseline line";
          const items = [
            { label: "Zoom in", action: "zoom_in" },
            { label: "Zoom out", action: "zoom_out" },
            { label: "Reset view", action: "reset_view" },
            { label: "Pan mode", action: "pan_mode" },
            { label: "Zoom mode", action: "zoom_mode" },
            { divider: true },
            { label: "Increase peak height", action: "height_up" },
            { label: "Decrease peak height", action: "height_down" },
            { label: "Reset peak height", action: "height_reset" },
            { label: clipLabel, action: "toggle_clip" },
            { label: magnifierLabel, action: "toggle_magnifier" },
            { label: zeroLineLabel, action: "toggle_zero_line" },
            { label: showPeakLabel, action: "toggle_peaks" },
          ];
          if (hasOriginal) {
            items.push({ divider: true });
            items.push({
              label: traceMode === "original" ? "Real evidence view" : "Original upload view",
              action: traceMode === "original" ? "review_view" : "original_view",
            });
          }
          if (rawFidKind) {
            const rawFidLabel = formatRawFidCorrectionKind(rawFidKind);
            items.push({ divider: true });
            items.push({ label: `Apply ${rawFidLabel} phase correction`, action: "phase_correction" });
            items.push({ label: `Apply ${rawFidLabel} baseline correction`, action: "baseline_correction" });
          }
          return items;
        }

        async function runSpectrumContextAction(action, plotId) {
          const context = getSpectrumContext(plotId);
          const rawFidKind = getRawFidCorrectionKind(context);
          if (action === "zoom_in") return zoomSpectrum(0.55, plotId);
          if (action === "zoom_out") return zoomSpectrum(1.8, plotId);
          if (action === "reset_view") return resetSpectrumView(plotId);
          if (action === "pan_mode") return setSpectrumDragMode("pan", plotId);
          if (action === "zoom_mode") return setSpectrumDragMode("zoom", plotId);
          if (action === "height_up") return stepSpectrumVerticalScale(2, plotId);
          if (action === "height_down") return stepSpectrumVerticalScale(-2, plotId);
          if (action === "height_reset") return resetSpectrumPeakView(plotId);
          if (action === "toggle_clip") return toggleSpectrumTallPeakClip(plotId);
          if (action === "toggle_magnifier") return toggleSpectrumWeakPeakMagnifier(plotId);
          if (action === "toggle_zero_line") return toggleSpectrumZeroLine(plotId);
          if (action === "toggle_peaks") return toggleSpectrumPeaks(plotId);
          if (action === "original_view") return setSpectrumTraceMode("original", plotId);
          if (action === "review_view") return setSpectrumTraceMode("review", plotId);
          if (action === "phase_correction") {
            if (rawFidKind === "13C") return applyCarbon13FidPhaseCorrection();
            if (rawFidKind === "1H") return applyRawFidPhaseCorrection();
          }
          if (action === "baseline_correction") {
            if (rawFidKind === "13C") return applyCarbon13FidBaselineCorrection();
            if (rawFidKind === "1H") return applyRawFidBaselineCorrection();
          }
          setJson({ error: "That spectrum action is not available for this preview." });
        }

        function showSpectrumContextMenu(event, plotId=null) {
          const context = getSpectrumContext(plotId);
          if (!context?.data) return;
          event.preventDefault();
          event.stopPropagation();
          const activePlotId = normalizeSpectrumPlotId(plotId);
          const menu = getSpectrumContextMenuNode();
          const items = spectrumContextMenuItems(context, activePlotId);
          menu.innerHTML = items.map((item) => (
            item.divider
              ? '<div class="context-divider"></div>'
              : `<button type="button" data-action="${escapeHtml(item.action)}">${escapeHtml(item.label)}</button>`
          )).join("");
          menu.querySelectorAll("button[data-action]").forEach((button) => {
            button.addEventListener("click", async () => {
              const action = button.getAttribute("data-action") || "";
              hideSpectrumContextMenu();
              await runSpectrumContextAction(action, activePlotId);
            });
          });
          menu.style.display = "block";
          const rect = menu.getBoundingClientRect();
          const left = Math.min(event.clientX, window.innerWidth - rect.width - 8);
          const top = Math.min(event.clientY, window.innerHeight - rect.height - 8);
          menu.style.left = `${Math.max(8, left)}px`;
          menu.style.top = `${Math.max(8, top)}px`;
        }

        function zoomSpectrum(factor, plotId=null) {
          const context = getSpectrumContext(plotId);
          const data = context?.data;
          if (!data || !Array.isArray(data.preview_points) || !data.preview_points.length || !window.Plotly) return;
          const xs = data.preview_points.map((p) => Number(p.shift_ppm));
          const current = state.latestSpectrumXRange || [Math.max(...xs), Math.min(...xs)];
          const a = Number(current[0]);
          const b = Number(current[1]);
          const center = (a + b) / 2;
          const halfWidth = Math.abs(a - b) / 2;
          const nextHalf = Math.max(0.05, halfWidth * factor);
          const nextRange = [center + nextHalf, center - nextHalf];
          state.latestSpectrumXRange = nextRange;
          relayoutSpectrumPlot({ 'xaxis.range': nextRange }, plotId);
        }

        function resetSpectrumView(plotId=null) {
          const context = getSpectrumContext(plotId);
          const data = context?.data;
          if (!data || !window.Plotly) return;
          state.latestSpectrumXRange = null;
          relayoutSpectrumPlot({ 'xaxis.autorange': 'reversed', ...getSpectrumYAxisUpdate(data, plotId) }, plotId);
        }

        function setSpectrumDragMode(mode, plotId=null) {
          setActiveSpectrumPlot(plotId);
          state.spectrumDragMode = mode === 'zoom' ? 'zoom' : 'pan';
          relayoutSpectrumPlot({ dragmode: state.spectrumDragMode }, plotId);
          refreshSpectrumToolbarState(plotId);
        }

        function shiftSpectrum(direction, plotId=null) {
          const context = getSpectrumContext(plotId);
          const data = context?.data;
          if (!data || !Array.isArray(data.preview_points) || !data.preview_points.length || !window.Plotly) return;
          const xs = data.preview_points.map((p) => Number(p.shift_ppm));
          const domainMax = Math.max(...xs);
          const domainMin = Math.min(...xs);
          const current = state.latestSpectrumXRange || [domainMax, domainMin];
          const left = Number(current[0]);
          const right = Number(current[1]);
          const width = Math.abs(left - right);
          const shiftBy = width * 0.22 * (direction === 'left' ? 1 : -1);
          let next = [left + shiftBy, right + shiftBy];

          const nextMax = Math.max(next[0], next[1]);
          const nextMin = Math.min(next[0], next[1]);

          if (nextMax > domainMax) {
            const over = nextMax - domainMax;
            next = [next[0] - over, next[1] - over];
          }
          if (nextMin < domainMin) {
            const under = domainMin - nextMin;
            next = [next[0] + under, next[1] + under];
          }

          state.latestSpectrumXRange = next;
          relayoutSpectrumPlot({ 'xaxis.range': next }, plotId);
        }

        function setSpectrumVerticalScale(value, plotId=null) {
          const context = getSpectrumContext(plotId);
          state.spectrumVerticalScale = clampSpectrumVerticalScale(Number(value));
          renderSpectrumGainControl(plotId);
          if (context?.data && window.Plotly) {
            relayoutSpectrumPlot(getSpectrumYAxisUpdate(context.data, plotId), plotId);
          }
        }

        function setSpectrumLabelThreshold(value, plotId=null) {
          setActiveSpectrumPlot(plotId);
          const parsed = Number(value);
          state.spectrumLabelThreshold = Number.isFinite(parsed) ? parsed : 0.12;
          const valueNode = el('spectrumLabelThresholdValue');
          if (valueNode) valueNode.textContent = `${Math.round(state.spectrumLabelThreshold * 100)}%`;
          rerenderSpectrumPreview(plotId);
        }

        function stepSpectrumVerticalScale(stepDelta, plotId=null) {
          const direction = stepDelta >= 0 ? 1 : -1;
          const steps = Math.max(1, Math.abs(Math.trunc(Number(stepDelta) || 1)));
          let next = clampSpectrumVerticalScale(Number(state.spectrumVerticalScale || 1));
          for (let idx = 0; idx < steps; idx += 1) {
            const factor = getSpectrumVerticalScaleFactor(next);
            next = direction > 0 ? next * factor : next / factor;
          }
          if (direction < 0 && next < 1.02) next = 1;
          setSpectrumVerticalScale(next, plotId);
        }

        function adjustSpectrumVerticalScaleFromWheel(event, plotId=null) {
          const context = getSpectrumContext(plotId);
          if (!context?.data) return;
          event.preventDefault();
          event.stopPropagation();
          const delta = Number(event.deltaY || 0);
          if (!Number.isFinite(delta) || delta === 0) return;
          const steps = event.shiftKey ? 3 : (Math.abs(delta) > 80 ? 2 : 1);
          stepSpectrumVerticalScale(delta < 0 ? steps : -steps, plotId);
        }

        function resetSpectrumPeakView(plotId=null) {
          const context = getSpectrumContext(plotId);
          state.spectrumVerticalScale = 1;
          state.spectrumLabelThreshold = 0.12;
          renderSpectrumGainControl(plotId);
          if (context?.data && window.Plotly) {
            relayoutSpectrumPlot(getSpectrumYAxisUpdate(context.data, plotId), plotId);
          }
        }

        function toggleSpectrumTallPeakClip(plotId=null) {
          const context = getSpectrumContext(plotId);
          state.spectrumTallPeakClip = !state.spectrumTallPeakClip;
          if (context?.data && window.Plotly) {
            relayoutSpectrumPlot(getSpectrumYAxisUpdate(context.data, plotId), plotId);
          }
          refreshSpectrumToolbarState(plotId, context?.data || null);
        }

        function toggleSpectrumWeakPeakMagnifier(plotId=null) {
          state.spectrumWeakPeakMagnifier = !state.spectrumWeakPeakMagnifier;
          rerenderSpectrumPreview(plotId);
        }

        function toggleSpectrumZeroLine(plotId=null) {
          const context = getSpectrumContext(plotId);
          state.spectrumZeroLine = !state.spectrumZeroLine;
          if (context?.data && window.Plotly) {
            relayoutSpectrumPlot({
              ...getSpectrumYAxisUpdate(context.data, plotId),
              'yaxis.zeroline': Boolean(state.spectrumZeroLine),
            }, plotId);
          }
          refreshSpectrumToolbarState(plotId, context?.data || null);
        }

        function focusSpectrumRegion(left, right, plotId=null) {
          if (!window.Plotly) return;
          const range = [left, right];
          state.latestSpectrumXRange = range;
          relayoutSpectrumPlot({ 'xaxis.range': range }, plotId);
        }

        function toggleSpectrumPeaks(plotId=null) {
          setActiveSpectrumPlot(plotId);
          state.spectrumShowPeaks = !state.spectrumShowPeaks;
          rerenderSpectrumPreview(plotId);
        }

        function getOriginalSpectrumState(data) {
          const original = data?.metadata?.original_spectrum_state;
          const points = Array.isArray(original?.preview_points) ? original.preview_points : [];
          return points.length ? original : null;
        }

        function getSpectrumTraceMode(data, plotId=null) {
          const activeId = normalizeSpectrumPlotId(plotId);
          const mode = state.spectrumTraceModes?.[activeId] || state.spectrumTraceMode || "review";
          return mode === "original" && getOriginalSpectrumState(data)
            ? "original"
            : "review";
        }

        function setSpectrumTraceMode(mode, plotId=null) {
          const activeId = setActiveSpectrumPlot(plotId);
          const nextMode = mode === "original" ? "original" : "review";
          state.spectrumTraceMode = nextMode;
          state.spectrumTraceModes = { ...(state.spectrumTraceModes || {}), [activeId]: nextMode };
          rerenderSpectrumPreview(plotId);
        }

        function formatSpectrumPeakSummary(peak) {
          if (!peak) return '—';
          const shift = Number(peak.shift_ppm);
          const shiftText = Number.isFinite(shift) ? shift.toFixed(2) : String(peak.shift_ppm ?? '—');
          if (peak.nucleus === "13C" || peak.carbon_type || peak.region || peak.assignment) {
            const bits = [];
            if (peak.region) bits.push(peak.region);
            if (peak.carbon_type) bits.push(peak.carbon_type);
            if (peak.assignment) bits.push(peak.assignment);
            return `${shiftText} ppm${bits.length ? ` (${bits.join(", ")})` : ""}`;
          }
          const mult = peak.multiplicity || 'm';
          const integration = peak.integration_h ?? '—';
          const jText = getSpectrumJValueText(peak);
          return `${shiftText} (${mult}${jText ? `, ${jText}` : ''}, ${integration}H)`;
        }

        function getSpectrumJValueText(peak) {
          const values = Array.isArray(peak?.j_values_hz)
            ? peak.j_values_hz.map((value) => Number(value)).filter((value) => Number.isFinite(value) && value > 0)
            : [];
          if (!values.length) return '';
          return `J = ${values.map((value) => value.toFixed(1)).join(', ')} Hz`;
        }

        function formatSpectrumMarkerType(markerType) {
          if (markerType === 'matched') return 'Matched marker';
          if (markerType === 'reference') return 'Reference marker';
          if (markerType === 'impurity') return 'Impurity marker';
          return 'Detected peak';
        }

        function renderSpectrumReviewerPanel(data, plotId=null) {
          const activePlotId = normalizeSpectrumPlotId(plotId);
          const peaks = Array.isArray(data?.inferred_peaks) ? data.inferred_peaks : [];
          const acceptedCount = peaks.filter((peak) => getSpectrumPeakDecision(buildPeakKey(peak)) === 'accepted').length;
          const excludedCount = peaks.filter((peak) => getSpectrumPeakDecision(buildPeakKey(peak)) === 'excluded').length;
          const includedCount = peaks.length - excludedCount;
          const reviewedText = getSpectrumReviewedNmrText(data);
          const originalText = String(data?.inferred_nmr_text || '').trim();
          const selected = state.selectedSpectrumMarker;
          const selectedDecision = selected?.peakKey ? getSpectrumPeakDecision(selected.peakKey) : 'neutral';
          const canReviewSelectedPeak = Boolean(selected?.peakKey);
          const selectedSummary = selected?.peak
            ? formatSpectrumPeakSummary(selected.peak)
            : (selected?.referenceText || 'Select a detected, matched, reference, or impurity marker on the spectrum.');
          const selectedExtraLine = selected?.referenceText && selected.referenceText !== selectedSummary
            ? `<div class="small muted" style="margin-top:.25rem;">Reference: ${escapeHtml(selected.referenceText)}</div>`
            : '';
          const selectedReason = selected?.reason
            ? `<div class="small muted" style="margin-top:.25rem;">Reason: ${escapeHtml(selected.reason)}</div>`
            : '';
          const selectedStatus = selected?.matchStatus
            ? `<div class="small muted" style="margin-top:.25rem;">Match status: ${escapeHtml(selected.matchStatus)}</div>`
            : '';
          const decisionBadgeClass = selectedDecision === 'accepted' ? 'ok' : (selectedDecision === 'excluded' ? 'bad' : 'warn');
          const decisionLabel = selectedDecision === 'accepted' ? 'Accepted' : (selectedDecision === 'excluded' ? 'Excluded' : 'Included by default');
          const disabledAttr = canReviewSelectedPeak ? '' : ' disabled';

          return `
            <div class="panel" style="margin-top:.8rem;">
              <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                <div>
                  <strong>Reviewer peak controls</strong>
                  <div class="small muted" style="margin-top:.25rem;">Click a marker on the spectrum, then accept, exclude, reset, or undo that peak decision.</div>
                </div>
                <div class="comparison-chip-row">
                  <span class="status-badge ok">Accepted ${escapeHtml(acceptedCount)}</span>
                  <span class="status-badge warn">Included ${escapeHtml(includedCount)}</span>
                  <span class="status-badge bad">Excluded ${escapeHtml(excludedCount)}</span>
                </div>
              </div>
              <div class="comparison-chip-row">
                <span class="status-badge ok">Matched markers</span>
                <span class="status-badge warn">Reference markers</span>
                <span class="status-badge warn">Impurity markers</span>
                <span class="status-badge warn">Click any marker to review</span>
              </div>
              <div class="panel" style="margin-top:.8rem;">
                <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                  <strong>${escapeHtml(formatSpectrumMarkerType(selected?.markerType || 'detected'))}</strong>
                  <span class="status-badge ${decisionBadgeClass}">${escapeHtml(decisionLabel)}</span>
                </div>
                <div class="mono" style="margin-top:.45rem; white-space:pre-wrap;">${escapeHtml(selectedSummary)}</div>
                ${selectedExtraLine}
                ${selectedReason}
                ${selectedStatus}
                <div class="row" style="margin-top:.75rem;">
                  <button type="button" class="${selectedDecision === 'accepted' ? 'secondary' : 'ghost'}" onclick="setSpectrumPeakDecision('accepted', '${activePlotId}')"${disabledAttr}>Accept peak</button>
                  <button type="button" class="${selectedDecision === 'excluded' ? 'danger' : 'ghost'}" onclick="setSpectrumPeakDecision('excluded', '${activePlotId}')"${disabledAttr}>Exclude peak</button>
                  <button type="button" class="ghost" onclick="setSpectrumPeakDecision('neutral', '${activePlotId}')"${disabledAttr}>Reset peak</button>
                  <button type="button" class="ghost" onclick="undoSpectrumPeakDecision('${activePlotId}')" title="Undo the last reviewer peak decision. Shortcut: Ctrl+Z or Cmd+Z.">Undo</button>
                  <button type="button" class="ghost" onclick="clearSpectrumPeakDecisions('${activePlotId}')">Reset all review decisions</button>
                </div>
                ${canReviewSelectedPeak ? '<div class="small muted" style="margin-top:.6rem;">Excluded peaks are removed from the reviewed peak list used by Use reviewed peaks as text and Analyze uploaded spectrum.</div>' : '<div class="small muted" style="margin-top:.6rem;">Reference markers without a linked extracted peak can be inspected, but only extracted peaks can be accepted or excluded.</div>'}
              </div>
              <div class="panel" style="margin-top:.8rem;">
                <strong>Reviewed peak list</strong>
                <div class="mono" style="margin-top:.45rem; white-space:pre-wrap;">${escapeHtml(reviewedText || 'All extracted peaks are currently excluded.')}</div>
                ${reviewedText && reviewedText !== originalText ? `<div class="small muted" style="margin-top:.65rem;">Original generated peak list</div><div class="mono" style="margin-top:.35rem; white-space:pre-wrap;">${escapeHtml(originalText)}</div>` : ''}
              </div>
            </div>
          `;
        }

        function renderSpectrumComparison(data) {
          const comparison = data?.comparison;
          if (!comparison) return '';
          const matched = Array.isArray(comparison.matched) ? comparison.matched : [];
          const missing = Array.isArray(comparison.missing_reference) ? comparison.missing_reference : [];
          const extra = Array.isArray(comparison.extra_spectrum) ? comparison.extra_spectrum : [];
          const notes = Array.isArray(comparison.notes) ? comparison.notes : [];
          const referenceTotal = comparison.reference_total_h ?? '—';
          const extractedTotal = comparison.extracted_total_h ?? '—';
          const visibleTarget = comparison.structure_visible_h ?? '—';
          return `
            <div class="panel" style="margin-top:.8rem;">
              <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                <strong>Reference-guided comparison</strong>
                <div class="comparison-chip-row">
                  <span class="status-badge ok">Matched ${escapeHtml(comparison.matched_count ?? matched.length)}</span>
                  <span class="status-badge warn">Shifted ${escapeHtml(comparison.shifted_count ?? 0)}</span>
                  <span class="status-badge bad">Missing ${escapeHtml(comparison.missing_count ?? missing.length)}</span>
                  <span class="status-badge ${extra.length ? 'warn' : 'ok'}">Extra ${escapeHtml(comparison.extra_count ?? extra.length)}</span>
                </div>
              </div>
              <div class="summary-grid">
                <div class="metric"><div class="label">Reference total H</div><div class="value">${escapeHtml(referenceTotal)}</div></div>
                <div class="metric"><div class="label">Extracted total H</div><div class="value">${escapeHtml(extractedTotal)}</div></div>
                <div class="metric"><div class="label">Structure visible H</div><div class="value">${escapeHtml(visibleTarget)}</div></div>
                <div class="metric"><div class="label">Multiplicity matches</div><div class="value">${escapeHtml(comparison.multiplicity_match_count ?? 0)}</div></div>
                <div class="metric"><div class="label">Integration matches</div><div class="value">${escapeHtml(comparison.integration_match_count ?? 0)}</div></div>
                <div class="metric"><div class="label">Total shift Δ</div><div class="value">${escapeHtml(comparison.total_shift_delta_ppm ?? 0)} ppm</div></div>
              </div>
              ${notes.length ? `<div class="panel" style="margin-top:.8rem; background:var(--warn-bg);"><strong style="color:var(--warn);">Mismatch notes</strong><ul>${notes.map((note) => `<li>${escapeHtml(note)}</li>`).join('')}</ul></div>` : ''}
              ${matched.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Matched / shifted peaks</strong><table><thead><tr><th>Reference</th><th>Extracted</th><th>Δ ppm</th><th>Status</th><th>Multiplicity</th><th>Integration</th></tr></thead><tbody>${matched.map((item) => `<tr><td>${escapeHtml(item.reference_raw_text || formatSpectrumPeakSummary(item.reference_peak))}</td><td>${escapeHtml(formatSpectrumPeakSummary(item.extracted_peak))}</td><td>${escapeHtml(item.delta_ppm ?? 0)}</td><td><span class="status-badge ${item.status === 'matched' ? 'ok' : 'warn'}">${escapeHtml(item.status || 'matched')}</span></td><td>${item.multiplicity_match ? 'match' : 'diff'}</td><td>${item.integration_match ? 'match' : 'diff'}</td></tr>`).join('')}</tbody></table></div>` : '<div class="panel" style="margin-top:.8rem;"><strong>Matched / shifted peaks</strong><p class="muted small">No reference peaks matched the extracted list within the configured ppm windows.</p></div>'}
              ${missing.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Missing reference peaks</strong><ul>${missing.map((item) => `<li>${escapeHtml(item.reference_raw_text || formatSpectrumPeakSummary(item.reference_peak))}</li>`).join('')}</ul></div>` : ''}
              ${extra.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Extra extracted peaks</strong><ul>${extra.map((item) => `<li>${escapeHtml(formatSpectrumPeakSummary(item.extracted_peak))}</li>`).join('')}</ul></div>` : ''}
            </div>
          `;
        }

        function renderSpectrumDisplayEvidence(data) {
          const metadata = data?.metadata || {};
          const mode = metadata.display_mode || 'real';
          const evidenceMode = metadata.evidence_trace_mode || 'uploaded_intensity';
          const downsampling = metadata.preview_downsampling || {};
          const baselineVisual = metadata.baseline_lock_visual_only !== false;
          return `
            <div class="panel" style="margin-top:.8rem;">
              <strong>Spectrum display and evidence</strong>
              <div class="summary-grid">
                <div class="metric"><div class="label">Evidence trace</div><div class="value">${escapeHtml(evidenceMode)}</div></div>
                <div class="metric"><div class="label">Display mode</div><div class="value">${escapeHtml(mode)}</div></div>
                <div class="metric"><div class="label">Display gain</div><div class="value">${escapeHtml(metadata.display_gain ?? 1)}× axis</div></div>
                <div class="metric"><div class="label">Baseline lock</div><div class="value">${baselineVisual ? 'Visual only' : 'Off'}</div></div>
                <div class="metric"><div class="label">Downsampling</div><div class="value">${escapeHtml(downsampling.method || '—')}</div></div>
                <div class="metric"><div class="label">Raw state</div><div class="value">${metadata.original_spectrum_state?.preserved ? 'Preserved' : '—'}</div></div>
              </div>
              <p class="muted small" style="margin:.6rem 0 0;">The main plot uses real intensity values. Peak-height controls change only the y-axis range; peak picking and reports use the evidence trace.</p>
            </div>
          `;
        }

        function renderFidProcessingEvidence(data) {
          const metadata = data?.processing_metadata;
          if (!metadata) return '';
          const parameters = metadata.processing_parameters || {};
          const acquisition = metadata.acquisition_parameters || {};
          const qa = metadata.qa_diagnostics || {};
          const baseline = metadata.baseline_correction || {};
          const phase = metadata.phase_settings || {};
          const baselineQa = baseline.flatness_qa || data?.metadata?.baseline_flatness_qa || {};
          const originalQa = data?.metadata?.original_spectrum_state?.baseline_flatness_qa || {};
          const qaWarnings = Array.isArray(qa.warnings) ? qa.warnings : [];
          const filesFound = metadata.raw_dataset_files_found || {};
          const extracted = Array.isArray(metadata.extracted_peak_list) ? metadata.extracted_peak_list : [];
          const filesFoundText = Object.keys(filesFound).length
            ? Object.entries(filesFound).map(([name, present]) => `${name}: ${present ? 'yes' : 'no'}`).join(', ')
            : '—';
          const qaLabel = String(qa.quality_label || 'review');
          const qaBadgeClass = qaLabel === 'good' ? 'ok' : (qaLabel === 'failed' || qaLabel === 'poor' ? 'bad' : 'warn');
          return `
            <div class="panel" style="margin-top:.8rem;">
              <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                <strong>Raw FID processing evidence</strong>
                <span class="status-badge warn">Reviewer signoff required</span>
              </div>
              <div class="summary-grid">
                <div class="metric"><div class="label">Vendor</div><div class="value">${escapeHtml(metadata.vendor_format_detected || '—')}</div></div>
                <div class="metric"><div class="label">Preset</div><div class="value">${escapeHtml(metadata.selected_preset || parameters.selected_preset_label || 'Balanced')}</div></div>
                <div class="metric"><div class="label">Nucleus</div><div class="value">${escapeHtml(formatNucleusLabel(metadata.nucleus || '1H'))}</div></div>
                <div class="metric"><div class="label">Reference ppm</div><div class="value">${escapeHtml(metadata.reference_ppm ?? '—')}</div></div>
                <div class="metric"><div class="label">Digital filter</div><div class="value">${escapeHtml(metadata.digital_filter_correction_status || '—')}</div></div>
                <div class="metric"><div class="label">Group delay</div><div class="value">${metadata.group_delay_correction_applied ? 'Applied' : 'Not applied'}</div></div>
                <div class="metric"><div class="label">Phase mode</div><div class="value">${escapeHtml(phase.phase_mode || metadata.phase_mode || (metadata.automatic_phase_correction ? 'auto' : 'none'))}</div></div>
                <div class="metric"><div class="label">p0 / p1</div><div class="value">${escapeHtml(`${phase.phase_p0 ?? metadata.phase_p0 ?? '—'} / ${phase.phase_p1 ?? metadata.phase_p1 ?? '—'}`)}</div></div>
                <div class="metric"><div class="label">Phase score</div><div class="value">${escapeHtml(phase.phase_score ?? metadata.phase_score ?? '—')}</div></div>
                <div class="metric"><div class="label">Phase applied</div><div class="value">${Boolean(phase.phase_correction_applied ?? metadata.phase_correction_applied) ? 'Yes' : 'No'}</div></div>
                <div class="metric"><div class="label">Baseline</div><div class="value">${escapeHtml(baseline.method || baseline.baseline_correction || metadata.baseline_correction_mode || (metadata.automatic_baseline_correction ? 'bernstein' : 'Off'))}</div></div>
                <div class="metric"><div class="label">Baseline order</div><div class="value">${escapeHtml(baseline.order ?? baseline.baseline_order ?? metadata.baseline_order ?? '—')}</div></div>
                <div class="metric"><div class="label">Baseline applied</div><div class="value">${Boolean(baseline.correction_applied ?? metadata.baseline_correction_applied) ? 'Yes' : 'No'}</div></div>
                <div class="metric"><div class="label">Files found</div><div class="value">${escapeHtml(filesFoundText)}</div></div>
                <div class="metric"><div class="label">Zero fill</div><div class="value">${escapeHtml(metadata.zero_filling?.factor ?? parameters.zero_fill_factor ?? '—')}x</div></div>
	                <div class="metric"><div class="label">Line broadening</div><div class="value">${escapeHtml(metadata.line_broadening?.hz ?? parameters.line_broadening_hz ?? '—')} Hz</div></div>
	                <div class="metric"><div class="label">Apodization</div><div class="value">${escapeHtml(metadata.line_broadening?.apodization_mode ?? parameters.apodization_mode ?? '—')}</div></div>
                <div class="metric"><div class="label">Human review</div><div class="value">${escapeHtml(metadata.human_review_status || 'pending_review')}</div></div>
                <div class="metric"><div class="label">FID points</div><div class="value">${escapeHtml(acquisition.fid_points_after_group_delay ?? '—')}</div></div>
                <div class="metric"><div class="label">Extracted peaks</div><div class="value">${escapeHtml(extracted.length)}</div></div>
              </div>
              <div class="mono" style="margin-top:.75rem; white-space:pre-wrap;">${escapeHtml(extracted.map((peak) => formatSpectrumPeakSummary(peak)).join(', ') || 'No peaks inferred.')}</div>
            </div>
            ${baselineQa.label ? `<div class="panel" style="margin-top:.8rem;"><strong>Baseline flatness QA</strong><div class="summary-grid">
              <div class="metric"><div class="label">Review trace</div><div class="value">${escapeHtml(baselineQa.label || '—')}</div></div>
              <div class="metric"><div class="label">Score</div><div class="value">${escapeHtml(baselineQa.score ?? '—')}/100</div></div>
              <div class="metric"><div class="label">Mode</div><div class="value">${escapeHtml(baselineQa.mode || baseline.method || '—')}</div></div>
              <div class="metric"><div class="label">Curvature</div><div class="value">${escapeHtml(baselineQa.curvature_proxy ?? '—')}</div></div>
              <div class="metric"><div class="label">Offset ratio</div><div class="value">${escapeHtml(baselineQa.offset_ratio ?? '—')}</div></div>
              <div class="metric"><div class="label">Original state</div><div class="value">${escapeHtml(originalQa.label || 'preserved')}</div></div>
            </div></div>` : ''}
            <div class="panel" style="margin-top:.8rem;">
              <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
                <strong>FID QA diagnostics</strong>
                <span class="status-badge ${qaBadgeClass}">${escapeHtml(qaLabel)}</span>
              </div>
              <div class="summary-grid">
                <div class="metric"><div class="label">Quality score</div><div class="value">${escapeHtml(qa.quality_score ?? '—')}</div></div>
                <div class="metric"><div class="label">Dynamic range</div><div class="value">${escapeHtml(qa.dynamic_range ?? '—')}</div></div>
                <div class="metric"><div class="label">Noise estimate</div><div class="value">${escapeHtml(qa.noise_estimate ?? '—')}</div></div>
                <div class="metric"><div class="label">Baseline offset</div><div class="value">${escapeHtml(qa.baseline_offset_ratio ?? '—')}</div></div>
                <div class="metric"><div class="label">Clipping proxy</div><div class="value">${escapeHtml(qa.saturation_clipping_proxy ?? '—')}</div></div>
                <div class="metric"><div class="label">Point count</div><div class="value">${escapeHtml(qa.point_count ?? acquisition.fid_points_after_group_delay ?? '—')}</div></div>
              </div>
              ${qaWarnings.length ? `<ul>${qaWarnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join('')}</ul>` : '<p class="muted small">No QA warnings were raised.</p>'}
            </div>
          `;
        }

        function renderSpectrumRegionControls(plotId, data, options={}) {
          const nucleus = String(options.nucleus || data?.metadata?.nucleus || data?.nucleus || "").toUpperCase();
          if (nucleus === "13C") {
            return `
                <button class="ghost" onclick="focusSpectrumRegion(220, 160, '${plotId}')" title="Jump to carbonyl and carboxyl ¹³C signals.">Carbonyl</button>
                <button class="ghost" onclick="focusSpectrumRegion(165, 100, '${plotId}')" title="Jump to aromatic and alkene ¹³C signals.">Aromatic C</button>
                <button class="ghost" onclick="focusSpectrumRegion(105, 45, '${plotId}')" title="Jump to oxygen- or nitrogen-bearing carbon signals, including sugar-ring carbons.">O/N-bearing</button>
                <button class="ghost" onclick="focusSpectrumRegion(45, -5, '${plotId}')" title="Jump to aliphatic ¹³C signals.">Aliphatic C</button>
                <button class="ghost" onclick="focusSpectrumRegion(80, 75, '${plotId}')" title="Jump to common CDCl₃ solvent carbon region.">Solvent C</button>`;
          }
          return `
                <button class="ghost" onclick="focusSpectrumRegion(8.5, 6.0, '${plotId}')" title="Jump to the aromatic proton region.">Aromatic</button>
                <button class="ghost" onclick="focusSpectrumRegion(5.5, 4.3, '${plotId}')" title="Jump to water, HDO, or solvent-adjacent signals.">Water / solvent</button>
                <button class="ghost" onclick="focusSpectrumRegion(4.2, 0.0, '${plotId}')" title="Jump to the aliphatic and sugar-ring region.">Aliphatic</button>`;
        }

        function renderSpectrumPreview(data, options={}) {
          syncSpectrumReviewState(data);
          state.latestSpectrumPreview = data;
          const targetId = options.targetId || "spectrumPreviewBox";
          const plotId = options.plotId || (targetId === "spectrumPreviewBox" ? "spectrumInteractivePlot" : `${targetId}InteractivePlot`);
          state.latestSpectrumPlotId = plotId;
          const previewTitle = options.title || "Processed spectrum preview";
          const extraHtmlBefore = options.extraHtmlBefore || "";
          const extraHtmlAfter = options.extraHtmlAfter || "";
          state.spectrumPreviewContexts[plotId] = { data, options: { ...options, targetId, plotId, title: previewTitle } };
          const peaks = Array.isArray(data.inferred_peaks) ? data.inferred_peaks : [];
          const referencePeaks = Array.isArray(data.reference_peaks) ? data.reference_peaks : [];
          const warnings = Array.isArray(data.warnings) ? data.warnings : [];
          const sourceMode = data.source_mode === 'peak_table' ? 'peak table' : (data.source_mode || 'unknown');
          const scaleLabel = formatSpectrumVerticalScaleLabel(state.spectrumVerticalScale);
          const meterFill = Math.round(getSpectrumVerticalMeterFillPercent() * 100);
          const scaleFillId = `${plotId}ScaleFill`;
          const scaleValueId = `${plotId}ScaleValue`;
          const referenceText = data.reference_nmr_text_normalized || '';
          const reviewedText = getSpectrumReviewedNmrText(data);
          const hasOriginalSpectrumState = Boolean(getOriginalSpectrumState(data));
          const traceMode = getSpectrumTraceMode(data, plotId);
          const target = el(targetId);
          if (!target) return;
          const plotHtml = targetId === "spectrumPreviewBox" && plotId === "spectrumInteractivePlot"
            ? '<div id="spectrumInteractivePlot" class="spectrum-plot"></div>'
            : `<div id="${escapeHtml(plotId)}" class="spectrum-plot"></div>`;
          target.innerHTML = `
            ${extraHtmlBefore}
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>${escapeHtml(previewTitle)}</strong>
              <span class="status-badge ${data.source_mode === 'peak_table' ? 'ok' : 'warn'}">${escapeHtml(sourceMode)}</span>
            </div>
            <div class="summary-grid">
              <div class="metric"><div class="label">Format</div><div class="value">${escapeHtml(data.format_detected || '—')}</div></div>
              <div class="metric"><div class="label">Points</div><div class="value">${escapeHtml(data.point_count ?? '—')}</div></div>
              <div class="metric"><div class="label">Inferred peaks</div><div class="value">${escapeHtml(peaks.length)}</div></div>
              <div class="metric"><div class="label">Reference peaks</div><div class="value">${escapeHtml(referencePeaks.length)}</div></div>
            </div>
            <div class="spectrum-shell">
              <div class="spectrum-stage">
                ${plotHtml}
                <div
                  class="spectrum-hover-rail"
                  onwheel="setActiveSpectrumPlot('${plotId}'); adjustSpectrumVerticalScaleFromWheel(event)"
                  ondblclick="resetSpectrumPeakView('${plotId}')"
                  title="Scroll here to increase or decrease peak height. Double-click to reset."
                >
                  <div class="spectrum-gain-box">
                    <button type="button" class="spectrum-gain-btn" onclick="stepSpectrumVerticalScale(2, '${plotId}')" aria-label="Increase peak height">+</button>
                    <div class="spectrum-gain-meter" aria-hidden="true">
                      <div id="${escapeHtml(scaleFillId)}" class="spectrum-gain-fill" style="height:${meterFill}%;"></div>
                    </div>
                    <button type="button" id="${escapeHtml(scaleValueId)}" class="spectrum-gain-btn spectrum-gain-readout" onclick="resetSpectrumPeakView('${plotId}')" aria-label="Reset peak height">${escapeHtml(scaleLabel)}</button>
                    <div class="spectrum-gain-hint">wheel to lift<br />short peaks</div>
                    <button type="button" class="spectrum-gain-btn" onclick="stepSpectrumVerticalScale(-2, '${plotId}')" aria-label="Decrease peak height">−</button>
                  </div>
                </div>
              </div>
              <div class="spectrum-toolbar">
                <label class="small muted" style="display:flex; align-items:center; gap:.45rem;" title="Changes only the y-axis range. The spectrum intensities are not recalculated.">
                  Vertical gain
                  <input id="${escapeHtml(plotId)}GainSlider" type="range" min="1" max="512" step="1" value="${escapeHtml(String(Math.min(512, Math.max(1, Number(state.spectrumVerticalScale || 1)))))}" oninput="setSpectrumVerticalScale(this.value, '${plotId}')" />
                </label>
                <button class="secondary" onclick="zoomSpectrum(0.55, '${plotId}')" title="Zoom into the current ppm window without changing peak data.">Zoom in</button>
                <button class="ghost" onclick="zoomSpectrum(1.8, '${plotId}')" title="Show a wider ppm window.">Zoom out</button>
                <button class="ghost" onclick="resetSpectrumView('${plotId}')" title="Return to the full reversed NMR ppm axis.">Reset view</button>
                <button class="ghost" onclick="shiftSpectrum('left', '${plotId}')" title="Move the visible ppm window toward higher ppm.">← Move left</button>
                <button class="ghost" onclick="shiftSpectrum('right', '${plotId}')" title="Move the visible ppm window toward lower ppm.">Move right →</button>
                <button id="${escapeHtml(plotId)}PanButton" class="${state.spectrumDragMode === 'pan' ? 'secondary' : 'ghost'}" onclick="setSpectrumDragMode('pan', '${plotId}')" title="Drag the spectrum to pan across ppm.">Pan mode</button>
                <button id="${escapeHtml(plotId)}ZoomButton" class="${state.spectrumDragMode === 'zoom' ? 'secondary' : 'ghost'}" onclick="setSpectrumDragMode('zoom', '${plotId}')" title="Drag a box over the plot to zoom into that region.">Zoom mode</button>
                ${hasOriginalSpectrumState ? `<button id="${escapeHtml(plotId)}RealViewButton" class="${traceMode === 'review' ? 'secondary' : 'ghost'}" onclick="setSpectrumTraceMode('review', '${plotId}')" title="Show the real evidence trace used for peak picking and reviewer decisions.">Real view</button><button id="${escapeHtml(plotId)}OriginalViewButton" class="${traceMode === 'original' ? 'secondary' : 'ghost'}" onclick="setSpectrumTraceMode('original', '${plotId}')" title="Show the preserved uploaded spectrum state.">Original upload</button>` : ''}
                ${renderSpectrumRegionControls(plotId, data, options)}
                <button id="${escapeHtml(plotId)}TallPeakClipButton" class="${state.spectrumTallPeakClip ? 'secondary' : 'ghost'}" onclick="toggleSpectrumTallPeakClip('${plotId}')" title="Limit the y-axis upper range so weak peaks can be inspected. Data values are not clipped.">Tall peak clipping</button>
                <button id="${escapeHtml(plotId)}WeakPeakMagnifierButton" class="${state.spectrumWeakPeakMagnifier ? 'secondary' : 'ghost'}" onclick="toggleSpectrumWeakPeakMagnifier('${plotId}')" title="Show a separate inset with relative weak-peak contrast. The main trace remains real.">Weak peak magnifier</button>
                <button id="${escapeHtml(plotId)}ZeroLineButton" class="${state.spectrumZeroLine ? 'secondary' : 'ghost'}" onclick="toggleSpectrumZeroLine('${plotId}')" title="Keep the y=0 baseline visible and stable as a visual guide only.">Baseline zero-line</button>
                <button id="${escapeHtml(plotId)}PeaksButton" class="${state.spectrumShowPeaks ? 'ghost' : 'secondary'}" onclick="toggleSpectrumPeaks('${plotId}')" title="Show or hide detected, reference, and impurity markers.">${state.spectrumShowPeaks ? 'Hide peaks' : 'Show peaks'}</button>
              </div>
              <div class="panel spectrum-inline-note">
                <div class="small muted">Evidence intensities stay preserved. The ¹H viewer equalizes the displayed baseline to y=0, and peak height controls adjust the y-axis only.</div>
                <button class="ghost" onclick="resetSpectrumPeakView('${plotId}')">Reset peak height</button>
              </div>
            </div>
            ${renderSpectrumDisplayEvidence(data)}
            ${renderFidProcessingEvidence(data)}
            <div id="${escapeHtml(plotId)}ReviewerPanel">${renderSpectrumReviewerPanel(data, plotId)}</div>
            <div class="panel" style="margin-top:.8rem;">
              <strong>Peak list used for analysis</strong>
              <div id="${escapeHtml(plotId)}ReviewedPeakList" class="mono" style="margin-top:.45rem; white-space:pre-wrap;">${escapeHtml(reviewedText || 'No peak list generated yet.')}</div>
            </div>
            ${referenceText ? `<div class="panel" style="margin-top:.8rem;"><strong>Normalized reference ¹H NMR text</strong><div class="mono" style="margin-top:.45rem; white-space:pre-wrap;">${escapeHtml(formatNmrLabelText(referenceText))}</div>${referencePeaks.length ? `<div class="summary-grid" style="margin-top:.75rem;">${referencePeaks.map((peak) => `<div class="metric"><div class="label">Reference peak</div><div class="value">${escapeHtml(formatSpectrumPeakSummary(peak))}</div></div>`).join('')}</div>` : ''}</div>` : ''}
            ${renderSpectrumComparison(data)}
            ${warnings.length ? `<div class="panel" style="margin-top:.8rem;"><strong>Warnings</strong><ul>${warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join('')}</ul></div>` : ''}
            ${extraHtmlAfter}
          `;
          renderSpectrumGainControl(plotId);
          renderInteractiveSpectrumPlot(data, plotId);
        }

        async function previewSpectrum() {
          try {
            const file = el("spectrumFile").files[0];
            if (!file) throw new Error("Choose a processed spectrum file first.");
            const formData = new FormData();
            formData.append("file", file);
            const smiles = el("smiles").value.trim();
            const solvent = el("solvent").value.trim();
            const frequency = el("frequencyMHz").value.trim();
            const reference = el("referencePPM").value.trim();
            const referenceNmrText = el("referenceNmrText").value.trim();
            const maskSolventRegions = Boolean(el("maskSolventRegions").checked);
            if (smiles) formData.append("smiles", smiles);
            if (solvent) formData.append("solvent", solvent);
            if (frequency) formData.append("frequency_mhz", frequency);
            if (reference) formData.append("reference_ppm", reference);
            if (referenceNmrText) formData.append("reference_nmr_text", referenceNmrText);
            formData.append("mask_solvent_regions", maskSolventRegions ? "true" : "false");
            formData.append("display_mode", el("processedDisplayMode")?.value || "real");
            formData.append("vertical_gain", "1");
            formData.append("processed_baseline_correction", el("processedBaselineCorrection")?.value || "bernstein");
            formData.append("processed_baseline_order", el("processedBaselineOrder")?.value || "3");
            const data = await api("/spectrum/preview", { method: "POST", body: formData });
            setJson(data);
            renderSpectrumPreview(data);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            el("spectrumPreviewBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function useSpectrumPeaks() {
          if (!state.latestSpectrumPreview) {
            setJson({ error: "Preview a processed spectrum first." });
            return;
          }
          const reviewedText = getSpectrumReviewedNmrText(state.latestSpectrumPreview);
          if (!reviewedText) {
            setJson({ error: "All extracted peaks are currently excluded." });
            return;
          }
          el("nmrText").value = reviewedText;
          clearValidationState();
          showSection("analyze");
        }

        async function analyzeSpectrum() {
          try {
            const file = el("spectrumFile").files[0];
            if (!file) throw new Error("Choose a processed spectrum file first.");
            const formData = new FormData();
            formData.append("file", file);
            formData.append("smiles", el("smiles").value.trim());
            const sampleId = el("sampleId").value.trim();
            const solvent = el("solvent").value.trim();
            const frequency = el("frequencyMHz").value.trim();
            const reference = el("referencePPM").value.trim();
            const referenceNmrText = el("referenceNmrText").value.trim();
            const maskSolventRegions = Boolean(el("maskSolventRegions").checked);
            if (
              state.latestSpectrumPreview
              && state.latestSpectrumPreview.filename === file.name
              && hasSpectrumManualReviewDecisions(state.latestSpectrumPreview)
            ) {
              const reviewedText = getSpectrumReviewedNmrText(state.latestSpectrumPreview);
              if (!reviewedText) throw new Error("All extracted peaks are currently excluded. Accept at least one peak before analyzing.");
              formData.append("manual_nmr_text", reviewedText);
            }
            if (sampleId) formData.append("sample_id", sampleId);
            if (solvent) formData.append("solvent", solvent);
            if (frequency) formData.append("frequency_mhz", frequency);
            if (reference) formData.append("reference_ppm", reference);
            if (referenceNmrText) formData.append("reference_nmr_text", referenceNmrText);
            formData.append("mask_solvent_regions", maskSolventRegions ? "true" : "false");
            formData.append("display_mode", el("processedDisplayMode")?.value || "real");
            formData.append("vertical_gain", "1");
            formData.append("processed_baseline_correction", el("processedBaselineCorrection")?.value || "bernstein");
            formData.append("processed_baseline_order", el("processedBaselineOrder")?.value || "3");
            const data = await api("/spectrum/analyze", { method: "POST", body: formData });
            setJson(data);
            if (data.preview) renderSpectrumPreview(data.preview);
            if (data.generated_inputs && data.generated_inputs.nmr_text) {
              el("nmrText").value = data.generated_inputs.nmr_text;
            }
            if (data.analysis) {
              renderAnalysis(data.analysis);
              showSection("analyze");
              await loadHistory().catch(() => null);
            }
          } catch (err) {
            setJson({ error: String(err.message || err) });
            setResultBadge("Spectrum analysis failed", "bad");
            el("readableOutput").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function getRawFidArchiveId() {
          return state.rawFidArchive?.raw_archive_id || state.rawFidArchive?.sha256 || "";
        }

        function renderRawFidVaultStatus(archive, detail=null) {
          const box = el("fidVaultStatus");
          if (!box) return;
          if (!archive) {
            box.innerHTML = "No immutable raw FID archive uploaded yet.";
            return;
          }
          const metadata = archive.acquisition_metadata || {};
          const metadataRows = Object.entries(metadata).slice(0, 8).map(([key, value]) => (
            `<div><strong>${escapeHtml(key)}:</strong> ${escapeHtml(value)}</div>`
          )).join("");
          const integrity = detail?.integrity;
          box.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:.8rem; align-items:center; flex-wrap:wrap;">
              <strong>Immutable source stored</strong>
              <span class="status-badge ok">Locked</span>
            </div>
            <div class="summary-grid" style="margin-top:.55rem;">
              <div class="metric"><div class="label">SHA-256</div><div class="value">${escapeHtml(archive.sha256 || archive.raw_archive_id || "—")}</div></div>
              <div class="metric"><div class="label">Vendor</div><div class="value">${escapeHtml(archive.vendor_detected || "unknown")}</div></div>
              <div class="metric"><div class="label">Dataset root</div><div class="value">${escapeHtml(archive.dataset_root || "—")}</div></div>
              <div class="metric"><div class="label">Integrity</div><div class="value">${integrity ? (integrity.sha256_verified ? "verified" : "check failed") : "stored"}</div></div>
            </div>
            <div class="small muted" style="margin-top:.55rem;">${metadataRows || "No acquisition metadata extracted."}</div>
          `;
        }

        function resetRawFidVaultSelection() {
          state.rawFidArchive = null;
          state.latestRawFidPreview = null;
          renderRawFidVaultStatus(null);
          const previewBox = el("fidPreviewBox");
          if (previewBox) previewBox.innerHTML = "No raw FID preview yet.";
          const status = el("fidExportStatus");
          if (status) status.textContent = "Export package includes manifest.json with SHA-256 hashes for the original archive and derived evidence files.";
        }

        async function uploadRawFidArchive() {
          try {
            const file = el("fidFile").files[0];
            if (!file) throw new Error("Choose a .zip, .tar.gz, or .tgz raw FID archive first.");
            const formData = new FormData();
            formData.append("file", file);
            const archive = await api("/raw-fid/upload", { method: "POST", body: formData });
            state.rawFidArchive = archive;
            renderRawFidVaultStatus(archive);
            setJson(archive);
            return archive;
          } catch (err) {
            setJson({ error: String(err.message || err) });
            const box = el("fidVaultStatus");
            if (box) box.innerHTML = `<span style="color:var(--danger);">${escapeHtml(err.message || err)}</span>`;
            throw err;
          }
        }

        async function ensureRawFidArchiveUploaded() {
          if (getRawFidArchiveId()) return state.rawFidArchive;
          return await uploadRawFidArchive();
        }

        async function refreshRawFidArchiveDetail() {
          const archiveId = getRawFidArchiveId();
          if (!archiveId) return null;
          const detail = await api(`/raw-fid/${encodeURIComponent(archiveId)}`, { method: "GET" });
          if (detail.archive) {
            state.rawFidArchive = detail.archive;
            renderRawFidVaultStatus(detail.archive, detail);
          }
          return detail;
        }

        async function exportRawFidPackage() {
          try {
            await ensureRawFidArchiveUploaded();
            const archiveId = getRawFidArchiveId();
            if (!archiveId) throw new Error("Upload and lock raw FID data before export.");
            openAuthedPath(`/raw-fid/${encodeURIComponent(archiveId)}/export`);
            const status = el("fidExportStatus");
            if (status) {
              status.innerHTML = `Export requested for <strong>${escapeHtml(archiveId)}</strong>. The package contains manifest.json, raw/original_archive.*, analysis/processing_recipe.json, analysis/peak_list.csv, evidence report JSON, and audit_trail.json.`;
            }
            await refreshRawFidArchiveDetail().catch(() => null);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            const status = el("fidExportStatus");
            if (status) status.innerHTML = `<span style="color:var(--danger);">${escapeHtml(err.message || err)}</span>`;
          }
        }

        function appendRawFidFormFields(formData, { includeSmiles=false } = {}) {
          const sampleId = el("sampleId").value.trim();
          const solvent = (el("fidSolvent")?.value || el("solvent").value || "").trim();
          const nucleus = el("fidNucleus").value.trim() || "1H";
	          const selectedPreset = el("fidProcessingPreset")?.value || "balanced";
	          const reference = el("fidReferencePPM").value.trim();
	          const zeroFillFactor = el("fidZeroFillFactor").value.trim();
	          const apodizationMode = el("fidApodizationMode")?.value || "exponential";
	          const lineBroadening = el("fidLineBroadeningHz").value.trim();
          const peakSensitivity = el("fidPeakSensitivity").value.trim();
          const referenceNmrText = el("nmrText").value.trim();
          if (includeSmiles) formData.append("smiles", el("smiles").value.trim());
          if (sampleId) formData.append("sample_id", sampleId);
          if (solvent) formData.append("solvent", solvent);
          if (nucleus) formData.append("nucleus", nucleus);
          formData.append("selected_preset", selectedPreset);
	          if (reference) formData.append("reference_ppm", reference);
	          if (referenceNmrText) formData.append("reference_nmr_text", referenceNmrText);
	          if (zeroFillFactor) formData.append("zero_fill_factor", zeroFillFactor);
	          formData.append("apodization_mode", apodizationMode);
	          if (lineBroadening) formData.append("line_broadening_hz", lineBroadening);
          if (peakSensitivity) formData.append("peak_sensitivity", peakSensitivity);
          const phaseMode = el("fidPhaseMode")?.value || "auto";
          const phaseP0 = el("fidPhaseP0")?.value || "0.0";
          const phaseP1 = el("fidPhaseP1")?.value || "0.0";
          const baselineMode = el("fidBaselineCorrection")?.value || "bernstein";
          const baselineOrder = el("fidBaselineOrder")?.value || "3";
          const displayMode = el("fidDisplayMode")?.value || "real";
          formData.append("apply_group_delay", el("fidApplyGroupDelay").checked ? "true" : "false");
          formData.append("auto_phase", phaseMode === "none" ? "false" : "true");
          formData.append("phase_mode", phaseMode);
          formData.append("phase_p0", phaseP0);
          formData.append("phase_p1", phaseP1);
          formData.append("auto_baseline", ["none", "preserve"].includes(baselineMode) ? "false" : "true");
          formData.append("baseline_correction", baselineMode);
          formData.append("baseline_order", baselineOrder);
          formData.append("mask_solvent_regions", el("fidMaskSolventRegions").checked ? "true" : "false");
          formData.append("display_mode", displayMode);
          formData.append("vertical_gain", "1");
          if (state.selectedWorkspaceSampleId) formData.append("workspace_sample_record_id", String(state.selectedWorkspaceSampleId));
          if (state.selectedProjectId) formData.append("workspace_project_id", String(state.selectedProjectId));
        }

        async function previewRawFid() {
          try {
            await ensureRawFidArchiveUploaded();
            const archiveId = getRawFidArchiveId();
            const formData = new FormData();
            const smiles = el("smiles").value.trim();
            if (smiles) formData.append("smiles", smiles);
            appendRawFidFormFields(formData);
            const data = await api(`/raw-fid/${encodeURIComponent(archiveId)}/preview`, { method: "POST", body: formData });
            state.latestRawFidPreview = data;
            setJson(data);
            renderSpectrumPreview(data, { targetId: "fidPreviewBox", title: "Raw FID immutable-vault preview" });
            await loadFidRuns().catch(() => null);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            el("fidPreviewBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        async function applyRawFidPhaseCorrection() {
          const phaseControl = el("fidPhaseMode");
          if (phaseControl) phaseControl.value = "auto";
          markFidPresetCustom();
          await previewRawFid();
        }

        async function applyRawFidBaselineCorrection() {
          const baselineControl = el("fidBaselineCorrection");
          if (baselineControl) baselineControl.value = "bernstein";
          if (el("fidBaselineOrder")) el("fidBaselineOrder").value = "3";
          markFidPresetCustom();
          await previewRawFid();
        }

        function useRawFidPeaks() {
          if (!state.latestRawFidPreview) {
            setJson({ error: "Process a raw FID preview first." });
            return;
          }
          const reviewedText = getSpectrumReviewedNmrText(state.latestRawFidPreview);
          if (!reviewedText) {
            setJson({ error: "All extracted peaks are currently excluded." });
            return;
          }
          el("nmrText").value = reviewedText;
          setAnalysisInputMethod("paste");
          clearValidationState();
          showSection("analyze");
        }

        async function analyzeRawFid() {
          try {
            await ensureRawFidArchiveUploaded();
            const archiveId = getRawFidArchiveId();
            const formData = new FormData();
            appendRawFidFormFields(formData, { includeSmiles: true });
            if (
              state.latestRawFidPreview
              && hasSpectrumManualReviewDecisions(state.latestRawFidPreview)
            ) {
              const reviewedText = getSpectrumReviewedNmrText(state.latestRawFidPreview);
              if (!reviewedText) throw new Error("All extracted peaks are currently excluded. Accept at least one peak before analyzing.");
              formData.append("manual_nmr_text", reviewedText);
            }
            const data = await api(`/raw-fid/${encodeURIComponent(archiveId)}/process`, { method: "POST", body: formData });
            state.latestRawFidPreview = data.preview || null;
            setJson(data);
            if (data.preview) renderSpectrumPreview(data.preview, { targetId: "fidPreviewBox", title: "Raw FID immutable-vault preview" });
            if (data.generated_inputs && data.generated_inputs.nmr_text) {
              el("nmrText").value = data.generated_inputs.nmr_text;
            }
            if (data.analysis) {
              renderAnalysis(data.analysis);
              showSection("analyze");
              await loadHistory().catch(() => null);
              await loadFidRuns().catch(() => null);
              if (state.selectedProjectId) await loadSelectedProjectSamples().catch(() => null);
            }
          } catch (err) {
            setJson({ error: String(err.message || err) });
            setResultBadge("Raw FID analysis failed", "bad");
            el("readableOutput").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        async function validateInput() {
          clearValidationState();
          try {
            const data = await api("/analyze/validate", { method: "POST", body: JSON.stringify(payload()) });
            setJson(data);
            renderValidation(data);
            showSection("analyze");
          } catch (err) {
            setValidationBadge("Validation failed", "bad");
            el("validationSummary").innerHTML = `<strong style="color:var(--danger);">Request failed</strong><p class="muted small">${escapeHtml(err.message || err)}</p>`;
            setJson({ error: String(err.message || err) });
          }
        }

        async function analyzeInput() {
          if (!state.validationOk) { setJson({ error: "Run validation successfully before analysis." }); return; }
          try {
            const data = await api("/analyze", { method: "POST", body: JSON.stringify(payload()) });
            setJson(data);
            renderAnalysis(data);
            showSection("analyze");
            await loadHistory().catch(() => null);
          } catch (err) {
            setResultBadge("Analysis failed", "bad");
            el("readableOutput").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
            setJson({ error: String(err.message || err) });
          }
        }

        async function submitJob() {
          try {
            if (!state.validationOk) throw new Error("Run validation first and fix any SMILES / ¹H NMR mismatch before submitting a job.");
            const data = await api("/jobs/submit", { method: "POST", body: JSON.stringify({ job_name: el("jobName").value.trim() || null, items: [payload()] }) });
            setJson(data);
            showSection("jobs");
            loadJobs().catch(() => null);
          } catch (err) { setJson({ error: String(err.message || err) }); }
        }

        async function uploadJob() {
          try {
            const file = el("uploadFile").files[0];
            if (!file) throw new Error("Choose a CSV or JSON file first.");
            const formData = new FormData();
            formData.append("file", file);
            const jobName = el("jobName").value.trim();
            if (jobName) formData.append("job_name", jobName);
            const data = await api("/jobs/upload", { method: "POST", body: formData });
            setJson(data);
            showSection("jobs");
            el("queueStatusBox").innerHTML = `<strong>Batch submitted</strong><div class="small muted">The uploaded file was accepted as a batch job. Use Refresh jobs to monitor its status and open Items once it completes.</div>`;
            loadJobs().catch(() => null);
          } catch (err) {
            setJson({ error: String(err.message || err) });
            el("queueStatusBox").innerHTML = `<span style="color:var(--danger);">${escapeHtml(err.message || err)}</span><div class="small muted" style="margin-top:.45rem;">Batch uploads expect CSV/JSON records with recognizable SMILES and ¹H NMR text fields.</div>`;
          }
        }

        async function loadQueueStatus() {
          try {
            const data = await api("/queue/status");
            setJson(data);
            el("queueStatusBox").innerHTML = `<strong>Queue status</strong><div class="small muted">Connected: ${escapeHtml(data.connected ?? "—")} · Worker running: ${escapeHtml(data.worker_running ?? "—")} · Backend: ${escapeHtml(data.backend ?? "—")}</div>`;
          } catch (err) {
            setJson({ error: String(err.message || err) });
            el("queueStatusBox").innerHTML = `<span style="color:var(--danger);">${escapeHtml(err.message || err)}</span>`;
          }
        }

        async function loadJobs() {
          try { const data = await api("/jobs"); setJson(data); renderJobs(Array.isArray(data) ? data : (data.items || [])); }
          catch (err) { setJson({ error: String(err.message || err) }); el("jobsBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`; }
        }

        async function viewJobItems(jobId) {
          try { const data = await api(`/jobs/${jobId}/items`); setJson(data); }
          catch (err) { setJson({ error: String(err.message || err) }); }
        }

        async function loadHistory() {
          try {
            const data = await api("/history?limit=10");
            const items = Array.isArray(data) ? data : [];
            setJson(data);
            renderHistory(items);
            return items;
          }
          catch (err) { setJson({ error: String(err.message || err) }); el("historyBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`; }
        }

        async function loadFidRuns() {
          try {
            const data = await api("/fid/runs?limit=20");
            const items = Array.isArray(data) ? data : [];
            setJson(data);
            renderFidRuns(items);
            return items;
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("fidRunHistoryBox")) el("fidRunHistoryBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
            return [];
          }
        }

        async function openFidRun(runId) {
          try {
            let run = getFidRunById(runId);
            if (!run) {
              run = await api(`/fid/runs/${runId}`);
            }
            if (!run || !run.preview) throw new Error("FID run preview is not available.");
            state.latestRawFidPreview = run.preview;
            if (run.analysis_id) setLatestAnalysisId(run.analysis_id);
            setJson(run);
            renderSpectrumPreview(run.preview, { targetId: "fidPreviewBox", title: `Raw FID run #${run.id}` });
            showSection("analyze");
          } catch (err) {
            setJson({ error: String(err.message || err) });
            if (el("fidPreviewBox")) el("fidPreviewBox").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        function compareSelectedFidRuns() {
          renderFidRunComparison(getSelectedFidRuns());
        }

        function openBestFidRun() {
          const candidates = getSelectedFidRuns().length ? getSelectedFidRuns() : state.fidRuns;
          if (!candidates.length) {
            setJson({ error: "Refresh FID runs first." });
            return;
          }
          const best = [...candidates].sort((a, b) => scoreFidRun(b) - scoreFidRun(a))[0];
          renderFidRunComparison(candidates.length >= 2 ? candidates : []);
          openFidRun(best.id);
        }

        async function approveFidRun(runId) {
          try {
            const data = await api(`/fid/runs/${runId}/approve`, { method: "POST", body: JSON.stringify({ comment: "Approved in Raw FID panel" }) });
            setJson(data);
            await loadFidRuns();
          } catch (err) { setJson({ error: String(err.message || err) }); }
        }

        async function rejectFidRun(runId) {
          try {
            const data = await api(`/fid/runs/${runId}/reject`, { method: "POST", body: JSON.stringify({ comment: "Rejected in Raw FID panel" }) });
            setJson(data);
            await loadFidRuns();
          } catch (err) { setJson({ error: String(err.message || err) }); }
        }

        async function loadMetrics() {
          try {
            const data = await api("/metrics/summary");
            setJson(data);
            renderMetricCards(data);
          } catch (err) {
            const msg = String(err.message || err);
            setJson({ error: msg });
            el("dashboardNotes").innerHTML = `<span style="color:var(--danger);">${escapeHtml(msg)}</span><p class="muted small" style="margin-top:.45rem;">Refresh metrics reloads the latest admin dashboard counters from the server. If this fails, the current account probably is not recognized as an admin yet.</p>`;
          }
        }

        async function loadAudit() {
          try { const data = await api("/audit"); setJson(data); renderAudit(data); }
          catch (err) { setJson({ error: String(err.message || err) }); el("auditPreview").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`; }
        }

        async function loadReviews() {
          try { const data = await api("/reviews"); setJson(data); renderReviewQueue(data); }
          catch (err) { setJson({ error: String(err.message || err) }); el("reviewQueue").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`; }
        }

        async function approveReview(analysisId, options={}) {
          try {
            const data = await api(`/reviews/${analysisId}/approve`, { method: "POST", body: JSON.stringify({ comment: "Approved in UI" }) });
            setJson(data);
            loadReviews().catch(() => null);
            if (options.refreshReport) await loadEvidenceReportJson(analysisId);
          }
          catch (err) { setJson({ error: String(err.message || err) }); }
        }

        async function rejectReview(analysisId, options={}) {
          try {
            const data = await api(`/reviews/${analysisId}/reject`, { method: "POST", body: JSON.stringify({ comment: "Rejected in UI" }) });
            setJson(data);
            loadReviews().catch(() => null);
            if (options.refreshReport) await loadEvidenceReportJson(analysisId);
          }
          catch (err) { setJson({ error: String(err.message || err) }); }
        }

        async function overrideReview(analysisId, options={}) {
          const finalLabel = prompt("Enter override label:");
          if (!finalLabel) return;
          const comment = prompt("Enter reviewer comment:") || "";
          try {
            const data = await api(`/reviews/${analysisId}/override`, { method: "POST", body: JSON.stringify({ final_label: finalLabel, comment }) });
            setJson(data);
            loadReviews().catch(() => null);
            if (options.refreshReport) await loadEvidenceReportJson(analysisId);
          }
          catch (err) { setJson({ error: String(err.message || err) }); }
        }

        async function loadReviewDecisions(analysisId) {
          try { const data = await api(`/reviews/${analysisId}/decisions`); setJson(data); }
          catch (err) { setJson({ error: String(err.message || err) }); }
        }

        async function loadAdminUsers() {
          try { const data = await api("/admin/users"); setJson(data); renderAdminUsers(data); }
          catch (err) { setJson({ error: String(err.message || err) }); el("adminUsers").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`; }
        }

        async function promoteUser(userId) {
          try { const data = await api(`/admin/users/${userId}/promote`, { method: "POST", body: JSON.stringify({}) }); setJson(data); loadAdminUsers().catch(() => null); }
          catch (err) { setJson({ error: String(err.message || err) }); }
        }

        async function demoteUser(userId) {
          try { const data = await api(`/admin/users/${userId}/demote`, { method: "POST", body: JSON.stringify({}) }); setJson(data); loadAdminUsers().catch(() => null); }
          catch (err) { setJson({ error: String(err.message || err) }); }
        }

        async function loadSystem() {
          try {
            const data = await api("/admin/system");
            setJson(data);
            el("adminSystem").innerHTML = `<div class="summary-grid"><div class="metric"><div class="label">Users</div><div class="value">${data.total_users ?? "—"}</div></div><div class="metric"><div class="label">Admins</div><div class="value">${data.total_admins ?? "—"}</div></div><div class="metric"><div class="label">Analyses</div><div class="value">${data.total_analyses ?? "—"}</div></div><div class="metric"><div class="label">Jobs</div><div class="value">${data.total_jobs ?? "—"}</div></div></div>`;
          } catch (err) {
            setJson({ error: String(err.message || err) });
            el("adminSystem").innerHTML = `<p style="color:var(--danger);">${escapeHtml(err.message || err)}</p>`;
          }
        }

        document.addEventListener("keydown", (event) => {
          if (String(event.key || "") === "Escape") {
            hideSpectrumContextMenu();
          }
          const target = event.target;
          const tagName = target && target.tagName ? String(target.tagName).toUpperCase() : "";
          if (tagName === "INPUT" || tagName === "TEXTAREA" || tagName === "SELECT") return;
          if ((event.ctrlKey || event.metaKey) && !event.shiftKey && String(event.key || "").toLowerCase() === "z") {
            if (!state.latestSpectrumPreview) return;
            event.preventDefault();
            undoSpectrumPeakDecision();
          }
        });

        document.addEventListener("click", (event) => {
          const menu = el("spectrumContextMenu");
          if (menu && !menu.contains(event.target)) hideSpectrumContextMenu();
        });

        document.addEventListener("DOMContentLoaded", async () => {
          installClearOnFocus();
          installHelpfulTooltips();
          installFidPresetControlHandlers();
          installNmr2dContextHandlers();
          loadFidPresets().catch(() => null);
          persistVerificationToken(state.verificationToken);
          captureAnalysisFormDefaults();
          setAnalysisInputMethod(state.defaultFormValues?.analysisInputMethod || "paste");
          setCarbon13InputMethod(state.defaultFormValues?.carbon13InputMethod || "text");
          const maskCheckbox = el("maskSolventRegions");
          const fidMaskCheckbox = el("fidMaskSolventRegions");
          const solventSelect = el("solvent");
          const fidSolventSelect = el("fidSolvent");
          if (maskCheckbox) {
            maskCheckbox.dataset.userChanged = "false";
            maskCheckbox.addEventListener("change", () => {
              maskCheckbox.dataset.userChanged = "true";
            });
          }
          if (maskCheckbox && solventSelect) {
            const syncMaskSolventRegions = () => {
              if (maskCheckbox.dataset.userChanged === "true") return;
              maskCheckbox.checked = Boolean(solventSelect.value);
              if (fidMaskCheckbox) fidMaskCheckbox.checked = Boolean(solventSelect.value);
              if (fidSolventSelect) fidSolventSelect.value = solventSelect.value;
            };
            solventSelect.addEventListener("change", syncMaskSolventRegions);
            if (fidSolventSelect) {
              fidSolventSelect.addEventListener("change", () => {
                solventSelect.value = fidSolventSelect.value;
              });
            }
            syncMaskSolventRegions();
          }
          clearValidationState();
          setResultBadge("No analysis yet", "warn");
          showAuthScreen();
          if (state.token) {
            try {
              await whoAmI();
              if (state.me) {
                showAppShell();
                loadMetrics().catch(() => null);
                loadProjects().catch(() => null);
                loadJobs().catch(() => null);
                loadHistory().catch(() => null);
                loadFidRuns().catch(() => null);
              } else {
                clearUserSessionState({ resetInputs: true });
                persistToken("");
                setAuthMessage("Previous session expired. Please sign in again.", false);
              }
            } catch {
              clearUserSessionState({ resetInputs: true });
              persistToken("");
              setAuthMessage("Previous session expired. Please sign in again.", false);
            }
          }
        });
      </script>
    </body>
    </html>
    """
    return (
        html.replace("__SOLVENT_OPTIONS__", solvent_options)
        .replace("__DEFAULT_SMILES__", default_smiles)
        .replace("__DEFAULT_NMR__", default_nmr)
        .replace("__NMR2D_FEATURE_CLASS__", nmr2d_feature_class)
        .replace("__NMR2D_CONTOUR_DISABLED_ATTR__", nmr2d_contour_disabled_attr)
        .replace("__NMR2D_RAW_DISABLED_ATTR__", nmr2d_raw_disabled_attr)
        .replace("__NMR2D_FLAG_NOTE__", nmr2d_flag_note)
    )
