"""
Acceptance tests for issue #140: Add Thai word-boundary chunking mode behind config flag

AC1 - A chunking_mode config option exists with at least two values: length (existing) and thai_word (new).
AC2 - When chunking_mode = thai_word, no chunk boundary falls mid-word for Thai text.
AC3 - Paragraph/newline boundaries are preferred as split points before word boundaries are consulted.
AC4 - The length-based mode continues to work exactly as before.
AC5 - Every chunk in either mode remains within the configured maximum character limit.
AC6 - If the Thai segmenter fails, system falls back to length-based splitting and logs a warning.
AC7 - Tests cover: mid-word split prevention, paragraph-boundary preference, length-cap enforcement,
      fallback behaviour, and length-mode regression.
"""

import json
import os
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUNKER_JS = os.path.join(REPO_ROOT, "src", "data", "chunker.js")
RETRIEVAL_JS = os.path.join(REPO_ROOT, "src", "config", "retrieval.js")


def _run_node(script, timeout=30, env=None):
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
        env=run_env,
    )
    return result.stdout, result.stderr, result.returncode


# ---------------------------------------------------------------------------
# AC1: chunking_mode config option with 'length' and 'thai_word' values
# ---------------------------------------------------------------------------


def test_ac1_chunking_mode_constants_exported():
    """AC1: chunker.js must export CHUNKING_MODE with 'length' and 'thai_word' values."""
    with open(CHUNKER_JS) as f:
        src = f.read()
    assert "CHUNKING_MODE" in src, "chunker.js must export CHUNKING_MODE"
    assert "length" in src, "CHUNKING_MODE must include 'length'"
    assert "thai_word" in src, "CHUNKING_MODE must include 'thai_word'"


def test_ac1_chunking_mode_field_in_retrieval_config():
    """AC1: retrieval.js must include chunkingMode in defaultRetrievalConfig()."""
    with open(RETRIEVAL_JS) as f:
        src = f.read()
    assert "chunkingMode" in src, "retrieval.js must include chunkingMode in config"


def test_ac1_default_chunking_mode_is_length():
    """AC1: defaultRetrievalConfig() must return chunkingMode='length' by default."""
    script = """
import { defaultRetrievalConfig } from './src/config/retrieval.js';
const cfg = defaultRetrievalConfig();
process.stdout.write(JSON.stringify({ chunkingMode: cfg.chunkingMode }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    assert result["chunkingMode"] == "length", (
        f"Default chunkingMode must be 'length', got '{result['chunkingMode']}'"
    )


def test_ac1_env_var_overrides_chunking_mode():
    """AC1: RETRIEVAL_CHUNKING_MODE env var must override chunkingMode to 'thai_word'."""
    script = """
import { defaultRetrievalConfig } from './src/config/retrieval.js';
const cfg = defaultRetrievalConfig();
process.stdout.write(JSON.stringify({ chunkingMode: cfg.chunkingMode }));
"""
    out, err, rc = _run_node(script, env={"RETRIEVAL_CHUNKING_MODE": "thai_word"})
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    assert result["chunkingMode"] == "thai_word", (
        f"RETRIEVAL_CHUNKING_MODE env var must set chunkingMode; got '{result['chunkingMode']}'"
    )


def test_ac1_chunking_mode_in_presets():
    """AC1: retrieval.js presets must include chunkingMode field."""
    script = """
import { PRESETS } from './src/config/retrieval.js';
const results = {};
for (const [name, preset] of Object.entries(PRESETS)) {
  results[name] = preset.chunkingMode ?? null;
}
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    for preset_name, mode in result.items():
        assert mode is not None, (
            f"Preset '{preset_name}' must include chunkingMode field"
        )


# ---------------------------------------------------------------------------
# AC2: Thai word segmenter used; no chunk boundary mid-word
# ---------------------------------------------------------------------------


