"""
compute_boi.py — compute the Banking Opportunity Index for every ward.

The unbanked-population component is normalized *within each LGA*, so we process
ward by LGA: gather the LGA's wards, find the min/max unbanked-adult count, then
score each ward. Results are upserted into ward_boi (idempotent on ward_id).

OSM activity uses the default (50) here; the live OSM score is applied on demand
by the intelligence API. Re-running recomputes cleanly.

Run from backend/:  python scripts/compute_boi.py
"""

import utils  # noqa: F401  (sys.path wiring)

import models
from database import SessionLocal
from boi_engine import compute_boi


def main():
    session = SessionLocal()
    total = session.query(models.Ward).count()
    if total == 0:
        print("[boi] No wards in DB. Run the loaders first. Aborting.")
        session.close()
        return
    print(f"[boi] Computing BOI for {total} wards ...")

    # National normalization range for the unbanked-population score.
    # Use the 5th–95th percentiles (not absolute min/max) so a few outlier
    # mega-wards don't crush everyone else; wards beyond the band cap at 0/100.
    import numpy as np

    all_wards = session.query(models.Ward).all()
    unbanked_values = [
        w.population * w.unbanked_rate
        for w in all_wards
        if w.population and w.unbanked_rate
    ]
    national_min = float(np.percentile(unbanked_values, 5))
    national_max = float(np.percentile(unbanked_values, 95))
    print(
        f"National unbanked range (5th-95th percentile): "
        f"{national_min:,.0f} to {national_max:,.0f} adults"
    )
    print(f"Absolute max for reference: {max(unbanked_values):,.0f}")

    processed = 0
    try:
        for ward in all_wards:
            ward_data = {
                "population": ward.population,
                "unbanked_rate": ward.unbanked_rate,
                "nearest_bank_distance_km": ward.nearest_bank_distance_km,
                "sim_penetration": ward.sim_penetration,
                "poverty_index": ward.poverty_index,
            }
            result = compute_boi(ward_data, national_min, national_max, osm_score=None)

            # Upsert ward_boi row (idempotent on ward_id).
            row = (
                session.query(models.WardBOI)
                .filter(models.WardBOI.ward_id == ward.id)
                .one_or_none()
            )
            if row is None:
                row = models.WardBOI(ward_id=ward.id)
                session.add(row)

            row.boi_score = result.boi_score
            row.boi_label = result.boi_label
            row.unbanked_population_score = result.components["unbanked_population"]
            row.bank_absence_score = result.components["bank_absence"]
            row.economic_viability_score = result.components["economic_viability"]
            row.poverty_filter_score = result.components["poverty_filter"]
            row.osm_activity_score = result.components["osm_activity"]
            row.explanation = result.explanation
            row.data_confidence = result.data_confidence

            processed += 1
            if processed % 500 == 0:
                session.commit()
                print(f"[boi] progress: {processed}/{total} wards scored ...")

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(f"[boi] DONE. Scored {processed} wards.")


if __name__ == "__main__":
    main()
