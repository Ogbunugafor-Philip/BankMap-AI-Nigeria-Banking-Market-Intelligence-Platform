"""
load_kogi.py — load REAL Kogi State ward boundaries into BankMap AI.

Source: GRID3 NGA - Operational Wards v1.0 (ArcGIS feature service,
NGA_Ward_Boundaries), original source INEC, status "Operational Validated".
The GRID3 v2.0 GeoPackage used by load_grid3.py covers only 15 states and
excludes Kogi; v1.0 is the full national release, so Kogi's 239 wards (21 LGAs)
come from there. Downloaded to data/raw/kogi_wards.geojson.

What this script does (idempotent — safe to re-run):
  1. Reads the real Kogi ward GeoJSON, normalizes names, ensures MULTIPOLYGON/4326.
  2. Inserts states/lgas/wards (lookup-before-insert, same pattern as load_grid3).
  3. Population: WorldPop 2020 1km zonal sum per ward — the SAME measured-data
     method used for the other 15 states (more faithful than area-weighting a
     national total).
  4. Socio-economic indicators (state-level constants for Kogi):
       unbanked_rate=0.62, poverty_index=0.185, sim_penetration=0.52,
       data_confidence=0.66
  5. nearest_bank_distance_km: Haversine from each ward centroid to the nearest
     row in bank_branches.
  6. BOI: computed per ward (unbanked-population normalized within each LGA) and
     written to ward_boi.

Run from backend/:  .venv/bin/python scripts/load_kogi.py
"""

import os
from collections import defaultdict
from math import radians, sin, cos, sqrt, atan2

import utils  # noqa: F401  (wires sys.path)

from geoalchemy2.shape import from_shape
from shapely.geometry import MultiPolygon

import models
from database import SessionLocal, init_db
from boi_engine import compute_boi
from utils import DATA_RAW, NIGERIAN_STATES, normalize_name

KOGI_GEOJSON = os.path.join(DATA_RAW, "kogi_wards.geojson")
WORLDPOP_TIF = os.path.join(DATA_RAW, "worldpop_nga_2020_1km.tif")

# Real state-level indicators for Kogi (applied to every Kogi ward).
KOGI_UNBANKED_RATE = 0.62      # EFInA financial exclusion
KOGI_POVERTY_INDEX = 0.185     # NBS / OPHI MPI
KOGI_SIM_PENETRATION = 0.52    # NCC SIM penetration
KOGI_DATA_CONFIDENCE = 0.66    # mostly state-level modelled inputs