def test_ac2_no_mid_word_split():
    """AC2: chunkDocumentThai must not split Thai text mid-word.

    Uses 'กระทรวง' (7 chars each) repeated 50 times. With chunkSize=20,
    the word segmenter should produce 14-char rawSegments (2 words).
    Since 14+1+14=29 > 20, no packing occurs, so chunks == rawSegments.
    Chunk boundary positions must all be in the segmenter's word-boundary set.
    """
    script = """
import { chunkDocumentThai } from './src/data/chunker.js';

// Check segmenter availability first
let segmenterAvailable = false;
try {
  const s = new Intl.Segmenter('th', { granularity: 'word' });
  segmenterAvailable = [...s.segment('กก')].length > 0;
} catch (_) {}

if (!segmenterAvailable) {
  process.stdout.write(JSON.stringify({ skipped: true }));
  process.exit(0);
}

const word = "กระทรวง";  // 7 chars
const text = word.repeat(50);  // 350 chars, no newlines
const article = { id: 'no-split-test', headline: 'H', details: text, attachment_url: '' };
const chunkSize = 20;
const chunks = chunkDocumentThai(article, chunkSize);

// Get canonical word boundaries from the segmenter
const segmenter = new Intl.Segmenter('th', { granularity: 'word' });
const segs = [...segmenter.segment(text)];
const wordBoundarySet = new Set(segs.map(s => s.index + s.segment.length));

// Reconstruct chunk boundary positions in original text.
// No newlines in text; chunkSize=20 prevents packing (14+1+14=29>20),
// so each chunk.details is a substring of the original text (no \\n added).
let pos = 0;
const badBoundaries = [];
for (let i = 0; i < chunks.length - 1; i++) {
  if (chunks[i].details.includes('\\n')) {
    // Packing happened — skip position check for this boundary
    pos += chunks[i].details.length;
    continue;
  }
  pos += chunks[i].details.length;
  if (!wordBoundarySet.has(pos)) {
    badBoundaries.push(pos);
  }
}

process.stdout.write(JSON.stringify({
  chunkCount: chunks.length,
  badBoundaries,
  sampleLengths: chunks.slice(0, 5).map(c => c.details.length),
}));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    if result.get("skipped"):
        pytest.skip("Intl.Segmenter not available in this Node.js build")
    assert result["chunkCount"] >= 2, "350-char Thai text with chunkSize=20 should produce multiple chunks"
    assert result["badBoundaries"] == [], (
        f"Chunk boundaries at positions {result['badBoundaries']} fall mid-word; "
        f"sample lengths: {result['sampleLengths']}"
    )


def test_ac2_chunkdocumentthai_exported():
    """AC2: chunker.js must export chunkDocumentThai function."""
    with open(CHUNKER_JS) as f:
        src = f.read()
    assert "export function chunkDocumentThai" in src or "export { chunkDocumentThai" in src, (
        "chunker.js must export chunkDocumentThai"
    )


# ---------------------------------------------------------------------------
# AC3: Paragraph/newline boundaries preferred over word boundaries
# ---------------------------------------------------------------------------


def test_ac3_paragraph_boundary_preferred_over_word_boundary():
    """AC3: Paragraphs that fit within chunkSize are each kept as a chunk boundary.

    Two paragraphs (70 chars + 60 chars). Together (70+1+60=131) exceed chunkSize=100,
    so they must be split — and the split must be at the paragraph boundary.
    """
    script = """
import { chunkDocumentThai } from './src/data/chunker.js';

const para1 = "ก".repeat(70);  // 70 chars
const para2 = "ก".repeat(60);  // 60 chars
// Joined: 70+1+60=131 > chunkSize=100 → must split at paragraph boundary
const text = para1 + "\\n\\n" + para2;
const article = { id: 'para-pref-test', headline: 'H', details: text, attachment_url: '' };
const chunks = chunkDocumentThai(article, 100);

