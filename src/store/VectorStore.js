/**
 * VectorStore interface contract.
 *
 * All store implementations must provide these async methods:
 *
 * @typedef {Object} VectorStore
 * @property {(article: {id: string, headline: string, details: string, attachment_url?: string}) => Promise<void>} upsert
 *   Add a new article or replace an existing one matched by id.
 * @property {(articleId: string) => Promise<boolean>} delete
 *   Remove the article with the given id. Returns true if removed, false if not found.
 * @property {() => Promise<number>} count
 *   Return the exact number of distinct articles currently held in the store.
 * @property {() => Promise<{ok: boolean}>} ping
 *   Health check. Must always resolve successfully regardless of store state.
 * @property {(query: string, k?: number) => Promise<Array>} search
 *   Return up to k articles ranked by cosine similarity to the query embedding.
 *   Each result includes: id, headline, details, score, attachment_url,
 *   attachment_url_type, and best_passage.
 */

// This file documents the contract. Implementations live alongside this file.
