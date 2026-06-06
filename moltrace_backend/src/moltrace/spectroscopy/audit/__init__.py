"""Audit trail + GxP controls supporting 21 CFR Part 11 workflows (Prompt 12).

:mod:`~moltrace.spectroscopy.audit.trail` provides a tamper-evident,
cryptographically chained audit trail, electronic-signature primitives designed
per 21 CFR Part 11.50/.70, append-only log sinks, periodic chain verification, a
7-year retention policy, and capture of AI model-weight checksums so any
AI-assisted result is reproducible and traceable.

These are controls that SUPPORT 21 CFR Part 11 and help customers meet it; full
computerized-system validation and the overall compliance determination remain
the customer's responsibility.
"""

from __future__ import annotations

from moltrace.spectroscopy.audit.trail import (
    MODEL_REGISTRY,
    AuditConfigurationError,
    AuditContextError,
    AuditEntry,
    AuditError,
    AuditLog,
    AuditRecorder,
    AuthorizationError,
    ChainIntegrityError,
    ChainVerificationReport,
    ElectronicSignature,
    InMemoryAuditLog,
    JsonlAuditLog,
    ModelRegistry,
    Operation,
    PdfExportUnavailable,
    RetentionPolicy,
    SignatureMeaning,
    assert_chain_integrity,
    audit_context,
    audited,
    compute_signature,
    configure_audit,
    entry_hash,
    export_pdfa,
    get_default_recorder,
    register_model_checksum,
    register_model_weights,
    render_audit_report_html,
    render_audit_report_text,
    sign_record,
    static_key,
    verify_chain,
    verify_signature,
    with_audit,
)

__all__ = [
    "MODEL_REGISTRY",
    "AuditConfigurationError",
    "AuditContextError",
    "AuditEntry",
    "AuditError",
    "AuditLog",
    "AuditRecorder",
    "AuthorizationError",
    "ChainIntegrityError",
    "ChainVerificationReport",
    "ElectronicSignature",
    "InMemoryAuditLog",
    "JsonlAuditLog",
    "ModelRegistry",
    "Operation",
    "PdfExportUnavailable",
    "RetentionPolicy",
    "SignatureMeaning",
    "assert_chain_integrity",
    "audit_context",
    "audited",
    "compute_signature",
    "configure_audit",
    "entry_hash",
    "export_pdfa",
    "get_default_recorder",
    "register_model_checksum",
    "register_model_weights",
    "render_audit_report_html",
    "render_audit_report_text",
    "sign_record",
    "static_key",
    "verify_chain",
    "verify_signature",
    "with_audit",
]
