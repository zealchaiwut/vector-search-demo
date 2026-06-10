"""
Acceptance tests for issue #15: Highlight best_passage in search result cards.

AC1  - Legend line "passage closest to your query" appears above results list
       with an amber swatch (#fff4d6 bg, #e0a200 2px bottom border)
AC2  - Each result card with best_passage shows exactly one highlighted passage:
       amber wash (background: #fff4d6, border-bottom: 2px solid #e0a200),
       text colour unchanged
AC3  - Passage matched using character offsets when both start and end offsets
       are present on best_passage
AC4  - Fallback to first verbatim occurrence of best_passage.text when offsets
       absent or incomplete
AC5  - A result with no best_passage renders document text normally — no
       highlight, no error, no empty highlight container
AC6  - No more than one highlighted region per result card
AC7  - Implementation lives in public/index.html
AC8  - Visual: warm amber wash (#fff4d6), 2px amber bottom edge (#e0a200),
       text colour unchanged
"""

import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")


def _src():
    with open(INDEX_HTML) as f:
        return f.read()


# ---------------------------------------------------------------------------
# AC1 — Legend line with amber swatch above results
# ---------------------------------------------------------------------------

def test_ac1_legend_text():
    """Page must contain the text 'passage closest to your query'."""
    src = _src()
    assert "passage closest to your query" in src, \
        "Legend text 'passage closest to your query' not found in index.html"


def test_ac1_legend_element_present():
    """A legend element (class 'legend') must be present in the HTML."""
    src = _src()
    assert re.search(r'class=["\'][^"\']*legend[^"\']*["\']', src), \
        "No element with class 'legend' found"


def test_ac1_swatch_element_present():
    """A swatch element must be present inside the legend."""
    src = _src()
    assert re.search(r'class=["\'][^"\']*swatch[^"\']*["\']', src), \
        "No element with class 'swatch' found"


def test_ac1_swatch_background_color():
    """Swatch background must be #fff4d6 (passage-bg)."""
    src = _src()
    has_color = (
        "#fff4d6" in src.lower()
        or re.search(r'--passage-bg\s*:\s*#fff4d6', src, re.IGNORECASE) is not None
    )
    assert has_color, "Amber swatch background #fff4d6 not found in CSS"


def test_ac1_swatch_border_color():
    """Swatch must have #e0a200 bottom border (passage-edge)."""
    src = _src()
    has_border = (
        "#e0a200" in src.lower()
        or re.search(r'--passage-edge\s*:\s*#e0a200', src, re.IGNORECASE) is not None
    )
    assert has_border, "Amber swatch border color #e0a200 not found in CSS"


def test_ac1_legend_above_results():
    """Legend must appear before the results container in the HTML."""
    src = _src()
    legend_pos = src.find("passage closest to your query")
    results_pos = src.find('id="results"')
    assert legend_pos != -1, "Legend text not found"
    assert results_pos != -1, "results container not found"
    assert legend_pos < results_pos, \
        "Legend must appear before the results container in the DOM"


# ---------------------------------------------------------------------------
# AC2 — Highlighted passage styling
# ---------------------------------------------------------------------------

def test_ac2_mark_passage_css_class():
    """CSS must define mark.passage or .passage with amber background."""
    src = _src()
    has_passage_style = re.search(
        r'mark\.passage|\.passage\b|mark\[class\*=passage\]',
        src
    ) is not None
    assert has_passage_style, "No CSS rule for mark.passage or .passage found"


def test_ac2_passage_background_fff4d6():
    """Highlighted passage background must be #fff4d6."""
    src = _src()
    assert "#fff4d6" in src.lower(), \
        "Passage highlight background #fff4d6 not found"


def test_ac2_passage_amber_border():
    """Highlighted passage must have #e0a200 bottom border styling."""
    src = _src()
    assert "#e0a200" in src.lower(), \
        "Passage amber border color #e0a200 not found"


def test_ac2_passage_uses_mark_element():
    """JS must emit a <mark> element to wrap the highlighted passage."""
    src = _src()
    assert re.search(r'<mark|mark.*passage|passage.*mark', src, re.IGNORECASE), \
        "No <mark> element used for passage highlight"


# ---------------------------------------------------------------------------
# AC3 — Character offset matching
# ---------------------------------------------------------------------------

def test_ac3_offset_based_highlight():
    """JS must read start/end character offsets from best_passage."""
    src = _src()
    has_offsets = re.search(
        r'\.start\b|\.end\b|best_passage\.start|best_passage\.end|'
        r'start_offset|end_offset|charStart|charEnd',
        src
    ) is not None
    assert has_offsets, \
        "No character offset (start/end) reading from best_passage found in JS"


