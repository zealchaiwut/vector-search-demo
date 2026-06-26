"""Tests for issue #109: Deduplicate overlapping static tests between two #98 test files

Acceptance Criteria:
1. conftest.py exists and exports shared assertion helpers
2. Both test_char_chunking__98.py and test_chunk_documents_overlapping_segments__98.py
   import the shared helpers from conftest.py (not duplicated)
3. The shared helpers (assert_migration_chunk_columns, assert_migration_preserves_article_metadata,
   assert_chunker_constants, read_all_migrations) work correctly when imported and called
"""

import os
import sys
import re

# Resolve paths
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Add tests dir to path so we can import conftest
sys.path.insert(0, TESTS_DIR)


def test_conftest_exists():
    """AC1: conftest.py exists in tests/ directory."""
    conftest_path = os.path.join(TESTS_DIR, "conftest.py")
    assert os.path.isfile(conftest_path), f"conftest.py not found at {conftest_path}"


def test_conftest_exports_required_helpers():
    """AC1: conftest.py exports read_all_migrations, assert_migration_chunk_columns, etc."""
    import conftest

    required_exports = [
        "read_all_migrations",
        "assert_migration_chunk_columns",
        "assert_migration_preserves_article_metadata",
        "assert_chunker_constants",
    ]
    for export_name in required_exports:
        assert hasattr(conftest, export_name), (
            f"conftest.py must export {export_name}"
        )
        assert callable(getattr(conftest, export_name)), (
            f"{export_name} must be callable"
        )


def test_conftest_exports_path_constants():
    """AC1: conftest.py exports path constants (CHUNKER_JS, MIGRATIONS_DIR, etc)."""
    import conftest

    required_constants = ["CHUNKER_JS", "MIGRATIONS_DIR", "PG_STORE_PATH"]
    for const_name in required_constants:
        assert hasattr(conftest, const_name), (
            f"conftest.py must export {const_name} path constant"
        )
        assert isinstance(getattr(conftest, const_name), str), (
            f"{const_name} must be a string path"
        )


def test_test_char_chunking_imports_from_conftest():
    """AC2: test_char_chunking__98.py imports helpers from conftest, not duplicated."""
    test_file = os.path.join(TESTS_DIR, "test_char_chunking__98.py")
    with open(test_file) as f:
        content = f.read()

    # Should have import from conftest
    assert "from conftest import" in content, (
        "test_char_chunking__98.py must import from conftest"
    )

    # Should NOT have duplicate definitions (no "def assert_migration_chunk_columns")
    assert not re.search(r"^def assert_migration_chunk_columns", content, re.MULTILINE), (
        "test_char_chunking__98.py must not define assert_migration_chunk_columns "
        "(should import from conftest)"
    )
    assert not re.search(r"^def assert_migration_preserves_article_metadata", content, re.MULTILINE), (
        "test_char_chunking__98.py must not define assert_migration_preserves_article_metadata "
        "(should import from conftest)"
    )
    assert not re.search(r"^def assert_chunker_constants", content, re.MULTILINE), (
        "test_char_chunking__98.py must not define assert_chunker_constants "
        "(should import from conftest)"
    )


def test_test_chunk_documents_overlapping_segments_imports_from_conftest():
    """AC2: test_chunk_documents_overlapping_segments__98.py imports from conftest."""
    test_file = os.path.join(TESTS_DIR, "test_chunk_documents_overlapping_segments__98.py")
    with open(test_file) as f:
        content = f.read()

    # Should have import from conftest
    assert "from conftest import" in content, (
        "test_chunk_documents_overlapping_segments__98.py must import from conftest"
    )

    # Should NOT have duplicate definitions
    assert not re.search(r"^def assert_migration_chunk_columns", content, re.MULTILINE), (
        "test_chunk_documents_overlapping_segments__98.py must not define "
        "assert_migration_chunk_columns (should import from conftest)"
    )


def test_read_all_migrations_works():
    """AC3: read_all_migrations() reads and concatenates all .sql files correctly."""
    import conftest

    sql = conftest.read_all_migrations()
    assert isinstance(sql, str), "read_all_migrations must return a string"
    assert len(sql) > 0, "read_all_migrations must return non-empty SQL"


