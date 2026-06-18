"""
Acceptance tests for issue #49: Add in-memory MockStore for zero-database operation

AC1: MockStore lives in src/store and satisfies VectorStore interface: upsert, delete, count, ping, search
AC2: Setting DB_BACKEND=mock selects MockStore; no other env vars or running services required
AC3: On initialization, MockStore automatically seeds itself from the bundled sample article set
AC4: ping() always returns a successful result regardless of store state
AC5: search() ranks by cosine similarity, attaches best_passage to every result
AC6: upsert() adds a new article or replaces an existing one (matched by ID)
AC7: delete() removes the specified article; subsequent search() and count() reflect removal
AC8: count() returns the exact number of articles currently held in memory
AC9: Starting with DB_BACKEND=mock and no Docker produces no connection errors
"""

import json
import os
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(REPO_ROOT, "src", "store")
MOCK_STORE_JS = os.path.join(STORE_DIR, "MockStore.js")
STORE_INDEX_JS = os.path.join(STORE_DIR, "index.js")

MODEL_TIMEOUT = 180  # model download can take time on first run


def _run_node(script, env=None, timeout=MODEL_TIMEOUT):
    """Run a Node.js ESM script and return (stdout, stderr, returncode)."""
    merged_env = {**os.environ}
    # Strip existing DB_BACKEND so each test controls it explicitly
    merged_env.pop("DB_BACKEND", None)
    if env:
        merged_env.update(env)
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=merged_env,
        timeout=timeout,
    )
    return result.stdout, result.stderr, result.returncode


# ---------------------------------------------------------------------------
# AC1: MockStore lives in src/store and satisfies VectorStore interface
# ---------------------------------------------------------------------------

def test_mock_store__files_exist():
    # AC1: src/store/MockStore.js and src/store/index.js exist
    assert os.path.isfile(MOCK_STORE_JS), f"MockStore.js not found at {MOCK_STORE_JS}"
    assert os.path.isfile(STORE_INDEX_JS), f"store/index.js not found at {STORE_INDEX_JS}"


def test_mock_store__has_required_interface_methods():
    # AC1: MockStore exports a class with upsert, delete, count, ping, search
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const methods = ['upsert', 'delete', 'count', 'ping', 'search'];
const missing = methods.filter(m => typeof store[m] !== 'function');
if (missing.length > 0) {
  process.stderr.write('Missing methods: ' + missing.join(', '));
  process.exit(1);
}
process.stdout.write('ok');
"""
    out, err, rc = _run_node(script, timeout=30)
    assert rc == 0, f"Method check failed: {err}"
    assert out.strip() == "ok"


# ---------------------------------------------------------------------------
# AC2: DB_BACKEND=mock selects MockStore via factory
# ---------------------------------------------------------------------------

def test_mock_store__factory_returns_mock_for_db_backend_mock():
    # AC2: getStore() returns MockStore when DB_BACKEND=mock
    script = """
import { getStore } from './src/store/index.js';
const store = await getStore();
if (!store) {
  process.stderr.write('getStore() returned null/undefined');
  process.exit(1);
}
const methods = ['upsert', 'delete', 'count', 'ping', 'search'];
const missing = methods.filter(m => typeof store[m] !== 'function');
if (missing.length > 0) {
  process.stderr.write('Store missing methods: ' + missing.join(', '));
  process.exit(1);
}
process.stdout.write(store.constructor.name);
"""
    out, err, rc = _run_node(script, env={"DB_BACKEND": "mock"}, timeout=30)
    assert rc == 0, f"Factory test failed: {err}"
    assert out.strip() == "MockStore", f"Expected MockStore, got {out.strip()!r}"


def test_mock_store__factory_db_backend_case_insensitive():
    # AC2: DB_BACKEND=MOCK (uppercase) also selects MockStore
    script = """
