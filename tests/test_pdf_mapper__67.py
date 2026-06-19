"""Tests for issue #67: Map extracted PDF text to add-article JSON shape

Acceptance Criteria:
  AC1  - Mapper module exists at src/pdf/ and exports a mapPdfToArticle function
  AC2  - headline: metadata title (when present) → first non-empty line → file name
  AC3  - details: body text with leading/trailing whitespace removed per line and
          multiple consecutive blank lines collapsed to a single blank line
  AC4  - attachment_url: "" when no URL provided; provided URL when supplied
  AC5  - Thai Unicode characters preserved without corruption
  AC6  - Mapping a sample Thai text (with or without title metadata) produces a
          valid add-article object where headline and details are non-empty strings
  AC7  - Unit tests cover: (a) headline from metadata, (b) headline fallback to
          first line, (c) headline fallback to file name, (d) whitespace normalisation,
          (e) Thai character preservation, (f) attachment_url empty and populated
"""
import json
import os
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPPER_MODULE = os.path.join(REPO_ROOT, "src", "pdf", "mapper.js")
NODE_TIMEOUT = 30


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
# AC1 — module file exists and exports mapPdfToArticle
# ---------------------------------------------------------------------------


def test_pdf_mapper__module_exists():
    """AC1: src/pdf/mapper.js exists"""
    assert os.path.isfile(MAPPER_MODULE), (
        f"src/pdf/mapper.js not found at {MAPPER_MODULE}"
    )


def test_pdf_mapper__exports_map_function():
    """AC1: mapper.js exports a mapPdfToArticle function"""
    with open(MAPPER_MODULE) as f:
        content = f.read()
    assert "mapPdfToArticle" in content and "export" in content, (
        "mapper.js must export a mapPdfToArticle function"
    )


# ---------------------------------------------------------------------------
# AC2 — headline derivation: metadata → first line → file name
# ---------------------------------------------------------------------------


def test_pdf_mapper__headline_from_metadata_title():
    """AC2/AC7a: headline is set to the metadata title when present"""
    script = r"""
import { mapPdfToArticle } from './src/pdf/mapper.js';

const result = mapPdfToArticle('First line of body\nMore content here.', {
  title: 'Document Title From Metadata',
});

if (result.headline !== 'Document Title From Metadata') {
  process.stderr.write(`Expected "Document Title From Metadata", got: ${JSON.stringify(result.headline)}\n`);
  process.exit(1);
}
process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Test failed.\nstdout: {out}\nstderr: {err}"
    assert out.strip() == "ok"


def test_pdf_mapper__headline_falls_back_to_first_line():
    """AC2/AC7b: headline falls back to first non-empty line when no title metadata"""
    script = r"""
import { mapPdfToArticle } from './src/pdf/mapper.js';

const result = mapPdfToArticle('\n\nFirst Real Line\nSecond line of content.');

if (result.headline !== 'First Real Line') {
  process.stderr.write(`Expected "First Real Line", got: ${JSON.stringify(result.headline)}\n`);
  process.exit(1);
}
process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Test failed.\nstdout: {out}\nstderr: {err}"
    assert out.strip() == "ok"


def test_pdf_mapper__headline_falls_back_to_filename():
    """AC2/AC7c: headline falls back to file name when both title and text are absent"""
    script = r"""
import { mapPdfToArticle } from './src/pdf/mapper.js';

const result = mapPdfToArticle('', {
  fileName: 'document.pdf',
});

if (result.headline !== 'document.pdf') {
  process.stderr.write(`Expected "document.pdf", got: ${JSON.stringify(result.headline)}\n`);
  process.exit(1);
}
process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Test failed.\nstdout: {out}\nstderr: {err}"
    assert out.strip() == "ok"


# ---------------------------------------------------------------------------
# AC3 — whitespace normalisation in details
# ---------------------------------------------------------------------------


def test_pdf_mapper__whitespace_normalisation():
    """AC3/AC7d: details collapses multiple blank lines and trims per-line whitespace"""
    script = r"""
import { mapPdfToArticle } from './src/pdf/mapper.js';

const rawText = [
  '  Line one with leading spaces  ',
  '',
  '',
  '',
  '  Line two after triple blank  ',
  '',
  'Line three',
].join('\n');

const result = mapPdfToArticle(rawText, { title: 'Title' });

const lines = result.details.split('\n');

// No line should have leading or trailing whitespace
for (const line of lines) {
  if (line !== line.trim()) {
    process.stderr.write(`Line has leading/trailing whitespace: ${JSON.stringify(line)}\n`);
    process.exit(1);
  }
}

// No run of more than one consecutive blank line
let consecutiveBlanks = 0;
for (const line of lines) {
  if (line === '') {
    consecutiveBlanks++;
    if (consecutiveBlanks > 1) {
      process.stderr.write(`Found more than one consecutive blank line in details\n`);
      process.exit(1);
    }
  } else {
    consecutiveBlanks = 0;
  }
}

