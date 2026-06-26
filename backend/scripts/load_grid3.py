"""
load_grid3.py — load GRID3 Nigeria ward boundaries into PostGIS.

What it does:
  * Reads the GRID3 ward boundary shapefile from backend/data/raw/.
  * Extracts ward name, LGA name, state name, and MULTIPOLYGON geometry.
  * Reprojects to SRID 4326 (WGS84) if needed.
  * Creates State and LGA rows as they are encountered.
  * Inserts/updates all wards (target: 8,809) with their geometry.

Idempotent: states/LGAs/wards are looked up before insert and updated in place,
so re-running never duplicates rows.

Run from backend/:  python scripts/load_grid3.py
"""

import os

import utils  # noqa: F401  (wires sys.path so `database`/`models` import cleanly)

from geoalchemy2.shape import from_shape
from shapely.geometry import MultiPolygon

import models
from database import SessionLocal, init_db
from utils import (
    DATA_RAW,
    NIGERIAN_STATES,
    best_match,
    canonical_state,
    find_column,
    normalize_name,
    require_files,
)

# Candidate filenames — GRID3 distributes wards under various names.
# GRID3 Operational Wards v2.0 ships as a GeoPackage (.gpkg); older/other
# releases ship as a shapefile (.shp). We auto-discover either, recursively,
# under data/raw/.
SHAPEFILE_CANDIDATES = [
    "grid3_wards.shp",
    "GRID3_NGA_-_Operational_LGA_Boundaries.shp",
    "nga_admbnda_adm3.shp",
    "wards.shp",
]


def _discover_boundary_file():
    """Find a GRID3 boundary file (.gpkg preferred, else .shp) under data/raw/."""
    import glob

    for pattern in ("**/*.gpkg", "**/*.shp"):
        hits = sorted(glob.glob(os.path.join(DATA_RAW, pattern), recursive=True))
        if hits:
            return hits[0]
    return None


def _as_multipolygon(geom):
    """Coerce a Polygon/MultiPolygon shapely geom to MultiPolygon (or None)."""
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type == "Polygon":
        return MultiPolygon([geom])
    if geom.geom_type == "MultiPolygon":
        return geom
    return None


def _resolve_state_name(raw):
    """Normalize a state name and snap it to the canonical 37-state list."""
    name = canonical_state(raw)
    if name is None:
        return None
    if name in NIGERIAN_STATES:
        return name
    match, _ = best_match(name, NIGERIAN_STATES.keys(), threshold=0.82)
    return match or name


def main():
    # geopandas/fiona are only needed by this script — import lazily so the
    # other scripts don't require the full spatial stack to run.
    import geopandas as gpd

    init_db()  # ensure PostGIS + tables exist

    # First try named shapefile candidates; otherwise auto-discover any
    # .gpkg/.shp under data/raw/ (GRID3 v2.0 is a GeoPackage).
    path = _discover_boundary_file()
    if not path:
        path = require_files(SHAPEFILE_CANDIDATES, "GRID3 ward boundary file (.gpkg or .shp)")
    if not path:
        return

    print(f"[grid3] Using boundary file: {path}")
    gdf = gpd.read_file(path)

    # Ensure WGS84 / SRID 4326.
    if gdf.crs is None:
        print("[grid3] WARNING: shapefile has no CRS; assuming EPSG:4326.")
        gdf.set_crs(epsg=4326, inplace=True)
    elif gdf.crs.to_epsg() != 4326:
        print(f"[grid3] Reprojecting from {gdf.crs} to EPSG:4326 ...")
        gdf = gdf.to_crs(epsg=4326)

    # Resolve the relevant columns case-insensitively.
    ward_col = find_column(gdf, ["wardname", "ward_name", "ward", "adm3_en", "name"])
    lga_col = find_column(gdf, ["lganame", "lga_name", "lga", "adm2_en"])
    state_col = find_column(gdf, ["statename", "state_name", "state", "adm1_en"])
    print(f"[grid3] Using columns -> ward={ward_col}, lga={lga_col}, state={state_col}")

    session = SessionLocal()
    state_cache = {}  # state_name -> State
    lga_cache = {}    # (state_id, lga_name) -> LGA

    inserted = updated = skipped = 0
    try:
        for idx, row in gdf.iterrows():
            state_name = _resolve_state_name(row[state_col])
            lga_name = normalize_name(row[lga_col])
            ward_name = normalize_name(row[ward_col])
            multipoly = _as_multipolygon(row.geometry)

            if not (state_name and lga_name and ward_name):
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
                        name=state_name, state_code=NIGERIAN_STATES.get(state_name)
                    )
                    session.add(state)
                    session.flush()  # assign id
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

            # --- Ward (idempotent, unique within LGA) ---
            geom_value = from_shape(multipoly, srid=4326) if multipoly else None
            ward = (
                session.query(models.Ward)
                .filter(models.Ward.name == ward_name, models.Ward.lga_id == lga.id)
                .one_or_none()
            )
            if ward is None:
                ward = models.Ward(
                    name=ward_name,
                    lga_id=lga.id,
                    state_id=state.id,
                    geometry=geom_value,
                )
                session.add(ward)
                inserted += 1
            else:
                ward.geometry = geom_value  # refresh boundary on re-run
                ward.state_id = state.id
                updated += 1

            if (inserted + updated) % 500 == 0:
                session.commit()
                print(f"[grid3] progress: {inserted + updated} wards processed ...")

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    total = session_count()
    print(
        f"[grid3] DONE. inserted={inserted}, updated={updated}, "
        f"skipped(blank)={skipped}. Total wards in DB: {total}"
    )


def session_count() -> int:
    s = SessionLocal()
    try:
        return s.query(models.Ward).count()
    finally:
        s.close()


if __name__ == "__main__":
    main()
