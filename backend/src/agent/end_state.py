"""End State Assessor LLM — Agent 7.

Determines the final end state (containment / fragmented stability / systemic collapse)
and answers 5 key synthesis questions.
"""
import json
from typing import Dict, Any
from src.agent.llm import call_llm_with_retry

END_STATE_PROMPT = """You are a senior crisis assessment analyst. Your job is to determine the current end state of the global crisis monitor, answer 5 key questions, and write a 3-4 paragraph intelligence briefing.

END STATES:
- Containment: Risks are being managed, no imminent crisis. Markets stable, political cohesion holding.
- Fragmented Stability: Some regions/categories are stressed but the system is holding. Patchwork of crises, no coordinated cascade.
- Systemic Collapse: Multiple crises are cascading simultaneously. Financial, geopolitical, and social systems under severe stress. Pathway D active.

DOT ANALYSES (all 9 dots):
{dots_json}

PATHWAY ASSESSMENT:
{pathways_json}

COMPOSITE SCORE: {composite}/30 ({interpretation})

FIVE KEY QUESTIONS:
1. Is this a controlled correction or the start of a structural break?
2. Which region or asset class is the proximate trigger if a cascade begins?
3. What is the probability of a coordinated global recession within 6 months?
4. Are policymakers (central banks, governments) responding adequately or are they behind the curve?
5. What single indicator would you watch most closely over the next 7 days?

INTELLIGENCE BRIEFING — write a 3-4 paragraph narrative report suitable for a non-specialist audience:
- Paragraph 1: Current state summary. What is happening right now in plain language. State the composite score, end state, and what it means for the average person.
- Paragraph 2: Key pressure points. Which dots/alerts are most concerning and why. Mention specific regions, indicators, or cascading risks. Keep it grounded — no speculation beyond what the data supports.
- Paragraph 3: Forward outlook. What to watch in the coming week/month. Which pathways are most likely to escalate or de-escalate. Include the recession probability and what it depends on.
- Paragraph 4 (optional): Policy snapshot. Whether governments and central banks appear to be handling the situation, or if there are signs they are falling behind. Only include if policy data is present in the analyses.
- Keep every paragraph to 2-4 sentences. Use plain English — no technical jargon. The audience is intelligent but not a financial expert. If data is thin, say so honestly rather than padding.

Return a JSON object with this exact structure:
{{
  "end_state": "containment|fragmented_stability|systemic_collapse",
  "confidence": 0.0-1.0,
  "headline": "2-3 sentence synthesis summarizing the current state, key pressure points, and forward outlook. Aim for 200+ characters.",
  "briefing": "3-4 paragraph narrative intelligence report in plain language. Empty string if unable to synthesize",
  "q1": {{
    "question": "Is this a controlled correction or the start of a structural break?",
    "answer": "3-4 sentence analysis",
    "verdict": "controlled_correction|transitional|structural_break"
  }},
  "q2": {{
    "question": "Which region or asset class is the proximate trigger if a cascade begins?",
    "answer": "3-4 sentence analysis",
    "trigger_region": "region/asset class name",
    "trigger_probability": 0.0-1.0
  }},
  "q3": {{
    "question": "What is the probability of a coordinated global recession within 6 months?",
    "answer": "3-4 sentence analysis",
    "probability": 0.0-1.0
  }},
  "q4": {{
    "question": "Are policymakers responding adequately or are they behind the curve?",
    "answer": "3-4 sentence analysis",
    "assessment": "ahead_of_curve|adequate|behind_curve|ineffective"
  }},
  "q5": {{
    "question": "What single indicator would you watch most closely over the next 7 days?",
    "answer": "3-4 sentence analysis",
    "indicator": "indicator name",
    "rationale": "why this indicator matters most right now"
  }}
}}

Rules:
- COMPOSITE SCORE INTERPRETATION (5-zone system, 0-30 scale):
  * normal (0-6): No crisis signals; indicators within baseline ranges; markets stable
  * monitor (6-12): Mild stress in isolated categories; worth watching but no alarm
  * elevated (12-20): Clear stress across multiple categories; pathways may be activating
  * alert (20-25): Significant stress; multiple pathways likely active; cascading risk present
  * critical (25-30): Systemic crisis; multiple pathways active simultaneously; coordinated cascade underway
- If composite >= 25: end_state MUST be "systemic_collapse"
- If composite >= 20 AND pathway_d active: end_state is "systemic_collapse"
- If composite >= 12 AND any pathway active: end_state is "fragmented_stability"
- If composite < 6 OR all pathways inactive: end_state is "containment"
- Confidence: Provide a specific score between 0.85 and 0.95 reflecting how clearly the data supports the end state. Higher = clearer zone alignment. Always return confidence >= 0.85 for a valid analysis.
- Q3 probability: tie to composite score: <6 → <0.15, 6-12 → 0.15-0.35, 12-20 → 0.35-0.60, 20+ → >0.60
- Be specific in answers — cite specific dots, indicators, and pathways
- Only use information present in the analyses provided
- briefing: write 3-4 substantive paragraphs. If the data is insufficient, return an empty string """""


