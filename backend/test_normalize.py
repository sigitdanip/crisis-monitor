import logging
from src.agent.normalize import fetch_and_normalize
from src.agent.composite_scorer_v2 import _resolve_slug, INDICATOR_REGISTRY

logging.basicConfig(level=logging.INFO)

def main():
    print("--- Fetching and Normalizing ---")
    indicators, news = fetch_and_normalize()
    
    print("\n--- Normalized Indicators Map ---")
    for k, v in sorted(indicators.items()):
        resolved = _resolve_slug(k)
        print(f"Key: {k:<30} | Value: {str(v):<15} | Resolved Slug: {str(resolved):<25}")
        
    print("\n--- Registry Slugs not present in Normalized Indicators ---")
    present_slugs = {str(_resolve_slug(k)) for k in indicators.keys()}
    for slug in sorted(INDICATOR_REGISTRY.keys()):
        if slug not in present_slugs:
            print(f"Missing from Normalized Map: {slug}")

if __name__ == "__main__":
    main()
