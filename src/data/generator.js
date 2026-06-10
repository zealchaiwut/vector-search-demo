/**
 * Synthetic news-article corpus for vector-search-demo.
 *
 * This is the single canonical corpus for the whole pipeline: `ingest` writes
 * these articles to attachments + the file-backed collection, `search` ranks them,
 * and `eval` checks recall against them.
 * No imports from src/commands/.
 */

const DOCUMENTS = [
  {
    id: "article-001",
    headline: "Introduction to Vector Search",
    details: `Vector search finds similar items by comparing high-dimensional numerical
vectors rather than matching exact keywords. Each document is converted into an
embedding — a dense list of floating point numbers that captures its semantic
meaning. At query time the search engine embeds the query the same way and
retrieves the documents whose vectors are closest. Unlike keyword search, which
fails when the user phrases a question differently from the source text, vector
search captures meaning, so a query about "finding similar items by meaning"
still matches a document with a matching headline. This makes vector search
the foundation of modern semantic search, recommendation, and retrieval-augmented
generation systems.`,
  },
  {
    id: "article-002",
    headline: "Semantic Similarity and Embedding Models",
    details: `Embedding models transform text into dense vector representations that
preserve semantic relationships between words and sentences. Two passages with
similar meaning end up close together in the vector space even when they share no
words. Cosine similarity measures the angle between two vectors and is the most
common scoring function for normalized embeddings: a score near one means the
texts are semantically similar, while a score near zero means they are unrelated.
Choosing a good embedding model is the single biggest factor in search quality,
because the model decides how meaning is mapped into geometry.`,
  },
  {
    id: "article-003",
    headline: "Approximate Nearest Neighbor Algorithms",
    details: `Approximate nearest neighbour algorithms such as HNSW and IVF-Flat enable
fast lookups in high-dimensional vector spaces, trading a small amount of accuracy
for very large speed gains. HNSW builds a layered proximity graph and greedily
walks toward the query vector, while IVF partitions the space into clusters and
only searches the most promising ones. The ef and nprobe parameters control how
many candidates are examined, letting operators tune the balance between recall
and latency. Without an ANN index, every query would have to compare against every
stored vector, which does not scale to millions of documents.`,
  },
  {
    id: "article-004",
    headline: "Milvus Vector Database Setup",
    details: `Milvus is an open-source vector database designed for high-performance
similarity search. It supports multiple index types including HNSW and IVF, scales
to billions of vectors, and exposes a gRPC API for creating collections, inserting
embeddings, and running searches. A typical setup runs Milvus standalone in Docker
with an etcd metadata store and MinIO object storage. After defining a collection
schema with a primary key and a float-vector field, you build an index, load the
collection into memory, and issue top-k vector queries. Health can be verified by
calling the get-version endpoint.`,
  },
  {
    id: "article-005",
    headline: "Transformer Sentence Embeddings with MiniLM",
    details: `Sentence-Transformers and the MiniLM model family produce compact,
high-quality sentence embeddings at low computational cost. MiniLM-L6-v2 outputs a
384-dimensional vector and runs fast enough to embed documents locally on a laptop
CPU, which is why it is a popular default for semantic search demos. The model is
distilled from larger transformers, keeping most of the accuracy while being a
fraction of the size. Running embeddings locally avoids sending data to an external
API and keeps the whole search pipeline self-contained and reproducible.`,
  },
  {
    id: "article-006",
    headline: "End-to-End Semantic Search Pipeline",
    details: `A full semantic search pipeline ingests documents, splits them into
overlapping chunks, generates an embedding for each chunk, and stores the vectors
in an index. At query time the same embedding model encodes the query, the index
returns the most similar chunks, and results are collapsed back to their parent
articles so each article appears once. The top-k most relevant articles are
returned with a relevance score and a link to download the original source file.
This ingest, embed, index, retrieve loop is the backbone of retrieval-augmented
generation and enterprise document search.`,
  },
];

export function generateDocuments() {
  return DOCUMENTS;
}