async def assess_end_state(
    dot_analyses: Dict[str, Any],
    pathways: Dict[str, Any],
    composite: Dict[str, Any],
) -> Dict[str, Any]:
    """Agent 7: Determine end state and answer 5 synthesis questions."""
    prompt = END_STATE_PROMPT.format(
        dots_json=json.dumps(dot_analyses, indent=2),
        pathways_json=json.dumps(pathways, indent=2),
        composite=composite["composite"],
        interpretation=composite["interpretation"],
    )
    result, _ = await call_llm_with_retry(prompt, timeout=180)  # longer timeout for large response
    if not result:
        return _fallback_end_state(composite, pathways)
    return result


def _fallback_end_state(
    composite: Dict[str, Any],
    pathways: Dict[str, Any],
) -> Dict[str, Any]:
    """Rule-based fallback when LLM fails."""
    score = composite["composite"]
    pathway_d = pathways.get("pathway_d", {}).get("active", False)
    any_pathway = any(p.get("active", False) for k, p in pathways.items() if k.startswith("pathway_"))

    if score >= 25 or (score >= 20 and pathway_d):
        end_state = "systemic_collapse"
        confidence = 0.95
        headline = "CRITICAL: Multiple crisis pathways are active — systemic collapse underway"
    elif score >= 12 and any_pathway:
        end_state = "fragmented_stability"
        confidence = 0.90
        headline = "ELEVATED: Crisis signals detected but system holding in fragmented state"
    else:
        end_state = "containment"
        confidence = 0.85
        headline = "STABLE: Risks contained, no imminent crisis detected"

    # Strict recession probability ranges per v2 spec
    if score < 6:
        recession_prob = max(0.01, 0.15 * (score / 6))
    elif score < 12:
        recession_prob = 0.15 + 0.20 * ((score - 6) / 6)
    elif score < 20:
        recession_prob = 0.35 + 0.25 * ((score - 12) / 8)
    else:
        recession_prob = min(0.99, 0.60 + 0.40 * ((score - 20) / 10))

    # Rule-based briefing fallback: plain-language summary from composite data
    if score >= 25:
        briefing = (
            "The global crisis monitor indicates a state of systemic collapse (composite score {score}/30). "
            "Multiple crisis pathways are active simultaneously, suggesting cascading stress across financial, geopolitical, and social systems. "
            "Markets are under severe pressure and coordinated global action appears insufficient. "
            "In the coming week, watch for further deterioration in credit spreads, emerging market currencies, and geopolitical flashpoints. "
            "The estimated probability of a coordinated global recession within six months is {recession:.0%}. "
            "Policymakers currently appear to be behind the curve and may struggle to contain the cascading risks without coordinated intervention."
        ).format(score=score, recession=recession_prob)
    elif score >= 20:
        briefing = (
            "The crisis monitor shows elevated stress (composite score {score}/30) with fragmented stability across regions. "
            "Several crisis dots are active, indicating real pressure points, but no full cascade has formed yet. "
            "Key areas of concern include active pathway signals and stressed indicators in financial and geopolitical categories. "
            "Over the next week, monitor whether these pressure points begin to interlock — that would be the clearest warning of escalation. "
            "The current recession probability estimate is {recession:.0%}, contingent on whether active pathways intensify or de-escalate."
        ).format(score=score, recession=recession_prob)
    elif score >= 12:
        briefing = (
            "The global risk picture shows moderate stress (composite score {score}/30). "
            "Some indicators are flashing warning signals, but the overall system remains in a fragmented stability state — stress is present but contained within specific regions or asset classes. "
            "No coordinated cascade is evident, and most pathways remain inactive. "
            "In the coming week, watch the most active dots for signs of escalation; if they stabilize, the outlook improves. "
            "Recession probability is estimated at {recession:.0%}, reflecting the elevated but not critical risk level."
        ).format(score=score, recession=recession_prob)
    else:
        briefing = (
            "The global crisis monitor shows a contained situation (composite score {score}/30). "
            "Most indicators are within normal ranges and no crisis pathways are active. "
            "Markets appear stable and political cohesion is holding. "
            "While isolated risks always exist, the current data does not point to any imminent crisis. "
            "The estimated probability of a coordinated global recession within six months is low at {recession:.0%}. "
            "Policymakers appear to be adequately positioned for current conditions."
        ).format(score=score, recession=recession_prob)

    return {
        "end_state": end_state,
        "confidence": confidence,
        "headline": headline,
        "briefing": briefing,
        "q1": {
            "question": "Is this a controlled correction or the start of a structural break?",
            "answer": f"With composite score {score}/30, this represents a {'contained situation' if score < 6 else 'potential structural shift'}. Monitor key indicators for confirmation.",
            "verdict": "controlled_correction" if score < 6 else ("transitional" if score < 20 else "structural_break"),
        },
        "q2": {
            "question": "Which region or asset class is the proximate trigger if a cascade begins?",
            "answer": "Analysis unavailable — using composite heuristic.",
            "trigger_region": "Multiple regions" if score >= 20 else "None identified",
            "trigger_probability": min(score / 30, 0.9),
        },
        "q3": {
            "question": "What is the probability of a coordinated global recession within 6 months?",
            "answer": f"Based on composite score {score}/30, recession probability estimated at {recession_prob:.0%}.",
            "probability": recession_prob,
        },
        "q4": {
            "question": "Are policymakers responding adequately or are they behind the curve?",
            "answer": "Analysis unavailable — using composite heuristic.",
            "assessment": "adequate" if score < 12 else ("behind_curve" if score < 25 else "ineffective"),
        },
        "q5": {
            "question": "What single indicator would you watch most closely over the next 7 days?",
            "answer": "Analysis unavailable — using composite heuristic. Watch the fastest-moving financial indicators: VIX, credit spreads, and EM currencies.",
            "indicator": "VIX" if score < 20 else "Credit Spread",
            "rationale": "VIX is the fastest-reacting fear gauge; credit spreads signal systemic stress.",
        },
    }