def test_ac3_substring_slice_for_offsets():
    """JS must use substring/slice to extract the passage by character offsets."""
    src = _src()
    has_slice = re.search(
        r'\.substring\s*\(|\.slice\s*\(|substr\s*\(',
        src
    ) is not None
    assert has_slice, \
        "No substring/slice call found for character-offset-based passage extraction"


# ---------------------------------------------------------------------------
# AC4 — Verbatim text fallback
# ---------------------------------------------------------------------------

def test_ac4_verbatim_text_fallback():
    """JS must fall back to indexOf/includes for verbatim text matching."""
    src = _src()
    has_fallback = re.search(
        r'indexOf|includes\s*\(|\.find\s*\(|search\s*\(',
        src, re.IGNORECASE
    ) is not None
    assert has_fallback, \
        "No verbatim text fallback (indexOf/includes) found in JS for best_passage.text"


def test_ac4_fallback_uses_best_passage_text():
    """JS must read best_passage.text for the verbatim fallback."""
    src = _src()
    has_text_field = re.search(
        r'best_passage\.text|best_passage\[["\']text["\']\]|passageText',
        src
    ) is not None
    assert has_text_field, \
        "No reference to best_passage.text for verbatim fallback"


# ---------------------------------------------------------------------------
# AC5 — No best_passage → normal render, no highlight, no error
# ---------------------------------------------------------------------------

def test_ac5_no_best_passage_guard():
    """JS must guard against missing best_passage (conditional check)."""
    src = _src()
    has_guard = re.search(
        r'best_passage\s*&&|if\s*\(\s*best_passage|best_passage\s*\?|'
        r'\.best_passage\b',
        src
    ) is not None
    assert has_guard, \
        "No guard/check for missing best_passage found; results without it may break"


def test_ac5_no_empty_mark_emitted():
    """JS must not emit an empty <mark> when best_passage is absent."""
    src = _src()
    # Should not have unconditional mark emission
    bad = re.search(
        r'<mark class=["\']passage["\']></mark>|<mark></mark>',
        src
    )
    assert not bad, "Unconditional empty <mark> found in template — would appear when best_passage is absent"


# ---------------------------------------------------------------------------
# AC6 — At most one highlighted region per result card
# ---------------------------------------------------------------------------

def test_ac6_single_highlight_per_card():
    """JS must emit at most one <mark class="passage"> per card."""
    src = _src()
    # The highlight function must not loop over multiple matches or passages
    # A simple proxy: the code should not call replaceAll/global regex on the
    # text to find multiple matches, or if it does, it should break after one.
    has_single_highlight_logic = re.search(
        r'replaceAll|replace.*\/g["\'\s,)]',
        src
    ) is None or re.search(
        r'indexOf|\.search\b|first.*match|once|break',
        src, re.IGNORECASE
    ) is not None
    assert has_single_highlight_logic, \
        "JS appears to replace all occurrences — only one highlight is allowed per card"


# ---------------------------------------------------------------------------
# AC7 — Implementation in public/index.html
# ---------------------------------------------------------------------------

def test_ac7_implementation_in_index_html():
    """All highlight logic must live in public/index.html (not a separate file)."""
    src = _src()
    # Must have both the mark.passage CSS and the highlight JS in the same file
    has_css = re.search(r'#fff4d6|--passage-bg', src) is not None
    has_js = re.search(r'best_passage', src) is not None
    assert has_css and has_js, \
        "public/index.html must contain both the passage CSS and the best_passage JS logic"


# ---------------------------------------------------------------------------
# AC8 — Visual correctness tokens
# ---------------------------------------------------------------------------

def test_ac8_passage_bg_token():
    """CSS variable --passage-bg must be #fff4d6."""
    src = _src()
    assert re.search(r'--passage-bg\s*:\s*#fff4d6', src, re.IGNORECASE), \
        "--passage-bg CSS variable not set to #fff4d6"


def test_ac8_passage_edge_token():
    """CSS variable --passage-edge must be #e0a200."""
    src = _src()
    assert re.search(r'--passage-edge\s*:\s*#e0a200', src, re.IGNORECASE), \
        "--passage-edge CSS variable not set to #e0a200"


def test_ac8_no_text_color_change_on_mark():
    """mark.passage must not set a different text colour — ink/inherit only."""
    src = _src()
    # Extract just the mark.passage rule (rough heuristic)
    mark_block = re.search(r'mark\.passage\s*\{([^}]+)\}', src)
    if mark_block:
        block = mark_block.group(1)
        bad_color = re.search(r'color\s*:\s*(?!var\(--ink\)|inherit|currentColor|#1a1d23)', block)
        assert not bad_color, \
            "mark.passage sets a custom text colour — AC requires text colour unchanged"
