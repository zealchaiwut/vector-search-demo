export const config = {
  port: parseInt(process.env.PORT ?? "8000", 10),
  milvusAddress: process.env.MILVUS_ADDRESS ?? "localhost:19530",
  collectionName: process.env.COLLECTION_NAME ?? "documents",
  embeddingModel: process.env.EMBEDDING_MODEL ?? "Xenova/all-MiniLM-L6-v2",
  dim: parseInt(process.env.DIM ?? "384", 10),
};
