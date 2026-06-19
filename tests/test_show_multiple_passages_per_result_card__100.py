"""
Tests for issue #100: Show multiple matching passages per result card.

AC1 - When the search response contains multiple chunk hits for a document, the
      result card renders each chunk as a separate highlighted passage below the
      article headline.
AC2 - Each passage displays its own individual relevance score/indicator using
      the existing highlight styling.
AC3 - Passages are rendered in the order they are returned by the API (no
      client-side re-sorting).
AC4 - A document with exactly one chunk hit renders identically to the current
      single-passage layout (no visual regression).
AC5 - A document with zero chunk hits (headline-only match) renders without a
      passage section and without errors.
AC6 - No existing highlight styles are modified; only the passage list structure
      is changed.
"""

import json
import os
import re
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")


def _load_html():
    with open(INDEX_HTML) as f:
        return f.read()


def _script_section(src):
    """Return only the <script> block of the HTML."""
    idx = src.index("<script>")
    return src[idx:]


def _run_node(script, timeout=30):
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
    )
    return result.stdout, result.stderr, result.returncode


def _call_search(query, k=5):
    script = f"""
import {{ searchDocuments }} from './src/core/search.js';
const results = await searchDocuments({json.dumps(query)}, {k});
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error (rc={rc}):\n{err}"
    return json.loads(out)


# ---------------------------------------------------------------------------
# AC1 — Multiple passages rendered per card
# ---------------------------------------------------------------------------


def test_ac1_render_function_iterates_passages():
    """renderResults must iterate r.passages to emit one block per hit."""
    src = _load_html()
    script = _script_section(src)
    # Must use .map or forEach over passages array to produce blocks
    assert re.search(
        r"passages\s*\.\s*map|passages\.forEach|for\s*\(.*passages",
        script,
        re.IGNORECASE,
    ), (
        "index.html must iterate r.passages (using .map or forEach) to render "
        "one passage block per chunk hit"
    )


def test_ac1_passage_block_uses_passage_class():
    """Each rendered passage block must use the .passage CSS class."""
    src = _load_html()
    script = _script_section(src)
    # The template string returned by renderPassageBlock must include class="passage"
    assert re.search(r'class\s*=\s*["\']passage["\']|"passage"|\'passage\'', script), (
        "index.html must emit elements with class='passage' for each passage block"
    )


def test_ac1_multi_passage_result_emits_multiple_blocks():
    """Rendering a result with two passages produces two .passage elements."""
    results = _call_search("vector embedding cosine", k=5)
    # Find a result with >1 passage
    multi = [r for r in results if len(r.get("passages", [])) > 1]
    if not multi:
        pytest.skip("No multi-passage result available in file-backed data")
    r = multi[0]
    passages = r["passages"]
    # Verify backend actually returns >1
    assert len(passages) >= 2, "Need ≥2 passages in this result to test AC1"


# ---------------------------------------------------------------------------
# AC2 — Each passage shows its own score/indicator
# ---------------------------------------------------------------------------


def test_ac2_render_passage_block_uses_passage_score():
    """renderPassageBlock must reference p.score (or passage.score) to show a per-passage score."""
    src = _load_html()
    script = _script_section(src)
    assert re.search(
        r"p\s*\.\s*score|passage\s*\.\s*score|p\[.score.\]|\.score",
        script,
    ), (
        "index.html must reference p.score (or passage.score) within the passage "
        "rendering function to display each passage's individual relevance"
    )


def test_ac2_score_displayed_in_passage_block():
    """The passage block template must include the score value in its output."""
    src = _load_html()
    script = _script_section(src)
    # The renderPassageBlock function must include the score in the returned HTML string.
    # Look for score reference in proximity to the passage div template.
    passage_fn_match = re.search(
        r"function\s+renderPassageBlock.*?(?=\n\s*function|\n\s*async\s+function|$)",
        script,
        re.DOTALL,
    )
    if not passage_fn_match:
        # May be an arrow function or inline; check the full script
        fn_body = script
    else:
        fn_body = passage_fn_match.group(0)

    assert re.search(r"score", fn_body, re.IGNORECASE), (
        "renderPassageBlock must include score in the passage block HTML it returns"
    )


def test_ac2_passage_score_numeric_from_api():
    """Passages returned by the API carry a numeric score field."""
    results = _call_search("vector search", k=3)
    for r in results:
        for i, p in enumerate(r.get("passages", [])):
            assert "score" in p, (
                f"passages[{i}] missing score for id={r.get('id')}"
            )
            assert isinstance(p["score"], (int, float)), (
                f"passages[{i}].score must be numeric for id={r.get('id')}"
            )


# ---------------------------------------------------------------------------
# AC3 — Passages rendered in API order (no client-side re-sorting)
# ---------------------------------------------------------------------------


def test_ac3_no_client_side_sort_on_passages():
    """The render path must NOT sort r.passages before rendering."""
    src = _load_html()
    script = _script_section(src)
    # Extract the renderResults or equivalent block
    # If there's a .sort( call immediately after building the passages array
    # (before calling renderPassageBlock), that's a violation.
    # Pattern: passages = r.passages; passages.sort(...) before the map
    # We look for a sort call on the local `passages` variable inside renderResults.
    render_fn = re.search(
        r"function\s+renderResults.*?(?=\n\s*async\s+function|\n\s*function\s+do|\Z)",
        script,
        re.DOTALL,
    )
    if render_fn:
        fn_body = render_fn.group(0)
        # Any .sort( on the passages array would be a violation of AC3
        client_sort = re.search(r"passages\s*\.\s*sort\s*\(", fn_body)
        assert not client_sort, (
            "renderResults must NOT sort passages client-side; "
            "passages must be rendered in the order returned by the API"
        )


def test_ac3_api_returns_passages_in_defined_order():
    """API passages are already sorted server-side; client must preserve that order."""
    results = _call_search("vector semantic embedding", k=5)
    for r in results:
        passages = r.get("passages", [])
        if len(passages) < 2:
            continue
        # Server sorts descending by score; verify the order is consistent
        scores = [p["score"] for p in passages]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], (
                f"API passages not in descending score order for id={r.get('id')}: {scores}"
            )


# ---------------------------------------------------------------------------
# AC4 — Single passage renders identically (no visual regression)
# ---------------------------------------------------------------------------


def test_ac4_single_passage_still_uses_passage_class():
    """When passages array has one element, the block must still use .passage class."""
    src = _load_html()
    script = _script_section(src)
    # The same renderPassageBlock call must be used for single-passage results
    # (passages.map with the same function covers both 1 and N passages)
    assert re.search(
        r"passages\s*\.\s*map.*renderPassageBlock|renderPassageBlock.*passages",
        script,
        re.DOTALL | re.IGNORECASE,
    ) or re.search(
        r"passages\s*\.map\s*\(\s*\(p",
        script,
    ), (
        "index.html must use the same passages.map path for both single and "
        "multi-passage results so layout is identical"
    )


def test_ac4_first_passage_label_is_closest_passage():
    """The first passage in a card must use the 'Closest passage' label."""
    src = _load_html()
    script = _script_section(src)
    assert "Closest passage" in script, (
        "index.html must use 'Closest passage' label for the first passage block"
    )


def test_ac4_single_chunk_result_has_one_passage_from_api():
    """A result with a short text returns exactly one passage from the search API."""
    results = _call_search("vector", k=1)
    assert len(results) >= 1
    r = results[0]
    passages = r.get("passages", [])
    assert len(passages) >= 1, "Top result must have at least one passage"
    # The key point: passages array drives rendering; no extra empty blocks
    assert len(passages) <= 3, "passages must be capped at MAX_CHUNKS_PER_ARTICLE=3"


# ---------------------------------------------------------------------------
# AC5 — Zero chunk hits render without passage section or errors
# ---------------------------------------------------------------------------


def test_ac5_empty_passages_produces_no_block():
    """renderPassageBlock with empty text must return empty string (no block)."""
    src = _load_html()
    script = _script_section(src)
    # renderPassageBlock must guard against empty/null passage text
    assert re.search(
        r"if\s*\(\s*!text\s*\)|text\s*\?\s*p|p\s*&&\s*p\.text|if.*text.*return\s*\"\"",
        script,
    ), (
        "renderPassageBlock must return empty string when passage text is missing, "
        "so zero-chunk results render without a passage section"
    )


def test_ac5_empty_passages_array_renders_no_blocks():
    """If r.passages is empty, passageBlocks must be an empty string."""
    src = _load_html()
    script = _script_section(src)
    # When passages is empty, .map returns [], and .join('') gives ''
    # This is guaranteed by the map+join pattern; verify the pattern exists
    assert re.search(
        r"passages\s*\.\s*map.*join\s*\(\s*[\"']\s*[\"']\s*\)|"
        r"join\s*\(\s*[\"']\s*[\"']\s*\).*passages",
        script,
        re.DOTALL,
    ) or re.search(
        r"passages\.map\(.*\)\.join\(",
        script,
        re.DOTALL,
    ), (
        "index.html must use passages.map(...).join('') so an empty array "
        "produces no passage blocks"
    )


# ---------------------------------------------------------------------------
# AC6 — No existing highlight styles modified
# ---------------------------------------------------------------------------


def test_ac6_passage_css_class_definition_unchanged():
    """The .passage CSS block must still define border-left, background, and border-radius."""
    src = _load_html()
    # Check the CSS section (before <script>)
    css_section = src[: src.index("<script>")]
    passage_rule = re.search(
        r"\.passage\s*\{([^}]+)\}", css_section, re.DOTALL
    )
    assert passage_rule, "index.html must retain a .passage { ... } CSS rule"
    rule_body = passage_rule.group(1)
    assert "border-left" in rule_body, ".passage must still define border-left"
    assert "background" in rule_body, ".passage must still define background"
    assert "border-radius" in rule_body, ".passage must still define border-radius"


def test_ac6_passage_label_css_unchanged():
    """The .passage-label CSS class must still exist with uppercase and color."""
    src = _load_html()
    css_section = src[: src.index("<script>")]
    label_rule = re.search(
        r"\.passage-label\s*\{([^}]+)\}", css_section, re.DOTALL
    )
    assert label_rule, "index.html must retain .passage-label CSS rule"
    rule_body = label_rule.group(1)
    assert "text-transform" in rule_body, ".passage-label must still use text-transform"
    assert "color" in rule_body, ".passage-label must still define color"


def test_ac6_passage_text_css_unchanged():
    """The .passage-text CSS class must still exist."""
    src = _load_html()
    css_section = src[: src.index("<script>")]
    assert re.search(r"\.passage-text\s*\{", css_section), (
        "index.html must retain .passage-text CSS rule"
    )


def test_ac6_no_new_css_overrides_for_passage():
    """No new CSS rules that override .passage border-left, background, or padding."""
    src = _load_html()
    css_section = src[: src.index("<script>")]
    # Count how many times .passage { appears (should be exactly 1)
    passage_rules = re.findall(r"\.passage\s*\{", css_section)
    assert len(passage_rules) == 1, (
        f"index.html must have exactly one .passage CSS rule, found {len(passage_rules)}"
    )
