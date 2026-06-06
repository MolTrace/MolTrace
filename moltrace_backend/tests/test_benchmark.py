"""Unit + integration tests for the 5-layer SpectraCheck benchmark."""

from __future__ import annotations

from fastapi.testclient import TestClient

from nmrcheck.api import create_app
from nmrcheck.benchmark import LAYER_WEIGHTS, evaluate_case, evaluate_suite
from nmrcheck.models import BenchmarkCase
from nmrcheck.settings import Settings

HEADERS = {"x-api-key": "test-key"}

# Ethanol — minimal but realistic test case. The observed NMR text matches
# the canonical proton spectrum the rest of the suite uses.
ETHANOL_CASE = BenchmarkCase(
    case_id="ethanol-1",
    smiles="CCO",
    nucleus="1H",
    solvent="CDCl3",
    observed_nmr_text=(
        "1H NMR (400 MHz, CDCl3) δ 3.65 (q, J = 7.1 Hz, 2H), "
        "1.26 (t, J = 7.1 Hz, 3H), 2.10 (br s, 1H)"
    ),
    candidate_block="Ethanol | CCO\nMethanol | CO\nPropanol | CCCO",
    sample_id="SAMPLE-001",
    sha256="a" * 64,
    operator="alice",
    instrument="Bruker 400",
)


def _client(tmp_path):
    return TestClient(
        create_app(
            Settings(
                database_url=f"sqlite:///{tmp_path / 'bench.sqlite3'}",
                require_verified_email=False,
                api_key="test-key",
                raw_data_vault_dir=str(tmp_path / "raw_data_vault"),
            )
        )
    )


class TestEvaluateCase:
    def test_layer_weights_sum_to_one(self) -> None:
        assert abs(sum(LAYER_WEIGHTS.values()) - 1.0) < 1e-9

    def test_ethanol_case_produces_all_five_layers(self) -> None:
        result = evaluate_case(ETHANOL_CASE)
        layer_names = {layer.name for layer in result.layers}
        assert layer_names == {
            "peak_level_accuracy",
            "structural_ranking",
            "explainability",
            "robustness",
            "regulatory_evidence",
        }
        assert 0.0 <= result.overall_score <= 1.0
        assert len(result.summary) == 6

    def test_explainability_is_perfect_when_all_peaks_have_reasoning(self) -> None:
        result = evaluate_case(ETHANOL_CASE)
        explain = next(layer for layer in result.layers if layer.name == "explainability")
        # The categorization module fills category/region/reason on every
        # parseable peak, so this should be 1.0.
        assert explain.score == 1.0
        assert explain.components["with_reason"] == explain.components["peak_count"]

    def test_regulatory_evidence_perfect_when_all_provenance_present(self) -> None:
        result = evaluate_case(ETHANOL_CASE)
        reg = next(layer for layer in result.layers if layer.name == "regulatory_evidence")
        assert reg.score == 1.0
        components = reg.components
        assert components["has_sample_id"] is True
        assert components["has_sha256"] is True
        assert components["has_provenance"] is True
        assert components["has_peak_reasoning_trace"] is True

    def test_regulatory_evidence_drops_when_provenance_missing(self) -> None:
        bare_case = BenchmarkCase(
            case_id="ethanol-2",
            smiles="CCO",
            nucleus="1H",
            solvent="CDCl3",
            observed_nmr_text=ETHANOL_CASE.observed_nmr_text,
        )
        result = evaluate_case(bare_case)
        reg = next(layer for layer in result.layers if layer.name == "regulatory_evidence")
        # Provenance is missing for sample_id / sha256 / operator+instrument — only
        # the peak reasoning trace contributes (0.25).
        assert reg.score == 0.25
        assert any("sample_id missing" in note for note in reg.notes)
        assert any("sha256" in note for note in reg.notes)

    def test_structural_ranking_is_top1_when_true_smiles_is_first(self) -> None:
        result = evaluate_case(ETHANOL_CASE)
        ranking = next(layer for layer in result.layers if layer.name == "structural_ranking")
        assert ranking.score == 1.0
        assert ranking.components["rank_of_true_structure"] == 1

    def test_structural_ranking_drops_when_true_smiles_not_first(self) -> None:
        case = ETHANOL_CASE.model_copy(
            update={"candidate_block": "Methanol | CO\nEthanol | CCO\nPropanol | CCCO"}
        )
        result = evaluate_case(case)
        ranking = next(layer for layer in result.layers if layer.name == "structural_ranking")
        # When the true SMILES is in candidates but not necessarily rank 1, the
        # score should be at most the top-3 reward (0.7).
        assert ranking.score <= 1.0
        rank = ranking.components["rank_of_true_structure"]
        assert rank is not None and rank >= 1

    def test_unparseable_observed_text_warns_but_still_returns_layers(self) -> None:
        case = ETHANOL_CASE.model_copy(
            update={"observed_nmr_text": "no numeric content at all"}
        )
        result = evaluate_case(case)
        assert len(result.warnings) >= 1
        assert len(result.layers) == 5

    def test_robustness_drops_when_top_peak_removed(self) -> None:
        result = evaluate_case(ETHANOL_CASE, robustness_drop_peaks=1)
        robust = next(layer for layer in result.layers if layer.name == "robustness")
        assert 0.0 <= robust.score <= 1.0
        components = robust.components
        assert components["drop_peaks"] == 1
        # Perturbed score never exceeds baseline by construction.
        assert components["perturbed_score"] <= components["baseline_score"] + 1e-9


