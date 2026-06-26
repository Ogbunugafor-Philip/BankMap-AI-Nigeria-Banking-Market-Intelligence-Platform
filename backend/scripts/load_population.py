"""
load_population.py — load NBS ward-level population into the wards table.

Matches each CSV row to a ward by (ward name + LGA name + state name) using
fuzzy-tolerant matching, then updates wards.population. Unmatched rows are
logged so they can be reconciled.

Run from backend/:  python scripts/load_population.py
(Requires load_grid3.py to have populated wards first.)
"""

import utils  # noqa: F401  (sys.path wiring)

import pandas as pd

import models
from database import SessionLocal
from utils import WardIndex, find_column, require_files

CSV_CANDIDATES = ["nbs_population.csv", "population.csv", "ward_population.csv"]


def main():
    path = require_files(CSV_CANDIDATES, "NBS ward-level population CSV")
    if not path:
        return

    print(f"[population] Reading {path} ...")
    df = pd.read_csv(path)

    state_col = find_column(df, ["state", "state_name", "statename"])
    lga_col = find_column(df, ["lga", "lga_name", "lganame"])
    ward_col = find_column(df, ["ward", "ward_name", "wardname"])
    pop_col = find_column(df, ["population", "pop", "total_population", "ward_population"])

    session = SessionLocal()
    if session.query(models.Ward).count() == 0:
        print("[population] No wards in DB. Run load_grid3.py first. Aborting.")
        session.close()
        return

    index = WardIndex(session, models)
    matched = unmatched = 0
    unmatched_rows = []

    try:
        for _, row in df.iterrows():
            ward = index.match(row[state_col], row[lga_col], row[ward_col])
            if ward is None:
                unmatched += 1
                unmatched_rows.append(
                    f"{row[state_col]} / {row[lga_col]} / {row[ward_col]}"
                )
                continue

            try:
                ward.population = int(float(row[pop_col]))
            except (TypeError, ValueError):
                ward.population = None
            matched += 1

            if matched % 500 == 0:
                session.commit()
                print(f"[population] progress: {matched} wards updated ...")

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(f"[population] DONE. matched={matched}, unmatched={unmatched}")
    if unmatched_rows:
        print("[population] Unmatched rows (first 25):")
        for r in unmatched_rows[:25]:
            print(f"    - {r}")


if __name__ == "__main__":
    main()