def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two lat/lon points."""
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def _as_multipolygon(geom):
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type == "Polygon":
        return MultiPolygon([geom])
    if geom.geom_type == "MultiPolygon":
        return geom
    return None


def main():
    import geopandas as gpd
    from rasterstats import zonal_stats

    if not os.path.exists(KOGI_GEOJSON):
        print(f"[kogi] Missing {KOGI_GEOJSON}. Download the GRID3 v1.0 Kogi wards first.")
        return

    init_db()
    print(f"[kogi] Reading {KOGI_GEOJSON} ...")
    gdf = gpd.read_file(KOGI_GEOJSON)

    if gdf.crs is None:
        gdf.set_crs(epsg=4326, inplace=True)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    # --- Population via WorldPop zonal sum (same method as the other 15 states) ---
    if os.path.exists(WORLDPOP_TIF):
        print("[kogi] Computing WorldPop zonal population per ward ...")
        stats = zonal_stats(gdf.geometry, WORLDPOP_TIF, stats=["sum"], nodata=-99999)
        gdf["_pop"] = [int(round(s["sum"])) if s and s["sum"] else 0 for s in stats]
    else:
        print("[kogi] WARNING: WorldPop raster not found; population set to 0.")
        gdf["_pop"] = 0

    session = SessionLocal()

    # Preload bank branches for Haversine nearest-distance.
    branches = [
        (b.latitude, b.longitude)
        for b in session.query(models.BankBranch).all()
        if b.latitude is not None and b.longitude is not None
    ]
    print(f"[kogi] {len(branches)} bank branches available for distance calc.")

    state_cache, lga_cache = {}, {}
    inserted = updated = skipped = 0
    new_ward_ids = []

    try:
        for _, row in gdf.iterrows():
            state_name = normalize_name(row.get("statename")) or "Kogi"
            lga_name = normalize_name(row.get("lganame"))
            ward_name = normalize_name(row.get("wardname"))
            multipoly = _as_multipolygon(row.geometry)
            if not (lga_name and ward_name and multipoly):
                skipped += 1
                continue

            # --- State (idempotent) ---
            state = state_cache.get(state_name)
            if state is None:
                state = (
                    session.query(models.State)
                    .filter(models.State.name == state_name)
                    .one_or_none()
                )
                if state is None:
                    state = models.State(
                        name=state_name, state_code=NIGERIAN_STATES.get(state_name, "KO")
                    )
                    session.add(state)
                    session.flush()
                state_cache[state_name] = state

            # --- LGA (idempotent, unique within state) ---
            lga_key = (state.id, lga_name)
            lga = lga_cache.get(lga_key)
            if lga is None:
                lga = (
                    session.query(models.LGA)
                    .filter(models.LGA.name == lga_name, models.LGA.state_id == state.id)
                    .one_or_none()
                )
                if lga is None:
                    lga = models.LGA(name=lga_name, state_id=state.id)
                    session.add(lga)
                    session.flush()
                lga_cache[lga_key] = lga

            # --- Ward centroid for distance ---
            centroid = multipoly.centroid
            wlat, wlon = centroid.y, centroid.x
            nearest_km = None
            if branches:
                nearest_km = round(min(haversine(wlat, wlon, blat, blon) for blat, blon in branches), 2)

            # --- Ward (idempotent, unique within LGA) ---
            geom_value = from_shape(multipoly, srid=4326)
            ward = (
                session.query(models.Ward)
                .filter(models.Ward.name == ward_name, models.Ward.lga_id == lga.id)
                .one_or_none()
            )
            if ward is None:
                ward = models.Ward(name=ward_name, lga_id=lga.id, state_id=state.id)
                session.add(ward)
                inserted += 1
            else:
                updated += 1

            ward.geometry = geom_value
            ward.state_id = state.id
            ward.population = int(row["_pop"])
            ward.unbanked_rate = KOGI_UNBANKED_RATE
            ward.poverty_index = KOGI_POVERTY_INDEX
            ward.sim_penetration = KOGI_SIM_PENETRATION
            ward.data_confidence = KOGI_DATA_CONFIDENCE
            ward.nearest_bank_distance_km = nearest_km
            session.flush()
            new_ward_ids.append(ward.id)

            if (inserted + updated) % 50 == 0:
                session.commit()
                print(f"[kogi] progress: {inserted + updated} wards processed ...")

        session.commit()
        print(f"[kogi] Geometry+indicators done. inserted={inserted}, updated={updated}, skipped={skipped}")

        # --- BOI computation (unbanked-population normalized nationally) ---
        # Authoritative scores come from scripts/compute_boi.py rerun afterwards.
        print("[kogi] Computing BOI for Kogi wards ...")
        all_counts = [
            (p or 0) * (r or 0.0)
            for p, r in session.query(models.Ward.population, models.Ward.unbanked_rate).all()
        ]
        national_min = min(all_counts) if all_counts else 0
        national_max = max(all_counts) if all_counts else 1
        wards = session.query(models.Ward).filter(models.Ward.id.in_(new_ward_ids)).all()
        by_lga = defaultdict(list)
        for w in wards:
            by_lga[w.lga_id].append(w)

        scored = 0
        for lga_id, lga_wards in by_lga.items():
            for w in lga_wards:
                result = compute_boi(
                    {
                        "population": w.population,
                        "unbanked_rate": w.unbanked_rate,
                        "nearest_bank_distance_km": w.nearest_bank_distance_km,
                        "sim_penetration": w.sim_penetration,
                        "poverty_index": w.poverty_index,
                    },
                    national_min, national_max, osm_score=None,
                )
                row = (
                    session.query(models.WardBOI)
                    .filter(models.WardBOI.ward_id == w.id)
                    .one_or_none()
                )
                if row is None:
                    row = models.WardBOI(ward_id=w.id)
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
                scored += 1
                if scored % 50 == 0:
                    session.commit()
                    print(f"[kogi] BOI progress: {scored}/{len(wards)} ...")
        session.commit()

        # --- Summary ---
        state = state_cache.get("Kogi") or session.query(models.State).filter(models.State.name == "Kogi").one()
        total = session.query(models.Ward).filter(models.Ward.state_id == state.id).count()
        lgas = session.query(models.LGA).filter(models.LGA.state_id == state.id).count()
        labels = defaultdict(int)
        for w in session.query(models.Ward).filter(models.Ward.state_id == state.id).all():
            b = session.query(models.WardBOI).filter(models.WardBOI.ward_id == w.id).one_or_none()
            if b:
                labels[b.boi_label] += 1
        sample = (
            session.query(models.Ward, models.WardBOI)
            .join(models.WardBOI, models.WardBOI.ward_id == models.Ward.id)
            .filter(models.Ward.state_id == state.id)
            .order_by(models.WardBOI.boi_score.desc())
            .first()
        )
        print("\n==================== KOGI LOAD SUMMARY ====================")
        print(f"  Total Kogi wards loaded : {total}")
        print(f"  Total Kogi LGAs         : {lgas}")
        print(f"  BOI distribution        : GREEN={labels['GREEN']} AMBER={labels['AMBER']} RED={labels['RED']}")
        if sample:
            sw, sb = sample
            slga = session.get(models.LGA, sw.lga_id)
            print(f"  Top ward                : {sw.name} ({slga.name} LGA) | pop={sw.population:,} | BOI={sb.boi_score} {sb.boi_label}")
        print("==========================================================")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
