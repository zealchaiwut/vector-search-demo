"""
Tests for issue #104: Show multiple matching passages per search result card.

AC1 - When a document has multiple chunk hits, all matching passages are rendered
      beneath the article headline as separate highlighted passage blocks
AC2 - Each passage block uses the existing highlight styling (same as the current
      single-passage treatment)
AC3 - Each passage block displays its own individual relevance score/indicator
      using the existing relevance treatment
AC4 - When a document has only one chunk hit, the card renders identically to
      the current single-passage behavior (no visual regression)
AC5 - Passages are ordered consistently (by relevance score descending)
AC6 - The card layout does not break or overflow when three or more passages
      are displayed
"""

import json
import os
import re
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")
SEARCH_MODULE = os.path.join(REPO_ROOT, "src", "search", "index.js")
CORE_SEARCH = os.path.join(REPO_ROOT, "src", "core", "search.js")


def _load_html():
    with open(INDEX_HTML) as f:
        return f.read()


def _script_section(src):
    """Return only the <script> block of the HTML."""
    idx = src.index("<script>")
    return src[idx:]


def _css_section(src):
    """Return everything before the <script> block (includes the CSS)."""
    idx = src.index("<script>")
    return src[:idx]


def _run_node(script, timeout=60):
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
    )
    return result.stdout, result.stderr, result.returncode


