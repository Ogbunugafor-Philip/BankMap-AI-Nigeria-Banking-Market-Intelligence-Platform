"""
cerebras_service.py — AI ward-intelligence briefs via the Cerebras inference API.

Given a ward's real demographics + its BOI, we ask the Cerebras model
(gpt-oss-120b) to write a concise, actionable ward intelligence brief for a
Nigerian bank manager — focused on who lives there, why the BOI is what it is,
which banking products fit, and the strategic FSO approach (FSO count is sized
from population only). No financial projections / ROI figures.

If the API key is missing or the call fails, we fall back to a deterministic
template brief (the `source` field records which path was taken).
"""

import os

import requests
from dotenv import load_dotenv

# override=True so the project's .env wins over any stale shell env var.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)

CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")
CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"

SYSTEM_PROMPT = (
    "You are a banking expansion analyst for a Nigerian commercial bank. "
    "Write clear, actionable ward intelligence briefs for bank managers. "
    "Focus on demographics, market opportunity, and strategic approach. "
    "Do not mention specific financial projections or ROI figures. "
    "Be specific about the ward. Maximum 130 words. Plain English. "
    "Use bullet points."
)


def _suggested_fso_count(unbanked_adults: int) -> int:
    """1 FSO per 15,000 unbanked adults, clamped to 1–4."""
    return max(1, min(4, round(unbanked_adults / 15000)))


def _build_user_prompt(ward: dict, boi: dict) -> str:
    """Assemble the demographic-focused user prompt (no ROI)."""
    ward_name = ward.get("name")
    lga_name = ward.get("lga_name")
    state_name = ward.get("state_name")

    population = ward.get("population") or 0
    unbanked_rate = ward.get("unbanked_rate") or 0
    unbanked_adults = round(population * unbanked_rate)
    unbanked_pct = round(unbanked_rate * 100)
    nearest_bank_km = round(ward.get("nearest_bank_distance_km") or 0, 1)
    sim_pct = round((ward.get("sim_penetration") or 0) * 100)
    poverty_index = ward.get("poverty_index") or 0
    boi_score = boi.get("boi_score")
    boi_label = boi.get("boi_label")
    confidence_pct = round((boi.get("data_confidence") or 0) * 100)

    return f"""Write a deployment brief for {ward_name} ward, {lga_name} LGA,
{state_name} State.

USE ONLY THESE FACTS:
- Population: {population:,}
- Unbanked adults: {unbanked_adults:,} ({unbanked_pct}% of population)
- Nearest bank branch: {nearest_bank_km} km away
- SIM penetration: {sim_pct}% (economic connectivity proxy)
- Poverty index: {poverty_index:.2f} (0=wealthy, 1=very poor)
- BOI score: {boi_score}/100 ({boi_label})
- Data confidence: {confidence_pct}%

Focus on:
1. Who lives here and their banking needs
2. Why this ward is or is not a priority
3. What banking approach suits this population
4. Recommended FSO count based on population size only
   (1 FSO per 15,000 unbanked adults, minimum 1, maximum 4)"""


def generate_deployment_brief(ward: dict, boi: dict, timeout: int = 60) -> dict:
    """
    Return {brief, source, model}. `source` is 'cerebras' on a live generation
    or 'template' on fallback. Never raises.
    """
    user_prompt = _build_user_prompt(ward, boi)

    if not CEREBRAS_API_KEY:
        return {"brief": _template_brief(ward, boi),
                "source": "template (no API key configured)", "model": None}

    payload = {
        "model": CEREBRAS_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
        # gpt-oss is a reasoning model: leave room so the final answer isn't
        # truncated by reasoning tokens, and keep reasoning effort low.
        "max_tokens": 2000,
        "reasoning_effort": "low",
    }
    headers = {
        "Authorization": f"Bearer {CEREBRAS_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(CEREBRAS_URL, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        content = (data["choices"][0]["message"].get("content") or "").strip()
        if not content:
            raise ValueError("empty content from model")
        return {"brief": content, "source": "cerebras", "model": CEREBRAS_MODEL}
    except Exception as exc:
        return {
            "brief": _template_brief(ward, boi),
            "source": f"template (cerebras failed: {type(exc).__name__})",
            "model": CEREBRAS_MODEL,
        }


def _template_brief(ward: dict, boi: dict) -> str:
    """Deterministic fallback brief — demographics + strategy, no ROI figures."""
    pop = ward.get("population") or 0
    rate = ward.get("unbanked_rate") or 0
    unbanked = int(pop * rate)
    label = boi.get("boi_label")
    fso = _suggested_fso_count(unbanked)
    distance = round(ward.get("nearest_bank_distance_km") or 0, 1)
    sim_pct = round((ward.get("sim_penetration") or 0) * 100)
    priority = (
        "a high-priority deployment target" if label == "GREEN"
        else "a monitor-and-plan ward" if label == "AMBER"
        else "a low-priority ward"
    )
    return (
        f"- {ward.get('name')} ward ({ward.get('lga_name')} LGA, {ward.get('state_name')} State) "
        f"has {pop:,} residents, of whom about {unbanked:,} ({round(rate*100)}%) are unbanked.\n"
        f"- Banking Opportunity Index {boi.get('boi_score')}/100 ({label}) makes it {priority}.\n"
        f"- The nearest branch is {distance} km away, so agent banking and mobile-first "
        f"onboarding suit this population (SIM penetration {sim_pct}%).\n"
        f"- Recommended approach: low-cost savings and agent accounts; prioritise "
        f"financial-literacy outreach given the unbanked share.\n"
        f"- Suggested field team: {fso} Field Sales Officer(s), sized to the unbanked population."
    )
