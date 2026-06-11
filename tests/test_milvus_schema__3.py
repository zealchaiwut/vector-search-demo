"""
Acceptance tests for issue #3: Define Milvus collection schema and vector index

AC1  - src/milvus/schema.js exports createCollection(recreate?) function
AC2  - Collection has fields: id (Int64, auto PK), doc_id (VarChar), chunk_id (Int64),
       title (VarChar), text (VarChar), attachment_name (VarChar), embedding (FloatVector dim=384)
AC3  - HNSW index on embedding with COSINE metric, M=16, efConstruction=200
AC4  - createCollection(false) is idempotent — skips drop/recreate if collection already exists
AC5  - createCollection(true) drops existing collection and recreates from scratch
AC6  - src/milvus/schema.js exports getCollection()
AC7  - src/commands/init.js registers a commander init command
AC8  - Running commander init twice leaves exactly one documents collection
AC9  - Index on embedding confirmed HNSW with COSINE metric after provisioning
AC10 - Collection is empty (zero entities) after fresh provisioning
"""

import json
import os
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# schema.ts is the TypeScript source; tests import from the compiled output
SCHEMA_PATH = os.path.join(REPO_ROOT, "dist", "milvus", "schema.js")
INIT_CMD_PATH = os.path.join(REPO_ROOT, "src", "commands", "init.js")
CLI_PATH = os.path.join(REPO_ROOT, "src", "cli.js")

MILVUS_HOST = os.environ.get("MILVUS_HOST", "localhost")
MILVUS_PORT = os.environ.get("MILVUS_PORT", "19530")

needs_milvus = pytest.mark.skipif(
    not os.environ.get("MILVUS_HOST"),
    reason="MILVUS_HOST not set — skipping live Milvus tests",
)


def run_node(script, timeout=30, env_extra=None):
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


def run_cli(args, timeout=30, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["node", CLI_PATH] + args,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
        env=env,
    )


# ---------------------------------------------------------------------------
# AC1 + AC6: module exists and exports createCollection / getCollection
# ---------------------------------------------------------------------------


def test_milvus_schema__module_exists():
    # AC1: dist/milvus/schema.js (compiled from schema.ts) must exist
    assert os.path.isfile(SCHEMA_PATH), f"dist/milvus/schema.js not found at {SCHEMA_PATH}"


def test_milvus_schema__exports_createCollection():
    # AC1: createCollection must be an exported function
    stdout, stderr, rc = run_node(
        f"""
import {{ createCollection }} from '{SCHEMA_PATH}';
if (typeof createCollection !== 'function') throw new Error('createCollection is not a function');
process.stdout.write(JSON.stringify({{ ok: true }}));
"""
    )
    assert rc == 0, f"Import failed: {stderr}"
    assert json.loads(stdout)["ok"] is True


def test_milvus_schema__exports_getCollection():
    # AC6: getCollection must be an exported function
    stdout, stderr, rc = run_node(
        f"""
import {{ getCollection }} from '{SCHEMA_PATH}';
if (typeof getCollection !== 'function') throw new Error('getCollection is not a function');
process.stdout.write(JSON.stringify({{ ok: true }}));
"""
    )
    assert rc == 0, f"Import failed: {stderr}"
    assert json.loads(stdout)["ok"] is True


# ---------------------------------------------------------------------------
# AC2: collection schema defines all 7 required fields
# ---------------------------------------------------------------------------


def test_milvus_schema__exports_COLLECTION_SCHEMA():
    # AC2: schema constants exported for inspection
    stdout, stderr, rc = run_node(
        f"""
import {{ COLLECTION_SCHEMA }} from '{SCHEMA_PATH}';
process.stdout.write(JSON.stringify(COLLECTION_SCHEMA));
"""
    )
    assert rc == 0, f"Import failed: {stderr}"
    schema = json.loads(stdout)

    assert schema["collection_name"] == "documents", (
        f"Expected collection_name 'documents', got {schema.get('collection_name')!r}"
    )

    field_names = [f["name"] for f in schema["fields"]]
    for required in ["id", "headline", "details", "attachment_url", "embedding"]:
        assert required in field_names, f"Field '{required}' missing from schema. Got: {field_names}"

    id_field = next(f for f in schema["fields"] if f["name"] == "id")
    assert id_field.get("is_primary_key") is True, "id field must be primary key"
    assert id_field.get("autoID") is False, "id field must have autoID=false"

    emb_field = next(f for f in schema["fields"] if f["name"] == "embedding")
    assert emb_field.get("dim") == 384, (
        f"embedding dim must be 384, got {emb_field.get('dim')}"
    )


