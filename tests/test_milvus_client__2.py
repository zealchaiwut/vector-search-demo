"""
Acceptance tests for issue #2: Add Milvus standalone setup and ping command

AC1  - docker-compose.yml defines three services: etcd, minio, standalone
       (Milvus v2.5.x), exposing ports 19530 (gRPC) and 9091 (HTTP/metrics)
AC2  - package.json contains milvus:up and milvus:down scripts
AC3  - src/milvus/client.js exports a singleton MilvusClient whose
       @zilliz/milvus2-sdk-node import is dynamic (no top-level import at module scope)
AC4  - MilvusClient exposes a ping() method returning the server version string
AC5  - src/commands/ping.js wires the commander ping subcommand to call ping()
AC6  - With Milvus running: commander ping prints
       'Milvus reachable at <address> (version X)' and exits 0
AC7  - With Milvus stopped: commander ping prints a message containing
       'Is it running? Try npm run milvus:up' and exits non-zero
AC8  - No gRPC/SDK code is loaded when running any non-Milvus CLI command
"""

import json
import os
import re
import subprocess

import pytest
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPOSE_PATH = os.path.join(REPO_ROOT, "docker-compose.yml")
PACKAGE_JSON_PATH = os.path.join(REPO_ROOT, "package.json")
CLIENT_PATH = os.path.join(REPO_ROOT, "src", "milvus", "client.js")
PING_CMD_PATH = os.path.join(REPO_ROOT, "src", "commands", "ping.js")
CLI_PATH = os.path.join(REPO_ROOT, "src", "cli.js")

MILVUS_HOST = os.environ.get("MILVUS_HOST", "localhost")
MILVUS_PORT = os.environ.get("MILVUS_PORT", "19530")

needs_milvus = pytest.mark.skipif(
    not os.environ.get("MILVUS_HOST"),
    reason="MILVUS_HOST not set — skipping live Milvus tests",
)


def run_node(script, timeout=30, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
        env=env,
    )
    return result.stdout, result.stderr, result.returncode


def run_cli(args, timeout=30, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["node", CLI_PATH] + args,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
        env=env,
    )


# ---------------------------------------------------------------------------
# AC1: docker-compose.yml defines etcd, minio, standalone with correct ports
# ---------------------------------------------------------------------------


def test_milvus_client__compose_file_exists():
    # AC1: docker-compose.yml must exist
    assert os.path.isfile(COMPOSE_PATH), f"docker-compose.yml not found at {COMPOSE_PATH}"


def test_milvus_client__compose_has_required_services():
    # AC1: must define etcd, minio, standalone services
    with open(COMPOSE_PATH) as f:
        compose = yaml.safe_load(f)
    services = compose.get("services", {})
    for svc in ("etcd", "minio", "standalone"):
        assert svc in services, f"Service '{svc}' missing from docker-compose.yml. Got: {list(services.keys())}"


def test_milvus_client__compose_standalone_ports():
    # AC1: standalone must expose 19530 and 9091
    with open(COMPOSE_PATH) as f:
        compose = yaml.safe_load(f)
    standalone = compose["services"]["standalone"]
    ports_raw = standalone.get("ports", [])
    # Ports may be strings like "19530:19530" or dicts
    ports_str = " ".join(str(p) for p in ports_raw)
    assert "19530" in ports_str, f"Port 19530 not found in standalone ports: {ports_raw}"
    assert "9091" in ports_str, f"Port 9091 not found in standalone ports: {ports_raw}"


def test_milvus_client__compose_standalone_image_version():
    # AC1: standalone must use Milvus v2.5.x image
    with open(COMPOSE_PATH) as f:
        compose = yaml.safe_load(f)
    standalone = compose["services"]["standalone"]
    image = standalone.get("image", "")
    assert "milvus" in image.lower(), f"standalone image should be milvus, got: {image!r}"
    assert "2.5" in image, f"standalone image should be v2.5.x, got: {image!r}"


# ---------------------------------------------------------------------------
# AC2: package.json contains milvus:up and milvus:down scripts
# ---------------------------------------------------------------------------


