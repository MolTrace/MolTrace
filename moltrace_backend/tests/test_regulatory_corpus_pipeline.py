"""Prompt 20 — regulatory corpus ingestion, versioning & revision tracking.

Exercises the per-source adapters (FDA public-domain, ICH/EMA internal-only, FDA NDSRI), the
content-hash version pinning, chunk-level citation provenance, the Prompt 19 validation gate,
licence enforcement at the redistribution boundary, and the revision-watch change-control gate
(no silent limit changes).
"""

from __future__ import annotations

import pytest

from moltrace.regulatory.data import (
    ChangeControlItem,
    CorpusLicense,
    CorpusSource,
    EmaGuidanceAdapter,
    FdaGuidanceAdapter,
    FdaNdsriAdapter,
    IchGuidelineAdapter,
    LicenseError,
    RevalidationTask,
    guard_redistribution,
    index,
    ingest,
    revision_watch,
    validate,
)

_FDA_REC = {
    "document_id": "FDA-Nitrosamine-Guidance",
    "title": "Control of Nitrosamine Impurities in Human Drugs",
    "revision": "Rev 1 (2021-02)",
    "effective_date": "2021-02-24",
    "url": "https://www.fda.gov/media/141720/download",
    "sections": [
        ("I. Introduction", "This guidance addresses nitrosamines."),
        ("II. Recommendations", "Manufacturers should assess risk."),
    ],
}
_ICH_REC = {
    "document_id": "ICH-M7(R2)",
    "title": "Assessment and Control of DNA Reactive (Mutagenic) Impurities",
    "revision": "R2",
    "effective_date": "2023-04-03",
    "url": "https://database.ich.org/sites/default/files/M7_R2_Guideline.pdf",
    "text": "The TTC of 1.5 ug/day applies to lifetime exposure.\n\nStaged limits apply otherwise.",
}
_EMA_REC = {
    "document_id": "EMA-Nitrosamines-QA",
    "title": "Questions and answers on nitrosamine impurities",
    "revision": "Rev 17",
    "effective_date": "2024-07-01",
    "url": "https://www.ema.europa.eu/en/documents/nitrosamines-qa.pdf",
    "text": "Q&A on nitrosamine acceptable intakes and the CPCA.",
}


def _fda() -> object:
    return ingest(FdaGuidanceAdapter([_FDA_REC]))


# --------------------------------------------------------------------------- #
# ingest + licence + version hash
# --------------------------------------------------------------------------- #
def test_each_adapter_stamps_its_licence() -> None:
    fda = ingest(FdaGuidanceAdapter([_FDA_REC]))
    ich = ingest(IchGuidelineAdapter([_ICH_REC]))
    ema = ingest(EmaGuidanceAdapter([_EMA_REC]))
    assert fda.license is CorpusLicense.FDA_PUBLIC_DOMAIN and fda.docs[0].redistributable is True
    assert ich.license is CorpusLicense.ICH_COPYRIGHTED and ich.docs[0].redistributable is False
    assert ema.license is CorpusLicense.EMA_REUSE_TERMS and ema.docs[0].redistributable is False


def test_ingest_records_revision_effective_date_url_and_hash() -> None:
    doc = _fda().docs[0]
    assert doc.source is CorpusSource.FDA_GUIDANCE
    assert doc.document_id == "FDA-Nitrosamine-Guidance"
    assert doc.revision == "Rev 1 (2021-02)"
    assert doc.effective_date == "2021-02-24"
    assert doc.url.startswith("https://www.fda.gov/")
    assert doc.content_hash.startswith("sha256:")


def test_content_hash_is_deterministic_and_change_sensitive() -> None:
    h1 = ingest(FdaGuidanceAdapter([_FDA_REC])).docs[0].content_hash
    h2 = ingest(FdaGuidanceAdapter([_FDA_REC])).docs[0].content_hash
    assert h1 == h2  # same revision re-fetched -> same hash (no silent drift)
    changed = {**_FDA_REC, "revision": "Rev 2 (2024-09)", "effective_date": "2024-09-01"}
    assert ingest(FdaGuidanceAdapter([changed])).docs[0].content_hash != h1


