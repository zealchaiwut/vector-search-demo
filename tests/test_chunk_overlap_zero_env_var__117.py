"""
Tests for issue #117: CHUNK_OVERLAP=0 silently ignored due to falsy short-circuit.

Bug: parseInt("0", 10) returns 0 (falsy), so `0 || default` resolves to the default
instead of the env var value. Users who want non-overlapping chunks (CHUNK_OVERLAP=0)
or very small chunks (CHUNK_SIZE via any falsy parse result) cannot achieve it.

Acceptance criteria:
  AC1 — CHUNK_OVERLAP=0 env var produces non-overlapping chunks (zero overlap), not the default 80.
  AC2 — CHUNK_SIZE env var non-zero values continue to work correctly (regression guard).
  AC3 — CHUNK_OVERLAP env var non-zero values continue to work correctly (regression guard).
  AC4 — The same falsy-safe fix is applied to the CHUNK_SIZE line for consistency.
"""

import json
import os
import re
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUNKER_JS = os.path.join(REPO_ROOT, "src", "data", "chunker.js")


def _run_node(script, env_overrides=None, timeout=30):
    run_env = os.environ.copy()
    if env_overrides:
        run_env.update(env_overrides)
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
# AC1: CHUNK_OVERLAP=0 must produce non-overlapping chunks
# ---------------------------------------------------------------------------

def test_ac1_chunk_overlap_zero_env_produces_no_overlap():
    """AC1: Setting CHUNK_OVERLAP=0 must result in zero overlap between consecutive chunks.

    Uses distinct characters at each position so that an accidental overlap (shared text)
    is distinguishable from two different chunks that happen to start/end with the same value.
    With CHUNK_OVERLAP=0 the stride equals CHUNK_SIZE, so chunk[1] starts exactly where
    chunk[0] ends — the boundary character of chunk[0] must NOT appear at the start of chunk[1].
    """
    script = """
import { chunkDocument } from './src/data/chunker.js';
// 1200 chars with unique characters at each position (cycling A-Z repeatedly)
// so we can tell if adjacent chunks share content
const text = Array.from({length: 1200}, (_, i) => String.fromCharCode(65 + (i % 26))).join('');
const article = { id: 'overlap-zero', headline: 'H', details: text, attachment_url: '' };
const chunks = chunkDocument(article);
if (chunks.length < 2) {
  process.stdout.write(JSON.stringify({ error: 'too_few_chunks', count: chunks.length }));
  process.exit(0);
}
// With CHUNK_OVERLAP=0, stride == chunkSize, so chunk[1].details[0] == text[chunk0.length]
// With overlap=80, stride == chunkSize - 80, so chunk[1].details[0] == text[chunk0.length - 80]
// We check: the 10-char boundary of chunk[0] end must NOT match start of chunk[1]
const endSlice = chunks[0].details.slice(-10);
const startSlice = chunks[1].details.slice(0, 10);
process.stdout.write(JSON.stringify({
  count: chunks.length,
  totalCoverage: chunks.reduce((s, c) => s + c.details.length, 0),
  textLen: text.length,
  // True means overlap is present (bug); false means no overlap (fix applied)
  overlapDetected: endSlice === startSlice,
  endSlice,
  startSlice,
}));
"""
    out, err, rc = _run_node(script, env_overrides={"CHUNK_OVERLAP": "0"})
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    assert "error" not in result, f"Chunking error: {result}"
    assert not result["overlapDetected"], (
        f"CHUNK_OVERLAP=0 must produce non-overlapping chunks; "
        f"the last 10 chars of chunk 0 ('{result.get('endSlice')}') must differ from "
        f"the first 10 chars of chunk 1 ('{result.get('startSlice')}') — "
        f"if they match, the env var was silently ignored (falsy || bug still present). "
        f"result={result}"
    )


def test_ac1_chunk_overlap_zero_total_coverage_equals_text_length():
    """AC1: With CHUNK_OVERLAP=0 and text that divides evenly, coverage equals text length."""
    script = """
import { chunkDocument } from './src/data/chunker.js';
// Exactly 1200 chars with CHUNK_SIZE=400 and CHUNK_OVERLAP=0 → 3 chunks of 400 each
const text = "B".repeat(1200);
const article = { id: 'coverage-test', headline: 'H', details: text, attachment_url: '' };
const chunks = chunkDocument(article);
const totalCoverage = chunks.reduce((s, c) => s + c.details.length, 0);
process.stdout.write(JSON.stringify({
  count: chunks.length,
  totalCoverage,
  textLen: text.length,
}));
"""
    out, err, rc = _run_node(script, env_overrides={"CHUNK_OVERLAP": "0", "CHUNK_SIZE": "400"})
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    # With no overlap, 1200 chars / 400 per chunk = 3 chunks, coverage = 1200 (no double-counting)
    assert result["totalCoverage"] == result["textLen"], (
        f"With CHUNK_OVERLAP=0, total coverage must equal text length (no double-counting). "
        f"Got coverage={result['totalCoverage']}, textLen={result['textLen']}. "
        f"If coverage > textLen, CHUNK_OVERLAP=0 was silently ignored."
    )


# ---------------------------------------------------------------------------
# AC2: Non-zero CHUNK_SIZE env var continues to work (regression guard)
# ---------------------------------------------------------------------------

