"""
Acceptance tests for issue #52: Route all commands through DB_BACKEND factory.

AC1  - DB_BACKEND=milvus: every command resolves and operates against Milvus via factory
AC2  - DB_BACKEND=postgres: every command routes to Postgres VectorStore via factory
AC3  - DB_BACKEND=mock: every command routes to Mock VectorStore via factory
AC4  - Each command emits a startup log: "[backend] active store: <backend>"
AC5  - Factory raises a clear error (with the invalid value) for unrecognised DB_BACKEND
AC6  - README contains a section describing the three backends and how to switch via DB_BACKEND
AC7  - DESIGN contains a section describing backends, the factory pattern, and switching
AC8  - Parity test: seed mock store → query → result non-empty and ranked (score field)
AC9  - Parity test passes without a live Milvus or Postgres instance
AC10 - No command in src/commands imports a VectorStore implementation directly
"""

import json
import os
import re
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_JS = os.path.join(REPO_ROOT, "src", "cli.js")
COMMANDS_DIR = os.path.join(REPO_ROOT, "src", "commands")
FACTORY_JS = os.path.join(REPO_ROOT, "src", "store", "factory.js")
COLLECTION_JSON = os.path.join(REPO_ROOT, "collection.json")
README_PATH = os.path.join(REPO_ROOT, "README.md")
DESIGN_PATH = os.path.join(REPO_ROOT, "DESIGN.md")

COMMANDS = ["init", "ingest", "search", "ping", "verify"]


