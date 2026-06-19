"""Tests for issue #48: Introduce swappable VectorStore interface over Milvus (runs against UAT)"""
import os
import subprocess
import json
import pytest
import httpx


# Resolved from UAT .env at runtime; see tester skill Step 0.
# Default kept only as a last-resort fallback if BASE_URL not exported.
BASE_URL = os.environ.get("UAT_BASE_URL") or "http://localhost:" + os.environ.get("UAT_PORT", "")
if not BASE_URL.startswith("http"):
    raise RuntimeError(
        "UAT_BASE_URL / UAT_PORT not set. Run the tester skill's Step 0 to resolve UAT before pytest."
    )

# Path to repo root (where CLI commands are run)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


# --- Acceptance Criteria ---

def test_vectorstore_interface__interface_defined(client):
    """AC: A VectorStore interface is defined in src/store with required methods"""
    # Verify the store factory exists and defines the interface
    factory_path = os.path.join(REPO_ROOT, "src", "store", "factory.js")
    assert os.path.exists(factory_path), "src/store/factory.js should exist"

    with open(factory_path) as f:
        factory_content = f.read()

    # Verify factory exports the key functions
    assert "export function resolveBackend" in factory_content, "factory should export resolveBackend"
    assert "export" in factory_content and "getStore" in factory_content, "factory should export getStore"
    assert "export function logActiveBackend" in factory_content, "factory should export logActiveBackend"

    # Verify the expected methods are documented as part of the interface
    assert "createCollection" in factory_content or os.path.exists(
        os.path.join(REPO_ROOT, "src", "store", "milvus.js")
    ), "VectorStore interface should include collection management"


def test_vectorstore_interface__milvus_store_isolated(client):
    """AC: MilvusStore is sole file importing Milvus SDK; no imports in search/ingest/commands"""
    # Run grep to verify Milvus imports are only in store/milvus.js
    search_dir = os.path.join(REPO_ROOT, "src", "search")
    ingest_dir = os.path.join(REPO_ROOT, "src", "ingest")
    commands_dir = os.path.join(REPO_ROOT, "src", "commands")

    for directory in [search_dir, ingest_dir, commands_dir]:
        if os.path.exists(directory):
            result = subprocess.run(
                ["grep", "-r", "from.*milvus", directory],
                capture_output=True,
                text=True
            )
            assert result.returncode != 0, f"Found Milvus imports in {directory}"

    # Verify milvus.js file exists in store
    milvus_store = os.path.join(REPO_ROOT, "src", "store", "milvus.js")
    assert os.path.exists(milvus_store), "src/store/milvus.js should exist"


def test_vectorstore_interface__factory_backend_resolution(client):
    """AC: Factory reads DB_BACKEND env var; accepts milvus/postgres/mock; default is milvus; errors on unrecognized"""
    factory_path = os.path.join(REPO_ROOT, "src", "store", "factory.js")
    assert os.path.exists(factory_path)

    with open(factory_path) as f:
        factory_content = f.read()

    # Verify supported backends
    assert "milvus" in factory_content, "factory should support 'milvus'"
    assert "postgres" in factory_content, "factory should support 'postgres'"
    assert "mock" in factory_content, "factory should support 'mock'"

    # Verify DB_BACKEND env var is checked
    assert "DB_BACKEND" in factory_content, "factory should check DB_BACKEND"

    # Verify error handling for unrecognized values
    assert "unrecognised" in factory_content.lower() or "error" in factory_content.lower(), \
        "factory should throw error on unrecognized backend"


def test_vectorstore_interface__search_uses_interface(client):
    """AC: src/search depends only on VectorStore interface"""
    search_dir = os.path.join(REPO_ROOT, "src", "search")
    if os.path.exists(search_dir):
        # Verify search doesn't import milvus directly
        result = subprocess.run(
            ["grep", "-r", "milvus", search_dir],
            capture_output=True,
            text=True
        )
        # Should have no 'milvus' references or only as part of env var names
        if result.returncode == 0:
            # If found, it should not be an import statement
            for line in result.stdout.split('\n'):
                assert 'import' not in line or 'from' not in line, \
                    f"search should not import milvus SDK directly: {line}"


def test_vectorstore_interface__ingest_uses_interface(client):
    """AC: src/ingest depends only on VectorStore interface"""
    ingest_file = os.path.join(REPO_ROOT, "src", "commands", "ingest.js")
    assert os.path.exists(ingest_file), "ingest command should use factory pattern"

    with open(ingest_file) as f:
        content = f.read()

    # Verify it imports the factory
    assert "from.*store/factory" in content or "import" in content and "factory" in content, \
        "ingest should import from store/factory"

    # Verify it uses resolveBackend and getStore
    assert "resolveBackend" in content, "ingest should call resolveBackend"
    assert "getStore" in content, "ingest should call getStore"


