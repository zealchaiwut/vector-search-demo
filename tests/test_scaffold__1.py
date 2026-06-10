"""
Acceptance tests for issue #1: Scaffold TypeScript monolith with CLI and Fastify server

AC1  - package.json defines a commander bin entry and scripts:
       build (tsc), dev (tsx watch src/cli.ts serve), start, typecheck (tsc --noEmit)
AC2  - tsconfig.json targets ESM with strict mode enabled
AC3  - src/config.ts reads env vars with defaults:
       port 8000, Milvus address localhost:19530, collection documents,
       embedding model Xenova/all-MiniLM-L6-v2, dim 384
AC4  - CLI exposes exactly four commands: serve, ping, ingest, search (visible in --help)
AC5  - Fastify app serves GET /health → {"status": "ok"} with HTTP 200
AC6  - Fastify app serves GET / → public/index.html
AC7  - Folder structure: src/{cli.ts,config.ts,commands/,server/,milvus/,embeddings/} and public/
AC8  - .env.example documents all config vars with their defaults
AC9  - .gitignore covers node_modules/, dist/, and .env
AC10 - npm run build exits 0 with no TypeScript errors
AC11 - npm run typecheck exits 0
"""

import json
import os
import re
import socket
import subprocess
import time

import pytest


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_JSON = os.path.join(REPO_ROOT, "package.json")
TSCONFIG = os.path.join(REPO_ROOT, "tsconfig.json")
CONFIG_TS = os.path.join(REPO_ROOT, "src", "config.ts")
CLI_TS = os.path.join(REPO_ROOT, "src", "cli.ts")
ENV_EXAMPLE = os.path.join(REPO_ROOT, ".env.example")
GITIGNORE = os.path.join(REPO_ROOT, ".gitignore")


# ---------------------------------------------------------------------------
# AC1 — package.json scripts and bin
# ---------------------------------------------------------------------------

def test_ac1_package_json_bin():
    with open(PACKAGE_JSON) as f:
        pkg = json.load(f)
    bin_entry = pkg.get("bin", {})
    assert "commander" in bin_entry, "bin.commander must be defined"


def test_ac1_package_json_scripts():
    with open(PACKAGE_JSON) as f:
        pkg = json.load(f)
    scripts = pkg.get("scripts", {})
    assert "build" in scripts, "scripts.build must be defined"
    assert "tsc" in scripts["build"], "scripts.build must invoke tsc"
    assert "dev" in scripts, "scripts.dev must be defined"
    assert "tsx" in scripts["dev"], "scripts.dev must use tsx"
    assert "src/cli.ts" in scripts["dev"], "scripts.dev must reference src/cli.ts"
    assert "start" in scripts, "scripts.start must be defined"
    assert "typecheck" in scripts, "scripts.typecheck must be defined"
    assert "tsc" in scripts["typecheck"], "scripts.typecheck must invoke tsc"
    assert "--noEmit" in scripts["typecheck"], "scripts.typecheck must pass --noEmit"


# ---------------------------------------------------------------------------
# AC2 — tsconfig.json ESM + strict
# ---------------------------------------------------------------------------

def test_ac2_tsconfig_exists():
    assert os.path.isfile(TSCONFIG), "tsconfig.json must exist"


def test_ac2_tsconfig_strict():
    with open(TSCONFIG) as f:
        tsconfig = json.load(f)
    compiler = tsconfig.get("compilerOptions", {})
    assert compiler.get("strict") is True, "strict must be true"


def test_ac2_tsconfig_esm():
    with open(TSCONFIG) as f:
        tsconfig = json.load(f)
    compiler = tsconfig.get("compilerOptions", {})
    module = compiler.get("module", "").lower()
    assert "node" in module or "es" in module, f"module must target ESM, got: {module}"


# ---------------------------------------------------------------------------
# AC3 — src/config.ts env vars with defaults
# ---------------------------------------------------------------------------

def test_ac3_config_ts_exists():
    assert os.path.isfile(CONFIG_TS), "src/config.ts must exist"


def test_ac3_config_ts_port_default():
    with open(CONFIG_TS) as f:
        content = f.read()
    assert "8000" in content, "config.ts must set default port 8000"


def test_ac3_config_ts_milvus_address():
    with open(CONFIG_TS) as f:
        content = f.read()
    assert "localhost:19530" in content, "config.ts must set default Milvus address localhost:19530"


def test_ac3_config_ts_collection():
    with open(CONFIG_TS) as f:
        content = f.read()
    assert "documents" in content, "config.ts must set default collection name documents"


def test_ac3_config_ts_embedding_model():
    with open(CONFIG_TS) as f:
        content = f.read()
    assert "Xenova/all-MiniLM-L6-v2" in content, "config.ts must set default embedding model"


def test_ac3_config_ts_dim():
    with open(CONFIG_TS) as f:
        content = f.read()
    assert "384" in content, "config.ts must set default dim 384"


# ---------------------------------------------------------------------------
# AC4 — CLI --help shows serve, ping, ingest, search
# ---------------------------------------------------------------------------