def run_cli(*args, env_override=None, timeout=300):
    env = os.environ.copy()
    # strip any live-backend env vars so mock tests stay offline
    for key in ("MILVUS_HOST", "MILVUS_PORT", "DATA_BACKEND"):
        env.pop(key, None)
    if env_override:
        env.update(env_override)
    return subprocess.run(
        ["node", CLI_JS, *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=timeout,
    )


def collection_is_seeded():
    """Return True if collection.json has at least one embedded row."""
    if not os.path.exists(COLLECTION_JSON):
        return False
    try:
        rows = json.loads(open(COLLECTION_JSON).read())
        return isinstance(rows, list) and len(rows) > 0 and "embedding" in (rows[0] if rows else {})
    except (json.JSONDecodeError, IOError, KeyError):
        return False


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def ensure_mock_store_seeded():
    """Seed collection.json once per session (uses MiniLM; cached after first run)."""
    if not collection_is_seeded():
        result = run_cli("ingest", env_override={"DB_BACKEND": "mock"}, timeout=600)
        assert result.returncode == 0, (
            f"Seeding ingest failed:\n{result.stdout}\n{result.stderr}"
        )
    assert collection_is_seeded(), "collection.json is still empty after ingest"


# ---------------------------------------------------------------------------
# AC1/AC2/AC3 — Factory routing: static analysis on factory.js
# ---------------------------------------------------------------------------

def test_factory_js_exists():
    """src/store/factory.js must exist."""
    assert os.path.isfile(FACTORY_JS), f"Missing: {FACTORY_JS}"


def test_factory_references_milvus_store():
    """factory.js must reference a milvus store module (AC1)."""
    with open(FACTORY_JS) as f:
        src = f.read()
    assert "milvus" in src.lower(), "factory.js must reference milvus backend"


def test_factory_references_postgres_store():
    """factory.js must reference a postgres store module (AC2)."""
    with open(FACTORY_JS) as f:
        src = f.read()
    assert "postgres" in src.lower(), "factory.js must reference postgres backend"


def test_factory_references_mock_store():
    """factory.js must reference a mock store module (AC3)."""
    with open(FACTORY_JS) as f:
        src = f.read()
    assert "mock" in src.lower(), "factory.js must reference mock backend"


# ---------------------------------------------------------------------------
# AC3 — DB_BACKEND=mock routes each command to Mock store
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command", ["init", "ping", "verify"])
def test_ac3_mock_command_runs_without_milvus(command):
    """Each command with DB_BACKEND=mock must run without a live Milvus instance."""
    result = run_cli(command, env_override={"DB_BACKEND": "mock"})
    # exit 0 or 1 is fine — just must not crash due to missing Milvus
    assert "ECONNREFUSED" not in result.stderr, (
        f"Command '{command}' with DB_BACKEND=mock tried to connect to Milvus:\n{result.stderr}"
    )
    assert "Cannot connect" not in result.stderr or "mock" in result.stdout.lower(), (
        f"Command '{command}' appears to have failed due to backend routing:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# AC4 — Startup log line "[backend] active store: <backend>"
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command,extra_args", [
    ("init", []),
    ("ping", []),
    ("verify", []),
    ("search", ["vector search demo"]),
])
def test_ac4_startup_log_emitted(command, extra_args):
    """Each command must emit '[backend] active store: mock' with DB_BACKEND=mock."""
    result = run_cli(command, *extra_args, env_override={"DB_BACKEND": "mock"})
    combined = result.stdout + result.stderr
    assert re.search(r"\[backend\]\s+active store:\s+mock", combined), (
        f"'{command}' did not emit '[backend] active store: mock'.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_ac4_startup_log_ingest():
    """ingest must emit '[backend] active store: mock' with DB_BACKEND=mock."""
    result = run_cli("ingest", env_override={"DB_BACKEND": "mock"})
    combined = result.stdout + result.stderr
    assert re.search(r"\[backend\]\s+active store:\s+mock", combined), (
        f"'ingest' did not emit '[backend] active store: mock'.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# AC5 — Factory raises a clear error for unrecognised DB_BACKEND
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command", ["init", "ping", "search", "verify", "ingest"])
def test_ac5_invalid_backend_exits_nonzero(command):
    """Any command with an invalid DB_BACKEND must exit non-zero."""
    extra = ["dummy query"] if command == "search" else []
    result = run_cli(command, *extra, env_override={"DB_BACKEND": "invalid_value"})
    assert result.returncode != 0, (
        f"Expected non-zero exit for DB_BACKEND=invalid_value on '{command}', got 0"
    )


def test_ac5_error_message_contains_invalid_value():
    """Error message for invalid DB_BACKEND must contain the bad value."""
    result = run_cli("init", env_override={"DB_BACKEND": "badbackend"})
    combined = result.stdout + result.stderr
    assert "badbackend" in combined, (
        f"Error message for invalid DB_BACKEND must include the bad value.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# AC6 — README has a backends section
# ---------------------------------------------------------------------------

def test_ac6_readme_backends_section_exists():
    """README must contain a section about backends."""
    with open(README_PATH) as f:
        content = f.read()
    assert re.search(r"##\s+.*backend", content, re.IGNORECASE), (
        "README must contain a '## Backends' (or similar) section"
    )


def test_ac6_readme_lists_all_three_backends():
    """README backends section must mention milvus, postgres, and mock."""
    with open(README_PATH) as f:
        content = f.read()
    for name in ("milvus", "postgres", "mock"):
        assert name in content.lower(), f"README must mention backend '{name}'"


def test_ac6_readme_explains_db_backend_env_var():
    """README must mention DB_BACKEND and how to set it."""
    with open(README_PATH) as f:
        content = f.read()
    assert "DB_BACKEND" in content, "README must mention the DB_BACKEND env var"


# ---------------------------------------------------------------------------
# AC7 — DESIGN has a backends section
# ---------------------------------------------------------------------------

def test_ac7_design_backends_section_exists():
    """DESIGN.md must contain a section about backends."""
    with open(DESIGN_PATH) as f:
        content = f.read()
    assert re.search(r"##\s+.*backend", content, re.IGNORECASE), (
        "DESIGN.md must contain a '## Backends' (or similar) section"
    )


def test_ac7_design_mentions_factory_pattern():
    """DESIGN.md must describe the factory pattern."""
    with open(DESIGN_PATH) as f:
        content = f.read()
    assert re.search(r"factory", content, re.IGNORECASE), (
        "DESIGN.md must describe the factory pattern for backend resolution"
    )


def test_ac7_design_explains_db_backend_switching():
    """DESIGN.md must mention DB_BACKEND switching."""
    with open(DESIGN_PATH) as f:
        content = f.read()
    assert "DB_BACKEND" in content, "DESIGN.md must mention the DB_BACKEND env var"


# ---------------------------------------------------------------------------
# AC8 — Parity test: seed mock, query, result is non-empty and ranked
# ---------------------------------------------------------------------------

def test_ac8_parity_search_returns_results():
    """Mock store search must return at least one result (requires seeded collection)."""
    result = run_cli("search", "vector search semantic", env_override={"DB_BACKEND": "mock"})
    assert result.returncode == 0, (
        f"search with DB_BACKEND=mock exited non-zero:\n{result.stderr}"
    )
    assert "No results found" not in result.stdout, (
        f"Expected search results in mock store, got 'No results found':\n{result.stdout}"
    )
    # Must have at least one result block
    assert re.search(r"rank\s*[:\-]?\s*1", result.stdout, re.IGNORECASE), (
        f"Expected at least one ranked result in output:\n{result.stdout}"
    )


def test_ac8_parity_results_have_score_field():
    """Search results from the mock store must include a score field."""
    result = run_cli("search", "vector search semantic", env_override={"DB_BACKEND": "mock"})
    assert result.returncode == 0
    assert re.search(r"score\s*[:\-]\s*[\d.]+", result.stdout, re.IGNORECASE), (
        f"Results must include a numeric score field:\n{result.stdout}"
    )


def test_ac8_parity_results_are_ranked_descending():
    """Results must be sorted by descending score."""
    result = run_cli("search", "vector search semantic", "-k", "5",
                     env_override={"DB_BACKEND": "mock"})
    assert result.returncode == 0
    scores = [
        float(m)
        for m in re.findall(r"score\s*[:\-]\s*([\d.]+)", result.stdout, re.IGNORECASE)
    ]
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], (
            f"Scores not descending at position {i}: {scores[i]} < {scores[i+1]}"
        )


# ---------------------------------------------------------------------------
# AC9 — Parity test runs without live Milvus or Postgres
# ---------------------------------------------------------------------------

def test_ac9_parity_needs_no_milvus():
    """Parity search must not attempt a Milvus connection when DB_BACKEND=mock."""
    result = run_cli("search", "semantic search", env_override={"DB_BACKEND": "mock"})
    assert "ECONNREFUSED" not in result.stderr, (
        f"mock search tried to connect to Milvus:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# AC10 — No command in src/commands imports VectorStore implementations directly
# ---------------------------------------------------------------------------

FORBIDDEN_IMPORTS = [
    "../data/collection",
    "../milvus/client",
]


def test_ac10_no_direct_store_imports_in_commands():
    """No file in src/commands/ may import a VectorStore implementation directly."""
    violations = []
    for fname in sorted(os.listdir(COMMANDS_DIR)):
        if not fname.endswith(".js"):
            continue
        path = os.path.join(COMMANDS_DIR, fname)
        with open(path) as f:
            src = f.read()
        for bad in FORBIDDEN_IMPORTS:
            if bad in src:
                violations.append(f"{fname} imports '{bad}'")
    assert not violations, (
        "Commands must not import VectorStore implementations directly:\n"
        + "\n".join(violations)
    )
