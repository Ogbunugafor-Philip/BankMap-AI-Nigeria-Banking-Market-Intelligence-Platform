"""
load_efina.py — load EFInA financial-inclusion data into the wards table.

EFInA data may be ward-level or only LGA-level:
  * Ward-level rows   -> applied directly, high data_confidence.
  * LGA-level rows    -> the LGA rate is applied to EVERY ward in that LGA
                         (demographic allocation model), with LOWER
                         data_confidence to flag the value as modelled.

Updates wards.unbanked_rate and wards.data_confidence.

Run from backend/:  python scripts/load_efina.py
(Requires load_grid3.py first.)
"""

import utils  # noqa: F401  (sys.path wiring)

import pandas as pd

import models
from database import SessionLocal
from utils import WardIndex, canonical_state, find_column, normalize_name, require_files

CSV_CANDIDATES = ["efina.csv", "efina_financial_inclusion.csv", "financial_inclusion.csv"]

# Confidence assigned to directly-sourced vs. modelled unbanked rates.
CONFIDENCE_WARD_LEVEL = 0.9
CONFIDENCE_LGA_MODELLED = 0.5


def _to_rate(value):
    """Coerce a value to a 0–1 rate. Accepts percentages (e.g. 63 -> 0.63)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v > 1.0:  # looks like a percentage
        v = v / 100.0
    return max(0.0, min(1.0, v))


def main():
    path = require_files(CSV_CANDIDATES, "EFInA financial-inclusion CSV (ward or LGA level)")
    if not path:
        return

    print(f"[efina] Reading {path} ...")
    df = pd.read_csv(path)

    state_col = find_column(df, ["state", "state_name", "statename"])
    lga_col = find_column(df, ["lga", "lga_name", "lganame"], required=False)
    ward_col = find_column(df, ["ward", "ward_name", "wardname"], required=False)
    rate_col = find_column(
        df, ["unbanked_rate", "unbanked", "exclusion_rate", "financially_excluded"]
    )

    has_ward_level = ward_col is not None
    has_lga_level = lga_col is not None
    level = "WARD" if has_ward_level else ("LGA" if has_lga_level else "STATE")
    print(f"[efina] Detected {level}-level data.")

    session = SessionLocal()
    if session.query(models.Ward).count() == 0:
        print("[efina] No wards in DB. Run load_grid3.py first. Aborting.")
        session.close()
        return

    index = WardIndex(session, models)
    direct = modelled = unmatched = 0

    try:
        if has_ward_level:
            # ---- Ward-level: apply each rate directly ----
            for _, row in df.iterrows():
                ward = index.match(row[state_col], row[lga_col], row[ward_col])
                if ward is None:
                    unmatched += 1
                    continue
                rate = _to_rate(row[rate_col])
                if rate is None:
                    continue
                ward.unbanked_rate = rate
                ward.data_confidence = CONFIDENCE_WARD_LEVEL
                direct += 1
        elif has_lga_level:
            # ---- LGA-level: build a {(state, lga): rate} table, then fan out ----
            lga_rates = {}
            for _, row in df.iterrows():
                sn = canonical_state(row[state_col])
                ln = normalize_name(row[lga_col])
                rate = _to_rate(row[rate_col])
                if sn and ln and rate is not None:
                    lga_rates[(sn, ln)] = rate

            # Apply the LGA rate to every ward in that LGA.
            for ward in session.query(models.Ward).all():
                lga = session.get(models.LGA, ward.lga_id)
                state = session.get(models.State, ward.state_id)
                if not (lga and state):
                    continue
                key = (canonical_state(state.name), normalize_name(lga.name))
                rate = lga_rates.get(key)
                if rate is None:
                    continue
                ward.unbanked_rate = rate
                # Modelled value -> lower confidence (flag it).
                ward.data_confidence = CONFIDENCE_LGA_MODELLED
                modelled += 1
        else:
            # ---- STATE-level: apply the state rate to every ward in the state ----
            # (e.g. EFInA A2F zone->state exclusion rates). Modelled, so lower
            # confidence is recorded.
            state_rates = {}
            for _, row in df.iterrows():
                sn = canonical_state(row[state_col])
                rate = _to_rate(row[rate_col])
                if sn and rate is not None:
                    state_rates[sn] = rate

            for ward in session.query(models.Ward).all():
                state = session.get(models.State, ward.state_id)
                if not state:
                    continue
                rate = state_rates.get(canonical_state(state.name))
                if rate is None:
                    continue
                ward.unbanked_rate = rate
                ward.data_confidence = CONFIDENCE_LGA_MODELLED
                modelled += 1

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(
        f"[efina] DONE. direct(ward-level)={direct}, modelled(lga-level)={modelled}, "
        f"unmatched={unmatched}"
    )


if __name__ == "__main__":
    main()
