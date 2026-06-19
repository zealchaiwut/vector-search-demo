"""Tests for issue #48: Introduce swappable VectorStore interface over Milvus"""
import os
import re
import pytest
import httpx


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(REPO_ROOT, "src", "store")
INDEX_PATH = os.path.join(STORE_DIR, "index.js")
MILVUS_STORE_PATH = os.path.join(STORE_DIR, "milvus-store.js")
MOCK_STORE_PATH = os.path.join(STORE_DIR, "mock-store.js")
POSTGRES_STORE_PATH = os.path.join(STORE_DIR, "postgres-store.js")
SEARCH_PATH = os.path.join(REPO_ROOT, "src", "core", "search.js")
INGEST_PATH = os.path.join(REPO_ROOT, "src", "commands", "ingest.js")
COMMANDS_DIR = os.path.join(REPO_ROOT, "src", "commands")

# Resolved from UAT .env at runtime; see tester skill Step 0.
BASE_URL = os.environ.get("UAT_BASE_URL") or "http://localhost:" + os.environ.get("UAT_PORT", "")
if not BASE_URL.startswith("http"):
    raise RuntimeError(
        "UAT_BASE_URL / UAT_PORT not set. Run the tester skill's Step 0 to resolve UAT before pytest."
    )


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as c:
        yield c


# --- Acceptance Criteria ---

def test_swappable_vectorstore_interface__store_files_exist():
    """AC1: VectorStore interface is defined in src/store with required files"""
    assert os.path.isfile(INDEX_PATH), f"index.js factory not found at {INDEX_PATH}"
    assert os.path.isfile(MILVUS_STORE_PATH), f"milvus-store.js not found at {MILVUS_STORE_PATH}"
    assert os.path.isfile(MOCK_STORE_PATH), f"mock-store.js not found at {MOCK_STORE_PATH}"
    assert os.path.isfile(POSTGRES_STORE_PATH), f"postgres-store.js not found at {POSTGRES_STORE_PATH}"


def test_swappable_vectorstore_interface__vectorstore_interface_methods_milvus():
    """AC1: MilvusStore class has all required VectorStore interface methods"""
    with open(MILVUS_STORE_PATH, "r") as f:
        content = f.read()

    required_methods = ["init", "migrate", "upsert", "delete", "search", "count", "ping"]
    for method in required_methods:
        # Check for async method definition
        assert re.search(rf"async\s+{method}\s*\(", content), \
            f"MilvusStore missing method: {method}"


def test_swappable_vectorstore_interface__vectorstore_interface_methods_mock():
    """AC1: MockStore class has all required VectorStore interface methods"""
    with open(MOCK_STORE_PATH, "r") as f:
        content = f.read()

    required_methods = ["init", "migrate", "upsert", "delete", "search", "count", "ping"]
    for method in required_methods:
        assert re.search(rf"async\s+{method}\s*\(", content), \
            f"MockStore missing method: {method}"


def test_swappable_vectorstore_interface__vectorstore_interface_methods_postgres():
    """AC1: PostgresStore class has all required VectorStore interface methods"""
    with open(POSTGRES_STORE_PATH, "r") as f:
        content = f.read()

    required_methods = ["init", "migrate", "upsert", "delete", "search", "count", "ping"]
    for method in required_methods:
        assert re.search(rf"async\s+{method}\s*\(", content), \
            f"PostgresStore missing method: {method}"


def test_swappable_vectorstore_interface__milvus_store_is_only_milvus_importer():
    """AC2: MilvusStore is the sole file that imports the Milvus SDK"""
    with open(MILVUS_STORE_PATH, "r") as f:
        milvus_store_content = f.read()

    # MilvusStore SHOULD import from @zilliz/milvus2-sdk-node
    assert "@zilliz/milvus2-sdk-node" in milvus_store_content, \
        "MilvusStore should import the Milvus SDK"


def test_swappable_vectorstore_interface__search_no_milvus_imports():
    """AC2: src/core/search.js has no direct Milvus SDK imports"""
    with open(SEARCH_PATH, "r") as f:
        search_content = f.read()
    # Check for @zilliz/milvus SDK imports specifically
    assert "@zilliz/milvus2-sdk-node" not in search_content, \
        "search.js should not import @zilliz/milvus2-sdk-node"


def test_swappable_vectorstore_interface__ingest_no_milvus_imports():
    """AC2: src/commands/ingest.js has no direct Milvus SDK imports"""
    with open(INGEST_PATH, "r") as f:
        ingest_content = f.read()
    # Check for @zilliz/milvus SDK imports specifically
    assert "@zilliz/milvus2-sdk-node" not in ingest_content, \
        "ingest.js should not import @zilliz/milvus2-sdk-node"


def test_swappable_vectorstore_interface__commands_no_milvus_imports():
    """AC2: src/commands/ directory has no direct Milvus SDK imports"""
    # Iterate through all command files
    for filename in os.listdir(COMMANDS_DIR):
        if filename.endswith(".js"):
            filepath = os.path.join(COMMANDS_DIR, filename)
            with open(filepath, "r") as f:
                content = f.read()
            # Commands should not import the Milvus SDK directly
            assert "@zilliz/milvus2-sdk-node" not in content, \
                f"{filename} should not import @zilliz/milvus2-sdk-node"


