"""
Acceptance tests for issue #48: Introduce swappable VectorStore interface over Milvus

AC1 - A VectorStore interface is defined in src/store with methods:
      init/migrate, upsert(article), delete(id), search(queryVector, k), count(), ping()
AC2 - MilvusStore implements VectorStore and is the sole file that imports the Milvus SDK;
      no Milvus SDK import paths appear in src/search, src/ingest, or src/commands
AC3 - A backend factory in src/store reads the DB_BACKEND env var
      (accepted: milvus, postgres, mock; default: milvus), throws on unrecognised values
AC4 - src/search, src/ingest, and src/commands depend only on the VectorStore interface
AC5 - With DB_BACKEND=milvus (or unset), all existing behaviour is preserved
AC6 - DB_BACKEND=mock returns a functional in-memory implementation (no live DB required)
AC7 - DB_BACKEND=postgres is accepted without error; methods return "not implemented" errors
"""

import os
import re
import json
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(REPO_ROOT, "src", "store")
MILVUS_STORE_PATH = os.path.join(STORE_DIR, "milvus-store.js")
MOCK_STORE_PATH = os.path.join(STORE_DIR, "mock-store.js")
POSTGRES_STORE_PATH = os.path.join(STORE_DIR, "postgres-store.js")
FACTORY_PATH = os.path.join(STORE_DIR, "factory.js")
STORE_INDEX_PATH = os.path.join(STORE_DIR, "index.js")
COLLECTION_PATH = os.path.join(REPO_ROOT, "src", "data", "collection.js")
SEARCH_PATH = os.path.join(REPO_ROOT, "src", "core", "search.js")
PING_CMD_PATH = os.path.join(REPO_ROOT, "src", "commands", "ping.js")
COMMANDS_DIR = os.path.join(REPO_ROOT, "src", "commands")

MILVUS_HOST = os.environ.get("MILVUS_HOST", "localhost")
MILVUS_PORT = os.environ.get("MILVUS_PORT", "19530")

needs_milvus = pytest.mark.skipif(
    not os.environ.get("MILVUS_HOST"),
    reason="MILVUS_HOST not set — skipping live Milvus tests",
)


def run_node(script, timeout=60, env_extra=None):
    env = os.environ.copy()
    # Strip DATA_BACKEND so legacy env doesn't interfere unless test sets DB_BACKEND
    env.pop("DATA_BACKEND", None)
    env.pop("DB_BACKEND", None)
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


# ---------------------------------------------------------------------------
# AC1: src/store directory and VectorStore interface
# ---------------------------------------------------------------------------


def test_store_directory_exists():
    """AC1: src/store directory must exist."""
    assert os.path.isdir(STORE_DIR), f"src/store directory not found at {STORE_DIR}"


def test_store_index_exports_getStore():
    """AC1: src/store/index.js must export a getStore function."""
    assert os.path.isfile(STORE_INDEX_PATH), f"src/store/index.js not found"
    stdout, stderr, rc = run_node(
        f"""
import {{ getStore }} from '{STORE_INDEX_PATH}';
if (typeof getStore !== 'function') throw new Error('getStore is not a function');
process.stdout.write(JSON.stringify({{ ok: true }}));
""",
        env_extra={"DB_BACKEND": "mock"},
    )
    assert rc == 0, f"Failed: {stderr}"
    assert json.loads(stdout)["ok"] is True


def test_mock_store_has_required_methods():
    """AC1: VectorStore (via MockStore) must expose init, upsert, delete, search, count, ping."""
    stdout, stderr, rc = run_node(
        f"""
import {{ getStore }} from '{STORE_INDEX_PATH}';
const store = getStore();
const required = ['init', 'upsert', 'delete', 'search', 'count', 'ping'];
const missing = required.filter(m => typeof store[m] !== 'function');
if (missing.length > 0) throw new Error('Missing methods: ' + missing.join(', '));
process.stdout.write(JSON.stringify({{ ok: true }}));
""",
        env_extra={"DB_BACKEND": "mock"},
    )
    assert rc == 0, f"Failed: {stderr}"
    assert json.loads(stdout)["ok"] is True


