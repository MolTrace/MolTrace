"""Regulatory corpus ingestion, versioning & revision tracking (Prompt 20, Phase 3).

A versioned, licence-aware, effective-date-tracked ingestion pipeline for the regulatory-guidance
corpus that backs the Prompt 14 RAG layer. The point is provenance: every retrieved citation traces
to a specific, current guidance revision, and a new upstream revision triggers *review* rather than
silently changing answers.

* :func:`ingest` — run a per-source adapter; record source, document id, revision / effective date,
  licence, url, and a deterministic content hash. Versions are pinned; an upstream change is never
  silently absorbed.
* :func:`index` — chunk each document for the retriever; every chunk keeps source + section +
  effective date + url so citations are exact and current.
* :func:`validate` — gate the corpus with the Prompt 19 validators (required metadata, non-empty
  text, parseable dates) plus the citation-url requirement for internal-only sources.
* :func:`revision_watch` — when a source publishes a new revision, open a change-control item
  (Prompt 18) and a re-validation task, and *hold* the new revision out of answers until the
  deterministic rule-set (Prompt 13) is updated and revalidated.

Licences are first-class: FDA / US-government material is public domain and redistributable; ICH and
EMA material is stored for internal retrieval only, never redistributed, and always cited + linked
to the official source. :func:`guard_redistribution` enforces this at any export boundary.

Adapters parse content the regulated user supplies (a local manifest of already-downloaded
documents); this module is the pipeline + provenance, and never fabricates guidance text.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from moltrace.regulatory.infra.validation import ValidationReport, validate_corpus_document
from moltrace.regulatory.infra.versioning import content_hash

__all__ = [
    "ChangeControlItem",
    "CorpusLicense",
    "CorpusSource",
    "EmaGuidanceAdapter",
    "FdaGuidanceAdapter",
    "FdaNdsriAdapter",
    "IchGuidelineAdapter",
    "IndexChunk",
    "LicenseError",
    "RawDoc",
    "RawDocs",
    "RevalidationTask",
    "RevisionAlert",
    "SourceAdapter",
    "VersionPin",
    "WhoTechnicalReportAdapter",
    "guard_redistribution",
    "index",
    "ingest",
    "revision_watch",
    "validate",
]


# --------------------------------------------------------------------------- #
# Licence + source enumerations
# --------------------------------------------------------------------------- #
class CorpusLicense(StrEnum):
    """Licence terms governing how a source's text may be stored and shared."""

    FDA_PUBLIC_DOMAIN = "fda_public_domain"  # US-government work: redistributable
    ICH_COPYRIGHTED = "ich_copyrighted"  # free to access, NOT redistributable
    EMA_REUSE_TERMS = "ema_reuse_terms"  # reuse terms apply; internal-only handling
    WHO_REUSE_TERMS = "who_reuse_terms"  # WHO TRS: freely available, copyrighted; internal-only

    @property
    def redistributable(self) -> bool:
        """True only for public-domain material; everything else is internal-only."""

        return self is CorpusLicense.FDA_PUBLIC_DOMAIN

    @property
    def requires_citation(self) -> bool:
        """All sources are cited; copyrighted/reuse-term sources MUST link the official source."""

        return True


class CorpusSource(StrEnum):
    """A regulatory-guidance source with a per-source adapter."""

    FDA_GUIDANCE = "fda_guidance"
    ICH_GUIDELINE = "ich_guideline"
    EMA_GUIDANCE = "ema_guidance"
    FDA_NDSRI = "fda_ndsri"  # FDA Nitrosamine (NDSRI) database — the Prompt 21 validation set
    WHO_TECHNICAL_REPORT = "who_technical_report"  # WHO TRS on pharmaceutical quality


