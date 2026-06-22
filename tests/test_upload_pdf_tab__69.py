"""Tests for issue #69: Add Upload PDF Tab with Extraction and Article Creation

Acceptance Criteria:
  AC1  - A new Upload PDF tab is visible and accessible in app navigation
  AC2  - The tab contains a file upload control that accepts PDF files only
  AC3  - Uploading a PDF triggers a POST request to POST /api/upload-pdf
  AC4  - The upload endpoint receives the PDF, runs extractor and mapper, returns
         article JSON (headline, details, attachment_url)
  AC5  - The uploaded PDF is stored on the server and served at /uploads/<filename>
  AC6  - attachment_url in the returned JSON points to the correct static route
  AC7  - The returned fields are displayed in an editable form after extraction
  AC8  - A Confirm button submits the (possibly edited) JSON to the article-creation
         endpoint to create the article
  AC9  - A progress/loading indicator is shown from PDF submission until result returns
  AC10 - On extraction failure, a clear error message is displayed; UI does not hang
  AC11 - A confirmed article is discoverable via search
  AC12 - Clicking the attachment_url link opens the uploaded PDF in the browser
"""
import os
import re
import subprocess

import httpx
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_MJS = os.path.join(REPO_ROOT, "src", "server.mjs")
INDEX_HTML = os.path.join(REPO_ROOT, "public", "index.html")
UAT_BASE_URL = os.environ.get("UAT_BASE_URL", "http://localhost:8001")

NODE_TIMEOUT = 60


def _server_src():
    with open(SERVER_MJS) as f:
        return f.read()


def _html_src():
    with open(INDEX_HTML) as f:
        return f.read()


def _run_node(script, timeout=NODE_TIMEOUT):
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
    )
    return result.stdout, result.stderr, result.returncode


# ---------------------------------------------------------------------------
# AC1 — Upload PDF tab exists in HTML
# ---------------------------------------------------------------------------

def test_ac1_upload_pdf_tab_exists_in_nav():
    """AC1: index.html has an 'Upload PDF' tab button in the navigation."""
    src = _html_src()
    assert re.search(r"Upload PDF|upload-pdf|upload_pdf", src, re.IGNORECASE), \
        "No 'Upload PDF' tab found in index.html navigation"


def test_ac1_upload_pdf_tab_has_correct_role():
    """AC1: Upload PDF tab button has role='tab' for accessibility."""
    src = _html_src()
    assert re.search(
        r'role\s*=\s*["\']tab["\'].*Upload PDF|Upload PDF.*role\s*=\s*["\']tab["\']',
        src, re.IGNORECASE | re.DOTALL
    ) or (
        "Upload PDF" in src and 'role="tab"' in src
    ), "Upload PDF tab must have role='tab'"


def test_ac1_upload_pdf_panel_exists():
    """AC1: A panel (tabpanel) corresponding to the Upload PDF tab exists."""
    src = _html_src()
    assert re.search(r'panel-upload|upload-pdf.*panel|id.*upload', src, re.IGNORECASE), \
        "No Upload PDF panel found in index.html"


# ---------------------------------------------------------------------------
# AC2 — File input accepts PDFs only
# ---------------------------------------------------------------------------

def test_ac2_file_input_accepts_pdf():
    """AC2: Upload PDF panel has a file input with accept='.pdf' or 'application/pdf'."""
    src = _html_src()
    assert (
        re.search(r'accept\s*=\s*["\'][^"\']*\.pdf[^"\']*["\']', src, re.IGNORECASE)
        or re.search(r'accept\s*=\s*["\']application/pdf["\']', src, re.IGNORECASE)
    ), "File input must have accept='.pdf' or accept='application/pdf'"


# ---------------------------------------------------------------------------
# AC3 — JS posts to /api/upload-pdf
# ---------------------------------------------------------------------------

def test_ac3_js_posts_to_upload_pdf_endpoint():
    """AC3: JS sends a request to /api/upload-pdf when a PDF is uploaded."""
    src = _html_src()
    assert "/api/upload-pdf" in src, \
        "index.html JS must reference /api/upload-pdf for the upload endpoint"


def test_ac3_js_uses_post_method_for_upload():
    """AC3: The upload request uses POST method."""
    src = _html_src()
    # Should have both /api/upload-pdf and POST nearby
    assert re.search(r"POST.*upload-pdf|upload-pdf.*POST|method.*POST.*upload|upload.*method.*POST",
                     src, re.IGNORECASE | re.DOTALL), \
        "Upload must use POST method to /api/upload-pdf"


def test_ac3_js_uses_formdata_for_upload():
    """AC3: JS uses FormData to send the PDF file."""
    src = _html_src()
    assert "FormData" in src, \
        "JS must use FormData to POST the PDF file"