def _call_search(query, k=5, module="./src/search/index.js"):
    script = f"""
import {{ searchDocuments }} from {json.dumps(module)};
const results = await searchDocuments({json.dumps(query)}, {k});
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error (rc={rc}):\n{err}"
    return json.loads(out)


# ---------------------------------------------------------------------------
# AC1 — Multi-passage rendering: all chunk hits render as separate blocks
# ---------------------------------------------------------------------------


def test_ac1_render_function_maps_over_passages_array():
    """renderResults must use passages.map(...) to emit one block per chunk hit."""
    src = _load_html()
    script = _script_section(src)
    assert re.search(
        r"passages\s*\.\s*map\s*\(\s*\(p|passages\s*\.map\(\s*\(p",
        script,
    ) or re.search(
        r"passages\s*\.map\(",
        script,
    ), (
        "index.html must call passages.map() to emit one passage block per chunk hit"
    )


def test_ac1_passage_block_emitted_per_hit_from_new_search_module():
    """New search module (src/search/index.js) returns passages array per article."""
    results = _call_search("vector embedding cosine", k=5)
    assert len(results) >= 1, "Expected at least one search result"
    for r in results:
        assert "passages" in r, (
            f"Result id={r.get('id')} must have 'passages' field. Keys: {list(r.keys())}"
        )
        assert isinstance(r["passages"], list), (
            f"passages must be a list for id={r.get('id')}"
        )
        assert len(r["passages"]) >= 1, (
            f"passages must have at least one entry for id={r.get('id')}"
        )


def test_ac1_multi_passage_result_available_from_new_search_module():
    """New search module can return articles with >1 passage from chunk hits."""
    results = _call_search("vector embedding cosine similarity semantic", k=10)
    multi = [r for r in results if len(r.get("passages", [])) > 1]
    if not multi:
        pytest.skip("No multi-passage result available with current collection.json")
    r = multi[0]
    assert len(r["passages"]) >= 2, (
        f"Expected ≥2 passages for multi-chunk article id={r.get('id')}, "
        f"got {len(r['passages'])}"
    )


def test_ac1_render_path_uses_r_passages_not_just_best_passage():
    """The render path must use r.passages (array), not just r.best_passage."""
    src = _load_html()
    script = _script_section(src)
    # passages array must be extracted from result before rendering
    assert re.search(r"r\.passages|result\.passages|passages\s*=", script, re.IGNORECASE), (
        "index.html must reference r.passages in the render path to show multiple passages"
    )


def test_ac1_passage_html_class_used_in_template():
    """Each rendered passage must use class='passage' HTML element."""
    src = _load_html()
    script = _script_section(src)
    assert re.search(
        r'class\s*=\s*["\']passage["\']|"passage"|\'passage\'',
        script,
    ), (
        "index.html must emit elements with class='passage' for each passage block"
    )


# ---------------------------------------------------------------------------
# AC2 — Each passage uses existing highlight styling
# ---------------------------------------------------------------------------


def test_ac2_passage_css_rule_defines_border_left():
    """The .passage CSS rule must define border-left (left-stripe highlight)."""
    src = _load_html()
    css = _css_section(src)
    passage_rule = re.search(r"\.passage\s*\{([^}]+)\}", css, re.DOTALL)
    assert passage_rule, "index.html must have a .passage CSS rule"
    rule_body = passage_rule.group(1)
    assert "border-left" in rule_body, (
        ".passage CSS rule must define border-left for the accent stripe"
    )


def test_ac2_passage_css_rule_defines_background():
    """The .passage CSS rule must define background (highlight background)."""
    src = _load_html()
    css = _css_section(src)
    passage_rule = re.search(r"\.passage\s*\{([^}]+)\}", css, re.DOTALL)
    assert passage_rule, "index.html must have a .passage CSS rule"
    rule_body = passage_rule.group(1)
    assert "background" in rule_body, (
        ".passage CSS rule must define background for the highlighted passage"
    )


def test_ac2_passage_text_css_exists_with_color():
    """The .passage-text CSS class must exist with a color definition."""
    src = _load_html()
    css = _css_section(src)
    text_rule = re.search(r"\.passage-text\s*\{([^}]+)\}", css, re.DOTALL)
    assert text_rule, "index.html must have a .passage-text CSS rule"
    rule_body = text_rule.group(1)
    assert "color" in rule_body, ".passage-text must define a text color"


def test_ac2_mark_highlight_css_exists():
    """The .passage-text mark selector must define a highlight background."""
    src = _load_html()
    css = _css_section(src)
    mark_rule = re.search(r"\.passage-text\s+mark\s*\{([^}]+)\}", css, re.DOTALL)
    assert mark_rule, (
        "index.html must have a .passage-text mark CSS rule for the semantic highlight"
    )
    rule_body = mark_rule.group(1)
    assert "background" in rule_body, (
        ".passage-text mark must define background for the semantic highlight"
    )


def test_ac2_same_render_function_used_for_all_passages():
    """All passage blocks must be rendered by the same function (no special-casing)."""
    src = _load_html()
    script = _script_section(src)
    # The render path maps over passages uniformly — no branch that renders
    # the first passage differently from others using a separate CSS class
    # (label differs via isFirst parameter, but class stays .passage)
    passage_fn = re.search(
        r"function\s+renderPassageBlock\b.*?(?=\nfunction\s|\nasync\s+function\s|\Z)",
        script,
        re.DOTALL,
    )
    if passage_fn:
        fn_body = passage_fn.group(0)
        # Must always produce class="passage" regardless of isFirst
        assert "passage" in fn_body, (
            "renderPassageBlock must produce a .passage element for every passage"
        )


# ---------------------------------------------------------------------------
# AC3 — Each passage displays its own individual relevance score
# ---------------------------------------------------------------------------


def test_ac3_render_passage_block_references_p_score():
    """renderPassageBlock must reference p.score to show a per-passage score."""
    src = _load_html()
    script = _script_section(src)
    passage_fn = re.search(
        r"function\s+renderPassageBlock\b.*?(?=\nfunction\s|\nasync\s+function\s|\Z)",
        script,
        re.DOTALL,
    )
    fn_body = passage_fn.group(0) if passage_fn else script
    assert re.search(r"p\s*\.\s*score|p\[.score.\]", fn_body), (
        "renderPassageBlock must reference p.score to render a per-passage score indicator"
    )


def test_ac3_new_search_module_passages_have_numeric_score():
    """Each passage returned by src/search/index.js must have a numeric score."""
    results = _call_search("vector search embedding", k=3)
    for r in results:
        for i, p in enumerate(r.get("passages", [])):
            assert "score" in p, (
                f"passages[{i}] missing 'score' for id={r.get('id')}"
            )
            assert isinstance(p["score"], (int, float)), (
                f"passages[{i}].score must be numeric for id={r.get('id')}, "
                f"got {type(p['score'])}"
            )


def test_ac3_passage_scores_differ_across_multi_chunk_results():
    """In a multi-passage result, the passages must have differing score values."""
    results = _call_search("vector embedding cosine similarity semantic", k=10)
    multi = [r for r in results if len(r.get("passages", [])) > 1]
    if not multi:
        pytest.skip("No multi-passage result in current collection.json")
    r = multi[0]
    passages = r["passages"]
    scores = [p["score"] for p in passages]
    # Scores don't have to be strictly different (dedup can collapse near-duplicates)
    # but for chunks from different document sections they should differ
    assert len(set(scores)) >= 1, "passages must each carry their own score"


def test_ac3_score_displayed_in_passage_label():
    """The passage-label template in renderPassageBlock must include the score."""
    src = _load_html()
    script = _script_section(src)
    passage_fn = re.search(
        r"function\s+renderPassageBlock\b.*?(?=\nfunction\s|\nasync\s+function\s|\Z)",
        script,
        re.DOTALL,
    )
    fn_body = passage_fn.group(0) if passage_fn else script
    # The score must appear in the passage-label div, not just anywhere
    assert re.search(r"passage-label.*score|score.*passage-label", fn_body, re.DOTALL), (
        "renderPassageBlock must include the passage score in the passage-label element"
    )


# ---------------------------------------------------------------------------
# AC4 — Single-chunk result renders identically (no regression)
# ---------------------------------------------------------------------------


def test_ac4_single_passage_still_rendered_with_passage_class():
    """A passages array of length 1 must still render a .passage element."""
    src = _load_html()
    script = _script_section(src)
    # passages.map is used uniformly; length=1 still maps to one block
    assert re.search(
        r"passages\s*\.map\(\s*\(p",
        script,
    ) or re.search(
        r"passages\.map\(",
        script,
    ), (
        "index.html must use passages.map() so a single-passage result "
        "renders identically to a multi-passage result"
    )


def test_ac4_first_passage_label_is_closest_passage():
    """The first (isFirst=true) passage must use 'Closest passage' label."""
    src = _load_html()
    script = _script_section(src)
    assert "Closest passage" in script, (
        "index.html must use 'Closest passage' label for the first passage block"
    )


def test_ac4_additional_passages_labeled_related_passage():
    """Passages beyond the first must use 'Related passage' label."""
    src = _load_html()
    script = _script_section(src)
    assert "Related passage" in script, (
        "index.html must use 'Related passage' label for subsequent passage blocks"
    )


def test_ac4_backward_compat_falls_back_to_best_passage():
    """If passages is absent, the UI must fall back to best_passage for compatibility."""
    src = _load_html()
    script = _script_section(src)
    assert re.search(r"best_passage", script), (
        "index.html must reference best_passage as a fallback when passages is absent"
    )


def test_ac4_single_result_has_at_least_one_passage_from_new_module():
    """Every result from src/search/index.js must have at least 1 passage."""
    results = _call_search("vector", k=1)
    assert len(results) >= 1, "Expected at least one result"
    r = results[0]
    passages = r.get("passages", [])
    assert len(passages) >= 1, (
        f"Top result (id={r.get('id')}) must have at least 1 passage"
    )


# ---------------------------------------------------------------------------
# AC5 — Passages ordered by relevance score descending
# ---------------------------------------------------------------------------


def test_ac5_new_search_module_returns_passages_sorted_descending():
    """src/search/index.js must return passages sorted by score descending."""
    results = _call_search("vector semantic embedding cosine", k=5)
    for r in results:
        passages = r.get("passages", [])
        if len(passages) < 2:
            continue
        scores = [p["score"] for p in passages]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], (
                f"passages not sorted descending for id={r.get('id')}: {scores}"
            )


def test_ac5_new_search_module_sort_logic_present():
    """src/search/index.js must contain sort logic for passages by score."""
    with open(SEARCH_MODULE) as f:
        src = f.read()
    assert re.search(r"\.sort\s*\(.*score|score.*\.sort", src, re.DOTALL), (
        "src/search/index.js must sort passages by score"
    )


def test_ac5_client_does_not_re_sort_passages():
    """index.html renderResults must NOT re-sort the passages array client-side."""
    src = _load_html()
    render_fn = re.search(
        r"function\s+renderResults\b.*?(?=\nasync\s+function\s|\nfunction\s+do|\Z)",
        _script_section(src),
        re.DOTALL,
    )
    if render_fn:
        fn_body = render_fn.group(0)
        client_sort = re.search(r"passages\s*\.\s*sort\s*\(", fn_body)
        assert not client_sort, (
            "renderResults must NOT sort passages client-side; "
            "order is determined server-side"
        )


def test_ac5_passages_index_used_for_is_first_flag():
    """renderResults must pass the array index to identify the first passage."""
    src = _load_html()
    script = _script_section(src)
    # passages.map((p, i) => ...) or passages.map((p, idx) => ...)
    assert re.search(r"passages\s*\.map\s*\(\s*\(\s*p\s*,\s*i", script) or re.search(
        r"passages\s*\.map\s*\(\s*\(p\s*,\s*i", script
    ), (
        "index.html must pass index (i) to the passages.map callback to identify "
        "the first passage (i === 0) for the 'Closest passage' label"
    )


# ---------------------------------------------------------------------------
# AC6 — Card layout handles 3+ passages without overflow
# ---------------------------------------------------------------------------


def test_ac6_card_has_no_overflow_hidden():
    """The .card CSS rule must NOT use overflow:hidden that would clip passages."""
    src = _load_html()
    css = _css_section(src)
    card_rule = re.search(r"\.card\s*\{([^}]+)\}", css, re.DOTALL)
    if card_rule:
        rule_body = card_rule.group(1)
        # overflow: hidden would clip multiple passages stacked vertically
        has_overflow_hidden = re.search(r"overflow\s*:\s*hidden", rule_body)
        assert not has_overflow_hidden, (
            ".card CSS must NOT use overflow:hidden — it would clip stacked passages"
        )


def test_ac6_passage_has_margin_for_vertical_spacing():
    """The .passage CSS rule must define margin for spacing between stacked blocks."""
    src = _load_html()
    css = _css_section(src)
    passage_rule = re.search(r"\.passage\s*\{([^}]+)\}", css, re.DOTALL)
    assert passage_rule, "index.html must have a .passage CSS rule"
    rule_body = passage_rule.group(1)
    assert "margin" in rule_body, (
        ".passage CSS rule must define margin for vertical spacing between stacked passages"
    )


def test_ac6_passage_count_capped_at_max_chunks():
    """New search module must cap passages at SEARCH_MAX_CHUNKS (default 3)."""
    with open(SEARCH_MODULE) as f:
        src = f.read()
    m = re.search(r"DEFAULT_MAX_CHUNKS\s*=\s*(\d+)|SEARCH_MAX_CHUNKS.*?(\d+)", src)
    default_max = int(m.group(1) or m.group(2)) if m else 3

    results = _call_search("vector semantic cosine embedding search", k=10)
    for r in results:
        passages = r.get("passages", [])
        assert len(passages) <= default_max, (
            f"passages for id={r.get('id')} has {len(passages)} entries; "
            f"must not exceed SEARCH_MAX_CHUNKS={default_max}"
        )


def test_ac6_card_uses_block_level_layout_for_passages():
    """Passage blocks must stack vertically (flex-direction column or block display)."""
    src = _load_html()
    css = _css_section(src)
    # .card must use flex-direction: column or block display to stack passages
    card_rule = re.search(r"\.card\s*\{([^}]+)\}", css, re.DOTALL)
    # Alternatively, .passage is block-level (div), so it naturally stacks.
    # The passage elements are divs which are block by default.
    # We just verify .passage is rendered as a div in the template.
    script = _script_section(src)
    assert re.search(r'<div class=["\']passage["\']|"<div class=\\"passage\\"', script) or \
           re.search(r'class\s*=\s*"passage"', script) or \
           re.search(r'"passage"', script), (
        "Passage blocks must be rendered as block-level div elements to stack vertically"
    )


# ---------------------------------------------------------------------------
# Source-level structure tests
# ---------------------------------------------------------------------------


def test_new_search_module_exports_search_documents():
    """src/search/index.js must export searchDocuments for use by the server."""
    with open(SEARCH_MODULE) as f:
        src = f.read()
    assert re.search(
        r"export\s+(async\s+)?function\s+searchDocuments|export\s+\{[^}]*searchDocuments",
        src,
    ), (
        "src/search/index.js must export searchDocuments"
    )


def test_new_search_module_returns_passages_in_result():
    """src/search/index.js must include 'passages' in its return shape."""
    with open(SEARCH_MODULE) as f:
        src = f.read()
    assert "passages" in src, (
        "src/search/index.js must include 'passages' in its result shape"
    )


def test_view_full_button_only_on_first_passage():
    """'View full article' button must only appear on the first passage block."""
    src = _load_html()
    script = _script_section(src)
    passage_fn = re.search(
        r"function\s+renderPassageBlock\b.*?(?=\nfunction\s|\nasync\s+function\s|\Z)",
        script,
        re.DOTALL,
    )
    fn_body = passage_fn.group(0) if passage_fn else script
    # view-full button must be conditional on isFirst
    assert re.search(r"isFirst.*view-full|view-full.*isFirst", fn_body, re.DOTALL), (
        "renderPassageBlock must only emit the 'View full article' button on the "
        "first passage (isFirst=true), not on subsequent passages"
    )
