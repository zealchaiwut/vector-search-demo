"""
TDD tests for issue #108: re-embed completion message hardcodes model name

The completion message in src/commands/re-embed.js must reflect the active
EMBEDDING_MODEL rather than hardcoding "multilingual-e5-small".

AC1 — re-embed.js does NOT contain a hardcoded model string in the completion
       message; it reads from EMBEDDING_MODEL env var (or a derived constant).
AC2 — Running re-embed with a custom EMBEDDING_MODEL prints that model name in
       the completion line, not the default name.
AC3 — Running re-embed without EMBEDDING_MODEL prints the default model name
       (Xenova/multilingual-e5-small or multilingual-e5-small) in the
       completion line.
"""

import os
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REEMBED_CMD = os.path.join(REPO_ROOT, "src", "commands", "re-embed.js")
MODEL_TIMEOUT = 120


def _run_cli(args, env=None, timeout=MODEL_TIMEOUT):
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    result = subprocess.run(
        ["node", "src/cli.js", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
        env=run_env,
    )
    return result.stdout, result.stderr, result.returncode


# ---------------------------------------------------------------------------
# AC1 — Source-level check: no hardcoded model string in completion message
# ---------------------------------------------------------------------------

def test_ac1_completion_message_does_not_hardcode_model_name():
    """AC1: The completion stdout.write must not contain a literal model name."""
    with open(REEMBED_CMD) as f:
        source = f.read()

    # Find the completion line (contains "re-embedded with")
    for line in source.splitlines():
        if "re-embedded with" in line and "write" in line:
            # The model name must NOT be a string literal on this line
            assert "multilingual-e5-small" not in line, (
                f"Completion message hardcodes model name on line:\n  {line.strip()}\n"
                "It must interpolate a variable instead."
            )
            assert "e5-base" not in line, (
                f"Completion message hardcodes 'e5-base' on line:\n  {line.strip()}"
            )
            assert "e5-large" not in line, (
                f"Completion message hardcodes 'e5-large' on line:\n  {line.strip()}"
            )
            break
    else:
        raise AssertionError(
            "Could not find the completion line (containing 're-embedded with') in re-embed.js"
        )


def test_ac1_completion_message_uses_variable_or_env():
    """AC1: The completion line uses a JS variable (not a string literal) for the model."""
    with open(REEMBED_CMD) as f:
        source = f.read()

    # The source must reference EMBEDDING_MODEL env var OR a variable holding it
    assert "EMBEDDING_MODEL" in source or "MODEL" in source, (
        "re-embed.js must reference process.env.EMBEDDING_MODEL or a MODEL variable "
        "to build the completion message dynamically"
    )

    for line in source.splitlines():
        if "re-embedded with" in line and "write" in line:
            # The line must use template literal interpolation ${...} or string concat with a var
            assert "${" in line or "+" in line, (
                f"Completion line must use a variable (template literal or concat), got:\n  {line.strip()}"
            )
            break


# ---------------------------------------------------------------------------
# AC2 — Behavioral: custom EMBEDDING_MODEL appears in output
# ---------------------------------------------------------------------------

def test_ac2_custom_model_appears_in_completion_message():
    """AC2: When EMBEDDING_MODEL is set, its value appears in the completion output."""
    custom_model = "multilingual-e5-base"

    # Seed the mock store
    out1, err1, rc1 = _run_cli(["ingest"], env={"DB_BACKEND": "mock"})
    assert rc1 == 0, f"Ingest failed: {err1}\n{out1}"

    out, err, rc = _run_cli(
        ["re-embed"],
        env={"DB_BACKEND": "mock", "EMBEDDING_MODEL": custom_model},
    )
    assert rc == 0, f"re-embed failed (rc={rc}):\n{err}\n{out}"

    combined = out + err
    assert custom_model in combined or "e5-base" in combined, (
        f"Expected '{custom_model}' in re-embed output when EMBEDDING_MODEL is set, "
        f"but got:\nstdout: {out}\nstderr: {err}"
    )


# ---------------------------------------------------------------------------
# AC3 — Behavioral: default model name appears when env var not set
# ---------------------------------------------------------------------------

def test_ac3_default_model_appears_in_completion_message_when_env_unset():
    """AC3: Without EMBEDDING_MODEL, the default model name appears in output."""
    # Seed the mock store
    out1, err1, rc1 = _run_cli(["ingest"], env={"DB_BACKEND": "mock"})
    assert rc1 == 0, f"Ingest failed: {err1}\n{out1}"

    env_without_model = {k: v for k, v in os.environ.items() if k != "EMBEDDING_MODEL"}
    env_without_model["DB_BACKEND"] = "mock"

    result = subprocess.run(
        ["node", "src/cli.js", "re-embed"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=MODEL_TIMEOUT,
        env=env_without_model,
    )
    out = result.stdout
    err = result.stderr
    assert result.returncode == 0, f"re-embed failed:\n{err}\n{out}"

    combined = out + err
    assert "multilingual-e5-small" in combined or "e5-small" in combined, (
        f"Expected default model name in output when EMBEDDING_MODEL not set, "
        f"but got:\nstdout: {out}\nstderr: {err}"
    )
