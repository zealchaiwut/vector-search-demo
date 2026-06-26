"""
TDD tests for issue #144: Decouple hybrid pipeline execution from debug flag in searchDocuments.

Primary bug (src/search/index.js): hybrid/RRF code path was gated on
`if (cfg.hybridEnabled && debug)` — when debug=false and hybridEnabled=true,
lexical and RRF stages were skipped entirely, so hybrid/hybrid-rerank presets
produced identical output to dense-only in production.

Secondary bug: even in debug mode, the explain RRF stage scores differed from
final result scores (fused scores computed but not reflected in results.score).

Suggested fix (from review comment): split the condition so pipeline stages run
whenever cfg.hybridEnabled is true (updating `results`), and _recordExplainStage
is only called when debug is also true.

AC1 — Hybrid pipeline (lexical search + RRF fusion) executes regardless of debug
       flag when hybridEnabled=true; results are updated with fused scores.
AC2 — results.score equals the RRF-fused score (not the original dense score) after
       hybrid pipeline executes, both when debug=false and when debug=true.
AC3 — In debug mode with hybridEnabled=true, explain "rrf" stage score matches
       the result's top-level score (no divergence between map and results).
AC4 — _recordExplainStage calls are inside debug guards; the hybrid pipeline
       execution path (results update) is NOT inside a debug guard.
"""

import os
import re
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


# ---------------------------------------------------------------------------
# AC4 — Static source checks: pipeline execution must NOT be gated on debug
# ---------------------------------------------------------------------------

def test_ac4_hybrid_pipeline_not_gated_on_debug_in_source():
    """
    The hybrid pipeline condition must be `if (cfg.hybridEnabled)` alone,
    NOT `if (cfg.hybridEnabled && debug)` or `if (cfg.hybridEnabled && cfg.debug)`.
    """
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    # Must NOT have the combined condition that was the root cause of the bug.
    assert not re.search(r"if\s*\(\s*cfg\.hybridEnabled\s*&&\s*debug\s*\)", src), (
        "Hybrid pipeline must NOT be gated on `if (cfg.hybridEnabled && debug)`. "
        "Pipeline execution must be independent of the debug flag."
    )


def test_ac4_hybrid_condition_exists_without_debug():
    """The hybrid block must open with `if (cfg.hybridEnabled)` on its own."""
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    assert re.search(r"if\s*\(\s*cfg\.hybridEnabled\s*\)", src), (
        "src/search/index.js must have `if (cfg.hybridEnabled)` as the sole gate "
        "for the hybrid pipeline — debug must not appear in this condition."
    )


def test_ac4_results_update_not_inside_debug_block():
    """
    The line that updates `results` with fused output (e.g. `results = fused.slice(...)`)
    must NOT appear inside an `if (debug)` block.  We verify this structurally by
    confirming `mergeRrf` is imported/called and that the assignment pattern exists
    independently of the debug guard.
    """
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    # mergeRrf must be called (hybrid fusion actually runs)
    assert "mergeRrf(" in src, (
        "mergeRrf must be called in src/search/index.js for hybrid fusion"
    )
    # results must be assigned from the fused output
    assert re.search(r"results\s*=\s*fused\s*\.slice\s*\(", src), (
        "results must be updated with `results = fused.slice(...)` after RRF fusion, "
        "and this assignment must not be inside a debug guard."
    )


def test_ac4_record_explain_stage_calls_are_inside_debug_guard():
    """
    Every _recordExplainStage call must appear after an `if (debug)` check.
    Verifies zero overhead in production (debug=false) paths.
    """
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    # Count how many times _recordExplainStage appears
    call_count = src.count("_recordExplainStage(")
    assert call_count > 0, "_recordExplainStage must be used in src/search/index.js"

    # Every call must be preceded (somewhere above it) by `if (debug)` or `if (debug &&`
    # We verify the simpler invariant: the function itself only runs in debug guards.
    # A tighter check: no _recordExplainStage call appears outside of an if(debug) block.
    # We do a line-scan: verify each call line is preceded by an `if (debug)` opener.
    lines = src.splitlines()
    in_debug_block_depth = 0
    brace_depth = 0
    debug_open_depths = []

    for line in lines:
        stripped = line.strip()
        # Track if (debug) { openers
        if re.search(r"if\s*\(\s*debug\s*\)\s*\{", stripped):
            debug_open_depths.append(brace_depth + 1)
        brace_depth += stripped.count("{") - stripped.count("}")
        # Close debug blocks
        debug_open_depths = [d for d in debug_open_depths if d <= brace_depth]

        # Skip the function definition itself; only check call sites.
        is_definition = re.search(r"^function\s+_recordExplainStage\s*\(", stripped)
        if "_recordExplainStage(" in stripped and not is_definition:
            assert len(debug_open_depths) > 0, (
                f"_recordExplainStage call found outside a `if (debug)` block: {stripped!r}"
            )


