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

from collections import defaultdict

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

    # Group wards by LGA for within-LGA normalization.
    wards_by_lga = defaultdict(list)
    for ward in session.query(models.Ward).all():
        wards_by_lga[ward.lga_id].append(ward)

    processed = 0
    try:
        for lga_id, wards in wards_by_lga.items():
            # Unbanked-adult counts across the LGA (for min-max normalization).
            counts = [
                (w.population or 0) * (w.unbanked_rate or 0.0) for w in wards
            ]
            lga_min, lga_max = (min(counts), max(counts)) if counts else (None, None)

            for ward in wards:
                ward_data = {
                    "population": ward.population,
                    "unbanked_rate": ward.unbanked_rate,
                    "nearest_bank_distance_km": ward.nearest_bank_distance_km,
                    "sim_penetration": ward.sim_penetration,
                    "poverty_index": ward.poverty_index,
                }
                result = compute_boi(ward_data, lga_min, lga_max, osm_score=None)

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
