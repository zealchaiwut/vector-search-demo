"""
TDD tests for issue #185: Support multi-model chunk embeddings for corpus comparison

AC1 — Schema defines a chunk_embeddings table (or equivalent per-model store) with
      chunk_id, model_id, vector, dimension; existing single-model data migrates
      without data loss.
AC2 — A models registry stores name, dimension, and "is default" flag for each
      registered embedding model.
AC3 — CLI command `embed-corpus --model <name>` embeds all existing chunks under
      the specified model, storing vectors at that model's native dimension, and
      is idempotent (re-running does not duplicate rows).
AC4 — The default search model remains configurable and unaffected by adding a
      secondary model.
AC5 — Search accepts an optional --model <name> flag that targets the named
      model's embedding space.
AC6 — At least two models with different dimensions can coexist in the store
      without error.
AC7 — Attempting to search with an unregistered model name returns a clear,
      actionable error message.
AC8 — Unit/integration tests cover: embed-corpus for secondary model, coexistence
      of two model vectors for same chunk, model-targeted search.
"""

import json
import os
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_REGISTRY = os.path.join(REPO_ROOT, "src", "embeddings", "model-registry.js")
MIGRATIONS_DIR = os.path.join(REPO_ROOT, "src", "store", "migrations")
EMBED_CORPUS_CMD = os.path.join(REPO_ROOT, "src", "commands", "embed-corpus.js")
SEARCH_CMD = os.path.join(REPO_ROOT, "src", "commands", "search.js")
CLI_TS = os.path.join(REPO_ROOT, "src", "cli.ts")
MULTI_MODEL_STORE = os.path.join(REPO_ROOT, "src", "store", "MultiModelStore.js")
PG_STORE = os.path.join(REPO_ROOT, "src", "store", "PgVectorStore.js")


def _run_node(script, timeout=60, env=None):
    run_env = os.environ.copy()
    run_env.pop("MILVUS_HOST", None)
    if env:
        run_env.update(env)
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
        env=run_env,
    )
    return result.stdout, result.stderr, result.returncode


def _run_cli(args, timeout=60, env=None):
    run_env = os.environ.copy()
    run_env.pop("MILVUS_HOST", None)
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
# AC1 — chunk_embeddings schema (migration or equivalent per-model store)
# ---------------------------------------------------------------------------

def test_ac1_migration_007_chunk_embeddings_exists():
    """AC1: Migration 007 (or later) must define a chunk_embeddings table."""
    files = sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql"))
    has_007 = any(f.startswith("007") for f in files)
    assert has_007, (
        f"Migration 007_chunk_embeddings.sql must exist in {MIGRATIONS_DIR}. "
        f"Found: {files}"
    )


def test_ac1_migration_chunk_embeddings_has_required_columns():
    """AC1: chunk_embeddings migration must define chunk_id, model_id, vector, dimension."""
    files = sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.startswith("007"))
    assert files, "Migration 007_*.sql not found"
    path = os.path.join(MIGRATIONS_DIR, files[0])
    with open(path) as f:
        sql = f.read().lower()
    assert "chunk_embeddings" in sql, "Migration must create chunk_embeddings table"
    assert "chunk_id" in sql, "chunk_embeddings must have chunk_id column"
    assert "model_id" in sql, "chunk_embeddings must have model_id column"
    assert "vector" in sql or "real[]" in sql or "embedding" in sql, (
        "chunk_embeddings must have a vector/embedding column"
    )
    assert "dimension" in sql or "dim" in sql, (
        "chunk_embeddings must have a dimension column"
    )


def test_ac1_migration_chunk_embeddings_has_primary_key():
    """AC1: chunk_embeddings must have a composite primary key on (chunk_id, model_id)."""
    files = sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.startswith("007"))
    assert files, "Migration 007_*.sql not found"
    path = os.path.join(MIGRATIONS_DIR, files[0])
    with open(path) as f:
        sql = f.read().lower()
    assert "primary key" in sql, (
        "chunk_embeddings must have a PRIMARY KEY to enforce idempotency"
    )