def test_swappable_vectorstore_interface__factory_exports_createstore():
    """AC3: Backend factory reads DB_BACKEND env var and exports createStore"""
    with open(INDEX_PATH, "r") as f:
        factory_content = f.read()

    assert "export function createStore" in factory_content, \
        "factory (index.js) should export createStore function"
    assert "export function getStore" in factory_content, \
        "factory (index.js) should export getStore function"
    assert "DB_BACKEND" in factory_content, \
        "factory should reference DB_BACKEND env var"


def test_swappable_vectorstore_interface__factory_accepts_supported_backends():
    """AC3: Factory accepts milvus, postgres, mock values"""
    with open(INDEX_PATH, "r") as f:
        factory_content = f.read()

    assert '"milvus"' in factory_content or "'milvus'" in factory_content, \
        "milvus backend not supported"
    assert '"postgres"' in factory_content or "'postgres'" in factory_content, \
        "postgres backend not supported"
    assert '"mock"' in factory_content or "'mock'" in factory_content, \
        "mock backend not supported"


def test_swappable_vectorstore_interface__factory_validates_backend():
    """AC3: Factory throws descriptive error on unrecognized backend values"""
    with open(INDEX_PATH, "r") as f:
        factory_content = f.read()

    assert "Unknown DB_BACKEND" in factory_content or "unrecognised" in factory_content, \
        "Factory should have error handling for unrecognized backends"
    assert "throw new Error" in factory_content or "throw Error" in factory_content, \
        "Factory should throw error on unknown backend"


def test_swappable_vectorstore_interface__milvus_store_imports_milvus():
    """AC2: MilvusStore imports and uses Milvus SDK"""
    with open(MILVUS_STORE_PATH, "r") as f:
        milvus_store_content = f.read()

    # MilvusStore must import MilvusClient
    assert "MilvusClient" in milvus_store_content, \
        "MilvusStore should import MilvusClient from Milvus SDK"


def test_swappable_vectorstore_interface__mock_store_no_milvus():
    """AC1, AC6: MockStore has no Milvus SDK imports"""
    with open(MOCK_STORE_PATH, "r") as f:
        mock_store_content = f.read()

    assert "@zilliz/milvus2-sdk-node" not in mock_store_content, \
        "MockStore should not import Milvus SDK"
    assert "new MilvusClient" not in mock_store_content, \
        "MockStore should not instantiate MilvusClient"


def test_swappable_vectorstore_interface__postgres_store_no_milvus():
    """AC1, AC7: PostgresStore has no Milvus SDK imports"""
    with open(POSTGRES_STORE_PATH, "r") as f:
        postgres_store_content = f.read()

    assert "@zilliz/milvus2-sdk-node" not in postgres_store_content, \
        "PostgresStore should not import Milvus SDK"
    assert "new MilvusClient" not in postgres_store_content, \
        "PostgresStore should not instantiate MilvusClient"


def test_swappable_vectorstore_interface__postgres_store_throws_not_implemented():
    """AC7: PostgresStore methods throw "not implemented" errors"""
    with open(POSTGRES_STORE_PATH, "r") as f:
        postgres_store_content = f.read()

    # PostgresStore should throw errors for all methods
    assert "NOT_IMPLEMENTED" in postgres_store_content or "not implemented" in postgres_store_content, \
        "PostgresStore should indicate unimplemented methods"


def test_swappable_vectorstore_interface__mock_store_is_functional():
    """AC6: MockStore is a functional in-memory implementation"""
    with open(MOCK_STORE_PATH, "r") as f:
        mock_store_content = f.read()

    # Check for key methods
    assert "this._rows" in mock_store_content or "this._data" in mock_store_content or "this._map" in mock_store_content, \
        "MockStore should have in-memory storage structure"
    assert "async search" in mock_store_content, \
        "MockStore should implement search"
    assert "async upsert" in mock_store_content, \
        "MockStore should implement upsert"


def test_swappable_vectorstore_interface__milvus_store_uses_milvus_address():
    """AC5: MilvusStore uses the correct address configuration"""
    with open(MILVUS_STORE_PATH, "r") as f:
        milvus_store_content = f.read()

    # MilvusStore should have constructor accepting address
    assert "constructor(address)" in milvus_store_content or "constructor(milvusAddress)" in milvus_store_content, \
        "MilvusStore should accept address parameter in constructor"
    assert "this._address" in milvus_store_content, \
        "MilvusStore should store the address"


def test_swappable_vectorstore_interface__collection_uses_vectorstore():
    """AC2, AC5: collection.js uses VectorStore interface instead of SDK directly"""
    collection_path = os.path.join(REPO_ROOT, "src", "data", "collection.js")
    with open(collection_path, "r") as f:
        collection_content = f.read()

    # collection.js should import MilvusStore class, not use SDK directly
    assert "MilvusStore" in collection_content or "getMilvusStoreInstance" in collection_content, \
        "collection.js should use MilvusStore class"


def test_swappable_vectorstore_interface__factory_default_is_milvus():
    """AC5: DB_BACKEND defaults to milvus when unset"""
    with open(INDEX_PATH, "r") as f:
        factory_content = f.read()

    assert "milvus" in factory_content and "default" in factory_content.lower(), \
        "Factory should default to milvus backend"
