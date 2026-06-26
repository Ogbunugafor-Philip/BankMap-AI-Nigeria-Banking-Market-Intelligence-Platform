"""
routers/wards.py — endpoints for wards (the core analytical unit).

Geometry is returned as GeoJSON (via PostGIS ST_AsGeoJSON) so the frontend can
render ward polygons directly on a map.
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy.orm import Session

from database import get_db
import models

router = APIRouter(tags=["wards"])


def _indicators(ward: models.Ward) -> dict:
    """The non-spatial market-intelligence fields for a ward."""
    return {
        "id": ward.id,
        "name": ward.name,
        "population": ward.population,
        "unbanked_rate": ward.unbanked_rate,
        "poverty_index": ward.poverty_index,
        "sim_penetration": ward.sim_penetration,
        "nearest_bank_distance_km": ward.nearest_bank_distance_km,
        "data_confidence": ward.data_confidence,
    }


@router.get("/lgas/{lga_id}/wards")
def list_wards(lga_id: int, db: Session = Depends(get_db)):
    """
    Return all wards inside the given LGA. Each ward includes its indicators
    plus its geometry as GeoJSON for map rendering.
    """
    lga = db.get(models.LGA, lga_id)
    if lga is None:
        raise HTTPException(status_code=404, detail="LGA not found")

    # Fetch wards together with their geometry serialized to GeoJSON in one query.
    rows = (
        db.query(models.Ward, ST_AsGeoJSON(models.Ward.geometry))
        .filter(models.Ward.lga_id == lga_id)
        .order_by(models.Ward.name.asc())
        .all()
    )

    result = []
    for ward, geojson in rows:
        item = _indicators(ward)
        item["lga_id"] = ward.lga_id
        item["state_id"] = ward.state_id
        item["geometry"] = json.loads(geojson) if geojson else None
        result.append(item)
    return result


@router.get("/wards/{ward_id}")
def get_ward(ward_id: int, db: Session = Depends(get_db)):
    """
    Return full detail for a single ward, including geometry as GeoJSON.
    """
    row = (
        db.query(models.Ward, ST_AsGeoJSON(models.Ward.geometry))
        .filter(models.Ward.id == ward_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Ward not found")

    ward, geojson = row
    detail = _indicators(ward)
    detail["lga_id"] = ward.lga_id
    detail["state_id"] = ward.state_id

    # Friendly names for context.
    lga = db.get(models.LGA, ward.lga_id)
    state = db.get(models.State, ward.state_id)
    detail["lga_name"] = lga.name if lga else None
    detail["state_name"] = state.name if state else None

    detail["geometry"] = json.loads(geojson) if geojson else None
    return detail