def test_ac4_cli_ts_exists():
    assert os.path.isfile(CLI_TS), "src/cli.ts must exist"


def test_ac4_cli_help_shows_four_commands():
    dist_cli = os.path.join(REPO_ROOT, "dist", "cli.js")
    if not os.path.isfile(dist_cli):
        pytest.skip("dist/cli.js not built yet — run npm run build first")
    result = subprocess.run(
        ["node", dist_cli, "--help"],
        capture_output=True, text=True, cwd=REPO_ROOT
    )
    output = result.stdout + result.stderr
    for cmd in ["serve", "ping", "ingest", "search"]:
        assert cmd in output, f"--help output must list '{cmd}' command"


# ---------------------------------------------------------------------------
# AC5 — Fastify GET /health → {"status": "ok"}
# ---------------------------------------------------------------------------

def test_ac5_health_endpoint():
    dist_cli = os.path.join(REPO_ROOT, "dist", "cli.js")
    if not os.path.isfile(dist_cli):
        pytest.skip("dist/cli.js not built yet — run npm run build first")

    port = find_free_port()
    env = {**os.environ, "PORT": str(port)}
    proc = subprocess.Popen(
        ["node", dist_cli, "serve"],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        time.sleep(2)
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             f"http://localhost:{port}/health"],
            capture_output=True, text=True, timeout=5
        )
        assert result.stdout.strip() == "200", "GET /health must return HTTP 200"

        body_result = subprocess.run(
            ["curl", "-s", f"http://localhost:{port}/health"],
            capture_output=True, text=True, timeout=5
        )
        body = json.loads(body_result.stdout)
        assert body == {"status": "ok"}, f"GET /health body must be {{\"status\": \"ok\"}}, got: {body}"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# AC6 — Fastify GET / → public/index.html
# ---------------------------------------------------------------------------

def test_ac6_root_serves_index_html():
    dist_cli = os.path.join(REPO_ROOT, "dist", "cli.js")
    if not os.path.isfile(dist_cli):
        pytest.skip("dist/cli.js not built yet — run npm run build first")

    index_path = os.path.join(REPO_ROOT, "public", "index.html")
    assert os.path.isfile(index_path), "public/index.html must exist"

    port = find_free_port()
    env = {**os.environ, "PORT": str(port)}
    proc = subprocess.Popen(
        ["node", dist_cli, "serve"],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        time.sleep(2)
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             f"http://localhost:{port}/"],
            capture_output=True, text=True, timeout=5
        )
        assert result.stdout.strip() == "200", "GET / must return HTTP 200"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# AC7 — Folder structure
# ---------------------------------------------------------------------------

def test_ac7_folder_structure():
    required = [
        os.path.join(REPO_ROOT, "src", "cli.ts"),
        os.path.join(REPO_ROOT, "src", "config.ts"),
        os.path.join(REPO_ROOT, "src", "commands"),
        os.path.join(REPO_ROOT, "src", "server"),
        os.path.join(REPO_ROOT, "src", "milvus"),
        os.path.join(REPO_ROOT, "src", "embeddings"),
        os.path.join(REPO_ROOT, "public"),
    ]
    for path in required:
        assert os.path.exists(path), f"Required path must exist: {path}"


# ---------------------------------------------------------------------------
# AC8 — .env.example documents all config vars
# ---------------------------------------------------------------------------

def test_ac8_env_example_exists():
    assert os.path.isfile(ENV_EXAMPLE), ".env.example must exist"


def test_ac8_env_example_all_vars():
    with open(ENV_EXAMPLE) as f:
        content = f.read()
    required_vars = ["PORT", "MILVUS_ADDRESS", "COLLECTION_NAME", "EMBEDDING_MODEL", "DIM"]
    for var in required_vars:
        assert var in content, f".env.example must document {var}"


# ---------------------------------------------------------------------------
# AC9 — .gitignore
# ---------------------------------------------------------------------------

def test_ac9_gitignore_exists():
    assert os.path.isfile(GITIGNORE), ".gitignore must exist"


def test_ac9_gitignore_entries():
    with open(GITIGNORE) as f:
        content = f.read()
    assert "node_modules" in content, ".gitignore must cover node_modules/"
    assert "dist" in content, ".gitignore must cover dist/"
    assert ".env" in content, ".gitignore must cover .env"


# ---------------------------------------------------------------------------
# AC10 — npm run build exits 0
# ---------------------------------------------------------------------------

def test_ac10_build_exits_0():
    result = subprocess.run(
        ["npm", "run", "build"],
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=120
    )
    assert result.returncode == 0, (
        f"npm run build must exit 0\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    dist_cli = os.path.join(REPO_ROOT, "dist", "cli.js")
    assert os.path.isfile(dist_cli), "dist/cli.js must exist after build"


# ---------------------------------------------------------------------------
# AC11 — npm run typecheck exits 0
# ---------------------------------------------------------------------------

def test_ac11_typecheck_exits_0():
    result = subprocess.run(
        ["npm", "run", "typecheck"],
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=120
    )
    assert result.returncode == 0, (
        f"npm run typecheck must exit 0\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
