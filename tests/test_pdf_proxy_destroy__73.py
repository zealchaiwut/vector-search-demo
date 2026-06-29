"""Tests for issue #73: Call pdfProxy.destroy() to prevent resource leak in extractPdfText

Acceptance Criteria derived from issue body:
  AC1 - extractPdfText calls pdfProxy.destroy() after processing all pages, before returning.
  AC2 - destroy() is called exactly once per extractPdfText invocation (no double-destroy).
  AC3 - The return value of extractPdfText is unchanged (destroy does not break the output).
"""
import os
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
# AC1 — destroy() is present in source
# ---------------------------------------------------------------------------


def test_pdf_proxy_destroy__present_in_source():
    """AC1: src/pdf/index.js contains a call to pdfProxy.destroy()."""
    with open(PDF_MODULE) as f:
        content = f.read()
    assert "pdfProxy.destroy()" in content, (
        "src/pdf/index.js must call pdfProxy.destroy() to release the PDF worker/WASM instance"
    )


def test_pdf_proxy_destroy__awaited():
    """AC1: The destroy() call is awaited (resource release is asynchronous)."""
    with open(PDF_MODULE) as f:
        content = f.read()
    assert "await pdfProxy.destroy()" in content, (
        "pdfProxy.destroy() must be awaited in src/pdf/index.js"
    )


# ---------------------------------------------------------------------------
# AC1/AC2 — destroy() is called at runtime, exactly once, per invocation
# ---------------------------------------------------------------------------


def test_pdf_proxy_destroy__called_at_runtime():
    """AC1/AC2: destroy() is called exactly once per extractPdfText call."""
    script = r"""
import { PDFDocument } from 'pdf-lib';
import { extractPdfText } from './src/pdf/index.js';
import { getDocumentProxy } from 'unpdf';

// Patch getDocumentProxy to intercept pdfProxy and spy on destroy()
let destroyCallCount = 0;
const originalGet = getDocumentProxy;

// We need to monkey-patch at the module level via a wrapper approach.
// Instead, we'll create a minimal PDF and verify destroy() was called
// by patching the prototype.

// Create a minimal text-only PDF (one page with embedded text so OCR is skipped)
import { StandardFonts } from 'pdf-lib';

const pdfDoc = await PDFDocument.create();
const font = await pdfDoc.embedFont(StandardFonts.Helvetica);
const page = pdfDoc.addPage([595, 842]);
page.drawText('Hello world', { x: 50, y: 700, size: 12, font });
const pdfBytes = await pdfDoc.save();
const pdfBuffer = Buffer.from(pdfBytes);

const mockOcr = { async recognize() { return ''; } };

// Patch the PDFDocumentProxy prototype to spy on destroy
const pdfProxy = await getDocumentProxy(new Uint8Array(pdfBuffer));
const proto = Object.getPrototypeOf(pdfProxy);
const originalDestroy = proto.destroy;
proto.destroy = async function(...args) {
  destroyCallCount++;
  return originalDestroy.apply(this, args);
};

// Now call extractPdfText — it will use patched instances going forward
await extractPdfText(pdfBuffer, mockOcr);

if (destroyCallCount === 0) {
  process.stderr.write('pdfProxy.destroy() was never called\n');
  process.exit(1);
}
if (destroyCallCount > 1) {
  process.stderr.write(`pdfProxy.destroy() was called ${destroyCallCount} times (expected 1)\n`);
  process.exit(1);
}

process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"destroy() runtime spy test failed.\nstdout: {out}\nstderr: {err}"
    assert out.strip() == "ok"


# ---------------------------------------------------------------------------
# AC3 — return value is unchanged
# ---------------------------------------------------------------------------


def test_pdf_proxy_destroy__output_unchanged():
    """AC3: Adding destroy() does not change the text returned by extractPdfText."""
    script = r"""
import { PDFDocument, StandardFonts } from 'pdf-lib';
import { extractPdfText } from './src/pdf/index.js';

const pdfDoc = await PDFDocument.create();
const font = await pdfDoc.embedFont(StandardFonts.Helvetica);
const page = pdfDoc.addPage([595, 842]);
page.drawText('Resource leak test', { x: 50, y: 700, size: 12, font });
const pdfBytes = await pdfDoc.save();
const pdfBuffer = Buffer.from(pdfBytes);

const mockOcr = { async recognize() { return ''; } };
const result = await extractPdfText(pdfBuffer, mockOcr);

if (!result.includes('Resource leak test')) {
  process.stderr.write(`Expected "Resource leak test" in output, got: ${JSON.stringify(result)}\n`);
  process.exit(1);
}

process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"Output unchanged test failed.\nstdout: {out}\nstderr: {err}"
    assert out.strip() == "ok"
