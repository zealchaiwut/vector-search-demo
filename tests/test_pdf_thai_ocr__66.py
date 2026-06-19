"""Tests for issue #66: Add PDF text extraction service with Thai OCR

Acceptance Criteria:
  AC1  - src/pdf contains extractor module accepting a PDF and returning full plain text
  AC2  - Extractor uses PDF parser to extract embedded text layer first
  AC3  - Pages with no usable embedded text are rasterized and sent to OCR engine
  AC4  - Pages with embedded text are NEVER sent to OCR
  AC5  - src/ocr defines Ocr interface with recognize(image): Promise<string>
  AC6  - src/ocr provides TesseractOcr using 'tha' (Thai) language data
  AC7  - TesseractOcr applies grayscale + threshold via sharp before passing to Tesseract
  AC8  - Extractor resolves OCR through Ocr interface (dependency-injected)
  AC9  - New OCR engine can be added by implementing Ocr and injecting it without modifying extractor
  AC10 - Tests cover: (a) PDF with full text layer returns text without OCR calls,
                      (b) scanned page goes through OCR
"""
import os
import re
import subprocess
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OCR_MODULE = os.path.join(REPO_ROOT, "src", "ocr", "index.js")
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
# AC1, AC5 — module files exist
# ---------------------------------------------------------------------------

def test_pdf_ocr__ocr_module_exists():
    """AC5: src/ocr/index.js exists"""
    assert os.path.isfile(OCR_MODULE), f"src/ocr/index.js not found at {OCR_MODULE}"


def test_pdf_ocr__pdf_module_exists():
    """AC1: src/pdf/index.js exists"""
    assert os.path.isfile(PDF_MODULE), f"src/pdf/index.js not found at {PDF_MODULE}"


# ---------------------------------------------------------------------------
# AC5 — Ocr interface typedef
# ---------------------------------------------------------------------------

def test_pdf_ocr__ocr_interface_defined():
    """AC5: src/ocr/index.js defines an Ocr interface (via @typedef or class contract) with recognize()"""
    with open(OCR_MODULE) as f:
        content = f.read()
    # Either a JSDoc typedef or a class-based interface definition
    has_interface = (
        re.search(r"@typedef.*Ocr", content) or
        re.search(r"recognize\s*\(", content)
    )
    assert has_interface, "src/ocr/index.js must define an Ocr interface with a recognize() method"


# ---------------------------------------------------------------------------
# AC6 — TesseractOcr exported and uses tha language
# ---------------------------------------------------------------------------

def test_pdf_ocr__tesseractocr_exported():
    """AC6: TesseractOcr class is exported from src/ocr/index.js"""
    with open(OCR_MODULE) as f:
        content = f.read()
    assert "export class TesseractOcr" in content or "export { TesseractOcr" in content, \
        "TesseractOcr must be exported from src/ocr/index.js"


def test_pdf_ocr__tesseractocr_uses_tha_language():
    """AC6: TesseractOcr uses 'tha' Thai language data"""
    with open(OCR_MODULE) as f:
        content = f.read()
    assert "'tha'" in content or '"tha"' in content, \
        "TesseractOcr must use 'tha' language data for Tesseract"


def test_pdf_ocr__tesseractocr_uses_tesseract_js():
    """AC6: TesseractOcr imports tesseract.js"""
    with open(OCR_MODULE) as f:
        content = f.read()
    assert "tesseract.js" in content or "Tesseract" in content, \
        "TesseractOcr must use tesseract.js"


# ---------------------------------------------------------------------------
# AC7 — TesseractOcr applies grayscale + threshold via sharp
# ---------------------------------------------------------------------------

def test_pdf_ocr__tesseractocr_uses_sharp_grayscale():
    """AC7: TesseractOcr applies sharp grayscale preprocessing"""
    with open(OCR_MODULE) as f:
        content = f.read()
    assert "grayscale" in content, \
        "TesseractOcr must apply grayscale preprocessing via sharp"


def test_pdf_ocr__tesseractocr_uses_sharp_threshold():
    """AC7: TesseractOcr applies sharp threshold preprocessing"""
    with open(OCR_MODULE) as f:
        content = f.read()
    assert "threshold" in content, \
        "TesseractOcr must apply threshold preprocessing via sharp"


def test_pdf_ocr__tesseractocr_imports_sharp():
    """AC7: src/ocr/index.js imports sharp"""
    with open(OCR_MODULE) as f:
        content = f.read()
    assert "sharp" in content, \
        "src/ocr/index.js must import sharp for image preprocessing"


# ---------------------------------------------------------------------------
# AC1, AC8 — extractPdfText exported and dependency-injected
# ---------------------------------------------------------------------------

