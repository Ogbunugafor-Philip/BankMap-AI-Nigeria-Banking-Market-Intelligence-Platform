"""
load_mpi.py — load NBS Multidimensional Poverty Index (LGA level) into wards.

The MPI is published at LGA level, so each LGA's poverty index is applied to
EVERY ward in that LGA (a modelled value). Updates wards.poverty_index and
flags the modelled nature via lower data_confidence.

Run from backend/:  python scripts/load_mpi.py
(Requires load_grid3.py first.)
"""

import utils  # noqa: F401  (sys.path wiring)

import pandas as pd

import models
from database import SessionLocal
from utils import canonical_state, find_column, normalize_name, require_files

CSV_CANDIDATES = ["nbs_mpi.csv", "mpi.csv", "poverty_index.csv"]

CONFIDENCE_MODELLED = 0.5


def _to_index(value):
    """MPI is typically 0–1; accept 0–100 and rescale."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v > 1.0:
        v = v / 100.0
    return max(0.0, min(1.0, v))


def main():
    path = require_files(CSV_CANDIDATES, "NBS Multidimensional Poverty Index CSV (LGA level)")
    if not path:
        return

    print(f"[mpi] Reading {path} ...")
    df = pd.read_csv(path)

    state_col = find_column(df, ["state", "state_name", "statename"])
    lga_col = find_column(df, ["lga", "lga_name", "lganame"], required=False)
    mpi_col = find_column(
        df, ["poverty_index", "mpi", "multidimensional_poverty_index", "headcount"]
    )

    has_lga_level = lga_col is not None
    print(f"[mpi] Detected {'LGA' if has_lga_level else 'STATE'}-level data.")

    session = SessionLocal()
    if session.query(models.Ward).count() == 0:
        print("[mpi] No wards in DB. Run load_grid3.py first. Aborting.")
        session.close()
        return

    # Build a lookup table keyed by (state, lga) when LGA data is present, or
    # by (state,) when only state-level MPI is available (e.g. OPHI/NBS MICS).
    lga_mpi, state_mpi = {}, {}
    for _, row in df.iterrows():
        sn = canonical_state(row[state_col])
        idx = _to_index(row[mpi_col])
        if not (sn and idx is not None):
            continue
        if has_lga_level:
            ln = normalize_name(row[lga_col])
            if ln:
                lga_mpi[(sn, ln)] = idx
        else:
            state_mpi[sn] = idx

    updated = 0
    try:
        for ward in session.query(models.Ward).all():
            state = session.get(models.State, ward.state_id)
            lga = session.get(models.LGA, ward.lga_id)
            if not state:
                continue
            if has_lga_level:
                if not lga:
                    continue
                idx = lga_mpi.get((canonical_state(state.name), normalize_name(lga.name)))
            else:
                idx = state_mpi.get(canonical_state(state.name))
            if idx is None:
                continue
            ward.poverty_index = idx
            # Modelled from LGA -> keep the lower confidence.
            ward.data_confidence = (
                CONFIDENCE_MODELLED
                if ward.data_confidence is None
                else min(ward.data_confidence, CONFIDENCE_MODELLED)
            )
            updated += 1

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(f"[mpi] DONE. wards updated with poverty_index={updated}")


if __name__ == "__main__":
    main()
