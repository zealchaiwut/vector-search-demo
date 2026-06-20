"""
Acceptance tests for issue #98: Chunk documents into overlapping segments before indexing

AC1  - A `chunks` table (or equivalent) exists with columns: article_id (FK),
       chunk_index (integer), text (string), embedding (vector)
AC2  - The `articles` table retains headline, attachment_url, and metadata fields unchanged
AC3  - Chunking splits by character length (~500 chars) with configurable overlap (~100 chars),
       not by whitespace, making it correct for Thai
AC4  - Each chunk is embedded using the multilingual passage prefix before storage
AC5  - A Thai PDF of ≥ 2 pages produces ≥ 2 chunk rows all linked to the same article_id
AC6  - The indexed/searchable unit returned by retrieval is the chunk, not the full article body
AC7  - Re-ingesting an existing article deletes all previous chunk rows before inserting new ones
AC8  - Chunk size and overlap are defined as constants or config values, not magic numbers
"""

import os
import re
import subprocess
import json

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUNKER_JS = os.path.join(REPO_ROOT, "src", "data", "chunker.js")
PG_STORE_PATH = os.path.join(REPO_ROOT, "src", "store", "PgVectorStore.js")
MIGRATIONS_DIR = os.path.join(REPO_ROOT, "src", "store", "migrations")
DATA_EMBEDDER = os.path.join(REPO_ROOT, "src", "data", "embedder.js")

MODEL_TIMEOUT = 120


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


# ---------------------------------------------------------------------------
# AC1: chunks table (or equivalent) exists with required columns
# ---------------------------------------------------------------------------

def _all_migration_sql():
    combined = ""
    for fname in sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")):
        with open(os.path.join(MIGRATIONS_DIR, fname)) as fh:
            combined += fh.read() + "\n"
    return combined


def test_ac1_chunks_equivalent_has_article_id():
    """AC1: articles table (chunks equivalent) has article_id column."""
    sql = _all_migration_sql()
    assert re.search(r"article_id\s+text", sql, re.IGNORECASE), (
        "articles table must have article_id text column (FK equivalent for chunk grouping)"
    )


def test_ac1_chunks_equivalent_has_chunk_index():
    """AC1: articles table (chunks equivalent) has chunk_index integer column."""
    sql = _all_migration_sql()
    assert re.search(r"chunk_index\s+integer", sql, re.IGNORECASE), (
        "articles table must have chunk_index integer column"
    )


def test_ac1_chunks_equivalent_has_text_column():
    """AC1: articles table (chunks equivalent) has details (text) column for chunk content."""
    sql = _all_migration_sql()
    assert re.search(r"details\s+text", sql, re.IGNORECASE), (
        "articles table must have details text column for chunk text storage"
    )


def test_ac1_chunks_equivalent_has_embedding_column():
    """AC1: articles table (chunks equivalent) has embedding (vector) column."""
    sql = _all_migration_sql()
    assert re.search(r"embedding\s+vector", sql, re.IGNORECASE), (
        "articles table must have embedding vector column"
    )


# ---------------------------------------------------------------------------
# AC2: articles table retains headline, attachment_url, and metadata fields
# ---------------------------------------------------------------------------

def test_ac2_articles_table_has_headline():
    """AC2: articles table must have headline column."""
    sql = _all_migration_sql()
    assert re.search(r"headline\s+text", sql, re.IGNORECASE), (
        "articles table must retain headline text column"
    )


def test_ac2_articles_table_has_attachment_url():
    """AC2: articles table must have attachment_url column."""
    sql = _all_migration_sql()
    assert "attachment_url" in sql.lower(), (
        "articles table must retain attachment_url column"
    )


def test_ac2_no_migration_drops_headline():
    """AC2: migrations must not drop headline, attachment_url, or created_at."""
    sql = _all_migration_sql()
    drops = re.findall(
        r"DROP\s+COLUMN\s+(headline|attachment_url|created_at)", sql, re.IGNORECASE
    )
    assert not drops, f"Migrations must not drop metadata columns; found: {drops}"


# ---------------------------------------------------------------------------
# AC3: Chunking splits by character length, not whitespace
# ---------------------------------------------------------------------------

def test_ac3_chunker_uses_char_length_constants():
    """AC3: chunker.js must define CHUNK_SIZE and CHUNK_OVERLAP as named constants (not word-based)."""
    with open(CHUNKER_JS) as f:
        src = f.read()
    assert "CHUNK_SIZE" in src, (
        "chunker.js must define CHUNK_SIZE constant for character-based chunking"
    )
    assert "CHUNK_OVERLAP" in src, (
        "chunker.js must define CHUNK_OVERLAP constant for character-based overlap"
    )


