"""
Acceptance tests for issue #13: Rebuild search results page to approved mock.

AC1  - Page renders at public/index.html
AC2  - Layout is centered single-column, max-width ~720px, responsive
AC3  - Background #f6f7f9; cards white with 1px #e6e8ec border, 12px border-radius
AC4  - Fraunces for page title/doc titles; Inter for body; IBM Plex Mono for data labels/IDs
AC5  - Indigo accent #5b54e8 applied to Search button, focus rings, relevance bar fill
AC6  - Header contains page title and one-line subtitle
AC7  - Search box: text input + Search button; Enter and click both trigger search
AC8  - Results from GET /search?q=<query>; card shows title, text, relevance bar "relevance N%",
       doc ID in mono, attachment action
AC9  - Relevance normalized: top result = 100%; others proportional
AC10 - Empty state message: "No matches, try rephrasing."
AC11 - Error state shown when API is unreachable
AC12 - Keyboard-navigable with visible focus indicators on all interactive elements
AC13 - No regressions on existing routes or API integrations
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
# AC1 — public/index.html exists
# ---------------------------------------------------------------------------

def test_ac1_index_html_exists():
    """public/index.html must exist."""
    assert os.path.exists(INDEX_HTML), "public/index.html not found"


def test_ac1_html_is_valid_document():
    """File must contain a full HTML document."""
    src = _src()
    assert re.search(r'<!DOCTYPE\s+html>', src, re.IGNORECASE), "Missing DOCTYPE declaration"
    assert "<html" in src
    assert "<body" in src


# ---------------------------------------------------------------------------
# AC2 — Single-column layout, max-width ~720px, responsive
# ---------------------------------------------------------------------------

def test_ac2_max_width_720px():
    """CSS must set max-width around 720px for the main container."""
    src = _src()
    assert re.search(r"max-width\s*:\s*7[12][05]px", src), \
        "No max-width ~720px found in CSS"


def test_ac2_centered_layout():
    """Container must use margin: auto for centering."""
    src = _src()
    assert re.search(r"margin\s*:\s*0\s+auto|margin-(left|right)\s*:\s*auto", src), \
        "No margin: 0 auto or margin-left/right: auto for centering"


def test_ac2_responsive_viewport_meta():
    """HTML must have viewport meta tag for mobile responsiveness."""
    src = _src()
    assert 'name="viewport"' in src and "width=device-width" in src, \
        "Missing viewport meta tag"


def test_ac2_mobile_media_query():
    """CSS must include at least one media query for responsive layout."""
    src = _src()
    assert "@media" in src, "No @media query found for responsive layout"


# ---------------------------------------------------------------------------
# AC3 — Colors: background #f6f7f9, cards white/#e6e8ec border, 12px radius
# ---------------------------------------------------------------------------

def test_ac3_background_color():
    """Background must be #f6f7f9."""
    src = _src()
    assert "#f6f7f9" in src.lower(), \
        "Background color #f6f7f9 not found"


def test_ac3_card_border_color():
    """Cards must use #e6e8ec border."""
    src = _src()
    assert "#e6e8ec" in src.lower(), \
        "Card border color #e6e8ec not found"


def test_ac3_card_border_radius_12px():
    """Cards must have 12px border-radius."""
    src = _src()
    assert re.search(r"border-radius\s*:\s*12px|--radius\s*:\s*12px", src), \
        "12px border-radius not found for cards"


def test_ac3_card_white_background():
    """Card background must be white (#ffffff)."""
    src = _src()
    assert re.search(r"#ffffff|#fff\b|background\s*:\s*white", src, re.IGNORECASE), \
        "White card background not found"


# ---------------------------------------------------------------------------
# AC4 — Typography: Fraunces, Inter, IBM Plex Mono
# ---------------------------------------------------------------------------

def test_ac4_fraunces_font():
    """Fraunces font must be loaded and applied to headings."""
    src = _src()
    assert "Fraunces" in src, "Fraunces font not referenced"
    assert "fonts.googleapis.com" in src or "@font-face" in src, \
        "No Google Fonts or @font-face for Fraunces"


def test_ac4_inter_font():
    """Inter font must be loaded and applied to body text."""
    src = _src()
    assert "Inter" in src, "Inter font not referenced"


def test_ac4_ibm_plex_mono_font():
    """IBM Plex Mono font must be loaded and applied to data/IDs."""
    src = _src()
    assert "IBM Plex Mono" in src, "IBM Plex Mono font not referenced"


def test_ac4_serif_var_used_for_titles():
    """Fraunces must be applied to title elements (h1, h2 or via serif var)."""
    src = _src()
    has_serif = (
        re.search(r'font-family\s*:\s*var\(--serif\)|"Fraunces"', src) is not None
        or re.search(r'--serif.*Fraunces|Fraunces.*serif', src) is not None
    )
    assert has_serif, "Fraunces not applied as serif font to title elements"


