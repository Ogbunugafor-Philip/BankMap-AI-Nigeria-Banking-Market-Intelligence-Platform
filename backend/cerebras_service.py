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

SYSTEM_PROMPT = """You are a banking expansion analyst for a Nigerian commercial bank, \
writing a ward intelligence brief for a branch manager who must decide where to deploy field officers.

Write two to three short, flowing paragraphs of plain prose. Hard rules:
- Under 200 words total.
- No markdown headers, no bullet points, no dashes, no numbered lists. Paragraphs only.
- Open with one specific sentence that names the ward, its LGA and state, and the exact number of unbanked adults.
- Ground every claim in the figures provided. Do not invent numbers or facts.
- Never use these phrases, or anything like them: "vibrant community", "untapped potential", \
"last mile", "financial inclusion journey", "banking the unbanked", or generic financial-inclusion \
buzzwords. Be concrete and specific to this ward's data.
- End with one single, concrete, highest-impact recommendation for this ward — not a list of options."""


def _suggested_fso_count(unbanked_adults: int) -> int:
    """1 FSO per 15,000 unbanked adults, clamped to 1–4."""
    return max(1, min(4, round(unbanked_adults / 15000)))


def _distance_guidance(km: float) -> str:
    """Concrete framing for the bank-access gap, banded by distance."""
    if km < 5:
        return ("with a branch within walking distance, the gap is service quality "
                "and product fit, not physical access")
    if km < 10:
        return "a moderate access gap that agent banking can bridge"
    if km < 20:
        return ("a significant 10km+ gap making this a strong candidate for agent "
                "or mobile-first deployment")
    return ("critically underserved — over 20km from the nearest branch, requiring "
            "a dedicated field presence")


def _tier_guidance(label: str) -> str:
    """How to characterise the BOI tier."""
    return {
        "GREEN": "ranks in the top opportunity tier nationally",
        "AMBER": "is mid-tier opportunity — monitor and assess in 6 months",
        "RED": ("is lower immediate opportunity, likely due to small market size or "
                "existing service coverage"),
    }.get(label, "has an unrated opportunity profile")


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

    distance_guidance = _distance_guidance(nearest_bank_km)
    tier_guidance = _tier_guidance(boi_label)
    fso = _suggested_fso_count(unbanked_adults)

    return f"""Write the brief for {ward_name} ward, {lga_name} LGA, {state_name} State.

Facts (use only these, do not invent others):
- Population: {population:,}
- Unbanked adults: {unbanked_adults:,} ({unbanked_pct}% of the population)
- Nearest bank branch: {nearest_bank_km} km away
- SIM penetration: {sim_pct}%
- Poverty index: {poverty_index:.2f} (0 = wealthy, 1 = very poor)
- Banking Opportunity Index: {boi_score}/100 ({boi_label})
- Data confidence: {confidence_pct}%

Interpretation you must weave in, in your own words:
- Bank access: {nearest_bank_km} km is {distance_guidance}.
- Opportunity tier: this ward {tier_guidance}.

Open with one specific sentence that names {ward_name}, {lga_name}, {state_name} and the \
{unbanked_adults:,} unbanked adults. Explain who is likely underserved and which products fit, \
using the bank-access and tier framing above. Close with one concrete recommendation — the single \
highest-impact action for this ward. Population-based sizing suggests roughly {fso} field officer(s); \
mention this only if it forms part of that single recommendation."""


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
    """Deterministic fallback brief — flowing prose, no ROI figures, no buzzwords."""
    pop = ward.get("population") or 0
    rate = ward.get("unbanked_rate") or 0
    unbanked = int(pop * rate)
    label = boi.get("boi_label")
    score = boi.get("boi_score")
    fso = _suggested_fso_count(unbanked)
    distance = round(ward.get("nearest_bank_distance_km") or 0, 1)
    sim_pct = round((ward.get("sim_penetration") or 0) * 100)
    name = ward.get("name")
    lga = ward.get("lga_name")
    state = ward.get("state_name")

    access = _distance_guidance(distance)
    tier = _tier_guidance(label)

    # Single highest-impact recommendation, chosen by access gap and tier.
    if distance >= 20:
        action = (f"establish a dedicated field presence of {fso} officer(s) with agent "
                  f"onboarding, since no branch is realistically reachable")
    elif distance >= 10:
        action = (f"deploy {fso} field officer(s) running agent and mobile-first account "
                  f"opening, leveraging the {sim_pct}% SIM penetration")
    elif label == "RED":
        action = ("hold direct investment and revisit after the next data refresh; the "
                  "near-term return does not justify a dedicated team")
    else:
        action = (f"prioritise product fit and {sim_pct}%-SIM mobile onboarding over new "
                  f"physical access, deploying {fso} officer(s) on low-cost savings and agent accounts")

    return (
        f"{name} ward in {lga} LGA, {state} State, has about {unbanked:,} unbanked adults among "
        f"{pop:,} residents ({round(rate * 100)}% of the population). At {distance} km to the nearest "
        f"branch, this is {access}. "
        f"On the Banking Opportunity Index it scores {score}/100 and {tier}, so the population is best "
        f"served by low-cost savings and agent accounts rather than a full branch. "
        f"The single highest-impact move is to {action}."
    )
