import nmrcheck.web as web
from nmrcheck.settings import Settings


def test_spectrum_preview_template_exposes_hover_gain_control_and_toolbar_below_plot() -> None:
    html = web.index()

    assert 'class="spectrum-stage"' in html
    assert 'class="spectrum-hover-rail"' in html
    assert 'id="referenceNmrText"' in html
    assert 'id="maskSolventRegions"' in html
    assert 'id="analysisInputMethod"' in html
    assert 'onchange="setAnalysisInputMethod(this.value)"' in html
    assert 'Paste processed ¹H NMR text' in html
    assert 'Upload processed spectrum (.csv, .tsv, .txt, .jcamp, .jdx, .dx, .xy, .asc, .dat)' in html
    assert 'Upload raw FID archive - Bruker or Varian/Agilent 1D .zip/.tar.gz/.tgz' in html
    assert 'Spectrum file (.csv, .tsv, .txt, .jcamp, .jdx, .dx, .xy, .asc, .dat)' in html
    assert 'accept=".mzml,.mzxml,.mzdata,.imzml,.mgf,.cdf,.netcdf,.raw,.wiff,.wiff2,.d,.yep,.baf,.tdf,.tsf,.xml,.csv,.tsv,.txt,.json,.jcamp,.jdx,.dx,.xy,.asc,.dat"' in html
    assert 'Raw FID Upload' in html
    assert 'Immutable raw FID workflow' in html
    assert 'Original raw FID archive is never modified.' in html
    assert 'Processing creates derived evidence only.' in html
    assert 'Display gain does not alter evidence data.' in html
    assert 'Step 1: Upload raw vendor archive (.zip, .tar.gz, .tgz)' in html
    assert 'Upload & Lock Raw Data' in html
    assert 'id="fidVaultStatus"' in html
    assert 'id="fidProcessingPreset"' in html
    assert 'Step 2: Phase/default processing recipe' in html
    assert 'Baseline preserve' in html
    assert 'Sensitive weak peaks' in html
    assert 'Higher resolution' in html
    assert 'id="fidSolvent"' in html
    assert 'id="fidReferencePPM"' in html
    assert 'id="fidNucleus"' in html
    assert 'id="fidApodizationMode"' in html
    assert 'id="fidDisplayMode"' in html
    assert 'id="processedDisplayMode"' in html
    assert 'Real spectrum - original intensity' in html
    assert 'Preview from immutable raw archive' in html
    assert 'Process as new run' in html
    assert 'Export analysis package' in html
    assert 'id="fidExportStatus"' in html
    assert 'spectrum-context-menu' in html
    assert "contextmenu" in html
    assert 'showSpectrumContextMenu' in html
    assert 'applyRawFidPhaseCorrection' in html
    assert 'applyRawFidBaselineCorrection' in html
    assert 'onclick="applyRawFidPhaseCorrection()"' not in html
    assert 'onclick="applyRawFidBaselineCorrection()"' not in html
    assert 'Reference-assisted matching' in html
    assert 'formData.append("reference_nmr_text", referenceNmrText);' in html
    assert 'Upload a processed spectrum as CSV, TSV, TXT, JCAMP, JDX, DX, XY, ASC, or DAT.' in html
    assert 'The raw archive is hashed and kept immutable.' in html
    assert 'methodTabProcessed' not in html
    assert 'method-tab' not in html
    assert 'id="rawFidPanel"' in html
    assert 'id="fidFile"' in html
    assert 'resetRawFidVaultSelection' in html
    assert 'Preview from immutable raw archive' in html
    assert 'Process as new run' in html
    assert 'FID processing run history' in html
    assert 'Saved FID processing runs' in html
    assert 'fid-run-history-block' in html
    assert 'id="fidRunSelect"' in html
    assert 'Show full FID run table' in html
    assert 'openSelectedFidRunFromDropdown' in html
    assert 'Refresh FID runs' in html
    assert 'Compare selected' in html
    assert 'Open best run' in html
    assert 'api("/fid/runs?limit=20"' in html
    assert 'Open</button>' in html
    assert 'Select this run for side-by-side comparison' in html
    assert 'Report</button>' in html
    assert 'Package</button>' in html
    assert '/fid/runs/${run.id}/package' in html
    assert 'Approve</button>' in html
    assert 'Reject</button>' in html
    assert 'Raw FID processing evidence' in html
    assert 'FID QA diagnostics' in html
    assert 'api("/fid/presets"' in html
    assert 'api("/raw-fid/upload"' in html
    assert 'api(`/raw-fid/${encodeURIComponent(archiveId)}/preview`' in html
    assert 'api(`/raw-fid/${encodeURIComponent(archiveId)}/process`' in html
    assert 'openAuthedPath(`/raw-fid/${encodeURIComponent(archiveId)}/export`' in html
    assert 'id="smiles"' in html
    assert 'id="smiles"' in html and 'required placeholder="Enter a valid SMILES string"' in html
    assert 'id="nmrText"' in html and 'required placeholder="Enter parseable ¹H NMR text with shifts, multiplicities, and integrations"' in html
    assert '¹H evidence' in html
    assert 'analyzeProtonEvidence' in html
    assert 'id="protonEvidenceBox"' in html
    assert 'id="processedSpectrumPanel"' in html
    assert 'id="rawFidPanel"' in html
    assert html.index("¹³C NMR Validation Beta") < html.index("DEPT/APT + 2D NMR Evidence Studio") < html.index("Processed spectrum upload")
    assert 'id="nav-nmr2d"' not in html
    assert 'id="section-nmr2d"' not in html
    assert 'DEPT/APT and 2D NMR evidence are supportive connectivity evidence and require human review.' in html
    assert 'HSQC/HMQC can use DEPT/APT to flag support or conflict. HMBC uses DEPT/APT as contextual evidence only.' in html
    assert 'id="deptAptFile"' in html
    assert 'id="deptAptExperiment"' in html
    assert 'id="deptAptPositive"' in html
    assert 'id="nmr2dFile"' in html
    assert 'id="nmr2dExperiment"' in html
    assert 'Auto-detect' in html
    assert 'Preview 2D' in html
    assert 'Analyze 2D + DEPT/APT' in html
    assert 'Save 2D Run' not in html
    assert 'Export 2D Evidence' not in html
    assert 'previewNmr2d' in html
    assert 'analyzeNmr2d' in html
    assert 'saveNmr2dRun' in html
    assert 'exportNmr2dEvidence' in html
    assert 'syncNmr2dContext' in html
    assert 'renderNmr2dCorrelationTable' in html
    assert 'renderNmr2dConnectivityGraph' in html
    assert 'renderNmr2dContourSummary' in html
    assert 'renderNmr2dReviewBox' in html
    assert 'formData.append("save_run", saveRun ? "true" : "false");' in html
    assert 'new Blob([JSON.stringify(payload, null, 2)]' in html
    assert 'api("/nmr2d/preview"' in html
    assert 'api("/nmr2d/analyze"' in html
    assert 'api("/nmr2d/raw/preview"' in html
    assert '["dashboard","analyze","workspaces","jobs","history","reviews","admin"]' in html
    assert '¹³C NMR Validation Beta' in html
    assert 'id="carbon13InputMethod"' in html
    assert 'id="carbon13Text"' in html
    assert 'id="carbon13SpectrumFile"' in html
    assert 'id="carbon13FidFile"' in html
    assert 'Raw ¹³C FID dataset archive (.zip, .tar.gz)' in html
    assert 'id="carbon13FidApodizationMode"' in html
    assert 'id="carbon13ProcessedDisplayMode"' in html
    assert 'id="carbon13FidDisplayMode"' in html
    assert 'Validate ¹³C text' in html
    assert 'Analyze ¹³C text' in html
    assert 'Preview ¹³C spectrum' in html
    assert 'Analyze ¹³C spectrum' in html
    assert 'Preview raw ¹³C FID' in html
    assert 'applyCarbon13FidPhaseCorrection' in html
    assert 'applyCarbon13FidBaselineCorrection' in html
    assert 'onclick="applyCarbon13FidPhaseCorrection()"' not in html
    assert 'onclick="applyCarbon13FidBaselineCorrection()"' not in html
    assert 'Analyze raw ¹³C FID' in html
    assert 'manual_peaks_json' in html
    assert 'api("/carbon13/analyze"' in html
    assert 'api("/carbon13/spectrum/preview"' in html
    assert 'api("/carbon13/spectrum/analyze"' in html
    assert 'api("/carbon13/fid/preview"' in html
    assert 'api("/carbon13/fid/analyze"' in html