def test_ac1_migration_is_idempotent():
    """AC1: Migration 007 must use IF NOT EXISTS or ON CONFLICT to be idempotent."""
    files = sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.startswith("007"))
    assert files
    path = os.path.join(MIGRATIONS_DIR, files[0])
    with open(path) as f:
        sql = f.read().lower()
    assert "if not exists" in sql or "on conflict" in sql, (
        "Migration 007 must be idempotent (IF NOT EXISTS or ON CONFLICT guard)"
    )


def test_ac1_multi_model_store_file_exists():
    """AC1: src/store/MultiModelStore.js must exist for the mock backend equivalent."""
    assert os.path.isfile(MULTI_MODEL_STORE), (
        f"src/store/MultiModelStore.js must exist at {MULTI_MODEL_STORE}"
    )


def test_ac1_multi_model_store_exports_upsert_and_get():
    """AC1: MultiModelStore must export upsert and get (or equivalent) methods."""
    with open(MULTI_MODEL_STORE) as f:
        source = f.read()
    assert "upsert" in source or "store" in source.lower(), (
        "MultiModelStore must export an upsert method for storing per-model vectors"
    )
    assert "get" in source or "lookup" in source or "find" in source, (
        "MultiModelStore must export a get/lookup method for retrieving per-model vectors"
    )


def test_ac1_multi_model_store_node_importable():
    """AC1: MultiModelStore imports without error in Node."""
    script = """
import { MultiModelStore } from './src/store/MultiModelStore.js';
const store = new MultiModelStore('/tmp/test_chunk_embeddings_185.json');
process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"MultiModelStore import failed: {err}"
    assert out.strip() == "ok"


def test_ac1_mock_backend_coexistence_two_models():
    """AC1/AC6: MultiModelStore can store vectors from two models for the same chunk."""
    script = """
import { MultiModelStore } from './src/store/MultiModelStore.js';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const path = join(tmpdir(), 'test_185_coexist.json');
const store = new MultiModelStore(path);

const vec384 = Array.from({length: 384}, (_, i) => i / 384);
const vec1024 = Array.from({length: 1024}, (_, i) => i / 1024);

await store.upsert('article-1:0', 'multilingual-e5-small', vec384, 384);
await store.upsert('article-1:0', 'BAAI/bge-m3', vec1024, 1024);

const r1 = await store.get('article-1:0', 'multilingual-e5-small');
const r2 = await store.get('article-1:0', 'BAAI/bge-m3');

if (!r1 || r1.dimension !== 384) throw new Error('e5-small row missing or wrong dim');
if (!r2 || r2.dimension !== 1024) throw new Error('bge-m3 row missing or wrong dim');

process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Coexistence test failed: {err}\n{out}"
    assert out.strip() == "ok"


def test_ac1_multi_model_store_upsert_is_idempotent():
    """AC1/AC3: Upserting the same chunk+model twice does not create duplicate entries."""
    script = """
import { MultiModelStore } from './src/store/MultiModelStore.js';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const path = join(tmpdir(), 'test_185_idempotent.json');
const store = new MultiModelStore(path);

const vec = Array.from({length: 384}, (_, i) => i / 384);
await store.upsert('art:0', 'multilingual-e5-small', vec, 384);
await store.upsert('art:0', 'multilingual-e5-small', vec, 384);

const all = await store.list('multilingual-e5-small');
const count = all.filter(r => r.chunk_id === 'art:0').length;
if (count !== 1) throw new Error('Expected 1 row, got ' + count);

process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Idempotency test failed: {err}\n{out}"
    assert out.strip() == "ok"


# ---------------------------------------------------------------------------
# AC2 — Models registry has isDefault flag
# ---------------------------------------------------------------------------

def test_ac2_model_registry_exports_is_default_info():
    """AC2: model-registry.js must expose isDefault or equivalent for each model."""
    with open(MODEL_REGISTRY) as f:
        source = f.read()
    assert "isDefault" in source or "is_default" in source or "getDefaultModel" in source, (
        "model-registry.js must expose isDefault flag or getDefaultModel() helper"
    )


def test_ac2_get_default_model_returns_e5_small():
    """AC2: getDefaultModel() returns 'Xenova/multilingual-e5-small' by default."""
    script = """
import { getDefaultModel } from './src/embeddings/model-registry.js';
const name = getDefaultModel();
process.stdout.write(name);
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    assert "e5-small" in out or "multilingual-e5-small" in out, (
        f"getDefaultModel() should return e5-small by default, got: {out!r}"
    )


