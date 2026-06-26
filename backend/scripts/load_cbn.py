"""
load_cbn.py — load the CBN bank-branch directory and compute distances.

Steps:
  1. Read the CBN CSV (bank_name, branch_name, state, lga, latitude, longitude).
  2. Insert branches into bank_branches (idempotent on the natural key).
  3. Assign each branch to a ward via PostGIS point-in-polygon (ST_Contains).
  4. For each ward, compute nearest_bank_distance_km using the PostGIS KNN
     operator (<->) plus geography distance, and store it on the ward.

Run from backend/:  python scripts/load_cbn.py
(Requires load_grid3.py first so ward geometries exist.)
"""

import utils  # noqa: F401  (sys.path wiring)

import pandas as pd
from sqlalchemy import text

import models
from database import SessionLocal, engine
from utils import canonical_state, find_column, normalize_name, require_files

CSV_CANDIDATES = ["cbn_branches.csv", "cbn.csv", "bank_branches.csv"]


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_branches():
    path = require_files(CSV_CANDIDATES, "CBN bank-branch directory CSV")
    if not path:
        return False

    print(f"[cbn] Reading {path} ...")
    df = pd.read_csv(path)

    bank_col = find_column(df, ["bank_name", "bank"])
    branch_col = find_column(df, ["branch_name", "branch"], required=False)
    state_col = find_column(df, ["state", "state_name"])
    lga_col = find_column(df, ["lga", "lga_name"])
    lat_col = find_column(df, ["latitude", "lat"])
    lon_col = find_column(df, ["longitude", "lon", "lng", "long"])

    session = SessionLocal()
    inserted = updated = skipped = 0
    try:
        for _, row in df.iterrows():
            lat, lon = _to_float(row[lat_col]), _to_float(row[lon_col])
            bank = normalize_name(row[bank_col])
            branch = normalize_name(row[branch_col]) if branch_col else None
            state = canonical_state(row[state_col])
            lga = normalize_name(row[lga_col])

            if lat is None or lon is None or bank is None:
                skipped += 1
                continue

            # Idempotent natural key: bank + branch + coordinates.
            existing = (
                session.query(models.BankBranch)
                .filter(
                    models.BankBranch.bank_name == bank,
                    models.BankBranch.branch_name == branch,
                    models.BankBranch.latitude == lat,
                    models.BankBranch.longitude == lon,
                )
                .one_or_none()
            )
            if existing is None:
                session.add(
                    models.BankBranch(
                        bank_name=bank,
                        branch_name=branch,
                        state=state,
                        lga=lga,
                        latitude=lat,
                        longitude=lon,
                    )
                )
                inserted += 1
            else:
                existing.state = state
                existing.lga = lga
                updated += 1

            if (inserted + updated) % 1000 == 0:
                session.commit()
                print(f"[cbn] progress: {inserted + updated} branches processed ...")

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(f"[cbn] Branches: inserted={inserted}, updated={updated}, skipped={skipped}")
    return True


def assign_branches_to_wards():
    """Point-in-polygon: set bank_branches.ward_id where the point is inside a ward."""
    print("[cbn] Assigning branches to wards (ST_Contains) ...")
    sql = text(
        """
        UPDATE bank_branches b
        SET ward_id = w.id
        FROM wards w
        WHERE w.geometry IS NOT NULL
          AND b.latitude IS NOT NULL
          AND b.longitude IS NOT NULL
          AND ST_Contains(
                w.geometry,
                ST_SetSRID(ST_MakePoint(b.longitude, b.latitude), 4326)
              )
        """
    )
    with engine.begin() as conn:
        result = conn.execute(sql)
    print(f"[cbn] Branches assigned to a ward: {result.rowcount}")


def compute_nearest_distance():
    """
    For every ward with geometry, find the nearest branch using the KNN (<->)
    operator for candidate ordering, then measure true distance on the
    geography type (metres) and store kilometres.
    """
    print("[cbn] Computing nearest_bank_distance_km per ward (PostGIS KNN) ...")
    sql = text(
        """
        UPDATE wards w
        SET nearest_bank_distance_km = (
            -- Correlated subquery: PostgreSQL forbids referencing the UPDATE
            -- target (w) from a LATERAL in the FROM clause, but a correlated
            -- scalar subquery in SET may reference it. KNN (<->) orders the
            -- branches by distance; ST_Distance on geography gives true metres.
            SELECT ST_Distance(
                       w.geometry::geography,
                       ST_SetSRID(ST_MakePoint(b.longitude, b.latitude), 4326)::geography
                   ) / 1000.0
            FROM bank_branches b
            WHERE b.latitude IS NOT NULL AND b.longitude IS NOT NULL
            ORDER BY w.geometry <-> ST_SetSRID(ST_MakePoint(b.longitude, b.latitude), 4326)
            LIMIT 1
        )
        WHERE w.geometry IS NOT NULL
        """
    )
    with engine.begin() as conn:
        result = conn.execute(sql)
    print(f"[cbn] Wards updated with nearest-bank distance: {result.rowcount}")


def ensure_spatial_index():
    """GiST index on ward geometry speeds up ST_Contains and KNN ordering."""
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_wards_geometry ON wards USING GIST (geometry)"))
    print("[cbn] Spatial index on wards.geometry ensured.")


def main():
    if not load_branches():
        return
    ensure_spatial_index()
    assign_branches_to_wards()
    compute_nearest_distance()
    print("[cbn] DONE.")


if __name__ == "__main__":
    main()
