"""
TDD acceptance tests for issue #5: Build ingestion pipeline for commander ingest command.

AC1 - commander ingest exits 0 and prints a summary matching "N docs / M chunks indexed"
AC2 - Collection entity count equals M (chunk count from summary)
AC3 - src/data/ contains isolated generator; ingest.js imports only public API (not internals)
AC4 - Generator produces ~15 docs spread across at least 5 distinct topic areas
AC5 - Each doc body chunked at ~120 words with ~30-word overlap
AC6 - Chunks batch-embedded before insertion (IDF built over full corpus)
AC7 - Each inserted row has: doc_id, chunk_id, title, text, attachment_name, embedding
AC8 - attachments/<doc_id>.txt exists and is non-empty for every document
AC9 - Idempotent: second run same entity count, no duplication
AC10 - Target files src/commands/ingest.js and src/data/*; cli.js routes ingest command
"""

import json
import os
import re
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INGEST_CMD_PATH = os.path.join(REPO_ROOT, "src", "commands", "ingest.js")
CLI_PATH = os.path.join(REPO_ROOT, "src", "cli.js")
DATA_DIR = os.path.join(REPO_ROOT, "src", "data")
GENERATOR_PATH = os.path.join(DATA_DIR, "generator.js")
CHUNKER_PATH = os.path.join(DATA_DIR, "chunker.js")
EMBEDDER_PATH = os.path.join(DATA_DIR, "embedder.js")
COLLECTION_PATH = os.path.join(DATA_DIR, "collection.js")
COLLECTION_JSON = os.path.join(REPO_ROOT, "collection.json")
ATTACHMENTS_DIR = os.path.join(REPO_ROOT, "attachments")