def test_mock_store_has_migrate_method():
    """AC1: VectorStore must expose migrate (may alias init)."""
    stdout, stderr, rc = run_node(
        f"""
import {{ getStore }} from '{STORE_INDEX_PATH}';
const store = getStore();
if (typeof store.migrate !== 'function' && typeof store.init !== 'function') {{
  throw new Error('Neither migrate nor init found on store');
}}
process.stdout.write(JSON.stringify({{ ok: true }}));
""",
        env_extra={"DB_BACKEND": "mock"},
    )
    assert rc == 0, f"Failed: {stderr}"
    assert json.loads(stdout)["ok"] is True


# ---------------------------------------------------------------------------
# AC2: MilvusStore is sole Milvus SDK importer
# ---------------------------------------------------------------------------


def test_milvus_store_file_exists():
    """AC2: src/store/milvus-store.js must exist."""
    assert os.path.isfile(MILVUS_STORE_PATH), f"milvus-store.js not found at {MILVUS_STORE_PATH}"


def test_milvus_store_imports_sdk():
    """AC2: milvus-store.js must import @zilliz/milvus2-sdk-node."""
    with open(MILVUS_STORE_PATH) as f:
        source = f.read()
    assert "@zilliz/milvus2-sdk-node" in source, (
        "milvus-store.js must reference @zilliz/milvus2-sdk-node"
    )


def test_no_milvus_sdk_import_in_commands():
    """AC2/AC4: src/commands/*.js must not import @zilliz/milvus2-sdk-node."""
    violations = []
    for fname in os.listdir(COMMANDS_DIR):
        if not fname.endswith(".js"):
            continue
        fpath = os.path.join(COMMANDS_DIR, fname)
        with open(fpath) as f:
            source = f.read()
        if "@zilliz/milvus2-sdk-node" in source:
            violations.append(fname)
    assert not violations, (
        f"Milvus SDK imports found in src/commands/: {violations}"
    )


def test_no_milvus_sdk_import_in_core_search():
    """AC2/AC4: src/core/search.js must not import @zilliz/milvus2-sdk-node."""
    with open(SEARCH_PATH) as f:
        source = f.read()
    assert "@zilliz/milvus2-sdk-node" not in source, (
        "src/core/search.js must not import @zilliz/milvus2-sdk-node"
    )


def test_no_milvus_sdk_import_in_collection():
    """AC2/AC4: src/data/collection.js must not import @zilliz/milvus2-sdk-node."""
    with open(COLLECTION_PATH) as f:
        source = f.read()
    assert "@zilliz/milvus2-sdk-node" not in source, (
        "src/data/collection.js must not import @zilliz/milvus2-sdk-node"
    )


def test_mock_store_no_milvus_sdk_import():
    """AC2: mock-store.js must not import @zilliz/milvus2-sdk-node."""
    with open(MOCK_STORE_PATH) as f:
        source = f.read()
    assert "@zilliz/milvus2-sdk-node" not in source, (
        "mock-store.js must not import @zilliz/milvus2-sdk-node"
    )


def test_postgres_store_no_milvus_sdk_import():
    """AC2: postgres-store.js must not import @zilliz/milvus2-sdk-node."""
    with open(POSTGRES_STORE_PATH) as f:
        source = f.read()
    assert "@zilliz/milvus2-sdk-node" not in source, (
        "postgres-store.js must not import @zilliz/milvus2-sdk-node"
    )


# ---------------------------------------------------------------------------
# AC3: Factory reads DB_BACKEND env var
# ---------------------------------------------------------------------------


def test_factory_file_exists():
    """AC3: src/store/factory.js must exist."""
    assert os.path.isfile(FACTORY_PATH), f"factory.js not found at {FACTORY_PATH}"


def test_factory_default_is_milvus_class():
    """AC3: default (unset DB_BACKEND) returns a MilvusStore instance."""
    stdout, stderr, rc = run_node(
        f"""
import {{ getStore }} from '{STORE_INDEX_PATH}';
const store = getStore();
process.stdout.write(JSON.stringify({{ name: store.constructor.name }}));
""",
        env_extra={},  # DB_BACKEND not set → default milvus
    )
    assert rc == 0, f"Failed: {stderr}"
    data = json.loads(stdout)
    assert "milvus" in data["name"].lower(), (
        f"Default store should be MilvusStore, got: {data['name']}"
    )


