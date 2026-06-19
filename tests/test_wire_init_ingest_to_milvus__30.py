"""Tests for issue #30: Wire init and ingest commands to real Milvus collection"""

import json
import os
import re
import subprocess

import pytest

CODER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CLI_PATH = os.path.join(CODER_DIR, "src", "cli.js")
INIT_CMD_PATH = os.path.join(CODER_DIR, "src", "commands", "init.js")
INGEST_CMD_PATH = os.path.join(CODER_DIR, "src", "commands", "ingest.js")
COLLECTION_JS_PATH = os.path.join(CODER_DIR, "src", "data", "collection.js")
COLLECTION_JSON_PATH = os.path.join(CODER_DIR, "collection.json")
ATTACHMENTS_DIR = os.path.join(CODER_DIR, "attachments")

MILVUS_HOST = os.environ.get("MILVUS_HOST", "localhost")
MILVUS_PORT = os.environ.get("MILVUS_PORT", "19530")

needs_milvus = pytest.mark.skipif(
    not os.environ.get("MILVUS_HOST"),
    reason="MILVUS_HOST not set — skipping live Milvus tests",
)


def run_cli(args, timeout=60):
    env = os.environ.copy()
    return subprocess.run(
        ["node", CLI_PATH] + args,
        capture_output=True,
        text=True,
        cwd=CODER_DIR,
        timeout=timeout,
        env=env,
    )


def run_node(script, timeout=60):
    env = os.environ.copy()
    return subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=CODER_DIR,
        timeout=timeout,
        env=env,
    )


def parse_ingest_summary(stdout):
    m = re.search(r"(\d+)\s+docs\s*/\s*(\d+)\s+chunks\s+indexed", stdout)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


# ---------------------------------------------------------------------------
# AC1: collection.json is never written — static analysis
# ---------------------------------------------------------------------------

def test_ac1_collection_js_has_no_collection_json_reference():
    """AC1: src/data/collection.js must not reference 'collection.json'."""
    with open(COLLECTION_JS_PATH) as f:
        src = f.read()
    assert "collection.json" not in src, (
        "src/data/collection.js still references 'collection.json' — must be removed"
    )


def test_ac1_collection_js_has_no_fs_write():
    """AC1: src/data/collection.js must not write to the filesystem."""
    with open(COLLECTION_JS_PATH) as f:
        src = f.read()
    # writeFileSync should not appear (the old mechanism that created collection.json)
    assert "writeFileSync" not in src, (
        "src/data/collection.js still uses writeFileSync — must be removed"
    )


def test_ac1_collection_json_absent_after_init():
    """AC1: running 'init' must not create collection.json on disk.
    Tested via static analysis — init.js must not import from the old file-backed store.
    """
    with open(INIT_CMD_PATH) as f:
        src = f.read()
    # init.js must not directly reference collection.json
    assert "collection.json" not in src, (
        "init.js references 'collection.json' directly"
    )


# ---------------------------------------------------------------------------
# AC2: runInit calls createCollection (Milvus-backed) — static analysis
# ---------------------------------------------------------------------------

def test_ac2_init_js_calls_createcollection():
    """AC2: init.js must call createCollection."""
    with open(INIT_CMD_PATH) as f:
        src = f.read()
    assert "createCollection" in src, (
        "init.js does not call createCollection"
    )


def test_ac2_init_js_awaits_createcollection():
    """AC2: init.js must await createCollection (async call)."""
    with open(INIT_CMD_PATH) as f:
        src = f.read()
    assert re.search(r"await\s+createCollection", src), (
        "init.js does not await createCollection — Milvus calls must be awaited"
    )


def test_ac2_collection_js_uses_milvus_sdk():
    """AC2: src/data/collection.js must use the Milvus SDK, not the filesystem."""
    with open(COLLECTION_JS_PATH) as f:
        src = f.read()
    assert "milvus2-sdk-node" in src or "MilvusClient" in src, (
        "src/data/collection.js does not import or reference the Milvus SDK"
    )


# ---------------------------------------------------------------------------
# AC3: After init, hasCollection returns true — live test
# ---------------------------------------------------------------------------

@needs_milvus
def test_ac3_init_creates_documents_collection():
    """AC3: 'commander init' creates the 'documents' collection in Milvus."""
    r = run_cli(["init"], timeout=60)
    assert r.returncode == 0, f"init failed (exit {r.returncode}): {r.stderr}"

    # Verify via SDK that the collection now exists
    script = f"""
import {{ MilvusClient }} from '@zilliz/milvus2-sdk-node';
const client = new MilvusClient({{ address: '{MILVUS_HOST}:{MILVUS_PORT}' }});
const res = await client.hasCollection({{ collection_name: 'documents' }});
process.stdout.write(JSON.stringify({{ exists: res.value }}));
"""
    result = run_node(script, timeout=30)
    assert result.returncode == 0, f"hasCollection check failed: {result.stderr}"
    data = json.loads(result.stdout)
    assert data["exists"] is True, (
        f"hasCollection returned false after 'commander init' — collection was not created"
    )


