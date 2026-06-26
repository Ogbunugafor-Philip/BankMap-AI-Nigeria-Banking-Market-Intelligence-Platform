"""
routers/lgas.py — endpoints for Local Government Areas within a state.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
import models

router = APIRouter(tags=["lgas"])


@router.get("/states/{state_id}/lgas")
def list_lgas(state_id: int, db: Session = Depends(get_db)):
    """
    Return all LGAs inside the given state, ordered alphabetically.
    Each item: {id, name, state_id}.
    """
    state = db.get(models.State, state_id)
    if state is None:
        raise HTTPException(status_code=404, detail="State not found")

    lgas = (
        db.query(models.LGA)
        .filter(models.LGA.state_id == state_id)
        .order_by(models.LGA.name.asc())
        .all()
    )
    return [
        {"id": lga.id, "name": lga.name, "state_id": lga.state_id}
        for lga in lgas
    ]
