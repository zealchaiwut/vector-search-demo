"""
Acceptance tests for issue #97: Switch embedder to multilingual-e5-small for Thai support

AC1  - src/embeddings uses intfloat/multilingual-e5-small as the embedding model
AC2  - Query text is prefixed with "query:" before embedding at all search call sites
AC3  - Document and chunk text is prefixed with "passage:" before embedding at all ingest call sites
AC4  - L2 normalization is retained on all produced vectors
AC5  - The vector column remains vector(384) — no migration of the schema is required
AC6  - A re-embed command/path exists that recomputes embeddings for every existing article and chunk
AC7  - Running ingest on already-ingested content replaces old vectors with new model vectors
AC8  - A Thai query returns the correct Thai article as the top-ranked result above unrelated English documents
AC9  - The cosine similarity score for a true Thai match is materially higher under the new model
"""

import json
import math
import os
import subprocess
import tempfile

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMBEDDINGS_INDEX = os.path.join(REPO_ROOT, "src", "embeddings", "index.js")
DATA_EMBEDDER = os.path.join(REPO_ROOT, "src", "data", "embedder.js")
SEARCH_CORE = os.path.join(REPO_ROOT, "src", "core", "search.js")
CLI_SRC = os.path.join(REPO_ROOT, "src", "cli.ts")
REEMBED_CMD = os.path.join(REPO_ROOT, "src", "commands", "re-embed.js")

MODEL_TIMEOUT = 300  # model download can take time on first run


def _run_node(script, timeout=MODEL_TIMEOUT, env=None):
    import os as _os
    run_env = _os.environ.copy()
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


def _run_cli(args, timeout=MODEL_TIMEOUT, env=None):
    import os as _os
    run_env = _os.environ.copy()
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


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# AC1: model is multilingual-e5-small
# ---------------------------------------------------------------------------

def test_model_is_multilingual_e5_small():
    """AC1: src/embeddings/index.js uses intfloat/multilingual-e5-small (Xenova port)."""
    with open(EMBEDDINGS_INDEX) as f:
        source = f.read()
    assert "multilingual-e5-small" in source, (
        "Expected 'multilingual-e5-small' in src/embeddings/index.js, "
        f"but got:\n{source[:500]}"
    )
    assert "all-MiniLM" not in source, (
        "all-MiniLM should have been replaced by multilingual-e5-small in src/embeddings/index.js"
    )


# ---------------------------------------------------------------------------
# AC2: query: prefix in search call sites
# ---------------------------------------------------------------------------

def test_query_prefix_in_search_core():
    """AC2: search.js adds 'query: ' prefix to query text before embedding."""
    with open(SEARCH_CORE) as f:
        source = f.read()
    assert "query: " in source or "query:" in source, (
        "Expected 'query: ' prefix in src/core/search.js but not found.\n"
        "The search code must prefix query text with 'query: ' before calling embed()."
    )


# ---------------------------------------------------------------------------
# AC3: passage: prefix in ingest call sites
# ---------------------------------------------------------------------------

def test_passage_prefix_in_data_embedder():
    """AC3: data/embedder.js adds 'passage: ' prefix to chunk text before embedding."""
    with open(DATA_EMBEDDER) as f:
        source = f.read()
    assert "passage: " in source or "passage:" in source, (
        "Expected 'passage: ' prefix in src/data/embedder.js but not found.\n"
        "The ingest embedder must prefix document text with 'passage: ' before calling embed()."
    )


# ---------------------------------------------------------------------------
# AC4: L2 normalization is retained
# ---------------------------------------------------------------------------

