"""
Tests for issue #57: Replace _query private-method access with public dropTable()
on PgVectorStore.

AC1 - PgVectorStore exposes a public dropTable() method that executes
      DROP TABLE IF EXISTS <table> for the store's configured table.
AC2 - All three call-sites in src/data/collection.js (lines ~85, ~101) and
      src/store/postgres.js (line ~58) that previously called
      store._query("DROP TABLE IF EXISTS articles") now call store.dropTable().
AC3 - _query is no longer called from any file outside PgVectorStore.js itself.
AC4 - dropTable() uses the store's internally configured table name (not a
      hardcoded "articles" literal).
AC5 - Existing behaviour preserved: DROP TABLE IF EXISTS semantics (no error if
      table does not exist).
"""

import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PG_STORE_PATH = os.path.join(REPO_ROOT, "src", "store", "PgVectorStore.js")
COLLECTION_JS = os.path.join(REPO_ROOT, "src", "data", "collection.js")
POSTGRES_STORE_JS = os.path.join(REPO_ROOT, "src", "store", "postgres.js")


# ---------------------------------------------------------------------------
# AC1: PgVectorStore exposes a public dropTable() method with DROP TABLE IF EXISTS
# ---------------------------------------------------------------------------


def test_ac1_droptable_method_exists():
    """PgVectorStore.js must define a public async dropTable() method."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert re.search(r"async\s+dropTable\s*\(", src), (
        "PgVectorStore must expose a public async dropTable() method"
    )


def test_ac1_droptable_contains_drop_table_if_exists():
    """dropTable() must execute DROP TABLE IF EXISTS."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert re.search(r"DROP\s+TABLE\s+IF\s+EXISTS", src, re.IGNORECASE), (
        "PgVectorStore.dropTable() must contain DROP TABLE IF EXISTS"
    )


# ---------------------------------------------------------------------------
# AC2: All three external call-sites use store.dropTable() not store._query(...)
# ---------------------------------------------------------------------------


def test_ac2_collection_js_no_direct_query_for_drop():
    """collection.js must not call store._query with DROP TABLE."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert not re.search(r"\._query\s*\(\s*['\"]DROP\s+TABLE", src, re.IGNORECASE), (
        "collection.js must not call store._query('DROP TABLE ...') directly — use store.dropTable() instead"
    )


def test_ac2_collection_js_calls_droptable():
    """collection.js must call store.dropTable() in its dropCollection / createCollection paths."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert re.search(r"\.dropTable\s*\(", src), (
        "collection.js must call store.dropTable() instead of store._query('DROP TABLE...')"
    )


def test_ac2_postgres_store_js_no_direct_query_for_drop():
    """src/store/postgres.js must not call store._query with DROP TABLE."""
    with open(POSTGRES_STORE_JS) as f:
        src = f.read()
    assert not re.search(r"\._query\s*\(\s*['\"]DROP\s+TABLE", src, re.IGNORECASE), (
        "src/store/postgres.js must not call store._query('DROP TABLE ...') directly — use store.dropTable() instead"
    )


def test_ac2_postgres_store_js_calls_droptable():
    """src/store/postgres.js must call store.dropTable() in its dropCollection path."""
    with open(POSTGRES_STORE_JS) as f:
        src = f.read()
    assert re.search(r"\.dropTable\s*\(", src), (
        "src/store/postgres.js must call store.dropTable() instead of store._query('DROP TABLE...')"
    )


# ---------------------------------------------------------------------------
# AC3: _query is not called from any file outside PgVectorStore.js
# ---------------------------------------------------------------------------


def test_ac3_collection_js_no_query_call():
    """collection.js must not reference ._query at all."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert "_query" not in src, (
        "collection.js must not call the private _query method — all _query usage must stay inside PgVectorStore.js"
    )


def test_ac3_postgres_store_js_no_query_call():
    """src/store/postgres.js must not reference ._query at all."""
    with open(POSTGRES_STORE_JS) as f:
        src = f.read()
    assert "_query" not in src, (
        "src/store/postgres.js must not call the private _query method — all _query usage must stay inside PgVectorStore.js"
    )


def test_ac3_no_external_query_calls_in_src():
    """No file outside PgVectorStore.js in src/ should call ._query(...)."""
    violations = []
    for dirpath, _, filenames in os.walk(os.path.join(REPO_ROOT, "src")):
        for fname in filenames:
            if not fname.endswith(".js") and not fname.endswith(".ts"):
                continue
            filepath = os.path.join(dirpath, fname)
            # PgVectorStore.js is allowed to define and call _query internally
            if os.path.abspath(filepath) == os.path.abspath(PG_STORE_PATH):
                continue
            with open(filepath) as f:
                src = f.read()
            if re.search(r"\._query\s*\(", src):
                violations.append(filepath)
    assert not violations, (
        f"These files call the private ._query() method outside PgVectorStore.js: {violations}"
    )


# ---------------------------------------------------------------------------
# AC4: dropTable() uses the store's internally configured table name
# ---------------------------------------------------------------------------


def test_ac4_droptable_does_not_hardcode_articles():
    """dropTable() must not contain a hardcoded 'articles' string literal."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    # Extract the dropTable method body
    match = re.search(r"async\s+dropTable\s*\([^)]*\)\s*\{([^}]*)\}", src, re.DOTALL)
    assert match, "PgVectorStore must have a dropTable() method to check"
    body = match.group(1)
    assert "articles" not in body, (
        "dropTable() must not hardcode the table name 'articles' — use the store's configured table name (e.g. this._table)"
    )


def test_ac4_pg_store_has_table_property():
    """PgVectorStore must store the table name as an instance property (e.g. this._table)."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert re.search(r"this\._table\s*=", src), (
        "PgVectorStore constructor must set this._table to hold the configured table name"
    )


# ---------------------------------------------------------------------------
# AC5: DROP TABLE IF EXISTS semantics preserved
# ---------------------------------------------------------------------------


def test_ac5_droptable_uses_if_exists():
    """dropTable() must use DROP TABLE IF EXISTS (not plain DROP TABLE)."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    # Must have IF EXISTS in the context of DROP TABLE
    assert re.search(r"DROP\s+TABLE\s+IF\s+EXISTS", src, re.IGNORECASE), (
        "dropTable() must use DROP TABLE IF EXISTS to preserve no-error-if-missing semantics"
    )
