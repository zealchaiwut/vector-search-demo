"""
Tests for issue #33: Port article CRUD operations from file to Milvus

AC1 - listArticles queries Milvus using an id-prefix expression instead of reading collection.json
AC2 - getArticle retrieves a single article from Milvus by id-prefix expression
AC3 - deleteArticle removes an article from Milvus by id-prefix expression
AC4 - collection.json is no longer read by any of the three functions at runtime
AC5 - README.md Architecture section accurately describes Milvus-backed data path
AC8 - listArticles/getArticle/deleteArticle are async; both test suites extended
AC9 - E2E: ingest article → search → fetch by id → delete → search again confirms removal
"""

import json
import os
import re
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLLECTION_JS = os.path.join(REPO_ROOT, "src", "data", "collection.js")
README_PATH = os.path.join(REPO_ROOT, "README.md")
CLI_PATH = os.path.join(REPO_ROOT, "src", "cli.js")
SERVER_MJS = os.path.join(REPO_ROOT, "src", "server.mjs")

MILVUS_HOST = os.environ.get("MILVUS_HOST", "localhost")
MILVUS_PORT = os.environ.get("MILVUS_PORT", "19530")

needs_milvus = pytest.mark.skipif(
    not os.environ.get("MILVUS_HOST"),
    reason="MILVUS_HOST not set — skipping live Milvus tests",
)


def run_node(script, timeout=120, env_extra=None):
    env = os.environ.copy()
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
# AC1: listArticles queries Milvus using id-prefix expression
# ---------------------------------------------------------------------------


def test_ac1_collection_js_references_milvus_client():
    """collection.js must use MilvusClient for the Milvus-backed path."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert re.search(r"MilvusClient", src), (
        "collection.js must reference MilvusClient for the Milvus-backed path"
    )


def test_ac1_listArticles_uses_id_like_expression():
    """collection.js must contain an id 'like' expression for listArticles."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert re.search(r'id\s+like\s+["\']', src), (
        "collection.js must use 'id like \"...\"' expression for Milvus queries"
    )


def test_ac1_listArticles_uses_client_query():
    """collection.js must call client.query for Milvus path."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert re.search(r"client\.query", src), (
        "collection.js must call client.query in the Milvus path"
    )


@needs_milvus
def test_ac1_listArticles_returns_array():
    """listArticles must return an array when Milvus is active."""
    out, err, rc = run_node(
        """
import { listArticles } from './src/data/collection.js';
const articles = await listArticles();
if (!Array.isArray(articles)) throw new Error('listArticles must return an array, got: ' + typeof articles);
process.stdout.write(JSON.stringify({ ok: true, count: articles.length }));
""",
        env_extra={"MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
    )
    assert rc == 0, f"listArticles (Milvus) failed: {err}"
    data = json.loads(out)
    assert data["ok"] is True


# ---------------------------------------------------------------------------
# AC2: getArticle retrieves from Milvus by id-prefix expression
# ---------------------------------------------------------------------------


def test_ac2_getArticle_uses_articleId_prefix():
    """collection.js getArticle must use articleId in a 'like' expression."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    # Should have a dynamic filter expression with articleId variable
    assert re.search(r'articleId.*like|like.*articleId', src), (
        "collection.js getArticle must build a Milvus 'like' filter with articleId"
    )


