/**
 * Word (.docx) text extraction service.
 */

import mammoth from "mammoth";

/**
 * Extract plain text from a DOCX buffer.
 *
 * @param {Buffer} docxBuffer - Raw .docx bytes
 * @returns {Promise<string>} Document text
 */
export async function extractDocxText(docxBuffer) {
  const { value } = await mammoth.extractRawText({ buffer: docxBuffer });
  return (value ?? "").trim();
}
