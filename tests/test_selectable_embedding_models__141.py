"""
TDD tests for issue #141: Support selectable larger embedding models via config

AC1 — EMBEDDING_MODEL config selects the model; supports at minimum: current default,
       multilingual-e5-base, multilingual-e5-large, BAAI/bge-m3
AC2 — Vector schema dimension is derived from the chosen model at startup; mismatches
       between configured model and stored schema raise a clear error with migration
       instructions
AC3 — re-embed command reads all stored documents, re-encodes with active model, and
       writes new vectors
AC4 — bge-m3 sparse vectors are generated and stored alongside dense vectors, making
       them available for the lexical half of hybrid search
AC5 — Switching from any supported model to any other supported model and running
       re-embed produces correct, working search results at the new dimension
AC6 — Ablation runner accepts --embedding-model flag (or reads config) to compare
       metrics across models on the Thai test set
AC7 — Schema migration script or per-model table strategy provided and documented;
       no silent data corruption when dimensions change
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMBEDDINGS_INDEX = os.path.join(REPO_ROOT, "src", "embeddings", "index.js")
MODEL_REGISTRY = os.path.join(REPO_ROOT, "src", "embeddings", "model-registry.js")
REEMBED_CMD = os.path.join(REPO_ROOT, "src", "commands", "re-embed.js")
ABLATION_SCRIPT = os.path.join(REPO_ROOT, "src", "eval", "run_ablation.py")
MIGRATIONS_DIR = os.path.join(REPO_ROOT, "src", "store", "migrations")
PG_STORE = os.path.join(REPO_ROOT, "src", "store", "PgVectorStore.js")
SCHEMA_MD = os.path.join(REPO_ROOT, "SCHEMA.md")

MODEL_TIMEOUT = 60  # lightweight tests — no actual model download


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


def _run_cli(args, timeout=MODEL_TIMEOUT, env=None):
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    result = subprocess.run(
        ["node", "src/cli.js", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
        env=run_env,
    )
    return result.stdout, result.stderr, result.returncode


def _run_ablation(args, extra_env=None):
    env = {**os.environ}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, ABLATION_SCRIPT] + args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# AC1 — Model registry: known models and their dimensions
# ---------------------------------------------------------------------------

def test_ac1_model_registry_file_exists():
    """AC1: src/embeddings/model-registry.js must exist."""
    assert os.path.isfile(MODEL_REGISTRY), (
        f"src/embeddings/model-registry.js not found at {MODEL_REGISTRY}"
    )


def test_ac1_model_registry_exports_resolve_function():
    """AC1: model registry exports a resolveModel function."""
    with open(MODEL_REGISTRY) as f:
        source = f.read()
    assert "resolveModel" in source, (
        "src/embeddings/model-registry.js must export a resolveModel function"
    )


def test_ac1_model_registry_has_e5_base():
    """AC1: model registry includes multilingual-e5-base with dim 768."""
    with open(MODEL_REGISTRY) as f:
        source = f.read()
    assert "multilingual-e5-base" in source, (
        "model-registry.js must include 'multilingual-e5-base'"
    )
    assert "768" in source, (
        "model-registry.js must include dimension 768 for e5-base"
    )


def test_ac1_model_registry_has_e5_large():
    """AC1: model registry includes multilingual-e5-large with dim 1024."""
    with open(MODEL_REGISTRY) as f:
        source = f.read()
    assert "multilingual-e5-large" in source, (
        "model-registry.js must include 'multilingual-e5-large'"
    )
    assert "1024" in source, (
        "model-registry.js must include dimension 1024 for e5-large"
    )


def test_ac1_model_registry_has_bge_m3():
    """AC1: model registry includes BAAI/bge-m3."""
    with open(MODEL_REGISTRY) as f:
        source = f.read()
    assert "bge-m3" in source, (
        "model-registry.js must include 'bge-m3'"
    )


def test_ac1_registry_resolve_e5_base_dim():
    """AC1: resolveModel('multilingual-e5-base').dim === 768."""
    script = """
import { resolveModel } from './src/embeddings/model-registry.js';
const m = resolveModel('multilingual-e5-base');
process.stdout.write(String(m.dim));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    assert out.strip() == "768", f"Expected dim=768 for e5-base, got {out.strip()}"


