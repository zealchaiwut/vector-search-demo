import { MilvusClient, DataType } from "@zilliz/milvus2-sdk-node";

const COLLECTION_NAME = "documents";
const EMBEDDING_DIM = 384;

export const COLLECTION_SCHEMA = {
  collection_name: COLLECTION_NAME,
  fields: [
    {
      name: "id",
      data_type: DataType.Int64,
      is_primary_key: true,
      autoID: true,
    },
    {
      name: "doc_id",
      data_type: DataType.VarChar,
      max_length: 128,
    },
    {
      name: "chunk_id",
      data_type: DataType.Int64,
    },
    {
      name: "title",
      data_type: DataType.VarChar,
      max_length: 1024,
    },
    {
      name: "text",
      data_type: DataType.VarChar,
      max_length: 65535,
    },
    {
      name: "attachment_name",
      data_type: DataType.VarChar,
      max_length: 512,
    },
    {
      name: "embedding",
      data_type: DataType.FloatVector,
      dim: EMBEDDING_DIM,
    },
  ],
};

export const INDEX_PARAMS = {
  field_name: "embedding",
  index_type: "HNSW",
  metric_type: "COSINE",
  params: { M: 16, efConstruction: 200 },
};

function getClient() {
  const host = process.env.MILVUS_HOST ?? "localhost";
  const port = process.env.MILVUS_PORT ?? "19530";
  return new MilvusClient({ address: `${host}:${port}` });
}

export async function createCollection(recreate = false) {
  const client = getClient();

  const { value: exists } = await client.hasCollection({
    collection_name: COLLECTION_NAME,
  });

  if (exists) {
    if (!recreate) return;
    await client.dropCollection({ collection_name: COLLECTION_NAME });
  }

  await client.createCollection(COLLECTION_SCHEMA);

  await client.createIndex({
    collection_name: COLLECTION_NAME,
    ...INDEX_PARAMS,
  });

  await client.loadCollection({ collection_name: COLLECTION_NAME });
}

export async function getCollection() {
  const client = getClient();
  await client.loadCollection({ collection_name: COLLECTION_NAME });
  return client;
}