# ---------------------------------------------------------------------------
# AC4 — Server endpoint exists and handles PDF extraction
# ---------------------------------------------------------------------------

def test_ac4_server_has_upload_pdf_route():
    """AC4: server.mjs handles POST /api/upload-pdf."""
    src = _server_src()
    assert "/api/upload-pdf" in src, \
        "server.mjs must handle POST /api/upload-pdf"


def test_ac4_server_imports_pdf_extractor():
    """AC4: server.mjs imports extractPdfText from src/pdf."""
    src = _server_src()
    assert re.search(r"extractPdfText|from.*pdf", src), \
        "server.mjs must import the PDF extractor"


def test_ac4_server_imports_pdf_mapper():
    """AC4: server.mjs imports mapPdfToArticle from src/pdf/mapper."""
    src = _server_src()
    assert re.search(r"mapPdfToArticle|from.*mapper", src), \
        "server.mjs must import the PDF mapper"


def test_ac4_server_returns_headline_details_attachment():
    """AC4: The upload endpoint returns headline, details, and attachment_url."""
    src = _server_src()
    for field in ("headline", "details", "attachment_url"):
        assert field in src, \
            f"server.mjs upload endpoint must return '{field}' in JSON response"


def test_ac4_upload_pdf_does_not_persist_article():
    """Upload must be extract-only; article is created when user clicks Confirm."""
    src = _server_src()
    upload_match = re.search(
        r'pathname === "/api/upload-pdf"[\s\S]*?(?=\n  // GET /uploads/)',
        src,
    )
    assert upload_match, "Could not locate POST /api/upload-pdf handler in server.mjs"
    block = upload_match.group(0)
    assert "upsertRows" not in block, (
        "POST /api/upload-pdf must not call upsertRows — that creates a duplicate before Confirm"
    )
    assert "chunkDocument" not in block, (
        "POST /api/upload-pdf must not chunk/embed — extraction only until Confirm"
    )


# ---------------------------------------------------------------------------
# AC5 — Uploaded PDF stored and served at /uploads/<filename>
# ---------------------------------------------------------------------------

def test_ac5_server_stores_uploads_in_directory():
    """AC5: server.mjs writes uploaded PDFs to an uploads directory."""
    src = _server_src()
    assert re.search(r"uploads|UPLOADS", src), \
        "server.mjs must store uploads in a dedicated directory"


def test_ac5_server_serves_uploads_route():
    """AC5: server.mjs serves files at /uploads/ path."""
    src = _server_src()
    assert "/uploads/" in src or "uploads" in src, \
        "server.mjs must serve uploaded files at /uploads/<filename>"


def test_ac5_server_has_uploads_dir_constant():
    """AC5: server.mjs defines an UPLOADS_DIR constant."""
    src = _server_src()
    assert re.search(r"UPLOADS_DIR|uploadsDir|uploads_dir", src, re.IGNORECASE), \
        "server.mjs must define an uploads directory path constant"


# ---------------------------------------------------------------------------
# AC6 — attachment_url points to /uploads/<filename>
# ---------------------------------------------------------------------------

def test_ac6_server_sets_attachment_url_to_uploads_path():
    """AC6: server.mjs builds attachment_url as /uploads/<filename>."""
    src = _server_src()
    assert re.search(r"attachment_url.*uploads|/uploads.*attachment", src, re.DOTALL), \
        "server.mjs must set attachment_url to the /uploads/<filename> path"


# ---------------------------------------------------------------------------
# AC7 — Returned fields displayed in editable form
# ---------------------------------------------------------------------------

def test_ac7_html_has_editable_headline_field():
    """AC7: Upload PDF panel includes an editable headline input field."""
    src = _html_src()
    assert re.search(r'pdf.*headline|headline.*pdf|upload.*headline|pdf-headline', src, re.IGNORECASE), \
        "Upload PDF panel must have an editable headline field"


def test_ac7_html_has_editable_details_field():
    """AC7: Upload PDF panel includes an editable details textarea."""
    src = _html_src()
    assert re.search(r'pdf.*details|details.*pdf|upload.*details|pdf-details', src, re.IGNORECASE), \
        "Upload PDF panel must have an editable details field"


def test_ac7_html_has_attachment_url_display():
    """AC7: Upload PDF panel displays the attachment_url field."""
    src = _html_src()
    assert re.search(r'pdf.*attachment|attachment.*pdf|upload.*attachment', src, re.IGNORECASE), \
        "Upload PDF panel must display the attachment_url field"