import { getStore } from './src/store/index.js';
const store = await getStore();
process.stdout.write(store ? store.constructor.name : 'null');
"""
    out, err, rc = _run_node(script, env={"DB_BACKEND": "MOCK"}, timeout=30)
    assert rc == 0, f"Case insensitive test failed: {err}"
    assert out.strip() == "MockStore", f"Expected MockStore, got {out.strip()!r}"


# ---------------------------------------------------------------------------
# AC3: Auto-seeds from bundled sample article set on initialization
# ---------------------------------------------------------------------------

def test_mock_store__auto_seeds_on_first_use():
    # AC3: count() > 0 without any explicit seed call
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const count = await store.count();
process.stdout.write(String(count));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Auto-seed test failed: {err}"
    count = int(out.strip())
    assert count > 0, f"Expected seeded count > 0, got {count}"


def test_mock_store__seed_count_matches_generator_document_count():
    # AC3: count() equals the number of articles in generateDocuments()
    script = """
import { MockStore } from './src/store/MockStore.js';
import { generateDocuments } from './src/data/generator.js';
const store = new MockStore();
const count = await store.count();
const expected = generateDocuments().length;
process.stdout.write(JSON.stringify({ count, expected }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Seed count test failed: {err}"
    data = json.loads(out.strip())
    assert data["count"] == data["expected"], (
        f"count()={data['count']} should equal generateDocuments().length={data['expected']}"
    )


# ---------------------------------------------------------------------------
# AC4: ping() always returns a successful result
# ---------------------------------------------------------------------------

def test_mock_store__ping_returns_success_before_seed():
    # AC4: ping() returns success even before any seeding has occurred
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
// ping() before any other call that would trigger seeding
const result = await store.ping();
process.stdout.write(JSON.stringify(result));
"""
    out, err, rc = _run_node(script, timeout=30)
    assert rc == 0, f"ping() test failed: {err}"
    result = json.loads(out.strip())
    # Accept any truthy success indicator: {ok: true}, {status: "ok"}, etc.
    ok = result.get("ok") is True or result.get("status") in ("ok", "healthy")
    assert ok, f"ping() should return a success indicator, got {result!r}"


def test_mock_store__ping_always_succeeds():
    # AC4: ping() returns success regardless of whether store is seeded
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
// Call ping before and after count() (which triggers seed)
const r1 = await store.ping();
await store.count();
const r2 = await store.ping();
const ok1 = r1.ok === true || r1.status === 'ok';
const ok2 = r2.ok === true || r2.status === 'ok';
process.stdout.write(JSON.stringify({ ok1, ok2 }));
"""
    out, err, rc = _run_node(script, timeout=30)
    assert rc == 0, f"ping() always succeeds test failed: {err}"
    data = json.loads(out.strip())
    assert data["ok1"] and data["ok2"], f"ping() must always succeed: {data}"


# ---------------------------------------------------------------------------
# AC5: search() ranks by cosine similarity, attaches best_passage
# ---------------------------------------------------------------------------

def test_mock_store__search_returns_results_with_best_passage():
    # AC5: each search result includes a non-empty best_passage object
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const results = await store.search('vector similarity search', 5);
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"search() test failed: {err}"
    results = json.loads(out.strip())
    assert len(results) > 0, "Expected at least one search result"
    for r in results:
        assert "best_passage" in r, f"Result missing best_passage: {r}"
        bp = r["best_passage"]
        assert isinstance(bp, dict), f"best_passage should be a dict, got {type(bp)}"
        assert bp.get("text"), f"best_passage.text should be non-empty: {bp}"


def test_mock_store__search_results_ordered_by_descending_score():
    # AC5: results are ranked by descending cosine similarity score
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const results = await store.search('embedding models semantic similarity', 6);
process.stdout.write(JSON.stringify(results.map(r => ({ id: r.id, score: r.score }))));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"search order test failed: {err}"
    items = json.loads(out.strip())
    assert len(items) > 1, "Expected multiple results to check ordering"
    scores = [item["score"] for item in items]
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], (
            f"Scores not sorted descending at index {i}: {scores}"
        )


def test_mock_store__search_returns_standard_result_fields():
    # AC5: each result has id, headline, details, score, best_passage
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const results = await store.search('vector search', 3);
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"search fields test failed: {err}"
    results = json.loads(out.strip())
    assert len(results) > 0
    for r in results:
        for field in ("id", "headline", "details", "score", "best_passage"):
            assert field in r, f"Result missing field '{field}': {r}"
        assert isinstance(r["score"], (int, float)), f"score should be numeric: {r['score']}"


# ---------------------------------------------------------------------------
# AC6: upsert() adds new or replaces existing (matched by ID)
# ---------------------------------------------------------------------------

def test_mock_store__upsert_new_article_increases_count():
    # AC6: count() increases by exactly 1 after upserting a new article
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const before = await store.count();
await store.upsert({
  id: 'test-upsert-new-unique-49',
  headline: 'Unique Test Article for Upsert',
  details: 'This brand new article discusses machine learning pipelines and neural network architectures in detail.'
});
const after = await store.count();
process.stdout.write(JSON.stringify({ before, after }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"upsert new article test failed: {err}"
    data = json.loads(out.strip())
    assert data["after"] == data["before"] + 1, (
        f"count() should increase by 1 after upsert: before={data['before']}, after={data['after']}"
    )


def test_mock_store__upsert_existing_id_replaces_and_keeps_count():
    # AC6: upserting an article with an existing ID replaces it; count stays same
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const before = await store.count();
// article-001 exists in the seed data
await store.upsert({
  id: 'article-001',
  headline: 'Updated Vector Search Introduction',
  details: 'This is an updated version about vector similarity and retrieval augmented generation systems.'
});
const after = await store.count();
process.stdout.write(JSON.stringify({ before, after }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"upsert replace test failed: {err}"
    data = json.loads(out.strip())
    assert data["after"] == data["before"], (
        f"count() should not change when upserting existing ID: before={data['before']}, after={data['after']}"
    )


def test_mock_store__upserted_article_appears_in_search():
    # AC6: a freshly upserted article is discoverable via search()
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
await store.upsert({
  id: 'test-upsert-searchable-49',
  headline: 'Quantum Cryptography and Post-Quantum Security',
  details: 'Quantum cryptography applies quantum mechanics principles to secure communications. Post-quantum algorithms are designed to resist attacks from quantum computers using lattice-based techniques.'
});
const results = await store.search('quantum cryptography security', 10);
const found = results.some(r => r.id === 'test-upsert-searchable-49');
process.stdout.write(JSON.stringify({ found, resultCount: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"upsert search test failed: {err}"
    data = json.loads(out.strip())
    assert data["found"], (
        f"Upserted article should appear in search results: {data}"
    )


# ---------------------------------------------------------------------------
# AC7: delete() removes article; subsequent search() and count() reflect it
# ---------------------------------------------------------------------------

def test_mock_store__delete_decreases_count():
    # AC7: count() decreases by 1 after deleting a seeded article
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const before = await store.count();
const deleted = await store.delete('article-001');
const after = await store.count();
process.stdout.write(JSON.stringify({ before, after, deleted }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"delete count test failed: {err}"
    data = json.loads(out.strip())
    assert data["deleted"] is True, "delete() should return true for existing article"
    assert data["after"] == data["before"] - 1, (
        f"count() should decrease by 1 after delete: before={data['before']}, after={data['after']}"
    )


def test_mock_store__deleted_article_absent_from_search():
    # AC7: deleted article does not appear in subsequent search() results
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const before = await store.search('vector search embedding', 10);
const foundBefore = before.some(r => r.id === 'article-001');
await store.delete('article-001');
const after = await store.search('vector search embedding', 10);
const foundAfter = after.some(r => r.id === 'article-001');
process.stdout.write(JSON.stringify({ foundBefore, foundAfter }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"delete search test failed: {err}"
    data = json.loads(out.strip())
    assert data["foundBefore"], "article-001 should appear in search before deletion"
    assert not data["foundAfter"], "article-001 should NOT appear in search after deletion"


def test_mock_store__delete_nonexistent_returns_false():
    # AC7: delete() returns false for a nonexistent article ID
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const result = await store.delete('nonexistent-article-xyz-49');
process.stdout.write(JSON.stringify(result));
"""
    out, err, rc = _run_node(script, timeout=30)
    assert rc == 0, f"delete nonexistent test failed: {err}"
    result = json.loads(out.strip())
    assert result is False, f"delete() nonexistent should return false, got {result!r}"


# ---------------------------------------------------------------------------
# AC8: count() returns exact number of articles in memory
# ---------------------------------------------------------------------------

def test_mock_store__count_exact_at_seed():
    # AC8: count() exactly matches the number of seed articles
    script = """
import { MockStore } from './src/store/MockStore.js';
import { generateDocuments } from './src/data/generator.js';
const store = new MockStore();
const count = await store.count();
const seedCount = generateDocuments().length;
process.stdout.write(JSON.stringify({ count, seedCount }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"count exact test failed: {err}"
    data = json.loads(out.strip())
    assert data["count"] == data["seedCount"], (
        f"count()={data['count']} should exactly equal seed count={data['seedCount']}"
    )


def test_mock_store__count_tracks_upsert_and_delete_sequence():
    # AC8: count accurately reflects a sequence of upsert and delete operations
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const seed = await store.count();
await store.upsert({ id: 'ac8-test-alpha', headline: 'Test Alpha', details: 'Distributed consensus algorithms and Raft protocol for fault-tolerant systems in production environments.' });
await store.upsert({ id: 'ac8-test-beta', headline: 'Test Beta', details: 'Graph databases and knowledge graphs for semantic reasoning over structured relational data.' });
const after2Upserts = await store.count();
await store.delete('ac8-test-alpha');
const afterDelete = await store.count();
process.stdout.write(JSON.stringify({ seed, after2Upserts, afterDelete }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"count sequence test failed: {err}"
    data = json.loads(out.strip())
    assert data["after2Upserts"] == data["seed"] + 2, (
        f"After 2 upserts, count should be seed+2: {data}"
    )
    assert data["afterDelete"] == data["seed"] + 1, (
        f"After 1 delete, count should be seed+1: {data}"
    )


# ---------------------------------------------------------------------------
# AC9: DB_BACKEND=mock with no Docker produces no connection errors
# ---------------------------------------------------------------------------

def test_mock_store__no_connection_errors_with_mock_backend():
    # AC9: using getStore() with DB_BACKEND=mock produces no errors (no Docker needed)
    script = """
import { getStore } from './src/store/index.js';
let errorCaught = null;
try {
  const store = await getStore();
  await store.ping();
  await store.count();
} catch (err) {
  errorCaught = err.message;
}
process.stdout.write(JSON.stringify({ error: errorCaught }));
"""
    out, err, rc = _run_node(script, env={"DB_BACKEND": "mock"})
    assert rc == 0, f"No-docker test exited non-zero: rc={rc}, stderr={err}"
    data = json.loads(out.strip())
    assert data["error"] is None, (
        f"Expected no connection errors with DB_BACKEND=mock, got: {data['error']}"
    )


def test_mock_store__no_unhandled_rejections_on_startup():
    # AC9: process exits cleanly with DB_BACKEND=mock (no unhandled promise rejections)
    script = """
import { getStore } from './src/store/index.js';
const store = await getStore();
const count = await store.count();
const pingResult = await store.ping();
process.stdout.write(JSON.stringify({ count, pingOk: pingResult.ok === true || pingResult.status === 'ok' }));
"""
    out, err, rc = _run_node(script, env={"DB_BACKEND": "mock"})
    assert rc == 0, f"Process should exit cleanly: rc={rc}, stderr={err}"
    # No "UnhandledPromiseRejection" in stderr
    assert "UnhandledPromiseRejection" not in err, (
        f"Unhandled promise rejection detected: {err}"
    )
    data = json.loads(out.strip())
    assert data["pingOk"] is True
    assert data["count"] > 0
