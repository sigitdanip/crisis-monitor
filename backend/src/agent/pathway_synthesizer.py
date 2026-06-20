"""Pathway Synthesizer LLM — Agent 6.

Connects all 9 dot analyses + composite score → determines which
pathways (A/B/C/D) are active.
"""
import json
from typing import Dict, Any
from src.agent.llm import get_llm, extract_json, get_llm_content

SYNTHESIZER_PROMPT = """You are a crisis pathway synthesis analyst. Your job is to connect the dots across all 9 crisis indicators and determine which of 4 escalation pathways are active.

PATHWAY DEFINITIONS:
- Pathway A (Monetary Cascade): Credit tightening → liquidity crisis → sovereign stress → global recession
- Pathway B (Energy Price Shock): Energy supply disruption → price spikes → food costs surge → social unrest → government crises
- Pathway C (Geopolitical Fracture): Alliance breakdowns → trade fragmentation → capital flight → regional crisis → global spillover
- Pathway D (Systemic Collapse): Multiple pathways A+B+C activating simultaneously → coordinated crisis

DOT ANALYSES:
{dots_json}

COMPOSITE SCORE: {composite}/16 ({interpretation})

Based on ALL the dot analyses above, determine which pathways are active.

Return a JSON object with this exact structure:
{{
  "pathway_a": {{
    "name": "Monetary Cascade",
    "description": "Credit tightening → liquidity crisis → sovereign stress → global recession. Tracks whether tightening financial conditions, rising borrowing costs, and sovereign debt pressures are converging into a coordinated monetary crisis.",
    "active": true/false,
    "fading": true/false,
    "narrative": "1-2 sentence explanation why this pathway is active or not",
    "triggered_by": ["dot_4", "dot_5"],
    "confidence": 0.0-1.0
  }},
  "pathway_b": {{
    "name": "Energy Price Shock",
    "description": "Energy supply disruption → price spikes → food costs surge → social unrest → government crises. Tracks whether energy market shocks, supply constraints, and commodity price spikes are cascading into food insecurity and political instability.",
    "active": true/false,
    "fading": true/false,
    "narrative": "1-2 sentence explanation",
    "triggered_by": ["dot_1", "dot_2", "dot_3"],
    "confidence": 0.0-1.0
  }},
  "pathway_c": {{
    "name": "Geopolitical Fracture",
    "description": "Alliance breakdowns → trade fragmentation → capital flight → regional crisis → global spillover. Tracks whether geopolitical tensions, broken alliances, and trade disruptions are fracturing international cooperation and triggering cross-border economic contagion.",
    "active": true/false,
    "fading": true/false,
    "narrative": "1-2 sentence explanation",
    "triggered_by": ["dot_6", "dot_4"],
    "confidence": 0.0-1.0
  }},
  "pathway_d": {{
    "name": "Systemic Collapse",
    "description": "Multiple pathways A+B+C activating simultaneously → coordinated crisis. Activates only when multiple other pathways are active simultaneously, indicating a systemic breakdown rather than isolated stress.",
    "active": true/false,
    "fading": true/false,
    "narrative": "1-2 sentence explanation",
    "triggered_by": ["all"],
    "confidence": 0.0-1.0
  }},
  "overall_assessment": "1-2 sentence synthesis of the overall crisis picture",
  "dominant_pathway": "A|B|C|D|none"
}}

Rules:
- "active": true if the dot analyses show clear signals for this pathway
- "fading": true if signals were recently active but are weakening
- "triggered_by": list the dot numbers that are driving this pathway
- Pathway D can only be active if at least 2 of A/B/C are active
- Confidence should reflect how strongly the data supports the pathway
- Only use information present in the dot analyses provided"""


async def synthesize_pathways(
    dot_analyses: Dict[str, Any],
    composite: Dict[str, Any],
) -> Dict[str, Any]:
    """Agent 6: Connect all dots into pathway assessment."""
    llm = get_llm(temperature=0.3)
    prompt = SYNTHESIZER_PROMPT.format(
        dots_json=json.dumps(dot_analyses, indent=2),
        composite=composite["composite"],
        interpretation=composite["interpretation"],
    )
    resp = await llm.ainvoke(prompt)
    result = extract_json(get_llm_content(resp))
    if not result:
        return _fallback_pathways(composite)
    return result


def _fallback_pathways(composite: Dict[str, Any]) -> Dict[str, Any]:
    """Safe fallback pathway assessment when LLM fails."""
    score = composite["composite"]
    # Simple heuristic: more composite score = more pathways active
    pathway_d_active = score >= 13
    pathway_a_active = score >= 9 or pathway_d_active
    pathway_b_active = score >= 9 or pathway_d_active
    pathway_c_active = score >= 9 or pathway_d_active

    def make_pathway(active: bool, fading: bool, dots: list, confidence: float,
                     name: str, description: str):
        return {
            "name": name,
            "description": description,
            "active": active,
            "fading": fading,
            "narrative": f"Pathway assessed via composite heuristic (score {score})",
            "triggered_by": dots,
            "confidence": confidence,
        }

    return {
        "pathway_a": make_pathway(pathway_a_active, False, ["dot_4", "dot_5"], 0.5,
            "Monetary Cascade",
            "Credit tightening → liquidity crisis → sovereign stress → global recession. Tracks whether tightening financial conditions, rising borrowing costs, and sovereign debt pressures are converging into a coordinated monetary crisis."),
        "pathway_b": make_pathway(pathway_b_active, False, ["dot_1", "dot_2", "dot_3"], 0.5,
            "Energy Price Shock",
            "Energy supply disruption → price spikes → food costs surge → social unrest → government crises. Tracks whether energy market shocks, supply constraints, and commodity price spikes are cascading into food insecurity and political instability."),
        "pathway_c": make_pathway(pathway_c_active, False, ["dot_6", "dot_4"], 0.5,
            "Geopolitical Fracture",
            "Alliance breakdowns → trade fragmentation → capital flight → regional crisis → global spillover. Tracks whether geopolitical tensions, broken alliances, and trade disruptions are fracturing international cooperation and triggering cross-border economic contagion."),
        "pathway_d": make_pathway(pathway_d_active, False, ["all"], 0.5,
            "Systemic Collapse",
            "Multiple pathways A+B+C activating simultaneously → coordinated crisis. Activates only when multiple other pathways are active simultaneously, indicating a systemic breakdown rather than isolated stress."),
        "overall_assessment": f"Fallback assessment: composite score {score}/16 ({composite['interpretation']})",
        "dominant_pathway": "D" if pathway_d_active else ("A" if pathway_a_active else "none"),
    }


# Self-check
if __name__ == "__main__":
    fb = _fallback_pathways({"composite": 2, "interpretation": "monitor"})
    assert fb["pathway_a"]["active"] is False
    assert fb["pathway_b"]["active"] is False
    assert fb["dominant_pathway"] == "none"
    # Verify name and description fields on all pathways
    for key in ("pathway_a", "pathway_b", "pathway_c", "pathway_d"):
        assert "name" in fb[key], f"{key} missing name"
        assert "description" in fb[key], f"{key} missing description"
        assert isinstance(fb[key]["name"], str) and len(fb[key]["name"]) > 0

    fb = _fallback_pathways({"composite": 14, "interpretation": "crisis"})
    assert fb["pathway_d"]["active"] is True
    assert fb["dominant_pathway"] == "D"
    assert fb["pathway_d"]["name"] == "Systemic Collapse"
    print("pathway_synthesizer fallback OK")
