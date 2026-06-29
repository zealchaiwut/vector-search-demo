/**
 * RetrievalConfig — typed pipeline configuration for every search request.
 *
 * Resolution order: env-var defaults → named preset → per-request overrides.
 *
 * Environment variables (all optional — sensible fallbacks are built in):
 *   RETRIEVAL_EMBEDDING_MODEL_ID       — embedding model id (default: Xenova/all-MiniLM-L6-v2)
 *   RETRIEVAL_TOP_K                    — max results to return (default: 10)
 *   RETRIEVAL_HYBRID_ENABLED           — enable hybrid dense+sparse fusion (default: false)
 *   RETRIEVAL_HYBRID_FUSION_WEIGHT     — dense/sparse blend weight 0–1 (default: 0.7)
 *   RETRIEVAL_RRF_K                    — RRF constant k (default: 60)
 *   RETRIEVAL_RERANK_ENABLED           — enable cross-encoder reranking (default: false)
 *   RETRIEVAL_RERANK_MODEL_ID          — reranker model id (default: cross-encoder/ms-marco-MiniLM-L-6-v2)
 *   RETRIEVAL_RERANK_CANDIDATE_COUNT   — candidates fetched before reranking (default: 50)
 *   RETRIEVAL_CHUNK_SIZE               — characters per chunk (default: 400)
 *   RETRIEVAL_CHUNK_OVERLAP            — character overlap between chunks (default: 80)
 *   RETRIEVAL_TEXT_NORMALISATION_ENABLED — normalise text before embedding (default: true)
 *   RETRIEVAL_CHUNKING_MODE             — chunking strategy: 'length' or 'thai_word' (default: length)
 */

// ---------------------------------------------------------------------------
// Internal coercion helpers
// ---------------------------------------------------------------------------

function parseBool(val, fallback) {
  if (val === undefined || val === null) return fallback;
  if (typeof val === "boolean") return val;
  const s = String(val).toLowerCase().trim();
  if (s === "true" || s === "1" || s === "yes") return true;
  if (s === "false" || s === "0" || s === "no") return false;
  return fallback;
}

function parseIntVal(val, fallback) {
  const n = parseInt(val, 10);
  return Number.isFinite(n) ? n : fallback;
}

function parseFloatVal(val, fallback) {
  const n = parseFloat(val);
  return Number.isFinite(n) ? n : fallback;
}

// ---------------------------------------------------------------------------
// Preset registry
// ---------------------------------------------------------------------------

export const PRESETS = {
  "dense-only": {
    embeddingModelId: "Xenova/all-MiniLM-L6-v2",
    topK: 10,
    hybridEnabled: false,
    hybridFusionWeight: 1.0,
    rrfK: 60,
    rerankEnabled: false,
    rerankModelId: "cross-encoder/ms-marco-MiniLM-L-6-v2",
    rerankCandidateCount: 50,
    chunkSize: 400,
    chunkOverlap: 80,
    textNormalisationEnabled: true,
    chunkingMode: "length",
  },
  hybrid: {
    embeddingModelId: "Xenova/all-MiniLM-L6-v2",
    topK: 10,
    hybridEnabled: true,
    hybridFusionWeight: 0.7,
    rrfK: 60,
    rerankEnabled: false,
    rerankModelId: "cross-encoder/ms-marco-MiniLM-L-6-v2",
    rerankCandidateCount: 50,
    chunkSize: 400,
    chunkOverlap: 80,
    textNormalisationEnabled: true,
    chunkingMode: "length",
  },
  "hybrid-rerank": {
    embeddingModelId: "Xenova/all-MiniLM-L6-v2",
    topK: 10,
    hybridEnabled: true,
    hybridFusionWeight: 0.7,
    rrfK: 60,
    rerankEnabled: true,
    rerankModelId: "cross-encoder/ms-marco-MiniLM-L-6-v2",
    rerankCandidateCount: 50,
    chunkSize: 400,
    chunkOverlap: 80,
    textNormalisationEnabled: true,
    chunkingMode: "length",
  },
};

export const KNOWN_PRESETS = new Set(Object.keys(PRESETS));

// ---------------------------------------------------------------------------
// Default config from environment variables
// ---------------------------------------------------------------------------

/**
 * Build the default RetrievalConfig, reading overrides from environment variables.
 * @returns {object} RetrievalConfig
 */