@needs_milvus
def test_ac2_getArticle_returns_null_for_unknown_id():
    """getArticle on a non-existent id must return null, not throw."""
    out, err, rc = run_node(
        """
import { getArticle } from './src/data/collection.js';
const result = await getArticle('nonexistent-article-id-for-issue-33');
if (result !== null) throw new Error('Expected null for unknown id, got: ' + JSON.stringify(result));
process.stdout.write(JSON.stringify({ ok: true }));
""",
        env_extra={"MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
    )
    assert rc == 0, f"getArticle (unknown id) failed: {err}"
    assert json.loads(out)["ok"] is True


# ---------------------------------------------------------------------------
# AC3: deleteArticle removes from Milvus by id-prefix expression
# ---------------------------------------------------------------------------


def test_ac3_deleteArticle_uses_client_delete():
    """collection.js deleteArticle must call client.delete for the Milvus path."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert re.search(r"client\.delete", src), (
        "collection.js must call client.delete in deleteArticle's Milvus path"
    )


@needs_milvus
def test_ac3_deleteArticle_returns_false_for_unknown_id():
    """deleteArticle on a non-existent id must return false, not throw."""
    out, err, rc = run_node(
        """
import { deleteArticle } from './src/data/collection.js';
const result = await deleteArticle('nonexistent-article-id-for-issue-33');
if (result !== false) throw new Error('Expected false for unknown id, got: ' + JSON.stringify(result));
process.stdout.write(JSON.stringify({ ok: true }));
""",
        env_extra={"MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
    )
    assert rc == 0, f"deleteArticle (unknown id) failed: {err}"
    assert json.loads(out)["ok"] is True


# ---------------------------------------------------------------------------
# AC4: collection.json no longer read by the three functions at runtime
# ---------------------------------------------------------------------------


def test_ac4_listArticles_milvus_branch_uses_query_not_file():
    """The Milvus-active path in collection.js must use client.query, not readFileSync."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert re.search(r"MILVUS_HOST", src), (
        "collection.js must gate Milvus vs file path on MILVUS_HOST env var"
    )
    assert re.search(r"client\.query", src), (
        "collection.js must call client.query instead of reading file when Milvus active"
    )


@needs_milvus
def test_ac4_listArticles_ignores_collection_json():
    """listArticles must not return data from collection.json when MILVUS_HOST is set."""
    collection_path = os.path.join(REPO_ROOT, "collection.json")
    sentinel = [
        {
            "id": "sentinel-article-issue33:0",
            "headline": "SENTINEL_HEADLINE_ISSUE_33",
            "details": "sentinel details",
            "attachment_url": "",
            "embedding": [],
        }
    ]
    backup = None
    if os.path.exists(collection_path):
        with open(collection_path) as f:
            backup = f.read()
    try:
        with open(collection_path, "w") as f:
            json.dump(sentinel, f)
        out, err, rc = run_node(
            """
import { listArticles } from './src/data/collection.js';
const articles = await listArticles();
const hasSentinel = articles.some(a => a.headline === 'SENTINEL_HEADLINE_ISSUE_33');
process.stdout.write(JSON.stringify({ ok: true, hasSentinel }));
""",
            env_extra={"MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
        )
        assert rc == 0, f"listArticles failed: {err}"
        data = json.loads(out)
        assert not data["hasSentinel"], (
            "listArticles read from collection.json when MILVUS_HOST is set — it must query Milvus instead"
        )
    finally:
        if backup is not None:
            with open(collection_path, "w") as f:
                f.write(backup)
        elif os.path.exists(collection_path):
            os.remove(collection_path)


# ---------------------------------------------------------------------------
# AC5: README.md Architecture section updated
# ---------------------------------------------------------------------------


def test_ac5_readme_architecture_section_exists():
    """README.md must have an ## Architecture section."""
    with open(README_PATH) as f:
        readme = f.read()
    assert re.search(r"^## Architecture", readme, re.MULTILINE), (
        "README.md must have an '## Architecture' section"
    )


def test_ac5_readme_architecture_describes_milvus():
    """README.md Architecture section must describe Milvus as the data store."""
    with open(README_PATH) as f:
        readme = f.read()
    arch_match = re.search(r"## Architecture.*?(?=^##|\Z)", readme, re.DOTALL | re.MULTILINE)
    assert arch_match, "README.md must have an '## Architecture' section"
    arch_text = arch_match.group(0)
    assert re.search(r"Milvus", arch_text), (
        "README.md Architecture section must mention Milvus as the current data store"
    )


def test_ac5_readme_architecture_no_unwired_label():
    """README.md Architecture must not mark Milvus as 'Unwired' or unused."""
    with open(README_PATH) as f:
        readme = f.read()
    arch_match = re.search(r"## Architecture.*?(?=^##|\Z)", readme, re.DOTALL | re.MULTILINE)
    assert arch_match, "README.md must have an '## Architecture' section"
    arch_text = arch_match.group(0).lower()
    assert "unwired" not in arch_text, (
        "README.md Architecture must not label Milvus as 'Unwired' — Milvus is now the active backend"
    )
    assert "unused" not in arch_text or "milvus" not in arch_text.lower(), (
        "README.md Architecture must not describe Milvus keys as 'unused'"
    )


def test_ac5_readme_no_file_backed_as_main_path():
    """README.md Architecture must not describe collection.json as the primary data path."""
    with open(README_PATH) as f:
        readme = f.read()
    arch_match = re.search(r"## Architecture.*?(?=^##|\Z)", readme, re.DOTALL | re.MULTILINE)
    assert arch_match, "README.md must have an '## Architecture' section"
    arch_text = arch_match.group(0)
    # collection.json should not appear as the active store (may appear as legacy note)
    assert not re.search(r"collection\.json\s*\(file[- ]backed", arch_text, re.IGNORECASE), (
        "README.md Architecture must not describe collection.json as the file-backed active path"
    )


# ---------------------------------------------------------------------------
# AC8: The three functions are async; server awaits them
# ---------------------------------------------------------------------------


def test_ac8_listArticles_is_async():
    """listArticles must be declared async in collection.js."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert re.search(r"export\s+async\s+function\s+listArticles", src), (
        "listArticles must be exported as 'export async function listArticles'"
    )


def test_ac8_getArticle_is_async():
    """getArticle must be declared async in collection.js."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert re.search(r"export\s+async\s+function\s+getArticle", src), (
        "getArticle must be exported as 'export async function getArticle'"
    )


