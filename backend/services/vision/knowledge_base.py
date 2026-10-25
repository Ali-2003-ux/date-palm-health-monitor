"""Date palm disease knowledge base.

Grounds AI outputs in agronomic reality: normalises disease names coming
from either inference provider, supplies default severity and actionable
treatment protocols, and decides the overall inspection status.
"""

from __future__ import annotations

from backend.models import InspectionStatus, Severity


class Disease:
    """Catalog entry for one disease / pest / stress condition."""

    __slots__ = (
        "aliases",
        "default_severity",
        "display_name",
        "is_critical",
        "key",
        "treatment_steps",
    )

    def __init__(
        self,
        key: str,
        display_name: str,
        default_severity: Severity,
        is_critical: bool,
        treatment_steps: list[str],
        aliases: tuple[str, ...] = (),
    ) -> None:
        self.key = key
        self.display_name = display_name
        self.default_severity = default_severity
        self.is_critical = is_critical
        self.treatment_steps = treatment_steps
        self.aliases = aliases


HEALTHY = Disease(
    key="healthy",
    display_name="Healthy",
    default_severity=Severity.LOW,
    is_critical=False,
    treatment_steps=[],
    aliases=("no disease", "none", "normal"),
)

DISEASES: dict[str, Disease] = {
    disease.key: disease
    for disease in [
        HEALTHY,
        Disease(
            key="red_palm_weevil",
            display_name="Red Palm Weevil",
            default_severity=Severity.HIGH,
            is_critical=True,
            treatment_steps=[
                ("Inject an approved systemic insecticide (e.g. imidaclorid or "
                "emamectin benzoate) into the trunk feeding galleries."),
                ("Install aggregation pheromone traps (ferrugineol + kairomone) "
                "at 1 trap per hectare and monitor weekly."),
                ("Remove and burn severely infested offshoots or fronds; do not "
                "compost infested material."),
                ("Seal trunk wounds and frond removal cuts with tar or Bordeaux "
                "paste to prevent egg-laying."),
                ("Re-inspect the tree and its 50 m radius neighbours every 2 "
                "weeks for at least 2 months."),
            ],
            aliases=("rpw", "rhynchophorus ferrugineus", "weevil"),
        ),
        Disease(
            key="graphiola_leaf_spot",
            display_name="Graphiola Leaf Spot",
            default_severity=Severity.LOW,
            is_critical=False,
            treatment_steps=[
                "Remove and destroy heavily infected older fronds.",
                "Improve airflow in the plantation by pruning dense canopies.",
                ("Apply a copper-based fungicide (e.g. Bordeaux mixture) during "
                "humid periods."),
                "Avoid overhead irrigation that keeps fronds wet overnight.",
            ],
            aliases=("graphiola", "false smut", "graphiola phoenicis"),
        ),
        Disease(
            key="diplodia_disease",
            display_name="Diplodia Bud Rot / Frond Rot",
            default_severity=Severity.MEDIUM,
            is_critical=False,
            treatment_steps=[
                "Prune out infected fronds, cutting well into healthy tissue.",
                ("Apply a thiophanate-methyl or copper fungicide to the crown "
                "and cut surfaces."),
                ("Disinfect pruning tools between trees (10% bleach or 70% "
                "alcohol)."),
                "Reduce mechanical damage near the crown during harvest.",
            ],
            aliases=("diplodia", "botryodiplodia", "bud rot"),
        ),
        Disease(
            key="pestalotiopsis_leaf_spot",
            display_name="Pestalotiopsis Leaf Spot",
            default_severity=Severity.LOW,
            is_critical=False,
            treatment_steps=[
                "Remove and burn affected fronds to reduce inoculum.",
                ("Apply a protectant fungicide (mancozeb or copper) on new "
                "growth during humid weather."),
                "Avoid water stress — stressed palms are far more susceptible.",
            ],
            aliases=("pestalotiopsis",),
        ),
        Disease(
            key="fusarium_wilt",
            display_name="Fusarium Wilt (Bayoud)",
            default_severity=Severity.HIGH,
            is_critical=True,
            treatment_steps=[
                ("CONFIRM with laboratory culture — Bayoud is a quarantine "
                "organism in most countries."),
                ("If confirmed: eradicate the tree, uproot and burn it, and "
                "restrict movement of soil and plant material from the focus."),
                ("Disinfect all tools, machinery and irrigation equipment that "
                "touched the tree."),
                ("Plant resistant cultivars (e.g. Bou Feggous, Tadment) when "
                "replanting."),
                "Notify your local agricultural extension service.",
            ],
            aliases=("bayoud", "fusarium oxysporum", "fusarium"),
        ),
        Disease(
            key="leaf_rust",
            display_name="Leaf Rust",
            default_severity=Severity.LOW,
            is_critical=False,
            treatment_steps=[
                ("Apply a sulfur-based or systemic fungicide at first symptom "
                "appearance."),
                ("Improve ventilation between trees and avoid excess nitrogen "
                "fertilisation."),
                "Collect and destroy fallen infected fronds.",
            ],
            aliases=("rust",),
        ),
        Disease(
            key="fruit_rot",
            display_name="Fruit Rot / Bunch Rot",
            default_severity=Severity.MEDIUM,
            is_critical=False,
            treatment_steps=[
                "Remove and destroy mummified fruits and rotten bunches.",
                ("Protect bunches with netting or paper bags against rain and "
                "insects."),
                ("Apply a copper fungicide after pollination and before rain "
                "season."),
                ("Harvest at the correct stage; avoid leaving over-ripe fruit "
                "on the bunch."),
            ],
            aliases=("bunch rot", "fruit disease", "brown rot"),
        ),
        Disease(
            key="potassium_deficiency",
            display_name="Potassium Deficiency",
            default_severity=Severity.LOW,
            is_critical=False,
            treatment_steps=[
                ("Apply potassium sulfate (K2SO4) at 1–1.5 kg per mature palm "
                "per year, split into 2–3 applications."),
                "Fertigate through the irrigation system for faster uptake.",
                "Confirm with a leaf tissue analysis (pinnae from frond 17).",
            ],
            aliases=("k deficiency", "potassium"),
        ),
        Disease(
            key="magnesium_deficiency",
            display_name="Magnesium Deficiency",
            default_severity=Severity.LOW,
            is_critical=False,
            treatment_steps=[
                "Apply magnesium sulfate or Kieserite around the root zone.",
                "Check soil pH — magnesium uptake drops in acidic soils.",
                "Use a balanced palm-specific fertiliser for maintenance.",
            ],
            aliases=("mg deficiency", "magnesium"),
        ),
        Disease(
            key="nitrogen_deficiency",
            display_name="Nitrogen Deficiency",
            default_severity=Severity.LOW,
            is_critical=False,
            treatment_steps=[
                "Apply urea or ammonium sulfate through fertigation.",
                "Add organic matter / manure around the root zone.",
                "Re-assess the overall fertilisation programme.",
            ],
            aliases=("n deficiency", "nitrogen"),
        ),
        Disease(
            key="drought_stress",
            display_name="Drought / Water Stress",
            default_severity=Severity.MEDIUM,
            is_critical=False,
            treatment_steps=[
                "Audit the irrigation system for clogged emitters and leaks.",
                "Increase irrigation frequency during fruit set and summer.",
                "Mulch the root zone to reduce evaporation.",
            ],
            aliases=("water stress", "drought", "heat stress"),
        ),
    ]
}

