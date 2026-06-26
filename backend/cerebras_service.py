"""
cerebras_service.py — AI deployment briefs via the Cerebras inference API.

Given a ward's real data + its BOI + an ROI projection, we ask the Cerebras
model (gpt-oss-120b) to write a concise, actionable Field Sales Officer (FSO)
deployment brief for a Nigerian commercial bank.

If the API key is missing or the call fails for any reason, we fall back to a
deterministic template brief built from the same numbers, so the endpoint always
returns something useful (the `source` field records which path was taken).
"""

import os

import requests
from dotenv import load_dotenv

# Load .env from the project root (one level above backend/). override=True so
# the project's .env is authoritative even if a stale CEREBRAS_API_KEY is already
# exported in the shell environment.
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)

CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
CEREBRAS_MODEL = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")
CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"

SYSTEM_PROMPT = (
    "You are a banking expansion analyst for a Nigerian commercial bank. "
    "Write clear, actionable FSO deployment briefs. Be specific with the data. "
    "Always end with FSO recommendation and estimated monthly account acquisition. "
    "Plain English. Maximum 150 words."
)


def _build_user_prompt(ward: dict, boi: dict, roi: dict) -> str:
    """
    Assemble the user prompt, passing the ALREADY-CALCULATED ROI figures in
    explicitly and instructing the model not to compute anything itself (so the
    brief can never contradict the ROI panel / PDF).
    """
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

    fso_count = roi.get("fso_count")
    monthly_accounts = roi.get("monthly_accounts")
    yearly_revenue = roi.get("yearly_revenue") or 0
    payback_months = roi.get("payback_months")
    # Derive monthly deposits from the pre-calculated yearly revenue.
    monthly_deposits = round(yearly_revenue / 12)

    user_prompt = f"""Generate a deployment brief for {ward_name} ward,
{lga_name} LGA, {state_name} State.

WARD DATA (use these exact figures, do not recalculate):
- Population: {population:,}
- Unbanked adults: {unbanked_adults:,} ({unbanked_pct}% of population)
- Nearest bank branch: {nearest_bank_km} km away
- SIM penetration: {sim_pct}%
- Poverty index: {poverty_index:.2f}
- Banking Opportunity Index: {boi_score}/100 ({boi_label})

PRE-CALCULATED PROJECTIONS (use these exact numbers):
- Recommended FSOs: {fso_count}
- Monthly new accounts: {monthly_accounts}
- Expected monthly deposits: NGN {monthly_deposits:,}
- Expected yearly revenue: NGN {yearly_revenue:,}
- Payback period: {payback_months} months
- Data confidence: {confidence_pct}%

Write a professional 120-word deployment brief using ONLY the figures above.
Do not calculate or estimate any numbers yourself.
End with: Recommended FSOs: {fso_count} | Monthly accounts: {monthly_accounts} | Payback: {payback_months} months"""
    return user_prompt


def generate_deployment_brief(ward: dict, boi: dict, roi: dict, timeout: int = 60) -> dict:
    """
    Return {brief, source, model}. `source` is 'cerebras' on a live generation
    or 'template' on fallback. Never raises.
    """
    user_prompt = _build_user_prompt(ward, boi, roi)

    if not CEREBRAS_API_KEY:
        return {"brief": _template_brief(ward, boi, roi),
                "source": "template (no API key configured)", "model": None}

    payload = {
        "model": CEREBRAS_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
        # gpt-oss is a reasoning model: leave generous room so the final answer
        # is not truncated by reasoning tokens, and keep reasoning effort low.
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
            "brief": _template_brief(ward, boi, roi),
            "source": f"template (cerebras failed: {type(exc).__name__})",
            "model": CEREBRAS_MODEL,
        }


def _template_brief(ward: dict, boi: dict, roi: dict) -> str:
    """Deterministic fallback brief from the same calculated numbers."""
    pop = ward.get("population") or 0
    unbanked = int(pop * (ward.get("unbanked_rate") or 0))
    return (
        f"{ward.get('name')} ward ({ward.get('lga_name')} LGA, {ward.get('state_name')} State) "
        f"scores {boi.get('boi_score')}/100 on the Banking Opportunity Index "
        f"({boi.get('boi_label')}). With about {unbanked:,} unbanked adults out of "
        f"{pop:,} residents and the nearest branch {ward.get('nearest_bank_distance_km', 0):.1f} km away, "
        f"this ward is {'a strong' if boi.get('boi_label') == 'GREEN' else 'a moderate' if boi.get('boi_label') == 'AMBER' else 'a low-priority'} "
        f"expansion target. Mobile penetration of {(ward.get('sim_penetration') or 0):.0%} supports "
        f"agent and digital onboarding. "
        f"Recommendation: deploy {roi.get('fso_count')} Field Sales Officer(s), "
        f"projected to acquire ~{roi.get('monthly_accounts')} new accounts per month "
        f"(~NGN {roi.get('expected_deposits', 0):,} monthly deposits), "
        f"with payback in about {roi.get('payback_months')} months."
    )
