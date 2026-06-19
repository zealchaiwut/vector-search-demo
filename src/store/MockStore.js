/**
 * MockStore — text-based in-memory VectorStore for zero-database unit tests.
 *
 * Auto-seeds from generateDocuments() on construction. Accepts plain text
 * queries (word-overlap scoring) so no embedding model or live DB is required.
 * Does NOT import the Milvus SDK.
 */

import { generateDocuments } from "../data/generator.js";

function tokenize(text) {
  return (text || "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter(Boolean);
}

function scoreText(queryTokens, text) {
  if (!queryTokens.length) return 0;
  const words = new Set(tokenize(text));
  let hits = 0;
  for (const t of queryTokens) {
    if (words.has(t)) hits++;
  }
  return hits / queryTokens.length;
}

function extractBestPassage(text, queryTokens) {
  const parts = (text || "")
    .split(/[.!?\n]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 5);

  if (!parts.length) {
    const snippet = (text || "").slice(0, 200).trim();
    return { text: snippet || "N/A", context: "" };
  }

  let bestIdx = 0;
  let bestScore = -1;
  for (let i = 0; i < parts.length; i++) {
    const s = scoreText(queryTokens, parts[i]);
    if (s > bestScore) {
      bestScore = s;
      bestIdx = i;
    }
  }

  const best = parts[bestIdx];
  const ctxParts = parts.slice(Math.max(0, bestIdx - 1), bestIdx + 2);
  const context = ctxParts.join(". ").trim();

  return { text: best, context };
}

export class MockStore {
  constructor() {
    this._articles = new Map();
    for (const doc of generateDocuments()) {
      this._articles.set(doc.id, {
        id: doc.id,
        headline: doc.headline || "",
        details: doc.details || "",
        attachment_url: doc.attachment_url ?? null,
      });
    }
  }

  async init() {}
  async migrate() {}

  async upsert(article) {
    if (!article?.id) return;
    this._articles.set(article.id, {
      id: article.id,
      headline: article.headline ?? "",
      details: article.details ?? "",
      attachment_url: article.attachment_url ?? null,
    });
  }

  async delete(articleId) {
    if (!this._articles.has(articleId)) return false;
    this._articles.delete(articleId);
    return true;
  }

  async count() {
    return this._articles.size;
  }

  async ping() {
    return { ok: true };
  }

  async search(query, k = 10) {
    const queryTokens = tokenize(typeof query === "string" ? query : "");
    const results = [];

    for (const article of this._articles.values()) {
      const fullText = `${article.headline} ${article.details}`;
      const score = scoreText(queryTokens, fullText);
      if (score > 0) {
        const best_passage = extractBestPassage(
          article.details || article.headline,
          queryTokens
        );
        results.push({
          id: article.id,
          headline: article.headline,
          details: article.details,
          attachment_url: article.attachment_url,
          score,
          best_passage,
        });
      }
    }

    return results.sort((a, b) => b.score - a.score).slice(0, k);
  }

  async listArticles() {
    return [...this._articles.values()];
  }

  async getArticle(articleId) {
    return this._articles.get(articleId) ?? null;
  }
}