_ALIASES_INDEX: dict[str, Disease] = {}
for _disease in DISEASES.values():
    _ALIASES_INDEX[_disease.key] = _disease
    _ALIASES_INDEX[_disease.display_name.lower()] = _disease
    for _alias in _disease.aliases:
        _ALIASES_INDEX[_alias.lower()] = _disease


def lookup_disease(name: str | None) -> Disease | None:
    """Resolve a provider-reported disease name to a catalog entry.

    Matches keys, display names and aliases case-insensitively. Returns
    None for healthy/no-disease indicators and for names we cannot map
    (the caller keeps the raw name and falls back to defaults).
    """
    if not name:
        return None
    cleaned = name.strip().lower()
    if cleaned in {"", "null", "none", "healthy", "no disease", "n/a"}:
        return None
    return _ALIASES_INDEX.get(cleaned)


def derive_status(
    is_healthy: bool, disease: Disease | None, severity: Severity | None
) -> InspectionStatus:
    """Overall verdict: healthy / infected / critical.

    A tree is CRITICAL when a high-severity or quarantine-critical disease
    (e.g. advanced Red Palm Weevil, Bayoud) is present — those demand
    immediate intervention.
    """
    if is_healthy or disease is None or disease is HEALTHY:
        return InspectionStatus.HEALTHY
    if severity == Severity.HIGH or disease.is_critical:
        return InspectionStatus.CRITICAL
    return InspectionStatus.INFECTED
