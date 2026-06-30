"""Pathway Synthesizer LLM — Agent 6.

Connects all 9 dot analyses + composite score + coupling matrix → determines which
pathways (A/B/C/D) are active.
"""
import json
from typing import Dict, Any, List
from src.agent.llm import call_llm_with_retry

# v2 Coupling Matrix: deterministic pathway activation amplifiers
COUPLING_MATRIX = {
    ("energy", "food"): 0.12,
    ("financial", "currency"): 0.10,
    ("geopolitical", "supply_chain"): 0.12,
    ("geopolitical", "energy"): 0.10,
    ("energy", "economic"): 0.08,
}
COUPLING_CAP = 0.15

SYNTHESIZER_PROMPT = """You are a crisis pathway synthesis analyst. Your job is to connect the dots across all 9 crisis indicators and determine which of 4 escalation pathways are active.

PATHWAY DEFINITIONS:
- Pathway A (Monetary Cascade): Credit tightening → liquidity crisis → sovereign stress → global recession
- Pathway B (Energy Price Shock): Energy supply disruption → price spikes → food costs surge → social unrest → government crises
- Pathway C (Geopolitical Fracture): Alliance breakdowns → trade fragmentation → capital flight → regional crisis → global spillover
- Pathway D (Systemic Collapse): Multiple pathways A+B+C activating simultaneously → coordinated crisis

DOT ANALYSES:
{dots_json}

COMPOSITE SCORE: {composite}/30 ({interpretation})

CATEGORY SCORES & COUPLING ACTIVATION:
{category_scores}

Based on ALL the dot analyses and category scores above, determine which pathways are active.

Return a JSON object with this exact structure:
{{
  "pathway_a": {{
    "name": "Monetary Cascade",
    "description": "Credit tightening → liquidity crisis → sovereign stress → global recession. Tracks whether tightening financial conditions, rising borrowing costs, and sovereign debt pressures are converging into a coordinated monetary crisis.",
    "active": true/false,
    "fading": true/false,
    "narrative": "1-2 sentence explanation why this pathway is active or not",
    "triggered_by": ["dot_4", "dot_5"],
    "confidence": 0.0-1.0,
    "activation_metric": float
  }},
  "pathway_b": {{
    "name": "Energy Price Shock",
    "description": "Energy supply disruption → price spikes → food costs surge → social unrest → government crises. Tracks whether energy market shocks, supply constraints, and commodity price spikes are cascading into food insecurity and political instability.",
    "active": true/false,
    "fading": true/false,
    "narrative": "1-2 sentence explanation",
    "triggered_by": ["dot_1", "dot_2", "dot_3"],
    "confidence": 0.0-1.0,
    "activation_metric": float
  }},
  "pathway_c": {{
    "name": "Geopolitical Fracture",
    "description": "Alliance breakdowns → trade fragmentation → capital flight → regional crisis → global spillover. Tracks whether geopolitical tensions, broken alliances, and trade disruptions are fracturing international cooperation and triggering cross-border economic contagion.",
    "active": true/false,
    "fading": true/false,
    "narrative": "1-2 sentence explanation",
    "triggered_by": ["dot_6", "dot_4"],
    "confidence": 0.0-1.0,
    "activation_metric": float
  }},
  "pathway_d": {{
    "name": "Systemic Collapse",
    "description": "Multiple pathways A+B+C activating simultaneously → coordinated crisis. Activates only when multiple other pathways are active simultaneously, indicating a systemic breakdown rather than isolated stress.",
    "active": true/false,
    "fading": true/false,
    "narrative": "1-2 sentence explanation",
    "triggered_by": ["all"],
    "confidence": 0.0-1.0,
    "activation_metric": float
  }},
  "overall_assessment": "1-2 sentence synthesis of the overall crisis picture",
  "dominant_pathway": "A|B|C|D|none"
}}

Rules:
- "active": true if the dot analyses and category scores show clear signals for this pathway
- "fading": true if signals were recently active but are weakening
- "triggered_by": list the dot numbers that are driving this pathway
- Pathway D MUST ONLY be active if at least 2 of A/B/C are active (v2 spec §5.3)
- Confidence should reflect how strongly the data supports the pathway
- Use the activation metrics derived from the coupling matrix to inform your assessment"""