# ---------------------------------------------------------------------------
# AC8 — Confirm button submits to article-creation endpoint
# ---------------------------------------------------------------------------

def test_ac8_html_has_confirm_button():
    """AC8: Upload PDF panel includes a Confirm button."""
    src = _html_src()
    assert re.search(r'Confirm|confirm', src), \
        "Upload PDF panel must include a Confirm button"


def test_ac8_js_confirm_posts_to_articles():
    """AC8: Confirm button POSTs to /articles to create the article."""
    src = _html_src()
    assert re.search(r"Confirm.*articles|articles.*Confirm|confirm.*POST.*articles|/articles.*confirm",
                     src, re.IGNORECASE | re.DOTALL), \
        "Confirm button must submit to the /articles endpoint"


# ---------------------------------------------------------------------------
# AC9 — Loading indicator
# ---------------------------------------------------------------------------

def test_ac9_html_has_loading_indicator():
    """AC9: Upload PDF panel includes a loading/progress indicator element."""
    src = _html_src()
    has_indicator = bool(re.search(
        r'loading|spinner|progress|uploading|extracting',
        src, re.IGNORECASE
    ))
    assert has_indicator, \
        "Upload PDF panel must include a loading/progress indicator"


def test_ac9_js_shows_indicator_on_submit():
    """AC9: JS shows the loading indicator when the PDF is submitted."""
    src = _html_src()
    # Should have something that shows/enables the loading state
    assert re.search(r'loading|spinner|progress', src, re.IGNORECASE), \
        "JS must manage a loading indicator during PDF extraction"


# ---------------------------------------------------------------------------
# AC10 — Error handling
# ---------------------------------------------------------------------------

def test_ac10_html_has_error_display_element():
    """AC10: Upload PDF panel includes an element to display extraction errors."""
    src = _html_src()
    assert re.search(r'pdf.*error|error.*pdf|upload.*error|pdf-error|pdf-feedback', src, re.IGNORECASE), \
        "Upload PDF panel must have an error display element"


def test_ac10_js_handles_failed_extraction():
    """AC10: JS catches errors from the upload endpoint and shows a message."""
    src = _html_src()
    # Must have both error handling (try/catch) and error display
    has_try_catch = bool(re.search(r"try\s*\{.*catch\s*\(", src, re.DOTALL))
    has_error_display = bool(re.search(r"error", src, re.IGNORECASE))
    assert has_try_catch and has_error_display, \
        "JS must catch upload errors and display a human-readable error message"


def test_ac10_server_returns_error_on_non_pdf():
    """AC10: server.mjs returns an error response when extraction fails."""
    src = _server_src()
    # Must have error handling in the upload handler
    assert re.search(r"422|500|error.*extraction|extraction.*error|catch.*upload|upload.*catch",
                     src, re.IGNORECASE | re.DOTALL), \
        "server.mjs must return an error response when PDF extraction fails"


# ---------------------------------------------------------------------------
# Live server tests (require UAT_BASE_URL)
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    try:
        with httpx.Client(timeout=3.0) as probe:
            probe.get(UAT_BASE_URL + "/")
    except Exception:
        pytest.skip(f"Live server not reachable at {UAT_BASE_URL} — skipping live tests")
    with httpx.Client(base_url=UAT_BASE_URL, timeout=120.0) as c:
        yield c


def _make_minimal_pdf_bytes():
    """Create a minimal valid PDF with embedded text (no OCR needed)."""
    script = r"""
import { PDFDocument, rgb, StandardFonts } from 'pdf-lib';

const pdfDoc = await PDFDocument.create();
const page = pdfDoc.addPage([595, 842]);
const font = await pdfDoc.embedFont(StandardFonts.Helvetica);
page.drawText('Thai article test headline', {
  x: 50, y: 750, size: 16, font, color: rgb(0, 0, 0),
});
page.drawText('This is the body text of the test article for issue 69.', {
  x: 50, y: 700, size: 12, font, color: rgb(0, 0, 0),
});
const bytes = await pdfDoc.save();
process.stdout.write(Buffer.from(bytes).toString('base64'));
"""
    out = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=30,
    ).stdout
    import base64
    return base64.b64decode(out)


