"""
Tests for issue #31: Replace TF-IDF embedder with MiniLM in ingest

AC1 - src/data/embedder.js no longer builds TF-IDF vectors; uses createEmbedder from
      src/embeddings/index.js for batch embedding
AC2 - Model identifier and embedding dimension read from env config (EMBEDDING_MODEL, DIM)
      and not hardcoded in more than one place
AC3 - Running ingest produces exactly one 384-element FloatVector per chunk, no dimension error
AC4 - Running ingest a second time on the same corpus does not create duplicate rows
      (upsert-by-id behaviour is preserved)
AC5 - README contains a note that the first ingest run downloads the embedding model (~90 MB)
      and documents the relevant .env variables (EMBEDDING_MODEL, DIM)
"""

import json
import os
import re
import subprocess

import pytest

CODER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EMBEDDER_PATH = os.path.join(CODER_DIR, "src", "data", "embedder.js")
EMBEDDINGS_INDEX_PATH = os.path.join(CODER_DIR, "src", "embeddings", "index.js")
INGEST_CMD_PATH = os.path.join(CODER_DIR, "src", "commands", "ingest.js")
CLI_PATH = os.path.join(CODER_DIR, "src", "cli.js")
COLLECTION_JSON = os.path.join(CODER_DIR, "collection.json")
README_PATH = os.path.join(CODER_DIR, "README.md")

# Longer timeout to handle model download on first run
INGEST_TIMEOUT = 180


