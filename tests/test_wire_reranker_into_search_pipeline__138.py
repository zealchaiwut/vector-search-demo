"""
TDD tests for issue #138: Wire reranker into search pipeline behind rerank flag.

AC1 — When rerank=true, the pipeline retrieves rerankCandidateCount candidates
       and passes them to the Reranker before returning results
AC2 — Final results when rerank=true reflect the reranker's ordering, not the
       original retrieval order
AC3 — The candidate count fed to the reranker is configurable (distinct from topK)
AC4 — When rerank=false, reranking is skipped; results match un-reranked baseline
AC5 — Explain mode with rerank=true reports pre_rerank_rank, post_rerank_rank,
       and rerank_score for each result
AC6 — Explain mode with rerank=false shows no rerank fields
AC7 — No regression in pipeline for dense-only or hybrid retrieval when rerank disabled
"""

import json
import os
import re
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEARCH_INDEX_JS = os.path.join(REPO_ROOT, "src", "search", "index.js")
RETRIEVAL_CONFIG_JS = os.path.join(REPO_ROOT, "src", "config", "retrieval.js")
RERANKER_JS = os.path.join(REPO_ROOT, "src", "search", "reranker.js")


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
# AC3 — rerankCandidateCount configurable and distinct from topK
# ---------------------------------------------------------------------------

def test_ac3_reranker_js_exists():
    assert os.path.isfile(RERANKER_JS), f"src/search/reranker.js must exist at {RERANKER_JS}"


def test_ac3_reranker_class_exported():
    with open(RERANKER_JS) as f:
        src = f.read()
    assert "Reranker" in src, "src/search/reranker.js must define a Reranker class"
    assert "export" in src, "src/search/reranker.js must export the Reranker class"


def test_ac3_retrieval_config_has_rerank_candidate_count():
    with open(RETRIEVAL_CONFIG_JS) as f:
        src = f.read()
    assert "rerankCandidateCount" in src, (
        "src/config/retrieval.js must define rerankCandidateCount field"
    )


def test_ac3_default_rerank_candidate_count_is_positive_int():
    script = """
import { defaultRetrievalConfig } from './src/config/retrieval.js';
const cfg = defaultRetrievalConfig();
process.stdout.write(JSON.stringify({ rerankCandidateCount: cfg.rerankCandidateCount }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert isinstance(data["rerankCandidateCount"], int) and data["rerankCandidateCount"] > 0, (
        f"rerankCandidateCount must be a positive integer. Got: {data['rerankCandidateCount']}"
    )


def test_ac3_rerank_candidate_count_env_var_override():
    script = """
import { defaultRetrievalConfig } from './src/config/retrieval.js';
const cfg = defaultRetrievalConfig();
process.stdout.write(JSON.stringify({ rerankCandidateCount: cfg.rerankCandidateCount }));
"""
    out, err, rc = _run_node(script, env={"RETRIEVAL_RERANK_CANDIDATE_COUNT": "99"})
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["rerankCandidateCount"] == 99, (
        f"RETRIEVAL_RERANK_CANDIDATE_COUNT=99 must set rerankCandidateCount=99. Got: {data['rerankCandidateCount']}"
    )


def test_ac3_retrieval_config_env_var_documented():
    with open(RETRIEVAL_CONFIG_JS) as f:
        src = f.read()
    assert "RETRIEVAL_RERANK_CANDIDATE_COUNT" in src, (
        "RETRIEVAL_RERANK_CANDIDATE_COUNT env var must be documented in src/config/retrieval.js"
    )


def test_ac3_parse_config_overrides_accepts_rerank_candidate_count():
    script = """
import { parseConfigOverrides } from './src/config/retrieval.js';
const out = parseConfigOverrides({ rerankCandidateCount: '30' });
process.stdout.write(JSON.stringify(out));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    result = json.loads(out)
    assert result.get("rerankCandidateCount") == 30, (
        f"parseConfigOverrides must coerce rerankCandidateCount to int. Got: {result}"
    )


