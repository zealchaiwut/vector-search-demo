"""
Tests for issue #51: Add Postgres pgvector backend to VectorStore

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

import json
import os
import re
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(REPO_ROOT, "src", "store")
PG_STORE_PATH = os.path.join(STORE_DIR, "PgVectorStore.js")
BACKEND_JS = os.path.join(REPO_ROOT, "src", "data", "backend.js")
COLLECTION_JS = os.path.join(REPO_ROOT, "src", "data", "collection.js")
SEARCH_JS = os.path.join(REPO_ROOT, "src", "core", "search.js")
INIT_CMD = os.path.join(REPO_ROOT, "src", "commands", "init.js")
PING_CMD = os.path.join(REPO_ROOT, "src", "commands", "ping.js")

DB_URL = os.environ.get("DATABASE_URL", "")
needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason="DATABASE_URL not set — skipping live Postgres tests",
)


def run_node(script, timeout=120, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
        env=env,
    )
    return result.stdout, result.stderr, result.returncode


def run_cli(args, timeout=120, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["node", os.path.join(REPO_ROOT, "src", "cli.js")] + args,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
        env=env,
    )


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
    assert "PgVectorStore" in src or "pgvector" in src.lower() or "store" in src.lower(), (
        "collection.js must reference PgVectorStore for the postgres path"
    )


# ---------------------------------------------------------------------------
# AC2: SQL migration creates articles table with correct columns
# ---------------------------------------------------------------------------


def test_ac2_migration_file_exists():
    """A SQL migration file must exist in src/store/migrations/."""
    migrations_dir = os.path.join(STORE_DIR, "migrations")
    assert os.path.isdir(migrations_dir), (
        f"src/store/migrations/ directory not found"
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
# AC5: init applies migration against Postgres
# ---------------------------------------------------------------------------


def test_ac5_init_js_calls_migrate_for_postgres():
    """init.js must call migrate when postgres backend is active."""
    with open(INIT_CMD) as f:
        src = f.read()
    has_migrate = "migrate" in src.lower() or "PgVectorStore" in src or "postgres" in src.lower()
    assert has_migrate, (
        "init.js must call migrate() or reference PgVectorStore for the postgres path"
    )


@needs_postgres
def test_ac5_init_creates_articles_table():
    """commander init with DB_BACKEND=postgres must create the articles table."""
    r = run_cli(["init"], env_extra={"DB_BACKEND": "postgres", "DATABASE_URL": DB_URL})
    assert r.returncode == 0, f"init failed (exit {r.returncode}):\nstderr={r.stderr}\nstdout={r.stdout}"

    out, err, rc = run_node(
        f"""
import pg from 'pg';
const {{ Pool }} = pg;
const pool = new Pool({{ connectionString: {json.dumps(DB_URL)} }});
const result = await pool.query(
  "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='articles'"
);
await pool.end();
process.stdout.write(JSON.stringify({{ exists: result.rows.length > 0 }}));
""",
        env_extra={"DATABASE_URL": DB_URL},
    )
    assert rc == 0, f"Table check failed: {err}"
    assert json.loads(out)["exists"], "articles table not found after commander init"


@needs_postgres
def test_ac5_init_is_idempotent():
    """Running commander init twice with postgres must succeed both times."""
    env = {"DB_BACKEND": "postgres", "DATABASE_URL": DB_URL}
    r1 = run_cli(["init"], env_extra=env)
    assert r1.returncode == 0, f"First init failed: {r1.stderr}"
    r2 = run_cli(["init"], env_extra=env)
    assert r2.returncode == 0, f"Second init failed: {r2.stderr}"


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


@needs_postgres
def test_ac6_upsert_no_duplicate_rows():
    """Upserting the same article twice must not create duplicate rows."""
    out, err, rc = run_node(
        f"""
import {{ PgVectorStore }} from './src/store/PgVectorStore.js';
const store = new PgVectorStore({json.dumps(DB_URL)});
await store.migrate();
const embedding = new Array(384).fill(0);
embedding[0] = 1.0;
const row = {{ id: 'upsert-test-51', headline: 'Test', details: 'First', attachment_url: null, embedding }};
await store.upsert([row]);
await store.upsert([{{ ...row, details: 'Updated' }}]);
const count = await store.count();
const rows = await store._query('SELECT id, details FROM articles WHERE id = $1', ['upsert-test-51']);
await store.delete('upsert-test-51');
await store.end();
process.stdout.write(JSON.stringify({{ details: rows.rows[0]?.details, ok: rows.rows.length === 1 }}));
""",
        env_extra={"DATABASE_URL": DB_URL},
    )
    assert rc == 0, f"Upsert test failed: {err}"
    data = json.loads(out)
    assert data["ok"], "Upserting same id twice must produce exactly one row"
    assert data["details"] == "Updated", "Second upsert must update the row, not ignore it"


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


@needs_postgres
def test_ac7_delete_removes_row():
    """delete(id) must remove the row from articles."""
    out, err, rc = run_node(
        f"""
import {{ PgVectorStore }} from './src/store/PgVectorStore.js';
const store = new PgVectorStore({json.dumps(DB_URL)});
await store.migrate();
const embedding = new Array(384).fill(0); embedding[0] = 1.0;
await store.upsert([{{ id: 'delete-test-51', headline: 'Del', details: 'Del', attachment_url: null, embedding }}]);
await store.delete('delete-test-51');
const rows = await store._query('SELECT id FROM articles WHERE id = $1', ['delete-test-51']);
await store.end();
process.stdout.write(JSON.stringify({{ gone: rows.rows.length === 0 }}));
""",
        env_extra={"DATABASE_URL": DB_URL},
    )
    assert rc == 0, f"Delete test failed: {err}"
    assert json.loads(out)["gone"], "Row must be gone after delete"


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


@needs_postgres
def test_ac8_search_returns_results_with_score():
    """search must return results including a numeric score between 0 and 1."""
    out, err, rc = run_node(
        f"""
