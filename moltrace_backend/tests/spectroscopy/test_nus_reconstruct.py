"""Prompt 11 — tests for NUS reconstruction (IST baseline + JTF-Net).

The classical IST-S baseline is exercised for real on synthetic non-uniformly
sampled FIDs (peak-position / intensity recovery and the reference-free REQUIRER
quality ratio). The optional JTF-Net path is exercised with a **fake torch** and
monkeypatched weight/model hooks — neither torch nor the protein-domain weights
are present in CI — to validate device resolution (CUDA -> MPS -> CPU), the
MPS -> CPU retry, the weights-acquisition guard, and the IST fallback, without
the real model. No protein-domain accuracy number is fabricated: the strict
JTF-Net validation gate (3D HNCA peak < 0.05 ppm, intensity < 10 %) needs the
authors' weights and is documented, not asserted, here.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pytest

from moltrace.spectroscopy.nus import (
    JTFNetUnavailable,
    ReconstructionResult,
    assess_reconstruction_quality,
    reconstruct_ist,
    reconstruct_jtfnet,
)
from moltrace.spectroscopy.nus import reconstruct as r

_N = 256
_FREQS = (30, 80, 150)
_AMPS = (1.0, 0.7, 0.5)


# --------------------------------------------------------------------------- #
# Synthetic-spectrum helpers
# --------------------------------------------------------------------------- #
def _synthetic_fid(
    n: int = _N,
    freqs: tuple[int, ...] = _FREQS,
    amps: tuple[float, ...] = _AMPS,
    decay: float = 0.01,
) -> np.ndarray:
    """A sum of decaying complex exponentials → a sparse, few-peak spectrum."""

    t = np.arange(n)
    fid = np.zeros(n, dtype=np.complex128)
    for f, a in zip(freqs, amps, strict=True):
        fid += a * np.exp(2j * np.pi * f * t / n) * np.exp(-decay * t)
    return fid


def _sampling_mask(n: int = _N, fraction: float = 0.40, seed: int = 0) -> np.ndarray:
    """Random NUS mask with the t=0 point always acquired (standard practice)."""

    rng = np.random.default_rng(seed)
    k = max(1, int(round(fraction * n)))
    idx = rng.choice(np.arange(1, n), size=k - 1, replace=False)
    idx = np.concatenate([[0], idx])
    mask = np.zeros(n, dtype=bool)
    mask[idx] = True
    return mask


# --------------------------------------------------------------------------- #
# Fake torch (so the JTF-Net path is testable without a real install)
# --------------------------------------------------------------------------- #
class _FakeDevice:
    def __init__(self, kind: str) -> None:
        self.type = kind

    def __str__(self) -> str:
        return self.type


def _install_fake_torch(monkeypatch, *, cuda: bool = False, mps: bool = False) -> types.ModuleType:
    torch = types.ModuleType("torch")
    torch.device = lambda kind="cpu": _FakeDevice(kind)  # type: ignore[attr-defined]
    torch.cuda = types.SimpleNamespace(is_available=lambda: cuda)  # type: ignore[attr-defined]
    torch.backends = types.SimpleNamespace(  # type: ignore[attr-defined]
        mps=types.SimpleNamespace(is_available=lambda: mps)
    )
    torch.load = lambda *a, **k: {}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", torch)
    return torch


# --------------------------------------------------------------------------- #
# Input normalisation — all four accepted forms + error guards
# --------------------------------------------------------------------------- #
def test_normalise_full_grid_with_boolean_mask() -> None:
    fid = _synthetic_fid()
    mask = _sampling_mask()
    grid, m = r._normalise_inputs(fid * mask, mask)
    assert grid.shape == (_N,)
    assert m.dtype == bool
    np.testing.assert_array_equal(m, mask)
    # Non-sampled increments are zeroed; sampled increments preserved.
    assert np.all(grid[~mask] == 0)
    np.testing.assert_allclose(grid[mask], fid[mask])


def test_normalise_compact_values_with_boolean_mask() -> None:
    fid = _synthetic_fid()
    mask = _sampling_mask()
    compact = fid[mask]  # only the measured values
    grid, m = r._normalise_inputs(compact, mask)
    np.testing.assert_array_equal(m, mask)
    np.testing.assert_allclose(grid[mask], compact)


def test_normalise_full_grid_with_integer_indices() -> None:
    fid = _synthetic_fid()
    mask = _sampling_mask()
    idx = np.flatnonzero(mask)
    grid, m = r._normalise_inputs(fid * mask, idx)
    np.testing.assert_array_equal(m, mask)
    np.testing.assert_allclose(grid[mask], fid[mask])


def test_normalise_compact_values_with_integer_indices_infers_grid() -> None:
    fid = _synthetic_fid()
    mask = _sampling_mask()
    mask[_N - 1] = True  # ensure the last grid point is sampled so N is recovered
    idx = np.flatnonzero(mask)
    compact = fid[idx]
    grid, m = r._normalise_inputs(compact, idx)
    assert grid.size == _N  # N = max(index) + 1
    np.testing.assert_array_equal(m, mask)
    np.testing.assert_allclose(grid[idx], compact)


def test_normalise_zero_one_integer_array_is_treated_as_mask() -> None:
    fid = _synthetic_fid()
    mask = _sampling_mask()
    as_int = mask.astype(int)  # 0/1 ints, same length as the FID
    grid, m = r._normalise_inputs(fid * mask, as_int)
    np.testing.assert_array_equal(m, mask)


def test_normalise_rejects_empty_negative_and_mismatched() -> None:
    fid = _synthetic_fid(n=8)
    with pytest.raises(ValueError):
        r._normalise_inputs(fid, np.array([], dtype=int))
    with pytest.raises(ValueError):
        r._normalise_inputs(fid, np.array([-1, 2, 3]))
    with pytest.raises(ValueError):
        # boolean mask length disagrees with both full-grid and sampled counts
        r._normalise_inputs(np.ones(5, dtype=complex), np.array([True, False, True]))


# --------------------------------------------------------------------------- #
# IST baseline — peak position / intensity recovery
# --------------------------------------------------------------------------- #
def test_ist_recovers_peak_positions() -> None:
    fid = _synthetic_fid()
    mask = _sampling_mask(fraction=0.40, seed=0)
    res = reconstruct_ist(fid * mask, mask, iterations=200, threshold=0.97)

    assert isinstance(res, ReconstructionResult)
    assert res.method == "ist"
    assert res.device == "cpu"
    assert res.iterations == 200
    assert res.reconstructed_fid.shape == (_N,)
    assert abs(res.sampling_fraction - mask.mean()) < 1e-9

    mag = np.abs(np.fft.fft(res.reconstructed_fid))
    # The strongest component (bin 30) is the global maximum, and the three
    # true frequencies are exactly the three largest peaks.
    assert int(np.argmax(mag)) == _FREQS[0]
    top3 = sorted(int(b) for b in np.argsort(mag)[-3:])
    assert top3 == sorted(_FREQS)


def test_ist_preserves_intensity_ordering_and_scale() -> None:
    fid = _synthetic_fid()
    mask = _sampling_mask(fraction=0.40, seed=0)
    res = reconstruct_ist(fid * mask, mask)

    mag = np.abs(np.fft.fft(res.reconstructed_fid))
    true_mag = np.abs(np.fft.fft(fid))
    # Recovered peak intensities keep the 1.0 > 0.7 > 0.5 ordering …
    assert mag[_FREQS[0]] > mag[_FREQS[1]] > mag[_FREQS[2]]
    # … and the strongest peak's amplitude is recovered to within 30 %.
    assert 0.7 < mag[_FREQS[0]] / true_mag[_FREQS[0]] < 1.3


def test_ist_requirer_is_in_unit_interval_and_informative() -> None:
    fid = _synthetic_fid()
    mask = _sampling_mask(fraction=0.40, seed=0)
    res = reconstruct_ist(fid * mask, mask)
    assert 0.0 <= res.requirer <= 1.0
    assert res.requirer > 0.3  # a real reconstruction, not a stub


def test_ist_requirer_increases_with_sampling_density() -> None:
    fid = _synthetic_fid()
    scores = []
    for frac in (0.25, 0.50, 0.75):
        mask = _sampling_mask(fraction=frac, seed=3)
        scores.append(reconstruct_ist(fid * mask, mask).requirer)
    assert scores[0] < scores[1] < scores[2]


# --------------------------------------------------------------------------- #
# REQUIRER — reference-free quality metric
# --------------------------------------------------------------------------- #
def test_assess_quality_separates_good_from_bad() -> None:
    fid = _synthetic_fid()
    mask = _sampling_mask(fraction=0.40, seed=0)
    nus = fid * mask
    res = reconstruct_ist(nus, mask)

    good = assess_reconstruction_quality(res, nus)
    zeros = assess_reconstruction_quality(np.zeros(_N, dtype=complex), nus)
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(_N) + 1j * rng.standard_normal(_N)
    bad_noise = assess_reconstruction_quality(noise, nus)

    assert 0.0 <= good <= 1.0
    assert good > zeros
    assert good > bad_noise


def test_assess_quality_accepts_result_or_array_identically() -> None:
    fid = _synthetic_fid()
    mask = _sampling_mask(fraction=0.40, seed=0)
    nus = fid * mask
    res = reconstruct_ist(nus, mask)
    # A ReconstructionResult and its bare .reconstructed_fid must score the same.
    from_result = assess_reconstruction_quality(res, nus)
    from_array = assess_reconstruction_quality(res.reconstructed_fid, nus)
    assert from_result == from_array


def test_assess_quality_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError):
        assess_reconstruction_quality(np.ones(4, dtype=complex), np.ones(8, dtype=complex))


# --------------------------------------------------------------------------- #
# Validation guards
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("threshold", [0.0, 1.0, -0.1, 1.5])
def test_ist_rejects_out_of_range_threshold(threshold: float) -> None:
    fid = _synthetic_fid(n=16)
    mask = _sampling_mask(n=16, fraction=0.5, seed=1)
    with pytest.raises(ValueError):
        reconstruct_ist(fid * mask, mask, threshold=threshold)


def test_ist_rejects_non_positive_iterations() -> None:
    fid = _synthetic_fid(n=16)
    mask = _sampling_mask(n=16, fraction=0.5, seed=1)
    with pytest.raises(ValueError):
        reconstruct_ist(fid * mask, mask, iterations=0)


def test_ist_rejects_empty_schedule() -> None:
    fid = _synthetic_fid(n=16)
    with pytest.raises(ValueError):
        reconstruct_ist(fid, np.array([], dtype=int))


def test_ist_rejects_all_false_mask() -> None:
    fid = _synthetic_fid(n=16)
    with pytest.raises(ValueError):
        reconstruct_ist(fid, np.zeros(16, dtype=bool))


# --------------------------------------------------------------------------- #
# Device resolution (CUDA -> MPS -> CPU)
# --------------------------------------------------------------------------- #
def test_select_device_prefers_cuda_then_mps_then_cpu(monkeypatch) -> None:
    _install_fake_torch(monkeypatch, cuda=True, mps=False)
    assert r._select_device().type == "cuda"
    _install_fake_torch(monkeypatch, cuda=False, mps=True)
    assert r._select_device().type == "mps"
    _install_fake_torch(monkeypatch, cuda=False, mps=False)
    assert r._select_device().type == "cpu"


def test_select_device_honours_explicit_preference(monkeypatch) -> None:
    _install_fake_torch(monkeypatch, cuda=True, mps=True)
    assert r._select_device("cpu").type == "cpu"


# --------------------------------------------------------------------------- #
# JTF-Net availability + IST fallback
# --------------------------------------------------------------------------- #
def test_jtfnet_without_torch_falls_back_to_ist(monkeypatch) -> None:
    # ``import torch`` raises ImportError when sys.modules["torch"] is None.
    monkeypatch.setitem(sys.modules, "torch", None)
    fid = _synthetic_fid()
    mask = _sampling_mask(fraction=0.40, seed=0)
    res = reconstruct_jtfnet(fid * mask, mask)
    assert res.method == "ist"
    assert any("JTF-Net unavailable" in w for w in res.warnings)


def test_jtfnet_without_torch_raises_when_fallback_disabled(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "torch", None)
    fid = _synthetic_fid(n=32)
    mask = _sampling_mask(n=32, fraction=0.5, seed=0)
    with pytest.raises(JTFNetUnavailable):
        reconstruct_jtfnet(fid * mask, mask, allow_fallback=False)


def test_jtfnet_missing_weights_falls_back_to_ist(monkeypatch, tmp_path: Path) -> None:
    _install_fake_torch(monkeypatch, cuda=False, mps=False)
    monkeypatch.setenv("MOLTRACE_JTFNET_CACHE", str(tmp_path))  # empty cache
    monkeypatch.delenv("MOLTRACE_JTFNET_WEIGHTS_URL", raising=False)
    fid = _synthetic_fid()
    mask = _sampling_mask(fraction=0.40, seed=0)

    res = reconstruct_jtfnet(fid * mask, mask)
    assert res.method == "ist"
    assert any("JTF-Net unavailable" in w for w in res.warnings)

    with pytest.raises(JTFNetUnavailable):
        reconstruct_jtfnet(fid * mask, mask, allow_fallback=False)


def test_jtfnet_model_forward_is_unfilled_integration_point(monkeypatch) -> None:
    # Weights present + package importable, but the model forward intentionally
    # raises (no fabricated reconstruction). Exercises torch.load + package
    # import + the integration-point guard.
    _install_fake_torch(monkeypatch, cuda=False, mps=False)
    monkeypatch.setitem(sys.modules, "jtfnet", types.ModuleType("jtfnet"))
    monkeypatch.setattr(r, "_resolve_weights", lambda warnings: Path("/tmp/jtfnet.pt"))
    fid = _synthetic_fid()
    mask = _sampling_mask(fraction=0.40, seed=0)

    with pytest.raises(JTFNetUnavailable, match="integration point"):
        reconstruct_jtfnet(fid * mask, mask, allow_fallback=False)

    # With fallback enabled it still returns a valid IST reconstruction.
    res = reconstruct_jtfnet(fid * mask, mask, allow_fallback=True)
    assert res.method == "ist"


def test_jtfnet_mps_failure_retries_on_cpu(monkeypatch) -> None:
    _install_fake_torch(monkeypatch, cuda=False, mps=True)

    calls: list[str] = []

    def _fake_run(grid, mask, device, warnings):
        calls.append(device.type)
        if device.type == "mps":
            raise RuntimeError("mps op unimplemented")
        return grid.copy()  # CPU pass succeeds

    monkeypatch.setattr(r, "_run_jtfnet", _fake_run)
    fid = _synthetic_fid()
    mask = _sampling_mask(fraction=0.40, seed=0)
    res = reconstruct_jtfnet(fid * mask, mask)

    assert res.method == "jtfnet"
    assert res.device == "cpu"
    assert calls == ["mps", "cpu"]
    assert any("MPS" in w for w in res.warnings)
