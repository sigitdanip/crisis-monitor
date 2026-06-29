import sys
sys.path.insert(0, '/root/crisis-monitor/backend')

from src.agent.composite_scorer_v2 import score_composite

# Scenario 3 data from the test
result = score_composite({
    "brent_oil": 110, "wti_oil": 105, "eu_gas_storage": 60, "natgas_henry_hub": 7.0,
    "fao_food_price_index": 150, "wheat_futures": 9.0, "corn_futures": 7.0, "rice_price": 20,
    "us_ism_manufacturing": 45, "china_caixin_pmi": 46, "eurozone_manufacturing_pmi": 45,
    "us_jobless_claims": 320,
    "vix": 35, "move_bond_volatility": 150, "ted_spread": 80, "credit_spread": 300,
    "dxy_index": 110, "eur_usd": 1.00, "usd_cny": 7.4,
    "copper_price": 4.5, "silver_price": 45,
    "baltic_dry_index": 2000, "scfi": 4000,
    "global_terrorism_index": 7.5,
    "hormuz_strait": "closure", "taiwan_strait_tension": "high",
    "russia_ukraine_conflict": "major", "middle_east_conflict": "widespread",
    "china_taiwan_tension": "critical",
})

print(f"Composite: {result['composite']}")
print(f"Total weight: {result['total_weight']}")
print(f"Available count: {result['available_count']}")
print()

# Show per-indicator scores
for slug, details in sorted(result['indicator_details'].items(), key=lambda x: x[1]['raw_score']):
    score = details['raw_score']
    marker = '***' if score != 1.0 else ''
    print(f"  {slug:30s} raw={score:.4f}  weighted={details['weighted_score']:.4f}  w={details['weight']}  cat={details['category']} {marker}")

print()
print('Category weighted sums:', result['category_scores'])