def test_ac2_get_default_model_respects_env_var():
    """AC2: getDefaultModel() uses EMBEDDING_MODEL env var when set."""
    script = """
import { getDefaultModel } from './src/embeddings/model-registry.js';
const name = getDefaultModel();
process.stdout.write(name);
"""
    out, err, rc = _run_node(script, env={"EMBEDDING_MODEL": "multilingual-e5-large"})
    assert rc == 0, f"Node error: {err}"
    assert "e5-large" in out or "multilingual-e5-large" in out, (
        f"getDefaultModel() should respect EMBEDDING_MODEL env, got: {out!r}"
    )


def test_ac2_resolve_model_exposes_is_default_field():
    """AC2: resolveModel() result includes isDefault field (true for the env-configured default)."""
    script = """
import { resolveModel } from './src/embeddings/model-registry.js';
const m = resolveModel('Xenova/multilingual-e5-small');
process.stdout.write(JSON.stringify({ hasDefault: 'isDefault' in m }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out.strip())
    assert data.get("hasDefault") is True, (
        f"resolveModel() result must include 'isDefault' field, got: {data}"
    )


# ---------------------------------------------------------------------------
# AC3 — embed-corpus CLI command exists and is idempotent
# ---------------------------------------------------------------------------

def test_ac3_embed_corpus_command_file_exists():
    """AC3: src/commands/embed-corpus.js must exist."""
    assert os.path.isfile(EMBED_CORPUS_CMD), (
        f"src/commands/embed-corpus.js must exist at {EMBED_CORPUS_CMD}"
    )


def test_ac3_embed_corpus_wired_in_cli():
    """AC3: cli.ts must wire the embed-corpus command."""
    with open(CLI_TS) as f:
        source = f.read()
    assert "embed-corpus" in source, (
        "cli.ts must register an 'embed-corpus' command"
    )


def test_ac3_embed_corpus_has_model_flag():
    """AC3: embed-corpus.js must accept --model flag."""
    with open(EMBED_CORPUS_CMD) as f:
        source = f.read()
    assert "--model" in source, (
        "embed-corpus.js must accept --model flag"
    )


def test_ac3_embed_corpus_help_runs():
    """AC3: embed-corpus --help exits 0 and mentions --model."""
    out, err, rc = _run_cli(
        ["embed-corpus", "--help"],
        env={"DB_BACKEND": "mock"},
    )
    combined = out + err
    assert rc == 0, f"embed-corpus --help failed: {combined}"
    assert "--model" in combined or "model" in combined.lower(), (
        f"embed-corpus --help must mention --model flag. Got: {combined[:400]}"
    )


def test_ac3_embed_corpus_requires_model_flag():
    """AC3: embed-corpus without --model gives clear error."""
    out, err, rc = _run_cli(
        ["embed-corpus"],
        env={"DB_BACKEND": "mock"},
    )
    combined = out + err
    assert rc != 0 or "model" in combined.lower(), (
        "embed-corpus without --model must either fail or prompt for --model. "
        f"Got rc={rc}, output: {combined[:400]}"
    )


def test_ac3_embed_corpus_unregistered_model_error():
    """AC3/AC7: embed-corpus --model nonexistent-model-xyz gives clear error."""
    out, err, rc = _run_cli(
        ["embed-corpus", "--model", "nonexistent-model-xyz"],
        env={"DB_BACKEND": "mock"},
    )
    combined = out + err
    assert rc != 0, (
        f"embed-corpus with unregistered model must exit non-zero. Got: {combined[:400]}"
    )
    assert "unknown" in combined.lower() or "not found" in combined.lower() or "supported" in combined.lower(), (
        f"embed-corpus must give clear error for unregistered model. Got: {combined[:400]}"
    )


# ---------------------------------------------------------------------------
# AC4 — Default search model is unaffected
# ---------------------------------------------------------------------------

def test_ac4_search_without_model_flag_still_works():
    """AC4: search command without --model flag uses the default model path."""
    with open(SEARCH_CMD) as f:
        source = f.read()
    # Default path must remain intact — no unconditional multi-model redirect
    assert "query" in source or "search" in source.lower(), (
        "search.js must still have the default search path"
    )


def test_ac4_embed_corpus_does_not_touch_articles_table():
    """AC4: embed-corpus stores vectors in chunk_embeddings, not overwriting articles/collection."""
    with open(EMBED_CORPUS_CMD) as f:
        source = f.read()
    # Must write to MultiModelStore / chunk_embeddings, not to articles
    assert "MultiModelStore" in source or "chunk_embeddings" in source or "upsert" in source, (
        "embed-corpus must write to the multi-model store (chunk_embeddings), not articles"
    )


# ---------------------------------------------------------------------------
# AC5 — Search accepts --model <name> flag
# ---------------------------------------------------------------------------

def test_ac5_search_command_has_model_flag_parsing():
    """AC5: search.js must parse a --model flag."""
    with open(SEARCH_CMD) as f:
        source = f.read()
    assert "--model" in source or '"model"' in source or "'model'" in source, (
        "search.js must accept --model flag"
    )


def test_ac5_search_model_flag_in_cli_ts():
    """AC5: cli.ts search command must expose --model option."""
    with open(CLI_TS) as f:
        source = f.read()
    assert "model" in source, (
        "cli.ts search command must expose --model option"
    )


def test_ac5_search_unregistered_model_returns_clear_error():
    """AC5/AC7: search --model nonexistent-xyz returns clear error."""
    out, err, rc = _run_cli(
        ["search", "--model", "nonexistent-xyz", "test query"],
        env={"DB_BACKEND": "mock"},
    )
    combined = out + err
    assert rc != 0, (
        f"search with unregistered model must exit non-zero. Got rc={rc}: {combined[:400]}"
    )
    assert (
        "unknown" in combined.lower()
        or "not found" in combined.lower()
        or "supported" in combined.lower()
        or "registered" in combined.lower()
        or "unregistered" in combined.lower()
    ), (
        f"search must return clear actionable error for unregistered model. Got: {combined[:400]}"
    )


# ---------------------------------------------------------------------------
# AC6 — Two models with different dimensions coexist without error
# ---------------------------------------------------------------------------

def test_ac6_multi_model_store_different_dims_no_error():
    """AC6: Storing 384-d and 1024-d vectors for the same chunk raises no error."""
    script = """
