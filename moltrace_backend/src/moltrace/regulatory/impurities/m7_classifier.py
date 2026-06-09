"""ICH M7(R2) mutagenic-impurity classifier (Prompt 4).

Classifies a potential impurity under ICH M7(R2) using the five-class scheme of
Mueller et al. (2006): a DNA-reactive structural-alert screen plus the dual
(Q)SAR rule, with experimental data overriding in-silico predictions, Cohort of
Concern handling, and the staged (less-than-lifetime) threshold of toxicological
concern (TTC).

Deterministic-first. The M7 **decision logic** — class assignment, the dual-(Q)SAR
rule, Cohort of Concern handling, and the TTC / acceptable-intake math — is pure,
auditable, and content-versioned: **no model in this path**. The only model-like
component is the **structural-alert screen**, a curated expert rule-based SMARTS
set (the M7-required "expert rule-based (Q)SAR" surrogate, in the spirit of
Ashby-Tennant / Benigni-Bossa) — a rule engine, **not an LLM**. For a formal M7
assessment, supply the results of two complementary (Q)SAR systems (one expert
rule-based, one statistical) via ``in_silico_result_expert`` /
``in_silico_result_statistical``; the internal screen is the default for the
expert/statistical call only when a result is not supplied.

Decision-support only. The class, TTC, and narrative are a documented starting
point for CTD Section 3.2.S.3.2 and must be reviewed and signed off by a qualified
toxicologist. No "compliant" claim is made.

Coverage notes. (1) **Class 4** (alerting structure shared with the drug substance
or a tested-negative related compound) requires drug-substance context not taken by
this function and is therefore not auto-assigned. (2) Cohort of Concern structural
auto-detection covers **N-nitroso and alkyl-azoxy** robustly; **aflatoxin-like**
compounds are a named CoC member that is not reliably detectable from a simple
SMARTS pattern and must be flagged by identity. (3) The structural-alert set is a
curated subset; verify classifications against the official ICH M7(R2) guideline,
its Q&A document, and qualified expert review.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from moltrace.regulatory.infra.validation import (
    ValidationFailure,
    ValidationReport,
    assert_valid_compound_record,
)
from moltrace.regulatory.infra.versioning import content_hash, rule_set_version

__all__ = [
    "M7Classification",
    "classify_m7",
    "m7_rule_set",
]

GUIDELINE = "ICH M7(R2)"
TITLE = (
    "Assessment and Control of DNA Reactive (Mutagenic) Impurities in Pharmaceuticals "
    "to Limit Potential Carcinogenic Risk"
)
CLASS_SCHEME_REFERENCE = "ICH M7(R2) section 6; Mueller et al. (2006) five-class scheme"
TTC_TABLE_REFERENCE = "ICH M7(R2) staged TTC (less-than-lifetime acceptable intakes)"
EFFECTIVE_YEAR = "2023"
CTD_SECTION = "CTD Section 3.2.S.3.2"

# The default TTC for a single mutagenic impurity, lifetime exposure (10^-5 risk).
LIFETIME_TTC_UG_PER_DAY = 1.5

_ALLOWED_CALLS = (None, "positive", "negative")

_CLASS_DEFINITION = {
    1: "Class 1 - known mutagenic carcinogen (mutagenicity + carcinogenicity data positive).",
    2: "Class 2 - known mutagen with unknown carcinogenic potential (bacterial mutagenicity "
    "positive, no rodent carcinogenicity data).",
    3: "Class 3 - alerting structure, unrelated to the drug substance, with no mutagenicity data.",
    4: "Class 4 - alerting structure shared with the drug substance or a related compound that "
    "has been tested non-mutagenic.",
    5: "Class 5 - no structural alert, or an alerting structure with data demonstrating a lack "
    "of mutagenicity.",
}

# Cohort of Concern: high-potency mutagenic carcinogens for which the TTC is not
# appropriate (compound-specific acceptable intakes required). ICH M7(R2) section 7.5.
_COC_DEFINITION = "Cohort of Concern (ICH M7 7.5): aflatoxin-like, N-nitroso, and alkyl-azoxy."

# Curated DNA-reactive structural alerts (expert rule-based screen).
# (name, SMARTS)
_ALERT_SMARTS: tuple[tuple[str, str], ...] = (
    ("aromatic nitro", "[c]-[$([NX3](=O)=O),$([NX3+](=O)[O-])]"),
    ("aromatic amine", "[c]-[NX3;!$([NX3]=O);!$([NX3]C=O);!$([NX3+]);!$([NX3]S(=O)=O)]"),
    ("aromatic azo", "[c]-[NX2]=[NX2]-[c]"),
    ("nitrosamine (N-nitroso)", "[NX3]-[NX2]=[OX1]"),
    ("alkyl-azoxy", "[#6]-[NX2]=[N+]([OX1-])-[#6]"),
    ("alkyl/aryl sulfonate ester", "[#6]-[OX2]-[SX4](=[OX1])(=[OX1])-[#6]"),
    ("epoxide", "[#6r3]1[#6r3][#8r3]1"),
    ("aziridine", "[#6r3]1[#6r3][#7r3]1"),
    ("alpha,beta-unsaturated carbonyl (Michael acceptor)", "[CX3]=[CX3]-[CX3]=[OX1]"),
    ("aldehyde", "[CX3H1](=[OX1])-[#6]"),
    ("primary alkyl halide", "[CX4;H2,H3]-[Cl,Br,I]"),
    ("hydrazine", "[NX3;!$(NC=O);!$(N=O)]-[NX3;!$(NC=O);!$(N=O)]"),
    ("aromatic N-oxide", "[n+]-[OX1-]"),
    ("organic azide", "[#6]-[NX2]=[NX2+]=[NX1-]"),
    ("aliphatic N-nitro / nitramine", "[NX3]-[$([NX3](=O)=O),$([NX3+](=O)[O-])]"),
    ("vinyl/aryl halide on alkene", "[CX3]=[CX3]-[Cl,Br,I]"),
    ("carboxylic acid anhydride", "[CX3](=[OX1])-[OX2]-[CX3]=[OX1]"),
)

# Cohort of Concern structural patterns (robust subset: nitroso + azoxy).
_COC_SMARTS: tuple[tuple[str, str], ...] = (
    ("N-nitroso", "[NX3]-[NX2]=[OX1]"),
    ("alkyl-azoxy", "[#6]-[NX2]=[N+]([OX1-])-[#6]"),
)

# Lazily compiled SMARTS caches (rdkit is imported on first use).
_ALERT_PATTERNS: list[tuple[str, Any]] | None = None
_COC_PATTERNS: list[tuple[str, Any]] | None = None


def _compile(smarts_table: tuple[tuple[str, str], ...]) -> list[tuple[str, Any]]:
    from rdkit import Chem

    compiled: list[tuple[str, Any]] = []
    for name, sma in smarts_table:
        patt = Chem.MolFromSmarts(sma)
        if patt is not None:
            compiled.append((name, patt))
    return compiled


def _alert_patterns() -> list[tuple[str, Any]]:
    global _ALERT_PATTERNS
    if _ALERT_PATTERNS is None:
        _ALERT_PATTERNS = _compile(_ALERT_SMARTS)
    return _ALERT_PATTERNS


def _coc_patterns() -> list[tuple[str, Any]]:
    global _COC_PATTERNS
    if _COC_PATTERNS is None:
        _COC_PATTERNS = _compile(_COC_SMARTS)
    return _COC_PATTERNS


def _parse_mol(smiles: str) -> Any:
    from rdkit import Chem
    from rdkit.rdBase import BlockLogs

    with BlockLogs():
        mol = Chem.MolFromSmiles(str(smiles))
    if mol is None:
        ValidationReport(
            success=False,
            failures=(ValidationFailure("smiles", f"could not parse SMILES {smiles!r}"),),
            n_checks=1,
        ).raise_for_status()
    return mol


def _validate_call(name: str, value: str | None) -> None:
    if value not in _ALLOWED_CALLS:
        ValidationReport(
            success=False,
            failures=(
                ValidationFailure(name, f"{value!r} must be 'positive', 'negative', or None"),
            ),
            n_checks=1,
        ).raise_for_status()


def _staged_ttc(duration_months: float) -> tuple[float, str]:
    """ICH M7 staged (less-than-lifetime) TTC for a single impurity."""

    if duration_months <= 1:
        return 120.0, "<=1 month (120 microg/day)"
    if duration_months <= 12:
        return 20.0, ">1-12 months (20 microg/day)"
    if duration_months <= 120:
        return 10.0, ">1-10 years (10 microg/day)"
    return LIFETIME_TTC_UG_PER_DAY, ">10 years to lifetime (1.5 microg/day)"


@dataclass(frozen=True)
class M7Classification:
    """An ICH M7(R2) classification for one impurity."""

    smiles: str
    m7_class: int
    class_definition: str
    ttc_ug_per_day: float | None
    duration_months: float
    duration_band: str
    regulatory_action_required: str
    structural_alerts: tuple[str, ...]
    in_silico_concordance: str
    expert_review_required: bool
    coc_flag: bool
    coc_categories: tuple[str, ...]
    data_basis: str
    reasoning: str
    regulatory_basis: str
    class_scheme_reference: str
    rule_set_version: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "smiles": self.smiles,
            "m7_class": self.m7_class,
            "class_definition": self.class_definition,
            "ttc_ug_per_day": self.ttc_ug_per_day,
            "duration_months": self.duration_months,
            "duration_band": self.duration_band,
            "regulatory_action_required": self.regulatory_action_required,
            "structural_alerts": list(self.structural_alerts),
            "in_silico_concordance": self.in_silico_concordance,
            "expert_review_required": self.expert_review_required,
            "coc_flag": self.coc_flag,
            "coc_categories": list(self.coc_categories),
            "data_basis": self.data_basis,
            "reasoning": self.reasoning,
            "regulatory_basis": self.regulatory_basis,
            "class_scheme_reference": self.class_scheme_reference,
            "rule_set_version": self.rule_set_version,
        }

    def content_hash(self) -> str:
        return content_hash(self.as_dict())


def classify_m7(
    smiles: str,
    duration_months: float = 120,
    in_silico_result_expert: str | None = None,
    in_silico_result_statistical: str | None = None,
    experimental_ames: str | None = None,
    experimental_carcinogen: str | None = None,
) -> M7Classification:
    """Classify an impurity under ICH M7(R2). See module docstring for the full logic.

    ``duration_months`` selects the staged TTC band (<=1 mo -> 120; >1-12 mo -> 20;
    >1-10 yr -> 10; >10 yr -> 1.5 microg/day). The in-silico / experimental arguments
    take ``'positive'``, ``'negative'``, or ``None``. Experimental data overrides the
    (Q)SAR prediction; the Cohort of Concern overrides the TTC with a compound-specific
    acceptable intake.
    """

    assert_valid_compound_record({"smiles": smiles})
    for arg_name, value in (
        ("in_silico_result_expert", in_silico_result_expert),
        ("in_silico_result_statistical", in_silico_result_statistical),
        ("experimental_ames", experimental_ames),
        ("experimental_carcinogen", experimental_carcinogen),
    ):
        _validate_call(arg_name, value)
    if not (isinstance(duration_months, (int, float)) and duration_months > 0):
        ValidationReport(
            success=False,
            failures=(
                ValidationFailure("duration_months", "must be a positive number of months"),
            ),
            n_checks=1,
        ).raise_for_status()

    mol = _parse_mol(smiles)

    # 1. Structural alert screen (expert rule-based surrogate) + CoC detection.
    alerts = tuple(name for name, patt in _alert_patterns() if mol.HasSubstructMatch(patt))
    coc_categories = tuple(
        name for name, patt in _coc_patterns() if mol.HasSubstructMatch(patt)
    )
    coc_flag = bool(coc_categories)
    has_alert = bool(alerts)

    # 2. Resolve the two (Q)SAR calls; the internal screen is the default per-system
    #    call only when a formal result is not supplied.
    screen_call = "positive" if has_alert else "negative"
    expert_call = in_silico_result_expert or screen_call
    statistical_call = in_silico_result_statistical or screen_call
    expert_substituted = in_silico_result_expert is None
    statistical_substituted = in_silico_result_statistical is None

    if expert_call == "negative" and statistical_call == "negative":
        concordance = "concordant_negative"
    elif expert_call == "positive" and statistical_call == "positive":
        concordance = "concordant_positive"
    else:
        concordance = "discordant"

    staged_ttc, duration_band = _staged_ttc(float(duration_months))

    # 3. Classification decision tree (experimental overrides; CoC overrides TTC).
    expert_review = concordance == "discordant" or coc_flag
    if experimental_carcinogen == "positive":
        m7_class, data_basis = 1, "experimental_carcinogenicity"
    elif coc_flag and experimental_carcinogen != "negative":
        # A Cohort-of-Concern structure is not cleared by a negative Ames result;
        # only a negative carcinogenicity study (handled below) would clear it.
        m7_class, data_basis = 2, "cohort_of_concern_structure"
    elif experimental_carcinogen == "negative":
        m7_class, data_basis = 5, "experimental_carcinogenicity"
    elif experimental_ames == "positive":
        m7_class, data_basis = 2, "experimental_ames"
    elif experimental_ames == "negative":
        m7_class, data_basis = 5, "experimental_ames"
    elif expert_call == "negative" and statistical_call == "negative":
        m7_class, data_basis = 5, "qsar"
    else:
        m7_class, data_basis = 3, "qsar"

    # 4. TTC / acceptable-intake + regulatory action by class.
    if m7_class == 1:
        ttc: float | None = None
        action = (
            "Control at a compound-specific acceptable intake (AI) derived from carcinogenic "
            f"potency (e.g. TD50 linear extrapolation); document in {CTD_SECTION}."
        )
    elif m7_class == 2 and coc_flag:
        ttc = None
        action = (
            "Compound-specific acceptable intake (AI) required; the TTC is not applicable to a "
            f"Cohort of Concern compound ({', '.join(coc_categories)}). Document in {CTD_SECTION}."
        )
    elif m7_class == 2:
        ttc = staged_ttc
        action = (
            f"Control at the staged TTC ({staged_ttc:g} microg/day for {duration_band}); "
            f"document in {CTD_SECTION}."
        )
    elif m7_class == 3:
        ttc = staged_ttc
        action = (
            f"Control at the staged TTC ({staged_ttc:g} microg/day for {duration_band}), or "
            "conduct a bacterial reverse mutation (Ames) assay: negative -> Class 5, "
            f"positive -> Class 2. Document in {CTD_SECTION}."
        )
    else:  # Class 5 (and Class 4, not auto-assigned here)
        ttc = None
        action = "Treat as a non-mutagenic impurity; control under ICH Q3A(R2)/Q3B(R2)."

    # 5. Narrative for CTD Section 3.2.S.3.2.
    reasoning = _build_reasoning(
        m7_class=m7_class,
        alerts=alerts,
        coc_flag=coc_flag,
        coc_categories=coc_categories,
        data_basis=data_basis,
        experimental_ames=experimental_ames,
        experimental_carcinogen=experimental_carcinogen,
        expert_call=expert_call,
        statistical_call=statistical_call,
        concordance=concordance,
        expert_substituted=expert_substituted,
        statistical_substituted=statistical_substituted,
        ttc=ttc,
        duration_band=duration_band,
        action=action,
    )

    return M7Classification(
        smiles=smiles,
        m7_class=m7_class,
        class_definition=_CLASS_DEFINITION[m7_class],
        ttc_ug_per_day=ttc,
        duration_months=float(duration_months),
        duration_band=duration_band,
        regulatory_action_required=action,
        structural_alerts=alerts,
        in_silico_concordance=concordance,
        expert_review_required=expert_review,
        coc_flag=coc_flag,
        coc_categories=coc_categories,
        data_basis=data_basis,
        reasoning=reasoning,
        regulatory_basis=f"{GUIDELINE}: {TITLE}",
        class_scheme_reference=CLASS_SCHEME_REFERENCE,
        rule_set_version=_RULE_SET_VERSION,
    )


def _build_reasoning(
    *,
    m7_class: int,
    alerts: tuple[str, ...],
    coc_flag: bool,
    coc_categories: tuple[str, ...],
    data_basis: str,
    experimental_ames: str | None,
    experimental_carcinogen: str | None,
    expert_call: str,
    statistical_call: str,
    concordance: str,
    expert_substituted: bool,
    statistical_substituted: bool,
    ttc: float | None,
    duration_band: str,
    action: str,
) -> str:
    parts: list[str] = []
    parts.append(
        f"Structural-alert screen: {', '.join(alerts) if alerts else 'no DNA-reactive alert'}."
    )
    if coc_flag:
        parts.append(
            f"Cohort of Concern flagged ({', '.join(coc_categories)}): the TTC does not apply; "
            "a compound-specific acceptable intake based on the specific compound is required."
        )
    if data_basis.startswith("experimental"):
        parts.append(
            f"Experimental data are determinative (Ames={experimental_ames!r}, "
            f"carcinogenicity={experimental_carcinogen!r}) and override the in-silico prediction."
        )
    elif data_basis == "cohort_of_concern_structure":
        parts.append(
            "No determinative carcinogenicity data; classification is driven by the "
            "Cohort-of-Concern structural assignment (a negative Ames does not clear it)."
        )
    else:
        srcs = []
        if expert_substituted:
            srcs.append("expert call from the internal structural-alert screen")
        if statistical_substituted:
            srcs.append("statistical call from the internal structural-alert screen")
        note = f" ({'; '.join(srcs)})" if srcs else ""
        parts.append(
            f"Dual (Q)SAR: expert={expert_call}, statistical={statistical_call} -> "
            f"{concordance}{note}. ICH M7 requires two complementary systems; supply both "
            "formal (Q)SAR results for a complete assessment."
        )
        if concordance == "discordant":
            parts.append(
                "Discordant (Q)SAR results are treated as positive (Class 3) pending expert "
                "review to resolve the conflict."
            )
    parts.append(f"Assigned ICH M7 {_CLASS_DEFINITION[m7_class]}")
    if ttc is not None:
        parts.append(f"Acceptable intake: staged TTC {ttc:g} microg/day for {duration_band}.")
    parts.append(action)
    return " ".join(parts)


def m7_rule_set() -> dict[str, Any]:
    """The encoded M7 logic parameters — the auditable rule-set."""

    return {
        "guideline": GUIDELINE,
        "title": TITLE,
        "class_scheme_reference": CLASS_SCHEME_REFERENCE,
        "ttc_table_reference": TTC_TABLE_REFERENCE,
        "effective_year": EFFECTIVE_YEAR,
        "class_definitions": {str(k): v for k, v in _CLASS_DEFINITION.items()},
        "cohort_of_concern": _COC_DEFINITION,
        "lifetime_ttc_ug_per_day": LIFETIME_TTC_UG_PER_DAY,
        "staged_ttc_ug_per_day": {
            "<=1_month": 120.0,
            ">1-12_months": 20.0,
            ">1-10_years": 10.0,
            ">10_years_lifetime": LIFETIME_TTC_UG_PER_DAY,
        },
        "structural_alerts": [name for name, _ in _ALERT_SMARTS],
        "coc_structural_patterns": [name for name, _ in _COC_SMARTS],
    }


_RULE_SET_VERSION = rule_set_version(m7_rule_set())
