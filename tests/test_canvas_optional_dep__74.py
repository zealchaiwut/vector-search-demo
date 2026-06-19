"""Tests for issue #74: Move @napi-rs/canvas from dependencies to optionalDependencies

Acceptance Criteria:
  AC1 - @napi-rs/canvas is listed under optionalDependencies in package.json, not under dependencies
  AC2 - @napi-rs/canvas is absent from the dependencies block in package.json
  AC3 - The extractImages code path executes successfully without @napi-rs/canvas installed
  AC4 - npm install in a CI-like environment (with --ignore-optional) completes without pulling
        in @napi-rs/canvas binaries — satisfied when canvas is in optionalDependencies
  AC5 - No other package.json fields (version, other deps) are altered as a side effect
"""
import json
import os
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_JSON = os.path.join(REPO_ROOT, "package.json")
NODE_TIMEOUT = 60

CANVAS_PKG = "@napi-rs/canvas"
CANVAS_VERSION = "^0.1.100"


def _load_pkg():
    with open(PACKAGE_JSON) as f:
        return json.load(f)


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
# AC1 — @napi-rs/canvas is under optionalDependencies
# ---------------------------------------------------------------------------


def test_canvas_in_optional_deps():
    """AC1: @napi-rs/canvas is listed under optionalDependencies in package.json"""
    pkg = _load_pkg()
    optional = pkg.get("optionalDependencies", {})
    assert CANVAS_PKG in optional, (
        f"'{CANVAS_PKG}' must be listed under 'optionalDependencies' in package.json, "
        f"found keys: {list(optional.keys())}"
    )


def test_canvas_optional_dep_version():
    """AC1: @napi-rs/canvas version in optionalDependencies is ^0.1.100"""
    pkg = _load_pkg()
    optional = pkg.get("optionalDependencies", {})
    version = optional.get(CANVAS_PKG)
    assert version == CANVAS_VERSION, (
        f"'{CANVAS_PKG}' version in optionalDependencies should be '{CANVAS_VERSION}', "
        f"got: {version!r}"
    )


# ---------------------------------------------------------------------------
# AC2 — @napi-rs/canvas is absent from dependencies
# ---------------------------------------------------------------------------


def test_canvas_absent_from_dependencies():
    """AC2: @napi-rs/canvas is NOT listed under dependencies in package.json"""
    pkg = _load_pkg()
    deps = pkg.get("dependencies", {})
    assert CANVAS_PKG not in deps, (
        f"'{CANVAS_PKG}' must NOT appear in 'dependencies'; remove it from there."
    )


# ---------------------------------------------------------------------------
# AC3 — extractImages executes successfully (no canvas import required)
# ---------------------------------------------------------------------------


def test_extractimages_runs_without_canvas_error():
    """AC3: extractImages from unpdf can be imported and called without canvas errors"""
    script = r"""
import { PDFDocument, rgb } from 'pdf-lib';
import sharp from 'sharp';
import { getDocumentProxy, extractImages } from 'unpdf';

// Build a minimal PDF with one embedded PNG image (no text layer)
const svgImage = '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="80">' +
  '<rect width="100%" height="100%" fill="white"/>' +
  '<text x="10" y="60" font-size="40" font-family="serif" fill="black">TEST</text>' +
  '</svg>';
const pngBuffer = await sharp(Buffer.from(svgImage)).png().toBuffer();

const pdfDoc = await PDFDocument.create();
const page = pdfDoc.addPage([595, 842]);
const pngImage = await pdfDoc.embedPng(pngBuffer);
page.drawImage(pngImage, { x: 50, y: 600, width: 200, height: 80 });
const pdfBytes = await pdfDoc.save();

// Call extractImages — this must NOT throw a canvas-related error
let thrownError = null;
try {
  const pdfProxy = await getDocumentProxy(new Uint8Array(pdfBytes));
  const images = await extractImages(pdfProxy, 1);
  // images is an array (possibly empty); the call itself must not fail
  if (!Array.isArray(images)) {
    process.stderr.write(`extractImages returned non-array: ${typeof images}\n`);
    process.exit(1);
  }
} catch (err) {
  thrownError = err;
}

if (thrownError !== null) {
  process.stderr.write(`extractImages threw: ${thrownError.message}\n`);
  process.exit(1);
}

process.stdout.write('ok');
"""
    out, err, rc = _run_node(script)
    assert rc == 0, f"extractImages failed.\nstdout: {out}\nstderr: {err}"
    assert out.strip() == "ok"


# ---------------------------------------------------------------------------
# AC4 — package structure means --ignore-optional skips @napi-rs/canvas
# ---------------------------------------------------------------------------


def test_canvas_in_optional_deps_satisfies_ignore_optional():
    """AC4: @napi-rs/canvas in optionalDependencies means it is skipped by npm install --ignore-optional"""
    pkg = _load_pkg()
    optional = pkg.get("optionalDependencies", {})
    deps = pkg.get("dependencies", {})
    # Moving canvas to optionalDependencies is the necessary and sufficient
    # condition for npm install --ignore-optional to skip native canvas binaries.
    assert CANVAS_PKG in optional, (
        f"'{CANVAS_PKG}' must be in optionalDependencies for --ignore-optional to skip it"
    )
    assert CANVAS_PKG not in deps, (
        f"'{CANVAS_PKG}' must NOT be in dependencies (would still be installed even with --ignore-optional)"
    )


# ---------------------------------------------------------------------------
# AC5 — no other package.json fields altered
# ---------------------------------------------------------------------------


def test_no_other_fields_altered():
    """AC5: version, devDependencies, scripts, and other dependency keys are unchanged"""
    pkg = _load_pkg()

    assert pkg.get("version") == "0.1.0", (
        f"package.json version changed unexpectedly: {pkg.get('version')!r}"
    )

    expected_dev_deps = {"@types/node", "pdf-lib", "tsx", "typescript"}
    actual_dev_deps = set(pkg.get("devDependencies", {}).keys())
    assert actual_dev_deps == expected_dev_deps, (
        f"devDependencies changed. Expected {expected_dev_deps}, got {actual_dev_deps}"
    )

    expected_non_canvas_deps = {
        "@xenova/transformers",
        "@zilliz/milvus2-sdk-node",
        "commander",
        "fastify",
        "pg",
        "pgvector",
        "sharp",
        "tesseract.js",
        "unpdf",
    }
    actual_deps = set(pkg.get("dependencies", {}).keys())
    assert actual_deps == expected_non_canvas_deps, (
        f"dependencies keys changed unexpectedly.\n"
        f"  Expected: {sorted(expected_non_canvas_deps)}\n"
        f"  Got:      {sorted(actual_deps)}"
    )