process.stdout.write(JSON.stringify({
  chunkCount: chunks.length,
  firstMatchesPara1: chunks[0]?.details === para1,
  secondMatchesPara2: chunks[1]?.details === para2,
  chunkTexts: chunks.map(c => c.details.length),
}));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    assert result["chunkCount"] == 2, (
        f"Two paragraphs (70+60 chars) with chunkSize=100 should produce exactly 2 chunks; "
        f"got {result['chunkCount']}"
    )
    assert result["firstMatchesPara1"], (
        "First chunk must be exactly para1 — paragraph boundary must be respected as split point"
    )
    assert result["secondMatchesPara2"], (
        "Second chunk must be exactly para2 — paragraph boundary must be respected as split point"
    )


def test_ac3_segmenter_not_invoked_for_short_paragraphs():
    """AC3: Word segmenter is only invoked for paragraphs that exceed chunkSize."""
    script = """
import { chunkDocumentThai } from './src/data/chunker.js';

let invocations = 0;
const factory = () => {
  invocations++;
  return new Intl.Segmenter('th', { granularity: 'word' });
};

// Three paragraphs each 20 chars; chunkSize=100 → all fit without segmenter
const text = "ก".repeat(20) + "\\n" + "ก".repeat(20) + "\\n" + "ก".repeat(20);
const article = { id: 'no-seg-test', headline: 'H', details: text, attachment_url: '' };
const chunks = chunkDocumentThai(article, 100, { _segmenterFactory: factory });

process.stdout.write(JSON.stringify({ invocations, chunkCount: chunks.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    assert result["invocations"] == 0, (
        f"Segmenter factory must not be invoked when all paragraphs fit within chunkSize; "
        f"got {result['invocations']} invocations"
    )


def test_ac3_long_paragraph_split_by_segmenter_not_at_arbitrary_char():
    """AC3: A paragraph exceeding chunkSize is split by the word segmenter, not at an arbitrary char."""
    script = """
import { chunkDocumentThai } from './src/data/chunker.js';

let segmenterUsed = false;
const factory = () => {
  segmenterUsed = true;
  return new Intl.Segmenter('th', { granularity: 'word' });
};

// One long paragraph (500 chars > chunkSize=100) — segmenter MUST be invoked
const text = "ก".repeat(500);
const article = { id: 'long-para-test', headline: 'H', details: text, attachment_url: '' };
const chunks = chunkDocumentThai(article, 100, { _segmenterFactory: factory });

process.stdout.write(JSON.stringify({
  segmenterUsed,
  chunkCount: chunks.length,
  maxLen: Math.max(...chunks.map(c => c.details.length)),
}));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    assert result["segmenterUsed"], (
        "Segmenter must be invoked when a paragraph exceeds chunkSize"
    )
    assert result["chunkCount"] >= 2, "Long paragraph should produce multiple chunks"


# ---------------------------------------------------------------------------
# AC4: Length mode unchanged (regression)
# ---------------------------------------------------------------------------


