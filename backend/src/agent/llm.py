"""LLM helper — OpenCode Go via langchain-openai."""
import os
import json
import re
from langchain_openai import ChatOpenAI


def get_llm(temperature: float = 0.3, timeout: int = 25) -> ChatOpenAI:
    """Return ChatOpenAI pointed at OpenCode Go."""
    api_key = os.environ.get("OPENCODE_GO_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "mimo-v2.5")
    return ChatOpenAI(
        model=model,
        base_url="https://opencode.ai/zen/go/v1",
        api_key=api_key,
        temperature=temperature,
        timeout=timeout,
    )


def get_llm_content(resp) -> str:
    """Extract content from LLM response, with reasoning_content fallback.

    OpenCode Go reasoning models may return content in reasoning_content
    instead of content. This defensive wrapper tries content first, then
    falls back to reasoning_content from additional_kwargs.
    """
    content = getattr(resp, "content", "") or ""
    if not content:
        reasoning = getattr(resp, "additional_kwargs", {}) or {}
        content = reasoning.get("reasoning_content", "")
    return content or ""


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
    # Try JSONDecoder.raw_decode — finds first complete JSON object even with
    # surrounding text (more robust than greedy regex when LLM includes curly
    # braces in narrative text before/after the JSON).  Iterates over every
    # '{' / '[' start position in case earlier ones are not valid JSON.
    for start_char in ('{', '['):
        idx = 0
        while True:
            idx = text.find(start_char, idx)
            if idx < 0:
                break
            try:
                decoder = json.JSONDecoder()
                obj, _ = decoder.raw_decode(text[idx:])
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass
            idx += 1
    return {}