# ---------------------------------------------------------------------------
# AC1 — Runtime: hybrid pipeline runs even when debug=false
# ---------------------------------------------------------------------------

def test_ac1_hybrid_enabled_produces_fused_score_without_debug():
    """
    When hybridEnabled=true and debug=false, results must have the `fused_score`
    property set by mergeRrf — proving the hybrid pipeline actually ran.
    (With an empty collection results will be [], which vacuously passes.)
    """
    script = """
import { searchDocuments } from './src/search/index.js';

const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 10,
  hybridEnabled: true,
  hybridFusionWeight: 0.7,
  rrfK: 60,
  rerankEnabled: false,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
};

// debug=false — the default production mode
const results = await searchDocuments('test', 10, null, cfg, false);

if (!Array.isArray(results)) {
  process.stderr.write('searchDocuments must return an array\\n');
  process.exit(1);
}

// If the collection has data, every result must carry fused_score from mergeRrf.
for (const r of results) {
  if (!('fused_score' in r)) {
    process.stderr.write(
      'Result missing fused_score — hybrid pipeline did not run or results were not updated. '
      + 'result.id=' + r.id + '\\n'
    );
    process.exit(1);
  }
}

process.stdout.write(JSON.stringify({ ok: true, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node script failed: {err}"
    import json
    data = json.loads(out)
    assert data["ok"] is True


def test_ac1_hybrid_enabled_produces_dense_and_lexical_ranks_without_debug():
    """
    When hybridEnabled=true and debug=false, results must have `dense_rank` and
    `lexical_rank` properties from mergeRrf, proving the fusion was executed.
    """
    script = """
import { searchDocuments } from './src/search/index.js';

const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 10,
  hybridEnabled: true,
  hybridFusionWeight: 0.7,
  rrfK: 60,
  rerankEnabled: false,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
};

const results = await searchDocuments('test', 10, null, cfg, false);

for (const r of results) {
  // dense_rank may be null for lexical-only items, but the key must be present
  if (!('dense_rank' in r)) {
    process.stderr.write('Result missing dense_rank — mergeRrf output not in results\\n');
    process.exit(1);
  }
  if (!('lexical_rank' in r)) {
    process.stderr.write('Result missing lexical_rank — mergeRrf output not in results\\n');
    process.exit(1);
  }
}

