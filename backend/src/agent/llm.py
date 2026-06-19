"""LLM helper — OpenCode Go via langchain-openai."""
import os
import json
import re
from langchain_openai import ChatOpenAI


def get_llm(temperature: float = 0.3, timeout: int = 120) -> ChatOpenAI:
    """Return ChatOpenAI pointed at OpenCode Go."""
    api_key = os.environ.get("OPENCODE_GO_API_KEY", "")
    return ChatOpenAI(
        model="deepseek-v4-pro",
        base_url="https://opencode.ai/zen/go/v1",
        api_key=api_key,
        temperature=temperature,
        timeout=timeout,
    )


def extract_json(text: str) -> dict:
    """
    Extract JSON from LLM output. Tries fenced block first, then raw parse.
    Returns empty dict on failure — caller handles graceful degradation.
    """
    # Try ```json fence
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try raw JSON — find first { or [ boundary
    for boundary in (r"\{.*\}", r"\[.*\]"):
        m = re.search(boundary, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}
