/**
 * Trigram-based lexical scorer using pg_trgm.
 *
 * Uses word_similarity() to score how well the query matches any contiguous
 * portion of the chunk text. This works for Thai and other unspaced scripts
 * because it operates on raw Unicode trigrams without word segmentation.
 *
 * Filtered with the <% operator so the GIN index on details is used.
 */

/**
 * Score chunks against a query using pg_trgm word_similarity.
 *
 * @param {import("../../store/PgVectorStore.js").PgVectorStore} store
 * @param {string} query
 * @param {number} k - max chunks to return (fetches k*5 candidates before grouping)
 * @returns {Promise<Array<{id: string, chunk_index: number, headline: string, details: string, attachment_url: string|null, lexical_score: number}>>}
 */
export async function trigramScorer(store, query, k) {
  const result = await store._query(
    `SELECT article_id AS id,
            chunk_index,
            headline,
            details,
            attachment_url,
            greatest(
              word_similarity($1, coalesce(details, '')),
              word_similarity($1, coalesce(headline, ''))
            ) AS lexical_score
     FROM articles
     WHERE $1 <% coalesce(details, '')
        OR $1 <% coalesce(headline, '')
     ORDER BY greatest(
       word_similarity($1, coalesce(details, '')),
       word_similarity($1, coalesce(headline, ''))
     ) DESC
     LIMIT $2`,
    [query, k * 5],
  );

  return result.rows.map((row) => ({
    id: row.id,
    chunk_index: typeof row.chunk_index === "number" ? row.chunk_index : parseInt(row.chunk_index ?? "0", 10),
    headline: row.headline,
    details: row.details,
    attachment_url: row.attachment_url ?? null,
    lexical_score: parseFloat(row.lexical_score),
  }));
}
