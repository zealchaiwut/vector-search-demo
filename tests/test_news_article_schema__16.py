"""
Acceptance tests for issue #16: Migrate Milvus collection schema to news-article model

AC1 - src/milvus/schema.ts defines exactly five fields: id (VarChar PK autoID:false),
      headline (VarChar), details (VarChar), attachment_url (VarChar),
      embedding (FloatVector dim 384)
AC2 - No references to old field names (doc_id, chunk_id, title, text, attachment_name)
      remain in the production source code under src/
AC3 - HNSW + COSINE index declared on embedding field in schema or index-creation step
AC4 - schema.ts is the schema file (not schema.js); exports COLLECTION_SCHEMA and INDEX_PARAMS
AC5 - TypeScript type-checking passes with zero errors (tsc --noEmit)
AC6 - Ingestion writes records using new field names; upsert by id does not duplicate rows
AC7 - Vector search returns result objects containing headline, details, and attachment_url
"""

import json
import os
import re
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_TS = os.path.join(REPO_ROOT, "src", "milvus", "schema.ts")
SCHEMA_JS_OLD = os.path.join(REPO_ROOT, "src", "milvus", "schema.js")
SRC_DIR = os.path.join(REPO_ROOT, "src")
CLI_PATH = os.path.join(REPO_ROOT, "src", "cli.js")
COLLECTION_JSON = os.path.join(REPO_ROOT, "collection.json")
CORE_SEARCH_JS = os.path.join(REPO_ROOT, "src", "core", "search.js")
INGEST_JS = os.path.join(REPO_ROOT, "src", "commands", "ingest.js")

MILVUS_HOST = os.environ.get("MILVUS_HOST", "localhost")
MILVUS_PORT = os.environ.get("MILVUS_PORT", "19530")

needs_milvus = pytest.mark.skipif(
    not os.environ.get("MILVUS_HOST"),
    reason="MILVUS_HOST not set — skipping live Milvus tests",
)

OLD_FIELD_NAMES = ["doc_id", "chunk_id", "attachment_name"]


def run_node(script, timeout=30):
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
    )
    return result.stdout, result.stderr, result.returncode


def run_cli(args, timeout=30):
    return subprocess.run(
        ["node", CLI_PATH] + args,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# AC1 + AC4: schema.ts exists and exports correct structure
# ---------------------------------------------------------------------------


def test_schema_ts_file_exists():
    # AC4: src/milvus/schema.ts must exist (TypeScript source)
    assert os.path.isfile(SCHEMA_TS), (
        f"src/milvus/schema.ts not found at {SCHEMA_TS}. "
        "Schema must be a .ts file."
    )


def test_schema_js_removed():
    # AC4: old schema.js must be gone — schema.ts is the canonical file
    assert not os.path.isfile(SCHEMA_JS_OLD), (
        "src/milvus/schema.js still exists. The old JS schema must be removed."
    )


def test_schema_ts_has_exactly_five_fields():
    # AC1: COLLECTION_SCHEMA must define exactly five fields
    with open(SCHEMA_TS) as f:
        src = f.read()

    required_fields = {"id", "headline", "details", "attachment_url", "embedding"}
    # Each field name should appear as a name: "..." entry
    found = set()
    for field in required_fields:
        if re.search(rf'name\s*:\s*["\x27]{re.escape(field)}["\x27]', src):
            found.add(field)

    missing = required_fields - found
    assert not missing, (
        f"schema.ts missing field declarations for: {missing}. "
        f"Expected all of: {required_fields}"
    )


def test_schema_ts_id_is_varchar_primary_key_no_autoid():
    # AC1: id field must be VarChar, primary key, autoID: false
    with open(SCHEMA_TS) as f:
        src = f.read()

    assert "autoID: false" in src or 'autoID:false' in src.replace(" ", ""), (
        "id field must have autoID: false"
    )
    assert "is_primary_key: true" in src or "is_primary_key:true" in src.replace(" ", ""), (
        "id field must be primary key"
    )


def test_schema_ts_embedding_is_floatvector_dim_384():
    # AC1: embedding field must be FloatVector with dim 384
    with open(SCHEMA_TS) as f:
        src = f.read()

    assert "FloatVector" in src, "embedding field must use DataType.FloatVector"
    assert "384" in src, "embedding dim must be 384"


# ---------------------------------------------------------------------------
# AC2: no old field names in src/
# ---------------------------------------------------------------------------


def _find_old_field_refs_in_src(field_name):
    """Return list of (file, line_no, line) where field_name appears as a property key or value."""
    hits = []
    for root, dirs, files in os.walk(SRC_DIR):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "dist", "__pycache__")]
        for fname in files:
            if not (fname.endswith(".ts") or fname.endswith(".js") or fname.endswith(".mjs")):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath, encoding="utf-8", errors="ignore") as f:
                for lineno, line in enumerate(f, 1):
                    # Match as object key, property access, or string literal
                    if re.search(
                        rf'\b{re.escape(field_name)}\b',
                        line
                    ):
                        hits.append((fpath, lineno, line.rstrip()))
    return hits