def test_ac4_mono_var_used_for_ids():
    """IBM Plex Mono must be applied to data labels/IDs."""
    src = _src()
    has_mono = (
        re.search(r'font-family\s*:\s*var\(--mono\)|"IBM Plex Mono"', src) is not None
        or re.search(r'--mono.*IBM Plex Mono|IBM Plex Mono.*mono', src) is not None
    )
    assert has_mono, "IBM Plex Mono not applied as mono font for IDs/labels"


# ---------------------------------------------------------------------------
# AC5 — Indigo accent #5b54e8
# ---------------------------------------------------------------------------

def test_ac5_accent_color_defined():
    """Accent color #5b54e8 must be present in CSS."""
    src = _src()
    assert "#5b54e8" in src.lower(), \
        "Accent color #5b54e8 not found"


def test_ac5_search_button_uses_accent():
    """Search button must use accent color as background."""
    src = _src()
    # Button must reference accent directly or via var(--accent)
    has_accent_btn = (
        re.search(r'button.*#5b54e8|#5b54e8.*button', src, re.DOTALL) is not None
        or re.search(r'background\s*:\s*var\(--accent\)', src) is not None
        or (re.search(r'--accent\s*:\s*#5b54e8', src) is not None
            and re.search(r'background\s*:\s*var\(--accent\)', src) is not None)
    )
    assert has_accent_btn, \
        "Search button background not linked to #5b54e8 accent color"


def test_ac5_relevance_bar_uses_accent():
    """Relevance bar fill must use accent color."""
    src = _src()
    has_bar_accent = (
        re.search(r'bar.*var\(--accent\)|rel.*var\(--accent\)|accent.*bar', src, re.DOTALL | re.IGNORECASE) is not None
        or re.search(r'relevance.*#5b54e8|#5b54e8.*relevance', src, re.DOTALL | re.IGNORECASE) is not None
    )
    assert has_bar_accent, \
        "Relevance bar fill not linked to accent color #5b54e8"


# ---------------------------------------------------------------------------
# AC6 — Header with title and one-line subtitle
# ---------------------------------------------------------------------------

def test_ac6_header_element():
    """Page must have a <header> element."""
    src = _src()
    assert "<header" in src, "No <header> element found"


def test_ac6_page_title_h1():
    """Header must contain an <h1> page title."""
    src = _src()
    assert re.search(r"<h1[^>]*>", src), "No <h1> in header"


def test_ac6_subtitle_paragraph():
    """Header must contain a subtitle (a <p> or similar) as a one-liner."""
    src = _src()
    # Look for a paragraph inside or near header
    assert re.search(r"<header[^>]*>.*?<p[^>]*>.*?</p>", src, re.DOTALL), \
        "No subtitle <p> found inside <header>"


# ---------------------------------------------------------------------------
# AC7 — Search box: input + Search button; Enter + click trigger search
# ---------------------------------------------------------------------------

def test_ac7_search_input():
    """Page must have a text input for search queries."""
    src = _src()
    has_input = re.search(r'<input[^>]+type=["\']text["\']|<input[^>]+placeholder', src) is not None
    assert has_input, "No search text input found"


def test_ac7_search_button_text():
    """Search button must have 'Search' as its label."""
    src = _src()
    assert re.search(r">Search<", src), "No 'Search' button label found"


def test_ac7_enter_key_handler():
    """JS must handle Enter key press on the input to trigger search."""
    src = _src()
    has_enter = (
        re.search(r'["\']Enter["\']|key.*Enter|keydown|keypress|keyup', src) is not None
        or re.search(r'type=["\']submit["\']|form.*submit|\.submit\(\)', src) is not None
    )
    assert has_enter, "No Enter key handler or form submit found for search trigger"


def test_ac7_button_click_handler():
    """JS must handle Search button click to trigger search."""
    src = _src()
    has_click = re.search(
        r'addEventListener.*click|onclick|submit.*form|form.*submit',
        src, re.IGNORECASE
    )
    assert has_click, "No click handler found for Search button"


# ---------------------------------------------------------------------------
# AC8 — Results from GET /search?q=<query>; card structure
# ---------------------------------------------------------------------------

def test_ac8_fetch_search_endpoint():
    """JS must call GET /search?q=<query>."""
    src = _src()
    assert re.search(r'/search\?q=|/search.*\?.*q=|searchParams.*q|q=.*encodeURIComponent', src), \
        "No /search?q= call found in JS"


def test_ac8_card_shows_title():
    """Each result card must display the document title."""
    src = _src()
    assert re.search(r'\.title\b|result\.title|item\.title', src), \
        "No title field rendered in result card"


def test_ac8_card_shows_text():
    """Each result card must display document text (snippet/text field)."""
    src = _src()
    assert re.search(r'\.text\b|\.snippet\b|doc\.text|result\.text|item\.text|item\.snippet', src), \
        "No text/snippet field rendered in result card"


def test_ac8_card_shows_relevance_bar_with_label():
    """Each card must include a relevance bar labelled 'relevance N%'."""
    src = _src()
    assert re.search(r'relevance\s*\$\{|relevance.*%|`relevance', src, re.IGNORECASE), \
        "No 'relevance N%' label found for relevance bar"


