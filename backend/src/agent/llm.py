"""LLM helper — OpenCode Go via langchain-openai."""
import asyncio
import json
import logging
import os
import re
from typing import Any

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


def get_llm(temperature: float = 0.3, timeout: int = 60) -> ChatOpenAI:
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


async def call_llm_with_retry(
    prompt: str,
    max_attempts: int = 2,
    timeout: int = 60,
    base_delay: float = 1.0,
    temperature: float = 0.3,
) -> tuple[dict[str, Any], int]:
    """Call the LLM with retry on transient failures.

    Creates an LLM instance via get_llm(), invokes with the prompt, extracts
    content via get_llm_content(), and parses JSON via extract_json().

    On failure (timeout, network error, 5xx), retries up to max_attempts
    times with exponential backoff (base_delay, base_delay*2, ...).

    Args:
        prompt: The full prompt string to send.
        max_attempts: Maximum call attempts (default 2).
        timeout: Per-call timeout in seconds (default 60).
        base_delay: Initial backoff delay in seconds (default 1.0).
        temperature: LLM temperature (default 0.3).

    Returns:
        Tuple of (parsed_json_dict, attempt_count) on success.

    Raises:
        The last exception after exhausting all attempts.
    """
    last_exception: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            llm = get_llm(temperature=temperature, timeout=timeout)
            resp = await llm.ainvoke(prompt)
            content = get_llm_content(resp)
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

    # All attempts exhausted — raise the last exception
    assert last_exception is not None
    raise last_exception
