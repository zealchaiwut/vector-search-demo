"""
Tests for issue #102: Chunk documents into overlapping vectors for semantic search

Acceptance Criteria:
  AC1  - A `chunks` table (or equivalent rows) exists with article_id (FK),
         chunk_index (integer), text (text), embedding (vector(384))
  AC2  - Article record retains headline, attachment_url, metadata; body embeddings
         move entirely to the chunks table
  AC3  - Chunking splits by character length (not whitespace) with configurable
         CHUNK_SIZE and CHUNK_OVERLAP env vars (defaults: 400 chars / 80 chars)
  AC4  - Each chunk embedded using multilingual passage prefix before storage
  AC5  - Create, edit, ingest, and PDF-upload flows invoke chunking + embedding
  AC6  - Edit or re-ingest deletes all existing chunks before writing new ones
  AC7  - Body > CHUNK_SIZE produces ≥ 2 chunk rows linked to same article_id
  AC8  - Body < CHUNK_SIZE produces exactly 1 chunk row
  AC9  - Every chunk row has a non-null embedding vector
  AC10 - Changing CHUNK_SIZE / CHUNK_OVERLAP env vars and re-ingesting reflects
         new chunking without leftover old-size chunks
"""

import json
import os
import re
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUNKER_JS = os.path.join(REPO_ROOT, "src", "data", "chunker.js")
EMBEDDER_JS = os.path.join(REPO_ROOT, "src", "data", "embedder.js")
PG_STORE_PATH = os.path.join(REPO_ROOT, "src", "store", "PgVectorStore.js")
SERVER_MJS = os.path.join(REPO_ROOT, "src", "server.mjs")
INGEST_JS = os.path.join(REPO_ROOT, "src", "commands", "ingest.js")
MIGRATIONS_DIR = os.path.join(REPO_ROOT, "src", "store", "migrations")

MODEL_TIMEOUT = 120


def _run_node(script, timeout=MODEL_TIMEOUT, env=None):
    run_env = os.environ.copy()
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


def _all_migration_sql():
    combined = ""
    for fname in sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")):
        with open(os.path.join(MIGRATIONS_DIR, fname)) as fh:
            combined += fh.read() + "\n"
    return combined


# ---------------------------------------------------------------------------
# AC1: chunks table (or equivalent) has required columns
# ---------------------------------------------------------------------------

def test_ac1_chunks_equivalent_has_article_id_column():
    """AC1: migrations define article_id column for grouping chunks by article."""
    sql = _all_migration_sql()
    assert re.search(r"article_id\s+text", sql, re.IGNORECASE), (
        "chunks equivalent (articles table) must have article_id text column"
    )


def test_ac1_chunks_equivalent_has_chunk_index_column():
    """AC1: migrations define chunk_index integer column."""
    sql = _all_migration_sql()
    assert re.search(r"chunk_index\s+integer", sql, re.IGNORECASE), (
        "chunks equivalent must have chunk_index integer column"
    )


def test_ac1_chunks_equivalent_has_text_column():
    """AC1: migrations define a text column for chunk body (details or text)."""
    sql = _all_migration_sql()
    assert re.search(r"(details|text)\s+text", sql, re.IGNORECASE), (
        "chunks equivalent must have a text/details text column for chunk content"
    )


def test_ac1_chunks_equivalent_has_embedding_vector_column():
    """AC1: migrations define embedding vector(384) column."""
    sql = _all_migration_sql()
    assert re.search(r"embedding\s+vector", sql, re.IGNORECASE), (
        "chunks equivalent must have embedding vector column"
    )


def test_ac1_pg_store_handles_article_id():
    """AC1: PgVectorStore handles article_id for grouping chunks."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert "article_id" in src, "PgVectorStore must use article_id to group chunks"


def test_ac1_pg_store_handles_chunk_index():
    """AC1: PgVectorStore handles chunk_index for ordering chunks."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert "chunk_index" in src, "PgVectorStore must use chunk_index to order chunks"


