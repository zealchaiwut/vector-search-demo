/**
 * PDF text extraction service.
 *
 * Uses the embedded text layer for pages that have one; falls back to OCR
 * (via the injected {@link Ocr} engine) for image-only (scanned) pages.
 */

import { getDocumentProxy, extractImages } from 'unpdf';
import sharp from 'sharp';

/**
 * Extract all text from a PDF buffer.
 *
 * @param {Buffer} pdfBuffer - Raw PDF bytes
 * @param {import('../ocr/index.js').Ocr} ocr - OCR engine for pages without a text layer
 * @returns {Promise<string>} Full document text in page order
 */
export async function extractPdfText(pdfBuffer, ocr) {
  const data = new Uint8Array(pdfBuffer);
  const pdfProxy = await getDocumentProxy(data);
  const { numPages } = pdfProxy;

  const pageResults = [];

  for (let pageNum = 1; pageNum <= numPages; pageNum++) {
    const page = await pdfProxy.getPage(pageNum);

    const textContent = await page.getTextContent();
    const embeddedText = textContent.items
      .map((item) => ('str' in item ? item.str : ''))
      .join(' ')
      .trim();

    if (embeddedText.length > 0) {
      pageResults.push(embeddedText);
    } else {
      // Rasterize: extract embedded images and send to OCR
      const ocrText = await _ocrPage(pdfProxy, pageNum, ocr);
      pageResults.push(ocrText);
    }

    page.cleanup();
  }

  return pageResults.join('\n');
}

/**
 * Rasterize a page by extracting its embedded image(s) and running OCR.
 *
 * @param {import('unpdf').PDFDocumentProxy} pdfProxy
 * @param {number} pageNum
 * @param {import('../ocr/index.js').Ocr} ocr
 * @returns {Promise<string>}
 */
async function _ocrPage(pdfProxy, pageNum, ocr) {
  const images = await extractImages(pdfProxy, pageNum);

  if (images.length === 0) {
    return '';
  }

  // Convert every fragment to PNG, then composite all of them top-to-bottom.
  // This ensures text in every fragment on a scanned page reaches OCR.
  const fragmentBuffers = await Promise.all(
    images.map((img) =>
      sharp(Buffer.from(img.data.buffer), {
        raw: { width: img.width, height: img.height, channels: img.channels },
      })
        .png()
        .toBuffer()
    )
  );

  const totalHeight = images.reduce((sum, img) => sum + img.height, 0);
  const maxWidth = Math.max(...images.map((img) => img.width));

  let yOffset = 0;
  const composites = fragmentBuffers.map((buf, i) => {
    const entry = { input: buf, top: yOffset, left: 0 };
    yOffset += images[i].height;
    return entry;
  });

  const imageBuffer = await sharp({
    create: { width: maxWidth, height: totalHeight, channels: 3, background: { r: 255, g: 255, b: 255 } },
  })
    .composite(composites)
    .png()
    .toBuffer();

  return ocr.recognize(imageBuffer);
}
