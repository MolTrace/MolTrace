import type { FaqItem } from "@/components/seo/structured-data"

/**
 * Answer-engine (AEO) content: per-surface definitional one-liners + FAQ Q&A.
 *
 * Every answer here was drafted from the white papers / README / module pages
 * and then adversarially fact-checked on two lenses (technical accuracy and
 * compliance-overclaim). Reviewer fixes are applied inline — notably:
 *   - No qNEHVI/BoTorch: multi-objective is a deterministic NumPy Pareto front
 *     + hypervolume indicator (see moltrace_backend/src/nmrcheck/reaction_pareto.py).
 *   - Framework names stay hedged ("designed to support", "ALCOA+-aligned") —
 *     never "compliant"/"certified"/"validated" as held facts.
 *   - Retention is scoped to the audit ledger's configurable floor (default
 *     seven years), per README + Technical WP §3.10.
 *
 * EDITORIAL RULE: any new Q&A must be grounded in a committed source and keep
 * the "designed to support" stance. These strings are rendered visibly AND
 * emitted as FAQPage JSON-LD, so an inaccuracy here is a public claim.
 */

export type ModuleSeo = {
  /** Definitional sentence — the RAG/AI-overview extractable answer. */
  oneLiner: string
  /** schema.org applicationCategory for the module's SoftwareApplication node. */
  applicationCategory: string
  faqs: FaqItem[]
}

export const HOME_FAQS: FaqItem[] = [
  {
    q: "What is MolTrace?",
    a: "MolTrace is an AI-native scientific intelligence platform for chemical and pharmaceutical R&D that links raw analytical data to decisions on one audit-ready evidence trail. It presents three modules — SpectraCheck, Regentry, and Repho — so any number in a report traces back to the spectrum, recipe, citation, and reviewer behind it.",
  },
  {
    q: "What modules does MolTrace include?",
    a: "Three, on one shared evidence stack: SpectraCheck for spectroscopy intelligence (NMR/MS structure elucidation from raw FID and LC-MS/MS), Regentry for regulatory intelligence (dossier drafting and impurity assessment designed to support ICH/FDA/EMA review), and Repho for multi-objective reaction optimization.",
  },
  {
    q: "Who is MolTrace built for?",
    a: "MolTrace is built for pharmaceutical and chemical R&D teams, regulatory affairs professionals, CRO and analytical labs, and academic researchers who need analytical claims they can defend under inspection.",
  },
  {
    q: "Does MolTrace's AI make the analytical or regulatory decisions?",
    a: "No. MolTrace is architected deterministic-first: regulated math and classifications come from a version-pinned rule engine, an auditable verifier is the sole arbiter of correctness, and AI is strictly advisory — it proposes and drafts, then a qualified human signs off. No regulatory document is released without explicit human review.",
  },
  {
    q: "Is MolTrace 21 CFR Part 11 compliant?",
    a: "MolTrace's controls — a tamper-evident HMAC-chained audit ledger, electronic signatures, and an immutable SHA-256-hashed raw-data vault — are designed to support 21 CFR Part 11 and GAMP 5. MolTrace does not claim the product is itself compliant or validated; full computerized-system validation, SOPs, and identity management remain the customer's responsibility.",
  },
  {
    q: "Can I trace a MolTrace result back to the raw data?",
    a: "Yes. MolTrace is evidence-first: every claim — a chemical shift, a peak integration, a candidate score — links back to a specific spectrum file, a processing-recipe hash, a literature citation, and the reviewer who released it, with raw vendor archives SHA-256-hashed in an immutable, write-once vault.",
  },
]