# ---------------------------------------------------------------------------
# AC2: Article record retains headline, attachment_url, metadata
# ---------------------------------------------------------------------------

def test_ac2_migrations_retain_headline():
    """AC2: migrations do not drop headline column."""
    sql = _all_migration_sql()
    drops = re.findall(r"DROP\s+COLUMN\s+headline", sql, re.IGNORECASE)
    assert not drops, f"Migrations must not drop headline column: {drops}"
    assert re.search(r"headline\s+text", sql, re.IGNORECASE), (
        "articles table must retain headline text column"
    )


def test_ac2_migrations_retain_attachment_url():
    """AC2: migrations do not drop attachment_url column."""
    sql = _all_migration_sql()
    drops = re.findall(r"DROP\s+COLUMN\s+attachment_url", sql, re.IGNORECASE)
    assert not drops, f"Migrations must not drop attachment_url column: {drops}"
    assert "attachment_url" in sql.lower(), (
        "articles table must retain attachment_url column"
    )


def test_ac2_pg_store_upsert_stores_headline():
    """AC2: PgVectorStore.upsert stores headline in chunk rows."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert "headline" in src, "PgVectorStore.upsert must store headline with each chunk row"


# ---------------------------------------------------------------------------
# AC3: Chunking by character length, configurable via env vars, defaults 400/80
# ---------------------------------------------------------------------------

def test_ac3_chunk_size_default_is_400():
    """AC3: CHUNK_SIZE default must be exactly 400 characters."""
    with open(CHUNKER_JS) as f:
        src = f.read()
    # Find the default value: look for 400 near CHUNK_SIZE
    match = re.search(r"CHUNK_SIZE.*?(\d+)", src)
    assert match, "CHUNK_SIZE must be defined"
    # Run node to get the actual resolved default (no env var override)
    script = """
import { CHUNK_SIZE } from './src/data/chunker.js';
process.stdout.write(String(CHUNK_SIZE));
"""
    out, err, rc = _run_node(script, env={"CHUNK_SIZE": "", "CHUNK_OVERLAP": ""})
    assert rc == 0, f"Node error: {err}"
    size = int(out.strip())
    assert size == 400, (
        f"CHUNK_SIZE default must be 400 chars (got {size}). "
        f"Issue #102 AC3 requires default of 400, not 500."
    )


def test_ac3_chunk_overlap_default_is_80():
    """AC3: CHUNK_OVERLAP default must be exactly 80 characters."""
    script = """
import { CHUNK_OVERLAP } from './src/data/chunker.js';
process.stdout.write(String(CHUNK_OVERLAP));
"""
    out, err, rc = _run_node(script, env={"CHUNK_SIZE": "", "CHUNK_OVERLAP": ""})
    assert rc == 0, f"Node error: {err}"
    overlap = int(out.strip())
    assert overlap == 80, (
        f"CHUNK_OVERLAP default must be 80 chars (got {overlap}). "
        f"Issue #102 AC3 requires default of 80, not 100."
    )


def test_ac3_chunk_size_configurable_via_env_var():
    """AC3: CHUNK_SIZE env var changes actual chunk character length."""
    script = """
import { chunkDocument } from './src/data/chunker.js';
const body = 'X'.repeat(500);
const article = { id: 't', headline: 'H', details: body, attachment_url: '' };
const chunks = chunkDocument(article);
const maxLen = Math.max(...chunks.map(c => c.details.length));
process.stdout.write(JSON.stringify({ count: chunks.length, maxLen }));
"""
    out, err, rc = _run_node(script, env={"CHUNK_SIZE": "200", "CHUNK_OVERLAP": "40"})
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["maxLen"] <= 200, (
        f"With CHUNK_SIZE=200 all chunks must be ≤ 200 chars; max was {result['maxLen']}"
    )
    assert result["count"] >= 2, (
        f"500-char body with CHUNK_SIZE=200 must produce ≥ 2 chunks; got {result['count']}"
    )


def test_ac3_chunk_overlap_configurable_via_env_var():
    """AC3: CHUNK_OVERLAP env var changes the stride between chunks."""
    # With zero overlap, stride = chunkSize, so count = ceil(len / chunkSize)
    # With 50% overlap, stride = chunkSize/2, so count is higher
    script = """
