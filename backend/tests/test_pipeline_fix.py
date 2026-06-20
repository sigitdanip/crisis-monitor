#!/usr/bin/env python3
"""Direct pipeline test — verify all 5 dot analyzers use mimo-v2.5 and produce results.

Runs the full crisis monitor pipeline with test data and reports per-agent timing
and status. Exits non-zero if any agent falls back or times out.
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, '/root/crisis-monitor/backend')

from src.agent.graph import run_pipeline

# Test indicators — realistic values that should produce meaningful analysis
TEST_INDICATORS = {
    "brent_price": 82.50,
    "wti_price": 78.20,
    "natgas_price": 3.45,
    "dxy": 104.2,
    "gold_price": 3050.0,
    "us_10y": 4.42,
    "us_2y": 4.28,
    "vix": 18.2,
    "ig_oas": 142,
    "hy_oas": 420,
    "fao_monthly_change_pct": 3.2,
    "cme_grains_monthly_pct": 1.8,
    "caixin_pmi": 50.1,
    "btp_bund_spread": 145,
    "eu_gas_storage_pct": 58.3,
    "us_spr_mbbl": 368,
    "idr_breach": 0,
    "try_breach": 0,
    "egp_breach": 0,
    "nato_fracture": 1,
    "us_nato_withdrawal": 0,
    "cds_doubling": 0,
    "protest_countries": 2,
    "govt_crisis": 0,
    "china_property_default": 0,
    "hormuz_closure": "",
}

# News headlines
TEST_NEWS = [
    {"title": "NATO leaders reaffirm Article 5 commitment amid rising tensions", "source": "Reuters"},
    {"title": "Brent crude holds steady at $82 as OPEC+ maintains output cuts", "source": "Bloomberg"},
    {"title": "China Caixin PMI at 50.1 — barely above contraction threshold", "source": "Reuters"},
]

async def main():
    print("=" * 60)
    print("Pipeline Test — verifying LLM timeout fix")
    print("=" * 60)
    
    # Verify env vars
    model = os.environ.get("LLM_MODEL", "mimo-v2.5")
    api_key = os.environ.get("OPENCODE_GO_API_KEY", "")
    print(f"LLM_MODEL env: {model}")
    print(f"OPENCODE_GO_API_KEY: {'SET' if api_key else 'MISSING'}")
    print()
    
    # Verify the LLM client picks up the env var
    from src.agent.llm import get_llm
    llm = get_llm()
    print(f"get_llm() model: {llm.model_name}")
    if llm.model_name == "deepseek-v4-pro":
        print("FAIL: model is still hardcoded to deepseek-v4-pro")
        sys.exit(1)
    if llm.model_name != model:
        print(f"WARN: model mismatch — env says {model}, llm says {llm.model_name}")
    print()
    
    print("Starting pipeline with test data...")
    t0 = time.time()
    
    try:
        result = await run_pipeline(TEST_INDICATORS, TEST_NEWS)
    except Exception as e:
        print(f"Pipeline crashed: {e}")
        sys.exit(1)
    
    elapsed = time.time() - t0
    
    # Report timing
    print(f"\nPipeline completed in {result.get('total_duration_ms', 0):.0f}ms ({elapsed:.1f}s wall)")
    print(f"Success count: {result.get('success_count', 0)}")
    
    # Check agent nodes
    agent_nodes = []
    for timing in result.get("node_timing", []):
        label = timing.get("label", "")
        status = timing.get("status", "")
        dur = timing.get("duration_ms", 0)
        agent_type = timing.get("type", "")
        
        if agent_type == "agent" and "Agent" in label and "parallel" not in label.lower():
            agent_nodes.append(timing)
            marker = "PASS" if status == "success" else "FAIL"
            print(f"  [{marker}] {label}: status={status}, duration={dur}ms")
        elif "Dot Analyzers (parallel)" in label:
            print(f"  [INFO] {label}: duration={dur}ms")
    
    # Summary
    print(f"\n{'-' * 60}")
    fallbacks = [a for a in agent_nodes if a.get("status") == "fallback"]
    errors = [a for a in agent_nodes if a.get("status") == "error"]
    success = [a for a in agent_nodes if a.get("status") == "success"]
    
    print(f"Agent results: {len(success)} success, {len(fallbacks)} fallback, {len(errors)} error")
    
    if fallbacks:
        print("\nFAIL: Agents falling back:")
        for f in fallbacks:
            print(f"  - {f['label']}: {f.get('error', 'no error')}")
        sys.exit(1)
    
    if errors:
        print("\nFAIL: Agents with errors:")
        for e in errors:
            print(f"  - {e['label']}: {e.get('error', 'no error')}")
        sys.exit(1)
    
    if not success:
        print("\nFAIL: No agents succeeded")
        sys.exit(1)
    
    # Verify AC criteria
    composite = result.get("composite_score", {})
    end_state = result.get("end_state", {})
    
    checks = []
    checks.append(("model uses mimo-v2.5", llm.model_name == "mimo-v2.5"))
    
    # Check for "LLM analysis unavailable" in dot summaries
    dots = result.get("dot_analyses", {})
    for dot_key, dot_data in dots.items():
        if isinstance(dot_data, dict) and dot_data.get("summary", "").startswith("LLM analysis unavailable"):
            checks.append((f"{dot_key} not using fallback text", False))
    
    if len(checks) == 1:  # only the model check
        checks.append(("no fallback text in dot summaries", True))
    
    checks.append(("pipeline < 90s", elapsed < 90))
    checks.append(("confidence >= 0.85", end_state.get("confidence", 0) >= 0.85))
    checks.append(("composite_score != 1", composite.get("composite", 0) != 1))
    
    # Check synthesis length (headline)
    headline = end_state.get("headline", "")
    checks.append((f"synthesis headline length >= 200 chars (got {len(headline)})", len(headline) >= 200))
    
    print("\nAcceptance Criteria:")
    all_pass = True
    for check_name, passed in checks:
        marker = "PASS" if passed else "FAIL"
        print(f"  [{marker}] {check_name}")
        if not passed:
            all_pass = False
    
    print(f"\n{'=' * 60}")
    if all_pass:
        print("ALL CHECKS PASSED — fix verified")
    else:
        print("SOME CHECKS FAILED — review above")
    print(f"{'=' * 60}")
    
    sys.exit(0 if all_pass else 1)

if __name__ == "__main__":
    asyncio.run(main())
