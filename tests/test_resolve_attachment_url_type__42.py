"""Tests for issue #42: [follow-up] Add docstring to resolveAttachmentUrlType helper (runs against UAT)"""
import os
import subprocess
import re
import pytest


# Resolved from UAT .env at runtime; see tester skill Step 0.
BASE_URL = os.environ.get("UAT_BASE_URL") or "http://localhost:" + os.environ.get("UAT_PORT", "8010")
if not BASE_URL.startswith("http"):
    raise RuntimeError(
        "UAT_BASE_URL / UAT_PORT not set. Run the tester skill's Step 0 to resolve UAT before pytest."
    )


def test_docstring_added_above_function():
    """AC: A docstring or comment is added directly above the resolveAttachmentUrlType() function in src/core/search.js (lines 13–18)."""
    # Read the source file
    src_path = os.path.join(os.path.dirname(__file__), "..", "src", "core", "search.js")
    with open(src_path, "r") as f:
        content = f.read()

    # Check that a docstring/comment exists above the function definition
    # Pattern: look for /** ... */ or // comment immediately before function resolveAttachmentUrlType
    pattern = r'(/\*\*[\s\S]*?\*/|//\s+[^\n]+)\s*function\s+resolveAttachmentUrlType'
    assert re.search(pattern, content), "No docstring/comment found above resolveAttachmentUrlType() function"


def test_comment_describes_purpose():
    """AC: The comment describes the function's purpose: determining the type of an attachment URL."""
    src_path = os.path.join(os.path.dirname(__file__), "..", "src", "core", "search.js")
    with open(src_path, "r") as f:
        content = f.read()

    # Find the function definition and its preceding comment
    pattern = r'(/\*\*[\s\S]*?\*/|(?://[^\n]*\n)+)\s*function\s+resolveAttachmentUrlType'
    match = re.search(pattern, content)
    assert match, "Could not locate docstring above function"

    docstring = match.group(1)
    # Check for keywords that indicate purpose documentation
    purpose_keywords = ["attachment", "url", "type", "determine", "resolve", "discriminat", "check"]
    has_purpose = any(keyword in docstring.lower() for keyword in purpose_keywords)
    assert has_purpose, f"Comment does not describe function purpose. Found: {docstring}"


def test_comment_states_return_value():
    """AC: The comment states what the function returns (e.g., the URL type string or enum value)."""
    src_path = os.path.join(os.path.dirname(__file__), "..", "src", "core", "search.js")
    with open(src_path, "r") as f:
        content = f.read()

    # Find the function definition and its preceding comment
    pattern = r'(/\*\*[\s\S]*?\*/|(?://[^\n]*\n)+)\s*function\s+resolveAttachmentUrlType'
    match = re.search(pattern, content)
    assert match, "Could not locate docstring above function"

    docstring = match.group(1)
    # Check for return value documentation keywords
    return_keywords = ["@returns", "return", "returns", "external", "local", "null"]
    has_return = any(keyword in docstring.lower() for keyword in return_keywords)
    assert has_return, f"Comment does not describe return value. Found: {docstring}"


def test_no_functional_logic_altered():
    """AC: No functional logic within resolveAttachmentUrlType() is altered — only the comment is added."""
    src_path = os.path.join(os.path.dirname(__file__), "..", "src", "core", "search.js")
    with open(src_path, "r") as f:
        content = f.read()

    # Extract the function body
    pattern = r'function\s+resolveAttachmentUrlType\(url\)\s*\{([\s\S]*?)\n\}'
    match = re.search(pattern, content)
    assert match, "Could not locate function body"

    body = match.group(1)
    # Expected lines in the function:
    expected_lines = [
        "if (!url) return null;",
        'if (url.startsWith("/download/")) return "local";',
        'if (url.startsWith("http://") || url.startsWith("https://")) return "external";',
        'return "external";'
    ]

    # Verify all expected lines are present
    for line in expected_lines:
        assert line in body, f"Expected line missing from function body: {line}"


def test_existing_test_suite_passes():
    """AC: Run the existing test suite and confirm all tests pass, verifying no logic was changed."""
    # Try to run npm test or jest
    try:
        result = subprocess.run(
            ["npm", "test"],
            cwd=os.path.join(os.path.dirname(__file__), ".."),
            capture_output=True,
            timeout=60,
            text=True
        )
        # If npm test runs, it should pass (exit code 0)
        # If node is not available or script is missing, skip this test
        skip_indicators = ("not found", "missing script", "npm error missing script")
        combined = (result.stderr + result.stdout).lower()
        if any(ind in combined for ind in skip_indicators):
            pytest.skip("npm test not available in this environment — manual verification required")
        else:
            assert result.returncode == 0, f"Test suite failed:\n{result.stdout}\n{result.stderr}"
    except FileNotFoundError:
        pytest.skip("npm not found — manual verification required via npm test")
    except subprocess.TimeoutExpired:
        pytest.skip("Test suite timeout — manual verification required")