def run_ingest(timeout=30):
    """Run `commander ingest` via node cli.js; return CompletedProcess."""
    return subprocess.run(
        ["node", CLI_PATH, "ingest"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
    )


def parse_summary(stdout):
    """Extract (n_docs, m_chunks) from 'N docs / M chunks indexed' line."""
    m = re.search(r"(\d+)\s+docs\s*/\s*(\d+)\s+chunks\s+indexed", stdout)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


# ---------------------------------------------------------------------------
# AC10 — file structure
# ---------------------------------------------------------------------------


def test_ingest_pipeline__ingest_command_file_exists():
    """AC10: src/commands/ingest.js must exist."""
    assert os.path.exists(INGEST_CMD_PATH), f"ingest.js not found at {INGEST_CMD_PATH}"


def test_ingest_pipeline__data_dir_exists():
    """AC10: src/data/ directory must exist."""
    assert os.path.isdir(DATA_DIR), f"src/data/ directory not found at {DATA_DIR}"


def test_ingest_pipeline__data_modules_exist():
    """AC10: generator.js, chunker.js, embedder.js, collection.js must exist under src/data/."""
    for path in [GENERATOR_PATH, CHUNKER_PATH, EMBEDDER_PATH, COLLECTION_PATH]:
        assert os.path.exists(path), f"Expected module not found: {path}"


def test_ingest_pipeline__cli_routes_ingest():
    """AC10: cli.js must import/handle 'ingest' command."""
    assert os.path.exists(CLI_PATH), f"cli.js not found"
    with open(CLI_PATH) as f:
        src = f.read()
    assert "ingest" in src, "cli.js does not reference 'ingest' command"


# ---------------------------------------------------------------------------
# AC1 — commander ingest exits 0 with summary line
# ---------------------------------------------------------------------------


def test_ingest_pipeline__exits_zero():
    """AC1: commander ingest exits 0."""
    result = run_ingest()
    assert result.returncode == 0, (
        f"ingest exited {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_ingest_pipeline__prints_summary_line():
    """AC1: stdout contains 'N docs / M chunks indexed'."""
    result = run_ingest()
    assert result.returncode == 0, f"ingest failed: {result.stderr}"
    n_docs, m_chunks = parse_summary(result.stdout)
    assert n_docs is not None, f"Summary line not found in stdout:\n{result.stdout}"
    assert n_docs > 0, "N docs must be > 0"
    assert m_chunks > 0, "M chunks must be > 0"


# ---------------------------------------------------------------------------
# AC2 — collection entity count equals M
# ---------------------------------------------------------------------------


def test_ingest_pipeline__collection_entity_count_equals_chunks():
    """AC2: collection.json entity count must equal M from the summary."""
    result = run_ingest()
    assert result.returncode == 0, f"ingest failed: {result.stderr}"
    _, m_chunks = parse_summary(result.stdout)
    assert m_chunks is not None, "Could not parse summary"

    assert os.path.exists(COLLECTION_JSON), f"collection.json not found at {COLLECTION_JSON}"
    with open(COLLECTION_JSON) as f:
        rows = json.load(f)
    assert len(rows) == m_chunks, (
        f"Collection has {len(rows)} rows but summary said {m_chunks} chunks"
    )


# ---------------------------------------------------------------------------
# AC3 — generator isolation
# ---------------------------------------------------------------------------


def test_ingest_pipeline__generator_has_no_import_from_commands():
    """AC3: generator.js must not import from src/commands/."""
    with open(GENERATOR_PATH) as f:
        src = f.read()
    # Check no import statement references commands/ — a comment mentioning it is fine
    assert not re.search(r'import\s.*["\'].*commands', src), (
        "generator.js must not have an import from src/commands/"
    )


def test_ingest_pipeline__ingest_imports_only_public_api():
    """AC3: ingest.js should import from src/data/ (public API), not internals."""
    with open(INGEST_CMD_PATH) as f:
        src = f.read()
    assert "../data/" in src or "./data/" in src or "src/data" in src, (
        "ingest.js must import from src/data/"
    )


# ---------------------------------------------------------------------------
# AC4 — generator produces ~15 docs across 5+ topic areas
# ---------------------------------------------------------------------------


def _load_generated_docs():
    """Run generator.js inline to get documents array."""
    script = """
import { generateDocuments } from './src/data/generator.js';
const docs = generateDocuments();
process.stdout.write(JSON.stringify(docs));
"""
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=10,
    )
    assert result.returncode == 0, f"generator failed: {result.stderr}"
    return json.loads(result.stdout)


def test_ingest_pipeline__generator_produces_roughly_15_docs():
    """AC4: generator produces between 10 and 20 documents (target ~15)."""
    docs = _load_generated_docs()
    assert 10 <= len(docs) <= 20, f"Expected ~15 docs, got {len(docs)}"


def test_ingest_pipeline__generator_docs_have_required_fields():
    """AC4: each generated doc has doc_id, title, body."""
    docs = _load_generated_docs()
    for doc in docs:
        assert "doc_id" in doc, f"Missing doc_id in: {doc}"
        assert "title" in doc, f"Missing title in: {doc}"
        assert "body" in doc, f"Missing body in: {doc}"
        assert doc["body"].strip(), f"Empty body for doc {doc.get('doc_id')}"


def test_ingest_pipeline__generator_spans_at_least_5_topic_areas():
    """AC4: documents span at least 5 distinct topic areas via doc_id prefix or topic field."""
    docs = _load_generated_docs()
    # Check for 'topic' field or infer diversity from doc_id prefixes
    if docs and "topic" in docs[0]:
        topics = {d["topic"] for d in docs}
    else:
        # Infer from doc_id prefix pattern e.g. "infra-001", "sec-001"
        prefixes = set()
        for d in docs:
            doc_id = d.get("doc_id", "")
            # Extract alphabetic prefix
            m = re.match(r"([a-z]+)", doc_id)
            if m:
                prefixes.add(m.group(1))
        topics = prefixes
    assert len(topics) >= 5, (
        f"Expected at least 5 topic areas, found {len(topics)}: {topics}"
    )


# ---------------------------------------------------------------------------
# AC5 — chunking at ~120 words with ~30-word overlap
# ---------------------------------------------------------------------------


def _load_chunks_for_doc(doc_body, doc_id="test-doc"):
    """Run chunker on a sample document and return chunks."""
    script = f"""
import {{ chunkDocument }} from './src/data/chunker.js';
const doc = {{ doc_id: {json.dumps(doc_id)}, title: 'Test Doc', body: {json.dumps(doc_body)} }};
const chunks = chunkDocument(doc);
process.stdout.write(JSON.stringify(chunks));
"""
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=10,
    )
    assert result.returncode == 0, f"chunker failed: {result.stderr}"
    return json.loads(result.stdout)


def test_ingest_pipeline__chunks_have_required_fields():
    """AC5/AC7: each chunk has doc_id, chunk_id, title, text, attachment_name."""
    body = " ".join(f"word{i}" for i in range(300))
    chunks = _load_chunks_for_doc(body)
    assert len(chunks) > 0, "Expected at least one chunk"
    for c in chunks:
        for field in ["doc_id", "chunk_id", "title", "text", "attachment_name"]:
            assert field in c, f"Chunk missing field '{field}': {c}"


def test_ingest_pipeline__chunk_word_count_approx_120():
    """AC5: each chunk (except last) has ~120 words (within 10% tolerance)."""
    body = " ".join(f"word{i}" for i in range(500))
    chunks = _load_chunks_for_doc(body)
    # Check all but the last chunk
    for chunk in chunks[:-1]:
        word_count = len(chunk["text"].split())
        assert 100 <= word_count <= 140, (
            f"Expected ~120 words per chunk, got {word_count}: {chunk['chunk_id']}"
        )