def test_ac8_deleteArticle_is_async():
    """deleteArticle must be declared async in collection.js."""
    with open(COLLECTION_JS) as f:
        src = f.read()
    assert re.search(r"export\s+async\s+function\s+deleteArticle", src), (
        "deleteArticle must be exported as 'export async function deleteArticle'"
    )


def test_ac8_server_awaits_listArticles():
    """server.mjs must await listArticles()."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert re.search(r"await\s+listArticles\(\)", src), (
        "server.mjs must await listArticles() — the function is now async"
    )


def test_ac8_server_awaits_getArticle():
    """server.mjs must await getArticle()."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert re.search(r"await\s+getArticle\(", src), (
        "server.mjs must await getArticle() — the function is now async"
    )


def test_ac8_server_awaits_deleteArticle():
    """server.mjs must await deleteArticle()."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert re.search(r"await\s+deleteArticle\(", src), (
        "server.mjs must await deleteArticle() — the function is now async"
    )


def test_ac8_server_awaits_upsertRows():
    """server.mjs must await upsertRows() since it is now async."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert re.search(r"await\s+upsertRows\(", src), (
        "server.mjs must await upsertRows() — the function is now async"
    )


def test_ac8_server_awaits_batchEmbed():
    """server.mjs must await batchEmbed() — it is async (MiniLM)."""
    with open(SERVER_MJS) as f:
        src = f.read()
    assert re.search(r"await\s+batchEmbed\(", src), (
        "server.mjs must await batchEmbed() — it is an async function using MiniLM"
    )


# ---------------------------------------------------------------------------
# AC9: End-to-end — ingest → fetch → delete (live Milvus)
# ---------------------------------------------------------------------------