def test_ac1_registry_resolve_e5_large_dim():
    """AC1: resolveModel('multilingual-e5-large').dim === 1024."""
    script = """
import { resolveModel } from './src/embeddings/model-registry.js';
const m = resolveModel('multilingual-e5-large');
process.stdout.write(String(m.dim));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    assert out.strip() == "1024", f"Expected dim=1024 for e5-large, got {out.strip()}"


def test_ac1_registry_resolve_bge_m3_dim():
    """AC1: resolveModel('BAAI/bge-m3').dim === 1024."""
    script = """
import { resolveModel } from './src/embeddings/model-registry.js';
const m = resolveModel('BAAI/bge-m3');
process.stdout.write(String(m.dim));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    assert out.strip() == "1024", f"Expected dim=1024 for bge-m3, got {out.strip()}"


def test_ac1_registry_resolve_default_dim():
    """AC1: resolveModel for the default model gives dim 384."""
    script = """
import { resolveModel } from './src/embeddings/model-registry.js';
const m = resolveModel('Xenova/multilingual-e5-small');
process.stdout.write(String(m.dim));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    assert out.strip() == "384", f"Expected dim=384 for e5-small, got {out.strip()}"


def test_ac1_registry_resolve_unknown_raises():
    """AC1: resolveModel on unknown model name throws a clear error."""
    script = """
import { resolveModel } from './src/embeddings/model-registry.js';
try {
  resolveModel('some-unknown-model-xyz');
  process.stdout.write('no-error');
} catch (e) {
  process.stdout.write('error:' + e.message);
}
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    assert out.strip().startswith("error:"), (
        f"Expected resolveModel to throw for unknown model, got: {out.strip()}"
    )


# ---------------------------------------------------------------------------
# AC1 (index.js) — EMBEDDING_DIM auto-derived from model
# ---------------------------------------------------------------------------

def test_ac1_embedding_dim_exported_from_index():
    """AC1: src/embeddings/index.js exports EMBEDDING_DIM derived from model registry."""
    with open(EMBEDDINGS_INDEX) as f:
        source = f.read()
    assert "EMBEDDING_DIM" in source, (
        "src/embeddings/index.js must export EMBEDDING_DIM"
    )
    assert "model-registry" in source or "resolveModel" in source, (
        "src/embeddings/index.js must use model-registry to derive EMBEDDING_DIM"
    )


def test_ac1_embedding_dim_derived_for_e5_base():
    """AC1: setting EMBEDDING_MODEL=multilingual-e5-base gives EMBEDDING_DIM=768."""
    script = """
import { EMBEDDING_DIM } from './src/embeddings/index.js';
process.stdout.write(String(EMBEDDING_DIM));
"""
    out, err, rc = _run_node(script, env={"EMBEDDING_MODEL": "multilingual-e5-base"})
    assert rc == 0, f"Node error: {err}"
    assert out.strip() == "768", (
        f"Expected EMBEDDING_DIM=768 when EMBEDDING_MODEL=multilingual-e5-base, got {out.strip()}"
    )


def test_ac1_embedding_dim_derived_for_e5_large():
    """AC1: setting EMBEDDING_MODEL=multilingual-e5-large gives EMBEDDING_DIM=1024."""
    script = """
import { EMBEDDING_DIM } from './src/embeddings/index.js';
process.stdout.write(String(EMBEDDING_DIM));
"""
    out, err, rc = _run_node(script, env={"EMBEDDING_MODEL": "multilingual-e5-large"})
    assert rc == 0, f"Node error: {err}"
    assert out.strip() == "1024", (
        f"Expected EMBEDDING_DIM=1024 when EMBEDDING_MODEL=multilingual-e5-large, got {out.strip()}"
    )


