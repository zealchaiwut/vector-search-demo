/**
 * OCR interface and default Tesseract implementation.
 *
 * @typedef {{ recognize(image: Buffer): Promise<string> }} Ocr
 */

import Tesseract from 'tesseract.js';
import sharp from 'sharp';

/**
 * TesseractOcr — default OCR implementation using Tesseract.js.
 *
 * Applies grayscale + threshold preprocessing via sharp before passing the
 * image to Tesseract with the Thai (`tha`) language pack.
 *
 * @implements {Ocr}
 */
export class TesseractOcr {
  /**
   * Recognize text in an image buffer.
   *
   * @param {Buffer} imageBuffer - Raw image data (PNG, JPEG, etc.)
   * @returns {Promise<string>} Recognized text
   */
  async recognize(imageBuffer) {
    const preprocessed = await sharp(imageBuffer)
      .grayscale()
      .threshold(128)
      .toBuffer();

    const { data: { text } } = await Tesseract.recognize(preprocessed, 'tha');
    return text.trim();
  }
}
