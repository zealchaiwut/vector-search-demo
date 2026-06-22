"""Tests for Word (.docx) document upload alongside PDF."""
import io
import os
import re
import subprocess
import zipfile

import httpx
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCX_MODULE = os.path.join(REPO_ROOT, "src", "docx", "index.js")
SERVER_MJS = os.path.join(REPO_ROOT, "src", "server.mjs")
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")
UAT_BASE_URL = os.environ.get("UAT_BASE_URL", "http://localhost:8001")


def _make_minimal_docx_bytes():
    """Build a minimal valid .docx (OOXML zip) with two paragraphs."""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    document = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Word upload test headline</w:t></w:r></w:p>
    <w:p><w:r><w:t>Body text for docx upload test.</w:t></w:r></w:p>
  </w:body>
</w:document>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document)
    return buf.getvalue()


def test_docx_module_exists():
    assert os.path.isfile(DOCX_MODULE), f"missing {DOCX_MODULE}"


def test_docx_module_exports_extract_docx_text():
    with open(DOCX_MODULE) as f:
        src = f.read()
    assert "export" in src and "extractDocxText" in src


def test_server_imports_docx_extractor():
    with open(SERVER_MJS) as f:
        src = f.read()
    assert "extractDocxText" in src
    assert "extractUploadText" in src or ".docx" in src


def test_server_rejects_unsupported_upload_extension():
    with open(SERVER_MJS) as f:
        src = f.read()
    assert "Unsupported file type" in src


def test_html_accepts_docx_upload():
    with open(INDEX_HTML) as f:
        src = f.read()
    assert ".docx" in src
    assert re.search(
        r'accept\s*=\s*["\'][^"\']*\.docx[^"\']*["\']',
        src,
        re.IGNORECASE,
    )


def test_extract_docx_text_node():
    docx_bytes = _make_minimal_docx_bytes()
    import base64

    b64 = base64.b64encode(docx_bytes).decode()
    script = f"""
import {{ extractDocxText }} from './src/docx/index.js';
const buf = Buffer.from('{b64}', 'base64');
const text = await extractDocxText(buf);
if (!text.includes('Word upload test headline')) throw new Error('missing headline: ' + text);
if (!text.includes('Body text for docx upload test')) throw new Error('missing body: ' + text);
console.log('ok');
"""
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.fixture
def client():
    try:
        with httpx.Client(timeout=3.0) as probe:
            probe.get(UAT_BASE_URL + "/")
    except Exception:
        pytest.skip(f"Live server not reachable at {UAT_BASE_URL}")
    with httpx.Client(base_url=UAT_BASE_URL, timeout=120.0) as c:
        yield c


def test_live_upload_docx_returns_article_json(client):
    docx_bytes = _make_minimal_docx_bytes()
    resp = client.post(
        "/api/upload-pdf",
        files={"file": ("test.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "headline" in data and "details" in data and "attachment_url" in data
    assert "Word upload test headline" in data["headline"] or "Word upload test headline" in data["details"]
    assert data["attachment_url"].startswith("/uploads/")

    get_resp = client.get(data["attachment_url"])
    assert get_resp.status_code == 200
    assert "wordprocessingml" in get_resp.headers.get("content-type", "")
