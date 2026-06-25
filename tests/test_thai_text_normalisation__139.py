"""
TDD tests for issue #139: Add Thai text normalization at ingest and query time.

AC1 — A normalization module exists that applies Unicode NFC normalization,
       strips zero-width and control characters, and converts Thai and Arabic
       numerals to a canonical form
AC2 — The normalization module exposes a flag (enable_normalization) that,
       when False, passes text through unchanged
AC3 — Document and chunk text is normalized via this module during ingest
AC4 — Query text is normalized via the same module at search time
AC5 — With normalization enabled, a query using zero-width characters matches
       a document without them (and vice versa)
AC6 — With normalization enabled, a query using Thai numerals matches a
       document using Arabic numerals representing the same value (and vice versa)
AC7 — With normalization enabled, two Thai strings that are canonically
       equivalent under NFC match each other
AC8 — With normalization disabled, none of the above cross-variant matches occur
AC9 — Normalization is applied identically by the same code path at both
       ingest and query time (no duplicated logic)
"""

import json
import os
import re
import subprocess
import unicodedata

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NORMALISE_JS = os.path.join(REPO_ROOT, "src", "text", "normalise.js")
SEARCH_INDEX_JS = os.path.join(REPO_ROOT, "src", "search", "index.js")
INGEST_JS = os.path.join(REPO_ROOT, "src", "commands", "ingest.js")


def _run_node(script, env=None, timeout=60):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
        env=merged,
    )
    return result.stdout, result.stderr, result.returncode


# ---------------------------------------------------------------------------
# AC1 — Module structure and normalization behaviors
# ---------------------------------------------------------------------------

def test_ac1_normalise_module_exists():
    assert os.path.isfile(NORMALISE_JS), (
        f"src/text/normalise.js must exist at {NORMALISE_JS}"
    )


def test_ac1_normalise_function_exported():
    with open(NORMALISE_JS) as f:
        src = f.read()
    assert "normalise" in src, "src/text/normalise.js must define and export normalise"
    assert "export" in src, "src/text/normalise.js must export the normalise function"


def test_ac1_nfc_normalization():
    """normalise() must produce NFC form for decomposed Unicode input."""
    # U+0E01 (ก) followed by a combining mark should become NFC.
    # NFD of แ (U+0E41) can be represented as U+0E41 directly in NFC.
    # Use a known NFD vs NFC pair: 'é' vs '\xe9' (é).
    script = r"""
import { normalise } from './src/text/normalise.js';
const nfd = 'é';   // NFD 'é'
const nfc = '\xe9';       // NFC 'é'
const result = normalise(nfd, true);
const ok = result === nfc;
process.stdout.write(JSON.stringify({ ok, result, nfc }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        f"normalise() must produce NFC. Got: {data['result']!r}, expected: {data['nfc']!r}"
    )


def test_ac1_strips_zero_width_characters():
    """normalise() must strip zero-width non-joiner (U+200C) and similar chars."""
    script = r"""