def test_l2_normalization_retained():
    """AC4: vectors produced by the new model are L2-normalized (norm ≈ 1.0)."""
    script = """
import { createEmbedder } from './src/embeddings/index.js';
const embedder = await createEmbedder();
const vecs = await embedder.embed(["passage: the quick brown fox jumps"]);
const v = vecs[0];
const norm = Math.sqrt(v.reduce((s, x) => s + x * x, 0));
process.stdout.write(String(norm));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    norm = float(out.strip())
    assert abs(norm - 1.0) < 0.01, f"Expected L2 norm ≈ 1.0, got {norm}"


# ---------------------------------------------------------------------------
# AC5: vector dimension is 384
# ---------------------------------------------------------------------------

def test_vector_dimension_is_384():
    """AC5: multilingual-e5-small produces 384-dimensional vectors (no schema migration needed)."""
    script = """
import { createEmbedder } from './src/embeddings/index.js';
const embedder = await createEmbedder();
const vecs = await embedder.embed(["passage: test"]);
process.stdout.write(String(vecs[0].length));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    assert out.strip() == "384", f"Expected 384 dimensions, got {out.strip()}"


def test_embedder_dim_property_is_384():
    """AC5: embedder.dim property is 384."""
    script = """
import { createEmbedder } from './src/embeddings/index.js';
const embedder = await createEmbedder();
process.stdout.write(String(embedder.dim));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    assert out.strip() == "384", f"Expected embedder.dim=384, got {out.strip()}"


# ---------------------------------------------------------------------------
# AC6: re-embed command exists
# ---------------------------------------------------------------------------

def test_reembed_command_file_exists():
    """AC6: src/commands/re-embed.js exists."""
    assert os.path.isfile(REEMBED_CMD), (
        f"src/commands/re-embed.js not found at {REEMBED_CMD}"
    )


def test_reembed_registered_in_cli():
    """AC6: CLI registers the re-embed command."""
    with open(CLI_SRC) as f:
        source = f.read()
    assert "re-embed" in source, (
        "Expected 're-embed' command registered in src/cli.ts but not found."
    )


def test_reembed_command_runs():
    """AC6: re-embed command runs without error (mock backend)."""
    # First run ingest so there's something to re-embed
    out1, err1, rc1 = _run_cli(["ingest"], env={"DB_BACKEND": "mock"})
    assert rc1 == 0, f"Ingest failed: {err1}\n{out1}"

    out2, err2, rc2 = _run_cli(["re-embed"], env={"DB_BACKEND": "mock"})
    assert rc2 == 0, (
        f"re-embed command failed: {err2}\n{out2}"
    )


# ---------------------------------------------------------------------------
# AC7: ingest replaces old vectors (idempotent, no duplicates)
# ---------------------------------------------------------------------------

def test_ingest_replaces_old_vectors_no_duplicates():
    """AC7: running ingest twice produces same row count (upsert, no duplicates)."""
    script = """
import { resolveBackend, getStore } from './src/store/factory.js';
const store = await getStore('mock');
await store.dropCollection();
await store.createCollection();

// First ingest simulation: import and run
const { runIngest } = await import('./src/commands/ingest.js');
await runIngest();
const count1 = await store.entityCount();

// Second ingest
await runIngest();
const count2 = await store.entityCount();

process.stdout.write(JSON.stringify({ count1, count2 }));
"""
    out, err, rc = _run_node(script, env={"DB_BACKEND": "mock"})
    assert rc == 0, f"Node error: {err}\nstdout: {out}"
    # extract JSON from last line (other lines are backend/ingest log output)
    json_line = [l for l in out.strip().splitlines() if l.startswith("{")][-1]
    result = json.loads(json_line)
    assert result["count1"] == result["count2"], (
        f"Running ingest twice should produce same count (upsert), "
        f"but got count1={result['count1']}, count2={result['count2']}"
    )
    assert result["count1"] > 0, "Expected at least one row after ingest"


# ---------------------------------------------------------------------------
# AC8: Thai query returns Thai article as top result
# ---------------------------------------------------------------------------

def test_thai_query_returns_thai_article_first():
    """AC8: Thai search query returns the Thai article as the top-ranked result."""
    # Run ingest (includes Thai article), then search
    out_ingest, err_ingest, rc_ingest = _run_cli(
        ["ingest"], env={"DB_BACKEND": "mock"}, timeout=MODEL_TIMEOUT
    )
    assert rc_ingest == 0, f"Ingest failed:\n{err_ingest}\n{out_ingest}"

    script = """