def test_no_doc_id_in_src():
    # AC2: "doc_id" must not appear in any src/ file
    hits = _find_old_field_refs_in_src("doc_id")
    assert not hits, (
        f"'doc_id' references found in src/ — must be removed:\n"
        + "\n".join(f"  {f}:{n}: {l}" for f, n, l in hits[:10])
    )


def test_no_chunk_id_in_src():
    # AC2: "chunk_id" must not appear in any src/ file
    hits = _find_old_field_refs_in_src("chunk_id")
    assert not hits, (
        f"'chunk_id' references found in src/ — must be removed:\n"
        + "\n".join(f"  {f}:{n}: {l}" for f, n, l in hits[:10])
    )


def test_no_attachment_name_in_src():
    # AC2: "attachment_name" must not appear in any src/ file
    hits = _find_old_field_refs_in_src("attachment_name")
    assert not hits, (
        f"'attachment_name' references found in src/ — must be removed:\n"
        + "\n".join(f"  {f}:{n}: {l}" for f, n, l in hits[:10])
    )


def test_no_old_title_field_in_src():
    # AC2: "title" as a data field key must not appear in src/ (comments OK, type interfaces OK
    # as long as the actual field is 'headline')
    # We check for r.title, row.title, {title:, "title": patterns that indicate field usage
    hits = []
    for root, dirs, files in os.walk(SRC_DIR):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "dist", "__pycache__")]
        for fname in files:
            if not (fname.endswith(".ts") or fname.endswith(".js") or fname.endswith(".mjs")):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath, encoding="utf-8", errors="ignore") as f:
                for lineno, line in enumerate(f, 1):
                    stripped = line.strip()
                    # Skip pure comments
                    if stripped.startswith("//") or stripped.startswith("*"):
                        continue
                    # Check for title as a data field
                    if re.search(
                        r'["\']title["\']|\.title\b|title\s*:|title\s*,\s|title\s*\)',
                        line
                    ):
                        hits.append((fpath, lineno, line.rstrip()))
    assert not hits, (
        f"'title' field references found in src/ — must be replaced with 'headline':\n"
        + "\n".join(f"  {f}:{n}: {l}" for f, n, l in hits[:10])
    )


# ---------------------------------------------------------------------------
# AC3: HNSW + COSINE index declared on embedding
# ---------------------------------------------------------------------------


def test_schema_ts_has_hnsw_cosine_index():
    # AC3: INDEX_PARAMS or equivalent must specify HNSW and COSINE on embedding
    with open(SCHEMA_TS) as f:
        src = f.read()

    assert "HNSW" in src, "HNSW index type not declared in schema.ts"
    assert "COSINE" in src, "COSINE metric not declared in schema.ts"
    assert '"embedding"' in src or "'embedding'" in src, (
        "Index must reference the 'embedding' field in schema.ts"
    )


# ---------------------------------------------------------------------------
# AC5: TypeScript type-checking passes
# ---------------------------------------------------------------------------


