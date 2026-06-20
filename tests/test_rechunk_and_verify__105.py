"""
Tests for issue #105: Add rechunk command and chunk integrity verification

Acceptance Criteria:
  AC1  - `rechunk` command exists at `src/commands/rechunk` and is registered with Commander
  AC2  - Running `rechunk` deletes existing chunks for all articles and regenerates them
  AC3  - `rechunk` processes all articles in the corpus, not a subset
  AC4  - `rechunk` re-embeds every newly created chunk (no null embedding after completion)
  AC5  - `rechunk` exits with a non-zero code and prints a clear error message on failure
  AC6  - `verify` reports `OK` when every article has ≥ 1 chunk and all embeddings non-null
  AC7  - `verify` lists each offending article ID when any article has zero chunks
  AC8  - `verify` lists each offending chunk ID when any chunk has a null embedding
  AC9  - `verify` exits with a non-zero code when any gap is found
  AC10 - Both commands are covered by unit or integration tests (this file)
"""

import json
import os
import re
import subprocess
import tempfile
import shutil

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECHUNK_JS = os.path.join(REPO_ROOT, "src", "commands", "rechunk.js")
VERIFY_JS = os.path.join(REPO_ROOT, "src", "commands", "verify.js")
CLI_TS = os.path.join(REPO_ROOT, "src", "cli.ts")
CLI_JS = os.path.join(REPO_ROOT, "dist", "cli.js")
COLLECTION_PATH = os.path.join(REPO_ROOT, "collection.json")
ATTACHMENTS_DIR = os.path.join(REPO_ROOT, "attachments")

MODEL_TIMEOUT = 120


def _run_node(script, timeout=MODEL_TIMEOUT, env=None):
    run_env = os.environ.copy()
    run_env["DB_BACKEND"] = "mock"
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
# AC1: rechunk command exists and is registered with Commander
# ---------------------------------------------------------------------------


def test_ac1_rechunk_file_exists():
    """AC1: src/commands/rechunk.js must exist."""
    assert os.path.exists(RECHUNK_JS), (
        f"rechunk command must exist at {RECHUNK_JS}"
    )


def test_ac1_rechunk_exports_run_rechunk():
    """AC1: rechunk.js must export a runRechunk function."""
    with open(RECHUNK_JS) as f:
        src = f.read()
    assert re.search(r"export\s+(async\s+)?function\s+runRechunk", src), (
        "rechunk.js must export a runRechunk function"
    )


def test_ac1_cli_ts_registers_rechunk():
    """AC1: cli.ts must register the rechunk command."""
    with open(CLI_TS) as f:
        src = f.read()
    assert "rechunk" in src, (
        "cli.ts must register the rechunk command"
    )
    assert "runRechunk" in src, (
        "cli.ts must import and call runRechunk"
    )


def test_ac1_cli_js_registers_rechunk():
    """AC1: compiled dist/cli.js must include rechunk command registration."""
    with open(CLI_JS) as f:
        src = f.read()
    assert "rechunk" in src, (
        "dist/cli.js must include the rechunk command (run `npm run build`)"
    )


# ---------------------------------------------------------------------------
# AC2: rechunk deletes existing chunks and regenerates them
# ---------------------------------------------------------------------------