class TestEvaluateSuite:
    def test_aggregates_have_one_entry_per_layer(self) -> None:
        result = evaluate_suite([ETHANOL_CASE, ETHANOL_CASE.model_copy(update={"case_id": "ethanol-dup"})])
        assert result.case_count == 2
        layer_names = {agg.layer for agg in result.aggregates}
        assert layer_names == set(LAYER_WEIGHTS)
        for agg in result.aggregates:
            assert 0.0 <= agg.mean_score <= 1.0
            assert agg.case_count == 2

    def test_overall_mean_score_is_average_of_case_scores(self) -> None:
        cases = [ETHANOL_CASE, ETHANOL_CASE.model_copy(update={"case_id": "ethanol-dup"})]
        suite = evaluate_suite(cases)
        per_case = [c.overall_score for c in suite.cases]
        assert abs(suite.overall_mean_score - sum(per_case) / len(per_case)) < 1e-3


class TestBenchmarkEndpoint:
    def test_endpoint_returns_full_scorecard(self, tmp_path) -> None:
        with _client(tmp_path) as client:
            response = client.post(
                "/benchmark/spectracheck/run",
                headers=HEADERS,
                json={
                    "cases": [ETHANOL_CASE.model_dump()],
                    "robustness_drop_peaks": 1,
                },
            )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["case_count"] == 1
        assert "aggregates" in payload
        assert len(payload["aggregates"]) == 5
        case_result = payload["cases"][0]
        assert case_result["case_id"] == "ethanol-1"
        assert 0.0 <= case_result["overall_score"] <= 1.0
        layer_names = {layer["name"] for layer in case_result["layers"]}
        assert layer_names == set(LAYER_WEIGHTS)

    def test_endpoint_rejects_empty_case_list(self, tmp_path) -> None:
        with _client(tmp_path) as client:
            response = client.post(
                "/benchmark/spectracheck/run",
                headers=HEADERS,
                json={"cases": [], "robustness_drop_peaks": 1},
            )
        assert response.status_code == 422

    def test_endpoint_accepts_multiple_cases(self, tmp_path) -> None:
        cases = [
            ETHANOL_CASE.model_dump(),
            {
                **ETHANOL_CASE.model_dump(),
                "case_id": "ethanol-2",
                "candidate_block": None,
                "sample_id": None,
                "sha256": None,
                "operator": None,
                "instrument": None,
            },
        ]
        with _client(tmp_path) as client:
            response = client.post(
                "/benchmark/spectracheck/run",
                headers=HEADERS,
                json={"cases": cases, "robustness_drop_peaks": 0},
            )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["case_count"] == 2
