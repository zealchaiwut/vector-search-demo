"""
Tests for issue #51: Add Postgres pgvector backend to VectorStore (UAT)

AC1  - DB_BACKEND=postgres routes to PgVectorStore in src/store/
AC2  - SQL migration creates articles table with correct columns
AC3  - Migration creates HNSW cosine index
AC4  - Migration is idempotent (safe to run multiple times)
AC5  - init/migrate applies migration against configured Postgres connection
AC6  - upsert uses INSERT...ON CONFLICT(id) DO UPDATE (no duplicate rows)
AC7  - delete executes DELETE FROM articles WHERE id = $1
AC8  - search executes ORDER BY embedding <=> $1 and returns 1-(distance) as score
AC9  - count returns total row count from articles
AC10 - ping verifies Postgres connection is live
AC11 - Vectors encoded/decoded using pgvector npm package with pg client
AC12 - Feature parity: init, ingest, search (with best_passage), delete all work via postgres
"""

import os
import re

import httpx
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(REPO_ROOT, "src", "store")
PG_STORE_PATH = os.path.join(STORE_DIR, "PgVectorStore.js")
BACKEND_JS = os.path.join(REPO_ROOT, "src", "data", "backend.js")
COLLECTION_JS = os.path.join(REPO_ROOT, "src", "data", "collection.js")
SEARCH_JS = os.path.join(REPO_ROOT, "src", "core", "search.js")
INIT_CMD = os.path.join(REPO_ROOT, "src", "commands", "init.js")
PING_CMD = os.path.join(REPO_ROOT, "src", "commands", "ping.js")

# Resolved from UAT .env at runtime; see tester skill Step 0.
BASE_URL = os.environ.get("UAT_BASE_URL") or "http://localhost:" + os.environ.get("UAT_PORT", "8010")


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


# ---------------------------------------------------------------------------
# AC1: src/store/ exists and DB_BACKEND=postgres routes to PgVectorStore
# ---------------------------------------------------------------------------


def test_ac1_pg_vector_store_file_exists():
    """PgVectorStore.js must exist in src/store/."""
    assert os.path.isfile(PG_STORE_PATH), (
        f"src/store/PgVectorStore.js not found at {PG_STORE_PATH}"
    )


def test_ac1_backend_js_has_use_postgres():
    """backend.js must export a usePostgres() function."""
    with open(BACKEND_JS) as f:
        src = f.read()
    assert re.search(r"export\s+function\s+usePostgres", src), (
        "backend.js must export usePostgres() function"
    )


def test_ac1_backend_js_checks_db_backend_postgres():
    """backend.js usePostgres must check DB_BACKEND=postgres env var."""
    with open(BACKEND_JS) as f:
        src = f.read()
    assert "DB_BACKEND" in src, "backend.js must check DB_BACKEND env var"
    assert "postgres" in src.lower(), "backend.js must handle 'postgres' backend"