def test_milvus_client__package_json_milvus_up():
    # AC2: milvus:up script must exist
    with open(PACKAGE_JSON_PATH) as f:
        pkg = json.load(f)
    scripts = pkg.get("scripts", {})
    assert "milvus:up" in scripts, f"milvus:up not in package.json scripts. Got: {list(scripts.keys())}"
    assert "docker compose up" in scripts["milvus:up"] or "docker-compose up" in scripts["milvus:up"], (
        f"milvus:up should run 'docker compose up', got: {scripts['milvus:up']!r}"
    )
    assert "-d" in scripts["milvus:up"], f"milvus:up should run in detached mode (-d), got: {scripts['milvus:up']!r}"


def test_milvus_client__package_json_milvus_down():
    # AC2: milvus:down script must exist
    with open(PACKAGE_JSON_PATH) as f:
        pkg = json.load(f)
    scripts = pkg.get("scripts", {})
    assert "milvus:down" in scripts, f"milvus:down not in package.json scripts. Got: {list(scripts.keys())}"
    assert "docker compose down" in scripts["milvus:down"] or "docker-compose down" in scripts["milvus:down"], (
        f"milvus:down should run 'docker compose down', got: {scripts['milvus:down']!r}"
    )


# ---------------------------------------------------------------------------
# AC3: src/milvus/client.js uses dynamic import (no top-level SDK import)
# ---------------------------------------------------------------------------


def test_milvus_client__client_file_exists():
    # AC3: src/milvus/client.js must exist
    assert os.path.isfile(CLIENT_PATH), f"src/milvus/client.js not found at {CLIENT_PATH}"


def test_milvus_client__no_toplevel_milvus_import():
    # AC3: no top-level 'import ... from @zilliz/milvus2-sdk-node' at module scope
    with open(CLIENT_PATH) as f:
        source = f.read()
    lines = source.splitlines()
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("import") and "@zilliz/milvus2-sdk-node" in stripped:
            pytest.fail(
                f"Top-level SDK import found at client.js:{i} — must use dynamic import() instead.\n  Line: {line!r}"
            )


def test_milvus_client__uses_dynamic_import():
    # AC3: must use dynamic import() for @zilliz/milvus2-sdk-node
    with open(CLIENT_PATH) as f:
        source = f.read()
    assert "import(" in source and "@zilliz/milvus2-sdk-node" in source, (
        "client.js must use dynamic import() for @zilliz/milvus2-sdk-node"
    )


def test_milvus_client__exports_getMilvusClient():
    # AC3: must export a singleton accessor (getMilvusClient or similar)
    stdout, stderr, rc = run_node(
        f"""
import {{ getMilvusClient }} from '{CLIENT_PATH}';
if (typeof getMilvusClient !== 'function') throw new Error('getMilvusClient is not a function');
process.stdout.write(JSON.stringify({{ ok: true }}));
"""
    )
    assert rc == 0, f"Import failed: {stderr}"
    assert json.loads(stdout)["ok"] is True


# ---------------------------------------------------------------------------
# AC4: MilvusClient has ping() method
# ---------------------------------------------------------------------------


def test_milvus_client__ping_is_function():
    # AC4: the object returned by getMilvusClient() must have a ping method
    stdout, stderr, rc = run_node(
        f"""
import {{ getMilvusClient }} from '{CLIENT_PATH}';
const client = getMilvusClient();
if (typeof client.ping !== 'function') throw new Error('ping is not a function on client');
process.stdout.write(JSON.stringify({{ ok: true }}));
"""
    )
    assert rc == 0, f"ping check failed: {stderr}"
    assert json.loads(stdout)["ok"] is True