import { chunkDocument } from './src/data/chunker.js';
const body = 'Y'.repeat(500);
const article = { id: 't2', headline: 'H', details: body, attachment_url: '' };
const chunks = chunkDocument(article);
process.stdout.write(JSON.stringify({ count: chunks.length }));
"""
    # High overlap (CHUNK_OVERLAP=190 with CHUNK_SIZE=200) → stride=10 → many chunks
    out_high, err, rc = _run_node(
        script, env={"CHUNK_SIZE": "200", "CHUNK_OVERLAP": "190"}
    )
    assert rc == 0, f"Node error: {err}"
    # Low overlap (CHUNK_OVERLAP=0 with CHUNK_SIZE=200) → stride=200 → fewer chunks
    out_low, err, rc = _run_node(
        script, env={"CHUNK_SIZE": "200", "CHUNK_OVERLAP": "0"}
    )
    assert rc == 0, f"Node error: {err}"
    high = json.loads(out_high)["count"]
    low = json.loads(out_low)["count"]
    assert high > low, (
        f"Higher CHUNK_OVERLAP must produce more chunks: "
        f"high_overlap={high} vs low_overlap={low}"
    )


def test_ac3_chunker_uses_character_based_splitting():
    """AC3: chunker.js uses character index slicing, not whitespace splitting."""
    with open(CHUNKER_JS) as f:
        src = f.read()
    assert re.search(r"\.slice\s*\(", src), (
        "chunker.js must use text.slice() for character-based chunking"
    )
    word_splits = re.findall(r"\.split\s*\(\s*/\\s\+/", src)
    assert not word_splits, (
        "chunker.js must not use .split(/\\s+/) — use character slicing for Thai"
    )


def test_ac3_chunker_exports_chunk_size():
    """AC3: chunker.js exports CHUNK_SIZE."""
    with open(CHUNKER_JS) as f:
        src = f.read()
    assert re.search(r"export\s+(const\s+)?CHUNK_SIZE", src), (
        "chunker.js must export CHUNK_SIZE"
    )


def test_ac3_chunker_exports_chunk_overlap():
    """AC3: chunker.js exports CHUNK_OVERLAP."""
    with open(CHUNKER_JS) as f:
        src = f.read()
    assert re.search(r"export\s+(const\s+)?CHUNK_OVERLAP", src), (
        "chunker.js must export CHUNK_OVERLAP"
    )


# ---------------------------------------------------------------------------
# AC4: Each chunk embedded using multilingual passage prefix
# ---------------------------------------------------------------------------

def test_ac4_embedder_uses_passage_prefix():
    """AC4: embedder.js applies 'passage: ' prefix before embedding."""
    with open(EMBEDDER_JS) as f:
        src = f.read()
    assert re.search(r"passage:\s*['\"]\s*\$\{|passage:\s*['\"]|`passage:", src) or \
           "passage: " in src or "'passage: '" in src or '"passage: "' in src, (
        "embedder.js must apply 'passage: ' prefix to chunk text before embedding"
    )


# ---------------------------------------------------------------------------
# AC5: Create, edit, ingest, and PDF-upload flows invoke chunking pipeline
# ---------------------------------------------------------------------------

def test_ac5_create_flow_uses_chunk_document():
    """AC5: POST /articles (create flow) calls chunkDocument before embedding."""
    with open(SERVER_MJS) as f:
        src = f.read()
    # Find POST /articles handler block
    create_match = re.search(
        r'pathname === "/articles"[\s\S]*?jsonResponse\(res, 201',
        src,
    )
    assert create_match, "Could not find POST /articles handler in server.mjs"
    block = create_match.group(0)
    assert "chunkDocument" in block, (
        "POST /articles must call chunkDocument to chunk the body before embedding"
    )
    assert "batchEmbed" in block, (
        "POST /articles must call batchEmbed after chunking"
    )


def test_ac5_edit_flow_uses_chunk_document():
    """AC5: PUT /articles/:id (edit flow) calls chunkDocument before embedding."""
    with open(SERVER_MJS) as f:
        src = f.read()
    put_match = re.search(
        r'req\.method === "PUT"[\s\S]*?jsonResponse\(res, 200',
        src,
    )
    assert put_match, "Could not find PUT /articles/:id handler in server.mjs"
    block = put_match.group(0)
    assert "chunkDocument" in block, (
        "PUT /articles/:id must call chunkDocument to re-chunk the updated body"
    )
    assert "batchEmbed" in block, (
        "PUT /articles/:id must call batchEmbed after chunking"
    )


def test_ac5_ingest_flow_uses_chunk_documents():
    """AC5: ingest.js (ingest flow) calls chunkDocuments before embedding."""
    with open(INGEST_JS) as f:
        src = f.read()
    assert "chunkDocument" in src or "chunkDocuments" in src, (
        "ingest.js must call chunkDocument(s) to chunk articles before embedding"
    )
    assert "batchEmbed" in src, (
        "ingest.js must call batchEmbed after chunking"
    )


def test_ac5_bulk_create_flow_uses_chunk_document():
    """AC5: POST /articles/bulk (bulk ingest flow) calls chunkDocument."""
    with open(SERVER_MJS) as f:
        src = f.read()
    bulk_match = re.search(
        r'pathname === "/articles/bulk"[\s\S]*?jsonResponse\(res, 200',
        src,
    )
    assert bulk_match, "Could not find POST /articles/bulk handler in server.mjs"
    block = bulk_match.group(0)
    assert "chunkDocument" in block, (
        "POST /articles/bulk must call chunkDocument for each row"
    )


def test_ac5_pdf_upload_triggers_create_flow():
    """AC5: PDF upload flow confirms article via POST /articles which chunks+embeds."""
    with open(SERVER_MJS) as f:
        src = f.read()
    # The PDF upload endpoint returns extracted text; the Confirm button POSTs to /articles
    # which does the chunking. Verify upload endpoint itself does NOT persist.
    upload_match = re.search(
        r'pathname === "/api/upload-pdf"[\s\S]*?(?=\n  // GET /uploads/)',
        src,
    )
    assert upload_match, "Could not locate POST /api/upload-pdf handler"
    block = upload_match.group(0)
    assert "chunkDocument" not in block, (
        "POST /api/upload-pdf must NOT chunk — extract only; chunking happens on POST /articles"
    )
    assert "upsertRows" not in block, (
        "POST /api/upload-pdf must NOT persist — only POST /articles (Confirm) persists"
    )


# ---------------------------------------------------------------------------
# AC6: Edit or re-ingest deletes all existing chunks before writing new ones
# ---------------------------------------------------------------------------

def test_ac6_edit_flow_deletes_before_reinserting():
    """AC6: PUT /articles/:id deletes all chunk rows before writing new chunks."""
    with open(SERVER_MJS) as f:
        src = f.read()
    put_match = re.search(
        r'req\.method === "PUT"[\s\S]*?jsonResponse\(res, 200',
        src,
    )
    assert put_match, "Could not find PUT /articles/:id handler"
    block = put_match.group(0)
    # deleteArticle must appear BEFORE chunkDocument in the edit block
    delete_pos = block.find("deleteArticle")
    chunk_pos = block.find("chunkDocument")
    assert delete_pos != -1, (
        "PUT /articles/:id must call deleteArticle to clear old chunks"
    )
    assert chunk_pos != -1, "PUT /articles/:id must call chunkDocument for new chunks"
    assert delete_pos < chunk_pos, (
        "deleteArticle must be called BEFORE chunkDocument to avoid stale chunks"
    )


def test_ac6_pg_store_delete_removes_all_chunks_by_article_id():
    """AC6: PgVectorStore.delete removes all chunk rows for a given article_id."""
    with open(PG_STORE_PATH) as f:
        src = f.read()
    assert re.search(
        r"DELETE\s+FROM\s+articles\s+WHERE\s+article_id\s*=", src, re.IGNORECASE
    ), (
        "PgVectorStore.delete must use 'DELETE FROM articles WHERE article_id = $1' "
        "to remove all chunks for an article before re-ingesting"
    )


def test_ac6_no_duplicate_chunks_on_reingest():
    """AC6: ingesting the same article twice must not create duplicate chunks."""
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

// Re-ingest: deleteArticle then upsert (mimics PUT /articles handler)
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
    assert result["count1"] > 0, "First ingest should store at least one chunk"
    assert result["count2"] == result["count1"], (
        f"Re-ingesting must not create duplicates: count1={result['count1']}, count2={result['count2']}"
    )


# ---------------------------------------------------------------------------
# AC7: Body > CHUNK_SIZE produces ≥ 2 chunk rows
# ---------------------------------------------------------------------------

def test_ac7_long_body_produces_multiple_chunks():
    """AC7: Article body longer than CHUNK_SIZE (400) produces ≥ 2 chunks."""
    script = """