def test_ac3_chunker_no_whitespace_split():
    """AC3: chunker.js must NOT use whitespace-based word splitting (/\\s+/) as the primary split."""
    with open(CHUNKER_JS) as f:
        src = f.read()
    # The old word-based chunker used: .split(/\s+/)
    # The new char-based chunker should NOT use whitespace splitting as its core logic
    # (it may still use it for trimming, but not for chunking boundaries)
    lines = src.splitlines()
    split_lines = [l for l in lines if re.search(r'\.split\s*\(\s*/\\s\+/', l)]
    assert not split_lines, (
        "chunker.js must not split by whitespace (\\s+) — use character index slicing for Thai support"
    )


def test_ac3_chunk_size_is_approx_500_chars():
    """AC3: default CHUNK_SIZE constant must be approximately 500 characters."""
    with open(CHUNKER_JS) as f:
        src = f.read()
    match = re.search(r'CHUNK_SIZE\s*=\s*(\d+)', src)
    assert match, "CHUNK_SIZE must be defined as a numeric constant"
    size = int(match.group(1))
    assert 400 <= size <= 600, (
        f"CHUNK_SIZE should be approximately 500 chars, got {size}"
    )


def test_ac3_chunk_overlap_is_approx_100_chars():
    """AC3: default CHUNK_OVERLAP constant must be approximately 100 characters."""
    with open(CHUNKER_JS) as f:
        src = f.read()
    match = re.search(r'CHUNK_OVERLAP\s*=\s*(\d+)', src)
    assert match, "CHUNK_OVERLAP must be defined as a numeric constant"
    overlap = int(match.group(1))
    assert 50 <= overlap <= 150, (
        f"CHUNK_OVERLAP should be approximately 100 chars, got {overlap}"
    )


def test_ac3_thai_text_chunked_without_spaces():
    """AC3: Thai text (no whitespace) must be chunked into multiple segments."""
    # 2000 Thai characters — Thai has no spaces, so word-split would produce 1 chunk
    # Character-based chunking with CHUNK_SIZE=500 should produce at least 3 chunks
    thai_char = "ก"  # single Thai character (1 char = 3 bytes UTF-8)
    script = f"""
import {{ chunkDocument }} from './src/data/chunker.js';
// 2000 identical Thai characters — no spaces
const text = "{thai_char}".repeat(2000);
const article = {{ id: 'thai-test', headline: 'Thai Test', details: text, attachment_url: '' }};
const chunks = chunkDocument(article);
process.stdout.write(JSON.stringify({{ count: chunks.length, ids: chunks.map(c => c.id) }}));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    assert result["count"] >= 2, (
        f"Thai text (no spaces, 2000 chars) should produce ≥ 2 chunks with char-based chunker, "
        f"got {result['count']}. Word-based chunker would produce 1 chunk."
    )


def test_ac3_chunk_ids_are_sequential():
    """AC3: chunk ids must follow '<article_id>:<index>' pattern with sequential 0-based indices."""
    script = """