export const SPECTROSCOPY_SEO: ModuleSeo = {
  oneLiner:
    "SpectraCheck is MolTrace's spectroscopy intelligence engine that turns raw NMR and mass-spectrometry data into ranked structure candidates with an audit trail from FID to report.",
  applicationCategory: "Scientific Intelligence Software",
  faqs: [
    {
      q: "What NMR and MS file formats and instrument vendors does SpectraCheck support?",
      a: "SpectraCheck ingests raw FID archives from Bruker and Agilent-Varian (parsed via the open-source nmrglue library), plus JCAMP-DX, CSV, and vendor exports for NMR, and mzML, mzXML, and processed peak lists for LC-MS, HRMS, and MS/MS.",
    },
    {
      q: "Can SpectraCheck do automated structure elucidation from NMR?",
      a: "It ranks candidate SMILES across a multi-layer evidence stack (1H/13C, 2D NMR, HRMS, MS/MS, predicted shifts, fragmentation trees) and runs an automated structure-verification layer, but the platform frames every output as decision support, never a proof of identity.",
    },
    {
      q: "How does SpectraCheck score confidence, and is it a calibrated DP4 probability?",
      a: "It aggregates cross-modal evidence into a ranked candidate list and exposes a DP4/DP5 panel, but MolTrace states the result is decision support — not proof of identity, and not a calibrated DP4/DP5 probability. A human reviewer weighs it before signoff.",
    },
    {
      q: "How does SpectraCheck keep spectroscopy results auditable for a regulatory submission?",
      a: "Every numerical claim links back to its source spectrum; raw FIDs are SHA-256 hashed in an immutable vault, processing is recipe-hash-linked for reproducible replay, and no report releases without human signoff recorded in an ALCOA+-aligned ledger — controls designed to support 21 CFR Part 11 and ICH Q2(R2), not a compliance claim.",
    },
    {
      q: "How does SpectraCheck handle solvent and impurity peaks?",
      a: "Each peak is auto-classified as compound, solvent, impurity, artifact, or 13C satellite against curated Fulmer/Gottlieb residual-solvent and impurity-shift tables, so non-analyte signals are masked from candidate scoring and flagged for the reviewer.",
    },
    {
      q: "Which modalities can SpectraCheck combine in one analysis?",
      a: "NMR (1H/13C, with 2D COSY/HSQC/HMQC/HMBC behind a feature flag), HRMS, MS/MS, and LC-MS features fuse into one evidence stack, and cross-modal contradictions — such as an HRMS exact mass disagreeing with the NMR-implied formula — surface as first-class warnings.",
    },
  ],
}

export const REGULATORY_SEO: ModuleSeo = {
  oneLiner:
    "Regentry is MolTrace's regulatory intelligence module that turns spectroscopy evidence into ICH-classified impurity assessments, CTD dossier drafts, and an ALCOA+-aligned audit ledger.",
  // Deliberately "Intelligence", not "Compliance": the product supports
  // regulatory work but never asserts compliance of itself.
  applicationCategory: "Regulatory Intelligence Software",
  faqs: [
    {
      q: "Does MolTrace Regentry make my submission 21 CFR Part 11 compliant?",
      a: "No. Regentry provides controls designed to support 21 CFR Part 11 — a tamper-evident hash-chained audit ledger and electronic signatures — but MolTrace does not claim the product is itself compliant. Full computerized-system validation, SOPs, and identity management remain the customer's responsibility.",
    },
    {
      q: "How does Regentry classify residual solvents and impurities?",
      a: "Regentry runs deterministic engines for ICH Q3A/B thresholds, Q3C(R8) residual solvents, Q3D(R2) elemental PDEs, M7(R2) mutagenic classification, and the FDA CPCA nitrosamine approach; each result carries its guidance citation and a content-hashed rule-set version, and an unknown solvent returns no guessed limit.",
    },
    {
      q: "What is an ALCOA+ audit trail and how does Regentry provide one?",
      a: "ALCOA+ is the data-integrity set — Attributable, Legible, Contemporaneous, Original, Accurate, plus Complete, Consistent, Enduring, Available. Regentry writes each signed decision to an HMAC-SHA256 hash-chained audit ledger with a configurable retention floor (default seven years), so any edit or reordering breaks recomputation.",
    },
    {
      q: "Can Regentry auto-release a dossier without human sign-off?",
      a: "No. Every regulatory result carries a human-review-required flag and a disclaimer, and no dossier artifact is released without explicit qualified-reviewer sign-off recorded with identity, role, timestamp, and artefact hash. Outputs are decision support, not submission-ready filings.",
    },
    {
      q: "How does Regentry help with CTD dossiers and submission readiness?",
      a: "Regentry drafts CTD Module 3 sections (for example 3.2.S.3.2 Impurities and 3.2.S.4 Control of Drug Substance) with every numerical claim hyperlinked back to its source spectrum, picked peak, literature window, and approving reviewer. The drafts scaffold a submission but are not a finished filing.",
    },
    {
      q: "How does Regentry govern AI-assisted regulatory decisions?",
      a: "Regentry logs AI-assisted decisions to a tamper-evident, hash-chained record with human gating on high-risk items, designed to support EU GMP Draft Annex 22; regulated numbers come from the deterministic rule engine, not the model. The draft Annex is not in force — this is decision-support governance, not a compliance claim.",
    },
  ],
}

