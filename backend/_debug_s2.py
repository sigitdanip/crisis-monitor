import sys
sys.path.insert(0, '/root/crisis-monitor/backend')

from src.agent.composite_scorer_v2 import score_composite

# Scenario 2 data from the test
result = score_composite({
    'brent_oil': 90, 'wti_oil': 85, 'eu_gas_storage': 70, 'natgas_henry_hub': 4.5,
    'fao_food_price_index': 130, 'wheat_futures': 7.5, 'corn_futures': 5.5, 'rice_price': 16,
    'us_ism_manufacturing': 47, 'china_caixin_pmi': 48, 'eurozone_manufacturing_pmi': 47,
    'us_jobless_claims': 280,
    'vix': 25, 'move_bond_volatility': 120, 'ted_spread': 50, 'credit_spread': 200,
    'dxy_index': 105, 'eur_usd': 1.05, 'usd_cny': 7.2,
    'copper_price': 3.5, 'silver_price': 35,
    'baltic_dry_index': 1500, 'scfi': 3000,
    'global_terrorism_index': 6.0,
    'hormuz_strait': 'normal', 'taiwan_strait_tension': 'normal',
    'russia_ukraine_conflict': 'normal', 'middle_east_conflict': 'normal',
    'china_taiwan_tension': 'normal',
})

print(f"Composite: {result['composite']}")
print(f"Total weight: {result['total_weight']}")
print(f"Available count: {result['available_count']}")
print()

# Show per-indicator scores
for slug, details in sorted(result['indicator_details'].items(), key=lambda x: x[1]['raw_score']):
    score = details['raw_score']
    marker = '***' if score != 0.5 else ''
    print(f"  {slug:30s} raw={score:.4f}  weighted={details['weighted_score']:.4f}  w={details['weight']}  cat={details['category']} {marker}")
print()
print('Category weighted sums:', result['category_scores'])
print('Category active weights:', result['category_weights_active'])
