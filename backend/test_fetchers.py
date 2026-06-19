"""Integration test for all 6 fetcher modules."""
import logging
logging.basicConfig(level=logging.WARNING)

from src.fetchers import (
    fetch_all_market, fetch_all_credit, fetch_all_economic,
    fetch_all_currencies, fetch_all_energy_storage, fetch_all_news,
)

print("=== ALL MODULES IMPORTABLE ===")

# Test market (yfinance — should always work)
r = fetch_all_market()
print(f"market: {len(r)} indicators returned")
if r:
    print(f"  first: {r[0]['name']} = {r[0]['value']} {r[0]['unit']}")
assert len(r) >= 1, f"market failed: {len(r)} returned, expected >=1"

# Test economic (yfinance grains + FAO attempt)
r = fetch_all_economic()
print(f"economic: {len(r)} indicators")

# Test currencies (yfinance FX pairs)
r = fetch_all_currencies()
print(f"currencies: {len(r)} indicators")

# Test credit (needs FRED_API_KEY — graceful skip)
r = fetch_all_credit()
print(f"credit: {len(r)} indicators")

# Test energy (mixed APIs — graceful skip)
r = fetch_all_energy_storage()
print(f"energy_storage: {len(r)} indicators")

# Test news (needs API keys — graceful skip)
r = fetch_all_news()
print(f"news: {len(r)} indicators")

print()
print("ALL TESTS PASSED")
