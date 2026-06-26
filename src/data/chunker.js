/**
 * Character-window chunker for vector-search-demo.
 * Splits article bodies into overlapping fixed-length character chunks.
 * Character-based (not whitespace-based) so it works correctly for Thai and
 * other scripts that have no space between words.
 *
 * Override defaults via environment variables:
 *   CHUNK_SIZE    — characters per chunk (default: 400)
 *   CHUNK_OVERLAP — overlap between consecutive chunks (default: 80)
 */

export const CHUNK_SIZE = 400;
export const CHUNK_OVERLAP = 80;

export const CHUNKING_MODE = {
  LENGTH: "length",
  THAI_WORD: "thai_word",
};

/**
 * Split an article into overlapping character-window chunks.
 * CHUNK_SIZE and CHUNK_OVERLAP env vars override the defaults at call time.
 * @param {object} article - { id, headline, details, attachment_url }
 * @param {number} chunkSize - characters per chunk (default CHUNK_SIZE)
 * @param {number} overlap - character overlap between consecutive chunks (default CHUNK_OVERLAP)
 * @returns {Array<{id, headline, details, attachment_url}>}
 */
export function chunkDocument(
  article,
  chunkSize = CHUNK_SIZE,
  overlap = CHUNK_OVERLAP,
) {
  const _szEnv = parseInt(process.env.CHUNK_SIZE, 10);
  const sz = (Number.isFinite(_szEnv) && _szEnv >= 0) ? _szEnv : chunkSize;
  const _ovEnv = parseInt(process.env.CHUNK_OVERLAP, 10);
  const ov = (Number.isFinite(_ovEnv) && _ovEnv >= 0) ? _ovEnv : overlap;
  const { id, headline, details } = article;
  const text = (details ?? "").trim();

  if (text.length === 0) return [];

  const stride = sz - ov;
  const chunks = [];
  let i = 0;

  while (i < text.length) {
    const slice = text.slice(i, i + sz);
    chunks.push({
      id: `${id}:${chunks.length}`,
      headline,
      details: slice,
      attachment_url: article.attachment_url || `/download/${id}`,
    });
    if (i + sz >= text.length) break;
    i += stride;
  }

  return chunks;
}

/**
 * Chunk an array of articles.
 * @param {Array} articles
 * @returns {Array} flat array of all chunks
 */
export function chunkDocuments(articles) {
  return articles.flatMap((article) => chunkDocument(article));
}

// ---------------------------------------------------------------------------
// Thai word-boundary chunker
// ---------------------------------------------------------------------------

function _defaultThaiSegmenterFactory() {
  return new Intl.Segmenter("th", { granularity: "word" });
}

function _splitParagraphAtWordBoundaries(para, chunkSize, segmenter) {
  const segs = [...segmenter.segment(para)];
  const result = [];
  let cur = "";
  for (const { segment } of segs) {
    if (cur.length + segment.length <= chunkSize) {
      cur += segment;
    } else {
      if (cur.length > 0) {
        result.push(cur);
        cur = "";
      }
      if (segment.length > chunkSize) {
        // Single token exceeds limit — hard-cap it at char boundaries
        for (let p = 0; p < segment.length; p += chunkSize) {
          result.push(segment.slice(p, p + chunkSize));
        }
      } else {
        cur = segment;
      }
    }
  }
  if (cur.length > 0) result.push(cur);
  return result;
}

/**
 * Split an article using Thai word boundaries.
 *
 * Paragraph/newline boundaries are preferred as split points; the word
 * segmenter is only consulted for paragraphs that exceed chunkSize.
 * Falls back to chunkDocument (length mode) if the segmenter is unavailable.
 *
 * @param {object} article - { id, headline, details, attachment_url }
 * @param {number} chunkSize - max characters per chunk (default CHUNK_SIZE)
 * @param {object} options
 * @param {function} [options.warn] - warning callback (default: stderr)
 * @param {function} [options._segmenterFactory] - injectable factory for testing
 * @param {number} [options.overlap] - overlap for length-mode fallback (default CHUNK_OVERLAP)
 * @returns {Array<{id, headline, details, attachment_url}>}
 */
export function chunkDocumentThai(
  article,
  chunkSize = CHUNK_SIZE,
  options = {},
) {
  const { id, headline } = article;
  const text = (article.details ?? "").trim();
  if (text.length === 0) return [];

  const warn =
    options.warn ?? ((msg) => process.stderr.write(`[chunker] ${msg}\n`));
  const segmenterFactory =
    options._segmenterFactory ?? _defaultThaiSegmenterFactory;
  const overlap = options.overlap ?? CHUNK_OVERLAP;

  const paragraphs = text.split(/\n+/).filter((p) => p.length > 0);
  const hasLongParagraph = paragraphs.some((p) => p.length > chunkSize);

  let segmenter = null;
  if (hasLongParagraph) {
    try {
      segmenter = segmenterFactory();
    } catch (e) {
      warn(
        `Thai word segmenter unavailable (${e.message}), falling back to length-based chunking`,
      );
      // Cap overlap so stride stays positive when chunkSize < default overlap
      const safeOverlap = Math.min(overlap, Math.max(0, chunkSize - 1));
      return chunkDocument(article, chunkSize, safeOverlap);
    }
  }

  const rawSegments = [];
  for (const para of paragraphs) {
    if (para.length <= chunkSize) {
      rawSegments.push(para);
    } else {
      rawSegments.push(
        ..._splitParagraphAtWordBoundaries(para, chunkSize, segmenter),
      );
    }
  }

  // Pack adjacent segments into chunks up to chunkSize, using '\n' as separator
  const packed = [];
  let buf = "";
  for (const seg of rawSegments) {
    if (buf.length === 0) {
      buf = seg;
    } else if (buf.length + 1 + seg.length <= chunkSize) {
      buf += "\n" + seg;
    } else {
      packed.push(buf);
      buf = seg;
    }
  }
  if (buf.length > 0) packed.push(buf);

  return packed.map((details, idx) => ({
    id: `${id}:${idx}`,
    headline,
    details,
    attachment_url: article.attachment_url || `/download/${id}`,
  }));
}
