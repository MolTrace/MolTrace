from __future__ import annotations

import re
from pathlib import Path


WEB = Path("src/nmrcheck/web.py")


def _web() -> str:
    return WEB.read_text()


def _function_body(source: str, name: str) -> str:
    match = re.search(rf"async function {name}\([^)]*\) \{{(?P<body>.*?)\n        \}}", source, re.S)
    assert match, f"{name} function not found"
    return match.group("body")


def test_dept_apt_2d_studio_is_after_carbon13_and_before_processed_spectrum() -> None:
    web = _web()
    carbon_idx = web.index("¹³C NMR Validation Beta")
    studio_idx = web.index("DEPT/APT + 2D NMR Evidence Studio")
    spectrum_idx = web.index("Processed spectrum upload")

    assert carbon_idx < studio_idx < spectrum_idx
    assert web.index('id="section-analyze"') < studio_idx
    assert 'id="section-nmr2d"' not in web
    assert 'id="nav-nmr2d"' not in web


def test_unified_studio_required_controls_exist() -> None:
    web = _web()

    for required in (
        'id="deptAptFile"',
        'id="deptAptExperiment"',
        'id="deptAptPositive"',
        'id="deptAptBox"',
        'id="nmr2dFile"',
        'id="nmr2dExperiment"',
        'id="nmr2dBox"',
        "Auto-detect",
        "DEPT-90",
        "DEPT-135",
        "APT",
        "COSY",
        "HSQC",
        "HMQC",
        "HMBC",
        "Preview DEPT/APT",
        "Analyze DEPT/APT",
        "Preview 2D",
        "Analyze 2D + DEPT/APT",
    ):
        assert required in web


def test_unified_studio_explains_supportive_human_review_science() -> None:
    web = _web()

    assert "DEPT/APT and 2D NMR evidence are supportive connectivity evidence and require human review." in web
    assert "HSQC/HMQC can use DEPT/APT to flag support or conflict. HMBC uses DEPT/APT as contextual evidence only." in web
    assert "DEPT/APT</div><div class=\"value\">Carbon type" in web
    assert "COSY</div><div class=\"value\">1H-1H" in web
    assert "HSQC/HMQC</div><div class=\"value\">Direct H-C" in web
    assert "HMBC</div><div class=\"value\">Long range" in web


def test_dept_apt_buttons_call_correct_endpoints() -> None:
    web = _web()
    preview_body = _function_body(web, "previewDeptApt")
    analyze_body = _function_body(web, "analyzeDeptApt")

    assert 'api("/carbon13/dept/preview", { method: "POST", body: formData })' in preview_body
    assert 'api("/carbon13/dept/analyze", { method: "POST", body: formData })' in analyze_body
    assert 'formData.append("apt_positive", aptPositive);' in web


def test_2d_buttons_call_correct_endpoints_and_include_dept_context() -> None:
    web = _web()
    preview_body = _function_body(web, "previewNMR2D")
    run_body = _function_body(web, "runNmr2dAnalysis")

    assert 'api("/nmr2d/preview", { method: "POST", body: formData })' in preview_body
    assert 'api("/nmr2d/analyze", { method: "POST", body: formData })' in run_body
    assert 'formData.append("dept_apt_file", deptFile);' in web
    assert 'formData.append("dept_apt_experiment_type", deptExperiment);' in web
    assert 'formData.append("apt_positive", aptPositive);' in web


def test_2d_analysis_uses_current_inputs_read_only() -> None:
    web = _web()
    append_body = re.search(r"function appendNmr2dFormFields\(formData, \{ includeStructure=false, saveRun=false \} = \{\}\) \{(?P<body>.*?)\n        \}", web, re.S)
    assert append_body, "appendNmr2dFormFields not found"
    body = append_body.group("body")

    assert 'const protonText = el("nmrText").value.trim();' in body
    assert 'const carbonText = el("carbon13Text") ? el("carbon13Text").value.trim() : "";' in body
    assert 'const sampleId = el("sampleId")?.value.trim() || "";' in body
    assert 'const solvent = el("solvent")?.value.trim() || "";' in body
    assert 'formData.append("smiles", el("smiles")?.value.trim() || "");' in body
    assert 'el("nmrText").value =' not in body
    assert 'el("carbon13Text").value =' not in body
    assert 'el("smiles").value =' not in body
    assert 'el("solvent").value =' not in body
    assert 'el("sampleId").value =' not in body
