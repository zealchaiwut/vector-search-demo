/**
 * Thai text normalization module.
 *
 * Shared by ingest (document/chunk text) and search (query text) so both
 * sides operate on the same canonical form, enabling cross-variant matching.
 *
 * Transformations (when enabled):
 *   1. Unicode NFC normalization — merges decomposed character sequences
 *   2. Zero-width / formatting control characters stripped
 *   3. Thai numerals (๐-๙) → ASCII digits (0-9)
 */

// Thai digit → ASCII digit
const THAI_DIGITS = { '๐': '0', '๑': '1', '๒': '2', '๓': '3', '๔': '4', '๕': '5', '๖': '6', '๗': '7', '๘': '8', '๙': '9' };

// Zero-width and invisible formatting characters to strip:
//   U+00AD  Soft Hyphen
//   U+200B  Zero Width Space
//   U+200C  Zero Width Non-Joiner
//   U+200D  Zero Width Joiner
//   U+200E  Left-to-Right Mark
//   U+200F  Right-to-Left Mark
//   U+202A–U+202E  Bidirectional embedding/override chars
//   U+2060–U+2064  Word Joiner and invisible math chars
//   U+2066–U+206F  Bidirectional isolate chars
//   U+FEFF  Zero Width No-Break Space / BOM
const ZERO_WIDTH_RE = /[­​-‏‪-‮⁠-⁤⁦-⁯﻿]/g;

/**
 * Normalize text for indexing or querying.
 *
 * @param {string} text - Input text.
 * @param {boolean} [enabled=true] - When false, returns text unchanged.
 * @returns {string}
 */
export function normalise(text, enabled = true) {
  if (!enabled || text == null) return text;
  // Step 1: Unicode NFC
  let result = text.normalize('NFC');
  // Step 2: Strip zero-width / formatting control chars
  result = result.replace(ZERO_WIDTH_RE, '');
  // Step 3: Thai digits → ASCII digits
  result = result.replace(/[๐-๙]/g, (ch) => THAI_DIGITS[ch] ?? ch);
  return result;
}
