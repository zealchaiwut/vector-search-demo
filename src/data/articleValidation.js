const URL_PATTERN = /^https?:\/\//;

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
