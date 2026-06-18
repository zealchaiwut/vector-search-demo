"""
Tests for issue #49: Add in-memory MockStore for zero-database operation

Acceptance Criteria:
AC1: MockStore lives in src/store and satisfies VectorStore interface: upsert, delete, count, ping, search
AC2: Setting DB_BACKEND=mock selects MockStore; no other env vars or running services required
AC3: On initialization, MockStore automatically seeds itself from bundled sample articles
AC4: ping() always returns success regardless of store state
AC5: search() ranks by cosine similarity, attaches best_passage to every result
AC6: upsert() adds new or replaces existing (matched by ID)
AC7: delete() removes article; search() and count() reflect removal
AC8: count() returns exact number of articles in memory
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
    merged_env.pop("DB_BACKEND", None)  # Strip existing to test explicitly
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
# AC1: MockStore exists and has required interface methods
# ---------------------------------------------------------------------------

def test_add_in_memory_mockstore__files_exist():
    """AC1: MockStore.js and index.js exist in src/store."""
    assert os.path.isfile(MOCK_STORE_JS), f"MockStore.js not found at {MOCK_STORE_JS}"
    assert os.path.isfile(STORE_INDEX_JS), f"index.js not found at {STORE_INDEX_JS}"


def test_add_in_memory_mockstore__class_has_interface_methods():
    """AC1: MockStore class has all required methods."""
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const required = ['upsert', 'delete', 'count', 'ping', 'search'];
const missing = required.filter(m => typeof store[m] !== 'function');
if (missing.length > 0) {
  process.stderr.write('Missing: ' + missing.join(', '));
  process.exit(1);
}
process.stdout.write('ok');
"""
    out, err, rc = _run_node(script, timeout=30)
    assert rc == 0, f"Method check failed: {err}"
    assert out.strip() == "ok"


# ---------------------------------------------------------------------------
# AC2: DB_BACKEND=mock selects MockStore
# ---------------------------------------------------------------------------

def test_add_in_memory_mockstore__factory_returns_mockstore():
    """AC2: index.js getStore() returns MockStore when DB_BACKEND=mock."""
    script = """
import { getStore } from './src/store/index.js';
const store = await getStore();
if (!store) {
  process.stderr.write('getStore() returned null');
  process.exit(1);
}
process.stdout.write(store.constructor.name);
"""
    out, err, rc = _run_node(script, env={"DB_BACKEND": "mock"}, timeout=30)
    assert rc == 0, f"Factory test failed: {err}"
    assert out.strip() == "MockStore", f"Expected MockStore, got {out.strip()!r}"


def test_add_in_memory_mockstore__factory_case_insensitive():
    """AC2: DB_BACKEND=MOCK (uppercase) also selects MockStore."""
    script = """
import { getStore } from './src/store/index.js';
const store = await getStore();
process.stdout.write(store ? store.constructor.name : 'null');
"""
    out, err, rc = _run_node(script, env={"DB_BACKEND": "MOCK"}, timeout=30)
    assert rc == 0
    assert out.strip() == "MockStore"


# ---------------------------------------------------------------------------
# AC3: Auto-seeds from bundled sample article set
# ---------------------------------------------------------------------------

def test_add_in_memory_mockstore__auto_seeds_on_first_use():
    """AC3: count() > 0 without explicit seed call."""
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


def test_add_in_memory_mockstore__seed_count_equals_sample_articles():
    """AC3: count() equals the number of articles in generateDocuments()."""
    script = """
import { MockStore } from './src/store/MockStore.js';
import { generateDocuments } from './src/data/generator.js';
const store = new MockStore();
const count = await store.count();
const expected = generateDocuments().length;
process.stdout.write(JSON.stringify({ count, expected }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0
    data = json.loads(out.strip())
    assert data["count"] == data["expected"], (
        f"count()={data['count']} should equal sample count={data['expected']}"
    )


# ---------------------------------------------------------------------------
# AC4: ping() always succeeds
# ---------------------------------------------------------------------------

def test_add_in_memory_mockstore__ping_succeeds_before_seed():
    """AC4: ping() returns success even before seeding."""
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const result = await store.ping();
process.stdout.write(JSON.stringify(result));
"""
    out, err, rc = _run_node(script, timeout=30)
    assert rc == 0, f"ping test failed: {err}"
    result = json.loads(out.strip())
    assert result.get("ok") is True, f"ping() should return {{ok: true}}, got {result!r}"


