"""
Acceptance tests for issue #50: Add Postgres + pgvector backend alongside Milvus

AC1  - docker-compose.yml includes a `postgres` service using pgvector/pgvector:pg16
       image (or newer pg16-compatible tag)
AC2  - The Postgres service exposes port 5432 on the host
AC3  - POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD are configurable via env vars
       in the docker-compose.yml service definition
AC4  - .env.example documents all new Postgres-related variables with placeholder values
AC5  - A pg client module exists under src/db/ (e.g. src/db/pg_client.js)
AC6  - The pg client source contains CREATE EXTENSION IF NOT EXISTS vector to ensure
       pgvector is enabled on first connect / pool initialisation
AC7  - A health-check method can be called that queries pg_extension for 'vector'
       and returns 'vector' confirming the extension; tested live when POSTGRES_HOST set
AC8  - The existing Milvus service definition (etcd, minio, standalone) in
       docker-compose.yml is unchanged
AC9  - All existing Milvus-related source files remain unmodified
AC10 - docker-compose.yml is valid YAML with both postgres and Milvus services present
"""

import json
import os
import subprocess

import pytest
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPOSE_PATH = os.path.join(REPO_ROOT, "docker-compose.yml")
ENV_EXAMPLE_PATH = os.path.join(REPO_ROOT, ".env.example")
PG_CLIENT_PATH = os.path.join(REPO_ROOT, "src", "db", "pg_client.js")

POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "vectordb")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "vectoruser")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "vectorpass")

