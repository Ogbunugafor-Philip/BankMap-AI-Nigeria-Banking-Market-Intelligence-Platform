"""
boi_engine.py — Banking Opportunity Index (BOI) for BankMap AI.

The BOI scores every ward 0–100 on how attractive it is for banking expansion,
combining five weighted components built from the real ward indicators:

  1. Unbanked Population Score   (30%)  number of unbanked adults, normalized
                                        within the ward's LGA
  2. Bank Absence Score          (25%)  distance to the nearest bank branch
  3. Economic Viability Score    (20%)  SIM penetration, discounted in very
                                        poor wards
  4. Poverty Filter Score        (15%)  rewards the "viable but underserved"
                                        poverty band, penalises extreme poverty
  5. OSM Live Activity Score     (10%)  live economic activity around the ward
                                        (markets/shops/roads); 50 until queried

FINAL BOI = round(weighted sum), capped to 0–100.
  GREEN 70–100  |  AMBER 40–69  |  RED 0–39

Every component returns an explanation string so the score is fully auditable.
"""

from dataclasses import dataclass, field
from typing import Optional

# Component weights (must sum to 1.0).
WEIGHTS = {
    "unbanked_population": 0.30,
    "bank_absence": 0.25,
    "economic_viability": 0.20,
    "poverty_filter": 0.15,
    "osm_activity": 0.10,
}

# Per-component confidence in the *source* of each input (0–1). Reflects whether
# the underlying value is directly observed at ward level or modelled from a
# coarser level. Used to compute an overall data_confidence for the score.
SOURCE_CONFIDENCE = {
    "unbanked_population": 0.55,  # population real (WorldPop) but rate modelled from zone
    "bank_absence": 0.85,         # computed from real OSM branch coordinates
    "economic_viability": 0.50,   # SIM penetration modelled from state level
    "poverty_filter": 0.50,       # MPI modelled from state level
    "osm_activity": 0.80,         # live Overpass query (0.5 when defaulted)
}

DEFAULT_OSM_SCORE = 50.0


@dataclass
class BOIResult:
    boi_score: int
    boi_label: str
    components: dict = field(default_factory=dict)        # raw 0–100 per component
    weighted: dict = field(default_factory=dict)          # weight-applied per component
    explanation: dict = field(default_factory=dict)       # human-readable per component
    data_confidence: float = 0.0

    def as_dict(self) -> dict:
        return {
            "boi_score": self.boi_score,
            "boi_label": self.boi_label,
            "components": self.components,
            "weighted": self.weighted,
            "explanation": self.explanation,
            "data_confidence": self.data_confidence,
        }


def label_for(score: float) -> str:
    """Map a 0–100 score to its traffic-light label."""
    if score >= 70:
        return "GREEN"
    if score >= 40:
        return "AMBER"
    return "RED"


# --------------------------------------------------------------------------
# Individual component scorers
# --------------------------------------------------------------------------
def _unbanked_population_score(population, unbanked_rate, national_min, national_max):
    """
    Unbanked adults = population × unbanked_rate, then min-max normalized to
    0–100 against the NATIONAL range of unbanked-adult counts so a ward is ranked
    against every other ward in Nigeria (not just its LGA peers).
    """
    pop = population or 0
    rate = unbanked_rate if unbanked_rate is not None else 0.0
    unbanked_adults = pop * rate

    if national_max is not None and national_min is not None and national_max > national_min:
        score = (unbanked_adults - national_min) / (national_max - national_min) * 100.0
    else:
        score = 50.0

    score = max(0.0, min(100.0, score))
    rate_pct = round(rate * 100)
    lo = national_min or 0
    hi = national_max or 1
    expl = (
        f"~{unbanked_adults:,.0f} unbanked adults "
        f"({rate_pct}% of {pop:,} residents); ranked nationally "
        f"(range {lo:,.0f}–{hi:,.0f})"
    )
    return score, expl


def _bank_absence_score(distance_km):
    """Step function: the farther the nearest branch, the higher the opportunity."""
    d = distance_km if distance_km is not None else 0.0
    if d < 2:
        score, band = 10.0, "0–2 km"
    elif d < 5:
        score, band = 30.0, "2–5 km"
    elif d < 10:
        score, band = 60.0, "5–10 km"
    elif d < 20:
        score, band = 80.0, "10–20 km"
    else:
        score, band = 100.0, "20+ km"
    return score, f"Nearest bank branch is {d:.1f} km away ({band} band → {score:.0f})."