# The licence each source ships under (a source cannot silently change its licence).
_SOURCE_LICENSE: dict[CorpusSource, CorpusLicense] = {
    CorpusSource.FDA_GUIDANCE: CorpusLicense.FDA_PUBLIC_DOMAIN,
    CorpusSource.ICH_GUIDELINE: CorpusLicense.ICH_COPYRIGHTED,
    CorpusSource.EMA_GUIDANCE: CorpusLicense.EMA_REUSE_TERMS,
    CorpusSource.FDA_NDSRI: CorpusLicense.FDA_PUBLIC_DOMAIN,
    CorpusSource.WHO_TECHNICAL_REPORT: CorpusLicense.WHO_REUSE_TERMS,
}


class LicenseError(RuntimeError):
    """Raised when internal-only (non-redistributable) corpus content crosses an export boundary."""


# --------------------------------------------------------------------------- #
# Documents + versions
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class VersionPin:
    """A pinned version of one document — the identity used to detect upstream change."""

    source: CorpusSource
    document_id: str
    revision: str
    effective_date: str  # ISO 'YYYY-MM-DD'
    content_hash: str  # 'sha256:...'


@dataclass(frozen=True)
class RawDoc:
    """One ingested guidance document with full provenance + a version-defining content hash."""

    source: CorpusSource
    document_id: str
    title: str
    revision: str
    effective_date: str  # ISO 'YYYY-MM-DD'
    license: CorpusLicense
    url: str  # official source link (mandatory for internal-only sources)
    content_hash: str  # 'sha256:...' over the version-defining fields (excludes retrieved_at)
    text: str
    sections: tuple[tuple[str, str], ...] = ()  # (section_label, section_text)
    retrieved_at: str = ""  # provenance only; deliberately excluded from content_hash

    @property
    def redistributable(self) -> bool:
        return self.license.redistributable

    def pin(self) -> VersionPin:
        return VersionPin(
            source=self.source,
            document_id=self.document_id,
            revision=self.revision,
            effective_date=self.effective_date,
            content_hash=self.content_hash,
        )

    def metadata_dict(self) -> dict:
        """The payload the Prompt 19 corpus validator checks (note British 'licence' spelling)."""

        return {
            "source": self.source.value,
            "document_id": self.document_id,
            "licence": self.license.value,
            "effective_date": self.effective_date,
            "content_hash": self.content_hash,
            "text": self.text,
        }


@dataclass(frozen=True)
class RawDocs:
    """The documents ingested from one source."""

    source: CorpusSource
    license: CorpusLicense
    docs: tuple[RawDoc, ...]
    retrieved_at: str = ""

    def __iter__(self):
        return iter(self.docs)

    def __len__(self) -> int:
        return len(self.docs)


def _version_hash(
    source: CorpusSource,
    document_id: str,
    revision: str,
    effective_date: str,
    url: str,
    text: str,
    sections: Sequence[tuple[str, str]] = (),
) -> str:
    """Deterministic content address over the version-defining fields (not the retrieval time).

    Covers BOTH ``text`` and ``sections`` — the sections are the content that is actually chunked,
    indexed, and served, so a silent edit to a section (e.g. a changed limit) must change the hash
    and trip :func:`revision_watch`.
    """

    return content_hash(
        {
            "source": source.value,
            "document_id": document_id,
            "revision": revision,
            "effective_date": effective_date,
            "url": url,
            "text": text,
            "sections": [[label, body] for label, body in sections],
        }
    )