def run_ingest(timeout=INGEST_TIMEOUT):
    return subprocess.run(
        ["node", CLI_PATH, "ingest"],
        capture_output=True,
        text=True,
        cwd=CODER_DIR,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# AC1: TF-IDF removed; createEmbedder from embeddings/index.js used
# ---------------------------------------------------------------------------


def test_embedder__no_tfidf_buildidf():
    """AC1: embedder.js must not contain TF-IDF buildIDF logic."""
    with open(EMBEDDER_PATH) as f:
        src = f.read()
    assert "buildIDF" not in src, (
        "src/data/embedder.js still contains buildIDF — TF-IDF must be removed"
    )


def test_embedder__no_tfidf_tokenize():
    """AC1: embedder.js must not contain TF-IDF tokenize function."""
    with open(EMBEDDER_PATH) as f:
        src = f.read()
    assert "function tokenize" not in src, (
        "src/data/embedder.js still contains tokenize() — TF-IDF must be removed"
    )


def test_embedder__imports_from_embeddings_index():
    """AC1: embedder.js must import createEmbedder from src/embeddings/index.js."""
    with open(EMBEDDER_PATH) as f:
        src = f.read()
    assert "../embeddings/index.js" in src or "../embeddings/index" in src, (
        "src/data/embedder.js does not import from ../embeddings/index.js"
    )
    assert "createEmbedder" in src, (
        "src/data/embedder.js does not use createEmbedder"
    )


def test_embedder__batchEmbed_is_async():
    """AC1: batchEmbed must be declared as an async function (returns a Promise)."""
    with open(EMBEDDER_PATH) as f:
        src = f.read()
    assert re.search(r"export\s+async\s+function\s+batchEmbed", src), (
        "batchEmbed is not declared as 'export async function batchEmbed'"
    )


def test_ingest_cmd__awaits_batchEmbed():
    """AC1: ingest.js must await the async batchEmbed call."""
    with open(INGEST_CMD_PATH) as f:
        src = f.read()
    assert re.search(r"await\s+batchEmbed\s*\(", src), (
        "ingest.js does not await batchEmbed()"
    )


def test_ingest_cmd__is_async():
    """AC1: runIngest must be declared as an async function."""
    with open(INGEST_CMD_PATH) as f:
        src = f.read()
    assert re.search(r"export\s+async\s+function\s+runIngest", src), (
        "runIngest is not declared as 'export async function runIngest'"
    )


def test_cli__handles_async_runingest():
    """AC1: cli.js must await or .catch() the Promise returned by runIngest()."""
    with open(CLI_PATH) as f:
        src = f.read()
    has_await = bool(re.search(r"await\s+runIngest\s*\(", src))
    has_chain = bool(re.search(r"runIngest\s*\(\s*\)\s*\.\s*(then|catch)", src))
    assert has_await or has_chain, (
        "cli.js does not await runIngest() or chain its Promise with .then/.catch"
    )


# ---------------------------------------------------------------------------
# AC2: Model and dim from env config, not hardcoded in multiple places
# ---------------------------------------------------------------------------


def test_embeddings_index__reads_embedding_model_from_env():
    """AC2: embeddings/index.js must read EMBEDDING_MODEL from process.env."""
    with open(EMBEDDINGS_INDEX_PATH) as f:
        src = f.read()
    assert "EMBEDDING_MODEL" in src, (
        "src/embeddings/index.js does not reference EMBEDDING_MODEL env var"
    )


def test_embeddings_index__reads_dim_from_env():
    """AC2: embeddings/index.js must read DIM from process.env."""
    with open(EMBEDDINGS_INDEX_PATH) as f:
        src = f.read()
    assert "DIM" in src, (
        "src/embeddings/index.js does not reference DIM env var"
    )


def test_embedder__does_not_hardcode_model_string():
    """AC2: embedder.js must not hardcode the model name string."""
    with open(EMBEDDER_PATH) as f:
        src = f.read()
    assert "all-MiniLM-L6-v2" not in src, (
        "src/data/embedder.js hardcodes the model name — must come from embeddings/index.js"
    )


def test_embedder__does_not_hardcode_dim_384():
    """AC2: embedder.js must not hardcode the dimension value 384 independently."""
    with open(EMBEDDER_PATH) as f:
        src = f.read()
    # dim should come from the embedder object, not a local constant
    assert not re.search(r"const\s+\w*[Dd]im\w*\s*=\s*384", src), (
        "src/data/embedder.js hardcodes DIM=384 as a local constant"
    )


# ---------------------------------------------------------------------------
# AC3: Ingest produces exactly 384-element FloatVectors per chunk
# ---------------------------------------------------------------------------


def test_ingest__produces_384_dim_vectors():
    """AC3: After ingest, every embedding in collection.json has exactly 384 elements."""
    r = run_ingest()
    assert r.returncode == 0, f"ingest failed (exit {r.returncode}): {r.stderr}"
    assert os.path.exists(COLLECTION_JSON), "collection.json not found after ingest"
    with open(COLLECTION_JSON) as f:
        rows = json.load(f)
    assert len(rows) > 0, "collection.json has no rows after ingest"
    for row in rows:
        emb = row.get("embedding")
        assert isinstance(emb, list), f"Row {row.get('id')} embedding is not a list"
        assert len(emb) == 384, (
            f"Row {row.get('id')} embedding has {len(emb)} dims, expected 384"
        )


def test_ingest__all_chunks_embedded():
    """AC3: Every chunk row has an embedding field (no chunks skipped)."""
    r = run_ingest()
    assert r.returncode == 0, f"ingest failed: {r.stderr}"
    with open(COLLECTION_JSON) as f:
        rows = json.load(f)
    for row in rows:
        assert "embedding" in row, f"Row {row.get('id')} is missing the embedding field"
        assert row["embedding"], f"Row {row.get('id')} has an empty embedding"


# ---------------------------------------------------------------------------
# AC4: Upsert-by-id — second ingest run produces no duplicates
# ---------------------------------------------------------------------------


def test_ingest__idempotent_no_duplicates():
    """AC4: Running ingest twice results in the same row count (upsert-by-id)."""
    r1 = run_ingest()
    assert r1.returncode == 0, f"First ingest failed: {r1.stderr}"
    with open(COLLECTION_JSON) as f:
        count_after_first = len(json.load(f))

    r2 = run_ingest()
    assert r2.returncode == 0, f"Second ingest failed: {r2.stderr}"
    with open(COLLECTION_JSON) as f:
        count_after_second = len(json.load(f))

    assert count_after_first == count_after_second, (
        f"Duplicate rows after second ingest: first={count_after_first}, second={count_after_second}"
    )


# ---------------------------------------------------------------------------
# AC5: README documents model download and env variables
# ---------------------------------------------------------------------------


def test_readme__mentions_model_download_size():
    """AC5: README must mention the ~90 MB model download."""
    with open(README_PATH) as f:
        readme = f.read()
    assert re.search(r"90\s*MB", readme, re.IGNORECASE), (
        "README does not mention the ~90 MB model download size"
    )


def test_readme__documents_embedding_model_env_var():
    """AC5: README must document the EMBEDDING_MODEL .env variable."""
    with open(README_PATH) as f:
        readme = f.read()
    assert "EMBEDDING_MODEL" in readme, (
        "README does not document the EMBEDDING_MODEL env variable"
    )


def test_readme__documents_dim_env_var():
    """AC5: README must document the DIM .env variable."""
    with open(README_PATH) as f:
        readme = f.read()
    assert "DIM" in readme, (
        "README does not document the DIM env variable"
    )


def test_readme__first_ingest_download_note():
    """AC5: README must contain a note that first ingest downloads the model."""
    with open(README_PATH) as f:
        readme = f.read()
    # Accept any phrasing that connects 'first' (or initial) ingest/run to a download
    has_note = (
        re.search(r"first\s+(ingest|run)", readme, re.IGNORECASE) and
        re.search(r"download", readme, re.IGNORECASE)
    )
    assert has_note, (
        "README does not contain a note about the first ingest run downloading the model"
    )