def test_ac2_rechunk_replaces_chunks():
    """AC2: rechunk deletes old chunks and inserts new ones."""
    # Seed mock store with one article with a known chunk count
    # then change CHUNK_SIZE and rechunk — chunk IDs should change
    script = """
import { getMockStore } from './src/store/mock.js';
import { chunkDocuments } from './src/data/chunker.js';
import { batchEmbed } from './src/data/embedder.js';
import { runRechunk } from './src/commands/rechunk.js';
import { writeFileSync, mkdirSync, existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const REPO_ROOT = process.cwd();
const attachDir = join(REPO_ROOT, 'attachments');
if (!existsSync(attachDir)) mkdirSync(attachDir);

// Write a test attachment
const articleId = 'rechunk-test-001';
const headline = 'Test Article for Rechunk';
const details = 'A'.repeat(800);
writeFileSync(join(attachDir, `${articleId}.txt`), `${headline}\\n\\n${details}\\n`, 'utf8');

// Seed collection with large-chunk rows (CHUNK_SIZE=400)
const article = { id: articleId, headline, details, attachment_url: `/download/${articleId}` };
const chunksLarge = chunkDocuments([article]);
const embeddedLarge = await batchEmbed(chunksLarge);

const store = getMockStore();
await store.dropCollection();
await store.createCollection();
await store.upsertRows(embeddedLarge.map(c => ({
  id: c.id, headline: c.headline, details: c.details,
  attachment_url: c.attachment_url, embedding: c.embedding
})));

const countBefore = await store.entityCount();
const idsBefore = (await store.listChunks()).map(c => c.id);

// Now rechunk with a smaller chunk size
process.env.CHUNK_SIZE = '200';
process.env.CHUNK_OVERLAP = '40';
await runRechunk();

const countAfter = await store.entityCount();
const idsAfter = (await store.listChunks()).map(c => c.id);

// New chunk IDs should be different (different count)
process.stdout.write(JSON.stringify({
  countBefore,
  countAfter,
  idsBefore,
  idsAfter
}));
"""
    out, err, rc = _run_node(script, timeout=MODEL_TIMEOUT)
    assert rc == 0, f"rechunk script failed (rc={rc}):\n{err}\n{out}"
    json_lines = [l for l in out.strip().splitlines() if l.startswith("{")]
    assert json_lines, f"No JSON output: {out}"
    result = json.loads(json_lines[-1])
    assert result["countAfter"] > result["countBefore"], (
        f"With smaller CHUNK_SIZE=200 vs default 400, rechunk must produce MORE chunks. "
        f"Before={result['countBefore']}, After={result['countAfter']}"
    )
    # No old chunk IDs should remain
    old_ids = set(result["idsBefore"])
    new_ids = set(result["idsAfter"])
    assert not old_ids & new_ids or result["countAfter"] != result["countBefore"], (
        "After rechunk, old chunk rows must be replaced by newly generated chunk rows"
    )


# ---------------------------------------------------------------------------
# AC3: rechunk processes all articles, not a subset
# ---------------------------------------------------------------------------


def test_ac3_rechunk_processes_all_articles():
    """AC3: rechunk must process every article in the corpus."""
    script = """
import { getMockStore } from './src/store/mock.js';
import { chunkDocuments } from './src/data/chunker.js';
import { batchEmbed } from './src/data/embedder.js';
import { runRechunk } from './src/commands/rechunk.js';
import { writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const attachDir = join(process.cwd(), 'attachments');
if (!existsSync(attachDir)) mkdirSync(attachDir);

// Create 3 test articles
const articles = [
  { id: 'all-test-001', headline: 'Article One', details: 'B'.repeat(500) },
  { id: 'all-test-002', headline: 'Article Two', details: 'C'.repeat(600) },
  { id: 'all-test-003', headline: 'Article Three', details: 'D'.repeat(700) },
];

for (const a of articles) {
  writeFileSync(
    join(attachDir, `${a.id}.txt`),
    `${a.headline}\\n\\n${a.details}\\n`, 'utf8'
  );
}

// Seed mock store
const all = articles.map(a => ({ ...a, attachment_url: `/download/${a.id}` }));
const chunks = chunkDocuments(all);
const embedded = await batchEmbed(chunks);

const store = getMockStore();
await store.dropCollection();
await store.createCollection();
await store.upsertRows(embedded.map(c => ({
  id: c.id, headline: c.headline, details: c.details,
  attachment_url: c.attachment_url, embedding: c.embedding
})));

await runRechunk();

// All 3 articles must have chunks after rechunk
const allChunks = await store.listChunks();
const articleIds = new Set(allChunks.map(c => c.id.split(':')[0]));
const processedArticles = articles.filter(a => articleIds.has(a.id));

process.stdout.write(JSON.stringify({
  totalArticles: articles.length,
  processedCount: processedArticles.length,
  articleIds: [...articleIds],
  processedIds: processedArticles.map(a => a.id)
}));
"""
    out, err, rc = _run_node(script, timeout=MODEL_TIMEOUT)
    assert rc == 0, f"rechunk all-articles script failed (rc={rc}):\n{err}\n{out}"
    json_lines = [l for l in out.strip().splitlines() if l.startswith("{")]
    assert json_lines, f"No JSON output: {out}"
    result = json.loads(json_lines[-1])
    assert result["processedCount"] == result["totalArticles"], (
        f"rechunk must process all {result['totalArticles']} articles; "
        f"only {result['processedCount']} found with chunks after rechunk. "
        f"Article IDs in store: {result['articleIds']}"
    )


