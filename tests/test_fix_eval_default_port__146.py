"""
TDD tests for issue #146: Fix eval script default port mismatch with .env PORT=8000.

AC1 — run_eval.py default SEARCH_URL uses port 8000, not 7070.
AC2 — run_ablation.py _DEFAULT_SEARCH_URL uses port 8000, not 7070.
AC3 — src/eval/README.md example comment references port 8000, not 7070.
"""

import importlib.util
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL_SCRIPT = os.path.join(REPO_ROOT, "src", "eval", "run_eval.py")
ABLATION_SCRIPT = os.path.join(REPO_ROOT, "src", "eval", "run_ablation.py")
README_PATH = os.path.join(REPO_ROOT, "src", "eval", "README.md")


def _load_module(path, name):
    """Load a Python source file as a module without executing its main()."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# AC1 — run_eval.py default SEARCH_URL must be port 8000
# ---------------------------------------------------------------------------


def test_ac1_run_eval_default_port_not_7070():
    """run_eval.py must not default to port 7070."""
    mod = _load_module(EVAL_SCRIPT, "run_eval_146")
    assert "7070" not in mod.SEARCH_URL, (
        f"run_eval.py SEARCH_URL defaults to port 7070 — must align with .env PORT=8000. "
        f"Got: {mod.SEARCH_URL}"
    )


def test_ac1_run_eval_default_port_is_8000():
    """run_eval.py must default to port 8000 when SEARCH_URL env is unset."""
    env_backup = os.environ.pop("SEARCH_URL", None)
    try:
        spec = importlib.util.spec_from_file_location("run_eval_146b", EVAL_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert "8000" in mod.SEARCH_URL, (
            f"run_eval.py SEARCH_URL must default to port 8000. Got: {mod.SEARCH_URL}"
        )
    finally:
        if env_backup is not None:
            os.environ["SEARCH_URL"] = env_backup


def test_ac1_run_eval_env_override_still_works():
    """Setting SEARCH_URL env var must still override the default."""
    custom = "http://localhost:9999/search"
    os.environ["SEARCH_URL"] = custom
    try:
        spec = importlib.util.spec_from_file_location("run_eval_146c", EVAL_SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.SEARCH_URL == custom, (
            f"SEARCH_URL env override broken. Expected {custom!r}, got {mod.SEARCH_URL!r}"
        )
    finally:
        del os.environ["SEARCH_URL"]


# ---------------------------------------------------------------------------
# AC2 — run_ablation.py _DEFAULT_SEARCH_URL must be port 8000
# ---------------------------------------------------------------------------


def test_ac2_ablation_default_url_not_7070():
    """run_ablation.py must not have 7070 as the default search URL."""
    mod = _load_module(ABLATION_SCRIPT, "run_ablation_146")
    assert "7070" not in mod._DEFAULT_SEARCH_URL, (
        f"run_ablation.py _DEFAULT_SEARCH_URL contains port 7070 — must align with .env PORT=8000. "
        f"Got: {mod._DEFAULT_SEARCH_URL}"
    )


def test_ac2_ablation_default_url_is_8000():
    """run_ablation.py _DEFAULT_SEARCH_URL must be port 8000."""
    mod = _load_module(ABLATION_SCRIPT, "run_ablation_146b")
    assert "8000" in mod._DEFAULT_SEARCH_URL, (
        f"run_ablation.py _DEFAULT_SEARCH_URL must default to port 8000. Got: {mod._DEFAULT_SEARCH_URL}"
    )


# ---------------------------------------------------------------------------
# AC3 — README.md example must reference port 8000, not 7070
# ---------------------------------------------------------------------------


def test_ac3_readme_no_7070_in_example_comment():
    """README.md must not reference port 7070 in the running-the-eval example."""
    with open(README_PATH, encoding="utf-8") as f:
        content = f.read()
    assert "7070" not in content, (
        "src/eval/README.md still references port 7070 — must be updated to 8000."
    )


def test_ac3_readme_default_port_comment_says_8000():
    """README.md example comment must say 'default port 8000'."""
    with open(README_PATH, encoding="utf-8") as f:
        content = f.read()
    assert "8000" in content, (
        "src/eval/README.md example comment must reference port 8000."
    )
