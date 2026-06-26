"""
models.py — SQLAlchemy ORM models for BankMap AI.

Four tables:
  states          — 36 states + FCT
  lgas            — Local Government Areas (each belongs to a state)
  wards           — electoral wards (the core analytical unit) with geometry
                    and all market-intelligence indicators
  bank_branches   — CBN branch directory, used to compute nearest-bank distance

All geometry uses SRID 4326 (WGS84).
"""

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from database import Base


class State(Base):
    __tablename__ = "states"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False, index=True)
    state_code = Column(String)  # e.g. "LA" for Lagos, "FC" for FCT

    lgas = relationship("LGA", back_populates="state", cascade="all, delete-orphan")
    wards = relationship("Ward", back_populates="state")


class LGA(Base):
    __tablename__ = "lgas"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, index=True)
    state_id = Column(Integer, ForeignKey("states.id"), nullable=False)

    state = relationship("State", back_populates="lgas")
    wards = relationship("Ward", back_populates="lga")

    # A given LGA name is unique within its state (names repeat across states).
    __table_args__ = (UniqueConstraint("name", "state_id", name="uq_lga_name_state"),)


class Ward(Base):
    __tablename__ = "wards"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, index=True)

    lga_id = Column(Integer, ForeignKey("lgas.id"), nullable=False)
    state_id = Column(Integer, ForeignKey("states.id"), nullable=False)

    # Ward boundary polygon from GRID3 shapefiles (WGS84).
    geometry = Column(Geometry(geometry_type="MULTIPOLYGON", srid=4326))

    # --- Market-intelligence indicators (populated by the loader scripts) ---
    population = Column(Integer)               # NBS ward population
    unbanked_rate = Column(Float)             # EFInA financial-exclusion rate
    poverty_index = Column(Float)             # NBS Multidimensional Poverty Index
    sim_penetration = Column(Float)           # NCC SIM penetration (modelled down)
    nearest_bank_distance_km = Column(Float)  # computed from CBN branches via PostGIS

    # How much of this ward's data is directly sourced vs. modelled (0.0–1.0).
    data_confidence = Column(Float)

    lga = relationship("LGA", back_populates="wards")
    state = relationship("State", back_populates="wards")
    branches = relationship("BankBranch", back_populates="ward")

    # A ward name is unique within its LGA.
    __table_args__ = (UniqueConstraint("name", "lga_id", name="uq_ward_name_lga"),)


class BankBranch(Base):
    __tablename__ = "bank_branches"

    id = Column(Integer, primary_key=True)
    bank_name = Column(String)
    branch_name = Column(String)
    state = Column(String)
    lga = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)

    # Filled in by load_cbn.py via PostGIS point-in-polygon; nullable because a
    # branch may fall outside every loaded ward boundary.
    ward_id = Column(Integer, ForeignKey("wards.id"), nullable=True)

    ward = relationship("Ward", back_populates="branches")


class WardBOI(Base):
    """Computed Banking Opportunity Index for a ward (one row per ward)."""

    __tablename__ = "ward_boi"

    id = Column(Integer, primary_key=True)
    ward_id = Column(Integer, ForeignKey("wards.id"), unique=True, nullable=False, index=True)

    boi_score = Column(Integer)
    boi_label = Column(String)  # GREEN / AMBER / RED

    # The five component scores (each 0–100, pre-weighting).
    unbanked_population_score = Column(Float)
    bank_absence_score = Column(Float)
    economic_viability_score = Column(Float)
    poverty_filter_score = Column(Float)
    osm_activity_score = Column(Float)

    # Full explainability payload + the confidence behind this score.
    explanation = Column(JSON)
    data_confidence = Column(Float)

    computed_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    ward = relationship("Ward")