def test_ac2_chunk_size_env_override_nonzero():
    """AC2: CHUNK_SIZE=200 env var overrides the default 400 correctly."""
    script = """
import { chunkDocument } from './src/data/chunker.js';
const text = "C".repeat(1000);
const article = { id: 'sz-test', headline: 'H', details: text, attachment_url: '' };
const chunks = chunkDocument(article);
process.stdout.write(JSON.stringify({
  count: chunks.length,
  maxChunkLen: Math.max(...chunks.map(c => c.details.length)),
}));
"""
    out, err, rc = _run_node(script, env_overrides={"CHUNK_SIZE": "200", "CHUNK_OVERLAP": "0"})
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    assert result["maxChunkLen"] <= 200, (
        f"CHUNK_SIZE=200 must cap chunk length at 200; got maxChunkLen={result['maxChunkLen']}"
    )
    assert result["count"] >= 5, (
        f"1000 chars with CHUNK_SIZE=200 and no overlap should yield ≥ 5 chunks; "
        f"got {result['count']}"
    )


# ---------------------------------------------------------------------------
# AC3: Non-zero CHUNK_OVERLAP env var continues to work (regression guard)
# ---------------------------------------------------------------------------

def test_ac3_chunk_overlap_env_override_nonzero():
    """AC3: CHUNK_OVERLAP=50 env var produces overlapping chunks with 50-char overlap."""
    script = """
import { chunkDocument } from './src/data/chunker.js';
// 1200 chars, CHUNK_SIZE=400, CHUNK_OVERLAP=50
const text = Array.from({length: 1200}, (_, i) => String.fromCharCode(65 + (i % 26))).join('');
const article = { id: 'ov-nonzero', headline: 'H', details: text, attachment_url: '' };
const chunks = chunkDocument(article);
if (chunks.length < 2) {
  process.stdout.write(JSON.stringify({ error: 'too_few_chunks', count: chunks.length }));
  process.exit(0);
}
// End of chunk0 last 50 chars == start of chunk1 first 50 chars
const endSlice = chunks[0].details.slice(-50);
const startSlice = chunks[1].details.slice(0, 50);
process.stdout.write(JSON.stringify({
  count: chunks.length,
  overlapMatches: endSlice === startSlice,
  endSlice,
  startSlice,
}));
"""
    out, err, rc = _run_node(script, env_overrides={"CHUNK_SIZE": "400", "CHUNK_OVERLAP": "50"})
    assert rc == 0, f"Node error: {err}\n{out}"
    result = json.loads(out)
    assert "error" not in result, f"Chunking error: {result}"
    assert result["overlapMatches"], (
        f"CHUNK_OVERLAP=50 must produce 50-char overlap between adjacent chunks. "
        f"End of chunk0: '{result.get('endSlice')}' != start of chunk1: '{result.get('startSlice')}'"
    )


# ---------------------------------------------------------------------------
# AC4: Both CHUNK_SIZE and CHUNK_OVERLAP lines use explicit finite-number check
# ---------------------------------------------------------------------------

def test_ac4_chunk_size_uses_finite_number_check():
    """AC4: The CHUNK_SIZE parsing line must not use `||` falsy short-circuit."""
    with open(CHUNKER_JS) as f:
        src = f.read()
    # The old pattern: parseInt(...) || chunkSize
    # Detect if the sz line still uses the falsy || pattern
    sz_line_match = re.search(r"const sz\s*=.*?;", src)
    assert sz_line_match, "chunker.js must have a 'const sz = ...' line"
    sz_line = sz_line_match.group(0)
    assert "||" not in sz_line, (
        f"CHUNK_SIZE parsing must not use `||` falsy short-circuit. "
        f"Found: {sz_line!r}. "
        f"Replace with Number.isFinite check so CHUNK_SIZE=0 is not silently ignored."
    )


def test_ac4_chunk_overlap_uses_finite_number_check():
    """AC4: The CHUNK_OVERLAP parsing line must not use `||` falsy short-circuit."""
    with open(CHUNKER_JS) as f:
        src = f.read()
    ov_line_match = re.search(r"const ov\s*=.*?;", src)
    assert ov_line_match, "chunker.js must have a 'const ov = ...' line"
    ov_line = ov_line_match.group(0)
    assert "||" not in ov_line, (
        f"CHUNK_OVERLAP parsing must not use `||` falsy short-circuit. "
        f"Found: {ov_line!r}. "
        f"Replace with Number.isFinite check so CHUNK_OVERLAP=0 is not silently ignored."
    )


def test_ac4_uses_number_is_finite_or_equivalent():
    """AC4: The env var parsing must use Number.isFinite or an equivalent explicit guard."""
    with open(CHUNKER_JS) as f:
        src = f.read()
    # Must use explicit finite check — either Number.isFinite or Number.isNaN guard
    has_finite_check = (
        "Number.isFinite" in src
        or "isFinite(" in src
        or "!isNaN(" in src
    )
    assert has_finite_check, (
        "chunker.js must use Number.isFinite (or equivalent) to guard env var parsing "
        "instead of the falsy `||` short-circuit. "
        "This ensures CHUNK_OVERLAP=0 and CHUNK_SIZE=0 are honoured."
    )
