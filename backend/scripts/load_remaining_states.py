"""
load_remaining_states.py — load every Nigerian state not yet in the database
from the GRID3 v1.0 national ward layer (same ArcGIS source that provided Kogi).

Source file: data/raw/grid3_nga_all_wards.geojson
  (GRID3 NGA Operational Wards v1.0, original source INEC; 9,410 wards / 37 states)

Per ward it sets:
  * geometry        — real GRID3/INEC MULTIPOLYGON (SRID 4326)
  * population       — WorldPop 2020 1km zonal sum (same method as the 15 GRID3
                       states and Kogi)
  * unbanked_rate    — from efina.csv  (state level)
  * poverty_index    — from nbs_mpi.csv (state level)
  * sim_penetration  — from ncc_sim.csv (state level)
  * nearest_bank_distance_km — Haversine from ward centroid to nearest bank_branches row
  * data_confidence  — average of per-input confidences (see below)
Then computes the BOI (unbanked-population normalized within each LGA) and writes
ward_boi.

Idempotent: states already present in the DB are skipped; existing wards are
updated in place (no duplicates).

Run from backend/:  .venv/bin/python scripts/load_remaining_states.py
"""

import os
from collections import defaultdict
from math import radians, sin, cos, sqrt, atan2

import utils  # noqa: F401  (sys.path wiring)

import pandas as pd
from geoalchemy2.shape import from_shape
from shapely.geometry import MultiPolygon

import models
from database import SessionLocal, init_db
from boi_engine import compute_boi
from utils import DATA_RAW, NIGERIAN_STATES, canonical_state, normalize_name

GEOJSON = os.path.join(DATA_RAW, "grid3_nga_all_wards.geojson")
WORLDPOP_TIF = os.path.join(DATA_RAW, "worldpop_nga_2020_1km.tif")

# Per-input confidence (spec) -> overall is their average.
CONF_GEOMETRY = 0.9
CONF_POP_WORLDPOP = 0.85
CONF_UNBANKED = 0.5
CONF_POVERTY = 0.7
CONF_SIM = 0.5
DATA_CONFIDENCE = round(
    (CONF_GEOMETRY + CONF_POP_WORLDPOP + CONF_UNBANKED + CONF_POVERTY + CONF_SIM) / 5, 3
)  # = 0.69


def haversine(lat1, lon1, lat2, lon2):
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


def _load_state_csv(filename, value_col_candidates):
    """Return {canonical_state_name: value} from a state-level CSV."""
    df = pd.read_csv(os.path.join(DATA_RAW, filename))
    state_col = next(c for c in df.columns if "state" in c.lower())
    val_col = next(c for c in df.columns if c.lower() in value_col_candidates)
    out = {}
    for _, row in df.iterrows():
        sn = canonical_state(row[state_col])
        try:
            out[sn] = float(row[val_col])
        except (TypeError, ValueError):
            pass
    return out


