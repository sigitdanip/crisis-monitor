"""Composite Alert Scorer — rule-based 0-16 across 8 categories.

Runs BEFORE the LLM agents. Feeds into their prompts as context.
"""
from typing import Dict, List, Any

# Category scoring thresholds per the plan
CATEGORIES = [
    "geopolitical",
    "energy",
    "credit_financial",
    "em_currency",
    "food",
    "china",
    "debt_sovereign",
    "social_political",
]

INTERPRETATIONS = {
    (0, 4): "monitor",
    (5, 8): "elevated",
    (9, 12): "high",
    (13, 16): "crisis",
}


def _in_range(val: float | None, lo: float, hi: float) -> bool:
    """True if val is between lo and hi (inclusive). None returns False."""
    return val is not None and lo <= val <= hi


def score_geopolitical(indicators: Dict[str, Any]) -> int:
    """
    0: No NATO/Hormuz escalation
    1: NATO fracture signals; no Hormuz resolution
    2: US withdraws from NATO; Strait closed past Sep
    """
    nato = (indicators.get("nato_fracture", 0) or 0)
    hormuz = indicators.get("hormuz_closure", "")
    us_withdraw = indicators.get("us_nato_withdrawal", 0) or 0
    if us_withdraw >= 1 or (hormuz and "closed" in str(hormuz).lower()):
        return 2
    if nato >= 1:
        return 1
    return 0


def score_energy(indicators: Dict[str, Any]) -> int:
    """
    0: Brent < $90
    1: Brent $90-$110
    2: Brent > $110 sustained
    """
    brent = indicators.get("brent_price")
    if brent is None:
        return 0
    if brent > 110:
        return 2
    if brent >= 90:
        return 1
    return 0


def score_credit_financial(indicators: Dict[str, Any]) -> int:
    """
    0: IG OAS < 150, HY < 400
    1: IG 150-200, HY 400-600
    2: IG > 200, HY > 600
    """
    ig = indicators.get("ig_oas")
    hy = indicators.get("hy_oas")
    ig_score = 0
    hy_score = 0
    if ig is not None:
        if ig > 200:
            ig_score = 2
        elif ig >= 150:
            ig_score = 1
    if hy is not None:
        if hy > 600:
            hy_score = 2
        elif hy >= 400:
            hy_score = 1
    return max(ig_score, hy_score)


def score_em_currency(indicators: Dict[str, Any]) -> int:
    """
    0: No major EM stress
    1: 1-2 currencies breaching triggers
    2: 3+ currencies simultaneous breach
    """
    breaches = 0
    for key in ("idr_breach", "try_breach", "egp_breach", "ars_breach",
                "ngn_breach", "pkr_breach"):
        if indicators.get(key):
            breaches += 1
    if breaches >= 3:
        return 2
    if breaches >= 1:
        return 1
    return 0


def score_food(indicators: Dict[str, Any]) -> int:
    """
    0: FAO index flat/falling
    1: CME grains up >10% monthly
    2: FAO index up >10% monthly
    """
    fao_change = indicators.get("fao_monthly_change_pct")
    grain_surge = indicators.get("cme_grains_monthly_pct")
    if fao_change is not None and fao_change > 10:
        return 2
    if grain_surge is not None and grain_surge > 10:
        return 1
    return 0


def score_china(indicators: Dict[str, Any]) -> int:
    """
    0: Caixin PMI > 50
    1: Caixin PMI 48-50
    2: Caixin PMI < 48 + property default
    """
    caixin = indicators.get("caixin_pmi")
    prop_default = indicators.get("china_property_default", 0) or 0
    if caixin is None:
        return 0
    if caixin < 48 and prop_default >= 1:
        return 2
    if caixin < 50:
        return 1
    return 0


def score_debt_sovereign(indicators: Dict[str, Any]) -> int:
    """
    0: Spreads stable
    1: Italy BTP-Bund > 250 bps
    2: Any G20 sovereign CDS doubling
    """
    btp_bund = indicators.get("btp_bund_spread")
    cds_doubling = indicators.get("cds_doubling", 0) or 0
    if cds_doubling >= 1:
        return 2
    if btp_bund is not None and btp_bund > 250:
        return 1
    return 0


def score_social_political(indicators: Dict[str, Any]) -> int:
    """
    0: Isolated protests
    1: Protests in 2+ countries
    2: Protests in 3+ countries + govt crisis
    """
    protest_countries = indicators.get("protest_countries", 0) or 0
    govt_crisis = indicators.get("govt_crisis", 0) or 0
    if protest_countries >= 3 and govt_crisis >= 1:
        return 2
    if protest_countries >= 2:
        return 1
    return 0


SCORERS = {
    "geopolitical": score_geopolitical,
    "energy": score_energy,
    "credit_financial": score_credit_financial,
    "em_currency": score_em_currency,
    "food": score_food,
    "china": score_china,
    "debt_sovereign": score_debt_sovereign,
    "social_political": score_social_political,
}


def score_composite(indicators: Dict[str, Any]) -> Dict[str, Any]:
    """
    Score all 8 categories and return composite analysis.
    Args:
        indicators: dict of indicator values keyed by name/slug.
    Returns:
        {category_scores: {cat: score}, composite: int 0-16, interpretation: str}
    """
    category_scores = {}
    for cat, scorer in SCORERS.items():
        category_scores[cat] = scorer(indicators)

    composite = sum(category_scores.values())

    interpretation = "monitor"
    for (lo, hi), label in INTERPRETATIONS.items():
        if lo <= composite <= hi:
            interpretation = label
            break

    return {
        "category_scores": category_scores,
        "composite": composite,
        "interpretation": interpretation,
    }


# Self-check
if __name__ == "__main__":
    # Normal state — everything at baseline
    normal = score_composite({"brent_price": 78, "caixin_pmi": 51.5})
    assert normal["composite"] == 0, f"Expected 0, got {normal['composite']}"
    assert normal["interpretation"] == "monitor"

    # Crisis state — multiple red flags
    crisis = score_composite({
        "brent_price": 115, "ig_oas": 220, "hy_oas": 650,
        "caixin_pmi": 46, "china_property_default": 1,
        "btp_bund_spread": 280, "cds_doubling": 1,
        "protest_countries": 4, "govt_crisis": 1,
        "us_nato_withdrawal": 1, "idr_breach": 1, "try_breach": 1, "egp_breach": 1,
        "fao_monthly_change_pct": 12,
    })
    assert crisis["composite"] >= 13, f"Expected >=13 crisis, got {crisis['composite']}"
    assert crisis["interpretation"] == "crisis"
    print(f"composite_scorer OK — normal={normal['composite']}, crisis={crisis['composite']}")