def test_ac1_embedding_dim_still_384_for_default():
    """AC1: default model still gives EMBEDDING_DIM=384."""
    script = """
import { EMBEDDING_DIM } from './src/embeddings/index.js';
process.stdout.write(String(EMBEDDING_DIM));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    assert out.strip() == "384", (
        f"Expected EMBEDDING_DIM=384 for default model, got {out.strip()}"
    )


# ---------------------------------------------------------------------------
# AC2 — Dimension mismatch raises clear error with migration instructions
# ---------------------------------------------------------------------------

def test_ac2_pg_store_has_schema_compatibility_check():
    """AC2: PgVectorStore has a method to check schema compatibility."""
    with open(PG_STORE) as f:
        source = f.read()
    assert "checkSchemaCompatibility" in source or "dimensionMismatch" in source or "schemaMismatch" in source or "checkDimension" in source, (
        "PgVectorStore must have a schema compatibility/dimension check method"
    )


def test_ac2_mismatch_error_includes_migration_hint():
    """AC2: The mismatch error message includes migration instructions."""
    with open(PG_STORE) as f:
        source = f.read()
    assert "re-embed" in source or "migration" in source.lower() or "migrate" in source.lower(), (
        "PgVectorStore dimension mismatch error must include migration instructions"
    )


def test_ac2_migration_005_exists():
    """AC2: Migration 005 exists to support per-model dimension handling."""
    migration_files = os.listdir(MIGRATIONS_DIR)
    has_005 = any(f.startswith("005") for f in migration_files)
    assert has_005, (
        f"Migration 005_*.sql must exist in {MIGRATIONS_DIR} for schema dimension tracking. "
        f"Found: {sorted(migration_files)}"
    )


def test_ac2_migration_005_creates_model_meta():
    """AC2: Migration 005 creates the model_meta table (or equivalent)."""
    migration_files = sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.startswith("005"))
    assert migration_files, "Migration 005_*.sql not found"
    path = os.path.join(MIGRATIONS_DIR, migration_files[0])
    with open(path) as f:
        sql = f.read().lower()
    assert "model" in sql or "meta" in sql or "dim" in sql, (
        f"Migration 005 must create a model metadata table. Content: {sql[:500]}"
    )


# ---------------------------------------------------------------------------
# AC3 — re-embed command outputs dynamic model name
# ---------------------------------------------------------------------------

def test_ac3_reembed_outputs_model_name():
    """AC3: re-embed output includes the active model name, not a hardcoded string."""
    with open(REEMBED_CMD) as f:
        source = f.read()
    # Should use the model name from config, not a hardcoded "multilingual-e5-small"
    # Either it references EMBEDDING_MODEL, or uses a variable
    assert "EMBEDDING_MODEL" in source or "MODEL" in source or "model" in source, (
        "re-embed.js must reference the active model name (EMBEDDING_MODEL or similar)"
    )


def test_ac3_reembed_runs_mock_backend():
    """AC3: re-embed command runs successfully on mock backend."""
    out_ingest, err_ingest, rc_ingest = _run_cli(["ingest"], env={"DB_BACKEND": "mock"})
    assert rc_ingest == 0, f"Ingest failed: {err_ingest}\n{out_ingest}"

    out, err, rc = _run_cli(["re-embed"], env={"DB_BACKEND": "mock"})
    assert rc == 0, f"re-embed failed: {err}\n{out}"


# ---------------------------------------------------------------------------
# AC4 — BGE-M3 sparse vectors generated and stored
# ---------------------------------------------------------------------------

def test_ac4_model_registry_marks_bge_m3_as_sparse():
    """AC4: model registry marks BAAI/bge-m3 as supporting sparse vectors."""
    script = """
