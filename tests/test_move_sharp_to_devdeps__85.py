"""Tests for issue #85: Move sharp from dependencies to devDependencies

Acceptance Criteria:
  AC1 - sharp is listed under devDependencies in package.json, not under dependencies
  AC2 - sharp is absent from the dependencies block in package.json
  AC3 - npm install --production no longer pulls sharp (verified structurally: sharp in
        devDependencies means production installs skip it)
  AC4 - No other package.json fields (version, other deps) are altered as a side effect
"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
PACKAGE_JSON = REPO_ROOT / "package.json"

SHARP_PKG = "sharp"
SHARP_VERSION = "^0.32.6"


def _load_pkg():
    with open(PACKAGE_JSON) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# AC1 — sharp is under devDependencies
# ---------------------------------------------------------------------------


def test_sharp_in_dev_dependencies():
    """AC1: sharp is listed under devDependencies in package.json"""
    pkg = _load_pkg()
    dev_deps = pkg.get("devDependencies", {})
    assert SHARP_PKG in dev_deps, (
        f"'{SHARP_PKG}' must be listed under 'devDependencies' in package.json, "
        f"found dev keys: {list(dev_deps.keys())}"
    )


def test_sharp_dev_dependency_version():
    """AC1: sharp version in devDependencies is ^0.32.6"""
    pkg = _load_pkg()
    dev_deps = pkg.get("devDependencies", {})
    version = dev_deps.get(SHARP_PKG)
    assert version == SHARP_VERSION, (
        f"'{SHARP_PKG}' version in devDependencies should be '{SHARP_VERSION}', "
        f"got: {version!r}"
    )


# ---------------------------------------------------------------------------
# AC2 — sharp is absent from dependencies
# ---------------------------------------------------------------------------


def test_sharp_absent_from_dependencies():
    """AC2: sharp is NOT listed under dependencies in package.json"""
    pkg = _load_pkg()
    deps = pkg.get("dependencies", {})
    assert SHARP_PKG not in deps, (
        f"'{SHARP_PKG}' must NOT appear in 'dependencies'; it should only be in devDependencies."
    )


# ---------------------------------------------------------------------------
# AC3 — sharp is skipped by npm install --production
# ---------------------------------------------------------------------------


def test_sharp_in_devdeps_means_skipped_on_production_install():
    """AC3: sharp in devDependencies means it is excluded from npm install --production"""
    pkg = _load_pkg()
    dev_deps = pkg.get("devDependencies", {})
    deps = pkg.get("dependencies", {})
    # devDependencies are skipped by `npm install --production` and `npm ci --production`
    assert SHARP_PKG in dev_deps, (
        f"'{SHARP_PKG}' must be in devDependencies for production installs to skip it"
    )
    assert SHARP_PKG not in deps, (
        f"'{SHARP_PKG}' must NOT be in dependencies (would still be installed with --production)"
    )


# ---------------------------------------------------------------------------
# AC4 — no other package.json fields altered
# ---------------------------------------------------------------------------


def test_no_other_fields_altered():
    """AC4: version, optionalDependencies, scripts, and other dependency keys are unchanged"""
    pkg = _load_pkg()

    assert pkg.get("version") == "0.1.0", (
        f"package.json version changed unexpectedly: {pkg.get('version')!r}"
    )

    assert pkg.get("name") == "vector-search-demo", (
        f"package.json name changed unexpectedly: {pkg.get('name')!r}"
    )

    # @napi-rs/canvas must still be in optionalDependencies (not regressed)
    optional = pkg.get("optionalDependencies", {})
    assert "@napi-rs/canvas" in optional, (
        "@napi-rs/canvas must still be in optionalDependencies (not regressed by this change)"
    )

    # Core production deps (sharp excluded) are all still present
    expected_prod_deps = {
        "@xenova/transformers",
        "@zilliz/milvus2-sdk-node",
        "commander",
        "fastify",
        "mammoth",
        "pg",
        "pgvector",
        "tesseract.js",
        "unpdf",
    }
    actual_deps = set(pkg.get("dependencies", {}).keys())
    assert actual_deps == expected_prod_deps, (
        f"dependencies keys changed unexpectedly.\n"
        f"  Expected: {sorted(expected_prod_deps)}\n"
        f"  Got:      {sorted(actual_deps)}"
    )

    # devDependencies must include sharp and the existing tools
    expected_dev_deps = {"@types/node", "pdf-lib", "tsx", "typescript", SHARP_PKG}
    actual_dev_deps = set(pkg.get("devDependencies", {}).keys())
    assert actual_dev_deps == expected_dev_deps, (
        f"devDependencies changed unexpectedly.\n"
        f"  Expected: {sorted(expected_dev_deps)}\n"
        f"  Got:      {sorted(actual_dev_deps)}"
    )
