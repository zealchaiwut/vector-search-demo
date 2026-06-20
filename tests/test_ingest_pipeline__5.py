"""Tests for issue #5: Build ingestion pipeline for commander ingest command (runs against UAT)"""
import json
import os
import re
import subprocess

import pytest

# UAT environment: the coder clone checked out on the feature branch is the deployed UAT app.
# The server is started from that directory; CLI tests run there too.
CODER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "coder")
)
CLI_PATH = os.path.join(CODER_DIR, "src", "cli.js")
DATA_DIR = os.path.join(CODER_DIR, "src", "data")
INGEST_CMD_PATH = os.path.join(CODER_DIR, "src", "commands", "ingest.js")
GENERATOR_PATH = os.path.join(DATA_DIR, "generator.js")
COLLECTION_JSON = os.path.join(CODER_DIR, "collection.json")
ATTACHMENTS_DIR = os.path.join(CODER_DIR, "attachments")

UAT_BASE_URL = os.environ.get("UAT_BASE_URL", "http://localhost:8001")


def run_ingest(timeout=30):
    return subprocess.run(
        ["node", CLI_PATH, "ingest"],
        capture_output=True,
        text=True,
        cwd=CODER_DIR,
        timeout=timeout,
    )


def parse_summary(stdout):
    m = re.search(r"(\d+)\s+docs\s*/\s*(\d+)\s+chunks\s+indexed", stdout)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


# --- AC1: commander ingest exits 0 and prints summary ---

def test_ingest_pipeline__runs_exits_0_prints_summary():
    # AC1: commander ingest completes without error, prints "N docs / M chunks indexed"
    r = run_ingest()
    assert r.returncode == 0, f"ingest exited {r.returncode}: {r.stderr}"
    n_docs, m_chunks = parse_summary(r.stdout)
    assert n_docs is not None, f"Summary line not found in stdout: {r.stdout!r}"
    assert n_docs > 0 and m_chunks > 0, f"Expected non-zero counts, got {n_docs}/{m_chunks}"


# --- AC2: collection entity count equals M ---

def test_ingest_pipeline__collection_entity_count_equals_chunk_count():
    # AC2: collection.json row count equals chunk count printed in summary
    r = run_ingest()
    assert r.returncode == 0, f"ingest failed: {r.stderr}"
    _, m_chunks = parse_summary(r.stdout)
    assert os.path.exists(COLLECTION_JSON), "collection.json not found"
    with open(COLLECTION_JSON) as f:
        rows = json.load(f)
    assert len(rows) == m_chunks, (
        f"Collection has {len(rows)} rows but summary said {m_chunks} chunks"
    )


# --- AC3: src/data/ isolated generator ---

def test_ingest_pipeline__generator_isolated_from_pipeline():
    # AC3: generator.js has no import from src/commands/
    assert os.path.exists(GENERATOR_PATH), f"generator.js not found at {GENERATOR_PATH}"
    with open(GENERATOR_PATH) as f:
        src = f.read()
    import_lines = [l for l in src.splitlines() if re.match(r'\s*(import|require)', l)]
    assert not any("commands" in l for l in import_lines), (
        "generator.js has an import from src/commands/ — isolation broken"
    )
    # ingest.js imports from src/data/ only (not internals)
    assert os.path.exists(INGEST_CMD_PATH), f"ingest.js not found at {INGEST_CMD_PATH}"
    with open(INGEST_CMD_PATH) as f:
        ingest_src = f.read()
    assert "../data/" in ingest_src, "ingest.js should import from ../data/"


# --- AC4: generator produces ~15 docs across >= 5 topic areas ---

def test_ingest_pipeline__generator_produces_15_docs_5_topics():
    # AC4: DOCUMENTS array has ~15 entries; at least 5 distinct topic values
    with open(GENERATOR_PATH) as f:
        src = f.read()
    # Count id entries as proxy for doc count
    id_count = len(re.findall(r'\bid\s*:', src))
    assert id_count >= 14, f"Expected ~15 docs, found only {id_count} id entries"
    # Topics: infra, security, hr, product, finance appear in source
    topics = {"infra", "security", "hr", "product", "finance"}
    found = {t for t in topics if t in src.lower()}
    assert len(found) >= 5, f"Expected >= 5 distinct topics, found: {found}"


# --- AC5: chunker size and overlap defined as named constants ---
# Updated by issue #98: chunking switched from word-based (120w/30w) to
# character-based (CHUNK_SIZE/CHUNK_OVERLAP) for Thai language support.

