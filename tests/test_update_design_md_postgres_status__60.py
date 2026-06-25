"""
Tests for issue #60: DESIGN.md postgres backend status accuracy.

Verifies that DESIGN.md no longer describes the postgres backend as
"not yet wired" and correctly reflects that it is implemented and operational.
"""

import pathlib
import re

DESIGN_MD = pathlib.Path(__file__).parent.parent / "DESIGN.md"


def _read_design():
    return DESIGN_MD.read_text(encoding="utf-8")


def test_design_md_table_row_no_longer_says_not_yet_wired():
    """AC: The postgres row in the Supported backends table must not say 'not yet wired'."""
    text = _read_design()
    # Find the postgres table row
    match = re.search(r"\|\s*`postgres`\s*\|[^\n]*", text)
    assert match, "postgres row not found in DESIGN.md backends table"
    assert "not yet wired" not in match.group().lower(), (
        "postgres table row still says 'not yet wired'"
    )


def test_design_md_table_row_no_longer_says_not_yet_implemented():
    """AC: The postgres row must not reference 'not yet implemented' error."""
    text = _read_design()
    match = re.search(r"\|\s*`postgres`\s*\|[^\n]*", text)
    assert match, "postgres row not found in DESIGN.md backends table"
    assert "not yet implemented" not in match.group().lower(), (
        "postgres table row still references 'not yet implemented' error"
    )


def test_design_md_switching_example_no_longer_says_not_yet_wired():
    """AC: The switching-backends code block comment for postgres must not say 'not yet wired'."""
    text = _read_design()
    match = re.search(r"export DB_BACKEND=postgres[^\n]*", text)
    assert match, "postgres export line not found in Switching backends section"
    assert "not yet wired" not in match.group().lower(), (
        "postgres switching example still says 'not yet wired'"
    )


def test_design_md_postgres_row_reflects_operational_status():
    """AC: The postgres table row must convey that the backend is implemented/operational."""
    text = _read_design()
    match = re.search(r"\|\s*`postgres`\s*\|[^\n]*", text)
    assert match, "postgres row not found in DESIGN.md backends table"
    row = match.group().lower()
    # Must contain some positive indicator of working status
    assert any(
        keyword in row
        for keyword in ("implement", "operational", "wired", "functional", "full", "active")
    ), (
        f"postgres table row does not convey operational status: {match.group()}"
    )
