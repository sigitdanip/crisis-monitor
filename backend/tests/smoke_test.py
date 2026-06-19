"""Quick smoke test for imports."""
from src.routes import router
from src.agent.graph import build_graph
from src.agent.indicator_narrator import INDICATOR_META, DOT_INDICATORS, sources_list_for_dot

print(f"Routes OK — {len(router.routes)} routes")
graph = build_graph()
print(f"Graph OK — {len(graph.nodes)} nodes")
print(f"Indicators with source metadata: {sum(1 for m in INDICATOR_META.values() if 'source' in m)}/{len(INDICATOR_META)}")
print(f"DOT_INDICATORS entries: {len(DOT_INDICATORS)}")
print("All imports clean")
