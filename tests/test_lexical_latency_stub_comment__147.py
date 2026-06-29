"""
TDD tests for issue #147: Lexical latency stub records misleading ≈0ms in explain output.

AC1 — A comment exists on the lexical stage latency line in src/search/index.js
       noting that the value is stub-only and will reflect real cost once BM25 is implemented.
AC2 — The comment text clearly communicates both that the ≈0ms value is not a real measurement
       and that the value will change when BM25 is implemented.
AC3 — No functional behavior changed — the latency recording still occurs.
AC4 — The explain output continues to include the latencyMs field for the lexical stage
       (no regression from #131).
"""

import os
import re
import json
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEARCH_INDEX_JS = os.path.join(REPO_ROOT, "src", "search", "index.js")


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


def _read_search_index():
    with open(SEARCH_INDEX_JS) as f:
        return f.read()


# ---------------------------------------------------------------------------
# AC1 — Comment exists on/near the lexical latency line mentioning stub and BM25
# ---------------------------------------------------------------------------

def test_ac1_lexical_latency_line_exists():
    """The lexicalLatencyMs assignment must still exist in src/search/index.js."""
    src = _read_search_index()
    assert re.search(r"lexicalLatencyMs\s*=\s*performance\.now\(\)", src), (
        "src/search/index.js must contain lexicalLatencyMs = performance.now() - lexicalT0"
    )


def test_ac1_stub_comment_near_lexical_latency():
    """A comment containing 'stub' must appear on or adjacent to the lexicalLatencyMs line."""
    src = _read_search_index()
    lines = src.splitlines()
    latency_line_idx = None
    for i, line in enumerate(lines):
        if re.search(r"lexicalLatencyMs\s*=\s*performance\.now\(\)", line):
            latency_line_idx = i
            break
    assert latency_line_idx is not None, "lexicalLatencyMs assignment line not found"

    # Check the latency line itself or up to 2 lines above/below for 'stub'
    window_start = max(0, latency_line_idx - 2)
    window_end = min(len(lines), latency_line_idx + 3)
    window = "\n".join(lines[window_start:window_end])
    assert "stub" in window.lower(), (
        f"No 'stub' comment found near lexicalLatencyMs at line {latency_line_idx + 1}. "
        f"Context:\n{window}"
    )


def test_ac1_bm25_mentioned_near_lexical_latency():
    """A reference to 'BM25' must appear near the lexicalLatencyMs line."""
    src = _read_search_index()
    lines = src.splitlines()
    latency_line_idx = None
    for i, line in enumerate(lines):
        if re.search(r"lexicalLatencyMs\s*=\s*performance\.now\(\)", line):
            latency_line_idx = i
            break
    assert latency_line_idx is not None, "lexicalLatencyMs assignment line not found"

    window_start = max(0, latency_line_idx - 2)
    window_end = min(len(lines), latency_line_idx + 3)
    window = "\n".join(lines[window_start:window_end])
    assert "BM25" in window or "bm25" in window.lower(), (
        f"No 'BM25' reference found near lexicalLatencyMs at line {latency_line_idx + 1}. "
        f"Context:\n{window}"
    )


# ---------------------------------------------------------------------------
# AC2 — Comment communicates both: ≈0ms is not real, and value will change with BM25
# ---------------------------------------------------------------------------

def test_ac2_comment_indicates_not_real_measurement():
    """Comment near lexicalLatencyMs must convey that 0ms is not a real measurement."""
    src = _read_search_index()
    lines = src.splitlines()
    latency_line_idx = None
    for i, line in enumerate(lines):
        if re.search(r"lexicalLatencyMs\s*=\s*performance\.now\(\)", line):
            latency_line_idx = i
            break
    assert latency_line_idx is not None

    window_start = max(0, latency_line_idx - 2)
    window_end = min(len(lines), latency_line_idx + 3)
    window = "\n".join(lines[window_start:window_end]).lower()
    # Any of these phrases indicate the measurement is not real
    markers = ["no real", "not real", "stub", "placeholder", "no actual", "not actual"]
    assert any(m in window for m in markers), (
        "Comment near lexicalLatencyMs must indicate the value is not a real measurement. "
        f"Context:\n{window}"
    )