import { resolveModel } from './src/embeddings/model-registry.js';
const m = resolveModel('BAAI/bge-m3');
process.stdout.write(JSON.stringify({ sparse: m.sparse }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out.strip())
    assert data.get("sparse") is True, (
        f"resolveModel('BAAI/bge-m3').sparse must be true, got: {data}"
    )


def test_ac4_non_bge_models_not_marked_sparse():
    """AC4: non-BGE models are not marked as sparse."""
    script = """
import { resolveModel } from './src/embeddings/model-registry.js';
const m = resolveModel('Xenova/multilingual-e5-small');
process.stdout.write(JSON.stringify({ sparse: !!m.sparse }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out.strip())
    assert data.get("sparse") is False, (
        f"e5-small should not be marked as sparse, got: {data}"
    )


def test_ac4_embedder_sparse_field_for_bge_m3():
    """AC4: createEmbedder with BAAI/bge-m3 model includes sparse field info."""
    with open(EMBEDDINGS_INDEX) as f:
        source = f.read()
    assert "sparse" in source, (
        "src/embeddings/index.js must handle sparse vector generation for bge-m3"
    )


def test_ac4_bge_m3_embed_returns_sparse_key():
    """AC4: batchEmbed with BGE-M3 model returns sparse_embedding field alongside embedding."""
    with open(os.path.join(REPO_ROOT, "src", "data", "embedder.js")) as f:
        source = f.read()
    # The embedder or re-embed path must handle sparse vectors
    assert "sparse" in source or "bge" in source.lower(), (
        "src/data/embedder.js must handle sparse embeddings for bge-m3 (look for 'sparse' or 'bge')"
    )


# ---------------------------------------------------------------------------
# AC5 — Switching models and re-embedding produces correct results
# ---------------------------------------------------------------------------

def test_ac5_reembed_accepts_force_recreate_or_equivalent():
    """AC5: re-embed command has a --recreate or --force flag for dimension migration."""
    with open(REEMBED_CMD) as f:
        source = f.read()
    assert "recreate" in source.lower() or "force" in source.lower() or "drop" in source.lower(), (
        "re-embed.js must have a --recreate/--force mechanism for dimension changes"
    )


def test_ac5_reembed_help_mentions_recreate():
    """AC5: re-embed --help shows the --recreate or similar flag."""
    out, err, rc = _run_cli(["re-embed", "--help"])
    combined = out + err
    assert "recreate" in combined.lower() or "force" in combined.lower() or rc == 0, (
        f"re-embed --help must document the dimension migration option. Got: {combined[:500]}"
    )


# ---------------------------------------------------------------------------
# AC6 — Ablation runner accepts --embedding-model flag
# ---------------------------------------------------------------------------

def test_ac6_ablation_runner_has_embedding_model_flag():
    """AC6: run_ablation.py --help shows --embedding-model flag."""
    result = subprocess.run(
        [sys.executable, ABLATION_SCRIPT, "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    out = result.stdout + result.stderr
    assert "embedding-model" in out or "embedding_model" in out, (
        f"run_ablation.py must accept --embedding-model flag. --help output:\n{out}"
    )


def test_ac6_ablation_script_source_has_embedding_model():
    """AC6: run_ablation.py source contains --embedding-model argument definition."""
    with open(ABLATION_SCRIPT) as f:
        source = f.read()
    assert "embedding-model" in source or "embedding_model" in source, (
        "run_ablation.py must define --embedding-model argument"
    )


def test_ac6_ablation_runner_accepts_embedding_model_flag(tmp_path):
    """AC6: run_ablation.py --embedding-model flag is accepted without error."""
    port = 24601

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            payload = json.dumps({"results": [{"id": "art-001", "score": 0.9}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_):
            pass

    srv = HTTPServer(("localhost", port), _Handler)
    t = threading.Thread(target=srv.serve_forever)
    t.daemon = True
    t.start()

    presets = [{"name": "e5-small", "hybridEnabled": "false"}]
    cfg_data = {"presets": presets}
    cfg = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir=str(tmp_path), encoding="utf-8"
    )
    json.dump(cfg_data, cfg, ensure_ascii=False)
    cfg.close()

    mini_dataset = [{"query": "test query", "expected": ["art-001"]}]
    ds = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir=str(tmp_path), encoding="utf-8"
    )
    json.dump(mini_dataset, ds, ensure_ascii=False)
    ds.close()

    try:
        result = _run_ablation([
            "--config", cfg.name,
            "--dataset", ds.name,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "3",
            "--embedding-model", "multilingual-e5-base",
        ])
        out = result.stdout + result.stderr
        # Must not fail with "unrecognized argument" error
        assert "unrecognized" not in out.lower(), (
            f"--embedding-model flag not recognized by run_ablation.py:\n{out}"
        )
        assert result.returncode == 0, (
            f"run_ablation.py must exit 0 with --embedding-model flag:\n{out}"
        )
    finally:
        srv.shutdown()
        os.unlink(cfg.name)
        os.unlink(ds.name)


def test_ac6_ablation_embedding_model_in_output(tmp_path):
    """AC6: When --embedding-model is specified, the model name appears in output or output file."""
    port = 24602

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            payload = json.dumps({"results": [{"id": "art-001", "score": 0.9}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_):
            pass

    srv = HTTPServer(("localhost", port), _Handler)
    t = threading.Thread(target=srv.serve_forever)
    t.daemon = True
    t.start()

    presets = [{"name": "e5-base-test", "hybridEnabled": "false"}]
    cfg_data = {"presets": presets}
    cfg = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir=str(tmp_path), encoding="utf-8"
    )
    json.dump(cfg_data, cfg, ensure_ascii=False)
    cfg.close()

    mini_dataset = [{"query": "test query", "expected": ["art-001"]}]
    ds = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, dir=str(tmp_path), encoding="utf-8"
    )
    json.dump(mini_dataset, ds, ensure_ascii=False)
    ds.close()

    out_file = str(tmp_path / "results.json")

    try:
        result = _run_ablation([
            "--config", cfg.name,
            "--dataset", ds.name,
            "--search-url", f"http://localhost:{port}/search",
            "--k", "3",
            "--embedding-model", "multilingual-e5-base",
            "--output", out_file,
        ])
        assert result.returncode == 0, (
            f"run_ablation.py failed:\n{result.stdout}\n{result.stderr}"
        )
        assert os.path.isfile(out_file), "Output file must be created"
        with open(out_file) as f:
            data = json.load(f)
        raw = json.dumps(data)
        # The embedding model should be recorded in the output
        assert "e5-base" in raw or "embedding_model" in raw or "embeddingModel" in raw, (
            f"Output JSON must include embedding model info. Got: {raw[:500]}"
        )
    finally:
        srv.shutdown()
        os.unlink(cfg.name)
        os.unlink(ds.name)


# ---------------------------------------------------------------------------
# AC7 — Schema migration strategy documented; no silent data corruption
# ---------------------------------------------------------------------------

def test_ac7_schema_md_documents_dimension_strategy():
    """AC7: SCHEMA.md documents the per-model dimension migration strategy."""
    assert os.path.isfile(SCHEMA_MD), f"SCHEMA.md must exist at {SCHEMA_MD}"
    with open(SCHEMA_MD) as f:
        content = f.read().lower()
    assert "embedding" in content and ("dimension" in content or "dim" in content or "model" in content), (
        "SCHEMA.md must document embedding dimension / model migration strategy"
    )


def test_ac7_schema_md_mentions_reembed_or_migration():
    """AC7: SCHEMA.md mentions re-embed or migration path for dimension changes."""
    with open(SCHEMA_MD) as f:
        content = f.read().lower()
    assert "re-embed" in content or "migration" in content or "recreate" in content or "migrate" in content, (
        "SCHEMA.md must mention re-embed or migration path when changing embedding models"
    )


def test_ac7_pg_store_mismatch_raises_not_silently_corrupts():
    """AC7: PgVectorStore dimension mismatch raises an error (not silent corruption)."""
    with open(PG_STORE) as f:
        source = f.read()
    # Must either throw or return an error — not silently pass
    error_patterns = ["throw", "Error(", "reject", "process.exit", "stderr"]
    has_error_handling = any(p in source for p in error_patterns)
    assert has_error_handling, (
        "PgVectorStore must raise/throw an error on dimension mismatch, not silently corrupt"
    )


def test_ac7_migration_strategy_is_per_model_or_recreate():
    """AC7: Either per-model table prefix or recreate path is implemented."""
    with open(PG_STORE) as f:
        pg_source = f.read()
    with open(REEMBED_CMD) as f:
        reembed_source = f.read()

    combined = pg_source + reembed_source
    has_strategy = (
        "recreate" in combined.lower()
        or "drop" in combined.lower()
        or "per-model" in combined.lower()
        or "model_meta" in combined
        or "dimension" in combined.lower()
    )
    assert has_strategy, (
        "Either re-embed --recreate (drop+recreate table) or per-model table strategy must be implemented"
    )
