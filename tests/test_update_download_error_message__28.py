"""Tests for issue #28: [follow-up] Update /download error message to mention attachments"""
import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_MJS = os.path.join(REPO_ROOT, "src", "server.mjs")


def _server_src():
    with open(SERVER_MJS) as f:
        return f.read()


def _download_handler_block(src):
    """Extract the /download route handler block from server.mjs."""
    m = re.search(
        r'// GET /download.*?(?=// GET /|$)',
        src,
        re.DOTALL,
    )
    return m.group(0) if m else src


# --- Acceptance Criteria ---

def test_update_download_error_message__download_route_returns_attachment_not_found():
    # AC1: The /download route must return 'Attachment not found', not 'Document not found'
    src = _server_src()
    handler = _download_handler_block(src)
    assert "Attachment not found" in handler, (
        "server.mjs /download handler must return 'Attachment not found' "
        "when the requested file does not exist"
    )
    assert "Document not found" not in handler, (
        "server.mjs /download handler must not contain the old message "
        "'Document not found' — it should be 'Attachment not found'"
    )


def test_update_download_error_message__fix_applied_at_server_mjs():
    # AC2: The error message change must be present in src/server.mjs
    assert os.path.isfile(SERVER_MJS), "src/server.mjs must exist"
    src = _server_src()
    assert "Attachment not found" in src, (
        "src/server.mjs must contain 'Attachment not found' — "
        "the fix has not been applied to this file"
    )
    assert "Document not found" not in src, (
        "src/server.mjs must not contain 'Document not found' anywhere — "
        "all instances must be updated to 'Attachment not found'"
    )


def test_update_download_error_message__download_route_behavior_unchanged():
    # AC3: Status codes, headers, and successful-download behavior must remain unchanged
    src = _server_src()
    handler = _download_handler_block(src)
    # 404 must still be returned on missing file
    assert "404" in handler, (
        "server.mjs /download handler must still return 404 for missing files"
    )
    # Content-Type header for successful downloads must still be set
    assert re.search(r'Content-Type|content-type', handler), (
        "server.mjs /download handler must still set Content-Type header for successful downloads"
    )
    # Content-Disposition header must still be present
    assert re.search(r'Content-Disposition|content-disposition|attachment', handler), (
        "server.mjs /download handler must still set Content-Disposition (attachment) header"
    )
