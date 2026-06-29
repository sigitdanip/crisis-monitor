"""Services package — shared service modules.

- auth.py: API key authentication.
- health.py: System health checks.
- pipeline_runner.py: Shared execute_pipeline (called by HTTP trigger + scheduler).
- tier_classifier.py: Per-dot data completeness tiering (LIVE/MIXED/QUALITATIVE).
- trigger_idempotency.py: Per-source duplicate trigger prevention.
- url_validator.py: Async HEAD check + 24h cache for citation liveness.
- qualitative_fallback.py: DuckDuckGo web search + LLM synthesis for MIXED/QUALITATIVE dots.
- fetcher_health.py: Per-fetcher success/failure tracking with 24h success rate.
"""

from src.services.tier_classifier import classify_dots, classify_dot, overall_tier
from src.services.url_validator import validate_urls
from src.services.qualitative_fallback import (
    run_qualitative_fallback,
    synthesize_dot_qualitative,
    init_fallback_run,
    get_fallback_cost,
    search_dot,
    synthesize_dot,
)

__all__ = [
    "classify_dots",
    "classify_dot",
    "overall_tier",
    "validate_urls",
    "run_qualitative_fallback",
    "synthesize_dot_qualitative",
    "init_fallback_run",
    "get_fallback_cost",
    "search_dot",
    "synthesize_dot",
]
