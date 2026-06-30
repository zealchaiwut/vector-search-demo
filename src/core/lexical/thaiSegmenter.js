/**
 * Thai word segmentation using Intl.Segmenter.
 *
 * Segments Thai text into individual word tokens joined by spaces, so that
 * to_tsvector('simple', segmented) produces one lexeme per Thai word instead
 * of treating the whole unsegmented run as a single token.
 *
 * Mixed text (Thai + Latin) has only the Thai portions segmented; Latin
 * words already have natural whitespace boundaries and are passed through as-is.
 */

const THAI_RE = /[฀-๿]/;

let _segmenter = null;

function getSegmenter() {
  if (!_segmenter) {
    _segmenter = new Intl.Segmenter('th', { granularity: 'word' });
  }
  return _segmenter;
}

/**
 * Segment Thai text into space-separated word tokens.
 * Non-Thai text is returned unchanged.
 *
 * @param {string} text
 * @returns {string}
 */
export function segmentThai(text) {
  if (!text || !THAI_RE.test(text)) return text;
  try {
    const segmenter = getSegmenter();
    return [...segmenter.segment(text)]
      .filter((s) => s.isWordLike)
      .map((s) => s.segment)
      .join(' ');
  } catch {
    return text;
  }
}

/**
 * Tokenise a query into individual terms for OR tsquery construction.
 * Thai queries are word-segmented first; then all text is split on whitespace.
 *
 * @param {string} query
 * @returns {string[]} Array of word tokens
 */
export function tokeniseQuery(query) {
  const trimmed = (query ?? '').trim();
  if (!trimmed) return [];
  const segmented = THAI_RE.test(trimmed) ? segmentThai(trimmed) : trimmed;
  return segmented.split(/\s+/).filter(Boolean);
}