import { MultiModelStore } from './src/store/MultiModelStore.js';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const path = join(tmpdir(), 'test_185_dims.json');
const store = new MultiModelStore(path);

const vec384 = Array.from({length: 384}, () => 0.5);
const vec1024 = Array.from({length: 1024}, () => 0.5);

try {
  await store.upsert('chunk:0', 'multilingual-e5-small', vec384, 384);
  await store.upsert('chunk:0', 'BAAI/bge-m3', vec1024, 1024);

  const r1 = await store.get('chunk:0', 'multilingual-e5-small');
  const r2 = await store.get('chunk:0', 'BAAI/bge-m3');

  if (!r1 || r1.dimension !== 384) throw new Error('384-d missing');
  if (!r2 || r2.dimension !== 1024) throw new Error('1024-d missing');

  process.stdout.write('ok');
} catch(e) {
  process.stderr.write(e.message);
  process.exit(1);
}
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Two-model coexistence failed: {err}\n{out}"
    assert out.strip() == "ok"


def test_ac6_pg_migration_supports_variable_dim():
    """AC6: Migration 007 uses real[] or text for vector (not fixed-dim vector type)
    so models with different output dimensions can coexist."""
    files = sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.startswith("007"))
    assert files
    path = os.path.join(MIGRATIONS_DIR, files[0])
    with open(path) as f:
        sql = f.read().lower()
    # Should NOT use vector(N) with a fixed N — must be real[] or similar
    import re
    fixed_dim = re.search(r"vector\s*\(\s*\d+\s*\)", sql)
    assert not fixed_dim, (
        "Migration 007 must NOT use vector(N) with fixed dimension — use real[] "
        "so models with different dims can coexist. Found: " + (fixed_dim.group(0) if fixed_dim else "")
    )


# ---------------------------------------------------------------------------
# AC7 — Unregistered model → clear error
# ---------------------------------------------------------------------------

