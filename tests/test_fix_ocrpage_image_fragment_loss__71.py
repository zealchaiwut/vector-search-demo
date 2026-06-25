"""Tests for issue #71: Fix misleading comment and silent image-fragment loss in _ocrPage

Acceptance Criteria derived from issue body:
  AC1 - The misleading comment "Combine multiple image fragments … or use largest" is
        removed; the actual behaviour is accurately documented (composite all or no claim
        of compositing where there is none).
  AC2 - When a scanned page contains multiple image fragments, ALL of them are composited
        into a single image sent to OCR — none are silently discarded.
  AC3 - Single-fragment pages still work correctly (regression: OCR receives a valid buffer).
  AC4 - The composited image passed to OCR has a height equal to the sum of the individual
        fragment heights (all fragments stacked top-to-bottom).
"""
import os
import re
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_MODULE = os.path.join(REPO_ROOT, "src", "pdf", "index.js")

NODE_TIMEOUT = 120


def _run_node(script, timeout=NODE_TIMEOUT):
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
    )
    return result.stdout, result.stderr, result.returncode


# ---------------------------------------------------------------------------
# AC1 — misleading comment is gone
# ---------------------------------------------------------------------------


def test_ocrpage__misleading_comment_removed():
    """AC1: The source no longer contains the misleading 'or use largest' comment."""
    with open(PDF_MODULE) as f:
        content = f.read()
    assert "or use largest" not in content, (
        "Misleading comment 'or use largest' must be removed from src/pdf/index.js"
    )


def test_ocrpage__reduce_largest_select_removed():
    """AC1: The 'reduce' that picks only the largest image by area is no longer present."""
    with open(PDF_MODULE) as f:
        content = f.read()
    # The original reduce selected the largest fragment; compositing should replace this
    assert not re.search(r"reduce\(.*width.*height.*>=.*width.*height", content, re.DOTALL), (
        "Largest-area image selection via reduce must be replaced with compositing logic"
    )


# ---------------------------------------------------------------------------
# AC3 — single-fragment pages still work
# ---------------------------------------------------------------------------


def test_ocrpage__single_fragment_ocr_called():
    """AC3: A page with one image fragment still triggers OCR and returns the result."""
    script = r"""
import { PDFDocument } from 'pdf-lib';
import sharp from 'sharp';
import { extractPdfText } from './src/pdf/index.js';

const svgImage = `<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
  <rect width="100%" height="100%" fill="white"/>
  <text x="10" y="60" font-size="30" font-family="serif" fill="black">SINGLE</text>
</svg>`;
const pngBuffer = await sharp(Buffer.from(svgImage)).png().toBuffer();

const pdfDoc = await PDFDocument.create();
const page = pdfDoc.addPage([595, 842]);
const pngImage = await pdfDoc.embedPng(pngBuffer);
page.drawImage(pngImage, { x: 50, y: 600, width: 200, height: 100 });
const pdfBytes = await pdfDoc.save();
const pdfBuffer = Buffer.from(pdfBytes);

let ocrCallCount = 0;
const mockOcr = {
  async recognize(imageBuffer) {
    ocrCallCount++;
    return 'SINGLE_FRAGMENT_RESULT';
  }
};

const result = await extractPdfText(pdfBuffer, mockOcr);

if (ocrCallCount === 0) {
  process.stderr.write('OCR was never called for a single-fragment page\n');
  process.exit(1);
}
if (!result.includes('SINGLE_FRAGMENT_RESULT')) {
  process.stderr.write(`Expected OCR result in output, got: ${JSON.stringify(result)}\n`);
  process.exit(1);
}

process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Single-fragment test failed.\nstdout: {out}\nstderr: {err}"
    assert out.strip() == "ok"


# ---------------------------------------------------------------------------
# AC2, AC4 — multi-fragment pages: all fragments composited
# ---------------------------------------------------------------------------


def test_ocrpage__multi_fragment_all_included():
    """AC2/AC4: A page with two image fragments sends a composited image to OCR whose
    height equals the sum of both fragment heights."""
    script = r"""
import { PDFDocument } from 'pdf-lib';
import sharp from 'sharp';
import { extractPdfText } from './src/pdf/index.js';

// Fragment A: 300 x 80
const svgA = `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="80">
  <rect width="100%" height="100%" fill="white"/>
  <text x="10" y="55" font-size="36" font-family="serif" fill="black">FRAGMENT A</text>
</svg>`;
// Fragment B: 200 x 60 (smaller — the old code would have discarded this one)
const svgB = `<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60">
  <rect width="100%" height="100%" fill="white"/>
  <text x="10" y="42" font-size="28" font-family="serif" fill="black">FRAG B</text>
</svg>`;

const pngA = await sharp(Buffer.from(svgA)).png().toBuffer();
const pngB = await sharp(Buffer.from(svgB)).png().toBuffer();

// Get the real dimensions back from the PNG metadata
const metaA = await sharp(pngA).metadata();
const metaB = await sharp(pngB).metadata();
const expectedMinHeight = metaA.height + metaB.height; // composite stacks them

const pdfDoc = await PDFDocument.create();
const page = pdfDoc.addPage([595, 842]);

const imgA = await pdfDoc.embedPng(pngA);
const imgB = await pdfDoc.embedPng(pngB);

// Place them at different y positions on the same page
page.drawImage(imgA, { x: 50, y: 650, width: 300, height: 80 });
page.drawImage(imgB, { x: 50, y: 550, width: 200, height: 60 });

const pdfBytes = await pdfDoc.save();
const pdfBuffer = Buffer.from(pdfBytes);

let receivedBuffer = null;
const mockOcr = {
  async recognize(imageBuffer) {
    receivedBuffer = imageBuffer;
    return 'COMPOSITED_RESULT';
  }
};

const result = await extractPdfText(pdfBuffer, mockOcr);

if (!result.includes('COMPOSITED_RESULT')) {
  process.stderr.write(`Expected COMPOSITED_RESULT in output, got: ${JSON.stringify(result)}\n`);
  process.exit(1);
}

if (!receivedBuffer) {
  process.stderr.write('OCR was never called\n');
  process.exit(1);
}

// Inspect the image the OCR received
const receivedMeta = await sharp(receivedBuffer).metadata();
if (receivedMeta.height < expectedMinHeight) {
  process.stderr.write(
    `Expected composited image height >= ${expectedMinHeight} ` +
    `(${metaA.height} + ${metaB.height}), got: ${receivedMeta.height}\n`
  );
  process.exit(1);
}

process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Multi-fragment test failed.\nstdout: {out}\nstderr: {err}"
    assert out.strip() == "ok"
