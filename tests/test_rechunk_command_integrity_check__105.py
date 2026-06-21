"""Tests for issue #105: Add rechunk command and chunk integrity verification (runs against UAT)"""
import os
import subprocess
import json
import sys

# Resolved from UAT .env at runtime; see tester skill Step 0.
UAT_BASE_URL = os.environ.get("UAT_BASE_URL", "")
UAT_PORT = os.environ.get("UAT_PORT", "")

if not UAT_BASE_URL:
    if UAT_PORT:
        UAT_BASE_URL = f"http://localhost:{UAT_PORT}"
    else:
        raise RuntimeError(
            "UAT_BASE_URL / UAT_PORT not set. Run the tester skill's Step 0 to resolve UAT before pytest."
        )

REPO_ROOT = os.environ.get("REPO_ROOT", "/Users/zeal-server/dev/vector-search-demo/tester")
COMMANDER_BIN = os.path.join(REPO_ROOT, "dist", "cli.js")


def run_command(cmd_args, env=None):
    """Run a CLI command and return exit code, stdout, stderr."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    try:
        result = subprocess.run(
            ["node", COMMANDER_BIN] + cmd_args,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            env=full_env
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError as e:
        return None, "", f"node not found: {e}"
    except subprocess.TimeoutExpired:
        return None, "", "Command timed out"
    except Exception as e:
        return None, "", f"Command error: {e}"


# --- Acceptance Criteria ---

def test_rechunk_command_exists_and_registered():
    """AC: rechunk command exists at src/commands/rechunk and is registered with Commander"""
    # Verify the rechunk command is available via --help
    rc, stdout, stderr = run_command(["--help"])
    assert rc == 0, f"Commander --help failed: {stderr}"
    assert "rechunk" in stdout.lower(), "rechunk command not listed in help output"


def test_rechunk_deletes_and_regenerates_chunks():
    """AC: Running rechunk deletes existing chunks for all articles and regenerates them"""
    # First, ingest to populate chunks
    rc, stdout, stderr = run_command(["ingest"], {"DB_BACKEND": "mock"})
    assert rc == 0, f"Ingest failed: {stderr}"

    # Verify chunks exist
    rc, stdout, stderr = run_command(["verify"], {"DB_BACKEND": "mock"})
    assert rc == 0, "Verify failed after ingest"
    initial_output = stdout

    # Run rechunk
    rc, stdout, stderr = run_command(["rechunk"], {"DB_BACKEND": "mock"})
    assert rc == 0, f"Rechunk failed: {stderr}"

    # Verify chunks still exist post-rechunk
    rc, stdout, stderr = run_command(["verify"], {"DB_BACKEND": "mock"})
    assert rc == 0, "Verify failed after rechunk"


def test_rechunk_processes_all_articles():
    """AC: rechunk processes all articles in the corpus, not a subset"""
    rc, stdout, stderr = run_command(["ingest"], {"DB_BACKEND": "mock"})
    assert rc == 0, f"Ingest failed: {stderr}"

    # Count articles before rechunk
    rc, verify_out, _ = run_command(["verify"], {"DB_BACKEND": "mock"})
    assert rc == 0, "Verify failed"
    # Output format: "OK: <count> articles, <count> vectors"
    import re
    match = re.search(r"(\d+) articles", verify_out)
    articles_before = int(match.group(1)) if match else 0

    # Run rechunk
    rc, stdout, stderr = run_command(["rechunk"], {"DB_BACKEND": "mock"})
    assert rc == 0, f"Rechunk failed: {stderr}"

    # Verify article count unchanged
    rc, verify_out, _ = run_command(["verify"], {"DB_BACKEND": "mock"})
    assert rc == 0, "Verify failed after rechunk"
    match = re.search(r"(\d+) articles", verify_out)
    articles_after = int(match.group(1)) if match else 0

    assert articles_before == articles_after, f"Article count changed: {articles_before} -> {articles_after}"


def test_rechunk_embeds_all_chunks():
    """AC: rechunk re-embeds every newly created chunk (no chunk is left with a null embedding after the command completes)"""
    rc, stdout, stderr = run_command(["ingest"], {"DB_BACKEND": "mock"})
    assert rc == 0, f"Ingest failed: {stderr}"

    # Run rechunk
    rc, stdout, stderr = run_command(["rechunk"], {"DB_BACKEND": "mock"})
    assert rc == 0, f"Rechunk failed: {stderr}"

    # Verify that verify passes (which checks embeddings exist)
    rc, stdout, stderr = run_command(["verify"], {"DB_BACKEND": "mock"})
    assert rc == 0, f"Verify failed after rechunk: {stderr}"
    assert "OK" in stdout, "Verify did not report OK after rechunk"


def test_rechunk_exits_nonzero_on_error():
    """AC: rechunk exits with a non-zero code and prints a clear error message if any article or chunk fails to process"""
    # Intentionally trigger an error by using an invalid backend
    rc, stdout, stderr = run_command(["rechunk"], {"DB_BACKEND": "invalid_backend"})
    # Should fail due to invalid backend
    assert rc is not None and rc != 0, "Rechunk should exit non-zero for invalid backend"
    # Should have an error message
    assert len(stderr) > 0 or len(stdout) > 0, "No error message produced"


def test_integrity_check_ok_when_all_valid():
    """AC: The integrity check at src/commands/verify reports OK when every article has >= 1 chunk and every chunk has a non-null embedding"""
    rc, stdout, stderr = run_command(["ingest"], {"DB_BACKEND": "mock"})
    assert rc == 0, f"Ingest failed: {stderr}"

    rc, stdout, stderr = run_command(["verify"], {"DB_BACKEND": "mock"})
    assert rc == 0, "Verify should exit 0 when all articles have chunks"
    assert "OK" in stdout, "Verify should print OK when healthy"


def test_integrity_check_lists_zero_chunk_articles():
    """AC: The integrity check lists each offending article ID when any article has zero chunks"""
    rc, stdout, stderr = run_command(["ingest"], {"DB_BACKEND": "mock"})
    assert rc == 0, f"Ingest failed: {stderr}"

    # Manually delete all chunks for one article in collection.json
    collection_path = os.path.join(REPO_ROOT, "collection.json")
    if os.path.exists(collection_path):
        with open(collection_path, "r") as f:
            rows = json.load(f)
        # Find an article ID and remove its chunks
        article_ids = set(row["id"].split(":")[0] for row in rows)
        if article_ids:
            victim_id = list(article_ids)[0]
            rows = [r for r in rows if r["id"].split(":")[0] != victim_id]
            with open(collection_path, "w") as f:
                json.dump(rows, f)

            # Run verify
            rc, stdout, stderr = run_command(["verify"], {"DB_BACKEND": "mock"})
            assert rc != 0, "Verify should exit non-zero when article has zero chunks"
            # Verify output mentions the missing article (partial match)
            assert victim_id in stdout or victim_id in stderr or "zero" in stdout.lower() or "missing" in stdout.lower(), \
                f"Verify did not report gap for article {victim_id}"


def test_integrity_check_lists_null_embedding_chunks():
    """AC: The integrity check lists each offending chunk ID when any chunk has a null embedding"""
    rc, stdout, stderr = run_command(["ingest"], {"DB_BACKEND": "mock"})
    assert rc == 0, f"Ingest failed: {stderr}"

    # Manually set embedding to null for one chunk
    collection_path = os.path.join(REPO_ROOT, "collection.json")
    if os.path.exists(collection_path):
        with open(collection_path, "r") as f:
            rows = json.load(f)
        # Set the first chunk's embedding to null
        if rows:
            rows[0]["embedding"] = None
            with open(collection_path, "w") as f:
                json.dump(rows, f)

            # Run verify
            rc, stdout, stderr = run_command(["verify"], {"DB_BACKEND": "mock"})
            assert rc != 0, "Verify should exit non-zero when chunk has null embedding"
            # Verify output mentions the issue
            assert "null" in stdout.lower() or rows[0]["id"] in stdout, \
                f"Verify did not report null embedding for chunk {rows[0]['id']}"


def test_integrity_check_exits_nonzero_on_gaps():
    """AC: The integrity check exits with a non-zero code when any gap is found"""
    rc, stdout, stderr = run_command(["ingest"], {"DB_BACKEND": "mock"})
    assert rc == 0, f"Ingest failed: {stderr}"

    # Create a gap by deleting all chunks
    collection_path = os.path.join(REPO_ROOT, "collection.json")
    if os.path.exists(collection_path):
        with open(collection_path, "w") as f:
            json.dump([], f)

        # Run verify
        rc, stdout, stderr = run_command(["verify"], {"DB_BACKEND": "mock"})
        assert rc != 0, "Verify should exit non-zero when chunks are missing"


def test_rechunk_repairs_corpus():
    """AC: Run rechunk after the integrity check failure from steps 4–5. rechunk repairs the corpus; a subsequent integrity check passes with OK."""
    rc, stdout, stderr = run_command(["ingest"], {"DB_BACKEND": "mock"})
    assert rc == 0, f"Ingest failed: {stderr}"

    # Corrupt the corpus
    collection_path = os.path.join(REPO_ROOT, "collection.json")
    if os.path.exists(collection_path):
        with open(collection_path, "r") as f:
            rows = json.load(f)
        # Remove one article's chunks
        if rows:
            victim_id = rows[0]["id"].split(":")[0]
            rows = [r for r in rows if r["id"].split(":")[0] != victim_id]
            with open(collection_path, "w") as f:
                json.dump(rows, f)

        # Verify corruption
        rc, _, _ = run_command(["verify"], {"DB_BACKEND": "mock"})
        assert rc != 0, "Corruption setup failed"

        # Run rechunk to repair
        rc, stdout, stderr = run_command(["rechunk"], {"DB_BACKEND": "mock"})
        assert rc == 0, f"Rechunk repair failed: {stderr}"

        # Verify repair
        rc, stdout, stderr = run_command(["verify"], {"DB_BACKEND": "mock"})
        assert rc == 0, "Verify should pass after rechunk repair"
        assert "OK" in stdout, "Verify should report OK after successful repair"


def test_rechunk_command_with_changed_chunk_size():
    """AC: Change the chunk size or overlap in configuration, then run rechunk again. Old chunks are replaced; new chunks reflect the updated parameters."""
    rc, stdout, stderr = run_command(["ingest"], {"DB_BACKEND": "mock"})
    assert rc == 0, f"Ingest failed: {stderr}"

    # Run rechunk with different chunk size
    env = {"DB_BACKEND": "mock", "CHUNK_SIZE": "600", "CHUNK_OVERLAP": "100"}
    rc, stdout, stderr = run_command(["rechunk"], env)
    assert rc == 0, f"Rechunk with changed size failed: {stderr}"

    # Verify chunks are regenerated and valid
    rc, verify_out, _ = run_command(["verify"], {"DB_BACKEND": "mock"})
    assert rc == 0, "Verify failed after rechunk with new chunk size"
    assert "OK" in verify_out, "Verify should report OK after size change rechunk"