def test_ac4_length_mode_produces_same_chunks():
    """AC4: chunkDocument (length mode) produces same results as before for Thai text."""
    script = """
import { chunkDocument, CHUNK_SIZE, CHUNK_OVERLAP } from './src/data/chunker.js';

const text = "ก".repeat(2000);
const article = { id: 'length-regression', headline: 'H', details: text, attachment_url: '' };
const chunks = chunkDocument(article);

const stride = CHUNK_SIZE - CHUNK_OVERLAP;
// Expected: ceil((2000 - CHUNK_OVERLAP) / stride) chunks
const expectedCount = Math.ceil((text.length - CHUNK_OVERLAP) / stride);

process.stdout.write(JSON.stringify({
  chunkCount: chunks.length,
  expectedCount,
  firstLen: chunks[0]?.details.length,
  chunkSize: CHUNK_SIZE,
  overlap: CHUNK_OVERLAP,
  // Verify overlap: end of first chunk == start of second chunk
  overlapCheck: chunks.length >= 2
    ? chunks[0].details.slice(-CHUNK_OVERLAP) === chunks[1].details.slice(0, CHUNK_OVERLAP)
    : true,
}));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    assert result["firstLen"] == result["chunkSize"], (
        f"Length mode: first chunk must be exactly CHUNK_SIZE={result['chunkSize']} chars"
    )
    assert result["chunkCount"] == result["expectedCount"], (
        f"Length mode: expected {result['expectedCount']} chunks, got {result['chunkCount']}"
    )
    assert result["overlapCheck"], (
        "Length mode: adjacent chunks must share CHUNK_OVERLAP chars"
    )


def test_ac4_length_mode_not_affected_by_chunking_mode_constant():
    """AC4: CHUNKING_MODE export must not change chunkDocument's length-mode behaviour."""
    script = """
import { chunkDocument, CHUNKING_MODE, CHUNK_SIZE } from './src/data/chunker.js';

// Verify CHUNKING_MODE is exported without changing chunkDocument behaviour
const text = "X".repeat(1000);
const article = { id: 'no-change-test', headline: 'H', details: text, attachment_url: '' };
const chunks = chunkDocument(article);
process.stdout.write(JSON.stringify({
  hasCHUNKING_MODE: typeof CHUNKING_MODE === 'object',
  lengthValue: CHUNKING_MODE?.LENGTH,
  thaiWordValue: CHUNKING_MODE?.THAI_WORD,
  chunkCount: chunks.length,
  firstLen: chunks[0]?.details.length,
  chunkSize: CHUNK_SIZE,
}));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    assert result["hasCHUNKING_MODE"], "CHUNKING_MODE must be exported as an object"
    assert result["lengthValue"] == "length", "CHUNKING_MODE.LENGTH must equal 'length'"
    assert result["thaiWordValue"] == "thai_word", "CHUNKING_MODE.THAI_WORD must equal 'thai_word'"
    assert result["firstLen"] == result["chunkSize"], (
        "chunkDocument must still produce CHUNK_SIZE-length chunks after CHUNKING_MODE is added"
    )


# ---------------------------------------------------------------------------
# AC5: Length cap enforcement in both modes
# ---------------------------------------------------------------------------


def test_ac5_thai_word_mode_length_cap_enforced():
    """AC5: chunkDocumentThai must never produce a chunk exceeding chunkSize."""
    script = """
import { chunkDocumentThai } from './src/data/chunker.js';

const text = "กระทรวงสาธารณสุข".repeat(30);  // ~480 chars
const article = { id: 'cap-test', headline: 'H', details: text, attachment_url: '' };
const chunkSize = 50;
const chunks = chunkDocumentThai(article, chunkSize);

const oversized = chunks.filter(c => c.details.length > chunkSize);
process.stdout.write(JSON.stringify({
  chunkCount: chunks.length,
  oversizedCount: oversized.length,
  maxLen: Math.max(...chunks.map(c => c.details.length)),
  chunkSize,
}));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    assert result["oversizedCount"] == 0, (
        f"Thai word mode must never exceed chunkSize={result['chunkSize']}; "
        f"found {result['oversizedCount']} oversized chunks (max was {result['maxLen']})"
    )


def test_ac5_hard_cap_when_no_word_boundary_near_limit():
    """AC5: Chunk is capped at chunkSize even when no natural word break is near the limit."""
    script = """
import { chunkDocumentThai } from './src/data/chunker.js';

// chunkSize=10, but "กระทรวง" is 7 chars → 2 words = 14 > 10
// So each chunk should have at most 1 word (7 chars) — always ≤ 10
const text = "กระทรวง".repeat(20);  // 140 chars
const article = { id: 'hard-cap-test', headline: 'H', details: text, attachment_url: '' };
const chunkSize = 10;
const chunks = chunkDocumentThai(article, chunkSize);

const oversized = chunks.filter(c => c.details.length > chunkSize);
process.stdout.write(JSON.stringify({
  oversizedCount: oversized.length,
  lengths: chunks.map(c => c.details.length),
  chunkSize,
}));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    assert result["oversizedCount"] == 0, (
        f"Must cap at chunkSize={result['chunkSize']} even when no word boundary is near limit; "
        f"found oversized chunks. All lengths: {result['lengths']}"
    )


def test_ac5_empty_article_produces_no_chunks():
    """AC5: Empty article must produce no chunks in either mode."""
    script = """