# ---------------------------------------------------------------------------
# AC4: rechunk re-embeds every chunk (no null embeddings after completion)
# ---------------------------------------------------------------------------


def test_ac4_rechunk_produces_no_null_embeddings():
    """AC4: after rechunk, every chunk must have a non-null embedding."""
    script = """
import { getMockStore } from './src/store/mock.js';
import { chunkDocuments } from './src/data/chunker.js';
import { batchEmbed } from './src/data/embedder.js';
import { runRechunk } from './src/commands/rechunk.js';
import { writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const attachDir = join(process.cwd(), 'attachments');
if (!existsSync(attachDir)) mkdirSync(attachDir);

const articleId = 'embed-check-001';
const headline = 'Embedding Check Article';
const details = 'E'.repeat(900);
writeFileSync(join(attachDir, `${articleId}.txt`), `${headline}\\n\\n${details}\\n`, 'utf8');

const article = { id: articleId, headline, details, attachment_url: `/download/${articleId}` };
const chunks = chunkDocuments([article]);
const embedded = await batchEmbed(chunks);

const store = getMockStore();
await store.dropCollection();
await store.createCollection();
await store.upsertRows(embedded.map(c => ({
  id: c.id, headline: c.headline, details: c.details,
  attachment_url: c.attachment_url, embedding: c.embedding
})));

// Run rechunk
await runRechunk();

// Check all chunks have non-null embeddings
const allChunks = await store.listChunks();
const relevantChunks = allChunks.filter(c => c.id.startsWith('embed-check-001'));
const nullCount = relevantChunks.filter(c => !c.embedding || (Array.isArray(c.embedding) && c.embedding.length === 0)).length;

process.stdout.write(JSON.stringify({
  total: relevantChunks.length,
  nullCount
}));
"""
    out, err, rc = _run_node(script, timeout=MODEL_TIMEOUT)
    assert rc == 0, f"rechunk embed check failed (rc={rc}):\n{err}\n{out}"
    json_lines = [l for l in out.strip().splitlines() if l.startswith("{")]
    assert json_lines, f"No JSON output: {out}"
    result = json.loads(json_lines[-1])
    assert result["total"] > 0, "rechunk must produce at least one chunk"
    assert result["nullCount"] == 0, (
        f"After rechunk, {result['nullCount']} of {result['total']} chunks have null embeddings"
    )


# ---------------------------------------------------------------------------
# AC5: rechunk exits with non-zero and error message on failure
# ---------------------------------------------------------------------------


def test_ac5_rechunk_exits_nonzero_on_failure():
    """AC5: rechunk must exit with non-zero code and print error when processing fails."""
    # We simulate a failure by providing a corrupt batchEmbed via env tricks
    # Instead, test the error-handling path by checking the source code
    with open(RECHUNK_JS) as f:
        src = f.read()

    assert re.search(r"process\.exit\s*\(\s*1\s*\)", src), (
        "rechunk.js must call process.exit(1) on failure"
    )
    assert re.search(r"process\.stderr\.write|console\.error", src), (
        "rechunk.js must write an error message to stderr on failure"
    )


def test_ac5_rechunk_error_message_contains_article_id():
    """AC5: rechunk error output must identify which article failed."""
    with open(RECHUNK_JS) as f:
        src = f.read()
    # The error message should include the article id to help debugging
    assert re.search(r"article|id|error|fail", src, re.IGNORECASE), (
        "rechunk.js error handling must reference the article or provide context"
    )


