"""
main.py — FastAPI application entrypoint for BankMap AI.

Wires the three routers (states, lgas, wards), enables CORS, and exposes a
health check. Run with:  uvicorn main:app --reload  (from the backend/ folder)
"""

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import get_db, init_db
import models
from routers import states, lgas, wards, intelligence, pdf_export
from routers.auth_router import router as auth_router

app = FastAPI(
    title="BankMap AI",
    description="Ward-level banking market intelligence platform for Nigeria.",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# CORS — open during Phase 1 development; tighten allow_origins for production.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth_router)  # router already carries the /auth prefix
app.include_router(states.router)
app.include_router(lgas.router)
app.include_router(wards.router)
app.include_router(intelligence.router)
app.include_router(pdf_export.router)


@app.on_event("startup")
def on_startup():
    """Ensure PostGIS + tables exist when the API boots."""
    init_db()


@app.get("/health", tags=["health"])
def health(db: Session = Depends(get_db)):
    """Liveness check: returns status and the total number of wards loaded."""
    ward_count = db.query(models.Ward).count()
    return {"status": "ok", "ward_count": ward_count}
