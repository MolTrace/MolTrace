"""Unit tests for the Phase 3 public-datasets pipeline (Prompt 20).

Exercises licence-aware ingestion + version pinning, RDKit/InChIKey normalization
+ dedup, QM9 synthetic flagging, the Prompt 19 validation gate (quarantine), and
-- the crux -- deterministic, leakage-free frozen splits whose test set is a
checksummed, hash-excluded sacred holdout. Runs on a CPU-only host with no real
dataset downloads (tiny in-memory fixtures) and no real database.
"""

from __future__ import annotations

import pytest

from moltrace.spectroscopy.data import (
    SOURCES,
    DatasetsPipelineError,
    HoldoutLeakageError,
    Modality,
    ProvenanceKind,
    RawRecord,
    UpstreamChangedError,
    assert_training_excludes_holdout,
    build_corpus,
    enforce_licences,
    freeze_splits,
    ingest,
    matchms_available,
    normalize,
    validate,
    version_splits,
)
from moltrace.spectroscopy.infra.versioning import LocalDatasetRemote

# 20 distinct small molecules (distinct InChIKey skeletons) for split tests.
_SMILES = [
    "CCO", "CCC", "CCCC", "CCCCC", "c1ccccc1", "CC(=O)O", "CCN", "CCCO",
    "c1ccncc1", "CC(C)O", "CCOCC", "C1CCCCC1", "CC#N", "CO", "c1ccc(O)cc1",
    "CCCCCC", "CCCCO", "CC(C)C", "CCCl", "CCBr",
]


def _nmr(source, ident, smiles, ppm, *, field=100.0):
    return RawRecord(
        source,
        ident,
        Modality.NMR_13C,
        smiles=smiles,
        spectrum={"nucleus": "13C", "field_mhz": field, "ppm": ppm, "intensity": [1.0] * len(ppm)},
    )


def _experimental_corpus(smiles=_SMILES, source="nmrshiftdb2"):
    recs = [_nmr(source, f"id{i}", s, [50.0 + i]) for i, s in enumerate(smiles)]
    return list(normalize(ingest(source, version="v1", records=recs)).records)


# --------------------------------------------------------------------------- #
# Ingest: version pin + licence + content hash
# --------------------------------------------------------------------------- #
def test_ingest_pins_licence_hash_and_provenance():
    ds = ingest("nmrshiftdb2", version="2024-05", records=[_nmr("nmrshiftdb2", "a", "CCO", [58.0])])
    assert ds.source_key == "nmrshiftdb2"
    assert ds.version == "2024-05"
    assert ds.licence.share_alike is True  # CC-BY-SA
    assert ds.licence.redistributable is True
    assert ds.content_hash.startswith("sha256:")
    assert ds.provenance_kind is ProvenanceKind.EXPERIMENTAL


def test_ingest_content_hash_is_order_independent():
    r1 = _nmr("nmrshiftdb2", "a", "CCO", [58.0])
    r2 = _nmr("nmrshiftdb2", "b", "CCC", [16.0])
    h1 = ingest("nmrshiftdb2", version="v1", records=[r1, r2]).content_hash
    h2 = ingest("nmrshiftdb2", version="v1", records=[r2, r1]).content_hash
    assert h1 == h2


def test_ingest_rejects_changed_upstream():
    recs = [_nmr("nmrshiftdb2", "a", "CCO", [58.0])]
    with pytest.raises(UpstreamChangedError):
        ingest("nmrshiftdb2", version="v1", records=recs, expected_content_hash="sha256:deadbeef")


def test_ingest_unknown_source_raises():
    with pytest.raises(DatasetsPipelineError):
        ingest("not-a-source", version="v1", records=[])


def test_qm9_is_flagged_computed():
    ds = ingest("qm9nmr", version="v1", records=[_nmr("qm9nmr", "q", "CCO", [57.0])])
    assert ds.provenance_kind is ProvenanceKind.COMPUTED
    norm = normalize(ds)
    assert all(r.provenance_kind is ProvenanceKind.COMPUTED for r in norm.records)


# --------------------------------------------------------------------------- #
# Normalize: InChIKey + dedup
# --------------------------------------------------------------------------- #
def test_normalize_assigns_inchikey_and_canonical_smiles():
    norm = normalize(ingest("nmrshiftdb2", version="v1", records=[_nmr("nmrshiftdb2", "a", "OCC", [58.0])]))
    rec = norm.records[0]
    assert rec.inchikey == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"  # ethanol
    assert rec.canonical_smiles == "CCO"  # canonicalised (input was "OCC")
    assert rec.record_hash.startswith("sha256:")


