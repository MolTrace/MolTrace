# Security Policy

MolTrace is a platform for regulated pharmaceutical R&D. We take the security of
the codebase and the hosted product seriously and appreciate responsible
disclosure from the security community.

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues,
discussions, or pull requests.**

Report privately through either of these channels:

1. **GitHub private vulnerability reporting** — use the repository's
   **Security → Report a vulnerability** tab (GitHub Security Advisories). This
   is the preferred channel.
2. **Email** — <security@moltrace.co>. If you would like to encrypt your report,
   ask in an initial low-detail email and we will provide a key.

These contacts are also published, machine-readable, at
`/.well-known/security.txt` (RFC 9116). The detailed policy — severity rubric,
remediation SLAs, coordinated-disclosure terms, and safe harbor — lives in the
[Vulnerability Disclosure Policy](moltrace_backend/docs/security/vulnerability_disclosure_policy.md).

Please include, where possible:

- A description of the vulnerability and its impact.
- Steps to reproduce (proof-of-concept, affected endpoint/component, version or
  commit SHA).
- Any logs, screenshots, or payloads needed to reproduce.
- Whether the issue is already public or known to other parties.

## What to expect

- **Acknowledgement** within **3 business days**.
- **Triage and initial assessment** (severity, affected versions) within
  **10 business days**.
- We will keep you informed of remediation progress and coordinate a disclosure
  timeline with you. We aim to remediate high-severity issues promptly and will
  credit reporters who wish to be acknowledged.

## Scope

In scope:

- The MolTrace source in this repository (backend `moltrace_backend/`, frontend
  `moltrace_frontend/`).
- The hosted product at <https://moltrace.co>.

Out of scope (please do not test against these):

- Denial-of-service / volumetric testing against the hosted product.
- Social engineering, physical attacks, or attacks on third-party services
  (Vercel, Render, GitHub, etc.).
- Automated scanner output without a demonstrated, reproducible impact.
- Findings that require a compromised user device or a privileged local account.

## Safe harbor

We will not pursue or support legal action against researchers who, in good
faith:

- Make a reasonable effort to avoid privacy violations, data destruction, and
  service degradation;
- Only interact with accounts they own or have explicit permission to access;
- Give us a reasonable time to remediate before any public disclosure; and
- Do not exfiltrate, retain, or share data beyond the minimum needed to
  demonstrate the issue.

If in doubt about whether an action is authorized, contact
<security@moltrace.co> first.

## A note on compliance framing

MolTrace ships controls **designed to support** regulated workflows (21 CFR
Part 11, GAMP 5, ALCOA+, and related regimes). These controls support, and do
not by themselves certify, a customer's compliance posture; the overall
compliance determination and computerized-system validation remain the
regulated user's responsibility.
