"""Unit test: load_dotenv(override=True) behavior.

Ensures that .env values override shell environment variables, even when
the shell has the same var set to an empty string. This is critical for
CRISIS_TRIGGER_TOKEN auth — if the uvicorn process is started in a shell
where the token is unset or empty, the .env value must still win.

Run: cd /root/crisis-monitor/backend && uv run python tests/test_load_dotenv.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _project_root() -> Path:
    return Path("/root/crisis-monitor/backend")


def test_override_env_with_value():
    """When shell has CRISIS_TRIGGER_TOKEN=shell_value and .env has env_value,
    load_dotenv(override=True) makes the .env value win."""
    env_dir = _project_root()
    env_file = env_dir / ".env"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os; "
                "os.environ['CRISIS_TRIGGER_TOKEN'] = 'shell_value'; "
                "from dotenv import load_dotenv; "
                f"load_dotenv(dotenv_path='{env_file}', override=True); "
                "print(os.environ['CRISIS_TRIGGER_TOKEN'])"
            ),
        ],
        capture_output=True,
        text=True,
        cwd=str(env_dir),
        timeout=10,
    )

    token = result.stdout.strip()
    assert token, "Expected a non-empty token from .env"
    assert token != "shell_value", (
        f"override=True should have replaced 'shell_value' with .env value, "
        f"but got '{token}'"
    )
    assert token != "", "Token should not be empty"


def test_override_env_empty_string():
    """When shell has CRISIS_TRIGGER_TOKEN='' (empty) and .env has a value,
    load_dotenv(override=True) makes the .env value win."""
    env_dir = _project_root()
    env_file = env_dir / ".env"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os; "
                "os.environ['CRISIS_TRIGGER_TOKEN'] = ''; "
                "from dotenv import load_dotenv; "
                f"load_dotenv(dotenv_path='{env_file}', override=True); "
                "print(repr(os.environ['CRISIS_TRIGGER_TOKEN']))"
            ),
        ],
        capture_output=True,
        text=True,
        cwd=str(env_dir),
        timeout=10,
    )

    token = result.stdout.strip()
    # repr should show a non-empty string
    assert token, "Expected a non-empty token from .env"
    assert token != "''", f"override=True should have replaced empty string with .env value, got {token}"
    assert token not in ("''", '""'), f"Token should not be empty string repr, got {token}"


def test_override_env_unset():
    """When shell does not have CRISIS_TRIGGER_TOKEN at all and .env has a value,
    load_dotenv(override=True) loads the .env value (unchanged from default behavior)."""
    env_dir = _project_root()
    env_file = env_dir / ".env"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os; "
                "os.environ.pop('CRISIS_TRIGGER_TOKEN', None); "
                "from dotenv import load_dotenv; "
                f"load_dotenv(dotenv_path='{env_file}', override=True); "
                "print(os.environ['CRISIS_TRIGGER_TOKEN'])"
            ),
        ],
        capture_output=True,
        text=True,
        cwd=str(env_dir),
        timeout=10,
    )

    token = result.stdout.strip()
    assert token, "Expected a non-empty token from .env"
    assert token != "", "Token should not be empty"


def test_main_py_uses_override_true():
    """Verify src/main.py calls load_dotenv(override=True)."""
    main_path = _project_root() / "src" / "main.py"
    content = main_path.read_text()
    assert "load_dotenv(override=True)" in content, (
        "src/main.py must call load_dotenv(override=True), not load_dotenv()"
    )


def test_other_env_vars_also_override():
    """Verify that override=True also protects other vars like OPENCODE_GO_API_KEY."""
    env_dir = _project_root()
    env_file = env_dir / ".env"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os; "
                "os.environ['OPENCODE_GO_API_KEY'] = ''; "
                "from dotenv import load_dotenv; "
                f"load_dotenv(dotenv_path='{env_file}', override=True); "
                "val = os.environ.get('OPENCODE_GO_API_KEY', 'MISSING'); "
                "print(f'len={len(val)} empty={val == \"\"}' if val != 'MISSING' else 'MISSING')"
            ),
        ],
        capture_output=True,
        text=True,
        cwd=str(env_dir),
        timeout=10,
    )

    output = result.stdout.strip()
    assert "MISSING" not in output, f"OPENCODE_GO_API_KEY should be in .env, got {output}"
    assert "empty=False" in output or "empty=True" not in output, (
        f"OPENCODE_GO_API_KEY should not be empty after override, got {output}"
    )


# ── Runner ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import traceback

    tests = [
        ("test_main_py_uses_override_true", test_main_py_uses_override_true),
        ("test_override_env_with_value", test_override_env_with_value),
        ("test_override_env_empty_string", test_override_env_empty_string),
        ("test_override_env_unset", test_override_env_unset),
        ("test_other_env_vars_also_override", test_other_env_vars_also_override),
    ]

    passed = 0
    failed = 0

    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    if failed:
        sys.exit(1)