def test_normalize_dedups_by_inchikey_and_spectral_hash():
    ds = ingest(
        "nmrshiftdb2",
        version="v1",
        records=[
            _nmr("nmrshiftdb2", "a", "CCO", [18.4, 58.0]),
            _nmr("nmrshiftdb2", "a-dup", "OCC", [58.0, 18.4]),  # same molecule + same peaks
            _nmr("nmrshiftdb2", "b", "CCO", [18.4, 59.0]),  # same molecule, different spectrum
        ],
    )
    norm = normalize(ds)
    assert norm.n_duplicates_removed == 1
    assert len(norm.records) == 2  # the genuinely-different spectrum survives


def test_normalize_dedups_across_sources():
    a = ingest("nmrshiftdb2", version="v1", records=[_nmr("nmrshiftdb2", "a", "CCO", [58.0])])
    b = ingest("hmdb", version="v1", records=[_nmr("hmdb", "h", "CCO", [58.0])])
    norm = normalize(a, b)
    assert len(norm.records) == 1
    assert norm.n_duplicates_removed == 1


# --------------------------------------------------------------------------- #
# Validate: quarantine (Prompt 19 gate)
# --------------------------------------------------------------------------- #
def test_validate_quarantines_bad_structures_and_shifts():
    ds = ingest(
        "nmrshiftdb2",
        version="v1",
        records=[
            _nmr("nmrshiftdb2", "good", "CCO", [58.0]),
            _nmr("nmrshiftdb2", "bad-struct", "!!!not-smiles!!!", [58.0]),
            _nmr("nmrshiftdb2", "bad-ppm", "CCC", [5000.0]),  # 13C out of range
            _nmr("nmrshiftdb2", "bad-field", "CO", [50.0], field=99999.0),
        ],
    )
    outcome = validate(normalize(ds))
    assert outcome.n_clean == 1
    assert outcome.n_quarantined == 3
    reasons = {q.record.identifier: " ".join(q.reasons) for q in outcome.quarantined}
    assert "structure" in reasons["bad-struct"]
    assert "ppm_range" in reasons["bad-ppm"]
    assert "field_range" in reasons["bad-field"]


# --------------------------------------------------------------------------- #
# Licence enforcement
# --------------------------------------------------------------------------- #
def test_sdbs_and_metlin_are_not_redistributable():
    assert SOURCES["sdbs"].licence.redistributable is False
    assert SOURCES["metlin"].licence.redistributable is False
    assert SOURCES["nmrshiftdb2"].licence.share_alike is True


def test_build_corpus_excludes_non_redistributable_sources():
    exp = ingest("nmrshiftdb2", version="v1", records=[_nmr("nmrshiftdb2", "a", "CCO", [58.0])])
    sdbs = ingest("sdbs", version="v1", records=[_nmr("sdbs", "s", "CCC", [16.0])])
    build = build_corpus(exp, sdbs)
    assert {r.source_key for r in build.corpus} == {"nmrshiftdb2"}
    assert {r.source_key for r in build.licence_blocked} == {"sdbs"}
    # explicit internal-use build may include them
    internal = build_corpus(exp, sdbs, allow_non_redistributable=True)
    assert {r.source_key for r in internal.corpus} == {"nmrshiftdb2", "sdbs"}


def test_enforce_licences_partition():
    recs = build_corpus(
        ingest("nmrshiftdb2", version="v1", records=[_nmr("nmrshiftdb2", "a", "CCO", [58.0])]),
        ingest("sdbs", version="v1", records=[_nmr("sdbs", "s", "CCC", [16.0])]),
        allow_non_redistributable=True,
    ).corpus
    allowed, blocked = enforce_licences(recs)
    assert all(r.licence.redistributable for r in allowed)
    assert all(not r.licence.redistributable for r in blocked)


# --------------------------------------------------------------------------- #
# Frozen, leakage-free, seeded splits
# --------------------------------------------------------------------------- #
def _partition(splits):
    return (
        frozenset(r.record_hash for r in splits.train),
        frozenset(r.record_hash for r in splits.val),
        frozenset(r.record_hash for r in splits.test),
    )


def test_freeze_splits_is_deterministic():
    corpus = _experimental_corpus()
    a = freeze_splits(corpus, seed=1)
    b = freeze_splits(corpus, seed=1)
    assert a.test_checksum == b.test_checksum
    assert _partition(a) == _partition(b)


def test_freeze_splits_seed_changes_partition():
    corpus = _experimental_corpus()
    a = freeze_splits(corpus, seed=1)
    b = freeze_splits(corpus, seed=2)
    assert _partition(a) != _partition(b)