# --------------------------------------------------------------------------- #
# Per-source adapters
# --------------------------------------------------------------------------- #
class SourceAdapter:
    """Base adapter: turns caller-supplied records into provenance-stamped :class:`RawDoc`s.

    A record is a mapping with: ``document_id``, ``title``, ``revision``, ``effective_date`` (ISO),
    ``url``, ``text``, and optional ``sections`` ([(label, text), ...]). The adapter stamps the
    source's fixed licence and computes the version hash; it never invents guidance text.
    """

    source: CorpusSource

    def __init__(self, records: Sequence[Mapping], *, retrieved_at: str = "") -> None:
        self._records = list(records)
        self._retrieved_at = retrieved_at

    @property
    def license(self) -> CorpusLicense:
        return _SOURCE_LICENSE[self.source]

    def _to_doc(self, record: Mapping) -> RawDoc:
        document_id = str(record["document_id"])
        revision = str(record["revision"])
        effective_date = str(record["effective_date"])
        url = str(record.get("url", ""))
        text = str(record.get("text", ""))
        sections = tuple(
            (str(label), str(body)) for label, body in record.get("sections", ()) or ()
        )
        if not text.strip() and sections:
            # A sectioned document carries its full text as the joined sections.
            text = "\n\n".join(body for _, body in sections)
        return RawDoc(
            source=self.source,
            document_id=document_id,
            title=str(record.get("title", document_id)),
            revision=revision,
            effective_date=effective_date,
            license=self.license,
            url=url,
            content_hash=_version_hash(
                self.source, document_id, revision, effective_date, url, text, sections
            ),
            text=text,
            sections=sections,
            retrieved_at=self._retrieved_at,
        )

    def ingest(self) -> RawDocs:
        docs = tuple(self._to_doc(r) for r in self._records)
        return RawDocs(
            source=self.source,
            license=self.license,
            docs=docs,
            retrieved_at=self._retrieved_at,
        )


class FdaGuidanceAdapter(SourceAdapter):
    """FDA guidance — US-government public domain (ingestible, storable, redistributable)."""

    source = CorpusSource.FDA_GUIDANCE


class IchGuidelineAdapter(SourceAdapter):
    """ICH guidelines (Q3A/B, Q3C, Q3D, M7, …) — copyrighted; internal retrieval only, always cited.

    Stored for internal RAG, never redistributed; every citation links the official ICH source.
    """

    source = CorpusSource.ICH_GUIDELINE


class EmaGuidanceAdapter(SourceAdapter):
    """EMA guidance + Q&A (e.g. the Nitrosamines Q&A revisions) — reuse terms; internal-only, cited.

    Stored for internal RAG, never redistributed; every citation links the official EMA source.
    """

    source = CorpusSource.EMA_GUIDANCE


class WhoTechnicalReportAdapter(SourceAdapter):
    """WHO technical reports (TRS) on pharmaceutical quality — freely available but copyrighted.

    Stored for internal RAG, never redistributed; every citation links the official WHO source.
    """

    source = CorpusSource.WHO_TECHNICAL_REPORT


class FdaNdsriAdapter(SourceAdapter):
    """FDA Nitrosamine (NDSRI) database — public domain; feeds the Prompt 21 validation set.

    Accepts either ready-made document records or raw NDSRI compound rows (``name`` + the CPCA
    category / AI limit); compound rows are rendered into one document per compound so they index
    and cite like any other corpus entry.
    """

    source = CorpusSource.FDA_NDSRI

    def _to_doc(self, record: Mapping) -> RawDoc:
        if "text" in record or "document_id" in record:
            return super()._to_doc(record)
        # NDSRI compound row -> a corpus document.
        name = str(record["name"])
        revision = str(record.get("revision", "NDSRI"))
        effective_date = str(record["effective_date"])
        url = str(record.get("url", ""))
        parts = [f"NDSRI compound: {name}."]
        if "smiles" in record:
            parts.append(f"SMILES: {record['smiles']}.")
        if "expected_category" in record:
            parts.append(f"FDA CPCA category: {record['expected_category']}.")
        if "expected_ai_limit_ng_per_day" in record:
            parts.append(f"Acceptable intake: {record['expected_ai_limit_ng_per_day']} ng/day.")
        text = " ".join(parts)
        return RawDoc(
            source=self.source,
            document_id=f"ndsri:{name}",
            title=f"NDSRI — {name}",
            revision=revision,
            effective_date=effective_date,
            license=self.license,
            url=url,
            content_hash=_version_hash(
                self.source, f"ndsri:{name}", revision, effective_date, url, text
            ),
            text=text,
            retrieved_at=self._retrieved_at,
        )