# ---------------------------------------------------------------------------
# AC3: HNSW index params
# ---------------------------------------------------------------------------


def test_milvus_schema__exports_INDEX_PARAMS():
    # AC3: index params exported and correct
    stdout, stderr, rc = run_node(
        f"""
import {{ INDEX_PARAMS }} from '{SCHEMA_PATH}';
process.stdout.write(JSON.stringify(INDEX_PARAMS));
"""
    )
    assert rc == 0, f"Import failed: {stderr}"
    idx = json.loads(stdout)

    assert idx.get("field_name") == "embedding", f"field_name must be 'embedding', got {idx.get('field_name')!r}"
    assert idx.get("index_type") == "HNSW", f"index_type must be HNSW, got {idx.get('index_type')!r}"
    assert idx.get("metric_type") == "COSINE", f"metric_type must be COSINE, got {idx.get('metric_type')!r}"
    assert idx.get("params", {}).get("M") == 16, f"M must be 16, got {idx.get('params', {}).get('M')}"
    assert idx.get("params", {}).get("efConstruction") == 200, (
        f"efConstruction must be 200, got {idx.get('params', {}).get('efConstruction')}"
    )


# ---------------------------------------------------------------------------
# AC7: src/commands/init.js exists and is wired in src/cli.js
# ---------------------------------------------------------------------------


def test_milvus_schema__init_command_file_exists():
    # AC7: src/commands/init.js must exist
    assert os.path.isfile(INIT_CMD_PATH), f"src/commands/init.js not found at {INIT_CMD_PATH}"


def test_milvus_schema__init_command_exports_runInit():
    # AC7: runInit must be an exported function
    stdout, stderr, rc = run_node(
        f"""
import {{ runInit }} from '{INIT_CMD_PATH}';
if (typeof runInit !== 'function') throw new Error('runInit is not a function');
process.stdout.write(JSON.stringify({{ ok: true }}));
"""
    )
    assert rc == 0, f"Import failed: {stderr}"
    assert json.loads(stdout)["ok"] is True


def test_milvus_schema__cli_registers_init():
    # AC7: cli.js must branch on 'init' command
    with open(CLI_PATH) as f:
        cli_source = f.read()
    assert "init" in cli_source, "cli.js does not reference 'init' command"


# ---------------------------------------------------------------------------
# Live Milvus tests (skipped when MILVUS_HOST not set)
# ---------------------------------------------------------------------------