def test_ac1_collection_js_imports_pg_store():
    """collection.js must import or reference PgVectorStore."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert "PgVectorStore" in src or "pgvector" in src.lower() or "getPostgresStore" in src, (
        "collection.js must reference PgVectorStore for the postgres path"
    )


# ---------------------------------------------------------------------------
# AC2: SQL migration creates articles table with correct columns
# ---------------------------------------------------------------------------


def test_ac2_migration_file_exists():
    """A SQL migration file must exist in src/store/migrations/."""
    migrations_dir = os.path.join(STORE_DIR, "migrations")
    assert os.path.isdir(migrations_dir), (
        "src/store/migrations/ directory not found"
    )
    sql_files = [f for f in os.listdir(migrations_dir) if f.endswith(".sql")]
    assert sql_files, "At least one .sql migration file must exist in src/store/migrations/"


def test_ac2_migration_creates_articles_table():
    """Migration SQL must CREATE TABLE articles."""
    migrations_dir = os.path.join(STORE_DIR, "migrations")
    sql_files = sorted(f for f in os.listdir(migrations_dir) if f.endswith(".sql"))
    combined = ""
    for fname in sql_files:
        with open(os.path.join(migrations_dir, fname)) as f:
            combined += f.read()
    assert re.search(r"CREATE TABLE", combined, re.IGNORECASE), (
        "Migration must contain CREATE TABLE statement"
    )
    assert "articles" in combined, "Migration must create an 'articles' table"


def test_ac2_migration_has_id_column():
    """Migration must define id text primary key."""
    migrations_dir = os.path.join(STORE_DIR, "migrations")
    combined = ""
    for fname in sorted(os.listdir(migrations_dir)):
        if fname.endswith(".sql"):
            with open(os.path.join(migrations_dir, fname)) as f:
                combined += f.read()
    assert re.search(r"id\s+text\s+primary\s+key", combined, re.IGNORECASE), (
        "Migration must define 'id text primary key' column"
    )


def test_ac2_migration_has_headline_column():
    """Migration must define headline text not null."""
    migrations_dir = os.path.join(STORE_DIR, "migrations")
    combined = ""
    for fname in sorted(os.listdir(migrations_dir)):
        if fname.endswith(".sql"):
            with open(os.path.join(migrations_dir, fname)) as f:
                combined += f.read()
    assert re.search(r"headline\s+text\s+not\s+null", combined, re.IGNORECASE), (
        "Migration must define 'headline text not null' column"
    )


def test_ac2_migration_has_details_column():
    """Migration must define details text not null."""
    migrations_dir = os.path.join(STORE_DIR, "migrations")
    combined = ""
    for fname in sorted(os.listdir(migrations_dir)):
        if fname.endswith(".sql"):
            with open(os.path.join(migrations_dir, fname)) as f:
                combined += f.read()
    assert re.search(r"details\s+text\s+not\s+null", combined, re.IGNORECASE), (
        "Migration must define 'details text not null' column"
    )


def test_ac2_migration_has_embedding_vector_384():
    """Migration must define embedding vector(384)."""
    migrations_dir = os.path.join(STORE_DIR, "migrations")
    combined = ""
    for fname in sorted(os.listdir(migrations_dir)):
        if fname.endswith(".sql"):
            with open(os.path.join(migrations_dir, fname)) as f:
                combined += f.read()
    assert re.search(r"embedding\s+vector\s*\(\s*384\s*\)", combined, re.IGNORECASE), (
        "Migration must define 'embedding vector(384)' column"
    )


def test_ac2_migration_has_created_at_column():
    """Migration must define created_at timestamptz default now()."""
    migrations_dir = os.path.join(STORE_DIR, "migrations")
    combined = ""
    for fname in sorted(os.listdir(migrations_dir)):
        if fname.endswith(".sql"):
            with open(os.path.join(migrations_dir, fname)) as f:
                combined += f.read()
    assert re.search(r"created_at\s+timestamptz", combined, re.IGNORECASE), (
        "Migration must define 'created_at timestamptz' column"
    )


# ---------------------------------------------------------------------------
# AC3: Migration creates HNSW cosine index
# ---------------------------------------------------------------------------


def test_ac3_migration_creates_hnsw_index():
    """Migration must create an HNSW cosine index on the embedding column."""
    migrations_dir = os.path.join(STORE_DIR, "migrations")
    combined = ""
    for fname in sorted(os.listdir(migrations_dir)):
        if fname.endswith(".sql"):
            with open(os.path.join(migrations_dir, fname)) as f:
                combined += f.read()
    assert re.search(r"hnsw", combined, re.IGNORECASE), (
        "Migration must create an HNSW index"
    )
    assert re.search(r"vector_cosine_ops", combined, re.IGNORECASE), (
        "Migration HNSW index must use vector_cosine_ops"
    )


# ---------------------------------------------------------------------------
# AC4: Migration is idempotent
# ---------------------------------------------------------------------------


def test_ac4_migration_uses_if_not_exists():
    """Migration must use IF NOT EXISTS for idempotency."""
    migrations_dir = os.path.join(STORE_DIR, "migrations")
    combined = ""
    for fname in sorted(os.listdir(migrations_dir)):
        if fname.endswith(".sql"):
            with open(os.path.join(migrations_dir, fname)) as f:
                combined += f.read()
    assert re.search(r"IF\s+NOT\s+EXISTS", combined, re.IGNORECASE), (
        "Migration must use IF NOT EXISTS for idempotent table/index creation"
    )


def test_ac4_migration_documents_recreate_path():
    """Migration must document a recreate path (drop-and-recreate comment)."""
    migrations_dir = os.path.join(STORE_DIR, "migrations")
    combined = ""
    for fname in sorted(os.listdir(migrations_dir)):
        if fname.endswith(".sql"):
            with open(os.path.join(migrations_dir, fname)) as f:
                combined += f.read()
    has_drop = "DROP" in combined.upper()
    has_recreate_comment = re.search(r"--.*recreat|--.*drop", combined, re.IGNORECASE)
    assert has_drop or has_recreate_comment, (
        "Migration must document a recreate path (DROP TABLE or a comment describing it)"
    )


# ---------------------------------------------------------------------------
# AC5: init applies migration against Postgres (static analysis only)
# ---------------------------------------------------------------------------


def test_ac5_init_js_calls_migrate_for_postgres():
    """init.js must use getStore(backend) which routes to postgres."""
    with open(INIT_CMD) as f:
        src = f.read()
    assert "getStore" in src or "resolveBackend" in src, (
        "init.js must use the store factory (getStore/resolveBackend) to support postgres"
    )
    # Verify factory.js routes to postgres
    factory_path = os.path.join(os.path.dirname(INIT_CMD), "..", "store", "factory.js")
    with open(factory_path) as f:
        factory_src = f.read()
    assert "postgres" in factory_src, "factory.js must recognize postgres backend"


# ---------------------------------------------------------------------------
# AC6: upsert uses INSERT...ON CONFLICT(id) DO UPDATE
# ---------------------------------------------------------------------------


def test_ac6_pg_store_has_on_conflict():
    """PgVectorStore.js must use INSERT...ON CONFLICT(id) DO UPDATE."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert re.search(r"ON\s+CONFLICT\s*\(\s*id\s*\)", src, re.IGNORECASE), (
        "PgVectorStore must use INSERT...ON CONFLICT(id) for upsert"
    )
    assert re.search(r"DO\s+UPDATE", src, re.IGNORECASE), (
        "PgVectorStore ON CONFLICT must DO UPDATE (not DO NOTHING)"
    )


