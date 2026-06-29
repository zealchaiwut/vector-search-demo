"""
Tests for issue #61: Consolidate dual Postgres connection configs (POSTGRES_* vs DATABASE_URL)

The problem: pg_client.js builds its pool from individual POSTGRES_HOST/PORT/DB/USER/PASSWORD
env vars, while PgVectorStore.js uses DATABASE_URL. This forces operators to configure two
separate sets of env vars to get both health probes and store operations working.

AC1 - pg_client.js accepts DATABASE_URL and uses it to construct the pool (primary path)
AC2 - pg_client.js falls back to individual POSTGRES_* vars when DATABASE_URL is not set
      (backward compatibility)
AC3 - PgVectorStore.js exposes a checkHealth() method that queries pg_extension for 'vector'
AC4 - .env.example comments clarify that DATABASE_URL is sufficient and POSTGRES_* are optional
      (only needed for docker-compose service defaults)
"""

import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PG_CLIENT_PATH = REPO_ROOT / "src" / "db" / "pg_client.js"
PG_STORE_PATH = REPO_ROOT / "src" / "store" / "PgVectorStore.js"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"

POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "")

needs_postgres = __import__("pytest").mark.skipif(
    not os.environ.get("POSTGRES_HOST"),
    reason="POSTGRES_HOST not set — skipping live Postgres tests",
)


def _read(path):
    return Path(path).read_text()


# ---------------------------------------------------------------------------
# AC1: pg_client.js uses DATABASE_URL when available
# ---------------------------------------------------------------------------


def test_ac1_pg_client_reads_database_url():
    """pg_client.js must read DATABASE_URL from the environment."""
    src = _read(PG_CLIENT_PATH)
    assert "DATABASE_URL" in src, (
        "pg_client.js must read DATABASE_URL env var to consolidate connection config"
    )


def test_ac1_pg_client_uses_connection_string_pool_when_database_url_set():
    """pg_client.js must construct Pool({ connectionString }) when DATABASE_URL is set."""
    src = _read(PG_CLIENT_PATH)
    # The pool must be constructable from a connectionString
    assert "connectionString" in src, (
        "pg_client.js must construct Pool({ connectionString }) when DATABASE_URL is set"
    )


# ---------------------------------------------------------------------------
# AC2: pg_client.js falls back to POSTGRES_* vars when DATABASE_URL is absent
# ---------------------------------------------------------------------------


def test_ac2_pg_client_still_accepts_postgres_vars():
    """pg_client.js must still reference POSTGRES_HOST for backward compatibility."""
    src = _read(PG_CLIENT_PATH)
    assert "POSTGRES_HOST" in src, (
        "pg_client.js must retain fallback to POSTGRES_HOST when DATABASE_URL is not set"
    )


def test_ac2_pg_client_fallback_is_conditional():
    """pg_client.js must only fall back to POSTGRES_* when DATABASE_URL is absent."""
    src = _read(PG_CLIENT_PATH)
    # There must be a conditional branch: DATABASE_URL present → connectionString path,
    # absent → individual-vars path. We check that both branches exist.
    assert "DATABASE_URL" in src and "POSTGRES_HOST" in src, (
        "pg_client.js must have both DATABASE_URL (primary) and POSTGRES_HOST (fallback) paths"
    )
    # The conditional must be an if/ternary/nullish, not just sequential reads
    has_branch = (
        re.search(r"if\s*\(.*DATABASE_URL", src)
        or re.search(r"DATABASE_URL.*\?", src)
        or re.search(r"\?\?|&&|\|\|", src)
    )
    assert has_branch, (
        "pg_client.js must conditionally choose DATABASE_URL over POSTGRES_* vars, not always use both"
    )


# ---------------------------------------------------------------------------
# AC3: PgVectorStore.js exposes checkHealth()
# ---------------------------------------------------------------------------


def test_ac3_pgvectorstore_has_check_health():
    """PgVectorStore.js must expose a checkHealth() method."""
    src = _read(PG_STORE_PATH)
    assert "checkHealth" in src, (
        "PgVectorStore must expose a checkHealth() method so pg_client.js is no longer the sole health probe"
    )


def test_ac3_pgvectorstore_check_health_queries_pg_extension():
    """PgVectorStore.checkHealth() must query pg_extension for 'vector'."""
    src = _read(PG_STORE_PATH)
    assert "pg_extension" in src, (
        "PgVectorStore.checkHealth() must query the pg_extension table"
    )
    assert "extname" in src, (
        "PgVectorStore.checkHealth() must select extname from pg_extension"
    )
    assert "'vector'" in src or '"vector"' in src, (
        "PgVectorStore.checkHealth() must filter WHERE extname = 'vector'"
    )


def test_ac3_pgvectorstore_check_health_is_async():
    """PgVectorStore.checkHealth() must be an async method."""
    src = _read(PG_STORE_PATH)
    assert re.search(r"async\s+checkHealth\s*\(", src), (
        "PgVectorStore.checkHealth() must be declared as an async method"
    )


# ---------------------------------------------------------------------------
# AC4: .env.example documents that POSTGRES_* vars are optional when DATABASE_URL is set
# ---------------------------------------------------------------------------


def test_ac4_env_example_documents_database_url_as_primary():
    """
    .env.example must clarify that DATABASE_URL is the primary/sufficient connection
    string and POSTGRES_* vars are for docker-compose defaults only.
    """
    content = _read(ENV_EXAMPLE_PATH)
    # Check that the comment near DATABASE_URL or POSTGRES_* section explains the relationship
    lower = content.lower()
    has_clarity = (
        "optional" in lower
        or "docker-compose" in lower.replace("-", "")
        or "sufficient" in lower
        or "only needed" in lower
        or "primary" in lower
        or "pg_client" in lower
    )
    assert has_clarity, (
        ".env.example must clarify that POSTGRES_* vars are optional/secondary when DATABASE_URL is set "
        "(e.g., add a comment explaining docker-compose defaults vs operator config)"
    )