import { chunkDocument, CHUNK_SIZE } from './src/data/chunker.js';
// 2 × CHUNK_SIZE guarantees at least 2 chunks
const body = 'A'.repeat(CHUNK_SIZE * 2 + 1);
const article = { id: 'long-test', headline: 'Long', details: body, attachment_url: '' };
const chunks = chunkDocument(article);
process.stdout.write(JSON.stringify({ count: chunks.length, chunkSize: CHUNK_SIZE }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["count"] >= 2, (
        f"Body of {result['chunkSize'] * 2 + 1} chars must produce ≥ 2 chunks, "
        f"got {result['count']}"
    )


def test_ac7_all_chunks_share_same_article_id():
    """AC7: all chunk rows for a long document link to the same article_id."""
    script = """
import { chunkDocument, CHUNK_SIZE } from './src/data/chunker.js';
const body = 'B'.repeat(CHUNK_SIZE * 2 + 1);
const article = { id: 'artid-test', headline: 'H', details: body, attachment_url: '' };
const chunks = chunkDocument(article);
// Each chunk id is '<article_id>:<chunk_index>'
const articleIds = chunks.map(c => c.id.split(':')[0]);
const allSame = articleIds.every(aid => aid === 'artid-test');
process.stdout.write(JSON.stringify({ allSame, count: chunks.length, articleIds }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["allSame"], (
        f"All chunks must share the same article_id prefix; got: {result['articleIds']}"
    )


# ---------------------------------------------------------------------------
# AC8: Body < CHUNK_SIZE produces exactly 1 chunk row
# ---------------------------------------------------------------------------

def test_ac8_short_body_produces_exactly_one_chunk():
    """AC8: Article body shorter than CHUNK_SIZE (400) produces exactly 1 chunk."""
    script = """
import { chunkDocument, CHUNK_SIZE } from './src/data/chunker.js';
const body = 'Short body under chunk size.';
const article = { id: 'short-test', headline: 'Short', details: body, attachment_url: '' };
const chunks = chunkDocument(article);
process.stdout.write(JSON.stringify({ count: chunks.length, chunkSize: CHUNK_SIZE }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["count"] == 1, (
        f"Body shorter than CHUNK_SIZE={result['chunkSize']} must produce exactly 1 chunk, "
        f"got {result['count']}"
    )


def test_ac8_exactly_chunk_size_body_produces_one_chunk():
    """AC8: Article body of exactly CHUNK_SIZE chars produces exactly 1 chunk."""
    script = """
import { chunkDocument, CHUNK_SIZE } from './src/data/chunker.js';
const body = 'X'.repeat(CHUNK_SIZE);
const article = { id: 'exact-test', headline: 'Exact', details: body, attachment_url: '' };
const chunks = chunkDocument(article);
process.stdout.write(JSON.stringify({ count: chunks.length, chunkSize: CHUNK_SIZE }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["count"] == 1, (
        f"Body of exactly CHUNK_SIZE={result['chunkSize']} chars must produce exactly 1 chunk, "
        f"got {result['count']}"
    )


# ---------------------------------------------------------------------------
# AC9: Every chunk row has a non-null embedding vector
# ---------------------------------------------------------------------------

def test_ac9_embedder_returns_non_null_embeddings():
    """AC9: batchEmbed returns embedding arrays (not null) for every chunk."""
    script = """
import { chunkDocument } from './src/data/chunker.js';
import { batchEmbed } from './src/data/embedder.js';
const body = 'Test content for embedding. '.repeat(20);
const article = { id: 'embed-test', headline: 'H', details: body, attachment_url: '' };
const chunks = chunkDocument(article);
const embedded = await batchEmbed(chunks);
const nullCount = embedded.filter(c => !c.embedding || c.embedding.length === 0).length;
process.stdout.write(JSON.stringify({ total: embedded.length, nullCount }));
"""
    out, err, rc = _run_node(script, timeout=MODEL_TIMEOUT)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["total"] > 0, "batchEmbed must return at least one chunk"
    assert result["nullCount"] == 0, (
        f"Every chunk must have a non-null embedding; {result['nullCount']} of "
        f"{result['total']} had null/empty embeddings"
    )


# ---------------------------------------------------------------------------
# AC10: Changing env vars and re-ingesting reflects new chunking
# ---------------------------------------------------------------------------

def test_ac10_custom_chunk_size_env_var_produces_smaller_chunks():
    """AC10: CHUNK_SIZE=200 env var produces chunks ≤ 200 chars."""
    script = """
import { chunkDocument } from './src/data/chunker.js';
const body = 'Y'.repeat(1000);
const article = { id: 'envvar-test', headline: 'H', details: body, attachment_url: '' };
const chunks = chunkDocument(article);
const maxLen = Math.max(...chunks.map(c => c.details.length));
process.stdout.write(JSON.stringify({ count: chunks.length, maxLen }));
"""
    out, err, rc = _run_node(script, env={"CHUNK_SIZE": "200", "CHUNK_OVERLAP": "40"})
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result["maxLen"] <= 200, (
        f"With CHUNK_SIZE=200 all chunks must be ≤ 200 chars; max was {result['maxLen']}"
    )
    assert result["count"] >= 4, (
        f"1000 chars with CHUNK_SIZE=200 CHUNK_OVERLAP=40 should produce ≥ 4 chunks; "
        f"got {result['count']}"
    )


def test_ac10_custom_chunk_size_produces_more_chunks_than_default():
    """AC10: CHUNK_SIZE=200 produces more chunks than the default CHUNK_SIZE=400."""
    script_default = """
import { chunkDocument, CHUNK_SIZE } from './src/data/chunker.js';
const body = 'Z'.repeat(1000);
const article = { id: 'default-test', headline: 'H', details: body, attachment_url: '' };
const chunks = chunkDocument(article);
process.stdout.write(JSON.stringify({ count: chunks.length, chunkSize: CHUNK_SIZE }));
"""
    script_small = script_default  # same script, different env

    out1, err1, rc1 = _run_node(script_default, env={"CHUNK_SIZE": "", "CHUNK_OVERLAP": ""})
    out2, err2, rc2 = _run_node(script_small, env={"CHUNK_SIZE": "200", "CHUNK_OVERLAP": "40"})

    assert rc1 == 0, f"Node error (default): {err1}"
    assert rc2 == 0, f"Node error (small): {err2}"

    default_result = json.loads(out1)
    small_result = json.loads(out2)

    assert small_result["count"] > default_result["count"], (
        f"CHUNK_SIZE=200 must produce more chunks than CHUNK_SIZE={default_result['chunkSize']}; "
        f"default={default_result['count']}, small={small_result['count']}"
    )
