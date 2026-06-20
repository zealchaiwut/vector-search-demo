"""
Acceptance tests for issue #42: Add docstring to resolveAttachmentUrlType helper.

AC1 - A docstring or comment is added directly above the resolveAttachmentUrlType()
      function in src/core/search.js.
AC2 - The comment describes the function's purpose: determining the type of an
      attachment URL.
AC3 - The comment states what the function returns (URL type string or enum value).
AC4 - No functional logic within resolveAttachmentUrlType() is altered.
"""

import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEARCH_JS = os.path.join(REPO_ROOT, "src", "core", "search.js")


def _src():
    with open(SEARCH_JS) as f:
        return f.read()


def _jsdoc_above_function(src):
    """
    Return the JSDoc comment block that is placed immediately before
    'function resolveAttachmentUrlType' (no intervening non-whitespace lines).
    Uses a line-by-line scan so we never accidentally capture content from
    earlier in the file.
    """
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if re.match(r'\s*function resolveAttachmentUrlType\b', line):
            # Walk backwards collecting the JSDoc block
            block_lines = []
            j = i - 1
            while j >= 0 and lines[j].strip() == '':
                j -= 1
            # Collect up to the opening /** of the JSDoc block
            if j >= 0 and lines[j].strip().endswith('*/'):
                end = j
                while j >= 0 and '/**' not in lines[j]:
                    j -= 1
                if j >= 0 and '/**' in lines[j]:
                    block_lines = lines[j:end + 1]
            return '\n'.join(block_lines)
    return ''


# ---------------------------------------------------------------------------
# AC1 — JSDoc block present immediately above the function
# ---------------------------------------------------------------------------

def test_ac1_jsdoc_exists_above_function():
    """A JSDoc block (/** ... */) must appear directly before resolveAttachmentUrlType."""
    src = _src()
    doc = _jsdoc_above_function(src)
    assert doc.strip().startswith('/**'), (
        "src/core/search.js must have a JSDoc block comment (/**...*/) immediately "
        "above the resolveAttachmentUrlType() function definition. "
        f"Found instead: {doc!r}"
    )


# ---------------------------------------------------------------------------
# AC2 — JSDoc describes the function's purpose
# ---------------------------------------------------------------------------

def test_ac2_jsdoc_describes_purpose():
    """The JSDoc must mention the attachment URL type-determination purpose."""
    src = _src()
    doc = _jsdoc_above_function(src).lower()
    assert doc, (
        "No JSDoc comment block found directly above resolveAttachmentUrlType()"
    )
    has_purpose = (
        "attachment" in doc
        and ("url" in doc or "type" in doc or "determin" in doc or "resolv" in doc)
    )
    assert has_purpose, (
        "The JSDoc directly above resolveAttachmentUrlType() must describe the "
        "function's purpose — it must mention 'attachment' and one of 'url', 'type', "
        "'determine', or 'resolve'. "
        f"Current doc: {doc!r}"
    )


# ---------------------------------------------------------------------------
# AC3 — JSDoc states what the function returns
# ---------------------------------------------------------------------------

def test_ac3_jsdoc_states_return_value():
    """The JSDoc must document what the function returns."""
    src = _src()
    doc = _jsdoc_above_function(src)
    assert doc, (
        "No JSDoc comment block found directly above resolveAttachmentUrlType()"
    )
    has_returns_tag = bool(re.search(r'@returns?', doc))
    has_return_values = bool(
        re.search(r'"external"|"local"|\'external\'|\'local\'', doc)
    )
    assert has_returns_tag or has_return_values, (
        "The JSDoc above resolveAttachmentUrlType() must state what the function "
        "returns — use @returns or mention the return values ('external', 'local', null). "
        f"Current doc: {doc!r}"
    )


# ---------------------------------------------------------------------------
# AC4 — no functional logic altered
# ---------------------------------------------------------------------------

def test_ac4_local_url_returns_local():
    """resolveAttachmentUrlType must still classify /download/ paths as 'local'."""
    src = _src()
    assert re.search(
        r'startsWith\(["\']\/download\/["\']\).*return\s+["\']local["\']', src, re.DOTALL
    ) or re.search(r'\/download\/.*local', src, re.DOTALL), (
        "resolveAttachmentUrlType must still return 'local' for /download/ paths"
    )


def test_ac4_http_url_returns_external():
    """resolveAttachmentUrlType must still classify http(s) URLs as 'external'."""
    src = _src()
    assert re.search(r'https?.*external|external.*https?', src, re.DOTALL), (
        "resolveAttachmentUrlType must still return 'external' for http(s) URLs"
    )


def test_ac4_null_url_returns_null():
    """resolveAttachmentUrlType must still return null for falsy input."""
    src = _src()
    assert re.search(r'if\s*\(\s*!url\s*\)\s*return null', src) or \
           re.search(r'if\s*\(!url\)', src), (
        "resolveAttachmentUrlType must still return null for falsy/empty url"
    )