def test_silent_section_edit_is_caught_by_the_hash_and_revision_gate() -> None:
    # A doc with BOTH an explicit summary text AND served sections: a silent edit to a section
    # (e.g. a 10x limit change) must change content_hash and trip revision_watch — the served
    # content, not just the summary, is version-addressed.
    def _doc(section_body: str):
        return ingest(
            IchGuidelineAdapter(
                [{
                    "document_id": "ICH-M7(R2)",
                    "title": "M7",
                    "revision": "R2",  # same revision + effective_date as the silent-edit attack
                    "effective_date": "2023-04-03",
                    "url": "https://database.ich.org/sites/default/files/M7_R2_Guideline.pdf",
                    "text": "Assessment and Control of DNA Reactive (Mutagenic) Impurities.",
                    "sections": [("II. Acceptable Intakes", section_body)],
                }]
            )
        ).docs[0]

    pinned = _doc("The TTC of 1.5 ug/day applies to lifetime exposure.")
    edited = _doc("The TTC of 0.15 ug/day applies to lifetime exposure.")  # 10x lower limit
    assert pinned.content_hash != edited.content_hash  # served-section edit changes the hash
    alert = revision_watch(pinned, edited)
    assert alert.changed is True and alert.hold is True and alert.serving_allowed is False
    assert alert.change_control is not None


def test_ndsri_adapter_renders_compound_rows() -> None:
    rows = [
        {
            "name": "NDMA",
            "smiles": "CN(C)N=O",
            "expected_category": 1,
            "expected_ai_limit_ng_per_day": 26.5,
            "effective_date": "2023-08-01",
        },
    ]
    docs = ingest(FdaNdsriAdapter(rows))
    assert docs.license is CorpusLicense.FDA_PUBLIC_DOMAIN
    doc = docs.docs[0]
    assert doc.document_id == "ndsri:NDMA"
    assert "26.5 ng/day" in doc.text and "category: 1" in doc.text
    assert doc.content_hash.startswith("sha256:")


# --------------------------------------------------------------------------- #
# index — citation provenance on every chunk
# --------------------------------------------------------------------------- #
def test_index_keeps_source_section_date_url_on_every_chunk() -> None:
    chunks = index(_fda())
    assert len(chunks) == 2  # two sections
    for ch in chunks:
        assert ch.source is CorpusSource.FDA_GUIDANCE
        assert ch.section and ch.effective_date == "2021-02-24"
        assert ch.url.startswith("https://www.fda.gov/")
        assert ch.license is CorpusLicense.FDA_PUBLIC_DOMAIN
        assert "effective 2021-02-24" in ch.citation() and ch.url in ch.citation()
    # paragraph fallback when no sections
    ich_chunks = index(ingest(IchGuidelineAdapter([_ICH_REC])))
    assert len(ich_chunks) == 2 and {c.section for c in ich_chunks} == {"p1", "p2"}


def test_index_embedder_and_sink_are_optional_hooks() -> None:
    seen: list[str] = []
    chunks = index(_fda(), embedder=lambda text: [float(len(text)), 1.0], sink=seen.append)
    assert all(c.embedding == (float(len(c.text)), 1.0) for c in chunks)
    assert len(seen) == len(chunks)  # sink received every chunk


# --------------------------------------------------------------------------- #
# licence enforcement at the redistribution boundary
# --------------------------------------------------------------------------- #
def test_guard_blocks_internal_only_redistribution() -> None:
    fda_chunks = index(_fda())
    guard_redistribution(fda_chunks)  # public domain -> no raise
    ich_chunks = index(ingest(IchGuidelineAdapter([_ICH_REC])))
    with pytest.raises(LicenseError, match="internal-only"):
        guard_redistribution(ich_chunks)
    # a mixed export is blocked too
    with pytest.raises(LicenseError):
        guard_redistribution([*fda_chunks, *ich_chunks])


