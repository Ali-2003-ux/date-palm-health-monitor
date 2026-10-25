"""Date palm disease knowledge base.

Grounds AI outputs in agronomic reality: normalises disease names coming
from either inference provider, supplies default severity, the causal
agent, actionable treatment protocols and preventive measures, and
decides the overall inspection status.
"""

from __future__ import annotations

from backend.models import InspectionStatus, Severity


class Disease:
    """Catalog entry for one disease / pest / stress condition."""

    __slots__ = (
        "aliases",
        "cause",
        "default_severity",
        "display_name",
        "is_critical",
        "key",
        "prevention",
        "treatment_steps",
    )

    def __init__(
        self,
        key: str,
        display_name: str,
        default_severity: Severity,
        is_critical: bool,
        cause: str | None,
        treatment_steps: list[str],
        prevention: list[str],
        aliases: tuple[str, ...] = (),
    ) -> None:
        self.key = key
        self.display_name = display_name
        self.default_severity = default_severity
        self.is_critical = is_critical
        self.cause = cause
        self.treatment_steps = treatment_steps
        self.prevention = prevention
        self.aliases = aliases


HEALTHY = Disease(
    key="healthy",
    display_name="Healthy",
    default_severity=Severity.LOW,
    is_critical=False,
    cause=None,
    treatment_steps=[],
    prevention=[
        "Apply a balanced NPK fertilisation programme every year.",
        "Audit the irrigation system and schedule seasonally.",
        "Inspect crowns and fronds every 2-4 weeks for early symptoms.",
    ],
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
            cause=(
                "Larvae of the red palm weevil (Rhynchophorus ferrugineus) "
                "tunnel into the trunk and crown after entering through "
                "wounds or fresh pruning cuts; internal feeding is invisible "
                "until the damage is advanced."
            ),
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
            prevention=[
                "Quarantine and inspect new offshoots before planting.",
                "Apply preventive insecticide treatments in high-risk areas.",
                ("Never prune during the weevil's active flight season where "
                "local regulations advise against it."),
                "Avoid unnecessary trunk wounds during field operations.",
            ],
            aliases=("rpw", "rhynchophorus ferrugineus", "weevil"),
        ),
        Disease(
            key="graphiola_leaf_spot",
            display_name="Graphiola Leaf Spot",
            default_severity=Severity.LOW,
            is_critical=False,
            cause=(
                "The fungus Graphiola phoenicis thrives in warm, humid "
                "coastal climates and produces the characteristic black "
                "sori (spots) with yellow halos on older fronds."
            ),
            treatment_steps=[
                "Remove and destroy heavily infected older fronds.",
                "Improve airflow in the plantation by pruning dense canopies.",
                ("Apply a copper-based fungicide (e.g. Bordeaux mixture) during "
                "humid periods."),
                "Avoid overhead irrigation that keeps fronds wet overnight.",
            ],
            prevention=[
                "Plant with wide spacing to keep fronds dry and ventilated.",
                "Irrigate at the root zone, never over the canopy.",
                "Routinely remove senescing fronds before sporulation season.",
                "Choose tolerant cultivars in humid regions.",
            ],
            aliases=("graphiola", "false smut", "graphiola phoenicis"),
        ),
        Disease(
            key="diplodia_disease",
            display_name="Diplodia Bud Rot / Frond Rot",
            default_severity=Severity.MEDIUM,
            is_critical=False,
            cause=(
                "Diplodia (Botryodiplodia) fungi enter the crown or frond "
                "bases through mechanical wounds, pruning cuts or insect "
                "damage and rot the tissue under humid conditions."
            ),
            treatment_steps=[
                "Prune out infected fronds, cutting well into healthy tissue.",
                ("Apply a thiophanate-methyl or copper fungicide to the crown "
                "and cut surfaces."),
                ("Disinfect pruning tools between trees (10% bleach or 70% "
                "alcohol)."),
                "Reduce mechanical damage near the crown during harvest.",
            ],
            prevention=[
                "Disinfect all pruning tools between trees.",
                "Protect the crown from mechanical injury during harvest.",
                "Keep palms vigorous — stressed tissue is infected first.",
            ],
            aliases=("diplodia", "botryodiplodia", "bud rot"),
        ),
        Disease(
            key="pestalotiopsis_leaf_spot",
            display_name="Pestalotiopsis Leaf Spot",
            default_severity=Severity.LOW,
            is_critical=False,
            cause=(
                "Pestalotiopsis is an opportunistic fungus that colonises "
                "fronds weakened by water stress, nutrient imbalance or "
                "physical injury, spreading fastest in humid weather."
            ),
            treatment_steps=[
                "Remove and burn affected fronds to reduce inoculum.",
                ("Apply a protectant fungicide (mancozeb or copper) on new "
                "growth during humid weather."),
                "Avoid water stress — stressed palms are far more susceptible.",
            ],
            prevention=[
                "Maintain balanced irrigation and nutrition year-round.",
                "Avoid leaf injuries during field work.",
                "Improve plantation ventilation and spacing.",
            ],
            aliases=("pestalotiopsis",),
        ),
        Disease(
            key="fusarium_wilt",
            display_name="Fusarium Wilt (Bayoud)",
            default_severity=Severity.HIGH,
            is_critical=True,
            cause=(
                "The soil-borne fungus Fusarium oxysporum f.sp. albedinis "
                "colonises the vascular tissue and spreads through infested "
                "soil, irrigation water, contaminated tools and infected "
                "offshoots. There is no cure once vascular infection sets in."
            ),
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
            prevention=[
                "Use certified disease-free offshoots from reliable sources.",
                ("Strictly disinfect tools and machinery before moving between "
                "plantations."),
                "In risk zones, replant only with resistant cultivars.",
                ("Never replant date palms into soil where Bayoud was "
                "confirmed."),
            ],
            aliases=("bayoud", "fusarium oxysporum", "fusarium"),
        ),
        Disease(
            key="leaf_rust",
            display_name="Leaf Rust",
            default_severity=Severity.LOW,
            is_critical=False,
            cause=(
                "Rust fungi form orange-brown pustules on fronds under humid, "
                "mild conditions, favouring dense canopies and excess "
                "nitrogen fertilisation."
            ),
            treatment_steps=[
                ("Apply a sulfur-based or systemic fungicide at first symptom "
                "appearance."),
                ("Improve ventilation between trees and avoid excess nitrogen "
                "fertilisation."),
                "Collect and destroy fallen infected fronds.",
            ],
            prevention=[
                "Balance nitrogen — lush soft growth is most susceptible.",
                "Remove and compost away (or burn) fallen infected fronds.",
                "Maintain tree spacing for airflow.",
            ],
            aliases=("rust",),
        ),
        Disease(
            key="fruit_rot",
            display_name="Fruit Rot / Bunch Rot",
            default_severity=Severity.MEDIUM,
            is_critical=False,
            cause=(
                "Fungal and bacterial rot agents attack bunches after rain, "
                "high humidity or insect punctures, especially on "
                "over-mature or damaged fruit."
            ),
            treatment_steps=[
                "Remove and destroy mummified fruits and rotten bunches.",
                ("Protect bunches with netting or paper bags against rain and "
                "insects."),
                ("Apply a copper fungicide after pollination and before rain "
                "season."),
                ("Harvest at the correct stage; avoid leaving over-ripe fruit "
                "on the bunch."),
            ],
            prevention=[
                "Bag or net bunches before the rainy season.",
                "Harvest promptly at the proper maturity stage.",
                "Remove old mummified fruit from the canopy each season.",
            ],
            aliases=("bunch rot", "fruit disease", "brown rot"),
        ),
        Disease(
            key="potassium_deficiency",
            display_name="Potassium Deficiency",
            default_severity=Severity.LOW,
            is_critical=False,
            cause=(
                "Potassium is the nutrient date palms consume most. "
                "Deficiency shows on older fronds as yellow-brown tip "
                "marginal necrosis — driven by sandy soils, rainfall "
                "leaching or unbalanced fertilisation."
            ),
            treatment_steps=[
                ("Apply potassium sulfate (K2SO4) at 1–1.5 kg per mature palm "
                "per year, split into 2–3 applications."),
                "Fertigate through the irrigation system for faster uptake.",
                "Confirm with a leaf tissue analysis (pinnae from frond 17).",
            ],
            prevention=[
                "Run a leaf tissue analysis every season (frond 17 pinnae).",
                "Keep the N:K balance aligned with crop removal.",
                "Use split fertigation doses instead of one heavy dressing.",
            ],
            aliases=("k deficiency", "potassium"),
        ),
        Disease(
            key="magnesium_deficiency",
            display_name="Magnesium Deficiency",
            default_severity=Severity.LOW,
            is_critical=False,
            cause=(
                "Low magnesium availability — typically acidic, sandy or "
                "heavily leached soils, or potassium-heavy fertilisation "
                "competing with Mg uptake — shows as broad orange-yellow "
                "bands on older fronds."
            ),
            treatment_steps=[
                "Apply magnesium sulfate or Kieserite around the root zone.",
                "Check soil pH — magnesium uptake drops in acidic soils.",
                "Use a balanced palm-specific fertiliser for maintenance.",
            ],
            prevention=[
                "Monitor soil pH and correct acidity with lime when needed.",
                "Include Mg in every seasonal fertilisation programme.",
                "Amend sandy soils with organic matter to reduce leaching.",
            ],
            aliases=("mg deficiency", "magnesium"),
        ),
        Disease(
            key="nitrogen_deficiency",
            display_name="Nitrogen Deficiency",
            default_severity=Severity.LOW,
            is_critical=False,
            cause=(
                "Nitrogen depletion from leaching, low soil organic matter "
                "or insufficient fertilisation produces uniformly pale "
                "green-yellow fronds and stunted overall growth."
            ),
            treatment_steps=[
                "Apply urea or ammonium sulfate through fertigation.",
                "Add organic matter / manure around the root zone.",
                "Re-assess the overall fertilisation programme.",
            ],
            prevention=[
                "Apply organic manure annually around the root zone.",
                "Split nitrogen doses through the irrigation season.",
                ("Use green manure / cover crops between palm rows where "
                "feasible."),
            ],
            aliases=("n deficiency", "nitrogen"),
        ),
        Disease(
            key="drought_stress",
            display_name="Drought / Water Stress",
            default_severity=Severity.MEDIUM,
            is_critical=False,
            cause=(
                "Prolonged water deficit — failed emitters, restricted roots "
                "or extreme heat — causes frond tip desiccation, premature "
                "frond senescence and reduced fruit set."
            ),
            treatment_steps=[
                "Audit the irrigation system for clogged emitters and leaks.",
                "Increase irrigation frequency during fruit set and summer.",
                "Mulch the root zone to reduce evaporation.",
            ],
            prevention=[
                "Audit emitters and flush lines at least twice a year.",
                "Track soil moisture or evapotranspiration-based schedules.",
                "Maintain an organic mulch layer over the root zone.",
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