def test_factory_mock_backend():
    """AC3: DB_BACKEND=mock returns a MockStore instance."""
    stdout, stderr, rc = run_node(
        f"""
import {{ getStore }} from '{STORE_INDEX_PATH}';
const store = getStore();
process.stdout.write(JSON.stringify({{ name: store.constructor.name }}));
""",
        env_extra={"DB_BACKEND": "mock"},
    )
    assert rc == 0, f"Failed: {stderr}"
    data = json.loads(stdout)
    assert "mock" in data["name"].lower(), (
        f"DB_BACKEND=mock should return MockStore, got: {data['name']}"
    )


def test_factory_postgres_backend():
    """AC3: DB_BACKEND=postgres returns a PostgresStore instance."""
    stdout, stderr, rc = run_node(
        f"""
import {{ getStore }} from '{STORE_INDEX_PATH}';
const store = getStore();
process.stdout.write(JSON.stringify({{ name: store.constructor.name }}));
""",
        env_extra={"DB_BACKEND": "postgres"},
    )
    assert rc == 0, f"Failed: {stderr}"
    data = json.loads(stdout)
    assert "postgres" in data["name"].lower(), (
        f"DB_BACKEND=postgres should return PostgresStore, got: {data['name']}"
    )


def test_factory_invalid_backend_throws():
    """AC3: Unknown DB_BACKEND throws a descriptive error."""
    stdout, stderr, rc = run_node(
        f"""
try {{
  const {{ getStore }} = await import('{STORE_INDEX_PATH}?t=' + Date.now());
  const store = getStore();
  process.stdout.write(JSON.stringify({{ threw: false }}));
}} catch (err) {{
  process.stdout.write(JSON.stringify({{ threw: true, message: err.message }}));
}}
""",
        env_extra={"DB_BACKEND": "invalid_value"},
    )
    assert rc == 0, f"Script itself failed: {stderr}"
    data = json.loads(stdout)
    assert data["threw"], "Factory must throw for unrecognised DB_BACKEND"
    assert "invalid_value" in data["message"] or "unknown" in data["message"].lower() or "unrecognised" in data["message"].lower() or "unrecognized" in data["message"].lower(), (
        f"Error message should name the bad value. Got: {data['message']!r}"
    )


def test_factory_milvus_explicit():
    """AC3: DB_BACKEND=milvus explicitly returns MilvusStore."""
    stdout, stderr, rc = run_node(
        f"""
import {{ getStore }} from '{STORE_INDEX_PATH}';
const store = getStore();
process.stdout.write(JSON.stringify({{ name: store.constructor.name }}));
""",
        env_extra={"DB_BACKEND": "milvus"},
    )
    assert rc == 0, f"Failed: {stderr}"
    data = json.loads(stdout)
    assert "milvus" in data["name"].lower(), (
        f"DB_BACKEND=milvus should return MilvusStore, got: {data['name']}"
    )


# ---------------------------------------------------------------------------
# AC6: DB_BACKEND=mock is a functional in-memory implementation
# ---------------------------------------------------------------------------


def test_mock_store_ping_no_live_db():
    """AC6: MockStore.ping() works without a live database connection."""
    stdout, stderr, rc = run_node(
        f"""
import {{ getStore }} from '{STORE_INDEX_PATH}';
const store = getStore();
const result = await store.ping();
if (typeof result !== 'string') throw new Error('ping() must return a string');
process.stdout.write(JSON.stringify({{ ok: true, result }}));
""",
        env_extra={"DB_BACKEND": "mock"},
    )
    assert rc == 0, f"MockStore.ping() failed: {stderr}"
    data = json.loads(stdout)
    assert data["ok"] is True


def test_mock_store_init_no_live_db():
    """AC6: MockStore.init() works without a live database connection."""
    stdout, stderr, rc = run_node(
        f"""
import {{ getStore }} from '{STORE_INDEX_PATH}';
const store = getStore();
await store.init();
process.stdout.write(JSON.stringify({{ ok: true }}));
""",
        env_extra={"DB_BACKEND": "mock"},
    )
    assert rc == 0, f"MockStore.init() failed: {stderr}"
    assert json.loads(stdout)["ok"] is True