needs_postgres = pytest.mark.skipif(
    not os.environ.get("POSTGRES_HOST"),
    reason="POSTGRES_HOST not set — skipping live Postgres tests",
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


def load_compose():
    with open(COMPOSE_PATH) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# AC1: postgres service uses pgvector/pgvector:pg16 image
# ---------------------------------------------------------------------------


def test_postgres_pgvector__compose_file_exists():
    # AC1: docker-compose.yml must exist
    assert os.path.isfile(COMPOSE_PATH), f"docker-compose.yml not found at {COMPOSE_PATH}"


def test_postgres_pgvector__compose_has_postgres_service():
    # AC1: must define a postgres service
    compose = load_compose()
    services = compose.get("services", {})
    assert "postgres" in services, (
        f"'postgres' service missing from docker-compose.yml. Got services: {list(services.keys())}"
    )


def test_postgres_pgvector__postgres_image_is_pgvector():
    # AC1: postgres service must use pgvector/pgvector:pg16 or compatible pg16 tag
    compose = load_compose()
    image = compose["services"]["postgres"].get("image", "")
    assert "pgvector" in image.lower(), (
        f"postgres image must contain 'pgvector', got: {image!r}"
    )
    assert "pg16" in image.lower(), (
        f"postgres image must target pg16, got: {image!r}"
    )


# ---------------------------------------------------------------------------
# AC2: Postgres service exposes port 5432
# ---------------------------------------------------------------------------


def test_postgres_pgvector__postgres_exposes_port_5432():
    # AC2: host port 5432 must be mapped for the postgres service
    compose = load_compose()
    postgres = compose["services"]["postgres"]
    ports_raw = postgres.get("ports", [])
    ports_str = " ".join(str(p) for p in ports_raw)
    assert "5432" in ports_str, (
        f"Port 5432 not found in postgres service ports: {ports_raw}"
    )


# ---------------------------------------------------------------------------
# AC3: POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD env vars in service
# ---------------------------------------------------------------------------


def test_postgres_pgvector__postgres_env_vars_in_compose():
    # AC3: postgres service must declare POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    compose = load_compose()
    postgres = compose["services"]["postgres"]
    env_section = postgres.get("environment", {})

    # environment can be a list of "KEY=VALUE" strings or a dict
    if isinstance(env_section, list):
        env_keys = [e.split("=")[0] for e in env_section]
    else:
        env_keys = list(env_section.keys())

    for var in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
        assert var in env_keys, (
            f"'{var}' not found in postgres service environment. Got: {env_keys}"
        )


# ---------------------------------------------------------------------------
# AC4: .env.example documents Postgres variables with placeholder values
# ---------------------------------------------------------------------------


def test_postgres_pgvector__env_example_exists():
    # AC4: .env.example must exist
    assert os.path.isfile(ENV_EXAMPLE_PATH), f".env.example not found at {ENV_EXAMPLE_PATH}"


def test_postgres_pgvector__env_example_has_postgres_vars():
    # AC4: .env.example must document POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    with open(ENV_EXAMPLE_PATH) as f:
        content = f.read()
    for var in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"):
        assert var in content, (
            f"'{var}' not found in .env.example. Ensure it is documented with a placeholder value."
        )


# ---------------------------------------------------------------------------
# AC5: pg client module exists under src/db/
# ---------------------------------------------------------------------------


def test_postgres_pgvector__pg_client_file_exists():
    # AC5: src/db/pg_client.js must exist
    assert os.path.isfile(PG_CLIENT_PATH), (
        f"src/db/pg_client.js not found at {PG_CLIENT_PATH}"
    )


def test_postgres_pgvector__pg_client_exports_getPgClient():
    # AC5: pg_client.js must export a getPgClient function (or similar accessor)
    stdout, stderr, rc = run_node(
        f"""
import {{ getPgClient }} from '{PG_CLIENT_PATH}';
if (typeof getPgClient !== 'function') throw new Error('getPgClient is not a function');
process.stdout.write(JSON.stringify({{ ok: true }}));
"""
    )
    assert rc == 0, f"Import of getPgClient failed: {stderr}"
    assert json.loads(stdout).get("ok") is True


# ---------------------------------------------------------------------------
# AC6: pg client source contains CREATE EXTENSION IF NOT EXISTS vector
# ---------------------------------------------------------------------------


def test_postgres_pgvector__pg_client_contains_create_extension():
    # AC6: pg_client.js must contain the CREATE EXTENSION IF NOT EXISTS vector statement
    with open(PG_CLIENT_PATH) as f:
        source = f.read()
    assert "CREATE EXTENSION IF NOT EXISTS vector" in source, (
        "pg_client.js must call 'CREATE EXTENSION IF NOT EXISTS vector' to enable pgvector on first connect"
    )


# ---------------------------------------------------------------------------
# AC7: health-check method queries pg_extension for 'vector' — live test
# ---------------------------------------------------------------------------


def test_postgres_pgvector__pg_client_has_checkHealth_method():
    # AC7: pg_client.js must export a checkHealth function (static check via source)
    with open(PG_CLIENT_PATH) as f:
        source = f.read()
    # Either exported directly or on the client object
    assert "checkHealth" in source, (
        "pg_client.js must expose a 'checkHealth' function that queries pg_extension for 'vector'"
    )
    assert "pg_extension" in source, (
        "pg_client.js checkHealth must query pg_extension table"
    )
    assert "extname" in source and "'vector'" in source, (
        "pg_client.js checkHealth must filter pg_extension WHERE extname = 'vector'"
    )


@needs_postgres
def test_postgres_pgvector__checkHealth_returns_vector():
    # AC7: live test — checkHealth returns 'vector' when pgvector extension is present
    stdout, stderr, rc = run_node(
        f"""
import {{ getPgClient }} from '{PG_CLIENT_PATH}';
const client = getPgClient();
const result = await client.checkHealth();
if (result !== 'vector') throw new Error(`checkHealth returned: ${{JSON.stringify(result)}}`);
process.stdout.write(JSON.stringify({{ extname: result }}));
await client.end();
""",
        timeout=30,
        env_extra={
            "POSTGRES_HOST": POSTGRES_HOST,
            "POSTGRES_PORT": POSTGRES_PORT,
            "POSTGRES_DB": POSTGRES_DB,
            "POSTGRES_USER": POSTGRES_USER,
            "POSTGRES_PASSWORD": POSTGRES_PASSWORD,
        },
    )
    assert rc == 0, f"checkHealth() live test failed: {stderr}"
    data = json.loads(stdout)
    assert data["extname"] == "vector", (
        f"checkHealth() must return 'vector', got: {data['extname']!r}"
    )


# ---------------------------------------------------------------------------
# AC8: Existing Milvus service definition is unchanged
# ---------------------------------------------------------------------------


def test_postgres_pgvector__milvus_services_still_present():
    # AC8: etcd, minio, standalone must still be defined
    compose = load_compose()
    services = compose.get("services", {})
    for svc in ("etcd", "minio", "standalone"):
        assert svc in services, (
            f"Milvus service '{svc}' was removed from docker-compose.yml — it must remain unchanged"
        )


def test_postgres_pgvector__milvus_standalone_ports_unchanged():
    # AC8: standalone must still expose 19530 and 9091
    compose = load_compose()
    standalone = compose["services"]["standalone"]
    ports_raw = standalone.get("ports", [])
    ports_str = " ".join(str(p) for p in ports_raw)
    assert "19530" in ports_str, (
        f"Milvus standalone port 19530 was altered. Ports: {ports_raw}"
    )
    assert "9091" in ports_str, (
        f"Milvus standalone port 9091 was altered. Ports: {ports_raw}"
    )


def test_postgres_pgvector__milvus_standalone_image_unchanged():
    # AC8: standalone image must still be milvus v2.5.x
    compose = load_compose()
    image = compose["services"]["standalone"].get("image", "")
    assert "milvus" in image.lower() and "2.5" in image, (
        f"Milvus standalone image was changed. Got: {image!r}"
    )


# ---------------------------------------------------------------------------
# AC9: Existing Milvus source files remain unmodified (spot-check key files)
# ---------------------------------------------------------------------------


def test_postgres_pgvector__milvus_client_file_untouched():
    # AC9: src/milvus/client.js must still exist and export getMilvusClient
    milvus_client = os.path.join(REPO_ROOT, "src", "milvus", "client.js")
    assert os.path.isfile(milvus_client), (
        "src/milvus/client.js was deleted — Milvus source files must remain unmodified"
    )
    with open(milvus_client) as f:
        source = f.read()
    assert "getMilvusClient" in source, (
        "src/milvus/client.js was altered — getMilvusClient export is missing"
    )


def test_postgres_pgvector__milvus_schema_file_untouched():
    # AC9: src/milvus/schema.ts must still exist
    milvus_schema = os.path.join(REPO_ROOT, "src", "milvus", "schema.ts")
    assert os.path.isfile(milvus_schema), (
        "src/milvus/schema.ts was deleted — Milvus source files must remain unmodified"
    )


# ---------------------------------------------------------------------------
# AC10: docker-compose.yml is valid YAML with both backends present
# ---------------------------------------------------------------------------


def test_postgres_pgvector__compose_valid_yaml_both_backends():
    # AC10: compose file is valid YAML and has both postgres and Milvus services
    compose = load_compose()
    services = compose.get("services", {})
    assert "postgres" in services, "postgres service missing from docker-compose.yml"
    assert "standalone" in services, "Milvus standalone service missing from docker-compose.yml"
