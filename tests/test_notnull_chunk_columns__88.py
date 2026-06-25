"""
Tests for issue #88: Add NOT NULL constraints to article_id and chunk_index columns

Context: Follow-up to #80 review (#84). The 002_chunk_columns.sql migration adds
article_id and chunk_index as nullable columns and backfills them. This ticket locks
down the invariant at the schema level by adding a follow-on migration that sets
NOT NULL after the backfill.

AC1 - A follow-on migration file exists at src/store/migrations/006_chunk_columns_notnull.sql
AC2 - The migration sets NOT NULL on the article_id column
AC3 - The migration sets NOT NULL on the chunk_index column
AC4 - The migration comes after 002_chunk_columns.sql (higher number), so the backfill
      always runs before the constraint is applied
"""

import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(REPO_ROOT, "src", "store", "migrations")
MIGRATION_PATH = os.path.join(MIGRATIONS_DIR, "006_chunk_columns_notnull.sql")


def read_migration():
    with open(MIGRATION_PATH) as f:
        return f.read()


# ---------------------------------------------------------------------------
# AC1: Migration file 006_chunk_columns_notnull.sql exists
# ---------------------------------------------------------------------------


def test_ac1_migration_file_exists():
    """Migration file 006_chunk_columns_notnull.sql must exist in the migrations directory."""
    assert os.path.isfile(MIGRATION_PATH), (
        f"Migration file not found: {MIGRATION_PATH}\n"
        "Expected a follow-on migration that adds NOT NULL constraints to article_id and chunk_index."
    )


# ---------------------------------------------------------------------------
# AC2: Migration sets NOT NULL on article_id
# ---------------------------------------------------------------------------


def test_ac2_migration_sets_article_id_not_null():
    """Migration must ALTER COLUMN article_id SET NOT NULL."""
    sql = read_migration()
    assert re.search(
        r"ALTER\s+COLUMN\s+article_id\s+SET\s+NOT\s+NULL",
        sql,
        re.IGNORECASE,
    ), (
        "Migration must contain 'ALTER COLUMN article_id SET NOT NULL' "
        "to enforce the NOT NULL constraint at the schema level."
    )


# ---------------------------------------------------------------------------
# AC3: Migration sets NOT NULL on chunk_index
# ---------------------------------------------------------------------------


def test_ac3_migration_sets_chunk_index_not_null():
    """Migration must ALTER COLUMN chunk_index SET NOT NULL."""
    sql = read_migration()
    assert re.search(
        r"ALTER\s+COLUMN\s+chunk_index\s+SET\s+NOT\s+NULL",
        sql,
        re.IGNORECASE,
    ), (
        "Migration must contain 'ALTER COLUMN chunk_index SET NOT NULL' "
        "to enforce the NOT NULL constraint at the schema level."
    )


# ---------------------------------------------------------------------------
# AC4: Migration file is numbered after 002 (backfill runs first)
# ---------------------------------------------------------------------------


def test_ac4_migration_numbered_after_002():
    """Migration filename must be numbered higher than 002 so the backfill runs first."""
    migration_files = sorted(
        f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")
    )
    notnull_files = [f for f in migration_files if "notnull" in f.lower()]
    chunk_files = [f for f in migration_files if "chunk_columns" in f.lower()]

    assert notnull_files, "Expected at least one migration file with 'notnull' in its name."

    notnull_file = notnull_files[0]
    notnull_num = int(notnull_file.split("_")[0])

    # Find 002_chunk_columns.sql number
    backfill_files = [f for f in chunk_files if not "notnull" in f.lower()]
    assert backfill_files, "Expected 002_chunk_columns.sql to still exist."
    backfill_num = int(backfill_files[0].split("_")[0])

    assert notnull_num > backfill_num, (
        f"NOT NULL migration ({notnull_file}, num={notnull_num}) must have a higher number "
        f"than the backfill migration ({backfill_files[0]}, num={backfill_num}) "
        "so that the backfill always runs first."
    )
