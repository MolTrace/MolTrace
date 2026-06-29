# Compliance control register (Security Prompt 22)

A machine-checkable **control→evidence map**: it ties each in-repo security control
(built across Security Prompts 5–21) to the **SOC 2 Trust Services Criteria** + the
**ISO/IEC 27001:2022 Annex A** themes, with repo-relative evidence paths — the
foundation a continuous-compliance platform (Vanta/Drata) maps onto.

> **This is control-coverage self-assessment, NOT an attestation.** SOC 2 and ISO 27001
> are *audited* outcomes — an independent auditor's report (SOC 2) or an accredited
> body's certificate (ISO 27001). **MolTrace does not currently hold either**; the
> controls are **designed to support** those frameworks. Only the auditor's
> report/certificate confers assurance. See the human-readable map in
> [`../moltrace_backend/docs/security/compliance_controls_map.md`](../moltrace_backend/docs/security/compliance_controls_map.md)
> and the customer
> [`trust_center.md`](../moltrace_backend/docs/security/trust_center.md).

## Files

- **`controls.json`** — the register: 21 in-repo controls (id, summary, SOC 2 TSC +
  ISO Annex A mapping, evidence paths) plus inherited (platform) / operational controls
  marked as such (not claimed as in-repo evidence).
- **`validate_controls.py`** — pure-stdlib validator: every in-repo control must cite a
  resolvable evidence path, with a SOC 2 + ISO mapping. **Fail-on-drift** — if a cited
  control file is deleted/moved, the check fails, so the map can't silently rot.

## Run

```bash
python compliance/validate_controls.py     # exit 0 = valid · 1 = problems · 2 = can't read
```

Unit-tested in `moltrace_backend/tests/test_compliance_register.py` (the shipped
register validates; the validator catches a missing path / unmapped control).

## Honest framing rules (do not drift)

- Never write "SOC 2 compliant / certified" or "ISO 27001 certified" while the report /
  certificate is **not held**. Use "designed to support", "mapped to / aligned with",
  "pursuing", "control coverage / readiness".
- Inherited controls (physical/data-center) cite the **sub-processor's** attestation,
  not MolTrace's own. Operational controls (HR, risk register, the audits themselves)
  are marked `operational`, not in-repo evidence.
- ISO 27017 / 27018 are **extensions** certified alongside an ISO 27001 ISMS, not
  standalone certifications.