import { chunkDocument, chunkDocumentThai } from './src/data/chunker.js';
const article = { id: 'empty', headline: 'H', details: '', attachment_url: '' };
const lengthChunks = chunkDocument(article);
const thaiChunks = chunkDocumentThai(article, 400);
process.stdout.write(JSON.stringify({
  lengthCount: lengthChunks.length,
  thaiCount: thaiChunks.length,
}));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    assert result["lengthCount"] == 0, "Empty article must produce 0 length-mode chunks"
    assert result["thaiCount"] == 0, "Empty article must produce 0 thai-word-mode chunks"


# ---------------------------------------------------------------------------
# AC6: Fallback to length mode when segmenter fails
# ---------------------------------------------------------------------------


def test_ac6_fallback_on_segmenter_failure():
    """AC6: When segmenter factory throws, system falls back to length-based chunking."""
    script = """
import { chunkDocumentThai, chunkDocument } from './src/data/chunker.js';

const text = "ก".repeat(2000);
const article = { id: 'fallback-test', headline: 'H', details: text, attachment_url: '' };
const chunkSize = 400;

const warnings = [];
const chunks = chunkDocumentThai(article, chunkSize, {
  _segmenterFactory: () => { throw new Error('Segmenter library missing'); },
  warn: (msg) => warnings.push(msg),
});

const lengthChunks = chunkDocument(article, chunkSize);

process.stdout.write(JSON.stringify({
  chunkCount: chunks.length,
  lengthChunkCount: lengthChunks.length,
  warningsCount: warnings.length,
  firstWarning: warnings[0] ?? null,
  firstChunkLen: chunks[0]?.details.length,
  lengthFirstChunkLen: lengthChunks[0]?.details.length,
}));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    assert result["chunkCount"] == result["lengthChunkCount"], (
        f"Fallback must produce same chunk count as length mode; "
        f"got {result['chunkCount']} vs {result['lengthChunkCount']}"
    )
    assert result["warningsCount"] >= 1, (
        "Fallback must log at least one warning when segmenter fails"
    )
    assert result["firstWarning"] is not None, "Warning message must not be null"


def test_ac6_warning_message_contains_fallback_notice():
    """AC6: Warning message must mention the fallback to length-based chunking."""
    script = """
import { chunkDocumentThai } from './src/data/chunker.js';

const text = "ก".repeat(500);
const article = { id: 'warn-test', headline: 'H', details: text, attachment_url: '' };
const warnings = [];
chunkDocumentThai(article, 100, {
  _segmenterFactory: () => { throw new Error('ICU not available'); },
  warn: (msg) => warnings.push(msg),
});
process.stdout.write(JSON.stringify({ warnings }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    assert result["warnings"], "Must produce at least one warning"
    combined = " ".join(result["warnings"]).lower()
    assert "fallback" in combined or "length" in combined or "unavailable" in combined, (
        f"Warning must mention fallback or unavailability; got: {result['warnings']}"
    )


def test_ac6_no_unhandled_exception_on_fallback():
    """AC6: Fallback must not raise an unhandled exception."""
    script = """
import { chunkDocumentThai } from './src/data/chunker.js';

const article = { id: 'ex-test', headline: 'H', details: 'สวัสดี'.repeat(100), attachment_url: '' };
let threw = false;
let chunks = [];
try {
  chunks = chunkDocumentThai(article, 50, {
    _segmenterFactory: () => { throw new Error('Library missing'); },
    warn: () => {},
  });
} catch (e) {
  threw = true;
}
process.stdout.write(JSON.stringify({ threw, chunkCount: chunks.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    assert not result["threw"], "Fallback must not raise an unhandled exception"
    assert result["chunkCount"] > 0, "Fallback must still produce chunks"
