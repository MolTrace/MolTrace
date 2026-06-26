# Security Findings Register

**Security Prompt 17.** The living, in-repo roll-up of security findings across all
sources — third-party penetration tests, internal threat-model sessions, external
researcher disclosures ([VDP](vulnerability_disclosure_policy.md)), and the
automated scanning gates. This register is the artifact that satisfies the program's
acceptance criterion: *findings flow into the backlog with severity SLAs and
remediation evidence.*

## How this register works

- **One row per finding.** Source, CVSS v3.1 severity, status, owner, the SLA dates,
  and a link to **remediation evidence** (fixing commit/PR + regression test +
  re-test).
- **Severity & SLA** follow the shared rubric in the
  [pen-test runbook](pentest_program.md#severity-sla-shared-with-the-scanning-gates)
  and the [secure-SDLC gates](../security_sdlc_gates.md) — one rubric for reported
  and scanner-found issues.
- **Scanner findings** primarily live in the GitHub **Security → Code scanning** tab
  (SARIF, auto-tracked); this register is the cross-source roll-up and the home for
  pen-test / threat-model / researcher findings that don't originate as SARIF.
- **Accepted risks** that cannot be fixed in-window are recorded with a compensating
  control + justification; deployment-level SCA exceptions also live in the
  [`.trivyignore` VEX register](../../../.trivyignore).
- A finding is **closed only with evidence** (commit/PR, regression test, re-test).

### Status values

`open` · `triaged` · `in-progress` · `fixed` · `verified` · `risk-accepted` ·
`false-positive` · `disclosed`

### Columns

| Column | Meaning |
|---|---|
| ID | `MT-VULN-YYYY-NNN` tracking id |
| Source | pen-test / threat-model / researcher (VDP) / scanner (Semgrep·Trivy·gitleaks) |
| Title | short description (no exploit detail in this public file) |
| CVSS | v3.1 base score + severity tier |
| Reported | date in |
| Triaged-by | triage SLA due date |
| Remediate-by | remediation SLA due date |
| Status | from the list above |
| Evidence | commit/PR + regression test + re-test |

## Register

> No findings are recorded yet. The program (cadence, intake, pipeline) is
> established; the first annual third-party pen test and any researcher disclosures
> will populate the table below. Pre-existing **scanner** findings are tracked in
> the GitHub **Security → Code scanning** tab and the
> [`.trivyignore` VEX register](../../../.trivyignore) (torch / mlflow CRITICALs,
> both `not_affected` — vulnerable code not in the execute path) and are summarized
> in [secure-SDLC gates](../security_sdlc_gates.md).

| ID | Source | Title | CVSS | Reported | Triaged-by | Remediate-by | Status | Evidence |
|---|---|---|---|---|---|---|---|---|
| _none yet_ | | | | | | | | |

### Example row (format reference — not a real finding)

| ID | Source | Title | CVSS | Reported | Triaged-by | Remediate-by | Status | Evidence |
|---|---|---|---|---|---|---|---|---|
| `MT-VULN-2026-001` | researcher (VDP) | _example: missing ownership check on a new child-read route_ | 7.1 (High) | 2026-07-01 | 2026-07-04 | 2026-07-31 | verified | PR #123 + `test_…_cross_user_404` + reporter re-test |

## Maintenance

- Add a row at **triage** time (not at fix time) so the SLA clock is visible.
- Update **status** as the finding moves through the
  [pipeline](pentest_program.md#4-findings-pipeline--the-done-when-definition).
- On close, ensure **Evidence** links a fixing commit/PR, a regression test, and a
  re-test result.
- Keep exploit specifics out of this public file — link to the private GitHub
  Security Advisory instead.
- Review the register at each pre-major-release threat-model session; carry open
  findings forward.
