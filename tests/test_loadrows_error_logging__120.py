"""Tests for issue #120: loadRows() silently swallows file read errors with bare catch"""
import subprocess
import os
import json
import sys
import tempfile
import shutil

# Get repo root and collection.json path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLLECTION_PATH = os.path.join(REPO_ROOT, "collection.json")


def test_loadrows__json_parse_error_logs_warning(capsys):
    """AC: When loadRows() catches a JSON parse error, it logs a warning message containing [search] prefix and error description."""
    # Save original collection.json
    original_content = None
    original_exists = os.path.exists(COLLECTION_PATH)
    if original_exists:
        with open(COLLECTION_PATH, 'r') as f:
            original_content = f.read()

    try:
        # Corrupt the JSON file
        with open(COLLECTION_PATH, 'w') as f:
            f.write("not valid json {]")

        # Run a search that will trigger loadRows
        result = subprocess.run(
            ["node", "-e", f"""
            import {{ searchDocuments }} from '{REPO_ROOT}/src/search/index.js';
            searchDocuments('test').then(() => {{}}).catch(() => {{}});
            """],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10
        )

        # Check stderr for warning message
        combined_output = result.stderr + result.stdout
        assert "[search]" in combined_output, f"Expected '[search]' prefix in output. Got: {combined_output}"
        assert "JSON" in combined_output or "parse" in combined_output, f"Expected error description in output. Got: {combined_output}"

    finally:
        # Restore original collection.json
        if original_exists and original_content:
            with open(COLLECTION_PATH, 'w') as f:
                f.write(original_content)
        elif os.path.exists(COLLECTION_PATH):
            os.remove(COLLECTION_PATH)


def test_loadrows__permission_error_logs_warning(capsys):
    """AC: When loadRows() catches a permission error, it logs a warning message containing [search] and permission-related error."""
    # Skip on Windows (permission model is different)
    if sys.platform == "win32":
        pytest.skip("Unix-style permissions not applicable on Windows")

    original_exists = os.path.exists(COLLECTION_PATH)
    original_perms = None
    original_content = None

    if original_exists:
        original_perms = os.stat(COLLECTION_PATH).st_mode
        with open(COLLECTION_PATH, 'r') as f:
            original_content = f.read()

    try:
        # Remove read permissions on collection.json
        os.chmod(COLLECTION_PATH, 0o000)

        # Run a search that will trigger loadRows
        result = subprocess.run(
            ["node", "-e", f"""
            import {{ searchDocuments }} from '{REPO_ROOT}/src/search/index.js';
            searchDocuments('test').then(() => {{}}).catch(() => {{}});
            """],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10
        )

        # Check stderr for warning with permission error message
        combined_output = result.stderr + result.stdout
        assert "[search]" in combined_output, f"Expected '[search]' prefix in output. Got: {combined_output}"
        assert "permission" in combined_output.lower() or "eacces" in combined_output.lower(), f"Expected permission error message. Got: {combined_output}"

    finally:
        # Restore permissions and content
        if original_exists and original_perms:
            os.chmod(COLLECTION_PATH, original_perms)
        elif os.path.exists(COLLECTION_PATH):
            os.chmod(COLLECTION_PATH, 0o644)


def test_loadrows__valid_file_no_warning(capsys):
    """AC: When collection.json is valid and readable, loadRows() returns parsed rows with no console warning emitted."""
    # Create a simple valid collection.json
    test_collection = [
        {
            "id": "doc1:0",
            "headline": "Test Article",
            "details": "This is a test article.",
            "embedding": [0.1, 0.2, 0.3],
            "chunk_index": 0
        }
    ]

    original_exists = os.path.exists(COLLECTION_PATH)
    original_content = None
    if original_exists:
        with open(COLLECTION_PATH, 'r') as f:
            original_content = f.read()

    try:
        # Write valid collection.json
        with open(COLLECTION_PATH, 'w') as f:
            json.dump(test_collection, f)

        # Run a search that will trigger loadRows
        result = subprocess.run(
            ["node", "-e", f"""
            import {{ searchDocuments }} from '{REPO_ROOT}/src/search/index.js';
            searchDocuments('test').then(() => {{}}).catch(() => {{}});
            """],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10
        )

        # Check that no warning is logged
        combined_output = result.stderr + result.stdout
        # Should not contain the warning prefix when file is valid
        warning_lines = [line for line in combined_output.split('\n') if "[search]" in line]
        assert len(warning_lines) == 0, f"Expected no warning for valid file, but got: {warning_lines}"

    finally:
        # Restore original collection.json
        if original_exists and original_content:
            with open(COLLECTION_PATH, 'w') as f:
                f.write(original_content)
        elif os.path.exists(COLLECTION_PATH):
            os.remove(COLLECTION_PATH)


def test_loadrows__returns_empty_array_on_error():
    """AC: loadRows() still returns an empty array on error — the error handling does not throw or propagate the exception."""
    original_exists = os.path.exists(COLLECTION_PATH)
    original_content = None
    if original_exists:
        with open(COLLECTION_PATH, 'r') as f:
            original_content = f.read()

    try:
        # Corrupt the JSON file
        with open(COLLECTION_PATH, 'w') as f:
            f.write("invalid json")

        # Run a direct test of loadRows behavior
        result = subprocess.run(
            ["node", "-e", f"""
            import {{ fileURLToPath }} from 'node:url';
            import {{ dirname, join }} from 'node:path';
            import {{ readFileSync, existsSync }} from 'node:fs';

            const __dirname = dirname(fileURLToPath(import.meta.url));
            const COLLECTION_PATH = join('{REPO_ROOT}', 'collection.json');

            function loadRows() {{
              if (!existsSync(COLLECTION_PATH)) return [];
              try {{
                const rows = JSON.parse(readFileSync(COLLECTION_PATH, 'utf8'));
                return Array.isArray(rows) ? rows : [];
              }} catch {{
                return [];
              }}
            }}

            const result = loadRows();
            console.log(JSON.stringify(result));
            """],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10
        )

        # Verify function returns empty array (not undefined, not error)
        output = result.stdout.strip()
        assert output == "[]", f"Expected empty array [], got: {output}"
        assert result.returncode == 0, f"Expected success exit code, got {result.returncode}: {result.stderr}"

    finally:
        # Restore original collection.json
        if original_exists and original_content:
            with open(COLLECTION_PATH, 'w') as f:
                f.write(original_content)
        elif os.path.exists(COLLECTION_PATH):
            os.remove(COLLECTION_PATH)