def main():
    import geopandas as gpd
    from rasterstats import zonal_stats

    if not os.path.exists(GEOJSON):
        print(f"[remaining] Missing {GEOJSON}. Download the national ward layer first.")
        return

    init_db()

    # State-level socio-economic data (real, all 37 states).
    unbanked_by_state = _load_state_csv("efina.csv", {"unbanked_rate"})
    poverty_by_state = _load_state_csv("nbs_mpi.csv", {"poverty_index"})
    sim_by_state = _load_state_csv("ncc_sim.csv", {"sim_penetration"})

    session = SessionLocal()

    # States already loaded -> skip them.
    existing_states = {
        canonical_state(s.name) for s in session.query(models.State).all()
    }
    print(f"[remaining] {len(existing_states)} states already loaded; they will be skipped.")

    # Bank branches for Haversine distance.
    branches = [
        (b.latitude, b.longitude)
        for b in session.query(models.BankBranch).all()
        if b.latitude is not None and b.longitude is not None
    ]
    print(f"[remaining] {len(branches)} bank branches for distance calc.")

    print(f"[remaining] Reading {GEOJSON} ...")
    gdf = gpd.read_file(GEOJSON)
    if gdf.crs is None:
        gdf.set_crs(epsg=4326, inplace=True)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    # Keep only wards whose (canonical) state is not yet loaded.
    gdf["_state"] = gdf["statename"].map(canonical_state)
    todo = gdf[~gdf["_state"].isin(existing_states)].copy()
    # Drop null/empty geometries (a few exist) so zonal_stats doesn't choke.
    before = len(todo)
    todo = todo[todo.geometry.notna() & ~todo.geometry.is_empty].copy().reset_index(drop=True)
    if len(todo) < before:
        print(f"[remaining] dropped {before - len(todo)} wards with null/empty geometry.")
    new_states = sorted(todo["_state"].unique())
    print(f"[remaining] {len(todo)} wards across {len(new_states)} new states: {new_states}")
    if todo.empty:
        print("[remaining] Nothing to load.")
        session.close()
        return

    # WorldPop zonal population for all wards-to-load in one batch.
    if os.path.exists(WORLDPOP_TIF):
        print("[remaining] Computing WorldPop zonal population (may take a minute) ...")
        stats = zonal_stats(todo.geometry, WORLDPOP_TIF, stats=["sum"], nodata=-99999)
        todo["_pop"] = [int(round(s["sum"])) if s and s["sum"] else 0 for s in stats]
    else:
        print("[remaining] WARNING: WorldPop raster missing; population set to 0.")
        todo["_pop"] = 0

    state_cache, lga_cache = {}, {}
    new_ward_ids = []
    inserted = updated = skipped = 0
    failed_states = set()

    try:
        for idx, row in todo.iterrows():
            try:
                state_name = canonical_state(row["statename"])
                lga_name = normalize_name(row["lganame"])
                ward_name = normalize_name(row["wardname"])
                multipoly = _as_multipolygon(row.geometry)
                if not (state_name and lga_name and ward_name and multipoly):
                    skipped += 1
                    continue

                # State (idempotent)
                state = state_cache.get(state_name)
                if state is None:
                    state = (
                        session.query(models.State)
                        .filter(models.State.name == state_name)
                        .one_or_none()
                    )
                    if state is None:
                        state = models.State(
                            name=state_name, state_code=NIGERIAN_STATES.get(state_name)
                        )
                        session.add(state)
                        session.flush()
                    state_cache[state_name] = state

                # LGA (idempotent)
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

                # Distance via Haversine from ward centroid
                c = multipoly.centroid
                nearest_km = None
                if branches:
                    nearest_km = round(min(haversine(c.y, c.x, bl, bo) for bl, bo in branches), 2)

                # Ward (idempotent)
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

                ward.geometry = from_shape(multipoly, srid=4326)
                ward.state_id = state.id
                ward.population = int(row["_pop"])
                ward.unbanked_rate = unbanked_by_state.get(state_name)
                ward.poverty_index = poverty_by_state.get(state_name)
                ward.sim_penetration = sim_by_state.get(state_name)
                ward.nearest_bank_distance_km = nearest_km
                ward.data_confidence = DATA_CONFIDENCE
                session.flush()
                new_ward_ids.append(ward.id)

                if (inserted + updated) % 100 == 0:
                    session.commit()
                    print(f"[remaining] progress: {inserted + updated}/{len(todo)} wards ...")
            except Exception as e:
                session.rollback()
                failed_states.add(row.get("statename"))
                print(f"[remaining] ERROR on ward idx={idx} ({row.get('statename')}): {e}")
                continue

        session.commit()
        print(f"[remaining] Geometry+indicators done. inserted={inserted}, updated={updated}, skipped={skipped}")

        # BOI — unbanked-population normalized against the NATIONAL range.
        # (Authoritative scores come from scripts/compute_boi.py, which is rerun
        # across all wards afterwards; this keeps freshly-loaded wards consistent.)
        print("[remaining] Computing BOI ...")
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
                if scored % 200 == 0:
                    session.commit()
                    print(f"[remaining] BOI progress: {scored}/{len(wards)} ...")
        session.commit()

        # Per-state summary for the newly loaded states.
        print("\n========== NEWLY LOADED STATES ==========")
        print(f"{'state':<28}{'wards':>6}{'lgas':>6}{'green':>7}{'amber':>7}{'red':>5}")
        for sname in new_states:
            st = session.query(models.State).filter(models.State.name == sname).one_or_none()
            if not st:
                continue
            wq = session.query(models.Ward).filter(models.Ward.state_id == st.id)
            wcount = wq.count()
            lcount = session.query(models.LGA).filter(models.LGA.state_id == st.id).count()
            g = a = r = 0
            for w in wq.all():
                b = session.query(models.WardBOI).filter(models.WardBOI.ward_id == w.id).one_or_none()
                if b and b.boi_label == "GREEN": g += 1
                elif b and b.boi_label == "AMBER": a += 1
                elif b and b.boi_label == "RED": r += 1
            print(f"{sname:<28}{wcount:>6}{lcount:>6}{g:>7}{a:>7}{r:>5}")
        if failed_states:
            print("\n[remaining] States with at least one failed ward:", sorted(failed_states))
        print("=========================================")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