export const REACTION_SEO: ModuleSeo = {
  oneLiner:
    "Repho is MolTrace's reaction-optimization module that recommends the next experiment via Bayesian and multi-objective optimization under regulatory, safety, and green-chemistry constraints.",
  applicationCategory: "Scientific Intelligence Software",
  faqs: [
    {
      q: "What optimization methods does Repho use for reaction optimization?",
      a: "Repho runs Bayesian optimization over a Gaussian-process surrogate, using Expected Improvement and upper-confidence-bound acquisition, plus random-forest and TPE-style alternatives. Multi-objective campaigns produce a deterministic non-dominated Pareto front with a hypervolume indicator, computed in pure NumPy.",
    },
    {
      q: "Does Repho calculate green chemistry metrics like E-factor and PMI?",
      a: "Yes. Repho computes Sheldon E-factor (simple and complete), Trost atom economy, process mass intensity (PMI), reaction mass efficiency, and a CHEM21-derived solvent green-score deterministically from RDKit and transparent arithmetic — no model produces the numbers. Each is selectable as an optimization objective alongside yield and selectivity.",
    },
    {
      q: "Can Repho design HTE or DoE plates for lab robotics?",
      a: "Yes. Repho generates a deterministic 24-, 96-, or 384-well plate over a project's design space using Sobol or Latin-hypercube space-filling, full-factorial enumeration, or a Bayesian-optimization seed set, honoring fixed conditions and excluded combinations. Plates are reproducible per seed and export to CSV/JSON for lab robotics.",
    },
    {
      q: "How does Repho enforce ICH impurity limits during optimization?",
      a: "Impurity action items from a Regentry dossier (for example ICH Q3A/B or Q3C limits) are injected as reaction constraints, and recorded experiment outcomes are evaluated against those limits with provenance back to the source action item. A high or critical limit flags an experiment as exceeding the limit; lower tiers apply an advisory penalty. This is decision support, not batch disposition.",
    },
    {
      q: "Does Repho run experiments on its own or is it fully autonomous?",
      a: "No — Repho is decision support and human-gated; nothing auto-executes. Its half-closed design-make-test-analyze loop only proposes the next batch as a draft cycle, which still requires qualified human sign-off and a cleared structural-safety gate before any execution. An optional advisor agent can plan and narrate but never computes a quantitative value.",
    },
    {
      q: "Is Repho's reaction optimization reproducible and audit-ready for regulated work?",
      a: "Repho campaigns are designed to be reproducible from a pinned recipe-hash and seed in the same environment, and every proposal, measured outcome, and human decision is written to MolTrace's tamper-evident audit ledger. The controls are built to support 21 CFR Part 11 and GAMP 5 workflows; MolTrace does not claim the product is itself compliant or validated.",
    },
  ],
}
