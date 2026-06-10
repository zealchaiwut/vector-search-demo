import { DataType, MilvusClient } from "@zilliz/milvus2-sdk-node";

const COLLECTION_NAME = "documents";
const EMBEDDING_DIM = 384;

export const COLLECTION_SCHEMA = {
  collection_name: COLLECTION_NAME,
  fields: [
    {
      name: "id",
      data_type: DataType.VarChar,
      max_length: 128,
      is_primary_key: true,
      autoID: false,
    },
    {
      name: "headline",
      data_type: DataType.VarChar,
      max_length: 1024,
    },
    {
      name: "details",
      data_type: DataType.VarChar,
      max_length: 65535,
    },
    {
      name: "attachment_url",
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

function getClient(): MilvusClient {
  const host = process.env.MILVUS_HOST ?? "localhost";
  const port = process.env.MILVUS_PORT ?? "19530";
  return new MilvusClient({ address: `${host}:${port}` });
}

export async function createCollection(recreate = false): Promise<void> {
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

export async function getCollection(): Promise<MilvusClient> {
  const client = getClient();
  await client.loadCollection({ collection_name: COLLECTION_NAME });
  return client;
}
