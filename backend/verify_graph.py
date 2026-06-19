"""Verify graph compiles correctly."""
import sys
sys.path.insert(0, '/root/crisis-monitor/backend/src')
import asyncio
from agent.graph import build_graph

async def main():
    graph = build_graph()
    nodes = list(graph.nodes.keys())
    expected = ["composite_scorer", "indicator_narrator", "dot_analyzers",
                "pathway_synthesizer", "end_state_assessor", "save_to_db"]
    for node in expected:
        assert node in nodes, f"Missing node: {node}"
    print(f"Graph OK — {len(nodes)} nodes: {nodes}")

asyncio.run(main())
