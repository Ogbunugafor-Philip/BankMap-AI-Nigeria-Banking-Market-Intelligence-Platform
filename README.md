# BankMap AI — Nigeria Banking Market Intelligence Platform

![BankMap AI](https://img.shields.io/badge/BankMap-AI-0ea5e9?style=for-the-badge)
![Nigeria](https://img.shields.io/badge/Nigeria-37%20States-green?style=for-the-badge)
![Wards](https://img.shields.io/badge/Wards-9%2C308-blue?style=for-the-badge)
![Live](https://img.shields.io/badge/Live-aibankmap.space-success?style=for-the-badge)

## Live Demo
**[https://aibankmap.space](https://aibankmap.space)**

Demo credentials:
- Email: philiposita1041@gmail.com
- Password: Osita@1989

## What It Does
BankMap AI gives Nigerian bank managers instant ward-level market
intelligence across all 774 LGAs and 9,308 wards in Nigeria —
with zero manual data input.

A manager selects a State and LGA. The system returns:
- Banking Opportunity Index (BOI) score for every ward (0–100)
- GREEN / AMBER / RED deployment labels
- AI-generated deployment brief (Cerebras gpt-oss-120b)
- FSO count simulator with ROI projection
- PDF export for presentations

## The Problem It Solves
Nigerian bank managers deploy Field Sales Officers (FSOs) based on
intuition rather than data. High-potential unbanked zones are
consistently missed in favor of already-penetrated urban areas.
No affordable ward-level intelligence tool existed for Nigerian
banking expansion — until now.

## Data Sources (All Real, All Public)
| Dataset | Source | Coverage |
|---------|--------|----------|
| Ward Boundaries | GRID3 / INEC Operational Wards v1.0 | 9,308 wards |
| Population | WorldPop 2020 UN-adjusted | All wards |
| Financial Inclusion | EFInA Access to Finance Survey 2020 | 37 states |
| Bank Branches | CBN / OpenStreetMap | 891 branches |
| Poverty Index | NBS Multidimensional Poverty Index 2022 | All LGAs |
| SIM Penetration | NCC / DHS-MICS 2021 | 37 states |
| Live Market Data | OpenStreetMap Overpass API | Real-time |

## Banking Opportunity Index (BOI)
Five-component weighted score:
- Unbanked Population (30%) — adults without bank accounts
- Bank Absence (25%) — distance to nearest branch
- Economic Viability (20%) — SIM penetration proxy
- Poverty Filter (15%) — MPI sweet spot targeting
- Live Market Activity (10%) — OpenStreetMap real-time data

## Tech Stack
| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (Python) |
| Database | PostgreSQL + PostGIS |
| Spatial Data | GeoAlchemy2, GeoPandas |
| Map Engine | Leaflet.js + GRID3 Shapefiles |
| AI Narrative | Cerebras gpt-oss-120b |
| Frontend | React 19 + Tailwind CSS |
| PDF Export | WeasyPrint |
| Deployment | Nginx + systemd + Contabo VPS |

## API Endpoints
| Endpoint | Description |
|----------|-------------|
| GET /states | All 37 states |
| GET /states/{id}/lgas | LGAs in a state |
| GET /lgas/{id}/intelligence/summary | Fast map render |
| GET /lgas/{id}/intelligence | Full LGA intelligence |
| GET /wards/{id}/intelligence | Single ward full report |
| GET /wards/{id}/roi?fso_count=2 | ROI calculator |
| POST /wards/{id}/export-pdf | PDF report export |
| POST /auth/login | Demo authentication |

## Local Setup
```bash
# Clone
git clone https://github.com/Ogbunugafor-Philip/BankMap-AI-Nigeria-Banking-Market-Intelligence-Platform.git
cd BankMap-AI-Nigeria-Banking-Market-Intelligence-Platform

# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Database (requires PostgreSQL + PostGIS)
createdb bankmap
psql -d bankmap -c "CREATE EXTENSION postgis;"

# Configure
cp .env.example .env
# Edit .env with your database credentials and Cerebras API key

# Start
uvicorn main:app --reload --port 8001
```

## Project Structure
```
bankmap-ai/
├── backend/
│   ├── main.py              # FastAPI app
│   ├── models.py            # SQLAlchemy models
│   ├── boi_engine.py        # BOI scoring algorithm
│   ├── cerebras_service.py  # AI brief generation
│   ├── osm_service.py       # OpenStreetMap integration
│   ├── roi_calculator.py    # Financial projections
│   ├── routers/             # API route handlers
│   └── scripts/             # Data loading scripts
└── frontend/
    ├── src/
    │   ├── pages/           # Login, Landing, Dashboard
    │   ├── components/      # Map, Intelligence panel, etc
    │   └── services/        # API client
    └── public/
```

## Author
**Philip Ogbunugafor**
Built as a flagship portfolio project demonstrating:
- Spatial data engineering (PostGIS, GeoJSON, shapefiles)
- Real Nigerian government dataset integration
- AI-powered narrative generation (Cerebras)
- Full-stack React + FastAPI production deployment

---
*BankMap AI is a decision-support tool. All estimates are
model-derived from public data and should be validated
with ground-level reconnaissance before FSO deployment.*