def ingest(source: SourceAdapter) -> RawDocs:
    """Run a per-source adapter and return its provenance-stamped, version-pinned documents.

    Each :class:`RawDoc` records the source, document id, revision, effective date, licence, url,
    and a deterministic ``content_hash`` over the version-defining fields — so the same revision
    re-fetched yields the same hash and a changed revision is detectable, never silently absorbed.
    """

    return source.ingest()


# --------------------------------------------------------------------------- #
# Indexing for the retriever
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class IndexChunk:
    """A retrievable chunk carrying the provenance needed for an exact, current citation."""

    chunk_id: str
    document_id: str
    source: CorpusSource
    section: str
    effective_date: str
    url: str
    license: CorpusLicense
    redistributable: bool
    text: str
    content_hash: str
    embedding: tuple[float, ...] | None = None

    def citation(self) -> str:
        return f"{self.source.value} §{self.section} (effective {self.effective_date}) — {self.url}"


def _window(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split ``text`` into ~``chunk_size``-token windows overlapping by ``chunk_overlap`` tokens.

    Tokens are whitespace-delimited (a dependency-free approximation of the Prompt 10 "800 tokens,
    200 overlap" spec). A body at or under ``chunk_size`` is returned unchanged.
    """

    tokens = text.split()
    if chunk_size <= 0 or len(tokens) <= chunk_size:
        return [text]
    step = max(1, chunk_size - chunk_overlap)
    windows: list[str] = []
    for start in range(0, len(tokens), step):
        window = tokens[start : start + chunk_size]
        if not window:
            break
        windows.append(" ".join(window))
        if start + chunk_size >= len(tokens):
            break
    return windows


def _chunk_doc(
    doc: RawDoc, *, chunk_size: int | None = None, chunk_overlap: int = 0
) -> list[tuple[str, str]]:
    """Split a document into (section_label, text) chunks — by its sections, else by paragraph.

    When ``chunk_size`` is given, each section/paragraph body is further split into token windows of
    that size overlapping by ``chunk_overlap`` (windows of a single body are suffixed ``#1``, ``#2``
    … so each chunk keeps a distinct, citable section label). With ``chunk_size`` unset the body is
    kept whole (one chunk per section/paragraph).
    """

    if doc.sections:
        base = [(label, body) for label, body in doc.sections if body.strip()]
    else:
        paras = [p.strip() for p in doc.text.split("\n\n") if p.strip()]
        base = [(f"p{i + 1}", para) for i, para in enumerate(paras)]
    if not base or chunk_size is None:
        return base
    out: list[tuple[str, str]] = []
    for label, body in base:
        windows = _window(body, chunk_size, chunk_overlap)
        if len(windows) == 1:
            out.append((label, windows[0]))
        else:
            out.extend((f"{label}#{j + 1}", w) for j, w in enumerate(windows))
    return out


def index(
    docs: RawDocs,
    *,
    embedder: Callable[[str], Sequence[float]] | None = None,
    sink: Callable[[IndexChunk], None] | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int = 0,
) -> list[IndexChunk]:
    """Chunk each document for the Prompt 14 retriever, preserving citation provenance.

    Every chunk keeps source + section + effective date + url (and licence/redistributable) so a
    retrieved citation is exact and current. ``embedder`` (a callable ``str -> Sequence[float]``)
    attaches vectors when supplied; ``sink`` (a callable ``IndexChunk -> None``, e.g. the OpenSearch
    / vector-store writer) receives each chunk. Both are optional so indexing is testable offline.

    Chunking is configurable: by default each section/paragraph becomes one chunk; pass
    ``chunk_size`` (whitespace tokens, e.g. 800) and ``chunk_overlap`` (e.g. 200) to split large
    bodies into overlapping windows. ``chunk_overlap`` must be ``0 <= overlap < chunk_size``.
    """

    if chunk_size is not None:
        if chunk_size <= 0:
            raise ValueError(f"chunk_size must be positive, got {chunk_size}")
        if not 0 <= chunk_overlap < chunk_size:
            raise ValueError(
                f"chunk_overlap must satisfy 0 <= overlap < chunk_size ({chunk_size}), "
                f"got {chunk_overlap}"
            )

    chunks: list[IndexChunk] = []
    for doc in docs.docs:
        for section, body in _chunk_doc(doc, chunk_size=chunk_size, chunk_overlap=chunk_overlap):
            # Stable, unique chunk address: the doc's version hash + this section + its body.
            chunk_id = content_hash(
                {
                    "document_id": doc.document_id,
                    "version": doc.content_hash,
                    "section": section,
                    "text": body,
                }
            )
            embedding = None
            if embedder is not None:
                embedding = tuple(float(x) for x in embedder(body))
            chunk = IndexChunk(
                chunk_id=chunk_id,
                document_id=doc.document_id,
                source=doc.source,
                section=section,
                effective_date=doc.effective_date,
                url=doc.url,
                license=doc.license,
                redistributable=doc.redistributable,
                text=body,
                content_hash=doc.content_hash,
                embedding=embedding,
            )
            if sink is not None:
                sink(chunk)
            chunks.append(chunk)
    return chunks


def guard_redistribution(chunks: Iterable[IndexChunk], *, context: str = "export") -> None:
    """Raise :class:`LicenseError` if any internal-only chunk crosses a redistribution boundary.

    Internal retrieval within the tenant is always permitted; exporting / sharing corpus text
    outside it must include only public-domain (redistributable) chunks. ICH/EMA chunks are
    internal-only and are blocked here.
    """

    blocked = sorted({f"{c.source.value}:{c.document_id}" for c in chunks if not c.redistributable})
    if blocked:
        raise LicenseError(
            f"{len(blocked)} internal-only source(s) cannot be redistributed via {context} "
            f"(cite + link the official source instead): {', '.join(blocked)}"
        )


# --------------------------------------------------------------------------- #
# Validation gate (reuses the Prompt 19 validators)
# --------------------------------------------------------------------------- #
def validate(docs: RawDocs) -> ValidationReport:
    """Gate the corpus: required citation metadata, non-empty text, parseable dates, and — for
    internal-only sources — a mandatory official-source url. Aggregates one report across documents.
    """

    from moltrace.spectroscopy.infra.validation import ValidationFailure  # failure model

    failures: list[ValidationFailure] = []
    n_checks = 0
    if not docs.docs:
        failures.append(ValidationFailure("schema", "corpus source produced no documents"))
        n_checks += 1
    for doc in docs.docs:
        report = validate_corpus_document(doc.metadata_dict())
        n_checks += report.n_checks
        failures.extend(report.failures)
        # Licence-compliance: an internal-only document must carry a citation url.
        n_checks += 1
        if not doc.redistributable and not doc.url.strip():
            failures.append(
                ValidationFailure(
                    "licence",
                    f"internal-only document '{doc.document_id}' must cite an official-source url",
                )
            )
        # No empty chunks.
        n_checks += 1
        if not _chunk_doc(doc):
            failures.append(
                ValidationFailure("schema", f"document '{doc.document_id}' produced no chunks")
            )

    return ValidationReport(
        success=not failures,
        failures=tuple(failures),
        n_checks=n_checks,
        backend="native",
    )


# --------------------------------------------------------------------------- #
# Revision watch + change control (Prompt 18) + re-validation (Prompt 21)
# --------------------------------------------------------------------------- #
class ChangeControlStatus(StrEnum):
    OPEN = "open"


@dataclass(frozen=True)
class ChangeControlItem:
    """A change-control item opened when an upstream revision changes (Prompt 18)."""

    change_control_id: str
    source: CorpusSource
    document_id: str
    from_revision: str
    to_revision: str
    from_effective_date: str
    to_effective_date: str
    summary: str
    requires_ruleset_update: bool
    blocks_serving: bool = True
    status: ChangeControlStatus = ChangeControlStatus.OPEN
    opened_at: str = ""


@dataclass(frozen=True)
class RevalidationTask:
    """A re-validation task that must close before a changed revision flows into answers."""

    task_id: str
    change_control_id: str
    document_id: str
    description: str
    rule_set_version: str | None = None  # the deterministic rule-set (Prompt 13) to update first
    status: str = "open"


@dataclass(frozen=True)
class RevisionAlert:
    """The outcome of comparing a pinned version with the latest fetched version."""

    document_id: str
    changed: bool
    hold: bool  # True => the new revision must NOT flow into answers yet
    reason: str
    change_control: ChangeControlItem | None = None
    revalidation_task: RevalidationTask | None = None

    @property
    def serving_allowed(self) -> bool:
        """Whether the latest revision may be served (only when nothing is on hold)."""

        return not self.hold


def revision_watch(
    pinned: RawDoc | VersionPin,
    latest: RawDoc | VersionPin,
    *,
    rule_affecting: bool = True,
    rule_set_version: str | None = None,
    as_of: str = "",
) -> RevisionAlert:
    """Detect an upstream revision change and gate it.

    Compares the pinned version with the latest fetched version (revision, effective date, and
    content hash). On any change it opens a :class:`ChangeControlItem` and a
    :class:`RevalidationTask` and sets ``hold=True`` — the new revision is held out of answers. When
    ``rule_affecting`` (the document encodes a limit/threshold/rule), ``requires_ruleset_update`` is
    set so the deterministic rule-set (Prompt 13) must be updated and revalidated *first*; a changed
    limit must never silently flow into answers.
    """

    p = pinned.pin() if isinstance(pinned, RawDoc) else pinned
    latest_pin = latest.pin() if isinstance(latest, RawDoc) else latest
    if p.document_id != latest_pin.document_id or p.source != latest_pin.source:
        raise ValueError("revision_watch compares two versions of the SAME document")

    changed = (
        p.revision != latest_pin.revision
        or p.effective_date != latest_pin.effective_date
        or p.content_hash != latest_pin.content_hash
    )
    if not changed:
        return RevisionAlert(
            document_id=p.document_id,
            changed=False,
            hold=False,
            reason=f"no change since pinned revision {p.revision} ({p.effective_date})",
        )

    cc_id = f"CC-{p.source.value}-{p.document_id}-{latest_pin.revision}"
    summary = (
        f"{p.source.value} document '{p.document_id}' changed: revision {p.revision} -> "
        f"{latest_pin.revision}, effective {p.effective_date} -> {latest_pin.effective_date}. "
        "Held out of retrieval answers pending review."
    )
    change_control = ChangeControlItem(
        change_control_id=cc_id,
        source=p.source,
        document_id=p.document_id,
        from_revision=p.revision,
        to_revision=latest_pin.revision,
        from_effective_date=p.effective_date,
        to_effective_date=latest_pin.effective_date,
        summary=summary,
        requires_ruleset_update=rule_affecting,
        opened_at=as_of,
    )
    revalidation = RevalidationTask(
        task_id=f"REVAL-{cc_id}",
        change_control_id=cc_id,
        document_id=p.document_id,
        description=(
            "Re-validate the corpus document and, if it changes a limit/threshold/rule, update and "
            "revalidate the deterministic rule-set (Prompt 13) BEFORE the new revision is served."
            if rule_affecting
            else "Re-validate the changed corpus document before it is served."
        ),
        rule_set_version=rule_set_version,
    )
    return RevisionAlert(
        document_id=p.document_id,
        changed=True,
        hold=True,
        reason=summary,
        change_control=change_control,
        revalidation_task=revalidation,
    )