def test_mock_store_upsert_and_count():
    """AC6: MockStore upsert increases count."""
    stdout, stderr, rc = run_node(
        f"""
import {{ getStore }} from '{STORE_INDEX_PATH}';
const store = getStore();
await store.init();
const countBefore = await store.count();
await store.upsert([{{
  id: 'art-1:0',
  headline: 'Test Article',
  details: 'Some details about the test article.',
  attachment_url: '',
  embedding: new Array(384).fill(0.1),
}}]);
const countAfter = await store.count();
process.stdout.write(JSON.stringify({{ countBefore, countAfter }}));
""",
        env_extra={"DB_BACKEND": "mock"},
    )
    assert rc == 0, f"MockStore upsert/count failed: {stderr}"
    data = json.loads(stdout)
    assert data["countAfter"] > data["countBefore"], (
        f"Count should increase after upsert. Before={data['countBefore']}, After={data['countAfter']}"
    )


def test_mock_store_search_returns_results():
    """AC6: MockStore.search() returns ranked results from in-memory data."""
    stdout, stderr, rc = run_node(
        f"""
import {{ getStore }} from '{STORE_INDEX_PATH}';
const store = getStore();
await store.init();

// Insert a row with a known embedding
const embedding = new Array(384).fill(0);
embedding[0] = 1.0;  // unit vector in dim 0

await store.upsert([{{
  id: 'art-search-1:0',
  headline: 'Search Test',
  details: 'Article for search test.',
  attachment_url: '',
  embedding,
}}]);

// Search with a similar query vector
const queryVector = new Array(384).fill(0);
queryVector[0] = 1.0;

const results = await store.search(queryVector, 5);
process.stdout.write(JSON.stringify({{ count: results.length, hasScore: results.length > 0 && 'score' in results[0] }}));
""",
        env_extra={"DB_BACKEND": "mock"},
    )
    assert rc == 0, f"MockStore.search() failed: {stderr}"
    data = json.loads(stdout)
    assert data["count"] >= 1, f"Expected at least 1 result, got {data['count']}"
    assert data["hasScore"], "Search results must have a score field"


def test_mock_store_delete():
    """AC6: MockStore.delete() removes the article from in-memory store."""
    stdout, stderr, rc = run_node(
        f"""
import {{ getStore }} from '{STORE_INDEX_PATH}';
const store = getStore();
await store.init();

await store.upsert([{{
  id: 'del-art-1:0',
  headline: 'To Delete',
  details: 'Will be deleted.',
  attachment_url: '',
  embedding: new Array(384).fill(0.1),
}}]);

const countBefore = await store.count();
const deleted = await store.delete('del-art-1');
const countAfter = await store.count();

process.stdout.write(JSON.stringify({{ deleted, countBefore, countAfter }}));
""",
        env_extra={"DB_BACKEND": "mock"},
    )
    assert rc == 0, f"MockStore.delete() failed: {stderr}"
    data = json.loads(stdout)
    assert data["deleted"] is True, "delete() should return true for existing article"
    assert data["countAfter"] < data["countBefore"], "Count should decrease after delete"


def test_mock_store_delete_nonexistent_returns_false():
    """AC6: MockStore.delete() returns false for non-existent article."""
    stdout, stderr, rc = run_node(
        f"""
import {{ getStore }} from '{STORE_INDEX_PATH}';
const store = getStore();
await store.init();
const deleted = await store.delete('nonexistent-article-id-99');
process.stdout.write(JSON.stringify({{ deleted }}));
""",
        env_extra={"DB_BACKEND": "mock"},
    )
    assert rc == 0, f"MockStore.delete() failed: {stderr}"
    data = json.loads(stdout)
    assert data["deleted"] is False, "delete() should return false for non-existent article"


# ---------------------------------------------------------------------------
# AC7: DB_BACKEND=postgres is accepted; methods return "not implemented" errors
# ---------------------------------------------------------------------------


def test_postgres_store_is_accepted():
    """AC7: DB_BACKEND=postgres is accepted without error during factory creation."""
    stdout, stderr, rc = run_node(
        f"""
import {{ getStore }} from '{STORE_INDEX_PATH}';
const store = getStore();
process.stdout.write(JSON.stringify({{ ok: true, name: store.constructor.name }}));
""",
        env_extra={"DB_BACKEND": "postgres"},
    )
    assert rc == 0, f"DB_BACKEND=postgres should not throw on store creation: {stderr}"
    data = json.loads(stdout)
    assert data["ok"] is True


