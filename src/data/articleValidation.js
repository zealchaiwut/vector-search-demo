const URL_PATTERN = /^https?:\/\//;
const ARTICLE_ID_PATTERN = /^[a-zA-Z0-9_-]+$/;

/**
 * Validates an articleId against the safe pattern (alphanumeric, hyphens, underscores).
 * Returns null when valid, or a descriptive error string when invalid.
 */
export function validateArticleId(articleId) {
  if (!articleId || !ARTICLE_ID_PATTERN.test(articleId)) {
    return "Invalid article id: must contain only letters, digits, hyphens, and underscores";
  }
  return null;
}

/**
 * Validates article fields. Returns an array of {field, message} error objects.
 * An empty array means all fields are valid.
 */
export function validateArticle(headline, details, attachment_url) {
  const errors = [];

  const h = (headline ?? "").trim();
  if (!h) {
    console.warn(`[WARN] validation: headline is required (received: ${JSON.stringify(headline)})`);
    errors.push({ field: "headline", message: "headline is required" });
  }

  const d = (details ?? "").trim();
  if (!d) {
    console.warn(`[WARN] validation: details is required (received: ${JSON.stringify(details)})`);
    errors.push({ field: "details", message: "details is required" });
  }

  const u = (attachment_url ?? "").trim();
  if (u && !URL_PATTERN.test(u)) {
    console.warn(`[WARN] validation: attachment_url must be a valid http or https URL (received: ${JSON.stringify(u)})`);
    errors.push({ field: "attachment_url", message: "attachment_url must be a valid http or https URL" });
  }

  return errors;
}
