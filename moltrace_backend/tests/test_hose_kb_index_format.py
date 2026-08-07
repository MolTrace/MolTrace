"""Precomputed HOSE index: same answers, without the startup cost (B0 deploy).

The problem
-----------
The knowledge base shipped as *molecules + assignments*, so every process start
re-parsed 49 618 molblocks with RDKit and recomputed ~3 M HOSE codes. Measured on
the full NMRShiftDB2 table: **51.2 s to load, 193 MB on disk, 83 % of which is
molblocks that are discarded the moment the codes are computed.**

That is what actually blocked deploying it. A 51 s cold start is incompatible
with a scale-to-zero service, and it was the reason a GPU sidecar looked
necessary — the cheap path appeared unshippable when it was only unoptimised.

The fix is to ship the *index* rather than its inputs. ``lookup`` never sees the
raw shift list: it returns ``fmean``, ``pstdev`` and ``len``. So a per-bucket
``(n, mean, M2)`` accumulator is **lossless for the entire public contract**, and
it serialises to something that loads with no RDKit at all.

The invariant these tests pin: **the precomputed index must answer identically to
the table it was built from.** Any drift here is silent — a shift that moves by
0.3 ppm produces no error, just a slightly wrong prediction forever.
"""

from __future__ import annotations

import json
import math

import pytest
from rdkit import Chem

from moltrace.spectroscopy.predict.nmrnet_wrapper import (
    build_seed_knowledge_base,
    hose_code,
    load_knowledge_base,
    predict_shifts,
    save_knowledge_base_index,
)

PROBE_MOLECULES = [
    "CC(=O)Nc1ccc(O)cc1",  # paracetamol
    "CC(C)Cc1ccc(cc1)C(C)C(=O)O",  # ibuprofen
    "c1ccccc1",  # benzene — in the seed table
    "CCO",  # ethanol
]


@pytest.fixture(scope="module")
def source_kb():
    """A knowledge base built the original way, from molecules."""

    return build_seed_knowledge_base()


@pytest.fixture(scope="module")
def round_tripped(tmp_path_factory, source_kb):
    """The same table, saved as a precomputed index and loaded back."""

    path = tmp_path_factory.mktemp("kb") / "index.json"
    save_knowledge_base_index(source_kb, path)
    return load_knowledge_base(path), path


def _all_probe_codes(mol_h):
    return [(idx, hose_code(mol_h, idx)) for idx in range(mol_h.GetNumAtoms())]


def test_index_answers_identically_to_its_source(source_kb, round_tripped):
    """Every lookup must agree — this is the whole contract."""

    loaded, _ = round_tripped
    checked = 0
    for smiles in PROBE_MOLECULES:
        mol_h = Chem.AddHs(Chem.MolFromSmiles(smiles))
        for idx, code in _all_probe_codes(mol_h):
            for nucleus in ("1H", "13C"):
                a = source_kb.lookup(nucleus, code)
                b = loaded.lookup(nucleus, code)
                if a is None or b is None:
                    assert a is None and b is None, (
                        f"{smiles} atom {idx} {nucleus}: one table matched and the "
                        f"other did not ({a!r} vs {b!r})"
                    )
                    continue
                checked += 1
                assert b[0] == pytest.approx(a[0], abs=1e-9), "mean drifted"
                assert b[1] == pytest.approx(a[1], abs=1e-9), "stdev drifted"
                assert b[2] == a[2], "matched sphere changed"
                assert b[3] == a[3], "reference count changed"
    assert checked > 0, "probes matched nothing — the test proved nothing"


def test_priors_survive_the_round_trip(source_kb, round_tripped):
    """The element prior is the value used when nothing matches; it must not move."""

    loaded, _ = round_tripped
    assert set(loaded.priors) == set(source_kb.priors)
    for nucleus, value in source_kb.priors.items():
        assert loaded.priors[nucleus] == pytest.approx(value, abs=1e-9)


def test_reference_count_and_source_survive(source_kb, round_tripped):
    loaded, _ = round_tripped
    assert loaded.reference_count == source_kb.reference_count
    assert loaded.source == source_kb.source


def test_index_carries_no_molblocks_or_smiles(round_tripped):
    """The 83 % of the old artifact that was dead weight must actually be gone."""

    _loaded, path = round_tripped
    raw = path.read_text()
    assert "molblock" not in raw
    assert "smiles" not in raw
    payload = json.loads(raw)
    assert payload["format"].startswith("hose-index-")