def test_ingest_pipeline__chunks_120_words_30_word_overlap():
    # AC5 (updated by #98): chunker defines CHUNK_SIZE and CHUNK_OVERLAP as named constants
    chunker_path = os.path.join(DATA_DIR, "chunker.js")
    assert os.path.exists(chunker_path), f"chunker.js not found at {chunker_path}"
    with open(chunker_path) as f:
        src = f.read()
    assert "CHUNK_SIZE" in src, "CHUNK_SIZE constant not found in chunker.js"
    assert "CHUNK_OVERLAP" in src, "CHUNK_OVERLAP constant not found in chunker.js"


# --- AC6: chunks batch-embedded before insertion ---

def test_ingest_pipeline__chunks_batch_embedded_before_insert():
    # AC6: ingest.js calls batchEmbed on all chunks before upsertRows
    with open(INGEST_CMD_PATH) as f:
        src = f.read()
    assert "batchEmbed" in src, "ingest.js must call batchEmbed"
    # batchEmbed called before upsertRows in source order
    batch_pos = src.index("batchEmbed")
    upsert_pos = src.index("upsertRows")
    assert batch_pos < upsert_pos, "batchEmbed must appear before upsertRows in ingest.js"


# --- AC7: each inserted row has required fields ---

def test_ingest_pipeline__rows_have_required_fields():
    # AC7: every row in collection.json has id, headline, details, attachment_url, embedding
    r = run_ingest()
    assert r.returncode == 0, f"ingest failed: {r.stderr}"
    with open(COLLECTION_JSON) as f:
        rows = json.load(f)
    assert len(rows) > 0, "No rows in collection.json"
    required = {"id", "headline", "details", "attachment_url", "embedding"}
    for row in rows[:5]:  # spot-check first 5
        missing = required - set(row.keys())
        assert not missing, f"Row {row.get('id')} missing fields: {missing}"
        assert isinstance(row["embedding"], list) and len(row["embedding"]) > 0


# --- AC8: attachments/<doc_id>.txt exists and non-empty ---

def test_ingest_pipeline__attachments_exist_and_non_empty():
    # AC8: one .txt file per doc in attachments/, all non-empty
    r = run_ingest()
    assert r.returncode == 0, f"ingest failed: {r.stderr}"
    n_docs, _ = parse_summary(r.stdout)
    assert os.path.isdir(ATTACHMENTS_DIR), f"attachments/ not found at {ATTACHMENTS_DIR}"
    txt_files = [f for f in os.listdir(ATTACHMENTS_DIR) if f.endswith(".txt")]
    assert len(txt_files) == n_docs, (
        f"Expected {n_docs} .txt files, found {len(txt_files)}"
    )
    for fname in txt_files:
        path = os.path.join(ATTACHMENTS_DIR, fname)
        assert os.path.getsize(path) > 0, f"Attachment file is empty: {fname}"


# --- AC9: idempotent — second run gives same counts, no duplication ---

def test_ingest_pipeline__idempotent_second_run():
    # AC9: running ingest twice yields same entity count (no duplication or stale data)
    r1 = run_ingest()
    assert r1.returncode == 0, f"First ingest failed: {r1.stderr}"
    n1, m1 = parse_summary(r1.stdout)

    r2 = run_ingest()
    assert r2.returncode == 0, f"Second ingest failed: {r2.stderr}"
    n2, m2 = parse_summary(r2.stdout)

    assert n1 == n2 and m1 == m2, f"Counts differ: first={n1}/{m1}, second={n2}/{m2}"
    with open(COLLECTION_JSON) as f:
        rows = json.load(f)
    assert len(rows) == m2, (
        f"After second run collection has {len(rows)} rows but expected {m2}"
    )
    txt_files = [f for f in os.listdir(ATTACHMENTS_DIR) if f.endswith(".txt")]
    assert len(txt_files) == n2, (
        f"After second run expected {n2} attachment files, found {len(txt_files)}"
    )


# --- AC10: only target files touched; cli.js routes ingest ---

def test_ingest_pipeline__only_target_files_and_cli_routes_ingest():
    # AC10: ingest.js + src/data/* exist; cli.js handles "ingest" command
    assert os.path.exists(INGEST_CMD_PATH), "src/commands/ingest.js not found"
    for fname in ["generator.js", "chunker.js", "embedder.js", "collection.js"]:
        path = os.path.join(DATA_DIR, fname)
        assert os.path.exists(path), f"src/data/{fname} not found"
    cli_path = os.path.join(CODER_DIR, "src", "cli.js")
    with open(cli_path) as f:
        cli_src = f.read()
    assert "ingest" in cli_src, "cli.js does not handle 'ingest' command"
    assert "runIngest" in cli_src, "cli.js does not import/call runIngest"