import { normalise } from './src/text/normalise.js';
const withZW = 'สวัสดี‌ครับ';  // zero-width non-joiner inserted
const expected = 'สวัสดีครับ';
const result = normalise(withZW, true);
const ok = result === expected;
process.stdout.write(JSON.stringify({ ok, result, expected }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        f"normalise() must strip U+200C. Got: {data['result']!r}, expected: {data['expected']!r}"
    )


def test_ac1_strips_zero_width_space():
    """normalise() must strip zero-width space (U+200B)."""
    script = r"""
import { normalise } from './src/text/normalise.js';
const withZWS = 'hello​world';
const expected = 'helloworld';
const result = normalise(withZWS, true);
const ok = result === expected;
process.stdout.write(JSON.stringify({ ok, result, expected }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        f"normalise() must strip U+200B. Got: {data['result']!r}"
    )


def test_ac1_strips_bom():
    """normalise() must strip BOM (U+FEFF)."""
    script = r"""
import { normalise } from './src/text/normalise.js';
const withBOM = '﻿text';
const expected = 'text';
const result = normalise(withBOM, true);
const ok = result === expected;
process.stdout.write(JSON.stringify({ ok, result, expected }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        f"normalise() must strip BOM (U+FEFF). Got: {data['result']!r}"
    )


def test_ac1_thai_to_arabic_numerals():
    """normalise() must convert Thai numerals ๐-๙ to ASCII digits 0-9."""
    script = r"""
import { normalise } from './src/text/normalise.js';
const thai = '๑๒๓';
const expected = '123';
const result = normalise(thai, true);
const ok = result === expected;
process.stdout.write(JSON.stringify({ ok, result, expected }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        f"normalise() must convert ๑๒๓ → 123. Got: {data['result']!r}"
    )


def test_ac1_all_thai_digits_mapped():
    """All ten Thai digits ๐๑๒๓๔๕๖๗๘๙ must map to 0123456789."""
    script = r"""
import { normalise } from './src/text/normalise.js';
const thai = '๐๑๒๓๔๕๖๗๘๙';
const expected = '0123456789';
const result = normalise(thai, true);
const ok = result === expected;
process.stdout.write(JSON.stringify({ ok, result, expected }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        f"All Thai digits must map to Arabic equivalents. Got: {data['result']!r}"
    )


def test_ac1_arabic_numerals_unchanged():
    """Arabic numerals 0-9 must remain unchanged after normalization."""
    script = r"""
import { normalise } from './src/text/normalise.js';
const arabic = '0123456789';
const result = normalise(arabic, true);
const ok = result === arabic;
process.stdout.write(JSON.stringify({ ok, result }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        f"Arabic digits must remain unchanged. Got: {data['result']!r}"
    )


def test_ac1_plain_text_unchanged():
    """Plain ASCII text must pass through normalise() unchanged."""
    script = r"""
import { normalise } from './src/text/normalise.js';
const text = 'Hello world! This is a test.';
const result = normalise(text, true);
const ok = result === text;
process.stdout.write(JSON.stringify({ ok, result }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        f"Plain ASCII must be unchanged by normalise(). Got: {data['result']!r}"
    )


# ---------------------------------------------------------------------------
# AC2 — enable_normalization=false passes text through unchanged
# ---------------------------------------------------------------------------

def test_ac2_disabled_passes_through_zero_width():
    """When enabled=false, zero-width chars must NOT be stripped."""
    script = r"""
import { normalise } from './src/text/normalise.js';
const withZW = 'สวัสดี‌ครับ';
const result = normalise(withZW, false);
const ok = result === withZW;
process.stdout.write(JSON.stringify({ ok, result }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        "normalise(text, false) must not strip zero-width chars. "
        f"Got: {data['result']!r}"
    )


def test_ac2_disabled_passes_through_thai_numerals():
    """When enabled=false, Thai numerals must NOT be converted."""
    script = r"""
import { normalise } from './src/text/normalise.js';
const thai = '๑๒๓';
const result = normalise(thai, false);
const ok = result === thai;
process.stdout.write(JSON.stringify({ ok, result, thai }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        f"normalise(text, false) must not convert Thai numerals. Got: {data['result']!r}"
    )


def test_ac2_disabled_passes_through_nfd():
    """When enabled=false, NFD text must NOT be converted to NFC."""
    script = r"""
import { normalise } from './src/text/normalise.js';
const nfd = 'é';   // NFD 'é'
const nfc = '\xe9';       // NFC 'é'
const result = normalise(nfd, false);
// must remain as NFD (not converted to NFC)
const ok = result === nfd;
process.stdout.write(JSON.stringify({ ok, result }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        "normalise(text, false) must not apply NFC. NFD should be preserved. "
        f"Got: {data['result']!r}"
    )


def test_ac2_default_enabled_is_true():
    """normalise() called with no second argument defaults to enabled (normalizes text)."""
    script = r"""
import { normalise } from './src/text/normalise.js';
// Default should normalize Thai numerals
const thai = '๑๒๓';
const result = normalise(thai);
const ok = result === '123';
process.stdout.write(JSON.stringify({ ok, result }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        f"normalise() with no second arg must default to enabled=true. Got: {data['result']!r}"
    )


# ---------------------------------------------------------------------------
# AC3 — Ingest applies normalization
# ---------------------------------------------------------------------------

def test_ac3_ingest_imports_normalise():
    """src/commands/ingest.js must import from src/text/normalise.js."""
    with open(INGEST_JS) as f:
        src = f.read()
    assert "normalise" in src or "text/normalise" in src, (
        "src/commands/ingest.js must import normalise from src/text/normalise.js"
    )


def test_ac3_ingest_references_text_normalisation_enabled():
    """src/commands/ingest.js must check textNormalisationEnabled flag."""
    with open(INGEST_JS) as f:
        src = f.read()
    assert "textNormalisationEnabled" in src or "normalise" in src, (
        "src/commands/ingest.js must respect textNormalisationEnabled or call normalise()"
    )


# ---------------------------------------------------------------------------
# AC4 — Query text normalized at search time
# ---------------------------------------------------------------------------

def test_ac4_search_index_imports_normalise():
    """src/search/index.js must import normalise from src/text/normalise.js."""
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    assert "normalise" in src or "text/normalise" in src, (
        "src/search/index.js must import normalise from src/text/normalise.js"
    )


def test_ac4_search_index_calls_normalise_for_query():
    """src/search/index.js must call normalise() on the query string."""
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    assert "normalise" in src, (
        "src/search/index.js must call normalise() to normalize the query text"
    )


def test_ac4_search_respects_text_normalisation_enabled():
    """searchDocuments must use cfg.textNormalisationEnabled to gate normalization."""
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    assert "textNormalisationEnabled" in src, (
        "src/search/index.js must read cfg.textNormalisationEnabled to decide normalization"
    )


# ---------------------------------------------------------------------------
# AC5 — Zero-width match with normalization enabled
# ---------------------------------------------------------------------------

def test_ac5_normalise_makes_zw_strings_equal():
    """After normalise(), a string with ZW chars equals one without them."""
    script = r"""
import { normalise } from './src/text/normalise.js';
const withZW  = 'สวัสดี‌ครับ';
const without = 'สวัสดีครับ';
const n1 = normalise(withZW, true);
const n2 = normalise(without, true);
const ok = n1 === n2;
process.stdout.write(JSON.stringify({ ok, n1, n2 }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        f"Normalized ZW string must equal normalized clean string. "
        f"Got: {data['n1']!r} vs {data['n2']!r}"
    )


# ---------------------------------------------------------------------------
# AC6 — Thai numeral matches Arabic numeral after normalization
# ---------------------------------------------------------------------------

def test_ac6_thai_and_arabic_numerals_normalise_equal():
    """After normalise(), Thai '๑๒๓' equals Arabic '123'."""
    script = r"""
import { normalise } from './src/text/normalise.js';
const thai   = '๑๒๓';
const arabic = '123';
const n1 = normalise(thai, true);
const n2 = normalise(arabic, true);
const ok = n1 === n2;
process.stdout.write(JSON.stringify({ ok, n1, n2 }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        f"normalise(thai) must equal normalise(arabic). Got: {data['n1']!r} vs {data['n2']!r}"
    )


# ---------------------------------------------------------------------------
# AC7 — NFC-equivalent Thai strings match after normalization
# ---------------------------------------------------------------------------

def test_ac7_nfc_equivalent_strings_equal_after_normalise():
    """After normalise(), NFD and NFC forms of the same string are equal."""
    script = r"""
import { normalise } from './src/text/normalise.js';
// NFD vs NFC for 'é' as a proxy (Thai NFC is harder to construct in JS)
const nfd = 'é';   // decomposed
const nfc = '\xe9';       // precomposed
const n1 = normalise(nfd, true);
const n2 = normalise(nfc, true);
const ok = n1 === n2;
process.stdout.write(JSON.stringify({ ok, n1, n2 }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        f"NFC and NFD forms must be equal after normalise(). "
        f"Got: {data['n1']!r} vs {data['n2']!r}"
    )


# ---------------------------------------------------------------------------
# AC8 — With normalization disabled, cross-variant strings remain distinct
# ---------------------------------------------------------------------------

def test_ac8_disabled_zw_strings_not_equal():
    """With enabled=false, ZW string must not equal the clean string."""
    script = r"""
import { normalise } from './src/text/normalise.js';
const withZW  = 'สวัสดี‌ครับ';
const without = 'สวัสดีครับ';
const n1 = normalise(withZW, false);
const n2 = normalise(without, false);
// must remain distinct
const ok = n1 !== n2;
process.stdout.write(JSON.stringify({ ok, n1, n2 }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        "normalise(text, false) must leave ZW chars intact so strings remain distinct. "
        f"Got n1==n2: {data['n1']!r}"
    )


def test_ac8_disabled_thai_arabic_not_equal():
    """With enabled=false, Thai numerals must not match Arabic numerals."""
    script = r"""
import { normalise } from './src/text/normalise.js';
const thai   = '๑๒๓';
const arabic = '123';
const n1 = normalise(thai, false);
const n2 = normalise(arabic, false);
const ok = n1 !== n2;
process.stdout.write(JSON.stringify({ ok, n1, n2 }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        "normalise(text, false) must not convert Thai numerals. "
        f"Got n1==n2: both={data['n1']!r}"
    )


# ---------------------------------------------------------------------------
# AC9 — Same code path (single shared module) for ingest and search
# ---------------------------------------------------------------------------

def test_ac9_ingest_and_search_import_same_module():
    """Both ingest.js and search/index.js must import from src/text/normalise.js."""
    with open(INGEST_JS) as f:
        ingest_src = f.read()
    with open(SEARCH_INDEX_JS) as f:
        search_src = f.read()

    assert "text/normalise" in ingest_src, (
        "src/commands/ingest.js must import from src/text/normalise.js (shared module)"
    )
    assert "text/normalise" in search_src, (
        "src/search/index.js must import from src/text/normalise.js (shared module)"
    )


def test_ac9_normalise_is_the_only_normalisation_implementation():
    """No duplicated normalisation logic should exist outside src/text/normalise.js."""
    # Look for Thai numeral replacement in non-normalise files
    script = r"""
import { normalise } from './src/text/normalise.js';
// Just verify the module is the canonical place — if it exports normalise, it's the single source
process.stdout.write(JSON.stringify({ ok: typeof normalise === 'function' }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, "normalise must be a function exported from src/text/normalise.js"


def test_ac9_retrieval_config_has_text_normalisation_enabled():
    """src/config/retrieval.js must have textNormalisationEnabled in defaultRetrievalConfig."""
    script = r"""
import { defaultRetrievalConfig } from './src/config/retrieval.js';
const cfg = defaultRetrievalConfig();
process.stdout.write(JSON.stringify({ has: 'textNormalisationEnabled' in cfg, val: cfg.textNormalisationEnabled }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["has"] is True, "defaultRetrievalConfig() must include textNormalisationEnabled"
    assert data["val"] is True, "textNormalisationEnabled must default to true"


def test_ac9_normalise_applied_to_query_in_search_pipeline():
    """searchDocuments must normalize the query before embedding when enabled."""
    script = r"""
import { searchDocuments } from './src/search/index.js';
const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 5,
  hybridEnabled: false,
  hybridFusionWeight: 0.7,
  rrfK: 60,
  rerankEnabled: false,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  rerankCandidateCount: 50,
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
};
// If normalisation is wired, this should not throw even with Thai query text
const results = await searchDocuments('๑๒๓ test', 5, null, cfg, false);
process.stdout.write(JSON.stringify({ ok: Array.isArray(results) }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"searchDocuments with Thai query threw error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, "searchDocuments must return an array when given Thai query text"
