"""
routers/pdf_export.py — one-page ward intelligence report as a PDF.

POST /wards/{ward_id}/export-pdf

Reuses the same intelligence assembly as GET /wards/{ward_id}/intelligence
(BOI + live OSM + Cerebras brief + ROI), renders pdf_template.html via token
replacement, and streams the result back as application/pdf via WeasyPrint.
"""

import io
import os
import re
from datetime import datetime, timezone

import markdown as md
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from weasyprint import HTML

from database import get_db
from routers.intelligence import ward_intelligence

router = APIRouter(tags=["pdf"])

_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "pdf_template.html")

_BOI_COLORS = {"GREEN": "#10b981", "AMBER": "#f59e0b", "RED": "#ef4444"}
_BAR_LABELS = [
    ("unbanked_population", "Unbanked Population"),
    ("bank_absence", "Bank Absence"),
    ("economic_viability", "Economic Viability"),
    ("poverty_filter", "Poverty Filter"),
    ("osm_activity", "Market Activity"),
]


# ---- small formatters (mirror the frontend) ----
def _ngn(amount):
    if amount is None:
        return "—"
    if amount >= 1_000_000_000:
        return f"₦{amount/1_000_000_000:.1f}B"
    if amount >= 1_000_000:
        return f"₦{amount/1_000_000:.1f}M"
    if amount >= 1_000:
        return f"₦{amount/1_000:.0f}K"
    return f"₦{amount:,.0f}"


def _num(n):
    return f"{round(n):,}" if n else "—"


def _pct(rate):
    return f"{round(rate*100)}%" if rate is not None else "—"


def _dist(km):
    return f"{km:.1f} km" if km is not None else "—"


def _progress_color(score):
    if score is None:
        return "#64748b"
    if score >= 70:
        return "#10b981"
    if score >= 40:
        return "#f59e0b"
    return "#ef4444"


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", (name or "ward")).strip("_") or "ward"


def _benchmark(score):
    """High/Medium/Low badge for a component score."""
    s = score or 0
    if s >= 70:
        return '<span class="badge b-high">High</span>'
    if s >= 40:
        return '<span class="badge b-med">Medium</span>'
    return '<span class="badge b-low">Low</span>'


def _build_html(intel: dict) -> str:
    ward = intel["ward"]
    boi = intel["boi"]

    pop = ward.get("population") or 0
    rate = ward.get("unbanked_rate") or 0
    unbanked = int(pop * rate)
    banked = max(0, pop - unbanked)
    label = boi.get("boi_label") or "RED"

    # BOI component score rows (Component | Score | Benchmark).
    comps = boi.get("components", {})
    comp_rows = []
    for key, text in _BAR_LABELS:
        val = comps.get(key) or 0
        comp_rows.append(
            f"<tr><td>{text}</td><td>{val:.0f}/100</td><td>{_benchmark(val)}</td></tr>"
        )

    brief_source = intel.get("deployment_brief_source", "")
    brief_tag = "Live AI (Cerebras)" if brief_source.startswith("cerebras") else "Template"

    with open(_TEMPLATE_PATH, encoding="utf-8") as f:
        html = f.read()

    replacements = {
        "__DATE__": datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC"),
        "__WARD_NAME__": ward.get("name") or "—",
        "__LGA_NAME__": ward.get("lga_name") or "—",
        "__STATE_NAME__": ward.get("state_name") or "—",
        "__BOI_COLOR__": _BOI_COLORS.get(label, "#64748b"),
        "__BOI_SCORE__": str(boi.get("boi_score", "—")),
        "__BOI_LABEL__": label,
        "__CONFIDENCE__": _pct(boi.get("data_confidence")),
        "__POPULATION__": _num(pop),
        "__UNBANKED__": _num(unbanked),
        "__BANKED__": _num(banked),
        "__UNBANKED_RATE__": _pct(rate),
        "__DISTANCE__": _dist(ward.get("nearest_bank_distance_km")),
        "__SIM__": _pct(ward.get("sim_penetration")),
        "__COMPONENT_ROWS__": "\n".join(comp_rows),
        "__BRIEF_SOURCE__": brief_tag,
        # Convert the markdown brief (## headers, **bold**) to real HTML so it
        # renders as formatted text in the PDF rather than literal characters.
        "__BRIEF_HTML__": md.markdown((intel.get("deployment_brief") or "").strip()),
    }
    for token, value in replacements.items():
        html = html.replace(token, str(value))
    return html


@router.post("/wards/{ward_id}/export-pdf")
def export_ward_pdf(ward_id: int, db: Session = Depends(get_db)):
    """Generate and stream a one-page PDF intelligence report for a ward."""
    try:
        intel = ward_intelligence(ward_id, db)  # reuse the full assembly
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"intelligence failed: {exc}")

    html = _build_html(intel)
    pdf_bytes = HTML(string=html, base_url=os.path.dirname(_TEMPLATE_PATH)).write_pdf()

    ward = intel["ward"]
    filename = f"bankmap_{_safe(ward.get('name'))}_{_safe(ward.get('lga_name'))}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