@needs_milvus
def test_ac3_init_collection_is_loaded():
    """AC3: After init, the documents collection is in LoadStateLoaded."""
    run_cli(["init"], timeout=60)

    script = f"""
import {{ MilvusClient }} from '@zilliz/milvus2-sdk-node';
const client = new MilvusClient({{ address: '{MILVUS_HOST}:{MILVUS_PORT}' }});
const res = await client.getLoadState({{ collection_name: 'documents' }});
process.stdout.write(JSON.stringify({{ state: res.state }}));
"""
    result = run_node(script, timeout=30)
    assert result.returncode == 0, f"getLoadState failed: {result.stderr}"
    data = json.loads(result.stdout)
    # LoadStateLoaded = 3 in Milvus SDK enum
    assert data["state"] in ("LoadStateLoaded", 3, "Loaded"), (
        f"Collection not in loaded state after init: {data['state']}"
    )


# ---------------------------------------------------------------------------
# AC4: runIngest upserts to Milvus — static analysis
# ---------------------------------------------------------------------------

def test_ac4_ingest_js_calls_upsertrows():
    """AC4: ingest.js must call upsertRows to persist chunks."""
    with open(INGEST_CMD_PATH) as f:
        src = f.read()
    assert "upsertRows" in src, (
        "ingest.js does not call upsertRows"
    )


def test_ac4_collection_js_upsert_uses_milvus_not_file():
    """AC4: upsertRows in collection.js must use Milvus SDK, not write to a file."""
    with open(COLLECTION_JS_PATH) as f:
        src = f.read()
    # Must have upsertRows function
    assert "upsertRows" in src, "collection.js must export upsertRows"
    # Must NOT use writeFileSync for persisting (that would be the old file-backed approach)
    assert "writeFileSync" not in src, (
        "collection.js uses writeFileSync — still file-backed, not Milvus"
    )


# ---------------------------------------------------------------------------
# AC5: Entity count in Milvus equals chunk count from CLI — live test
# ---------------------------------------------------------------------------

@needs_milvus
def test_ac5_milvus_entity_count_equals_chunk_count():
    """AC5: After ingest, Milvus entity count equals the chunk count reported by CLI."""
    # Ensure fresh state
    run_cli(["init"], timeout=60)
    r = run_cli(["ingest"], timeout=120)
    assert r.returncode == 0, f"ingest failed: {r.stderr}"

    _, m_chunks = parse_ingest_summary(r.stdout)
    assert m_chunks is not None, f"Could not parse chunk count from: {r.stdout!r}"

    script = f"""
import {{ MilvusClient }} from '@zilliz/milvus2-sdk-node';
const client = new MilvusClient({{ address: '{MILVUS_HOST}:{MILVUS_PORT}' }});
const stats = await client.getCollectionStatistics({{ collection_name: 'documents' }});
const countStat = (stats.stats || []).find(s => s.key === 'row_count');
const count = parseInt(countStat?.value ?? '0', 10);
process.stdout.write(JSON.stringify({{ count }}));
"""
    result = run_node(script, timeout=30)
    assert result.returncode == 0, f"getCollectionStatistics failed: {result.stderr}"
    data = json.loads(result.stdout)
    assert data["count"] == m_chunks, (
        f"Milvus entity count ({data['count']}) does not match CLI chunk count ({m_chunks})"
    )


# ---------------------------------------------------------------------------
# AC6: runInit and runIngest are async, CLI properly awaits them — static analysis
# ---------------------------------------------------------------------------

def test_ac6_run_init_is_async():
    """AC6: runInit must be declared as an async function."""
    with open(INIT_CMD_PATH) as f:
        src = f.read()
    assert re.search(r"export\s+async\s+function\s+runInit", src), (
        "runInit is not declared as 'export async function runInit' in init.js"
    )


def test_ac6_run_ingest_is_async():
    """AC6: runIngest must be declared as an async function."""
    with open(INGEST_CMD_PATH) as f:
        src = f.read()
    assert re.search(r"export\s+async\s+function\s+runIngest", src), (
        "runIngest is not declared as 'export async function runIngest' in ingest.js"
    )


