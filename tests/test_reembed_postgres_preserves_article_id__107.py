"""
Tests for issue #107: reEmbedPostgres() must include article_id and chunk_index
in the row mapping passed to store.upsert() so those fields are not nulled out.

AC:
- The mapped object includes article_id: r.article_id
- The mapped object includes chunk_index: r.chunk_index
- No rows in the upsert payload have article_id or chunk_index set to undefined/null
"""
import re
import textwrap
from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "commands" / "re-embed.js"


def _read_source():
    return SRC.read_text(encoding="utf-8")


def _extract_normal_reembed_mapping(source: str) -> str:
    """
    Pull the row mapping block inside reEmbedPostgres() for the normal re-embed
    path (no recreate). That block is between the SELECT query result and the
    batchEmbed call.
    """
    # Find the normal re-embed path (after checkSchemaCompatibility)
    match = re.search(
        r"checkSchemaCompatibility\(\).*?rows\s*=\s*result\.rows\.map\(\(r\)\s*=>\s*\((\{.*?\})\)\)",
        source,
        re.DOTALL,
    )
    assert match, (
        "Could not locate the row mapping in the normal re-embed path of reEmbedPostgres(). "
        "Expected pattern: result.rows.map((r) => ({...})) after checkSchemaCompatibility()"
    )
    return match.group(1)


class TestArticleIdInUpsertPayload:
    """AC: article_id and chunk_index must be in the mapped object."""

    def test_article_id_present_in_row_mapping(self):
        source = _read_source()
        mapping = _extract_normal_reembed_mapping(source)
        assert "article_id" in mapping, (
            f"article_id is missing from the row mapping in reEmbedPostgres().\n"
            f"Current mapping block:\n{textwrap.indent(mapping, '  ')}"
        )

    def test_chunk_index_present_in_row_mapping(self):
        source = _read_source()
        mapping = _extract_normal_reembed_mapping(source)
        assert "chunk_index" in mapping, (
            f"chunk_index is missing from the row mapping in reEmbedPostgres().\n"
            f"Current mapping block:\n{textwrap.indent(mapping, '  ')}"
        )

    def test_article_id_mapped_from_row(self):
        """The mapping must read r.article_id, not some other value."""
        source = _read_source()
        mapping = _extract_normal_reembed_mapping(source)
        assert re.search(r"article_id\s*:\s*r\.article_id", mapping), (
            "article_id must be mapped as `article_id: r.article_id`.\n"
            f"Current mapping block:\n{textwrap.indent(mapping, '  ')}"
        )

    def test_chunk_index_mapped_from_row(self):
        """The mapping must read r.chunk_index, not some other value."""
        source = _read_source()
        mapping = _extract_normal_reembed_mapping(source)
        assert re.search(r"chunk_index\s*:\s*r\.chunk_index", mapping), (
            "chunk_index must be mapped as `chunk_index: r.chunk_index`.\n"
            f"Current mapping block:\n{textwrap.indent(mapping, '  ')}"
        )

    def test_select_query_fetches_article_id_and_chunk_index(self):
        """The SELECT query must include article_id and chunk_index so they're available in r."""
        source = _read_source()
        # Find the SELECT inside reEmbedPostgres
        match = re.search(r"SELECT\s+(.*?)\s+FROM\s+articles", source, re.DOTALL | re.IGNORECASE)
        assert match, "Could not find SELECT query in reEmbedPostgres()"
        columns = match.group(1)
        assert "article_id" in columns, f"SELECT query missing article_id. Got: {columns}"
        assert "chunk_index" in columns, f"SELECT query missing chunk_index. Got: {columns}"