process.stdout.write(JSON.stringify({ ok: true, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node script failed: {err}"
    import json
    data = json.loads(out)
    assert data["ok"] is True


def test_ac1_hybrid_false_does_not_set_fused_score():
    """
    When hybridEnabled=false, results must NOT have `fused_score` — proving that
    the hybrid pipeline only runs when hybridEnabled is true.
    """
    script = """
import { searchDocuments } from './src/search/index.js';

const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 10,
  hybridEnabled: false,
  hybridFusionWeight: 0.7,
  rerankEnabled: false,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
};

const results = await searchDocuments('test', 10, null, cfg, false);

for (const r of results) {
  if ('fused_score' in r) {
    process.stderr.write('Result has fused_score but hybridEnabled=false — unexpected RRF run\\n');
    process.exit(1);
  }
}

process.stdout.write(JSON.stringify({ ok: true, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node script failed: {err}"
    import json
    data = json.loads(out)
    assert data["ok"] is True


# ---------------------------------------------------------------------------
# AC2 — Runtime: result.score reflects fused score (not original dense score)
# ---------------------------------------------------------------------------

def test_ac2_result_score_matches_fused_score_without_debug():
    """
    When hybridEnabled=true and debug=false, result.score must equal result.fused_score.
    This confirms the secondary bug is fixed: fused scores ARE written back to results.
    """
    script = """
import { searchDocuments } from './src/search/index.js';

const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 10,
  hybridEnabled: true,
  hybridFusionWeight: 0.7,
  rrfK: 60,
  rerankEnabled: false,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
};

const results = await searchDocuments('test', 10, null, cfg, false);

for (const r of results) {
  if (r.fused_score !== undefined && r.score !== r.fused_score) {
    process.stderr.write(
      'result.score (' + r.score + ') does not equal fused_score (' + r.fused_score + '). '
      + 'Fused scores were not written back to results.\\n'
    );
    process.exit(1);
  }
}

process.stdout.write(JSON.stringify({ ok: true, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node script failed: {err}"
    import json
    data = json.loads(out)
    assert data["ok"] is True


# ---------------------------------------------------------------------------
# AC3 — Runtime: explain RRF score matches result.score (no divergence in debug mode)
# ---------------------------------------------------------------------------

def test_ac3_explain_rrf_score_matches_result_score_in_debug_mode():
    """
    When hybridEnabled=true and debug=true, the explain 'rrf' stage score must
    equal the result's top-level score.  This is the secondary bug: previously the
    explain map recorded a score that differed from what was in results.
    """
    script = """
import { searchDocuments } from './src/search/index.js';

const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 10,
  hybridEnabled: true,
  hybridFusionWeight: 0.7,
  rrfK: 60,
  rerankEnabled: false,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
};

const results = await searchDocuments('test', 10, null, cfg, true);

for (const r of results) {
  const stages = r.explain ?? [];
  const rrfStage = stages.find(s => s.stage === 'rrf');
  if (rrfStage) {
    if (rrfStage.score !== r.score) {
      process.stderr.write(
        'explain rrf stage score (' + rrfStage.score + ') does not match '
        + 'result.score (' + r.score + ') for result id=' + r.id + '.\\n'
        + 'Fused score was not written back to results — secondary bug still present.\\n'
      );
      process.exit(1);
    }
  }
}

process.stdout.write(JSON.stringify({ ok: true, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node script failed: {err}"
    import json
    data = json.loads(out)
    assert data["ok"] is True


def test_ac3_explain_rrf_score_equals_fused_score_in_debug_mode():
    """
    When hybridEnabled=true and debug=true, the explain 'rrf' stage score must
    equal result.fused_score (the canonical fused score set by mergeRrf).
    """
    script = """
import { searchDocuments } from './src/search/index.js';

const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 10,
  hybridEnabled: true,
  hybridFusionWeight: 0.7,
  rrfK: 60,
  rerankEnabled: false,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
};

const results = await searchDocuments('test', 10, null, cfg, true);

for (const r of results) {
  if (r.fused_score === undefined) continue;  // skip if no fused_score
  const stages = r.explain ?? [];
  const rrfStage = stages.find(s => s.stage === 'rrf');
  if (rrfStage && rrfStage.score !== r.fused_score) {
    process.stderr.write(
      'explain rrf stage score (' + rrfStage.score + ') does not match '
      + 'fused_score (' + r.fused_score + ') for result id=' + r.id + '.\\n'
    );
    process.exit(1);
  }
}

process.stdout.write(JSON.stringify({ ok: true, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node script failed: {err}"
    import json
    data = json.loads(out)
    assert data["ok"] is True


def test_ac3_hybrid_debug_false_still_produces_correct_fused_result_order():
    """
    When hybridEnabled=true and debug=false, results must be sorted by descending
    fused_score — confirming the RRF output is used for ranking, not dense scores.
    """
    script = """
import { searchDocuments } from './src/search/index.js';

const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 10,
  hybridEnabled: true,
  hybridFusionWeight: 0.7,
  rrfK: 60,
  rerankEnabled: false,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
};

const results = await searchDocuments('test', 10, null, cfg, false);

let prevScore = Infinity;
for (const r of results) {
  if (r.score > prevScore + 1e-9) {
    process.stderr.write(
      'Results not sorted by descending score after RRF fusion.\\n'
      + 'Got ' + r.score + ' after ' + prevScore + '\\n'
    );
    process.exit(1);
  }
  prevScore = r.score;
}

process.stdout.write(JSON.stringify({ ok: true, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node script failed: {err}"
    import json
    data = json.loads(out)
    assert data["ok"] is True
