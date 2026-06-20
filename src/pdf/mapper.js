/**
 * Maps extracted PDF text and optional metadata to an add-article JSON shape.
 *
 * @param {string} text - Full extracted text from the PDF
 * @param {{ title?: string, fileName?: string, attachmentUrl?: string }} [options]
 * @returns {{ headline: string, details: string, attachment_url: string }}
 */
export function mapPdfToArticle(text, options = {}) {
  const { title, fileName, attachmentUrl } = options;
  return {
    headline: _deriveHeadline(text, title, fileName),
    details: _normalizeWhitespace(text),
    attachment_url: attachmentUrl ?? '',
  };
}

/**
 * @param {string} text
 * @param {string|undefined} title
 * @param {string|undefined} fileName
 * @returns {string}
 */
function _deriveHeadline(text, title, fileName) {
  const t = (title ?? '').trim();
  if (t) return t;

  const firstNonEmpty = (text ?? '').split('\n').find((line) => line.trim());
  if (firstNonEmpty !== undefined) {
    const line = firstNonEmpty.trim();
    // Single-line PDF extraction can yield one very long "line"; keep headline short.
    if (line.length > 200) return _shortExcerpt(line);
    return line;
  }

  return (fileName ?? '').trim();
}

/** @param {string} text */
function _shortExcerpt(text) {
  const sentenceEnd = text.search(/[.!?。]\s/u);
  if (sentenceEnd > 0 && sentenceEnd <= 200) return text.slice(0, sentenceEnd + 1).trim();
  return text.length > 120 ? `${text.slice(0, 120).trim()}…` : text.trim();
}

/**
 * Trims each line and collapses runs of multiple blank lines into one.
 *
 * @param {string} text
 * @returns {string}
 */
function _normalizeWhitespace(text) {
  if (!text) return '';
  const lines = text.split('\n').map((l) => l.trim());
  const out = [];
  let blankRun = 0;
  for (const line of lines) {
    if (line === '') {
      blankRun++;
      if (blankRun === 1) out.push('');
    } else {
      blankRun = 0;
      out.push(line);
    }
  }
  return out.join('\n').trim();
}
