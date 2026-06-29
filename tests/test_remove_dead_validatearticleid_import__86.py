"""Tests for issue #86: Remove dead validateArticleId import from server.mjs

Acceptance Criteria:
  AC1 - validateArticleId is no longer imported in src/server.mjs
  AC2 - validateArticle and getArticleIdError are still imported (no regression)
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SERVER_MJS = REPO_ROOT / "src" / "server.mjs"

ARTICLE_VALIDATION_IMPORT_RE = re.compile(
    r'import\s*\{([^}]+)\}\s*from\s*["\']\.\/data\/articleValidation\.js["\']'
)


def _get_article_validation_imports():
    """Return the set of names imported from ./data/articleValidation.js in server.mjs."""
    source = SERVER_MJS.read_text(encoding="utf-8")
    match = ARTICLE_VALIDATION_IMPORT_RE.search(source)
    if not match:
        return set()
    names = {n.strip() for n in match.group(1).split(",")}
    return names


# ---------------------------------------------------------------------------
# AC1 — validateArticleId is not imported
# ---------------------------------------------------------------------------


def test_validateArticleId_not_imported():
    """AC1: validateArticleId must not appear in the articleValidation import in server.mjs"""
    names = _get_article_validation_imports()
    assert "validateArticleId" not in names, (
        "Dead import 'validateArticleId' must be removed from the "
        "articleValidation import in src/server.mjs"
    )


# ---------------------------------------------------------------------------
# AC2 — validateArticle and getArticleIdError are still imported (no regression)
# ---------------------------------------------------------------------------


def test_validateArticle_still_imported():
    """AC2: validateArticle must still be imported from articleValidation in server.mjs"""
    names = _get_article_validation_imports()
    assert "validateArticle" in names, (
        "'validateArticle' must still be imported from articleValidation in src/server.mjs"
    )


def test_getArticleIdError_still_imported():
    """AC2: getArticleIdError must still be imported from articleValidation in server.mjs"""
    names = _get_article_validation_imports()
    assert "getArticleIdError" in names, (
        "'getArticleIdError' must still be imported from articleValidation in src/server.mjs"
    )