@needs_milvus
def test_ac9_e2e_upsert_get_delete():
    """E2E: upsertRows → getArticle → deleteArticle → getArticle returns null."""
    out, err, rc = run_node(
        """
import { upsertRows } from './src/data/collection.js';
import { getArticle, deleteArticle, listArticles } from './src/data/collection.js';

const articleId = 'e2e-issue33-crud-' + Date.now();
const chunkId = articleId + ':0';
const embedding = new Array(384).fill(0);
embedding[0] = 1.0;

// Step 1: ingest
await upsertRows([{
  id: chunkId,
  headline: 'E2E Issue33 CRUD Test',
  details: 'Automated end-to-end test for issue 33 Milvus CRUD port.',
  attachment_url: '',
  embedding,
}]);

// Step 2: fetch by id
const fetched = await getArticle(articleId);
if (!fetched) throw new Error('getArticle returned null after upsert');
if (fetched.id !== articleId) throw new Error('Wrong article id: ' + fetched.id);
if (fetched.headline !== 'E2E Issue33 CRUD Test') throw new Error('Wrong headline: ' + fetched.headline);

// Step 3: confirm in list
const listBefore = await listArticles();
const inList = listBefore.some(a => a.id === articleId);
if (!inList) throw new Error('Article not found in listArticles after upsert');

// Step 4: delete
const deleted = await deleteArticle(articleId);
if (!deleted) throw new Error('deleteArticle returned false');

// Step 5: confirm gone
const afterDelete = await getArticle(articleId);
if (afterDelete !== null) throw new Error('getArticle still returns article after delete');

// Step 6: confirm not in list
const listAfter = await listArticles();
const stillInList = listAfter.some(a => a.id === articleId);
if (stillInList) throw new Error('Article still appears in listArticles after delete');

process.stdout.write(JSON.stringify({ ok: true, articleId }));
""",
        timeout=120,
        env_extra={"MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
    )
    assert rc == 0, f"E2E CRUD test failed:\nstderr={err}\nstdout={out}"
    data = json.loads(out)
    assert data["ok"] is True


@needs_milvus
def test_ac9_e2e_ingest_search_delete_search():
    """E2E: ingest → search confirms appears → delete → search confirms removed."""
    out, err, rc = run_node(
        """
import { upsertRows, deleteArticle } from './src/data/collection.js';
import { searchDocuments } from './src/core/search.js';
import { createEmbedder } from './src/embeddings/index.js';

// Use a unique phrase unlikely to match existing data
const uniquePhrase = 'xyzIssue33UniqueTestPhraseForMilvusCRUD portFromFileToVectorStore';
const articleId = 'e2e-issue33-search-' + Date.now();
const chunkId = articleId + ':0';

// Embed the article with the real model so search can find it
const embedder = await createEmbedder();
const [embedding] = await embedder.embed([uniquePhrase]);

// Step 1: ingest
await upsertRows([{
  id: chunkId,
  headline: 'Issue33 Unique Search Test Article',
  details: uniquePhrase,
  attachment_url: '',
  embedding,
}]);

// Step 2: search — article must appear
const resultsBefore = await searchDocuments(uniquePhrase, 10);
const foundBefore = resultsBefore.some(r => r.id === articleId);

// Step 3: delete
await deleteArticle(articleId);

// Step 4: search again — article must NOT appear
const resultsAfter = await searchDocuments(uniquePhrase, 10);
const foundAfter = resultsAfter.some(r => r.id === articleId);

process.stdout.write(JSON.stringify({
  ok: foundBefore && !foundAfter,
  foundBefore,
  foundAfter,
  resultsBefore: resultsBefore.map(r => r.id),
  resultsAfter: resultsAfter.map(r => r.id),
}));
""",
        timeout=180,
        env_extra={"MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
    )
    assert rc == 0, f"E2E search test failed:\nstderr={err}\nstdout={out}"
    data = json.loads(out)
    assert data["foundBefore"], (
        f"Article not found in search results after ingest. Results: {data.get('resultsBefore')}"
    )
    assert not data["foundAfter"], (
        f"Article still in search results after delete. Results: {data.get('resultsAfter')}"
    )
    assert data["ok"] is True