def test_assert_migration_chunk_columns_validates():
    """AC3: assert_migration_chunk_columns validates the required columns."""
    import conftest

    # Valid SQL with required columns
    valid_sql = """
    CREATE TABLE articles (
        article_id text,
        chunk_index integer,
        details text,
        embedding vector
    );
    """
    # Should not raise
    conftest.assert_migration_chunk_columns(valid_sql)

    # Invalid SQL missing a column
    invalid_sql = """
    CREATE TABLE articles (
        article_id text,
        chunk_index integer
    );
    """
    try:
        conftest.assert_migration_chunk_columns(invalid_sql)
        assert False, "assert_migration_chunk_columns should reject SQL without all required columns"
    except AssertionError as e:
        assert "details" in str(e).lower() or "text" in str(e).lower(), (
            "Error message should identify the missing column"
        )


def test_assert_migration_preserves_article_metadata_validates():
    """AC3: assert_migration_preserves_article_metadata validates metadata columns."""
    import conftest

    # Valid SQL with metadata
    valid_sql = """
    CREATE TABLE articles (
        headline text,
        attachment_url text
    );
    """
    # Should not raise
    conftest.assert_migration_preserves_article_metadata(valid_sql)

    # Invalid SQL with DROP COLUMN on metadata
    invalid_sql = """
    ALTER TABLE articles DROP COLUMN headline;
    """
    try:
        conftest.assert_migration_preserves_article_metadata(invalid_sql)
        assert False, "Should reject DROP COLUMN on metadata columns"
    except AssertionError as e:
        assert "drop" in str(e).lower() or "headline" in str(e).lower(), (
            "Error message should mention the dropped column"
        )


def test_assert_chunker_constants_validates():
    """AC3: assert_chunker_constants validates export and value constraints."""
    import conftest

    # Valid chunker code
    valid_src = """
    export const CHUNK_SIZE = 500;
    export const CHUNK_OVERLAP = 100;
    function chunkDocument(article) {
        const chunks = [];
        for (let i = 0; i < article.details.length; i += (CHUNK_SIZE - CHUNK_OVERLAP)) {
            const chunk = article.details.slice(i, i + CHUNK_SIZE);
            chunks.push(chunk);
        }
        return chunks;
    }
    """
    # Should not raise
    conftest.assert_chunker_constants(valid_src)

    # Invalid: missing CHUNK_SIZE export
    invalid_src1 = """
    export const CHUNK_OVERLAP = 100;
    const CHUNK_SIZE = 500;
    """
    try:
        conftest.assert_chunker_constants(invalid_src1)
        assert False, "Should reject code without exported CHUNK_SIZE"
    except AssertionError as e:
        assert "chunk_size" in str(e).lower(), "Error should mention CHUNK_SIZE"

    # Invalid: bad value for CHUNK_SIZE
    invalid_src2 = """
    export const CHUNK_SIZE = 1000;
    export const CHUNK_OVERLAP = 100;
    """
    try:
        conftest.assert_chunker_constants(invalid_src2)
        assert False, "Should reject CHUNK_SIZE outside 400-600 range"
    except AssertionError as e:
        assert "400" in str(e) or "600" in str(e), "Error should mention expected range"


def test_no_duplicate_static_assertions():
    """AC2: Verify static assertion logic is not duplicated across test files."""
    test_file2 = os.path.join(TESTS_DIR, "test_chunk_documents_overlapping_segments__98.py")

    with open(test_file2) as f:
        content2 = f.read()

    # Verify that test_chunk_documents_overlapping_segments__98.py does NOT define
    # its own migration column check (it should import and use conftest)
    assert not re.search(
        r"def test.*migration.*chunk.*columns",
        content2,
        re.IGNORECASE
    ), (
        "test_chunk_documents_overlapping_segments__98.py should not define its own "
        "migration column check (use conftest helper)"
    )


def test_conftest_utf8_encoding_fix():
    """AC3: read_all_migrations uses explicit utf-8 encoding (fix for issue #109)."""
    import conftest
    import inspect

    # Check the function source
    source = inspect.getsource(conftest.read_all_migrations)
    assert "encoding" in source, (
        "read_all_migrations must specify encoding in open() call"
    )
    assert "utf-8" in source, (
        "read_all_migrations must use utf-8 encoding"
    )