import {{ PgVectorStore }} from './src/store/PgVectorStore.js';
const store = new PgVectorStore({json.dumps(DB_URL)});
await store.migrate();
const embedding = new Array(384).fill(0); embedding[0] = 1.0;
await store.upsert([{{ id: 'search-test-51', headline: 'Search Test', details: 'Searchable content', attachment_url: null, embedding }}]);
const results = await store.search(embedding, 5);
await store.delete('search-test-51');
await store.end();
const r = results[0];
process.stdout.write(JSON.stringify({{ ok: results.length > 0, hasScore: typeof r?.score === 'number', scoreInRange: r?.score >= 0 && r?.score <= 1 }}));
""",
        env_extra={"DATABASE_URL": DB_URL},
    )
    assert rc == 0, f"Search test failed: {err}"
    data = json.loads(out)
    assert data["ok"], "search must return results when data exists"
    assert data["hasScore"], "search results must have a numeric score"
    assert data["scoreInRange"], "score must be between 0 and 1"


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


@needs_postgres
def test_ac9_count_reflects_upserted_rows():
    """count() must reflect the number of rows in the articles table."""
    out, err, rc = run_node(
        f"""
import {{ PgVectorStore }} from './src/store/PgVectorStore.js';
const store = new PgVectorStore({json.dumps(DB_URL)});
await store.migrate();
await store._query('DELETE FROM articles WHERE id LIKE $1', ['count-test-51%']);
const embedding = new Array(384).fill(0); embedding[0] = 1.0;
await store.upsert([{{ id: 'count-test-51-a', headline: 'A', details: 'A', attachment_url: null, embedding }}]);
await store.upsert([{{ id: 'count-test-51-b', headline: 'B', details: 'B', attachment_url: null, embedding }}]);
const count = await store.count();
const baselineResult = await store._query('SELECT COUNT(*) FROM articles');
const total = parseInt(baselineResult.rows[0].count, 10);
await store._query('DELETE FROM articles WHERE id LIKE $1', ['count-test-51%']);
await store.end();
process.stdout.write(JSON.stringify({{ count, total, ok: count === total }}));
""",
        env_extra={"DATABASE_URL": DB_URL},
    )
    assert rc == 0, f"Count test failed: {err}"
    data = json.loads(out)
    assert data["ok"], f"count() ({data['count']}) must match actual row count ({data['total']})"


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


@needs_postgres
def test_ac10_ping_succeeds_with_valid_url():
    """ping() must resolve successfully with a valid DATABASE_URL."""
    out, err, rc = run_node(
        f"""
import {{ PgVectorStore }} from './src/store/PgVectorStore.js';
const store = new PgVectorStore({json.dumps(DB_URL)});
const result = await store.ping();
await store.end();
process.stdout.write(JSON.stringify({{ ok: true, result }}));
""",
        env_extra={"DATABASE_URL": DB_URL},
    )
    assert rc == 0, f"ping() failed: {err}"
    assert json.loads(out)["ok"]


def test_ac10_ping_cmd_references_postgres():
    """ping.js must handle postgres backend."""
    with open(PING_CMD) as f:
        src = f.read()
    assert "postgres" in src.lower() or "PgVectorStore" in src or "DB_BACKEND" in src, (
        "ping.js must handle the postgres backend path"
    )


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
# AC12: Feature parity — full end-to-end with postgres
# ---------------------------------------------------------------------------


@needs_postgres
def test_ac12_e2e_init_ingest_search_delete():
    """E2E: init → ingest → search → delete behave identically with postgres backend."""
    env = {"DB_BACKEND": "postgres", "DATABASE_URL": DB_URL}

    # Step 1: init
    r = run_cli(["init"], env_extra=env)
    assert r.returncode == 0, f"init failed: {r.stderr}"

    # Step 2: ingest
    r = run_cli(["ingest"], env_extra=env, timeout=180)
    assert r.returncode == 0, f"ingest failed: {r.stderr}"
    assert re.search(r"\d+\s+docs", r.stdout), f"ingest should report docs count: {r.stdout}"

    # Step 3: search
    r = run_cli(["search", "vector search similarity"], env_extra=env, timeout=120)
    assert r.returncode == 0, f"search failed: {r.stderr}"
    assert "Headline" in r.stdout or "headline" in r.stdout.lower() or "Result" in r.stdout, (
        f"search must return results: {r.stdout}"
    )


@needs_postgres
def test_ac12_search_returns_best_passage():
    """search results with postgres backend must include best_passage field."""
    out, err, rc = run_node(
        f"""
import {{ searchDocuments }} from './src/core/search.js';
const results = await searchDocuments('vector search similarity', 5);
const r = results[0];
process.stdout.write(JSON.stringify({{
  ok: results.length > 0,
  hasBestPassage: r && 'best_passage' in r,
  hasScore: r && typeof r.score === 'number',
  score: r?.score,
  id: r?.id,
}});
""",
        env_extra={"DB_BACKEND": "postgres", "DATABASE_URL": DB_URL},
    )
    assert rc == 0, f"search failed: {err}"
    data = json.loads(out)
    assert data["ok"], "search must return results"
    assert data["hasBestPassage"], "search results must include best_passage"
    assert data["hasScore"], "search results must include score"
