"""
Tests for issue #24: Clarify scope path for best_passage implementation
(src/search vs src/core).

Acceptance criteria:
- The test for AC10 (issue #14) uses a direct, non-redundant path to
  src/core/search.js without the confusing ../coder detour.
- The path resolves to the actual implementation file.
- The AC10 comment in the test explicitly names src/core/search.js, not src/search/.
"""

import ast
import os

TEST_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "test_add_best_matching_passage_to_search_results__14.py",
)


def _get_source():
    with open(TEST_FILE) as f:
        return f.read()


def test_path_has_no_redundant_coder_segment():
    """Path must not use the ../coder detour."""
    src = _get_source()
    assert '"..", "coder"' not in src and '"..","coder"' not in src and "'..',  'coder'" not in src, (
        "CORE_SEARCH_JS path still contains the redundant '../coder' detour. "
        "Should use os.path.join(REPO_ROOT, 'src', 'core', 'search.js') directly."
    )


def test_path_targets_core_search_js():
    """CORE_SEARCH_JS must resolve to src/core/search.js under REPO_ROOT."""
    src = _get_source()
    assert '"src", "core", "search.js"' in src or "'src', 'core', 'search.js'" in src, (
        "CORE_SEARCH_JS must use os.path.join(REPO_ROOT, 'src', 'core', 'search.js')."
    )


def test_resolved_path_exists():
    """The resolved path must point to an existing file."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    core_search_js = os.path.join(repo_root, "src", "core", "search.js")
    assert os.path.isfile(core_search_js), (
        f"Expected implementation file at {core_search_js} but it does not exist."
    )


def test_ac10_comment_names_core_search_js():
    """AC10 comment must reference src/core/search.js, not the outdated src/search/."""
    src = _get_source()
    ac10_lines = [l for l in src.splitlines() if "AC10" in l or "ac10" in l.lower()]
    assert ac10_lines, "No AC10 comment found in the test file."
    combined = " ".join(ac10_lines)
    assert "src/search/" not in combined, (
        "AC10 comment still references the incorrect path 'src/search/'. "
        "Should reference 'src/core/search.js'."
    )
    assert "src/core" in combined, (
        "AC10 comment must explicitly reference 'src/core' (i.e. src/core/search.js)."
    )
