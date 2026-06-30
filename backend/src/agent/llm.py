"""LLM helper — OpenCode Go via langchain-openai."""
import asyncio
import json
import logging
import os
import re
import threading
from typing import Any

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

# ── Token cost tracking ────────────────────────────────────────────────
# Module-level counters and lock for thread-safe accumulation.

_token_cost_lock = threading.Lock()
_total_tokens: int = 0
_total_cost_estimate: float = 0.0

MODEL_COST_PER_1K: dict[str, float] = {
    "mimo-v2.5": 0.0015,
    "gpt-4o": 0.005,
    "gpt-4o-mini": 0.0006,
    "claude-sonnet-4": 0.003,
    "deepseek-v4-pro": 0.002,
}


def _estimate_cost(token_count: int, model: str) -> float:
    """Estimate cost for a given token count and model name."""
    rate = MODEL_COST_PER_1K.get(model, 0.002)
    return (token_count / 1000) * rate


def track_token_usage(token_count: int, model: str = "") -> None:
    """Accumulate token usage into module-level counters (thread-safe)."""
    global _total_tokens, _total_cost_estimate
    model = model or os.environ.get("LLM_MODEL", "mimo-v2.5")
    cost = _estimate_cost(token_count, model)
    with _token_cost_lock:
        _total_tokens += token_count
        _total_cost_estimate += cost


def get_token_cost() -> dict[str, Any]:
    """Return cumulative token usage and cost estimate."""
    with _token_cost_lock:
        return {
            "total_tokens": _total_tokens,
            "total_cost_estimate": round(_total_cost_estimate, 6),
        }


def reset_token_cost() -> None:
    """Reset cumulative token counters to zero."""
    global _total_tokens, _total_cost_estimate
    with _token_cost_lock:
        _total_tokens = 0
        _total_cost_estimate = 0.0


def get_llm(temperature: float = 0.3, timeout: int = 60) -> ChatOpenAI:
    """Return ChatOpenAI pointed at OpenCode Go."""
    api_key = os.environ.get("OPENCODE_GO_API_KEY", "")
    # For test inspection: deepseek-v4-pro
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
    """Extract JSON from LLM output. Returns empty dict on failure."""
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    for start_char in ('{', '['):
        idx = 0
        while True:
            idx = text.find(start_char, idx)
            if idx < 0:
                break
            try:
                decoder = json.JSONDecoder()
                obj, _ = decoder.raw_decode(text[idx:])
                if isinstance(obj, (dict, list)):
                    return obj
            except json.JSONDecodeError:
                pass
            idx += 1
    return {}


async def call_llm_with_retry(
    prompt: str,
    max_attempts: int = 3,
    timeout: int = 60,
    base_delay: float = 3.0,
    temperature: float = 0.3,
) -> tuple[dict[str, Any], int]:
    """Call the LLM with retry on transient failures.

    Retry strategy (exponential backoff):
      attempt 1 fails → wait base_delay * 1 = 3s
      attempt 2 fails → wait base_delay * 2 = 6s
      attempt 3 fails → raise

    Combined with the staggered semaphore in graph.py this eliminates
    HTTP 429 rate-limit fallbacks from provider bursts.
    """
    last_exception: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            llm = get_llm(temperature=temperature, timeout=timeout)
            resp = await llm.ainvoke(prompt)
            content = get_llm_content(resp)
            # Track token usage (estimate)
            estimated_tokens = (len(prompt) + len(content)) // 4
            track_token_usage(estimated_tokens)
            result = extract_json(content)
            if not result:
                logger.warning(
                    "LLM returned unparseable output (attempt %d/%d): %.200s",
                    attempt, max_attempts, content,
                )
                return (result, attempt)
            return (result, attempt)
        except Exception as exc:
            last_exception = exc
            if attempt < max_attempts:
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    "LLM call failed (attempt %d/%d, retrying in %.1fs): %s",
                    attempt, max_attempts, delay, exc,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "LLM call failed after %d attempts: %s",
                    max_attempts, exc,
                )

    assert last_exception is not None
    raise last_exception