@needs_milvus
def test_milvus_client__ping_returns_version_string():
    # AC4: ping() returns the server version string
    stdout, stderr, rc = run_node(
        f"""
import {{ getMilvusClient }} from '{CLIENT_PATH}';
const client = getMilvusClient();
const version = await client.ping();
if (typeof version !== 'string' || !version.trim()) throw new Error(`ping() returned non-string: ${{JSON.stringify(version)}}`);
process.stdout.write(JSON.stringify({{ version }}));
""",
        timeout=30,
        env_extra={"MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
    )
    assert rc == 0, f"ping() failed: {stderr}"
    data = json.loads(stdout)
    assert data["version"], f"ping() returned empty version: {data['version']!r}"


# ---------------------------------------------------------------------------
# AC5: src/commands/ping.js exists and wires the ping subcommand
# ---------------------------------------------------------------------------


def test_milvus_client__ping_command_file_exists():
    # AC5: src/commands/ping.js must exist
    assert os.path.isfile(PING_CMD_PATH), f"src/commands/ping.js not found at {PING_CMD_PATH}"


def test_milvus_client__ping_command_exports_runPing():
    # AC5: runPing must be an exported function
    stdout, stderr, rc = run_node(
        f"""
import {{ runPing }} from '{PING_CMD_PATH}';
if (typeof runPing !== 'function') throw new Error('runPing is not a function');
process.stdout.write(JSON.stringify({{ ok: true }}));
"""
    )
    assert rc == 0, f"Import failed: {stderr}"
    assert json.loads(stdout)["ok"] is True


def test_milvus_client__cli_registers_ping():
    # AC5: cli.js must branch on 'ping' command
    with open(CLI_PATH) as f:
        cli_source = f.read()
    assert "ping" in cli_source, "cli.js does not reference 'ping' command"


# ---------------------------------------------------------------------------
# AC6: With Milvus running, commander ping prints reachable message and exits 0
# ---------------------------------------------------------------------------


@needs_milvus
def test_milvus_client__ping_success_output():
    # AC6: output contains 'Milvus reachable at' and exits 0
    result = run_cli(
        ["ping"],
        timeout=30,
        env_extra={"MILVUS_HOST": MILVUS_HOST, "MILVUS_PORT": MILVUS_PORT},
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"commander ping should exit 0 when Milvus is running, got {result.returncode}. Output: {combined}"
    )
    assert "Milvus reachable at" in combined, (
        f"Output should contain 'Milvus reachable at'. Got: {combined!r}"
    )
    assert re.search(r"version\s+\S+", combined, re.IGNORECASE) or re.search(r"v\d+\.\d+", combined), (
        f"Output should contain version string. Got: {combined!r}"
    )


# ---------------------------------------------------------------------------
# AC7: With Milvus stopped, commander ping prints error hint and exits non-zero
# ---------------------------------------------------------------------------


def test_milvus_client__ping_failure_output():
    # AC7: output contains 'Is it running? Try npm run milvus:up' and exits non-zero
    # Use a port/host guaranteed to be unreachable
    result = run_cli(
        ["ping"],
        timeout=15,
        env_extra={"MILVUS_HOST": "127.0.0.1", "MILVUS_PORT": "19999"},
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        f"commander ping should exit non-zero when Milvus unreachable, got 0. Output: {combined}"
    )
    assert "Is it running? Try npm run milvus:up" in combined, (
        f"Output should contain 'Is it running? Try npm run milvus:up'. Got: {combined!r}"
    )


# ---------------------------------------------------------------------------
# AC8: No gRPC/SDK code loaded for non-Milvus commands
# ---------------------------------------------------------------------------


def test_milvus_client__no_sdk_import_on_search_command():
    # AC8: running commander search does not load @zilliz/milvus2-sdk-node
    # Use NODE_OPTIONS to trace module loading
    env = os.environ.copy()
    env["NODE_OPTIONS"] = "--experimental-loader=./tests/trace_loader.mjs"
    # Simpler: inspect that client.js is NOT imported when running search
    # by checking that the dynamic import guard is in cli.js/search.js
    with open(CLI_PATH) as f:
        cli_source = f.read()
    with open(os.path.join(REPO_ROOT, "src", "commands", "search.js")) as f:
        search_source = f.read()
    # Neither cli.js nor search.js should contain a direct milvus import
    assert "@zilliz/milvus2-sdk-node" not in cli_source, (
        "cli.js must not import @zilliz/milvus2-sdk-node — use dynamic import in client.js only"
    )
    assert "@zilliz/milvus2-sdk-node" not in search_source, (
        "search.js must not import @zilliz/milvus2-sdk-node"
    )


def test_milvus_client__no_sdk_import_in_cli_top_level():
    # AC8: cli.js must not statically import milvus client module at top level
    # This ensures non-Milvus commands don't trigger gRPC init
    with open(CLI_PATH) as f:
        source = f.read()
    # The ping command import should be lazy (inside the ping branch) or client.js
    # must use dynamic import internally
    # Verify client.js is not imported at top of cli.js
    lines = source.splitlines()
    top_level_imports = [l for l in lines if l.strip().startswith("import") and "client" in l.lower() and "milvus" in l.lower()]
    assert not top_level_imports, (
        f"cli.js should not statically import milvus client at top level. Found: {top_level_imports}"
    )
