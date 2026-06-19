"""
Crisis Monitor data fetchers.

Importable modules:
- market: Brent, WTI, natgas, DXY, gold, 10Y, 2Y, VIX
- credit: IG OAS, HY OAS (FRED)
- economic: FAO FPI, grains, copper, BDI
- currencies: IDR, TRY, EGP, ARS, NGN, PKR, SHIBOR 1W, Caixin PMI
- energy_storage: EU gas %, US SPR, TTF gas, FBX
- news: NewsAPI, WHO RSS, ACLED, RCP polls

Each module exposes a fetch_all_<category>() function returning list[dict].
"""
from src.fetchers.market import fetch_all_market
from src.fetchers.credit import fetch_all_credit
from src.fetchers.economic import fetch_all_economic
from src.fetchers.currencies import fetch_all_currencies
from src.fetchers.energy_storage import fetch_all_energy_storage
from src.fetchers.news import fetch_all_news

__all__ = [
    "fetch_all_market",
    "fetch_all_credit",
    "fetch_all_economic",
    "fetch_all_currencies",
    "fetch_all_energy_storage",
    "fetch_all_news",
]

# ponytail: single entrypoint that runs all fetchers in sequence
ALL_FETCHERS = [
    ("market", fetch_all_market),
    ("credit", fetch_all_credit),
    ("economic", fetch_all_economic),
    ("currencies", fetch_all_currencies),
    ("energy_storage", fetch_all_energy_storage),
    ("news", fetch_all_news),
]
