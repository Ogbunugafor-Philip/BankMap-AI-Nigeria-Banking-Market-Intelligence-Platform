"""
routers/intelligence.py — the BankMap AI intelligence layer.

Endpoints:
  GET /lgas/{lga_id}/intelligence          wards ranked by BOI, live OSM, summary
  GET /wards/{ward_id}/intelligence         full ward report incl. AI brief + ROI
  GET /wards/{ward_id}/roi?fso_count=2      ROI recalculation for 1–10 FSOs
  GET /lgas/{lga_id}/intelligence/summary   fast map payload (no OSM/Cerebras)

The BOI stored in ward_boi uses the default OSM score; here we recompute it with
the *live* OSM activity so the figures reflect current on-the-ground signal.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
import models
from boi_engine import compute_boi
from osm_service import get_osm_activity
from cerebras_service import generate_deployment_brief
from roi_calculator import compute_roi, compute_roi_with_whatif

router = APIRouter(tags=["intelligence"])


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _ward_data(db: Session, ward: models.Ward) -> dict:
    """Flatten a ward (+ parent names) into the dict the engines expect."""
    state = db.get(models.State, ward.state_id)
    lga = db.get(models.LGA, ward.lga_id)
    return {
        "id": ward.id,
        "name": ward.name,
        "lga_id": ward.lga_id,
        "state_id": ward.state_id,
        "lga_name": lga.name if lga else None,
        "state_name": state.name if state else None,
        "population": ward.population,
        "unbanked_rate": ward.unbanked_rate,
        "unbanked_rate_source": ward.unbanked_rate_source,
        "nearest_bank_distance_km": ward.nearest_bank_distance_km,
        "sim_penetration": ward.sim_penetration,
        "poverty_index": ward.poverty_index,
        # Ground-level reality indicators — NULL until the PHASE 1–3 loaders
        # (INEC voter, OSM agents, EFInA microdata) run. The panel hides any
        # field that is None.
        "registered_voters": ward.registered_voters,
        "voter_density": ward.voter_density,
        "civic_participation_ratio": ward.civic_participation_ratio,
        "mobile_money_agents": ward.mobile_money_agents,
        "pos_terminals": ward.pos_terminals,
        "agent_density_per_1000": ward.agent_density_per_1000,
        "osm_agent_queried": ward.osm_agent_queried,
    }


_NATIONAL_RANGE = None  # cached (5th, 95th) percentile of unbanked-adult counts


def _national_unbanked_range(db: Session):
    """
    Return the (5th, 95th) percentile of unbanked-adult counts across ALL wards,
    so live BOI recomputation matches the nationally-normalized stored scores
    (compute_boi.py uses the same percentile band). Cached for the process
    lifetime (the range only changes on a data reload + restart).
    """
    global _NATIONAL_RANGE
    if _NATIONAL_RANGE is None:
        import numpy as np

        rows = db.query(models.Ward.population, models.Ward.unbanked_rate).all()
        values = [p * r for p, r in rows if p and r]
        if values:
            _NATIONAL_RANGE = (
                float(np.percentile(values, 5)),
                float(np.percentile(values, 95)),
            )
        else:
            _NATIONAL_RANGE = (0.0, 1.0)
    return _NATIONAL_RANGE


_TOTAL_WARDS = None  # cached count of all wards (changes only on data reload)


def _total_wards(db: Session) -> int:
    global _TOTAL_WARDS
    if _TOTAL_WARDS is None:
        _TOTAL_WARDS = db.query(func.count(models.Ward.id)).scalar() or 0
    return _TOTAL_WARDS


def _national_ranks(db: Session, ward: models.Ward) -> dict:
    """
    Exact national ranks computed on the fly — there are no stored rank columns.
    Unbanked-adult counts are not stored, so we rank on (population * unbanked_rate);
    BOI lives in ward_boi, so we rank on its boi_score. Rank N = (wards strictly
    higher) + 1. Two indexed-free COUNT scans over ~9k rows — only called on the
    single-ward detail endpoints, never in the LGA loop.
    """
    total = _total_wards(db)

    this_unbanked = (ward.population or 0) * (ward.unbanked_rate or 0)
    wards_with_more_unbanked = (
        db.query(func.count(models.Ward.id))
        .filter((models.Ward.population * models.Ward.unbanked_rate) > this_unbanked)
        .scalar()
    ) or 0

    this_boi = (
        db.query(models.WardBOI.boi_score)
        .filter(models.WardBOI.ward_id == ward.id)
        .scalar()
    )
    if this_boi is not None:
        wards_with_higher_boi = (
            db.query(func.count(models.WardBOI.ward_id))
            .filter(models.WardBOI.boi_score > this_boi)
            .scalar()
        ) or 0
        national_boi_rank = wards_with_higher_boi + 1
    else:
        national_boi_rank = None

    return {
        "national_unbanked_rank": wards_with_more_unbanked + 1,
        "wards_with_more_unbanked": wards_with_more_unbanked,
        "national_boi_rank": national_boi_rank,
        "total_wards": total,
    }


def _centroid(db: Session, ward: models.Ward):
    """(lat, lon) of the ward centroid via PostGIS, or (None, None)."""
    row = db.query(
        func.ST_Y(func.ST_Centroid(models.Ward.geometry)),
        func.ST_X(func.ST_Centroid(models.Ward.geometry)),
    ).filter(models.Ward.id == ward.id).first()
    if row and row[0] is not None:
        return float(row[0]), float(row[1])
    return None, None


# --------------------------------------------------------------------------
# GET /lgas/{lga_id}/intelligence
# --------------------------------------------------------------------------
@router.get("/lgas/{lga_id}/intelligence")
def lga_intelligence(
    lga_id: int,
    osm_limit: int = Query(8, ge=0, le=40),
    db: Session = Depends(get_db),
):
    """
    All wards in an LGA ranked by BOI, with summary.

    Public Overpass latency (~10s/call) makes live OSM for every ward impractical,
    so we run *live* OSM only for the top `osm_limit` wards (by stored BOI) and use
    the stored BOI for the rest. Set osm_limit=0 for an instant response, or raise
    it to widen live coverage. The per-ward `osm.source` records which path was used.
    """
    lga = db.get(models.LGA, lga_id)
    if lga is None:
        raise HTTPException(status_code=404, detail="LGA not found")

    national_min, national_max = _national_unbanked_range(db)

    # Pull wards with their stored BOI, ordered so the best opportunities get the
    # (expensive) live OSM calls.
    rows = (
        db.query(models.Ward, models.WardBOI)
        .outerjoin(models.WardBOI, models.WardBOI.ward_id == models.Ward.id)
        .filter(models.Ward.lga_id == lga_id)
        .order_by(models.WardBOI.boi_score.desc().nullslast())
        .all()
    )

    items = []
    for rank, (ward, stored) in enumerate(rows):
        lat, lon = _centroid(db, ward)
        if rank < osm_limit:
            # Live OSM + live-adjusted BOI for the top wards.
            osm = get_osm_activity(lat, lon, timeout=20)
            wd = _ward_data(db, ward)
            boi = compute_boi(wd, national_min, national_max, osm_score=osm["score"])
            score, label = boi.boi_score, boi.boi_label
            components, confidence = boi.components, boi.data_confidence
        else:
            # Stored BOI (computed with default OSM) — no live call.
            osm = {"score": (stored.osm_activity_score if stored else 50),
                   "total_nodes": None, "source": "stored (osm not queried live)"}
            score = stored.boi_score if stored else None
            label = stored.boi_label if stored else None
            components = {
                "unbanked_population": stored.unbanked_population_score,
                "bank_absence": stored.bank_absence_score,
                "economic_viability": stored.economic_viability_score,
                "poverty_filter": stored.poverty_filter_score,
                "osm_activity": stored.osm_activity_score,
            } if stored else {}
            confidence = stored.data_confidence if stored else None
        items.append({
            "ward_id": ward.id,
            "name": ward.name,
            "latitude": lat,
            "longitude": lon,
            "boi_score": score,
            "boi_label": label,
            "components": components,
            "data_confidence": confidence,
            "osm": osm,
            "population": ward.population,
            "unbanked_rate": ward.unbanked_rate,
            "nearest_bank_distance_km": ward.nearest_bank_distance_km,
        })

    items.sort(key=lambda x: (x["boi_score"] is not None, x["boi_score"]), reverse=True)
    summary = {
        "green": sum(1 for i in items if i["boi_label"] == "GREEN"),
        "amber": sum(1 for i in items if i["boi_label"] == "AMBER"),
        "red": sum(1 for i in items if i["boi_label"] == "RED"),
        "total_wards": len(items),
        "top_ward": (
            {"ward_id": items[0]["ward_id"], "name": items[0]["name"], "boi_score": items[0]["boi_score"]}
            if items else None
        ),
    }
    return {
        "lga_id": lga_id,
        "lga_name": lga.name,
        "summary": summary,
        "wards": items,
    }


# --------------------------------------------------------------------------
# GET /wards/{ward_id}/intelligence
# --------------------------------------------------------------------------
@router.get("/wards/{ward_id}/intelligence")
def ward_intelligence(ward_id: int, db: Session = Depends(get_db)):
    """Full ward report: live-adjusted BOI + explanation, live OSM, AI brief, ROI(2)."""
    ward = db.get(models.Ward, ward_id)
    if ward is None:
        raise HTTPException(status_code=404, detail="Ward not found")

    wd = _ward_data(db, ward)
    wd.update(_national_ranks(db, ward))
    national_min, national_max = _national_unbanked_range(db)
    lat, lon = _centroid(db, ward)

    # Shorter timeouts so this combined endpoint degrades gracefully:
    # OSM 8s (else default 50), Cerebras 15s (else template brief).
    osm = get_osm_activity(lat, lon, timeout=8)
    boi = compute_boi(wd, national_min, national_max, osm_score=osm["score"])

    # AI deployment brief from real demographics (no ROI).
    brief = generate_deployment_brief(wd, boi.as_dict(), timeout=15)

    return {
        "ward": wd,
        "centroid": {"latitude": lat, "longitude": lon},
        "boi": boi.as_dict(),
        "osm_data": osm,
        "deployment_brief": brief["brief"],
        "deployment_brief_source": brief["source"],
    }


# --------------------------------------------------------------------------
# GET /wards/{ward_id}/intelligence/base   (instant — stored data only)
# --------------------------------------------------------------------------
@router.get("/wards/{ward_id}/intelligence/base")
def ward_intelligence_base(ward_id: int, db: Session = Depends(get_db)):
    """
    Fast (<200ms) ward report from STORED data only — no OSM, no Cerebras.
    Returns demographics, the stored (nationally-normalized) BOI + explanation,
    and an instant ROI projection. The frontend renders this immediately and then
    fills in OSM + AI brief from the dedicated endpoints below.
    """
    ward = db.get(models.Ward, ward_id)
    if ward is None:
        raise HTTPException(status_code=404, detail="Ward not found")

    wd = _ward_data(db, ward)
    wd.update(_national_ranks(db, ward))
    stored = db.query(models.WardBOI).filter(models.WardBOI.ward_id == ward_id).one_or_none()

    component_scores = {
        "unbanked_population_score": stored.unbanked_population_score if stored else None,
        "bank_absence_score": stored.bank_absence_score if stored else None,
        "economic_viability_score": stored.economic_viability_score if stored else None,
        "poverty_filter_score": stored.poverty_filter_score if stored else None,
        "osm_activity_score": stored.osm_activity_score if stored else None,
    }
    # `components` mirrors the keys the panel's progress bars expect.
    components = {
        "unbanked_population": stored.unbanked_population_score if stored else None,
        "bank_absence": stored.bank_absence_score if stored else None,
        "economic_viability": stored.economic_viability_score if stored else None,
        "poverty_filter": stored.poverty_filter_score if stored else None,
        "osm_activity": stored.osm_activity_score if stored else None,
    }
    boi = {
        "boi_score": stored.boi_score if stored else None,
        "boi_label": stored.boi_label if stored else None,
        "data_confidence": stored.data_confidence if stored else None,
        "components": components,
        "component_scores": component_scores,
        "explanation": stored.explanation if stored else {},
    }

    return {
        "ward": wd,
        "boi": boi,
        "data_confidence": stored.data_confidence if stored else None,
    }


# --------------------------------------------------------------------------
# GET /wards/{ward_id}/osm   (OSM only)
# --------------------------------------------------------------------------
@router.get("/wards/{ward_id}/osm")
def ward_osm(ward_id: int, db: Session = Depends(get_db)):
    """Live OpenStreetMap activity for a ward only (timeout 20s, default on failure)."""
    ward = db.get(models.Ward, ward_id)
    if ward is None:
        raise HTTPException(status_code=404, detail="Ward not found")
    lat, lon = _centroid(db, ward)
    return get_osm_activity(lat, lon, timeout=20)


# --------------------------------------------------------------------------
# GET /wards/{ward_id}/brief   (Cerebras only)
# --------------------------------------------------------------------------
@router.get("/wards/{ward_id}/brief")
def ward_brief(ward_id: int, db: Session = Depends(get_db)):
    """Cerebras ward-intelligence brief only (timeout 20s) — no ROI."""
    ward = db.get(models.Ward, ward_id)
    if ward is None:
        raise HTTPException(status_code=404, detail="Ward not found")

    wd = _ward_data(db, ward)
    stored = db.query(models.WardBOI).filter(models.WardBOI.ward_id == ward_id).one_or_none()
    boi = {
        "boi_score": stored.boi_score if stored else None,
        "boi_label": stored.boi_label if stored else None,
        "data_confidence": stored.data_confidence if stored else None,
    }
    brief = generate_deployment_brief(wd, boi, timeout=20)
    return {
        "ward_id": ward_id,
        "brief": brief["brief"],
        "source": brief["source"],
        "model": brief.get("model"),
    }


# --------------------------------------------------------------------------
# GET /wards/{ward_id}/roi
# --------------------------------------------------------------------------
@router.get("/wards/{ward_id}/roi")
def ward_roi(
    ward_id: int,
    fso_count: int = Query(2, ge=1, le=10),
    db: Session = Depends(get_db),
):
    """Recalculate ROI for any FSO count (1–10). Uses the stored BOI score."""
    ward = db.get(models.Ward, ward_id)
    if ward is None:
        raise HTTPException(status_code=404, detail="Ward not found")

    wd = _ward_data(db, ward)
    boi_row = db.query(models.WardBOI).filter(models.WardBOI.ward_id == ward_id).one_or_none()
    wd["boi_score"] = boi_row.boi_score if boi_row else 50

    result = compute_roi(wd, fso_count)
    result["what_if"] = [compute_roi(wd, n) for n in range(1, 5)]
    return {"ward_id": ward_id, "ward_name": ward.name, "roi": result}


# --------------------------------------------------------------------------
# GET /lgas/{lga_id}/intelligence/summary
# --------------------------------------------------------------------------
@router.get("/lgas/{lga_id}/intelligence/summary")
def lga_intelligence_summary(lga_id: int, db: Session = Depends(get_db)):
    """
    Fast map payload: ward name, centroid, BOI score+label, population, and the
    ward boundary as GeoJSON so the frontend map can render coloured polygons.
    No OSM/Cerebras calls.
    """
    lga = db.get(models.LGA, lga_id)
    if lga is None:
        raise HTTPException(status_code=404, detail="LGA not found")

    rows = (
        db.query(
            models.Ward.id,
            models.Ward.name,
            models.Ward.population,
            models.Ward.nearest_bank_distance_km,
            models.WardBOI.boi_score,
            models.WardBOI.boi_label,
            func.ST_Y(func.ST_Centroid(models.Ward.geometry)),
            func.ST_X(func.ST_Centroid(models.Ward.geometry)),
            func.ST_AsGeoJSON(models.Ward.geometry),
        )
        .outerjoin(models.WardBOI, models.WardBOI.ward_id == models.Ward.id)
        .filter(models.Ward.lga_id == lga_id)
        .order_by(models.WardBOI.boi_score.desc().nullslast())
        .all()
    )
    wards = [
        {
            "ward_id": r[0],
            "name": r[1],
            "population": r[2],
            "nearest_bank_distance_km": r[3],
            "boi_score": r[4],
            "boi_label": r[5],
            "latitude": float(r[6]) if r[6] is not None else None,
            "longitude": float(r[7]) if r[7] is not None else None,
            "geometry": json.loads(r[8]) if r[8] else None,
        }
        for r in rows
    ]

    # Lightweight summary (green/amber/red counts + top ward) computed from the
    # already-fetched wards — no extra queries, no OSM/Cerebras.
    counts = {"GREEN": 0, "AMBER": 0, "RED": 0}
    for w in wards:
        if w["boi_label"] in counts:
            counts[w["boi_label"]] += 1
    top = max(
        (w for w in wards if w["boi_score"] is not None),
        key=lambda w: w["boi_score"], default=None,
    )
    summary = {
        "green": counts["GREEN"],
        "amber": counts["AMBER"],
        "red": counts["RED"],
        "total_wards": len(wards),
        "top_ward": (
            {"ward_id": top["ward_id"], "name": top["name"], "boi_score": top["boi_score"]}
            if top else None
        ),
    }
    return {
        "lga_id": lga_id,
        "lga_name": lga.name,
        "ward_count": len(wards),
        "summary": summary,
        "wards": wards,
    }


# --------------------------------------------------------------------------
# GET /lgas/{lga_id}/ward-scores   (BOI component scores for charts)
# --------------------------------------------------------------------------
@router.get("/lgas/{lga_id}/ward-scores")
def lga_ward_scores(lga_id: int, db: Session = Depends(get_db)):
    """
    BOI component scores for every ward in the LGA plus LGA-average components,
    used by the comparison radar chart.
    """
    lga = db.get(models.LGA, lga_id)
    if lga is None:
        raise HTTPException(status_code=404, detail="LGA not found")

    rows = (
        db.query(models.Ward, models.WardBOI)
        .join(models.WardBOI, models.WardBOI.ward_id == models.Ward.id)
        .filter(models.Ward.lga_id == lga_id)
        .order_by(models.WardBOI.boi_score.desc().nullslast())
        .all()
    )

    wards, acc = [], {
        "boi_score": [], "unbanked_score": [], "bank_absence_score": [],
        "economic_viability_score": [], "poverty_filter_score": [], "osm_activity_score": [],
    }
    for ward, b in rows:
        wards.append({
            "ward_name": ward.name,
            "boi_score": b.boi_score,
            "unbanked_score": round(b.unbanked_population_score or 0, 1),
            "bank_absence_score": round(b.bank_absence_score or 0, 1),
            "economic_viability_score": round(b.economic_viability_score or 0, 1),
            "poverty_filter_score": round(b.poverty_filter_score or 0, 1),
            "osm_activity_score": round(b.osm_activity_score or 0, 1),
            "population": ward.population,
            "unbanked_rate": ward.unbanked_rate,
            "boi_label": b.boi_label,
        })
        acc["boi_score"].append(b.boi_score or 0)
        acc["unbanked_score"].append(b.unbanked_population_score or 0)
        acc["bank_absence_score"].append(b.bank_absence_score or 0)
        acc["economic_viability_score"].append(b.economic_viability_score or 0)
        acc["poverty_filter_score"].append(b.poverty_filter_score or 0)
        acc["osm_activity_score"].append(b.osm_activity_score or 0)

    def avg(vals):
        return round(sum(vals) / len(vals)) if vals else 0

    lga_averages = {k: avg(v) for k, v in acc.items()}
    return {"lga_name": lga.name, "wards": wards, "lga_averages": lga_averages}