def test_ac4_live_upload_pdf_returns_article_json(client):
    """AC4: POST /api/upload-pdf with a valid PDF returns article JSON."""
    pdf_bytes = _make_minimal_pdf_bytes()
    resp = client.post(
        "/api/upload-pdf",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200, \
        f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert "headline" in data, f"Response missing 'headline': {data}"
    assert "details" in data, f"Response missing 'details': {data}"
    assert "attachment_url" in data, f"Response missing 'attachment_url': {data}"
    assert isinstance(data["headline"], str) and len(data["headline"]) > 0, \
        f"'headline' must be a non-empty string: {data}"
    assert isinstance(data["details"], str) and len(data["details"]) > 0, \
        f"'details' must be a non-empty string: {data}"


def test_ac5_live_uploaded_pdf_served_at_uploads_route(client):
    """AC5: After upload, the PDF is accessible at its /uploads/<filename> URL."""
    pdf_bytes = _make_minimal_pdf_bytes()
    upload_resp = client.post(
        "/api/upload-pdf",
        files={"file": ("serve_test.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
    data = upload_resp.json()
    attachment_url = data.get("attachment_url", "")

    assert attachment_url.startswith("/uploads/"), \
        f"attachment_url must start with /uploads/, got: {attachment_url!r}"

    get_resp = client.get(attachment_url)
    assert get_resp.status_code == 200, \
        f"GET {attachment_url} returned {get_resp.status_code} — uploaded PDF not served"
    assert get_resp.headers.get("content-type", "").startswith("application/pdf"), \
        f"Expected application/pdf content-type, got: {get_resp.headers.get('content-type')}"


def test_ac6_live_attachment_url_matches_storage(client):
    """AC6: attachment_url in JSON response points to the stored file."""
    pdf_bytes = _make_minimal_pdf_bytes()
    resp = client.post(
        "/api/upload-pdf",
        files={"file": ("url_test.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200
    url = resp.json().get("attachment_url", "")
    assert url, "attachment_url must not be empty"
    assert url.startswith("/uploads/"), \
        f"attachment_url must be a /uploads/ path, got: {url!r}"

    # File must be retrievable at that URL
    file_resp = client.get(url)
    assert file_resp.status_code == 200, \
        f"File not found at attachment_url {url!r}: {file_resp.status_code}"


def test_ac10_live_non_pdf_body_returns_error(client):
    """AC10: Sending non-PDF data returns an error response."""
    resp = client.post(
        "/api/upload-pdf",
        files={"file": ("not-a-pdf.pdf", b"not a pdf at all %^&", "application/pdf")},
    )
    assert resp.status_code in (400, 415, 422, 500), \
        f"Expected an error status for invalid PDF, got {resp.status_code}"
    data = resp.json()
    assert "error" in data, f"Error response must have 'error' field: {data}"


def test_ac11_live_confirmed_article_findable_via_search(client):
    """AC11: Article created via Confirm (POST /articles with extracted data) is findable."""
    pdf_bytes = _make_minimal_pdf_bytes()
    upload_resp = client.post(
        "/api/upload-pdf",
        files={"file": ("search_test.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_resp.status_code == 200
    extracted = upload_resp.json()

    unique_term = "xqz69uniquepdftest"
    create_resp = client.post("/articles", json={
        "headline": f"{extracted['headline']} {unique_term}",
        "details": extracted["details"],
        "attachment_url": extracted["attachment_url"],
    })
    assert create_resp.status_code == 201, \
        f"Article creation failed: {create_resp.status_code} {create_resp.text}"
    created_id = create_resp.json()["id"]

    search_resp = client.get("/search", params={"q": unique_term})
    assert search_resp.status_code == 200
    results = search_resp.json().get("results", [])
    ids = [r["id"] for r in results]
    assert created_id in ids, \
        f"Created article {created_id!r} not found in search: {ids}"


def test_ac4_upload_alone_does_not_create_article(client):
    """Upload & Extract alone must not add an article — only Confirm creates one."""
    before_resp = client.get("/articles")
    assert before_resp.status_code == 200
    before_count = len(before_resp.json().get("articles", []))

    pdf_bytes = _make_minimal_pdf_bytes()
    upload_resp = client.post(
        "/api/upload-pdf",
        files={"file": ("no_persist_test.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"

    after_resp = client.get("/articles")
    assert after_resp.status_code == 200
    after_count = len(after_resp.json().get("articles", []))
    assert after_count == before_count, (
        f"Upload alone must not create an article; before={before_count}, after={after_count}"
    )


def test_ac4_live_upload_pdf_quoted_boundary(client):
    """Quoted boundary= in Content-Type must not break multipart parsing."""
    import uuid
    pdf_bytes = _make_minimal_pdf_bytes()
    boundary = "----WebKitFormBoundary" + uuid.uuid4().hex[:16]
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="quoted.pdf"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode() + pdf_bytes + f"\r\n--{boundary}--\r\n".encode()
    resp = client.post(
        "/api/upload-pdf",
        content=body,
        headers={"Content-Type": f'multipart/form-data; boundary="{boundary}"'},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "headline" in data and "details" in data and "attachment_url" in data