def compute_pathway_activation(category_rss_scores: Dict[str, float], pathway_categories: List[str]) -> float:
    """Compute deterministic pathway activation using base scores and coupling matrix."""
    # Base activation = Σ Scat,i (for categories in this pathway)
    base_activation = sum(category_rss_scores.get(cat, 0.0) for cat in pathway_categories)
    
    # Coupling bonus = Σ M_{i,j} × Scat,j (incoming cross-domain spillovers)
    coupling_bonus = 0.0
    for (src, target), weight in COUPLING_MATRIX.items():
        if target in pathway_categories:
            coupling_bonus += weight * category_rss_scores.get(src, 0.0)
            
    # Cap the coupling bonus at 0.15 per v2 spec
    coupling_bonus = min(coupling_bonus, COUPLING_CAP)
    return round(base_activation + coupling_bonus, 4)


async def synthesize_pathways(
    dot_analyses: Dict[str, Any],
    composite: Dict[str, Any],
) -> Dict[str, Any]:
    """Agent 6: Connect all dots into pathway assessment."""
    cat_rss = composite.get("category_rss_scores", {})
    
    # Pre-compute deterministic activations for context
    activations = {
        "A": compute_pathway_activation(cat_rss, ["financial", "currency", "economic"]),
        "B": compute_pathway_activation(cat_rss, ["energy", "food", "economic"]),
        "C": compute_pathway_activation(cat_rss, ["geopolitical", "supply_chain", "currency"])
    }
    
    cat_scores_text = json.dumps(cat_rss, indent=2) + "\n\nPathway Base Activations:\n" + json.dumps(activations, indent=2)

    prompt = SYNTHESIZER_PROMPT.format(
        dots_json=json.dumps(dot_analyses, indent=2),
        composite=composite["composite"],
        interpretation=composite["interpretation"],
        category_scores=cat_scores_text,
    )
    result, _ = await call_llm_with_retry(prompt)
    if not result:
        return _fallback_pathways(composite)
        
    # Enforce Pathway D ≥ 2 rule on LLM output
    active_abc = sum(1 for p in ["pathway_a", "pathway_b", "pathway_c"] if result.get(p, {}).get("active"))
    if active_abc < 2 and result.get("pathway_d", {}).get("active"):
        result["pathway_d"]["active"] = False
        result["pathway_d"]["narrative"] = "Overridden: Pathway D requires ≥2 base pathways to be active."
        if result["dominant_pathway"] == "D":
            result["dominant_pathway"] = "none"

    return result