def test_add_in_memory_mockstore__ping_always_succeeds():
    """AC4: ping() returns success before and after seeding."""
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const r1 = await store.ping();
await store.count();  // triggers seed
const r2 = await store.ping();
process.stdout.write(JSON.stringify({ ok1: r1.ok === true, ok2: r2.ok === true }));
"""
    out, err, rc = _run_node(script, timeout=30)
    assert rc == 0
    data = json.loads(out.strip())
    assert data["ok1"] and data["ok2"]


# ---------------------------------------------------------------------------
# AC5: search() ranks by cosine similarity with best_passage
# ---------------------------------------------------------------------------

def test_add_in_memory_mockstore__search_returns_best_passage():
    """AC5: Every search result includes a non-empty best_passage object."""
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const results = await store.search('vector similarity search', 5);
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"search test failed: {err}"
    results = json.loads(out.strip())
    assert len(results) > 0, "Expected at least one result"
    for r in results:
        assert "best_passage" in r, f"Result missing best_passage: {r}"
        bp = r["best_passage"]
        assert bp.get("text"), f"best_passage.text should be non-empty: {bp}"
        assert "context" in bp, f"best_passage missing context: {bp}"


def test_add_in_memory_mockstore__search_ranked_by_descending_score():
    """AC5: Results are ranked by descending cosine similarity score."""
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const results = await store.search('embedding models semantic similarity', 6);
process.stdout.write(JSON.stringify(results.map(r => ({ id: r.id, score: r.score }))));
"""
    out, err, rc = _run_node(script)
    assert rc == 0
    items = json.loads(out.strip())
    assert len(items) > 1
    scores = [item["score"] for item in items]
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], f"Scores not descending: {scores}"


def test_add_in_memory_mockstore__search_result_structure():
    """AC5: Each result has required fields: id, headline, details, score, best_passage."""
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const results = await store.search('vector search', 3);
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = _run_node(script)
    assert rc == 0
    results = json.loads(out.strip())
    assert len(results) > 0
    for r in results:
        for field in ("id", "headline", "details", "score", "best_passage"):
            assert field in r, f"Missing field {field}: {r}"
        assert isinstance(r["score"], (int, float))


# ---------------------------------------------------------------------------
# AC6: upsert() adds new or replaces existing
# ---------------------------------------------------------------------------