def test_ac6_cli_awaits_runingest():
    """AC6: cli.js must await or properly handle the Promise from runIngest."""
    with open(CLI_PATH) as f:
        src = f.read()
    # Either directly awaited or handled via .then/.catch
    has_await = bool(re.search(r"await\s+runIngest\s*\(\s*\)", src))
    has_promise_chain = bool(re.search(r"runIngest\s*\(\s*\)\s*\.\s*(then|catch)", src))
    assert has_await or has_promise_chain, (
        "cli.js does not await runIngest() or chain its Promise — async errors will be silently dropped"
    )


# ---------------------------------------------------------------------------
# AC7: Attachments directory behaviour unchanged — live test
# ---------------------------------------------------------------------------

@needs_milvus
def test_ac7_ingest_creates_attachment_files():
    """AC7: After ingest, one .txt attachment file per article is created in attachments/."""
    run_cli(["init"], timeout=60)
    r = run_cli(["ingest"], timeout=120)
    assert r.returncode == 0, f"ingest failed: {r.stderr}"

    n_docs, _ = parse_ingest_summary(r.stdout)
    assert n_docs is not None and n_docs > 0

    assert os.path.isdir(ATTACHMENTS_DIR), "attachments/ directory not found after ingest"
    txt_files = [f for f in os.listdir(ATTACHMENTS_DIR) if f.endswith(".txt")]
    assert len(txt_files) == n_docs, (
        f"Expected {n_docs} attachment files, found {len(txt_files)}"
    )
    for fname in txt_files:
        path = os.path.join(ATTACHMENTS_DIR, fname)
        assert os.path.getsize(path) > 0, f"Attachment file is empty: {fname}"


@needs_milvus
def test_ac7_collection_json_absent_after_ingest():
    """AC7: collection.json must NOT be created after ingest."""
    # Remove it if it somehow exists from before
    if os.path.exists(COLLECTION_JSON_PATH):
        os.remove(COLLECTION_JSON_PATH)

    run_cli(["init"], timeout=60)
    run_cli(["ingest"], timeout=120)

    assert not os.path.exists(COLLECTION_JSON_PATH), (
        f"collection.json was created at {COLLECTION_JSON_PATH} — it must not exist"
    )


# ---------------------------------------------------------------------------
# AC8: No runtime errors when Milvus stack is up — live test
# ---------------------------------------------------------------------------

@needs_milvus
def test_ac8_init_exits_0():
    """AC8: 'commander init' exits 0 with no stderr errors."""
    r = run_cli(["init"], timeout=60)
    assert r.returncode == 0, (
        f"'commander init' exited {r.returncode}\nstderr: {r.stderr}"
    )


@needs_milvus
def test_ac8_ingest_exits_0():
    """AC8: 'commander ingest' exits 0 with no stderr errors."""
    run_cli(["init"], timeout=60)
    r = run_cli(["ingest"], timeout=120)
    assert r.returncode == 0, (
        f"'commander ingest' exited {r.returncode}\nstderr: {r.stderr}"
    )


@needs_milvus
def test_ac8_ingest_idempotent_upsert():
    """AC8: Running ingest twice does not double the entity count (upsert semantics)."""
    run_cli(["init"], timeout=60)

    r1 = run_cli(["ingest"], timeout=120)
    assert r1.returncode == 0, f"First ingest failed: {r1.stderr}"
    _, chunks1 = parse_ingest_summary(r1.stdout)

    r2 = run_cli(["ingest"], timeout=120)
    assert r2.returncode == 0, f"Second ingest failed: {r2.stderr}"
    _, chunks2 = parse_ingest_summary(r2.stdout)

    assert chunks1 == chunks2, f"Chunk counts differ between runs: {chunks1} vs {chunks2}"

    # Entity count must not have doubled
    script = f"""
import {{ MilvusClient }} from '@zilliz/milvus2-sdk-node';
const client = new MilvusClient({{ address: '{MILVUS_HOST}:{MILVUS_PORT}' }});
const stats = await client.getCollectionStatistics({{ collection_name: 'documents' }});
const countStat = (stats.stats || []).find(s => s.key === 'row_count');
const count = parseInt(countStat?.value ?? '0', 10);
process.stdout.write(JSON.stringify({{ count }}));
"""
    result = run_node(script, timeout=30)
    assert result.returncode == 0, f"getCollectionStatistics failed: {result.stderr}"
    data = json.loads(result.stdout)
    assert data["count"] == chunks2, (
        f"After second ingest, Milvus entity count ({data['count']}) != chunk count ({chunks2}). "
        f"Upsert should overwrite, not duplicate."
    )