// Content lines must be present and trimmed
if (!result.details.includes('Line one with leading spaces')) {
  process.stderr.write(`Expected trimmed "Line one with leading spaces" in details\n`);
  process.exit(1);
}

process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Test failed.\nstdout: {out}\nstderr: {err}"
    assert out.strip() == "ok"


# ---------------------------------------------------------------------------
# AC4 — attachment_url: empty string or provided URL
# ---------------------------------------------------------------------------


def test_pdf_mapper__attachment_url_empty_by_default():
    """AC4/AC7f: attachment_url is "" when no URL is provided"""
    script = r"""
import { mapPdfToArticle } from './src/pdf/mapper.js';

const result = mapPdfToArticle('Some body text.', { title: 'Title' });

if (result.attachment_url !== '') {
  process.stderr.write(`Expected attachment_url to be "", got: ${JSON.stringify(result.attachment_url)}\n`);
  process.exit(1);
}
process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Test failed.\nstdout: {out}\nstderr: {err}"
    assert out.strip() == "ok"


def test_pdf_mapper__attachment_url_populated_when_provided():
    """AC4/AC7f: attachment_url equals the supplied URL when one is provided"""
    script = r"""
import { mapPdfToArticle } from './src/pdf/mapper.js';

const url = 'https://example.com/uploads/doc.pdf';
const result = mapPdfToArticle('Body text.', {
  title: 'Title',
  attachmentUrl: url,
});

if (result.attachment_url !== url) {
  process.stderr.write(`Expected attachment_url "${url}", got: ${JSON.stringify(result.attachment_url)}\n`);
  process.exit(1);
}
process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Test failed.\nstdout: {out}\nstderr: {err}"
    assert out.strip() == "ok"


# ---------------------------------------------------------------------------
# AC5 — Thai Unicode preserved
# ---------------------------------------------------------------------------


def test_pdf_mapper__thai_characters_preserved():
    """AC5/AC7e: Thai Unicode characters are preserved without corruption"""
    script = r"""
import { mapPdfToArticle } from './src/pdf/mapper.js';

const thaiText = 'ภาษาไทย\nข้อความภาษาไทย\nเนื้อหาเพิ่มเติม';
const result = mapPdfToArticle(thaiText);

// headline should be first Thai line
if (!result.headline.includes('ภาษาไทย')) {
  process.stderr.write(`Thai headline lost. Got: ${JSON.stringify(result.headline)}\n`);
  process.exit(1);
}

// details must contain intact Thai characters
if (!result.details.includes('ข้อความภาษาไทย')) {
  process.stderr.write(`Thai text corrupted in details. Got: ${JSON.stringify(result.details)}\n`);
  process.exit(1);
}

process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Test failed.\nstdout: {out}\nstderr: {err}"
    assert out.strip() == "ok"


# ---------------------------------------------------------------------------
# AC6 — Thai PDF produces valid add-article object
# ---------------------------------------------------------------------------


def test_pdf_mapper__thai_pdf_with_title_produces_valid_article():
    """AC6: Thai PDF with title metadata returns valid add-article object"""
    script = r"""
import { mapPdfToArticle } from './src/pdf/mapper.js';

const thaiBody = 'ข้อความภาษาไทย\nเนื้อหาเพิ่มเติมในเอกสาร';
const result = mapPdfToArticle(thaiBody, {
  title: 'เอกสารภาษาไทย',
  attachmentUrl: '',
});

const ok = (
  typeof result.headline === 'string' && result.headline.length > 0 &&
  typeof result.details === 'string' && result.details.length > 0 &&
  typeof result.attachment_url === 'string'
);

if (!ok) {
  process.stderr.write(`Invalid add-article object: ${JSON.stringify(result)}\n`);
  process.exit(1);
}
process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Test failed.\nstdout: {out}\nstderr: {err}"
    assert out.strip() == "ok"


def test_pdf_mapper__thai_pdf_without_title_produces_valid_article():
    """AC6: Thai PDF without title metadata returns valid add-article object"""
    script = r"""
import { mapPdfToArticle } from './src/pdf/mapper.js';

const thaiBody = 'เอกสารทดสอบ\nข้อความภาษาไทยเพิ่มเติม';
const result = mapPdfToArticle(thaiBody);

const ok = (
  typeof result.headline === 'string' && result.headline.length > 0 &&
  typeof result.details === 'string' && result.details.length > 0 &&
  typeof result.attachment_url === 'string'
);

if (!ok) {
  process.stderr.write(`Invalid add-article object (no title): ${JSON.stringify(result)}\n`);
  process.exit(1);
}
process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Test failed.\nstdout: {out}\nstderr: {err}"
    assert out.strip() == "ok"