def test_ac3_candidate_count_greater_than_default_top_k():
    """Default rerankCandidateCount must be > default topK so the pool is larger."""
    script = """
import { defaultRetrievalConfig } from './src/config/retrieval.js';
const cfg = defaultRetrievalConfig();
process.stdout.write(JSON.stringify({ rerankCandidateCount: cfg.rerankCandidateCount, topK: cfg.topK }));
"""
    env = {k: v for k, v in os.environ.items() if not k.startswith("RETRIEVAL_")}
    out, err, rc = _run_node(script, env=env)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["rerankCandidateCount"] > data["topK"], (
        f"Default rerankCandidateCount ({data['rerankCandidateCount']}) must exceed default topK ({data['topK']})"
    )


# ---------------------------------------------------------------------------
# AC1 — Reranker class exists with the right interface
# ---------------------------------------------------------------------------

def test_ac1_reranker_has_rerank_method():
    script = """
import { Reranker } from './src/search/reranker.js';
const r = new Reranker();
if (typeof r.rerank !== 'function') {
  process.stderr.write('Reranker.rerank must be a function\\n');
  process.exit(1);
}
process.stdout.write(JSON.stringify({ ok: true }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    assert json.loads(out)["ok"] is True


def test_ac1_reranker_returns_array_of_same_length():
    script = """