def test_postgres_store_init_throws_not_implemented():
    """AC7: PostgresStore.init() throws a descriptive 'not implemented' error."""
    stdout, stderr, rc = run_node(
        f"""
import {{ getStore }} from '{STORE_INDEX_PATH}';
const store = getStore();
try {{
  await store.init();
  process.stdout.write(JSON.stringify({{ threw: false }}));
}} catch (err) {{
  process.stdout.write(JSON.stringify({{ threw: true, message: err.message }}));
}}
""",
        env_extra={"DB_BACKEND": "postgres"},
    )
    assert rc == 0, f"Script failed: {stderr}"
    data = json.loads(stdout)
    assert data["threw"], "PostgresStore.init() must throw"
    assert "not implemented" in data["message"].lower() or "not_implemented" in data["message"].lower(), (
        f"Error should say 'not implemented'. Got: {data['message']!r}"
    )


def test_postgres_store_search_throws_not_implemented():
    """AC7: PostgresStore.search() throws a descriptive 'not implemented' error."""
    stdout, stderr, rc = run_node(
        f"""
import {{ getStore }} from '{STORE_INDEX_PATH}';
const store = getStore();
try {{
  await store.search(new Array(384).fill(0), 5);
  process.stdout.write(JSON.stringify({{ threw: false }}));
}} catch (err) {{
  process.stdout.write(JSON.stringify({{ threw: true, message: err.message }}));
}}
""",
        env_extra={"DB_BACKEND": "postgres"},
    )
    assert rc == 0, f"Script failed: {stderr}"
    data = json.loads(stdout)
    assert data["threw"], "PostgresStore.search() must throw"
    assert "not implemented" in data["message"].lower() or "not_implemented" in data["message"].lower(), (
        f"Error should say 'not implemented'. Got: {data['message']!r}"
    )


# ---------------------------------------------------------------------------
# AC4: ping command uses VectorStore interface
# ---------------------------------------------------------------------------


def test_ping_command_no_direct_milvus_import():
    """AC4: src/commands/ping.js must not import Milvus SDK or milvus/client directly."""
    with open(PING_CMD_PATH) as f:
        source = f.read()
    assert "@zilliz/milvus2-sdk-node" not in source, (
        "ping.js must not import @zilliz/milvus2-sdk-node"
    )
    # Should not import from milvus/client module (should use store instead)
    assert "milvus/client" not in source, (
        "ping.js must not import from ../milvus/client — use getStore() instead"
    )


# ---------------------------------------------------------------------------
# Live Milvus tests (AC5)
# ---------------------------------------------------------------------------


@needs_milvus
def test_milvus_store_ping_live():
    """AC5: MilvusStore.ping() returns a version string with live Milvus."""
    stdout, stderr, rc = run_node(
        f"""
import {{ getStore }} from '{STORE_INDEX_PATH}';
const store = getStore();
const version = await store.ping();
if (typeof version !== 'string' || !version.trim()) {{
  throw new Error('ping() must return a non-empty string');
}}
process.stdout.write(JSON.stringify({{ version }}));
""",
        env_extra={"DB_BACKEND": "milvus", "MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
        timeout=30,
    )
    assert rc == 0, f"MilvusStore.ping() failed: {stderr}"
    data = json.loads(stdout)
    assert data["version"], f"ping() returned empty version: {data['version']!r}"


@needs_milvus
def test_milvus_store_upsert_search_delete_round_trip():
    """AC5: MilvusStore upsert → search → delete round trip."""
    stdout, stderr, rc = run_node(
        f"""
import {{ getStore }} from '{STORE_INDEX_PATH}';
import {{ createEmbedder }} from './src/embeddings/index.js';

const phrase = 'vectorstore interface round trip test phrase unique beacon 48';
const articleId = 'rt-store-48-' + Math.random().toString(36).slice(2);
const embedder = await createEmbedder();
const [embedding] = await embedder.embed([phrase]);

const store = getStore();
await store.init();
await store.upsert([{{
  id: articleId + ':0',
  headline: 'VectorStore Round Trip Test #48',
  details: phrase,
  attachment_url: '',
  embedding,
}}]);

const results = await store.search(embedding, 10);
const found = results.some(r => r.id === articleId || r.id === articleId + ':0' || r.id.startsWith(articleId));

await store.delete(articleId);
process.stdout.write(JSON.stringify({{ found, count: results.length }}));
""",
        timeout=180,
        env_extra={"DB_BACKEND": "milvus", "MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
    )
    assert rc == 0, f"Round trip test failed: {stderr}"
    data = json.loads(stdout)
    assert data["found"], (
        f"Ingested article not found via store.search(). Results count: {data.get('count')}"
    )