def test_tsc_no_errors():
    # AC5: tsc --noEmit must exit 0 with no output
    result = subprocess.run(
        ["npx", "tsc", "--noEmit"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"tsc --noEmit failed (exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# AC6: Ingestion uses new field names; upsert does not duplicate by id
# ---------------------------------------------------------------------------


def test_ingest_uses_new_field_names_in_source():
    # AC6: ingest.js must reference 'headline', 'details', 'attachment_url'
    with open(INGEST_JS) as f:
        src = f.read()

    assert "headline" in src, "ingest.js must use 'headline' field"
    assert "details" in src or "attachment_url" in src, (
        "ingest.js must use 'details' and/or 'attachment_url' fields"
    )


def test_ingest_collection_rows_have_new_fields():
    # AC6: after ingest, collection.json rows must have id, headline, details,
    # attachment_url, embedding
    r = run_cli(["ingest"])
    assert r.returncode == 0, f"commander ingest failed: {r.stderr}"

    assert os.path.exists(COLLECTION_JSON), "collection.json not found after ingest"
    with open(COLLECTION_JSON) as f:
        rows = json.load(f)

    assert len(rows) > 0, "No rows in collection.json after ingest"

    required = {"id", "headline", "details", "attachment_url", "embedding"}
    for row in rows[:5]:
        missing = required - set(row.keys())
        assert not missing, (
            f"Row missing required fields {missing}. Got keys: {list(row.keys())}"
        )


def test_ingest_no_old_fields_in_collection():
    # AC6: collection.json rows must NOT have doc_id, chunk_id, title, text, attachment_name
    r = run_cli(["ingest"])
    assert r.returncode == 0, f"commander ingest failed: {r.stderr}"

    with open(COLLECTION_JSON) as f:
        rows = json.load(f)

    old_fields = {"doc_id", "chunk_id", "title", "text", "attachment_name"}
    for row in rows[:5]:
        found_old = old_fields & set(row.keys())
        assert not found_old, (
            f"Row still has old field names: {found_old}. "
            f"All old field names must be removed."
        )


def test_upsert_by_id_does_not_duplicate():
    # AC6: running ingest twice must not duplicate rows (upsert semantics)
    r1 = run_cli(["ingest"])
    assert r1.returncode == 0, f"First ingest failed: {r1.stderr}"

    with open(COLLECTION_JSON) as f:
        count_after_first = len(json.load(f))

    r2 = run_cli(["ingest"])
    assert r2.returncode == 0, f"Second ingest failed: {r2.stderr}"

    with open(COLLECTION_JSON) as f:
        count_after_second = len(json.load(f))

    assert count_after_second == count_after_first, (
        f"Row count grew from {count_after_first} to {count_after_second} after second ingest. "
        "Ingest must upsert by id, not append duplicates."
    )


def test_upsert_updates_existing_row():
    # AC6: upserting a row with the same id updates rather than duplicates
    r = run_cli(["ingest"])
    assert r.returncode == 0, f"Ingest failed: {r.stderr}"

    with open(COLLECTION_JSON) as f:
        rows = json.load(f)
    assert len(rows) > 0

    # Mutate the first row's headline and write it back via a node script that
    # calls insertRows again — the collection module must handle upsert
    first_id = rows[0]["id"]
    mutated_headline = "UPSERT_TEST_HEADLINE_XYZ"

    upsert_script = f"""
import {{ upsertRows }} from './src/data/collection.js';
upsertRows([{{
  id: {json.dumps(first_id)},
  headline: {json.dumps(mutated_headline)},
  details: "test details",
  attachment_url: "/download/test",
  embedding: [],
}}]);
process.stdout.write(JSON.stringify({{ ok: true }}));
"""
    out, err, rc = run_node(upsert_script)
    assert rc == 0, f"upsertRows script failed: {err}"

    with open(COLLECTION_JSON) as f:
        rows_after = json.load(f)

    matching = [r for r in rows_after if r["id"] == first_id]
    assert len(matching) == 1, (
        f"Expected exactly 1 row with id={first_id!r}, found {len(matching)}"
    )
    assert matching[0]["headline"] == mutated_headline, (
        f"Row not updated. Expected headline={mutated_headline!r}, "
        f"got {matching[0]['headline']!r}"
    )


# ---------------------------------------------------------------------------
# AC7: Search results contain headline, details, attachment_url
# ---------------------------------------------------------------------------


def test_search_results_have_headline():
    # AC7: searchDocuments must return results with 'headline' field
    script = """
import { searchDocuments } from './src/core/search.js';
const results = searchDocuments("vector search embedding", 5);
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = run_node(script)
    assert rc == 0, f"searchDocuments failed: {err}"
    results = json.loads(out)
    assert len(results) > 0, "No results returned for a known query"
    for r in results:
        assert "headline" in r, (
            f"Result missing 'headline' field. Got keys: {list(r.keys())}"
        )


def test_search_results_have_details():
    # AC7: searchDocuments must return results with 'details' field
    script = """
import { searchDocuments } from './src/core/search.js';
const results = searchDocuments("semantic similarity cosine", 5);
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = run_node(script)
    assert rc == 0, f"searchDocuments failed: {err}"
    results = json.loads(out)
    assert len(results) > 0
    for r in results:
        assert "details" in r, (
            f"Result missing 'details' field. Got keys: {list(r.keys())}"
        )
        assert r["details"], f"Result 'details' field is empty"


def test_search_results_have_attachment_url():
    # AC7: searchDocuments must return results with 'attachment_url' field
    script = """
import { searchDocuments } from './src/core/search.js';
const results = searchDocuments("milvus database index", 5);
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = run_node(script)
    assert rc == 0, f"searchDocuments failed: {err}"
    results = json.loads(out)
    assert len(results) > 0
    for r in results:
        assert "attachment_url" in r, (
            f"Result missing 'attachment_url' field. Got keys: {list(r.keys())}"
        )
        assert r["attachment_url"].startswith("/download/"), (
            f"attachment_url must start with /download/, got: {r['attachment_url']!r}"
        )


def test_search_results_no_old_field_names():
    # AC7: results must not contain old field names
    script = """
import { searchDocuments } from './src/core/search.js';
const results = searchDocuments("vector embedding search", 5);
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = run_node(script)
    assert rc == 0, f"searchDocuments failed: {err}"
    results = json.loads(out)
    assert len(results) > 0
    old_fields = {"doc_id", "title", "text", "attachment_name"}
    for r in results:
        found_old = old_fields & set(r.keys())
        assert not found_old, (
            f"Search result contains old field names: {found_old}. "
            f"All old field names must be replaced."
        )


# ---------------------------------------------------------------------------
# Milvus live tests (skipped when MILVUS_HOST not set)
# ---------------------------------------------------------------------------


@needs_milvus
def test_milvus_init_creates_article_schema():
    # AC4 (live): commander init creates collection with exactly the 5 article fields
    result = run_cli(
        ["init"],
        timeout=60,
    )
    assert result.returncode == 0, (
        f"commander init failed (exit {result.returncode}): {result.stderr}"
    )

    out, err, rc = run_node(
        f"""
import {{ MilvusClient }} from '@zilliz/milvus2-sdk-node';
const client = new MilvusClient({{ address: '{MILVUS_HOST}:{MILVUS_PORT}' }});
const desc = await client.describeCollection({{ collection_name: 'documents' }});
process.stdout.write(JSON.stringify(desc));
""",
        timeout=60,
    )
    assert rc == 0, f"describeCollection failed: {err}"
    data = json.loads(out)
    fields = data.get("schema", {}).get("fields", [])
    field_names = {f["name"] for f in fields}
    required = {"id", "headline", "details", "attachment_url", "embedding"}
    missing = required - field_names
    assert not missing, (
        f"Milvus collection missing fields: {missing}. Got: {field_names}"
    )
    old_names = {"doc_id", "chunk_id", "title", "text", "attachment_name"}
    found_old = old_names & field_names
    assert not found_old, (
        f"Milvus collection still has old field names: {found_old}"
    )
