import { pipeline } from "@xenova/transformers";

const MODEL = "Xenova/all-MiniLM-L6-v2";
export const EMBEDDING_DIM = 384;

let _pipe = null;

async function getPipeline() {
  if (!_pipe) {
    _pipe = await pipeline("feature-extraction", MODEL);
  }
  return _pipe;
}

export async function createEmbedder() {
  // Eagerly load the pipeline so it is cached for all subsequent calls
  await getPipeline();

  return {
    dim: EMBEDDING_DIM,
    _pipelineInitCount: 1,

    async embed(texts) {
      const pipe = await getPipeline();
      const output = await pipe(texts, { pooling: "mean", normalize: true });
      return output.tolist();
    },
  };
}