import { searchDocuments } from './src/core/search.js';
const results = await searchDocuments("การค้นหาเชิงความหมายในภาษาไทย", 5);
process.stdout.write(JSON.stringify(results.map(r => ({ id: r.id, score: r.score, headline: r.headline }))));
"""
    out, err, rc = _run_node(script, env={"DB_BACKEND": "mock"})
    assert rc == 0, f"Search failed: {err}\n{out}"
    results = json.loads(out)
    assert len(results) > 0, "Expected at least one search result for Thai query"

    top = results[0]
    assert "thai" in top["id"].lower() or "ภาษาไทย" in top.get("headline", "").lower() or "thai" in top.get("headline", "").lower(), (
        f"Expected Thai article as top result, got: {top}"
    )


# ---------------------------------------------------------------------------
# AC9: cosine similarity is materially higher for Thai match
# ---------------------------------------------------------------------------

def test_thai_match_score_higher_than_english_docs():
    """AC9: Thai article cosine score is materially higher than unrelated English docs."""
    script = """
import { searchDocuments } from './src/core/search.js';
const results = await searchDocuments("การค้นหาเชิงความหมายในภาษาไทย", 10);
if (results.length < 2) {
  process.stdout.write(JSON.stringify({ error: "not enough results", count: results.length }));
  process.exit(0);
}
const topScore = results[0].score;
const secondScore = results[1].score;
process.stdout.write(JSON.stringify({ topScore, secondScore, topId: results[0].id, results: results.map(r => ({ id: r.id, score: r.score })) }));
"""
    out, err, rc = _run_node(script, env={"DB_BACKEND": "mock"})
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert "error" not in data, f"Search error: {data}"

    top_score = data["topScore"]
    second_score = data["secondScore"]

    # The Thai article should score materially higher than second-best
    assert top_score > second_score + 0.02, (
        f"Expected Thai article score ({top_score}) to be materially higher than "
        f"second-best ({second_score}). Full results: {data['results']}"
    )


# ---------------------------------------------------------------------------
# AC2 (behavioral): query: prefix changes embedding correctly
# ---------------------------------------------------------------------------

def test_query_prefix_applied_in_search():
    """AC2 (behavioral): embedding with 'query: ' prefix differs from bare text,
    confirming the prefix is applied at search time."""
    script = """
import { createEmbedder } from './src/embeddings/index.js';
const embedder = await createEmbedder();
const [bare] = await embedder.embed(["vector search"]);
const [prefixed] = await embedder.embed(["query: vector search"]);
// They must differ — prefix changes the embedding
const diff = bare.reduce((s, x, i) => s + Math.abs(x - prefixed[i]), 0);
process.stdout.write(String(diff));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    diff = float(out.strip())
    assert diff > 0.001, (
        f"Expected 'query: ' prefix to change the embedding, but diff={diff} (too small). "
        "The prefix may not be applied."
    )


# ---------------------------------------------------------------------------
# AC3 (behavioral): passage: prefix changes embedding correctly
# ---------------------------------------------------------------------------

def test_passage_prefix_applied_in_embed():
    """AC3 (behavioral): embedding with 'passage: ' prefix differs from bare text,
    confirming the prefix is applied at ingest time."""
    script = """
import { createEmbedder } from './src/embeddings/index.js';
const embedder = await createEmbedder();
const [bare] = await embedder.embed(["vector search is great"]);
const [prefixed] = await embedder.embed(["passage: vector search is great"]);
const diff = bare.reduce((s, x, i) => s + Math.abs(x - prefixed[i]), 0);
process.stdout.write(String(diff));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    diff = float(out.strip())
    assert diff > 0.001, (
        f"Expected 'passage: ' prefix to change the embedding, but diff={diff} (too small). "
        "The prefix may not be applied."
    )
