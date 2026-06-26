"""
roi_calculator.py — deposit/revenue/payback projections for FSO deployment.

Given a ward's data and a number of Field Sales Officers (FSOs), we project:
  * monthly_accounts   new accounts acquired per month
  * expected_deposits  annual deposits mobilized (NGN)
  * yearly_revenue     year-1 revenue from the deposit margin (NGN)
  * acquisition_cost   upfront ramp investment over the deployment period (NGN)
  * payback_months     months to recover the acquisition cost from revenue
  * what_if            the same projection for 1–4 FSOs

Model (simple, explicit, tunable via the constants below):
  unbanked         = population × unbanked_rate
  monthly_accounts = round(unbanked × ACCOUNT_CAPTURE_RATE × fso_count)
  annual_accounts  = monthly_accounts × 12
  expected_deposits= annual_accounts × AVG_DEPOSIT_PER_ACCOUNT
  yearly_revenue   = expected_deposits × REVENUE_RATE
  acquisition_cost = fso_count × FSO_MONTHLY_COST × DEPLOYMENT_MONTHS
  payback_months   = round(acquisition_cost / (yearly_revenue / 12))
"""

# ---- Tunable business constants ----
AVG_DEPOSIT_PER_ACCOUNT = 45_000   # NGN, average balance per new account
REVENUE_RATE = 0.03                # margin earned on the deposits mobilized
FSO_MONTHLY_COST = 180_000         # NGN, fully-loaded cost per FSO per month
DEPLOYMENT_MONTHS = 3              # ramp/deployment period (upfront investment)
ACCOUNT_CAPTURE_RATE = 0.0013      # 0.13% of unbanked adults converted per FSO per month
                                   # (FSO works ~22 days/month, ~6 accounts/day) — realistic
                                   # for rural Nigeria cold-start deployment

# Per-FSO efficiency by team size: in a small ward each additional FSO faces a
# smaller addressable pool, so later FSOs convert fewer accounts each. This makes
# payback rise with team size (diminishing returns) rather than stay flat.
SATURATION = {1: 1.0, 2: 0.85, 3: 0.70, 4: 0.58}
SATURATION_DEFAULT = 0.50          # 5+ FSOs: heavy saturation


def compute_roi(ward: dict, fso_count: int) -> dict:
    """Full ROI projection for a given FSO count."""
    fso_count = max(1, int(fso_count))

    unbanked = (ward.get("population") or 0) * (ward.get("unbanked_rate") or 0.0)

    # Apply diminishing returns: each FSO in a larger team converts at lower
    # efficiency, so accounts grow sub-linearly while cost grows linearly.
    saturation = SATURATION.get(fso_count, SATURATION_DEFAULT)
    monthly_accounts = round(unbanked * ACCOUNT_CAPTURE_RATE * fso_count * saturation)
    annual_accounts = monthly_accounts * 12
    expected_deposits = annual_accounts * AVG_DEPOSIT_PER_ACCOUNT
    yearly_revenue = expected_deposits * REVENUE_RATE
    acquisition_cost = fso_count * FSO_MONTHLY_COST * DEPLOYMENT_MONTHS

    # Payback = upfront cost / monthly revenue. Guard against zero revenue.
    monthly_revenue = yearly_revenue / 12
    payback_months = round(acquisition_cost / monthly_revenue) if monthly_revenue > 0 else None

    return {
        "fso_count": fso_count,
        "monthly_accounts": monthly_accounts,
        "expected_deposits": int(expected_deposits),
        "yearly_revenue": int(yearly_revenue),
        "acquisition_cost": int(acquisition_cost),
        "payback_months": payback_months,  # None if there is no revenue to recover it
        "assumptions": {
            "avg_deposit_per_account": AVG_DEPOSIT_PER_ACCOUNT,
            "revenue_rate": REVENUE_RATE,
            "fso_monthly_cost": FSO_MONTHLY_COST,
            "deployment_months": DEPLOYMENT_MONTHS,
            "account_capture_rate": ACCOUNT_CAPTURE_RATE,
        },
    }


def what_if(ward: dict, max_fso: int = 4) -> list:
    """ROI projection for 1..max_fso FSOs (default 1–4)."""
    return [compute_roi(ward, n) for n in range(1, max_fso + 1)]


def compute_roi_with_whatif(ward: dict, fso_count: int = 2, max_fso: int = 4) -> dict:
    """Convenience: a single ROI plus the 1–max_fso what-if array."""
    result = compute_roi(ward, fso_count)
    result["what_if"] = what_if(ward, max_fso)
    return result
