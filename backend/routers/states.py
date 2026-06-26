"""
routers/states.py — endpoints for the top administrative level (states).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
import models

router = APIRouter(tags=["states"])


@router.get("/states")
def list_states(db: Session = Depends(get_db)):
    """
    Return all states (36 + FCT), ordered alphabetically.
    Each item: {id, name, state_code}.
    """
    states = db.query(models.State).order_by(models.State.name.asc()).all()
    return [
        {"id": s.id, "name": s.name, "state_code": s.state_code}
        for s in states
    ]