def test_ingest_pipeline__chunk_overlap_approx_30_words():
    """AC5: consecutive chunks share ~30 words of overlap."""
    body = " ".join(f"word{i}" for i in range(500))
    chunks = _load_chunks_for_doc(body)
    if len(chunks) < 2:
        pytest.skip("Need at least 2 chunks to verify overlap")
    # Compare last words of chunk N with first words of chunk N+1
    for i in range(len(chunks) - 1):
        words_a = chunks[i]["text"].split()
        words_b = chunks[i + 1]["text"].split()
        # Count overlapping suffix/prefix
        overlap = 0
        for j in range(1, min(len(words_a), len(words_b)) + 1):
            if words_a[-j:] == words_b[:j]:
                overlap = j
        assert 20 <= overlap <= 40, (
            f"Expected ~30-word overlap between chunks {i} and {i+1}, got {overlap}"
        )


def test_ingest_pipeline__chunk_id_format():
    """AC5: chunk_id follows pattern <doc_id>:<index>."""
    body = " ".join(f"word{i}" for i in range(300))
    chunks = _load_chunks_for_doc(body, "test-doc")
    for i, c in enumerate(chunks):
        assert c["chunk_id"] == f"test-doc:{i}", (
            f"Expected chunk_id 'test-doc:{i}', got '{c['chunk_id']}'"
        )


def test_ingest_pipeline__attachment_name_format():
    """AC5: attachment_name equals <doc_id>.txt."""
    body = " ".join(f"word{i}" for i in range(300))
    chunks = _load_chunks_for_doc(body, "test-doc")
    for c in chunks:
        assert c["attachment_name"] == "test-doc.txt", (
            f"Expected attachment_name 'test-doc.txt', got '{c['attachment_name']}'"
        )


# ---------------------------------------------------------------------------
# AC6 — batch embedding (IDF built over full corpus)
# ---------------------------------------------------------------------------


def test_ingest_pipeline__embedder_batch_processes_all_chunks():
    """AC6: batchEmbed returns same number of chunks with embedding field added."""
    script = """
import { batchEmbed } from './src/data/embedder.js';
const chunks = [
  { doc_id: 'd1', chunk_id: 'd1:0', title: 'T1', text: 'hello world foo bar baz', attachment_name: 'd1.txt' },
  { doc_id: 'd2', chunk_id: 'd2:0', title: 'T2', text: 'world baz qux quux corge', attachment_name: 'd2.txt' },
];
const result = batchEmbed(chunks);
process.stdout.write(JSON.stringify(result));
"""
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=10,
    )
    assert result.returncode == 0, f"embedder failed: {result.stderr}"
    embedded = json.loads(result.stdout)
    assert len(embedded) == 2, "batchEmbed must return same count as input"
    for chunk in embedded:
        assert "embedding" in chunk, "Each chunk must have 'embedding' field after batchEmbed"
        assert isinstance(chunk["embedding"], list), "embedding must be a list"
        assert len(chunk["embedding"]) > 0, "embedding must be non-empty"
        # All values must be finite floats
        for v in chunk["embedding"]:
            assert isinstance(v, (int, float)), f"Embedding value not numeric: {v}"


def test_ingest_pipeline__embeddings_are_unit_vectors():
    """AC6: embeddings are L2-normalized (unit vectors, norm ≈ 1.0)."""
    script = """
import { batchEmbed } from './src/data/embedder.js';
const chunks = [
  { doc_id: 'd1', chunk_id: 'd1:0', title: 'T1', text: 'hello world foo bar baz qux', attachment_name: 'd1.txt' },
  { doc_id: 'd2', chunk_id: 'd2:0', title: 'T2', text: 'machine learning neural network', attachment_name: 'd2.txt' },
];
const result = batchEmbed(chunks);
process.stdout.write(JSON.stringify(result.map(c => c.embedding)));
"""
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=10,
    )
    assert result.returncode == 0, f"embedder failed: {result.stderr}"
    embeddings = json.loads(result.stdout)
    for emb in embeddings:
        norm = sum(v * v for v in emb) ** 0.5
        assert abs(norm - 1.0) < 0.01, f"Embedding norm {norm:.4f} not close to 1.0"


# ---------------------------------------------------------------------------
# AC7 — row schema in collection
# ---------------------------------------------------------------------------


