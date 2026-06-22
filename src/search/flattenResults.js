/**
 * Flatten grouped search results (one object per article with chunks[]) into
 * one row per chunk, sorted globally by chunk score descending.
 *
 * Each flat row keeps backward-compatible fields (passages, best_passage,
 * single-item chunks[]) so older clients keep working.
 */

function normalizePassage(passage, chunk) {
  if (passage && typeof passage === "object" && passage.text) {
    return { ...passage, score: passage.score ?? chunk.score };
  }
  if (typeof passage === "string") {
    return {
      text: passage,
      score: chunk.score,
      context: { before: "", after: "" },
    };
  }
  return {
    text: chunk.text ?? "",
    score: chunk.score,
    context: { before: "", after: "" },
  };
}

function buildFlatChunkRow(article, chunk, chunkIndex, passage) {
  const articleId = article.id ?? article.article_id;
  const text = (chunk.text ?? "").trim();
  const chunkIdx = chunk.chunk_index ?? chunkIndex;

  return {
    id: articleId,
    article_id: articleId,
    chunk_index: chunkIdx,
    headline: article.headline ?? "",
    text,
    details: text.length > 420 ? `${text.slice(0, 420)}…` : text,
    score: chunk.score,
    attachment_url: article.attachment_url ?? null,
    attachment_url_type: article.attachment_url_type ?? null,
    best_passage: passage,
    passages: [passage],
    chunks: [{ text, score: chunk.score, chunk_index: chunkIdx }],
  };
}

/**
 * @param {Array<object>} articleResults
 * @returns {Array<object>}
 */
export function flattenChunkResults(articleResults) {
  const flat = [];

  for (const article of articleResults ?? []) {
    const articleId = article.id ?? article.article_id;
    const chunks = Array.isArray(article.chunks) && article.chunks.length > 0
      ? article.chunks
      : null;

    if (chunks) {
      chunks.forEach((chunk, i) => {
        const passage = normalizePassage(article.passages?.[i], chunk);
        if (chunk.html && passage && !passage.html) {
          passage.html = chunk.html;
        }
        flat.push(buildFlatChunkRow(article, chunk, i, passage));
      });
      continue;
    }

    const text =
      (article.text ?? article.details ?? "").trim() ||
      (typeof article.best_passage === "string"
        ? article.best_passage
        : article.best_passage?.text ?? "");
    const score = article.score ?? 0;
    const passage = normalizePassage(
      article.best_passage ?? article.passages?.[0],
      { text, score },
    );
    if (article.passages?.[0]?.html && passage && !passage.html) {
      passage.html = article.passages[0].html;
    }

    flat.push({
      id: articleId,
      article_id: articleId,
      chunk_index: article.chunk_index ?? 0,
      headline: article.headline ?? "",
      text,
      details: text.length > 420 ? `${text.slice(0, 420)}…` : text,
      score,
      attachment_url: article.attachment_url ?? null,
      attachment_url_type: article.attachment_url_type ?? null,
      best_passage: passage,
      passages: article.passages?.length ? article.passages : [passage],
      chunks: [{ text, score, chunk_index: article.chunk_index ?? 0 }],
    });
  }

  return flat.sort((a, b) => b.score - a.score);
}