def test_pdf_ocr__extract_function_exported():
    """AC1: extractPdfText is exported from src/pdf/index.js"""
    with open(PDF_MODULE) as f:
        content = f.read()
    assert "export" in content and "extractPdfText" in content, \
        "extractPdfText must be exported from src/pdf/index.js"


def test_pdf_ocr__extractor_takes_ocr_param():
    """AC8: extractPdfText accepts an OCR engine as a parameter (dependency injection)"""
    with open(PDF_MODULE) as f:
        content = f.read()
    # Function signature should have two params: PDF buffer + ocr engine
    match = re.search(r"function\s+extractPdfText\s*\(([^)]+)\)", content)
    assert match, "extractPdfText must be defined as a function"
    params = match.group(1)
    assert "," in params, \
        "extractPdfText must accept at least 2 parameters (pdfBuffer, ocr)"


def test_pdf_ocr__extractor_no_direct_tesseractocr_import():
    """AC8, AC9: src/pdf/index.js does not import TesseractOcr directly — OCR is injected"""
    with open(PDF_MODULE) as f:
        content = f.read()
    assert "TesseractOcr" not in content, \
        "src/pdf/index.js must not import TesseractOcr — the OCR engine is dependency-injected"


def test_pdf_ocr__extractor_uses_unpdf_or_pdfjs():
    """AC2: src/pdf/index.js imports unpdf or pdfjs for PDF parsing"""
    with open(PDF_MODULE) as f:
        content = f.read()
    uses_pdf_lib = "unpdf" in content or "pdfjs" in content
    assert uses_pdf_lib, \
        "src/pdf/index.js must use unpdf or pdfjs for PDF text extraction"


# ---------------------------------------------------------------------------
# AC3, AC4 — rasterize scanned pages, skip text pages
# ---------------------------------------------------------------------------

def test_pdf_ocr__extractor_rasterizes_for_ocr():
    """AC3: src/pdf/index.js rasterizes pages without text (via image extraction or rendering)"""
    with open(PDF_MODULE) as f:
        content = f.read()
    # Must use an image extraction/rendering approach for OCR fallback
    has_rasterize = (
        "renderPageAsImage" in content or
        "extractImages" in content or
        ("render" in content.lower() and "image" in content.lower())
    )
    assert has_rasterize, \
        "src/pdf/index.js must extract/rasterize page images (e.g. extractImages) for OCR fallback"


def test_pdf_ocr__extractor_calls_ocr_recognize():
    """AC3, AC8: src/pdf/index.js calls ocr.recognize() for image pages"""
    with open(PDF_MODULE) as f:
        content = f.read()
    assert "ocr.recognize" in content or ".recognize(" in content, \
        "src/pdf/index.js must call ocr.recognize() for scanned pages"


# ---------------------------------------------------------------------------
# AC10a — PDF with full text layer returns text without OCR calls (functional)
# ---------------------------------------------------------------------------

def test_pdf_ocr__text_pdf_returns_embedded_text_no_ocr():
    """AC4, AC10a: PDF with embedded text layer returns text; OCR is never called"""
    script = r"""
import { PDFDocument, rgb, StandardFonts } from 'pdf-lib';
import { extractPdfText } from './src/pdf/index.js';

// Create a PDF with embedded text using pdf-lib
const pdfDoc = await PDFDocument.create();
const page = pdfDoc.addPage([595, 842]);
const font = await pdfDoc.embedFont(StandardFonts.Helvetica);
page.drawText('Hello World from embedded text', {
  x: 50,
  y: 700,
  size: 16,
  font,
  color: rgb(0, 0, 0),
});
const pdfBytes = await pdfDoc.save();
const pdfBuffer = Buffer.from(pdfBytes);

// Mock OCR that records calls
let ocrCallCount = 0;
const mockOcr = {
  async recognize(imageBuffer) {
    ocrCallCount++;
    return 'OCR SHOULD NOT BE CALLED';
  }
};

const result = await extractPdfText(pdfBuffer, mockOcr);

if (ocrCallCount !== 0) {
  process.stderr.write(`OCR was called ${ocrCallCount} time(s) for a text PDF — expected 0 calls\n`);
  process.exit(1);
}
if (!result.includes('Hello World')) {
  process.stderr.write(`Expected embedded text to contain "Hello World", got: ${JSON.stringify(result)}\n`);
  process.exit(1);
}

process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Test failed.\nstdout: {out}\nstderr: {err}"
    assert out.strip() == "ok"


# ---------------------------------------------------------------------------
# AC3, AC10b — scanned page (no text layer) is sent to OCR
# ---------------------------------------------------------------------------

def test_pdf_ocr__scanned_page_calls_ocr():
    """AC3, AC10b: Page with no embedded text is rasterized and sent to OCR"""
    script = r"""
