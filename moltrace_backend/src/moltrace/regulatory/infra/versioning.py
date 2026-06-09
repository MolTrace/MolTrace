"""Content-addressed versioning of rule-sets, corpus snapshots, and gold sets (Prompt 19).

Every regulated artifact is pinned **by content hash** so a result is tied to the
exact bytes it was computed from and a rule-set is reproducible from its hash —
the substrate the GAMP 5 CSV package (Prompt 21) and the Annex 22 audit wrapper
(Prompt 12) stand on. Large blobs live in a DVC + S3 remote, never in git.

Reuse-first: the content-addressing kernel (:func:`dataset_hash`, :func:`file_sha256`,
:func:`current_git_sha`) and the DVC/S3 + local remotes are the tested spectroscopy
Phase 0 implementations, re-exported here so regulatory callers have one surface.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from moltrace.spectroscopy.infra.contract import content_hash
from moltrace.spectroscopy.infra.versioning import (
    DatasetVersion,
    DvcS3Remote,
    LocalDatasetRemote,
    current_git_sha,
    dataset_hash,
    file_sha256,
)

__all__ = [
    "DatasetVersion",
    "DvcS3Remote",
    "LocalDatasetRemote",
    "RegulatoryArtifact",
    "artifact_for",
    "content_hash",
    "corpus_snapshot_version",
    "current_git_sha",
    "dataset_hash",
    "file_sha256",
    "gold_set_version",
    "rule_set_version",
]


@dataclass(frozen=True)
class RegulatoryArtifact:
    """A content-addressed regulatory artifact, pinned by hash with its provenance.

    ``identity_hash`` is the ``sha256:<hex>`` of the artifact's canonical content,
    so re-deriving the same rule-set / corpus snapshot / gold set yields the same
    hash. ``source_guidance`` + ``effective_date`` tie a rule-set to the exact
    guidance revision it encodes (e.g. ``"ICH Q3C(R8)"`` effective ``2021-..``).
    """

    kind: str  # "rule_set" | "corpus_snapshot" | "gold_set"
    identity_hash: str
    semver: str
    source_guidance: str | None = None
    effective_date: str | None = None
    notes: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "identity_hash": self.identity_hash,
            "semver": self.semver,
            "source_guidance": self.source_guidance,
            "effective_date": self.effective_date,
            "notes": self.notes,
        }


def rule_set_version(rule_set: Mapping[str, Any]) -> str:
    """Deterministic ``sha256:<hex>`` content address of a rule-set definition."""

    return content_hash(dict(rule_set))


def corpus_snapshot_version(manifest: Mapping[str, Any]) -> str:
    """Deterministic ``sha256:<hex>`` content address of a regulatory-corpus snapshot."""

    return content_hash(dict(manifest))


def gold_set_version(manifest: Mapping[str, Any]) -> str:
    """Deterministic ``sha256:<hex>`` content address of an evaluation gold set."""

    return content_hash(dict(manifest))


def artifact_for(
    kind: str,
    payload: Mapping[str, Any],
    *,
    semver: str,
    source_guidance: str | None = None,
    effective_date: str | None = None,
    notes: str | None = None,
) -> RegulatoryArtifact:
    """Build a :class:`RegulatoryArtifact` whose ``identity_hash`` addresses ``payload``."""

    return RegulatoryArtifact(
        kind=kind,
        identity_hash=content_hash(dict(payload)),
        semver=semver,
        source_guidance=source_guidance,
        effective_date=effective_date,
        notes=notes,
    )
