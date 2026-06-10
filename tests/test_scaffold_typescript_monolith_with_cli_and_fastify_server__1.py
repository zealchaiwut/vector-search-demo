"""Tests for issue #1: Scaffold TypeScript monolith with CLI and Fastify server (runs against UAT)"""
import json
import os
import socket
import subprocess
import time

import pytest
import httpx

UAT_BASE_URL = os.environ.get("UAT_BASE_URL", "http://localhost:8001")

CODER_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "coder")
)
PACKAGE_JSON = os.path.join(CODER_DIR, "package.json")
TSCONFIG    = os.path.join(CODER_DIR, "tsconfig.json")
CONFIG_TS   = os.path.join(CODER_DIR, "src", "config.ts")
CLI_TS      = os.path.join(CODER_DIR, "src", "cli.ts")
ENV_EXAMPLE = os.path.join(CODER_DIR, ".env.example")
GITIGNORE   = os.path.join(CODER_DIR, ".gitignore")
DIST_CLI    = os.path.join(CODER_DIR, "dist", "cli.js")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def fastify_url():
    """Start dist/cli.js serve on a free port; yield URL; kill after module."""
    if not os.path.isfile(DIST_CLI):
        pytest.skip("dist/cli.js not present — run npm run build first")
    port = _free_port()
    proc = subprocess.Popen(
        ["node", DIST_CLI, "serve"],
        cwd=CODER_DIR,
        env={**os.environ, "PORT": str(port)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("localhost", port), timeout=0.3):
                break
        except OSError:
            time.sleep(0.2)
    yield f"http://localhost:{port}"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ---------------------------------------------------------------------------
# AC1 — package.json: commander bin + build/dev/start/typecheck scripts
# ---------------------------------------------------------------------------

def test_scaffold_typescript_monolith_with_cli_and_fastify_server__package_json_bin_and_scripts():
    # AC1: bin.commander defined; scripts build(tsc), dev(tsx+src/cli.ts), start, typecheck(tsc --noEmit)
    with open(PACKAGE_JSON) as f:
        pkg = json.load(f)
    assert "commander" in pkg.get("bin", {}), "bin.commander must be defined"
    scripts = pkg.get("scripts", {})
    assert "build" in scripts and "tsc" in scripts["build"], "scripts.build must invoke tsc"
    assert "dev" in scripts and "tsx" in scripts["dev"] and "src/cli.ts" in scripts["dev"], \
        "scripts.dev must use tsx with src/cli.ts"
    assert "start" in scripts, "scripts.start must be defined"
    assert "typecheck" in scripts and "tsc" in scripts["typecheck"] and "--noEmit" in scripts["typecheck"], \
        "scripts.typecheck must invoke tsc --noEmit"


# ---------------------------------------------------------------------------
# AC2 — tsconfig.json: ESM + strict
# ---------------------------------------------------------------------------

def test_scaffold_typescript_monolith_with_cli_and_fastify_server__tsconfig_esm_strict():
    # AC2: tsconfig.json exists, strict=true, module targets ESM (NodeNext or ESNext)
    assert os.path.isfile(TSCONFIG), "tsconfig.json must exist"
    with open(TSCONFIG) as f:
        tsconfig = json.load(f)
    opts = tsconfig.get("compilerOptions", {})
    assert opts.get("strict") is True, "compilerOptions.strict must be true"
    module = opts.get("module", "").lower()
    assert "node" in module or "es" in module, \
        f"compilerOptions.module must target ESM (NodeNext/ESNext), got: {module!r}"


# ---------------------------------------------------------------------------
# AC3 — src/config.ts: all five env vars with correct defaults
# ---------------------------------------------------------------------------

def test_scaffold_typescript_monolith_with_cli_and_fastify_server__config_ts_defaults():
    # AC3: config.ts exports defaults port=8000, milvus=localhost:19530, coll=documents,
    #      model=Xenova/all-MiniLM-L6-v2, dim=384
    assert os.path.isfile(CONFIG_TS), "src/config.ts must exist"
    with open(CONFIG_TS) as f:
        src = f.read()
    for expected in ("8000", "localhost:19530", "documents", "Xenova/all-MiniLM-L6-v2", "384"):
        assert expected in src, f"config.ts must contain default value {expected!r}"


# ---------------------------------------------------------------------------
# AC4 — CLI --help lists exactly serve, ping, ingest, search
# ---------------------------------------------------------------------------

def test_scaffold_typescript_monolith_with_cli_and_fastify_server__cli_help_four_commands():
    # AC4: dist/cli.js --help output lists serve, ping, ingest, search
    if not os.path.isfile(DIST_CLI):
        pytest.skip("dist/cli.js not present — run npm run build first")
    result = subprocess.run(
        ["node", DIST_CLI, "--help"],
        capture_output=True, text=True, cwd=CODER_DIR, timeout=10,
    )
    output = result.stdout + result.stderr
    for cmd in ("serve", "ping", "ingest", "search"):
        assert cmd in output, f"--help must list '{cmd}' command. Output: {output!r}"


# ---------------------------------------------------------------------------
# AC5 — GET /health → HTTP 200 + {"status": "ok"}
# ---------------------------------------------------------------------------

def test_scaffold_typescript_monolith_with_cli_and_fastify_server__health_200_json(fastify_url):
    # AC5: Fastify GET /health returns 200 with body {"status": "ok"}
    with httpx.Client(base_url=fastify_url, timeout=10.0) as c:
        r = c.get("/health")
    assert r.status_code == 200, f"GET /health must return 200, got {r.status_code}"
    body = r.json()
    assert body == {"status": "ok"}, f"body must be {{\"status\": \"ok\"}}, got {body!r}"


# ---------------------------------------------------------------------------
# AC6 — GET / → HTTP 200 serving public/index.html
# ---------------------------------------------------------------------------

def test_scaffold_typescript_monolith_with_cli_and_fastify_server__root_serves_html(fastify_url):
    # AC6: GET / returns 200 with text/html content (public/index.html)
    with httpx.Client(base_url=fastify_url, timeout=10.0) as c:
        r = c.get("/")
    assert r.status_code == 200, f"GET / must return 200, got {r.status_code}"
    ct = r.headers.get("content-type", "")
    assert "text/html" in ct, f"GET / must return text/html, got content-type: {ct!r}"


# ---------------------------------------------------------------------------
# AC7 — Folder structure
# ---------------------------------------------------------------------------

def test_scaffold_typescript_monolith_with_cli_and_fastify_server__folder_structure():
    # AC7: src/{cli.ts,config.ts,commands/,server/,milvus/,embeddings/} and public/ exist
    required = [
        os.path.join(CODER_DIR, "src", "cli.ts"),
        os.path.join(CODER_DIR, "src", "config.ts"),
        os.path.join(CODER_DIR, "src", "commands"),
        os.path.join(CODER_DIR, "src", "server"),
        os.path.join(CODER_DIR, "src", "milvus"),
        os.path.join(CODER_DIR, "src", "embeddings"),
        os.path.join(CODER_DIR, "public"),
    ]
    missing = [p for p in required if not os.path.exists(p)]
    assert not missing, f"Missing required paths: {missing}"


# ---------------------------------------------------------------------------
# AC8 — .env.example documents all five config vars
# ---------------------------------------------------------------------------

def test_scaffold_typescript_monolith_with_cli_and_fastify_server__env_example_all_vars():
    # AC8: .env.example exists and contains PORT, MILVUS_ADDRESS, COLLECTION_NAME,
    #      EMBEDDING_MODEL, DIM
    assert os.path.isfile(ENV_EXAMPLE), ".env.example must exist"
    with open(ENV_EXAMPLE) as f:
        content = f.read()
    for var in ("PORT", "MILVUS_ADDRESS", "COLLECTION_NAME", "EMBEDDING_MODEL", "DIM"):
        assert var in content, f".env.example must document {var!r}"


# ---------------------------------------------------------------------------
# AC9 — .gitignore covers node_modules/, dist/, .env
# ---------------------------------------------------------------------------

def test_scaffold_typescript_monolith_with_cli_and_fastify_server__gitignore_entries():
    # AC9: .gitignore covers node_modules, dist, .env
    assert os.path.isfile(GITIGNORE), ".gitignore must exist"
    with open(GITIGNORE) as f:
        content = f.read()
    for entry in ("node_modules", "dist", ".env"):
        assert entry in content, f".gitignore must cover {entry!r}"


# ---------------------------------------------------------------------------
# AC10 — npm run build exits 0, dist/ produced
# ---------------------------------------------------------------------------

def test_scaffold_typescript_monolith_with_cli_and_fastify_server__build_exits_0():
    # AC10: npm run build exits 0 and produces dist/cli.js
    result = subprocess.run(
        ["npm", "run", "build"],
        capture_output=True, text=True, cwd=CODER_DIR, timeout=120,
    )
    assert result.returncode == 0, (
        f"npm run build must exit 0\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    assert os.path.isfile(DIST_CLI), "dist/cli.js must exist after build"


# ---------------------------------------------------------------------------
# AC11 — npm run typecheck exits 0
# ---------------------------------------------------------------------------

def test_scaffold_typescript_monolith_with_cli_and_fastify_server__typecheck_exits_0():
    # AC11: npm run typecheck exits 0
    result = subprocess.run(
        ["npm", "run", "typecheck"],
        capture_output=True, text=True, cwd=CODER_DIR, timeout=120,
    )
    assert result.returncode == 0, (
        f"npm run typecheck must exit 0\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
