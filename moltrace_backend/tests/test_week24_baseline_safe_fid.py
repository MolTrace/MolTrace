from nmrcheck.baseline import evaluate_baseline_flatness, normalize_baseline_mode
from nmrcheck.fid import fid_settings_from_preset


def test_baseline_mode_aliases_to_preserve() -> None:
    assert normalize_baseline_mode("strict") == "preserve"
    assert normalize_baseline_mode("locked") == "preserve"
    assert normalize_baseline_mode("no-correction") == "preserve"


def test_baseline_preserve_preset_is_conservative() -> None:
    settings = fid_settings_from_preset(selected_preset="baseline_preserve")

    assert settings.selected_preset == "baseline_preserve"
    assert settings.line_broadening_hz == 0.0
    assert settings.auto_baseline is False
    assert settings.auto_phase is True


def test_flat_baseline_scores_high() -> None:
    points = [(float(i), 0.001) for i in range(100)]
    points[50] = (50.0, 10.0)

    qa = evaluate_baseline_flatness(points, mode="preserve")

    assert qa.label in {"flat", "review"}
    assert qa.score >= 65


def test_sloped_baseline_flags_review_or_distorted() -> None:
    points = [(float(i), i * 0.02) for i in range(100)]
    points[50] = (50.0, 20.0)

    qa = evaluate_baseline_flatness(points, mode="preserve")

    assert qa.label in {"review", "distorted"}
    assert qa.warnings