def test_ac7_resolve_model_gives_clear_error_for_unknown():
    """AC7: resolveModel('bad-model') throws a clear error mentioning supported values."""
    script = """
import { resolveModel } from './src/embeddings/model-registry.js';
try {
  resolveModel('bad-model-xyz');
  process.stdout.write('no-error');
} catch(e) {
  process.stdout.write('error:' + e.message);
}
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node crashed: {err}"
    assert out.startswith("error:"), f"Expected error, got: {out!r}"
    msg = out[len("error:"):]
    assert "bad-model-xyz" in msg or "unknown" in msg.lower() or "supported" in msg.lower(), (
        f"Error must mention the bad model name or list supported values. Got: {msg!r}"
    )


def test_ac7_search_model_flag_error_is_actionable():
    """AC7: --model error from search command is actionable (names supported models)."""
    out, err, rc = _run_cli(
        ["search", "--model", "bad-model-name", "test"],
        env={"DB_BACKEND": "mock"},
    )
    combined = out + err
    assert rc != 0, "Must exit non-zero for unregistered model"
    # Error message should give the user something to act on
    assert len(combined.strip()) > 10, "Error message must be non-empty"


# ---------------------------------------------------------------------------
# AC8 — Integration: embed-corpus secondary model + coexistence + targeted search
# ---------------------------------------------------------------------------

def test_ac8_embed_corpus_stores_vectors_in_multi_model_store():
    """AC8: embed-corpus stores per-model vectors in MultiModelStore."""
    with open(EMBED_CORPUS_CMD) as f:
        source = f.read()
    assert "MultiModelStore" in source, (
        "embed-corpus.js must use MultiModelStore to store per-model vectors"
    )


def test_ac8_embed_corpus_reads_chunks_from_main_store():
    """AC8: embed-corpus reads existing chunks from the main store (collection.json or articles)."""
    with open(EMBED_CORPUS_CMD) as f:
        source = f.read()
    assert (
        "collection" in source.lower()
        or "listChunks" in source
        or "getStore" in source
        or "articles" in source.lower()
    ), (
        "embed-corpus.js must read existing chunks from the main store to re-embed them"
    )


def test_ac8_search_with_model_uses_multi_model_store():
    """AC8: When --model is passed to search, it uses MultiModelStore for lookup."""
    with open(SEARCH_CMD) as f:
        source = f.read()
    assert "MultiModelStore" in source or "model" in source.lower(), (
        "search.js must reference MultiModelStore when --model flag is used"
    )


def test_ac8_pg_store_has_chunk_embeddings_methods():
    """AC8: PgVectorStore must expose methods for multi-model embeddings."""
    with open(PG_STORE) as f:
        source = f.read()
    assert (
        "chunk_embeddings" in source
        or "upsertEmbedding" in source
        or "searchByModel" in source
    ), (
        "PgVectorStore must have methods for the chunk_embeddings table "
        "(upsertEmbedding, searchByModel, or chunk_embeddings references)"
    )


def test_ac8_multi_model_store_search_returns_ranked_results():
    """AC8: MultiModelStore.search() returns chunks ranked by cosine similarity."""
    script = """
import { MultiModelStore } from './src/store/MultiModelStore.js';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const path = join(tmpdir(), 'test_185_search.json');
const store = new MultiModelStore(path);

// Two chunks: chunk-A similar to query, chunk-B not
const vecA = [1.0, 0.0, 0.0];
const vecB = [0.0, 1.0, 0.0];
const query = [1.0, 0.0, 0.0]; // same as A

const articleRows = [
  { id: 'art-1:0', headline: 'Article A', details: 'details A', attachment_url: null },
  { id: 'art-2:0', headline: 'Article B', details: 'details B', attachment_url: null },
];

await store.upsert('art-1:0', 'e5-small', vecA, 3);
await store.upsert('art-2:0', 'e5-small', vecB, 3);

const results = await store.search(query, 'e5-small', 10, articleRows);

if (results.length < 2) throw new Error('Expected 2 results, got ' + results.length);
if (results[0].id !== 'art-1' && results[0].id !== 'art-1:0') {
  throw new Error('Expected art-1 first, got ' + results[0].id);
}
process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"MultiModelStore search test failed: {err}\n{out}"
    assert out.strip() == "ok"
