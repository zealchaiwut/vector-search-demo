import { pipeline } from "@xenova/transformers";
import { resolveModel } from "./model-registry.js";

const MODEL_NAME = process.env.EMBEDDING_MODEL ?? "Xenova/multilingual-e5-small";
const _modelInfo = resolveModel(MODEL_NAME);

export const EMBEDDING_DIM = _modelInfo.dim;
export const EMBEDDING_MODEL = _modelInfo.xenovaId;
export const MODEL_SPARSE = _modelInfo.sparse;

// One cached pipeline per resolved xenova model id, so the model can be chosen
// per call (Compare tab / ?model=) without re-loading a shared singleton.
const _pipes = new Map();

async function getPipeline(xenovaId) {
  if (!_pipes.has(xenovaId)) {
    _pipes.set(xenovaId, await pipeline("feature-extraction", xenovaId));
  }
  return _pipes.get(xenovaId);
}

/**
 * Create an embedder for a specific model.
 * @param {string} [modelName] registered model name/id; defaults to EMBEDDING_MODEL.
 */
export async function createEmbedder(modelName = MODEL_NAME) {
  const info = resolveModel(modelName);
  await getPipeline(info.xenovaId);

  return {
    dim: info.dim,
    sparse: info.sparse,
    modelName,
    modelId: info.xenovaId,
    _pipelineInitCount: 1,

    /**
     * Embed texts into dense float vectors. Always returns an array of float arrays
     * regardless of model — the stable interface used by search and ingest.
     * @param {string[]} texts
     * @returns {Promise<number[][]>}
     */
    async embed(texts) {
      const pipe = await getPipeline(info.xenovaId);
      const output = await pipe(texts, { pooling: "mean", normalize: true });
      return output.tolist();
    },

    /**
     * For BGE-M3: generate sparse lexical weights alongside dense vectors.
     * Returns an array of {token_id: weight} objects (one per input text).
     * For non-sparse models, returns an array of empty objects.
     * @param {string[]} texts
     * @returns {Promise<Record<string,number>[]>}
     */
    async embedSparse(texts) {
      if (!info.sparse) {
        return texts.map(() => ({}));
      }
      const pipe = await getPipeline(info.xenovaId);
      try {
        // BGE-M3 sparse weights: ReLU over log(1 + logits) summed across sequence
        const rawOutput = await pipe(texts, {
          pooling: "none",
          normalize: false,
        });
        if (!rawOutput || !rawOutput.dims || rawOutput.dims.length !== 3) {
          return texts.map(() => ({}));
        }
        const [batch, seq, vocabSize] = rawOutput.dims;
        const data = rawOutput.data;
        const results = [];
        for (let b = 0; b < batch; b++) {
          const weights = {};
          for (let v = 0; v < vocabSize; v++) {
            let sum = 0;
            for (let s = 0; s < seq; s++) {
              const val = data[b * seq * vocabSize + s * vocabSize + v];
              if (val > 0) sum += Math.log(1 + val);
            }
            if (sum > 0.01) weights[String(v)] = sum;
          }
          results.push(weights);
        }
        return results;
      } catch {
        return texts.map(() => ({}));
      }
    },
  };
}
