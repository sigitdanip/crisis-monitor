"""Unit tests for retry logic and module self-checks — no live API required."""
import sys
import asyncio

# 1. Test retry logic with mock
async def test_retry_raises_after_exhaustion():
    """Verify call_llm_with_retry raises after max_attempts failures."""
    from unittest.mock import AsyncMock, patch

    with patch("src.agent.llm.get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke.side_effect = RuntimeError("simulated 503")
        mock_get_llm.return_value = mock_llm

        from src.agent.llm import call_llm_with_retry
        try:
            await call_llm_with_retry("test prompt", max_attempts=2, base_delay=0.01)
            assert False, "Should have raised"
        except RuntimeError as e:
            assert "simulated 503" in str(e)

        # Verify 2 attempts were made
        assert mock_llm.ainvoke.call_count == 2
    print("PASS: test_retry_raises_after_exhaustion")


async def test_retry_succeeds_on_second_attempt():
    """Verify retry succeeds if first fails, second passes."""
    from unittest.mock import AsyncMock, patch

    with patch("src.agent.llm.get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke.side_effect = [
            RuntimeError("simulated 503"),
            AsyncMock(content='{"ok": true}'),
        ]
        mock_get_llm.return_value = mock_llm

        from src.agent.llm import call_llm_with_retry
        result, attempt = await call_llm_with_retry("test", max_attempts=2, base_delay=0.01)

        assert result == {"ok": True}, f"Expected {{'ok': True}}, got {result}"
        assert attempt == 2, f"Expected attempt 2, got {attempt}"
        assert mock_llm.ainvoke.call_count == 2
    print("PASS: test_retry_succeeds_on_second_attempt")


async def test_retry_succeeds_on_first_attempt():
    """Verify normal path returns (result, 1)."""
    from unittest.mock import AsyncMock, patch

    with patch("src.agent.llm.get_llm") as mock_get_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = AsyncMock(content='{"status": "normal"}')
        mock_get_llm.return_value = mock_llm

        from src.agent.llm import call_llm_with_retry
        result, attempt = await call_llm_with_retry("test", max_attempts=2, base_delay=0.01)

        assert result == {"status": "normal"}
        assert attempt == 1
        assert mock_llm.ainvoke.call_count == 1
    print("PASS: test_retry_succeeds_on_first_attempt")


async def test_get_llm_default_timeout():
    """Verify get_llm() default timeout is 60."""
    from src.agent.llm import get_llm
    import inspect
    sig = inspect.signature(get_llm)
    assert sig.parameters["timeout"].default == 60, \
        f"Expected timeout=60, got {sig.parameters['timeout'].default}"
    print("PASS: test_get_llm_default_timeout")


# 2. Module self-checks
def test_module_self_checks():
    """Run the __main__ self-checks from each module."""
    import subprocess
    import os
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    modules = [
        "src/agent/pathway_synthesizer.py",
        "src/agent/end_state.py",
        "src/agent/indicator_narrator.py",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = backend_dir
    for mod in modules:
        result = subprocess.run(
            [sys.executable, mod],
            capture_output=True, text=True,
            cwd=backend_dir, env=env,
        )
        assert result.returncode == 0, f"{mod} failed: {result.stderr}"
        print(f"PASS: {mod} self-check — {result.stdout.strip()}")


async def main():
    print("=== Running retry unit tests ===")
    await test_retry_raises_after_exhaustion()
    await test_retry_succeeds_on_second_attempt()
    await test_retry_succeeds_on_first_attempt()
    await test_get_llm_default_timeout()

    print("\n=== Running module self-checks ===")
    test_module_self_checks()

    print("\n=== ALL TESTS PASSED ===")


asyncio.run(main())