import { PDFDocument, rgb } from 'pdf-lib';
import sharp from 'sharp';
import { extractPdfText } from './src/pdf/index.js';

// Create a PDF page with an embedded PNG image but NO text layer
const svgImage = `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="100">
  <rect width="100%" height="100%" fill="white"/>
  <text x="10" y="70" font-size="40" font-family="serif" fill="black">OCR TEXT</text>
</svg>`;
const pngBuffer = await sharp(Buffer.from(svgImage)).png().toBuffer();

const pdfDoc = await PDFDocument.create();
const page = pdfDoc.addPage([595, 842]);
const pngImage = await pdfDoc.embedPng(pngBuffer);
page.drawImage(pngImage, { x: 50, y: 600, width: 300, height: 100 });
const pdfBytes = await pdfDoc.save();
const pdfBuffer = Buffer.from(pdfBytes);

// Mock OCR that records calls and returns fixed text
let ocrCallCount = 0;
const mockOcr = {
  async recognize(imageBuffer) {
    ocrCallCount++;
    return 'mock-ocr-result';
  }
};

const result = await extractPdfText(pdfBuffer, mockOcr);

if (ocrCallCount === 0) {
  process.stderr.write('OCR was never called for a page with no text layer — expected at least 1 call\n');
  process.exit(1);
}
if (!result.includes('mock-ocr-result')) {
  process.stderr.write(`Expected OCR result in output, got: ${JSON.stringify(result)}\n`);
  process.exit(1);
}

process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Test failed.\nstdout: {out}\nstderr: {err}"
    assert out.strip() == "ok"


# ---------------------------------------------------------------------------
# AC9 — stub OCR injection works without modifying extractor
# ---------------------------------------------------------------------------

def test_pdf_ocr__stub_ocr_accepted():
    """AC9: A custom stub Ocr implementation works without any changes to src/pdf"""
    script = r"""
import { PDFDocument } from 'pdf-lib';
import sharp from 'sharp';
import { extractPdfText } from './src/pdf/index.js';

// Create a PDF with an image-only page (no text layer)
const svgImage = '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="80"><rect width="100%" height="100%" fill="white"/></svg>';
const pngBuffer = await sharp(Buffer.from(svgImage)).png().toBuffer();
const pdfDoc = await PDFDocument.create();
const page = pdfDoc.addPage([595, 842]);
const pngImage = await pdfDoc.embedPng(pngBuffer);
page.drawImage(pngImage, { x: 50, y: 600, width: 200, height: 80 });
const pdfBytes = await pdfDoc.save();
const pdfBuffer = Buffer.from(pdfBytes);

// Custom stub OCR — returns a fixed sentinel string without any changes to src/pdf
class StubOcr {
  async recognize(imageBuffer) {
    return 'STUB_SENTINEL_OUTPUT';
  }
}

const result = await extractPdfText(pdfBuffer, new StubOcr());

if (!result.includes('STUB_SENTINEL_OUTPUT')) {
  process.stderr.write(`Expected STUB_SENTINEL_OUTPUT in result, got: ${JSON.stringify(result)}\n`);
  process.exit(1);
}

process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Test failed.\nstdout: {out}\nstderr: {err}"
    assert out.strip() == "ok"


# ---------------------------------------------------------------------------
# AC5, AC6 — TesseractOcr functional: recognize() returns a string
# ---------------------------------------------------------------------------

def test_pdf_ocr__tesseractocr_recognize_returns_string():
    """AC5, AC6: TesseractOcr.recognize() accepts a Buffer and returns a string"""
    script = r"""
import { TesseractOcr } from './src/ocr/index.js';
import sharp from 'sharp';

// Create a simple white image (minimal valid PNG input)
const imageBuffer = await sharp({
  create: { width: 100, height: 50, channels: 3, background: { r: 255, g: 255, b: 255 } }
}).png().toBuffer();

const ocr = new TesseractOcr();
const result = await ocr.recognize(imageBuffer);

if (typeof result !== 'string') {
  process.stderr.write(`Expected recognize() to return a string, got: ${typeof result}\n`);
  process.exit(1);
}

process.stdout.write('ok');
"""
    out, err, rc = _run_node(script, timeout=NODE_TIMEOUT)
    assert rc == 0, f"TesseractOcr.recognize() failed.\nstdout: {out}\nstderr: {err}"
    assert out.strip() == "ok"