# --------------------------------------------------------------------------- #
# validate — Prompt 19 gate + citation-url requirement
# --------------------------------------------------------------------------- #
def test_validate_passes_well_formed_corpus() -> None:
    report = validate(_fda())
    assert report.success, report.failures


def test_validate_flags_internal_only_without_citation_url() -> None:
    ich_no_url = ingest(IchGuidelineAdapter([{**_ICH_REC, "url": ""}]))
    report = validate(ich_no_url)
    assert not report.success
    assert any("official-source url" in f.detail for f in report.failures)


def test_validate_flags_unparseable_date_and_empty_text() -> None:
    bad = ingest(
        FdaGuidanceAdapter(
            [
                {
                    "document_id": "X",
                    "title": "X",
                    "revision": "r",
                    "effective_date": "not-a-date",
                    "url": "https://fda.gov/x",
                    "text": "",
                }
            ]
        )
    )
    report = validate(bad)
    assert not report.success
    assert any("effective_date" in f.detail for f in report.failures)


def test_validate_flags_empty_source() -> None:
    empty = ingest(FdaGuidanceAdapter([]))
    report = validate(empty)
    assert not report.success
    assert any("no documents" in f.detail for f in report.failures)


# --------------------------------------------------------------------------- #
# revision_watch — change control + revalidation, no silent limit changes
# --------------------------------------------------------------------------- #
def test_revision_watch_no_change_allows_serving() -> None:
    pinned = _fda().docs[0]
    alert = revision_watch(pinned, pinned)
    assert alert.changed is False and alert.hold is False
    assert alert.serving_allowed is True
    assert alert.change_control is None and alert.revalidation_task is None


def test_revision_watch_change_opens_change_control_and_holds() -> None:
    pinned = ingest(IchGuidelineAdapter([_ICH_REC])).docs[0]
    revised = ingest(
        IchGuidelineAdapter(
            [
                {
                    **_ICH_REC,
                    "revision": "R3",
                    "effective_date": "2027-01-01",
                    "text": "The TTC of 1.0 ug/day now applies.",
                }
            ]
        )
    ).docs[0]
    alert = revision_watch(pinned, revised, rule_affecting=True, rule_set_version="sha256:abc")
    assert alert.changed is True and alert.hold is True
    assert alert.serving_allowed is False  # held out of answers until revalidated
    assert isinstance(alert.change_control, ChangeControlItem)
    assert alert.change_control.from_revision == "R2" and alert.change_control.to_revision == "R3"
    assert alert.change_control.requires_ruleset_update is True
    assert isinstance(alert.revalidation_task, RevalidationTask)
    assert alert.revalidation_task.rule_set_version == "sha256:abc"
    assert "rule-set" in alert.revalidation_task.description.lower()


def test_revision_watch_non_rule_change_still_holds_but_no_ruleset_update() -> None:
    pinned = ingest(EmaGuidanceAdapter([_EMA_REC])).docs[0]
    revised = ingest(
        EmaGuidanceAdapter([{**_EMA_REC, "revision": "Rev 18", "effective_date": "2025-01-01"}])
    ).docs[0]
    alert = revision_watch(pinned, revised, rule_affecting=False)
    assert alert.changed is True and alert.hold is True
    assert alert.change_control.requires_ruleset_update is False


def test_revision_watch_rejects_mismatched_documents() -> None:
    a = ingest(FdaGuidanceAdapter([_FDA_REC])).docs[0]
    b = ingest(IchGuidelineAdapter([_ICH_REC])).docs[0]
    with pytest.raises(ValueError, match="SAME document"):
        revision_watch(a, b)