def _economic_viability_score(sim_penetration, poverty_index):
    """SIM penetration as a proxy for economic activity; discounted if very poor."""
    sim = sim_penetration if sim_penetration is not None else 0.0
    score = sim * 100.0
    note = f"SIM penetration {sim:.0%}"
    if poverty_index is not None and poverty_index > 0.75:
        score *= 0.6
        note += f"; discounted ×0.6 (extreme poverty MPI {poverty_index:.2f})"
    score = max(0.0, min(100.0, score))
    return score, f"{note} → {score:.0f}."


def _poverty_filter_score(poverty_index):
    """
    Rewards the 'viable but underserved' poverty band. Extreme poverty scores
    low (hard to bank), very low poverty scores moderate (likely already served).
    """
    if poverty_index is None:
        return 40.0, "No poverty index; neutral 40."
    p = poverty_index
    if p < 0.30:
        score, band = 40.0, "<0.30 (relatively well-off, likely already served)"
    elif p <= 0.65:
        score, band = 80.0, "0.30–0.65 (viable but underserved — ideal)"
    elif p <= 0.80:
        score, band = 50.0, "0.65–0.80 (poor, more challenging)"
    else:
        score, band = 20.0, ">0.80 (extreme poverty)"
    return score, f"MPI {p:.2f} in band {band} → {score:.0f}."


def _osm_activity_score(osm_score):
    s = DEFAULT_OSM_SCORE if osm_score is None else float(osm_score)
    s = max(0.0, min(100.0, s))
    if osm_score is None or osm_score == DEFAULT_OSM_SCORE:
        return s, f"OSM activity score {s:.0f} (default — not yet queried live)."
    return s, f"Live OSM activity score {s:.0f} (markets/shops/roads near ward)."


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
def compute_boi(
    ward: dict,
    national_min: Optional[float] = 0,
    national_max: Optional[float] = 1,
    osm_score: Optional[float] = None,
) -> BOIResult:
    """
    Compute the BOI for a single ward.

    `ward` is a dict with keys: population, unbanked_rate, nearest_bank_distance_km,
    sim_penetration, poverty_index. `national_min/max` give the NATIONAL range of
    unbanked-adult counts (so the unbanked-population score ranks the ward against
    every ward in Nigeria). `osm_score` is the live OSM score (or None for default).
    """
    components, weighted, explanation = {}, {}, {}

    s, e = _unbanked_population_score(
        ward.get("population"), ward.get("unbanked_rate"),
        national_min, national_max,
    )
    components["unbanked_population"], explanation["unbanked_population"] = s, e

    s, e = _bank_absence_score(ward.get("nearest_bank_distance_km"))
    components["bank_absence"], explanation["bank_absence"] = s, e

    s, e = _economic_viability_score(ward.get("sim_penetration"), ward.get("poverty_index"))
    components["economic_viability"], explanation["economic_viability"] = s, e

    s, e = _poverty_filter_score(ward.get("poverty_index"))
    components["poverty_filter"], explanation["poverty_filter"] = s, e

    s, e = _osm_activity_score(osm_score)
    components["osm_activity"], explanation["osm_activity"] = s, e

    # Weighted sum.
    total = 0.0
    for key, weight in WEIGHTS.items():
        w = components[key] * weight
        weighted[key] = round(w, 2)
        total += w

    boi_score = int(max(0, min(100, round(total))))

    # data_confidence: weighted blend of per-component source confidence, with
    # the OSM component upgraded to live confidence when a real score was passed.
    conf = dict(SOURCE_CONFIDENCE)
    if osm_score is None or osm_score == DEFAULT_OSM_SCORE:
        conf["osm_activity"] = 0.5
    data_confidence = round(sum(conf[k] * WEIGHTS[k] for k in WEIGHTS), 3)

    return BOIResult(
        boi_score=boi_score,
        boi_label=label_for(boi_score),
        components={k: round(v, 1) for k, v in components.items()},
        weighted=weighted,
        explanation=explanation,
        data_confidence=data_confidence,
    )
