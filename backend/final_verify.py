"""Final verification: hit the live API and check indicator fields."""
import urllib.request
import json

resp = urllib.request.urlopen('http://localhost:8001/api/dashboard')
data = json.loads(resp.read())
indicators = data.get('indicators', [])

print(f"Total indicators: {len(indicators)}")
assert len(indicators) > 0, "NO INDICATORS!"

# Check required fields
for ind in indicators:
    assert ind.get('name'), f"Missing name: {ind}"
    assert 'value' in ind, f"Missing value: {ind}"
    assert ind.get('status'), f"Missing status: {ind}"
    assert ind.get('category') is not None, f"Missing category: {ind}"

# Show status distribution
from collections import Counter
status_counts = Counter(ind['status'] for ind in indicators)
print(f"Status distribution: {dict(status_counts)}")

# Show first 5
print("\nFirst 5 indicators:")
for ind in indicators[:5]:
    print(f"  {ind['name']}: {ind['value']} {ind.get('unit','')} [{ind['status']}] — {ind['category']}")

print("\nAll checks passed — indicators array populated with all required fields.")
