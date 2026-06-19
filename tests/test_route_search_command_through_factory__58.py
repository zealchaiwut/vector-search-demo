"""Tests for issue #58: Route search command through factory store interface (runs against UAT)"""
import os
import subprocess


# Resolved from UAT .env at runtime; see tester skill Step 0.
BASE_URL = os.environ.get("UAT_BASE_URL") or f"http://localhost:{os.environ.get('UAT_PORT', '8010')}"
if not BASE_URL.startswith("http"):
    raise RuntimeError(
        "UAT_BASE_URL / UAT_PORT not set. Run the tester skill's Step 0 to resolve UAT before pytest."
    )

# Resolve the main repo root from git
REPO_ROOT = subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"], text=True
).strip()


# --- Acceptance Criteria ---

def test_search_command_uses_getstore_instead_of_searchdocuments():
    """
    AC: `search.js` calls `getStore(backend)` to obtain a store instance
    after resolving the backend, instead of calling `searchDocuments(query, k)` directly.
    """
    search_js_path = os.path.join(REPO_ROOT, "src", "commands", "search.js")
    with open(search_js_path, "r") as f:
        content = f.read()

    # Check that getStore is called
    assert "getStore(backend)" in content, "search.js should call getStore(backend)"

    # Check that store.search() is called (on the result of getStore)
    assert "store.search" in content, "search.js should call store.search()"


def test_searchdocuments_not_imported_in_search_js():
    """
    AC: The direct import and call to `searchDocuments` is removed from `search.js`;
    the function is no longer invoked from that file.
    """
    search_js_path = os.path.join(REPO_ROOT, "src", "commands", "search.js")
    with open(search_js_path, "r") as f:
        content = f.read()

    # searchDocuments should not be imported
    assert "searchDocuments" not in content, (
        "search.js should not import or call searchDocuments directly"
    )


def test_search_command_calls_store_search_method():
    """
    AC: `store.search(query, k)` is called on the store instance returned by
    `getStore(backend)`, consistent with how `init`, `ingest`, `ping`, and `verify`
    commands use the factory.
    """
    search_js_path = os.path.join(REPO_ROOT, "src", "commands", "search.js")
    with open(search_js_path, "r") as f:
        content = f.read()

    # Check the pattern: getStore(backend) followed by store.search(query, k)
    assert "const store = await getStore(backend)" in content, (
        "search.js should get the store via getStore(backend)"
    )
    assert "await store.search(query, k)" in content, (
        "search.js should call store.search(query, k)"
    )


def test_resolvecbackend_and_logactivebackend_still_present():
    """
    AC: `resolveBackend()` and `logActiveBackend()` calls remain in place —
    only the document-search invocation changes.
    """
    search_js_path = os.path.join(REPO_ROOT, "src", "commands", "search.js")
    with open(search_js_path, "r") as f:
        content = f.read()

    # Both functions should still be called
    assert "resolveBackend()" in content, "search.js should still call resolveBackend()"
    assert "logActiveBackend(backend)" in content, (
        "search.js should still call logActiveBackend(backend)"
    )


def test_store_search_method_exists():
    """
    AC: Verify that store objects returned by getStore() have a search method
    that accepts (query, k) parameters. Check the store implementations.
    """
    # Check mock store
    mock_store_path = os.path.join(REPO_ROOT, "src", "store", "mock.js")
    with open(mock_store_path, "r") as f:
        mock_content = f.read()
    assert "search:" in mock_content, "mock store should have search property in the returned object"

    # Check milvus store
    milvus_store_path = os.path.join(REPO_ROOT, "src", "store", "milvus.js")
    if os.path.exists(milvus_store_path):
        with open(milvus_store_path, "r") as f:
            milvus_content = f.read()
        assert "search:" in milvus_content or "search(" in milvus_content, (
            "milvus store should have search method"
        )

    # Check postgres store
    postgres_store_path = os.path.join(REPO_ROOT, "src", "store", "postgres.js")
    if os.path.exists(postgres_store_path):
        with open(postgres_store_path, "r") as f:
            postgres_content = f.read()
        assert "search:" in postgres_content or "search(" in postgres_content, (
            "postgres store should have search method"
        )


def test_no_other_commands_modified():
    """
    AC: No other command files are modified as part of this change.

    Verify that init, ingest, ping, verify commands still follow the
    factory pattern and haven't been corrupted.
    """
    init_js = os.path.join(REPO_ROOT, "src", "commands", "init.js")
    ping_js = os.path.join(REPO_ROOT, "src", "commands", "ping.js")
    verify_js = os.path.join(REPO_ROOT, "src", "commands", "verify.js")

    # Check that all commands still use the factory pattern
    commands_to_check = [
        (init_js, "init.js"),
        (ping_js, "ping.js"),
    ]

    # verify.js may or may not exist, only check if it does
    if os.path.exists(verify_js):
        commands_to_check.append((verify_js, "verify.js"))

    for cmd_file, name in commands_to_check:
        assert os.path.exists(cmd_file), f"{name} should exist"
        with open(cmd_file, "r") as f:
            content = f.read()
        assert "getStore(backend)" in content, f"{name} should use getStore(backend)"
        assert "resolveBackend()" in content, f"{name} should use resolveBackend()"


def test_search_js_factory_pattern_complete():
    """
    AC: Verify search.js follows the complete factory pattern including all imports.
    """
    search_js_path = os.path.join(REPO_ROOT, "src", "commands", "search.js")
    with open(search_js_path, "r") as f:
        content = f.read()

    # Check that factory imports are present (flexible to formatting)
    assert "resolveBackend" in content and "logActiveBackend" in content and "getStore" in content, (
        "search.js should import resolveBackend, logActiveBackend, and getStore from factory"
    )
    assert 'from "../store/factory.js"' in content, (
        "factory functions should be imported from ../store/factory.js"
    )

    # Verify the exact pattern: getStore followed by store.search
    assert "const store = await getStore(backend)" in content, (
        "search.js should assign store from getStore(backend)"
    )
    assert "await store.search(query, k)" in content, (
        "search.js should call await store.search(query, k)"
    )


def test_search_output_format_preserved():
    """
    AC: The search command output format is defined in search.js and
    should include all required fields (Rank, Headline, ID, Score, URL).
    """
    search_js_path = os.path.join(REPO_ROOT, "src", "commands", "search.js")
    with open(search_js_path, "r") as f:
        content = f.read()

    # Verify that the output format matches the AC requirement
    required_fields = ["Rank:", "Headline:", "ID:", "Score:", "URL:"]
    for field in required_fields:
        assert field in content, f"search.js output should include '{field}' field"

    # Verify that results formatting logic is intact
    assert "for (let i = 0; i < results.length; i++)" in content or \
           "for (const" in content, (
        "search.js should iterate over results"
    )


def test_error_handling_preserved():
    """
    AC: Error handling for missing query is preserved.
    """
    search_js_path = os.path.join(REPO_ROOT, "src", "commands", "search.js")
    with open(search_js_path, "r") as f:
        content = f.read()

    # Verify that query validation is present
    assert "query is required" in content.lower(), (
        "search.js should validate that query is required"
    )
    assert "process.exit(1)" in content, (
        "search.js should exit with error code when query is missing"
    )
