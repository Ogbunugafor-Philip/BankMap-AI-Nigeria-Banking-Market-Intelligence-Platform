"""
load_ncc.py — load NCC SIM-penetration data and model it down to wards.

NCC publishes SIM penetration at state or LGA level. SIM penetration is a rate
(SIMs per capita / % of population), so:

  * If the source gives a penetration RATE per state/LGA, that rate is applied
    to each ward in scope. (A rate is intensive — it does not get summed.)
  * If the source gives an ABSOLUTE SIM COUNT per state/LGA, we distribute it to
    wards by POPULATION WEIGHT, then divide by ward population to get a rate.
    This is the "population weighting" disaggregation.

Either way the result is a modelled value, so it is flagged via lower
data_confidence (only lowered if not already lower from EFInA modelling).

Updates wards.sim_penetration.

Run from backend/:  python scripts/load_ncc.py
(Requires load_grid3.py first; load_population.py improves count-based modelling.)
"""

import utils  # noqa: F401  (sys.path wiring)

import pandas as pd

import models
from database import SessionLocal
from utils import canonical_state, find_column, normalize_name, require_files

CSV_CANDIDATES = ["ncc_sim.csv", "ncc.csv", "sim_penetration.csv"]

CONFIDENCE_MODELLED = 0.5


def _to_rate(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v > 1.0:  # percentage -> fraction
        v = v / 100.0
    return max(0.0, v)


def _to_count(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main():
    path = require_files(CSV_CANDIDATES, "NCC SIM-penetration CSV (state or LGA level)")
    if not path:
        return

    print(f"[ncc] Reading {path} ...")
    df = pd.read_csv(path)

    state_col = find_column(df, ["state", "state_name", "statename"])
    lga_col = find_column(df, ["lga", "lga_name", "lganame"], required=False)
    rate_col = find_column(
        df, ["sim_penetration", "penetration", "penetration_rate"], required=False
    )
    count_col = find_column(
        df, ["sim_count", "active_sims", "subscribers", "connections"], required=False
    )

    if rate_col is None and count_col is None:
        print(
            "[ncc] Could not find a penetration-rate or SIM-count column. "
            "Expected one of: sim_penetration / subscribers. Aborting."
        )
        return

    level = "LGA" if lga_col is not None else "STATE"
    mode = "RATE" if rate_col is not None else "COUNT(population-weighted)"
    print(f"[ncc] Detected {level}-level data, modelling by {mode}.")

    session = SessionLocal()
    if session.query(models.Ward).count() == 0:
        print("[ncc] No wards in DB. Run load_grid3.py first. Aborting.")
        session.close()
        return

    updated = 0
    try:
        if rate_col is not None:
            # ---- Rate given: apply directly to wards in scope ----
            rates = {}  # key -> rate ; key is (state[, lga])
            for _, row in df.iterrows():
                sn = canonical_state(row[state_col])
                if sn is None:
                    continue
                key = (sn, normalize_name(row[lga_col])) if lga_col else (sn,)
                r = _to_rate(row[rate_col])
                if r is not None:
                    rates[key] = r

            for ward in session.query(models.Ward).all():
                state = session.get(models.State, ward.state_id)
                lga = session.get(models.LGA, ward.lga_id)
                if state is None:
                    continue
                sn = canonical_state(state.name)
                key = (
                    (sn, normalize_name(lga.name)) if (lga_col and lga) else (sn,)
                )
                rate = rates.get(key)
                if rate is None:
                    continue
                ward.sim_penetration = rate
                ward.data_confidence = _lower_confidence(ward.data_confidence)
                updated += 1
        else:
            # ---- Absolute counts: distribute by population weight ----
            counts = {}
            for _, row in df.iterrows():
                sn = canonical_state(row[state_col])
                if sn is None:
                    continue
                key = (sn, normalize_name(row[lga_col])) if lga_col else (sn,)
                c = _to_count(row[count_col])
                if c is not None:
                    counts[key] = c

            # Total population per key, so we can split the SIM count proportionally.
            pop_totals = {}
            for ward in session.query(models.Ward).all():
                state = session.get(models.State, ward.state_id)
                lga = session.get(models.LGA, ward.lga_id)
                if state is None:
                    continue
                sn = canonical_state(state.name)
                key = (sn, normalize_name(lga.name)) if (lga_col and lga) else (sn,)
                pop_totals[key] = pop_totals.get(key, 0) + (ward.population or 0)

            for ward in session.query(models.Ward).all():
                state = session.get(models.State, ward.state_id)
                lga = session.get(models.LGA, ward.lga_id)
                if state is None or not ward.population:
                    continue
                sn = canonical_state(state.name)
                key = (sn, normalize_name(lga.name)) if (lga_col and lga) else (sn,)
                total_sims = counts.get(key)
                total_pop = pop_totals.get(key, 0)
                if not total_sims or not total_pop:
                    continue
                ward_sims = total_sims * (ward.population / total_pop)
                ward.sim_penetration = max(0.0, ward_sims / ward.population)
                ward.data_confidence = _lower_confidence(ward.data_confidence)
                updated += 1

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(f"[ncc] DONE. wards updated with sim_penetration={updated}")


def _lower_confidence(current):
    """Modelled value -> keep the lower of existing/modelled confidence."""
    if current is None:
        return CONFIDENCE_MODELLED
    return min(current, CONFIDENCE_MODELLED)


if __name__ == "__main__":
    main()