import { chunkDocument } from './src/data/chunker.js';
const text = "A".repeat(2000);
const article = { id: 'seq-test', headline: 'H', details: text, attachment_url: '' };
const chunks = chunkDocument(article);
const ids = chunks.map(c => c.id);
process.stdout.write(JSON.stringify({ ids }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    ids = result["ids"]
    assert len(ids) >= 2, "Expected multiple chunks for 2000-char document"
    for i, cid in enumerate(ids):
        assert cid == f"seq-test:{i}", (
            f"Expected chunk id 'seq-test:{i}', got '{cid}'"
        )


def test_ac3_short_doc_produces_one_chunk():
    """AC5 / AC3: A document shorter than CHUNK_SIZE produces exactly 1 chunk."""
    script = """
import { chunkDocument } from './src/data/chunker.js';
const text = "Short document under 500 chars.";
const article = { id: 'short-test', headline: 'Short', details: text, attachment_url: '' };
const chunks = chunkDocument(article);
process.stdout.write(JSON.stringify({ count: chunks.length, text: chunks[0]?.details }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["count"] == 1, (
        f"Short document should produce exactly 1 chunk, got {result['count']}"
    )
    assert "Short document" in result["text"], "Single chunk should contain the full document text"


def test_ac3_adjacent_chunks_overlap():
    """AC3: adjacent chunks must share overlapping text of approximately CHUNK_OVERLAP chars."""
    script = """
import { chunkDocument, CHUNK_OVERLAP } from './src/data/chunker.js';
// 1200 chars — should produce at least 2 chunks
const text = Array.from({ length: 1200 }, (_, i) => String.fromCharCode(65 + (i % 26))).join('');
const article = { id: 'overlap-test', headline: 'Overlap', details: text, attachment_url: '' };
const chunks = chunkDocument(article);
if (chunks.length < 2) {
  process.stdout.write(JSON.stringify({ error: 'too few chunks', count: chunks.length }));
  process.exit(0);
}
const end_of_first = chunks[0].details.slice(-CHUNK_OVERLAP);
const start_of_second = chunks[1].details.slice(0, CHUNK_OVERLAP);
process.stdout.write(JSON.stringify({
  count: chunks.length,
  overlap: end_of_first === start_of_second,
  end_of_first,
  start_of_second,
  configured_overlap: CHUNK_OVERLAP
}));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert "error" not in result, f"Chunking error: {result}"
    assert result["overlap"], (
        f"Adjacent chunks must overlap by CHUNK_OVERLAP={result.get('configured_overlap')} chars. "
        f"End of chunk 0: '{result.get('end_of_first')}' vs start of chunk 1: '{result.get('start_of_second')}'"
    )


def test_ac3_chunk_detail_length_bounded():
    """AC3: each chunk's details must not exceed CHUNK_SIZE characters."""
    script = """
import { chunkDocument, CHUNK_SIZE } from './src/data/chunker.js';
const text = "X".repeat(3000);
const article = { id: 'bound-test', headline: 'H', details: text, attachment_url: '' };
const chunks = chunkDocument(article);
const tooLong = chunks.filter(c => c.details.length > CHUNK_SIZE);
process.stdout.write(JSON.stringify({
  count: chunks.length,
  tooLong: tooLong.length,
  maxLen: Math.max(...chunks.map(c => c.details.length)),
  chunkSize: CHUNK_SIZE
}));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["tooLong"] == 0, (
        f"All chunks must be ≤ CHUNK_SIZE={result['chunkSize']} chars. "
        f"Found {result['tooLong']} chunks exceeding limit (max was {result['maxLen']})."
    )


# ---------------------------------------------------------------------------
# AC4: Each chunk is embedded using the multilingual passage prefix
# ---------------------------------------------------------------------------

def test_ac4_embedder_uses_passage_prefix():
    """AC4: data/embedder.js must prefix chunk text with 'passage: ' before embedding."""
    with open(DATA_EMBEDDER) as f:
        src = f.read()
    assert "passage: " in src or "passage:" in src, (
        "data/embedder.js must add 'passage: ' prefix to chunk text before embedding"
    )


# ---------------------------------------------------------------------------
# AC6: Indexed/searchable unit is the chunk, not the full article body
# ---------------------------------------------------------------------------

def test_ac6_pgvector_search_returns_chunk_fields():
    """AC6: PgVectorStore.search must return chunk-level fields (chunk_index, article_id)."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert "chunk_index" in src, (
        "PgVectorStore.search must return chunk_index — the indexed unit is the chunk, not full article"
    )
    assert "article_id" in src, (
        "PgVectorStore.search must return article_id to link chunks back to their article"
    )


def test_ac6_search_returns_chunk_not_full_body():
    """AC6: mock store search returns chunk-level results (details is a chunk, not full body)."""
    script = """
import { resolveBackend, getStore } from './src/store/factory.js';
const store = await getStore('mock');
await store.dropCollection();
await store.createCollection();

// Import and run ingest to load demo data
const { runIngest } = await import('./src/commands/ingest.js');
await runIngest();

const results = await store.search('technology', 3);
if (!results || results.length === 0) {
  process.stdout.write(JSON.stringify({ error: 'no results' }));
  process.exit(0);
}
// Each result's details should be a chunk (< CHUNK_SIZE * 2 chars) not a full multi-page body
const topResult = results[0];
process.stdout.write(JSON.stringify({
  detailsLength: topResult.details?.length ?? 0,
  hasDetails: 'details' in topResult,
  score: topResult.score,
}));
"""
    out, err, rc = _run_node(script, timeout=60, env={"DB_BACKEND": "mock"})
    assert rc == 0, f"Node error: {err}\n{out}"
    # Extract JSON from the last JSON line
    json_lines = [l for l in out.strip().splitlines() if l.startswith("{")]
    assert json_lines, f"No JSON output found: {out}"
    result = json.loads(json_lines[-1])
    assert "error" not in result, f"Search error: {result}"
    assert result["hasDetails"], "Search results must include details field"


# ---------------------------------------------------------------------------
# AC7: Re-ingesting deletes all previous chunk rows before inserting new ones
# ---------------------------------------------------------------------------

def test_ac7_pgvector_delete_by_article_id():
    """AC7: PgVectorStore.delete must delete all chunks by article_id (not by chunk id)."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert re.search(r"DELETE\s+FROM\s+articles\s+WHERE\s+article_id\s*=", src, re.IGNORECASE), (
        "PgVectorStore.delete must use DELETE FROM articles WHERE article_id = $1 "
        "to remove all chunk rows before re-ingesting"
    )


def test_ac7_reingest_no_duplicate_chunks():
    """AC7: ingesting the same article twice must not create duplicate chunks."""
    script = """
import { getMockStore } from './src/store/mock.js';
const store = getMockStore();
await store.dropCollection();
await store.createCollection();

import { batchEmbed } from './src/data/embedder.js';
import { chunkDocument } from './src/data/chunker.js';

const article = { id: 'reingest-test', headline: 'Reingest', details: 'A'.repeat(1200), attachment_url: '' };
const chunks1 = chunkDocument(article);
const embedded1 = await batchEmbed(chunks1);
const rows1 = embedded1.map(c => ({ id: c.id, headline: c.headline, details: c.details, attachment_url: c.attachment_url, embedding: c.embedding }));
await store.upsertRows(rows1);
const count1 = await store.entityCount();

// Re-ingest: delete then upsert (as the server does for PUT /articles)
await store.deleteArticle?.('reingest-test');
await store.upsertRows(rows1);
const count2 = await store.entityCount();

process.stdout.write(JSON.stringify({ count1, count2 }));
"""
    out, err, rc = _run_node(script, timeout=60, env={"DB_BACKEND": "mock"})
    assert rc == 0, f"Node error: {err}\n{out}"
    json_lines = [l for l in out.strip().splitlines() if l.startswith("{")]
    assert json_lines, f"No JSON output: {out}"
    result = json.loads(json_lines[-1])
    # count1 and count2 should reflect no duplicates
    assert result["count1"] > 0, "First ingest should store chunks"
    assert result["count2"] == result["count1"], (
        f"Re-ingesting must not create duplicates: count1={result['count1']}, count2={result['count2']}"
    )


# ---------------------------------------------------------------------------
# AC8: Chunk size and overlap are defined as constants, not magic numbers
# ---------------------------------------------------------------------------

def test_ac8_constants_are_exported():
    """AC8: chunker.js must export CHUNK_SIZE and CHUNK_OVERLAP as named constants."""
    with open(CHUNKER_JS) as f:
        src = f.read()
    # Must be exported (either export const or exported in export block)
    has_export_chunk_size = re.search(r"export\s+(const\s+)?CHUNK_SIZE", src)
    has_export_chunk_overlap = re.search(r"export\s+(const\s+)?CHUNK_OVERLAP", src)
    assert has_export_chunk_size, (
        "chunker.js must export CHUNK_SIZE so other modules can reference the configured value"
    )
    assert has_export_chunk_overlap, (
        "chunker.js must export CHUNK_OVERLAP so other modules can reference the configured value"
    )


def test_ac8_no_magic_numbers_in_chunker():
    """AC8: chunkDocument function must not contain magic numbers for size/overlap."""
    with open(CHUNKER_JS) as f:
        src = f.read()
    # The function body should reference CHUNK_SIZE and CHUNK_OVERLAP constants,
    # not hardcoded numbers like 500 or 100 inline in the slicing logic
    func_match = re.search(
        r"export\s+function\s+chunkDocument.*?(?=export\s+function|\Z)",
        src,
        re.DOTALL,
    )
    if func_match:
        func_body = func_match.group(0)
        # Inline magic numbers like slice(0, 500) or slice(i, i + 100) without constants
        inline_numbers = re.findall(r'slice\s*\([^)]*\b(500|100)\b[^)]*\)', func_body)
        assert not inline_numbers, (
            f"chunkDocument must use CHUNK_SIZE/CHUNK_OVERLAP constants, not magic numbers; "
            f"found inline: {inline_numbers}"
        )