export function defaultRetrievalConfig() {
  return {
    embeddingModelId:
      process.env.RETRIEVAL_EMBEDDING_MODEL_ID ?? "Xenova/all-MiniLM-L6-v2",
    topK: parseIntVal(process.env.RETRIEVAL_TOP_K, 10),
    hybridEnabled: parseBool(process.env.RETRIEVAL_HYBRID_ENABLED, false),
    hybridFusionWeight: parseFloatVal(
      process.env.RETRIEVAL_HYBRID_FUSION_WEIGHT,
      0.7,
    ),
    rrfK: parseIntVal(process.env.RETRIEVAL_RRF_K, 60),
    rerankEnabled: parseBool(process.env.RETRIEVAL_RERANK_ENABLED, false),
    rerankModelId:
      process.env.RETRIEVAL_RERANK_MODEL_ID ??
      "cross-encoder/ms-marco-MiniLM-L-6-v2",
    rerankCandidateCount: parseIntVal(
      process.env.RETRIEVAL_RERANK_CANDIDATE_COUNT,
      50,
    ),
    chunkSize: parseIntVal(
      process.env.RETRIEVAL_CHUNK_SIZE ?? process.env.CHUNK_SIZE,
      400,
    ),
    chunkOverlap: parseIntVal(
      process.env.RETRIEVAL_CHUNK_OVERLAP ?? process.env.CHUNK_OVERLAP,
      80,
    ),
    textNormalisationEnabled: parseBool(
      process.env.RETRIEVAL_TEXT_NORMALISATION_ENABLED,
      true,
    ),
    chunkingMode: process.env.RETRIEVAL_CHUNKING_MODE ?? "length",
  };
}

// ---------------------------------------------------------------------------
// Parse per-request overrides from a flat params map
// ---------------------------------------------------------------------------

/**
 * Extract and coerce recognised RetrievalConfig keys from a flat params object
 * (URL query string or JSON body). Unknown keys are silently ignored.
 *
 * @param {Record<string, string|boolean|number>} params
 * @returns {Partial<object>} Partial RetrievalConfig with only the provided fields.
 */
export function parseConfigOverrides(params) {
  const out = {};
  if (params.embeddingModelId !== undefined)
    out.embeddingModelId = String(params.embeddingModelId);
  if (params.topK !== undefined) out.topK = parseIntVal(params.topK, undefined);
  if (params.hybridEnabled !== undefined)
    out.hybridEnabled = parseBool(params.hybridEnabled, undefined);
  if (params.hybridFusionWeight !== undefined)
    out.hybridFusionWeight = parseFloatVal(
      params.hybridFusionWeight,
      undefined,
    );
  if (params.rrfK !== undefined) out.rrfK = parseIntVal(params.rrfK, undefined);
  if (params.rerankEnabled !== undefined)
    out.rerankEnabled = parseBool(params.rerankEnabled, undefined);
  if (params.rerankModelId !== undefined)
    out.rerankModelId = String(params.rerankModelId);
  if (params.rerankCandidateCount !== undefined)
    out.rerankCandidateCount = parseIntVal(
      params.rerankCandidateCount,
      undefined,
    );
  if (params.chunkSize !== undefined)
    out.chunkSize = parseIntVal(params.chunkSize, undefined);
  if (params.chunkOverlap !== undefined)
    out.chunkOverlap = parseIntVal(params.chunkOverlap, undefined);
  if (params.textNormalisationEnabled !== undefined)
    out.textNormalisationEnabled = parseBool(
      params.textNormalisationEnabled,
      undefined,
    );
  if (params.chunkingMode !== undefined)
    out.chunkingMode = String(params.chunkingMode);
  return out;
}

// ---------------------------------------------------------------------------
// Resolve: env defaults → preset → overrides
// ---------------------------------------------------------------------------

/**
 * Resolve a complete RetrievalConfig for a single request.
 *
 * Resolution order:
 *   1. Environment-variable defaults  (lowest precedence)
 *   2. Named preset (if provided)
 *   3. Per-request overrides           (highest precedence)
 *
 * @param {string|null} presetName  Named preset or null.
 * @param {object} overrides        Partial RetrievalConfig from the request.
 * @returns {{ config: object|null, error: string|null }}
 */
export function resolveRetrievalConfig(presetName, overrides = {}) {
  const base = defaultRetrievalConfig();

  if (presetName) {
    if (!KNOWN_PRESETS.has(presetName)) {
      return {
        config: null,
        error: `Unknown preset "${presetName}". Valid presets: ${[...KNOWN_PRESETS].join(", ")}`,
      };
    }
    Object.assign(base, PRESETS[presetName]);
  }

  for (const [key, value] of Object.entries(overrides)) {
    if (value !== undefined && key in base) {
      base[key] = value;
    }
  }

  if (base.topK < 1 || base.topK > 500) {
    return {
      config: null,
      error: `topK must be between 1 and 500, got ${base.topK}`,
    };
  }

  if (base.hybridFusionWeight < 0.0 || base.hybridFusionWeight > 1.0) {
    return {
      config: null,
      error: `hybridFusionWeight must be between 0.0 and 1.0, got ${base.hybridFusionWeight}`,
    };
  }

  return { config: base, error: null };
}