def test_freeze_splits_no_cross_split_leakage():
    corpus = _experimental_corpus()
    sp = freeze_splits(corpus, seed=5)
    tr, va, te = _partition(sp)
    assert tr.isdisjoint(va) and tr.isdisjoint(te) and va.isdisjoint(te)
    assert tr | va | te == {r.record_hash for r in corpus}
    # no molecule skeleton straddles two splits
    skel = {"train": set(), "val": set(), "test": set()}
    for name, recs in (("train", sp.train), ("val", sp.val), ("test", sp.test)):
        skel[name] = {r.inchikey[:14] for r in recs if r.inchikey}
    assert skel["train"].isdisjoint(skel["test"])
    assert skel["train"].isdisjoint(skel["val"])
    assert skel["val"].isdisjoint(skel["test"])


def test_holdout_is_experimental_only_and_excludes_overlapping_computed():
    experimental = _experimental_corpus(["c1ccccc1", "CCO"])
    computed = list(
        normalize(
            ingest(
                "qm9nmr",
                version="v1",
                records=[
                    _nmr("qm9nmr", "cE", "CCO", [18.0, 57.0]),  # same molecule as an exp test record
                    _nmr("qm9nmr", "cP", "CCC", [15.0]),  # unique to the synthetic set
                ],
            )
        ).records
    )
    sp = freeze_splits([*experimental, *computed], seed=1, ratios=(0.0, 0.0, 1.0))
    # all experimental land in test; computed never in val/test
    assert all(r.provenance_kind is ProvenanceKind.EXPERIMENTAL for r in sp.test)
    assert all(r.provenance_kind is ProvenanceKind.EXPERIMENTAL for r in sp.val)
    assert len(sp.test) == 2
    # the synthetic ethanol (shares a skeleton with a test molecule) is excluded from training
    assert sp.n_computed_excluded_for_holdout == 1
    train_idents = {r.identifier for r in sp.train}
    assert "cP" in train_idents and "cE" not in train_idents
    train_comp_skel = {r.inchikey[:14] for r in sp.train if r.provenance_kind is ProvenanceKind.COMPUTED}
    eval_skel = {r.inchikey[:14] for r in (*sp.val, *sp.test)}
    assert train_comp_skel.isdisjoint(eval_skel)


def test_holdout_checksum_and_exclusion_guard():
    corpus = _experimental_corpus()
    sp = freeze_splits(corpus, seed=1, ratios=(0.5, 0.0, 0.5))  # guarantee a non-empty holdout
    assert sp.test  # non-empty with this split
    assert sp.holdout_exclusion_hashes == {r.record_hash for r in sp.test}
    # a clean training set passes
    assert_training_excludes_holdout([r.record_hash for r in sp.train], sp)
    # a training set that touches the holdout is rejected
    leaked = next(iter(sp.holdout_exclusion_hashes))
    with pytest.raises(HoldoutLeakageError):
        assert_training_excludes_holdout([r.record_hash for r in sp.train] + [leaked], sp)


# --------------------------------------------------------------------------- #
# DVC / content-addressed versioning of splits
# --------------------------------------------------------------------------- #
def test_version_splits_roundtrip(tmp_path):
    sp = freeze_splits(_experimental_corpus(), seed=3, ratios=(0.5, 0.0, 0.5))
    remote = LocalDatasetRemote(tmp_path / "store")
    versions = version_splits(sp, remote, workdir=tmp_path / "work")
    assert set(versions) == {"train", "val", "test"}
    for version in versions.values():
        assert version.dataset_hash.startswith("sha256:")
    restored = remote.restore("moltrace-corpus-test-seed3", tmp_path / "restored_test.jsonl")
    assert restored.dataset_hash == versions["test"].dataset_hash


# --------------------------------------------------------------------------- #
# matchms is optional (native fallback)
# --------------------------------------------------------------------------- #
def test_matchms_optional_native_fallback():
    assert isinstance(matchms_available(), bool)
    ms = RawRecord(
        "massbank_eu",
        "ms1",
        Modality.MSMS,
        smiles="CCO",
        spectrum={"peaks": [(45.0, 10.0), (31.0, 5.0)], "precursor_mz": 47.0},
    )
    ds = ingest("massbank_eu", version="v1", records=[ms])
    # use_matchms=True must not crash even when matchms is absent (native fallback)
    norm = normalize(ds, use_matchms=True)
    spectrum = norm.records[0].spectrum
    assert spectrum is not None
    assert spectrum["peaks"][0][0] == 31.0  # sorted by m/z
    assert max(i for _, i in spectrum["peaks"]) == 1.0  # intensities normalised