def test_ingest_pipeline__collection_rows_have_required_schema():
    """AC7: each row in collection.json has doc_id, chunk_id, title, text, attachment_name, embedding."""
    result = run_ingest()
    assert result.returncode == 0, f"ingest failed: {result.stderr}"
    assert os.path.exists(COLLECTION_JSON), "collection.json not found"
    with open(COLLECTION_JSON) as f:
        rows = json.load(f)
    required = {"doc_id", "chunk_id", "title", "text", "attachment_name", "embedding"}
    for row in rows:
        missing = required - set(row.keys())
        assert not missing, f"Row missing fields {missing}: {row.get('chunk_id')}"


def test_ingest_pipeline__row_embedding_is_list_of_floats():
    """AC7: embedding field is a list of numeric values."""
    run_ingest()
    with open(COLLECTION_JSON) as f:
        rows = json.load(f)
    assert len(rows) > 0
    for row in rows[:3]:  # spot-check first 3
        emb = row["embedding"]
        assert isinstance(emb, list) and len(emb) > 0, f"Bad embedding in row {row['chunk_id']}"
        assert all(isinstance(v, (int, float)) for v in emb), "Non-numeric embedding value"


# ---------------------------------------------------------------------------
# AC8 — attachments/<doc_id>.txt exists and non-empty
# ---------------------------------------------------------------------------


def test_ingest_pipeline__attachments_dir_created():
    """AC8: attachments/ directory must exist after ingest."""
    result = run_ingest()
    assert result.returncode == 0, f"ingest failed: {result.stderr}"
    assert os.path.isdir(ATTACHMENTS_DIR), f"attachments/ dir not found at {ATTACHMENTS_DIR}"


def test_ingest_pipeline__one_attachment_per_doc():
    """AC8: exactly N .txt files in attachments/ matching doc count from summary."""
    result = run_ingest()
    assert result.returncode == 0, f"ingest failed: {result.stderr}"
    n_docs, _ = parse_summary(result.stdout)
    txt_files = [f for f in os.listdir(ATTACHMENTS_DIR) if f.endswith(".txt")]
    assert len(txt_files) == n_docs, (
        f"Expected {n_docs} .txt files in attachments/, found {len(txt_files)}"
    )


def test_ingest_pipeline__attachment_files_non_empty():
    """AC8: every attachment file is non-empty."""
    run_ingest()
    txt_files = [f for f in os.listdir(ATTACHMENTS_DIR) if f.endswith(".txt")]
    assert len(txt_files) > 0, "No attachment files found"
    for fname in txt_files:
        path = os.path.join(ATTACHMENTS_DIR, fname)
        assert os.path.getsize(path) > 0, f"Attachment file is empty: {fname}"


def test_ingest_pipeline__attachment_name_matches_doc_id():
    """AC8: each attachment file is named <doc_id>.txt matching rows in collection."""
    run_ingest()
    with open(COLLECTION_JSON) as f:
        rows = json.load(f)
    doc_ids = {row["doc_id"] for row in rows}
    for doc_id in doc_ids:
        expected = os.path.join(ATTACHMENTS_DIR, f"{doc_id}.txt")
        assert os.path.exists(expected), f"Missing attachment: {doc_id}.txt"


# ---------------------------------------------------------------------------
# AC9 — idempotency
# ---------------------------------------------------------------------------


def test_ingest_pipeline__idempotent_entity_count():
    """AC9: running ingest twice gives same entity count (not doubled)."""
    r1 = run_ingest()
    assert r1.returncode == 0, f"First ingest failed: {r1.stderr}"
    _, m1 = parse_summary(r1.stdout)

    r2 = run_ingest()
    assert r2.returncode == 0, f"Second ingest failed: {r2.stderr}"
    _, m2 = parse_summary(r2.stdout)

    assert m1 == m2, f"Chunk counts differ between runs: {m1} vs {m2}"

    with open(COLLECTION_JSON) as f:
        rows = json.load(f)
    assert len(rows) == m2, (
        f"Collection has {len(rows)} rows but second run said {m2} chunks"
    )


def test_ingest_pipeline__idempotent_attachment_count():
    """AC9: running ingest twice gives same number of attachment files."""
    r1 = run_ingest()
    assert r1.returncode == 0
    n1, _ = parse_summary(r1.stdout)

    r2 = run_ingest()
    assert r2.returncode == 0
    n2, _ = parse_summary(r2.stdout)

    assert n1 == n2, f"Doc counts differ between runs: {n1} vs {n2}"
    txt_files = [f for f in os.listdir(ATTACHMENTS_DIR) if f.endswith(".txt")]
    assert len(txt_files) == n2, (
        f"Expected {n2} attachment files after second run, found {len(txt_files)}"
    )
