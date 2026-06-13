"""MolTrace ComplianceCore (Roadmap Phase 7) — the second module to ship.

The ComplianceCore turns SpectraCheck's confirmed structures, impurity peaks, and
purity values into regulatory submission-**support** documentation — drafts for
review and sign-off by qualified regulatory-affairs and toxicology professionals,
**not** finished filings or regulatory determinations.

Overriding design principle — **deterministic-first**: every quantitative or
rules-based result (ICH thresholds, Q3C/Q3D PDEs, ICH M7 class, the FDA/EMA CPCA
category and AI limit, specification-limit math) is computed by an auditable
deterministic engine tied to a named guidance revision. LLMs are used only for
narrative drafting, retrieval, and triage — never to produce a regulated number.

Provenance & IP. Regulatory thresholds and the CPCA approach are factual
regulatory criteria, implemented from the official source documents and cited;
copyrighted guideline text/tables (ICH, EMA) are summarised + cited + linked, not
reproduced verbatim, and stored for internal retrieval only. FDA guidance is US
government public domain. All AI outputs are decision-support requiring human
review and sign-off.

* :mod:`.infra` — Phase 0 foundation (Prompt 19): the regulatory metric layer,
  artifact versioning, run tracking, fail-loud input validation, and the GAMP 5
  Appendix D11 / CSV validation-document skeleton. Built reuse-first over the
  spectroscopy Phase 0 foundation (``moltrace.spectroscopy.infra``).
"""

from __future__ import annotations