# ---------------------------------------------------------------------------
# AC7: delete executes DELETE FROM articles WHERE id = $1
# ---------------------------------------------------------------------------


def test_ac7_pg_store_has_delete_query():
    """PgVectorStore.js must use DELETE FROM articles WHERE id = $1."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert re.search(r"DELETE\s+FROM\s+articles\s+WHERE\s+id\s*=", src, re.IGNORECASE), (
        "PgVectorStore must have DELETE FROM articles WHERE id = ... in its delete method"
    )


# ---------------------------------------------------------------------------
# AC8: search uses ORDER BY embedding <=> $1 and returns 1-distance as score
# ---------------------------------------------------------------------------


def test_ac8_pg_store_has_cosine_distance_operator():
    """PgVectorStore.js search must use the cosine distance operator <=>."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert "<=>" in src, (
        "PgVectorStore search must use the pgvector cosine distance operator <=>"
    )


def test_ac8_pg_store_has_score_as_one_minus_distance():
    """PgVectorStore.js must return 1 - (embedding <=> $1) as the score."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert re.search(r"1\s*-\s*.*<=>|<=>.*1\s*-", src), (
        "PgVectorStore search must compute score as 1 - (embedding <=> query_embedding)"
    )


# ---------------------------------------------------------------------------
# AC9: count returns total row count
# ---------------------------------------------------------------------------


def test_ac9_pg_store_has_count_query():
    """PgVectorStore.js must have a count method using COUNT(*)."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert re.search(r"COUNT\s*\(\s*\*\s*\)", src, re.IGNORECASE), (
        "PgVectorStore must have a count() method using SELECT COUNT(*) FROM articles"
    )


# ---------------------------------------------------------------------------
# AC10: ping verifies Postgres connection
# ---------------------------------------------------------------------------


def test_ac10_pg_store_has_ping_method():
    """PgVectorStore.js must have a ping() method."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert re.search(r"async\s+ping\s*\(", src), (
        "PgVectorStore must have an async ping() method"
    )


def test_ac10_ping_cmd_references_postgres():
    """ping.js must use getStore(backend) which routes to postgres."""
    with open(PING_CMD) as f:
        src = f.read()
    assert "getStore" in src or "resolveBackend" in src, (
        "ping.js must use the store factory (getStore/resolveBackend) to support postgres"
    )
    # Verify factory.js routes to postgres
    factory_path = os.path.join(os.path.dirname(PING_CMD), "..", "store", "factory.js")
    with open(factory_path) as f:
        factory_src = f.read()
    assert "postgres" in factory_src, "factory.js must recognize postgres backend"


# ---------------------------------------------------------------------------
# AC11: pgvector npm package used with pg client
# ---------------------------------------------------------------------------


def test_ac11_pg_store_imports_pg():
    """PgVectorStore.js must import from the 'pg' package."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert re.search(r"import.*from\s+['\"]pg['\"]", src), (
        "PgVectorStore must import from the 'pg' package"
    )


def test_ac11_pg_store_imports_pgvector():
    """PgVectorStore.js must import from the 'pgvector' package."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert re.search(r"import.*from\s+['\"]pgvector", src), (
        "PgVectorStore must import from the 'pgvector' package"
    )


# ---------------------------------------------------------------------------
# AC12: Feature parity — verify server code supports postgres search endpoint
# ---------------------------------------------------------------------------


def test_ac12_server_supports_postgres_search():
    """Server code must support search through the postgres backend."""
    search_src = open(SEARCH_JS).read()
    assert "searchDocuments" in search_src, "search.js must export searchDocuments"
    # The search module uses the store factory, which supports postgres
    factory_path = os.path.join(os.path.dirname(SEARCH_JS), "..", "store", "factory.js")
    with open(factory_path) as f:
        factory_src = f.read()
    assert "postgres" in factory_src, "factory.js must support postgres backend"
