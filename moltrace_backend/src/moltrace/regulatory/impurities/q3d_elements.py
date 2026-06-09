"""ICH Q3D(R2) elemental-impurity engine (Prompt 3).

Returns the ICH Q3D permitted daily exposure (PDE) for an elemental impurity by
administration route, the 30%-of-PDE control threshold, the permitted product
concentration for a given daily dose, and a class-driven Q3D risk assessment over
a drug product's components and manufacturing equipment.

Deterministic-first: pure, auditable table lookups + arithmetic over a
content-versioned rule-set — **no model in the numeric path**. Decision-support:
every value carries its regulatory basis + table reference and must be verified
against the official ICH Q3D(R2) source and signed off by a qualified reviewer
before any filing or release decision. The risk-assessment outputs are a starting
point for a documented Q3D assessment, not a regulatory determination.

Route coverage. The PDEs for the **oral, parenteral, and inhalation** routes
(ICH Q3D(R2) Table A.2.1, all 24 elements) are encoded from the canonical ICH
values. The **cutaneous / transcutaneous** PDEs (the Q3D(R2) addition) are **not
encoded** in this rule-set: those routes are recognised and validated, but return
``route_data_available = False`` with ``pde = None`` (an explicit "not encoded",
never a guessed limit) and a note to consult the official Q3D(R2) cutaneous
appendix. Extend the table once those values are confirmed.

Control threshold. ICH Q3D defines a **control threshold** of 30% of the
established PDE: if the elemental impurity level is expected to be consistently
below it, additional controls are not required. It is reported here for each
element/route as ``control_threshold = 0.30 x PDE``.

Concentration. The permitted product concentration follows ICH Q3D Option 1:
``permitted concentration (ppm) = PDE (microg/day) / max daily dose (g/day)``
(1 microg/g = 1 ppm).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from moltrace.regulatory.infra.validation import (
    ALLOWED_ROUTES,
    ValidationFailure,
    ValidationReport,
    assert_valid_dose,
)
from moltrace.regulatory.infra.versioning import content_hash, rule_set_version

__all__ = [
    "ConcentrationLimit",
    "ElementPDE",
    "ElementRiskItem",
    "ElementalRiskAssessment",
    "calculate_concentration_limit",
    "get_element_pde",
    "q3d_rule_set",
    "risk_assessment_report",
]

GUIDELINE = "ICH Q3D(R2)"
TITLE = "Guideline for Elemental Impurities"
TABLE_REFERENCE = "ICH Q3D(R2) Table A.2.1"
EFFECTIVE_YEAR = "2022"

# ICH Q3D control threshold = 30% of the established PDE (guideline section 3.2).
CONTROL_THRESHOLD_FRACTION = 0.30

# Routes whose PDEs are encoded from ICH Q3D(R2) Table A.2.1.
_ENCODED_ROUTES = ("oral", "parenteral", "inhalation")
_ROUTE_COLUMN = {"oral": 3, "parenteral": 4, "inhalation": 5}
# Recognised but not encoded (the Q3D(R2) cutaneous appendix).
_CUTANEOUS_ROUTES = frozenset({"cutaneous", "transcutaneous"})

_CLASS_DESCRIPTION = {
    "1": (
        "Class 1 - human toxicants (As, Cd, Hg, Pb) with limited use in manufacturing; "
        "commonly present in mined materials and water; assess all sources for all routes."
    ),
    "2A": (
        "Class 2A - relatively high probability of occurrence; assess all sources for all "
        "routes."
    ),
    "2B": (
        "Class 2B - reduced probability of occurrence (low natural abundance); may be "
        "excluded from the risk assessment unless intentionally added."
    ),
    "3": (
        "Class 3 - low oral toxicity (oral PDE > 500 microg/day); assess for the parenteral "
        "and inhalation routes, or if intentionally added."
    ),
}

_DECISION_SUPPORT_NOTE = (
    "Decision-support only: verify the PDE, class, and limit against the official ICH "
    "Q3D(R2) source and obtain qualified sign-off before any filing or release use."
)
_CUTANEOUS_NOTE = (
    "Cutaneous / transcutaneous PDEs are not encoded in this rule-set; consult the "
    "official ICH Q3D(R2) cutaneous appendix before relying on a limit for this route."
)

# ICH Q3D(R2) Table A.2.1 - PDEs in microg/day.
# (symbol, name, class, oral, parenteral, inhalation)
_TABLE: tuple[tuple[str, str, str, float, float, float], ...] = (
    # --- Class 1 -------------------------------------------------------- #
    ("As", "Arsenic", "1", 15.0, 15.0, 2.0),
    ("Cd", "Cadmium", "1", 5.0, 2.0, 3.0),
    ("Hg", "Mercury", "1", 30.0, 3.0, 1.0),
    ("Pb", "Lead", "1", 5.0, 5.0, 5.0),
    # --- Class 2A ------------------------------------------------------- #
    ("Co", "Cobalt", "2A", 50.0, 5.0, 3.0),
    ("Ni", "Nickel", "2A", 200.0, 20.0, 5.0),
    ("V", "Vanadium", "2A", 100.0, 10.0, 1.0),
    # --- Class 2B ------------------------------------------------------- #
    ("Ag", "Silver", "2B", 150.0, 15.0, 7.0),
    ("Au", "Gold", "2B", 300.0, 300.0, 3.0),
    ("Ir", "Iridium", "2B", 100.0, 10.0, 1.0),
    ("Os", "Osmium", "2B", 100.0, 10.0, 1.0),
    ("Pd", "Palladium", "2B", 100.0, 10.0, 1.0),
    ("Pt", "Platinum", "2B", 100.0, 10.0, 1.0),
    ("Rh", "Rhodium", "2B", 100.0, 10.0, 1.0),
    ("Ru", "Ruthenium", "2B", 100.0, 10.0, 1.0),
    ("Se", "Selenium", "2B", 150.0, 80.0, 130.0),
    ("Tl", "Thallium", "2B", 8.0, 8.0, 8.0),
    # --- Class 3 -------------------------------------------------------- #
    ("Ba", "Barium", "3", 1400.0, 700.0, 300.0),
    ("Cr", "Chromium", "3", 11000.0, 1100.0, 3.0),
    ("Cu", "Copper", "3", 3000.0, 300.0, 30.0),
    ("Li", "Lithium", "3", 550.0, 250.0, 25.0),
    ("Mo", "Molybdenum", "3", 3000.0, 1500.0, 10.0),
    ("Sb", "Antimony", "3", 1200.0, 90.0, 20.0),
    ("Sn", "Tin", "3", 6000.0, 600.0, 60.0),
)

# Common pharmaceutical equipment materials -> Q3D elements they can contribute.
# Heuristic alloy knowledge base (keyword in equipment string -> elements).
_EQUIPMENT_ELEMENTS: tuple[tuple[str, frozenset[str]], ...] = (
    ("stainless steel", frozenset({"Cr", "Ni", "Mo", "V"})),
    ("316", frozenset({"Cr", "Ni", "Mo"})),
    ("304", frozenset({"Cr", "Ni"})),
    ("hastelloy", frozenset({"Ni", "Cr", "Mo", "Co"})),
    ("inconel", frozenset({"Ni", "Cr", "Mo", "Co"})),
    ("monel", frozenset({"Ni", "Cu"})),
    ("nickel", frozenset({"Ni"})),
    ("cobalt-chrome", frozenset({"Co", "Cr"})),
    ("cobalt chrome", frozenset({"Co", "Cr"})),
)

_BY_SYMBOL: dict[str, int] = {}
_BY_NAME: dict[str, int] = {}
for _i, _row in enumerate(_TABLE):
    _BY_SYMBOL[_row[0].lower()] = _i
    _BY_NAME[_row[1].lower()] = _i


def _assert_route(route: str) -> None:
    if route not in ALLOWED_ROUTES:
        ValidationReport(
            success=False,
            failures=(
                ValidationFailure(
                    "route", f"unknown route {route!r}; expected one of {sorted(ALLOWED_ROUTES)}"
                ),
            ),
            n_checks=1,
        ).raise_for_status()


def _lookup_index(element: str) -> int:
    key = str(element).strip().lower()
    idx = _BY_SYMBOL.get(key)
    if idx is None:
        idx = _BY_NAME.get(key)
    if idx is None:
        ValidationReport(
            success=False,
            failures=(
                ValidationFailure(
                    "element", f"{element!r} is not one of the 24 ICH Q3D-listed elements"
                ),
            ),
            n_checks=1,
        ).raise_for_status()
    return idx  # type: ignore[return-value]


@dataclass(frozen=True)
class ElementPDE:
    """An ICH Q3D PDE for one element by route, with class + control threshold."""

    element: str
    element_name: str
    element_class: str
    class_description: str
    route: str
    pde_ug_per_day: float | None
    control_threshold_ug_per_day: float | None
    route_data_available: bool
    regulatory_basis: str
    table_reference: str
    notes: tuple[str, ...]
    rule_set_version: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "element": self.element,
            "element_name": self.element_name,
            "element_class": self.element_class,
            "class_description": self.class_description,
            "route": self.route,
            "pde_ug_per_day": self.pde_ug_per_day,
            "control_threshold_ug_per_day": self.control_threshold_ug_per_day,
            "route_data_available": self.route_data_available,
            "regulatory_basis": self.regulatory_basis,
            "table_reference": self.table_reference,
            "notes": list(self.notes),
            "rule_set_version": self.rule_set_version,
        }

    def content_hash(self) -> str:
        return content_hash(self.as_dict())


@dataclass(frozen=True)
class ConcentrationLimit:
    """The permitted product concentration for one element at a given daily dose."""

    element: str
    element_class: str
    route: str
    max_daily_dose_g: float
    pde_ug_per_day: float | None
    permitted_concentration_ppm: float | None
    control_threshold_ppm: float | None
    route_data_available: bool
    regulatory_basis: str
    table_reference: str
    notes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "element": self.element,
            "element_class": self.element_class,
            "route": self.route,
            "max_daily_dose_g": self.max_daily_dose_g,
            "pde_ug_per_day": self.pde_ug_per_day,
            "permitted_concentration_ppm": self.permitted_concentration_ppm,
            "control_threshold_ppm": self.control_threshold_ppm,
            "route_data_available": self.route_data_available,
            "regulatory_basis": self.regulatory_basis,
            "table_reference": self.table_reference,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ElementRiskItem:
    """The Q3D risk-assessment line for one element."""

    element: str
    element_name: str
    element_class: str
    likely_present: bool
    rationale: str
    potential_sources: tuple[str, ...]
    pde_ug_per_day: float | None
    control_threshold_ug_per_day: float | None
    permitted_concentration_ppm: float | None
    assessment_required: bool
    exclusion_applies: bool
    recommended_action: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "element": self.element,
            "element_name": self.element_name,
            "element_class": self.element_class,
            "likely_present": self.likely_present,
            "rationale": self.rationale,
            "potential_sources": list(self.potential_sources),
            "pde_ug_per_day": self.pde_ug_per_day,
            "control_threshold_ug_per_day": self.control_threshold_ug_per_day,
            "permitted_concentration_ppm": self.permitted_concentration_ppm,
            "assessment_required": self.assessment_required,
            "exclusion_applies": self.exclusion_applies,
            "recommended_action": self.recommended_action,
        }


@dataclass(frozen=True)
class ElementalRiskAssessment:
    """A full ICH Q3D risk assessment over all 24 elements for one product/route."""

    route: str
    max_daily_dose_g: float
    route_data_available: bool
    components: tuple[str, ...]
    equipment: tuple[str, ...]
    elements: tuple[ElementRiskItem, ...]
    n_assessment_required: int
    n_exclusion_applies: int
    regulatory_basis: str
    table_reference: str
    notes: tuple[str, ...]
    rule_set_version: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "max_daily_dose_g": self.max_daily_dose_g,
            "route_data_available": self.route_data_available,
            "components": list(self.components),
            "equipment": list(self.equipment),
            "elements": [e.as_dict() for e in self.elements],
            "n_assessment_required": self.n_assessment_required,
            "n_exclusion_applies": self.n_exclusion_applies,
            "regulatory_basis": self.regulatory_basis,
            "table_reference": self.table_reference,
            "notes": list(self.notes),
            "rule_set_version": self.rule_set_version,
        }

    def content_hash(self) -> str:
        return content_hash(self.as_dict())


def get_element_pde(element: str, route: str) -> ElementPDE:
    """Return the ICH Q3D PDE for ``element`` by ``route``.

    ``element`` is a symbol (e.g. ``'As'``, ``'Pb'``) or name (e.g. ``'arsenic'``).
    Oral / parenteral / inhalation PDEs are encoded from Table A.2.1; cutaneous /
    transcutaneous return ``route_data_available = False`` with ``pde = None`` (an
    explicit "not encoded", never a guess). An element outside the Q3D list of 24
    fails loud.
    """

    _assert_route(route)
    symbol, name, element_class, oral, parenteral, inhalation = _TABLE[_lookup_index(element)]

    notes = [_DECISION_SUPPORT_NOTE]
    if route in _CUTANEOUS_ROUTES:
        pde: float | None = None
        control: float | None = None
        available = False
        notes.insert(0, _CUTANEOUS_NOTE)
    else:
        pde = (oral, parenteral, inhalation)[_ROUTE_COLUMN[route] - 3]
        control = pde * CONTROL_THRESHOLD_FRACTION
        available = True

    return ElementPDE(
        element=symbol,
        element_name=name,
        element_class=element_class,
        class_description=_CLASS_DESCRIPTION[element_class],
        route=route,
        pde_ug_per_day=pde,
        control_threshold_ug_per_day=control,
        route_data_available=available,
        regulatory_basis=f"{GUIDELINE}: {TITLE}",
        table_reference=TABLE_REFERENCE,
        notes=tuple(notes),
        rule_set_version=_RULE_SET_VERSION,
    )


def calculate_concentration_limit(
    element: str, route: str, max_daily_dose_g: float
) -> ConcentrationLimit:
    """Permitted product concentration for ``element`` at ``max_daily_dose_g``.

    ``permitted concentration (ppm) = PDE (microg/day) / max daily dose (g/day)``
    (ICH Q3D Option 1). The 30% control threshold is converted to ppm the same way.
    A cutaneous / transcutaneous route returns ``None`` limits (route not encoded).
    """

    assert_valid_dose({"daily_dose_g": max_daily_dose_g, "route": route})
    pde_info = get_element_pde(element, route)

    if not pde_info.route_data_available or pde_info.pde_ug_per_day is None:
        return ConcentrationLimit(
            element=pde_info.element,
            element_class=pde_info.element_class,
            route=route,
            max_daily_dose_g=float(max_daily_dose_g),
            pde_ug_per_day=None,
            permitted_concentration_ppm=None,
            control_threshold_ppm=None,
            route_data_available=False,
            regulatory_basis=f"{GUIDELINE}: {TITLE}",
            table_reference=TABLE_REFERENCE,
            notes=(_CUTANEOUS_NOTE, _DECISION_SUPPORT_NOTE),
        )

    permitted_ppm = pde_info.pde_ug_per_day / float(max_daily_dose_g)
    control_ppm = (pde_info.control_threshold_ug_per_day or 0.0) / float(max_daily_dose_g)
    return ConcentrationLimit(
        element=pde_info.element,
        element_class=pde_info.element_class,
        route=route,
        max_daily_dose_g=float(max_daily_dose_g),
        pde_ug_per_day=pde_info.pde_ug_per_day,
        permitted_concentration_ppm=permitted_ppm,
        control_threshold_ppm=control_ppm,
        route_data_available=True,
        regulatory_basis=f"{GUIDELINE}: {TITLE}",
        table_reference=TABLE_REFERENCE,
        notes=(
            "Permitted concentration = PDE / max daily dose (ICH Q3D Option 1).",
            "Control threshold (ppm) = 30% of the permitted concentration.",
            _DECISION_SUPPORT_NOTE,
        ),
    )


def _sources_in_strings(name: str, haystacks: tuple[str, ...]) -> list[str]:
    needle = name.lower()
    return [h for h in haystacks if needle in h.lower()]


def _equipment_sources(symbol: str, equipment: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for equip in equipment:
        low = equip.lower()
        for keyword, elements in _EQUIPMENT_ELEMENTS:
            if keyword in low and symbol in elements:
                hits.append(equip)
                break
    return hits


def risk_assessment_report(
    drug_product_components: Mapping[str, float],
    manufacturing_equipment: list[str],
    route: str,
    max_daily_dose_g: float,
) -> ElementalRiskAssessment:
    """Generate a class-driven ICH Q3D elemental-impurity risk assessment.

    For each of the 24 Q3D elements, decides whether it is likely present (Class 1
    and 2A always; Class 2B only if intentionally added or equipment-sourced; Class 3
    for the parenteral/inhalation routes or if added/sourced), identifies the
    potential source(s), and gives the permitted concentration and the recommended
    action (include in the assessment vs. apply an intentional-addition / route-based
    exclusion). Intentional addition is detected by element name in a component;
    equipment sourcing via a heuristic alloy knowledge base. Cutaneous / transcutaneous
    routes return structural results with ``None`` limits (route not encoded).
    """

    assert_valid_dose({"daily_dose_g": max_daily_dose_g, "route": route})
    components = tuple(str(c) for c in drug_product_components)
    equipment = tuple(str(e) for e in manufacturing_equipment)
    route_available = route not in _CUTANEOUS_ROUTES

    items: list[ElementRiskItem] = []
    for symbol, name, element_class, *route_pdes in _TABLE:
        added_in = _sources_in_strings(name, components)
        intentionally_added = bool(added_in)
        equip_hits = _equipment_sources(symbol, equipment) + _sources_in_strings(name, equipment)
        equipment_sourced = bool(equip_hits)

        if element_class in ("1", "2A"):
            likely = True
            rationale = (
                f"Class {element_class}: assessed for all routes regardless of intentional "
                "addition (commonly present from materials, water, or equipment)."
            )
        elif element_class == "2B":
            likely = intentionally_added or equipment_sourced
            rationale = (
                "Class 2B: present via intentional addition or equipment."
                if likely
                else "Class 2B: low natural abundance, not intentionally added and no "
                "identified source - intentional-addition exclusion may apply."
            )
        else:  # Class 3
            likely = (route != "oral") or intentionally_added or equipment_sourced
            if route == "oral" and not likely:
                rationale = (
                    "Class 3: low oral toxicity (high oral PDE), not intentionally added - "
                    "may be excluded for the oral route."
                )
            else:
                rationale = (
                    f"Class 3: assessed for the {route} route (or due to intentional "
                    "addition / equipment source)."
                )

        sources: list[str] = []
        if likely and element_class in ("1", "2A"):
            sources.extend(["drug substance / excipients (mined materials)", "water"])
        elif likely:
            sources.append("drug substance / excipients")
        if intentionally_added:
            sources.append(f"intentional addition (components: {', '.join(added_in)})")
        if equipment_sourced:
            uniq = list(dict.fromkeys(equip_hits))
            sources.append(f"manufacturing equipment ({', '.join(uniq)})")
        if likely and route in ("parenteral", "inhalation") and element_class in ("1", "2A"):
            sources.append("container closure system (leaching)")
        if not sources:
            sources.append("no identified source")

        pde_val: float | None = None
        control_val: float | None = None
        permitted: float | None = None
        if route_available:
            pde_val = route_pdes[_ROUTE_COLUMN[route] - 3]
            control_val = pde_val * CONTROL_THRESHOLD_FRACTION
            permitted = pde_val / float(max_daily_dose_g)

        if not route_available:
            action = (
                "Cutaneous/transcutaneous PDE not encoded - verify the ICH Q3D(R2) cutaneous "
                "appendix before setting a limit."
            )
            assessment_required = likely
            exclusion_applies = not likely
        elif likely:
            action = (
                f"Include in the risk assessment; demonstrate control below the 30% control "
                f"threshold ({control_val:g} microg/day) via analytical testing or qualified "
                "process / supplier controls."
            )
            assessment_required = True
            exclusion_applies = False
        else:
            action = (
                "May apply an intentional-addition / route-based exclusion; document the "
                "justification (no identified source)."
            )
            assessment_required = False
            exclusion_applies = True

        items.append(
            ElementRiskItem(
                element=symbol,
                element_name=name,
                element_class=element_class,
                likely_present=likely,
                rationale=rationale,
                potential_sources=tuple(sources),
                pde_ug_per_day=pde_val,
                control_threshold_ug_per_day=control_val,
                permitted_concentration_ppm=permitted,
                assessment_required=assessment_required,
                exclusion_applies=exclusion_applies,
                recommended_action=action,
            )
        )

    notes = [
        "Class 1 and 2A elements are assessed for all routes; Class 2B may be excluded "
        "unless intentionally added; Class 3 is assessed for parenteral/inhalation or if added.",
        "Intentional addition is inferred from element names in the component list; "
        "equipment sourcing from a heuristic alloy knowledge base - confirm against the "
        "actual materials of construction and supplier data.",
        _DECISION_SUPPORT_NOTE,
    ]
    if not route_available:
        notes.insert(0, _CUTANEOUS_NOTE)

    return ElementalRiskAssessment(
        route=route,
        max_daily_dose_g=float(max_daily_dose_g),
        route_data_available=route_available,
        components=components,
        equipment=equipment,
        elements=tuple(items),
        n_assessment_required=sum(1 for it in items if it.assessment_required),
        n_exclusion_applies=sum(1 for it in items if it.exclusion_applies),
        regulatory_basis=f"{GUIDELINE}: {TITLE}",
        table_reference=TABLE_REFERENCE,
        notes=tuple(notes),
        rule_set_version=_RULE_SET_VERSION,
    )


def q3d_rule_set() -> dict[str, Any]:
    """The encoded ICH Q3D(R2) Table A.2.1 PDEs — the auditable rule-set."""

    return {
        "guideline": GUIDELINE,
        "title": TITLE,
        "table_reference": TABLE_REFERENCE,
        "effective_year": EFFECTIVE_YEAR,
        "control_threshold_fraction": CONTROL_THRESHOLD_FRACTION,
        "encoded_routes": list(_ENCODED_ROUTES),
        "elements": [
            {
                "element": symbol,
                "element_name": name,
                "element_class": element_class,
                "oral_pde_ug_per_day": oral,
                "parenteral_pde_ug_per_day": parenteral,
                "inhalation_pde_ug_per_day": inhalation,
            }
            for (symbol, name, element_class, oral, parenteral, inhalation) in _TABLE
        ],
    }


_RULE_SET_VERSION = rule_set_version(q3d_rule_set())