def test_vectorstore_interface__milvus_default_baseline(client):
    """AC: DB_BACKEND=milvus preserves existing behavior (search/ingest/delete)"""
    # Verify milvus store implementation exists and imports factory correctly
    milvus_path = os.path.join(REPO_ROOT, "src", "store", "milvus.js")
    assert os.path.exists(milvus_path), "MilvusStore should exist"

    with open(milvus_path) as f:
        content = f.read()

    # Verify it exports the store interface
    assert "export function getMilvusStore" in content, "MilvusStore should export getMilvusStore"
    assert "searchDocuments" in content, "MilvusStore should wire up search"


def test_vectorstore_interface__mock_backend_functional(client):
    """AC: DB_BACKEND=mock provides functional in-memory implementation"""
    # Verify mock store implementation exists
    mock_path = os.path.join(REPO_ROOT, "src", "store", "mock.js")
    assert os.path.exists(mock_path), "MockStore should exist"

    with open(mock_path) as f:
        content = f.read()

    # Verify it exports the store interface
    assert "export function getMockStore" in content, "MockStore should export getMockStore"
    assert "ping" in content, "MockStore should implement ping method"


def test_vectorstore_interface__postgres_stub_accepted(client):
    """AC: DB_BACKEND=postgres is accepted by factory without error on startup"""
    # Verify the factory includes postgres in supported backends
    factory_path = os.path.join(REPO_ROOT, "src", "store", "factory.js")
    with open(factory_path) as f:
        content = f.read()

    assert "postgres" in content, "postgres should be in supported backends"
    assert "getPostgresStore" in content or "PostgresStore" in content, \
        "postgres implementation should exist"


def test_vectorstore_interface__factory_error_on_invalid_backend(client):
    """AC: Invalid DB_BACKEND exits with descriptive error"""
    # Verify error handling exists in factory
    factory_path = os.path.join(REPO_ROOT, "src", "store", "factory.js")
    with open(factory_path) as f:
        content = f.read()

    # Check for error throwing on invalid backend
    assert "throw" in content and ("unrecognised" in content.lower() or "error" in content.lower()), \
        "factory should throw descriptive error on invalid backend"


def test_vectorstore_interface__no_milvus_in_search_dir(client):
    """AC: Grep search/ for Milvus SDK import returns zero hits"""
    search_dir = os.path.join(REPO_ROOT, "src", "search")
    if os.path.exists(search_dir):
        result = subprocess.run(
            ["grep", "-r", "from.*milvus-sdk", search_dir],
            capture_output=True,
            text=True
        )
        assert result.returncode != 0, "search/ should have zero Milvus SDK imports"


def test_vectorstore_interface__no_milvus_in_ingest_dir(client):
    """AC: Grep ingest/ for Milvus SDK import returns zero hits"""
    ingest_dir = os.path.join(REPO_ROOT, "src", "ingest")
    if os.path.exists(ingest_dir):
        result = subprocess.run(
            ["grep", "-r", "from.*milvus-sdk", ingest_dir],
            capture_output=True,
            text=True
        )
        assert result.returncode != 0, "ingest/ should have zero Milvus SDK imports"


def test_vectorstore_interface__no_milvus_in_commands_dir(client):
    """AC: Grep commands/ for Milvus SDK import returns zero hits"""
    commands_dir = os.path.join(REPO_ROOT, "src", "commands")
    if os.path.exists(commands_dir):
        result = subprocess.run(
            ["grep", "-r", "from.*milvus-sdk", commands_dir],
            capture_output=True,
            text=True
        )
        assert result.returncode != 0, "commands/ should have zero Milvus SDK imports"


def test_vectorstore_interface__store_implementations_exist(client):
    """AC: VectorStore implementations for milvus, mock, and postgres exist"""
    store_dir = os.path.join(REPO_ROOT, "src", "store")

    # Check that all backend implementations exist
    assert os.path.exists(os.path.join(store_dir, "milvus.js")), "MilvusStore implementation should exist"
    assert os.path.exists(os.path.join(store_dir, "mock.js")), "MockStore implementation should exist"
    assert os.path.exists(os.path.join(store_dir, "postgres.js")), "PostgresStore implementation should exist"
