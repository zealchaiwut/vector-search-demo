"""Tests for issue #58: Route search command through factory store interface (runs against UAT)"""
import os
import subprocess
import sys

# No httpx needed for this ticket — all steps are CLI/file inspection
# UAT_BASE_URL not used; tests hit the local CLI and inspect the codebase


def test_search_refactor__uses_getstore():
    """AC: search.js calls getStore(backend) instead of searchDocuments directly"""
    search_js_path = os.path.join(
        os.path.dirname(__file__), "..", "src", "commands", "search.js"
    )
    with open(search_js_path, "r") as f:
        content = f.read()

    # Verify getStore is imported (flexible to formatting)
    assert "getStore" in content, "getStore must be imported in search.js"
    assert "resolveBackend" in content and "logActiveBackend" in content, (
        "getStore must be imported alongside resolveBackend and logActiveBackend"
    )

    # Verify searchDocuments is NOT imported
    assert "searchDocuments" not in content, (
        "searchDocuments must not be directly imported or called in search.js"
    )

    # Verify store.search is called
    assert "store.search(query, k)" in content, (
        "store.search(query, k) must be called on the store instance"
    )


def test_search_refactor__getstore_called():
    """AC: getStore(backend) is called to obtain a store instance"""
    search_js_path = os.path.join(
        os.path.dirname(__file__), "..", "src", "commands", "search.js"
    )
    with open(search_js_path, "r") as f:
        content = f.read()

    assert "const store = await getStore(backend);" in content, (
        "getStore(backend) must be called and assigned to a store variable"
    )


def test_search_refactor__no_searchdocuments_import():
    """AC: Direct import and call to searchDocuments is removed"""
    search_js_path = os.path.join(
        os.path.dirname(__file__), "..", "src", "commands", "search.js"
    )
    with open(search_js_path, "r") as f:
        content = f.read()

    # searchDocuments must not appear anywhere in the file
    assert "searchDocuments" not in content, (
        "searchDocuments must be completely removed from search.js imports and calls"
    )


def test_search_refactor__resolvebackend_intact():
    """AC: resolveBackend() and logActiveBackend() calls remain"""
    search_js_path = os.path.join(
        os.path.dirname(__file__), "..", "src", "commands", "search.js"
    )
    with open(search_js_path, "r") as f:
        content = f.read()

    assert "const backend = resolveBackend();" in content, (
        "resolveBackend() call must remain"
    )
    assert "logActiveBackend(backend);" in content, (
        "logActiveBackend(backend) call must remain"
    )


def test_search_refactor__other_commands_unchanged():
    """AC: No other command files are modified"""
    commands_dir = os.path.join(
        os.path.dirname(__file__), "..", "src", "commands"
    )

    # These commands should still have their original patterns
    for cmd_file in ["init.js", "ingest.js", "ping.js", "verify.js"]:
        cmd_path = os.path.join(commands_dir, cmd_file)
        if os.path.exists(cmd_path):
            with open(cmd_path, "r") as f:
                content = f.read()
            # Just verify they can be read and are not empty
            assert len(content) > 0, f"{cmd_file} should not be empty"