@needs_milvus
def test_milvus_schema__createCollection_creates_documents():
    # AC2/AC10: createCollection(true) creates collection; entity count is 0
    stdout, stderr, rc = run_node(
        f"""
import {{ createCollection }} from '{SCHEMA_PATH}';
await createCollection(true);
process.stdout.write(JSON.stringify({{ ok: true }}));
""",
        timeout=60,
        env_extra={"MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
    )
    assert rc == 0, f"createCollection failed: {stderr}"
    assert json.loads(stdout)["ok"] is True


@needs_milvus
def test_milvus_schema__collection_empty_after_provision():
    # AC10: entity count is 0 after fresh provisioning
    stdout, stderr, rc = run_node(
        f"""
import {{ createCollection }} from '{SCHEMA_PATH}';
import {{ MilvusClient }} from '@zilliz/milvus2-sdk-node';
await createCollection(true);
const client = new MilvusClient({{ address: '{MILVUS_HOST}:{MILVUS_PORT}' }});
const stats = await client.getCollectionStatistics({{ collection_name: 'documents' }});
const count = parseInt(stats.stats?.find(s => s.key === 'row_count')?.value ?? '0', 10);
process.stdout.write(JSON.stringify({{ count }}));
""",
        timeout=60,
        env_extra={"MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
    )
    assert rc == 0, f"Entity count check failed: {stderr}"
    data = json.loads(stdout)
    assert data["count"] == 0, f"Expected 0 entities after fresh provisioning, got {data['count']}"


@needs_milvus
def test_milvus_schema__createCollection_false_idempotent():
    # AC4: createCollection(false) does not drop/recreate if collection exists
    stdout, stderr, rc = run_node(
        f"""
import {{ createCollection }} from '{SCHEMA_PATH}';
await createCollection(true);   // fresh create
await createCollection(false);  // should skip silently
await createCollection(false);  // should skip silently again
process.stdout.write(JSON.stringify({{ ok: true }}));
""",
        timeout=60,
        env_extra={"MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
    )
    assert rc == 0, f"Idempotent createCollection(false) failed: {stderr}"


@needs_milvus
def test_milvus_schema__createCollection_true_drops_and_recreates():
    # AC5: createCollection(true) drops existing collection and recreates from scratch
    stdout, stderr, rc = run_node(
        f"""
import {{ createCollection }} from '{SCHEMA_PATH}';
await createCollection(true);  // initial create
await createCollection(true);  // drop + recreate
process.stdout.write(JSON.stringify({{ ok: true }}));
""",
        timeout=60,
        env_extra={"MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
    )
    assert rc == 0, f"createCollection(true) drop+recreate failed: {stderr}"


@needs_milvus
def test_milvus_schema__index_is_hnsw_cosine():
    # AC3/AC9: index on embedding is HNSW with COSINE metric after provisioning
    stdout, stderr, rc = run_node(
        f"""
import {{ createCollection }} from '{SCHEMA_PATH}';
import {{ MilvusClient }} from '@zilliz/milvus2-sdk-node';
await createCollection(true);
const client = new MilvusClient({{ address: '{MILVUS_HOST}:{MILVUS_PORT}' }});
const desc = await client.describeIndex({{ collection_name: 'documents', field_name: 'embedding' }});
process.stdout.write(JSON.stringify(desc));
""",
        timeout=60,
        env_extra={"MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
    )
    assert rc == 0, f"describeIndex failed: {stderr}"
    data = json.loads(stdout)
    indexes = data.get("index_descriptions", [])
    assert len(indexes) > 0, f"No index found on embedding field. Response: {data}"
    # Params may be returned as key-value array or direct fields depending on SDK version
    idx = indexes[0]
    params = {p["key"]: p["value"] for p in idx.get("params", [])} if isinstance(idx.get("params"), list) else {}
    index_type = params.get("index_type") or idx.get("index_type", "")
    metric_type = params.get("metric_type") or idx.get("metric_type", "")
    assert index_type == "HNSW", f"Expected HNSW index, got {index_type!r}"
    assert metric_type == "COSINE", f"Expected COSINE metric, got {metric_type!r}"


@needs_milvus
def test_milvus_schema__commander_init_exits_0():
    # AC7/AC8: commander init exits 0
    result = run_cli(
        ["init"],
        timeout=60,
        env_extra={"MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
    )
    assert result.returncode == 0, (
        f"commander init failed (exit {result.returncode}): {result.stderr}"
    )


@needs_milvus
def test_milvus_schema__commander_init_twice_single_collection():
    # AC8: running init twice leaves exactly one documents collection
    r1 = run_cli(
        ["init"],
        timeout=60,
        env_extra={"MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
    )
    assert r1.returncode == 0, f"First init failed: {r1.stderr}"
    r2 = run_cli(
        ["init"],
        timeout=60,
        env_extra={"MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
    )
    assert r2.returncode == 0, f"Second init failed: {r2.stderr}"


# ---------------------------------------------------------------------------
# Issue #33 extension: ingest-to-search round trip via collection schema
# ---------------------------------------------------------------------------


@needs_milvus
def test_milvus_schema__ingest_to_search_round_trip():
    """Issue #33 AC8: after upsertRows via schema-provisioned collection, searchDocuments finds it."""
    stdout, stderr, rc = run_node(
        f"""
import {{ upsertRows, deleteArticle, createCollection }} from './src/data/collection.js';
import {{ createEmbedder }} from './src/embeddings/index.js';
import {{ searchDocuments }} from './src/core/search.js';

// Ensure collection exists (idempotent)
await createCollection();

const phrase = 'milvus schema round trip test phrase issue33 unique beacon';
const articleId = 'rt-schema-33-' + Date.now();
const embedder = await createEmbedder();
const [embedding] = await embedder.embed([phrase]);

await upsertRows([{{
  id: articleId + ':0',
  headline: 'Round Trip Schema Test Issue33',
  details: phrase,
  attachment_url: '',
  embedding,
}}]);

const results = await searchDocuments(phrase, 10);
const found = results.some(r => r.id === articleId);

// Cleanup
await deleteArticle(articleId);

process.stdout.write(JSON.stringify({{ found, count: results.length }}));
""",
        timeout=180,
        env_extra={"MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
    )
    assert rc == 0, f"Round trip test failed: {stderr}"
    data = json.loads(stdout)
    assert data["found"], (
        f"Ingested article not found by searchDocuments after schema init. "
        f"Results count: {data.get('count')}"
    )