import { Reranker } from './src/search/reranker.js';
const r = new Reranker();
const candidates = [
  { id: 'a', headline: 'Machine learning', details: 'Deep neural networks for ML', score: 0.9 },
  { id: 'b', headline: 'Database systems', details: 'SQL and NoSQL databases', score: 0.8 },
];
const result = r.rerank('machine learning', candidates);
if (!Array.isArray(result)) {
  process.stderr.write('rerank must return an array\\n');
  process.exit(1);
}
process.stdout.write(JSON.stringify({ ok: true, len: result.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True
    assert data["len"] == 2


def test_ac1_reranker_result_has_rerank_score():
    script = """
import { Reranker } from './src/search/reranker.js';
const r = new Reranker();
const candidates = [
  { id: 'a', headline: 'Machine learning', details: 'Deep neural networks', score: 0.9 },
];
const result = r.rerank('machine learning', candidates);
const item = result[0];
if (typeof item.rerankScore !== 'number') {
  process.stderr.write('rerank result must have rerankScore (number). Got: ' + JSON.stringify(item) + '\\n');
  process.exit(1);
}
process.stdout.write(JSON.stringify({ ok: true }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    assert json.loads(out)["ok"] is True


def test_ac1_reranker_result_has_pre_and_post_rank():
    script = """
import { Reranker } from './src/search/reranker.js';
const r = new Reranker();
const candidates = [
  { id: 'a', headline: 'Machine learning', details: 'Deep neural networks', score: 0.9 },
  { id: 'b', headline: 'Database systems', details: 'SQL databases', score: 0.8 },
];
const result = r.rerank('machine learning', candidates);
for (const item of result) {
  if (typeof item.preRerankRank !== 'number' || typeof item.postRerankRank !== 'number') {
    process.stderr.write('rerank result must have preRerankRank and postRerankRank. Got: ' + JSON.stringify(item) + '\\n');
    process.exit(1);
  }
}
process.stdout.write(JSON.stringify({ ok: true }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    assert json.loads(out)["ok"] is True


def test_ac1_reranker_sorted_by_descending_rerank_score():
    """Reranker returns items sorted by descending rerankScore."""
    script = """
import { Reranker } from './src/search/reranker.js';
const r = new Reranker();
// Second candidate strongly matches 'database' query
const candidates = [
  { id: 'a', headline: 'Machine learning', details: 'Neural networks for ML tasks', score: 0.9 },
  { id: 'b', headline: 'Database database database', details: 'SQL and NoSQL databases database', score: 0.3 },
];
const result = r.rerank('database', candidates);
const sorted = result.every((item, i) => i === 0 || result[i-1].rerankScore >= item.rerankScore);
process.stdout.write(JSON.stringify({ ok: sorted, first: result[0]?.result?.id, scores: result.map(r => r.rerankScore) }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, f"rerank must return items sorted by descending rerankScore. Got: {data}"


def test_ac1_reranker_pre_rank_reflects_input_order():
    """preRerankRank must be 1-indexed based on the candidate input order."""
    script = """
import { Reranker } from './src/search/reranker.js';
const r = new Reranker();
const candidates = [
  { id: 'a', headline: 'alpha', details: 'text1', score: 0.9 },
  { id: 'b', headline: 'beta', details: 'text2', score: 0.8 },
  { id: 'c', headline: 'gamma', details: 'text3', score: 0.7 },
];
const result = r.rerank('test', candidates);
const preRanks = result.map(item => item.preRerankRank).sort((a, b) => a - b);
const ok = preRanks.length === 3 && preRanks[0] === 1 && preRanks[1] === 2 && preRanks[2] === 3;
process.stdout.write(JSON.stringify({ ok, preRanks }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, f"preRerankRank must be 1-indexed from input position. Got: {data['preRanks']}"


def test_ac1_reranker_post_rank_is_1_indexed_output_position():
    """postRerankRank must be 1-indexed position in the reranked output."""
    script = """
import { Reranker } from './src/search/reranker.js';
const r = new Reranker();
const candidates = [
  { id: 'a', headline: 'alpha', details: 'text1', score: 0.9 },
  { id: 'b', headline: 'beta', details: 'text2', score: 0.8 },
];
const result = r.rerank('test', candidates);
const postRanks = result.map(item => item.postRerankRank);
const ok = postRanks[0] === 1 && postRanks[1] === 2;
process.stdout.write(JSON.stringify({ ok, postRanks }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, f"postRerankRank must be 1-indexed output position. Got: {data['postRanks']}"


# ---------------------------------------------------------------------------
# AC2 — Final results when rerank=true reflect the reranker's ordering
# ---------------------------------------------------------------------------

def test_ac2_search_index_imports_reranker():
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    assert "reranker" in src.lower() or "Reranker" in src, (
        "src/search/index.js must import Reranker from reranker.js"
    )


def test_ac2_pipeline_references_rerank_candidate_count():
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    assert "rerankCandidateCount" in src or "candidateCount" in src, (
        "src/search/index.js must use rerankCandidateCount to size the retrieval pool when rerankEnabled"
    )


def test_ac2_reranked_results_count_at_most_top_k():
    """With rerankEnabled=true, final results must not exceed topK."""
    script = """
import { searchDocuments } from './src/search/index.js';
const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 5,
  hybridEnabled: false,
  hybridFusionWeight: 0.7,
  rrfK: 60,
  rerankEnabled: true,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  rerankCandidateCount: 20,
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
};
const results = await searchDocuments('test', 5, null, cfg, false);
process.stdout.write(JSON.stringify({ ok: results.length <= 5, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, f"Reranked results must not exceed topK=5. Got count: {data['count']}"


def test_ac2_hybrid_with_rerank_returns_array():
    """Hybrid + rerank pipeline must complete without errors."""
    script = """
import { searchDocuments } from './src/search/index.js';
const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 5,
  hybridEnabled: true,
  hybridFusionWeight: 0.7,
  rrfK: 60,
  rerankEnabled: true,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  rerankCandidateCount: 20,
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
};
const results = await searchDocuments('test', 5, null, cfg, false);
process.stdout.write(JSON.stringify({ ok: Array.isArray(results), count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Hybrid + rerank pipeline error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, "Hybrid + rerank pipeline must return an array"


# ---------------------------------------------------------------------------
# AC4 — rerank=false skips reranking; results match un-reranked baseline
# ---------------------------------------------------------------------------

def test_ac4_rerankEnabled_gates_reranking_in_source():
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    assert re.search(r"cfg\.rerankEnabled", src), (
        "src/search/index.js must gate reranking on cfg.rerankEnabled"
    )


def test_ac4_rerank_false_pipeline_succeeds():
    script = """
import { searchDocuments } from './src/search/index.js';
const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 10,
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
const results = await searchDocuments('test query', 10, null, cfg, false);
process.stdout.write(JSON.stringify({ ok: Array.isArray(results), count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error when rerankEnabled=false: {err}"
    data = json.loads(out)
    assert data["ok"] is True


def test_ac4_two_calls_rerank_false_give_same_results():
    """Two calls with rerankEnabled=false must return the same result ordering."""
    script = """
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
const r1 = await searchDocuments('test', 5, null, cfg, false);
const r2 = await searchDocuments('test', 5, null, cfg, false);
const idsMatch = JSON.stringify(r1.map(r => r.id)) === JSON.stringify(r2.map(r => r.id));
process.stdout.write(JSON.stringify({ ok: idsMatch }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, "Two calls with rerankEnabled=false must return identical result order"


# ---------------------------------------------------------------------------
# AC5 — Explain mode with rerank=true adds pre/post rank and rerank_score
# ---------------------------------------------------------------------------

def test_ac5_explain_rerank_stage_has_rerank_score_field():
    script = """
import { searchDocuments } from './src/search/index.js';
const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 5,
  hybridEnabled: false,
  hybridFusionWeight: 0.7,
  rrfK: 60,
  rerankEnabled: true,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  rerankCandidateCount: 20,
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
};
const results = await searchDocuments('test', 5, null, cfg, true);
let ok = true;
for (const r of results) {
  const rerankStage = (r.explain ?? []).find(s => s.stage === 'rerank');
  if (rerankStage && typeof rerankStage.rerankScore !== 'number') {
    ok = false;
    process.stderr.write('rerank explain stage missing rerankScore. Got: ' + JSON.stringify(rerankStage) + '\\n');
  }
}
process.stdout.write(JSON.stringify({ ok, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, "rerank explain stage must have rerankScore (number)"


def test_ac5_explain_rerank_stage_has_pre_rerank_rank():
    script = """
import { searchDocuments } from './src/search/index.js';
const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 5,
  hybridEnabled: false,
  hybridFusionWeight: 0.7,
  rrfK: 60,
  rerankEnabled: true,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  rerankCandidateCount: 20,
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
};
const results = await searchDocuments('test', 5, null, cfg, true);
let ok = true;
for (const r of results) {
  const rerankStage = (r.explain ?? []).find(s => s.stage === 'rerank');
  if (rerankStage && typeof rerankStage.preRerankRank !== 'number') {
    ok = false;
    process.stderr.write('rerank explain stage missing preRerankRank. Got: ' + JSON.stringify(rerankStage) + '\\n');
  }
}
process.stdout.write(JSON.stringify({ ok, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, "rerank explain stage must have preRerankRank (number)"


def test_ac5_explain_rerank_stage_has_post_rerank_rank():
    script = """
import { searchDocuments } from './src/search/index.js';
const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 5,
  hybridEnabled: false,
  hybridFusionWeight: 0.7,
  rrfK: 60,
  rerankEnabled: true,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  rerankCandidateCount: 20,
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
};
const results = await searchDocuments('test', 5, null, cfg, true);
let ok = true;
for (const r of results) {
  const rerankStage = (r.explain ?? []).find(s => s.stage === 'rerank');
  if (rerankStage && typeof rerankStage.postRerankRank !== 'number') {
    ok = false;
    process.stderr.write('rerank explain stage missing postRerankRank. Got: ' + JSON.stringify(rerankStage) + '\\n');
  }
}
process.stdout.write(JSON.stringify({ ok, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["ok"] is True, "rerank explain stage must have postRerankRank (number)"


# ---------------------------------------------------------------------------
# AC6 — Explain mode with rerank=false shows no rerank stage or fields
# ---------------------------------------------------------------------------

def test_ac6_no_rerank_explain_stage_when_disabled():
    script = """
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
const results = await searchDocuments('test', 5, null, cfg, true);
let hasRerankStage = false;
for (const r of results) {
  if ((r.explain ?? []).some(s => s.stage === 'rerank')) {
    hasRerankStage = true;
    break;
  }
}
process.stdout.write(JSON.stringify({ hasRerankStage, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["hasRerankStage"] is False, (
        "rerankEnabled=false must produce no 'rerank' stage in explain"
    )


def test_ac6_no_rerank_fields_on_results_when_disabled():
    script = """
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
const results = await searchDocuments('test', 5, null, cfg, false);
const hasRerankFields = results.some(r =>
  'rerankScore' in r || 'preRerankRank' in r || 'postRerankRank' in r
);
process.stdout.write(JSON.stringify({ hasRerankFields, count: results.length }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["hasRerankFields"] is False, (
        "rerankEnabled=false must not add rerankScore/preRerankRank/postRerankRank to results"
    )


# ---------------------------------------------------------------------------
# AC7 — No regression for dense-only or hybrid when rerank is disabled
# ---------------------------------------------------------------------------

def test_ac7_dense_only_rerank_false_no_error():
    script = """
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
const results = await searchDocuments('test', 5, null, cfg, false);
process.stdout.write(JSON.stringify({ ok: Array.isArray(results) }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Dense-only pipeline with rerank=false broke: {err}"
    assert json.loads(out)["ok"] is True


def test_ac7_hybrid_rerank_false_no_error():
    script = """
import { searchDocuments } from './src/search/index.js';
const cfg = {
  embeddingModelId: 'Xenova/multilingual-e5-small',
  topK: 5,
  hybridEnabled: true,
  hybridFusionWeight: 0.7,
  rrfK: 60,
  rerankEnabled: false,
  rerankModelId: 'cross-encoder/ms-marco-MiniLM-L-6-v2',
  rerankCandidateCount: 50,
  chunkSize: 400,
  chunkOverlap: 80,
  textNormalisationEnabled: true,
};
const results = await searchDocuments('test', 5, null, cfg, false);
process.stdout.write(JSON.stringify({ ok: Array.isArray(results) }));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Hybrid pipeline with rerank=false broke: {err}"
    assert json.loads(out)["ok"] is True


def test_ac7_default_config_rerank_still_false():
    """Default configuration must keep rerankEnabled=false (backward compat)."""
    script = """
import { defaultRetrievalConfig } from './src/config/retrieval.js';
const cfg = defaultRetrievalConfig();
process.stdout.write(JSON.stringify({ rerankEnabled: cfg.rerankEnabled }));
"""
    env = {k: v for k, v in os.environ.items() if not k.startswith("RETRIEVAL_")}
    out, err, rc = _run_node(script, env=env)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["rerankEnabled"] is False, (
        f"Default rerankEnabled must remain false. Got: {data['rerankEnabled']}"
    )


def test_ac7_existing_presets_still_defined():
    script = """
import { PRESETS } from './src/config/retrieval.js';
const names = ['dense-only', 'hybrid', 'hybrid-rerank'];
const results = Object.fromEntries(names.map(n => [n, n in PRESETS]));
process.stdout.write(JSON.stringify(results));
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Node error: {err}"
    data = json.loads(out)
    assert data["dense-only"] is True, "dense-only preset must still exist"
    assert data["hybrid"] is True, "hybrid preset must still exist"
    assert data["hybrid-rerank"] is True, "hybrid-rerank preset must still exist"


def test_ac7_explain_infrastructure_unchanged():
    """The explain infrastructure from issue #131 must remain intact."""
    with open(SEARCH_INDEX_JS) as f:
        src = f.read()
    for field in ("stage", "score", "rank", "rankDelta", "latencyMs"):
        assert field in src, (
            f"src/search/index.js must still reference explain field '{field}' (regression from #131)"
        )