def test_index_loads_without_rdkit(round_tripped, monkeypatch):
    """No RDKit at load time — that is where the 51 s went.

    Guarded by making the import fail: if any RDKit call creeps back into the
    index path, this fails rather than quietly reintroducing the cold start.
    """

    import builtins

    _loaded, path = round_tripped
    real_import = builtins.__import__

    def _no_rdkit(name, *args, **kwargs):
        if name == "rdkit" or name.startswith("rdkit."):
            raise ImportError("RDKit must not be needed to load a precomputed index")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_rdkit)
    kb = load_knowledge_base(path)
    assert kb.reference_count > 0


def test_gzipped_index_round_trips(tmp_path, source_kb):
    """Deployment ships this compressed; the loader must read it transparently."""

    path = tmp_path / "index.json.gz"
    save_knowledge_base_index(source_kb, path)
    assert path.exists()

    loaded = load_knowledge_base(path)
    assert loaded.reference_count == source_kb.reference_count
    assert loaded.priors == pytest.approx(source_kb.priors)


def test_missing_configured_table_is_logged_not_absorbed(tmp_path, monkeypatch, caplog):
    """A deploy that forgot to stage the table must say so.

    Unset MOLTRACE_HOSE_KB is a fine dev default. Set-but-missing is a
    misconfiguration, and silently substituting the 16-molecule seed table for the
    one that was explicitly configured is precisely the silent degradation this
    module was fixed for — the service would answer every request with a ~35 ppm
    median ¹³C uncertainty and look healthy doing it.
    """

    monkeypatch.setenv("MOLTRACE_HOSE_KB", str(tmp_path / "not-staged.json.gz"))
    monkeypatch.setattr(
        "moltrace.spectroscopy.predict.nmrnet_wrapper._FALLBACK_KB", None, raising=False
    )

    from moltrace.spectroscopy.predict.nmrnet_wrapper import _fallback_kb

    with caplog.at_level("ERROR"):
        kb = _fallback_kb()

    assert kb.source == "seed", "should still start, on the seed table"
    assert any("MOLTRACE_HOSE_KB" in r.message for r in caplog.records), (
        "a configured-but-missing knowledge base was absorbed without a log line"
    )


def test_unset_table_does_not_log_an_error(monkeypatch, caplog):
    """The dev default is legitimate and must not cry wolf."""

    monkeypatch.delenv("MOLTRACE_HOSE_KB", raising=False)
    monkeypatch.setattr(
        "moltrace.spectroscopy.predict.nmrnet_wrapper._FALLBACK_KB", None, raising=False
    )

    from moltrace.spectroscopy.predict.nmrnet_wrapper import _fallback_kb

    with caplog.at_level("ERROR"):
        assert _fallback_kb().source == "seed"
    assert not [r for r in caplog.records if "MOLTRACE_HOSE_KB" in r.message]


def test_predictions_are_unchanged_end_to_end(tmp_path, source_kb, monkeypatch):
    """The user-visible outcome, not just the internals.

    A representation change that shifted a prediction by 0.3 ppm would produce no
    error anywhere — only a permanently slightly-wrong answer. So compare the
    actual predicted shifts.
    """

    baseline = {
        s.atom_index: (s.predicted_ppm, s.uncertainty_ppm, s.source)
        for s in predict_shifts("CC(=O)Nc1ccc(O)cc1").shifts
    }

    path = tmp_path / "index.json"
    save_knowledge_base_index(source_kb, path)
    monkeypatch.setenv("MOLTRACE_HOSE_KB", str(path))
    monkeypatch.setattr(
        "moltrace.spectroscopy.predict.nmrnet_wrapper._FALLBACK_KB", None, raising=False
    )

    after = predict_shifts("CC(=O)Nc1ccc(O)cc1")
    assert len(after.shifts) == len(baseline)
    for s in after.shifts:
        want_ppm, want_sigma, want_source = baseline[s.atom_index]
        assert s.predicted_ppm == pytest.approx(want_ppm, abs=1e-9), (
            f"atom {s.atom_index} {s.nucleus} moved {abs(s.predicted_ppm - want_ppm):.2e} ppm"
        )
        assert s.source == want_source
        if math.isfinite(want_sigma):
            assert s.uncertainty_ppm == pytest.approx(want_sigma, abs=1e-9)