def test_2d_ui_hidden_when_feature_flag_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        web,
        "settings",
        Settings(enable_2d_nmr=False, enable_2d_contour_preview=True, enable_raw_2d_fid_beta=False),
    )

    html = web.index()

    assert 'id="nav-nmr2d"' not in html
    assert 'id="section-nmr2d"' not in html
    assert "DEPT/APT + 2D NMR Evidence Studio" in html


def test_2d_ui_disables_subfeature_controls(monkeypatch) -> None:
    monkeypatch.setattr(
        web,
        "settings",
        Settings(enable_2d_nmr=True, enable_2d_contour_preview=False, enable_raw_2d_fid_beta=False),
    )

    html = web.index()

    assert 'id="nmr2dContourPreview"' not in html
    assert "DEPT/APT + 2D NMR Evidence Studio" in html
    assert 'formData.append("proton_nmr_text", protonNmrText);' in html
    assert 'formData.append("mask_solvent_regions", "true");' in html
    assert 'current SMILES/¹H context' in html
    assert 'Clear analysis' in html
    assert 'clearAnalysisWorkspace()' in html
    assert "Workspaces" in html
    assert "showSection('workspaces')" in html
    assert 'id="section-workspaces"' in html
    assert 'id="workspaceProjectName"' in html
    assert 'Create sample from current analysis inputs' in html
    assert 'Load report JSON' in html
    assert 'Open report HTML' in html
    assert 'Use latest analysis' in html
    assert 'Generate from current/latest' in html
    assert 'id="reportAnalysisId"' in html
    assert 'Project dashboard' in html
    assert 'Linked-analysis count' in html
    assert 'Solvents used' in html
    assert 'Sample detail' in html
    assert 'Sample analysis comparison' in html
    assert 'Reviewer timeline and audit trail' in html
    assert 'Open sample' in html
    assert 'Compare analyses' in html
    assert 'Load latest report' in html
    assert 'Inspect reviewer timeline' in html
    assert 'Same-SMILES fallback' in html
    assert 'Latest linked analysis ID' in html
    assert 'Open latest report' in html
    assert 'Link current analysis' in html
    assert 'Open workspace' in html
    assert 'New sample' in html
    assert 'Analysis count' in html
    assert 'Owner ID' in html
    assert 'Project / sample context' in html
    assert 'Structured evidence' in html
    assert 'Peak list table' in html
    assert 'Reviewer signoff' in html
    assert 'Report JSON' in html
    assert 'Report HTML' in html
    assert 'Use in Workspaces' in html
    assert 'adjustSpectrumVerticalScaleFromWheel(event)' in html
    assert 'getSpectrumVerticalAxisRange(values, scale, baseline=0' in html
    assert 'Real spectrum — original intensity' in html
    assert 'Vertical gain' in html
    assert 'Tall peak clipping' in html
    assert 'Weak peak magnifier' in html
    assert 'Baseline zero-line' in html
    assert 'Plotly.relayout' in html
    assert "type: traceType" in html
    assert "const traceType = x.length > 1200 ? 'scattergl' : 'scatter';" in html
    assert "line: { color: usingOriginalState ? '#64748b' : '#2855d9', width: 2 }" in html
    assert 'showlegend: true' in html
    assert "legend: { orientation: 'h'" in html
    assert 'original_spectrum_state' in html
    assert 'Original upload' in html
    assert 'setSpectrumTraceMode' in html
    assert 'Original uploaded spectrum state (preserved)' in html
    assert 'Baseline flatness QA' in html
    assert 'scaleSpectrumIntensityForDisplay(value, baseline, scale, lockBand=0)' not in html
    assert 'formData.append("display_mode", displayMode);' in html
    assert 'formData.append("display_mode", el("processedDisplayMode")?.value || "real");' in html
    assert 'formData.append("mnova_view"' not in html
    assert 'state.spectrumPreviewContexts[plotId]' in html
    assert 'renderInteractiveSpectrumPlot(context.data, activeId);' in html
    assert 'refreshSpectrumReviewUi(activeId);' in html
    assert "selectSpectrumMarker(markerPayload, plotTarget.id)" in html
    assert "onclick=\"zoomSpectrum(0.55, '${plotId}')\"" in html
    assert 'getSpectrumJValueText' in html
    assert 'Coupling Constant' in html
    assert 'Evidence intensities stay preserved. The ¹H viewer equalizes the displayed baseline to y=0, and peak height controls adjust the y-axis only.' in html
    assert 'getSpectrumBaselineAnchorFraction' in html
    assert 'getSpectrumBaselineEqualizedDisplay' in html
    assert 'baseline-locked display' in html
    assert 'fixedrange: true' in html
    assert 'Reference-guided comparison' in html
    assert 'Normalized reference ¹H NMR text' in html
    assert 'Reviewer peak controls' in html
    assert 'Undo' in html
    assert 'undoSpectrumPeakDecision' in html
    assert 'event.key || "").toLowerCase() === "z"' in html
    assert 'baseline_lock_visual_only' in html
    assert 'installHelpfulTooltips' in html
    assert 'one observed FID peak is selected' in html
    assert 'Matched markers' in html
    assert 'Reference markers' in html
    assert 'Impurity markers' in html
    assert 'Accept peak' in html
    assert 'Exclude peak' in html
    assert 'Reset all review decisions' in html
    assert 'Aromatic H' in html
    assert 'Aliphatic H' in html
    assert 'Carbonyl' in html
    assert 'Aromatic C' in html
    assert 'O/N-bearing' in html
    assert 'Aliphatic C' in html
    assert 'Solvent C' in html
    assert 'formData.append("reference_nmr_text", referenceNmrText);' in html
    assert 'formData.append("apodization_mode", apodizationMode);' in html
    assert 'formData.append("mask_solvent_regions", maskSolventRegions ? "true" : "false");' in html
    assert 'formData.append("manual_nmr_text", reviewedText);' in html
    assert 'Use reviewed peaks as text' in html
    assert 'Structure ↔ NMR' in html
    assert 'Run validation first and fix any SMILES / ¹H NMR mismatch before submitting a job.' in html
    assert 'clearUserSessionState({ resetInputs: true })' in html
    assert 'resetAnalysisInputsToDefaults' in html
    assert 'resetWorkspaceState()' in html
    assert 'loadProjects().catch(() => null);' in html
    assert 'openAuthedPath' in html
    assert 'withAccessToken' in html
    assert 'loadEvidenceReportJson' in html
    assert 'generateReportFromCurrentLatestAnalysis' in html
    assert 'loadReviewerTimelineForAnalysis' in html
    assert '/audit?entity_type=analysis&entity_id=' in html
    assert 'createWorkspaceProject' in html
    assert 'createWorkspaceSampleFromCurrentInputs' in html
    assert 'No output yet.' in html
    assert "plotly_click" in html
    assert "getSpectrumClickPayload" in html
    assert "parseSpectrumMarkerPayload" in html
    assert "clickmode: 'event+select'" in html
    assert "response.status === 401" in html
    assert "Your session expired. Sign in again." in html
    assert html.index('id="spectrumInteractivePlot"') < html.index('onclick="zoomSpectrum(0.55,')