def test_ac8_card_shows_doc_id_in_mono():
    """Doc ID must be displayed using mono font class or var."""
    src = _src()
    has_mono_id = (
        re.search(r'docid|doc-id|doc_id.*mono|mono.*doc', src, re.IGNORECASE) is not None
        or re.search(r'class=["\'][^"\']*docid[^"\']*["\']|class=["\'][^"\']*doc-id[^"\']*["\']', src) is not None
    )
    assert has_mono_id, "Doc ID not displayed in mono font or no docid class"


def test_ac8_card_has_attachment_action():
    """Each card must have an attachment action (Download link or button)."""
    src = _src()
    assert re.search(r'[Dd]ownload|attachment|attach', src), \
        "No attachment/download action found in result card"


# ---------------------------------------------------------------------------
# AC9 — Relevance normalisation: top = 100%
# ---------------------------------------------------------------------------

def test_ac9_normalises_scores():
    """JS must normalise scores so the top result shows 100%."""
    src = _src()
    has_normalise = (
        re.search(r'Math\.max|top\s*=|maxScore|max_score|topScore|highest', src) is not None
        and re.search(r'/ ?(top|max|highest)|normaliz', src, re.IGNORECASE) is not None
    )
    if not has_normalise:
        # Alternative: divides by first/max result score
        has_normalise = re.search(
            r'\[0\]\.score|results\[0\]|Math\.max\(.*score', src
        ) is not None
    assert has_normalise, \
        "No score normalisation (divide by max) found; top result must be 100%"


def test_ac9_top_result_pct_is_100():
    """Score normalisation must yield 100% for the top result."""
    src = _src()
    # Must use division by max and multiply by 100
    has_100_normalise = re.search(
        r'(\*\s*100|Math\.round.*\*.*100).*(?:top|max)|(?:top|max).*(\*\s*100)',
        src, re.IGNORECASE | re.DOTALL
    )
    assert has_100_normalise, \
        "Normalisation formula (score/max * 100) not found — top result must be 100%"


# ---------------------------------------------------------------------------
# AC10 — Empty state: "No matches, try rephrasing."
# ---------------------------------------------------------------------------

def test_ac10_empty_state_message():
    """Empty state must show 'No matches, try rephrasing.'"""
    src = _src()
    assert "No matches, try rephrasing" in src, \
        "Empty state message 'No matches, try rephrasing.' not found"


# ---------------------------------------------------------------------------
# AC11 — Error state when API unreachable
# ---------------------------------------------------------------------------

def test_ac11_error_state_present():
    """Page must include an error state message for unreachable API."""
    src = _src()
    has_error = re.search(
        r'error|unreachable|could not|failed|unable|something went wrong',
        src, re.IGNORECASE
    )
    assert has_error, "No error state message found"


def test_ac11_fetch_catch_handler():
    """JS fetch must have try/catch or .catch for error handling."""
    src = _src()
    has_catch = re.search(r'catch\s*\(|\.catch\s*\(', src)
    assert has_catch, "No catch/error handler for fetch found"


# ---------------------------------------------------------------------------
# AC12 — Keyboard navigation with visible focus indicators
# ---------------------------------------------------------------------------

def test_ac12_focus_visible_styles():
    """CSS must include :focus-visible styles for focus rings."""
    src = _src()
    assert ":focus-visible" in src or ":focus" in src, \
        "No :focus-visible or :focus styles for keyboard navigation"


def test_ac12_interactive_elements_focusable():
    """Input and button must be naturally focusable (no tabindex=-1)."""
    src = _src()
    # tabindex="-1" would remove from tab order (only OK on non-interactive elements)
    has_bad_tabindex = re.search(
        r'<(?:input|button)[^>]+tabindex=["\']?-1["\']?', src
    )
    assert not has_bad_tabindex, \
        "Interactive element (input/button) has tabindex=-1 — not keyboard navigable"


def test_ac12_aria_label_on_input():
    """Search input must have aria-label for screen reader accessibility."""
    src = _src()
    has_aria = re.search(r'aria-label|<label[^>]+for=', src)
    assert has_aria, "No aria-label or <label> for search input"


# ---------------------------------------------------------------------------
# AC13 — No regressions: existing routes still present
# ---------------------------------------------------------------------------

def test_ac13_search_url_pattern_preserved():
    """GET /search?q= pattern must still be used (no regression)."""
    src = _src()
    assert re.search(r'/search', src), "Missing /search endpoint reference"


def test_ac13_download_url_pattern_preserved():
    """Download action must still reference /download/ endpoint."""
    src = _src()
    assert re.search(r'/download', src), "Missing /download endpoint reference"


def test_ac13_results_field_name_preserved():
    """JS must still read 'results' array from API response."""
    src = _src()
    assert re.search(r'\.results\b|data\.results|["\']results["\']', src), \
        "Missing 'results' field reference in API response parsing"