def _fallback_pathways(composite: Dict[str, Any]) -> Dict[str, Any]:
    """Safe fallback pathway assessment using v2 deterministic heuristics."""
    score = composite["composite"]
    cat_rss = composite.get("category_rss_scores", {})
    
    act_a = compute_pathway_activation(cat_rss, ["financial", "currency", "economic"])
    act_b = compute_pathway_activation(cat_rss, ["energy", "food", "economic"])
    act_c = compute_pathway_activation(cat_rss, ["geopolitical", "supply_chain", "currency"])
    
    # Pathway D heuristic: C ≥ 20
    pathway_d_active = score >= 20.0
    
    # Pathway A/B/C heuristic: C ≥ 12 OR D OR high specific activation
    # We use a base threshold of 1.2 for pathway activation if score < 12
    pathway_a_active = score >= 12.0 or pathway_d_active or act_a >= 1.2
    pathway_b_active = score >= 12.0 or pathway_d_active or act_b >= 1.2
    pathway_c_active = score >= 12.0 or pathway_d_active or act_c >= 1.2

    # Enforce Pathway D rule: D only if ≥2 of A,B,C active (v2 spec §5.3)
    active_abc = sum([pathway_a_active, pathway_b_active, pathway_c_active])
    if pathway_d_active and active_abc < 2:
        pathway_d_active = False

    def make_pathway(active: bool, fading: bool, dots: list, confidence: float,
                     name: str, description: str, act_metric: float = 0.0):
        return {
            "name": name,
            "description": description,
            "active": active,
            "fading": fading,
            "narrative": f"Pathway assessed via composite heuristic (score {score}) with activation {act_metric}",
            "triggered_by": dots,
            "confidence": confidence,
            "activation_metric": act_metric
        }

    return {
        "pathway_a": make_pathway(pathway_a_active, False, ["dot_4", "dot_5"], 0.5,
            "Monetary Cascade",
            "Credit tightening → liquidity crisis → sovereign stress → global recession. Tracks whether tightening financial conditions, rising borrowing costs, and sovereign debt pressures are converging into a coordinated monetary crisis.", act_a),
        "pathway_b": make_pathway(pathway_b_active, False, ["dot_1", "dot_2", "dot_3"], 0.5,
            "Energy Price Shock",
            "Energy supply disruption → price spikes → food costs surge → social unrest → government crises. Tracks whether energy market shocks, supply constraints, and commodity price spikes are cascading into food insecurity and political instability.", act_b),
        "pathway_c": make_pathway(pathway_c_active, False, ["dot_6", "dot_4"], 0.5,
            "Geopolitical Fracture",
            "Alliance breakdowns → trade fragmentation → capital flight → regional crisis → global spillover. Tracks whether geopolitical tensions, broken alliances, and trade disruptions are fracturing international cooperation and triggering cross-border economic contagion.", act_c),
        "pathway_d": make_pathway(pathway_d_active, False, ["all"], 0.5,
            "Systemic Collapse",
            "Multiple pathways A+B+C activating simultaneously → coordinated crisis. Activates only when multiple other pathways are active simultaneously, indicating a systemic breakdown rather than isolated stress.", round(act_a + act_b + act_c, 4)),
        "overall_assessment": f"Fallback assessment: composite score {score}/30 ({composite['interpretation']})",
        "dominant_pathway": "D" if pathway_d_active else ("A" if pathway_a_active else "none"),
    }


# Self-check
if __name__ == "__main__":
    # Test fallback with low score
    fb = _fallback_pathways({"composite": 2, "interpretation": "normal", "category_rss_scores": {}})
    assert fb["pathway_a"]["active"] is False
    assert fb["pathway_b"]["active"] is False
    assert fb["dominant_pathway"] == "none"
    
    # Verify name and description fields on all pathways
    for key in ("pathway_a", "pathway_b", "pathway_c", "pathway_d"):
        assert "name" in fb[key], f"{key} missing name"
        assert "description" in fb[key], f"{key} missing description"
        assert isinstance(fb[key]["name"], str) and len(fb[key]["name"]) > 0

    # Test fallback with critical score
    fb = _fallback_pathways({"composite": 26, "interpretation": "critical", "category_rss_scores": {
        "financial": 1.0, "currency": 1.0, "energy": 1.0, "food": 1.0
    }})
    assert fb["pathway_d"]["active"] is True
    assert fb["dominant_pathway"] == "D"
    assert fb["pathway_d"]["name"] == "Systemic Collapse"
    
    # Test pathway D override rule (score is 26, but only 1 pathway active)
    fb2 = _fallback_pathways({"composite": 26, "interpretation": "critical", "category_rss_scores": {
        "energy": 1.5, "food": 1.5  # Only Pathway B active via activation metrics
    }})
    # Since C=26, the heuristic turns on A, B, and C anyway (score >= 12)
    assert fb2["pathway_a"]["active"] is True  # Due to score heuristic
    assert fb2["pathway_d"]["active"] is True  # Active because ≥2 are active
    
    print("pathway_synthesizer fallback and v2 logic OK")