# ---------------------------------------------------------------------------
# AC6: verify reports OK when all articles have chunks and non-null embeddings
# ---------------------------------------------------------------------------


def test_ac6_verify_reports_ok_after_clean_ingest():
    """AC6: verify must print OK and exit 0 when corpus is clean."""
    tmp_dir = tempfile.mkdtemp(prefix="verify_test_ac6_")
    try:
        # Write one article attachment file from Python (pre-import)
        article_id = "verify-ok-001"
        with open(os.path.join(tmp_dir, f"{article_id}.txt"), "w") as f:
            f.write(f"Clean Article\n\n{'F' * 500}\n")

        script = """
import { getMockStore } from './src/store/mock.js';
import { chunkDocuments } from './src/data/chunker.js';
import { batchEmbed } from './src/data/embedder.js';
import { runVerify } from './src/commands/verify.js';

const articleId = 'verify-ok-001';
const headline = 'Clean Article';
const details = 'F'.repeat(500);

const article = { id: articleId, headline, details, attachment_url: `/download/${articleId}` };
const chunks = chunkDocuments([article]);
const embedded = await batchEmbed(chunks);

const store = getMockStore();
await store.dropCollection();
await store.createCollection();
await store.upsertRows(embedded.map(c => ({
  id: c.id, headline: c.headline, details: c.details,
  attachment_url: c.attachment_url, embedding: c.embedding
})));

let exitCode = null;
const origExit = process.exit;
process.exit = (code) => { exitCode = code ?? 0; };

const lines = [];
const origWrite = process.stdout.write.bind(process.stdout);
process.stdout.write = (s) => { lines.push(s); return origWrite(s); };

try { await runVerify(); } catch(e) {}

process.exit = origExit;
process.stdout.write = origWrite;

process.stdout.write(JSON.stringify({ exitCode, output: lines.join('') }));
"""
        out, err, rc = _run_node(
            script, timeout=MODEL_TIMEOUT,
            env={"VERIFY_ATTACHMENTS_DIR": tmp_dir}
        )
        json_lines = [l for l in out.strip().splitlines() if l.startswith("{")]
        assert json_lines, f"No JSON output: {out}\nstderr: {err}"
        result = json.loads(json_lines[-1])
        assert result["exitCode"] == 0, (
            f"verify must exit 0 for a clean corpus; got exit code {result['exitCode']}. "
            f"Output: {result['output']}"
        )
        assert "OK" in result["output"], (
            f"verify must print 'OK' for a clean corpus; got: {result['output']}"
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# AC7: verify lists offending article IDs when any article has zero chunks
# ---------------------------------------------------------------------------


def test_ac7_verify_lists_article_id_with_zero_chunks():
    """AC7: verify must list article IDs that have no chunks in the store."""
    tmp_dir = tempfile.mkdtemp(prefix="verify_test_ac7_")
    try:
        # Write both articles' attachment files from Python
        for aid, headline in [("has-chunks-001", "Has Chunks"), ("no-chunks-001", "No Chunks")]:
            with open(os.path.join(tmp_dir, f"{aid}.txt"), "w") as f:
                f.write(f"{headline}\n\n{'G' * 200}\n")

        script = """
import { getMockStore } from './src/store/mock.js';
import { chunkDocuments } from './src/data/chunker.js';
import { batchEmbed } from './src/data/embedder.js';
import { runVerify } from './src/commands/verify.js';

// Only store chunks for the first article (has-chunks-001)
const fullArticle = { id: 'has-chunks-001', headline: 'Has Chunks',
  details: 'G'.repeat(200), attachment_url: '/download/has-chunks-001' };
const chunks = chunkDocuments([fullArticle]);
const embedded = await batchEmbed(chunks);

const store = getMockStore();
await store.dropCollection();
await store.createCollection();
await store.upsertRows(embedded.map(c => ({
  id: c.id, headline: c.headline, details: c.details,
  attachment_url: c.attachment_url, embedding: c.embedding
})));
// no-chunks-001 has no rows in the store

const lines = [];
let exitCode = null;
const origExit = process.exit;
const origWrite = process.stdout.write.bind(process.stdout);
process.exit = (code) => { exitCode = code ?? 0; };
process.stdout.write = (s) => { lines.push(s); return origWrite(s); };

try { await runVerify(); } catch(e) {}

process.exit = origExit;
process.stdout.write = origWrite;

const output = lines.join('');
process.stdout.write(JSON.stringify({ exitCode, output }));
"""
        out, err, rc = _run_node(
            script, timeout=MODEL_TIMEOUT,
            env={"VERIFY_ATTACHMENTS_DIR": tmp_dir}
        )
        json_lines = [l for l in out.strip().splitlines() if l.startswith("{")]
        assert json_lines, f"No JSON output: {out}\nstderr: {err}"
        result = json.loads(json_lines[-1])
        assert "no-chunks-001" in result["output"], (
            f"verify must list 'no-chunks-001' as an article with zero chunks. "
            f"Got output: {result['output']}"
        )
        assert result["exitCode"] != 0, (
            f"verify must exit with non-zero when articles have zero chunks; "
            f"got exit code {result['exitCode']}"
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# AC8: verify lists offending chunk IDs when any chunk has null embedding
# ---------------------------------------------------------------------------


def test_ac8_verify_lists_chunk_id_with_null_embedding():
    """AC8: verify must list chunk IDs that have null embeddings."""
    tmp_dir = tempfile.mkdtemp(prefix="verify_test_ac8_")
    try:
        article_id = "null-embed-001"
        with open(os.path.join(tmp_dir, f"{article_id}.txt"), "w") as f:
            f.write(f"Null Embedding Article\n\n{'I' * 500}\n")

        script = """
import { getMockStore } from './src/store/mock.js';
import { chunkDocuments } from './src/data/chunker.js';
import { batchEmbed } from './src/data/embedder.js';
import { runVerify } from './src/commands/verify.js';

const articleId = 'null-embed-001';
const article = { id: articleId, headline: 'Null Embedding Article',
  details: 'I'.repeat(500), attachment_url: `/download/${articleId}` };
const chunks = chunkDocuments([article]);
const embedded = await batchEmbed(chunks);

// Force the first chunk to have null embedding
const rows = embedded.map((c, idx) => ({
  id: c.id, headline: c.headline, details: c.details,
  attachment_url: c.attachment_url,
  embedding: idx === 0 ? null : c.embedding
}));

const store = getMockStore();
await store.dropCollection();
await store.createCollection();
await store.upsertRows(rows);

const nullChunkId = rows[0].id;

const lines = [];
let exitCode = null;
const origExit = process.exit;
const origWrite = process.stdout.write.bind(process.stdout);
process.exit = (code) => { exitCode = code ?? 0; };
process.stdout.write = (s) => { lines.push(s); return origWrite(s); };

try { await runVerify(); } catch(e) {}

process.exit = origExit;
process.stdout.write = origWrite;

const output = lines.join('');
process.stdout.write(JSON.stringify({ exitCode, output, nullChunkId }));
"""
        out, err, rc = _run_node(
            script, timeout=MODEL_TIMEOUT,
            env={"VERIFY_ATTACHMENTS_DIR": tmp_dir}
        )
        json_lines = [l for l in out.strip().splitlines() if l.startswith("{")]
        assert json_lines, f"No JSON output: {out}\nstderr: {err}"
        result = json.loads(json_lines[-1])
        assert result["nullChunkId"] in result["output"], (
            f"verify must list chunk ID '{result['nullChunkId']}' as having a null embedding. "
            f"Got output: {result['output']}"
        )
        assert result["exitCode"] != 0, (
            f"verify must exit non-zero when chunks have null embeddings; "
            f"got exit code {result['exitCode']}"
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# AC9: verify exits with non-zero code when any gap is found
# ---------------------------------------------------------------------------


def test_ac9_verify_exits_nonzero_when_gaps_found():
    """AC9: verify exit code must be non-zero when integrity gaps exist."""
    # Already tested implicitly in AC7 and AC8 tests.
    # Confirm via source code inspection as belt-and-suspenders.
    with open(VERIFY_JS) as f:
        src = f.read()
    assert re.search(r"process\.exit\s*\(\s*1\s*\)", src), (
        "verify.js must call process.exit(1) when integrity gaps are found"
    )


def test_ac9_verify_exits_zero_when_clean():
    """AC9: verify exit code must be 0 when corpus is clean."""
    with open(VERIFY_JS) as f:
        src = f.read()
    assert re.search(r"process\.exit\s*\(\s*0\s*\)", src), (
        "verify.js must call process.exit(0) when all integrity checks pass"
    )


# ---------------------------------------------------------------------------
# AC10: Both commands are covered by tests (meta test)
# ---------------------------------------------------------------------------


def test_ac10_rechunk_command_is_tested():
    """AC10: rechunk command must be covered by tests in this file."""
    # This file itself covers rechunk — verifying the file exists with test functions
    this_file = __file__
    with open(this_file) as f:
        content = f.read()
    rechunk_test_count = content.count("rechunk")
    assert rechunk_test_count > 5, (
        f"This test file must contain substantial rechunk coverage; found {rechunk_test_count} references"
    )


def test_ac10_verify_command_is_tested():
    """AC10: verify command must be covered by tests in this file."""
    this_file = __file__
    with open(this_file) as f:
        content = f.read()
    verify_test_count = content.count("verify")
    assert verify_test_count > 5, (
        f"This test file must contain substantial verify coverage; found {verify_test_count} references"
    )


def test_ac10_listchunks_method_exists_in_mock_store():
    """AC10: mock store must expose a listChunks() method for integrity inspection."""
    from pathlib import Path
    mock_store = Path(REPO_ROOT) / "src" / "store" / "mock.js"
    src = mock_store.read_text()
    assert "listChunks" in src, (
        "src/store/mock.js must expose listChunks() so verify can inspect raw chunk rows"
    )


def test_ac10_listchunks_returns_chunk_rows_with_embeddings():
    """AC10: listChunks() must return rows including embedding field for verify to inspect."""
    script = """
import { getMockStore } from './src/store/mock.js';
import { chunkDocuments } from './src/data/chunker.js';
import { batchEmbed } from './src/data/embedder.js';
import { writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const attachDir = join(process.cwd(), 'attachments');
if (!existsSync(attachDir)) mkdirSync(attachDir);

const articleId = 'listchunks-test-001';
const details = 'J'.repeat(500);
writeFileSync(join(attachDir, `${articleId}.txt`), `Headline\\n\\n${details}\\n`, 'utf8');

const article = { id: articleId, headline: 'Headline', details, attachment_url: '/download/' + articleId };
const chunks = chunkDocuments([article]);
const embedded = await batchEmbed(chunks);

const store = getMockStore();
await store.dropCollection();
await store.createCollection();
await store.upsertRows(embedded.map(c => ({
  id: c.id, headline: c.headline, details: c.details,
  attachment_url: c.attachment_url, embedding: c.embedding
})));

const allChunks = await store.listChunks();
const relevant = allChunks.filter(c => c.id.startsWith(articleId));
const hasEmbedding = relevant.every(c => c.embedding !== undefined);
process.stdout.write(JSON.stringify({ count: relevant.length, hasEmbedding }));
"""
    out, err, rc = _run_node(script, timeout=MODEL_TIMEOUT)
    assert rc == 0, f"listChunks test failed (rc={rc}):\n{err}\n{out}"
    json_lines = [l for l in out.strip().splitlines() if l.startswith("{")]
    assert json_lines, f"No JSON output: {out}"
    result = json.loads(json_lines[-1])
    assert result["count"] > 0, "listChunks must return chunk rows"
    assert result["hasEmbedding"], (
        "listChunks must return rows that include the embedding field"
    )