def test_ac2_comment_indicates_will_change_with_bm25():
    """Comment must indicate the value will reflect real cost when BM25 is implemented."""
    src = _read_search_index()
    lines = src.splitlines()
    latency_line_idx = None
    for i, line in enumerate(lines):
        if re.search(r"lexicalLatencyMs\s*=\s*performance\.now\(\)", line):
            latency_line_idx = i
            break
    assert latency_line_idx is not None

    window_start = max(0, latency_line_idx - 2)
    window_end = min(len(lines), latency_line_idx + 3)
    window = "\n".join(lines[window_start:window_end]).lower()
    # Phrase indicating future BM25 implementation will change this
    future_markers = ["when implemented", "once implemented", "will reflect", "when bm25"]
    assert any(m in window for m in future_markers), (
        "Comment must state the value will change when BM25 is implemented. "
        f"Context:\n{window}"
    )


# ---------------------------------------------------------------------------
# AC3 — Functional behavior unchanged: latency is still recorded
# ---------------------------------------------------------------------------

def test_ac3_lexical_latency_still_passed_to_record_explain_stage():
    """_recordExplainStage must still be called with lexicalLatencyMs (no regression)."""
    src = _read_search_index()
    assert re.search(
        r'_recordExplainStage\s*\([^)]*"lexical"[^)]*lexicalLatencyMs',
        src,
    ) or re.search(
        r"_recordExplainStage\s*\([^)]*'lexical'[^)]*lexicalLatencyMs",
        src,
    ), (
        "_recordExplainStage must still be called with 'lexical' stage and lexicalLatencyMs"
    )


def test_ac3_lexical_timer_starts_before_computation():
    """lexicalT0 = performance.now() must precede the lexical search try block."""
    src = _read_search_index()
    t0_match = list(re.finditer(r"lexicalT0\s*=\s*performance\.now\(\)", src))
    latency_match = list(re.finditer(r"lexicalLatencyMs\s*=\s*performance\.now\(\)\s*-\s*lexicalT0", src))
    assert t0_match, "lexicalT0 = performance.now() must exist"
    assert latency_match, "lexicalLatencyMs = performance.now() - lexicalT0 must exist"
    assert t0_match[0].start() < latency_match[0].start(), (
        "lexicalT0 must be assigned before lexicalLatencyMs is computed"
    )


# ---------------------------------------------------------------------------
# AC4 — Explain output still includes latencyMs for lexical stage (no regression)
# ---------------------------------------------------------------------------

def test_ac4_latency_ms_field_still_in_explain_structure():
    """The explain stage structure in source must still reference latencyMs."""
    src = _read_search_index()
    assert "latencyMs" in src, (
        "src/search/index.js must still contain 'latencyMs' in explain stage output"
    )


def test_ac4_searchdocuments_returns_latency_ms_in_lexical_stage():
    """With debug=true and hybridEnabled, explain stages must include latencyMs."""
    script = """
import { searchDocuments } from './src/search/index.js';
const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 10,
  hybridEnabled: true,
  hybridFusionWeight: 0.7,
  rerankEnabled: false,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
};
const results = await searchDocuments('test query', 10, null, cfg, true);
// Verify all explain stages have latencyMs (for any results that include lexical stage)
let allHaveLatency = true;
for (const r of results) {
  for (const stage of (r.explain ?? [])) {
    if (typeof stage.latencyMs !== 'number') {
      allHaveLatency = false;
      break;
    }
  }
}
process.stdout.write(JSON.stringify({ ok: allHaveLatency, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, (
        "All explain stage entries must have a numeric latencyMs field (no regression from #131)"
    )