def test_add_in_memory_mockstore__upsert_new_increases_count():
    """AC6: count() increases by 1 after upserting a new article."""
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const before = await store.count();
await store.upsert({
  id: 'test-upsert-new-unique-49',
  headline: 'Unique Test Article',
  details: 'This discusses machine learning pipelines and neural network architectures in detail.'
});
const after = await store.count();
process.stdout.write(JSON.stringify({ before, after }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0
    data = json.loads(out.strip())
    assert data["after"] == data["before"] + 1, (
        f"count should increase by 1: {data}"
    )


def test_add_in_memory_mockstore__upsert_existing_replaces():
    """AC6: Upserting existing ID replaces it without changing count."""
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const before = await store.count();
await store.upsert({
  id: 'article-001',
  headline: 'Updated Vector Search',
  details: 'Updated content about vector similarity and RAG systems.'
});
const after = await store.count();
process.stdout.write(JSON.stringify({ before, after }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0
    data = json.loads(out.strip())
    assert data["after"] == data["before"]


def test_add_in_memory_mockstore__upserted_article_searchable():
    """AC6: Upserted article is immediately discoverable via search()."""
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
await store.upsert({
  id: 'test-upsert-searchable-49',
  headline: 'Quantum Cryptography',
  details: 'Quantum cryptography applies quantum mechanics to secure communications. Post-quantum algorithms resist quantum attacks.'
});
const results = await store.search('quantum cryptography security', 10);
const found = results.some(r => r.id === 'test-upsert-searchable-49');
process.stdout.write(JSON.stringify({ found }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0
    data = json.loads(out.strip())
    assert data["found"]


# ---------------------------------------------------------------------------
# AC7: delete() removes article; search() and count() reflect it
# ---------------------------------------------------------------------------

def test_add_in_memory_mockstore__delete_decreases_count():
    """AC7: count() decreases by 1 after deleting an article."""
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const before = await store.count();
const deleted = await store.delete('article-001');
const after = await store.count();
process.stdout.write(JSON.stringify({ before, after, deleted }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0
    data = json.loads(out.strip())
    assert data["deleted"] is True
    assert data["after"] == data["before"] - 1


def test_add_in_memory_mockstore__deleted_absent_from_search():
    """AC7: Deleted article does not appear in subsequent search results."""
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
    assert rc == 0
    data = json.loads(out.strip())
    assert data["foundBefore"] and not data["foundAfter"]


def test_add_in_memory_mockstore__delete_nonexistent_returns_false():
    """AC7: delete() returns false for nonexistent article."""
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const result = await store.delete('nonexistent-xyz-49');
process.stdout.write(JSON.stringify(result));
"""
    out, err, rc = _run_node(script, timeout=30)
    assert rc == 0
    result = json.loads(out.strip())
    assert result is False


# ---------------------------------------------------------------------------
# AC8: count() returns exact number of articles in memory
# ---------------------------------------------------------------------------

def test_add_in_memory_mockstore__count_exact_at_seed():
    """AC8: count() exactly matches seed article count."""
    script = """
import { MockStore } from './src/store/MockStore.js';
import { generateDocuments } from './src/data/generator.js';
const store = new MockStore();
const count = await store.count();
const seedCount = generateDocuments().length;
process.stdout.write(JSON.stringify({ count, seedCount }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0
    data = json.loads(out.strip())
    assert data["count"] == data["seedCount"]


def test_add_in_memory_mockstore__count_tracks_mutations():
    """AC8: count() accurately reflects upsert and delete sequence."""
    script = """
import { MockStore } from './src/store/MockStore.js';
const store = new MockStore();
const seed = await store.count();
await store.upsert({ id: 'ac8-alpha', headline: 'Alpha', details: 'Distributed consensus and Raft protocol for fault tolerance.' });
await store.upsert({ id: 'ac8-beta', headline: 'Beta', details: 'Graph databases and knowledge graphs for semantic reasoning.' });
const after2 = await store.count();
await store.delete('ac8-alpha');
const after1 = await store.count();
process.stdout.write(JSON.stringify({ seed, after2, after1 }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0
    data = json.loads(out.strip())
    assert data["after2"] == data["seed"] + 2
    assert data["after1"] == data["seed"] + 1


# ---------------------------------------------------------------------------
# AC9: No connection errors with DB_BACKEND=mock and no Docker
# ---------------------------------------------------------------------------

def test_add_in_memory_mockstore__no_connection_errors():
    """AC9: Using MockStore with DB_BACKEND=mock produces no errors."""
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
    assert rc == 0, f"Exited non-zero: rc={rc}, stderr={err}"
    data = json.loads(out.strip())
    assert data["error"] is None, f"Unexpected error: {data['error']}"


def test_add_in_memory_mockstore__no_unhandled_rejections():
    """AC9: Process exits cleanly with no unhandled promise rejections."""
    script = """
import { getStore } from './src/store/index.js';
const store = await getStore();
const count = await store.count();
const pingResult = await store.ping();
process.stdout.write(JSON.stringify({ count, ok: pingResult.ok === true }));
"""
    out, err, rc = _run_node(script, env={"DB_BACKEND": "mock"})
    assert rc == 0, f"Process should exit cleanly: rc={rc}, stderr={err}"
    assert "UnhandledPromiseRejection" not in err
    data = json.loads(out.strip())
    assert data["ok"] and data["count"] > 0