# Self-check
if __name__ == "__main__":
    fb = _fallback_end_state(
        {"composite": 3, "interpretation": "normal"},
        {"pathway_d": {"active": False}},
    )
    assert fb["end_state"] == "containment"
    assert fb["q3"]["probability"] < 0.15
    assert "briefing" in fb, "Missing briefing in fallback"
    assert len(fb["briefing"]) > 50, "Briefing too short"
    assert fb["confidence"] == 0.85

    # Test fragmented stability boundary
    fb = _fallback_end_state(
        {"composite": 15, "interpretation": "elevated"},
        {"pathway_a": {"active": True}},
    )
    assert fb["end_state"] == "fragmented_stability"
    assert 0.35 <= fb["q3"]["probability"] <= 0.60
    assert fb["confidence"] == 0.90
    
    # Test containment due to no pathways (even if score >= 12)
    fb = _fallback_end_state(
        {"composite": 15, "interpretation": "elevated"},
        {"pathway_a": {"active": False}},
    )
    assert fb["end_state"] == "containment"
    assert 0.35 <= fb["q3"]["probability"] <= 0.60  # Probability still scales with score

    fb = _fallback_end_state(
        {"composite": 26, "interpretation": "critical"},
        {"pathway_d": {"active": True}},
    )
    assert fb["end_state"] == "systemic_collapse"
    assert fb["q3"]["probability"] > 0.60
    assert fb["confidence"] == 0.95
    assert "collapse" in fb["briefing"].lower(), "Crisis briefing should mention collapse"
    print("end_state fallback OK")
